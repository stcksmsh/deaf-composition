#!/usr/bin/env python3
"""
Actually apply a Surge XT .fxp preset's params to a live REAPER Surge XT instance,
via the direct bridge file protocol (scripts/surge_bridge_client.py) -- one process,
one script, ~500+ TrackFX_SetParam calls, rather than that many individual MCP tool
round-trips.

Order matters for the 4 filter-subtype params: each slot's "Type" must be set BEFORE
probing that slot's subtype enum size, since subtype's choice count depends on which
filter type is active. So: apply everything from build_apply_plan() first (which
includes both filter Types), THEN resolve+apply the state-dependent subtypes.

Usage:
    python scripts/apply_surge_preset_live.py <path-to.fxp> <track_index> <fx_index>
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from apply_surge_preset import build_apply_plan, STATE_DEPENDENT_ENUM_CTRLTYPES  # noqa: E402
from surge_bridge_client import call  # noqa: E402
from surge_normalize import load_map, normalize  # noqa: E402

_ENUM_SIZES = json.loads((ROOT / "scripts/surge_enum_sizes.json").read_text())


def set_param(track, fx, index, norm):
    resp = call("TrackFX_SetParam", [track, fx, index, norm])
    if not resp.get("ok"):
        raise RuntimeError(f"SetParam failed for index {index}: {resp}")


def format_value(track, fx, index, norm):
    resp = call("TrackFX_FormatParamValueNormalized", [track, fx, index, norm])
    if not resp.get("ok"):
        raise RuntimeError(f"FormatParamValueNormalized failed for index {index}: {resp}")
    return resp["ret"]


def probe_enum_size(track, fx, index, scan_points=61):
    labels = [format_value(track, fx, index, i / (scan_points - 1)) for i in range(scan_points)]
    distinct = 1
    for a, b in zip(labels, labels[1:]):
        if a != b:
            distinct += 1
    return distinct


def apply_preset(fxp_path, track, fx, verbose=False):
    """
    Apply a Surge XT .fxp preset's params to a live Surge XT instance at
    (track, fx). Returns (stats, applied_subtype_details) -- stats is the same
    dict build_apply_plan() reports (counts of applied/skipped/etc.), and
    applied_subtype_details lists what each state-dependent subtype resolved to,
    for logging/debugging.

    Requires the target instance to already be Surge XT at that track/fx slot,
    and the reaper_mcp_bridge.lua bridge (with the TrackFX_FormatParamValueNormalized
    case) running and reachable via surge_bridge_client.
    """
    plan, needs_live_subtype, stats = build_apply_plan(fxp_path)

    for entry in plan:
        set_param(track, fx, entry["index"], entry["normalized"])
    if verbose:
        print(f"applied {len(plan)} params directly")

    subtype_details = []
    for entry in needs_live_subtype:
        n = probe_enum_size(track, fx, entry["index"])
        norm = max(0.0, min(1.0, entry["raw"] / (n - 1))) if n > 1 else 0.0
        set_param(track, fx, entry["index"], norm)
        subtype_details.append({**entry, "enum_size": n, "normalized": norm})
        if verbose:
            print(f"  {entry['name']}: raw={entry['raw']} enum_size={n} -> normalized={norm:.4f}")
    if verbose:
        print(f"applied {len(needs_live_subtype)} state-dependent subtype params")

    return stats, subtype_details


def apply_overrides(track, fx, overrides, verbose=False):
    """
    overrides: {param_name: raw_value_in_surge_native_units}, using the same
    human-readable names as surge_param_map.json ("A Amp EG Release", etc.) --
    applied AFTER a base preset, so a leaf can say "this preset, but faster attack"
    without hand-computing normalized values.

    Raises KeyError for an unknown name, ValueError for an unresolved param (the
    239 type-dependent ones from build_surge_param_map.py) -- both are caller
    errors worth failing loudly on, not silently skipping.
    """
    param_map = load_map()
    by_name = {e["name"]: e for e in param_map}
    applied = {}
    for name, raw in overrides.items():
        if name not in by_name:
            raise KeyError(f"no such Surge param: {name!r}")
        entry = by_name[name]
        if not entry["resolved"]:
            raise ValueError(
                f"{name!r} is not a settable param (type-dependent, ctrltype "
                f"{entry.get('ctrltype')!r}): {entry.get('note', '')}"
            )
        if entry.get("max") is None:
            ctrltype = entry["ctrltype"]
            if ctrltype in STATE_DEPENDENT_ENUM_CTRLTYPES:
                n = probe_enum_size(track, fx, entry["index"])
            else:
                n = _ENUM_SIZES[ctrltype]["n"]
            norm = normalize(entry, raw, enum_max=n - 1)
        else:
            norm = normalize(entry, raw)
        set_param(track, fx, entry["index"], norm)
        applied[name] = norm
        if verbose:
            print(f"  override {name}: raw={raw} -> normalized={norm:.4f}")
    return applied


def main():
    if len(sys.argv) != 4:
        print("usage: apply_surge_preset_live.py <path-to.fxp> <track_index> <fx_index>", file=sys.stderr)
        return 1
    fxp_path, track, fx = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])

    stats, _ = apply_preset(fxp_path, track, fx, verbose=True)
    print(json.dumps(stats, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
