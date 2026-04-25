"""
The New Code expression layer.

This module is what makes New Code an actual language rather than a thin
wrapper over Python ``eval()``. It provides:

  * a lexer that recognises the full Unicode-rich New Code surface
  * a recursive-descent parser that produces a typed AST
  * a transpiler that lowers the AST to safe Python source
  * a direct-evaluation interpreter for REPL input

Every body to the right of ``≔``, every ``let`` expression, and every
expression typed at the REPL prompt now passes through this module before
it touches Python's eval(). The Python eval() escape hatch is preserved
explicitly via ``python { ... }`` blocks; every other expression in a
.nc file is parsed, type-checked at the surface level, and lowered.

The design goals are:

  1. **Familiar.** Looks like F# / OCaml / Haskell-flavoured Python, with
     the added Unicode operators of New Code.
  2. **Lowering, not interpretation.** The transpiler emits clean Python
     so the existing AST safety check in compiler.py remains the security
     boundary, and so explicit bodies and AI-compiled bodies share an
     execution surface.
  3. **Total grammar.** Anything you'd want to write in a .nc file should
     be expressible without falling back to a python { } block.
  4. **Recoverable parse errors.** Syntax errors carry line/column info so
     the LSP can report them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple, Union


# =============================================================================
# Tokens
# =============================================================================

# Token kinds. We use string constants rather than an enum so error messages
# are immediately readable.
TK_NUMBER     = "NUMBER"
TK_STRING     = "STRING"
TK_IDENT      = "IDENT"
TK_KEYWORD    = "KEYWORD"
TK_OP         = "OP"
TK_LPAREN     = "LPAREN"
TK_RPAREN     = "RPAREN"
TK_LBRACE     = "LBRACE"
TK_RBRACE     = "RBRACE"
TK_LBRACK     = "LBRACK"
TK_RBRACK     = "RBRACK"
TK_COMMA      = "COMMA"
TK_SEMI       = "SEMI"
TK_COLON      = "COLON"
TK_DOT        = "DOT"
TK_ASSIGN     = "ASSIGN"
TK_BIND       = "BIND"        # ≔ or :=
TK_ARROW      = "ARROW"       # → or ->
TK_FATARROW   = "FATARROW"    # ⇒ or =>
TK_QUOTED     = "QUOTED"      # 「...」 or 『...』 (intent payloads)
TK_PYBLOCK    = "PYBLOCK"     # python { raw }
TK_HOLE       = "HOLE"        # ??
TK_LAMBDA     = "LAMBDA"      # λ or \
TK_FLOOR_L    = "FLOOR_L"     # ⌊
TK_FLOOR_R    = "FLOOR_R"     # ⌉
TK_NEWLINE    = "NEWLINE"
TK_EOF        = "EOF"


KEYWORDS = {
    "let", "in", "if", "then", "else", "fn", "process", "module", "import",
    "as", "extern", "python", "match", "with", "and", "or", "not", "true",
    "false", "True", "False", "intent", "forbid", "ensure", "requires",
    "emits", "consumes", "guard", "do", "end",
}


# Multi-character operators recognised greedily before single chars.
MULTI_OPS = [
    "≔", ":=", "==", "!=", "<=", ">=", "->", "→", "=>", "⇒",
    "⊕", "⊚", "⇝", "⌊", "⌉", "▶", "∥", "↺", "⁻", "**",
    "&&", "||",
]

SINGLE_OPS = set("+-*/%<>=&|^")


# =============================================================================
# Token dataclass
# =============================================================================

@dataclass
class Token:
    kind: str
    value: str
    line: int
    col: int

    def __repr__(self) -> str:
        return f"Token({self.kind}, {self.value!r}, {self.line}:{self.col})"


# =============================================================================
# Lexer
# =============================================================================

class LexError(Exception):
    def __init__(self, msg: str, line: int, col: int):
        super().__init__(f"{msg} at {line}:{col}")
        self.line = line
        self.col = col


class Lexer:
    """Convert source text to a stream of Token objects.

    The lexer is whitespace-insensitive *within an expression* — newlines are
    emitted as TK_NEWLINE tokens but the parser treats them as separators
    only between top-level forms, not inside an expression.
    """

    IDENT_START = re.compile(r"[A-Za-z_𝕎ℝℤℕ𝔹]")
    IDENT_CONT  = re.compile(r"[A-Za-z0-9_𝕎ℝℤℕ𝔹]")

    def __init__(self, source: str):
        self.src = source
        self.pos = 0
        self.line = 1
        self.col = 1
        self.tokens: List[Token] = []

    def lex(self) -> List[Token]:
        while self.pos < len(self.src):
            ch = self.src[self.pos]

            # Skip horizontal whitespace.
            if ch in " \t":
                self._advance(); continue

            # Newline.
            if ch == "\n":
                self._emit(TK_NEWLINE, "\n")
                self._advance()
                self.line += 1
                self.col = 1
                continue

            # Line comments: ※ ... \n   or   # ... \n
            if ch == "※" or ch == "#":
                while self.pos < len(self.src) and self.src[self.pos] != "\n":
                    self._advance()
                continue

            # Quoted intent payload: 「…」 or 『…』
            if ch in "「『":
                self._lex_quoted(ch); continue

            # String literal: "..." or '...'
            if ch in "\"'":
                self._lex_string(ch); continue

            # Number.
            if ch.isdigit() or (ch == "." and self._peek(1).isdigit()):
                self._lex_number(); continue

            # python { ... } raw escape — recognised by leading word.
            if (ch == "p" and self.src[self.pos:self.pos + 6] == "python"
                    and self._is_ident_boundary(self.pos + 6)):
                # Try to detect immediate "{" (after optional whitespace).
                save = (self.pos, self.line, self.col)
                self._advance(6)  # skip "python"
                # skip whitespace
                while self.pos < len(self.src) and self.src[self.pos] in " \t":
                    self._advance()
                if self.pos < len(self.src) and self.src[self.pos] == "{":
                    self._lex_pyblock(); continue
                # Restore — treat "python" as a plain identifier.
                self.pos, self.line, self.col = save
                # fall through to identifier lex

            # Identifiers / keywords.
            if self.IDENT_START.match(ch):
                self._lex_ident(); continue

            # Punctuation / parens / brackets.
            tok_map = {
                "(": TK_LPAREN, ")": TK_RPAREN,
                "{": TK_LBRACE, "}": TK_RBRACE,
                "[": TK_LBRACK, "]": TK_RBRACK,
                ",": TK_COMMA,  ";": TK_SEMI,
                ".": TK_DOT,
            }
            if ch in tok_map:
                self._emit(tok_map[ch], ch)
                self._advance()
                continue

            if ch == ":":
                # Check for := (bind alias).
                if self._peek(1) == "=":
                    self._emit(TK_BIND, ":=")
                    self._advance(2)
                else:
                    self._emit(TK_COLON, ":")
                    self._advance()
                continue

            # Lambda glyphs.
            if ch == "λ":
                self._emit(TK_LAMBDA, "λ"); self._advance(); continue
            if ch == "\\":
                # \\ is the ASCII lambda when followed by an identifier.
                self._emit(TK_LAMBDA, "\\"); self._advance(); continue

            # Floor brackets.
            if ch == "⌊":
                self._emit(TK_FLOOR_L, "⌊"); self._advance(); continue
            if ch == "⌉":
                self._emit(TK_FLOOR_R, "⌉"); self._advance(); continue

            # Multi-char operators.
            matched = False
            for op in MULTI_OPS:
                if self.src.startswith(op, self.pos):
                    if op in ("≔", ":="):
                        self._emit(TK_BIND, op)
                    elif op in ("→", "->"):
                        self._emit(TK_ARROW, op)
                    elif op in ("⇒", "=>"):
                        self._emit(TK_FATARROW, op)
                    elif op == "⌊":
                        self._emit(TK_FLOOR_L, op)
                    elif op == "⌉":
                        self._emit(TK_FLOOR_R, op)
                    else:
                        self._emit(TK_OP, op)
                    self._advance(len(op))
                    matched = True
                    break
            if matched:
                continue

            # Single-char operators.
            if ch in SINGLE_OPS:
                if ch == "=":
                    self._emit(TK_ASSIGN, "="); self._advance(); continue
                self._emit(TK_OP, ch)
                self._advance()
                continue

            raise LexError(f"unexpected character {ch!r}", self.line, self.col)

        self._emit(TK_EOF, "")
        return self.tokens

    # ----- helpers -----

    def _advance(self, n: int = 1) -> None:
        for _ in range(n):
            if self.pos < len(self.src):
                if self.src[self.pos] == "\n":
                    pass  # newlines are emitted as tokens; col reset there.
                else:
                    self.col += 1
                self.pos += 1

    def _peek(self, offset: int) -> str:
        i = self.pos + offset
        return self.src[i] if i < len(self.src) else ""

    def _is_ident_boundary(self, pos: int) -> bool:
        if pos >= len(self.src):
            return True
        return not self.IDENT_CONT.match(self.src[pos])

    def _emit(self, kind: str, value: str) -> None:
        self.tokens.append(Token(kind, value, self.line, self.col))

    def _lex_quoted(self, opener: str) -> None:
        closer = "」" if opener == "「" else "』"
        start_line, start_col = self.line, self.col
        self._advance()  # skip opener
        buf = []
        while self.pos < len(self.src) and self.src[self.pos] != closer:
            if self.src[self.pos] == "\n":
                self.line += 1
                self.col = 0
            buf.append(self.src[self.pos])
            self._advance()
        if self.pos >= len(self.src):
            raise LexError("unclosed quoted payload", start_line, start_col)
        self._advance()  # skip closer
        self.tokens.append(Token(TK_QUOTED, "".join(buf), start_line, start_col))

    def _lex_string(self, quote: str) -> None:
        start_line, start_col = self.line, self.col
        self._advance()  # opening quote
        buf = []
        while self.pos < len(self.src) and self.src[self.pos] != quote:
            ch = self.src[self.pos]
            if ch == "\\" and self._peek(1):
                esc = self._peek(1)
                escape_map = {"n": "\n", "t": "\t", "r": "\r",
                              "\\": "\\", "\"": "\"", "'": "'", "0": "\0"}
                buf.append(escape_map.get(esc, esc))
                self._advance(2)
                continue
            if ch == "\n":
                self.line += 1
                self.col = 0
            buf.append(ch)
            self._advance()
        if self.pos >= len(self.src):
            raise LexError("unterminated string", start_line, start_col)
        self._advance()  # closing quote
        self.tokens.append(Token(TK_STRING, "".join(buf), start_line, start_col))

    def _lex_number(self) -> None:
        start_line, start_col = self.line, self.col
        start = self.pos
        # Integer part.
        while self.pos < len(self.src) and self.src[self.pos].isdigit():
            self._advance()
        # Fractional part.
        if (self.pos < len(self.src) and self.src[self.pos] == "."
                and self._peek(1).isdigit()):
            self._advance()
            while self.pos < len(self.src) and self.src[self.pos].isdigit():
                self._advance()
        # Exponent.
        if self.pos < len(self.src) and self.src[self.pos] in "eE":
            self._advance()
            if self.pos < len(self.src) and self.src[self.pos] in "+-":
                self._advance()
            while self.pos < len(self.src) and self.src[self.pos].isdigit():
                self._advance()
        # Optional unit/imaginary suffix could go here in the future.
        text = self.src[start:self.pos]
        self.tokens.append(Token(TK_NUMBER, text, start_line, start_col))

    def _lex_ident(self) -> None:
        start_line, start_col = self.line, self.col
        start = self.pos
        while (self.pos < len(self.src)
               and self.IDENT_CONT.match(self.src[self.pos])):
            self._advance()
        text = self.src[start:self.pos]
        # ?? is a hole — handled here only if it was a bare identifier; the
        # canonical form is two question marks captured before this point.
        if text in KEYWORDS:
            if text in ("true", "True"):
                self.tokens.append(Token(TK_KEYWORD, "true", start_line, start_col))
            elif text in ("false", "False"):
                self.tokens.append(Token(TK_KEYWORD, "false", start_line, start_col))
            else:
                self.tokens.append(Token(TK_KEYWORD, text, start_line, start_col))
        else:
            self.tokens.append(Token(TK_IDENT, text, start_line, start_col))

    def _lex_pyblock(self) -> None:
        # Already consumed "python" + optional ws; current char must be "{".
        start_line, start_col = self.line, self.col
        depth = 0
        assert self.src[self.pos] == "{"
        self._advance()  # opening {
        depth = 1
        buf = []
        while self.pos < len(self.src) and depth > 0:
            ch = self.src[self.pos]
            if ch == "{":
                depth += 1
                buf.append(ch)
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    break
                buf.append(ch)
            else:
                if ch == "\n":
                    self.line += 1
                    self.col = 0
                buf.append(ch)
            self._advance()
        if self.pos >= len(self.src):
            raise LexError("unclosed python block", start_line, start_col)
        self._advance()  # closing }
        self.tokens.append(Token(TK_PYBLOCK, "".join(buf), start_line, start_col))


def lex(source: str) -> List[Token]:
    return Lexer(source).lex()


# =============================================================================
# Expression AST
# =============================================================================

@dataclass
class NumberLit:
    value: float
    line: int = 0
    col: int = 0


@dataclass
class StringLit:
    value: str
    line: int = 0
    col: int = 0


@dataclass
class BoolLit:
    value: bool
    line: int = 0
    col: int = 0


@dataclass
class UnitLit:
    line: int = 0
    col: int = 0


@dataclass
class NameRef:
    name: str
    line: int = 0
    col: int = 0


@dataclass
class Call:
    callee: Any
    args: List[Any]
    kwargs: List[Tuple[str, Any]] = field(default_factory=list)
    line: int = 0
    col: int = 0


@dataclass
class Attr:
    target: Any
    attr: str
    line: int = 0
    col: int = 0


@dataclass
class Index:
    target: Any
    index: Any
    line: int = 0
    col: int = 0


@dataclass
class BinOp:
    op: str
    left: Any
    right: Any
    line: int = 0
    col: int = 0


@dataclass
class UnaryOp:
    op: str
    operand: Any
    line: int = 0
    col: int = 0


@dataclass
class IfExpr:
    cond: Any
    then_branch: Any
    else_branch: Any
    line: int = 0
    col: int = 0


@dataclass
class LetIn:
    name: str
    type_: Optional[str]
    value: Any
    body: Any
    line: int = 0
    col: int = 0


@dataclass
class Lambda:
    params: List[str]
    body: Any
    line: int = 0
    col: int = 0


@dataclass
class Block:
    stmts: List[Any]      # LetStmt or expression
    result: Any           # final expression (or None for unit-returning)
    line: int = 0
    col: int = 0


@dataclass
class LetStmt:
    name: str
    type_: Optional[str]
    value: Any
    line: int = 0
    col: int = 0


@dataclass
class ListLit:
    elements: List[Any]
    line: int = 0
    col: int = 0


@dataclass
class RecordLit:
    fields: List[Tuple[str, Any]]
    line: int = 0
    col: int = 0


@dataclass
class WaveLit:
    """Convenience for ``w(f=..., A=..., phi=..., sigma=...)`` literals.

    Parsed into a Call node downstream — but we keep this distinct so the
    LSP and pretty-printer can render it as a literal."""
    fields: List[Tuple[str, Any]]
    line: int = 0
    col: int = 0


@dataclass
class PyBlock:
    """Raw Python escape hatch: ``python { ... }``."""
    source: str
    line: int = 0
    col: int = 0


@dataclass
class Floor:
    """The ⌊·⌉ collapse bracket, parsed as a function call to collapse()."""
    inner: Any
    line: int = 0
    col: int = 0


@dataclass
class Hole:
    """The ?? hole — only valid as a top-level body, never inside an expression."""
    line: int = 0
    col: int = 0


@dataclass
class Match:
    scrutinee: Any
    arms: List[Tuple[Any, Any]]   # (pattern, body) — pattern is an expr-AST
    line: int = 0
    col: int = 0


# =============================================================================
# Parser
# =============================================================================

class ParseError(Exception):
    def __init__(self, msg: str, line: int, col: int):
        super().__init__(f"{msg} at {line}:{col}")
        self.line = line
        self.col = col


# Operator precedence table. Higher number binds tighter.
PRECEDENCE = {
    "or":  1, "||": 1,
    "and": 2, "&&": 2,
    "==": 3, "!=": 3, "<": 3, "<=": 3, ">": 3, ">=": 3,
    "⊕": 4, "⊚": 5, "⇝": 5,
    "+":  6, "-":  6,
    "*":  7, "/":  7, "%": 7,
    "**": 8,   # right-associative power
    "▶":  3,   # process series — same level as comparisons; rarely mixed
    "∥":  3,   # process parallel
    "↺":  3,   # process feedback (postfix-like)
}

RIGHT_ASSOC = {"**"}


class Parser:
    """Recursive-descent parser producing an expression AST."""

    def __init__(self, tokens: List[Token]):
        self.tokens = tokens
        self.i = 0

    # ----- core helpers -----

    def _peek(self, offset: int = 0) -> Token:
        idx = self.i + offset
        if idx < len(self.tokens):
            return self.tokens[idx]
        return self.tokens[-1]  # EOF

    def _advance(self) -> Token:
        tok = self.tokens[self.i]
        if tok.kind != TK_EOF:
            self.i += 1
        return tok

    def _skip_newlines(self) -> None:
        while self._peek().kind == TK_NEWLINE:
            self._advance()

    def _expect(self, kind: str, value: Optional[str] = None) -> Token:
        tok = self._peek()
        if tok.kind != kind or (value is not None and tok.value != value):
            want = kind if value is None else f"{kind} {value!r}"
            raise ParseError(f"expected {want}, got {tok.kind} {tok.value!r}",
                             tok.line, tok.col)
        return self._advance()

    def _check(self, kind: str, value: Optional[str] = None) -> bool:
        tok = self._peek()
        if tok.kind != kind:
            return False
        if value is not None and tok.value != value:
            return False
        return True

    def _match(self, kind: str, value: Optional[str] = None) -> bool:
        if self._check(kind, value):
            self._advance()
            return True
        return False

    # ----- entry points -----

    def parse_expression(self) -> Any:
        """Parse a single expression. Used for explicit bodies and let RHS."""
        self._skip_newlines()
        expr = self._parse_expr()
        self._skip_newlines()
        # Allow trailing newlines/semicolons before EOF.
        while self._peek().kind in (TK_NEWLINE, TK_SEMI):
            self._advance()
        if self._peek().kind != TK_EOF:
            tok = self._peek()
            raise ParseError(f"unexpected trailing token {tok.value!r} after expression",
                             tok.line, tok.col)
        return expr

    # ----- expression hierarchy -----

    def _parse_expr(self) -> Any:
        return self._parse_let_or_if_or_lambda_or_match_or_binary()

    def _parse_let_or_if_or_lambda_or_match_or_binary(self) -> Any:
        tok = self._peek()
        if tok.kind == TK_KEYWORD:
            if tok.value == "let":
                return self._parse_let_in()
            if tok.value == "if":
                return self._parse_if()
            if tok.value == "match":
                return self._parse_match()
        if tok.kind == TK_LAMBDA:
            return self._parse_lambda()
        return self._parse_binary(0)

    def _parse_let_in(self) -> LetIn:
        kw = self._expect(TK_KEYWORD, "let")
        name_tok = self._expect(TK_IDENT)
        type_ = None
        if self._match(TK_COLON):
            type_ = self._parse_type_annotation()
        self._expect(TK_ASSIGN)
        value = self._parse_expr()
        self._skip_newlines()
        self._expect(TK_KEYWORD, "in")
        body = self._parse_expr()
        return LetIn(name_tok.value, type_, value, body, kw.line, kw.col)

    def _parse_if(self) -> IfExpr:
        kw = self._expect(TK_KEYWORD, "if")
        cond = self._parse_expr()
        self._skip_newlines()
        self._expect(TK_KEYWORD, "then")
        then_b = self._parse_expr()
        self._skip_newlines()
        self._expect(TK_KEYWORD, "else")
        else_b = self._parse_expr()
        return IfExpr(cond, then_b, else_b, kw.line, kw.col)

    def _parse_match(self) -> Match:
        kw = self._expect(TK_KEYWORD, "match")
        scrut = self._parse_expr()
        self._skip_newlines()
        self._expect(TK_KEYWORD, "with")
        arms: List[Tuple[Any, Any]] = []
        self._skip_newlines()
        while self._check(TK_OP, "|"):
            self._advance()  # |
            patt = self._parse_pattern()
            self._expect(TK_ARROW)
            body = self._parse_expr()
            arms.append((patt, body))
            self._skip_newlines()
        if not arms:
            raise ParseError("match expression must have at least one arm",
                             kw.line, kw.col)
        return Match(scrut, arms, kw.line, kw.col)

    def _parse_pattern(self) -> Any:
        # Patterns are a subset of expressions: literals and identifiers
        # (which bind), plus the wildcard "_".
        tok = self._peek()
        if tok.kind == TK_IDENT and tok.value == "_":
            self._advance()
            return NameRef("_", tok.line, tok.col)
        return self._parse_unary()

    def _parse_lambda(self) -> Lambda:
        tok = self._advance()  # λ or \
        params: List[str] = []
        while self._check(TK_IDENT):
            params.append(self._advance().value)
        if not params:
            raise ParseError("lambda requires at least one parameter",
                             tok.line, tok.col)
        self._expect(TK_ARROW)
        body = self._parse_expr()
        return Lambda(params, body, tok.line, tok.col)

    def _parse_binary(self, min_prec: int) -> Any:
        left = self._parse_unary()
        while True:
            tok = self._peek()
            op = self._binop_value(tok)
            if op is None:
                break
            prec = PRECEDENCE[op]
            if prec < min_prec:
                break
            self._advance()
            next_min = prec + (0 if op in RIGHT_ASSOC else 1)
            right = self._parse_binary(next_min)
            left = BinOp(op, left, right, tok.line, tok.col)
        return left

    def _binop_value(self, tok: Token) -> Optional[str]:
        if tok.kind == TK_OP and tok.value in PRECEDENCE:
            return tok.value
        if tok.kind == TK_KEYWORD and tok.value in ("and", "or"):
            return tok.value
        return None

    def _parse_unary(self) -> Any:
        tok = self._peek()
        if tok.kind == TK_OP and tok.value == "-":
            self._advance()
            operand = self._parse_unary()
            return UnaryOp("-", operand, tok.line, tok.col)
        if tok.kind == TK_OP and tok.value == "⁻":
            self._advance()
            operand = self._parse_unary()
            return UnaryOp("⁻", operand, tok.line, tok.col)
        if tok.kind == TK_KEYWORD and tok.value == "not":
            self._advance()
            operand = self._parse_unary()
            return UnaryOp("not", operand, tok.line, tok.col)
        if tok.kind == TK_FLOOR_L:
            self._advance()
            inner = self._parse_expr()
            self._expect(TK_FLOOR_R)
            return Floor(inner, tok.line, tok.col)
        return self._parse_postfix()

    def _parse_postfix(self) -> Any:
        node = self._parse_primary()
        while True:
            tok = self._peek()
            if tok.kind == TK_LPAREN:
                node = self._parse_call(node)
            elif tok.kind == TK_DOT:
                self._advance()
                attr_tok = self._expect(TK_IDENT)
                node = Attr(node, attr_tok.value, attr_tok.line, attr_tok.col)
            elif tok.kind == TK_LBRACK:
                self._advance()
                idx = self._parse_expr()
                self._expect(TK_RBRACK)
                node = Index(node, idx, tok.line, tok.col)
            else:
                break
        return node

    def _parse_call(self, callee: Any) -> Call:
        lp = self._expect(TK_LPAREN)
        args: List[Any] = []
        kwargs: List[Tuple[str, Any]] = []
        self._skip_newlines()
        if not self._check(TK_RPAREN):
            while True:
                self._skip_newlines()
                # keyword-arg lookahead: IDENT '=' expr (but not ==)
                if (self._peek().kind == TK_IDENT
                        and self._peek(1).kind == TK_ASSIGN):
                    name = self._advance().value
                    self._advance()  # =
                    val = self._parse_expr()
                    kwargs.append((name, val))
                else:
                    args.append(self._parse_expr())
                self._skip_newlines()
                if self._match(TK_COMMA):
                    continue
                break
        self._skip_newlines()
        self._expect(TK_RPAREN)
        return Call(callee, args, kwargs, lp.line, lp.col)

    def _parse_primary(self) -> Any:
        tok = self._peek()

        if tok.kind == TK_NUMBER:
            self._advance()
            try:
                value = float(tok.value) if "." in tok.value or "e" in tok.value.lower() else int(tok.value)
            except ValueError as exc:
                raise ParseError(f"bad number literal: {exc}", tok.line, tok.col)
            return NumberLit(value, tok.line, tok.col)

        if tok.kind == TK_STRING:
            self._advance()
            return StringLit(tok.value, tok.line, tok.col)

        if tok.kind == TK_KEYWORD and tok.value in ("true", "false"):
            self._advance()
            return BoolLit(tok.value == "true", tok.line, tok.col)

        if tok.kind == TK_PYBLOCK:
            self._advance()
            return PyBlock(tok.value, tok.line, tok.col)

        if tok.kind == TK_LPAREN:
            self._advance()
            self._skip_newlines()
            if self._check(TK_RPAREN):
                self._advance()
                return UnitLit(tok.line, tok.col)
            inner = self._parse_expr()
            self._skip_newlines()
            self._expect(TK_RPAREN)
            return inner

        if tok.kind == TK_LBRACK:
            return self._parse_list()

        if tok.kind == TK_LBRACE:
            return self._parse_brace()

        if tok.kind == TK_IDENT:
            # Could be an identifier or a wave literal w(...).
            if tok.value == "w" and self._peek(1).kind == TK_LPAREN:
                # Treat w(...) as a regular call so the runtime constructor
                # remains the source of truth, but tag it as a WaveLit if all
                # args are keyword args.
                callee = NameRef("w", tok.line, tok.col)
                self._advance()
                call = self._parse_call(callee)
                if not call.args and call.kwargs:
                    return WaveLit(call.kwargs, tok.line, tok.col)
                return call
            self._advance()
            return NameRef(tok.value, tok.line, tok.col)

        raise ParseError(f"unexpected token {tok.value!r}", tok.line, tok.col)

    def _parse_list(self) -> ListLit:
        lb = self._expect(TK_LBRACK)
        elems: List[Any] = []
        self._skip_newlines()
        if not self._check(TK_RBRACK):
            while True:
                self._skip_newlines()
                elems.append(self._parse_expr())
                self._skip_newlines()
                if self._match(TK_COMMA):
                    continue
                break
        self._skip_newlines()
        self._expect(TK_RBRACK)
        return ListLit(elems, lb.line, lb.col)

    def _parse_brace(self) -> Any:
        """A brace expression is either:
            - a record literal: { name = expr, ... }
            - a block:          { stmt; stmt; expr }
        We disambiguate by looking ahead: if the first significant tokens are
        IDENT followed by ASSIGN, it's a record. Otherwise, a block.
        """
        lb = self._expect(TK_LBRACE)
        self._skip_newlines()
        if self._check(TK_RBRACE):
            self._advance()
            return RecordLit([], lb.line, lb.col)
        # Lookahead: IDENT '=' (but not '==') and NOT followed by 'in' chain
        if (self._peek().kind == TK_IDENT
                and self._peek(1).kind == TK_ASSIGN):
            return self._parse_record_body(lb)
        return self._parse_block_body(lb)

    def _parse_record_body(self, lb: Token) -> RecordLit:
        fields: List[Tuple[str, Any]] = []
        while True:
            self._skip_newlines()
            name = self._expect(TK_IDENT).value
            self._expect(TK_ASSIGN)
            value = self._parse_expr()
            fields.append((name, value))
            self._skip_newlines()
            if self._match(TK_COMMA):
                continue
            break
        self._skip_newlines()
        self._expect(TK_RBRACE)
        return RecordLit(fields, lb.line, lb.col)

    def _parse_block_body(self, lb: Token) -> Block:
        stmts: List[Any] = []
        result: Any = UnitLit(lb.line, lb.col)
        while True:
            self._skip_newlines()
            if self._check(TK_RBRACE):
                break
            # let-statement form: `let x = expr;` — terminated by ;
            if self._check(TK_KEYWORD, "let"):
                # Distinguish let-in from let-stmt by lookahead for `in`
                # without committing to either yet. If the let has no `in`
                # before the next semicolon or close-brace, treat it as a stmt.
                if self._is_let_stmt():
                    stmts.append(self._parse_let_stmt())
                    continue
            expr = self._parse_expr()
            if self._match(TK_SEMI):
                stmts.append(expr)
                self._skip_newlines()
                if self._check(TK_RBRACE):
                    break
                continue
            # No terminator → this is the result expression.
            result = expr
            self._skip_newlines()
            break
        self._expect(TK_RBRACE)
        return Block(stmts, result, lb.line, lb.col)

    def _is_let_stmt(self) -> bool:
        """Return True if the `let` at the cursor is a let-statement (no `in`
        before next `;` or `}`). Look ahead conservatively."""
        depth = 0
        i = self.i + 1   # skip 'let'
        # Skip ident, optional ': type', '=', then scan expr boundary.
        while i < len(self.tokens):
            tok = self.tokens[i]
            if tok.kind == TK_LPAREN or tok.kind == TK_LBRACE or tok.kind == TK_LBRACK:
                depth += 1
            elif tok.kind == TK_RPAREN or tok.kind == TK_LBRACE or tok.kind == TK_RBRACK:
                depth -= 1
                if depth < 0:
                    return True
            if depth == 0:
                if tok.kind == TK_SEMI:
                    return True
                if tok.kind == TK_RBRACE:
                    return True
                if tok.kind == TK_KEYWORD and tok.value == "in":
                    return False
            i += 1
        return True

    def _parse_let_stmt(self) -> LetStmt:
        kw = self._expect(TK_KEYWORD, "let")
        name = self._expect(TK_IDENT).value
        type_ = None
        if self._match(TK_COLON):
            type_ = self._parse_type_annotation()
        self._expect(TK_ASSIGN)
        value = self._parse_expr()
        self._expect(TK_SEMI)
        return LetStmt(name, type_, value, kw.line, kw.col)

    def _parse_type_annotation(self) -> str:
        """Capture a type as raw text. Type-checking is best-effort; the
        v1.0 runtime doesn't enforce types yet beyond annotations on FFI.
        """
        depth = 0
        parts: List[str] = []
        while True:
            tok = self._peek()
            if tok.kind in (TK_EOF, TK_NEWLINE):
                break
            if depth == 0 and tok.kind in (TK_ASSIGN, TK_COMMA, TK_RPAREN,
                                            TK_BIND, TK_RBRACE, TK_RBRACK,
                                            TK_KEYWORD):
                if tok.kind == TK_KEYWORD and tok.value not in (
                    "in", "then", "else", "with",
                ):
                    parts.append(tok.value)
                    self._advance()
                    continue
                break
            if tok.kind == TK_LBRACK:
                depth += 1
            elif tok.kind == TK_RBRACK:
                depth -= 1
                if depth < 0:
                    break
            parts.append(tok.value)
            self._advance()
        return " ".join(parts).strip()


def parse_expression(source: str) -> Any:
    """Lex and parse a single New Code expression."""
    tokens = lex(source)
    return Parser(tokens).parse_expression()


# =============================================================================
# Transpiler: AST → Python source
# =============================================================================
#
# The transpiler emits Python source. We keep the output close to the New
# Code source so stack traces remain meaningful. Operator translation:
#
#   ⊕ → superpose(a, b)
#   ⊚ → oscillate(a, b)
#   ⇝ → drift(a, b)
#   ⌊x⌉ → collapse(x)
#   ⁻x  → invert(x)
#   ▶ → series(a, b)
#   ∥ → parallel(a, b)
#   ↺ → feedback(a, b)
#   λx -> e   →   (lambda x: <e>)
#   let x = a in b   →   (lambda x: <b>)(<a>)
#   { let x = a; b }  →   ((lambda x: <b>)(<a>))
#   match x with | p1 -> e1 | p2 -> e2  →  if-elif chain
#
# The output is wrapped to be either a single expression (for let RHS / REPL
# expressions) or a function body (for fn/process declarations).

class TranspileError(Exception):
    pass


_EXPR_BIN_PYOP = {
    "+": "+", "-": "-", "*": "*", "/": "/", "%": "%", "**": "**",
    "==": "==", "!=": "!=", "<": "<", "<=": "<=", ">": ">", ">=": ">=",
    "and": "and", "or": "or", "&&": "and", "||": "or",
}

_EXPR_BIN_FN = {
    "⊕": "superpose",
    "⊚": "oscillate",
    "⇝": "drift",
    "▶": "series",
    "∥": "parallel",
    "↺": "feedback",
}


def to_python_expr(node: Any) -> str:
    """Lower an AST to a single Python expression."""
    return _expr(node)


def to_python_function(name: str, params: List[str], body_ast: Any) -> str:
    """Lower a function body AST into a complete Python def block.

    The result is prefixed with `def name(params):\n` and the body is
    indented one level. The body itself is `return <expr>` or, if the body
    AST is a Block with statements, a sequence of assignments followed by
    a return.
    """
    lines = _function_body_lines(body_ast)
    indented = "\n".join("    " + ln for ln in lines)
    arglist = ", ".join(params)
    return f"def {name}({arglist}):\n{indented}\n"


def to_python_process_factory(name: str, body_ast: Any) -> str:
    """Lower a process declaration body. Same as a function with no args."""
    return to_python_function(name, [], body_ast)


def _function_body_lines(node: Any) -> List[str]:
    if isinstance(node, Block):
        out: List[str] = []
        for stmt in node.stmts:
            if isinstance(stmt, LetStmt):
                out.append(f"{stmt.name} = {_expr(stmt.value)}")
            else:
                out.append(_expr(stmt))
        if isinstance(node.result, UnitLit):
            out.append("return None")
        else:
            out.append(f"return {_expr(node.result)}")
        return out
    if isinstance(node, PyBlock):
        # If the entire body is a python { ... } block, splice it in.
        return _dedented_lines(node.source)
    return [f"return {_expr(node)}"]


def _dedented_lines(source: str) -> List[str]:
    import textwrap
    src = textwrap.dedent(source).strip("\n")
    return src.splitlines() if src else ["pass"]


def _expr(node: Any) -> str:
    if isinstance(node, NumberLit):
        return repr(node.value)
    if isinstance(node, StringLit):
        return repr(node.value)
    if isinstance(node, BoolLit):
        return "True" if node.value else "False"
    if isinstance(node, UnitLit):
        return "None"
    if isinstance(node, NameRef):
        return _safe_name(node.name)
    if isinstance(node, Call):
        callee = _expr(node.callee)
        parts = [_expr(a) for a in node.args]
        parts += [f"{k}={_expr(v)}" for k, v in node.kwargs]
        return f"{callee}({', '.join(parts)})"
    if isinstance(node, Attr):
        return f"({_expr(node.target)}).{node.attr}"
    if isinstance(node, Index):
        return f"({_expr(node.target)})[{_expr(node.index)}]"
    if isinstance(node, BinOp):
        op = node.op
        if op in _EXPR_BIN_PYOP:
            return f"({_expr(node.left)} {_EXPR_BIN_PYOP[op]} {_expr(node.right)})"
        if op in _EXPR_BIN_FN:
            fn = _EXPR_BIN_FN[op]
            return f"{fn}({_expr(node.left)}, {_expr(node.right)})"
        raise TranspileError(f"unknown binary operator {op!r}")
    if isinstance(node, UnaryOp):
        if node.op == "-":
            return f"(-({_expr(node.operand)}))"
        if node.op == "not":
            return f"(not ({_expr(node.operand)}))"
        if node.op == "⁻":
            return f"invert({_expr(node.operand)})"
        raise TranspileError(f"unknown unary operator {node.op!r}")
    if isinstance(node, Floor):
        return f"collapse({_expr(node.inner)})"
    if isinstance(node, IfExpr):
        return (f"({_expr(node.then_branch)} if {_expr(node.cond)} "
                f"else {_expr(node.else_branch)})")
    if isinstance(node, LetIn):
        # (lambda name: <body>)(<value>)
        return (f"((lambda {_safe_name(node.name)}: "
                f"{_expr(node.body)})({_expr(node.value)}))")
    if isinstance(node, Lambda):
        params = ", ".join(_safe_name(p) for p in node.params)
        return f"(lambda {params}: {_expr(node.body)})"
    if isinstance(node, Block):
        return _block_as_expression(node)
    if isinstance(node, ListLit):
        return f"[{', '.join(_expr(e) for e in node.elements)}]"
    if isinstance(node, RecordLit):
        # Lower records as dicts. Field names become keys.
        parts = ", ".join(f"{k!r}: {_expr(v)}" for k, v in node.fields)
        return "{" + parts + "}"
    if isinstance(node, WaveLit):
        parts = ", ".join(f"{k}={_expr(v)}" for k, v in node.fields)
        return f"w({parts})"
    if isinstance(node, PyBlock):
        return _python_block_as_expr(node.source)
    if isinstance(node, Match):
        return _match_as_expression(node)
    raise TranspileError(f"cannot lower {type(node).__name__}")


def _block_as_expression(block: Block) -> str:
    """Lower a { ... } block to a single Python expression by chaining
    lambdas. Statements that aren't `let` become discarded values."""
    if not block.stmts:
        return _expr(block.result)
    # Walk from innermost out.
    body = _expr(block.result) if not isinstance(block.result, UnitLit) else "None"
    for stmt in reversed(block.stmts):
        if isinstance(stmt, LetStmt):
            body = f"((lambda {_safe_name(stmt.name)}: {body})({_expr(stmt.value)}))"
        else:
            # Side-effecting expression; sequence with comma-trick (eval discards).
            body = f"((lambda __: {body})({_expr(stmt)}))"
    return body


def _python_block_as_expr(source: str) -> str:
    """Embed a python { ... } source as an expression.

    If the source is a single Python expression, use it as-is. Otherwise
    wrap it in `(lambda: <multi-line>)()` via exec() — we conservatively
    raise rather than allow statement-level escapes here; statement-level
    Python is only allowed at the body level (handled by _function_body_lines).
    """
    import ast as _ast
    src = source.strip()
    if not src:
        return "None"
    try:
        _ast.parse(src, mode="eval")
    except SyntaxError as exc:
        raise TranspileError(
            f"python {{ }} expression must be a single expression: {exc.msg}"
        ) from None
    return f"({src})"


def _match_as_expression(node: Match) -> str:
    """Lower match to a chained ternary. Patterns are equality-checked
    against the scrutinee unless they are a NameRef (which binds).
    """
    scrut = _expr(node.scrutinee)
    # Build from the back forward so the conditional chain reads naturally.
    expr = "(_ for _ in ()).throw(ValueError('match: no arm matched'))"
    for patt, body in reversed(node.arms):
        if isinstance(patt, NameRef) and patt.name == "_":
            # Wildcard — always matches.
            expr = _expr(body)
            continue
        if isinstance(patt, NameRef):
            # Bind: wrap body in a lambda that takes the binding name.
            expr = (f"((lambda {_safe_name(patt.name)}: {_expr(body)})({scrut}) "
                    f"if True else {expr})")
            continue
        # Literal/equality match.
        expr = f"({_expr(body)} if {scrut} == {_expr(patt)} else {expr})"
    return expr


_PYTHON_RESERVED = {
    "False", "None", "True", "and", "as", "assert", "async", "await",
    "break", "class", "continue", "def", "del", "elif", "else", "except",
    "finally", "for", "from", "global", "if", "import", "in", "is",
    "lambda", "nonlocal", "not", "or", "pass", "raise", "return", "try",
    "while", "with", "yield",
}


def _safe_name(name: str) -> str:
    """Map New Code identifiers to safe Python names."""
    if name in _PYTHON_RESERVED:
        return name + "_"
    # Unicode names are fine in Python 3.
    return name


# =============================================================================
# Direct evaluator (REPL convenience — not the primary execution path)
# =============================================================================

def evaluate(node: Any, env: Dict[str, Any]) -> Any:
    """Walk an expression AST and produce a value. Used by the REPL for
    direct evaluation. Production execution still goes through the Python
    transpiler so AST safety checks apply uniformly.
    """
    src = _expr(node)
    return eval(src, env)


def evaluate_source(source: str, env: Dict[str, Any]) -> Any:
    return evaluate(parse_expression(source), env)


# =============================================================================
# Convenience: detect whether a body is a pure expression or block
# =============================================================================

def parse_body(body_text: str) -> Any:
    """Parse a function/process body. Returns either an expression or a Block.

    Bodies in v1.0 may be:
      - a single expression: ``≔ amplify(signal, 2.0)``
      - a block:             ``≔ { let x = ...; ... }``
      - a python escape:     ``≔ python { ... }``
    """
    return parse_expression(body_text)
