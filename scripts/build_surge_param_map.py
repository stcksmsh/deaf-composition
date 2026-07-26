#!/usr/bin/env python3
"""
Build the REAPER param-index -> Surge ctrltype/range map for Surge XT.

Walks manifest.json's 778 Surge XT param names as a state machine, matching each
name's position against the fixed structural layout Surge itself uses (scene A/B,
each with 3 oscillators, 2 filters, 2 ADSRs, 12 LFOs, mixer routing, and the FX
send/global header), and assigns each param the ctrltype recorded in
surge_assign_calls.json for that structural role.

Two families of param are structurally *type-dependent* and cannot be resolved this
way: the 7 generic oscillator params per osc (Shape/Width1/Width2/SubMix/Sync/
UnisonDetune/UnisonVoices -- Surge's own p[i] slots, meaning changes with oscillator
type) and the 12 generic FX params per FX slot (meaning changes with the effect type
loaded into that slot). Those are emitted with ctrltype=None, resolved=False --
closing that gap requires a second pass over each oscillator/effect type's own
parameter definitions, not attempted here.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

RANGES = json.loads((ROOT / "scripts/surge_ctrltype_ranges.json").read_text())["ranges"]

# ctrltypes whose max is "some_enum_count() - 1" at runtime -- not a literal range.
VARIABLE_MAX = {
    "ct_lfotrigmode", "ct_osctype", "ct_fxtype", "ct_fxbypass", "ct_lfotype",
    "ct_fbconfig", "ct_fmconfig", "ct_filtertype", "ct_filtersubtype", "ct_wstype",
    "ct_scenemode", "ct_polymode", "ct_ensemble_stages", "ct_stringosc_excitation_model",
    "ct_alias_wave", "ct_distortion_waveshape", "ct_nimbusmode",
}

MIXER_SLOT = [
    ("Volume", "ct_amplitude"), ("Mute", "ct_bool_mute"),
    ("Solo", "ct_bool_solo"), ("Route", "ct_oscroute"),
]
RING_SLOT = [
    ("Volume", "ct_amplitude_ringmod"), ("Mute", "ct_bool_mute"),
    ("Solo", "ct_bool_solo"), ("Route", "ct_oscroute"),
]
OSC_FIXED = [
    ("Type", "ct_osctype"), ("Octave", "ct_pitch_octave"),
    ("Pitch", "ct_pitch_semi7bp_absolutable"),
]
OSC_DYNAMIC_TAILS = ["Shape", "Width 1", "Width 2", "Sub Mix", "Sync", "Unison Detune", "Unison Voices"]
OSC_TAIL_FIXED = [("Keytrack", "ct_bool_keytrack"), ("Retrigger", "ct_bool_retrigger")]

FILTER_FIELDS = [
    ("Type", "ct_filtertype"), ("Subtype", "ct_filtersubtype"),
    ("Cutoff", "ct_freq_audible_with_tunability"), ("Resonance", "ct_percent"),
    ("FEG Mod Amount", "ct_freq_mod"), ("Keytrack", "ct_percent_bipolar"),
]
EG_FIELDS = [
    ("Attack", "ct_envtime"), ("Attack Shape", "ct_envshape_attack"),
    ("Decay", "ct_envtime"), ("Decay Shape", "ct_envshape"),
    ("Sustain", "ct_percent"), ("Release", "ct_envtime"),
    ("Release Shape", "ct_envshape"), ("Envelope Mode", "ct_envmode"),
]
LFO_FIELDS = [
    ("Type", "ct_lfotype"), ("Rate", "ct_lforate_deactivatable"),
    ("Phase", "ct_lfophaseshuffle"), ("Amplitude", "ct_lfoamplitude"),
    ("Deform", "ct_lfodeform"), ("Trigger Mode", "ct_lfotrigmode"),
    ("Unipolar", "ct_bool_unipolar"), ("Delay", "ct_envtime_deactivatable"),
    ("Attack", "ct_envtime"), ("Hold", "ct_envtime"), ("Decay", "ct_envtime"),
    ("Sustain", "ct_percent"), ("Release", "ct_envtime_lfodecay"),
]
SCENE_HEADER = [
    ("Octave", "ct_pitch_octave"), ("Pitch", "ct_pitch_semi7bp"),
    ("Portamento", "ct_portatime"), ("Play Mode", "ct_polymode"),
    ("FM Routing", "ct_fmconfig"), ("FM Depth", "ct_decibel_fmdepth"),
    ("Osc Drift", "ct_percent_oscdrift"), ("Noise Color", "ct_noise_color"),
    ("Keytrack Root Key", "ct_midikey"), ("Volume", "ct_amplitude_clipper"),
    ("Pan", "ct_percent_bipolar_pan"), ("Width", "ct_percent_bipolar"),
    ("Send FX 1 Level", "ct_sendlevel"), ("Send FX 2 Level", "ct_sendlevel"),
    ("Send FX 3 Level", "ct_sendlevel"), ("Send FX 4 Level", "ct_sendlevel"),
    ("Pitch Bend Up Range", "ct_pbdepth"), ("Pitch Bend Down Range", "ct_pbdepth"),
    ("VCA Gain", "ct_decibel"), ("Velocity > VCA Gain", "ct_decibel_attenuation"),
    ("Feedback", "ct_filter_feedback"), ("Filter Configuration", "ct_fbconfig"),
    ("Filter Balance", "ct_percent_bipolar"), ("Highpass", "ct_freq_hpf"),
    ("Waveshaper Type", "ct_wstype"), ("Waveshaper Drive", "ct_decibel_narrow_short_extendable"),
    ("Filter 2 Offset Mode", "ct_bool_relative_switch"), ("Link Resonance", "ct_bool_link_switch"),
]
GLOBAL_HEADER = [
    ("Send FX 1 Return", "ct_amplitude"), ("Send FX 2 Return", "ct_amplitude"),
    ("Send FX 3 Return", "ct_amplitude"), ("Send FX 4 Return", "ct_amplitude"),
    ("Global Volume", "ct_decibel_attenuation_clipper"), ("Active Scene", "ct_scenesel"),
    ("Scene Mode", "ct_scenemode"), ("Split Point", "ct_midikey_or_channel"),
    ("FX Disable", None), ("Polyphony Limit", "ct_polylimit"),
    ("FX Chain Bypass", "ct_fxbypass"),
]
HOST_PARAMS = {"Bypass Surge XT": None, "Bypass": None, "Wet": None, "Delta": None}


def entry(index, name, ctrltype, resolved, note=""):
    d = {"index": index, "name": name, "ctrltype": ctrltype, "resolved": resolved}
    if ctrltype:
        if ctrltype in VARIABLE_MAX:
            d["min"] = 0
            d["max"] = None
            d["note"] = "enum, max = runtime enum size - 1 (query via TrackFX_GetParameterStepSizes)"
        elif ctrltype in RANGES:
            d["min"], d["max"] = RANGES[ctrltype]
        else:
            d["resolved"] = False
            note = note or f"ctrltype '{ctrltype}' not found in surge_ctrltype_ranges.json"
    if note:
        d["note"] = note
    return d


def consume(names, i, fields):
    """Match a fixed sequence of (tail, ctrltype) against names[i:], return next i and entries."""
    out = []
    for tail, ct in fields:
        assert names[i] == tail, f"expected '{tail}' at index {i}, got '{names[i]}'"
        out.append((i, names[i], ct))
        i += 1
    return i, out


def build():
    manifest = json.loads((ROOT / "manifest.json").read_text())
    surge = next(p for p in manifest["plugins"] if p["matched_name"] == "Surge XT")
    names = [p["name"] for p in surge["params"]]
    assert len(names) == 778

    out = [None] * len(names)
    i = 0

    # Macros M1-M8 -- not in surge_assign_calls.json (loop-assigned), assumed ct_percent
    # per Surge's default unipolar macro range. Flagged as an assumption, not verified.
    for k in range(8):
        assert names[i] == f"M{k+1}: -"
        out[i] = entry(i, names[i], "ct_percent", True,
                       note="assumed (macro ctrltype not in static assign table)")
        i += 1

    i, fields = consume(names, i, GLOBAL_HEADER)
    for idx, name, ct in fields:
        note = "" if ct is not None else "ct_none in Surge; not a real DSP-facing param"
        out[idx] = entry(idx, name, ct, ct is not None, note=note)

    # 16 FX slots, each: FX Type + 12 generic params.
    # Manifest order is (A1,A2,B1,B2,S1,S2,G1,G2,A3,A4,B3,B4,S3,S4,G3,G4), not grouped by letter.
    fx_slot_order = [
        ("A", 1), ("A", 2), ("B", 1), ("B", 2), ("S", 1), ("S", 2), ("G", 1), ("G", 2),
        ("A", 3), ("A", 4), ("B", 3), ("B", 4), ("S", 3), ("S", 4), ("G", 3), ("G", 4),
    ]
    for group, slot in fx_slot_order:
            tname = f"FX {group}{slot} FX Type"
            assert names[i] == tname, f"expected '{tname}' at {i}, got '{names[i]}'"
            out[i] = entry(i, names[i], "ct_fxtype", True)
            i += 1
            for p in range(1, 13):
                pname = f"FX {group}{slot} Param {p}"
                assert names[i] == pname, f"expected '{pname}' at {i}, got '{names[i]}'"
                out[i] = entry(i, names[i], None, False,
                               note="type-dependent: meaning set by the effect loaded in this slot")
                i += 1

    assert names[i] == "Character"
    out[i] = entry(i, names[i], "ct_character", True)
    i += 1

    for scene in ("A", "B"):
        # scene header (28 fields, each prefixed "<scene> ")
        for tail, ct in SCENE_HEADER:
            name = f"{scene} {tail}"
            assert names[i] == name, f"expected '{name}' at {i}, got '{names[i]}'"
            out[i] = entry(i, names[i], ct, True)
            i += 1

        # 3 oscillators, 12 fields each
        for osc in (1, 2, 3):
            for tail, ct in OSC_FIXED:
                name = f"{scene} Osc {osc} {tail}"
                assert names[i] == name, f"expected '{name}' at {i}, got '{names[i]}'"
                out[i] = entry(i, names[i], ct, True)
                i += 1
            for tail in OSC_DYNAMIC_TAILS:
                name = f"{scene} Osc {osc} {tail}"
                assert names[i] == name, f"expected '{name}' at {i}, got '{names[i]}'"
                out[i] = entry(i, names[i], None, False,
                               note="type-dependent: meaning set by this oscillator's type")
                i += 1
            for tail, ct in OSC_TAIL_FIXED:
                name = f"{scene} Osc {osc} {tail}"
                assert names[i] == name, f"expected '{name}' at {i}, got '{names[i]}'"
                out[i] = entry(i, names[i], ct, True)
                i += 1

        # mixer routing: Osc1-3, Ring 1x2, Ring 2x3, Noise
        for label, slot_fields in [
            ("Osc 1", MIXER_SLOT), ("Osc 2", MIXER_SLOT), ("Osc 3", MIXER_SLOT),
            ("Ring Modulation 1x2", RING_SLOT), ("Ring Modulation 2x3", RING_SLOT),
            ("Noise", MIXER_SLOT),
        ]:
            for tail, ct in slot_fields:
                name = f"{scene} {label} {tail}"
                assert names[i] == name, f"expected '{name}' at {i}, got '{names[i]}'"
                out[i] = entry(i, names[i], ct, True)
                i += 1

        assert names[i] == f"{scene} Pre-Filter Gain"
        out[i] = entry(i, names[i], "ct_decibel", True)
        i += 1

        for filt in (1, 2):
            for tail, ct in FILTER_FIELDS:
                name = f"{scene} Filter {filt} {tail}"
                assert names[i] == name, f"expected '{name}' at {i}, got '{names[i]}'"
                out[i] = entry(i, names[i], ct, True)
                i += 1

        for eg in ("Amp", "Filter"):
            for tail, ct in EG_FIELDS:
                name = f"{scene} {eg} EG {tail}"
                assert names[i] == name, f"expected '{name}' at {i}, got '{names[i]}'"
                out[i] = entry(i, names[i], ct, True)
                i += 1

        # 6 voice LFOs + 6 scene LFOs, 13 fields each
        for lfo in range(1, 7):
            for tail, ct in LFO_FIELDS:
                name = f"{scene} LFO {lfo} {tail}"
                assert names[i] == name, f"expected '{name}' at {i}, got '{names[i]}'"
                out[i] = entry(i, names[i], ct, True)
                i += 1
        for lfo in range(1, 7):
            for tail, ct in LFO_FIELDS:
                name = f"{scene} Scene LFO {lfo} {tail}"
                assert names[i] == name, f"expected '{name}' at {i}, got '{names[i]}'"
                out[i] = entry(i, names[i], ct, True)
                i += 1

    # trailing host-level params (not Surge's own ctrltype table)
    while i < len(names):
        assert names[i] in HOST_PARAMS, f"unexpected trailing param '{names[i]}' at {i}"
        out[i] = entry(i, names[i], None, False, note="host-level VST3 param, not a Surge parameter")
        i += 1

    assert all(o is not None for o in out), "did not cover every param index"
    return out


def main():
    out = build()
    resolved = sum(1 for o in out if o["resolved"])
    unresolved = [o for o in out if not o["resolved"]]
    dest = ROOT / "scripts/surge_param_map.json"
    dest.write_text(json.dumps(out, indent=2))
    print(f"{len(out)} params total, {resolved} resolved, {len(unresolved)} unresolved")
    by_note = {}
    for o in unresolved:
        by_note.setdefault(o.get("note", ""), 0)
        by_note[o.get("note", "")] += 1
    for note, count in sorted(by_note.items(), key=lambda x: -x[1]):
        print(f"  {count:4d}  {note}")
    print(f"wrote {dest}")


if __name__ == "__main__":
    main()
