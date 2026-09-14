"""A gate run that silently shrank is not a green — ledger task **8.20**.

`docs/internal/lessons-archive.md` `L7.8`. A container brought down mid-task dropped 51 tests out of
every subsequent run, and every one of those runs reported green. Nothing read pytest's own skip
count, so a suite that quietly stopped covering a large part of what it covers looked identical to
one that passed.

**No threshold is chosen here, and no count either.** Two things are checked. Every skip names a
cause this file knows — `SkipCause` — so a new reason to skip fails on the machine that introduces
it. And no skip contradicts a service the environment claims: `WEFT_DATABASE_URL` or
`WEFT_QDRANT_URL` set means that service is up, so a test skipping because it is unreachable
proved nothing. Unset, those skips are expected — a laptop with no container still runs the unit
suite.

**A pinned expected total, `WEFT_TEST_EXPECTED_SKIPS`, was retired on 2026-09-14.** It summed
causes that move independently — untracked documents, a Qdrant and a BM25 server CI deliberately
does not run — so it moved seven times in five days (48 to 96), and only a clean checkout could
measure it, which meant after the push.

Hooks rather than a test: this is a fact about the *run*, and a test asserting it would be a test
whose subject is the other tests. The work is split across two hooks so that neither has to reach
for anything private — `pytest_terminal_summary` owns pytest's reporting channel, and
`pytest_sessionfinish` is handed the `Session` whose exit status decides the run.
"""

from __future__ import annotations

import os
from collections.abc import Iterable, Mapping
from enum import Enum
from functools import cache
from pathlib import Path
from typing import Final

import pytest

#: The eight files under `/docs/internal/` that `.gitignore` keeps out of version control from
#: 2026-09-11 — the internal process record. Single-sourced here so every check that treats their
#: absence as expected rather than as a defect reads one list.
#:
#: **Written out rather than derived from the directory, and that is forced.** The obvious
#: definition — *anything under `docs/internal/`* — can only be evaluated by listing a directory
#: that a clean checkout does not have, so it would return the empty set precisely where the
#: allowance is needed and silently stop excusing anything.
UNTRACKED_BY_DESIGN: Final[frozenset[str]] = frozenset(
    {
        "docs/internal/README.md",
        "docs/internal/build-ledger.md",
        "docs/internal/lessons.md",
        "docs/internal/lessons-archive.md",
        "docs/internal/05-grilling-sessions.md",
        "docs/internal/12-roadmap.md",
        "docs/internal/product-direction.md",
        "docs/internal/ADAM_TODO.md",
    }
)

#: The repository root, from which every path in `UNTRACKED_BY_DESIGN` is relative.
_UNTRACKED_ROOT: Final[Path] = Path(__file__).resolve().parent.parent


def _pretending_untracked() -> bool:
    """Whether to answer as a clean checkout would, however this working tree looks.

    `WEFT_PRETEND_UNTRACKED=1 uv run poe test` takes the path CI's clean checkout takes, without
    moving `docs/internal/` aside — the source of truth for the phase in progress, which a suite
    that renamed it would be one interrupt away from losing.
    """
    return os.environ.get("WEFT_PRETEND_UNTRACKED", "") not in {"", "0"}


def untracked_reason(repo_relative: str) -> str | None:
    """`None` when `repo_relative` is present on disk; otherwise a skip reason naming it.

    Only ever called with a member of `UNTRACKED_BY_DESIGN` — asserted below — so a typo'd path
    cannot silently turn into "skip everything", which is the one way a conditional skip becomes
    the unconditional one policy forbids.
    """
    assert repo_relative in UNTRACKED_BY_DESIGN, (
        f"{repo_relative!r} is not one of the eight files this repository keeps untracked by "
        f"design — see UNTRACKED_BY_DESIGN. A skip reason must name a real member of that set."
    )
    if not _pretending_untracked() and (_UNTRACKED_ROOT / repo_relative).exists():
        return None
    return (
        f"{repo_relative} is untracked by design (owner's decision, 2026-09-11 — see "
        f".gitignore and tests.conftest.UNTRACKED_BY_DESIGN) and absent from this checkout"
    )


class SkipCause(Enum):
    """Why a test may skip. A skip whose reason names none of these fails the run, everywhere.

    A new reason to skip is a new member, added in the commit that introduces it — which fails on
    the machine making that commit, where a pinned total could only fail in CI after the push.
    """

    UNTRACKED_BY_DESIGN = "a document this repository keeps untracked by design is absent"
    POSTGRES_UNREACHABLE = "the Postgres WEFT_DATABASE_URL names is unreachable"
    QDRANT_UNREACHABLE = "the Qdrant WEFT_QDRANT_URL names is unreachable"
    BM25_UNREACHABLE = "no BM25-capable Postgres is running"
    LIVE_API_NOT_OPTED_IN = "a live API test was not opted into"
    CORPUS_NETWORK_NOT_OPTED_IN = "a corpus network test was not opted into"
    CORPUS_NOT_MATERIALISED = "the corpus documents are not on this machine"


#: The fragment of our own sentence each cause's skip reason carries. Matched on the half this tree
#: writes, never on a driver's error text, which changes between versions (`L6.9`).
_CAUSE_FRAGMENTS: Final[Mapping[SkipCause, tuple[str, ...]]] = {
    SkipCause.UNTRACKED_BY_DESIGN: ("is untracked by design",),
    SkipCause.POSTGRES_UNREACHABLE: ("WEFT_DATABASE_URL (", "WEFT_DATABASE_URL names no reachable"),
    SkipCause.QDRANT_UNREACHABLE: ("WEFT_QDRANT_URL (",),
    SkipCause.BM25_UNREACHABLE: ("no BM25 database at",),
    SkipCause.LIVE_API_NOT_OPTED_IN: ("WEFT_LIVE_API_TESTS is unset", "OPENAI_API_KEY is unset"),
    SkipCause.CORPUS_NETWORK_NOT_OPTED_IN: ("WEFT_CORPUS_NETWORK=1",),
    SkipCause.CORPUS_NOT_MATERIALISED: (
        "no corpus document is materialised",
        "corpus fixture missing",
    ),
}

#: A service whose variable, when set, is the operator's claim that it is up (`L7.8`, `L11.22`).
_CLAIMED_BY: Final[Mapping[SkipCause, str]] = {
    SkipCause.POSTGRES_UNREACHABLE: "WEFT_DATABASE_URL",
    SkipCause.QDRANT_UNREACHABLE: "WEFT_QDRANT_URL",
}


def skip_cause(reason: str) -> SkipCause | None:
    """The cause `reason` names, or `None` when it names none this file knows."""
    for cause, fragments in _CAUSE_FRAGMENTS.items():
        if any(fragment in reason for fragment in fragments):
            return cause
    return None


def skip_problems(skips: Iterable[tuple[str, str]], *, environ: Mapping[str, str]) -> list[str]:
    """Every `(nodeid, reason)` skip this run should not have produced."""
    problems: list[str] = []
    for nodeid, reason in skips:
        cause = skip_cause(reason)
        if cause is None:
            problems.append(
                f"{nodeid} skipped for a reason no SkipCause recognises: {reason.strip()!r}. "
                f"Make the test run, or add the cause to tests/conftest.py's SkipCause."
            )
            continue
        claim = _CLAIMED_BY.get(cause)
        if claim is not None and environ.get(claim, "").strip():
            problems.append(
                f"{nodeid} skipped because {cause.value}, while {claim} is set, claiming it is "
                f"up — so the test proved nothing. Start it (`docker compose up -d`), or unset "
                f"{claim} to run offline deliberately."
            )
    return problems


#: Collected per report, not read off `TerminalReporter.stats`: `pytest_sessionfinish` runs before
#: `pytest_terminal_summary`, and a flag set in the latter never reached the exit status (`L11.11`).
_skips_seen: list[tuple[str, str]] = []


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    # A teardown skip would record a test already recorded at setup or call.
    if report.skipped and report.when != "teardown" and isinstance(report.longrepr, tuple):
        _skips_seen.append((report.nodeid, report.longrepr[2]))


def pytest_terminal_summary(terminalreporter: pytest.TerminalReporter) -> None:
    problems = skip_problems(_skips_seen, environ=os.environ)
    if not problems:
        return
    terminalreporter.section("gate shrank", red=True)
    for problem in problems[:10]:
        terminalreporter.write_line(problem)
    if len(problems) > 10:
        terminalreporter.write_line(f"… and {len(problems) - 10} more")


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    del exitstatus
    if skip_problems(_skips_seen, environ=os.environ):
        session.exitstatus = 1


#: The one container this repository brings up, and the reason `tests/` is not simply handed to
#: `pytest -n auto`. `docs/internal/lessons-archive.md` `L8.30`: a close-review measurement read
#: `nodes now stored: 70` and minutes later the table held one row, because a second process in the
#: same session truncated it — two suites sharing the one Postgres produce a result about neither.
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
