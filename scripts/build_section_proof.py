#!/usr/bin/env python3
"""
The real decompose -> emit chain (plan §11 stage 4's actual unstarted
core), run for real: one root Split node's own children -- how many
layers, what each one's job is -- decided by a real Sonnet call
(src/planner/decompose.py), not hand-picked by a human like
fold_proof.py's pad+bells pair was. Each child's Leaf.implementation then
comes from a real Haiku call (leaf_emit.py's emit_leaf_implementation,
reused as-is).

Targets a "build" section this time (fold_proof.py already covered
"intro") -- partly to get a genuinely different structural answer out of
decompose, not a rerun of the same split.

This script only plans -- see src/planner/scheduler.py's docstring for
why execution against real REAPER happens in the controlling MCP-capable
session afterward, reading this script's output plan and running each
child's ops verbatim through the real reaper MCP tools, then folding
results with src/planner/review.py (same pattern as leaf_emit.py before
it).

Run:
    set -a; source .env; set +a
    .venv/bin/python scripts/build_section_proof.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import anthropic

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from planner.node import AcceptanceCriteria, Node, ScopeLink, Split  # noqa: E402
from planner.scheduler import build_section  # noqa: E402

DURATION_S = 16.0
TRACK_START_INDEX = 2  # tracks 0-1 already used by fold_proof.py's intro pair


def build_root() -> Node:
    return Node(
        node_id="proof/section_build",
        own_purpose=(
            "The album's build section: rising energy leading into a drop, "
            "following directly after the sparse intro."
        ),
        spec=(
            f"A {DURATION_S:.0f}-second build section (120bpm, 4/4) -- energy "
            "should be clearly rising by its end, denser and more rhythmic than "
            "the preceding sparse intro, without arriving at full drop-level "
            "intensity yet. Decide how many independent Surge XT layers this "
            "needs and what each contributes to that rise."
        ),
        acceptance_criteria=AcceptanceCriteria(structural_facts={}),
        scope_chain=(
            ScopeLink(level="album", summary="A deaf-composed machine-music record."),
            ScopeLink(level="song", summary="Opening track: sparse intro, rising build, drop."),
        ),
        body=Split(children=()),
    )


def main() -> int:
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    root = build_root()

    children = build_section(
        root, decompose_client=client, emit_client=client,
        target_section_type="build", duration_s=DURATION_S,
        track_start_index=TRACK_START_INDEX,
    )

    print(f"=== {root.node_id} decomposed into {len(children)} children ===\n")
    for child in children:
        print(f"{child.node_id} (track_index={child.body.implementation['track_index']}):")
        print(f"  own_purpose: {child.own_purpose}")
        print(f"  spec: {child.spec}")
        print(f"  ops: {json.dumps(child.body.implementation['ops'])}\n")

    out = {
        "root": root.to_dict(),
        "children": {c.node_id: c.to_dict() for c in children},
    }
    out_path = ROOT / "state/leaf_proof/build_section_plan.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
    print(f"plan written: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
