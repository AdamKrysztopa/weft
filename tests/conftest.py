"""A gate run that silently shrank is not a green — ledger task **8.20**.

`docs/lessons-archive.md` `L7.8`. A container brought down mid-task dropped 51 tests out of every
subsequent run, and every one of those runs reported green. Nothing read pytest's own skip count,
so a suite that quietly stopped covering a large part of what it covers looked identical to one
that passed.

**No threshold is chosen here, and that is the design.** "More than N skips is suspicious" is a
number nobody can defend, and `09` §4.4's argument against inventing one applies to a gate as well
as to a quality target. What is checked instead is an **agreement between two things the operator
already stated**: if `WEFT_DATABASE_URL` is set to a non-empty value, the operator is claiming a
database is there. A test that then skips *because that database is unreachable* means the claim is
false and every test that skipped proved nothing. That is a contradiction the run can detect about
itself, with nothing to tune.

With no `WEFT_DATABASE_URL` set, container skips are correct and expected — a laptop with no
container should still run the unit suite — so nothing fires. The check speaks only when the
environment contradicts itself.

Hooks rather than a test: this is a fact about the *run*, and a test asserting it would be a test
whose subject is the other tests. The work is split across two hooks so that neither has to reach
for anything private — `pytest_terminal_summary` owns pytest's reporting channel, and
`pytest_sessionfinish` is handed the `Session` whose exit status decides the run.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:  # pragma: no cover — import-time only, for the type checker
    import pytest

#: The substring a container-dependent skip puts in its own reason — `tests/integration`'s skip
#: helper reports `WEFT_DATABASE_URL (<dsn>) is unreachable: <driver error>`. Matched loosely on
#: purpose (`docs/lessons.md` L6.9): the driver's half of that sentence is not ours and changes
#: between versions, while the first half is written here.
_UNREACHABLE: Final[str] = "is unreachable"

#: The environment variable whose non-empty value is the operator's claim that a container is up.
_DSN_ENV: Final[str] = "WEFT_DATABASE_URL"

_container_skips: list[str] = []


def _claimed_a_database() -> bool:
    return bool(os.environ.get(_DSN_ENV, "").strip())


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    """Record every skip whose reason says the database was unreachable."""
    if report.skipped and isinstance(report.longrepr, tuple):
        reason = report.longrepr[2]
        # **Both** halves, and the second was found by watching this fire on the wrong
        # container: `tests/integration/test_store_conformance.py` skips when *qdrant* is
        # down, and `WEFT_DATABASE_URL` makes no claim about qdrant. A skip only contradicts
        # the operator's claim when it names the variable that carried it.
        if _UNREACHABLE in reason and _DSN_ENV in reason:
            _container_skips.append(f"{report.nodeid} — {reason.strip()}")


def pytest_terminal_summary(terminalreporter: pytest.TerminalReporter) -> None:
    """Say what shrank, through pytest's own reporting channel."""
    if not _claimed_a_database() or not _container_skips:
        return

    terminalreporter.section("gate shrank", red=True)
    terminalreporter.write_line(
        f"{_DSN_ENV} is set, so this run claimed a database — and {len(_container_skips)} "
        f"test(s) skipped because it was unreachable. Those tests proved nothing, and the run "
        f"would otherwise have reported green (lessons-archive L7.8, ledger 8.20)."
    )
    for skipped in _container_skips[:5]:
        terminalreporter.write_line(f"  {skipped}")
    if len(_container_skips) > 5:
        terminalreporter.write_line(f"  … and {len(_container_skips) - 5} more")
    terminalreporter.write_line(
        f"Start the container (`docker compose up -d`), or unset {_DSN_ENV} to run the offline "
        f"suite deliberately."
    )


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Turn that contradiction into a non-zero exit, so the gate reports it as a failure."""
    del exitstatus
    if _claimed_a_database() and _container_skips:
        session.exitstatus = 1
