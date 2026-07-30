"""Real decomposition (plan §3.1/§6): given a Split-shaped node's
own_purpose/spec, decide the child leaves it splits into. This is the
piece nothing before this session touched at all -- leaf_proof.py and
leaf_emit.py both worked with hand-specified leaves; fold_proof.py's two
siblings were hand-picked by a human (a pad + a bell layer), not decided
by a model. This is a genuinely creative decision (how many layers, what
each one's job is), not translation -- so it's routed at Sonnet tier
(plan §6: "mid-tree decomposition"), a step up from Haiku's leaf-level DSL
emission in leaf_emit.py.

Each returned child now carries a real `is_leaf` verdict (plan §3.1's own
base-case predicate, asked of the model directly rather than assumed):
"a node is a leaf when it is expressible as a bounded set of deterministic
DSL commands... with no remaining creative sub-decision." A child marked
`is_leaf=False` still needs another decompose() call before it can be
emitted -- src/planner/scheduler.py's build_tree() is what actually
recurses on that, this function just answers the question honestly per
child instead of forcing every child to be leaf-sized (the first version
of this prompt did exactly that, which is why nothing ever recursed).
"""
from __future__ import annotations

import json

from planner.node import Node, PROMINENCE_LEVELS

MODEL = "claude-sonnet-5"  # mid-tree decomposition, plan §6

DECOMPOSE_TOOL = {
    "name": "decompose",
    "description": (
        "Split this node into 2-6 independent children within the same "
        "section. Each child may itself be leaf-sized (one Surge XT layer, "
        "ready for direct implementation) or still composite (needs further "
        "decomposition before it's leaf-sized) -- judge each one honestly."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "children": {
                "type": "array",
                "minItems": 2,
                "maxItems": 6,
                "items": {
                    "type": "object",
                    "properties": {
                        "own_purpose": {
                            "type": "string",
                            "description": "This child's job, in its own words.",
                        },
                        "spec": {
                            "type": "string",
                            "description": (
                                "What to build. If is_leaf is true, specific "
                                "enough that a translation-only model could "
                                "act on it with no further creative decision "
                                "left. If is_leaf is false, this is still a "
                                "composite job description -- it gets "
                                "decomposed again, not implemented directly."
                            ),
                        },
                        "is_leaf": {
                            "type": "boolean",
                            "description": (
                                "true: expressible as ONE deterministic Surge "
                                "XT layer (one preset, one note pattern) with "
                                "no remaining creative sub-decision -- ready "
                                "for direct implementation. false: this child "
                                "is still a composite decision -- e.g. "
                                "multiple interacting instruments/parts, or a "
                                "role broad enough it hides more than one "
                                "sound-design choice -- and needs its own "
                                "further split before anything can be built."
                            ),
                        },
                        "realizes_element_id": {
                            "type": "string",
                            "description": (
                                "If a recurring_context list was given below "
                                "and this child is the one carrying one of "
                                "those elements, copy that element's "
                                "element_id here verbatim. Empty string "
                                "otherwise (most children won't realize a "
                                "recurring element -- that's normal)."
                            ),
                        },
                        "prominence": {
                            "type": "string",
                            "enum": ["foreground", "midground", "background"],
                            "description": (
                                "This child's intended mixing role, not a "
                                "loudness number -- the leaf-implementation "
                                "step reads this to decide how present it "
                                "should sit in the final mix. foreground: "
                                "the thing a listener's attention should be "
                                "drawn to right now (a lead line, the "
                                "section's main motif). midground: real "
                                "harmonic/rhythmic content that should be "
                                "clearly audible but isn't the focal point "
                                "(most bass/pad/rhythm-section parts). "
                                "background: deliberately recessed texture "
                                "or color that's meant to sit under "
                                "everything else, felt more than consciously "
                                "heard. Pick honestly -- calling something "
                                "background because it's a supporting part "
                                "does NOT mean it should be inaudible, and "
                                "calling something foreground when the "
                                "section already has a real focal point "
                                "elsewhere creates competition, not depth."
                            ),
                        },
                    },
                    "required": ["own_purpose", "spec", "is_leaf", "prominence"],
                },
            },
        },
        "required": ["children"],
    },
}


def _validate(children, force_leaf: bool = False) -> list[dict]:
    """The API's tool-use JSON isn't schema-validated server-side beyond
    well-formedness -- observed empirically and consistently (not a one-off
    flake -- happened 3/3 tries on one real prompt): `children` sometimes
    comes back as a giant, perfectly well-formed JSON-blob *string* --
    `'{"children": [...]}'`, the whole tool input double-encoded and stuffed
    into its own field -- instead of an actual array (len() on it then
    silently "succeeds" by counting characters, which is how this was first
    caught: a ValueError complaining about 3395 children). The *content*
    inspected in that failure was genuinely good decomposition, not
    garbage -- worth recovering the string rather than only retrying and
    hoping for a differently-shaped response. If it parses as JSON and
    contains a real children array, use that; otherwise fall through to a
    normal type error."""
    if isinstance(children, str):
        try:
            parsed = json.loads(children)
            children = parsed.get("children", parsed) if isinstance(parsed, dict) else parsed
        except json.JSONDecodeError:
            pass  # let the TypeError below report the original shape
    if not isinstance(children, list):
        raise TypeError(f"'children' was {type(children).__name__}, not a list")
    if not (2 <= len(children) <= 6):
        raise ValueError(f"decompose returned {len(children)} children, expected 2-6")
    for c in children:
        if not isinstance(c, dict) or "own_purpose" not in c or "spec" not in c:
            raise TypeError(f"malformed child: {c!r}")
        if "is_leaf" not in c or not isinstance(c["is_leaf"], bool):
            raise TypeError(f"child missing a real boolean is_leaf verdict: {c!r}")
        # Optional and encouraged-not-forced (2026-07-27, per user decision on
        # recurring-element reuse) -- default to "" (none) rather than
        # requiring every child to carry it, since most children legitimately
        # don't realize a recurring element.
        c["realizes_element_id"] = str(c.get("realizes_element_id") or "").strip()
        # Soft default rather than a hard failure -- same reasoning as
        # realizes_element_id above: this is a new field, and rejecting an
        # otherwise-good decomposition over one malformed enum value would
        # throw away real content, not just a formatting slip.
        if c.get("prominence") not in PROMINENCE_LEVELS:
            c["prominence"] = "midground"
        if force_leaf:
            c["is_leaf"] = True
    return children


def decompose(node: Node, client, *, duration_s: float, tempo_bpm: float = 120.0,
              time_signature_numerator: int = 4, retries: int = 2,
              recurring_context: list[dict] | None = None,
              force_leaf: bool = False) -> list[dict]:
    """Real Sonnet call. Returns a list of {own_purpose, spec, is_leaf,
    realizes_element_id} dicts -- the caller is responsible for turning each
    into a real Node (assigning node_id, acceptance_criteria, scope_chain, a
    track) since those are structural/plumbing decisions, not part of what
    the model is deciding.

    recurring_context (new 2026-07-27, following real user feedback that a
    song built section-by-section with zero cross-section memory reads as
    "a melange of 40s windows"): the subset of arc.py's recurring_elements
    that this section is supposed to carry, each dict shaped
    {element_id, description, is_recurrence, prior_realization}.
    prior_realization (only present when is_recurrence=True) is what an
    earlier section actually built for this element -- preset_path and a
    short note-pattern summary -- so this call can ask for a recognizable
    variation instead of describing the element only in the abstract."""
    scope_summary = "; ".join(f"{s.level}: {s.summary}" for s in node.scope_chain)
    recurring_block = ""
    if recurring_context:
        lines = []
        for e in recurring_context:
            if e.get("is_recurrence") and e.get("prior_realization"):
                prior = e["prior_realization"]
                lines.append(
                    f"  - [{e['element_id']}] RECURRENCE of: {e['description']}\n"
                    f"    Previously realized as preset '{prior.get('preset_path')}' "
                    f"playing this note pattern: {prior.get('note_summary')}. "
                    f"Vary it -- different register, different rhythm, a "
                    f"different instrument playing the same notes, added "
                    f"processing, or some combination -- while keeping it "
                    f"recognizably a callback, not a literal repeat."
                )
            else:
                lines.append(
                    f"  - [{e['element_id']}] FIRST APPEARANCE of: {e['description']}\n"
                    f"    Introduce it fresh; later sections will recall it."
                )
        recurring_block = f"""

This section is asked to carry these recurring elements from the song's \
arc plan. If practical, make exactly ONE child realize each one -- set \
that child's realizes_element_id to the element's id verbatim, and write \
its spec around actually being that element (not just mentioning it in \
passing). This is strongly encouraged, not mandatory: skip an element only \
if nothing in this section could carry it without feeling forced.
{chr(10).join(lines)}"""

    prompt = f"""You are decomposing one node in a recursive music-\
composition tree (plan §3: recursive descent on the way down, a fold on \
the way up). A node either splits into child problems or is a leaf that \
implements directly. This node needs to split -- it's still a composite \
decision (how many layers, what each contributes), not a single bounded \
translation.

own_purpose: {node.own_purpose}
spec: {node.spec}
ancestor context (coarsest to finest): {scope_summary}
duration: {duration_s} seconds, {tempo_bpm:.0f}bpm, {time_signature_numerator}/4
{recurring_block}

You are deciding how many independent parts this section needs and what \
each one's job is -- not the notes or preset for any of them (that's a \
separate, later, translation-only step). For each child, judge honestly \
whether it's already leaf-sized: a leaf is expressible as ONE Surge XT \
layer -- one preset, one note pattern -- with no remaining creative \
sub-decision. If a child's job still hides more than one sound-design \
choice (e.g. "the rhythm section" covering both a percussive part AND a \
bassline that need to interlock, or a role broad enough that "which \
single preset" isn't yet a well-posed question), mark it is_leaf=false -- \
it will be decomposed again before anything is built. Don't force \
everything to be leaf-sized just to finish in one step; a genuinely \
composite child marked as a leaf by mistake can't be fixed later, only a \
worse translation can be attempted on it.

If this section runs more than ~16 bars, an is_leaf=true child's note \
pattern will get authored as ONE short cycle and mechanically tiled/looped \
to fill the full duration -- so a static spec produces an audibly static, \
repeating loop for the ENTIRE section, which reads as boring even when the \
loop itself is good. Real finding from a prior generation of this pipeline: \
telling the leaf step "make it evolve" without more than that just produces \
one clean, uniform ramp from a start value to an end value -- real motion, \
but the same predictable shape every time, which a listener still reads as \
static/repetitive over a long section even though something is technically \
moving. For any such child, the spec MUST describe a concrete THREE-STAGE \
arc instead of a vague "changes over time": name (a) what it sounds like at \
the start, (b) a real turning point partway through -- something that \
happens at roughly a specific point in the section, not a smooth midpoint \
average of start and end, e.g. a new layer entering, a filter snapping \
open, density doubling, a register jump -- and (c) where it lands by the \
end. Prefer a NON-monotonic arc (recede then surge, or surge then pull back \
before the next section hits) over a flat build when the section's own \
purpose supports it -- a straight line start-to-end is exactly the shape \
that reads as predictable. Say this in terms of audible, specific events, \
not just "grows" or "builds." This applies even inside a locked_grid \
section: "locked" means the rhythmic/harmonic pattern stays fixed, not that \
literally nothing may move (timbral/filter/level motion is still \
expected). Only skip this if the part is a short one-shot or a single \
sustained/evolving note that was never going to loop in the first place.{
    chr(10) + chr(10) +
    'This run has hit its recursion budget: EVERY child you return here '
    'MUST be is_leaf=true, no exceptions. If a role still feels composite, '
    'simplify it down to its single most important sound rather than '
    'marking it false -- there is no further decomposition step available '
    'after this one.' if force_leaf else ''
}"""

    last_error: Exception | None = None
    running_prompt = prompt
    for attempt in range(retries + 1):
        response = client.messages.create(
            model=MODEL,
            # Raised from 2048 (2026-07-29, live failure): decompose's own
            # per-child output got real substantially longer the same day
            # this was still 2048 -- the 3-stage-arc requirement added
            # earlier this session asks for a real described arc in every
            # long child's spec, not a one-line description. A section
            # needing several such children (found live: an 80s "locked
            # hypnotic machine" drop section) can plausibly exceed 2048
            # tokens and get its tool call truncated mid-response, which
            # surfaced as `children` coming back None rather than a
            # visibly-truncated string -- not proven with a captured
            # stop_reason, but a real, scoped, low-risk fix either way.
            max_tokens=6144,
            tools=[DECOMPOSE_TOOL],
            tool_choice={"type": "tool", "name": "decompose"},
            messages=[{"role": "user", "content": running_prompt}],
        )
        block = next(b for b in response.content if b.type == "tool_use")
        try:
            return _validate(block.input.get("children"), force_leaf=force_leaf)
        except (TypeError, ValueError) as e:
            last_error = e
            # decompose() never fed failures back before this (2026-07-29,
            # live failure: 3 IDENTICAL retries against the unchanged prompt
            # all failed the same way, "children" missing/None each time --
            # a blind retry with no feedback has no reason to behave
            # differently). Mirror leaf_emit.py's established escalating-
            # feedback pattern instead of silently repeating the same
            # request.
            running_prompt = (
                f"{prompt}\n\nYour previous attempt (this is retry "
                f"{attempt + 2} of {retries + 1}) failed: {e}. If your "
                f"response is being cut off, keep each child's spec "
                f"focused and avoid unnecessary repetition across "
                f"children -- but do not drop the 3-stage arc requirement "
                f"for children that need it. Return the children array in "
                f"full this time."
            )
    raise RuntimeError(
        f"decompose produced a malformed result {retries + 1} times in a row: {last_error}"
    )
