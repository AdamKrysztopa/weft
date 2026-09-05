"""Fitness function 0 — the gate must be in the gate.

Every architecture check runs inside the composite task the documentation calls
canonical, and this test asserts that membership.

It exists because a 316-line hexagonal boundary checker can be written, committed, and
never wired into the composite the documentation calls the canonical full gate: the
composite a project's own `CLAUDE.md` calls that can resolve to a task that omits the
checker, and a `.pre-commit-config.yaml` can omit it too. A fitness function that is not
wired into the canonical task is not a fitness function.

The waiver constant below is a named escape hatch pinned empty, so a waiver is a visible
act in a diff rather than a silent edit to a script nobody reads. The constant, its shape
and the gate it guards are Weft's own. It is pinned empty.
"""

from pathlib import Path
from typing import Final, cast

from .conftest import str_list_at, table_at

CANONICAL_GATE: Final[str] = "ci-checks"

#: Architecture checks permitted to sit outside the canonical gate.
#: **Pinned empty.** A check outside the gate does not run, and a check that does
#: not run is documentation. If you believe you need an entry here, the honest
#: options are to fix the check or to delete it.
CHECKS_WAIVED_FROM_GATE: Final[frozenset[str]] = frozenset()

#: Tasks that constitute the architecture checks. Every one must be reachable
#: from the canonical gate.
ARCHITECTURE_TASKS: Final[frozenset[str]] = frozenset({"arch"})

_REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]

#: Directories the tree-wide suite sweep never descends into — not waivers, and not test
#: suites this project owns. The entry below excludes the untracked symlink `CLAUDE.md`
#: documents as a different, unversioned repository nothing here may read through.
#: `worktrees` is `.claude/worktrees/`, where
#: `git worktree` checkouts of *this* repository live: a suite found in one is the same suite
#: this gate already runs, at a different commit, and counting it would make the gate's
#: coverage depend on which branches happen to be checked out on a developer's machine.
#: The rest are build and environment output.
_NOT_OURS: Final[frozenset[str]] = frozenset(
    {
        ".venv",
        ".git",
        "_external-src",
        "_external-reading",
        "worktrees",
        "node_modules",
        "__pycache__",
        "dist",
        "build",
        ".ruff_cache",
    }
)

#: Test suites permitted to sit outside the canonical gate — **the second ratchet**, added
#: 2026-08-22 by the drain of `docs/lessons.md` L6.12.
#:
#: A directory of tests no task runs is prose, exactly as a documented check no task runs is
#: prose — this fitness function's own subject, one level up from the check to the suite. It was
#: found the hard way: six example packs each ship a test suite, `testpaths = ["tests"]` meant
#: `poe ci-checks` had never executed one of them, and two of `examples/weft-example-graph`'s
#: twelve were quietly red for it.
#:
#: **Empty since 2026-08-25, ledger task 6.23.** All seven suites — 116 tests — run in the gate
#: through the `examples-tests` step, which exists as its own task because an example pack is
#: deliberately not a workspace member (fitness function 9(a)) and so needs its `src/` put on
#: `sys.path` explicitly, and because several packs name a test file the same thing.
#: `_covered_roots` above was widened in the same commit to read every pytest step of the gate
#: rather than the `test` task alone — without that it could not have seen the new step, and
#: these entries would have stayed here while the suites were already running. **Nothing may be
#: added here without a task that empties it.**
SUITES_WAIVED_FROM_GATE: Final[frozenset[str]] = frozenset()


def _suite_directories() -> frozenset[str]:
    """Every directory in this repository that actually holds tests, repo-relative.

    Read off the filesystem rather than off any list, for the same reason the check above
    reads the gate's own `sequence` rather than a second copy of it: the two sides have to be
    able to disagree (`docs/lessons.md` L5.6). A suite added under a directory nobody thought
    to list is exactly the failure this clause exists to catch.
    """
    found: set[str] = set()
    for path in _REPO_ROOT.rglob("test_*.py"):
        if any(part in _NOT_OURS for part in path.relative_to(_REPO_ROOT).parts):
            continue
        found.add(path.parent.relative_to(_REPO_ROOT).as_posix())
    return frozenset(found)


def _covered_roots(workspace_config: dict[str, object]) -> tuple[str, ...]:
    """Every path any step of the canonical gate hands to `pytest`.

    **Read across the whole sequence, not off one task.** It used to read `test` alone, which was
    true while the gate had exactly one pytest step and became a hole the moment ledger task 6.23
    added `examples-tests` for the out-of-tree packs' own suites: the new task really did cover
    `examples/*/tests`, and this function could not see it, so the suites would have stayed waived
    while actually running. That is this fitness function's own subject — the gate must be in the
    gate — aimed at itself, and the fix is to ask the composite rather than a member of it.

    A task may be a plain `cmd` string or a table carrying one (`examples-tests` is a table,
    because it also needs `env`), so both shapes are read.
    """
    tasks = table_at(workspace_config, "tool", "poe", "tasks")
    gate = table_at(workspace_config, "tool", "poe", "tasks", CANONICAL_GATE)
    roots: list[str] = []

    for step in str_list_at(gate, "sequence"):
        task = tasks.get(step)
        command = task if isinstance(task, str) else None
        if command is None and isinstance(task, dict):
            found = cast("dict[str, object]", task).get("cmd")
            command = found if isinstance(found, str) else None
        if command is None or "pytest" not in command:
            continue
        roots.extend(
            word
            for word in command.split()
            if not word.startswith("-") and word != "pytest" and "=" not in word
        )
    return tuple(roots)


def test_waiver_list_is_empty() -> None:
    assert not CHECKS_WAIVED_FROM_GATE, (
        "A check has been waived out of the canonical gate. The waiver policy is that "
        "there is no waiver policy: a check outside the gate does not run. Fix it or "
        "delete it, but do not park it here."
    )


def test_canonical_gate_exists(workspace_config: dict[str, object]) -> None:
    tasks = table_at(workspace_config, "tool", "poe", "tasks")

    assert CANONICAL_GATE in tasks, (
        f"The canonical gate '{CANONICAL_GATE}' is not defined. Fitness function 0 has "
        f"nothing to check membership against, which is exactly the failure this function "
        f"exists to catch."
    )


def test_every_architecture_check_runs_in_the_canonical_gate(
    workspace_config: dict[str, object],
) -> None:
    gate = table_at(workspace_config, "tool", "poe", "tasks", CANONICAL_GATE)

    missing = ARCHITECTURE_TASKS - CHECKS_WAIVED_FROM_GATE - set(str_list_at(gate, "sequence"))

    assert not missing, (
        f"Architecture checks {sorted(missing)} are not in '{CANONICAL_GATE}'. They will "
        f"not run in CI, and a check that does not run in CI can pass silently no matter "
        f"how many real violations sit underneath it."
    )


def test_suite_waiver_list_is_declared_not_discovered() -> None:
    """Every waived suite must still be **found by the sweep** — not merely exist on disk.

    A waiver naming a directory that is gone is a waiver nobody will ever remove, and it makes
    the ratchet read shorter than it is. But that was the whole of this check until 2026-08-25,
    and `docs/lessons.md` **L6.29** is why it is not enough: a waiver-liveness test that asks
    whether the waived *thing* exists, rather than whether the *sweep finds it*, passes exactly
    as happily when the sweep has stopped finding anything at all. That is not hypothetical —
    task 6.9 shipped a check whose prose sweep matched nothing in the entire shipped
    documentation set, with its own liveness test green, and it was found only by emptying the
    waiver. `_suite_directories()` walks `rglob("test_*.py")` and prunes by name; a pruning list
    that grew one entry too many would silently empty it, and every waived suite would still be
    a directory on disk.
    """
    # Act
    swept = _suite_directories()
    unfound = {name for name in SUITES_WAIVED_FROM_GATE if name not in swept}

    # Assert
    assert swept, "the suite sweep found nothing at all — the walk is broken, not the tree"
    assert unfound == set(), (
        f"{sorted(unfound)} is waived out of the gate and the sweep does not find it. Either the "
        f"directory is gone — delete the entry, since task 6.23 empties this constant and a stale "
        f"name makes that look already done — or the sweep has stopped seeing it, in which case "
        f"the waiver is hiding that the suite check may now be looking at nothing."
    )


def test_every_test_suite_in_the_tree_runs_in_the_canonical_gate(
    workspace_config: dict[str, object],
) -> None:
    """Fitness function 0, one level up: the gate must reach every *suite*, not only every
    *check*. `docs/lessons.md` L6.12 — a directory of tests no task runs is prose.
    """
    # Act
    covered = _covered_roots(workspace_config)
    unreached = {
        suite
        for suite in _suite_directories()
        if not any(suite == root or suite.startswith(f"{root}/") for root in covered)
    } - SUITES_WAIVED_FROM_GATE

    # Assert
    assert unreached == set(), (
        f"{sorted(unreached)} holds tests that '{CANONICAL_GATE}' never runs. A suite outside "
        f"the gate does not run, and a suite that does not run is prose — the identical "
        f"argument this file makes about a check, one level up. Add it to the gate's test "
        f"task, or name it in SUITES_WAIVED_FROM_GATE with a task that empties it."
    )


def test_the_check_can_actually_fail() -> None:
    """Fitness function 16 clause (b) — ledger task **6.15**.

    This file predates FF16 and was one of the seven waived in `CHECKS_WITHOUT_A_SELF_TEST`.
    Both of its comparisons pass against the real tree and have since Phase 0, so this is the
    only place either is seen disagreeing — which is the whole point: a check that has never
    been observed failing is indistinguishable from one that cannot (`docs/lessons.md` L5.6,
    L5.19).

    Planted through the **real helpers**, never against hand-written sets. A self-test that
    asserted `{"arch"} - set() == {"arch"}` would prove that `frozenset.__sub__` works.
    """
    # Arrange — a workspace whose canonical gate forgot `arch`, and whose test task reaches
    # `tests` only, while a suite lives somewhere else entirely.
    forgetful: dict[str, object] = {
        "tool": {
            "poe": {
                "tasks": {
                    "test": "pytest tests -q",
                    CANONICAL_GATE: {"sequence": ["fmt", "lint", "types", "test"]},
                }
            }
        }
    }
    suites = frozenset({"tests/architecture", "examples/weft-example-chunker/tests"})

    # Act — the same two expressions the two checks above compute.
    gate = table_at(forgetful, "tool", "poe", "tasks", CANONICAL_GATE)
    missing = ARCHITECTURE_TASKS - CHECKS_WAIVED_FROM_GATE - set(str_list_at(gate, "sequence"))
    covered = _covered_roots(forgetful)
    unreached = {
        suite
        for suite in suites
        if not any(suite == root or suite.startswith(f"{root}/") for root in covered)
    }

    # Assert
    assert missing == {"arch"}
    assert covered == ("tests",)
    assert unreached == {"examples/weft-example-chunker/tests"}
