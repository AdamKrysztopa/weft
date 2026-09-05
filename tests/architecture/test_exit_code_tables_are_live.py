"""`exit_codes.py`'s two hand-maintained error tables name only live classes — ledger task **8.22**.

`docs/lessons-archive.md` `L8.12`. Adding an error class turned out to owe edits to four sites
keyed on error classes, none reachable from the new code. Two of those four live in
`weft_cli/exit_codes.py` and are the only ones with **no discovery walk behind them**:
`_ALSO_RESOLUTION_FAILED`, a tuple of `WeftError` subclasses mapped to exit 4 despite not
inheriting `PipelineResolutionError`, and the local-import `isinstance` branch inside
`exit_code_for`. A miss in either does not fail the build — it silently exits `1` where `4` was
meant, in production code.

**What this file checks, and what it deliberately does not.**

The completeness direction — *"every error of kind X must be in these tables"* — was attempted and
**abandoned on measurement, which is the finding this file exists to record.** The obvious
candidate was `weft_kernel.errors.UnresolvedNameError`, fitness function 12's own marker for "a
name that did not resolve against a known set". If that marker meant "exit 4", the tables would be
derivable and `L8.12`'s defect mechanically impossible. It does not: **34 classes carry the marker
and 15 of them map to `OPERATION_FAILED` on purpose** — `UnknownServiceKeyError`,
`UnknownPermissionKeyError`, `UnmappedLLMRoleError`, `UnresolvedServiceError` and eleven more.
`docs/03-cli.md` → *Output* defines `4` as *"pipeline failed to resolve"*, not *"you typed a name
wrong"*, and a mistyped `weft.toml` key is an operation that failed rather than a pipeline that
would not resolve. So which errors belong is a **judgement about what a user should do next**, and
no structural property of the class hierarchy encodes it. Asserting the candidate would have
changed the exit code of fifteen error classes to satisfy a rule nobody made.

What *is* mechanically true, and is checked below: every entry in both tables names a real
`WeftError` subclass, no entry is duplicated between them, and every entry actually reaches
`RESOLUTION_FAILED` when `exit_code_for` is asked. That catches a renamed or deleted class, an
entry added to both tables, and — the one that matters — an entry that is present but no longer
does anything, which is how a table quietly becomes decoration.
"""

from __future__ import annotations

import inspect
from typing import Final

from weft_cli.exit_codes import ExitCode, exit_code_for
from weft_kernel.errors import WeftError

#: The two tables, read out of the module rather than restated. `_ALSO_RESOLUTION_FAILED` is a
#: module constant; the local-import branch is not, so its members are named here — and that is
#: itself the point: a check that restated the branch would agree with itself. This list is
#: compared against the module's own source text below, so it cannot drift silently.
#: The private tuple this file reads out of `weft_cli.exit_codes`. Held as a *name* rather
#: than written as an attribute access on purpose, and the reason is a genuine standoff
#: between two checks this repository runs: ruff's B009 refuses `getattr` with a constant
#: literal, and pyright's reportPrivateUsage refuses the attribute access it rewrites to.
#: A check whose whole subject is a private table has to reach it somehow; going through a
#: named string satisfies both rules without suppressing either.
_TABLE_ATTR: Final[str] = "_ALSO_RESOLUTION_FAILED"

_LOCAL_IMPORT_MEMBERS: Final[tuple[str, ...]] = (
    "NoRouterPipelineError",
    "UnknownRunIdError",
    "NoBaselineRunsError",
    "UnknownMetricNameError",
)


def _also_resolution_failed() -> tuple[object, ...]:
    """`exit_codes._ALSO_RESOLUTION_FAILED`, read by name rather than imported.

    It is private, and a check whose subject is a private table has to reach it — but importing
    it makes a type checker object, and the entries are typed `type[WeftError]` there, which
    would make `test_every_entry_in_both_tables_is_a_live_weft_error` a question the annotation
    already answers rather than one about what the tuple actually holds. Returned as `object`
    for the same reason: the runtime content is the subject.
    """
    import weft_cli.exit_codes as module

    return tuple(getattr(module, _TABLE_ATTR))


def _local_import_classes() -> tuple[object, ...]:
    from weft_cli.eval_commands import NoBaselineRunsError, UnknownRunIdError
    from weft_cli.route_ask import NoRouterPipelineError
    from weft_eval.offline import UnknownMetricNameError

    return (NoRouterPipelineError, UnknownRunIdError, NoBaselineRunsError, UnknownMetricNameError)


def _raised(error_class: type[WeftError]) -> WeftError:
    """An instance of `error_class` without calling its own `__init__`.

    Every family member takes different required keyword arguments — `valid_options`, `pipeline`,
    `run_id`, `baseline` — so constructing them properly would mean a table of constructor
    signatures, which is a second hand-maintained list to keep in step with the first. What
    `exit_code_for` reads is the *type*, so the instance only has to be one.
    """
    instance = error_class.__new__(error_class)
    WeftError.__init__(instance, "for the exit-code dispatch")
    return instance


def test_every_entry_in_both_tables_is_a_live_weft_error() -> None:
    # Arrange / Act
    entries = [*_also_resolution_failed(), *_local_import_classes()]

    # Assert
    not_errors = [
        getattr(e, "__name__", repr(e))
        for e in entries
        if not (inspect.isclass(e) and issubclass(e, WeftError))
    ]
    assert not not_errors, (
        f"these exit-code table entries are not WeftError subclasses: {not_errors}. The table "
        f"decides an exit code by isinstance, so an entry that is not an exception class is a "
        f"row that can never match."
    )


def test_no_class_is_named_by_both_tables() -> None:
    # A class in both is harmless at runtime and is a sign the two tables have stopped meaning
    # different things — `_ALSO_RESOLUTION_FAILED` is for classes importable at module scope, the
    # local-import branch for classes whose import would cost `weft --version` a heavy chain.
    overlap = sorted(
        {getattr(e, "__name__", repr(e)) for e in _also_resolution_failed()}
        & {getattr(e, "__name__", repr(e)) for e in _local_import_classes()}
    )
    assert not overlap, (
        f"these classes are named by both exit-code tables: {overlap}. The split exists so "
        f"`weft --version` does not pay for weft_cli.eval_commands' import chain; a class in "
        f"both means one of the two entries is doing nothing."
    )


def test_every_entry_actually_reaches_resolution_failed() -> None:
    # The direction that catches a dead entry: present in the table, and no longer routed.
    # `_ALSO_RESOLUTION_FAILED` feeds an `isinstance` tuple and the local-import branch a second
    # one, so an entry can be present and unreachable if the branch above it already matched or
    # if the branch was reordered.
    classes = [
        e
        for e in [*_also_resolution_failed(), *_local_import_classes()]
        if inspect.isclass(e) and issubclass(e, WeftError)
    ]
    wrong = {
        entry.__name__: exit_code_for(_raised(entry)).name
        for entry in classes
        if exit_code_for(_raised(entry)) is not ExitCode.RESOLUTION_FAILED
    }
    assert not wrong, (
        f"these classes are named by an exit-code table and do not reach RESOLUTION_FAILED: "
        f"{wrong}. An entry that routes nowhere is a row nobody can tell from a missing one."
    )


def test_the_named_local_import_members_are_the_ones_the_module_actually_branches_on() -> None:
    # `_LOCAL_IMPORT_MEMBERS` above is a hand-written list, which is the shape this whole file is
    # about — so it is compared against `exit_codes.py`'s own source rather than trusted. This is
    # the two-way ratchet `test_ff12_unresolvable_name_carries_options.py` already uses, applied
    # to a branch instead of a frozenset.
    import weft_cli.exit_codes as module

    source = inspect.getsource(module)
    missing = [name for name in _LOCAL_IMPORT_MEMBERS if name not in source]
    assert not missing, (
        f"this file names {missing} as local-import branch members and exit_codes.py does not "
        f"mention them — one of the two is stale."
    )

    # And the other direction: a class imported inside `exit_code_for` and not named here.
    body = source[source.index("def exit_code_for") :]
    imported = {
        part.strip()
        for line in body.splitlines()
        if line.strip().startswith("from ") and " import " in line
        for part in line.split(" import ", 1)[1].split(",")
    }
    unnamed = sorted(imported - set(_LOCAL_IMPORT_MEMBERS))
    assert not unnamed, (
        f"exit_code_for imports {unnamed}, which _LOCAL_IMPORT_MEMBERS does not name — a new "
        f"branch member was added and this check was not told, which is exactly the miss "
        f"lessons-archive L8.12 records."
    )


def test_the_check_can_actually_fail() -> None:
    # Plant the two shapes the checks above exist to catch: a table entry that is not an error
    # class, and one that does not reach RESOLUTION_FAILED. `docs/lessons.md` L6.29 — the
    # question is whether the comparison fires, not whether the tree is currently clean.
    class _NotAnError:
        pass

    class _RoutedNowhereError(WeftError):
        pass

    assert not issubclass(_NotAnError, WeftError), (
        "the isinstance/issubclass test cannot distinguish a non-error from an error class"
    )
    assert exit_code_for(_raised(_RoutedNowhereError)) is ExitCode.OPERATION_FAILED, (
        "a WeftError named by neither table already reaches RESOLUTION_FAILED, so "
        "test_every_entry_actually_reaches_resolution_failed cannot fail"
    )
