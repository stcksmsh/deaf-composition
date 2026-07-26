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
                            "enum": ["sidechain", "eq_cut", "highpass"],
                            "description": (
                                "sidechain: ducks target's level whenever trigger "
                                "actually plays -- right when the two parts mostly "
                                "don't overlap in time and the problem is transient "
                                "masking. eq_cut: a narrow notch at one frequency on "
                                "target -- CAUTION: cutting energy at a signal's own "
                                "spectral centroid does NOT reliably push that "
                                "centroid away from the cut; it redistributes the "
                                "remaining energy, which can land on either side "
                                "unpredictably (confirmed empirically: this backfired "
                                "on this exact backbone once already). highpass: "
                                "removes ALL content below cutoff_hz -- unlike eq_cut, "
                                "this is structurally guaranteed to shift the "
                                "remaining signal's centroid upward (only lower "
                                "content is removed, nothing shifts down), the right "
                                "choice when a signal needs to vacate a low register "
                                "entirely for a neighbor rather than avoid one "
                                "specific frequency within it."
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
                            "description": "the node being ducked/EQ'd/highpassed",
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
                            "description": (
                                "eq_cut/highpass: bandwidth or slope steepness, "
                                "e.g. 1.5 (narrower/steeper = more surgical)"
                            ),
                        },
                        "cutoff_hz": {
                            "type": "number",
                            "description": "highpass only: frequency below which content is removed",
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
        if f["type"] == "highpass" and f.get("cutoff_hz") is None:
            raise ValueError(f"highpass fix missing cutoff_hz: {f!r}")
    return fixes


def propose_composition_fix(parent: Node, composition_review: ReviewState,
                             sibling_info: dict[str, dict], client, retries: int = 2,
                             prior_fixes: list[dict] | None = None) -> list[dict]:
    """sibling_info: {node_id: {"own_purpose": str, "track_index": int,
    "lufs": float, "centroid_hz": float}} for every sibling review_composition
    was run against -- pass CURRENT values (post any prior fix), not the
    original failure's numbers. Returns the model's proposed fixes list
    (validated node ids only) -- the caller resolves node_id -> real
    track_index and executes.

    prior_fixes: fixes already applied in an earlier pass (this function's
    own previous return value) -- lets a second call revise/replace an
    existing EQ cut instead of blindly stacking a new one on top, which is
    what a real convergence check needs (does the fold settle, or does
    fixing A just relocate the problem to B, forever)."""
    prior_note = ""
    if prior_fixes:
        prior_note = f"""
Fixes already applied in an earlier pass (these are ALREADY live -- if the \
same target still has a problem, consider REVISING one of these rather than \
adding a redundant third fix on top):
{json.dumps(prior_fixes, indent=2)}
"""

    prompt = f"""A composition review failed for {parent.node_id}'s children. \
This is a genuine mixing problem, not something re-picking a preset or note \
pattern on one leaf alone can fix -- you're deciding how these SPECIFIC \
siblings should relate to each other.

own_purpose: {parent.own_purpose}

Composition review failure reasons (verbatim, from real measurements, current \
state -- after any prior fixes below already applied):
{json.dumps(list(composition_review.reasons), indent=2)}

Siblings involved (current measured values):
{json.dumps(sibling_info, indent=2)}
{prior_note}
Propose 1-3 concrete fixes. Don't default to sidechain just because this is \
a rhythm section -- read the actual reported problem (which pairs, loudness \
vs. spectral) and pick sidechain only where transient masking is really the \
issue. For spectral overlap, prefer highpass over eq_cut when a signal needs \
to vacate a low register entirely (highpass's effect on the centroid is \
predictable; eq_cut's is not, per the tool description above -- this has \
already backfired once on this exact kind of problem). A fix must target one \
of the sibling node_ids given above."""

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
