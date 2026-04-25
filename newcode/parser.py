"""
Parser for the New Code surface syntax.

v1.0 splits parsing into two layers:

  1. **Top-level parser (this file).** Indentation-aware. Recognises
     declarations: `module`, `import`, `extern`, `fn`, `process`, `let`.
     Collects intent / forbid / ensure / requires / emits / consumes /
     guard clauses. Captures bodies as raw text after `≔`.

  2. **Expression parser ([expr.py](expr.py)).** Brace/paren-based. Parses
     the body text from a declaration into a typed AST. Used for both
     explicit bodies and `let` RHS.

The split keeps indentation handling local to declarations while letting
expressions be free-form and Unicode-rich without indentation rules.

A declaration body in v1.0 is **always parsed by [expr.py](expr.py)** unless
it is the `??` hole. The Python `eval()` shortcut from v0.x is gone — use
`python { ... }` blocks for explicit Python escape, which the expression
parser recognises as a first-class form.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional


# -----------------------------------------------------------------------------
# AST node types.
# -----------------------------------------------------------------------------

@dataclass
class Arg:
    name: str
    type_: str


@dataclass
class Intent:
    intent: str = ""
    forbid: str = ""
    ensure: str = ""
    requires: str = ""
    emits: str = ""
    consumes: str = ""
    guard: str = ""


@dataclass
class Function:
    name: str
    args: List[Arg]
    return_type: str
    intent: Intent
    body: str            # the literal source of the body, may be `??`
    is_hole: bool = False


@dataclass
class Process:
    name: str
    return_type: str
    intent: Intent
    body: str
    is_hole: bool = False


@dataclass
class Let:
    name: str
    type_: Optional[str]
    expression: str       # raw expression text — parsed by expr.py


@dataclass
class Module:
    name: str
    intent: Intent
    declarations: List = field(default_factory=list)


@dataclass
class Import:
    """`import path.to.module` or `import path.to.module as alias`.

    Modules are resolved against the source file's directory and a search
    path supplied by the loader. See [modules.py](modules.py).
    """
    path: str
    alias: Optional[str] = None


@dataclass
class Extern:
    """A raw escape hatch: `extern python { ... }`.

    The body is executed in the loading scope so users can pull in NumPy,
    define helpers, or wire host APIs. Use sparingly; it bypasses the
    expression parser and the AST safety check.
    """
    language: str        # "python" for now
    body: str


# -----------------------------------------------------------------------------
# Lexical helpers.
# -----------------------------------------------------------------------------

_QUOTE_PAIRS = [("「", "」"), ("『", "』"), ("\"", "\""), ("'", "'")]


def _extract_quoted(line: str, start: int = 0) -> tuple:
    """Find the next bracketed string in line starting from `start`.

    Returns (content, end_index). Raises ValueError if none found.
    """
    for open_q, close_q in _QUOTE_PAIRS:
        i = line.find(open_q, start)
        if i == -1:
            continue
        j = line.find(close_q, i + len(open_q))
        if j == -1:
            raise ValueError(f"Unclosed quote at {i}: {line!r}")
        return line[i + len(open_q):j], j + len(close_q)
    raise ValueError(f"No quoted string in {line!r}")


_BIND = re.compile(r"(≔|:=)")
_FN_HEAD = re.compile(
    r"^fn\s+(?P<name>[A-Za-z_][\w]*)\s*\((?P<args>.*?)\)\s*(?:→|->)\s*(?P<ret>.+?)\s*$"
)
_PROC_HEAD = re.compile(
    r"^process\s+(?P<name>[A-Za-z_][\w]*)\s*:\s*(?P<ret>.+?)\s*$"
)
_LET = re.compile(
    r"^let\s+(?P<name>[A-Za-z_][\w]*)\s*(?::\s*(?P<type>.+?))?\s*=\s*(?P<expr>.+)$"
)
_MODULE_HEAD = re.compile(r"^module\s+(?P<name>[\w.]+)\s*$")
_IMPORT = re.compile(
    r"^import\s+(?P<path>[\w.]+)(?:\s+as\s+(?P<alias>[A-Za-z_][\w]*))?\s*$"
)
_EXTERN_HEAD = re.compile(
    r"^extern\s+(?P<lang>[A-Za-z_][\w]*)\s*\{?\s*$"
)


def _parse_args(s: str) -> List[Arg]:
    """Parse `a : T, b : T` into a list of Arg nodes."""
    s = s.strip()
    if not s:
        return []
    parts = []
    depth = 0
    buf = ""
    for ch in s:
        if ch in "<⟨(":
            depth += 1
        elif ch in ">⟩)":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append(buf)
            buf = ""
        else:
            buf += ch
    if buf.strip():
        parts.append(buf)

    args: List[Arg] = []
    for p in parts:
        p = p.strip()
        if ":" not in p:
            raise ValueError(f"Argument missing type: {p!r}")
        name, type_ = p.split(":", 1)
        args.append(Arg(name=name.strip(), type_=type_.strip()))
    return args


# -----------------------------------------------------------------------------
# The parser.
# -----------------------------------------------------------------------------

class Parser:
    def __init__(self, source: str):
        self.lines = source.splitlines()
        self.i = 0

    def _peek(self) -> Optional[str]:
        while self.i < len(self.lines):
            raw = self.lines[self.i]
            stripped = raw.strip()
            if not stripped or stripped.startswith("※"):
                self.i += 1
                continue
            return raw
        return None

    def _advance(self) -> str:
        line = self._peek()
        if line is None:
            raise ValueError("Unexpected end of input")
        self.i += 1
        return line

    def _indent(self, line: str) -> int:
        return len(line) - len(line.lstrip())

    def parse(self) -> List:
        decls = []
        while self._peek() is not None:
            decls.append(self._parse_decl(base_indent=0))
        return decls

    def _parse_decl(self, base_indent: int):
        head = self._peek()
        if head is None:
            raise ValueError("Expected declaration")
        stripped = head.strip()

        if stripped.startswith("module"):
            return self._parse_module(base_indent)
        if stripped.startswith("import"):
            return self._parse_import()
        if stripped.startswith("extern"):
            return self._parse_extern(base_indent)
        if stripped.startswith("fn "):
            return self._parse_fn(base_indent)
        if stripped.startswith("process "):
            return self._parse_process(base_indent)
        if stripped.startswith("let "):
            return self._parse_let(base_indent)

        raise ValueError(f"Unknown declaration at line {self.i + 1}: {stripped!r}")

    def _parse_module(self, base_indent: int) -> Module:
        head = self._advance().strip()
        m = _MODULE_HEAD.match(head)
        if not m:
            raise ValueError(f"Malformed module header: {head!r}")
        name = m.group("name")
        intent, _ = self._collect_intent(base_indent)
        decls = []
        while self._peek() is not None:
            nxt = self._peek()
            if self._indent(nxt) <= base_indent:
                break
            decls.append(self._parse_decl(base_indent=self._indent(nxt)))
        return Module(name=name, intent=intent, declarations=decls)

    def _parse_import(self) -> Import:
        line = self._advance().strip()
        m = _IMPORT.match(line)
        if not m:
            raise ValueError(f"Malformed import: {line!r}")
        return Import(path=m.group("path"), alias=m.group("alias"))

    def _parse_extern(self, base_indent: int) -> Extern:
        head_raw = self._advance()
        head = head_raw.strip()
        m = _EXTERN_HEAD.match(head)
        if not m:
            raise ValueError(f"Malformed extern header: {head!r}")
        language = m.group("lang")
        # If the head ended with `{`, collect lines until the matching `}`.
        # Otherwise fall back to indentation-collected body.
        body_lines: List[str] = []
        if head.rstrip().endswith("{"):
            depth = 1
            while self._peek() is not None and depth > 0:
                line = self._advance()
                if "}" in line and "{" not in line:
                    depth -= 1
                    if depth == 0:
                        # Strip the trailing }
                        idx = line.rfind("}")
                        prefix = line[:idx]
                        if prefix.strip():
                            body_lines.append(prefix)
                        break
                if "{" in line:
                    depth += line.count("{") - line.count("}")
                body_lines.append(line)
            if depth > 0:
                raise ValueError("Unclosed extern block")
        else:
            while self._peek() is not None:
                nxt = self._peek()
                if self._indent(nxt) <= base_indent:
                    break
                body_lines.append(self._advance())
        body = "\n".join(body_lines)
        return Extern(language=language, body=body)

    def _parse_fn(self, base_indent: int) -> Function:
        head_raw = self._advance()
        head = head_raw.strip()
        m = _FN_HEAD.match(head)
        if not m:
            raise ValueError(f"Malformed function header: {head!r}")
        name = m.group("name")
        args = _parse_args(m.group("args"))
        return_type = m.group("ret").strip()

        intent, body = self._collect_intent_and_body(base_indent)
        is_hole = body.strip() in ("??", "??;")

        return Function(
            name=name, args=args, return_type=return_type,
            intent=intent, body=body, is_hole=is_hole,
        )

    def _parse_process(self, base_indent: int) -> Process:
        head_raw = self._advance()
        head = head_raw.strip()
        m = _PROC_HEAD.match(head)
        if not m:
            raise ValueError(f"Malformed process header: {head!r}")
        name = m.group("name")
        return_type = m.group("ret").strip()

        intent, body = self._collect_intent_and_body(base_indent)
        is_hole = body.strip() in ("??", "??;")

        return Process(
            name=name, return_type=return_type,
            intent=intent, body=body, is_hole=is_hole,
        )

    def _parse_let(self, base_indent: int) -> Let:
        # `let` may span multiple lines if the expression continues at deeper
        # indentation, e.g. a multi-line { ... } block.
        first = self._advance()
        m = _LET.match(first.strip())
        if not m:
            raise ValueError(f"Malformed let binding: {first!r}")
        expr_text = m.group("expr").strip()
        # If the expression contains an unbalanced opening bracket, gather
        # continuation lines that are more indented than the let.
        opens = expr_text.count("(") + expr_text.count("[") + expr_text.count("{")
        closes = expr_text.count(")") + expr_text.count("]") + expr_text.count("}")
        depth = opens - closes
        while depth > 0 and self._peek() is not None:
            nxt = self._peek()
            if self._indent(nxt) <= base_indent:
                break
            cont = self._advance()
            expr_text += "\n" + cont
            depth += (cont.count("(") + cont.count("[") + cont.count("{"))
            depth -= (cont.count(")") + cont.count("]") + cont.count("}"))
        return Let(
            name=m.group("name"),
            type_=(m.group("type") or "").strip() or None,
            expression=expr_text.strip(),
        )

    def _collect_intent(self, base_indent: int) -> tuple:
        """Collect intent/forbid/ensure/... clauses following a header."""
        intent = Intent()
        while True:
            nxt = self._peek()
            if nxt is None:
                break
            if self._indent(nxt) <= base_indent:
                break
            stripped = nxt.strip()
            if ":" not in stripped:
                break
            key, _, rest = stripped.partition(":")
            key = key.strip()
            if key not in {"intent", "forbid", "ensure", "requires",
                           "emits", "consumes", "guard"}:
                break
            try:
                payload, _ = _extract_quoted(rest)
            except ValueError:
                payload = rest.strip()
            setattr(intent, key, payload)
            self._advance()
        return intent, None

    def _collect_intent_and_body(self, base_indent: int) -> tuple:
        intent, _ = self._collect_intent(base_indent)
        # Expect a ≔ line.
        body_line = self._advance()
        m = _BIND.search(body_line)
        if not m:
            raise ValueError(f"Expected ≔ (or :=): {body_line!r}")
        body = body_line[m.end():].strip()
        # Collect any continuation lines at a deeper indent.
        while self._peek() is not None:
            nxt = self._peek()
            if self._indent(nxt) <= base_indent:
                break
            body += "\n" + self._advance()
        return intent, body


def parse(source: str):
    return Parser(source).parse()
