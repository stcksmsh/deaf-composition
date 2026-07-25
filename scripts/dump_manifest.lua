-- Dump params/ranges for the curated instrument palette (plan §5) to manifest.json.
-- Runs headless: xvfb-run -a reaper -nosplash scripts/dump_manifest.lua
-- Scratch project only -- never touches a real .RPP.

local OUT_PATH = reaper.GetResourcePath() .. "/../../../manifest_dump_out.json"
-- Overridden below via an env-style marker file so the caller controls the real path
-- without needing command-line args (reaper's script invocation doesn't pass argv cleanly
-- for this pattern) -- see scripts/dump_manifest.py, which writes this file first.
local marker = io.open("/tmp/dump_manifest_out_path.txt", "r")
if marker then
  OUT_PATH = marker:read("*l")
  marker:close()
end

-- Name variants to try with TrackFX_AddByName, in order -- Reaper's fuzzy match on the
-- short form usually works, but bridged/renamed plugins sometimes need the full form.
local PALETTE = {
  {id = "reasynth", variants = {"ReaSynth", "VSTi: ReaSynth (Cockos)"}},
  {id = "surge_xt", variants = {"Surge XT", "VST3i: Surge XT (Surge Synth Team)"}},
  {id = "vital", variants = {"Vital", "VST3i: Vital"}},
  {id = "pigments", variants = {"Pigments", "VSTi: Pigments (Arturia) (2->2ch)"}},
}

local MAX_PRESETS = 200  -- safety cap; NavigatePresets loops if a plugin has none

local function param_info(track, fx, idx)
  local ok, name = reaper.TrackFX_GetParamName(track, fx, idx, "")
  local value, minval, maxval = reaper.TrackFX_GetParam(track, fx, idx)
  local _, formatted = reaper.TrackFX_GetFormattedParamValue(track, fx, idx, "")
  return {
    index = idx,
    name = ok and name or ("param_" .. idx),
    value = value,
    min = minval,
    max = maxval,
    formatted = formatted,
  }
end

local function preset_names(track, fx)
  local presets = {}
  local _, first = reaper.TrackFX_GetPreset(track, fx, "")
  if first == nil or first == "" then
    return presets
  end
  table.insert(presets, first)
  for _ = 1, MAX_PRESETS do
    reaper.TrackFX_NavigatePresets(track, fx, 1)
    local _, name = reaper.TrackFX_GetPreset(track, fx, "")
    if name == first or name == nil or name == "" then
      break
    end
    table.insert(presets, name)
  end
  return presets
end

local function json_escape(s)
  return tostring(s):gsub('[\\"]', '\\%0'):gsub("\n", "\\n")
end

local function json_encode(value, indent)
  indent = indent or ""
  local t = type(value)
  if t == "string" then
    return '"' .. json_escape(value) .. '"'
  elseif t == "number" then
    if value ~= value then return "null" end  -- NaN
    return tostring(value)
  elseif t == "boolean" then
    return tostring(value)
  elseif t == "table" then
    local is_array = (#value > 0)
    local inner = indent .. "  "
    local parts = {}
    if is_array then
      for _, v in ipairs(value) do
        table.insert(parts, inner .. json_encode(v, inner))
      end
      if #parts == 0 then return "[]" end
      return "[\n" .. table.concat(parts, ",\n") .. "\n" .. indent .. "]"
    else
      local keys = {}
      for k in pairs(value) do table.insert(keys, k) end
      table.sort(keys)
      for _, k in ipairs(keys) do
        table.insert(parts, inner .. '"' .. json_escape(k) .. '": ' .. json_encode(value[k], inner))
      end
      if #parts == 0 then return "{}" end
      return "{\n" .. table.concat(parts, ",\n") .. "\n" .. indent .. "}"
    end
  end
  return "null"
end

local function dump_plugin(entry)
  local track_idx = reaper.CountTracks(0)
  reaper.InsertTrackAtIndex(track_idx, false)
  local track = reaper.GetTrack(0, track_idx)

  local fx, matched_name = -1, nil
  for _, variant in ipairs(entry.variants) do
    fx = reaper.TrackFX_AddByName(track, variant, false, -1)
    if fx >= 0 then
      matched_name = variant
      break
    end
  end

  if fx < 0 then
    return {id = entry.id, found = false, tried = entry.variants}
  end

  -- REAPER's VST3 wrapper auto-exposes 128+ "MIDI CC n|m" automatable params on
  -- EVERY VST3i regardless of what the plugin itself defines -- noise, not real
  -- sound-design surface, and it blows a leaf-implementation model's param search
  -- space up by 10-100x. Excluded here so manifest.json reflects the plugin's own
  -- params, which is what plan §5's "bounding the sonic vocabulary" is about.
  local n_params_raw = reaper.TrackFX_GetNumParams(track, fx)
  local params = {}
  for i = 0, n_params_raw - 1 do
    local info = param_info(track, fx, i)
    if not info.name:match("^MIDI CC") then
      table.insert(params, info)
    end
  end

  local _, actual_fx_name = reaper.TrackFX_GetFXName(track, fx, "")

  return {
    id = entry.id,
    found = true,
    matched_name = matched_name,
    fx_name = actual_fx_name,
    n_params = #params,
    n_params_raw = n_params_raw,
    params = params,
    presets = preset_names(track, fx),
  }
end

local function write_manifest(results)
  local manifest = {
    schema_version = 1,
    reaper_version = reaper.GetAppVersion(),
    generated_at = os.date("!%Y-%m-%dT%H:%M:%SZ"),
    plugins = results,
  }
  local f = io.open(OUT_PATH, "w")
  if f then
    f:write(json_encode(manifest, ""))
    f:write("\n")
    f:close()
  end
end

reaper.Main_OnCommand(40023, 0)  -- File: New project (ignore save prompt via project state below)
reaper.Undo_BeginBlock()

-- Written after EVERY plugin, not just at the end: a bridged plugin (yabridge/
-- wine) can abort the whole REAPER process on init failure -- confirmed with
-- Pigments in this environment (std::system_error / "read: End of file" from
-- yabridge's socket, then REAPER core-dumps). A crash on plugin N must not
-- erase the N-1 results already gathered.
local results = {}
for _, entry in ipairs(PALETTE) do
  local ok, result = pcall(dump_plugin, entry)
  table.insert(results, ok and result or {id = entry.id, found = false, error = tostring(result)})
  write_manifest(results)
end

reaper.Undo_EndBlock("dump_manifest", -1)
reaper.Main_OnCommand(40004, 0)  -- File: Quit REAPER
