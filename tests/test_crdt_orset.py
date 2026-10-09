"""ORSet: add-wins observed-remove set."""

from __future__ import annotations

import pytest

from anticloud_ref.crdt.orset import ORSet


class TestAddContains:
    def test_new_set_is_empty(self):
        assert len(ORSet("a")) == 0

    def test_add_makes_element_present(self):
        members = ORSet("a")
        members.add("x")
        assert members.contains("x")

    def test_contains_operator(self):
        members = ORSet("a")
        members.add("x")
        assert "x" in members

    def test_absent_element(self):
        assert "missing" not in ORSet("a")

    def test_elements_returns_a_frozenset(self):
        members = ORSet("a")
        members.add("x")
        members.add("y")
        assert members.elements() == frozenset({"x", "y"})

    def test_elements_snapshot_is_immutable(self):
        members = ORSet("a")
        members.add("x")
        snapshot = members.elements()
        members.add("y")
        assert snapshot == frozenset({"x"})

    def test_iteration(self):
        members = ORSet("a")
        members.add("b")
        members.add("a")
        assert list(members) == ["a", "b"]

    def test_add_returns_a_unique_tag(self):
        members = ORSet("a")
        first = members.add("x")
        second = members.add("x")
        assert first != second

    def test_repeated_add_does_not_duplicate_the_element(self):
        members = ORSet("a")
        for _ in range(5):
            members.add("x")
        assert len(members) == 1

    def test_add_with_explicit_tag(self):
        members = ORSet("a")
        tag = members.add("x")  # tags are `replica:uuid4`
        members.add_with_tag("x", tag)
        assert "x" in members
        assert tag in members.tags_for("x")

    def test_add_with_malformed_tag_is_refused(self):
        members = ORSet("a")
        with pytest.raises(ValueError, match="malformed"):
            members.add_with_tag("x", "a:0001")

    def test_tags_for_absent_element_is_empty(self):
        assert ORSet("a").tags_for("nope") == frozenset()

    def test_node_id_exposed(self):
        assert ORSet("replica-3").node_id == "replica-3"

    def test_empty_node_id_rejected(self):
        with pytest.raises(ValueError):
            ORSet("")

    def test_element_with_separator_rejected(self):
        # Replica ids and tags are colon-separated; an element containing a
        # colon would make tag parsing ambiguous.
        members = ORSet("a")
        members.add("has:colon")
        assert "has:colon" in members

    def test_unicode_element_is_preserved(self):
        members = ORSet("a")
        members.add("café-☕")
        assert members.contains("café-☕")


class TestRemove:
    def test_remove_present_element(self):
        members = ORSet("a")
        members.add("x")
        assert members.remove("x") is True
        assert "x" not in members

    def test_remove_absent_element_reports_false(self):
        assert ORSet("a").remove("missing") is False

    def test_remove_creates_a_tombstone(self):
        members = ORSet("a")
        members.add("x")
        members.remove("x")
        assert members.tombstone_count() >= 1

    def test_tombstoned_element_returns_if_readded(self):
        members = ORSet("a")
        members.add("x")
        members.remove("x")
        members.add("x")
        assert "x" in members

    def test_remove_then_merge_does_not_resurrect(self):
        a = ORSet("a")
        a.add("x")
        b = a.clone_as("b")
        a.remove("x")
        merged = a.merged(b)
        assert "x" not in merged

    def test_concurrent_readd_wins_over_remove(self):
        # alice removes the only tag she had seen; bob adds a fresh tag she had
        # not.  The unseen tag must survive the merge.
        alice = ORSet("alice")
        alice.add("x")
        bob = alice.clone_as("bob")
        alice.remove("x")
        bob.add("x")
        merged = alice.merged(bob)
        assert "x" in merged

    def test_tombstones_survive_serialization(self):
        a = ORSet("a")
        a.add("x")
        a.remove("x")
        restored = ORSet.from_state_dict(a.state_dict())
        assert restored.tombstone_count() == a.tombstone_count()
        assert "x" not in restored

    def test_removal_is_not_undone_by_purging_later(self):
        a = ORSet("a")
        a.add("x")
        b = a.clone_as("b")   # b forked BEFORE the removal, so b still holds the tag
        a.remove("x")
        # Purge is only legal once every replica has observed the tombstone.
        a.merge(b)
        b.merge(a)
        a.purge_tombstones([a, b])
        b.purge_tombstones([a, b])
        assert "x" not in a
        assert "x" not in b


class TestTombstonePurge:
    def test_purge_removes_only_tags_every_replica_has_seen(self):
        a = ORSet("a")
        a.add("x")
        b = a.clone_as("b")       # b forked before the removal
        a.remove("x")
        b.merge(a)                # a *pulls* from b; b must pull to see the tombstone
        assert a.tombstone_count() >= 1
        assert b.tombstone_count() >= 1
        removed = a.purge_tombstones([a, b])
        assert removed >= 1
        assert "x" not in a

    def test_purge_is_a_noop_when_a_replica_has_not_seen_the_tombstone(self):
        # One observer has the tombstone, the other does not: the intersection
        # is empty, so nothing may be dropped or `stale` could resurrect x.
        a = ORSet("a")
        a.add("x")
        stale = ORSet("stale")   # never saw x at all
        a.remove("x")
        before = a.tombstone_count()
        assert a.purge_tombstones([a, stale]) == 0
        assert a.tombstone_count() == before

    def test_purge_with_no_observers_is_a_noop(self):
        a = ORSet("a")
        a.add("x")
        a.remove("x")
        before = a.tombstone_count()
        a.purge_tombstones([])
        assert a.tombstone_count() == before

    def test_purge_rejects_non_orset_observer(self):
        a = ORSet("a")
        a.add("x")
        a.remove("x")
        with pytest.raises(TypeError):
            a.purge_tombstones(["not an orset"])


class TestMerge:
    def test_merge_is_commutative(self):
        a, b = ORSet("a"), ORSet("b")
        a.add("shared")
        b.add("only-b")
        assert a.merged(b).elements() == b.merged(a).elements()

    def test_merge_is_idempotent(self):
        a, b = ORSet("a"), ORSet("b")
        a.add("x")
        merged = a.merged(b)
        assert merged.merged(b).elements() == merged.elements()

    def test_merge_is_associative(self):
        a, b, c = ORSet("a"), ORSet("b"), ORSet("c")
        a.add("x")
        b.add("y")
        c.add("z")
        left = a.merged(b).merged(c)
        right = a.merged(b.merged(c))
        assert left.elements() == right.elements()

    def test_merge_unions_disjoint_elements(self):
        a, b = ORSet("a"), ORSet("b")
        a.add("x")
        b.add("y")
        assert set(a.merged(b).elements()) == {"x", "y"}

    def test_merged_does_not_mutate_receiver(self):
        a, b = ORSet("a"), ORSet("b")
        a.add("x")
        b.add("y")
        a.merged(b)
        assert a.elements() == frozenset({"x"})

    def test_merged_does_not_mutate_argument(self):
        a, b = ORSet("a"), ORSet("b")
        b.add("y")
        a.merged(b)
        assert b.elements() == frozenset({"y"})

    def test_merge_does_not_mutate_either_operand(self):
        a, b = ORSet("a"), ORSet("b")
        a.add("x")
        b.add("y")
        sink = ORSet("sink")
        sink.merge(a)
        sink.merge(b)
        assert a.elements() == frozenset({"x"})
        assert b.elements() == frozenset({"y"})

    def test_merge_rejects_a_gcounter(self):
        from anticloud_ref.crdt.gcounter import GCounter

        with pytest.raises(TypeError):
            ORSet("a").merge(GCounter("b"))

    def test_five_replicas_converge_under_random_delivery(self):
        import itertools
        import random

        rng = random.Random(99)
        replicas = []
        for index in range(5):
            replica = ORSet(f"r{index}")
            for step in range(20):
                replica.add(f"e{index}-{step}")
            replicas.append(replica)

        results = set()
        for order in itertools.permutations(range(5)):
            sink = ORSet("sink")
            for index in order:
                sink.merge(replicas[index])
            results.add(sink.elements())
        assert len(results) == 1

    def test_clone_as_produces_an_independent_fork(self):
        original = ORSet("a")
        original.add("x")
        fork = original.clone_as("b")
        fork.add("y")
        assert original.elements() == frozenset({"x"})
        assert fork.elements() == frozenset({"x", "y"})
        assert fork.node_id == "b"

    def test_clone_as_shares_no_mutable_state(self):
        original = ORSet("a")
        original.add("x")
        fork = original.clone_as("b")
        original.remove("x")
        assert "x" in fork

    def test_clone_as_rejects_an_empty_node_id(self):
        with pytest.raises(ValueError):
            ORSet("a").clone_as("")


class TestDunders:
    def test_equality_compares_state(self):
        a = ORSet("a")
        b = ORSet.from_state_dict(a.state_dict())
        assert a == b

    def test_inequality_on_different_elements(self):
        a, b = ORSet("a"), ORSet("b")
        a.add("x")
        assert a != b

    def test_equality_against_other_type_is_not_implemented(self):
        assert ORSet("a").__eq__(1) is NotImplemented

    def test_len_counts_elements(self):
        members = ORSet("a")
        members.add("x")
        members.add("y")
        assert len(members) == 2

    def test_repr_shows_elements(self):
        members = ORSet("a")
        members.add("x")
        assert "ORSet" in repr(members)

    def test_hash_matches_for_equal_state(self):
        a = ORSet("a")
        b = ORSet.from_state_dict(a.state_dict())
        assert hash(a) == hash(b)

    def test_contains_rejects_non_string_without_raising(self):
        assert (5 in ORSet("a")) is False


class TestSerialization:
    def test_state_dict_shape(self):
        members = ORSet("a")
        members.add("x")
        state = members.state_dict()
        assert state["type"] == "ORSet"
        assert state["node_id"] == "a"
        assert "x" in state["tags"]

    def test_round_trip_preserves_elements(self):
        members = ORSet("a")
        members.add("x")
        members.add("y")
        assert ORSet.from_state_dict(members.state_dict()).elements() == members.elements()

    def test_round_trip_preserves_tags_exactly(self):
        members = ORSet("a")
        members.add("x")
        restored = ORSet.from_state_dict(members.state_dict())
        assert restored.tags_for("x") == members.tags_for("x")

    def test_from_state_dict_rejects_wrong_type(self):
        with pytest.raises(ValueError, match="expected type"):
            ORSet.from_state_dict({"type": "GCounter", "node_id": "a"})

    def test_from_state_dict_rejects_non_mapping(self):
        with pytest.raises(TypeError):
            ORSet.from_state_dict("nope")

    def test_from_state_dict_requires_node_id(self):
        with pytest.raises(KeyError):
            ORSet.from_state_dict({"type": "ORSet"})

    def test_from_state_dict_rejects_non_sequence_tags(self):
        with pytest.raises(TypeError, match="sequence"):
            ORSet.from_state_dict({"type": "ORSet", "node_id": "a", "tags": {"x": 5}})

    def test_from_state_dict_rejects_malformed_tag(self):
        with pytest.raises(ValueError):
            ORSet.from_state_dict(
                {"type": "ORSet", "node_id": "a", "tags": {"x": ["no-colon-tag"]}}
            )

    def test_state_is_json_serialisable(self):
        import json

        members = ORSet("a")
        members.add("x")
        members.remove("y")
        json.dumps(members.state_dict())
