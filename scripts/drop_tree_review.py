#!/usr/bin/env python3
"""
Two-level fold review for the real recursive drop-section tree
build_tree_proof.py planned and the controlling session executed live
(see memory.md for the exact sequence). Every leaf gets review_leaf();
the composite "rhythmic backbone" child gets its own review_composition
among its 3 children; the root gets review_composition among its 4
top-level children -- using the backbone's own combined-mix state as its
representative "sound" in that top-level check, since a Split node's
measured audio, for review purposes, is its own children's combined
render (not something a Split node has on its own).

Run:
    RETURN_CHANNEL_CLAP_CHECKPOINT=experiments/exp1/music_audioset_epoch_15_esc_90.14.pt \
        .venv/bin/python scripts/drop_tree_review.py
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

LEAF_TRACKS = {
    "proof/section_drop/child_0/child_0": ("DROP kick", "drop_leaf_0_kick.wav"),
    "proof/section_drop/child_0/child_1": ("DROP percussion", "drop_leaf_1_perc.wav"),
    "proof/section_drop/child_0/child_2": ("DROP bass", "drop_leaf_2_bass.wav"),
    "proof/section_drop/child_1": ("DROP lead", "drop_leaf_3_lead.wav"),
    "proof/section_drop/child_2": ("DROP pad", "drop_leaf_4_pad.wav"),
    "proof/section_drop/child_3": ("DROP noise", "drop_leaf_5_noise.wav"),
}
BACKBONE_TRACKS = {"DROP kick", "DROP percussion", "DROP bass"}
ALL_TRACKS = BACKBONE_TRACKS | {"DROP lead", "DROP pad", "DROP noise"}


def build_and_review_leaf(node_id: str, node_by_id: dict, library: dict) -> dict:
    node = node_by_id[node_id]
    track_name, wav_name = LEAF_TRACKS[node_id]
    wav = ROOT / "state/leaf_proof" / wav_name
    built = state.build(project=PROJECT, wav=wav, region=None, track=track_name, embedding=True)
    state.write(built, wav.with_suffix(".state.json"))
    review, score = review_leaf(node, built, library)
    node.review_state = review
    print(f"{node_id} ({track_name}): {review.status.value}"
          + (f" -- {'; '.join(review.reasons)}" if review.reasons else ""))
    def _fmt(x, unit="", precision=3):
        return f"{x:.{precision}f}{unit}" if x is not None else "None"

    lufs = built["measured"]["lufs"]
    centroid = built["measured"]["spectral_centroid"]["median"]
    print(f"  measured distance {_fmt(score['measured']['distance'])}, "
          f"embedding distance {_fmt(score['embedding']['distance'])}, "
          f"LUFS {_fmt(lufs, precision=1)}, "
          f"centroid {_fmt(centroid, 'Hz', 0)}")
    if lufs is None:
        print(f"  warnings: {built['measured'].get('warnings')} -- essentially "
              f"silent output (sample_peak {built['measured']['sample_peak']:.1f}dB)")
    print()
    return built


def main() -> int:
    plan = json.loads(PLAN.read_text())
    node_by_id = {node_id: Node.from_dict(n) for node_id, n in plan["nodes"].items()}
    node_by_id[plan["root"]["node_id"]] = Node.from_dict(plan["root"])
    root = node_by_id["proof/section_drop"]
    backbone = node_by_id["proof/section_drop/child_0"]

    library = reference.load_library(LIBRARY)

    print("=== Leaf reviews ===\n")
    leaf_states = {node_id: build_and_review_leaf(node_id, node_by_id, library)
                   for node_id in LEAF_TRACKS}

    print("=== Backbone (kick+percussion+bass) composition review ===\n")
    backbone_children_ids = [c for c in backbone.body.children]
    backbone_sibling_states = {nid: leaf_states[nid] for nid in backbone_children_ids}

    backbone_combined_wav = ROOT / "state/leaf_proof/drop_backbone_combined.wav"
    backbone_combined = state.build(project=PROJECT, wav=backbone_combined_wav, region=None,
                                     track=BACKBONE_TRACKS, embedding=False)
    state.write(backbone_combined, backbone_combined_wav.with_suffix(".state.json"))

    backbone_review = review_composition(backbone_sibling_states, combined_state=backbone_combined)
    backbone.review_state = backbone_review
    print(f"{backbone.node_id}: {backbone_review.status.value}"
          + (f" -- {'; '.join(backbone_review.reasons)}" if backbone_review.reasons else " -- balanced"))
    print(f"  backbone combined LUFS: {backbone_combined['measured']['lufs']:.1f}\n")

    print("=== Root (whole drop section) composition review ===\n")
    # The backbone's own "sound," for the top-level composition check, is its
    # own combined-children render -- a Split node has no audio of its own.
    top_level_states = {
        backbone.node_id: backbone_combined,
        "proof/section_drop/child_1": leaf_states["proof/section_drop/child_1"],
        "proof/section_drop/child_2": leaf_states["proof/section_drop/child_2"],
        "proof/section_drop/child_3": leaf_states["proof/section_drop/child_3"],
    }
    drop_combined_wav = ROOT / "state/leaf_proof/section_drop_combined.wav"
    drop_combined = state.build(project=PROJECT, wav=drop_combined_wav, region=None,
                                 track=ALL_TRACKS, embedding=False)
    state.write(drop_combined, drop_combined_wav.with_suffix(".state.json"))

    root_review = review_composition(top_level_states, combined_state=drop_combined)
    root.review_state = root_review
    print(f"{root.node_id}: {root_review.status.value}"
          + (f" -- {'; '.join(root_review.reasons)}" if root_review.reasons else " -- balanced"))
    print(f"  whole-drop combined LUFS: {drop_combined['measured']['lufs']:.1f}")

    out_path = ROOT / "state/leaf_proof/drop_tree_review.result.json"
    out_path.write_text(json.dumps(
        {nid: n.to_dict() for nid, n in node_by_id.items()},
        indent=2, sort_keys=True) + "\n")
    print(f"\nresult written: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
