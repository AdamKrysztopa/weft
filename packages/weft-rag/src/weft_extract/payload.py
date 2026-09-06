"""`Rendition` — what a `Renderer` produces, and an honest account of what it cost.

`.phase2-design.md` A.2, attached to ledger task 2.27 by A.4's consequences
table. The constraint this satisfies is the project owner's, recorded as
finding 10: **the parse result is a typed model whose export formats are
pluggable.** `json` is intrinsic and needs nothing; every other format is a
registration under one contract, so a third party adding `docx` writes a
distribution and edits nothing here.

**Why this is not a `str` return, which is the whole design.** A format that
cannot carry a table, an image or an embedding has lost something, and a
renderer that hands back only text is indistinguishable from one that lost
nothing — the same success-and-failure-look-alike shape the project refuses
everywhere else. `dropped` is where that is said out loud, and A.2 states the
review rule directly: "a renderer returning a partial document with an empty
`dropped` is a defect the reviewer must catch."

**`media_type` is a plain `str`, and this is the one place the project's
enum-over-string-constant rule does not apply.** `weft_kernel.payload.MediaType`
is a closed enum precisely because it is core-field vocabulary every store and
strategy must understand. An IANA media type is the opposite: the set is open
by construction, and the first third-party renderer would need a member added
to an enum in a distribution it does not own, which is requirement 1 failing on
its own terms.

**`BoundingBox`, `CellSpan`, `PageSpan` and `TableGrid` — ledger task 9.5.** `docs/11-
multimodal.md` §2.4's ingest path gives the payload table: a prose node carries a
`PageSpan` (page, reading-order ordinal), a table node carries a `TableGrid` (rows,
headers, spans, caption, page, bbox), and a figure node carries a `PageSpan` *and* a
`BlobRef` (`weft_blob.payload`, shipped at task 9.4).

**Why here and not `weft-pdf`, which is what `11:181` proposes.** That line predates
`9.13`, which ships a *second* structured extractor — `weft-docling`, its own
distribution, kept separate for its dependency weight — and that extractor produces
tables too. A `TableGrid` published from `weft-pdf` would make every future table
producer depend on the pdfplumber pack to name the fact it produces. `11` §6 rank 11
already states the rule this follows, and calls it the canonical example of itself:
*"if two extractors both need it, it belongs to the contract's pack"*. `weft_extract`
is the pack that publishes `Extractor`, so it is that pack.

**Neither `TableGrid` nor `PageSpan` is transient.** `11` §2.4 is explicit for the
grid — *"a cell grid is kilobytes of JSONB, which is what `ext` is for. Only bytes were
ever a transience problem"* — and a comparable design destroyed its grid inside the
cleaning pipeline, which is why nothing downstream could choose a representation.
Stripping either would leave a node in the store that no serialiser could re-render and
no retriever could filter by page.

**`BoundingBox` and `CellSpan` are models, not tuples.** A positional quadruple is a
convention a docstring states and nothing enforces — the exact shape `11` §6 records a
third party paying for, where "the cache key is a positional assumption its own
docstring states and nothing enforces". Naming the edges (and a merged cell's row,
column and span) costs one class each and makes the mistake unrepresentable — a
`model_validator` can refuse an inverted box in a way four bare floats cannot.

**`TableGrid` refuses a ragged grid.** A row whose width disagrees with `headers` is
representable in a list-of-lists and meaningless as a table — a serialiser would emit
cells under the wrong headers, silently, and task `9.6` ships two serialisers that
would both do it. Refused here, where the fact is built, rather than at whichever
serialiser notices first.

**`caption` defaults to `None`, never `""`.** `11` §2.4 refuses a synthesised label
outright; `None` is the honest absence of one.
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from weft_kernel.payload import ExtModel, NodeId


class DroppedKind(StrEnum):
    """What kind of thing a rendered format could not carry."""

    #: The node's `media_type` has no representation in this format, so a reader cannot
    #: tell a table from a paragraph.
    MEDIA = "media"
    #: The node carried a vector. No text format holds one.
    EMBEDDING = "embedding"
    #: A declared extension model — page boundaries, a table grid, whatever a parser
    #: recovered beyond the text.
    EXTENSION = "extension"


class DroppedContent(BaseModel):
    """One thing one node carried that the rendered format could not.

    Per node rather than per rendition, because "something was lost" is not
    actionable and "the page boundaries on node `sha256:…` were lost" is: a
    caller can go and fetch that node.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    node_id: NodeId
    kind: DroppedKind
    #: What was lost, named — the extension model's namespace, the media type, or the
    #: dimension of the vector. Free text because the three kinds have nothing in common
    #: to make a field out of.
    detail: str = Field(min_length=1)


class Rendition(BaseModel):
    """One rendered document, and an honest account of what rendering cost.

    Not a `Node`: the output leaves the pipeline for a human or another system,
    which is what makes a `Renderer` a terminus rather than another `Node`
    transformation — see `weft_extract.contract.Renderer`.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    text: str
    #: The IANA type, e.g. `"text/markdown"` — see the module docstring for why this is
    #: a `str` and not an enum.
    media_type: str = Field(min_length=1)
    nodes_rendered: int = Field(ge=0)
    dropped: tuple[DroppedContent, ...] = ()


class BoundingBox(BaseModel):
    """A rectangle on a page, in the extractor's own coordinate space.

    A value inside `TableGrid`, not itself an `ExtModel` — it never carries a namespace
    of its own, only ever appears nested inside a fact that does. Named edges rather than
    a 4-tuple: see the module docstring's argument for `BoundingBox` and `CellSpan`.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    x0: float
    y0: float
    x1: float
    y1: float

    @model_validator(mode="after")
    def _edges_are_not_inverted(self) -> "BoundingBox":
        if self.x1 <= self.x0:
            raise ValueError(f"BoundingBox has x1 ({self.x1}) <= x0 ({self.x0}); not a box")
        if self.y1 <= self.y0:
            raise ValueError(f"BoundingBox has y1 ({self.y1}) <= y0 ({self.y0}); not a box")
        return self


class CellSpan(BaseModel):
    """One merged cell in a `TableGrid`, named rather than positional.

    A value inside `TableGrid`, not itself an `ExtModel`, for the identical reason
    `BoundingBox` is not: see the module docstring.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    row: int = Field(ge=0)
    column: int = Field(ge=0)
    row_span: int = Field(ge=1)
    column_span: int = Field(ge=1)


class PageSpan(ExtModel):
    """Where in the document a node sits: which page, and its reading-order position on it.

    Carried by a prose node and a figure node alike (`11` §2.4) — a figure carries this
    *and* a `BlobRef` together, which is why this occupies its own namespace rather than
    folding into the blob's.
    """

    __namespace__ = "weft-extract-page"
    __schema_version__ = "1.0.0"

    #: 1-based. A page an extractor could not determine is a bug upstream, not a `-1`
    #: sentinel — see the module docstring.
    page: int = Field(ge=1)
    #: 0-based reading-order position within the page.
    ordinal: int = Field(ge=0)


class TableGrid(ExtModel):
    """A table an extractor recovered: its cells, any merges, its caption and where it sits.

    Not transient — see the module docstring's argument, quoting `11` §2.4 directly: a
    cell grid is kilobytes of JSONB, which is what `ext` is for, and only bytes were ever
    a transience problem. Carries no `bytes` field of any kind; fitness function 24
    (`tests/architecture/test_ff24_no_bytes_in_a_node.py`) refuses one across the whole
    tree.
    """

    __namespace__ = "weft-extract-table"
    __schema_version__ = "1.0.0"

    headers: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]
    spans: tuple[CellSpan, ...] = ()
    #: `None` is the honest absence of a caption; see the module docstring for why this
    #: is never defaulted to `""`.
    caption: str | None = None
    page: int = Field(ge=1)
    bbox: BoundingBox

    @model_validator(mode="after")
    def _grid_is_not_ragged(self) -> "TableGrid":
        width = len(self.headers)
        for index, row in enumerate(self.rows):
            if len(row) != width:
                raise ValueError(
                    f"TableGrid row {index} has {len(row)} cells but headers declare "
                    f"{width}; every row must agree with headers or the grid is not a "
                    f"grid — see the module docstring"
                )
        return self
