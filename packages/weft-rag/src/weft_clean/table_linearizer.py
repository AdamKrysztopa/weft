"""`TableLinearizer` — turns whitespace-separated columns into one cell per line.

Task **1.7**'s second worked example — `02` §3 → *Ordering constraints*:
"table linearisation needs the whitespace gaps; whitespace normalisation
destroys both and must run last."

The reasoning: extracted text carries no marker saying
"these two words are in different table columns" — the only surviving signal
is the run of spaces between them, wider than an ordinary word gap. Once
`weft_clean.whitespace.WhitespaceNormalizer` has collapsed every run of
whitespace to one space, that signal is gone and a table reads as one run-on
sentence. `intact = (WhitespaceGaps,)` is what makes a pipeline that places
this stage after `WhitespaceNormalizer` fail at load rather than at the first
document that happened to contain a table.

**Task 2.35 adds `destroys = (Verbatim,)`.** Rewriting a wide gap into a
newline (`_linearize` below) inserts a character extraction never produced —
the same honest reason every other processor in this pack destroys
`Verbatim`; see `weft_clean.property`'s module docstring.

**`config_model = TableLinearizerConfig` — a repair, not part of the
original lift.** Without this class attribute, `weft_kernel.resolution.
resolve` reads `getattr(declared, "config_model", None)` as `None` and
refuses any `with:` block naming `gap_width` with `StageNotConfigurableError`,
falsely claiming this stage "cannot be parameterised at all" even though
`TableLinearizerConfig`, immediately above, is exactly the model task 1.5's
mechanism was built to validate against.
"""

import re
from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict, model_validator

from weft_clean.property import Verbatim, WhitespaceGaps
from weft_kernel.context import Context
from weft_kernel.payload import Node, NothingToProduce, Outcome, Produced, Property

#: A run this wide is read as a column boundary rather than an ordinary word
#: gap. Chosen independently for Weft — a short row is exempted below instead
#: of tuning this threshold down, so the two knobs stay separable.
_DEFAULT_GAP_WIDTH = 3

#: A line shorter than this is more likely a caption or a page artefact than
#: a real table row, and splitting it on whitespace risks shredding prose
#: that merely happens to contain two spaces.
_MIN_ROW_LENGTH = 12


class TableLinearizerConfig(BaseModel):
    """`TableLinearizer`'s `with:` configuration: how wide a gap counts as a column boundary."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    gap_width: int = _DEFAULT_GAP_WIDTH

    @model_validator(mode="after")
    def _gap_width_is_positive(self) -> "TableLinearizerConfig":
        if self.gap_width < 1:
            raise ValueError(f"gap_width must be at least 1 (got {self.gap_width})")
        return self


class TableLinearizer:
    """Rewrites `Column1   Column2` as `Column1\\nColumn2`, one line at a time.

    Satisfies `weft_clean.contract.Cleaner` structurally.
    """

    intact: tuple[type[Property], ...] = (WhitespaceGaps,)
    destroys: tuple[type[Property], ...] = (Verbatim,)
    config_model: type[TableLinearizerConfig] = TableLinearizerConfig

    def __init__(self, config: TableLinearizerConfig | None = None) -> None:
        self._config = config if config is not None else TableLinearizerConfig()

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        del ctx
        if not payload:
            return NothingToProduce(reason="no nodes to linearize")
        linearized = [
            node.derive(content=_linearize(node.content, gap_width=self._config.gap_width))
            for node in payload
        ]
        return Produced(value=linearized)


def _linearize(text: str, *, gap_width: int) -> str:
    """Every wide-gap line in `text`, one cell per line; short or gap-free lines untouched."""
    gap = re.compile(r" {" + str(gap_width) + r",}")
    lines: list[str] = []
    for line in text.split("\n"):
        if len(line.strip()) >= _MIN_ROW_LENGTH and gap.search(line):
            cells = [cell.strip() for cell in gap.split(line) if cell.strip()]
            lines.append("\n".join(cells))
        else:
            lines.append(line)
    return "\n".join(lines)
