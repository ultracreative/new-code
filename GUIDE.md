# The Conductor's Guide to New Code (v1.0)

A tutorial for writing your first New Code score.

This guide is for the human who wants to use the language — not the one who wants to understand the theory. The theory lives in `New_Code.md` and the papers. The grammar lives in `GRAMMAR.md`. The runtime semantics live in `SEMANTICS.md`. **This file is the thing you read when you sit down to write.**

---

## The shape of the thing

New Code is written like an orchestral score. The human is the conductor. The AI compiler is the orchestra. You describe, in a dedicated kind of sentence called an **intent**, what the music should do. The orchestra plays it.

You do not write loops. You do not write control flow by hand. You write:

- **what** the function should accomplish (`intent`),
- **what** it must never do (`forbid`),
- **what** must be true at the end (`ensure`),

and then, where a conventional language would have you write the body, you write `??`. The compiler fills it in. You read the result the way a doctor reads blood work — through diagnostics, through the debugger, through tests, through the **provenance record** the compiler stamps onto every body — not by following the code line by line.

In v1.0 the loop is closed: when you accept a body the compiler produced, it is persisted into a snapshot store, keyed by the *intent* you wrote. The next time the same intent compiles, no API call happens. **`:accept` turns yesterday's online run into today's deterministic replay.**

This guide takes you from zero to a running score, then through the v1.0 approval workflow, the new expression grammar, and the host bridge.

---

## Chapter 1 — The primitive

Everything in New Code is built on one type, the **waveform number** 𝕎. A waveform number has four components:

```
⟨ f , A , φ , σ ⟩
  freq amp phase shape
```

- `f` — how often the value updates or repeats (cycles per unit time).
- `A` — the amplitude, or magnitude.
- `φ` — the phase, or offset within the cycle (radians).
- `σ` — the shape, a unit-periodic function: `sine`, `sq`, `tri`, `saw`, `pulse(duty)`.

That is the whole type. Everything else is operators on 𝕎.

The name is "waveform" because audio is the domain where all four components are already native vocabulary. But the abstraction is general. A UI state has all four: how often it updates, how loud the change is, where in the user's attention it arrives, and what curve it takes getting there. A belief has all four: how often you revise it, how strongly you hold it, where you are in your update cycle, what shape your revising takes. **You are describing change, and change has these four components whether you name them or not.** New Code names them.

### Your first score

Open a file, call it `first.nc`, and write:

```newcode
※ A 440 Hz tone.
let concert_a : 𝕎 = w(f=440, A=1.0, phi=0.0, sigma=sine)
```

`※` is a comment. `let` binds a name. `w(...)` is the convenience constructor for 𝕎. This is a 𝕎 whose frequency is 440 cycles per second, at full amplitude, with no phase offset, in the shape of a sine wave.

Load it:

```bash
python -m newcode.repl first.nc
```

You should see:

```
loading first.nc...
  let concert_a = ⟨440, 1, 0, sine⟩
New Code v1.0 — mode: offline
nc> concert_a.realise(0.25)
0.9999952938095761
nc> concert_a.realise(0.0)
0.0
```

`realise(t)` evaluates the waveform at a particular time. This is how 𝕎 becomes a number.

> A note on `tau`. 𝕎 is a *descriptor* of change; it does not itself change over `tau`. The thing that changes is `realise(tau)`. The debugger plots `realise(tau)`. See `SEMANTICS.md §1` for the full lock.

---

## Chapter 2 — Intent blocks: the conductor's three gestures

You do not write the body of a function by hand. You write three clauses that describe it to the compiler, then a `??` where the body would go. The compiler reads your clauses and fills in the rest.

There are three canonical clauses, and you should think of them as three gestures of the baton:

| Clause | Gesture | What it says |
|---|---|---|
| `intent`  | bringing the orchestra in | what the function should **do** |
| `forbid`  | the cut-off, the don't-do-that | what the function must **not** do |
| `ensure`  | the sustain, the hold | what must be **true** at the end |

Here is the canonical example:

```newcode
fn amplify (signal : 𝕎, gain : ℝ) → 𝕎
    intent: 「scale the amplitude of signal by gain while preserving shape」
    forbid: 「do not modify phase」
    ensure: 「output shape equals input shape」
    ≔ ??
```

Read it aloud. *"Amplify takes a signal and a gain and returns a 𝕎; its intent is to scale the amplitude while preserving shape; it is forbidden to modify phase; it must ensure the output shape equals the input shape; and the body is a hole — you, the compiler, will fill it."*

The `≔` symbol is "is defined as". Type it as `≔` or `:=` — both work.

When you load this score into the REPL, the compiler runs. Which backend it uses depends on **mode** — see Chapter 8.

```
nc> amplify(concert_a, 2.5)
⟨440, 2.5, 0, sine⟩
```

Amplitude doubled-and-a-halved. Shape unchanged. Phase unchanged. The three clauses held.

### Writing good intents

Writing a good intent is like writing a good prompt — because it is a prompt. A few rules:

1. **Name the primitive.** The compiler knows the names of the operators and collapses. If you want drift, say "drift". If you want coherence, say "coherence". "Make it more similar" is ambiguous; "increase the coherence with e₀" is not.
2. **Be literal about forbid clauses.** Forbids are enforced literally. `"do not modify phase"` means φ may not change.
3. **Use ensure for invariants.** Anything you want true of the output — a bound, a shape, a sign — put it in ensure. The compiler reads these as post-conditions.
4. **One intent per function.** If you find yourself writing two intents joined by "and", split the function.
5. **When in doubt, look at the stdlib.** Every function there has the intent it would have had if it had been written in New Code.

Two intent strings produce two different snapshots. Re-phrasing the intent re-prompts the model. **Intent text is part of the cache key.**

---

## Chapter 3 — The operators

These are the operators on 𝕎. In expression contexts you may call them by name **or** by symbol — the v1.0 expression grammar parses both.

| Symbol | Function | What it does |
|---|---|---|
| ⊕ | `superpose(a, b)` | pointwise sum of two waveforms |
| ⊚ | `oscillate(a, b)` | ring-modulates the shapes |
| ⁻ | `invert(a)` | shifts phase by π |
| ⇝ | `drift(a, δ)` | ages `a` by δ toward the square-wave attractor |
| ⟪·,·⟫ | `coherence(a, b)` | shape-sensitive correlation, in [−1, 1] |
| d_γ | `d_gamma(a, b)` | coherence distance, in [0, 1] |
| ⌊·⌉ | `collapse(a)` | reduce a 𝕎 to a scalar (**information loss**) |
| ⌊·⌉_amp | `collapse_amp(a)` | collapse by amplitude only |
| ⌊·⌉_freq | `collapse_freq(a)` | collapse by frequency only |
| ⌊·⌉_rms | `collapse_rms(a)` | root-mean-square over one period |

Two things to internalise:

- **Drift is the important one.** It is a single operator that captures ageing, decay, analysis, and thermodynamic termination. A program ends when it drifts to the square-wave attractor. Cleanly ending a process is letting drift complete, not aborting.
- **Collapse is irreversible.** Every `collapse` is a declaration that you are leaving New Code and returning to a conventional scalar. The type signature makes the loss visible. Treat collapse calls the way you would treat `unsafe` in Rust.

---

## Chapter 4 — Processes

A process is not a thread. It is an ongoing unfolding with its own internal clock, τ.

```newcode
let beat : 𝕎 = w(f=1.0, A=1.0, sigma=sine)
```

```
nc> p = every(beat)
nc> unfold(p, 3)
[⟨1, 1, 0, sine⟩, ⟨1, 1, 0, sine⟩, ⟨1, 1, 0, sine⟩]
```

`every(w)` makes a process that, on each call to `sample()`, emits `w` and advances its own `tau`. **`every(w)` does not mutate `w`.** It emits the same descriptor every tick; what changes is `realise(tau)`. (See `SEMANTICS.md §3`.)

`unfold(p, n)` advances the process by `n` ticks and returns the values.

### Combinators

Three ways to compose processes:

- **series** — the output of each feeds the input of the next. Symbol: ▶.
- **parallel** — two processes run independently, yielding a pair. Symbol: ∥.
- **feedback** — a process's output feeds back into itself with a delay. Symbol: ↺.

Combinators **sample** their children — they do not call `step(...)` directly. This is what gives `series` and `feedback` honest semantics under nested processes (`SEMANTICS.md §4`).

### Drift as termination

```
nc> aged = drift_process(every(concert_a), delta_per_step=0.2)
nc> unfold(aged, 5)
[⟨440, 1, 0, sine⟩, ⟨440, 0.8187, …, sine→sq(0.20)⟩, ⟨440, 0.6703, …, sine→sq(0.40)⟩, …]
```

Each step ages the underlying waveform a little more. Amplitude decays. Shape bends toward square. This is what it looks like to **end a process cleanly** in New Code. You do not call `stop()`. You let the drift complete.

---

## Chapter 5 — Entanglement

Two values are entangled when there is a declared coupling Φ such that **any transformation of one induces Φ on the other**. This is structural coupling, promoted into the type system.

In conventional languages, "the toggle and its indicator should always agree" is a comment, maybe a test, maybe the thing that breaks in production when someone forgets. In New Code it is a declaration:

```newcode
let toggle   : 𝕎 = w(f=60, A=1.0, phi=0.0, sigma=tri)
let indicator: 𝕎 = w(f=60, A=1.0, phi=0.0, sigma=tri)
```

```
nc> pair = entangle(toggle, indicator, via=identity)
nc> pair.transform_left(invert)
⟨ ⟨60, 1, 3.14159, tri⟩ ▷◁ ⟨60, 1, 3.14159, tri⟩ ⟩ via identity
```

Any `transform_left` you apply propagates through Φ to the right. The two are guaranteed to stay consistent under the coupling.

Entanglement is **symmetric** (both sides propagate) and **not transitive** (A ▷◁ B and B ▷◁ C does not imply A ▷◁ C). Non-transitivity is a deliberate design choice: coupling is declared between specific pairs, not inferred across chains.

The coupling library ships with `identity`, `pitch_follow` (fifth above), `amplitude_mirror`, and `phase_opposition`. You may pass any pure function as a coupling.

---

## Chapter 6 — The expression grammar (new in v1.0)

Until v0.3, New Code expressions were Python expressions in disguise. In v1.0 there is a real expression layer parsed by [`newcode/expr.py`](newcode/expr.py). You write let-bindings, lambdas, blocks, conditionals, records, and lists in a familiar Python/F#-flavoured surface, and the compiler lowers them to safe Python.

### Let-in

```newcode
let scaled =
    let base = w(f=440, A=1.0, sigma=sine) in
    let gain = 1.5 in
    amplify(base, gain)
```

A `let … in` expression is local. Outside the `let-in`, `base` and `gain` do not exist.

### Lambdas

```newcode
let double = \x -> x * 2
let mul    = \x y -> x * y
```

`\x -> e` is the lambda. `λ` is accepted too if you like the Greek.

### Blocks

```newcode
let pipeline = {
    let a = every(concert_a)
    let b = drift_process(a, 0.05)
    unfold(b, 16)
}
```

A `{ ... }` block is a sequence of let-bindings and a final expression. It evaluates to the value of the final expression.

### If / then / else

```newcode
let safe_gain = if gain > 10 then 10 else gain
```

It's an expression, not a statement. Both arms must yield a value.

### Records and lists

```newcode
let voice  = { f: 440, A: 1.0, phi: 0, sigma: sine }
let chord  = [concert_a, amplify(concert_a, 0.5), invert(concert_a)]
```

Records and lists are first-class. Records use `{ key: value, ... }`. Lists use `[a, b, c]`.

### `python { ... }` — the explicit escape hatch

When you genuinely need Python — to call a NumPy primitive inline, or to use a comprehension — wrap it:

```newcode
let arr = python { [i * 2 for i in range(10)] }
```

The forbidden-name list still applies inside `python { }`. You cannot call `eval`, `exec`, `__import__`, or `open` from inside the escape hatch. (See `SEMANTICS.md §10` for the full lock on the expression evaluator.)

### What this buys you

The REPL evaluates `let` bindings through the same grammar the compiler uses. What you can write in a `let` is exactly what the compiler can produce in a body. There is no second-class expression layer.

---

## Chapter 7 — The host bridge: `import` and `extern python`

Two ways to reach Python from New Code, both explicit and both auditable:

### `import host.<module>`

```newcode
import host.numpy as np

let arr = np.array([1, 2, 3, 4])
```

Top-level. Resolved through the typed `HostBridge`. Cached. The name `np` is bound in the loading scope.

### `extern python { ... }`

```newcode
extern python {
    import numpy as np
    SAMPLE_RATE = 44_100
    def to_pcm(w):
        return np.sin(2 * np.pi * w.f * np.arange(SAMPLE_RATE) / SAMPLE_RATE)
}
```

Top-level only. The block runs once when the score loads, and its top-level names (`np`, `SAMPLE_RATE`, `to_pcm`) become available everywhere in the score. The forbidden-name list does **not** apply inside `extern python { }` — this is the deliberate trap door for "I really do need the host."

> Use `import host.x` for *consumption* (you want a Python library available by name). Use `extern python { }` for *setup* (you need to define helpers, constants, configure the host runtime).

---

## Chapter 8 — Modes: offline, online, snapshot

In v1.0 the compiler has three explicit modes. The mode is the only thing that decides what happens to an intent hole.

| Mode     | What happens to `≔ ??`                                          | Network |
|----------|------------------------------------------------------------------|---------|
| offline  | offline pattern matcher; otherwise raises `OfflineHoleError`     | no      |
| online   | calls Anthropic; AST safety pass; writes to snapshot store       | yes     |
| snapshot | replays a `SnapshotStore` from disk; miss → falls through        | no      |

**Explicit bodies (`≔ <expression>`) compile in any mode without an API call.** The mode only matters for intent holes.

### Picking a mode

```bash
python -m newcode.repl --offline   first.nc
python -m newcode.repl --online    first.nc
python -m newcode.repl --snapshot=tests/fixtures/snap.json first.nc
```

Without a flag, the REPL picks based on `NEWCODE_MODE` then on `ANTHROPIC_API_KEY`. No key → offline.

Inside the REPL, switch with `:mode`:

```
nc> :mode
mode: offline
nc> :mode online
mode: online
```

### When the offline backend can't resolve a hole

```
nc> :reload
loading first.nc...
  ⚠ amplify: OfflineHoleError: no offline match for intent
    「scale the amplitude of signal by gain while preserving shape」
    fix: add this intent to the offline pattern table, run --online to
    let the model fill it, or write the body explicitly.
```

The compiler does **not** silently fall back to a different mode. It tells you exactly what to do.

---

## Chapter 9 — Provenance and the approval workflow

Every compiled artefact carries a `Provenance` record:

```
backend     : anthropic
model       : claude-sonnet-4-5
intent_hash : 7c9e3a2b4f8d1e6a
body_hash   : 9d4a7e2c1b3f6580
timestamp   : 2026-04-24T18:32:11+00:00
accepted    : False
notes       : 0 retries
```

- `backend` — `offline` | `anthropic` | `snapshot` | `explicit`.
- `intent_hash` — a stable 16-hex-char SHA-256 prefix over the declaration's *shape* (name, kind, args, return type, intent clauses). **It does not depend on the body.** Same hole + same intent → same hash, whether or not the body has been accepted.
- `body_hash` — hash of the produced Python body. Informational; safety is enforced by the AST pass, not the hash.
- `accepted` — the only user-controlled field.

### The four REPL commands

```
:provenance amplify    show the full record
:src        amplify    show the compiled body
:accept     amplify    persist the body to the snapshot store
:reject     amplify    remove it from the store
```

### A typical session

```text
$ python -m newcode.repl --online first.nc
loading first.nc...
  let concert_a = ⟨440, 1.0, 0, sine⟩
  compiled: amplify  (compiled by claude-sonnet-4-5, 0 retries)
nc> :src amplify
    f_, A_, phi_, sigma_ = signal.unpack()
    return W(f=f_, A=A_ * gain, phi=phi_, sigma=sigma_)
nc> amplify(concert_a, 2.0)
⟨440, 2.0, 0, sine⟩
nc> :provenance amplify
  amplify:
    backend     : anthropic
    accepted    : False
    ...
nc> :accept amplify
  ✓ amplify accepted (intent_hash=7c9e3a2b…, snapshot=~/.newcode/snapshots/default.json)
```

From the next run on, the same source compiles in `--snapshot` mode (or `--online` with the cache) without an API call. **`:accept` is how you turn an exploratory online run into a deterministic replay you can pin under version control and exercise in CI.**

If you change the intent text, the `intent_hash` changes, the cache misses, and the model re-runs. If you change only the body of a `python { }` escape inside an explicit declaration, the body hash changes but no online recompile is triggered. This is the lock from `SEMANTICS.md §8.1`: **the body never participates in the cache key.**

---

## Chapter 10 — Watching it unfold

You do not read a New Code program. You watch it unfold. Start the visual debugger from the REPL:

```
nc> :debug
debugger at http://127.0.0.1:54321/  (tracking 2 process(es), 1 entangled pair(s); +3 new this call)
```

A browser tab opens. Every process in scope becomes a horizontal band: τ along the x-axis, the realisation plotted against y. Every entangled pair becomes its own row; the link between its left and right flashes when a transformation propagates.

Call `unfold(p, 20)` or `pair.transform_left(invert)` and watch the UI refresh in real time over Server-Sent Events. **This is how you read a New Code program: by watching it play.**

For code-pad work without an editor, run the **browser playground**:

```bash
python -m newcode.playground
```

Same idea: stdlib HTTP, single-page frontend, no install. You compile, run, accept, replay all from the browser.

---

## Chapter 11 — The workflow

When you sit down to write a New Code score, the order goes:

1. **Decide what you are modelling.** An audio signal? A belief? A UI state? A transaction? The type is the same.
2. **Write the literals.** `let` bindings for the 𝕎s you already know.
3. **Write the function signatures with intents.** Header, intent/forbid/ensure, `≔ ??`.
4. **Pick a mode.** `--offline` for the known-pattern path; `--online` to let the model fill new holes; `--snapshot` once you have a pinned recording.
5. **Compile in the REPL.** Read the provenance, read the body, run the function, watch the debugger.
6. **`:accept` the bodies you trust.** Now the score compiles without the network. Commit the snapshot file.
7. **Watch processes unfold.** `:debug` and run them in the browser.
8. **When drift ends it, it has ended.** Do not abort. Do not force-quit. Let the square-wave attractor be reached.

A good first session is fifteen minutes. A good first non-trivial score is a UI panel or a belief system — something that is not audio, to prove to yourself that the language is general.

---

## Chapter 12 — Editor support

New Code ships with a stdlib-only language server. Point your editor at it for diagnostics, completion over the stdlib, hover tooltips that show intent blocks, and document symbols.

### VS Code

Install the extension in `vscode-newcode/` (see its README). Open any `.nc` file. Features:

- Colour for keywords, types, intent clauses, bracketed intent strings, the `??` hole, the `≔` bind, the `import`/`extern` forms, and the new expression-layer keywords (`let`, `in`, `if/then/else`, `\` for lambdas, `python { }` blocks).
- Red squiggles on parse errors.
- Autocomplete for declaration keywords, clause keywords, stdlib names, shape names.
- Hover on a compiled function to see its intent block.
- Document symbols (outline) over `fn`/`process`/`let`/`module`.

### Other editors

```bash
python -m newcode.lsp   # JSON-RPC over stdin/stdout
```

Pure stdlib Python.

---

## Appendix A — The reserved vocabulary

Top-level decl keywords:

```
fn   let   process   module   import   extern
```

Clause keywords:

```
intent   forbid   ensure   requires   emits   consumes   guard
```

Expression-layer keywords:

```
let in if then else and or not match with do end
true false True False
```

Anything else at line start is a comment (`※`), a continuation, or an error.

## Appendix B — The stdlib, in one page

```
W  w  Shape                            ─ the primitive
sine  sq  tri  saw  pulse              ─ the shapes
e0  silence                            ─ the unit and the zero
superpose  oscillate  invert  drift    ─ the operators
coherence  d_gamma                     ─ the correlators
collapse  collapse_amp  collapse_freq  collapse_rms   ─ the collapses
fingerprint  identifiability_horizon   ─ the diagnostics

Process  every  on  while_             ─ the process constructors
series  parallel  feedback             ─ the combinators
unfold  drift_process                  ─ the runtime

Entangled  entangle                    ─ the coupling type
pitch_follow  amplitude_mirror         ─ stock couplings
phase_opposition  identity

pi  tau_const  e_const                 ─ math constants
sqrt exp log sin cos tan ...           ─ math functions
fold_left fold_right take drop         ─ functional helpers
compose pipe head tail unique          ─ list helpers
fmt show print io_buffer io_clear      ─ formatting + IO

host_load  host_call                   ─ FFI accessors
```

Memorise the top three blocks. The rest you will look up.

## Appendix C — The mode cheatsheet

| You wrote                 | Offline                                | Online                              | Snapshot                              |
|---------------------------|----------------------------------------|-------------------------------------|---------------------------------------|
| `≔ ??` known pattern      | offline backend matches                | API call (cached if present)        | replay if present, else fall through  |
| `≔ ??` unknown pattern    | `OfflineHoleError`                     | API call, AST-checked, cached       | fall through to chosen fallback       |
| `≔ <expr>`                | parse + lower                          | parse + lower                       | parse + lower                         |
| `extern python { ... }`   | runs                                   | runs                                | runs                                  |
| `import host.x`           | works                                  | works                               | works                                 |

## Appendix D — A reading list

- `New_Code.md` — the full specification. Read for the theory.
- `GRAMMAR.md` — the formal grammar. Read for the parser.
- `SEMANTICS.md` — the locked runtime. Read for the precise meaning of `tau`, `realise`, the modes, and the cache key.
- `examples/` — the worked examples. Read last; by then they will be obvious.
