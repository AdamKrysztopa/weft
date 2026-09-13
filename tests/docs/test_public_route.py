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
import tomllib
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Final

from tests.architecture.conftest import tracked_files
from tests.docs.test_quickstart import BLOCKS_WAIVED_FROM_EXECUTION as QUICKSTART_WAIVER
from tests.docs.test_readme_is_enough import BLOCKS_WAIVED_FROM_EXECUTION as README_WAIVER

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


#: `28.2`'s ratchet, pinned empty. A block that must differ between the two pages is named here
#: with its reason — the two walkthroughs are the same walkthrough, and a divergence nobody chose
#: is the failure this check exists for.
BLOCKS_ALLOWED_TO_DIFFER: Final[frozenset[str]] = frozenset()

_TAGGED_FENCE: Final[re.Pattern[str]] = re.compile(
    r"^```(?P<language>\w+)\s+id=(?P<id>\S+)\n(?P<body>.*?)^```\s*$", re.MULTILINE | re.DOTALL
)


def _tagged_blocks(page: str) -> dict[str, str]:
    """Every fenced block on `page` carrying an `id=`, by id."""
    text = (REPO_ROOT / page).read_text(encoding="utf-8")
    return {match.group("id"): match.group("body") for match in _TAGGED_FENCE.finditer(text)}


def test_the_readme_and_the_quickstart_agree_block_for_block() -> None:
    """`28.2`, and `L17.4`(b): `08` §3 aims a harness at each page and nothing asserted they agree.

    Both pages carry the same walkthrough, both are executed, and both passing says nothing about
    whether a reader who starts on one and continues on the other is typing one coherent sequence.
    Two blocks had already drifted — the corpus file the quickstart then quotes back as output,
    and a `--yes` on one page's `index` and not the other's.
    """
    # Arrange
    readme = _tagged_blocks("README.md")
    quickstart = _tagged_blocks("manual/quickstart.md")
    shared = sorted((set(readme) & set(quickstart)) - BLOCKS_ALLOWED_TO_DIFFER)
    assert shared, (
        "no block id appears on both `README.md` and `manual/quickstart.md`. The floor `08` §3 "
        "requires: nothing was compared, so nothing below could have failed"
    )

    # Act
    differing = [name for name in shared if readme[name] != quickstart[name]]

    # Assert
    assert not differing, (
        f"these blocks differ between `README.md` and `manual/quickstart.md`: {differing}. "
        f"They are the same walkthrough under the same ids; a reader who indexes the README's "
        f"corpus and then reads the quickstart's expected output is comparing two different runs"
    )


#: `28.3`'s ratchet, pinned empty. A claim beside a waived block that this check must not read is
#: named here with its reason.
WAIVED_PROSE_ALLOWED_TO_NAME: Final[frozenset[str]] = frozenset()

#: The names this project published before **G19** folded the add-ons into extras on 2026-09-09,
#: plus the four yanked on 2026-09-05. None is a distribution and none may be installed; they are
#: listed rather than merely absent from `_published_names()` so the failure says *retired* rather
#: than *unknown*, which is the difference between a typo and a page that has not been read since
#: the consolidation.
RETIRED_DISTRIBUTION_NAMES: Final[frozenset[str]] = frozenset(
    {
        "weft-generate",
        "weft-embed",
        "weft-command",
        "weft-llm",
        "weft-pdf",
        "weft-openai",
        "weft-qdrant",
        "weft-otel",
        "weft-docling",
        "weft-agent",
        "weft-kg",
        "weft-graph",
    }
)

_MANIFESTS: Final[tuple[Path, ...]] = (
    REPO_ROOT / "packages" / "weft-kernel" / "pyproject.toml",
    REPO_ROOT / "packages" / "weft-rag" / "pyproject.toml",
)

_DISTRIBUTION_NAME: Final[re.Pattern[str]] = re.compile(r"\bweft-[a-z][a-z0-9-]*")
_ATTACHED_EXTRA: Final[re.Pattern[str]] = re.compile(r"weft-rag\[(?P<names>[a-z, ]+)\]")
_BARE_EXTRA: Final[re.Pattern[str]] = re.compile(r"`\[(?P<name>[a-z][a-z0-9-]*)\]`")
_INSTALL_VERB: Final[re.Pattern[str]] = re.compile(r"\b(?:uv add|uv pip install|pip install)\b")


def _install_instructions(prose: str) -> list[str]:
    """The paragraphs of `prose` that tell a reader to install something."""
    return [block for block in re.split(r"\n\s*\n", prose) if _INSTALL_VERB.search(block)]


@cache
def _published_names() -> frozenset[str]:
    """The `[project] name` of each distribution this repository builds — read, never retyped."""
    names = {
        tomllib.loads(path.read_text(encoding="utf-8"))["project"]["name"] for path in _MANIFESTS
    }
    assert names, (
        "no distribution names were read — the prose below would be checked against nothing"
    )
    return frozenset(names)


@cache
def _published_extras() -> frozenset[str]:
    """Every `[project.optional-dependencies]` key across those distributions."""
    extras: set[str] = set()
    for path in _MANIFESTS:
        project = tomllib.loads(path.read_text(encoding="utf-8"))["project"]
        extras.update(project.get("optional-dependencies", {}))
    assert extras, (
        "no extras were read — an `[openai]` in the prose would be checked against nothing"
    )
    return frozenset(extras)


def _prose_around(page: str, block_id: str) -> str:
    """The text between the fenced block before `block_id` and the one after it, block excluded.

    This is the span a waiver leaves uncovered: a block that is not executed takes the sentences
    explaining it out of the gate with it, and the sentences are where the install instructions
    live (`docs/internal/lessons.md` `L17.4`).
    """
    text = (REPO_ROOT / page).read_text(encoding="utf-8")
    fences = list(_TAGGED_FENCE.finditer(text)) + [
        match for match in re.finditer(r"^```.*?^```\s*$", text, re.MULTILINE | re.DOTALL)
    ]
    target = next(
        (match for match in _TAGGED_FENCE.finditer(text) if match.group("id") == block_id), None
    )
    assert target is not None, f"`{page}` has no block tagged id={block_id}"
    starts = sorted({match.start() for match in fences})
    ends = sorted({match.end() for match in fences})
    previous_end = max((end for end in ends if end <= target.start()), default=0)
    next_start = min((start for start in starts if start >= target.end()), default=len(text))
    return text[previous_end : target.start()] + text[target.end() : next_start]


def test_the_prose_beside_a_waived_block_names_only_what_exists() -> None:
    """`28.3`. A waiver is a ratchet on *execution*, and nothing read the claims beside the block.

    Measured 2026-09-12, before `R17.15`: the quickstart's install section instructed four separate
    `uv add`s for distributions that had been extras of one wheel since **G19**, and said the
    package was on no index three days after it was published. Every executed block on the page was
    green throughout. The waiver is still right — this gate makes no network call — and the floor
    beneath it is that the sentences it takes out of the run still describe the tree.

    **Two populations, deliberately different, and the difference is what a page is allowed to
    say.** A *distribution* name is read only in a paragraph that tells the reader to install
    something — `uv add`, `pip install` — because a page may and should name a retired name in
    order to withdraw it, and `README.md`'s status blockquote does exactly that about the four
    yanked on 2026-09-05. An *extra* is read wherever it appears beside the block: an extra is
    never the subject of a withdrawal here, and `[graph]` — which existed for one day — is the
    instance `L17.5` was written about.

    **What this does not cover**, per `08`'s rule that a floor names its own gap: the prose is read
    for *names*, never for claims. "Install this first" pointing at the wrong step is not something
    a pattern can see, and the exit (`28.5`) is where a person reads the page instead.
    """
    # Arrange — the waivers themselves, read from the modules that own them rather than retyped.
    waived = {
        "README.md": README_WAIVER,
        "manual/quickstart.md": QUICKSTART_WAIVER,
    }
    spans = {
        (page, block_id): _prose_around(page, block_id)
        for page, ids in waived.items()
        for block_id in ids
        if block_id not in WAIVED_PROSE_ALLOWED_TO_NAME
    }
    assert spans, "no waived block on either page — nothing was read, so nothing could fail"

    # Act
    wrong: list[str] = []
    for (page, block_id), prose in spans.items():
        for paragraph in _install_instructions(prose):
            for name in sorted(set(_DISTRIBUTION_NAME.findall(paragraph))):
                if name in _published_names():
                    continue
                why = "retired" if name in RETIRED_DISTRIBUTION_NAMES else "never published"
                wrong.append(f"{page} (beside id={block_id}): installs `{name}`, which is {why}")
        claimed = {
            extra.strip()
            for match in _ATTACHED_EXTRA.finditer(prose)
            for extra in match.group("names").split(",")
        }
        if "extra" in prose:
            claimed.update(match.group("name") for match in _BARE_EXTRA.finditer(prose))
        for extra in sorted(claimed - _published_extras()):
            wrong.append(f"{page} (beside id={block_id}): `[{extra}]` is not an extra of weft-rag")

    # Assert
    assert not wrong, (
        "prose beside a waived block names something that does not exist:\n  "
        + "\n  ".join(wrong)
        + f"\n\nDistributions read from {[str(p.relative_to(REPO_ROOT)) for p in _MANIFESTS]}: "
        + f"{sorted(_published_names())}; extras: {sorted(_published_extras())}"
    )


#: `28.4`'s ratchet, pinned empty. A public page that must carry a link, a count or a task name
#: this file cannot check is named here with its reason.
PAGES_WAIVED_FROM_STRUCTURE: Final[frozenset[str]] = frozenset()

#: The nouns of the developer-local record. A number in front of one of these is a fact about a
#: table no reader of a clone can see, and it is wrong the next time a gate closes: `26.0` fixed
#: `README.md`'s gate counts on 2026-09-11 and they were false again inside twenty-four hours.
#: *Phases* are deliberately absent — `manual/contract-reference.md`:922 says a property "went
#: unreached for two phases", which is history and stays true.
UNTRACKED_LOG_NOUNS: Final[tuple[str, ...]] = ("gates", "gate", "decision gates", "decisions")

_QUANTIFIED_LOG = re.compile(
    r"\b(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|"
    r"fifteen|sixteen|seventeen|eighteen|nineteen|twenty|twenty-\w+|\d+)[- ]"
    r"(?:architecture |decision |open |settled )*(?:gates?|decisions)\b",
    re.IGNORECASE,
)
_POE_TASK = re.compile(r"\bpoe (?P<task>[a-z][a-z0-9-]*)")


@cache
def _poe_tasks() -> frozenset[str]:
    """Every task name in the workspace's `[tool.poe.tasks]` — read, never retyped."""
    tasks = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))["tool"][
        "poe"
    ]["tasks"]
    assert tasks, "no poe tasks were read, so no page's command could have been checked"
    return frozenset(tasks)


def _structurally_checked_pages() -> list[str]:
    swept = [page for page in PUBLIC_PAGES if page not in PAGES_WAIVED_FROM_STRUCTURE]
    assert swept, "every public page was waived — nothing was read"
    return swept


def test_every_link_on_a_public_page_resolves_to_something_tracked() -> None:
    """`28.4`'s first clause, generalised past `CONTRIBUTING.md` to every public page.

    `03-public-route.md` §5 step 1 runs this by hand at the exit, once. It is the same act and it
    is mechanical, so it runs every time instead: a link into `docs/internal/` is one way to
    strand a reader and a link to a file that was renamed is the other, and only the first has a
    check of its own.
    """
    # Arrange
    tracked = tracked_files()

    # Act
    broken: list[str] = []
    for page in _structurally_checked_pages():
        source = REPO_ROOT / page
        for target in sorted(_link_targets(page)):
            resolved = REPO_ROOT / target
            if target in tracked or (
                resolved.is_dir() and any(name.startswith(f"{target}/") for name in tracked)
            ):
                continue
            broken.append(f"{source.name}: `{target}`")

    # Assert
    assert not broken, (
        "public pages link to paths this repository does not track:\n  "
        + "\n  ".join(broken)
        + "\n\nA reader with a clone or a wheel follows these; a rename that missed one is "
        "indistinguishable, from where they sit, from a page that was never true"
    )


def test_no_public_page_counts_the_rows_of_a_developer_local_log() -> None:
    """`28.4`'s second clause. A tracked page counting an untracked table is wrong by construction.

    `CONTRIBUTING.md` said "ten architecture gates … six are closed and four are not" against a
    log of thirty-four rows, and `README.md` carried two counts that `26.0` corrected on
    2026-09-11 and that were false again within a day. The repair was never better numbers: it is
    stating the property — *the decisions are recorded, and none open today blocks what ships* —
    which stays true without anybody maintaining it.

    **Two pages, not twelve, and the narrowing is measured rather than cautious.** Swept across
    the whole public set this arrives red on two correct sentences: `manual/user-manual.md`:42's
    "One gate in front of the runner still reads the primary alone" is a branch in the code, and
    `manual/operations-guide.md`:612's "three decisions in it" are `[packs.store]` settings. Both
    are ordinary English about something else, and a two-entry waiver is where a real count would
    hide (`R10.2`'s shape). The defect was on the two pages a stranger and a contributor land on,
    which is the population this clause keeps.
    """
    # Act
    counted = [
        f"{page}:{text.count(chr(10), 0, match.start()) + 1} — {match.group(0)!r}"
        for page in ROUTE_PAGES_OUTSIDE_MANUAL
        for text in [(REPO_ROOT / page).read_text(encoding="utf-8")]
        for match in _QUANTIFIED_LOG.finditer(text)
    ]

    # Assert
    assert not counted, (
        "a public page counts something only the developer-local decision log knows:\n  "
        + "\n  ".join(counted)
        + "\n\nSay the property instead. A count here is right on the day it is written and "
        "wrong at the next gate, and nothing on a public page can notice"
    )


def test_every_poe_task_a_public_page_names_exists() -> None:
    """`28.4`'s third clause: a command a reader is told to run resolves in `pyproject.toml`."""
    # Act
    unknown = sorted(
        {
            f"{page}: `poe {match.group('task')}`"
            for page in _structurally_checked_pages()
            for match in _POE_TASK.finditer((REPO_ROOT / page).read_text(encoding="utf-8"))
            if match.group("task") not in _poe_tasks()
        }
    )

    # Assert
    assert not unknown, (
        "public pages name `poe` tasks that do not exist:\n  "
        + "\n  ".join(unknown)
        + f"\n\nDeclared in `pyproject.toml` `[tool.poe.tasks]`: {sorted(_poe_tasks())}"
    )
