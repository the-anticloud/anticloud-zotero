# FACTS

**This file contains only statements that were executed and observed.**

Every number below was produced by running a command in this repository at the
recorded revision. Each entry carries the command that reproduces it. If a fact
stops being true, the command stops producing the stated value — that is the
whole point of this file.

- **Repository:** `anticloud-ref` v1.0.0
- **License:** Apache-2.0 (`LICENSE`, `NOTICE`)
- **Revision for these facts:** `a80176f` on `main`

---

## 1. What this project is

A pure-Python library of conflict-free replicated data types (CRDTs) with a
hash-linked provenance log, plus a benchmark suite that scores its own
engineering claims.

It is **not** an AI or machine-learning system. It imports no ML runtime and
contains no model, prompt, inference or agent surface. This is a structural
absence, verified by the source scan in `16_ml_trl` and the framework statement
in `owasp_llm_top10`.

## 2. Size

Reproduce:

```bash
python -c "
import sys; sys.path.insert(0,'src')
from pathlib import Path
from anticloud_ref.bench.runner import _count_loc
paths=[p for p in Path('.').rglob('*.py') if '.git' not in p.parts and '_build' not in p.parts]
print(_count_loc(paths))"
```

| Metric | Value |
|---|---|
| Python files | 38 |
| Total lines | 8,384 |
| Code lines | 6,887 |
| Comment lines | 219 |
| Blank lines | 1,278 |

Ceilings enforced by `01_loc_files`: `FILE_CEILING = 120` files, `LOC_CEILING =
20_000` lines. Both are asserted independently in
`tests/test_project_metadata.py`.

## 3. Dependencies

`requirements.lock` pins **6 direct requirements**, each hash-pinned:

| Package | Version | Licence class |
|---|---|---|
| `cffi` | 2.1.1 | A (MIT) |
| `coverage` | 7.16.2 | A (Apache-2.0) |
| `cryptography` | 50.0.2 | A (Apache-2.0 / BSD) |
| `pycparser` | 3.0 | A (BSD-3-Clause) |
| `pytest` | 9.1.1 | A (MIT) |
| `pytest-cov` | 7.1.0 | A (MIT) |

`03_dependency_scan` fails the build if any requirement is not hash-pinned, or
if any licence falls outside the permitted set for this tree
(`Apache-2.0, MIT, BSD-3-Clause, BSD-2-Clause, ISC`). No class B or C
dependency is present.

`cryptography` is the only non-test runtime requirement, and it is used solely
for Ed25519 signing in the provenance chain.

## 4. Capabilities the library does not have

Each of these is asserted by a named test, not by prose:

| Absent capability | Enforced by |
|---|---|
| Network I/O (`socket`, `http`, `urllib`, `requests`, …) | `FORBIDDEN_MODULES` in `runner.py`; OWASP A10 control |
| ML runtimes (`torch`, `transformers`, `vllm`, …) | `FORBIDDEN_IMPORTS`; `16_ml_trl` |
| Prompt / model / agent surface | `TestNoLLMSurface`; the LLM01/LLM07/LLM08 controls |
| Shell execution | source scan; the library spawns no subprocess |
| Deserialisation of untrusted input | validated constructors throughout |

## 5. Cryptography actually used

| Primitive | Use | Location |
|---|---|---|
| SHA3-256 | provenance record digests, artefact hashes | `provenance/chain.py` |
| Ed25519 | optional record signing | `provenance/chain.py` |
| scrypt | vault passphrase derivation | `security/vault.py` |
| AES-256-GCM | vault payload encryption | `security/vault.py` |

A passphrase is never stored. `load_signing_key` re-derives the public half
from the private key rather than trusting a neighbouring `.pub.pem`, so a
swapped public key file cannot make a verifier accept an attacker's signature.

## 6. Known limitation — provenance signature stripping

**This is a real gap, recorded rather than hidden.**

`ProvenanceChain.verify_signatures` selects its work list with
`[r for r in self._records if r.signature]`. A record whose signature has been
*removed* is therefore skipped rather than rejected, so an attacker who can
rewrite the file can downgrade a fully-signed chain to a partially-signed one
and `verify()` still returns `valid=True`.

What **is** detected: edits to a signed record's contents, a broken parent
link, reordered or deleted records, and a signature made by the wrong key. Only
signature *removal* passes.

Asserted as-is in
`tests/test_provenance_chain.py::TestSigning::test_stripping_one_signature_is_NOT_detected`,
which will fail (the intended signal) if the gap is ever closed. Fixing it means
changing `verify_signatures` — a change to the library's security semantics,
which is a maintainer decision, not a test-suite decision.

## 7. Known limitation — SBOM scope

`sbom.cdx.json` is generated from **live `importlib.metadata` plus
`requirements.lock`**, not from a hand-written list. On a machine with a large
Python environment, that environment is enumerated into the BOM with
`scope: "optional"`.

Observed consequence: the current SBOM has **107 components**, and the 6 that
genuinely belong to this project are identifiable only because they carry a
`sha256` (`cffi`, `coverage`, `cryptography`, `pycparser`, `pytest`,
`pytest-cov`). **Every one of the 107 is tagged `scope: "optional"`** — no
component carries `scope: "required"` — so scope alone does not separate our
dependencies from the host environment. The other 101 describe whatever
happened to be installed on the machine that generated the file, and include
unrelated heavyweights such as `torch`, `transformers` and `numpy`.

**This does not mean `anticloud-ref` depends on `torch`.** It does not: those
packages appear nowhere in `requirements.lock` or in the source. But a reader
of the raw BOM could be misled, so the caveat belongs here.

Reproduce:

```bash
python -c "
import json; d=json.load(open('sbom.cdx.json'))
scopes={c.get('scope') for c in d['components']}
print('total', len(d['components']), 'scopes present', scopes)
print('hash-bearing (i.e. ours):',
      [c['name'] for c in d['components'] if c.get('hashes')])
print('forbidden ML imports present:',
      [c['name'] for c in d['components']
       if c['name'] in ('torch','transformers','vllm')])"
```

The fix is to tag the `requirements.lock` components as `scope: "required"` and
everything else as excluded, or to generate the BOM in a clean environment. It
is not a scoring error: `04_sbom_cyclonedx` validates format, licence
presence, purl validity and the hash count, and all of those pass — which is
itself a small demonstration that a check can be correctly implemented and
still fail to catch this.

## 8. Test suite

```
$ python -m pytest -q
```

Green at the recorded revision. The suite is the primary evidence for the
control maps in `22_COMPLIANCE_FRAMEWORKS/`, which is why every framework
control names a pytest node in its `verified_by` field.

## 9. What is *not* claimed

This repository makes **no** claim of certification, attestation or external
audit. Specifically:

- no SOC 2 Type II report — that requires an independent CPA firm and a review period;
- no ISO/IEC 27001 certificate — that requires an accredited certification body;
- no PCI DSS attestation — that is issued by a QSA against a merchant's environment;
- no FedRAMP authorisation and no 3PAO assessment;
- no penetration test.

Each framework's `scope_statement` in `src/anticloud_ref/bench/compliance.py`
states its own limit, and `tests/test_compliance_frameworks.py` asserts that
none of those statements overclaims.
