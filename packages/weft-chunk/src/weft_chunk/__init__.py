"""First-party chunking pack.

Publishes the `Chunker` contract, in `contract.py` — the Protocol and its
version, per the canonical-file convention `docs/07-extension-cost.md` §1
sets for a brand new contract. Registered through the public entry point,
with no shortcut a third party lacks — fitness function 2. `register()` and
the built-in fixed-size chunker (`fixed_size.py`) arrive at
`docs/06-phase-0-build.md` step 8.
"""

from pydantic import BaseModel, ConfigDict

from weft_chunk.contract import CHUNKER_CONTRACT_VERSION, Chunker
from weft_chunk.fixed_size import FixedSizeChunker, FixedSizeChunkerConfig
from weft_kernel.discovery import PackRegistrar


class Settings(BaseModel):
    """`weft-chunk` takes no pack settings — an empty model is still the required shape."""

    model_config = ConfigDict(frozen=True, extra="forbid")


def register(registrar: PackRegistrar, settings: Settings) -> None:
    """Register `FixedSizeChunker` as `"fixed-size"` for `Chunker` — the only plugin here."""
    del settings
    registrar.add(Chunker, "fixed-size", FixedSizeChunker)


__all__ = [
    "CHUNKER_CONTRACT_VERSION",
    "Chunker",
    "FixedSizeChunker",
    "FixedSizeChunkerConfig",
    "Settings",
    "register",
]
