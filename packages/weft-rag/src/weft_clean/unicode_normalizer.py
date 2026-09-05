"""`UnicodeNormalizer` — repairs mis-decoded byte sequences before any other cleaner runs.

Task **2.35** — `docs/04-reference-inventory.md` category A names six cleaning processors;
`weft-clean` shipped four. This is the first of the two absent, and the reference's own
rationale (`indexing/cleaning/pipeline.py:70`, verbatim) is why it goes first: *"Fix
encoding errors first (e.g., Ã³ -> ó) so regexes work correctly."* Verified at source,
`reference/study/08-salvage.md` §T1.1 and `unicode_normalizer.py:12-37`: the reference's own
`process` calls `ftfy.fix_text(text)`, then `unicodedata.normalize('NFC', fixed)`. The
second call is dropped here, not carried: `ftfy.fix_text`'s own default configuration
already performs NFC normalisation (`ftfy.TextFixerConfig.normalization = "NFC"`), so
re-running `unicodedata.normalize` afterward changes nothing it did not already do — a
correction, not a copy, the same reference-lift latitude that already dropped the reference's
unused `llm` constructor parameter from every processor in this pack.

**`intact = (Verbatim,)` is the constraint `01`'s Phase 2 exit reference audit found missing.**
Every regex in this pack's other five processors assumes it is looking at exactly the
character sequence extraction produced — `weft_clean.property`'s module docstring works
through why: a mis-decoded byte sequence is only recognisable to `ftfy.fix_text` while it
is still contiguous, in its original order, with nothing else's insertion, deletion or
join having touched it first. This stage is the only one in the pack that ever declares
`intact = (Verbatim,)`, and `destroys = (Verbatim,)` here too — repairing the mis-decoded
sequence is itself a change to the character stream, the same honest reason every other
processor in this pack destroys it. That symmetry costs nothing: the only stage that could
ever be checked against `UnicodeNormalizer`'s own `destroys` is itself, and the intact
check on a stage's own `destroys` set never fires against itself — see
`weft_kernel.resolution.resolve`, which checks `intact` before recording what the current
stage destroys, not after.

`config_model = UnicodeNormalizerConfig` — a repair, not part of the original lift, on the
same footing `weft_clean.hyphenation`'s own note gives.
"""

from collections.abc import Sequence

import ftfy
from pydantic import BaseModel, ConfigDict

from weft_clean.property import Verbatim
from weft_kernel.context import Context
from weft_kernel.payload import Node, NothingToProduce, Outcome, Produced, Property


class UnicodeNormalizerConfig(BaseModel):
    """`UnicodeNormalizer` takes no `with:` configuration — an empty model is still the shape."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class UnicodeNormalizer:
    """Repairs mis-decoded byte sequences (`Ã³` -> `ó`) and normalises Unicode to NFC.

    Satisfies `weft_clean.contract.Cleaner` structurally, the same path any third-party
    cleaning pack takes.
    """

    intact: tuple[type[Property], ...] = (Verbatim,)
    destroys: tuple[type[Property], ...] = (Verbatim,)
    config_model: type[UnicodeNormalizerConfig] = UnicodeNormalizerConfig

    def __init__(self, config: UnicodeNormalizerConfig | None = None) -> None:
        self._config = config if config is not None else UnicodeNormalizerConfig()

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        del ctx  # no service or locale this stage needs
        if not payload:
            return NothingToProduce(reason="no nodes to normalize")
        normalized = [node.derive(content=_normalize(node.content)) for node in payload]
        return Produced(value=normalized)


def _normalize(text: str) -> str:
    """`text` with encoding errors repaired and Unicode normalised to NFC."""
    return ftfy.fix_text(text)
