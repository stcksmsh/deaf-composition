#!/usr/bin/env python3
"""Applies the freshly re-emitted implementations (state/scratch/
reemitted_drum_leaves.json) to their EXISTING live tracks -- unlike
execute_section_direct.py's build_leaf(), this does NOT InsertTrackAtIndex
or TrackFX_AddByName since the track and Surge XT instance already exist
from the original (broken, Drum One.fxp) build. Deletes the old MIDI item
first, re-applies the preset (overwriting all params), rebuilds notes and
any automation.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from apply_surge_preset import STATE_DEPENDENT_ENUM_CTRLTYPES  # noqa: E402
from apply_surge_preset_live import apply_preset, apply_overrides, probe_enum_size  # noqa: E402
from surge_bridge_client import call  # noqa: E402
from surge_normalize import load_map, normalize  # noqa: E402

PLAN_PATH = ROOT / "state/song_plan/song_plan.json"
REEMIT_PATH = ROOT / "state/scratch/reemitted_drum_leaves.json"

_PARAM_MAP_BY_NAME = None
_ENUM_SIZES = json.loads((ROOT / "scripts/surge_enum_sizes.json").read_text())


def param_map_by_name():
    global _PARAM_MAP_BY_NAME
    if _PARAM_MAP_BY_NAME is None:
        _PARAM_MAP_BY_NAME = {e["name"]: e for e in load_map()}
    return _PARAM_MAP_BY_NAME


def surge_param_normalized(track_index, fx_index, param_name, raw_value):
    entry = param_map_by_name()[param_name]
    if entry.get("max") is None:
        ctrltype = entry["ctrltype"]
        n = probe_enum_size(track_index, fx_index, entry["index"]) if ctrltype in STATE_DEPENDENT_ENUM_CTRLTYPES else _ENUM_SIZES[ctrltype]["n"]
        return entry["index"], normalize(entry, raw_value, enum_max=n - 1)
    return entry["index"], normalize(entry, raw_value)


def reapply(node_id: str, impl: dict, timeline_start_s: float, tempo_bpm: float) -> None:
    track_index = impl["track_index"]
    preset_op = next(op for op in impl["ops"] if op["tool"] == "apply_surge_preset")
    item_op = next(op for op in impl["ops"] if op["tool"] == "create_midi_item")
    notes_op = next(op for op in impl["ops"] if op["tool"] == "add_midi_notes_batch")
    fx_index = preset_op["args"].get("fx_index", 0)

    preset_path = preset_op["args"]["preset_path"]
    full_fxp = f"/usr/share/surge-xt/patches_factory/{preset_path}"
    apply_preset(full_fxp, track_index, fx_index)
    overrides = preset_op["args"].get("overrides") or {}
    if overrides:
        apply_overrides(track_index, fx_index, overrides)

    # Delete old item(s) on this track (there should be exactly 1).
    while True:
        r = call("GetTrackMediaItem", [track_index, 0])
        if not r.get("ok") or not r.get("ret"):
            break
        d = call("DeleteTrackMediaItem", [track_index, 0])
        if not d.get("ok"):
            raise RuntimeError(f"DeleteTrackMediaItem failed for {node_id}: {d}")

    position = timeline_start_s + item_op["args"]["position"]
    length = item_op["args"]["length"]
    r = call("CreateMIDIItem", [track_index, position, position + length])
    if not r.get("ok"):
        raise RuntimeError(f"CreateMIDIItem failed for {node_id}: {r}")
    item_index = 0

    def beats_to_seconds(b):
        return b / tempo_bpm * 60.0

    for note in notes_op["args"]["notes"]:
        start_s = beats_to_seconds(note.get("start_beat", 0))
        length_s = beats_to_seconds(note.get("length_beats", 1.0))
        call("InsertMIDINote", [track_index, item_index, note.get("pitch", 60),
                                 start_s, start_s + length_s, note.get("velocity", 100),
                                 note.get("channel", 0)])

    for op in impl["ops"][3:]:
        if op["tool"] == "automate_track_envelope":
            args = op["args"]
            env_track, env_name = args["track_index"], args["envelope_name"]
            r = call("GetTrackEnvelopeByName", [env_track, env_name])
            if not r.get("ok") or not r.get("ret"):
                show_action = {"Volume": 40406, "Pan": 40407}.get(env_name)
                if show_action is None:
                    print(f"  !! skipping {env_name} automation for {node_id} -- no known show action", file=sys.stderr)
                    continue
                call("SetTrackSelected", [env_track, True])
                call("Main_OnCommand", [show_action, 0])
                r = call("GetTrackEnvelopeByName", [env_track, env_name])
                if not r.get("ok") or not r.get("ret"):
                    print(f"  !! still failed to show {env_name} for {node_id}, skipping automation", file=sys.stderr)
                    continue
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
                                        param_map_by_name()[args["param_name"]]["index"]])
            if not r.get("ok"):
                raise RuntimeError(f"GetFXEnvelope failed for {node_id}: {r}")
            for pt in args["points"]:
                pt_time = timeline_start_s + pt["time"]
                param_index, norm = surge_param_normalized(
                    au_track, au_fx, args["param_name"], pt["value"]
                )
                call("AddFXEnvelopePoint", [
                    au_track, au_fx, param_index, pt_time, norm, pt.get("shape", 0),
                ])


def main() -> None:
    plan = json.loads(PLAN_PATH.read_text())
    reemitted = json.loads(REEMIT_PATH.read_text())
    tempo_bpm = plan.get("tempo_bpm", 120.0)
    nodes = {n["node_id"]: n for n in plan["nodes"]}

    for node_id, impl in reemitted.items():
        node = nodes[node_id]
        old_track_index = node["body"]["implementation"]["track_index"]
        impl["track_index"] = old_track_index
        for op in impl["ops"]:
            op["args"]["track_index"] = old_track_index

        # Each node carries its own timeline_start_s directly (confirmed:
        # song_plan.json's item_op position is section-relative, NOT
        # absolute -- e.g. section_1/child_1/child_1 has position=5 while
        # its own timeline_start_s=40, so build_leaf() adds them together).
        timeline_start_s = node["timeline_start_s"]

        print(f"=== reapplying {node_id} (track {old_track_index}) ===", file=sys.stderr)
        reapply(node_id, impl, timeline_start_s, tempo_bpm)

        node["body"]["implementation"] = impl

    PLAN_PATH.write_text(json.dumps(plan, indent=2))
    print("song_plan.json updated", file=sys.stderr)


if __name__ == "__main__":
    main()
