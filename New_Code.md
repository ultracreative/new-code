# NEW CODE

**A Machine-Native Language for Human–AI Collaboration**

*A working specification, v0.1*

Dan Rodriguez · [UltraNarrative](https://ultranarrative.com) · [newcode.ultranarrative.com](https://newcode.ultranarrative.com) · [dan@ultranarrative.com](mailto:dan@ultranarrative.com) · April 2026

---

## Preface

Code was never natural to us. We naturalised it. Every programming language in existence is a compromise between what humans can read and what machines can execute, and for seventy years the compromise has favoured the humans. Keywords are English words. Operators are symbols from algebra. Control flow borrows its shape from natural-language imperatives: *if*, *while*, *return*. The machine, in all this, has been asked to understand us. It has done so by pretending we were more systematic than we are.

That compromise is ending. The rise of large language models has produced a species of machine that can hold far more context than any human, reason across wider conceptual distances, and generate code faster than we can review it. Asking such a machine to keep speaking Python is like asking a concert pianist to communicate in semaphore. The bandwidth is wrong, the abstraction is wrong, and the interface bottleneck is now on our side of the table.

New Code is a proposal for the other direction. It is a programming language whose primary reader is an AI system, whose primary writer is an AI system compiling from human intent, and whose source text is optimised for machine interpretation rather than human legibility. Humans do not write New Code line by line. We define what we want, what we forbid, and what must remain true; an AI compiler produces the New Code that satisfies those specifications. We then interpret the result the way a doctor interprets blood work: through diagnostics, functions, and components, not through fluent reading.

The language draws its primitive objects from Waveform Logic, a mathematical system developed in parallel work, in which numbers are not discrete symbols but oscillatory structures carrying frequency, amplitude, phase, and shape. It draws its execution model from Processism, the philosophical framework in which stasis is incoherent and process is fundamental. These two sources give New Code something no conventional language has: a substrate in which values are already dynamic, computation is already a transformation of structured objects rather than a shuffling of collapsed scalars, and the natural unit of execution is the unfolding of a process rather than the evaluation of an expression.

The specification that follows is a working draft. The syntax is concrete but subject to revision. The semantics are defined precisely where precision is possible and sketched where it is not. A full glossary is provided at the end. Anyone attempting to implement a compiler for this language will find gaps; the gaps are where the interesting work is.

What matters for now is the shape of the thing. New Code treats values as processes, functions as transformations of processes, and programs as the controlled unfolding of structured computation. It is not meant to replace Python or Rust or C. It is meant to be the language we speak to the machines that will, within a decade, be writing most of our code anyway. We may as well give them something good to work with.

---

## Table of Contents

1. [Design Principles](#1-design-principles)
2. [The Execution Model](#2-the-execution-model)
3. [Primitive Types](#3-primitive-types)
4. [Syntax](#4-syntax)
5. [Operators](#5-operators)
6. [Control Flow](#6-control-flow)
7. [Functions and Processes](#7-functions-and-processes)
8. [The Intent Layer](#8-the-intent-layer)
9. [Entanglement and Coupled State](#9-entanglement-and-coupled-state)
10. [Drift, Decay, and Temporal Semantics](#10-drift-decay-and-temporal-semantics)
11. [Collapse and the Interface to Conventional Systems](#11-collapse-and-the-interface-to-conventional-systems)
12. [Modules and Composition](#12-modules-and-composition)
13. [Error Model](#13-error-model)
14. [A Worked Example: Timbre Classification in New Code](#14-a-worked-example-timbre-classification-in-new-code)
15. [Use Cases](#15-use-cases)
16. [Relation to Existing Languages](#16-relation-to-existing-languages)
17. [Open Problems](#17-open-problems)
18. [Glossary](#18-glossary)

---

## 1. Design Principles

New Code rests on six principles. They are stated in order of priority: when two principles conflict, the earlier one wins.

**1. Process over state.** The fundamental unit of computation in New Code is not a value held in memory but a process unfolding over time. A variable in New Code does not *have* a value the way a Python variable has a value; it *is* a process whose current realisation can be sampled, whose trajectory can be transformed, and whose coupling to other processes can be observed. This is a direct consequence of Processism: stasis is not a legal state of the language. A value that is not changing is a degenerate case of a value that is, not the default against which change must be introduced.

**2. Structure over scalar.** Every value in New Code carries internal structure. Where a conventional language represents the number 440 as a single machine word, New Code represents it as a waveform number ⟨440, 1, 0, σ⟩ with explicit frequency, amplitude, phase, and shape components. Collapsing to a scalar is a legal operation, but it is a destructive one: information is lost, and the loss is made visible in the syntax. The default is to preserve structure. Collapse is opt-in.

**3. Intent as first-class.** New Code programs begin with an intent block. The intent block states what the program is for, what it must guarantee, and what it must not do. The compiler is required to produce code that provably satisfies the intent or to fail with a diagnostic explaining which intent it cannot satisfy. This is not documentation. It is part of the type system. A New Code function without an intent declaration is syntactically invalid.

**4. The compiler is the reader.** New Code is written for compilation by a capable AI system, not for direct human reading. Syntax is chosen for disambiguation and machine parsing, not for typographic beauty or keyboard ergonomics. Identifiers are long and explicit. Operators are non-ASCII where an ASCII alternative would introduce ambiguity. Whitespace is meaningful. The aesthetic is the aesthetic of a molecular formula, not a sonnet.

**5. Entanglement over dependency.** When two values in New Code are linked such that changes to one must propagate to the other, the language represents this as an entanglement relation between the values themselves, not as a dependency between the computations that produced them. Entanglement is symmetric, declarable, and enforced by the runtime. This eliminates entire categories of bug that arise when two variables are *supposed* to stay consistent but the language has no way to say so.

**6. Collapse is explicit and lossy.** Any operation that reduces a structured value to a scalar, a discrete event, or a fixed-point representation must use the collapse operator ⌊·⌉ and must declare what is lost. The language tracks collapse events in the program's type signature. A function that collapses its input is marked as such; a function that preserves structure is marked as such. Callers can reason about information loss without inspecting implementation.

---

## 2. The Execution Model

A New Code program is a directed graph of processes. Execution is not the sequential evaluation of statements but the continuous unfolding of the graph. Each node in the graph is a process; each edge is either a transformation (a process produces an input to another process) or an entanglement (two processes are coupled such that transformations of one induce transformations of the other).

### 2.1 Processes, not threads

A process in New Code is not a thread in the operating-system sense. It is the language's primitive unit of ongoing computation. A process has four components, mirroring the structure of a waveform number:

- A *frequency* component, describing how often the process produces observable output.
- An *amplitude* component, describing the magnitude or intensity of its output.
- A *phase* component, describing its offset relative to a reference process.
- A *shape* component, describing the functional form of its output over time.

A process may be dormant (frequency zero, amplitude zero) but it always has structural identity. Two dormant processes with different shape components are distinct objects, just as two waveform numbers with different σ are distinct numbers even when both are realising zero at a given instant.

### 2.2 The unfolding

A New Code program does not *run*. It *unfolds*. The compiler produces an execution graph; the runtime unfolds the graph by allowing each process to advance along its own internal time. Processes that are not coupled advance independently. Processes that are entangled advance in lockstep, with the coupling function Φ enforcing the relation between them.

The difference between "run" and "unfold" is not metaphor. A running program can be paused and resumed at an instruction boundary; an unfolding program can be *sampled* at any point along its trajectory, but it cannot be stopped mid-process without collapsing the process to a scalar (which is a lossy operation). This has real consequences for debugging: a New Code debugger does not step through instructions, it inspects the current realisation of a chosen process and optionally drifts the process to examine nearby trajectories.

### 2.3 No implicit global time

New Code has no global clock. Each process carries its own time parameter. When two processes must be coordinated, the coordination is expressed as entanglement, not as a shared clock. This eliminates a large class of race conditions but introduces a new class of problem: processes may become *desynchronised* (their phases drift apart under independent evolution). The language provides operators for re-coherence (`◈`) and for explicit synchronisation (`‖`), but does not enforce either by default.

### 2.4 Termination

A New Code program terminates when every process in its execution graph has either (a) reached a declared fixed point, (b) been collapsed to a scalar and consumed, or (c) drifted to the square-wave attractor sq, which is the fixed point of the drift operator. Termination by (c) is called *thermodynamic termination* and is the default fate of any process that is not externally sustained. This is the language-level expression of the Second Law: every process eventually dies to the same shape unless something keeps feeding it structure.

---

## 3. Primitive Types

New Code's primitive types are drawn from Waveform Logic. Each type is written with a type glyph followed by a parameter specification.

### 3.1 The waveform number: `𝕎`

The fundamental type. A value of type `𝕎` is a quadruple ⟨f, A, φ, σ⟩.

```
let carrier : 𝕎 = ⟨ 440.0, 1.0, 0.0, sine ⟩
let warped  : 𝕎 = ⟨ 220.0, 0.7, π/4, sawtooth ⟩
```

The parameters are, in order: frequency (positive real), amplitude (real), phase (in radians mod 2π), and shape (a symbol referring to a shape function, or a shape literal written with `{ ... }`).

Shape literals can be given as closed-form expressions:

```
let shape_custom : shape = { t ↦ tanh(sin(2π · t)) · exp(-|t - 0.5|) }
```

All shapes are unit-periodic by convention; non-periodic shape expressions are rejected at compile time.

### 3.2 The spectrum: `𝕎*`

A finite superposition of waveform numbers, representing a complex signal. Spectra are written with the superposition operator `⊕`:

```
let oboe_tone : 𝕎* = ⟨440, 0.82, 0, σ_fundamental⟩
              ⊕ ⟨880, 0.34, 0, σ_2nd⟩
              ⊕ ⟨1320, 0.21, π/3, σ_3rd⟩
```

Spectra support all operations defined on individual waveform numbers, distributing over the superposition where appropriate.

### 3.3 The shape: `shape`

A periodic function σ : ℝ → [-1, 1] with σ(t+1) = σ(t). Built-in shapes include `sine`, `square`, `triangle`, `sawtooth`, `pulse(d)` (pulse wave with duty cycle d), and `noise(seed)` (deterministic pseudo-random shape).

Custom shapes are introduced with the `shape` keyword:

```
shape σ_bell := { t ↦ sin(2π · t) · exp(-4 · (t - 0.5)²) }
```

### 3.4 The scalar: `ℝ`

The conventional real number. In New Code, `ℝ` is regarded as a degenerate case of `𝕎`: any `ℝ` value r is isomorphic to the waveform number ⟨1, r, 0, sine⟩ sampled at t=0. The language does not forbid scalar computation but does mark it as a collapsed type.

```
let plain : ℝ = 3.14159
```

A scalar can always be promoted to a waveform (`𝕎`) by combination with a shape; a waveform can only become a scalar through the collapse operator `⌊·⌉`.

### 3.5 The process: `proc<τ>`

A running computation that produces values of type τ. The type parameter is mandatory.

```
let heartbeat : proc<𝕎> = every ⟨1.0, 1.0, 0, pulse(0.1)⟩
```

Processes are introduced with `every` (producing a value at each cycle of its argument), `on` (producing a value when triggered by an event), or `while` (producing values while a condition holds).

### 3.6 The entangled pair: `⟨τ₁ ▷◁ τ₂⟩`

A pair of values linked by an entanglement relation. The two components cannot be updated independently; any transformation of one induces the coupled transformation on the other, as specified by a declared coupling function Φ.

```
let coupled : ⟨𝕎 ▷◁ 𝕎⟩ = entangle(violin_voice, cello_voice) via pitch_follow
```

### 3.7 The collapsed: `⌊τ⌉`

A wrapper type marking a value that has been collapsed from its full structural form. A function that accepts `⌊𝕎⌉` declares it will treat the input as a scalar; a function that accepts `𝕎` declares it will preserve structure. This is checked at compile time.

### 3.8 Composite types

New Code supports tuples `(τ₁, τ₂, ...)`, records `{ name : τ, name : τ }`, lists `[τ]`, and streams `stream<τ>` (lazy, potentially infinite sequences). These behave as in conventional functional languages, with the single restriction that any composite containing a `𝕎` or a `proc<τ>` inherits the non-collapsibility of its components.

---

## 4. Syntax

New Code's syntax is designed for unambiguous parsing by a machine. It is not pleasant to type. It is not meant to be. The compiler is expected to generate New Code from human intent specifications; humans inspecting the output are expected to use a rendering tool that prettifies it.

### 4.1 Lexical elements

Identifiers are any sequence of Unicode letters, digits, and the underscore, beginning with a letter. Reserved symbols include the mathematical glyphs used for operators (`⊚`, `⊕`, `⇝`, `▷◁`, `⌊·⌉`, `◈`, `‖`) and the structural glyphs used for types (`𝕎`, `ℝ`, `⟨`, `⟩`, `↦`).

Comments begin with `※` and run to end of line. Block comments are bracketed with `《 ... 》`. Comments are stripped by the compiler and have no semantic effect.

Whitespace is significant at the block level: indentation defines scope. Within a line, whitespace is insignificant.

### 4.2 Literals

Waveform literals are written in angle-brackets with four components separated by commas:

```
⟨ 440, 1.0, 0, sine ⟩
```

Scalar literals are written as decimal numerals with optional exponent: `3.14`, `6.022e23`. Scalar literals are of type `ℝ` unless annotated.

Shape literals use brace syntax: `{ t ↦ expr }`.

String literals are bracketed with `「` and `」`. Strings are primarily used for tagging and diagnostics; they are not a primary data type.

### 4.3 Declarations

A variable declaration has the form:

```
let NAME : TYPE = EXPRESSION
```

A process declaration has the form:

```
process NAME : TYPE ≔ EXPRESSION
```

The difference: a `let` binding is a single realisation of a value; a `process` declaration is an ongoing unfolding whose current value is sampled at read-sites. Sampling is written with a trailing question mark: `NAME?` gives the current realisation of the process at the point of evaluation.

A function declaration has the form:

```
fn NAME (ARG₁ : TYPE₁, ARG₂ : TYPE₂) → RETURN_TYPE
    intent: 「what this function is for」
    forbid: 「what this function must not do」
    ensure: 「invariant this function maintains」
    ≔ EXPRESSION
```

The `intent`, `forbid`, and `ensure` clauses are mandatory for any function exposed outside its module. Private functions (prefixed with `_`) may omit them.

### 4.4 Blocks and scope

Blocks are introduced by indentation after a declaration header. Scope is lexical. There is no `return` keyword; the final expression of a block is its value.

```
fn amplify (w : 𝕎, gain : ℝ) → 𝕎
    intent: 「scale the amplitude of w by gain while preserving shape and frequency」
    forbid: 「do not modify phase」
    ensure: 「output shape equals input shape」
    ≔
        let ⟨f, A, φ, σ⟩ = w
        ⟨f, A · gain, φ, σ⟩
```

Note the destructuring bind on the waveform number. Any quadruple-typed value can be destructured this way.

---

## 5. Operators

### 5.1 Superposition: `⊕`

Pointwise sum of waveform realisations. Commutative and associative. Identity: the zero-amplitude waveform.

```
let combined : 𝕎* = voice_1 ⊕ voice_2 ⊕ voice_3
```

### 5.2 Oscillation product: `⊚`

Shape-composing multiplication. Commutative, not associative. See Waveform Logic specification for full semantics.

```
let modulated : 𝕎 = carrier ⊚ modulator
```

Because `⊚` is non-associative, New Code evaluates chains of `⊚` left-to-right by default. Parentheses override. A compiler warning is issued for any unparenthesised chain of three or more `⊚` applications.

### 5.3 Phase inversion: `⁻`

Unary postfix. Shifts phase by π. Provides the additive inverse under superposition.

```
let cancelled : 𝕎 = signal ⊕ signal⁻    ※ yields zero-amplitude waveform
```

### 5.4 Drift: `⇝`

Infix. Applies the drift operator with a scalar parameter.

```
let aged : 𝕎 = fresh_signal ⇝ 0.3
```

Drift simultaneously shifts frequency, decays amplitude, rotates phase, and deforms shape toward the square-wave attractor. See Section 10 for temporal semantics.

### 5.5 Coherence: `⟪·,·⟫`

Binary, prefix with bracket syntax. Returns a scalar of type `ℝ` measuring the shape-sensitive correlation of two waveforms.

```
let similarity : ℝ = ⟪ oboe_sample, clarinet_sample ⟫
```

Note that `⟪·,·⟫` produces a scalar, which is a collapse. The compiler will flag this in any type signature that claims to preserve structure.

### 5.6 Coherence distance: `d_γ`

Derived from coherence; gives a non-Euclidean distance metric on `𝕎`.

```
let how_different : ℝ = d_γ(wave_a, wave_b)
```

### 5.7 Entanglement: `▷◁`

Declarative, used in type signatures and in the `entangle` primitive. Not an operator in the evaluation sense; it expresses a constraint between two processes.

```
let pair : ⟨𝕎 ▷◁ 𝕎⟩ = entangle(left_channel, right_channel) via stereo_field
```

### 5.8 Re-coherence: `◈`

Unary, applied to a pair of processes that have drifted out of phase. Restores phase alignment without altering other parameters.

```
◈(process_a, process_b)
```

This is expensive and may fail if the processes have drifted beyond the identifiability horizon; the failure mode is a compile-time warning and a runtime fault if attempted.

### 5.9 Synchronisation: `‖`

Binary. Forces two processes to advance in lockstep until released.

```
voice_1 ‖ voice_2
    ※ both advance together for the duration of this block
```

### 5.10 Collapse: `⌊·⌉`

Unary bracket syntax. Reduces a waveform number to a scalar by taking its amplitude-weighted coherence with the unit oscillator `e₀`.

```
let plain_number : ℝ = ⌊ complex_wave ⌉
```

Collapse is irreversible, lossy, and explicit. Any function containing `⌊·⌉` in its body inherits the collapse marker in its type signature.

### 5.11 Operator precedence

From tightest to loosest:

1. Unary postfix: `⁻`, `?`
2. Bracket operators: `⌊·⌉`, `⟪·,·⟫`
3. Oscillation product: `⊚`
4. Drift: `⇝`
5. Superposition: `⊕`
6. Synchronisation: `‖`
7. Entanglement declaration: `▷◁`

Explicit parentheses `( ... )` override precedence. Because `⊚` is non-associative, chains of three or more require explicit grouping.

---

## 6. Control Flow

New Code has limited control flow. Most of what conventional languages do with branching is expressed instead through process composition. What remains is minimal.

### 6.1 Conditional evaluation: `when`

`when` is an expression, not a statement. It evaluates a condition and returns one of two branches. Both branches must have the same type.

```
let response : 𝕎 = when signal_strength > threshold
                   then amplified_signal
                   else silence
```

A `when` without an `else` is a type error.

### 6.2 Pattern matching: `case`

`case` destructures values against patterns. Patterns can match waveform components, ranges, shapes, or nested structure.

```
case incoming of
    ⟨f, _, _, sine⟩ when f < 100        ↦ handle_sub_bass(incoming)
    ⟨f, A, _, _⟩ when A < 0.01          ↦ noise_floor()
    ⟨_, _, _, σ⟩                        ↦ generic_processor(σ, incoming)
```

The compiler verifies exhaustiveness. Non-exhaustive cases are a compile error, not a warning.

### 6.3 Iteration: `fold`

New Code has no `for` or `while` loop in the conventional sense. Iteration over finite structure is expressed as a fold:

```
let combined : 𝕎* = voices fold with ⊕ from silence
```

For ongoing iteration over a stream, use process composition (Section 7).

### 6.4 Guards and preconditions

A function may declare guards that must hold at entry:

```
fn divide_safely (a : ℝ, b : ℝ) → ℝ
    intent: 「divide a by b, rejecting zero divisors」
    forbid: 「produce NaN or infinity」
    ensure: 「result is finite」
    guard: b ≠ 0
    ≔ a / b
```

A violated guard produces a runtime fault of a declared fault type.

---

## 7. Functions and Processes

### 7.1 Pure functions

A function declared with `fn` is pure: given the same input, it returns the same output. Purity is enforced; attempting to read external state from within a `fn` is a compile error.

### 7.2 Processes

A process is introduced with `process` and is permitted to have internal state, external effects, and ongoing unfolding. The cost is that a process must declare its interaction interface explicitly.

```
process audio_in : proc<𝕎>
    intent: 「continuously sample microphone input as waveform」
    emits: 𝕎 at 48000 Hz
    consumes: hardware_channel<mic>
    ≔ ...
```

The `emits` clause specifies the output rate and type; the `consumes` clause specifies external resources. A process without these clauses is a compile error.

### 7.3 Process composition

Processes compose through three primitive combinators:

**Series (`▶`):** The output of one process feeds the input of the next.
```
let pipeline : proc<𝕎> = audio_in ▶ equaliser ▶ compressor
```

**Parallel (`∥`):** Two processes run independently, producing a pair.
```
let stereo : proc<(𝕎, 𝕎)> = left_channel ∥ right_channel
```

**Feedback (`↺`):** A process's output is fed back into its input with a specified delay.
```
let delay_line : proc<𝕎> = reverb ↺ by 0.1s
```

### 7.4 Higher-order functions

Functions may accept and return other functions. Higher-order-ness interacts with the intent system: a higher-order function must declare constraints on the intents of its function arguments.

```
fn apply_to_signal (f : fn(𝕎) → 𝕎, w : 𝕎) → 𝕎
    intent: 「apply a shape-preserving transformation f to w」
    requires: f.ensure contains 「preserves shape」
    ≔ f(w)
```

The `requires` clause is checked at compile time against the intent declarations of any function passed in.

### 7.5 Anonymous functions

Lambda syntax uses `↦`:

```
let doubler : fn(𝕎) → 𝕎 = λ w ↦ amplify(w, 2.0)
```

Anonymous functions cannot carry full `intent`/`forbid`/`ensure` clauses and therefore cannot be passed to higher-order functions that require them. This is by design: consequential transformations must be named and specified.

---

## 8. The Intent Layer

The intent layer is what distinguishes New Code from every language preceding it. It is where humans, in practice, actually write.

### 8.1 What the intent layer is

Every function, process, and module in New Code carries three mandatory declarations:

- `intent`: what the unit of code is for, stated as a natural-language sentence or a formal predicate.
- `forbid`: what the unit of code must not do, stated as a constraint.
- `ensure`: an invariant the unit of code guarantees to maintain.

These declarations are not comments. They are parsed, type-checked against the body of the code, and verified by the compiler. The compiler is an AI system capable of natural-language understanding; it reads the intent clause, compares it to the implementation, and either confirms the match or rejects the program with a diagnostic.

### 8.2 How humans write New Code

In practice, a human does not write the body of a New Code function. The human writes the intent block:

```
fn extract_voiced_segments (audio : proc<𝕎>) → stream<𝕎*>
    intent: 「segment incoming audio into regions where human voice is present」
    forbid: 「include segments shorter than 80 ms; include non-voice transients」
    ensure: 「each output segment has sustained pitch detectable via coherence with vocal shapes」
    ≔ ??
```

The `≔ ??` is a hole. The compiler fills it. If the compiler can produce an implementation that satisfies the three declarations, it does so and the program is complete. If it cannot, it reports what it cannot satisfy and asks the human to refine the intent.

This is how the language is meant to be used. The human specifies; the AI compiler implements. The New Code body is the shared artefact: readable by machines, inspectable by humans through tooling, verifiable against the intent.

### 8.3 Intent as type

The intent declarations are part of the function's type. A function signature in New Code is not just `(τ₁, τ₂) → τ₃`; it is `(τ₁, τ₂) → τ₃ with { intent: ..., forbid: ..., ensure: ... }`. Two functions with identical input and output types but different intents are different types. This matters for higher-order composition: you cannot pass a function whose intent is `「compress audio dynamically」` where a function whose intent is `「apply a shape-preserving transformation」` is required, even if the raw types match.

### 8.4 Intent inheritance

Modules declare their own intent clauses, which are inherited by contained functions as a constraint. A function whose local intent contradicts the containing module's intent is a compile error. This provides coarse-grained guardrails at the architectural level.

### 8.5 The limits of intent

Intent declarations are natural-language-anchored, and natural language is imprecise. The compiler handles ambiguity by producing multiple candidate implementations and either selecting by secondary criteria (performance, concision) or surfacing the ambiguity to the human. The language does not pretend to resolve the general problem of specification; it pushes as much as possible into the compiler and surfaces the rest.

---

## 9. Entanglement and Coupled State

### 9.1 What entanglement is

Two values in New Code are *entangled* when there exists a declared coupling function Φ such that any transformation of one induces Φ on the other. Entanglement is not quantum-mechanical. It is the waveform-logic entanglement relation, lifted into the type system of the language.

### 9.2 Declaring entanglement

Entanglement is declared at the point of pair creation:

```
let stereo_field : ⟨𝕎 ▷◁ 𝕎⟩ = entangle(L, R) via φ_haas
```

The `via` clause names the coupling function. The coupling function must be a pure `fn(𝕎) → 𝕎` and must be declared with its own intent block. Common coupling functions are provided in the standard library (pitch-follow, amplitude-mirror, phase-opposition, haas-delay) and custom ones can be written.

### 9.3 Transforming entangled values

Any operation on one component of an entangled pair propagates automatically:

```
let new_pair = amplify(stereo_field.left, 2.0)
    ※ the right channel is also amplified, according to φ_haas
```

Attempting to transform one component without propagation requires explicit disentanglement:

```
let ⟨L, R⟩ = disentangle(stereo_field)
    ※ now L and R are independent
```

Disentanglement is a lossy operation: the coupling function is discarded and cannot be automatically restored.

### 9.4 Why entanglement matters

Entire classes of bug in conventional languages arise because two values are *supposed* to stay consistent but the language has no way to say so. Model-view pairs in UI code, corresponding halves of a transaction, left and right stereo channels, the forwards and backwards pointers of a linked list. All of these are entangled in the domain; none of them are entangled in the language. New Code makes the entanglement explicit and enforced.

### 9.5 Entanglement is not transitive

If `A ▷◁ B` and `B ▷◁ C`, it is *not* the case that `A ▷◁ C` unless separately declared. This is a deliberate restriction drawn from the Waveform Logic axioms (A7). It prevents entanglement from propagating silently across a program.

---

## 10. Drift, Decay, and Temporal Semantics

### 10.1 Time in New Code

Each process carries its own time parameter `τ`. There is no global clock. A process's τ advances monotonically at a rate determined by its declared frequency; processes with `f = 0` are dormant and their τ does not advance.

### 10.2 The drift operator

Drift (`⇝`) takes a process and a scalar δ and returns a process that has been advanced by δ units along the drift trajectory. This is distinct from waiting δ units of wall-clock time. Drift deforms the process:

- Frequency shifts by δA (amplitude-modulated frequency drift).
- Amplitude decays by a factor of `exp(-|δ|)`.
- Phase rotates by δf.
- Shape deforms toward the square-wave attractor by factor |δ|.

A process drifted by δ = 0 is unchanged. A process drifted by a large δ converges toward the sq shape, the terminal configuration of all oscillation.

### 10.3 Uses of drift

Drift is used to model three distinct phenomena that conventional languages handle separately:

**Ageing:** Applying `⇝` with increasing δ over wall-clock time simulates the gradual degradation of a signal, the slow loss of information in a codec, the decay of a memory. This is used wherever temporal realism matters.

**Analysis:** Drifting a process and sampling the result reveals how robust its identity is. The δ at which two processes become indistinguishable under coherence distance is the *identifiability horizon*, a quantity useful in classification, authentication, and similarity search.

**Thermodynamic termination:** A process that is not externally sustained drifts, by default, toward sq. This is the language's expression of the Second Law: without input, every process dies to the same shape. Terminating a process cleanly is done by letting it drift rather than by aborting.

### 10.4 Synchronisation primitives

Because there is no global clock, coordinating processes requires explicit synchronisation. Three primitives:

- `‖` (forced synchronisation): two processes advance in lockstep for the duration of a block.
- `◈` (re-coherence): re-aligns phases of two processes that have drifted apart.
- `await` (event-triggered): a process pauses until another process emits a specified value.

```
await pitch_tracker emits ⟨f, _, _, _⟩ where f > 1000
```

---

## 11. Collapse and the Interface to Conventional Systems

### 11.1 Why collapse exists

New Code must be able to interoperate with conventional systems. Most external APIs expect scalars: an integer file descriptor, a floating-point sample value, a discrete Boolean. The collapse operator is the bridge.

### 11.2 The collapse operation

`⌊w⌉` takes a waveform number and returns its amplitude-weighted coherence with the unit oscillator:

```
⌊ ⟨f, A, φ, σ⟩ ⌉ = A · γ(⟨f, A, φ, σ⟩, e₀)
```

where `e₀ = ⟨1, 1, 0, sine⟩`. The result is a real number. The mapping is many-to-one: many distinct waveforms collapse to the same scalar.

### 11.3 Collapse markers in types

Any function that performs a collapse inherits a collapse marker:

```
fn peak_detector (w : 𝕎) → ⌊ℝ⌉
    intent: 「identify the peak amplitude of w as a scalar」
    forbid: 「claim to preserve structure」
    ensure: 「output is A of input」
    ≔ ⌊w⌉
```

The return type `⌊ℝ⌉` indicates that the scalar is the product of a collapse operation, and that structural information has been discarded. Callers are required to acknowledge this by pattern-matching on the marker:

```
let ⌊peak⌉ = peak_detector(signal)
```

### 11.4 Alternative collapse maps

Different domains need different collapses. The language provides:

- `⌊·⌉_amp`: amplitude only (equivalent to default)
- `⌊·⌉_freq`: frequency only
- `⌊·⌉_rms`: root-mean-square over one period
- `⌊·⌉_centroid`: spectral centroid

Custom collapse maps can be declared with the `collapse` keyword:

```
collapse ⌊·⌉_custom : 𝕎 → ℝ
    intent: 「extract the magnitude of the third harmonic」
    ≔ λ w ↦ ⟪ w, ⟨3·f₀(w), 1, 0, sine⟩ ⟫
```

### 11.5 Foreign function interface

External functions are imported through an FFI block that specifies the collapse at the boundary:

```
foreign fn write_audio_file(path : ⌊string⌉, samples : ⌊[ℝ]⌉) → ⌊unit⌉
    from 「libsndfile」
```

All FFI-crossing values are collapsed. The compiler inserts the collapse operations automatically but warns on any information-rich type (`𝕎`, `𝕎*`, `proc<·>`) that is being silently reduced.

---

## 12. Modules and Composition

### 12.1 Module declaration

A module is declared with `module NAME` followed by an intent block and a body:

```
module audio.analysis
    intent: 「provide primitives for analysis of incoming audio streams」
    forbid: 「produce outputs that claim precision beyond the numerical floor of the input」
    ensure: 「all exported functions are shape-preserving or explicitly marked as collapsing」

    export fn spectral_centroid ...
    export fn onset_detection ...
```

### 12.2 Imports

Imports are explicit. There is no global namespace.

```
import audio.analysis.spectral_centroid as centroid
import waveform.algebra.{⊚, ⊕, ⇝}
```

The compiler rejects any unused import. Wildcards are not permitted.

### 12.3 Versioning

Every module has a version declaration. Version-incompatible imports are a compile error, not a runtime one.

### 12.4 Composition rules

A module's intent propagates to all contained functions as a containing constraint. A function whose local intent contradicts its module's intent is a compile error. This enforces architectural coherence at the language level.

---

## 13. Error Model

### 13.1 No exceptions

New Code has no exception mechanism. A function that may fail declares its failure modes in its return type.

```
fn parse_frequency (source : ⌊string⌉) → 𝕎 | fault<parse>
    intent: 「parse a textual frequency specification into a waveform number」
    forbid: 「produce silent defaults on malformed input」
    ensure: 「failure cases are explicit」
    ≔ ...
```

The `|` is sum type construction. Callers must pattern-match to handle both branches.

### 13.2 Fault types

Faults are structured values, not strings. A fault has a type (here, `parse`), a location (file and position), and a payload describing the specific failure.

```
case parse_frequency(「four forty」) of
    ⟨f, _, _, _⟩          ↦ use_it(f)
    fault<parse>(location, payload) ↦ diagnose(location, payload)
```

### 13.3 Thermodynamic termination is not a fault

When a process drifts to sq and terminates, this is not a failure. It is the natural end state of any unsustained process. Handlers that want to restart such processes must explicitly re-seed them.

### 13.4 Compiler diagnostics

The compiler produces diagnostics as structured values that can be inspected programmatically. The toolchain includes an AI-backed explainer that renders diagnostics as natural-language explanations for human consumption.

---

## 14. A Worked Example: Timbre Classification in New Code

This example implements the timbre classification problem from the Waveform Logic worked example, rewritten in New Code. The goal: given two recorded instruments playing the same pitch, identify which is which.

```
module audio.timbre
    intent: 「classify musical instruments by timbre, independent of pitch」
    forbid: 「rely on features that collapse shape information before comparison」
    ensure: 「classifications are stable under drift up to the declared identifiability horizon」

    import waveform.algebra.{⊚, ⟪·,·⟫, d_γ, ⇝}
    import audio.capture.mic_input

    ※ an instrument signature is a prototype waveform for a known instrument
    record signature ≔ { name : ⌊string⌉, prototype : 𝕎 }

    fn classify (sample : 𝕎, known : [signature]) → signature | fault<no_match>
        intent: 「identify the instrument whose prototype has smallest coherence distance to sample」
        forbid: 「return a match if the best distance exceeds the ambiguity threshold 0.65」
        ensure: 「output is the unique nearest signature, or a no-match fault」
        ≔
            let distances : [(signature, ℝ)] =
                known map (λ s ↦ (s, d_γ(sample, s.prototype)))

            let best = distances fold-min by second

            when second(best) > 0.65
                then fault<no_match>(「ambiguous timbre」, distances)
                else first(best)

    fn fingerprint (w : 𝕎) → 𝕎
        intent: 「produce a unique morphological fingerprint of w」
        forbid: 「collapse shape before the fingerprint is computed」
        ensure: 「fingerprint is invariant under amplitude scaling」
        ≔
            let e₀ : 𝕎 = ⟨1, 1, 0, sine⟩
            normalise(w ⊚ e₀)

    fn identifiability_horizon (w : 𝕎, threshold : ℝ) → ℝ
        intent: 「find the smallest drift δ at which w becomes unrecognisable」
        forbid: 「report a horizon if the process fails to converge within 100 probe steps」
        ensure: 「output δ satisfies d_γ(w, w ⇝ δ) ≥ threshold」
        ≔
            process probe : proc<(ℝ, ℝ)> =
                every ⟨100, 1, 0, pulse(0.01)⟩
                produce (δ, d_γ(w, w ⇝ δ)) for δ ∈ [0, 0.01, 0.02, ...]

            first(probe where second ≥ threshold)

    export classify, fingerprint, identifiability_horizon
```

Several things are worth observing about this example.

The module declaration forbids any internal function from collapsing shape before comparison. This is checked by the compiler against every function body, not enforced by programmer discipline. A function inside this module that attempted to implement classification via MFCCs (which are scalar features and therefore collapses) would be rejected.

The `classify` function's intent declares the ambiguity threshold, its forbid clause enumerates the failure mode, and its ensure clause states the property. The body then implements those declarations straightforwardly. A human who cared only about the intent could write:

```
fn classify (sample : 𝕎, known : [signature]) → signature | fault<no_match>
    intent: 「identify the instrument whose prototype has smallest coherence distance to sample」
    forbid: 「return a match if the best distance exceeds the ambiguity threshold 0.65」
    ensure: 「output is the unique nearest signature, or a no-match fault」
    ≔ ??
```

and the compiler would produce a body equivalent to the one shown.

The `identifiability_horizon` function illustrates process composition: a probe process emits a stream of (δ, distance) pairs, and the first pair to exceed the threshold is returned. There is no explicit loop. The process composes through its own frequency parameter.

---

## 15. Use Cases

New Code is not a general-purpose replacement for Python or Rust. It is a language for specific domains where its primitive commitments (process over state, structure over scalar, intent as type) produce real advantages. Five domains stand out.

**Audio and signal processing.** The native representation is a waveform. All operations preserve phase and shape information by default. The language was effectively designed for this domain, and for DSP work it should feel immediate. Applications include synthesis, adaptive filtering, timbre classification, acoustic scene analysis, and anywhere else that discarding phase information has historically cost accuracy.

**Continuous-simulation modelling.** Models of coupled physical systems, such as populations, economies, ecosystems, and climate subsystems, are naturally expressed as entangled processes. The entanglement primitive handles the consistency requirements that cause so many simulation bugs. Drift handles the gradual parameter evolution that most models fudge with ad-hoc time stepping.

**AI-AI interface code.** The original motivation. When one AI system is producing code to be consumed by another AI system, as increasingly happens in agent frameworks, model-to-model tool calls, and compiler pipelines, the intent layer makes the interface machine-verifiable. One AI declares what its code does; the consuming AI checks the declaration and acts accordingly. The human is in the loop only for specification and review.

**Specification-first codebases.** Any project in which correctness matters more than performance, and in which humans want to reason about *what* without micromanaging *how*, benefits from a language in which the intent is the primary artefact and the implementation is generated. Financial settlement logic, medical device firmware, voting systems, legal contract execution. Places where "the code matches the spec" is currently a hope and should be a guarantee.

**Experimental language design itself.** New Code is a testbed for ideas that do not yet fit anywhere else. The drift operator has no analogue in conventional languages. The entanglement primitive exists in nothing the author is aware of. Researchers interested in what a language built on non-standard primitives looks like will find New Code useful as a concrete object to argue about.

New Code is explicitly *not* well suited to: low-level systems programming where every cycle counts, scripting and one-liners, codebases that must be easily readable by humans without tooling, or any task where the overhead of intent declarations would drown out the work. There is no shame in reaching for Python when Python is the right tool.

---

## 16. Relation to Existing Languages

New Code is not invented from nothing. Several traditions contribute ideas.

From the **ML family** (Standard ML, OCaml, Haskell, Rust): algebraic data types, pattern matching, strong static typing, sum types for error handling without exceptions, pure functions as the default.

From the **dataflow languages** (Lucid, Esterel, Lustre, Max/MSP, Pure Data): the notion that programs are networks of continuously-running nodes rather than sequences of instructions. Audio programming languages have been quietly correct about this for decades; mainstream programming has mostly ignored them.

From the **dependently-typed languages** (Idris, Agda, Lean): the idea that types can carry propositions and that the compiler can verify propositional content at compile time. The intent layer is not dependent typing in the strict sense, but it plays an analogous role: lifting specification into the type system.

From **Prolog and the logic-programming tradition**: the idea that a program can be a set of declarations from which the machine works out how to produce a result. New Code's compiler-fills-the-hole pattern (`≔ ??`) is this idea warmed over, with a neural compiler in place of a resolution engine.

From **the literate-programming tradition** (Knuth's WEB, modern org-mode Babel): the insight that documentation and code can and should be the same artefact. New Code takes this further: the documentation *is* the specification *is* part of the type.

What is new in New Code is the combination. No existing language takes waveform numbers as primitive. No existing language makes entanglement a type-level primitive. No existing language makes intent declarations part of the function signature and verified by a neural compiler. The integration is the contribution.

---

## 17. What Is Still Open

v1.0 closes most of what the original specification listed as open. A working compiler exists with three backends, the runtime unfolds processes and propagates entanglement, the REPL drives both, the language server runs editors, the debugger renders unfolding live, and the browser playground removes the install step for evaluation. What follows is the honest list of what is *still* open — the v2 agenda — and the known limits a user of v1 should hold in mind.

### ⇝ Open · 4 of 14

These are the four items from the original §17 that v1.0 has not closed. The other ten — working compiler, runtime, parser, FFI execution, REPL, debugger, language server, modules, snapshot replay, provenance — are landed in v1.

- **Formal verification of natural-language intent.** *(OPEN.)* The compiler produces code that *probably* satisfies the intent and runs it through an AST/safety pass plus a constraint report. That is a check, not a proof. Turning plausibility into guarantee is still the core technical challenge of the language.
- **Foreign function interface · boundary types.** *(FFI.)* `host_load`, `host_call`, and `extern python { … }` work at runtime: a score can pull NumPy in and call it. What is *not* yet specified is the type-level boundary — how host types are surfaced into New Code's type system, what marshalling guarantees hold across the boundary, and what happens when a long-running process is called from a short-lived host function.
- **`evolving` · `await` · streaming primitives.** *(SPEC.)* These are in the specification but not in the v1 implementation. v1 has finite `unfold` and pair-wise entanglement; time-varying continuations and streaming await are deferred.
- **Browser REPL · try it without installing.** *(NEXT.)* The browser playground (`python -m newcode.playground`) ships a stdlib-only HTTP server and a single-page frontend, but it still requires a local Python install. A fully hosted version that runs the compiler server-side and exposes the REPL/debugger over the open web is the next adoption-side milestone.

### ◌ Known Limits · approximate

These are intentional limits of v1, not unfinished work. They define what a user should and should not expect from v1 today.

- **Intent verification is plausibility, not proof.** *(HONEST.)* The Anthropic backend returns a body, the constraint report scores it against intent/forbid/ensure clauses, and provenance records the decision. Acceptance is auditable; it is not formally verified. Treat compiled bodies the way you treat code review output: trust, but read.
- **Offline compiler covers only six known intents.** *(FALLBACK.)* `OfflineCompiler` is a deterministic pattern matcher for `amplify`, `invert`, `collapse`, `drift`, `coherence`, and `superpose`. It exists for keyless environments and tests. Anything beyond that set raises `OfflineHoleError`. The main story is the Anthropic backend; the offline matcher is a fallback, not a substitute.

These items are not reasons not to use v1. They are the agenda for v2.

---

## 18. Glossary

A complete glossary of terms, operators, and types in New Code. Entries are ordered alphabetically within sections. Symbols precede words; unicode glyphs are listed under their customary mathematical names.

### 18.1 Operators and Symbols

| Symbol | Name | Definition |
|---|---|---|
| `⊕` | Superposition | Pointwise sum of waveform realisations; the addition of New Code. Commutative, associative, identity is the zero-amplitude waveform. |
| `⊚` | Oscillation product | Shape-composing multiplication of waveform numbers. Commutative, not associative. The core novel operator of Waveform Logic. |
| `⁻` | Phase inversion | Unary postfix operator. Shifts phase by π radians. Provides the additive inverse of superposition. |
| `⇝` | Drift | Binary infix operator taking a process and a scalar δ. Simultaneously shifts frequency, decays amplitude, rotates phase, and deforms shape. |
| `⟪·,·⟫` | Coherence | Binary bracket operator returning a scalar. Measures shape-sensitive correlation of two waveforms. Marks a collapse. |
| `d_γ` | Coherence distance | Derived metric on `𝕎`. Returns non-Euclidean distance based on coherence. |
| `▷◁` | Entanglement | Type-level and declarative operator expressing that two values are coupled by a named function Φ. Symmetric, not transitive. |
| `◈` | Re-coherence | Unary operator applied to a pair of processes. Restores phase alignment between them. |
| `‖` | Synchronisation | Binary operator. Forces two processes to advance in lockstep for the duration of a block. |
| `⌊·⌉` | Collapse | Unary bracket operator. Reduces a waveform number to a scalar by amplitude-weighted coherence with the unit oscillator. Irreversible and lossy. |
| `▶` | Series composition | Combinator that feeds the output of one process into the input of another. |
| `∥` | Parallel composition | Combinator that runs two processes independently, yielding a pair. |
| `↺` | Feedback | Combinator that feeds a process's output back into its input with a declared delay. |
| `↦` | Maps to | Used in lambda expressions and shape literals. Separates parameter from body. |
| `≔` | Defines | Separates the header of a declaration from its body. Used in `let`, `fn`, `process`, `module`. |
| `?` | Sample | Unary postfix on a process. Returns the current realisation of the process at the point of evaluation. |
| `??` | Hole | Placeholder for an unimplemented body. The compiler fills it from the intent declaration. |
| `※` | Line comment | Introduces a comment that runs to end of line. |
| `《 ... 》` | Block comment | Bracketed comment. |
| `「 ... 」` | String literal | Delimits a string. Primarily used in intent declarations and tags. |
| `⟨ ... ⟩` | Waveform literal | Delimits the four components of a waveform number. |
| `{ ... }` | Shape literal | Delimits a shape expression of the form `{ t ↦ expr }`. |

### 18.2 Types

| Type | Name | Definition |
|---|---|---|
| `𝕎` | Waveform number | A quadruple ⟨f, A, φ, σ⟩ of frequency, amplitude, phase, and shape. The fundamental value type. |
| `𝕎*` | Spectrum | A finite superposition of waveform numbers, representing a complex signal. |
| `ℝ` | Scalar | A conventional real number. Treated as a degenerate waveform for type compatibility. |
| `shape` | Shape | A unit-periodic function σ : ℝ → [-1, 1]. The fourth component of a waveform number. |
| `proc<τ>` | Process | A running computation that produces values of type τ over time. |
| `⟨τ₁ ▷◁ τ₂⟩` | Entangled pair | A pair of values coupled by a declared Φ function. |
| `⌊τ⌉` | Collapsed | A type marker indicating a value has been reduced from a richer structure. |
| `stream<τ>` | Stream | A lazy, potentially infinite sequence of τ values. |
| `fault<name>` | Fault | A structured failure value with a named type and a payload. |
| `τ₁ \| τ₂` | Sum type | A value of type τ₁ or type τ₂, discriminated by pattern matching. |
| `(τ₁, τ₂)` | Tuple | An ordered pair of values. Extends to arbitrary arity. |
| `[τ]` | List | A finite ordered sequence of τ values. |
| `{ n : τ, ... }` | Record | A collection of named fields with declared types. |

### 18.3 Keywords

| Keyword | Role | Definition |
|---|---|---|
| `await` | Process coordination | Pauses the current process until another process emits a value matching a pattern. |
| `case ... of` | Pattern matching | Destructures a value against a series of patterns. |
| `collapse` | Collapse declaration | Introduces a custom collapse map from `𝕎` to `ℝ`. |
| `consumes` | Process declaration | Declares the external resources a process requires. |
| `disentangle` | Entanglement primitive | Splits an entangled pair into independent components. Lossy. |
| `emits` | Process declaration | Declares the output type and rate of a process. |
| `ensure` | Intent clause | States an invariant the code guarantees to maintain. |
| `entangle` | Entanglement primitive | Creates an entangled pair from two independent values given a coupling function. |
| `every` | Process constructor | Creates a process that produces output at each cycle of its argument. |
| `export` | Module control | Makes a declaration visible outside the module. |
| `fn` | Function declaration | Introduces a pure function. |
| `fold` | Iteration | Reduces a collection to a single value using a binary operation. |
| `forbid` | Intent clause | States what the code must not do. |
| `foreign` | FFI | Introduces a function implemented outside New Code. |
| `guard` | Precondition | Declares a predicate that must hold at function entry. |
| `import` | Module control | Brings a declaration from another module into scope. |
| `intent` | Intent clause | States what the code is for. |
| `let` | Binding | Introduces a local variable. |
| `λ` | Lambda | Introduces an anonymous function. |
| `module` | Module declaration | Introduces a named collection of declarations with shared intent. |
| `on` | Process constructor | Creates a process that produces output when triggered by an event. |
| `process` | Process declaration | Introduces an ongoing unfolding computation with internal state and external effects. |
| `record` | Type declaration | Introduces a record type. |
| `requires` | Higher-order constraint | Declares what must be true of a function argument's intent. |
| `shape` | Shape declaration | Introduces a named shape function. |
| `via` | Coupling specification | Names the coupling function used in an entanglement. |
| `when ... then ... else` | Conditional | Expression form of branching. |
| `while` | Process constructor | Creates a process that produces values while a condition holds. |

### 18.4 Concepts

**Ageing.** The gradual deformation of a process under repeated drift. All processes age toward the square-wave attractor; the rate is determined by the amount of drift applied.

**Ambiguity threshold.** A user-declared coherence distance above which two waveforms are considered not reliably distinguishable. Used in classification.

**Attractor.** A fixed point of a dynamical operator. The primary attractor in New Code is the square wave `sq`, which is the fixed point of drift.

**Bit, dynamic.** A distinction whose value changes over time. The minimum informational content of a coherent state, per the Instability of Nothingness.

**Coherence distance.** The metric `d_γ` on `𝕎` derived from the coherence measure. Sensitive to shape, not just magnitude. Non-Euclidean.

**Collapse.** The irreversible projection of a structured value (typically `𝕎`) to a scalar. Destroys phase, shape, and spectral information.

**Composition, process.** The construction of new processes from old ones via series, parallel, and feedback combinators.

**Compiler.** In New Code, an AI system capable of parsing source, reading intent declarations in natural language, and producing verified implementations. Distinguished from a conventional compiler by its reliance on neural reasoning for the intent layer.

**Coupling function.** A function `Φ : 𝕎 → 𝕎` that defines the relation between two entangled values. Any transformation of one induces Φ on the other.

**Drift.** The operator `⇝` that simultaneously shifts frequency, decays amplitude, rotates phase, and deforms shape under a single scalar parameter.

**Entanglement.** A structural coupling between two values in New Code such that transformations of one automatically propagate to the other. Symmetric, not transitive.

**Fingerprint.** The product `w ⊚ e₀` or analogous shape-composed object, used to identify a waveform number uniquely by its morphology.

**Fixed point.** A state of a process from which no further change occurs under its native dynamics. The drift operator's fixed point is the square wave.

**Hole.** A placeholder body `??` to be filled by the compiler from the declared intent.

**Identifiability horizon.** The smallest drift parameter δ at which a waveform number becomes unrecognisable under coherence distance. Measures the robustness of its identity.

**Intent.** A natural-language or formal declaration of what a unit of code is for. Part of the function's type.

**Oscillation.** A single complete cycle of a wave. The primitive event of computation.

**Process.** A running computation with its own internal time. The primary unit of execution in New Code.

**Realisation.** The instantaneous value `ŵ(t) = A · σ(ft + φ)` of a waveform number at time t.

**Re-coherence.** The operation of re-aligning the phases of two processes that have drifted apart. Expensive and may fail.

**Shape.** The fourth component of a waveform number: a unit-periodic function σ : ℝ → [-1, 1]. Carries morphological information beyond frequency, amplitude, and phase.

**Spectrum.** The complete set of frequency components of a complex waveform number. The Fourier-domain identity of a value.

**Superposition.** Pointwise summation of waveform realisations. The addition of New Code.

**Synchronisation.** The coordination of two processes such that they advance in lockstep. Explicit in New Code because there is no global clock.

**Thermodynamic termination.** The natural end state of an unsustained process: drift to the square-wave attractor. Not a fault.

**Unfolding.** The execution of a New Code program as the continuous advancement of processes along their internal times. Distinguished from "running" by the absence of an instruction counter.

**Unit oscillator.** The canonical reference waveform `e₀ = ⟨1, 1, 0, sine⟩`. The "1" of New Code and the probe for collapse.

**Waveform number.** The fundamental data type of New Code. A quadruple of frequency, amplitude, phase, and shape.

---

## Closing Note

The first review's two recommendations were "narrow to audio" and "fake the AI compiler." One of those is right. The compiler in v1.0 is a real LLM call when online, with AST-level safety checks, a constraint report, and a content-addressable cache that turns yesterday's online run into today's offline replay. That is the honest version of what the specification describes.

The other recommendation misses the bet. New Code is not a DSL for signal processing. The 𝕎 primitive looks audio-specific because audio is the domain where four-component waveform structure is already native vocabulary, but the abstraction generalises: a UI state, a belief, a transaction, a database stream — all have frequency, amplitude, phase, and shape as latent components. What makes New Code worth building is the claim that this structure is universal, that intent is a first-class declaration, and that the combination kills categories of bug that conventional languages cannot name.

v1.0 is the version you can build with. Everything from here is widening — more shapes, more couplings, more streaming primitives, formal intent verification when that becomes a solved problem — not deepening the bet.

---

*New Code v1.0 · Working Specification · Dan Rodriguez · [UltraNarrative](https://ultranarrative.com) · [newcode.ultranarrative.com](https://newcode.ultranarrative.com) · [dan@ultranarrative.com](mailto:dan@ultranarrative.com) · April 2026*

*Built on: Waveform Logic (D. R. S., 2026), Processism (D. R. S., 2026), and the Philosophy note on machine-native computation.*

*v1.0 ships a working compiler, runtime, REPL, language server, debugger, and browser playground. Definitions are stable for v1; the open items in §17 are the v2 agenda.*
