"""Unit tests for `scripts/lessons_graph.py` — carried repair **R9.12**.

Mirrors the script. Its subject is the *edges between lessons*: `recurs`, `reverses`,
`refines`. Until this repair it read `docs/lessons-archive.md` alone, so a recurrence became
visible only once the entry stating it had been **drained** — and a drain is exactly when
somebody is deciding what a phase learned. The phase whose queue is densest with recurrences is
the one the detector could say least about (`docs/lessons.md` `L9.91`); Phase 9's own drain found
**six** recurrences inside Phase 9 that the script could not see, every one stated in the
entries' own prose.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Final

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import lessons_graph  # noqa: E402 — the script is not a package; the path above is how it loads

QUEUE: Final[Path] = REPO_ROOT / "docs" / "lessons.md"


def test_an_open_queue_entry_and_its_edges_are_read() -> None:
    # Arrange — the queue's entries are `### L12.5 — title` headings with the edge stated
    # anywhere in the body, where the archive's are `- **L12.5** …` bullets. Two shapes, one
    # vocabulary; the script has to read both or the detector is blind for exactly as long as
    # the entry is open, which is the whole window in which it would be useful.
    text = """## Queue

### L12.5 — a brief named none of the sites keyed on exception identity

**What happened.** Something happened. This is `recurs L8.12`'s fifth instance.

**Generalises to.** A rule.

### L12.6 — six single-row fixtures

**What happened.** `refines L11.42` one level down.

## When the queue is empty
"""

    # Act
    entries, edges = lessons_graph.parse_queue(text)

    # Assert
    assert set(entries) == {"L12.5", "L12.6"}
    assert ("L12.5", "recurs", "L8.12") in edges
    assert ("L12.6", "refines", "L11.42") in edges


def test_nothing_after_the_queue_section_is_read_as_an_entry() -> None:
    # Arrange — `docs/lessons.md` carries an *Applied* section and a closing note as well as the
    # queue, and both mention lesson ids. Only the queue's own entries are open lessons; reading
    # the rest would report an applied rule as an unresolved recurrence, which is the opposite
    # of what this script is for.
    text = """## Applied

- **L9.91** something already applied, mentioning `recurs L5.1`.

## Queue

### L12.1 — the open one

Body with `refines L7.2`.

## When the queue is empty

A closing note naming `L9.91` again.
"""

    entries, edges = lessons_graph.parse_queue(text)

    assert set(entries) == {"L12.1"}
    assert edges == [("L12.1", "refines", "L7.2")]


def test_the_live_queue_is_readable_by_this_parser() -> None:
    # The floor, and it is about the real file rather than a fixture: a parser that agrees with
    # its own examples and not with `docs/lessons.md` is the shape `R11.7` was filed for one
    # document over. An empty reading here means the queue's heading or entry form moved.
    entries, _edges = lessons_graph.parse_queue(QUEUE.read_text(encoding="utf-8"))

    assert entries, (
        "no open entry was read out of docs/lessons.md. Either the queue is genuinely empty — "
        "in which case this check has no subject and should be looked at — or the entry form "
        "changed and the parser did not."
    )
    assert all(identifier.startswith("L") for identifier in entries)
