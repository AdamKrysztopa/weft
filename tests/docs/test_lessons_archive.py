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
