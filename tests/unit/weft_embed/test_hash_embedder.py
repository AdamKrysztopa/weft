"""Unit tests for `weft_embed.hash_embedder`.

Mirrors `packages/weft-rag/src/weft_embed/hash_embedder.py`. Covers the
happy path (a batch of nodes each gets a deterministic, fixed-dimension
vector), the edge case of an empty batch (`NothingToProduce`, never an empty
`Produced([])`), and the error case of a non-positive configured dimension.
"""

from collections.abc import Sequence

import pytest
from pydantic import ValidationError

from weft_embed.hash_embedder import HashEmbedder, HashEmbedderConfig
from weft_kernel.context import Context
from weft_kernel.payload import MediaType, Node, NothingToProduce, Outcome, Produced


def _ctx() -> Context:
    return Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")


def _node(content: str) -> Node:
    return Node.synthetic(content=content, media_type=MediaType.TEXT, reason="test fixture")


async def test_run_attaches_a_deterministic_fixed_dimension_vector_to_every_node() -> None:
    # Arrange
    embedder = HashEmbedder(config=HashEmbedderConfig(dimension=8))
    first = _node("hello world")
    second = _node("goodbye world")

    # Act
    outcome: Outcome[Sequence[Node]] = await embedder.run([first, second], _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    embedded = outcome.value
    assert [node.embedding for node in embedded if node.embedding is not None]
    for node in embedded:
        assert node.embedding is not None
        assert node.embedding.dimension == 8
    # Same content, same vector — required for re-index idempotency to hold through storage.
    again = await embedder.run([_node("hello world")], _ctx())
    assert isinstance(again, Produced)
    assert again.value[0].embedding == embedded[0].embedding
    # Different content, different vector.
    assert embedded[0].embedding != embedded[1].embedding


async def test_run_answers_nothing_to_produce_for_an_empty_batch() -> None:
    # Arrange
    embedder = HashEmbedder()

    # Act
    outcome = await embedder.run([], _ctx())

    # Assert
    assert outcome == NothingToProduce(reason="no nodes to embed")


def test_config_refuses_a_non_positive_dimension() -> None:
    # Act / Assert
    with pytest.raises(ValidationError):
        HashEmbedderConfig(dimension=0)
