"""
Tests for New Code v0.01.

Run with: python -m pytest tests/ -v
Or: python -m unittest tests.test_core
"""

import io
import json
import math
import unittest

from newcode import (
    W, w, sine, sq, tri, saw, pulse, e0, silence,
    superpose, oscillate, invert, drift,
    coherence, d_gamma, collapse, collapse_amp, collapse_freq, collapse_rms,
    fingerprint, identifiability_horizon,
    Process, every, unfold, drift_process, series, parallel, feedback,
    Entangled, entangle, pitch_follow, amplitude_mirror, phase_opposition,
    parse, OfflineCompiler, Compiler,
    Tracer, LanguageServer,
)
from newcode.repl import REPL


class TestWaveformPrimitive(unittest.TestCase):

    def test_unit_oscillator(self):
        self.assertAlmostEqual(e0.f, 1.0)
        self.assertAlmostEqual(e0.A, 1.0)
        self.assertEqual(e0.sigma.name, "sine")

    def test_realise(self):
        # A 1 Hz sine at t=0.25 should be sin(π/2) = 1.
        v = e0.realise(0.25)
        self.assertAlmostEqual(v, 1.0, places=6)

    def test_silence(self):
        self.assertEqual(silence.A, 0.0)
        for t in [0.0, 0.1, 0.5, 1.0]:
            self.assertAlmostEqual(silence.realise(t), 0.0)


class TestOperators(unittest.TestCase):

    def test_superpose_same_freq_sine(self):
        # Two unit sines in phase should double in amplitude.
        a = w(f=1.0, A=1.0, phi=0.0, sigma=sine)
        b = w(f=1.0, A=1.0, phi=0.0, sigma=sine)
        result = superpose(a, b)
        self.assertAlmostEqual(result.A, 2.0, places=6)
        self.assertEqual(result.sigma.name, "sine")

    def test_superpose_antiphase_cancels(self):
        a = w(f=1.0, A=1.0, phi=0.0, sigma=sine)
        b = invert(a)
        result = superpose(a, b)
        self.assertLess(result.A, 1e-6)

    def test_oscillate_amplitude(self):
        a = w(f=1.0, A=2.0, sigma=sine)
        b = w(f=3.0, A=0.5, sigma=sine)
        result = oscillate(a, b)
        self.assertAlmostEqual(result.A, 1.0)

    def test_drift_zero_is_identity(self):
        a = w(f=440.0, A=0.8, phi=0.1, sigma=sine)
        result = drift(a, 0.0)
        self.assertAlmostEqual(result.f, a.f)
        self.assertAlmostEqual(result.A, a.A, places=6)

    def test_drift_decays_amplitude(self):
        a = w(f=1.0, A=1.0, sigma=sine)
        result = drift(a, 1.0)
        self.assertLess(result.A, a.A)
        self.assertAlmostEqual(result.A, math.exp(-1.0), places=6)

    def test_drift_large_converges_to_square(self):
        a = w(f=1.0, A=1.0, sigma=sine)
        # Drift hard. Amplitude decays but shape should bend toward square.
        result = drift(a, 1.0)
        # After a full unit of drift, shape is mostly square by our morph.
        self.assertIn("sq", result.sigma.name)

    def test_coherence_self_is_one(self):
        a = w(f=2.0, A=0.7, phi=0.3, sigma=sine)
        c = coherence(a, a)
        self.assertAlmostEqual(c, 1.0, places=4)

    def test_coherence_antiphase_is_negative(self):
        a = w(f=1.0, A=1.0, phi=0.0, sigma=sine)
        b = invert(a)
        c = coherence(a, b)
        self.assertLess(c, -0.99)

    def test_d_gamma_self_is_zero(self):
        a = w(f=1.0, A=1.0, sigma=sine)
        self.assertAlmostEqual(d_gamma(a, a), 0.0, places=3)

    def test_collapse_preserves_sign(self):
        a = w(f=1.0, A=1.0, sigma=sine)
        s = collapse(a)
        # Collapse is A × coherence(a, e0); with identical shape/freq, ~1.
        self.assertGreater(s, 0.99)

    def test_collapse_amp(self):
        a = w(f=2.0, A=3.5, phi=0.7, sigma=tri)
        self.assertAlmostEqual(collapse_amp(a), 3.5)

    def test_collapse_freq(self):
        a = w(f=440.0, A=1.0, sigma=saw)
        self.assertAlmostEqual(collapse_freq(a), 440.0)

    def test_collapse_rms_of_sine(self):
        a = w(f=1.0, A=1.0, sigma=sine)
        rms = collapse_rms(a)
        # The RMS of a unit sine is 1/√2 ≈ 0.707.
        self.assertAlmostEqual(rms, 1.0 / math.sqrt(2), places=2)


class TestShapes(unittest.TestCase):

    def test_square_at_half(self):
        # sq(0.25) = 1, sq(0.75) = -1.
        self.assertAlmostEqual(sq(0.25), 1.0)
        self.assertAlmostEqual(sq(0.75), -1.0)

    def test_triangle_symmetry(self):
        self.assertAlmostEqual(tri(0.25), 0.0, places=6)
        self.assertAlmostEqual(tri(0.5), 1.0, places=6)
        self.assertAlmostEqual(tri(0.75), 0.0, places=6)

    def test_saw_at_zero(self):
        self.assertAlmostEqual(saw(0.0), -1.0)

    def test_pulse_duty(self):
        p = pulse(0.1)
        self.assertEqual(p(0.05), 1.0)
        self.assertEqual(p(0.5), -1.0)


class TestProcesses(unittest.TestCase):

    def test_every_samples(self):
        p = every(w(f=2.0, A=1.0))
        values = unfold(p, 3)
        self.assertEqual(len(values), 3)
        for v in values:
            self.assertAlmostEqual(v.f, 2.0)

    def test_drift_process_ages(self):
        p = every(w(f=1.0, A=1.0, sigma=sine))
        aged = drift_process(p, delta_per_step=0.2)
        values = unfold(aged, 5)
        # Amplitude should monotonically decrease.
        amps = [v.A for v in values]
        for a, b in zip(amps, amps[1:]):
            self.assertGreaterEqual(a, b)

    def test_process_tau_advances_by_inverse_rate(self):
        p = every(w(f=4.0, A=1.0, sigma=sine))
        self.assertAlmostEqual(p.tau, 0.0)
        p.sample()
        self.assertAlmostEqual(p.tau, 0.25)
        p.sample()
        self.assertAlmostEqual(p.tau, 0.5)

    def test_every_returns_static_wave_descriptor(self):
        signal = w(f=2.0, A=1.0, phi=0.0, sigma=sine)
        p = every(signal)
        first = p.sample()
        second = p.sample()
        self.assertEqual(first, signal)
        self.assertEqual(second, signal)
        self.assertNotAlmostEqual(first.realise(0.0), first.realise(0.125))

    def test_series_samples_children_and_feeds_output_forward(self):
        source = Process(name="source", rate=2.0, step=lambda tau: tau)
        sink = Process(name="sink", rate=4.0, step=lambda tau, incoming: (tau, incoming))
        pipeline = series(source, sink)
        out1 = pipeline.sample()
        out2 = pipeline.sample()
        self.assertEqual(out1, (0.0, 0.0))
        self.assertEqual(out2, (0.25, 0.5))
        self.assertAlmostEqual(source.tau, 1.0)
        self.assertAlmostEqual(sink.tau, 0.5)

    def test_parallel_samples_both_children(self):
        left = every(w(f=2.0, A=1.0, sigma=sine), name="left")
        right = every(w(f=5.0, A=1.0, sigma=tri), name="right")
        duo = parallel(left, right)
        values = unfold(duo, 2)
        self.assertEqual(len(values), 2)
        self.assertAlmostEqual(left.tau, 1.0)
        self.assertAlmostEqual(right.tau, 0.4)
        self.assertEqual(values[0][0].sigma.name, "sine")
        self.assertEqual(values[0][1].sigma.name, "triangle")

    def test_feedback_reinjects_delayed_output(self):
        inner = Process(
            name="acc",
            rate=2.0,
            step=lambda tau, incoming=None: (incoming or 0) + 1,
        )
        loop = feedback(inner, delay_samples=2)
        values = unfold(loop, 4)
        self.assertEqual(values, [1, 1, 2, 2])
        self.assertAlmostEqual(inner.tau, 2.0)


class TestEntanglement(unittest.TestCase):

    def test_entangle_initial(self):
        L = w(f=100, A=1.0)
        R = pitch_follow(L)
        pair = entangle(L, R, via=pitch_follow)
        self.assertAlmostEqual(pair.left.f, 100)
        self.assertAlmostEqual(pair.right.f, 150)

    def test_transform_propagates(self):
        L = w(f=100, A=1.0)
        R = pitch_follow(L)
        pair = entangle(L, R, via=pitch_follow)

        def doubled(x):
            return w(f=x.f * 2, A=x.A, phi=x.phi, sigma=x.sigma)

        new_pair = pair.transform_left(doubled)
        self.assertAlmostEqual(new_pair.left.f, 200)
        self.assertAlmostEqual(new_pair.right.f, 300)  # pitch_follow(200)

    def test_entanglement_not_transitive(self):
        # The API simply does not expose a way to chain entanglements;
        # declaring A▷◁B and B▷◁C does not create A▷◁C. This is tested
        # structurally: Entangled has no transitive constructor.
        self.assertFalse(hasattr(Entangled, "transitive_close"))


class TestParser(unittest.TestCase):

    def test_parse_function(self):
        src = """fn amplify (w_in : 𝕎, gain : ℝ) → 𝕎
    intent: 「scale the amplitude of w_in by gain while preserving shape」
    forbid: 「do not modify phase」
    ensure: 「output shape equals input shape」
    ≔ ??"""
        decls = parse(src)
        self.assertEqual(len(decls), 1)
        fn = decls[0]
        self.assertEqual(fn.name, "amplify")
        self.assertEqual(len(fn.args), 2)
        self.assertEqual(fn.args[0].name, "w_in")
        self.assertTrue(fn.is_hole)
        self.assertIn("scale", fn.intent.intent.lower())

    def test_parse_let(self):
        src = "let heartbeat : 𝕎 = ⟨1.0, 1.0, 0, sine⟩"
        decls = parse(src)
        self.assertEqual(len(decls), 1)
        self.assertEqual(decls[0].name, "heartbeat")

    def test_parse_alternative_bind(self):
        src = """fn f (x : 𝕎) → 𝕎
    intent: 「identity」
    forbid: 「nothing」
    ensure: 「identity」
    := ??"""
        decls = parse(src)
        self.assertEqual(decls[0].name, "f")


class TestOfflineCompiler(unittest.TestCase):

    def test_compiles_amplify(self):
        src = """fn amplify (w_in : 𝕎, gain : ℝ) → 𝕎
    intent: 「scale the amplitude of w_in by gain while preserving shape」
    forbid: 「do not modify phase」
    ensure: 「output shape equals input shape」
    ≔ ??"""
        decl = parse(src)[0]
        c = OfflineCompiler()
        compiled = c.compile(decl)
        input_wave = w(f=440, A=1.0, sigma=sine)
        result = compiled(input_wave, 2.5)
        self.assertAlmostEqual(result.A, 2.5)
        self.assertAlmostEqual(result.f, 440)
        self.assertEqual(result.sigma.name, "sine")

    def test_compiles_drift(self):
        src = """fn age (w_in : 𝕎, delta : ℝ) → 𝕎
    intent: 「drift w_in by delta, ageing toward the square-wave attractor」
    forbid: 「nothing」
    ensure: 「amplitude does not increase」
    ≔ ??"""
        decl = parse(src)[0]
        c = OfflineCompiler()
        compiled = c.compile(decl)
        input_wave = w(f=1.0, A=1.0, sigma=sine)
        result = compiled(input_wave, 0.5)
        self.assertLess(result.A, 1.0)

    def test_attaches_constraint_report(self):
        src = """fn amplify (w_in : 𝕎, gain : ℝ) → 𝕎
    intent: 「scale the amplitude of w_in by gain while preserving shape」
    forbid: 「do not modify phase」
    ensure: 「output shape equals input shape」
    ≔ ??"""
        decl = parse(src)[0]
        compiled = OfflineCompiler().compile(decl)
        self.assertIsNotNone(compiled.report)
        findings = {f.clause: f.verdict for f in compiled.report.findings}
        self.assertEqual(findings.get("forbid"), "honored")
        self.assertEqual(findings.get("ensure"), "honored")


class TestExplicitBodies(unittest.TestCase):

    def test_explicit_expression_body_compiles(self):
        src = """fn identity_wave (signal : 𝕎) → 𝕎
    intent: 「preserve signal shape」
    forbid: 「do not modify phase」
    ensure: 「output shape equals input shape」
    ≔ signal"""
        decl = parse(src)[0]
        compiled = Compiler().compile(decl)
        signal = w(f=3.0, A=0.8, phi=0.4, sigma=tri)
        result = compiled(signal)
        self.assertAlmostEqual(result.f, signal.f)
        self.assertAlmostEqual(result.A, signal.A)
        self.assertAlmostEqual(result.phi, signal.phi)
        self.assertEqual(result.sigma.name, signal.sigma.name)
        self.assertIsNotNone(compiled.report)

    def test_repl_explicit_function_sees_scope(self):
        src = """let base_gain : ℝ = 2.0
fn amplify_by_base (signal : 𝕎) → 𝕎
    intent: 「scale the amplitude of signal by base_gain while preserving shape」
    forbid: 「do not modify phase」
    ensure: 「output shape equals input shape」
    ≔ W(f=signal.f, A=signal.A * base_gain, phi=signal.phi, sigma=signal.sigma)"""
        repl = REPL()
        repl.load_source(src)
        signal = w(f=10.0, A=0.5, phi=0.2, sigma=saw)
        result = repl.scope["amplify_by_base"](signal)
        self.assertAlmostEqual(result.A, 1.0)
        self.assertAlmostEqual(result.phi, signal.phi)
        self.assertEqual(result.sigma.name, signal.sigma.name)

    def test_repl_installs_explicit_process(self):
        src = """process beat : Process
    intent: 「emit a steady waveform」
    ≔ every(w(f=2.0, A=1.0, sigma=sine), name="beat")"""
        repl = REPL()
        repl.load_source(src)
        self.assertIn("beat", repl.scope)
        self.assertIsInstance(repl.scope["beat"], Process)
        values = unfold(repl.scope["beat"], 3)
        self.assertEqual(len(values), 3)
        for value in values:
            self.assertAlmostEqual(value.f, 2.0)


class TestProcessCompilation(unittest.TestCase):

    def test_offline_compiles_emit_process_from_wave_binding(self):
        src = """let calm_belief : 𝕎 = w(f=0.1, A=0.9, phi=0.0, sigma=sine)
process calm_loop : Process
    intent: 「emit calm_belief at each tick」
    ≔ ??"""
        repl = REPL()
        repl.load_source(src)
        self.assertIn("calm_loop", repl.scope)
        self.assertIsInstance(repl.scope["calm_loop"], Process)
        values = unfold(repl.scope["calm_loop"], 2)
        self.assertEqual(len(values), 2)
        self.assertAlmostEqual(values[0].f, 0.1)
        self.assertAlmostEqual(values[1].A, 0.9)
        self.assertIn("calm_loop", repl.compiled_meta)

    def test_offline_compiles_drift_process_from_wave_binding(self):
        src = """let anxious_belief : 𝕎 = w(f=5.0, A=0.3, phi=1.2, sigma=saw)
process anxious_loop : Process
    intent: 「drift anxious_belief by 0.08 each step」
    ≔ ??"""
        repl = REPL()
        repl.load_source(src)
        proc = repl.scope["anxious_loop"]
        self.assertIsInstance(proc, Process)
        values = unfold(proc, 3)
        self.assertGreater(values[1].f, values[0].f)
        self.assertLess(values[1].A, values[0].A)

    def test_compiler_rejects_unknown_process_intent_offline(self):
        src = """let base_wave : 𝕎 = w(f=1.0, A=1.0, sigma=sine)
process mystery : Process
    intent: 「make it feel different somehow」
    ≔ ??"""
        repl = REPL()
        repl.load_source(src)
        self.assertNotIn("mystery", repl.scope)


class TestDebugger(unittest.TestCase):

    def test_tracer_records_process_samples(self):
        t = Tracer()
        p = every(w(f=2.0, A=1.0, sigma=sine))
        t.track_process("voice", p)
        # Sampling the wrapped process must produce events and keep working.
        v1 = p.sample()
        v2 = p.sample()
        self.assertIsInstance(v1, W)
        self.assertIsInstance(v2, W)
        tp = t.processes["voice"]
        self.assertEqual(len(tp.samples), 2)
        self.assertEqual(tp.samples[0]["type"], "sample")
        self.assertEqual(tp.samples[0]["process"], "voice")
        self.assertAlmostEqual(tp.samples[0]["tau"], 0.0)
        # Events are also on the shared log, preceded by registration.
        types = [e["type"] for e in t.log]
        self.assertEqual(types[0], "process_registered")
        self.assertEqual(types.count("sample"), 2)

    def test_wave_samples_carry_tau_realisation_and_ribbon(self):
        # v0.01 bug: samples were always realised at t=0, so the debugger
        # plotted a flat line. Guard against regression.
        t = Tracer()
        p = every(w(f=1.0, A=1.0, sigma=sine))
        t.track_process("beat", p)
        p.sample()
        p.sample()
        tp = t.processes["beat"]
        first = tp.samples[0]
        # The sample's value should be realised at tau_before.
        expected = w(f=1.0, A=1.0, sigma=sine).realise(first["tau"])
        self.assertAlmostEqual(first["value"]["realised"], expected)
        # A 𝕎 sample carries a ribbon — a dense list of (τ, y) pairs
        # spanning [τ_before, τ_after) for shape-accurate rendering.
        self.assertIn("ribbon", first)
        ribbon = first["ribbon"]
        self.assertGreaterEqual(len(ribbon), 8)
        # Ribbon τs stay inside the step's interval.
        for tau, _y in ribbon:
            self.assertGreaterEqual(tau, first["tau"])
            self.assertLessEqual(tau, first["tau_after"] + 1e-6)
        # Ribbon ys respect the waveform's amplitude bound.
        for _tau, y in ribbon:
            self.assertLessEqual(abs(y), 1.0 + 1e-6)

    def test_tracer_records_entanglement_firings(self):
        t = Tracer()
        L = w(f=100, A=1.0)
        R = pitch_follow(L)
        pair = entangle(L, R, via=pitch_follow, name="voices")
        t.track_entangled("voices", pair)

        def doubled(x):
            return w(f=x.f * 2, A=x.A, phi=x.phi, sigma=x.sigma)

        pair.transform_left(doubled)
        te = t.entangled["voices"]
        self.assertEqual(len(te.firings), 1)
        firing = te.firings[0]
        self.assertEqual(firing["side"], "left")
        self.assertEqual(firing["op"], "doubled")
        self.assertAlmostEqual(firing["after"]["left"]["f"], 200)
        self.assertAlmostEqual(firing["after"]["right"]["f"], 300)
        # And the wrapped pair's own state reflects the firing.
        self.assertAlmostEqual(pair.left.f, 200)
        self.assertAlmostEqual(pair.right.f, 300)

    def test_tracer_subscribe_receives_future_events(self):
        t = Tracer()
        p = every(w(f=1.0, A=1.0, sigma=sine))
        t.track_process("p1", p)
        q = t.subscribe()
        # Subscriber replays the registration event first.
        drained = []
        while not q.empty():
            drained.append(q.get_nowait())
        self.assertEqual(drained[0]["type"], "process_registered")
        # New samples are delivered live.
        p.sample()
        live = q.get(timeout=0.5)
        self.assertEqual(live["type"], "sample")
        self.assertEqual(live["process"], "p1")

    def test_snapshot_shape(self):
        t = Tracer()
        p = every(w(f=1.0, A=1.0, sigma=sine))
        t.track_process("beat", p)
        p.sample()
        snap = t.snapshot()
        self.assertEqual(len(snap["processes"]), 1)
        self.assertEqual(snap["processes"][0]["name"], "beat")
        self.assertEqual(len(snap["processes"][0]["samples"]), 1)
        self.assertEqual(snap["entangled"], [])


class TestLanguageServer(unittest.TestCase):
    """Drive the language server in-process over a pair of BytesIO buffers.

    We build LSP messages by hand (Content-Length framing + JSON body),
    feed them to the server's stdin, run one ``serve`` step per message
    by calling the dispatcher directly, and inspect what ends up on stdout.
    """

    def _make_server(self):
        stdin = io.BytesIO()
        stdout = io.BytesIO()
        log = io.StringIO()
        return LanguageServer(stdin=stdin, stdout=stdout, log=log), stdout

    def _read_all(self, stdout_buf):
        """Read every framed message written to the server's stdout buffer."""
        data = stdout_buf.getvalue()
        messages = []
        i = 0
        while i < len(data):
            # Find header terminator.
            sep = data.find(b"\r\n\r\n", i)
            if sep < 0:
                break
            header_bytes = data[i:sep].decode("ascii")
            length = 0
            for h in header_bytes.split("\r\n"):
                if h.lower().startswith("content-length:"):
                    length = int(h.split(":", 1)[1].strip())
            body = data[sep + 4: sep + 4 + length]
            messages.append(json.loads(body.decode("utf-8")))
            i = sep + 4 + length
        return messages

    def test_initialize_advertises_capabilities(self):
        srv, out = self._make_server()
        srv._dispatch({
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"processId": None, "rootUri": None, "capabilities": {}},
        })
        responses = self._read_all(out)
        self.assertEqual(len(responses), 1)
        result = responses[0]["result"]
        caps = result["capabilities"]
        self.assertTrue(caps["hoverProvider"])
        self.assertTrue(caps["documentSymbolProvider"])
        self.assertIn("completionProvider", caps)
        self.assertEqual(result["serverInfo"]["name"], "newcode-lsp")

    def test_did_open_publishes_diagnostics(self):
        srv, out = self._make_server()
        # A score with a syntax error (malformed fn header).
        broken = "fn !!! () → 𝕎\n    ≔ ??"
        srv._dispatch({
            "jsonrpc": "2.0", "method": "textDocument/didOpen",
            "params": {"textDocument": {
                "uri": "file:///broken.nc", "languageId": "newcode",
                "version": 1, "text": broken,
            }},
        })
        notifications = self._read_all(out)
        # One publishDiagnostics with at least one diagnostic.
        pubs = [m for m in notifications
                if m.get("method") == "textDocument/publishDiagnostics"]
        self.assertEqual(len(pubs), 1)
        self.assertGreaterEqual(len(pubs[0]["params"]["diagnostics"]), 1)

    def test_completion_at_line_start_offers_decl_keywords(self):
        srv, out = self._make_server()
        srv._dispatch({
            "jsonrpc": "2.0", "method": "textDocument/didOpen",
            "params": {"textDocument": {
                "uri": "file:///x.nc", "languageId": "newcode",
                "version": 1, "text": "",
            }},
        })
        out.seek(0); out.truncate(0)
        srv._dispatch({
            "jsonrpc": "2.0", "id": 2, "method": "textDocument/completion",
            "params": {
                "textDocument": {"uri": "file:///x.nc"},
                "position": {"line": 0, "character": 0},
            },
        })
        responses = self._read_all(out)
        result = responses[-1]["result"]
        labels = [it["label"] for it in result["items"]]
        for kw in ("fn", "let", "process", "module"):
            self.assertIn(kw, labels)

    def test_hover_on_stdlib_name(self):
        srv, out = self._make_server()
        srv._dispatch({
            "jsonrpc": "2.0", "method": "textDocument/didOpen",
            "params": {"textDocument": {
                "uri": "file:///x.nc", "languageId": "newcode",
                "version": 1,
                "text": "let a : 𝕎 = drift(e0, 0.1)",
            }},
        })
        out.seek(0); out.truncate(0)
        # Position the cursor inside "drift".
        line = "let a : 𝕎 = drift(e0, 0.1)"
        col = line.index("drift") + 2
        srv._dispatch({
            "jsonrpc": "2.0", "id": 3, "method": "textDocument/hover",
            "params": {
                "textDocument": {"uri": "file:///x.nc"},
                "position": {"line": 0, "character": col},
            },
        })
        responses = self._read_all(out)
        hover = responses[-1]["result"]
        self.assertIsNotNone(hover)
        self.assertIn("drift", hover["contents"]["value"])

    def test_hover_on_user_declaration(self):
        srv, out = self._make_server()
        source = (
            "fn amplify (signal : 𝕎, gain : ℝ) → 𝕎\n"
            "    intent: 「scale the amplitude」\n"
            "    forbid: 「do not modify phase」\n"
            "    ensure: 「shape equal」\n"
            "    ≔ ??\n"
            "let x : 𝕎 = amplify(e0, 2.0)\n"
        )
        srv._dispatch({
            "jsonrpc": "2.0", "method": "textDocument/didOpen",
            "params": {"textDocument": {
                "uri": "file:///x.nc", "languageId": "newcode",
                "version": 1, "text": source,
            }},
        })
        out.seek(0); out.truncate(0)
        # The 'amplify' call in the last line is at a known column.
        last_line = source.splitlines()[-1]
        col = last_line.index("amplify") + 3
        srv._dispatch({
            "jsonrpc": "2.0", "id": 4, "method": "textDocument/hover",
            "params": {
                "textDocument": {"uri": "file:///x.nc"},
                "position": {"line": 5, "character": col},
            },
        })
        hover = self._read_all(out)[-1]["result"]
        self.assertIsNotNone(hover)
        value = hover["contents"]["value"]
        self.assertIn("amplify", value)
        self.assertIn("scale the amplitude", value)

    def test_document_symbols(self):
        srv, out = self._make_server()
        source = (
            "let concert_a : 𝕎 = w(f=440)\n"
            "fn amplify (s : 𝕎, g : ℝ) → 𝕎\n"
            "    intent: 「scale amplitude」\n"
            "    forbid: 「none」\n"
            "    ensure: 「shape」\n"
            "    ≔ ??\n"
        )
        srv._dispatch({
            "jsonrpc": "2.0", "method": "textDocument/didOpen",
            "params": {"textDocument": {
                "uri": "file:///x.nc", "languageId": "newcode",
                "version": 1, "text": source,
            }},
        })
        out.seek(0); out.truncate(0)
        srv._dispatch({
            "jsonrpc": "2.0", "id": 5, "method": "textDocument/documentSymbol",
            "params": {"textDocument": {"uri": "file:///x.nc"}},
        })
        symbols = self._read_all(out)[-1]["result"]
        names = [s["name"] for s in symbols]
        self.assertIn("concert_a", names)
        self.assertIn("amplify", names)


class TestIdentifiabilityHorizon(unittest.TestCase):

    def test_horizon_is_finite(self):
        a = w(f=1.0, A=1.0, sigma=sine)
        h = identifiability_horizon(a, threshold=0.5)
        self.assertGreater(h, 0.0)
        self.assertLess(h, 5.0)


if __name__ == "__main__":
    unittest.main()
