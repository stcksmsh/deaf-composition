"""Orchestration: which fix strategy -- mix_fix (src/planner/mix_fix.py) or
leaf_retry (leaf_emit.py's feedback mechanism, per escalation.py) -- for a
failing composition review, and when to switch.

This is grounded in real evidence from one backbone failure resolved by
hand across 4 attempts (see memory.md), not a designed-in-the-abstract
policy:

  round 1 (baseline, 3 reasons) -> mix_fix (sidechain+2 EQ cuts) -> 1 reason.
  round 2 (1 reason) -> mix_fix again (revise the EQ) -> still 1 reason,
    but WORSE in substance (centroid moved the wrong direction, level
    dropped) -- reason *count* didn't change, so a naive "reasons went up
    or down" check misses this round's real regression. Caught by hand
    from reading the actual numbers, not from the review verdict alone.
  round 3 (still 1 reason) -> mix_fix again (highpass, confirmed the
    predictable-direction diagnosis) -> 3 reasons, unambiguously worse.
  round 4 (3 reasons, mix_fix now 2-for-3 non-improving) -> switched to
    leaf_retry -> 1 reason, but a NEW kind (loudness, not spectral) --
    the original problem is gone, a different one replaced it.

The one clean, real signal available from review data alone (not requiring
a human to read the substance) is reason *count* trending non-improving
across consecutive rounds of the same strategy. It's a genuinely crude
proxy -- round 2 above shows it can miss a real regression that doesn't
happen to change the count -- documented as a known limitation, not
hidden. `max_non_improving` defaults to 2 for consistency with
escalation.py's own DEFAULT_MAX_ATTEMPTS, not a value independently
tuned.

Explicitly NOT solved here: *why* a strategy is or isn't converging, or
what to try within it (mix_fix.py's own model call already handles "which
specific fix" -- this module only decides "which strategy family, and
when to give up on the current one"). And this module never invents
"leaf_retry" targets by itself -- the caller supplies which sibling(s) a
leaf_retry should target, since that requires reading which node_ids the
composition failure actually names, itself the kind of judgment call this
project has consistently routed to review.py's own structured
ReviewState.reasons rather than string-parsed here.
"""
from __future__ import annotations

from dataclasses import dataclass

from planner.node import ReviewState

DEFAULT_MAX_NON_IMPROVING = 2  # matches escalation.py's DEFAULT_MAX_ATTEMPTS


@dataclass(frozen=True)
class FixStrategy:
    action: str  # "mix_fix" | "leaf_retry" | "escalate" | "done"
    reason: str


def choose_fix_strategy(review_history: list[ReviewState], strategy_history: list[str],
                         max_non_improving: int = DEFAULT_MAX_NON_IMPROVING) -> FixStrategy:
    """review_history: the composition ReviewState after each round, in
    order, review_history[0] being the original pre-any-fix failure.
    strategy_history: the strategy used to PRODUCE each corresponding
    later round (len(strategy_history) == len(review_history) - 1)."""
    if review_history[-1].status.value == "passed":
        return FixStrategy("done", "composition review passes")

    if len(review_history) == 1:
        # No fix tried yet. Default to mix_fix first -- it's the cheaper,
        # more surgical option, and real data shows composition failures
        # are often genuinely relational (round 1 above resolved 2 of 3
        # reasons this way) rather than requiring a whole leaf redo.
        return FixStrategy("mix_fix", "first attempt -- try the cheaper relational fix first")

    last_strategy = strategy_history[-1]
    streak = 0
    for i in range(len(review_history) - 1, 0, -1):
        if strategy_history[i - 1] != last_strategy:
            break
        prev_n = len(review_history[i - 1].reasons)
        curr_n = len(review_history[i].reasons)
        if curr_n < prev_n:
            break  # this round improved -- streak ends here
        streak += 1

    if streak < max_non_improving:
        return FixStrategy(
            last_strategy,
            f"{last_strategy}: {streak} non-improving round(s) so far (threshold "
            f"{max_non_improving}) -- keep trying"
        )

    other = "leaf_retry" if last_strategy == "mix_fix" else "mix_fix"
    if other in strategy_history:
        return FixStrategy(
            "escalate",
            f"both mix_fix and leaf_retry already tried, neither converging -- "
            f"needs a human, not another automated guess"
        )
    return FixStrategy(
        other,
        f"{last_strategy} stalled for {streak} consecutive rounds -- switching to {other}"
    )
