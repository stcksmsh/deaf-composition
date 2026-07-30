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

**Sidechain fix type: reproducibly unreliable on this REAPER-MCP setup, not
just under-configured -- treat with real suspicion (found 2026-07-27).**
First hypothesis was that `setup_sidechain_compression()`'s routing call
leaves ReaComp's own Threshold/Ratio at untouched plugin defaults, so
`_validate()` now requires `threshold_db`/`ratio` on any sidechain fix (the
executing session must call `track_fx_set_param` for ReaComp's Threshold
(param 0) and Ratio (param 1) right after `setup_sidechain_compression()`,
not just wire the routing and trust the defaults) -- a real, worthwhile
schema improvement, kept. **But this was NOT the whole story**: re-tested
live with an aggressive explicit threshold/ratio (raw params 0.1 and 1.8,
well past the plugin defaults that clearly weren't engaging) and the target
STILL measured LOUDER afterward (-11.9dB -> -5.9dB peak) -- an outcome
statistically identical to the first, unconfigured attempt. Two independent
live rounds, two different configurations, the same wrong-direction result.
Checked the obvious routing culprits (`SignIn`/`AudIn` detector-source
toggles) and found them at expected values, not misconfigured -- root cause
NOT fully isolated (a real REAPER channel-routing/multichannel-send quirk
in how `setup_sidechain_compression` wires the aux 3-4 channels is the
leading unconfirmed suspect, since a track defaulting to 2 channels
receiving a send addressed to channels 3-4 could plausibly fold back onto
the main output instead of staying isolated, but this was NOT verified --
no tool was available in this session to read a track's actual channel
count). **Practical guidance until this is properly root-caused: avoid
proposing `sidechain` fixes on this project's REAPER setup at all** --
`eq_cut` (with its own documented direction-unpredictability caveat) and
`highpass` remain the two fix types with a real track record of doing what
they claim.

**Fixes are not independent line items -- an eq_cut/highpass can silently
undo a gain fix's benefit (found 2026-07-27).** A 450Hz highpass on the
build section's texture layer correctly improved its spectral centroid but
cost 10.8dB of level, erasing most of an earlier +9dB gain fix and making
the OVERALL result worse than doing nothing (severity 22.5 vs. 20.6
pre-fix), even though the gain-only alternative (severity 12.6) was clearly
best. **Mandatory step, not optional**: after executing any eq_cut/highpass
fix, re-measure the target's LUFS and call `compensating_gain_db(pre, post)`
-- if nonzero, apply the returned dB via `set_track_volume` as a follow-up
before treating the round as done. Every eq_cut/highpass fix executed
without this check is unverified for level, no matter how good its spectral
result looks in isolation.

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
                            "enum": ["gain", "sidechain", "eq_cut", "highpass"],
                            "description": (
                                "gain: a flat, constant volume change on target's whole "
                                "track (via set_track_volume) -- the right, direct tool "
                                "for a pure loudness-BALANCE problem (a peak/LUFS gap "
                                "with no reported spectral overlap) where nothing about "
                                "target's frequency content needs to change, just its "
                                "overall level. Simpler and more predictable than "
                                "reaching for sidechain/EQ to solve a problem that's not "
                                "actually spectral or time-varying. "
                                "sidechain: ducks target's level whenever trigger "
                                "actually plays -- right when the two parts mostly "
                                "don't overlap in time and the problem is transient "
                                "masking. CAUTION (2026-07-27): two independent live "
                                "tests on this project's REAPER setup both showed the "
                                "target getting LOUDER, not quieter, after this fix -- "
                                "with default AND with aggressive explicit threshold/"
                                "ratio settings. Root cause not fully isolated (a "
                                "suspected multichannel-send routing issue, unconfirmed). "
                                "Prefer eq_cut or highpass unless there's a specific "
                                "reason sidechain is the only option, and treat any "
                                "sidechain result with real suspicion until re-verified. "
                                "eq_cut: a narrow notch at one frequency on "
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
                                "specific frequency within it. CAUTION (2026-07-27): "
                                "'upward' is not the same as 'clear of the specific "
                                "neighbor it's meant to separate from' -- confirmed "
                                "empirically that a highpass can shift a centroid "
                                "upward right ONTO a neighbor's own centroid (206Hz "
                                "-> 245Hz landed almost exactly on a neighbor sitting "
                                "at 243Hz, making that overlap worse in ratio terms "
                                "even though the direction was correct). Always pick "
                                "cutoff_hz with real margin ABOVE the specific "
                                "neighbor_node_id's own centroid_hz (given in "
                                "sibling_info below), not just any value above the "
                                "target's current centroid."
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
                            "description": "the node being gain-adjusted/ducked/EQ'd/highpassed",
                        },
                        "gain_change_db": {
                            "type": "number",
                            "description": (
                                "gain only, REQUIRED: dB change to target's track volume, "
                                "e.g. -6 to turn it down or +4 to turn it up."
                            ),
                        },
                        "send_volume_db": {
                            "type": "number",
                            "description": "sidechain only: how hard the ducking hits, e.g. 0 to -6",
                        },
                        "threshold_db": {
                            "type": "number",
                            "description": (
                                "sidechain only, REQUIRED: ReaComp's detector threshold in dB "
                                "-- the sidechain signal must cross this to trigger any gain "
                                "reduction at all. Found empirically (2026-07-26) that leaving "
                                "this at ReaComp's untouched default let a sidechain 'fix' "
                                "produce no real ducking (and the target measured LOUDER "
                                "afterward, the opposite of intended) -- must be set low enough "
                                "that the actual trigger_node_id's own measured level crosses it. "
                                "e.g. -20 to -30 for a typical drum hit."
                            ),
                        },
                        "ratio": {
                            "type": "number",
                            "description": (
                                "sidechain only, REQUIRED: ReaComp's compression ratio (e.g. 4 "
                                "for 4:1). Same reason as threshold_db -- without an explicit "
                                "ratio, ReaComp's default may barely compress even when "
                                "triggered."
                            ),
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


def compensating_gain_db(pre_lufs: float | None, post_lufs: float | None) -> float:
    """Found empirically (2026-07-27, build section's texture layer): an
    eq_cut/highpass fix removes real energy, which costs real level -- a
    450Hz highpass cut LUFS from -23.3 to -34.1 (a 10.8dB loss) even though
    it correctly improved the target's spectral centroid, silently undoing
    most of an earlier +9dB gain fix's benefit. Fixes are NOT independent
    line items even though this module's schema treats them as separate.

    Call this after applying any eq_cut/highpass fix, with the target's LUFS
    measured immediately before and after, to get the gain_change_db needed
    to restore its pre-fix level via a follow-up `set_track_volume` call --
    every eq_cut/highpass application should be followed by this check, not
    assumed level-neutral."""
    if pre_lufs is None or post_lufs is None:
        return 0.0
    return pre_lufs - post_lufs


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
        if f["type"] == "gain" and f.get("gain_change_db") is None:
            raise ValueError(f"gain fix missing gain_change_db: {f!r}")
        if f["type"] == "sidechain":
            if f.get("trigger_node_id") not in valid_node_ids:
                raise ValueError(f"unknown trigger_node_id {f.get('trigger_node_id')!r}")
            if f.get("threshold_db") is None or f.get("ratio") is None:
                raise ValueError(
                    f"sidechain fix missing threshold_db/ratio: {f!r} -- required "
                    f"since ReaComp's untouched defaults were confirmed (2026-07-26) "
                    f"to sometimes make the target LOUDER instead of ducking it"
                )
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
