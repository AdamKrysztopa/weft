"""This pack's own tests for `ExampleChecksumEmbedder`."""

import pytest
from pydantic import ValidationError
from weft_example_ingest.embedder import ExampleChecksumEmbedder, ExampleEmbedderConfig

from weft_embed.contract import Embedder
from weft_kernel.context import Context
from weft_kernel.payload import MediaType, Node, NothingToProduce, Produced
from weft_kernel.seam import wrap


def _ctx() -> Context:
    return Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")


async def test_embedder_attaches_a_deterministic_vector_through_the_seam() -> None:
    # Arrange
    embedder = ExampleChecksumEmbedder(ExampleEmbedderConfig(dimension=8))
    wrapped = wrap(
        embedder.run,
        distribution="weft-example-ingest",
        contract="Embedder",
        plugin="example-embedder",
    )
    node = Node.synthetic(content="alpha", media_type=MediaType.TEXT, reason="fixture")

    # Act
    first = await wrapped([node], _ctx())
    second = await embedder.run([node], _ctx())

    # Assert — deterministic: the same content hashes to the same vector every time.
    assert isinstance(first, Produced)
    assert isinstance(second, Produced)
    assert first.value[0].embedding is not None
    assert first.value[0].embedding.dimension == 8
    assert first.value[0].embedding == second.value[0].embedding


async def test_embedder_on_no_nodes_produces_nothing() -> None:
    # Arrange
    embedder = ExampleChecksumEmbedder()

    # Act
    outcome = await embedder.run([], _ctx())

    # Assert
    assert isinstance(outcome, NothingToProduce)


def test_embedder_config_refuses_a_non_positive_dimension() -> None:
    # Act / Assert
    with pytest.raises(ValidationError):
        ExampleEmbedderConfig(dimension=0)


def test_embedder_satisfies_the_embedder_contract_structurally() -> None:
    # Act / Assert
    assert isinstance(ExampleChecksumEmbedder(), Embedder)
