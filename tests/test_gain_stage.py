"""Tests for src/planner/gain_stage.py -- the prominence-aware, band-based
(not flat-normalize) gain correction built 2026-07-29 from real "Tidal
Lock" measurements."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from planner import gain_stage  # noqa: E402


class TestWithinBand(unittest.TestCase):
    def test_foreground_within_band_needs_no_correction(self):
        # gap=5dB sits inside foreground's (2, 8) band.
        result = gain_stage.propose_gain_correction("foreground", solo_rms_db=-20.0, mix_rms_db=-15.0)
        self.assertIsNone(result)

    def test_background_within_band_needs_no_correction(self):
        # gap=20dB sits inside background's (15, 25) band -- a quiet
        # texture that's quiet ON PURPOSE should not get boosted.
        result = gain_stage.propose_gain_correction("background", solo_rms_db=-38.0, mix_rms_db=-18.0)
        self.assertIsNone(result)


class TestTooQuiet(unittest.TestCase):
    def test_buried_foreground_gets_boosted_to_band_edge(self):
        # gap=20dB, foreground band high=8 -> needs +12dB to reach the edge.
        result = gain_stage.propose_gain_correction("foreground", solo_rms_db=-35.0, mix_rms_db=-15.0)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result.delta_db, 12.0)
        self.assertAlmostEqual(result.new_fader_db, 12.0)
        self.assertFalse(result.hit_correction_cap)

    def test_real_measured_case_section2_pluck_motif(self):
        # Real numbers from tonight's diagnostic: t12 solo RMS -39.7dB vs.
        # mix window RMS -18.1dB (gap 21.6dB), assigned midground (band
        # 8-15) -- should propose a boost of gap-15 = 6.6dB.
        result = gain_stage.propose_gain_correction("midground", solo_rms_db=-39.7, mix_rms_db=-18.1)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result.delta_db, 6.6, places=1)


class TestTooLoud(unittest.TestCase):
    def test_overprominent_background_gets_cut(self):
        # gap=5dB is far too loud for a background role (band 15-25) --
        # needs a cut of gap-15 = -10dB.
        result = gain_stage.propose_gain_correction("background", solo_rms_db=-20.0, mix_rms_db=-15.0)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result.delta_db, -10.0)


class TestClamping(unittest.TestCase):
    def test_correction_cap_applied_and_flagged(self):
        # gap=48dB, foreground high=8 -> raw delta would be 40dB, clamped
        # to MAX_SINGLE_CORRECTION_DB.
        result = gain_stage.propose_gain_correction("foreground", solo_rms_db=-63.0, mix_rms_db=-15.0)
        self.assertTrue(result.hit_correction_cap)
        self.assertAlmostEqual(result.delta_db, gain_stage.MAX_SINGLE_CORRECTION_DB)

    def test_fader_limit_applied_and_flagged(self):
        result = gain_stage.propose_gain_correction(
            "foreground", solo_rms_db=-35.0, mix_rms_db=-15.0, current_fader_db=10.0
        )
        # delta=+12, current=10 -> raw new fader 22, above MAX_FADER_DB (18).
        self.assertTrue(result.hit_fader_limit)
        self.assertEqual(result.new_fader_db, gain_stage.MAX_FADER_DB)


class TestValidation(unittest.TestCase):
    def test_unknown_prominence_raises(self):
        with self.assertRaises(ValueError):
            gain_stage.propose_gain_correction("extremely loud", solo_rms_db=-20.0, mix_rms_db=-15.0)


if __name__ == "__main__":
    unittest.main()
