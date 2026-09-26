"""Unit tests for `weft_retrieve.whole_corpus` — ledger task **43.49**.

`whole-corpus` hands the generator every leaf of the bound target as one ranked list, in source
order then chunk ordinal, and never reads the question. It counts each leaf with the generating
role's tokenizer as it reads, and the moment the total passes `max_tokens` it stops and refuses by
name — never a silent cut (the owner's rule, settled 2026-09-26). The refusal is a raise, not a
`Failed`: the fault is the corpus and the configuration, not the question (`L28.1`).

The counter counts whitespace-separated words, as `test_repack_budget.py`'s does, and every leaf in
`leaf_corpus` is a fixed number of words, so each total is checkable by hand.
"""

from typing import NoReturn

import pytest
from pydantic import ValidationError

import weft_retrieve
from tests.unit.weft_retrieve.leaf_corpus import Corpus, corpus, stored
from weft_cli.exit_codes import ExitCode
from weft_cli.render import render_refusal
from weft_kernel.context import Context, ServiceRegistry
from weft_kernel.discovery import PackRegistrar
from weft_kernel.payload import Outcome, Produced
from weft_kernel.registry import Registry
from weft_llm.contract import LLM
from weft_llm.errors import TokenCountUnavailableError
from weft_retrieve.contract import Retriever
from weft_retrieve.payload import Candidates, Passage, Query, QuerySet
from weft_retrieve.whole_corpus import (
    NAME,
    CorpusOverTokenBoundError,
    WholeCorpus,
    WholeCorpusConfig,
)
from weft_store.contract import Filter, FilterOp, MetadataFilter, NodeStore

_WORDS = 600


class _WordCounter:
    def __init__(self) -> None:
        self.roles: list[str] = []
        self.texts: list[str] = []

    async def count_tokens(self, role: str, text: str) -> int:
        self.roles.append(role)
        self.texts.append(text)
        return len(text.split())


class _CannotCount:
    async def count_tokens(self, role: str, text: str) -> int:
        del text
        raise TokenCountUnavailableError(role=role, provider="scripted", model="any-model")


class _Untouchable(tuple[Query, ...]):
    """`QuerySet.queries` for a retriever that must not read it: any use fails the test."""

    def _read(self, *_args: object) -> NoReturn:
        raise AssertionError("'whole-corpus' read payload.queries; it offers every leaf unasked")

    __iter__ = _read
    __len__ = _read
    __getitem__ = _read
    __bool__ = _read
    __contains__ = _read


def _ctx(store: object, llm: object) -> Context:
    services = ServiceRegistry()
    services.add(NodeStore, store)
    services.add(LLM, llm)
    return Context(
        tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en", services=services
    )


def _unread_question(text: str) -> QuerySet:
    """A question whose origin carries a filter the store double cannot evaluate.

    `leaf_selection.selects` raises on an `EQ` over `id`, so a retriever that narrowed the leaf
    read by the question's own filter fails loudly rather than being answered.
    """
    origin = Query(text=text, filter=Filter(op=FilterOp.EQ, field="id", value="nowhere"))
    return QuerySet.model_construct(origin=origin, queries=_Untouchable(), history=(), ext={})


def _question() -> QuerySet:
    origin = Query(text="what did the Curies find?")
    return QuerySet(origin=origin, queries=(origin,))


def _offered(outcome: Outcome[Candidates]) -> Candidates:
    assert isinstance(outcome, Produced), outcome
    assert isinstance(outcome.value, Candidates)
    return outcome.value


def _hits(outcome: Outcome[Candidates]) -> tuple[Passage, ...]:
    """The one list a whole-corpus read produces — one list, whatever the corpus holds."""
    offered = _offered(outcome)
    assert len(offered.lists) == 1, offered.lists
    return offered.lists[0].hits


def _total(fixture: Corpus) -> int:
    return sum(len(leaf.content.split()) for leaf in fixture.leaves)


def test_it_is_registered_as_a_retriever_that_needs_a_filterable_store() -> None:
    # Arrange
    registry = Registry()
    registrar = PackRegistrar(registry, distribution="weft-retrieve")

    # Act
    weft_retrieve.register(registrar, weft_retrieve.Settings())
    registrar.commit()

    # Assert
    assert NAME == "whole-corpus"
    assert NAME in registry.names_for(Retriever)
    assert isinstance(registry.entry(Retriever, NAME).factory(None), WholeCorpus)
    assert isinstance(WholeCorpus(), Retriever)
    assert WholeCorpus.needs_store == (MetadataFilter,)


def test_the_bound_defaults_to_a_hundred_thousand_tokens_counted_for_the_generate_role() -> None:
    # Act
    config = WholeCorpusConfig()

    # Assert
    assert config.max_tokens == 100_000
    assert config.role == "generate"


@pytest.mark.parametrize("field", [{"max_tokens": 0}, {"role": ""}, {"top_k": 8}])
def test_a_zero_bound_a_blank_role_and_an_unknown_field_are_refused(
    field: dict[str, object],
) -> None:
    # Act / Assert
    with pytest.raises(ValidationError):
        WholeCorpusConfig.model_validate(field)


async def test_every_leaf_comes_back_once_in_source_then_ordinal_order() -> None:
    # Arrange
    fixture = corpus()
    store = await stored(fixture)
    expected = [leaf.id for leaf in fixture.leaves]
    assert [node.id for node in fixture.stored_order()] != expected
    assert sorted(expected) != expected

    # Act
    offered = _offered(await WholeCorpus().run(_question(), _ctx(store, _WordCounter())))

    # Assert
    assert len(offered.lists) == 1
    ranked = offered.lists[0]
    assert ranked.retriever == NAME
    assert [hit.node.id for hit in ranked.hits] == expected
    assert [hit.rank for hit in ranked.hits] == list(range(len(expected)))
    assert {hit.retrieved_by for hit in ranked.hits} == {NAME}


async def test_no_score_ranks_a_later_leaf_above_an_earlier_one() -> None:
    """A consumer that orders by score, keeping ties in place, still reads source order."""
    # Arrange
    store = await stored(corpus())

    # Act
    hits = _hits(await WholeCorpus().run(_question(), _ctx(store, _WordCounter())))

    # Assert
    scores = [hit.score for hit in hits]
    assert scores == sorted(scores, reverse=True)


async def test_the_question_is_never_read_so_two_questions_are_offered_the_same_leaves() -> None:
    # Arrange
    fixture = corpus()
    store = await stored(fixture)
    first, second = _unread_question("polonium?"), _unread_question("what is radium's half-life?")

    # Act
    by_first = await WholeCorpus().run(first, _ctx(store, _WordCounter()))
    by_second = await WholeCorpus().run(second, _ctx(store, _WordCounter()))

    # Assert
    expected = [leaf.id for leaf in fixture.leaves]
    assert [hit.node.id for hit in _hits(by_first)] == expected
    assert [hit.node.id for hit in _hits(by_second)] == expected
    assert _offered(by_first).origin == first.origin


async def test_every_leaf_is_counted_once_for_the_configured_role() -> None:
    # Arrange
    fixture = corpus()
    store = await stored(fixture)
    counter = _WordCounter()
    config = WholeCorpusConfig(role="long-context")

    # Act
    await WholeCorpus(config).run(_question(), _ctx(store, counter))

    # Assert
    assert sorted(counter.texts) == sorted(leaf.content for leaf in fixture.leaves)
    assert set(counter.roles) == {"long-context"}


async def test_a_corpus_exactly_at_the_bound_is_offered_whole() -> None:
    # Arrange
    fixture = corpus(words=_WORDS)
    store = await stored(fixture)
    config = WholeCorpusConfig(max_tokens=_total(fixture))

    # Act
    hits = _hits(await WholeCorpus(config).run(_question(), _ctx(store, _WordCounter())))

    # Assert
    assert len(hits) == len(fixture.leaves)


async def test_a_corpus_over_the_bound_is_refused_naming_total_bound_and_remedies() -> None:
    # Arrange — each leaf is 600 tokens, so the second read reaches 1,200 against 1,000, partway
    # through the store's first page of three.
    store = await stored(corpus(words=_WORDS))
    counter = _WordCounter()
    config = WholeCorpusConfig(max_tokens=1_000)

    # Act
    with pytest.raises(CorpusOverTokenBoundError) as refused:
        await WholeCorpus(config).run(_question(), _ctx(store, counter))

    # Assert
    message = str(refused.value)
    assert (refused.value.counted, refused.value.bound) == (1_200, 1_000)
    assert f"'{NAME}'" in message
    assert "at least 1,200 tokens against a bound of 1,000 tokens" in message
    assert "raise max_tokens" in message
    assert "retrieve-then-generate" in message
    assert len(counter.texts) <= 2


async def test_the_refusal_an_operator_reads_states_the_bound_and_exits_one() -> None:
    # Arrange
    store = await stored(corpus(words=_WORDS))
    config = WholeCorpusConfig(max_tokens=1_000)
    with pytest.raises(CorpusOverTokenBoundError) as refused:
        await WholeCorpus(config).run(_question(), _ctx(store, _WordCounter()))

    # Act
    rendered = render_refusal(refused.value)

    # Assert
    assert rendered.exit_code is ExitCode.OPERATION_FAILED
    assert "a bound of 1,000 tokens" in (rendered.stderr or "")


async def test_a_model_that_cannot_count_is_refused_rather_than_estimated() -> None:
    # Arrange
    store = await stored(corpus())

    # Act / Assert
    with pytest.raises(TokenCountUnavailableError):
        await WholeCorpus().run(_question(), _ctx(store, _CannotCount()))


async def test_an_empty_corpus_is_a_search_that_found_nothing_not_one_never_asked() -> None:
    # Arrange
    store = await stored(Corpus(leaves=(), excluded=corpus().excluded))

    # Act
    hits = _hits(await WholeCorpus().run(_question(), _ctx(store, _WordCounter())))

    # Assert
    assert hits == ()
