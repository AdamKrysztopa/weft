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
from functools import cache
from pathlib import Path
from typing import Final

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


#: The one container this repository brings up, and the reason `tests/` is not simply handed to
#: `pytest -n auto`. `docs/lessons-archive.md` `L8.30`: a close-review measurement read `nodes now
#: stored: 70` and minutes later the table held one row, because a second process in the same
#: session truncated it — two suites sharing the one Postgres produce a result about neither.
#: Every test that reaches a container therefore carries one `xdist_group`, so `--dist loadgroup`
#: puts all of them on a single worker, where they run one after another exactly as they always
#: have. Everything that touches no container is free to spread across the rest.
_CONTAINER_GROUP: Final[str] = "weft-container"

#: What "reaches a container" means is **derived from each module's own source**, never from a
#: list kept here. A hand-maintained list of container tests is a second population that drifts
#: from the tests themselves, and the direction it drifts in is a unit test quietly sharing a
#: database with another worker. A module naming any of these either opens a connection or is one
#: import away from one; matching too widely costs only parallelism, matching too narrowly costs
#: the correctness of every run.
_CONTAINER_TOKENS: Final[tuple[str, ...]] = (
    "WEFT_DATABASE_URL",
    "WEFT_QDRANT_URL",
    "psycopg",
    "qdrant_client",
    "PgVectorStore",
    "QdrantStore",
)

#: Everything under here reaches a container by construction, whatever it says in its source.
_INTEGRATION_DIR: Final[Path] = Path(__file__).parent / "integration"


@cache
def _reaches_a_container(module_path: Path) -> bool:
    """Whether a test module may talk to Postgres or Qdrant. Unreadable means *yes*."""
    if module_path.is_relative_to(_INTEGRATION_DIR):
        return True
    try:
        source = module_path.read_text(encoding="utf-8")
    except OSError:
        return True
    return any(token in source for token in _CONTAINER_TOKENS)


def pytest_configure(config: pytest.Config) -> None:
    """Register `xdist_group`, so `--strict-markers` accepts it with or without xdist loaded.

    `pytest-xdist` registers this marker itself when it is active, and a duplicate registration
    is a no-op. Declaring it here as well is what keeps a plain `pytest tests/...` — no `-n`, no
    plugin — from failing collection on a marker `addopts`' own `--strict-markers` has never
    heard of.
    """
    config.addinivalue_line(
        "markers", "xdist_group(name): run these tests on one and the same xdist worker."
    )


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Pin every container-touching test to one xdist worker, so no two of them ever overlap.

    A no-op for a serial run — the mark is only read by `--dist loadgroup`, and adding it changes
    nothing about which tests run, in what order, or what they assert.

    **`tryfirst` is load-bearing and was found by watching it fail.** `--dist=loadgroup` does not
    read the mark at scheduling time: `xdist.remote.WorkerInteractor.pytest_collection_modifyitems`
    rewrites each marked item's nodeid to end in `@<group>`, and that is what the scheduler groups
    on. Without `tryfirst` this hook ran *after* xdist's, so the marks were added to items whose
    nodeids had already been decided, no nodeid carried a suffix, and the container tests spread
    across every worker — seventeen of them failed against each other's truncated tables in a run
    that looked exactly like a parallelism win. That is `L8.30` reproduced by the machinery meant
    to be safe from it.
    """
    for item in items:
        if _reaches_a_container(item.path):
            item.add_marker(pytest.mark.xdist_group(_CONTAINER_GROUP))
