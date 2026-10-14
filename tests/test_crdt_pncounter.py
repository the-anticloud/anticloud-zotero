"""PNCounter: grow-only counter pair giving a signed integer."""

from __future__ import annotations

import pytest

from anticloud_ref.crdt.pncounter import PNCounter


class TestConstruction:
    def test_starts_at_zero(self):
        assert PNCounter("a").value() == 0

    def test_node_id_exposed(self):
        assert PNCounter("replica-7").node_id == "replica-7"

    def test_empty_node_id_rejected(self):
        with pytest.raises(ValueError):
            PNCounter("")

    def test_halves_start_empty(self):
        counter = PNCounter("a")
        assert counter.positive.value() == 0
        assert counter.negative.value() == 0


class TestIncrementDecrement:
    def test_increment(self):
        counter = PNCounter("a")
        assert counter.increment(3) == 3
        assert counter.value() == 3

    def test_decrement(self):
        counter = PNCounter("a")
        assert counter.decrement(2) == -2
        assert counter.value() == -2

    def test_increment_and_decrement_cancel(self):
        counter = PNCounter("a")
        counter.increment(10)
        counter.decrement(10)
        assert counter.value() == 0

    def test_value_may_go_negative(self):
        counter = PNCounter("a")
        counter.decrement(5)
        assert counter.value() == -5

    def test_negative_increment_is_refused(self):
        # Decrementing is what decrement() is for; letting increment() go
        # negative would double-count once the halves are merged.
        with pytest.raises(ValueError):
            PNCounter("a").increment(-1)

    def test_apply_with_positive_delta(self):
        counter = PNCounter("a")
        assert counter.apply(4) == 4

    def test_apply_with_negative_delta(self):
        counter = PNCounter("a")
        assert counter.apply(-4) == -4

    def test_apply_zero_returns_the_current_value(self):
        # apply(0) is a legitimate read-only no-op: it must not touch either
        # half, or a polling caller would inflate the merge state.
        counter = PNCounter("a")
        counter.increment(4)
        assert counter.apply(0) == 4
        assert counter.positive.value() == 4
        assert counter.negative.value() == 0

    def test_apply_bool_is_refused(self):
        with pytest.raises(TypeError):
            PNCounter("a").apply(True)

    def test_apply_float_is_refused(self):
        with pytest.raises(TypeError):
            PNCounter("a").apply(1.5)

    def test_positive_and_negative_halves_are_separate(self):
        counter = PNCounter("a")
        counter.increment(5)
        counter.decrement(2)
        assert counter.positive.value() == 5
        assert counter.negative.value() == 2
        assert counter.value() == 3


class TestMerge:
    def test_merge_is_commutative(self):
        a, b = PNCounter("a"), PNCounter("b")
        a.increment(3)
        b.increment(4)
        assert a.merged(b).value() == b.merged(a).value() == 7

    def test_merge_is_idempotent(self):
        a, b = PNCounter("a"), PNCounter("b")
        a.increment(3)
        merged = a.merged(b)
        assert merged.merged(b).value() == merged.value()

    def test_merge_is_associative(self):
        a, b, c = PNCounter("a"), PNCounter("b"), PNCounter("c")
        a.increment(1)
        b.increment(2)
        c.increment(3)
        assert a.merged(b).merged(c).value() == a.merged(b.merged(c)).value() == 6

    def test_concurrent_increment_and_decrement_both_survive(self):
        left, right = PNCounter("a"), PNCounter("b")
        left.increment(10)
        right.decrement(4)
        # The naive integer resolution would give 6; the CRDT must give 6 too,
        # but by summing both replicas' independent contributions.
        assert left.merged(right).value() == 6

    def test_decrement_on_one_side_never_cancels_an_unrelated_increment(self):
        a, b = PNCounter("a"), PNCounter("b")
        a.decrement(5)
        b.increment(5)
        assert a.merged(b).value() == 0
        assert a.merged(b).positive.value() == 5
        assert a.merged(b).negative.value() == 5

    def test_merge_takes_per_replica_maxima_in_each_half(self):
        left = PNCounter("m")
        left.increment(10)
        right = PNCounter.from_state_dict(left.state_dict())
        assert left.merged(right).value() == 10

    def test_merged_does_not_mutate_receiver(self):
        a, b = PNCounter("a"), PNCounter("b")
        a.increment(1)
        b.increment(2)
        a.merged(b)
        assert a.value() == 1

    def test_merged_does_not_mutate_argument(self):
        a, b = PNCounter("a"), PNCounter("b")
        b.increment(2)
        a.merged(b)
        assert b.value() == 2

    def test_merge_rejects_a_gcounter(self):
        from anticloud_ref.crdt.gcounter import GCounter

        with pytest.raises(TypeError):
            PNCounter("a").merge(GCounter("b"))

    def test_five_replicas_converge_under_random_delivery(self):
        import random

        rng = random.Random(4242)
        replicas = [PNCounter(f"r{i}") for i in range(5)]
        for _ in range(200):
            replica = rng.choice(replicas)
            delta = rng.randint(1, 5)
            replica.apply(delta if rng.random() < 0.6 else -delta)

        expected = sum(r.value() for r in replicas)
        orders = []
        for seed in (1, 2, 3):
            order = list(range(5))
            random.Random(seed).shuffle(order)
            sink = PNCounter("sink")
            for index in order:
                sink.merge(replicas[index])
            orders.append(sink.value())
        assert orders == [expected, expected, expected]

    def test_writes_after_merge_are_not_lost(self):
        a, b = PNCounter("a"), PNCounter("b")
        a.increment(5)
        b.increment(5)
        merged = a.merged(b)
        merged.increment(1)
        assert merged.value() == 11
        assert merged.merged(b).value() == 11


class TestDunders:
    def test_int_conversion(self):
        counter = PNCounter("a")
        counter.increment(7)
        assert int(counter) == 7

    def test_equality_compares_full_state_not_just_value(self):
        # Two replicas that each landed on 5 are NOT in the same state: merging
        # them must yield 10, so treating them as equal would be a real bug.
        a, b = PNCounter("a"), PNCounter("b")
        a.increment(5)
        b.increment(5)
        assert a != b
        assert a.value() == b.value() == 5
        assert a.merged(b).value() == 10

    def test_hash_matches_for_equal_state(self):
        a = PNCounter("a")
        b = PNCounter.from_state_dict(a.state_dict())
        b.increment(3)
        a.increment(3)
        assert hash(a) == hash(b)
        assert a == b

    def test_inequality_on_different_value(self):
        a, b = PNCounter("a"), PNCounter("b")
        a.increment(1)
        assert a != b

    def test_repr_shows_state(self):
        assert "PNCounter" in repr(PNCounter("a"))

    def test_equality_against_other_type_is_not_implemented(self):
        assert PNCounter("a").__eq__(1) is NotImplemented


class TestSerialization:
    def test_state_dict_shape(self):
        counter = PNCounter("a")
        counter.increment(3)
        state = counter.state_dict()
        assert state["type"] == "PNCounter"
        assert state["node_id"] == "a"
        assert set(state) >= {"positive", "negative"}

    def test_round_trip_preserves_value(self):
        counter = PNCounter("a")
        counter.increment(5)
        counter.decrement(2)
        restored = PNCounter.from_state_dict(counter.state_dict())
        assert restored.value() == counter.value() == 3

    def test_round_trip_preserves_negative_value(self):
        counter = PNCounter("a")
        counter.decrement(4)
        assert PNCounter.from_state_dict(counter.state_dict()).value() == -4

    def test_restored_counter_merges_correctly(self):
        original = PNCounter("a")
        original.increment(5)
        restored = PNCounter.from_state_dict(original.state_dict())
        other = PNCounter("b")
        other.increment(2)
        assert restored.merged(other).value() == 7

    def test_from_state_dict_rejects_wrong_type(self):
        with pytest.raises(ValueError, match="expected type"):
            PNCounter.from_state_dict({"type": "GCounter", "node_id": "a"})

    def test_from_state_dict_rejects_non_mapping(self):
        with pytest.raises(TypeError):
            PNCounter.from_state_dict(None)

    def test_from_state_dict_requires_node_id(self):
        with pytest.raises(KeyError):
            PNCounter.from_state_dict({"type": "PNCounter"})

    def test_apply_after_round_trip_accumulates(self):
        counter = PNCounter("a")
        counter.increment(5)
        restored = PNCounter.from_state_dict(counter.state_dict())
        restored.increment(1)
        assert restored.value() == 6
