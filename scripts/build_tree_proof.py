#!/usr/bin/env python3
"""
The first real multi-level recursion (plan §11 stage 4): build_tree()
recurses for real when decompose() marks a child is_leaf=false, instead
of build_section_proof.py's single level (its decompose() prompt forced
every child to be leaf-sized, so nothing ever needed a second pass).

Targets a "drop" section this time -- the album's most energy-dense
section, and deliberately the best candidate for producing a genuinely
composite child (e.g. "the rhythm section" needing its own percussion +
bass split) rather than a rerun of "intro"/"build"'s already-simple
splits.

Plans only -- see scheduler.py's own docstring for why execution happens
in the controlling MCP-capable session afterward, same pattern as every
other proof script this session.

Run:
    set -a; source .env; set +a
    .venv/bin/python scripts/build_tree_proof.py
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
from planner.scheduler import build_tree  # noqa: E402

DURATION_S = 16.0
TRACK_START_INDEX = 6  # tracks 0-5 already used by the intro/build sections
MAX_DEPTH = 3


def build_root() -> Node:
    return Node(
        node_id="proof/section_drop",
        own_purpose=(
            "The album's drop section: full-energy arrival right after the "
            "build, the most saturated and dense part of the track."
        ),
        spec=(
            f"A {DURATION_S:.0f}-second drop section (120bpm, 4/4) -- maximum "
            "energy and density, the payoff the build has been leading toward. "
            "Decide the full structure needed: how many parts, whether any of "
            "them are themselves composite (e.g. a rhythm section combining "
            "multiple interacting instruments) rather than a single sound-"
            "design choice."
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

    leaves, all_nodes = build_tree(
        root, decompose_client=client, emit_client=client,
        target_section_type="drop", duration_s=DURATION_S,
        track_counter=TRACK_START_INDEX, max_depth=MAX_DEPTH,
    )

    print(f"=== {root.node_id}: {len(all_nodes)} total nodes, {len(leaves)} leaves ===\n")

    def describe(node_id: str, node_by_id: dict, indent: int = 0):
        n = node_by_id[node_id]
        kind = "leaf" if n.is_leaf else "split"
        print(f"{'  ' * indent}{node_id} [{kind}]: {n.own_purpose}")
        if n.is_leaf:
            print(f"{'  ' * indent}  track_index={n.body.implementation['track_index']}, "
                  f"preset={n.body.implementation['ops'][0]['args']['preset_path']}")
        else:
            for child_id in n.body.children:
                describe(child_id, node_by_id, indent + 1)

    node_by_id = {root.node_id: root, **{n.node_id: n for n in all_nodes}}
    describe(root.node_id, node_by_id)

    out = {
        "root": root.to_dict(),
        "nodes": {n.node_id: n.to_dict() for n in all_nodes},
    }
    out_path = ROOT / "state/leaf_proof/drop_tree_plan.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
    print(f"\nplan written: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
