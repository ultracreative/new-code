※ examples/demo.nc
※ A small demonstration of New Code v0.01.
※ Load with: python -m newcode.repl examples/demo.nc

※ A waveform literal: 440 Hz, full amplitude, zero phase, sine shape.
let concert_a : 𝕎 = w(f=440, A=1.0, phi=0.0, sigma=sine)

※ A detuned version, two cents flat.
let slightly_flat : 𝕎 = w(f=439.5, A=1.0, phi=0.0, sigma=sine)

※ A pattern-matched compilation: the offline compiler knows "scale the
※ amplitude". The intent block is the function, from the human side. The
※ body is a hole; the compiler fills it.
fn amplify (signal : 𝕎, gain : ℝ) → 𝕎
    intent: 「scale the amplitude of signal by gain while preserving shape」
    forbid: 「do not modify phase」
    ensure: 「output shape equals input shape」
    ≔ ??

※ Drift: the operator that expresses ageing, decay, and thermodynamic
※ termination as a single motion toward the square-wave attractor.
fn age (signal : 𝕎, delta : ℝ) → 𝕎
    intent: 「drift signal by delta, ageing toward the square-wave attractor」
    forbid: 「nothing」
    ensure: 「amplitude does not increase」
    ≔ ??

※ A collapse: the bridge to conventional systems. This reduces a
※ structured value to a scalar and makes the loss visible.
fn to_scalar (signal : 𝕎) → ℝ
    intent: 「collapse signal to a single real number by coherence with the unit oscillator」
    forbid: 「claim to preserve structure」
    ensure: 「result is a real scalar」
    ≔ ??
