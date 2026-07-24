"""Audio measurements and the CLAP embedding — the numbers the system steers on."""

from __future__ import annotations

import time
from pathlib import Path

import librosa
import numpy as np
import pyloudnorm
import soundfile as sf
from scipy.signal import resample_poly

N_FFT = 2048
HOP_LENGTH = 512
ROLL_PERCENT = 0.85
SILENCE_GATE_DBFS = -60.0
TRUE_PEAK_OVERSAMPLE = 4

CLAP_SR = 48000
CLAP_WINDOW_S = 10.0
# Half-overlap. exp1 used hop == window, which on an 18s leaf yields a single
# window and leaves 44% of the node unembedded — the steering signal cannot be
# blind to half of each node. Must match whatever built the reference envelopes.
CLAP_HOP_S = 5.0
CLAP_AMODEL = "HTSAT-tiny"

# Loading CLAP costs far more than embedding with it, and a batch embeds many
# leaves per process, so the model is cached rather than rebuilt per call.
_MODELS: dict[tuple[str, str], object] = {}


def _db(x: float) -> float | None:
    return float(20 * np.log10(x)) if x > 0 else None


def _summary(values: np.ndarray) -> dict:
    return {
        "median": float(np.median(values)),
        "mean": float(np.mean(values)),
        "std": float(np.std(values)),
    }


def measure(wav_path: str | Path) -> dict:
    """Loudness and spectral measurements for one rendered stem."""
    data, sr = sf.read(str(wav_path), dtype="float64", always_2d=True)
    warnings = []

    meter = pyloudnorm.Meter(sr)
    lufs = meter.integrated_loudness(data) if len(data) >= int(0.4 * sr) else float("-inf")
    if not np.isfinite(lufs):
        lufs = None
        warnings.append("integrated loudness undefined (signal too short or silent)")

    sample_peak = float(np.max(np.abs(data))) if data.size else 0.0
    oversampled = resample_poly(data, TRUE_PEAK_OVERSAMPLE, 1, axis=0)
    true_peak = float(np.max(np.abs(oversampled))) if oversampled.size else 0.0
    rms = float(np.sqrt(np.mean(np.square(data)))) if data.size else 0.0

    mono = data.mean(axis=1)
    spectrum = np.abs(librosa.stft(mono, n_fft=N_FFT, hop_length=HOP_LENGTH))
    frame_rms = librosa.feature.rms(S=spectrum, frame_length=N_FFT,
                                   hop_length=HOP_LENGTH)[0]
    with np.errstate(divide="ignore"):
        frame_db = 20 * np.log10(np.maximum(frame_rms, 1e-12))

    # native_short.RPP's notes stop at 5.95s of an 18s item, so two thirds of the
    # stem is a decay into silence. Ungated, flatness over near-silence is noise.
    gate = frame_db > SILENCE_GATE_DBFS
    if not gate.any():
        warnings.append("every frame below the silence gate; reporting ungated values")
        gate = np.ones_like(gate, dtype=bool)
    elif gate.mean() < 0.5:
        warnings.append(f"only {gate.mean():.0%} of frames above the silence gate")

    gated = spectrum[:, gate]
    centroid = librosa.feature.spectral_centroid(S=gated, sr=sr)[0]
    rolloff = librosa.feature.spectral_rolloff(S=gated, sr=sr,
                                               roll_percent=ROLL_PERCENT)[0]
    flatness = librosa.feature.spectral_flatness(S=gated)[0]

    return {
        "lufs": lufs,
        "true_peak": _db(true_peak),
        "sample_peak": _db(sample_peak),
        "crest_factor": _db(sample_peak / rms) if rms > 0 else None,
        "spectral_centroid": _summary(centroid),
        "spectral_rolloff": _summary(rolloff),
        "spectral_flatness": _summary(flatness),
        "active_ratio": float(gate.mean()),
        "audio": {
            "sample_rate": sr,
            "channels": data.shape[1],
            "duration_s": len(data) / sr,
            "frames_total": int(len(frame_db)),
            "frames_kept": int(gate.sum()),
        },
        "warnings": warnings,
    }


def windows(audio: np.ndarray, width: int, hop: int) -> list[np.ndarray]:
    """Slice audio into fixed-width windows, anchoring a final one to the end.

    Without the tail anchor the last partial segment is dropped: an 18s file at
    width 10s / hop 5s would otherwise cover only 0-15s.
    """
    if len(audio) < width:
        audio = np.pad(audio, (0, width - len(audio)))
    starts = list(range(0, len(audio) - width + 1, hop))
    if starts[-1] + width < len(audio):
        starts.append(len(audio) - width)
    return [audio[s:s + width] for s in starts]


def _load_model(checkpoint: str | None, amodel: str):
    import laion_clap

    key = (checkpoint or "default", amodel)
    if key not in _MODELS:
        model = laion_clap.CLAP_Module(enable_fusion=False, amodel=amodel)
        model.load_ckpt(checkpoint) if checkpoint else model.load_ckpt()
        _MODELS[key] = model
    return _MODELS[key]


def embed(wav_path: str | Path, checkpoint: str | None = None,
          amodel: str = CLAP_AMODEL) -> dict:
    """CLAP embedding, following experiments/exp1/exp1_separability.py.

    laion_clap is imported lazily: the checkpoint is a ~2GB download, and
    everything else in the return channel works without it.
    """
    audio, _ = librosa.load(str(wav_path), sr=CLAP_SR, mono=True)
    batch = windows(audio, int(CLAP_WINDOW_S * CLAP_SR), int(CLAP_HOP_S * CLAP_SR))

    # Timed separately: a one-time model load must not read as per-leaf cost.
    started = time.monotonic()
    model = _load_model(checkpoint, amodel)
    load_s = time.monotonic() - started

    started = time.monotonic()
    vectors = np.asarray(
        model.get_audio_embedding_from_data(x=np.stack(batch).astype(np.float32),
                                            use_tensor=False),
        dtype=np.float32,
    )
    vectors /= np.linalg.norm(vectors, axis=1, keepdims=True) + 1e-9
    pooled = vectors.mean(axis=0)
    pooled /= np.linalg.norm(pooled) + 1e-9

    return {
        "vector": pooled.tolist(),
        "load_s": load_s,
        "inference_s": time.monotonic() - started,
        "meta": {
            "model": "laion_clap CLAP_Module",
            "amodel": amodel,
            "enable_fusion": False,
            "checkpoint": checkpoint or "default",
            "dim": int(pooled.shape[0]),
            "n_windows": len(batch),
            "window_s": CLAP_WINDOW_S,
            "hop_s": CLAP_HOP_S,
            "pooling": "mean+l2",
        },
    }
