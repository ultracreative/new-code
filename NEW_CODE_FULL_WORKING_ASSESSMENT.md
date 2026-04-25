# New Code: What It Needs To Be Fully Working

As of 2026-04-23, based on the current `new-code_v0.1` workspace.

## Executive Summary

New Code is already a real prototype, not just a concept document. The current repository contains a working waveform primitive (`𝕎`), operators, a minimal process runtime, entanglement, a parser, an intent-to-body compiler path, a REPL, a browser debugger, an LSP server, and a VS Code extension. The core examples load in the REPL, and the automated test suite passes.

What it is **not** yet is a fully working language in the strong sense. It is not semantically locked down, not trustworthy enough for serious use, not complete as a language surface, not interoperable with real systems, and not packaged as a developer platform. The fastest honest description is:

- It is a credible **research prototype**.
- It is a promising **language experiment**.
- It is not yet a **finished language**, a **stable compiler**, or a **production runtime**.

If the goal is to make New Code fully working, the next stage is not mainly about adding more ideas. It is about tightening semantics, finishing the missing execution and compilation paths, making compiler output inspectable, and building one decisive demo that proves the language is useful outside audio metaphors.

## What Exists Right Now

The repository already implements the following:

### Core runtime

- `𝕎` as a concrete Python datatype with `f`, `A`, `phi`, and `sigma`.
- Built-in shapes: `sine`, `sq`, `tri`, `saw`, `pulse(duty)`.
- Operators: `superpose`, `oscillate`, `invert`, `drift`, `coherence`, `d_gamma`, and several collapse functions.
- Diagnostics helpers such as `fingerprint` and `identifiability_horizon`.

### Process model

- `Process` type with internal `tau`.
- Constructors: `every`, `on`, `while_`.
- Combinators: `series`, `parallel`, `feedback`.
- `unfold` and `drift_process`.

### Entanglement

- `Entangled` pair type.
- Couplings: `identity`, `pitch_follow`, `amplitude_mirror`, `phase_opposition`.
- Left/right transform propagation.

### Language surface

- Parser for `fn`, `process`, `let`, and `module`.
- Intent clauses: `intent`, `forbid`, `ensure`, plus `requires`, `emits`, `consumes`, `guard`.
- Unicode and ASCII fallbacks for `≔`/`:=` and `→`/`->`.

### Compiler path

- `OfflineCompiler` that handles a small pattern-matched set of intents.
- `AnthropicCompiler` that can synthesize Python bodies from intent text.
- AST safety filtering before execution.
- Runtime assembly of compiled Python callables.

### Tooling

- REPL that loads `.nc` files and installs compiled functions and `let` bindings.
- Browser debugger with HTTP + Server-Sent Events and an embedded SVG frontend.
- Python LSP server for diagnostics, completion, hover, and document symbols.
- VS Code extension that launches the LSP and provides syntax support.
- Project site describing the model and current implementation.

### Evidence that the prototype works

- `python3 -m unittest tests.test_core` passes in this workspace.
- `examples/demo.nc` loads cleanly in the REPL.
- `ui_state.nc` loads cleanly in the REPL.
- The non-audio example produces a coherence distance of about `0.9757` between the “strong slow belief” and the “anxious belief”, which supports the current pitch that the abstraction generalizes beyond audio.

## What Is Already Good About It

These are the strongest parts of the project today.

### 1. It has a real primitive, not just a slogan

New Code is not only “AI writes code for humans.” It has an actual substrate: `𝕎 = ⟨f, A, phi, sigma⟩`. That matters. A lot of AI-language ideas collapse into prompt wrappers over Python. This repo does more than that.

### 2. It treats change as the default, not the exception

Most languages start with stable values and bolt on time, events, mutation, and reactivity later. New Code starts from dynamic structure. Even if the exact `𝕎` model evolves, this is one of the project’s best philosophical and technical bets.

### 3. It makes information loss explicit

The collapse functions are one of the best ideas in the project. Ordinary languages erase rich structure into scalars all the time without naming the loss. New Code makes the transition visible. That is genuinely useful.

### 4. It has a plausible non-audio generalization story

The presence of `ui_state.nc` is important. It shows that the project is at least trying to prove that frequency/amplitude/phase/shape can model UI state and belief-like dynamics, not only sound.

### 5. The debugger direction is exactly right

If execution is unfolding rather than stepping, then the debugger is not a side feature. It is the primary reading interface. The fact that a browser debugger already exists is one of the strongest assets in the repo.

### 6. The intent-first authoring model is directionally correct

Even if the current compiler is not trustworthy enough yet, the human role in this language is already clear:

- describe what the function should do
- describe what it must not do
- describe what must remain true

That is a strong interaction model for human-AI programming.

### 7. The project is honest about being incomplete

The README and spec do not hide the open problem: natural-language intent verification is not solved. That honesty helps. Overclaiming would damage the project more than missing features do.

## The Real Potential

This is where New Code could become genuinely important if the semantics are tightened and the toolchain matures.

### Important honesty first

Strictly speaking, almost nothing here is literally impossible in other Turing-complete languages. You can simulate most of these ideas in Python, Rust, Haskell, Clojure, or a custom runtime.

So the right claim is not:

> “New Code can do things no other language can possibly do.”

The stronger and more defensible claim is:

> “New Code tries to make certain kinds of dynamic structure, coupling, intent, and information loss first-class in the language itself, instead of leaving them as conventions in libraries and application code.”

That is the claim worth defending.

### What New Code could make first-class in a way mainstream languages do not

#### Intent-native programming

The language can make `intent`, `forbid`, and `ensure` part of the executable surface, not comments. That is stronger than docstrings and lighter-weight than formal proof systems.

#### Structural dynamic values

If `𝕎` or something close to it survives contact with real use cases, New Code could model changing values in a richer way than “just numbers” or “just events”.

#### Entangled state as a language primitive

Modern apps constantly have values that are supposed to stay in sync:

- toggle and indicator
- slider and readout
- source text and preview
- model state and explanation state
- agent intention and execution state

Today that consistency usually lives in discipline, tests, or framework-specific reactivity. New Code’s entanglement idea tries to elevate that relation into the language.

#### Explicit collapse boundaries

Very few languages mark “this is the point where rich state gets crushed into a simpler representation” as a first-class semantic event. New Code can.

#### Lifecycle as drift rather than stop/start mechanics

The drift concept is unusual and potentially powerful. A language where decay, cooling, degradation, convergence, and termination share one common operator could produce a much more coherent model for dynamic systems than today’s event-loop plus timers plus mutable flags approach.

#### Process-native debugging

If the debugger becomes the normal interface for reading programs, New Code could offer a very different developer experience from imperative step-debugging and log spelunking.

## What Could Be Built With It

These are the application classes where New Code looks most promising.

### 1. Coupled UI state and animation systems

This is the best near-term domain because it fits the current abstraction well:

- refresh/update frequency
- salience/amplitude
- lag/phase
- easing/shape

Entanglement is naturally demonstrable here.

### 2. AI confidence, belief, and agent-state visualization

New Code is well-positioned for systems where state is not static and not binary:

- confidence changing over time
- uncertainty pulses
- attention shifts
- alignment or divergence between two models

The coherence and drift vocabulary fits surprisingly well.

### 3. Audio and signal work

This is the obvious and still valuable domain. Even if the end ambition is broader, audio remains a clean proving ground.

### 4. Reactive orchestration systems

Agent workflows, autonomous systems, and event pipelines are all process-heavy. A process-native language with explicit collapse and coupling could become interesting here if the runtime matures.

### 5. Simulation and “state as trajectory” systems

Places where a value is best thought of as a trajectory rather than a static assignment:

- economic indicators
- sensor streams
- control systems
- trust or risk evolution

## Where the Project Is Still Weak

This is the part that most directly answers “what does it need to be fully working?”

### 1. The semantics are not locked

This is the biggest issue.

The runtime currently sits between multiple interpretations:

- Is `𝕎` itself changing over `tau`, or is it only a descriptor whose realized scalar changes when sampled?
- Does a `Process` carry evolving values, or does it often just return the same `𝕎` object repeatedly?
- Are process combinators modeling real composition semantics, or are they placeholders?

This is not a cosmetic problem. It touches:

- `unfold`
- `drift_process`
- the debugger
- process composition
- the meaning of `tau`
- the meaning of a value “inside” a process

Until this is fixed, everything else is resting on ambiguous foundations.

### 2. The process combinators are conceptually ahead of their implementation

The current `series`, `parallel`, and `feedback` are minimal scaffolding, not mature semantics.

Examples:

- `series` does not actually feed the previous output into the next process in a meaningful way.
- Several higher-order process wrappers call `step(...)` directly instead of advancing nested processes through `sample()`, which means internal `tau` handling for composed processes is not robust.
- The current implementation works for simple demos but is not yet a trustworthy process runtime.

This is one of the core “make it real” tasks.

### 3. The language is not actually fully parsed yet

The parser handles headers and intent blocks, but expressions are still mostly delegated to Python strings. That means New Code is currently:

- part New Code surface syntax
- part embedded Python

That is acceptable for a prototype. It is not acceptable for a finished language.

To be fully working, New Code needs a real expression grammar, a real evaluator or compiler path for that grammar, and clear rules for what is New Code versus what is foreign code.

### 4. Compiler trust is the central unsolved problem

This is the biggest product risk.

The current compiler story is:

- offline pattern matching for a small number of known intents
- LLM-generated Python bodies for broader intent coverage
- AST filtering to block obviously unsafe constructs

That is useful, but still weak in several ways:

- It does not prove intent satisfaction.
- It does not provide robust evidence beyond coarse checks.
- It is vendor-dependent in the Anthropic path.
- It executes generated Python directly.
- It does not provide a mature review/approval workflow.

If the user cannot trust the compiler, New Code stays a curiosity.

### 5. Constraint checking exists in code but is not integrated

There is a `constraint_check.py` module that clearly intends to provide:

- post-compile evidence reports
- REPL explanation support
- richer hover output

But in the current repo it is not wired into the compiler, REPL, or LSP. This is a classic prototype smell: a good direction exists, but the user experience still does not expose it.

This should be promoted from “planned utility” to “default workflow”.

### 6. Explicit-body functions and process compilation are unfinished

This matters more than it may seem.

Right now:

- the REPL skips explicit-body functions
- the top-level compiler raises `NotImplementedError` for process compilation

That means New Code is not yet a complete programming surface even within its own current syntax. A fully working version must support both:

- intent-hole compilation
- explicit authored bodies

without forcing the user into a partial subset.

### 7. Interoperability is still mostly absent

The spec talks about an FFI. The README says it is stubbed. In practice, there is no real interoperability layer yet.

Without interoperability, New Code cannot become a usable language. It remains an isolated runtime experiment.

To be fully working, it needs:

- boundary types
- explicit collapse rules at foreign boundaries
- host language interop
- module/package import story
- calling conventions for long-lived processes

### 8. Tooling is promising, but not complete enough yet

What exists is good. What is missing is equally important.

Still needed:

- browser REPL/playground
- code actions
- semantic tokens
- richer debugger controls
- trace recording and replay
- packaging/project scaffolding
- formatter/linter story
- versioned standard library story

The language server is a good start, but not yet a full developer experience.

### 9. Documentation and project hygiene need tightening

There are already visible inconsistencies in the workspace:

- `README.md` says `tests/test_core.py` contains 41 tests; the current suite runs 42.
- `more-info.md` describes the debugger as not yet built, but the repo now contains it.
- `ui_state.nc` still identifies itself as `examples/ui_state.nc`, but the file is in the repo root.
- Several docs assume the `python` command exists, but in this environment `python3` was required.
- The project license is still `TBD`.

These do not kill the language, but they do reduce confidence. A language project needs very disciplined documentation.

### 10. The generalization claim is still a hypothesis, not a proven fact

The biggest conceptual claim in New Code is that `𝕎` generalizes beyond audio into UI, belief, transaction flows, and more.

That claim is not yet disproven, but it is not yet established either.

Right now the project has:

- one clean signal-processing interpretation
- one plausible UI/belief example

That is enough to keep the hypothesis alive. It is not enough to declare victory.

The project needs two or three stronger domain proofs.

## What “Fully Working” Should Mean

To avoid drifting into vagueness, here is a concrete definition.

New Code is “fully working” only when all of these are true:

### Semantic completeness

- The meaning of `𝕎`, `Process`, `tau`, drift, entanglement, and collapse is stable and tested.
- The spec, implementation, debugger, and examples all agree.

### Language completeness

- The surface syntax is fully parsed.
- Expressions are not delegated to embedded Python by default.
- Explicit-body functions and processes work.
- Modules behave like real namespaces.

### Compiler credibility

- Intent compilation produces inspectable output.
- The system explains what constraints were checked.
- The user can review, accept, reject, and persist generated bodies.
- There is a deterministic fallback for key language patterns.

### Runtime credibility

- Process composition is semantically sound.
- Entanglement behavior is well-defined for realistic cases.
- Performance is at least measured and characterized.

### Interoperability

- Foreign boundaries are implemented.
- Collapse rules at boundaries are explicit.
- Host-language integration is stable.

### Tooling completeness

- Editor support is good enough for daily use.
- The debugger is strong enough to be the normal inspection interface.
- A browser playground exists.

### Project readiness

- Documentation is coherent.
- Examples are version-aligned.
- Packaging and installation are stable.
- Licensing is decided.

## What It Needs, In Priority Order

This is the roadmap I would follow.

### Phase 1: Lock semantics

This is the highest priority.

Deliverables:

- Decide exactly what a `𝕎` means inside a process.
- Decide whether process sampling yields descriptors, realized values, or both.
- Define how composed processes advance `tau`.
- Define what entanglement means under time evolution, not only manual transforms.
- Write semantic tests for all of the above.

Success condition:

- A short semantic reference document exists.
- The runtime, debugger, README, and examples agree with it.

### Phase 2: Make the compiler inspectable and safer

Deliverables:

- Wire `constraint_check.py` into the compile flow.
- Add REPL support for explaining compiled output.
- Store generated source and evidence reports in a predictable way.
- Add compiler provenance metadata: backend, model, retries, timestamp.
- Add a manual approval workflow for generated bodies.
- Add deterministic snapshots for offline tests.

Success condition:

- The user can ask “why did this compile this way?” and get a precise answer.

### Phase 3: Finish the language surface

Deliverables:

- Real expression grammar.
- Explicit-body function execution.
- Process declaration compilation.
- Better module semantics.
- Clear distinction between native New Code and embedded foreign code.

Success condition:

- A nontrivial `.nc` program can be written without silently depending on Python expressions everywhere.

### Phase 4: Build real interoperability

Deliverables:

- First FFI boundary.
- Explicit collapse-at-boundary behavior.
- Import/module story.
- Host runtime hooks for Python and, ideally later, JavaScript.

Success condition:

- New Code can meaningfully participate inside a larger system instead of existing only as a standalone experiment.

### Phase 5: Upgrade the debugger into the primary interface

Deliverables:

- Better time controls.
- Replay and recording.
- Focus/filter by process or entanglement group.
- Visual cues for collapse events and constraint violations.
- Stronger linking between source declarations and live traces.

Success condition:

- The debugger becomes the easiest way to understand a running New Code program.

### Phase 6: Prove the generalization claim

Deliverables:

- One strong non-audio UI demo.
- One strong agent/belief/confidence demo.
- One domain write-up explaining why the abstraction helped.

Success condition:

- New Code is no longer “an audio abstraction pretending to be general.”

### Phase 7: Productize the developer experience

Deliverables:

- Browser playground.
- Cleaner install process.
- More polished VS Code extension.
- Stable docs site.
- Tutorial flow for first-time users.
- Licensing and packaging cleanup.

Success condition:

- A new person can try it without reading the whole spec first.

## The Best Initial Demo To Build

If the goal is to show New Code’s potential quickly and honestly, I would build:

### Demo: Entangled Interface and Belief Lab

This is the right first demo because it proves three things at once:

- New Code is not just for audio metaphors.
- The language can model dynamic state structurally.
- The debugger is essential to the experience.

### Demo concept

Build a small browser-visible demo where:

- a toggle state is modeled as a `𝕎`
- its visual indicator is entangled with it
- a “calm belief” and an “anxious belief” are modeled as two other `𝕎`s
- one belief drifts over time
- coherence and distance between beliefs are shown live
- collapse to scalar is shown as an explicit boundary event

This demonstrates:

- intent-first functions
- entanglement
- drift
- coherence
- collapse
- debugger-led reading
- non-audio use of the primitive

### Why this is better than a pure audio demo

Audio proves the math works. UI/belief state proves the language idea works.

For a first public pitch, the second is more important.

## What the demo should include

### A score file

Create a `.nc` file that defines:

- `toggle_state`
- `indicator_state`
- `calm_belief`
- `anxious_belief`
- an amplify/preserve-shape function
- a drift/age function
- a coherence-measuring function
- a superposition/mix function

To stay within the current offline compiler, keep the intent wording close to the patterns it already knows.

### A small Python driver

The driver should:

- load the score
- compile the hole functions
- create the entangled pair
- create one or two processes
- start the debugger
- periodically sample the processes
- periodically transform or drift one side of the entangled pair
- print a few live scalar readings such as coherence distance

### A presentation-friendly flow

The demo should let you show, in order:

1. the source score with intent blocks
2. the generated function bodies
3. the running debugger view
4. entanglement propagation
5. drift over time
6. a visible collapse to scalar

That sequence makes the language legible in under five minutes.

## Suggested `.nc` file for the demo

This stays close to the current implemented compiler behavior.

```newcode
※ entangled_interface_lab.nc

let toggle_state : 𝕎 = w(f=60, A=1.0, phi=0.0, sigma=tri)
let indicator_state : 𝕎 = w(f=60, A=1.0, phi=0.0, sigma=tri)

let calm_belief : 𝕎 = w(f=0.1, A=0.9, phi=0.0, sigma=sine)
let anxious_belief : 𝕎 = w(f=5.0, A=0.3, phi=1.2, sigma=saw)

fn amplify_signal (signal : 𝕎, gain : ℝ) → 𝕎
    intent: 「scale the amplitude of signal by gain while preserving shape」
    forbid: 「do not modify phase」
    ensure: 「output shape equals input shape」
    ≔ ??

fn age_signal (signal : 𝕎, delta : ℝ) → 𝕎
    intent: 「drift signal by delta, ageing toward the square-wave attractor」
    forbid: 「nothing」
    ensure: 「amplitude does not increase」
    ≔ ??

fn compare_beliefs (a : 𝕎, b : 𝕎) → ℝ
    intent: 「measure the coherence between a and b as a scalar」
    forbid: 「claim to preserve structure」
    ensure: 「result is a real scalar」
    ≔ ??

fn mix_beliefs (a : 𝕎, b : 𝕎) → 𝕎
    intent: 「mix a and b by superpose」
    forbid: 「nothing」
    ensure: 「result preserves waveform structure」
    ≔ ??
```

## Suggested Python driver outline

This is the simplest practical shape for the current repo:

```python
from pathlib import Path
from newcode import *
from newcode.repl import REPL

r = REPL()
r.load_file("entangled_interface_lab.nc")

toggle = r.scope["toggle_state"]
indicator = r.scope["indicator_state"]
calm = r.scope["calm_belief"]
anxious = r.scope["anxious_belief"]

pair = entangle(toggle, indicator, via=identity, name="toggle_ui")

calm_proc = every(calm, name="calm")
anxious_proc = drift_process(every(anxious, name="anxious"), delta_per_step=0.08)

r.scope["pair"] = pair
r.scope["calm_proc"] = calm_proc
r.scope["anxious_proc"] = anxious_proc

server = start_debugger(r.scope, open_browser=True)
tracer = shared_tracer()
tracer.track_scope(r.scope)

print("Debugger:", server.url)
print("Initial belief distance:", d_gamma(calm, anxious))

for step in range(8):
    unfold(calm_proc, 1)
    values = unfold(anxious_proc, 1)
    aged = values[-1]
    print(f"step={step} anxious_distance={d_gamma(calm, aged):.4f}")

pair = pair.transform_left(invert)
print("Entangled pair flipped:", pair)
print("Collapsed anxious belief:", collapse(aged))
```

## How to present the demo

### Minute 1: show the source

Explain:

- humans write intent
- the compiler fills the body
- values are structured dynamic objects, not bare numbers

### Minute 2: show generated bodies

Use the REPL to show:

- `:src amplify_signal`
- `:src age_signal`
- `:src compare_beliefs`

This proves there is a working compilation path.

### Minute 3: show the debugger

Show:

- two tracked processes
- one entangled pair
- live unfolding

This proves the language is meant to be watched, not just read.

### Minute 4: show propagation

Invert the left side of the entangled pair and show the right side move with it.

This proves the coupling concept.

### Minute 5: show collapse

Collapse a belief to a scalar and explain that this is the moment where structural richness is intentionally lost.

This proves that collapse is not an implementation detail; it is part of the programming model.

## A Stronger Demo To Build After That

After the first demo, the best next step is a browser playground that combines:

- editor pane
- compile/review pane
- debugger pane
- live metric cards for coherence/collapse/drift

That would make New Code feel like a coherent system rather than a set of interesting pieces.

## My Honest Bottom Line

New Code’s best ideas are real:

- intent-first authoring
- structured dynamic values
- explicit collapse
- entanglement
- debugger-as-primary-interface

Its weakest parts are also clear:

- semantics are not locked
- the compiler is not trustworthy enough yet
- the process runtime is still prototype-level
- the language surface is incomplete
- interoperability is mostly missing

So the right strategy is not to broaden the vision further. It is to tighten the core until the current claims become undeniably true.

If I had to compress the completion strategy into one sentence:

> Make New Code smaller, clearer, more inspectable, and more demonstrably real before making it larger.

That is the path from “interesting prototype” to “fully working language”.
