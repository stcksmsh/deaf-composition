#!/usr/bin/env python3
"""One-off script (2026-07-29): re-emit the 5 leaves that used the now-
excluded Percussion/Drum One.fxp preset. Confirmed live that the preset
is fundamentally non-functional (silent across a full 6-octave sweep),
so patching overrides can't fix these -- only a fresh emission with a
different preset can. Prints the new implementation ops for each leaf;
does NOT touch song_plan.json or REAPER directly (the controlling
session applies the result live and updates the plan after verifying).
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import anthropic

from src.planner.node import Node
from scripts.leaf_emit import emit_leaf_implementation

TARGET_IDS = [
    "song/section_1/child_1/child_1",
    "song/section_2/child_2/child_1",
    "song/section_2/child_2/child_2",
    "song/section_4/child_3/child_1",
    "song/section_4/child_3/child_2",
]


def main() -> None:
    plan = json.load(open("state/song_plan/song_plan.json"))
    nodes = plan["nodes"]
    tempo_bpm = plan.get("tempo_bpm", 120.0)
    time_sig = plan.get("time_signature_numerator", 4)
    by_id = {n["node_id"]: n for n in nodes}

    client = anthropic.Anthropic()

    results = {}
    for node_id in TARGET_IDS:
        raw = by_id[node_id]
        node = Node.from_dict(raw)
        print(f"=== re-emitting {node_id} (track {raw['body']['implementation']['ops'][0]['args']['track_index']}) ===", file=sys.stderr)
        try:
            impl = emit_leaf_implementation(
                node, client,
                duration_s=raw["duration_s"],
                tempo_bpm=tempo_bpm,
                time_signature_numerator=time_sig,
                retries=7,
            )
        except Exception as e:
            print(f"  !! FAILED: {e}", file=sys.stderr)
            continue
        results[node_id] = impl
        preset = next((op["args"]["preset_path"] for op in impl["ops"] if op["tool"] == "apply_surge_preset"), None)
        print(f"  -> preset: {preset}", file=sys.stderr)

    out_path = "state/scratch/reemitted_drum_leaves.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"wrote {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
