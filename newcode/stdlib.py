"""
The New Code standard library.

Every binding here is in scope for every compiled function body, every
explicit body, every let RHS, and every REPL expression. The stdlib is
the language's "operating environment" — anything not in here must come
from a host import (`import host.numpy as np`) or an FFI block.

The stdlib is organised in layers:

  * **Wave layer** — 𝕎, shapes, operators, collapse.
  * **Process layer** — Process, every/on/while_, series/parallel/feedback.
  * **Entanglement** — Entangled and the coupling library.
  * **Math layer** — pi, e, tau, sqrt, abs, min, max, exp, log, sin, cos…
  * **Container layer** — list, dict, set, tuple, len, range…
  * **Functional layer** — map, filter, fold (left/right), zip, take, drop…
  * **String layer** — str, format, split, join, lower, upper.
  * **IO layer** — print (writes to a captured buffer in pure mode).
  * **FFI layer** — host accessor for Python interop.

Builtins are a curated subset of Python's. Dangerous names (exec, eval,
__import__, open) are excluded so an LLM-generated body cannot reach
them through the normal scope.
"""

from __future__ import annotations

import functools
import math
from typing import Any, Callable, Dict, Iterable, List, TypeVar

T = TypeVar("T")
U = TypeVar("U")


# -----------------------------------------------------------------------------
# Functional helpers
# -----------------------------------------------------------------------------

def fold_left(f: Callable[[U, T], U], init: U, xs: Iterable[T]) -> U:
    return functools.reduce(f, xs, init)


def fold_right(f: Callable[[T, U], U], init: U, xs: Iterable[T]) -> U:
    return functools.reduce(lambda acc, x: f(x, acc), reversed(list(xs)), init)


def take(n: int, xs: Iterable[T]) -> List[T]:
    out: List[T] = []
    it = iter(xs)
    for _ in range(n):
        try:
            out.append(next(it))
        except StopIteration:
            break
    return out


def drop(n: int, xs: Iterable[T]) -> List[T]:
    return list(xs)[n:]


def flatten(xs: Iterable[Iterable[T]]) -> List[T]:
    return [x for sub in xs for x in sub]


def compose(*fs: Callable) -> Callable:
    if not fs:
        return lambda x: x
    if len(fs) == 1:
        return fs[0]

    def composed(x):
        for fn in reversed(fs):
            x = fn(x)
        return x
    return composed


def pipe(*fs: Callable) -> Callable:
    """Left-to-right composition, the opposite of compose."""
    if not fs:
        return lambda x: x

    def piped(x):
        for fn in fs:
            x = fn(x)
        return x
    return piped


def repeat(n: int, x: T) -> List[T]:
    return [x] * n


def head(xs: List[T]) -> T:
    return xs[0]


def tail(xs: List[T]) -> List[T]:
    return list(xs[1:])


def init_list(xs: List[T]) -> List[T]:
    return list(xs[:-1])


def last(xs: List[T]) -> T:
    return xs[-1]


def reverse(xs: Iterable[T]) -> List[T]:
    return list(reversed(list(xs)))


def unique(xs: Iterable[T]) -> List[T]:
    """Stable-order unique: preserves first occurrence."""
    seen = set()
    out: List[T] = []
    for x in xs:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def zip_with(f: Callable[[T, U], Any], xs: Iterable[T], ys: Iterable[U]) -> List[Any]:
    return [f(a, b) for a, b in zip(xs, ys)]


# -----------------------------------------------------------------------------
# String / format helpers
# -----------------------------------------------------------------------------

def fmt(template: str, **kwargs) -> str:
    """Format with kwargs. Lighter-weight than str.format for the common case."""
    return template.format(**kwargs)


def show(x: Any) -> str:
    """Default printable form. Wraps repr but special-cases 𝕎 to its
    Unicode-rich four-tuple."""
    return repr(x)


# -----------------------------------------------------------------------------
# IO (captured)
# -----------------------------------------------------------------------------

class _IOSink:
    """A capturable IO sink. The default sink writes to stdout; the REPL
    swaps in a list-backed sink during command evaluation so output goes
    to the user terminal but remains diffable from tests."""

    def __init__(self):
        self.buffer: List[str] = []
        self.echo_to_stdout = True

    def write(self, *parts: Any, sep: str = " ", end: str = "\n") -> None:
        text = sep.join(str(p) for p in parts) + end
        self.buffer.append(text)
        if self.echo_to_stdout:
            import sys
            sys.stdout.write(text)
            sys.stdout.flush()

    def flush(self) -> None:
        self.buffer.clear()


_DEFAULT_SINK = _IOSink()


def io_print(*parts: Any, sep: str = " ", end: str = "\n") -> None:
    _DEFAULT_SINK.write(*parts, sep=sep, end=end)


def io_buffer() -> List[str]:
    return list(_DEFAULT_SINK.buffer)


def io_clear() -> None:
    _DEFAULT_SINK.flush()


def io_set_echo(on: bool) -> None:
    _DEFAULT_SINK.echo_to_stdout = on


# -----------------------------------------------------------------------------
# Type checking helpers (best-effort, surface-level)
# -----------------------------------------------------------------------------

_TYPE_MAP = {
    "ℝ": float, "ℤ": int, "ℕ": int, "𝔹": bool, "Bool": bool,
    "Str": str, "String": str, "Unit": type(None),
    "Int": int, "Float": float, "Number": (int, float),
}


def conforms(value: Any, type_text: str) -> bool:
    """Best-effort surface-level conformance check.

    Used by the runtime when an FFI boundary or an `ensure` clause asks
    whether a value matches a declared type. Returns True for unknown
    types (we don't reject what we can't verify)."""
    type_text = (type_text or "").strip()
    if not type_text:
        return True
    if type_text in _TYPE_MAP:
        return isinstance(value, _TYPE_MAP[type_text])
    if type_text == "𝕎":
        from .wave import W
        return isinstance(value, W)
    if type_text == "Process":
        from .process import Process
        return isinstance(value, Process)
    if type_text == "Entangled":
        from .entanglement import Entangled
        return isinstance(value, Entangled)
    # List / record / function types — we'd need a real parser for these,
    # but a coarse check is fine.
    if type_text.startswith("[") and type_text.endswith("]"):
        return isinstance(value, list)
    if "→" in type_text or "->" in type_text:
        return callable(value)
    return True


# -----------------------------------------------------------------------------
# Host bridge (Python FFI surface)
# -----------------------------------------------------------------------------

class HostBridge:
    """Access to the host runtime (Python). Used by `extern python { }`
    and by `import host.<module>`.

    The bridge is intentionally explicit: New Code code reaches the host
    by name, never by the implicit Python import path. This is what makes
    the offline/online split honest — the only host effects are the ones
    the user named.
    """

    def __init__(self):
        self._loaded: Dict[str, Any] = {}

    def load(self, dotted_name: str) -> Any:
        """Import a host (Python) module by dotted name and cache it."""
        if dotted_name in self._loaded:
            return self._loaded[dotted_name]
        # Dotted-name import. We use __import__ here behind the scenes.
        mod = __import__(dotted_name)
        for part in dotted_name.split(".")[1:]:
            mod = getattr(mod, part)
        self._loaded[dotted_name] = mod
        return mod

    def call(self, dotted_name: str, *args, **kwargs):
        """Resolve a dotted host name to a callable and invoke it."""
        parts = dotted_name.split(".")
        # find the longest importable prefix
        for split in range(len(parts), 0, -1):
            try:
                base = self.load(".".join(parts[:split]))
                target = base
                for attr in parts[split:]:
                    target = getattr(target, attr)
                return target(*args, **kwargs)
            except (ImportError, AttributeError):
                continue
        raise ValueError(f"unknown host name: {dotted_name}")


_HOST = HostBridge()


def host_load(name: str) -> Any:
    return _HOST.load(name)


def host_call(name: str, *args, **kwargs):
    return _HOST.call(name, *args, **kwargs)


# -----------------------------------------------------------------------------
# Scope builder — what the compiler sees when it executes a body
# -----------------------------------------------------------------------------

def build_scope() -> Dict[str, Any]:
    from . import wave as _wave
    from . import process as _process
    from . import entanglement as _entangle

    scope: Dict[str, Any] = {
        # --- waveform layer ---
        "W": _wave.W, "w": _wave.w,
        "Shape": _wave.Shape,
        "sine": _wave.sine, "sq": _wave.sq, "tri": _wave.tri,
        "saw": _wave.saw, "pulse": _wave.pulse,
        "e0": _wave.e0, "silence": _wave.silence,
        "superpose": _wave.superpose, "oscillate": _wave.oscillate,
        "invert": _wave.invert, "drift": _wave.drift,
        "coherence": _wave.coherence, "d_gamma": _wave.d_gamma,
        "collapse": _wave.collapse,
        "collapse_amp": _wave.collapse_amp,
        "collapse_freq": _wave.collapse_freq,
        "collapse_rms": _wave.collapse_rms,
        "fingerprint": _wave.fingerprint,
        "identifiability_horizon": _wave.identifiability_horizon,

        # --- process layer ---
        "Process": _process.Process,
        "every": _process.every, "on": _process.on, "while_": _process.while_,
        "series": _process.series, "parallel": _process.parallel,
        "feedback": _process.feedback,
        "unfold": _process.unfold, "drift_process": _process.drift_process,

        # --- entanglement ---
        "Entangled": _entangle.Entangled,
        "entangle": _entangle.entangle,
        "pitch_follow": _entangle.pitch_follow,
        "amplitude_mirror": _entangle.amplitude_mirror,
        "phase_opposition": _entangle.phase_opposition,
        "identity": _entangle.identity,

        # --- math ---
        "pi": math.pi, "tau_const": math.tau, "e_const": math.e,
        "sqrt": math.sqrt, "exp": math.exp, "log": math.log,
        "log2": math.log2, "log10": math.log10,
        "sin": math.sin, "cos": math.cos, "tan": math.tan,
        "asin": math.asin, "acos": math.acos, "atan": math.atan,
        "atan2": math.atan2, "hypot": math.hypot,
        "floor": math.floor, "ceil": math.ceil, "trunc": math.trunc,
        "isnan": math.isnan, "isinf": math.isinf,
        "pow": pow,

        # --- functional ---
        "fold_left": fold_left, "fold_right": fold_right,
        "take": take, "drop": drop, "flatten": flatten,
        "compose": compose, "pipe": pipe,
        "repeat": repeat, "head": head, "tail": tail,
        "init_list": init_list, "last": last, "reverse": reverse,
        "unique": unique, "zip_with": zip_with,

        # --- string / formatting ---
        "fmt": fmt, "show": show,

        # --- io (captured) ---
        "print": io_print,
        "io_buffer": io_buffer, "io_clear": io_clear,
        "io_set_echo": io_set_echo,

        # --- type helpers ---
        "conforms": conforms,

        # --- host / FFI ---
        "host_load": host_load, "host_call": host_call,
    }

    scope["__builtins__"] = {
        # Curated safe set.
        "abs": abs, "min": min, "max": max, "sum": sum, "len": len,
        "range": range, "list": list, "dict": dict, "tuple": tuple,
        "set": set, "frozenset": frozenset,
        "int": int, "float": float, "str": str, "bool": bool,
        "round": round, "enumerate": enumerate, "zip": zip,
        "map": map, "filter": filter, "sorted": sorted, "reversed": reversed,
        "any": any, "all": all,
        "isinstance": isinstance, "type": type, "callable": callable,
        "iter": iter, "next": next,
        "True": True, "False": False, "None": None,
        # Re-export the io print under the builtin name as well so that
        # transpiled code calling print() gets the captured sink.
        "print": io_print,
    }
    return scope
