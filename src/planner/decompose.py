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

from planner.node import Node

MODEL = "claude-sonnet-5"  # mid-tree decomposition, plan §6

DECOMPOSE_TOOL = {
    "name": "decompose",
    "description": (
        "Split this node into 2-4 independent children within the same "
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
                "maxItems": 4,
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
                    },
                    "required": ["own_purpose", "spec", "is_leaf"],
                },
            },
        },
        "required": ["children"],
    },
}


def _validate(children) -> list[dict]:
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
    if not (2 <= len(children) <= 4):
        raise ValueError(f"decompose returned {len(children)} children, expected 2-4")
    for c in children:
        if not isinstance(c, dict) or "own_purpose" not in c or "spec" not in c:
            raise TypeError(f"malformed child: {c!r}")
        if "is_leaf" not in c or not isinstance(c["is_leaf"], bool):
            raise TypeError(f"child missing a real boolean is_leaf verdict: {c!r}")
    return children


def decompose(node: Node, client, *, duration_s: float, retries: int = 2) -> list[dict]:
    """Real Sonnet call. Returns a list of {own_purpose, spec} dicts -- the
    caller is responsible for turning each into a real Node (assigning
    node_id, acceptance_criteria, scope_chain, a track) since those are
    structural/plumbing decisions, not part of what the model is deciding."""
    scope_summary = "; ".join(f"{s.level}: {s.summary}" for s in node.scope_chain)
    prompt = f"""You are decomposing one node in a recursive music-\
composition tree (plan §3: recursive descent on the way down, a fold on \
the way up). A node either splits into child problems or is a leaf that \
implements directly. This node needs to split -- it's still a composite \
decision (how many layers, what each contributes), not a single bounded \
translation.

own_purpose: {node.own_purpose}
spec: {node.spec}
ancestor context (coarsest to finest): {scope_summary}
duration: {duration_s} seconds, 120bpm, 4/4

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
worse translation can be attempted on it."""

    last_error: Exception | None = None
    for attempt in range(retries + 1):
        response = client.messages.create(
            model=MODEL,
            max_tokens=2048,
            tools=[DECOMPOSE_TOOL],
            tool_choice={"type": "tool", "name": "decompose"},
            messages=[{"role": "user", "content": prompt}],
        )
        block = next(b for b in response.content if b.type == "tool_use")
        try:
            return _validate(block.input.get("children"))
        except (TypeError, ValueError) as e:
            last_error = e
    raise RuntimeError(
        f"decompose produced a malformed result {retries + 1} times in a row: {last_error}"
    )
