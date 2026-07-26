"""Real decomposition (plan §3.1/§6): given a Split-shaped node's
own_purpose/spec, decide the child leaves it splits into. This is the
piece nothing before this session touched at all -- leaf_proof.py and
leaf_emit.py both worked with hand-specified leaves; fold_proof.py's two
siblings were hand-picked by a human (a pad + a bell layer), not decided
by a model. This is a genuinely creative decision (how many layers, what
each one's job is), not translation -- so it's routed at Sonnet tier
(plan §6: "mid-tree decomposition"), a step up from Haiku's leaf-level DSL
emission in leaf_emit.py.

Scoped down for this first real run, documented not hidden: always
returns leaves directly (no further nested splitting) -- proving
decompose produces a sane split at all is the goal here, not an
arbitrary-depth tree yet. Nothing about this function is depth-limited
by construction, though -- calling it again on a child whose own spec
still looks too broad for one leaf is the natural way to go deeper; that
recursive call just hasn't been exercised yet.
"""
from __future__ import annotations

import json

from planner.node import Node

MODEL = "claude-sonnet-5"  # mid-tree decomposition, plan §6

DECOMPOSE_TOOL = {
    "name": "decompose",
    "description": (
        "Split this node into 2-4 independent leaf children, each its own "
        "Surge XT layer within the same section."
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
                                "What to build -- specific enough that a "
                                "leaf-implementation model could act on it "
                                "with no further creative decision left."
                            ),
                        },
                    },
                    "required": ["own_purpose", "spec"],
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

Every child will be realized on its own Surge XT instance -- you are \
deciding how many independent layers this section needs and what each \
one's job is, not the notes or preset (that's the next, translation-only \
step, done separately per child). Each child's spec should be concrete \
enough to hand to a translation-only model with no remaining creative \
sub-decision -- but you're not naming a specific preset or note pattern \
yourself, just describing the layer's role clearly enough that someone \
else could."""

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
