"""
The New Code browser playground.

A stdlib-only HTTP server that serves a single-page web app where you can:

  * write or paste a `.nc` score in the left pane
  * pick a compilation mode (offline / online / snapshot)
  * click **Compile** — the server parses the score, compiles each
    declaration through the chosen backend, and reports per-declaration
    results (provenance, body source, errors, OfflineHoleError fix-its)
  * click **Run** to evaluate the most recent script in a fresh scope
    and see the captured output buffer
  * click **Accept** on a compiled body to persist it to a SnapshotStore
    keyed by intent_hash — exactly the same workflow as the REPL
    `:accept` command

No build step. No external dependencies. Vanilla JavaScript front-end
served as a single embedded HTML string. Run as:

    python -m newcode.playground

The playground is the browser-native counterpart of the REPL. It exists
so a user can try New Code without installing an editor or learning the
REPL's command surface, and so the approval workflow is reachable in
two clicks.
"""

from __future__ import annotations

import json
import sys
import threading
import traceback
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Dict, List, Optional, Tuple

from . import stdlib
from .compiler import (
    Compiled,
    Compiler,
    OfflineHoleError,
    OFFLINE,
    ONLINE,
    SNAPSHOT,
    SnapshotStore,
)
from .parser import (
    Extern,
    Function,
    Import,
    Let,
    Module,
)
from .parser import Process as ProcessDecl
from .parser import parse as parse_score
from . import expr as expr_module


# -----------------------------------------------------------------------------
# Compile / run engine.
# -----------------------------------------------------------------------------

class PlaygroundEngine:
    """The headless half of the playground.

    Holds the most recent parsed declarations, the most recent compile
    results, and the current scope. The HTTP layer is a thin shell over
    this object so it is straightforwardly testable.
    """

    def __init__(
        self,
        mode: str = OFFLINE,
        snapshot_store: Optional[SnapshotStore] = None,
    ):
        self.snapshot_store = (
            snapshot_store if snapshot_store is not None else SnapshotStore()
        )
        self.compiler = Compiler(mode=mode, snapshot_store=self.snapshot_store)
        self.scope: Dict[str, Any] = stdlib.build_scope()
        # name -> Compiled artefact (most recent compile of that name).
        self.compiled: Dict[str, Compiled] = {}
        # name -> the source declaration (for re-accepting).
        self.declarations: Dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Mode

    def set_mode(self, mode: str) -> None:
        if mode not in (OFFLINE, ONLINE, SNAPSHOT):
            raise ValueError(f"unknown mode: {mode}")
        self.compiler = Compiler(mode=mode, snapshot_store=self.snapshot_store)

    @property
    def mode(self) -> str:
        return self.compiler.mode

    # ------------------------------------------------------------------
    # Compile

    def compile_source(self, source: str) -> Dict[str, Any]:
        """Parse and compile ``source``, returning a JSON-serialisable
        result dict the front-end can render directly."""
        out: Dict[str, Any] = {
            "mode": self.compiler.mode,
            "results": [],
            "parse_error": None,
        }
        try:
            decls = parse_score(source)
        except Exception as exc:  # noqa: BLE001
            out["parse_error"] = str(exc)
            return out

        # Reset scope so two runs of compile() are independent.
        self.scope = stdlib.build_scope()
        self.compiled.clear()
        self.declarations.clear()

        for decl in decls:
            entry = self._handle_decl(decl)
            if entry is not None:
                out["results"].append(entry)
        return out

    def _handle_decl(self, decl: Any) -> Optional[Dict[str, Any]]:
        cls = decl.__class__.__name__
        if cls == "Module":
            # Recurse into module — flat for the v1.0 playground.
            inner: List[Dict[str, Any]] = []
            for sub in decl.declarations:
                e = self._handle_decl(sub)
                if e is not None:
                    inner.append(e)
            return {
                "kind": "module",
                "name": decl.name,
                "inner": inner,
            }
        if cls == "Import":
            try:
                mod = stdlib.host_load(decl.path[5:] if decl.path.startswith("host.") else decl.path)
                self.scope[decl.alias or decl.path.split(".")[-1]] = mod
                return {
                    "kind": "import",
                    "path": decl.path,
                    "alias": decl.alias,
                    "ok": True,
                }
            except Exception as exc:  # noqa: BLE001
                return {
                    "kind": "import",
                    "path": decl.path,
                    "alias": decl.alias,
                    "ok": False,
                    "error": str(exc),
                }
        if cls == "Extern":
            try:
                exec(compile(decl.body, "<extern>", "exec"), self.scope)
                return {"kind": "extern", "language": decl.language, "ok": True}
            except Exception as exc:  # noqa: BLE001
                return {
                    "kind": "extern",
                    "language": decl.language,
                    "ok": False,
                    "error": str(exc),
                }
        if cls == "Let":
            try:
                value = self._eval_let(decl)
                self.scope[decl.name] = value
                return {
                    "kind": "let",
                    "name": decl.name,
                    "ok": True,
                    "repr": _safe_repr(value),
                }
            except Exception as exc:  # noqa: BLE001
                return {
                    "kind": "let",
                    "name": decl.name,
                    "ok": False,
                    "error": str(exc),
                }
        if cls in ("Function", "Process"):
            return self._compile_callable(decl)
        return None

    def _eval_let(self, decl: Let) -> Any:
        # Try the New Code expression grammar first.
        try:
            return expr_module.evaluate_source(decl.expression, self.scope)
        except (expr_module.ParseError, expr_module.LexError):
            # Fall through to Python eval.
            pass
        try:
            return eval(decl.expression, self.scope)
        except SyntaxError:
            exec(decl.expression, self.scope)
            return self.scope.get(decl.name)

    def _compile_callable(self, decl: Any) -> Dict[str, Any]:
        try:
            compiled = self.compiler.compile(decl, extra_scope=self.scope)
        except OfflineHoleError as exc:
            return {
                "kind": decl.__class__.__name__.lower(),
                "name": decl.name,
                "ok": False,
                "error_kind": "OfflineHoleError",
                "error": str(exc),
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "kind": decl.__class__.__name__.lower(),
                "name": decl.name,
                "ok": False,
                "error_kind": exc.__class__.__name__,
                "error": str(exc),
            }

        # Bind the callable into the scope so subsequent decls / `run` can
        # call it. Compiled itself is callable (delegates to callable_).
        self.scope[decl.name] = compiled
        self.compiled[decl.name] = compiled
        self.declarations[decl.name] = decl

        return {
            "kind": decl.__class__.__name__.lower(),
            "name": decl.name,
            "ok": True,
            "src": getattr(compiled, "source", "") or "",
            "provenance": _provenance_to_json(compiled),
        }

    # ------------------------------------------------------------------
    # Accept / reject

    def accept(self, name: str) -> Dict[str, Any]:
        compiled = self.compiled.get(name)
        decl = self.declarations.get(name)
        if compiled is None or decl is None:
            return {"ok": False, "error": f"unknown declaration: {name}"}
        try:
            from .compiler import intent_hash
            ihash = intent_hash(decl)
            prov = getattr(compiled, "provenance", None)
            self.snapshot_store.put(
                ihash,
                source=getattr(compiled, "source", "") or "",
                model=(getattr(prov, "model", None) or "") if prov else "",
                decl_name=name,
                accepted=True,
            )
            if prov is not None:
                prov.accepted = True
            return {
                "ok": True,
                "intent_hash": ihash,
                "snapshot_path": str(getattr(self.snapshot_store, "path", "")),
            }
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}

    def reject(self, name: str) -> Dict[str, Any]:
        decl = self.declarations.get(name)
        if decl is None:
            return {"ok": False, "error": f"unknown declaration: {name}"}
        try:
            from .compiler import intent_hash
            ihash = intent_hash(decl)
            self.snapshot_store.remove(ihash)
            return {"ok": True, "intent_hash": ihash}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}

    # ------------------------------------------------------------------
    # Run an arbitrary expression in the current scope

    def run_expression(self, source: str) -> Dict[str, Any]:
        # Clear the IO buffer so each Run starts fresh.
        try:
            stdlib.io_clear()
        except Exception:  # noqa: BLE001
            pass

        try:
            value = expr_module.evaluate_source(source, self.scope)
            return {
                "ok": True,
                "repr": _safe_repr(value),
                "buffer": stdlib.io_buffer(),
            }
        except (expr_module.ParseError, expr_module.LexError):
            pass
        except Exception as exc:  # noqa: BLE001
            return {
                "ok": False,
                "error": str(exc),
                "trace": traceback.format_exc(limit=4),
                "buffer": stdlib.io_buffer(),
            }

        # Fall back to Python eval / exec.
        try:
            value = eval(source, self.scope)
            return {
                "ok": True,
                "repr": _safe_repr(value),
                "buffer": stdlib.io_buffer(),
            }
        except SyntaxError:
            try:
                exec(source, self.scope)
                return {
                    "ok": True,
                    "repr": "",
                    "buffer": stdlib.io_buffer(),
                }
            except Exception as exc:  # noqa: BLE001
                return {
                    "ok": False,
                    "error": str(exc),
                    "trace": traceback.format_exc(limit=4),
                    "buffer": stdlib.io_buffer(),
                }
        except Exception as exc:  # noqa: BLE001
            return {
                "ok": False,
                "error": str(exc),
                "trace": traceback.format_exc(limit=4),
                "buffer": stdlib.io_buffer(),
            }


# -----------------------------------------------------------------------------
# JSON serialisation helpers.
# -----------------------------------------------------------------------------

def _safe_repr(value: Any) -> str:
    try:
        return repr(value)
    except Exception:  # noqa: BLE001
        return f"<unrepresentable {type(value).__name__}>"


def _provenance_to_json(compiled: Compiled) -> Dict[str, Any]:
    p = getattr(compiled, "provenance", None)
    if p is None:
        return {}
    return {
        "backend": p.backend,
        "model": p.model,
        "intent_hash": p.intent_hash,
        "body_hash": p.body_hash,
        "timestamp": p.timestamp,
        "accepted": p.accepted,
        "notes": p.notes,
    }


# -----------------------------------------------------------------------------
# HTTP server.
# -----------------------------------------------------------------------------

class _Handler(BaseHTTPRequestHandler):
    engine: PlaygroundEngine = None  # type: ignore[assignment]

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        # Quiet by default; the playground talks to itself a lot.
        return

    def _send_json(self, status: int, payload: Any) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, status: int, body: str) -> None:
        encoded = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(encoded)

    def _read_body(self) -> Dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:  # noqa: BLE001
            return {}

    # -- routes --------------------------------------------------------

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            self._send_html(200, _INDEX_HTML)
            return
        if path == "/api/state":
            self._send_json(200, {
                "mode": self.engine.mode,
                "snapshot_count": len(self.engine.snapshot_store),
                "snapshot_path": str(getattr(self.engine.snapshot_store, "path", "")),
            })
            return
        self._send_json(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        body = self._read_body()
        if path == "/api/compile":
            source = body.get("source", "")
            self._send_json(200, self.engine.compile_source(source))
            return
        if path == "/api/run":
            source = body.get("source", "")
            self._send_json(200, self.engine.run_expression(source))
            return
        if path == "/api/accept":
            name = body.get("name", "")
            self._send_json(200, self.engine.accept(name))
            return
        if path == "/api/reject":
            name = body.get("name", "")
            self._send_json(200, self.engine.reject(name))
            return
        if path == "/api/mode":
            new_mode = body.get("mode", "")
            try:
                self.engine.set_mode(new_mode)
                self._send_json(200, {"ok": True, "mode": self.engine.mode})
            except Exception as exc:  # noqa: BLE001
                self._send_json(400, {"ok": False, "error": str(exc)})
            return
        self._send_json(404, {"error": "not found"})


class PlaygroundServer:
    """Embedded HTTP server hosting a :class:`PlaygroundEngine`.

    Boots on a background thread so a script that constructs a server
    can keep running. Bind to port 0 to let the OS pick.
    """

    def __init__(
        self,
        engine: Optional[PlaygroundEngine] = None,
        host: str = "127.0.0.1",
        port: int = 0,
    ):
        self.engine = engine or PlaygroundEngine()
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
        engine = self.engine

        class BoundHandler(_Handler):
            pass

        BoundHandler.engine = engine
        self._httpd = ThreadingHTTPServer((self.host, self.port), BoundHandler)
        self._thread = threading.Thread(
            target=self._httpd.serve_forever,
            name="newcode-playground",
            daemon=True,
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
# The single-file front-end.
# -----------------------------------------------------------------------------

_INDEX_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>New Code — Playground</title>
<style>
  :root {
    --bg: #0d1117;
    --panel: #161b22;
    --border: #30363d;
    --fg: #c9d1d9;
    --muted: #8b949e;
    --accent: #ffb454;
    --accent-strong: #f0883e;
    --ok: #56d364;
    --err: #f85149;
    --link: #58a6ff;
    --mono: 'SF Mono', Menlo, Consolas, 'Liberation Mono', monospace;
  }
  * { box-sizing: border-box; }
  html, body { margin: 0; padding: 0; height: 100%; background: var(--bg); color: var(--fg); font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; }
  header { display: flex; align-items: center; gap: 12px; padding: 10px 16px; border-bottom: 1px solid var(--border); background: var(--panel); }
  header .logo { font-weight: 700; letter-spacing: 0.5px; color: var(--accent); font-size: 14px; }
  header .version { color: var(--muted); font-size: 12px; }
  header .spacer { flex: 1; }
  header label { color: var(--muted); font-size: 12px; }
  header select, header button { background: var(--bg); color: var(--fg); border: 1px solid var(--border); border-radius: 4px; padding: 6px 10px; font-size: 12px; cursor: pointer; }
  header button.primary { background: var(--accent-strong); color: #0d1117; border-color: var(--accent-strong); font-weight: 600; }
  header button:hover { border-color: var(--accent); }
  main { display: grid; grid-template-columns: 1fr 1fr; gap: 1px; background: var(--border); height: calc(100% - 49px); }
  .pane { background: var(--bg); display: flex; flex-direction: column; min-height: 0; }
  .pane > .pane-header { padding: 8px 12px; font-size: 11px; text-transform: uppercase; letter-spacing: 0.6px; color: var(--muted); border-bottom: 1px solid var(--border); display: flex; align-items: center; gap: 8px; }
  .pane > .pane-body { flex: 1; overflow: auto; min-height: 0; }
  textarea { width: 100%; height: 100%; background: var(--bg); color: var(--fg); font-family: var(--mono); font-size: 13px; line-height: 1.5; border: none; outline: none; padding: 12px 14px; resize: none; tab-size: 4; }
  .results { padding: 12px; }
  .result { border: 1px solid var(--border); border-radius: 6px; padding: 10px 12px; margin-bottom: 10px; background: var(--panel); }
  .result h3 { margin: 0 0 6px; font-size: 13px; font-family: var(--mono); display: flex; align-items: center; gap: 8px; }
  .badge { font-size: 10px; padding: 2px 6px; border-radius: 10px; background: var(--border); color: var(--muted); font-family: var(--mono); text-transform: uppercase; letter-spacing: 0.4px; }
  .badge.offline { background: #30363d; color: var(--fg); }
  .badge.anthropic { background: #5e3b1c; color: var(--accent); }
  .badge.snapshot { background: #1f3a5f; color: var(--link); }
  .badge.explicit { background: #1d3a25; color: var(--ok); }
  .result pre { background: var(--bg); padding: 8px 10px; border-radius: 4px; margin: 6px 0 0; font-family: var(--mono); font-size: 12px; line-height: 1.45; overflow-x: auto; white-space: pre; color: var(--fg); }
  .result.error { border-color: var(--err); }
  .result.error h3 { color: var(--err); }
  .result .meta { font-family: var(--mono); font-size: 11px; color: var(--muted); margin-top: 6px; }
  .result button { margin-top: 6px; margin-right: 6px; background: transparent; color: var(--link); border: 1px solid var(--border); border-radius: 4px; padding: 3px 8px; font-size: 11px; cursor: pointer; }
  .result button:hover { border-color: var(--link); }
  .result button.accepted { background: #1d3a25; color: var(--ok); border-color: var(--ok); cursor: default; }
  .repl-zone { display: flex; flex-direction: column; gap: 0; min-height: 0; height: 100%; }
  .repl-input { display: flex; gap: 6px; padding: 8px 12px; border-top: 1px solid var(--border); background: var(--panel); align-items: center; }
  .repl-input span { color: var(--accent); font-family: var(--mono); font-size: 13px; }
  .repl-input input { flex: 1; background: var(--bg); color: var(--fg); border: 1px solid var(--border); border-radius: 4px; padding: 6px 10px; font-family: var(--mono); font-size: 13px; outline: none; }
  .repl-input input:focus { border-color: var(--accent); }
  .repl-output { flex: 1; padding: 12px; overflow: auto; font-family: var(--mono); font-size: 12px; line-height: 1.5; }
  .repl-line { white-space: pre-wrap; word-break: break-word; padding: 2px 0; }
  .repl-line.echo { color: var(--accent); }
  .repl-line.err { color: var(--err); }
  .repl-line.muted { color: var(--muted); }
  .footer { padding: 6px 12px; border-top: 1px solid var(--border); background: var(--panel); font-size: 11px; color: var(--muted); display: flex; gap: 12px; }
  .footer .ok { color: var(--ok); }
  .footer .err { color: var(--err); }
  a { color: var(--link); }
</style>
</head>
<body>
<header>
  <span class="logo">New Code</span>
  <span class="version">v1.0 playground</span>
  <span class="spacer"></span>
  <label>mode</label>
  <select id="mode">
    <option value="offline">offline</option>
    <option value="online">online</option>
    <option value="snapshot">snapshot</option>
  </select>
  <button id="compile" class="primary">Compile (⌘⏎)</button>
  <button id="reset">Reset score</button>
</header>
<main>
  <section class="pane">
    <div class="pane-header">Score · first.nc</div>
    <div class="pane-body">
      <textarea id="source" spellcheck="false">※ A 440 Hz tone.
let concert_a : 𝕎 = w(f=440, A=1.0, phi=0.0, sigma=sine)

fn amplify (signal : 𝕎, gain : ℝ) → 𝕎
    intent: 「scale the amplitude of signal by gain while preserving shape」
    forbid: 「do not modify phase」
    ensure: 「output shape equals input shape」
    ≔ ??
</textarea>
    </div>
  </section>
  <section class="pane repl-zone">
    <div class="pane-header">Compile output</div>
    <div class="pane-body">
      <div id="results" class="results">
        <p style="color:var(--muted);font-size:12px;">Press <kbd>⌘⏎</kbd> or click <strong>Compile</strong>. Each declaration's provenance, body, and any errors will land here.</p>
      </div>
    </div>
    <div class="repl-output" id="repl-output">
      <div class="repl-line muted">Ready. Type expressions below — they evaluate in the same scope as your compiled score.</div>
    </div>
    <form class="repl-input" id="repl-form">
      <span>nc&gt;</span>
      <input id="repl-input" autocomplete="off" placeholder="e.g.  amplify(concert_a, 2.0)">
    </form>
    <div class="footer">
      <span>mode: <span id="footer-mode">offline</span></span>
      <span>snapshot: <span id="footer-snap">0 entries</span></span>
      <span class="spacer" style="flex:1"></span>
      <span><a href="https://github.com">GUIDE.md</a> · <a href="https://github.com">SEMANTICS.md</a></span>
    </div>
  </section>
</main>

<script>
const $ = (id) => document.getElementById(id);
const sourceEl = $('source');
const modeEl = $('mode');
const resultsEl = $('results');
const replOutEl = $('repl-output');
const replInputEl = $('repl-input');
const footerMode = $('footer-mode');
const footerSnap = $('footer-snap');

const DEFAULT_SOURCE = sourceEl.value;

async function fetchJSON(url, opts) {
  const res = await fetch(url, opts);
  return await res.json();
}

async function refreshState() {
  const s = await fetchJSON('/api/state');
  modeEl.value = s.mode;
  footerMode.textContent = s.mode;
  footerSnap.textContent = s.snapshot_count + ' entries';
}

modeEl.addEventListener('change', async () => {
  const r = await fetchJSON('/api/mode', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({mode: modeEl.value}),
  });
  if (!r.ok) {
    appendRepl('mode change failed: ' + r.error, 'err');
  } else {
    footerMode.textContent = r.mode;
  }
});

$('reset').addEventListener('click', () => {
  sourceEl.value = DEFAULT_SOURCE;
});

async function compile() {
  resultsEl.innerHTML = '<p style="color:var(--muted);font-size:12px;">Compiling…</p>';
  const r = await fetchJSON('/api/compile', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({source: sourceEl.value}),
  });
  renderResults(r);
  refreshState();
}

function renderResults(r) {
  resultsEl.innerHTML = '';
  if (r.parse_error) {
    const div = document.createElement('div');
    div.className = 'result error';
    div.innerHTML = '<h3>Parse error</h3><pre></pre>';
    div.querySelector('pre').textContent = r.parse_error;
    resultsEl.appendChild(div);
    return;
  }
  if (!r.results || r.results.length === 0) {
    resultsEl.innerHTML = '<p style="color:var(--muted);font-size:12px;">No declarations to compile.</p>';
    return;
  }
  for (const entry of r.results) {
    resultsEl.appendChild(renderEntry(entry));
  }
}

function renderEntry(e) {
  const div = document.createElement('div');
  div.className = 'result' + (e.ok === false ? ' error' : '');

  if (e.kind === 'let') {
    div.innerHTML = `<h3><span class="badge explicit">let</span> ${esc(e.name)}</h3>`;
    if (e.ok) {
      const pre = document.createElement('pre');
      pre.textContent = e.repr;
      div.appendChild(pre);
    } else {
      const pre = document.createElement('pre');
      pre.textContent = e.error;
      div.appendChild(pre);
    }
    return div;
  }

  if (e.kind === 'import') {
    div.innerHTML = `<h3><span class="badge">import</span> ${esc(e.path)}${e.alias ? ' as ' + esc(e.alias) : ''}</h3>`;
    if (!e.ok) {
      const pre = document.createElement('pre');
      pre.textContent = e.error;
      div.appendChild(pre);
    }
    return div;
  }

  if (e.kind === 'extern') {
    div.innerHTML = `<h3><span class="badge">extern ${esc(e.language)}</span></h3>`;
    if (!e.ok) {
      const pre = document.createElement('pre');
      pre.textContent = e.error;
      div.appendChild(pre);
    }
    return div;
  }

  if (e.kind === 'module') {
    div.innerHTML = `<h3><span class="badge">module</span> ${esc(e.name)}</h3>`;
    for (const inner of (e.inner || [])) {
      div.appendChild(renderEntry(inner));
    }
    return div;
  }

  // Function / Process: full provenance + body + accept button.
  const provBadge = e.provenance ? `<span class="badge ${esc(e.provenance.backend)}">${esc(e.provenance.backend)}</span>` : '';
  div.innerHTML = `<h3>${provBadge} ${esc(e.kind)} ${esc(e.name)}</h3>`;
  if (e.ok === false) {
    const pre = document.createElement('pre');
    pre.textContent = (e.error_kind ? '[' + e.error_kind + '] ' : '') + e.error;
    div.appendChild(pre);
    return div;
  }
  if (e.src) {
    const pre = document.createElement('pre');
    pre.textContent = e.src;
    div.appendChild(pre);
  }
  if (e.provenance) {
    const meta = document.createElement('div');
    meta.className = 'meta';
    const p = e.provenance;
    meta.textContent =
      'intent_hash=' + p.intent_hash +
      '  body_hash=' + p.body_hash +
      (p.model ? '  model=' + p.model : '') +
      '  ' + (p.accepted ? 'accepted' : 'unaccepted');
    div.appendChild(meta);
  }

  const accept = document.createElement('button');
  if (e.provenance && e.provenance.accepted) {
    accept.textContent = '✓ accepted';
    accept.className = 'accepted';
    accept.disabled = true;
  } else {
    accept.textContent = ':accept';
    accept.addEventListener('click', async () => {
      const r = await fetchJSON('/api/accept', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({name: e.name}),
      });
      if (r.ok) {
        accept.textContent = '✓ accepted';
        accept.className = 'accepted';
        accept.disabled = true;
        appendRepl('accepted ' + e.name + ' (intent_hash=' + r.intent_hash + ')', 'muted');
        refreshState();
      } else {
        appendRepl('accept failed: ' + r.error, 'err');
      }
    });
  }
  div.appendChild(accept);

  const reject = document.createElement('button');
  reject.textContent = ':reject';
  reject.addEventListener('click', async () => {
    const r = await fetchJSON('/api/reject', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({name: e.name}),
    });
    if (r.ok) {
      appendRepl('rejected ' + e.name + ' (intent_hash=' + r.intent_hash + ')', 'muted');
      refreshState();
    } else {
      appendRepl('reject failed: ' + r.error, 'err');
    }
  });
  div.appendChild(reject);

  return div;
}

function esc(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));
}

function appendRepl(text, cls) {
  const div = document.createElement('div');
  div.className = 'repl-line' + (cls ? ' ' + cls : '');
  div.textContent = text;
  replOutEl.appendChild(div);
  replOutEl.scrollTop = replOutEl.scrollHeight;
}

$('repl-form').addEventListener('submit', async (ev) => {
  ev.preventDefault();
  const source = replInputEl.value.trim();
  if (!source) return;
  appendRepl('nc> ' + source, 'echo');
  replInputEl.value = '';
  const r = await fetchJSON('/api/run', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({source}),
  });
  for (const line of (r.buffer || [])) {
    appendRepl(line.replace(/\n$/, ''), '');
  }
  if (r.ok) {
    if (r.repr) appendRepl(r.repr, '');
  } else {
    appendRepl(r.error || 'error', 'err');
  }
});

$('compile').addEventListener('click', compile);
sourceEl.addEventListener('keydown', (e) => {
  if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
    e.preventDefault();
    compile();
  }
});

refreshState();
</script>
</body>
</html>
"""


# -----------------------------------------------------------------------------
# CLI entry point.
# -----------------------------------------------------------------------------

def _parse_cli(argv: List[str]) -> Tuple[str, Optional[str], int, bool]:
    """Parse CLI flags. Returns (mode, snapshot_path, port, open_browser)."""
    mode = OFFLINE
    snapshot_path: Optional[str] = None
    port = 0
    open_browser = True
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--offline":
            mode = OFFLINE
        elif a == "--online":
            mode = ONLINE
        elif a == "--snapshot":
            mode = SNAPSHOT
        elif a.startswith("--snapshot="):
            mode = SNAPSHOT
            snapshot_path = a.split("=", 1)[1]
        elif a == "--port":
            i += 1
            port = int(argv[i])
        elif a.startswith("--port="):
            port = int(a.split("=", 1)[1])
        elif a == "--no-open":
            open_browser = False
        elif a in ("-h", "--help"):
            _print_help()
            sys.exit(0)
        i += 1
    return mode, snapshot_path, port, open_browser


def _print_help() -> None:
    sys.stdout.write(
        "Usage: python -m newcode.playground [options]\n"
        "\n"
        "Options:\n"
        "  --offline               Use offline-only compilation (default)\n"
        "  --online                Use the Anthropic backend (needs API key)\n"
        "  --snapshot[=PATH]       Replay from a SnapshotStore on disk\n"
        "  --port N                Bind to a specific port (default: OS-chosen)\n"
        "  --no-open               Don't auto-open the browser\n"
        "  -h, --help              Show this message\n"
    )


def main(argv: Optional[List[str]] = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    mode, snapshot_path, port, open_browser = _parse_cli(args)

    store = SnapshotStore(path=snapshot_path) if snapshot_path else SnapshotStore()
    engine = PlaygroundEngine(mode=mode, snapshot_store=store)
    server = PlaygroundServer(engine=engine, port=port)
    url = server.start()

    sys.stdout.write(f"playground at {url}  (mode: {engine.mode}, "
                     f"{len(store)} snapshot entries)\n")
    sys.stdout.flush()

    if open_browser:
        try:
            server.open_browser()
        except Exception:  # noqa: BLE001
            pass

    try:
        # Block forever — Ctrl-C to exit.
        threading.Event().wait()
    except KeyboardInterrupt:
        sys.stdout.write("\nshutting down\n")
    finally:
        server.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
