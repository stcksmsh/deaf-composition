"""Minimal fold/review (plan §3.6) -- the piece node.py's own docstring
explicitly deferred ("no split/decompose/fold logic yet"). Only the two
checks a real leaf pair can actually exercise right now:

  1. own acceptance criteria -- reference.score_node against the reference
     envelope, exactly what leaf_proof.py/leaf_emit.py called by hand.
  2. composes with siblings -- a real, if deliberately lightweight,
     structural coupling check between two already-scored children's own
     solo measurements (not a combined mixed render -- see review_composition's
     docstring for why that's a scoped-down version, not a placeholder).

Seam continuity (plan §3.6 check 3) isn't here: it applies to sequential
timeline neighbors sharing a boundary (plan §3.4's local edges), and the
two leaves this module was first run against are parallel layers of the
same section, not timeline-adjacent -- there's no seam between them to
check yet.
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


def review_composition(sibling_states: dict[str, dict]) -> ReviewState:
    """Check 2: do the children's own solo measurements sit in a workable
    loudness balance? Deliberately scoped to each child's own state.json
    (measured.lufs) rather than rendering a combined mix -- a full mixed-
    render composition check (does the pad get masked once the bells sit on
    top of it, spectrally, not just in level) is real future work, not
    built here. This is still a genuine structural fact a review can catch
    on its own, not a stand-in for one."""
    lufs = {node_id: s["measured"]["lufs"] for node_id, s in sibling_states.items()}
    reasons = []
    for (a_id, a_lufs), (b_id, b_lufs) in itertools.combinations(lufs.items(), 2):
        gap = abs(a_lufs - b_lufs)
        if gap > LOUDNESS_BALANCE_THRESHOLD_DB:
            reasons.append(
                f"{a_id} ({a_lufs:.1f} LUFS) and {b_id} ({b_lufs:.1f} LUFS) are "
                f"{gap:.1f} dB apart -- risk of one burying the other"
            )

    composes = not reasons
    return ReviewState(
        status=ReviewStatus.PASSED if composes else ReviewStatus.FAILED,
        reasons=tuple(reasons),
        composes_with_siblings=composes,
    )
