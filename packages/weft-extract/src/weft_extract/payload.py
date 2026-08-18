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
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from weft_kernel.payload import NodeId


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
