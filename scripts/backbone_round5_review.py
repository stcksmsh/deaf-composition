#!/usr/bin/env python3
"""
Verifies round 5's real outcome: the live-orchestrated leaf retry
(Percussion/Synth Tom 2.fxp, mid-range notes) against the backbone
composition check.

Run:
    RETURN_CHANNEL_CLAP_CHECKPOINT=experiments/exp1/music_audioset_epoch_15_esc_90.14.pt \
        .venv/bin/python scripts/backbone_round5_review.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from planner.node import Node  # noqa: E402
from planner.review import review_composition, review_leaf  # noqa: E402
from return_channel import reference, state  # noqa: E402

LIBRARY = ROOT / "reference_library.json"
PROJECT = ROOT / "state/scratch/session.rpp"
PLAN = ROOT / "state/leaf_proof/drop_tree_plan.json"

KICK_ID = "proof/section_drop/child_0/child_0"
PERC_ID = "proof/section_drop/child_0/child_1"
BASS_ID = "proof/section_drop/child_0/child_2"


def main() -> int:
    plan = json.loads(PLAN.read_text())
    perc_node = Node.from_dict(plan["nodes"][PERC_ID])
    library = reference.load_library(LIBRARY)

    kick_built = json.loads((ROOT / "state/leaf_proof/drop_leaf_0_kick.state.json").read_text())
    bass_built = json.loads((ROOT / "state/leaf_proof/drop_leaf_2_bass_fixed3.state.json").read_text())

    perc_wav = ROOT / "state/leaf_proof/drop_leaf_1_perc_round5.wav"
    perc_built = state.build(project=PROJECT, wav=perc_wav, region=None,
                              track="DROP percussion", embedding=True)
    state.write(perc_built, perc_wav.with_suffix(".state.json"))

    print("=== Percussion across all 5 rounds ===\n")
    history = [
        ("baseline", -27.0, 159),
        ("round1 mix_fix", -29.7, 115),
        ("round2 mix_fix", -34.2, 103),
        ("round3 mix_fix", -43.3, 159),
        ("round4 leaf_retry", -42.1, 439),
    ]
    for label, lufs, c in history:
        print(f"  {label}: LUFS {lufs:.1f}, centroid {c}Hz")
    p_lufs = perc_built["measured"]["lufs"]
    p_c = perc_built["measured"]["spectral_centroid"]["median"]
    lufs_str = f"{p_lufs:.1f}" if p_lufs is not None else "None (near-total silence)"
    print(f"  round5 leaf_retry (LIVE orchestrated): LUFS {lufs_str}, centroid {p_c:.0f}Hz, "
          f"sample_peak {perc_built['measured']['sample_peak']:.1f}dB\n")

    review, score = review_leaf(perc_node, perc_built, library)
    print(f"{PERC_ID} own-criteria: {review.status.value}"
          + (f" -- {'; '.join(review.reasons)}" if review.reasons else ""))
    print(f"  measured distance {score['measured']['distance']:.3f}\n")

    sibling_states = {KICK_ID: kick_built, PERC_ID: perc_built, BASS_ID: bass_built}
    combined_wav = ROOT / "state/leaf_proof/drop_backbone_combined_round5.wav"
    combined_built = state.build(project=PROJECT, wav=combined_wav, region=None,
                                  track={"DROP kick", "DROP percussion", "DROP bass"},
                                  embedding=False)
    state.write(combined_built, combined_wav.with_suffix(".state.json"))

    composition_review = review_composition(sibling_states, combined_state=combined_built)
    print(f"=== Backbone composition review, round 5 (live orchestrated) ===\n")
    print(f"backbone: {composition_review.status.value}"
          + (f" -- {'; '.join(composition_review.reasons)}"
             if composition_review.reasons else " -- BALANCED, first time across 5 rounds"))
    print(f"  combined LUFS: {combined_built['measured']['lufs']:.1f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
