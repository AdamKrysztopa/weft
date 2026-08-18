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
_EXPECTED_PATH: Final[Path] = REPO_ROOT / "packages" / "weft-cli" / "src" / "weft_cli" / "cli.py"


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
