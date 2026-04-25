"""
New Code — a machine-native language for human-AI collaboration.

v1.0. The 𝕎 primitive and its operators, a process runtime, entanglement,
a top-level parser for the surface syntax (`fn`, `process`, `let`, `module`,
`import`, `extern python {}`), a real expression grammar parsed and lowered
by [expr.py](expr.py), an explicit online/offline compilation split with
deterministic snapshot replay, a content-addressable cache, an approval
workflow (`:accept` / `:reject`), a stdlib-only Language Server, a visual
debugger, and a Python FFI surface (`host_load`, `host_call`, `extern python`).

This is the language usable end-to-end: write scores, compile holes
deterministically (offline via patterns, online via LLM, deterministic via
snapshots), wire to host libraries, and inspect everything through the LSP
or the visual debugger.
"""

from .wave import (
    W, w, Shape,
    sine, sq, tri, saw, pulse,
    e0, silence,
    superpose, oscillate, invert, drift,
    coherence, d_gamma,
    collapse, collapse_amp, collapse_freq, collapse_rms,
    fingerprint, identifiability_horizon,
)
from .process import (
    Process,
    every, on, while_,
    series, parallel, feedback,
    unfold, drift_process,
)
from .entanglement import (
    Entangled, entangle,
    pitch_follow, amplitude_mirror, phase_opposition, identity,
)
from .parser import parse, Function, Intent, Let, Module, Import, Extern
from .compiler import (
    Compiler, Compiled, Provenance,
    OfflineCompiler, AnthropicCompiler, SnapshotCompiler,
    SnapshotStore, OfflineHoleError,
    intent_hash, body_hash,
    OFFLINE, ONLINE, SNAPSHOT,
)
from .debugger import (
    Tracer, DebuggerServer,
    shared_tracer, start_debugger,
)
from .lsp import LanguageServer

__version__ = "1.0.0"

__all__ = [
    # waveform layer
    "W", "w", "Shape",
    "sine", "sq", "tri", "saw", "pulse",
    "e0", "silence",
    "superpose", "oscillate", "invert", "drift",
    "coherence", "d_gamma",
    "collapse", "collapse_amp", "collapse_freq", "collapse_rms",
    "fingerprint", "identifiability_horizon",
    # process layer
    "Process", "every", "on", "while_",
    "series", "parallel", "feedback",
    "unfold", "drift_process",
    # entanglement layer
    "Entangled", "entangle",
    "pitch_follow", "amplitude_mirror", "phase_opposition", "identity",
    # parser AST
    "parse", "Function", "Intent", "Let", "Module", "Import", "Extern",
    # compiler
    "Compiler", "Compiled", "Provenance",
    "OfflineCompiler", "AnthropicCompiler", "SnapshotCompiler",
    "SnapshotStore", "OfflineHoleError",
    "intent_hash", "body_hash",
    "OFFLINE", "ONLINE", "SNAPSHOT",
    # debugger / lsp
    "Tracer", "DebuggerServer", "shared_tracer", "start_debugger",
    "LanguageServer",
]
