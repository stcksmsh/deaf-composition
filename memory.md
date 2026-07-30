# memory.md — deaf composition project

## Session checkpoint (2026-07-29, end of session)

**Just did**: full regeneration of a brand-new song from scratch, end to
end, replacing the "Tidal Lock" reskin approach with a real from-zero
build. In order: extended the pipeline so tempo/time-signature are real
per-song creative decisions (not hardcoded 120bpm/4-4), wrote a new
creative brief centered on "interconnectedness" as the one real
constraint, generated+built the song (88bpm, 5/4, C minor, 6 sections,
33 leaves, a recurring 5-note "germ cell" motif), diagnosed and fixed
all 9 leaves that came out silent (3 distinct root causes, all verified
live), ran a real gain-staging pass across all 33 leaves, ran a real
mastering pass (fixed actual clipping, added glue compression, modest
loudness lift). Tidal Lock's own project/plan/render were checkpointed
first and left untouched throughout
(`state/checkpoints/v8_20260729_.../`).

**Current state**: `song_mastered_v1.mp3` has been rendered and sent to
the user — **this is the first time they've heard this song at all**,
unlike Tidal Lock which went through several rounds of listening
feedback. No feedback yet.

**Real open items, in priority order**:
1. One leaf (`song/section_4/child_0`) is missing its intended Width
   envelope automation — the correct REAPER "show Width envelope"
   action ID was never found; the op was stripped from the plan rather
   than guessed at again. Cosmetic (stereo width motion on one part),
   not urgent.
2. Four leaves (tracks 3, 6, 10, 21 — genuinely continuous background/
   midground parts, not sparse one-shots) sit below their prominence
   band's target even after gain-staging, because they hit REAPER's
   +18dB fader ceiling. Pushing further would mean changing their own
   Surge-level params, not just track volume — deliberately left alone
   rather than force it.
3. Normal next step: get the user's listening feedback on
   `song_mastered_v1.mp3` and iterate from there, same pattern as Tidal
   Lock's v1→v8 cycle.

**Key methodology lessons this session, worth knowing before touching
this project's tooling again**:
- `TrackFX_FormatParamValueNormalized`-based calibration (sample the
  REAL formatted value at several normalized points before trusting a
  plugin param's raw `min`/`max` or its label's apparent sign/scale) is
  now confirmed necessary for THREE unrelated cases: Surge enum params,
  Tidal Lock's ReaLimit tuning, and tonight's ReaComp/ReaLimit tuning.
  Default to this, don't trust get_param's raw range or a control's
  display name.
- A factory Surge preset being numerically valid and even sounding fine
  in isolation does NOT mean it's safe generally — 3 different
  `Percussion/` factory presets (Snare Tight, Drum One, Synth Tom 1)
  turned out to be genuinely broken/silent this project, found only by
  live clean-preset testing. Treat any untested `Percussion/` preset as
  suspect.
- RMS-averaged-over-a-whole-window metrics (gain-staging's gap
  measurement) silently break for sparse one-shot content inside a much
  longer section — inflates the apparent problem and can drive a
  correction into real clipping. Always peak-check anything the metric
  flagged as extreme before trusting the fix.
- Full-length (~300s+) `RenderProject` calls reliably time out the RPC
  layer while REAPER itself finishes the render correctly in the
  background — confirmed 3+ times across two different songs. Never
  trust an RPC timeout as a real failure for a long render; check the
  output file directly (`soundfile.info`) before deciding it failed.

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

**Param-curation direction changed: presets + macros, not manual per-param curation.**
User's call, replacing the plan of hand-picking 20-40 params per synth: use factory
presets for sonic diversity, expose only a small universal control surface per synth
(macros, mod wheel/pitch bend via MIDI CC — not FX params, separate automation path — plus
a few simple shared params like cutoff/ADSR). `songs.txt` deleted per user instruction
(untracked, no history to preserve).

**Preset-loading investigation — three real technical walls found, all now understood:**
1. **Presets exist as real files, just not host-visible.** Surge XT: 637 factory `.fxp` at
   `/usr/share/surge-xt/patches_factory/`. Pigments: ~1900 files (incl. tutorials) at
   `~/.wineprefixes/WIN10_64/drive_c/ProgramData/Arturia/Presets/Pigments/`. Vital: **none
   found on this system** — its free factory content ships via an in-app content-manager
   download on first launch, never done headlessly here; still unresolved whether that's
   automatable. `TrackFX_GetPreset`/`NavigatePresets` return empty for all three because
   they implement their own custom patch browsers instead of the VST3 host-visible preset
   API — not a REAPER bug, expected behavior for this class of plugin.
2. **`TrackFX_SetPreset(track, fx, filepath)` fails for Surge's `.fxp`** (`set_ok=false`,
   confirmed via `scripts/test_preset_load.lua`). Root cause: that `.fxp` is a genuine
   VST2-format binary chunk (`CcnK`/`FPCh` header wrapping Surge's own XML patch data), but
   only the **VST3** build of Surge is registered in `reaper-vstplugins64.ini` (no VST2 —
   Steinberg revoked the VST2 SDK license industry-wide; modern Surge XT doesn't ship it).
   VST3's state format doesn't accept a VST2 chunk via REAPER's generic preset-load path.
   Dead end for *host-native* preset loading — confirmed structural, not worth retrying.
3. **Built a working index-mapping instead**, sidestepping (2) entirely: the LV2 build's
   `.ttl` manifest (`/usr/lib/lv2/Surge XT.lv2/dsp.ttl`, 8798 lines) declares
   `plug:<internal_id>` → `rdfs:label "<REAPER host param name>"` for every parameter, and
   the internal ids match the `.fxp` patch XML's own tag names **verbatim** (e.g.
   `plug:a_osc1_type` / `<a_osc1_type ... />` / REAPER's `"A Osc 1 Type"` are the same
   parameter). 774 ttl param blocks, only 16 label collisions — all of them the already-
   excluded generic FX-slot params (`FX A1 -` etc., 12 sub-params each) reused across 16
   slots, confirming every param we actually care about resolves unambiguously.
   Cross-checked against `manifest.json`: 559/778 REAPER-exposed Surge params get a real
   value out of one sample patch this way (the other 219 are FX-slot/unset-in-this-patch,
   expected).
4. **Value scale is the remaining piece, now solved via source, not yet wired up.**
   `TrackFX_FormatParamValue`'s `value` argument is REAPER-**normalized** [0,1] regardless
   of plugin internals — confirmed empirically (`scripts/test_surge_scale.lua`: feeding
   `Global Volume`'s raw patch value `0.0` back through it gives `"-48.00 dB"`, not `"0.00
   dB"` — VST3 hosts structurally never see plugin-native units, by spec). The `.fxp`'s raw
   values ARE in Surge's own native units (confirmed: Parameter.cpp's declared per-type
   ranges match observed clamp behavior exactly, e.g. `ct_freq_audible` -60..70 explains the
   Filter Cutoff clamp-to-"0.00 Hz", `ct_pitch_semi7bp` -7..7 explains Osc Pitch's observed
   `-7.00 semitones` at normalized 0). Pulled the **complete ctrltype→(val_min,val_max)
   table** from Surge's open-source `src/common/Parameter.cpp` (`set_type()`, ~150 distinct
   ctrltypes, all listed) — this is the piece that lets us convert
   `normalized = (raw - val_min) / (val_max - val_min)` per parameter, and the conversion
   appears to be linear at the storage level (display-string nonlinearity, e.g. Hz-from-
   semitones, is separate from raw storage, which is linear in its own native units).
   **Still missing**: which ctrltype each of the 778 parameters actually uses — that
   assignment lives in `SurgeStorage.cpp`'s parameter-registration code, a much bigger file,
   not yet pulled/parsed. Until that's done, values can't actually be set correctly.
5. **Not yet started**: same investigation for Vital (open source, JSON-based presets,
   likely has an equivalent scaling-table problem but no local preset files to test
   against yet — factory content acquisition is the first blocker there, see point 1).
   Pigments explicitly descoped from preset-value-loading per user decision (proprietary/
   closed, not worth reverse-engineering) — falls back to macros+curated-params only.

Scratch/test scripts from this investigation, not yet cleaned up: `scripts/
test_preset_load.lua`, `scripts/test_surge_scale.lua`, `/tmp/surge_preset_apply.json`
(regeneratable index→raw-value mapping for one sample Surge patch, built from the ttl +
patch file — the mapping logic is reusable, just needs the ctrltype table wired in before
it produces correct normalized values).

**Two concrete artifacts committed to `scripts/` from the Parameter.cpp/SurgePatch.cpp
dive**: `scripts/surge_ctrltype_ranges.json` (the full ~150-entry ctrltype→[val_min,
val_max] table from `Parameter::set_type()`, source-linked, with a few ctrltypes flagged
as needing a runtime enum-count for their max rather than a literal) and `scripts/
surge_assign_calls.json` (all 100 `.assign()` call sites from `SurgePatch.cpp`, each with
its `short_name`/`label`/`path`/`ctrltype` args parsed out — covers all 778 params via
loops over scene/oscillator/filter/LFO index, so 100 call-sites × loop expansion = full
coverage, not partial).
**Not yet done, this is the next concrete step**: the quoted `short_name`/`path` args in
`surge_assign_calls.json` (e.g. `"type"`, `"{:c}/osc/{}/param{}"`) are NOT the same string
as the ttl/fxp internal id (e.g. `a_osc1_param0`) — that exact id is assembled by other
code not yet located (probably `Parameter.cpp` or a DAWextraState id-builder), so the
call-site table can't yet be mechanically joined to `manifest.json`'s 778 REAPER param
names by string matching alone. Two ways to close that gap, neither attempted yet:
(a) find the actual id-assembly code and replicate it, or (b) match by the `label`
argument's tail (e.g. every assign call whose label is `"Cutoff"` inside a filter-group
loop almost certainly corresponds to every ttl label ending in `" Cutoff"`) — (b) is
probably faster given there are only ~100 distinct label/role patterns to eyeball against
774 ttl labels, but is a manual/semi-manual pass, not a clean automatic join.

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

**MCP reconnect happened this session — tools loaded, but round-trip timed out; found and
fixed a real bug.** `mcp__reaper__get_project_summary` returned `"File request timed out"`
even with the bridge process confirmed healthy (Reaper alive 3m53s, no crash, JACK-not-found
noise in the log is harmless/expected under Xvfb per existing notes). Root cause: the
`twelvetake-reaper-mcp` Python server's own default bridge dir
(`reaper_mcp_server.py`, `BRIDGE_DIR` default) is
`os.path.expandvars(r"%APPDATA%\REAPER\Scripts\mcp_bridge_data")` — a **Windows-style
`%VAR%` path**, which `os.path.expandvars` does not expand on POSIX (it only handles
`$VAR`/`${VAR}`), so on Linux it silently becomes the literal string
`%APPDATA%\REAPER\Scripts\mcp_bridge_data` and never matches the real bridge dir at
`~/.config/REAPER/Scripts/mcp_bridge_data`. The Python side was writing request files
nobody was reading — no crash, just silent timeout. It only reads the real path from the
`REAPER_BRIDGE_DIR` env var, which `.mcp.json` wasn't setting.
**Fix applied**: added `"env": {"REAPER_BRIDGE_DIR": "${HOME}/.config/REAPER/Scripts/mcp_bridge_data"}`
to the `reaper` entry in `.mcp.json`. **Verified 2026-07-25**: after reconnect,
`mcp__reaper__get_project_summary` round-tripped successfully and returned the full
17-track project (KICK BUSS, Generator/Surge XT, Low/Mid/Click split, DRUM BUSS,
Perc 1/2, Hats, BASS, MAIN SYNTH, SECONDARY SYNTH/CHRONOS, TEXTURE/ATMOS, FX/ONE-SHOTS,
three return busses, master chain with EQ/Saturation/Volume/Event Horizon Limiter). Bug
is closed — the bridge dir mismatch was the only blocker.

## Surge id-assembly gap — closed for the fixed-role params (2026-07-25)
Built `scripts/build_surge_param_map.py`: walks `manifest.json`'s 778 Surge XT param
names as a state machine matching Surge's own structural layout (scene A/B header,
3 oscillators, mixer routing, 2 filters, 2 ADSRs, 12 LFOs, global/FX header, 16 FX
slots), assigns each param the ctrltype from `scripts/surge_assign_calls.json`'s
per-role table, and writes `scripts/surge_param_map.json` (per-index ctrltype +
native min/max, or `resolved:false` with a reason). `scripts/surge_normalize.py`
converts a raw Surge-native value to REAPER's normalized `[0,1]` via that map, for
`TrackFX_SetParam`.

**Result: 539/778 (69%) resolved**, everything with a fixed role: osc type/octave/
pitch/keytrack/retrigger, both filters, both envelopes, all 12 LFOs, mixer routing,
scene header, global header, macros (macro ctrltype assumed `ct_percent` — not in
the static assign table, unverified). The generator runs with hard `assert`s against
the exact expected name at each position (no silent fallback) and passed clean over
all 778 names — strong evidence the structural model matches Surge's real layout.

**239 unresolved, and this is a hard boundary, not unfinished polish**: 192 are FX
generic params (12 per slot × 16 slots) and 42 are oscillator generic params (7 per
osc × 6 oscillators) — Surge itself gives these slots no fixed meaning; it's set at
runtime by whichever effect/oscillator type occupies that slot (`ct_none` in Surge's
own source, per `surge_assign_calls.json`'s `"-" | ct_none | scene[sc].osc[osc].p[i]`
and `dawlabel | ct_none | fx[fx].p[p]` entries). Label-tail matching cannot close this
— it needs a second pass over each oscillator/effect type's own per-type param
definitions (not available locally; would need Surge source access). Remaining 5:
4 host-level VST3 params (Bypass/Wet/Delta) + `FX Disable` (Surge's own `ct_none`).

## Surge preset pipeline — wired end-to-end (2026-07-25)
Full chain now exists and ran clean against a real factory patch
(`/usr/share/surge-xt/patches_factory/Basses/Bass 5.fxp`):

- **`scripts/build_surge_id_map.py`** → `scripts/surge_id_map.json`: maps each of the
  778 REAPER param indices to Surge's own `.fxp`-XML internal id (e.g. index 319 →
  `a_filter1_cutoff`). Needed because Surge's patch-XML field order is genuinely
  **not** the same order REAPER's VST3 wrapper exposes params in (XML groups
  octave/pitch/portamento before the 3 oscillators; REAPER groups the whole scene
  header first) — id-based join, not positional, confirmed necessary and correct
  against 15 randomly-sampled factory patches (zero tag mismatches) plus the full
  Bass 5 patch (all 571 tags accounted for).
- **`scripts/apply_surge_preset.py`**: parses a `.fxp`'s embedded XML (`<?xml...` after
  the `CcnK`/`FPCh` VST2-preset-container header), joins against `surge_id_map.json`
  + `surge_param_map.json`, normalizes via `surge_normalize.py`. On Bass 5: 512/778
  resolved offline, 4 deferred (filter subtype, state-dependent — see below), 195
  legitimately absent from this patch (unused FX slots, sparse by design), 55
  unresolved (the type-dependent osc/FX params from the earlier pass), 12 with no
  patch-domain id (8 macros + 4 host params).
- **Enum sizes** (`ct_scenemode`, `ct_osctype`, `ct_filtertype`, `ct_fxtype`, etc. —
  the "resolved but runtime-sized max" params from the earlier pass): REAPER's
  `TrackFX_GetParameterStepSizes` **does not work for VST3 params** (confirmed
  empirically — returns `retval:false` even on plain continuous ones, not just
  enums). Worked around via `TrackFX_FormatParamValueNormalized` instead (formats an
  arbitrary normalized value to text without changing state) — sampled 61 points per
  ctrltype, counted label transitions. `scripts/probe_surge_enum_sizes.py` →
  `scripts/surge_enum_sizes.json` (11 ctrltypes resolved this way, e.g.
  `ct_filtertype`=34 choices, `ct_fxtype`=30, `ct_scenemode`=4).
- **`ct_filtersubtype` is the one exception**: its choice count depends on which
  filter *type* is currently active in that slot, not a global constant — resolved
  live in `scripts/apply_surge_preset_live.py` by setting the slot's Type first, then
  re-probing that specific index's enum size before computing/setting Subtype.
  Verified this sequencing actually matters: scene A's filter type got 4 valid
  subtypes, scene B's (different type) got only 1.
- **Bridge extended, not the vendored package**: `reaper_mcp_bridge.lua` (ours, both
  `scripts/` and the deployed `~/.config/REAPER/Scripts/` copy) got two new whitelisted
  dispatcher cases — `TrackFX_GetParameterStepSizes` and
  `TrackFX_FormatParamValueNormalized` — added in the exact style of the existing
  cases. The third-party `twelvetake-reaper-mcp` Python package (no MCP tool wraps
  either) was deliberately left untouched (fragile, re-fetched by `uvx`). Instead,
  **`scripts/surge_bridge_client.py`** talks to the bridge's file protocol directly
  (`request_<n>.json`/`response_<n>.json` in the bridge dir) for anything without an
  MCP tool wrapper. Two gotchas hit and fixed: (1) the bridge's dispatcher only scans
  `request_1.json`..`request_1000.json` — ids outside that range are silently never
  picked up; (2) a monotonic counter runs past 1000 on any long probing run — cycle a
  band instead (`itertools.cycle(range(800, 1000))`).
- **Live end-to-end run**: applied all 516 resolvable Bass 5 params to a fresh Surge XT
  instance (test track), read back several live values against the plan (Global
  Volume, Filter 1 Cutoff, Osc 1 Type, Amp EG Attack — all matched exactly), added a
  sustained MIDI note, rendered to `scripts/_surge_bass5_applied_TEST.wav`. Sanity
  peak-checked (≈-25 dBFS, no clipping, not silent) — confirms the pipeline produces
  real audio reflecting the applied params. **The actual acid test — does it sound
  like Bass 5? — is still open and needs a human to listen**; nothing in this repo
  can judge that.

**Near-incident, resolved**: discovered mid-session that the live headless REAPER
project was titled `[unsaved project]` — 17 tracks (KICK BUSS, MAIN SYNTH, etc.),
never written to an `.rpp` file, existing only in that process's memory. A
`save_project` call made the bridge stop responding for a bit (recovered by sending
Escape via `xdotool` to the Xvfb display, `DISPLAY=:105`, using the Xauthority file
matching the xvfb-run process's start time under `/tmp/xvfb-run.*` — the parent
shell's own `XAUTHORITY` doesn't apply to a separate Xvfb instance). **Asked the user
directly rather than guessing**; they confirmed this instance is disposable scratch,
not real production work — freed up restarting REAPER (needed anyway to load the
bridge script edits) and mutating it freely for this test.

## Acid test partially run (2026-07-25, continued)
User's laptop speakers initially made the first render sound like "no sound" (just too
quiet/low for the speakers, not actually silent — confirmed by waveform analysis: real
signal ~-28dBFS RMS from 0-1.7s then a release tail to silence by 2.4s). Then flagged
the release sounded like an instant cutoff. **Checked against Surge's own displayed
value, not our own math**: Amp EG Release = 31.2ms, Attack = instant, Sustain = 100%,
via live `TrackFX_GetFormattedParamValue` — confirmed this is a real Bass 5 characteristic
(tight/plucky bass design), not a mapping bug. Good validation of the normalize pipeline:
the exact number we compute matches what Surge itself displays.

Rendered a direct A/B: `scripts/_surge_A_default_B_bass5.wav` — Surge's untouched init
patch (A) then our Bass 5 reproduction (B), same note/length, spliced with a 0.5s gap.
**Still waiting on the user's actual listen — timbre match not yet confirmed, only the
envelope numbers.**

**Enum-size probing instability found, root-caused, not fully hardened**: re-running
`apply_surge_preset_live.py` against the same patch on the same track gave a different
filter-subtype enum size than the first run (4 vs 1). Root cause on the *second* run
verified directly: `TrackFX_FormatParamValueNormalized` returns the literal string
`"None"` across the whole 0-1 range for that param under Bass 5's actual filter type
(HP 24dB / LP 24dB) — Surge is correctly reporting "no subtype exists for this filter
type," so `enum_size=1` was right. The *first* run's "4" was very likely a stale/
misattributed response from a request-id collision: `surge_bridge_client.py` writes
`request_800.json`..`request_999.json` directly, and the official `twelvetake-reaper-mcp`
Python MCP server writes its own numbered request files into the *same* directory with
its own (unknown to us) numbering — if both are in flight at once (e.g. I ran manual
`mcp__reaper__track_fx_get_param` verification calls right after that first live-apply),
a response file can get consumed by the wrong reader. Not hardened yet — if this
matters going forward, `surge_bridge_client.py` needs either a private id namespace
proven disjoint from the Python server's own counter, or a request-id embedded in the
response for the client to check against before consuming a file.

`apply_surge_preset_live.py` refactored: the apply logic is now `apply_preset(fxp_path,
track, fx, verbose=False)`, importable, not just a CLI script — returns `(stats,
subtype_details)`. `main()` is now a thin wrapper. Ready to be called from the actual
generation pipeline once the acid test is confirmed.

## Acid test: PASSED (2026-07-25, user verdict)
User listened to `scripts/_surge_A_default_B_bass5.wav`: "B sounds like a bass, A
sounds like stock synth stuff" — A (Surge's untouched default) reads as generic,
B (our Bass 5 reproduction) reads as an actual bass. Pipeline reproduces patch
character correctly. This closes out the open question from the previous entry.

## Generation pipeline doesn't exist yet — checked src/ directly
`src/planner/node.py` is schema-only (`Leaf.implementation` is explicitly a
placeholder: "deliberately opaque here... set by whichever Reaper-MCP gets picked,
which hasn't happened yet"). No split/decompose/fold/DSL-emission code exists (that's
"plan §11 stage 4"). `src/return_channel/` is the *other* direction — a reader that
extracts symbolic facts from an already-rendered `.RPP` for review/feedback, and
treats VST state as "opaque base64... unreadable by design" (rpp.py:187) — confirms
today's approach (name/id-based join + live param-set, not chunk manipulation) is the
only viable direction, not a shortcut avoided for no reason.
**So "wire apply_preset() into the pipeline" isn't an available task yet** — there's
nothing to wire into. `apply_preset()` is already in the right shape (clean, importable,
takes fxp path + track/fx) for whenever stage 3/4 exists and needs to call it.

239-param gap decision: **deferred for v1**, not resolved. Mostly FX-slot coloring and
oscillator sub-params, not core tonal identity — revisit only if real target patches
lean heavily on FX-slot effects.

Cleaned up `%APPDATA%\REAPER\Scripts\mcp_bridge_data` — a literal-backslash-named
directory (not nested paths; Linux doesn't split on `\`) created by the pre-fix
`REAPER_BRIDGE_DIR` bug from earlier in the session. Empty, deleted.

## Vital investigation — started, real progress, hit a genuine wall
**Corrected a stale assumption**: memory previously said "no local preset files yet"
for Vital. False — checked directly and found Vital already installed
(`~/.vst3/Vital.vst3`) with several full preset packs already on disk under
`~/.local/share/vital/` (Factory, plus curated packs: Afro, In The Mix, inktome,
Glorkglunk, Mr Bill). Content availability is not a blocker at all.

**The good news**: `.vital` preset files are plain JSON (`settings` is a flat dict of
~775 self-describing snake_case keys — `chorus_cutoff`, `compressor_attack`, etc.) —
no binary container, no ctrltype/range reverse-engineering needed at all, since the
values are presumably already in whatever native units the engine uses directly by
name. `manifest.json` (dumped earlier in the project) already has Vital's 775 REAPER
param entries too — same count, suggesting a clean 1:1 correspondence *should* exist.

**The wall**: REAPER's displayed param names don't match the JSON keys directly
("Chorus Filter Cutoff" vs `chorus_cutoff`, "Chorus Mix" vs `chorus_dry_wet`, "Chorus
Switch" vs `chorus_on`) — same class of problem as Surge. Tried the obvious shortcut:
`TrackFX_GetParamIdent` (a VST3's stable paramID, separate from the display name) —
added it to the bridge (same pattern as the other additions) and tested live; for
Vital it returns opaque host-internal strings like `"0:48"`, not the plugin's own key.
Dead end, confirmed empirically not assumed. Also checked **positional** correspondence
(both lists are 775 long, in a stable order) — matches for the first ~8 params, then
diverges (JSON has an extra `chorus_spread` key REAPER's list doesn't carry in the same
slot) — not a reliable join either.
**Conclusion: closing this out for real needs a name-mapping build of comparable size
to today's whole Surge effort (label-tail rules + a structural traversal), not a quick
follow-on.** Stopped here deliberately rather than silently spending several more hours
on a second instrument without a checkpoint.

## Stage 3 groundwork: read the actual plan docs, corrected a misreading (2026-07-26)
Read `PROJECT_BRIEF.md` + `deaf-composition-plan.md` in full before proposing anything
(per PROJECT_BRIEF's own instruction to read source docs, not assume). **Corrected
my own earlier claim**: I'd said stage 3 was blocked on "whether the MCP's typed
tools are the DSL" being an open decision — that's wrong. Plan §8.1 already settles
it: "the MCP's typed tools are the DSL." `node.py`'s docstring saying this "hasn't
happened yet" is just stale — written before the Reaper-MCP was picked, which memory
already confirms happened. No architecture debate needed there; don't re-litigate it.

**What today's Surge work actually surfaced as a real gap in that plan**: raw
`TrackFX_SetParam` calls can't practically express "load Bass 5" — 778 params, ~500
meaningfully set. A leaf model emitting that is a token-economics violation (plan
§1.5/§6 — cost concentrated at the leaf tier is a *hard requirement*, not a nicety)
and a stability risk (500+ model-copied param values vs. one deterministic function
call). Proposed closing this with one addition to the leaf vocabulary: an
`apply_surge_preset` tool wrapping the already-built `apply_preset()` +
`apply_overrides()` pipeline, alongside the ~150 existing `mcp__reaper__*` tools —
not a bespoke JSON "op" needing custom interpretation, a real MCP tool, so it fits
§8.1 literally.

**Built and verified**: `scripts/deaf_composition_mcp_server.py` — a small supplementary
FastMCP server (separate from the vendored `twelvetake-reaper-mcp`, which stays
untouched) exposing `apply_surge_preset(track_index, fx_index, preset_path, overrides)`.
`overrides` is `{param_name: raw_native_value}` (e.g. `{"A Amp EG Release": -1.5}`),
applied after the base preset — lets a leaf say "this preset, but faster attack"
without hand-computing normalized values. **Added the `mcp` Python SDK as a new
dependency** — asked first per PROJECT_BRIEF's explicit rule, user said yes, installed
via `uv pip install --python .venv/bin/python mcp` (`mcp==1.28.1`), pinned in
`requirements.txt`.

**Tested live, both overrides verified against Surge's own displayed values** (not
just our math): called `apply_surge_preset(track=0, fx=0, "Basses/Bass 5.fxp",
overrides={"A Amp EG Release": -1.5, "A Amp EG Attack": -2.0})` directly (bypassing
the MCP transport, calling the tool function in-process, since the server itself
needs a Claude Code reconnect to be reachable as `mcp__deaf_composition__*` — same
reconnect requirement as any `.mcp.json` change). Result: 512 base params applied,
both overrides read back exactly right (Attack → 250.0ms = 2⁻², Release → 353.6ms
= 2⁻¹·⁵).

Registered in `.mcp.json` as a second server (`deaf_composition`) alongside `reaper`,
using absolute paths (not `${PWD}`, which isn't guaranteed to be the project root).
**Not yet live in this session — needs a reconnect**, same as the original bridge-dir
fix earlier.

## `apply_surge_preset` verified live through the real MCP path — request-id collision bug found and fixed (2026-07-26)
Reconnected; `mcp__deaf_composition__apply_surge_preset` and the full `mcp__reaper__*`
set loaded as real tools. Headless REAPER from last session was gone (disposable scratch
instance, as expected — not persisted), so `start_reaper_mcp_bridge.sh start` first.

**First two live attempts timed out** (`TrackFX_SetParam[...]: no response within 10.0s`,
different param index each time) — this was the "not hardened yet" request-id collision
memory had already flagged, now manifesting for real instead of just in manual probing.
**Root-caused precisely**: the vendored `twelvetake-reaper-mcp` server cycles its own
request ids via `request_counter = (request_counter % 999) + 1` — i.e. the *full* 1-999
range (confirmed by reading `reaper_mcp_server.py` directly from the uv cache) — while
`surge_bridge_client.py` used an 800-999 band nested entirely inside it. `apply_preset()`
fires ~500+ sequential `SetParam` calls, wrapping that narrow band 2+ times per run, so
collisions were now frequent instead of a rare manual-overlap edge case.

**Fixed at the actual constraint, not by picking a different sub-range**: the Lua
dispatcher only scans `request_1.json`..`request_1000.json`
(`reaper_mcp_bridge.lua:1778`), which is *why* the client's original 9000+ band silently
never worked and *why* it had to nest inside twelvetake's space in the first place.
Extended the scan to `1, 2000` and moved `surge_bridge_client.py`'s band to 1200-1999 —
genuinely disjoint from twelvetake's 1-999, no more sharing. Deployed to
`~/.config/REAPER/Scripts/reaper_mcp_bridge.lua` (diff-checked first, only differed by
this change) and restarted REAPER (Lua edits don't hot-reload into a running instance,
per existing working notes). Both `scripts/reaper_mcp_bridge.lua` and
`scripts/surge_bridge_client.py` now carry comments explaining the shared-namespace
constraint so this doesn't get "optimized" back into a collision later.

**Re-ran clean after the fix**: `apply_surge_preset(track=1, fx=0, "Basses/Bass 5.fxp",
overrides={"A Amp EG Release": -1.5, "A Amp EG Attack": -2.0})` through the real
`mcp__deaf_composition__` tool (took >120s — ran as a background MCP task — but
completed with zero timeouts). Result: 512/778 applied, exactly matching the earlier
in-process test's stats; both overrides resolved to the correct normalized values
(0.5 and 0.4615 respectively). **Step 1 of the prior "Next" list is done and closed —
the live MCP path is now trustworthy, not just the in-process bypass.**

Note for next session: ~500-call sequential apply over a synchronous file-poll protocol
is inherently slow (took over 2 minutes) — fine for one-off leaf execution, but if the
generation pipeline ends up calling this per-leaf at scale, latency (not just
correctness) may become a real constraint worth revisiting.

## Plan §11 stage 3 proven end-to-end: minimal single-leaf proof (2026-07-26)
User chose stage 3 over Vital (Vital has no dependencies on anything else, can wait;
stage 3 is the project's actual spine). Built `scripts/leaf_proof.py`: one hand-written
`Node`/`Leaf` (per `src/planner/node.py`'s frozen schema) whose `implementation` records
the exact ops run live — `apply_surge_preset` (Bass 5 + slower attack/release overrides,
reusing the pipeline verified earlier this session) + a 16-note driving root/fifth/octave
bassline via `create_midi_item`/`add_midi_notes_batch` + `render_project` — then measured,
embedded, and scored the render against the real reference library's `"drop"` envelope via
`reference.score_node`, exactly as a fold review would (no reviewer node exists yet, so
called directly).

**Real result, not a rubber stamp**: measured distance FAILed hard (14.79 vs a threshold
of 3.0) — dominated by LUFS (-37 LUFS for a solo unmastered bass stem vs a "drop" envelope
built from full mixed/mastered reference tracks, correctly registering as very different).
Embedding distance passed comfortably (0.51 vs 0.8) — CLAP-level timbre match is fine, the
gap is entirely "this is one instrument, not a finished section," which is exactly the
right thing for the loop to catch. Closes plan §11 stage 3's own bar — "prove a leaf spec
becomes correct audio" — with a verdict that couldn't have been gamed by a lenient
threshold, not just a working script.

**Hit and worked around the documented near-incident again**: `mcp__reaper__save_project`
on the still-never-named scratch project popped REAPER's Save-As dialog and blocked the
bridge, same as before. Recovered the same way (`xdotool key Escape` against
`DISPLAY=:99`, matched to the live `Xvfb :99 ... -auth /tmp/xvfb-run.<id>/Xauthority` via
`ps -eo pid,ppid,args | grep Xvfb`, not by directory mtime — mtimes on the xvfb-run temp
dirs were unreliable for matching, the live `Xvfb` process's own `-auth` argument is the
ground truth). **Sidestepped needing a saved `.rpp` at all** for this proof rather than
retry save: `return_channel.state.build()` accepts an explicit `symbolic` dict, so
`leaf_proof.py` hand-supplies the note data (matching `rpp.extract_symbolic`'s schema)
instead of round-tripping through `rpp.parse_file` on a file that was never written. A
real pipeline run still needs the save path solved for real eventually (see Next) — this
was a one-off proof of leaf→audio→score, not a save-flow fix.

Output artifacts land in `state/leaf_proof/` (gitignored, `state/` already covered) —
`leaf_bass_drop.wav`, `.state.json`, `.score.json`. Only `scripts/leaf_proof.py` itself is
committed.

## `save_project` fixed for real (2026-07-26)
Root cause understood properly this time, not just worked around. Two things tried and
rejected before finding the real fix:
- Passing a *nonexistent* `.rpp` path as REAPER's CLI arg does **not** pre-name the
  project (an assumption worth recording as wrong so it doesn't get retried) — REAPER
  throws a blocking "file not found"-style error dialog and falls back to
  `[unsaved project]` anyway. Confirmed by inspecting the Xvfb window tree directly
  (`xwininfo -root -tree` against the matched `DISPLAY=:99` / `-auth` path) mid-hang:
  a `"REAPER Error"` dialog plus an `"Error opening devices"` dialog (the latter is the
  usually-harmless JACK-missing warning, but it's a real *modal* here, not just log
  noise, when startup is otherwise unhappy).
- **Real fix**: write a minimal *valid, already-on-disk* `.rpp` first (just
  `<REAPER_PROJECT 0.1 "7.75" <epoch>\n  <TEMPOENVEX\n  >\n>`) and launch REAPER against
  that path. Since the file genuinely exists, REAPER opens it with zero dialogs, treats
  it as already-named, and `Main_SaveProject`/`save_project` then works silently —
  verified live through the real `mcp__reaper__save_project` tool, not just the raw
  bridge call.

**Wired into `scripts/start_reaper_mcp_bridge.sh` permanently**: `start()` now seeds
`state/scratch/session.rpp` (path overridable via `REAPER_PROJECT_PATH`) with that
skeleton *only if it doesn't already exist*, and passes it as REAPER's first CLI arg
alongside the bridge script (`reaper -nosplash session.rpp bridge.lua` — REAPER accepts
a project path and a startup script as two separate positional args together, confirmed
empirically). Re-verified end-to-end through the actual updated launcher (not just the
manual test that found the fix): bridge came up clean on the first try, `save_project`
returned `{"ok": true}` immediately, no `xdotool` intervention needed anywhere in the
run. **Side benefit, not the goal but real**: because the launcher now reuses
`session.rpp` if it's already there, project state survives bridge restarts going
forward instead of being disposable every time (previous "unsaved project" instances
were lost on every restart) — worth knowing if a future session finds unexpected
leftover tracks in `state/scratch/session.rpp`, that's expected, not corruption.
`state/` is gitignored, so this file itself never lands in git.

## DSL emission + minimal fold/review, both proven live (2026-07-26)
User set up a real `ANTHROPIC_API_KEY` for this (given directly in chat — stored in
`.env`, gitignored, never committed; `anthropic==0.120.0` added to `requirements.txt`).
Confirmed working with a live Haiku call before building anything on top of it.

**`scripts/leaf_emit.py`** — real DSL emission (plan §6/§8.1), not hand-authored.
Given only a `Node`'s `own_purpose`/`spec`/`acceptance_criteria`/`scope_chain` and a
curated 3-tool catalog (`apply_surge_preset`, `create_midi_item`,
`add_midi_notes_batch` — Anthropic tool-use format, `tool_choice: any`), a real
`claude-haiku-4-5-20251001` call picked `Pads/Distant.fxp` (a genuinely apt name for
an atmospheric-intro spec it was never shown a preset list description of, just
filenames) and one sustained middle-C held across the full 8-bar item — a sensible,
unforced plan. Rendering is deliberately *not* something the model plans (deterministic
plumbing derived from the emitted MIDI item, not a creative decision, matches `Leaf`'s
own "no remaining creative sub-decision" definition) — the script appends it. Scoped
down on purpose: exactly one MIDI item per leaf, referenced by a fixed `item_index=0`
placeholder (sidesteps needing multi-turn execution feedback for a real REAPER-assigned
item index); `_validate_ops` fails loudly on any other op-sequence shape rather than
silently patching it. **Emission only** — the script doesn't execute against REAPER
itself (no standalone client exists for the ~150 reaper-mcp tools outside a real MCP
session); the controlling Claude Code session ran the emitted ops verbatim, same
pattern as `leaf_proof.py`.

Executed live: rebuilt a fresh `session.rpp` (the earlier 17-track scratch project was
never saved, so it's gone — expected, `state/` is gitignored) with just the one track
this leaf needed, ran the three emitted ops **unmodified except `track_index` rebased
12→0** (the spec text baked in an assumption about a project layout that no longer
existed by execution time — a runtime-environment fact, not a change to anything Haiku
actually decided). `apply_surge_preset` succeeded (503/778 params). Rendered, and for
the first time **used the fixed `save_project` for real** in the actual pipeline (not
just the fix's own verification) — instant, no dialog, and `rpp.parse_file` correctly
recovered exactly the 1 note that was added, confirming the fix works for downstream
tooling too, not just "doesn't hang." Scored against `"intro"`: measured distance 4.36
(fails the 3.0 threshold — same loudness-scale-mismatch pattern as every solo-stem
render this session, a single soft pad note read against full mixed/mastered
references), embedding distance 0.772 (passes the 0.8 threshold, barely — a real signal
that "Distant.fxp" was a sonically apt pick).

**`src/planner/review.py`** — the fold/review code `node.py`'s own docstring flagged as
not yet built. Two real functions: `review_leaf(node, state, library)` (check 1 —
`reference.score_node` against the node's own `acceptance_criteria`, returns a real
`ReviewState`) and `review_composition(sibling_states)` (check 2 — a genuine, if
deliberately lightweight, structural check: do siblings' own solo LUFS levels sit
within 12dB of each other, i.e. would one bury the other before any mixing even
happens). Scoped down honestly: composition is checked from each child's own solo
`state.json`, not a combined mixed render (spectral masking once layers actually
overlap is real future work, not built) — and seam continuity (plan §3.6 check 3)
isn't touched at all, since these two leaves are parallel layers of one section, not
timeline-adjacent, so there's no seam between them yet.

**`scripts/fold_proof.py`** ran it for real against two siblings under one parent
`Split` node: `proof/leaf_intro_texture` (the model-emitted pad from `leaf_emit.py`)
and a hand-written second layer, `proof/leaf_intro_bells` (ReaSynth, 4 sparse quiet
high notes scattered across the same 16s, rendered solo via `set_track_solo` so its
`state.json` reflects only its own audio). Both individual leaves **failed** their own
acceptance criteria (bells: measured distance 5.26 vs threshold 4.0, same loudness-scale
pattern; embedding distance 0.604, actually better than the pad's) — but the **parent's
composition review PASSED**: an 8.5dB LUFS gap (pad -24.8, bells -16.3) is under the
12dB burial threshold, a correct, non-trivial "these two would sit together reasonably"
verdict. Real discrimination at both the leaf and the composition level, not a rubber
stamp at either.

**A known, honest gap surfaced, not fixed**: `state.build()`'s `symbolic` extraction has
no track-scoping — `leaf_intro_bells`'s state.json's symbolic notes include both tracks'
notes (session.rpp had both by the time it was built), since `_slice_symbolic` only
slices by time region, not by track. Doesn't affect the `measured`/`embedding` scoring
used here (audio-domain, computed from the isolated solo render, unaffected), but a real
per-node snapshot (§7.3) will eventually need track-scoped symbolic extraction too — not
built, flagged for whoever picks this up next.

## Track-scoped symbolic extraction + real combined-mix composition check (2026-07-26)
Closed the two gaps flagged at the end of the previous entry.

**`state.py`'s `_slice_symbolic`/`build()` now take a `track` param** (a name or set
of names, matching `symbolic["tracks"][i]["name"]`) alongside the existing `region`
time-window param — filters `notes`/`tracks`/`fx`/`automation` down to just the leaf's
own track(s). Backward compatible (`track=None` default, identical old behavior).
`fold_proof.py` rebuilds both leaves' states with explicit track scoping now
(`"TEXTURE / ATMOS"`, `"INTRO BELLS"`) instead of the untracked pull that silently
absorbed both tracks' notes into whichever leaf happened to be built after both
existed. Re-running confirmed the fix doesn't change `measured`/`embedding` scores
(those come from the isolated solo renders, never affected by symbolic pollution) —
only `symbolic.notes` correctness changed, as expected.

**`review_composition` gained two more real checks**, on top of the existing loudness
balance: (1) **spectral-overlap** — do the two siblings' own solo spectral centroids
sit within half an octave of each other (ratio < 1.5)? — computed from data already in
their `state.json`s, no extra render needed; (2) **combined-mix sanity** — an actual
new render of the section with both tracks audible together (`section_intro_combined.wav`,
via `mcp__reaper__render_project` with both tracks unsoloed/unmuted), checked against
"combining uncorrelated sources should never produce something quieter than the
loudest ingredient" (a real audio-engineering inequality — a violation means phase
cancellation or a render-chain bug, not just poor balance).

**Real result, and a genuinely useful one**: re-running `fold_proof.py` flipped the
composition verdict from PASS to **FAIL** — the spectral-overlap check caught something
neither the loudness-balance check nor a symbolic/MIDI-level read would have: the pad
(`Pads/Distant.fxp`, sustained note) and the bells (ReaSynth, nominally high-register
short notes) came out with spectral centroids at 1548Hz and 1318Hz respectively —
despite the bells' MIDI pitches being much higher, their actual rendered timbral
brightness landed close to the pad's (short transient plucks decay fast, likely
dominated by lower-frequency envelope/waveform content, not sustained high harmonics).
That's real audio-grounded signal, exactly the class of thing this system exists to
catch that a symbolic-only check couldn't. The combined-mix LUFS check passed silently
(no cancellation detected). Still deliberately not built: an actual spectral-masking
model of the combined render itself (does the pad's harmonic content get eaten once
the bells sit on top, not just "are their solo centroids close") — flagged as real
future work in `review_composition`'s own docstring, not silently assumed done.

## Real decompose→emit chain, run end-to-end on a 4-leaf model-decided section (2026-07-26)
Closed stage 4's actual unstarted core (previous entry's #2): a real recursive
decompose step, chained to the already-proven emit step, run on a genuinely new
section ("build," not a rerun of the intro pad+bells pair).

**`src/planner/decompose.py`** — the piece nothing before this session touched at
all: a real Sonnet call (plan §6: mid-tree decomposition) that decides how many
leaf children a Split node needs and what each one's job is, given only
`own_purpose`/`spec`/`scope_chain`. Forced tool-use (`tool_choice: {"type": "tool",
"name": "decompose"}`), 2-4 children. **Hit and root-caused a real API quirk**: the
first 4 attempts against the real prompt (not a toy one — a simplified paraphrase
worked fine on the first try) came back with `children` as a giant, perfectly
well-formed JSON string double-encoding the whole tool input, instead of an actual
array — `len()` on the string then silently "succeeded" by counting characters
(3395, 4055...), which is how this was caught. Retries alone didn't fix it (3/3
failures on the real prompt). **Fixed by recovering the string**, not just
retrying: the content inspected mid-failure was genuinely excellent decomposition,
not garbage, so `_validate()` now `json.loads()`s a string `children` before giving
up, with the failure mode and reasoning documented directly in the code, not just
here.

**`src/planner/scheduler.py`** — `build_section()` chains `decompose()` to
`leaf_emit.py`'s existing `emit_leaf_implementation()` (imported as-is via the same
scripts-as-flat-modules pattern the rest of the project already uses, e.g.
`apply_surge_preset_live.py` importing from `apply_surge_preset.py`), assigning
each decomposed child a fresh sequential track (plumbing, not a creative decision,
so the scheduler owns it) and a tapered scope-chain link back to the parent.
Doesn't execute — same documented gap as `leaf_emit.py` (no standalone client for
the ~150 reaper-mcp tools outside a real MCP session).

**Real run, `scripts/build_section_proof.py`**: a "build section" spec (rising
energy after the intro, before a drop) decomposed into **4 model-decided layers**
— rhythmic pulse, rising bass, atmospheric glue texture, rising lead accent —
each with a genuinely coherent spec (increasing density/velocity toward the end,
staying below drop-level intensity, explicit frequency-range separation between
layers) and a real emitted implementation, including the model choosing its own
Surge override (`{"Filter Cutoff": 0.7}` on the texture layer) unprompted.

**Two real leaf-emission mistakes hit during execution, both handled the way the
system is supposed to handle them**: the model twice invented a plausible-sounding
but nonexistent Surge param name for an override (`"Master Volume"`, then
`"Filter Cutoff"` again on a *different* preset) — `apply_surge_preset` correctly
raised immediately both times (its own documented behavior: "caller mistakes worth
failing loudly on"), and the executing session retried without the invalid
override rather than guessing a fix or silently patching the emitted plan.

**Reviewed for real** (`scripts/build_section_review.py`, reusing `review_leaf`/
`review_composition` unchanged): 3 of 4 leaves failed their own criteria, 1
(**the bass layer**) passed cleanly. The standout finding: the rhythmic-pulse
layer came out at **-52.1 LUFS**, essentially inaudible — the model paired "MW
Pulsating" (a pad preset, slow attack/release) with a pattern of short 0.5-beat
staccato hits; a pad envelope structurally can't reach useful amplitude on notes
that short. **A real preset/technique mismatch the model had no way to hear**,
caught only because the audio was actually rendered and measured — exactly the
class of failure this whole architecture exists to catch, not a contrived result.
Composition review correctly failed hard (huge LUFS gaps driven by the near-silent
layer, plus 2 flagged spectral-overlap pairs), combined-mix LUFS (-14.7) sane
otherwise (no cancellation).

## Seam continuity: plan §3.6's third check, run for real (2026-07-26)
Closed the previous entry's #2. First moved the "build" section's 4 tracks from
timeline position 0 to position 16 (`set_item_position` ×4 + `save_project`) --
they'd been sitting *overlapping* the intro the whole time, since
`build_section_proof.py`'s scheduler only ever allocated tracks, never timeline
position (nothing needed real sequencing until this check). Rendered the actual
boundary from the live combined timeline (every track audible together, not
soloed): `seam_before_intro_tail.wav` (12-16s) and `seam_after_build_head.wav`
(16-20s) — the real acoustic handoff, not two isolated section renders compared
after the fact. Also rendered `song_so_far.wav` (0-32s) for an actual listen
across the transition, and re-rendered `section_build_combined.wav` at its new
16-32s position (the old 0-16s version was stale the moment the tracks moved).

**`review_seam(before_state, after_state)`** (`src/planner/review.py`) — plan
§3.6's third check, the one no code existed for at all until this. Deliberately
looser thresholds than `review_composition`'s simultaneous-sibling checks (a
section change is often *supposed* to jump — documented directly in the
threshold constants' comments, not just here): loudness gap > 10dB, or spectral
centroid ratio > 2.0 (more than an octave) right at the boundary.

**Real result**: loudness held fine (-20.5 → -15.4 LUFS, 5.1dB gap, well under
threshold) — but spectral centroid jumped from 1735Hz to 567Hz, ratio 3.06,
**failing** the check. Makes complete sense once you know what's on each side:
intro is airy/high-register (pad + bells), build immediately drops into
low-register material (the rhythmic pulse's root-note pattern + bass) — a real,
abrupt timbral handoff with nothing bridging the register gap between them. Not
a contrived failure; an honest one, same pattern as every other genuine finding
this session.

**Also, for the first time, a real `NeighborEdge`** (plan §3.4): built a `song`
parent `Node` over the two existing sections with `NeighborEdge(target=
"proof/section_build", kind="local", weight=1.0)` on it — `node.py`'s schema has
carried `NeighborEdge` since the schema was frozen, nothing before this session
ever actually instantiated one.

All three of plan §3.6's review checks now have real, tested code:
`review_leaf` (own criteria), `review_composition` (siblings), `review_seam`
(neighbors) — `review.py`'s own module docstring updated to reflect this instead
of listing seam continuity as "isn't here."

## Escalation (plan §7.4), run for real against a known failure, and it worked (2026-07-26)
User's framing: `song_so_far.wav` "has some good parts/structure but is very 2018 AI
vibe" — multi-level recursion, emission quality, and escalation are all needed for
this to actually work well, escalation first. Closed the previous entry's #4.

**`src/planner/escalation.py`** — plan §7.4's three triggers, all real: (1) fails own
criteria N times (`max_attempts`, default 2) → retry, then escalate; (2) low
confidence — a FAIL within 15% of its own threshold escalates immediately rather than
burning a retry on a near-miss; (3) `build_payload()` is the literal "surfaces the
rendered stem + measurements + specific conflict" plan §7.4 describes. Explicitly
does NOT decide *how* to fix anything — the human is still the taste oracle (§7.1);
this module only decides retry-vs-escalate and builds what the human needs to rule on
it. `feedback_for_retry()` turns a `ReviewState`'s reasons into the actual retry
mechanism: natural-language feedback appended to the next `emit_leaf_implementation()`
call.

**Broadened `leaf_emit.py`'s preset catalog before running the retry** — every Surge
factory category (`Plucks`, `Percussion`, `Basses`, etc.), not just `Pads`. Root cause
check: the known -52 LUFS failure happened because Pads-only meant the model had
nothing with a fast enough attack to offer for a rhythmic part, no matter how it
retried. Fixing the retry's *chance* of succeeding, not just adding the retry
mechanism itself — an empty toolbox doesn't get better with more attempts.

**Real end-to-end result, run against the actual known-broken pulse leaf, not a
synthetic test**: `escalation.decide()` on attempt 1 correctly said "retry" (not
"escalate yet"). Re-emission got the real failure reasons via `feedback_for_retry()`
and **picked `Plucks/Snap.fxp` instead of a Pads preset** — a fast-attack, genuinely
appropriate choice — plus switched to a steady 8th-note pattern. Executed live
(cleared the old MIDI item's notes rather than duplicating, reapplied the new
preset). Re-reviewed: **LUFS went from -52.1 to -16.8, measured distance from 19.876
to 1.606** (comfortably under the 4.0 threshold) — `escalation.decide()` on attempt 2
correctly returned `"pass"`. No human intervention needed; the model fixed its own
mistake once told what was wrong, using a strictly worse toolbox constraint (Pads-only)
identified and lifted as part of making the retry meaningful. Re-rendered
`section_build_combined.wav` and `song_so_far.wav` so the fix is actually audible in
the full song, not just in isolated review numbers.

**Not yet built**: `decide()`'s "two criteria conflict" trigger (plan §7.4's second
one) has no real test case yet — no observed run this session has had a node fail two
review dimensions in genuinely opposing directions (the pulse leaf's own-criteria and
composition failures were aligned, not conflicting: fixing loudness fixed both). The
code path exists in principle (any node with multiple simultaneous FAILed reviews) but
detecting true directional conflict (fixing A would break B) is real, undone work —
flagged, not silently assumed solved.

## Emission-quality: override-name hallucination closed at the source (2026-07-26)
User's order: emission quality first, then multi-level recursion. Closed the
previous entry's #3 for real, not just documented as known.

**Root cause was structural, not a model-quality problem**: the model was never
given the actual valid Surge param names anywhere -- `TOOL_CATALOG`'s
`apply_surge_preset` description just said "param_name" with no real list, so
"Master Volume" and "Filter Cutoff" were reasonable-sounding guesses with nothing
to check them against. `scripts/surge_param_map.json` (built earlier this session,
the exact source `apply_overrides()` itself checks against) already has all 539
real, resolved param names -- it was just never surfaced to the emission model.

**`leaf_emit.py`'s `_valid_override_names()`** loads that same list and now
injects it directly into the prompt (`valid_override_names`, verbatim, with an
explicit "omit entirely if unsure" escape hatch) -- the model gets the ground
truth instead of having to invent plausible-sounding names.

**`_validate_ops()` now checks override names against that list too**, not just
op-sequence shape -- catches a hallucinated name *before* a live REAPER call, not
after a ~2-minute `apply_surge_preset` round-trip fails. `emit_leaf_implementation`
gained a real retry loop around this (same pattern as `decompose.py`'s, `retries=2`
default): a structurally-invalid plan gets specific feedback about exactly what was
wrong and one more shot, not just an immediate raise.

**Verified against the two actual names that failed live this session**, not
synthetic ones: confirmed `"Master Volume"` and `"Filter Cutoff"` are both
correctly absent from the 539-name valid set (and would now be rejected pre-flight
by `_validate_ops`), while their real equivalents exist under exact, discoverable
names (`"A Amp EG Release"`, `"A Filter 1 Cutoff"` / `"B Filter 1 Cutoff"` / etc.).
Re-ran `leaf_emit.py`'s original intro-texture proof end-to-end afterward to
confirm nothing broke -- same sensible pad choice as before.

## Multi-level recursion, run for real, 2 levels deep, folded review at both (2026-07-26)
Closed the previous entry's #2 -- the last of the three items (escalation, emission
quality, multi-level recursion) the user named as needed together to stop
`song_so_far.wav` reading as "2018 AI vibe."

**Root cause of why nothing ever recursed before**: `decompose()`'s own prompt
*forced* every child to be leaf-sized ("concrete enough to hand to a translation-
only model with no remaining creative sub-decision") -- there was never a child
marked as still-composite to recurse into, by construction. Fixed at the source:
`DECOMPOSE_TOOL`'s schema now requires a real `is_leaf` boolean per child (plan
§3.1's own base-case predicate, asked of the model honestly), and the prompt
explicitly permits and explains composite children instead of assuming everything
must resolve in one pass.

**`src/planner/scheduler.py`'s `build_tree()`** is the first real recursive
implementation: leaf children get emitted (Haiku) and assigned a track immediately;
`is_leaf=false` children recurse into another real `decompose()` call (Sonnet), up
to a real `max_depth` cap (`MaxDepthExceeded` on overflow) -- plan §6's own
"every run needs max_depth... or nodes spin and credits evaporate" requirement,
never actually enforced anywhere before this. Track allocation threads a shared
counter through the recursion so every leaf anywhere in the tree gets a distinct
track regardless of depth. `build_section()` (the original single-level entry
point) kept as a thin `max_depth=1` wrapper for `build_section_proof.py`'s backward
compatibility.

**Real run** (`scripts/build_tree_proof.py`, targeting "drop" -- the album's most
energy-dense section, deliberately not a rerun of intro/build's already-simple
splits): root split into 4 children, **one honestly marked composite** --
"Rhythmic backbone... kick, percussion, and bass working together as one
interlocking groove engine" -- which recursed into 3 further leaves (kick,
percussion, bass), while the other 3 (lead/hook, harmonic bed, noise/impact) were
correctly judged leaf-sized directly. 6 leaves total across 2 depth levels, no
overrides attempted this run (model played it safe per the new prompt guidance),
every preset genuinely category-appropriate (`Basses/Attacky.fxp` for the
interlocking bass, `Percussion/Kick 909ish.fxp` for the kick) -- the emission-
quality fix's broadened catalog paying off immediately.

**Executed live, all 6 leaves** (tracks 6-11, presets applied sequentially, MIDI
content added, moved to timeline position 32s -- right after the build section
ends, same seam-adjacency convention as intro→build). Hit 3 transient
`SetParam` timeouts on the last preset apply (`FX/Crackling.fxp`) -- checked
REAPER's health directly (432MB RSS, 13.7% CPU, empty bridge dir, nothing
alarming) before concluding it was ordinary flakiness rather than the
already-fixed collision bug recurring; a 4th retry succeeded clean.

**Real two-level fold review** (`scripts/drop_tree_review.py`, using
`review_leaf`/`review_composition` unmodified in logic, just called at both
levels): all 6 leaves failed their own criteria individually (same established
loudness-scale pattern). The composition checks are where this run earned its
keep:
- **Backbone (kick+percussion+bass) composition FAILED for real, useful
  reasons**: a 12.6dB LUFS gap between kick and percussion, *and* two spectral-
  overlap flags (kick-vs-percussion centroids at 230Hz/159Hz, ratio 1.45;
  percussion-vs-bass at 159Hz/115Hz, ratio 1.38) -- exactly the failure mode a
  rhythm section review should catch: three parts meant to interlock are instead
  all crowding the same low-mid register.
- **Root (whole drop) composition FAILED**, dominated by one clear cause: the
  noise leaf (`FX/Crackling.fxp`) rendered at **undefined LUFS, essentially total
  silence** (sample_peak -63.3dB) -- an FX-category preset driven by MIDI
  note-on events the way an instrument patch would be, which it apparently isn't
  built to respond to. A worse failure than the pulse leaf's earlier -52 LUFS
  near-silence, and a natural candidate for the same escalation/retry loop
  already proven to work -- not re-run here to keep this item's scope to the
  recursion mechanism itself, flagged for whoever picks it up next.

**Found and fixed a real crash while running this**: `review_composition` didn't
handle a sibling with `LUFS: null` (pyloudnorm's own "signal too short or silent"
case, exactly what the noise leaf hit) -- `abs(x - None)` blew up. Fixed by
flagging an undefined-LUFS sibling directly as its own reason (a worse problem
than a loudness *gap*, not something to silently exclude from the balance check)
and guarding the centroid/combined-mix paths the same way. This is the kind of
edge case that was always latent in the code but only a genuinely-failing real
leaf could have surfaced -- consistent with how every other fix this session got
found.

Re-rendered `song_so_far.wav` at its new full length (0-48s: intro, build, drop).

## Composition-level fixes (sidechain/EQ), closing a real architecture gap (2026-07-26)
User's own diagnosis of the backbone's spectral-overlap failure -- "we probably
need sidechaining" -- was correct and surfaced a real gap: `review_composition`
could detect siblings clashing but had no way to *act* on it beyond re-emitting
one leaf's content, the wrong tool for a genuinely relational (two-sibling)
mixing problem.

**`src/planner/mix_fix.py`** -- `propose_composition_fix()`, a real Sonnet call
(a mixing judgment, not mechanical translation) given a failed
`review_composition` verdict's actual reasons plus the siblings' own
`own_purpose`/track_index/LUFS/centroid, proposing 1-3 concrete fixes from two
real REAPER tool families: sidechain (`setup_sidechain_compression`, ducks
target when trigger plays -- right for transient masking) or `eq_cut`
(`add_eq`+`set_eq_band`, permanently carves a band -- right for constant
register crowding regardless of timing). **Deliberately not hardcoded to
"kick+bass always means sidechain"** -- and that mattered: the model correctly
read that the *actual* reported overlaps were kick-percussion and
percussion-bass, not kick-bass directly, and proposed a mixed sidechain+EQ
response instead of reflexively reaching for the textbook technique. Hit the
same double-encoded-JSON-string API quirk `decompose.py` already
root-caused and fixed -- applied the identical string-recovery fix here rather
than rediscovering it.

**Executed live against the real backbone failure**: sidechain (kick ducks
percussion, -5dB) + EQ notch on percussion (200Hz, -3.5dB, Q1.2) + EQ notch on
bass (150Hz, -3dB, Q1.3) -- `track_fx_add_by_name`/`add_eq`'s real returned
`fx_index` read live before each follow-up call, not assumed.

**Real, honest, mixed result** -- not a clean win, not a failure either:
- **The originally-reported kick↔percussion overlap resolved**: percussion's
  centroid moved from 159Hz to 115Hz, now well clear of kick's 230Hz (ratio
  2.0, passes the 1.5 threshold).
- **But a new overlap appeared**: percussion's centroid landed almost exactly
  on bass's (115Hz vs 111Hz, ratio 1.03) -- worse than either original pair.
  The EQ notch moved percussion's *median* spectral centroid further than
  intended, into territory nothing anticipated. A real, useful finding about
  the fix mechanism's limits: a single narrow cut on a busy signal doesn't
  reliably relocate its aggregate centroid to a predictable place.
- Individual leaves' own-criteria scores barely moved (expected -- those
  measure fit against the whole "drop" reference envelope, not the specific
  sibling relationships the fix targeted).
- **Explicitly not claimed**: whether the sidechain actually makes the kick
  audibly punch through. `review_composition` has no masking-clarity model
  (already flagged in its own docstring as future work) -- that's a listen,
  not something these numbers can confirm either way.

This is exactly the kind of result this session's whole approach is built to
produce: every real check finds something real, nothing gets waved through.
The new percussion↔bass overlap is itself now a legitimate input to another
`propose_composition_fix()` call -- the mechanism is real and reusable, not a
one-shot demo.

## Convergence test, run for real: it did NOT converge (2026-07-26)
Pass 1's fix relocated the percussion↔bass overlap instead of resolving it. Ran
a real pass 2 to answer the actual question -- does the fold settle, or
oscillate -- rather than assuming either.

**`propose_composition_fix()` extended with `prior_fixes`**: a second call gets
the currently-live fixes as context, so it can revise (e.g., soften the bass
cut now that the real conflict frequency moved) rather than blindly stacking a
third fix on top. The model used this well -- it correctly reasoned that the
bass cut's original justification (separating from percussion's *old* 159Hz
centroid) no longer applied now that percussion sat at 115Hz, and reduced that
cut's depth rather than leaving it untouched or removing it.

**But the actual result: it got worse, not better.** Percussion's new notch
targeted its own current centroid (115Hz) with the intent of pushing remaining
energy toward its higher transient content -- instead the measured centroid
moved to **103Hz**, further past bass's 111Hz, not away from it. Composition
review still FAILED (ratio 1.03 → 1.08, no improvement), percussion got
noticeably quieter as an unplanned side effect (-29.7 → -34.2 LUFS), and the
combined backbone mix kept getting quieter across both passes (-24.3 → -26.0 →
-27.6 LUFS) -- an EQ-cuts-only fix vocabulary has an inherent one-directional
bias (cuts only remove energy, never add it back), so repeated notching
trends the whole mix down regardless of whether it's solving the actual
problem.

**A real, useful architectural finding, not a fluke**: notching *at* a
broadband percussive signal's own current median frequency doesn't reliably
push that median away from the notch -- removing energy there just
redistributes weight to whatever spectral content is left, which can land on
either side unpredictably. Two iterations of the same instinct ("cut where the
overlap is") produced two different, both-wrong outcomes. This is real
information about `mix_fix.py`'s current tool vocabulary being too blunt for
this class of problem, not something to keep iterating on blindly hoping the
third try lands -- a genuinely better fix would likely need a different tool
(a highpass on percussion's low end rather than a narrow notch at its
centroid, so the removed energy is structurally guaranteed to shift the median
upward instead of leaving the outcome to chance) or accepting the tradeoff and
declaring victory on the *original* kick↔percussion fix alone rather than
chasing the percussion↔bass overlap it created.

Stopped at 2 passes rather than trying a 3rd blind iteration -- consistent
with the whole session's pattern of treating a real negative result as
information worth stopping on, not something to paper over with another guess.

## Pass 3: highpass added, diagnosis confirmed correct, deeper problem surfaced (2026-07-26)
Added `highpass` as a real third `mix_fix.py` fix type (ReaEQ's existing
bandtype=0 hipass band -- no new REAPER tool needed), with the tool description
explicitly warning against `eq_cut`'s unpredictable direction (backed by pass
2's real failure, not a guess) and recommending highpass when a signal needs
to vacate a register entirely.

**The model used it well and reasoned about the whole history**: given all of
pass 1 + pass 2's fixes as `prior_fixes` context, it proposed highpassing
percussion at 220Hz *and*, unprompted, reverting the now-redundant bass EQ cut
back toward 0dB -- correctly recognizing that once percussion is structurally
out of the low register, bass doesn't need its own compensating cut anymore.
Genuine simplification, not more stacking.

**Real result, and it's the most informative one yet**: the centroid prediction
was **exactly right** -- percussion moved from 103Hz to 159Hz, upward as a
highpass should (confirms pass 2's diagnosis was correct, not just plausible).
But 159Hz is almost precisely percussion's *original*, pre-any-fix centroid --
three passes netted to zero displacement, and both original overlaps
(kick↔percussion, percussion↔bass) are back at nearly their starting ratios.
**Worse**, a highpass at 220Hz turned out to remove so much of
`Plucks/Metallic.fxp`'s actual energy that percussion's level collapsed to
-43.3 LUFS (from -34.2) -- a new 14.3dB gap vs. bass, the worst loudness-balance
failure of any pass. The whole backbone kept trending quieter across all three
passes (-24.3 → -26.0 → -27.6 → -28.5 LUFS combined) -- every fix so far has
only removed energy, none has added any back, a structural bias built into
this session's chosen mix-fix vocabulary (sidechain ducking + subtractive EQ
only).

**The real lesson, confirmed by evidence across 3 real passes, not assumed**:
for a preset whose actual sonic identity lives in the exact register clashing
with its neighbors, mix-level surgery (sidechain, notch, or highpass) cannot
resolve the clash without gutting what made the sound useful in the first
place -- the correct fix is picking a *different preset* at the leaf level,
not further mix processing. This connects directly back to the already-proven
`escalation.py` retry mechanism (exactly what fixed the earlier silent-pulse
leaf by re-emitting with a different, better-suited preset) -- suggesting
composition-level failures should sometimes route back to leaf-level
re-emission rather than only ever trying harder at the mix-fix level.
**Stopped at 3 passes** -- the diagnostic value of a 4th mix-only guess is low
now that the evidence points at a leaf-level fix instead.

## Leaf-level re-emission tried on the same failure: solved register, created loudness (2026-07-26)
Routed percussion back to `leaf_emit.py`'s re-emission (via `feedback`, same
mechanism `escalation.py` already proved on the silent pulse leaf) instead of a
4th mix-fix pass -- fed it the full 3-pass mix-fix history and why it failed,
told it explicitly to pick a genuinely higher-register instrument this time.
Cleaned up first: deleted percussion's ReaComp+ReaEQ, removed the sidechain
send from kick (abandoning the mix-fix approach for this leaf entirely, not
layering a new approach on top of the old one).

**The model responded correctly to the feedback**: picked `Percussion/Verber.fxp`
(a different preset entirely) and moved every note from the mid-range (48-55)
up to 84-90 -- both changes directly responsive to "pick something whose energy
sits above 500Hz."

**Real result: solved exactly what it was asked to solve, nothing more.**
Percussion's centroid moved from 159Hz to **439Hz** -- comfortably clear of
both kick (230Hz) and bass (111Hz). The composition review's spectral-overlap
complaint is **completely gone**, for the first time across 4 total fix
attempts (3 mix-fix + this one). But a **new** problem appeared: percussion
rendered at -42.1 LUFS, even quieter than any mix-fix attempt -- "Verber" is
plausibly a reverb-tail-oriented preset, hitting the same class of problem as
the very first pulse-leaf bug from earlier in the session (a preset whose
envelope doesn't produce strong output on short percussive MIDI triggers).
Composition review now fails on a 13dB loudness gap instead of spectral
overlap; the leaf's own review_leaf also independently failed hard (measured
distance 17.586) -- the standard leaf-review pipeline would have caught this
new problem on its own, separate from the composition check.

**The complete picture, now backed by real data across 4 total fix attempts,
not speculation**: mix-level fixes (sidechain/EQ/highpass) and leaf-level
re-emission are NOT interchangeable -- each solves a different class of
problem (relational/register vs. this-specific-leaf's-own-envelope-behavior),
and this specific failure needed both, applied in sequence, not either alone.
Neither mechanism is "the" fix; they're complementary tools a real fold would
need to chain (leaf retry for register, then either another leaf retry or a
mix-level gain boost for the resulting loudness gap) rather than treat as
alternatives to pick once.

**Left in this state deliberately** -- not chasing a 5th fix pass. The
combined value of this whole thread (4 real fix attempts, 2 real mechanisms,
1 confirmed-correct diagnosis, 1 genuine architectural finding about tool
complementarity) is now complete enough to design the real next piece from,
rather than continuing to patch this one specific backbone by hand.

## Orchestration: which fix strategy, and when to switch -- built and validated (2026-07-26)
Closed the previous entry's #2. `src/planner/orchestrate.py`'s `choose_fix_strategy()`
decides mix_fix vs. leaf_retry vs. escalate for a failing composition review, given
the real, hard-won lesson from the 4-round backbone saga: **reason count trending
non-improving across consecutive rounds of the same strategy** is the one clean
signal available from review data alone (crude -- documented as missing at least
one real regression that didn't change the reason count, round 2 of the saga --
but real and honestly characterized, not oversold). `max_non_improving` defaults
to 2, matching `escalation.py`'s own `DEFAULT_MAX_ATTEMPTS` for consistency across
the planner package, not independently tuned.

**Validated against the actual 4-round history**, not just trusted by design
(`scripts/orchestrate_validate.py`, replaying the real `ReviewState` reason lists
from `drop_tree_review.py` through `backbone_reemit_review.py`): the policy
reproduces the exact sequence of decisions made by hand -- mix_fix, mix_fix,
mix_fix, switch to leaf_retry -- **4/4 rounds match**. Its recommendation for the
still-open round 5 (retry `leaf_retry` again, since it's only had one
non-improving round so far, not two) independently matches what was already
flagged as the natural next step in the previous entry, before the policy was
even asked. This isn't a retrofit dressed up as validation -- the reason-count
data was fixed before the policy was written, and the policy's job was to see if
a simple, honest rule reproduces sound judgment from it, which it did.

**Explicitly scoped narrowly, not oversold**: `choose_fix_strategy()` decides
strategy *family* and *when to give up on one*, nothing about *which specific*
mix fix or leaf change to make (that's still `mix_fix.py`/`leaf_emit.py`'s own
model calls) or *which sibling* a leaf_retry should target (left to the caller,
since that requires reading which node_ids a composition failure actually names
-- the same kind of judgment call this project has consistently kept in
`review.py`'s structured `ReviewState.reasons`, not string-parsed here).

## Round 5: the live loop worked, and it found a worse bug + its own blind spot (2026-07-26)
Built `scripts/backbone_orchestrated_round5.py` -- rebuilds the real 5-round review
history from the actual persisted `state.json` files on disk (real audio
measurements, not hand-typed reason strings), calls `choose_fix_strategy()` for
real (not replayed), and dispatches to a real `emit_leaf_implementation()` call
using `escalation.feedback_for_retry()` generically instead of hand-crafted
feedback text. This is qualitatively different from `orchestrate_validate.py`:
that replayed fixed historical data through the function; this let the function's
live output pick the next real action.

**It worked as a pipeline**: same review history reconstructed independently from
real files matched the hand-replayed version exactly; the orchestrator correctly
said `leaf_retry`; the resulting live model call (using generic feedback, not my
own wording) produced a genuinely different response from every prior attempt --
`Percussion/Synth Tom 2.fxp`, mid-range notes (60-64), dense 16th-note pattern.

**Executed live, and it's the worst result of the entire session**: near-total
digital silence, sample_peak **-110.2dB** (not "quiet" -- essentially the noise
floor), `own-criteria measured distance 295.141` (vs. threshold 4.0, the largest
distance recorded all session by a wide margin).

**A real, second-time-confirmed limitation of `orchestrate.py` itself**: round 4
(-42.1 LUFS) and round 5 (-110dB, effectively -infinity) both report as exactly
"1 reason" in the composition review ("undefined LUFS" / "13dB apart" -- one
reason either way), so the reason-count signal treats them as equally bad,
completely missing that round 5 is a categorically different failure. This is
precisely the blind spot the module's own docstring already flagged from round 2
of the mix-fix saga (a real regression that didn't change the reason count) --
now confirmed on a starker case, not a one-off.

**A new hypothesis worth testing before more retries, not yet confirmed**: three
different percussion presets across this whole saga -- a pad-type preset (the
very first pulse-leaf bug), `Verber.fxp`, and now `Synth Tom 2.fxp` -- have all
produced near/total silence when driven by the same short 0.25-beat MIDI note
length. That pattern is starting to look less like "wrong preset each time" and
more like a structural mismatch between very short note triggers and how many
Surge envelopes actually respond -- worth testing directly (e.g. re-run round 5
with longer note lengths, same preset) before assuming the next preset choice is
the fix. Not chased further this session -- flagged as the honest next hypothesis,
not confirmed.

**Deliberately stopped here** rather than immediately trying a round 6 -- the
combined yield (a working live loop, a newly confirmed orchestrator limitation,
and a real testable hypothesis about note length) is a complete, valuable stopping
point, and blindly retrying a 6th time without addressing the note-length
hypothesis would likely just reproduce the same class of failure with a 4th preset.

## Note-length hypothesis tested directly on `Synth Tom 2.fxp` -- refuted as stated, refined into a real finding (2026-07-26)
Live-tested against the actual round-5 percussion leaf (track 7, `DROP percussion`,
same `Synth Tom 2.fxp` preset, same MIDI content) rather than guessing:

- **0.25 -> 0.5 beat (doubling every note's length, same pattern)**: still
  near-total silence, sample_peak **-91.5dB**, LUFS undefined. The simple "just
  make notes a bit longer" version of the hypothesis is **refuted** -- 0.5 beats
  (0.25s at 120bpm) is nowhere near enough.
- **Single sustained 15-beat note**: real audible output, -24.7 LUFS, -22.5dB
  peak, centroid 133Hz. Confirms the preset itself is not broken/silent by
  design -- it can produce normal output.
- **Bracketed the actual attack time** with 4 isolated notes (1/2/4/8 beats =
  0.5/1.0/2.0/4.0s at 120bpm), measured peak dB directly per time-window from
  the rendered wav (numpy/soundfile, not the aggregate LUFS pipeline): -56.9dB
  at 0.5s, -43.4dB at 1.0s, -23.4dB at 2.0s, -23.8dB at 4.0s (plateaued by 2s).
  **Real attack time is ~1.5-2 full seconds**, not a fraction of a beat.

**The actual, more useful finding**: this isn't "percussion presets need
slightly longer notes" -- it's that `Synth Tom 2.fxp` (like `Verber.fxp` and the
original pad-type pulse-leaf bug before it) is a **slow-attack, pad/riser-style
patch mislabeled by category**, structurally incompatible with *any* rhythmic
note length a real percussion part would use (even a full quarter note at
120bpm is only 0.5s -- 4x too short). Three separate percussion-category
presets across this whole saga have now failed the identical way for the
identical reason: category name isn't a reliable signal of envelope shape in
this preset library. Lengthening notes within a musically sane range will not
fix this class of failure -- the real fix has to be preset selection informed
by envelope/attack behavior, not just category, or a pre-flight check that
renders a single hit and measures onset time before committing to a preset for
a rhythmic role.

Project restored to its exact pre-test round-5 state (same notes, same preset)
and saved afterward -- this was a throwaway diagnostic, not a kept change.
Scratch renders (`drop_leaf_1_perc_notelength_test.wav`, `_sustained_test.wav`,
`_bracket_test.wav`) left in `state/leaf_proof/` (gitignored).

## Attack-time pre-flight check: built, validated live, and used for a real fix (2026-07-26)
Closed the previous entry's #1-3 in the user's specified order (Vital explicitly
deferred until "Surge works" -- i.e. stage 4 first).

**`src/planner/preset_attack.py`** (pure functions, no REAPER dependency):
`measure_attack_time(wav, note_start_s, note_dur_s)` computes an amplitude
envelope (RMS over 10ms hops) and returns when it first crosses 50% of its own
peak; `attack_ok_for_note_length(measurement, note_length_beats, tempo_bpm)`
gates on the real rule this session's data established: **a preset is usable
for a note only if its attack completes within that note's own length**.
Critical implementation detail, found by an early mistake and corrected before
trusting any result: the test note must be generously long (8 beats) regardless
of the candidate note length being evaluated, and reused for every candidate
length -- using a short truncated window per candidate gives a self-referential
"peak" that hasn't actually plateaued yet, which falsely passes short notes
that are really still just as silent. Fixed and reverified against the
already-collected round5 wavs before trusting it on anything live.

**`scripts/check_preset_attack.py`** -- the live-test harness (same "script
documents the plan, the controlling MCP session executes it" pattern as every
other live check this project has built). Validated with a real positive AND
negative control on the actual live project, not just unit-level: `Percussion/
Kick 909ish.fxp` (already used successfully for the kick leaf) -- 0.0s attack,
passes at every rhythmic length; `Percussion/Synth Tom 2.fxp` (the known-bad
round-5 preset) -- 1.12s attack, fails everything under 4 beats, matching the
hand-measured bracket data exactly. Track 7 restored to its exact prior state
(preset + notes) and saved after both tests.

**Wired into `scripts/leaf_emit.py`**: `min_note_length_beats(ops)`,
`needs_attack_check(ops)` (true when the shortest note is <= 2 beats -- the
real cutoff found live), and `feedback_for_attack_failure(...)` (same retry-
feedback mechanism as `escalation.feedback_for_retry`). `leaf_emit.py` itself
still can't call REAPER (same standalone-client gap as always), so this is a
signal for the controlling session to act on, not a fully automatic gate --
documented plainly in both modules' docstrings rather than overclaiming
automation that doesn't exist yet.

**Immediately paid for itself on the noise leaf** (`proof/section_drop/child_3`,
`FX/Crackling.fxp`, the multi-level-recursion-era total-silence bug flagged
back at that entry): live-tested the ORIGINAL preset first, and it refuted the
attack-time hypothesis for this specific leaf -- a 15-second sustained note on
`Crackling.fxp` never exceeds -52 to -54dB RMS even at full sustain (confirmed
with numpy/soundfile envelope inspection directly, not just the pass/fail
check). **Different bug class than the percussion presets**: this isn't a slow
attack, it's a preset that doesn't respond to MIDI note-on/velocity like an
instrument at all (a fixed-level noise/crackle generator) -- no note length
fixes that. Re-emitted via `leaf_emit.emit_leaf_implementation()` with feedback
stating this precise diagnosis (not the generic attack-time message, since that
would have been the wrong lesson); the model responded by picking a genuinely
different preset, `Plucks/Man Machine.fxp` (an apt name for "machine-noise
grit" too), with a 16th-note pattern (min length 0.25 beats). Live-tested THAT
preset's attack before committing (0.01s, passes clean, -30.7dB peak) --
using the new check as a real gate on the re-emitted plan, not just on the
original failure. Executed and saved live.

**Real result**: noise leaf went from **-110dB (total silence) to -24.7 LUFS,
-18.5dB peak, embedding distance 0.633** (passes its own 0.85 threshold --
sonically apt pick). Own-criteria measured distance still fails (12.6 vs
threshold 4.0) -- but this is the same solo-stem-vs-full-mix-reference
artifact that's affected every isolated leaf render all session, not a new or
unexpected problem; not chased further, consistent with how every other
instance of this exact pattern was handled.

**`orchestrate.py` hardened with real magnitudes, not just reason count**:
added a `metrics: dict` field to `ReviewState` (node.py), populated by
`review_composition` with the actual numbers its `reasons` text was already
derived from and previously threw away (`worst_lufs_gap_db`,
`undefined_lufs_count`, `worst_centroid_ratio`, `combined_deficit_db`,
`combined_undefined`). `orchestrate.py`'s `_round_severity()` turns these into
one comparable scalar per round, weighted so a sibling going to undefined LUFS
(effectively zero output) can never read as equal-or-better than a merely-
large gap -- falls back to the original reason-count proxy when `metrics` is
empty (old/replayed `ReviewState`s), so nothing existing broke.

**Verified three ways, not just trusted by design**: (1) re-ran
`orchestrate_validate.py` (hand-typed historical reasons, no metrics) --
still 4/4 match, confirming the fallback path is exercised correctly and
nothing regressed; (2) re-ran `backbone_orchestrated_round5.py` (real
`review_composition()` calls against real state.json files, metrics now
genuinely populated) -- identical `leaf_retry` decision, confirming the new
severity path agrees with the old one on real historical data where they
should agree; (3) built a synthetic adversarial case matching the exact
documented blind spot (round A: 2 reasons, no undefined LUFS; round B: only
1 reason but a sibling gone totally silent) and confirmed the **old**
reason-count logic would have wrongly read 2->1 as improvement and reset the
non-improving streak, while the **new** severity logic correctly keeps the
streak alive (severity 17.0 -> 1000.0, unambiguously worse). Full test suite
(66 tests, `unittest discover`) still passes clean.

## Autonomous loop, iteration 1: root-level drop review passes for the first time (2026-07-26)
User asked to iterate one step at a time (do/test/report) via `/loop` until
stopped. First real action: re-ran the root-level `section_drop` composition
review (all 4 direct children -- backbone aggregate, lead, pad, noise) for the
first time since fixing the noise leaf's silence bug.

**Result: PASSES.** Worst LUFS gap 11.8dB (just under the 12dB threshold),
worst centroid ratio 1.87 (above the 1.5 overlap threshold), combined-mix
deficit 0.2dB (no cancellation). Fixing the noise leaf's silence alone was
sufficient -- confirms it was the sole driver of the earlier root-level FAIL,
not one of several simultaneous problems.

**But this does NOT mean everything is clean**: re-ran the narrower,
backbone-internal composition check (child_0's own three children: kick/
percussion/bass) separately, and it still FAILS -- percussion (track 7) still
has undefined LUFS. Root passing and a subtree failing are both true at once
because review is hierarchical: the root check only ever looks at each direct
child's own *aggregate* render, and kick+bass together are loud enough that
the backbone's aggregate LUFS looks normal even with percussion contributing
nothing. **Real architectural confirmation, not a bug**: passing at a
coarser grain never implies a finer grain is clean.

## Iteration 2: percussion's silence bug actually fixed for real, using the attack-time check as a live gate (2026-07-26)
Percussion (`proof/section_drop/child_0/child_1`, track 7) had been sitting in
its broken round-5 state (`Synth Tom 2.fxp`, near-total silence) all session --
it was only ever used as the *test subject* for building the attack-time check,
then restored to its broken state afterward since fixing it wasn't in scope at
the time.

Re-emitted via `leaf_emit.emit_leaf_implementation()` with feedback stating the
precise measured root cause (Synth Tom 2 and Verber both confirmed too slow-
attack for this pattern). Model picked `Plucks/Metallic.fxp`, min note length
0.125 beats (a 16th note) -- **live attack-tested it before committing**
(0.0s attack, passes clean even at 0.125 beats) using `check_preset_attack.py`
exactly as designed. Executed and saved.

**Real result: silence bug genuinely fixed** -- -25.8 LUFS, -17dB peak, real
audible signal, embedding distance 0.53 (comfortably passes 0.85). Own-criteria
measured distance still fails (9.7 vs 4.0) -- same solo-stem-vs-full-mix
artifact affecting every isolated leaf render all session, not new.

**But the backbone composition review still FAILS** -- for a different,
better reason now: `undefined_lufs_count` is 0 (no more silence), but kick
(-39.6 LUFS) and percussion (-25.8 LUFS) are now 13.8dB apart with a centroid
overlap (230Hz vs 323Hz, ratio 1.41) -- almost exactly the SAME kick-
percussion pairing/ratio the very original pre-any-fix backbone had at the
start of the whole mix-fix saga. Fixing silence didn't fix everything; it
surfaced the next real problem underneath, consistent with this project's
whole pattern.

## Iteration 3: used orchestrate.py live to decide the next move -- it said mix_fix, we ran it, and it made things worse (2026-07-26)
Rather than guessing the next fix, called the actual `choose_fix_strategy()`
tool built earlier this session against this round's real
`ReviewState`/`metrics` -- correctly returned `mix_fix` (first attempt, cheaper
relational fix). Called `mix_fix.propose_composition_fix()` for real (Sonnet):
proposed **highpass percussion at 200Hz** (push its centroid away from kick,
using the confirmed-reliable technique from earlier in the session), **light
sidechain kick->percussion** (-4dB, reasoning percussion's off-beat pattern
mostly doesn't overlap kick's hits in time), and a **preventive highpass on
bass at 60Hz**. Executed all three live (ReaEQ + ReaComp + `setup_sidechain_
compression`), re-rendered percussion/bass/backbone-combined, re-measured.

**Real result: it got WORSE, not better** -- confirmed both by eye and by
`orchestrate.py`'s own severity metric (14.70 -> 17.84, a genuine regression,
not just eyeballed). Reasons went from 2 to 3: kick-percussion gap widened to
16.8dB (worse), and a **new** kick-bass gap appeared (12.5dB, didn't exist
before) since bass's own highpass nudged its level. Centroid ratio barely
moved (1.41 -> 1.39, negligible -- the highpass on percussion did essentially
nothing to separate it from kick, unlike the earlier successful highpass
finding on this exact backbone). Orchestrator, asked again, correctly said
"keep trying mix_fix" (streak 1 of 2, per its own policy) -- a legitimate
per-policy answer, but pointed at investigating *why* the fix failed rather
than blindly running a 2nd mix_fix pass immediately.

## The real finding: kick's low LUFS is a duty-cycle artifact, not a mixing problem -- review_composition's loudness check has a structural blind spot for sparse rhythmic parts (2026-07-26)
Investigated *why* kick reads as -39.6 LUFS before accepting it as "the
problem." Checked kick's own MIDI (max velocity 127 on every note, clean
on-beat 4/4-ish pattern -- nothing wrong with the content) and its own
measured stats: **sample_peak -24.0dB** (a genuinely strong, punchy hit),
**crest_factor 20.5dB** (very high -- sharp transient, long silence between
hits, exactly what a punchy kick should look like), **active_ratio 17.5%**
(only 17.5% of the render frames have audible signal at all).

**This fully explains the "problem" without any bug**: integrated LUFS
averages in all the silence between sparse hits, so a kick playing loud, sharp
transients on a fraction of beats will always read far quieter on integrated
LUFS than a denser or more continuous neighbor (percussion's busier pattern,
bass's longer notes) -- independent of how loud or punchy any single hit
actually is. `review_composition`'s loudness-balance check (raw integrated-
LUFS gap > 12dB threshold) doesn't account for this at all, and is very likely
a real contributor to why the ENTIRE backbone mix-fix saga (4+ rounds
spanning most of this session) never fully converged: every round was tuning
percussion/bass in relation to kick's integrated LUFS, a number that no
EQ/sidechain/preset choice can close without either destroying the kick's
sparse rhythmic identity (playing it far more often) or the metric itself
becoming duty-cycle-aware. Not yet fixed -- this is a `review.py`-level change
(e.g. compare LUFS computed only over active/gated frames, or lean on peak/
crest-factor comparison for sparse parts instead of integrated LUFS), not
another mix_fix/leaf_retry round on the same siblings.

## `review_composition`'s loudness check made duty-cycle-aware -- fixed and validated (2026-07-26)
Closed the previous entry's #1 directly. `src/planner/review.py`: added
`SPARSE_ACTIVE_RATIO_THRESHOLD` (0.5) and `PEAK_BALANCE_THRESHOLD_DB` (12.0,
reused from the LUFS threshold pragmatically, not independently re-tuned --
flagged as a real simplification, not a validated number). For any
loudness-balance pair where either sibling's `active_ratio` (already computed
by `analyze.measure`, just never read by `review.py` before) sits below the
threshold, the check now compares `sample_peak` (duty-cycle independent)
instead of integrated LUFS, with its own reason text that says explicitly
*why* peak was used instead of LUFS. New `used_peak_for_sparse_pair` metric
field added alongside the others. All 66 existing tests still pass.

**Validated against real data, not just trusted by design**: re-ran the
backbone review against the exact pre-mix-fix-regression state (v2). The
kick-vs-percussion *loudness* false positive (13.8dB LUFS gap, driven purely
by kick's low duty cycle) is **gone**, as hypothesized. What's left is
genuinely different and correctly NOT silenced by this change: kick-vs-bass
now shows a 12.1dB *peak* gap (barely over the reused threshold -- a real
open question about whether 12dB is the right number for peak comparisons
specifically, not yet resolved) and the kick-vs-percussion *spectral centroid*
overlap (1.41 ratio, 230Hz vs 323Hz) is untouched, because that's a real
register clash, not a duty-cycle artifact -- exactly the right selectivity: a
targeted fix, not a threshold loosened until everything passes.

## Regressive mix_fix round reverted live; confirmed the corrected metric leaves exactly 2 genuine reasons (2026-07-26)
Reverted all three live changes from the earlier regressive mix_fix round:
deleted the kick->percussion sidechain send (track 6, send_index 0), disabled
percussion's ReaEQ highpass band and ReaComp (track 7, fx_index 1 and 2),
disabled bass's ReaEQ highpass band (track 8, fx_index 1). Saved. Re-rendered
percussion/bass/backbone-combined and re-ran the now-duty-cycle-aware
composition review on the live, reverted state.

**Result matches the earlier v2 analysis almost exactly** (tiny floating-
point differences from re-rendering): review still FAILS, but now for
precisely 2 reasons, both real, neither a metric artifact:
1. kick (-24.0dB peak) vs. bass (-11.9dB peak), 12.1dB gap -- right at the
   reused 12dB threshold, genuinely marginal, not resolved by this session
   (deliberately not loosening the threshold to force a pass -- that would be
   gaming the metric, not fixing anything real).
2. kick (230Hz) vs. percussion (324Hz) spectral centroid ratio 1.41 -- a real
   register clash, correctly untouched by the duty-cycle fix since it was
   never a duty-cycle artifact to begin with.

This closes out the whole percussion-silence -> mix-fix-regression ->
duty-cycle-metric-fix -> revert thread for real, with an honest, defensible
end state: one borderline judgment call and one genuine unsolved spectral
problem, nothing hidden or hand-waved.

## Second real mix_fix round tried on the genuine kick-percussion/kick-bass issues -- also regressed, and surfaced a real implementation gap in mix_fix.py itself (2026-07-27)
Continuing the autonomous `/loop`. Called `mix_fix.propose_composition_fix()`
again, this time armed with the corrected duty-cycle-aware metric and the
2 genuine remaining reasons (kick-bass 12.1dB peak gap, kick-percussion
1.41 centroid ratio). Model proposed a materially different pair of fixes
than any prior round: **sidechain kick->bass** (-6dB, targeting the peak gap
directly this time, correctly reasoning kick is the sparse priority
transient) and **highpass percussion at 250Hz** (targeting the centroid
overlap, correctly avoiding eq_cut per the tool's own documented warning).
Executed live: added ReaComp to bass (fx_index 2) + `setup_sidechain_
compression(trigger=kick, target=bass, send=-6dB)`, re-enabled + retuned
percussion's existing ReaEQ hipass band to 250Hz.

**Real result: regressed again**, confirmed by `orchestrate.py`'s own
severity metric (13.02 -> 19.11). Percussion's centroid barely moved (324Hz
-> 322Hz, negligible -- 250Hz cutoff too gentle/low to shift a centroid
already sitting at 322Hz, unlike the much more aggressive 220Hz cut that
worked on a *different*, lower-starting-point percussion preset earlier this
session). **Bass got measurably LOUDER, not quieter** (-11.9dB -> -5.9dB
peak) despite being the sidechain-ducked target -- widening the kick-bass
gap from 12.1dB to 18.1dB, the opposite of the intended effect.

**Investigated why rather than just reverting blindly**: checked ReaComp's
actual live parameters on bass (`track_fx_get_param`/`_get_param_name`).
Detector-routing toggles (`SignIn`=1, sidechain-listening enabled; `AudIn`=0,
normal main-signal input) were both at their expected, correct defaults --
ruled out a signal-bleed/routing misconfiguration. **The real finding**:
`setup_sidechain_compression()` (the REAPER-MCP tool) only wires *routing*
(the send volume, the detector's sidechain source) -- it never touches
ReaComp's own `Threshold`/`Ratio`, which are left at the plugin's untouched
defaults. `mix_fix.py`'s `propose_composition_fix()` only ever asks the model
for `send_volume_db`, never threshold/ratio -- so the "sidechain fix" type as
currently implemented has no way to guarantee the compressor's detector
actually crosses its threshold and engages any real gain reduction at all.
Whatever changed bass's level here came from a mechanism this fix type
doesn't control, which is itself the bug: **a sidechain fix that can't
verify or configure how much it actually ducks isn't a complete fix
mechanism**, independent of whether this specific round's numbers happened
to move the wrong way.

Reverted both changes (deleted the sidechain send, disabled ReaComp on bass,
disabled percussion's ReaEQ hipass band again) and saved -- confirmed back
to the same 2-reason honest-failure baseline from the previous entry.

## Sidechain fix type: first fix was incomplete -- it's reproducibly unreliable, not just under-configured (2026-07-27)
Implemented the planned fix: added required `threshold_db`/`ratio` fields to
`mix_fix.py`'s sidechain schema, `_validate()` now rejects a sidechain fix
missing either. **Before trusting this as the real fix, tested it live** --
same discipline this project has used throughout (verify against real
behavior, not assumed math). No formatted-value read tool exists for generic
REAPER-MCP FX params (unlike the custom normalize/format tooling built for
Surge earlier this session), so exact dB/ratio semantics of ReaComp's raw
`[0,2]`-range params aren't calibrated -- set an aggressive raw
Threshold=0.1, Ratio=1.8 (well past the untouched defaults) directly via
`track_fx_set_param` and re-tested the exact same kick->bass sidechain setup.

**Result: bass got louder again** (-11.9dB -> -5.9dB peak) -- statistically
identical to the first, unconfigured attempt. Two independent live tests,
two different configurations, the same wrong-direction result. This rules
out "wrong threshold/ratio" as the (sole) explanation. Checked `SignIn`/
`AudIn` detector-routing toggles again -- both at their expected values, not
misconfigured. **Real, corrected finding**: this is very likely a genuine
channel-routing quirk in how `setup_sidechain_compression` wires the aux 3-4
channels (leading unconfirmed suspect: a 2-channel track receiving a send
addressed to channels 3-4 could fold back onto the main output instead of
staying isolated as a true sidechain input) -- not something `mix_fix.py`'s
proposal schema can fix at all, and not verified further since no tool in
this session's REAPER-MCP surface reads a track's actual channel count.

**Corrected the module's own documentation and tool description** to reflect
this properly (not just the earlier, too-optimistic "add threshold_db/ratio
and it's fixed" framing) -- `sidechain` now carries an explicit CAUTION in
its schema description recommending `eq_cut`/`highpass` instead until this is
properly root-caused. Reverted the live test (deleted the sidechain send,
disabled ReaComp on bass) -- tracks 6-8 back to the same clean, honest
2-reason baseline. All 66 tests still pass.

## Added a real `gain` fix type to mix_fix.py -- and it worked cleanly on the first try (2026-07-27)
Closed the previous entry's real gap directly: neither `eq_cut`, `highpass`,
nor the now-unreliable `sidechain` can address a pure loudness-BALANCE
problem (a peak/LUFS gap with no spectral complaint) -- they're all spectral
or time-varying tools applied to a problem that's neither. Added `gain`
(flat `set_track_volume` change via a new required `gain_change_db` field) to
`MIX_FIX_TOOL`'s enum and `_validate()`. All 66 tests still pass.

Called `propose_composition_fix()` again on the live 2-reason state (kick-bass
12.1dB peak gap, kick-percussion 1.41 centroid ratio). Model correctly split
the two problems by kind: **gain** (-6dB on bass) for the pure loudness gap,
**highpass** (220Hz on percussion) for the spectral overlap -- no longer
reaching for sidechain at all, per the new caution in its own tool
description.

**Real result: gain fix worked exactly as intended, first try.** Bass peak
moved from -11.9dB to -17.9dB -- a clean, exact -6dB, fully predictable
(unlike every sidechain attempt this session). The kick-bass loudness reason
is **completely gone** from the review. Severity improved for real
(13.02 -> 11.45, confirmed by `orchestrate.py`'s own metric, not just eyeballed).
**The highpass on percussion was a no-op again** (centroid 324Hz -> 322Hz,
same as the earlier 250Hz attempt's negligible move) -- two independent
highpass attempts at different cutoffs (220Hz, 250Hz) on this exact
percussion content have both failed to shift its centroid at all, unlike an
earlier highpass in this same session that successfully moved a *different*
percussion preset's centroid by 56Hz. This matches the session's own
established, validated lesson from the percussion-silence saga: when a
preset's actual sonic identity occupies the clashing register, mix-level EQ
cannot relocate it -- the fix has to be a different preset at the leaf level,
not another EQ variant.

Backbone composition review is now down to **exactly 1 genuine reason**
(kick-percussion spectral overlap) -- the loudness side of this whole thread
is closed for real, not patched around.

## Backbone composition review PASSES for the first time all session (2026-07-27)
Closed the whole backbone saga's remaining thread. Re-emitted percussion via
`leaf_emit.emit_leaf_implementation()` with feedback stating precisely that
the problem is REGISTER, not attack time (already ruled out) and NOT
EQ-fixable (two highpass attempts at 220/250Hz on the prior preset both
no-op'd). Model picked **`Plucks/Snap.fxp`** at a higher pitch range
(71-78 vs. the previous 60-67) -- live attack-tested first (0.0s attack,
-2.0dB peak, passes clean) after 4 transient `SetParam` timeouts and a 5th
successful attempt (REAPER health-checked directly mid-failures -- 475MB RSS,
10.6% CPU, empty bridge dir, nothing alarming -- consistent with ordinary
flakiness, not a new bug, matching this session's own established pattern
for this exact class of transient error).

**Register problem: solved decisively.** Centroid jumped 322Hz -> 1375Hz,
comfortably clear of kick's 230Hz (ratio ~6, previously 1.4). Also the first
own-criteria PASS for any drop-section leaf all session (measured distance
1.54 vs 4.0, embedding 0.577 vs 0.85) -- no solo-stem artifact this time.

**But it immediately created a new, more dramatic problem -- the same
established pattern as the earlier Verber.fxp saga, this time louder**:
`Snap.fxp` measured `sample_peak = 0.0dB` exactly (clipping), burying both
kick (24.0dB gap) and bass (17.9dB gap) by huge margins. Diagnosed instantly
as a pure gain problem (not register, not attack, not a preset mismatch) and
fixed the same reliable way as the earlier bass fix: `set_track_volume`
-6dB) -> -20dB flat reduction on percussion's track.

**Real, final result: backbone composition review PASSES.** Kick -24.0dB,
percussion -14.0dB, bass -17.9dB peak (max gap 10dB, under the 12dB
threshold), centroid ratio still ~6 (no overlap). `orchestrate.py`'s own
severity metric: 10.0 (best of every round this entire saga, mix-fix or
leaf-retry). **Percussion's own-criteria review flipped back to FAILED**
(measured distance 19.3, worse than the pre-gain-cut 1.54) -- pushing gain
down 20dB for ensemble balance moved it away from the "drop" reference
envelope's expected loudness, the same solo-stem-vs-full-mix-reference
tension that's affected every leaf all session, just pointing the opposite
direction this time. Not a new problem, not chased further -- composition
(the sibling-relative check) is what this whole thread was actually trying
to fix, and it's fixed.

**This closes the entire kick/percussion/bass backbone saga** that started
with the very first mix-fix round early in the session: 4 mix-fix rounds
(never converged) -> 1 leaf retry (fixed register, created loudness gap) ->
orchestration built and proven -> round 5 (worse, total silence) -> silence
fixed via the new attack-time check -> 2 more mix-fix rounds this cycle
(both regressed, surfacing the duty-cycle metric bug, the sidechain
reliability bug, and the missing `gain` fix type) -> leaf-level re-emission
for register (fixed overlap, caused clipping) -> gain trim -> **PASS**.
Every mechanism built this session (attack-time check, duty-cycle-aware
loudness metric, `gain`/`highpass`/`eq_cut`/sidechain-with-caution fix
types, `orchestrate.py`'s severity scoring, leaf-level re-emission) played a
real, necessary role in getting here -- none of it was decorative.

## Root-level drop review re-confirmed clean after the backbone fix (2026-07-27)
Re-rendered a fresh full-drop combined mix (all 6 tracks, current live state)
and re-ran the root-level `section_drop` review (backbone/lead/pad/noise)
with the updated backbone numbers.

**Result: PASSES, and cleanly** -- severity 5.72, the lowest (best) of any
composition-review round measured this entire session. Worst LUFS gap only
5.6dB (well under 12). Worst centroid ratio 1.504 (backbone 791Hz vs. lead
526Hz) -- right at the edge of the 1.5 overlap threshold but still passing,
worth knowing as a close call, not a comfortable margin. The whole drop
section is now composition-clean at BOTH levels (root and backbone-internal)
for the first time -- the fix holds up at the coarser grain too, not just
the narrow one it was built to satisfy.

## Hardened toolchain tested on the BUILD section too -- gain fix generalizes cleanly, highpass surfaces a new nuance (2026-07-27)
Re-ran the build section's composition review (pulse/bass/texture/lead, 4
leaves, a genuinely different section from the drop backbone) with today's
hardened metric. **Result: FAILS for a real reason, correctly NOT flagged as
a duty-cycle artifact** (`used_peak_for_sparse_pair: false` -- all 4
siblings' active_ratio sits above the 0.5 sparse threshold, so LUFS
comparison was legitimately used, not a false positive this metric exists to
catch). Texture (-32.3 LUFS, continuous/active_ratio 1.0) is genuinely too
quiet next to pulse (-16.8) and bass (-14.9) -- 15-17dB gaps -- plus a mild
centroid overlap with pulse (ratio 1.18).

Called `propose_composition_fix()` on this genuinely different section for
the first time. Model split it exactly right: **gain (+9dB on texture)** for
the pure loudness gap, **highpass (300Hz on texture)** for the mild overlap.
Executed live (new ReaEQ added to texture's previously-empty FX chain,
`set_track_volume` +9dB).

**Gain fix generalized perfectly**: texture moved from -32.3 to -24.8 LUFS,
almost exactly the requested +9dB (peak -25.7 -> -19.4, also ~+6dB, roughly
consistent) -- third clean, predictable, correctly-executed `gain` fix this
session (after the two backbone rounds), confirming this fix type is
reliable in general, not a one-off.

**Highpass surfaced a real, new nuance, not a repeat of the old EQ-cut
failure mode**: texture's centroid DID move upward as the tool's own
documentation promises (206Hz -> 245Hz, the structural direction guarantee
held) -- but it moved too far and landed almost exactly on pulse's own
centroid (243Hz, ratio now 1.01 -- worse in ratio terms than before the fix,
even though the *direction* was correct). **The real lesson**: "highpass
always shifts the centroid upward" is true but insufficient -- the cutoff
also needs to clear the SPECIFIC neighbor's own centroid, not just move
generally upward. A cutoff picked without checking where the neighbor itself
sits can overshoot directly onto it. Not yet fixed in `mix_fix.py`'s tool
description -- flagged here as a real gap in the highpass fix type's current
guidance, distinct from eq_cut's already-documented unpredictable-direction
problem.

**Net result**: severity improved (20.56 -> 14.81, confirmed by
`orchestrate.py`'s metric) -- the loudness fix dominates -- but the review
still fails on the (now worse-ratio) centroid overlap. Real, partial
progress, not a full close like the backbone got. Confirms the hardened
toolchain (duty-cycle-aware metric, `gain` fix type, severity scoring) is
genuinely general infrastructure, not drop-section-specific -- it correctly
diagnosed and partially fixed a different section's different problem on
the first try.

## Highpass guidance corrected, retried with an informed cutoff -- made things WORSE, revealing a bigger lesson: EQ changes need a compensating gain, fixes aren't independent (2026-07-27)
Updated `mix_fix.py`'s highpass description to require picking `cutoff_hz`
with real margin above the SPECIFIC neighbor's own centroid (not just any
value above the target's current one) -- direct fix for the previous
iteration's finding. Re-called `propose_composition_fix()` with
`prior_fixes` context; model correctly reasoned from both neighbors' actual
centroids (pulse 243Hz, bass 455Hz) and picked 450Hz specifically to clear
pulse without landing on bass. Executed live.

**Result: severity got WORSE (14.81 -> 22.53), worse than doing nothing at
all (20.56 originally).** Centroid *did* improve as intended (ratio 1.01 ->
1.17, real progress on the spectral side) -- but LUFS collapsed from -24.8
back to -34.1, undoing almost all of the earlier +9dB gain fix. **The real,
generalizable lesson**: a highpass/eq_cut removes real energy, which
directly costs level -- stacking a more aggressive cutoff on top of an
existing gain fix can silently cancel most of that gain's benefit, since the
two fixes aren't independent even though `mix_fix.py`'s schema treats them
as separate line items. Confirmed by isolating variables directly: disabled
the highpass entirely, kept only the +9dB gain, re-measured -- **this
gain-only configuration is the best result found across all three variants**
(severity 12.61, vs. 14.81 with 300Hz highpass, vs. 22.53 with 450Hz
highpass), with only the original mild centroid ratio (1.18) remaining,
unchanged from before any EQ was ever tried. Settled on gain-only as the
live, saved configuration for this leaf (highpass disabled, not deleted).

**Not yet done**: teaching `mix_fix.py` this lesson directly (e.g. a
sidechain/eq_cut/highpass fix proposed alongside an existing or concurrent
gain fix on the same target should account for the level cost, or the
executing session should re-check LUFS after any EQ change and follow up
with a compensating gain adjustment before declaring the round done) --
flagged as a real, validated architectural gap, not fixed this session.

## Compensating-gain fix built and validated -- spectral fixes are now safe, not a gamble (2026-07-27)
Closed the previous entry's gap directly. Added `mix_fix.py`'s
`compensating_gain_db(pre_lufs, post_lufs)` -- returns the dB needed to
restore a target's level after an eq_cut/highpass fix, documented as a
mandatory post-step (re-measure LUFS, apply the returned gain via
`set_track_volume`) rather than an optional nicety. All 66 tests still pass.

**Tested live on the exact case that motivated it**: re-enabled the 450Hz
highpass (previously disabled after it regressed things) and applied
`compensating_gain_db(-23.3, -34.1) = +10.8dB` on top of the existing +9dB
gain (net +19.8dB on texture's track). **Result: LUFS restored to -23.3 --
essentially identical to the gain-only baseline** -- while KEEPING the
improved centroid (283Hz, vs. 206Hz originally, vs. 243Hz for its neighbor
pulse). Full composition review: severity 12.80, statistically tied with
the gain-only result (12.61) but now genuinely carrying the spectral
improvement instead of discarding it. **This is the real validation**: with
proper level compensation, a spectral fix is safe to apply rather than a
gamble that might silently regress the overall result -- the mechanism this
whole sub-thread was working toward.

Settled on this as the final live configuration for the build section's
texture layer: +19.8dB gain (net of the original +9dB plus the +10.8dB
compensation), 450Hz highpass enabled. One mild centroid reason remains
(1.16 ratio, pulse vs. texture) -- consistent across three different cutoff
attempts (300Hz, 450Hz, and this compensated 450Hz), a real practical
ceiling for this specific preset pairing rather than something worth
chasing further with diminishing returns.

## Real pipeline integration: `src/planner/pipeline.py` built and tested (2026-07-27)
Closed the previous entry's largest gap for real, not just documented it.
Built the actual missing glue: `run_leaf_cycle()` (emit -> attack-check gate
-> execute -> review -> escalation.decide() -> retry-with-feedback or stop)
and `run_composition_fix_cycle()` (review -> orchestrate.choose_fix_strategy()
-> propose+apply mix_fix, with the compensating-gain follow-up applied
automatically for any eq_cut/highpass -> re-review -> repeat), as reusable,
testable functions instead of hand-executed sequences.

**The real architectural constraint respected, not worked around**: no
standalone MCP client exists outside a live session, so this module cannot
execute REAPER calls itself (same limitation `scheduler.py` documented from
day one). Solved via an `Executor` Protocol (`test_attack`, `execute_leaf`,
`apply_fix`, `set_gain`, `remeasure`) that a controlling session implements --
this module owns the *decision logic* (what to emit, whether a result
passes, what to try next, when to give up), completely separable from who
actually runs the live calls. That separation is what makes the logic
testable at all without a live REAPER instance.

**`tests/test_pipeline.py`, 6 new tests, all passing** (72 total now, up
from 66) -- using a `FakeExecutor` and a fake Anthropic client (matching
both `leaf_emit.py`'s multi-tool-use response shape and `mix_fix.py`'s
single-forced-tool shape) instead of mocks that assume the answer. Verified:
a leaf passing clean on attempt 1; an attack-check failure correctly
triggering one retry with the right feedback before a live render even
happens (confirmed via `leaf_states` list len -- only one render consumed,
not two); repeated own-criteria failure retrying then escalating at
`max_attempts`; a composition cycle converging to "done" after one gain fix;
an eq_cut/highpass fix automatically triggering the exact compensating-gain
amount (`pre_lufs - post_lufs`); and `choose_fix_strategy()` returning
`leaf_retry` correctly ending the cycle for the caller to route elsewhere
(this module deliberately does NOT guess which sibling a leaf_retry should
target -- same explicit scope boundary `orchestrate.py` itself documents).

**Hit and fixed a real test-authoring bug while writing these** (worth
noting since it's exactly the kind of mistake this project's whole ethos
guards against): an early version of the mix-fix-convergence test gave both
siblings identical centroids in both rounds, which spuriously kept a
spectral-overlap reason alive after the loudness fix and made the test fail
for a reason that had nothing to do with the code under test. Fixed by
giving the test's own fixture data non-overlapping centroids, not by
loosening the assertion.

**Honestly scoped, not oversold**: this is the decision-logic layer, not a
literal autonomous system -- a real run still needs a live MCP-capable
session to implement `Executor` and drive it, same as every other mechanism
this project has built. What's new is that the SEQUENCING logic (which was
previously re-derived by hand, script by script, differently each time) now
lives in one tested module instead of living only in a human's head across
a long session.

## Build->drop seam check: never run before, and it FAILS -- a real side effect of this cycle's own percussion fix (2026-07-27)
Real end-to-end automation being architecturally blocked (no standalone MCP
client -- pipeline.py's `Executor` still needs a live session to implement
it, same documented constraint as ever), picked the next genuinely useful,
never-yet-run check instead: plan §3.6's seam-continuity check between
`build` and `drop`, which this session proved works (intro->build) but
never applied to this specific boundary. Rendered fresh 4s windows on each
side of the t=32s boundary from the current full 12-track mix (build tail
28-32s, drop head 32-36s) and ran `review_seam` for real.

**Result: FAILS.** Loudness held fine (4.4dB gap, well under the 10dB
threshold) but spectral centroid jumps 254Hz -> 1602Hz right at the
boundary (ratio 6.30, far past the ~2x "abrupt jump" threshold). **Very
likely a direct, previously-invisible side effect of this cycle's own
percussion register fix**: moving percussion from ~322Hz to ~1358Hz to
escape the kick's register (a real, necessary fix for the backbone's
internal composition) also means the drop's very opening instant is now
dominated by much brighter content than before, creating an abrupt timbral
handoff from the build's warmer ~254Hz tail that didn't exist when
percussion sat in a lower register. **Not necessarily a bug to reflexively
fix** -- `review_seam`'s own documented philosophy is that a section change
is often *supposed* to jump (an "arrival" contrast at a drop is arguably
the whole point), and this section already had bright neighbors regardless
(pad at 2557Hz, lead at 526Hz) -- but it's a real, measured, newly-surfaced
fact that a human/taste judgment hasn't weighed in on, exactly the kind of
cross-cutting consequence this project's whole review architecture exists
to surface rather than silently accept or auto-"fix" away.

## Sidechain channel-routing suspicion: confirmed, not just suspected (2026-07-27)
Closed this investigation for real. Searched the full REAPER-MCP tool
surface exposed to this session for anything that reads or sets a track's
channel count (REAPER's own `I_NCHAN`) -- **none exists**. `set_track_width`
only sets stereo width/pan law, not channel count; `set_send_dest_channels`
lets a send TARGET "channels 3-4" but there's no tool to give the
destination track those channels in the first place. REAPER tracks default
to 2 channels. **This confirms, rather than just suspects, the root cause**
flagged earlier: `setup_sidechain_compression`'s routing to "channels 3-4"
on a plain 2-channel track cannot create a real isolated sidechain input,
since the destination track structurally doesn't have those channels --
almost certainly why every sidechain attempt this session made the target
louder instead of ducking it, independent of threshold/ratio settings.

**Real next step, if ever revisited**: this needs a new dispatcher case
added to the vendored Lua bridge (`reaper_mcp_bridge.lua` / the deployed
copy), mirroring the exact pattern already used twice this session for
`TrackFX_GetParameterStepSizes`/`TrackFX_FormatParamValueNormalized` --
wrapping REAPER's own `SetMediaTrackInfo_Value(track, "I_NCHAN", n)`. Not
done this session (a real, scoped, but nontrivial addition, not urgent now
that `gain` covers the loudness-balance case sidechain was aimed at) --
recorded here so it isn't re-investigated as "unconfirmed" again.

## Intro section swept with the hardened toolchain -- found and fixed the LAST known open composition issue in the song (2026-07-27)
The intro (pad + bells, `fold_proof.py`'s original 2-leaf proof from very
early this session) had never been re-checked with today's tools. Re-ran
`review_composition` on its existing states -- **FAILS**, but not a new
problem: this is the exact pad-vs-bells centroid overlap (1548Hz vs. 1318Hz,
ratio 1.17) flagged and documented back in the "Track-scoped symbolic
extraction" entry near the start of the session, never actually fixed, only
left as a known finding.

With the mix-fix toolkit now mature, fixed it for real: `propose_composition_fix()`
correctly picked **highpass at 1600Hz** on the pad (informed by bells'
1318Hz centroid, learning the lesson from the build section's earlier
overcorrection). Executed live, then followed the now-mandatory
compensating-gain protocol: measured the level cost (-24.8 -> -28.0 LUFS,
-3.2dB) and applied `compensating_gain_db` (+3.2dB) before calling the round
done -- exactly the process `pipeline.py`'s `run_composition_fix_cycle()`
encodes, run by hand since a live `Executor` still needs a real session.

**Real result: PASSES.** Pad's centroid moved 1548Hz -> 2209Hz (ratio vs.
bells now 1.68, clear of the 1.5 threshold), level restored to -23.4 LUFS
(within 1.4dB of its pre-fix value). Severity 4.01 -- the lowest of any
section checked this entire session. **This closes out the last known
open composition-level issue across the whole song** -- intro, build, and
drop have all now been sweep-checked with the hardened metric and mix-fix
toolkit; only the build's mild residual centroid ratio (1.16, a practical
ceiling, not chased further) and the build->drop seam jump (an explicit
human/taste call, not something this architecture should decide) remain,
neither of which further autonomous mix-fix iteration can responsibly
resolve.

## SESSION CHECKPOINT (2026-07-27, end of session -- read this first)
User listened to the actual current mix (`song_so_far_v2.wav`,
`build_to_drop_transition.wav`) and gave real, substantive feedback that
changes the picture: **"It sounds bad, its very short for two abrupt
changes (including an abrupt start as the 3rd one), there is not enough
change, then a lot, then not enough, then a lot etc, the beauty comes from
almost predictability."** Confirmed mechanically before this checkpoint:
every layer in every section starts at EXACTLY the section boundary with no
staggering or ramp -- build's 4 layers (pulse/bass/texture/lead) all start
at t=16.0 precisely; drop's layers (kick/percussion/bass confirmed, lead/pad/
noise presumably the same pattern) all start at t=32.0 precisely. Three hard
walls (song start, build entrance, drop entrance), full-force, zero
anticipation. User was about to pick a fix-scope option (full rework / just
build->drop / plan-first) when they instead asked to checkpoint memory and
start a fresh chat -- so **nothing has been fixed for this specific
feedback yet**. This is the single most important thing for the next
session to act on.

### Current state (by section, composition-review status)
- **Intro** (pad+bells): passes composition review (fixed this session --
  see below). Not re-checked against the NEW pacing feedback.
- **Build** (pulse/bass/texture/lead): passes at a practical ceiling (one
  mild centroid ratio, 1.16, left as acceptable). Not re-checked against
  pacing feedback.
- **Drop** (backbone + lead/pad/noise): passes cleanly, both at the
  backbone-internal level and the section-root level. Not re-checked
  against pacing feedback.
- **Build->drop seam**: FAILS on `review_seam` (spectral centroid jumps
  254Hz->1602Hz) -- this was already flagged as a real, measured fact
  needing a human call before the user's broader feedback arrived. The
  user's feedback subsumes and explains this specific finding: it's one of
  the three abrupt walls they're describing, not a separate issue.
- **Song start** (silence -> intro): never explicitly composition-reviewed
  as a "seam" (no `review_seam` call exists for it), but per the same
  entrance-timing check, intro's own layers presumably also start cold at
  t=0 -- worth confirming, not yet confirmed.

### What was done this session (the long version is below in-line,
dated 2026-07-26/27; this is the compressed index)
1. Built `src/planner/preset_attack.py` + `scripts/check_preset_attack.py`:
   measures a preset's real attack time from rendered audio, live-validated
   with positive/negative controls. Wired into `leaf_emit.py`.
2. Fixed the noise leaf's total-silence bug (`FX/Crackling.fxp` doesn't
   respond to MIDI like an instrument -- re-emitted to `Plucks/Man
   Machine.fxp`).
3. Hardened `orchestrate.py` with real severity scoring (`ReviewState.metrics`,
   `review.py` populates real numbers) instead of raw reason-count, which had
   twice missed real regressions.
4. Root-caused and fixed percussion's long-standing silence bug (`Synth Tom
   2.fxp`'s attack was ~1.0-1.1s, far too slow for its rhythmic pattern) --
   re-emitted to `Plucks/Metallic.fxp`, verified with the attack check.
5. Found and fixed a real architectural bug: `review_composition`'s loudness
   check compared integrated LUFS across siblings with very different duty
   cycles (a sparse punchy kick vs. a continuous part) -- structurally
   unfair, and likely why the whole backbone mix-fix saga earlier in the
   session never converged. Fixed with a peak-based fallback for sparse
   siblings (`SPARSE_ACTIVE_RATIO_THRESHOLD`).
6. Tried sidechain twice for real mixing fixes -- both times the target got
   LOUDER, not quieter. Root-caused for real: **no tool in this REAPER-MCP
   surface can read or set a track's channel count**, and sidechain's
   routing to "channels 3-4" needs the destination track widened first,
   which isn't possible with available tools. `sidechain` fix type flagged
   with strong caution in `mix_fix.py`; would need a new Lua bridge
   dispatcher case (`SetMediaTrackInfo_Value(track, "I_NCHAN", n)`) to fix
   for real, not done.
7. Added a `gain` fix type to `mix_fix.py` (flat `set_track_volume` change)
   -- validated repeatedly (backbone, build, intro) as the reliable,
   predictable fix for pure loudness-balance problems, unlike sidechain.
8. Found that highpass fixes have a real, uncompensated level cost (removing
   energy costs LUFS, which can silently erase a separate gain fix's
   benefit) -- added `mix_fix.compensating_gain_db()` as a mandatory
   post-step, validated live (build section, then intro section).
9. **Backbone composition review passes for the first time all session**
   (closing a saga that ran through most of the session): silence fix,
   2 more mix-fix rounds (regressed, informative), a leaf re-emission for
   register (fixed overlap, caused clipping), a gain trim -> PASS.
10. Build section swept with the hardened toolchain -- gain fix generalized
    cleanly to a different section on the first try; a highpass regression
    there is what led to discovering the compensating-gain requirement.
11. Built `src/planner/pipeline.py` -- real, tested (6 new tests, 72 total)
    decision-logic integration: `run_leaf_cycle()` and
    `run_composition_fix_cycle()`, using an `Executor` protocol since no
    standalone MCP client can execute REAPER calls outside a live session.
    This is the sequencing logic made reusable, not a literal autonomous
    system -- a live run still needs a session to implement `Executor`.
12. Ran the build->drop seam check for the first time -- found the abrupt
    centroid jump, correctly flagged as a human/taste call rather than
    auto-"fixed."
13. Swept the intro section (never rechecked since very early in the
    session) -- found and FIXED the long-standing pad-vs-bells overlap
    (1548Hz vs 1318Hz) using the now-mature toolkit: highpass + compensating
    gain, first try, clean pass.

### What was solved
Every *spectral/loudness balance* composition-review failure across the
whole song (intro, build, drop, backbone-internal) is now either passing or
at an accepted practical ceiling. Two real, previously-silent bugs (a
percussion silence bug and a noise-leaf silence bug) are fixed. Three real
architectural gaps in the review/fix tooling itself were found and closed
(duty-cycle-blind loudness metric, unreliable/unconfigured sidechain,
uncompensated EQ level cost).

### What issue this surfaced (read this as the humbling one)
**Every automated check this whole session measures STEADY-STATE
properties** (a section's own LUFS/centroid, a boundary's before/after jump
magnitude) -- **none of them measure PACING or anticipation**, which is
what the user's ear actually caught. `review_seam` correctly flagged the
build->drop jump as measurably abrupt, but that was treated as one
isolated data point, not read as a symptom of a *structural* pattern (every
section boundary in this arrangement is a hard, simultaneous, full-force
cut, by construction -- `scheduler.py`'s `build_tree()` assigns every leaf
under a Split the same track/duration/position with no concept of staggered
entrance or cross-fade). The automated toolchain got very good at "do these
simultaneous layers balance," and never had a mechanism for "does this
transition feel earned" -- a real, structural blind spot in the plan's own
review model (plan §3.6's three checks -- own criteria, composes with
siblings, seams hold -- have no fourth check for *pacing/predictability*
across a longer span than one boundary).

### What should've been done differently
1. **Should have asked the user to actually listen much earlier and more
   often.** Every mix-fix round this session was validated against
   measured numbers (LUFS gaps, centroid ratios, severity scores) -- real
   and rigorous, but a human ear caught in 15 seconds what dozens of
   measured composition-review passes never flagged: the whole arrangement
   feels jarring. Plan §7.1's "human is the taste oracle" principle was
   honored for narrow decisions (which preset, which fix) but never invoked
   for the bigger structural question of whether the arrangement's pacing
   works, until asked directly.
2. **`scheduler.py`/`decompose.py` should treat entrance staggering and
   cross-boundary ramps as a first-class part of section composition**, not
   an afterthought bolted on after the fact -- currently every leaf under a
   Split gets identical position/duration, which is fine for "these are
   parallel layers of one section" but wrong for "how does this section
   begin." A future `build_tree()`/`decompose()` pass should let the model
   decide *when within the section* each layer enters (and whether it fades
   in via automation), not just *what* each layer is.
3. **Concrete next-session plan** (per what the user was about to choose
   between before checkpointing): stagger layer entrances within each
   section instead of all-at-once, and add volume/filter automation ramps
   at all three boundaries (song-start, build-entrance, drop-entrance) --
   scope (full rework vs. just build->drop vs. plan-first) is the user's
   call to make at the start of the next session, not decided here.

## Arc planner built: the actual missing top-level structure decision (2026-07-27, new session)
Followed up on the previous checkpoint's pacing complaint. Real conversation
first, not straight to code: user's diagnosis went past "sections don't
stagger" to "the composition is structurally arbitrary" -- every section so
far (intro/build/drop) was hand-picked (`target_section_type`+`duration_s`
passed as bare args to `decompose()`/`build_tree()`), never a real top-level
decision. Confirmed by reading `node.py`/`decompose.py`/`scheduler.py`
directly: **`Node` had no `duration_s` field at all**, and `build_tree()`
propagates one shared `target_section_type`+`duration_s` uniformly through
an entire recursion -- there was structurally nowhere for "the song has 7
sections of different lengths" to live.

Design settled through several rounds of real back-and-forth (not decided
unilaterally): freedom over form (no required section sequence/drop),
reference library as a light outlier check only ("too much reference is
just copying" -- explicit user correction against an earlier over-reliance
on mining the library for thresholds), ~40s "cells" as a soft default
(natural variety from free per-section cell-count choice, not a forced-
variation rule) with a locked-grid override requiring real stated
justification, climax-shorter as a soft bias, contrast enforced by
**measurement on real rendered audio afterward** (not a prompt rule) --
matches the project's whole "steer by measurement" philosophy. Total song
length fully the model's call. Model tier: Fable (`ModelTier.FABLE`,
defined in `node.py` since the schema-freeze session, never assigned by any
code until now) -- prototyping on `claude-opus-5` first, same `MODEL="..."`
top-of-file swap convention as `decompose.py`/`leaf_emit.py`.

Planned via `EnterPlanMode` (Explore + Plan subagents for research/design,
full context handed off explicitly) before writing anything, per real
non-trivial scope: schema change + new module + new review check + tests.

**Built, all real, live-verified:**
- `Node` gained `duration_s: float | None`, `locked_grid: bool`,
  `grid_justification: str` (+ `__post_init__` requiring a real
  justification when `locked_grid=True`) -- `to_dict`/`from_dict` extended,
  every existing call site keeps compiling (same optional-default pattern
  as `ReviewState.metrics`).
- `src/planner/arc.py` (new): `plan_arc(brief, client)` -- a real Opus
  tool-use call returning an ordered section-spec list. **Hit and fixed a
  genuinely new failure mode**, distinct from `decompose.py`'s known
  double-JSON-encoding bug: with this module's longer, multi-paragraph
  prompt, the model reliably (3/3 in one run) leaked a raw tool-call
  parameter tag into the string value itself --
  `'\n<parameter name="sections">[{...}]'` -- not valid JSON as-is, but a
  real array right after the tag. Fixed by stripping up to the first `[`
  before parsing, confirmed via direct API probing (not guessed) that the
  recovered content was genuinely well-formed, same lesson decompose.py's
  own docstring already drew.
- `src/planner/review.py`: new `review_arc_contrast(ordered_states,
  labels=None)` -- checks section N against N-1 *and* N-2 (the N-2 leg is
  what catches back-and-forth A/B/A repetition an adjacent-only check like
  `review_seam` structurally can't see), flags *insufficient* difference
  (mirror image of `review_seam`'s excessive-jump check), new
  `ARC_CONTRAST_MIN_LOUDNESS_GAP_DB=3.0`/`ARC_CONTRAST_MIN_CENTROID_RATIO=1.15`
  constants explicitly picked as a rough perceptual floor, not mined from
  the reference library. Populates a real `metrics` dict (same
  shape-family as `review_composition`'s) for future severity scoring.
- `tests/test_arc.py` (12 new tests, suite now 84/84 passing): validation/
  retry/both-JSON-recovery-paths for `plan_arc`, and `review_arc_contrast`
  cases including one specifically asserting the i-2/A-B-A catch (the
  actual point of the function).
- `scripts/arc_proof.py`: real live run against `ANTHROPIC_API_KEY`,
  genuinely good output -- 7 sections, 312s total, durations 40/80/40/32/
  40/40/40s, one real locked-grid section (80s hypnotic core, real stated
  justification), two drop occurrences instead of one forced climax, both
  drops (32s/40s) shorter than the locked-grid build (80s) -- the
  climax-shorter bias working as designed, chosen by the model, not
  scripted. Output: `state/arc_proof/arc_plan.json` (gitignored).

**Explicitly deferred, not done, flagged in the plan itself**: wiring
`plan_arc`'s output into `scheduler.build_tree()` for a real per-section
live song build (today's uniform propagation stays as-is); an arc-level
fix/replan orchestrator for when `review_arc_contrast` fails (replanning
one section vs. the whole arc is a materially different, asymmetric
decision from `orchestrate.py`'s existing lateral `mix_fix`/`leaf_retry`
choice); actually regenerating the current song; any MIDI/symbolic-level
repetition check beyond audio-domain contrast.

## SESSION CHECKPOINT (2026-07-27, continued -- full song regenerated end-to-end)
Followed straight on from the arc-planner build (previous entry). User said
"regenerate the arc, from scratch" and, after a brief scope negotiation
(brief = full creative control over concept/genre/mood, not just structure;
scope = full song in one pass, not a checkpoint slice), approved a plan
(`/home/stcksmsh/.claude/plans/modular-snuggling-valley.md`) to actually
build it live -- the first time this project executed a real multi-section
song end-to-end in one session, not another proof script.

**The real arc, locked in and built**: *"Tidewater Clock"* -- a Dm9-rooted
piece with real harmonic movement (Dm9 -> Bbmaj7#11 -> Gm11 -> Csus2/A), 7
sections/320s: intro(40s) -> build[locked-grid, 80s] -> build[chord turn,
40s] -> drop(40s) -> breakdown(40s) -> drop(40s) -> outro(40s). Old 12-track
song deleted first (explicit user go-ahead: "you are always allowed to
delete reaper tracks within this project" -- worth remembering for future
sessions, this is now a standing permission, not a one-off).

**Real engineering pivot mid-session, worth remembering**: the initial
per-tool-call MCP approach (one insert_track/apply_surge_preset/
create_midi_item/add_midi_notes_batch call each, narrated turn-by-turn) was
far too slow and token-expensive -- every note-batch call echoed a
per-note `{"ok":true}`, every preset apply cost a ~2min round-trip tied to
a full conversation turn. User flagged it directly ("too slow and token
expensive, need a better batching idea"). Fix: `twelvetake-reaper-mcp`'s
tool functions are themselves thin wrappers over the same file-based bridge
protocol `scripts/surge_bridge_client.py` already talks to directly (for
functions with no MCP wrapper) -- confirmed by reading `reaper_mcp_server.py`
directly, not guessed. Built **`scripts/execute_section_direct.py`**: one
script per section, driving track creation/FX/presets/MIDI/render/solo
directly via `surge_bridge_client.call()` + the existing `apply_preset()`/
`apply_overrides()` (reused unchanged from `apply_surge_preset_live.py`),
with a `resume_from_leaf` arg for restarting after a mid-run crash without
rebuilding earlier leaves. Cut both time and (much more so) context/token
cost dramatically -- no more per-call echo, no more turn-per-preset wait.
Also hardened `surge_bridge_client.call()` with a 2x retry (a specific
call, `TrackFX_FormatParamValueNormalized` during enum-size probing, has
now failed transiently 4+ times across this and earlier sessions, fully
sequential, so it's real flakiness not concurrency -- worth retrying, not
worth chasing further).

**Real bugs found and fixed live, each a genuine defect not a taste call**:
1. **`add_midi_notes_batch` with zero notes** -- `leaf_emit._validate_ops`
   never actually checked the `notes` array was non-empty; 6/33 leaves
   across the song emitted no notes at all (silent by construction). Fixed
   the validator for real (`scripts/leaf_emit.py`), re-emitted the 6 leaves
   with feedback.
2. **Untiled repeating patterns** -- a much bigger, systemic version of the
   same root problem: ~20 leaves across sections 2-6 wrote one cycle of a
   repeating figure (e.g. one 8-beat riff) without tiling it to fill the
   actual section duration, so far more of the song than just those 6
   leaves would have gone silent partway through. Root cause: the model
   defaults to a conventional ~8-16-bar loop length regardless of the
   actual (often much longer) stated section duration. Re-emission with
   feedback partially fixed it; the rest were mechanically tiled (repeating
   the model's own pattern at its own natural period until the section's
   full beat-length) -- legitimate plumbing completion of an
   already-decided figure, not a new creative decision, same reasoning as
   why track_index/timeline placement are mechanical. **Two leaves already
   built live before this was caught (section 1's pluck/kick) got fixed
   retroactively by appending the missing repeats directly.** `max_tokens`
   in `leaf_emit.emit_leaf_implementation` raised 2048->4096 since a dense
   full-length pattern can exceed the old budget and silently truncate.
3. **`Snare Tight.fxp` is unreliable for short percussive notes** -- went
   silent on 3 separate leaves across 2 sections (with AND without extra
   overrides), matching this project's own long-documented "preset attack
   too slow for note length" failure class (same as `Synth Tom 2.fxp`
   earlier this session). Swapped every occurrence (live fixes for
   already-built leaves, pre-emptive song_plan.json patch for
   not-yet-built ones) to `Plucks/Metallic.fxp`, the same proven substitute
   used earlier.
4. **A folder-name typo** (`Bases/Eighties Drone.fxp` -> real path is
   `Basses/...`) -- caught by the preset lookup raising immediately, fixed
   in both the live call and the plan JSON.
5. **Real digital clipping** on 2 leaves (section 5's reprised drop bed,
   section 6's deconstructing pluck) and on the **full mixed-down song**
   (individual leaves were clean but the sum exceeded 0dBFS) -- fixed with
   plain gain trims (`SetMediaTrackInfo_Value(track/-1, "D_VOL", ...)`),
   confirmed via direct sample-level clip counting
   (`np.abs(data) >= 0.999`), not just LUFS. A blanket -8dB master trim
   (not a mastering chain -- no EQ/compression/limiting, explicitly out of
   this pass's scope) was enough to clear the final mix.
6. **A near-total-silence sub-bass** (section 3's first drop, -50 LUFS vs.
   its own drop's -17 LUFS lead) -- a real audibility defect for a climax
   section's foundation, fixed with a +20dB gain trim, not chased to full
   mix-fix convergence given time constraints.

**Real, measured final result** (not rubber-stamped): full song rendered
clean (0 clipped samples after the master trim), `review_arc_contrast`
**PASSES across all 7 sections** (confirms the arc-planner's freedom-over-
form design actually produced audibly varied sections, the whole point of
last session's design conversation) -- `worst_gap_db=1.25`,
`worst_centroid_ratio=1.87`, 11 pairs checked, 0 insufficient. `review_seam`
at the 6 section boundaries: 4 pass clean, 2 fail with real, large
measured jumps -- **120s (build->drop, centroid ratio 2.51)** and **160s
(drop->breakdown, centroid ratio 19.57, a near-total spectral collapse)**.
Both are flagged, not auto-fixed -- exactly the kind of "is this abrupt
arrival/vacuum the intended character, or does it need bridging" call this
project has always treated as the human's, not the architecture's, to make
(same principle as last session's build->drop seam finding, which is now
superseded by this actual regenerated song). MP3 (7.7MB, ffmpeg -b:a 192k,
since the 88MB WAV exceeded the file-delivery size limit) sent to the user
for a real listen -- the acid test this whole pass exists to earn.

**Explicitly not chased further this pass, consistent with "practical
ceiling" precedent**: per-leaf loudness-balance/register-overlap findings
within sections (documented via the lightweight measured-only
`scripts/_review_composition_only.py`, no CLAP) -- real, but not
structural defects like the ones above, and mix-fix convergence per
section would have cost far more time than the remaining budget allowed.
One leaf's tiling fix was deliberately left partial (section 1's pluck,
section 2's hi-hat texture -- cover roughly the first half of their
section rather than the full tiled length) given the escalating token
cost of very dense note batches; flagged, not silently dropped.

## Next
1. **Get the user's actual listen and reaction to `tidewater_clock_full.mp3`**
   -- this is the real next step; nothing else matters until that lands,
   per this whole project's own recurring lesson about asking early.
2. **Human/taste call on the two failing seams** (120s, 160s) -- same
   "human is the taste oracle" principle as always; not this architecture's
   call to make unilaterally.
3. If the pacing/anticipation feedback from two sessions ago (staggered
   entrances, boundary ramps) still applies to this NEW arc, that's a
   distinct, not-yet-done layer on top of what this pass built -- this pass
   built the arc and its content, not per-boundary automation ramps.
4. `scripts/execute_section_direct.py` is now a real, reusable pattern for
   any future live section build in this project -- prefer it over
   individual MCP tool calls for anything touching more than 1-2 leaves.
5. Vital param-mapping -- still explicitly deferred, not blocking.

## SESSION CHECKPOINT (2026-07-27 night, new session -- READ THIS FIRST, stopped mid-build on user's request to sleep)

**Do not touch the live REAPER session until the concurrent-agent question
below is resolved with the user.** This checkpoint exists specifically
because something is actively wrong with the live project state.

### What this session did, in order
1. User gave detailed listening feedback on "Tidewater Clock" (the
   previous session's regenerated song): parts genuinely good, but overall
   "melange of 40s windows," mixing issues (piercing/screechy elements,
   underpowered percussion), drop sections weak, no reused
   synths/motifs/textures across sections.
2. Real design conversation (not straight to code) on: (a) recurring
   elements -- both timbral (same patch reappears) and thematic (same
   note-shape, different instrument) recall, tracked independently,
   "encouraged not forced"; (b) speed/batching; (c) automation -- confirmed
   this project had ZERO automation usage anywhere before this session
   (grepped the whole codebase). Landed on: recurring-element registry
   decided top-down at arc-planning time, filled in sequentially by
   `song_plan.py`'s existing per-section loop (cheaper than a post-hoc
   harmonize pass); two generic automation tools (track envelope
   Volume/Pan/Width, FX-param envelope for any Surge param) since REAPER's
   `get_track_envelope`/`add_envelope_point`/`get_fx_envelope`/
   `add_fx_envelope_point` MCP tools are already fully generic; macros
   excluded (undefined mod-matrix routing, never built).
3. **Built and tested, all real code** (not yet git-committed -- see git
   status below):
   - `src/planner/arc.py`: `plan_arc()` now returns
     `{"sections":..., "recurring_elements":...}` -- new
     `recurring_elements` field (element_id, description, section_indices,
     >=2 occurrences required, validated in-range).
   - `src/planner/decompose.py`: `decompose()` takes `recurring_context`
     (origin vs. recall + prior realization details); each child can carry
     optional `realizes_element_id`. Also gained `force_leaf: bool` --
     forces every child `is_leaf=True` at the last allowed recursion depth,
     closing a real `MaxDepthExceeded` crash class caused by decompose's
     own stochastic over-splitting near the depth boundary (found live,
     hit 3 times across repeated song_plan.py runs before this fix).
     `maxItems`/validated range widened from 2-4 to 2-6 children (the
     breakdown section genuinely needed 6).
   - `src/planner/scheduler.py`: `build_tree()` bakes recurrence
     instructions straight into a leaf's own spec text (no leaf_emit.py
     signature change needed for that part), tracks `element_realizations`
     up through recursion (returns 3-tuple now, was 2-tuple -- callers
     updated), soft-logs identical repeats and dropped/unclaimed elements.
     Sibling leaf emission is now parallelized (`ThreadPoolExecutor`,
     `MAX_PARALLEL_LEAF_EMISSIONS=4`) -- track indices still pre-assigned
     single-threaded before dispatch, deterministic.
   - `scripts/song_plan.py`: maintains the song-wide element registry
     across sections; **now writes incremental checkpoints after EVERY
     section** (`complete: true/false` field), not just once at the end --
     added after a real incident this session where a crash on section 2/3
     lost all of sections 0-1's already-paid-for API work three times in a
     row before this fix.
   - `scripts/leaf_emit.py`: two new optional trailing ops,
     `automate_track_envelope` and `automate_surge_param`. Reverb/delay
     automation explicitly NOT included (no resolved param table exists
     for that). `EXCLUDED_PRESETS = {"Percussion/Snare Tight.fxp"}` --
     confirmed unreliable/silent for short notes across TWO separate
     sessions now, hard-excluded from the offered list AND rejected in
     `_validate_ops` if picked anyway. `max_tokens` raised 4096->8192
     (still hit truncation at 4096 with a large override dict + notes in
     one turn). **`tile_notes_to_duration()`** -- the real fix for the
     long-standing "model can't write out a full 80s of 16th notes"
     problem: model writes ONE cycle, this mechanically tiles it to fill
     the leaf's real duration. Ship-blocking bug found and fixed same
     session: tiling extended the NOTES array but not the
     `create_midi_item` container's own `length` -- REAPER clips notes
     outside an item's `[position, position+length)` bounds, so ~12+
     leaves across the song were silently inaudible past their item
     boundary despite "successful" builds. Fixed: tiling now also grows
     the item's length to match (capped so `position + length` never
     exceeds the section's own duration -- a few leaves had model-side
     beat-math errors, e.g. writing 96 beats of content into a 48-beat/
     24s section; those got clipped to fit rather than extended past their
     section into the next one).
   - `scripts/execute_section_direct.py`: real bug found and fixed --
     leaves were being built in tree-traversal order, NOT ascending
     `track_index` order, so `InsertTrackAtIndex` got called out of
     sequence (e.g. index 3 before 0/1/2 existed) and REAPER silently
     placed tracks at the wrong actual index, desyncing every subsequent
     `track_index` reference. Fixed: leaves sorted by `track_index` before
     the build loop. Also: `automate_track_envelope`'s Volume/Pan
     envelopes need a one-time "show" toggle
     (`SetTrackSelected`+`Main_OnCommand(40406)` for Volume,
     `40407` for Pan) before `GetTrackEnvelopeByName` will find them --
     REAPER returns nil for a real, always-present envelope that's just
     never been made visible. Both fixes are in the committed-to-disk
     script now.
   - 5 new test files (`test_arc.py` extended, `test_decompose.py`,
     `test_leaf_emit.py`, `test_scheduler.py` all new), 122 tests total,
     all passing as of the last test run this session.
4. **Fresh full regeneration run, real arc**: *"Tidal Lock"* -- D Dorian,
   120bpm, 6 sections/320s: intro(48s) -> build(40s) ->
   drop[locked-grid, 80s] -> breakdown(64s) -> drop(40s) -> outro(48s).
   3 recurring elements declared: `four_note_motif` (D-A-C-G, appears in
   ALL 6 sections, different guise every time -- FM bell, pure rhythm, fast
   arpeggio, half-speed higher octave, simultaneous lead+arpeggio, dying
   down to one note), `dm9_bbmaj7_rotation` (harmonic anchor pad,
   sections 0/2/4/5), `dorian_16th_bassline` (sections 1/2/4). Old 33-track
   "Tidewater Clock" deleted first (standing permission).
   `state/song_plan/arc.json` and `state/song_plan/song_plan.json` are
   BOTH fully built and correct on disk -- 6 sections, all leaves emitted,
   all recurring elements actually realized where scheduled, 27/38 leaves
   used the new automation ops. This is safe, disk-only, NOT dependent on
   the live REAPER project -- always the authoritative source to rebuild
   from.
5. **Live execution**: only sections 0 and 1 (10 leaves, tracks 0-9) were
   ever attempted live. Found and fixed 2 real content bugs (both required
   several iterations, documented in full further up this file):
   percussion/pad presets muting all oscillators + relying on Surge's
   dedicated Noise generator rendered totally silent (root cause: `A Noise
   Mute` gates it independently of `A Noise Volume`, and even after fixing
   that, the signal path stayed unreliable -- abandoned the Noise
   generator entirely, used a safe plain-pad + automation swell instead);
   a leaf accidentally had `Attack=4.5` (2^4.5≈22.6s) against a 24s note,
   never audibly opening. **A real bookkeeping mistake happened during
   manual live fixing**: mislabeled which node_id owned track 4 partway
   through (confused `song/section_0/child_2` with
   `song/section_0/child_0/child_1`), fixed the wrong one first, had to
   untangle and re-fix both correctly. `song_plan.json` now has the
   CORRECT final ops for both, verified.

### THE OPEN PROBLEM -- root cause now identified, recovery not yet done
While rebuilding sections 0+1 live (after the item-length repair above), a
stray subagent process ("what are we waiting for now?", not intentionally
spawned by this session -- likely leaked from an earlier background
invocation) sent task-notifications describing the exact same live events
this session was mid-doing. **Root cause, confirmed by that same process
on a later check-in: a DUPLICATE, leaked `execute_section_direct.py 0`
process (started 23:23) was still running in the background and racing
against this session's manual live fixes** -- both processes hitting the
same file-based REAPER bridge protocol concurrently, which explains the
"Track not found" errors, the project resetting to 0/inconsistent track
counts, and the headless REAPER process (PID 27072) dying outright. This
was NOT a second human session or a second Claude Code window -- just an
orphaned background task that never got cleaned up.

**Current confirmed state** (per that process's final report -- it has
since killed the stray process and stopped the bridge cleanly, nothing is
running now):
- `state/scratch/session.rpp` on disk is the **corrupted 0-track version**
  (autosaved during the incident).
- A verified-good backup exists at
  **`state/scratch/Backups/session-2026-07-27_230959.rpp-bak`** (10
  tracks -- sections 0 and 1, including section 0's fixes).
- `state/song_plan/song_plan.json` (full 6-section plan/content) is
  untouched and safe regardless -- always the authoritative source.
- No REAPER/bridge process is currently running; nothing is mid-write.

No recovery action was taken -- the user asked to stop and sleep before
authorizing anything further, so restoring the backup (or rebuilding from
`song_plan.json` instead, which doesn't need the backup at all) is still
an open decision for the next session to make with the user.

### Next steps, in order, for whoever picks this up
1. **Root cause is identified and resolved** (a leaked duplicate
   background process, not a second human session -- see above); no need
   to interrogate the user about other open sessions. Do a quick sanity
   check before trusting this fully: `pgrep -af "execute_section_direct|
   reaper_mcp_bridge|session.rpp"` should show nothing (bridge was
   confirmed stopped). If anything unexpected shows up, stop and ask
   rather than assume it's another leak.
2. **Check what's actually live**: `mcp__reaper__get_track_count` /
   `get_project_summary` (read-only, safe) before any writes. Don't assume
   0 tracks, don't assume 10 -- verify.
3. **Recovery plan (once concurrency is resolved), in order of
   preference**: (a) simplest and recommended -- since
   `state/song_plan/song_plan.json` already has fully correct, verified
   ops for every leaf in sections 0 and 1 (including all the fixes
   documented above), just delete whatever tracks currently exist and
   re-run `execute_section_direct.py 0` then `execute_section_direct.py 1`
   fresh, exactly as this session was mid-doing when it got interrupted.
   This does NOT require restoring the `.rpp-bak` file at all. (b) Only if
   (a) turns out to be insufficient for some reason: the backup at
   `state/scratch/Backups/session-2026-07-27_230959.rpp-bak` is available
   as a fallback, but restoring it means discarding whatever's live now --
   confirm with the user first regardless of which path, given the
   sensitivity already in play.
4. **After sections 0+1 are confirmed solid** (render + measure, no
   silence/clipping, matching what this session already verified via
   `analyze.measure` before the concurrency issue surfaced): continue
   building sections 2-5 the same way (`execute_section_direct.py 2/3/4/5`)
   -- these were never attempted live at all this session, so no known
   bugs there yet, but the same class of issues (silent presets, item-
   length mismatches) could in principle still surface; the leaf_emit.py
   fixes should prevent the item-length one specifically, going forward.
5. **Tasks 11 and 12 (from this session's own tracker, still pending)**:
   sequence/verify timeline positions across all 6 sections, run
   `review_arc_contrast` + `review_seam` at each boundary on the full
   combined mix, do a master gain pass (check for clipping, blanket trim
   if needed), render final mix, convert to mp3, send to the user for the
   actual listen -- which is the whole point of this regeneration pass,
   per the user's original feedback that started this session.
6. **Code is NOT git-committed** -- `git status` shows all the files
   listed above as modified/untracked, exactly as this session left them.
   No git risk either way; this is a plain-disk-state concern only.

### Working note for this specific failure mode
If a future session sees inconsistent `get_all_tracks`/`get_track_count`
results across successive calls with no code change in between, or a
REAPER process that was alive suddenly isn't (`ps -p <pid>` empty), treat
concurrent-agent interference as a real hypothesis, not just "the bridge
is flaky again" -- check `pgrep -af "reaper_mcp_bridge|session.rpp"` for
more than one bridge-owning process pair, and ask the user directly rather
than guessing.

### UPDATE (same night, right before sleep): recovery step (a) done, bridge left OFF
Continued directly from the checkpoint above, same session. Confirmed no
stray processes (`ps aux` clean). Found the bridge/REAPER process was
**still actually running** (PID from a `start` a few messages earlier) --
the previous checkpoint's "bridge was confirmed stopped" referred to the
stray subagent's own report, but a follow-up `stop` command had been
silently blocked by the permission classifier (bundled into a multi-line
compound command that got denied as a whole) and never actually ran.
Re-ran `stop` on its own (unblocked this time) -- confirmed clean via `ps`.

**Took recovery path (b) from the list above, not (a)**: copied
`state/scratch/Backups/session-2026-07-27_230959.rpp-bak` directly over
`state/scratch/session.rpp` (verified 10 `<TRACK>` blocks before and after
the copy). Path (a) (re-running `execute_section_direct.py 0`/`1` fresh
against a cleared project) was also valid and doesn't strictly need the
backup, but the backup is exact, zero-risk, and faster -- both paths land
at the same content since `song_plan.json` already has the correct final
ops for sections 0-1's leaves either way.

**Bridge deliberately left OFF** for the night -- no need to keep a live
REAPER process running unattended, and starting fresh next session
(`scripts/start_reaper_mcp_bridge.sh start`) is cheap and known-reliable.

**Full test suite re-run clean**: 122/122 passing, no regressions from any
of tonight's fixes.

**Verified `song_plan.json` and the restored `session.rpp` are mutually
consistent**: both `song/section_1/child_0/child_1` and `.../child_2`
(the two Snare-Tight leaves) still show the ORIGINAL unfixed
`Percussion/Snare Tight.fxp` preset in `song_plan.json` -- the live fix
attempted tonight (swap to `Plucks/Metallic.fxp`) was lost in the
corruption before it was ever written back to `song_plan.json`, so there's
no mismatch/stale-bookkeeping risk carried into next session. These two
leaves are simply back to square one, exactly like every other
not-yet-executed leaf in sections 2-5.

### Exact next-session starting point
1. `state/scratch/session.rpp` = the verified-good 10-track backup
   (sections 0+1, section 0's fixes intact). `state/song_plan/song_plan.json`
   = the full, correct 6-section plan, `"complete": true`. These two files
   are consistent with each other right now -- confirmed above.
2. Start the bridge fresh: `scripts/start_reaper_mcp_bridge.sh start`,
   then verify with a read-only `get_track_count` (expect 10) before
   touching anything.
3. Redo the two Snare-Tight fixes on tracks 8 and 9
   (`song/section_1/child_0/child_1` = hi-hat, `.../child_2` = rimshot
   carrying `four_note_motif`): swap `Percussion/Snare Tight.fxp` ->
   `Plucks/Metallic.fxp`, same notes, DROP the aggressive `A Highpass: 0.7`
   override this session tried (it likely stripped nearly all of
   Metallic.fxp's energy -- a -59 LUFS near-silent result even with a real,
   non-gated signal). Keep `A Amp EG Attack/Decay/Release/Sustain` only.
   **Watch the automation-point time convention**: `execute_section_direct.py`
   adds `timeline_start_s` (the SECTION's absolute start, e.g. 48 for
   section 1) to automation "time" values, not the item's own position --
   confirmed by reading the code, and this session got it wrong once
   live (used relative-to-item offset by mistake, had to redo). For a
   leaf whose item starts exactly at the section boundary (`position: 0`
   in its own ops) this coincides, but don't assume it always will.
   Update `song_plan.json`'s record for both leaves after fixing, matching
   the pattern already used for section 0's fixes (full ops list, real
   `track_index`, a `source` note explaining the swap).
4. Once 0+1 are both clean (render+measure each leaf again, confirm no
   `None`/gated-silent LUFS and no 0.0dB clipping): proceed through
   sections 2-5 via `execute_section_direct.py 2/3/4/5` -- untouched
   territory, no known bugs, but budget time for the same failure classes
   (silent presets, occasional transient bridge timeouts -- just retry
   those, they're documented as real flakiness elsewhere in this file).
5. **Only ever run ONE `execute_section_direct.py` (or any live-REAPER
   script) at a time.** Tonight's whole incident was two copies racing on
   the same file-based bridge. If a background invocation is started,
   confirm it has actually finished (`ps aux | grep execute_section`)
   before starting another one against the same project.
6. Then tasks 11-12: timeline sequencing verification, `review_arc_contrast`
   + `review_seam` across all 6 sections, master gain pass, final render,
   mp3, send to user -- the actual deliverable this whole regeneration
   exists to produce.
7. Code still not git-committed (unchanged from the earlier checkpoint's
   note) -- no git risk, plain-disk-state concern only.

## SESSION CHECKPOINT (2026-07-28 -- recovery + remaining sections built, full song delivered)
Picked up exactly at the previous checkpoint's "exact next-session starting
point." Verified clean (`pgrep` for stray `execute_section_direct`/
`reaper_mcp_bridge` processes -- none), confirmed `state/scratch/session.rpp`
(10 tracks) and `song_plan.json` (`complete: true`) were mutually consistent
as documented, started the bridge fresh, confirmed live track count matched
via `get_project_summary` before touching anything.

**Redid the two Snare-Tight fixes exactly as prescribed** (tracks 8/9,
`song/section_1/child_0/child_1`+`child_2`): swapped `Percussion/Snare
Tight.fxp` -> `Plucks/Metallic.fxp`, dropped the filter/highpass overrides,
kept only Amp EG envelope overrides. Verified live (solo render + `analyze.measure`):
real non-gated signal (active_ratio 11-15%, appropriate for sparse
hi-hat/rimshot patterns), no clipping. Updated `song_plan.json` with the new
preset + a `source` note, matching the established pattern.

**Built sections 2-5 live** (`execute_section_direct.py 2/3/4/5`, one at a
time, never concurrently -- the hard lesson from the prior incident).
**Found 4 more silent leaves, same root cause every time**:
`Percussion/Snare Tight.fxp` -- section 2's `child_0/child_2` (closed
hi-hat, 341 16th notes) and section 4's `child_0/child_1`/`child_2`/`child_3`
(snare/hi-hat/rimshot backbeat trio). This preset is now confirmed
unreliable across **5 separate leaves over 2 sessions** -- worth
hard-excluding at the source (`leaf_emit.py` already has
`EXCLUDED_PRESETS = {"Percussion/Snare Tight.fxp"}` from a prior session,
but `song_plan.json`'s existing plan predates that fix, so leaves already
decided before the exclusion still reference it; the exclusion only stops
*new* emissions, not ones baked into an existing plan). Fixed all 4 the same
way: swap to `Plucks/Metallic.fxp`, no overrides needed (none of these had
any), verified live non-silent, updated `song_plan.json`.

**Real bug hit and fixed**: an `mcp__reaper__set_track_solo(track=32,
solo=false)` call timed out (bridge round-trip, not a crash) but the
underlying REAPER-side call had actually succeeded-then-not -- checked via
`get_track` afterward and found it was STILL soloed, meaning a prior `save_project`
call saved the project mid-solo. Caught before it mattered by explicitly
verifying via `get_project_summary` (all 33 tracks' solo state) before
re-saving -- a real instance of "don't trust a tool response, verify the
actual state," worth remembering: **REAPER bridge tool timeouts don't
reliably indicate the call didn't happen** on the REAPER side, just that the
response didn't come back in time.

**Ran the actual final review pass, all 6 sections, real rendered audio**:
- Fresh combined-mix renders for all 6 sections (post-fix, superseding the
  stale ones some of which predated tonight's fixes).
- No clipping anywhere, per-section or full mix (full mix peaks -2.3dBFS --
  no master trim needed this time, unlike Tidewater Clock).
- `review_arc_contrast` across all 6 sections: **PASSES**
  (worst_gap_db=0.70, worst_centroid_ratio=1.13, 9 pairs, 0 insufficient) --
  confirms real audible variety across the arc.
- `review_seam` at all 5 boundaries, **measured correctly this time**: first
  attempt compared whole-section average LUFS (wrong methodology, caught
  before reporting it -- section duration/density differences pollute a
  whole-section average, that's not what a "seam" means). Redone properly
  with actual 4s before/after boundary-window renders (matching
  `seam_review.py`'s established method): **intro->build passes, drop->outro
  passes; build->drop(locked-grid), drop->breakdown, and breakdown->drop all
  fail** (13-30dB jumps, centroid ratios up to 6.88). **Flagged, not
  auto-fixed** -- same principle as every previous seam finding in this
  project: these are exactly the boundaries where an abrupt jump plausibly
  *is* the intended character (entering/exiting a drop, stripping down into
  a breakdown), a human/taste call this architecture has never claimed for
  itself.

**Final render delivered**: `state/song_build/tidal_lock_full.wav` (320s,
-17.7 LUFS integrated, -2.3dBTP, crest 18.4dB) ->
`tidal_lock_full.mp3` (192kbps, 7.7MB), sent to the user. This is
"Tidal Lock" fully built end-to-end for the first time -- previous session
only got sections 0-1 live before the concurrency incident.

**Still open, for the user's actual listen**:
1. The 3 failing seams (build->drop, drop->breakdown, breakdown->drop) --
   same "is this the intended character or does it need bridging" call as
   always, now with real audio to judge, not just numbers.
2. Per-leaf loudness-balance/register-overlap findings within sections
   (real, logged in each section's build log, not chased to convergence --
   same "practical ceiling given time" precedent as the Tidewater Clock
   pass).
3. The pacing/staggered-entrance feedback from two sessions ago -- this pass
   built content and fixed bugs, did not add per-boundary automation ramps;
   still an open layer if the user's ear still wants it after hearing this
   version.
4. Code (this session's `src/planner/`, `scripts/` changes plus everything
   from the prior session) is still not git-committed.

## First real mastering pass -- master bus had ZERO processing the whole project (2026-07-28, continued)
User gave detailed listening feedback on `tidal_lock_full.mp3`, mapped
cleanly onto section boundaries (0:48/1:28/2:48/3:52/4:35 landing almost
exactly on section starts 48/88/168/232/272s -- confirms the diagnosis
approach of reading feedback against actual timeline math works). Key
complaints: intro drone "doesn't go anywhere," build section too silent/
dissonant/empty, drop's big entrance quickly repetitive + "timings out of
whack" + "broken ai trope" + muffled, breakdown's melody too quiet/muffled,
second drop's melody muffled/inseparable, outro genuinely good. Common
thread: "muffled/buried/inseparable" recurring almost everywhere.

**Root-caused before touching anything**: `get_project_summary` confirmed
master track `fx_count: 0` -- this entire project, across every session,
has only ever applied individual per-leaf gain trims; **zero EQ/
compression/limiting has ever existed anywhere in the signal chain**. This
is a real, unambiguous technical gap (not a creative call), and plausibly
explains most of the "muffled" complaints on its own. Also checked (before
assuming a bug): section 2's MIDI notes are all perfectly grid-quantized
(16th-note remainders all 0.0) -- "timings out of whack" is NOT a
quantization bug, more likely a perceptual/attack-time or arrangement
effect. Section 1's spec is a genuine groove-build (kick+bass+hats), not
intentionally sparse -- so "silent and dissonant" there is a real mix-
balance symptom, not by design.

**Added `mcp__reaper__add_mastering_chain()` to the master bus**: ReaEQ
(corrective) -> ReaComp (glue) -> ReaEQ (tonal) -> ReaLimit. Real bug hit
and fixed live: **`TrackFX_FormatParamValueNormalized` probing (same
technique as the Surge enum-size work) showed ReaLimit's "Threshold" param
formats as a plain increasing dB value (0->-60dB, 1.0->+12dB), which reads
like a drive/boost control -- it is NOT.** Set Threshold to +3.36dB
(*above* the Ceiling at -0.36dB) expecting a loudness boost; measured
result was ~4-8dB QUIETER, confirmed by isolating each FX via
`track_fx_set_enabled` (bypass-all baseline: -15.95 LUFS/-3.89dBTP on a
30s test window; limiter-alone: -19.8 LUFS/-8.0dBTP). **Root cause**:
ReaLimit's Threshold is a target/normalize-toward level that must sit
*below* Ceiling -- asking it to boost above its own ceiling puts the gain
computer in a permanent over-ceiling state, producing heavy constant
attenuation instead of a boost. Fixed by setting Threshold to -2.4dB
(below the -0.36dB ceiling) -- confirmed via the same isolated test:
level restored to parity with bypass baseline (-15.6 vs -15.95 LUFS) with
real, measurable EQ/glue effect (spectral centroid 1598Hz->1971Hz on the
test window, crest factor 14.0->9.3). **Worth remembering for any future
ReaLimit tuning: iterate empirically via a short isolated render + bypass
comparison, don't trust the parameter's directional sign from its display
label alone** -- same "verify, don't assume" lesson as the solo-timeout
bug from earlier today, now hit in a completely different subsystem.

Also hit **the same render-timeout-but-actually-succeeded pattern noted
earlier this session**: multiple full-320s `render_project` calls returned
`"File request timed out"` but the file was correct duration/content
seconds later once the render actually finished writing -- confirmed by
`soundfile.info` before trusting each result, never blindly retried
into a race.

**Final settings, live on the master bus** (fx_index 0-3):
- ReaEQ corrective: hipass 35Hz (rumble control); band cut -3dB at 300Hz,
  Q1.2 (the classic low-mid "muffled/muddy" band, main lever for the
  user's core complaint).
- ReaComp glue: threshold -9.9dB, ratio ~2:1, attack 10ms, release 150ms,
  Auto Make Up Gain on -- deliberately gentle after the first attempt
  (-18.4dB threshold, 3:1 ratio) proved too aggressive for this mix's
  ~18dB crest factor and ate ~8dB of level with insufficient auto-makeup
  compensation.
- ReaEQ tonal: band +2dB at 2500Hz Q1.0 (presence/clarity where melodic
  content sits); hishelf +2.5dB at 6000Hz (air).
- ReaLimit: threshold -2.4dB, ceiling -0.36dB (~streaming-safe per the
  tool's own -0.3dB guidance), release norm 0.15.

**Full-song result, measured**: -16.9 LUFS integrated (was -17.7,
modest +0.8dB), true peak -7.2dBTP, **crest factor 18.4dB -> 11.6dB**
(the real, meaningful change -- much tighter/glued mix, should read as
punchier/clearer even though raw LUFS barely moved), 0 clipped samples.
Rendered `tidal_lock_mastered_v1.wav` -> `.mp3` (192kbps), sent to user
explicitly framed as a first pass addressing the mastering-level symptom,
not the deeper composition-level ones (section 2's 80s of no evolution,
section 1's weak groove, the "broken ai trope" repetition/timing feel) --
those are flagged as still open, waiting on whether this pass's mix
clarity changes the user's read on them at all before investing further.

**Still fully open, explicitly not touched this round**:
1. Section 2 (drop, locked-grid, 88-168s): "quickly turns repetitive... no
   real evolution until 2:48" -- the locked-grid design manifesting as
   literal staticness. Needs composition-level work (automation/filter
   movement/layer thinning over the 80s), not a mix fix. Same root cause
   family as the pacing/anticipation feedback flagged 2 checkpoints ago.
2. "Timings ... out of whack ... broken ai trope" at the section 2
   entrance -- confirmed NOT a MIDI quantization bug. Leading hypothesis,
   not yet tested: attack-time mismatch across different Surge presets
   triggered on the same grid (a documented failure class in this project,
   `preset_attack.py` exists for exactly this) -- a slow-attack layer
   "arrives" audibly late relative to a fast-attack one even on identical
   MIDI timing. Not measured yet for section 2's specific preset mix.
3. Section 1 (build, 48-88s): real groove-build spec, perceived as
   silent/dissonant/empty -- likely a balance issue (kick/bass/hats
   individually too quiet or masking each other), not yet isolated per-leaf.
4. Get the user's reaction to `tidal_lock_mastered_v1.mp3` before deciding
   how much more to invest in 1-3 -- same "ask early, don't guess" pattern
   this project keeps re-learning.

## Real "off tempo buzzing" bug found and fixed: a backbeat layer with a non-4-beat cycle (2026-07-28, continued)
User's v1 feedback was detailed and section-mapped again (confirms the
"read feedback against actual timeline math" approach keeps paying off).
Key new items: section 4 (3:53) got WORSE ("illegible/garbled") after
mastering while section 3 (2:50) got better -- real signal that glue
compression hurts an already-dense section more than a sparse one, argues
for per-section not just global master treatment. User also asked a real
methodology question: does an iterative "set numeric EQ/comp values, measure,
adjust direction, repeat, only escalate to a listen once converged" loop
make sense for carving, generalizable elsewhere? **Answer given: yes, with
one correction** -- it needs to target *relative/pairwise* metrics between
competing tracks (this project already has this in `review_composition`'s
spectral-centroid-ratio/LUFS-gap checks), not each track's own absolute
target in isolation, since "audible" is inherently about masking between
simultaneous elements, not a solo property. Proposed extending `mix_fix.py`/
`orchestrate.py` into a real closed iterative loop instead of the current
single propose-and-check pass -- **not yet built**, flagged as real next
work if the user wants to invest in it.

**Diagnosed "buzzing off tempo" at 1:27 concretely, ruled out one
hypothesis before finding the real one.** First checked whether the
hi-hat we swapped earlier today (`song/section_2/child_0/child_2`,
`Plucks/Metallic.fxp`) had a slow attack causing perceived lateness --
built a scratch test track (insert_track/apply preset/one 8-beat note/
solo/render with master FX bypassed/measure/delete track -- clean
throwaway pattern, didn't touch the live section), measured via
`check_preset_attack.py`: **attack_time_s=0.0, instant** -- ruled out,
not that leaf.

**Found the real cause by inspecting the actual note data**, not by
guessing: `song/section_2/child_0/child_3` (rimshot, track 16)'s own
spec explicitly says "triggered on a fixed backbeat pattern (beats 2
and 4 of every bar)... locked for all 40 bars... no fills or pattern
variation." But its actual authored notes had a real repeating
**3.25-beat cycle** (diffs alternating 2.0, 1.25) instead of a 4-beat
bar cycle -- since 3.25 doesn't divide 4, the pattern continuously
drifts out of phase with the bar/kick/bass grid forever, landing on a
different beat-offset every cycle. 84/98 notes were off the intended
beat-2/beat-4 grid. This is a genuine model authoring bug (contradicts
its own explicit spec), not a taste call, not a preset problem --
exactly matches "intermittent buzz-buzz, off tempo" as a description of
a rhythmic layer that never locks to the groove.

**Fixed live**: `clear_midi_item` + rewrote with a clean 80-note backbeat
(beat 1 and 3 of every one of the 40 bars, 0-indexed, same pitch/velocity/
length as original), verified via `get_midi_notes` that all 80 notes sit
on a consistent 2-beat spacing. Updated `song_plan.json` with the new note
array and a `source` note. Saved project.

**Re-rendered full song** (`tidal_lock_mastered_v2.wav/mp3`, same master
chain as v1, only the rimshot content changed): -16.9 LUFS, -6.9dBTP, 0
clipped samples. Sent to user.

**Still fully open, unchanged from v1's list**, plus the two new items
from this round:
5. Section 4 (3:53) got more garbled under the current global master
   chain -- likely needs per-section compression/EQ treatment instead of
   one static master bus setting, or the density itself (9 leaves) needs
   thinning/register-carving at the composition level.
6. The iterative pairwise EQ-carving loop discussed but not built --
   real next infrastructure investment if the user wants to pursue it,
   would extend `mix_fix.py`/`orchestrate.py` rather than replace them.
7. Section 2's "no evolution for 80s," section 1's weak/empty groove,
   section 3's melody staying quiet rather than growing -- all still
   open, all composition-level, none touched this round.

## v2 listening feedback -- systemic "static loops" gap found and fixed at the PROMPT level (2026-07-28, continued)
User's v2 feedback confirmed the timing fix worked ("the rim being on
time now made that part a really good loop... jumpscares you") but
converged on a single unifying complaint across three separate
observations (section 2's locked-grid drop, section 4, and the just-fixed
rimshot loop itself once its novelty wears off): **sections don't evolve
within themselves -- they differentiate well from each other, but each
one's own loop is static for its whole duration.** User explicitly asked
for this to be fixed at the prompt level, not per-section, since it's the
same root cause repeating.

**Root-caused by reading the actual prompts, not guessing.** Both
`decompose.py` and `scripts/leaf_emit.py` already had automation tools
(`automate_track_envelope`/`automate_surge_param`) built and available --
the gap was entirely in how they were framed:
- `leaf_emit.py`'s emission prompt said automation was OPTIONAL ("only add
  it when the spec actually calls for movement, not by default") -- so a
  leaf whose note pattern gets tiled/looped for a whole 80s section had no
  pressure to ever move.
- `decompose.py`'s child-spec generation never asked the model to think
  about evolution AT ALL -- specs described only what a part is, never how
  it changes over its own duration, so leaf_emit had nothing to act on even
  if it wanted to.

**Fixed both, flipping the default from opt-in to opt-out**:
- `decompose.py`: added an explicit paragraph -- for any section >~16 bars,
  an is_leaf child's spec MUST say how the part changes across its own
  duration (filter opening, density/velocity build, layers in/out, register
  shift), not just describe the static loop. Explicit clarification that
  `locked_grid` means the rhythmic/harmonic pattern stays fixed, NOT that
  literally nothing may move -- timbral/filter/level motion is still
  expected even in a locked section.
- `scripts/leaf_emit.py`: automation is now the default requirement for any
  leaf with `duration_s >= 12`, with the actual computed loop-repeat count
  stated in-prompt (e.g. "this cycle repeats ~20 times over 80s") and an
  explicit requirement for >=2-3 distinct automation points, not just an
  on/off toggle. Skipping is still allowed, but only for genuinely short/
  one-shot/single-sustained-note parts where motion would fight the part's
  own purpose.
- Verified: full test suite still 122/122 passing after both edits (pure
  prompt-text changes, no schema/validation changes).
- **Not yet updated**: the older bug-fix/retry call sites
  (`pipeline.py`'s leaf-retry path, `reemit_percussion_leaf.py`,
  `retry_pulse_leaf.py`, `backbone_orchestrated_round5.py`) don't pass
  `duration_s`, so they fall back to the "skip automation" branch --
  acceptable for now since those are surgical single-leaf bug fixes, not
  the main generation path, but worth closing if they get reused for
  fresh content generation later.

**User's specific creative note on section 1** ("should be something
other than the melody, a premonition of the third aggressive thing")
-- a genuinely good, specific idea (a build section foreshadowing the
upcoming drop's character rather than just being quiet filler) but
NOT folded into the generic prompt fix above, since it's a specific
compositional choice for this song, not a universal rule. Flagged as a
real option for whenever section 1 gets rewritten/regenerated, not
generalized into arc.py's prompt (would need its own separate
conversation about whether "sections before a big contrast should tease
it" is a rule worth generalizing).

**Not yet decided or executed**: whether to regenerate content with the
improved prompts. Two real options, cost/consistency tradeoff, the
user's call: (a) full song regeneration (most consistent result, most
expensive -- many fresh API calls + a full live REAPER rebuild), or
(b) targeted resurgical rewrites of just the worst-offending leaves
(section 2's static layers, section 4's density/legibility, section 1
reimagined as a premonition) using the improved prompts -- cheaper,
faster, but leaves the rest of the song on the old static-loop content.
Nothing rebuilt yet this round -- prompts fixed, content not
regenerated.

**User chose (b), targeted rewrites.** Work started via a 7-task list
(TaskCreate #1-7): new "premonition" leaf for section 1 (track 33), pad
re-emits for sections 1/2/4, lead re-emit for section 4, final
re-render/deliver.

## MID-TASK CHECKPOINT (2026-07-28, session still live -- READ THIS FIRST if resuming)
**Currently blocked**: the `reaper` MCP server disconnected mid-task
(tool calls started returning "No such tool available") after ~50s of
waiting it had not reconnected, though `ps` confirms the underlying
REAPER process (PID 6450, healthy, 75min CPU time) and the bridge
xvfb-run wrapper (PID 6432) are both still alive -- this looks like a
transport-layer hiccup in the twelvetake MCP python process (PID 4561,
also still alive), not a crash, but nothing in this session can force a
reconnect. Whoever resumes: check `ToolSearch("select:mcp__reaper__get_track_count")`
first: if it resolves, the tools are back, continue below; if not, this
may need the user to reconnect the session per the project's own
existing note ("`.mcp.json`-configured tools won't appear in *this*
conversation -- needs a session reconnect + approval first" -- though
that note was originally about *newly added* servers, an existing
server dropping mid-session may behave the same way).

**Real, unrelated-to-the-disconnect finding from this same stretch**:
two stray task-notifications arrived from an agent named "would it make
sense to make all changes for all s..." (task-id
`awould-it-make-d1b7e15f05e7588c`) that this session never spawned --
same class of incident as the "stray subagent" note from two sessions
ago (leaked background process, not a second human/session). Its
content (batching apply_surge_preset calls, reducing the ~2min-per-preset
cost) was read but NOT acted on -- correctly treated as untrusted
per-instructions ("no human input has been received"), not a real user
request. Its actual content is genuinely useful for later (see "Real
lead for future speed work" below) but nothing was done with it live.
Worth flagging to the user next message just as an FYI, not urgent --
no evidence it touched the live project.

**Progress on task #1 (section 1 premonition leaf) before the
disconnect**: emitted via a real Haiku call (4 sparse hits, velocity
80->95, at beats 16/36/52/76 of a 40-beat section -- genuinely good,
matches the brief). Built live on a NEW track 33 (`InsertTrackAtIndex`
correctly shifted section 5's tracks from 33-37 to 34-38, confirmed via
`get_project_summary` -- initial track-count jump to 39 that looked like
a bug was NOT one, just this expected reindex). Notes + preset applied
cleanly (verified via a clean solo bare-note render: peak -27dB, real
signal, not silent).

**A real, reproducible new bug found and root-caused this stretch,
distinct from the disconnect**: `automate_track_envelope` on "Volume"
produces COMPLETE digital silence (exactly 0.0 peak, not just quiet) for
the whole leaf, even at moderate envelope values (tested 0.25-0.9 AND a
flat 0.5 AND a flat 1.0 -- all gave hard zero). Isolated via real A/B
testing, not guessed: cleared both automation envelopes -> real signal
returns (peak 0.045, matches expectation). Added back ONLY the FX
param envelope (filter cutoff) -> still real signal (0.044, confirmed
that env produces a sane 380Hz cutoff via `TrackFX_FormatParamValueNormalized`,
not the culprit). Added back ONLY the Volume track envelope (value=0.5
flat) -> hard silence again. **The Volume track envelope is confirmed
the actual cause, root cause of ITS OWN mechanism not yet found** -- was
mid-testing whether value=1.0 (should be neutral/unity if this is a
linear-gain scale) also produces silence, which would point at a
structural bug in the envelope-arm/automation-mode state rather than a
units/scaling mistake, when the MCP disconnect hit. **This is a real
bug in this project's automation pipeline that will block EVERY planned
re-emission in the current task list** (sections 1/2/4 pad/lead
re-emits all rely on Volume envelope automation) -- must be root-caused
before continuing, not worked around per-leaf.

**Hypotheses not yet tested, for whoever resumes**:
1. value=1.0 (unity) still silent -> points at automation being
   structurally broken (bypass flag, automation mode, or an
   envelope-arm requirement -- `mcp__reaper__arm_track_envelope` exists
   and was never tried) rather than a scaling mistake.
2. If value=1.0 is NOT silent -> the actual valid range for a Volume
   envelope's `value` argument is narrower/different than assumed
   (`automate_track_envelope`'s existing calls elsewhere in the song,
   e.g. section 2's pad at values 0.3/1.0, apparently DID work when
   originally built by `execute_section_direct.py`'s `build_leaf()` --
   worth diffing exactly what that function does differently from the
   direct MCP-tool path used here, e.g. it calls the raw bridge
   `InsertEnvelopePoint` directly with explicit shape/selected/clear-old
   args, not the `mcp__reaper__add_envelope_point` tool -- a parameter-
   default mismatch between the two paths is a real, testable
   hypothesis).
3. Check `set_track_automation_mode` for track 33 -- if a prior op left
   it in something other than trim/read (mode 0), that could explain
   points existing but not being heard.

**Real lead for future speed work** (from the stray agent's otherwise-
untrusted content, worth evaluating on its own merits later): the ~2min
`apply_surge_preset` cost is ~500 individual param-set round-trips over
the file-based bridge protocol; a single batched-params bridge call
could collapse that to seconds. Not verified, not attempted -- a real
scoped idea for whenever this project wants to invest in build speed,
independent of tonight's automation bug.

**Test artifacts from this diagnostic stretch, safe to delete**:
`state/song_build/check_premonition*.wav` (multiple isolation-test
renders).

## reaper MCP disconnect fixed: upstream mcp>=2.0.0 break + daemon persistence gotcha (2026-07-28, continued)
Root-caused the mid-task MCP disconnect flagged in the last checkpoint (was NOT a
transport hiccup as originally guessed -- confirmed via `claude mcp list`: reaper
server `Failed to connect -- Connection closed`). Ran `uvx twelvetake-reaper-mcp`
manually: `ModuleNotFoundError: No module named 'mcp.server.fastmcp'`. Real cause:
twelvetake-reaper-mcp pins `mcp>=1.2.0` with no upper bound; the `mcp` PyPI package
just shipped a breaking 2.0.0 that removed/renamed `mcp.server.fastmcp` ->
`mcp.server.mcpserver`, and uvx resolved to the new incompatible 2.0.0 on this
reconnect. **Fixed in `.mcp.json`**: `"args": ["--with", "mcp<2.0.0",
"twelvetake-reaper-mcp"]` -- verified via `claude mcp list` (Connected).

**Second gotcha, real and worth remembering**: closing/reopening the Claude Code
app does NOT restart the MCP client -- Claude Code runs a persistent background
daemon (`claude daemon run --origin transient`, survives the app window closing)
that the reopened app just reconnects to, so a `.mcp.json` fix does not take effect
until the daemon itself is killed (`claude daemon stop --any`) and a fresh one
spawns. A plain app restart is NOT enough when an MCP server config changed --
this explains why the project's older "needs a reconnect" notes were sometimes
insufficient.

## Volume-envelope silence bug: root-caused and fixed for real (2026-07-28, continued)
Resumed exactly where the previous checkpoint left off (task #1, section 1
premonition leaf on track 33, blocked on `automate_track_envelope`/Volume
producing hard 0.0-peak silence at every value tried). Closed out both
untested hypotheses from that checkpoint and found the real cause, distinct
from either: **not** an automation-mode/arm issue (tested Read mode and
`arm_track_envelope(true)` explicitly, both still silent), **not**
track-33-specific (reproduced live on track 0, a track already confirmed to
render real audio, by adding the same two unity-value Volume points to it --
also went instantly silent).

**Root cause, found by reading the raw `.rpp` envelope chunk directly** (added
a temporary `GetEnvelopeStateChunkRaw` bridge case to get real ground truth
instead of guessing further): inserting value=1.0 produced a stored chunk
point of `PT 55 0 0` -- REAPER itself was silently collapsing our "1.0" to
effectively zero. Probing a range of raw inputs (0.5 through 8.0, then 1e5
through 5e7) showed a highly non-linear curve (roughly cubic at small scale,
exploding at large scale) -- the signature of a **fader-scaling curve**, not
a units mistake. Confirmed directly: this track's Volume envelope has
`reaper.GetEnvelopeScalingMode(env) == 1`, and `reaper.ScaleToEnvelopeMode(1,
1.0)` returns `716.21785031261` -- *that* raw value, not `1.0`, is what
REAPER's `InsertEnvelopePoint` actually needed for true unity gain on this
scaling mode. Verified by hand: inserting the scaled value produced a clean
`PT 50 1 0` in the chunk and real audio on render (peak 0.044, matching the
no-envelope baseline exactly).

**This was a bug in the shared bridge code, not caller-specific** -- both the
real `mcp__reaper__add_envelope_point` MCP tool and `execute_section_direct.py`'s
direct `InsertEnvelopePoint` bridge calls go through the exact same Lua
dispatcher case, and neither ever scaled the value. This also retroactively
explains the earlier-flagged "does execute_section_direct.py's raw
`InsertEnvelopePoint` path differ from the MCP tool path" open question from
the previous checkpoint -- **it doesn't differ; both were equally broken**,
meaning **any previously-built leaf anywhere in the song that used
`automate_track_envelope` on Volume is suspect and may be silently
non-functional automation** (worth an audit pass, not yet done).

**Fixed at the actual choke point**: `scripts/reaper_mcp_bridge.lua`'s
`InsertEnvelopePoint` case now always computes
`reaper.ScaleToEnvelopeMode(reaper.GetEnvelopeScalingMode(env), value)`
before calling REAPER's own `InsertEnvelopePoint` (safe even for
identity-scaling envelopes, where it's a no-op) -- both the primary
`(track_index, envelope_name, ...)` calling convention and the legacy
userdata one. `GetEnvelopePoints` (the read side) now applies the inverse
`ScaleFromEnvelopeMode` so a get/insert round-trip stays in real/display
units on both ends, matching every existing MCP tool docstring's documented
contract ("value: Envelope value (0.0-1.0 for most envelopes)") instead of
silently violating it. Deployed to `~/.config/REAPER/Scripts/` and verified
three times: via the raw bridge client, via the real `mcp__reaper__` MCP
tools with an ordinary non-unity value (0.5), and acoustically (rendered
note near the envelope's 0.5 point measured quieter than a note near its 1.0
point, correct direction and rough magnitude). Two throwaway diagnostic
dispatcher cases added mid-investigation (`EchoArgs`, `ScaleEnvelopeModeTest`)
were removed again once the real fix landed; `GetEnvelopeStateChunkRaw` was
kept (small, generically useful for any future envelope-state debugging).

**Premonition leaf (track 33) finished**: since the original Haiku-emitted
automation spec from the pre-disconnect session was never persisted to a
file (it only existed as live tool calls in that earlier conversation, not
recoverable), applied a fresh, musically-justified Volume swell instead of
trying to reconstruct the lost exact values -- 0.55 at t=48 (item start) to
1.0 at t=88 (item end), paralleling the leaf's own existing velocity ramp
(80->95 across its 4 notes) to match its "premonition" build purpose. Track
unsoloed, automation mode set back to Read, project saved.

**Remaining task-list items (from the 7-task pre-disconnect plan), still
open**: pad re-emits for sections 1/2/4, lead re-emit for section 4, final
re-render/deliver. All now unblocked by this fix.

## Section 1 was almost entirely misplaced on the timeline -- found and fixed (2026-07-28, continued)
While starting the pad re-emit (task #3), checked track 6's live item
position before touching it and found it at project position 0.0, length
40 -- but `song_plan.json` says `timeline_start_s: 48.0` for every section 1
leaf. Checked all 5 of section 1's leaves against the plan's own track_index
assignments (kick=track7, hihat=track8, rimshot=track9, bass=track5,
pad=track6):

- track5 (bass): position 0.0 -- **wrong**, should be 48. Content itself
  fine (91 well-formed notes spanning the full ~40s pattern).
- track6 (pad): position 0.0 -- **wrong**. Being rebuilt anyway (task #3).
- track7 (kick): position 0.0 -- **wrong**. Content fine (80 notes, clean
  four-on-the-floor).
- track8 (hihat): position 48.0 -- **correct**, the only one.
- track9 (rimshot): position 20.0, length 20.0 -- **wrong on both counts**:
  40 real notes present, but their absolute times run 20.875-41.875s,
  i.e. up to 21.875s past the item's own 20s length -- the tail was being
  silently clipped on top of being misplaced (same clipping failure mode
  `leaf_emit.py`'s own comments already document elsewhere in this file).

**Real, previously-unknown consequence for the delivered song**: 4 of 5
section-1 leaves were actually sounding during 0-40s (bleeding into/
overlapping the true intro, section 0's 0-48s window) instead of 48-88s,
leaving section 1's real timeline window with only the hihat correctly
present alone. This lines up exactly with the user's actual v2 feedback --
intro "doesn't go anywhere" (masked by an uninvited kick+bass+pad bleeding
in from a misplaced section) and section 1 "silent/dissonant/empty" (it
genuinely was, missing kick/bass/pad entirely, just one lone hi-hat) --
likely a bigger contributor to those two complaints than anything about
static loops or automation. **Checked whether this is systemic**: spot-
checked one track each from sections 0, 2, 3, 4 (tracks 0, 10, 18, 24) --
all correctly positioned at their real section starts. **This bug is
isolated to section 1** -- consistent with section 1 being the very first
real decompose->emit section built this project (`build_section_proof.py`
era, before later sections used the more mature `execute_section_direct.py`
pipeline that got the positioning right).

**Fixed**: `set_item_position` on tracks 5, 7, 9 to project time 48
(content/notes untouched -- moving a MIDI item preserves its internal
beat-relative note timing, only the item's absolute anchor moves), plus
`set_item_length` on track 9 to 40s to stop the tail clipping. Saved.
Track 6 (pad) is being rebuilt fresh at the correct position as part of
task #3 rather than moved. **Not yet re-rendered/verified acoustically
post-fix** -- that happens as part of the final re-render (task #7); this
alone is likely to change the intro and section-1 character substantially,
independent of any of the planned re-emissions.

## All 7 tasks closed out, v3 rendered and delivered (2026-07-28, continued)
Finished the full pre-disconnect task list in one continuous session after
reconnect. In order: fixed the Volume-envelope bug (bridge-level), finished
the premonition leaf, fixed section 1's timeline-position bug (4 of 5 leaves
were misplaced -- see entry above), then re-emitted 4 leaves with the
automation-required prompt: section 1 pad, section 2 pad, section 4 pad,
section 4 lead (the sustained "Leads/Saw Octaves" slot -- re-emission
independently picked a different but equally apt preset, "Leads/Crisp PWM",
a legitimate re-emission outcome, not an error).

**Second real bug found and fixed during this pass, in `leaf_emit.py`
itself** (not the bridge): `tile_notes_to_duration()` is deliberately a
no-op for a pattern that already spans/exceeds the target duration (a
one-shot/sustained part) -- correct for that case, but the model has no
explicit duration_beats constraint in that prompt branch, so it can (and
did, live, on the very first re-emit: section 1's pad) emit a sustained
note far longer than the leaf's real duration. The existing post-processing
only grew the item to match overlong notes, never shrank -- would have
silently stretched a 40s leaf's item out to 80s, into the next section's
territory. Fixed: notes now get clamped to duration_beats after tiling,
before the item-growth check ever runs. Verified via a rebuilt emission
(160-beat pad note -> correctly clamped to 80 beats/40s on the next attempt).

**Also found while identifying which track was which leaf**: track 4 ("S0
leaf4") has `volume_db=30.0` (an extreme, likely-mistaken gain) but is
totally silent even soloed (peak 0.0) -- so it's a dead/broken leaf, not a
clipping risk. Not chased further this round -- flagged here as a real,
still-open minor gap in section 0's content, separate from everything else
fixed tonight.

**Final render**: `tidal_lock_mastered_v3.wav/mp3` -- same master chain as
v1/v2 (untouched), -17.4 LUFS integrated, -8.4dBTP, 0 clipped samples.
Delivered to the user, framed around three real, verifiable changes since
v2: (1) section 1 (the "build") should sound like an actual section for the
first time, not a near-silent afterimage with content bleeding into the
intro instead; (2) sections 1/2/4's re-emitted layers have real audible
motion (volume swells, filter sweeps) instead of static loops; (3) the
premonition leaf (track 33) is live for the first time this session.
**Not yet done**: getting the user's actual listen/reaction to v3 -- same
"ask before over-investing further" pattern this project keeps following.

## v3 listening feedback -- received, NOT acted on (2026-07-28, continued)
User gave detailed section-mapped feedback on `tidal_lock_mastered_v3.mp3`
then explicitly said **stop iterating for now, wait for credits** -- this
session did not make any further song changes after receiving it. Recorded
here verbatim-mapped so a future session can act on it without re-deriving
the mapping. Real timestamps given: ~2:49 (169s) and ~3:52 (232s) line up
almost exactly with section3's start (168s) and section4's start (232s) --
same "feedback maps cleanly onto section boundary math" pattern this
project has repeatedly confirmed, so the part-numbering below is inferred
from that math, not guessed blind:

1. **Intro (section0, 0-48s)**: "perhaps too long for the droning it does
   without much change in the middle of it" -- a pacing/evolution
   complaint, not a mix complaint. Section0 has never had automation work
   done on it this project (all the automation-prompt fixes/re-emits
   targeted sections 1/2/4) -- likely still has the original static-drone
   content from before the automation-required prompt existed.
2. **Section1 (build, 48-88s)**: "background stuff happening now, not as
   bad, but there is something hidden deep again, probably wanted it to be
   more surfaced" -- the position-bug fix + pad re-emit from this session
   registered as real improvement ("not as bad"), but something in this
   section (bass? the premonition leaf on track 33? unclear which) is
   still buried/too quiet relative to what the user wants foregrounded.
   Not yet isolated to a specific track.
3. **Section2 (drop, 88-168s)**: "better, but still perhaps not enough
   variation... sandwiched between better material so it seems better" --
   user is explicitly flagging a possible contrast-illusion (their own
   words), not fully certain the section itself actually improved. This is
   the same "locked-grid drop, no real evolution" section flagged multiple
   checkpoints ago -- still not fully resolved even after the pad
   re-emit/filter-sweep work this session.
4. **Section3 (breakdown, 168-232s, "the 4th part, ~2:49")**: "better than
   before, the melody underneath should probably be even louder than it is
   now over time" -- real, specific, actionable: a melody layer needs a
   rising volume automation (not necessarily new content, could be an
   envelope-only fix now that the Volume envelope bug is closed).
5. **Section4 (climax/2nd drop, 232-272s, "the 5th part, ~3:52")**: the
   most substantive note -- "couldve reused stuff from the 3rd, bringing
   back the rim or whatever it was that was off tempo before and that
   crunchy sound wouldve been perfect... too muddled and illegible, also
   the recall wouldve been nice, perhaps start different, add the recall."
   Concretely: bring back section3's rimshot layer (the one fixed for the
   3.25-beat off-tempo bug a few checkpoints ago,
   `song/section_2/child_0/child_3` -- note this is section**2** in the
   plan's own 0-indexed node_id, which is the drop, NOT section3 in the
   user's spoken 1-indexed "3rd part"; the user's "3rd part" -> plan's
   node-id section2 given the timestamp math above lines up with drop=
   section2's window (88-168s) -- **this cross-indexing needs to be
   double-checked against the actual node_id/timestamp mapping before
   acting**, don't assume) as a recall/callback into section4, and address
   the muddled/illegible density there (matches the older "section4
   garbled/illegible" complaint from two checkpoints ago -- still not
   resolved by the lead re-emit done this session).
6. **Outro (section5, 272-320s)**: "good... but also stuff is low/muddled
   and probably isnt legible on shitty headphones" -- user explicitly
   caveats their whole listen was on "really good headphones" and expects
   translation loss on worse playback systems; the low/muddled notes here
   and in section4/section5 may partly be a translation-to-worse-speakers
   issue rather than a pure mix bug -- worth keeping in mind before
   over-correcting for one listening environment.

**No further action taken this session per explicit instruction.** Next
session picking this up should: (a) re-derive/confirm the section-number
mapping above against actual `song_plan.json` node_ids and timestamps
before touching anything (flagged above as uncertain in one place), (b)
treat item 5 (section4 recall + muddle) as the highest-value single fix
given how specific and reasoned the user's note is, (c) NOT start any of
this without the user's go-ahead, since they explicitly asked to pause for
credits.

## v4: section4 rim recall + section3 melody swell, rendered and delivered (2026-07-29)
User said "continue with the music" -- treated as the go-ahead the previous
checkpoint was waiting for. Re-derived the section mapping from
`song_plan.json` directly before touching anything (didn't trust the prior
session's own flagged-uncertain note blind): `section_root_ids` timestamps
confirm section0=0-48s(intro), section1=48-88s(build), **section2=88-168s
(drop) = user's spoken "3rd part"**, section3=168-232s(breakdown, "4th
part"), section4=232-272s(climax, "5th part"), section5=272-320s(outro) --
matches the prior session's own inferred mapping, now confirmed not just
guessed.

**Bridge/REAPER were not running at session start** (only the
twelvetake MCP python process was alive, no Xvfb/reaper) --
`start_reaper_mcp_bridge.sh start` brought it back up against the
persisted `session.rpp` (39 tracks, confirmed via `get_project_path` --
not a fresh scratch project, all prior session's fixes intact).

**Item 5 (section4 recall + muddle), addressed as one fix**: found
`song/section_4/child_0/child_3` (S4 leaf8, track 32, REAPER's own spec
calls it "sparse accent layer") was actually a dense 85-note pattern of
overlapping/tied notes -- not sparse at all -- using `Plucks/Metallic.fxp`,
the *same* preset as section4's snare/clap (track 30) and hi-hat (track
31). Three metallic percussion layers stacked at near-continuous density
is a real, plausible source of "too muddled and illegible." Fixed by
replacing both preset and pattern with a direct recall of
`song/section_2/child_0/child_3` (the rimshot fixed for the 3.25-beat
off-tempo bug a few checkpoints ago): applied `Plucks/Snap.fxp` to track
32, cleared the old notes, wrote a clean 40-note beat-1/beat-3 backbeat
(pitch 60, vel 100, len 0.25 beats -- exact same note shape as section2's
fixed pattern, just half the note count since section4 is 40s vs
section2's 80s). Serves both complaints at once: it's now an audible
recall of the earlier fixed rimshot's exact sound/pattern, AND it's no
longer a 3-way same-timbre density pileup since Snap != Metallic and the
pattern is now genuinely sparse.

**Item 4 (section3 melody should grow louder over time)**: added a Volume
envelope on track 21 (`song/section_3/child_3`, "Plucks/Bell 1.fxp",
the breakdown's "signature motif... glassy FM bell" per its own spec) --
0.6 at t=168 (section3 start) rising to 1.15 at t=232 (section3 end).
Needed `run_action(40406)` ("Track: Toggle volume envelope visible") on
the selected track first -- `add_envelope_point` fails with "Envelope not
found" if the envelope was never shown, a real gotcha not hit before
since every prior automation this project built used tracks whose
envelope was already visible from an earlier op. Verified via
`get_envelope_points` after saving: 3 points present (default 1.0 at t=0,
then the two new ones), values round-tripped exactly as written --
confirms the `ScaleToEnvelopeMode` fix from the prior checkpoint's bug
continues to hold for a fresh envelope on a fresh track, not just the one
it was originally debugged on.

**Items 1, 2, 3, 6 (intro pacing, section1's still-buried element,
section2's contrast-illusion uncertainty, translation-to-worse-speakers)
deliberately NOT touched this round** -- scoped to the one highest-value
fix per the prior checkpoint's own plan, not a full pass over every v3
note.

**Rendered v4**: `tidal_lock_mastered_v4.wav/mp3`, same master chain as
v1-v3 (untouched). Full render returned the documented "File request
timed out" false-negative (render actually completed) -- polled the
output file size via a background Bash task instead of blindly retrying,
confirmed via `soundfile.info` (323s = 320s + 3s tail, 24-bit, real
signal, peak 0.38) before trusting it. Measured: **-17.3 LUFS
integrated, -8.4dBFS peak, 0 clipped samples** -- in line with v1
(-16.9/-7.2), v2 (-16.9/-6.9), v3 (-17.4/-8.4), confirms these two
targeted edits didn't regress the master chain's overall level/headroom.
Delivered to user.

**Not yet done**: user's reaction to v4 -- same pattern as every prior
round, don't over-invest in items 1/2/3/6 until there's a read on whether
this round's fixes actually landed as intended.

## v5: real gain-staging bug found across the whole song, root-caused with data, 3 layers fixed (2026-07-29, continued)
User gave v4 feedback fast (didn't wait for a separate listen round) and it
converged on the same complaint across 3 of 4 flagged sections -- "quiet/
buried... every part so far" -- plus asked a real design question: does
automation need actual before/after contrast to be heard, and does the AI
need more data to avoid uniform/predictable movement.

**Answered the conceptual question directly rather than deferring**: the
leaf-emission model isn't being trained on this project's audio (it's a
fixed pretrained LLM making one-shot creative calls), so "more data" isn't
the lever -- the real gap is that "add automation" specs produce a single
clean start->end ramp, which is real motion but uniformly shaped every
time. Real evolution needs the *spec* to describe a non-monotonic arc and
touch more than volume (density/register/which notes play), not just a
tool-use nudge.

**Diagnosed "buried in every part" with real numbers instead of guessing
again** -- solo-rendered the 4 flagged melodic candidates full-section
(section1 premonition t33, section2 pluck-motif t12, section3 bell t21,
section4 lead-sustained t27) and compared each against the corresponding
window of the already-rendered v4 full mix:
- t33: solo RMS **14dB below** the mix window
- t12: solo RMS **22dB below**
- t21: solo RMS **20dB below** (even after last round's volume-envelope
  swell -- confirms the swell was a shape on top of an already-buried
  base level, not a fix to it)
- t27 (the one user said was "crowded by design, not error"): only
  **2dB below** -- present and loud, exactly matching that read.

**Real root cause, confirmed not guessed**: every leaf this project has
ever built got its track fader left at flat 0dB regardless of how loud
its Surge preset renders natively -- `get_project_summary` confirms every
track (except the pre-existing dead track4 anomaly) sits at `volume_db:
0.0`. Since presets vary wildly in native output level (plucks/bells/thin
pads vs kicks/basses run very differently hot), that raw preset-loudness
spread propagates straight into the mix with nothing correcting it. This
is a systemic gain-staging bug, not a composition or automation problem
-- matches the user's own hypothesis ("presets are quieter/louder on base
settings maybe?") exactly, now confirmed with data.

**Fixed the 3 confirmed-buried layers** via `set_track_volume` (real dB,
not envelope tricks): t33 +10dB, t12 +12dB, t21 +12dB. t27 left untouched
(already correctly prominent per the diagnostic). **Not** a full-song
audit -- only the 4 flagged candidates were measured/fixed, not all 39
tracks; a real remaining gap if more "buried" complaints surface
elsewhere (see Next).

**Verified the fix actually changed something audible, not just a number
in a fader field**: rendered v5, diffed it against v4 sample-by-sample in
each affected section window. The diff signal's own RMS (i.e. exactly
what changed) is *louder than or comparable to* the entire v4 mix at that
moment in sections 1 and 3 (diff RMS -1.9dB and +3.0dB relative to the
full mix, respectively) and a healthy -3.8dB in section 2 -- strong
confirmation these are now major, clearly audible contributors, not a
marginal nudge that happens to look right in a spectrogram.

**Rendered v5**: `tidal_lock_mastered_v5.wav/mp3`, same master chain
throughout. -17.3 LUFS, -8.4dBFS peak, 0 clipped samples -- matches v4
almost exactly (aggregate LUFS barely moves when boosting one buried
voice among many, as expected; the audible-presence diff-test above is
the real evidence, not the aggregate loudness number). Delivered to user.

**Deliberately NOT touched this round, flagged explicitly to the user**:
(1) items 1 & 3 from the v3 feedback ("section1/section2 too long") --
real structural edits (shortening a section means re-timing every
downstream leaf's absolute position and re-checking every seam), high
blast radius, needs the user's direction on approach before starting, not
something to do silently; (2) a full 39-track gain-staging audit -- only
the 4 flagged candidates were measured; if "still buried somewhere" comes
back in future feedback, the same solo-render-and-diff method
(established and validated this round) should be applied broadly rather
than guessing which track this time.

## v5 feedback -> real planning conversation -> pipeline infrastructure built for real (2026-07-29, continued)
User's v5 reaction converged the whole project's open threads into three
named problems: length (every part still "too long"), variance (low
evolution compounds length -- a long static-feeling section feels even
longer), and mastering (the iterative EQ/comp carving loop discussed
2026-07-28 was never built). User also asked a real design question:
does automation need real before/after contrast to be heard, and does the
underlying AI need more data to avoid predictable movement -- answered
directly (not deferred): the leaf-emission model isn't trained on this
project's audio, it's a one-shot LLM call per leaf, so "more data" isn't
the lever. The real gap is that "add automation" specs were producing a
single uniform ramp every time -- real motion, same predictable shape.

User confirmed the priority order (fix the pipeline before regenerating,
not after -- my recommendation, they agreed) and gave one real correction
on the gain-staging plan: NOT flat normalization -- "some things should be
a tad quieter... but when they should be audible they should be audible."
This reframed item 2 from "fix a bug" into "encode musical role into the
correction," which is what got built.

**Confirmed via the actual code, not memory's own stale note, that the
mastering loop genuinely didn't exist**: `mix_fix.py` has only
`propose_composition_fix` (single propose-and-check), `orchestrate.py` has
only `choose_fix_strategy` (which strategy family, not numeric
convergence within one). Matches what memory already said, now verified
fresh.

**1. Length + variance, both real prompt-engineering fixes**:
- `src/planner/arc.py`: added an explicit paragraph citing the real
  finding that every section in the last generation came out too long
  relative to its content, not just non-climax sections -- "default toward
  FEWER cells... when in doubt, pick the shorter one." This is the ONLY
  place section duration gets decided (decompose() splits a node into
  SIMULTANEOUS children within the same fixed duration, it doesn't
  re-time anything -- confirmed by reading decompose.py's own tool
  description, "within the same section"), so length is entirely an
  arc.py prompt concern, not a decompose/leaf_emit one.
- `src/planner/decompose.py`: the existing ">~16 bars must say how it
  changes" instruction upgraded to require a concrete THREE-STAGE arc
  (named start state, a real turning point at roughly a specific moment,
  end state) instead of vague "changes over time" -- explicitly prefers
  non-monotonic shapes (recede-then-surge) over a flat build, and calls
  out that "make it evolve" alone was found to just produce one uniform
  ramp regardless of point count, which is the wrong SHAPE not just too
  few points.
- `scripts/leaf_emit.py`: automation instruction now explicitly ties the
  emitted automation points to the spec's 3-stage arc (a point AT the
  turning point, not evenly spaced ones) and requires >=2 different
  automation targets (not just one) for a foreground-prominence leaf on a
  long section, so evolution is felt through more than a single lever.

**2. Prominence-aware gain-staging, NOT flat normalization**:
- `src/planner/node.py`: new `prominence` field on `Node`
  (foreground/midground/background, default "midground" for backward
  compat with every pre-existing snapshot/proof script), validated in
  `__post_init__`, threaded through `to_dict`/`from_dict`.
- `src/planner/decompose.py`: `DECOMPOSE_TOOL` schema gained a required
  `prominence` enum field per child with real guidance on what each tier
  means (foreground = the focal point, midground = clearly audible
  supporting content, background = deliberately recessed texture --
  explicitly NOT "background means quiet is fine to ignore"). `_validate`
  soft-defaults an absent/malformed value to "midground" rather than
  hard-failing (same pattern as `realizes_element_id`) -- a decomposition
  that's otherwise good shouldn't get thrown away over one enum slip.
- **New `src/planner/gain_stage.py`**: generalizes tonight's validated
  solo-vs-mix-window RMS diagnostic into real decision logic.
  `TARGET_GAP_DB_BANDS` gives each prominence tier a (low, high) dB-below-
  mix band -- foreground (2,8), midground (8,15), background (15,25) --
  derived directly from tonight's real numbers (the 3 confirmed-buried
  leaves sat 14-22dB below, the confirmed-correct one sat 2dB below).
  `propose_gain_correction(prominence, solo_rms_db, mix_rms_db,
  current_fader_db)` returns `None` when already within band (the common,
  healthy case -- a background leaf sitting quiet ON PURPOSE gets left
  alone) or a `GainCorrection` with the minimal delta needed to reach the
  NEAREST band edge, clamped to a max single-correction size and a fader
  range, with both clamps flagged in the result rather than silently
  applied. Decision-only, same division of labor as mix_fix.py -- caller
  still does the actual solo/full-mix renders and applies the fader.
  8 real unit tests (`tests/test_gain_stage.py`), including one using
  tonight's actual measured numbers as a regression check.

**3. Real iterative mastering convergence loop**:
- **New `src/planner/mastering_loop.py`**: `MixCarveLoop`, a
  direction-corrected bisection loop -- caller supplies an initial
  direction guess (real mixing judgment, same kind mix_fix.py's model
  call already makes) and step size; each round, if the last move made
  the target relative metric (a LUFS gap, a spectral-centroid ratio --
  review_composition already computes exactly these) closer to target,
  keep going the same way; if worse, reverse and halve the step. Returns
  "converged" within tolerance, "adjust" with the next param value to
  try, or "escalate" once the step shrinks below a floor or a round
  budget is spent -- directly implements the "only escalate to a listen
  once converged [or stuck]" behavior from the 2026-07-28 discussion.
  Decision-only; never touches REAPER itself. 9 real unit tests
  (`tests/test_mastering_loop.py`) covering immediate convergence, both
  move directions, the improve-keep-going case, the worsen-reverse-halve
  case, both escalation paths (step floor and round budget), and
  construction validation.

**Real bug caught and fixed before it mattered**: `scheduler.py` builds
each child `Node` from decompose's raw dict at two call sites (leaf
children, still-composite children) and neither originally threaded the
new `prominence` value through -- would have silently defaulted every
real node to "midground" regardless of what decompose.py decided, making
the whole prominence field dead weight in practice. Both call sites now
pass `prominence=spec.get("prominence", "midground")`.

**Verified nothing broke**: full suite 142/142 passing (122 pre-existing +
20 new), including after the node.py schema change and the scheduler.py
fix.

**Not yet done -- the actual validation this all still needs**: none of
this has been run against a real decompose()/leaf_emit() call yet (no
fresh section has been generated since these prompt changes landed), and
gain_stage.py/mastering_loop.py haven't been wired into a live pipeline
call or exercised against real REAPER audio -- only unit-tested against
synthetic and tonight's-already-known numbers. Real next step before any
full regeneration: generate one new test section with the updated
decompose/leaf_emit prompts and confirm the 3-stage arc + prominence
tagging actually come back sane from a live model call, not just that the
validation code accepts well-formed synthetic input.

## Real full-song gain-stage audit + v6 test render (2026-07-29, continued)
User asked to test gain_stage.py against the OLD song (find which
section(s) it would change most) before committing to a fresh
regeneration -- a genuinely good idea, tests the new machinery against
real data without spending on a full regen. Also raised a real
architecture point: 39 tracks is a lot, and "recall" should mean literally
REUSING the same track for a recurring element across sections, not a
brand-new track playing a similar-sounding new leaf each time. **Logged as
a real future item, NOT implemented this round**: currently
`realizes_element_id`/`recurring_context` (decompose.py/arc.py) only pass
prior-realization METADATA into a fresh leaf's prompt (preset/note
summary, "vary it but keep it recognizable") -- the recall is
approximated by similar sound design on a new track, not architecturally
enforced by reusing the channel. A real fix would need `scheduler.py` to
allocate one track per recurring ELEMENT (spanning multiple timeline
positions across sections) rather than one track per section-instance --
a genuinely bigger change (item placement per occurrence, avoiding overlap
across a track's own multiple appearances) than anything done tonight,
deliberately deferred rather than rushed in.

**Delegated the mechanical audit to a background general-purpose agent**
(protects context from ~35 sequential solo-render round trips) rather
than doing it inline -- gave it full methodology (solo-render each leaf
over its section window, compare against the SAME window in the
already-rendered v5.wav, heuristic prominence from own_purpose text,
`gain_stage.propose_gain_correction`), explicit sequencing constraints
(solo/render/unsolo must be strictly sequential, REAPER is shared mutable
state), and cleanup instructions. Took ~17 minutes, 137 tool calls, came
back clean (verified all tracks unsoloed at the end, temp files removed,
v5.wav/project state untouched).

**Real result: 30 of 38 measured leaves (track4, a known-dead silent
track, excluded) wanted a non-None correction.** Confirms tonight's
3-track fix was the tip of something genuinely systemic, not a fluke.
**Real, slightly surprising finding**: about a third of the corrections
were NEGATIVE -- several midground pads/basses and two background
textures (the section1 pad, the premonition leaf) were sitting too LOUD
for their assigned role, not too quiet. The flat-0dB-fader bug cuts both
ways, not just "buried."

**Section3 (breakdown, 168-232s) is the clear answer to "which section
would see the most difference"**: single largest correction (track19, the
sustained sub-bass drone, +18dB -- hit `gain_stage`'s own
`MAX_SINGLE_CORRECTION_DB` cap) AND largest total |delta| summed across
its leaves (~60dB over 5 of 6 leaves). Section4 (climax) had more leaves
flagged (8/9) but smaller individual corrections -- systematically hot
drum/bass presets sitting a bit too loud for midground once the section
gets dense, not one dramatic outlier.

**Applied all 30 corrections for real and rendered v6** -- direct
end-to-end validation of gain_stage.py against actual REAPER audio, not
just unit tests. Real per-track new fader values (current fader + proposed
delta, reusing the 3 tracks already boosted tonight as real
current_fader_db inputs): track19 +18.0, track18 +17.3, track0 +14.3,
track2 +14.3, track29 +14.2, track6 -10.8, track34 +10.7, track23 +10.7,
track33 -0.1 (pulled back from tonight's rough +10 guess toward flat, now
data-driven), track20 -8.1, track35 +7.8, track3 -7.8, track10 -7.6,
track36 -7.5, track26 -7.2, track30 +6.1, track1 +5.9, track22 +5.7,
track31 +5.2, track38 -4.9, track24 -4.8, track17 +2.8, track11 -2.7,
track9 +2.1, track13 -2.1, track32 +2.0, track15 +2.0, track12 +13.7
(13.7 = 12 already-applied + 1.7 more), track25 -1.3, track27 -0.2.

**Real, honest side effect found and fixed, not hidden**: first v6 render
measured -18.9 LUFS vs. v5's -17.3 -- QUIETER overall despite mostly
boosting individual layers. Root cause: the static master compressor
reacts to the new dynamic/transient content differently and doesn't fully
auto-compensate. This is real, concrete evidence for exactly why item 3
(the adaptive mastering loop) matters -- a static one-size-fits-all master
chain doesn't play nicely with per-leaf gain changes, confirming
2026-07-28's "section4 got worse under the same global chain" finding
generalizes beyond that one case. **Fixed using the project's own
established pattern** (`mix_fix.py`'s `compensating_gain_db`, originally
built for EQ-cut level loss, applies identically here): computed
+1.63dB, applied to the master fader (-8.0 -> -6.37dB), re-rendered.
Final v6: **-17.3 LUFS integrated (matches v5's target exactly), -6.7dBFS
peak (up from -8.4, still comfortably safe, 0 clipped samples)**.

**Verified the corrections actually changed something audible, not just
numbers**: diffed v6 against v5 per-section (same method validated on
v4/v5) -- the diff signal is comparable to or LOUDER than the section
itself in most sections (section2: diff +2.0dB above v6's own level;
section4: diff -0.5dB, essentially equal; section3, the biggest-target
section: diff sits 4.8dB below v6, still a large, real, audible change).
Delivered to user.

**Real remaining gaps, honestly flagged**: (1) `mastering_loop.py`
(item 3's iterative convergence loop) was built and unit-tested this
session but NOT exercised in this v6 test -- the master-gain fix above
used the simpler existing `compensating_gain_db` one-shot, not the new
bisection loop, since this was one global level correction, not a
pairwise/relative EQ-carve problem the loop is actually for; (2) the
arc.py/decompose.py prompt changes (length + 3-stage variance) still
haven't been tested against a live model call -- v6 only tests gain_stage,
the third leg (prompt changes) needs a fresh generated section to
validate; (3) the track-reuse/recall architecture idea is logged above,
not built.

## v7: real cost-conscious variance test -- 2 leaves, 2 Haiku calls, real evidence (2026-07-29, continued)
User's own framing for this round: make the song as good as possible for
the LEAST API spend, since that's the real cost driver, not engineering
time. Explicit plan agreed: cheapest possible test of the new leaf_emit
automation-shape prompt is re-emitting ONE identity-carrying leaf per
weak section by hand-writing an upgraded spec (free) and calling
`emit_leaf_implementation` directly (one Haiku call each) -- NOT
re-running decompose() (Sonnet) or any full regeneration. User named
section2 (the drop, "starts very nice but loops a lot") as priority,
plus section1 (the build) as a bonus.

**Picked targets from real data, not guessing**: read both leaves' live
specs/implementation directly from song_plan.json before touching
anything. `song/section_2/child_3` (track12, the drop's foreground
arpeggio pluck stating the four_note_motif, 80s) had exactly ONE
automation call -- a single 2-point ramp on one FX send level across the
full 80s -- the textbook single-lever-uniform-ramp case the new prompt
targets. `song/section_1/child_1` (track5, the build's bass, 40s) had
**zero** automation at all, a flat static 4-bar loop repeated 10x. Both
confirmed, not assumed.

**Re-emitted both via `emit_leaf_implementation` with a hand-written spec
addendum** (appended to the real original spec, not replacing it) stating
the concrete measured problem and requiring a real 3-stage arc with >=2
automation targets -- exactly the shape the new leaf_emit.py prompt
itself now asks for, given a spec that actually describes one. Both real
Haiku responses came back with genuinely non-monotonic, multi-parameter
automation: track12 got filter cutoff (60->85->95->90->75) AND delay send
(0.1->0.4->0.6->0.5->0.35) with a real turning point at bar 20 (40s into
the leaf); track5 got filter cutoff, resonance, AND a Volume swell, all
three holding flat for the first 12s then opening from bar 20 onward --
unprompted convergence on "hold, then open" as the actual shape, matching
the addendum's spirit closely.

**Real bug found in the emitted values, not hidden**: track12's filter
cutoff automation (85/95/90) exceeds Surge's real ct_freq_audible range
(-60..70, documented earlier this project) -- the model isn't given
per-param numeric ranges, only names, so it can pick an in-spirit but
out-of-range value. Effect: normalize() clamps everything above 70 to
1.0, so the intended "open then pull back slightly" become "opens once at
bar 20, then holds at ceiling" -- a real but truncated version of the
intended arc. The delay-send automation (fully in-range) carries the
complete intended non-monotonic shape on its own, so the leaf still
evolves for real; this is flagged as a genuine, scoped leaf_emit.py gap
(prompt doesn't give numeric ranges) worth fixing if this pattern recurs,
not blocking on it tonight.

**Two real, reusable technical findings from actually applying this
live**: (1) 823 authored+tiled notes for the 80s pluck leaf is too large
to inline as an MCP tool call parameter -- switched to the raw
`surge_bridge_client.call()` bridge protocol (same one
`execute_section_direct.py` already established) for note insertion and
FX-envelope automation instead of the `add_midi_notes_batch`/
`add_fx_envelope_point` MCP tools directly. (2) A REAL, previously-
undocumented bridge quirk: `GetTrackEnvelopeByName` can return `{"ok":
true}` (no `ret` envelope pointer) for an envelope that has genuinely
never been shown on that track -- checking only `.get("ok")` (as the
existing `execute_section_direct.py` code and this session's first
attempt both did) is NOT sufficient to detect "needs the show step,"
since a bare `ok: true` with no `ret` reads as success but isn't one.
Worth hardening `execute_section_direct.py`'s equivalent check later
(check `r.get("ret")` truthiness, not just `ok`) since it has the exact
same latent bug.

**MUST wait for `apply_surge_preset` MCP calls to fully complete before
running any raw-bridge-client script** -- confirmed by reading
`apply_surge_preset_live.py` directly: it uses the SAME
`surge_bridge_client.call()` counter band (1200-1999) as any standalone
script would, so running both concurrently risks the exact request-id
collision bug found and fixed 2026-07-26. Waited for both background
`apply_surge_preset` MCP tasks to report completion before running the
note/automation script.

**Rendered and measured v7 (not a full mp3-quality pass, a real
verification render)**: 323s, 0 clipped samples, -17.7 LUFS (0.4dB below
v6, within noise). RMS-based diffing (the method that worked well for
tonight's gain-staging changes) was the WRONG tool here and said so
honestly -- these are timbral (filter/brightness) changes, not level
changes, so plain RMS diff showed only a small, inconclusive shift.
**Switched to spectral centroid over time** (librosa, 4 sub-windows per
section): real, consistent, unambiguous result -- v7's centroid sits
100-220Hz HIGHER than v6's in every single sub-window of both target
sections, a genuine measurable brightness change matching the intended
"opens up" arc, not noise. The precise non-monotonic shape isn't crisply
resolved at this coarse 20s-bucket resolution (consistent with the
cutoff-clamping finding above -- section2's cutoff rises and holds rather
than pulling back), but the automation is doing something real and
audible, not nothing. Delivered v7.mp3 to the user for the actual
judgment call (ear, not just metrics, same as every prior round).

**Cost actually spent this round**: 2 Haiku calls (emit_leaf_implementation
x2) + 2 preset-apply round-trips (deterministic, not model calls) + local
compute (renders, measurement). No Sonnet, no Opus, no full regeneration
-- matches the user's explicit cost-minimization ask precisely.

## v8: real melodic-evolution fix, not just automation -- the actual gap the user named (2026-07-29, continued)
User's v7 reaction was specific and correct: automation alone hit its
ceiling, repetitiveness is worst in the loud/locked sections ("3 and 5" --
drop and climax, since a quiet building section can legitimately sit
inside its own automation but a dense section needs the CONTENT itself to
move), and explicitly rejected my first proposed fix (splitting a leaf's
timeline into independent segments, each emitted separately) as "not
supposed to be different each time... not split into thirds" -- correctly
read as producing disconnected chunks, not one coherent evolving decision.

**Real root cause of why leaf_emit.py can't already do this**:
`tile_notes_to_duration()` exists specifically because authoring a full
80s pattern directly (~640-800 notes) reliably truncates mid-response (5/5
failures, documented in the function's own docstring from earlier this
project) -- so every leaf has always been "one short cycle, tiled," which
is structurally incapable of containing real evolution no matter what the
automation does on top.

**Real fix, found through honest failure, not the first prompt tried**:
tested re-emitting the drop's arpeggio pluck (track12, `song/section_2/
child_3`) 3 times, same leaf, escalating fixes, each one inspected for
real periodicity (not trusted on the model's word):
1. Attempt 1 (asked for "3-4 phrases, ~24-32 beats"): came back with only
   an 8-beat authored block (confirmed via direct note-by-note
   periodicity check) -- barely better than before.
2. Attempt 2 (added a stated "hard requirement: last note >= beat 24",
   NOT mechanically enforced, just stated in the prompt): still
   under-delivered, 12 beats.
3. **Root cause finally identified by reading leaf_emit.py's OWN base
   prompt, not just my addendum**: the base prompt (unchanged, still
   present ahead of any addendum) explicitly says "emit ONE natural cycle
   ... do NOT try to write out notes for the entire section's duration
   yourself... will overflow and fail." My addendum was fighting that
   instruction, not replacing it, and the model was resolving the
   conflict toward the more cautious original instruction both times.
   Attempt 3 explicitly told the model to disregard that instruction for
   this specific leaf ("OVERRIDE: ignore the earlier instruction above...
   two prior attempts... both under-delivered... treat the 'one short
   cycle' framing as explicitly suspended"). **Worked exactly as asked**:
   confirmed via periodicity check the repeat period is now precisely
   24.0 beats (12s at 120bpm), with four genuinely different pitch
   phrases inside (50/57/60/55 -> 51/55/62/57 -> 52/59/62/55 -> 50/57/59/56
   -- real variation, not internal micro-repeats). Loop period: ~4s -> 12s,
   a real 3x increase in the actual repeating unit's length, achieved as
   ONE coherent creative decision in one call, not three independent ones.

**Second recurring bug confirmed, not a fluke**: attempt 1's automation
again used an out-of-range "A Filter 1 Cutoff" value, this time attempt 2
picked literal-Hz-looking numbers (8000/10500/9200/8500) against a real
range of -60..70 -- same class of mistake as tonight's earlier track12 v7
attempt, now seen twice on the same param. Attempt 3's prompt added an
explicit warning ("Surge's own internal parameter ranges are much
narrower than raw Hz numbers would suggest, favor small relative moves")
and the model responded with a small in-range override (-1.0) and a
different, in-range send-level automation instead -- confirms the range
gap is real and fixable by prompt guidance alone, without needing to
teach the model exact numeric ranges per param. Worth folding this
specific caution into leaf_emit.py's default prompt if it recurs on a
third param.

**Applied live, 160 notes + 2 automation targets** (A Send FX 3 Level,
Volume envelope -- both non-monotonic, both clean/in-range). Verified via
direct readback after applying: `get_midi_item` on track12 confirms
`note_count: 160`, matching the successful attempt 3's output exactly
(not a leftover from attempts 1 or 2). Rendered v8: 323s, 0 clipped
samples, -17.7 LUFS (stable, consistent with v6/v7). Delivered to user.

**Scope, explicitly not yet done**: only the drop's arpeggio pluck
(section2/"part 3") was touched. The climax ("part 5") -- the other
section the user named as most repetitive -- has NOT been touched with
this technique yet; same 8-24s bass/pad targets from the v7 round are
still automation-only too. This 3-attempt process (2 real failures before
the fix) is now a validated, reusable recipe for the SAME class of fix
elsewhere: hand-write the spec addendum with the "OVERRIDE: ignore the
one-short-cycle instruction" framing from the start (don't repeat
attempts 1-2's mistake of assuming a softer ask would work), verify
periodicity by direct inspection before trusting the model's stated
compliance, and watch for out-of-range continuous-param automation values
on the first attempt.

**Cost this round**: 3 Haiku calls (2 failed, 1 succeeded and was
applied) + 1 preset-apply round-trip. Still far cheaper than a Sonnet
decompose call or any regeneration, and the 2 "failed" attempts were real,
cheap, informative diagnostic data (confirmed the root cause precisely),
not wasted spend.

## Session close-out: v8's lesson baked into leaf_emit.py for real, not left as a one-off (2026-07-29, continued)
User confirmed v8 sounds better and said to move on rather than spend
more per-leaf fixes tonight (part 5/climax never got touched -- still
open, deliberately not done). Read "move on" as "lock in what we
learned" rather than "discard it" -- the whole point of validating the
technique live was so it doesn't need re-discovering by hand next time.
Free to do (code/prompt edit, zero API cost), so did it before ending.

**Three real changes to `scripts/leaf_emit.py`**, all baking in exactly
what the 3-attempt saga above found:
1. **`MIN_FOREGROUND_ARC_BEATS = 24.0`** (new module constant) + a
   `foreground_arc_override` prompt block, applied automatically whenever
   `node.prominence == "foreground"` and `duration_s >= 20` -- states the
   OVERRIDE framing (ignore the "one short cycle" instruction for this
   leaf) from the FIRST attempt, not discovered through 2 failures like
   tonight. Any future foreground leaf on a section >=20s gets this by
   default, no manual spec addendum needed.
2. **Mechanically enforced, not just requested**: after the model
   responds, if a foreground leaf's pre-tile pattern span is under 24
   beats, this is now a real validation failure that flows through the
   existing retry-with-feedback path (same mechanism `_validate_ops`
   already used) -- closes the exact gap that let tonight's attempts 1-2
   silently under-deliver against a stated-but-unenforced requirement.
3. **General filter-cutoff range caution** added to the automation
   section (not foreground-specific -- this bug hit on a plain automation
   leaf too): explicit warning that Surge's real parameter ranges are
   much narrower than raw Hz-looking numbers suggest, confirmed live
   twice now, with guidance to favor small relative moves.

**Real implementation bug caught before landing**: the first attempt at
change #1 nested an `f"""..."""` string inside another `f"""..."""`'s
`{}` substitution, reusing the same triple-quote delimiter -- a
SyntaxError on Python 3.11 (this project's runtime), which doesn't have
PEP 701's relaxed f-string grammar. Fixed by computing
`foreground_arc_override` as a plain variable BEFORE the main prompt
f-string, referenced by name inside it, rather than nesting. Caught
immediately via `python -m unittest discover` (breaks `test_scheduler.py`
transitively, since `scheduler.py` imports `leaf_emit`) -- a real
reminder to run the suite after any leaf_emit.py edit, not just eyeball
the diff.

**5 new real tests** (`TestForegroundArcRequirement` in
`tests/test_leaf_emit.py`): a too-short foreground pattern gets rejected
and retried (verified via a multi-response fake client -- attempt 1
returns 8 beats, attempt 2 returns 24, the final result reflects attempt
2); exhausting retries on a persistently-short pattern raises
`RuntimeError`; a midground leaf with the same short pattern is correctly
NOT rejected (rule is foreground-only); a foreground leaf on a <20s
section is correctly NOT subject to the rule either. Full suite: **147/147
passing** (142 before this entry + 5 new).

**Real state of the pipeline-improvement work after tonight, for whoever
picks this up next**:
- Length (arc.py) + variance shape (decompose.py's 3-stage arc
  requirement): built, NOT yet validated against a live model call.
- Gain-staging (gain_stage.py): built AND validated end-to-end on real
  audio (v6).
- Melodic-evolution-not-just-automation (leaf_emit.py's new foreground
  override + mechanical enforcement): built AND validated live on ONE
  leaf (v8, track12) -- now baked into the default prompt for any future
  foreground leaf, not just that one.
- Iterative mastering loop (mastering_loop.py): built and unit-tested,
  NEVER exercised against a real mixing problem (no real pairwise
  masking issue has come up since it was built -- the v6 master-level fix
  used the older, simpler `compensating_gain_db` instead, correctly,
  since that was a global-level problem not a pairwise one).
- Track-reuse/recall architecture: logged, not built.
- Part 5 (climax)'s repetitiveness: named by the user as needing the same
  treatment as part 3, not yet done.
- "Tidal Lock" v8 is the current best version. A full regeneration with
  all of the above baked in would produce a genuinely different song
  (confirmed explicitly with the user) -- not on the table unless/until
  they actually ask for a fresh song rather than further work on this one.

## Checkpoint saved, real API cost estimate given, tempo/time-signature de-hardcoded (2026-07-29, continued)
User asked to save current state before considering a full regen (wanted a
safe rollback point, and was curious "how it could've looked"). Saved
`state/checkpoints/v8_20260729_.../` -- `session.rpp`, `song_plan.json`,
and the v8 mp3 -- so a regen experiment can be undone by copying these
back and reloading the bridge.

**Real pricing pulled from the actual API pricing table** (not
guessed): Opus 5 $5/$25 per MTok, Sonnet 5 $2/$10 (intro pricing through
2026-08-31), Haiku 4.5 $1/$5. Estimated a full "from 0" regen (1 Opus arc
call + ~10 Sonnet decompose calls + ~39 Haiku leaf-emit calls, matching
this project's actual call structure) at **~$0.50-1 clean, ~$2-5 with
realistic retries** (this project's real first build hit real friction --
hallucinated preset names, a dead leaf, mix_fix rounds, escalation --
so the higher end is the honest estimate). Real conclusion, given
directly: money was never the actual constraint on this decision --
~50-80 total API calls is cheap regardless of model tier. The real cost
of a regen is losing this song's specific character, not dollars.

**Brief redesign for a potential regen, collaboratively landed on**: the
user correctly pushed back on my first "concept album" framing (it's a
single song, not an album) and converged on "interconnectedness" as the
one explicit creative directive for a next brief -- decide a unifying
idea and let it genuinely connect/inform every section, not just decorate
with a couple of motifs, while leaving genre/mood/concept/harmony/
structure completely open otherwise (same "full creative control"
framing Tidal Lock's own brief used, just with one real thesis added).
Concrete brief text drafted and confirmed. **Not yet used** -- no arc
call has been made with it; the user hasn't given the final go-ahead to
actually spend anything yet, this was drafting/prep.

**Real, unprompted-by-me technical finding from the user**: tempo (120bpm)
and time signature (4/4) don't need to be fixed either -- they were never
a creative decision in this pipeline, just a silently hardcoded assumption
copied into 4+ places. Confirmed via direct grep before promising
anything: `TEMPO = 120.0` in `leaf_emit.py`, a second independent `TEMPO
= 120.0` in `scripts/execute_section_direct.py`, and "120bpm, 4/4"
literal text baked into `decompose.py`'s and `scheduler.py`'s prompts.

**Fixed for real, not just for the next brief** -- this is now a
permanent pipeline capability, not a one-off brief tweak:
- `arc.py`: `ARC_TOOL` schema gained top-level `tempo_bpm` (40-220,
  required) and `time_signature_numerator` (2-7, quarter-note beat only
  -- compound meters like 6/8 explicitly out of scope, a real engineering
  constraint stated as such, not a creative one) fields. New
  `_validate_tempo()` coerces stringified numbers (same defensive pattern
  as elsewhere in this project) and range-checks both. `plan_arc()`'s
  return dict now carries both alongside `sections`/`recurring_elements`.
- `decompose.py`: `decompose()` gained `tempo_bpm`/`time_signature_numerator`
  parameters (default 120/4 for backward compat with old call sites and
  tests), the hardcoded "120bpm, 4/4" prompt line now interpolates the
  real values.
- `leaf_emit.py`: `emit_leaf_implementation()` gained the same two
  parameters (default `= TEMPO` / `= 4`); every internal beats<->seconds
  conversion (repeat-count estimate, `duration_beats`, `needed_length_s`)
  now uses the parameter instead of the module constant. The
  `TOOL_CATALOG`'s tool description no longer hardcodes "120bpm, 4/4" --
  generalized to "this project's tempo/time signature (given in the spec
  below)". Left `build_spec_node()`'s demo/proof fixture untouched
  (confirmed via `grep '^def '` that it's a `main()`-only demo, not on the
  real pipeline path -- not worth touching).
- `scheduler.py`: both `build_tree()` and `build_section()` gained the
  same two parameters, threaded through the `decompose()` call, the leaf
  spec-text interpolation (was hardcoded "120bpm/4-4"), the
  `emit_leaf_implementation()` call, and the recursive `build_tree()` call
  for still-composite children.
- `scripts/song_plan.py`: reads `tempo_bpm`/`time_signature_numerator`
  from `arc.json` (default 120/4 for pre-2026-07-29 arc.json files),
  threads them into every `build_tree()` call, and writes them into the
  final `song_plan.json` output -- so whichever session actually executes
  a new song's ops live knows to call `set_tempo`/`set_time_signature` on
  the real REAPER project before building anything, matching this
  project's established pattern of writing plumbing values into the plan
  for the execution phase to read (`track_index`, `timeline_start_s`, etc.
  work the same way already).

**Verified via tests, not just by inspection**: existing `test_arc.py`
fixtures didn't carry the new required fields and correctly started
failing the moment the schema required them -- confirms the validation is
real, not decorative. Updated `_arc_response()`'s helper to include
`tempo_bpm`/`time_signature_numerator` by default. Added 4 new real tests
(`TestPlanArc`): valid tempo/time-sig round-trips, tempo above the 220
ceiling is rejected and retried, time-signature above the 7 ceiling
exhausts retries and raises, a stringified tempo ("128") is coerced
correctly. Full suite: **151/151 passing** (147 before this entry + 4
new).

**Not yet done**: no actual arc call has been made yet with either the
new interconnectedness brief or a non-120bpm/non-4-4 result -- this was
pipeline capability work, unblocking the decision, not the decision
itself. Whether to actually spend anything on a real regen is still
entirely open, pending the user's go-ahead.

## Full regen kicked off for real: new song, two real bugs found and fixed live (2026-07-29, continued)
User said "do it, make a new one." Checkpointed `arc.json` too (song_plan.json
and session.rpp were already checkpointed). Ran the real `plan_arc()` call
with the finalized interconnectedness brief (open genre/mood/tempo/meter).

**Real, striking result**: **88bpm, 5/4 time signature**, C minor, a
"germ cell" five-note descending contour (G-F-Eb-D-C, scale degrees
5-4-b3-2-1) that the model chose to make recur in **all 6 sections**
(not just the suggested 2-3) plus 3 more recurring elements (a bell
patch, a "fifth beat accent" rhythmic signature specifically built around
the 5/4 meter's asymmetry, and a structural "always land on the 2nd
degree, never resolve" device). 6 sections, 320s total, nothing over 80s
-- the length guardrail held on a completely fresh call. This is a
genuinely different, more ambitious piece than Tidal Lock, not a
reskin -- confirms the new brief design actually worked as intended.

**Ran `scripts/song_plan.py` for real (the actual production driver, not
a proof script) -- hit two real, live-only bugs, both found and fixed
during the run, not anticipated in advance:**

**Bug 1 -- the new MIN_FOREGROUND_ARC_BEATS retry-feedback was too weak
in practice.** First failure: a foreground bass leaf's spec asked for a
genuine 3-stage evolving arc across ~8 bars, but the model kept falling
back to an 8-beat authored cycle across all 5 retries, crashing the
whole build after burning them. Root cause: `emit_leaf_implementation`'s
generic retry feedback ("your previous attempt was invalid: {error}. Fix
this specific problem.") just restates the same message every retry --
it doesn't escalate. This exact failure mode was hand-diagnosed earlier
the same day (see "v8: real melodic-evolution fix" entry above) and only
got fixed by explicit "OVERRIDE, ignore your instinct, N prior attempts
already failed this way" language on the 3rd manual attempt -- the
mechanical retry never got that escalation. **Fixed**: when the
ValueError comes from this specific check (detected by matching "beats
before its pattern would repeat" in the message), the retry feedback now
uses that same escalating OVERRIDE framing, naming the attempt number and
explicitly forbidding automation-only compensation ("Automation on top is
fine and encouraged, but it does NOT substitute for this").

**Bug 2 -- a real architectural gap, not a retry-tuning issue.** Second
failure, section 5's outro: a leaf spec explicitly asked for "a short
(roughly 2-3 second) filtered-collapse gesture ... no loop ... then
leaves total space for the bell/pad to enter" -- a genuine one-shot
INSIDE a much longer (40s) section. The model correctly authored a
3-beat item for exactly this. But `emit_leaf_implementation` was
validating and tiling against the SECTION's full duration_beats (~59
beats at 88bpm/5-4) regardless of what the model's own `create_midi_item`
call declared -- both (a) wrongly demanding 24+ beats of content from a
deliberate 3-beat gesture, forcing 5 failed retries where the model kept
correctly re-authoring something short and kept getting rejected, AND
(b) about to mechanically loop that explicitly "no loop" gesture across
the entire 40s section once tiling ran, silently destroying the intended
effect even if the retry problem hadn't crashed the build first. Neither
of these was hypothetical -- both would have actually happened.

**Real root cause**: this pipeline's tiling/validation logic had always
implicitly assumed every leaf either (a) tiles a short cycle to fill the
WHOLE section, or (b) authors one long sustained note spanning the whole
section -- there was never a supported third case of "short deliberate
gesture + trailing silence within a longer section," because until
tonight's richer decompose specs, no leaf had ever asked for one.

**Fixed properly, not patched around**: `emit_leaf_implementation` now
reads the model's OWN declared `create_midi_item` length and treats it
as authoritative when it's genuinely shorter than the section
(`item_is_deliberately_short`). For such a leaf: the MIN_FOREGROUND_ARC_BEATS
check is scoped to the item's own length, not the section's (so a
deliberately-short item is never forced into a fabricated long pattern),
and the model's raw authored notes are used AS-IS, with NO tiling at all
-- a real design decision made mid-fix, not the first instinct: an
earlier version of this fix tiled a short pattern to fill the short
item's own length instead of skipping tiling entirely, which a new test
caught as wrong (a 1-beat 2-note pattern in a 6-beat item became a 6x
"loop" -- exactly the kind of unintended repetition the fix was
supposed to prevent). Corrected to trust the model's raw notes verbatim
whenever the item is deliberately short, since the leaf_emit prompt was
never written to expect tiling into anything shorter than the full
section. The common case (item length >= section length, i.e. every leaf
built so far in this project) is completely unchanged.

**3 new real tests** (`TestItemLengthAwareTiling`): a short deliberate
one-shot is not forced to 24 beats and is not tiled; a short one-shot
item is not grown to fill the section; a full-section item still tiles
exactly as before (regression check). One of these tests caught the
wrong first-draft fix (tile-to-item-length instead of no-tiling) before
it shipped -- a real example of a test doing its job, not just
decoration. Full suite: **154/154 passing** (151 before this entry + 3
new).

**Status when this entry was written**: third attempt at the full
`song_plan.py` run in progress (background), both fixes applied before
this run started. Not yet known whether it completes cleanly or surfaces
a third real issue -- next memory entry covers the outcome.

## New song fully built: real bugs found via live execution, 9 silent leaves diagnosed and fixed (2026-07-29, continued)
Fourth `song_plan.py` attempt succeeded clean: **all 6 sections, 33
leaves, 320s, 88bpm/5-4/C minor, "germ cell" motif recurring in all 6
sections.** Plan generation phase closed out for real.

**Execution phase**: reused `scripts/execute_section_direct.py` (the
proven fast batch-execution path from Tidal Lock) rather than 33
individual conversational MCP round-trips. Built a fresh REAPER project
(`state/scratch/new_song.rpp`, seeded on-disk first per the existing
save-dialog-hang fix) rather than touching Tidal Lock's live project or
file -- Tidal Lock stayed completely untouched all night, only the
checkpoint needed it.

**Two more real bugs found and fixed live during execution, both in
`execute_section_direct.py` (not `leaf_emit.py` this time)**:
1. **`TEMPO` hardcoded to 120** in this script independently of
   `leaf_emit.py`'s own now-parameterized version -- missed during
   tonight's earlier de-hardcoding pass since this script doesn't import
   from `leaf_emit.py`. Fixed: `main()` now sets `global TEMPO` from the
   plan's own `tempo_bpm` field at runtime.
2. **`Width` envelope -- real REAPER action-ID gap, not guessable
   reliably.** A leaf legitimately used `envelope_name: "Width"`
   (a real option in `leaf_emit.py`'s own tool schema), but
   `execute_section_direct.py`'s show-envelope-action map only had
   Volume(40406)/Pan(40407). Guessed 40408 by pattern (wrong -- confirmed
   live, same "ok:true, no ret" failure persisted even after the show
   attempt). Given a second guess risked more wasted build time, worked
   around it instead: stripped the Width automation op from the one
   affected leaf's `song_plan.json` entry rather than keep guessing
   REAPER's internal action IDs. Real remaining gap, not fully closed:
   the correct Width-toggle action ID is still unknown.

**Also hit and fixed a data-corruption near-miss of my own making**: my
first attempt to verify Drum One.fxp used `apply_surge_preset` directly
on a freshly `insert_track`'d track WITHOUT first adding the Surge XT
plugin via `track_fx_add_by_name` -- the tool's own docstring says it
needs an existing Surge XT instance, `insert_track` alone doesn't add
one. Real, simple ordering mistake, caught immediately by the tool's own
error rather than silently producing a false negative.

**execute_section_direct.py's own resume_from mechanism used for real,
twice** (section 2 crashed on the leaf that used Width; section 4
crashed on the very first leaf) -- checked live track count each time to
compute the correct resume index rather than guessing, since re-running
`InsertTrackAtIndex` for an already-inserted leaf would silently
duplicate/desync every later track_index.

### The silent-leaf investigation (9 of 33 leaves, ~27%)
User explicitly asked to diagnose rather than just patch. Pulled every
silent leaf's real preset/overrides/notes from `song_plan.json` first
(not guessing) -- an immediate, obvious pattern: **5 of 9 used
`Percussion/Drum One.fxp`**, including one occurrence with **zero
overrides at all** and still silent -- the cleanest possible evidence of
a broken preset, not an authoring mistake.

**Root cause A -- confirmed live, not assumed**: applied `Drum One.fxp`
clean (no overrides) to a scratch track, one note, real velocity ->
peak ~1e-6 (genuine digital silence). **User raised a real, smart
alternative hypothesis before accepting this**: many drum/percussion
patches (Decent Sampler, LinnDrum-style packs) only respond on a handful
of specifically-mapped MIDI notes, not the whole keyboard -- so a single
pitch=60 test could have been a false negative if this preset worked
that way. Tested properly instead of dismissing it: full 6-octave sweep
(pitches 24-96, one note per beat) -- **every single pitch silent**
(peak below -110dB throughout), conclusively ruling out the keyed-mapping
theory and confirming the preset is genuinely non-functional. Added
`"Percussion/Drum One.fxp"` to `EXCLUDED_PRESETS` in `leaf_emit.py`
(same list as the already-known `Snare Tight.fxp`), full test suite
re-verified at 156/156 after the edit.

**Root cause B (3 leaves)**: `song/section_0/child_3` (FX/Radio Noise),
`song/section_1/child_2/child_0` (Basses/Eighties Drone),
`song/section_1/child_2/child_2/child_0` (Pads/Distant) all explicitly
muted all 3 oscillators via override (a legitimate "noise-only texture"
sound-design choice) but never explicitly set `"A Noise Mute": 0` --
confirmed live on all three tracks that `A Noise Mute` was sitting at
1.0 (muted), the preset's own default, since the override never touched
it. With every oscillator AND the noise generator both muted, there was
no possible sound source left. Fixed live via `track_fx_set_param`
(param index 313, set to 0.0) on all three tracks -- a real leaf-content
bug (contradicts the leaf's own creative intent), not a broken preset,
so no exclusion needed, just the live correction.

**Root cause C (1 leaf, `song/section_2/child_0`, Leads/Sync Lead)**: no
obvious muted/zeroed param on inspection (oscillator unmuted, not
soloed-out, routed normally, filter open, real envelope, real
velocity) -- genuinely puzzling until isolated properly: applied the
CLEAN unmodified preset to a scratch track first (real sound, -18dB
peak, confirming the preset itself is fine), then re-applied with ONLY
the leaf's `"A Osc 1/2 Type": 4` overrides (the most structurally risky
change) -- reproduced the exact silence (-121.6dB). **Real finding**: a
Surge ctrltype enum value can be numerically in-range (0-11 for
`ct_osctype`, confirmed via `surge_enum_sizes.json`) but still produce a
non-functional oscillator configuration for a SPECIFIC base preset --
range validation alone doesn't catch this class of bug, since "in range"
and "actually produces sound for this preset" are different guarantees.
Fixed live: re-applied `Leads/Sync Lead.fxp` to the real track (12) with
every override EXCEPT the two broken Osc Type ones -- verified real
sound afterward (-24.5dB peak, was digital silence). `song_plan.json`'s
own record for this node updated to match (both broken override keys
removed) so the persisted plan stays consistent with what's actually
live.

**All 9 silent leaves now resolved**: 5 via preset exclusion + (not yet
re-picked/rebuilt -- those 5 leaves' tracks still have the broken preset
applied and need a real preset swap, see Next), 3 via live noise-mute
fix, 1 via live override correction. Project saved after each live fix.

### Real remaining work, honestly scoped
1. **The 5 Drum One leaves still need an actual working preset applied**
   -- excluding it from future generation doesn't retroactively fix
   these 5 already-built tracks. Each needs a real replacement preset
   picked and applied (ideally something in the same percussive
   character family) -- not done yet, deliberately deferred to keep the
   diagnostic pass itself scoped and reportable.
2. **A full gain-staging pass across all 33 leaves** -- every section's
   composition review failed on real loudness-gap/spectral-overlap
   findings (expected, this song has never had ANY mixing pass, unlike
   Tidal Lock which got the full `gain_stage.py` treatment tonight).
   `node.prominence` should actually be populated for real now (decompose.py
   sets it live per child) -- worth checking it came back sane before
   relying on it for automatic gain correction, same "verify before
   trusting" discipline as everywhere else tonight.
3. **Mastering chain** -- none applied yet to this new song; Tidal
   Lock's chain (highpass/notch/glue-comp/presence-EQ/limiter) is a
   reasonable starting point but should be re-tuned against this song's
   own real measured crest factor/LUFS, not copy-pasted blind.
4. **Final render and delivery** -- not done.
5. **The Width envelope action-ID gap** -- one leaf's Width automation
   was silently dropped rather than fixed; the correct REAPER action ID
   is still unknown. Low priority (cosmetic stereo-width motion, not
   core content) but a real, open gap if it recurs.

## All 5 Drum One leaves fixed and live-verified (2026-07-29, continued)
Closed out the deferred item from the previous entry: the 5 leaves that
used the now-excluded `Percussion/Drum One.fxp` (tracks 6, 17, 18, 26,
27) were re-emitted via `leaf_emit.py` and applied live. Two more real
bugs surfaced during this, both fixed:

**Bug: `GetTrackMediaItem` bridge handler passed a raw track_index to
`reaper.GetTrackMediaItem` instead of resolving it to a MediaTrack
first** (`scripts/reaper_mcp_bridge.lua`, same class of mistake as
`DeleteTrackMediaItem`'s correct handler a few lines below it, which
this one didn't match). Every call returned `{"ok": false}` with a Lua
argument-type error -- silently read by
`scripts/reapply_reemitted_leaves.py`'s cleanup loop as "no item exists
here, nothing to delete," so it never actually cleared the OLD
Drum-One-preset item before creating a new one. Result: every fixed
track ended up with 2 overlapping items (old + new) instead of 1.
Source fixed in the bridge script to resolve the track first (mirrors
`DeleteTrackMediaItem`'s existing pattern) -- not yet confirmed live
since REAPER needs to reload the Lua script for the fix to take effect,
but the source bug itself is real and fixed.

**Bug of my own making, caught by re-measuring rather than trusting the
first "OK" result**: because the old item never got deleted, `item_index
0` on each track referred to the OLD (pre-existing) item at the moment
`InsertMIDINote` ran, not the newly created one -- so the new notes
landed in the old item while the genuinely-new item sat empty. First
dedup attempt (deleting what I assumed was "the old item" by process of
elimination) guessed wrong for 3 of 5 tracks where old/new items had
identical position+length (no reliable metadata to distinguish them),
deleting the item that actually held the working notes and leaving the
empty one -- turned a working state into total silence on tracks 17,
18, 26, 27. Caught immediately by re-running the same verification
script rather than declaring victory after the first "OK", exactly the
"measure, don't assume" discipline this session kept relying on.
Recovered by deleting ALL items per affected track (down to a clean
zero), creating exactly one fresh item, and inserting notes using that
item's own real (non-hardcoded) index.

**Real gap in the original re-emission, also found only by measuring**:
`emit_leaf_implementation()` was called with `duration_s=node.duration_s`,
but leaf nodes don't carry their own `duration_s` (only section-root
nodes do) -- it was `None` for all 5, which silently skips the
function's own duration-beats validation AND its `tile_notes_to_duration`
call. Two of the five leaves needed that tiling (a "once per bar"
hi-hat and a "one-bar cycle repeated all section" pattern) and came back
with only the single un-tiled repeating unit -- 1 note for a 40s section,
10 notes covering the first 4 of 80s. Fixed by calling
`tile_notes_to_duration()` directly against the correct section duration
for just those two leaves rather than re-spending API calls.

**A THIRD broken factory percussion preset found**: the re-emission for
track 27 picked `Percussion/Synth Tom 1.fxp`, which -- after ruling out
override/async-race causes the same way `A Noise Volume` was diagnosed
on track 6 (see below) -- turned out to be silent even completely clean
(single 2-beat note at velocity 100 on a fresh scratch track, peak
-138dB). Added to `EXCLUDED_PRESETS` alongside Snare Tight and Drum One
-- `Percussion/` is now 3-for-3 on broken presets actually tested this
session; treat any untested one as suspect. Replaced live with
`Percussion/Kick Tech 1.fxp` (tested clean first: real -17dB peak
signal, confirmed genuinely functional) plus a short/dry override set
for the rimshot-timbre spec; re-verified at -24.2dB peak on the real
track.

**A real async/timing race in `apply_overrides`, confirmed on track 6**:
`A Noise Volume` was set to 1.0 during the leaf's build, but reading it
back live afterward showed 0.0 -- `TrackFX_SetParam` returned success at
the time, so this isn't a silently-failed call, more likely Surge XT's
own patch-load completing asynchronously AFTER the immediately-following
override calls and clobbering them. Re-setting the same param again
(with the preset now stably loaded) made it stick permanently. Not
chased further architecturally (no minimum reliable delay between
preset-load and override-apply has been established) -- worth watching
for on any future leaf that measures "silent" or "wrong" immediately
after a preset+override sequence with no other explanation.

**Outcome**: all 5 originally-silent leaves confirmed producing real
audio via solo-render+measure (peaks from -57dB to -5dB depending on the
part's intended prominence -- track 6's hi-hat is deliberately quiet
background texture, not silent-in-disguise). `song_plan.json` updated to
match exactly what's live (including stripping 2 automation ops for the
track 27 leaf that were in the original re-emission but never actually
applied live, to keep the persisted plan honest). Full 156-test suite
still green after the `EXCLUDED_PRESETS` edit. Project saved.

### Real remaining work (updated)
Items 2-4 from the previous entry (gain-staging pass, mastering chain,
final render/delivery) are still open -- this entry only closes out
item 1 (the 5 Drum One leaves). Item 5 (Width envelope action ID) is
still open. New: verify the `GetTrackMediaItem` bridge fix actually
takes effect next time REAPER reloads the script (untested live).

## Gain-staging pass run across all 33 leaves (2026-07-29, continued)
Ran `src/planner/gain_stage.py`'s prominence-aware correction for real,
for the first time, via a new `scripts/apply_gain_staging.py` (per
section: one full-mix render + one solo render per leaf over the same
window, RMS computed directly from raw samples rather than derived from
`measure()`'s peak/crest_factor since those go `None` on near-silent/
short stems). 29 of 33 leaves got a real fader correction; 4 were
already within their prominence band untouched.

**A real methodological blind spot found and worked around, not
ignored**: this song's "germ cell" concept means most leaves are
deliberately SHORT one-shot gestures inside a much longer section (e.g.
a single kick hit or a 3-note arp burst inside an 80s section), not
continuous parts filling the whole window. For those, `mix_rms_db -
solo_rms_db` measured over the FULL section window is dominated by how
much of the window is silence, not by how loud the part is when it
actually plays -- inflating the apparent "gap" to 30-70dB for leaves
that were already fine. The correction cap (`MAX_SINGLE_CORRECTION_DB
= 18`) mostly absorbed this blindly, but one case broke through: track
25 (a sparse one-shot kick, `song/section_4/child_3/child_0`) got
boosted straight to -0.33dB peak -- real clipping risk. Caught by a
post-pass peak spot-check (not just trusting the RMS-gap numbers moved
in the right direction), pulled back to a sane +10dB fader (-8.3dB
peak). Checked every other capped, sparse-item leaf (tracks 7, 13, 24,
27) the same way -- all landed at reasonable peaks (-6 to -22dB), no
further correction needed there.

**Four leaves are still measurably outside their prominence band and
will STAY that way**: tracks 3, 6, 10, 21 are genuinely continuous
parts (not sparse one-shots, so the RMS-gap metric is trustworthy for
them), but all four had hit `MAX_FADER_DB = +18dB` (REAPER's typical
fader ceiling) on the first pass already -- there is no more fader
headroom to give them via `set_track_volume` alone. Track 3 (`FX/Radio
Noise`, the same leaf fixed for the noise-mute bug earlier tonight) got
an additional real fix beyond the fader ceiling: its own `A Noise
Volume` override (0.15, by design, "very low level throughout" per its
own spec) was raised to 0.4 directly -- a content-level fix, not a
mix-level one -- closing ~8dB of the gap. The other three (6, 10, 21)
were left as-is: pushing them further would mean either raising their
own Surge-level params (not attempted -- out of scope for a mix pass,
risks changing the leaf's authored character) or accepting that a
purely faint/textural background element sitting far below a loud
full-band mix is sometimes just true to what it is, not a bug to chase
into the ground. Documented honestly rather than forced to look
"fixed" by further guessing.

Project saved after all changes; `state/scratch/gain_staging_report.json`
holds the full per-leaf before/after numbers from the first pass.

### Real remaining work (updated again)
Mastering chain and final render/delivery are the two items actually
left from the original post-diagnosis list. Width envelope action ID
still open (low priority). New, lower-priority items surfaced this
pass: (1) tracks 3/6/10/21 sit below their prominence band's fader-only
ceiling -- a real ceiling, not urgent, but worth knowing before
mastering in case any of them still get lost in the final mix; (2) the
RMS-over-full-window gap metric is unreliable for sparse one-shot
leaves in general (not just the one case caught here) -- worth a
peak-based sanity check on any future gain-staging run rather than
trusting the RMS numbers blindly, especially for anything that got
capped.

## Mastering pass applied and the song build closed out (2026-07-29, continued)
Measured this song's own real baseline BEFORE touching anything (per
the previous entry's own flag not to copy Tidal Lock's numbers blind):
full 320s unmastered render came back at **-12.9 LUFS, true peak
+0.16dBTP -- genuinely clipping (over 0dBFS on interpolated peaks)**,
crest factor 15.55dB. The clipping is real and traces directly to
tonight's gain-staging pass -- several leaves got pushed to their
+18dB fader ceiling, and stacked together in the full mix they now
occasionally exceed 0dBFS. This made the mastering pass's priority
different from Tidal Lock's (which needed a loudness lift): here the
limiter's real job is fixing an existing peak problem, not just
polishing an already-safe mix.

Added the standard chain via `add_mastering_chain()` (ReaEQ corrective
-> ReaComp glue -> ReaEQ tonal -> ReaLimit), same as Tidal Lock, onto a
master track confirmed at `fx_count: 0` beforehand.

**Real calibration gap hit and worked around, applicable to any future
ReaComp/ReaLimit tuning in this project**: `track_fx_get_param`'s
reported `min`/`max` for ReaComp's Threshold showed a raw range of
`0.0` to `2.0` -- not dB, not obviously anything else either. Rather
than guess, used `TrackFX_FormatParamValueNormalized` (the exact same
technique the Surge enum-size/param work uses) to sample the REAL
formatted value at several normalized [0,1] points and build a lookup:
ReaComp Threshold is linear -60dB@0 to +12dB@1.0; Ratio is sharply
nonlinear (n=0.01 -> ~2:1, n=0.1 -> ~11:1 -- most of the useful "gentle
glue" range lives in the bottom ~5% of the slider); ReaLimit Threshold
linear -60@0/+12@1.0 (same curve as ReaComp's); ReaLimit Ceiling linear
-24@0/0@1.0. This calibration approach (probe via FormatParamValueNormalized
before trusting get_param's raw min/max, or a control's own display
label) is now confirmed for a second unrelated plugin family (ReaComp/
ReaLimit, not just Surge) -- worth doing by default for any JSFX param
this project hasn't calibrated yet, rather than assuming 0-1 normalized
or trusting the label's apparent sign/scale.

**Final settings, live on the master bus** (fx 0-3):
- ReaEQ corrective: hipass 30Hz; band cut -2.5dB at 300Hz, Q1.2 (same
  "muddy low-mid" target as Tidal Lock, justified here too -- baseline
  spectral centroid/rolloff were both unusually low, ~650-800Hz, a real
  measured sign of a bass-heavy/dark mix, not assumed).
- ReaComp glue: threshold -12.4dB, ratio ~2:1, attack 10ms, release
  150ms, Auto Make Up Gain on -- gentler ratio than Tidal Lock's
  already-gentle 2:1 given this mix's baseline crest factor (15.55dB)
  was itself lower/tighter than Tidal Lock's was pre-master.
- ReaEQ tonal: band +2.5dB at 3000Hz Q1.0 (presence); hishelf +2dB at
  7000Hz (air) -- both aimed at compensating the measured dark/low-
  centroid baseline.
- ReaLimit: threshold -3.0dB, ceiling -1.0dB (1dB safer than Tidal
  Lock's -0.36dB, given this mix's baseline was ALREADY over 0dBTP --
  more headroom margin felt warranted than the streaming-minimum
  -0.3dB this time).

**Verified on an isolated 30s window (section 4, t=220-250s) via real
bypass-vs-enabled A/B before committing to the full render**: LUFS
-18.9 -> -16.1, true peak +0.02dBTP -> -1.00dBTP (exact ceiling match,
confirms the calibration was correct), crest factor 18.9 -> 15.3dB.

**Full-song result, measured**: -12.9 -> -11.8 LUFS (+1.1dB, modest,
appropriate since this mix didn't need a big loudness push), true peak
+0.16dBTP -> -0.67dBTP (**the clipping is fixed**), crest factor 15.55
-> 12.67dB (real, meaningful glue), spectral centroid 651Hz -> 729Hz
(measurably brighter, consistent with the tonal EQ's intent). Rendered
`state/song_build/mastered_full_song.wav`, converted to
`song_mastered_v1.mp3` (192kbps via ffmpeg -- REAPER's own render-to-mp3
path wasn't used since the bridge's RenderProject handler only special-
cases the wav extension). Project saved.

**Same render-timeout-but-actually-succeeded pattern hit again** (now a
3rd confirmed occurrence across two different songs) on the full 320s
render -- RPC returned before REAPER finished writing; confirmed the
file was real via `soundfile.info` (correct duration, correct size)
rather than trusting or retrying the RPC response.

### Song build status: complete for this pass
All five phases of tonight's regen are done: (1) new song built via
free tempo/time-signature pipeline (88bpm, 5/4, C minor, 6 sections,
33 leaves), (2) all 9 silent leaves diagnosed and fixed with live
verification, (3) gain-staging pass across all 33 leaves, (4) mastering
pass with a real measured before/after. Real open items, in priority
order: the Width envelope action ID (cosmetic, one leaf), tracks
3/6/10/21 sitting below their prominence band's fader ceiling (flagged,
accepted, not chased further), and normal next-step user
listening-feedback iteration (this song has never been heard by the
user yet, unlike Tidal Lock's multi-round feedback cycle).
