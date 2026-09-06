"""The two table serialisations — ledger task `9.6`, and `11` §6 rank 10.

*"Triplets for the index, markdown or HTML for the prompt. A single linearisation cannot
serve both, which is the concrete reason the grid must survive extraction."* So there are
two functions here — `index_text` for retrieval, `prompt_markdown` for a generator — and
they live in the pack that publishes `TableGrid`, `weft_extract`, rather than in whichever
extractor happened to need one first (`11` §6 rank 11: *"if two extractors both need it,
it belongs to the contract's pack"*).

**The property `9.6` states, in its own words: a cell containing a pipe cannot break one
extractor and not another.** Both renderings are delimited — `index_text` by ` | ` between
cells and by newlines between rows, `prompt_markdown` by `|` at every column boundary — and
a financial table legitimately contains `|`, `\\` and newlines. One escape function, used by
both, makes the rendering injective: two different grids never collide on one string. It
escapes backslash first (so the escape sequences it introduces for `|` and newline are not
themselves re-escaped), then `|`, then `\\n` and `\\r` — a newline inside a cell must never
become a new line in the output, or one cell silently becomes a row.

Both functions are pure, deterministic and synchronous: a node id is a digest of its
content, so a serialiser that varied would re-index a corpus that had not changed.
"""

from weft_extract.payload import TableGrid


def _escape(cell: str) -> str:
    """The one escape both serialisers use, applied to every cell, header and caption.

    Order matters: backslash first, so the escape sequences introduced below are not
    themselves swept up by a second pass over `\\`. `|` next, since both renderings use
    it as a delimiter. Then `\\n` and `\\r`, so an embedded newline cannot split one cell
    into two rows in either format.
    """
    return cell.replace("\\", "\\\\").replace("|", "\\|").replace("\n", "\\n").replace("\r", "\\r")


def row_text(grid: TableGrid, index: int) -> str:
    """`grid.rows[index]` rendered exactly the way `index_text` renders that row.

    Factored out for ledger task `9.14`: `weft_chunk.table_rows.TableRowChunker` turns a
    row into a node of its own, and that node's content has to be byte-for-byte what
    `index_text` already emits for that row, or the two renderings drift the moment either
    is edited alone. `index_text` calls this for every row rather than duplicating the
    format, which is what makes drift structurally impossible rather than merely unlikely.

    Each cell renders `{header}: {value}`, joined ` | ` across the row, through the same
    `_escape` both serialisers share. `index` is passed straight to `grid.rows[index]`, so
    an out-of-range index raises the ordinary `IndexError` — no guard is added, since a
    caller passing an index it did not get from iterating `grid.rows` has a bug worth
    seeing plainly.
    """
    headers = tuple(_escape(header) for header in grid.headers)
    row = grid.rows[index]
    return " | ".join(
        f"{header}: {_escape(value)}" for header, value in zip(headers, row, strict=True)
    )


def index_text(grid: TableGrid) -> str:
    """The retrieval rendering: a caption line if there is one, then one line per row.

    Each row's line is `row_text`'s own line for it — see that function's docstring for
    why the two must never be produced by two separate formatters. The header is repeated
    on every row deliberately — `11` §6 rank 3's measured gain (BM25 Recall@1 0.366 →
    0.754, arXiv:2605.00318) is row-level retrieval with the header propagated, and a row
    reaching a retriever without its header is a row of numbers nobody can read. No
    caption line is emitted when `grid.caption` is `None` — `11` §2.4 refuses a
    synthesised label outright.
    """
    headers = tuple(_escape(header) for header in grid.headers)
    lines: list[str] = []
    if grid.caption is not None:
        lines.append(_escape(grid.caption))
    if grid.rows:
        for index in range(len(grid.rows)):
            lines.append(row_text(grid, index))
    else:
        # A table an extractor found and recovered no body from is still a table: the
        # headers are the only fact left to carry, so they render on their own line.
        lines.append(" | ".join(headers))
    return "\n".join(lines)


def prompt_markdown(grid: TableGrid) -> str:
    """The generator rendering: a GitHub-flavoured markdown table.

    A header row, a delimiter row of dashes, then one row per data row — every line
    starting and ending with `|`. A caption, if there is one, is a line above the table.
    """
    headers = tuple(_escape(header) for header in grid.headers)
    lines: list[str] = []
    if grid.caption is not None:
        lines.append(_escape(grid.caption))
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("| " + " | ".join("---" for _ in headers) + " |")
    for row in grid.rows:
        lines.append("| " + " | ".join(_escape(value) for value in row) + " |")
    return "\n".join(lines)
