# memory.md — deaf composition project

## What's built (plan §11 build order)

**Stage 1 — return channel: done.** `src/return_channel/` — `.RPP` parser, headless
xvfb-run render, LUFS/true peak/crest factor/spectral analysis + CLAP embedding,
assembled into `state.json`. Verified end-to-end on real projects.

**Stage 2 — reference grounding: done, real library built, one gap found and fixed.**
- `src/return_channel/reference.py` + `reference_cli.py`: ingest a curated fingerprint
  library, build per-section-type target distributions (z-scored measured metrics +
  per-window CLAP vectors), score a leaf by nearest-window cosine distance rather than
  distance-to-centroid.
- Canonical CLAP checkpoint pinned to music-trained HTSAT-base (`4da87c8`) —
  `exp1_checkpoint_comparison.md` has the data/reasoning. Every leaf embedding and every
  reference envelope must use it; `analyze.py` refuses to guess a checkpoint for any
  non-tiny amodel (raises unless `--checkpoint`/`RETURN_CHANNEL_CLAP_CHECKPOINT` is set).
- **Real fingerprint library exists**: 25 tracks (sourced by the user — I did not and will
  not automate acquisition of copyrighted audio; `songs.txt` is the user's own YouTube-link
  list, deliberately not committed), cut into 165 clips across the 5 section types via
  `scripts/suggest_boundaries.py` (self-similarity/MFCC novelty detection, Foote 2000 — a
  loudness-only heuristic tried first was too weak, missed anything that builds via
  timbre/filter sweep rather than loudness) + `scripts/cut_clips.py` + `scripts/label_ui.py`
  (local stdlib-only web UI, `localhost:8765`). `references/` is fully gitignored; only the
  tooling is committed (`207cc4d`).
- `reference_library.json` built for real (gitignored — regenerate via
  `reference_cli.py build references -o reference_library.json`, needs
  `RETURN_CHANNEL_CLAP_CHECKPOINT`).
- **Silence-collapse gap found scoring native_short (test fixture) against the real
  library, and fixed** (`493b2ae`): near-total-silence maps to an almost-universal CLAP
  embedding region regardless of source — a quiet leaf tail nearest-matched a real
  reference track's fade-out at cosine=1.0. Per-window RMS now tracked
  (`embedding_window_levels` in `state.json`, schema_version 3); windows at/below -50dB
  excluded from both library-building and leaf-scoring. Verified fixed on the real
  library: native_short's outro score went from a spurious 1.0 to a sane ~0.37, in line
  with its scores against every other section type.

**Node schema frozen in code** (`6a04f43`, plan §3.2): `src/planner/node.py` —
`Node`/`Split`/`Leaf`/`ReviewState`/`ScopeLink`/`NeighborEdge`/`AcceptanceCriteria`/
`ModelTier` dataclasses, JSON-diffable round-trip for §7.3 snapshot persistence. Structure
only, no fold/scheduler logic yet (stage 4, on top of this).

**Reaper-MCP picked AND installed/validated: TwelveTake-Studios/reaper-mcp** (`0331ac0`).
Compared against shiehn/total-reaper-mcp (600+ tools/40+ categories, 64 stars, more
comprehensive but likely too large a surface for a cheap leaf-implementation model to
search per plan §6) and a few smaller/less mature options. TwelveTake:
~129-158 tools, cleanly categorized (explicit FX-param-automation tools, region/rendering
tools matching the batching approach exp2 already validated), MIT license, versioned
(v1.6.0 + changelog — real maintenance signal), file-based Lua-bridge IPC (no network/port
setup, fits the already-headless workflow).

**Installed and hands-on validated this session**: `.mcp.json` configures Claude Code to
run it via `uvx twelvetake-reaper-mcp` — new project-scoped MCP servers need approval and
only take effect on the *next* session/reconnect, they don't hot-load into a running one.
The Lua bridge (vendored at `scripts/reaper_mcp_bridge.lua`) runs headless via
`scripts/start_reaper_mcp_bridge.sh start`, which self-verifies by round-tripping a real
`GetAppVersion` request through the file protocol before reporting success. Manually
confirmed `GetAppVersion`/`CountTracks`/`InsertTrackAtIndex` all round-trip correctly
against a live headless REAPER instance, independent of the MCP layer itself.

Real gotchas hit getting it running the first time, now baked into the launcher script and
noted in Working Notes below: `ShowConsoleMsg` output is invisible under Xvfb so it can't
be used to confirm startup, the bridge directory can take 10-20s to appear (headless
audio/plugin-scan cost), and `xvfb-run`'s own PID isn't enough to kill what it spawns.
`.mcp.json`-configured tools won't appear in *this* conversation — needs a session
reconnect + approval first.

**Instrument palette identified, manifest.json dumped for real, curation NOT done.**
Installed and confirmed working: ReaSynth (native, 18 params), Surge XT (native VST3, 778
real params after filtering REAPER's auto-generated MIDI-CC noise out of a raw 2858),
Vital (native VST3, 775/2855), Pigments (yabridge/Wine-bridged, 2369/4449 — crashed REAPER
once via a yabridge socket read failure before dumping cleanly on retry; likely the same
Wine cold-start flakiness the brief already warns about, not yet fully root-caused).
Contrary to plan §5's own worry, none of the four exposed generic "Param 1"-style names —
all real, meaningful param names. Presets came back empty for all four; `TrackFX_GetPreset`
isn't surfacing factory presets as expected, not root-caused.
`scripts/dump_manifest.lua` + `dump_manifest.py` (`ca58408`) do the dumping — turned out to
need zero MCP integration, since Reaper's CLI runs `.lua` scripts directly
(`reaper script.lua`); manifest dumping and runtime leaf control are decoupled concerns.
**Real remaining work, explicitly not done**: curating which ~20-40 of each synth's
hundreds of real params actually belong in the leaf DSL vocabulary. That's a creative call
(plan §2's cage/freedom split puts "curated instrument palette" in the human's cage) — not
something to truncate silently. `manifest.json` itself is gitignored (regenerate via the
dump script) since it's large and environment-dependent.

**Stage 3 — leaf layer: still not started**, but no longer blocked on open decisions —
Reaper-MCP is picked (needs installing/wiring), manifest dumping works (needs the param
curation pass). Both are concrete, scoped next actions now rather than open research.

## §10 open items status
- [x] Assemble fingerprint reference library
- [x] Freeze node schema
- [x] Pick the Reaper-MCP (picked AND installed/validated)
- [~] Curate instrument palette + dump `manifest.json` (dumped; per-plugin param curation
  still open, see above)
- [ ] Structure reference library (§4.3 — separate purpose, "how to build an arc":
  Four Tet/Floating Points/Burial/etc., model-consumed at planning time, not numeric)
- [ ] Fix nominal tree size → cost one run → candidates-per-$100
- [ ] Choose TTS-modulator source (vocoder, low priority, explicitly deferred)

## Working notes
- `.venv` uses `uv`, no `pip` binary — activate or prefix with `.venv/bin/python`. Plain
  `python`/`python3 -m unittest` won't find `.venv`'s packages.
- CLAP inference is CPU-only, ~1-2s/window. Building the 165-clip reference library takes
  several minutes — always run in background, don't block on it.
- **`xvfb-run` process cleanup**: it's a wrapper script that forks Xvfb + the real command
  as children. Killing the `xvfb-run` PID alone does NOT kill those children — orphans a
  live Reaper (plus wineserver/yabridge-host for bridged plugins) running in the
  background. Always launch with `start_new_session=True` (Python) and kill the whole
  process group (`os.killpg`), not just the direct child PID. Bit twice by this in one
  session before catching it — see `scripts/dump_manifest.py`.
- **Reaper's own quit command hangs under Xvfb** if the project has unsaved changes — it
  waits for a dialog click that can never come (no window manager, no automation). Don't
  rely on a script's own `Main_OnCommand(40004, 0)` to actually exit the process; poll for
  the expected output file instead and kill externally once it's settled.
- Bridged (Wine/yabridge) plugins can abort the whole REAPER process on init, not just
  fail gracefully — write any multi-step result incrementally, not once at the end, or a
  late crash erases everything gathered before it.
- **`reaper.ShowConsoleMsg` output only reaches REAPER's own GUI console** — invisible
  under Xvfb, cannot be used to confirm a script started or is behaving. Use file-based
  signals (a marker file, the actual expected output) to verify headless script execution.
- A freshly-launched headless REAPER instance can take **10-20s before a `reaper.defer`
  loop is actually live** (audio device probing / plugin scan first) — a short timeout
  reads as "broken" when it's just slow. `scripts/start_reaper_mcp_bridge.sh` polls up to
  60s and round-trips a real request before declaring success, not just checks a directory
  exists.
- New MCP servers added via `.mcp.json` need approval and only take effect on the *next*
  Claude Code session/reconnect — they do not hot-load into an already-running session.
- `git am` risk: a stalled `git am` from an earlier cloud session
  (`session_01PA6ixGgnhvAd8yXRUEHqTi`) sat in `.git/rebase-apply/` for part of this session
  before being resolved by hand (its `analyze.py` hunk assumed a `checkpoint_sha256()`
  helper never actually committed here). If `git status` ever again says "in the middle of
  an am session," back up `.git/rebase-apply/patch` before touching anything — don't
  assume, don't force-apply.
- `songs.txt` (YouTube URLs, the user's source list) is the one remaining uncommitted loose
  end — deliberately left for the user's call rather than auto-committed: committing a
  copyrighted-content source list is a visibility judgment call, not mine to make silently,
  given the project's promotional/HN-facing angle per plan §0.

## Next
1. **Restart/reconnect the Claude Code session** and approve the `reaper` MCP server —
   `.mcp.json` is written but not live in whatever session reads this. Once reconnected,
   `scripts/start_reaper_mcp_bridge.sh start` needs to have been run first (bridge must be
   up before the MCP server can talk to it).
2. Curate the actual leaf-facing param subset per palette plugin (creative call, needs the
   user) — now doable interactively through the live MCP tools instead of blind.
3. Decide on `songs.txt`.
4. Only after 1-2: start stage 3 (leaf layer / DSL emission).
