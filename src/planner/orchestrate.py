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

The original version of this module used reason *count* trending
non-improving across consecutive rounds as its only signal -- a genuinely
crude proxy, and round 2 above is a real case where it missed a real
regression that didn't happen to change the count (percussion got quieter
and the combined mix trended down as unplanned side effects of an EQ
cut, neither of which changed how many reasons fired). A second, starker
case surfaced later the same session (round 4 of the backbone saga,
-42.1 LUFS, vs. round 5, near-total silence -- both counted as exactly
"1 reason").

**Hardened (2026-07-26)** to compare `ReviewState.metrics` -- the real
numbers (`worst_lufs_gap_db`, `undefined_lufs_count`, `worst_centroid_ratio`,
`combined_deficit_db`) `review_composition` already computes internally to
build its `reasons` text, now exposed directly instead of being thrown away
-- rather than raw reason count. `_round_severity()` turns those into one
comparable scalar per round, weighted so a categorically worse failure
(a sibling with undefined LUFS -- essentially producing no output at all)
can never read as an improvement over a merely-large gap, which is exactly
what the round-count proxy got wrong in spirit even when it happened to get
individual historical cases right. Falls back to reason count when
`metrics` is empty (e.g. a `ReviewState` built by hand or replayed from
before this field existed), so old callers and historical data keep
working. `max_non_improving` defaults to 2 for consistency with
escalation.py's own DEFAULT_MAX_ATTEMPTS, not a value independently tuned.

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
from planner.review import SPECTRAL_OVERLAP_RATIO_THRESHOLD

DEFAULT_MAX_NON_IMPROVING = 2  # matches escalation.py's DEFAULT_MAX_ATTEMPTS

# A sibling with undefined LUFS means "produced no audible output" -- a
# categorically worse failure than any loudness gap or spectral overlap
# number, so it dominates the severity score outright. Round 4 (-42.1 LUFS,
# a real but merely large gap) vs. round 5 (near-total silence) of the
# backbone saga both reported as "1 reason" -- this weight is what makes
# _round_severity tell them apart instead of treating them as equal.
UNDEFINED_LUFS_PENALTY = 1000.0
CENTROID_OVERLAP_WEIGHT = 10.0  # scales a 0-1-ish ratio deficit onto a dB-like range


def _round_severity(review: ReviewState) -> float | None:
    """One comparable scalar per round from the real numbers behind a
    composition review's `reasons` text, or None if `metrics` wasn't
    populated (old/replayed data) -- callers should fall back to reason
    count in that case."""
    m = review.metrics
    if not m:
        return None
    score = UNDEFINED_LUFS_PENALTY * m.get("undefined_lufs_count", 0)
    if m.get("worst_lufs_gap_db") is not None:
        score += m["worst_lufs_gap_db"]
    if m.get("worst_centroid_ratio") is not None:
        score += max(0.0, SPECTRAL_OVERLAP_RATIO_THRESHOLD - m["worst_centroid_ratio"]) \
                 * CENTROID_OVERLAP_WEIGHT
    if m.get("combined_undefined"):
        score += UNDEFINED_LUFS_PENALTY
    elif m.get("combined_deficit_db") is not None and m["combined_deficit_db"] > 0:
        score += m["combined_deficit_db"]
    return score


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
        prev_severity = _round_severity(review_history[i - 1])
        curr_severity = _round_severity(review_history[i])
        if prev_severity is not None and curr_severity is not None:
            if curr_severity < prev_severity:
                break  # this round improved in real magnitude -- streak ends here
        else:
            # metrics missing (old/replayed ReviewState) -- fall back to the
            # original reason-count proxy rather than refusing to decide.
            prev_n = len(review_history[i - 1].reasons)
            curr_n = len(review_history[i].reasons)
            if curr_n < prev_n:
                break
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
