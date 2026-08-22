"""First-party chunking pack.

Publishes the `Chunker` contract, in `contract.py` — the Protocol and its
version, per the canonical-file convention `docs/07-extension-cost.md` §1
sets for a brand new contract. Registered through the public entry point,
with no shortcut a third party lacks — fitness function 2. `register()` and
the built-in fixed-size chunker (`fixed_size.py`) arrive at
`docs/06-phase-0-build.md` step 8.

**`ChunkOffset` reaches rehydration through `register()` itself, with no `weft-store`
dependency here at all — task 5.2g.** `register()` calls `registrar.add_ext_model
(ChunkOffset)`, exactly the way it calls `registrar.add(Chunker, ...)` for a plugin:
`PackRegistrar` lives in `weft-kernel`, and `ExtModel` is a kernel-owned payload
primitive, not a capability, so this costs the dependency this module used to refuse
nothing at all — fitness function 9(a) still proves a stranger can extend this pack from
a wheel install carrying `weft-kernel` and `weft-chunk` alone. What actually walks
`PackReport.ext_models` back into `weft_store.rehydrate.ext_models` is
`weft_store.rehydrate.register_from_reports`, called once, generically, by whatever
already calls `discover()` — `weft_cli.registry_bootstrap.build_dependencies` today —
with no pack named at that call site and no further edit owed to it by a future pack.
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
    """Register `FixedSizeChunker` as `"fixed-size"` for `Chunker`, and `ChunkOffset` as this
    pack's own `ExtModel` — task 5.2g, see the module docstring.
    """
    del settings
    registrar.add(Chunker, "fixed-size", FixedSizeChunker)
    registrar.add_ext_model(ChunkOffset)


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
