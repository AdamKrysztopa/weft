"""Unit tests for `weft_generate.contradiction`.

Mirrors `packages/weft-generate/src/weft_generate/contradiction.py`. Task **2.22**,
`docs/build-ledger.md`: "a query about whether the sources agree is answerable, and a
critic that could not look says so instead of reporting agreement." The load-bearing
test here is `test_a_critic_whose_cascade_cannot_be_parsed_reports_undetermined_not_
agreement`: the reference's `critique.py:158-166` returned `has_consensus=True` when its own
critique call failed, and the fix this task ships is a *third*, distinguishable value in
the returned `Agreement.status` — never a silent fall-through to the same value a clean
`agree` pass produces. Covers the happy path (sources agree, cited), the edge case
(sources conflict, cited separately from the agreement), the error case named above, and
a drive through `weft_kernel.seam.wrap`.

**The `LLM` is a stub and both prompts are real.** The same split every plugin test in
this tree takes: `ContradictionCriticPrompt` and `ContradictionAnswerPrompt` are exercised
for real, so this plugin's reading of what each renders is tested against the shape
rendering actually produces, while the model answering both is a script.
"""

from collections.abc import Mapping

from weft_generate.contract import Generator
from weft_generate.contradiction import (
    NAME,
    Agreement,
    ContradictionCheck,
    ContradictionCheckConfig,
)
from weft_generate.payload import AnswerStance
from weft_generate.prompts import (
    CONTRADICTION_ANSWER_NAME,
    CONTRADICTION_CRITIC_NAME,
    ConflictStatus,
    ContradictionAnswerPrompt,
    ContradictionCriticPrompt,
)
from weft_kernel.context import Context, ServiceRegistry
from weft_kernel.payload import MediaType, Node, Outcome, Produced
from weft_kernel.seam import wrap
from weft_llm.contract import LLM
from weft_llm.payload import Completion, Rendered
from weft_retrieve.contract import StageLookup
from weft_retrieve.payload import Passage, Passages, Query
from weft_store.contract import NodeStore, Scored, SourceRecord


class _StubLLM:
    """An `LLM` answering every `complete` call from a script, in order.

    `native_structured_available` is `False`, so the critic's own cascade starts at tier
    2 — the same derived-capability check a real provider is subject to, and the same
    stub shape `test_rerank.py` and `test_cited_answer.py` both use.
    """

    def __init__(self, replies: list[str]) -> None:
        self._replies = replies
        self.calls = 0
        #: Every role `complete` was asked under, in call order — how the two-role test
        #: below proves the critic and the answer route independently rather than reading
        #: the same field twice by coincidence.
        self.roles: list[str] = []

    async def native_structured_available(self, role: str) -> bool:
        del role
        return False

    async def complete_structured(
        self, rendered: Rendered, schema: Mapping[str, object], *, role: str, ctx: Context
    ) -> Outcome[Completion]:
        raise AssertionError("tier 1 is unavailable on this stub and must not be reached")

    async def complete(self, rendered: Rendered, *, role: str, ctx: Context) -> Outcome[Completion]:
        del ctx
        self.last_prompt = rendered.conversation.messages[-1].content
        self.roles.append(role)
        reply = self._replies[min(self.calls, len(self._replies) - 1)]
        self.calls += 1
        return Produced(value=Completion(text=reply, model="stub-model"))

    async def close(self) -> None: ...


class _StubLookup:
    """A `StageLookup` holding this pack's own two prompts, and refusing the other verb."""

    def __init__(self) -> None:
        self._prompts = {
            CONTRADICTION_CRITIC_NAME: ContradictionCriticPrompt(),
            CONTRADICTION_ANSWER_NAME: ContradictionAnswerPrompt(),
        }
        self.asked: list[str] = []

    def names(self, contract: type[object]) -> frozenset[str]:
        del contract
        return frozenset(self._prompts)

    async def build(self, contract: type[object], name: str, config: object = None) -> object:
        raise AssertionError("this plugin resolves a capability by name, never a stage")

    async def build_capability(
        self, contract: type[object], name: str, config: object = None
    ) -> object:
        del contract, config
        self.asked.append(name)
        return self._prompts[name]


class _StubStore:
    """A `NodeStore` that resolves no source — every passage here is `Node.synthetic`."""

    async def get_source(self, source_id: object) -> SourceRecord | None:
        del source_id
        return None


def _services(llm: _StubLLM) -> ServiceRegistry:
    services = ServiceRegistry()
    services.add(LLM, llm)
    services.add(StageLookup, _StubLookup())
    services.add(NodeStore, _StubStore())
    return services


def _ctx(services: ServiceRegistry) -> Context:
    return Context(
        tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en", services=services
    )


def _passage(label: str, content: str) -> Passage:
    node = Node.synthetic(content=content, media_type=MediaType.TEXT, reason="test fixture")
    return Passage(
        scored=Scored(value=node, score=0.5), rank=0, retrieved_by="vector-top-k", label=label
    )


def _passages(*items: Passage) -> Passages:
    asked = Query(text="did the two studies find the same effect?")
    return Passages(origin=asked, passages=items)


async def test_sources_that_agree_are_answered_with_status_agree_and_cited() -> None:
    # Arrange — the critic's tier-2 JSON validates immediately, so the cascade never
    # steps down, and the final answer cites both offered passages.
    payload = _passages(
        _passage("1", "Study A found a 12% reduction."),
        _passage("2", "Study B also found a reduction of about 12%."),
    )
    llm = _StubLLM(
        [
            '{"status": "agree", "agreed": ["Both studies found ~12% [1] [2]."], "conflicts": []}',
            "Both studies found a reduction of about 12% [1] [2].",
        ]
    )

    # Act
    outcome = await ContradictionCheck().run(payload, _ctx(_services(llm)))

    # Assert
    assert isinstance(outcome, Produced)
    answer = outcome.value
    assert answer.origin == payload.origin
    assert answer.stance == AnswerStance.ANSWERED
    assert answer.used == payload.passages
    assert sorted(c.marker for c in answer.citations) == ["1", "2"]
    agreement = answer.ext[Agreement.__namespace__]
    assert isinstance(agreement, Agreement)
    assert agreement.status == ConflictStatus.AGREE
    assert agreement.agreed and not agreement.conflicts
    assert llm.calls == 2
    # The critic's judgement and the final answer are structurally different calls
    # (`weft_llm.contract.LLM`'s own reason for the role mechanism: "generate and grade
    # can run on different models without either technique's code knowing which") and
    # this plugin routes them under two independent config fields, not one shared knob.
    assert llm.roles == ["grade", "generate"]


async def test_sources_that_conflict_are_answered_with_status_conflict_and_cited() -> None:
    # Arrange — the edge case: agreement and conflict are reported in *separate* fields,
    # not folded into one boolean the way the reference's `has_consensus` was.
    payload = _passages(
        _passage("1", "The 2019 report puts the population at 4,200."),
        _passage("2", "The 2021 report puts the population at 6,800."),
    )
    llm = _StubLLM(
        [
            '{"status": "conflict", "agreed": [], '
            '"conflicts": ["[1] reports 4,200 while [2] reports 6,800."]}',
            "The sources conflict: [1] reports 4,200, but [2] reports 6,800.",
        ]
    )

    # Act
    outcome = await ContradictionCheck().run(payload, _ctx(_services(llm)))

    # Assert
    assert isinstance(outcome, Produced)
    answer = outcome.value
    assert answer.origin == payload.origin
    assert answer.stance == AnswerStance.ANSWERED
    agreement = answer.ext[Agreement.__namespace__]
    assert isinstance(agreement, Agreement)
    assert agreement.status == ConflictStatus.CONFLICT
    assert agreement.conflicts and not agreement.agreed
    assert sorted(c.marker for c in answer.citations) == ["1", "2"]


async def test_a_critic_whose_cascade_cannot_be_parsed_reports_undetermined_not_agreement() -> None:
    # Arrange — the critic's cascade fails at every tier (tier 2 and tier 3 both answer
    # unparseable prose with no JSON anywhere in it), so `weft_prompts.cascade.execute`
    # itself returns `Failed`. The plugin must not let that failure resolve to the same
    # `AGREE` a clean pass reports — it is the reference's `has_consensus=True`-on-failure
    # defect this task exists to fix.
    payload = _passages(
        _passage("1", "Study A found a 12% reduction."),
        _passage("2", "Study B also found a reduction of about 12%."),
    )
    llm = _StubLLM(
        [
            "I cannot answer that in the format you asked for.",
            "I still cannot answer that in the format you asked for.",
            "The passages exist, but whether they agree could not be determined.",
        ]
    )

    # Act
    outcome = await ContradictionCheck().run(payload, _ctx(_services(llm)))

    # Assert — a *distinguishable* outcome from the AGREE test above, in the same
    # returned model: an `Answer` is still produced (09 §4 V2's engine-always-answers
    # requirement), but both `Agreement.status` and `Answer.stance` say "undetermined",
    # never "agree".
    assert isinstance(outcome, Produced)
    answer = outcome.value
    assert answer.origin == payload.origin
    assert answer.stance == AnswerStance.UNDETERMINED
    agreement = answer.ext[Agreement.__namespace__]
    assert isinstance(agreement, Agreement)
    assert agreement.status == ConflictStatus.UNDETERMINED
    assert agreement.status != ConflictStatus.AGREE
    assert agreement.agreed == ()
    assert agreement.conflicts == ()
    # Both the critic's cascade (stepped down through all three tiers) and the final
    # answer call ran — a hard critic failure does not skip answering the question.
    assert llm.calls == 3
    assert llm.roles == ["grade", "grade", "generate"]


async def test_driving_contradiction_check_through_the_seam_produces_an_answer() -> None:
    """Fitness function 7(b) against the one path a registered plugin is actually called
    through in production — `weft_kernel.seam.wrap`, not a direct method call a
    registered instance never receives."""
    # Arrange
    payload = _passages(_passage("1", "the only candidate"))
    llm = _StubLLM(
        [
            '{"status": "agree", "agreed": ["Only one source, nothing to compare it against."], '
            '"conflicts": []}',
            "The only candidate answers it [1].",
        ]
    )
    check = ContradictionCheck()
    wrapped = wrap(check.run, distribution="weft-generate", contract="Generator", plugin=NAME)

    # Act
    outcome = await wrapped(payload, _ctx(_services(llm)))

    # Assert
    assert isinstance(outcome, Produced)
    assert [c.marker for c in outcome.value.citations] == ["1"]
    assert isinstance(check, Generator)


def test_the_prompt_names_and_roles_are_configuration_rather_than_constants() -> None:
    # Act / Assert — every knob this technique has is a field with a default, per this
    # pack's own rule, and swapping the wording — or routing the critic and the answer
    # to different models — is a document edit, not a code edit.
    config = ContradictionCheckConfig()
    assert config.critic_prompt == CONTRADICTION_CRITIC_NAME
    assert config.answer_prompt == CONTRADICTION_ANSWER_NAME
    assert config.critic_role == "grade"
    assert config.answer_role == "generate"


def test_the_declared_cost_bound_is_two_two() -> None:
    # Act / Assert — no skip path: the critic's own cascade and the final answer call
    # are both always attempted, the same "no skip path" arithmetic `hyde`'s own
    # docstring states for its own single fixed call.
    assert ContradictionCheck.cost_bound == (2, 2)
