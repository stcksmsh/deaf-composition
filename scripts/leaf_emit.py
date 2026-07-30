#!/usr/bin/env python3
"""
DSL emission (plan §6/§8.1): given one Leaf node's spec, have a real model
call -- Haiku, per §6's routing table -- emit the ordered sequence of MCP
tool calls (Leaf.implementation) that realizes it. This is the piece
scripts/leaf_proof.py deliberately hand-wrote instead of generating: that
proof was "does leaf->audio->score work at all," this one is "does a model,
given only the spec and the tool catalog, produce a sane ops list."

Scope, deliberately bounded for this proof (documented, not silently
assumed):
  - The model plans against three "creative" tools only -- apply_surge_preset,
    create_midi_item, add_midi_notes_batch. Rendering is deterministic
    plumbing derived from the emitted MIDI item, not a creative decision
    (matches the Leaf definition in node.py: "no remaining creative
    sub-decision"), so this script appends the render op itself rather than
    asking the model to plan it.
  - Exactly one MIDI item per leaf, referenced by the fixed placeholder
    item_index=0 in add_midi_notes_batch -- sidesteps needing multi-turn
    execution feedback (create_midi_item's real item_index isn't known until
    it actually runs) without inventing a general placeholder-resolution
    protocol. A leaf needing multiple items is out of scope for this proof.
  - This script only emits and validates the plan; it does not execute it
    (no standalone MCP client exists for the ~150 reaper-mcp tools outside
    an actual MCP session -- see surge_bridge_client.py's docstring for why
    that gap exists). Execution happens the same way leaf_proof.py's did:
    the controlling Claude Code session runs the emitted ops verbatim
    through its own loaded mcp__reaper__* / mcp__deaf_composition__* tools.
  - `_validate_ops` only checks structural/naming validity -- it cannot
    catch a preset whose *envelope* is wrong for the note pattern (that
    needs real rendered audio, not just plan shape). `needs_attack_check()`
    below flags plans that need that live test before being trusted; see
    scripts/check_preset_attack.py and src/planner/preset_attack.py.

Run:
    set -a; source .env; set +a
    .venv/bin/python scripts/leaf_emit.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import anthropic

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from planner.node import (  # noqa: E402
    AcceptanceCriteria, Leaf, ModelTier, Node, ScopeLink,
)

MODEL = "claude-haiku-4-5-20251001"
TEMPO = 120.0  # bpm, matches every other module's hardcoded assumption
# Minimum authored (pre-tile) pattern length, in beats, required for a
# foreground-prominence leaf on a section >=20s -- real finding (2026-07-29,
# "Tidal Lock" drop's arpeggio pluck): automation alone reads as static on a
# long, loud, foreground part; the underlying note content has to actually
# evolve. 24 beats (~6-8 bars) is what a real live re-emission achieved with
# genuine phrase-to-phrase variation after two shorter attempts (8, then 12
# beats) under-delivered against a stated-but-unenforced version of this
# same requirement -- mechanically enforced now, not just requested.
MIN_FOREGROUND_ARC_BEATS = 24.0
SURGE_FACTORY_DIR = Path("/usr/share/surge-xt/patches_factory")
# Every category except the two that aren't real sonic content -- broadened
# from "Pads only" after a real retro finding: the pulse leaf in
# build_section_review.py picked a Pads preset (slow attack/release) for a
# rhythmic part of short staccato notes and rendered at -52 LUFS, essentially
# inaudible, because nothing offered was ever going to have a fast enough
# attack for that job. Plucks/Percussion/Basses etc. are real options now.
EXCLUDED_CATEGORIES = {"Tutorials", "Templates"}
# Confirmed unreliable for short/rhythmic notes across TWO separate sessions
# ("Tidewater Clock" and "Tidal Lock") -- rendered completely silent 3+ times
# on percussive parts regardless of override attempts. Excluded outright
# rather than left for another session to rediscover and manually swap.
#
# "Percussion/Drum One.fxp" added 2026-07-29: the dominant cause (5 of 9
# silent leaves) in a real fresh song build -- confirmed live with a
# completely clean, unmodified apply + a real note (peak ~1e-6, genuine
# digital silence, not just quiet), and separately confirmed by one of the
# 5 real occurrences using zero overrides at all and still being silent.
# Same failure class as Snare Tight.fxp -- a broken factory preset on this
# system, not a leaf-authoring mistake.
#
# "Percussion/Synth Tom 1.fxp" added 2026-07-29: found while fixing one of
# the Drum One leaves above -- its re-emitted replacement picked this
# preset, which was ALSO silent (clean, unmodified, single long note at
# velocity 100 -> peak -138dB). Confirmed live via the same clean-preset
# isolation test as the others before excluding. Percussion/ is now 3-for-3
# on broken presets found this session (Snare Tight, Drum One, Synth Tom 1)
# -- worth treating any untested Percussion/ factory preset as suspect
# until it's been through a live clean-apply check at least once.
EXCLUDED_PRESETS = {
    "Percussion/Snare Tight.fxp",
    "Percussion/Drum One.fxp",
    "Percussion/Synth Tom 1.fxp",
}
SURGE_PARAM_MAP = Path(__file__).resolve().parent / "surge_param_map.json"

TOOL_CATALOG = [
    {
        "name": "apply_surge_preset",
        "description": (
            "Apply a Surge XT factory .fxp preset to a Surge XT instance already "
            "present at (track_index, fx_index), then optionally override named "
            "params. preset_path is relative to Surge's factory patch library, "
            "e.g. 'Pads/Distant.fxp'. overrides is {param_name: raw_native_value} -- "
            "param_name MUST be copied verbatim from the valid_override_names list "
            "given below; there is no other way to know a real param's exact name, "
            "and a name that isn't in that list will fail. ct_envtime params "
            "(names ending Attack/Decay/Release/Delay/Hold) are log2(seconds) -- "
            "0.0=1s, -1.0=0.5s, 1.0=2s. ct_percent params (Sustain, Resonance, "
            "Mix, ...) are plain 0-1. When in doubt, omit overrides entirely -- "
            "the preset's own defaults are always valid."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "track_index": {"type": "integer"},
                "fx_index": {"type": "integer"},
                "preset_path": {"type": "string"},
                "overrides": {"type": "object", "additionalProperties": {"type": "number"}},
            },
            "required": ["track_index", "fx_index", "preset_path"],
        },
    },
    {
        "name": "create_midi_item",
        "description": "Create one empty MIDI item on a track. position/length in seconds.",
        "input_schema": {
            "type": "object",
            "properties": {
                "track_index": {"type": "integer"},
                "position": {"type": "number"},
                "length": {"type": "number"},
            },
            "required": ["track_index", "position", "length"],
        },
    },
    {
        "name": "add_midi_notes_batch",
        "description": (
            "Add notes to the MIDI item this leaf created. Always pass "
            "item_index=0 -- this leaf creates exactly one item, and 0 always "
            "refers to it. notes: list of {pitch (0-127), velocity (1-127), "
            "start_beat, length_beats}, timed against the item's own start, at "
            "this project's tempo/time signature (given in the spec below)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "track_index": {"type": "integer"},
                "item_index": {"type": "integer"},
                "notes": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "pitch": {"type": "integer"},
                            "velocity": {"type": "integer"},
                            "start_beat": {"type": "number"},
                            "length_beats": {"type": "number"},
                        },
                        "required": ["pitch", "velocity", "start_beat", "length_beats"],
                    },
                },
            },
            "required": ["track_index", "item_index", "notes"],
        },
    },
    {
        "name": "automate_track_envelope",
        "description": (
            "OPTIONAL: add movement to one of this leaf's own track-level "
            "envelopes over time -- a volume fade/swell, a pan movement, or "
            "a stereo width change across the item. Only call this if the "
            "part is meant to evolve rather than sit static the whole "
            "section (most leaves don't need it -- omit it entirely if the "
            "preset's own character is enough). Times are seconds from the "
            "start of THIS leaf's own item."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "track_index": {"type": "integer"},
                "envelope_name": {
                    "type": "string",
                    "enum": ["Volume", "Pan", "Width"],
                },
                "points": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "time": {"type": "number"},
                            "value": {
                                "type": "number",
                                "description": (
                                    "Volume: linear amplitude, 1.0 = unity "
                                    "(0dB), 2.0 = +6dB, 0.5 = -6dB. Pan: "
                                    "-1.0 (left) to 1.0 (right). Width: 0.0 "
                                    "(mono) to 1.0 (full stereo)."
                                ),
                            },
                            "shape": {
                                "type": "integer",
                                "default": 0,
                                "description": "0=linear, 2=slow start/end (a natural swell/fade curve).",
                            },
                        },
                        "required": ["time", "value"],
                    },
                },
            },
            "required": ["track_index", "envelope_name", "points"],
        },
    },
    {
        "name": "automate_surge_param",
        "description": (
            "OPTIONAL: ramp one of this leaf's Surge XT params over time "
            "instead of leaving it static -- e.g. a rising/falling filter "
            "cutoff (an LPF/HPF sweep). param_name MUST come from "
            "valid_override_names verbatim (the same list "
            "apply_surge_preset's overrides uses), and values are in the "
            "SAME native units as an override there. Only call this for a "
            "part that's meant to visibly evolve, e.g. a filter opening up "
            "across a build section -- most leaves don't need it."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "track_index": {"type": "integer"},
                "fx_index": {"type": "integer"},
                "param_name": {"type": "string"},
                "points": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "time": {"type": "number"},
                            "value": {
                                "type": "number",
                                "description": "Native units -- same scale as apply_surge_preset's overrides.",
                            },
                            "shape": {"type": "integer", "default": 0},
                        },
                        "required": ["time", "value"],
                    },
                },
            },
            "required": ["track_index", "fx_index", "param_name", "points"],
        },
    },
]

# apply_surge_preset/create_midi_item/add_midi_notes_batch are the only
# required ops (checked by exact sequence in _validate_ops); these two may
# optionally follow them. Deliberately NOT extending this to reverb/delay
# wet automation yet -- that would need either Surge's own internal FX-slot
# params resolved (the 239-param gap flagged as deferred earlier this
# project) or a static param manifest for whatever stock reverb/delay
# plugin got added, neither of which exists. Flagged as a real gap, not
# silently dropped.
OPTIONAL_AUTOMATION_TOOLS = {"automate_track_envelope", "automate_surge_param"}


def build_spec_node() -> Node:
    """The leaf spec the model gets -- own_purpose/spec/acceptance_criteria are
    exactly what a real fold-decompose step would hand down; nothing about the
    implementation is given."""
    return Node(
        node_id="proof/leaf_intro_texture",
        own_purpose=(
            "Prove a leaf spec becomes correct audio when the DSL ops are "
            "emitted by a real model call, not hand-written (plan §11 stage 3, "
            "the emission half this time, not just execution)."
        ),
        spec=(
            "On the 'TEXTURE / ATMOS' track (track_index=12 in this project's "
            "numbering, its Surge XT instance is fx_index=0), load a factory "
            "preset suited to a sparse, atmospheric album intro and play one "
            "long sustained chord or note across the full 8-bar item (120bpm, "
            "4/4) -- this is the intro's sole textural layer, so it should read "
            "as spacious and unhurried, not rhythmic or busy."
        ),
        acceptance_criteria=AcceptanceCriteria(
            target_section_type="intro",
            max_measured_distance=3.0,
            max_embedding_distance=0.8,
            structural_facts={"instrument": "Surge XT", "bars": 8},
        ),
        scope_chain=(
            ScopeLink(level="album", summary="A deaf-composed machine-music record."),
            ScopeLink(level="song", summary="Opening track, establishes the record's world."),
            ScopeLink(level="section", summary="The intro's sole atmospheric texture layer."),
        ),
        body=Leaf(implementation={}),  # filled in by emit_leaf_implementation
        assigned_model=ModelTier.HAIKU,
    )


def _factory_preset_names() -> list[str]:
    names = []
    for category_dir in sorted(SURGE_FACTORY_DIR.iterdir()):
        if not category_dir.is_dir() or category_dir.name in EXCLUDED_CATEGORIES:
            continue
        names += [f"{category_dir.name}/{p.name}" for p in sorted(category_dir.glob("*.fxp"))]
    return [n for n in names if n not in EXCLUDED_PRESETS]


def _valid_override_names() -> set[str]:
    """The exact same source of truth apply_overrides() itself checks
    against (surge_param_map.json's resolved param names) -- giving the
    model this list up front, and validating against it before ever
    calling REAPER, closes the gap that let it invent "Master Volume" and
    "Filter Cutoff" twice this session: apply_surge_preset correctly
    raised both times, but only after a live ~2-minute preset-apply call
    had already run. Catching it here is instant and doesn't burn a real
    REAPER round-trip on a name that was never going to work."""
    param_map = json.loads(SURGE_PARAM_MAP.read_text())
    return {e["name"] for e in param_map if e.get("resolved")}


def tile_notes_to_duration(notes: list[dict], duration_beats: float) -> list[dict]:
    """Mechanically repeats a model-emitted note pattern to fill a leaf's
    actual duration, instead of asking the model to write every note for a
    long section directly. Real, reproducible failure this fixes (found live
    building "Tidal Lock"'s 80s locked-grid drop): a continuous 16th-note
    arpeggio over 80 seconds needs ~640 notes, which overflows a single
    emit call's token budget -- 5/5 identical attempts came back with the
    notes array missing entirely (truncated mid-argument), not just short.
    Plumbing, not a creative decision -- same reasoning as track_index/
    timeline placement being assigned mechanically rather than asked of the
    model. A no-op if the pattern already covers (or exceeds) the full
    duration, so genuinely one-shot/evolving parts are untouched."""
    if not notes:
        return notes
    pattern_span = max(n["start_beat"] + n["length_beats"] for n in notes)
    if pattern_span <= 0 or pattern_span >= duration_beats:
        return notes
    tiled = []
    rep = 0
    while rep * pattern_span < duration_beats:
        shift = rep * pattern_span
        for n in notes:
            start = n["start_beat"] + shift
            if start >= duration_beats:
                continue
            tiled.append({**n, "start_beat": start})
        rep += 1
    return tiled


def emit_leaf_implementation(node: Node, client: anthropic.Anthropic,
                              feedback: str | None = None, retries: int = 4,
                              duration_s: float | None = None,
                              tempo_bpm: float = TEMPO,
                              time_signature_numerator: int = 4) -> dict:
    preset_names = _factory_preset_names()
    valid_overrides = _valid_override_names()

    foreground_arc_override = ""
    if node.prominence == "foreground" and duration_s and duration_s >= 20:
        foreground_arc_override = f"""

OVERRIDE for this leaf specifically -- the "one short cycle" instruction \
above does NOT apply here. This is a foreground-prominence leaf on a \
{duration_s:.0f}s section: real user finding is that automation alone \
(filter/volume swells on an unchanging short loop) reads as static and \
repetitive in exactly this case, especially in loud/locked-groove \
sections where a listener's attention sits on this part -- confirmed \
live, not theoretical. Author a LONGER pattern spanning at least ~24 \
beats (roughly 6-8 bars, still compact enough for one response -- do NOT \
attempt the full section length) structured as 3-4 distinct short \
phrases that are NOT pitch-for-pitch identical to each other: phrase 1 \
states the core melodic idea plainly; phrase 2 is a real variation \
(an embellishing/passing note, a rhythmic displacement) with DIFFERENT \
pitches than phrase 1 at equivalent positions, not phrase 1 repeated; \
phrase 3 a further variation (register shift, contour stretched/\
compressed); phrase 4 thins back down or resolves, priming a natural \
return to phrase 1's character. This block will still be tiled to fill \
the section if it doesn't already reach the full duration, but the \
REPEATING UNIT will now contain real internal motion across 24+ beats \
instead of being a short static loop."""

    def build_prompt(extra_feedback: str | None) -> str:
        return f"""You are planning the implementation of one leaf node in a \
recursive music-composition tree. A leaf is translation, not composition: \
you are given a fully-specified creative decision and must express it as a \
bounded set of deterministic tool calls -- nothing here is left to your \
own creative judgment beyond picking which preset name and which notes best \
match the spec.

own_purpose: {node.own_purpose}
spec: {node.spec}
acceptance_criteria: {json.dumps(node.acceptance_criteria.to_dict())}
scope_chain: {json.dumps([{"level": s.level, "summary": s.summary} for s in node.scope_chain])}

Available Surge XT factory presets, every category (preset_path must be \
exactly one of these, "<Category>/<name>.fxp" -- pick whichever category \
actually fits the part: a rhythmic/percussive part needs a fast attack \
(Plucks, Percussion), a sustained texture needs a slow one (Pads), etc.):
{json.dumps(preset_names, indent=2)}

valid_override_names (apply_surge_preset's overrides keys MUST come from \
this exact list verbatim, or be omitted entirely -- no other name will work):
{json.dumps(sorted(valid_overrides), indent=2)}
{f"{chr(10)}{extra_feedback}{chr(10)}" if extra_feedback else ""}
Emit the tool calls needed to realize this leaf, in the exact order they \
must execute: one apply_surge_preset call, one create_midi_item call, then \
one add_midi_notes_batch call (item_index=0). Call each tool exactly once, \
in that order, in this single turn.

If this part is a REPEATING rhythmic/melodic pattern (a loop, an ostinato, \
an arpeggio, a groove), emit only ONE natural cycle of it (however many \
bars that pattern actually needs -- often 1-4) -- do NOT try to write out \
notes for the entire section's duration yourself. The pattern is \
automatically tiled/repeated afterward to fill the leaf's real length; \
writing it out in full yourself for a long section will overflow this \
call's token budget and fail. If the part is genuinely NOT repeating (one \
sustained note, a single evolving swell, a part that's meant to change \
and not loop), write it out in full as its own actual length instead --\
it won't be tiled if it already spans the requested duration.{foreground_arc_override}

After those three, add automate_track_envelope and/or automate_surge_param \
calls so this part actually evolves over its own duration -- a volume \
swell, a rising/falling filter cutoff, a widening stereo image, a density \
or brightness shift partway through. {
    f"This leaf's one authored cycle will repeat roughly "
    f"{max(1, round(duration_s * tempo_bpm / 60.0 / time_signature_numerator))} "
    f"times to fill its "
    f"{duration_s:.0f}s duration -- a bare repeating loop with zero motion "
    f"for that long reads as static and boring, even if the loop itself is "
    f"good. At least one automation call covering the FULL duration is "
    f"required for a leaf this long. A single 2-point ramp from the start "
    f"value straight to the end value is NOT enough -- interpolated over "
    f"{duration_s:.0f}s that's an almost imperceptibly slow crawl, not real "
    f"movement, and it's also the wrong SHAPE regardless of point count: a "
    f"uniform ramp is exactly what reads as predictable/mechanical over a "
    f"long section, even with more points sprinkled onto it. If the spec "
    f"above describes a concrete arc (a start state, a turning point, an "
    f"end state), your automation points MUST realize THAT shape -- put a "
    f"point at the moment the spec's turning point happens, not evenly "
    f"spaced ones. A non-monotonic arc (recede then surge, or surge then "
    f"pull back) is preferred over a flat build whenever the spec supports "
    f"it. For a foreground-prominence leaf especially, combine at least TWO "
    f"different automation targets (e.g. volume AND filter cutoff, not just "
    f"one) so the evolution is felt through more than a single lever."
    if duration_s and duration_s >= 12
    else "Skip automation only for something genuinely short or a single "
    "sustained note where added movement would fight the part's own "
    "purpose -- state that reasoning isn't needed, just don't add motion "
    "that contradicts the spec."
}

For any automate_surge_param call on a continuous parameter (filter \
cutoff, resonance, etc.): Surge's own internal parameter ranges are much \
narrower than raw Hz/frequency numbers would suggest (e.g. filter cutoff \
is NOT stored in Hz). Confirmed live twice: values like 8000 or 10500 for \
a cutoff parameter are far outside its real range and get silently \
clamped to the parameter's ceiling, flattening the automation you \
intended. Favor small, conservative moves relative to the preset's own \
starting value (e.g. -2.0 to +2.0-ish for a filter cutoff override) over \
large absolute-sounding numbers you're not certain are in-range.

prominence: {node.prominence} -- this leaf's intended mixing role \
(foreground/midground/background). It does not change what tool calls you \
emit here (leveling itself is handled separately by the pipeline, not by \
you), but it should inform note velocity choices and, for a foreground \
leaf, argues for a more confident/present sound-design choice rather than a \
timid one."""

    last_error: Exception | None = None
    running_feedback = feedback
    for attempt in range(retries + 1):
        response = client.messages.create(
            model=MODEL,
            max_tokens=8192,  # a dense preset with many overrides plus a
                              # multi-chord note pattern can still overflow
                              # 4096 across all 3+ tool calls in one turn --
                              # observed live truncating mid-sequence (missing
                              # the whole add_midi_notes_batch call, not just
                              # a short notes array) building "Tidal Lock"'s
                              # opening pad leaf, even with tile_notes_to_
                              # duration() already limiting the notes array
                              # itself to one short cycle. Raised again with
                              # real headroom rather than incrementally.
            tools=TOOL_CATALOG,
            tool_choice={"type": "any"},
            messages=[{"role": "user", "content": build_prompt(running_feedback)}],
        )
        ops = [{"tool": block.name, "args": block.input}
               for block in response.content if block.type == "tool_use"]
        try:
            _validate_ops(ops, valid_overrides)
            if duration_s is not None:
                notes_op = next(op for op in ops if op["tool"] == "add_midi_notes_batch")
                item_op = next(op for op in ops if op["tool"] == "create_midi_item")
                duration_beats = duration_s * tempo_bpm / 60.0
                raw_notes = notes_op["args"]["notes"]
                # The model's OWN declared item length is the real signal for
                # how much of the section this leaf is meant to actively
                # occupy -- NOT always the full section duration. Found live
                # (2026-07-29, first real multi-section pipeline run since
                # this rule was added): a leaf spec explicitly asked for "a
                # short (roughly 2-3 second) ... gesture ... no loop ... then
                # leaves total space for the bell/pad to enter" -- a genuine
                # one-shot within a much longer section. The model correctly
                # authored a 3-beat item for it, but this code was comparing
                # against the SECTION's full duration_beats (40s = ~59 beats),
                # both wrongly demanding 24+ beats of content for something
                # that was supposed to be 3 beats, AND (via tile_notes_to_
                # duration below) about to loop that "no loop" gesture across
                # the entire section. effective_duration_beats fixes both by
                # trusting the model's own item length when it's genuinely
                # shorter than the section, falling back to the full section
                # otherwise (the original, still-correct default for the
                # common case of a leaf meant to fill its whole section).
                item_length_beats = item_op["args"]["length"] * tempo_bpm / 60.0
                item_is_deliberately_short = 0 < item_length_beats < duration_beats
                effective_duration_beats = (
                    item_length_beats if item_is_deliberately_short else duration_beats
                )
                # Mechanically enforce the foreground-long-section OVERRIDE
                # above, rather than trusting the model followed it --
                # found live (2026-07-29) that a stated-but-unenforced "must
                # be >=24 beats" instruction was under-delivered twice in a
                # row (8 beats, then 12 beats) before being caught by hand.
                # This closes that gap for future runs: a too-short pattern
                # is now a real validation failure that retries with
                # feedback, the same path _validate_ops already uses below.
                # Gated on effective_duration_beats (not the raw section
                # duration) so a deliberately short one-shot item -- see
                # above -- is never forced into a fabricated 24-beat pattern.
                if (node.prominence == "foreground" and duration_s >= 20 and raw_notes
                        and effective_duration_beats >= MIN_FOREGROUND_ARC_BEATS):
                    pattern_span = max(n["start_beat"] + n["length_beats"] for n in raw_notes)
                    min_required = min(MIN_FOREGROUND_ARC_BEATS, effective_duration_beats)
                    if pattern_span < min_required:
                        raise ValueError(
                            f"foreground leaf on a {duration_s:.0f}s section authored "
                            f"only {pattern_span:.1f} beats before its pattern would "
                            f"repeat -- the OVERRIDE instruction requires at least "
                            f"{MIN_FOREGROUND_ARC_BEATS:.0f} beats structured as 3-4 "
                            f"genuinely different phrases. Re-read that instruction: "
                            f"the 'one short cycle' guidance does NOT apply to this leaf."
                        )
                # A deliberately short item is never tiled -- the model was
                # only ever instructed to expect its short cycle tiled to
                # fill the FULL section (the emit prompt's own "automatically
                # tiled/repeated afterward to fill the leaf's real length"
                # language), never some shorter intermediate window. Trust
                # the model's raw authoring as final for a short item instead
                # of mechanically repeating it into a "loop" it was
                # explicitly told not to have.
                tiled = (
                    raw_notes if item_is_deliberately_short
                    else tile_notes_to_duration(raw_notes, effective_duration_beats)
                )
                # tile_notes_to_duration is deliberately a no-op for a pattern that
                # already spans/exceeds duration_beats (a genuine one-shot/sustained
                # part), but that leaves a real gap: the model has no explicit
                # duration_beats constraint in the sustained-note branch of its own
                # prompt, so it can (and did, live: a "40s" pad leaf came back with
                # an 80s sustained note) emit a note far longer than the leaf's
                # actual duration. Clamp here rather than growing the item to match
                # -- a sustained pad note getting cut off at the section boundary is
                # correct leaf behavior; silently extending the item into whatever
                # comes next in the timeline is not.
                for n in tiled:
                    if n["start_beat"] + n["length_beats"] > duration_beats:
                        n["length_beats"] = max(0.0, duration_beats - n["start_beat"])
                tiled = [n for n in tiled if n["length_beats"] > 0]
                notes_op["args"]["notes"] = tiled
                # tile_notes_to_duration extends the NOTES; it does nothing to
                # the MIDI item container those notes live in. REAPER clips
                # notes outside their item's [position, position+length)
                # bounds -- found live building "Tidal Lock": ~12 leaves
                # across 4 sections had notes tiled out past their own item's
                # length, silently inaudible past that boundary despite
                # rendering "fine." The item must grow to match.
                if tiled:
                    needed_end_beats = max(n["start_beat"] + n["length_beats"] for n in tiled)
                    needed_length_s = needed_end_beats / tempo_bpm * 60.0
                    if needed_length_s > item_op["args"]["length"]:
                        item_op["args"]["length"] = needed_length_s
            return {"ops": ops, "source": f"model-emitted ({MODEL})"}
        except ValueError as e:
            last_error = e
            # Real finding (2026-07-29, live pipeline run): a generic "fix this
            # specific problem" retry message is NOT enough to unstick a model
            # that keeps falling back to a short tiled cycle -- this exact
            # failure mode was hand-diagnosed earlier the same day and needed
            # an explicit "OVERRIDE, ignore your instinct, N prior attempts
            # already failed this way" framing before it actually produced a
            # longer authored pattern. A flat restatement of the error just
            # reproduces the same short-cycle answer on every retry. Detect
            # this specific failure by its message (raised by the
            # MIN_FOREGROUND_ARC_BEATS check above) and escalate for real,
            # not just repeat.
            if "beats before its pattern would repeat" in str(e):
                running_feedback = (
                    f"{feedback + ' ' if feedback else ''}"
                    f"OVERRIDE -- this is attempt {attempt + 2} at this leaf. "
                    f"Your previous {attempt + 1} attempt(s) all fell back to "
                    f"a short repeating cycle despite being told not to: {e} "
                    f"Whatever instinct is producing a short cycle here, "
                    f"suspend it. Do not tile a 2-4 beat pattern. Write out "
                    f"actual, different notes for each of 4 real phrases "
                    f"spanning 24+ beats total -- phrase 2's notes must not "
                    f"match phrase 1's, phrase 3's must not match either "
                    f"earlier phrase. Automation on top is fine and "
                    f"encouraged, but it does NOT substitute for this -- the "
                    f"note content itself must be longer and non-repeating."
                )
            else:
                running_feedback = (
                    f"{feedback + ' ' if feedback else ''}Your previous attempt was "
                    f"structurally invalid: {e}. Fix this specific problem."
                )
    raise RuntimeError(
        f"emit_leaf_implementation produced an invalid plan {retries + 1} times "
        f"in a row: {last_error}. Final attempt's raw ops: {json.dumps(ops)}. "
        f"spec was: {node.spec!r}"
    )


def _validate_ops(ops: list[dict], valid_overrides: set[str] | None = None) -> None:
    """Fail loudly on a malformed plan rather than silently patching it --
    per Leaf's own definition, a leaf has no remaining creative sub-decision,
    so there's nothing legitimate to improvise here if the model got the
    mechanical shape wrong. Checking override names here (not just at
    apply_surge_preset's own call time) catches a hallucinated name before
    it costs a real ~2-minute REAPER round-trip, not just eventually."""
    names = [op["tool"] for op in ops]
    expected = ["apply_surge_preset", "create_midi_item", "add_midi_notes_batch"]
    if names[:3] != expected:
        raise ValueError(f"expected op sequence to start with {expected}, model emitted {names}")
    preset_path = ops[0]["args"].get("preset_path")
    if preset_path in EXCLUDED_PRESETS:
        # EXCLUDED_PRESETS filters the PROMPT's offered list, but that alone
        # doesn't stop the model from emitting an excluded name anyway --
        # Surge's Category/Name.fxp convention is guessable/memorable enough
        # that this happened for real building "Tidal Lock" (2 leaves picked
        # 'Percussion/Snare Tight.fxp' despite it never appearing in the
        # preset_names list they were given). Structural rejection here
        # catches it before a live apply, not just via omission.
        raise ValueError(
            f"preset_path {preset_path!r} is in EXCLUDED_PRESETS (confirmed "
            f"unreliable) -- pick a different preset even though this name "
            f"may feel familiar/plausible"
        )
    if ops[2]["args"].get("item_index") != 0:
        raise ValueError(
            f"add_midi_notes_batch must use item_index=0 (the placeholder for "
            f"this leaf's one MIDI item), got {ops[2]['args'].get('item_index')!r}"
        )
    if not ops[2]["args"].get("notes"):
        raise ValueError(
            "add_midi_notes_batch had no notes (missing or empty) -- a leaf "
            "with no notes renders as silence, the same class of bug as the "
            "known preset-attack silence failures, just structural instead "
            "of timbral"
        )
    if valid_overrides is not None:
        overrides = ops[0]["args"].get("overrides") or {}
        invalid = set(overrides) - valid_overrides
        if invalid:
            raise ValueError(
                f"apply_surge_preset overrides used unknown param name(s) "
                f"{sorted(invalid)} -- not in valid_override_names"
            )

    for op in ops[3:]:
        if op["tool"] not in OPTIONAL_AUTOMATION_TOOLS:
            raise ValueError(
                f"unexpected op after the required 3: {op['tool']!r} -- only "
                f"{sorted(OPTIONAL_AUTOMATION_TOOLS)} may follow them"
            )
        if op["tool"] == "automate_track_envelope":
            envelope_name = op["args"].get("envelope_name")
            if envelope_name not in ("Volume", "Pan", "Width"):
                raise ValueError(
                    f"automate_track_envelope envelope_name must be one of "
                    f"Volume/Pan/Width, got {envelope_name!r}"
                )
            if not op["args"].get("points"):
                raise ValueError("automate_track_envelope had no points")
        elif op["tool"] == "automate_surge_param":
            if not op["args"].get("points"):
                raise ValueError("automate_surge_param had no points")
            if valid_overrides is not None:
                param_name = op["args"].get("param_name")
                if param_name not in valid_overrides:
                    raise ValueError(
                        f"automate_surge_param param_name {param_name!r} not "
                        f"in valid_override_names"
                    )


# Real cutoff found live against Percussion/Synth Tom 2.fxp (2026-07-26): its
# attack took ~1.0-1.1s to reach half its own eventual peak, which cleared a
# 4-beat note but failed everything from 0.25 up to 2 beats at 120bpm. Any
# plan whose shortest note is at or under this many beats needs a live
# attack-time check (scripts/check_preset_attack.py) before being trusted --
# not just this one preset's known-bad case, since the same failure has now
# hit 3 different presets picked for 3 different rhythmic roles.
ATTACK_CHECK_BEATS_THRESHOLD = 2.0


def min_note_length_beats(ops: list[dict]) -> float | None:
    """Shortest note length in the emitted add_midi_notes_batch call, or
    None if there are no notes to check."""
    notes_op = next((op for op in ops if op["tool"] == "add_midi_notes_batch"), None)
    notes = notes_op["args"].get("notes") if notes_op else None
    if not notes:
        return None
    return min(n["length_beats"] for n in notes)


def needs_attack_check(ops: list[dict]) -> bool:
    """True if this plan's shortest note is short enough that the chosen
    preset's envelope needs to be verified live (rendered + measured) before
    accepting the plan -- see scripts/check_preset_attack.py for the actual
    live test. Structural validation (_validate_ops) cannot catch this: a
    preset can be a perfectly well-formed, correctly-named choice and still
    render as near-silence if its attack doesn't fit inside the note length,
    which is exactly what sank 3 separate leaves this session."""
    min_len = min_note_length_beats(ops)
    return min_len is not None and min_len <= ATTACK_CHECK_BEATS_THRESHOLD


def feedback_for_attack_failure(preset_path: str, note_length_beats: float, reason: str) -> str:
    """Turns a failed live attack-time check into retry feedback for the next
    emit_leaf_implementation() call -- same mechanism as
    escalation.feedback_for_retry(), for a failure class review_leaf/
    review_composition can't see (they only ever look at the final render,
    which by then has already burned a real ~2-minute preset-apply call)."""
    return (
        f"Your previous attempt picked preset '{preset_path}' for a pattern whose "
        f"shortest note is {note_length_beats} beats. A live attack-time test showed: "
        f"{reason}. Pick a preset with a demonstrably fast attack for a part this "
        f"rhythmic (Plucks and Percussion categories vary widely in this -- category "
        f"name alone is not reliable), or use longer notes if the part can tolerate it. "
        f"Do not repeat the same preset at this note length."
    )


def main() -> int:
    node = build_spec_node()
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    implementation = emit_leaf_implementation(node, client)

    node.body.implementation.update(implementation)
    print(json.dumps(implementation, indent=2))

    out_path = ROOT / "state/leaf_proof/leaf_intro_texture.plan.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({
        "node": node.to_dict(),
        "implementation": implementation,
    }, indent=2, sort_keys=True) + "\n")
    print(f"\nplan written: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
