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

from weft_embed.contract import EMBED_ROLE, EMBEDDER_CONTRACT_VERSION, Embedder
from weft_embed.hash_embedder import HashEmbedder, HashEmbedderConfig
from weft_kernel.discovery import Disclosure, PackRegistrar


class Settings(BaseModel):
    """`weft-embed` takes no pack settings — an empty model is still the required shape."""

    model_config = ConfigDict(frozen=True, extra="forbid")


#: `R17.2` — a pack that touches nothing still owes a disclosure, because `weft plugins doctor`
#: is the operator surface and `disclosure: not disclosed` was what it printed for the one pack
#: whose *default* needs a sentence: `hash` derives every vector from a content digest, and a
#: ranking built from it means nothing an operator should trust without being told so. The trade
#: the default makes is argued at `weft_cli/services.py:27 '`hash` stays the default'`.
DISCLOSURE = Disclosure(
    network=(),
    filesystem=(),
    subprocess=(),
    note=(
        "hash is the default embedder, and the default exists so a clean checkout runs offline "
        "with no account: a deliberate trade rather than an oversight. Every component of the "
        "vector it produces is a SHA-256 digest of the node's content, so the vector carries no "
        "semantic similarity at all — two passages about the same subject sit no closer "
        "together than two about unrelated ones. A retrieval result ranked with it therefore "
        "says that the pipeline ran end to end, and says nothing about relevance. Switching it "
        "is one key, [services] embed in weft.toml, to a registered plugin such as "
        "openai-embeddings or openai-compatible-embeddings."
    ),
)

#: Ledger task **9.0** — read by `weft_kernel.discovery._read_service_roles` at import time,
#: before settings are validated, exactly where `DISCLOSURE` is read. Module-level rather than
#: buffered through `register()` because which `[services]` key this pack declares is a static
#: fact about the pack: a pack whose settings fail must still be able to tell an operator that
#: its role key exists, or the refusal names the wrong problem.
SERVICE_ROLES = (EMBED_ROLE,)


def register(registrar: PackRegistrar, settings: Settings) -> None:
    """Register `HashEmbedder` as `"hash"` for `Embedder`, and declare `[services].embed`
    selectable — ledger task **9.0**. The only plugin this pack ships.
    """
    del settings
    registrar.add(Embedder, "hash", HashEmbedder)


__all__ = [
    "DISCLOSURE",
    "EMBEDDER_CONTRACT_VERSION",
    "EMBED_ROLE",
    "Embedder",
    "HashEmbedder",
    "HashEmbedderConfig",
    "Settings",
    "register",
]
