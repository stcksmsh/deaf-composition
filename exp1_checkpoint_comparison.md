# CLAP checkpoint comparison (exp1 separability)

Higher is better for all three. The winner becomes canonical: it must then
be used for every leaf embedding *and* every reference envelope, since
vectors from different checkpoints are not comparable.

| Checkpoint | Cohesion gap | Silhouette | NN purity (target) | Verdict |
|---|---|---|---|---|
| stock (HTSAT-tiny) | +0.158 | +0.214 | +0.995 | SIGNAL PRESENT |
| music (HTSAT-base) | +0.178 | +0.250 | +0.991 | SIGNAL PRESENT |

## Decision: music (HTSAT-base)

Music wins both real separation metrics (cohesion gap, silhouette) — the numbers
that measure whether target/offtarget actually cluster apart. NN purity is
already near-ceiling on both (0.991 vs 0.995): a 0.004 gap up there is one or
two windows flipping their nearest neighbor, not a meaningful difference — not
enough to override the separation metrics.

Pinned in `src/return_channel/analyze.py` (`CLAP_AMODEL = "HTSAT-base"`). The
checkpoint file itself is not bundled (2GB) — it must be passed explicitly via
`--checkpoint` or the `RETURN_CHANNEL_CLAP_CHECKPOINT` env var; there is no safe
default, since laion_clap's stock download is unrelated weights, not this one.
