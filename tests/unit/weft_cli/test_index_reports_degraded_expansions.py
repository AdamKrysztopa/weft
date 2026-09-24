"""`weft index` counts the chunks an `Expander` could not expand — carried repair **R38.13**.

`hypothetical-questions` degrades rather than failing a run: a refusal or a rate-limit storm leaves
a chunk with no questions. Before this repair nothing counted how many, so a questions arm could
shrink while its record read as a full measurement, and `38.6` had to count question nodes per
chunk in the database by hand before its table could be committed.

The chunk now carries `weft_index.payload.ExpansionDegraded`, which lives outside the node's id and
is stored with it, so the count is the store's to answer: every stored node carrying the marker.
A store that cannot evaluate a filter is not asked, and the line stays silent rather than printing
a zero nobody measured.
"""

from collections.abc import Sequence
from typing import ClassVar

from weft_cli import render
from weft_cli.commands import IndexCommandResult
from weft_cli.ingest import count_degraded_expansions
from weft_index.payload import ExpansionDegraded
from weft_kernel.payload import MediaType, Node, Produced
from weft_kernel.runner import RunSummary
from weft_store.contract import STORE_CONTRACT_VERSION, Cursor, Filter, FilterOp, Page

_FIELD = f"ext.{ExpansionDegraded.__namespace__}.expander"


def _node(content: str, *, degraded: bool) -> Node:
    node = Node.synthetic(content=content, media_type=MediaType.TEXT, reason="test fixture")
    if degraded:
        node = node.with_ext(
            ExpansionDegraded(expander="hypothetical-questions", reason="the model declined")
        )
    return node


class _PagingStore:
    """Answers `matching` for the one `EXISTS` filter the count asks, one node per page, so a
    count that reads only the first page is caught.
    """

    version: ClassVar[str] = STORE_CONTRACT_VERSION

    def __init__(self, nodes: Sequence[Node]) -> None:
        self._nodes = tuple(nodes)
        self.asked: list[Filter] = []

    async def matching(self, filter: Filter, cursor: Cursor | None = None) -> Page[Node]:
        self.asked.append(filter)
        assert filter.op is FilterOp.EXISTS
        assert filter.field == _FIELD
        hits = [node for node in self._nodes if node.ext_as(ExpansionDegraded) is not None]
        start = int(cursor) if cursor is not None else 0
        following = start + 1
        return Page(
            items=tuple(hits[start:following]),
            next_cursor=Cursor(str(following)) if following < len(hits) else None,
        )


async def test_every_stored_chunk_carrying_the_marker_is_counted_across_pages() -> None:
    # Arrange
    store = _PagingStore(
        [
            _node("one", degraded=True),
            _node("two", degraded=False),
            _node("three", degraded=True),
            _node("four", degraded=True),
        ]
    )

    # Act
    counted = await count_degraded_expansions(store)

    # Assert
    assert counted == 3
    assert store.asked


async def test_a_store_holding_no_degraded_chunk_counts_zero() -> None:
    # Arrange
    store = _PagingStore([_node("one", degraded=False)])

    # Act / Assert
    assert await count_degraded_expansions(store) == 0


def _result(degraded: int | None) -> IndexCommandResult:
    return IndexCommandResult(
        summary=RunSummary(produced=1),
        stored_count=4,
        documents_discovered=1,
        documents_indexed=1,
        degraded_expansions=degraded,
    )


def test_the_count_is_printed_with_its_label() -> None:
    # Act
    rendered = render.render_outcome(Produced(value=_result(3)))

    # Assert
    assert "chunks stored without their expansion: 3." in (rendered.stdout or "")


def test_a_counted_zero_is_printed_because_it_was_measured() -> None:
    # Act
    rendered = render.render_outcome(Produced(value=_result(0)))

    # Assert
    assert "chunks stored without their expansion: 0." in (rendered.stdout or "")


def test_a_run_that_did_not_count_says_nothing() -> None:
    # Act
    rendered = render.render_outcome(Produced(value=_result(None)))

    # Assert
    assert rendered.stdout == "1 documents: 1 indexed, 0 unchanged. nodes now stored: 4."
