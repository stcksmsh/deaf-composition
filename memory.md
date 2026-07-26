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

## Next
1. Decide: take on the full Vital param-mapping build (comparable scope to the whole
   Surge effort), or prioritize elsewhere (stage 3's actual fold/tree code, Pigments).
2. Pigments: descoped from preset-value-loading (user decision) — build the macro+curated-
   param fallback surface for it directly instead.
3. Stage 3 proper (decompose/fold/scheduler — `node.py` explicitly has none of this yet)
   can now start for real: the leaf vocabulary question is settled (§8.1 + `apply_surge_preset`,
   now verified live end-to-end). The next design step is probably a minimal single-leaf
   proof: one hand-written Leaf.implementation (a couple mcp_tool calls + one
   apply_surge_preset call) executed and reviewed end-to-end, per plan §11 stage 3's own
   framing ("prove a leaf spec becomes correct audio") — before any scheduler/tree code.
