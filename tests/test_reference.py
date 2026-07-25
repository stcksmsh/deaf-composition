"""Reference-library tests: file discovery, stats, and scoring math.

Everything here runs without CLAP or a checkpoint — build_library(embedding=False)
exercises the measured-metric path against synthesized wavs, and the scoring math
is tested against hand-constructed vectors/envelopes.
"""

import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from return_channel import reference  # noqa: E402

SR = 48000


def sine(freq, seconds, amplitude=1.0, sr=SR):
    t = np.arange(int(seconds * sr)) / sr
    return amplitude * np.sin(2 * np.pi * freq * t)


def write_wav(directory, name, samples, sr=SR):
    path = Path(directory) / name
    sf.write(path, samples, sr, subtype="PCM_24")
    return path


class TestIterReferenceFiles(unittest.TestCase):
    def test_section_type_subfolders(self):
        with tempfile.TemporaryDirectory() as tmp:
            for section in ("intro", "drop"):
                d = Path(tmp) / section
                d.mkdir()
                write_wav(d, "a.wav", sine(440, 0.1))
            found = reference.iter_reference_files(tmp)
            self.assertEqual(set(found), {"intro", "drop"})
            self.assertEqual(len(found["intro"]), 1)

    def test_flat_directory_falls_back_to_unlabeled(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_wav(tmp, "a.wav", sine(440, 0.1))
            write_wav(tmp, "b.wav", sine(220, 0.1))
            found = reference.iter_reference_files(tmp)
            self.assertEqual(set(found), {reference.UNLABELED})
            self.assertEqual(len(found[reference.UNLABELED]), 2)

    def test_empty_directory_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(FileNotFoundError):
                reference.iter_reference_files(tmp)

    def test_non_audio_files_are_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "readme.txt").write_text("not audio")
            with self.assertRaises(FileNotFoundError):
                reference.iter_reference_files(tmp)


class TestBuildLibraryMeasuredOnly(unittest.TestCase):
    def test_stats_reflect_the_underlying_levels(self):
        with tempfile.TemporaryDirectory() as tmp:
            drop = Path(tmp) / "drop"
            drop.mkdir()
            write_wav(drop, "loud.wav", sine(1000, 2.0, 0.5))
            write_wav(drop, "quiet.wav", sine(1000, 2.0, 0.05))

            library = reference.build_library(tmp, embedding=False)
            envelope = library["drop"]

            self.assertEqual(envelope["n_tracks"], 2)
            self.assertEqual(envelope["n_tracks_measured"], 2)
            self.assertEqual(envelope["n_windows"], 0)
            self.assertIsNone(envelope["embedding_centroid"])

            lufs = envelope["measured_stats"]["lufs"]
            self.assertEqual(lufs["n"], 2)
            # A 20dB amplitude spread should show up as roughly that much spread.
            self.assertAlmostEqual(lufs["max"] - lufs["min"], 20.0, delta=1.0)

    def test_only_populated_section_types_appear(self):
        with tempfile.TemporaryDirectory() as tmp:
            drop = Path(tmp) / "drop"
            drop.mkdir()
            write_wav(drop, "a.wav", sine(1000, 1.0, 0.3))
            library = reference.build_library(tmp, embedding=False)
            self.assertEqual(list(library), ["drop"])


class TestZscore(unittest.TestCase):
    def test_at_the_mean_is_zero(self):
        self.assertEqual(reference.zscore(5.0, 5.0, 2.0), 0.0)

    def test_symmetric_around_the_mean(self):
        self.assertAlmostEqual(reference.zscore(7.0, 5.0, 2.0), 1.0)
        self.assertAlmostEqual(reference.zscore(3.0, 5.0, 2.0), -1.0)

    def test_zero_std_does_not_divide_by_zero(self):
        # A section type with one reference track has std=0 for every metric;
        # this must not raise or return inf.
        result = reference.zscore(6.0, 5.0, 0.0)
        self.assertTrue(np.isfinite(result))


class TestScoreMeasured(unittest.TestCase):
    def test_on_target_scores_near_zero(self):
        stats = {"lufs": {"mean": -20.0, "std": 2.0},
                 "spectral_centroid": {"mean": 2000.0, "std": 200.0}}
        measured = {"lufs": -20.0, "spectral_centroid": {"median": 2000.0}}
        result = reference.score_measured(measured, stats)
        self.assertAlmostEqual(result["distance"], 0.0)

    def test_off_target_scores_away_from_zero(self):
        stats = {"lufs": {"mean": -20.0, "std": 2.0}}
        measured = {"lufs": -10.0}  # 5 std away
        result = reference.score_measured(measured, stats)
        self.assertAlmostEqual(result["zscores"]["lufs"], 5.0)
        self.assertGreater(result["distance"], 4.9)

    def test_metrics_missing_from_stats_are_skipped_not_raised(self):
        stats = {"lufs": {"mean": -20.0, "std": 2.0}}
        measured = {"lufs": -20.0, "crest_factor": 12.0}  # crest_factor has no stats
        result = reference.score_measured(measured, stats)
        self.assertEqual(set(result["zscores"]), {"lufs"})

    def test_no_overlapping_metrics_returns_none_distance(self):
        result = reference.score_measured({"crest_factor": 12.0}, {"lufs": {"mean": 0, "std": 1}})
        self.assertIsNone(result["distance"])


class TestScoreEmbedding(unittest.TestCase):
    def test_identical_vector_is_nearly_zero_distance(self):
        vector = [1.0, 0.0, 0.0, 0.0]
        envelope = {"embedding_vectors": [vector], "embedding_centroid": vector}
        result = reference.score_embedding([vector], envelope)
        self.assertAlmostEqual(result["nearest_cosine"], 1.0, places=5)
        self.assertAlmostEqual(result["distance"], 0.0, places=5)

    def test_orthogonal_vector_is_maximally_distant(self):
        envelope = {"embedding_vectors": [[1.0, 0.0]], "embedding_centroid": [1.0, 0.0]}
        result = reference.score_embedding([[0.0, 1.0]], envelope)
        self.assertAlmostEqual(result["nearest_cosine"], 0.0, places=5)
        self.assertAlmostEqual(result["distance"], 1.0, places=5)

    def test_nearest_window_beats_centroid_for_an_outlier_reference(self):
        # A leaf near one specific reference moment should score close via
        # nearest-window even if the reference set's centroid is far away —
        # this is the whole point of not scoring against a pooled reference.
        near, far = [1.0, 0.0], [-1.0, 0.0]
        envelope_vectors = [near, far]
        centroid = list(np.mean([near, far], axis=0))  # ~[0, 0], uninformative
        envelope = {"embedding_vectors": envelope_vectors, "embedding_centroid": centroid}
        result = reference.score_embedding([near], envelope)
        self.assertAlmostEqual(result["nearest_cosine"], 1.0, places=5)
        self.assertLess(result["centroid_cosine"], 0.5)

    def test_empty_envelope_returns_none(self):
        result = reference.score_embedding([[1.0, 0.0]], {"embedding_vectors": []})
        self.assertIsNone(result["distance"])


class TestScoreNode(unittest.TestCase):
    def test_prefers_embedding_windows_over_pooled(self):
        library = {"drop": {
            "measured_stats": {"lufs": {"mean": -20.0, "std": 2.0}},
            "embedding_vectors": [[0.0, 1.0]],
            "embedding_centroid": [0.0, 1.0],
        }}
        state = {"measured": {"lufs": -20.0},
                "embedding": [1.0, 0.0],           # pooled: would score as orthogonal
                "embedding_windows": [[0.0, 1.0]]}  # per-window: matches exactly
        result = reference.score_node(state, library, "drop")
        self.assertAlmostEqual(result["embedding"]["nearest_cosine"], 1.0, places=5)

    def test_falls_back_to_pooled_when_windows_absent(self):
        library = {"drop": {
            "measured_stats": {},
            "embedding_vectors": [[1.0, 0.0]],
            "embedding_centroid": [1.0, 0.0],
        }}
        state = {"measured": {}, "embedding": [1.0, 0.0], "embedding_windows": None}
        result = reference.score_node(state, library, "drop")
        self.assertAlmostEqual(result["embedding"]["nearest_cosine"], 1.0, places=5)

    def test_unknown_section_type_raises(self):
        with self.assertRaises(KeyError):
            reference.score_node({"measured": {}}, {"drop": {}}, "intro")


class TestLibraryRoundtrip(unittest.TestCase):
    def test_save_and_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            drop = Path(tmp) / "drop"
            drop.mkdir()
            write_wav(drop, "a.wav", sine(1000, 1.0, 0.3))
            library = reference.build_library(tmp, embedding=False)

            out = Path(tmp) / "library.json"
            reference.save_library(library, out)
            reloaded = reference.load_library(out)
            self.assertEqual(reloaded, library)


if __name__ == "__main__":
    unittest.main()
