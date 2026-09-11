"""Every path a workflow file references is a tracked file — ledger task **8.19**.

`docs/internal/lessons-archive.md` `L7.2`. `uv.lock` sat in `.gitignore` for eight phases, so the
gate a developer ran (against whatever their environment had resolved to) and the gate CI runs
(against a clean checkout) were two different gates, and **nothing could have noticed** — CI passed,
the local run passed, and neither was evidence about the other. The repair tracked the lockfile;
this is the check that would have caught it, and that catches the next file a workflow depends on
and this repository does not carry.

**Why what already exists does not cover it.** `test_sdist_completeness.py` and
`test_isolated_installs.py` both read `.github/workflows/ci.yml`, and both ask whether it *invokes*
a particular `poe` task. Neither asks whether the paths it names resolve. Those are different
questions and only one of them was ever answered.

**Scope, deliberately narrow.** This reads path-shaped tokens out of the workflow files and asks
whether each is tracked. It does not model YAML semantics, shell quoting or `${{ }}` expressions —
a workflow is a shell script wearing a schema, and a checker pretending otherwise would assert
things it cannot know. The population is tokens shaped like a repository-relative path to a file
with a suffix, minus URLs, action references (`owner/repo@ref`), globs, interpolations, and output
directories the job creates rather than carries. Anything it cannot classify it skips — and
`test_the_check_can_actually_fail` proves the classifier still fires on a real one.

Tracked files come from `conftest.tracked_files()`, which is `git ls-files` and not a directory walk
(`docs/internal/lessons.md` L8.8). That helper was consolidated there when this check would
otherwise have been the third copy of the same six lines.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final

from tests.conftest import UNTRACKED_BY_DESIGN

from .conftest import REPO_ROOT, tracked_files

WORKFLOWS: Final[Path] = REPO_ROOT / ".github" / "workflows"

#: A repository-relative path to a file: at least one `/`, and a suffix. Deliberately
#: over-inclusive on shape and filtered below — a false positive costs one waiver entry and a
#: false negative costs the defect this file exists for, so the asymmetry decides the tuning.
_PATHISH: Final[re.Pattern[str]] = re.compile(
    r"(?<![\w@/.-])(?P<path>(?:\./)?[\w.-]+(?:/[\w.-]+)+\.[A-Za-z0-9]+)"
)

#: Substrings marking a token as something other than a path this repository could track.
_NOT_A_REPO_PATH: Final[tuple[str, ...]] = ("${{", "://", "*", "$(", "~")

#: Directories a build tool creates without an explicit `mkdir`, by its own convention —
#: `uv build --out-dir dist` and the docs builder. Two entries, and hand-maintained on purpose:
#: nothing in the workflow text names them as created, so there is nothing to derive them from.
#: Every *other* job-created directory is derived by `_job_created_prefixes` below rather than
#: listed here, because a hand-maintained set of "ignore these" is the shape that silently grows
#: until the check stops looking at anything (`docs/internal/lessons.md` L8.12).
_BUILD_TOOL_OUTPUT: Final[tuple[str, ...]] = ("dist/", "site/")

#: `mkdir -p reproduction` and friends — a directory the workflow states it is creating.
_MKDIR: Final[re.Pattern[str]] = re.compile(r"\bmkdir\s+(?:-p\s+)?(?P<dir>[\w./-]+)")

#: Workflow paths permitted not to be tracked. **Pinned empty.** An entry says a workflow depends
#: on something this repository does not carry, which is `L7.2`'s defect written down rather than
#: fixed — a visible act in a diff, never a silent edit.
UNTRACKED_WORKFLOW_PATHS_WAIVED: Final[frozenset[str]] = frozenset()

#: The eight files under `docs/internal/`. **An allowance, not a waiver**: `ci.yml` and
#: `release.yml` name `docs/internal/lessons.md` and `docs/internal/lessons-archive.md`, and every
#: occurrence — checked by hand, 2026-09-11 — is inside a `#` comment or an `echo` message citing a
#: lesson id, never a `run:` step that reads the file. No workflow depends on any of the eight at
#: runtime, so this is not `L7.2`'s defect. A path to any other untracked file still fails.
_UNTRACKED_WORKFLOW_CITATIONS: Final[frozenset[str]] = UNTRACKED_BY_DESIGN


def _job_created_prefixes(text: str) -> frozenset[str]:
    """Every directory `text` says it creates, as a `prefix/`.

    Derived from the workflow's own `mkdir` lines rather than listed by hand: the release job
    assembles a `reproduction/` directory and copies tracked files into it, so paths under it
    are outputs, not dependencies — and the *sources* of those copies (`corpus/manifest.toml`,
    `eval/baselines`) are still checked, which is the half that matters.
    """
    return frozenset(
        match.group("dir").removeprefix("./").rstrip("/") + "/" for match in _MKDIR.finditer(text)
    )


def _workflow_files() -> tuple[Path, ...]:
    return tuple(sorted(WORKFLOWS.glob("*.yml")) + sorted(WORKFLOWS.glob("*.yaml")))


def referenced_paths(text: str) -> frozenset[str]:
    """Every repository-relative file path `text` names, without a leading `./`.

    Public rather than private so `test_the_check_can_actually_fail` can exercise the classifier
    directly on a planted line. The classifier is the part that can silently stop matching, and a
    self-test that only ran the whole check would not see that happen (`docs/internal/lessons.md`
    L6.29).
    """
    created = frozenset(_BUILD_TOOL_OUTPUT) | _job_created_prefixes(text)
    found: set[str] = set()
    for match in _PATHISH.finditer(text):
        token = match.group("path")
        if any(marker in token for marker in _NOT_A_REPO_PATH):
            continue
        normalised = token.removeprefix("./")
        if any(normalised.startswith(prefix) for prefix in created):
            continue
        found.add(normalised)
    return frozenset(found)


def test_every_path_a_workflow_names_is_tracked() -> None:
    # Arrange
    tracked = tracked_files()

    # Act
    missing: dict[str, list[str]] = {}
    for workflow in _workflow_files():
        absent = sorted(
            path
            for path in referenced_paths(workflow.read_text(encoding="utf-8"))
            if path not in tracked
            and path not in UNTRACKED_WORKFLOW_PATHS_WAIVED
            and path not in _UNTRACKED_WORKFLOW_CITATIONS
        )
        if absent:
            missing[workflow.relative_to(REPO_ROOT).as_posix()] = absent

    # Assert
    assert not missing, (
        f"these workflow files name paths this repository does not track: {missing}. A workflow "
        f"depending on a file only some checkouts have is how the gate a developer runs and the "
        f"gate CI runs become two different gates with nothing able to notice — an untracked "
        f"'uv.lock' did exactly that for eight phases (lessons-archive L7.2). Track the file, or "
        f"name it in UNTRACKED_WORKFLOW_PATHS_WAIVED and say why."
    )


def test_the_walk_found_the_workflows_and_read_paths_out_of_them() -> None:
    # `docs/internal/lessons.md` L5.19: a sweep over an empty population passes while looking at
    # nothing, and the green is identical either way. Both halves: that there are workflow files,
    # and that the classifier actually pulled paths out of them.
    workflows = _workflow_files()
    assert workflows, f"no workflow files found under {WORKFLOWS} — the check read nothing"

    everything: frozenset[str] = frozenset()
    for workflow in workflows:
        everything |= referenced_paths(workflow.read_text(encoding="utf-8"))
    assert everything, (
        "the classifier found no repository paths in any workflow file, so the check above would "
        "pass by matching nothing"
    )


def test_the_check_can_actually_fail() -> None:
    # Plant the exact shape: a workflow line naming a file this repository does not carry.
    # `L7.2`'s defect was a path that resolved on one machine and nowhere else, so the planted
    # case is one that resolves nowhere.
    planted = "      - run: uv run --frozen --locked pytest -c config/no_such_file.toml\n"

    found = referenced_paths(planted)

    assert "config/no_such_file.toml" in found, (
        "the classifier does not fire on a workflow line naming an untracked path, so a green "
        "from test_every_path_a_workflow_names_is_tracked would mean nothing is being looked at"
    )
    assert "config/no_such_file.toml" not in tracked_files()
