"""Every first-party distribution `weft-cli` imports is one it actually declares.

This test was written for a reviewer finding against task 2.8: `weft_cli.route_ask`
(the module backing the new `weft route` command) imports `weft_generate.payload.Answer`
at module scope, but `weft-cli`'s own `pyproject.toml` never lists `weft-generate` in
`dependencies` — and nothing it *does* declare pulls `weft-generate` in transitively
(`weft-retrieve` deliberately does not, per `.phase2-design.md`'s own DAG rule). Inside
this repository's shared `uv` workspace venv every first-party package is already
editable-installed regardless of any one distribution's declared dependencies, so the gap
was invisible to every test that ran here — the same blind spot `tests/architecture/
test_ff1_boundary.py`'s module docstring names for the kernel, applied to a pack instead
of the kernel: "a kernel that is its own wheel is checked by installing it alone and
importing it" (`CLAUDE.md`, *Where things are*). A real `pip install weft-cli` installs a
wheel that raises `ModuleNotFoundError` the first time `weft route` is run.

Mirrors `test_ff1_boundary.py`'s AST-walk approach (`_top_level_imports` there), scoped to
one distribution's own source tree checked against that same distribution's own manifest
rather than a fixed dependency set — `weft-cli` is not the kernel, so what it may import is
whatever it declares, not a G1-fixed pair.
"""

from __future__ import annotations

import ast
import sys
import tomllib
from pathlib import Path
from typing import Final

from .conftest import REPO_ROOT, str_list_at, table_at

CLI_ROOT: Final[Path] = REPO_ROOT / "packages" / "weft-cli"


def test_weft_cli_declares_every_first_party_distribution_it_imports() -> None:
    with (CLI_ROOT / "pyproject.toml").open("rb") as handle:
        cli_config = tomllib.load(handle)
    project = table_at(cli_config, "project")
    declared = {_distribution_name(entry) for entry in str_list_at(project, "dependencies")}

    violations: list[str] = []
    for path in sorted((CLI_ROOT / "src").rglob("*.py")):
        for imported in _top_level_first_party_imports(path):
            distribution = imported.replace("_", "-")
            if distribution == "weft-cli" or distribution in declared:
                continue
            violations.append(
                f"{path.relative_to(CLI_ROOT)} imports {imported}, but '{distribution}' is "
                f"not in weft-cli's own pyproject.toml dependencies"
            )

    assert not violations, (
        "weft-cli imports a distribution it does not declare:\n  "
        + "\n  ".join(violations)
        + "\nOutside this repo's shared uv workspace venv (where every first-party package "
        "is already installed regardless of declared deps), a real `pip install weft-cli` "
        "would not pull this in, and the import would fail at runtime."
    )


def test_at_least_one_cli_file_is_walked() -> None:
    # Floor, same shape as test_ff1_boundary's — a walk that finds nothing would let the
    # assertion above pass vacuously.
    walked = sorted((CLI_ROOT / "src").rglob("*.py"))
    assert walked, f"no `.py` file found under {CLI_ROOT / 'src'} — the walk itself is broken."


def _distribution_name(requirement: str) -> str:
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
