"""First-party agentic front end — task **7.1**, `docs/05-grilling-sessions.md` G8.

**A pack, not an agentic REPL.** `docs/03`'s governing rule keeps logic out of the driving
adapter; G8 settled that the agent lands after release, built against `weft-kernel` and
`weft-rag`'s *published, versioned* API rather than a moving one — so it registers through the
same `weft.packs` entry point a third party would use, and nothing here reaches into
`weft_cli`. `tests/architecture/test_ff21_agent_is_an_ordinary_pack.py`'s own module docstring
states the three properties that test falsifies; this pack's whole job at 7.1 is to be a
distribution that satisfies all three and nothing more.

**Registers one plugin: `next-action`, against `weft_prompts.contract.Prompt`.** That contract
is published by `weft-rag`, never by this pack — the structural half of `01` -> Phase 7's own
claim, "built against nothing but the released API". The loop that would actually ask this
prompt, decide what to do with its answer, and dispatch a tool call is task 7.2; a tool
catalogue a loop could offer is task 7.3. Neither exists yet, deliberately: this task's only
claim is that the pack boundary itself holds.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from weft_agent.prompts import NEXT_ACTION_NAME, NextActionPrompt
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
    """Register `NextActionPrompt` as `"next-action"` for `Prompt`, and nothing else.

    `settings` is accepted, per the fixed two-parameter shape every pack declares, and unused —
    see `Settings`'s own docstring for what it will carry once task 7.2 gives it something to
    configure.
    """
    del settings
    registrar.add(Prompt, NEXT_ACTION_NAME, NextActionPrompt)


__all__ = [
    "NEXT_ACTION_NAME",
    "NextActionPrompt",
    "Settings",
    "register",
]
