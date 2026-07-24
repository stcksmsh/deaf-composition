# Deaf Composition System — Project Brief for Claude Code

This is the onboarding doc for this repo. Read this first, then `deaf-composition-plan.md`
(the full design spec) before writing any code.

---

## 0. What this project is

An album directed by an AI that has full creative authority (concept, structure, notes,
sound design, arrangement — everything) but **zero access to the audio it produces**. It
steers entirely by measurement: render → extract features/embeddings → compare against
grounded targets → adjust. The human (project owner) builds the system, sets a small set
of hard outer constraints, and acts as the final taste gate — never as a co-composer.

This is a **separate project from MAXIMAVELIANISM** (another album by the same person).
Do not pull concept, theme, vocabulary, or voice-system ideas from that project into this
one — this system's concept must emerge from its own constraints, not be seeded.

Full design reasoning, the node/tree/fold architecture, the reference-library rules, model
routing, and risk analysis all live in **`deaf-composition-plan.md`** — that is the source
of truth for *why* things are designed the way they are. This brief is the *current state
+ immediate task* on top of that plan.

---

## 1. What's already been validated (do not re-litigate these)

Two kill-check experiments were run before any system code was written, specifically to
find out whether the premise was viable at all. Both passed. Their code and outputs live
in `experiments/`.

### Experiment 1 — fingerprint separability (`experiments/exp1_separability.py`)

**Question:** does "good = distance into a reference envelope" carry any real signal?

**Method:** CLAP-embed a curated `target/` set (machine-native records: Justice, 
Gesaffelstein, Objekt, Blawan, Alva Noto, Ryoji Ikeda) against an `offtarget/` set
(warm/performed records: Daft Punk, Four Tet, Floating Points, M83) and check separation.

**Result: SIGNAL PRESENT, cleanly.**
- Cohesion gap: +0.162, silhouette: 0.218 (understated on purpose — target set is
  deliberately multi-modal/spread across the machine-native gamut)
- NN purity (target): 0.995 — a target window's nearest neighbor is almost always another
  target window, across six stylistically different records
- PCA plot shows two visually distinct regions with almost no boundary bleed

**Conclusion:** CLAP embedding distance is a legitimate, usable steering signal for this
system. "Good = measurably in the neighborhood of the reference library" is validated.

### Experiment 2 — render throughput economics (`experiments/exp2b_*`, `experiments/build_test_projects*.lua`)

**Question:** is offline rendering fast/cheap enough for a generate-and-select workflow?

**Confirmed findings, in order of impact:**

1. **Headless (xvfb) vs real display: ~2.7x faster.** Always render via
   `xvfb-run -a reaper -renderproject <path>`. Never render through a real X display in
   the loop.
2. **Batching is the single biggest lever, and it scales cleanly.** Rendering N regions
   in ONE Reaper invocation (via Reaper's "render regions as separate files" mode) costs
   roughly `O + N*r` where `O ≈ 7.6–7.9s` (fixed per-invocation overhead: project load,
   plugin init, render-engine handshake) and `r ≈ 0.15s` (marginal cost per additional
   *cheap-synth* leaf). Confirmed linear at both N=5 and N=20 — no degradation at scale.
   **Implication: always batch multiple leaf renders into one Reaper invocation. Never
   spawn one Reaper process per leaf/iteration.**
3. **Wine/yabridge overhead is real but invocation-level, not leaf-level:** ~+2.9s
   steady-state per invocation (watch for a one-time cold-start spike ~16s on the very
   first run of a session — always do one throwaway warm-up render before timing or
   relying on anything Wine-bridged).
4. **Real DSP load matters and isn't free:** a Surge XT patch with 6-note chords +
   automated cutoff sweep added **+3.46s** over the near-free ReaSynth baseline, in a
   single-leaf invocation. **OPEN QUESTION, not yet resolved:** whether this per-patch
   DSP cost amortizes across a batch the same gentle way the fixed overhead does, or
   whether every leaf in a batch pays its own full DSP tax. This matters a lot for
   real-world (non-toy) render economics and should be tested before assuming the
   optimistic case.
5. **CPU governor and P-core pinning: no measurable effect.** Don't bother with either.

**Conclusion:** rendering is cheap enough (even pessimistically, low minutes for a full
album's leaf-render pass) to support generate-and-select. Render economics are closed as
a blocking question — proceed to building the system.

---

## 2. Environment — DO NOT change these pins without flagging it first

This dependency set was hard-won through several rounds of real breakage (numpy/distutils
on Python 3.12, laion-clap's undeclared torchvision dependency, transformers requiring
torch>=2.4 and silently disabling its torch backend, huggingface_hub removing
`cached_download`). All of it is captured in `experiments/requirements.txt`.

- **Python 3.11 required.** Not 3.12+ — numpy==1.23.5 (hard-pinned by laion-clap) has no
  cp312 wheel, and 3.12 removed distutils, so pip can't build it from source either. Dead
  end on 3.12. Use `uv venv --python 3.11`.
- Key pins: `laion-clap==1.1.6`, `numpy==1.23.5`, `torch==2.2.2`, `torchvision==0.17.2`,
  `transformers==4.30.2`, `huggingface_hub==0.15.1`, `tokenizers==0.13.3`,
  `librosa==0.10.2`, `soundfile==0.12.1`, `scikit-learn==1.4.2`, `matplotlib==3.8.4`.
- If a new dependency (e.g. `pyloudnorm`) conflicts with any of the above, stop and ask
  rather than bumping a pin — this stack broke in non-obvious ways multiple times and
  each fix is documented in conversation history, not just in the file.
- ffmpeg is a system package (`sudo apt install ffmpeg`), needed for non-wav decoding.
- First CLAP model load downloads a ~2GB checkpoint — expect a pause, not a hang.

Reaper rendering: use `xvfb-run -a reaper -renderproject <path>` exactly as validated in
`experiments/exp2b_render_levers_v2.sh`. Batching requires the target `.RPP` to already
have "render regions as separate files" set and saved (this doesn't transfer between
projects — it's a manual one-time step per project via Reaper's Render dialog).

Hardware: personal laptop, i7-13700H, 32GB RAM, no GPU in the render/embed loop (CPU-only
CLAP inference, ~1-2s/window, not a bottleneck). A separate machine with a stronger GPU
exists but is reserved for occasional batch/training jobs, not the live loop — don't design
around GPU availability being in the hot path.

---

## 3. Test assets already in the repo (`experiments/`)

Built via ReaScript (`build_test_projects.lua`, `build_test_projects_2.lua`) rather than
hand-authored, because plugin state in a `.RPP` is an opaque binary chunk even though the
surrounding file is plaintext — building via Reaper's own API is the reliable path.

- `native_short.RPP` — ~18s, single ReaSynth track, melodic MIDI line. Known ground truth:
  exact note count/pitches are whatever `add_midi_notes` in the build script generated —
  read the script to get exact values if writing parser regression tests against it.
- `wine_short.RPP` — same shape, Pigments via yabridge instead of ReaSynth.
- `heavy_patch_short.RPP` — Surge XT, 6-note chords x6 repeats + automated cutoff sweep.
  Confirmed via `grep -i surge heavy_patch_short.RPP`.
- `batch_regions.RPP` / `batch_regions_20.RPP` — 5 and 20 regions respectively, native
  ReaSynth, for batched-render testing. **Both require the manual render-mode step
  (Bounds=Regions, "render regions as separate files", click Render once, re-save) before
  they'll produce multiple output files headless — verify file count before trusting any
  timing run against these.**
- `exp1_separability.py`, `requirements.txt` — working CLAP pipeline.
- `exp2b_render_levers_v2.sh` — working render-timing harness, good reference for how to
  invoke Reaper headless correctly.

---

## 4. The immediate task: build the "return channel"

This is the first real system component (see plan §8.1). Everything above is context;
this section is the actual work.

**Goal:** given a Reaper project (or a project + region), produce one `state.json`
containing symbolic ground truth (what was actually specified), measured audio features
(what actually came out), and a perceptual embedding (how it sits relative to the
reference library). This is the foundation the whole fold/review system reads from.

**Build in this order — get `native_short.RPP` through all three stages end-to-end,
crudely if necessary, before improving any single stage:**

1. **`.RPP` parser.** Read a couple of the real `.RPP` files in `experiments/` directly
   first — don't write a parser from a remembered/assumed format. Extract: track list, FX
   chain per track (plugin names + any readable params), MIDI note data per item
   (pitch/velocity/start/end), automation envelope points, tempo/time signature,
   render/region bounds.

2. **Render step.** Given a project path (+ optional region), render headless using the
   exact pattern already proven in `exp2b_render_levers_v2.sh`. Return the output wav
   path. Don't reinvent the invocation — reuse what's already validated.

3. **Analyze step.** Given a wav path: LUFS (`pyloudnorm`), true peak, crest factor,
   spectral centroid/rolloff/flatness (`librosa`), and a CLAP embedding (reuse the exact
   model-loading code and checkpoint from `experiments/exp1_separability.py` — same
   environment, don't deviate).

4. **Assemble `state.json`** per node:
   ```json
   {
     "symbolic": { "tracks": [...], "fx": [...], "notes": [...], "automation": [...],
                   "tempo": ..., "time_sig": ..., "bounds": ... },
     "measured": { "lufs": ..., "true_peak": ..., "crest_factor": ...,
                   "spectral_centroid": ..., "spectral_rolloff": ...,
                   "spectral_flatness": ... },
     "embedding": [ ... ]
   }
   ```

**Working method:**
- Vertical slice first, breadth second — one real `state.json` from `native_short.RPP`
  beats a polished parser with no render/analyze step behind it yet.
- Write at least one regression test against `native_short.RPP`'s known ground truth
  (check the build script for exact note count/pitches — don't guess).
- Don't touch any pin in section 2 without stopping to flag it first.
- Ask before installing anything not already covered by `experiments/requirements.txt`.

Show the resulting `state.json` before building anything further on top of it — it needs
to be checked against the design doc's node schema (plan §3.2) and the measurement spec
(plan §4) before the tree/fold logic gets built on this foundation.
