"""Licence classification for Anticloud's A/B/C policy.

The policy is deliberately conservative.  A verdict is only ever A when a
recognised permissive licence is positively identified; anything the classifier
cannot positively identify as permissive is C, not A.  B is reserved for
copyleft and source-available licences that forbid relicensing or restrict use
to internal deployment.
"""

from anticloud_ref.licence.classifier import (
    A_POLICY,
    B_POLICY,
    C_POLICY,
    LicenseClass,
    LicenseVerdict,
    classify_file,
    classify_name,
    classify_text,
    scan_tree,
)
from anticloud_ref.licence.policy import (
    can_push_as_ours,
    policy_for,
    redistribution_allowed,
    requires_internal_only,
)

__all__ = [
    "A_POLICY",
    "B_POLICY",
    "C_POLICY",
    "LicenseClass",
    "LicenseVerdict",
    "can_push_as_ours",
    "classify_file",
    "classify_name",
    "classify_text",
    "policy_for",
    "redistribution_allowed",
    "requires_internal_only",
    "scan_tree",
]
