# Deaf Composition

An album directed by an AI that has full creative authority — concept, structure, notes,
sound design, arrangement — but **zero access to the audio it produces**. It steers
entirely by measurement: render → extract features/embeddings → compare against grounded
reference targets → adjust. A human owns the system, sets a small set of hard outer
constraints, and acts as the final taste gate — never as a co-composer.

This is a separate project from *MAXIMAVELIANISM* (another album by the same author).
Nothing here borrows concept, theme, or vocabulary from that project.

## Why

Two kill-check experiments were run before any system code was written, to find out
whether the premise was viable at all:

- **Fingerprint separability** (`experiments/exp1_separability.py`) — does "good = distance
  into a reference embedding" carry real signal? Yes: CLAP embedding distance cleanly
  separates a machine-native reference set from a warm/performed off-target set (nearest-
  neighbor purity 0.995).
- **Render throughput economics** (`experiments/exp2b_*`) — is offline, headless rendering
  cheap enough for a generate-and-select loop? Yes: headless (xvfb) rendering is ~2.7x
  faster than a real display, and batching N region renders into one REAPER invocation
  scales linearly with negligible per-leaf cost.

Full design reasoning — the node/tree/fold architecture, reference-library rules, model
routing, and risk analysis — lives in [`deaf-composition-plan.md`](deaf-composition-plan.md).
[`PROJECT_BRIEF.md`](PROJECT_BRIEF.md) has the environment setup and onboarding detail.
[`memory.md`](memory.md) is the running session log: current state, what's built, what's
broken, and what's next.

## How it works

The system builds each song as a tree: a root **song** node splits into **sections**,
sections split into **leaves** (individual instrument/part renders). Each leaf is emitted
as a small DSL plan, rendered headless in REAPER via MCP, measured, and scored against a
curated reference-fingerprint library built from real machine-native tracks. Leaves fold
back up into sections, sections into the song, with review and automatic fix/re-emission
at every level when a node's measured result doesn't match its target.

```
song
 └─ section (per structural region: intro, build, drop, ...)
     └─ leaf (one instrument part; DSL plan → REAPER render → measure → score)
```

## Layout

```
src/
  return_channel/   .RPP parsing, headless render, audio analysis (LUFS/peaks/spectral/
                     CLAP), reference-library scoring — the measurement foundation.
  planner/           Node/tree schema, decompose/emit, fold + review, fix/escalation
                      strategies, gain-staging, mastering, and the live orchestration loop.
scripts/             REAPER-MCP bridge, Surge XT preset/param tooling, one-off build/
                      review/proof scripts used while developing each pipeline stage.
tests/               Unit tests, most run against the checked-in experiment fixtures.
experiments/         The two kill-check experiments above, plus test REAPER projects
                      (`native_short.RPP`, `heavy_patch_short.RPP`, etc.) used as known-
                      ground-truth fixtures throughout the codebase.
references/          Reference-fingerprint audio library (gitignored — user-sourced,
                      not redistributed).
state/               Run checkpoints and generated state.json artifacts (gitignored).
```

## Setup

Requires **Python 3.11** exactly (not 3.12+ — see [`PROJECT_BRIEF.md`](PROJECT_BRIEF.md#2-environment--do-not-change-these-pins-without-flagging-it-first)
for why) and a local REAPER install with Surge XT.

```bash
uv venv --python 3.11
uv pip install -r requirements.txt
```

REAPER control goes through [TwelveTake-Studios/reaper-mcp](https://github.com/TwelveTake-Studios/reaper-mcp),
configured in `.mcp.json`. Start the headless bridge:

```bash
scripts/start_reaper_mcp_bridge.sh start
```

Rendering always goes through `xvfb-run -a reaper -renderproject <path>` — never through a
real X display in the hot loop.

## Tests

```bash
.venv/bin/python -m unittest discover tests
```

## Status

Actively in development. See the top of [`memory.md`](memory.md) for the current session
checkpoint and open items.
