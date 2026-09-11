"""A gate run that silently shrank is not a green — ledger task **8.20**.

`docs/internal/lessons-archive.md` `L7.8`. A container brought down mid-task dropped 51 tests out of
every subsequent run, and every one of those runs reported green. Nothing read pytest's own skip
count, so a suite that quietly stopped covering a large part of what it covers looked identical to
one that passed.

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
    if (_UNTRACKED_ROOT / repo_relative).exists():
        return None
    return (
        f"{repo_relative} is untracked by design (owner's decision, 2026-09-11 — see "
        f".gitignore and tests.conftest.UNTRACKED_BY_DESIGN) and absent from this checkout"
    )


#: The substring a container-dependent skip puts in its own reason — `tests/integration`'s skip
#: helper reports `WEFT_DATABASE_URL (<dsn>) is unreachable: <driver error>`. Matched loosely on
#: purpose (`docs/internal/lessons.md` L6.9): the driver's half of that sentence is not ours and
#: changes between versions, while the first half is written here.
_UNREACHABLE: Final[str] = "is unreachable"

#: Every environment variable whose non-empty value is the operator's claim that a container is up.
#: **Two, since `docs/internal/lessons.md` `L11.22`** — this was `WEFT_DATABASE_URL` alone, and with
#: Qdrant stopped a gate run reported 44 skips against an expected 9 and still exited `0`, because
#: nothing here made a claim about the second container. The asymmetry was visible in this very
#: file: `_CONTAINER_TOKENS` below has listed **both** variables since it was written, so the
#: scheduling half knew about two containers while the shrink guard knew about one.
_CLAIM_ENVS: Final[tuple[str, ...]] = ("WEFT_DATABASE_URL", "WEFT_QDRANT_URL")

#: The operator's claim about how many tests *should* skip — `docs/internal/lessons.md` `L11.22`,
#: the other half. The two variables above only catch a container the operator explicitly named, and
#: both have working defaults, so a laptop that never exports `WEFT_QDRANT_URL` claims nothing about
#: Qdrant and a stopped container is invisible to them. `CLAUDE.md` has stated the expected count in
#: **prose** — *"Expected skip count is 9; more means a container is down"* — which is exactly the
#: shape this repository keeps discovering is not a check. **This is not the invented threshold the
#: module docstring refuses**, and the difference is who chooses the number. *"More than N skips is
#: suspicious"* is a constant nobody can defend. A count the **operator states**, in the same breath
#: as the DSN, is a claim the run can contradict — the identical mechanism one variable over. **And
#: it is set by `.github/workflows/ci.yml`, not by `pyproject.toml`, because a skip count is a fact
#: about an *environment*.** The first version of this check pinned `9` in the `test` task; 9 was a
#: fact about the machine it was measured on, which had Qdrant running. CI — which provisions
#: Postgres alone, matching what `docker compose up -d` starts — produced **48** and went red on the
#: first push. The same tree with Qdrant unreachable locally produces **44**. Three numbers, three
#: environments, and only one of them is declared in a file. So the claim lives beside the services
#: that determine it, and a local run makes none: nothing here fires unless someone states a number,
#: and the container half above still speaks whenever a named service is down. `L11.21`'s rule —
#: every running service is an assumption the local gate is making — arriving in the check written
#: to answer its sibling.
_EXPECTED_SKIPS_ENV: Final[str] = "WEFT_EXPECTED_SKIPS"

_container_skips: list[str] = []

#: Every skip this run produced, counted where pytest itself counts them — in the per-report hook,
#: which the controller runs for every worker's reports under `-n auto`. **Counted here rather than
#: read off `TerminalReporter.stats`, and that was measured.** The first version of this check read
#: `stats["skipped"]` inside `pytest_terminal_summary` and set a flag for `pytest_sessionfinish` to
#: act on. It printed a correct, red "gate shrank" banner and the process exited **0**:
#: `pytest_sessionfinish` runs *before* `pytest_terminal_summary`, so the flag was always empty when
#: the exit status was decided. A guard against a silent shrink that silently could not fail —
#: `docs/internal/lessons.md` `L11.11` happening to the check written to answer `L11.11`, caught
#: only because `phase-step` → *Finish* item 3 requires planting a disagreeing case and watching it
#: go red.
_skips_seen: list[str] = []


def _claimed_containers() -> tuple[str, ...]:
    """Every claim variable the operator actually set to something."""
    return tuple(env for env in _CLAIM_ENVS if os.environ.get(env, "").strip())


def _expected_skips() -> int | None:
    """The operator's stated skip count, or `None` when they stated none.

    A value that is not an integer is treated as no claim rather than as a failure: this is a
    guard against a silent shrink, and turning a typo in an environment variable into a red gate
    would be a guard that fails runs for a reason unrelated to what it watches.
    """
    raw = os.environ.get(_EXPECTED_SKIPS_ENV, "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    """Record every skip whose reason says the database was unreachable."""
    if report.skipped and isinstance(report.longrepr, tuple):
        reason = report.longrepr[2]
        # **A skip only contradicts the operator's claim when it names the variable that
        # carried it**, which is why this matches the reason against the claim variables rather
        # than against the word "container". That was found by watching an earlier version fire
        # on the wrong one: `tests/integration/test_store_conformance.py` skips when *qdrant* is
        # down, and `WEFT_DATABASE_URL` makes no claim about qdrant. `L11.22` is the same
        # observation from the other side — qdrant carries its own claim, and it was not read.
        claimed = _claimed_containers()
        if _UNREACHABLE in reason and any(env in reason for env in claimed):
            _container_skips.append(f"{report.nodeid} — {reason.strip()}")
    # `when != "teardown"` matches what pytest's own summary counts: a `skipif` reports at
    # `setup` and a `pytest.skip()` call at `call`, and a teardown skip would double-count a
    # test already tallied.
    if report.skipped and report.when != "teardown":
        _skips_seen.append(report.nodeid)


def pytest_terminal_summary(terminalreporter: pytest.TerminalReporter) -> None:
    """Say what shrank, through pytest's own reporting channel.

    Two independent checks, reported together: a skip that contradicts a named container's own
    claim, and a total skip count that contradicts the operator's stated one. Either alone is
    enough to fail the run — see `pytest_sessionfinish`.
    """
    expected = _expected_skips()
    if expected is not None:
        actual = len(_skips_seen)
        if actual != expected:
            terminalreporter.section("gate shrank", red=True)
            terminalreporter.write_line(
                f"This run claimed {expected} skip(s) via {_EXPECTED_SKIPS_ENV} and produced "
                f"{actual}. More usually means a service this environment provisions did not "
                f"come up — `docker compose up -d`, then run it again. Fewer means a test that "
                f"used to skip now runs, which is good news that has to be recorded. The number "
                f"is a fact about an environment, so it lives where that environment is "
                f"declared: `WEFT_TEST_EXPECTED_SKIPS` in .github/workflows/ci.yml, forwarded "
                f"by pyproject.toml's `test` task. Move it in the commit that changed it "
                f"(docs/internal/lessons.md L11.22, L12.1)."
            )

    if not _claimed_containers() or not _container_skips:
        return

    terminalreporter.section("gate shrank", red=True)
    terminalreporter.write_line(
        f"{', '.join(_claimed_containers())} is set, so this run claimed a container — and "
        f"{len(_container_skips)} test(s) skipped because it was unreachable. Those tests proved "
        f"nothing, and the run would otherwise have reported green (lessons-archive L7.8, "
        f"ledger 8.20; L11.22 for the second container)."
    )
    for skipped in _container_skips[:5]:
        terminalreporter.write_line(f"  {skipped}")
    if len(_container_skips) > 5:
        terminalreporter.write_line(f"  … and {len(_container_skips) - 5} more")
    terminalreporter.write_line(
        "Start the container (`docker compose up -d`), or unset "
        f"{' / '.join(_claimed_containers())} to run the offline suite deliberately."
    )


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Turn that contradiction into a non-zero exit, so the gate reports it as a failure."""
    del exitstatus
    expected = _expected_skips()
    shrank = expected is not None and len(_skips_seen) != expected
    if (_claimed_containers() and _container_skips) or shrank:
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
