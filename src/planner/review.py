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

# A sibling this sparse (fraction of frames above the silence gate) has its
# integrated LUFS structurally diluted by however much silence sits between
# hits -- found for real (2026-07-26) on a kick drum: max-velocity 0.125s hits
# on a clean on-beat pattern measured -39.6 LUFS (vs. -24.0dB sample_peak,
# crest_factor 20.5dB, active_ratio 0.175) purely because BS.1770 loudness
# blocks are 400ms wide, several times longer than the hit itself -- no
# gating scheme rescues that, since the dilution happens inside each
# analysis block before gating ever sees it. Comparing integrated LUFS
# between a sparse transient part and a denser/more continuous one is
# comparing different things; this was very likely a real contributor to
# why an earlier multi-round mix-fix saga on exactly this kick/percussion
# pairing never fully converged. Below this active_ratio, the loudness-
# balance check falls back to sample_peak (duty-cycle independent) instead.
SPARSE_ACTIVE_RATIO_THRESHOLD = 0.5
PEAK_BALANCE_THRESHOLD_DB = 12.0

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

# Cross-section contrast (arc-level, plan §6): the inverse problem from
# review_seam's -- not "does the boundary jump too hard" but "does section N
# actually differ from N-1 AND N-2" (the N-2 leg specifically guards against
# back-and-forth repetition -- A/B/A -- which an adjacent-only check can't
# see, since A vs. the immediately-preceding B always looks different).
# Deliberately NOT derived from mining the reference library's own
# section-to-section deltas (arc.py's design explicitly treats "too much
# reference is just copying") -- picked instead as a rough perceptual
# floor: a few dB is in the neighborhood of a loudness JND in a full mix,
# and a ~15% centroid shift (ratio 1.15) is a mild but real, audible
# timbral move. Both thresholds intentionally sit well below
# review_composition's/review_seam's own badness thresholds (10-12dB,
# 1.5-2x): those ask "is this dangerously off", this asks "is this
# suspiciously almost-identical" -- a much lower bar.
ARC_CONTRAST_MIN_LOUDNESS_GAP_DB = 3.0
ARC_CONTRAST_MIN_CENTROID_RATIO = 1.15


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
    peaks = {node_id: s["measured"]["sample_peak"] for node_id, s in sibling_states.items()}
    active_ratios = {node_id: s["measured"].get("active_ratio", 1.0)
                      for node_id, s in sibling_states.items()}
    centroids = {node_id: s["measured"]["spectral_centroid"]["median"]
                 for node_id, s in sibling_states.items()}
    reasons = []
    worst_lufs_gap_db = None
    worst_centroid_ratio = None  # closest to 1.0 = worst overlap
    used_peak_for_sparse_pair = False

    # A sibling with undefined LUFS (pyloudnorm's own signal for "too short
    # or essentially silent," per analyze.py) is already a worse problem than
    # a loudness *gap* -- flag it directly instead of crashing on `abs(x -
    # None)` or silently excluding it from the balance check as if it were
    # fine.
    silent_siblings = [node_id for node_id, v in lufs.items() if v is None]
    for node_id in silent_siblings:
        reasons.append(f"{node_id} has undefined LUFS (essentially silent output)")

    voiced_lufs = {k: v for k, v in lufs.items() if v is not None}
    for (a_id, a_lufs), (b_id, b_lufs) in itertools.combinations(voiced_lufs.items(), 2):
        # A sparse part's integrated LUFS is diluted by however much silence
        # sits between hits -- comparing it against a denser/continuous
        # sibling's LUFS compares different things (see
        # SPARSE_ACTIVE_RATIO_THRESHOLD's docstring). Fall back to sample_peak
        # (duty-cycle independent) for any pair involving a sparse sibling.
        if (active_ratios.get(a_id, 1.0) < SPARSE_ACTIVE_RATIO_THRESHOLD
                or active_ratios.get(b_id, 1.0) < SPARSE_ACTIVE_RATIO_THRESHOLD):
            used_peak_for_sparse_pair = True
            a_peak, b_peak = peaks[a_id], peaks[b_id]
            gap = abs(a_peak - b_peak)
            worst_lufs_gap_db = gap if worst_lufs_gap_db is None else max(worst_lufs_gap_db, gap)
            if gap > PEAK_BALANCE_THRESHOLD_DB:
                reasons.append(
                    f"{a_id} ({a_peak:.1f}dB peak) and {b_id} ({b_peak:.1f}dB peak) are "
                    f"{gap:.1f} dB apart -- risk of one burying the other (compared by "
                    f"peak, not LUFS, since at least one is sparse enough that integrated "
                    f"loudness would be diluted by silence between hits)"
                )
            continue
        gap = abs(a_lufs - b_lufs)
        worst_lufs_gap_db = gap if worst_lufs_gap_db is None else max(worst_lufs_gap_db, gap)
        if gap > LOUDNESS_BALANCE_THRESHOLD_DB:
            reasons.append(
                f"{a_id} ({a_lufs:.1f} LUFS) and {b_id} ({b_lufs:.1f} LUFS) are "
                f"{gap:.1f} dB apart -- risk of one burying the other"
            )

    voiced_centroids = {k: v for k, v in centroids.items() if v is not None and v > 0}
    for (a_id, a_c), (b_id, b_c) in itertools.combinations(voiced_centroids.items(), 2):
        ratio = max(a_c, b_c) / min(a_c, b_c)
        worst_centroid_ratio = (ratio if worst_centroid_ratio is None
                                 else min(worst_centroid_ratio, ratio))
        if ratio < SPECTRAL_OVERLAP_RATIO_THRESHOLD:
            reasons.append(
                f"{a_id} ({a_c:.0f}Hz) and {b_id} ({b_c:.0f}Hz) spectral centroids "
                f"are within half an octave (ratio {ratio:.2f}) -- risk of "
                f"competing for the same register"
            )

    combined_deficit_db = None
    combined_lufs_value = None
    if combined_state is not None and voiced_lufs:
        combined_lufs = combined_state["measured"]["lufs"]
        combined_lufs_value = combined_lufs
        loudest_id, loudest_lufs = max(voiced_lufs.items(), key=lambda kv: kv[1])
        if combined_lufs is None:
            reasons.append("combined mix has undefined LUFS (essentially silent output)")
        else:
            combined_deficit_db = loudest_lufs - combined_lufs
            if combined_deficit_db > COMBINED_QUIETER_THAN_LOUDEST_DB:
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
        metrics={
            "undefined_lufs_count": len(silent_siblings),
            "worst_lufs_gap_db": worst_lufs_gap_db,
            "worst_centroid_ratio": worst_centroid_ratio,
            "combined_lufs": combined_lufs_value,
            "combined_deficit_db": combined_deficit_db,
            "combined_undefined": combined_state is not None and combined_lufs_value is None
                                  and bool(voiced_lufs),
            "used_peak_for_sparse_pair": used_peak_for_sparse_pair,
        },
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


def review_arc_contrast(ordered_states: list[dict],
                         labels: list[str] | None = None) -> ReviewState:
    """New composition-review check (plan §6, arc-level): for each section
    i (i>=1), compare its rendered state against i-1, and (i>=2) against
    i-2 too -- the i-2 leg is what guards against back-and-forth repetition
    (A/B/A), not just adjacent sameness, which review_seam alone can't
    catch since it only ever looks at one boundary at a time.

    Flags INSUFFICIENT difference (too similar), the mirror image of
    review_seam's excessive-jump check -- reuses the same loudness-gap /
    centroid-ratio primitives already used by review_composition and
    review_seam (this file still has no shared state-vs-state delta
    helper; every check computes its own gap/ratio inline -- a real,
    pre-existing gap, not something this change should silently start
    fixing under a different task).

    A pair only fails when BOTH loudness and centroid are close --
    differing meaningfully on either axis alone is real contrast.

    ordered_states must be in timeline order. labels (optional) are used
    only for readable reasons text; defaults to "section[i]" when omitted.
    """
    labels = labels or [f"section[{i}]" for i in range(len(ordered_states))]
    reasons = []
    insufficient_pairs: list[tuple[int, int]] = []
    worst_gap_db = None          # smallest observed gap across all checked pairs
    worst_centroid_ratio = None  # closest to 1.0 across all checked pairs

    def _gap_and_ratio(a: dict, b: dict) -> tuple[float | None, float | None]:
        a_lufs = a["measured"]["lufs"]
        b_lufs = b["measured"]["lufs"]
        gap = None
        if a_lufs is not None and b_lufs is not None:
            gap = abs(a_lufs - b_lufs)
        a_c = a["measured"]["spectral_centroid"]["median"]
        b_c = b["measured"]["spectral_centroid"]["median"]
        ratio = None
        if a_c and b_c:
            ratio = max(a_c, b_c) / min(a_c, b_c)
        return gap, ratio

    pairs_checked = 0
    for i in range(1, len(ordered_states)):
        for j in (i - 1, i - 2):
            if j < 0:
                continue
            gap, ratio = _gap_and_ratio(ordered_states[i], ordered_states[j])
            if gap is None or ratio is None:
                continue  # undefined LUFS/centroid handled by review_leaf/
                          # review_composition already; not re-flagged here
            pairs_checked += 1
            worst_gap_db = gap if worst_gap_db is None else min(worst_gap_db, gap)
            worst_centroid_ratio = (ratio if worst_centroid_ratio is None
                                     else min(worst_centroid_ratio, ratio))
            if (gap < ARC_CONTRAST_MIN_LOUDNESS_GAP_DB
                    and ratio < ARC_CONTRAST_MIN_CENTROID_RATIO):
                insufficient_pairs.append((i, j))
                reasons.append(
                    f"{labels[i]} and {labels[j]} are too similar -- "
                    f"{gap:.1f}dB apart and centroid ratio {ratio:.2f} "
                    f"(need >= {ARC_CONTRAST_MIN_LOUDNESS_GAP_DB}dB or "
                    f">= {ARC_CONTRAST_MIN_CENTROID_RATIO} ratio on at "
                    f"least one axis)"
                )

    ok = not reasons
    return ReviewState(
        status=ReviewStatus.PASSED if ok else ReviewStatus.FAILED,
        reasons=tuple(reasons),
        metrics={
            "worst_gap_db": worst_gap_db,
            "worst_centroid_ratio": worst_centroid_ratio,
            "insufficient_pairs": insufficient_pairs,
            "pairs_checked": pairs_checked,
        },
    )
