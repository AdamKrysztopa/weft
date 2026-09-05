"""Unit tests for `weft_retrieve.transforms`.

Mirrors `packages/weft-rag/src/weft_retrieve/transforms.py`. Ledger **2.15**: "a query
transform is a composable stage a caller can omit, so no strategy pays for a rewrite it did
not ask for." Covers the happy path (a follow-up question rewritten against history, the
literal original kept alongside it), the edge case (no history and `skip_without_history` —
the omitted-by-configuration case, and the one that makes `cost_bound`'s floor of zero a fact
rather than a claim: no `LLM`, no `StageLookup`, no model call), the error case (a cascade
that could not produce a rewrite is relayed exactly as it answered, never papered over), and a
drive through `weft_kernel.seam.wrap`.

**The `LLM` is a stub and the cascade is real** — the same split `test_rerank.py` uses and
for the same reason: `weft_prompts.cascade.execute` is the one path this plugin reaches a
typed answer through, and stubbing it out would leave this plugin's own reading of the
cascade's answer untested against the shape it actually returns.

`out.origin == in.origin` is asserted in every test that produces a `QuerySet`, never
assumed — `QuerySet.origin`'s own docstring records the obligation this rule exists to hold:
feeding a hallucinated HyDE passage to a cross-encoder *as the query* is the failure this
query-path invariant stops a transform from committing. `weft_retrieve.rerank`'s own test
module carries the identical assertion for the same stated reason.

**`Hyde` (ledger 2.16) joins below.** It reuses `_StubLLM` and `_RefusingLLM` as-is and adds
`_hyde_lookup` beside `_lookup`, because both plugins reach a typed answer through the same
`weft_prompts.cascade.execute` and the stub shape that proves it is the same shape either
way. Its own `out.origin == in.origin` assertion is load-bearing rather than a formality:
`hyde` is the plugin ledger 2.4's own line names as the one whose loss of this property *is*
a cross-encoder-scores-a-hallucination defect, because this is the transform that
actually generates the hallucinated text a substitution would otherwise leak.

**`StepBack` (ledger 2.17) joins below too, reusing the same stub shapes for its own happy
path, edge case, error case and seam-driven test.** Its distinct test is the one the ledger
line is actually about: `test_step_back_is_the_same_technique_whether_tokens_arrive_at_once_
or_one_at_a_time` drives `StepBack.run` through a *real* `weft_llm.client.LLMClient` twice —
once against a provider that answers in a single chunk, once against one that answers word
by word — and asserts the two `QuerySet`s that come back are equal. `_StubLLM` cannot stand
in for this one: it answers `complete()` directly and never touches `stream()` at all, so a
stub-driven test could not tell a provider whose blocking and streaming answers had drifted
from one whose had not — exactly the blocking-vs-streaming drift a mock of the *symptom's*
absence would be blind to.
"""

from collections.abc import AsyncIterator, Mapping

from weft_kernel.context import Context, ServiceRegistry
from weft_kernel.payload import Failed, Outcome, Produced
from weft_kernel.registry import Registry
from weft_kernel.seam import wrap
from weft_llm.client import NullSink, llm_service
from weft_llm.contract import LLM, LLMProvider, TokenSink
from weft_llm.payload import Completion, Conversation, Rendered
from weft_llm.roles import LLMRoles, RoleMapping
from weft_llm.scripted import ScriptedConfig, ScriptedProvider
from weft_retrieve.contract import QueryTransform, StageLookup
from weft_retrieve.payload import Channel, Query, QueryOrigin, QuerySet, Turn, TurnRole
from weft_retrieve.prompts import (
    HYDE_DOCUMENT_NAME,
    MULTI_QUERY_VARIANTS_NAME,
    STANDALONE_QUESTION_NAME,
    STEP_BACK_QUESTION_NAME,
    HydeDocumentPrompt,
    MultiQueryVariantsPrompt,
    StandaloneQuestionPrompt,
    StepBackPrompt,
)
from weft_retrieve.transforms import (
    HYDE_NAME,
    MULTI_QUERY_NAME,
    NAME,
    STEP_BACK_NAME,
    ContextualQueryRewrite,
    ContextualQueryRewriteConfig,
    ExpansionKind,
    Hyde,
    HydeConfig,
    MultiQuery,
    MultiQueryConfig,
    StepBack,
    StepBackConfig,
)


class _StubLLM:
    """An `LLM` answering tier 2 of the cascade from a script — same shape as `test_rerank.py`'s."""

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
        del rendered, ctx
        reply = self._replies[min(self.calls, len(self._replies) - 1)]
        self.calls += 1
        return Produced(value=Completion(text=reply, model="stub-model"))

    async def close(self) -> None: ...


class _StubLookup:
    """A `StageLookup` holding this pack's own prompts — same shape as `test_rerank.py`'s."""

    def __init__(self, prompts: Mapping[str, object]) -> None:
        self._prompts = prompts
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


class _RefusingLLM:
    """An `LLM` that never answers usably — proves `run` never resolves it when it need not."""

    async def native_structured_available(self, role: str) -> bool:
        raise AssertionError("no model service should be touched when history is skipped")

    async def complete_structured(self, *args: object, **kwargs: object) -> object:
        raise AssertionError("no model service should be touched when history is skipped")

    async def complete(self, *args: object, **kwargs: object) -> object:
        raise AssertionError("no model service should be touched when history is skipped")

    async def close(self) -> None: ...


def _lookup() -> _StubLookup:
    return _StubLookup({STANDALONE_QUESTION_NAME: StandaloneQuestionPrompt()})


def _hyde_lookup() -> _StubLookup:
    return _StubLookup({HYDE_DOCUMENT_NAME: HydeDocumentPrompt()})


def _stepback_lookup() -> _StubLookup:
    return _StubLookup({STEP_BACK_QUESTION_NAME: StepBackPrompt()})


def _multiquery_lookup() -> _StubLookup:
    return _StubLookup({MULTI_QUERY_VARIANTS_NAME: MultiQueryVariantsPrompt()})


def _services(llm: object, lookup: object | None = None) -> ServiceRegistry:
    services = ServiceRegistry()
    services.add(LLM, llm)
    services.add(StageLookup, lookup if lookup is not None else _lookup())
    return services


def _streaming_services(llm: object, lookup: object) -> ServiceRegistry:
    """`_services`, plus a `TokenSink` — needed only by the equivalence test below, which
    drives `StepBack` through a *real* `weft_llm.client.LLMClient` rather than `_StubLLM`.
    A real client's `complete()` always resolves `TokenSink` (`.phase2-design.md` §7: "the
    `LLM` client always calls `provider.stream(...)` … and emits each chunk to
    `ctx.require(TokenSink)`"), which `_StubLLM` never does, so no earlier test in this
    module needed one.
    """
    services = _services(llm, lookup)
    services.add(TokenSink, NullSink())
    return services


def _reply_provider(reply: str, *, chunked: bool) -> type[object]:
    """A provider *class* that always answers `reply`, delegating every word of *how* to
    `weft_llm.scripted.ScriptedProvider` — never a second implementation of what a reply is.

    A class, not an instance: `weft_llm.client.LLMClient._bind` always builds a provider by
    calling `entry.factory(None)`, the same shape `test_client.py`'s own local `_Catalogued`
    class already uses to hand a real `LLMClient` a fixture it could not otherwise construct
    with a fixed answer. `chunked` is the one axis this test needs to vary: `True` streams
    `ScriptedProvider`'s own word-by-word chunks unchanged; `False` drains the same generator
    first and yields the whole answer as one chunk. Both read the identical text from the
    identical `ScriptedProvider` instance — the equivalence this proves would be worthless if
    either path computed the reply on its own.

    **Returns `type[object]`, not `type[LLMProvider]`** — the same choice `test_client.py`'s
    own `_Catalogued` makes by leaving its class unannotated: `LLMProvider`'s own contract
    declares `version: ClassVar[str]` only inside `if TYPE_CHECKING`, assigned once on the
    Protocol itself after its class body, never asked of an implementer, so a local test
    class genuinely satisfying every runtime method still fails a `type[LLMProvider]`
    structural check that no real provider pack is held to either.
    """

    class _FixedReply:
        def __init__(self, config: object = None) -> None:
            del config
            self._inner = ScriptedProvider(ScriptedConfig(reply=reply))

        async def complete(
            self, conv: Conversation, *, model: str, ctx: Context
        ) -> Outcome[Completion]:
            return await self._inner.complete(conv, model=model, ctx=ctx)

        async def stream(
            self, conv: Conversation, *, model: str, ctx: Context
        ) -> AsyncIterator[str]:
            if chunked:
                async for chunk in self._inner.stream(conv, model=model, ctx=ctx):
                    yield chunk
            else:
                parts = [chunk async for chunk in self._inner.stream(conv, model=model, ctx=ctx)]
                yield "".join(parts)

        async def close(self) -> None:
            await self._inner.close()

    return _FixedReply


def _client_for(reply: str, *, chunked: bool) -> LLM:
    """A real `LLM` service, wired to one provider answering `reply` under role `"stepback"`
    — never `_StubLLM`, because the property under test lives in `weft_llm.client`, not in
    this module.
    """
    registry = Registry()
    registry.add(
        LLMProvider, "scripted", _reply_provider(reply, chunked=chunked), distribution="weft-llm"
    )
    return llm_service(
        registry=registry, roles=LLMRoles(roles={"stepback": RoleMapping(provider="scripted")})
    )


def _ctx(services: ServiceRegistry) -> Context:
    return Context(
        tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en", services=services
    )


async def test_a_follow_up_with_history_is_rewritten_and_the_original_is_kept() -> None:
    # Arrange
    original = Query(text="and what about the second one?")
    history = (
        Turn(role=TurnRole.USER, text="what is mRMR?"),
        Turn(role=TurnRole.ASSISTANT, text="a feature-selection criterion."),
    )
    payload = QuerySet(origin=original, queries=(original,), history=history)
    llm = _StubLLM(['{"text": "what is the second feature-selection criterion discussed?"}'])
    lookup = _lookup()

    # Act
    outcome = await ContextualQueryRewrite().run(payload, _ctx(_services(llm, lookup)))

    # Assert
    assert isinstance(outcome, Produced)
    result: QuerySet = outcome.value
    assert result.origin == payload.origin
    assert [q.text for q in result.queries] == [
        "and what about the second one?",
        "what is the second feature-selection criterion discussed?",
    ]
    derived = result.queries[1]
    assert derived.origin is QueryOrigin.DERIVED
    assert derived.produced_by == NAME
    assert result.history == payload.history
    assert lookup.asked == [STANDALONE_QUESTION_NAME]
    assert llm.calls == 1


async def test_keep_question_false_drops_the_literal_original() -> None:
    # Arrange
    original = Query(text="and the third one?")
    history = (Turn(role=TurnRole.USER, text="what is mRMR?"),)
    payload = QuerySet(origin=original, queries=(original,), history=history)
    llm = _StubLLM(['{"text": "what is the third criterion discussed?"}'])

    # Act
    outcome = await ContextualQueryRewrite(ContextualQueryRewriteConfig(keep_question=False)).run(
        payload, _ctx(_services(llm, _lookup()))
    )

    # Assert
    assert isinstance(outcome, Produced)
    result: QuerySet = outcome.value
    assert result.origin == payload.origin
    assert [q.text for q in result.queries] == ["what is the third criterion discussed?"]


async def test_no_history_and_skip_without_history_returns_the_payload_unchanged() -> None:
    # Arrange — the omittable-by-configuration case: `skip_without_history=True` (the
    # default) is what makes `cost_bound`'s floor of zero a fact. `_RefusingLLM` and a
    # `StageLookup` neither one is ever asked prove no service was even reached, not merely
    # that no reply was used.
    asked = Query(text="a fresh, standalone question")
    payload = QuerySet(origin=asked, queries=(asked,))
    services = ServiceRegistry()
    services.add(LLM, _RefusingLLM())

    # Act
    outcome = await ContextualQueryRewrite().run(payload, _ctx(services))

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value == payload
    assert outcome.value.origin == payload.origin


async def test_a_cascade_that_could_not_produce_a_rewrite_is_relayed_not_papered_over() -> None:
    # Arrange — the model answers prose no tier can parse into `StandaloneQuestion`; three
    # attempts (tier 2 plus the rescue tier) and then `Failed`, relayed exactly as the cascade
    # answered it rather than falling back to the unrewritten question silently.
    original = Query(text="and that one?")
    payload = QuerySet(
        origin=original, queries=(original,), history=(Turn(role=TurnRole.USER, text="hi"),)
    )
    llm = _StubLLM(["I cannot help with that."])

    # Act
    outcome = await ContextualQueryRewrite().run(payload, _ctx(_services(llm, _lookup())))

    # Assert
    assert isinstance(outcome, Failed)


async def test_driving_the_rewrite_through_the_seam_composes_a_new_query_set() -> None:
    """Fitness function 7(b) against the one path a registered plugin is actually called
    through in production — `weft_kernel.seam.wrap`, not a direct method call a registered
    instance never receives."""
    # Arrange
    original = Query(text="what about that other one?")
    payload = QuerySet(
        origin=original, queries=(original,), history=(Turn(role=TurnRole.USER, text="hi"),)
    )
    llm = _StubLLM(['{"text": "what is the other one discussed?"}'])
    transform = ContextualQueryRewrite()
    wrapped = wrap(
        transform.run, distribution="weft-retrieve", contract="QueryTransform", plugin=NAME
    )

    # Act
    outcome = await wrapped(payload, _ctx(_services(llm, _lookup())))

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value.origin == payload.origin
    assert len(outcome.value.queries) == 2
    assert isinstance(transform, QueryTransform)


def test_the_config_defaults_match_the_design_records_table() -> None:
    # Act / Assert — requirement 6's second clause, read off the config model: an operator
    # retunes every one of these without touching this distribution.
    config = ContextualQueryRewriteConfig()
    assert config.history_turns == 4
    assert config.prompt == STANDALONE_QUESTION_NAME
    assert config.role == "rewrite"
    assert config.keep_question is True
    assert config.skip_without_history is True
    assert ContextualQueryRewrite.config_model is ContextualQueryRewriteConfig


def test_the_declared_cost_bound_is_zero_to_one() -> None:
    # Act / Assert — zero when omitted (asserted above against a service that refuses any
    # call), one otherwise: a cascade stepping down is one ask re-put, the same arithmetic
    # `weft_retrieve.rerank`'s own `(0, 1)` uses.
    assert ContextualQueryRewrite.cost_bound == (0, 1)


async def test_hyde_generates_one_derived_query_per_document_and_keeps_the_question() -> None:
    # Arrange — the happy path: one cascade call returns two hypothetical documents, and
    # both `samples` (two requested) and `keep_question` (the default `True`) are read off
    # the config rather than hard-coded, per requirement 6's second clause.
    asked = Query(text="why is mRMR preferred to plain relevance ranking?")
    payload = QuerySet(origin=asked, queries=(asked,))
    llm = _StubLLM(
        [
            '{"documents": ["mRMR balances relevance against redundancy directly.", '
            '"mRMR avoids selecting features that duplicate each other."]}'
        ]
    )
    lookup = _hyde_lookup()

    # Act
    outcome = await Hyde(HydeConfig(samples=2)).run(payload, _ctx(_services(llm, lookup)))

    # Assert
    assert isinstance(outcome, Produced)
    result: QuerySet = outcome.value
    assert result.origin == payload.origin
    assert [q.text for q in result.queries] == [
        "why is mRMR preferred to plain relevance ranking?",
        "mRMR balances relevance against redundancy directly.",
        "mRMR avoids selecting features that duplicate each other.",
    ]
    for derived in result.queries[1:]:
        assert derived.origin is QueryOrigin.DERIVED
        assert derived.produced_by == HYDE_NAME
        # HyDE is a claim about dense retrieval — the hallucinated document must never
        # reach the text arm, per this plugin's own module docstring and `Query.channels`'
        # own docstring on the inversion this guards against.
        assert derived.channels == (Channel.VECTOR.value,)
    assert lookup.asked == [HYDE_DOCUMENT_NAME]
    assert llm.calls == 1


async def test_hyde_channels_accepts_an_arm_no_first_party_channel_enum_names() -> None:
    # Arrange — repair for a reviewer finding: `Query.channels` is deliberately `tuple[str,
    # ...]`, not `Channel`, so a transform can aim a derived query at an arm no first-party
    # code anticipated (`Query`'s own docstring; `Channel`'s own docstring names "graph
    # traversal" as exactly the kind of arm this axis stays open for). `hyde` calls no
    # store itself — it only stamps `Query.channels` for whatever retriever runs downstream
    # — so `HydeConfig.channels` must accept an arm name outside the closed two-member
    # enum, unlike `vector-top-k`'s identical-looking field, which is closed because that
    # plugin's `needs_store = (VectorSearch,)` genuinely cannot call anything else.
    asked = Query(text="what causes overfitting?")
    payload = QuerySet(origin=asked, queries=(asked,))
    llm = _StubLLM(['{"documents": ["overfitting happens when a model memorises noise."]}'])

    # Act
    outcome = await Hyde(HydeConfig(channels=("graph",))).run(
        payload, _ctx(_services(llm, _hyde_lookup()))
    )

    # Assert
    assert isinstance(outcome, Produced)
    derived = outcome.value.queries[1]
    assert derived.channels == ("graph",)


async def test_hyde_keep_question_false_drops_the_literal_question() -> None:
    # Arrange — the edge case: the third named knob, `keep_question`, set away from its
    # default drops the literal question and leaves only the generated documents.
    asked = Query(text="what is feature selection?")
    payload = QuerySet(origin=asked, queries=(asked,))
    llm = _StubLLM(
        ['{"documents": ["feature selection reduces a model\'s input dimensionality."]}']
    )

    # Act
    outcome = await Hyde(HydeConfig(keep_question=False)).run(
        payload, _ctx(_services(llm, _hyde_lookup()))
    )

    # Assert
    assert isinstance(outcome, Produced)
    result: QuerySet = outcome.value
    assert result.origin == payload.origin
    assert [q.text for q in result.queries] == [
        "feature selection reduces a model's input dimensionality."
    ]


async def test_hyde_a_cascade_that_could_not_produce_documents_is_relayed_not_papered_over() -> (
    None
):
    # Arrange — the error case: the third named knob, `on_failure`, has one member (`FAIL`)
    # today, and relaying the cascade's own `Failed` *is* that behaviour — never a silent
    # fall-through to the unrewritten question, which would let a failed rewrite pass as a
    # successful one.
    asked = Query(text="what is feature selection?")
    payload = QuerySet(origin=asked, queries=(asked,))
    llm = _StubLLM(["I cannot help with that."])

    # Act
    outcome = await Hyde().run(payload, _ctx(_services(llm, _hyde_lookup())))

    # Assert
    assert isinstance(outcome, Failed)


async def test_driving_hyde_through_the_seam_composes_a_new_query_set() -> None:
    """Fitness function 7(b) against the one path a registered plugin is actually called
    through in production — `weft_kernel.seam.wrap`, not a direct method call a registered
    instance never receives."""
    # Arrange
    asked = Query(text="what causes overfitting?")
    payload = QuerySet(origin=asked, queries=(asked,))
    llm = _StubLLM(['{"documents": ["overfitting happens when a model memorises noise."]}'])
    transform = Hyde()
    wrapped = wrap(
        transform.run, distribution="weft-retrieve", contract="QueryTransform", plugin=HYDE_NAME
    )

    # Act
    outcome = await wrapped(payload, _ctx(_services(llm, _hyde_lookup())))

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value.origin == payload.origin
    assert len(outcome.value.queries) == 2
    assert isinstance(transform, QueryTransform)


def test_hyde_config_defaults_match_the_design_records_table() -> None:
    # Act / Assert — requirement 6's second clause, read off the config model: an operator
    # retunes samples, query inclusion and failure behaviour without touching this
    # distribution.
    config = HydeConfig()
    assert config.samples == 3
    assert config.keep_question is True
    assert config.prompt == HYDE_DOCUMENT_NAME
    assert config.role == "hyde"
    assert config.channels == (Channel.VECTOR,)
    assert config.on_failure.value == "fail"
    assert Hyde.config_model is HydeConfig


def test_hyde_declared_cost_bound_is_one_to_one() -> None:
    # Act / Assert — always exactly one cascade call: unlike `contextual-query-rewrite`,
    # hyde has no skip path, so the floor and the ceiling are the same number.
    assert Hyde.cost_bound == (1, 1)


async def test_step_back_abstracts_the_question_and_keeps_the_literal_one() -> None:
    # Arrange — the happy path: one cascade call returns the abstraction, and it lands
    # alongside the literal question, per this plugin's own row in `.phase2-design.md` §10:
    # "emits the abstract question alongside the literal one."
    asked = Query(text="why did the mRMR score for feature X drop after preprocessing?")
    payload = QuerySet(origin=asked, queries=(asked,))
    llm = _StubLLM(['{"text": "what generally affects an mRMR score during preprocessing?"}'])
    lookup = _stepback_lookup()

    # Act
    outcome = await StepBack().run(payload, _ctx(_services(llm, lookup)))

    # Assert
    assert isinstance(outcome, Produced)
    result: QuerySet = outcome.value
    assert result.origin == payload.origin
    assert [q.text for q in result.queries] == [
        "why did the mRMR score for feature X drop after preprocessing?",
        "what generally affects an mRMR score during preprocessing?",
    ]
    derived = result.queries[1]
    assert derived.origin is QueryOrigin.DERIVED
    assert derived.produced_by == STEP_BACK_NAME
    assert lookup.asked == [STEP_BACK_QUESTION_NAME]
    assert llm.calls == 1


async def test_step_back_keep_question_false_drops_the_literal_original() -> None:
    # Arrange — the edge case: the named knob, `keep_question`, set away from its default
    # leaves only the abstraction searched for.
    asked = Query(text="why does this specific model overfit on the validation split?")
    payload = QuerySet(origin=asked, queries=(asked,))
    llm = _StubLLM(['{"text": "what generally causes a model to overfit?"}'])

    # Act
    outcome = await StepBack(StepBackConfig(keep_question=False)).run(
        payload, _ctx(_services(llm, _stepback_lookup()))
    )

    # Assert
    assert isinstance(outcome, Produced)
    result: QuerySet = outcome.value
    assert result.origin == payload.origin
    assert [q.text for q in result.queries] == ["what generally causes a model to overfit?"]


async def test_step_back_a_cascade_that_could_not_abstract_is_relayed_not_papered_over() -> None:
    # Arrange — the error case: `on_failure` has one member (`FAIL`) today, and relaying the
    # cascade's own outcome *is* that behaviour — never a silent fall-through to the literal
    # question alone, which would let a failed abstraction pass as a successful one.
    asked = Query(text="why does this happen?")
    payload = QuerySet(origin=asked, queries=(asked,))
    llm = _StubLLM(["I cannot help with that."])

    # Act
    outcome = await StepBack().run(payload, _ctx(_services(llm, _stepback_lookup())))

    # Assert
    assert isinstance(outcome, Failed)


async def test_driving_step_back_through_the_seam_composes_a_new_query_set() -> None:
    """Fitness function 7(b) against the one path a registered plugin is actually called
    through in production — `weft_kernel.seam.wrap`, not a direct method call a registered
    instance never receives."""
    # Arrange
    asked = Query(text="why did this specific run fail?")
    payload = QuerySet(origin=asked, queries=(asked,))
    llm = _StubLLM(['{"text": "what generally causes a run like this to fail?"}'])
    transform = StepBack()
    wrapped = wrap(
        transform.run,
        distribution="weft-retrieve",
        contract="QueryTransform",
        plugin=STEP_BACK_NAME,
    )

    # Act
    outcome = await wrapped(payload, _ctx(_services(llm, _stepback_lookup())))

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value.origin == payload.origin
    assert len(outcome.value.queries) == 2
    assert isinstance(transform, QueryTransform)


def test_step_back_config_defaults_match_the_design_records_table() -> None:
    # Act / Assert — requirement 6's second clause, read off the config model. `prompt`'s
    # default is `step-back-question`, not the design table's literal `step-back` string —
    # see `weft_retrieve.prompts.STEP_BACK_QUESTION_NAME`'s own docstring for why reusing
    # the transform's own name here would make `AmbiguousStageContractError` reachable by
    # any document naming `use: step-back`.
    config = StepBackConfig()
    assert config.prompt == STEP_BACK_QUESTION_NAME
    assert config.role == "stepback"
    assert config.keep_question is True
    assert config.on_failure.value == "fail"
    assert StepBack.config_model is StepBackConfig


def test_step_back_declared_cost_bound_is_one_to_one() -> None:
    # Act / Assert — like `hyde`, step-back is not conditioned on anything in the payload,
    # so the floor and the ceiling are the same number.
    assert StepBack.cost_bound == (1, 1)


def test_step_back_and_hyde_and_contextual_query_rewrite_are_registered_under_distinct_names() -> (
    None
):
    # Act / Assert — `.phase2-design.md` §5's own derived rule: "no plugin name may be
    # registered under two Phase 2 contracts." `step-back` (the `QueryTransform`) and
    # `step-back-question` (the `Prompt`) must differ, or a document naming `use: step-back`
    # becomes ambiguous the moment both are registered — see `weft_retrieve.__init__.register`.
    names = {NAME, HYDE_NAME, STEP_BACK_NAME}
    assert len(names) == 3
    assert STEP_BACK_NAME != STEP_BACK_QUESTION_NAME


async def test_step_back_is_the_same_technique_whether_tokens_arrive_at_once_or_one_at_a_time() -> (
    None
):
    """Ledger **2.17**: "`step-back` is the same technique whether tokens arrive at once or
    one at a time." `10` §1.1's own entry for this technique is the failure mode this test
    checks directly rather than reasons about: a blocking path that keeps the literal and
    abstract contexts in separate prompt slots while a streaming path discards the split
    makes the interactive default silently a different, weaker technique — "one name, two
    techniques."

    Here there is exactly one place a model is asked anything: `StepBack.run` calls
    `ctx.require(LLM).complete_structured`/`.complete` through `weft_prompts.cascade.
    execute`, and the real `LLM` — `weft_llm.client.LLMClient` — always calls
    `provider.stream(...)` regardless of who is watching (`.phase2-design.md` §7, `01` →
    *Colour*'s streaming consequence). So the only way tokens-at-once and tokens-one-at-a-
    time can *disagree* is if a provider's `stream` and a caller's accumulation of it
    diverge — which is exactly what this test drives, through two providers answering with
    the identical text delivered two different ways, per Zheng, Mishra, Chen, Cheng, Chi,
    Le & Zhou, *Take a Step Back*, ICLR 2024, arXiv:2310.06117.
    """
    # Arrange
    reply = '{"text": "what generally determines a nutrient deficiency\'s cause?"}'
    asked = Query(text="why did this patient develop scurvy?")
    payload = QuerySet(origin=asked, queries=(asked,))
    lookup = _stepback_lookup()
    all_at_once = _client_for(reply, chunked=False)
    one_token_at_a_time = _client_for(reply, chunked=True)

    # Act
    from_one_chunk = await StepBack().run(payload, _ctx(_streaming_services(all_at_once, lookup)))
    from_many_chunks = await StepBack().run(
        payload, _ctx(_streaming_services(one_token_at_a_time, lookup))
    )

    # Assert — the same technique, byte for byte, whichever way the answer arrived.
    assert isinstance(from_one_chunk, Produced)
    assert isinstance(from_many_chunks, Produced)
    assert from_one_chunk.value == from_many_chunks.value
    assert [q.text for q in from_one_chunk.value.queries] == [
        "why did this patient develop scurvy?",
        "what generally determines a nutrient deficiency's cause?",
    ]


async def test_multi_query_generates_variants_for_the_literal_question_and_keeps_it() -> None:
    # Arrange — the happy path: one cascade call, one seed (the literal question, the only
    # query whose `produced_by` matches the default `expand_origins=("",)`), and the literal
    # question kept alongside the variants per the default `keep_question=True`.
    asked = Query(text="why does mRMR outperform plain relevance ranking?")
    payload = QuerySet(origin=asked, queries=(asked,))
    llm = _StubLLM(
        [
            '{"groups": [{"index": 0, "variants": '
            '["what makes mRMR better than a relevance-only ranking?", '
            '"how does mRMR compare against ranking by relevance alone?"]}]}'
        ]
    )
    lookup = _multiquery_lookup()

    # Act
    outcome = await MultiQuery(MultiQueryConfig(variants=2)).run(
        payload, _ctx(_services(llm, lookup))
    )

    # Assert
    assert isinstance(outcome, Produced)
    result: QuerySet = outcome.value
    assert result.origin == payload.origin
    assert [q.text for q in result.queries] == [
        "why does mRMR outperform plain relevance ranking?",
        "what makes mRMR better than a relevance-only ranking?",
        "how does mRMR compare against ranking by relevance alone?",
    ]
    for derived in result.queries[1:]:
        assert derived.origin is QueryOrigin.DERIVED
        assert derived.produced_by == MULTI_QUERY_NAME
    assert lookup.asked == [MULTI_QUERY_VARIANTS_NAME]
    assert llm.calls == 1


async def test_multi_query_expands_only_queries_whose_produced_by_matches_expand_origins() -> None:
    # Arrange — `.phase2-design.md`'s own worked example: composing this transform after one
    # that already derived a query (here standing in for `hyde`) must not re-expand what the
    # earlier transform produced, which is why composing two fan-out stages does not multiply.
    # The default `expand_origins=("",)` selects only the literal question below.
    asked = Query(text="what causes catalyst poisoning?")
    already_derived = Query(
        text="a hypothetical passage about catalyst poisoning",
        origin=QueryOrigin.DERIVED,
        produced_by="hyde",
    )
    payload = QuerySet(origin=asked, queries=(asked, already_derived))
    llm = _StubLLM(['{"groups": [{"index": 0, "variants": ["v1", "v2", "v3", "v4"]}]}'])

    # Act
    outcome = await MultiQuery().run(payload, _ctx(_services(llm, _multiquery_lookup())))

    # Assert — 2 original queries + 4 variants of the one that matched, never 8.
    assert isinstance(outcome, Produced)
    result: QuerySet = outcome.value
    assert len(result.queries) == 6
    assert result.queries[0] == asked
    assert result.queries[1] == already_derived
    variants = result.queries[2:]
    assert [q.text for q in variants] == ["v1", "v2", "v3", "v4"]
    for variant in variants:
        assert variant.produced_by == MULTI_QUERY_NAME


async def test_multi_query_batches_every_matched_seed_into_one_cascade_call() -> None:
    # Arrange — two seeds match `expand_origins`, and `cost_bound` is `(1, 1)`: the batching
    # is what keeps that true regardless of how many queries are being expanded at once.
    asked = Query(text="what limits catalyst lifetime?")
    second_seed = Query(
        text="what accelerates catalyst deactivation?",
        origin=QueryOrigin.DERIVED,
        produced_by="step-back",
    )
    payload = QuerySet(origin=asked, queries=(asked, second_seed))
    llm = _StubLLM(
        ['{"groups": [{"index": 0, "variants": ["v1"]}, {"index": 1, "variants": ["v2"]}]}']
    )

    # Act
    outcome = await MultiQuery(MultiQueryConfig(expand_origins=("", "step-back"), variants=1)).run(
        payload, _ctx(_services(llm, _multiquery_lookup()))
    )

    # Assert — one call fanned both seeds out, not two calls.
    assert isinstance(outcome, Produced)
    assert [q.text for q in outcome.value.queries] == [
        "what limits catalyst lifetime?",
        "what accelerates catalyst deactivation?",
        "v1",
        "v2",
    ]
    assert llm.calls == 1


async def test_multi_query_require_distinct_drops_a_duplicate_variant() -> None:
    # Arrange — the edge case: a model answering with a near-duplicate of the seed's own
    # question (differing only by trailing whitespace and case) is dropped rather than kept
    # as a second, redundant probe — `10` §1.1's own finding: "near-duplicate queries
    # weaken the fusion, whose benefit comes from rankings that disagree."
    asked = Query(text="what is feature selection?")
    payload = QuerySet(origin=asked, queries=(asked,))
    llm = _StubLLM(
        [
            '{"groups": [{"index": 0, "variants": '
            '["What Is Feature Selection?  ", "how do you choose which features to keep?"]}]}'
        ]
    )

    # Act
    outcome = await MultiQuery(MultiQueryConfig(variants=2)).run(
        payload, _ctx(_services(llm, _multiquery_lookup()))
    )

    # Assert — the near-duplicate of the seed's own text never becomes a second `Query`.
    assert isinstance(outcome, Produced)
    assert [q.text for q in outcome.value.queries] == [
        "what is feature selection?",
        "how do you choose which features to keep?",
    ]


async def test_multi_query_keep_question_false_drops_the_expanded_seed() -> None:
    # Arrange — the edge case: the named knob, `keep_question`, set away from its default
    # drops the seed that was expanded, keeping only its variants.
    asked = Query(text="what is overfitting?")
    payload = QuerySet(origin=asked, queries=(asked,))
    llm = _StubLLM(['{"groups": [{"index": 0, "variants": ["why does a model overfit?"]}]}'])

    # Act
    outcome = await MultiQuery(MultiQueryConfig(keep_question=False)).run(
        payload, _ctx(_services(llm, _multiquery_lookup()))
    )

    # Assert
    assert isinstance(outcome, Produced)
    assert [q.text for q in outcome.value.queries] == ["why does a model overfit?"]


async def test_multi_query_no_seed_matches_expand_origins_is_refused_by_name() -> None:
    # Arrange — the error case: every query in this set was itself derived, none has
    # `produced_by` in the default `expand_origins=("",)`, and there is nothing to expand.
    # `cost_bound`'s floor of one is for a *successful* run; a misconfiguration is refused
    # before any model is asked anything, naming the mismatch rather than guessing at a seed.
    asked = Query(text="was this ever the literal question?")
    derived = Query(
        text="a step-back abstraction", origin=QueryOrigin.DERIVED, produced_by="step-back"
    )
    payload = QuerySet(origin=asked, queries=(derived,))

    # Act
    outcome = await MultiQuery().run(payload, _ctx(_services(_RefusingLLM())))

    # Assert
    assert isinstance(outcome, Failed)
    assert "expand_origins" in outcome.reason


async def test_multi_query_a_cascade_that_could_not_answer_is_relayed_not_papered_over() -> None:
    # Arrange — the error case: `on_failure` has one member (`FAIL`) today, and relaying the
    # cascade's own outcome *is* that behaviour, the same as every other transform in this
    # module.
    asked = Query(text="what is regularisation?")
    payload = QuerySet(origin=asked, queries=(asked,))
    llm = _StubLLM(["I cannot help with that."])

    # Act
    outcome = await MultiQuery().run(payload, _ctx(_services(llm, _multiquery_lookup())))

    # Assert
    assert isinstance(outcome, Failed)


async def test_multi_query_a_group_answering_for_an_unoffered_index_is_refused_by_name() -> None:
    # Arrange — the model answered for an index this call never offered (only index 0 was
    # offered) — the same "the model invented something" refusal `llm-rerank`'s own
    # `_scores_by_index` makes, applied to this plugin's own indexed response.
    asked = Query(text="what is cross-validation?")
    payload = QuerySet(origin=asked, queries=(asked,))
    llm = _StubLLM(['{"groups": [{"index": 3, "variants": ["v1"]}]}'])

    # Act
    outcome = await MultiQuery().run(payload, _ctx(_services(llm, _multiquery_lookup())))

    # Assert
    assert isinstance(outcome, Failed)
    assert "3" in outcome.reason


async def test_driving_multi_query_through_the_seam_composes_a_new_query_set() -> None:
    """Fitness function 7(b) against the one path a registered plugin is actually called
    through in production — `weft_kernel.seam.wrap`, not a direct method call a registered
    instance never receives."""
    # Arrange
    asked = Query(text="what drives model drift?")
    payload = QuerySet(origin=asked, queries=(asked,))
    llm = _StubLLM(['{"groups": [{"index": 0, "variants": ["what causes a model to drift?"]}]}'])
    transform = MultiQuery()
    wrapped = wrap(
        transform.run,
        distribution="weft-retrieve",
        contract="QueryTransform",
        plugin=MULTI_QUERY_NAME,
    )

    # Act
    outcome = await wrapped(payload, _ctx(_services(llm, _multiquery_lookup())))

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value.origin == payload.origin
    assert len(outcome.value.queries) == 2
    assert isinstance(transform, QueryTransform)


def test_multi_query_config_defaults_match_the_design_records_table() -> None:
    # Act / Assert — requirement 6's second clause, read off the config model: an operator
    # retunes every one of these without touching this distribution.
    config = MultiQueryConfig()
    assert config.variants == 4
    assert config.keep_question is True
    assert config.expansion is ExpansionKind.ASPECT
    assert config.require_distinct is True
    assert config.expand_origins == ("",)
    assert config.prompt == MULTI_QUERY_VARIANTS_NAME
    assert MultiQuery.config_model is MultiQueryConfig


def test_multi_query_declared_cost_bound_is_one_to_one() -> None:
    # Act / Assert — always exactly one cascade call, batched over however many seeds
    # matched `expand_origins` — see the batching test above.
    assert MultiQuery.cost_bound == (1, 1)
