"""A command's permission class is enforced on the path a library caller uses — ledger task **7.0**.

`docs/05-grilling-sessions.md` → G12, settled 2026-09-06, and `docs/03-cli.md` → *Permissions* →
*What a permission class means when the caller is never a TTY*. The gate G12 depends on was called
from exactly one place — inside `weft_cli.cli.run_command`, which takes an `argparse.Namespace` and
returns a `Rendered`. The typed result task 7.3 requires comes from `Command.run`, and **nothing
gated `Command.run`**. So the ceiling G12 settled was prose on the exact path Phase 7 is told to
take: the *control that looks like enforcement and is not* which `02` §2 refuses.

**The repair is not "call the gate from a second place".** That reproduces the defect one caller
later, and `docs/lessons.md` `L8.31` is the general form: placing a concern at *"the one place that
calls X"* is a bet there will never be a second caller, and the bet's expiry is written down
nowhere. What this task makes true is that **the invocation seam itself takes the consent decision
as a required argument**, so a caller that has not made one cannot construct the call at all. That
is the same shape `CLAUDE.md` already requires of every other cross-cutting concern: attached at the
seam, never left to a rule an author must remember.

**`Consent` is a Protocol rather than a policy object, and that keeps `weft-command` clean.**
The seam must not learn `weft.toml`, `PermissionPolicy` or what a TTY is — those belong to the
driving adapter, per `03`'s governing rule. It asks one question and takes whatever answer it is
given: `weft-cli` answers with the TTY prompt it already ships, and an agent answers *"refuse
every ask-class operation"*. Two callers, one seam, and neither can skip it.
"""

from __future__ import annotations

import inspect
from typing import ClassVar

import pytest
from pydantic import BaseModel

from weft_command.contract import COMMAND_CONTRACT_VERSION, CommandResult
from weft_command.permission import PermissionClass
from weft_kernel.context import Context
from weft_kernel.payload import Outcome, Produced


class _Args(BaseModel):
    target: str = "a-collection"


class _Result(CommandResult):
    ran: bool


class _Wipe:
    """A `destroy`-class command that declares nothing else — a stranger's, in every sense.

    `weft_cli.confirm`'s own argument is that a pack's destructive command is refused "with no
    cooperation from its author"; this class is what proves the same of the library path.
    """

    # Annotated rather than inferred: `type[_Args]` is not assignable to the Protocol's
    # `type[BaseModel]` under invariance, and this double is passed to a parameter typed
    # `Command` — which `tests/unit/weft_command/test_contract.py`'s own double never is.
    version: ClassVar[str] = COMMAND_CONTRACT_VERSION
    args_model: ClassVar[type[BaseModel]] = _Args
    result_model: ClassVar[type[CommandResult]] = _Result
    permission_class: ClassVar[PermissionClass] = PermissionClass.DESTROY
    help: ClassVar[str] = "wipe a collection"
    required_declarations: ClassVar[tuple[str, ...]] = ("permission_class", "help")

    def __init__(self) -> None:
        self.ran = False

    async def run(self, args: BaseModel, ctx: Context) -> Outcome[CommandResult]:
        self.ran = True
        return Produced(value=_Result(ran=True))


class _Reader(_Wipe):
    """A `read`-class command — the class the seam must let through untouched."""

    permission_class: ClassVar[PermissionClass] = PermissionClass.READ


class _Refusing:
    """The consent a caller with no TTY gives: it refuses every ask-class operation."""

    def __init__(self) -> None:
        self.asked: list[str] = []

    async def decide(self, *, command_name: str, instance: object, args: BaseModel) -> None:
        self.asked.append(command_name)
        permission_class = getattr(instance, "permission_class", None)
        if permission_class in (PermissionClass.OVERWRITE, PermissionClass.DESTROY):
            raise PermissionError(f"'{command_name}' needs consent this caller cannot give")


class _Permitting:
    def __init__(self) -> None:
        self.asked: list[str] = []

    async def decide(self, *, command_name: str, instance: object, args: BaseModel) -> None:
        self.asked.append(command_name)


def _context() -> Context:
    return Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")


@pytest.mark.asyncio
async def test_a_permitted_command_runs_and_returns_its_typed_result() -> None:
    # Arrange
    from weft_command.invocation import invoke

    instance = _Reader()

    # Act
    outcome = await invoke(
        command_name="peek",
        instance=instance,
        args=_Args(),
        ctx=_context(),
        consent=_Permitting(),
        distribution="weft-canary",
    )

    # Assert — the typed result, not a rendered string: this is what task 7.3 requires.
    assert isinstance(outcome, Produced)
    assert isinstance(outcome.value, CommandResult)
    assert instance.ran is True


@pytest.mark.asyncio
async def test_the_seam_asks_for_consent_on_every_command_whatever_its_class() -> None:
    # The seam does not decide which classes are interesting — the `Consent` implementation does.
    # A seam that pre-filtered would put the class table in two places, and `docs/03-cli.md` keeps
    # the classes the adapter's policy rather than the contract's.
    from weft_command.invocation import invoke

    consent = _Permitting()
    await invoke(
        command_name="peek",
        instance=_Reader(),
        args=_Args(),
        ctx=_context(),
        consent=consent,
        distribution="weft-canary",
    )

    assert consent.asked == ["peek"]


@pytest.mark.asyncio
async def test_a_destroy_class_command_is_refused_on_the_library_path() -> None:
    # Arrange — the defect this task exists for, from the caller's side.
    from weft_command.invocation import invoke

    instance = _Wipe()

    # Act / Assert
    with pytest.raises(PermissionError):
        await invoke(
            command_name="wipe",
            instance=instance,
            args=_Args(),
            ctx=_context(),
            consent=_Refusing(),
            distribution="weft-canary",
        )

    assert instance.ran is False, (
        "the command ran despite consent being refused — the gate is after the run, not before it"
    )


def test_consent_is_required_and_cannot_be_defaulted() -> None:
    """The property that makes this a seam rather than a second call site.

    Asserted against the signature rather than by calling with the argument missing, because the
    fact being specified is *"a caller that has not decided cannot construct the call"* — a
    statement about the parameter, not about one traceback. `docs/lessons.md` `L8.24`: a defaulted
    parameter with one caller is a narrowing wearing a default, and the previous arrangement was
    safe only because the single caller happened to remember.
    """
    from weft_command.invocation import invoke

    parameter = inspect.signature(invoke).parameters["consent"]

    assert parameter.default is inspect.Parameter.empty, (
        "`consent` has a default, so a caller can invoke a command without deciding anything — "
        "which is the bypass this task exists to close"
    )
    assert parameter.kind is inspect.Parameter.KEYWORD_ONLY


def test_consent_is_a_runtime_checkable_protocol() -> None:
    # So a caller can be told it has handed over something that cannot answer, rather than meeting
    # an `AttributeError` from inside the seam.
    from weft_command.invocation import Consent

    assert isinstance(_Refusing(), Consent)
    assert not isinstance(object(), Consent)
