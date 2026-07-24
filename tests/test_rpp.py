"""Regression tests against the known ground truth of the experiments/exp2 fixtures.

Note ground truth comes from build_test_project.lua's add_midi_notes(tr, 0, 36, 12):
12 notes, pitch = 55 + ((i*3) % 12), velocity 90, start i*960 ticks, length 864 ticks.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from return_channel import rpp  # noqa: E402

FIXTURES = Path(__file__).resolve().parents[1] / "experiments" / "exp2"


def symbolic(name):
    return rpp.extract_symbolic(rpp.parse_file(FIXTURES / name))


class TestTokenizer(unittest.TestCase):
    def test_double_quoted(self):
        self.assertEqual(rpp.tokenize('NAME "KICK BUSS"'), ["NAME", "KICK BUSS"])

    def test_single_quoted_empty_string(self):
        # AUXRECV lines end in '' — a double-quote-only tokenizer mis-parses them.
        self.assertEqual(rpp.tokenize("AUXRECV -1:U 4177951 -1 ''"),
                         ["AUXRECV", "-1:U", "4177951", "-1", ""])

    def test_composite_tokens_survive(self):
        line = '<VST "VST3i: Surge XT (2->6ch)" "Surge XT.vst3" 0 "" 661331015{ABCD} ""'
        self.assertEqual(rpp.tokenize(line[1:]),
                         ["VST", "VST3i: Surge XT (2->6ch)", "Surge XT.vst3", "0", "",
                          "661331015{ABCD}", ""])


class TestNativeShort(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s = symbolic("native_short.RPP")

    def test_project_header(self):
        self.assertEqual(self.s["tempo"], 120.0)
        self.assertEqual(self.s["time_sig"], [4, 4])
        self.assertEqual(self.s["sample_rate"], 48000)
        self.assertEqual(self.s["bounds"]["selection"], {"start": 0.0, "end": 18.0})

    def test_is_not_a_single_track_project(self):
        # PROJECT_BRIEF.md calls this a single ReaSynth track; it is the author's
        # 18-track default template with NativeSynth appended.
        self.assertEqual(len(self.s["tracks"]), 18)
        self.assertEqual(self.s["tracks"][0]["name"], "KICK BUSS")
        self.assertEqual(self.s["tracks"][-1]["name"], "NativeSynth")

    def test_native_synth_notes(self):
        notes = [n for n in self.s["notes"] if n["track"] == "NativeSynth"]
        self.assertEqual(len(notes), 12)
        self.assertEqual([n["pitch"] for n in notes],
                         [55, 58, 61, 64, 55, 58, 61, 64, 55, 58, 61, 64])
        self.assertEqual([n["velocity"] for n in notes], [90] * 12)
        self.assertEqual([n["start_ticks"] for n in notes], [i * 960 for i in range(12)])
        self.assertEqual([n["end_ticks"] - n["start_ticks"] for n in notes], [864] * 12)
        for i, note in enumerate(notes):
            self.assertAlmostEqual(note["start_s"], i * 0.5, places=9)
            self.assertAlmostEqual(note["end_s"] - note["start_s"], 0.45, places=9)

    def test_lowercase_event_lines_are_not_dropped(self):
        # The Generator item uses lowercase `e` events; NativeSynth uses uppercase `E`.
        notes = [n for n in self.s["notes"] if n["track"] == "Generator"]
        self.assertEqual(len(notes), 4)
        self.assertEqual([n["pitch"] for n in notes], [24] * 4)
        self.assertEqual([n["velocity"] for n in notes], [127] * 4)
        self.assertEqual(len(self.s["notes"]), 16)

    def test_main_send_alone_does_not_mean_inaudible(self):
        # Generator has MAINSEND 0, but it sits inside the KICK BUSS folder
        # (ISBUS 1 1 opens, Click's ISBUS 2 -1 closes), so its audio still
        # reaches master through the parent bus. Routing needs both fields.
        by_name = {t["name"]: t for t in self.s["tracks"]}
        self.assertFalse(by_name["Generator"]["main_send"])
        self.assertEqual(by_name["Generator"]["folder_depth"], 1)

        self.assertTrue(by_name["KICK BUSS"]["is_folder"])
        self.assertEqual(by_name["KICK BUSS"]["folder_depth"], 0)

        # NativeSynth is top-level with a direct send: unambiguously audible.
        self.assertTrue(by_name["NativeSynth"]["main_send"])
        self.assertEqual(by_name["NativeSynth"]["folder_depth"], 0)

    def test_folder_depth_closes_correctly(self):
        by_name = {t["name"]: t for t in self.s["tracks"]}
        for inside in ("Generator", "Low", "Mid", "Click"):
            self.assertEqual(by_name[inside]["folder_depth"], 1, inside)
        # Click closes the folder, so the next track is back at top level.
        self.assertEqual(by_name["DRUM BUSS"]["folder_depth"], 0)

    def test_fx_extraction(self):
        native = [f for f in self.s["fx"] if f["track"] == "NativeSynth"]
        self.assertEqual(len(native), 1)
        self.assertEqual(native[0]["name"], "VSTi: ReaSynth (Cockos)")
        self.assertEqual(native[0]["binary"], "reasynth.vst.so")
        self.assertIsNone(native[0]["params"])

        master = [f["name"] for f in self.s["fx"] if f["track"] == "<master>"]
        self.assertEqual(master, ["VST: ReaEQ (Cockos)", "loser/Saturation",
                                  "utility/volume", "sstillwell/eventhorizon2"])

    def test_js_params_are_readable(self):
        js = {f["name"]: f["params"] for f in self.s["fx"] if f["type"] == "JS"}
        self.assertEqual(js["utility/volume"], [-6.0, 0.0])
        self.assertEqual(js["guitar/distortion"], [9.0, 6.0, -6.0, 2.0])

    def test_render_config_is_whole_project(self):
        self.assertEqual(self.s["bounds"]["render"]["bounds"], rpp.BOUNDS_PROJECT)
        self.assertFalse(self.s["bounds"]["render"]["batches_regions"])


class TestRegionsAndRenderConfig(unittest.TestCase):
    def test_batch_regions(self):
        s = symbolic("batch_regions.RPP")
        regions = s["bounds"]["regions"]
        self.assertEqual([r["name"] for r in regions],
                         ["leaf_0", "leaf_1", "leaf_2", "leaf_3", "leaf_4"])
        self.assertEqual([r["start"] for r in regions], [0.0, 20.0, 40.0, 60.0, 80.0])
        self.assertEqual([r["end"] for r in regions], [15.0, 35.0, 55.0, 75.0, 95.0])

    def test_batch_render_mode_is_detected(self):
        render = symbolic("batch_regions.RPP")["bounds"]["render"]
        self.assertEqual(render["bounds"], rpp.BOUNDS_REGIONS)
        self.assertIn("$region", render["pattern"])
        self.assertTrue(render["batches_regions"])

    def test_twenty_regions(self):
        self.assertEqual(len(symbolic("batch_regions_20.RPP")["bounds"]["regions"]), 20)


class TestAutomation(unittest.TestCase):
    def test_cutoff_envelope(self):
        # build_Test_project_2.lua inserts points at (0, 0.1), (9, 0.9), (18, 0.3).
        envelopes = symbolic("heavy_patch_short.RPP")["automation"]
        self.assertEqual(len(envelopes), 1)
        self.assertEqual(envelopes[0]["name"],
                         "A Filter Configuration / Surge XT / A Common")
        self.assertEqual([(p["time"], p["value"]) for p in envelopes[0]["points"]],
                         [(0.0, 0.1), (9.0, 0.9), (18.0, 0.3)])


class TestAllFixturesParse(unittest.TestCase):
    def test_every_fixture(self):
        for path in sorted(FIXTURES.glob("*.RPP")):
            with self.subTest(path.name):
                s = symbolic(path.name)
                self.assertGreater(len(s["tracks"]), 0)
                self.assertEqual(s["tempo"], 120.0)


if __name__ == "__main__":
    unittest.main()
