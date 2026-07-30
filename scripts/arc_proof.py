#!/usr/bin/env python3
"""Real plan_arc call (src/planner/arc.py) for one song brief: the
top-level arc decision (how many sections, order, type, duration each)
that has never existed before this session -- every prior section
(intro/build/drop) was hand-picked by whoever called build_section_proof.py
et al., never planned as a whole song. This script only plans and
prints/writes the result -- see scheduler.py's own docstring for why
execution against real REAPER happens in the controlling MCP-capable
session afterward. Wiring this output into build_tree() for a live
full-song run is explicitly future work, not done here.

Run:
    set -a; source .env; set +a
    .venv/bin/python scripts/arc_proof.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import anthropic

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from planner.arc import plan_arc  # noqa: E402

BRIEF = (
    "A deaf-composed machine-music track (120bpm, 4/4). No fixed structure "
    "requirement -- decide the real arc: how many sections, what order, "
    "what type each is, how long each runs. Free to repeat section types, "
    "skip a drop entirely, or do something the 5 reference types don't "
    "name, as long as it's grounded and not wildly outside anything real "
    "music does."
)


def main() -> int:
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    plan = plan_arc(BRIEF, client)
    sections = plan["sections"]
    recurring = plan["recurring_elements"]

    total_s = sum(s["duration_s"] for s in sections)
    print(f"=== arc: {len(sections)} sections, {total_s:.0f}s total ===\n")
    for i, s in enumerate(sections):
        grid_note = f" [locked_grid: {s['grid_justification']}]" if s["locked_grid"] else ""
        print(f"[{i}] {s['target_section_type']} ({s['duration_s']:.0f}s){grid_note}")
        print(f"    own_purpose: {s['own_purpose']}")
        print(f"    spec: {s['spec']}\n")

    print(f"=== {len(recurring)} recurring element(s) ===")
    for e in recurring:
        print(f"  [{e['element_id']}] sections {e['section_indices']}: {e['description']}")

    out_path = ROOT / "state/arc_proof/arc_plan.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(
        {"brief": BRIEF, "sections": sections, "recurring_elements": recurring},
        indent=2, sort_keys=True) + "\n")
    print(f"plan written: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
