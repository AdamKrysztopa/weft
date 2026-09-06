"""The agent's own payload types — a tool call, a decided next action, and a run's transcript.

Task **7.1**, `docs/01-high-level-plan.md` -> Phase 7. This module carries no loop and no
tool catalogue — those are tasks 7.2 and 7.3 — only the shapes `weft_agent.prompts.
NextActionPrompt` renders against and the ones a future loop will pass between steps.

**Frozen throughout, `extra="forbid"` throughout**, the same discipline every payload type in
this tree already carries: a value object that could silently gain a field or be mutated after
construction is exactly the "plausible answer nobody can tell from a correct one" `CLAUDE.md`'s
own rule on silent fallbacks is written against.
"""

from __future__ import annotations

from collections.abc import Mapping

from pydantic import BaseModel, ConfigDict, model_validator


class ToolCall(BaseModel):
    """One tool invocation, named and its arguments — nothing about how it is dispatched.

    `arguments` is a `Mapping[str, object]`, never `dict[str, Any]`: a tool's own parameter
    schema is that tool's responsibility to check, not this payload's, so the values it carries
    are left as the loosest type a JSON-like argument bag can honestly claim.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    tool: str
    arguments: Mapping[str, object]


class NextAction(BaseModel):
    """What a model decided, given a goal and what has happened so far: call one tool, or
    answer.

    Exactly one of `call`/`final_answer` is set — never both, never neither. A model that
    hedged by offering both, or answered with neither, has not actually decided anything, and
    a loop that silently preferred one field over the other would be manufacturing a decision
    the model never made.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    reasoning: str
    call: ToolCall | None = None
    final_answer: str | None = None

    @model_validator(mode="after")
    def _exactly_one_of_call_or_final_answer(self) -> NextAction:
        if (self.call is None) == (self.final_answer is None):
            raise ValueError(
                "a NextAction must set exactly one of 'call' or 'final_answer', never both "
                f"and never neither (call={self.call!r}, final_answer={self.final_answer!r})"
            )
        return self


class AgentTranscript(BaseModel):
    """A run's goal, and every `NextAction` decided toward it so far, in order.

    Frozen, so advancing a run never mutates the transcript already handed to a caller — `
    with_step` returns a new instance, the same discipline `weft_kernel.payload`'s own frozen
    models are held to.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    goal: str
    steps: tuple[NextAction, ...] = ()

    def with_step(self, step: NextAction) -> AgentTranscript:
        """A new transcript with `step` appended after every step already recorded."""
        return self.model_copy(update={"steps": (*self.steps, step)})


class NextActionRequest(BaseModel):
    """What `next-action` renders: the goal, the tools on offer, and what has happened so far.

    `tools` and `transcript` arrive pre-rendered, the same split every prompt request type in
    this tree draws (`weft_retrieve.prompts.PassageRelevanceRequest`'s own docstring states it
    first): `string.Template` cannot iterate a tuple, so numbering the available tools and
    rendering `AgentTranscript.steps` as text is whatever plugin builds this request's own
    work — task 7.2's loop, not this prompt.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    goal: str
    tools: str
    transcript: str
