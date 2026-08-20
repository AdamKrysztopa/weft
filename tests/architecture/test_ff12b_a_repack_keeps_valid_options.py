"""Fitness function 12, second clause — a catch site cannot discard what a raise site cannot
omit. `01` -> *Fitness functions* item 12; `docs/build-ledger.md` 2.36 turns FF12 on; this file
is the check the 2026-08-20 repair (`402a957`) asked for and did not itself add.

**Why FF12's structural check, on its own, missed two real Phase 3 defects.** `test_ff12_
unresolvable_name_carries_options.py` proves every *named* family member carries `valid_options`
— but membership is opt-in (`issubclass(cls, UnresolvedNameError)`), and a raise site that never
mixes the marker in is invisible to it. Commit `402a957` found two: `weft_cli.permission_policy`
computed the valid `[permissions]` keys and interpolated them straight into a bare `WeftError`'s
message, never joining the family; `weft_cli.registry_bootstrap.require_plugin` caught
`weft_kernel.registry.UnknownPluginError` — which *does* carry `valid_options` — and discarded it
into `plain=str(exc)` before raising a bare `CommandRefusalError`. Both were repaired by hand.
This file is the machinery that should have caught the second shape before a human found it.

**Two candidate heuristics were weighed, and only one shipped — measured, not guessed.** The
module docstring of `test_ff12_unresolvable_name_carries_options.py` already states the reference's
own lesson: *"doing it by hand at nine sites is why three sites do not."* Building a checker that
also does it by hand — a list of excluded raise sites — repeats the exact failure this whole
function exists to prevent, one layer up.

1. *Rejected, with evidence*: flag any `raise` of a `WeftError` subclass outside the family whose
   message was built from a `sorted(...)`, a comprehension, or a `str.join(...)` call — the shape
   `weft_cli.permission_policy`'s pre-repair site had. Measured against the real tree (every
   first-party module, the identical import-and-walk this file's own check below performs): **13
   raise sites match the syntactic shape, and 11 of the 13 are not name-resolution failures at
   all** — a closed `StrEnum`'s value check, a contract shape violation, an inert pin, a Pydantic
   validation report, a type-provision gap, a pipeline cycle, a slot-ordering collision, a
   fallback's capability mismatch, an API error, an unused-field report, and a missing required
   locale. Distinguishing "these are the *valid alternatives* for a name" from "this is some
   *other* enumerable fact this raise happens to report" is a question about what the code
   *means*, not what it is shaped like, and AST structure alone cannot answer it — the same
   reference lesson, applied to the checker itself: a heuristic precise enough to need no
   hand-maintained exclusion list would have to re-derive, structurally, the judgement task 2.36's
   own audit made by reading every site. (The other 2 of the 13 are real: see the module docstring
   of the ledger entry this task's own report cites — reported, not fixed here.)
2. *Shipped*: the catch-and-repack shape below. It does not ask what a collection *means*; it asks
   a single mechanical question the language itself already answers — does the class actually
   caught here have a `valid_options` field, and does the class actually raised have one too. This
   is exactly finding 2's own shape, and it is empirically silent on the current tree: zero matches
   across all 130 first-party modules, which is why `CATCH_AND_REPACK_WAIVER` below ships pinned
   empty rather than pre-populated.

**The shape.** A `try`/`except` inside a function, where the handler names a single exception type
(`except SomeError as exc:`, never a tuple or a bare `except:`) that resolves, in the enclosing
module's own namespace, to an `UnresolvedNameError` subclass — a class fitness function 12's own
structural check has already proven carries `valid_options`. If that handler's body raises a
*new* exception (`raise Other(...)`, a call, never a bare `raise` or `raise exc` — both of those
preserve the original object, structure and all) whose class is a `WeftError` subclass that is
**not** an `UnresolvedNameError` subclass, the structured alternative the catch site *had* cannot
have survived into what it raised, because the class it raised has nowhere to put it. No text is
read at any point — `_catch_and_repack_findings` below never inspects a message string, only
`issubclass` and the AST's own shape, the identical discipline `_carries_valid_options_field` in
`test_ff12_unresolvable_name_carries_options.py` already holds for the family's own constructors.

**What this cannot see, stated rather than papered over.** Finding 2's own historical shape did
not raise in the same function that caught: `require_plugin` caught `UnknownPluginError` and
*returned* a plain value; the untyped `CommandRefusalError` was raised two modules away, in
`weft_cli.commands`, built from data that had already been flattened to a string in between. A
purely lexical, single-function check cannot follow a caught error's structured field through an
arbitrary return value into an arbitrary later caller without the kind of interprocedural
data-flow analysis that stops being a fast, legible check and starts being a second interpreter —
`test_a_return_based_discard_is_not_flagged_this_is_a_stated_limit` below proves this directly: a
return-based version of the identical discard is not flagged, on purpose, because this file would
rather say plainly what it cannot do than pretend a heuristic reaches further than it does.
"""

from __future__ import annotations

import ast
import importlib
import inspect
import pkgutil
import tomllib
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Final, cast

from weft_kernel.errors import UnresolvedNameError, WeftError

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
PACKAGES_ROOT: Final[Path] = REPO_ROOT / "packages"

#: `01`'s own ratchet shape, item 0's style, restated for this clause. **Pinned empty** — the
#: real-tree run below found nothing to waive (see the module docstring's measurement), and an
#: entry here is a dated decision-log act, never a place to park an unreviewed finding.
CATCH_AND_REPACK_WAIVER: Final[frozenset[str]] = frozenset()


def _first_party_top_level_packages() -> tuple[str, ...]:
    """Every first-party distribution's top-level import name, off `packages/*/pyproject.toml`.

    Restated rather than imported from `test_ff12_unresolvable_name_carries_options.py` — that
    file's own precedent (itself citing `test_ff11_pipeline_integrity.py`'s "one self-contained
    scenario" reasoning) for why a shared computation is duplicated across architecture tests
    rather than threaded through an import between test modules.
    """
    names: list[str] = []
    for package_dir in sorted(p for p in PACKAGES_ROOT.iterdir() if p.is_dir()):
        pyproject = package_dir / "pyproject.toml"
        if not pyproject.is_file():
            continue
        with pyproject.open("rb") as handle:
            document = tomllib.load(handle)
        project = cast("dict[str, object]", document.get("project", {}))
        name = project.get("name")
        if isinstance(name, str):
            names.append(name.replace("-", "_"))
    return tuple(names)


_FIRST_PARTY_TOP_LEVEL_PACKAGES: Final[tuple[str, ...]] = _first_party_top_level_packages()


def _every_first_party_module() -> tuple[ModuleType, ...]:
    """Every submodule of every first-party distribution, imported — the identical walk `test_
    ff12_unresolvable_name_carries_options.py`'s own `_import_every_first_party_module` performs,
    returning the modules themselves rather than only having imported them: this check needs each
    module's own source and namespace, not only its classes.
    """
    modules: list[ModuleType] = []
    for top_level in _FIRST_PARTY_TOP_LEVEL_PACKAGES:
        package = importlib.import_module(top_level)
        package_path = getattr(package, "__path__", None)
        if package_path is None:
            continue
        prefix = f"{top_level}."
        for module_info in pkgutil.walk_packages(package_path, prefix=prefix):
            modules.append(importlib.import_module(module_info.name))
    return tuple(modules)


def _raised_class_name(node: ast.Raise) -> str | None:
    """The bare name a `raise` statement constructs, or `None` if it is not a call at all —
    a bare `raise` or `raise exc` keeps the same object, `valid_options` and all, intact, so
    neither is this shape's concern. Split out of `_catch_and_repack_findings` below purely to
    keep that function's own branching under `ruff`'s complexity budget, the identical reason
    `weft_cli.cli._render_result` became a dispatch table in the 2026-08-20 repair — a function
    the family walk this file measured against, not a coincidence.
    """
    if not isinstance(node.exc, ast.Call):
        return None
    callee = node.exc.func
    if isinstance(callee, ast.Name):
        return callee.id
    if isinstance(callee, ast.Attribute):
        return callee.attr
    return None


def _handler_catches_a_family_member(
    handler: ast.ExceptHandler, *, resolve: Callable[[str], object | None]
) -> str | None:
    """The caught type's own bare name, if `handler` names exactly one exception type and it
    resolves to an `UnresolvedNameError` subclass — `None` otherwise. A tuple of exception types
    or a bare `except:` is out of scope, stated in `_catch_and_repack_findings`'s own docstring.
    """
    if not isinstance(handler.type, ast.Name):
        return None
    caught = resolve(handler.type.id)
    if inspect.isclass(caught) and issubclass(caught, UnresolvedNameError):
        return handler.type.id
    return None


def _repack_findings_in_handler(
    handler: ast.ExceptHandler, *, caught_name: str, resolve: Callable[[str], object | None]
) -> tuple[str, ...]:
    """Every `raise` inside `handler` that repacks `caught_name`'s catch into a `WeftError`
    with nowhere to put `valid_options` — see `_catch_and_repack_findings`'s own docstring for
    the shape and its stated scope.
    """
    findings: list[str] = []
    for stmt in ast.walk(handler):
        if not isinstance(stmt, ast.Raise):
            continue
        raised_name = _raised_class_name(stmt)
        if raised_name is None:
            continue
        raised = resolve(raised_name)
        if not (inspect.isclass(raised) and issubclass(raised, WeftError)):
            continue  # not a WeftError at all — outside this family's concern
        if issubclass(raised, UnresolvedNameError):
            continue  # the raised class has somewhere to put valid_options — fine
        findings.append(
            f"{stmt.lineno} catches {caught_name} (carries valid_options) and raises "
            f"{raised_name} (does not)"
        )
    return tuple(findings)


def _catch_and_repack_findings(
    tree: ast.Module, *, resolve: Callable[[str], object | None]
) -> tuple[str, ...]:
    """The catch-and-repack shape (module docstring), found in `tree` — a pure function taking a
    parsed module and a name resolver, so a synthetic snippet can drive it directly in a test
    exactly as `members_without_the_typed_field` in the sibling file takes a plain `frozenset`
    rather than performing its own discovery — `weft_cli.contract_reference.missing_from_walked_
    set`'s own precedent, restated there: "the check has something to call that is not the same
    code path it is checking."

    `resolve` maps a bare name as it appears in the source (`handler.type.id`, or a raised call's
    `Name`/the final `.attr` of an `Attribute`) to whatever class is bound to it in the scope that
    source came from — for a real module, `module.__dict__.get`; for a synthetic snippet, a plain
    `dict.get`. Neither `handler.type` nor a raised call's `func` is resolved when it is anything
    but a bare name or a dotted attribute access — a tuple of exception types or a bare `except:`
    is out of scope, stated rather than silently mishandled: every real site in the tree today
    names exactly one exception type by its own imported name (confirmed by the module docstring's
    zero-finding run), and a multi-type catch cannot promise `valid_options` is even present
    without a runtime `isinstance` narrowing an AST walk cannot perform.
    """
    findings: list[str] = []
    for func_node in ast.walk(tree):
        if not isinstance(func_node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        for try_node in ast.walk(func_node):
            if not isinstance(try_node, ast.Try):
                continue
            for handler in try_node.handlers:
                caught_name = _handler_catches_a_family_member(handler, resolve=resolve)
                if caught_name is None:
                    continue
                findings.extend(
                    f"{func_node.name}:{finding}"
                    for finding in _repack_findings_in_handler(
                        handler, caught_name=caught_name, resolve=resolve
                    )
                )
    return tuple(findings)


def _real_tree_findings() -> tuple[str, ...]:
    """`_catch_and_repack_findings`, run against every first-party module's own real source and
    namespace — the check itself, separated from the assertion so the self-tests below can drive
    the pure function on synthetic input without importing the whole tree twice.
    """
    findings: list[str] = []
    for module in _every_first_party_module():
        try:
            source = inspect.getsource(module)
        except (OSError, TypeError):
            continue  # no source to read — nothing this check can examine
        tree = ast.parse(source)
        module_findings = _catch_and_repack_findings(tree, resolve=module.__dict__.get)
        findings.extend(f"{module.__name__}.{finding}" for finding in module_findings)
    return tuple(findings)


# --- the coverage check itself: nothing in the tree repacks silently ------------------------


def test_waiver_list_is_empty() -> None:
    # `07` §2's own ratchet policy, restated for this clause: an exemption is a visible entry in
    # a diff, changeable only by a dated decision-log entry — and the module docstring's own
    # measurement is why this one ships with nothing in it rather than merely small.
    assert frozenset() == CATCH_AND_REPACK_WAIVER


def test_no_catch_and_repack_escapes_across_the_first_party_tree() -> None:
    # Arrange / Act
    findings = frozenset(_real_tree_findings())

    # Assert
    unwaived = findings - CATCH_AND_REPACK_WAIVER
    assert not unwaived, (
        f"catch-and-repack site(s) discard a caught name's valid_options: {sorted(unwaived)} — "
        f"`01` requirement 5's other half: a caught `UnresolvedNameError` family member's "
        f"alternatives must survive into whatever is raised instead, or the caller sees a "
        f"refusal with nothing to compare a typo against. Either raise the caught error itself "
        f"(or an unmodified `raise`), raise a family member that carries `valid_options` forward "
        f"(`weft_kernel.runner`'s own fallback chain does this), or, if this site genuinely is not "
        f"a name-resolution failure, add a dated decision-log entry and name it in "
        f"CATCH_AND_REPACK_WAIVER."
    )


# --- the self-test: proven able to fail, proven not to cry wolf -----------------------------

#: Stand-ins for real family members and a real bare `WeftError` subclass, shaped exactly like
#: `weft_kernel.registry.UnknownPluginError`/`weft_cli.commands.CommandRefusalError` (a family
#: member and, pre-repair, its bare sibling) and `weft_kernel.runner.UnknownFallbackError` (the
#: correct shape: a second family member the caught one's data is carried forward into) — never
#: the real classes themselves, so this self-test cannot be made to pass by a change to either.


class _CaughtHasOptionsError(WeftError, UnresolvedNameError):
    def __init__(self, message: str, *, valid_options: tuple[str, ...]) -> None:
        super().__init__(message)
        self.valid_options = valid_options


class _RaisedHasNoOptionsError(WeftError):
    pass


class _RaisedAlsoHasOptionsError(WeftError, UnresolvedNameError):
    def __init__(self, message: str, *, valid_options: tuple[str, ...]) -> None:
        super().__init__(message)
        self.valid_options = valid_options


_STAND_INS: Final[dict[str, type[object]]] = {
    "_CaughtHasOptionsError": _CaughtHasOptionsError,
    "_RaisedHasNoOptionsError": _RaisedHasNoOptionsError,
    "_RaisedAlsoHasOptionsError": _RaisedAlsoHasOptionsError,
}

#: Finding 2's own mechanism (module docstring), reconstructed in one function rather than
#: threaded through two modules and a return value — the shape this file's check can actually
#: see. `weft_cli.registry_bootstrap.require_plugin`'s pre-repair body, restated with the stand-in
#: names above rather than copied: catch, discard into `str(exc)`, raise the bare sibling.
_REPACK_VIOLATION_SOURCE: Final[str] = """
def resolve_or_refuse(registry, name):
    try:
        registry.entry(name)
    except _CaughtHasOptionsError as exc:
        raise _RaisedHasNoOptionsError(f"unknown name: {name} ({exc})") from exc
"""

#: The correct shape — `weft_kernel.runner._chain`'s own fallback path, restated: the caught
#: error's discarded, but what it raises is itself a family member carrying its own
#: `valid_options`, recomputed rather than lifted from `exc`. Must not be flagged, or this file
#: is measuring "did this function catch a family member" rather than what it claims to.
_CORRECT_REPACK_SOURCE: Final[str] = """
def resolve_or_refuse(registry, name):
    try:
        registry.entry(name)
    except _CaughtHasOptionsError as exc:
        registered = tuple(sorted(registry.names_for(name)))
        raise _RaisedAlsoHasOptionsError(
            f"no such name: {registered}", valid_options=registered
        ) from exc
"""

#: A bare re-raise — the caught object itself, unmodified, propagates. Must not be flagged: no
#: `WeftError` is even constructed here, the identical object with its identical `valid_options`
#: reaches the caller.
_BARE_RERAISE_SOURCE: Final[str] = """
def resolve_or_refuse(registry, name):
    try:
        registry.entry(name)
    except _CaughtHasOptionsError:
        raise
"""

#: Finding 2's own *literal* historical shape: the discard happens, but by `return`, not `raise`
#: — the untyped exception is constructed two modules away, from the returned string. The module
#: docstring's own stated limit, proven directly: this file's check cannot see it.
_RETURN_BASED_DISCARD_SOURCE: Final[str] = """
def require_plugin(registry, name):
    try:
        registry.entry(name)
    except _CaughtHasOptionsError as exc:
        return str(exc)
"""


def test_the_check_can_actually_fail() -> None:
    # The vacuousness proof `07` §2 requires, `test_ff9c_every_contract_has_a_stranger.py`'s own
    # `test_the_discovery_ratchet_can_actually_fail` shape: a real violation, planted as source
    # text rather than asserted about, must be caught.
    tree = ast.parse(_REPACK_VIOLATION_SOURCE)

    findings = _catch_and_repack_findings(tree, resolve=_STAND_INS.get)

    assert findings == (
        "resolve_or_refuse:6 catches _CaughtHasOptionsError (carries valid_options) and raises "
        "_RaisedHasNoOptionsError (does not)",
    )


def test_the_correct_shape_is_not_flagged() -> None:
    # The other direction — a catch-and-repack that *does* carry the field forward (by
    # recomputing it, `weft_kernel.runner._chain`'s own real pattern) must not be reported, or
    # this check is measuring "did this function catch a family member" rather than "did it lose
    # what the family member carried."
    tree = ast.parse(_CORRECT_REPACK_SOURCE)

    findings = _catch_and_repack_findings(tree, resolve=_STAND_INS.get)

    assert findings == ()


def test_a_bare_reraise_is_not_flagged() -> None:
    # `raise` with no expression re-raises the exact object caught, `valid_options` and all —
    # no `WeftError` is constructed at this site, so there is nothing to check.
    tree = ast.parse(_BARE_RERAISE_SOURCE)

    findings = _catch_and_repack_findings(tree, resolve=_STAND_INS.get)

    assert findings == ()


def test_a_return_based_discard_is_not_flagged_this_is_a_stated_limit() -> None:
    # The module docstring's own honesty, made a fact rather than a claim: finding 2's literal
    # historical shape discarded `exc` into a `return`, and the untyped exception was raised two
    # modules away. This check is lexical and single-function; it cannot and does not follow a
    # value through an arbitrary return into an arbitrary later caller. If this assertion ever
    # starts failing, the check has grown a capability its own docstring does not yet claim.
    tree = ast.parse(_RETURN_BASED_DISCARD_SOURCE)

    findings = _catch_and_repack_findings(tree, resolve=_STAND_INS.get)

    assert findings == ()
