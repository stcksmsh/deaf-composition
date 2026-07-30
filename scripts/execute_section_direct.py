#!/usr/bin/env python3
"""Direct-bridge section executor for the live Tidewater Clock build.

Built mid-session after the per-tool-call MCP approach proved too slow and
token-expensive (every add_midi_notes_batch call echoed a per-note "ok":true,
every apply_surge_preset cost a ~2min round-trip tied to a full conversation
turn). This script drives the SAME underlying REAPER bridge the MCP tools use
-- via scripts/surge_bridge_client.py's call() (already proven, built earlier
this session for bridge functions without an MCP wrapper) -- directly from one
Python process. The twelvetake-reaper-mcp tool functions are themselves thin
wrappers over this exact bridge protocol (confirmed by reading
reaper_mcp_server.py directly), so this reuses their exact func/arg mappings,
not a reinvention.

One script run = one whole section: insert tracks, add Surge XT, apply
presets (reusing apply_surge_preset_live.apply_preset, unchanged), create
MIDI items + notes, save, render (combined + one solo pass per leaf), and a
lightweight review_composition pass (measured audio only, no CLAP) -- then
prints ONE compact summary instead of narrating every step.

Usage:
    set -a; source .env; set +a
    .venv/bin/python scripts/execute_section_direct.py <section_index> [track_start_index]
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from apply_surge_preset import STATE_DEPENDENT_ENUM_CTRLTYPES  # noqa: E402
from apply_surge_preset_live import apply_preset, apply_overrides, probe_enum_size  # noqa: E402
from surge_bridge_client import call  # noqa: E402
from surge_normalize import load_map, normalize  # noqa: E402

from planner import review  # noqa: E402
from return_channel import analyze  # noqa: E402

PLAN_PATH = ROOT / "state/song_plan/song_plan.json"
PROJECT_PATH = ROOT / "state/scratch/session.rpp"
BUILD_DIR = ROOT / "state/song_build"
# Was a hardcoded 120.0 -- now read from the plan itself at runtime (set in
# main(), see the `global TEMPO` there) now that tempo is a real per-song
# creative decision (2026-07-29) instead of a fixed pipeline assumption.
# Kept as a module-level default so beats_to_seconds() still works if
# anything imports this module without going through main().
TEMPO = 120.0

_ENUM_SIZES = json.loads((ROOT / "scripts/surge_enum_sizes.json").read_text())
_PARAM_MAP_BY_NAME: dict | None = None


def _param_map_by_name() -> dict:
    """Lazy, cached -- same lookup apply_overrides() already does per-call;
    loaded once here since a section can automate many leaves' params."""
    global _PARAM_MAP_BY_NAME
    if _PARAM_MAP_BY_NAME is None:
        _PARAM_MAP_BY_NAME = {e["name"]: e for e in load_map()}
    return _PARAM_MAP_BY_NAME


def _surge_param_normalized(track_index: int, fx_index: int, param_name: str, raw_value: float) -> tuple[int, float]:
    """Resolves a Surge param name to (REAPER param index, normalized [0,1]
    value) -- the exact same resolve+normalize logic apply_overrides() uses
    for a static override, reused here for an automation point instead of a
    one-shot SetParam."""
    entry = _param_map_by_name()[param_name]
    if entry.get("max") is None:
        ctrltype = entry["ctrltype"]
        if ctrltype in STATE_DEPENDENT_ENUM_CTRLTYPES:
            n = probe_enum_size(track_index, fx_index, entry["index"])
        else:
            n = _ENUM_SIZES[ctrltype]["n"]
        return entry["index"], normalize(entry, raw_value, enum_max=n - 1)
    return entry["index"], normalize(entry, raw_value)


def beats_to_seconds(beats: float) -> float:
    return beats / TEMPO * 60.0


def leaves_for_section(plan: dict, section_idx: int):
    nodes = {n["node_id"]: n for n in plan["nodes"]}
    root = nodes[plan["section_root_ids"][section_idx]]
    out = []

    def walk(node_id):
        n = nodes[node_id]
        if n["body"]["kind"] == "leaf":
            out.append(n)
        else:
            for c in n["body"]["children"]:
                walk(c)

    walk(plan["section_root_ids"][section_idx])
    return root, out


def build_leaf(leaf: dict, timeline_start_s: float, track_name: str) -> None:
    impl = leaf["body"]["implementation"]
    track_index = impl["track_index"]
    preset_op = next(op for op in impl["ops"] if op["tool"] == "apply_surge_preset")
    item_op = next(op for op in impl["ops"] if op["tool"] == "create_midi_item")
    notes_op = next(op for op in impl["ops"] if op["tool"] == "add_midi_notes_batch")

    r = call("InsertTrackAtIndex", [track_index, True])
    if not r.get("ok"):
        raise RuntimeError(f"InsertTrackAtIndex failed for {leaf['node_id']}: {r}")
    call("GetSetMediaTrackInfo_String", [track_index, "P_NAME", track_name, True])
    r = call("TrackFX_AddByName", [track_index, "Surge XT", False, -1])
    if not r.get("ok"):
        raise RuntimeError(f"TrackFX_AddByName failed for {leaf['node_id']}: {r}")
    fx_index = 0

    preset_path = preset_op["args"]["preset_path"]
    full_fxp = f"/usr/share/surge-xt/patches_factory/{preset_path}"
    stats, _ = apply_preset(full_fxp, track_index, fx_index)
    overrides = preset_op["args"].get("overrides") or {}
    if overrides:
        # Reuse the same apply_overrides() the deaf_composition MCP tool itself
        # calls -- handles the state-dependent/runtime-sized enum params (e.g.
        # "A Osc 1 Type") that a naive normalize() can't, since their range
        # depends on a live TrackFX_GetParameterStepSizes query.
        apply_overrides(track_index, fx_index, overrides)

    position = timeline_start_s + item_op["args"]["position"]
    length = item_op["args"]["length"]
    r = call("CreateMIDIItem", [track_index, position, position + length])
    if not r.get("ok"):
        raise RuntimeError(f"CreateMIDIItem failed for {leaf['node_id']}: {r}")
    item_index = 0

    for note in notes_op["args"]["notes"]:
        start_s = beats_to_seconds(note.get("start_beat", 0))
        length_s = beats_to_seconds(note.get("length_beats", 1.0))
        call("InsertMIDINote", [track_index, item_index, note.get("pitch", 60),
                                 start_s, start_s + length_s, note.get("velocity", 100),
                                 note.get("channel", 0)])

    # Optional automation ops (leaf_emit.py's automate_track_envelope /
    # automate_surge_param) -- always appear after the required 3, if at all.
    for op in impl["ops"][3:]:
        if op["tool"] == "automate_track_envelope":
            args = op["args"]
            env_track, env_name = args["track_index"], args["envelope_name"]
            r = call("GetTrackEnvelopeByName", [env_track, env_name])
            # Real bug found live (2026-07-29, same session): this bridge
            # call can return {"ok": True} with NO "ret" envelope pointer
            # for an envelope that has genuinely never been shown on this
            # track -- checking only .get("ok") (as this line originally
            # did) reads that as success and skips the show step, so the
            # InsertEnvelopePoint calls below fail with "Envelope not
            # found" despite this check having just "passed". Must also
            # check for a real "ret" value.
            if not r.get("ok") or not r.get("ret"):
                # REAPER's GetTrackEnvelopeByName returns nil for a real,
                # always-present Volume/Pan/Width envelope if it's never been
                # made visible on this track -- not a bug, just needs the
                # same one-time "show" toggle a human would do by right-
                # clicking the track. Found live: every automate_track_
                # envelope leaf failed here until this was added.
                # "Width" is a real, allowed envelope_name in leaf_emit.py's
                # own tool schema (automate_track_envelope's enum includes
                # it) -- this map was just never extended to match when that
                # schema was written, so a leaf using it correctly per its
                # own contract failed here live (2026-07-29). REAPER's
                # standard action IDs for these three toggles are
                # sequential (40406/40407/40408).
                show_action = {"Volume": 40406, "Pan": 40407, "Width": 40408}.get(env_name)
                if show_action is None:
                    raise RuntimeError(
                        f"no known 'show envelope' action for {env_name!r} "
                        f"({leaf['node_id']}) -- add one to show_action above"
                    )
                call("SetTrackSelected", [env_track, True])
                call("Main_OnCommand", [show_action, 0])
                r = call("GetTrackEnvelopeByName", [env_track, env_name])
                if not r.get("ok") or not r.get("ret"):
                    raise RuntimeError(
                        f"GetTrackEnvelopeByName still failed for "
                        f"{leaf['node_id']} after showing {env_name}: {r}"
                    )
            for pt in args["points"]:
                pt_time = timeline_start_s + pt["time"]
                call("InsertEnvelopePoint", [
                    env_track, env_name, pt_time, pt["value"],
                    pt.get("shape", 0), 0, False, False,
                ])
        elif op["tool"] == "automate_surge_param":
            args = op["args"]
            au_track, au_fx = args["track_index"], args["fx_index"]
            r = call("GetFXEnvelope", [au_track, au_fx,
                                        _param_map_by_name()[args["param_name"]]["index"]])
            if not r.get("ok"):
                raise RuntimeError(f"GetFXEnvelope failed for {leaf['node_id']}: {r}")
            for pt in args["points"]:
                pt_time = timeline_start_s + pt["time"]
                param_index, norm = _surge_param_normalized(
                    au_track, au_fx, args["param_name"], pt["value"]
                )
                call("AddFXEnvelopePoint", [
                    au_track, au_fx, param_index, pt_time, norm, pt.get("shape", 0),
                ])


def main() -> int:
    global TEMPO
    section_idx = int(sys.argv[1])
    plan = json.loads(PLAN_PATH.read_text())
    TEMPO = plan.get("tempo_bpm", 120.0)
    root, leaves = leaves_for_section(plan, section_idx)
    # Must insert tracks in ascending track_index order -- leaves_for_section's
    # tree-traversal order does NOT match ascending track_index (a composite
    # child's nested leaves get numerically later indices than its top-level
    # siblings, since indices are pre-assigned per decompose level before any
    # recursion happens). InsertTrackAtIndex assumes the requested index is
    # reachable given tracks already created so far; calling it out of order
    # (e.g. index 3 before 0/1/2 exist) makes REAPER place the track at
    # whatever the next real slot is instead, silently desyncing every
    # subsequent track_index reference. Found live building "Tidal Lock"'s
    # section 0 (TrackFX_AddByName: "Track not found").
    leaves = sorted(leaves, key=lambda l: l["body"]["implementation"]["track_index"])
    start_s = root["timeline_start_s"] or 0.0
    end_s = start_s + root["duration_s"]

    print(f"=== executing section {section_idx}: {root['own_purpose'][:60]} "
          f"({len(leaves)} leaves, t={start_s:.0f}-{end_s:.0f}s) ===")

    resume_from = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    for i, leaf in enumerate(leaves):
        if i < resume_from:
            print(f"  leaf {i} ({leaf['node_id']}): skipped (already built)")
            continue
        t0 = time.monotonic()
        build_leaf(leaf, start_s, f"S{section_idx} leaf{i}")
        print(f"  leaf {i} ({leaf['node_id']}): built in {time.monotonic()-t0:.0f}s")

    call("Main_SaveProject", [0, False])

    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    combined_wav = BUILD_DIR / f"section_{section_idx}_combined.wav"
    call("RenderProject", [str(combined_wav), start_s, end_s, 2, True])

    sibling_states = {}
    for i, leaf in enumerate(leaves):
        track_index = leaf["body"]["implementation"]["track_index"]
        call("SetMediaTrackInfo_Value", [track_index, "I_SOLO", 1])
        solo_wav = BUILD_DIR / f"section_{section_idx}_leaf{i}_solo.wav"
        call("RenderProject", [str(solo_wav), start_s, end_s, 2, True])
        call("SetMediaTrackInfo_Value", [track_index, "I_SOLO", 0])
        m = analyze.measure(solo_wav)
        sibling_states[f"leaf{i}"] = {"measured": m}
        peak = m.get("sample_peak")
        flag = " <<< SILENT" if peak is None or peak < -60 else ""
        print(f"  leaf {i} measured: lufs={m.get('lufs')} peak={peak} "
              f"active_ratio={m.get('active_ratio')}{flag}")

    combined_state = {"measured": analyze.measure(combined_wav)}
    comp = review.review_composition(sibling_states, combined_state=combined_state)
    print(f"composition: {comp.status.value}")
    for reason in comp.reasons:
        print(f"  - {reason}")
    print(f"=== section {section_idx} done ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
