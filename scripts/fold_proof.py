#!/usr/bin/env python3
"""
Minimal fold proof: two sibling leaves under one parent Split node, each
individually reviewed against its own acceptance criteria, then the parent
reviewed for "composes with siblings" (plan §3.6, checks 1 and 2). This is
the step leaf_proof.py and leaf_emit.py both stopped short of -- each of
those proved one *isolated* leaf, no siblings, no parent, no review code
running at all (the scoring was done by hand, calling reference.score_node
directly in the proof script). This one exercises src/planner/review.py for
real, against two leaves that actually share a section.

The two leaves, executed live this run (see memory.md for the full
sequence -- recorded here for reproducibility, not re-executed):
  - proof/leaf_intro_texture: the model-emitted pad leaf from leaf_emit.py
    (Surge XT, "Pads/Distant.fxp", one long sustained note), track 0.
  - proof/leaf_intro_bells: a hand-written sibling -- ReaSynth, 4 sparse
    high short notes scattered across the same 16s -- a second, much
    thinner texture layer for the same intro section, track 1. Rendered
    solo (track 1 soloed, track 0 silent) so its own state.json reflects
    only its own audio, not the pad underneath it.

Both leaves' state.json/score.json already exist under state/leaf_proof/
from the live run; this script rebuilds leaf_intro_bells's state (the pad's
was already built after track 0's render, before track 1 existed) and runs
both checks.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from planner.node import (  # noqa: E402
    AcceptanceCriteria, Leaf, ModelTier, Node, ScopeLink, Split,
)
from planner.review import review_composition, review_leaf  # noqa: E402
from return_channel import reference, state  # noqa: E402

LIBRARY = ROOT / "reference_library.json"
PROJECT = ROOT / "state/scratch/session.rpp"


def build_bells_leaf() -> Node:
    return Node(
        node_id="proof/leaf_intro_bells",
        own_purpose=(
            "A second, sparser texture layer for the same intro section as "
            "proof/leaf_intro_texture -- proves two siblings under one parent "
            "can each be reviewed and then checked for composition (plan §3.6)."
        ),
        spec=(
            "On a ReaSynth track, play 4 sparse, quiet, high-register short "
            "notes scattered across the same 16-second intro window as the "
            "pad -- a thin bell-like accent layer, not a rhythmic element."
        ),
        acceptance_criteria=AcceptanceCriteria(
            target_section_type="intro",
            max_measured_distance=4.0,
            max_embedding_distance=0.85,
            structural_facts={"instrument": "ReaSynth", "note_count": 4},
        ),
        scope_chain=(
            ScopeLink(level="album", summary="A deaf-composed machine-music record."),
            ScopeLink(level="song", summary="Opening track, establishes the record's world."),
            ScopeLink(level="section", summary="The intro's second, sparser texture layer."),
        ),
        body=Leaf(implementation={
            "ops": [
                {"tool": "mcp__reaper__track_fx_add_by_name",
                 "args": {"track_index": 1, "fx_name": "ReaSynth"}},
                {"tool": "mcp__reaper__create_midi_item",
                 "args": {"track_index": 1, "position": 0, "length": 16}},
                {"tool": "mcp__reaper__add_midi_notes_batch",
                 "args": {"track_index": 1, "item_index": 0, "notes": [
                     {"pitch": 84, "velocity": 70, "start_beat": 0, "length_beats": 2},
                     {"pitch": 91, "velocity": 55, "start_beat": 9, "length_beats": 2},
                     {"pitch": 79, "velocity": 60, "start_beat": 18, "length_beats": 2},
                     {"pitch": 88, "velocity": 50, "start_beat": 27, "length_beats": 2},
                 ]}},
            ],
            "source": "hand-written (item 2 already proved emission; scope here is fold/review)",
        }),
        assigned_model=ModelTier.HAIKU,
    )


def build_parent(children: list[Node]) -> Node:
    return Node(
        node_id="proof/section_intro",
        own_purpose="The album's intro section: sparse, atmospheric, two thin layers.",
        spec="Compose the pad and bell-accent leaves into one coherent intro section.",
        acceptance_criteria=AcceptanceCriteria(structural_facts={"child_count": len(children)}),
        scope_chain=(
            ScopeLink(level="album", summary="A deaf-composed machine-music record."),
            ScopeLink(level="song", summary="Opening track, establishes the record's world."),
        ),
        body=Split(children=tuple(c.node_id for c in children)),
    )


def main() -> int:
    library = reference.load_library(LIBRARY)

    # --- rebuild leaf_intro_bells's state (post track-1 render) ---
    bells_wav = ROOT / "state/leaf_proof/leaf_intro_bells.wav"
    bells_built = state.build(project=PROJECT, wav=bells_wav, region=None, embedding=True)
    state.write(bells_built, bells_wav.with_suffix(".state.json"))

    texture_state_path = ROOT / "state/leaf_proof/leaf_intro_texture.state.json"
    texture_built = json.loads(texture_state_path.read_text())

    bells_node = build_bells_leaf()
    texture_node = Node(  # mirrors leaf_emit.py's build_spec_node(), same node_id
        node_id="proof/leaf_intro_texture",
        own_purpose="(see leaf_emit.py)", spec="(see leaf_emit.py)",
        acceptance_criteria=AcceptanceCriteria(
            target_section_type="intro", max_measured_distance=3.0,
            max_embedding_distance=0.8,
        ),
        scope_chain=(), body=Leaf(implementation={}),
    )
    parent = build_parent([texture_node, bells_node])

    print(f"=== Reviewing children of {parent.node_id} ===\n")

    results = {}
    for node, built in [(texture_node, texture_built), (bells_node, bells_built)]:
        review, score = review_leaf(node, built, library)
        node.review_state = review
        results[node.node_id] = built
        print(f"{node.node_id}: {review.status.value}"
              + (f" -- {'; '.join(review.reasons)}" if review.reasons else ""))
        print(f"  measured distance {score['measured']['distance']:.3f}, "
              f"embedding distance {score['embedding']['distance']:.3f}, "
              f"LUFS {built['measured']['lufs']:.1f}\n")

    print(f"=== Reviewing composition at {parent.node_id} ===\n")
    composition_review = review_composition(results)
    parent.review_state = composition_review
    print(f"{parent.node_id}: {composition_review.status.value}"
          + (f" -- {'; '.join(composition_review.reasons)}"
             if composition_review.reasons else " -- balanced"))

    out = {
        "parent": parent.to_dict(),
        "children": {node_id: {} for node_id in results},
    }
    out_path = ROOT / "state/leaf_proof/fold_proof.result.json"
    out_path.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
    print(f"\nresult written: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
