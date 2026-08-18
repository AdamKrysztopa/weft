"""This pack's own tests for `ExampleWordCountEnhancer`."""

from weft_example_ingest.enhancer import ExampleWordCountEnhancer, WordCount

from weft_enhance.contract import Enhancer
from weft_kernel.context import Context
from weft_kernel.payload import MediaType, Node, NothingToProduce, Produced
from weft_kernel.seam import wrap


def _ctx() -> Context:
    return Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")


async def test_enhancer_attaches_a_word_count_without_touching_content_through_the_seam() -> None:
    # Arrange
    enhancer = ExampleWordCountEnhancer()
    wrapped = wrap(
        enhancer.run,
        distribution="weft-example-ingest",
        contract="Enhancer",
        plugin="example-enhancer",
    )
    node = Node.synthetic(content="alpha beta gamma", media_type=MediaType.TEXT, reason="fixture")

    # Act
    outcome = await wrapped([node], _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    enhanced = outcome.value[0]
    assert enhanced.id == node.id  # identity unaffected — content never rewritten
    word_count = enhanced.ext_as(WordCount)
    assert word_count is not None
    assert word_count.count == 3


async def test_enhancer_on_no_nodes_produces_nothing() -> None:
    # Arrange
    enhancer = ExampleWordCountEnhancer()

    # Act
    outcome = await enhancer.run([], _ctx())

    # Assert
    assert isinstance(outcome, NothingToProduce)


async def test_enhancer_satisfies_the_enhancer_contract_structurally() -> None:
    # Act / Assert
    assert isinstance(ExampleWordCountEnhancer(), Enhancer)
