"""Iterative mastering/mixing convergence loop (2026-07-29) -- the real
infrastructure gap flagged during "Tidal Lock" mastering (see memory.md,
2026-07-28: "does an iterative set-values/measure/adjust-direction/repeat
loop make sense... generalizable elsewhere?"). Confirmed before writing
this that it did NOT already exist: mix_fix.py's `propose_composition_fix`
is a single propose-and-check pass (one model call, one set of fixes,
done), and orchestrate.py's `choose_fix_strategy` decides WHICH strategy
family to use and when to give up on it, not how to converge numerically
within one.

The answer given to the user's question, now encoded here: yes, this
pattern generalizes, with one correction the user's framing needed --
it must target a RELATIVE/pairwise metric between competing elements (a
loudness gap, a spectral-centroid ratio -- review_composition already
computes exactly these), not each element's own absolute level in
isolation, since audibility/masking is inherently about the relationship
between simultaneous sources, not a solo property.

This is decision-only, same division of labor as mix_fix.py and
gain_stage.py: `MixCarveLoop` turns a stream of (param_value, metric_value)
observations into the next param_value to try, or a verdict that it's
converged or should escalate to a human listen. The caller (a live session
with real MCP tools) owns applying each proposed param value, re-rendering,
and re-measuring the metric -- this module never touches REAPER.

Algorithm: direction-corrected bisection. The caller supplies an initial
guess at which way the param should move (a real judgment call -- e.g.
"cutting this EQ band should widen the spectral gap" -- the same kind of
domain reasoning mix_fix.py's own model call already makes, not invented
here). Each round: if the last move made the metric CLOSER to target, keep
going the same direction at the same step size (still converging, no need
to change course). If it made things WORSE -- overshot, or the initial
direction guess was simply wrong -- reverse direction and halve the step.
Stops and reports "converged" once within tolerance, or "escalate" once
the step size has been halved past a floor (or a round budget is spent)
without converging -- exactly the "only escalate to a listen once
converged [or clearly stuck]" behavior the user asked for.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class CarveObservation:
    param_value: float
    metric_value: float


@dataclass(frozen=True)
class CarveMove:
    action: str  # "adjust" | "converged" | "escalate"
    new_param_value: float | None
    reason: str


@dataclass
class MixCarveLoop:
    """One instance per (metric, param) pair being carved -- e.g. "the
    spectral-centroid ratio between the pad and the lead" carved via "the
    pad's Filter 1 Cutoff." A composition failure naming several problem
    pairs needs several independent loops, not one shared instance --
    each pair can converge or stall on its own schedule.

    target: the metric value convergence is aiming for (e.g. the midpoint
        of review_composition's own SPECTRAL_OVERLAP_RATIO_THRESHOLD-based
        acceptable range, or a specific LUFS-gap target -- the caller's
        choice, since only it knows which review threshold this loop is
        trying to satisfy).
    tolerance: how close counts as "converged" -- should be well inside
        whatever threshold review_composition itself checks, so a
        converged loop reliably passes review, not just barely.
    initial_direction: +1.0 or -1.0 -- which way to move param_value on
        the very first, undirected move. A real judgment call the caller
        makes (mix_fix.py-style reasoning), not guessed here.
    initial_step: the size of that first move, in the param's own units
        (dB for a gain/EQ param, etc.).
    min_step: once bisection has halved the step below this, further
        halving isn't worth another round -- stop and escalate rather than
        take a vanishingly small, practically inaudible step forever.
    max_rounds: a hard ceiling independent of step size, in case the
        metric oscillates without ever shrinking the effective error
        (converging step size doesn't guarantee converging error if the
        param/metric relationship is noisy, e.g. a re-render measurement
        with real variance) -- matches orchestrate.py's own
        DEFAULT_MAX_NON_IMPROVING philosophy of a hard round budget as a
        backstop, not just a trend check.
    """
    target: float
    tolerance: float
    initial_direction: float
    initial_step: float
    min_step: float = 0.25
    max_rounds: int = 6

    _direction: float = field(init=False, repr=False)
    _step: float = field(init=False, repr=False)
    history: list[CarveObservation] = field(default_factory=list, init=False)

    def __post_init__(self) -> None:
        if self.initial_direction not in (1.0, -1.0):
            raise ValueError(f"initial_direction must be +1.0 or -1.0, got {self.initial_direction!r}")
        if self.initial_step <= 0:
            raise ValueError(f"initial_step must be > 0, got {self.initial_step!r}")
        self._direction = self.initial_direction
        self._step = self.initial_step

    def propose_next(self, current_param_value: float, metric_value: float) -> CarveMove:
        """Call once per round, AFTER measuring metric_value at
        current_param_value (the value this loop itself proposed last
        round, or the pre-fix baseline on the first call). Records the
        observation, then returns either the next param_value to try, or
        a converged/escalate verdict."""
        distance = abs(metric_value - self.target)

        if self.history:
            prev_distance = abs(self.history[-1].metric_value - self.target)
            if distance > prev_distance:
                # Last move made things worse -- either an overshoot past
                # the target, or the initial direction guess was simply
                # wrong. Either way: reverse and take a smaller step next.
                self._direction *= -1
                self._step /= 2.0

        self.history.append(CarveObservation(current_param_value, metric_value))

        if distance <= self.tolerance:
            return CarveMove(
                "converged", None,
                f"metric {metric_value:.3f} within {self.tolerance} of target "
                f"{self.target:.3f} after {len(self.history)} round(s)"
            )

        if self._step < self.min_step or len(self.history) >= self.max_rounds:
            return CarveMove(
                "escalate", None,
                f"stalled after {len(self.history)} round(s) (step={self._step:.4f}, "
                f"still {distance:.3f} from target) -- needs a human listen, not "
                f"another automated guess"
            )

        new_value = current_param_value + self._direction * self._step
        return CarveMove(
            "adjust", new_value,
            f"round {len(self.history)}: distance {distance:.3f} from target, "
            f"moving {'+' if self._direction > 0 else '-'}{self._step:.3f}"
        )
