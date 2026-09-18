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

import pytest
from pydantic import ValidationError

import weft_retrieve
from weft_kernel.context import Context, ServiceRegistry
from weft_kernel.discovery import PackRegistrar
from weft_kernel.payload import Produced
from weft_kernel.registry import Registry
from weft_retrieve.contract import QueryTransform
from weft_retrieve.intent_and_anchors import (
    NAME,
    AnchorKind,
    IntentAndAnchors,
    IntentAndAnchorsConfig,
    find_anchors,
)
from weft_retrieve.payload import Channel, Query, QueryOrigin, QuerySet
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
