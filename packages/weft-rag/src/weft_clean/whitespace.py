"""`WhitespaceNormalizer` — collapses whitespace runs. Destructive by design, and last.

Task **1.7**'s third worked example — `02` §3 → *Ordering constraints*:
"`WhitespaceNormalizer` must run last for being destructive, not because
anyone reads its output."

`destroys = (Newlines, WhitespaceGaps)` states that plainly instead of
leaving it to a comment nobody reads before inserting a new stage: collapsing
a whitespace run to one space is a single operation that erases both the
column gap a table lineariser reads and the line break a hyphenation repair
reads, which is why one stage's `destroys` tuple names both properties
`weft_clean.hyphenation.HyphenationRepair` and
`weft_clean.table_linearizer.TableLinearizer` each need `intact` — see
`weft_clean.property` for why splitting the reasoning into two facts, not
one, matters.

**Task 2.35 adds a third**: `Verbatim` joins the other two, for the same
reason it joins every other processor in this pack — collapsing whitespace
and trimming edges (`_normalize` below) both rewrite the exact character
sequence extraction produced, which is what `weft_clean.property`'s module
docstring means by every stage in this pack destroying `Verbatim`, not only
the one that is destructive by design.

`config_model = WhitespaceNormalizerConfig` — a repair, not part of the
original lift, on the same footing `weft_clean.hyphenation`'s note gives.
"""

import re
from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict

from weft_clean.property import Newlines, Verbatim, WhitespaceGaps
from weft_kernel.context import Context
from weft_kernel.payload import (
    Applies,
    MediaType,
    Node,
    NothingToProduce,
    Outcome,
    Produced,
    Property,
    carry_forward,
)

_HORIZONTAL_RUN = re.compile(r"[ \t]+")
_BLANK_LINE_RUN = re.compile(r"\n{3,}")
_TRAILING_HORIZONTAL_SPACE = re.compile(r"[ \t]+\n")


class WhitespaceNormalizerConfig(BaseModel):
    """`WhitespaceNormalizer` takes no `with:` configuration — an empty model is still the shape."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class WhitespaceNormalizer:
    """Collapses runs of spaces/tabs to one, and three-or-more blank lines to a paragraph break.

    Satisfies `weft_clean.contract.Cleaner` structurally. The single stage in
    this pack that touches whitespace structure at all — see the module
    docstring for why its `destroys` tuple names two properties, not one.
    """

    intact: tuple[type[Property], ...] = ()
    destroys: tuple[type[Property], ...] = (Newlines, WhitespaceGaps, Verbatim)
    #: Ledger task **9.8**. `docs/11-multimodal.md` §2.4: **"Tables leave this pipeline."** A
    #: cleaner rebuilds its node with `Node.derive`, which deliberately drops `ext` — so a
    #: `TABLE` node passing through here loses the `TableGrid` that *is* the table, and an
    #: `IMAGE` node loses the `BlobRef` that is the only surviving pointer to its pixels. That is
    #: `11` §1.4's own scar, verbatim: a comparable design "destroyed the grid inside its cleaning
    #: pipeline, which is why nothing downstream could choose a representation".
    #:
    #: Declared as what this cleaner *needs* rather than as what it excludes, per `02` §3: it
    #: repairs prose, and prose is `MediaType.TEXT`. Everything else the runner routes past.
    applies_to: tuple[Applies, ...] = (Applies(media_type=MediaType.TEXT),)
    config_model: type[WhitespaceNormalizerConfig] = WhitespaceNormalizerConfig

    def __init__(self, config: WhitespaceNormalizerConfig | None = None) -> None:
        self._config = config if config is not None else WhitespaceNormalizerConfig()

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        del ctx
        if not payload:
            return NothingToProduce(reason="no nodes to normalize")
        normalized = [
            carry_forward(node.derive(content=_normalize(node.content)), parent=node)
            for node in payload
        ]
        return Produced(value=normalized)


def _normalize(text: str) -> str:
    """`text` with every whitespace run collapsed, paragraph breaks kept, edges trimmed."""
    collapsed = _HORIZONTAL_RUN.sub(" ", text)
    collapsed = _TRAILING_HORIZONTAL_SPACE.sub("\n", collapsed)
    collapsed = _BLANK_LINE_RUN.sub("\n\n", collapsed)
    return collapsed.strip()
