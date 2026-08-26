"""Fitness function 1 — boundary.

Nothing under the kernel may import anything the kernel does not ship.

Two halves. The **primary** one is not a test at all: because the kernel is its
own distribution, you install `weft-kernel` alone in a clean environment and
import it — if anything else is reachable, the import fails and no AST walk was
needed. That runs as `poe kernel-isolated`, in CI, because it needs a fresh
environment this process cannot provide.

The **static** half lives here, for the distributions that ship together in one
repository and can therefore see each other on `sys.path` regardless of what
they declare. It is derived from the declared dependency set rather than
enumerated as a denylist of prefixes — the reference's checker used a denylist, it
matched zero imports, and it exited 0 on a tree with 11 violations.
"""

import ast
import sys
from pathlib import Path
from typing import Final

from .conftest import KERNEL_ROOT, str_list_at, table_at

#: Settled in G1: the kernel depends on these and nothing else. The OTel package
#: is the API, which libraries are meant to depend on and which no-ops without an
#: SDK; everything that exports a span is a pack.
KERNEL_DEPENDENCIES: Final[frozenset[str]] = frozenset({"pydantic", "opentelemetry"})


def test_kernel_declares_exactly_its_two_dependencies(kernel_config: dict[str, object]) -> None:
    project = table_at(kernel_config, "project")

    names = {_distribution_name(entry) for entry in str_list_at(project, "dependencies")}

    assert names == {"pydantic", "opentelemetry-api"}, (
        f"weft-kernel declares {sorted(names)}. G1 settled its dependencies as pydantic and "
        f"opentelemetry-api, and nothing else. A third dependency is a change to the kernel "
        f"boundary, which is a decision-log entry, not a line in a pyproject."
    )


def test_kernel_imports_nothing_it_does_not_ship() -> None:
    violations: list[str] = []

    for path in sorted((KERNEL_ROOT / "src").rglob("*.py")):
        for imported in _top_level_imports(path):
            if imported in KERNEL_DEPENDENCIES or imported in sys.stdlib_module_names:
                continue
            violations.append(f"{path.relative_to(KERNEL_ROOT)} imports {imported}")

    assert not violations, (
        "The kernel imports something it does not ship:\n  "
        + "\n  ".join(violations)
        + "\nThe kernel performs no RAG work and names no capability (G1). An import that "
        "does not resolve to pydantic, opentelemetry or the standard library means one of "
        "those two rules has been broken."
    )


def test_at_least_one_kernel_file_is_walked() -> None:
    # Floor — `08` §3's shape, applied to a source walk instead of a document walk: a
    # walk that finds nothing would let the assertion above pass on an empty tree,
    # exactly the vacuous shape `reference/study/08-salvage.md:777-782`'s parity test takes.
    walked = sorted((KERNEL_ROOT / "src").rglob("*.py"))
    assert walked, (
        f"no `.py` file found under {KERNEL_ROOT / 'src'} — the walk itself is broken; "
        f"fix it before trusting the boundary check above."
    )


def _distribution_name(requirement: str) -> str:
    """`opentelemetry-api>=1.28` -> `opentelemetry-api`."""
    for separator in (">=", "==", "<=", "~=", ">", "<", "[", ";", " "):
        requirement = requirement.split(separator)[0]
    return requirement.strip()


def _top_level_imports(path: Path) -> set[str]:
    modules: set[str] = set()

    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            modules.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            modules.add(node.module.split(".")[0])

    return modules - {"weft_kernel"}


def test_the_check_can_actually_fail(tmp_path: Path) -> None:
    """Fitness function 16 clause (b) — ledger task **6.15**.

    The reference's boundary checker "used a denylist, it matched zero imports, and it exited 0
    on a tree with 11 violations" — this file's own docstring. That is precisely a check
    nobody had watched fail, and it is why this self-test plants a real violation and runs
    the real `_top_level_imports` over it rather than asserting anything about a set.

    Three shapes at once, because they take three different AST paths and a walker can be
    right about one and blind to another: a plain `import`, a dotted `import a.b`, and a
    `from x import y`. The stdlib and `weft_kernel` exclusions are exercised in the same
    file, so a walker that stopped excluding either would fail here too.
    """
    # Arrange
    planted = tmp_path / "planted.py"
    planted.write_text(
        "import os\n"
        "import psycopg\n"
        "import openai.types\n"
        "from weft_kernel.payload import Node\n"
        "from pydantic import BaseModel\n",
        encoding="utf-8",
    )

    # Act — the same expression `test_kernel_imports_nothing_it_does_not_ship` computes.
    imported = _top_level_imports(planted)
    violations = [
        name
        for name in sorted(imported)
        if name not in KERNEL_DEPENDENCIES and name not in sys.stdlib_module_names
    ]

    # Assert
    assert violations == ["openai", "psycopg"]
    assert "os" in imported, "the walker must see stdlib imports; the check is what filters them"
    assert "weft_kernel" not in imported
    assert "pydantic" in imported


def test_the_dependency_reader_can_actually_fail() -> None:
    """The other comparison in this file — a declared dependency set that disagrees with G1."""
    # Arrange
    declared = ["pydantic>=2", "opentelemetry-api>=1.28", "psycopg[binary]>=3.2"]

    # Act
    names = {_distribution_name(entry) for entry in declared}

    # Assert
    assert names != {"pydantic", "opentelemetry-api"}
    assert names == {"pydantic", "opentelemetry-api", "psycopg"}
