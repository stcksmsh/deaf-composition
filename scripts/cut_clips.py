#!/usr/bin/env python3
"""Cut confirmed clips out of full tracks into the reference-library layout.

Takes a manifest of clips you've confirmed by ear (see suggest_boundaries.py
for a starting skeleton) and slices them into
    references/<section_type>/<name>.wav
which is exactly the layout reference_cli.py build expects.

MANIFEST FORMAT (JSON list)
    [
      {"source": "references/_raw/ikeda_datapath.wav",
       "start": 12.0, "end": 38.0,
       "section_type": "build", "name": "ikeda_datapath_build1"},
      ...
    ]

RUN
    python scripts/cut_clips.py manifest.json
    python scripts/cut_clips.py manifest.json --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from return_channel.reference import SECTION_TYPES, UNLABELED  # noqa: E402

KNOWN_TYPES = set(SECTION_TYPES) | {UNLABELED}
MIN_RECOMMENDED_S = 20.0  # below this, embed_windows() gives you 1 padded window, not several


def cut_one(entry: dict, references_root: Path, dry_run: bool) -> str:
    source = Path(entry["source"])
    start, end = float(entry["start"]), float(entry["end"])
    section_type, name = entry["section_type"], entry["name"]

    warnings = []
    if section_type not in KNOWN_TYPES:
        warnings.append(f"section_type {section_type!r} not in {sorted(KNOWN_TYPES)}")
    if end - start < MIN_RECOMMENDED_S:
        warnings.append(f"clip is {end - start:.1f}s, recommend >= {MIN_RECOMMENDED_S:.0f}s")
    if end <= start:
        raise ValueError(f"{name}: end ({end}) must be after start ({start})")

    out_path = references_root / section_type / f"{name}.wav"
    line = f"{source.name} [{start:.1f}s-{end:.1f}s] -> {out_path}"
    if warnings:
        line += "  [warn: " + "; ".join(warnings) + "]"

    if not dry_run:
        info = sf.info(str(source))
        sr = info.samplerate
        start_frame, stop_frame = int(round(start * sr)), int(round(end * sr))
        data, _ = sf.read(str(source), start=start_frame, stop=stop_frame, always_2d=True)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        sf.write(out_path, data, sr)
    return line


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--references-root", type=Path, default=Path("references"))
    parser.add_argument("--dry-run", action="store_true",
                        help="print what would be cut without writing files")
    args = parser.parse_args(argv)

    entries = json.loads(args.manifest.read_text(encoding="utf-8"))
    for entry in entries:
        print(cut_one(entry, args.references_root, args.dry_run))

    if not args.dry_run:
        by_type = {}
        for entry in entries:
            by_type[entry["section_type"]] = by_type.get(entry["section_type"], 0) + 1
        print("\nwrote:")
        for section_type, count in sorted(by_type.items()):
            print(f"  {section_type}: {count} clip(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
