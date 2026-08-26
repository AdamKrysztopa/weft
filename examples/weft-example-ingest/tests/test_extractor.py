"""This pack's own tests for `ExampleExtractor` — the fourth canonical file.

**Collected by weft's own gate since its ledger task 6.23**, through the `examples-tests` step —
a suite no task runs is prose, and two tests in this tree were quietly red for exactly that
reason. Still runnable on its own with `uv run pytest` from inside this directory, which is how
a stranger runs it.
"""

from weft_example_ingest.extractor import ExampleExtractor

from weft_extract.contract import Extractor, SourceDoc
from weft_kernel.context import Context
from weft_kernel.payload import NothingToProduce, Produced, SourceId
from weft_kernel.seam import wrap


def _ctx() -> Context:
    return Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")


async def test_extractor_produces_one_node_per_document_through_the_seam() -> None:
    # Arrange — driven through `weft_kernel.seam.wrap`, the one path a registered plugin is
    # actually called through in production.
    extractor = ExampleExtractor()
    wrapped = wrap(
        extractor.run,
        distribution="weft-example-ingest",
        contract="Extractor",
        plugin="example-extractor",
    )
    doc = SourceDoc(source_id=SourceId("src-1"), uri="file:///a.txt", content=b"hello world")

    # Act
    outcome = await wrapped([doc], _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    assert [node.content for node in outcome.value] == ["hello world"]
    assert outcome.value[0].lineage.sources == frozenset({SourceId("src-1")})


async def test_extractor_on_blank_only_documents_produces_nothing() -> None:
    # Arrange
    extractor = ExampleExtractor()
    doc = SourceDoc(source_id=SourceId("src-1"), uri="file:///a.txt", content=b"   \n  ")

    # Act
    outcome = await extractor.run([doc], _ctx())

    # Assert
    assert isinstance(outcome, NothingToProduce)


async def test_extractor_satisfies_the_extractor_contract_structurally() -> None:
    # Act / Assert — no import of Extractor in extractor.py itself.
    assert isinstance(ExampleExtractor(), Extractor)
