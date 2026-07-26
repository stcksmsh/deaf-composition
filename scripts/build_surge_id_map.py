#!/usr/bin/env python3
"""
Build REAPER param-index -> Surge .fxp internal-id map for Surge XT.

Same traversal as build_surge_param_map.py (same manifest.json name assertions,
same order), but instead of emitting ctrltype/range per index, emits the internal
id string Surge's own patch (.fxp) XML uses for that param -- e.g. index 319
("A Filter 1 Cutoff") -> "a_filter1_cutoff". Confirmed against the real internal
ids visible in /usr/share/surge-xt/patches_factory/Basses/Bass 5.fxp (its
<parameters> tags), since Surge's XML field order is NOT the same order REAPER's
VST3 wrapper exposes params in (patch order groups octave/pitch/portamento before
the 3 oscillators; REAPER's order groups the whole scene header before them) --
id-based lookup, not positional, is required to join a patch's raw values to a
REAPER param index. Params outside Surge's own patch domain (the 8 macros, the
4 host-level VST3 meta params) get id=None -- nothing to look up, left at default.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

MIXER_SLOT_IDS = [("Volume", "level"), ("Mute", "mute"), ("Solo", "solo"), ("Route", "route")]

SCENE_HEADER_IDS = [
    ("Octave", "octave"), ("Pitch", "pitch"), ("Portamento", "portamento"),
    ("Play Mode", "polymode"), ("FM Routing", "fm_switch"), ("FM Depth", "fm_depth"),
    ("Osc Drift", "drift"), ("Noise Color", "noisecol"), ("Keytrack Root Key", "ktrkroot"),
    ("Volume", "volume"), ("Pan", "pan"), ("Width", "pan2"),
    ("Send FX 1 Level", "send_fx_1"), ("Send FX 2 Level", "send_fx_2"),
    ("Send FX 3 Level", "send_fx_3"), ("Send FX 4 Level", "send_fx_4"),
    ("Pitch Bend Up Range", "pbrange_up"), ("Pitch Bend Down Range", "pbrange_dn"),
    ("VCA Gain", "vca_level"), ("Velocity > VCA Gain", "vca_velsense"),
    ("Feedback", "feedback"), ("Filter Configuration", "fb_config"),
    ("Filter Balance", "f_balance"), ("Highpass", "lowcut"),
    ("Waveshaper Type", "ws_type"), ("Waveshaper Drive", "ws_drive"),
    ("Filter 2 Offset Mode", "f2_cf_is_offset"), ("Link Resonance", "f2_link_resonance"),
]
OSC_FIXED_IDS = [("Type", "type"), ("Octave", "octave"), ("Pitch", "pitch")]
OSC_DYNAMIC_TAILS = ["Shape", "Width 1", "Width 2", "Sub Mix", "Sync", "Unison Detune", "Unison Voices"]
OSC_TAIL_FIXED_IDS = [("Keytrack", "keytrack"), ("Retrigger", "retrigger")]
FILTER_FIELD_IDS = [
    ("Type", "type"), ("Subtype", "subtype"), ("Cutoff", "cutoff"),
    ("Resonance", "resonance"), ("FEG Mod Amount", "envmod"), ("Keytrack", "keytrack"),
]
EG_FIELD_IDS = [
    ("Attack", "attack"), ("Attack Shape", "attack_shape"), ("Decay", "decay"),
    ("Decay Shape", "decay_shape"), ("Sustain", "sustain"), ("Release", "release"),
    ("Release Shape", "release_shape"), ("Envelope Mode", "mode"),
]
LFO_FIELD_IDS = [
    ("Type", "shape"), ("Rate", "rate"), ("Phase", "phase"), ("Amplitude", "magnitude"),
    ("Deform", "deform"), ("Trigger Mode", "trigmode"), ("Unipolar", "unipolar"),
    ("Delay", "delay"), ("Attack", "attack"), ("Hold", "hold"), ("Decay", "decay"),
    ("Sustain", "sustain"), ("Release", "release"),
]
GLOBAL_HEADER_IDS = [
    ("Send FX 1 Return", "volume_FX1"), ("Send FX 2 Return", "volume_FX2"),
    ("Send FX 3 Return", "volume_FX3"), ("Send FX 4 Return", "volume_FX4"),
    ("Global Volume", "volume"), ("Active Scene", "scene_active"),
    ("Scene Mode", "scenemode"), ("Split Point", "splitkey"),
    ("FX Disable", "fx_disable"), ("Polyphony Limit", "polylimit"),
    ("FX Chain Bypass", "fx_bypass"),
]


def consume(names, i, fields, id_fmt):
    out = []
    for tail, key in fields:
        assert names[i] == tail, f"expected '{tail}' at index {i}, got '{names[i]}'"
        out.append((i, id_fmt(key)))
        i += 1
    return i, out


def build():
    manifest = json.loads((ROOT / "manifest.json").read_text())
    surge = next(p for p in manifest["plugins"] if p["matched_name"] == "Surge XT")
    names = [p["name"] for p in surge["params"]]
    assert len(names) == 778

    out = [None] * len(names)
    i = 0

    for k in range(8):
        assert names[i] == f"M{k+1}: -"
        out[i] = None  # macros aren't part of Surge's own patch serialization
        i += 1

    i, fields = consume(names, i, GLOBAL_HEADER_IDS, lambda key: key)
    for idx, pid in fields:
        out[idx] = pid

    fx_slot_order = [
        ("A", 1), ("A", 2), ("B", 1), ("B", 2), ("S", 1), ("S", 2), ("G", 1), ("G", 2),
        ("A", 3), ("A", 4), ("B", 3), ("B", 4), ("S", 3), ("S", 4), ("G", 3), ("G", 4),
    ]
    for slot_num, (group, slot) in enumerate(fx_slot_order, start=1):
        tname = f"FX {group}{slot} FX Type"
        assert names[i] == tname, f"expected '{tname}' at {i}, got '{names[i]}'"
        out[i] = f"fx{slot_num}_type"
        i += 1
        for p in range(1, 13):
            pname = f"FX {group}{slot} Param {p}"
            assert names[i] == pname, f"expected '{pname}' at {i}, got '{names[i]}'"
            out[i] = f"fx{slot_num}_p{p - 1}"
            i += 1

    assert names[i] == "Character"
    out[i] = "character"
    i += 1

    for scene in ("A", "B"):
        prefix = "a_" if scene == "A" else "b_"

        for tail, key in SCENE_HEADER_IDS:
            name = f"{scene} {tail}"
            assert names[i] == name, f"expected '{name}' at {i}, got '{names[i]}'"
            out[i] = prefix + key
            i += 1

        for osc in (1, 2, 3):
            for tail, key in OSC_FIXED_IDS:
                name = f"{scene} Osc {osc} {tail}"
                assert names[i] == name, f"expected '{name}' at {i}, got '{names[i]}'"
                out[i] = f"{prefix}osc{osc}_{key}"
                i += 1
            for p, tail in enumerate(OSC_DYNAMIC_TAILS):
                name = f"{scene} Osc {osc} {tail}"
                assert names[i] == name, f"expected '{name}' at {i}, got '{names[i]}'"
                out[i] = f"{prefix}osc{osc}_param{p}"
                i += 1
            for tail, key in OSC_TAIL_FIXED_IDS:
                name = f"{scene} Osc {osc} {tail}"
                assert names[i] == name, f"expected '{name}' at {i}, got '{names[i]}'"
                out[i] = f"{prefix}osc{osc}_{key}"
                i += 1

        for label, suffix in [
            ("Osc 1", "o1"), ("Osc 2", "o2"), ("Osc 3", "o3"),
            ("Ring Modulation 1x2", "ring12"), ("Ring Modulation 2x3", "ring23"),
            ("Noise", "noise"),
        ]:
            for tail, key in MIXER_SLOT_IDS:
                name = f"{scene} {label} {tail}"
                assert names[i] == name, f"expected '{name}' at {i}, got '{names[i]}'"
                out[i] = f"{prefix}{key}_{suffix}"
                i += 1

        assert names[i] == f"{scene} Pre-Filter Gain"
        out[i] = prefix + "level_pfg"
        i += 1

        for filt in (1, 2):
            for tail, key in FILTER_FIELD_IDS:
                name = f"{scene} Filter {filt} {tail}"
                assert names[i] == name, f"expected '{name}' at {i}, got '{names[i]}'"
                out[i] = f"{prefix}filter{filt}_{key}"
                i += 1

        for eg_num, eg in enumerate(("Amp", "Filter"), start=1):
            for tail, key in EG_FIELD_IDS:
                name = f"{scene} {eg} EG {tail}"
                assert names[i] == name, f"expected '{name}' at {i}, got '{names[i]}'"
                out[i] = f"{prefix}env{eg_num}_{key}"
                i += 1

        for lfo in range(1, 7):
            for tail, key in LFO_FIELD_IDS:
                name = f"{scene} LFO {lfo} {tail}"
                assert names[i] == name, f"expected '{name}' at {i}, got '{names[i]}'"
                out[i] = f"{prefix}lfo{lfo - 1}_{key}"
                i += 1
        for lfo in range(1, 7):
            for tail, key in LFO_FIELD_IDS:
                name = f"{scene} Scene LFO {lfo} {tail}"
                assert names[i] == name, f"expected '{name}' at {i}, got '{names[i]}'"
                out[i] = f"{prefix}lfo{lfo + 5}_{key}"
                i += 1

    host_params = {"Bypass Surge XT", "Bypass", "Wet", "Delta"}
    while i < len(names):
        assert names[i] in host_params, f"unexpected trailing param '{names[i]}' at {i}"
        out[i] = None
        i += 1

    return names, out


def main():
    names, ids = build()
    dest = ROOT / "scripts/surge_id_map.json"
    dest.write_text(json.dumps(
        [{"index": i, "name": n, "id": pid} for i, (n, pid) in enumerate(zip(names, ids))],
        indent=2,
    ))
    have_id = sum(1 for x in ids if x is not None)
    print(f"{len(ids)} params, {have_id} with a patch-XML id, {len(ids) - have_id} without (macros/host params)")
    print(f"wrote {dest}")


if __name__ == "__main__":
    main()
