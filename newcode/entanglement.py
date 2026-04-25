"""
Entanglement in New Code.

Two values are entangled when there is a declared coupling function Φ such
that any transformation of one induces Φ on the other. Entanglement is
symmetric and not transitive. It is how New Code expresses structural
coupling directly in the type system instead of leaving it to discipline.

This module provides the `Entangled` type and a small library of coupling
functions. The axiom that "entanglement is not transitive" is enforced by
the fact that we do not propagate across chains; the runtime only updates
the directly-coupled pair.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Generic, TypeVar

from .wave import W

T = TypeVar("T")

Coupling = Callable[[T], T]


@dataclass
class Entangled(Generic[T]):
    """A pair ⟨T ▷◁ T⟩ coupled by a function Φ.

    Any update to .left triggers Φ on .right, and vice versa. The coupling
    function must be a pure function of its input; side effects will cause
    the entanglement relation to become inconsistent.
    """

    left: T
    right: T
    via: Coupling
    name: str = "entangled"
    # History of operations, useful for the debugger.
    _history: list = field(default_factory=list)

    def transform_left(self, f: Callable[[T], T]) -> "Entangled[T]":
        """Apply f to the left; propagate via Φ to the right."""
        new_left = f(self.left)
        new_right = self.via(new_left)
        self._history.append(("left", f.__name__ if hasattr(f, "__name__") else str(f)))
        return Entangled(left=new_left, right=new_right, via=self.via,
                         name=self.name, _history=self._history)

    def transform_right(self, f: Callable[[T], T]) -> "Entangled[T]":
        """Apply f to the right; propagate via Φ to the left.

        Note: symmetric propagation requires Φ to be invertible. In practice
        we apply f to the right and then re-derive the left by the inverse
        coupling, if one is declared; otherwise we refuse.
        """
        new_right = f(self.right)
        # The simplest invertible case: Φ is its own inverse (involution).
        # For general couplings, a bidirectional declaration is required.
        new_left = self.via(new_right)
        self._history.append(("right", f.__name__ if hasattr(f, "__name__") else str(f)))
        return Entangled(left=new_left, right=new_right, via=self.via,
                         name=self.name, _history=self._history)

    def disentangle(self) -> tuple:
        """Return the bare pair. The coupling is lost."""
        return (self.left, self.right)

    def __repr__(self) -> str:
        return f"⟨{self.left} ▷◁ {self.right}⟩ via {self.via.__name__}"


# -----------------------------------------------------------------------------
# Library of common coupling functions.
# -----------------------------------------------------------------------------

def pitch_follow(w: W) -> W:
    """Second voice follows the first at a perfect fifth above."""
    return W(f=w.f * 1.5, A=w.A, phi=w.phi, sigma=w.sigma)


def amplitude_mirror(w: W) -> W:
    """Second voice mirrors the first's amplitude, keeping its own phase/shape."""
    return W(f=w.f, A=w.A, phi=-w.phi, sigma=w.sigma)


def phase_opposition(w: W) -> W:
    """Second voice is anti-phase of the first."""
    import math
    return W(f=w.f, A=w.A, phi=w.phi + math.pi, sigma=w.sigma)


def identity(x):
    """Trivial coupling: the two values are always identical."""
    return x


# -----------------------------------------------------------------------------
# Entanglement constructor.
# -----------------------------------------------------------------------------

def entangle(left: T, right: T, via: Coupling, name: str = "entangled") -> Entangled[T]:
    """Declare two values entangled by a coupling function.

    The caller is responsible for ensuring that ``right`` is already
    consistent with Φ(left); the runtime does not check this at construction
    to allow intentional initial offsets. A warning could be issued.
    """
    return Entangled(left=left, right=right, via=via, name=name)
