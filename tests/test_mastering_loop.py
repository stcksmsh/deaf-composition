"""Tests for src/planner/mastering_loop.py -- the direction-corrected
bisection convergence loop built 2026-07-29 in response to the user's real
question about whether an iterative propose/measure/adjust-direction/
repeat mastering workflow generalizes (it does, targeting relative/
pairwise metrics, per the module's own docstring)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from planner import mastering_loop  # noqa: E402


class TestImmediateConvergence(unittest.TestCase):
    def test_first_measurement_already_within_tolerance(self):
        loop = mastering_loop.MixCarveLoop(
            target=1.5, tolerance=0.1, initial_direction=1.0, initial_step=2.0
        )
        move = loop.propose_next(current_param_value=0.0, metric_value=1.55)
        self.assertEqual(move.action, "converged")
        self.assertIsNone(move.new_param_value)


class TestFirstMove(unittest.TestCase):
    def test_proposes_initial_direction_and_step(self):
        loop = mastering_loop.MixCarveLoop(
            target=1.5, tolerance=0.05, initial_direction=1.0, initial_step=2.0
        )
        move = loop.propose_next(current_param_value=0.0, metric_value=3.0)
        self.assertEqual(move.action, "adjust")
        self.assertAlmostEqual(move.new_param_value, 2.0)

    def test_negative_initial_direction(self):
        loop = mastering_loop.MixCarveLoop(
            target=1.5, tolerance=0.05, initial_direction=-1.0, initial_step=2.0
        )
        move = loop.propose_next(current_param_value=0.0, metric_value=3.0)
        self.assertAlmostEqual(move.new_param_value, -2.0)


class TestKeepsDirectionWhenImproving(unittest.TestCase):
    def test_continues_same_direction_and_step_after_improvement(self):
        loop = mastering_loop.MixCarveLoop(
            target=0.0, tolerance=0.01, initial_direction=1.0, initial_step=1.0
        )
        # round 1: far from target, proposes +1.0
        move1 = loop.propose_next(current_param_value=0.0, metric_value=10.0)
        self.assertEqual(move1.action, "adjust")
        self.assertAlmostEqual(move1.new_param_value, 1.0)
        # round 2: metric moved closer (distance shrank) -- keep direction/step
        move2 = loop.propose_next(current_param_value=1.0, metric_value=8.0)
        self.assertEqual(move2.action, "adjust")
        self.assertAlmostEqual(move2.new_param_value, 2.0)


class TestReversesOnOvershoot(unittest.TestCase):
    def test_reverses_direction_and_halves_step_when_metric_gets_worse(self):
        loop = mastering_loop.MixCarveLoop(
            target=0.0, tolerance=0.01, initial_direction=1.0, initial_step=1.0
        )
        move1 = loop.propose_next(current_param_value=0.0, metric_value=2.0)
        self.assertAlmostEqual(move1.new_param_value, 1.0)
        # round 2: distance got WORSE (4.0 vs 2.0) -- wrong direction, reverse+halve
        move2 = loop.propose_next(current_param_value=1.0, metric_value=4.0)
        self.assertEqual(move2.action, "adjust")
        self.assertAlmostEqual(move2.new_param_value, 1.0 - 0.5)


class TestEscalation(unittest.TestCase):
    def test_escalates_once_step_shrinks_below_floor(self):
        loop = mastering_loop.MixCarveLoop(
            target=0.0, tolerance=0.001, initial_direction=1.0, initial_step=1.0,
            min_step=0.4, max_rounds=20,
        )
        # Force repeated overshoots so the step keeps halving: 1.0 -> 0.5 -> 0.25 (< min_step 0.4)
        move = loop.propose_next(current_param_value=0.0, metric_value=5.0)  # dist 5.0, propose +1.0
        self.assertEqual(move.action, "adjust")
        move = loop.propose_next(current_param_value=1.0, metric_value=10.0)  # worse -> reverse, step=0.5
        self.assertEqual(move.action, "adjust")
        move = loop.propose_next(current_param_value=0.5, metric_value=15.0)  # worse -> reverse, step=0.25 < 0.4
        self.assertEqual(move.action, "escalate")
        self.assertIn("needs a human listen", move.reason)

    def test_escalates_at_max_rounds_even_if_still_improving(self):
        loop = mastering_loop.MixCarveLoop(
            target=0.0, tolerance=0.001, initial_direction=1.0, initial_step=1.0,
            min_step=0.001, max_rounds=2,
        )
        move1 = loop.propose_next(current_param_value=0.0, metric_value=10.0)
        self.assertEqual(move1.action, "adjust")
        move2 = loop.propose_next(current_param_value=1.0, metric_value=9.0)  # improving, but round 2 hits max_rounds
        self.assertEqual(move2.action, "escalate")


class TestValidation(unittest.TestCase):
    def test_bad_initial_direction_raises(self):
        with self.assertRaises(ValueError):
            mastering_loop.MixCarveLoop(target=0.0, tolerance=0.1, initial_direction=0.5, initial_step=1.0)

    def test_nonpositive_initial_step_raises(self):
        with self.assertRaises(ValueError):
            mastering_loop.MixCarveLoop(target=0.0, tolerance=0.1, initial_direction=1.0, initial_step=0.0)


if __name__ == "__main__":
    unittest.main()
