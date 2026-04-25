"""
Processes in New Code.

A process is not a thread. It is an ongoing computation with its own internal
time τ. Processes are the language's unit of execution; the runtime advances
each process along its own clock, and operators like ‖ synchronise them.

In this v0.01 we implement processes as generators that yield values when
sampled. A process has a sampling function that, given a current τ, returns
the next realisation. This is enough to express `every`, `on`, `while`, and
the series/parallel/feedback combinators.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any, Callable, Generic, List, Optional, TypeVar

from .wave import W, drift, silence

T = TypeVar("T")
_NO_INPUT = object()


@dataclass
class Process(Generic[T]):
    """A named, ongoing computation producing values of type T.

    The ``step`` callable is given the current internal time τ and returns
    the value produced at that time. The process's own τ advances whenever
    ``sample`` is called; external coordination is done through the runtime.
    """

    name: str
    step: Callable[[float], T]
    intent: str = ""
    # Rate at which τ advances per sample call (cycles per sample).
    rate: float = 1.0
    tau: float = 0.0

    def sample(self, incoming: Any = _NO_INPUT) -> T:
        value = _invoke_step(self.step, self.tau, incoming)
        self.tau += 1.0 / max(self.rate, 1e-9)
        return value

    def reset(self) -> None:
        self.tau = 0.0

    def __repr__(self) -> str:
        return f"proc<{self.name}>"


# -----------------------------------------------------------------------------
# Process constructors
# -----------------------------------------------------------------------------

def _invoke_step(step: Callable[..., T], tau: float, incoming: Any = _NO_INPUT) -> T:
    """Call a process step with the most specific supported calling form.

    v0.01 locks the semantics this way:
    - plain processes accept `step(tau)`
    - input-aware processes may accept `step(tau, incoming)`

    Constructors in this module use the one-argument form; explicit Python
    process bodies may opt into the two-argument form so combinators like
    series and feedback can feed values through a process graph.
    """
    if incoming is _NO_INPUT:
        return step(tau)

    try:
        sig = inspect.signature(step)
    except (TypeError, ValueError):
        return step(tau, incoming)

    positional = [
        p for p in sig.parameters.values()
        if p.kind in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        )
    ]
    has_varargs = any(
        p.kind == inspect.Parameter.VAR_POSITIONAL
        for p in sig.parameters.values()
    )
    if has_varargs or len(positional) >= 2:
        return step(tau, incoming)
    return step(tau)

def every(w_val: W, name: str = "every") -> Process[W]:
    """Produce a realisation of w_val at each tick of its frequency.

    The intent corresponds to New Code's `every` keyword.
    """
    def step(tau: float) -> W:
        # We return the waveform itself, not a collapsed sample. Consumers
        # that want a scalar can call w_val.realise(tau) or ⌊·⌉ themselves.
        return w_val

    return Process(name=name, step=step, rate=max(w_val.f, 1e-9))


def on(trigger: Callable[[float], bool], body: Callable[[float], T],
       name: str = "on") -> Process[Optional[T]]:
    """Produce a value when a trigger predicate fires; otherwise None."""
    def step(tau: float) -> Optional[T]:
        return body(tau) if trigger(tau) else None
    return Process(name=name, step=step)


def while_(cond: Callable[[float], bool], body: Callable[[float], T],
           name: str = "while") -> Process[Optional[T]]:
    """Produce values while a condition holds; None once it stops."""
    def step(tau: float) -> Optional[T]:
        return body(tau) if cond(tau) else None
    return Process(name=name, step=step)


# -----------------------------------------------------------------------------
# Combinators: series, parallel, feedback
# -----------------------------------------------------------------------------

def series(*procs: Process) -> Process:
    """▶ — left-to-right process composition over one observation step.

    Each sampling of the composite samples each child exactly once, in order.
    The output of each child is offered as the `incoming` value to the next
    child. A child that does not accept an incoming value simply ignores it.
    """
    if not procs:
        raise ValueError("series requires at least one process")

    def step(tau: float):
        v = procs[0].sample()
        for p in procs[1:]:
            v = p.sample(v)
        return v

    return Process(
        name="▶".join(p.name for p in procs),
        step=step,
        rate=max(p.rate for p in procs),
    )


def parallel(a: Process, b: Process) -> Process:
    """∥ — two processes run independently, yielding a pair."""
    def step(tau: float):
        return (a.sample(), b.sample())

    return Process(name=f"{a.name}∥{b.name}", step=step, rate=max(a.rate, b.rate))


def feedback(inner: Process, delay_samples: int = 1) -> Process:
    """↺ — feed a process's output back into its input with a delay.

    The minimal implementation keeps a ring buffer of past outputs and
    exposes them on future ticks. Consumers of the process receive the
    current tick's output; the feedback is implicit in how `inner.step` uses
    its recent history.
    """
    buffer: List[Any] = [None] * max(delay_samples, 1)

    def step(tau: float):
        delayed = buffer[0]
        v = inner.sample(delayed)
        buffer.append(v)
        buffer.pop(0)
        return v

    return Process(name=f"{inner.name}↺", step=step, rate=inner.rate)


# -----------------------------------------------------------------------------
# The runtime: unfold, not run
# -----------------------------------------------------------------------------

def unfold(p: Process[T], n: int) -> List[T]:
    """Advance process p by n ticks and collect the values. A New Code program
    is not run; it is unfolded. This is the minimal unfolding primitive.
    """
    return [p.sample() for _ in range(n)]


def drift_process(p: Process[W], delta_per_step: float) -> Process[W]:
    """Return a process that drifts its underlying value by δ at each step.

    This is how thermodynamic termination is expressed: let a process drift
    until it converges to the square-wave attractor. Cleanly ending a
    process is *not* an abort; it is letting the drift complete.
    """
    accumulated = {"delta": 0.0}

    def step(tau: float) -> W:
        v = p.sample()
        if isinstance(v, W):
            out = drift(v, accumulated["delta"])
        else:
            out = silence
        accumulated["delta"] += delta_per_step
        return out

    return Process(name=f"{p.name}⇝", step=step, rate=p.rate)
