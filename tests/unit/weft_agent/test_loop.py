"""The agent's loop — ledger task **7.2**, and every choice in it is chosen rather than inherited.

`docs/01-high-level-plan.md` → Phase 7, `docs/05-grilling-sessions.md` → G8 and G12. The
`agentic-patterns` design pass ran before this task, and what it decided is what these tests assert,
so the loop's shape is a decision with reasons rather than whatever the first draft happened to do:

- **Autonomy: a single agent, and the least that works.** No planner, no reflection pass, no
  sub-agents, no topology layer. The irreducible reason an agent is needed at all is that
  `weft index` reports what failed only *after* running, and twenty-seven shipped pipeline
  documents make *"which rung fits this corpus"* a runtime choice no branch table can enumerate.
- **Reasoning loop: ReAct, one step at a time, under a hard budget.** The next tool depends on the
  last typed result, which is what makes it a loop rather than a plan.
- **The step is a typed structured answer, not native tool-calling.** `LLMProvider` has no
  tool-calling and deliberately is not gaining any: `complete_structured` plus
  `weft_prompts.cascade` already buy the same thing, while adding a tool role to `Conversation`
  would be a G9 major for every implementer *and* would make the agent untestable against
  `scripted`.
- **Memory: a frozen transcript within one invocation, nothing across them.** Durable read-back
  already exists as tools (`weft trace`, `weft eval`), so a Recorder contract would add a gate for
  something the command surface already answers.
- **Reliability: exhausting the budget is a typed result, never an exception.** A loop that raises
  on its own designed stopping condition forces every caller to treat a normal outcome as a
  failure, and puts what the agent actually did on an exception instead of in the result.

**A transcript of actions alone cannot be reasoned from, so `AgentStep` pairs each decision with
what it observed.** Task 7.1 shipped `AgentTranscript.steps` as bare `NextAction`s, which is enough
to record what was decided and not enough to decide anything *next* — the model needs to see what
its last call returned. The memory shape is this task's own subject, so it changes here.

**What is deliberately not reused, measured rather than assumed.** The design pass suggested
`weft_llm.loop_guard`. It does not apply: that module answers *"has this generated text settled into
repeating itself?"* — a streaming-token concern whose thresholds are tuned for markdown tables — and
an agent going in circles is a different fact, about repeated *actions* across steps. Citing it here
would have been a citation rather than a mechanism.
"""

from __future__ import annotations

import json
from collections.abc import Mapping

import pytest

from weft_kernel.context import Context
from weft_kernel.payload import Outcome, Produced
from weft_llm.payload import Completion, Rendered


def _ctx() -> Context:
    return Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")


class _StubLLM:
    """An `LLM` answering tier 2 of the cascade from a script.

    `native_structured_available` is `False`, so tier 1 is skipped structurally rather than by a
    flag — the same derived-capability check a real provider is subject to. Shaped after
    `tests/unit/weft_retrieve/test_rerank.py`, which is this tree's established way to exercise the
    real cascade against a stubbed provider: the stub sits at `weft_llm.contract.LLM`, exactly
    where the run assembler puts a real client.
    """

    def __init__(self, replies: list[str]) -> None:
        self._replies = replies
        self.calls = 0

    async def native_structured_available(self, role: str) -> bool:
        del role
        return False

    async def complete_structured(
        self, rendered: Rendered, schema: Mapping[str, object], *, role: str, ctx: Context
    ) -> Outcome[Completion]:
        raise AssertionError("tier 1 is unavailable on this stub and must not be reached")

    async def complete(self, rendered: Rendered, *, role: str, ctx: Context) -> Outcome[Completion]:
        del rendered, role, ctx
        reply = self._replies[min(self.calls, len(self._replies) - 1)]
        self.calls += 1
        return Produced(value=Completion(text=reply, model="stub-model"))

    async def close(self) -> None: ...


class _CountingTool:
    """One tool the loop may call, recording every set of arguments it was given."""

    def __init__(self, answer: str = "counted nine") -> None:
        # An instance attribute, matching the Protocol — a tool whose description is *derived*
        # cannot use a `ClassVar`, and every `CommandTool`'s is, being the command's own `help`.
        self.description = "count something"
        self.calls: list[Mapping[str, object]] = []
        self._answer = answer

    async def call(self, arguments: Mapping[str, object], ctx: Context) -> str:
        del ctx
        self.calls.append(arguments)
        return self._answer


def _action(
    *, call: str | None = None, final: str | None = None, reasoning: str = "because"
) -> str:
    """One `NextAction` as a model emits it — JSON the cascade's tier 2 parses."""
    body: dict[str, object] = {"reasoning": reasoning, "call": None, "final_answer": final}
    if call is not None:
        body["call"] = {"tool": call, "arguments": {"what": "nodes"}}
    return json.dumps(body)


@pytest.mark.asyncio
async def test_the_loop_calls_a_tool_then_answers() -> None:
    # Arrange — the whole of ReAct: act, observe, then decide it is done.
    from weft_agent.loop import StopReason, run_agent

    tool = _CountingTool()
    llm = _StubLLM([_action(call="count"), _action(final="there are nine")])

    # Act
    outcome = await run_agent(
        goal="how many nodes are stored?",
        tools={"count": tool},
        llm=llm,
        ctx=_ctx(),
        max_steps=5,
    )

    # Assert
    assert outcome.final_answer == "there are nine"
    assert outcome.stopped_because is StopReason.ANSWERED
    assert tool.calls == [{"what": "nodes"}]
    assert len(outcome.transcript.steps) == 2


@pytest.mark.asyncio
async def test_what_a_tool_returned_reaches_the_next_step() -> None:
    """The *observe* half of ReAct, which is the half a transcript of actions alone loses.

    Without this the loop is a plan with extra rounds: the model would decide step two knowing
    only what it decided in step one, never what came back.
    """
    # Arrange
    from weft_agent.loop import run_agent

    tool = _CountingTool(answer="counted nine")
    llm = _StubLLM([_action(call="count"), _action(final="nine")])

    # Act
    outcome = await run_agent(goal="count", tools={"count": tool}, llm=llm, ctx=_ctx(), max_steps=5)

    # Assert
    assert outcome.transcript.steps[0].observation == "counted nine"
    assert outcome.transcript.steps[1].observation is None, (
        "a step that answered rather than called observed nothing, and must not invent one"
    )


@pytest.mark.asyncio
async def test_exhausting_the_budget_is_a_result_and_not_an_exception() -> None:
    """The designed stopping condition, and a caller must not have to catch it.

    A loop that raises when it runs out of steps makes every caller treat a normal outcome as a
    failure, and the one thing the caller most needs — what the agent did before it ran out — ends
    up on an exception rather than in the result.
    """
    # Arrange — a model that never answers, only ever calls.
    from weft_agent.loop import StopReason, run_agent

    tool = _CountingTool()
    llm = _StubLLM([_action(call="count", reasoning="again")])

    # Act
    outcome = await run_agent(
        goal="never finish", tools={"count": tool}, llm=llm, ctx=_ctx(), max_steps=3
    )

    # Assert
    assert outcome.stopped_because is StopReason.BUDGET_EXHAUSTED
    assert outcome.final_answer is None
    assert len(outcome.transcript.steps) == 3, "the budget is a count of steps actually taken"
    assert outcome.transcript.goal == "never finish", "the transcript carries what was being tried"


@pytest.mark.asyncio
async def test_a_tool_the_catalogue_does_not_hold_is_refused_by_name() -> None:
    """Requirement 5, applied to a model's own output.

    A model is an untrusted source of names here, exactly as a pipeline document is: it can ask for
    a tool that does not exist, or one deliberately kept out of its reach. The refusal names what
    was wanted and what is available — and it reaches the **model**, as an observation, rather than
    ending the run, because a wrong guess is something an agent should be able to recover from.
    That is the one place this differs from a document naming an unknown plugin, and it is a
    difference in *who is being told*, never in whether the refusal is loud.
    """
    # Arrange
    from weft_agent.loop import run_agent

    tool = _CountingTool()
    llm = _StubLLM([_action(call="delete"), _action(final="I cannot do that")])

    # Act
    outcome = await run_agent(
        goal="remove everything", tools={"count": tool}, llm=llm, ctx=_ctx(), max_steps=5
    )

    # Assert
    assert tool.calls == [], "a tool outside the catalogue was called"
    refusal = outcome.transcript.steps[0].observation or ""
    assert "delete" in refusal, "the refusal does not say which tool was refused"
    assert "count" in refusal, "the refusal does not name what is available"


@pytest.mark.asyncio
async def test_the_transcript_is_frozen_and_grows_by_replacement() -> None:
    """`CLAUDE.md`: frozen where the value is a domain object.

    Asserted as a fact about the type and about how it grows, rather than by catching what one
    assignment raises — the property is *"a step cannot mutate a transcript a caller is holding"*,
    and the config plus the replacement behaviour are what say so.
    """
    from weft_agent.loop import run_agent
    from weft_agent.payload import AgentTranscript

    assert AgentTranscript.model_config.get("frozen") is True

    outcome = await run_agent(
        goal="answer at once",
        tools={},
        llm=_StubLLM([_action(final="done")]),
        ctx=_ctx(),
        max_steps=2,
    )
    transcript = outcome.transcript
    grown = transcript.with_step(transcript.steps[0])

    assert grown is not transcript, "growing the transcript mutated it instead of replacing it"
    assert len(grown.steps) == len(transcript.steps) + 1
    assert len(transcript.steps) == 1, "the original transcript changed under the caller"


def test_the_budget_is_a_setting_rather_than_a_constant() -> None:
    """A configured `max_steps` reaches the loop — asserted as *arrival*, not as declaration.

    **The first version of this test asserted `"max_steps" in Settings.model_fields` and that the
    default was positive**, under a docstring claiming the value "arrives through the pack's own
    settings". It did not arrive: `register()` deleted `settings` and `AgentCommand.run` built a
    fresh `Settings()`, so `[packs.agent] max_steps = 3` validated, was accepted, and was silently
    discarded. The test passed throughout, because the half it checked — that the field is declared
    — was the half never in doubt. That is `CLAUDE.md`'s own `weft --help` pattern: a test shaped
    around the defect it was written to prevent, found by a phase-close review rather than by the
    gate.

    So this asserts the binding: a `Settings` with a specific budget produces a command that runs
    that many steps and no more.
    """
    from weft_agent import Settings
    from weft_agent.command import AgentCommand

    assert Settings().max_steps > 0, "the default budget must let at least one step run"

    bound = AgentCommand(Settings(max_steps=2))

    assert bound.max_steps == 2, (
        "a configured budget does not reach the command, so [packs.agent] max_steps is accepted "
        "and discarded — which is worse than refusing it"
    )
    assert AgentCommand().max_steps == Settings().max_steps, (
        "an unconfigured command must still get the declared default"
    )
