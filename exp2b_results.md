| Baseline (xvfb, native-only) | 9.02,9.01,9.01 | **9.01** | the number everything else compares against |
| Non-headless (real X display) | 24.18,24.04,24.09 | **24.09** | sanity check vs xvfb; expect similar or slightly slower |
| Native-only short leaf (xvfb) | 7.99,7.97,7.96 | **7.97** | the ~15-20s leaf-scale render, no Wine plugins |
| Wine/yabridge short leaf (xvfb) | 10.50,14.54,10.50 | **10.5** | same content, one track swapped to a bridged plugin - diff vs #3 isolates bridge overhead |
| Native-only short leaf (performance governor) | 7.97,7.96,7.97 | **7.97** | same as #3 but with performance governor - diff isolates clock/scheduling effect |
| Pinned to P-cores (single run) | 7.91 | 7.91 | verify core range with `lscpu -e` first |
| Batched: 5 regions, 1 invocation | 8.45,8.53,8.51 | **8.51** | compare total time here vs 5x the single-leaf median from #3 - if much less than 5x, batching is the big lever |
