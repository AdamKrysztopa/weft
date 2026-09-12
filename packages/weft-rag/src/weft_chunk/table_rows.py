"""`table-rows` — a table's rows become its children. Ledger `9.14`, `11` §6 rank 3.

**The measurement this stage exists for.** Row-level chunking with the header propagated
into every row moves BM25 Recall@1 **0.366 → 0.754** and hybrid MRR **0.3576 → 0.5945**
(arXiv:2605.00318), which `10` §4 records as the largest absolute gain in the multimodal
survey — and as the number a future `describe-table` would have to beat. A table indexed
as one blob is one retrievable unit no matter how many facts it holds; a row is the unit
a question is usually about.

**Many, plus one.** The parent table node survives alongside its rows, because `11` §4's
G4-c asks that *"a row is retrievable on its own and its parent is one filter away."* A
stage that replaced the table with its rows would satisfy the first half and destroy the
second — `run` emits the node itself first, then its row children, for every node in the
batch.

**This does not weaken the atomic rule; it is the same mechanism used the other way.**
`01`'s *"an atomic node passes the chunker unsplit"* is enforced by `applies_to` at the
registration seam, never by a prohibition: `weft_chunk.fixed_size.FixedSizeChunker`
declares `Applies(media_type=TEXT)`, so a table routes past it untouched.
`TableRowChunker` declares `Applies(media_type=TABLE)` instead — not an exception to the
rule, the identical mechanism applied to the one media type that understands a grid.

**A row's content is `weft_extract.table_text.row_text`'s own line for it**, never a
second formatter written here — see that function's docstring for why two renderings of
one row must never be free to drift. Each child then carries forward what its parent's
`ext` said (`weft_kernel.payload.carry_forward`, minus `SyntheticOrigin`) and, last, its own
one-row `TableGrid` — attached after the carry so it wins over the parent's whole-table
grid in the same namespace. `spans` and `caption` are deliberately **not** carried into a
row's own grid: a `CellSpan` describes a merge across the table's whole geometry, which
one row does not have, and the caption belongs to the table — repeating it into fifty rows
would swamp the header terms the measured gain above actually comes from, and the parent
node still carries it, one `lineage.parents` filter away.

**`MediaType.TABLE` on every row, never `TEXT`.** `TEXT` would route each row straight
into `fixed-size`, which slices on characters with no notion of a row boundary and would
cut `Revenue: 120` in half on a narrow window.
"""

from collections.abc import Sequence
from typing import ClassVar

from pydantic import BaseModel, ConfigDict

from weft_extract.payload import TableGrid
from weft_extract.table_text import row_text
from weft_kernel.context import Context
from weft_kernel.payload import (
    Applies,
    ExtModel,
    MediaType,
    Node,
    NothingToProduce,
    Outcome,
    Produced,
    Property,
    carry_forward,
)

NAME = "table-rows"


class TableRowChunkerConfig(BaseModel):
    """`TableRowChunker`'s `with:` configuration — empty, and deliberately so.

    Every decision this stage could expose is already settled by the task it implements:
    the parent table survives, its caption is not repeated into every row, and a row stays
    `MediaType.TABLE` rather than becoming plain text. `weft_chunk.Settings` is the
    precedent for an empty model still being the required shape, per
    `docs/02-extension-model.md` §1's rule that a contract's registration API carries a
    typed configuration model or the extension point is decorative.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")


class TableRowChunker:
    """Splits a table node into row children, each self-describing, alongside its parent.

    Satisfies `weft_chunk.contract.Chunker` structurally — this class never imports it, the
    same path any third-party chunker pack takes. See the module docstring for "many, plus
    one" and for why a row keeps `MediaType.TABLE`.
    """

    applies_to: tuple[Applies, ...] = (Applies(media_type=MediaType.TABLE),)
    #: `Chunker` publishes a property vocabulary, so `weft_kernel.registry` refuses any
    #: implementation that omits `destroys`. Splitting on row boundaries cuts no word — the
    #: only property this pack has ever named is `WordBoundaries`, and a row keeps every
    #: cell whole — so the empty tuple is the honest declaration, not an omission.
    destroys: tuple[type[Property], ...] = ()
    requires: ClassVar[tuple[type[ExtModel], ...]] = (TableGrid,)
    provides: ClassVar[tuple[type[ExtModel], ...]] = (TableGrid,)
    config_model: type[TableRowChunkerConfig] = TableRowChunkerConfig

    def __init__(self, config: TableRowChunkerConfig | None = None) -> None:
        self._config = config if config is not None else TableRowChunkerConfig()

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        del ctx  # no service or locale this stage needs
        if not payload:
            return NothingToProduce(reason="no table nodes to split into rows")
        result: list[Node] = []
        for node in payload:
            result.append(node)
            result.extend(_rows(node))
        return Produced(value=result)


def _rows(node: Node) -> list[Node]:
    """`node`'s row children, or none at all if it carries no `TableGrid`, or an empty one.

    `requires = (TableGrid,)` makes a grid-less table node unreachable through a resolved
    pipeline; this still checks rather than trusting resolution, because crashing here
    would fail a whole batch for one odd node — the same reasoning
    `weft_vision.describe_figure._describe_one` gives for leaving a `BlobRef`-less node
    untouched rather than raising.
    """
    grid = node.ext_as(TableGrid)
    if grid is None:
        return []
    children: list[Node] = []
    for index, row in enumerate(grid.rows):
        child = node.derive(
            content=row_text(grid, index), media_type=MediaType.TABLE, ordinal=index
        )
        child = carry_forward(child, parent=node)
        # The row's own grid is attached last, so it wins over the parent's whole-table
        # `TableGrid` in the same namespace. No `spans`, no `caption` — see the module
        # docstring for why both are the table's facts, not this row's.
        row_grid = TableGrid(headers=grid.headers, rows=(row,), page=grid.page, bbox=grid.bbox)
        children.append(child.with_ext(row_grid))
    return children


__all__ = ["NAME", "TableRowChunker", "TableRowChunkerConfig"]
