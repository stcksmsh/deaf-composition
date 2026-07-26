#!/usr/bin/env python3
"""
The first real seam-continuity check (plan §3.6 check 3), the piece
review.py couldn't exercise until now -- fold_proof.py and
build_section_review.py both reviewed *parallel* layers of one section
(simultaneous siblings), never two nodes that actually follow each other
on the timeline. Made that possible by moving the "build" section's 4
tracks from position 0 to position 16 (they were built overlapping the
intro in time, since build_section_proof.py never assigned them a real
position -- track allocation was the scheduler's job, timeline placement
wasn't, and nothing needed it until this check).

Builds a real "song" parent Node over the two already-existing sections
(proof/section_intro, proof/section_build) with a genuine NeighborEdge
between them (plan §3.4's local/automatic edges) -- node.py has always had
NeighborEdge in its schema; nothing before this instantiated one for real.

Run:
    RETURN_CHANNEL_CLAP_CHECKPOINT=experiments/exp1/music_audioset_epoch_15_esc_90.14.pt \
        .venv/bin/python scripts/seam_review.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from planner.node import AcceptanceCriteria, Node, NeighborEdge, ScopeLink, Split  # noqa: E402
from planner.review import review_seam  # noqa: E402
from return_channel import state  # noqa: E402

PROJECT = ROOT / "state/scratch/session.rpp"
INTRO_TRACKS = {"TEXTURE / ATMOS", "INTRO BELLS"}
BUILD_TRACKS = {"BUILD rhythmic pulse", "BUILD bass", "BUILD texture", "BUILD lead"}


def build_song() -> Node:
    song = Node(
        node_id="proof/song",
        own_purpose="The opening track: sparse intro, rising build, drop.",
        spec="Sequence the intro and build sections; the drop isn't built yet.",
        acceptance_criteria=AcceptanceCriteria(structural_facts={}),
        scope_chain=(ScopeLink(level="album", summary="A deaf-composed machine-music record."),),
        body=Split(children=("proof/section_intro", "proof/section_build")),
        # A local edge, automatic per plan §3.4 -- section_intro is section_build's
        # immediate timeline predecessor, full weight (no distance to decay over
        # for the nearest neighbor).
        neighbor_edges=(NeighborEdge(target="proof/section_build", kind="local", weight=1.0),),
    )
    return song


def main() -> int:
    # --- boundary windows: last 4s of the intro, first 4s of the build,
    # both rendered from the real combined song timeline (every track
    # audible together, not soloed) -- a seam is what actually plays across
    # the join, not each section's own isolated content. ---
    before_wav = ROOT / "state/leaf_proof/seam_before_intro_tail.wav"
    before_built = state.build(project=PROJECT, wav=before_wav, region=None,
                                track=INTRO_TRACKS, embedding=False)
    state.write(before_built, before_wav.with_suffix(".state.json"))

    after_wav = ROOT / "state/leaf_proof/seam_after_build_head.wav"
    after_built = state.build(project=PROJECT, wav=after_wav, region=None,
                               track=BUILD_TRACKS, embedding=False)
    state.write(after_built, after_wav.with_suffix(".state.json"))

    song = build_song()
    print(f"=== Reviewing the seam between {song.neighbor_edges[0].target} and its "
          f"predecessor, at {song.node_id} ===\n")
    print(f"  before (intro tail, 12-16s): LUFS {before_built['measured']['lufs']:.1f}, "
          f"centroid {before_built['measured']['spectral_centroid']['median']:.0f}Hz")
    print(f"  after  (build head, 16-20s): LUFS {after_built['measured']['lufs']:.1f}, "
          f"centroid {after_built['measured']['spectral_centroid']['median']:.0f}Hz\n")

    seam_review = review_seam(before_built, after_built)
    song.review_state = seam_review
    print(f"{song.node_id} seam: {seam_review.status.value}"
          + (f" -- {'; '.join(seam_review.reasons)}" if seam_review.reasons else " -- holds"))

    out_path = ROOT / "state/leaf_proof/seam_review.result.json"
    out_path.write_text(json.dumps({"song": song.to_dict()}, indent=2, sort_keys=True) + "\n")
    print(f"\nresult written: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
