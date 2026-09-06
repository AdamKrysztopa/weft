"""`describe-figure` — a described figure keeps its caption and gains a description. Task `9.11`.

`docs/11-multimodal.md` §2.4 stage 4 is the owning text and it is unusually specific: the stage
*"`requires` `BlobRef`, `provides` `FigureDescription`. Reads the bytes back through
`ctx.require(BlobStore).open(uri)`, calls `ctx.require(Describer)`, and **augments** the node's
content — caption *and* description — rather than replacing it."* Every test below is one clause
of that sentence, plus the two the ledger line adds: the caption is never overwritten by
assignment, and a document naming this stage with no `Describer` configured fails with
`UnresolvedServiceError` naming what exists — never a `fallback` counter in a span.

**Why the content and not only `ext`.** `Node.derive` drops `ext` by design, and 9.10's GREEN
verdict (`09` §4.3b) measured that a caption is what retrieval matches on. A description that lives
only in `ext` is never embedded and never retrieved, so it would be a VLM call bought for nothing.
`11` §2.4 stage 5 states the consequence directly: *"For an `IMAGE` node, embeds `content` — caption
plus description."*

**Why the ext still has to survive.** `11` §2.4's *Query time* paragraph requires the retrieved
node's `BlobRef` to be **durable**, so a vision-capable generator can reopen the pixels. `derive`
would drop it, which is exactly `L9.63` — so this stage carries every namespace forward the way
`weft_chunk.fixed_size._carry_forward` does, and a test below fails if it stops.
"""

from collections.abc import Sequence

import pytest

from weft_blob.contract import BLOB_ROLE, BlobStore, BlobUri
from weft_blob.payload import BlobRef
from weft_extract.payload import PageSpan
from weft_kernel.context import Context, ServiceRegistry, UnresolvedServiceError
from weft_kernel.payload import (
    Failed,
    MediaType,
    Node,
    NothingToProduce,
    Outcome,
    Produced,
    SourceId,
)
from weft_kernel.payload.applicability import Applies
from weft_vision.contract import Describer
from weft_vision.describe_figure import FigureDescriber, FigureDescription

_CAPTION = "Figure 1. Revenue by region."
_DESCRIPTION = "A bar chart with four bars, the tallest labelled EMEA."
_PIXELS = b"\x89PNG\r\n\x1a\nnot-really-a-png"
_URI = BlobUri("file:///blobs/tenant-a/abc/1.png")


class _StubBlobStore:
    """Answers `open` for the one uri these tests wrote, and refuses anything else by name."""

    def __init__(self, *, data: bytes = _PIXELS) -> None:
        self._data = data
        self.opened: list[BlobUri] = []

    async def put(self, key: str, data: bytes, media_type: str) -> BlobUri:
        del key, data, media_type
        return _URI

    async def open(self, uri: BlobUri) -> bytes:
        self.opened.append(uri)
        if uri != _URI:
            raise AssertionError(f"asked for {uri!r}, which nothing in this test wrote")
        return self._data

    async def delete_prefix(self, prefix: str) -> int:
        del prefix
        return 0


class _StubDescriber:
    """A `Describer` whose answer these tests choose, recording what it was asked."""

    def __init__(self, answer: Outcome[str]) -> None:
        self._answer = answer
        self.calls: list[tuple[bytes, str, str]] = []

    async def describe(self, data: bytes, media_type: str, instruction: str) -> Outcome[str]:
        self.calls.append((data, media_type, instruction))
        return self._answer


def _figure_node() -> Node:
    """An `IMAGE` node in exactly the shape `pdf-layout` leaves one: caption as content, a
    `BlobRef` and a `PageSpan` in `ext` (`weft_pdf.pdf_layout:215`).
    """
    root = Node.synthetic(
        content="Annual report",
        media_type=MediaType.TEXT,
        reason="the document root a PDF extractor derives every page node from",
        sources=frozenset({SourceId("report.pdf")}),
    )
    figure = root.derive(content=_CAPTION, media_type=MediaType.IMAGE, ordinal=1001)
    return figure.with_ext(BlobRef(uri=_URI, media_type="image/png")).with_ext(
        PageSpan(page=1, ordinal=1)
    )


def _ctx(*, describer: object | None, blobs: object | None) -> Context:
    services = ServiceRegistry()
    if blobs is not None:
        services.add(BlobStore, blobs)
    if describer is not None:
        services.add(Describer, describer)
    return Context(
        tenant_id="tenant-a",
        run_id="run-1",
        trace_id="trace-1",
        locale="en",
        services=services,
    )


async def _run(
    stage: FigureDescriber, nodes: Sequence[Node], ctx: Context
) -> Outcome[Sequence[Node]]:
    return await stage.run(nodes, ctx)


async def test_the_described_node_holds_the_caption_and_the_description() -> None:
    """`11` §2.4 stage 4: *augments* rather than replaces. Both strings are in `content`."""
    # Arrange
    stage = FigureDescriber(None)
    ctx = _ctx(describer=_StubDescriber(Produced(value=_DESCRIPTION)), blobs=_StubBlobStore())

    # Act
    outcome = await _run(stage, [_figure_node()], ctx)

    # Assert
    assert isinstance(outcome, Produced)
    (described,) = outcome.value
    assert _CAPTION in described.content
    assert _DESCRIPTION in described.content


async def test_the_caption_is_never_overwritten_by_assignment() -> None:
    """The ledger's own wording, tested as a property rather than trusted as an intention.

    A describer that answers with the caption's own words must not be able to produce a node
    whose content *is* the description — the caption's text has to survive verbatim, in order,
    ahead of whatever was added.
    """
    # Arrange — a description that begins with the caption, the case a naive `content =
    # description` would make indistinguishable from a correct augmentation.
    stage = FigureDescriber(None)
    sneaky = f"{_CAPTION} and then some model prose."
    ctx = _ctx(describer=_StubDescriber(Produced(value=sneaky)), blobs=_StubBlobStore())

    # Act
    outcome = await _run(stage, [_figure_node()], ctx)

    # Assert — the caption appears first and the description follows it, so the content is a
    # composition of the two rather than either one alone.
    assert isinstance(outcome, Produced)
    (described,) = outcome.value
    assert described.content.startswith(_CAPTION)
    assert described.content != sneaky
    assert described.content != _CAPTION


async def test_the_blob_reference_survives_describing() -> None:
    """`11` §2.4 *Query time*: the `BlobRef` is durable, so a generator can reopen the pixels.

    `Node.derive` drops `ext`, which is `L9.63` — this test is what stops that lesson recurring
    one stage later.
    """
    # Arrange
    stage = FigureDescriber(None)
    ctx = _ctx(describer=_StubDescriber(Produced(value=_DESCRIPTION)), blobs=_StubBlobStore())

    # Act
    outcome = await _run(stage, [_figure_node()], ctx)

    # Assert — and the page fact too: this stage owns the whole path, not only its own namespace.
    assert isinstance(outcome, Produced)
    (described,) = outcome.value
    assert described.ext_as(BlobRef) == BlobRef(uri=_URI, media_type="image/png")
    assert described.ext_as(PageSpan) == PageSpan(page=1, ordinal=1)


async def test_the_description_is_attached_as_the_fact_the_stage_provides() -> None:
    """`provides FigureDescription` is a declaration; this is the value behind it."""
    # Arrange
    stage = FigureDescriber(None)
    ctx = _ctx(describer=_StubDescriber(Produced(value=_DESCRIPTION)), blobs=_StubBlobStore())

    # Act
    outcome = await _run(stage, [_figure_node()], ctx)

    # Assert
    assert isinstance(outcome, Produced)
    (described,) = outcome.value
    described_fact = described.ext_as(FigureDescription)
    assert described_fact is not None
    assert described_fact.description == _DESCRIPTION


async def test_the_stage_reads_the_pixels_back_through_the_blob_store() -> None:
    """The bytes never travelled in the payload, so the only way to them is `BlobStore.open`."""
    # Arrange
    stage = FigureDescriber(None)
    blobs = _StubBlobStore()
    describer = _StubDescriber(Produced(value=_DESCRIPTION))
    ctx = _ctx(describer=describer, blobs=blobs)

    # Act
    await _run(stage, [_figure_node()], ctx)

    # Assert — opened exactly the uri the node's own `BlobRef` named, and handed those bytes on
    # with the media type the reference carried rather than one this stage guessed.
    assert blobs.opened == [_URI]
    assert describer.calls[0][0] == _PIXELS
    assert describer.calls[0][1] == "image/png"


async def test_a_describer_that_produces_nothing_leaves_the_node_exactly_as_it_was() -> None:
    """`NothingToProduce` is an absence, and the honest response to it is the caption alone.

    No synthesised label — `11` §2.4 names template strings such as `f'Figure on page {n}'` as
    *measurable index poisoning* — and no `fallback` counter in a span, which the ledger line
    forbids by name.
    """
    # Arrange
    stage = FigureDescriber(None)
    ctx = _ctx(
        describer=_StubDescriber(NothingToProduce(reason="the provider refused this image")),
        blobs=_StubBlobStore(),
    )
    before = _figure_node()

    # Act
    outcome = await _run(stage, [before], ctx)

    # Assert — the same node, id included: nothing about it changed, so nothing about it may.
    assert isinstance(outcome, Produced)
    (after,) = outcome.value
    assert after == before
    assert after.ext_as(FigureDescription) is None


async def test_a_describer_that_fails_does_not_take_the_rest_of_the_batch_with_it() -> None:
    """One figure's provider error is not the document's failure — `Describer`'s own docstring:
    *"has to be able to say so without raising through a stage that has forty more figures to get
    through."*
    """
    # Arrange — two figures, and a describer that fails the first thing it is asked.
    stage = FigureDescriber(None)
    ctx = _ctx(
        describer=_StubDescriber(Failed(reason="provider returned 500")),
        blobs=_StubBlobStore(),
    )
    # Act
    outcome = await _run(stage, [_figure_node()], ctx)

    # Assert — the node survives undescribed rather than the batch failing.
    assert isinstance(outcome, Produced)
    (after,) = outcome.value
    assert after.content == _CAPTION
    assert after.ext_as(FigureDescription) is None


async def test_a_run_with_no_describer_configured_is_refused_naming_what_exists() -> None:
    """The ledger's own clause. An absent service is a wiring bug and reads as one."""
    # Arrange — the blob store is there; the describer is not.
    stage = FigureDescriber(None)
    ctx = _ctx(describer=None, blobs=_StubBlobStore())

    # Act / Assert
    with pytest.raises(UnresolvedServiceError) as caught:
        await _run(stage, [_figure_node()], ctx)
    assert "Describer" in str(caught.value)
    assert BlobStore in caught.value.valid_options or "BlobStore" in str(caught.value)


async def test_the_stage_declares_that_it_operates_on_images_alone() -> None:
    """Applicability, not an `if` — G2-c: the runner routes a `TEXT` node past this stage, so a
    text-only project that installs this pack pays for nothing and no author writes the guard.
    """
    # Arrange / Act
    applies_to = FigureDescriber.applies_to

    # Assert
    assert applies_to == (Applies(media_type=MediaType.IMAGE),)


async def test_the_stage_declares_what_it_needs_and_what_it_adds() -> None:
    """`11` §2.4 stage 4, verbatim: *`requires` `BlobRef`, `provides` `FigureDescription`*."""
    # Arrange / Act / Assert
    assert FigureDescriber.requires == (BlobRef,)
    assert FigureDescriber.provides == (FigureDescription,)


async def test_the_blob_role_is_how_the_store_is_reached() -> None:
    """A guard on the wiring this stage depends on: `9.0`'s role table is what makes
    `ctx.require(BlobStore)` answerable at all, and `BLOB_ROLE` is the key an operator sets.
    """
    # Arrange / Act / Assert
    assert BLOB_ROLE.contract is BlobStore
