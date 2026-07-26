#!/usr/bin/env python3
"""
Second pass of the composition-fix loop -- the real convergence test.
Pass 1 (propose_backbone_fix.py) resolved the original kick<->percussion
overlap but relocated percussion's centroid onto bass's, creating a new
overlap (115Hz vs 111Hz, ratio 1.03 -- worse than either original pair).
This asks propose_composition_fix again, with the current (post-fix)
measured values and the prior fixes as context, to see whether it revises
sensibly or just stacks more processing.

Run:
    set -a; source .env; set +a
    .venv/bin/python scripts/propose_backbone_fix_2.py
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

PLAN = ROOT / "state/leaf_proof/drop_tree_plan.json"
PRIOR_FIX = ROOT / "state/leaf_proof/backbone_fix_proposal.json"

KICK_ID = "proof/section_drop/child_0/child_0"
PERC_ID = "proof/section_drop/child_0/child_1"
BASS_ID = "proof/section_drop/child_0/child_2"


def main() -> int:
    plan = json.loads(PLAN.read_text())
    backbone = Node.from_dict(plan["nodes"]["proof/section_drop/child_0"])
    prior = json.loads(PRIOR_FIX.read_text())

    composition_review = ReviewState(
        status=ReviewStatus.FAILED,
        reasons=(
            f"{PERC_ID} (115Hz) and {BASS_ID} (111Hz) spectral centroids are "
            "within half an octave (ratio 1.03) -- risk of competing for the "
            "same register",
        ),
        composes_with_siblings=False,
    )

    sibling_info = {
        KICK_ID: {"own_purpose": Node.from_dict(plan["nodes"][KICK_ID]).own_purpose,
                  "track_index": 6, "lufs": -39.6, "centroid_hz": 230},
        PERC_ID: {"own_purpose": Node.from_dict(plan["nodes"][PERC_ID]).own_purpose,
                  "track_index": 7, "lufs": -29.7, "centroid_hz": 115},
        BASS_ID: {"own_purpose": Node.from_dict(plan["nodes"][BASS_ID]).own_purpose,
                  "track_index": 8, "lufs": -29.0, "centroid_hz": 111},
    }

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    fixes = propose_composition_fix(
        backbone, composition_review, sibling_info, client,
        prior_fixes=prior["fixes"],
    )

    print(json.dumps(fixes, indent=2))
    out_path = ROOT / "state/leaf_proof/backbone_fix_proposal_2.json"
    out_path.write_text(json.dumps({
        "sibling_info": sibling_info,
        "prior_fixes": prior["fixes"],
        "fixes": fixes,
    }, indent=2, sort_keys=True) + "\n")
    print(f"\nplan written: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
