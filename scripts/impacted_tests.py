"""Run only the tests a diff can have affected — a fast local and pull-request signal.

**This is not the gate and must never be wired in as one.** `uv run poe ci-checks` is the canonical
full gate; fitness function 0 asserts every architecture check is reachable from it, and
`docs/internal/lessons-archive.md` `L7.8` is what a run that quietly stopped covering part of the
tree costs. What this buys is the minutes between making an edit and finding out it broke something
— nothing else. Every selection here is a *guess about impact*, and a guess is exactly what the gate
is not allowed to be.

**Reads a change set on stdin, one repository-relative path per line, and runs pytest in this
process.** Splitting it that way is not a style choice: a script under `scripts/` is shipped-shaped
code, `ruff`'s `S` rules apply to it in full, and every `subprocess.run` in this tree therefore
carries a `# noqa: S603`. This file needs none, because it spawns nothing — `poe test-impacted`
supplies the diff through a pipe and `pytest.main` runs the tests in-process.

**Why a package graph and not `pytest-testmon`.** testmon is the obvious alternative and it was
rejected on three counts, each about this tree specifically:

* It selects from a `.testmondata` database built by a previous full run on the same machine. A
  clean pull-request checkout has no such file, so the first CI run selects everything and every
  run after it selects against a database whose provenance nobody can see — the `L7.2` shape,
  where the gate a developer ran and the gate CI ran differ and nothing can notice.
* It tracks *Python* dependencies, by coverage. The dominant genre of test here is not an
  import-shaped one: `tests/architecture` and `tests/docs` read `git ls-files`, parse
  `pyproject.toml`, walk `docs/` and scan `.github/workflows/`. A change to
  `docs/internal/README.md` or `weft.toml.example` breaks tests that import nothing new, and
  coverage cannot see that edge. The answer below is blunt and correct instead: those two suites run
  whenever anything does.
* It does not run under `pytest-xdist`, which `poe test` now uses.

**The graph is derived, never listed.** Modules come from `packages/*/src/*` and the edges between
them from the imports written in their own source, so a new pack is seen without an edit here.

**`examples/` is deliberately not run from here.** The out-of-tree packs' own suites need their
`src/` directories on `sys.path` and `--import-mode=importlib`, both of which
`tool.poe.tasks.examples-tests` already states once; restating them would be a second copy of a
decision, and running them in a second in-process `pytest.main` would be a second session in one
interpreter. A change under `examples/` selects the whole-tree suites — which is where FF9, FF9(c)
and the Phase 3 exit criterion actually exercise those packs — and prints the one command that
runs their own tests.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Iterable, Sequence
from functools import cache
from pathlib import Path
from typing import Final

import pytest
from pydantic import BaseModel, ConfigDict

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[1]
PACKAGES_ROOT: Final[Path] = REPO_ROOT / "packages"

#: The two suites that reason about the whole checkout rather than about one module, so any
#: tracked change at all can move them. `tests/architecture` reads task definitions, distribution
#: metadata, workflow files and line counts; `tests/docs` reads the shipped documentation set
#: against the code. Neither has a "changed file" that predicts it.
WHOLE_TREE_SUITES: Final[tuple[str, ...]] = ("tests/architecture", "tests/docs")

#: Files whose change re-shapes the workspace itself — a dependency set, a task definition, the
#: container, or a root conftest every suite loads. Nothing narrower than the whole tree is honest
#: about any of them.
WHOLE_TREE_TRIGGERS: Final[tuple[str, ...]] = (
    "pyproject.toml",
    "uv.lock",
    "compose.yaml",
    "tests/conftest.py",
    "tests/discovery.py",
)

#: `from weft_store import ...` / `import weft_store`. Matched on the line rather than parsed: a
#: first-party import inside a function body or a `TYPE_CHECKING` block is still an edge, and an
#: unparseable file should not silently contribute no edges at all.
_FIRST_PARTY_IMPORT: Final[re.Pattern[str]] = re.compile(
    r"^\s*(?:from|import)\s+(weft_\w+)", re.MULTILINE
)


class Selection(BaseModel):
    """What a change set selects: the pytest paths, and whether `examples/` moved."""

    model_config = ConfigDict(frozen=True)

    paths: tuple[str, ...]
    examples_changed: bool
    reason: str


@cache
def module_sources() -> dict[str, Path]:
    """Every first-party top-level module, mapped to its own source directory.

    `packages/<something>/src/<module>` — the same invariant `tests/architecture/conftest.py`'s
    `first_party_source_roots` reads, and for the same reason: one distribution ships sixteen
    modules, so a distribution name predicts nothing about a module name.
    """
    found: dict[str, Path] = {}
    for src in sorted(PACKAGES_ROOT.glob("*/src")):
        for module in sorted(path for path in src.iterdir() if (path / "__init__.py").is_file()):
            found[module.name] = module
    return found


@cache
def importers() -> dict[str, frozenset[str]]:
    """For each first-party module, every first-party module that imports it."""
    modules = module_sources()
    edges: dict[str, set[str]] = {name: set() for name in modules}
    for name, source in modules.items():
        for path in source.rglob("*.py"):
            text = path.read_text(encoding="utf-8", errors="replace")
            for imported in _FIRST_PARTY_IMPORT.findall(text):
                if imported in edges and imported != name:
                    edges[imported].add(name)
    return {name: frozenset(dependents) for name, dependents in edges.items()}


def dependents_of(module: str) -> frozenset[str]:
    """`module` and every first-party module that reaches it, directly or transitively."""
    graph = importers()
    seen: set[str] = set()
    queue = [module]
    while queue:
        current = queue.pop()
        if current in seen:
            continue
        seen.add(current)
        queue.extend(graph.get(current, frozenset()))
    return frozenset(seen)


def _module_for(changed: str) -> str | None:
    """The module a `packages/<dist>/src/<module>/...` path belongs to, if it is one."""
    parts = Path(changed).parts
    if len(parts) < 4 or parts[0] != "packages" or parts[2] != "src":
        return None
    return parts[3] if parts[3] in module_sources() else None


def _unit_suite(module: str) -> str | None:
    return f"tests/unit/{module}" if (REPO_ROOT / "tests" / "unit" / module).is_dir() else None


def _test_target(changed: str) -> str:
    """A changed path under `tests/` selects itself, or its directory once the file is gone."""
    return changed if (REPO_ROOT / changed).exists() else str(Path(changed).parent)


def _prune(paths: Iterable[str]) -> tuple[str, ...]:
    """Drop any path already covered by another selected path, so pytest is handed no duplicate."""
    kept = sorted(set(paths))
    return tuple(
        path
        for path in kept
        if not any(other != path and path.startswith(f"{other}/") for other in kept)
    )


def _reshapes_the_workspace(changed: frozenset[str]) -> bool:
    return any(name in WHOLE_TREE_TRIGGERS for name in changed) or any(
        name.startswith("packages/") and name.endswith("pyproject.toml") for name in changed
    )


def select(changed: frozenset[str]) -> Selection:
    """The tests a change set can have affected. Over-selects on purpose; never under-selects."""
    if not changed:
        return Selection(
            paths=(), examples_changed=False, reason="nothing changed against the base"
        )

    if _reshapes_the_workspace(changed):
        return Selection(
            paths=("tests",),
            examples_changed=True,
            reason="a workspace-shaping file changed, so nothing narrower than the tree is honest",
        )

    paths: set[str] = set(WHOLE_TREE_SUITES)
    examples_changed = False
    for name in sorted(changed):
        if name.startswith("packages/"):
            paths.add("tests/integration")
            module = _module_for(name)
            reached = dependents_of(module) if module is not None else frozenset[str]()
            paths.update(suite for suite in map(_unit_suite, reached) if suite is not None)
        elif name.startswith("tests/"):
            paths.add(_test_target(name))
        elif name.startswith("examples/"):
            examples_changed = True
        elif name.startswith(("scripts/", "eval/")):
            paths.add("tests/unit/eval")

    return Selection(
        paths=_prune(paths),
        examples_changed=examples_changed,
        reason=f"{len(changed)} changed file(s) against the base",
    )


def read_change_set(lines: Iterable[str]) -> frozenset[str]:
    """The change set, one repository-relative path per line, blank lines ignored."""
    return frozenset(line.strip() for line in lines if line.strip())


def main(argv: Sequence[str]) -> int:
    forwarded = [argument for argument in argv if argument != "--list"]
    changed = read_change_set(sys.stdin)
    selection = select(changed)

    print(f"impacted: {selection.reason}")
    print(f"pytest paths: {' '.join(selection.paths) or '(none)'}")
    if selection.examples_changed:
        print("examples/ changed — run their own suites with: uv run poe examples-tests")
    if "--list" in argv or not selection.paths:
        return 0
    return int(pytest.main([*selection.paths, "-q", *forwarded]))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
