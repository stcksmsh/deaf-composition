#!/usr/bin/env python3
"""
Supplementary local MCP server for this project's own leaf-vocabulary extensions
-- tools that sit alongside the twelvetake-reaper-mcp server's ~150 tools, per
plan §8.1 ("the MCP's typed tools are the DSL"). Doesn't touch that vendored
package; this is ours, versioned in this repo.

First and so far only tool: apply_surge_preset. Raw TrackFX_SetParam calls can't
practically express "load Bass 5" (778 params, ~500 of them meaningfully set) --
a leaf model shouldn't have to emit that, and even if it could, review/escalation
would be looking at a wall of numbers instead of "loaded Bass 5, faster attack."
This tool is the fix: a single call wrapping the already-built, already-verified
apply_preset() + apply_overrides() pipeline (scripts/apply_surge_preset_live.py).

Requires: reaper_mcp_bridge.lua running (scripts/start_reaper_mcp_bridge.sh start),
same as everything else built on scripts/surge_bridge_client.py.

Run:
    .venv/bin/python scripts/deaf_composition_mcp_server.py
Registered in .mcp.json as a second server alongside "reaper".
"""
from __future__ import annotations

import sys
from pathlib import Path

from mcp.server.fastmcp import FastMCP

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from apply_surge_preset_live import apply_preset, apply_overrides  # noqa: E402

SURGE_FACTORY_PATCHES = Path("/usr/share/surge-xt/patches_factory")

mcp = FastMCP(
    "deaf-composition",
    instructions=(
        "Project-specific tools that extend the reaper-mcp DSL. Currently just "
        "apply_surge_preset -- use it whenever a leaf needs a Surge XT instance "
        "to sound like a specific patch, instead of individual TrackFX_SetParam calls."
    ),
)


def _resolve_preset_path(preset_path: str) -> Path:
    p = Path(preset_path)
    if p.is_file():
        return p
    candidate = SURGE_FACTORY_PATCHES / preset_path
    if candidate.is_file():
        return candidate
    raise FileNotFoundError(
        f"no such preset: {preset_path!r} (checked as given, and under {SURGE_FACTORY_PATCHES})"
    )


@mcp.tool()
def apply_surge_preset(
    track_index: int,
    fx_index: int,
    preset_path: str,
    overrides: dict[str, float] | None = None,
) -> dict:
    """
    Apply a Surge XT factory .fxp preset to a Surge XT instance already present
    at (track_index, fx_index), then optionally override specific named params.

    preset_path: absolute path, or a path relative to Surge's factory patch
        library (e.g. "Basses/Bass 5.fxp").
    overrides: {param_name: raw_value_in_surge_native_units}, applied after the
        base preset. Param names match REAPER's own display names for Surge XT
        (e.g. "A Amp EG Release", "A Filter 1 Cutoff") -- ct_envtime-family params
        (Attack/Decay/Release/Delay/Hold) are log2(seconds): 0.0 = 1s, -1.0 = 0.5s,
        1.0 = 2s. ct_percent-family params (Sustain, Resonance, ...) are plain 0-1.
        Raises immediately on an unknown name or a type-dependent (unsettable) one
        -- both are caller mistakes worth failing loudly on.

    Returns a compact summary, not per-param detail (778 params is too much to put
    in a tool result) -- counts of what was applied/skipped, plus what each
    override actually resolved to.
    """
    resolved_path = _resolve_preset_path(preset_path)
    stats, subtype_details = apply_preset(str(resolved_path), track_index, fx_index)

    applied_overrides = {}
    if overrides:
        applied_overrides = apply_overrides(track_index, fx_index, overrides)

    return {
        "preset_path": str(resolved_path),
        "track_index": track_index,
        "fx_index": fx_index,
        "stats": stats,
        "subtype_params_resolved": len(subtype_details),
        "overrides_applied": applied_overrides,
    }


if __name__ == "__main__":
    mcp.run()
