"""`ExampleChecksumEmbedder` — a stranger's `Embedder`. **Not a quality embedder.**

The counterpart to `weft_embed.hash_embedder.HashEmbedder`, written fresh rather than
reused: a third-party embedder pack is not expected to depend on `weft-embed` at all, so
this one carries its own deterministic, content-hashed vector — one SHA-256 digest per
component, salted by the component's own index, so the same content always hashes to the
same vector. It carries no semantic understanding of content whatsoever; two documents
about unrelated topics that happen to hash to nearby components are not "similar" in any
sense a retrieval strategy should trust. This exists only so the pack's own `InMemoryNodeStore`
has a real `Vector` to rank by, produced by a real stage, with no model download and no API
key standing between a clean checkout and this pack's own tests passing.
"""

import hashlib
from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict, model_validator

from weft_kernel.context import Context
from weft_kernel.payload import Node, NothingToProduce, Outcome, Produced, Vector

_DEFAULT_DIMENSION = 32


class ExampleEmbedderConfig(BaseModel):
    """`ExampleChecksumEmbedder`'s `with:` config — one real field, defaulted."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    dimension: int = _DEFAULT_DIMENSION

    @model_validator(mode="after")
    def _dimension_is_positive(self) -> "ExampleEmbedderConfig":
        if self.dimension < 1:
            raise ValueError(f"dimension must be at least 1 — got {self.dimension}")
        return self


class ExampleChecksumEmbedder:
    """Attaches a deterministic, content-hashed `Vector` to every node it is handed.

    Satisfies `weft_embed.contract.Embedder` structurally — this class never imports it.
    """

    def __init__(self, config: ExampleEmbedderConfig | None = None) -> None:
        self._config = config if config is not None else ExampleEmbedderConfig()

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        del ctx
        if not payload:
            return NothingToProduce(reason="no node to embed")
        dimension = self._config.dimension
        embedded = [node.with_embedding(_vector(node.content, dimension)) for node in payload]
        return Produced(value=embedded)


def _vector(content: str, dimension: int) -> Vector:
    """One SHA-256-derived component per dimension — deterministic, never semantic."""
    components = tuple(
        int.from_bytes(hashlib.sha256(f"{index}:{content}".encode()).digest()[:4], "big") / 2**32
        for index in range(dimension)
    )
    return Vector(values=components)
