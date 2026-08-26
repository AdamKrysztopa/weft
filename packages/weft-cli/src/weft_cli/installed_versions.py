"""What version of each distribution is actually installed — `weft plugins doctor`'s column.

Ledger task **6.4**. `docs/09-release.md` §1, a binding consequence of the release set G10
settled 2026-08-22: "`weft plugins doctor` gains one column, not a new command: the version of
each active distribution. **Whether `doctor` also flags a mismatch, and what a mismatch does, are
G9's** — the column exists under either answer, because `doctor` has to be able to *say* what is
installed before any policy can act on it."

**Why this is not in the kernel, and why `PackReport` gains no field.** G9's own answer (`09`
§2.3, answer 1) is explicit that skew is "detected and reported by `weft plugins doctor`, never
used to refuse a load. There is no kernel load-time version check and the kernel gains no lines."
A version column is the same kind of fact, arrived at one task later: a `doctor` feature, read
from installed metadata by the CLI, costing `weft-kernel` nothing. `weft_cli.skew` reads the same
source for the same reason and this module deliberately does not import it — skew asks whether an
installed version *satisfies another distribution's declared specifier*, which is a comparison;
this asks only what is there.

**An absent version is reported, not dropped.** `importlib.metadata.version` raises
`PackageNotFoundError` for a distribution with no `.dist-info` — which is a real state a
`doctor` run can meet, since a `PackReport` exists for a pack that was refused or failed as
readily as for one that loaded. The name is omitted from the mapping and
`weft_cli.plugins_report` renders that omission as *"version not recorded"*, so the fact reaches
the operator's screen rather than being smoothed into a blank. `docs/lessons.md` L5.9: an empty
answer means *"I did not find it"*, never *"it is not there"*.
"""

from __future__ import annotations

from collections.abc import Iterable
from importlib import metadata


def installed_versions(distributions: Iterable[str]) -> dict[str, str]:
    """`{distribution: version}` for each name that has recorded metadata.

    A name with none is left out — see the module docstring for why that is a reported state
    rather than a swallowed one.
    """
    found: dict[str, str] = {}

    for distribution in distributions:
        try:
            found[distribution] = metadata.version(distribution)
        except metadata.PackageNotFoundError:
            continue

    return found
