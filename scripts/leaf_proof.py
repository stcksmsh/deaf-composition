#!/usr/bin/env python3
"""
Minimal single-leaf proof (plan §11 stage 3): "prove a leaf spec becomes
correct audio," end-to-end through the real pieces already built --
node schema (src/planner/node.py), the leaf-vocabulary MCP tools (§8.1),
and the return-channel measure/embed/score pipeline (stages 1-2) -- with
no new fold/scheduler machinery, because that's stage 4 and doesn't exist
yet.

What actually happened, live, this run (recorded here for reproducibility,
not re-executed by this script -- the MCP calls already ran in the
controlling session):
  1. track 1 ("Generator", already carrying a Surge XT instance) got the
     Bass 5 factory preset applied via mcp__deaf_composition__apply_surge_preset,
     with overrides for a slightly slower attack/release than the stock patch.
  2. A 16-note driving bassline (4 bars @ 120bpm, root/fifth/octave motion,
     punchy 0.9-beat note lengths) was written via
     mcp__reaper__create_midi_item + add_midi_notes_batch.
  3. mcp__reaper__render_project rendered bars 3-5 (the new material) to
     state/leaf_proof/leaf_bass_drop.wav.
  4. This script measures + embeds that wav and scores it against the
     real reference library's "drop" envelope, exactly the way a fold
     review would (reference.score_node) -- just invoked directly, since
     there is no reviewer node yet to invoke it for us.

Deliberately NOT done here: mcp__reaper__save_project. The live project
was never given a filename (still "[unsaved project]", same disposable
scratch instance from earlier sessions), and save_project on an unnamed
project pops REAPER's native Save-As dialog, which blocks the whole
bridge under Xvfb (a documented near-incident, memory.md's "Near-incident,
resolved" entry) -- recovered once already this session via an xdotool
Escape, not worth repeating for a proof run. So this script hand-supplies
the symbolic note data (rpp.extract_symbolic's schema, populated from
exactly what step 2 wrote) instead of round-tripping through a saved
.rpp + rpp.parse_file. A real pipeline run *would* save the project --
this is a one-off proof of the leaf→audio→score path, not the save flow.

Run:
    RETURN_CHANNEL_CLAP_CHECKPOINT=experiments/exp1/music_audioset_epoch_15_esc_90.14.pt \
        .venv/bin/python scripts/leaf_proof.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from planner.node import (  # noqa: E402
    AcceptanceCriteria, Leaf, ModelTier, Node, ScopeLink,
)
from return_channel import reference, state  # noqa: E402

WAV = ROOT / "state/leaf_proof/leaf_bass_drop.wav"
LIBRARY = ROOT / "reference_library.json"
BPM = 120.0
ITEM_POSITION_S = 4.0  # where the rendered region starts in the live project

# The exact 16 notes added via add_midi_notes_batch (start_beat/length_beats,
# converted to seconds at 120bpm -- 0.5s/beat) -- hand-supplied because the
# live project was never saved to a .rpp this run (see module docstring).
_NOTES_BEATS = [
    (36, 115, 0), (36, 95, 1), (43, 100, 2), (36, 95, 3),
    (36, 115, 4), (36, 95, 5), (43, 100, 6), (48, 105, 7),
    (36, 115, 8), (36, 95, 9), (43, 100, 10), (36, 95, 11),
    (36, 115, 12), (36, 95, 13), (43, 100, 14), (48, 110, 15),
]
SEC_PER_BEAT = 60.0 / BPM
NOTE_LEN_BEATS = 0.9


def hand_supplied_symbolic() -> dict:
    notes = []
    for pitch, velocity, start_beat in _NOTES_BEATS:
        start_s = ITEM_POSITION_S + start_beat * SEC_PER_BEAT
        end_s = ITEM_POSITION_S + (start_beat + NOTE_LEN_BEATS) * SEC_PER_BEAT
        notes.append({
            "pitch": pitch, "velocity": velocity, "channel": 0,
            "start_ticks": None, "end_ticks": None,
            "start_s": start_s, "end_s": end_s,
            "track": "Generator", "item": 1,
        })
    return {
        "tempo": BPM, "time_sig": [4, 4], "sample_rate": 48000,
        "bounds": {"selection": None, "regions": [], "render": None},
        "tracks": [{
            "index": 1, "guid": "", "name": "Generator", "is_folder": False,
            "folder_depth": 0, "channels": 2, "volume": [1.0, 0.0],
            "muted": False, "main_send": True,
        }],
        "fx": [{"name": "Surge XT", "track": "Generator",
                "preset": "Basses/Bass 5.fxp",
                "overrides": {"A Amp EG Release": -1.5, "A Amp EG Attack": -2.0}}],
        "notes": notes,
        "automation": [],
    }


def build_leaf_node() -> Node:
    return Node(
        node_id="proof/leaf_bass_drop",
        own_purpose=(
            "Prove a hand-written leaf spec becomes correct, measurable audio "
            "end-to-end (plan §11 stage 3), reusing the already-verified Surge "
            "preset pipeline and the return-channel measure/embed/score chain."
        ),
        spec=(
            "On the Generator track's Surge XT instance, load the Bass 5 "
            "factory preset with a slightly slower attack/release than stock "
            "(more sustain, less pluck), then play a 4-bar driving root/fifth/"
            "octave bassline (16 notes, punchy 0.9-beat lengths) suited to a "
            "high-energy 'drop' section."
        ),
        acceptance_criteria=AcceptanceCriteria(
            target_section_type="drop",
            max_measured_distance=3.0,
            max_embedding_distance=0.8,
            structural_facts={"note_count": 16, "instrument": "Surge XT",
                               "bars": 4},
        ),
        scope_chain=(
            ScopeLink(level="album", summary="A deaf-composed machine-music record."),
            ScopeLink(level="song", summary="High-energy drop-section track."),
            ScopeLink(level="section", summary="The drop's driving bass layer."),
        ),
        body=Leaf(implementation={
            "ops": [
                {"tool": "mcp__deaf_composition__apply_surge_preset",
                 "args": {"track_index": 1, "fx_index": 0,
                          "preset_path": "Basses/Bass 5.fxp",
                          "overrides": {"A Amp EG Release": -1.5,
                                        "A Amp EG Attack": -2.0}}},
                {"tool": "mcp__reaper__create_midi_item",
                 "args": {"track_index": 1, "position": ITEM_POSITION_S, "length": 8}},
                {"tool": "mcp__reaper__add_midi_notes_batch",
                 "args": {"track_index": 1, "item_index": 1,
                          "notes": [{"pitch": p, "velocity": v, "start_beat": b,
                                     "length_beats": NOTE_LEN_BEATS}
                                    for p, v, b in _NOTES_BEATS]}},
                {"tool": "mcp__reaper__render_project",
                 "args": {"output_path": str(WAV), "start_time": ITEM_POSITION_S,
                          "end_time": ITEM_POSITION_S + 8, "tail_seconds": 1,
                          "overwrite": True}},
            ],
        }),
        assigned_model=ModelTier.HAIKU,
    )


def main() -> int:
    node = build_leaf_node()
    print(f"Leaf node: {node.node_id}")
    print(json.dumps(node.to_dict(), indent=2)[:800] + "\n...\n")

    if not WAV.is_file():
        print(f"ERROR: {WAV} not found -- render step didn't happen", file=sys.stderr)
        return 1

    symbolic = hand_supplied_symbolic()
    built = state.build(
        project=WAV,  # no saved .rpp this run (see module docstring) --
                      # sha256'd for provenance, symbolic data is hand-supplied
        wav=WAV,
        symbolic=symbolic,
        region=None,
        embedding=True,
    )
    state_path = WAV.with_suffix(".state.json")
    state.write(built, state_path)
    print(f"state.json written: {state_path}")
    print(f"measured: {json.dumps(built['measured'], indent=2)}")

    library = reference.load_library(LIBRARY)
    ac = node.acceptance_criteria
    score = reference.score_node(built, library, ac.target_section_type)

    measured_dist = score["measured"]["distance"]
    embedding_dist = score["embedding"]["distance"]
    print(f"\nScored against reference envelope: {ac.target_section_type!r}")
    print(f"  measured distance:  {measured_dist:.4f}  (threshold {ac.max_measured_distance})")
    print(f"  embedding distance: {embedding_dist:.4f}  (threshold {ac.max_embedding_distance})")

    own_criteria_met = (
        measured_dist is not None and measured_dist <= ac.max_measured_distance
        and embedding_dist is not None and embedding_dist <= ac.max_embedding_distance
    )
    verdict = "PASS" if own_criteria_met else "FAIL"
    print(f"\nLeaf review (own acceptance criteria only -- no siblings/seams, "
          f"this is a single isolated leaf): {verdict}")

    score_path = WAV.with_suffix(".score.json")
    score_path.write_text(json.dumps(score, indent=2, sort_keys=True) + "\n")
    print(f"score written: {score_path}")
    return 0 if own_criteria_met else 1


if __name__ == "__main__":
    raise SystemExit(main())
