"""`weft agent` — ledger task **7.4**'s code half, and the seam it needed opened.

`docs/01-high-level-plan.md` → Phase 7's **Exit**: the pack drives a corpus end to end *with no edit
to core*, and `weft plugins doctor` reports it exactly as it reports any other pack.

**Building this found the gap Phase 8's own close review predicted, one phase early.** That review
recorded requirement 1 failing at the ambient-service seam: `ServiceRegistry` has a *consuming* side
anyone can reach (`ctx.require`) and a *producing* side reachable only by editing `weft-cli`, which
is `docs/lessons.md` `L5.15`'s shape. Phase 7 is where it stops being theoretical. An agent needs
the run's `LLM`, `weft_cli` is the only thing that parses `[llm.roles]` out of `weft.toml`, and
`weft_cli.cli.run_command` used to put exactly one thing into `ctx.services`: its own
`Dependencies`, which a stranger's pack cannot import without depending on the driving adapter —
the dependency `weft_command.contract`'s own placement argument forbids.

**The repair is one edit to the adapter that opens the seam for everyone**, not one edit per
capability: `run_command` now registers the run's ambient services by their *published contract
types* — `LLM`, `Prompts`, `TokenSink` — so any command reads `ctx.require(LLM)` and no pack ever
has to make this repair again. That is the distinction requirement 1 actually turns on. It is
stated plainly rather than glossed: **shipping the agent required an edit to `weft-cli`**, and what
makes it defensible is that the *next* pack needs none.

`weft-kernel` is untouched, which is what Phase 7's exit means by *core*.

**The command declares `write`.** `03` → *Permissions*: a command declares the highest class it may
reach, and the agent may reach `write` commands. It may not reach `overwrite` or `destroy` — G12's
ceiling, held by task 7.2a's catalogue and task 7.3's `RefusingConsent`, not by this declaration.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import ClassVar

import pytest
from pydantic import BaseModel

from weft_command.contract import Command, CommandResult
from weft_command.permission import PermissionClass
from weft_kernel.context import Context, ServiceRegistry
from weft_kernel.payload import Outcome, Produced
from weft_kernel.registry import Registry
from weft_llm.contract import LLM
from weft_llm.payload import Completion, Rendered


class _StubLLM:
    """Answers tier 2 of the cascade with one scripted decision, then a final answer."""

    def __init__(self, replies: list[str]) -> None:
        self._replies = replies
        self.calls = 0

    async def native_structured_available(self, role: str) -> bool:
        del role
        return False

    async def complete_structured(
        self, rendered: Rendered, schema: Mapping[str, object], *, role: str, ctx: Context
    ) -> Outcome[Completion]:
        raise AssertionError("tier 1 is unavailable on this stub")

    async def complete(self, rendered: Rendered, *, role: str, ctx: Context) -> Outcome[Completion]:
        del rendered, role, ctx
        reply = self._replies[min(self.calls, len(self._replies) - 1)]
        self.calls += 1
        return Produced(value=Completion(text=reply, model="stub-model"))

    async def close(self) -> None: ...


def _ctx(llm: LLM, registry: Registry) -> Context:
    services = ServiceRegistry()
    services.add(LLM, llm)
    services.add(Registry, registry)
    return Context(
        tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en", services=services
    )


class _NoArgs(BaseModel):
    """A real empty model, which is what a no-argument command declares.

    Bare `pydantic.BaseModel` is **not** a legitimate `args_model`: `weft_cli.commands`' own
    argument-free commands declare `NoArgs`, and pydantic refuses `model_json_schema()` on the
    base class itself. The first draft of this fixture used the bare class and found a real gap
    one layer down — see `weft_agent.tools._args_schema_of`, which now refuses it by name.
    """


class _CountResult(CommandResult):
    counted: int


class _Count:
    version: ClassVar[str] = "2.0.0"
    args_model: ClassVar[type[BaseModel]] = _NoArgs
    result_model: ClassVar[type[CommandResult]] = _CountResult
    required_declarations: ClassVar[tuple[str, ...]] = ("permission_class", "help")
    permission_class: ClassVar[PermissionClass] = PermissionClass.READ
    help: ClassVar[str] = "count what is stored"

    def __init__(self, config: object = None) -> None:
        del config

    async def run(self, args: BaseModel, ctx: Context) -> Outcome[CommandResult]:
        del args, ctx
        return Produced(value=_CountResult(counted=9))


def _registry() -> Registry:
    registry = Registry()
    registry.add(Command, "count", _Count, distribution="stranger-pack")
    return registry


def _decision(*, call: str | None = None, final: str | None = None) -> str:
    import json

    body: dict[str, object] = {"reasoning": "r", "call": None, "final_answer": final}
    if call is not None:
        body["call"] = {"tool": call, "arguments": {}}
    return json.dumps(body)


@pytest.mark.asyncio
async def test_the_agent_command_reaches_the_llm_through_the_published_contract() -> None:
    """The property the seam repair exists for: no `weft_cli` import anywhere in the path."""
    # Arrange
    from weft_agent.command import AgentArgs, AgentCommand, AgentCommandResult

    registry = _registry()
    llm = _StubLLM([_decision(call="count"), _decision(final="nine are stored")])

    # Act
    outcome = await AgentCommand().run(AgentArgs(goal="how many?"), _ctx(llm, registry))

    # Assert
    assert isinstance(outcome, Produced)
    result = outcome.value
    assert isinstance(result, AgentCommandResult)
    assert result.final_answer == "nine are stored"


@pytest.mark.asyncio
async def test_the_result_carries_the_transcript_a_reader_needs() -> None:
    # A final answer with no record of how it was reached is not auditable, and `09` §4's whole
    # posture is that a claim is judged against evidence rather than taken.
    from weft_agent.command import AgentArgs, AgentCommand, AgentCommandResult

    llm = _StubLLM([_decision(call="count"), _decision(final="nine")])
    outcome = await AgentCommand().run(AgentArgs(goal="how many?"), _ctx(llm, _registry()))

    assert isinstance(outcome, Produced)
    result = outcome.value
    assert isinstance(result, AgentCommandResult)
    assert len(result.transcript.steps) == 2
    assert result.transcript.steps[0].observation is not None


def test_the_command_declares_write_and_not_more() -> None:
    """`03` → *Permissions*: a command declares the highest class it may reach.

    `write` and not `destroy`: the ceiling is held by the catalogue and by consent, and a command
    that declared `destroy` would ask a human to confirm something the agent cannot do anyway.
    """
    from weft_agent.command import AgentCommand

    assert AgentCommand.permission_class is PermissionClass.WRITE
    assert isinstance(AgentCommand.help, str) and AgentCommand.help


def test_the_ambient_services_reach_every_command_not_only_the_cli_s_own() -> None:
    """The seam repair itself, asserted where a stranger would meet it.

    `run_command` used to register only `weft_cli.registry_bootstrap.Dependencies`, which a pack
    cannot import without depending on the driving adapter. It now registers the run's services by
    their published contract types, so `ctx.require(LLM)` answers for anybody.

    **Rewritten at ledger task 9.0**, and the reason is worth keeping. This test used to parse
    `weft_cli/cli.py`'s own AST looking for a literal `.add(LLM, ...)` call — so it asserted
    *where the registration is written* rather than *that a command can reach the service*, which
    is the property its own docstring names. The moment 9.0 moved that construction into
    `weft_cli.run_services.command_path_services`, so the three assemblers stop being one list
    written thrice, a green test failed for a change that strictly improved the thing it guards.
    An assertion is a specification including the parts you did not mean (`docs/lessons.md`
    `L9.39`). This version asks the question through the seam a command actually uses, so it
    survives the code moving and would still fail if the registration were dropped.
    """
    # Arrange
    from weft_cli.registry_bootstrap import Dependencies
    from weft_cli.run_services import command_path_services
    from weft_cli.services import ServiceSelection
    from weft_llm.client import NullSink
    from weft_prompts.contract import Prompts

    registry = Registry()
    deps = Dependencies(registry=registry, reports=(), services=ServiceSelection())

    # Act
    services = command_path_services(deps, sink=NullSink())

    # Assert — every published contract a stranger's command may reach, by contract and not by
    # `Dependencies`, which is `weft-cli`'s own and unimportable from a pack.
    assert services.resolve(LLM) is not None
    assert services.resolve(Prompts) is not None
    assert services.resolve(Registry) is registry
