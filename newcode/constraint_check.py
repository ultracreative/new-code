"""
Constraint check: post-compile evidence that the generated body honoured
the conductor's forbid / ensure clauses.

The compiler cannot *prove* that a body satisfies a natural-language
intent — that is the open problem at the heart of New Code. What it can
do is parse the generated Python AST and check mechanical properties that
commonly-phrased constraints translate to: "did this body modify φ?",
"does it return a 𝕎 or a scalar?", "does it pass the input through to an
operator that preserves shape?".

The output is a ``ConstraintReport`` that goes onto every ``Compiled``
artefact. The REPL's ``:explain`` command renders it. The LSP hover
shows it next to the intent block. The user sees, in plain text, *what
we checked* — not a proof, but visible evidence of trust.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from typing import Iterable, List, Optional


# -----------------------------------------------------------------------------
# The report.
# -----------------------------------------------------------------------------

@dataclass
class ConstraintFinding:
    clause: str       # "forbid" | "ensure" | "intent"
    text: str         # the original clause text, verbatim
    verdict: str      # "honored" | "violated" | "unknown"
    evidence: str     # one sentence: what we checked, and what we saw

    def __str__(self) -> str:
        glyph = {"honored": "✔", "violated": "✘", "unknown": "·"}[self.verdict]
        return f"  {glyph} {self.clause}: 「{self.text}」\n    — {self.evidence}"


@dataclass
class ConstraintReport:
    function_name: str
    findings: List[ConstraintFinding] = field(default_factory=list)

    def honored(self) -> List[ConstraintFinding]:
        return [f for f in self.findings if f.verdict == "honored"]

    def violated(self) -> List[ConstraintFinding]:
        return [f for f in self.findings if f.verdict == "violated"]

    def unknown(self) -> List[ConstraintFinding]:
        return [f for f in self.findings if f.verdict == "unknown"]

    def __str__(self) -> str:
        if not self.findings:
            return f"{self.function_name}: (no checkable clauses)"
        lines = [f"{self.function_name}:"]
        lines.extend(str(f) for f in self.findings)
        return "\n".join(lines)

    def to_markdown(self) -> str:
        """A compact form for the LSP hover card."""
        if not self.findings:
            return ""
        lines = ["**Constraint check**"]
        for f in self.findings:
            glyph = {"honored": "✔", "violated": "✘", "unknown": "·"}[f.verdict]
            lines.append(f"- {glyph} *{f.clause}*: 「{f.text}」 — {f.evidence}")
        return "\n".join(lines)


# -----------------------------------------------------------------------------
# AST helpers.
# -----------------------------------------------------------------------------

def _parse_body(source: str) -> Optional[ast.AST]:
    try:
        return ast.parse("def __f():\n" + source)
    except SyntaxError:
        return None


def _w_constructor_calls(tree: ast.AST) -> Iterable[ast.Call]:
    """Yield every call site that constructs a 𝕎 (``W(...)`` or ``w(...)``)."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _callee_name(node)
        if name in ("W", "w"):
            yield node


def _callee_name(node: ast.Call) -> Optional[str]:
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _arg_value_source(node: ast.Call, arg_name: str) -> Optional[ast.AST]:
    """Return the AST node for the value passed as ``arg_name`` (keyword)
    or by position if we can infer it."""
    for kw in node.keywords:
        if kw.arg == arg_name:
            return kw.value
    # Positional: (f, A, phi, sigma) is the canonical order for ``w`` and W.
    order = ["f", "A", "phi", "sigma"]
    if arg_name in order:
        idx = order.index(arg_name)
        if idx < len(node.args):
            return node.args[idx]
    return None


def _is_name_ref(node: ast.AST, names: Iterable[str]) -> bool:
    """True if ``node`` is a direct reference to any of ``names`` — either
    ``x`` or ``x.field`` where we don't mind the field (for destructured
    tuples like ``_, A_, phi_, sigma_ = signal.unpack()``)."""
    if isinstance(node, ast.Name) and node.id in names:
        return True
    if isinstance(node, ast.Attribute):
        return _is_name_ref(node.value, names)
    return False


def _derives_from_input(node: ast.AST, input_names: Iterable[str]) -> bool:
    """True if the expression ``node`` can be traced back to one of the
    function inputs (by name) without going through a literal constant."""
    if isinstance(node, ast.Name) and node.id in input_names:
        return True
    if isinstance(node, ast.Name):
        # A local variable — we don't track assignments; treat as ambiguous.
        # Destructured component names ending in "_" often come from unpack;
        # accept them as derived to avoid false positives.
        return node.id.endswith("_")
    if isinstance(node, ast.Attribute):
        return _derives_from_input(node.value, input_names)
    if isinstance(node, ast.BinOp):
        return _derives_from_input(node.left, input_names) \
            or _derives_from_input(node.right, input_names)
    if isinstance(node, ast.UnaryOp):
        return _derives_from_input(node.operand, input_names)
    if isinstance(node, ast.Call):
        return any(_derives_from_input(a, input_names) for a in node.args)
    return False


def _returns_a_wave(tree: ast.AST) -> Optional[bool]:
    """Tri-state: True if every return expression yields a 𝕎; False if any
    yields a scalar (a number, a ``float(...)`` call, a collapse); None if
    we can't tell."""
    returns = [n for n in ast.walk(tree) if isinstance(n, ast.Return)]
    if not returns:
        return None
    verdicts: List[bool] = []
    for r in returns:
        v = r.value
        if v is None:
            continue
        if isinstance(v, ast.Call):
            name = _callee_name(v)
            if name in ("W", "w", "superpose", "oscillate", "invert", "drift",
                        "fingerprint", "amplitude_mirror", "phase_opposition",
                        "pitch_follow"):
                verdicts.append(True); continue
            if name in ("collapse", "collapse_amp", "collapse_freq",
                        "collapse_rms", "coherence", "d_gamma",
                        "identifiability_horizon", "float", "int"):
                verdicts.append(False); continue
        if isinstance(v, ast.Constant) and isinstance(v.value, (int, float)):
            verdicts.append(False); continue
        # Anything else: unclear.
        return None
    if not verdicts:
        return None
    if all(verdicts): return True
    if not any(verdicts): return False
    return None


# -----------------------------------------------------------------------------
# Clause classification.
# -----------------------------------------------------------------------------
#
# Each clause is matched against a small set of patterns. A pattern is
# (regex, checker) — the checker receives the parsed body and the input
# argument names, and returns (verdict, evidence).

PHASE_WORDS = r"(phase|phi|φ)"
AMP_WORDS   = r"(amplitude|amp|\bA\b)"
FREQ_WORDS  = r"(frequency|freq|\bf\b)"
SHAPE_WORDS = r"(shape|sigma|σ)"


def _check_preserves_component(component: str, tree: ast.AST,
                               input_names: List[str]) -> "tuple[str, str]":
    """Check that every 𝕎 constructor in the body passes ``component``
    through unchanged from the input (or omits it, if sensible)."""
    calls = list(_w_constructor_calls(tree))
    if not calls:
        # No 𝕎 constructed. That usually means the body calls an operator
        # (which has its own contract) or returns its input directly.
        return ("unknown",
                f"body does not construct a 𝕎; cannot confirm {component} directly")
    for call in calls:
        val = _arg_value_source(call, component)
        if val is None:
            # Omitted — the default is a safe, non-input value. Flag as
            # unknown if we were asked to preserve the component.
            return ("unknown",
                    f"𝕎 constructor omits `{component}=`; default may differ from input")
        if _derives_from_input(val, input_names):
            continue
        # The component is set to something that doesn't derive from input.
        return ("violated",
                f"𝕎 constructor at line {getattr(call, 'lineno', '?')} sets "
                f"`{component}=` from a value not derived from input")
    return ("honored",
            f"every 𝕎 constructor passes `{component}=` through from an input")


def _check_no_assignment_to(component: str, tree: ast.AST) -> bool:
    """Secondary check: any direct assignment like ``x.phi = ...`` is a
    red flag. Returns True if no such assignment was found."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr == component:
            if isinstance(node.ctx, ast.Store):
                return False
    return True


def _scan_clause(clause_kind: str, text: str, tree: ast.AST,
                 input_names: List[str]) -> Optional[ConstraintFinding]:
    """Try to verdict this clause. Returns a ConstraintFinding or None if
    we had nothing to say at all."""
    t = text.lower()

    def _for(component: str) -> ConstraintFinding:
        verdict, evidence = _check_preserves_component(component, tree, input_names)
        if verdict == "honored" and not _check_no_assignment_to(component, tree):
            verdict, evidence = "violated", \
                f"direct assignment to `.{component}` detected"
        return ConstraintFinding(clause=clause_kind, text=text,
                                 verdict=verdict, evidence=evidence)

    preserve_verbs = r"(preserve|preserving|keep|keeping|do not modify|"\
                     r"do not change|not modify|not change|must equal|equal|unchanged)"

    if re.search(preserve_verbs + r".*" + PHASE_WORDS, t) \
       or re.search(PHASE_WORDS + r".*" + preserve_verbs, t) \
       or "do not modify phase" in t:
        return _for("phi")
    if re.search(preserve_verbs + r".*" + SHAPE_WORDS, t) \
       or re.search(SHAPE_WORDS + r".*" + preserve_verbs, t) \
       or "output shape equals input shape" in t \
       or "shape equal" in t:
        return _for("sigma")
    if re.search(preserve_verbs + r".*" + FREQ_WORDS, t) \
       or re.search(FREQ_WORDS + r".*" + preserve_verbs, t):
        return _for("f")
    if re.search(preserve_verbs + r".*" + AMP_WORDS, t) \
       or re.search(AMP_WORDS + r".*" + preserve_verbs, t):
        return _for("A")

    # "amplitude does not increase" / "A <= A" — we can't prove this from
    # AST alone but we can observe whether A is reassigned at all.
    if re.search(r"amplitude.*not.*increase|does not increase.*amplitude", t):
        # If the body calls drift() or collapse-to-scalar, amplitude is
        # not increased. If it multiplies input amplitude by a bare name,
        # we can't tell.
        calls = [_callee_name(n) for n in ast.walk(tree) if isinstance(n, ast.Call)]
        if "drift" in calls:
            return ConstraintFinding(
                clause=clause_kind, text=text, verdict="honored",
                evidence="body calls `drift`, which monotonically decays amplitude")
        return ConstraintFinding(
            clause=clause_kind, text=text, verdict="unknown",
            evidence="amplitude bound is a value property; no AST proof available")

    # "result is a real scalar" / "returns a scalar" / "result is in [-1, 1]"
    if re.search(r"real scalar|returns a scalar|result is.*scalar|scalar$", t) \
       or re.search(r"result is in \[.*\]", t):
        w_return = _returns_a_wave(tree)
        if w_return is False:
            return ConstraintFinding(
                clause=clause_kind, text=text, verdict="honored",
                evidence="every return in the body yields a scalar")
        if w_return is True:
            return ConstraintFinding(
                clause=clause_kind, text=text, verdict="violated",
                evidence="return path yields a 𝕎, not a scalar")
        return ConstraintFinding(
            clause=clause_kind, text=text, verdict="unknown",
            evidence="return type could not be determined from AST")

    if t.strip() in ("", "nothing", "none"):
        return ConstraintFinding(
            clause=clause_kind, text=text, verdict="honored",
            evidence="empty clause; nothing to forbid / ensure")

    return None


# -----------------------------------------------------------------------------
# Public entry.
# -----------------------------------------------------------------------------

def build_report(function_name: str, source: str, intent,
                 input_names: List[str]) -> ConstraintReport:
    """Produce a ConstraintReport by analysing the generated body source
    against the ``intent`` (which has ``forbid`` / ``ensure`` / etc.)."""
    report = ConstraintReport(function_name=function_name)
    tree = _parse_body(source)
    if tree is None:
        report.findings.append(ConstraintFinding(
            clause="parse", text="(body)", verdict="unknown",
            evidence="generated body failed to parse — no checks run",
        ))
        return report

    for clause_kind, clause_text in (
        ("forbid", getattr(intent, "forbid", "") or ""),
        ("ensure", getattr(intent, "ensure", "") or ""),
    ):
        if not clause_text:
            continue
        finding = _scan_clause(clause_kind, clause_text, tree, input_names)
        if finding is not None:
            report.findings.append(finding)

    return report
