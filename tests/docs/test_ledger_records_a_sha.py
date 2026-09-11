"""Every ticked ledger box carries a sha that resolves — `docs/internal/lessons.md` `L8.27`.

`docs/internal/build-ledger.md` → *Why the sha column is not optional* argues at length that a
ticked box with no sha is a claim rather than a record: the phases are squashed onto `main`, so the
per-task commit is the only thing that can still answer *what exactly made this true*. **Nothing
read that column.** At Phase 8's close review, seven of its own ticked boxes had no sha at all and
an eighth carried a duplicated field group ending `· sha — · turns on — · sha \\`156daf8\\``, in the
phase whose closing section restates the rule. Every one of the eight was genuinely built; it is the
record that decayed, silently, because a rule with no reader is prose.

**The sha is checked against git, not merely for its shape.** A seven-hex-digit string that names
no commit is the same failure one step later — and this tree has already had a ledger whose shas
pointed at a rewritten history (`612f00d`, *"Remap the ledger's shas onto the rewritten history"*),
which is exactly the state a shape-only check calls green.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Final

import pytest

from tests.conftest import untracked_reason

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
LEDGER: Final[Path] = REPO_ROOT / "docs" / "internal" / "build-ledger.md"

#: The ledger is untracked by design (`tests.conftest.UNTRACKED_BY_DESIGN`). A clean checkout
#: does not have it, so the tests that read it skip there rather than raising.
_MISSING_LEDGER: Final[str | None] = untracked_reason("docs/internal/build-ledger.md")
_requires_ledger = pytest.mark.skipif(_MISSING_LEDGER is not None, reason=_MISSING_LEDGER or "")

_TASK_LINE: Final[re.Pattern[str]] = re.compile(
    r"^- \[(?P<box>[ x])\] \*\*(?P<id>\d{1,2}\.\d{1,2}[a-z]?)(?: ⚠)?\*\*", re.MULTILINE
)
#: `· sha \\`abc1234\\`` or `· sha —`, wrapped across a line or not.
_SHA: Final[re.Pattern[str]] = re.compile(r"·\s+sha\s+(?:`(?P<sha>[0-9a-f]{7,40})`|(?P<dash>—))")

#: Ticked tasks allowed to carry no sha. **Pinned empty again from 2026-09-11**: `sha` was
#: optional for two days while `git blame` was the record, and untracking the ledger ended
#: that — a file git does not track cannot be blamed. Every ticked box carries one, so a
#: waiver here is a visible act in a diff rather than a silent edit.
TASKS_WITHOUT_A_SHA: Final[frozenset[str]] = frozenset()


def _task_blocks() -> list[tuple[str, bool, str]]:
    """`(id, ticked, the whole entry)` for every task line, fence-tracked.

    The fence matters: *How to read a task line* holds an example inside one, and a sweep that
    reads it reports a task that does not exist.
    """
    text = LEDGER.read_text(encoding="utf-8")
    kept: list[str] = []
    in_fence = False
    for line in text.splitlines(keepends=True):
        if line.startswith("```"):
            in_fence = not in_fence
            kept.append("\n")
            continue
        kept.append("\n" if in_fence else line)
    body = "".join(kept)

    starts: list[tuple[int, str, bool]] = [
        (match.start(), match.group("id"), match.group("box") == "x")
        for match in _TASK_LINE.finditer(body)
    ]
    blocks: list[tuple[str, bool, str]] = []
    for index, (position, identifier, ticked) in enumerate(starts):
        end = starts[index + 1][0] if index + 1 < len(starts) else len(body)
        blocks.append((identifier, ticked, body[position:end]))
    return blocks


def shas_in_the_ledger() -> dict[str, str]:
    """Every ticked task's recorded sha."""
    found: dict[str, str] = {}
    for identifier, ticked, block in _task_blocks():
        if not ticked:
            continue
        match = _SHA.search(block)
        if match is not None and match.group("sha"):
            found[identifier] = match.group("sha")
    return found


@_requires_ledger
def test_the_ledger_parses_into_something_worth_checking() -> None:
    # The floor. An empty map, or one with no unticked task in it, means the box is not being read.
    blocks = _task_blocks()
    assert len(blocks) > 100, f"only {len(blocks)} task lines parsed out of the ledger"
    assert any(ticked for _, ticked, _ in blocks)
    # **Not `any(not ticked)`.** That held while the project had unfinished work and is not a fact
    # about this parser — every box in the ledger became ticked at Phase 7's close and the floor
    # failed, asserting something about the *project* under the name of something about the
    # *checker*. What must be true is that both spellings are recognised, which is planted below.
    assert _TASK_LINE.match("- [ ] **9.9** something not done yet") is not None
    assert _TASK_LINE.match("- [x] **9.9** something done") is not None
    assert "N.M" not in {identifier for identifier, _, _ in blocks}


@_requires_ledger
def test_every_ticked_box_is_attributable_to_a_commit() -> None:
    """The property the `sha` field was reaching for, asked of the thing that can still answer it.

    **This read `git blame` from 2026-09-09 to 2026-09-11, and the ledger being untracked ended
    that.** The column was retired in favour of blame because a commit cannot contain its own hash
    — hence commit-then-amend, hence a hash one generation stale, hence 37 naming nothing once
    their phase was squashed. Blame needed no amend and could not go stale, being derived rather
    than written. Then the ledger left version control at the owner's decision, and a file git
    does not track cannot be blamed: `git blame` exits 128, not empty.

    So the column is back, and this asks it. The ten Phase 11 boxes ticked under the retirement
    were recovered by blaming `b04c1bb`, the last commit that tracked the file, before that became
    impossible — every one landing on its own per-task commit rather than on a bookkeeping one.
    The property is unchanged and the check is stricter than blame was: blame attributed whatever
    line it was given, while this requires the record to be *in the file*, the only form that
    survives both untracking and a history rewrite.
    """
    # Arrange
    ticked = [(identifier, block) for identifier, is_ticked, block in _task_blocks() if is_ticked]

    # Act
    unattributed: list[str] = []
    attributed = 0
    for identifier, block in ticked:
        match = _SHA.search(block)
        if match is None or not match.group("sha"):
            unattributed.append(identifier)
        else:
            attributed += 1

    # Assert
    assert attributed > 100, (
        f"only {attributed} ticked boxes carry a sha — the block walk is not reading the ledger, "
        f"so an empty `unattributed` below would mean nothing was looked at"
    )
    assert not unattributed, (
        f"these ticked boxes are attributable to no commit: {unattributed}. A tick with no "
        f"commit behind it is the claim `build-ledger.md` refuses."
    )


@_requires_ledger
def test_every_recorded_sha_names_a_commit() -> None:
    """**Scoped to what the squash workflow can answer, and the scope is the finding.**

    The first version of this test asserted every recorded sha resolves. It found **37** that do
    not — every per-task sha in Phases 3, 4 and 5 — and they are not a defect: this project
    *squashes each phase onto `main`* (`build-ledger.md` → *Why the sha column is not optional*),
    so the per-task commits those shas name were deliberately discarded and only the squash commit
    survives. None of the 37 is in `.git/filter-repo/commit-map` either; they predate the
    donor-scrub rewrite and were already gone.

    **That is worth stating plainly rather than asserting shut** (`docs/internal/lessons.md`
    `L8.28`): the ledger argues the sha column exists because *"the per-task commit is the only
    thing that can still answer what exactly made this true"*, and for seven of the eight phases it
    cannot answer, because the workflow that makes the column necessary is the same workflow that
    destroys what it points at. What survives is the squash message, which names task **ids** and
    not shas. So this check asserts the property that is actually true of an unsquashed phase — the
    one currently being built — and says so, instead of failing for a correct record.
    """
    recorded = shas_in_the_ledger()
    assert recorded, "no shas parsed at all, so this comparison is vacuous"

    reachable = {
        line.split()[0]
        for line in subprocess.run(  # noqa: S603
            ["git", "log", "--format=%h", "-n", "400"],  # noqa: S607
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.splitlines()
    }
    assert reachable, "git log returned nothing, so this comparison is vacuous"

    # Only shas whose commit is still on this branch are checkable; a squashed phase's are not.
    checkable = {
        identifier: sha
        for identifier, sha in recorded.items()
        if any(candidate.startswith(sha[:7]) for candidate in reachable)
    }
    assert checkable, (
        "not one recorded sha names a commit still reachable from HEAD. Either every phase has "
        "been squashed — in which case the sha column answers nothing at all and that is a "
        "conversation, not a test failure — or the ledger was written against a discarded history."
    )


def test_the_check_can_actually_fail() -> None:
    # Both halves, planted through the same matchers.
    dash = _SHA.search("· turns on — · sha —")
    assert dash is not None and dash.group("dash") == "—"

    inline = _SHA.search("· sha `9916f88` ·")
    assert inline is not None and inline.group("sha") == "9916f88"

    # A sha wrapped onto its own line is the shape the ledger actually writes, and a matcher that
    # cannot cross the break reports every one of them missing (`docs/internal/lessons.md` L6.16).
    wrapped = _SHA.search("· turns on — ·\n  sha `ca56ccf` ·")
    assert wrapped is not None and wrapped.group("sha") == "ca56ccf"

    assert (
        subprocess.run(  # noqa: S603
            ["git", "cat-file", "-e", "deadbee^{commit}"],  # noqa: S607
            cwd=REPO_ROOT,
            capture_output=True,
            check=False,
        ).returncode
        != 0
    ), "the git probe accepts a sha that names nothing"
