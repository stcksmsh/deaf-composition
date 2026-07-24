"""Audio measurements and the CLAP embedding — the numbers the system steers on."""

from __future__ import annotations

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
CLAP_HOP_S = 10.0


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


def embed(wav_path: str | Path, checkpoint: str | None = None) -> dict:
    """CLAP embedding, reproducing experiments/exp1/exp1_separability.py exactly.

    Imported lazily: the checkpoint is a ~2GB download, and everything else in the
    return channel works without it.
    """
    import laion_clap

    audio, _ = librosa.load(str(wav_path), sr=CLAP_SR, mono=True)
    width, hop = int(CLAP_WINDOW_S * CLAP_SR), int(CLAP_HOP_S * CLAP_SR)
    if len(audio) < width:
        audio = np.pad(audio, (0, width - len(audio)))
    windows = [audio[i:i + width] for i in range(0, len(audio) - width + 1, hop)]

    model = laion_clap.CLAP_Module(enable_fusion=False, amodel="HTSAT-tiny")
    model.load_ckpt(checkpoint) if checkpoint else model.load_ckpt()

    vectors = np.asarray(
        model.get_audio_embedding_from_data(x=np.stack(windows).astype(np.float32),
                                            use_tensor=False),
        dtype=np.float32,
    )
    vectors /= np.linalg.norm(vectors, axis=1, keepdims=True) + 1e-9
    pooled = vectors.mean(axis=0)
    pooled /= np.linalg.norm(pooled) + 1e-9

    return {
        "vector": pooled.tolist(),
        "meta": {
            "model": "laion_clap CLAP_Module",
            "amodel": "HTSAT-tiny",
            "enable_fusion": False,
            "checkpoint": checkpoint or "default",
            "dim": int(pooled.shape[0]),
            "n_windows": len(windows),
            "window_s": CLAP_WINDOW_S,
            "hop_s": CLAP_HOP_S,
            "pooling": "mean+l2",
        },
    }
