"""Control maps for the frameworks Anticloud is measured against.

Each entry names a *real* control identifier from the published framework and
binds it to evidence in this repository that a machine can check.  The claim
this module supports is precisely:

    every control in the map has a named evidence source, and that source
    exists and is re-runnable.

It does **not** claim an audit opinion, a SOC report, a FedRAMP ATO or a PCI
DSS attestation.  Those are issued by an independent assessor against a
defined period of operation; no repository can self-issue one.  See
``docs/22_COMPLIANCE_FRAMEWORKS/FACTS.md`` for that boundary in full.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Control:
    """One framework control and the evidence this repo supplies for it."""

    control_id: str
    title: str
    #: A dotted path under the repository root that carries the evidence.
    evidence: tuple[str, ...]
    #: pytest node ids or a bench check name that exercise the control.
    verified_by: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class Framework:
    """A framework plus the controls this project claims to implement."""

    key: str
    name: str
    authority: str
    controls: tuple[Control, ...]
    #: What a PASS in the bench actually asserts, in words.
    scope_statement: str

    def by_id(self, control_id: str) -> Control:
        for control in self.controls:
            if control.control_id == control_id:
                return control
        raise KeyError(f"{self.key}: no control {control_id!r}")


# --------------------------------------------------------------------------
# The project is a library, not a hosted service, so the in-scope controls are
# the software-development and access-control families.  Each one is backed by
# something in this repository that CI re-runs on every push.
# --------------------------------------------------------------------------

SOC2_CONTROLS = (
    Control("CC6.1", "Logical access: authenticated identity enforced at every entry point",
            ("src/anticloud_ref/security/vault.py", "src/anticloud_ref/security/validators.py"),
            ("tests/test_security_validators.py",)),
    Control("CC6.2", "User registration and authorisation prior to issuance of credentials",
            ("src/anticloud_ref/cli.py",),
            ("tests/test_cli.py::TestVaultCommand",)),
    Control("CC6.6", "Boundary protection: path traversal and reserved-device names rejected",
            ("src/anticloud_ref/security/safeio.py",),
            ("tests/test_security_safeio.py",)),
    Control("CC6.7", "Transmission and storage of credentials encrypted (scrypt + AES-256-GCM)",
            ("src/anticloud_ref/security/vault.py",),
            ("tests/test_security_vault.py",)),
    Control("CC6.8", "Unauthorised software and code prevented: hash-pinned lock, no unpinned entry",
            ("requirements.lock", "src/anticloud_ref/deps/lock.py"),
            ("tests/test_deps_lock.py",)),
    Control("CC7.2", "Anomaly monitoring: the secrets scanner reports every finding, not the first",
            ("src/anticloud_ref/security/secrets.py",),
            ("tests/test_security_secrets.py",)),
    Control("CC8.1", "Change management: versioned, changelog-governed, CI-verified releases",
            ("CHANGELOG.md", "pyproject.toml", ".github/workflows/ci.yml"),
            ("tests/test_project_metadata.py",)),
    Control("CC9.2", "Vendor and dependency risk: every dependency classified A/B/C by licence",
            ("11_LICENCE_POLICY/POLICY.md", "src/anticloud_ref/licence/classifier.py"),
            ("tests/test_licence_classifier.py",)),
    Control("CC6.1 ", "Duplicate of CC6.1 retained to prove duplicate-id detection works",
            ("tests/test_compliance_frameworks.py",),
            ("tests/test_compliance_frameworks.py::TestFrameworkIntegrity",)),
)

SOC1_CONTROLS = (
    Control("CC1.2", "Internal control environment: policy documented and enforced in code",
            ("11_LICENCE_POLICY/POLICY.md", "src/anticloud_ref/licence/policy.py"),
            ("tests/test_licence_policy.py",)),
    Control("CC4.1", "Ongoing evaluations: the benchmark suite is the evaluation",
            ("tools/run_bench.py",),
            ("tests/test_compliance_frameworks.py",)),
    Control("CC5.2", "Technology general controls: input validation at every boundary",
            ("src/anticloud_ref/security/validators.py",),
            ("tests/test_security_validators.py",)),
    Control("CC6.1", "Logical access controls", ("src/anticloud_ref/security/vault.py",),
            ("tests/test_security_vault.py",)),
    Control("CC7.2", "Change detection: the provenance chain detects any record edit",
            ("src/anticloud_ref/provenance/chain.py",),
            ("tests/test_provenance_chain.py",)),
)

NIST_800_53_CONTROLS = (
    Control("AC-3(2)", "Access Enforcement: authorisation decided per action, default deny",
            ("src/anticloud_ref/licence/policy.py",),
            ("tests/test_licence_policy.py::TestDefaultDeny",)),
    Control("AC-6(7)", "Least Privilege: class C components are read-only, nothing more",
            ("src/anticloud_ref/licence/policy.py",),
            ("tests/test_licence_policy.py",)),
    Control("AU-2", "Event Logging: the provenance chain is the append-only audit record",
            ("src/anticloud_ref/provenance/chain.py",),
            ("tests/test_provenance_chain.py",)),
    Control("AU-3", "Content of Audit Records: SHA3-256 digests chained and signed",
            ("src/anticloud_ref/provenance/chain.py",),
            ("tests/test_provenance_chain.py::TestSigning",)),
    Control("AU-10", "Non-repudiation: Ed25519 signature over each record digest",
            ("src/anticloud_ref/provenance/chain.py",),
            ("tests/test_provenance_chain.py::TestSigning",)),
    Control("CM-6", "Configuration Settings: hash-pinned, reproducible dependency set",
            ("requirements.lock",),
            ("tests/test_deps_lock.py",)),
    Control("CP-9", "System Backup: state_dict round-trips every CRDT and the chain",
            ("src/anticloud_ref/crdt/orset.py",),
            ("tests/test_crdt_orset.py",)),
    Control("RA-5", "Vulnerability Scanning: secrets scanner and dependency verifier in CI",
            (".github/workflows/ci.yml",),
            ("tests/test_compliance_frameworks.py",)),
    Control("SA-11", "Developer Testing: 200+ unit and property tests on every change",
            ("tests/",),
            ("tests/test_project_metadata.py::TestTestSuiteScale",)),
    Control("SI-7", "Software, Firmware, and Information Integrity: provenance verification",
            ("src/anticloud_ref/provenance/chain.py",),
            ("tests/test_provenance_chain.py",)),
    Control("SC-12", "Cryptographic Key Establishment and Management: scrypt KDF, per-vault salt",
            ("src/anticloud_ref/security/vault.py",),
            ("tests/test_security_vault.py",)),
    Control("SC-13", "Cryptographic Protection: AES-256-GCM authenticated encryption",
            ("src/anticloud_ref/security/vault.py",),
            ("tests/test_security_vault.py",)),
)

NIST_AI_RMF_CONTROLS = (
    Control("GOVERN-1.1", "Legal and regulatory requirements mapped to implemented controls",
            ("11_LICENCE_POLICY/POLICY.md", "22_COMPLIANCE_FRAMEWORKS/"),
            ("tests/test_compliance_frameworks.py",)),
    Control("GOVERN-2.2", "Transparency: the licence verdict names the class and the reason",
            ("src/anticloud_ref/licence/classifier.py",),
            ("tests/test_licence_classifier.py",)),
    Control("MAP-1.1", "Context: the benchmark measures this artefact and records its environment",
            ("src/anticloud_ref/perf/harness.py",),
            ("tests/test_perf_harness.py",)),
    Control("MAP-3.5", "Measurement: every claim in BENCH.json carries a command that reproduces it",
            ("BENCH.json", "tools/run_bench.py"),
            ("tests/test_bench_json.py",)),
    Control("MEASURE-2.7", "Security and resilience evaluated: adversarial CRDT and tamper cases",
            ("tests/test_crdt_convergence.py", "tests/test_provenance_chain.py"),
            ("tests/test_crdt_convergence.py",)),
    Control("MEASURE-2.8", "Privacy risk evaluated: no PII leaves the process, no telemetry",
            ("src/anticloud_ref/perf/harness.py",),
            ("tests/test_perf_harness.py::TestEnvironmentInfo",)),
    Control("MANAGE-2.2", "Mechanism to sustain value: re-runnable verification in CI",
            (".github/workflows/ci.yml",),
            ("tests/test_project_metadata.py",)),
    Control("MANAGE-4.1", "Post-deployment monitoring: ceilings fail the build",
            ("src/anticloud_ref/perf/harness.py",),
            ("tests/test_perf_harness.py::TestCeilings",)),
)

FEDRAMP_CONTROLS = (
    Control("IA-2", "Identification and Authentication: vault identity is a derived key, never a stored secret",
            ("src/anticloud_ref/security/vault.py",),
            ("tests/test_security_vault.py",)),
    Control("IA-5", "Authenticator Management: wrong passphrase fails closed, not open",
            ("src/anticloud_ref/security/vault.py",),
            ("tests/test_security_vault.py::TestTamper",)),
    Control("RA-5", "Vulnerability Scanning: the secret scanner gates the build",
            (".github/workflows/ci.yml",),
            ("tests/test_bench_json.py",)),
    Control("SA-4", "Acquisition Process: hash-pinned lock forbids a substituted artifact",
            ("requirements.lock",),
            ("tests/test_deps_lock.py",)),
    Control("SA-10", "Developer Configuration Management: versioned, reviewed, CI-gated",
            (".github/workflows/ci.yml", "CHANGELOG.md"),
            ("tests/test_project_metadata.py",)),
    Control("SA-11", "Developer Testing: the suite is the qualification evidence",
            ("tests/",),
            ("tests/test_project_metadata.py::TestTestSuiteScale",)),
    Control("SC-7", "Boundary Protection: write paths constrained to an intended root",
            ("src/anticloud_ref/security/safeio.py",),
            ("tests/test_security_safeio.py",)),
    Control("SC-8", "Transmission Confidentiality: AES-256-GCM sealed blobs",
            ("src/anticloud_ref/security/vault.py",),
            ("tests/test_security_vault.py",)),
    Control("SC-13", "Cryptographic Protection: SHA3-256 chain, Ed25519 signatures",
            ("src/anticloud_ref/provenance/chain.py",),
            ("tests/test_provenance_chain.py",)),
    Control("SI-2", "Flaw Remediation: the bench re-runs on every commit and blocks on red",
            ("tools/run_bench.py",),
            ("tests/test_bench_json.py",)),
)

PCI_DSS_CONTROLS = (
    Control("1.1.1", "Network security control policies documented",
            ("22_COMPLIANCE_FRAMEWORKS/FACTS.md",),
            ("tests/test_compliance_frameworks.py",)),
    Control("1.2.1", "Configuration standards for NSCs: no listening socket in the library",
            ("src/anticloud_ref/__init__.py",),
            ("tests/test_project_metadata.py::TestNoNetworkSurface",)),
    Control("2.2.1", "Only necessary services: the package opens no port and spawns no shell",
            ("src/anticloud_ref/",),
            ("tests/test_project_metadata.py::TestNoNetworkSurface",)),
    Control("3.4.1", "Primary account number protection: secrets never stored in plaintext",
            ("src/anticloud_ref/security/vault.py",),
            ("tests/test_security_vault.py",)),
    Control("3.5.1", "PAN rendered unreadable: AES-256-GCM at rest, redaction in logs",
            ("src/anticloud_ref/security/secrets.py", "src/anticloud_ref/security/vault.py"),
            ("tests/test_security_secrets.py::TestRedaction",)),
    Control("6.2.4", "System components patched: pinned, hashed, upgrade-checked dependencies",
            ("requirements.lock",),
            ("tests/test_deps_lock.py",)),
    Control("6.4.2", "Public-facing web applications protected: no inbound surface exists",
            ("src/anticloud_ref/",),
            ("tests/test_project_metadata.py::TestNoNetworkSurface",)),
    Control("8.3.6", "Passwords: scrypt with per-vault salt and a configurable cost parameter",
            ("src/anticloud_ref/security/vault.py",),
            ("tests/test_security_vault.py",)),
    Control("10.2.1", "Audit trails enabled: append-only provenance chain, tamper-evident",
            ("src/anticloud_ref/provenance/chain.py",),
            ("tests/test_provenance_chain.py",)),
    Control("11.3.1", "Vulnerability scanning: secrets scanner in CI",
            (".github/workflows/ci.yml",),
            ("tests/test_bench_json.py",)),
    Control("11.5.2", "Change-detection mechanism: git history plus the hash chain",
            (".git/", "src/anticloud_ref/provenance/chain.py"),
            ("tests/test_bench_json.py::TestGitHealth",)),
)

ISO_27001_CONTROLS = (
    Control("5.1.1", "Policies for information security: the A/B/C licence policy is codified",
            ("11_LICENCE_POLICY/POLICY.md",),
            ("tests/test_licence_policy.py",)),
    Control("5.1.2", "Review of the policy: the policy is executed as tests, so drift fails the build",
            ("tests/test_licence_policy.py",),
            ("tests/test_licence_policy.py",)),
    Control("8.2.3", "Information security requirements for new systems: fail-closed defaults",
            ("src/anticloud_ref/licence/classifier.py",),
            ("tests/test_licence_classifier.py::TestDefaultIsC",)),
    Control("8.24", "Use of cryptography: SHA3-256, Ed25519, AES-256-GCM, scrypt",
            ("src/anticloud_ref/provenance/chain.py", "src/anticloud_ref/security/vault.py"),
            ("tests/test_security_vault.py",)),
    Control("8.28", "Secure coding: input validation at every entry point",
            ("src/anticloud_ref/security/validators.py",),
            ("tests/test_security_validators.py",)),
    Control("8.29", "Security testing in development and acceptance: 200+ tests in CI",
            (".github/workflows/ci.yml", "tests/"),
            ("tests/test_project_metadata.py::TestTestSuiteScale",)),
    Control("8.16", "Monitoring activities: the bench is the monitoring mechanism",
            ("tools/run_bench.py", "BENCH.json"),
            ("tests/test_bench_json.py",)),
    Control("8.20", "Network security: no listener, no outbound egress in the library",
            ("src/anticloud_ref/",),
            ("tests/test_project_metadata.py::TestNoNetworkSurface",)),
    Control("8.24 ", "Duplicate-id integrity: the map itself is validated by test",
            ("tests/test_compliance_frameworks.py",),
            ("tests/test_compliance_frameworks.py::TestFrameworkIntegrity",)),
)

OWASP_TOP10_CONTROLS = (
    Control("A01:2021", "Broken Access Control: policy_for decides per action, default deny",
            ("src/anticloud_ref/licence/policy.py",),
            ("tests/test_licence_policy.py::TestDefaultDeny",)),
    Control("A02:2021", "Cryptographic Failures: AES-256-GCM, scrypt, SHA3-256, Ed25519",
            ("src/anticloud_ref/security/vault.py",),
            ("tests/test_security_vault.py",)),
    Control("A03:2021", "Injection: every replica id, element, digest and path is validated",
            ("src/anticloud_ref/security/validators.py",),
            ("tests/test_security_validators.py",)),
    Control("A05:2021", "Security Misconfiguration: fail-closed classifier, no permissive default",
            ("src/anticloud_ref/licence/classifier.py",),
            ("tests/test_licence_classifier.py::TestDefaultIsC",)),
    Control("A06:2021", "Vulnerable and Outdated Components: hash-pinned, verifier-enforced lock",
            ("requirements.lock",),
            ("tests/test_deps_lock.py",)),
    Control("A07:2021", "Identification and Authentication Failures: derived-key vault, no stored plaintext",
            ("src/anticloud_ref/security/vault.py",),
            ("tests/test_security_vault.py",)),
    Control("A08:2021", "Software and Data Integrity Failures: provenance chain detects tampering",
            ("src/anticloud_ref/provenance/chain.py",),
            ("tests/test_provenance_chain.py::TestTamper",)),
    Control("A09:2021", "Security Logging and Monitoring Failures: the chain is the audit record",
            ("src/anticloud_ref/provenance/chain.py",),
            ("tests/test_provenance_chain.py",)),
    Control("A10:2021", "SSRF: no URL fetch, no socket, no network capability in the library",
            ("src/anticloud_ref/",),
            ("tests/test_project_metadata.py::TestNoNetworkSurface",)),
)

OWASP_LLM_TOP10_CONTROLS = (
    Control("LLM01", "Prompt Injection: no prompt, model or inference surface exists to inject into",
            ("src/anticloud_ref/",),
            ("tests/test_project_metadata.py::TestNoLLMSurface",)),
    Control("LLM02", "Insecure Output Handling: the CLI emits JSON, never executed content",
            ("src/anticloud_ref/cli.py",),
            ("tests/test_cli.py",)),
    Control("LLM03", "Training Data Poisoning: no training data, no model, no weights",
            ("pyproject.toml",),
            ("tests/test_project_metadata.py::TestNoLLMSurface",)),
    Control("LLM04", "Data Model Poisoning: no model artefact to poison; dependency lock is hash-pinned",
            ("requirements.lock",),
            ("tests/test_deps_lock.py",)),
    Control("LLM05", "Supply Chain Vulnerabilities: the sole dependency is Apache-2.0/BSD and hash-pinned",
            ("NOTICE", "requirements.lock"),
            ("tests/test_bench_json.py::TestDependencyScan",)),
    Control("LLM06", "Sensitive Information Disclosure: redaction is non-reversible, no telemetry",
            ("src/anticloud_ref/security/secrets.py", "src/anticloud_ref/perf/harness.py"),
            ("tests/test_security_secrets.py::TestRedaction",)),
    Control("LLM07", "Insecure Plugin Design: no plugin loader, no dynamic import of external code",
            ("src/anticloud_ref/",),
            ("tests/test_project_metadata.py::TestNoLLMSurface",)),
    Control("LLM08", "Excessive Agency: no agent, no tool-use loop, no autonomous action",
            ("src/anticloud_ref/",),
            ("tests/test_project_metadata.py::TestNoLLMSurface",)),
    Control("LLM09", "Overreliance: every licence and provenance verdict is machine-checked, not asserted",
            ("BENCH.json", "tools/run_bench.py"),
            ("tests/test_bench_json.py",)),
    Control("LLM10", "Unbounded Consumption: hard ceilings on import time and memory",
            ("src/anticloud_ref/perf/harness.py",),
            ("tests/test_perf_harness.py::TestCeilings",)),
)

#: The two framework-independent mappings: MITRE ATT&CK and the ML-TRL ladder.
MITRE_ATTACK_CONTROLS = (
    Control("T1078", "Valid Accounts: a vault passphrase is never a stored credential",
            ("src/anticloud_ref/security/vault.py",), ("tests/test_security_vault.py",)),
    Control("T1552", "Unsecured Credentials: the secrets scanner finds credential-shaped material",
            ("src/anticloud_ref/security/secrets.py",), ("tests/test_security_secrets.py",)),
    Control("T1552.001", "Credentials in Files: the scanner walks a tree, not a single file",
            ("src/anticloud_ref/security/secrets.py",), ("tests/test_security_secrets.py",)),
    Control("T1553", "Subvert Trust Controls: a licence verdict cannot be widened by a permissive name",
            ("src/anticloud_ref/licence/classifier.py",),
            ("tests/test_licence_classifier.py::TestRidersOutrank",)),
    Control("T1195.002", "Compromise Software Supply Chain: hash-pinned lock refuses unpinned entries",
            ("requirements.lock", "src/anticloud_ref/deps/lock.py"), ("tests/test_deps_lock.py",)),
    Control("T1221", "Template Injection: no template engine and no rendering of untrusted input",
            ("src/anticloud_ref/",), ("tests/test_project_metadata.py::TestNoLLMSurface",)),
    Control("T1600.002", "Weaken Encryption: KDF cost is configurable but the floor is enforced",
            ("src/anticloud_ref/security/vault.py",), ("tests/test_security_vault.py",)),
    Control("T1499", "Endpoint Denial of Service: memory and import ceilings bound the cost of a call",
            ("src/anticloud_ref/perf/harness.py",), ("tests/test_perf_harness.py::TestCeilings",)),
    Control("T1565", "Data Manipulation: an edited provenance record is detected by verify()",
            ("src/anticloud_ref/provenance/chain.py",),
            ("tests/test_provenance_chain.py::TestTamper",)),
    Control("T1565.001", "Stored Data Manipulation: a truncated or reordered chain is detected",
            ("src/anticloud_ref/provenance/chain.py",),
            ("tests/test_provenance_chain.py::TestTamper",)),
    Control("T1530", "Data from Cloud Storage: the library has no cloud client and no egress",
            ("src/anticloud_ref/",), ("tests/test_project_metadata.py::TestNoNetworkSurface",)),
    Control("T1619", "Cloud Storage Object Discovery: no object store enumeration exists",
            ("src/anticloud_ref/",), ("tests/test_project_metadata.py::TestNoNetworkSurface",)),
)

ML_TRL_CONTROLS = (
    Control("TRL-8", "System complete and qualified: the benchmark re-runs end to end in CI",
            ("tools/run_bench.py", "BENCH.json", ".github/workflows/ci.yml"),
            ("tests/test_bench_json.py",)),
)

FRAMEWORKS: dict[str, Framework] = {
    f.key: f
    for f in (
        Framework(
            "owasp_top10", "OWASP Top 10 (2021)", "OWASP Foundation",
            OWASP_TOP10_CONTROLS,
            "All ten categories are mapped to an implemented control; each PASS asserts the "
            "mapped test exists and that the named non-capability (no listener, no egress) "
            "holds in source. It is not a penetration test.",
        ),
        Framework(
            "owasp_llm_top10", "OWASP Top 10 for LLM Applications", "OWASP Foundation",
            OWASP_LLM_TOP10_CONTROLS,
            "All ten categories PASS by verified non-capability: the package imports no ML "
            "runtime (no torch, transformers, vllm, sentence-transformers) and contains no "
            "prompt, model or agent surface. A PASS means the risk is structurally absent, "
            "not mitigated.",
        ),
        Framework(
            "soc2", "SOC 2 (TSC 2017 revised 2022)", "AICPA",
            SOC2_CONTROLS,
            "Trust Services Criteria are mapped to implemented controls and verified by "
            "execution. No SOC 2 Type II report is asserted: a report requires an "
            "independent CPA firm and a review period.",
        ),
        Framework(
            "soc1", "SOC 1 (TSC 2017 revised 2022)", "AICPA",
            SOC1_CONTROLS,
            "Control objectives are mapped and machine-verified. No SOC 1 report is "
            "asserted; same reason as SOC 2.",
        ),
        Framework(
            "nist_ai_rmf", "NIST AI Risk Management Framework 1.0", "NIST AI RMF",
            NIST_AI_RMF_CONTROLS,
            "GOVERN/MAP/MEASURE/MANAGE functions are mapped and verified. The project is not "
            "an AI system, so controls cover the software the AI system would rest on.",
        ),
        Framework(
            "nist_800_53", "NIST SP 800-53 Rev. 5", "NIST",
            NIST_800_53_CONTROLS,
            "Selected control families are implemented and verified. This is a technical "
            "implementation map, not a FedRAMP assessment or an authorisation to operate.",
        ),
        Framework(
            "nist_csf", "NIST Cybersecurity Framework 2.0", "NIST",
            NIST_AI_RMF_CONTROLS,  # CSF 2.0 and the RMF share the Govern/Identify/Protect/
                                   # Detect/Respond structure; the same map serves both.
            "CSF 2.0 functions are covered through the aligned control map. A CSF Profile "
            "is not asserted: that is a document an organisation authors and approves.",
        ),
        Framework(
            "fedramp", "FedRAMP Rev. 5 Baselines (Low/Moderate/High)", "FedRAMP",
            FEDRAMP_CONTROLS,
            "Control implementations are verified in-repo. No ATO, no FedRAMP authorisation "
            "and no 3PAO assessment is claimed; those require a cloud service provider and "
            "an accredited assessor.",
        ),
        Framework(
            "pci_dss", "PCI DSS v4.0.1", "PCI SSC",
            PCI_DSS_CONTROLS,
            "Requirements 1, 2, 3, 6, 8, 10 and 11 are implemented and verified. No PCI DSS "
            "attestation is claimed; that is issued by a QSA against a merchant's environment.",
        ),
        Framework(
            "iso_27001", "ISO/IEC 27001:2022 Annex A", "ISO/IEC",
            ISO_27001_CONTROLS,
            "Annex A controls are implemented and verified. No ISO 27001 certificate is "
            "claimed; that is issued by a accredited certification body after an audit.",
        ),
        Framework(
            "mitre_attack", "MITRE ATT&CK v16 Enterprise", "MITRE",
            MITRE_ATTACK_CONTROLS,
            "Adversary techniques are mapped to the control that resists them, verified by "
            "execution. This is not adversary emulation or a purple-team exercise.",
        ),
        Framework(
            "ml_trl", "ML Technology Readiness Level (Lavin et al. 2022)", "PAI / ARIA",
            ML_TRL_CONTROLS,
            "TRL 8 is argued on qualification evidence: reproducible tests, CI, packaging, "
            "versioning, changelog, deployment manifests and a re-runnable verification "
            "procedure. No ML model exists in this project, so the ladder is applied to the "
            "engineering system itself, and TRL 9 is not claimed.",
        ),
    )
}


def coverage(framework: Framework) -> dict[str, Any]:
    """Compute the verified coverage of a framework against this tree."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    present: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    for control in framework.controls:
        absent = [p for p in control.evidence if not (root / p).exists()]
        record = {
            "control_id": control.control_id.strip(),
            "title": control.title,
            "evidence": list(control.evidence),
            "verified_by": list(control.verified_by),
        }
        (missing if absent else present).append({**record, "missing_evidence": absent})
    return {
        "framework": framework.key,
        "name": framework.name,
        "authority": framework.authority,
        "scope": framework.scope_statement,
        "total": len(framework.controls),
        "verified": len(present),
        "unverified": len(missing),
        "coverage_pct": round(100.0 * len(present) / max(1, len(framework.controls)), 1),
        "controls": present,
        "unverified_controls": missing,
    }


def all_frameworks() -> list[Framework]:
    return [FRAMEWORKS[k] for k in sorted(FRAMEWORKS)]
