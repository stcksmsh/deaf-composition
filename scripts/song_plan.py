#!/usr/bin/env python3
"""Turns a locked-in arc (state/song_plan/arc.json, from a real plan_arc()
call -- see src/planner/arc.py) into a fully planned song tree: one section
root Node per arc entry, each decomposed into real leaves via
scheduler.build_tree() (Sonnet decompose + Haiku emit, both real LLM
calls), with a shared track counter across the whole song and a real
timeline_start_s per section (the cumulative sum of prior sections'
duration_s) copied onto every leaf under it.

Plan-only, like every prior proof script in this project -- no REAPER calls
happen here. The controlling MCP-capable session executes
state/song_plan/song_plan.json's leaves live afterward (apply_surge_preset,
create_midi_item, add_midi_notes_batch, set_item_position), section by
section, with real review/mix-fix in between -- see this session's plan
for the full execution design; that part isn't scriptable the same way
since no standalone client exists for the reaper-mcp tools outside a live
session.

Run:
    set -a; source .env; set +a
    .venv/bin/python scripts/song_plan.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import anthropic

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from planner.node import AcceptanceCriteria, Node, ScopeLink, Split  # noqa: E402
from planner.scheduler import build_tree, _Counter  # noqa: E402

ARC_PATH = ROOT / "state/song_plan/arc.json"
OUT_PATH = ROOT / "state/song_plan/song_plan.json"
TRACK_START_INDEX = 0  # old song's 12 tracks are deleted before this runs


def _set_timeline_start(node: Node, start_s: float, by_id: dict[str, Node]) -> None:
    """Copies timeline_start_s onto a section root and every leaf under it
    -- plumbing, not a creative decision, same division of labor build_tree
    already uses for track_index."""
    node.timeline_start_s = start_s
    if isinstance(node.body, Split):
        for child_id in node.body.children:
            _set_timeline_start(by_id[child_id], start_s, by_id)


def _write(out_path: Path, brief: str, total_s: float, section_roots: list[Node],
           all_nodes: list[Node], registry: dict, complete: bool,
           tempo_bpm: float = 120.0, time_signature_numerator: int = 4) -> None:
    """Writes progress incrementally, after every section -- not just once
    at the end. A leaf-emission failure (e.g. a real, if rare, empty-notes
    retry exhaustion) used to abort the whole run with NOTHING written,
    losing every already-paid-for API call for earlier sections. `complete`
    records whether this is a full run or a partial one left by a crash, so
    a resumed run isn't mistaken for a finished plan."""
    out = {
        "brief": brief,
        "total_duration_s": total_s,
        "complete": complete,
        "tempo_bpm": tempo_bpm,
        "time_signature_numerator": time_signature_numerator,
        "section_root_ids": [r.node_id for r in section_roots],
        "nodes": [n.to_dict() for n in all_nodes],
        "recurring_elements_registry": registry,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")


def main() -> int:
    arc = json.loads(ARC_PATH.read_text())
    sections = arc["sections"]
    brief = arc["brief"]
    # Older arc.json files (pre-2026-07-27) never had this key -- default to
    # empty rather than requiring every existing plan to be regenerated.
    recurring_elements = arc.get("recurring_elements", [])
    # Older arc.json files (pre-2026-07-29, before tempo/time-signature
    # became a real arc-level creative decision instead of a hardcoded
    # 120bpm/4-4 assumption) never had these keys either -- same
    # backward-compat default.
    tempo_bpm = arc.get("tempo_bpm", 120.0)
    time_signature_numerator = arc.get("time_signature_numerator", 4)

    decompose_client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    emit_client = decompose_client

    album_summary = ScopeLink(level="album", summary=brief)
    track_counter = _Counter(TRACK_START_INDEX)

    # element_id -> {"description":, "realization": {node_id, preset_path,
    # note_summary} | None} -- built up across the whole sequential loop
    # below, since only this loop (not any single build_tree() call) knows
    # what an EARLIER section actually realized an element as by the time a
    # LATER section needs to recall it.
    registry: dict[str, dict] = {
        e["element_id"]: {"description": e["description"], "realization": None}
        for e in recurring_elements
    }

    all_nodes: list[Node] = []
    section_roots: list[Node] = []
    timeline_start_s = 0.0

    for i, sec in enumerate(sections):
        root = Node(
            node_id=f"song/section_{i}",
            own_purpose=sec["own_purpose"],
            spec=sec["spec"],
            acceptance_criteria=AcceptanceCriteria(structural_facts={}),
            scope_chain=(album_summary,),
            body=Split(children=()),
            duration_s=sec["duration_s"],
            locked_grid=sec["locked_grid"],
            grid_justification=sec["grid_justification"],
        )
        print(f"[section {i}] decomposing: {sec['target_section_type']} "
              f"({sec['duration_s']}s) -- {sec['own_purpose'][:70]}...")

        section_context = []
        for e in recurring_elements:
            if i not in e["section_indices"]:
                continue
            is_recurrence = i != e["section_indices"][0]
            entry = {
                "element_id": e["element_id"],
                "description": e["description"],
                "is_recurrence": is_recurrence,
                "prior_realization": registry[e["element_id"]]["realization"] if is_recurrence else None,
            }
            section_context.append(entry)
            if is_recurrence and entry["prior_realization"] is None:
                print(f"           !! element {e['element_id']!r} scheduled as a "
                      f"recurrence here, but no prior realization is recorded yet "
                      f"(its origin section hasn't produced one) -- passing it as "
                      f"a first-appearance instead")
                entry["is_recurrence"] = False

        try:
            leaves, section_nodes, element_realizations = build_tree(
                root, decompose_client, emit_client,
                target_section_type=sec["target_section_type"],
                duration_s=sec["duration_s"],
                track_counter=track_counter,
                max_depth=4,
                recurring_context=section_context or None,
                tempo_bpm=tempo_bpm, time_signature_numerator=time_signature_numerator,
            )
        except Exception:
            print(f"\n!!! section {i} ({sec['target_section_type']}) failed to "
                  f"build -- writing the {len(section_roots)} section(s) already "
                  f"completed before re-raising, so that work isn't lost.")
            _write(OUT_PATH, brief, timeline_start_s, section_roots, all_nodes,
                   registry, complete=False,
                   tempo_bpm=tempo_bpm, time_signature_numerator=time_signature_numerator)
            raise
        by_id = {n.node_id: n for n in [root] + section_nodes}
        _set_timeline_start(root, timeline_start_s, by_id)

        for element_id, realization in element_realizations.items():
            registry[element_id]["realization"] = realization
            print(f"           -> element {element_id!r} realized: "
                  f"{realization['node_id']} / {realization['preset_path']}")

        print(f"           -> {len(leaves)} leaf(s), tracks "
              f"{[l.body.implementation['track_index'] for l in leaves]}, "
              f"starts at {timeline_start_s:.0f}s")

        section_roots.append(root)
        all_nodes.append(root)
        all_nodes += section_nodes
        timeline_start_s += sec["duration_s"]

        _write(OUT_PATH, brief, timeline_start_s, section_roots, all_nodes,
               registry, complete=(i == len(sections) - 1),
               tempo_bpm=tempo_bpm, time_signature_numerator=time_signature_numerator)

    total_s = timeline_start_s
    print(f"\n=== {len(section_roots)} sections, {total_s:.0f}s total, "
          f"{len(all_nodes)} nodes -- plan written: {OUT_PATH} ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
