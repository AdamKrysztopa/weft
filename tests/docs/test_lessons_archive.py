"""The oscillation check can actually see the archive — `docs/lessons-archive.md`.

`scripts/lessons_graph.py` is the only mechanism standing between the lessons loop and an on/off
cycle: `implement-ll` runs it before applying anything, and its answer decides whether a queue entry
is a fresh lesson or an unsettled decision wearing a lesson's clothes. That makes *"the parser sees
what is written"* a property worth checking, and it is not self-evident — it was false twice on the
same day.

**Both failures were silent, which is the point.** The parser read only each entry's *first* line,
so it found 6 of the 18 edges actually written down and answered "no oscillation" from a third of
the evidence (`lessons.md` L6.16). And a drain section inserted by anchoring on a string that first
appears inside this file's own fenced Format **example** landed inside the fence, where the parser
skips it — thirteen entries invisible, with nothing said (`L6.17`). Neither showed up as an error;
both showed up as a smaller number that nobody had a reason to distrust.

So this file reads the archive twice, by two different routes that can genuinely disagree
(`docs/lessons.md` L5.6): once through `parse()`, and once as plain text with the Format example
removed. A count that used the parser to check the parser could not fail at all.

`lessons_graph` imports as a bare module because `pyproject.toml`'s `[tool.pytest.ini_options]
pythonpath` already carries `scripts` — the same route `tests/docs` reaches the corpus-manifest
script by, and the reason that setting exists: the script is imported rather than reimplemented, so
this file cannot drift from the parser an operator actually runs.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final

from lessons_graph import parse

_REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
_ARCHIVE: Final[Path] = _REPO_ROOT / "docs" / "lessons-archive.md"
_QUEUE: Final[Path] = _REPO_ROOT / "docs" / "lessons.md"

#: A queue entry's own heading — `docs/lessons.md`'s Queue mints ids, and until `L8.21` it was
#: the one file that minted them and was never read by anything.
_QUEUE_HEADING: Final[re.Pattern[str]] = re.compile(r"^### (L[\d.]+) ", re.MULTILINE)

#: **The archive records an id in two forms and `_BULLET` sees only one.** A drain writes each
#: entry as a one-line `- **L5.3**` disposition — 66 of those — and a full `### L8.18 — title`
#: section is written for the ones that earn a narrative — 28 of those, and *no* `L8.x` entry has a
#: bullet at all. A uniqueness check built on `_BULLET` alone would have run green over a population
#: that excludes the very block the collision happened in, which is `docs/lessons.md` L6.4 exactly:
#: read the population, not the declaration. Measured while writing the check, not assumed.
_ENTRY_HEADING: Final[re.Pattern[str]] = re.compile(r"^### (L[\d.]+)", re.MULTILINE)

_BULLET: Final[re.Pattern[str]] = re.compile(r"^- \*\*(L[\d.]+)\*\*", re.MULTILINE)
_EDGE: Final[re.Pattern[str]] = re.compile(
    r"`(refines|supersedes|moves|recurs|reverses|caused-by) (L[\d.]+)`"
)


def _text() -> str:
    return _ARCHIVE.read_text(encoding="utf-8")


def _outside_the_format_example() -> str:
    """The archive with its one fenced block — the Format section's worked example — removed.

    The example is *meant* to be skipped by the parser: it is illustrative, and its `a1b2c3d`
    shas name no commit. Everything else in the file is real and must be seen.
    """
    parts = _text().split("```")
    # An odd number of segments means the fences are balanced: keep the even-indexed ones.
    assert len(parts) % 2 == 1, (
        f"{_ARCHIVE} has unbalanced ``` fences. Everything after an unclosed fence is invisible "
        f"to scripts/lessons_graph.py, which is how thirteen entries went missing once already."
    )
    return "".join(parts[::2])


def test_the_parser_sees_every_entry_that_is_written_down() -> None:
    # Arrange
    written = set(_BULLET.findall(_outside_the_format_example()))

    # Act
    entries, _ = parse(_text())

    # Assert
    assert written - set(entries) == set(), (
        "entries are in the archive and invisible to scripts/lessons_graph.py. The usual cause "
        "is a drain section written inside the Format section's fenced example — anchoring an "
        "edit on '## <date> —' finds that one first, because it is above every real section."
    )


def test_the_parser_sees_every_edge_that_is_written_down() -> None:
    """The edges are the archive's whole reason to exist, and they are routinely written on an
    entry's *continuation* line — this file's own Format example puts them there.
    """
    # Arrange
    written = {(kind, target) for kind, target in _EDGE.findall(_outside_the_format_example())}

    # Act
    _, edges = parse(_text())

    # Assert
    assert written - {(kind, target) for _, kind, target in edges} == set(), (
        "edges are written in the archive and not seen by the parser. An unseen `reverses` edge "
        "is an oscillation the next drain cannot detect, which is the one failure this whole "
        "loop exists to prevent."
    )


def test_every_edge_names_an_entry_the_archive_holds() -> None:
    """A dangling edge is a reference to a lesson nobody can read — the archive's own third
    reported condition, asserted here rather than only printed by the script.
    """
    # Act
    entries, edges = parse(_text())
    dangling = sorted(
        f"{source} {kind} {target}" for source, kind, target in edges if target not in entries
    )

    # Assert
    assert dangling == []


def test_the_check_can_tell_a_seen_entry_from_an_unseen_one() -> None:
    """The floor `docs/lessons.md` L5.19 requires: a comparison whose two sides are equal today
    proves nothing unless it is shown to be non-vacuous. Planting an entry inside a fence must
    make the parser miss it — if it did not, the two tests above would pass on any archive.
    """
    # Arrange
    planted = "## 2099-01-01 — planted\n\n- **L99.9** *a planted entry* · `deadbee`\n"

    # Act
    seen_outside, _ = parse(planted)
    seen_inside, _ = parse(f"```markdown\n{planted}```\n")

    # Assert
    assert "L99.9" in seen_outside
    assert "L99.9" not in seen_inside


def _archived_ids() -> list[str]:
    """Every id the archive mints, in **both** the forms it writes them in."""
    text = _outside_the_format_example()
    return _BULLET.findall(text) + _ENTRY_HEADING.findall(text)


def test_no_archived_id_is_used_twice() -> None:
    """`docs/lessons.md` `L8.21` — uniqueness is a property of the record, so it is checked as one.

    A duplicated id is not *wrong* anywhere: every citation of it resolves to something, which is
    precisely why nothing failed. It is ambiguous everywhere instead, and a reader following
    `docs/lessons.md L8.18` from a manual gets whichever of the two the file they opened holds.
    """
    # **Uniqueness is per form, not across forms**, and that is the archive's design rather than a
    # concession: an entry earns a one-line `- **L7.1**` disposition in its drain section *and*, if
    # it earned a narrative, a `### L7.1 —` section under *The entries as they stood*. Those are two
    # views of one lesson. What must never happen is two of either.
    text = _outside_the_format_example()
    for form, ids in (
        ("disposition bullet", _BULLET.findall(text)),
        ("narrative heading", _ENTRY_HEADING.findall(text)),
    ):
        duplicates = sorted({identifier for identifier in ids if ids.count(identifier) > 1})
        assert not duplicates, (
            f"docs/lessons-archive.md holds these ids more than once as a {form}: {duplicates}. "
            f"Every citation of one resolves to something, so nothing else in this tree notices."
        )


def test_no_queued_id_reuses_an_archived_one() -> None:
    """`docs/lessons.md` `L8.21` — the check covers every file that mints an id, not only the store.

    This is the half that actually fired. `L8.18` was written into the queue while the archive
    already held an `L8.18`, and the citation reached three shipped documents before anyone looked;
    `ci-checks` was green throughout, because until this test the queue was read by nothing.
    """
    archived = set(_archived_ids())
    queued = set(_QUEUE_HEADING.findall(_QUEUE.read_text(encoding="utf-8")))
    collisions = sorted(archived & queued)
    assert not collisions, (
        f"docs/lessons.md's Queue mints these ids and docs/lessons-archive.md already holds them: "
        f"{collisions}. Pick the next free id — the archive is append-only, so a reused one makes "
        f"every existing citation ambiguous rather than wrong."
    )


def test_the_uniqueness_checks_can_actually_fail() -> None:
    """Both halves, planted — a check whose subject is legitimately empty passes vacuously."""
    ids = ["L1.1", "L1.2", "L1.2"]
    assert sorted({i for i in ids if ids.count(i) > 1}) == ["L1.2"]

    archived = set(_archived_ids())
    assert archived, "the archive parsed to no ids at all, so the comparison is vacuous"
    assert {"L5.3", "L8.18"} <= archived, (
        "the id sweep misses one of the archive's two forms — L5.3 is a bullet, L8.18 a heading"
    )
    assert sorted(archived & {"L8.18", "L9.99"}) == ["L8.18"], (
        "L8.18 is not in the archive, so the collision this check was written for cannot be shown"
    )


#: Every tree directory that cites a lesson by id. `docs/lessons.md` and the archive are the two
#: that *mint* ids and are read separately; everything here only ever refers to one.
#: A disposition written as a table row — the form the 2026-09-05 drain used for 21 entries, and
#: the form `scripts/lessons_graph.py` cannot read. See `docs/lessons.md` `L8.22`.
_TABLE_ROW_ENTRY: Final[re.Pattern[str]] = re.compile(r"^\|\s*`(L[\d.]+)`", re.MULTILINE)

_CITING_ROOTS: Final[tuple[str, ...]] = (
    "tests",
    "docs",
    "manual",
    "packages",
    "scripts",
    ".github",
)

_CITATION: Final[re.Pattern[str]] = re.compile(r"\bL(\d{1,2}\.\d{1,2})\b")

#: Ids this module invents to plant its own failures. Named rather than excluded by filename,
#: so this file stays inside the population it checks — a check that exempts itself is the
#: shape `docs/lessons.md` L6.12 refuses one level up.
_PLANTED_IDS: Final[frozenset[str]] = frozenset({"L1.1", "L1.2", "L9.99", "L99.9"})


def _cited_ids() -> dict[str, list[str]]:
    """Every `Lx.y` cited anywhere in the tree, mapped to the files citing it."""
    cited: dict[str, list[str]] = {}
    for root in _CITING_ROOTS:
        for path in sorted((_REPO_ROOT / root).rglob("*")):
            if not path.is_file() or path.suffix not in {".py", ".md", ".yml", ".yaml", ".toml"}:
                continue
            if path in {_ARCHIVE, _QUEUE}:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            for identifier in set(_CITATION.findall(text)):
                cited.setdefault(f"L{identifier}", []).append(str(path.relative_to(_REPO_ROOT)))
    return cited


def test_every_cited_lesson_id_exists() -> None:
    """`docs/lessons.md` `L8.21` — an id written by hand is unchecked in three ways.

    It can **collide** with one already minted (the two tests above), it can **dangle** — name a
    lesson nothing holds — which is this one, and it can be **mis-aimed**: a live id whose entry
    says something other than what the citing sentence claims. The third is not mechanically
    checkable and is stated here rather than pretended away; it is also the one that actually
    happened alongside the collision, four sites citing `L6.29` (waiver liveness) for a sweep that
    could not cross a line break, which is `L6.16`. Both were repaired at Phase 8's drain.
    """
    known = set(_archived_ids()) | set(_QUEUE_HEADING.findall(_QUEUE.read_text(encoding="utf-8")))
    dangling = {
        identifier: sorted(files)
        for identifier, files in _cited_ids().items()
        if identifier not in known and identifier not in _PLANTED_IDS
    }
    assert not dangling, (
        f"these lesson ids are cited and neither docs/lessons-archive.md nor docs/lessons.md's "
        f"Queue holds them: {dangling}. A citation nobody can follow is the loop's memory failing "
        f"silently, which is the whole thing lessons-archive.md exists to prevent."
    )


def test_the_citation_sweep_is_not_vacuous() -> None:
    # `docs/lessons.md` L5.19. A sweep matching nothing passes identically to one finding nothing.
    cited = _cited_ids()
    assert len(cited) > 50, f"only {len(cited)} lesson ids found cited across the tree"
    assert "L6.16" in cited, "the sweep does not see the id whose mis-citation motivated this check"

    # And the plant set is live: every id in it must actually be absent from the archive, or the
    # exemption is quietly covering a real id.
    known = set(_archived_ids()) | set(_QUEUE_HEADING.findall(_QUEUE.read_text(encoding="utf-8")))
    assert not (_PLANTED_IDS & known), (
        f"_PLANTED_IDS names ids the loop actually holds: {sorted(_PLANTED_IDS & known)}"
    )


def test_no_drain_records_an_entry_in_a_form_the_parser_cannot_read() -> None:
    """`docs/lessons.md` `L8.22` — the archive has exactly one entry form, and this is why.

    `test_the_parser_sees_every_entry_that_is_written_down` above compares `parse()`'s output
    against `_BULLET`, which is a regex for **the same format the parser reads**. Both sides come
    from one source, so it cannot see an entry written any other way — the precise defect this
    module's own docstring says it was built to avoid, reproduced one format later. The 2026-09-05
    drain wrote 21 dispositions as a Markdown table; they parsed to nothing, took their `refines`
    and `reverses` edges with them, and the count went *down* with nothing said.

    A count cannot catch that, because the missing entries were never in either total. A structural
    rule can: **a disposition is a `- **Lx.y**` bullet, and nothing else**, so any other id-bearing
    shape is a failure at the moment it is written rather than a silence a later drain inherits.
    """
    rows = sorted(set(_TABLE_ROW_ENTRY.findall(_outside_the_format_example())))
    assert not rows, (
        f"docs/lessons-archive.md records these entries as table rows: {rows}. "
        f"scripts/lessons_graph.py reads `- **Lx.y** ...` bullets only, so a row is an entry the "
        f"oscillation check cannot see, and an edge the next drain cannot follow. Use bullets."
    )


def test_the_form_rule_can_actually_fail() -> None:
    # Plant the exact shape, through the same matcher.
    assert _TABLE_ROW_ENTRY.findall("| `L7.1` | Applied — somewhere |") == ["L7.1"]
    assert not _TABLE_ROW_ENTRY.findall("- **L7.1** Applied — somewhere")
