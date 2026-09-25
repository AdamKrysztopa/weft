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
line numbers so an unrelated edit does not move the key. On 2026-09-15 exactly one call escaped the
seam — the retrieve-only store search — and task 33.3 emptied the waiver.

**The instance is followed into the helpers it is handed to** (`docs/internal/lessons.md`
`L28.52`), because splitting a function for the complexity limit moves its plugin calls into a
helper the one-function walk could not see. A built local passed by position or keyword to a
module-level function, or to `self.`/`cls.`/`type(self).` a method of the same class, binds the
matching parameter, and that parameter is walked as the local was — transitively. A call found in
a helper is keyed by the helper's name and its parameter's name, which is where the line is.
Measured 2026-09-25: 24 builders, 15 hand-offs followed, 13 awaited calls on a holder, none
escaping.

**The known gaps, stated as FF7(b) states its own.** A store method a retriever calls inside its own
`run` is not built by a `.factory` call in that function, so it is timed only as part of the
retriever's record. Splitting it would be a wrapped arm inside the retriever, which is that
retriever's business rather than the seam's. The walk also does not follow an instance into
another module's helper, onto an attribute, into a container, or through an expression such as
`cast(NodeStore, instance).method()`.
"""

import ast
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
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
UNWRAPPED_PLUGIN_CALLS: Final[frozenset[str]] = frozenset()

_LIFECYCLE: Final[frozenset[str]] = frozenset({"close", "aclose", "flush"})

type _Function = ast.FunctionDef | ast.AsyncFunctionDef
_FUNCTION_NODES: Final = (ast.FunctionDef, ast.AsyncFunctionDef)


class _Receiver(Enum):
    INSTANCE = "instance"
    CLASS = "class"


def _factory_built(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(fn):
        if (
            isinstance(node, ast.Assign | ast.AnnAssign)
            and node.value is not None
            and _calls_factory(node.value)
        ):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            names |= {target.id for target in targets if isinstance(target, ast.Name)}
    return names


def _calls_factory(value: ast.expr) -> bool:
    return any(
        isinstance(call, ast.Call)
        and isinstance(call.func, ast.Attribute)
        and call.func.attr == "factory"
        for call in ast.walk(value)
    )


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
    return {
        f"{relative} {fn.name} {call}"
        for fn, name in _reached_holders(ast.parse(source))
        for call in _escaping_calls(fn, {name})
    }


@dataclass(frozen=True)
class _Module:
    functions: dict[str, _Function]
    methods_of: dict[int, dict[str, _Function]]


def _index(tree: ast.Module) -> _Module:
    methods_of: dict[int, dict[str, _Function]] = {}
    for owner in ast.walk(tree):
        if isinstance(owner, ast.ClassDef):
            methods = {n.name: n for n in owner.body if isinstance(n, _FUNCTION_NODES)}
            methods_of |= {id(method): methods for method in methods.values()}
    functions = {n.name: n for n in tree.body if isinstance(n, _FUNCTION_NODES)}
    return _Module(functions=functions, methods_of=methods_of)


def _reached_holders(tree: ast.Module) -> set[tuple[_Function, str]]:
    """Every `(function, name)` where `name` holds a `.factory`-built instance inside `function`.

    The builders' own locals, then every same-module parameter one is handed to, transitively.
    """
    module = _index(tree)
    pending = [
        (fn, name)
        for fn in ast.walk(tree)
        if isinstance(fn, _FUNCTION_NODES)
        for name in _factory_built(fn)
    ]
    reached: set[tuple[_Function, str]] = set()
    while pending:
        pair = pending.pop()
        if pair not in reached:
            reached.add(pair)
            pending.extend(_handoffs(*pair, module=module))
    return reached


def _handoffs(fn: _Function, name: str, *, module: _Module) -> set[tuple[_Function, str]]:
    """Every `(callee, parameter)` a call in `fn` binds `name` to, for a same-module callee."""
    edges: set[tuple[_Function, str]] = set()
    for call in ast.walk(fn):
        if isinstance(call, ast.Call) and (resolved := _callee(call, fn, module)) is not None:
            callee, skip = resolved
            edges |= {(callee, bound) for bound in _bound_parameters(call, name, callee, skip)}
    return edges


def _callee(call: ast.Call, fn: _Function, module: _Module) -> tuple[_Function, int] | None:
    """The same-module function `call` reaches, and how many leading parameters it binds itself."""
    if isinstance(call.func, ast.Name):
        target = module.functions.get(call.func.id)
        return None if target is None else (target, 0)
    if not isinstance(call.func, ast.Attribute):
        return None
    receiver = _receiver(call.func.value)
    target = module.methods_of.get(id(fn), {}).get(call.func.attr)
    if receiver is None or target is None:
        return None
    return target, _implicit_parameters(target, receiver)


def _receiver(value: ast.expr) -> _Receiver | None:
    """Whether `value` is `self`, or `cls` / `type(self)`; anything else is not followed."""
    match value:
        case ast.Name(id="self"):
            return _Receiver.INSTANCE
        case ast.Name(id="cls") | ast.Call(func=ast.Name(id="type"), args=[ast.Name(id="self")]):
            return _Receiver.CLASS
        case _:
            return None


def _implicit_parameters(target: _Function, receiver: _Receiver) -> int:
    decorators = {d.id for d in target.decorator_list if isinstance(d, ast.Name)}
    if "staticmethod" in decorators:
        return 0
    if "classmethod" in decorators:
        return 1
    return 1 if receiver is _Receiver.INSTANCE else 0


def _bound_parameters(call: ast.Call, name: str, callee: _Function, skip: int) -> set[str]:
    signature = callee.args
    positional = [*signature.posonlyargs, *signature.args][skip:]
    bound: set[str] = set()
    for parameter, argument in zip(positional, call.args, strict=False):
        if isinstance(argument, ast.Starred):
            break
        if isinstance(argument, ast.Name) and argument.id == name:
            bound.add(parameter.arg)
    by_keyword = {parameter.arg for parameter in [*signature.args, *signature.kwonlyargs]}
    bound |= {
        keyword.arg
        for keyword in call.keywords
        if keyword.arg in by_keyword
        and isinstance(keyword.value, ast.Name)
        and keyword.value.id == name
    }
    return bound


def _escaping_calls(fn: ast.FunctionDef | ast.AsyncFunctionDef, built: set[str]) -> set[str]:
    """Every `<name>.<method>` awaited in `fn` on a `built` instance that bypasses `wrap`."""
    wrapped = _handed_to_wrap(fn)
    covered = _inside_a_wrapped_local(fn)
    escaping: set[str] = set()
    for node in ast.walk(fn):
        if not (isinstance(node, ast.Await) and isinstance(node.value, ast.Call)):
            continue
        if id(node) in covered:
            continue
        if (call := _escaping_call(node.value.func, built, wrapped)) is not None:
            escaping.add(call)
    return escaping


def _escaping_call(target: ast.expr, built: set[str], wrapped: set[str]) -> str | None:
    """`<name>.<method>` when `target` is a non-lifecycle method of a built instance not wrapped."""
    if (
        isinstance(target, ast.Attribute)
        and isinstance(target.value, ast.Name)
        and target.value.id in built
        and target.attr not in _LIFECYCLE
        and f"{target.value.id}.{target.attr}" not in wrapped
    ):
        return f"{target.value.id}.{target.attr}"
    return None


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


_BUILDER: Final[str] = (
    "async def run(registry, vector):\n"
    "    store = registry.entry(NodeStore, 'x').factory(None)\n"
    "    await _search(store, vector)\n"
    "\n"
)


def test_the_check_follows_the_instance_into_a_helper() -> None:
    """`L28.52`: the helper half fails on its own, and a wrapped helper is its control."""
    # Arrange
    unwrapped = _BUILDER + (
        "async def _search(target, vector):\n    return await target.search(vector, 5)\n"
    )
    wrapped = _BUILDER + (
        "async def _search(target, vector):\n"
        "    async def _call():\n"
        "        return Produced(value=await target.search(vector, 5))\n"
        "    return await wrap(_call, distribution='d', contract='c', plugin='p')()\n"
    )
    through_methods = (
        "class Command:\n"
        "    async def run(self, registry, vector):\n"
        "        instance = registry.entry(NodeStore, 'x').factory(None)\n"
        "        await self._outer(vector, held=instance)\n"
        "    async def _outer(self, vector, *, held):\n"
        "        await type(self)._inner(held)\n"
        "    @staticmethod\n"
        "    async def _inner(pool):\n"
        "        await pool.search(None, 5)\n"
    )

    # Act
    found = unwrapped_calls(unwrapped, "helper.py")
    through_wrap = unwrapped_calls(wrapped, "helper.py")
    transitive = unwrapped_calls(through_methods, "methods.py")

    # Assert
    assert found == {"helper.py _search target.search"}
    assert through_wrap == set()
    assert transitive == {"methods.py _inner pool.search"}
