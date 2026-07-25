#!/usr/bin/env python3
"""Suggest candidate section-boundary timestamps in a full track.

Nothing here can tell you "this is the drop" -- picking section types is a
judgment call the plan reserves for the human ear (deaf-composition-plan.md
§7.1). This just flags *where something changes* (loudness jumps, brightness
shifts) so you scan-and-confirm by ear at those timestamps instead of
scrubbing the whole track blind.

Prints a coarse level/brightness table plus detected change points, then a
ready-to-edit JSON skeleton for cut_clips.py's manifest format.

RUN
    python scripts/suggest_boundaries.py references/_raw/ikeda_datapath.wav
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import librosa
import numpy as np

BUCKET_S = 2.0        # coarse table resolution
FRAME_S = 0.5         # analysis frame for the novelty detector
KERNEL_S = 16.0        # checkerboard-kernel half-width -- the structural timescale
                       # this looks for; bigger = coarser (fewer, bigger sections)
NOVELTY_STD = 1.0     # peak must clear mean + this*std of the track's own novelty curve
CHANGE_MIN_GAP_S = 10.0       # don't flag two candidates closer than this
MAX_CANDIDATES = 14           # hard cap -- a glitchy track can still produce a noisy
                              # curve; past this many the list stops being useful anyway
TRAILING_SILENCE_FLOOR_DB = -50.0    # ignore a fade-to-silence tail as a "boundary"
MIN_SEGMENT_S = 8.0           # merge a segment shorter than this into its neighbor
N_MFCC = 14


def _load_frames(path: Path, sr: int = 22050):
    audio, _ = librosa.load(str(path), sr=sr, mono=True)
    frame_len = int(FRAME_S * sr)
    hop = frame_len
    rms = librosa.feature.rms(y=audio, frame_length=frame_len, hop_length=hop)[0]
    centroid = librosa.feature.spectral_centroid(y=audio, sr=sr, n_fft=frame_len,
                                                 hop_length=hop)[0]
    mfcc = librosa.feature.mfcc(y=audio, sr=sr, n_mfcc=N_MFCC, n_fft=frame_len,
                               hop_length=hop)
    with np.errstate(divide="ignore"):
        level_db = 20 * np.log10(np.maximum(rms, 1e-9))
    times = np.arange(len(level_db)) * FRAME_S
    return times, level_db, centroid, mfcc


def _envelopes(path: Path, sr: int = 22050):
    times, level_db, centroid, _ = _load_frames(path, sr)
    return times, level_db, centroid


def _trim_trailing_silence(level_db: np.ndarray) -> int:
    """Index past the last frame above the silence floor.

    A fade-to-silence tail reads as a huge level drop -- real, but not a
    section boundary you'd ever want to cut a clip at. Detection runs only
    up to this point; it also can't corrupt the similarity matrix for the
    rest of the track (a -180dB digital-silence run reads as maximally
    "similar to itself" and would otherwise swamp the novelty curve).
    """
    above = np.where(level_db > TRAILING_SILENCE_FLOOR_DB)[0]
    return int(above[-1]) + 1 if len(above) else len(level_db)


def _checkerboard_kernel(half: int) -> np.ndarray:
    """Foote's kernel: self-similar quadrants positive, cross quadrants negative,
    Gaussian-tapered so points near the checkerboard's own edges count less."""
    size = 2 * half
    kernel = np.ones((size, size))
    kernel[:half, half:] = -1
    kernel[half:, :half] = -1
    axis = np.arange(size) - (size - 1) / 2
    taper = np.exp(-0.5 * (axis / (half / 2)) ** 2)
    return kernel * np.outer(taper, taper)


def _novelty_curve(level_db: np.ndarray, mfcc: np.ndarray, keep: int) -> np.ndarray:
    """Self-similarity-matrix novelty (Foote 2000): the standard MIR technique for
    finding structural boundaries, used here instead of a hand-picked scalar
    feature (loudness, brightness) because it works off the full spectral-envelope
    shape (MFCCs) plus level, so it catches timbral/filter-driven transitions that
    have no loudness signature at all -- exactly what a scalar heuristic misses on
    texture-driven tracks."""
    feat = np.vstack([mfcc[1:, :keep], level_db[:keep][None, :]]).T  # (keep, N_MFCC)
    std = feat.std(axis=0)
    feat = (feat - feat.mean(axis=0)) / np.where(std > 1e-9, std, 1e-9)
    norm = np.linalg.norm(feat, axis=1, keepdims=True) + 1e-9
    unit = feat / norm
    similarity = unit @ unit.T  # cosine similarity, (keep, keep)

    half = max(4, int(KERNEL_S / FRAME_S))
    kernel = _checkerboard_kernel(half)
    novelty = np.zeros(keep)
    for i in range(half, keep - half):
        novelty[i] = float(np.sum(similarity[i - half:i + half, i - half:i + half] * kernel))
    return novelty


def _find_change_points(level_db: np.ndarray, mfcc: np.ndarray,
                        times: np.ndarray) -> list[float]:
    keep = _trim_trailing_silence(level_db)
    if keep < 2 * max(4, int(KERNEL_S / FRAME_S)) + 1:
        return []  # track too short for even one kernel window

    novelty = _novelty_curve(level_db, mfcc, keep)
    scored = novelty[novelty != 0]
    if scored.size == 0:
        return []
    threshold = scored.mean() + NOVELTY_STD * scored.std()

    candidates = []
    for i in np.argsort(-novelty):
        if novelty[i] < threshold or len(candidates) >= MAX_CANDIDATES:
            break
        t = times[i]
        if any(abs(t - c) < CHANGE_MIN_GAP_S for c in candidates):
            continue
        candidates.append(t)
    return sorted(candidates)


def _merge_short_segments(bounds: list[float]) -> list[float]:
    """Drop boundaries that would produce a segment shorter than MIN_SEGMENT_S."""
    merged = [bounds[0]]
    for b in bounds[1:-1]:
        if b - merged[-1] >= MIN_SEGMENT_S:
            merged.append(b)
    merged.append(bounds[-1])
    return merged


DROP_MARGIN_FRACTION = 0.75    # x this track's own body-level std -> counts as "drop"
DROP_MARGIN_FLOOR_DB = 0.5     # ... but never less than this (near-zero-variance tracks)
BUILD_SLOPE_DB_S = 0.15         # rising loudness trend within a segment -> "build"
BREAKDOWN_DROP_DB = 3.0        # sharp drop from the previous segment -> "breakdown"


def _classify_segments(bounds: list[float], times: np.ndarray,
                       level_db: np.ndarray) -> list[str]:
    """Rule-of-thumb section-type guess from each segment's own loudness stats.

    This is a starting guess to edit, not a verdict -- picking section types is
    reserved for the human ear (deaf-composition-plan.md §7.1). It only uses
    signal already computed for boundary detection: mean level (is this the
    loudest part of the track -> drop), within-segment loudness trend (rising
    -> build), and the jump from the previous segment (sharp drop -> breakdown).
    First/last segments default to intro/outro unless they're themselves the
    loudest part of the track.
    """
    stats = []
    for start, end in zip(bounds[:-1], bounds[1:]):
        i0, i1 = int(start / FRAME_S), max(int(start / FRAME_S) + 1, int(end / FRAME_S))
        i1 = min(i1, len(level_db))
        seg_level, seg_times = level_db[i0:i1], times[i0:i1]
        slope = float(np.polyfit(seg_times - seg_times[0], seg_level, 1)[0]) \
            if len(seg_level) > 1 else 0.0
        stats.append({"mean_level": float(np.mean(seg_level)), "slope": slope})

    n = len(stats)
    # Margin scales to the track's OWN dynamic range, not a fixed dB value: a
    # loop-driven track that's uniformly loud throughout (e.g. murk/quiet-machine
    # material, often <2dB of spread end to end) would otherwise have every
    # segment read as "the drop" under a fixed threshold. Computed from the
    # interior ("body") segments so a quiet intro/outro can't inflate the scale.
    body = [s["mean_level"] for s in stats[1:-1]] if n > 2 else [s["mean_level"] for s in stats]
    body_std = float(np.std(body)) if len(body) > 1 else 0.0
    margin = max(DROP_MARGIN_FLOOR_DB, DROP_MARGIN_FRACTION * body_std)
    loudest = max(body) if body else max(s["mean_level"] for s in stats)

    types: list[str | None] = [
        "drop" if loudest - s["mean_level"] <= margin else None for s in stats
    ]
    if types[0] is None:
        types[0] = "intro"
    if n > 1 and types[-1] is None:
        types[-1] = "outro"

    for i in range(n):
        if types[i] is not None:
            continue
        if stats[i]["slope"] > BUILD_SLOPE_DB_S:
            types[i] = "build"
        elif stats[i - 1]["mean_level"] - stats[i]["mean_level"] > BREAKDOWN_DROP_DB:
            types[i] = "breakdown"
        else:
            types[i] = "build"
    return types  # type: ignore[return-value]


def _bucketed_table(times: np.ndarray, level_db: np.ndarray, centroid: np.ndarray) -> list[str]:
    lines = []
    bucket_frames = max(1, int(BUCKET_S / FRAME_S))
    for start in range(0, len(times), bucket_frames):
        chunk_t = times[start:start + bucket_frames]
        chunk_db = level_db[start:start + bucket_frames]
        chunk_c = centroid[start:start + bucket_frames]
        if len(chunk_t) == 0:
            continue
        lines.append(f"  {chunk_t[0]:6.1f}s  level={np.median(chunk_db):6.1f}dB  "
                     f"centroid={np.median(chunk_c):6.0f}Hz")
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("track", type=Path)
    parser.add_argument("--section-type", default=None,
                        help="force every segment to this section_type instead of "
                             "guessing per-segment from loudness (see _classify_segments)")
    parser.add_argument("--manifest-out", type=Path, default=None,
                        help="write the JSON skeleton here instead of only printing it")
    args = parser.parse_args(argv)

    times, level_db, centroid, mfcc = _load_frames(args.track)
    duration = float(times[-1] + FRAME_S)
    changes = _find_change_points(level_db, mfcc, times)

    print(f"{args.track}  ({duration:.1f}s)\n")
    print("level/brightness over time:")
    for line in _bucketed_table(times, level_db, centroid):
        print(line)

    print(f"\ncandidate change points (self-similarity novelty, "
          f"{KERNEL_S:.0f}s structural scale, silence tail excluded):")
    bounds = _merge_short_segments([0.0] + changes + [duration])
    changes = bounds[1:-1]
    for t in changes:
        print(f"  {t:6.1f}s")
    if not changes:
        print("  none found -- track may be too uniform for this heuristic; "
              "you'll need to place boundaries by ear")

    guessed_types = [args.section_type] * (len(bounds) - 1) if args.section_type \
        else _classify_segments(bounds, times, level_db)
    print("\nguessed section types (loudness-rule heuristic -- verify by ear, "
          "this is a starting point, not a verdict):")
    for (start, end), guess in zip(zip(bounds[:-1], bounds[1:]), guessed_types):
        print(f"  {start:6.1f}s - {end:6.1f}s  {guess}")

    print("\nmanifest skeleton (edit start/end/section_type/name, then feed to "
          "cut_clips.py):")
    skeleton = []
    for (start, end), guess in zip(zip(bounds[:-1], bounds[1:]), guessed_types):
        skeleton.append({
            "source": str(args.track),
            "start": round(start, 1),
            "end": round(end, 1),
            "section_type": guess,
            "name": f"{args.track.stem}_{round(start)}s",
        })
    print(json.dumps(skeleton, indent=2))
    if args.manifest_out:
        args.manifest_out.parent.mkdir(parents=True, exist_ok=True)
        args.manifest_out.write_text(json.dumps(skeleton, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
