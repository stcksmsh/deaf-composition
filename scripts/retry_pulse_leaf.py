#!/usr/bin/env python3
"""
The first real escalation/retry cycle (plan §7.4), run against a concrete,
already-known failure rather than a synthetic one: build_section_review.py
found the "build" section's rhythmic-pulse leaf rendering at -52.1 LUFS,
essentially inaudible -- it paired a Pads preset (slow attack/release)
with short staccato triggers, a preset/technique mismatch a pad envelope
structurally can't produce useful output for.

This script re-emits that same leaf's implementation, feeding the actual
failure reasons back to Haiku via leaf_emit.py's new `feedback` param
(escalation.feedback_for_retry), and against a broadened preset catalog
(leaf_emit.py now offers every factory category, not just Pads -- the
retry has nowhere to go if the only options on offer are all slow-attack).
Prints escalation.decide()'s verdict either way: pass, retry again, or
escalate with a full payload.

Only emits + decides; execution of whatever comes back still happens the
same way it always has -- the controlling MCP-capable session running the
ops verbatim (see leaf_emit.py's own docstring for why).

Run:
    set -a; source .env; set +a
    .venv/bin/python scripts/retry_pulse_leaf.py
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

PREVIOUS_REVIEW_PATH = ROOT / "state/leaf_proof/build_section_review.result.json"
LEAF_ID = "proof/section_build/leaf_0"


def main() -> int:
    prior = json.loads(PREVIOUS_REVIEW_PATH.read_text())
    node = Node.from_dict(prior["children"][LEAF_ID])
    prior_review = node.review_state  # Node.from_dict already reconstructs a real ReviewState

    decision = escalation.decide(node, prior_review, attempt=1)
    print(f"attempt 1 review: {prior_review.status.value} -- {'; '.join(prior_review.reasons)}")
    print(f"escalation decision: {decision.action} ({decision.reason})\n")

    if decision.action != "retry":
        print("not retrying -- nothing to emit")
        return 0

    feedback = escalation.feedback_for_retry(prior_review)
    print(f"feedback fed to re-emission:\n  {feedback}\n")

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    implementation = emit_leaf_implementation(node, client, feedback=feedback)

    print("=== attempt 2 emitted plan ===")
    print(json.dumps(implementation, indent=2))

    out_path = ROOT / "state/leaf_proof/build_leaf_0_retry_plan.json"
    out_path.write_text(json.dumps({
        "node": node.to_dict(),
        "prior_review": {"status": prior_review.status.value, "reasons": list(prior_review.reasons)},
        "feedback_given": feedback,
        "implementation": implementation,
    }, indent=2, sort_keys=True) + "\n")
    print(f"\nplan written: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
