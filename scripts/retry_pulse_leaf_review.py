#!/usr/bin/env python3
"""
Second half of the escalation/retry cycle scripts/retry_pulse_leaf.py
started: review the retried pulse leaf (Plucks/Snap.fxp, steady 8th-note
pattern, executed live -- see memory.md) against the same acceptance
criteria as attempt 1, and run escalation.decide() again at attempt=2 to
see whether it now passes, needs a third attempt, or escalates.

Run:
    RETURN_CHANNEL_CLAP_CHECKPOINT=experiments/exp1/music_audioset_epoch_15_esc_90.14.pt \
        .venv/bin/python scripts/retry_pulse_leaf_review.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from planner import escalation  # noqa: E402
from planner.node import Node  # noqa: E402
from planner.review import review_leaf  # noqa: E402
from return_channel import reference, state  # noqa: E402

LIBRARY = ROOT / "reference_library.json"
PROJECT = ROOT / "state/scratch/session.rpp"
RETRY_PLAN = ROOT / "state/leaf_proof/build_leaf_0_retry_plan.json"
WAV = ROOT / "state/leaf_proof/build_leaf_0_pulse_retry.wav"
TRACK_NAME = "BUILD rhythmic pulse"


def main() -> int:
    plan = json.loads(RETRY_PLAN.read_text())
    node = Node.from_dict(plan["node"])
    node.body.implementation.update(plan["implementation"])

    library = reference.load_library(LIBRARY)
    built = state.build(project=PROJECT, wav=WAV, region=None,
                         track=TRACK_NAME, embedding=True)
    state.write(built, WAV.with_suffix(".state.json"))

    review, score = review_leaf(node, built, library)
    node.review_state = review
    print(f"{node.node_id} retry review: {review.status.value}"
          + (f" -- {'; '.join(review.reasons)}" if review.reasons else ""))
    print(f"  measured distance {score['measured']['distance']:.3f}, "
          f"embedding distance {score['embedding']['distance']:.3f}, "
          f"LUFS {built['measured']['lufs']:.1f}")
    print(f"  (attempt 1 was: measured distance 19.876, LUFS -52.1)\n")

    decision = escalation.decide(node, review, attempt=2, score=score, wav_path=str(WAV))
    print(f"escalation decision (attempt 2): {decision.action} ({decision.reason})")
    if decision.payload:
        print(f"\nescalation payload (what would surface to the human):")
        print(json.dumps(decision.payload, indent=2))

    out_path = ROOT / "state/leaf_proof/build_leaf_0_retry_review.result.json"
    out_path.write_text(json.dumps({
        "node": node.to_dict(),
        "decision": {"action": decision.action, "reason": decision.reason,
                      "payload": decision.payload},
    }, indent=2, sort_keys=True) + "\n")
    print(f"\nresult written: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
