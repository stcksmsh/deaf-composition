#!/usr/bin/env python3
"""Run exp1_separability.py under both CLAP checkpoints and compare the verdict metrics.

WHY THIS EXISTS
    exp1_separability.py calls bare load_ckpt(), which fetches the stock
    HTSAT-tiny checkpoint, while its own docstring recommends the music-trained
    checkpoint for this use case. Whichever one is chosen becomes canonical: every
    stored embedding and every reference envelope is invalidated the moment it
    changes. So pick it from data, once, before the reference library is built.

    This does not modify exp1_separability.py -- it already accepts --ckpt and
    --amodel. It runs it twice and tabulates the three numbers the verdict uses.

THE MUSIC CHECKPOINT IS NOT BUNDLED (~2GB). Fetch it first:
    curl -L -o music_audioset_epoch_15_esc_90.14.pt \\
      https://huggingface.co/lukewys/laion_clap/resolve/main/music_audioset_epoch_15_esc_90.14.pt

RUN
    python compare_checkpoints.py --root ./references
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP1 = HERE / "exp1_separability.py"
MUSIC_CKPT = "music_audioset_epoch_15_esc_90.14.pt"
MUSIC_URL = ("https://huggingface.co/lukewys/laion_clap/resolve/main/"
             "music_audioset_epoch_15_esc_90.14.pt")

# Pulled from exp1's own report, so the comparison uses its numbers verbatim.
METRICS = {
    "cohesion_gap": r"cohesion gap\s*:\s*([+-]?[\d.]+)",
    "silhouette": r"silhouette \(2-cluster\)\s*:\s*([+-]?[\d.]+)",
    "nn_purity_target": r"NN purity \(target\)\s*:\s*([\d.]+)",
}


def run(root: Path, out: Path, ckpt: Path | None, amodel: str) -> dict:
    argv = [sys.executable, str(EXP1), "--root", str(root), "--out", str(out),
            "--amodel", amodel]
    if ckpt:
        argv += ["--ckpt", str(ckpt)]

    print(f"\n=== {amodel} / {ckpt.name if ckpt else 'stock checkpoint'} ===")
    print(f"  {' '.join(argv)}")
    result = subprocess.run(argv, capture_output=True, text=True)
    sys.stdout.write(result.stdout)
    if result.returncode != 0:
        sys.stderr.write(result.stderr)
        raise SystemExit(f"exp1 failed under {amodel} (exit {result.returncode})")

    values = {}
    for name, pattern in METRICS.items():
        match = re.search(pattern, result.stdout)
        values[name] = float(match.group(1)) if match else None
        if match is None:
            print(f"  [warn] could not parse {name} from exp1 output")
    values["verdict"] = "SIGNAL PRESENT" if "VERDICT: SIGNAL PRESENT" in result.stdout \
        else "WEAK / NO SEPARATION"
    return values


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="./references")
    ap.add_argument("--music-ckpt", default=None,
                    help=f"path to {MUSIC_CKPT} (default: alongside this script)")
    ap.add_argument("--out", default="exp1_checkpoint_comparison.md")
    args = ap.parse_args()

    root = Path(args.root)
    if not (root / "target").is_dir() or not (root / "offtarget").is_dir():
        raise SystemExit(f"expected {root}/target and {root}/offtarget to exist")

    music = Path(args.music_ckpt) if args.music_ckpt else HERE / MUSIC_CKPT
    if not music.is_file():
        raise SystemExit(
            f"music checkpoint not found at {music}\n\n"
            f"It is a ~2GB download and is deliberately not fetched automatically:\n"
            f"  curl -L -o {music} \\\n    {MUSIC_URL}\n"
        )

    results = {
        "stock (HTSAT-tiny)": run(root, HERE / "exp1_out_tiny", None, "HTSAT-tiny"),
        "music (HTSAT-base)": run(root, HERE / "exp1_out_music", music, "HTSAT-base"),
    }

    lines = [
        "# CLAP checkpoint comparison (exp1 separability)",
        "",
        "Higher is better for all three. The winner becomes canonical: it must then",
        "be used for every leaf embedding *and* every reference envelope, since",
        "vectors from different checkpoints are not comparable.",
        "",
        "| Checkpoint | Cohesion gap | Silhouette | NN purity (target) | Verdict |",
        "|---|---|---|---|---|",
    ]
    for label, v in results.items():
        cells = [f"{v[k]:+.3f}" if v[k] is not None else "?"
                 for k in ("cohesion_gap", "silhouette", "nn_purity_target")]
        lines.append(f"| {label} | {cells[0]} | {cells[1]} | {cells[2]} | {v['verdict']} |")

    report = "\n".join(lines) + "\n"
    Path(args.out).write_text(report)
    print("\n" + report)
    print(f"[*] wrote {args.out}")


if __name__ == "__main__":
    main()
