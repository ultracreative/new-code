"""
The New Code compiler, v1.0.

The compiler takes a declaration with a hole (``≔ ??``) and an intent
block, and produces a Python implementation that satisfies the intent
as closely as the backing language model can manage.

Three backends:

  * ``OfflineCompiler`` — pattern-matched dispatch. Deterministic; covers a
    growing library of common intents. Used in offline mode and as a
    fallback when no API key is set.
  * ``AnthropicCompiler`` — calls the Anthropic API. Validates the response
    through a syntax check, an AST safety pass, and the constraint report.
    Now caches accepted bodies by content-addressable hash so the same
    intent produces the same body across runs (snapshot mode).
  * ``SnapshotCompiler`` — replays a recorded LLM session from disk. Used
    by tests so the LLM path is exercised without flaky API calls.

Explicit bodies (anything not ``≔ ??``) are now parsed by [expr.py](expr.py)
and transpiled to Python. The Python ``eval()`` shortcut from v0.x is gone.
"""

from __future__ import annotations

import ast
import datetime
import hashlib
import json
import os
import re
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from . import expr as _expr
from .constraint_check import ConstraintReport, build_report
from .parser import Function, Intent, Process as ProcessDecl


# -----------------------------------------------------------------------------
# Online / offline mode.
# -----------------------------------------------------------------------------
#
# v1.0 makes the online/offline split explicit. Every backend honours a mode
# flag, and the auto-selector picks the right one based on environment +
# explicit user choice. The intent-hole compilation path is the only thing
# that requires an online backend; everything else (explicit bodies,
# snapshots, the offline pattern matcher) works without network access.

OFFLINE = "offline"
ONLINE = "online"
SNAPSHOT = "snapshot"


class OfflineHoleError(RuntimeError):
    """Raised when an intent hole is encountered in offline mode."""

    def __init__(self, decl_name: str, intent_text: str = ""):
        msg = (
            f"Cannot compile intent hole for {decl_name!r} in offline mode. "
            f"Either:\n"
            f"  - rerun with --online (and ANTHROPIC_API_KEY set), or\n"
            f"  - provide a recorded snapshot, or\n"
            f"  - replace `≔ ??` with an explicit body."
        )
        if intent_text:
            msg += f"\nIntent was: 「{intent_text}」"
        super().__init__(msg)
        self.decl_name = decl_name
        self.intent_text = intent_text


# -----------------------------------------------------------------------------
# The context exposed to compiled code.
# -----------------------------------------------------------------------------
#
# When the compiler produces a Python body, that body is evaluated with the
# New Code standard library in scope. Compiled functions can refer to W, w,
# sine, sq, tri, saw, pulse, e0, silence, superpose, oscillate, drift, and
# all the coupling functions by their short names.

def _stdlib_scope() -> Dict[str, Any]:
    from . import stdlib as _stdlib
    return _stdlib.build_scope()


# -----------------------------------------------------------------------------
# Compiled artefact.
# -----------------------------------------------------------------------------

@dataclass
class Provenance:
    """Where a compiled body came from. Stored on every Compiled artefact
    for inspection, reproducibility, and the approval workflow."""
    backend: str             # "offline" | "anthropic" | "snapshot" | "explicit"
    model: Optional[str] = None
    intent_hash: Optional[str] = None
    body_hash: Optional[str] = None
    timestamp: Optional[str] = None
    accepted: bool = False
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "backend": self.backend,
            "model": self.model,
            "intent_hash": self.intent_hash,
            "body_hash": self.body_hash,
            "timestamp": self.timestamp,
            "accepted": self.accepted,
            "notes": self.notes,
        }


@dataclass
class Compiled:
    name: str
    callable_: Callable
    source: str            # the Python body produced by the compiler
    intent: Intent
    notes: str = ""
    report: Optional[ConstraintReport] = None
    provenance: Optional[Provenance] = None

    def __call__(self, *args, **kwargs):
        return self.callable_(*args, **kwargs)

    def __repr__(self) -> str:
        suffix = ""
        if self.provenance is not None:
            tag = self.provenance.backend
            if self.provenance.accepted:
                tag += "✓"
            suffix = f" [{tag}]"
        return f"<compiled {self.name}{suffix}>"


# -----------------------------------------------------------------------------
# Intent / body hashing — content-addressable identity for snapshots & cache.
# -----------------------------------------------------------------------------

def intent_hash(decl: Any) -> str:
    """Stable hash over the declaration shape that drives compilation.

    The hash includes the declaration name, kind (fn or process), arguments,
    return type, and every populated intent clause. It deliberately ignores
    the body text (which is `??` for holes), so the same hole produces the
    same hash whether or not whitespace differs.
    """
    h = hashlib.sha256()
    if isinstance(decl, Function):
        kind = "fn"
        args_repr = "|".join(f"{a.name}:{a.type_}" for a in decl.args)
        ret = decl.return_type
    elif isinstance(decl, ProcessDecl):
        kind = "process"
        args_repr = ""
        ret = decl.return_type
    else:
        kind = "other"
        args_repr = ""
        ret = ""
    parts = [
        kind, decl.name, args_repr, ret,
        decl.intent.intent or "",
        decl.intent.forbid or "",
        decl.intent.ensure or "",
        decl.intent.requires or "",
        decl.intent.emits or "",
        decl.intent.consumes or "",
        decl.intent.guard or "",
    ]
    h.update("\x1f".join(parts).encode("utf-8"))
    return h.hexdigest()[:16]


def body_hash(source: str) -> str:
    return hashlib.sha256(source.encode("utf-8")).hexdigest()[:16]


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


# -----------------------------------------------------------------------------
# On-disk snapshot store.
# -----------------------------------------------------------------------------
#
# A snapshot is a mapping from intent_hash → (source, metadata). We keep them
# in a single JSON file for portability — small enough to commit alongside
# tests, big enough to replay an entire test suite without an API call.

DEFAULT_SNAPSHOT_DIR = Path.home() / ".newcode" / "snapshots"
DEFAULT_CACHE_DIR = Path.home() / ".newcode" / "cache"


class SnapshotStore:
    """A keyed store of accepted compiler outputs, persisted as JSON.

    Each entry is keyed by `intent_hash` and carries the body, model name,
    timestamp, and an `accepted` flag. The store is the source of truth for
    deterministic replays in tests and for the REPL's `:accept` workflow.
    """

    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path) if path else (DEFAULT_SNAPSHOT_DIR / "default.json")
        self._entries: Dict[str, Dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            try:
                with self.path.open("r", encoding="utf-8") as f:
                    self._entries = json.load(f)
            except (json.JSONDecodeError, OSError):
                self._entries = {}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as f:
            json.dump(self._entries, f, indent=2, sort_keys=True)

    def get(self, intent_hash_: str) -> Optional[Dict[str, Any]]:
        return self._entries.get(intent_hash_)

    def put(self, intent_hash_: str, *, source: str, model: str,
            decl_name: str, accepted: bool = False) -> None:
        self._entries[intent_hash_] = {
            "source": source,
            "model": model,
            "decl_name": decl_name,
            "body_hash": body_hash(source),
            "timestamp": _now_iso(),
            "accepted": accepted,
        }
        self._save()

    def mark_accepted(self, intent_hash_: str, accepted: bool = True) -> bool:
        entry = self._entries.get(intent_hash_)
        if entry is None:
            return False
        entry["accepted"] = accepted
        entry["timestamp"] = _now_iso()
        self._save()
        return True

    def remove(self, intent_hash_: str) -> bool:
        if intent_hash_ not in self._entries:
            return False
        del self._entries[intent_hash_]
        self._save()
        return True

    def __len__(self) -> int:
        return len(self._entries)

    def __contains__(self, key: str) -> bool:
        return key in self._entries

    def keys(self):
        return self._entries.keys()


# -----------------------------------------------------------------------------
# Safety — reject obviously unsafe generated code.
# -----------------------------------------------------------------------------

_FORBIDDEN_NODES = (
    ast.Import, ast.ImportFrom, ast.Global, ast.Nonlocal,
    ast.AsyncFunctionDef, ast.AsyncWith, ast.AsyncFor,
    ast.Try,  # discourage swallowing errors silently
)

_FORBIDDEN_NAMES = {
    "exec", "eval", "compile", "__import__", "open", "input",
    "globals", "locals", "vars", "getattr", "setattr", "delattr",
    "breakpoint", "help",
}


def _reject_unsafe(tree: ast.AST) -> Optional[str]:
    for node in ast.walk(tree):
        if isinstance(node, _FORBIDDEN_NODES):
            return f"forbidden construct: {type(node).__name__}"
        if isinstance(node, ast.Name) and node.id in _FORBIDDEN_NAMES:
            return f"forbidden name: {node.id}"
        if isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            return f"dunder access: {node.attr}"
    return None


# -----------------------------------------------------------------------------
# The offline compiler: pattern-matched intents.
# -----------------------------------------------------------------------------

class OfflineCompiler:
    """A stub compiler that matches intents against a small known set.

    This exists so the system can be exercised without an API key, and so
    tests are deterministic. It is the default backend in offline mode and
    a fallback when no API key is set.
    """

    backend_name = "offline"

    def compile(self, decl: Function) -> Compiled:
        intent = decl.intent.intent.lower()
        args = [a.name for a in decl.args]

        # A handful of hand-written patterns. Intentionally small.
        if "amplify" in intent or "scale the amplitude" in intent:
            src = _src_amplify(args)
        elif "invert" in intent and "phase" in intent:
            src = _src_invert(args)
        elif "collapse" in intent or "reduce" in intent and "scalar" in intent:
            src = _src_collapse(args)
        elif "drift" in intent or "age" in intent:
            src = _src_drift(args)
        elif "coherence" in intent or "similar" in intent:
            src = _src_coherence(args)
        elif "superpose" in intent or "sum" in intent or "mix" in intent:
            src = _src_superpose(args)
        else:
            raise NotImplementedError(
                f"OfflineCompiler has no pattern for intent: {intent!r}. "
                f"Use AnthropicCompiler or add a pattern."
            )

        prov = Provenance(
            backend="offline",
            intent_hash=intent_hash(decl),
            body_hash=body_hash(src),
            timestamp=_now_iso(),
            accepted=True,  # deterministic patterns are always accepted
            notes="offline pattern match",
        )
        return _compile_function_body(
            decl,
            source=src,
            notes="compiled by offline pattern match",
            provenance=prov,
        )

    def compile_process(
        self,
        decl: ProcessDecl,
        extra_scope: Optional[Dict[str, Any]] = None,
    ) -> Compiled:
        source = _offline_process_source(decl, extra_scope or {})
        prov = Provenance(
            backend="offline",
            intent_hash=intent_hash(decl),
            body_hash=body_hash(source),
            timestamp=_now_iso(),
            accepted=True,
            notes="offline pattern match",
        )
        return _compile_process_body(
            decl,
            source=source,
            notes="compiled by offline pattern match",
            extra_scope=extra_scope,
            provenance=prov,
        )


def _src_amplify(args):
    w_arg, gain_arg = args[0], args[1]
    return (
        f"    f_, A_, phi_, sigma_ = {w_arg}.unpack()\n"
        f"    return W(f=f_, A=A_ * {gain_arg}, phi=phi_, sigma=sigma_)"
    )


def _src_invert(args):
    return f"    return invert({args[0]})"


def _src_collapse(args):
    return f"    return collapse({args[0]})"


def _src_drift(args):
    return f"    return drift({args[0]}, {args[1]})"


def _src_coherence(args):
    return f"    return coherence({args[0]}, {args[1]})"


def _src_superpose(args):
    if len(args) == 1:
        return (
            f"    result = silence\n"
            f"    for x in {args[0]}:\n"
            f"        result = superpose(result, x)\n"
            f"    return result"
        )
    return f"    return superpose({args[0]}, {args[1]})"


def _offline_process_source(decl: ProcessDecl, scope: Dict[str, Any]) -> str:
    intent = decl.intent.intent.lower()
    binding_name = _match_scope_name(intent, scope)
    if binding_name is None:
        raise NotImplementedError(
            "OfflineCompiler could not identify a referenced binding in "
            f"process intent: {decl.intent.intent!r}"
        )

    value = scope[binding_name]
    process_name = decl.name
    drift_match = re.search(
        r"drift\s+[a-z_][\w]*\s+by\s+([-+]?(?:\d+(?:\.\d*)?|\.\d+))",
        intent,
    )
    emitish = any(word in intent for word in ("emit", "steady", "every", "repeat"))

    if drift_match:
        delta = drift_match.group(1)
        if _is_process_like(value):
            return f"    return drift_process({binding_name}, delta_per_step={delta})"
        if _is_wave_like(value):
            return (
                f"    return drift_process("
                f"every({binding_name}, name={process_name!r}), "
                f"delta_per_step={delta})"
            )
    if emitish:
        if _is_process_like(value):
            return f"    return {binding_name}"
        if _is_wave_like(value):
            return f"    return every({binding_name}, name={process_name!r})"

    raise NotImplementedError(
        f"OfflineCompiler has no pattern for process intent: {decl.intent.intent!r}"
    )


# -----------------------------------------------------------------------------
# Anthropic-backed compiler.
# -----------------------------------------------------------------------------

_COMPILER_SYSTEM_PROMPT = """\
You are the compiler for New Code, a programming language in which humans
declare intent and the compiler produces an implementation. You translate
New Code function declarations into pure Python function bodies.

You have the following primitives in scope, imported from the New Code
standard library. Use them by name, never re-import:

    W(f, A, phi, sigma)         — the waveform-number type
    w(f, A=1, phi=0, sigma=sine)— convenience constructor
    sine, sq, tri, saw          — predefined shapes
    pulse(duty)                 — variable-duty pulse
    e0                          — the unit oscillator ⟨1, 1, 0, sine⟩
    silence                     — ⟨0, 0, 0, sine⟩
    superpose(a, b)             — ⊕ : pointwise sum
    oscillate(a, b)             — ⊚ : shape product
    invert(a)                   — π phase shift
    drift(a, delta)             — ⇝ : drift toward square-wave attractor
    coherence(a, b)              — ⟪·,·⟫ : scalar correlation
    d_gamma(a, b)               — coherence distance
    collapse(a)                 — ⌊·⌉ : lossy projection to scalar
    collapse_amp(a)             — amplitude-only collapse
    collapse_freq(a)            — frequency-only collapse
    collapse_rms(a)             — RMS over one period
    fingerprint(a)              — w ⊚ e0
    every(w)                    — a process producing w at each tick
    entangle(left, right, via)  — create an Entangled pair
    pitch_follow, amplitude_mirror, phase_opposition, identity — couplings

Rules you must follow:

1. Produce ONLY the Python body of the function. Do not include the def
   line, do not include markdown fencing, do not include explanations.
2. Use four-space indentation. Every line of the body must start with at
   least four spaces.
3. The body must be pure: no I/O, no imports, no mutation of externally
   visible state, no exceptions caught silently.
4. Respect the `forbid` clauses literally. If the forbid says "do not
   modify phase", do not change the phi component.
5. Respect the `ensure` clauses: the return value must satisfy them.
6. When the intent is ambiguous, prefer the interpretation that preserves
   the most structural information. Collapse is opt-in.
7. Do not invent or import additional functions. Every call must be to a
   primitive in the scope listed above, or to the function's own arguments.
8. If you genuinely cannot produce a body that satisfies the intent, emit
   a single line: `    raise NotImplementedError("reason")` — but only as
   a last resort.

Respond with nothing but the Python body.
"""


class AnthropicCompiler:
    """Calls the Anthropic API to compile New Code declarations into Python.

    Requires the ANTHROPIC_API_KEY environment variable to be set. Uses the
    anthropic SDK if installed; falls back to urllib if not.

    If a SnapshotStore is supplied, every accepted compilation is written
    back to it under its `intent_hash`, so subsequent identical declarations
    can be replayed without an API call. Pass ``snapshot_store=None`` to
    disable caching entirely (useful when testing the live API path).
    """

    backend_name = "anthropic"

    def __init__(
        self,
        model: str = "claude-sonnet-4-5",
        max_retries: int = 2,
        snapshot_store: Optional[SnapshotStore] = None,
    ):
        self.model = model
        self.max_retries = max_retries
        self.snapshot_store = (
            snapshot_store
            if snapshot_store is not None
            else SnapshotStore()
        )
        self._client = self._make_client()

    def _make_client(self):
        try:
            import anthropic  # type: ignore
            return anthropic.Anthropic()
        except ImportError:
            return None

    def compile(self, decl: Function) -> Compiled:
        ihash = intent_hash(decl)

        # Cache hit: skip the API call entirely.
        if self.snapshot_store is not None:
            cached = self.snapshot_store.get(ihash)
            if cached is not None:
                source = cached["source"]
                prov = Provenance(
                    backend="anthropic",
                    model=cached.get("model", self.model),
                    intent_hash=ihash,
                    body_hash=cached.get("body_hash", body_hash(source)),
                    timestamp=cached.get("timestamp", _now_iso()),
                    accepted=cached.get("accepted", False),
                    notes="cache hit",
                )
                return _compile_function_body(
                    decl, source=source,
                    notes=f"cache hit ({prov.model})",
                    provenance=prov,
                )

        prompt = self._build_prompt(decl)
        source = self._request(prompt)

        # Validate the generated source.
        source = _strip_fences(source)
        err = _validate(source)
        attempts = 0
        while err and attempts < self.max_retries:
            attempts += 1
            retry_prompt = (
                prompt
                + "\n\nYour previous attempt was rejected. Reason: "
                + err
                + "\nProduce a new body that addresses this."
            )
            source = _strip_fences(self._request(retry_prompt))
            err = _validate(source)

        if err:
            raise ValueError(
                f"Compiler could not produce a valid body for {decl.name}: {err}"
            )

        if self.snapshot_store is not None:
            self.snapshot_store.put(
                ihash,
                source=source,
                model=self.model,
                decl_name=decl.name,
                accepted=False,  # awaits :accept in the REPL
            )
        prov = Provenance(
            backend="anthropic",
            model=self.model,
            intent_hash=ihash,
            body_hash=body_hash(source),
            timestamp=_now_iso(),
            accepted=False,
            notes=f"{attempts} retries",
        )
        return _compile_function_body(
            decl,
            source=source,
            notes=f"compiled by {self.model}, {attempts} retries",
            provenance=prov,
        )

    def compile_process(
        self,
        decl: ProcessDecl,
        extra_scope: Optional[Dict[str, Any]] = None,
    ) -> Compiled:
        ihash = intent_hash(decl)

        if self.snapshot_store is not None:
            cached = self.snapshot_store.get(ihash)
            if cached is not None:
                source = cached["source"]
                prov = Provenance(
                    backend="anthropic",
                    model=cached.get("model", self.model),
                    intent_hash=ihash,
                    body_hash=cached.get("body_hash", body_hash(source)),
                    timestamp=cached.get("timestamp", _now_iso()),
                    accepted=cached.get("accepted", False),
                    notes="cache hit",
                )
                return _compile_process_body(
                    decl, source=source,
                    notes=f"cache hit ({prov.model})",
                    extra_scope=extra_scope,
                    provenance=prov,
                )

        prompt = self._build_process_prompt(decl)
        source = _strip_fences(self._request(prompt))

        err = _validate(source)
        attempts = 0
        while err and attempts < self.max_retries:
            attempts += 1
            retry_prompt = (
                prompt
                + "\n\nYour previous attempt was rejected. Reason: "
                + err
                + "\nProduce a new body that returns a Process."
            )
            source = _strip_fences(self._request(retry_prompt))
            err = _validate(source)

        if err:
            raise ValueError(
                f"Compiler could not produce a valid process body for "
                f"{decl.name}: {err}"
            )

        if self.snapshot_store is not None:
            self.snapshot_store.put(
                ihash,
                source=source,
                model=self.model,
                decl_name=decl.name,
                accepted=False,
            )
        prov = Provenance(
            backend="anthropic",
            model=self.model,
            intent_hash=ihash,
            body_hash=body_hash(source),
            timestamp=_now_iso(),
            accepted=False,
            notes=f"{attempts} retries",
        )
        return _compile_process_body(
            decl,
            source=source,
            notes=f"compiled by {self.model}, {attempts} retries",
            extra_scope=extra_scope,
            provenance=prov,
        )

    def _build_prompt(self, decl: Function) -> str:
        arg_spec = ", ".join(f"{a.name} : {a.type_}" for a in decl.args)
        intent = decl.intent
        parts = [
            "Declaration to compile:",
            "",
            f"fn {decl.name}({arg_spec}) → {decl.return_type}",
        ]
        if intent.intent:
            parts.append(f"    intent: 「{intent.intent}」")
        if intent.forbid:
            parts.append(f"    forbid: 「{intent.forbid}」")
        if intent.ensure:
            parts.append(f"    ensure: 「{intent.ensure}」")
        if intent.requires:
            parts.append(f"    requires: 「{intent.requires}」")
        if intent.guard:
            parts.append(f"    guard: {intent.guard}")
        return "\n".join(parts)

    def _build_process_prompt(self, decl: ProcessDecl) -> str:
        intent = decl.intent
        parts = [
            "Process declaration to compile:",
            "",
            f"process {decl.name} : {decl.return_type}",
        ]
        if intent.intent:
            parts.append(f"    intent: 「{intent.intent}」")
        if intent.forbid:
            parts.append(f"    forbid: 「{intent.forbid}」")
        if intent.ensure:
            parts.append(f"    ensure: 「{intent.ensure}」")
        if intent.requires:
            parts.append(f"    requires: 「{intent.requires}」")
        if intent.emits:
            parts.append(f"    emits: 「{intent.emits}」")
        if intent.consumes:
            parts.append(f"    consumes: 「{intent.consumes}」")
        if intent.guard:
            parts.append(f"    guard: {intent.guard}")
        parts.extend([
            "",
            "Produce a Python body for a zero-argument function that returns a "
            "Process. Use the New Code stdlib constructors directly.",
        ])
        return "\n".join(parts)

    def _request(self, prompt: str) -> str:
        if self._client is not None:
            resp = self._client.messages.create(
                model=self.model,
                max_tokens=1024,
                system=_COMPILER_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )
            return "".join(
                block.text for block in resp.content if getattr(block, "type", "") == "text"
            )
        # Fallback: urllib.
        import json, urllib.request
        key = os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise RuntimeError(
                "AnthropicCompiler requires the anthropic package or "
                "ANTHROPIC_API_KEY; neither was available."
            )
        body = json.dumps({
            "model": self.model,
            "max_tokens": 1024,
            "system": _COMPILER_SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": prompt}],
        }).encode("utf-8")
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=body,
            headers={
                "x-api-key": key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
        )
        with urllib.request.urlopen(req) as r:
            payload = json.loads(r.read().decode("utf-8"))
        return "".join(
            block["text"] for block in payload.get("content", [])
            if block.get("type") == "text"
        )


# -----------------------------------------------------------------------------
# Snapshot compiler — replays accepted recordings without an API call.
# -----------------------------------------------------------------------------

class SnapshotCompiler:
    """A compiler backend that replays a SnapshotStore.

    On a hit, the recorded body is reused verbatim. On a miss, behaviour
    depends on ``fallback``: if a backend is supplied, the call is delegated
    and (if the snapshot store allows) the new body is recorded; if no
    fallback is supplied, ``LookupError`` is raised so the caller knows the
    snapshot needs to be recorded explicitly.

    Mode = ``snapshot`` is the default for offline test suites. It pairs
    naturally with `:accept` in the REPL: a developer compiles online once,
    accepts the result, and from then on the test suite (and CI) replays
    deterministically.
    """

    backend_name = "snapshot"

    def __init__(
        self,
        store: SnapshotStore,
        fallback: Optional[Any] = None,
        require_accepted: bool = False,
    ):
        self.store = store
        self.fallback = fallback
        self.require_accepted = require_accepted

    def _hit(self, decl: Any) -> Optional[Dict[str, Any]]:
        ihash = intent_hash(decl)
        entry = self.store.get(ihash)
        if entry is None:
            return None
        if self.require_accepted and not entry.get("accepted", False):
            return None
        return entry

    def compile(self, decl: Function) -> Compiled:
        entry = self._hit(decl)
        if entry is not None:
            source = entry["source"]
            prov = Provenance(
                backend="snapshot",
                model=entry.get("model"),
                intent_hash=intent_hash(decl),
                body_hash=entry.get("body_hash", body_hash(source)),
                timestamp=entry.get("timestamp", _now_iso()),
                accepted=entry.get("accepted", False),
                notes=f"replayed from {self.store.path.name}",
            )
            return _compile_function_body(
                decl, source=source,
                notes=f"snapshot replay ({prov.model or 'unknown'})",
                provenance=prov,
            )
        if self.fallback is None:
            raise LookupError(
                f"No snapshot for intent_hash={intent_hash(decl)} "
                f"({decl.name!r}); rerun online or supply a fallback."
            )
        compiled = self.fallback.compile(decl)
        return compiled

    def compile_process(
        self,
        decl: ProcessDecl,
        extra_scope: Optional[Dict[str, Any]] = None,
    ) -> Compiled:
        entry = self._hit(decl)
        if entry is not None:
            source = entry["source"]
            prov = Provenance(
                backend="snapshot",
                model=entry.get("model"),
                intent_hash=intent_hash(decl),
                body_hash=entry.get("body_hash", body_hash(source)),
                timestamp=entry.get("timestamp", _now_iso()),
                accepted=entry.get("accepted", False),
                notes=f"replayed from {self.store.path.name}",
            )
            return _compile_process_body(
                decl, source=source,
                notes=f"snapshot replay ({prov.model or 'unknown'})",
                extra_scope=extra_scope,
                provenance=prov,
            )
        if self.fallback is None:
            raise LookupError(
                f"No snapshot for intent_hash={intent_hash(decl)} "
                f"({decl.name!r}); rerun online or supply a fallback."
            )
        if hasattr(self.fallback, "compile_process"):
            return self.fallback.compile_process(decl, extra_scope=extra_scope)
        raise NotImplementedError("Fallback backend cannot compile processes")


def _strip_fences(source: str) -> str:
    s = source.strip()
    s = re.sub(r"^```(?:python)?\s*", "", s)
    s = re.sub(r"\s*```$", "", s)
    return s


def _validate(source: str) -> Optional[str]:
    """Return None if source is acceptable, else an error string."""
    if not source.strip():
        return "empty body"
    # Ensure every line is indented.
    lines = source.splitlines()
    for ln in lines:
        if ln.strip() and not ln.startswith(("    ", "\t")):
            return f"unindented line: {ln!r}"
    # Ensure it parses as a function body by wrapping it.
    wrapped = "def __check():\n" + source
    try:
        tree = ast.parse(wrapped)
    except SyntaxError as exc:
        return f"syntax error: {exc.msg}"
    reason = _reject_unsafe(tree)
    if reason:
        return reason
    return None


def _indented(source: str) -> str:
    return "\n".join(
        ("    " + line) if line.strip() else ""
        for line in source.splitlines()
    )


def _normalise_explicit_body(body: str) -> str:
    """Turn an explicit New Code body into an executable Python body.

    v1.0: the body is parsed by the New Code expression parser ([expr.py](expr.py))
    and lowered to Python. The result is a function-body source where every
    line is indented one level (so it can be slotted into ``def f(...):``).

    Raises ValueError on parse / transpile failure, with the original
    line/column information surfaced in the message.
    """
    raw = textwrap.dedent(body).strip("\n")
    if not raw.strip():
        raise ValueError("empty explicit body")

    try:
        ast_node = _expr.parse_expression(raw)
    except (_expr.ParseError, _expr.LexError) as exc:
        raise ValueError(f"expression parse error: {exc}") from None

    try:
        # Lower to a function-body, then strip the leading "def __body():\n"
        # to match the calling-side `def name(args): <here>` shape.
        wrapped = _expr.to_python_function("__body", [], ast_node)
    except _expr.TranspileError as exc:
        raise ValueError(f"expression lowering error: {exc}") from None

    body_lines = wrapped.splitlines()
    # Drop the def header and any leading blank lines.
    inner = body_lines[1:]
    # Body lines are already indented 4 spaces — that's what we want.
    source = "\n".join(inner).rstrip()
    if not source.strip():
        source = "    pass"

    err = _validate(source)
    if err:
        raise ValueError(f"invalid explicit body after lowering: {err}")
    return source


def _match_scope_name(intent: str, scope: Dict[str, Any]) -> Optional[str]:
    names = sorted(
        (name for name in scope if re.match(r"^[A-Za-z_]\w*$", name)),
        key=len,
        reverse=True,
    )
    for name in names:
        if re.search(rf"\b{re.escape(name.lower())}\b", intent):
            return name
    return None


def _is_wave_like(value: Any) -> bool:
    from .wave import W
    return isinstance(value, W)


def _is_process_like(value: Any) -> bool:
    from .process import Process
    return isinstance(value, Process)


def _assemble(name: str, args: list, source: str,
              extra_scope: Optional[Dict[str, Any]] = None) -> Callable:
    """Build an executable Python function from a validated body."""
    arg_list = ", ".join(args)
    src = f"def {name}({arg_list}):\n{source}\n"
    scope = _stdlib_scope()
    if extra_scope:
        for key, value in extra_scope.items():
            if key == "__builtins__":
                continue
            scope[key] = value
    exec(compile(src, f"<newcode:{name}>", "exec"), scope)
    return scope[name]


def _compile_function_body(
    decl: Function,
    source: str,
    notes: str,
    extra_scope: Optional[Dict[str, Any]] = None,
    provenance: Optional[Provenance] = None,
) -> Compiled:
    err = _validate(source)
    if err:
        raise ValueError(f"invalid body for {decl.name}: {err}")
    args = [a.name for a in decl.args]
    fn = _assemble(decl.name, args, source, extra_scope=extra_scope)
    report = build_report(decl.name, source, decl.intent, args)
    return Compiled(
        name=decl.name,
        callable_=fn,
        source=source,
        intent=decl.intent,
        notes=notes,
        report=report,
        provenance=provenance,
    )


def compile_explicit_function(
    decl: Function,
    extra_scope: Optional[Dict[str, Any]] = None,
) -> Compiled:
    source = _normalise_explicit_body(decl.body)
    prov = Provenance(
        backend="explicit",
        intent_hash=intent_hash(decl),
        body_hash=body_hash(source),
        timestamp=_now_iso(),
        accepted=True,
        notes="written by hand",
    )
    return _compile_function_body(
        decl,
        source=source,
        notes="explicit Python body",
        extra_scope=extra_scope,
        provenance=prov,
    )


def compile_explicit_process(
    decl: ProcessDecl,
    extra_scope: Optional[Dict[str, Any]] = None,
) -> Compiled:
    source = _normalise_explicit_body(decl.body)
    prov = Provenance(
        backend="explicit",
        intent_hash=intent_hash(decl),
        body_hash=body_hash(source),
        timestamp=_now_iso(),
        accepted=True,
        notes="written by hand",
    )
    return _compile_process_body(
        decl,
        source=source,
        notes="explicit Python process body",
        extra_scope=extra_scope,
        provenance=prov,
    )


def _compile_process_body(
    decl: ProcessDecl,
    source: str,
    notes: str,
    extra_scope: Optional[Dict[str, Any]] = None,
    provenance: Optional[Provenance] = None,
) -> Compiled:
    from .process import Process

    creator = _assemble(
        decl.name,
        [],
        source,
        extra_scope=extra_scope,
    )

    def wrapped() -> Process:
        value = creator()
        if not isinstance(value, Process):
            raise TypeError(
                f"process {decl.name} must return Process, got "
                f"{type(value).__name__}"
            )
        return value

    return Compiled(
        name=decl.name,
        callable_=wrapped,
        source=source,
        intent=decl.intent,
        notes=notes,
        provenance=provenance,
    )


# -----------------------------------------------------------------------------
# The front-door Compiler class.
# -----------------------------------------------------------------------------

class Compiler:
    """The front-door compiler.

    A `Compiler` carries a *mode* and a *backend*. The mode constrains what
    happens when an intent hole is encountered:

      * ``offline`` — intent holes raise :class:`OfflineHoleError`. Explicit
        bodies and pattern-matched intents still compile.
      * ``online``  — intent holes are compiled by the backend
        (Anthropic, by default). Explicit bodies still go through the
        expression parser.
      * ``snapshot`` — intent holes are looked up in a SnapshotStore and
        replayed; if no snapshot exists, behaviour depends on the backend's
        own fallback policy.

    The backend defaults to the most capable choice available given the mode
    and the environment. Pass an explicit backend to override.
    """

    def __init__(
        self,
        backend: Optional[object] = None,
        *,
        mode: Optional[str] = None,
        snapshot_store: Optional[SnapshotStore] = None,
    ):
        self.snapshot_store = snapshot_store
        self.mode = mode or self._auto_mode()
        self.backend = backend or self._auto_backend(self.mode)

    @staticmethod
    def _auto_mode() -> str:
        explicit = os.environ.get("NEWCODE_MODE")
        if explicit in (OFFLINE, ONLINE, SNAPSHOT):
            return explicit
        if os.environ.get("ANTHROPIC_API_KEY"):
            return ONLINE
        return OFFLINE

    def _auto_backend(self, mode: str):
        if mode == ONLINE:
            try:
                return AnthropicCompiler(snapshot_store=self.snapshot_store)
            except Exception:  # noqa: BLE001 — fallback is always valid
                return OfflineCompiler()
        if mode == SNAPSHOT:
            store = (
                self.snapshot_store if self.snapshot_store is not None
                else SnapshotStore()
            )
            return SnapshotCompiler(store, fallback=OfflineCompiler())
        return OfflineCompiler()

    # ------------------------------------------------------------------
    def compile(self, decl, extra_scope: Optional[Dict[str, Any]] = None) -> Compiled:
        if isinstance(decl, Function):
            if not decl.is_hole:
                return compile_explicit_function(decl, extra_scope=extra_scope)
            self._guard_hole(decl)
            return self.backend.compile(decl)
        if isinstance(decl, ProcessDecl):
            if decl.is_hole:
                self._guard_hole(decl)
                if hasattr(self.backend, "compile_process"):
                    return self.backend.compile_process(
                        decl,
                        extra_scope=extra_scope,
                    )
                raise NotImplementedError(
                    "This compiler backend does not support process compilation"
                )
            return compile_explicit_process(decl, extra_scope=extra_scope)
        raise TypeError(f"cannot compile {type(decl).__name__}")

    def _guard_hole(self, decl: Any) -> None:
        if self.mode == OFFLINE and isinstance(self.backend, OfflineCompiler):
            # OfflineCompiler can satisfy a *small* set of intents on its
            # own; we only raise if it would refuse anyway. We do this by
            # peeking at its known patterns. A simpler heuristic: if the
            # intent text doesn't match any known keyword, raise eagerly so
            # the user gets the right message instead of NotImplementedError.
            intent = (decl.intent.intent or "").lower()
            keywords = (
                "amplify", "scale the amplitude",
                "invert", "collapse", "reduce",
                "drift", "age", "coherence", "similar",
                "superpose", "sum", "mix",
                "emit", "steady", "every", "repeat",
            )
            if not any(k in intent for k in keywords):
                raise OfflineHoleError(decl.name, decl.intent.intent or "")
