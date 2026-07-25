"""Fingerprint reference library: per-section-type target distributions.

Plan §4.1: a node's acceptance criterion is "distance into the reference envelope,"
never an absolute magic value. This module builds that envelope from a curated
fingerprint library (plan §4.2/§4.3 — machine-native only, kept separate from the
structure library) and scores a leaf's state.json against it.

Expected layout, one folder per section type:
    <root>/intro/*.wav
    <root>/build/*.wav
    <root>/drop/*.wav
    <root>/breakdown/*.wav
    <root>/outro/*.wav
A flat <root>/*.wav with no subfolders is accepted as a single `unlabeled` type.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from . import analyze

SECTION_TYPES = ("intro", "build", "drop", "breakdown", "outro")
UNLABELED = "unlabeled"
AUDIO_EXTENSIONS = {".wav", ".flac", ".mp3", ".ogg", ".m4a"}

# Scalar-per-track metrics carried straight through from analyze.measure().
MEASURED_SCALARS = ("lufs", "true_peak", "sample_peak", "crest_factor", "active_ratio")
# Nested {mean,median,std} metrics — the median is what represents the track.
MEASURED_SPECTRAL = ("spectral_centroid", "spectral_rolloff", "spectral_flatness")


def iter_reference_files(root: str | Path,
                         section_types: tuple[str, ...] = SECTION_TYPES) -> dict[str, list[Path]]:
    """Discover reference audio, by section-type subfolder or as one flat set."""
    root = Path(root)
    found = {}
    for section_type in section_types:
        directory = root / section_type
        if directory.is_dir():
            files = sorted(p for p in directory.iterdir()
                           if p.suffix.lower() in AUDIO_EXTENSIONS)
            if files:
                found[section_type] = files
    if found:
        return found

    flat = sorted(p for p in root.iterdir()
                  if p.is_file() and p.suffix.lower() in AUDIO_EXTENSIONS) if root.is_dir() else []
    if flat:
        return {UNLABELED: flat}

    raise FileNotFoundError(
        f"no reference audio under {root}. Expected {root}/<section_type>/*.wav "
        f"for section_type in {section_types}, or audio files directly under {root}."
    )


def _flatten_measured(measured: dict) -> dict[str, float]:
    """One scalar per metric, matching the same mean/median convention measure() uses."""
    flat = {}
    for key in MEASURED_SCALARS:
        value = measured.get(key)
        if value is not None:
            flat[key] = value
    for key in MEASURED_SPECTRAL:
        value = measured.get(key)
        if value is not None:
            flat[key] = value["median"]
    return flat


def analyze_reference_track(path: str | Path, embedding: bool = True,
                            checkpoint: str | None = None,
                            amodel: str = analyze.CLAP_AMODEL) -> dict:
    """Measure + (optionally) embed one reference track. Failures are recorded,
    not raised — a library build should not die because one file is unreadable
    by soundfile (e.g. a lone mp3 that only librosa's backend can decode)."""
    path = Path(path)
    record = {"path": str(path), "measured": None, "embedding_windows": None,
             "warnings": []}
    try:
        record["measured"] = analyze.measure(path)
    except Exception as exc:  # noqa: BLE001 - genuinely any decode failure is recoverable here
        record["warnings"].append(f"measure failed: {exc}")

    if embedding:
        try:
            embedded = analyze.embed_windows(path, checkpoint, amodel)
            record["embedding_windows"] = embedded["vectors"].tolist()
        except Exception as exc:  # noqa: BLE001
            record["warnings"].append(f"embed failed: {exc}")

    return record


def _aggregate_stats(flats: list[dict[str, float]]) -> dict[str, dict]:
    keys = sorted({key for flat in flats for key in flat})
    stats = {}
    for key in keys:
        values = np.asarray([flat[key] for flat in flats if key in flat], dtype=np.float64)
        if len(values) == 0:
            continue
        stats[key] = {"mean": float(values.mean()), "std": float(values.std()),
                      "min": float(values.min()), "max": float(values.max()),
                      "n": int(len(values))}
    return stats


def build_library(root: str | Path, section_types: tuple[str, ...] = SECTION_TYPES,
                  embedding: bool = True, checkpoint: str | None = None,
                  amodel: str = analyze.CLAP_AMODEL) -> dict[str, dict]:
    """One envelope per section type: measured-metric distributions plus the
    per-window CLAP vectors of every reference track of that type."""
    files_by_type = iter_reference_files(root, section_types)
    library = {}
    for section_type, paths in files_by_type.items():
        flats, vectors, warnings = [], [], []
        for path in paths:
            record = analyze_reference_track(path, embedding, checkpoint, amodel)
            warnings += [f"{record['path']}: {w}" for w in record["warnings"]]
            if record["measured"] is not None:
                flats.append(_flatten_measured(record["measured"]))
            if record["embedding_windows"] is not None:
                vectors += record["embedding_windows"]

        centroid = None
        if vectors:
            arr = np.asarray(vectors, dtype=np.float32)
            centroid = arr.mean(axis=0)
            centroid = (centroid / (np.linalg.norm(centroid) + 1e-9)).tolist()

        library[section_type] = {
            "section_type": section_type,
            "files": [str(p) for p in paths],
            "n_tracks": len(paths),
            "n_tracks_measured": len(flats),
            "n_windows": len(vectors),
            "measured_stats": _aggregate_stats(flats),
            "embedding_vectors": vectors,
            "embedding_centroid": centroid,
            "embedding_amodel": amodel if embedding else None,
            "warnings": warnings,
        }
    return library


def save_library(library: dict, path: str | Path) -> Path:
    path = Path(path)
    path.write_text(json.dumps(library, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def load_library(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def zscore(value: float, mean: float, std: float, eps: float = 1e-9) -> float:
    """Dimensionless distance-from-target. This is what makes centroid (~1e2-1e3)
    and flatness (~1e-11) comparable without a metric-specific log transform:
    each metric is scored against its own distribution's scale."""
    return (value - mean) / (std if std > eps else eps)


def score_measured(measured: dict, stats: dict) -> dict:
    """Per-metric z-scores against a section-type envelope, plus one aggregate
    distance (RMS of the per-metric z-scores)."""
    flat = _flatten_measured(measured)
    zscores = {key: zscore(value, stats[key]["mean"], stats[key]["std"])
              for key, value in flat.items() if key in stats}
    if not zscores:
        return {"zscores": {}, "distance": None}
    distance = float(np.sqrt(np.mean(np.square(list(zscores.values())))))
    return {"zscores": zscores, "distance": distance}


def score_embedding(vectors: list, envelope: dict) -> dict:
    """Nearest-window cosine distance: how close the leaf gets to ANY single
    reference moment, not to the reference set's average. This is the mitigation
    for the pooling mismatch noted in analyze.embed_windows — comparing against
    individual windows rather than a centroid-only distance."""
    ref_vectors = envelope.get("embedding_vectors") or []
    if not ref_vectors or not vectors:
        return {"nearest_cosine": None, "centroid_cosine": None, "distance": None}

    ref = np.asarray(ref_vectors, dtype=np.float32)
    leaf = np.asarray(vectors, dtype=np.float32)
    if leaf.ndim == 1:
        leaf = leaf[None, :]
    nearest = float((leaf @ ref.T).max())

    centroid_cosine = None
    if envelope.get("embedding_centroid") is not None:
        centroid = np.asarray(envelope["embedding_centroid"], dtype=np.float32)
        centroid_cosine = float((leaf @ centroid).mean())

    return {"nearest_cosine": nearest, "centroid_cosine": centroid_cosine,
            "distance": 1.0 - nearest}


def score_node(state: dict, library: dict, section_type: str) -> dict:
    """Score a return-channel state.json against one section type's envelope."""
    envelope = library.get(section_type)
    if envelope is None:
        raise KeyError(f"no envelope for section type {section_type!r}; "
                       f"have {sorted(library)}")

    vectors = state.get("embedding_windows")
    if not vectors and state.get("embedding"):
        vectors = [state["embedding"]]  # fallback: pooled-only state.json

    return {
        "section_type": section_type,
        "measured": score_measured(state["measured"], envelope["measured_stats"]),
        "embedding": score_embedding(vectors or [], envelope),
    }
