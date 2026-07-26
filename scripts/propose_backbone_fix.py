#!/usr/bin/env python3
"""
Real composition-level fix proposal, run against the actual backbone
failure from build_tree_proof.py/drop_tree_review.py: kick+percussion
12.6dB apart and spectrally overlapping, percussion+bass also spectrally
overlapping. Only proposes -- see mix_fix.py's own docstring for why
execution happens live in the controlling session afterward.

Run:
    set -a; source .env; set +a
    .venv/bin/python scripts/propose_backbone_fix.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import anthropic

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from planner.mix_fix import propose_composition_fix  # noqa: E402
from planner.node import Node, ReviewState, ReviewStatus  # noqa: E402

RESULT = ROOT / "state/leaf_proof/drop_tree_review.result.json"

TRACK_INDEX = {
    "proof/section_drop/child_0/child_0": 6,  # kick
    "proof/section_drop/child_0/child_1": 7,  # percussion
    "proof/section_drop/child_0/child_2": 8,  # bass
}


def main() -> int:
    all_nodes = json.loads(RESULT.read_text())
    backbone = Node.from_dict(all_nodes["proof/section_drop/child_0"])
    composition_review = backbone.review_state
    assert composition_review.status == ReviewStatus.FAILED

    sibling_info = {}
    for node_id in backbone.body.children:
        n = Node.from_dict(all_nodes[node_id])
        # measured stats were only in the review script's own state.json files,
        # not on the Node itself -- pull straight from those.
        wav_stub = {
            "proof/section_drop/child_0/child_0": "drop_leaf_0_kick",
            "proof/section_drop/child_0/child_1": "drop_leaf_1_perc",
            "proof/section_drop/child_0/child_2": "drop_leaf_2_bass",
        }[node_id]
        measured = json.loads(
            (ROOT / f"state/leaf_proof/{wav_stub}.state.json").read_text()
        )["measured"]
        sibling_info[node_id] = {
            "own_purpose": n.own_purpose,
            "track_index": TRACK_INDEX[node_id],
            "lufs": measured["lufs"],
            "centroid_hz": measured["spectral_centroid"]["median"],
        }

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    fixes = propose_composition_fix(backbone, composition_review, sibling_info, client)

    print(json.dumps(fixes, indent=2))
    out_path = ROOT / "state/leaf_proof/backbone_fix_proposal.json"
    out_path.write_text(json.dumps({
        "sibling_info": sibling_info,
        "fixes": fixes,
    }, indent=2, sort_keys=True) + "\n")
    print(f"\nplan written: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
