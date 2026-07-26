#!/usr/bin/env python3
"""
Determine the real enum size (choice count) for each of Surge's runtime-sized
ctrltypes (VARIABLE_MAX in build_surge_param_map.py), by formatting normalized
values against a live Surge XT instance and counting label transitions.

REAPER's TrackFX_GetParameterStepSizes returns retval=false for these VST3 params
(confirmed empirically -- it doesn't work for this plugin), so this uses
TrackFX_FormatParamValueNormalized instead, which does. Coarse-scans 61 points
(1/60 resolution) per ctrltype; good enough since none of Surge's enums here run
past ~50 options.

ct_filtersubtype is deliberately excluded: its choice count depends on which
filter TYPE is currently selected in that specific slot, not a global constant --
it must be re-probed live, after setting the type, at apply time.

Requires: a running REAPER with the bridge script loaded (scripts/start_reaper_mcp_bridge.sh),
and a track with a Surge XT instance at (track_index, fx_index) -- point PROBE_TRACK/PROBE_FX
at one.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from surge_bridge_client import call  # noqa: E402

PROBE_TRACK = 0
PROBE_FX = 0
SKIP_CTRLTYPES = {"ct_filtersubtype"}
SCAN_POINTS = 61


def format_value(param_index, norm):
    resp = call("TrackFX_FormatParamValueNormalized", [PROBE_TRACK, PROBE_FX, param_index, norm])
    if not resp.get("ok"):
        raise RuntimeError(f"format failed for param {param_index} @ {norm}: {resp}")
    return resp["ret"]


def count_enum_size(param_index):
    labels = []
    for i in range(SCAN_POINTS):
        norm = i / (SCAN_POINTS - 1)
        labels.append(format_value(param_index, norm))
    distinct = 1
    for a, b in zip(labels, labels[1:]):
        if a != b:
            distinct += 1
    return distinct, labels[0], labels[-1]


def main():
    param_map = json.loads((ROOT / "scripts/surge_param_map.json").read_text())
    reps = {}
    for entry in param_map:
        ct = entry["ctrltype"]
        if ct and entry.get("max") is None and ct not in SKIP_CTRLTYPES and ct not in reps:
            reps[ct] = entry["index"]

    sizes = {}
    for ct, idx in sorted(reps.items()):
        n, first, last = count_enum_size(idx)
        sizes[ct] = {"n": n, "sample_index": idx, "first_label": first, "last_label": last}
        print(f"{ct:35s} n={n:3d}  index={idx:4d}  [{first!r} .. {last!r}]")

    dest = ROOT / "scripts/surge_enum_sizes.json"
    dest.write_text(json.dumps(sizes, indent=2))
    print(f"wrote {dest}")


if __name__ == "__main__":
    main()
