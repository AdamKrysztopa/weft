"""Every first-party module a distribution imports is one it ships or one it declares.

This test was written for a reviewer finding against task 2.8: `weft_cli.route_ask`
(the module backing the `weft route` command) imports `weft_generate.payload.Answer`
at module scope, but `weft-cli`'s own `pyproject.toml` never listed `weft-generate` in
`dependencies` — and nothing it *did* declare pulled `weft-generate` in transitively
(`weft-retrieve` deliberately does not, per `.phase2-design.md`'s own DAG rule). Inside
this repository's shared `uv` workspace venv every first-party package is already
editable-installed regardless of any one distribution's declared dependencies, so the gap
was invisible to every test that ran here — the same blind spot `tests/architecture/
test_ff1_boundary.py`'s module docstring names for the kernel, applied to a pack instead
of the kernel: "a kernel that is its own wheel is checked by installing it alone and
importing it" (`CLAUDE.md`, *Where things are*). A real `pip install weft-cli` installed a
wheel that raised `ModuleNotFoundError` the first time `weft route` ran.

**Widened from `weft-cli` alone to every published distribution on 2026-09-05**, when
fourteen distributions became one. Scoped to `weft-cli`, this check would now be close to
vacuous — `weft_cli` ships in `weft-rag` alongside every module it imports, so almost
nothing it imports needs declaring at all. The property is unchanged and the subject is
simply larger: for each distribution under `packages/`, every first-party module its own
source tree imports must either ship in that same distribution or be named in its
`dependencies`. That is what makes `weft-pdf`'s `import weft_extract` a declared fact
rather than an accident of a shared venv, and it is exactly the finding above generalised
past the one distribution that produced it.

Mirrors `test_ff1_boundary.py`'s AST-walk approach (`_top_level_imports` there), checked
against each distribution's own manifest rather than a fixed dependency set — a pack is not
the kernel, so what it may import is whatever it declares, not a G1-fixed pair.
"""

from __future__ import annotations

import ast
import sys
import tomllib
from pathlib import Path
from typing import Final

from .conftest import REPO_ROOT, first_party_source_roots, str_list_at, table_at

PACKAGES_ROOT: Final[Path] = REPO_ROOT / "packages"


def test_every_distribution_declares_every_first_party_distribution_it_imports() -> None:
    # `weft_extract` -> `weft-pdf`, and so on: which distribution actually ships each
    # first-party module, read off the tree rather than guessed from the module's own name.
    ships = {
        module: _distribution_at(root.parents[1])
        for module, root in first_party_source_roots().items()
    }

    violations: list[str] = []
    for manifest in sorted(PACKAGES_ROOT.glob("*/pyproject.toml")):
        root = manifest.parent
        with manifest.open("rb") as handle:
            document = tomllib.load(handle)
        project = table_at(document, "project")
        own = project["name"]
        declared = {_requirement_name(entry) for entry in str_list_at(project, "dependencies")}

        for path in sorted((root / "src").rglob("*.py")):
            for imported in _top_level_first_party_imports(path):
                provider = ships.get(imported)
                if provider is None:
                    violations.append(
                        f"{path.relative_to(REPO_ROOT)} imports {imported}, which no "
                        f"distribution under packages/ ships"
                    )
                elif provider != own and provider not in declared:
                    violations.append(
                        f"{path.relative_to(REPO_ROOT)} imports {imported}, shipped by "
                        f"'{provider}', but '{provider}' is not in {own}'s own "
                        f"pyproject.toml dependencies"
                    )

    assert not violations, (
        "a distribution imports a first-party module it neither ships nor declares:\n  "
        + "\n  ".join(sorted(violations))
        + "\nOutside this repo's shared uv workspace venv (where every first-party package "
        "is already installed regardless of declared deps), a real install would not pull "
        "this in, and the import would fail at runtime."
    )


def test_at_least_one_source_file_is_walked() -> None:
    # Floor, same shape as test_ff1_boundary's — a walk that finds nothing would let the
    # assertion above pass vacuously. Stated per distribution rather than in total, because
    # the failure this guards against is a *directory layout* change silently emptying the
    # walk, and one distribution's tree can vanish while the total stays non-zero.
    for manifest in sorted(PACKAGES_ROOT.glob("*/pyproject.toml")):
        root = manifest.parent
        walked = sorted((root / "src").rglob("*.py"))
        assert walked, f"no `.py` file found under {root / 'src'} — the walk itself is broken."


def _distribution_at(root: Path) -> str:
    with (root / "pyproject.toml").open("rb") as handle:
        document = tomllib.load(handle)
    name = table_at(document, "project")["name"]
    assert isinstance(name, str)
    return name


def _requirement_name(requirement: str) -> str:
    """`opentelemetry-api>=1.28` -> `opentelemetry-api`."""
    for separator in (">=", "==", "<=", "~=", ">", "<", "[", ";", " "):
        requirement = requirement.split(separator)[0]
    return requirement.strip()


def _top_level_first_party_imports(path: Path) -> set[str]:
    modules: set[str] = set()

    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            modules.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            modules.add(node.module.split(".")[0])

    return {m for m in modules if m.startswith("weft_") and m not in sys.stdlib_module_names}
