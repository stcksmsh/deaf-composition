#!/usr/bin/env python3
"""
DSL emission (plan §6/§8.1): given one Leaf node's spec, have a real model
call -- Haiku, per §6's routing table -- emit the ordered sequence of MCP
tool calls (Leaf.implementation) that realizes it. This is the piece
scripts/leaf_proof.py deliberately hand-wrote instead of generating: that
proof was "does leaf->audio->score work at all," this one is "does a model,
given only the spec and the tool catalog, produce a sane ops list."

Scope, deliberately bounded for this proof (documented, not silently
assumed):
  - The model plans against three "creative" tools only -- apply_surge_preset,
    create_midi_item, add_midi_notes_batch. Rendering is deterministic
    plumbing derived from the emitted MIDI item, not a creative decision
    (matches the Leaf definition in node.py: "no remaining creative
    sub-decision"), so this script appends the render op itself rather than
    asking the model to plan it.
  - Exactly one MIDI item per leaf, referenced by the fixed placeholder
    item_index=0 in add_midi_notes_batch -- sidesteps needing multi-turn
    execution feedback (create_midi_item's real item_index isn't known until
    it actually runs) without inventing a general placeholder-resolution
    protocol. A leaf needing multiple items is out of scope for this proof.
  - This script only emits and validates the plan; it does not execute it
    (no standalone MCP client exists for the ~150 reaper-mcp tools outside
    an actual MCP session -- see surge_bridge_client.py's docstring for why
    that gap exists). Execution happens the same way leaf_proof.py's did:
    the controlling Claude Code session runs the emitted ops verbatim
    through its own loaded mcp__reaper__* / mcp__deaf_composition__* tools.

Run:
    set -a; source .env; set +a
    .venv/bin/python scripts/leaf_emit.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import anthropic

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from planner.node import (  # noqa: E402
    AcceptanceCriteria, Leaf, ModelTier, Node, ScopeLink,
)

MODEL = "claude-haiku-4-5-20251001"
SURGE_FACTORY_DIR = Path("/usr/share/surge-xt/patches_factory")
# Every category except the two that aren't real sonic content -- broadened
# from "Pads only" after a real retro finding: the pulse leaf in
# build_section_review.py picked a Pads preset (slow attack/release) for a
# rhythmic part of short staccato notes and rendered at -52 LUFS, essentially
# inaudible, because nothing offered was ever going to have a fast enough
# attack for that job. Plucks/Percussion/Basses etc. are real options now.
EXCLUDED_CATEGORIES = {"Tutorials", "Templates"}
SURGE_PARAM_MAP = Path(__file__).resolve().parent / "surge_param_map.json"

TOOL_CATALOG = [
    {
        "name": "apply_surge_preset",
        "description": (
            "Apply a Surge XT factory .fxp preset to a Surge XT instance already "
            "present at (track_index, fx_index), then optionally override named "
            "params. preset_path is relative to Surge's factory patch library, "
            "e.g. 'Pads/Distant.fxp'. overrides is {param_name: raw_native_value} -- "
            "param_name MUST be copied verbatim from the valid_override_names list "
            "given below; there is no other way to know a real param's exact name, "
            "and a name that isn't in that list will fail. ct_envtime params "
            "(names ending Attack/Decay/Release/Delay/Hold) are log2(seconds) -- "
            "0.0=1s, -1.0=0.5s, 1.0=2s. ct_percent params (Sustain, Resonance, "
            "Mix, ...) are plain 0-1. When in doubt, omit overrides entirely -- "
            "the preset's own defaults are always valid."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "track_index": {"type": "integer"},
                "fx_index": {"type": "integer"},
                "preset_path": {"type": "string"},
                "overrides": {"type": "object", "additionalProperties": {"type": "number"}},
            },
            "required": ["track_index", "fx_index", "preset_path"],
        },
    },
    {
        "name": "create_midi_item",
        "description": "Create one empty MIDI item on a track. position/length in seconds.",
        "input_schema": {
            "type": "object",
            "properties": {
                "track_index": {"type": "integer"},
                "position": {"type": "number"},
                "length": {"type": "number"},
            },
            "required": ["track_index", "position", "length"],
        },
    },
    {
        "name": "add_midi_notes_batch",
        "description": (
            "Add notes to the MIDI item this leaf created. Always pass "
            "item_index=0 -- this leaf creates exactly one item, and 0 always "
            "refers to it. notes: list of {pitch (0-127), velocity (1-127), "
            "start_beat, length_beats}, timed against the item's own start, at "
            "the project tempo (120bpm, 4/4, given in the spec below)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "track_index": {"type": "integer"},
                "item_index": {"type": "integer"},
                "notes": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "pitch": {"type": "integer"},
                            "velocity": {"type": "integer"},
                            "start_beat": {"type": "number"},
                            "length_beats": {"type": "number"},
                        },
                        "required": ["pitch", "velocity", "start_beat", "length_beats"],
                    },
                },
            },
            "required": ["track_index", "item_index", "notes"],
        },
    },
]


def build_spec_node() -> Node:
    """The leaf spec the model gets -- own_purpose/spec/acceptance_criteria are
    exactly what a real fold-decompose step would hand down; nothing about the
    implementation is given."""
    return Node(
        node_id="proof/leaf_intro_texture",
        own_purpose=(
            "Prove a leaf spec becomes correct audio when the DSL ops are "
            "emitted by a real model call, not hand-written (plan §11 stage 3, "
            "the emission half this time, not just execution)."
        ),
        spec=(
            "On the 'TEXTURE / ATMOS' track (track_index=12 in this project's "
            "numbering, its Surge XT instance is fx_index=0), load a factory "
            "preset suited to a sparse, atmospheric album intro and play one "
            "long sustained chord or note across the full 8-bar item (120bpm, "
            "4/4) -- this is the intro's sole textural layer, so it should read "
            "as spacious and unhurried, not rhythmic or busy."
        ),
        acceptance_criteria=AcceptanceCriteria(
            target_section_type="intro",
            max_measured_distance=3.0,
            max_embedding_distance=0.8,
            structural_facts={"instrument": "Surge XT", "bars": 8},
        ),
        scope_chain=(
            ScopeLink(level="album", summary="A deaf-composed machine-music record."),
            ScopeLink(level="song", summary="Opening track, establishes the record's world."),
            ScopeLink(level="section", summary="The intro's sole atmospheric texture layer."),
        ),
        body=Leaf(implementation={}),  # filled in by emit_leaf_implementation
        assigned_model=ModelTier.HAIKU,
    )


def _factory_preset_names() -> list[str]:
    names = []
    for category_dir in sorted(SURGE_FACTORY_DIR.iterdir()):
        if not category_dir.is_dir() or category_dir.name in EXCLUDED_CATEGORIES:
            continue
        names += [f"{category_dir.name}/{p.name}" for p in sorted(category_dir.glob("*.fxp"))]
    return names


def _valid_override_names() -> set[str]:
    """The exact same source of truth apply_overrides() itself checks
    against (surge_param_map.json's resolved param names) -- giving the
    model this list up front, and validating against it before ever
    calling REAPER, closes the gap that let it invent "Master Volume" and
    "Filter Cutoff" twice this session: apply_surge_preset correctly
    raised both times, but only after a live ~2-minute preset-apply call
    had already run. Catching it here is instant and doesn't burn a real
    REAPER round-trip on a name that was never going to work."""
    param_map = json.loads(SURGE_PARAM_MAP.read_text())
    return {e["name"] for e in param_map if e.get("resolved")}


def emit_leaf_implementation(node: Node, client: anthropic.Anthropic,
                              feedback: str | None = None, retries: int = 2) -> dict:
    preset_names = _factory_preset_names()
    valid_overrides = _valid_override_names()

    def build_prompt(extra_feedback: str | None) -> str:
        return f"""You are planning the implementation of one leaf node in a \
recursive music-composition tree. A leaf is translation, not composition: \
you are given a fully-specified creative decision and must express it as a \
bounded set of deterministic tool calls -- nothing here is left to your \
own creative judgment beyond picking which preset name and which notes best \
match the spec.

own_purpose: {node.own_purpose}
spec: {node.spec}
acceptance_criteria: {json.dumps(node.acceptance_criteria.to_dict())}
scope_chain: {json.dumps([{"level": s.level, "summary": s.summary} for s in node.scope_chain])}

Available Surge XT factory presets, every category (preset_path must be \
exactly one of these, "<Category>/<name>.fxp" -- pick whichever category \
actually fits the part: a rhythmic/percussive part needs a fast attack \
(Plucks, Percussion), a sustained texture needs a slow one (Pads), etc.):
{json.dumps(preset_names, indent=2)}

valid_override_names (apply_surge_preset's overrides keys MUST come from \
this exact list verbatim, or be omitted entirely -- no other name will work):
{json.dumps(sorted(valid_overrides), indent=2)}
{f"{chr(10)}{extra_feedback}{chr(10)}" if extra_feedback else ""}
Emit the tool calls needed to realize this leaf, in the exact order they \
must execute: one apply_surge_preset call, one create_midi_item call, then \
one add_midi_notes_batch call (item_index=0). Call each tool exactly once, \
in that order, in this single turn."""

    last_error: Exception | None = None
    running_feedback = feedback
    for attempt in range(retries + 1):
        response = client.messages.create(
            model=MODEL,
            max_tokens=2048,
            tools=TOOL_CATALOG,
            tool_choice={"type": "any"},
            messages=[{"role": "user", "content": build_prompt(running_feedback)}],
        )
        ops = [{"tool": block.name, "args": block.input}
               for block in response.content if block.type == "tool_use"]
        try:
            _validate_ops(ops, valid_overrides)
            return {"ops": ops, "source": f"model-emitted ({MODEL})"}
        except ValueError as e:
            last_error = e
            running_feedback = (
                f"{feedback + ' ' if feedback else ''}Your previous attempt was "
                f"structurally invalid: {e}. Fix this specific problem."
            )
    raise RuntimeError(
        f"emit_leaf_implementation produced an invalid plan {retries + 1} times "
        f"in a row: {last_error}"
    )


def _validate_ops(ops: list[dict], valid_overrides: set[str] | None = None) -> None:
    """Fail loudly on a malformed plan rather than silently patching it --
    per Leaf's own definition, a leaf has no remaining creative sub-decision,
    so there's nothing legitimate to improvise here if the model got the
    mechanical shape wrong. Checking override names here (not just at
    apply_surge_preset's own call time) catches a hallucinated name before
    it costs a real ~2-minute REAPER round-trip, not just eventually."""
    names = [op["tool"] for op in ops]
    expected = ["apply_surge_preset", "create_midi_item", "add_midi_notes_batch"]
    if names != expected:
        raise ValueError(f"expected op sequence {expected}, model emitted {names}")
    if ops[2]["args"].get("item_index") != 0:
        raise ValueError(
            f"add_midi_notes_batch must use item_index=0 (the placeholder for "
            f"this leaf's one MIDI item), got {ops[2]['args'].get('item_index')!r}"
        )
    if valid_overrides is not None:
        overrides = ops[0]["args"].get("overrides") or {}
        invalid = set(overrides) - valid_overrides
        if invalid:
            raise ValueError(
                f"apply_surge_preset overrides used unknown param name(s) "
                f"{sorted(invalid)} -- not in valid_override_names"
            )


def main() -> int:
    node = build_spec_node()
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    implementation = emit_leaf_implementation(node, client)

    node.body.implementation.update(implementation)
    print(json.dumps(implementation, indent=2))

    out_path = ROOT / "state/leaf_proof/leaf_intro_texture.plan.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({
        "node": node.to_dict(),
        "implementation": implementation,
    }, indent=2, sort_keys=True) + "\n")
    print(f"\nplan written: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
