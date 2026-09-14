"""Fitness function **32** — a tenant a caller can choose fails the gate, naming Phase 22b.

**G23, settled 2026-09-14 on position 1: an in-process caller is the operator, and the deployment
stays the boundary** (`docs/01-high-level-plan.md` → *Multi-tenancy in the core*,
`docs/02-extension-model.md` §2). Every pack shares one interpreter, one set of credentials and one
connection, so a tenant chosen inside the process is a label and enforces nothing. `01`'s deferral
row used to carry a trigger — *an in-process caller that is not `weft-cli`* — that fired on the
embedded API the day after it was written and was not measured. A trigger nobody measures is a
sentence; this is the replacement made a check, so the next firing is a red gate rather than a
review noticing a day late.

**The property is keyed on where a `Context` is minted, never on today's signatures.** A check
phrased as *"no `tenant` parameter on `Weft.open`"* passes an HTTP adapter that reads the tenant
from a header. What every route to a caller-chosen tenant has to do is put one into a `Context`,
and a frozen `Context` offers two ways: construct one, or `replace` a field on one already built.
So, over every tracked module under the two shipped source roots:

- **(a)** `weft_engine.api.new_context` is the only function that calls `Context(...)`; it takes no
  parameter at all, and passes `tenant_id` as the literal `"default"` by keyword.
- **(b)** no call to `replace` — `dataclasses.replace`, `copy.replace`, a bare import of either, or
  `__replace__` — passes `tenant_id`, and no `setattr` or `__setattr__` names it.

**Structural, not textual, and this was decided first because the population forces it.**
`weft_cli/pack_new.py` carries `Context(tenant_id="t", ...)` inside a template string: the test
file `weft pack new` writes into a *pack author's* tree, run by their test process, against no
deployment — the same thing every `examples/*/tests` fixture is. A textual walk would see it and
could only waive it, and a waiver entry that is not a mint site is where a real one would hide
(`R10.2`); an `ast` walk sees a string and nothing in it, which is `L5.23`'s structural rule.
**Blind spot:** a `Context` built without naming it — `type(ctx)(...)`, a class reached through
`getattr` — and any adapter outside this repository.

**The one waiver** is the store conformance kit's fixture, `weft_store.conformance`
`_conformance_context`, which a pack author's test suite runs against their store with no
deployment behind it. Pinned; a second entry is a visible act in a diff.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import Final

from .conftest import REPO_ROOT, tracked_files

_SHIPPED_ROOTS: Final[tuple[str, ...]] = (
    "packages/weft-rag/src/",
    "packages/weft-kernel/src/",
)

MINT_SITE: Final[tuple[str, str]] = ("packages/weft-rag/src/weft_engine/api.py", "new_context")

DEFAULT_TENANT: Final[str] = "default"

WAIVED_MINT_SITES: Final[frozenset[tuple[str, str]]] = frozenset(
    {("packages/weft-rag/src/weft_store/conformance.py", "_conformance_context")}
)

_REPLACERS: Final[frozenset[str]] = frozenset({"replace", "__replace__"})
_SETTERS: Final[frozenset[str]] = frozenset({"setattr", "__setattr__"})

_WHY: Final[str] = (
    "A tenant a caller can choose is Phase 22b's trigger — isolation machinery is WON'T yet, and "
    "G23 settled that an in-process caller is the operator and the deployment is the boundary "
    "(docs/01-high-level-plan.md → Multi-tenancy in the core; docs/02-extension-model.md §2). "
    "Open Phase 22b rather than widening this check."
)


@dataclass(frozen=True, slots=True)
class _Mint:
    function: str | None
    function_node: ast.FunctionDef | ast.AsyncFunctionDef | None
    call: ast.Call


def _callee_name(call: ast.Call) -> str | None:
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return None


def _mints(tree: ast.AST) -> list[_Mint]:
    """Every `Context(...)` call, with the innermost function that makes it."""
    found: list[_Mint] = []

    def visit(node: ast.AST, owner: ast.FunctionDef | ast.AsyncFunctionDef | None) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef):
                visit(child, child)
                continue
            if isinstance(child, ast.Call) and _callee_name(child) == "Context":
                found.append(_Mint(owner.name if owner else None, owner, child))
            visit(child, owner)

    visit(tree, None)
    return found


def _takes_parameters(function: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    arguments = function.args
    return bool(
        arguments.posonlyargs
        or arguments.args
        or arguments.kwonlyargs
        or arguments.vararg
        or arguments.kwarg
    )


def _passes_the_default_tenant(call: ast.Call) -> bool:
    if call.args or any(keyword.arg is None for keyword in call.keywords):
        return False
    tenants = [keyword.value for keyword in call.keywords if keyword.arg == "tenant_id"]
    return (
        len(tenants) == 1
        and isinstance(tenants[0], ast.Constant)
        and tenants[0].value == DEFAULT_TENANT
    )


def _violations(path: str, source: str) -> list[str]:
    """Every way `source`, read as the module at `path`, lets a tenant be chosen."""
    tree = ast.parse(source)
    found: list[str] = []

    for mint in _mints(tree):
        site = (path, mint.function or "<module>")
        if site in WAIVED_MINT_SITES:
            continue
        where = f"{path}:{mint.call.lineno}"
        if site != MINT_SITE:
            found.append(f"{where} mints a Context in {site[1]}, not in new_context")
            continue
        if mint.function_node is not None and _takes_parameters(mint.function_node):
            found.append(f"{where} new_context takes a parameter — a tenant a caller can pass")
        if not _passes_the_default_tenant(mint.call):
            found.append(
                f"{where} new_context passes a tenant_id other than the literal "
                f"{DEFAULT_TENANT!r} by keyword"
            )

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        callee = _callee_name(node)
        if callee in _REPLACERS and any(k.arg == "tenant_id" for k in node.keywords):
            found.append(f"{path}:{node.lineno} replaces tenant_id on a Context already built")
        if callee in _SETTERS and any(
            isinstance(arg, ast.Constant) and arg.value == "tenant_id" for arg in node.args
        ):
            found.append(f"{path}:{node.lineno} sets tenant_id on a Context already built")

    return found


def _shipped_modules() -> list[str]:
    return sorted(
        name
        for name in tracked_files()
        if name.endswith(".py") and name.startswith(_SHIPPED_ROOTS) and (REPO_ROOT / name).is_file()
    )


def _read(name: str) -> str:
    return (REPO_ROOT / name).read_text(encoding="utf-8")


def test_a_tenant_is_minted_only_by_new_context_and_never_replaced() -> None:
    # Arrange
    modules = _shipped_modules()
    assert modules, "no tracked module under the shipped roots — the walk is wrong, not the tree"

    # Act
    found = [violation for name in modules for violation in _violations(name, _read(name))]

    # Assert
    assert not found, _WHY + "\n  " + "\n  ".join(found)


def test_the_mint_site_and_the_waiver_are_live() -> None:
    """Both named sites still mint exactly one `Context`, so neither constant describes nothing.

    A renamed `new_context` would turn its own call into a finding, which is loud; a waived fixture
    that stopped minting would leave an entry suppressing nothing, which is silent (`L6.29`).
    """
    for path, function in {MINT_SITE, *WAIVED_MINT_SITES}:
        # Act
        mints = [mint for mint in _mints(ast.parse(_read(path))) if mint.function == function]

        # Assert
        assert len(mints) == 1, f"{path}:{function} mints {len(mints)} Context(s), expected 1"


def test_a_context_inside_a_string_is_not_a_mint_site() -> None:
    """The structural decision, pinned: `weft pack new`'s template is text, not a mint site."""
    # Arrange
    source = 'TEMPLATE = """\\ndef _ctx():\\n    return Context(tenant_id="t")\\n"""\n'

    # Act
    found = _violations("packages/weft-rag/src/weft_cli/pack_new.py", source)

    # Assert
    assert found == []
    assert "Context(" in _read("packages/weft-rag/src/weft_cli/pack_new.py")


def test_the_check_can_actually_fail() -> None:
    """Four planted disagreements, each through `_violations` itself, each naming its line.

    The first two are the plants task 22.0 names — a tenant threaded from `Weft.open` into
    `new_context`, and a `replace` of `tenant_id` — and the third is 24b's shape: an adapter that
    never touches `new_context`'s signature and builds its own `Context` from a header.
    """
    # Arrange
    api = MINT_SITE[0]
    adapter_path = "packages/weft-rag/src/weft_http/app.py"
    threaded = (
        "def new_context(tenant: str) -> Context:\n"
        '    return Context(tenant_id=tenant, run_id="r", trace_id="t", locale="en")\n'
    )
    replaced = (
        "import dataclasses\n"
        "def _invoke(tenant):\n"
        "    return dataclasses.replace(new_context(), tenant_id=tenant)\n"
    )
    adapter = (
        "from weft_kernel.context import Context\n"
        "def handle(request):\n"
        '    return Context(tenant_id=request.headers["X-Tenant"], run_id="r", '
        'trace_id="t", locale="en")\n'
    )
    forced = 'def _invoke(ctx, tenant):\n    object.__setattr__(ctx, "tenant_id", tenant)\n'

    # Act
    results = {
        "threaded": _violations(api, threaded),
        "replaced": _violations(api, replaced),
        "adapter": _violations(adapter_path, adapter),
        "forced": _violations(api, forced),
    }

    # Assert
    assert any("takes a parameter" in v for v in results["threaded"]), results
    assert any("other than the literal 'default'" in v for v in results["threaded"]), results
    assert results["replaced"] == [f"{api}:3 replaces tenant_id on a Context already built"]
    assert results["adapter"] == [f"{adapter_path}:3 mints a Context in handle, not in new_context"]
    assert results["forced"] == [f"{api}:2 sets tenant_id on a Context already built"]
    assert "Phase 22b" in _WHY
