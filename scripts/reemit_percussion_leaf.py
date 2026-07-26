#!/usr/bin/env python3
"""
Routes the backbone's still-failing spectral overlap back to leaf-level
re-emission instead of a 4th mix-fix pass -- three real mix-fix passes
(sidechain, EQ notch x2, highpass) either relocated the problem or gutted
the sound trying to fix it (see memory.md). The evidence points at the
original preset choice (Plucks/Metallic.fxp) itself being wrong: its
natural register genuinely conflicts with its neighbors, which no amount
of downstream processing can fix without destroying what made it audible.

Re-emits percussion's leaf via leaf_emit.py's existing feedback param
(same mechanism escalation.py already proved on the silent pulse leaf),
telling Haiku explicitly that mix-level fixes were tried and failed, and
why -- so it picks a genuinely different register from the start rather
than another Plucks/Percussion preset that might have the same problem.

Run:
    set -a; source .env; set +a
    .venv/bin/python scripts/reemit_percussion_leaf.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import anthropic

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from leaf_emit import emit_leaf_implementation  # noqa: E402

from planner.node import Node  # noqa: E402

PLAN = ROOT / "state/leaf_proof/drop_tree_plan.json"
PERC_ID = "proof/section_drop/child_0/child_1"

FEEDBACK = (
    "Your previous choice for this leaf was Plucks/Metallic.fxp, played as a "
    "syncopated pattern. That rendered with a spectral centroid around 159Hz -- "
    "which put it in direct, unresolvable conflict with its neighbors in this "
    "same rhythmic backbone: a kick drum around 230Hz and a bass around 111Hz. "
    "Three real mix-level fixes were tried against this exact conflict "
    "(sidechain ducking, an EQ notch, a second EQ notch, and finally a "
    "highpass filter) -- none resolved it without either relocating the "
    "problem elsewhere or removing so much of the preset's actual energy "
    "that it became nearly inaudible (the highpass cut the level by 9dB). "
    "The preset's own natural register is the actual problem, not something "
    "downstream processing can fix. Pick a genuinely different preset this "
    "time -- one whose natural spectral character sits clearly in the "
    "higher-frequency/transient range (think hi-hats, shakers, clicks, "
    "metallic ticks with most of their energy above 500Hz), not another "
    "low-mid-heavy percussion or pluck sound, so it doesn't compete with the "
    "kick or bass at all rather than needing to be mixed around them."
)


def main() -> int:
    plan = json.loads(PLAN.read_text())
    node = Node.from_dict(plan["nodes"][PERC_ID])

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    implementation = emit_leaf_implementation(node, client, feedback=FEEDBACK)

    print(json.dumps(implementation, indent=2))
    out_path = ROOT / "state/leaf_proof/percussion_reemit_plan.json"
    out_path.write_text(json.dumps({
        "feedback_given": FEEDBACK,
        "implementation": implementation,
    }, indent=2, sort_keys=True) + "\n")
    print(f"\nplan written: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
