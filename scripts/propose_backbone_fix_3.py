#!/usr/bin/env python3
"""
Pass 3: same still-failing percussion<->bass overlap (ratio 1.08 after
pass 2 made it worse, not better), but now mix_fix.py's tool vocabulary
includes highpass -- structurally guaranteed to shift a centroid upward,
unlike eq_cut's notch (which backfired twice: pass 1 moved percussion's
centroid down onto bass, pass 2's attempt to fix that moved it down
further). Real test of whether the added tool actually resolves what two
notch-based passes couldn't.

Run:
    set -a; source .env; set +a
    .venv/bin/python scripts/propose_backbone_fix_3.py
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
PRIOR_FIX_1 = ROOT / "state/leaf_proof/backbone_fix_proposal.json"
PRIOR_FIX_2 = ROOT / "state/leaf_proof/backbone_fix_proposal_2.json"

KICK_ID = "proof/section_drop/child_0/child_0"
PERC_ID = "proof/section_drop/child_0/child_1"
BASS_ID = "proof/section_drop/child_0/child_2"


def main() -> int:
    plan = json.loads(PLAN.read_text())
    backbone = Node.from_dict(plan["nodes"]["proof/section_drop/child_0"])
    prior_1 = json.loads(PRIOR_FIX_1.read_text())["fixes"]
    prior_2 = json.loads(PRIOR_FIX_2.read_text())["fixes"]

    composition_review = ReviewState(
        status=ReviewStatus.FAILED,
        reasons=(
            f"{PERC_ID} (103Hz) and {BASS_ID} (111Hz) spectral centroids are "
            "within half an octave (ratio 1.08) -- risk of competing for the "
            "same register. NOTE: this is WORSE than before pass 2 (was ratio "
            "1.03->1.08 is actually a tiny improvement in ratio, but percussion's "
            "centroid moved in the WRONG direction, from 115Hz to 103Hz, further "
            "past bass's 111Hz rather than away from it, and percussion also got "
            "5dB quieter as an unplanned side effect).",
        ),
        composes_with_siblings=False,
    )

    sibling_info = {
        KICK_ID: {"own_purpose": Node.from_dict(plan["nodes"][KICK_ID]).own_purpose,
                  "track_index": 6, "lufs": -39.6, "centroid_hz": 230},
        PERC_ID: {"own_purpose": Node.from_dict(plan["nodes"][PERC_ID]).own_purpose,
                  "track_index": 7, "lufs": -34.2, "centroid_hz": 103},
        BASS_ID: {"own_purpose": Node.from_dict(plan["nodes"][BASS_ID]).own_purpose,
                  "track_index": 8, "lufs": -29.0, "centroid_hz": 111},
    }

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    fixes = propose_composition_fix(
        backbone, composition_review, sibling_info, client,
        prior_fixes=prior_1 + prior_2,
    )

    print(json.dumps(fixes, indent=2))
    out_path = ROOT / "state/leaf_proof/backbone_fix_proposal_3.json"
    out_path.write_text(json.dumps({
        "sibling_info": sibling_info,
        "prior_fixes": prior_1 + prior_2,
        "fixes": fixes,
    }, indent=2, sort_keys=True) + "\n")
    print(f"\nplan written: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
