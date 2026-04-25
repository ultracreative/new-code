"""
The New Code REPL.

Read a .nc source file, parse it, compile every declaration that has a
hole, execute any `let` bindings at the top level, and drop into an
interactive prompt where the user can call compiled functions, inspect
values, and watch processes unfold.

Usage:
    python -m newcode.repl              # start empty
    python -m newcode.repl file.nc      # load a source file, then prompt

The REPL is minimal. It does not try to be IPython. It evaluates Python
expressions in a scope that has the New Code stdlib and all compiled
declarations bound by name. The point is to make the language usable
end-to-end, not to be pretty.
"""

from __future__ import annotations

import sys
import traceback
from typing import Any, Dict, List, Optional

from . import (
    W, w, sine, sq, tri, saw, pulse, e0, silence,
    superpose, oscillate, invert, drift,
    coherence, d_gamma, collapse, collapse_amp, collapse_freq, collapse_rms,
    fingerprint, identifiability_horizon,
    Process, every, on, while_, series, parallel, feedback, unfold, drift_process,
    Entangled, entangle, pitch_follow, amplitude_mirror, phase_opposition, identity,
    parse, Compiler,
    start_debugger, shared_tracer,
)
from . import expr as _expr
from . import stdlib as _stdlib
from .compiler import (
    OfflineHoleError, SnapshotStore, intent_hash,
    OFFLINE, ONLINE, SNAPSHOT,
)
from .parser import Function, Let, Module, Process as ProcessDecl


BANNER = """\
New Code v1.0 — a machine-native language for human-AI collaboration.
Mode: {mode}.  Type :help for commands, :quit to exit.
"""

HELP = """\
Commands (all prefixed with ':'):
    :help              show this help
    :quit              exit the REPL
    :load <path>       load a .nc source file
    :scope             list bound names
    :src <name>        show the compiled source of a declaration
    :intent <name>     show the intent block of a declaration
    :explain <name>    show compiler notes and any checked constraints
    :provenance <name> show how a compiled body was produced
    :accept <name>     mark a generated body as accepted (persists to snapshot)
    :reject <name>     remove a body from the snapshot store
    :unfold <proc> <n> advance a process n ticks and show the outputs
    :debug [port]      open the visual debugger in a browser; tracks every
                       Process and Entangled currently in scope
    :mode [m]          show or switch compiler mode (offline | online | snapshot)
    :clear             reset the scope to a fresh stdlib

Anything else is evaluated as a New Code expression first; if that doesn't
parse, it falls back to Python. The full New Code stdlib is in scope along
with every declaration loaded from .nc files.
"""


def _fresh_scope() -> Dict[str, Any]:
    """A clean compile/eval scope, populated from the New Code stdlib."""
    return _stdlib.build_scope()


_UNRESOLVED = object()


class REPL:
    def __init__(
        self,
        mode: Optional[str] = None,
        snapshot_store: Optional[SnapshotStore] = None,
    ):
        self.scope: Dict[str, Any] = _fresh_scope()
        self.compiled_meta: Dict[str, Any] = {}
        # Use `is None` (not `or`) so a freshly-created empty SnapshotStore
        # — which is falsy via __len__ — is preserved.
        self.snapshot_store = (
            snapshot_store if snapshot_store is not None else SnapshotStore()
        )
        self.compiler = Compiler(
            mode=mode,
            snapshot_store=self.snapshot_store,
        )
        self.mode = self.compiler.mode

    # -------------------------------------------------------------------
    # Loading source files.
    # -------------------------------------------------------------------

    def load_file(self, path: str) -> None:
        with open(path, "r", encoding="utf-8") as f:
            source = f.read()
        self.load_source(source, origin=path)

    def load_source(self, source: str, origin: str = "<string>") -> None:
        try:
            decls = parse(source)
        except Exception as exc:  # noqa: BLE001
            print(f"parse error in {origin}: {exc}")
            return

        for decl in decls:
            self._install(decl)

    def _install(self, decl: Any) -> None:
        if isinstance(decl, Function):
            try:
                compiled = self.compiler.compile(decl, extra_scope=self.scope)
            except OfflineHoleError as exc:
                print(f"  ⚠ {exc}")
                return
            except Exception as exc:  # noqa: BLE001
                print(f"compile error for {decl.name}: {exc}")
                return
            self.scope[decl.name] = compiled
            self.compiled_meta[decl.name] = compiled
            print(f"  compiled: {decl.name}  ({compiled.notes})")
        elif isinstance(decl, ProcessDecl):
            try:
                compiled = self.compiler.compile(decl, extra_scope=self.scope)
                proc = compiled()
            except OfflineHoleError as exc:
                print(f"  ⚠ {exc}")
                return
            except Exception as exc:  # noqa: BLE001
                print(f"compile error for process {decl.name}: {exc}")
                return
            self.scope[decl.name] = proc
            self.compiled_meta[decl.name] = compiled
            print(f"  process {decl.name} = {proc!r}  ({compiled.notes})")
        elif isinstance(decl, Let):
            val = self._eval_expression(decl.expression, label=f"let {decl.name}")
            if val is _UNRESOLVED:
                return
            self.scope[decl.name] = val
            print(f"  let {decl.name} = {val!r}")
        elif isinstance(decl, Module):
            # A module is a namespace holder; we install its declarations
            # into the top-level scope.
            print(f"  module {decl.name}")
            for inner in decl.declarations:
                self._install(inner)
        else:
            print(f"  unknown declaration: {decl}")

    def _eval_expression(self, source: str, label: str = "expression") -> Any:
        """Evaluate a New Code expression. Falls back to Python on parse error.

        The fallback exists so the REPL stays usable while the expression
        grammar is still growing — but every successful native parse is the
        preferred path, so we try that first and only swallow ParseError /
        LexError to fall through to Python.
        """
        try:
            return _expr.evaluate_source(source, self.scope)
        except (_expr.ParseError, _expr.LexError):
            pass  # fall through to Python
        except Exception as exc:  # noqa: BLE001
            print(f"  {label} failed (newcode expr): {exc}")
            return _UNRESOLVED
        try:
            return eval(source, self.scope)
        except SyntaxError:
            try:
                exec(source, self.scope)
                return None
            except Exception as exc:  # noqa: BLE001
                print(f"  {label} failed (python fallback): {exc}")
                return _UNRESOLVED
        except Exception as exc:  # noqa: BLE001
            print(f"  {label} failed (python fallback): {exc}")
            return _UNRESOLVED

    # -------------------------------------------------------------------
    # Interactive loop.
    # -------------------------------------------------------------------

    def run(self) -> None:
        print(BANNER.format(mode=self.mode))
        while True:
            try:
                line = input("nc> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                return
            if not line:
                continue
            if line.startswith(":"):
                if self._handle_command(line):
                    return
                continue
            self._evaluate(line)

    def _handle_command(self, line: str) -> bool:
        """Returns True if the REPL should exit."""
        parts = line.split(maxsplit=2)
        cmd = parts[0]
        if cmd in (":quit", ":q", ":exit"):
            return True
        if cmd == ":help":
            print(HELP)
        elif cmd == ":load":
            if len(parts) < 2:
                print("usage: :load <path>")
            else:
                self.load_file(parts[1])
        elif cmd == ":scope":
            user_names = [n for n in self.scope if not n.startswith("_")
                          and n not in _fresh_scope()]
            if not user_names:
                print("(no user-defined bindings)")
            for n in sorted(user_names):
                v = self.scope[n]
                print(f"  {n}  = {v!r}")
        elif cmd == ":src":
            if len(parts) < 2:
                print("usage: :src <name>")
            elif parts[1] not in self.compiled_meta:
                print(f"no compiled source for {parts[1]!r}")
            else:
                print(self.compiled_meta[parts[1]].source)
        elif cmd == ":intent":
            if len(parts) < 2:
                print("usage: :intent <name>")
            elif parts[1] not in self.compiled_meta:
                print(f"no intent block known for {parts[1]!r}")
            else:
                intent = self.compiled_meta[parts[1]].intent
                if intent.intent:
                    print(f"  intent: 「{intent.intent}」")
                if intent.forbid:
                    print(f"  forbid: 「{intent.forbid}」")
                if intent.ensure:
                    print(f"  ensure: 「{intent.ensure}」")
        elif cmd == ":explain":
            if len(parts) < 2:
                print("usage: :explain <name>")
            elif parts[1] not in self.compiled_meta:
                print(f"no compiled declaration known for {parts[1]!r}")
            else:
                compiled = self.compiled_meta[parts[1]]
                print(f"  {compiled.name}: {compiled.notes}")
                if compiled.report is not None:
                    print(compiled.report)
                else:
                    print("  (no constraint report available)")
        elif cmd == ":unfold":
            if len(parts) < 3:
                print("usage: :unfold <proc_name> <n>")
            else:
                name = parts[1]
                try:
                    n = int(parts[2])
                except ValueError:
                    print("n must be an integer")
                    return False
                if name not in self.scope:
                    print(f"no such binding: {name}")
                    return False
                p = self.scope[name]
                if not isinstance(p, Process):
                    print(f"{name} is not a process")
                    return False
                values = unfold(p, n)
                for i, v in enumerate(values):
                    print(f"  [{i}] {v!r}")
        elif cmd == ":debug":
            port = 0
            if len(parts) >= 2:
                try:
                    port = int(parts[1])
                except ValueError:
                    print("usage: :debug [port]")
                    return False
            server = start_debugger(self.scope, port=port, open_browser=True)
            tracer = shared_tracer()
            added = tracer.track_scope(self.scope)
            print(f"debugger at {server.url}  "
                  f"(tracking {len(tracer.processes)} process(es), "
                  f"{len(tracer.entangled)} entangled pair(s); "
                  f"+{added} new this call)")
        elif cmd == ":clear":
            self.scope = _fresh_scope()
            self.compiled_meta.clear()
            print("scope cleared.")
        elif cmd == ":provenance":
            self._cmd_provenance(parts)
        elif cmd == ":accept":
            self._cmd_accept(parts)
        elif cmd == ":reject":
            self._cmd_reject(parts)
        elif cmd == ":mode":
            self._cmd_mode(parts)
        else:
            print(f"unknown command: {cmd}  (try :help)")
        return False

    # ------------------------------------------------------------------
    # Approval workflow.
    # ------------------------------------------------------------------

    def _cmd_provenance(self, parts: List[str]) -> None:
        if len(parts) < 2:
            print("usage: :provenance <name>")
            return
        name = parts[1]
        compiled = self.compiled_meta.get(name)
        if compiled is None:
            print(f"no compiled declaration known for {name!r}")
            return
        prov = compiled.provenance
        if prov is None:
            print(f"  {name}: no provenance recorded.")
            return
        print(f"  {name}:")
        print(f"    backend     : {prov.backend}")
        if prov.model:
            print(f"    model       : {prov.model}")
        print(f"    intent_hash : {prov.intent_hash}")
        print(f"    body_hash   : {prov.body_hash}")
        print(f"    timestamp   : {prov.timestamp}")
        print(f"    accepted    : {prov.accepted}")
        if prov.notes:
            print(f"    notes       : {prov.notes}")

    def _cmd_accept(self, parts: List[str]) -> None:
        if len(parts) < 2:
            print("usage: :accept <name>")
            return
        name = parts[1]
        compiled = self.compiled_meta.get(name)
        if compiled is None or compiled.provenance is None:
            print(f"no compiled declaration with provenance for {name!r}")
            return
        prov = compiled.provenance
        if prov.backend == "explicit":
            print(f"  {name} is an explicit body; nothing to accept.")
            return
        # Ensure the snapshot store has the entry, then mark accepted.
        if prov.intent_hash not in self.snapshot_store:
            self.snapshot_store.put(
                prov.intent_hash,
                source=compiled.source,
                model=prov.model or prov.backend,
                decl_name=name,
                accepted=True,
            )
        else:
            self.snapshot_store.mark_accepted(prov.intent_hash, True)
        prov.accepted = True
        print(f"  ✓ {name} accepted "
              f"(intent_hash={prov.intent_hash}, "
              f"snapshot={self.snapshot_store.path})")

    def _cmd_reject(self, parts: List[str]) -> None:
        if len(parts) < 2:
            print("usage: :reject <name>")
            return
        name = parts[1]
        compiled = self.compiled_meta.get(name)
        if compiled is None or compiled.provenance is None:
            print(f"no compiled declaration with provenance for {name!r}")
            return
        prov = compiled.provenance
        removed = self.snapshot_store.remove(prov.intent_hash)
        prov.accepted = False
        msg = "removed from snapshot" if removed else "no snapshot entry"
        print(f"  ✗ {name} rejected ({msg})")

    def _cmd_mode(self, parts: List[str]) -> None:
        if len(parts) < 2:
            print(f"  current mode: {self.mode}")
            return
        target = parts[1].strip().lower()
        if target not in (OFFLINE, ONLINE, SNAPSHOT):
            print(f"  mode must be one of: {OFFLINE}, {ONLINE}, {SNAPSHOT}")
            return
        self.compiler = Compiler(
            mode=target,
            snapshot_store=self.snapshot_store,
        )
        self.mode = target
        print(f"  switched to {target} mode")

    # ------------------------------------------------------------------
    def _evaluate(self, src: str) -> None:
        value = self._eval_expression(src, label="expression")
        if value is _UNRESOLVED:
            return
        if value is not None:
            print(repr(value))


def _parse_cli(argv: List[str]) -> tuple:
    """Pull recognised flags out of argv. Remaining args are file paths.

    Recognised:
        --offline         force mode = offline (intent holes raise)
        --online          force mode = online  (use AnthropicCompiler)
        --snapshot        force mode = snapshot (replay-only by default)
        --snapshot=<path> use a non-default snapshot store
        --help, -h        print usage and exit
    """
    mode: Optional[str] = None
    snapshot_path: Optional[str] = None
    files: List[str] = []
    for arg in argv:
        if arg in ("--offline",):
            mode = OFFLINE
        elif arg in ("--online",):
            mode = ONLINE
        elif arg == "--snapshot":
            mode = SNAPSHOT
        elif arg.startswith("--snapshot="):
            snapshot_path = arg.split("=", 1)[1]
            if mode is None:
                mode = SNAPSHOT
        elif arg in ("--help", "-h"):
            print(__doc__)
            print("Flags: --offline | --online | --snapshot[=<path>]")
            sys.exit(0)
        else:
            files.append(arg)
    return mode, snapshot_path, files


def main(argv: List[str] | None = None) -> None:
    argv = argv if argv is not None else sys.argv[1:]
    mode, snapshot_path, files = _parse_cli(argv)
    store = SnapshotStore(snapshot_path) if snapshot_path else None
    r = REPL(mode=mode, snapshot_store=store)
    for path in files:
        print(f"loading {path}...")
        r.load_file(path)
    r.run()


if __name__ == "__main__":
    main()
