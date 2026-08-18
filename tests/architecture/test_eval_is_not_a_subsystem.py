"""The V-prerequisite harness is an artefact, not a subsystem — and Phase 4 is where it stops.

`docs/09-release.md` §4.3 asks for six artefacts, each *"a file or a persisted run"*. `eval/`
holds three of them and the code that produces them, and every line of it is meant to be
**deleted and replaced** by Phase 4: task 4.1 publishes `Metric` from a real `weft-eval`
distribution and 4.2 reimplements the measurements against it (`docs/build-ledger.md`). Nothing
here is promoted.

**Being extensible is precisely what would make it Phase 4's system**, which is why this file
tests for the absence of things rather than the presence of them. A registry of metrics, an
entry point, a `pyproject.toml` — any one of them and `eval/` has quietly become a distribution
that Phase 4 must migrate rather than replace, and the phase boundary `01` draws would have been
crossed by a convenience nobody argued for.

The third check is the one that would otherwise rot silently: a pack importing the harness would
make the *measurement* part of the engine, so a change to how a baseline is scored would change
what the engine does. The dependency is one-way by design — `eval/` drives `weft` as a
subprocess and imports the CLI's own result model to read what it printed — and this is the
direction that must never appear.
"""

import ast
from pathlib import Path
from typing import Final

from .conftest import REPO_ROOT

EVAL_ROOT: Final[Path] = REPO_ROOT / "eval"
PACKAGES_ROOT: Final[Path] = REPO_ROOT / "packages"

#: Every top-level module name `eval/` publishes on the import path. Derived from what is there
#: rather than listed, so a fourth harness module is covered the day it is written.
EVAL_MODULES: Final[frozenset[str]] = frozenset(
    path.stem for path in EVAL_ROOT.glob("*.py") if not path.stem.startswith("_")
)

#: What a distribution is made of. Any of these under `eval/` means it became one.
_DISTRIBUTION_FILES: Final[tuple[str, ...]] = ("pyproject.toml", "setup.py", "setup.cfg")


def test_the_walk_found_the_harness_and_the_packages() -> None:
    # Task 1.18's floor: every check below is "no violations", which is true of an empty walk.
    # A renamed directory would otherwise turn this whole file green by finding nothing.
    # Assert
    assert {"metrics", "run_baseline", "check_baseline", "check_questions"} <= EVAL_MODULES, (
        f"the harness modules this file exists to fence are not under {EVAL_ROOT}: found "
        f"{sorted(EVAL_MODULES)}"
    )
    assert list(PACKAGES_ROOT.glob("*/src")), f"no distribution sources under {PACKAGES_ROOT}"


def test_the_harness_is_not_a_distribution() -> None:
    # A `pyproject.toml` here is the whole difference between "a script that produced a file"
    # and "a package Phase 4 has to keep working". `09` §4.3's artefacts are files.
    # Act
    found = sorted(
        str(path.relative_to(REPO_ROOT))
        for name in _DISTRIBUTION_FILES
        for path in EVAL_ROOT.rglob(name)
    )

    # Assert
    assert not found, (
        f"{found} make eval/ a distribution. It is a set of hand-run tools producing the "
        f"artefacts `docs/09-release.md` §4.3 requires; Phase 4 task 4.2 *deletes* them and "
        f"reimplements the measurements inside a real `weft-eval` pack rather than promoting "
        f"these."
    )


def test_the_harness_registers_nothing() -> None:
    # The other half of the same rule, and the one a helpful refactor would reach for first: a
    # metric that could be registered would need a registry, a name space and a config model,
    # and `eval/` would be the extension system Phase 4 is supposed to design.
    # Act
    declaring = sorted(
        str(path.relative_to(REPO_ROOT))
        for path in EVAL_ROOT.rglob("*.py")
        if "weft.packs" in path.read_text(encoding="utf-8")
    )

    # Assert
    assert not declaring, (
        f"{declaring} name the `weft.packs` entry point group. Nothing under eval/ is a plugin, "
        f"a contract or a registry — see this file's docstring."
    )


def test_no_distribution_imports_the_harness() -> None:
    # The direction that must never appear. `eval/` imports `weft_cli.ask`'s result model to
    # read what the command printed, which is one-way and fine; a pack importing `metrics` would
    # make how a baseline is scored part of what the engine does.
    # Act
    violations = [
        f"{path.relative_to(REPO_ROOT)} imports {imported}"
        for path in sorted(PACKAGES_ROOT.rglob("*.py"))
        for imported in _top_level_imports(path)
        if imported in EVAL_MODULES
    ]

    # Assert
    assert not violations, (
        "a distribution imports the evaluation harness:\n  "
        + "\n  ".join(violations)
        + "\nThe harness measures the engine; the engine may not depend on the harness, or the "
        "measurement is part of what is being measured."
    )


def _top_level_imports(path: Path) -> set[str]:
    """Every root module name `path` imports, however the import was spelled."""
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module.split(".", 1)[0])
    return names
