# New Code — grammar specification (v1.0)

This is the grammar of the surface syntax v1.0 accepts, written in EBNF. It is the reference for the parser ([`newcode/parser.py`](newcode/parser.py) for declarations, [`newcode/expr.py`](newcode/expr.py) for expressions), the language server, and the VS Code TextMate grammar. When those disagree, this document wins.

The grammar is split into two layers, the same way the implementation is:

  1. A **top-level layer** that is indentation-aware. It recognises `module`, `import`, `extern`, `fn`, `process`, `let`. It collects intent / forbid / ensure / requires / emits / consumes / guard clauses. It captures bodies as raw text after the bind token (`≔` or `:=`).
  2. An **expression layer** that is brace/paren-based, free-form, and Unicode-rich. It is invoked on every `let` RHS, every explicit body, and every REPL expression.

Everything a human writes in New Code is a **score**. The conductor writes the score; the orchestra (the compiler) plays it.

---

## 1. Conventions

- `A ::= B` — A is defined as B.
- `A | B` — one of A or B.
- `A?` — optional.
- `A*` — zero or more.
- `A+` — one or more.
- `( A B )` — grouping.
- `"lit"` — a literal token.
- UPPERCASE names are terminals; lowercase are non-terminals.

## 2. Lexical structure

```ebnf
source        ::= ( line NEWLINE )*

comment       ::= "※"  any*              ※ whole-line comment
                | "※※" any*              ※※ whole-line comment, emphatic

whitespace    ::= " " | "\t"
NEWLINE       ::= "\r\n" | "\n"
```

### 2.1 Identifiers

```ebnf
IDENT         ::= ( LETTER | "_" ) ( LETTER | DIGIT | "_" )*
DOTTED_IDENT  ::= IDENT ( "." IDENT )*
LETTER        ::= "A".."Z" | "a".."z"
DIGIT         ::= "0".."9"
```

### 2.2 Numeric literals

```ebnf
NUMBER        ::= SIGN? ( FLOAT | INT ) EXPONENT?
SIGN          ::= "+" | "-"
INT           ::= DIGIT+
FLOAT         ::= DIGIT+ "." DIGIT* | "." DIGIT+
EXPONENT      ::= ("e" | "E") SIGN? DIGIT+
```

### 2.3 String literals

```ebnf
STRING        ::= "\"" STRING_CHAR* "\""
                | "'"  STRING_CHAR* "'"
STRING_CHAR   ::= any character except the closing quote, with \" / \\ / \n / \t escapes
```

### 2.4 Type atoms

```ebnf
type          ::= TYPE_ATOM ( "(" type ( "," type )* ")" )?
                | "[" type "]"                                ※ list type
                | type ARROW type                             ※ function type
TYPE_ATOM     ::= "𝕎" | "ℝ" | "ℕ" | "ℤ" | "𝔹"
                | "Process" | "Entangled" | "Shape"
                | "List" | "Option" | "Tuple"
                | "Bool" | "Int" | "Float" | "Str" | "String" | "Number"
                | "Unit"
                | IDENT                                       ※ user-defined type
```

### 2.5 Intent strings

```ebnf
INTENT_STRING ::= "「" STRING_CONTENT "」"
                | "『" STRING_CONTENT "』"
                | "\"" STRING_CONTENT "\""
                | "'" STRING_CONTENT "'"
```

Corner brackets are preferred. Tools should emit them.

### 2.6 Structural tokens

```ebnf
BIND          ::= "≔" | ":="
ARROW         ::= "→" | "->"
HOLE          ::= "??"
LAMBDA        ::= "\\"           ※ lambda introducer, `\x -> body`
PIPE          ::= "|"
```

## 3. Top-level declarations

A score is a sequence of top-level declarations.

```ebnf
declaration   ::= module_decl
                | import_decl
                | extern_decl
                | function_decl
                | process_decl
                | let_decl
```

### 3.1 `let` — value bindings

```ebnf
let_decl      ::= "let" IDENT ( ":" type )? "=" expression
```

The expression is parsed by the expression layer (§4). Multi-line expressions are allowed: continuation lines are gathered as long as they are more indented than the `let` keyword and the running bracket depth is positive.

```newcode
let concert_a  : 𝕎 = w(f=440, A=1.0, phi=0.0, sigma=sine)
let chord = [
    w(f=440, A=1.0, sigma=sine),
    w(f=660, A=0.7, sigma=sine),
    w(f=880, A=0.5, sigma=sine),
]
```

### 3.2 `fn` — functions with intent blocks

```ebnf
function_decl ::= "fn" IDENT "(" arg_list? ")" ARROW type
                  intent_block
                  BIND function_body

arg_list      ::= arg ( "," arg )*
arg           ::= IDENT ":" type

function_body ::= HOLE                   ※ the compiler fills this in
                | expression             ※ explicit body
                | block                  ※ explicit multi-form body
```

Bodies that are not the hole are parsed by the expression layer (§4) and lowered to Python. The `python { … }` escape hatch is a first-class expression form (§4.4) — use it when you need a host call inline; never as a way around the expression grammar.

```ebnf
intent_block  ::= intent_clause*
intent_clause ::= INDENT CLAUSE_NAME ":" INTENT_STRING NEWLINE
CLAUSE_NAME   ::= "intent" | "forbid" | "ensure"
                | "requires" | "emits" | "consumes" | "guard"
```

The three canonical clauses are `intent` / `forbid` / `ensure` — the conductor's three gestures. The rest are optional and used by the richer compiler.

```newcode
fn amplify (signal : 𝕎, gain : ℝ) → 𝕎
    intent: 「scale the amplitude of signal by gain while preserving shape」
    forbid: 「do not modify phase」
    ensure: 「output shape equals input shape」
    ≔ ??
```

### 3.3 `process` — ongoing unfoldings

```ebnf
process_decl  ::= "process" IDENT ":" type
                  intent_block
                  BIND function_body
```

A process is a computation with its own internal time τ, realised lazily through sampling. The body returns a `Process`; intent-hole compilation for processes uses the same backends as functions (offline pattern matcher / Anthropic / snapshot).

### 3.4 `module` — scoped scores

```ebnf
module_decl   ::= "module" DOTTED_IDENT
                  intent_block?
                  INDENT declaration+ DEDENT
```

A module is a namespace with an optional intent block describing what the whole module is for. Its declarations are installed into the loading scope.

### 3.5 `import` — bringing in another module

```ebnf
import_decl   ::= "import" DOTTED_IDENT ( "as" IDENT )?
```

Modules are resolved against the source file's directory and a search path supplied by the loader.

```newcode
import audio.shapes
import host.numpy as np
```

`host.<module>` is special: it routes through the FFI bridge and returns a Python module object. Use it for NumPy, file I/O, anything outside the New Code surface.

### 3.6 `extern` — host escape blocks

```ebnf
extern_decl   ::= "extern" IDENT "{"
                  any_lines
                  "}"
```

A bracketed host body. The body is executed in the loading scope. Use it sparingly — it bypasses the expression grammar and the AST safety check.

```newcode
extern python {
    import numpy as np
    def to_array(samples):
        return np.asarray(samples, dtype=float)
}
```

## 4. Expression layer

The expression layer is parsed by [`newcode/expr.py`](newcode/expr.py) and lowered to Python for execution. Same grammar applies to `let` RHS, explicit `fn`/`process` bodies, and REPL input.

### 4.1 Atoms

```ebnf
atom          ::= NUMBER | STRING | bool_lit | unit_lit
                | "??"                              ※ hole expression
                | IDENT
                | wave_lit
                | list_lit
                | record_lit
                | "(" expression ")"

bool_lit      ::= "true" | "false"
unit_lit      ::= "()"
```

### 4.2 Composite literals

```ebnf
wave_lit      ::= "⟨" expression "," expression "," expression "," expression "⟩"
list_lit      ::= "[" ( expression ( "," expression )* ","? )? "]"
record_lit    ::= "{" ( record_field ( "," record_field )* ","? )? "}"
record_field  ::= IDENT "=" expression
```

`⟨ f , A , φ , σ ⟩` is the literal form for `𝕎`; it is sugar for `w(f=…, A=…, phi=…, sigma=…)`.

### 4.3 Postfix forms

```ebnf
postfix       ::= atom postfix_op*
postfix_op    ::= "(" arg_list_call? ")"            ※ call
                | "." IDENT                          ※ attribute
                | "[" expression "]"                 ※ index
arg_list_call ::= call_arg ( "," call_arg )* ","?
call_arg      ::= expression
                | IDENT "=" expression               ※ keyword argument
```

### 4.4 Operators (precedence climbing, tightest last)

| Operator              | Meaning                              | Precedence | Assoc |
|-----------------------|--------------------------------------|-----------:|-------|
| `or`                  | logical or                           | 1          | left  |
| `and`                 | logical and                          | 2          | left  |
| `not`                 | logical not (prefix)                 | 3          | —     |
| `==` `!=` `<` `<=` `>` `>=` | comparison                     | 4          | left  |
| `+` `-`               | arithmetic add / subtract            | 5          | left  |
| `⊕`                   | superpose (pointwise sum on 𝕎)       | 5          | left  |
| `⇝`                   | drift by δ                           | 5          | left  |
| `*` `/` `%`           | arithmetic                           | 6          | left  |
| `⊚`                   | oscillate (shape product on 𝕎)       | 6          | left  |
| `⟪·,·⟫`               | coherence (binary infix)             | 6          | left  |
| `**`                  | power                                | 7          | right |
| unary `-` `+`         | sign                                 | 8          | —     |
| unary `⁻`             | phase inversion (postfix on 𝕎)        | 9          | —     |
| `⌊·⌉`                 | collapse to scalar (matched-fix)     | 9          | —     |

ASCII fallbacks for the Unicode operators: `+:` (⊕), `*:` (⊚), `~>` (⇝), `[|...|]` (⌊·⌉), `<|...|>` (⟪·,·⟫), `dg` (d_γ), `!~` (postfix ⁻).

### 4.5 Conditional

```ebnf
if_expr       ::= "if" expression "then" expression "else" expression
```

### 4.6 Let-in

```ebnf
let_in        ::= "let" IDENT ( ":" type )? "=" expression "in" expression
```

### 4.7 Lambda

```ebnf
lambda_expr   ::= LAMBDA IDENT ( IDENT )* ARROW expression
```

### 4.8 Block

```ebnf
block         ::= "{" block_stmt ( ";" block_stmt )* ";"? "}"
block_stmt    ::= "let" IDENT "=" expression       ※ binding
                | expression                        ※ effect / value
```

The value of a block is the value of its last statement. Bindings inside a block are scoped to the block.

### 4.9 Match

```ebnf
match_expr    ::= "match" expression "with" "{"
                  match_case ( "," match_case )* ","?
                  "}"
match_case    ::= pattern ARROW expression
pattern       ::= NUMBER | STRING | bool_lit | unit_lit
                | IDENT                              ※ binds the scrutinee
                | "_"                                ※ wildcard
```

### 4.10 Python escape

```ebnf
py_block      ::= "python" "{" any_chars_with_balanced_braces "}"
```

Lowered as an immediate-evaluated Python expression / statement block. Use it for one-shot host escapes inside a `fn` or `let`. For a top-level escape, use the `extern` declaration (§3.6) instead.

## 5. Indentation

Indentation is structural at the top level only:

- Intent clauses of a declaration sit at any deeper indent than the header.
- The body following `≔` extends as long as subsequent lines are deeper than the header and the running bracket depth from `( [ {` is positive.
- Inside a `module`, declarations sit at any indent deeper than the `module` keyword.

The expression layer (§4) is **not** indentation-sensitive — it is brace/paren-based. A multi-line block expression lives between `{` and `}`; a multi-line list lives between `[` and `]`.

## 6. Reserved words

```
fn      process    let     module    import    extern
intent  forbid     ensure  requires  emits     consumes   guard
if      then       else    in        and       or         not
match   with       true    false
python
```

## 7. Tolerated variations

The parser is deliberately forgiving about:

- `≔` vs `:=` (bind).
- `→` vs `->` (arrow).
- 「…」, 『…』, `"…"`, `'…'` (intent-string quoting).
- Leading whitespace before a header line.
- Blank lines and comments anywhere.
- Mixed Unicode / ASCII operators in the same expression.

Tools should emit the canonical Unicode forms (`≔`, `→`, 「…」, `⊕`, `⊚`, etc.).

## 8. Reference examples

```newcode
※ a small score showing every layer.
import host.numpy as np

extern python {
    def gain_curve(n):
        import math
        return [0.5 + 0.5 * math.sin(i / n * 6.28) for i in range(n)]
}

let concert_a : 𝕎 = ⟨440, 1.0, 0.0, sine⟩
let curve     = gain_curve(8)

fn amplify (signal : 𝕎, gain : ℝ) → 𝕎
    intent: 「scale the amplitude of signal by gain while preserving shape」
    forbid: 「do not modify phase」
    ensure: 「output shape equals input shape」
    ≔ ??

fn shape_of (signal : 𝕎) → Shape
    intent: 「return the shape component of signal」
    ≔ {
        let f = signal.f;
        let A = signal.A;
        signal.sigma
    }

process pulse_train : 𝕎
    intent: 「emit concert_a every tick, no drift」
    ≔ ??
```
