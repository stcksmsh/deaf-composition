---
title: First full song, start to finish
date: 2026-07-30
tags: [devlog, deaf-composition, ai, audio]
---

[Everything since the 26th landed here at once](https://github.com/stcksmsh/deaf-composition/commit/8745f6826497aabd70243173475d4477d16bfdaf): arc planning, gain-staging, a mastering loop, and the orchestration wired through a real pipeline module, plus a README since this had been running without one.

The actual result: a complete song built from zero — no reskin of an earlier attempt — 88bpm, 5/4, C minor, six sections, 33 leaves, a recurring 5-note "germ cell" motif tying the sections together. Tempo and time signature are real per-song creative decisions now instead of a hardcoded 120bpm/4-4 default. Nine leaves came out silent on the first pass; root-caused all nine down to three distinct causes and fixed each, verified live rather than assumed fixed. Then a real gain-staging pass across all 33 leaves and a real mastering pass — fixed actual clipping, added glue compression, a modest loudness lift.

`song_mastered_v1.mp3` went out after that — first time hearing this particular song at all, no feedback yet. A few real open items sitting on top of a genuinely working pipeline now: one leaf's missing a stereo-width automation because the right REAPER action ID was never found (cosmetic, left alone rather than guessed at), and four continuous background parts sit under their target loudness because they're hitting REAPER's own +18dB fader ceiling — fixing that means touching their own synth params, not just track volume, so also left alone for now rather than forced.
