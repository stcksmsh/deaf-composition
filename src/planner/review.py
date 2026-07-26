"""Fold/review (plan §3.6) -- the piece node.py's own docstring explicitly
deferred ("no split/decompose/fold logic yet"). All three of plan §3.6's
checks now have real code:

  1. own acceptance criteria -- reference.score_node against the reference
     envelope, exactly what leaf_proof.py/leaf_emit.py called by hand.
  2. composes with siblings -- a real, if deliberately lightweight,
     structural coupling check between simultaneous children's own solo
     measurements plus an actual combined-mix render (see
     review_composition's own docstring).
  3. seams hold -- a real, deliberately looser check between timeline-
     *adjacent* nodes' boundary windows (see review_seam's own docstring).
     Needed two sections to actually sit sequentially on the timeline
     before this was even testable -- the first two proof runs
     (fold_proof.py, build_section_review.py) both built parallel layers
     of one section, not sequential ones.
"""
from __future__ import annotations

import itertools

from planner.node import Node, ReviewState, ReviewStatus
from return_channel import reference

# If one sibling sits more than this many dB away from another meant to
# occupy the same section, it will bury (or vanish under) the other before
# any mixing decision even happens -- a real coupling failure, not a taste
# call, so it belongs in an automated review rather than waiting for a human.
LOUDNESS_BALANCE_THRESHOLD_DB = 12.0

# Two siblings whose solo spectral centroids sit within half an octave of
# each other (ratio < 1.5) occupy close to the same register -- a real risk
# they'll compete for the same sonic space once mixed together, independent
# of loudness balance.
SPECTRAL_OVERLAP_RATIO_THRESHOLD = 1.5

# For uncorrelated/incoherent sources, combining them should never make the
# result quieter than the loudest single ingredient -- energy adds. If the
# actual combined-mix render comes in more than this many dB quieter than
# the loudest solo sibling, that's a real signal of phase cancellation or
# something wrong in the render chain, not just "close balance."
COMBINED_QUIETER_THAN_LOUDEST_DB = 3.0

# A seam is a boundary between timeline-*adjacent* nodes (plan §3.4's local
# edges), not simultaneous siblings -- a real handoff can legitimately jump
# in both loudness and timbre (that's often the whole point of a section
# change), so these thresholds are deliberately looser than the composition
# checks above. What they catch is an *abrupt* jump with nothing bridging
# it, not a deliberate contrast.
SEAM_LOUDNESS_JUMP_THRESHOLD_DB = 10.0
SEAM_SPECTRAL_JUMP_RATIO_THRESHOLD = 2.0  # more than an octave right at the boundary


def review_leaf(node: Node, state: dict, library: dict) -> tuple[ReviewState, dict]:
    """Check 1: does this leaf, on its own, meet its own acceptance criteria?"""
    ac = node.acceptance_criteria
    score = reference.score_node(state, library, ac.target_section_type)
    measured_dist = score["measured"]["distance"]
    embedding_dist = score["embedding"]["distance"]

    reasons = []
    if ac.max_measured_distance is not None and (
        measured_dist is None or measured_dist > ac.max_measured_distance
    ):
        reasons.append(
            f"measured distance {measured_dist:.3f} exceeds threshold "
            f"{ac.max_measured_distance}"
        )
    if ac.max_embedding_distance is not None and (
        embedding_dist is None or embedding_dist > ac.max_embedding_distance
    ):
        reasons.append(
            f"embedding distance {embedding_dist:.3f} exceeds threshold "
            f"{ac.max_embedding_distance}"
        )

    own_criteria_met = not reasons
    review = ReviewState(
        status=ReviewStatus.PASSED if own_criteria_met else ReviewStatus.FAILED,
        reasons=tuple(reasons),
        own_criteria_met=own_criteria_met,
    )
    return review, score


def review_composition(sibling_states: dict[str, dict],
                        combined_state: dict | None = None) -> ReviewState:
    """Check 2: do these siblings actually work together?

    Three real checks, two purely from each child's own solo state.json,
    one from an actual combined-mix render:

    1. Loudness balance -- do the children's own solo LUFS sit close enough
       that neither buries the other before any mixing decision happens?
    2. Spectral overlap -- do their solo spectral centroids sit far enough
       apart that they're not competing for the same register?
    3. Combined-mix sanity (only if `combined_state` is given -- an actual
       render of the section with every child audible together, not
       inferred from the solo renders): is the mix at least as loud as its
       loudest ingredient? For uncorrelated sources this should always hold;
       a violation is a real signal of phase cancellation or a render-chain
       bug, not just poor balance.

    Checks 1-2 don't need a combined render at all -- they're real structural
    facts available the moment both children have been individually
    reviewed, before any mix even exists. Check 3 is the genuine "does the
    actual combination hold up" test on top of that; still no spectral
    masking model of the combined render itself (does the pad's harmonic
    content actually get eaten once the bells are added) -- that's real
    future work, deliberately not built here.
    """
    lufs = {node_id: s["measured"]["lufs"] for node_id, s in sibling_states.items()}
    centroids = {node_id: s["measured"]["spectral_centroid"]["median"]
                 for node_id, s in sibling_states.items()}
    reasons = []

    for (a_id, a_lufs), (b_id, b_lufs) in itertools.combinations(lufs.items(), 2):
        gap = abs(a_lufs - b_lufs)
        if gap > LOUDNESS_BALANCE_THRESHOLD_DB:
            reasons.append(
                f"{a_id} ({a_lufs:.1f} LUFS) and {b_id} ({b_lufs:.1f} LUFS) are "
                f"{gap:.1f} dB apart -- risk of one burying the other"
            )

    for (a_id, a_c), (b_id, b_c) in itertools.combinations(centroids.items(), 2):
        if a_c <= 0 or b_c <= 0:
            continue
        ratio = max(a_c, b_c) / min(a_c, b_c)
        if ratio < SPECTRAL_OVERLAP_RATIO_THRESHOLD:
            reasons.append(
                f"{a_id} ({a_c:.0f}Hz) and {b_id} ({b_c:.0f}Hz) spectral centroids "
                f"are within half an octave (ratio {ratio:.2f}) -- risk of "
                f"competing for the same register"
            )

    if combined_state is not None and lufs:
        combined_lufs = combined_state["measured"]["lufs"]
        loudest_id, loudest_lufs = max(lufs.items(), key=lambda kv: kv[1])
        if combined_lufs < loudest_lufs - COMBINED_QUIETER_THAN_LOUDEST_DB:
            reasons.append(
                f"combined mix ({combined_lufs:.1f} LUFS) is quieter than its "
                f"loudest solo layer {loudest_id} ({loudest_lufs:.1f} LUFS) by "
                f"more than {COMBINED_QUIETER_THAN_LOUDEST_DB}dB -- signals "
                f"cancellation, not just close balance"
            )

    composes = not reasons
    return ReviewState(
        status=ReviewStatus.PASSED if composes else ReviewStatus.FAILED,
        reasons=tuple(reasons),
        composes_with_siblings=composes,
    )


def review_seam(before_state: dict, after_state: dict) -> ReviewState:
    """Check 3 (plan §3.6): does the handoff between two timeline-*adjacent*
    nodes hold? `before_state`/`after_state` should be short windows right
    at the boundary (e.g. the last few seconds of one section, the first
    few of the next), not the sections' own full-length measured stats --
    a seam is a local property of the boundary itself, not whatever each
    section averages out to overall. Judged at the lowest common ancestor
    that can see both sides (plan §3.6) -- the caller is responsible for
    that; this function only computes the verdict.

    Deliberately looser thresholds than review_composition's simultaneous-
    sibling checks (see the threshold constants' own comments): a section
    change is often *supposed* to jump in loudness or timbre. What this
    catches is an abrupt jump with nothing bridging it, not a deliberate
    contrast -- still a real, if coarse, distinction, not a stand-in for
    one. A genuine "does this transition work musically" judgment is well
    beyond what a measurement-only check can make."""
    reasons = []

    before_lufs = before_state["measured"]["lufs"]
    after_lufs = after_state["measured"]["lufs"]
    gap = abs(after_lufs - before_lufs)
    if gap > SEAM_LOUDNESS_JUMP_THRESHOLD_DB:
        reasons.append(
            f"loudness jumps {gap:.1f}dB across the seam "
            f"({before_lufs:.1f} -> {after_lufs:.1f} LUFS)"
        )

    before_c = before_state["measured"]["spectral_centroid"]["median"]
    after_c = after_state["measured"]["spectral_centroid"]["median"]
    if before_c > 0 and after_c > 0:
        ratio = max(before_c, after_c) / min(before_c, after_c)
        if ratio > SEAM_SPECTRAL_JUMP_RATIO_THRESHOLD:
            reasons.append(
                f"spectral centroid jumps from {before_c:.0f}Hz to {after_c:.0f}Hz "
                f"(ratio {ratio:.2f}) -- an abrupt timbral shift right at the boundary"
            )

    seams_hold = not reasons
    return ReviewState(
        status=ReviewStatus.PASSED if seams_hold else ReviewStatus.FAILED,
        reasons=tuple(reasons),
        seams_hold=seams_hold,
    )
