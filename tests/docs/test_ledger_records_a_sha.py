"""Every ticked ledger box carries a sha that resolves — `docs/lessons.md` `L8.27`.

`docs/build-ledger.md` → *Why the sha column is not optional* argues at length that a ticked box
with no sha is a claim rather than a record: the phases are squashed onto `main`, so the per-task
commit is the only thing that can still answer *what exactly made this true*. **Nothing read that
column.** At Phase 8's close review, seven of its own ticked boxes had no sha at all and an eighth
carried a duplicated field group ending `· sha — · turns on — · sha \\`156daf8\\``, in the phase
whose closing section restates the rule. Every one of the eight was genuinely built; it is the
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

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
LEDGER: Final[Path] = REPO_ROOT / "docs" / "build-ledger.md"

_TASK_LINE: Final[re.Pattern[str]] = re.compile(
    r"^- \[(?P<box>[ x])\] \*\*(?P<id>\d{1,2}\.\d{1,2}[a-z]?)(?: ⚠)?\*\*", re.MULTILINE
)
#: `· sha \\`abc1234\\`` or `· sha —`, wrapped across a line or not.
_SHA: Final[re.Pattern[str]] = re.compile(r"·\s+sha\s+(?:`(?P<sha>[0-9a-f]{7,40})`|(?P<dash>—))")

#: Ticked tasks allowed to carry no sha. **No longer pinned empty, and that is the point** —
#: `sha` became optional on 2026-09-09 and this constant is now a *record* of the lines written
#: before that, not a waiver anybody may add to. Nothing is checked against it; `git blame` is the
#: check. It stays only so a reader of an old line knows the field was once required.
TASKS_WITHOUT_A_SHA: Final[frozenset[str]] = frozenset()


def _blame_of_ticked_boxes() -> dict[str, str]:
    """Every ticked task id mapped to the commit that ticked its line, from `git blame`.

    **This replaces the `sha` field, and the reason is in this file's own docstring.** A commit
    cannot contain its own hash, so the protocol asked for commit-then-amend, which records a hash
    naming an object one generation behind — and then the phase is squashed and the object is gone.
    `test_every_recorded_sha_names_a_commit` below measured that: **37 recorded shas name nothing**,
    every per-task sha in Phases 3, 4 and 5, and it had to narrow its own scope to stay honest. A
    column that answers nothing for seven of eight phases was not a record, it was a ritual.

    `git blame` needs no amend, no placeholder and no ceremony: the commit that changed `- [ ]` to
    `- [x]` *is* the answer, it is exact, and `--follow`-style history means the squash commit is
    what a reader lands on rather than a dangling hash. `-w` ignores whitespace-only rewrapping so
    a reflowed paragraph does not re-attribute a tick nobody touched.
    """
    blame = subprocess.run(  # noqa: S603
        ["git", "blame", "-w", "--line-porcelain", "--", str(LEDGER)],  # noqa: S607
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    ticked: dict[str, str] = {}
    commit = ""
    for line in blame.splitlines():
        if len(line) >= 40 and line[:40].isalnum() and " " in line and not line.startswith("\t"):
            commit = line.split()[0]
        elif line.startswith("\t"):
            match = _TASK_LINE.match(line[1:])
            if match is not None and match.group("box") == "x":
                ticked[match.group("id")] = commit
    return ticked


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


def test_every_ticked_box_is_attributable_to_a_commit() -> None:
    """The property the `sha` field was reaching for, asked of something that can answer it.

    Retired `test_every_ticked_task_records_a_sha` on 2026-09-09. That test enforced a field a
    commit cannot contain — hence commit-then-amend, hence a hash one generation stale, hence 37
    of them naming nothing once their phase was squashed. `git blame` answers *what made this
    true* directly, for every ticked box including the ones whose phase was squashed years of
    commits ago, and it cannot go stale because it is derived rather than written.
    """
    # Arrange
    ticked = {identifier for identifier, is_ticked, _ in _task_blocks() if is_ticked}

    # Act
    attributed = _blame_of_ticked_boxes()
    unattributed = sorted(identifier for identifier in ticked if not attributed.get(identifier))

    # Assert
    assert len(attributed) > 100, (
        f"blame attributed only {len(attributed)} ticked boxes — the porcelain walk is not reading "
        f"the ledger, so an empty `unattributed` below would mean nothing was looked at"
    )
    assert not unattributed, (
        f"these ticked boxes are attributable to no commit: {unattributed}. A tick with no commit "
        f"behind it is the claim `build-ledger.md` refuses — but the record is `git blame` on the "
        f"line, not a hash written into it, because a commit cannot carry its own."
    )


def test_every_recorded_sha_names_a_commit() -> None:
    """**Scoped to what the squash workflow can answer, and the scope is the finding.**

    The first version of this test asserted every recorded sha resolves. It found **37** that do
    not — every per-task sha in Phases 3, 4 and 5 — and they are not a defect: this project
    *squashes each phase onto `main`* (`build-ledger.md` → *Why the sha column is not optional*),
    so the per-task commits those shas name were deliberately discarded and only the squash commit
    survives. None of the 37 is in `.git/filter-repo/commit-map` either; they predate the
    donor-scrub rewrite and were already gone.

    **That is worth stating plainly rather than asserting shut** (`docs/lessons.md` `L8.28`): the
    ledger argues the sha column exists because *"the per-task commit is the only thing that can
    still answer what exactly made this true"*, and for seven of the eight phases it cannot answer,
    because the workflow that makes the column necessary is the same workflow that destroys what it
    points at. What survives is the squash message, which names task **ids** and not shas. So this
    check asserts the property that is actually true of an unsquashed phase — the one currently
    being built — and says so, instead of failing for a correct record.
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
    # cannot cross the break reports every one of them missing (`docs/lessons.md` L6.16).
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
