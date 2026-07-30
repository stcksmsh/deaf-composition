"""Tests for src/planner/decompose.py's recurring-element additions
(2026-07-27): realizes_element_id defaulting/validation and recurring_context
being threaded into the prompt -- fake-client style matching
tests/test_arc.py / tests/test_pipeline.py's established pattern."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from planner import decompose  # noqa: E402
from planner.node import AcceptanceCriteria, Node, ScopeLink, Split  # noqa: E402


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
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self._responses.pop(0)


class _FakeClient:
    def __init__(self, responses):
        self.messages = _FakeMessages(responses)


def _child(own_purpose="a layer", spec="do something", is_leaf=True, realizes_element_id=None):
    d = {"own_purpose": own_purpose, "spec": spec, "is_leaf": is_leaf}
    if realizes_element_id is not None:
        d["realizes_element_id"] = realizes_element_id
    return d


def _decompose_response(children):
    return _FakeResponse([_FakeBlock("tool_use", "decompose", {"children": children})])


def make_node():
    return Node(
        node_id="song/section_1",
        own_purpose="a build section",
        spec="rising energy",
        acceptance_criteria=AcceptanceCriteria(structural_facts={}),
        scope_chain=(ScopeLink(level="album", summary="x"),),
        body=Split(children=()),
    )


class TestRealizesElementId(unittest.TestCase):
    def test_defaults_to_empty_string_when_absent(self):
        children = [_child(), _child(is_leaf=False)]
        client = _FakeClient([_decompose_response(children)])
        result = decompose.decompose(make_node(), client, duration_s=40.0)
        self.assertEqual([c["realizes_element_id"] for c in result], ["", ""])

    def test_preserves_a_real_tag(self):
        children = [_child(realizes_element_id="lead_motif"), _child(is_leaf=False)]
        client = _FakeClient([_decompose_response(children)])
        result = decompose.decompose(make_node(), client, duration_s=40.0)
        self.assertEqual(result[0]["realizes_element_id"], "lead_motif")

    def test_blank_string_normalizes_to_empty(self):
        children = [_child(realizes_element_id="   "), _child(is_leaf=False)]
        client = _FakeClient([_decompose_response(children)])
        result = decompose.decompose(make_node(), client, duration_s=40.0)
        self.assertEqual(result[0]["realizes_element_id"], "")


class TestProminence(unittest.TestCase):
    def test_preserves_a_valid_value(self):
        children = [_child(), _child(is_leaf=False)]
        children[0]["prominence"] = "foreground"
        client = _FakeClient([_decompose_response(children)])
        result = decompose.decompose(make_node(), client, duration_s=40.0)
        self.assertEqual(result[0]["prominence"], "foreground")

    def test_missing_defaults_to_midground(self):
        children = [_child(), _child(is_leaf=False)]
        client = _FakeClient([_decompose_response(children)])
        result = decompose.decompose(make_node(), client, duration_s=40.0)
        self.assertEqual(result[0]["prominence"], "midground")

    def test_invalid_value_defaults_to_midground_rather_than_failing(self):
        children = [_child(), _child(is_leaf=False)]
        children[0]["prominence"] = "extremely loud"
        client = _FakeClient([_decompose_response(children)])
        result = decompose.decompose(make_node(), client, duration_s=40.0)
        self.assertEqual(result[0]["prominence"], "midground")


class TestRetryFeedback(unittest.TestCase):
    """2026-07-29, live failure: decompose() previously retried with the
    IDENTICAL prompt every attempt -- a real live run got 'children' back
    as None 3 times in a row with no variation, which a blind retry has no
    mechanism to recover from. Now mirrors leaf_emit.py's escalating-
    feedback pattern."""

    def test_children_none_retries_with_feedback_and_succeeds(self):
        bad_response = _decompose_response(None)
        good_children = [_child(), _child(is_leaf=False)]
        good_response = _decompose_response(good_children)
        client = _FakeClient([bad_response, good_response])
        result = decompose.decompose(make_node(), client, duration_s=40.0, retries=1)
        self.assertEqual(len(result), 2)
        # second call's prompt must differ from the first (real feedback,
        # not a repeated identical request)
        first_prompt = client.messages.calls[0]["messages"][0]["content"]
        second_prompt = client.messages.calls[1]["messages"][0]["content"]
        self.assertNotEqual(first_prompt, second_prompt)
        self.assertIn("previous attempt", second_prompt)

    def test_exhausting_retries_on_persistent_none_raises(self):
        bad_response = _decompose_response(None)
        client = _FakeClient([bad_response, bad_response])
        with self.assertRaises(RuntimeError):
            decompose.decompose(make_node(), client, duration_s=40.0, retries=1)


class TestForceLeaf(unittest.TestCase):
    def test_coerces_is_leaf_true_even_when_model_said_false(self):
        children = [_child(is_leaf=False), _child(is_leaf=False)]
        client = _FakeClient([_decompose_response(children)])
        result = decompose.decompose(make_node(), client, duration_s=40.0, force_leaf=True)
        self.assertTrue(all(c["is_leaf"] for c in result))

    def test_prompt_states_the_hard_requirement(self):
        children = [_child(is_leaf=False), _child(is_leaf=False)]
        client = _FakeClient([_decompose_response(children)])
        decompose.decompose(make_node(), client, duration_s=40.0, force_leaf=True)
        prompt = client.messages.calls[0]["messages"][0]["content"]
        self.assertIn("MUST be is_leaf=true", prompt)

    def test_no_force_leaf_language_when_false(self):
        children = [_child(is_leaf=True), _child(is_leaf=False)]
        client = _FakeClient([_decompose_response(children)])
        decompose.decompose(make_node(), client, duration_s=40.0, force_leaf=False)
        prompt = client.messages.calls[0]["messages"][0]["content"]
        self.assertNotIn("MUST be is_leaf=true", prompt)


class TestRecurringContextPrompt(unittest.TestCase):
    def test_no_context_means_no_recurring_block_in_prompt(self):
        children = [_child(), _child(is_leaf=False)]
        client = _FakeClient([_decompose_response(children)])
        decompose.decompose(make_node(), client, duration_s=40.0, recurring_context=None)
        prompt = client.messages.calls[0]["messages"][0]["content"]
        self.assertNotIn("recurring elements", prompt)

    def test_first_appearance_element_is_described_without_prior_realization(self):
        children = [_child(realizes_element_id="lead_motif"), _child(is_leaf=False)]
        client = _FakeClient([_decompose_response(children)])
        context = [{
            "element_id": "lead_motif", "description": "a signature lead line",
            "is_recurrence": False, "prior_realization": None,
        }]
        decompose.decompose(make_node(), client, duration_s=40.0, recurring_context=context)
        prompt = client.messages.calls[0]["messages"][0]["content"]
        self.assertIn("lead_motif", prompt)
        self.assertIn("FIRST APPEARANCE", prompt)

    def test_recurrence_element_prompt_includes_prior_realization(self):
        children = [_child(realizes_element_id="lead_motif"), _child(is_leaf=False)]
        client = _FakeClient([_decompose_response(children)])
        context = [{
            "element_id": "lead_motif", "description": "a signature lead line",
            "is_recurrence": True,
            "prior_realization": {
                "preset_path": "Plucks/Metallic.fxp",
                "note_summary": "4 notes, pitch-intervals-from-first [0, 3, 5, 7]",
            },
        }]
        decompose.decompose(make_node(), client, duration_s=40.0, recurring_context=context)
        prompt = client.messages.calls[0]["messages"][0]["content"]
        self.assertIn("RECURRENCE", prompt)
        self.assertIn("Plucks/Metallic.fxp", prompt)
        self.assertIn("Vary it", prompt)


if __name__ == "__main__":
    unittest.main()
