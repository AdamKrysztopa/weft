"""`table-rows` — a table's rows become its children. Ledger `9.14`, `11` §6 rank 3.

**The measurement this stage exists for.** Row-level chunking with the header propagated into
every row moves BM25 Recall@1 **0.366 → 0.754** and hybrid MRR **0.3576 → 0.5945**
(arXiv:2605.00318), which `10` §4 records as the largest absolute gain in the multimodal survey
— and as the number a future `describe-table` would have to beat. A table indexed as one blob
is one retrievable unit no matter how many facts it holds; a row is the unit a question is
usually about.

**Many, plus one.** The parent table node survives alongside its rows, because `11` §4's G4-c
asks that *"a row is retrievable on its own and its parent is one filter away"* — a stage that
replaced the table with its rows would satisfy the first half and destroy the second.

**This does not weaken the atomic rule, and the mechanism is why.** `01`'s *"an atomic node
passes the chunker unsplit"* is enforced by `applies_to` at the registration seam, never by a
prohibition: `weft_chunk.fixed_size.FixedSizeChunker` declares `Applies(media_type=TEXT)`, so a
table routes past it untouched. A chunker that declares `Applies(media_type=TABLE)` is not an
exception to that rule — it is the same mechanism used the other way, and it is what lets a
table be split by something that understands a grid while a generic text chunker still cannot
touch it.
"""

import pytest

from weft_chunk.contract import Chunker
from weft_chunk.table_rows import NAME, TableRowChunker, TableRowChunkerConfig
from weft_extract.payload import BoundingBox, TableGrid
from weft_extract.table_text import index_text
from weft_kernel.context import Context
from weft_kernel.payload import (
    Applies,
    MediaType,
    Node,
    NothingToProduce,
    Produced,
    SourceId,
)

_HEADERS = ("Region", "Revenue")
_ROWS = (("North", "120"), ("South", "95"))


def _ctx() -> Context:
    return Context(tenant_id="t", run_id="r", trace_id="tr", locale="en")


def _grid(caption: str | None = None) -> TableGrid:
    return TableGrid(
        headers=_HEADERS,
        rows=_ROWS,
        caption=caption,
        page=3,
        bbox=BoundingBox(x0=0.0, y0=0.0, x1=100.0, y1=50.0),
    )


def _table_node(caption: str | None = None) -> Node:
    grid = _grid(caption)
    root = Node.synthetic(
        content="a document",
        media_type=MediaType.TEXT,
        reason="test root",
        sources=frozenset({SourceId("/corpus/report.pdf")}),
    )
    return root.derive(content=index_text(grid), media_type=MediaType.TABLE).with_ext(grid)


async def _run(node: Node) -> list[Node]:
    outcome = await TableRowChunker(TableRowChunkerConfig()).run([node], _ctx())
    assert isinstance(outcome, Produced)
    return list(outcome.value)


def test_it_is_selectable_by_name() -> None:
    assert NAME == "table-rows"


def test_it_satisfies_the_chunker_contract_structurally() -> None:
    assert isinstance(TableRowChunker(TableRowChunkerConfig()), Chunker)


def test_it_applies_to_tables_and_to_nothing_else() -> None:
    # The atomic rule's own mechanism — see the module docstring. A stage that declared no
    # applicability would be handed text nodes and would have to branch on media type itself,
    # which is exactly what `11` §4 G2-c settles against.
    assert TableRowChunker.applies_to == (Applies(media_type=MediaType.TABLE),)


def test_it_declares_that_it_destroys_nothing() -> None:
    # `Chunker` publishes a property vocabulary, so `weft_kernel.registry` refuses any
    # implementation that omits `destroys`. Splitting on row boundaries cuts no word, so the
    # honest declaration is the empty tuple rather than `WordBoundaries`.
    assert TableRowChunker.destroys == ()


def test_it_declares_the_fact_it_reads() -> None:
    assert TableRowChunker.requires == (TableGrid,)


def test_it_declares_the_fact_it_attaches() -> None:
    assert TableRowChunker.provides == (TableGrid,)


async def test_the_table_survives_alongside_its_rows() -> None:
    # "Many, plus one" — `11` §6 rank 3. The parent is what G4-c's "one filter away" reaches.
    table = _table_node()

    result = await _run(table)

    assert result[0].id == table.id
    assert len(result) == 1 + len(_ROWS)


async def test_each_row_is_a_child_of_the_table() -> None:
    # Reverse lineage is the whole retrieval story: a row answers, and its table is one
    # `lineage.parents contains <id>` away.
    table = _table_node()

    result = await _run(table)

    assert [child.lineage.parents for child in result[1:]] == [(table.id,), (table.id,)]


async def test_a_row_carries_its_header_into_its_own_content() -> None:
    # The measured gain is header propagation, not row splitting on its own — a row of bare
    # numbers reaching a retriever is a row nobody can match against.
    result = await _run(_table_node())

    assert result[1].content == "Region: North | Revenue: 120"
    assert result[2].content == "Region: South | Revenue: 95"


async def test_a_row_renders_the_way_the_whole_table_renders_that_row() -> None:
    # Two renderings of one row must not drift, so the row's content is `index_text`'s own
    # line for it rather than a second formatter written here.
    table = _table_node()

    result = await _run(table)

    assert index_text(_grid()).splitlines() == [child.content for child in result[1:]]


async def test_a_row_carries_a_grid_of_its_own() -> None:
    # So the row is self-describing: `prompt_markdown` renders it as a one-row table, and a
    # later stage's `requires TableGrid` binds to a row exactly as it binds to a table.
    result = await _run(_table_node())

    row_grid = result[1].ext_as(TableGrid)
    assert row_grid is not None
    assert row_grid.headers == _HEADERS
    assert row_grid.rows == (("North", "120"),)


async def test_a_rows_grid_keeps_the_page_its_table_was_on() -> None:
    # A citation that lost its page is a citation nobody can check.
    result = await _run(_table_node())

    row_grid = result[1].ext_as(TableGrid)
    assert row_grid is not None
    assert row_grid.page == 3


async def test_a_row_stays_a_table_so_no_text_chunker_can_cut_it() -> None:
    # `MediaType.TEXT` here would hand every row to `fixed-size`, which slices on characters
    # and would cut `Revenue: 120` in half on a narrow window.
    result = await _run(_table_node())

    assert all(child.media_type is MediaType.TABLE for child in result[1:])


async def test_rows_are_ordinally_distinct_so_two_identical_rows_are_two_nodes() -> None:
    # `Node`'s id is a content digest that includes the ordinal, and a real table repeats a
    # row often enough that collapsing them would lose data silently — G5's own reason.
    grid = TableGrid(
        headers=_HEADERS,
        rows=(("North", "120"), ("North", "120")),
        page=1,
        bbox=BoundingBox(x0=0.0, y0=0.0, x1=10.0, y1=10.0),
    )
    root = Node.synthetic(
        content="d", media_type=MediaType.TEXT, reason="test root", sources=frozenset()
    )
    table = root.derive(content=index_text(grid), media_type=MediaType.TABLE).with_ext(grid)

    result = await _run(table)

    assert result[1].id != result[2].id


async def test_a_caption_is_not_repeated_into_every_row() -> None:
    # `index_text` emits the caption as its own first line. Copying it into all fifty rows of
    # a table would swamp the header terms the measured gain actually comes from.
    result = await _run(_table_node(caption="Table 2. Revenue by region."))

    assert not any("Table 2." in child.content for child in result[1:])


async def test_a_table_with_no_rows_yields_no_children() -> None:
    # Headers and no body is a table an extractor found and recovered nothing from — it is
    # still a table, and there is nothing to split.
    grid = TableGrid(
        headers=_HEADERS,
        rows=(),
        page=1,
        bbox=BoundingBox(x0=0.0, y0=0.0, x1=10.0, y1=10.0),
    )
    root = Node.synthetic(
        content="d", media_type=MediaType.TEXT, reason="test root", sources=frozenset()
    )
    table = root.derive(content=index_text(grid), media_type=MediaType.TABLE).with_ext(grid)

    result = await _run(table)

    assert result == [table]


async def test_a_table_node_with_no_grid_is_returned_untouched() -> None:
    # `requires TableGrid` makes this unreachable through a resolved pipeline, and a stage
    # that trusted resolution and crashed here would fail a whole batch for one odd node.
    root = Node.synthetic(
        content="d", media_type=MediaType.TEXT, reason="test root", sources=frozenset()
    )
    bare = root.derive(content="Region | Revenue", media_type=MediaType.TABLE)

    result = await _run(bare)

    assert result == [bare]


async def test_an_empty_batch_is_nothing_to_produce() -> None:
    outcome = await TableRowChunker(TableRowChunkerConfig()).run([], _ctx())

    assert isinstance(outcome, NothingToProduce)


def test_the_config_refuses_an_unknown_key() -> None:
    with pytest.raises(ValueError, match="extra_forbidden|Extra inputs"):
        TableRowChunkerConfig(headers=False)  # type: ignore[call-arg]
