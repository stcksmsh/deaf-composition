#!/usr/bin/env bash
#
# Experiment 2b (v2) - render throughput lever comparison, extended with
# a 20-region batch scaling check and a real-load ("heavy patch") test.
#
# WHAT THIS DOES
#   Times several offline-render configurations, 3 runs each (unless noted),
#   reports median wall-clock seconds per configuration.
#
# FILENAMES EXPECTED (as produced by build_test_projects.lua /
# build_test_projects_2.lua, in the same directory as this script by default -
# edit the CONFIG paths below if yours live elsewhere):
#   native_short.RPP       - ~18s, ReaSynth, native only
#   wine_short.RPP         - same content, Pigments (or manual swap)
#   batch_regions.RPP      - 5 x ~15s regions, native
#   batch_regions_20.RPP   - 20 x ~15s regions, native  [NEW]
#   heavy_patch_short.RPP  - ~18s, dense chords + automated cutoff,
#                             Surge XT / Vital if found, else ReaSynth [NEW]
#
# REQUIRED MANUAL STEP before timing either batch project headless:
#   Open it in Reaper GUI once, Render dialog (Ctrl+Alt+R), Bounds = Regions,
#   enable "render regions as separate files", click Render once (confirm
#   N separate output files appear), then Ctrl+S to persist the setting.
#   Without this, the project renders as one linear file and the batch
#   numbers are meaningless (this bit us on the first pass - check the
#   output folder file count before trusting these results).
#
# USAGE
#   chmod +x exp2b_render_levers_v2.sh
#   ./exp2b_render_levers_v2.sh

set -uo pipefail

# ============================== CONFIG ======================================
REAPER_BIN="reaper"                     # or full path, e.g. /usr/bin/reaper

PROJ_NATIVE_SHORT="native_short.RPP"
PROJ_WINE_SHORT="wine_short.RPP"
PROJ_BATCH_REGIONS="batch_regions.RPP"
PROJ_BATCH_REGIONS_20="batch_regions_20.RPP"      # NEW
PROJ_HEAVY_PATCH="heavy_patch_short.RPP"          # NEW

# Baseline for the headless-vs-display / governor / pinning comparisons.
# Reuses the native short leaf project by default.
PROJ_BASELINE="$PROJ_NATIVE_SHORT"

RUNS_PER_CONFIG=3
# ============================================================================

RESULTS_MD="./exp2b_results_v2.md"
RAW_LOG="./exp2b_raw_v2.log"
: > "$RAW_LOG"
: > "$RESULTS_MD"

echo "# Experiment 2b (v2) results" >> "$RESULTS_MD"
echo "" >> "$RESULTS_MD"
echo "| Configuration | Runs (s) | Median (s) | Notes |" >> "$RESULTS_MD"
echo "|---|---|---|---|" >> "$RESULTS_MD"

log() { echo "$@" | tee -a "$RAW_LOG"; }

median3() {
    python3 -c "import sys; v=sorted(float(x) for x in sys.argv[1:]); print(v[1])" "$@"
}

time_render() {
    local proj="$1"; shift
    local extra_args=("$@")
    local start end
    start=$(date +%s.%N)
    "$REAPER_BIN" -renderproject "$proj" "${extra_args[@]}" >> "$RAW_LOG" 2>&1
    end=$(date +%s.%N)
    python3 -c "print(f'{$end - $start:.2f}')"
}

time_render_xvfb() {
    local proj="$1"; shift
    local extra_args=("$@")
    local start end
    start=$(date +%s.%N)
    xvfb-run -a "$REAPER_BIN" -renderproject "$proj" "${extra_args[@]}" >> "$RAW_LOG" 2>&1
    end=$(date +%s.%N)
    python3 -c "print(f'{$end - $start:.2f}')"
}

run_config() {
    local label="$1" fn="$2" proj="$3" note="$4"; shift 4
    if [[ -z "$proj" ]]; then
        log "[skip] $label - no project path given"
        echo "| $label | (skipped) | - | no project provided |" >> "$RESULTS_MD"
        return
    fi
    if [[ ! -f "$proj" ]]; then
        log "[skip] $label - file not found: $proj"
        echo "| $label | (skipped) | - | file not found: $proj |" >> "$RESULTS_MD"
        return
    fi
    log ""
    log "=== $label ($proj) ==="
    local times=()
    for i in $(seq 1 "$RUNS_PER_CONFIG"); do
        log "  run $i..."
        local t
        t=$("$fn" "$proj" "$@")
        log "  run $i: ${t}s"
        times+=("$t")
    done
    local med
    med=$(median3 "${times[@]}")
    log "  -> median: ${med}s"
    local runs_str
    runs_str=$(IFS=,; echo "${times[*]}")
    echo "| $label | $runs_str | **$med** | $note |" >> "$RESULTS_MD"
}

log "Starting experiment 2b (v2) at $(date)"
log "REAPER_BIN=$REAPER_BIN  RUNS_PER_CONFIG=$RUNS_PER_CONFIG"

# --- 1. Baseline: headless (xvfb) --------------------------------------
run_config "Baseline (xvfb, native-only)" time_render_xvfb "$PROJ_BASELINE" \
    "the number everything else compares against"

# --- 2. Non-headless (real display) -------------------------------------
run_config "Non-headless (real X display)" time_render "$PROJ_BASELINE" \
    "sanity check vs xvfb; expect ~2.5-3x slower based on prior run"

# --- 3. Native-only short leaf -------------------------------------------
run_config "Native-only short leaf (xvfb)" time_render_xvfb "$PROJ_NATIVE_SHORT" \
    "the ~15-20s leaf-scale render, no Wine plugins"

# --- 4. Wine/yabridge short leaf ------------------------------------------
log ""
log "NOTE: run this at least twice if you can - first run may include a"
log "one-time yabridge cache/bridge-negotiation cost (~4s extra seen previously)."
run_config "Wine/yabridge short leaf (xvfb)" time_render_xvfb "$PROJ_WINE_SHORT" \
    "diff vs #3 isolates bridge overhead - watch for a cold-start outlier in the 3 runs"

# --- 5. CPU governor: performance mode ------------------------------------
if command -v cpupower >/dev/null 2>&1; then
    log ""
    log "=== Setting CPU governor to performance ==="
    sudo cpupower frequency-set -g performance >> "$RAW_LOG" 2>&1
    run_config "Native-only short leaf (performance governor)" time_render_xvfb "$PROJ_NATIVE_SHORT" \
        "diff vs #3 isolates clock/scheduling effect - was negligible last run"
    log "=== Restoring CPU governor (adjust if this isn't your default) ==="
    sudo cpupower frequency-set -g schedutil >> "$RAW_LOG" 2>&1 || sudo cpupower frequency-set -g powersave >> "$RAW_LOG" 2>&1
else
    log "[skip] cpupower not installed"
    echo "| Performance governor | (skipped) | - | cpupower not installed |" >> "$RESULTS_MD"
fi

# --- 6. Pinned to performance cores (taskset) -----------------------------
if command -v taskset >/dev/null 2>&1 && [[ -f "$PROJ_NATIVE_SHORT" ]]; then
    log ""
    log "=== Pinned to cores 0-11 (assumed P-cores - verify with lscpu -e) ==="
    start=$(date +%s.%N)
    xvfb-run -a taskset -c 0-11 "$REAPER_BIN" -renderproject "$PROJ_NATIVE_SHORT" >> "$RAW_LOG" 2>&1
    end=$(date +%s.%N)
    t=$(python3 -c "print(f'{$end - $start:.2f}')")
    log "  single run: ${t}s"
    echo "| Pinned to P-cores (single run) | $t | $t | verify core range with \`lscpu -e\` first |" >> "$RESULTS_MD"
else
    echo "| Pinned to P-cores | (skipped) | - | taskset missing or project not found |" >> "$RESULTS_MD"
fi

# --- 7. Batched region render, N=5 ----------------------------------------
log ""
log "=== Batched region render, N=5 ==="
log "REQUIRES: render-regions-as-separate-files already set + saved in the project."
log "Verify the output folder has 5 files after this run, not 1."
run_config "Batched: 5 regions, 1 invocation" time_render_xvfb "$PROJ_BATCH_REGIONS" \
    "compare vs 5x the single-leaf median from #3 - large gap = batching works"

# --- 8. Batched region render, N=20 (NEW - scaling check) ------------------
log ""
log "=== Batched region render, N=20 ==="
log "REQUIRES: same render-regions setup as N=5, done separately for this project."
log "Verify the output folder has 20 files after this run, not 1."
run_config "Batched: 20 regions, 1 invocation" time_render_xvfb "$PROJ_BATCH_REGIONS_20" \
    "checks whether the fixed-overhead + linear-marginal-cost model from N=5 still holds at N=20, or degrades"

# --- 9. Heavy patch (real DSP load: polyphony + automation) (NEW) ---------
log ""
log "=== Heavy patch short leaf ==="
log "Check build_test_projects_2.lua's console output to confirm which synth"
log "was actually used (Surge XT / Vital / fallback ReaSynth) before trusting this."
run_config "Heavy patch short leaf (xvfb)" time_render_xvfb "$PROJ_HEAVY_PATCH" \
    "6-note chords x6 + automated cutoff sweep - diff vs #3 (7.97s baseline) estimates real per-leaf DSP cost"

log ""
log "Done. Results table written to $RESULTS_MD"
log "Raw log in $RAW_LOG"

echo ""
echo "======================================================"
echo "RESULTS:"
cat "$RESULTS_MD"
echo "======================================================"
echo "Send back the contents of $RESULTS_MD (and $RAW_LOG if anything looks off)."
