"""First-party chunking pack.

Publishes the `Chunker` contract, in `contract.py` — the Protocol and its
version, per the canonical-file convention `docs/07-extension-cost.md` §1
sets for a brand new contract. Registered through the public entry point,
with no shortcut a third party lacks — fitness function 2. `register()` and
the built-in fixed-size chunker (`fixed_size.py`) arrive at
`docs/06-phase-0-build.md` step 8.

**`ChunkOffset` is not registered for rehydration here, on purpose.** Every chunk this
pack derives now carries it (`fixed_size.py`'s module docstring, ledger 2.9), and
`weft_store.rehydrate` needs a namespace registered before it can read one back — but
this distribution does not depend on `weft-store` to make that call itself, exactly the
choice `weft_pdf.__init__` records for `PdfPages` and for the same reason: fitness
function 9(a) proves a stranger can extend this pack from a wheel install carrying
`weft-kernel` and `weft-chunk` alone, and a hard dependency on the store contract would
make that wheel uninstallable wherever `weft-store` is not also on the index. The call
is made once, by `weft_cli.registry_bootstrap`, which already depends on both and is
where the two ends of a real pipeline — the pack that derives the data and the store
that must read it back — are already required to meet.
"""

from pydantic import BaseModel, ConfigDict

from weft_chunk.contract import CHUNKER_CONTRACT_VERSION, Chunker
from weft_chunk.fixed_size import FixedSizeChunker, FixedSizeChunkerConfig
from weft_chunk.payload import ChunkOffset
from weft_chunk.property import WordBoundaries
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
    "ChunkOffset",
    "Chunker",
    "FixedSizeChunker",
    "FixedSizeChunkerConfig",
    "Settings",
    "WordBoundaries",
    "register",
]
