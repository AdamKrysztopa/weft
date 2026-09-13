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


#: `28.1`'s ratchet, pinned empty. A public page that must link into the untracked record is named
#: here with its reason, so the exception is a line in a diff rather than a silent sweep result.
PAGES_ALLOWED_TO_ROUTE_INTERNAL: Final[frozenset[str]] = frozenset()

#: A markdown link whose target is under `docs/internal/`, from any depth. **Link syntax, never the
#: bare string** — `tests/docs/test_phase_document_routing.py`:12-19's distinction, and the one this
#: whole check turns on: "`docs/internal/lessons.md` `L8.5`" beside a fact is a citation, the form
#: `CLAUDE.md` asks a docstring to use and 250 source files already use, and the id is the datum.
#: Telling a reader to *go* somewhere they do not have is the defect.
_INTERNAL_LINK: Final[re.Pattern[str]] = re.compile(
    r"\]\((?:\.\./)*(?P<target>docs/internal/\S*?)\)"
)

#: Whitespace inside the parentheses is deliberate: `manual/user-manual.md`:722 and
#: `manual/quickstart.md`:143 both wrap a link across two lines, and a pattern that missed
#: them would report a hand-off as absent that a reader can follow.
_MARKDOWN_LINK: Final[re.Pattern[str]] = re.compile(r"\]\(\s*(?P<target>[^)\s]+)\s*\)")


def _link_targets(page: str) -> set[str]:
    """Every markdown link on `page`, resolved to a repository-relative posix path.

    Anchors, fragments and absolute URLs are dropped: what a hand-off needs is the file.
    """
    source = REPO_ROOT / page
    resolved: set[str] = set()
    for match in _MARKDOWN_LINK.finditer(source.read_text(encoding="utf-8")):
        target = match.group("target").split("#", 1)[0]
        if not target or "://" in target or target.startswith("mailto:"):
            continue
        candidate = (source.parent / target).resolve()
        try:
            resolved.add(candidate.relative_to(REPO_ROOT).as_posix())
        except ValueError:
            continue
    return resolved


def test_no_public_page_routes_a_reader_into_the_untracked_record() -> None:
    """`28.1`. The finding the third outside review opened this phase with, and the only reader
    that could have made it — every check in this tree that reads these pages executes a block or
    compares an id, and none follows a link.

    `docs/internal/` is untracked by design (`tests/conftest.py`'s `UNTRACKED_BY_DESIGN`), so a
    link into it is a dead link on the front page of the project for every clone and every wheel.
    """
    # Arrange
    swept = [page for page in PUBLIC_PAGES if page not in PAGES_ALLOWED_TO_ROUTE_INTERNAL]
    assert swept, "every public page was waived — nothing was actually swept"

    # Act
    routing = [
        f"{page}:{text.count(chr(10), 0, match.start()) + 1} → {match.group('target')}"
        for page in swept
        for text in [(REPO_ROOT / page).read_text(encoding="utf-8")]
        for match in _INTERNAL_LINK.finditer(text)
    ]

    # Assert
    assert not routing, (
        "public pages link into `docs/internal/`, which no clone and no wheel has:\n  "
        + "\n  ".join(routing)
        + "\n\nCite the id if the reason matters — `docs/internal/lessons.md` `L8.5` beside a "
        "fact is what `CLAUDE.md` asks for and this check does not read. What it refuses is a "
        "link, which tells a stranger to go and open a file they do not have"
    )


def test_each_route_page_links_to_the_page_it_hands_to() -> None:
    """The hand-off is a property of the *page*, not of the table that plans it.

    `08` §1 can say step 2 hands to the user manual and the quickstart can end without mentioning
    it; the reader stops there either way.
    """
    # Act
    stranded = [
        f"`{step.page}` does not link to `{step.hands_to}`"
        for step in route()
        if step.hands_to is not None and step.hands_to not in _link_targets(step.page)
    ]

    # Assert
    assert not stranded, (
        "the route breaks on the page rather than in the table:\n  "
        + "\n  ".join(stranded)
        + "\n\n`docs/08-manuals.md` §1 names each step's successor; the page has to name it too, "
        "or the reader arrives at the end of a page with nowhere to go"
    )


def test_the_readme_says_what_an_id_citation_into_the_untracked_record_is() -> None:
    """`28.1`'s last clause. Stripping the citations was option (c) and was not taken — 34 tracked
    non-Python files and 250 Python files carry the form — so the page owes a reader one sentence
    saying what those ids are and that a clone will not have the files they name.

    Presence, never wording: the section names the directory and says a clone does not have it.
    """
    # Arrange
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    layout = re.search(r"^## Layout$.*?(?=^## )", readme, re.MULTILINE | re.DOTALL)
    assert layout is not None, "`README.md` has no *Layout* section to carry the sentence"

    # Act
    section = layout.group(0)

    # Assert
    assert "docs/internal/" in section, (
        "`README.md` → *Layout* does not name `docs/internal/`. A reader meeting "
        "`docs/internal/lessons.md L8.5` in a docstring has no way to learn that the id is the "
        "datum and the file is developer-local"
    )
    assert any(word in section for word in ("clone", "checkout", "wheel")), (
        "`README.md` → *Layout* names `docs/internal/` without saying a clone does not have it, "
        "which is the half that stops the citation reading as a broken link"
    )
