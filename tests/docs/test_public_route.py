"""The public route — ledger tasks **28.0**–**28.4**, `docs/08-manuals.md` §1 and §3.

A stranger holds a clone or a wheel and no access to `docs/internal/`. `09` §5.2's last
documentation item promises they can install, index and ask from `README.md` alone; the route is
the same promise extended past the first page — arrive, run, configure, extend — with each page
handing to the next **by name**, and every page on it tracked.

**Why the route is read from `docs/08-manuals.md` rather than pinned here.** `08` §1 owns the
shipped set, and a route retyped into a check is the two-lists bug the route exists to end: the
document would be free to say one thing while the check asserted another, and the check would win
silently. So §1's route table is the specification and this file is its reader. The *population of
public pages* is pinned here instead (`PUBLIC_PAGES`), for
`tests/docs/test_phase_document_routing.py`:12-19's reason — a discovered population cannot tell a
page that is missing from a page that was never there.

**The floor**, per `08` §3: the route parses to at least four steps before any assertion about it
runs. A parser that quietly returns nothing would otherwise make every clause below vacuous, which
is the shape §3's floor rule exists for.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Final

from tests.architecture.conftest import tracked_files

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
MANUALS_DOC: Final[Path] = REPO_ROOT / "docs" / "08-manuals.md"

#: The pages a stranger can reach without a checkout of this project's process record. Pinned by
#: name, never discovered: `tests/docs/test_phase_document_routing.py`:12-19 records why a sweep
#: over whatever happens to be on disk "would flag the correct ones as often as the wrong ones".
PUBLIC_PAGES: Final[tuple[str, ...]] = (
    "README.md",
    "CONTRIBUTING.md",
    "CHANGELOG.md",
    "SECURITY.md",
    "manual/quickstart.md",
    "manual/user-manual.md",
    "manual/pack-author-guide.md",
    "manual/contract-reference.md",
    "manual/operations-guide.md",
    "manual/troubleshooting.md",
    "packages/weft-kernel/README.md",
    "packages/weft-rag/README.md",
)

#: The two pages outside `manual/` that the route depends on and `08` §1's second table owns.
ROUTE_PAGES_OUTSIDE_MANUAL: Final[tuple[str, ...]] = ("README.md", "CONTRIBUTING.md")

_SECTION_1: Final[re.Pattern[str]] = re.compile(r"^## 1\. .*?(?=^## )", re.MULTILINE | re.DOTALL)
_ROW: Final[re.Pattern[str]] = re.compile(r"^\|(?P<cells>.+)\|\s*$", re.MULTILINE)
_PATH_CELL: Final[re.Pattern[str]] = re.compile(r"`(?P<path>[A-Za-z0-9_./-]+\.md)`")

#: The cell a last step carries where a hand-off would go. Spelled once, here.
END_OF_ROUTE: Final[str] = "—"


@dataclass(frozen=True)
class Step:
    """One row of `08` §1's route table: a page, and the page it hands to."""

    ordinal: int
    page: str
    hands_to: str | None


@cache
def section_one() -> str:
    """`docs/08-manuals.md` §1, from its heading to the next one."""
    found = _SECTION_1.search(MANUALS_DOC.read_text(encoding="utf-8"))
    assert found is not None, (
        f"{MANUALS_DOC} has no '## 1.' section — `08` §1 is where the shipped set and the public "
        f"route are owned, and this file reads it rather than restating it"
    )
    return found.group(0)


def _rows(table_header: str) -> list[list[str]]:
    """Every data row of the one table in §1 whose header line contains `table_header`."""
    lines = section_one().splitlines()
    collected: list[list[str]] = []
    inside = False
    for line in lines:
        if not line.startswith("|"):
            inside = False
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if not inside:
            inside = table_header in line
            continue
        if all(set(cell) <= {"-", ":"} for cell in cells):
            continue
        collected.append(cells)
    return collected


@cache
def route() -> tuple[Step, ...]:
    """The four-step public route, in the order `08` §1 writes it."""
    steps: list[Step] = []
    for ordinal, cells in enumerate(_rows("Hands to"), start=1):
        page = _PATH_CELL.search(cells[1])
        hand_off = _PATH_CELL.search(cells[2])
        assert page is not None, f"route step {ordinal} names no page: {cells}"
        steps.append(
            Step(
                ordinal=ordinal,
                page=page.group("path"),
                hands_to=hand_off.group("path") if hand_off else None,
            )
        )
    return tuple(steps)


def test_the_route_is_written_in_08_with_at_least_four_steps() -> None:
    """The floor. Every clause below reads this table; a table that parses to nothing passes them
    all by having nothing to check."""
    # Act
    steps = route()

    # Assert
    assert len(steps) >= 4, (
        f"`docs/08-manuals.md` §1 carries {len(steps)} route steps. The route is arrive → run → "
        f"configure → extend, and `28.0` is what puts it there; a shorter table means this file's "
        f"other assertions are checking a route that is not written down"
    )


def test_every_route_page_is_tracked() -> None:
    """A route step naming an untracked page is the defect the phase opened for.

    `README.md` sent a stranger to `docs/internal/README.md` for a year — a file `.gitignore`
    keeps out of every clone and every wheel (`tests/conftest.py`'s `UNTRACKED_BY_DESIGN`).
    """
    # Arrange — both columns. A hand-off is where the defect actually was, and a check reading
    # only the *Page* column passes a route whose last instruction is to open an untracked file.
    tracked = tracked_files()
    named = [step.page for step in route()] + [
        step.hands_to for step in route() if step.hands_to is not None
    ]

    # Act
    missing = sorted({page for page in named if page not in tracked})

    # Assert
    assert not missing, (
        f"`docs/08-manuals.md` §1's route names {missing}, which this repository does not track. "
        f"A stranger with a clone or a wheel does not have it, so the route stops there"
    )


def test_each_step_hands_to_the_next_one() -> None:
    """The order is a chain, not a list: step *n*'s hand-off is step *n+1*'s page."""
    # Act
    steps = route()
    assert steps, "no route to chain — see the floor test above"
    broken = [
        f"step {step.ordinal} (`{step.page}`) hands to {step.hands_to!r}, "
        f"step {step.ordinal + 1} is `{steps[step.ordinal].page}`"
        for step in steps[:-1]
        if step.hands_to != steps[step.ordinal].page
    ]

    # Assert
    assert not broken, (
        "`docs/08-manuals.md` §1's route does not chain:\n  "
        + "\n  ".join(broken)
        + f"\n\nEach step names the page it hands to; only the last carries {END_OF_ROUTE!r}"
    )
    assert steps[-1].hands_to is None, (
        f"the last route step (`{steps[-1].page}`) hands to `{steps[-1].hands_to}`, which is not "
        f"in the route — a route that loops has no end for a reader to reach"
    )


def test_the_two_pages_outside_manual_have_a_row_in_section_one() -> None:
    """`28.0`, the half `08` §1 owed: the route's first page and the contributor's page were owned
    by nothing, which is how `CONTRIBUTING.md` reached 2026-09 saying the code was unwritten."""
    # Act
    audiences = {
        match.group("path")
        for cells in _rows("Audience")
        for match in [_PATH_CELL.search(cells[0])]
        if match is not None
    }

    # Assert
    missing = [page for page in ROUTE_PAGES_OUTSIDE_MANUAL if page not in audiences]
    assert not missing, (
        f"`docs/08-manuals.md` §1 gives no row to {missing}. `09` §5.2 promises a newcomer can "
        f"install, index and ask from `README.md` alone and `08` §1 owns which document covers "
        f"which task — a page promised by one document and owned by none is how both went stale"
    )
