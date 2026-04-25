"""
The New Code visual debugger.

A process is not a thread; it's an ongoing computation with its own internal
time τ. You cannot read a New Code program by looking at a line at a time —
you have to watch it unfold. The debugger is the organ for that watching.

What this module provides:

    * ``Tracer`` — a recording surface. Wrap a ``Process`` or an ``Entangled``
      pair and every sample / transformation becomes an event on a shared
      trace. The instrumentation is non-intrusive: the wrapped object keeps
      its identity, its type, and its public API.

    * ``DebuggerServer`` — a stdlib-only HTTP + Server-Sent-Events server
      that streams the trace to a browser. No external dependencies. Runs
      on a background thread; the REPL remains interactive while it runs.

    * An embedded SVG frontend (``_INDEX_HTML``). Processes become
      horizontal bands; their realisations are plotted against τ; entangled
      pairs sit as their own rows and flash when a transform propagates.
      One file, vanilla JS, no build step.

This is the v0.01 debugger: it will be wrong in places, and it is honest
about being a visualisation rather than a proof. But the τ on ``Process``
and the ``_history`` on ``Entangled`` exist specifically so that this can
be built; this module is those fields paying rent.
"""

from __future__ import annotations

import html
import json
import queue
import threading
import time
import webbrowser
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Dict, List, Optional

from .entanglement import Entangled
from .process import Process
from .wave import W


# -----------------------------------------------------------------------------
# Event model.
# -----------------------------------------------------------------------------
#
# The debugger is a stream of events. Each event is a small JSON-serialisable
# dict with a ``type`` tag. The UI consumes them in order and mutates its own
# state tables; the server keeps an append-only log so late-joining clients
# can catch up.

def _wave_to_json(v: W, t: float = 0.0) -> Dict[str, Any]:
    """A 𝕎 serialised for the UI, realised *at* the moment it was observed.

    The 𝕎 type is the static description of a pattern of change; what you
    see at any given moment is ``realise(τ)``, not the descriptor itself.
    This was the bug in v0.01 of the debugger — it always realised at 0.
    """
    return {
        "kind": "W",
        "f": v.f,
        "A": v.A,
        "phi": v.phi,
        "sigma": v.sigma.name,
        "realised": v.realise(t),
    }


def _value_to_json(v: Any, t: float = 0.0) -> Any:
    if isinstance(v, W):
        return _wave_to_json(v, t)
    if isinstance(v, (int, float, bool)) or v is None:
        return v
    if isinstance(v, (list, tuple)):
        return [_value_to_json(x, t) for x in v]
    return {"kind": "repr", "value": repr(v)}


# -----------------------------------------------------------------------------
# Sub-step ribbons.
# -----------------------------------------------------------------------------
#
# A process advances τ by 1/rate per sample. If the rate is the same as the
# waveform's frequency (the default for ``every``), successive samples land
# at the same phase of the cycle — the plot would be flat even though the
# pattern underneath is cycling. To make the shape of the waveform visible
# in the debugger we attach a short ``ribbon`` to every 𝕎 sample: a dense
# set of realisations over the τ interval that the sample covers.
#
# This is a visualisation concern, not a semantic one. The language still
# says: 𝕎 is a descriptor, τ is the clock, ``realise(τ)`` is the scalar.

_RIBBON_POINTS = 32


def _wave_ribbon(v: W, tau_before: float, tau_after: float,
                 n: int = _RIBBON_POINTS) -> List[List[float]]:
    if tau_after <= tau_before:
        tau_after = tau_before + 1e-9
    span = tau_after - tau_before
    out: List[List[float]] = []
    for k in range(n):
        u = k / (n - 1) if n > 1 else 0.0
        t = tau_before + span * u
        out.append([t, v.realise(t)])
    return out


# -----------------------------------------------------------------------------
# Tracer.
# -----------------------------------------------------------------------------

@dataclass
class TrackedProcess:
    name: str
    process: Process
    samples: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class TrackedEntangled:
    name: str
    pair: Entangled
    firings: List[Dict[str, Any]] = field(default_factory=list)


class Tracer:
    """The recording surface for a debugger session.

    A ``Tracer`` owns a list of tracked objects and a list of subscribers.
    When an event fires, each subscriber gets it on its own ``queue.Queue``.
    The HTTP server's SSE handlers are subscribers; so is any test that
    wants to assert on the trace directly.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.processes: Dict[str, TrackedProcess] = {}
        self.entangled: Dict[str, TrackedEntangled] = {}
        self.log: List[Dict[str, Any]] = []
        self._subscribers: List["queue.Queue[Dict[str, Any]]"] = []
        self._t0 = time.monotonic()

    # -- subscription -----------------------------------------------------

    def subscribe(self) -> "queue.Queue[Dict[str, Any]]":
        q: "queue.Queue[Dict[str, Any]]" = queue.Queue()
        with self._lock:
            for event in self.log:
                q.put(event)
            self._subscribers.append(q)
        return q

    def unsubscribe(self, q: "queue.Queue[Dict[str, Any]]") -> None:
        with self._lock:
            if q in self._subscribers:
                self._subscribers.remove(q)

    def _emit(self, event: Dict[str, Any]) -> None:
        event["t"] = time.monotonic() - self._t0
        with self._lock:
            self.log.append(event)
            subs = list(self._subscribers)
        for q in subs:
            q.put(event)

    # -- tracking ---------------------------------------------------------

    def track_process(self, name: str, p: Process) -> Process:
        """Wrap ``p.sample`` so every sample becomes an event.

        The wrapped object keeps its identity: callers that already hold a
        reference to ``p`` continue to see samples propagate through the
        trace. The mechanism is an instance-level override of ``sample``.
        """
        if name in self.processes:
            return self.processes[name].process
        tp = TrackedProcess(name=name, process=p)
        self.processes[name] = tp

        original_sample = p.sample

        def sample(*args: Any) -> Any:
            tau_before = p.tau
            value = original_sample(*args)
            tau_after = p.tau
            payload = {
                "type": "sample",
                "process": name,
                "tau": tau_before,
                "tau_after": tau_after,
                # Realise at τ_before — the moment the step function saw
                # the world. This is what the band should plot.
                "value": _value_to_json(value, t=tau_before),
            }
            # For 𝕎 samples, attach a dense ribbon of realisations over
            # [τ_before, τ_after) so the UI can draw the waveform's shape
            # through this step, not just a single point.
            if isinstance(value, W):
                payload["ribbon"] = _wave_ribbon(value, tau_before, tau_after)
            tp.samples.append(payload)
            self._emit(payload)
            return value

        p.sample = sample  # type: ignore[method-assign]

        self._emit({
            "type": "process_registered",
            "process": name,
            "rate": p.rate,
            "intent": p.intent,
            "initial_tau": p.tau,
        })
        return p

    def track_entangled(self, name: str, e: Entangled) -> Entangled:
        """Wrap ``e.transform_left`` / ``transform_right`` so every firing
        becomes an event. The returned ``Entangled`` is the same object.
        """
        if name in self.entangled:
            return self.entangled[name].pair
        te = TrackedEntangled(name=name, pair=e)
        self.entangled[name] = te

        original_left = e.transform_left
        original_right = e.transform_right

        def transform_left(f: Callable[[Any], Any]) -> Entangled:
            before_left = e.left
            before_right = e.right
            result = original_left(f)
            # transform_left returns a new Entangled. We mirror the new
            # state onto the tracked object so the visual refers to a
            # stable identity. This matches how the REPL actually binds
            # new pair states over the old name when the user reassigns.
            e.left = result.left
            e.right = result.right
            e._history[:] = result._history
            payload = {
                "type": "entangle_fire",
                "pair": name,
                "side": "left",
                "op": getattr(f, "__name__", repr(f)),
                "before": {"left": _value_to_json(before_left),
                           "right": _value_to_json(before_right)},
                "after":  {"left": _value_to_json(e.left),
                           "right": _value_to_json(e.right)},
            }
            te.firings.append(payload)
            self._emit(payload)
            return e

        def transform_right(f: Callable[[Any], Any]) -> Entangled:
            before_left = e.left
            before_right = e.right
            result = original_right(f)
            e.left = result.left
            e.right = result.right
            e._history[:] = result._history
            payload = {
                "type": "entangle_fire",
                "pair": name,
                "side": "right",
                "op": getattr(f, "__name__", repr(f)),
                "before": {"left": _value_to_json(before_left),
                           "right": _value_to_json(before_right)},
                "after":  {"left": _value_to_json(e.left),
                           "right": _value_to_json(e.right)},
            }
            te.firings.append(payload)
            self._emit(payload)
            return e

        e.transform_left = transform_left   # type: ignore[method-assign]
        e.transform_right = transform_right  # type: ignore[method-assign]

        self._emit({
            "type": "entangle_registered",
            "pair": name,
            "via": getattr(e.via, "__name__", repr(e.via)),
            "left": _value_to_json(e.left),
            "right": _value_to_json(e.right),
        })
        return e

    def track_scope(self, scope: Dict[str, Any]) -> int:
        """Walk a dict (typically the REPL scope) and wrap every ``Process``
        and ``Entangled`` in it. Returns the number of new objects tracked.

        Existing tracked names are skipped; this is safe to call repeatedly
        as the user defines new values in the REPL.
        """
        count = 0
        for name, value in list(scope.items()):
            if name.startswith("_"):
                continue
            if isinstance(value, Process) and name not in self.processes:
                self.track_process(name, value)
                count += 1
            elif isinstance(value, Entangled) and name not in self.entangled:
                self.track_entangled(name, value)
                count += 1
        return count

    # -- snapshot ---------------------------------------------------------

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "processes": [
                    {
                        "name": tp.name,
                        "rate": tp.process.rate,
                        "tau": tp.process.tau,
                        "intent": tp.process.intent,
                        "samples": list(tp.samples),
                    }
                    for tp in self.processes.values()
                ],
                "entangled": [
                    {
                        "name": te.name,
                        "via": getattr(te.pair.via, "__name__", repr(te.pair.via)),
                        "left": _value_to_json(te.pair.left),
                        "right": _value_to_json(te.pair.right),
                        "firings": list(te.firings),
                    }
                    for te in self.entangled.values()
                ],
            }


# -----------------------------------------------------------------------------
# HTTP + SSE server.
# -----------------------------------------------------------------------------

class _Handler(BaseHTTPRequestHandler):
    # Populated by the server subclass.
    tracer: Tracer = None  # type: ignore[assignment]

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        # Silence the default access log; the REPL's stdout is precious.
        return

    def _send(self, status: int, body: bytes, content_type: str,
              extra_headers: Optional[Dict[str, str]] = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if extra_headers:
            for k, v in extra_headers.items():
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path == "/" or path == "/index.html":
            body = _INDEX_HTML.encode("utf-8")
            self._send(200, body, "text/html; charset=utf-8")
            return
        if path == "/snapshot":
            body = json.dumps(self.tracer.snapshot()).encode("utf-8")
            self._send(200, body, "application/json")
            return
        if path == "/events":
            self._serve_events()
            return
        self._send(404, b"not found", "text/plain")

    def _serve_events(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        q = self.tracer.subscribe()
        try:
            # Hello packet so the browser knows the stream is live even
            # before any event arrives.
            self.wfile.write(b": connected\n\n")
            self.wfile.flush()
            while True:
                try:
                    event = q.get(timeout=15.0)
                except queue.Empty:
                    # Keepalive comment so intermediaries don't reap us.
                    self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
                    continue
                payload = json.dumps(event).encode("utf-8")
                self.wfile.write(b"data: " + payload + b"\n\n")
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            # Client went away. Normal.
            pass
        finally:
            self.tracer.unsubscribe(q)


class DebuggerServer:
    """HTTP + SSE server wrapping a ``Tracer``.

    Starts on a background thread so the REPL stays responsive. The
    running server can be inspected via ``.url`` and stopped with
    ``.stop()``. Re-calling ``.start()`` on a stopped server is fine.
    """

    def __init__(self, tracer: Tracer, host: str = "127.0.0.1",
                 port: int = 0) -> None:
        self.tracer = tracer
        self.host = host
        self.port = port
        self._httpd: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    @property
    def url(self) -> Optional[str]:
        if self._httpd is None:
            return None
        host, port = self._httpd.server_address[:2]
        return f"http://{host}:{port}/"

    def start(self) -> str:
        if self._httpd is not None:
            return self.url or ""
        tracer = self.tracer

        class BoundHandler(_Handler):
            pass

        BoundHandler.tracer = tracer
        self._httpd = ThreadingHTTPServer((self.host, self.port), BoundHandler)
        self._thread = threading.Thread(
            target=self._httpd.serve_forever, name="newcode-debugger", daemon=True
        )
        self._thread.start()
        return self.url or ""

    def stop(self) -> None:
        if self._httpd is None:
            return
        self._httpd.shutdown()
        self._httpd.server_close()
        self._httpd = None
        self._thread = None

    def open_browser(self) -> None:
        url = self.url
        if url:
            webbrowser.open(url)


# -----------------------------------------------------------------------------
# Convenience: a module-level singleton for the REPL.
# -----------------------------------------------------------------------------

_shared_tracer: Optional[Tracer] = None
_shared_server: Optional[DebuggerServer] = None


def shared_tracer() -> Tracer:
    global _shared_tracer
    if _shared_tracer is None:
        _shared_tracer = Tracer()
    return _shared_tracer


def start_debugger(scope: Optional[Dict[str, Any]] = None,
                   port: int = 0, open_browser: bool = True) -> DebuggerServer:
    """Start (or return the existing) debugger server, auto-tracking anything
    visible in ``scope``. Designed to be called from the REPL's :debug hook.
    """
    global _shared_server
    tracer = shared_tracer()
    if scope is not None:
        tracer.track_scope(scope)
    if _shared_server is None:
        _shared_server = DebuggerServer(tracer, port=port)
        _shared_server.start()
        if open_browser:
            _shared_server.open_browser()
    elif scope is not None:
        # Already running — re-scan in case new bindings appeared.
        tracer.track_scope(scope)
    return _shared_server


# -----------------------------------------------------------------------------
# Frontend.
# -----------------------------------------------------------------------------

_INDEX_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>New Code — debugger</title>
<style>
  :root {
    --bg: #0b0d10;
    --fg: #e7e9ec;
    --dim: #7a8088;
    --grid: #1b1e22;
    --band: #12151a;
    --band-alt: #0f1216;
    --accent: #8ab4ff;
    --fire: #ffcf5a;
    --fire-strong: #ff7a59;
    --good: #7ed6a5;
    --edge: #2a2e34;
  }
  * { box-sizing: border-box; }
  html, body {
    margin: 0; padding: 0;
    background: var(--bg); color: var(--fg);
    font: 13px/1.45 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    height: 100%;
  }
  header {
    padding: 10px 16px;
    border-bottom: 1px solid var(--edge);
    display: flex; align-items: baseline; gap: 16px;
  }
  header h1 { margin: 0; font-size: 13px; font-weight: 600; letter-spacing: 0.02em; }
  header .sub { color: var(--dim); }
  header .status { margin-left: auto; color: var(--dim); }
  header .status.live { color: var(--good); }
  main { padding: 12px 16px 40px; }
  .empty {
    color: var(--dim); padding: 40px; text-align: center;
    border: 1px dashed var(--edge); border-radius: 4px;
    margin-top: 24px;
  }
  .row {
    background: var(--band); border: 1px solid var(--edge);
    border-radius: 4px; margin-bottom: 10px;
    overflow: hidden;
  }
  .row:nth-child(even) { background: var(--band-alt); }
  .row .head {
    padding: 8px 12px; display: flex; align-items: baseline; gap: 12px;
    border-bottom: 1px solid var(--edge);
  }
  .row .head .name { font-weight: 600; }
  .row .head .kind {
    font-size: 11px; color: var(--dim); text-transform: uppercase;
    letter-spacing: 0.08em;
  }
  .row .head .meta { color: var(--dim); margin-left: auto; font-size: 11px; }
  .row .body { padding: 0; }
  svg { display: block; width: 100%; height: 120px; }
  .pair-body {
    padding: 10px 12px; display: grid;
    grid-template-columns: 1fr auto 1fr;
    align-items: center; gap: 12px;
  }
  .pair-side {
    background: #0a0c0f; border: 1px solid var(--edge);
    border-radius: 4px; padding: 8px 10px;
  }
  .pair-side.fire { border-color: var(--fire); box-shadow: 0 0 12px rgba(255, 207, 90, 0.25); }
  .pair-link {
    height: 2px; background: var(--edge); position: relative;
    transition: background 180ms linear;
  }
  .pair-link.fire { background: var(--fire-strong); box-shadow: 0 0 8px var(--fire-strong); }
  .pair-link::before, .pair-link::after {
    content: ""; position: absolute; top: -3px;
    width: 8px; height: 8px; border-radius: 50%;
    background: var(--edge); transition: background 180ms linear;
  }
  .pair-link::before { left: -4px; }
  .pair-link::after  { right: -4px; }
  .pair-link.fire::before, .pair-link.fire::after { background: var(--fire-strong); }
  .k { color: var(--dim); }
  .v { color: var(--fg); }
  .pair-op {
    padding: 10px 12px; color: var(--dim); font-size: 11px;
    border-top: 1px solid var(--edge);
  }
  .pair-op .op-latest { color: var(--fg); }
  footer {
    color: var(--dim); padding: 12px 16px;
    border-top: 1px solid var(--edge); font-size: 11px;
  }
</style>
</head>
<body>
<header>
  <h1>New Code — debugger</h1>
  <span class="sub">processes unfold against their own τ</span>
  <span class="status" id="status">connecting…</span>
</header>
<main>
  <div id="root"></div>
  <div id="empty" class="empty" style="display:none">
    Nothing to show yet. In the REPL, define a process with <code>every(...)</code>
    or an entangled pair with <code>entangle(...)</code>, then call
    <code>:debug</code> again to register them, or call <code>unfold(p, 20)</code>
    to see samples land here.
  </div>
</main>
<footer id="footer">—</footer>
<script>
(() => {
  const root = document.getElementById("root");
  const empty = document.getElementById("empty");
  const status = document.getElementById("status");
  const footer = document.getElementById("footer");

  const processes = new Map();  // name -> { rate, tau, intent, samples: [] }
  const pairs = new Map();      // name -> { via, left, right, firings: [] }

  const MAX_SAMPLES = 400;

  function setStatus(text, live) {
    status.textContent = text;
    status.classList.toggle("live", !!live);
  }

  function updateFooter() {
    const nP = processes.size, nE = pairs.size;
    const totalSamples = [...processes.values()]
      .reduce((s, p) => s + p.samples.length, 0);
    const totalFirings = [...pairs.values()]
      .reduce((s, p) => s + p.firings.length, 0);
    footer.textContent =
      `${nP} process${nP === 1 ? "" : "es"}, ` +
      `${nE} entangled pair${nE === 1 ? "" : "s"} · ` +
      `${totalSamples} samples, ${totalFirings} firings`;
  }

  function fmt(n, d = 3) {
    if (n === null || n === undefined || Number.isNaN(n)) return "—";
    const a = Math.abs(n);
    if (a !== 0 && (a < 0.001 || a >= 10000)) return n.toExponential(2);
    return Number(n.toFixed(d)).toString();
  }

  function waveText(v) {
    if (!v || v.kind !== "W") return "—";
    return `⟨f=${fmt(v.f)}, A=${fmt(v.A)}, φ=${fmt(v.phi)}, σ=${v.sigma}⟩`;
  }

  function valueText(v) {
    if (v === null || v === undefined) return "—";
    if (typeof v === "number") return fmt(v);
    if (typeof v === "boolean") return v ? "true" : "false";
    if (Array.isArray(v)) return "[" + v.map(valueText).join(", ") + "]";
    if (v && v.kind === "W") return waveText(v);
    if (v && v.kind === "repr") return v.value;
    return String(v);
  }

  function valueScalar(v) {
    // A scalar we can plot on the y-axis.
    if (typeof v === "number") return v;
    if (v && v.kind === "W") return v.realised;
    return null;
  }

  // ---- Rendering: process bands -----------------------------------------

  function ensureProcessRow(name) {
    let row = document.getElementById("proc-" + name);
    if (row) return row;
    row = document.createElement("section");
    row.className = "row";
    row.id = "proc-" + name;
    row.innerHTML = `
      <div class="head">
        <span class="name"></span>
        <span class="kind">process</span>
        <span class="meta"></span>
      </div>
      <div class="body">
        <svg viewBox="0 0 800 120" preserveAspectRatio="none"
             xmlns="http://www.w3.org/2000/svg">
          <rect x="0" y="0" width="800" height="120" fill="transparent"/>
          <line class="axis" x1="0" y1="60" x2="800" y2="60"
                stroke="var(--grid)" stroke-width="1"/>
          <polyline class="trace" fill="none" stroke="var(--accent)"
                    stroke-width="1.5" points=""/>
          <g class="markers"></g>
          <text class="current" x="790" y="18" text-anchor="end"
                fill="var(--dim)" font-size="11"></text>
        </svg>
      </div>`;
    root.appendChild(row);
    return row;
  }

  function renderProcess(name, state) {
    const row = ensureProcessRow(name);
    row.querySelector(".name").textContent = name;
    const intent = state.intent ? ` · "${state.intent}"` : "";
    row.querySelector(".meta").textContent =
      `rate=${fmt(state.rate)} · τ=${fmt(state.tau)}${intent}`;

    const svg = row.querySelector("svg");
    const poly = svg.querySelector(".trace");
    const current = svg.querySelector(".current");

    const samples = state.samples.slice(-MAX_SAMPLES);
    if (samples.length === 0) {
      poly.setAttribute("points", "");
      current.textContent = "";
      return;
    }

    // Build a dense list of (τ, y) points. Prefer a sample's ribbon if it
    // has one — that's the waveform's shape over the step. Fall back to
    // a single (τ, realise(τ)) point per sample for non-𝕎 values.
    const dense = [];
    let minTau = Infinity, maxTau = -Infinity;
    let minY = Infinity, maxY = -Infinity;
    for (const s of samples) {
      if (Array.isArray(s.ribbon) && s.ribbon.length > 0) {
        for (const [t, y] of s.ribbon) {
          if (t < minTau) minTau = t;
          if (t > maxTau) maxTau = t;
          if (y < minY) minY = y;
          if (y > maxY) maxY = y;
          dense.push([t, y]);
        }
      } else {
        const y = valueScalar(s.value);
        if (y === null) continue;
        const t = s.tau;
        if (t < minTau) minTau = t;
        if (t > maxTau) maxTau = t;
        if (y < minY) minY = y;
        if (y > maxY) maxY = y;
        dense.push([t, y]);
      }
    }
    if (dense.length === 0) {
      poly.setAttribute("points", "");
      current.textContent = "";
      return;
    }
    if (!isFinite(minTau) || !isFinite(maxTau) || minTau === maxTau) {
      minTau = 0; maxTau = 1;
    }
    if (!isFinite(minY) || !isFinite(maxY)) { minY = -1; maxY = 1; }
    if (minY === maxY) { minY -= 0.5; maxY += 0.5; }
    const pad = (maxY - minY) * 0.1;
    minY -= pad; maxY += pad;

    const W = 800, H = 120;
    const points = dense.map(([t, y]) => {
      const px = ((t - minTau) / (maxTau - minTau)) * W;
      const py = H - ((y - minY) / (maxY - minY)) * H;
      return `${px.toFixed(1)},${py.toFixed(1)}`;
    });
    poly.setAttribute("points", points.join(" "));

    const latest = samples[samples.length - 1];
    current.textContent = `latest: ${valueText(latest.value)} @ τ=${fmt(latest.tau)}`;
  }

  // ---- Rendering: entangled pairs ---------------------------------------

  function ensurePairRow(name) {
    let row = document.getElementById("pair-" + name);
    if (row) return row;
    row = document.createElement("section");
    row.className = "row";
    row.id = "pair-" + name;
    row.innerHTML = `
      <div class="head">
        <span class="name"></span>
        <span class="kind">entangled</span>
        <span class="meta"></span>
      </div>
      <div class="pair-body">
        <div class="pair-side left">
          <div class="k">left</div><div class="v"></div>
        </div>
        <div class="pair-link"></div>
        <div class="pair-side right">
          <div class="k">right</div><div class="v"></div>
        </div>
      </div>
      <div class="pair-op"><span class="op-latest">—</span></div>`;
    root.appendChild(row);
    return row;
  }

  function renderPair(name, state) {
    const row = ensurePairRow(name);
    row.querySelector(".name").textContent = name;
    row.querySelector(".meta").textContent = `via ${state.via}`;
    row.querySelector(".pair-side.left .v").textContent = valueText(state.left);
    row.querySelector(".pair-side.right .v").textContent = valueText(state.right);

    const op = row.querySelector(".op-latest");
    if (state.firings.length === 0) {
      op.textContent = "no firings yet";
    } else {
      const f = state.firings[state.firings.length - 1];
      op.textContent = `last firing — ${f.side} · ${f.op}`;
    }
  }

  function flashPair(name, side) {
    const row = document.getElementById("pair-" + name);
    if (!row) return;
    const link = row.querySelector(".pair-link");
    const sideEl = row.querySelector(".pair-side." + side);
    link.classList.add("fire");
    sideEl.classList.add("fire");
    setTimeout(() => {
      link.classList.remove("fire");
      sideEl.classList.remove("fire");
    }, 450);
  }

  function refreshAll() {
    const anything = processes.size + pairs.size;
    empty.style.display = anything ? "none" : "";
    // Render in insertion order.
    for (const [name, state] of processes) renderProcess(name, state);
    for (const [name, state] of pairs)     renderPair(name, state);
    updateFooter();
  }

  // ---- Event pipeline ---------------------------------------------------

  function ingest(event) {
    switch (event.type) {
      case "process_registered": {
        if (!processes.has(event.process)) {
          processes.set(event.process, {
            rate: event.rate, tau: event.initial_tau,
            intent: event.intent, samples: [],
          });
        }
        renderProcess(event.process, processes.get(event.process));
        break;
      }
      case "sample": {
        const p = processes.get(event.process);
        if (!p) break;
        p.tau = event.tau_after;
        p.samples.push(event);
        if (p.samples.length > MAX_SAMPLES * 2) {
          p.samples.splice(0, p.samples.length - MAX_SAMPLES);
        }
        renderProcess(event.process, p);
        break;
      }
      case "entangle_registered": {
        if (!pairs.has(event.pair)) {
          pairs.set(event.pair, {
            via: event.via, left: event.left, right: event.right,
            firings: [],
          });
        }
        renderPair(event.pair, pairs.get(event.pair));
        break;
      }
      case "entangle_fire": {
        const p = pairs.get(event.pair);
        if (!p) break;
        p.left = event.after.left;
        p.right = event.after.right;
        p.firings.push(event);
        renderPair(event.pair, p);
        flashPair(event.pair, event.side);
        break;
      }
    }
    updateFooter();
    if (processes.size + pairs.size > 0) empty.style.display = "none";
  }

  // Initial snapshot fetch (in case the SSE stream starts mid-session).
  fetch("/snapshot").then(r => r.json()).then(snap => {
    for (const p of snap.processes) {
      processes.set(p.name, {
        rate: p.rate, tau: p.tau, intent: p.intent, samples: p.samples,
      });
    }
    for (const e of snap.entangled) {
      pairs.set(e.name, {
        via: e.via, left: e.left, right: e.right, firings: e.firings,
      });
    }
    refreshAll();
  }).catch(() => { /* SSE will deliver. */ });

  // Live stream.
  const es = new EventSource("/events");
  es.onopen = () => setStatus("live", true);
  es.onerror = () => setStatus("disconnected", false);
  es.onmessage = (ev) => {
    try {
      const event = JSON.parse(ev.data);
      ingest(event);
    } catch (err) {
      // Ignore malformed packets; keepalives arrive as empty.
    }
  };

  refreshAll();
})();
</script>
</body>
</html>
"""
