#!/usr/bin/env python3
"""
Validates choose_fix_strategy() against this session's real 4-round
backbone fix history -- not a synthetic test, the actual ReviewState
reasons produced by real review_composition calls this session, replayed
through the decision function to see whether it reproduces a sensible
strategy sequence (not necessarily identical to what was done by hand,
which included deliberate mix_fix exploration for diagnostic value the
policy has no reason to replicate).

Run:
    .venv/bin/python scripts/orchestrate_validate.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from planner.node import ReviewState, ReviewStatus  # noqa: E402
from planner.orchestrate import choose_fix_strategy  # noqa: E402


def failed(*reasons: str) -> ReviewState:
    return ReviewState(status=ReviewStatus.FAILED, reasons=reasons)


# The real reason strings from this session's actual review_composition
# calls (drop_tree_review.py, backbone_fix_review.py, _2.py, _3.py,
# backbone_reemit_review.py) -- shortened here, full text is in memory.md.
ROUNDS = [
    failed(
        "kick-perc 12.6dB apart",
        "kick-perc centroid ratio 1.45",
        "perc-bass centroid ratio 1.38",
    ),  # round 0: baseline
    failed("perc-bass centroid ratio 1.03"),  # round 1: after mix_fix pass 1
    failed("perc-bass centroid ratio 1.08"),  # round 2: after mix_fix pass 2
    failed(
        "kick-perc 14.3dB apart",
        "kick-perc centroid ratio 1.44",
        "perc-bass centroid ratio 1.43",
    ),  # round 3: after mix_fix pass 3 (highpass)
    failed("perc-bass 13.0dB apart"),  # round 4: after leaf_retry
]

ACTUAL_STRATEGIES = ["mix_fix", "mix_fix", "mix_fix", "leaf_retry"]


def main() -> int:
    review_history = [ROUNDS[0]]
    strategy_history: list[str] = []

    for round_num in range(1, len(ROUNDS)):
        decision = choose_fix_strategy(review_history, strategy_history)
        actual = ACTUAL_STRATEGIES[round_num - 1]
        match = "MATCH" if decision.action == actual else "differs"
        print(f"Before round {round_num}: policy says {decision.action!r} "
              f"({decision.reason})")
        print(f"  actually done: {actual!r} -- {match}\n")

        strategy_history.append(actual)
        review_history.append(ROUNDS[round_num])

    final_decision = choose_fix_strategy(review_history, strategy_history)
    print(f"After round {len(ROUNDS) - 1} (leaf_retry, real result: "
          f"1 reason, still failing): policy says {final_decision.action!r} "
          f"({final_decision.reason})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
