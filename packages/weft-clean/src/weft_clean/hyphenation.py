"""`HyphenationRepair` — rejoins a word broken across a line by a trailing hyphen.

Task **1.7**'s worked example, and `02` §3 → *Ordering constraints*'s own —
"hyphenation repair... MUST run before whitespace normalization while
newlines still exist (e.g. kompu-\\nter -> komputer)" is the reference's own
docstring restated for Weft, verified against
`indexing/cleaning/pipeline.py:30-51`. The reasoning is `weft_clean.property`'s:
a broken word's two halves are only rejoinable while the line break between
them is still a real newline, not yet folded into an ordinary space by
`weft_clean.whitespace.WhitespaceNormalizer` — once that happens there is no
longer a seam to find.

`intact = (Newlines,)` is what turns that sentence into something
`weft_kernel.resolution.resolve` checks: a pipeline placing this stage after
anything that destroys `Newlines` fails at load, naming both stages, rather
than silently shipping two words that used to be one.

`config_model = HyphenationRepairConfig` — a repair, not part of the
original lift. Without this class attribute, a stray non-empty `with:` block
here would raise `StageNotConfigurableError` claiming this stage cannot be
parameterised at all, rather than the accurate `InvalidStageConfigError`
naming the field it does not accept — see `weft_chunk.fixed_size` for the
worked case where the missing model actually blocked a real knob.
"""

import re
from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict

from weft_clean.property import Newlines
from weft_kernel.context import Context
from weft_kernel.payload import Node, NothingToProduce, Outcome, Produced, Property

# A word ending in a hyphen at a line break, continued on the next line — the
# reference's own example is `kompu-\nter`. Authored fresh for Weft: match a run of
# letters, a hyphen sitting at the line break (optional trailing spaces before
# the newline, since extraction sometimes leaves a stray one), then a run of
# letters starting the next line, and join the two halves with the hyphen
# dropped. `re.UNICODE` (the default for `str` patterns in Python 3) keeps this
# correct for accented letters — the reference's own whitespace stage was flagged
# for the opposite mistake in `docs/04-reference-inventory.md`.
_BROKEN_WORD = re.compile(r"(\w+)-[ \t]*\n[ \t]*(\w+)", re.UNICODE)


class HyphenationRepairConfig(BaseModel):
    """`HyphenationRepair` takes no `with:` configuration — an empty model is still the shape."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class HyphenationRepair:
    """Joins `word-\\nword` back into one word, for every node in the batch.

    Satisfies `weft_clean.contract.Cleaner` structurally, the same path any
    third-party cleaning pack takes.
    """

    intact: tuple[type[Property], ...] = (Newlines,)
    destroys: tuple[type[Property], ...] = ()
    config_model: type[HyphenationRepairConfig] = HyphenationRepairConfig

    def __init__(self, config: HyphenationRepairConfig | None = None) -> None:
        self._config = config if config is not None else HyphenationRepairConfig()

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        del ctx  # no service or locale this stage needs
        if not payload:
            return NothingToProduce(reason="no nodes to repair")
        repaired = [node.derive(content=_repair(node.content)) for node in payload]
        return Produced(value=repaired)


def _repair(text: str) -> str:
    """Every `word-\\nword` pair in `text`, joined into one word."""
    return _BROKEN_WORD.sub(r"\1\2", text)
