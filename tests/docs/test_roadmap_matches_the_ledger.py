"""`docs/internal/12-roadmap.md` §1's verdict column against `build-ledger.md`'s tick state.

**The table this checks is the one the *next phase* is chosen from**, and it had been drifting for
days with nothing reading it. Measured 2026-09-13, at Phase 24a's close: **four of its ten rows**
named a phase that was fully built in the ledger and still carried `MUST` or `SHOULD` — `26a`,
`16a`, `27` and `20a`. `27`'s row still read *"A live data-loss defect … its trigger has fired"*
about a phase whose four tasks were ticked and whose Exit had been run through the shipped binary.

**What that cost, and it is why this file exists rather than a sentence somewhere.** Asked what to
build next, I read `27`'s row, wrote it into `docs/internal/README.md`'s *Next action* as a
recommendation, and argued from my own sentence one message later — proposing to open a grilling
session for a question `05` → G20 had settled the day before, on a phase that was already complete.
What caught it was reading the register before writing a duplicate into it; nothing else would have.
`CLAUDE.md`'s *re-measure before arguing from a number a phase could have changed* is the rule, it
was Applied, and it did not bite, because a MoSCoW verdict does not look like a number.

**Two files that can genuinely disagree**, which is what makes this a check and not a restatement:
the ledger is edited when a task is ticked and the roadmap is edited when a phase is *planned*, so
nothing connects them but somebody remembering. The property is one-directional on purpose — a row
whose phase has tasks in the ledger, all of them ticked, must read `DONE`. A phase absent from the
ledger is unbuilt and its verdict is a plan, which this says nothing about; a phase with an open
task is building, and its verdict is still a plan too.

Skips on a clean checkout: both files are untracked by design
(`tests.conftest.UNTRACKED_BY_DESIGN`).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final

import pytest

from tests.conftest import untracked_reason

_REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
_LEDGER: Final[Path] = _REPO_ROOT / "docs" / "internal" / "build-ledger.md"
_ROADMAP: Final[Path] = _REPO_ROOT / "docs" / "internal" / "12-roadmap.md"

_MISSING: Final[str | None] = untracked_reason("docs/internal/build-ledger.md") or untracked_reason(
    "docs/internal/12-roadmap.md"
)
_requires_both = pytest.mark.skipif(_MISSING is not None, reason=_MISSING or "")

#: `## Phase 24a — The embeddable Python API`, capturing `24a`.
_PHASE_HEADING: Final[re.Pattern[str]] = re.compile(r"^## Phase ([0-9]+[a-z]?) ", re.MULTILINE)

#: A task line, ticked or not. The same shape `scripts/next_task.py` reads, and for its reason: a
#: fenced worked example in this file's own subject would otherwise be counted as a real task.
_TASK: Final[re.Pattern[str]] = re.compile(r"^- \[([ x])\] \*\*(\d+[a-z]?\.\d+)\*\*")

#: A §1 row: `| **24a** | … | LOW | **SHOULD** | nothing |`, capturing the id and the verdict.
_ROW: Final[re.Pattern[str]] = re.compile(
    r"^\| \*\*([0-9]+[a-z]?)\*\* \|.*\| \*\*([A-Z' ]+)\*\* \|"
)


def _ticks_by_phase() -> dict[str, tuple[int, int]]:
    """`{phase id: (ticked, open)}`, skipping fenced blocks the way every reader of this file must.

    `build-ledger.md` → *How to read a task line* contains an unticked task inside a fence,
    deliberately, so a worked example can never drift from the convention it documents. A counter
    that did not skip fences would read it as a permanently open task in whichever phase it falls
    under, and this check would then never report a phase as built.
    """
    found: dict[str, list[int]] = {}
    phase: str | None = None
    fenced = False
    for line in _LEDGER.read_text(encoding="utf-8").splitlines():
        if line.startswith("```"):
            fenced = not fenced
            continue
        if fenced:
            continue
        heading = _PHASE_HEADING.match(line)
        if heading is not None:
            name = str(heading.group(1))
            phase = name
            found.setdefault(name, [0, 0])
            continue
        task = _TASK.match(line)
        if task and phase is not None:
            found[phase][0 if task.group(1) == "x" else 1] += 1
    return {name: (done, still_open) for name, (done, still_open) in found.items()}


@_requires_both
def test_a_fully_built_phase_reads_done_in_the_roadmap() -> None:
    # Arrange
    ticks = _ticks_by_phase()
    rows = [
        (match.group(1), match.group(2))
        for line in _ROADMAP.read_text(encoding="utf-8").splitlines()
        if (match := _ROW.match(line))
    ]
    assert rows, (
        "no §1 row was parsed out of docs/internal/12-roadmap.md — the table's shape moved and "
        "this check is reading nothing, which would pass forever."
    )

    # Act
    stale = [
        f"{phase}: roadmap says {verdict}, ledger has {ticks[phase][0]} ticked tasks and none open"
        for phase, verdict in rows
        if phase in ticks and ticks[phase][1] == 0 and ticks[phase][0] > 0 and verdict != "DONE"
    ]

    # Assert
    assert not stale, (
        "these roadmap rows describe a phase that is finished:\n  "
        + "\n  ".join(stale)
        + "\nThe §1 table is what the next phase is chosen from, so a row that outlived its phase "
        "is a plan presented as a decision. Mark the row DONE in the commit that closes the phase."
    )


@_requires_both
def test_the_check_can_actually_fail() -> None:
    """A planted disagreement, because the assertion above passes when the tree is right and would
    pass equally if either regex had stopped matching."""
    # Arrange — one row and one phase, disagreeing the way the four real ones did.
    ticks = {"99a": (4, 0)}
    rows = [("99a", "MUST")]

    # Act
    stale = [
        phase
        for phase, verdict in rows
        if phase in ticks and ticks[phase][1] == 0 and ticks[phase][0] > 0 and verdict != "DONE"
    ]

    # Assert
    assert stale == ["99a"]


@_requires_both
def test_a_phase_still_building_is_not_reported() -> None:
    """The one-directional half: an open task means the verdict is still a plan, and a plan is
    exactly what this table is for."""
    # Arrange
    ticks = {"99a": (4, 1)}
    rows = [("99a", "MUST")]

    # Act
    stale = [
        phase
        for phase, verdict in rows
        if phase in ticks and ticks[phase][1] == 0 and ticks[phase][0] > 0 and verdict != "DONE"
    ]

    # Assert
    assert stale == []


@_requires_both
def test_the_ledger_walk_finds_the_phases_it_is_supposed_to() -> None:
    """Non-vacuity for the parser: an empty `ticks` map makes the real assertion pass over nothing.

    This is the failure mode that has no symptom — the check goes green because it compared an
    empty population, which is `L11.5`'s shape and the reason every sweep in this tree carries a
    floor.
    """
    # Arrange / Act
    ticks = _ticks_by_phase()

    # Assert
    assert len(ticks) >= 10, f"only {len(ticks)} phases were found in the ledger — the walk broke"
    assert any(done > 0 for done, _ in ticks.values()), "no phase has a ticked task"
