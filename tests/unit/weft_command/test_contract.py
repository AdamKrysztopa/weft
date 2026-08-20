"""Unit tests for `weft_command.contract`.

Mirrors `packages/weft-command/src/weft_command/contract.py`. Covers capability derived by
`isinstance` rather than declared — the same property `weft_extract.contract` and
`weft_chunk.contract`'s own tests assert for `Extractor` and `Chunker` — a full `run` proving
the typed-result shape `docs/03-cli.md` → *Two modes, one implementation* requires ("a
`Command` returns a typed result and never writes to a stream"), and task 3.1's own mandatory
declaration: `Command.required_declarations == ("permission_class",)`, and
`weft_kernel.registry` refuses to register a plugin under it that never declares
`permission_class` — the generalised mechanism `tests/unit/weft_kernel/test_registry.py`
proves contract-agnostically, exercised here against the real contract it was built for.
"""

import pytest
from pydantic import BaseModel, ConfigDict

from weft_command.contract import COMMAND_CONTRACT_VERSION, Command, CommandResult
from weft_command.permission import PermissionClass
from weft_kernel.context import Context
from weft_kernel.payload import Failed, NothingToProduce, Outcome, Produced
from weft_kernel.registry import MissingRequiredDeclarationError, Registry


def _ctx() -> Context:
    return Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")


class _ListArgs(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class _ListResult(CommandResult):
    names: tuple[str, ...]


class _ListPipelines:
    """Satisfies `Command` structurally, and declares both mandatory declarations."""

    version = COMMAND_CONTRACT_VERSION
    args_model = _ListArgs
    result_model = _ListResult
    permission_class = PermissionClass.READ
    help = "list every pipeline this pack knows"

    def __init__(self, config: object) -> None:
        self.config = config

    async def run(self, args: BaseModel, ctx: Context) -> Outcome[CommandResult]:
        del args, ctx
        return Produced(value=_ListResult(names=("base", "specific")))


async def test_command_run_returns_a_typed_result_never_printed_text() -> None:
    # Arrange
    command = _ListPipelines(config=None)

    # Act
    outcome = await command.run(_ListArgs(), _ctx())

    # Assert — a typed model a renderer formats, not a string.
    assert isinstance(outcome, Produced)
    assert isinstance(outcome.value, _ListResult)
    assert outcome.value.names == ("base", "specific")


async def test_command_nothing_to_produce_is_a_legitimate_outcome() -> None:
    # Arrange
    class _EmptyList:
        version = COMMAND_CONTRACT_VERSION
        args_model = _ListArgs
        result_model = _ListResult
        permission_class = PermissionClass.READ

        def __init__(self, config: object) -> None: ...

        async def run(self, args: BaseModel, ctx: Context) -> Outcome[CommandResult]:
            del args, ctx
            return NothingToProduce(reason="no pipelines installed")

    # Act
    outcome = await _EmptyList(config=None).run(_ListArgs(), _ctx())

    # Assert
    assert isinstance(outcome, NothingToProduce)
    assert outcome.reason == "no pipelines installed"


async def test_command_failed_reason_is_a_decided_outcome() -> None:
    # Arrange
    class _AlwaysFails:
        version = COMMAND_CONTRACT_VERSION
        args_model = _ListArgs
        result_model = _ListResult
        permission_class = PermissionClass.DESTROY

        def __init__(self, config: object) -> None: ...

        async def run(self, args: BaseModel, ctx: Context) -> Outcome[CommandResult]:
            del args, ctx
            return Failed(reason="collection does not exist")

    # Act
    outcome = await _AlwaysFails(config=None).run(_ListArgs(), _ctx())

    # Assert
    assert isinstance(outcome, Failed)
    assert outcome.reason == "collection does not exist"


def test_command_capability_is_derived_by_isinstance_not_declared() -> None:
    # Arrange
    class _MissingRun:
        """Everything `Command` needs except `run` — never satisfies the contract."""

        version = COMMAND_CONTRACT_VERSION
        args_model = _ListArgs
        result_model = _ListResult

    class _MissingArgsModel:
        """`run` and `result_model`, but no `args_model` — `isinstance` membership fails."""

        version = COMMAND_CONTRACT_VERSION
        result_model = _ListResult

        async def run(self, args: BaseModel, ctx: Context) -> Outcome[CommandResult]:
            del args, ctx
            return Produced(value=_ListResult(names=()))

    # Act / Assert
    assert isinstance(_ListPipelines(config=None), Command)
    assert not isinstance(_MissingRun(), Command)
    assert not isinstance(_MissingArgsModel(), Command)


def test_command_requires_a_permission_class_and_help_declaration() -> None:
    # Act / Assert — `03` → *Permissions* and task 3.2's own addition: both are readable off
    # the contract itself, the same way `version` is, and neither is a member `isinstance`
    # checks — see the module docstring for why.
    assert Command.required_declarations == ("permission_class", "help")
    protocol_attrs = getattr(Command, "__protocol_attrs__", frozenset[str]())
    assert "permission_class" not in protocol_attrs
    assert "required_declarations" not in protocol_attrs
    assert "help" not in protocol_attrs


def test_registering_a_command_with_no_permission_class_is_refused() -> None:
    # Arrange — a real contract, not a kernel-level stand-in: `Command` really names
    # `permission_class` as required, so this is task 3.1's mandatory check proven end to end.
    class _NoPermissionDeclared:
        version = COMMAND_CONTRACT_VERSION
        args_model = _ListArgs
        result_model = _ListResult

        def __init__(self, config: object) -> None: ...

        async def run(self, args: BaseModel, ctx: Context) -> Outcome[CommandResult]:
            del args, ctx
            return Produced(value=_ListResult(names=()))

    registry = Registry()

    # Act / Assert
    with pytest.raises(MissingRequiredDeclarationError) as excinfo:
        registry.add(Command, "no-permission", _NoPermissionDeclared, distribution="acme-cmd")

    message = str(excinfo.value)
    assert "no-permission" in message
    assert "Command" in message
    assert "permission_class" in message


def test_registering_a_command_with_no_help_is_refused() -> None:
    # Arrange — the mirror case: `permission_class` alone is not enough since task 3.2 added
    # `help` to `required_declarations` too.
    class _NoHelpDeclared:
        version = COMMAND_CONTRACT_VERSION
        args_model = _ListArgs
        result_model = _ListResult
        permission_class = PermissionClass.READ

        def __init__(self, config: object) -> None: ...

        async def run(self, args: BaseModel, ctx: Context) -> Outcome[CommandResult]:
            del args, ctx
            return Produced(value=_ListResult(names=()))

    registry = Registry()

    # Act / Assert
    with pytest.raises(MissingRequiredDeclarationError) as excinfo:
        registry.add(Command, "no-help", _NoHelpDeclared, distribution="acme-cmd")

    message = str(excinfo.value)
    assert "no-help" in message
    assert "help" in message


def test_registering_a_command_with_a_permission_class_succeeds() -> None:
    # Arrange
    registry = Registry()

    # Act
    registry.add(Command, "list", _ListPipelines, distribution="acme-cmd")

    # Assert
    assert registry.lookup(Command, "list") is _ListPipelines
