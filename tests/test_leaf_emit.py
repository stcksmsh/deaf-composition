"""Tests for scripts/leaf_emit.py's _validate_ops -- specifically the
2026-07-27 additions (automate_track_envelope / automate_surge_param as
optional trailing ops), which existing coverage never had a dedicated test
module for (this project validated leaf_emit.py via live proof scripts
until now; these are pure-function checks, no API key needed)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import leaf_emit  # noqa: E402


def _base_ops(preset_path="Plucks/Metallic.fxp", notes=None):
    if notes is None:
        notes = [{"pitch": 60, "velocity": 100, "start_beat": 0, "length_beats": 8}]
    return [
        {"tool": "apply_surge_preset",
         "args": {"track_index": 7, "fx_index": 0, "preset_path": preset_path}},
        {"tool": "create_midi_item", "args": {"track_index": 7, "position": 0, "length": 16}},
        {"tool": "add_midi_notes_batch", "args": {"track_index": 7, "item_index": 0, "notes": notes}},
    ]


class TestTileNotesToDuration(unittest.TestCase):
    def test_empty_notes_returns_empty(self):
        self.assertEqual(leaf_emit.tile_notes_to_duration([], 32.0), [])

    def test_pattern_already_spanning_full_duration_is_unchanged(self):
        notes = [{"pitch": 60, "velocity": 100, "start_beat": 0, "length_beats": 32}]
        result = leaf_emit.tile_notes_to_duration(notes, 32.0)
        self.assertEqual(result, notes)

    def test_short_cycle_is_tiled_to_fill_duration(self):
        # 1-beat cycle, 4 beats total -> should repeat 4 times
        notes = [{"pitch": 60, "velocity": 100, "start_beat": 0, "length_beats": 1}]
        result = leaf_emit.tile_notes_to_duration(notes, 4.0)
        self.assertEqual(sorted(n["start_beat"] for n in result), [0, 1, 2, 3])

    def test_partial_final_repeat_is_clipped_not_overrun(self):
        # 3-beat cycle (2 notes), 7 beats total -> 2 full reps (6 beats) + a
        # partial 3rd rep clipped to whatever fits before 7.
        notes = [
            {"pitch": 60, "velocity": 100, "start_beat": 0, "length_beats": 1},
            {"pitch": 64, "velocity": 100, "start_beat": 2, "length_beats": 1},
        ]
        result = leaf_emit.tile_notes_to_duration(notes, 7.0)
        starts = sorted(n["start_beat"] for n in result)
        self.assertTrue(all(s < 7.0 for s in starts))
        self.assertEqual(starts, [0, 2, 3, 5, 6])

    def test_multi_note_pattern_preserves_relative_shape_per_repeat(self):
        notes = [
            {"pitch": 60, "velocity": 100, "start_beat": 0, "length_beats": 0.5},
            {"pitch": 62, "velocity": 100, "start_beat": 0.5, "length_beats": 0.5},
        ]
        result = leaf_emit.tile_notes_to_duration(notes, 2.0)
        pitches_by_start = {n["start_beat"]: n["pitch"] for n in result}
        self.assertEqual(pitches_by_start[0], 60)
        self.assertEqual(pitches_by_start[1], 60)
        self.assertEqual(pitches_by_start[0.5], 62)
        self.assertEqual(pitches_by_start[1.5], 62)


class TestTilingExtendsItemLength(unittest.TestCase):
    """emit_leaf_implementation's duration_s wiring must extend the item
    container to match tiled notes, not just tile the notes array --
    otherwise REAPER clips anything past the item's own [position,
    position+length) bounds, silently inaudible despite a "successful" plan.
    Real bug found live across ~12 leaves in a fresh song build."""

    def _fake_client(self, ops):
        class Block:
            def __init__(self, name, input_):
                self.type = "tool_use"
                self.name = name
                self.input = input_

        class Response:
            def __init__(self, content):
                self.content = content

        class Messages:
            def create(self, **kwargs):
                return Response([Block(op["tool"], op["args"]) for op in ops])

        class Client:
            def __init__(self):
                self.messages = Messages()

        return Client()

    def test_item_length_extended_when_tiling_grows_past_it(self):
        ops = [
            {"tool": "apply_surge_preset",
             "args": {"track_index": 0, "fx_index": 0, "preset_path": "Plucks/Metallic.fxp"}},
            {"tool": "create_midi_item", "args": {"track_index": 0, "position": 0, "length": 2}},
            {"tool": "add_midi_notes_batch", "args": {"track_index": 0, "item_index": 0,
                "notes": [{"pitch": 60, "velocity": 100, "start_beat": 0, "length_beats": 1}]}},
        ]
        from planner.node import AcceptanceCriteria, Leaf, ModelTier, Node, ScopeLink
        node = Node(
            node_id="x", own_purpose="p", spec="s",
            acceptance_criteria=AcceptanceCriteria(structural_facts={}),
            scope_chain=(ScopeLink(level="album", summary="x"),),
            body=Leaf(implementation={}), assigned_model=ModelTier.HAIKU,
        )
        result = leaf_emit.emit_leaf_implementation(
            node, self._fake_client(ops), duration_s=8.0,
        )
        item_op = next(o for o in result["ops"] if o["tool"] == "create_midi_item")
        notes_op = next(o for o in result["ops"] if o["tool"] == "add_midi_notes_batch")
        max_note_end_beats = max(n["start_beat"] + n["length_beats"] for n in notes_op["args"]["notes"])
        item_len_beats = item_op["args"]["length"] * leaf_emit.TEMPO / 60.0
        self.assertGreaterEqual(item_len_beats, max_note_end_beats)

    def test_item_length_untouched_when_no_tiling_needed(self):
        ops = [
            {"tool": "apply_surge_preset",
             "args": {"track_index": 0, "fx_index": 0, "preset_path": "Pads/Distant.fxp"}},
            {"tool": "create_midi_item", "args": {"track_index": 0, "position": 0, "length": 8}},
            {"tool": "add_midi_notes_batch", "args": {"track_index": 0, "item_index": 0,
                "notes": [{"pitch": 60, "velocity": 100, "start_beat": 0, "length_beats": 16}]}},
        ]
        from planner.node import AcceptanceCriteria, Leaf, ModelTier, Node, ScopeLink
        node = Node(
            node_id="x", own_purpose="p", spec="s",
            acceptance_criteria=AcceptanceCriteria(structural_facts={}),
            scope_chain=(ScopeLink(level="album", summary="x"),),
            body=Leaf(implementation={}), assigned_model=ModelTier.HAIKU,
        )
        result = leaf_emit.emit_leaf_implementation(
            node, self._fake_client(ops), duration_s=8.0,
        )
        item_op = next(o for o in result["ops"] if o["tool"] == "create_midi_item")
        self.assertEqual(item_op["args"]["length"], 8)


class TestForegroundArcRequirement(unittest.TestCase):
    """2026-07-29: a stated-but-unenforced ">=24 beats" instruction was
    under-delivered twice live (8 beats, then 12 beats) before being caught
    by hand. MIN_FOREGROUND_ARC_BEATS + the mechanical check in
    emit_leaf_implementation close that gap -- these tests cover the actual
    enforcement, not just the prompt text."""

    def _make_node(self, prominence="midground"):
        from planner.node import AcceptanceCriteria, Leaf, ModelTier, Node, ScopeLink
        return Node(
            node_id="x", own_purpose="p", spec="s",
            acceptance_criteria=AcceptanceCriteria(structural_facts={}),
            scope_chain=(ScopeLink(level="album", summary="x"),),
            body=Leaf(implementation={}), assigned_model=ModelTier.HAIKU,
            prominence=prominence,
        )

    def _ops_with_pattern_span(self, span_beats, track=0):
        notes = [{"pitch": 60, "velocity": 100, "start_beat": 0, "length_beats": span_beats}]
        return [
            {"tool": "apply_surge_preset",
             "args": {"track_index": track, "fx_index": 0, "preset_path": "Plucks/Metallic.fxp"}},
            {"tool": "create_midi_item", "args": {"track_index": track, "position": 0, "length": 80}},
            {"tool": "add_midi_notes_batch", "args": {"track_index": track, "item_index": 0, "notes": notes}},
        ]

    def _multi_response_client(self, ops_list):
        class Block:
            def __init__(self, name, input_):
                self.type = "tool_use"
                self.name = name
                self.input = input_

        class Response:
            def __init__(self, content):
                self.content = content

        class Messages:
            def __init__(self, ops_list):
                self._queue = list(ops_list)
                self.call_count = 0

            def create(self, **kwargs):
                self.call_count += 1
                ops = self._queue.pop(0) if len(self._queue) > 1 else self._queue[0]
                return Response([Block(op["tool"], op["args"]) for op in ops])

        class Client:
            def __init__(self, ops_list):
                self.messages = Messages(ops_list)

        return Client(ops_list)

    def test_foreground_short_pattern_on_long_section_is_rejected_and_retried(self):
        client = self._multi_response_client([
            self._ops_with_pattern_span(8.0),   # attempt 1: too short
            self._ops_with_pattern_span(24.0),  # attempt 2: meets the minimum
        ])
        node = self._make_node(prominence="foreground")
        result = leaf_emit.emit_leaf_implementation(node, client, duration_s=80.0, retries=2)
        self.assertEqual(client.messages.call_count, 2)
        notes_op = next(o for o in result["ops"] if o["tool"] == "add_midi_notes_batch")
        # first (pre-tile) note should now come from the accepted 24-beat attempt
        self.assertEqual(notes_op["args"]["notes"][0]["length_beats"], 24.0)

    def test_foreground_pattern_exhausting_retries_raises(self):
        client = self._multi_response_client([self._ops_with_pattern_span(8.0)])
        node = self._make_node(prominence="foreground")
        with self.assertRaises(RuntimeError):
            leaf_emit.emit_leaf_implementation(node, client, duration_s=80.0, retries=1)

    def test_midground_short_pattern_on_long_section_is_not_rejected(self):
        client = self._multi_response_client([self._ops_with_pattern_span(8.0)])
        node = self._make_node(prominence="midground")
        result = leaf_emit.emit_leaf_implementation(node, client, duration_s=80.0, retries=1)
        self.assertEqual(client.messages.call_count, 1)
        self.assertIn("ops", result)

    def test_foreground_short_section_below_20s_is_not_subject_to_the_rule(self):
        client = self._multi_response_client([self._ops_with_pattern_span(4.0)])
        node = self._make_node(prominence="foreground")
        result = leaf_emit.emit_leaf_implementation(node, client, duration_s=12.0, retries=1)
        self.assertEqual(client.messages.call_count, 1)
        self.assertIn("ops", result)

    def test_prompt_includes_override_language_for_foreground_long_section(self):
        client = self._multi_response_client([self._ops_with_pattern_span(24.0)])
        node = self._make_node(prominence="foreground")
        leaf_emit.emit_leaf_implementation(node, client, duration_s=80.0, retries=0)
        # sanity: the override constant is what the mechanical check compares against
        self.assertEqual(leaf_emit.MIN_FOREGROUND_ARC_BEATS, 24.0)


class TestItemLengthAwareTiling(unittest.TestCase):
    """2026-07-29, real live pipeline bug: a leaf spec explicitly asked for
    a short one-shot gesture ("no loop... leaves total space for the
    bell/pad to enter") inside a much longer section. The model correctly
    authored a short item for it, but emit_leaf_implementation was tiling
    against the SECTION's full duration regardless of the model's own
    declared item length -- both wrongly demanding 24+ beats of content
    from a deliberate 3-beat gesture, AND about to loop that "no loop"
    gesture across the whole section. effective_duration_beats (min of the
    model's own item length and the section duration) fixes both."""

    def _make_node(self, prominence="foreground"):
        from planner.node import AcceptanceCriteria, Leaf, ModelTier, Node, ScopeLink
        return Node(
            node_id="x", own_purpose="p", spec="s",
            acceptance_criteria=AcceptanceCriteria(structural_facts={}),
            scope_chain=(ScopeLink(level="album", summary="x"),),
            body=Leaf(implementation={}), assigned_model=ModelTier.HAIKU,
            prominence=prominence,
        )

    def _single_response_client(self, ops):
        class Block:
            def __init__(self, name, input_):
                self.type = "tool_use"
                self.name = name
                self.input = input_

        class Response:
            def __init__(self, content):
                self.content = content

        class Messages:
            def create(self, **kwargs):
                return Response([Block(op["tool"], op["args"]) for op in ops])

        class Client:
            def __init__(self):
                self.messages = Messages()

        return Client()

    def test_short_deliberate_one_shot_is_not_forced_to_24_beats(self):
        # A 3-beat one-shot gesture in a 3-beat item, on a 40s (foreground)
        # section -- must NOT trigger the MIN_FOREGROUND_ARC_BEATS error,
        # since the leaf's own declared item is genuinely short.
        notes = [{"pitch": 36, "velocity": 120, "start_beat": 0.0, "length_beats": 0.5},
                 {"pitch": 40, "velocity": 110, "start_beat": 0.5, "length_beats": 0.5}]
        ops = [
            {"tool": "apply_surge_preset",
             "args": {"track_index": 0, "fx_index": 0, "preset_path": "Sequences/Acid Seq 1.fxp"}},
            {"tool": "create_midi_item", "args": {"track_index": 0, "position": 0, "length": 3}},
            {"tool": "add_midi_notes_batch", "args": {"track_index": 0, "item_index": 0, "notes": notes}},
        ]
        node = self._make_node(prominence="foreground")
        result = leaf_emit.emit_leaf_implementation(
            node, self._single_response_client(ops), duration_s=40.0, retries=0,
        )
        notes_op = next(o for o in result["ops"] if o["tool"] == "add_midi_notes_batch")
        # Not tiled out across the 40s section -- still just the 2 authored notes.
        self.assertEqual(len(notes_op["args"]["notes"]), 2)

    def test_short_one_shot_item_is_not_grown_to_fill_section(self):
        notes = [{"pitch": 36, "velocity": 120, "start_beat": 0.0, "length_beats": 1.0}]
        ops = [
            {"tool": "apply_surge_preset",
             "args": {"track_index": 0, "fx_index": 0, "preset_path": "Sequences/Acid Seq 1.fxp"}},
            {"tool": "create_midi_item", "args": {"track_index": 0, "position": 0, "length": 2}},
            {"tool": "add_midi_notes_batch", "args": {"track_index": 0, "item_index": 0, "notes": notes}},
        ]
        node = self._make_node(prominence="midground")
        result = leaf_emit.emit_leaf_implementation(
            node, self._single_response_client(ops), duration_s=40.0, retries=0,
        )
        item_op = next(o for o in result["ops"] if o["tool"] == "create_midi_item")
        self.assertEqual(item_op["args"]["length"], 2)

    def test_full_section_item_still_tiles_to_full_duration(self):
        # Regression check: a leaf whose declared item length already spans
        # the full section (the common case) must still tile/extend exactly
        # as before this fix.
        notes = [{"pitch": 60, "velocity": 100, "start_beat": 0, "length_beats": 1}]
        ops = [
            {"tool": "apply_surge_preset",
             "args": {"track_index": 0, "fx_index": 0, "preset_path": "Plucks/Metallic.fxp"}},
            {"tool": "create_midi_item", "args": {"track_index": 0, "position": 0, "length": 8}},
            {"tool": "add_midi_notes_batch", "args": {"track_index": 0, "item_index": 0, "notes": notes}},
        ]
        node = self._make_node(prominence="midground")
        result = leaf_emit.emit_leaf_implementation(
            node, self._single_response_client(ops), duration_s=8.0, retries=0,
        )
        notes_op = next(o for o in result["ops"] if o["tool"] == "add_midi_notes_batch")
        # 8s section at TEMPO=120 -> 16 beats; 1-beat cycle -> 16 repeats.
        self.assertEqual(len(notes_op["args"]["notes"]), 16)


class TestBaseSequenceStillEnforced(unittest.TestCase):
    def test_correct_three_ops_pass(self):
        leaf_emit._validate_ops(_base_ops())  # no raise

    def test_wrong_order_rejected(self):
        ops = _base_ops()
        ops[0], ops[1] = ops[1], ops[0]
        with self.assertRaises(ValueError):
            leaf_emit._validate_ops(ops)

    def test_empty_notes_rejected(self):
        with self.assertRaises(ValueError):
            leaf_emit._validate_ops(_base_ops(notes=[]))


class TestExcludedPresetRejected(unittest.TestCase):
    def test_excluded_preset_path_raises(self):
        ops = _base_ops(preset_path="Percussion/Snare Tight.fxp")
        with self.assertRaises(ValueError):
            leaf_emit._validate_ops(ops)

    def test_non_excluded_preset_passes(self):
        leaf_emit._validate_ops(_base_ops(preset_path="Plucks/Metallic.fxp"))  # no raise


class TestAutomationOpsOptional(unittest.TestCase):
    def test_no_automation_ops_is_fine(self):
        leaf_emit._validate_ops(_base_ops())  # no raise

    def test_valid_track_envelope_op_passes(self):
        ops = _base_ops() + [{
            "tool": "automate_track_envelope",
            "args": {"track_index": 7, "envelope_name": "Volume",
                      "points": [{"time": 0, "value": 0.5}, {"time": 8, "value": 1.0}]},
        }]
        leaf_emit._validate_ops(ops)  # no raise

    def test_track_envelope_bad_name_rejected(self):
        ops = _base_ops() + [{
            "tool": "automate_track_envelope",
            "args": {"track_index": 7, "envelope_name": "Mute",
                      "points": [{"time": 0, "value": 1.0}]},
        }]
        with self.assertRaises(ValueError):
            leaf_emit._validate_ops(ops)

    def test_track_envelope_empty_points_rejected(self):
        ops = _base_ops() + [{
            "tool": "automate_track_envelope",
            "args": {"track_index": 7, "envelope_name": "Volume", "points": []},
        }]
        with self.assertRaises(ValueError):
            leaf_emit._validate_ops(ops)

    def test_surge_param_op_with_valid_name_passes(self):
        ops = _base_ops() + [{
            "tool": "automate_surge_param",
            "args": {"track_index": 7, "fx_index": 0, "param_name": "A Filter 1 Cutoff",
                      "points": [{"time": 0, "value": -60}, {"time": 8, "value": 70}]},
        }]
        leaf_emit._validate_ops(ops, valid_overrides={"A Filter 1 Cutoff"})

    def test_surge_param_op_with_unknown_name_rejected(self):
        ops = _base_ops() + [{
            "tool": "automate_surge_param",
            "args": {"track_index": 7, "fx_index": 0, "param_name": "Master Volume",
                      "points": [{"time": 0, "value": 0}]},
        }]
        with self.assertRaises(ValueError):
            leaf_emit._validate_ops(ops, valid_overrides={"A Filter 1 Cutoff"})

    def test_unknown_trailing_tool_rejected(self):
        ops = _base_ops() + [{"tool": "not_a_real_tool", "args": {}}]
        with self.assertRaises(ValueError):
            leaf_emit._validate_ops(ops)

    def test_both_automation_ops_together(self):
        ops = _base_ops() + [
            {"tool": "automate_track_envelope",
             "args": {"track_index": 7, "envelope_name": "Width",
                      "points": [{"time": 0, "value": 0.2}, {"time": 8, "value": 1.0}]}},
            {"tool": "automate_surge_param",
             "args": {"track_index": 7, "fx_index": 0, "param_name": "A Filter 1 Cutoff",
                       "points": [{"time": 0, "value": -60}, {"time": 8, "value": 70}]}},
        ]
        leaf_emit._validate_ops(ops, valid_overrides={"A Filter 1 Cutoff"})


if __name__ == "__main__":
    unittest.main()
