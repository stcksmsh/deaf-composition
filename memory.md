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

## Next
1. Decide: take on the full Vital param-mapping build (comparable scope to the whole
   Surge effort, no dependencies on anything else — can wait indefinitely), or keep
   pushing stage 4 (Pigments' macro fallback is the remaining low-priority item).
2. **Build real orchestration logic for chaining fix strategies** -- now backed by
   concrete evidence (not a hypothetical) that a composition failure sometimes
   needs leaf retry, sometimes needs mix fix, and sometimes needs both in
   sequence. `escalation.decide()` currently only knows "retry the same leaf" or
   "escalate to human" -- it has no way to route a composition failure to
   `mix_fix.py` vs `leaf_emit.py`'s retry, let alone chain both. This is the real
   "two criteria conflict" trigger's first genuine test case: composition-level
   fix and leaf-level fix are two different resolution strategies that can each
   partially succeed while leaving a problem the other approach would catch.
3. Run the escalation/retry loop for real on the noise leaf's total-silence failure
   -- a second, independent real case, still not done.
4. Everything built this session is still a chain of individually-run proof
   scripts, not one autonomous pipeline. Real remaining integration work.
