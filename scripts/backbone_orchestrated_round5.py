#!/usr/bin/env python3
"""
The first LIVE orchestration decision, not a replay: rebuilds the real
5-round review history from the actual persisted state.json files this
session produced (real audio measurements, not hand-typed reason
strings like orchestrate_validate.py used), calls choose_fix_strategy()
for real, and -- since it should say leaf_retry per the validated policy
-- dispatches to a real emit_leaf_implementation() call using
escalation.py's existing feedback_for_retry() rather than hand-written
feedback text (reemit_percussion_leaf.py wrote its own custom feedback;
this reuses the generic mechanism instead, since the orchestrator, not a
human, is choosing the target and framing now).

Only emits -- execution follows the same pattern as every other op in
this project (the controlling MCP session runs it for real afterward).

Run:
    set -a; source .env; set +a
    .venv/bin/python scripts/backbone_orchestrated_round5.py
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

from planner import escalation  # noqa: E402
from planner.node import Node  # noqa: E402
from planner.orchestrate import choose_fix_strategy  # noqa: E402
from planner.review import review_composition  # noqa: E402

LEAF_PROOF = ROOT / "state/leaf_proof"
PLAN = ROOT / "state/leaf_proof/drop_tree_plan.json"

KICK_ID = "proof/section_drop/child_0/child_0"
PERC_ID = "proof/section_drop/child_0/child_1"
BASS_ID = "proof/section_drop/child_0/child_2"

# (perc_state_file, bass_state_file, combined_state_file, strategy_used_to_produce_this_round)
ROUNDS = [
    ("drop_leaf_1_perc.state.json", "drop_leaf_2_bass.state.json",
     "drop_backbone_combined.state.json", None),
    ("drop_leaf_1_perc_fixed.state.json", "drop_leaf_2_bass_fixed.state.json",
     "drop_backbone_combined_fixed.state.json", "mix_fix"),
    ("drop_leaf_1_perc_fixed2.state.json", "drop_leaf_2_bass_fixed2.state.json",
     "drop_backbone_combined_fixed2.state.json", "mix_fix"),
    ("drop_leaf_1_perc_fixed3.state.json", "drop_leaf_2_bass_fixed3.state.json",
     "drop_backbone_combined_fixed3.state.json", "mix_fix"),
    ("drop_leaf_1_perc_reemit.state.json", "drop_leaf_2_bass_fixed3.state.json",
     "drop_backbone_combined_reemit.state.json", "leaf_retry"),
]


def load(name: str) -> dict:
    return json.loads((LEAF_PROOF / name).read_text())


def main() -> int:
    kick_built = load("drop_leaf_0_kick.state.json")

    review_history = []
    strategy_history = []
    for perc_file, bass_file, combined_file, strategy in ROUNDS:
        perc_built = load(perc_file)
        bass_built = load(bass_file)
        combined_built = load(combined_file)
        sibling_states = {KICK_ID: kick_built, PERC_ID: perc_built, BASS_ID: bass_built}
        review = review_composition(sibling_states, combined_state=combined_built)
        review_history.append(review)
        if strategy is not None:
            strategy_history.append(strategy)
        print(f"round (strategy={strategy}): {review.status.value}"
              + (f" -- {'; '.join(review.reasons)}" if review.reasons else " -- balanced"))

    print()
    decision = choose_fix_strategy(review_history, strategy_history)
    print(f"LIVE decision for round 5: {decision.action!r} -- {decision.reason}\n")

    if decision.action != "leaf_retry":
        print(f"policy says {decision.action!r}, not leaf_retry -- nothing to emit")
        return 0

    plan = json.loads(PLAN.read_text())
    node = Node.from_dict(plan["nodes"][PERC_ID])

    # The composition review's own reasons ARE the real problem report --
    # reuse escalation.py's generic feedback mechanism instead of writing
    # custom text, since the orchestrator (not a human) chose this target.
    feedback = escalation.feedback_for_retry(review_history[-1])
    print(f"feedback (via escalation.feedback_for_retry, composition review's own reasons):\n"
          f"  {feedback}\n")

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    implementation = emit_leaf_implementation(node, client, feedback=feedback)

    print("=== round 5 emitted plan ===")
    print(json.dumps(implementation, indent=2))

    out_path = LEAF_PROOF / "backbone_round5_plan.json"
    out_path.write_text(json.dumps({
        "decision": {"action": decision.action, "reason": decision.reason},
        "feedback_given": feedback,
        "implementation": implementation,
    }, indent=2, sort_keys=True) + "\n")
    print(f"\nplan written: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
