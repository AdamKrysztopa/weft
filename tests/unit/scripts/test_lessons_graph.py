"""Unit tests for `scripts/lessons_graph.py` — carried repair **R9.12**.

Mirrors the script. Its subject is the *edges between lessons*: `recurs`, `reverses`, `refines`.
Until this repair it read `docs/internal/lessons-archive.md` alone, so a recurrence became visible
only once the entry stating it had been **drained** — and a drain is exactly when somebody is
deciding what a phase learned. The phase whose queue is densest with recurrences is the one the
detector could say least about (`docs/internal/lessons.md` `L9.91`); Phase 9's own drain found
**six** recurrences inside Phase 9 that the script could not see, every one stated in the entries'
own prose.
"""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Final, cast

import pytest

from tests.conftest import untracked_reason

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import lessons_graph  # noqa: E402 — the script is not a package; the path above is how it loads

QUEUE: Final[Path] = REPO_ROOT / "docs" / "internal" / "lessons.md"

#: Untracked by design (`tests.conftest.UNTRACKED_BY_DESIGN`) — absent from a clean checkout.
_MISSING_QUEUE: Final[str | None] = untracked_reason("docs/internal/lessons.md")
_requires_queue = pytest.mark.skipif(_MISSING_QUEUE is not None, reason=_MISSING_QUEUE or "")


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
    # Arrange — `docs/internal/lessons.md` carries an *Applied* section and a closing note as well
    # as the queue, and both mention lesson ids. Only the queue's own entries are open lessons;
    # reading the rest would report an applied rule as an unresolved recurrence, which is the
    # opposite of what this script is for.
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


@_requires_queue
def test_the_live_queue_is_readable_by_this_parser() -> None:
    """`lessons_graph` and the `SessionStart` hook read the same entries out of the same file.

    **This asserted `entries` was non-empty until 2026-09-11, which made it fail at the one
    moment it mattered.** `implement-ll` drains the queue to empty and empty is the healthy
    state, so the check went red on the commit that did the draining — and its own message had
    predicted exactly that (*"either the queue is genuinely empty… or the entry form changed"*)
    while leaving the two cases indistinguishable, which is the defect rather than a note about
    it.

    **The first repair was worse and is worth recording.** It compared the parser against a
    "naive" scan written inside this test — which bounded the Queue section the same way the
    parser does, so the two sides came from one source and a planted moved-heading changed both
    at once and fired nothing. `L5.6`, in a test written during the drain that archived four
    entries about `L5.6`.

    The two sides here are two real implementations, in two files, written for different jobs:
    `scripts/lessons_graph.py` builds the edge graph, and `.claude/hooks/lessons_context.py`
    injects the queue into every session. `lessons_graph`'s own entry-regex comment already says
    these two *"cannot disagree about what an entry is"* — this is what makes that a fact. Both
    reading zero is a real agreement, not a vacuous one: either file's section logic could break
    while the other's held, which is the drift this exists to catch.
    """
    # Arrange — load the hook by path. It runs under bare `python3` and is not importable as a
    # package, which is why this goes through `importlib` rather than an import statement.
    hook_path = Path(__file__).resolve().parents[3] / ".claude" / "hooks" / "lessons_context.py"
    spec = importlib.util.spec_from_file_location("lessons_context_probe", hook_path)
    assert spec is not None and spec.loader is not None, f"could not load {hook_path}"
    hook = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hook)
    text = QUEUE.read_text(encoding="utf-8")

    # Act
    entries, _edges = lessons_graph.parse_queue(text)
    by_the_hook = [identifier for identifier, _title in _queued_entries(hook)(text)]

    # Assert
    assert sorted(entries) == sorted(by_the_hook), (
        f"scripts/lessons_graph.py read {sorted(entries)} out of docs/internal/lessons.md's Queue "
        f"and"
        f".claude/hooks/lessons_context.py read {sorted(by_the_hook)} from the same file — one "
        f"of the two followed a change to the queue's heading or entry form and the other did not"
    )
    assert all(identifier.startswith("L") for identifier in entries)


def _queued_entries(hook: ModuleType) -> Callable[[str], list[tuple[str, str]]]:
    """The hook's own `_queued_entries`, fetched with its name as a parameter.

    A literal private attribute access trips `pyright`'s `reportPrivateUsage` and a literal
    `getattr` trips `ruff`'s `B009`; passing the name through a variable satisfies both while
    leaving the reach visible, which is this tree's idiom for reading into a module deliberately.
    """
    return cast("Callable[[str], list[tuple[str, str]]]", hook._queued_entries)
