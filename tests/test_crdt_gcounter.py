"""GCounter: grow-only counter over per-replica totals."""

from __future__ import annotations

import pytest

from anticloud_ref.crdt.gcounter import GCounter


class TestConstruction:
    def test_empty_counter_is_zero(self):
        assert GCounter("a").value() == 0

    def test_node_id_is_exposed(self):
        assert GCounter("replica-1").node_id == "replica-1"

    def test_empty_node_id_rejected(self):
        with pytest.raises(ValueError, match="non-empty"):
            GCounter("")

    def test_non_string_node_id_rejected(self):
        with pytest.raises(ValueError, match="non-empty string"):
            GCounter(42)

    def test_seed_counts_are_copied_not_aliased(self):
        seed = {"a": 1}
        counter = GCounter("a", seed)
        seed["a"] = 99
        assert counter.value() == 1

    def test_counts_property_returns_a_defensive_copy(self):
        counter = GCounter("a", {"a": 1, "b": 2})
        snapshot = counter.counts
        snapshot["a"] = 500
        assert counter.counts["a"] == 1

    def test_negative_seed_value_rejected(self):
        with pytest.raises(ValueError, match=">= 0"):
            GCounter("a", {"b": -1})

    def test_bool_seed_value_rejected(self):
        with pytest.raises(TypeError, match="must be int"):
            GCounter("a", {"b": True})

    def test_float_seed_value_rejected(self):
        with pytest.raises(TypeError, match="must be int"):
            GCounter("a", {"b": 1.5})


class TestIncrement:
    def test_increment_by_one(self):
        counter = GCounter("a")
        assert counter.increment() == 1
        assert counter.value() == 1

    def test_increment_by_amount(self):
        counter = GCounter("a")
        counter.increment(5)
        assert counter.value() == 5

    def test_increment_accumulates(self):
        counter = GCounter("a")
        for _ in range(10):
            counter.increment(3)
        assert counter.value() == 30

    def test_zero_increment_is_rejected_because_grow_only(self):
        # A grow-only counter cannot represent a decrement, so increment(0) is
        # refused rather than silently ignored: a caller who meant to add
        # nothing should not be told the write happened.
        with pytest.raises(ValueError, match="> 0"):
            GCounter("a").increment(0)

    def test_negative_increment_rejected(self):
        counter = GCounter("a")
        with pytest.raises(ValueError):
            counter.increment(-1)

    def test_increment_tracks_local_contribution(self):
        counter = GCounter("a")
        counter.increment(4)
        assert counter.local() == 4
        assert counter.value() == 4

    def test_local_is_zero_for_a_replica_with_no_writes(self):
        assert GCounter("a", {"b": 3}).local() == 0

    def test_float_increment_rejected(self):
        with pytest.raises(TypeError):
            GCounter("a").increment(1.5)

    def test_bool_increment_rejected(self):
        with pytest.raises(TypeError):
            GCounter("a").increment(True)


class TestReset:
    def test_reset_clears_only_local_contribution(self):
        counter = GCounter("a", {"b": 7})
        counter.increment(3)
        counter.reset()
        assert counter.value() == 7
        assert counter.local() == 0

    def test_reset_keeps_the_replica_entry_present(self):
        counter = GCounter("a")
        counter.increment(1)
        counter.reset()
        assert "a" in counter.replicas

    def test_increment_after_reset_still_merges(self):
        left = GCounter("a")
        left.increment(5)
        left.reset()
        left.increment(2)
        right = GCounter("b")
        right.increment(3)
        assert left.merged(right).value() == 5


class TestMerge:
    def test_merge_is_commutative(self):
        a, b = GCounter("a"), GCounter("b")
        a.increment(3)
        b.increment(4)
        assert a.merged(b).value() == b.merged(a).value() == 7

    def test_merge_is_idempotent(self):
        a, b = GCounter("a"), GCounter("b")
        a.increment(3)
        merged = a.merged(b)
        assert merged.merged(b).value() == merged.value()

    def test_merge_is_associative(self):
        a, b, c = GCounter("a"), GCounter("b"), GCounter("c")
        a.increment(1)
        b.increment(2)
        c.increment(3)
        left = a.merged(b).merged(c)
        right = a.merged(b.merged(c))
        assert left.value() == right.value() == 6

    def test_merge_takes_the_max_per_replica(self):
        left = GCounter("merge", {"a": 10})
        right = GCounter("merge", {"a": 4})
        assert left.merged(right).value() == 10

    def test_merged_does_not_mutate_the_receiver(self):
        a, b = GCounter("a"), GCounter("b")
        a.increment(1)
        b.increment(2)
        a.merged(b)
        assert a.value() == 1

    def test_merged_does_not_mutate_the_argument(self):
        a, b = GCounter("a"), GCounter("b")
        b.increment(2)
        a.merged(b)
        assert b.value() == 2

    def test_merge_with_self_is_a_noop(self):
        a = GCounter("a", {"a": 5})
        assert a.merged(a).value() == 5

    def test_merge_preserves_distinct_replica_entries(self):
        a, b = GCounter("a"), GCounter("b")
        a.increment(1)
        b.increment(1)
        assert set(a.merged(b).replicas) == {"a", "b"}

    def test_in_place_merge_matches_merged(self):
        # Feed both replicas into a sink and compare the in-place path against
        # the non-mutating one.  Merging only `b` into a sink that never saw `a`
        # would legitimately miss `a`'s contribution.
        a, b = GCounter("a"), GCounter("b")
        a.increment(3)
        b.increment(4)

        expected = GCounter("sink").merged(a).merged(b)
        in_place = GCounter("sink")
        in_place.merge(a)
        in_place.merge(b)
        assert in_place.counts == expected.counts
        assert in_place.value() == expected.value() == 7

    def test_three_way_merge_converges_regardless_of_order(self):
        import itertools

        replicas = []
        for name, amount in (("a", 3), ("b", 5), ("c", 7)):
            replica = GCounter(name)
            replica.increment(amount)
            replicas.append(replica)

        results = set()
        for order in itertools.permutations(replicas):
            sink = GCounter("sink")
            for replica in order:
                sink.merge(replica)
            results.add(sink.value())
        assert results == {15}

    def test_merge_accepts_subclass_state(self):
        a = GCounter("a")
        a.increment(1)
        b = GCounter.from_state_dict(a.state_dict())
        assert a.merged(b).value() == 1


class TestDunders:
    def test_int_conversion(self):
        counter = GCounter("a")
        counter.increment(4)
        assert int(counter) == 4

    def test_len_counts_replicas_not_value(self):
        counter = GCounter("a")
        counter.increment(10)
        assert len(counter) == 1

    def test_equality_compares_state(self):
        a = GCounter("a", {"a": 1})
        b = GCounter("b", {"a": 1})
        assert a == b

    def test_inequality_on_different_state(self):
        assert GCounter("a", {"a": 1}) != GCounter("a", {"a": 2})

    def test_equality_against_other_type_is_not_implemented(self):
        assert GCounter("a").__eq__(5) is NotImplemented

    def test_hash_matches_for_equal_state(self):
        a = GCounter("a", {"a": 1, "b": 2})
        b = GCounter("z", {"b": 2, "a": 1})
        assert hash(a) == hash(b)

    def test_iteration_is_sorted(self):
        counter = GCounter("a", {"z": 1, "a": 1, "m": 1})
        assert list(counter) == ["a", "m", "z"]

    def test_repr_shows_state(self):
        assert "GCounter" in repr(GCounter("a", {"a": 1}))


class TestSerialization:
    def test_state_dict_shape(self):
        state = GCounter("a", {"a": 1}).state_dict()
        assert state["type"] == "GCounter"
        assert state["node_id"] == "a"
        assert state["counts"] == {"a": 1}

    def test_round_trip_preserves_value(self):
        original = GCounter("a", {"a": 1})
        original.increment(2)
        restored = GCounter.from_state_dict(original.state_dict())
        assert restored.value() == original.value()
        assert restored.counts == original.counts

    def test_from_state_dict_rejects_wrong_type(self):
        with pytest.raises(ValueError, match="expected type"):
            GCounter.from_state_dict({"type": "PNCounter", "node_id": "a"})

    def test_from_state_dict_rejects_non_mapping(self):
        with pytest.raises(TypeError):
            GCounter.from_state_dict(["not", "a", "mapping"])

    def test_from_state_dict_requires_node_id(self):
        with pytest.raises(KeyError):
            GCounter.from_state_dict({"type": "GCounter", "counts": {}})

    def test_round_trip_survives_merge(self):
        a = GCounter.from_state_dict(GCounter("a", {"a": 1}).state_dict())
        b = GCounter("b")
        b.increment(9)
        assert a.merged(b).value() == 10
