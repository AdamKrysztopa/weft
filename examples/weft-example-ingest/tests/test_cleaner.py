"""This pack's own tests for `ExampleBlankLineCollapser`."""

from weft_example_ingest.cleaner import ExampleBlankLineCollapser

from weft_clean.contract import Cleaner
from weft_kernel.context import Context
from weft_kernel.payload import MediaType, Node, NothingToProduce, Produced
from weft_kernel.seam import wrap


def _ctx() -> Context:
    return Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")


async def test_cleaner_collapses_long_blank_runs_through_the_seam() -> None:
    # Arrange
    cleaner = ExampleBlankLineCollapser()
    wrapped = wrap(
        cleaner.run,
        distribution="weft-example-ingest",
        contract="Cleaner",
        plugin="example-cleaner",
    )
    node = Node.synthetic(
        content="alpha\n\n\n\nbeta", media_type=MediaType.TEXT, reason="test fixture"
    )

    # Act
    outcome = await wrapped([node], _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value[0].content == "alpha\n\nbeta"
    assert node.id in outcome.value[0].lineage.parents


async def test_cleaner_on_no_nodes_produces_nothing() -> None:
    # Arrange
    cleaner = ExampleBlankLineCollapser()

    # Act
    outcome = await cleaner.run([], _ctx())

    # Assert
    assert isinstance(outcome, NothingToProduce)


async def test_cleaner_satisfies_the_cleaner_contract_and_declares_destroys_truthfully() -> None:
    # Act / Assert — `Cleaner` publishes a property vocabulary, so `destroys` must be
    # stated; collapsing blank-line runs never breaks a word or a sentence.
    assert isinstance(ExampleBlankLineCollapser(), Cleaner)
    assert ExampleBlankLineCollapser.destroys == ()
