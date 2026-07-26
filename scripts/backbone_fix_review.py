#!/usr/bin/env python3
"""
Verifies the real composition-level fix applied to the drop section's
rhythmic backbone: sidechain (kick ducks percussion, -5dB) + EQ notch on
percussion (200Hz, -3.5dB) + EQ notch on bass (150Hz, -3dB) -- proposed
by mix_fix.propose_composition_fix, executed live in the controlling
session (see memory.md).

Honest about what these numbers can and can't show: the EQ cuts are
static processing, so they show up in percussion/bass's own solo
renders. The sidechain only engages when the kick is actually playing,
so its effect is only visible in the backbone's combined render -- and
even there, review_composition has no direct masking model (its own
docstring already flags this as future work), so "did ducking help
clarity" isn't something these specific checks can confirm either way,
only "did the reported loudness/register problems change."

Run:
    RETURN_CHANNEL_CLAP_CHECKPOINT=experiments/exp1/music_audioset_epoch_15_esc_90.14.pt \
        .venv/bin/python scripts/backbone_fix_review.py
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
    kick = Node.from_dict(plan["nodes"][KICK_ID])
    perc = Node.from_dict(plan["nodes"][PERC_ID])
    bass = Node.from_dict(plan["nodes"][BASS_ID])
    library = reference.load_library(LIBRARY)

    # kick untouched by any fix -- reuse its already-built state.
    kick_built = json.loads((ROOT / "state/leaf_proof/drop_leaf_0_kick.state.json").read_text())

    perc_wav = ROOT / "state/leaf_proof/drop_leaf_1_perc_fixed.wav"
    perc_built = state.build(project=PROJECT, wav=perc_wav, region=None,
                              track="DROP percussion", embedding=True)
    state.write(perc_built, perc_wav.with_suffix(".state.json"))

    bass_wav = ROOT / "state/leaf_proof/drop_leaf_2_bass_fixed.wav"
    bass_built = state.build(project=PROJECT, wav=bass_wav, region=None,
                              track="DROP bass", embedding=True)
    state.write(bass_built, bass_wav.with_suffix(".state.json"))

    print("=== Before vs after (solo renders) ===\n")
    before = {
        KICK_ID: (-39.6, 230),
        PERC_ID: (-27.0, 159),
        BASS_ID: (-27.8, 115),
    }
    for node_id, built in [(KICK_ID, kick_built), (PERC_ID, perc_built), (BASS_ID, bass_built)]:
        b_lufs, b_c = before[node_id]
        a_lufs = built["measured"]["lufs"]
        a_c = built["measured"]["spectral_centroid"]["median"]
        print(f"{node_id}: LUFS {b_lufs:.1f} -> {a_lufs:.1f}, "
              f"centroid {b_c:.0f}Hz -> {a_c:.0f}Hz")

    print("\n=== Re-reviewed leaves ===\n")
    sibling_states = {}
    for node_id, node, built in [(KICK_ID, kick, kick_built), (PERC_ID, perc, perc_built),
                                   (BASS_ID, bass, bass_built)]:
        review, score = review_leaf(node, built, library)
        sibling_states[node_id] = built
        print(f"{node_id}: {review.status.value}"
              + (f" -- {'; '.join(review.reasons)}" if review.reasons else ""))

    combined_wav = ROOT / "state/leaf_proof/drop_backbone_combined_fixed.wav"
    combined_built = state.build(project=PROJECT, wav=combined_wav, region=None,
                                  track={"DROP kick", "DROP percussion", "DROP bass"},
                                  embedding=False)
    state.write(combined_built, combined_wav.with_suffix(".state.json"))

    print("\n=== Composition review, after the fix ===\n")
    composition_review = review_composition(sibling_states, combined_state=combined_built)
    print(f"backbone: {composition_review.status.value}"
          + (f" -- {'; '.join(composition_review.reasons)}"
             if composition_review.reasons else " -- balanced"))
    print(f"  combined LUFS: {combined_built['measured']['lufs']:.1f} "
          f"(was -24.3 before the fix)")

    print("\nCaveat: review_composition has no direct model of masking/ducking "
          "clarity -- these numbers show whether the reported loudness-gap and "
          "register-overlap problems changed, not whether the sidechain actually "
          "makes the kick punch through audibly. That's a listen, not a metric, "
          "for now.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
