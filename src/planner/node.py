"""Node schema (plan §3.2) -- the unit the tree/fold planner operates on.

"Nothing is built until this schema and the two context structures (§3.3,
§3.4) are frozen. Everything compiles against them." This module freezes
the schema in code. It defines structure only -- no split/decompose/fold
logic, no scheduler, no model-calling code. That's plan §11 stage 4, and it
builds on top of this, not inside it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

# A leaf's intended mixing prominence (2026-07-29, real user finding: three
# separate "quiet/buried" complaints across three different sections all
# traced to the same root cause -- every leaf's track fader sat at flat 0dB
# regardless of how loud its preset renders natively, so raw preset-loudness
# spread governed the mix instead of musical intent). Deliberately NOT "make
# everything equally loud" -- a background texture is SUPPOSED to sit
# quieter than a lead; the point is that decompose.py's own role assignment
# (foreground lead vs. midground harmonic support vs. background texture)
# should be what determines relative level, not an accident of which Surge
# preset happened to render hot. src/planner/gain_stage.py is what actually
# acts on this value.
PROMINENCE_LEVELS = ("foreground", "midground", "background")


class ModelTier(str, Enum):
    """Routed by tree depth (plan §6) -- sparse/expensive at the root, cheap
    and high-volume at the leaves. Never assign FABLE inside the hot loop."""
    FABLE = "fable"      # root + section thinking, top integration reviews
    SONNET = "sonnet"    # mid-tree decomposition, leaf review
    HAIKU = "haiku"      # leaf implementation (DSL emission vs manifest)


class ReviewStatus(str, Enum):
    PENDING = "pending"
    PASSED = "passed"
    FAILED = "failed"
    ESCALATED = "escalated"


@dataclass(frozen=True)
class ReviewState:
    """plan §3.6: three checks per review -- meets own acceptance criteria,
    composes with siblings, seams hold with local neighbors. A failed review
    always carries why, so a re-split/patch/escalate decision has something
    to act on.

    `metrics` carries the real numbers a check's own `reasons` strings are
    derived from (e.g. worst LUFS gap in dB, whether any sibling had
    undefined LUFS) -- added after orchestrate.py's `choose_fix_strategy`
    was found (2026-07-26) to rely on raw `len(reasons)` alone, which twice
    missed a real severity change across rounds that didn't happen to
    change the reason count. Optional/empty by default so old call sites
    and replayed historical data (which never populated it) keep working;
    a consumer that wants real magnitude comparisons should read this
    instead of re-parsing `reasons` text."""
    status: ReviewStatus = ReviewStatus.PENDING
    reasons: tuple[str, ...] = ()
    own_criteria_met: bool | None = None
    composes_with_siblings: bool | None = None
    seams_hold: bool | None = None
    metrics: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.status == ReviewStatus.FAILED and not self.reasons:
            raise ValueError("a FAILED review_state must carry at least one reason")


@dataclass(frozen=True)
class ScopeLink:
    """One rung of the tapered scope chain (plan §3.3) -- coarser the
    higher it sits. A leaf's chain is [album: one-liner, song: purpose +
    energy, section: fine-grained job], a *compressed* summary at each
    level, never the ancestor's full spec. This is what keeps per-call
    tokens bounded and keeps upper links cache-stable (plan §6)."""
    level: str      # ancestor's own tier, e.g. "album" | "song" | "section"
    summary: str    # compressed -- not the ancestor's own_purpose/spec verbatim


@dataclass(frozen=True)
class NeighborEdge:
    """Horizontal context (plan §3.4). Local edges are free and automatic
    (immediate timeline neighbors, added by whatever builds the tree, not
    declared by a model). Long-range edges are sparse, high-weight, and
    must be explicitly declared -- a motif that returns, an intro the
    finale resolves -- because only the root thinking node has the
    whole-album view needed to declare them (plan §3.4)."""
    target: str     # neighbor node_id
    kind: str       # "local" | "declared"
    weight: float   # decays with timeline distance; declared edges stay high

    def __post_init__(self) -> None:
        if self.kind not in ("local", "declared"):
            raise ValueError(f"kind must be 'local' or 'declared', got {self.kind!r}")


@dataclass(frozen=True)
class AcceptanceCriteria:
    """Machine-checkable target -- never an absolute magic value (plan
    §4.1). target_section_type is what reference.score_node scores
    distance into; structural_facts covers things that don't need an
    envelope at all (note count, bar count, a specific FX being present)."""
    target_section_type: str | None = None    # scored via return_channel.reference.score_node
    max_measured_distance: float | None = None
    max_embedding_distance: float | None = None
    structural_facts: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "target_section_type": self.target_section_type,
            "max_measured_distance": self.max_measured_distance,
            "max_embedding_distance": self.max_embedding_distance,
            "structural_facts": dict(self.structural_facts),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AcceptanceCriteria":
        return cls(**data)


@dataclass(frozen=True)
class Leaf:
    """Base case (plan §3.1): a bounded set of deterministic DSL commands
    against the manifest, with no remaining creative sub-decision --
    translation, not composition. `implementation`'s shape is deliberately
    opaque here: it's set by whichever Reaper-MCP gets picked (plan §8.1,
    "the MCP's typed tools are the DSL"), which hasn't happened yet."""
    implementation: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"kind": "leaf", "implementation": dict(self.implementation)}


@dataclass(frozen=True)
class Split:
    """A node that decomposes further. The tree (not this dataclass) owns
    node storage -- children are referenced by id, not embedded, so a
    child can be built/reviewed/snapshotted independently of its parent."""
    children: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {"kind": "split", "children": list(self.children)}


def _body_from_dict(data: dict) -> Split | Leaf:
    if data["kind"] == "leaf":
        return Leaf(implementation=data["implementation"])
    if data["kind"] == "split":
        return Split(children=tuple(data["children"]))
    raise ValueError(f"unknown body kind {data['kind']!r}")


@dataclass
class Node:
    """plan §3.2. A musical problem: either splits into child problems or
    is a leaf that implements. Every node carries enough to review itself
    without re-fetching the whole tree: its own job, its acceptance
    criteria, a tapered slice of ancestor context, and its local/declared
    neighbors.
    """
    node_id: str
    own_purpose: str
    spec: str
    acceptance_criteria: AcceptanceCriteria
    scope_chain: tuple[ScopeLink, ...]
    body: Split | Leaf
    neighbor_edges: tuple[NeighborEdge, ...] = ()
    review_state: ReviewState = field(default_factory=ReviewState)
    assigned_model: ModelTier = ModelTier.HAIKU
    snapshot_ref: str | None = None    # plan §7.3: pointer to this node's versioned project state
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    # Arc-planning (plan §6 root tier, src/planner/arc.py): a section's own
    # length and whether it's deliberately exempt from the ~40s soft cell
    # cap. Optional/default-safe for the same reason as ReviewState.metrics
    # above -- old call sites (scheduler.py, every proof script) never pass
    # these and must keep compiling unmodified.
    duration_s: float | None = None
    locked_grid: bool = False
    grid_justification: str = ""
    # A section's position on the song timeline, in seconds -- same
    # optional-default reasoning as duration_s above. Set by whatever
    # assembles a full arc from multiple sections (scripts/song_plan.py);
    # a lone section built in isolation (every prior proof script) has no
    # timeline to place itself on, so this stays None for it.
    timeline_start_s: float | None = None
    # Mixing-role intent (see PROMINENCE_LEVELS above), set by decompose.py
    # per child based on musical role. Defaults to "midground" -- the safe
    # middle when a node predates this field (old snapshots/proof scripts)
    # or genuinely doesn't need a strong opinion either way.
    prominence: str = "midground"

    def __post_init__(self) -> None:
        if self.locked_grid and not self.grid_justification.strip():
            raise ValueError(
                f"{self.node_id}: locked_grid=True requires a non-empty "
                f"grid_justification (a real declared reason, not a silent escape hatch)"
            )
        if self.prominence not in PROMINENCE_LEVELS:
            raise ValueError(
                f"{self.node_id}: prominence must be one of {PROMINENCE_LEVELS}, "
                f"got {self.prominence!r}"
            )

    @property
    def is_leaf(self) -> bool:
        return isinstance(self.body, Leaf)

    def to_dict(self) -> dict:
        """For snapshot persistence (plan §7.3) -- a run must be recoverable,
        two runs must be diffable. json.dumps(node.to_dict(), sort_keys=True)
        is the diffable form."""
        return {
            "node_id": self.node_id,
            "own_purpose": self.own_purpose,
            "spec": self.spec,
            "acceptance_criteria": self.acceptance_criteria.to_dict(),
            "scope_chain": [{"level": s.level, "summary": s.summary} for s in self.scope_chain],
            "body": self.body.to_dict(),
            "neighbor_edges": [{"target": e.target, "kind": e.kind, "weight": e.weight}
                              for e in self.neighbor_edges],
            "review_state": {
                "status": self.review_state.status.value,
                "reasons": list(self.review_state.reasons),
                "own_criteria_met": self.review_state.own_criteria_met,
                "composes_with_siblings": self.review_state.composes_with_siblings,
                "seams_hold": self.review_state.seams_hold,
                "metrics": dict(self.review_state.metrics),
            },
            "assigned_model": self.assigned_model.value,
            "snapshot_ref": self.snapshot_ref,
            "created_at": self.created_at,
            "duration_s": self.duration_s,
            "locked_grid": self.locked_grid,
            "grid_justification": self.grid_justification,
            "timeline_start_s": self.timeline_start_s,
            "prominence": self.prominence,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Node":
        rs = data["review_state"]
        return cls(
            node_id=data["node_id"],
            own_purpose=data["own_purpose"],
            spec=data["spec"],
            acceptance_criteria=AcceptanceCriteria.from_dict(data["acceptance_criteria"]),
            scope_chain=tuple(ScopeLink(**s) for s in data["scope_chain"]),
            body=_body_from_dict(data["body"]),
            neighbor_edges=tuple(NeighborEdge(**e) for e in data["neighbor_edges"]),
            review_state=ReviewState(
                status=ReviewStatus(rs["status"]),
                reasons=tuple(rs["reasons"]),
                own_criteria_met=rs["own_criteria_met"],
                composes_with_siblings=rs["composes_with_siblings"],
                seams_hold=rs["seams_hold"],
                metrics=rs.get("metrics", {}),
            ),
            assigned_model=ModelTier(data["assigned_model"]),
            snapshot_ref=data["snapshot_ref"],
            created_at=data["created_at"],
            duration_s=data.get("duration_s"),
            locked_grid=data.get("locked_grid", False),
            grid_justification=data.get("grid_justification", ""),
            timeline_start_s=data.get("timeline_start_s"),
            prominence=data.get("prominence", "midground"),
        )
