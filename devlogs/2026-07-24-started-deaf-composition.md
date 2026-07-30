---
title: Started Deaf Composition
date: 2026-07-24
tags: [devlog, deaf-composition, ai, audio]
---

The whole premise: an AI directs an album — concept, structure, arrangement, sound design — but never gets to *hear* what it made. It only sees measurements: render a section, extract audio features + a CLAP embedding, compare against grounded reference targets, adjust. I'm the taste gate; it's steering blind.

Before writing any real system code I ran two kill-checks. First: does "good = distance into a reference embedding" actually carry signal, or is that just a nice-sounding idea? Checked — CLAP embedding distance cleanly separates a machine-native reference set from a warm/performed off-target set. Second: is offline, headless rendering even cheap enough to generate-and-select in a loop? Also checked — headless (`xvfb`) rendering is ~2.7x faster than a real display, and batching region renders into one REAPER call scales close to linearly.

First real component: [the return channel](https://github.com/stcksmsh/deaf-composition/commit/3a3e37c379bf1f8ff05f60a149815d246bdf6a22), `.RPP → render → analyze → state.json` — the one artifact the loop is ever allowed to read about a node. Symbolic ground truth parsed straight out of Reaper's project file format (which has three different quoting conventions and two different ways of encoding MIDI delta events, both handled), plus LUFS/true-peak/crest-factor/spectral features, plus the CLAP embedding. And the batch rendering turned out to be fully programmatic after all — the brief assumed a human would need to click through Reaper's render dialog per project, but `batch_regions.RPP` differs from the single-render version by exactly two lines, so a script can set those and skip the human entirely.
