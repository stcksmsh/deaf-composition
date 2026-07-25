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
    to act on."""
    status: ReviewStatus = ReviewStatus.PENDING
    reasons: tuple[str, ...] = ()
    own_criteria_met: bool | None = None
    composes_with_siblings: bool | None = None
    seams_hold: bool | None = None

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
            },
            "assigned_model": self.assigned_model.value,
            "snapshot_ref": self.snapshot_ref,
            "created_at": self.created_at,
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
            ),
            assigned_model=ModelTier(data["assigned_model"]),
            snapshot_ref=data["snapshot_ref"],
            created_at=data["created_at"],
        )
