"""Node schema tests (plan §3.2): construction, validation, round-trip."""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from planner.node import (  # noqa: E402
    AcceptanceCriteria, Leaf, ModelTier, NeighborEdge, Node, ReviewState,
    ReviewStatus, ScopeLink, Split,
)


def make_leaf_node(node_id="album.song1.section1.leaf1") -> Node:
    return Node(
        node_id=node_id,
        own_purpose="place the 32 acid-line notes at these velocities",
        spec="32 notes, C minor, velocities 60-100",
        acceptance_criteria=AcceptanceCriteria(target_section_type="drop",
                                               structural_facts={"note_count": 32}),
        scope_chain=(ScopeLink("album", "cold machine-native concept album"),
                    ScopeLink("song", "track 3, rhythmic-machine energy peak")),
        body=Leaf(implementation={"tool": "insert_notes", "notes": []}),
    )


class TestReviewState(unittest.TestCase):
    def test_pending_by_default(self):
        self.assertEqual(ReviewState().status, ReviewStatus.PENDING)

    def test_failed_requires_reasons(self):
        with self.assertRaises(ValueError):
            ReviewState(status=ReviewStatus.FAILED)

    def test_failed_with_reasons_is_fine(self):
        rs = ReviewState(status=ReviewStatus.FAILED, reasons=("seam broke",))
        self.assertEqual(rs.reasons, ("seam broke",))


class TestNeighborEdge(unittest.TestCase):
    def test_local_and_declared_are_valid(self):
        NeighborEdge(target="x", kind="local", weight=0.9)
        NeighborEdge(target="x", kind="declared", weight=1.0)

    def test_other_kind_rejected(self):
        with self.assertRaises(ValueError):
            NeighborEdge(target="x", kind="ambient", weight=0.5)


class TestNodeBody(unittest.TestCase):
    def test_leaf_node_is_leaf(self):
        self.assertTrue(make_leaf_node().is_leaf)

    def test_split_node_is_not_leaf(self):
        node = make_leaf_node()
        node.body = Split(children=("album.song1.section1", "album.song1.section2"))
        self.assertFalse(node.is_leaf)


class TestNodeRoundTrip(unittest.TestCase):
    def test_leaf_node_survives_dict_round_trip(self):
        node = make_leaf_node()
        restored = Node.from_dict(node.to_dict())
        self.assertEqual(restored.to_dict(), node.to_dict())
        self.assertTrue(restored.is_leaf)

    def test_split_node_survives_dict_round_trip(self):
        node = make_leaf_node()
        node.body = Split(children=("a", "b"))
        node.neighbor_edges = (NeighborEdge("a", "local", 0.8),
                              NeighborEdge("finale", "declared", 1.0))
        node.review_state = ReviewState(status=ReviewStatus.FAILED, reasons=("x",))
        node.assigned_model = ModelTier.SONNET
        restored = Node.from_dict(node.to_dict())
        self.assertEqual(restored.to_dict(), node.to_dict())
        self.assertFalse(restored.is_leaf)

    def test_dict_form_is_json_diffable(self):
        # plan §7.3: a run must be diffable -- this is the actual serialized form.
        node = make_leaf_node()
        text = json.dumps(node.to_dict(), sort_keys=True)
        self.assertEqual(json.loads(text), node.to_dict())


if __name__ == "__main__":
    unittest.main()
