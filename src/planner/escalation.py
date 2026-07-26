"""Escalation (plan §7.4) -- the piece that was missing after every review
this session: every FAIL so far just got printed and written to a result
JSON, nothing *acted* on it. Plan §7.4 names three triggers ("the fold
escalates when it can't self-resolve"): a node fails its own criteria N
times, two criteria conflict, or review confidence is low. This module
turns those triggers into a real decision -- retry (with the failure fed
back to the emission model) or escalate to the human -- not just a log
line.

What this does NOT do: decide *how* to fix a failure. Plan §7.4 is
explicit that escalation surfaces "the rendered stem + the measurements +
the specific conflict" and "the human rules or kicks it back" -- the
human is the taste oracle (plan §7.1), not this code. This module's job
ends at deciding retry-vs-escalate and building the payload; the retry
itself (re-emitting with feedback) lives in leaf_emit.py's
`feedback` parameter, and the actual re-execution happens the same way
every leaf's execution has all session: the controlling MCP-capable
session runs it.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from planner.node import Node, ReviewState

DEFAULT_MAX_ATTEMPTS = 2

# "review confidence is low" (plan §7.4's third trigger) -- a FAIL whose
# distance sits within this fraction of its own threshold read as a close
# call, not a clear miss, and gets escalated even on attempt 1 rather than
# silently retried into the same near-miss again. A FAIL blown well past
# the threshold is unambiguous and worth a normal retry first.
LOW_CONFIDENCE_MARGIN = 0.15


@dataclass(frozen=True)
class EscalationDecision:
    action: str  # "pass" | "retry" | "escalate"
    reason: str
    payload: dict | None = field(default=None)


def _is_low_confidence_fail(node: Node, score: dict) -> bool:
    """A FAIL is "low confidence" if it only barely crossed its threshold --
    close enough that measurement noise or a marginally different render
    could plausibly flip it. Checks both the measured and embedding
    distances against their own thresholds independently."""
    ac = node.acceptance_criteria
    measured = score.get("measured", {}).get("distance")
    embedding = score.get("embedding", {}).get("distance")

    if ac.max_measured_distance and measured is not None:
        over = (measured - ac.max_measured_distance) / ac.max_measured_distance
        if 0 < over <= LOW_CONFIDENCE_MARGIN:
            return True
    if ac.max_embedding_distance and embedding is not None:
        over = (embedding - ac.max_embedding_distance) / ac.max_embedding_distance
        if 0 < over <= LOW_CONFIDENCE_MARGIN:
            return True
    return False


def decide(node: Node, review: ReviewState, *, attempt: int,
           score: dict | None = None, max_attempts: int = DEFAULT_MAX_ATTEMPTS,
           wav_path: str | None = None) -> EscalationDecision:
    """The one real decision this module makes: given a node's review
    result and how many times it's already been attempted, pass, retry,
    or escalate."""
    if review.status.value == "passed":
        return EscalationDecision(action="pass", reason="meets its own acceptance criteria")

    if score is not None and _is_low_confidence_fail(node, score):
        return EscalationDecision(
            action="escalate",
            reason="low-confidence fail -- within 15% of threshold, not a clear miss",
            payload=build_payload(node, review, wav_path=wav_path),
        )

    if attempt < max_attempts:
        return EscalationDecision(
            action="retry",
            reason=f"attempt {attempt}/{max_attempts} failed: {'; '.join(review.reasons)}",
        )

    return EscalationDecision(
        action="escalate",
        reason=f"failed its own criteria {attempt} times in a row",
        payload=build_payload(node, review, wav_path=wav_path),
    )


def build_payload(node: Node, review: ReviewState, *, wav_path: str | None = None) -> dict:
    """plan §7.4: "surfaces the rendered stem + the measurements + the
    specific conflict." This is that payload -- everything a human needs
    to rule on it without re-deriving context."""
    return {
        "node_id": node.node_id,
        "own_purpose": node.own_purpose,
        "spec": node.spec,
        "wav_path": wav_path,
        "review_status": review.status.value,
        "reasons": list(review.reasons),
    }


def feedback_for_retry(review: ReviewState) -> str:
    """Turns a failed ReviewState into the natural-language note appended to
    the next emit_leaf_implementation() call (leaf_emit.py's `feedback`
    param) -- the actual mechanism of "retry," not just a decision to do
    so."""
    return (
        "Your previous attempt at this leaf failed review for these reasons: "
        + "; ".join(review.reasons)
        + ". Pick a different preset and/or note pattern that avoids this -- "
        "do not repeat the same choice."
    )
