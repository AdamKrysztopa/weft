"""This pack's own tests for `ExampleContextPacker`."""

from weft_example_query.packer import ExampleContextPacker, ExampleContextPackerConfig

from weft_kernel.context import Context
from weft_kernel.payload import MediaType, Node, Produced
from weft_kernel.seam import wrap
from weft_retrieve.contract import ContextPacker
from weft_retrieve.payload import Passage, Query, Ranking
from weft_store.contract import Scored


def _ctx() -> Context:
    return Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")


def _passage(text: str, rank: int) -> Passage:
    node = Node.synthetic(content=text, media_type=MediaType.TEXT, reason="fixture", ordinal=rank)
    return Passage(
        scored=Scored(value=node, score=1.0 - rank * 0.1), rank=rank, retrieved_by="fixture"
    )


async def test_packer_labels_the_top_n_in_rank_order_through_the_seam() -> None:
    # Arrange
    packer = ExampleContextPacker(ExampleContextPackerConfig(top_n=2))
    wrapped = wrap(
        packer.run,
        distribution="weft-example-query",
        contract="ContextPacker",
        plugin="example-top-n",
    )
    payload = Ranking(
        origin=Query(text="q"), hits=(_passage("a", 0), _passage("b", 1), _passage("c", 2))
    )

    # Act
    outcome = await wrapped(payload, _ctx())

    # Assert — `top_n=2` keeps only the first two, and `Passages`' own validator would have
    # refused a blank or repeated label had this plugin gotten one wrong.
    assert isinstance(outcome, Produced)
    assert [p.label for p in outcome.value.passages] == ["[1]", "[2]"]
    assert [p.node.content for p in outcome.value.passages] == ["a", "b"]


async def test_packer_on_no_hits_produces_no_passages() -> None:
    # Arrange
    packer = ExampleContextPacker()
    payload = Ranking(origin=Query(text="q"), hits=())

    # Act
    outcome = await packer.run(payload, _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value.passages == ()


async def test_packer_satisfies_the_contextpacker_contract_structurally() -> None:
    # Act / Assert
    assert isinstance(ExampleContextPacker(), ContextPacker)
