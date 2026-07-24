#!/usr/bin/env python3
"""
Experiment 1 - Fingerprint separability kill-check.

QUESTION being answered:
    Does "good = distance into the reference envelope" carry any signal?

METHOD:
    Embed reference audio with LAION-CLAP. Check whether on-target tracks
    cluster tightly in embedding space AND sit measurably apart from
    off-target tracks. If they do, the deaf loop has a real steering signal.
    If everything smears together, STOP - you have no usable "good" metric,
    and no amount of architecture fixes that.

EXPECTED LAYOUT:
    references/
      target/       <- records you WANT to sound near (Cross, Alva Noto, Objekt...)
        cross_a.wav
        alvanoto_b.wav
        ...
      offtarget/    <- records that SHOULD score far (RAM, Junk, warm/performed)
        ram_a.wav
        junk_b.wav
        ...
    Any sample rate / length / channel count. wav/flac fine; mp3 needs ffmpeg.

SETUP (CPU is fine for this - it's a one-shot):
    python -m venv .venv && source .venv/bin/activate
    pip install laion-clap librosa soundfile scikit-learn matplotlib numpy

RUN:
    python exp1_separability.py --root ./references --window 10 --hop 10

NOTE ON CHECKPOINT:
    Defaults to the stock LAION-CLAP checkpoint, which is enough for a first
    pass. For the music-trained checkpoint (better for this use case), pass
    --ckpt /path/to/music_audioset_epoch_15_esc_90.14.pt
    and set --amodel HTSAT-base to match it.
"""

import argparse
import sys
from pathlib import Path

import numpy as np


def die(msg: str, code: int = 1):
    print(f"\n[FATAL] {msg}\n", file=sys.stderr)
    sys.exit(code)


def load_windows(path: Path, sr: int, window_s: float, hop_s: float):
    """Load one file, return a list of fixed-length float32 windows at `sr` mono."""
    import librosa
    try:
        y, _ = librosa.load(str(path), sr=sr, mono=True)
    except Exception as e:
        print(f"  [skip] {path.name}: {e}")
        return []
    w = int(window_s * sr)
    h = int(hop_s * sr)
    if len(y) < w:
        # pad short files up to one window rather than dropping them
        y = np.pad(y, (0, w - len(y)))
    out = []
    for start in range(0, len(y) - w + 1, h):
        out.append(y[start:start + w].astype(np.float32))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="./references")
    ap.add_argument("--window", type=float, default=10.0, help="window length (s)")
    ap.add_argument("--hop", type=float, default=10.0, help="hop between windows (s)")
    ap.add_argument("--sr", type=int, default=48000)
    ap.add_argument("--ckpt", default=None, help="optional CLAP checkpoint path")
    ap.add_argument("--amodel", default="HTSAT-tiny",
                    help="audio model arch; use HTSAT-base with the music ckpt")
    ap.add_argument("--out", default="exp1_out")
    args = ap.parse_args()

    root = Path(args.root)
    tdir, odir = root / "target", root / "offtarget"
    if not tdir.is_dir() or not odir.is_dir():
        die(f"expected {tdir} and {odir} to exist, each with audio files")

    try:
        import laion_clap
    except Exception as e:
        import traceback
        traceback.print_exc()
        die(f"could not import laion_clap ({type(e).__name__}: {e}).\n"
            f"If this is a huggingface_hub / transformers mismatch, pin the trio:\n"
            f"  uv pip install 'transformers==4.30.2' "
            f"'huggingface_hub==0.15.1' 'tokenizers==0.13.3'")

    outdir = Path(args.out)
    outdir.mkdir(exist_ok=True)

    # --- load model ---
    print("[*] loading CLAP...")
    model = laion_clap.CLAP_Module(enable_fusion=False, amodel=args.amodel)
    if args.ckpt:
        model.load_ckpt(args.ckpt)
    else:
        model.load_ckpt()  # downloads the default checkpoint

    # --- gather windows ---
    embeddings, labels, tracks = [], [], []
    for label, d in (("target", tdir), ("offtarget", odir)):
        files = sorted([p for p in d.iterdir()
                        if p.suffix.lower() in {".wav", ".flac", ".mp3", ".ogg", ".m4a"}])
        if not files:
            die(f"no audio files found in {d}")
        print(f"[*] {label}: {len(files)} files")
        for f in files:
            wins = load_windows(f, args.sr, args.window, args.hop)
            if not wins:
                continue
            batch = np.stack(wins)  # (N, samples)
            emb = model.get_audio_embedding_from_data(x=batch, use_tensor=False)
            emb = np.asarray(emb, dtype=np.float32)
            embeddings.append(emb)
            labels += [label] * len(wins)
            tracks += [f.stem] * len(wins)
            print(f"    {f.name}: {len(wins)} windows")

    X = np.concatenate(embeddings, axis=0)
    X = X / (np.linalg.norm(X, axis=1, keepdims=True) + 1e-9)  # L2 normalize
    y = np.array(labels)
    is_t = y == "target"
    print(f"\n[*] total windows: {len(X)}  (target={is_t.sum()}, offtarget={(~is_t).sum()})")

    # --- metric 1: cohesion vs separation (cosine on normalized embeddings) ---
    def mean_pairwise_cos(A, B=None):
        if B is None:
            S = A @ A.T
            iu = np.triu_indices(len(A), k=1)
            return float(S[iu].mean())
        return float((A @ B.T).mean())

    T, O = X[is_t], X[~is_t]
    intra_t = mean_pairwise_cos(T)
    intra_o = mean_pairwise_cos(O)
    inter = mean_pairwise_cos(T, O)
    print("\n--- cohesion / separation (cosine) ---")
    print(f"  intra-target cohesion : {intra_t:+.3f}   (higher = target set is tight)")
    print(f"  intra-offtarget       : {intra_o:+.3f}")
    print(f"  target <-> offtarget  : {inter:+.3f}   (lower than intra = separated)")
    gap = intra_t - inter
    print(f"  cohesion gap          : {gap:+.3f}   (want clearly positive)")

    # --- metric 2: silhouette (target vs offtarget) using cosine distance ---
    from sklearn.metrics import silhouette_score
    try:
        sil = silhouette_score(X, is_t.astype(int), metric="cosine")
    except Exception as e:
        sil = float("nan")
        print(f"  [warn] silhouette failed: {e}")
    print(f"\n  silhouette (2-cluster): {sil:+.3f}   "
          f"(<0.1 weak, 0.1-0.25 modest, >0.25 clear)")

    # --- metric 3: nearest-neighbour purity ---
    S = X @ X.T
    np.fill_diagonal(S, -np.inf)
    nn = S.argmax(axis=1)
    same = (y[nn] == y).mean()
    t_same = (y[nn][is_t] == "target").mean()
    print(f"\n  NN label purity (all) : {same:.3f}")
    print(f"  NN purity (target)    : {t_same:.3f}   "
          f"(target windows whose nearest neighbour is also target)")

    # --- 2D projection for eyeballing ---
    try:
        from sklearn.decomposition import PCA
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        P = PCA(n_components=2).fit_transform(X)
        plt.figure(figsize=(7, 6))
        plt.scatter(P[is_t, 0], P[is_t, 1], s=14, alpha=.7, label="target")
        plt.scatter(P[~is_t, 0], P[~is_t, 1], s=14, alpha=.7, label="offtarget")
        plt.legend(); plt.title("CLAP embedding space (PCA)")
        plt.tight_layout()
        fig = outdir / "embedding_pca.png"
        plt.savefig(fig, dpi=120)
        print(f"\n[*] wrote {fig}")
    except Exception as e:
        print(f"  [warn] plot skipped: {e}")

    # --- verdict ---
    signal = (gap > 0.05) and (sil == sil and sil > 0.1) and (t_same > 0.65)
    print("\n" + "=" * 52)
    if signal:
        print("VERDICT: SIGNAL PRESENT.")
        print("Targets cohere and separate from off-target. The 'distance")
        print("into the envelope' metric is worth building on. Proceed to")
        print("experiment 2 (render throughput).")
    else:
        print("VERDICT: WEAK / NO SEPARATION.")
        print("The steering signal is not clearly there with this corpus +")
        print("embedding. Before writing any system code: try the music-")
        print("trained CLAP checkpoint, tighten the target set (it may be")
        print("too stylistically broad), or reconsider whether 'good' is")
        print("measurable this way. This is the cheap place to find out.")
    print("=" * 52)


if __name__ == "__main__":
    main()
