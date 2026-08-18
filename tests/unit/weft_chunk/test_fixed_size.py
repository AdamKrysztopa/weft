"""Unit tests for `weft_chunk.fixed_size`.

Mirrors `packages/weft-chunk/src/weft_chunk/fixed_size.py`. Covers the happy
path (overlapping fixed-size windows, each carrying lineage back to its
parent), the edge case of a node with empty content contributing no chunks
while a batch that produces none at all answers `NothingToProduce`, and the
error case of a configured overlap that is not smaller than the window size.
"""

from collections.abc import Sequence

import pytest
from pydantic import ValidationError

from weft_chunk.fixed_size import FixedSizeChunker, FixedSizeChunkerConfig
from weft_kernel.context import Context
from weft_kernel.payload import MediaType, Node, NothingToProduce, Outcome, Produced


def _ctx() -> Context:
    return Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")


def _node(content: str) -> Node:
    return Node.synthetic(content=content, media_type=MediaType.TEXT, reason="test fixture")


async def test_run_splits_content_into_overlapping_windows_carrying_lineage() -> None:
    # Arrange
    chunker = FixedSizeChunker(config=FixedSizeChunkerConfig(size=4, overlap=1))
    parent = _node("abcdefgh")

    # Act
    outcome: Outcome[Sequence[Node]] = await chunker.run([parent], _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    pieces = [chunk.content for chunk in outcome.value]
    assert pieces == ["abcd", "defg", "gh"]
    assert all(chunk.lineage.parents == (parent.id,) for chunk in outcome.value)
    assert all(chunk.lineage.sources == parent.lineage.sources for chunk in outcome.value)


async def test_run_answers_nothing_to_produce_when_every_node_is_empty() -> None:
    # Arrange
    chunker = FixedSizeChunker()
    empty = _node("")

    # Act
    outcome = await chunker.run([empty], _ctx())

    # Assert
    assert outcome == NothingToProduce(reason="no chunk had any content to carry")


def test_config_refuses_an_overlap_not_smaller_than_size() -> None:
    # Act / Assert
    with pytest.raises(ValidationError):
        FixedSizeChunkerConfig(size=10, overlap=10)
