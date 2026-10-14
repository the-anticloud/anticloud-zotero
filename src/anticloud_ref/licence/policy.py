"""The operational rules that follow from a licence class.

These are pure functions over the class so that the CLI, the CI gate and the
tests all enforce exactly the same policy rather than three drifting copies.
"""

from __future__ import annotations

from anticloud_ref.licence.classifier import B_POLICY, LicenseClass

#: Actions a class B component may take: use internally, modify, but never
#: redistribute outside the organisation and never relicense.
B_ACTIONS = frozenset({"use_internal", "modify", "audit", "vendor_privately"})

#: Actions a class C component may take: read the source for reference only.
C_ACTIONS = frozenset({"read_only", "cite"})


def policy_for(license_class: LicenseClass) -> frozenset[str]:
    """Return the set of permitted actions for ``license_class``."""
    if license_class == LicenseClass.A:
        return frozenset(B_ACTIONS | {"vendor", "relicense", "push_as_ours", "redistribute"})
    if license_class == LicenseClass.B:
        return B_ACTIONS
    if license_class == LicenseClass.C:
        return C_ACTIONS
    raise ValueError(f"unknown licence class: {license_class!r}")


def can_push_as_ours(license_class: LicenseClass) -> bool:
    """Only class A code may be republished under an Anticloud licence."""
    return "push_as_ours" in policy_for(license_class)


def requires_internal_only(license_class: LicenseClass) -> bool:
    """Class B code may be used and deployed, but only inside the organisation."""
    return license_class == LicenseClass.B


def redistribution_allowed(license_class: LicenseClass) -> bool:
    """Whether the component may ship outside the organisation as a source release."""
    return license_class == LicenseClass.A


def assert_not_forbidden(license_class: LicenseClass, action: str) -> None:
    """Raise unless ``action`` is permitted for ``license_class``."""
    if action not in policy_for(license_class):
        allowed = ", ".join(sorted(policy_for(license_class)))
        raise PermissionError(
            f"action {action!r} is not permitted for licence class "
            f"{license_class.name} (permitted: {allowed})"
        )


assert B_POLICY  # re-exported for callers importing from this module
