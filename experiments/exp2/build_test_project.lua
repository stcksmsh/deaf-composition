-- build_test_projects.lua
--
-- Builds the test .RPP projects needed for exp2b_render_levers.sh, using
-- Reaper's own scripting API rather than hand-written project-file text
-- (plugin state is an opaque binary chunk even in a plaintext .RPP, so
-- building via the API is the reliable way to get valid files).
--
-- HOW TO RUN:
--   Reaper > Actions > Show action list > ReaScript: Load...
--   select this file, then run it (or "New action... > Load ReaScript").
--   Watch the console (opens automatically) for progress/warnings.
--
-- OUTPUT (saved next to this script):
--   native_short.RPP   - ~18s, one ReaSynth track (native, no Wine)      -> PROJ_BASELINE / PROJ_NATIVE_SHORT
--   wine_short.RPP     - same content, Pigments instead of ReaSynth       -> PROJ_WINE_SHORT (only if Pigments found)
--   batch_regions.RPP  - 5 x ~15s regions in one project                 -> PROJ_BATCH_REGIONS
--
-- AFTER RUNNING:
--   - Open batch_regions.RPP once in Reaper and set render mode to
--     "Region render matrix" / enable regions in File > Render, then
--     re-save, so exp2b's batched test actually renders all 5 regions.
--   - If wine_short.RPP wasn't created (Pigments name mismatch), open
--     native_short.RPP, Save As wine_short.RPP, and manually swap the
--     ReaSynth instance for Pigments in that one track's FX chain.
--   - Fill the resulting paths into exp2b_render_levers.sh's CONFIG block.

local function msg(s) reaper.ShowConsoleMsg(tostring(s) .. "\n") end

local script_path = ({reaper.get_action_context()})[2]
local dir = script_path:match("(.*[/\\])") or "./"

local function new_project()
  reaper.Main_OnCommand(40023, 0) -- File: New project (ignore if unsaved changes prompt appears)
end

local function add_track_with_fx(name, fx_names)
  -- fx_names: ordered list of plugin names to try; first one found is added.
  reaper.InsertTrackAtIndex(reaper.CountTracks(0), true)
  local tr = reaper.GetTrack(0, reaper.CountTracks(0) - 1)
  reaper.GetSetMediaTrackInfo_String(tr, "P_NAME", name, true)
  for _, fxname in ipairs(fx_names) do
    local fx = reaper.TrackFX_AddByName(tr, fxname, false, 1) -- 1 = add if missing, instantiate
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
    local pitch = 55 + ((i * 3) % 12) -- wander around a scale-ish range, not just repeated note
    reaper.MIDI_InsertNote(take, false, false, s, e, 0, pitch, 90, true)
  end
  reaper.MIDI_Sort(take)
  return item
end

reaper.ClearConsole()
msg("=== build_test_projects.lua starting ===")
msg("Output dir: " .. dir)

-- === Project A: native_short (~18s, native only) ===========================
msg("\n--- native_short.RPP ---")
new_project()
local tr = add_track_with_fx("NativeSynth", {"VSTi: ReaSynth (Cockos)"})
add_midi_notes(tr, 0, 36, 12) -- 36 beats @120bpm = 18s
reaper.GetSet_LoopTimeRange(true, false, 0, 18, false)
reaper.Main_SaveProjectEx(0, dir .. "native_short.RPP", 0)
msg("Saved: " .. dir .. "native_short.RPP")

-- === Project B: batch_regions (5 x ~15s regions, one project) ==============
msg("\n--- batch_regions.RPP ---")
new_project()
local tr2 = add_track_with_fx("BatchSynth", {"VSTi: ReaSynth (Cockos)"})
for i = 0, 4 do
  local region_start = i * 20
  add_midi_notes(tr2, region_start, 30, 10) -- 30 beats @120bpm = 15s
  reaper.AddProjectMarker2(0, true, region_start, region_start + 15, "leaf_" .. i, i + 1, 0)
end
reaper.Main_SaveProjectEx(0, dir .. "batch_regions.RPP", 0)
msg("Saved: " .. dir .. "batch_regions.RPP")
msg("REMINDER: open this once, set File > Render > Bounds = Regions,")
msg("and 'Render regions as separate files' (Source: Master mix, etc), then re-save,")
msg("or the render will just render the whole timeline as one file.")

-- === Project C: wine_short (Pigments if findable, else manual) ============
msg("\n--- wine_short.RPP ---")
new_project()
local tr3, fx3, found_name = add_track_with_fx("WineSynth", {
  "Pigments", "Pigments (Arturia)", "VSTi: Pigments (Arturia)", "VST3i: Pigments (Arturia)"
})
if fx3 >= 0 then
  add_midi_notes(tr3, 0, 36, 12)
  reaper.GetSet_LoopTimeRange(true, false, 0, 18, false)
  reaper.Main_SaveProjectEx(0, dir .. "wine_short.RPP", 0)
  msg("Saved: " .. dir .. "wine_short.RPP  (found as '" .. found_name .. "')")
else
  msg("Could not auto-add Pigments under any of the tried names.")
  msg("MANUAL STEP: open native_short.RPP, Save As wine_short.RPP,")
  msg("delete the ReaSynth instance on the track, add your Pigments instance instead,")
  msg("keep the same MIDI item/notes.")
end

msg("\n=== Done ===")
msg("Fill these into exp2b_render_levers.sh:")
msg("  PROJ_BASELINE=\"" .. dir .. "native_short.RPP\"")
msg("  PROJ_NATIVE_SHORT=\"" .. dir .. "native_short.RPP\"")
msg("  PROJ_WINE_SHORT=\"" .. dir .. "wine_short.RPP\"  (if created, else build manually)")
msg("  PROJ_BATCH_REGIONS=\"" .. dir .. "batch_regions.RPP\"  (after setting render-regions mode)")
