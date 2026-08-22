"""Fitness function 15 — every `weft_kernel.resolution.resolve` call site passes `contributions=`.

Task **5.3a** (`S8`). Specified in `docs/01-high-level-plan.md` -> *Fitness functions*, item 15,
and `docs/02-extension-model.md` §3 → *Slots*. A pack's own `Contribution` only ever reaches a
pipeline if the `resolve()` call that produces it was actually handed one — `weft_cli.
registry_bootstrap.build_dependencies` is the one place every installed pack's own tuple is
assembled (`Dependencies.contributions`), but nothing at the language level stops a fourth
`resolve()` call site, added later, from being wired to everything *except* that one keyword
argument: it would still compile, still resolve, still pass every other test — and it would
silently make one pipeline's own slot un-fillable by any pack, forever, with no error anywhere.

**A new numbered function rather than a clause of an existing one.** The nearest neighbour is
item 14 (`test_ff14_ext_model_reaches_rehydration.py`), which checks the analogous "declared
versus present" property for `PackReport.ext_models` — but that one is a *runtime* fact,
comparing two sets computed by actually running discovery. This property is a *caller-shape*
fact: it holds or fails by inspection of the call, before anything runs at all, which is why
walking the AST rather than driving `discover()` is the right proof technique here, on the
identical reasoning item 13's own note gives for why a proof technique that answers a different
kind of question earns its own number rather than a shared clause.

**Structural, not textual.** A bare `grep -n "resolve("` over `weft-cli` matches `Runner.resolve`
(the kernel's own StageSpec-list resolver) and `ServiceRegistry.resolve` (an unrelated DI lookup)
in the same files this check cares about — `weft_cli.route_ask._run_pipeline` and `weft_cli.
ingest.run_index` each call both. Only a call to the bare name `resolve` — reachable exclusively
because a file's own `from weft_kernel.resolution import resolve` bound it there — is this
function's `resolve`; every other spelling is an attribute call (`ast.Attribute`, not `ast.Name`)
on some other object entirely, and this check reads that distinction directly off the parse tree
rather than guessing from the source text.
"""

import ast
from pathlib import Path
from typing import Final

from .conftest import REPO_ROOT

_CLI_SRC: Final[Path] = REPO_ROOT / "packages" / "weft-cli" / "src"


def _imports_resolve_as_a_bare_name(tree: ast.Module) -> bool:
    """Whether `tree`'s module body binds `resolve` via `from weft_kernel.resolution import
    resolve` — the only way a bare `resolve(...)` call in this tree can mean `weft_kernel.
    resolution.resolve` rather than some other object's own `.resolve` method.
    """
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.ImportFrom)
            and node.module == "weft_kernel.resolution"
            and any(alias.name == "resolve" for alias in node.names)
        ):
            return True
    return False


def _bare_resolve_calls(tree: ast.Module) -> list[ast.Call]:
    """Every `ast.Call` in `tree` whose function is the bare name `resolve` — never an
    attribute access (`runner.resolve(...)`, `service_registry.resolve(...)`), which is a
    different `resolve` on a different object entirely. See the module docstring.
    """
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "resolve"
    ]


def _passes_contributions(call: ast.Call) -> bool:
    return any(keyword.arg == "contributions" for keyword in call.keywords)


def _resolve_call_sites() -> dict[Path, list[ast.Call]]:
    """Every file under `weft-cli` that imports `resolve` as a bare name, and every call to
    it that file's own body makes — the whole population fitness function 0's own composite
    rule ("every architecture check runs in the gate") requires this test to check, not a
    hand-picked subset of it.
    """
    sites: dict[Path, list[ast.Call]] = {}
    for path in sorted(_CLI_SRC.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        if not _imports_resolve_as_a_bare_name(tree):
            continue
        calls = _bare_resolve_calls(tree)
        if calls:
            sites[path] = calls
    return sites


def test_at_least_one_call_site_is_found() -> None:
    # Floor — `08` §3's shape, applied to a source walk instead of a document walk: a walk
    # that finds nothing passes every check below vacuously, which would make this file
    # prove nothing at all the day every call site it currently finds is refactored away
    # without anyone noticing this test stopped checking anything.
    sites = _resolve_call_sites()
    assert sites, (
        f"no file under {_CLI_SRC} imports `resolve` from weft_kernel.resolution as a bare "
        f"name and calls it — the walk itself is broken; fix it before trusting the check below."
    )


def test_every_resolve_call_site_passes_contributions() -> None:
    sites = _resolve_call_sites()
    offenders = [
        f"{path.relative_to(REPO_ROOT)}:{call.lineno}"
        for path, calls in sites.items()
        for call in calls
        if not _passes_contributions(call)
    ]
    assert not offenders, (
        f"the following call(s) to weft_kernel.resolution.resolve() do not pass "
        f"`contributions=`, which means any Contribution an installed pack offers can never "
        f"reach the pipeline resolved there: {offenders}. Pass "
        f"`contributions=deps.contributions` (or thread it from whichever caller already "
        f"has `Dependencies` in scope) — see `weft_cli.registry_bootstrap.Dependencies."
        f"contributions`'s own docstring."
    )


def test_the_check_can_actually_fail(tmp_path: Path) -> None:
    # Arrange — a file shaped exactly like a fourth call site that forgot the keyword: it
    # imports `resolve` as a bare name and calls it without `contributions=`.
    offending = tmp_path / "forgetful_caller.py"
    offending.write_text(
        "from weft_kernel.resolution import resolve\n"
        "\n"
        "\n"
        "def run(pipeline, *, registry, contracts, parents):\n"
        "    return resolve(pipeline, registry=registry, contracts=contracts, parents=parents)\n"
    )
    tree = ast.parse(offending.read_text(encoding="utf-8"))

    # Act
    assert _imports_resolve_as_a_bare_name(tree)
    calls = _bare_resolve_calls(tree)

    # Assert — this is exactly the shape `test_every_resolve_call_site_passes_contributions`
    # would report as an offender, proving the check catches the regression it exists for
    # rather than passing merely because it stopped being able to fail.
    assert len(calls) == 1
    assert not _passes_contributions(calls[0])
