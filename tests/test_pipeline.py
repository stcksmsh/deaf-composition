"""Pipeline integration tests (2026-07-27): validates the decision logic in
src/planner/pipeline.py -- emit -> attack-check -> execute -> review ->
escalate/retry for one leaf, and review -> orchestrate -> mix_fix ->
compensate -> re-review for a composition round -- using a fake Executor and
a fake Anthropic client, no live REAPER required. This tests the GLUE, not
REAPER integration itself (which no standalone client can do outside a real
MCP session, per every module's own documented constraint)."""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from planner import orchestrate, pipeline  # noqa: E402
from planner.node import (  # noqa: E402
    AcceptanceCriteria, Leaf, ModelTier, Node, ReviewState, ReviewStatus, ScopeLink,
)
from planner.preset_attack import AttackMeasurement  # noqa: E402


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


def _emit_response(preset_path="Plucks/Metallic.fxp", notes=None, track_index=7):
    notes = notes or [{"pitch": 60, "velocity": 100, "start_beat": 0, "length_beats": 8}]
    return _FakeResponse([
        _FakeBlock("tool_use", "apply_surge_preset",
                   {"track_index": track_index, "fx_index": 0, "preset_path": preset_path}),
        _FakeBlock("tool_use", "create_midi_item",
                   {"track_index": track_index, "position": 0, "length": 16}),
        _FakeBlock("tool_use", "add_midi_notes_batch",
                   {"track_index": track_index, "item_index": 0, "notes": notes}),
    ])


def _fix_response(fixes):
    return _FakeResponse([_FakeBlock("tool_use", "propose_fixes", {"fixes": fixes})])


def make_node(node_id="proof/leaf", short_notes=False):
    notes = ([{"pitch": 60, "velocity": 100, "start_beat": 0, "length_beats": 0.25}]
             if short_notes else
             [{"pitch": 60, "velocity": 100, "start_beat": 0, "length_beats": 8}])
    return Node(
        node_id=node_id,
        own_purpose="test leaf",
        spec="test spec (track_index=7, fx_index=0, duration 16.0s at 120bpm/4-4)",
        acceptance_criteria=AcceptanceCriteria(target_section_type="drop",
                                               max_measured_distance=4.0,
                                               max_embedding_distance=0.85),
        scope_chain=(ScopeLink(level="album", summary="x"),),
        body=Leaf(implementation={}),
        assigned_model=ModelTier.HAIKU,
    ), notes


class FakeExecutor:
    """Records calls and returns pre-programmed results -- lets each test
    control exactly what "live REAPER" would have said without touching it."""

    def __init__(self, attack_measurements=None, leaf_states=None, remeasure_states=None):
        self.attack_measurements = list(attack_measurements or [])
        self.leaf_states = list(leaf_states or [])
        self.remeasure_states = dict(remeasure_states or {})
        self.applied_fixes = []
        self.gains_set = []

    def test_attack(self, track_index, fx_index, preset_path):
        return self.attack_measurements.pop(0)

    def execute_leaf(self, node_id, ops):
        return self.leaf_states.pop(0)

    def apply_fix(self, fix):
        self.applied_fixes.append(fix)

    def set_gain(self, node_id, gain_change_db):
        self.gains_set.append((node_id, gain_change_db))

    def remeasure(self, node_id):
        return self.remeasure_states[node_id]

    def remeasure_combined(self):
        raise NotImplementedError


def _state(lufs, centroid=440.0, embedding_ok=True):
    return {
        "measured": {"lufs": lufs, "sample_peak": lufs + 10,
                     "spectral_centroid": {"median": centroid}, "active_ratio": 1.0},
        "embedding": {"windows": []} if embedding_ok else None,
    }


class TestRunLeafCycle(unittest.TestCase):
    def test_passes_on_first_attempt_no_attack_check_needed(self):
        node, _ = make_node()
        client = _FakeClient([_emit_response()])
        executor = FakeExecutor(leaf_states=[_state(-15.0)])
        passed_review = ReviewState(status=ReviewStatus.PASSED, reasons=())
        with patch("planner.pipeline.review_leaf",
                   return_value=(passed_review, {"measured": {"distance": 1.0},
                                                  "embedding": {"distance": 0.1}})):
            result = pipeline.run_leaf_cycle(node, client, executor, library={})
        self.assertEqual(result.attempts, 1)
        self.assertFalse(result.escalated)
        self.assertEqual(result.review.status, ReviewStatus.PASSED)

    def test_attack_check_failure_triggers_retry_with_feedback(self):
        node, short_notes = make_node(short_notes=True)
        # First emission: short notes -> needs a live attack check, which fails.
        # Second emission: same short notes, but this time attack passes.
        client = _FakeClient([
            _emit_response(preset_path="Percussion/Synth Tom 2.fxp", notes=short_notes),
            _emit_response(preset_path="Percussion/Kick 909ish.fxp", notes=short_notes),
        ])
        executor = FakeExecutor(
            attack_measurements=[
                AttackMeasurement(attack_time_s=1.1, peak_db=-25.0),  # too slow -> fails
                AttackMeasurement(attack_time_s=0.0, peak_db=-20.0),  # instant -> passes
            ],
            leaf_states=[_state(-15.0)],
        )
        passed_review = ReviewState(status=ReviewStatus.PASSED, reasons=())
        with patch("planner.pipeline.review_leaf",
                   return_value=(passed_review, {"measured": {"distance": 1.0},
                                                  "embedding": {"distance": 0.1}})):
            result = pipeline.run_leaf_cycle(node, client, executor, library={})
        # Attack check failed once (consuming attempt 1's emission), succeeded
        # on the retry -- exactly one live render happened, not two, since the
        # first attempt never got past the attack gate.
        self.assertEqual(len(executor.leaf_states), 0)  # the one state was consumed
        self.assertFalse(result.escalated)
        self.assertEqual(result.review.status, ReviewStatus.PASSED)

    def test_own_criteria_failure_retries_then_escalates(self):
        node, _ = make_node()
        client = _FakeClient([_emit_response(), _emit_response()])
        executor = FakeExecutor(leaf_states=[_state(-52.0), _state(-50.0)])
        failed_review = ReviewState(status=ReviewStatus.FAILED,
                                     reasons=("measured distance 20 exceeds threshold 4",))
        with patch("planner.pipeline.review_leaf",
                   return_value=(failed_review, {"measured": {"distance": 20.0},
                                                  "embedding": {"distance": 0.5}})):
            result = pipeline.run_leaf_cycle(node, client, executor, library={},
                                              max_attempts=2)
        self.assertEqual(result.attempts, 2)
        self.assertTrue(result.escalated)
        self.assertIsNotNone(result.escalation_payload)


class TestRunCompositionFixCycle(unittest.TestCase):
    def test_converges_to_done_after_one_mix_fix_round(self):
        parent = Node(
            node_id="proof/parent", own_purpose="backbone",
            spec="x", acceptance_criteria=AcceptanceCriteria(structural_facts={}),
            scope_chain=(), body=Leaf(implementation={}),
        )
        # Round 0: kick vs bass loudness gap. Round 1 (post gain fix): passes.
        states_by_round = [
            {"a": _state(-24.0, 200), "b": _state(-11.0, 600)},
            {"a": _state(-24.0, 200), "b": _state(-20.0, 600)},
        ]
        combined_by_round = [_state(-15.0), _state(-15.0)]
        call = {"n": 0}

        def get_sibling_states():
            return states_by_round[call["n"]]

        def get_combined():
            return combined_by_round[call["n"]]

        client = _FakeClient([
            _fix_response([{"type": "gain", "target_node_id": "b", "rationale": "r",
                             "gain_change_db": -9.0}]),
        ])
        executor = FakeExecutor()

        def sibling_info_fn(states):
            return {k: {"own_purpose": "x", "track_index": 0,
                        "lufs": v["measured"]["lufs"],
                        "sample_peak_db": v["measured"]["sample_peak"],
                        "centroid_hz": v["measured"]["spectral_centroid"]["median"]}
                    for k, v in states.items()}

        orig_apply_fix = executor.apply_fix

        def apply_fix_and_advance(fix):
            orig_apply_fix(fix)
            call["n"] += 1

        executor.apply_fix = apply_fix_and_advance

        result = pipeline.run_composition_fix_cycle(
            parent, sibling_info_fn, get_sibling_states, get_combined, executor, client,
        )
        self.assertFalse(result.escalated)
        self.assertEqual(result.final_review.status, ReviewStatus.PASSED)
        self.assertEqual(result.strategy_history, ["mix_fix"])

    def test_eqcut_or_highpass_fix_triggers_compensating_gain(self):
        parent = Node(
            node_id="proof/parent", own_purpose="backbone",
            spec="x", acceptance_criteria=AcceptanceCriteria(structural_facts={}),
            scope_chain=(), body=Leaf(implementation={}),
        )
        states_by_round = [
            {"a": _state(-24.0, 230), "b": _state(-20.0, 240)},
            {"a": _state(-24.0, 230), "b": _state(-20.0, 500)},
        ]
        combined_by_round = [_state(-15.0), _state(-15.0)]
        call = {"n": 0}

        client = _FakeClient([
            _fix_response([{"type": "highpass", "target_node_id": "b", "rationale": "r",
                             "cutoff_hz": 400, "q": 0.9}]),
        ])
        # remeasure() after the highpass shows the level dropped (-20 -> -30) --
        # the compensating-gain step should be triggered with the difference.
        executor = FakeExecutor(remeasure_states={"b": _state(-30.0, 500)})

        def get_sibling_states():
            return states_by_round[call["n"]]

        def get_combined():
            return combined_by_round[call["n"]]

        def sibling_info_fn(states):
            return {k: {"own_purpose": "x", "track_index": 0,
                        "lufs": v["measured"]["lufs"],
                        "sample_peak_db": v["measured"]["sample_peak"],
                        "centroid_hz": v["measured"]["spectral_centroid"]["median"]}
                    for k, v in states.items()}

        orig_apply_fix = executor.apply_fix

        def apply_fix_and_advance(fix):
            orig_apply_fix(fix)
            call["n"] += 1

        executor.apply_fix = apply_fix_and_advance

        pipeline.run_composition_fix_cycle(
            parent, sibling_info_fn, get_sibling_states, get_combined, executor, client,
        )
        self.assertEqual(len(executor.applied_fixes), 1)
        self.assertEqual(executor.applied_fixes[0]["type"], "highpass")
        # pre_lufs (-20.0) - post_lufs (-30.0) = +10.0dB compensating gain.
        self.assertEqual(executor.gains_set, [("b", 10.0)])

    def test_escalates_when_orchestrate_says_leaf_retry(self):
        parent = Node(
            node_id="proof/parent", own_purpose="backbone",
            spec="x", acceptance_criteria=AcceptanceCriteria(structural_facts={}),
            scope_chain=(), body=Leaf(implementation={}),
        )
        failing_review = ReviewState(status=ReviewStatus.FAILED, reasons=("bad",),
                                      metrics={"undefined_lufs_count": 1})
        with patch("planner.pipeline.review_composition", return_value=failing_review), \
             patch("planner.orchestrate.choose_fix_strategy",
                   return_value=orchestrate.FixStrategy("leaf_retry", "stalled")):
            executor = FakeExecutor()
            client = _FakeClient([])
            result = pipeline.run_composition_fix_cycle(
                parent, lambda s: {}, lambda: {}, lambda: {}, executor, client,
            )
        self.assertTrue(result.escalated)


if __name__ == "__main__":
    unittest.main()
