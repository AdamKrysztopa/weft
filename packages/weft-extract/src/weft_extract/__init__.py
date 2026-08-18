"""First-party extraction pack.

Publishes the `Extractor` contract, in `contract.py` — the Protocol, its
version and the `SourceDoc` boundary type it needs, per the canonical-file
convention `docs/07-extension-cost.md` §1 sets for a brand new contract. The
kernel defines no capability contract at all (G1), so this contract is owned
here and this pack registers through the same public entry point a third
party would use — fitness function 2. `register()` and the built-in text
extractor (`text.py`) arrive at `docs/06-phase-0-build.md` step 8.
"""

from pydantic import BaseModel, ConfigDict

from weft_extract.contract import EXTRACTOR_CONTRACT_VERSION, Extractor, SourceDoc
from weft_extract.text import EXTENSIONS, TextExtractor, TextExtractorConfig, discover_source_docs
from weft_kernel.discovery import PackRegistrar


class Settings(BaseModel):
    """`weft-extract` takes no pack settings — an empty model is still the required shape."""

    model_config = ConfigDict(frozen=True, extra="forbid")


def register(registrar: PackRegistrar, settings: Settings) -> None:
    """Register `TextExtractor` as `"text"` for `Extractor`. The only plugin this pack ships."""
    del settings
    registrar.add(Extractor, "text", TextExtractor)


__all__ = [
    "EXTENSIONS",
    "EXTRACTOR_CONTRACT_VERSION",
    "Extractor",
    "Settings",
    "SourceDoc",
    "TextExtractor",
    "TextExtractorConfig",
    "discover_source_docs",
    "register",
]
