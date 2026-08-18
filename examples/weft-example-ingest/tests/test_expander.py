"""This pack's own tests for `ExampleFirstSentenceExpander`."""

from weft_example_ingest.expander import NAME, ExampleFirstSentenceExpander

from weft_index.contract import Expander
from weft_index.payload import Representation
from weft_kernel.context import Context
from weft_kernel.payload import MediaType, Node, NothingToProduce, Produced
from weft_kernel.seam import wrap


def _ctx() -> Context:
    return Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")


async def test_expander_carries_the_input_and_adds_a_gist_through_the_seam() -> None:
    # Arrange
    expander = ExampleFirstSentenceExpander()
    wrapped = wrap(
        expander.run,
        distribution="weft-example-ingest",
        contract="Expander",
        plugin=NAME,
    )
    node = Node.synthetic(
        content="First sentence here. Second sentence follows.",
        media_type=MediaType.TEXT,
        reason="fixture",
    )

    # Act
    outcome = await wrapped([node], _ctx())

    # Assert — the original continues unchanged, and one gist is added beside it.
    assert isinstance(outcome, Produced)
    assert node in outcome.value
    gists = [n for n in outcome.value if n.id != node.id]
    assert len(gists) == 1
    assert gists[0].content == "First sentence here."
    representation = gists[0].ext_as(Representation)
    assert representation is not None
    assert representation.technique == NAME
    assert node.id in gists[0].lineage.parents


async def test_expander_leaves_a_single_sentence_node_ungisted() -> None:
    # Arrange
    expander = ExampleFirstSentenceExpander()
    node = Node.synthetic(content="Only one sentence", media_type=MediaType.TEXT, reason="fixture")

    # Act
    outcome = await expander.run([node], _ctx())

    # Assert — every node handed in still continues; nothing extra was gistable.
    assert isinstance(outcome, Produced)
    assert list(outcome.value) == [node]


async def test_expander_on_no_nodes_produces_nothing() -> None:
    # Arrange
    expander = ExampleFirstSentenceExpander()

    # Act
    outcome = await expander.run([], _ctx())

    # Assert
    assert isinstance(outcome, NothingToProduce)


async def test_expander_satisfies_the_expander_contract_structurally() -> None:
    # Act / Assert
    assert isinstance(ExampleFirstSentenceExpander(), Expander)
