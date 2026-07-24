# Deaf Composition — Project Plan (v0.1)

*An album directed by a model that cannot hear it, executed by a human who does not compose it.*

Working title TBD (album/system naming is the author's call, per catalogue convention — all-caps, cold perceptual/systems register).

---

## 0. Thesis

A record is built by an AI that has **full authority over every musical decision** — concept, mood, structure, notes, sound design, arrangement, whether the vocals mean anything — and **zero access to the audio it produces**. It steers only by measurement. The human builds the system, sets the outer constraints, handles setup/errors/code, and acts as the final taste gate. The human never composes.

Two products fall out of one build:

1. **The record** (primary). A concept album whose concept, sound, and arc are the model's, produced under a hard sensory constraint.
2. **The engineering** (secondary, promotional). A recursive compositional planner over a DAW — a real artifact for HN / generative-art / r/WeAreTheMusicMakers / KVR / IDM communities. The flex funnels attention to the record; it is not the point.

The sensory constraint is not a limitation to engineer away. **The deafness is the art.** The system's characteristic output — over-precise, machine-exact, artifact-clean — is a defect against warmth and the *aesthetic* against machine-native targets. The plan is built to exploit that, not hide it.

---

## 1. The five hard requirements (acceptance criteria for the *system*)

Every design decision below is justified against these. If a decision fails one, it's wrong.

1. **Tight, innovative, efficient engineering.** The novelty is the *architecture*, not the plumbing. DAW-control via LLM is a commodity (multiple mature Reaper-MCP servers, 100+ tools each). We bolt onto that and build the part with no prior art: hierarchical decompose → implement → fold-review with coupling resolved structurally.
2. **Bounded yet free.** Maximum creative freedom *inside* a cage of hard constraints. The human defines the cage (palette, reference space, runtime budget); the AI moves freely within it. Freedom is not "anything"; it's "anything reachable."
3. **It sounds good.** Music first, CS second. "Good" must be operationally defined (§4) and the human ear must be spent where it has leverage (§7), not diffused across every decision.
4. **Human hands-off in the music.** The author touches setup, errors, and code — never compositional choices — or the concept dies. Authorship = *build the system + say yes/no*, not steer.
5. **Token/usage efficient.** Many candidate albums, many iterations on the good ones. Cost concentrated where it earns out; the hot loop runs cheap or the whole generate-and-select model collapses.

---

## 2. The cage: human bounds vs AI freedom

The single organizing principle. The human sets a small number of **hard boundaries**; everything inside is the model's.

| Human sets (the cage) | AI decides (free inside it) |
|---|---|
| Outer runtime budget (e.g. ~5 tracks / ~20 min) | Concept, theme, mood, title register |
| Curated **instrument palette** (§5) | The **path** through reference space = the arc (§4) |
| Curated **reference libraries** (§4) | All composition: notes, rhythm, harmony, structure |
| Hard technical constraints (this doc) | All sound design within the palette |
| Setup, errors, code, final gate, escalations | Whether vocals carry meaning or are pure texture |

Two axes of autonomy, deliberately asymmetric:

- **Execution autonomy → maxed.** ReaScript exposes the whole instrument; there is no musical action the tooling can't reach. Solved, commoditized, not our contribution.
- **Judgment autonomy → hard ceiling.** Every automated review is a *proxy*. An optimizer satisfies exactly what's measured (Goodhart). Machine review reliably catches objective failure (mud, clipping, thinness, broken seam, wrong key, lopsided mix); it structurally cannot catch *technically-clean-but-boring*. That gap is the human's, and only the human's.

---

## 3. Core architecture: the problem tree

The album is compiled the way a program is: **recursive descent on the way down, a fold (catamorphism) on the way up.** Decompose to base cases, then reduce reviewed children into a verdict on the parent.

### 3.1 Nodes and the base case

A node is a musical problem. It either **splits** into child problems or **is a leaf** that implements.

**Base-case predicate:** a node is a leaf when it is expressible as a bounded set of deterministic DSL commands against the manifest with **no remaining creative sub-decision**. Leaf = translation, not composition.

- *Not a leaf:* "8-bar acid line on Vital" (still hides sound-design vs note-pattern vs automation).
- *Leaf:* "place these 32 notes at these velocities"; "cutoff envelope 0.2→0.8 over bars 1–8".

### 3.2 Node schema

```
Node {
  own_purpose         // this node's job, in its own words
  spec                // what to build
  acceptance_criteria // machine-checkable: target measurements + structural facts
  scope_chain         // tapered ancestor context (§3.3)
  neighbor_edges      // local (auto) + long-range (declared), weighted (§3.4)
  body: Split(children[]) | Leaf(implementation)
  review_state        // pending | passed | failed(reasons) | escalated
  assigned_model      // routed by depth (§6)
  snapshot_ref        // versioned project state for this node (§7.3)
}
```

Nothing is built until this schema and the two context structures (§3.3, §3.4) are frozen. Everything compiles against them.

### 3.3 Vertical context — the scope chain (tapered)

Context is **lexically scoped**, not broadcast. A node resolves its context by walking its ancestors, at **decreasing resolution the higher it goes**:

- Album node → one-line identity to a leaf.
- Song node → this song's purpose and energy.
- Section node → the fine-grained job ("this intro's approach").

The taper is not cosmetic: it's what keeps per-call tokens bounded (a leaf carries a *compressed* chain, not the whole album) and keeps the upper links **cache-stable** (§6), which is most of the token budget.

### 3.4 Horizontal context — the neighbor DAG

A pure tree has no horizontal edges, but musical subproblems are **coupled**. Add adjacency edges; the structure becomes a DAG (containment vertical, adjacency horizontal). Edge weight decays with distance along the arrangement timeline.

- **Local edges** — free, automatic. Every node links to what's immediately before/after it. A section cares intensely about its seams, weakly about distant neighbors.
- **Long-range edges** — sparse, high-weight, **declared**. A motif that returns; an intro the finale resolves. Only the top thinking node has the whole-album view, so *declaring callbacks is part of arc-planning* — a root-tier (Fable) decision. This is the only case where an early section legitimately "knows about" the ending: because an explicit edge exists, not ambient awareness.

### 3.5 Build order and cycles

Context assembly is **time-sensitive**:

- At **think-time** a neighbor may exist only as a spec → the node gets its neighbor's *intent*.
- At **implement-time**, if the neighbor is already rendered → the node gets its neighbor's *actual* `state.json` (real last bar, real landing key) and is built to hand off cleanly.

Therefore implementation proceeds **along the timeline**, so each node's heaviest neighbor is already concrete. Backward edges (outro resolving intro) are cycles: break them by spec'ing one endpoint as a **provisional target**, build forward, revisit on the way up.

### 3.6 Review = the fold, at the LCA

Coupling is reviewed at the **lowest common ancestor** of its endpoints. Each node review is three checks:

1. Meets its **own** acceptance criteria.
2. **Composes** with its siblings.
3. Its **seams** hold (continuity with local neighbors).

A seam between adjacent sections is judged by their shared parent; the intro↔finale callback is judged at the album node — the lowest node that can see both ends. Long-range coherence surfaces exactly where both sides are visible. A failed review can re-split, patch, or escalate (§7).

---

## 4. Where "good" comes from (the keystone)

A deaf loop course-corrects toward target measurements. If those targets are invented ("target centroid = 3.2 kHz"), convergence is meaningless — it's a random walk toward a hallucinated number. Targets must be **grounded in real audio.**

### 4.1 Fingerprint references → distance-based criteria

Analyze a curated set of real records into **measurement distributions per section-type** (intro / build / drop / breakdown / outro): LUFS, spectral centroid, crest factor, peak, spectral shape, density, self-similarity. A node's acceptance criterion is **"distance into the reference envelope,"** never an absolute magic value. That single decision turns the deaf loop from a random walk into a real controller.

### 4.2 The reachability axis: machine-native vs human-performed

The axis that matters is **not** loud/soft or fast/slow — all of those are measurable and controllable, so range freely. The only off-limits axis is **warmth / performance / humanity**, which is proxy-invisible and un-synthesizable from a bounded palette.

Rule for the fingerprint library: **anything whose identity lives in its machineness, at any speed or intensity.** Two reachable poles, both forgiving of the deaf process — one hides the artifacts, one *is* the artifact:

- **Quiet-machine:** Alva Noto, Ryoji Ikeda, Emptyset — precision as the aesthetic; the deaf failure mode (cold, exact) is the target.
- **Murk / broken-machine:** Actress, early Arca, Objekt — lo-fi, artifact-native, extremely forgiving.
- **Loud-machine:** Justice (*Cross*), Gesaffelstein, Boys Noize — saturation *masks* the machineness.
- **Rhythmic-machine:** hard techno broadly — structural, synthesizable, native to the tree.

**Explicitly excluded as fingerprint targets** (identity = execution, not envelope; a target transmits the envelope and throws the execution away):

- *RAM* — conceptually computery, sonically the least computery Daft Punk record (live disco, real players, wide dynamics, human micro-timing). Its greatness is unreachable; its envelope is a trap.
- *Junk* (M83) — a false friend: clean production leaves every artifact naked, and its identity is melody/chord-craft/pastiche, all proxy-invisible.

### 4.3 Two libraries, no cross-contamination

- **Structure references** — how to build an arc: Four Tet, Floating Points, Burial, Justice, Objekt, Actress, early Arca.
- **Fingerprint references** — what to sound like: machine-native only (§4.2).

A producer admired for structure may be *unreachable* as a sonic target (Four Tet / Floating Points are warm and performance-feeling → great arc models, illegal fingerprints). Burial is borderline: crackle/detuning are reachable texture, the emotional swing is not. Keep the libraries separate.

### 4.4 The gamut is the arc

Breadth isn't only "more freedom" — it hands the album its macro-structure. A concept that runs Alva-Noto-sparse → Justice-dense is a **trajectory through the reference space**, and that trajectory *is* the four-act energy curve. The concept node's job is to **pick a path through the library**, not a single point.

### 4.5 Anti-monotony metric

The most likely deaf failure isn't ugliness — it's everything converging to the same safe texture. "Interesting" is unmeasurable, but **sameness is measurable**: cross-section self-similarity, spectral variety, repetition indices. Write these into `state.json` so the fold can **reject uniformity** even when it can't reward brilliance.

---

## 5. The palette and manifest

Deaf composition picks instruments by name and parameters by manifest. On Linux/Wine/yabridge this is exactly where it breaks: some bridged VSTs expose generic "Param 1," and wavetable slots often aren't host params at all.

- **Curate a small fixed instrument set** of well-behaved plugins (native Reaper synths, Vital/Surge XT, a handful of clean VSTs with named params). Dump the manifest **once** (params, ranges, presets → `manifest.json`); re-dump only on new install.
- **Bounding the sonic vocabulary is a feature**, not a limitation, for a deaf system — fewer unknowns, more predictable measurement→sound mapping.

---

## 6. Model routing and economics

Route by **tree depth**. The tree is narrow at the top (one root, few section nodes) and wide at the bottom (many leaves, many correction iterations). Cost concentrates where volume is lowest — exactly where a frontier model earns out.

| Tree region | Model | Why |
|---|---|---|
| Root + section thinking; top integration reviews | **Fable 5** ($10/$50 per M) | Sparse, highest-leverage: concept, arc, long-range edges, coherence. Never in the hot loop. |
| Mid-tree decomposition; leaf review | **Sonnet** (intro $2/$10) | Structured reasoning, moderate volume. |
| Leaf implementation (DSL emission vs manifest) | **Haiku** | Mechanical, high-volume, cheap. |

**Caching is the main lever.** The scope chain's upper links are cache-stable; prompt caching cuts repeated input by ~90%. A rich Fable thinking-node (~5k in / ~3k out) is ≈ $0.20 before caching. $100 buys several hundred top-tier calls **only if Fable never touches the leaf loop.**

**Termination is non-negotiable economics.** Every run needs `max_depth`, `max_iterations_per_node`, and a convergence threshold, or nodes spin and credits evaporate. A run must be **finite and costable**: `nodes × model-per-node × tokens`. Once the tree size is fixed we cost one run and derive candidates-per-$100.

---

## 7. Autonomy, QA, and generate-and-select

### 7.1 The human is the taste oracle

The human is not supervising the work — the human is the **single term in the loss the loop can't compute for itself**, the ground truth the proxies approximate. Attention must be *concentrated*, not uniform (uniform QA just kills the autonomy). **Human-on-the-loop, not in it.**

### 7.2 Generate-and-select (forced by maximal autonomy)

Pushing autonomy to the top (meaning, theme, concept) collapses authorship into one form: **build the system, say yes/no.** You can no longer *steer* toward good — only *accept or reject*. So the workflow is not steer-and-refine, it's **generate-and-select**: run the system to produce many candidate albums, curate to the one where the invisible thing landed. Taste **filters**, it doesn't shape. This is the answer to the Goodhart wall: competent output is guaranteed, gripping output isn't, so run many and keep the rare hit.

This makes cheapness, speed, and reproducibility (below) *requirements*, not niceties — most output is thrown away by design.

### 7.3 Reproducibility (required for curate-many-discard-most)

- Seeded model calls, versioned `manifest.json`, per-node project snapshots.
- A good run must be **recoverable**; two runs must be **diffable**. Without this, curation is impossible.

### 7.4 Escalation — where the ear re-enters

Default surfacing granularity: **autonomous per song, surface at song boundaries** (cheap early veto, never in the leaf loop). The fold escalates when it can't self-resolve:

- a node fails its own criteria N times;
- two criteria conflict (fixing a seam breaks a sibling);
- review confidence is low.

An escalation surfaces the **rendered stem + the measurements + the specific conflict**. The human rules or kicks it back. This is the only routine point where the human hears anything mid-process.

---

## 8. The loop (plumbing) and the vocoder

### 8.1 Reaper as API

- `.RPP` is plaintext → the **return channel already exists** with zero audio: read arrangement, notes, FX chain, automation envelopes directly.
- **Bolt onto an existing Reaper-MCP** for execution. Its tool schema *becomes* the leaf vocabulary — which dissolves the "raw Lua vs typed DSL" question: the MCP's typed tools are the DSL, and our contribution (the decompose/fold planner) sits cleanly **above** it.
- After each command: **render the stem → run the analysis script → write `state.json`.** The AI reads measurements, never vibes. This is the mechanical realization of "hearing as symbols."

### 8.2 Vocoder subtree

- Its own small subtree with its own manifest. Voice as **texture/instrument**; semantics optional and the model's choice.
- Symmetric with the whole premise: the *sound* of the voice (vowel brightness, syllable density, rhythmic placement) is measurable and controllable; whether it *means* anything is proxy-invisible — the same class as timbre-goodness.
- One real unknown: the TTS-modulator source on Linux. Flag as an open item (§10).

---

## 9. Risks (named, not hidden)

1. **Goodhart / boring.** Proxies trend toward technically-clean-and-dull. *Mitigations:* generate-and-select, the anti-monotony metric, and leaning into deafness as the aesthetic rather than fighting it.
2. **More fun to build than to hear.** *Mitigation:* record-first discipline — the engineering is promotional, never the deliverable.
3. **Concept more compelling described than heard.** *Mitigation:* the concept must **emerge from the real constraints** (deaf, vocoded, recursively composed) rather than be invented blank-page, which defaults to cliché. Constrain the input, not the output.
4. **Manifest fragility on Wine.** *Mitigation:* curated well-behaved palette; manifest dumped and versioned once.
5. **Scope vs "shorter album."** The full architecture is weeks of infra. *Mitigation:* reuse the MCP for plumbing; spend real effort only on the two novel layers (fold planner + reference grounding).

---

## 10. Open items to close before any code

- [ ] **Freeze the node schema** and both context structures (§3.2–3.4). Everything compiles against these.
- [ ] **Pick the Reaper-MCP** to bolt onto → fixes the leaf vocabulary.
- [ ] **Assemble both reference libraries** (§4.3) and run the fingerprint analysis → per-section-type target distributions.
- [ ] **Curate the instrument palette** and dump `manifest.json`.
- [ ] **Fix a nominal tree size** → cost one run → derive candidates-per-$100.
- [ ] **Choose the TTS-modulator source** on Linux for the vocoder subtree.
- [ ] **Define the analysis feature set** written to `state.json` (measurements + anti-monotony indices).

---

## 11. Build order (once §10 is closed)

1. **Return channel first:** parse `.RPP` + render→analyze→`state.json`. Prove the deaf feedback loop works on a hand-built project before any planning.
2. **Reference grounding:** fingerprint analysis → target distributions. Prove "distance into envelope" is a usable signal.
3. **Leaf layer:** DSL emission (Haiku) against the MCP + manifest. Prove a leaf spec becomes correct audio.
4. **Fold + tree:** decomposition, scope chain, neighbor DAG, LCA review. Prove one song builds and self-reviews end-to-end.
5. **Routing + termination + reproducibility:** make a full run finite, seeded, diffable, costed.
6. **Generate-and-select:** run many, curate. Ship the one that lands.
7. **Vocoder subtree** folds in as its own branch.

Each stage is independently testable and independently interesting to write about — which is also the devlog spine for the promotional track.
