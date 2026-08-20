"""This pack's own tests — the fourth canonical file `docs/07-extension-cost.md` names.

Exercises `GreetCommand` directly, the same way `weft-example-chunker`'s own test suite
exercises `WordChunker`: against a real `Context`, no double standing in for the kernel or
contract this pack depends on. Not collected by `weft`'s own `pytest` (its `testpaths` is
`["tests"]`, and this directory is outside the weft workspace entirely) — a stranger's tests
are the stranger's own to run, `uv run pytest` from inside this directory.
"""

import pytest
from weft_example_command.greet import GreetArgs, GreetCommand, GreetResult

from weft_command.contract import Command
from weft_kernel.context import Context
from weft_kernel.payload import Produced
from weft_kernel.registry import MissingRequiredDeclarationError, Registry


def _ctx() -> Context:
    return Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")


async def test_greet_command_produces_a_typed_greeting() -> None:
    # Arrange
    command = GreetCommand()

    # Act
    outcome = await command.run(GreetArgs(name="Ada"), _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    result = outcome.value
    assert isinstance(result, GreetResult)
    assert result.greeting == "Hello, Ada!"


def test_greet_command_satisfies_the_command_contract_structurally() -> None:
    # Act / Assert — no import of `Command` in greet.py itself; this is the caller's check.
    assert isinstance(GreetCommand(), Command)


def test_greet_command_registers_under_command() -> None:
    # Arrange
    registry = Registry()

    # Act
    registry.add(Command, "greet", GreetCommand, distribution="weft-example-command")

    # Assert
    assert registry.lookup(Command, "greet") is GreetCommand


def test_greet_without_a_declared_permission_class_is_refused() -> None:
    # Arrange — `Command.required_declarations` refuses registration, loudly, for a plugin
    # that never states its permission class — proving the mandatory declaration a stranger's
    # own pack is held to exactly as `weft-cli`'s own built-ins are.
    class _NoPermission:
        args_model = GreetArgs

        class _Result:
            pass

        result_model = _Result
        help = "missing its permission class"

        def __init__(self, config: object = None) -> None:
            del config

        async def run(self, args: object, ctx: object) -> object:
            raise NotImplementedError

    registry = Registry()

    # Act / Assert
    with pytest.raises(MissingRequiredDeclarationError):
        registry.add(Command, "broken", _NoPermission, distribution="weft-example-command")
