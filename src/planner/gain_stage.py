"""Prominence-aware gain staging (2026-07-29) -- generalizes the ad hoc fix
applied by hand to "Tidal Lock" v4->v5: three separate "quiet/buried"
complaints across three different sections all traced to the same root
cause, confirmed with real measurements, not guessed. Every leaf this
project has ever built left its track fader at flat 0dB regardless of how
loud its Surge preset renders natively -- some presets are structurally
much hotter than others (a plucked/percussive patch vs. a thin pad), so
that raw preset-loudness spread governed the final mix instead of musical
intent. The three fixed leaves' solo-render RMS sat 14-22dB below their
section's full mix -- essentially inaudible -- while the one leaf the user
said was correctly prominent sat only 2dB below.

Deliberately NOT "normalize everything to the same loudness" -- explicit
user correction (2026-07-29) on the first draft of this idea: a background
texture is SUPPOSED to sit quieter than a lead, that's the point of it
being background. The fix is target BANDS per node.py's `prominence`
field (foreground/midground/background), not a single uniform target --
decompose.py's own role assignment governs how present a leaf should be,
not an accident of which preset happened to render hot.

Measurement method (validated 2026-07-29 against the real "Tidal Lock"
render, not assumed): solo-render the leaf's own track over its section's
time window, compare its RMS (dB) against the SAME window's RMS in the
existing full-mix render. The gap (mix_rms_db - solo_rms_db) is how many
dB quieter the leaf sits than the section as a whole. That night's manual
fix additionally validated the fix mattered (not just "a number changed")
by diffing the before/after full-mix renders sample-by-sample and
confirming the diff signal's own RMS was comparable to or louder than the
entire prior mix at that moment -- worth doing again whenever this module's
corrections are applied for real, not just trusting the fader math.

This module is decision-only, same division of labor as mix_fix.py's
propose_composition_fix: it turns two measured RMS numbers into a proposed
`set_track_volume` delta. The caller (a live session with real MCP tools)
is responsible for the solo/full-mix renders that produce those numbers,
for applying the delta, and for re-measuring/re-rendering to confirm.
"""
from __future__ import annotations

from dataclasses import dataclass

from planner.node import PROMINENCE_LEVELS

# (low, high) dB gap a solo-rendered leaf should sit below its section's
# full mix, given its intended prominence. Below `low` means the leaf is
# louder than its role calls for (risks crowding out whatever IS supposed
# to be foreground); above `high` means it's buried past the point of being
# a felt presence at all. These bands come directly from tonight's real
# measurements: the confirmed-buried leaves sat 14-22dB below the mix
# (foreground/midground role, clearly past any reasonable band), the
# confirmed-correct one sat 2dB below (foreground). background has no
# real measured anchor yet -- set by extrapolation (roughly double the
# midground band) pending a real background-leaf case; revisit if that
# assumption doesn't hold up against real data.
TARGET_GAP_DB_BANDS: dict[str, tuple[float, float]] = {
    "foreground": (2.0, 8.0),
    "midground": (8.0, 15.0),
    "background": (15.0, 25.0),
}

# A single correction should not try to fix everything in one jump --
# tonight's real fixes used +10/+12dB and that was already a large,
# clearly audible move (confirmed via the diff-RMS check in this module's
# own docstring). Cap higher than that to leave room for a genuinely
# extreme outlier, but flag when a proposal hits the cap rather than
# silently truncating it, so the caller knows the target band wasn't
# actually reached in one pass.
MAX_SINGLE_CORRECTION_DB = 18.0

# REAPER's own track fader range (set_track_volume's documented "typical"
# ceiling is +12dB, but tonight's real +10/+12dB corrections landed fine;
# floor is generous since a background leaf legitimately correct at -20dB
# base level is plausible).
MIN_FADER_DB = -36.0
MAX_FADER_DB = 18.0


@dataclass(frozen=True)
class GainCorrection:
    prominence: str
    measured_gap_db: float          # mix_rms_db - solo_rms_db, as measured
    target_band_db: tuple[float, float]
    delta_db: float                 # proposed change to the current fader
    new_fader_db: float             # current_fader_db + delta_db, clamped
    hit_correction_cap: bool        # True if delta_db was clamped to MAX_SINGLE_CORRECTION_DB
    hit_fader_limit: bool           # True if new_fader_db was clamped to [MIN_FADER_DB, MAX_FADER_DB]


def propose_gain_correction(prominence: str, solo_rms_db: float, mix_rms_db: float,
                             current_fader_db: float = 0.0) -> GainCorrection | None:
    """Returns None if the leaf already sits within its prominence tier's
    target band (no correction needed -- this is the common case for a
    healthy mix, not a sign the function did nothing). Otherwise returns
    the proposed `set_track_volume` delta needed to bring it to the
    NEAREST edge of the band (not the band's center -- a minimal correction,
    consistent with "only fix what's actually broken")."""
    if prominence not in PROMINENCE_LEVELS:
        raise ValueError(f"prominence must be one of {PROMINENCE_LEVELS}, got {prominence!r}")

    low, high = TARGET_GAP_DB_BANDS[prominence]
    gap = mix_rms_db - solo_rms_db

    if low <= gap <= high:
        return None

    # gap > high: leaf is too quiet (buried) -- needs a boost (positive delta).
    # gap < low: leaf is too loud for its intended role -- needs a cut (negative delta).
    raw_delta = (gap - high) if gap > high else (gap - low)

    hit_cap = abs(raw_delta) > MAX_SINGLE_CORRECTION_DB
    delta = max(-MAX_SINGLE_CORRECTION_DB, min(MAX_SINGLE_CORRECTION_DB, raw_delta))

    raw_new_fader = current_fader_db + delta
    hit_limit = not (MIN_FADER_DB <= raw_new_fader <= MAX_FADER_DB)
    new_fader = max(MIN_FADER_DB, min(MAX_FADER_DB, raw_new_fader))

    return GainCorrection(
        prominence=prominence,
        measured_gap_db=gap,
        target_band_db=(low, high),
        delta_db=delta,
        new_fader_db=new_fader,
        hit_correction_cap=hit_cap,
        hit_fader_limit=hit_limit,
    )
