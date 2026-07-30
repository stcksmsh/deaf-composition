"""Tests for src/planner/scheduler.py's recurring-element registry threading
and parallelized sibling emission (2026-07-27) -- fake-client style matching
tests/test_arc.py / tests/test_pipeline.py. Real Anthropic calls (decompose,
emit_leaf_implementation) are faked; the thing under test is build_tree()'s
own plumbing: spec augmentation, element_realizations collection/merging,
and that concurrent leaf emission doesn't corrupt deterministic track
assignment."""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from planner import scheduler  # noqa: E402
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
    """Keyed by tool name, not popped in strict order -- build_tree() fires
    concurrent emit_leaf_implementation calls (ThreadPoolExecutor), so the
    real popped-in-order _FakeMessages from test_pipeline.py/test_arc.py
    isn't safe here: two threads could race for the same response. Each
    call is matched by which tool_choice/tools it's making, using a
    per-tool queue instead."""

    def __init__(self):
        self._queues: dict[str, list] = {}
        self.calls = []

    def add(self, tool_name: str, response):
        self._queues.setdefault(tool_name, []).append(response)

    def create(self, **kwargs):
        self.calls.append(kwargs)
        tool_choice = kwargs.get("tool_choice", {})
        name = tool_choice.get("name") if isinstance(tool_choice, dict) else None
        if name is None:
            # leaf_emit uses tool_choice={"type": "any"} -- infer from the
            # single-leaf-emit queue key used throughout this test module.
            name = "leaf_emit"
        queue = self._queues.get(name)
        if not queue:
            raise AssertionError(f"no queued response for tool {name!r}")
        return queue.pop(0)


class _FakeClient:
    def __init__(self, messages: _FakeMessages):
        self.messages = messages


def _decompose_response(children):
    return _FakeResponse([_FakeBlock("tool_use", "decompose", {"children": children})])


def _emit_response(preset_path="Plucks/Metallic.fxp", notes=None):
    notes = notes if notes is not None else [
        {"pitch": 60, "velocity": 100, "start_beat": 0, "length_beats": 8},
    ]
    return _FakeResponse([
        _FakeBlock("tool_use", "apply_surge_preset",
                   {"track_index": 0, "fx_index": 0, "preset_path": preset_path}),
        _FakeBlock("tool_use", "create_midi_item",
                   {"track_index": 0, "position": 0, "length": 16}),
        _FakeBlock("tool_use", "add_midi_notes_batch",
                   {"track_index": 0, "item_index": 0, "notes": notes}),
    ])


def make_root():
    return Node(
        node_id="song/section_0",
        own_purpose="an intro section",
        spec="sparse and atmospheric",
        acceptance_criteria=AcceptanceCriteria(structural_facts={}),
        scope_chain=(ScopeLink(level="album", summary="x"),),
        body=Split(children=()),
    )


class TestElementRealizationThreading(unittest.TestCase):
    def test_leaf_realizing_an_element_is_recorded(self):
        messages = _FakeMessages()
        messages.add("decompose", _decompose_response([
            {"own_purpose": "lead", "spec": "carries the motif", "is_leaf": True,
             "realizes_element_id": "lead_motif"},
            {"own_purpose": "texture", "spec": "background pad", "is_leaf": True,
             "realizes_element_id": ""},
        ]))
        messages.add("leaf_emit", _emit_response(preset_path="Pads/Distant.fxp"))
        messages.add("leaf_emit", _emit_response(preset_path="Plucks/Metallic.fxp"))
        client = _FakeClient(messages)

        recurring_context = [{
            "element_id": "lead_motif", "description": "a signature lead line",
            "is_recurrence": False, "prior_realization": None,
        }]
        # Pin to 1 worker: the two queued leaf_emit responses are order-
        # sensitive (lead's preset must land on the lead child specifically),
        # and concurrent dispatch doesn't guarantee submission order pops
        # responses in that same order. A single worker thread still
        # exercises the real ThreadPoolExecutor code path, just serialized.
        with patch.object(scheduler, "MAX_PARALLEL_LEAF_EMISSIONS", 1):
            leaves, all_nodes, realizations = scheduler.build_tree(
                make_root(), client, client,
                target_section_type="intro", duration_s=32.0,
                track_counter=0, max_depth=2,
                recurring_context=recurring_context,
            )
        self.assertIn("lead_motif", realizations)
        self.assertEqual(realizations["lead_motif"]["preset_path"], "Pads/Distant.fxp")
        self.assertEqual(len(leaves), 2)

    def test_spec_is_augmented_with_recurrence_instruction(self):
        messages = _FakeMessages()
        messages.add("decompose", _decompose_response([
            {"own_purpose": "lead", "spec": "carries the motif", "is_leaf": True,
             "realizes_element_id": "lead_motif"},
            {"own_purpose": "texture", "spec": "background pad", "is_leaf": True,
             "realizes_element_id": ""},
        ]))
        messages.add("leaf_emit", _emit_response())
        messages.add("leaf_emit", _emit_response())
        client = _FakeClient(messages)

        recurring_context = [{
            "element_id": "lead_motif", "description": "a signature lead line",
            "is_recurrence": True,
            "prior_realization": {"preset_path": "Plucks/Metallic.fxp",
                                   "note_summary": "3 notes, pitch-intervals-from-first [0, 3, 5]"},
        }]
        with patch.object(scheduler, "MAX_PARALLEL_LEAF_EMISSIONS", 1):
            leaves, _, _ = scheduler.build_tree(
                make_root(), client, client,
                target_section_type="drop", duration_s=32.0,
                track_counter=0, max_depth=2,
                recurring_context=recurring_context,
            )
        lead_leaf = next(l for l in leaves if "lead" in l.own_purpose)
        self.assertIn("lead_motif", lead_leaf.spec)
        self.assertIn("Vary it", lead_leaf.spec)
        other_leaf = next(l for l in leaves if l is not lead_leaf)
        self.assertNotIn("lead_motif", other_leaf.spec)

    def test_unclaimed_element_is_dropped_and_not_raised(self):
        messages = _FakeMessages()
        messages.add("decompose", _decompose_response([
            {"own_purpose": "a", "spec": "x", "is_leaf": True, "realizes_element_id": ""},
            {"own_purpose": "b", "spec": "y", "is_leaf": True, "realizes_element_id": ""},
        ]))
        messages.add("leaf_emit", _emit_response())
        messages.add("leaf_emit", _emit_response())
        client = _FakeClient(messages)

        recurring_context = [{
            "element_id": "never_claimed", "description": "n/a",
            "is_recurrence": False, "prior_realization": None,
        }]
        leaves, _, realizations = scheduler.build_tree(
            make_root(), client, client,
            target_section_type="intro", duration_s=32.0,
            track_counter=0, max_depth=2,
            recurring_context=recurring_context,
        )
        self.assertEqual(realizations, {})
        self.assertEqual(len(leaves), 2)

    def test_track_indices_are_deterministic_despite_concurrent_emission(self):
        messages = _FakeMessages()
        messages.add("decompose", _decompose_response([
            {"own_purpose": f"leaf{i}", "spec": "x", "is_leaf": True, "realizes_element_id": ""}
            for i in range(4)
        ]))
        for _ in range(4):
            messages.add("leaf_emit", _emit_response())
        client = _FakeClient(messages)

        leaves, _, _ = scheduler.build_tree(
            make_root(), client, client,
            target_section_type="intro", duration_s=32.0,
            track_counter=10, max_depth=2,
        )
        track_indices = sorted(l.body.implementation["track_index"] for l in leaves)
        self.assertEqual(track_indices, [10, 11, 12, 13])

    def test_nested_realization_merges_up_through_recursion(self):
        messages = _FakeMessages()
        # top-level: one leaf (unrelated), one composite child that will
        # itself decompose into the leaf that actually claims the element.
        messages.add("decompose", _decompose_response([
            {"own_purpose": "unrelated", "spec": "x", "is_leaf": True, "realizes_element_id": ""},
            {"own_purpose": "composite", "spec": "needs further split", "is_leaf": False,
             "realizes_element_id": ""},
        ]))
        messages.add("decompose", _decompose_response([
            {"own_purpose": "nested lead", "spec": "carries it", "is_leaf": True,
             "realizes_element_id": "lead_motif"},
            {"own_purpose": "nested texture", "spec": "background", "is_leaf": True,
             "realizes_element_id": ""},
        ]))
        # Consumption order: outer level's "unrelated" leaf is built (via
        # ThreadPoolExecutor) before the outer decompose recurses into the
        # composite child, so the FIRST queued response goes to "unrelated",
        # not to the nested leaf that actually claims the element.
        messages.add("leaf_emit", _emit_response(preset_path="Pads/Distant.fxp"))  # unrelated
        messages.add("leaf_emit", _emit_response(preset_path="Plucks/Snap.fxp"))  # nested lead
        messages.add("leaf_emit", _emit_response())  # nested texture
        client = _FakeClient(messages)

        recurring_context = [{
            "element_id": "lead_motif", "description": "a signature lead line",
            "is_recurrence": False, "prior_realization": None,
        }]
        with patch.object(scheduler, "MAX_PARALLEL_LEAF_EMISSIONS", 1):
            leaves, all_nodes, realizations = scheduler.build_tree(
                make_root(), client, client,
                target_section_type="build", duration_s=40.0,
                track_counter=0, max_depth=3,
                recurring_context=recurring_context,
            )
        self.assertIn("lead_motif", realizations)
        self.assertEqual(realizations["lead_motif"]["preset_path"], "Plucks/Snap.fxp")
        self.assertEqual(len(leaves), 3)


if __name__ == "__main__":
    unittest.main()
