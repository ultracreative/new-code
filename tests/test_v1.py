"""
v1.0 regression tests.

These cover the new machinery added in v1.0:

  * SnapshotStore + SnapshotCompiler — deterministic replay of accepted
    bodies, including the "no snapshot, no fallback → LookupError" path.
  * Provenance — every Compiled artefact carries a populated provenance
    record describing where its body came from.
  * OfflineHoleError — offline mode refuses to compile intent holes that
    the offline pattern matcher cannot satisfy, with a helpful message.
  * REPL `let` evaluation — `let x = <expression>` now parses through the
    New Code expression grammar (expr.py) instead of Python eval().
  * REPL `:accept` / `:reject` — round-trip an Anthropic-style body
    through the snapshot store and confirm subsequent compiles replay
    deterministically.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from newcode import (
    Compiler, Compiled, Provenance,
    OfflineCompiler, SnapshotCompiler, SnapshotStore, OfflineHoleError,
    intent_hash, body_hash,
    OFFLINE, ONLINE, SNAPSHOT,
    parse,
)
from newcode.parser import Function, Intent, Process as ProcessDecl, Arg
from newcode.compiler import (
    _compile_function_body, _validate, _normalise_explicit_body,
)
from newcode.repl import REPL


def _hole_fn(name: str, intent: str) -> Function:
    """Construct a Function decl with a hole, by hand. The parser exercises
    the same shape; doing it by hand keeps these tests focussed."""
    return Function(
        name=name,
        args=[Arg(name="x", type_="𝕎")],
        return_type="𝕎",
        intent=Intent(intent=intent),
        body="??",
        is_hole=True,
    )


class TestSnapshotStore(unittest.TestCase):
    def test_put_and_get_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "snap.json"
            store = SnapshotStore(path)
            store.put(
                "abc123",
                source="    return x",
                model="test-model",
                decl_name="identity",
                accepted=True,
            )
            # New instance reads from disk.
            store2 = SnapshotStore(path)
            entry = store2.get("abc123")
            self.assertIsNotNone(entry)
            self.assertEqual(entry["source"], "    return x")
            self.assertTrue(entry["accepted"])
            self.assertEqual(entry["body_hash"], body_hash("    return x"))

    def test_mark_accepted_and_remove(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "snap.json"
            store = SnapshotStore(path)
            store.put("k", source="    return 1",
                      model="m", decl_name="d", accepted=False)
            self.assertTrue(store.mark_accepted("k", True))
            self.assertTrue(store.get("k")["accepted"])
            self.assertTrue(store.remove("k"))
            self.assertIsNone(store.get("k"))


class TestIntentHash(unittest.TestCase):
    def test_hash_is_stable(self):
        decl = _hole_fn("amp", "amplify the signal by gain")
        h1 = intent_hash(decl)
        h2 = intent_hash(decl)
        self.assertEqual(h1, h2)

    def test_hash_changes_with_intent_text(self):
        a = _hole_fn("amp", "amplify the signal by gain")
        b = _hole_fn("amp", "invert the phase of the signal")
        self.assertNotEqual(intent_hash(a), intent_hash(b))


class TestProvenance(unittest.TestCase):
    def test_offline_compiler_populates_provenance(self):
        decl = _hole_fn("amp", "amplify the signal by gain")
        decl.args.append(Arg(name="gain", type_="ℝ"))
        compiled = OfflineCompiler().compile(decl)
        self.assertIsInstance(compiled, Compiled)
        prov = compiled.provenance
        self.assertIsNotNone(prov)
        self.assertEqual(prov.backend, "offline")
        self.assertEqual(prov.intent_hash, intent_hash(decl))
        self.assertTrue(prov.accepted)  # offline patterns are auto-accepted

    def test_explicit_body_has_explicit_provenance(self):
        src = """
fn double(x : ℝ) → ℝ
    intent: 「double the input」
    ≔ x * 2.0
""".strip()
        decls = parse(src)
        c = Compiler(mode=OFFLINE)
        compiled = c.compile(decls[0])
        self.assertIsNotNone(compiled.provenance)
        self.assertEqual(compiled.provenance.backend, "explicit")
        self.assertTrue(compiled.provenance.accepted)
        self.assertEqual(compiled(3.0), 6.0)


class TestOfflineHoleError(unittest.TestCase):
    def test_offline_hole_raises_on_unknown_intent(self):
        decl = _hole_fn("mystery", "make it feel different somehow")
        c = Compiler(mode=OFFLINE)
        with self.assertRaises(OfflineHoleError) as ctx:
            c.compile(decl)
        self.assertIn("mystery", str(ctx.exception))
        self.assertIn("--online", str(ctx.exception))

    def test_offline_compiler_still_handles_known_intents(self):
        decl = _hole_fn("amp", "amplify the signal")
        decl.args.append(Arg(name="gain", type_="ℝ"))
        c = Compiler(mode=OFFLINE)
        compiled = c.compile(decl)
        self.assertIsNotNone(compiled.provenance)
        self.assertEqual(compiled.provenance.backend, "offline")


class TestSnapshotCompiler(unittest.TestCase):
    def test_replay_from_snapshot(self):
        decl = _hole_fn("amp", "amplify by some factor")
        ihash = intent_hash(decl)

        with tempfile.TemporaryDirectory() as tmp:
            store = SnapshotStore(Path(tmp) / "snap.json")
            store.put(
                ihash,
                source=(
                    "    f_, A_, phi_, sigma_ = x.unpack()\n"
                    "    return W(f=f_, A=A_ * 2.0, phi=phi_, sigma=sigma_)"
                ),
                model="recorded",
                decl_name="amp",
                accepted=True,
            )
            sc = SnapshotCompiler(store)
            compiled = sc.compile(decl)
            self.assertEqual(compiled.provenance.backend, "snapshot")
            self.assertEqual(compiled.provenance.model, "recorded")
            self.assertTrue(compiled.provenance.accepted)
            # And it actually runs.
            from newcode import w, sine
            out = compiled(w(f=440, A=1.0, phi=0.0, sigma=sine))
            self.assertAlmostEqual(out.A, 2.0)

    def test_miss_without_fallback_raises(self):
        decl = _hole_fn("nope", "intent never recorded")
        with tempfile.TemporaryDirectory() as tmp:
            store = SnapshotStore(Path(tmp) / "snap.json")
            sc = SnapshotCompiler(store, fallback=None)
            with self.assertRaises(LookupError):
                sc.compile(decl)

    def test_miss_with_fallback_uses_fallback(self):
        decl = _hole_fn("amp", "amplify the signal")
        decl.args.append(Arg(name="gain", type_="ℝ"))
        with tempfile.TemporaryDirectory() as tmp:
            store = SnapshotStore(Path(tmp) / "snap.json")
            sc = SnapshotCompiler(store, fallback=OfflineCompiler())
            compiled = sc.compile(decl)
            self.assertEqual(compiled.provenance.backend, "offline")


class TestREPLLetThroughExpr(unittest.TestCase):
    def test_let_uses_newcode_expression_grammar(self):
        src = "let g = 2.0 * 3.0\n"
        repl = REPL(mode=OFFLINE)
        repl.load_source(src)
        self.assertIn("g", repl.scope)
        self.assertAlmostEqual(repl.scope["g"], 6.0)

    def test_let_can_call_stdlib_functions(self):
        src = """
let baseline = w(f=2.0, A=1.0, phi=0.0, sigma=sine)
let louder   = amplify_w(baseline, 3.0)
""".strip() + "\n"
        # We don't actually have an `amplify_w` in stdlib by default —
        # exercise something that *is* there: superpose.
        src = """
let a = w(f=2.0, A=1.0, phi=0.0, sigma=sine)
let b = superpose(a, a)
""".strip() + "\n"
        repl = REPL(mode=OFFLINE)
        repl.load_source(src)
        self.assertIn("a", repl.scope)
        self.assertIn("b", repl.scope)


class TestREPLApprovalWorkflow(unittest.TestCase):
    def test_accept_persists_to_snapshot_store(self):
        # Use a hand-constructed function and a minimal valid body. The
        # offline compiler will fill it (intent matches "amplify"), then
        # we simulate the approval workflow against a fresh store.
        src = """
fn amp(x : 𝕎, gain : ℝ) → 𝕎
    intent: 「amplify the signal by gain」
    ≔ ??
""".strip()
        with tempfile.TemporaryDirectory() as tmp:
            store_path = Path(tmp) / "snap.json"
            store = SnapshotStore(store_path)
            repl = REPL(mode=OFFLINE, snapshot_store=store)
            repl.load_source(src)
            self.assertIn("amp", repl.compiled_meta)
            # Run accept programmatically.
            repl._cmd_accept([":accept", "amp"])
            ihash = repl.compiled_meta["amp"].provenance.intent_hash
            # Reload the store from disk and confirm it is there + accepted.
            store2 = SnapshotStore(store_path)
            entry = store2.get(ihash)
            self.assertIsNotNone(entry)
            self.assertTrue(entry["accepted"])

    def test_reject_removes_from_snapshot_store(self):
        src = """
fn amp(x : 𝕎, gain : ℝ) → 𝕎
    intent: 「amplify the signal by gain」
    ≔ ??
""".strip()
        with tempfile.TemporaryDirectory() as tmp:
            store_path = Path(tmp) / "snap.json"
            store = SnapshotStore(store_path)
            repl = REPL(mode=OFFLINE, snapshot_store=store)
            repl.load_source(src)
            repl._cmd_accept([":accept", "amp"])
            ihash = repl.compiled_meta["amp"].provenance.intent_hash
            self.assertIn(ihash, store)
            repl._cmd_reject([":reject", "amp"])
            store2 = SnapshotStore(store_path)
            self.assertNotIn(ihash, store2)


class TestModeAutoSelection(unittest.TestCase):
    def test_explicit_offline_overrides_env(self):
        # Even with a fake API key set, an explicit mode wins.
        old = os.environ.pop("ANTHROPIC_API_KEY", None)
        try:
            os.environ["ANTHROPIC_API_KEY"] = "sk-fake-just-for-test"
            c = Compiler(mode=OFFLINE)
            self.assertEqual(c.mode, OFFLINE)
            self.assertIsInstance(c.backend, OfflineCompiler)
        finally:
            if old is None:
                os.environ.pop("ANTHROPIC_API_KEY", None)
            else:
                os.environ["ANTHROPIC_API_KEY"] = old

    def test_no_api_key_defaults_to_offline(self):
        old = os.environ.pop("ANTHROPIC_API_KEY", None)
        try:
            c = Compiler()
            self.assertEqual(c.mode, OFFLINE)
        finally:
            if old is not None:
                os.environ["ANTHROPIC_API_KEY"] = old


class TestLSPv1Surface(unittest.TestCase):
    """v1.0 additions to the language server.

    Covers the surfaces that grew with v1.0: hover for the new stdlib
    helpers (`host_load`, `fold_left`, `pi`), completion of the new
    expression keywords (`let`, `in`, `if`, `then`, `else`, `\\` for
    lambdas), declaration-keyword completion for `import` / `extern`,
    document symbols for Import / Extern blocks, and the mode-aware
    info diagnostic for unknown-intent holes in offline mode.
    """

    def setUp(self):
        # Local imports to avoid pulling LSP machinery for unrelated tests.
        import io as _io
        import json as _json
        from newcode.lsp import LanguageServer
        self._io = _io
        self._json = _json
        self._LanguageServer = LanguageServer

    def _make_server(self):
        stdin = self._io.BytesIO()
        stdout = self._io.BytesIO()
        log = self._io.StringIO()
        return self._LanguageServer(stdin=stdin, stdout=stdout, log=log), stdout

    def _read_all(self, stdout_buf):
        data = stdout_buf.getvalue()
        messages = []
        i = 0
        while i < len(data):
            sep = data.find(b"\r\n\r\n", i)
            if sep < 0:
                break
            header_bytes = data[i:sep].decode("ascii")
            length = 0
            for h in header_bytes.split("\r\n"):
                if h.lower().startswith("content-length:"):
                    length = int(h.split(":", 1)[1].strip())
            body = data[sep + 4: sep + 4 + length]
            messages.append(self._json.loads(body.decode("utf-8")))
            i = sep + 4 + length
        return messages

    def _open_doc(self, srv, uri: str, text: str):
        srv._dispatch({
            "jsonrpc": "2.0", "method": "textDocument/didOpen",
            "params": {"textDocument": {
                "uri": uri, "languageId": "newcode",
                "version": 1, "text": text,
            }},
        })

    def test_completion_offers_import_and_extern_at_line_start(self):
        srv, out = self._make_server()
        self._open_doc(srv, "file:///x.nc", "")
        out.seek(0); out.truncate(0)
        srv._dispatch({
            "jsonrpc": "2.0", "id": 1, "method": "textDocument/completion",
            "params": {
                "textDocument": {"uri": "file:///x.nc"},
                "position": {"line": 0, "character": 0},
            },
        })
        labels = [it["label"] for it in self._read_all(out)[-1]["result"]["items"]]
        self.assertIn("import", labels)
        self.assertIn("extern", labels)
        # Snippet variants ship too.
        self.assertIn("import host (snippet)", labels)
        self.assertIn("extern python (snippet)", labels)

    def test_completion_indented_line_offers_expr_keywords(self):
        srv, out = self._make_server()
        # Open a doc whose first line is just whitespace so we can request
        # completion at an indented column.
        self._open_doc(srv, "file:///x.nc", "    \n")
        out.seek(0); out.truncate(0)
        srv._dispatch({
            "jsonrpc": "2.0", "id": 2, "method": "textDocument/completion",
            "params": {
                "textDocument": {"uri": "file:///x.nc"},
                "position": {"line": 0, "character": 4},
            },
        })
        labels = [it["label"] for it in self._read_all(out)[-1]["result"]["items"]]
        for kw in ("in", "if", "then", "else", "match", "with"):
            self.assertIn(kw, labels)

    def test_hover_on_host_load(self):
        srv, out = self._make_server()
        self._open_doc(srv, "file:///x.nc",
                       "let np = host_load(\"numpy\")")
        out.seek(0); out.truncate(0)
        line = "let np = host_load(\"numpy\")"
        col = line.index("host_load") + 2
        srv._dispatch({
            "jsonrpc": "2.0", "id": 3, "method": "textDocument/hover",
            "params": {
                "textDocument": {"uri": "file:///x.nc"},
                "position": {"line": 0, "character": col},
            },
        })
        result = self._read_all(out)[-1]["result"]
        self.assertIsNotNone(result)
        self.assertIn("host_load", result["contents"]["value"])
        # Hover doc mentions the FFI / host bridge purpose.
        self.assertIn("host", result["contents"]["value"].lower())

    def test_hover_on_expr_keyword(self):
        srv, out = self._make_server()
        self._open_doc(srv, "file:///x.nc",
                       "let x = if a then 1 else 2")
        out.seek(0); out.truncate(0)
        line = "let x = if a then 1 else 2"
        # Position cursor inside "then"
        col = line.index("then") + 1
        srv._dispatch({
            "jsonrpc": "2.0", "id": 4, "method": "textDocument/hover",
            "params": {
                "textDocument": {"uri": "file:///x.nc"},
                "position": {"line": 0, "character": col},
            },
        })
        result = self._read_all(out)[-1]["result"]
        self.assertIsNotNone(result)
        self.assertIn("then", result["contents"]["value"].lower())

    def test_document_symbols_include_import_and_extern(self):
        srv, out = self._make_server()
        score = (
            "import host.numpy as np\n"
            "extern python {\n"
            "    SAMPLE_RATE = 44100\n"
            "}\n"
            "let beat = w(f=1.0, A=1.0, sigma=sine)\n"
        )
        self._open_doc(srv, "file:///x.nc", score)
        out.seek(0); out.truncate(0)
        srv._dispatch({
            "jsonrpc": "2.0", "id": 5, "method": "textDocument/documentSymbol",
            "params": {"textDocument": {"uri": "file:///x.nc"}},
        })
        symbols = self._read_all(out)[-1]["result"]
        names = [s["name"] for s in symbols]
        self.assertTrue(any(n.startswith("import host.numpy") for n in names))
        self.assertTrue(any(n.startswith("extern python") for n in names))
        self.assertIn("beat", names)

    def test_offline_unknown_intent_emits_info_diagnostic(self):
        srv, out = self._make_server()
        score = (
            "fn quantum (x : 𝕎) → 𝕎\n"
            "    intent: 「entangle x with the cosmic microwave background」\n"
            "    forbid: 「do nothing」\n"
            "    ensure: 「the universe still exists」\n"
            "    ≔ ??\n"
        )
        self._open_doc(srv, "file:///x.nc", score)
        notifications = self._read_all(out)
        pubs = [m for m in notifications
                if m.get("method") == "textDocument/publishDiagnostics"]
        self.assertEqual(len(pubs), 1)
        diags = pubs[0]["params"]["diagnostics"]
        # Should include at least one Info-severity hint about offline.
        info_hints = [d for d in diags if d.get("severity") == 3]
        self.assertGreaterEqual(len(info_hints), 1)
        self.assertIn("quantum", info_hints[0]["message"])
        self.assertIn("--online", info_hints[0]["message"])

    def test_offline_known_intent_emits_no_info_diagnostic(self):
        srv, out = self._make_server()
        score = (
            "fn amplify (signal : 𝕎, gain : ℝ) → 𝕎\n"
            "    intent: 「scale the amplitude of signal by gain "
            "while preserving shape」\n"
            "    forbid: 「do not modify phase」\n"
            "    ensure: 「output shape equals input shape」\n"
            "    ≔ ??\n"
        )
        self._open_doc(srv, "file:///x.nc", score)
        notifications = self._read_all(out)
        pubs = [m for m in notifications
                if m.get("method") == "textDocument/publishDiagnostics"]
        diags = pubs[0]["params"]["diagnostics"]
        # No info diagnostics — the offline backend recognises "amplify".
        info_hints = [d for d in diags if d.get("severity") == 3]
        self.assertEqual(info_hints, [])


class TestPlaygroundEngine(unittest.TestCase):
    """The headless half of the browser playground.

    Drives PlaygroundEngine end-to-end: parse → compile → run-in-scope →
    accept → confirm the snapshot store now contains the entry. The HTTP
    layer is exercised separately in TestPlaygroundServer.
    """

    def setUp(self):
        from newcode.playground import PlaygroundEngine
        self._tmpdir = tempfile.TemporaryDirectory()
        store = SnapshotStore(path=Path(self._tmpdir.name) / "snap.json")
        self.engine = PlaygroundEngine(mode=OFFLINE, snapshot_store=store)

    def tearDown(self):
        self._tmpdir.cleanup()

    def _amplify_source(self) -> str:
        return (
            "let concert_a = w(f=440, A=1.0, phi=0, sigma=sine)\n"
            "\n"
            "fn amplify (signal : 𝕎, gain : ℝ) → 𝕎\n"
            "    intent: 「scale the amplitude of signal by gain "
            "while preserving shape」\n"
            "    forbid: 「do not modify phase」\n"
            "    ensure: 「output shape equals input shape」\n"
            "    ≔ ??\n"
        )

    def test_compile_returns_provenance_for_each_decl(self):
        result = self.engine.compile_source(self._amplify_source())
        self.assertIsNone(result["parse_error"])
        kinds = [r["kind"] for r in result["results"]]
        self.assertIn("let", kinds)
        self.assertIn("function", kinds)
        fn_entry = next(r for r in result["results"] if r["kind"] == "function")
        self.assertTrue(fn_entry["ok"])
        self.assertIn("provenance", fn_entry)
        self.assertEqual(fn_entry["provenance"]["backend"], "offline")
        self.assertTrue(fn_entry["provenance"]["intent_hash"])

    def test_run_evaluates_in_compiled_scope(self):
        self.engine.compile_source(self._amplify_source())
        out = self.engine.run_expression("amplify(concert_a, 2.0).A")
        self.assertTrue(out["ok"], msg=out)
        self.assertEqual(out["repr"], "2.0")

    def test_offline_unknown_intent_returns_offline_hole_error_entry(self):
        src = (
            "fn bogus (x : 𝕎) → 𝕎\n"
            "    intent: 「do something the offline pattern table never heard of」\n"
            "    ≔ ??\n"
        )
        result = self.engine.compile_source(src)
        fn_entry = next(r for r in result["results"] if r["kind"] == "function")
        self.assertFalse(fn_entry["ok"])
        self.assertEqual(fn_entry["error_kind"], "OfflineHoleError")

    def test_accept_persists_to_snapshot_store(self):
        self.engine.compile_source(self._amplify_source())
        before = len(self.engine.snapshot_store)
        r = self.engine.accept("amplify")
        self.assertTrue(r["ok"], msg=r)
        self.assertEqual(len(self.engine.snapshot_store), before + 1)
        # The provenance object should now report accepted=True.
        compiled = self.engine.compiled["amplify"]
        self.assertTrue(compiled.provenance.accepted)
        # And the entry round-trips.
        entry = self.engine.snapshot_store.get(r["intent_hash"])
        self.assertIsNotNone(entry)
        self.assertEqual(entry["decl_name"], "amplify")
        self.assertTrue(entry["accepted"])

    def test_reject_removes_from_snapshot_store(self):
        self.engine.compile_source(self._amplify_source())
        r1 = self.engine.accept("amplify")
        self.assertTrue(r1["ok"])
        r2 = self.engine.reject("amplify")
        self.assertTrue(r2["ok"])
        self.assertEqual(len(self.engine.snapshot_store), 0)

    def test_set_mode_swaps_compiler(self):
        self.assertEqual(self.engine.mode, OFFLINE)
        self.engine.set_mode(SNAPSHOT)
        self.assertEqual(self.engine.mode, SNAPSHOT)

    def test_set_mode_rejects_unknown(self):
        with self.assertRaises(ValueError):
            self.engine.set_mode("warp")


class TestPlaygroundServer(unittest.TestCase):
    """The HTTP shell around PlaygroundEngine.

    Uses urllib against a real ThreadingHTTPServer bound to a random
    port. Snapshot store is in a tempdir so the user's home is never
    touched.
    """

    def setUp(self):
        import urllib.request as _ur
        from newcode.playground import PlaygroundEngine, PlaygroundServer
        self._urllib = _ur
        self._tmpdir = tempfile.TemporaryDirectory()
        store = SnapshotStore(path=Path(self._tmpdir.name) / "snap.json")
        engine = PlaygroundEngine(mode=OFFLINE, snapshot_store=store)
        self.server = PlaygroundServer(engine=engine, port=0)
        self.url = self.server.start()

    def tearDown(self):
        self.server.stop()
        self._tmpdir.cleanup()

    def _post_json(self, path: str, payload: dict) -> dict:
        import json as _json
        data = _json.dumps(payload).encode("utf-8")
        req = self._urllib.Request(
            self.url + path,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with self._urllib.urlopen(req, timeout=5) as resp:
            return _json.loads(resp.read().decode("utf-8"))

    def _get_json(self, path: str) -> dict:
        import json as _json
        with self._urllib.urlopen(self.url + path, timeout=5) as resp:
            return _json.loads(resp.read().decode("utf-8"))

    def test_get_index_serves_html(self):
        with self._urllib.urlopen(self.url, timeout=5) as resp:
            body = resp.read()
        self.assertIn(b"<title>", body)
        self.assertIn(b"New Code", body)

    def test_state_endpoint_reports_mode(self):
        state = self._get_json("api/state")
        self.assertEqual(state["mode"], "offline")
        self.assertEqual(state["snapshot_count"], 0)

    def test_compile_endpoint_returns_results(self):
        src = (
            "fn amplify (signal : 𝕎, gain : ℝ) → 𝕎\n"
            "    intent: 「scale the amplitude of signal by gain "
            "while preserving shape」\n"
            "    forbid: 「do not modify phase」\n"
            "    ensure: 「output shape equals input shape」\n"
            "    ≔ ??\n"
        )
        r = self._post_json("api/compile", {"source": src})
        self.assertIsNone(r["parse_error"])
        self.assertEqual(len(r["results"]), 1)
        self.assertEqual(r["results"][0]["name"], "amplify")
        self.assertTrue(r["results"][0]["ok"])

    def test_accept_endpoint_persists(self):
        src = (
            "fn amplify (signal : 𝕎, gain : ℝ) → 𝕎\n"
            "    intent: 「scale the amplitude of signal by gain "
            "while preserving shape」\n"
            "    forbid: 「do not modify phase」\n"
            "    ensure: 「output shape equals input shape」\n"
            "    ≔ ??\n"
        )
        self._post_json("api/compile", {"source": src})
        r = self._post_json("api/accept", {"name": "amplify"})
        self.assertTrue(r["ok"], msg=r)
        # State endpoint should now report 1 entry in the store.
        state = self._get_json("api/state")
        self.assertEqual(state["snapshot_count"], 1)


if __name__ == "__main__":
    unittest.main()
