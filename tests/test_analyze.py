"""Metric tests against synthesized signals with analytically known properties."""

import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from return_channel import analyze  # noqa: E402

SR = 48000


def write_wav(tmpdir, name, samples, sr=SR):
    path = Path(tmpdir) / name
    sf.write(path, samples, sr, subtype="PCM_24")
    return path


def sine(freq, seconds, amplitude=1.0, sr=SR):
    t = np.arange(int(seconds * sr)) / sr
    return amplitude * np.sin(2 * np.pi * freq * t)


class TestMeasure(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def test_full_scale_sine(self):
        path = write_wav(self.tmp, "sine.wav", sine(1000, 5.0, 0.5))
        m = analyze.measure(path)

        self.assertAlmostEqual(m["sample_peak"], -6.02, places=1)
        # A sine's crest factor is sqrt(2) -> 3.01 dB, independent of level.
        self.assertAlmostEqual(m["crest_factor"], 3.01, places=1)
        self.assertAlmostEqual(m["spectral_centroid"]["median"], 1000, delta=30)
        self.assertLess(m["spectral_flatness"]["median"], 0.01)
        self.assertEqual(m["audio"]["sample_rate"], SR)
        self.assertAlmostEqual(m["audio"]["duration_s"], 5.0, places=3)

    def test_level_tracks_lufs(self):
        loud = analyze.measure(write_wav(self.tmp, "loud.wav", sine(1000, 3.0, 0.5)))
        quiet = analyze.measure(write_wav(self.tmp, "quiet.wav", sine(1000, 3.0, 0.05)))
        # A 20 dB amplitude drop is a 20 dB LUFS drop.
        self.assertAlmostEqual(loud["lufs"] - quiet["lufs"], 20.0, places=1)

    def test_white_noise_is_flat_and_bright(self):
        rng = np.random.default_rng(0)
        noise = rng.normal(0, 0.1, SR * 3)
        m = analyze.measure(write_wav(self.tmp, "noise.wav", noise))

        self.assertGreater(m["spectral_flatness"]["median"], 0.5)
        self.assertAlmostEqual(m["spectral_centroid"]["median"], SR / 4, delta=SR / 20)

    def test_true_peak_exceeds_sample_peak_on_intersample_content(self):
        # A 1/4-Nyquist sine sampled off-crest peaks between samples.
        m = analyze.measure(write_wav(self.tmp, "tp.wav", sine(SR / 4 - 1, 2.0, 0.9)))
        self.assertGreater(m["true_peak"], m["sample_peak"])

    def test_silence_gate_ignores_the_tail(self):
        # Reproduces native_short's shape: signal for 6s of an 18s stem.
        signal = np.concatenate([sine(1000, 6.0, 0.5), np.zeros(12 * SR)])
        m = analyze.measure(write_wav(self.tmp, "tail.wav", signal))

        self.assertAlmostEqual(m["active_ratio"], 6 / 18, delta=0.02)
        self.assertTrue(any("silence gate" in w for w in m["warnings"]))
        # Gated, the centroid still reads the tone rather than the silence.
        self.assertAlmostEqual(m["spectral_centroid"]["median"], 1000, delta=30)

    def test_digital_silence(self):
        m = analyze.measure(write_wav(self.tmp, "mute.wav", np.zeros(SR)))
        self.assertIsNone(m["lufs"])
        self.assertIsNone(m["crest_factor"])
        self.assertTrue(m["warnings"])

    def test_stereo_is_preserved(self):
        stereo = np.stack([sine(1000, 2.0, 0.5), sine(2000, 2.0, 0.5)], axis=1)
        m = analyze.measure(write_wav(self.tmp, "stereo.wav", stereo))
        self.assertEqual(m["audio"]["channels"], 2)


if __name__ == "__main__":
    unittest.main()
