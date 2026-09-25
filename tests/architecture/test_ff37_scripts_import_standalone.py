"""Fitness function 37 — a script's imports resolve when it is run directly. `01` item 37.

`docs/internal/lessons.md` `L28.50`: `scripts/open_ragbench_questions.py` imported
`check_questions`, which lives in `eval/`. pytest's `pythonpath` and pyright's `extraPaths` both
put `eval` on the path, so the script's tests and type check passed while
`uv run python scripts/open_ragbench_questions.py --help` raised `ModuleNotFoundError`. A script
run directly sees its own directory as `sys.path[0]` and the installed environment after it,
and nothing a test runner added.

So every module-level absolute import in every tracked `scripts/**.py`, and in each `eval/`
harness run directly, is resolved by the built-in, frozen and path finders over `sys.path` as a
directly run interpreter builds it — its prefixes and its `.pth` entries, nothing a test runner
added — plus that script's own entries. No script is run. A module-level
`sys.path.insert(0, ...)` or `sys.path.append(...)` before an import counts, because Python
honours it and `24e155a` fixed `L28.50` that way. Its argument is read, never run: string
literals, `__file__`, `Path(...)`, `str(...)`, `.resolve()`, `.parent`, `.parents[n]`, `/`, and
module-level names bound to those. Any other `sys.path` call fails the check naming its line.

**Scope and blind spots.** The module body and the bodies of module-level `try` statements.
Imports under a module-level `if` (so `if TYPE_CHECKING:`), inside a function or class, and
relative imports are not resolved; nor is a `sys.path` edit made by assignment.
"""

from __future__ import annotations

import ast
import site
import sys
from collections.abc import Iterator, Mapping, Sequence
from importlib.machinery import FrozenImporter, PathFinder
from pathlib import Path, PurePosixPath

from pydantic import BaseModel, ConfigDict

from .conftest import REPO_ROOT, tracked_files

type PathValue = Path | str


class StandaloneImport(BaseModel):
    """A module a script imports at module level, named by its top-level package."""

    model_config = ConfigDict(frozen=True)

    script: str
    module: str


class ImportQuery(BaseModel):
    """One import, with the `sys.path` entries its script adds around the environment's."""

    model_config = ConfigDict(frozen=True)

    script: str
    module: str
    front: tuple[str, ...]
    back: tuple[str, ...]


class UnreadablePathEditError(ValueError):
    """A module-level `sys.path` edit whose argument cannot be evaluated statically."""


def _as_path(node: ast.expr, bindings: Mapping[str, PathValue]) -> Path:
    value = _evaluate(node, bindings)
    if isinstance(value, str):
        raise UnreadablePathEditError(ast.unparse(node))
    return value


def _evaluate(node: ast.expr, bindings: Mapping[str, PathValue]) -> PathValue:
    match node:
        case ast.Constant(value=str() as text):
            return text
        case ast.Name(id=name) if name in bindings:
            return bindings[name]
        case ast.Call(func=ast.Name(id="Path"), args=[argument], keywords=[]):
            return Path(_evaluate(argument, bindings))
        case ast.Call(func=ast.Name(id="str"), args=[argument], keywords=[]):
            return str(_evaluate(argument, bindings))
        case ast.Call(func=ast.Attribute(value=inner, attr="resolve"), args=[], keywords=[]):
            return _as_path(inner, bindings).resolve()
        case ast.Attribute(value=inner, attr="parent"):
            return _as_path(inner, bindings).parent
        case ast.Subscript(
            value=ast.Attribute(value=inner, attr="parents"),
            slice=ast.Constant(value=int() as depth),
        ):
            return _as_path(inner, bindings).parents[depth]
        case ast.BinOp(left=left, op=ast.Div(), right=right):
            return _as_path(left, bindings) / _evaluate(right, bindings)
        case _:
            raise UnreadablePathEditError(ast.unparse(node))


def _sys_path_call(statement: ast.stmt) -> ast.Call | None:
    match statement:
        case ast.Expr(
            value=ast.Call(
                func=ast.Attribute(value=ast.Attribute(value=ast.Name(id="sys"), attr="path"))
            ) as call
        ):
            return call
        case _:
            return None


def _apply_edit(
    call: ast.Call, bindings: Mapping[str, PathValue], front: list[str], back: list[str]
) -> None:
    match call:
        case ast.Call(func=ast.Attribute(attr="insert"), args=[ast.Constant(value=0), argument]):
            front.insert(0, str(_evaluate(argument, bindings)))
        case ast.Call(func=ast.Attribute(attr="append"), args=[argument]):
            back.append(str(_evaluate(argument, bindings)))
        case _:
            raise UnreadablePathEditError(ast.unparse(call))


def _edit_located(
    call: ast.Call,
    bindings: Mapping[str, PathValue],
    paths: tuple[list[str], list[str]],
    script: str,
) -> None:
    try:
        _apply_edit(call, bindings, *paths)
    except UnreadablePathEditError as error:
        raise UnreadablePathEditError(
            f"{script}:{call.lineno} edits `sys.path` with `{error}`, which this check cannot "
            f"read; spell it with the forms its docstring lists"
        ) from error


def _module_level(body: Sequence[ast.stmt]) -> Iterator[ast.stmt]:
    for statement in body:
        if isinstance(statement, ast.Try | ast.TryStar):
            yield from _module_level(statement.body)
        else:
            yield statement


def _imported(statement: ast.stmt) -> list[str]:
    match statement:
        case ast.Import(names=aliases):
            return [alias.name.partition(".")[0] for alias in aliases]
        case ast.ImportFrom(module=str() as module, level=0):
            return [module.partition(".")[0]]
        case _:
            return []


def _bind(statement: ast.stmt, bindings: dict[str, PathValue]) -> None:
    match statement:
        case (
            ast.Assign(targets=[ast.Name(id=name)], value=value)
            | ast.AnnAssign(target=ast.Name(id=name), value=ast.expr() as value)
        ):
            try:
                bindings[name] = _evaluate(value, bindings)
            except UnreadablePathEditError:
                bindings.pop(name, None)
        case _:
            pass


def import_queries(root: Path, script: str) -> list[ImportQuery]:
    """Every module-level absolute import in `script`, with the `sys.path` it resolves against.

    Args:
        root: The directory `script` is relative to.
        script: A posix path to a Python file under `root`.

    Returns:
        One query per distinct top-level module, in first-import order.

    Raises:
        UnreadablePathEditError: A module-level `sys.path` call cannot be evaluated statically.
    """
    path = root / script
    front, back = [str(path.parent)], list[str]()
    bindings: dict[str, PathValue] = {"__file__": str(path)}
    queries: dict[str, ImportQuery] = {}
    for statement in _module_level(ast.parse(path.read_text(encoding="utf-8")).body):
        if (call := _sys_path_call(statement)) is not None:
            _edit_located(call, bindings, (front, back), script)
        _bind(statement, bindings)
        for module in _imported(statement):
            queries.setdefault(
                module,
                ImportQuery(script=script, module=module, front=tuple(front), back=tuple(back)),
            )
    return list(queries.values())


def _interpreter_path() -> list[str]:
    """`sys.path` as a directly run interpreter builds it: its prefixes and what `.pth` files add.

    Anything else on this process's path was put there by the test runner — pytest's
    `pythonpath` is exactly what hid `L28.50`.
    """
    prefixes = {Path(sys.prefix).resolve(), Path(sys.base_prefix).resolve()}
    added = {
        line.strip()
        for site_dir in site.getsitepackages()
        for pth in Path(site_dir).glob("*.pth")
        for line in pth.read_text().splitlines()
        if line.strip() and not line.startswith(("#", "import"))
    }
    return [
        entry
        for entry in sys.path
        if entry in added or any(Path(entry).resolve().is_relative_to(p) for p in prefixes)
    ]


def _resolves(module: str, path: list[str]) -> bool:
    return (
        module in sys.builtin_module_names
        or FrozenImporter.find_spec(module) is not None
        or PathFinder.find_spec(module, path) is not None
    )


def unresolved_imports(queries: Sequence[ImportQuery]) -> list[StandaloneImport]:
    """The queries a directly run interpreter cannot resolve, with no path a test runner added.

    Args:
        queries: The imports to resolve, each with its script's own `sys.path` entries.

    Returns:
        One entry per import no finder on that interpreter's path locates.
    """
    environment = _interpreter_path()
    assert PathFinder.find_spec("sqlite3", environment), f"no stdlib on {environment}"
    return [
        StandaloneImport(script=query.script, module=query.module)
        for query in queries
        if not _resolves(query.module, [*query.front, *environment, *query.back])
    ]


def _tracked_scripts() -> list[str]:
    """`scripts/`, and the `eval/` harnesses that are run directly.

    `.claude/` is left out: its hooks run under bare `python3`, not this interpreter.
    """
    return sorted(
        path
        for path in tracked_files()
        if path.endswith(".py")
        and (
            PurePosixPath(path).parts[0] == "scripts"
            or (
                PurePosixPath(path).parts[0] == "eval"
                and '__name__ == "__main__"' in (REPO_ROOT / path).read_text(encoding="utf-8")
            )
        )
    )


def test_every_script_import_resolves_when_the_script_runs_directly() -> None:
    scripts = _tracked_scripts()
    assert scripts, "no tracked script found — the filter is wrong, not the tree"
    queries = [query for script in scripts for query in import_queries(REPO_ROOT, script)]

    unresolved = unresolved_imports(queries)

    assert not unresolved, (
        "These imports resolve only through a path a test runner or type checker added, so "
        "running the script raises ModuleNotFoundError (`L28.50`):\n  "
        + "\n  ".join(f"{entry.script}: import {entry.module}" for entry in unresolved)
    )


def test_the_check_can_actually_fail(tmp_path: Path) -> None:
    (tmp_path / "planted.py").write_text("import json\nimport check_questions\n", encoding="utf-8")

    unresolved = unresolved_imports(import_queries(tmp_path, "planted.py"))

    assert unresolved == [StandaloneImport(script="planted.py", module="check_questions")]


def test_a_sys_path_edit_counts_only_for_the_imports_after_it(tmp_path: Path) -> None:
    (tmp_path / "lib").mkdir()
    (tmp_path / "lib" / "helper.py").write_text("", encoding="utf-8")
    (tmp_path / "sibling.py").write_text("", encoding="utf-8")
    (tmp_path / "planted.py").write_text(
        "import sys\n"
        "from pathlib import Path\n"
        "import helper\n"
        "LIB = Path(__file__).resolve().parent / 'lib'\n"
        "sys.path.insert(0, str(LIB))\n"
        "from helper import thing\n"
        "import sibling\n",
        encoding="utf-8",
    )

    unresolved = unresolved_imports(import_queries(tmp_path, "planted.py"))

    assert unresolved == [StandaloneImport(script="planted.py", module="helper")]


def test_only_imports_that_run_at_module_load_are_collected(tmp_path: Path) -> None:
    (tmp_path / "planted.py").write_text(
        "from typing import TYPE_CHECKING\n"
        "from . import relative\n"
        "if TYPE_CHECKING:\n"
        "    import typing_only\n"
        "try:\n"
        "    import guarded.sub\n"
        "except ImportError:\n"
        "    import handler_only\n"
        "def main() -> None:\n"
        "    import function_only\n",
        encoding="utf-8",
    )

    modules = [query.module for query in import_queries(tmp_path, "planted.py")]

    assert modules == ["typing", "guarded"]


def test_an_unreadable_sys_path_edit_fails_naming_its_line(tmp_path: Path) -> None:
    (tmp_path / "planted.py").write_text(
        "import os, sys\nsys.path.insert(0, os.getcwd())\n", encoding="utf-8"
    )

    try:
        import_queries(tmp_path, "planted.py")
    except UnreadablePathEditError as error:
        assert str(error).startswith(f"planted.py:{2} ")
    else:
        raise AssertionError("an edit the check cannot read was accepted in silence")
