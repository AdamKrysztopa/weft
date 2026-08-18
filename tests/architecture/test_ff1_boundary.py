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
