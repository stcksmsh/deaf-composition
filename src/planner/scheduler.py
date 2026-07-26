"""The real recursive decompose -> emit chain (plan §11 stage 4's actual
core). build_section() (the original, single-level version) proved
decompose -> emit chains for real on a "build" section: 4 model-decided
leaves, no human picking the structure. It never actually recursed,
though -- its own decompose() prompt forced every child to be leaf-sized
("concrete enough to hand to a translation-only model with no further
creative decision"), so there was never a child marked as still-composite
to recurse into. decompose.py now asks the model to judge is_leaf
honestly per child instead of assuming it; build_tree() is what actually
acts on that -- the first real multi-level recursion in this codebase.

What this module does NOT do, on purpose (same architectural gap as
build_section() before it, and leaf_emit.py before that): execute the
emitted ops against REAPER. No standalone client exists for the ~150
reaper-mcp tools outside a real MCP session. build_tree() returns a fully
planned tree (every leaf's Leaf.implementation populated, every Split's
children populated, review_state still PENDING everywhere) for the
controlling MCP-capable session to execute, then fold results back in
with src/planner/review.py.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from leaf_emit import emit_leaf_implementation  # noqa: E402

from planner import decompose as decompose_mod  # noqa: E402
from planner.node import AcceptanceCriteria, Leaf, ModelTier, Node, ScopeLink, Split  # noqa: E402

DEFAULT_MAX_DEPTH = 3  # plan §6: "every run needs max_depth... or nodes spin
                        # and credits evaporate" -- never enforced anywhere
                        # before this; a hard cap here is that enforcement.


class MaxDepthExceeded(RuntimeError):
    pass


def build_section(root: Node, decompose_client, emit_client, *,
                   target_section_type: str, duration_s: float,
                   track_start_index: int) -> list[Node]:
    """The original single-level entry point, kept for backward
    compatibility with build_section_proof.py -- equivalent to calling
    build_tree() with max_depth=1: the root decomposes once, and any
    child that comes back with is_leaf=false raises MaxDepthExceeded
    (fails loud rather than silently mistreating a composite child as a
    leaf) instead of being recursed into. New code wanting real multi-
    level trees should call build_tree() directly with a higher
    max_depth."""
    leaves, _ = build_tree(
        root, decompose_client, emit_client,
        target_section_type=target_section_type, duration_s=duration_s,
        track_counter=_Counter(track_start_index), max_depth=1,
    )
    return leaves


class _Counter:
    """Sequential track allocation threaded through the recursion -- every
    leaf anywhere in the tree needs a distinct track, regardless of how
    deep it sits, so this can't just be a per-call local variable."""
    def __init__(self, start: int):
        self.next_index = start

    def take(self) -> int:
        i = self.next_index
        self.next_index += 1
        return i


def build_tree(node: Node, decompose_client, emit_client, *,
                target_section_type: str, duration_s: float,
                track_counter: _Counter | int, max_depth: int = DEFAULT_MAX_DEPTH,
                depth: int = 0) -> tuple[list[Node], list[Node]]:
    """Recursively decomposes `node` for real, emitting a real
    implementation for every leaf reached along the way -- at whatever
    depth it's actually reached, not assumed to be depth 1.

    Returns (leaves, all_nodes): `leaves` is every Leaf-shaped Node built
    (implementation populated, ready to execute); `all_nodes` is every
    node touched including intermediate Split nodes (for persisting the
    whole tree, not just its leaves). Mutates `node.body` into a Split
    referencing its immediate children's node_ids.
    """
    if isinstance(track_counter, int):
        track_counter = _Counter(track_counter)
    if depth >= max_depth:
        raise MaxDepthExceeded(
            f"{node.node_id} needs to split at depth {depth}, but max_depth="
            f"{max_depth} -- either the tree is genuinely too deep for this "
            f"run's budget (plan §6), or decompose is over-splitting"
        )

    raw_children = decompose_mod.decompose(node, decompose_client, duration_s=duration_s)

    leaves: list[Node] = []
    all_nodes: list[Node] = []
    child_ids: list[str] = []

    for i, spec in enumerate(raw_children):
        child_id = f"{node.node_id}/child_{i}"
        child_ids.append(child_id)

        if spec["is_leaf"]:
            track_index = track_counter.take()
            child = Node(
                node_id=child_id,
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
                scope_chain=node.scope_chain + (
                    ScopeLink(level="section", summary=node.own_purpose),
                ),
                body=Leaf(implementation={}),
                assigned_model=ModelTier.HAIKU,
            )
            implementation = emit_leaf_implementation(child, emit_client)
            child.body.implementation.update(implementation)
            child.body.implementation["track_index"] = track_index
            leaves.append(child)
            all_nodes.append(child)
        else:
            child = Node(
                node_id=child_id,
                own_purpose=spec["own_purpose"],
                spec=spec["spec"],
                acceptance_criteria=AcceptanceCriteria(structural_facts={}),
                scope_chain=node.scope_chain + (
                    ScopeLink(level="section", summary=node.own_purpose),
                ),
                body=Split(children=()),
            )
            sub_leaves, sub_all = build_tree(
                child, decompose_client, emit_client,
                target_section_type=target_section_type, duration_s=duration_s,
                track_counter=track_counter, max_depth=max_depth, depth=depth + 1,
            )
            leaves += sub_leaves
            all_nodes.append(child)
            all_nodes += sub_all

    node.body = Split(children=tuple(child_ids))
    return leaves, all_nodes
