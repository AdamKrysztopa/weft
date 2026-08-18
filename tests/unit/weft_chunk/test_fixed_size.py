"""Unit tests for `weft_chunk.fixed_size`.

Mirrors `packages/weft-chunk/src/weft_chunk/fixed_size.py`. Covers the happy
path (overlapping fixed-size windows, each carrying lineage back to its
parent), the edge case of a node with empty content contributing no chunks
while a batch that produces none at all answers `NothingToProduce`, and the
error case of a configured overlap that is not smaller than the window size.
Also covers task 1.2's own worked example: `FixedSizeChunker` declares
`destroys = (WordBoundaries,)`, truthfully — a fixed-size window can and
does split a word across a boundary.

**`test_resolving_a_pipeline_naming_fixed_size_with_size_and_overlap_actually_validates_it`
is a repair test.** A review found `FixedSizeChunker` shipping with no
`config_model`, so `weft_kernel.resolution.resolve` refused `02` §3's own
canonical `with: {size: 512, overlap: 50}` example with
`StageNotConfigurableError`, claiming falsely that the stage "cannot be
parameterised at all". The direct `FixedSizeChunkerConfig(...)` construction
the tests above use never goes through `resolve()`, so it could not have
caught this.
"""

from collections.abc import Sequence

import pytest
from pydantic import ValidationError

from weft_chunk.contract import Chunker
from weft_chunk.fixed_size import FixedSizeChunker, FixedSizeChunkerConfig
from weft_chunk.property import WordBoundaries
from weft_kernel import resolution
from weft_kernel.context import Context
from weft_kernel.payload import MediaType, Node, NothingToProduce, Outcome, Produced
from weft_kernel.pipeline import Pipeline, StageDeclaration
from weft_kernel.registry import Registry


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


def test_destroys_word_boundaries_truthfully() -> None:
    # Act / Assert — declared on the class, readable with no instance, per `02` §3.
    assert FixedSizeChunker.destroys == (WordBoundaries,)


def test_resolving_a_pipeline_naming_fixed_size_with_size_and_overlap_actually_validates_it() -> (
    None
):
    # Arrange — `02` §3's own canonical pipeline example: `with: {size: 512, overlap: 50}`.
    registry = Registry()
    registry.add(Chunker, "fixed-size", FixedSizeChunker, distribution="weft-chunk")
    pipeline = Pipeline(
        name="ingest",
        stages=(
            StageDeclaration(id="chunk", use="fixed-size", config={"size": 512, "overlap": 50}),
        ),
    )

    # Act
    resolved = resolution.resolve(pipeline, registry=registry, contracts={"chunk": Chunker})

    # Assert — the block actually reached and validated against `FixedSizeChunkerConfig`,
    # never silently dropped or refused as "not configurable".
    assert resolved.stages[0].config == FixedSizeChunkerConfig(size=512, overlap=50)
