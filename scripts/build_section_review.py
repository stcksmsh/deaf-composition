#!/usr/bin/env python3
"""
Closes the loop build_section_proof.py's plan started: execute (done live
in the controlling session -- see memory.md for the exact sequence, plus
two real leaf-emission mistakes hit and handled: the model twice invented
a plausible-but-nonexistent Surge override param name, apply_surge_preset
correctly raised loudly both times, and the executor retried without the
invalid override rather than guessing a fix), then review each leaf and
fold a composition verdict onto the root -- the same review.py functions
fold_proof.py already proved, run this time against a real model-decided
4-leaf split instead of a hand-picked pair.

Run:
    RETURN_CHANNEL_CLAP_CHECKPOINT=experiments/exp1/music_audioset_epoch_15_esc_90.14.pt \
        .venv/bin/python scripts/build_section_review.py
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
PLAN = ROOT / "state/leaf_proof/build_section_plan.json"

TRACK_NAMES = {
    "proof/section_build/leaf_0": "BUILD rhythmic pulse",
    "proof/section_build/leaf_1": "BUILD bass",
    "proof/section_build/leaf_2": "BUILD texture",
    "proof/section_build/leaf_3": "BUILD lead",
}
WAV_NAMES = {
    "proof/section_build/leaf_0": "build_leaf_0_pulse.wav",
    "proof/section_build/leaf_1": "build_leaf_1_bass.wav",
    "proof/section_build/leaf_2": "build_leaf_2_texture.wav",
    "proof/section_build/leaf_3": "build_leaf_3_lead.wav",
}


def main() -> int:
    plan = json.loads(PLAN.read_text())
    root = Node.from_dict(plan["root"])
    children = [Node.from_dict(plan["children"][node_id]) for node_id in TRACK_NAMES]

    library = reference.load_library(LIBRARY)

    print(f"=== Reviewing children of {root.node_id} ===\n")
    results = {}
    for child in children:
        wav = ROOT / "state/leaf_proof" / WAV_NAMES[child.node_id]
        built = state.build(project=PROJECT, wav=wav, region=None,
                             track=TRACK_NAMES[child.node_id], embedding=True)
        state.write(built, wav.with_suffix(".state.json"))
        results[child.node_id] = built

        review, score = review_leaf(child, built, library)
        child.review_state = review
        print(f"{child.node_id} ({TRACK_NAMES[child.node_id]}): {review.status.value}"
              + (f" -- {'; '.join(review.reasons)}" if review.reasons else ""))
        print(f"  measured distance {score['measured']['distance']:.3f}, "
              f"embedding distance {score['embedding']['distance']:.3f}, "
              f"LUFS {built['measured']['lufs']:.1f}, "
              f"centroid {built['measured']['spectral_centroid']['median']:.0f}Hz\n")

    combined_wav = ROOT / "state/leaf_proof/section_build_combined.wav"
    combined_built = state.build(
        project=PROJECT, wav=combined_wav, region=None,
        track=set(TRACK_NAMES.values()), embedding=False,
    )
    state.write(combined_built, combined_wav.with_suffix(".state.json"))

    print(f"=== Reviewing composition at {root.node_id} ===\n")
    composition_review = review_composition(results, combined_state=combined_built)
    root.review_state = composition_review
    print(f"{root.node_id}: {composition_review.status.value}"
          + (f" -- {'; '.join(composition_review.reasons)}"
             if composition_review.reasons else " -- balanced"))
    print(f"  combined mix LUFS: {combined_built['measured']['lufs']:.1f}")

    out_path = ROOT / "state/leaf_proof/build_section_review.result.json"
    out_path.write_text(json.dumps({
        "root": root.to_dict(),
        "children": {c.node_id: c.to_dict() for c in children},
    }, indent=2, sort_keys=True) + "\n")
    print(f"\nresult written: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
