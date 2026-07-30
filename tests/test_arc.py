"""Tests for src/planner/arc.py (plan_arc) and the new
review.review_arc_contrast check -- fake-client/fake-state style, matching
tests/test_pipeline.py's established pattern (duplicated locally rather
than extracted to a shared module, matching that file's own precedent)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from planner import arc, review  # noqa: E402


class _FakeBlock:
    def __init__(self, type_, name=None, input=None):
        self.type = type_
        self.name = name
        self.input = input


class _FakeResponse:
    def __init__(self, content):
        self.content = content


class _FakeMessages:
    def __init__(self, responses):
        self._responses = list(responses)

    def create(self, **kwargs):
        return self._responses.pop(0)


class _FakeClient:
    def __init__(self, responses):
        self.messages = _FakeMessages(responses)


def _section(own_purpose="intro layer", spec="a sparse pad", section_type="intro",
             duration_s=32.0, locked_grid=False, grid_justification=""):
    return {
        "own_purpose": own_purpose,
        "spec": spec,
        "target_section_type": section_type,
        "duration_s": duration_s,
        "locked_grid": locked_grid,
        "grid_justification": grid_justification,
    }


def _element(element_id="lead_motif", description="a recurring lead line",
             section_indices=(0, 2)):
    return {
        "element_id": element_id,
        "description": description,
        "section_indices": list(section_indices),
    }


def _arc_response(sections, recurring_elements=(), tempo_bpm=120.0, time_signature_numerator=4):
    return _FakeResponse([_FakeBlock(
        "tool_use", "plan_arc",
        {
            "sections": sections,
            "recurring_elements": list(recurring_elements),
            "tempo_bpm": tempo_bpm,
            "time_signature_numerator": time_signature_numerator,
        },
    )])


def _state(lufs, centroid=440.0):
    return {
        "measured": {"lufs": lufs, "sample_peak": lufs + 10,
                     "spectral_centroid": {"median": centroid}, "active_ratio": 1.0},
    }


class TestPlanArc(unittest.TestCase):
    def test_returns_validated_sections(self):
        sections = [_section(), _section(section_type="drop", duration_s=20.0)]
        client = _FakeClient([_arc_response(sections)])
        result = arc.plan_arc("a test brief", client)
        self.assertEqual(result["sections"], sections)
        self.assertEqual(result["recurring_elements"], [])

    def test_returns_validated_tempo_and_time_signature(self):
        client = _FakeClient([_arc_response([_section()], tempo_bpm=90.0,
                                             time_signature_numerator=3)])
        result = arc.plan_arc("a test brief", client)
        self.assertEqual(result["tempo_bpm"], 90.0)
        self.assertEqual(result["time_signature_numerator"], 3)

    def test_tempo_out_of_range_is_rejected(self):
        bad = _arc_response([_section()], tempo_bpm=300.0)  # over the 220 ceiling
        good = _arc_response([_section()], tempo_bpm=140.0)
        client = _FakeClient([bad, good])
        result = arc.plan_arc("a test brief", client, retries=1)
        self.assertEqual(result["tempo_bpm"], 140.0)

    def test_time_signature_out_of_range_is_rejected(self):
        bad = _arc_response([_section()], time_signature_numerator=12)  # over the 7 ceiling
        client = _FakeClient([bad, bad])
        with self.assertRaises(RuntimeError):
            arc.plan_arc("a test brief", client, retries=1)

    def test_stringified_tempo_is_coerced(self):
        client = _FakeClient([_arc_response([_section()], tempo_bpm="128")])
        result = arc.plan_arc("a test brief", client)
        self.assertEqual(result["tempo_bpm"], 128.0)

    def test_recovers_json_string_sections(self):
        sections = [_section()]
        import json
        client = _FakeClient([_arc_response(json.dumps({"sections": sections}))])
        result = arc.plan_arc("a test brief", client)
        self.assertEqual(result["sections"], sections)

    def test_recovers_leaked_parameter_tag(self):
        import json
        sections = [_section()]
        leaked = '\n<parameter name="sections">' + json.dumps(sections)
        client = _FakeClient([_arc_response(leaked)])
        result = arc.plan_arc("a test brief", client)
        self.assertEqual(result["sections"], sections)

    def test_retries_then_raises(self):
        bad = _arc_response([])  # zero sections is invalid
        client = _FakeClient([bad, bad, bad])
        with self.assertRaises(RuntimeError):
            arc.plan_arc("a test brief", client, retries=2)
        self.assertEqual(len(client.messages._responses), 0)  # all 3 attempts consumed

    def test_rejects_locked_grid_without_justification(self):
        bad = _arc_response([_section(locked_grid=True, grid_justification="")])
        good_sections = [_section(locked_grid=True, grid_justification="hypnotic groove")]
        good = _arc_response(good_sections)
        client = _FakeClient([bad, good])
        result = arc.plan_arc("a test brief", client, retries=1)
        self.assertEqual(result["sections"], good_sections)

    def test_rejects_non_positive_duration(self):
        bad = _arc_response([_section(duration_s=0)])
        client = _FakeClient([bad])
        with self.assertRaises(RuntimeError):
            arc.plan_arc("a test brief", client, retries=0)

    def test_returns_validated_recurring_elements(self):
        sections = [_section(), _section(section_type="drop", duration_s=20.0)]
        elements = [_element(section_indices=(0, 1))]
        client = _FakeClient([_arc_response(sections, elements)])
        result = arc.plan_arc("a test brief", client)
        self.assertEqual(result["recurring_elements"], elements)

    def test_rejects_element_with_only_one_occurrence(self):
        sections = [_section(), _section(section_type="drop", duration_s=20.0)]
        bad = _arc_response(sections, [_element(section_indices=(0,))])
        client = _FakeClient([bad])
        with self.assertRaises(RuntimeError):
            arc.plan_arc("a test brief", client, retries=0)

    def test_rejects_out_of_range_section_index(self):
        sections = [_section(), _section(section_type="drop", duration_s=20.0)]
        bad = _arc_response(sections, [_element(section_indices=(0, 5))])
        client = _FakeClient([bad])
        with self.assertRaises(RuntimeError):
            arc.plan_arc("a test brief", client, retries=0)

    def test_rejects_duplicate_element_id(self):
        sections = [_section(), _section(section_type="drop", duration_s=20.0)]
        bad = _arc_response(sections, [
            _element(element_id="a", section_indices=(0, 1)),
            _element(element_id="a", section_indices=(0, 1)),
        ])
        client = _FakeClient([bad])
        with self.assertRaises(RuntimeError):
            arc.plan_arc("a test brief", client, retries=0)


class TestReviewArcContrast(unittest.TestCase):
    def test_flags_two_adjacent_sections_too_similar(self):
        result = review.review_arc_contrast([_state(-15, 440), _state(-14, 450)])
        self.assertEqual(result.status.value, "failed")
        self.assertTrue(any("section[1]" in r and "section[0]" in r for r in result.reasons))

    def test_passes_with_real_loudness_contrast(self):
        result = review.review_arc_contrast([_state(-15, 440), _state(-5, 450)])
        self.assertEqual(result.status.value, "passed")

    def test_passes_with_real_timbral_contrast(self):
        result = review.review_arc_contrast([_state(-15, 200), _state(-14, 900)])
        self.assertEqual(result.status.value, "passed")

    def test_flags_back_and_forth_aba_via_n_minus_2_leg(self):
        states = [_state(-15, 440), _state(-5, 900), _state(-15, 440)]
        result = review.review_arc_contrast(states, labels=["A", "B", "A2"])
        self.assertEqual(result.status.value, "failed")
        self.assertTrue(any("A2" in r and "A" in r for r in result.reasons))
        self.assertIn((2, 0), result.metrics["insufficient_pairs"])

    def test_two_sections_only_checks_the_one_available_pair(self):
        result = review.review_arc_contrast([_state(-15, 440), _state(-14, 450)])
        self.assertEqual(result.metrics["pairs_checked"], 1)

    def test_metrics_populated_on_pass(self):
        result = review.review_arc_contrast([_state(-15, 440), _state(-5, 450)])
        self.assertEqual(result.status.value, "passed")
        self.assertIsNotNone(result.metrics["worst_gap_db"])
        self.assertIsNotNone(result.metrics["worst_centroid_ratio"])
        self.assertEqual(result.metrics["pairs_checked"], 1)


if __name__ == "__main__":
    unittest.main()
