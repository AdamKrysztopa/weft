"""First-party embedding pack.

Publishes the `Embedder` contract, in `contract.py`, and registers
`HashEmbedder` (`hash_embedder.py`) — a deterministic local embedder that is
**not a quality component**, per `docs/06-phase-0-build.md` step 8. This
pack exists at all because of a forced conclusion, not a design choice: G4
forbids a `Store` from embedding, G2 has not placed the embed step, and a
walking skeleton must not need a model download or an API key to prove that
indexing produces stored nodes.

Registered through the same public `weft.packs` entry point any third-party
pack uses — fitness function 2 — with no shortcut for being first-party.
"""

from pydantic import BaseModel, ConfigDict

from weft_embed.contract import EMBEDDER_CONTRACT_VERSION, Embedder
from weft_embed.hash_embedder import HashEmbedder, HashEmbedderConfig
from weft_kernel.discovery import PackRegistrar


class Settings(BaseModel):
    """`weft-embed` takes no pack settings — an empty model is still the required shape."""

    model_config = ConfigDict(frozen=True, extra="forbid")


def register(registrar: PackRegistrar, settings: Settings) -> None:
    """Register `HashEmbedder` as `"hash"` for `Embedder`. The only plugin this pack ships."""
    del settings
    registrar.add(Embedder, "hash", HashEmbedder)


__all__ = [
    "EMBEDDER_CONTRACT_VERSION",
    "Embedder",
    "HashEmbedder",
    "HashEmbedderConfig",
    "Settings",
    "register",
]
