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
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from leaf_emit import emit_leaf_implementation  # noqa: E402

from planner import decompose as decompose_mod  # noqa: E402
from planner.node import AcceptanceCriteria, Leaf, ModelTier, Node, ScopeLink, Split  # noqa: E402

MAX_PARALLEL_LEAF_EMISSIONS = 4  # sibling leaves at the same decompose level
                                  # don't depend on each other's emitted plan,
                                  # so their Anthropic calls run concurrently --
                                  # real wall-clock win found necessary once a
                                  # whole song (33+ leaves) was being built in
                                  # one session (2026-07-27, following the
                                  # user's "we need a way to speed it up" ask).
                                  # Capped, not unbounded, to stay a polite
                                  # API client.

DEFAULT_MAX_DEPTH = 3  # plan §6: "every run needs max_depth... or nodes spin
                        # and credits evaporate" -- never enforced anywhere
                        # before this; a hard cap here is that enforcement.


class MaxDepthExceeded(RuntimeError):
    pass


def build_section(root: Node, decompose_client, emit_client, *,
                   target_section_type: str, duration_s: float,
                   track_start_index: int,
                   tempo_bpm: float = 120.0, time_signature_numerator: int = 4) -> list[Node]:
    """The original single-level entry point, kept for backward
    compatibility with build_section_proof.py -- equivalent to calling
    build_tree() with max_depth=1: the root decomposes once, and any
    child that comes back with is_leaf=false raises MaxDepthExceeded
    (fails loud rather than silently mistreating a composite child as a
    leaf) instead of being recursed into. New code wanting real multi-
    level trees should call build_tree() directly with a higher
    max_depth."""
    leaves, _, _ = build_tree(
        root, decompose_client, emit_client,
        target_section_type=target_section_type, duration_s=duration_s,
        track_counter=_Counter(track_start_index), max_depth=1,
        tempo_bpm=tempo_bpm, time_signature_numerator=time_signature_numerator,
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


def _note_summary(notes: list[dict]) -> str:
    """Compact, register-independent description of a note pattern's shape
    -- pitches relative to the pattern's own first note, so the 'same'
    motif transposed to a different register still summarizes
    recognizably. Deliberately not a full musical analysis, just enough
    for a later recurrence prompt (decompose.py's recurring_context) to
    reason about what it's being asked to vary."""
    if not notes:
        return "(no notes)"
    ordered = sorted(notes, key=lambda n: n.get("start_beat", 0))
    base = ordered[0].get("pitch", 60)
    intervals = [n.get("pitch", 60) - base for n in ordered]
    suffix = "..." if len(intervals) > 16 else ""
    return f"{len(ordered)} notes, pitch-intervals-from-first {intervals[:16]}{suffix}"


def _extract_realization(child: Node) -> dict:
    """What a leaf that realizes a recurring element actually chose --
    recorded so a LATER section's recurrence of the same element can be
    told what it's varying from, not just the element's abstract
    description."""
    ops = child.body.implementation.get("ops", [])
    preset_op = next((op for op in ops if op["tool"] == "apply_surge_preset"), None)
    notes_op = next((op for op in ops if op["tool"] == "add_midi_notes_batch"), None)
    return {
        "preset_path": preset_op["args"]["preset_path"] if preset_op else None,
        "note_summary": _note_summary(notes_op["args"]["notes"]) if notes_op else None,
    }


def _augment_spec_for_element(spec_text: str, element: dict) -> str:
    """Bakes the recurrence instruction straight into the leaf's own spec
    text -- deliberately NOT a change to leaf_emit.py's prompt or call
    signature, since node.spec is already what it reads verbatim. Keeps
    the recurring-element mechanism entirely a scheduler/decompose-level
    concern."""
    if element.get("is_recurrence") and element.get("prior_realization"):
        prior = element["prior_realization"]
        return (
            f"{spec_text} This leaf realizes recurring element "
            f"'{element['element_id']}' ({element['description']}) -- a "
            f"RECALL, previously realized as preset "
            f"'{prior.get('preset_path')}' playing note pattern "
            f"{prior.get('note_summary')}. Vary it (register, rhythm, a "
            f"different instrument on the same notes, added processing, or "
            f"some combination) while keeping it recognizably a callback, "
            f"not a literal repeat."
        )
    return (
        f"{spec_text} This leaf realizes recurring element "
        f"'{element['element_id']}' ({element['description']}) -- its "
        f"FIRST appearance in the song; later sections will recall it, so "
        f"make its identity clear and memorable."
    )


def build_tree(node: Node, decompose_client, emit_client, *,
                target_section_type: str, duration_s: float,
                track_counter: _Counter | int, max_depth: int = DEFAULT_MAX_DEPTH,
                depth: int = 0,
                recurring_context: list[dict] | None = None,
                tempo_bpm: float = 120.0, time_signature_numerator: int = 4,
                ) -> tuple[list[Node], list[Node], dict]:
    """Recursively decomposes `node` for real, emitting a real
    implementation for every leaf reached along the way -- at whatever
    depth it's actually reached, not assumed to be depth 1.

    Returns (leaves, all_nodes, element_realizations): `leaves` is every
    Leaf-shaped Node built (implementation populated, ready to execute);
    `all_nodes` is every node touched including intermediate Split nodes
    (for persisting the whole tree, not just its leaves); `element_realizations`
    (new 2026-07-27) maps element_id -> {node_id, preset_path, note_summary}
    for every recurring element actually realized anywhere in this call's
    subtree -- the caller (scripts/song_plan.py) merges this into a
    song-wide registry so a LATER section's recurrence of the same element
    knows what it's varying from. Mutates `node.body` into a Split
    referencing its immediate children's node_ids.

    recurring_context propagation is deliberately shallow, not threaded to
    arbitrary depth: elements unclaimed by any leaf child at this level are
    handed to at most the FIRST still-composite (is_leaf=false) child one
    level down, then dropped (logged, not silently) if still unclaimed
    after that. A real recurring element being buried 3+ levels deep in a
    section's tree is rare enough in practice that deeper propagation
    would add real complexity for a case that hasn't come up -- flagged
    here rather than silently building it out further than it's been
    needed.
    """
    if isinstance(track_counter, int):
        track_counter = _Counter(track_counter)
    if depth >= max_depth:
        raise MaxDepthExceeded(
            f"{node.node_id} needs to split at depth {depth}, but max_depth="
            f"{max_depth} -- either the tree is genuinely too deep for this "
            f"run's budget (plan §6), or decompose is over-splitting"
        )

    raw_children = decompose_mod.decompose(
        node, decompose_client, duration_s=duration_s, recurring_context=recurring_context,
        tempo_bpm=tempo_bpm, time_signature_numerator=time_signature_numerator,
        force_leaf=(depth == max_depth - 1),
    )

    leaves: list[Node] = []
    all_nodes: list[Node] = []
    child_ids: list[str] = []
    element_realizations: dict = {}

    context_by_id = {e["element_id"]: e for e in (recurring_context or [])}
    claimed_ids = {c["realizes_element_id"] for c in raw_children if c["realizes_element_id"]}
    unclaimed = [e for eid, e in context_by_id.items() if eid not in claimed_ids]

    # Track allocation must stay deterministic and sequential regardless of
    # emission order, so it happens up front, single-threaded, before any
    # concurrent dispatch below.
    leaf_indices = [i for i, spec in enumerate(raw_children) if spec["is_leaf"]]
    leaf_track_index = {i: track_counter.take() for i in leaf_indices}

    def build_leaf_child(i: int, spec: dict) -> Node:
        child_id = f"{node.node_id}/child_{i}"
        track_index = leaf_track_index[i]
        element_id = spec["realizes_element_id"] or None
        spec_text = spec["spec"]
        if element_id and element_id in context_by_id:
            spec_text = _augment_spec_for_element(spec_text, context_by_id[element_id])
        child = Node(
            node_id=child_id,
            own_purpose=spec["own_purpose"],
            spec=(
                f"{spec_text} (track_index={track_index}, fx_index=0, "
                f"duration {duration_s}s at {tempo_bpm:.0f}bpm/"
                f"{time_signature_numerator}-4)"
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
            prominence=spec.get("prominence", "midground"),
        )
        implementation = emit_leaf_implementation(
            child, emit_client, duration_s=duration_s,
            tempo_bpm=tempo_bpm, time_signature_numerator=time_signature_numerator,
        )
        child.body.implementation.update(implementation)
        child.body.implementation["track_index"] = track_index
        return child

    built_leaves: dict[int, Node] = {}
    if leaf_indices:
        workers = min(MAX_PARALLEL_LEAF_EMISSIONS, len(leaf_indices))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(build_leaf_child, i, raw_children[i]): i for i in leaf_indices
            }
            for future in as_completed(futures):
                i = futures[future]
                try:
                    built_leaves[i] = future.result()
                except Exception as e:
                    raise RuntimeError(
                        f"{node.node_id}/child_{i} ({raw_children[i]['own_purpose']!r}) "
                        f"failed to emit: {e}"
                    ) from e

    consumed_unclaimed = False
    for i, spec in enumerate(raw_children):
        child_id = f"{node.node_id}/child_{i}"
        child_ids.append(child_id)

        if spec["is_leaf"]:
            child = built_leaves[i]
            leaves.append(child)
            all_nodes.append(child)
            element_id = spec["realizes_element_id"] or None
            if element_id and element_id in context_by_id:
                realization = _extract_realization(child)
                element_realizations[element_id] = {"node_id": child.node_id, **realization}
                element = context_by_id[element_id]
                prior = element.get("prior_realization")
                if element.get("is_recurrence") and prior and (
                    prior.get("preset_path") == realization["preset_path"]
                    and prior.get("note_summary") == realization["note_summary"]
                ):
                    print(
                        f"  [recurrence flag] {child_id} realizes {element_id!r} "
                        f"IDENTICALLY to its prior occurrence (same preset+note "
                        f"pattern) -- the 'vary it' guidance was ignored; not a "
                        f"failure (recurrence is encouraged, not forced), just "
                        f"worth noticing."
                    )
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
                prominence=spec.get("prominence", "midground"),
            )
            child_recurring = None
            if unclaimed and not consumed_unclaimed:
                child_recurring = unclaimed
                consumed_unclaimed = True  # hand unclaimed elements down at most once
            sub_leaves, sub_all, sub_realizations = build_tree(
                child, decompose_client, emit_client,
                target_section_type=target_section_type, duration_s=duration_s,
                track_counter=track_counter, max_depth=max_depth, depth=depth + 1,
                recurring_context=child_recurring,
                tempo_bpm=tempo_bpm, time_signature_numerator=time_signature_numerator,
            )
            leaves += sub_leaves
            all_nodes.append(child)
            all_nodes += sub_all
            element_realizations.update(sub_realizations)

    if unclaimed and not consumed_unclaimed:
        for e in unclaimed:
            print(
                f"  [recurrence flag] element {e['element_id']!r} was scheduled "
                f"for {node.node_id} but no child (leaf or further split) "
                f"claimed it -- dropped for this section."
            )

    node.body = Split(children=tuple(child_ids))
    return leaves, all_nodes, element_realizations
