"""Adversarial convergence tests for the CRDT layer.

The merge laws asserted here are the whole basis of the CRDT claim: if a
regression makes ``merge`` non-commutative, non-associative or non-idempotent,
replicas silently diverge and every downstream correctness guarantee is void.

These tests are deliberately *adversarial* rather than a happy-path smoke test.
They feed each type concurrent updates, out-of-order delivery, duplicate
delivery and interleaved remove/add of the same element, then require the
replicas to agree.  The exhaustive permutation check in
:func:`assert_convergent` is kept to small replica counts so it stays
exhaustive rather than sampled.
"""

from __future__ import annotations

import itertools

import pytest

from anticloud_ref.crdt.convergence import (
    ConvergenceError,
    all_pairwise_orderings_converge,
    assert_convergent,
    check_associative,
    check_commutative,
    check_idempotent,
    convergence_report,
)
from anticloud_ref.crdt.gcounter import GCounter
from anticloud_ref.crdt.lww import HybridLogicalClock, LWWRegister
from anticloud_ref.crdt.orset import ORSet
from anticloud_ref.crdt.pncounter import PNCounter


def _concurrent_gcounters(replicas: int = 3) -> list[GCounter]:
    """Each replica increments itself a different number of times."""
    nodes = [GCounter(f"g{i}") for i in range(replicas)]
    for offset, node in enumerate(nodes, start=1):
        for _ in range(offset):
            node.increment(offset)
    return nodes


def _concurrent_pncounters(replicas: int = 3) -> list[PNCounter]:
    """Each replica applies a different mix of positive and negative deltas."""
    nodes = [PNCounter(f"p{i}") for i in range(replicas)]
    for offset, node in enumerate(nodes, start=1):
        node.apply(offset)
        node.apply(-offset)
    return nodes


def _equal_clock_registers() -> list[LWWRegister]:
    """Two replicas whose clocks read the same wall-clock instant.

    Equal timestamps are the interesting case: the hybrid logical clock has to
    break the tie deterministically, or the register diverges between replicas.
    """
    fixed = lambda: 1767225600.0  # 2026-01-01T00:00:00Z
    return [
        LWWRegister(f"r{i}", clock=HybridLogicalClock(f"r{i}", fixed)) for i in range(2)
    ]


def _concurrent_orset() -> list[ORSet]:
    """alice and bob diverge; alice tombstones what she saw, bob re-adds."""
    alice = ORSet("alice")
    alice.add("alpha")
    alice.add("beta")
    bob = alice.clone_as("bob")
    bob.add("alpha")  # fresh tag bob had not yet revealed
    bob.add("gamma")
    alice.remove("alpha")  # tombstone only the tag alice had observed
    return [alice, bob]


class TestMergeLaws:
    """Each algebraic law the merge operation must satisfy."""

    def test_gcounter_merge_is_commutative(self) -> None:
        left, right = GCounter("a"), GCounter("b")
        left.increment(3)
        right.increment(5)
        check_commutative(lambda: GCounter("sink"), left, right)

    def test_gcounter_merge_is_idempotent(self) -> None:
        node = GCounter("a")
        node.increment(7)
        check_idempotent(lambda: GCounter("sink"), node)

    def test_gcounter_merge_is_associative(self) -> None:
        nodes = [GCounter(f"n{i}") for i in range(3)]
        nodes[0].increment(2)
        nodes[1].increment(3)
        nodes[2].increment(5)
        check_associative(lambda: GCounter("sink"), nodes[0], nodes[1], nodes[2])

    def test_pncounter_merge_is_commutative(self) -> None:
        left, right = PNCounter("a"), PNCounter("b")
        left.apply(3)
        right.apply(-5)
        check_commutative(lambda: PNCounter("sink"), left, right)

    def test_pncounter_merge_is_idempotent(self) -> None:
        node = PNCounter("a")
        node.apply(-7)
        check_idempotent(lambda: PNCounter("sink"), node)

    def test_pncounter_merge_is_associative(self) -> None:
        nodes = [PNCounter(f"n{i}") for i in range(3)]
        nodes[0].apply(2)
        nodes[1].apply(-3)
        nodes[2].apply(5)
        check_associative(lambda: PNCounter("sink"), nodes[0], nodes[1], nodes[2])

    def test_commutative_failure_is_actually_detected(self) -> None:
        """The law checker must catch a deliberately broken merge.

        If this cannot raise, the checker is vacuous and every other test in
        this module proves nothing.
        """

        class BrokenCounter(GCounter):
            """Last-write-wins instead of a join: plainly order-dependent."""

            def merge(self, other):  # type: ignore[override]
                self._counts = dict(other._counts)  # noqa: SLF001 - deliberate probe
                return self

        a, b = BrokenCounter("a"), BrokenCounter("b")
        a.increment(1)
        b.increment(1)
        with pytest.raises(ConvergenceError):
            check_commutative(lambda: BrokenCounter("sink"), a, b)


class TestDeliveryOrders:
    """Out-of-order and duplicate delivery must not change the outcome."""

    def test_gcounter_all_permutations_converge(self) -> None:
        assert_convergent(lambda: GCounter("sink"), _concurrent_gcounters(3))

    def test_pncounter_all_permutations_converge(self) -> None:
        assert_convergent(lambda: PNCounter("sink"), _concurrent_pncounters(3))

    def test_orset_all_permutations_converge(self) -> None:
        assert_convergent(lambda: ORSet("sink"), _concurrent_orset())

    def test_duplicate_delivery_is_harmless(self) -> None:
        nodes = _concurrent_gcounters(3)
        once = GCounter("sink")
        for node in nodes:
            once.merge(node)
        redelivered = GCounter("sink")
        for node in nodes:
            redelivered.merge(node)
        redelivered.merge(nodes[1]).merge(nodes[0])  # duplicate deliveries
        assert redelivered.value() == once.value()
        assert redelivered.counts == once.counts

    def test_permutation_scan_agrees_with_assertion(self) -> None:
        """The boolean helper must agree with the raising variant."""
        assert all_pairwise_orderings_converge(
            lambda: GCounter("sink"), _concurrent_gcounters(3)
        ) is True

    def test_every_permutation_yields_one_distinct_value(self) -> None:
        nodes = _concurrent_gcounters(3)
        results = set()
        for order in itertools.permutations(nodes):
            sink = GCounter("sink")
            for node in order:
                sink.merge(node)
            results.add(sink.value())
        assert results == {14}  # g0 += 1, g1 += 4, g2 += 9


class TestConcurrentSemantics:
    """Each type's documented concurrent-update semantics."""

    def test_orset_add_wins_over_concurrent_remove(self) -> None:
        alice, bob = _concurrent_orset()
        alice.merge(bob)
        bob.merge(alice)
        assert alice.elements() == bob.elements(), "replicas diverged"
        assert "alpha" in alice, "concurrent add must survive a concurrent remove"
        assert "gamma" in alice
        assert "beta" in alice

    def test_orset_remove_leaves_a_tombstone(self) -> None:
        alice, _bob = _concurrent_orset()
        assert alice.tombstone_count() > 0, "remove must leave a tombstone"

    def test_lww_equal_timestamps_resolve_deterministically(self) -> None:
        left, right = _equal_clock_registers()
        left.assign("from-r0")
        right.assign("from-r1")
        merged_left = left.merged(right)
        merged_right = right.merged(left)
        assert merged_left.value() == merged_right.value()
        assert merged_left.timestamp() == merged_right.timestamp()

    def test_lww_later_write_wins(self) -> None:
        left, right = _equal_clock_registers()
        left.assign("first")
        left.assign("second")
        right.assign("other")
        assert left.merged(right).value() == "second"

    def test_counter_total_is_sum_of_replicas(self) -> None:
        nodes = _concurrent_gcounters(3)
        sink = GCounter("sink")
        for node in nodes:
            sink.merge(node)
        assert sink.value() == sum(node.value() for node in nodes)


class TestConvergenceReport:
    """The machine-readable report consumed by the benchmark."""

    def test_report_declares_convergence(self) -> None:
        report = convergence_report()
        assert report["all_converged"] is True
        assert set(report["types"]) >= {"GCounter", "PNCounter", "ORSet", "LWWRegister"}

    def test_report_is_deterministic_for_a_fixed_seed(self) -> None:
        """Same seed, same verdict -- otherwise the benchmark is not auditable."""
        first = convergence_report(seed=1234)
        second = convergence_report(seed=1234)
        assert first["types"]["GCounter"] == second["types"]["GCounter"]
        assert first["types"]["PNCounter"] == second["types"]["PNCounter"]

    def test_oracle_reports_add_wins_counterpart(self) -> None:
        assert convergence_report()["types"]["ORSet"]["add_wins_concurrent"] is True