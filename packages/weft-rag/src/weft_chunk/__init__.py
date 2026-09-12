"""First-party chunking pack.

Publishes the `Chunker` contract, in `contract.py` — the Protocol and its
version, per the canonical-file convention `docs/07-extension-cost.md` §1
sets for a brand new contract. Registered through the public entry point,
with no shortcut a third party lacks — fitness function 2. `register()` and
the built-in fixed-size chunker (`fixed_size.py`) arrive at
`docs/06-phase-0-build.md` step 8.

**This pack contributes no `ExtModel`, and that is a withdrawal rather than an absence —
repair `R17.1`, 2026-09-12.** `weft_chunk.payload.ChunkOffset` was registered here through
`registrar.add_ext_model` (task 5.2g), and **G17** retired its only reader: a page stopped
being resolved through an offset and became a scalar fact on the node it describes. A field
a persisted record carries and nothing renders is deleted (`R9.11`'s rule), so it was. The
mechanism is untouched and a future ext model reaches rehydration the same way — `register()`
calls `registrar.add_ext_model(...)`, `weft_store.rehydrate.register_from_reports` walks
`PackReport.ext_models` generically from whatever already calls `discover()`, and no pack is
named at that call site.
"""

from pydantic import BaseModel, ConfigDict

from weft_chunk.contract import CHUNKER_CONTRACT_VERSION, Chunker
from weft_chunk.fixed_size import FixedSizeChunker, FixedSizeChunkerConfig
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


__all__ = [
    "CHUNKER_CONTRACT_VERSION",
    "Chunker",
    "FixedSizeChunker",
    "FixedSizeChunkerConfig",
    "Settings",
    "TableRowChunker",
    "TableRowChunkerConfig",
    "WordBoundaries",
    "register",
]
