※ examples/ui_state.nc
※
※ New Code is not a DSL for audio. The 𝕎 primitive generalises.
※
※ In a UI, a piece of state has:
※   f     — how often it updates (refresh rate)
※   A     — its salience (how strong the visual change is)
※   phi   — its offset relative to user attention (latency, lag)
※   sigma — the form of its update curve (linear ramp, ease-in, spring…)
※
※ Two pieces of UI state that are *supposed* to stay consistent (a toggle
※ and its visual indicator, a form and its preview, a leader and a follower
※ animation) are exactly the kind of bug that "entangle via Φ" fixes. In a
※ conventional language this is discipline; in New Code it is the type.

※ A toggle switch: updates 60 times a second, full salience, no latency,
※ eases in with a triangle ramp.
let toggle_state : 𝕎 = w(f=60, A=1.0, phi=0.0, sigma=tri)

※ Its visual indicator, which must follow the toggle. We declare the
※ coupling function and entangle them. In the real implementation this
※ is what the spec means by entanglement: the language enforces what the
※ domain requires.
let indicator : 𝕎 = w(f=60, A=1.0, phi=0.0, sigma=tri)

※ A belief system: how often do you revise this belief, how strongly do
※ you hold it, where are you in the update cycle, what shape does your
※ revising take? A confident, slowly-revised belief has low f and high A.
※ An anxious one has high f and deforming sigma.
let a_strong_slow_belief : 𝕎 = w(f=0.1, A=0.9, phi=0.0, sigma=sine)
let an_anxious_belief : 𝕎 = w(f=5.0, A=0.3, phi=1.2, sigma=saw)

※ The point is not that audio and UI and belief are all "really the same".
※ The point is that the *description* needed for each one is the same
※ four components, and so the same operators, the same entanglement
※ declarations, and the same collapse rules apply. New Code is the
※ language in which that observation becomes code.

fn preserve_shape (signal : 𝕎, gain : ℝ) → 𝕎
    intent: 「scale the amplitude of signal by gain while preserving shape」
    forbid: 「do not modify phase」
    ensure: 「output shape equals input shape」
    ≔ ??
