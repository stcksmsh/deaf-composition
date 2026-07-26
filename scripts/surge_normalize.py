#!/usr/bin/env python3
"""
Convert a Surge-native param value into the normalized [0,1] value REAPER's
TrackFX_SetParam expects, using scripts/surge_param_map.json (index -> ctrltype/range).

Usage:
    from surge_normalize import load_map, normalize
    param_map = load_map()
    norm = normalize(param_map[index], raw_value)  # raw_value in Surge's own units
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_map():
    return json.loads((ROOT / "scripts/surge_param_map.json").read_text())


def normalize(param_entry, raw_value, enum_max=None):
    """
    param_entry: one entry from surge_param_map.json.
    raw_value: the value in Surge's native units (as stored in a patch/preset).
    enum_max: required only for entries whose ctrltype has a runtime-sized enum
        (param_entry["max"] is None) -- pass enum_count - 1, found by querying
        REAPER's TrackFX_GetParameterStepSizes for that param index live.
    """
    if not param_entry["resolved"]:
        raise ValueError(
            f"param {param_entry['index']} ({param_entry['name']!r}) is not resolved: "
            f"{param_entry.get('note', 'no ctrltype known')}"
        )
    lo = param_entry["min"]
    hi = param_entry["max"]
    if hi is None:
        if enum_max is None:
            raise ValueError(
                f"param {param_entry['index']} ({param_entry['name']!r}) has a runtime-sized "
                f"enum range -- pass enum_max (query TrackFX_GetParameterStepSizes live)"
            )
        hi = enum_max
    if hi == lo:
        return 0.0
    return max(0.0, min(1.0, (raw_value - lo) / (hi - lo)))
