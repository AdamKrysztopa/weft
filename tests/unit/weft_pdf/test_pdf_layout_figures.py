"""`pdf-layout` recovers a figure as its own node, pixels outside the payload — ledger `9.7`.

`MediaType.IMAGE`'s first producer, and the first stage anywhere to reach a run-wide service that
`weft-cli` does not name: it writes pixels through `ctx.require(BlobStore)` — task `9.0`'s seam,
`9.4`'s contract — and puts a non-transient `BlobRef` in the node's `ext`. The bytes never enter the
payload, which is what makes `11` §1.4's first scar unrepresentable rather than merely avoided: *the
blob rode on every node through several ingest stages... N configured retrieval strategies meant N
copies of the base64 string and N vision-LLM calls on the same image.*

**A captionless figure is `NothingToProduce` for that node, never a template string.** `11` §2.4 and
G5-b at `11:667` settle this: `content` feeds the identity digest, so base64 writes megabytes into
the store, a path binds ids to a directory, and a synthesised `f"Figure on page {n}"` is measurable
index poisoning — identical strings collide as a block at retrieval time. The answer is caption →
OCR text → nothing, and "nothing" means the node is not made.

**The ordinal is stable, and that is a stated obligation rather than an implementation detail.**
G5-b again: *"`ordinal` saves the id from colliding across siblings only if the extractor assigns
distinct ordinals, which becomes a stated obligation on any image extractor."* A running counter
over a document is the shape `11` §1.4 records a third party paying for — *"a cache hit that rebinds
a figure to a blob by positional index"* — so a re-extraction that finds one figure fewer must not
shift every later figure onto another figure's blob. The ordinal here is derived from where the
figure *is*, not from how many came before it.
"""

from collections.abc import Sequence

from tests.unit.weft_pdf.minimal_pdf import (
    figure_beside_a_zero_width_image,
    figure_with_caption,
    text_pages,
)
from weft_blob.contract import BlobStore
from weft_blob.filesystem_store import FilesystemBlobSettings, FilesystemBlobStore
from weft_blob.payload import BlobRef
from weft_extract.contract import SourceDoc
from weft_extract.payload import PageSpan
from weft_kernel.context import Context, ServiceRegistry
from weft_kernel.payload import MediaType, Node, Produced, SourceId
from weft_pdf.pdf_layout import PdfLayoutExtractor

_CAPTION = "Figure 1. Revenue by region."


def _ctx(root: object) -> Context:
    """A passport carrying a real `FilesystemBlobStore`, the way the ingest path assembles one."""
    from pathlib import Path

    services = ServiceRegistry()
    services.add(BlobStore, FilesystemBlobStore(FilesystemBlobSettings(root=Path(str(root)))))
    return Context(
        tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en", services=services
    )


def _doc(content: bytes) -> SourceDoc:
    return SourceDoc(source_id=SourceId("s-1"), uri="file:///report.pdf", content=content)


async def _nodes(content: bytes, root: object) -> Sequence[Node]:
    outcome = await PdfLayoutExtractor().run([_doc(content)], _ctx(root))
    assert isinstance(outcome, Produced), outcome
    return outcome.value


def _figures(nodes: Sequence[Node]) -> list[Node]:
    return [node for node in nodes if node.media_type is MediaType.IMAGE]


async def test_a_figure_arrives_as_its_own_node_whose_media_type_says_so(tmp_path: object) -> None:
    """`MediaType.IMAGE`'s first producer in the tree."""
    # Act
    nodes = await _nodes(figure_with_caption(_CAPTION), tmp_path)

    # Assert
    assert len(_figures(nodes)) == 1


async def test_the_figures_content_is_the_caption_the_document_supplied(tmp_path: object) -> None:
    """Source-derived, stable, and it never fabricates — G5-b's own three words."""
    # Act
    figure = _figures(await _nodes(figure_with_caption(_CAPTION), tmp_path))[0]

    # Assert
    assert figure.content == _CAPTION


async def test_a_figure_with_no_caption_produces_no_node_at_all(tmp_path: object) -> None:
    """The clause `11` §2.4 states outright: not a template string, not an empty string, nothing.

    An empty `content` would still be a node — with an id every other captionless figure in the
    corpus shares, since the digest is over content, media type, parents and ordinal.
    """
    # Act
    nodes = await _nodes(figure_with_caption(None), tmp_path)

    # Assert
    assert _figures(nodes) == []


async def test_the_pixels_are_in_the_blob_store_and_not_in_the_node(tmp_path: object) -> None:
    """The property the whole design turns on: bytes leave, a reference stays.

    Asserted by reading the bytes back through the contract rather than by looking at the disk —
    what matters is that a later stage can resolve the reference, which is what `9.11`'s describer
    will do.
    """
    # Arrange
    figure = _figures(await _nodes(figure_with_caption(_CAPTION), tmp_path))[0]
    ref = figure.ext_as(BlobRef)

    # Act / Assert
    assert ref is not None
    from pathlib import Path

    store = FilesystemBlobStore(FilesystemBlobSettings(root=Path(str(tmp_path))))
    assert await store.open(ref.uri)
    assert _CAPTION in figure.content
    assert "base64" not in figure.content


async def test_the_figure_node_carries_where_it_came_from(tmp_path: object) -> None:
    """`PageSpan` — `11` §2.4's table gives a figure node a page and a reading-order position."""
    # Act
    figure = _figures(await _nodes(figure_with_caption(_CAPTION), tmp_path))[0]

    # Assert
    span = figure.ext_as(PageSpan)
    assert span is not None
    assert span.page == 1


async def test_the_figure_node_is_a_child_of_the_document_root(tmp_path: object) -> None:
    """So `weft delete` of the source reaps it, and the blob with it through the prefix."""
    # Act
    nodes = await _nodes(figure_with_caption(_CAPTION), tmp_path)
    root = next(node for node in nodes if node.media_type is MediaType.TEXT)

    # Assert
    assert _figures(nodes)[0].lineage.parents == (root.id,)


async def test_the_blob_key_lies_under_this_sources_own_prefix(tmp_path: object) -> None:
    """Cascade delete is one prefix and no ledger — `9.4`'s derived-key design, used."""
    # Arrange
    from weft_blob.keys import source_prefix

    figure = _figures(await _nodes(figure_with_caption(_CAPTION), tmp_path))[0]
    ref = figure.ext_as(BlobRef)

    # Act / Assert
    assert ref is not None
    assert source_prefix(tenant_id="tenant-a", source_id=SourceId("s-1")) in str(ref.uri)


async def test_re_extracting_an_unchanged_file_writes_the_same_blob_key(tmp_path: object) -> None:
    """Stability across re-extraction, which is what `9.7` asks for in as many words."""
    # Act
    first = _figures(await _nodes(figure_with_caption(_CAPTION), tmp_path))[0].ext_as(BlobRef)
    second = _figures(await _nodes(figure_with_caption(_CAPTION), tmp_path))[0].ext_as(BlobRef)

    # Assert
    assert first is not None
    assert second is not None
    assert first.uri == second.uri


async def test_a_figure_that_loses_a_predecessor_keeps_its_own_key(tmp_path: object) -> None:
    """The positional-index defect `11` §1.4 travels with, made unrepresentable.

    Two figures on two pages; re-extract with the first page's figure gone. A running counter over
    the document would move the survivor from ordinal 1 to ordinal 0 and rebind it to the blob the
    *other* figure wrote. Derived from where the figure sits, it does not move.
    """
    # Arrange
    from tests.unit.weft_pdf.minimal_pdf import figures_on_two_pages

    both = _figures(await _nodes(figures_on_two_pages(_CAPTION, "Figure 2. Costs."), tmp_path))
    survivor_before = next(node for node in both if node.content == "Figure 2. Costs.")

    # Act — the same document with the first page's figure removed.
    after = _figures(await _nodes(figures_on_two_pages(None, "Figure 2. Costs."), tmp_path))
    survivor_after = next(node for node in after if node.content == "Figure 2. Costs.")

    # Assert
    before_ref, after_ref = survivor_before.ext_as(BlobRef), survivor_after.ext_as(BlobRef)
    assert before_ref is not None
    assert after_ref is not None
    assert before_ref.uri == after_ref.uri


async def test_a_pdf_with_no_figure_produces_no_figure_node(tmp_path: object) -> None:
    """The contrast that makes every assertion above a property of the figure path."""
    # Act / Assert
    assert _figures(await _nodes(text_pages("prose and nothing else"), tmp_path)) == []


async def test_an_extractor_with_no_blob_store_configured_refuses_by_name(
    tmp_path: object,
) -> None:
    """`ctx.require` raises `UnresolvedServiceError` naming what it wanted and what is available.

    Never a figure node with no pixels behind it, and never a silently skipped figure: a run whose
    pipeline extracts figures and whose project configured no `[services] blob` is misconfigured,
    and the loud failure is the whole point of the seam `9.0` built.
    """
    # Arrange
    del tmp_path
    from weft_kernel.context import UnresolvedServiceError

    bare = Context(tenant_id="tenant-a", run_id="r", trace_id="t", locale="en")

    # Act / Assert
    import pytest

    with pytest.raises(UnresolvedServiceError):
        await PdfLayoutExtractor().run([_doc(figure_with_caption(_CAPTION))], bare)


async def test_an_image_with_no_area_is_skipped_and_the_real_figure_still_arrives(
    tmp_path: object,
) -> None:
    """Carried repair `R11.1`, and it is a defect found by running the binary, not by these tests.

    `weft index corpus --pipeline index-pdf` exited **1** on a real paper from this project's own
    `corpus/mrmr/` with a single line — `'extract' failed: cannot write empty image` — naming
    neither the document nor the page, and it did the same on `index-pdf-undescribed` and
    `index-pdf-rows`. The cause, measured: `pdfplumber` reports 67 image boxes of zero rounded
    width across that paper's 21 pages, and cropping a zero-area box gives PIL an empty image that
    `save` refuses.

    **The policy this restores is already settled one path over**, in `weft_pdf.document.
    ExtractedTable`'s own docstring: a backend's unusable reading "must skip the one table rather
    than fail the document." A box with no area holds no pixels, so nothing is lost by skipping it
    — which is why this is silent, exactly as `_table_node`'s refusal is, rather than reported.

    One document, two images: the assertion is that the good one survives, because a document
    holding only the bad image could not tell "skipped it" from "found no figures at all."
    """
    # Act
    nodes = await _nodes(figure_beside_a_zero_width_image(_CAPTION), tmp_path)

    # Assert
    figures = _figures(nodes)
    assert len(figures) == 1
    assert figures[0].content == _CAPTION
