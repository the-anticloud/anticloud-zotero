# Changelog

All notable changes to this project are documented in CHANGELOG.md, the file you
are reading; the release notes are the change-management record the compliance
map cites as evidence for CC8.1 / SA-10. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-10-05

First release of the reference exemplar. Every capability below is implemented,
exercised by the test suite, and reported by `anticloud-ref bench`.

### Added

- **CRDT layer** (`anticloud_ref.crdt`) — `GCounter`, `PNCounter`, `ORSet`
  (add-wins observed-remove with tombstones and safe purge) and `LWWRegister`
  on a hybrid logical clock. `convergence_report()` runs randomised multi-replica
  workloads and asserts commutativity, idempotence and associativity of merge,
  plus add-wins on concurrent add/remove and deterministic HLC tie-breaking.
- **Provenance** (`anticloud_ref.provenance`) — append-only SHA3-256 hash chain
  with optional Ed25519 signing. `verify()` returns the index, artifact name and
  human-readable reason for the first record that breaks the chain.
- **Licence classifier** (`anticloud_ref.licence`) — A/B/C verdicts that fail
  closed: MIT/Apache-2.0/BSD/ISC/MPL-2.0 are class A, the GPL/AGPL/LGPL/SSPL
  and Commons Clause family is class B (internal only, never relicensable), and
  everything unidentified, absent or non-commercial is class C. Non-commercial
  terms and restrictive riders outrank permissive text, so a Commons Clause on
  top of an Apache grant lands in B, not A.
- **Security** (`anticloud_ref.security`) — strict input validators
  (replica ids, elements, digests, paths with Windows reserved-device-name
  rejection, ports), a tree secrets scanner with an entropy floor and
  non-reversible redaction, path-traversal-proof atomic writes, and a
  scrypt + AES-256-GCM secret vault.
- **Dependencies** (`anticloud_ref.deps`) — PEP 508-aware `requirements.lock`
  parser, hash-pinned lock generator that refuses to emit an unpinned entry, and
  a verifier that reports every problem it finds rather than the first.
- **Performance harness** (`anticloud_ref.perf`) — cold import timed in a fresh
  subprocess, cold start, `tracemalloc` memory ceiling, and eight hot-path
  microbenchmarks reported with median and p95, all emitted as one JSON
  document with the environment it was measured in.
- **CLI** (`anticloud_ref`) — `crdt`, `crdt-demo`, `provenance-build`,
  `provenance-verify`, `licence-classify`, `licence-scan`, `secrets-scan`,
  `vault`, `deps-verify`, `deps-generate`, `perf`, `validate` and `bench`.
  JSON on stdout, human summary on stderr, and exit code 1 reserved for a
  failed check so CI can distinguish a bad artefact from a bad command.

### Fixed during development

- `ProvenanceChain.record()` computed each record's digest but never passed it to
  `ProvenanceRecord`, so every chain raised `TypeError` on first append.
- `SignKeyPair` decoded PEM by base64-ing the body, which yields PKCS8 DER
  rather than the 32 raw bytes Ed25519 requires; signing now goes through
  `serialization.load_pem_private_key`.
- `parse_lock` discarded pip's `--hash=` continuation lines, so a generated lock
  verified as having zero hashed entries.
- The requirement pattern placed `[extras]` after the version instead of after
  the name, so any requirement with extras failed to parse.
- The ORSet convergence scenario was not genuinely concurrent (the remover's
  tombstone covered the adder's tag), so it asserted add-wins without testing it.
