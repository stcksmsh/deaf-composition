---
title: Building the thing that decides "good"
date: 2026-07-25
tags: [devlog, deaf-composition, ai, audio]
---

Spent the day on reference grounding: pin down a checkpoint, build a real fingerprint library, and freeze the node schema before letting anything else get built against a moving target.

Checkpoint choice actually had a real answer, not a coin flip — [compared a music-trained HTSAT-base CLAP checkpoint against stock](https://github.com/stcksmsh/deaf-composition/commit/4da87c89205451311fa21591e88f921ebdc109d2) on real separation metrics (cohesion gap, silhouette score), and music-trained won on both. Every embedding from here on has to use that one checkpoint specifically, since vectors from different checkpoints aren't comparable — made the loader refuse to run without an explicit checkpoint rather than silently defaulting to whatever `load_ckpt()` downloads.

Found a real bug the same day: [a near-silent leaf's quiet tail was nearest-matching a reference track's fade-to-silence tail](https://github.com/stcksmsh/deaf-composition/commit/493b2aeeb6d1a74a6396e469ebeacc4deeb147f8) at cosine similarity 1.0. Not a matching-code bug — CLAP genuinely maps near-total silence to an almost-universal embedding region regardless of what's actually playing, so any quiet tail looks "in the envelope" of anything else that fades out. Fixed by gating near-silent windows out of scoring on both sides (leaf and reference library), using per-window RMS computed from the exact same windows that get embedded.

Then [froze the node schema in code](https://github.com/stcksmsh/deaf-composition/commit/6a04f4320f970f085884e23e109ca5ed9f5dc293) — real dataclasses for Node, the Split/Leaf body union, review state, scope links — specifically so nothing downstream gets built against a schema that's still shifting under it.
