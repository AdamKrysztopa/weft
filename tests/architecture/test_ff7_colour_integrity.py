"""Fitness function 7(a) — colour integrity, clause (a): one bridge.

`docs/01-high-level-plan.md` → *Fitness functions*: "`asyncio.run` appears
exactly once in the tree, at `weft-cli`'s entry point, asserted by path — so
a second one fails the build rather than being noticed in review. This
exists because the reference's single bridge was safe only by docstring."
`docs/06-phase-0-build.md` step 9 activates this clause.

Found by an AST walk over the **whole repository** — not just `packages/*`
and `testing/*`, which would leave a second bridge under `tests/`,
`scripts/`, or an example pack such as step 10's `examples/weft-example-chunker/`
free to hide unseen — for a call whose callee resolves to `asyncio.run`,
however it was imported (`import asyncio; asyncio.run(...)` or `from asyncio
import run; run(...)`), rather than a text `grep` for the string
`"asyncio.run"`, which a docstring quoting the phrase (this repository has
several) would falsely trip.

The walk excludes only non-source directories (`.venv`, `.git`, build
artefacts, and any other dot-directory) and never follows a symlink —
`os.walk`'s own default — so the untracked `reference` symlink at the repository
root (`CLAUDE.md`: "a different repository, not under version control...
Nothing in Weft's build, tests or packaging may even *read* through it") is
listed but never descended into.

Clause 7(b) — the categorical blocking-call detector — is not this file's
subject: it already has somewhere to live per `docs/06-phase-0-build.md`
step 3, and its mechanism is unit-tested directly in
`tests/unit/weft_kernel/test_blocking.py` and `test_seam.py`. Step 9 activates
7(a) only.
"""

import ast
import os
from pathlib import Path
from typing import Final

from .conftest import REPO_ROOT

#: Directories that hold no Weft source of our own — vendored dependencies, VCS internals,
#: build/cache artefacts, and (by name, belt-and-suspenders alongside `followlinks=False`
#: below) the untracked `reference` symlink, which must never be read through at all.
_EXCLUDED_DIR_NAMES: Final[frozenset[str]] = frozenset({"dist", "build", "__pycache__", "reference"})

#: The one call site fitness function 7(a) requires — `docs/06-phase-0-build.md` step 9.
_EXPECTED_PATH: Final[Path] = REPO_ROOT / "packages" / "weft-rag" / "src" / "weft_cli" / "cli.py"


def test_asyncio_run_appears_exactly_once_at_the_cli_entry_point() -> None:
    sites = [path for path in _repository_python_files() if _calls_asyncio_run(path)]

    assert sites == [_EXPECTED_PATH], (
        f"asyncio.run() must appear exactly once in the whole tree, at "
        f"{_EXPECTED_PATH.relative_to(REPO_ROOT)}. Found it at: "
        f"{[str(site.relative_to(REPO_ROOT)) for site in sites]}. A second bridge is exactly "
        f"the reference's incident this fitness function exists to prevent — see "
        f"docs/01-high-level-plan.md -> Colour."
    )


def _repository_python_files() -> list[Path]:
    """Every `.py` file in the repository, walked with `followlinks=False`.

    `os.walk` never descends into a symlinked directory unless told to, which is what keeps
    the `reference` symlink (`../a prior project`) unread — its entry is visited (so it can be pruned
    from `dirnames` below) but never opened. Hidden directories (`.venv`, `.git`, `.ruff_cache`
    and the like) and build/cache artefacts are pruned the same way: named or dot-prefixed
    entries removed from `dirnames` before `os.walk` recurses into them, exactly the mechanism
    `os.walk`'s own docs describe for in-place pruning.
    """
    files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(REPO_ROOT, followlinks=False):
        dirnames[:] = sorted(
            name
            for name in dirnames
            if name not in _EXCLUDED_DIR_NAMES and not name.startswith(".")
        )
        files.extend(
            Path(dirpath) / filename for filename in sorted(filenames) if filename.endswith(".py")
        )
    return files


def _calls_asyncio_run(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    bound_names = _names_bound_to_asyncio_run(tree)

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        callee = node.func
        if isinstance(callee, ast.Attribute) and callee.attr == "run":
            target = callee.value
            if isinstance(target, ast.Name) and target.id in _names_bound_to_asyncio_module(tree):
                return True
        if isinstance(callee, ast.Name) and callee.id in bound_names:
            return True
    return False


def _names_bound_to_asyncio_module(tree: ast.AST) -> set[str]:
    """Every local name bound to the `asyncio` module itself — `import asyncio as aio` included."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(
                (alias.asname or alias.name) for alias in node.names if alias.name == "asyncio"
            )
    return names


def _names_bound_to_asyncio_run(tree: ast.AST) -> set[str]:
    """Every local name bound directly to `asyncio.run` — `from asyncio import run as go`."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "asyncio":
            names.update(
                (alias.asname or alias.name) for alias in node.names if alias.name == "run"
            )
    return names


def test_the_check_can_actually_fail(tmp_path: Path) -> None:
    """Fitness function 16 clause (b) — ledger task **6.15**.

    The real tree holds exactly one `asyncio.run` and has since Phase 0, so the detector has
    never been observed saying yes to anything but that one file. Planted here through the
    real `_calls_asyncio_run` in all four spellings it claims to catch, plus the two shapes
    it must *not* mistake for a bridge — because a detector that answered `True` for
    everything would also pass the check above only until someone added a second file, and
    one that answered `False` for everything would pass forever.
    """
    # Arrange — four ways to reach the same bridge, and two near-misses.
    caught = {
        "plain": "import asyncio\nasyncio.run(main())\n",
        "aliased-module": "import asyncio as aio\naio.run(main())\n",
        "from-import": "from asyncio import run\nrun(main())\n",
        "aliased-function": "from asyncio import run as go\ngo(main())\n",
    }
    ignored = {
        "someone-elses-run": "import subprocess\nsubprocess.run(['ls'])\n",
        "merely-imported": (
            "import asyncio\n\nasync def main() -> None:\n    await asyncio.sleep(0)\n"
        ),
    }

    # Act
    def verdict(source: str, name: str) -> bool:
        planted = tmp_path / f"{name}.py"
        planted.write_text(source, encoding="utf-8")
        return _calls_asyncio_run(planted)

    found = {name for name, source in caught.items() if verdict(source, name)}
    false_positives = {name for name, source in ignored.items() if verdict(source, name)}

    # Assert
    assert found == set(caught), f"the detector missed {sorted(set(caught) - found)}"
    assert false_positives == set(), (
        f"{sorted(false_positives)} is not a second event-loop bridge, and a check that says "
        f"it is would make the real assertion fail for the wrong reason."
    )


def test_the_walk_can_actually_fail() -> None:
    """The other half: a walk that returns nothing makes the assertion above vacuous.

    `sites == [_EXPECTED_PATH]` is not vacuous the way an emptiness check would be — an empty
    walk fails it rather than passing it — but the walk is still the input everything rests
    on, and `docs/lessons.md` L5.19 asks for it to be proved real rather than assumed.
    """
    # Act
    walked = _repository_python_files()

    # Assert
    assert _EXPECTED_PATH in walked, (
        f"the walk did not reach {_EXPECTED_PATH}, which is the one file that is supposed to "
        f"be found. The pruning is wrong, not the tree."
    )
    assert len(walked) > 100, "the walk reached almost nothing — it is pruning too much"
