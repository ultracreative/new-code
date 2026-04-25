"""
The New Code Language Server (v1.0).

A Language Server Protocol implementation for New Code scores. Speaks
JSON-RPC 2.0 over stdio — no external dependencies, stdlib only. Any LSP
client (VS Code, Neovim, Zed, Emacs) can point at it.

Run as an executable:

    python -m newcode.lsp

The server reads `Content-Length: N\\r\\n\\r\\n` framed JSON messages on
stdin and writes the same framing on stdout. Log messages go to stderr.

What v1.0 supports:

    initialize                  — handshake; advertises capabilities
    textDocument/didOpen        — pick up a document
    textDocument/didChange      — whole-document sync (no incremental)
    textDocument/didClose       — release a document
    textDocument/didSave        — re-diagnose
    textDocument/completion     — keywords, stdlib names, shapes, clauses
                                  including the new expression-layer
                                  keywords (let/in/if/then/else/match…)
                                  and `import` / `extern` / FFI accessors
    textDocument/hover          — intent-block docs, stdlib docs, expr
                                  keyword docs, host_load/host_call docs
    textDocument/documentSymbol — outline of declarations, including
                                  Import and Extern blocks

Diagnostics are published on open/change with the parser's error.

The server is non-network, synchronous, single-threaded. LSP responses
arrive in the order requests were sent.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from .parser import Parser, parse


# -----------------------------------------------------------------------------
# Stdlib vocabulary for completion + hover.
# -----------------------------------------------------------------------------
#
# Each entry is (label, detail, documentation, kind). ``kind`` matches the
# LSP CompletionItemKind enum (1=Text, 3=Function, 6=Variable, 7=Class,
# 14=Keyword, 22=Struct, 25=TypeParameter).

@dataclass
class StdlibEntry:
    label: str
    detail: str
    doc: str
    kind: int = 6  # Variable by default


_STDLIB: List[StdlibEntry] = [
    # The primitive.
    StdlibEntry("W", "class W(f, A, phi, sigma)",
                "The waveform-number type: ⟨f, A, φ, σ⟩. Four components:\n"
                "frequency, amplitude, phase, shape. The primitive of "
                "New Code.", kind=7),
    StdlibEntry("w", "w(f, A=1.0, phi=0.0, sigma=sine) → W",
                "Convenience constructor for W. Prefer this over `W(...)` "
                "in scores.", kind=3),
    StdlibEntry("Shape", "class Shape(name, kernel)",
                "A unit-periodic function σ : ℝ → [-1, 1]. Built-ins: "
                "sine, sq, tri, saw, pulse(duty).", kind=7),

    # Shapes.
    StdlibEntry("sine", "Shape", "The canonical shape. σ(t) = sin(2πt).",
                kind=22),
    StdlibEntry("sq", "Shape", "The square wave. The thermodynamic attractor: "
                "all shapes drift toward this.", kind=22),
    StdlibEntry("tri", "Shape", "The triangle wave.", kind=22),
    StdlibEntry("saw", "Shape", "The sawtooth wave.", kind=22),
    StdlibEntry("pulse", "pulse(duty: float) → Shape",
                "A variable-duty-cycle pulse.", kind=3),

    # The two identities.
    StdlibEntry("e0", "W", "The unit oscillator ⟨1, 1, 0, sine⟩. "
                "The \"1\" of New Code.", kind=6),
    StdlibEntry("silence", "W", "⟨0, 0, 0, sine⟩. The additive identity "
                "under ⊕.", kind=6),

    # Operators.
    StdlibEntry("superpose", "superpose(a: W, b: W) → W",
                "⊕ — pointwise sum of two waveforms.", kind=3),
    StdlibEntry("oscillate", "oscillate(a: W, b: W) → W",
                "⊚ — shape-composing multiplication (ring modulation).",
                kind=3),
    StdlibEntry("invert", "invert(a: W) → W",
                "⁻ — phase inversion (shifts φ by π).", kind=3),
    StdlibEntry("drift", "drift(a: W, delta: float) → W",
                "⇝ — ages a toward the square-wave attractor. The single "
                "operator that expresses decay and termination.", kind=3),

    # Correlators.
    StdlibEntry("coherence", "coherence(a: W, b: W) → float",
                "⟪·,·⟫ — shape-sensitive correlation in [-1, 1].", kind=3),
    StdlibEntry("d_gamma", "d_gamma(a: W, b: W) → float",
                "d_γ — coherence distance in [0, 1]. Non-Euclidean.",
                kind=3),

    # Collapses.
    StdlibEntry("collapse", "collapse(a: W) → float",
                "⌊·⌉ — irreversible projection to scalar. Information loss.",
                kind=3),
    StdlibEntry("collapse_amp", "collapse_amp(a: W) → float",
                "⌊·⌉_amp — amplitude-only collapse.", kind=3),
    StdlibEntry("collapse_freq", "collapse_freq(a: W) → float",
                "⌊·⌉_freq — frequency-only collapse.", kind=3),
    StdlibEntry("collapse_rms", "collapse_rms(a: W) → float",
                "⌊·⌉_rms — RMS over one period.", kind=3),

    # Diagnostics.
    StdlibEntry("fingerprint", "fingerprint(a: W) → W",
                "w ⊚ e₀ — the morphological fingerprint.", kind=3),
    StdlibEntry("identifiability_horizon",
                "identifiability_horizon(a: W) → float",
                "Smallest δ at which a becomes unrecognisable under d_γ.",
                kind=3),

    # Processes.
    StdlibEntry("Process", "class Process(name, step, ...)",
                "A named ongoing computation with its own τ.", kind=7),
    StdlibEntry("every", "every(w: W) → Process[W]",
                "A process producing w at each tick of its frequency. "
                "Does not mutate w; what changes is realise(tau). "
                "(SEMANTICS.md §3)",
                kind=3),
    StdlibEntry("on", "on(trigger, body) → Process",
                "A process that fires body when trigger is true.", kind=3),
    StdlibEntry("while_", "while_(cond, body) → Process",
                "A process that fires while cond holds.", kind=3),
    StdlibEntry("series", "series(*procs) → Process",
                "▶ — chain processes left-to-right; output of one becomes "
                "the `incoming` of the next. Samples children, never calls "
                "step() directly.", kind=3),
    StdlibEntry("parallel", "parallel(a, b) → Process",
                "∥ — two processes run independently, yielding a pair.",
                kind=3),
    StdlibEntry("feedback", "feedback(inner, delay_samples=1) → Process",
                "↺ — feed a process's delayed output back as `incoming`.",
                kind=3),
    StdlibEntry("unfold", "unfold(p: Process, n: int) → list",
                "Advance p by n ticks and collect the values. A New Code "
                "program is not run; it is unfolded.", kind=3),
    StdlibEntry("drift_process",
                "drift_process(p: Process, delta_per_step: float)",
                "A process that drifts its sampled 𝕎 by δ at each step.",
                kind=3),

    # Entanglement.
    StdlibEntry("Entangled", "class Entangled(left, right, via)",
                "A pair ⟨T ▷◁ T⟩ coupled by Φ.", kind=7),
    StdlibEntry("entangle", "entangle(left, right, via) → Entangled",
                "Declare two values entangled via a coupling function.",
                kind=3),
    StdlibEntry("pitch_follow", "pitch_follow(w: W) → W",
                "Coupling: second voice at a perfect fifth above.", kind=3),
    StdlibEntry("amplitude_mirror", "amplitude_mirror(w: W) → W",
                "Coupling: second voice mirrors amplitude.", kind=3),
    StdlibEntry("phase_opposition", "phase_opposition(w: W) → W",
                "Coupling: second voice is anti-phase.", kind=3),
    StdlibEntry("identity", "identity(x) → x",
                "Coupling: the two values are identical.", kind=3),

    # --- v1.0 additions: math constants ---
    StdlibEntry("pi", "float", "π — the circle constant.", kind=21),
    StdlibEntry("tau_const", "float", "τ — 2π, the natural circle constant.",
                kind=21),
    StdlibEntry("e_const", "float", "Euler's number.", kind=21),

    # --- v1.0 additions: math functions ---
    StdlibEntry("sqrt", "sqrt(x) → float", "Square root.", kind=3),
    StdlibEntry("exp", "exp(x) → float", "Exponential e^x.", kind=3),
    StdlibEntry("log", "log(x) → float", "Natural logarithm.", kind=3),
    StdlibEntry("sin", "sin(x) → float", "Sine.", kind=3),
    StdlibEntry("cos", "cos(x) → float", "Cosine.", kind=3),
    StdlibEntry("tan", "tan(x) → float", "Tangent.", kind=3),
    StdlibEntry("floor", "floor(x) → int", "Floor.", kind=3),
    StdlibEntry("ceil", "ceil(x) → int", "Ceiling.", kind=3),

    # --- v1.0 additions: functional helpers ---
    StdlibEntry("fold_left", "fold_left(f, init, xs)",
                "Left fold (reduce).", kind=3),
    StdlibEntry("fold_right", "fold_right(f, init, xs)",
                "Right fold.", kind=3),
    StdlibEntry("take", "take(n, xs) → list",
                "First n elements.", kind=3),
    StdlibEntry("drop", "drop(n, xs) → list",
                "All but the first n elements.", kind=3),
    StdlibEntry("compose", "compose(*fs) → fn",
                "Right-to-left composition: compose(f, g)(x) == f(g(x)).",
                kind=3),
    StdlibEntry("pipe", "pipe(*fs) → fn",
                "Left-to-right composition: pipe(f, g)(x) == g(f(x)).",
                kind=3),
    StdlibEntry("head", "head(xs)", "First element.", kind=3),
    StdlibEntry("tail", "tail(xs) → list", "All but first.", kind=3),
    StdlibEntry("last", "last(xs)", "Last element.", kind=3),
    StdlibEntry("reverse", "reverse(xs) → list", "Reversed list.", kind=3),
    StdlibEntry("unique", "unique(xs) → list",
                "Stable-order unique elements.", kind=3),
    StdlibEntry("zip_with", "zip_with(f, xs, ys) → list",
                "Pairwise apply f.", kind=3),
    StdlibEntry("flatten", "flatten(xss) → list",
                "Concatenate one level of nesting.", kind=3),

    # --- v1.0 additions: string / IO ---
    StdlibEntry("fmt", "fmt(template, **kwargs) → str",
                "String.format-style templating.", kind=3),
    StdlibEntry("show", "show(x) → str",
                "Default printable form (special-cases 𝕎).", kind=3),
    StdlibEntry("print", "print(*args, sep=' ', end='\\n')",
                "Captured print. Echoes to stdout and to a buffer the "
                "REPL/tests can read.", kind=3),
    StdlibEntry("io_buffer", "io_buffer() → list[str]",
                "Snapshot of the captured IO buffer.", kind=3),
    StdlibEntry("io_clear", "io_clear() → None",
                "Empty the captured IO buffer.", kind=3),

    # --- v1.0 additions: type helpers ---
    StdlibEntry("conforms", "conforms(value, type_text: str) → bool",
                "Best-effort surface conformance check used by ensure clauses.",
                kind=3),

    # --- v1.0 additions: FFI / host bridge ---
    StdlibEntry("host_load", "host_load(name: str) → Any",
                "Import a host (Python) module by dotted name. The typed "
                "FFI surface that `import host.<name>` lowers to.", kind=3),
    StdlibEntry("host_call", "host_call(name: str, *args, **kwargs)",
                "Resolve a dotted host name to a callable and invoke it.",
                kind=3),
]

_STDLIB_INDEX: Dict[str, StdlibEntry] = {e.label: e for e in _STDLIB}


# -----------------------------------------------------------------------------
# Keyword / clause vocabulary.
# -----------------------------------------------------------------------------

_DECL_KEYWORDS: List[Tuple[str, str]] = [
    ("fn", "Declare a function. Header → intent/forbid/ensure → ≔ ??"),
    ("let", "Bind a name to an expression."),
    ("process", "Declare an ongoing process with its own τ."),
    ("module", "Open a named namespace."),
    ("import", "`import path.to.module` or `import host.numpy as np`. "
               "Resolves through the typed HostBridge."),
    ("extern", "`extern python { ... }` — top-level escape hatch. The "
               "block runs once when the score loads; its top-level names "
               "are bound in the loading scope."),
]

_CLAUSE_KEYWORDS: List[Tuple[str, str]] = [
    ("intent", "What the function should do. The conductor bringing the "
               "orchestra in. Part of the cache key — change it and the "
               "snapshot misses."),
    ("forbid", "What the function must not do. The cut-off."),
    ("ensure", "What must be true at the end. The sustain."),
    ("requires", "Input pre-conditions (optional)."),
    ("emits", "What this declaration emits (optional)."),
    ("consumes", "What this declaration consumes (optional)."),
    ("guard", "A runtime guard expression (optional)."),
]

# Expression-layer keywords (introduced in v1.0).
_EXPR_KEYWORDS: List[Tuple[str, str]] = [
    ("in",     "`let x = e in body` — the body of a let-binding."),
    ("if",     "`if cond then a else b` — conditional expression."),
    ("then",   "Then-branch of an `if` expression."),
    ("else",   "Else-branch of an `if` expression."),
    ("and",    "Logical AND."),
    ("or",     "Logical OR."),
    ("not",    "Logical NOT."),
    ("match",  "`match x with pattern -> result | …`"),
    ("with",   "Pattern match clause separator."),
    ("do",     "Block-do form (paired with `end`)."),
    ("end",    "Closes a `do … end` block."),
    ("python", "Inside `python { … }` — the explicit Python escape hatch. "
               "The forbidden-name list still applies."),
    ("as",     "Used in `import path as alias`."),
    ("true",   "Boolean literal."),
    ("false",  "Boolean literal."),
]

_TYPE_ATOMS: List[Tuple[str, str]] = [
    ("𝕎", "The waveform-number type ⟨f, A, φ, σ⟩."),
    ("ℝ", "Real numbers."),
    ("ℕ", "Natural numbers."),
    ("ℤ", "Integers."),
    ("𝔹", "Booleans."),
    ("Bool", "Booleans (ASCII alias for 𝔹)."),
    ("Int",  "Integers (ASCII alias for ℤ)."),
    ("Float","Floats (ASCII alias for ℝ)."),
    ("Str",  "Strings."),
    ("Unit", "The unit type — a function that returns nothing meaningful."),
]


# -----------------------------------------------------------------------------
# Document model.
# -----------------------------------------------------------------------------

@dataclass
class Document:
    uri: str
    text: str
    version: int = 0
    diagnostics: List[Dict[str, Any]] = field(default_factory=list)

    def line(self, i: int) -> str:
        lines = self.text.splitlines()
        return lines[i] if 0 <= i < len(lines) else ""


# -----------------------------------------------------------------------------
# LSP protocol plumbing.
# -----------------------------------------------------------------------------

def _read_message(stream) -> Optional[Dict[str, Any]]:
    """Read one LSP message off ``stream`` (a binary stdin).

    Returns ``None`` on clean EOF. Raises on malformed framing.
    """
    headers: Dict[str, str] = {}
    while True:
        line = stream.readline()
        if not line:
            return None
        line = line.decode("ascii", errors="strict")
        if line in ("\r\n", "\n"):
            break
        if ":" in line:
            k, _, v = line.partition(":")
            headers[k.strip().lower()] = v.strip()
    length = int(headers.get("content-length", "0"))
    if length <= 0:
        return None
    body = stream.read(length)
    if len(body) < length:
        return None
    return json.loads(body.decode("utf-8"))


def _write_message(stream, payload: Dict[str, Any]) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
    stream.write(header)
    stream.write(body)
    stream.flush()


# -----------------------------------------------------------------------------
# Position helpers.
# -----------------------------------------------------------------------------

def _offset_to_position(text: str, offset: int) -> Dict[str, int]:
    line = 0
    col = 0
    for i, ch in enumerate(text):
        if i == offset:
            break
        if ch == "\n":
            line += 1
            col = 0
        else:
            col += 1
    return {"line": line, "character": col}


def _range_for_line(line: int, start: int, end: int) -> Dict[str, Any]:
    return {
        "start": {"line": line, "character": start},
        "end":   {"line": line, "character": end},
    }


_WORD_RE = re.compile(r"[A-Za-z_𝕎ℝℕℤ𝔹][A-Za-z0-9_]*")


def _word_at(line_text: str, character: int) -> Tuple[str, int, int]:
    """Return (word, start_col, end_col) for the identifier straddling
    ``character`` in ``line_text``. Empty word if no identifier."""
    if character > len(line_text):
        character = len(line_text)
    start = character
    while start > 0 and _WORD_RE.match(line_text[start - 1]):
        start -= 1
    end = character
    while end < len(line_text) and _WORD_RE.match(line_text[end]):
        end += 1
    return line_text[start:end], start, end


# -----------------------------------------------------------------------------
# The server.
# -----------------------------------------------------------------------------

class LanguageServer:

    def __init__(self, stdin=None, stdout=None, log=None):
        self.stdin = stdin or sys.stdin.buffer
        self.stdout = stdout or sys.stdout.buffer
        self.log = log or sys.stderr
        self.docs: Dict[str, Document] = {}
        self.shutdown_requested = False
        self._handlers: Dict[str, Callable] = {
            "initialize":                  self._on_initialize,
            "initialized":                 self._on_initialized,
            "shutdown":                    self._on_shutdown,
            "exit":                        self._on_exit,
            "textDocument/didOpen":        self._on_did_open,
            "textDocument/didChange":      self._on_did_change,
            "textDocument/didSave":        self._on_did_save,
            "textDocument/didClose":       self._on_did_close,
            "textDocument/completion":     self._on_completion,
            "textDocument/hover":          self._on_hover,
            "textDocument/documentSymbol": self._on_document_symbol,
        }

    # -- loop -------------------------------------------------------------

    def serve(self) -> int:
        while True:
            try:
                msg = _read_message(self.stdin)
            except Exception as exc:  # noqa: BLE001
                self._log(f"read error: {exc}")
                return 1
            if msg is None:
                return 0
            self._dispatch(msg)
            if self.shutdown_requested and msg.get("method") == "exit":
                return 0

    def _dispatch(self, msg: Dict[str, Any]) -> None:
        method = msg.get("method")
        handler = self._handlers.get(method)
        if handler is None:
            if "id" in msg:
                self._respond_error(msg["id"], -32601,
                                    f"method not found: {method}")
            return
        try:
            result = handler(msg)
        except Exception as exc:  # noqa: BLE001
            self._log(f"handler error in {method}: {exc}")
            if "id" in msg:
                self._respond_error(msg["id"], -32603, f"internal error: {exc}")
            return
        if "id" in msg:
            self._respond_result(msg["id"], result)

    def _respond_result(self, id_: Any, result: Any) -> None:
        _write_message(self.stdout, {
            "jsonrpc": "2.0", "id": id_, "result": result,
        })

    def _respond_error(self, id_: Any, code: int, message: str) -> None:
        _write_message(self.stdout, {
            "jsonrpc": "2.0", "id": id_,
            "error": {"code": code, "message": message},
        })

    def _notify(self, method: str, params: Dict[str, Any]) -> None:
        _write_message(self.stdout, {
            "jsonrpc": "2.0", "method": method, "params": params,
        })

    def _log(self, text: str) -> None:
        try:
            self.log.write("[newcode-lsp] " + text + "\n")
            self.log.flush()
        except Exception:  # noqa: BLE001
            pass

    # -- lifecycle --------------------------------------------------------

    def _on_initialize(self, msg: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "capabilities": {
                "textDocumentSync": {
                    "openClose": True,
                    "change": 1,       # full sync
                    "save": {"includeText": False},
                },
                "completionProvider": {
                    "triggerCharacters": [":", " ", "「", ".", "\\"],
                    "resolveProvider": False,
                },
                "hoverProvider": True,
                "documentSymbolProvider": True,
            },
            "serverInfo": {"name": "newcode-lsp", "version": "1.0.0"},
        }

    def _on_initialized(self, msg: Dict[str, Any]) -> None:
        self._log("initialized (v1.0)")
        return None

    def _on_shutdown(self, msg: Dict[str, Any]) -> Any:
        self.shutdown_requested = True
        return None

    def _on_exit(self, msg: Dict[str, Any]) -> None:
        return None

    # -- text sync --------------------------------------------------------

    def _on_did_open(self, msg: Dict[str, Any]) -> None:
        td = msg["params"]["textDocument"]
        doc = Document(uri=td["uri"], text=td["text"], version=td.get("version", 0))
        self.docs[doc.uri] = doc
        self._diagnose(doc)
        return None

    def _on_did_change(self, msg: Dict[str, Any]) -> None:
        uri = msg["params"]["textDocument"]["uri"]
        version = msg["params"]["textDocument"].get("version", 0)
        changes = msg["params"].get("contentChanges") or []
        doc = self.docs.get(uri)
        if doc is None:
            return None
        # Full-document sync: take the whole text from the last change.
        if changes:
            doc.text = changes[-1]["text"]
        doc.version = version
        self._diagnose(doc)
        return None

    def _on_did_save(self, msg: Dict[str, Any]) -> None:
        uri = msg["params"]["textDocument"]["uri"]
        doc = self.docs.get(uri)
        if doc is not None:
            self._diagnose(doc)
        return None

    def _on_did_close(self, msg: Dict[str, Any]) -> None:
        uri = msg["params"]["textDocument"]["uri"]
        self.docs.pop(uri, None)
        # Clear diagnostics on close.
        self._notify("textDocument/publishDiagnostics",
                     {"uri": uri, "diagnostics": []})
        return None

    # -- diagnostics ------------------------------------------------------

    def _diagnose(self, doc: Document) -> None:
        diagnostics: List[Dict[str, Any]] = []
        try:
            decls = parse(doc.text)
        except Exception as exc:  # noqa: BLE001
            line = self._guess_error_line(str(exc), doc.text)
            diagnostics.append({
                "range": _range_for_line(line, 0,
                                         len(doc.line(line)) or 1),
                "severity": 1,   # Error
                "source": "newcode",
                "message": str(exc),
            })
            doc.diagnostics = diagnostics
            self._notify("textDocument/publishDiagnostics",
                         {"uri": doc.uri, "diagnostics": diagnostics})
            return

        # Mode-aware hints: surface intent holes with no offline match as
        # informational diagnostics. Real failure happens at compile time;
        # this is just a heads-up in the editor.
        try:
            from .compiler import OfflineCompiler  # local import — keep LSP fast
            offline = OfflineCompiler()
            for decl in decls:
                if getattr(decl, "is_hole", False):
                    intent_text = (getattr(decl.intent, "intent", "") or "").lower()
                    if not self._offline_can_resolve(offline, intent_text):
                        line = self._find_hole_line(doc.text, decl.name)
                        diagnostics.append({
                            "range": _range_for_line(
                                line, 0, len(doc.line(line)) or 1),
                            "severity": 3,   # Information
                            "source": "newcode",
                            "message": (
                                f"intent hole `{decl.name}`: no offline "
                                "pattern matches this intent. Run --online "
                                "to let the compiler fill it, or write the "
                                "body explicitly."
                            ),
                        })
        except Exception:  # noqa: BLE001
            # Compiler import or pattern lookup failed — diagnostics are
            # best-effort, never fatal.
            pass

        doc.diagnostics = diagnostics
        self._notify("textDocument/publishDiagnostics",
                     {"uri": doc.uri, "diagnostics": diagnostics})

    # Mirror of the keyword set baked into OfflineCompiler.compile. Kept
    # in sync by hand — when the offline pattern table grows, add here
    # too. Used only for LSP info diagnostics; never authoritative.
    _OFFLINE_KEYWORDS = (
        "amplify", "scale the amplitude",
        "invert", "phase",
        "collapse", "reduce", "scalar",
        "drift", "age",
        "coherence", "similar",
        "superpose", "sum", "mix",
    )

    def _offline_can_resolve(self, offline_compiler, intent_text: str) -> bool:
        """Best-effort check that the offline backend has a pattern for
        this intent text. Returns True if uncertain (we don't squiggle
        what we can't verify)."""
        if not intent_text:
            return True
        # Prefer compiler introspection if it ever exposes a `patterns`
        # attribute; otherwise fall back to the mirrored keyword list.
        patterns = getattr(offline_compiler, "patterns", None)
        if patterns:
            keywords = [kw.lower() for kw in patterns]
        else:
            keywords = list(self._OFFLINE_KEYWORDS)
        for kw in keywords:
            if kw in intent_text:
                return True
        return False

    def _find_hole_line(self, text: str, name: str) -> int:
        for i, line in enumerate(text.splitlines()):
            if name in line and re.search(rf"\b{re.escape(name)}\b", line):
                return i
        return 0

    def _guess_error_line(self, msg: str, text: str) -> int:
        m = re.search(r"line (\d+)", msg)
        if m:
            return max(0, int(m.group(1)) - 1)
        return 0

    # -- completion -------------------------------------------------------

    def _on_completion(self, msg: Dict[str, Any]) -> Dict[str, Any]:
        uri = msg["params"]["textDocument"]["uri"]
        pos = msg["params"]["position"]
        doc = self.docs.get(uri)
        items: List[Dict[str, Any]] = []
        if doc is None:
            return {"isIncomplete": False, "items": items}

        line_text = doc.line(pos["line"])
        prefix = line_text[:pos["character"]]
        stripped = prefix.lstrip()
        indent = len(prefix) - len(stripped)

        # At line start (no indent), suggest declaration keywords.
        at_line_start = (
            (indent == 0 and not stripped)
            or (indent == 0 and not re.search(r"\s", stripped))
        )
        if at_line_start:
            for kw, doc_ in _DECL_KEYWORDS:
                items.append(self._completion_item(
                    kw, kw, doc_, kind=14))
            # Useful snippets.
            items.append(self._completion_item(
                "fn (snippet)",
                "fn ${1:name} (${2:arg} : ${3:𝕎}) → ${4:𝕎}\n"
                "    intent: 「${5:...}」\n"
                "    forbid: 「${6:...}」\n"
                "    ensure: 「${7:...}」\n"
                "    ≔ ??",
                "Create a new intent-blocked function.",
                kind=15,   # Snippet
                insert_text_format=2,
            ))
            items.append(self._completion_item(
                "import host (snippet)",
                "import host.${1:numpy} as ${2:np}",
                "Import a Python library through the typed HostBridge.",
                kind=15, insert_text_format=2,
            ))
            items.append(self._completion_item(
                "extern python (snippet)",
                "extern python {\n    ${1:# ...}\n}",
                "Top-level escape hatch. The block runs once at load time; "
                "its top-level names are bound in the loading scope.",
                kind=15, insert_text_format=2,
            ))
            items.append(self._completion_item(
                "let (snippet)",
                "let ${1:name} = ${2:expression}",
                "Bind a name.",
                kind=15, insert_text_format=2,
            ))
            return {"isIncomplete": False, "items": items}

        # Indented line: suggest clause keywords + stdlib + expr keywords.
        if indent > 0 and (not stripped or re.match(r"[A-Za-z_]", stripped)):
            for kw, doc_ in _CLAUSE_KEYWORDS:
                items.append(self._completion_item(
                    kw, kw + ": 「", doc_, kind=14))
            for kw, doc_ in _EXPR_KEYWORDS:
                items.append(self._completion_item(
                    kw, kw, doc_, kind=14))

        # Always offer stdlib names.
        for entry in _STDLIB:
            items.append(self._completion_item(
                entry.label, entry.label,
                f"**{entry.detail}**\n\n{entry.doc}",
                kind=entry.kind,
            ))
        # And type atoms.
        for atom, doc_ in _TYPE_ATOMS:
            items.append(self._completion_item(
                atom, atom, doc_, kind=25))   # TypeParameter
        return {"isIncomplete": False, "items": items}

    def _completion_item(self, label: str, insert_text: str, doc: str,
                         kind: int = 6,
                         insert_text_format: int = 1) -> Dict[str, Any]:
        return {
            "label": label,
            "kind": kind,
            "insertText": insert_text,
            "insertTextFormat": insert_text_format,
            "documentation": {"kind": "markdown", "value": doc},
        }

    # -- hover ------------------------------------------------------------

    def _on_hover(self, msg: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        uri = msg["params"]["textDocument"]["uri"]
        pos = msg["params"]["position"]
        doc = self.docs.get(uri)
        if doc is None:
            return None
        line_text = doc.line(pos["line"])
        word, start, end = _word_at(line_text, pos["character"])
        if not word:
            return None

        # First: a stdlib entry?
        entry = _STDLIB_INDEX.get(word)
        if entry is not None:
            return {
                "contents": {
                    "kind": "markdown",
                    "value": f"**`{entry.label}`** — *{entry.detail}*\n\n{entry.doc}",
                },
                "range": _range_for_line(pos["line"], start, end),
            }

        # Second: a declared function or let in this doc?
        decl_hover = self._hover_for_declaration(doc, word)
        if decl_hover is not None:
            return {
                "contents": {"kind": "markdown", "value": decl_hover},
                "range": _range_for_line(pos["line"], start, end),
            }

        # Third: a known clause / decl / expr keyword?
        for kw, kdoc in _CLAUSE_KEYWORDS + _DECL_KEYWORDS + _EXPR_KEYWORDS:
            if kw == word:
                return {
                    "contents": {"kind": "markdown",
                                 "value": f"**`{kw}`** — {kdoc}"},
                    "range": _range_for_line(pos["line"], start, end),
                }

        # Fourth: type atom?
        for atom, adoc in _TYPE_ATOMS:
            if atom == word:
                return {
                    "contents": {"kind": "markdown",
                                 "value": f"**`{atom}`** — {adoc}"},
                    "range": _range_for_line(pos["line"], start, end),
                }

        return None

    def _hover_for_declaration(self, doc: Document, name: str) -> Optional[str]:
        try:
            decls = parse(doc.text)
        except Exception:
            return None
        for decl in self._walk_decls(decls):
            if getattr(decl, "name", None) != name:
                continue
            cls = decl.__class__.__name__
            kind_word = {
                "Function": "fn", "Process": "process", "Let": "let",
                "Module": "module", "Import": "import", "Extern": "extern",
            }.get(cls, cls.lower())
            lines = [f"**`{kind_word} {name}`**"]
            intent = getattr(decl, "intent", None)
            if intent is not None:
                for field_name in ("intent", "forbid", "ensure",
                                   "requires", "emits", "consumes", "guard"):
                    val = getattr(intent, field_name, "")
                    if val:
                        lines.append(f"- *{field_name}*: 「{val}」")
            body = getattr(decl, "body", None)
            if body == "??":
                lines.append("- *body*: `??` (compiler-filled)")
            elif body:
                lines.append("- *body*: (explicit)")
            return "\n".join(lines)
        return None

    def _walk_decls(self, decls):
        """Yield top-level decls and any decls nested inside modules."""
        for decl in decls:
            yield decl
            sub = getattr(decl, "declarations", None)
            if sub:
                for inner in self._walk_decls(sub):
                    yield inner

    # -- document symbols --------------------------------------------------

    def _on_document_symbol(self, msg: Dict[str, Any]) -> List[Dict[str, Any]]:
        uri = msg["params"]["textDocument"]["uri"]
        doc = self.docs.get(uri)
        if doc is None:
            return []
        symbols: List[Dict[str, Any]] = []
        try:
            decls = parse(doc.text)
        except Exception:
            return []

        lines = doc.text.splitlines()

        def find_header(kind: str, name: str, search_from: int = 0) -> int:
            pat = re.compile(rf"^\s*{re.escape(kind)}\s+{re.escape(name)}\b")
            for i in range(search_from, len(lines)):
                if pat.match(lines[i]):
                    return i
            return 0

        def find_simple(kind: str, search_from: int = 0) -> int:
            pat = re.compile(rf"^\s*{re.escape(kind)}\b")
            for i in range(search_from, len(lines)):
                if pat.match(lines[i]):
                    return i
            return 0

        cursor = 0
        kind_map = {
            "Function": ("fn",      12),   # SymbolKind.Function
            "Process":  ("process", 14),   # SymbolKind.Event
            "Let":      ("let",     13),   # SymbolKind.Variable / Constant
            "Module":   ("module",  2),    # SymbolKind.Module
            "Import":   ("import",  3),    # SymbolKind.Namespace
            "Extern":   ("extern",  4),    # SymbolKind.Package
        }
        for decl in decls:
            cls = decl.__class__.__name__
            if cls not in kind_map:
                continue
            kw, sym_kind = kind_map[cls]
            # Imports and externs don't carry a `name` like the others.
            if cls == "Import":
                line = find_simple(kw, cursor)
                length = len(lines[line]) if 0 <= line < len(lines) else 0
                label = decl.alias or decl.path
                symbols.append({
                    "name": f"import {decl.path}" + (
                        f" as {decl.alias}" if decl.alias else ""),
                    "kind": sym_kind,
                    "range": _range_for_line(line, 0, length),
                    "selectionRange": _range_for_line(line, 0, length),
                })
            elif cls == "Extern":
                line = find_simple(kw, cursor)
                length = len(lines[line]) if 0 <= line < len(lines) else 0
                symbols.append({
                    "name": f"extern {decl.language}",
                    "kind": sym_kind,
                    "range": _range_for_line(line, 0, length),
                    "selectionRange": _range_for_line(line, 0, length),
                })
            else:
                name = getattr(decl, "name", None)
                if name is None:
                    continue
                line = find_header(kw, name, cursor)
                length = len(lines[line]) if 0 <= line < len(lines) else 0
                symbols.append({
                    "name": name,
                    "kind": sym_kind,
                    "range": _range_for_line(line, 0, length),
                    "selectionRange": _range_for_line(line, 0, length),
                })
            cursor = max(cursor, line + 1)
        return symbols


# -----------------------------------------------------------------------------
# Entry point.
# -----------------------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> int:
    server = LanguageServer()
    server._log("newcode-lsp v1.0 starting")
    return server.serve()


if __name__ == "__main__":
    sys.exit(main())
