---
title: The day the actual pipeline got built (and broke, honestly)
date: 2026-07-26
tags: [devlog, deaf-composition, ai, audio]
---

Long one. Built the real recursive generate→review→fix loop end to end: a model call emits a DSL plan for a leaf, it gets rendered, reviewed against three checks, and — if it fails — either retried or escalated to me depending on how it failed.

Two failures were worth actually writing down rather than just fixing quietly. First: [a composition-level fix loop that genuinely did not converge](https://github.com/stcksmsh/deaf-composition/commit/aa2b866b9be138f5c25adbc8dc10d40fd885fb1a). The model correctly avoided re-stacking an EQ cut that no longer made sense, but the *replacement* cut pushed percussion's spectral centroid further past bass's instead of away from it — cuts-only EQ can only remove energy, never add it back, so repeated notching just biased the whole mix quieter without solving the actual conflict. Real architectural finding, not a bug: notching a signal at its own median frequency doesn't reliably push that median in either particular direction. Stopped after two passes instead of guessing a third time.

Second: [an override-name hallucination](https://github.com/stcksmsh/deaf-composition/commit/ea472e95819973bd02eeaef18ab2bc546fb286d1). The model was inventing plausible-sounding Surge param names ("Master Volume", "Filter Cutoff") because nothing ever told it what the real 539 valid names actually were — the tool description just said `param_name` with no ground truth to check against. Fixed at the source: inject the real valid-name list into the prompt, validate before ever hitting REAPER instead of after a ~2-minute live round-trip fails.

[Escalation logic](https://github.com/stcksmsh/deaf-composition/commit/e9e0f4033ad4cdbf8e50212321700eb690e1fd23) (the three real triggers: fails its own criteria N times, a low-confidence near-miss, or something serious enough to bring straight to me) got run against an actual known-broken leaf — a percussion part rendering at -52 LUFS because only Pad presets were on offer for a part that needed a fast attack. Broadened the preset catalog, re-emitted with the real failure reason fed back, second attempt picked a Pluck preset and passed clean: -52.1 → -16.8 LUFS.

Last thing that day: [ran the live orchestration loop end to end](https://github.com/stcksmsh/deaf-composition/commit/1d065aa85eb48f14f079e30f0d8baa407f780612) and it immediately found a worse bug than any of the above — near-total digital silence, and a genuine blind spot in the convergence signal (it counts "1 reason" the same whether the failure is -42 LUFS or -110dB, treating a quiet failure and a catastrophic one as equally bad). Flagged it, didn't chase a fix same-night.
