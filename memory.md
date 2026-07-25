# memory.md — deaf composition project

## What's built (plan §11 build order)

**Stage 1 — return channel: done.** `src/return_channel/` — `.RPP` parser, headless
xvfb-run render, LUFS/true peak/crest factor/spectral analysis + CLAP embedding,
assembled into `state.json`. Verified end-to-end on real projects. 6 commits on `master`
(`3a3e37c` → `6a04f43`).

**Stage 2 — reference grounding: code done, real library built, one gap found and fixed.**
- `src/return_channel/reference.py` + `reference_cli.py`: ingest a curated fingerprint
  library, build per-section-type target distributions (z-scored measured metrics +
  per-window CLAP vectors), score a leaf by nearest-window cosine distance rather than
  distance-to-centroid.
- Canonical CLAP checkpoint pinned to music-trained HTSAT-base (`4da87c8`) —
  `exp1_checkpoint_comparison.md` has the data/reasoning. Every leaf embedding and every
  reference envelope must use it; `analyze.py` now refuses to guess a checkpoint for any
  non-tiny amodel (raises unless `--checkpoint`/`RETURN_CHANNEL_CLAP_CHECKPOINT` is set).
- **Real fingerprint library exists now**: 25 tracks downloaded (by the user, from their
  own sourcing — I did not and will not automate acquisition of copyrighted audio; see
  `songs.txt`, a YouTube-link list the user made, not committed), cut into 165 clips across
  the 5 section types via `scripts/suggest_boundaries.py` (self-similarity/MFCC novelty
  detection, Foote 2000 — a loudness-only heuristic tried first was fundamentally too weak,
  missed anything that builds via timbre/filter sweep rather than loudness) +
  `scripts/cut_clips.py` + `scripts/label_ui.py` (local stdlib-only web UI for
  playback/editing, `localhost:8765`). `references/` is fully gitignored — raw tracks,
  manifests, and cut clips never enter git; only the tooling does (`207cc4d`).
- Built `reference_library.json` for real (gitignored, regenerate via
  `reference_cli.py build references -o reference_library.json`, needs
  `RETURN_CHANNEL_CLAP_CHECKPOINT` set).
- **Found scoring native_short (test fixture, not real composed material) against it**:
  near-silent audio maps to an almost-universal CLAP embedding region regardless of source
  — a quiet leaf tail was nearest-matching a real reference track's fade-to-silence tail at
  cosine=1.0. Fixed (`493b2ae`): per-window RMS now tracked alongside embeddings
  (`embedding_window_levels` in `state.json`, schema_version 3), windows at/below -50dB
  excluded from both library-building and leaf-scoring.

**Stage 3 — leaf layer: not started.** Blocked on two undecided §10 items: picking a
Reaper-MCP (plan §8.1: "the MCP's typed tools are the DSL"), and curating + dumping the
instrument palette (`manifest.json` doesn't exist yet).

**Node schema frozen in code** (`6a04f43`, plan §3.2): `src/planner/node.py` —
`Node`/`Split`/`Leaf`/`ReviewState`/`ScopeLink`/`NeighborEdge`/`AcceptanceCriteria`/
`ModelTier` dataclasses, JSON-diffable round-trip for §7.3 snapshot persistence. Structure
only, no fold/scheduler logic yet (that's stage 4, on top of this).

## §10 open items status
- [x] Assemble fingerprint reference library
- [x] Freeze node schema
- [ ] Structure reference library (§4.3 — separate purpose, "how to build an arc":
  Four Tet/Floating Points/Burial/etc., model-consumed at planning time, not numeric)
- [ ] Pick the Reaper-MCP
- [ ] Curate instrument palette + dump `manifest.json`
- [ ] Fix nominal tree size → cost one run → candidates-per-$100
- [ ] Choose TTS-modulator source (vocoder, low priority, explicitly deferred)

## Working notes
- `.venv` uses `uv`, no `pip` binary — activate or prefix with `.venv/bin/python`. Plain
  `python`/`python3 -m unittest` won't find `.venv`'s packages.
- CLAP inference is CPU-only, ~1-2s/window per the brief. Building the 165-clip reference
  library takes several minutes — always run in background, don't block on it.
- `git am` risk: a stalled `git am` from an earlier cloud session
  (`session_01PA6ixGgnhvAd8yXRUEHqTi`) sat in `.git/rebase-apply/` for part of this session
  before being resolved by hand (its `analyze.py` hunk assumed a `checkpoint_sha256()`
  helper never actually committed here). If `git status` ever again says "in the middle of
  an am session," back up `.git/rebase-apply/patch` before touching anything — don't
  assume, don't force-apply.
- `songs.txt` (YouTube URLs, the user's source list) and the `exp2b_results*.md` root→
  `experiments/exp2/` relocation are the remaining uncommitted loose ends as of this write
  — deliberately left for the user's call rather than auto-committed (songs.txt especially:
  committing a copyrighted-content source list is a visibility judgment call, not mine to
  make silently, given the project's promotional/HN-facing angle per plan §0).

## Next
1. Research + pick a Reaper-MCP server (blocks all of stage 3).
2. Curate instrument palette from whatever that MCP can introspect + dump `manifest.json`.
3. Decide on `songs.txt` and the `exp2b_results*.md` relocation.
