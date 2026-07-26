#!/usr/bin/env python3
"""
Verifies the leaf-level re-emission of percussion (Percussion/Verber.fxp,
higher-register notes) against the same backbone composition check that
3 mix-fix passes couldn't resolve. Real test of whether routing back to
leaf-level re-emission (escalation.py's mechanism) succeeds where
mix-level surgery didn't.

Run:
    RETURN_CHANNEL_CLAP_CHECKPOINT=experiments/exp1/music_audioset_epoch_15_esc_90.14.pt \
        .venv/bin/python scripts/backbone_reemit_review.py
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

    perc_wav = ROOT / "state/leaf_proof/drop_leaf_1_perc_reemit.wav"
    perc_built = state.build(project=PROJECT, wav=perc_wav, region=None,
                              track="DROP percussion", embedding=True)
    state.write(perc_built, perc_wav.with_suffix(".state.json"))

    # bass's own solo render hasn't changed since pass 3 (its EQ is neutral,
    # no fix touched it since) -- reuse that state.
    bass_built = json.loads((ROOT / "state/leaf_proof/drop_leaf_2_bass_fixed3.state.json").read_text())

    print("=== Percussion: before (original) vs re-emitted ===\n")
    print(f"original:  LUFS -27.0, centroid 159Hz (Plucks/Metallic.fxp, mid-range notes)")
    p_lufs = perc_built["measured"]["lufs"]
    p_c = perc_built["measured"]["spectral_centroid"]["median"]
    print(f"re-emit:   LUFS {p_lufs:.1f}, centroid {p_c:.0f}Hz "
          f"(Percussion/Verber.fxp, high notes)\n")

    review, score = review_leaf(perc_node, perc_built, library)
    print(f"{PERC_ID} own-criteria review: {review.status.value}"
          + (f" -- {'; '.join(review.reasons)}" if review.reasons else ""))
    print(f"  measured distance {score['measured']['distance']:.3f}, "
          f"embedding distance {score['embedding']['distance']:.3f}\n")

    sibling_states = {KICK_ID: kick_built, PERC_ID: perc_built, BASS_ID: bass_built}
    combined_wav = ROOT / "state/leaf_proof/drop_backbone_combined_reemit.wav"
    combined_built = state.build(project=PROJECT, wav=combined_wav, region=None,
                                  track={"DROP kick", "DROP percussion", "DROP bass"},
                                  embedding=False)
    state.write(combined_built, combined_wav.with_suffix(".state.json"))

    composition_review = review_composition(sibling_states, combined_state=combined_built)
    print(f"=== Backbone composition review, after leaf re-emission ===\n")
    print(f"backbone: {composition_review.status.value}"
          + (f" -- {'; '.join(composition_review.reasons)}"
             if composition_review.reasons else " -- balanced"))
    print(f"  combined LUFS: {combined_built['measured']['lufs']:.1f} "
          f"(original: -24.3, after 3 mix-fix passes: -28.5)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
