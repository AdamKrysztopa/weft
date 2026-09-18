"""Unit tests for `weft_retrieve.intent_and_anchors` — ledger task **39.0**.

Mirrors `packages/weft-rag/src/weft_retrieve/intent_and_anchors.py`. G24 settled the shape: the
question is split into its intent, searched densely **in the user's original wording**, and its
exact anchors, each searched lexically **on its own**; a question with no anchor asks the text
arm nothing. High precision over high recall — a false anchor costs a query the noise Phase 38
measured, a missed one costs it only the dense arm it had anyway — so the negative cases below
are as much the specification as the positive ones.

The forty-question gate is `39.1`'s and reads a fixture this file does not.
"""

from __future__ import annotations

from collections.abc import Mapping

import pytest
from pydantic import ValidationError

import weft_retrieve
from weft_kernel.context import Context, ServiceRegistry
from weft_kernel.discovery import PackRegistrar
from weft_kernel.payload import Failed, Outcome, Produced
from weft_kernel.registry import Registry
from weft_llm.contract import LLM
from weft_llm.payload import Completion, Rendered
from weft_prompts.contract import Prompt
from weft_retrieve.contract import QueryTransform, StageLookup
from weft_retrieve.intent_and_anchors import (
    NAME,
    AnchorKind,
    AnchorMethod,
    IntentAndAnchors,
    IntentAndAnchorsConfig,
    find_anchors,
)
from weft_retrieve.payload import Channel, Query, QueryOrigin, QuerySet
from weft_retrieve.prompts import QUESTION_ANCHORS_NAME, QuestionAnchorsPrompt
from weft_store.contract import Filter, FilterOp


def _ctx() -> Context:
    """No `LLM`, no store, no embedder: the rule reaches none of them."""
    return Context(
        tenant_id="tenant-a",
        run_id="run-1",
        trace_id="trace-1",
        locale="en",
        services=ServiceRegistry(),
    )


def _asked(text: str, *, filter: Filter | None = None) -> QuerySet:
    query = Query(text=text, locale="en", filter=filter)
    return QuerySet(origin=query, queries=(query,))


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("What is the difference between the controller WRH123 and STX58", ("WRH123", "STX58")),
        ("error E1234 after the upgrade to v2.1.0", ("E1234", "v2.1.0")),
        ("what does RFC 7231 section 4.3.2 say about 404", ("7231", "4.3.2", "404")),
        ("HTTP/2 over IPv6", ("HTTP/2", "IPv6")),
        ("why does the browser show ERR_CONNECTION_REFUSED", ("ERR_CONNECTION_REFUSED",)),
        ("how do I set maxAge on the cookie", ("maxAge",)),
        ("call getElementById from onClick", ("getElementById", "onClick")),
        ("what does §4.3 require", ("4.3",)),
        ("Is STX58, or WRH123?", ("STX58", "WRH123")),
        ("WRH123 against WRH123 again", ("WRH123",)),
    ],
)
def test_identifier_shaped_tokens_are_anchors_in_the_order_they_first_appear(
    text: str, expected: tuple[str, ...]
) -> None:
    # Act
    anchors = find_anchors(text)

    # Assert
    assert tuple(anchor.text for anchor in anchors) == expected
    assert {anchor.kind for anchor in anchors} == {AnchorKind.IDENTIFIER}


@pytest.mark.parametrize(
    "text",
    [
        "I am looking for the best controller for underwater RC",
        "How does TLS protect HTTP traffic from a DNS attacker",
        "does Content-Type matter on Wi-Fi",
        "why did the 2nd and 3rd retries fail",
        "retry 3 times then give up",
        "top 10 tips for caching",
        "what does __init__ do",
        "is DoH supported on iOS and macOS",
        "the iPhone and eBay apps on GitHub",
    ],
)
def test_ordinary_language_acronyms_and_counts_are_not_anchors(text: str) -> None:
    # Act
    anchors = find_anchors(text)

    # Assert
    assert anchors == ()


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ('what does "must not cache" mean for WRH123', ("must not cache", "WRH123")),
        ("what does “must not cache” mean", ("must not cache",)),
        ("where is `max_age` parsed", ("max_age",)),
        ('find the "WRH123 manual"', ("WRH123 manual",)),
    ],
)
def test_a_quoted_span_is_one_anchor_and_what_it_encloses_is_not_split_again(
    text: str, expected: tuple[str, ...]
) -> None:
    # Act
    anchors = find_anchors(text)

    # Assert
    assert tuple(anchor.text for anchor in anchors) == expected
    assert anchors[0].kind is AnchorKind.QUOTED


def test_a_configured_entity_is_an_anchor_matched_as_a_whole_word_and_case_sensitively() -> None:
    # Arrange
    entities = ("Kerberos", "NTLM")

    # Act
    found = find_anchors("compare Kerberos with NTLM and kerberos-like schemes", entities=entities)
    partial = find_anchors("Kerberized services", entities=("Kerberos",))

    # Assert
    assert tuple((anchor.text, anchor.kind) for anchor in found) == (
        ("Kerberos", AnchorKind.ENTITY),
        ("NTLM", AnchorKind.ENTITY),
    )
    assert partial == ()


async def test_the_intent_is_the_question_as_asked_aimed_at_the_vector_arm_alone() -> None:
    # Arrange
    narrowing = Filter(field="lineage.sources", op=FilterOp.EQ, value="rfc7231")
    asked = _asked("What is the difference between WRH123 and STX58", filter=narrowing)

    # Act
    outcome = await IntentAndAnchors().run(asked, _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    out = outcome.value
    assert out.origin == asked.origin
    intent = out.queries[0]
    assert intent.text == asked.origin.text
    assert intent.origin is QueryOrigin.USER
    assert intent.produced_by == ""
    assert tuple(intent.channels) == (Channel.VECTOR.value,)
    assert intent.filter == narrowing


async def test_each_anchor_is_its_own_query_aimed_at_the_text_arm_alone() -> None:
    # Arrange
    narrowing = Filter(field="lineage.sources", op=FilterOp.EQ, value="rfc7231")
    asked = _asked("What is the difference between WRH123 and STX58", filter=narrowing)

    # Act
    outcome = await IntentAndAnchors().run(asked, _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    anchors = outcome.value.queries[1:]
    assert [query.text for query in anchors] == ["WRH123", "STX58"]
    for query in anchors:
        assert tuple(query.channels) == (Channel.TEXT.value,)
        assert query.origin is QueryOrigin.DERIVED
        assert query.produced_by == NAME
        assert query.filter == narrowing
        assert query.locale == "en"


async def test_a_question_with_no_anchor_asks_the_text_arm_nothing() -> None:
    # Arrange
    asked = _asked("I am looking for the best controller for underwater RC")

    # Act
    outcome = await IntentAndAnchors().run(asked, _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    queries = outcome.value.queries
    assert len(queries) == 1
    assert queries[0].text == asked.origin.text
    assert all(Channel.TEXT.value not in query.channels for query in queries)


async def test_configured_entities_reach_the_rule() -> None:
    # Arrange
    transform = IntentAndAnchors(IntentAndAnchorsConfig(entities=("Kerberos",)))

    # Act
    outcome = await transform.run(_asked("how does Kerberos renew a ticket"), _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    assert [query.text for query in outcome.value.queries[1:]] == ["Kerberos"]


async def test_a_query_another_transform_derived_passes_through_untouched() -> None:
    # Arrange
    user = Query(text="what does WRH123 do")
    derived = Query(
        text="WRH123 is a controller that ...",
        origin=QueryOrigin.DERIVED,
        produced_by="hyde",
        channels=(Channel.VECTOR.value,),
    )
    asked = QuerySet(origin=user, queries=(user, derived))

    # Act
    outcome = await IntentAndAnchors().run(asked, _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    assert derived in outcome.value.queries
    user_worded = [query for query in outcome.value.queries if query.produced_by == ""]
    assert len(user_worded) == 1
    assert tuple(user_worded[0].channels) == (Channel.VECTOR.value,)


def test_a_blank_entity_is_refused_at_the_field() -> None:
    # Act / Assert
    with pytest.raises(ValidationError, match="entities"):
        IntentAndAnchorsConfig(entities=("Kerberos", ""))


def test_an_unknown_config_key_is_refused() -> None:
    # Act / Assert
    with pytest.raises(ValidationError, match="entites"):
        IntentAndAnchorsConfig.model_validate({"entites": ["Kerberos"]})


def test_register_adds_intent_and_anchors_under_the_query_transform_contract() -> None:
    # Arrange
    registry = Registry()
    registrar = PackRegistrar(registry, distribution="weft-rag")

    # Act
    weft_retrieve.register(registrar, weft_retrieve.Settings())
    registrar.commit()

    # Assert
    assert NAME == "intent-and-anchors"
    assert isinstance(registry.entry(QueryTransform, NAME).factory(None), IntentAndAnchors)


class _StubLLM:
    """An `LLM` answering tier 2 of the cascade from a script — `test_transforms.py`'s own."""

    def __init__(self, replies: list[str]) -> None:
        self._replies = replies
        self.calls = 0
        self.roles: list[str] = []

    async def native_structured_available(self, role: str) -> bool:
        del role
        return False

    async def complete_structured(
        self, rendered: Rendered, schema: Mapping[str, object], *, role: str, ctx: Context
    ) -> Outcome[Completion]:
        raise AssertionError("tier 1 is unavailable on this stub and must not be reached")

    async def complete(self, rendered: Rendered, *, role: str, ctx: Context) -> Outcome[Completion]:
        del rendered, ctx
        self.roles.append(role)
        reply = self._replies[min(self.calls, len(self._replies) - 1)]
        self.calls += 1
        return Produced(value=Completion(text=reply, model="stub-model"))

    async def close(self) -> None: ...


class _StubLookup:
    """A `StageLookup` holding this pack's own prompts — `test_transforms.py`'s own."""

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


def _model_ctx(llm: _StubLLM) -> Context:
    services = ServiceRegistry()
    services.add(LLM, llm)
    services.add(StageLookup, _StubLookup({QUESTION_ANCHORS_NAME: QuestionAnchorsPrompt()}))
    return Context(
        tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en", services=services
    )


def _by_model() -> IntentAndAnchors:
    return IntentAndAnchors(IntentAndAnchorsConfig(method=AnchorMethod.MODEL))


async def test_the_model_method_turns_each_anchor_it_names_into_a_text_arm_query() -> None:
    # Arrange
    llm = _StubLLM(['{"anchors": ["ETIMEDOUT", "X-Forwarded-For"]}'])
    asked = _asked("does ETIMEDOUT mean the X-Forwarded-For header was dropped after 30 seconds")

    # Act
    outcome = await _by_model().run(asked, _model_ctx(llm))

    # Assert
    assert isinstance(outcome, Produced)
    intent, *anchors = outcome.value.queries
    assert intent.text == asked.origin.text
    assert tuple(intent.channels) == (Channel.VECTOR.value,)
    assert [query.text for query in anchors] == ["ETIMEDOUT", "X-Forwarded-For"]
    assert all(tuple(query.channels) == (Channel.TEXT.value,) for query in anchors)
    assert all(query.produced_by == NAME for query in anchors)
    assert llm.calls == 1


async def test_the_model_method_asks_under_its_own_role() -> None:
    # Arrange
    llm = _StubLLM(['{"anchors": []}'])

    # Act
    await _by_model().run(_asked("is a 5 GHz band faster"), _model_ctx(llm))

    # Assert
    assert llm.roles == ["anchors"]


async def test_the_model_naming_no_anchor_asks_the_text_arm_nothing() -> None:
    # Arrange
    llm = _StubLLM(['{"anchors": []}'])
    asked = _asked("is a 5 GHz band always faster in a crowded office")

    # Act
    outcome = await _by_model().run(asked, _model_ctx(llm))

    # Assert
    assert isinstance(outcome, Produced)
    assert len(outcome.value.queries) == 1
    assert all(Channel.TEXT.value not in query.channels for query in outcome.value.queries)


async def test_an_anchor_the_question_does_not_contain_fails_rather_than_being_searched() -> None:
    # Arrange — a lexical search for a span the user never typed is a hallucination searched
    # exactly, which is worse than no anchor at all.
    llm = _StubLLM(['{"anchors": ["ETIMEDOUT", "ECONNRESET"]}'])
    asked = _asked("what does ETIMEDOUT mean")

    # Act
    outcome = await _by_model().run(asked, _model_ctx(llm))

    # Assert
    assert isinstance(outcome, Failed)
    assert "ECONNRESET" in outcome.reason
    assert "does not contain" in outcome.reason


async def test_a_repeated_model_anchor_is_searched_once() -> None:
    # Arrange
    llm = _StubLLM(['{"anchors": ["AX6000", "AX6000"]}'])

    # Act
    outcome = await _by_model().run(_asked("AX6000 or AX6000 v2"), _model_ctx(llm))

    # Assert
    assert isinstance(outcome, Produced)
    assert [query.text for query in outcome.value.queries[1:]] == ["AX6000"]


def test_entities_are_refused_beside_the_model_method_because_it_would_ignore_them() -> None:
    # Act / Assert
    with pytest.raises(ValidationError, match="entities"):
        IntentAndAnchorsConfig(method=AnchorMethod.MODEL, entities=("Kerberos",))


def test_the_rule_is_the_default_so_no_model_is_called_unless_asked() -> None:
    # Act
    config = IntentAndAnchorsConfig()

    # Assert
    assert config.method is AnchorMethod.RULE
    assert AnchorKind.EXTRACTED.value == "extracted"


def test_register_adds_the_question_anchors_prompt() -> None:
    # Arrange
    registry = Registry()
    registrar = PackRegistrar(registry, distribution="weft-rag")

    # Act
    weft_retrieve.register(registrar, weft_retrieve.Settings())
    registrar.commit()

    # Assert
    assert QUESTION_ANCHORS_NAME == "question-anchors"
    assert isinstance(
        registry.entry(Prompt, QUESTION_ANCHORS_NAME).factory(None), QuestionAnchorsPrompt
    )


async def test_the_model_may_recombine_words_the_user_typed() -> None:
    # Arrange — recall first (G24, reversed 2026-09-18): `TLS 1.2` is not a span of the question,
    # but every word of it is, so it is searched rather than losing the question's anchors.
    llm = _StubLLM(['{"anchors": ["TLS 1.3", "TLS 1.2"]}'])
    asked = _asked("Is TLS 1.3 backwards compatible with 1.2?")

    # Act
    outcome = await _by_model().run(asked, _model_ctx(llm))

    # Assert
    assert isinstance(outcome, Produced)
    assert [query.text for query in outcome.value.queries[1:]] == ["TLS 1.3", "TLS 1.2"]


@pytest.mark.parametrize(
    ("named", "searched"),
    [("getSocketOpt()", "getSocketOpt"), ("6335's", "6335")],
)
async def test_call_parentheses_and_a_possessive_are_not_part_of_what_is_searched(
    named: str, searched: str
) -> None:
    # Arrange
    llm = _StubLLM([f'{{"anchors": ["{named}"]}}'])
    asked = _asked("does getSocketOpt() read RFC 6335's registry")

    # Act
    outcome = await _by_model().run(asked, _model_ctx(llm))

    # Assert
    assert isinstance(outcome, Produced)
    assert [query.text for query in outcome.value.queries[1:]] == [searched]


@pytest.mark.parametrize(
    "amount", ["5GHz", "2.4GHz", "32MB", "16 GB", "100ms", "10Gbps", "64KiB", "250us"]
)
def test_a_number_with_a_unit_is_an_amount_and_never_an_anchor(amount: str) -> None:
    # Arrange — the one error class both extractors shared at 39.1's gate: an amount glued to its
    # unit reads as a part number by shape.
    text = f"does AX6000 firmware v2.1.0 run at {amount}?"

    # Act
    anchors = find_anchors(text)

    # Assert
    assert [anchor.text for anchor in anchors] == ["AX6000", "v2.1.0"]


async def test_the_model_path_drops_a_unit_bearing_amount_it_named() -> None:
    # Arrange
    llm = _StubLLM(['{"anchors": ["AX6000", "5GHz", "2.4GHz", "v2.1.0"]}'])
    asked = _asked("does AX6000 on v2.1.0 prefer 5GHz over 2.4GHz?")

    # Act
    outcome = await _by_model().run(asked, _model_ctx(llm))

    # Assert
    assert isinstance(outcome, Produced)
    assert [query.text for query in outcome.value.queries[1:]] == ["AX6000", "v2.1.0"]
