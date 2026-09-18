"""First-party chunking pack.

Publishes the `Chunker` contract, in `contract.py` — the Protocol and its
version, per the canonical-file convention `docs/07-extension-cost.md` §1
sets for a brand new contract. Registered through the public entry point,
with no shortcut a third party lacks — fitness function 2. `register()` and
the built-in fixed-size chunker (`fixed_size.py`) arrive at
`docs/06-phase-0-build.md` step 8.

**This pack contributes `ChunkPosition`, back at ledger `32.1` after `R17.1` withdrew its
predecessor.** `R17.1`'s rule — a field a persisted record carries and nothing renders is
deleted — is met again within Phase 32, by two readers in the same phase: `32.3`'s
`adjacent-chunks` reads a hit's siblings by ordinal through the store's Filter AST built at
`32.2`. `register()` calls `registrar.add_ext_model(ChunkPosition)`, and
`weft_store.rehydrate.register_from_reports` walks `PackReport.ext_models` generically from
whatever already calls `discover()` — no pack is named at that call site.
"""

from pydantic import BaseModel, ConfigDict

from weft_chunk.contract import CHUNKER_CONTRACT_VERSION, Chunker
from weft_chunk.fixed_size import FixedSizeChunker, FixedSizeChunkerConfig
from weft_chunk.payload import ChunkPosition
from weft_chunk.property import WordBoundaries
from weft_chunk.table_rows import TableRowChunker, TableRowChunkerConfig
from weft_kernel.discovery import PackRegistrar


class Settings(BaseModel):
    """`weft-chunk` takes no pack settings — an empty model is still the required shape."""

    model_config = ConfigDict(frozen=True, extra="forbid")


def register(registrar: PackRegistrar, settings: Settings) -> None:
    """Register `FixedSizeChunker` as `"fixed-size"` and `TableRowChunker` as `"table-rows"`
    for `Chunker` — see `weft_chunk.table_rows` for `"table-rows"`, ledger task `9.14`.
    """
    del settings
    registrar.add(Chunker, "fixed-size", FixedSizeChunker)
    registrar.add(Chunker, "table-rows", TableRowChunker)
    registrar.add_ext_model(ChunkPosition)


__all__ = [
    "CHUNKER_CONTRACT_VERSION",
    "ChunkPosition",
    "Chunker",
    "FixedSizeChunker",
    "FixedSizeChunkerConfig",
    "Settings",
    "TableRowChunker",
    "TableRowChunkerConfig",
    "WordBoundaries",
    "register",
]
