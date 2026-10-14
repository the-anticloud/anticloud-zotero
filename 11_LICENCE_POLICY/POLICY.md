# Licence Policy

**Status:** Active · **Applies to:** every component in `anticloud-ref` and every
dependency it vendors · **Enforced by:** `anticloud_ref.licence.policy`, asserted
by `tests/test_licence_policy.py`

## 1. Purpose

This policy exists to prevent one specific, recurring harm: **shipping someone
else's code under our licence, or redistributing it outside the organisation
when its licence forbids that.** Everything below is a consequence of that
single goal.

The policy is deliberately *executable*. The rules live in
`src/anticloud_ref/licence/policy.py` as pure functions, and
`tests/test_licence_policy.py` asserts them. A change to this document that is
not accompanied by a change to that module is not a policy change; it is a
documentation change and will not affect behaviour.

## 2. The three classes

Each dependency is assigned exactly one class. The class determines what we may
do with it. Classes are not a severity ranking; they are a statement of what the
licence *permits*.

### Permissive (MIT/Apache/BSD/ISC/MPL/Unlicense) — permissive

Licences: Apache-2.0, MIT, BSD-2-Clause, BSD-3-Clause, ISC.

> May be vendored, relicensed, and pushed as an Anticloud artefact.

**Permitted:** `vendor`, `relicense`, `push_as_ours`, `redistribute`, plus
everything a class B component may do (`use_internal`, `modify`, `audit`,
`vendor_privately`).

### Copyleft (GPL/LGPL/AGPL) — copyleft or source-available

Licences: GPL-2.0/3.0, AGPL-3.0, LGPL, MPL-2.0, SSPL, and similar.

> Internal use and modification only. Relicensing and external redistribution
> are forbidden.

**Permitted:** `use_internal`, `modify`, `audit`, `vendor_privately`.

Copyleft (GPL/LGPL/AGPL) code may be deployed inside our own products, but the product itself is
then a combined work: the class B terms travel with it. **This is the decision
that requires legal sign-off, not an engineering one.**

### No license detected — reference only

Licences: proprietary licences, source-available licences with no commercial
grant, "all rights reserved", unparseable licences, and anything with a
restrictive rider (non-commercial, field-of-use, no-derivatives) attached to an
otherwise-permissive licence.

> Read the source for reference only.

**Permitted:** `read_only`, `cite`.

No license detected code is never copied into this repository. Reading it to understand an
approach is permitted; reproducing it is not.

## 3. The decision rules

`policy.py` encodes exactly four questions, and every enforcement point asks
one of them:

| Question | Function | True for |
|---|---|---|
| May we publish this as our own? | `can_push_as_ours(cls)` | A only |
| Must this stay inside the organisation? | `requires_internal_only(cls)` | B only |
| May this ship in a source release? | `redistribution_allowed(cls)` | A only |
| Is `action` permitted for `cls`? | `assert_not_forbidden(cls, action)` | raises `PermissionError` if not |

`assert_not_forbidden` **fails closed**: an action nobody has declared is
refused for every class, including A. An undeclared action is a question we have
not answered, and the correct response to an unanswered question about
redistribution is "no".

## 4. What this policy does not cover

- **Transitive dependencies.** Classification covers direct dependencies. A
  class A project can carry a class B transitive dependency; that risk is
  tracked by the SBOM (`04_sbom_cyclonedx`), not by this document.
- **Our own licence.** `LICENSE` and `NOTICE` cover this project as a
  distribution. They do not grant us anything in someone else's code.
- **Legal advice.** This document is an engineering control, not legal advice.
  Copyleft (GPL/LGPL/AGPL) decisions require sign-off from whoever holds that responsibility in
  the organisation. What this policy guarantees is that no such decision is
  made *implicitly*, by a developer, in a pull request.

## 5. Review

This policy is reviewed when any of the following occurs:

- a new licence is added to the classifier's tables;
- a dependency's class changes;
- a class B or C component is proposed for redistribution;
- the underlying standards change (this policy supports the ISO/IEC 27001:2022
  control 5.1.1 on information-security policies).

Control 5.1.2 requires that policy review is *evidenced*. Here the evidence is
mechanical: `tests/test_licence_policy.py` executes the policy, and
`tests/test_licence_classifier.py` executes the classification. A policy that
drifts from its implementation fails the build rather than surviving until
someone notices.

## 6. Enforcement summary

| Where | How |
|---|---|
| Import time | `policy_for` raises on an unknown class |
| CLI | `assert_not_forbidden` refuses a forbidden action before any file is written |
| CI | `02_licence` benchmark fails the build on an unclassified or forbidden dependency |
| Tests | `tests/test_licence_policy.py` asserts each class's action set and the fail-closed default |
