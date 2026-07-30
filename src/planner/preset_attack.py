"""Attack-time pre-flight check for preset selection -- built after three
independent real failures this session (the original pad-type pulse leaf,
Percussion/Verber.fxp, Percussion/Synth Tom 2.fxp) all turned out to be the
same bug: a preset's *category* name is not a reliable signal of its
envelope shape in this factory library. All three were slow-attack
pad/riser-style patches that rendered as near-total silence when driven by
short rhythmic MIDI notes, because the note ended before the amplitude
envelope ever ramped up.

Directly measured on Synth Tom 2.fxp (2026-07-26): a single sustained
15-beat note produced normal audio (-24.7 LUFS), but doubling a rhythmic
pattern's note length from 0.25 to 0.5 beats did NOT fix it (still
-91.5dB, essentially silent) -- the preset's actual attack time is ~1.5-2
full seconds, many times longer than any note length a rhythmic part would
plausibly use. That's the real gap this module closes: measure attack time
directly from rendered audio instead of guessing from the preset's category
folder, and reject presets whose attack can't complete within their own
note's length.

This module only does the signal analysis (pure functions, testable
offline against any rendered wav) and the accept/reject decision. Applying
a preset and rendering a test note still requires a live REAPER session --
same pattern as every other live check this project has built (escalation.py,
mix_fix.py): this module decides, the controlling MCP-capable session
executes.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import soundfile as sf

# Amplitude envelope computed as RMS over short hops -- fine enough to
# resolve attack times as short as ~10ms, coarse enough to not be fooled by
# single-sample transients or digital silence noise floor.
_HOP_S = 0.01

# A preset's attack is "too slow" for a given note if it can't reach this
# fraction of its own eventual peak within the note's own length -- i.e. the
# note would end before the preset ever became clearly audible. 0.5 (half
# amplitude) rather than something looser like 0.1: the real Synth Tom 2
# failure was already at -56.9dB (nowhere near half) a full beat into a note
# meant to last a quarter of that -- a loose threshold would have let it
# through.
DEFAULT_THRESHOLD_FRAC = 0.5


@dataclass(frozen=True)
class AttackMeasurement:
    attack_time_s: float | None  # None = never reached threshold_frac of peak
    peak_db: float | None        # None = never audible at all (pure silence)


def measure_attack_time(wav_path: str | Path, note_start_s: float, note_dur_s: float,
                         threshold_frac: float = DEFAULT_THRESHOLD_FRAC) -> AttackMeasurement:
    """Attack time of one note, measured directly from a rendered wav.

    note_start_s/note_dur_s bound the region containing exactly one test
    note (silence before/after it, if any, is fine -- only used to find the
    note's own peak and how long it took to get there)."""
    data, sr = sf.read(str(wav_path), dtype="float64", always_2d=True)
    mono = data.mean(axis=1)

    start_i = int(note_start_s * sr)
    end_i = int((note_start_s + note_dur_s) * sr)
    segment = mono[start_i:end_i]
    if segment.size == 0:
        return AttackMeasurement(attack_time_s=None, peak_db=None)

    hop = max(1, int(_HOP_S * sr))
    n_hops = segment.size // hop
    if n_hops == 0:
        return AttackMeasurement(attack_time_s=None, peak_db=None)
    trimmed = segment[: n_hops * hop].reshape(n_hops, hop)
    envelope = np.sqrt(np.mean(np.square(trimmed), axis=1))

    peak = float(np.max(envelope))
    if peak <= 0:
        return AttackMeasurement(attack_time_s=None, peak_db=None)
    peak_db = float(20 * np.log10(peak))

    reached = np.nonzero(envelope >= threshold_frac * peak)[0]
    if reached.size == 0:
        return AttackMeasurement(attack_time_s=None, peak_db=peak_db)
    attack_time_s = float(reached[0] * _HOP_S)
    return AttackMeasurement(attack_time_s=attack_time_s, peak_db=peak_db)


def attack_ok_for_note_length(measurement: AttackMeasurement, note_length_beats: float,
                               tempo_bpm: float = 120.0,
                               silence_floor_db: float = -50.0) -> tuple[bool, str]:
    """Real gate, derived from the actual failure data: a preset is usable
    for a note of this length only if (a) it's audible at all, and (b) its
    attack completes within that note's own duration -- a note that ends
    before the envelope ramps up produces the exact near-silent-render bug
    this module exists to catch."""
    if measurement.peak_db is None or measurement.peak_db < silence_floor_db:
        return False, "never reaches audible level (near-total silence) within the test window"

    note_length_s = note_length_beats * 60.0 / tempo_bpm
    if measurement.attack_time_s is None:
        return False, (
            f"attack never reaches {DEFAULT_THRESHOLD_FRAC:.0%} of its own peak within "
            f"the measurement window -- attack is far longer than a {note_length_beats}-beat note"
        )
    if measurement.attack_time_s > note_length_s:
        return False, (
            f"attack time {measurement.attack_time_s:.2f}s exceeds the note's own length "
            f"{note_length_s:.2f}s ({note_length_beats} beats at {tempo_bpm:.0f}bpm) -- "
            f"the note would end before this preset becomes clearly audible"
        )
    return True, "attack completes within the note's own length"
