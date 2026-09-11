"""First-party agentic front end — task **7.1**, `docs/internal/05-grilling-sessions.md` G8.

**A pack, not an agentic REPL.** `docs/03`'s governing rule keeps logic out of the driving
adapter; G8 settled that the agent lands after release, built against `weft-kernel` and
`weft-rag`'s *published, versioned* API rather than a moving one — so it registers through the
same `weft.packs` entry point a third party would use, and nothing here reaches into
`weft_cli`. `tests/architecture/test_ff21_agent_is_an_ordinary_pack.py`'s own module docstring
states the three properties that test falsifies; this pack's whole job at 7.1 is to be a
distribution that satisfies all three and nothing more.

**Registers `next-action` against `weft_prompts.contract.Prompt`, and, since task 7.4, `agent`
against `weft_command.contract.Command` — both contracts published by `weft-rag`, never by this
pack**, the structural half of `01` -> Phase 7's own claim, "built against nothing but the
released API". `weft_agent.command.AgentCommand` is the loop (task 7.2) and the tool catalogue
(task 7.3) reached through the one surface a stranger's own command would use; see that
module's own docstring for the ambient-service seam it needed `weft_cli.cli.run_command` to
open. `AgentCommandResult`'s own renderer is registered the identical way any pack's is
(`weft_kernel.discovery.PackRegistrar.add_renderer`, task 6.20's own seam).
"""

from __future__ import annotations

from functools import partial

from pydantic import BaseModel, ConfigDict

from weft_agent.command import AgentCommand, AgentCommandResult
from weft_agent.prompts import NEXT_ACTION_NAME, NextActionPrompt
from weft_agent.render import render_agent
from weft_command.contract import Command
from weft_kernel.discovery import PackRegistrar
from weft_prompts.contract import Prompt


class Settings(BaseModel):
    """`weft-agent`'s pack settings — task 7.2's own: the loop's step budget.

    `max_steps` is an operator's decision, not a number baked into `weft_agent.loop`, per that
    module's own docstring. Defaulted to 10: enough for a handful of tool calls plus a final
    answer on the kind of multi-step retrieval question this pack exists for, without letting a
    model stuck in a loop run away unbounded.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    max_steps: int = 10


def register(registrar: PackRegistrar, settings: Settings) -> None:
    """Register `NextActionPrompt` as `"next-action"` for `Prompt`, `AgentCommand` as `"agent"`
    for `Command`, and that command's own renderer.

    `settings` is accepted, per the fixed two-parameter shape every pack declares, and unused —
    `AgentCommand.run` reads `Settings` itself, for the reason its own module docstring gives
    (a module-scope import here would be circular).
    """
    registrar.add(Prompt, NEXT_ACTION_NAME, NextActionPrompt)
    registrar.add(Command, "agent", partial(AgentCommand, settings))
    registrar.add_renderer(AgentCommandResult, render_agent)


__all__ = [
    "NEXT_ACTION_NAME",
    "AgentCommand",
    "AgentCommandResult",
    "NextActionPrompt",
    "Settings",
    "register",
]
