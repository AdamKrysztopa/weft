"""`weft agent` — the command that drives `weft_agent.loop.run_agent` through the published
`weft_command.contract.Command` surface. Ledger task **7.4**.

**This is the seam Phase 8's own close review predicted, one phase early.**
`docs/internal/lessons.md` `L5.15`'s shape — a *consuming* side of `ServiceRegistry` anyone can
reach (`ctx.require`) and a *producing* side reachable only by editing `weft-cli` — is what made
this command impossible to write honestly until `weft_cli.cli.run_command` registered the run's
`LLM` (and `Prompts`, `TokenSink`) by their *published contract types*, not only under its own
private `Dependencies`. See that module's own docstring for the repair; nothing here depends on
`weft_cli` at all, and `weft_agent` must not — that pack boundary is task 7.1's own claim and this
task does not reopen it.

**`registry = ctx.require(Registry)`, not a name this command resolves itself.** The agent's own
tool catalogue is built from whatever `Registry` the run assembled (`weft_agent.command_tools.
command_tools`), which is `ctx.require`'s exact job: a service every stage may need regardless of
what pipeline runs, resolved by type with no name to disambiguate — there is exactly one registry
per run.

**The command declares `write`, not more.** `03` → *Permissions*: a command declares the highest
class it may reach, and the agent may reach `write` commands (`weft_agent.tools.
REACHABLE_CLASSES`) but never `overwrite`/`destroy` — G12's ceiling, held by that catalogue and by
`weft_agent.command_tools.RefusingConsent`, not by this declaration. Declaring `destroy` here
would ask a human to confirm something the agent cannot do anyway.

**`max_steps` comes from `weft_agent.Settings`, this pack's own configured budget** — an
operator's decision (that model's own docstring), read here rather than hard-coded a second time.
Imported inside `run`, not at module scope: `weft_agent/__init__.py` imports `AgentCommand` from
this module to register it, so a module-scope `from weft_agent import Settings` here would be a
circular import at the moment `weft_agent` itself is still being defined.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from weft_agent import Settings

from collections.abc import Mapping
from typing import ClassVar, cast

from pydantic import BaseModel, ConfigDict

from weft_agent.command_tools import command_tools
from weft_agent.loop import AgentTool, StopReason, run_agent
from weft_agent.payload import AgentTranscript
from weft_command.contract import CommandResult
from weft_command.permission import PermissionClass
from weft_kernel.context import Context
from weft_kernel.payload import Outcome, Produced
from weft_kernel.registry import Registry
from weft_llm.contract import LLM

_AGENT_HELP = (
    "drive a goal to an answer, calling the run's published commands as tools "
    "(docs/01-high-level-plan.md -> Phase 7)"
)


class AgentArgs(BaseModel):
    """What `weft agent` needs from a caller: the goal to work toward, and nothing else."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    goal: str


class AgentCommandResult(CommandResult):
    """What one agent run produced — the full transcript, the final answer if there is one,
    and why the loop stopped. The same three facts `weft_agent.loop.AgentOutcome` carries,
    restated as a `CommandResult` so `weft_cli`/a stranger's renderer can format them without
    depending on `weft_agent.loop` itself.
    """

    transcript: AgentTranscript
    final_answer: str | None
    stopped_because: StopReason


class AgentCommand:
    """`weft agent` — one ReAct run toward a goal, its tools drawn from the run's own
    published command surface. See this module's own docstring for the seam it needed opened.
    """

    args_model: ClassVar[type[BaseModel]] = AgentArgs
    result_model: ClassVar[type[CommandResult]] = AgentCommandResult
    permission_class: ClassVar[PermissionClass] = PermissionClass.WRITE
    help: ClassVar[str] = _AGENT_HELP

    def __init__(self, settings: Settings | None = None, config: object = None) -> None:
        """`settings` bound at construction, `config` accepted and unused.

        **Bound rather than constructed in `run`**, which is what `weft_qdrant` and `weft_openai`
        already do through `functools.partial`. The first version built a fresh `Settings()` per
        run, so `[packs.agent] max_steps = 3` validated, was accepted and was silently discarded —
        a knob that reads as configurable and is not. `config` is the per-plugin argument every
        factory receives and an agent has nothing per-stage to configure.
        """
        del config
        # Imported here, not at module scope: `weft_agent/__init__.py` imports this module in
        # order to register the command, so a module-scope import would be a cycle — the same
        # reason the docstring above already gives for `Settings` not appearing in the imports.
        from weft_agent import Settings  # noqa: PLC0415

        self._settings = settings if settings is not None else Settings()

    @property
    def max_steps(self) -> int:
        """The configured step budget this command will run under."""
        return self._settings.max_steps

    async def run(self, args: BaseModel, ctx: Context) -> Outcome[CommandResult]:
        # Local import: `weft_agent/__init__.py` imports `AgentCommand` from this module to
        # register it, so a module-scope `from weft_agent import Settings` here would be a
        # circular import at the moment `weft_agent` itself is still being defined — see this
        # module's own docstring.

        agent_args = cast(AgentArgs, args)
        registry = ctx.require(Registry)
        llm = ctx.require(LLM)
        tools = command_tools(registry)

        outcome = await run_agent(
            goal=agent_args.goal,
            # `CommandTool` satisfies `AgentTool` structurally at runtime (it carries
            # `description` and an async `call`) but not statically: `AgentTool.description`
            # is declared `ClassVar[str]`, while `CommandTool` sets it as an instance
            # attribute in `__init__`. `weft_agent.loop`'s own `NextActionPrompt`/`Prompt`
            # pairing is the identical, already-established shape for "a static check cannot
            # see a structural conformance that holds at runtime" — this is that same cast,
            # not a new pattern.
            tools=cast("Mapping[str, AgentTool]", tools),
            llm=llm,
            ctx=ctx,
            max_steps=self.max_steps,
        )

        return Produced(
            value=AgentCommandResult(
                transcript=outcome.transcript,
                final_answer=outcome.final_answer,
                stopped_because=outcome.stopped_because,
            )
        )


__all__ = ["AgentArgs", "AgentCommand", "AgentCommandResult"]
