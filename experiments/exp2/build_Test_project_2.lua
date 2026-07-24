-- build_test_projects_2.lua
--
-- Follow-up test-project builder: (1) a 20-region batch project to check the
-- marginal-cost line holds at scale, (2) a "heavy patch" project using real
-- polyphony + automation to approximate realistic DSP load, since a preset
-- can't be dialed in from outside Reaper.
--
-- HOW TO RUN:
--   Reaper > Actions > Show action list > New action... > Load ReaScript...
--   select this file, run it. Watch the console for progress/warnings.
--
-- OUTPUT (saved next to this script):
--   batch_regions_20.RPP  - 20 x ~15s regions, native ReaSynth
--   heavy_patch_short.RPP - ~18s, dense chords + automated filter cutoff,
--                           tries Surge XT then Vital then falls back to
--                           ReaSynth (with a warning) if neither is found.
--
-- AFTER RUNNING:
--   - Open batch_regions_20.RPP once, set File > Render > Bounds = Regions
--     + "render regions as separate files", click Render once to persist
--     that setting into the project, THEN use it in exp2b (same step as
--     last time - this setting does not carry over between projects).
--   - heavy_patch_short.RPP should render fine as-is.
--   - Fill both paths into a fresh copy of exp2b_render_levers.sh's CONFIG.

local function msg(s) reaper.ShowConsoleMsg(tostring(s) .. "\n") end

local script_path = ({reaper.get_action_context()})[2]
local dir = script_path:match("(.*[/\\])") or "./"

local function new_project()
  reaper.Main_OnCommand(40023, 0) -- File: New project
end

local function add_track_with_fx(name, fx_names)
  reaper.InsertTrackAtIndex(reaper.CountTracks(0), true)
  local tr = reaper.GetTrack(0, reaper.CountTracks(0) - 1)
  reaper.GetSetMediaTrackInfo_String(tr, "P_NAME", name, true)
  for _, fxname in ipairs(fx_names) do
    local fx = reaper.TrackFX_AddByName(tr, fxname, false, 1)
    if fx >= 0 then
      msg("  added FX: " .. fxname)
      return tr, fx, fxname
    end
  end
  msg("  WARNING: none of these FX could be added: " .. table.concat(fx_names, ", "))
  return tr, -1, nil
end

local function add_midi_notes(track, start_time, n_beats, note_count, bpm)
  bpm = bpm or 120
  local end_time = start_time + (n_beats * 60 / bpm)
  local item = reaper.CreateNewMIDIItemInProj(track, start_time, end_time, false)
  local take = reaper.GetActiveTake(item)
  local ppq_per_beat = 960
  for i = 0, note_count - 1 do
    local s = i * ppq_per_beat
    local e = s + ppq_per_beat * 0.9
    local pitch = 55 + ((i * 3) % 12)
    reaper.MIDI_InsertNote(take, false, false, s, e, 0, pitch, 90, true)
  end
  reaper.MIDI_Sort(take)
  return item
end

-- Adds a block chord (multiple simultaneous notes) repeated across the
-- section - raises voice count / polyphony, which is a bigger real DSP
-- cost driver than a single melodic line.
local function add_chord_notes(track, start_time, n_beats, chord_repeats, bpm)
  bpm = bpm or 120
  local end_time = start_time + (n_beats * 60 / bpm)
  local item = reaper.CreateNewMIDIItemInProj(track, start_time, end_time, false)
  local take = reaper.GetActiveTake(item)
  local ppq_per_beat = 960
  local chord = {48, 52, 55, 58, 62, 65} -- 6-note stack -> real polyphony load
  local beats_per_chord = n_beats / chord_repeats
  for c = 0, chord_repeats - 1 do
    local s = math.floor(c * beats_per_chord * ppq_per_beat)
    local e = math.floor(s + beats_per_chord * ppq_per_beat * 0.95)
    for _, pitch in ipairs(chord) do
      reaper.MIDI_InsertNote(take, false, false, s, e, 0, pitch, 100, true)
    end
  end
  reaper.MIDI_Sort(take)
  return item
end

-- Adds an automation envelope on the first available FX param that looks
-- like a cutoff/filter (falls back to param 0 if nothing matches), and
-- sweeps it across the section - forces continuous per-block recomputation,
-- much closer to a real automated sound-design pass than a static patch.
local function add_param_automation(track, fx, start_time, end_time)
  if fx < 0 then return false end
  local param_count = reaper.TrackFX_GetNumParams(track, fx)
  local target_param = 0
  for p = 0, param_count - 1 do
    local _, pname = reaper.TrackFX_GetParamName(track, fx, p, "")
    if pname and (pname:lower():find("cutoff") or pname:lower():find("filter")) then
      target_param = p
      break
    end
  end
  local env = reaper.GetFXEnvelope(track, fx, target_param, true)
  if not env then
    msg("  WARNING: could not create automation envelope for param " .. target_param)
    return false
  end
  reaper.InsertEnvelopePoint(env, start_time, 0.1, 0, 0, false, true)
  reaper.InsertEnvelopePoint(env, (start_time + end_time) / 2, 0.9, 0, 0, false, true)
  reaper.InsertEnvelopePoint(env, end_time, 0.3, 0, 0, false, true)
  reaper.Envelope_SortPoints(env)
  msg("  added automation sweep on param " .. target_param)
  return true
end

reaper.ClearConsole()
msg("=== build_test_projects_2.lua starting ===")
msg("Output dir: " .. dir)

-- === Project A: batch_regions_20 (20 x ~15s regions) =======================
msg("\n--- batch_regions_20.RPP ---")
new_project()
local trB = add_track_with_fx("BatchSynth20", {"VSTi: ReaSynth (Cockos)"})
for i = 0, 19 do
  local region_start = i * 20
  add_midi_notes(trB, region_start, 30, 10) -- 15s of notes
  reaper.AddProjectMarker2(0, true, region_start, region_start + 15, "leaf_" .. i, i + 1, 0)
end
reaper.Main_SaveProjectEx(0, dir .. "batch_regions_20.RPP", 0)
msg("Saved: " .. dir .. "batch_regions_20.RPP")
msg("REMINDER: set Bounds=Regions + 'render regions as separate files' in the")
msg("Render dialog once, click Render, THEN re-save before timing this headless.")

-- === Project B: heavy_patch_short (~18s, dense chords + automation) =======
msg("\n--- heavy_patch_short.RPP ---")
new_project()
local trH, fxH, foundName = add_track_with_fx("HeavyPatch", {
  "Surge XT", "Surge XT (Surge Synth Team)", "VSTi: Surge XT (Surge Synth Team)",
  "Vital", "Vital (Matt Tytel)", "VSTi: Vital (Matt Tytel)",
})
if fxH < 0 then
  msg("Neither Surge XT nor Vital found - falling back to ReaSynth.")
  msg("This run will NOT represent real album DSP load - treat its number as")
  msg("a second native-overhead data point only, not a 'heavy patch' result.")
  trH, fxH = add_track_with_fx("HeavyPatchFallback", {"VSTi: ReaSynth (Cockos)"})
end
add_chord_notes(trH, 0, 36, 6, 120) -- 6-note chords, 6 repeats over ~18s -> real polyphony
add_param_automation(trH, fxH, 0, 18)
reaper.GetSet_LoopTimeRange(true, false, 0, 18, false)
reaper.Main_SaveProjectEx(0, dir .. "heavy_patch_short.RPP", 0)
msg("Saved: " .. dir .. "heavy_patch_short.RPP" .. (foundName and (" (using " .. foundName .. ")") or ""))

msg("\n=== Done ===")
msg("Add to exp2b_render_levers.sh (or a copy) for a follow-up pass:")
msg("  PROJ_BATCH_REGIONS=\"" .. dir .. "batch_regions_20.RPP\"  (after setting render-regions mode)")
msg("  compare heavy_patch_short.RPP timing directly against native_short.RPP's 7.97s baseline")
