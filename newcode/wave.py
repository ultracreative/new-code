"""
The 𝕎 type: the primitive of New Code.

A waveform number is a four-tuple ⟨f, A, φ, σ⟩ where:
    f : float   — frequency (how often the value repeats / updates)
    A : float   — amplitude (magnitude)
    φ : float   — phase (offset within the cycle, in radians)
    σ : Shape   — shape (a unit-periodic function carrying morphology)

This generalises beyond audio. In a UI, f is an update rate and σ is the
form of the interaction. In a belief system, f is how often the belief is
revised and σ is the curve of its updating. The point is that most dynamic
values have these four components latent; New Code makes them explicit.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Callable, Tuple

# -----------------------------------------------------------------------------
# Shapes
# -----------------------------------------------------------------------------
#
# A shape is a unit-periodic function σ : ℝ → [-1, 1]. The argument is
# interpreted as a phase in cycles (not radians); σ(0) = σ(1) for every
# well-formed shape. Domain-specific shapes can be defined by passing an
# arbitrary callable to Shape.from_callable; the runtime does not enforce
# the periodicity contract but operators that assume it may behave badly
# if it is violated.

Kernel = Callable[[float], float]


@dataclass(frozen=True)
class Shape:
    name: str
    kernel: Kernel

    def __call__(self, t: float) -> float:
        return self.kernel(t)

    def __repr__(self) -> str:
        return f"σ:{self.name}"

    @staticmethod
    def from_callable(name: str, kernel: Kernel) -> "Shape":
        return Shape(name, kernel)


def _sine_k(t: float) -> float:
    return math.sin(2.0 * math.pi * t)


def _square_k(t: float) -> float:
    return 1.0 if (t % 1.0) < 0.5 else -1.0


def _triangle_k(t: float) -> float:
    u = t % 1.0
    return 4.0 * u - 1.0 if u < 0.5 else 3.0 - 4.0 * u


def _saw_k(t: float) -> float:
    u = t % 1.0
    return 2.0 * u - 1.0


def _pulse(duty: float) -> Kernel:
    def k(t: float) -> float:
        return 1.0 if (t % 1.0) < duty else -1.0
    return k


sine = Shape("sine", _sine_k)
sq = Shape("square", _square_k)      # the thermodynamic attractor
tri = Shape("triangle", _triangle_k)
saw = Shape("saw", _saw_k)


def pulse(duty: float) -> Shape:
    return Shape(f"pulse({duty})", _pulse(duty))


# -----------------------------------------------------------------------------
# The waveform number 𝕎
# -----------------------------------------------------------------------------

@dataclass(frozen=True)
class W:
    f: float
    A: float
    phi: float
    sigma: Shape

    def realise(self, t: float) -> float:
        """ŵ(t) = A · σ(f·t + φ/2π) — the instantaneous value at time t."""
        phase_in_cycles = (self.phi / (2.0 * math.pi))
        return self.A * self.sigma(self.f * t + phase_in_cycles)

    # Destructuring helper so we can pattern-match from Python.
    def unpack(self) -> Tuple[float, float, float, Shape]:
        return self.f, self.A, self.phi, self.sigma

    # --- Pretty print ---
    def __repr__(self) -> str:
        return f"⟨{self.f:g}, {self.A:g}, {self.phi:g}, {self.sigma.name}⟩"


# The unit oscillator: the "1" of New Code.
e0 = W(f=1.0, A=1.0, phi=0.0, sigma=sine)

# The silence: the additive identity under superposition.
silence = W(f=0.0, A=0.0, phi=0.0, sigma=sine)


def w(f: float, A: float = 1.0, phi: float = 0.0, sigma: Shape = sine) -> W:
    """Convenience constructor — use when you don't want to import W directly."""
    return W(f=f, A=A, phi=phi, sigma=sigma)


# -----------------------------------------------------------------------------
# Operators
# -----------------------------------------------------------------------------
#
# The core operators of Waveform Logic, lifted into Python. For structured
# (non-commensurate) operands, some operators produce a derived shape rather
# than a pure 𝕎; in those cases we return a W whose sigma is a closure.

def superpose(a: W, b: W) -> W:
    """⊕ : pointwise sum of realisations, rendered back into a 𝕎.

    When a.f == b.f we can express the result as a single sinusoid-like 𝕎
    by vector addition on amplitude/phase (if both are sine-shaped). In the
    general case we return a 𝕎 whose sigma is the sum-at-phase closure, and
    whose f is taken from a (the sampling reference) and A is the peak of
    the sum over one period.
    """
    if a.f == b.f and a.sigma is sine and b.sigma is sine:
        # Exact sinusoidal superposition.
        x = a.A * math.cos(a.phi) + b.A * math.cos(b.phi)
        y = a.A * math.sin(a.phi) + b.A * math.sin(b.phi)
        A = math.hypot(x, y)
        phi = math.atan2(y, x)
        return W(f=a.f, A=A, phi=phi, sigma=sine)

    # General case: define the sum shape.
    def summed_kernel(t: float) -> float:
        # Normalise by amplitude of the primary; consumer can scale.
        return a.sigma(a.f * t + a.phi / (2 * math.pi)) \
             + (b.A / max(a.A, 1e-12)) * b.sigma(b.f * t + b.phi / (2 * math.pi))

    name = f"({a.sigma.name}+{b.sigma.name})"
    # Estimate peak over one reference period.
    peak = max(abs(a.A * summed_kernel(k / 128.0)) for k in range(129))
    return W(f=a.f, A=peak, phi=0.0, sigma=Shape(name, summed_kernel))


def oscillate(a: W, b: W) -> W:
    """⊚ : shape-composing multiplication (ring modulation of shape)."""
    def prod_kernel(t: float) -> float:
        return a.sigma(a.f * t + a.phi / (2 * math.pi)) \
             * b.sigma(b.f * t + b.phi / (2 * math.pi))
    name = f"({a.sigma.name}·{b.sigma.name})"
    A = a.A * b.A
    f = a.f  # carry the primary frequency
    return W(f=f, A=A, phi=0.0, sigma=Shape(name, prod_kernel))


def invert(a: W) -> W:
    """Phase inversion: shift by π."""
    return replace(a, phi=a.phi + math.pi)


def drift(a: W, delta: float) -> W:
    """⇝ : the drift operator. Takes a value toward the square-wave attractor.

    This is the single operator that captures ageing, decay, analysis, and
    thermodynamic termination. It shifts f, decays A, rotates φ, and morphs
    σ toward sq proportionally to |δ|.
    """
    # Frequency shift (amplitude-modulated).
    new_f = a.f + delta * a.A
    # Amplitude decay.
    new_A = a.A * math.exp(-abs(delta))
    # Phase rotation.
    new_phi = a.phi + delta * a.f * 0.01  # small coupling constant
    # Shape deformation toward square.
    if abs(delta) < 1e-9:
        new_sigma = a.sigma
    else:
        alpha = min(abs(delta), 1.0)  # clamp to [0, 1]
        original = a.sigma

        def morphed(t: float) -> float:
            return (1.0 - alpha) * original(t) + alpha * sq(t)

        new_sigma = Shape(f"{a.sigma.name}→sq({alpha:.2f})", morphed)

    return W(f=new_f, A=new_A, phi=new_phi, sigma=new_sigma)


def coherence(a: W, b: W, samples: int = 256) -> float:
    """⟪·,·⟫ : shape-sensitive correlation. Produces a scalar (this is a collapse).

    Computed as the normalised inner product of the two realisations over
    one reference period. Returns a value in [-1, 1].
    """
    ref_period = 1.0 / max(a.f, b.f, 1e-9)
    dot = 0.0
    na = 0.0
    nb = 0.0
    for k in range(samples):
        t = k * ref_period / samples
        va = a.realise(t)
        vb = b.realise(t)
        dot += va * vb
        na += va * va
        nb += vb * vb
    denom = math.sqrt(na * nb)
    if denom < 1e-12:
        return 0.0
    return dot / denom


def d_gamma(a: W, b: W) -> float:
    """Coherence distance on 𝕎. Non-Euclidean. Sensitive to shape, not just magnitude."""
    return math.sqrt(max(0.0, 1.0 - coherence(a, b)))


def collapse(a: W) -> float:
    """⌊·⌉ : irreversible projection of a 𝕎 to a scalar ℝ.

    Defined as the amplitude-weighted coherence with the unit oscillator e₀.
    Every use of this function represents an information loss.
    """
    return a.A * coherence(a, e0)


# Alternative collapse maps.

def collapse_amp(a: W) -> float:
    """⌊·⌉_amp : amplitude only."""
    return a.A


def collapse_freq(a: W) -> float:
    """⌊·⌉_freq : frequency only."""
    return a.f


def collapse_rms(a: W, samples: int = 256) -> float:
    """⌊·⌉_rms : root-mean-square over one period."""
    period = 1.0 / max(a.f, 1e-9)
    s = 0.0
    for k in range(samples):
        t = k * period / samples
        v = a.realise(t)
        s += v * v
    return math.sqrt(s / samples)


# -----------------------------------------------------------------------------
# Fingerprint & identifiability horizon — handy diagnostics.
# -----------------------------------------------------------------------------

def fingerprint(a: W) -> W:
    """w ⊚ e₀ — the morphological fingerprint of a waveform."""
    return oscillate(a, e0)


def identifiability_horizon(a: W, threshold: float = 0.5, step: float = 0.02,
                            max_delta: float = 5.0) -> float:
    """The smallest δ at which a becomes unrecognisable under coherence distance."""
    delta = 0.0
    while delta < max_delta:
        drifted = drift(a, delta)
        if d_gamma(a, drifted) > threshold:
            return delta
        delta += step
    return max_delta
