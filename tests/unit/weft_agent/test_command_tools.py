"""The agent reaches Weft only through the published command surface — ledger task **7.3**.

`docs/03-cli.md` → *Two modes, one implementation*, and `docs/internal/05-grilling-sessions.md` →
G12. Three properties, and each one is a way the agent could have cheated:

*(a) It goes through `weft_command.invocation.invoke`, so the permission gate applies to it.* Task
7.0 moved that gate onto the typed path precisely because Phase 7 was about to become its second
caller; a tool that called `Command.run` directly would work, would return the right answer, and
would have no ceiling at all. That is the failure 7.0 repaired, and this is where it would come
back.

*(b) The observation is built from the typed result, never from rendered text.* `Rendered` is what a
human's terminal receives — stdout, stderr, an exit code. An agent parsing that would be reading a
presentation layer, which is the *"never re-parsed text"* half of this task's own line, and it would
break the first time somebody improved a message. The tool reads `Outcome[CommandResult]` and
serialises the model.

*(c) Consent is answered, not skipped.* `invoke` requires a `Consent`, and the agent's answer is
`RefusingConsent`: **every** `overwrite`/`destroy`-class operation is refused, with the refusal
naming what would be needed. That is G12's settled rule — *nothing other than a TTY counts as
consent* — expressed as code rather than as a paragraph.

**Belt and braces, on purpose, and the two halves guard different things.** Task 7.2a's catalogue
decides what the model is *offered*; `RefusingConsent` decides what actually *executes*. They fail
independently: a catalogue bug offers a tool that should not exist, and consent still refuses it; a
consent bug permits something, and the model was never told the tool was there. Neither alone is the
ceiling, and saying which is which is what keeps the pair from reading as duplication somebody later
deletes as redundant.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import ClassVar

import pytest
from pydantic import BaseModel

from weft_command.contract import Command, CommandResult
from weft_command.permission import PermissionClass
from weft_kernel.context import Context
from weft_kernel.payload import Outcome, Produced
from weft_kernel.registry import Registry


class _CountArgs(BaseModel):
    what: str = "nodes"


class _CountResult(CommandResult):
    counted: int


class _Count:
    """A `read`-class command a stranger might ship."""

    version: ClassVar[str] = "2.0.0"
    args_model: ClassVar[type[BaseModel]] = _CountArgs
    result_model: ClassVar[type[CommandResult]] = _CountResult
    required_declarations: ClassVar[tuple[str, ...]] = ("permission_class", "help")
    permission_class: ClassVar[PermissionClass] = PermissionClass.READ
    help: ClassVar[str] = "count what is stored"

    def __init__(self, config: object = None) -> None:
        del config

    async def run(self, args: BaseModel, ctx: Context) -> Outcome[CommandResult]:
        del args, ctx
        return Produced(value=_CountResult(counted=9))


class _Wipe(_Count):
    permission_class: ClassVar[PermissionClass] = PermissionClass.DESTROY
    help: ClassVar[str] = "wipe what is stored"


def _ctx() -> Context:
    return Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")


def _registry_with(**commands: type[_Count]) -> Registry:
    registry = Registry()
    for name, factory in commands.items():
        registry.add(Command, name.replace("_", " "), factory, distribution="stranger-pack")
    return registry


@pytest.mark.asyncio
async def test_the_observation_comes_from_the_typed_result() -> None:
    """(b) — and the assertion is about *provenance*, not about formatting.

    What matters is that `9` reached the observation from `_CountResult.counted`, a field, rather
    than from a string a renderer produced. Asserting an exact rendering here would make the format
    a contract nobody agreed to; asserting the value arrived is the fact.
    """
    # Arrange
    from weft_agent.command_tools import command_tools

    tools = command_tools(_registry_with(count=_Count))

    # Act
    observation = await tools["count"].call({"what": "nodes"}, _ctx())

    # Assert
    assert "9" in observation, (
        "the command's own typed field did not reach the observation, so the agent is reading "
        "something other than the result"
    )


@pytest.mark.asyncio
async def test_a_destroy_class_command_is_refused_even_if_a_tool_exists_for_it() -> None:
    """(c) — consent guards execution, and it is tested with task 7.2a's catalogue bypassed.

    A `CommandTool` is built here for a `destroy`-class command deliberately, which the catalogue
    would never offer. That is the point: the two halves must fail independently, or one of them is
    decoration that survives until somebody notices it looks redundant.
    """
    # Arrange
    from weft_agent.command_tools import CommandTool

    tool = CommandTool(registry=_registry_with(wipe=_Wipe), command_name="wipe")

    # Act
    observation = await tool.call({"what": "everything"}, _ctx())

    # Assert — the refusal reaches the *model*, as an observation, so it can choose otherwise.
    assert "wipe" in observation, "the refusal does not name what was refused"
    assert "consent" in observation.lower() or "tty" in observation.lower(), (
        "the refusal does not say why, so the model cannot tell it from a crash"
    )


@pytest.mark.asyncio
async def test_a_read_class_command_is_permitted() -> None:
    # The other side of the same gate. A consent that refused everything would pass the test above
    # and make the agent useless, which is why both directions are asserted.
    from weft_agent.command_tools import command_tools

    tools = command_tools(_registry_with(count=_Count))
    observation = await tools["count"].call({}, _ctx())

    assert "refus" not in observation.lower()


@pytest.mark.asyncio
async def test_refusing_consent_covers_the_whole_permission_vocabulary() -> None:
    """G12's rule as code: *nothing other than a TTY counts as consent*.

    Asserted over every `PermissionClass` member rather than over the two that matter today — the
    rule is about the classes `03` names, and a sixth member added later must be a deliberate
    decision here rather than something that silently becomes reachable. `docs/internal/lessons.md`
    `L6.4`: read the population, and this is the population being fixed rather than sampled.
    """
    from weft_agent.command_tools import ConsentRefusedError, RefusingConsent

    consent = RefusingConsent()
    ask_classes = {PermissionClass.OVERWRITE, PermissionClass.DESTROY}

    for permission_class in PermissionClass:
        instance = type("_Probe", (), {"permission_class": permission_class})()
        if permission_class in ask_classes:
            with pytest.raises(ConsentRefusedError):
                await consent.decide(command_name="probe", instance=instance, args=_CountArgs())
        else:
            await consent.decide(command_name="probe", instance=instance, args=_CountArgs())


def test_the_tool_runs_a_command_only_through_the_seam() -> None:
    """(a) — structural, because a tool that bypassed the seam passes every test above.

    A `CommandTool` calling `instance.run(...)` directly would return the same observation and have
    no permission gate at all — which is precisely the defect task 7.0 repaired one caller earlier.
    Asserted the way fitness function 20 asks its own version of this question: over the source, not
    by patching a module attribute at runtime, because the property is *"this module never does
    that"* rather than *"it did not do it this once"*.
    """
    import weft_agent.command_tools as module

    tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
    called = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    called |= {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }

    assert "invoke" in called, "the tool never calls the invocation seam"
    assert "run" not in called, (
        "weft_agent.command_tools calls `.run(...)` directly, which bypasses the permission gate "
        "task 7.0 moved onto this path — the ceiling G12 settled would not apply to the agent"
    )
