"""The first real decompose -> emit chain (plan §11 stage 4's actual
unstarted core, per memory.md's own framing): given one Split-shaped root
node, get real children from decompose.decompose() (Sonnet), then get a
real Leaf.implementation for each from leaf_emit.emit_leaf_implementation()
(Haiku, reused as-is from scripts/leaf_emit.py). No hand-picked leaves
anywhere in this path -- fold_proof.py's pad+bells pair was a human
decision; this is the model's own.

What this module does NOT do, on purpose: execute the emitted ops against
REAPER. No standalone client exists for the ~150 reaper-mcp tools outside
a real MCP session (same architectural gap leaf_emit.py already
documented) -- build_section() returns a fully planned tree (every child's
Leaf.implementation populated, review_state still PENDING) for the
controlling MCP-capable session to execute, then fold results back in
with src/planner/review.py's already-proven review_leaf/review_composition.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from leaf_emit import emit_leaf_implementation  # noqa: E402

from planner import decompose as decompose_mod  # noqa: E402
from planner.node import AcceptanceCriteria, Leaf, ModelTier, Node, ScopeLink, Split  # noqa: E402


def build_section(root: Node, decompose_client, emit_client, *,
                   target_section_type: str, duration_s: float,
                   track_start_index: int) -> list[Node]:
    """Decomposes `root` for real and emits a real implementation for each
    child. Mutates root.body into a Split referencing the children.
    Assigns each child a fresh, sequential track_index starting at
    track_start_index (track allocation is plumbing -- which physical
    track a layer lives on isn't a creative decision -- so the scheduler
    handles it, not the model).

    Returns the list of built child Nodes (implementation populated,
    review_state left PENDING -- that's the executing session's job).
    """
    raw_children = decompose_mod.decompose(root, decompose_client, duration_s=duration_s)

    children: list[Node] = []
    for i, spec in enumerate(raw_children):
        track_index = track_start_index + i
        child = Node(
            node_id=f"{root.node_id}/leaf_{i}",
            own_purpose=spec["own_purpose"],
            spec=(
                f"{spec['spec']} (track_index={track_index}, fx_index=0, "
                f"duration {duration_s}s at 120bpm/4-4)"
            ),
            acceptance_criteria=AcceptanceCriteria(
                target_section_type=target_section_type,
                max_measured_distance=4.0,
                max_embedding_distance=0.85,
            ),
            scope_chain=root.scope_chain + (
                ScopeLink(level="section", summary=root.own_purpose),
            ),
            body=Leaf(implementation={}),
            assigned_model=ModelTier.HAIKU,
        )
        implementation = emit_leaf_implementation(child, emit_client)
        child.body.implementation.update(implementation)
        child.body.implementation["track_index"] = track_index
        children.append(child)

    root.body = Split(children=tuple(c.node_id for c in children))
    return children
