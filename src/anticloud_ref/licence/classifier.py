"""Licence identification and A/B/C classification.

Policy, stated once:

* **A** — a recognised permissive licence (MIT, Apache-2.0, BSD-2/3, ISC,
  MPL-2.0).  May be vendored, relicensed and pushed as an Anticloud artefact.
* **B** — copyleft or source-available (GPL family, AGPL, LGPL, SSPL, Commons
  Clause).  Internal use and modification only; **no relicensing**, no
  redistribution outside the organisation.
* **C** — unknown, absent, non-commercial, proprietary or unrecognised.  Read
  only.  **C is the default and is never escalated to A.**

The classifier only ever returns A on positive identification of a permissive
SPDX id or a licence file whose text carries that licence's distinctive marker.
Everything else is B or C, so a classifier bug fails closed rather than open.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

#: Files that commonly carry licence text, in the order we prefer to read them.
CANDIDATE_FILENAMES = (
    "LICENSE",
    "LICENSE.txt",
    "LICENSE.md",
    "LICENCE",
    "LICENCE.txt",
    "COPYING",
    "COPYING.txt",
    "LICENSE.rst",
)

#: Permissive licences.  Presence of any of these ids, or a marker string from
#: one of their texts, is the only route to class A.
PERMISSIVE_IDS = frozenset(
    {
        "mit",
        "apache-2.0",
        "apache 2.0",
        "bsd-2-clause",
        "bsd-3-clause",
        "bsd",
        "isc",
        "mpl-2.0",
        "0bsd",
        "python-2.0",
        "unlicense",
        "cc0-1.0",
    }
)

#: Copyleft / source-available.  Usable internally; never relicensable.
COPYLEFT_IDS = frozenset(
    {
        "gpl-2.0",
        "gpl-3.0",
        "gpl",
        "agpl-3.0",
        "agpl",
        "lgpl-2.1",
        "lgpl-3.0",
        "lgpl",
        "sspl-1.0",
        "sspl",
        "commons-clause",
        "epl-2.0",
        "cddl-1.0",
        "cc-by-sa-4.0",
    }
)

#: Licences that forbid commercial use outright.  Class C, read only.
NON_COMMERCIAL_IDS = frozenset(
    {
        "cc-by-nc-4.0",
        "cc-by-nc-sa-4.0",
        "cc-by-nc-nd-4.0",
        "non-commercial",
        "research-only",
    }
)

#: Text markers for permissive licences.  Chosen to be distinctive: a phrase
#: that appears in a copyleft text would wrongly promote a GPL file to A, so each
#: marker is something only that licence's text says.  Order matters: BSD texts
#: contain the MIT grant phrase too, so the BSD-only marker is tested first.
PERMISSIVE_MARKERS = (
    ("redistribution and use in source and binary forms", "bsd-3-clause"),
    ("permission is hereby granted, without warranty", "bsd"),
    ("permission is hereby granted, free of charge", "mit"),
    ("apache license", "apache-2.0"),
    ("mozilla public license", "mpl-2.0"),
    ("permission to use, copy, modify, and/or distribute", "isc"),
    ("this is free and unencumbered software released into the public domain", "unlicense"),
)

#: Text markers for copyleft licences.
COPYLEFT_MARKERS = (
    ("gnu general public license", "gpl"),
    ("gnu lesser general public license", "lgpl"),
    ("gnu affero general public license", "agpl"),
    ("server side public license", "sspl"),
    ("commons clause", "commons-clause"),
)

#: Text markers for non-commercial terms.  Compiled as regexes against the
#: normalised text so that licence texts which merely *mention* the words do
#: not trigger them: GPL-3 says "noncommercially" in a remedies clause, and
#: the Unlicense grants "any purpose, commercial or non-commercial" - neither
#: restricts commercial use.  A real restriction looks like CC's
#: "NonCommercial" standing alone or "non-commercial use only".
NON_COMMERCIAL_MARKERS = (
    (r"(?<!commercial or )(?<![a-z0-9])non-?commercial(?!(?:-|\s)?distribution)(?![a-z])",
     "non-commercial"),
    ("non-commercial use only", "non-commercial"),
    ("noncommercial use only", "non-commercial"),
    ("not used for commercial purposes", "non-commercial"),
    ("for non-commercial purposes", "non-commercial"),
    ("only for non-commercial", "non-commercial"),
)

#: Substring tokens that count as a *positive* statement of the named licence
#: when they appear in a metadata line such as ``License: Apache-2.0``.
_SPDX_LINE = re.compile(r"(?im)^\s*(?:license|licence)\s*[:=]\s*(?P<id>[A-Za-z0-9.\-+ ]{2,40})\s*$")

#: Regex riders that must block a permissive reading: restrictive riders on
#: top of permissive text.  Non-commercial terms reuse the grant-aware NC
#: markers, so a licence that merely mentions the words (GPL-3 "noncommercially",
#: Unlicense "commercial or non-commercial") is not blocked.
_RIDER_NON_COMMERCIAL = tuple(
    (pat, "non-commercial marker") for pat, _ in NON_COMMERCIAL_MARKERS)

#: Regex riders that must block a permissive reading.
RESTRICTIVE_RIDERS = (
    (r"commons clause", "commons clause"),
    (r"server side public license", "server side public license"),
    (r"no permission is hereby granted", "no permission is hereby granted"),
) + _RIDER_NON_COMMERCIAL


class LicenseClass(str, Enum):
    """The three-way policy bucket."""

    A = "A"
    B = "B"
    C = "C"

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class LicenseVerdict:
    """The outcome of classifying one component."""

    license_class: LicenseClass
    spdx_id: str | None
    reason: str
    evidence: str = ""
    path: str | None = None
    conflicting_ids: tuple[str, ...] = field(default_factory=tuple)

    def __bool__(self) -> bool:
        """Truthy when the component is safe to act on (class A or B)."""
        return self.license_class is not LicenseClass.C

    def as_dict(self) -> dict[str, Any]:
        return {
            "license_class": self.license_class.value,
            "spdx_id": self.spdx_id,
            "reason": self.reason,
            "evidence": self.evidence,
            "path": self.path,
            "conflicting_ids": list(self.conflicting_ids),
        }


A_POLICY = (
    "Permissive licence positively identified. May be vendored, relicensed, "
    "and pushed as an Anticloud artefact."
)
B_POLICY = (
    "Copyleft or source-available licence. Internal use and modification only. "
    "Relicensing and external redistribution are forbidden."
)
C_POLICY = (
    "Unknown, absent, non-commercial or unrecognised licence. Read-only reference. "
    "Default classification; never escalated to A without positive identification."
)


def _normalise(raw: str) -> str:
    return re.sub(r"\s+", " ", raw.strip().lower())


def _match_table(raw: str, ids: frozenset[str], markers: tuple[tuple[str, str], ...]) -> str | None:
    """Return the identifier matched by ``raw`` from ids or text markers."""
    norm = _normalise(raw)
    # Longest-first so "apache-2.0" wins over a bare "apache" substring match.
    # Each id must appear as a whole token: "unlicensed" must not match the id
    # "unlicense", so id matching is boundary-delimited, not substring.
    for candidate in sorted(ids, key=len, reverse=True):
        if re.search(rf"(?<![a-z0-9]){re.escape(candidate)}(?![a-z0-9])", norm):
            return candidate
    for marker, ident in markers:
        # markers are regexes over the normalised text (see the marker tables);
        # plain phrases match as themselves.
        if re.search(marker, norm):
            return ident
    return None


def _has_restrictive_rider(text: str) -> str | None:
    norm = _normalise(text)
    for pattern, label in RESTRICTIVE_RIDERS:
        if re.search(pattern, norm):
            return label
    return None


def classify_text(text: str, *, source: str | None = None) -> LicenseVerdict:
    """Classify a blob of licence text.

    Ordering matters and is intentional: an explicit non-commercial or
    copyleft statement outranks a permissive-looking phrase, so a licence that
    carries the Commons Clause on top of Apache text lands in B, not A.
    """
    if not isinstance(text, str):
        raise TypeError("text must be a str")

    # 1. Explicit SPDX metadata line, if present, is the strongest signal.
    spdx_match = _SPDX_LINE.search(text)
    explicit = _normalise(spdx_match.group("id")) if spdx_match else ""

    explicit_nc = _match_table(explicit, NON_COMMERCIAL_IDS, ())
    explicit_copy = _match_table(explicit, COPYLEFT_IDS, ())
    explicit_perm = _match_table(explicit, PERMISSIVE_IDS, ())

    if explicit_nc:
        return LicenseVerdict(LicenseClass.C, explicit_nc, "explicit non-commercial licence", "License: line", source)
    if explicit_copy:
        rider = _has_restrictive_rider(text)
        note = f" (restrictive rider present: {rider!r})" if rider else ""
        return LicenseVerdict(LicenseClass.B, explicit_copy, f"copyleft/source-available{note}", "License: line", source)

    # 2. No explicit line: fall back to whole-text marker matching.
    text_nc = _match_table(text, frozenset(), NON_COMMERCIAL_MARKERS)
    if text_nc and not explicit_perm:
        return LicenseVerdict(LicenseClass.C, text_nc, "non-commercial terms found in licence text", text_nc, source)

    rider = _has_restrictive_rider(text)
    text_copy = _match_table(text, COPYLEFT_IDS, COPYLEFT_MARKERS)
    if text_copy:
        return LicenseVerdict(LicenseClass.B, text_copy, "copyleft/source-available text", text_copy, source)

    if rider and explicit_perm:
        # Apache-style grant plus a restrictive rider: fail closed to C.
        return LicenseVerdict(
            LicenseClass.C,
            explicit_perm,
            f"permissive id present but restrictive rider {rider!r} found; failing closed",
            rider,
            source,
        )

    text_perm = _match_table(text, PERMISSIVE_IDS, PERMISSIVE_MARKERS)
    if text_perm and not rider:
        return LicenseVerdict(LicenseClass.A, text_perm, "permissive licence text identified", text_perm, source)
    if explicit_perm and not rider:
        return LicenseVerdict(LicenseClass.A, explicit_perm, "permissive SPDX id identified", f"License: {explicit}", source)

    if not text.strip():
        return LicenseVerdict(LicenseClass.C, None, "licence text is empty", "", source)
    return LicenseVerdict(LicenseClass.C, None, "no recognised licence identified", "", source)


def classify_name(name: str) -> LicenseVerdict:
    """Classify from a package or component *name* alone.

    Name-only evidence is never enough for A: a directory called ``MIT`` proves
    nothing about its contents.  Names are used for reporting and for the B
    branch, where a recognised copyleft id in the name is a genuine signal.
    """
    if not isinstance(name, str):
        raise TypeError("name must be a str")
    norm = _normalise(name)
    if not norm:
        return LicenseVerdict(LicenseClass.C, None, "component name is empty")

    nc = _match_table(norm, NON_COMMERCIAL_IDS, ())
    if nc:
        return LicenseVerdict(LicenseClass.C, nc, "non-commercial id in component name", norm)
    copy = _match_table(norm, COPYLEFT_IDS, ())
    if copy:
        return LicenseVerdict(LicenseClass.B, copy, "copyleft id in component name", norm)
    perm = _match_table(norm, PERMISSIVE_IDS, ())
    if perm:
        return LicenseVerdict(
            LicenseClass.C,
            perm,
            "permissive id in name only; name alone cannot prove class A without a licence file",
            norm,
        )
    return LicenseVerdict(LicenseClass.C, None, "unrecognised component name", norm)


def classify_file(path: str | os.PathLike[str]) -> LicenseVerdict:
    """Classify a component directory or licence file.

    If ``path`` is a directory the usual licence filenames are probed in order;
    the first that yields a non-C verdict wins, otherwise the best C verdict
    (the one with the most evidence) is returned.
    """
    p = Path(path)
    if p.is_dir():
        best: LicenseVerdict | None = None
        found_any = False
        for filename in CANDIDATE_FILENAMES:
            candidate = p / filename
            if not candidate.is_file():
                continue
            found_any = True
            try:
                text = candidate.read_text(encoding="utf-8", errors="replace")
            except OSError as exc:  # pragma: no cover - unreadable file
                verdict = LicenseVerdict(LicenseClass.C, None, f"licence file unreadable: {exc}", filename, str(p))
            else:
                verdict = classify_text(text, source=str(candidate))
            if verdict.license_class is not LicenseClass.C:
                return verdict
            if best is None or len(verdict.evidence) > len(best.evidence):
                best = verdict
        if best is not None:
            return LicenseVerdict(best.license_class, best.spdx_id, best.reason, best.evidence, str(p))
        return LicenseVerdict(LicenseClass.C, None, "no licence file present in directory", "", str(p))

    if not p.is_file():
        return LicenseVerdict(LicenseClass.C, None, "path does not exist", "", str(p))

    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:  # pragma: no cover - unreadable file
        return LicenseVerdict(LicenseClass.C, None, f"licence file unreadable: {exc}", "", str(p))
    return classify_text(text, source=str(p))


def scan_tree(root: str | os.PathLike[str], *, include_name_hints: bool = True) -> dict[str, Any]:
    """Classify every immediate subdirectory of ``root`` as a component.

    Returns a JSON-ready report with a per-component verdict and a roll-up of
    counts.  ``overall`` is the worst class found, so a single class C component
    makes the tree C — the report fails closed at the aggregate level too.
    """
    base = Path(root)
    if not base.is_dir():
        raise NotADirectoryError(f"{base} is not a directory")

    components: list[dict[str, Any]] = []
    if include_name_hints:
        for entry in sorted(p for p in base.iterdir() if p.is_dir()):
            components.append(classify_file(entry).as_dict())

    counts = {c.value: 0 for c in LicenseClass}
    worst = LicenseClass.A
    for component in components:
        klass = LicenseClass(component["license_class"])
        counts[klass.value] += 1
        if _rank(klass) > _rank(worst):
            worst = klass

    return {
        "root": str(base),
        "components": components,
        "counts": counts,
        "overall": worst.value,
        "policy": {LicenseClass.A.value: A_POLICY, LicenseClass.B.value: B_POLICY, LicenseClass.C.value: C_POLICY},
    }


def _rank(license_class: LicenseClass) -> int:
    return {LicenseClass.A: 0, LicenseClass.B: 1, LicenseClass.C: 2}[license_class]


def to_json(report: dict[str, Any]) -> str:
    """Serialise a report deterministically."""
    return json.dumps(report, indent=2, sort_keys=True)
