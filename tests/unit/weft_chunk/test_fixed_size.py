"""Unit tests for `weft_chunk.fixed_size`.

Mirrors `packages/weft-rag/src/weft_chunk/fixed_size.py`. Covers the happy
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
from weft_chunk.payload import ChunkOffset
from weft_chunk.property import WordBoundaries
from weft_kernel import resolution
from weft_kernel.context import Context
from weft_kernel.payload import (
    ExtModel,
    MediaType,
    Node,
    NothingToProduce,
    Outcome,
    Produced,
    SyntheticOrigin,
)
from weft_kernel.pipeline import Pipeline, StageDeclaration
from weft_kernel.registry import Registry


class _DocumentFact(ExtModel):
    """A stand-in for a document-structure fact a real extractor pack attaches to a root
    node — `weft_pdf.PdfPages`, in production. Declared locally rather than imported from
    `weft-pdf` so this test proves the *generic* carry-forward mechanism, not a special
    case for one pack `weft-chunk` does not and must not depend on."""

    __namespace__ = "test-document-fact"
    __schema_version__ = "1.0.0"

    value: str


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


async def test_each_chunk_carries_its_own_character_offset_into_the_parent() -> None:
    # Arrange — ledger 2.9's first half of the page-attribution gap: a chunk records
    # `ordinal` (which window this is) but nothing said *where* in the parent's content
    # the window starts, and a page number cannot be looked up without one.
    chunker = FixedSizeChunker(config=FixedSizeChunkerConfig(size=4, overlap=1))
    parent = _node("abcdefgh")

    # Act
    outcome = await chunker.run([parent], _ctx())

    # Assert — step = size - overlap = 3, so the three windows start at 0, 3, 6.
    assert isinstance(outcome, Produced)
    assert [chunk.ext_as(ChunkOffset) for chunk in outcome.value] == [
        ChunkOffset(start=0),
        ChunkOffset(start=3),
        ChunkOffset(start=6),
    ]


async def test_a_chunk_carries_forward_its_parents_document_level_facts() -> None:
    # Arrange — ledger 2.9's second half: `Node.derive` drops `ext` by design, so a fact
    # a pack attached to the whole document (page boundaries, headings) must be
    # explicitly carried forward by the chunker or it dies at the first `derive` call.
    chunker = FixedSizeChunker(config=FixedSizeChunkerConfig(size=4, overlap=1))
    parent = _node("abcdefgh").with_ext(_DocumentFact(value="attached to the root"))

    # Act
    outcome = await chunker.run([parent], _ctx())

    # Assert — every chunk carries the same document-level fact its parent did.
    assert isinstance(outcome, Produced)
    assert all(
        chunk.ext_as(_DocumentFact) == _DocumentFact(value="attached to the root")
        for chunk in outcome.value
    )


async def test_a_chunk_does_not_carry_forward_its_parents_synthetic_origin() -> None:
    # Arrange — `SyntheticOrigin` states that *this* node has no real lineage. A chunk
    # always has real lineage (its parent), so copying this namespace forward would
    # attach a claim to the chunk that is false the moment it is read.
    chunker = FixedSizeChunker(config=FixedSizeChunkerConfig(size=4, overlap=1))
    parent = _node("abcdefgh")
    assert parent.ext_as(SyntheticOrigin) is not None  # the fixture actually carries one

    # Act
    outcome = await chunker.run([parent], _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    assert all(chunk.ext_as(SyntheticOrigin) is None for chunk in outcome.value)


async def test_a_second_chunking_pass_compounds_the_offset_instead_of_overwriting_it() -> None:
    # Arrange — repair for a defect three reviewers of the first cut traced independently:
    # a coarse pass (size=10, overlap=0) then a fine pass (size=4, overlap=0) over the coarse
    # pass's second window is an ordinary two-level chunking technique, and `Chunker`'s
    # `Stage[Sequence[Node], Sequence[Node]]` shape lets a pipeline compose it. The fine pass's
    # `ChunkOffset.start` must stay relative to the root `parent`, because that is what
    # `weft_pdf.PdfPages.starts` — carried forward onto every level — is indexed against.
    chunker = FixedSizeChunker(config=FixedSizeChunkerConfig(size=10, overlap=0))
    parent = _node("0123456789ABCDEFGHIJ")  # 20 chars: two coarse windows, start=0 and start=10

    # Act — coarse pass, then re-chunk the second coarse window with a finer window.
    coarse = await chunker.run([parent], _ctx())
    assert isinstance(coarse, Produced)
    second_coarse_window = coarse.value[1]
    assert second_coarse_window.ext_as(ChunkOffset) == ChunkOffset(start=10)

    fine_chunker = FixedSizeChunker(config=FixedSizeChunkerConfig(size=4, overlap=0))
    fine = await fine_chunker.run([second_coarse_window], _ctx())

    # Assert — local fine-pass offsets (0, 4, 8) added to the coarse window's own start (10),
    # never a bare local offset that would be indexed against the wrong document.
    assert isinstance(fine, Produced)
    assert [chunk.ext_as(ChunkOffset) for chunk in fine.value] == [
        ChunkOffset(start=10),
        ChunkOffset(start=14),
        ChunkOffset(start=18),
    ]


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
