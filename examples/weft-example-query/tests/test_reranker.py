"""This pack's own tests for `ExampleReranker`."""

from weft_example_query.reranker import ExampleReranker

from weft_kernel.context import Context
from weft_kernel.payload import MediaType, Node, Produced
from weft_kernel.seam import wrap
from weft_retrieve.contract import Reranker
from weft_retrieve.payload import Passage, Query, Ranking
from weft_store.contract import Scored


def _ctx() -> Context:
    return Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")


def _passage(text: str, rank: int) -> Passage:
    node = Node.synthetic(content=text, media_type=MediaType.TEXT, reason="fixture", ordinal=rank)
    return Passage(scored=Scored(value=node, score=0.0), rank=rank, retrieved_by="fixture")


async def test_reranker_rescores_by_overlap_with_the_original_question_through_the_seam() -> None:
    # Arrange
    reranker = ExampleReranker()
    wrapped = wrap(
        reranker.run,
        distribution="weft-example-query",
        contract="Reranker",
        plugin="example-overlap-rerank",
    )
    on_topic = _passage("weft is a rag engine", 0)
    off_topic = _passage("completely unrelated words", 1)
    payload = Ranking(origin=Query(text="weft rag engine"), hits=(off_topic, on_topic))

    # Act
    outcome = await wrapped(payload, _ctx())

    # Assert — the passage sharing words with the original question is ranked first, even
    # though it started second.
    assert isinstance(outcome, Produced)
    assert outcome.value.hits[0].node.id == on_topic.node.id
    assert outcome.value.hits[0].rank == 0
    assert outcome.value.origin == payload.origin


async def test_reranker_on_no_hits_produces_an_empty_ranking() -> None:
    # Arrange
    reranker = ExampleReranker()
    payload = Ranking(origin=Query(text="anything"), hits=())

    # Act
    outcome = await reranker.run(payload, _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value.hits == ()


async def test_reranker_satisfies_the_reranker_contract_structurally() -> None:
    # Act / Assert
    assert isinstance(ExampleReranker(), Reranker)
