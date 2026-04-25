from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from newcode import collapse, d_gamma, entangle, identity, invert, shared_tracer, start_debugger, unfold
from newcode.repl import REPL


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the New Code entangled interface demo."
    )
    parser.add_argument("--steps", type=int, default=8, help="Number of process steps to unfold.")
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Start the debugger server without opening a browser tab.",
    )
    args = parser.parse_args()

    score_path = Path(__file__).with_name("entangled_interface_lab.nc")

    repl = REPL()
    repl.load_file(str(score_path))

    toggle = repl.scope["toggle_state"]
    indicator = repl.scope["indicator_state"]
    calm = repl.scope["calm_belief"]
    anxious = repl.scope["anxious_belief"]

    pair = entangle(toggle, indicator, via=identity, name="toggle_ui")
    repl.scope["toggle_pair"] = pair

    try:
        server = start_debugger(repl.scope, open_browser=not args.no_browser)
        tracer = shared_tracer()
        tracer.track_scope(repl.scope)
    except OSError as exc:
        server = None
        print(f"Debugger unavailable in this environment: {exc}")
    else:
        print(f"Debugger: {server.url}")
    print()
    print("Compiled bodies:")
    for name in ("amplify_signal", "age_signal", "compare_beliefs", "mix_beliefs", "calm_loop", "anxious_loop"):
        compiled = repl.compiled_meta[name]
        print(f"[{name}] {compiled.notes}")
        print(compiled.source)
        print()

    print("Initial metrics:")
    print(f"  coherence distance(calm, anxious) = {d_gamma(calm, anxious):.4f}")
    print(f"  compare_beliefs(calm, anxious)    = {repl.scope['compare_beliefs'](calm, anxious):.4f}")
    print()

    calm_proc = repl.scope["calm_loop"]
    anxious_proc = repl.scope["anxious_loop"]

    print("Unfolding:")
    latest_anxious = anxious
    for step in range(args.steps):
        calm_value = unfold(calm_proc, 1)[-1]
        latest_anxious = unfold(anxious_proc, 1)[-1]
        mixed = repl.scope["mix_beliefs"](calm_value, latest_anxious)
        print(
            f"  step={step:02d} "
            f"anxious_distance={d_gamma(calm_value, latest_anxious):.4f} "
            f"mixed_amp={mixed.A:.4f}"
        )

    print()
    print("Entanglement:")
    pair.transform_left(invert)
    print(f"  toggle_pair = {pair}")

    print()
    print("Collapse:")
    print(f"  collapse(latest anxious belief) = {collapse(latest_anxious):.4f}")
    print(f"  age_signal(anxious, 0.2)        = {repl.scope['age_signal'](anxious, 0.2)!r}")
    print(f"  amplify_signal(toggle, 1.5)     = {repl.scope['amplify_signal'](toggle, 1.5)!r}")


if __name__ == "__main__":
    main()
