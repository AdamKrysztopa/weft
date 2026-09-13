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


#: What this plugin is called, and the name describes the arithmetic. **It was `keybert` until
#: ledger task `21.10`** — `R19.15` — and that was the overclaim `10` §2.1 rule 4 exists to forbid:
#: real KeyBERT (Grootendorst, doi:10.5281/zenodo.4461265) ranks n-grams by cosine similarity to a
#: transformer embedding of the document, and this counts tokens against a fixed stoplist.
NAME = "term-frequency-keywords"

#: The name `weft-rag 2.4.0` published, kept registered and **marked**. Removing it would turn a
#: working `weft.toml` into an `UnknownPluginError` on upgrade, and leaving it unmarked would be
#: the silent half `09` §2.2 refuses: *"inside 0.x a contract may move without a deprecation
#: period, but never silently."*
RETIRED_NAME = "keybert"


def register(registrar: PackRegistrar, settings: Settings) -> None:
    """Register `KeyBertKeywordExtractor` under both names for `Enhancer`, and `Keywords` as
    this pack's own `ExtModel` — task 5.2g, see `weft_chunk.__init__`'s own module
    docstring for the full argument for why this costs no `weft-store` dependency.

    **Two names, one plugin, and the old one is marked.** `PackRegistrar.deprecate` is task
    5.2e's mechanism for exactly this: the fact is stated once here and
    `weft_kernel.seam.warn_deprecated` emits the notice at the registration seam, so nobody
    writes a warning by hand and nobody has to remember to.
    """
    del settings
    registrar.add(Enhancer, NAME, KeyBertKeywordExtractor)
    registrar.add(Enhancer, RETIRED_NAME, KeyBertKeywordExtractor)
    registrar.deprecate(
        RETIRED_NAME,
        reason=(
            f"renamed to '{NAME}', which is what it does: it ranks tokens by frequency against a "
            f"fixed stoplist, and real KeyBERT ranks n-grams by similarity to a transformer "
            f"embedding of the document. Change 'use: keybert' to 'use: {NAME}'; nothing else "
            f"about the stage moves"
        ),
    )
    registrar.add_ext_model(Keywords)


__all__ = [
    "ENHANCER_CONTRACT_VERSION",
    "NAME",
    "RETIRED_NAME",
    "Enhancer",
    "KeyBertConfig",
    "KeyBertKeywordExtractor",
    "Keywords",
    "Settings",
    "register",
]
