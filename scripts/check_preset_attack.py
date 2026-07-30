#!/usr/bin/env python3
"""
Live attack-time pre-flight check (task #1 from memory.md's "Next" list,
2026-07-26): documents the exact live-REAPER steps to test one Surge preset's
attack behavior, for the controlling MCP-capable session to run -- same
"script documents the plan, the session executes it" pattern as every other
live check in this project (backbone_round5_review.py, fold_proof.py, etc.).
No standalone REAPER client exists outside an MCP session, so this can't run
itself; `plan_attack_test()` is what a session runs, `analyze_attack_test()`
is what it calls afterward on the rendered wav.

Why this exists: 3 independent leaves this session (a pad-type pulse leaf,
Percussion/Verber.fxp, Percussion/Synth Tom 2.fxp) all rendered as
near-total silence because their category name ("Percussion") didn't match
their actual envelope shape (all three were slow-attack pad/riser patches).
Measuring attack time directly, once per preset, from one long test note
closes that gap -- see src/planner/preset_attack.py's module docstring for
the full data (Synth Tom 2.fxp: ~1.0-1.1s attack, confirmed too slow for any
note under ~2 beats at 120bpm).

TEST_NOTE_BEATS is deliberately long (8 beats = 4s at 120bpm) regardless of
the candidate note length actually being validated -- using a short window
that matches the candidate length was tried first and is WRONG: a truncated
window's own local peak isn't the preset's true plateau, so "reaches 50% of
peak" can trivially pass near the end of a short window even though the
preset is still far from actually audible. Always measure once with a
generously long note, then call attack_ok_for_note_length() for as many
candidate note lengths as needed -- no need to re-render per length.

Usage (run by the controlling session, not standalone):
    1. apply_surge_preset(track_index, fx_index, preset_path)  [MCP tool]
    2. clear_midi_item(track_index, item_index=0)              [MCP tool]
    3. add_midi_notes_batch(track_index, item_index=0,
                             notes=plan_attack_test()["test_note"])  [MCP tool]
    4. solo the track, render_project(...) over the test note's time range,
       unsolo                                                  [MCP tools]
    5. analyze_attack_test(wav_path, note_start_s, tempo_bpm) -- prints the
       measured attack time and whether it clears a set of common rhythmic
       note lengths (0.25/0.5/1/2/4 beats)
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from planner.preset_attack import (  # noqa: E402
    attack_ok_for_note_length,
    measure_attack_time,
)

TEST_NOTE_BEATS = 8.0
TEST_PITCH = 60
TEST_VELOCITY = 100

# The candidate note lengths (in beats) a leaf-emission pass might actually
# use for a rhythmic part -- report pass/fail against each so the caller can
# see exactly where the cutoff is, not just a single yes/no.
CANDIDATE_NOTE_LENGTHS_BEATS = (0.25, 0.5, 1.0, 2.0, 4.0)


def plan_attack_test(tempo_bpm: float = 120.0) -> dict:
    """What the controlling session needs to set up one live attack test."""
    return {
        "test_note": [{
            "pitch": TEST_PITCH,
            "velocity": TEST_VELOCITY,
            "start_beat": 0.0,
            "length_beats": TEST_NOTE_BEATS,
        }],
        "note_start_s": 0.0,
        "test_window_s": TEST_NOTE_BEATS * 60.0 / tempo_bpm,
    }


def analyze_attack_test(wav_path: str, preset_path: str, tempo_bpm: float = 120.0) -> dict:
    """Run after the live render -- prints and returns the verdict for each
    candidate note length, given one measurement from the long test note."""
    plan = plan_attack_test(tempo_bpm)
    measurement = measure_attack_time(wav_path, note_start_s=plan["note_start_s"],
                                       note_dur_s=plan["test_window_s"])

    print(f"=== attack test: {preset_path} ===")
    print(f"  peak_db={measurement.peak_db}, attack_time_s={measurement.attack_time_s}")

    results = {}
    for beats in CANDIDATE_NOTE_LENGTHS_BEATS:
        ok, reason = attack_ok_for_note_length(measurement, beats, tempo_bpm=tempo_bpm)
        results[beats] = {"ok": ok, "reason": reason}
        note_s = beats * 60.0 / tempo_bpm
        print(f"  {beats:>4} beats ({note_s:.3f}s): {'OK  ' if ok else 'FAIL'} -- {reason}")

    return {
        "preset_path": preset_path,
        "measurement": {"peak_db": measurement.peak_db, "attack_time_s": measurement.attack_time_s},
        "results": results,
    }


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("usage: check_preset_attack.py <wav_path> <preset_path> [tempo_bpm]")
        raise SystemExit(1)
    tempo = float(sys.argv[3]) if len(sys.argv) > 3 else 120.0
    analyze_attack_test(sys.argv[1], sys.argv[2], tempo)
