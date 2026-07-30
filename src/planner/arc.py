"""Arc planning (plan §6 root tier: "root + section thinking, top
integration reviews") -- the piece nothing before this session touched:
deciding a whole song's section sequence (how many sections, what order,
what type each is, how long each runs) before any section-level
decompose() runs. Every section built so far (intro/build/drop) was
hand-picked -- a human chose target_section_type and duration_s per call --
never planned as a whole song. This module is the first real Fable-tier
consumer of node.py's ModelTier enum (FABLE is defined there but has never
been assigned by any code until this).

Design intentionally gives the model real creative freedom: no required
section-type sequence, no required drop, no forced duration variety --
those constraints live in the prompt as soft guidance only. The one hard
constraint (sections must actually differ from their recent predecessors)
is deliberately NOT enforced here at plan time -- it's checked afterward
against real rendered audio by review.review_arc_contrast, matching this
project's whole "steer by measurement, not by upfront rule" philosophy.
"""
from __future__ import annotations

import json

MODEL = "claude-opus-5"  # prototype tier for faster/cheaper iteration while
                          # this module is being built out; swap to whatever
                          # model string node.py's ModelTier.FABLE resolves
                          # to once that tier is actually wired up anywhere
                          # (it currently isn't -- see node.py's own
                          # docstring: "Never assign FABLE inside the hot
                          # loop" -- the enum has never been assigned by any
                          # code before this module).

ARC_TOOL = {
    "name": "plan_arc",
    "description": (
        "Plan the full section-by-section arc of one song: how many "
        "sections, what order, what type each is, and how long each runs. "
        "Real creative freedom -- no required sequence, no required drop "
        "at all, any order or repeats of existing reference types. "
        "Contrast between sections is checked later against real rendered "
        "audio, not enforced by this plan -- don't over-engineer artificial "
        "variety here."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "tempo_bpm": {
                "type": "number",
                "description": (
                    "This song's tempo, in beats per minute -- your own "
                    "creative call, not fixed. Pick whatever actually serves "
                    "the piece (a slow ballad might want 70bpm, a driving "
                    "track 140bpm). Must be between 40 and 220."
                ),
            },
            "time_signature_numerator": {
                "type": "integer",
                "description": (
                    "Beats per bar, quarter-note beat (denominator is always "
                    "4 -- compound meters like 6/8 are out of scope for this "
                    "pipeline). 4 is the ordinary default; 3, 5, 6, or 7 are "
                    "real options if the piece calls for it. Must be between "
                    "2 and 7."
                ),
            },
            "sections": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "properties": {
                        "own_purpose": {
                            "type": "string",
                            "description": "This section's job in the arc, in its own words.",
                        },
                        "spec": {
                            "type": "string",
                            "description": (
                                "What this section is -- specific enough to "
                                "hand to section-level decompose() later. "
                                "Not notes/presets (that's a separate, "
                                "later, translation-only step)."
                            ),
                        },
                        "target_section_type": {
                            "type": "string",
                            "description": (
                                "One of the reference library's existing "
                                "types (intro/build/drop/breakdown/outro), "
                                "or a new folder-driven type if the "
                                "reference library has grown one -- used "
                                "only as a light outlier sanity check "
                                "later, not a mold to match."
                            ),
                        },
                        "duration_s": {
                            "type": "number",
                            "description": (
                                "Section length in seconds. Cells are ~40s "
                                "soft default; a section can span multiple "
                                "cells (e.g. 80s = 2 cells). High-intensity/"
                                "climax sections should default toward the "
                                "SHORTER end -- a sustained climax loses "
                                "potency."
                            ),
                        },
                        "locked_grid": {
                            "type": "boolean",
                            "description": (
                                "true ONLY if this section is a locked-grid/"
                                "hypnotic-groove type whose staying static "
                                "past ~40s is the point, not an accident. "
                                "Requires grid_justification."
                            ),
                        },
                        "grid_justification": {
                            "type": "string",
                            "description": (
                                "Required, non-empty, real reason when "
                                "locked_grid is true -- state why this "
                                "section needs to stay static longer than "
                                "the soft cap. Empty string otherwise."
                            ),
                        },
                    },
                    "required": [
                        "own_purpose", "spec", "target_section_type",
                        "duration_s", "locked_grid", "grid_justification",
                    ],
                },
            },
            "recurring_elements": {
                "type": "array",
                "description": (
                    "Optional (empty array is fine): elements that recur "
                    "across sections, varied but recognizable, instead of "
                    "every section being a self-contained, unrelated 40s "
                    "window. Real user finding this exists to fix: a song "
                    "with none of these reads as 'a melange of windows,' "
                    "not a song."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "element_id": {
                            "type": "string",
                            "description": "Short unique slug, e.g. 'lead_motif_a'.",
                        },
                        "description": {
                            "type": "string",
                            "description": (
                                "What makes this recognizable across "
                                "occurrences -- can be timbral (the same "
                                "instrument/patch coming back), thematic "
                                "(the same melodic/rhythmic shape on a "
                                "DIFFERENT instrument), or both. Specific "
                                "enough that a section-level decompose call "
                                "later, seeing only this text, could "
                                "recognize when it's supposed to carry this "
                                "element."
                            ),
                        },
                        "section_indices": {
                            "type": "array",
                            "items": {"type": "integer"},
                            "description": (
                                "Ordered list of section indices (into the "
                                "sections array above) this element appears "
                                "in -- at least 2 (a 'recurring' element "
                                "that only appears once isn't recurring). "
                                "First index is the introduction; later "
                                "ones are recalls."
                            ),
                        },
                    },
                    "required": ["element_id", "description", "section_indices"],
                },
            },
        },
        "required": ["tempo_bpm", "time_signature_numerator", "sections", "recurring_elements"],
    },
}


def _validate_tempo(tempo_bpm, time_signature_numerator) -> tuple[float, int]:
    """tempo_bpm/time_signature_numerator are new (2026-07-29, real user
    request to stop hardcoding 120bpm/4-4 across the whole pipeline) --
    same double-encoding recovery isn't needed here since these are plain
    scalars, not nested structures, but the model can still return them as
    numeric strings (observed on other scalar fields elsewhere in this
    project), so coerce before range-checking rather than raising on a
    merely-stringified number."""
    try:
        tempo_bpm = float(tempo_bpm)
    except (TypeError, ValueError):
        raise TypeError(f"tempo_bpm was not a number: {tempo_bpm!r}")
    if not (40 <= tempo_bpm <= 220):
        raise ValueError(f"tempo_bpm must be between 40 and 220, got {tempo_bpm!r}")
    try:
        time_signature_numerator = int(time_signature_numerator)
    except (TypeError, ValueError):
        raise TypeError(
            f"time_signature_numerator was not an integer: {time_signature_numerator!r}"
        )
    if not (2 <= time_signature_numerator <= 7):
        raise ValueError(
            f"time_signature_numerator must be between 2 and 7, got "
            f"{time_signature_numerator!r}"
        )
    return tempo_bpm, time_signature_numerator


def _validate(sections) -> list[dict]:
    """Two distinct string-encoding failure modes observed live against
    this module's real (long, multi-paragraph) prompt -- confirmed
    empirically, not assumed:

    1. decompose._validate's original quirk (whole tool input
       double-encoded as a JSON string) -- handled the same way, by
       json.loads()-ing the string directly.
    2. A DIFFERENT failure hit only with arc.py's fuller prompt, not
       decompose's shorter one: the model leaks a raw tool-call parameter
       tag into the string value itself, e.g.
       '\\n<parameter name="sections">[{...}]' -- not valid JSON as-is,
       but a real JSON array sits right after the tag. Stripping up to the
       first '[' before parsing recovers it. Reproduced multiple times
       against the real prompt (3/3 in one run) before this fix; the
       content recovered this way was genuinely well-formed, not garbage,
       same lesson decompose.py already drew -- worth recovering, not just
       retrying and hoping."""
    if isinstance(sections, str):
        candidate = sections
        if candidate.lstrip().startswith("<parameter"):
            bracket = candidate.find("[")
            if bracket != -1:
                candidate = candidate[bracket:]
        try:
            parsed = json.loads(candidate)
            sections = parsed.get("sections", parsed) if isinstance(parsed, dict) else parsed
        except json.JSONDecodeError:
            pass  # let the TypeError below report the original shape
    if not isinstance(sections, list):
        raise TypeError(f"'sections' was {type(sections).__name__}, not a list")
    if len(sections) < 1:
        raise ValueError("plan_arc returned zero sections")
    for s in sections:
        if not isinstance(s, dict):
            raise TypeError(f"malformed section: {s!r}")
        for key in ("own_purpose", "spec", "target_section_type",
                    "duration_s", "locked_grid", "grid_justification"):
            if key not in s:
                raise TypeError(f"section missing {key!r}: {s!r}")
        if not isinstance(s["duration_s"], (int, float)) or s["duration_s"] <= 0:
            raise ValueError(f"duration_s must be > 0, got {s['duration_s']!r}")
        if not isinstance(s["locked_grid"], bool):
            raise TypeError(f"locked_grid must be a bool: {s!r}")
        if s["locked_grid"] and not str(s["grid_justification"]).strip():
            raise ValueError(
                f"locked_grid=True requires non-empty grid_justification: {s!r}"
            )
    return sections


def _validate_recurring(recurring_elements, num_sections: int) -> list[dict]:
    """Same double-JSON-encoding/parameter-tag-leak recovery as _validate --
    the model can produce either failure mode on any field in this tool's
    input, not just 'sections'."""
    if isinstance(recurring_elements, str):
        candidate = recurring_elements
        if candidate.lstrip().startswith("<parameter"):
            bracket = candidate.find("[")
            if bracket != -1:
                candidate = candidate[bracket:]
        try:
            parsed = json.loads(candidate)
            recurring_elements = (
                parsed.get("recurring_elements", parsed) if isinstance(parsed, dict) else parsed
            )
        except json.JSONDecodeError:
            pass
    if not isinstance(recurring_elements, list):
        raise TypeError(
            f"'recurring_elements' was {type(recurring_elements).__name__}, not a list"
        )
    seen_ids = set()
    for e in recurring_elements:
        if not isinstance(e, dict):
            raise TypeError(f"malformed recurring element: {e!r}")
        for key in ("element_id", "description", "section_indices"):
            if key not in e:
                raise TypeError(f"recurring element missing {key!r}: {e!r}")
        if not str(e["element_id"]).strip():
            raise ValueError(f"recurring element has empty element_id: {e!r}")
        if e["element_id"] in seen_ids:
            raise ValueError(f"duplicate element_id {e['element_id']!r}")
        seen_ids.add(e["element_id"])
        indices = e["section_indices"]
        if not isinstance(indices, list) or len(indices) < 2:
            raise ValueError(
                f"element {e['element_id']!r} needs >=2 section_indices to "
                f"actually be 'recurring', got {indices!r}"
            )
        for idx in indices:
            if not isinstance(idx, int) or not (0 <= idx < num_sections):
                raise ValueError(
                    f"element {e['element_id']!r} has out-of-range "
                    f"section_index {idx!r} (num_sections={num_sections})"
                )
    return recurring_elements


def plan_arc(brief: str, client, *, retries: int = 2) -> dict:
    """Fable-tier (prototyping on Opus, see MODEL). Returns {"tempo_bpm":
    float, "time_signature_numerator": int, "sections": [...],
    "recurring_elements": [...]}. tempo_bpm/time_signature_numerator are new
    (2026-07-29, real user request -- this pipeline hardcoded 120bpm/4-4
    everywhere until now); sections is the ORDERED list of section spec
    dicts as before; recurring_elements is new (2026-07-27,
    following real user feedback that the song read as "a melange of 40s
    windows" with nothing reused across sections). The caller is
    responsible for turning each section into a real Node (node_id, track
    allocation, scope_chain -- structural/plumbing decisions, same division
    of labor as decompose()) and for threading recurring_elements into each
    section's decompose() call (scripts/song_plan.py does this, maintaining
    a registry of what each element actually got realized as, section by
    section, since only song_plan.py's sequential loop knows that by the
    time a later section needs it)."""
    prompt = f"""You are planning the top-level arc of one song -- the \
first and only place this decision gets made (plan §6: "only the top \
thinking node has the whole-album view"). Every section built after this \
call inherits what you decide here.

brief: {brief}

tempo_bpm and time_signature_numerator are your own creative call too, not \
fixed infrastructure -- pick whatever actually serves this piece (40-220bpm, \
2-7 beats per bar, quarter-note beat -- compound meters like 6/8 aren't \
supported by this pipeline, but 3/4, 5/4, 6/4, 7/4 are all real options \
alongside the ordinary 4/4).

You have real creative freedom over structure. No required section-type \
sequence, no required drop at all -- you may repeat a type, skip types \
entirely, or propose something the existing reference types \
(intro/build/drop/breakdown/outro) don't name if the composition calls \
for it. Don't force a conventional form just because it's conventional.

Duration: think in ~40-second cells. That's a soft default per section, \
not a quota -- a section can span multiple cells if it needs to develop, \
and sections are NOT required to differ in length artificially. Let each \
section's own cell-count choice create whatever variety the song actually \
needs, rather than forcing variation for its own sake. If a section is \
genuinely a locked-grid/hypnotic-groove type where staying static well \
past 40s IS the point, not an oversight, mark locked_grid=true and state \
a real reason in grid_justification -- an empty or decorative reason will \
be rejected.

Real finding from a prior generation of this pipeline, not a hypothetical \
worry: EVERY section came out too long relative to how much it actually \
had to say, not just the climax -- a section spanning N cells needs to \
justify each additional cell with real content (a genuine new idea, a real \
structural turn), not just "more time for the existing idea to sit." \
Multi-cell length is not free -- default toward FEWER cells per section \
across the board, and only extend a section when you can point to what \
specifically fills the extra time. When in doubt between two adjacent cell \
counts, pick the shorter one.

A high-intensity/climax section (a drop or equivalent) should default \
toward the SHORTER end of what its content deserves -- a sustained climax \
tends to lose potency. This is a bias, not a rule: deviate if the \
composition genuinely calls for a longer climax.

Total length is entirely your call -- there's no hard cap. As ordinary \
guidance (not a cage): most tracks in this kind of idiom run roughly in \
the 2-5 minute range, but a deliberate short interlude or an atypical \
total length is fine if the composition calls for it. Decide your own \
section list; the total falls out of that, not the other way around.

One more thing, so you don't try to solve it here: whether consecutive \
sections actually sound different enough from each other will be checked \
automatically against the real rendered audio afterward, not read from \
this plan. Don't try to artificially engineer contrast into the text of \
this plan -- just plan the arc that's actually right for this song; the \
measurement step is what enforces the difference, later, for real.

recurring_elements -- a real, separate concern from the contrast check \
above: a song where every section is a self-contained window, with \
nothing carried between them, reads as a melange, not a song, no matter \
how well each individual section works or how well adjacent sections \
contrast. Name 2-3 elements that recur across the arc, each recognizable \
through EITHER the same instrument/patch coming back, OR the same \
melodic/rhythmic shape realized on a different instrument, OR both -- \
describe each clearly enough that a later section-level pass (which won't \
see this reasoning, only your description) can recognize when it's \
supposed to carry it. Each element needs at least 2 occurrences (that's \
what makes it recurring, not incidental) spread across sections that \
aren't all adjacent -- a callback lands better with distance since the \
last occurrence. Empty is a legitimate answer if the composition genuinely \
doesn't call for it, but for most songs in this idiom, 2-3 real recurring \
elements make it feel like one piece instead of several."""

    last_error: Exception | None = None
    for attempt in range(retries + 1):
        response = client.messages.create(
            model=MODEL,
            max_tokens=4096,
            tools=[ARC_TOOL],
            tool_choice={"type": "tool", "name": "plan_arc"},
            messages=[{"role": "user", "content": prompt}],
        )
        block = next(b for b in response.content if b.type == "tool_use")
        try:
            tempo_bpm, time_signature_numerator = _validate_tempo(
                block.input.get("tempo_bpm"), block.input.get("time_signature_numerator")
            )
            sections = _validate(block.input.get("sections"))
            recurring = _validate_recurring(
                block.input.get("recurring_elements", []), len(sections)
            )
            return {
                "tempo_bpm": tempo_bpm,
                "time_signature_numerator": time_signature_numerator,
                "sections": sections,
                "recurring_elements": recurring,
            }
        except (TypeError, ValueError) as e:
            last_error = e
    raise RuntimeError(
        f"plan_arc produced a malformed result {retries + 1} times in a row: {last_error}"
    )
