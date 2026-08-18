"""First-party enrichment pack.

Publishes the `Enhancer` contract, in `contract.py`, and registers
`KeyBertKeywordExtractor` (`keybert_stand_in.py`) — a deterministic, frequency-ranked
keyword picker that is **not KeyBERT**, on the exact precedent `docs/06-phase-0-build.md`
step 8 sets for `weft-embed`'s `HashEmbedder`: task 1.9's driving use case names KeyBERT
in a `use:` field, and a walking pipeline must not need a model download to prove that
field resolves. See `keybert_stand_in.py`'s own docstring for the full reasoning and the
real technique's citation.

Registered through the same public `weft.packs` entry point any third-party pack uses —
fitness function 2 — with no shortcut for being first-party.
"""

from pydantic import BaseModel, ConfigDict

from weft_enhance.contract import ENHANCER_CONTRACT_VERSION, Enhancer
from weft_enhance.keybert_stand_in import KeyBertConfig, KeyBertKeywordExtractor
from weft_enhance.keywords import Keywords
from weft_kernel.discovery import PackRegistrar


class Settings(BaseModel):
    """`weft-enhance` takes no pack settings — an empty model is still the required shape."""

    model_config = ConfigDict(frozen=True, extra="forbid")


def register(registrar: PackRegistrar, settings: Settings) -> None:
    """Register `KeyBertKeywordExtractor` as `"keybert"` for `Enhancer`. The only plugin here."""
    del settings
    registrar.add(Enhancer, "keybert", KeyBertKeywordExtractor)


__all__ = [
    "ENHANCER_CONTRACT_VERSION",
    "Enhancer",
    "KeyBertConfig",
    "KeyBertKeywordExtractor",
    "Keywords",
    "Settings",
    "register",
]
