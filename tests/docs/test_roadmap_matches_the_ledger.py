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

#: A §1 row's **id alone**, whatever its verdict says. `_ROW` above keys on a verdict spelled
#: `[A-Z' ]+` and therefore cannot see `WON'T yet` — right where a verdict is judged, wrong where
#: the question is whether the table has a row at all (`L22.1`).
_ROW_ID: Final[re.Pattern[str]] = re.compile(r"^\| \*\*([0-9]+[a-z]?)\*\* \|", re.MULTILINE)


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


#: A row whose own text says the phase dissolved into a ledger task rather than becoming a phase —
#: `19`'s says *"folded into ledger task `9.13`; the phase dissolves"*. Such a row has **no**
#: `## Phase 19` heading in the ledger, so the comparison below cannot see it at all, and `19` sat
#: reading `SHOULD` with `9.13` ticked. Found by reading the table out loud one hour after the
#: check above was written — the same class of defect, one gap over.
_DISSOLVED: Final[re.Pattern[str]] = re.compile(r"folded into ledger task `(\d+\.\d+)`")

#: A ticked ledger task, by id — `- [x] **9.13**`.
_TICKED_TASK: Final[re.Pattern[str]] = re.compile(
    r"^- \[x\] \*\*(\d+[a-z]?\.\d+)\*\*", re.MULTILINE
)


@_requires_both
def test_a_dissolved_phase_does_not_still_read_should() -> None:
    """A row that folded into a ledger task is finished when that task is ticked.

    It needs its own test because the one below compares against `## Phase <id>` headings, and a
    dissolved phase has none — so it is invisible to that comparison rather than passing it. An
    absence nothing looks for is `L10.33`'s shape, and this is that shape inside a check written
    to catch a neighbouring one.
    """
    # Arrange
    ledger = _LEDGER.read_text(encoding="utf-8")
    ticked = {match.group(1) for match in _TICKED_TASK.finditer(ledger)}
    roadmap = _ROADMAP.read_text(encoding="utf-8").splitlines()

    # Act
    stale: list[str] = []
    for line in roadmap:
        row = _ROW.match(line)
        dissolved = _DISSOLVED.search(line)
        if row is None or dissolved is None or row.group(2) == "DONE":
            continue
        if dissolved.group(1) in ticked:
            stale.append(
                f"{row.group(1)}: says {row.group(2)}, dissolved into {dissolved.group(1)}, ticked"
            )

    # Assert
    assert not stale, (
        "these roadmap rows describe a phase that dissolved into a task that is done:\n  "
        + "\n  ".join(stale)
        + "\nA dissolved phase has no ledger heading, so the finished-phase check cannot see it."
    )


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
    """A planted disagreement, so the assertion above is shown able to fail.

    The assertion above passes when the tree is right and would pass equally if either regex
    had stopped matching.
    """
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
    """The one-directional half: an open task means the verdict is still a plan.

    A plan is exactly what this table is for.
    """
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


#: An argument section for one phase: `## 5d · Phase 17 — …`. The separator is a middle dot and
#: the id follows the word *Phase*, which is the spelling every section in that document uses.
_SECTION: Final[re.Pattern[str]] = re.compile(r"^## \S+ · Phase ([0-9]+[a-z]?) ", re.MULTILINE)

#: **A row that dissolved is not a phase and owes no section.** Phase 19's work folded into
#: ledger task `9.13` and the row says so, pointing at the task rather than at a section — which
#: is a pointer to where the decision lives, which is all §1 asks of a row. One entry, named, so
#: a second is a visible act in a diff.
DISSOLVED_ROWS: Final[tuple[str, ...]] = ("19",)


def _rows_owing_a_section(roadmap: str) -> list[str]:
    """Every §1 row that should point at an argument section and does not.

    `WON'T` rows are excluded because §6 is where their argument lives: that table gives each one
    the trigger that fires it, and `12` §1's rule for a `WON'T` is *a trigger*, not a section.
    Everything else — `MUST`, `SHOULD`, `COULD`, and `DONE` — is a phase somebody either built or
    is about to, and for those the section is the decision the row points at.

    Two things exclude a `WON'T`, and only one of them is this filter. `_ROW`'s verdict class is
    `[A-Z' ]+`, which cannot match the lowercase in `WON'T yet`, so those rows never reach here
    at all; the `startswith` below is what catches a bare `**WON'T**`, which the class *does*
    match. Stated because a filter that looks load-bearing and is not is how a check quietly
    stops having a subject.
    """
    sections = set(_SECTION.findall(roadmap))
    return sorted(
        phase
        for phase, verdict in _verdicts(roadmap)
        if not verdict.startswith("WON'T") and phase not in DISSOLVED_ROWS and phase not in sections
    )


def _verdicts(roadmap: str) -> list[tuple[str, str]]:
    """`(phase, verdict)` per §1 row.

    Line by line, because `_ROW` is deliberately unanchored to `MULTILINE` and `.*` must not be
    allowed to reach across a row boundary.
    """
    return [
        (match.group(1), match.group(2))
        for line in roadmap.splitlines()
        if (match := _ROW.match(line))
    ]


@_requires_both
def test_every_live_row_points_at_a_section_arguing_it() -> None:
    """`docs/internal/lessons.md` `L19.5` and `L19.6`.

    **A MoSCoW row is a pointer to an argument, never the argument.** `12` §1:42 already rules
    that *"a `WON'T` with no trigger is a defect in the verdict, not a decision"*; the same holds
    of a `SHOULD` with no section, and nothing was checking it.

    **Measured 2026-09-13, at Phase 21a's close: three live rows had none** — 17, 26b and 16b.
    All three carried a verdict, a size and a dependency, and 16b had been routed as the next
    phase but one by a status block reading its row as settled work. Its entire specification was
    one table cell of fourteen words, three of whose four nouns occur exactly once in this whole
    repository — in the row that names them — and whose disambiguator cites a label defined
    nowhere in the tree.

    **Writing the three sections changed the plan**, which is the argument for this check rather
    than for a reminder: 16b's verdict became `WON'T yet` with a trigger, 26b's inherited refusal
    was withdrawn because every reason it rested on had expired at a gate, and 17 took a decision
    about corpus-scoped stages that nobody had been asked for. A row is a pointer, and when the
    argument is finally written it does not always agree with the pointer.

    Measured 2026-09-13: the row walk sees **9** live rows, `DISSOLVED_ROWS` waives **1**, so it
    checks **8** and fails **0**. Before the three sections were written it would have failed
    **3** — 17, 26b and 16b.
    """
    # Arrange
    roadmap = _ROADMAP.read_text(encoding="utf-8")

    # Act
    unargued = _rows_owing_a_section(roadmap)

    # Assert
    assert not unargued, (
        "a live roadmap row with no section arguing it is a plan nobody has taken — `12` §1: a "
        "row is a pointer to a decision (docs/internal/lessons.md L19.5, L19.6): "
        + ", ".join(unargued)
    )


@_requires_both
def test_the_section_walk_is_not_vacuous() -> None:
    """The subject is real on both sides, which is the half a green assertion cannot show.

    A regex that stopped matching would make `_rows_owing_a_section` return `[]` and the check
    above would pass for the worst possible reason. So: the row walk finds the live rows, the
    section walk finds the sections, and a planted row with no section is reported.
    """
    # Arrange
    roadmap = _ROADMAP.read_text(encoding="utf-8")

    # Assert — both walks see a real population.
    assert len(_SECTION.findall(roadmap)) >= 8, "the section walk found almost nothing"
    live = [p for p, v in _verdicts(roadmap) if not v.startswith("WON'T")]
    assert len(live) >= 6, f"the row walk found {len(live)} live rows, which is too few"

    # Act — a row that exists with no section for it, the shape all three real ones took.
    planted = roadmap + "\n| **98z** | Invented. | LOW | **SHOULD** | nothing |\n"

    # Assert
    assert "98z" in _rows_owing_a_section(planted)


@_requires_both
def test_every_section_arguing_a_phase_has_a_row_in_the_table() -> None:
    """The inverse of the check above — `docs/internal/lessons.md` `L22.1`.

    **`L19.5` made a live row point at an argument, and nothing asserted the other direction.**
    Phase 28 was specified in full on 2026-09-12 — five tasks, three reserved ids, an exit and four
    named checks — cited by a settled gate's own decision-log row and by the ledger's `R17.x`
    grouping, with every blocking repair closed. It had **no §1 row**, which is the table the next
    phase is chosen from, so `next_task.py`, the Status block and that session's own *what next*
    answer were all blind to it, and `README.md` said *"Nothing is building"* on a day it was
    unblocked and written. Found by an outside reviewer who could not read this directory at all.

    A pointer with no target and a target with no pointer are two defects; a check for one reads as
    coverage of both. Walks 13 sections today and fails 0.
    """
    # Arrange
    roadmap = _ROADMAP.read_text(encoding="utf-8")

    # Act — every row id, not `_verdicts`: that walk keys on a verdict spelled `[A-Z' ]+` and so
    # cannot see `WON'T yet`, which is deliberate where a verdict is being judged and wrong here,
    # where the question is only whether the table has a row at all. Measured: `16b` is exactly
    # that row, and reading it through `_verdicts` would have reported this check green while the
    # defect it was written for sat one row away.
    sections = set(_SECTION.findall(roadmap))
    rows = set(_ROW_ID.findall(roadmap))

    # Assert
    assert len(sections) >= 8, (
        "the section walk found almost nothing, so an empty result below would mean the parser "
        "moved rather than that every argument is scheduled"
    )
    unscheduled = sorted(sections - rows)
    assert not unscheduled, (
        f"these phases have an argument section in `12` and no §1 row: {unscheduled}. §1 is the "
        f"table the next phase is chosen from, so an argument with no row is a phase nothing can "
        f"schedule — however completely it is specified, and however many documents cite it"
    )
