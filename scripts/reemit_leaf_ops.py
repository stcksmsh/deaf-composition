#!/usr/bin/env python3
"""One-off: re-emit a single leaf's implementation ops using the current
(automation-required) leaf_emit.py prompt, given its node_id in song_plan.json.
Prints the new ops as JSON; does not execute or mutate the plan file itself --
the controlling session applies them live and updates the plan separately,
same pattern as every other leaf built this project.

Usage: .venv/bin/python scripts/reemit_leaf_ops.py <node_id> <duration_s>
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import anthropic
from leaf_emit import emit_leaf_implementation
from planner.node import AcceptanceCriteria, Leaf, Node, ScopeLink

PLAN_PATH = ROOT / "state/song_plan/song_plan.json"


def load_node(node_id: str) -> Node:
    plan = json.loads(PLAN_PATH.read_text())
    for n in plan["nodes"]:
        if n["node_id"] == node_id:
            return Node(
                node_id=n["node_id"],
                own_purpose=n["own_purpose"],
                spec=n["spec"],
                acceptance_criteria=AcceptanceCriteria.from_dict(n["acceptance_criteria"]),
                scope_chain=tuple(ScopeLink(**s) for s in n["scope_chain"]),
                body=Leaf(implementation=n["body"]["implementation"]),
            )
    raise KeyError(node_id)


def main() -> int:
    node_id = sys.argv[1]
    duration_s = float(sys.argv[2])
    node = load_node(node_id)
    client = anthropic.Anthropic()
    result = emit_leaf_implementation(node, client, duration_s=duration_s)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
