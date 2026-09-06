"""The agent's ReAct loop — task **7.2**. See this package's own `__init__.py` and
`docs/01-high-level-plan.md` -> Phase 7 for why the loop takes the shape it does; the reasoning
lives there and in `tests/unit/weft_agent/test_loop.py`'s own module docstring, not here twice.

**One step is: render the request, ask `weft_prompts.cascade.execute`, act on what came back.**
`NextActionRequest.tools` and `.transcript` arrive pre-rendered per that payload's own
docstring — turning the tool catalogue and the transcript into text is this module's job, since
`string.Template` cannot iterate a tuple.

**A tool name the model invented is refused as an observation, not an exception.** The model is
an untrusted source of names here exactly as a pipeline document is (requirement 5), but unlike a
document, the reader of the refusal is the model itself on its next turn — a wrong guess is
something an agent should be able to recover from, so the refusal is fed back rather than ending
the run.

**A cascade call that does not produce ends the loop with what was recorded so far, and says
`NO_DECISION`.** This branch is the one place task 7.2's own brief had decided nothing: it forbade
adding a `StopReason` member *and* forbade reusing `BUDGET_EXHAUSTED` for anything but the budget,
which are two constraints with no true value between them. The first pass reused
`BUDGET_EXHAUSTED`, documented the reuse and reported the contradiction rather than resolving it
quietly — which is the right handling of a brief that has decided nothing, and is why it was caught.

It is settled against the **operator** rather than against the code. `stopped_because` is a field
somebody reads to decide what to do next; `BUDGET_EXHAUSTED` on a run that stopped after one step
of ten tells them to raise the budget, and raising it would change nothing, because the model never
returned a usable decision. The remedy for this branch is the model or the prompt. Two causes
wearing one name is not wrong anywhere and ambiguous everywhere.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from typing import ClassVar, Protocol, cast, runtime_checkable

from pydantic import BaseModel, ConfigDict

from weft_agent.payload import AgentStep, AgentTranscript, NextAction, NextActionRequest
from weft_agent.prompts import NextActionPrompt
from weft_kernel.context import Context
from weft_kernel.payload import Produced
from weft_llm.contract import LLM
from weft_prompts.cascade import execute
from weft_prompts.contract import Prompt


@runtime_checkable
class AgentTool(Protocol):
    """One tool the loop may offer a model: a name to call it under, a description to pick it
    by, and the call itself.

    The name a tool is offered under is the key the caller's `tools` mapping supplies, never a
    member on the tool — a tool run under two names (a catalogue's alias, say) needs no second
    implementation.
    """

    description: ClassVar[str]

    async def call(self, arguments: Mapping[str, object], ctx: Context) -> str: ...


class StopReason(StrEnum):
    """Why `run_agent` returned — a field somebody reads to decide what to do next.

    **Three members, and the third was added rather than folded into the second on purpose.**
    Task 7.2's brief forbade adding a member *and* forbade reusing `BUDGET_EXHAUSTED` for
    anything but the budget, which left no value that is true; the implementer reused it,
    documented the reuse and reported the contradiction rather than choosing quietly. Settled
    against the operator: `BUDGET_EXHAUSTED` on a run that stopped after one step of ten tells
    them to raise the budget, and raising it would change nothing, because the model never
    returned a usable decision. Two causes wearing one name is not wrong anywhere and ambiguous
    everywhere.
    """

    #: The model gave a final answer. The only member that comes with one.
    ANSWERED = "answered"
    #: Every one of `max_steps` steps was taken and none of them answered.
    BUDGET_EXHAUSTED = "budget_exhausted"
    #: The cascade could not turn what the model said into a `NextAction` at any tier — so the
    #: run stopped with steps left, and the remedy is the model or the prompt, never the budget.
    NO_DECISION = "no_decision"


class AgentOutcome(BaseModel):
    """What a run produced: the full transcript, the final answer if there is one, and why the
    loop stopped."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    transcript: AgentTranscript
    final_answer: str | None
    stopped_because: StopReason


def _render_tools(tools: Mapping[str, AgentTool]) -> str:
    """The tool catalogue as the numbered list `next-action`'s prompt text asks for."""
    if not tools:
        return "(no tools are available; you must answer directly)"
    return "\n".join(f"- {name}: {tool.description}" for name, tool in tools.items())


def _render_transcript(transcript: AgentTranscript) -> str:
    """Every step recorded so far, as text a model reads back on its next turn."""
    if not transcript.steps:
        return "(nothing yet — this is the first step)"
    lines: list[str] = []
    for index, step in enumerate(transcript.steps, start=1):
        action = step.action
        lines.append(f"{index}. reasoning: {action.reasoning}")
        if action.call is not None:
            lines.append(f"   called '{action.call.tool}' with {dict(action.call.arguments)!r}")
            lines.append(f"   observed: {step.observation}")
        else:
            lines.append(f"   answered: {action.final_answer}")
    return "\n".join(lines)


def _refuse_unknown_tool(requested: str, tools: Mapping[str, AgentTool]) -> str:
    """Requirement 5, phrased for the model rather than for a log: what was asked for, and
    what is actually on offer."""
    available = ", ".join(sorted(tools)) if tools else "(none)"
    return (
        f"tool '{requested}' is not available. Available tools: {available}. "
        "Choose one of the available tools, or answer if you already have enough."
    )


async def run_agent(
    *,
    goal: str,
    tools: Mapping[str, AgentTool],
    llm: LLM,
    ctx: Context,
    max_steps: int,
) -> AgentOutcome:
    """Run one ReAct loop toward `goal`, for at most `max_steps` steps.

    Never raises for budget exhaustion or for a cascade that could not produce a decision — both
    are typed results, per this pack's own reliability decision. `CancelledError` is not caught
    anywhere here and propagates untouched, the same as everywhere else in this tree.
    """
    transcript = AgentTranscript(goal=goal)
    rendered_tools = _render_tools(tools)

    for _ in range(max_steps):
        request = NextActionRequest(
            goal=goal, tools=rendered_tools, transcript=_render_transcript(transcript)
        )
        outcome = await execute(
            llm=llm,
            # `NextActionPrompt` satisfies `Prompt` structurally at runtime — `version` is
            # assigned dynamically the same way every registered prompt's is, per
            # `weft_prompts.contract.Prompt`'s own docstring — but is invisible to a static
            # check on a concrete class. `weft_prompts.registry.PromptRegistry.render` casts
            # for the identical reason; there is no tool catalogue to resolve this through yet.
            prompt=cast(Prompt, NextActionPrompt()),
            values=request,
            output=NextAction,
            role="agent",
            ctx=ctx,
        )
        if not isinstance(outcome, Produced):
            # The model said something the cascade could not read as a decision at any of its
            # three tiers. The run stops with budget left, and says so — see `StopReason`.
            return AgentOutcome(
                transcript=transcript,
                final_answer=None,
                stopped_because=StopReason.NO_DECISION,
            )
        action = outcome.value.value

        if action.final_answer is not None:
            transcript = transcript.with_step(AgentStep(action=action))
            return AgentOutcome(
                transcript=transcript,
                final_answer=action.final_answer,
                stopped_because=StopReason.ANSWERED,
            )

        # `NextAction`'s own validator guarantees exactly one of `call`/`final_answer` is set;
        # `final_answer` was just ruled out above, so `call` is set.
        call = action.call
        assert call is not None

        tool = tools.get(call.tool)
        if tool is None:
            observation = _refuse_unknown_tool(call.tool, tools)
        else:
            observation = await tool.call(call.arguments, ctx)
        transcript = transcript.with_step(AgentStep(action=action, observation=observation))

    return AgentOutcome(
        transcript=transcript, final_answer=None, stopped_because=StopReason.BUDGET_EXHAUSTED
    )
