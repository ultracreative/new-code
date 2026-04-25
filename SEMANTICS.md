# New Code v1.0 Semantics Lock

This file fixes the runtime meaning of v1.0 as it exists in this repository. When the spec, examples, and implementation drift, this file wins for v1.0.

## 1. `𝕎` is a descriptor, not a self-evolving object

A value of type `𝕎` is a static description of a pattern of change:

- `f` — frequency
- `A` — amplitude
- `phi` — phase
- `sigma` — shape

`𝕎` does not mutate or advance itself over time. What changes over time is the scalar obtained by observing it:

```python
w.realise(t)
```

That means:

- the descriptor may remain the same across process samples
- the observed scalar can still differ from one `tau` to the next
- the debugger visualises `realise(tau)`, not the descriptor

## 2. A `Process` owns `tau`

A `Process` is the runtime object that unfolds over time. On every call to:

```python
p.sample()
```

the runtime:

1. evaluates the process step at the current `tau`
2. returns that value
3. advances `tau` by `1 / rate`

`tau` is local to the process. There is no global clock.

## 3. `every(w)` emits the same descriptor at each tick

`every(w)` does not mutate `w`. It emits the same waveform descriptor each time it is sampled.

In v1.0:

- the process advances
- the descriptor does not
- the observed scalar is obtained separately through `realise(tau)`

## 4. Process combinators sample child processes

Combinators advance child processes through `sample()`, not by calling `step(...)` directly. Calling `step(...)` directly bypasses the child process clock and breaks the semantics.

### `series(a, b, ...)`

- samples child processes left-to-right
- feeds each emitted value to the next child as `incoming`
- if the next child does not accept an incoming argument, it ignores it
- returns the final child output

### `parallel(a, b)`

- samples both children once per observation step
- returns a pair `(a_value, b_value)`

### `feedback(inner, delay_samples=n)`

- keeps a delayed buffer of prior outputs
- offers the delayed value back to `inner` as `incoming`
- if `inner` does not accept an incoming argument, it ignores it

## 5. Input-aware processes are opt-in

Most built-in constructors use `step(tau)`. Explicit Python or expression-grammar process bodies may opt into `step(tau, incoming)`. This is how `series` and `feedback` carry data without changing constructor ergonomics.

## 6. Drift creates new descriptors

`drift(w, delta)` returns a new `𝕎`. `drift_process(p, delta_per_step)` samples the child once per step and applies drift to the sampled `𝕎`. So:

- plain `every(w)` emits a static descriptor repeatedly
- `drift_process(every(w), ...)` emits a changing sequence of descriptors

## 7. Compilation modes (v1.0 lock)

Every `Compiler` carries an explicit **mode**. The mode is the only thing that decides what happens to an intent hole (`≔ ??`).

| Mode      | Intent holes                                          | Explicit bodies | Network |
|-----------|-------------------------------------------------------|-----------------|---------|
| `offline` | offline pattern matcher only; otherwise `OfflineHoleError` | yes (parsed by expr.py)  | no      |
| `online`  | Anthropic API → AST safety → cache write              | yes             | yes     |
| `snapshot`| replay `SnapshotStore` from disk; miss → fall through | yes             | no      |

**Locked invariants:**

1. **Explicit bodies never require the network.** A `fn` whose body is anything other than `??` compiles in any mode without an API call.
2. **Mode is sticky.** A `Compiler(mode=offline)` will not silently upgrade itself to online when an API key appears.
3. **`OfflineHoleError` is the only failure mode.** If an intent hole reaches the offline backend without a matching pattern, the compiler raises `OfflineHoleError` with a fix-it message — it does not fall back to a different mode.
4. **Online compilation always writes to the snapshot store** unless `snapshot_store=None` is passed explicitly. The default store lives at `~/.newcode/snapshots/default.json`.

## 8. Provenance (v1.0 lock)

Every `Compiled` artefact carries a `Provenance` record with these fields:

- `backend` — `offline` | `anthropic` | `snapshot` | `explicit`.
- `model` — model name when applicable; `None` for `offline` and `explicit`.
- `intent_hash` — 16-hex-char SHA-256 prefix over the declaration shape (name, kind, args, return type, every populated intent clause). Stable across runs and across whitespace differences in the body.
- `body_hash` — 16-hex-char SHA-256 prefix over the produced Python body.
- `timestamp` — UTC ISO-8601, second-resolution.
- `accepted` — boolean. Set by the user via `:accept` (or auto-set for `offline` and `explicit`).
- `notes` — free-form string; e.g. retry count, "cache hit", "replayed from <file>".

**Locked invariants:**

1. **`intent_hash` ignores the body.** The same hole + intent block produces the same hash whether the user has accepted a body or not. This is what lets `:accept` round-trip into the snapshot store keyed by intent.
2. **`intent_hash` is collision-resistant for human use, not cryptographically perfect.** 16 hex chars = 64 bits. Sufficient for snapshot keys; not a substitute for digital signatures.
3. **`accepted` is the only user-controlled field.** Changing `accepted` requires `:accept` or `:reject` (or programmatic equivalents); the runtime never sets it from `False` to `True` automatically.
4. **`body_hash` is informational.** It does not gate execution; the AST safety pass and constraint report do.

## 9. Snapshot store semantics

A `SnapshotStore` is a JSON file mapping `intent_hash → { source, model, decl_name, body_hash, timestamp, accepted }`.

**Locked invariants:**

1. **A snapshot is keyed by intent_hash.** Two declarations with the same name but different intent text produce different keys.
2. **Cache hit short-circuits the API call.** The Anthropic backend consults the store before sending a prompt. A hit produces a `Compiled` with `provenance.notes = "cache hit"`.
3. **`SnapshotCompiler.require_accepted=True` filters out unaccepted entries.** Useful for CI: only replay things a human signed off on.
4. **Removal is explicit.** `:reject` removes the entry from the store on disk. The next compile in `online` mode re-prompts the model.

## 10. Expression evaluator semantics

The expression grammar (§4 of GRAMMAR.md) is parsed into an AST and lowered to Python by `expr.to_python_function` / `expr.to_python_expr`. The evaluator path (`expr.evaluate_source`) re-uses the lowering; there is no separate tree-walking interpreter.

**Locked invariants:**

1. **Same scope as the compiler.** The REPL evaluates a `let` RHS in the same `stdlib.build_scope()` that the compiler uses for assembled bodies. What's available to a hole-filled function is available to a `let`.
2. **Python fallback only on parse failure.** The REPL falls back to Python's `eval` only when the New Code grammar raises `ParseError` / `LexError`. A successful parse is binding even if execution fails.
3. **`python { ... }` blocks are first-class.** They are parsed by the expression layer and lowered as immediate-evaluated Python expressions. The forbidden-name list still applies.

## 11. Debugger semantics

Unchanged from v0.01:

- a process band is indexed by the process's own `tau`
- when a sampled value is a `𝕎`, the debugger plots `realise(tau)`
- the ribbon attached to a `𝕎` sample is a visualisation over `[tau_before, tau_after]`
- the ribbon is not a claim that the descriptor changed during that interval

## 12. What is still intentionally incomplete

These semantics are locked for v1.0, but the broader language is not finished. Still unresolved:

- formal verification of natural-language intent (the open problem at the heart of the spec)
- language-level synchronisation / re-coherence / `await` / streaming primitives
- graph-scale entanglement semantics (n-ary coupling networks)
- a more capable offline compiler (more pattern templates)

## 13. Short version

> `𝕎` describes change. `Process` owns time. `realise(tau)` is the observation. Combinators advance processes through sampling. The compiler has three modes — offline, online, snapshot — and every compiled body carries a content-addressable provenance record. `:accept` turns yesterday's online run into today's deterministic replay.
