"""Fitness function 33 — a stage times itself with no action by its author (ledger task 33.2).

Specified in `docs/01-high-level-plan.md` → *Fitness functions*, entry 33. Task 33.1 made timing a
seam concern: every `weft_kernel.seam.wrap` call inside a recording scope leaves a `StageRecord`.
That is only true of the calls that go through the seam, so this function checks both halves.

**(a) Every pipeline position is recorded without the plugin doing anything.** A pipeline of
in-process plugins, one per position, run through `Runner.run_once` inside a scope, yields one
record per position, and none of those plugins imports a clock or a tracer.

**(b) No plugin method is called around the seam.** The walk finds every function in `weft-rag`
that builds a plugin through `registry.entry(...).factory(...)` and every awaited method call on
that instance that is not a lifecycle call (`close`, `aclose`, `flush`) and is not handed to
`wrap`. Each one is a call no record can see. `UNWRAPPED_PLUGIN_CALLS` names them, keyed without
line numbers so an unrelated edit does not move the key. Measured 2026-09-15: 8 functions build a
plugin that way, and exactly one call escapes the seam — the retrieve-only store search. Task 33.3
is what empties the waiver.

**The known gap, stated as FF7(b) states its own.** A store method a retriever calls inside its own
`run` is not built by a `.factory` call in that function, so it is timed only as part of the
retriever's record. Splitting it would be a wrapped arm inside the retriever, which is that
retriever's business rather than the seam's.
"""

import ast
from collections.abc import Sequence
from pathlib import Path
from typing import Final, Protocol

from weft_kernel import runner, seam
from weft_kernel.context import Context
from weft_kernel.payload import Outcome, Produced
from weft_kernel.registry import Registry

from .conftest import REPO_ROOT

RAG_SOURCE: Final[Path] = REPO_ROOT / "packages" / "weft-rag" / "src"

#: Every plugin method call made around the seam, as `<path under src> <function> <name>.<method>`.
#: **Emptied by task 33.3**, and pinned empty after it: an entry is a call whose time no record
#: shows, so adding one is a visible act in a diff.
UNWRAPPED_PLUGIN_CALLS: Final[frozenset[str]] = frozenset(
    {"weft_cli/ask.py run_ask instance_store.search_vector"}
)

_LIFECYCLE: Final[frozenset[str]] = frozenset({"close", "aclose", "flush"})


def _factory_built(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(fn):
        if isinstance(node, ast.Assign | ast.AnnAssign) and node.value is not None:
            built = any(
                isinstance(call, ast.Call)
                and isinstance(call.func, ast.Attribute)
                and call.func.attr == "factory"
                for call in ast.walk(node.value)
            )
            if built:
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                names |= {target.id for target in targets if isinstance(target, ast.Name)}
    return names


def _wrap_arguments(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> list[ast.expr]:
    return [
        argument
        for call in ast.walk(fn)
        if isinstance(call, ast.Call) and isinstance(call.func, ast.Name) and call.func.id == "wrap"
        for argument in call.args[:1]
    ]


def _handed_to_wrap(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    return {
        f"{argument.value.id}.{argument.attr}"
        for argument in _wrap_arguments(fn)
        if isinstance(argument, ast.Attribute) and isinstance(argument.value, ast.Name)
    }


def _inside_a_wrapped_local(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> set[int]:
    """Identities of every node inside a local function that is itself handed to `wrap`.

    A method that returns no `Outcome` cannot be wrapped directly, so the seam's own idiom is a
    local adapter — `async def _search(): return Produced(value=await store.search_vector(...))`
    handed to `wrap(_search, ...)`. The call inside it is timed, attributed and spanned.
    """
    wrapped_names = {arg.id for arg in _wrap_arguments(fn) if isinstance(arg, ast.Name)}
    return {
        id(node)
        for local in ast.walk(fn)
        if isinstance(local, ast.FunctionDef | ast.AsyncFunctionDef)
        and local is not fn
        and local.name in wrapped_names
        for node in ast.walk(local)
    }


def unwrapped_calls(source: str, relative: str) -> set[str]:
    """Every awaited method call on a `.factory`-built instance that does not go through `wrap`."""
    found: set[str] = set()
    for fn in ast.walk(ast.parse(source)):
        if not isinstance(fn, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        built = _factory_built(fn)
        if not built:
            continue
        wrapped = _handed_to_wrap(fn)
        covered = _inside_a_wrapped_local(fn)
        for node in ast.walk(fn):
            if not (isinstance(node, ast.Await) and isinstance(node.value, ast.Call)):
                continue
            if id(node) in covered:
                continue
            target = node.value.func
            if (
                isinstance(target, ast.Attribute)
                and isinstance(target.value, ast.Name)
                and target.value.id in built
                and target.attr not in _LIFECYCLE
                and f"{target.value.id}.{target.attr}" not in wrapped
            ):
                found.add(f"{relative} {fn.name} {target.value.id}.{target.attr}")
    return found


def _tree_unwrapped_calls() -> set[str]:
    found: set[str] = set()
    for path in sorted(RAG_SOURCE.rglob("*.py")):
        relative = path.relative_to(RAG_SOURCE).as_posix()
        found |= unwrapped_calls(path.read_text(encoding="utf-8"), relative)
    return found


class _Position(runner.Stage[Sequence[int], Sequence[int]], Protocol):
    """Any pipeline position a stranger could fill: it transforms and times nothing itself."""

    async def run(self, payload: Sequence[int], ctx: Context) -> Outcome[Sequence[int]]: ...


class _Double:
    def __init__(self, config: object = None) -> None:
        del config

    async def run(self, payload: Sequence[int], ctx: Context) -> Outcome[Sequence[int]]:
        del ctx
        return Produced(value=tuple(item + 1 for item in payload))


class _Halve:
    def __init__(self, config: object = None) -> None:
        del config

    async def run(self, payload: Sequence[int], ctx: Context) -> Outcome[Sequence[int]]:
        del ctx
        return Produced(value=tuple(payload[: len(payload) // 2]))


async def test_every_position_is_recorded_without_its_plugin_doing_anything() -> None:
    # Arrange
    registry = Registry()
    registry.add(_Position, "double", _Double, distribution="weft-test-pack")
    registry.add(_Position, "halve", _Halve, distribution="weft-test-pack")
    engine = runner.Runner(registry)
    pipeline = engine.resolve(
        (
            runner.StageSpec(id="first", contract=_Position, name="double"),
            runner.StageSpec(id="second", contract=_Position, name="halve"),
        ),
        tenant_id="tenant-a",
    )
    ctx = Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")

    # Act
    with seam.recording() as scope:
        await engine.run_once(pipeline, (1, 2, 3, 4), ctx)

    # Assert
    positions = [record.position for record in scope.records if record.position is not None]
    assert sorted(positions) == ["first", "second"]
    by_position = {record.position: record for record in scope.records}
    assert (by_position["first"].items_in, by_position["first"].items_out) == (4, 4)
    assert (by_position["second"].items_in, by_position["second"].items_out) == (4, 2)


def test_no_plugin_method_is_called_around_the_seam() -> None:
    # Act
    found = _tree_unwrapped_calls()

    # Assert
    assert found <= UNWRAPPED_PLUGIN_CALLS, (
        "a plugin method is called without `weft_kernel.seam.wrap`, so no stage record, span or "
        "attribution sees it (fitness function 33 (b)): "
        + ", ".join(sorted(found - UNWRAPPED_PLUGIN_CALLS))
    )
    assert found >= UNWRAPPED_PLUGIN_CALLS, (
        "a waiver names a call the tree no longer makes — remove it, so the list stays a list of "
        "real calls: " + ", ".join(sorted(UNWRAPPED_PLUGIN_CALLS - found))
    )


def test_the_walk_sees_the_functions_that_build_plugins() -> None:
    """Non-vacuity: a walk that found no `.factory`-built plugin would pass over nothing."""
    # Act
    building = [
        fn
        for path in RAG_SOURCE.rglob("*.py")
        for fn in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        if isinstance(fn, ast.FunctionDef | ast.AsyncFunctionDef) and _factory_built(fn)
    ]

    # Assert
    assert len(building) >= 5, f"only {len(building)} functions build a plugin — the walk broke"


def test_the_check_can_actually_fail() -> None:
    # Arrange
    planted = (
        "async def run(registry, vector):\n"
        "    store = registry.entry(NodeStore, 'x').factory(None)\n"
        "    wrapped = wrap(store.run, distribution='d', contract='c', plugin='p')\n"
        "    await wrapped(vector)\n"
        "    await store.search_vector(vector, 5)\n"
        "    await store.aclose()\n"
    )

    adapted = (
        "async def run(registry, vector):\n"
        "    store = registry.entry(NodeStore, 'x').factory(None)\n"
        "    async def _search():\n"
        "        return Produced(value=await store.search_vector(vector, 5))\n"
        "    await wrap(_search, distribution='d', contract='c', plugin='p')()\n"
    )

    # Act
    found = unwrapped_calls(planted, "planted.py")
    through_an_adapter = unwrapped_calls(adapted, "adapted.py")

    # Assert
    assert found == {"planted.py run store.search_vector"}
    assert through_an_adapter == set()
