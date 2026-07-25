"""Assemble state.json — the only thing the deaf loop gets to read about a node."""

from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from . import analyze, rpp

SCHEMA_VERSION = 3  # bumped: state.json now carries embedding_window_levels too


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _versions() -> dict:
    import librosa
    import numpy
    import soundfile
    return {"numpy": numpy.__version__, "librosa": librosa.__version__,
            "soundfile": soundfile.__version__}


def _slice_symbolic(symbolic: dict, region: dict) -> dict:
    """Restrict a project's symbolic data to one region's time span."""
    start, end = region["start"], region["end"]
    sliced = dict(symbolic)
    sliced["notes"] = [n for n in symbolic["notes"] if start <= n["start_s"] < end]
    sliced["bounds"] = dict(symbolic["bounds"], selection={"start": start, "end": end})
    return sliced


def build(project: str | Path, wav: str | Path, symbolic: dict | None = None,
          region: dict | None = None, embedding: bool = True,
          checkpoint: str | None = None, render_info: dict | None = None) -> dict:
    """One node's state: what was specified, what came out, and where it sits."""
    project, wav = Path(project), Path(wav)
    if symbolic is None:
        symbolic = rpp.extract_symbolic(rpp.parse_file(project))
    if region is not None:
        symbolic = _slice_symbolic(symbolic, region)

    started = time.monotonic()
    measured = analyze.measure(wav)
    measure_s = time.monotonic() - started

    embedded = analyze.embed(wav, checkpoint) if embedding else None

    return {
        "meta": {
            "schema_version": SCHEMA_VERSION,
            "node_id": region["name"] if region else project.stem,
            "project": str(project),
            "project_sha256": _sha256(project),
            "wav": str(wav),
            "wav_sha256": _sha256(wav),
            "region": region,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "versions": _versions(),
            "embedding": embedded["meta"] if embedded else None,
            "render": render_info,
            "timing": {
                "measure_s": round(measure_s, 3),
                # Split so a one-time model load never reads as per-leaf cost.
                "clap_load_s": round(embedded["load_s"], 3) if embedded else None,
                "clap_inference_s": round(embedded["inference_s"], 3) if embedded else None,
            },
        },
        "symbolic": symbolic,
        "measured": measured,
        # Bare pooled vector — the shape PROJECT_BRIEF.md's schema specifies.
        "embedding": embedded["vector"] if embedded else None,
        # Unpooled per-window vectors: what reference.py scores against, since
        # comparing a pooled leaf to per-window reference vectors is a mismatch
        # (see analyze.embed_windows). The pooled field above is a convenience
        # summary, not the primary signal.
        "embedding_windows": embedded["vectors"] if embedded else None,
        # Per-window RMS (dB), same windowing as embedding_windows. Lets
        # reference.py gate out near-silent windows before nearest-window
        # scoring -- silence maps to an almost-universal CLAP embedding
        # regardless of source, so an ungated silent window can spuriously
        # "match" any faded reference clip.
        "embedding_window_levels": embedded["window_rms_db"] if embedded else None,
    }


def write(state: dict, path: str | Path) -> Path:
    path = Path(path)
    path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path
