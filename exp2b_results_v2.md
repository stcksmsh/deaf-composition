# Experiment 2b (v2) results

| Configuration | Runs (s) | Median (s) | Notes |
|---|---|---|---|
| Baseline (xvfb, native-only) | 7.99,7.89,7.85 | **7.89** | the number everything else compares against |
| Non-headless (real X display) | 7.78,7.80,7.79 | **7.79** | sanity check vs xvfb; expect ~2.5-3x slower based on prior run |
| Native-only short leaf (xvfb) | 7.90,7.89,7.88 | **7.89** | the ~15-20s leaf-scale render, no Wine plugins |
| Wine/yabridge short leaf (xvfb) | 10.81,10.81,16.77 | **10.81** | diff vs #3 isolates bridge overhead - watch for a cold-start outlier in the 3 runs |
| Native-only short leaf (performance governor) | 7.84,7.89,7.89 | **7.89** | diff vs #3 isolates clock/scheduling effect - was negligible last run |
| Pinned to P-cores (single run) | 7.84 | 7.84 | verify core range with `lscpu -e` first |
| Batched: 5 regions, 1 invocation | 8.40,8.39,8.39 | **8.39** | compare vs 5x the single-leaf median from #3 - large gap = batching works |
| Batched: 20 regions, 1 invocation | 10.66,10.64,10.39 | **10.64** | checks whether the fixed-overhead + linear-marginal-cost model from N=5 still holds at N=20, or degrades |
| Heavy patch short leaf (xvfb) | 11.35,11.34,11.50 | **11.35** | 6-note chords x6 + automated cutoff sweep - diff vs #3 (7.97s baseline) estimates real per-leaf DSP cost |
