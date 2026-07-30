#!/usr/bin/env python3
"""Solo-render + measure each of the 5 tracks fixed by
reapply_reemitted_leaves.py, reusing execute_section_direct.py's exact
solo/render/measure pattern. Prints peak/LUFS per track; flags anything
still silent."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from surge_bridge_client import call  # noqa: E402
from return_channel import analyze  # noqa: E402

BUILD_DIR = ROOT / "state/song_build"
BUILD_DIR.mkdir(parents=True, exist_ok=True)

# node_id -> (track_index, absolute start_s, absolute end_s), read live from
# song_plan.json's timeline_start_s + item position/length per leaf.
TARGETS = {
    "song/section_1/child_1/child_1": (6, 40.0, 80.0),
    "song/section_2/child_2/child_1": (17, 80.0, 120.0),
    "song/section_2/child_2/child_2": (18, 80.0, 120.0),
    "song/section_4/child_3/child_1": (26, 200.0, 280.0),
    "song/section_4/child_3/child_2": (27, 200.0, 203.5),
}


def main() -> None:
    for node_id, (track_index, start_s, end_s) in TARGETS.items():
        call("SetMediaTrackInfo_Value", [track_index, "I_SOLO", 1])
        wav = BUILD_DIR / f"verify_track{track_index}.wav"
        call("RenderProject", [str(wav), start_s, end_s, 2, True])
        call("SetMediaTrackInfo_Value", [track_index, "I_SOLO", 0])
        m = analyze.measure(wav)
        peak = m.get("sample_peak")
        flag = " <<< STILL SILENT" if peak is None or peak < -60 else " OK"
        print(f"{node_id} (track {track_index}): lufs={m.get('lufs')} peak={peak} "
              f"active_ratio={m.get('active_ratio')}{flag}")


if __name__ == "__main__":
    main()
