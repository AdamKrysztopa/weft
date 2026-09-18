"""Unit tests for `weft_chunk.payload.ChunkPosition` — ledger task **32.1**.

Every chunk `fixed-size` and `table-rows` emits records where it sat in its parent, so a
`Reranker` can read its siblings back through the Filter AST (`adjacent-chunks`, `32.3`). The
position is an `ext` fact and never an input to the node's id: the ids pinned below were taken
from both chunkers before `32.1`, and a position that moved them would re-derive every stored
corpus.
"""

from weft_chunk import Settings, register
from weft_chunk.fixed_size import FixedSizeChunker, FixedSizeChunkerConfig
from weft_chunk.payload import ChunkPosition
from weft_chunk.table_rows import TableRowChunker, TableRowChunkerConfig
from weft_extract.payload import BoundingBox, TableGrid
from weft_extract.table_text import index_text
from weft_kernel.context import Context
from weft_kernel.discovery import PackRegistrar
from weft_kernel.payload import MediaType, Node, Produced
from weft_kernel.registry import Registry
from weft_store import Filter, FilterOp

#: `FixedSizeChunker(size=10, overlap=2)` over `"abcdefghij" * 3`, taken at `207b462`.
_PINNED_WINDOW_IDS = (
    "9ef0d31cedd55357c08ec4380060d32915b4904bc5b0789cb2a77c7ec9c61a62",
    "6f83e8976ac737dde859ab7b5312a3110012e12b6f81dff4b9e712a91354dce0",
    "babb3bf73a8fa7110d356ffb002aa22787ee23ab2b73892a36a715e12ad85c0b",
    "a7f875f874cacc902027c5152885bd0daa064595fa52dd757a779c3b078e71c0",
)


def _ctx() -> Context:
    return Context(tenant_id="t", run_id="r", trace_id="tr", locale="en")


async def _windows() -> list[Node]:
    parent = Node.synthetic(content="abcdefghij" * 3, media_type=MediaType.TEXT, reason="pin")
    outcome = await FixedSizeChunker(FixedSizeChunkerConfig(size=10, overlap=2)).run(
        [parent], _ctx()
    )
    assert isinstance(outcome, Produced)
    return list(outcome.value)


def _table() -> Node:
    grid = TableGrid(
        headers=("Region", "Units"),
        rows=(("North", "120"), ("South", "95"), ("East", "40")),
        page=1,
        bbox=BoundingBox(x0=0.0, y0=0.0, x1=100.0, y1=50.0),
    )
    root = Node.synthetic(content="a document", media_type=MediaType.TEXT, reason="root")
    return root.derive(content=index_text(grid), media_type=MediaType.TABLE).with_ext(grid)


async def test_each_window_records_its_ordinal_and_where_it_starts_in_its_parent() -> None:
    # Act
    windows = await _windows()

    # Assert — step is size - overlap = 8, so windows start at 0, 8, 16, 24.
    positions = [window.ext_as(ChunkPosition) for window in windows]
    assert positions == [
        ChunkPosition(ordinal=0, start=0),
        ChunkPosition(ordinal=1, start=8),
        ChunkPosition(ordinal=2, start=16),
        ChunkPosition(ordinal=3, start=24),
    ]


async def test_recording_the_position_leaves_every_window_id_where_it_was() -> None:
    # Act
    windows = await _windows()

    # Assert
    assert tuple(window.id for window in windows) == _PINNED_WINDOW_IDS


async def test_a_window_cut_from_a_window_records_its_place_in_that_window_not_the_first() -> None:
    # Arrange — nested chunking: the inner chunker's position wins over the one carried forward.
    outer = (await _windows())[1]

    # Act
    outcome = await FixedSizeChunker(FixedSizeChunkerConfig(size=4, overlap=0)).run([outer], _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    assert [node.ext_as(ChunkPosition) for node in outcome.value] == [
        ChunkPosition(ordinal=0, start=0),
        ChunkPosition(ordinal=1, start=4),
        ChunkPosition(ordinal=2, start=8),
    ]


async def test_each_table_row_records_its_ordinal_and_no_character_start() -> None:
    # Act
    outcome = await TableRowChunker(TableRowChunkerConfig()).run([_table()], _ctx())

    # Assert — the table itself is passed through first and is not a chunk of anything.
    assert isinstance(outcome, Produced)
    table, *rows = outcome.value
    assert table.ext_as(ChunkPosition) is None
    assert [row.ext_as(ChunkPosition) for row in rows] == [
        ChunkPosition(ordinal=0, start=None),
        ChunkPosition(ordinal=1, start=None),
        ChunkPosition(ordinal=2, start=None),
    ]


def test_both_chunkers_declare_the_position_they_attach() -> None:
    # Act / Assert
    assert ChunkPosition in FixedSizeChunker.provides
    assert ChunkPosition in TableRowChunker.provides
    assert TableGrid in TableRowChunker.provides


def test_the_pack_registers_the_position_so_a_stored_node_rehydrates_it() -> None:
    # Arrange
    registrar = PackRegistrar(Registry(), distribution="weft-chunk")

    # Act
    register(registrar, Settings())

    # Assert
    assert registrar.ext_models == (ChunkPosition,)


def test_the_position_lives_in_the_weft_chunk_namespace_a_filter_can_name() -> None:
    # Act
    siblings = Filter(op=FilterOp.IN, field="ext.weft-chunk.ordinal", value=(0, 1, 2))

    # Assert
    assert ChunkPosition.__namespace__ == "weft-chunk"
    assert siblings.field == "ext.weft-chunk.ordinal"
