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
`PackageNotFoundError` for a distribution with no `.dist-info` — which is a real state a `doctor`
run can meet, since a `PackReport` exists for a pack that was refused or failed as readily as for
one that loaded. The name is omitted from the mapping and `weft_cli.plugins_report` renders that
omission as *"version not recorded"*, so the fact reaches the operator's screen rather than being
smoothed into a blank. `docs/internal/lessons.md` L5.9: an empty answer means *"I did not find it"*,
never *"it is not there"*.
"""

from __future__ import annotations

from collections.abc import Iterable
from importlib import metadata

from weft_eval.run_record import active_distribution_set
from weft_kernel.discovery import PackReport


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


def active_distribution_versions(reports: Iterable[PackReport]) -> dict[str, str]:
    """`installed_versions` over exactly the set a run record calls active — task **16.3**.

    Keyed through `weft_eval.run_record.active_distribution_set` itself rather than by
    re-filtering `reports` here, so a record's versions and its `active_distributions` cannot
    come to disagree about which distributions a run had. Fitness function 8(c) binds that set
    to what `plugins doctor` reports; a second, independently-composed set of names to look
    versions up for would be a second way to disagree with it.

    A name with no recorded metadata is omitted, exactly as `installed_versions` omits it —
    which is why an empty mapping is a measurement and `None` is the absence of one
    (`RunRecord.distribution_versions`'s own comment).
    """
    return installed_versions(active_distribution_set(reports))
