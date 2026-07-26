"""Composition-level fixes (plan §3.6 gap, closed for real): review_composition
can detect that siblings clash (loudness gap, spectral overlap) but had no way
to act on it beyond re-emitting a leaf's content -- the wrong tool for a mixing
problem. A leaf can pick a different preset or note pattern; it can't apply
sidechain compression or EQ carving to itself and a neighbor, because that's
not a property of one leaf, it's a relationship between two.

This module is the mixing-decision half of that: given a failed
review_composition verdict and the siblings involved, a real Sonnet call (a
genuine mixing judgment -- which pair, which technique, why -- not mechanical
translation) proposes concrete fixes from two real REAPER tools: sidechain
compression (ducks target when trigger fires -- right for transient masking,
wrong if the parts barely overlap in time) and EQ notch (permanently carves a
band out of target -- right for parts that constantly occupy the same
register regardless of timing, wrong if it'd gut a part's core identity).
Deliberately does NOT hardcode "kick+bass always means sidechain" -- the real
backbone failure this was built against turned out to need EQ reasoning, not
the textbook sidechain instinct, because the actual overlapping pairs were
kick-percussion and percussion-bass, not kick-bass directly.

Only proposes; execution happens the same way every other op in this project
has -- the controlling MCP-capable session runs the resulting tool calls
against real REAPER tracks (track_fx_add_by_name/add_eq's return value has to
be read live to get the new FX's real index before the follow-up call, so
this can't be a blind ops list the way leaf emission's was).
"""
from __future__ import annotations

import json

from planner.node import Node, ReviewState

MODEL = "claude-sonnet-5"  # a mixing judgment, not mechanical translation -- plan §6

MIX_FIX_TOOL = {
    "name": "propose_fixes",
    "description": (
        "Propose 1-3 concrete mixing fixes for a failed composition review "
        "among sibling leaves."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "fixes": {
                "type": "array",
                "minItems": 1,
                "maxItems": 3,
                "items": {
                    "type": "object",
                    "properties": {
                        "type": {
                            "type": "string",
                            "enum": ["sidechain", "eq_cut"],
                            "description": (
                                "sidechain: ducks target's level whenever trigger "
                                "actually plays -- right when the two parts mostly "
                                "don't overlap in time and the problem is transient "
                                "masking. eq_cut: permanently cuts a frequency band "
                                "on target -- right when the two parts constantly "
                                "occupy the same register regardless of timing."
                            ),
                        },
                        "rationale": {
                            "type": "string",
                            "description": "why this fixes the specific reported problem",
                        },
                        "trigger_node_id": {
                            "type": "string",
                            "description": "sidechain only: whose hits duck the target",
                        },
                        "target_node_id": {
                            "type": "string",
                            "description": "the node being ducked (sidechain) or EQ'd (eq_cut)",
                        },
                        "send_volume_db": {
                            "type": "number",
                            "description": "sidechain only: how hard the ducking hits, e.g. 0 to -6",
                        },
                        "freq_hz": {
                            "type": "number",
                            "description": "eq_cut only: center frequency to cut",
                        },
                        "gain_db": {
                            "type": "number",
                            "description": "eq_cut only: negative gain, e.g. -4",
                        },
                        "q": {
                            "type": "number",
                            "description": "eq_cut only: bandwidth, e.g. 1.5 (narrower = more surgical)",
                        },
                    },
                    "required": ["type", "rationale", "target_node_id"],
                },
            },
        },
        "required": ["fixes"],
    },
}


def _validate(fixes, valid_node_ids: set[str]) -> list[dict]:
    # Same double-encoding quirk decompose.py hit and documented: the tool
    # input's array field sometimes comes back as a whole well-formed JSON
    # string instead of a real array. Recover it rather than discard
    # genuinely good content.
    if isinstance(fixes, str):
        try:
            parsed = json.loads(fixes)
            fixes = parsed.get("fixes", parsed) if isinstance(parsed, dict) else parsed
        except json.JSONDecodeError:
            pass
    if not isinstance(fixes, list) or not (1 <= len(fixes) <= 3):
        raise ValueError(f"expected 1-3 fixes, got {fixes!r}")
    for f in fixes:
        if f.get("target_node_id") not in valid_node_ids:
            raise ValueError(f"unknown target_node_id {f.get('target_node_id')!r}")
        if f["type"] == "sidechain" and f.get("trigger_node_id") not in valid_node_ids:
            raise ValueError(f"unknown trigger_node_id {f.get('trigger_node_id')!r}")
        if f["type"] == "eq_cut" and f.get("freq_hz") is None:
            raise ValueError(f"eq_cut fix missing freq_hz: {f!r}")
    return fixes


def propose_composition_fix(parent: Node, composition_review: ReviewState,
                             sibling_info: dict[str, dict], client, retries: int = 2) -> list[dict]:
    """sibling_info: {node_id: {"own_purpose": str, "track_index": int,
    "lufs": float, "centroid_hz": float}} for every sibling review_composition
    was run against. Returns the model's proposed fixes list (validated node
    ids only) -- the caller resolves node_id -> real track_index and executes."""
    prompt = f"""A composition review failed for {parent.node_id}'s children. \
This is a genuine mixing problem, not something re-picking a preset or note \
pattern on one leaf alone can fix -- you're deciding how these SPECIFIC \
siblings should relate to each other.

own_purpose: {parent.own_purpose}

Composition review failure reasons (verbatim, from real measurements):
{json.dumps(list(composition_review.reasons), indent=2)}

Siblings involved:
{json.dumps(sibling_info, indent=2)}

Propose 1-3 concrete fixes. Don't default to sidechain just because this is \
a rhythm section -- read the actual reported problem (which pairs, loudness \
vs. spectral) and pick sidechain only where transient masking is really the \
issue, eq_cut where constant register crowding is the issue. A fix must \
target one of the sibling node_ids given above."""

    valid_ids = set(sibling_info)
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        response = client.messages.create(
            model=MODEL,
            max_tokens=2048,
            tools=[MIX_FIX_TOOL],
            tool_choice={"type": "tool", "name": "propose_fixes"},
            messages=[{"role": "user", "content": prompt}],
        )
        block = next(b for b in response.content if b.type == "tool_use")
        try:
            return _validate(block.input.get("fixes"), valid_ids)
        except (TypeError, ValueError) as e:
            last_error = e
    raise RuntimeError(
        f"propose_composition_fix produced an invalid result {retries + 1} times "
        f"in a row: {last_error}"
    )
