#!/usr/bin/env python3
"""Real gain-staging pass across the whole new song (2026-07-29), using
src/planner/gain_stage.py's prominence-aware correction -- built earlier
this session but not yet exercised on this song (every leaf's fader is
still at the flat 0dB default from build time).

Per section: one full-mix render over the section's time window, then one
solo render per leaf over the SAME window. RMS is computed directly from
the raw samples (not derived from measure()'s peak/crest_factor, which
can be None on near-silent/short stems) so every leaf gets a real number
regardless of how quiet it legitimately is. propose_gain_correction()
turns the (mix_rms_db - solo_rms_db) gap plus the leaf's own prominence
into a fader delta; corrections are applied live via set_track_volume.

Usage:
    set -a; source .env; set +a
    .venv/bin/python scripts/apply_gain_staging.py [section_idx]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from surge_bridge_client import call  # noqa: E402
from planner.gain_stage import propose_gain_correction  # noqa: E402

PLAN_PATH = ROOT / "state/song_plan/song_plan.json"
BUILD_DIR = ROOT / "state/song_build"
BUILD_DIR.mkdir(parents=True, exist_ok=True)


def rms_db(wav_path: Path) -> float:
    data, _sr = sf.read(str(wav_path), dtype="float64", always_2d=True)
    if data.size == 0:
        return -120.0
    rms = float(np.sqrt(np.mean(np.square(data))))
    return 20 * np.log10(rms) if rms > 0 else -120.0


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


def process_section(plan: dict, section_idx: int, report: list) -> None:
    root, leaves = leaves_for_section(plan, section_idx)
    start_s = root["timeline_start_s"] or 0.0
    end_s = start_s + root["duration_s"]

    print(f"=== section {section_idx}: {root['own_purpose'][:50]} "
          f"(t={start_s:.0f}-{end_s:.0f}s, {len(leaves)} leaves) ===")

    combined_wav = BUILD_DIR / f"gainstage_section_{section_idx}_combined.wav"
    r = call("RenderProject", [str(combined_wav), start_s, end_s, 2, True])
    if not r.get("ok"):
        raise RuntimeError(f"combined render failed for section {section_idx}: {r}")
    mix_db = rms_db(combined_wav)
    print(f"  mix RMS: {mix_db:.1f}dB")

    for leaf in leaves:
        track_index = leaf["body"]["implementation"]["track_index"]
        prominence = leaf.get("prominence", "midground")

        gv = call("GetMediaTrackInfo_Value", [track_index, "D_VOL"])
        current_fader_db = 0.0
        if gv.get("ok") and gv.get("ret") is not None and gv["ret"] > 0:
            current_fader_db = 20 * np.log10(gv["ret"])

        call("SetMediaTrackInfo_Value", [track_index, "I_SOLO", 1])
        solo_wav = BUILD_DIR / f"gainstage_s{section_idx}_t{track_index}_solo.wav"
        call("RenderProject", [str(solo_wav), start_s, end_s, 2, True])
        call("SetMediaTrackInfo_Value", [track_index, "I_SOLO", 0])
        solo_db = rms_db(solo_wav)

        correction = propose_gain_correction(prominence, solo_db, mix_db, current_fader_db)
        if correction is None:
            print(f"  track {track_index} ({prominence}): gap={mix_db - solo_db:.1f}dB "
                  f"-- within band, no change")
            report.append({"track": track_index, "prominence": prominence,
                            "gap_db": mix_db - solo_db, "applied": False})
            continue

        new_db = correction.new_fader_db
        new_linear = 10 ** (new_db / 20)
        sp = call("SetMediaTrackInfo_Value", [track_index, "D_VOL", new_linear])
        flag = ""
        if correction.hit_correction_cap:
            flag += " [capped]"
        if correction.hit_fader_limit:
            flag += " [fader limit]"
        print(f"  track {track_index} ({prominence}): gap={correction.measured_gap_db:.1f}dB "
              f"target={correction.target_band_db} -> delta={correction.delta_db:+.1f}dB "
              f"new_fader={new_db:+.1f}dB{flag} (set ok={sp.get('ok')})")
        report.append({"track": track_index, "prominence": prominence,
                        "gap_db": correction.measured_gap_db,
                        "delta_db": correction.delta_db, "new_fader_db": new_db,
                        "applied": True})

    print(f"=== section {section_idx} done ===\n")


def main() -> int:
    plan = json.loads(PLAN_PATH.read_text())
    n_sections = len(plan["section_root_ids"])
    report = []

    if len(sys.argv) > 1:
        sections = [int(sys.argv[1])]
    else:
        sections = list(range(n_sections))

    for idx in sections:
        process_section(plan, idx, report)

    call("Main_SaveProject", [0, False])

    report_path = ROOT / "state/scratch/gain_staging_report.json"
    report_path.write_text(json.dumps(report, indent=2))
    n_applied = sum(1 for r in report if r["applied"])
    print(f"=== gain staging done: {n_applied}/{len(report)} leaves corrected, "
          f"report at {report_path} ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
