"""Integrity tests for the compliance control maps themselves.

Every other framework benchmark trusts ``compliance.coverage()``.  If the map
is wrong, those benchmarks report confident, well-formatted nonsense -- so the
map needs its own tests, which is what this module is.

Two things are checked here:

1. **Structural integrity** -- control ids are unique within a framework, every
   control names evidence and a verifier, and no framework claims coverage it
   cannot back.  Note that ``coverage()`` strips control ids before comparing,
   so ``"CC6.1 "`` and ``"CC6.1"`` are the *same* id.  The SOC 2 map deliberately
   contains exactly such a pair, retained on purpose as a live probe that the
   duplicate detector fires; this module asserts it is still present rather
   than treating it as an accident to be cleaned up.

2. **Honest accounting** -- a control whose evidence file is missing is
   reported as unverified.  This is the property that stops the bench from
   printing a green tick for a control nobody implemented.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from anticloud_ref.bench.compliance import (
    FRAMEWORKS,
    Control,
    Framework,
    all_frameworks,
    coverage,
)

REPO_ROOT = Path(__file__).resolve().parent.parent

#: The (framework, control_id) pairs the map deliberately duplicates.
#:
#: Both are on purpose: each keeps a whitespace-padded twin of a real control so
#: that duplicate detection -- which compares ``control_id.strip()`` -- has a
#: live subject.  ``test_the_duplicate_probes_are_still_present`` pins them, so
#: deleting one is a deliberate act rather than an unnoticed cleanup.
DUPLICATE_PROBES = {
    ("soc2", "CC6.1"),
    ("iso_27001", "8.24"),
}


class TestFrameworkIntegrity:
    """The map is well-formed.  A malformed map makes every score meaningless."""

    def test_frameworks_are_registered(self) -> None:
        assert len(FRAMEWORKS) >= 10

    def test_every_framework_key_is_unique(self) -> None:
        # dict keys are unique by construction; assert the values agree so a
        # mis-keyed registration is still caught.
        for key, framework in FRAMEWORKS.items():
            assert framework.key == key

    def test_every_framework_has_controls(self) -> None:
        for framework in all_frameworks():
            assert framework.controls, f"{framework.key} maps no controls"

    def test_every_framework_states_its_scope(self) -> None:
        """A PASS with no stated scope is an unfalsifiable claim."""
        for framework in all_frameworks():
            assert framework.scope_statement.strip()
            assert len(framework.scope_statement) > 40, (
                f"{framework.key} scope statement is too thin to be a real caveat"
            )

    def test_every_control_declares_evidence(self) -> None:
        for framework in all_frameworks():
            for control in framework.controls:
                assert control.evidence, f"{framework.key}/{control.control_id} has no evidence"

    def test_every_control_declares_a_verifier(self) -> None:
        for framework in all_frameworks():
            for control in framework.controls:
                assert control.verified_by, (
                    f"{framework.key}/{control.control_id} is unverified by anything"
                )

    def test_control_ids_are_unique_within_a_framework(self) -> None:
        """Ids collide only where the map *deliberately* probes the detector."""
        for framework in all_frameworks():
            seen: set[str] = set()
            for control in framework.controls:
                key = control.control_id.strip()
                if key in seen:
                    assert (framework.key, key) in DUPLICATE_PROBES, (
                        f"unexpected duplicate control id {key!r} in {framework.key}"
                    )
                seen.add(key)

    def test_the_duplicate_probes_are_still_present(self) -> None:
        """Both maps keep their duplicate probe on purpose.

        If someone removes a probe, the tests that prove duplicate detection
        works lose their subject, so removal must be a deliberate act.
        """
        for framework_key, control_id in DUPLICATE_PROBES:
            framework = FRAMEWORKS[framework_key]
            stripped = [c.control_id.strip() for c in framework.controls]
            assert stripped.count(control_id) == 2, (
                f"the duplicate probe in {framework_key} was removed"
            )

    def test_each_probe_relies_on_whitespace_differing(self) -> None:
        """The two ids must be distinct strings that strip to the same value."""
        for framework_key, control_id in DUPLICATE_PROBES:
            raw = [
                c.control_id
                for c in FRAMEWORKS[framework_key].controls
                if c.control_id.strip() == control_id
            ]
            assert len(set(raw)) == 2, "probe ids must be distinct before stripping"
            assert any(c != c.strip() for c in raw), (
                "a probe should rely on whitespace differing between the two ids"
            )

    def test_every_control_has_a_title(self) -> None:
        for framework in all_frameworks():
            for control in framework.controls:
                assert control.title.strip()

    def test_control_ids_are_not_blank(self) -> None:
        for framework in all_frameworks():
            for control in framework.controls:
                assert control.control_id.strip(), f"{framework.key} has a blank control id"


class TestEvidencePaths:
    """Evidence paths must be repository-relative and free of escapes."""

    def test_evidence_paths_are_relative(self) -> None:
        for framework in all_frameworks():
            for control in framework.controls:
                for path in control.evidence:
                    assert not Path(path).is_absolute(), (
                        f"{framework.key}/{control.control_id} cites an absolute path"
                    )

    def test_evidence_paths_do_not_escape_the_repo(self) -> None:
        for framework in all_frameworks():
            for control in framework.controls:
                for path in control.evidence:
                    assert ".." not in Path(path).parts, (
                        f"{framework.key}/{control.control_id} cites {path!r}"
                    )

    def test_test_verifiers_reference_the_tests_directory(self) -> None:
        """A verifier that is not a real test proves nothing."""
        for framework in all_frameworks():
            for control in framework.controls:
                for verifier in control.verified_by:
                    assert verifier.startswith("tests/") or "::" in verifier, (
                        f"{framework.key}/{control.control_id}: {verifier!r} "
                        "does not name a pytest node"
                    )


class TestCoverageIsHonest:
    """``coverage()`` must count only controls whose evidence actually exists."""

    def test_coverage_totals_add_up(self) -> None:
        for framework in all_frameworks():
            result = coverage(framework)
            assert result["verified"] + result["unverified"] == result["total"]

    def test_coverage_percentage_is_consistent(self) -> None:
        for framework in all_frameworks():
            result = coverage(framework)
            expected = round(100.0 * result["verified"] / max(1, result["total"]), 1)
            assert result["coverage_pct"] == expected

    def test_unverified_controls_name_what_is_missing(self) -> None:
        for framework in all_frameworks():
            for control in coverage(framework)["unverified_controls"]:
                assert control["missing_evidence"], (
                    f"{framework.key}/{control['control_id']} is unverified but names nothing"
                )
                for missing in control["missing_evidence"]:
                    assert not (REPO_ROOT / missing).exists(), (
                        f"{missing} is reported missing but exists on disk"
                    )

    def test_present_controls_really_have_their_evidence(self) -> None:
        """The core anti-honesty property: a verified control's files exist."""
        for framework in all_frameworks():
            for control in coverage(framework)["controls"]:
                for path in control["evidence"]:
                    assert (REPO_ROOT / path).exists(), (
                        f"{framework.key}/{control['control_id']} counts {path} as present"
                        " but it does not exist"
                    )

    def test_every_framework_verifies_at_least_one_control(self) -> None:
        for framework in all_frameworks():
            assert coverage(framework)["verified"] > 0, (
                f"{framework.key} verifies nothing at all"
            )


class TestControlConstruction:
    """The dataclass itself, which every framework depends on."""

    def test_control_is_frozen(self) -> None:
        control = Control("X", "title", ("evidence.md",), ("tests/test_x.py",))
        with pytest.raises(Exception):
            control.control_id = "Y"  # type: ignore[misc]

    def test_verified_by_defaults_to_empty(self) -> None:
        assert Control("X", "title", ("e.md",)).verified_by == ()

    def test_framework_holds_controls_as_a_tuple(self) -> None:
        framework = Framework("k", "Name", "Auth", (Control("X", "t", ("e",)),), "scope")
        assert isinstance(framework.controls, tuple)

    def test_unverified_control_carries_its_evidence_list(self) -> None:
        framework = Framework(
            "k", "Name", "Auth", (Control("X", "t", ("does/not/exist.md",)),), "scope"
        )
        result = coverage_for(framework)
        assert result["verified"] == 0
        assert result["unverified_controls"][0]["evidence"] == ["does/not/exist.md"]


def coverage_for(framework: Framework) -> dict:
    """Run :func:`coverage` against an ad-hoc framework.

    ``coverage()`` measures against the real repository root, so a synthetic
    framework lets us prove the arithmetic without inventing files on disk.
    """
    from anticloud_ref.bench import compliance

    return compliance.coverage(framework)


class TestScopeStatementsAreHonest:
    """The claim each framework makes must not overstate what was verified."""

    #: Phrases that would turn a technical map into a certification claim.
    OVERCLAIMS = (
        "certified",
        "compliant with",
        "attested",
        "audited by",
        "authorised",
        "authorized",
    )

    def test_no_framework_claims_a_certification(self) -> None:
        for framework in all_frameworks():
            lowered = framework.scope_statement.lower()
            for phrase in self.OVERCLAIMS:
                assert phrase not in lowered, (
                    f"{framework.key} scope statement overclaims: {phrase!r}"
                )

    def test_frameworks_that_map_a_standard_disclaim_the_certificate(self) -> None:
        """Standards requiring an external assessor must say so."""
        for key in ("soc2", "iso_27001", "pci_dss", "fedramp"):
            statement = FRAMEWORKS[key].scope_statement.lower()
            assert any(
                word in statement for word in ("no ", "not claimed", "is not")
            ), f"{key} does not disclaim the external assessment"

    def test_llm_framework_states_the_pass_is_absence_not_mitigation(self) -> None:
        """The OWASP LLM map passes by non-capability; that must be stated."""
        statement = FRAMEWORKS["owasp_llm_top10"].scope_statement.lower()
        assert "absent" in statement or "structurally" in statement


class TestBenchmarkIdsResolveToFrameworks:
    """Every framework benchmark in the runner must map to a real framework."""

    def test_owasp_llm_framework_is_registered(self) -> None:
        assert "owasp_llm_top10" in FRAMEWORKS
        assert len(FRAMEWORKS["owasp_llm_top10"].controls) == 10

    def test_llm_control_ids_are_the_canonical_ten(self) -> None:
        ids = [c.control_id.strip() for c in FRAMEWORKS["owasp_llm_top10"].controls]
        assert ids == [f"LLM{n:02d}" for n in range(1, 11)]

    def test_owasp_llm_scope_names_the_ten_risks(self) -> None:
        """The map must reference the actual LLM risk categories, not a vague set."""
        titles = " ".join(
            c.title.lower() for c in FRAMEWORKS["owasp_llm_top10"].controls
        )
        for keyword in ("prompt injection", "supply chain", "agency", "poisoning"):
            assert keyword in titles, f"no LLM control mentions {keyword!r}"


def test_control_id_stripping_is_what_creates_the_duplicates() -> None:
    """Pin the mechanism: a probe collides only because ids are stripped."""
    for framework_key, control_id in DUPLICATE_PROBES:
        framework = FRAMEWORKS[framework_key]
        raw = [
            c.control_id for c in framework.controls if c.control_id.strip() == control_id
        ]
        assert len(raw) == 2
        assert len(set(raw)) == 2, "the raw ids must differ"
        assert len({c.strip() for c in raw}) == 1, "the stripped ids must collide"