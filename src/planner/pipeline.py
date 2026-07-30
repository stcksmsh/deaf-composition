"""Pipeline integration (2026-07-27): every mechanism built this session --
the attack-time check, the duty-cycle-aware loudness metric, escalation,
orchestration, mix_fix's gain/eq_cut/highpass fix types, and the
compensating-gain follow-up -- has been invoked by hand, script by script,
one live REAPER round at a time. This module is the piece that was never
built: the actual glue that chains them into one reusable cycle instead of
a human re-deriving the sequence every time.

The real constraint this has to respect, unchanged since scheduler.py's own
docstring: no standalone MCP client exists for the ~150 reaper-mcp tools
outside a real MCP session, so this module cannot execute REAPER calls
itself. What it CAN do -- and is the actual point of this module -- is own
the *decision logic* (what to emit, whether a result passes, what to try
next, when to give up) as clean, testable code, independent of who actually
runs the REAPER calls. That separation is expressed as the `Executor`
protocol below: a controlling session (or, someday, a real automation
harness) implements it; this module's cycle functions call it and act on
what it returns, without knowing or caring how it's implemented.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from planner import escalation, mix_fix, orchestrate
from planner.node import Node, ReviewState
from planner.preset_attack import AttackMeasurement, attack_ok_for_note_length
from planner.review import review_composition, review_leaf


class Executor(Protocol):
    """What a controlling session must provide to run a real cycle. Each
    method does real, live work (REAPER calls, rendering, measuring) --
    this module never touches REAPER directly."""

    def test_attack(self, track_index: int, fx_index: int, preset_path: str) -> AttackMeasurement:
        """Apply preset_path, play one generously long test note, render,
        and return the measured attack (see scripts/check_preset_attack.py
        for the exact live steps)."""
        ...

    def execute_leaf(self, node_id: str, ops: list[dict]) -> dict:
        """Run ops (apply_surge_preset/create_midi_item/add_midi_notes_batch
        + render) against the real project, return the built `state` dict
        (measured + embedding) for the resulting render."""
        ...

    def apply_fix(self, fix: dict) -> None:
        """Execute one mix_fix.py fix dict live (gain/sidechain/eq_cut/
        highpass) against the real project."""
        ...

    def set_gain(self, node_id: str, gain_change_db: float) -> None:
        """Apply an additional flat gain change to node_id's track (used
        for the compensating-gain follow-up after eq_cut/highpass)."""
        ...

    def remeasure(self, node_id: str) -> dict:
        """Re-render and re-build the state for node_id after a fix."""
        ...

    def remeasure_combined(self) -> dict:
        """Re-render and re-build the state for the combined mix of every
        sibling in the current composition round."""
        ...


@dataclass(frozen=True)
class LeafCycleResult:
    node_id: str
    final_state: dict | None
    review: ReviewState | None
    attempts: int
    escalated: bool
    escalation_payload: dict | None = None


ATTACK_CHECK_MAX_RETRIES = 2


def run_leaf_cycle(node: Node, client, executor: Executor, library,
                    max_attempts: int = escalation.DEFAULT_MAX_ATTEMPTS) -> LeafCycleResult:
    """One leaf's full lifecycle: emit -> (attack-check gate, if the pattern
    needs it) -> execute -> review -> escalation.decide() -> retry with
    feedback, or stop. Mirrors exactly the manual sequence run by hand for
    the noise leaf and the percussion leaf this session, as reusable code."""
    from leaf_emit import (  # noqa: E402 -- see scripts/leaf_emit.py's own
        emit_leaf_implementation,   # docstring for why this lives in scripts/,
        feedback_for_attack_failure,  # not src/planner/: no standalone REAPER
        min_note_length_beats,        # client exists outside a real session,
        needs_attack_check,           # so it was written as a script, not a
    )                                  # package module, before this pipeline
                                       # existed to import it from.

    feedback: str | None = None
    attempt = 0
    attack_retries = 0

    while True:
        attempt += 1
        impl = emit_leaf_implementation(node, client, feedback=feedback)
        ops = impl["ops"]

        if needs_attack_check(ops):
            preset_path = ops[0]["args"]["preset_path"]
            track_index = ops[0]["args"]["track_index"]
            fx_index = ops[0]["args"]["fx_index"]
            note_beats = min_note_length_beats(ops)
            measurement = executor.test_attack(track_index, fx_index, preset_path)
            ok, reason = attack_ok_for_note_length(measurement, note_beats)
            if not ok:
                attack_retries += 1
                if attack_retries > ATTACK_CHECK_MAX_RETRIES:
                    # Structural gap this deliberately does NOT paper over:
                    # give up gating and let the real render/review catch it
                    # instead of looping forever on attack-check alone.
                    pass
                else:
                    feedback = feedback_for_attack_failure(preset_path, note_beats, reason)
                    continue

        node.body.implementation.update(impl)
        state = executor.execute_leaf(node.node_id, ops)
        review, score = review_leaf(node, state, library)
        decision = escalation.decide(node, review, attempt=attempt, score=score,
                                      max_attempts=max_attempts)

        if decision.action == "pass":
            return LeafCycleResult(node.node_id, state, review, attempt, escalated=False)
        if decision.action == "retry":
            feedback = escalation.feedback_for_retry(review)
            continue
        return LeafCycleResult(node.node_id, state, review, attempt, escalated=True,
                                escalation_payload=decision.payload)


@dataclass(frozen=True)
class CompositionCycleResult:
    final_review: ReviewState
    review_history: list[ReviewState] = field(default_factory=list)
    strategy_history: list[str] = field(default_factory=list)
    escalated: bool = False


DEFAULT_MAX_ROUNDS = 4  # generous relative to orchestrate.py's own
                         # max_non_improving=2 default -- lets one strategy
                         # switch happen and still leave room to try the
                         # other before this cycle itself gives up.


def run_composition_fix_cycle(parent: Node, sibling_info_fn, get_sibling_states,
                               get_combined_state, executor: Executor, client,
                               max_rounds: int = DEFAULT_MAX_ROUNDS) -> CompositionCycleResult:
    """One composition-level fix cycle for `parent`'s children: review ->
    orchestrate.choose_fix_strategy() -> (if mix_fix) propose+apply fixes,
    with the compensating-gain follow-up applied automatically for any
    eq_cut/highpass fix -> re-review -> repeat, exactly the manual sequence
    run by hand this session on both the drop backbone and the build
    section's texture layer.

    sibling_info_fn: () -> {node_id: {own_purpose, track_index, lufs,
    sample_peak_db, centroid_hz}} built from CURRENT sibling states, called
    fresh each round (mix_fix.propose_composition_fix's own contract: pass
    current values, not the original failure's numbers).

    Explicitly does NOT attempt leaf_retry itself -- orchestrate.py's own
    documented scope never picks *which* sibling a leaf_retry should target
    (that requires reading which node_ids a composition failure actually
    names, a judgment call this project has consistently kept explicit, not
    string-parsed here). A `leaf_retry` decision ends this cycle for the
    caller to route into run_leaf_cycle() on whichever sibling it judges is
    the real target."""
    sibling_states = get_sibling_states()
    combined = get_combined_state()
    review = review_composition(sibling_states, combined_state=combined)
    review_history = [review]
    strategy_history: list[str] = []
    prior_fixes: list[dict] | None = None

    for _ in range(max_rounds):
        decision = orchestrate.choose_fix_strategy(review_history, strategy_history)

        if decision.action == "done":
            return CompositionCycleResult(review_history[-1], review_history,
                                           strategy_history, escalated=False)
        if decision.action in ("leaf_retry", "escalate"):
            return CompositionCycleResult(review_history[-1], review_history,
                                           strategy_history, escalated=True)

        # mix_fix
        sibling_info = sibling_info_fn(sibling_states)
        fixes = mix_fix.propose_composition_fix(
            parent, review_history[-1], sibling_info, client, prior_fixes=prior_fixes,
        )
        for fix in fixes:
            target_id = fix["target_node_id"]
            pre_lufs = sibling_states[target_id]["measured"]["lufs"]
            executor.apply_fix(fix)
            if fix["type"] in ("eq_cut", "highpass"):
                post_state = executor.remeasure(target_id)
                comp = mix_fix.compensating_gain_db(pre_lufs, post_state["measured"]["lufs"])
                if comp:
                    executor.set_gain(target_id, comp)

        prior_fixes = fixes
        strategy_history.append("mix_fix")
        sibling_states = get_sibling_states()
        combined = get_combined_state()
        review = review_composition(sibling_states, combined_state=combined)
        review_history.append(review)

    return CompositionCycleResult(review_history[-1], review_history,
                                   strategy_history, escalated=True)
