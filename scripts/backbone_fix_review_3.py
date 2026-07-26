#!/usr/bin/env python3
"""
Verifies pass 3: highpass on percussion (220Hz) instead of another notch,
plus reverting bass's now-unneeded EQ cut. Real test of whether the
diagnosis from pass 2's failure (notches don't reliably move a centroid;
highpass structurally does) actually holds up.

Run:
    RETURN_CHANNEL_CLAP_CHECKPOINT=experiments/exp1/music_audioset_epoch_15_esc_90.14.pt \
        .venv/bin/python scripts/backbone_fix_review_3.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from planner.review import review_composition  # noqa: E402
from return_channel import state  # noqa: E402

PROJECT = ROOT / "state/scratch/session.rpp"

KICK_ID = "proof/section_drop/child_0/child_0"
PERC_ID = "proof/section_drop/child_0/child_1"
BASS_ID = "proof/section_drop/child_0/child_2"


def main() -> int:
    kick_built = json.loads((ROOT / "state/leaf_proof/drop_leaf_0_kick.state.json").read_text())

    perc_wav = ROOT / "state/leaf_proof/drop_leaf_1_perc_fixed3.wav"
    perc_built = state.build(project=PROJECT, wav=perc_wav, region=None,
                              track="DROP percussion", embedding=False)
    state.write(perc_built, perc_wav.with_suffix(".state.json"))

    bass_wav = ROOT / "state/leaf_proof/drop_leaf_2_bass_fixed3.wav"
    bass_built = state.build(project=PROJECT, wav=bass_wav, region=None,
                              track="DROP bass", embedding=False)
    state.write(bass_built, bass_wav.with_suffix(".state.json"))

    print("=== Pass 2 -> pass 3 (solo renders) ===\n")
    pass2 = {PERC_ID: (-34.2, 103), BASS_ID: (-29.0, 111)}
    for node_id, built in [(PERC_ID, perc_built), (BASS_ID, bass_built)]:
        p2_lufs, p2_c = pass2[node_id]
        p3_lufs = built["measured"]["lufs"]
        p3_c = built["measured"]["spectral_centroid"]["median"]
        print(f"{node_id}: LUFS {p2_lufs:.1f} -> {p3_lufs:.1f}, "
              f"centroid {p2_c:.0f}Hz -> {p3_c:.0f}Hz")
    print(f"{KICK_ID}: unchanged (LUFS -39.6, centroid 230Hz)\n")

    sibling_states = {KICK_ID: kick_built, PERC_ID: perc_built, BASS_ID: bass_built}

    combined_wav = ROOT / "state/leaf_proof/drop_backbone_combined_fixed3.wav"
    combined_built = state.build(project=PROJECT, wav=combined_wav, region=None,
                                  track={"DROP kick", "DROP percussion", "DROP bass"},
                                  embedding=False)
    state.write(combined_built, combined_wav.with_suffix(".state.json"))

    review = review_composition(sibling_states, combined_state=combined_built)
    print(f"=== Backbone composition review, pass 3 ===\n")
    print(f"backbone: {review.status.value}"
          + (f" -- {'; '.join(review.reasons)}" if review.reasons else " -- balanced"))
    print(f"  combined LUFS: {combined_built['measured']['lufs']:.1f} "
          f"(pass 2: -27.6, pass 1: -26.0, original: -24.3)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
