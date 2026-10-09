"""The A/B/C licence policy, executed as tests.

The policy exists to stop a specific failure: someone ships a copyleft or
source-available dependency under an Anticloud licence, or vendors it into a
product that is redistributed.  That is a legal and operational harm, not a
style preference, so the rules are encoded as executable predicates in
``anticloud_ref.licence.policy`` and asserted here.

These tests are the *review* mechanism the ISO 27001 control 5.1.2 refers to.
If someone edits ``policy.py`` to widen a class, this module fails and the
change does not reach a release silently.
"""

from __future__ import annotations

import pytest

from anticloud_ref.licence.classifier import (
    A_POLICY,
    B_POLICY,
    C_POLICY,
    LicenseClass,
)
from anticloud_ref.licence.policy import (
    B_ACTIONS,
    C_ACTIONS,
    assert_not_forbidden,
    can_push_as_ours,
    policy_for,
    redistribution_allowed,
    requires_internal_only,
)


class TestClassDefinitions:
    """The three buckets and their ordering."""

    def test_exactly_three_classes(self) -> None:
        assert {member.value for member in LicenseClass} == {"A", "B", "C"}

    def test_classes_are_strings(self) -> None:
        assert LicenseClass.A == "A"
        assert str(LicenseClass.B) == "B"

    def test_policy_statements_are_non_empty_prose(self) -> None:
        for statement in (A_POLICY, B_POLICY, C_POLICY):
            assert isinstance(statement, str)
            assert len(statement) > 20, "a policy with no wording cannot be reviewed"


class TestPolicyFor:
    """The action sets per class."""

    def test_class_a_permits_the_full_set(self) -> None:
        allowed = policy_for(LicenseClass.A)
        assert {"vendor", "relicense", "push_as_ours", "redistribute"} <= allowed

    def test_class_b_is_internal_only(self) -> None:
        assert policy_for(LicenseClass.B) == B_ACTIONS

    def test_class_c_is_read_only(self) -> None:
        assert policy_for(LicenseClass.C) == C_ACTIONS

    def test_class_a_is_a_superset_of_b(self) -> None:
        assert B_ACTIONS < policy_for(LicenseClass.A)

    def test_class_b_and_c_actions_are_disjoint(self) -> None:
        assert not (B_ACTIONS & C_ACTIONS)

    def test_policy_sets_are_immutable(self) -> None:
        assert isinstance(policy_for(LicenseClass.A), frozenset)

    def test_unknown_class_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="unknown licence class"):
            policy_for("D")  # type: ignore[arg-type]


class TestRestrictivePredicates:
    """The single-question predicates used by the CLI and CI gate."""

    def test_only_class_a_may_be_pushed_as_ours(self) -> None:
        assert can_push_as_ours(LicenseClass.A) is True
        assert can_push_as_ours(LicenseClass.B) is False
        assert can_push_as_ours(LicenseClass.C) is False

    def test_only_class_b_is_internal_only(self) -> None:
        assert requires_internal_only(LicenseClass.B) is True
        assert requires_internal_only(LicenseClass.A) is False
        assert requires_internal_only(LicenseClass.C) is False

    def test_only_class_a_may_be_redistributed(self) -> None:
        assert redistribution_allowed(LicenseClass.A) is True
        assert redistribution_allowed(LicenseClass.B) is False
        assert redistribution_allowed(LicenseClass.C) is False


class TestForbiddenActions:
    """The actions that must be refused, refused loudly."""

    @pytest.mark.parametrize(
        ("license_class", "action"),
        [
            (LicenseClass.B, "relicense"),
            (LicenseClass.B, "redistribute"),
            (LicenseClass.B, "push_as_ours"),
            (LicenseClass.C, "modify"),
            (LicenseClass.C, "vendor"),
            (LicenseClass.C, "use_internal"),
        ],
    )
    def test_forbidden_action_raises(self, license_class, action) -> None:
        with pytest.raises(PermissionError):
            assert_not_forbidden(license_class, action)

    @pytest.mark.parametrize(
        ("license_class", "action"),
        [
            (LicenseClass.A, "vendor"),
            (LicenseClass.A, "relicense"),
            (LicenseClass.B, "use_internal"),
            (LicenseClass.B, "modify"),
            (LicenseClass.C, "read_only"),
            (LicenseClass.C, "cite"),
        ],
    )
    def test_permitted_action_does_not_raise(self, license_class, action) -> None:
        assert_not_forbidden(license_class, action)

    def test_error_names_the_class_and_the_alternatives(self) -> None:
        with pytest.raises(PermissionError) as excinfo:
            assert_not_forbidden(LicenseClass.C, "vendor")
        message = str(excinfo.value)
        assert "vendor" in message
        assert "read_only" in message, "the error should list what IS permitted"

    def test_unknown_action_is_refused(self) -> None:
        """An action nobody defined must fail closed, not default to allowed."""
        for license_class in LicenseClass:
            with pytest.raises(PermissionError):
                assert_not_forbidden(license_class, "launch_missiles")


class TestPolicyIsReviewable:
    """Guards against the policy being widened by accident."""

    def test_class_c_can_never_gain_a_modifying_action(self) -> None:
        """Class C is reference-only; a write action here is a policy regression."""
        forbidden = {"modify", "vendor", "use_internal", "relicense", "redistribute"}
        assert not (C_ACTIONS & forbidden)

    def test_class_b_can_never_gain_a_redistribution_action(self) -> None:
        forbidden = {"redistribute", "push_as_ours", "relicense"}
        assert not (B_ACTIONS & forbidden)

    def test_every_permitted_action_is_declared_somewhere(self) -> None:
        declared = set(policy_for(LicenseClass.A)) | set(B_ACTIONS) | set(C_ACTIONS)
        assert declared  # sanity: the union is not empty
        assert declared >= {"read_only", "cite", "use_internal", "modify", "vendor"}