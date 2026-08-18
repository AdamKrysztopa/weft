"""This pack's own tests for `ExampleFixedRetriever`."""

from weft_example_query.retriever import NAME, ExampleFixedRetriever

from weft_kernel.context import Context
from weft_kernel.payload import Produced
from weft_kernel.seam import wrap
from weft_retrieve.contract import Retriever
from weft_retrieve.payload import Query, QuerySet


def _ctx() -> Context:
    return Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")


async def test_retriever_answers_every_query_with_the_fixture_passages_through_the_seam() -> None:
    # Arrange
    retriever = ExampleFixedRetriever()
    wrapped = wrap(
        retriever.run, distribution="weft-example-query", contract="Retriever", plugin=NAME
    )
    query = Query(text="what is weft")
    payload = QuerySet(origin=query, queries=(query,))

    # Act
    outcome = await wrapped(payload, _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    assert len(outcome.value.lists) == 1
    ranked = outcome.value.lists[0]
    assert ranked.query == query
    assert ranked.retriever == NAME
    assert len(ranked.hits) == 2
    assert ranked.hits[0].score > ranked.hits[1].score


async def test_retriever_needs_no_store_capability() -> None:
    # Act / Assert — the whole point of this pack's own module docstring.
    assert ExampleFixedRetriever.needs_store == ()


async def test_retriever_satisfies_the_retriever_contract_structurally() -> None:
    # Act / Assert
    assert isinstance(ExampleFixedRetriever(), Retriever)
