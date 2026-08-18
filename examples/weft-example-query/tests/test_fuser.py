"""This pack's own tests for `ExampleFuser`."""

from weft_example_query.fuser import ExampleFuser

from weft_kernel.context import Context
from weft_kernel.payload import MediaType, Node, Produced
from weft_kernel.seam import wrap
from weft_retrieve.contract import Fuser
from weft_retrieve.payload import Candidates, Passage, Query, RankedList
from weft_store.contract import Scored


def _ctx() -> Context:
    return Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")


def _passage(text: str, score: float, rank: int, retriever: str) -> Passage:
    node = Node.synthetic(content=text, media_type=MediaType.TEXT, reason="fixture", ordinal=rank)
    return Passage(scored=Scored(value=node, score=score), rank=rank, retrieved_by=retriever)


async def test_fuser_dedupes_and_sorts_by_score_through_the_seam() -> None:
    # Arrange
    fuser = ExampleFuser()
    wrapped = wrap(
        fuser.run,
        distribution="weft-example-query",
        contract="Fuser",
        plugin="example-concat-dedupe",
    )
    shared = _passage("shared node", 0.4, 0, "vector")
    high = _passage("shared node", 0.9, 0, "text")  # same content -> same node id, higher score
    unique = _passage("unique node", 0.5, 1, "vector")
    query = Query(text="q")
    candidates = Candidates(
        origin=query,
        lists=(
            RankedList(query=query, retriever="vector", hits=(shared, unique)),
            RankedList(query=query, retriever="text", hits=(high,)),
        ),
    )

    # Act
    outcome = await wrapped(candidates, _ctx())

    # Assert — the first sighting of the shared node id is kept (from "vector"), the later
    # duplicate from "text" is dropped even though its score is higher; ordering is by the
    # kept passage's own score.
    assert isinstance(outcome, Produced)
    node_ids = [passage.node.id for passage in outcome.value.hits]
    assert len(node_ids) == 2
    assert node_ids[0] == unique.node.id  # 0.5 > 0.4
    assert outcome.value.hits[0].rank == 0
    assert set(outcome.value.contributors) == {"vector", "text"}


async def test_fuser_on_no_lists_produces_an_empty_ranking() -> None:
    # Arrange
    fuser = ExampleFuser()
    query = Query(text="q")

    # Act
    outcome = await fuser.run(Candidates(origin=query, lists=()), _ctx())

    # Assert — the emptiness rule: `Produced` carrying an empty collection, never
    # `NothingToProduce`, which would stop a query-path pipeline entirely.
    assert isinstance(outcome, Produced)
    assert outcome.value.hits == ()


async def test_fuser_satisfies_the_fuser_contract_structurally() -> None:
    # Act / Assert
    assert isinstance(ExampleFuser(), Fuser)
