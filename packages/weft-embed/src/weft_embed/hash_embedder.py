"""`HashEmbedder` — a deterministic, content-hashed vector. **Not a quality embedder.**

Specified in `docs/06-phase-0-build.md` step 8: "Phase 0 ships a deterministic
local embedder (hashing to a fixed-dimension vector) whose only job is to be
a real vector produced by a real stage. It is not a quality component and
its docstring should say so." This is that docstring, said plainly: `HashEmbedder`
carries no semantic understanding of content whatsoever. Two documents about
unrelated topics that happen to hash to nearby components are not "similar"
in any sense a retrieval strategy should trust — this class exists only so
that Phase 0's ingest pipeline has a real `Vector`, produced by a real stage,
flowing into a real `NodeStore.search_vector` call, with no model download
and no API key standing between a clean checkout and a passing test. Replace
it with a real embedding model before trusting a single retrieval result
against it.

**Deterministic by construction, not by convention.** Every component is a
SHA-256 digest of the node's content concatenated with that component's own
index, so the same content always hashes to the same vector — required for
`weft index`'s re-index-is-idempotent property (`docs/02-extension-model.md`
→ *Identity is a content-addressed digest*) to hold all the way through
storage, not just at the `Node` layer. It is not, and must never become,
a hash-based *approximation* of semantic similarity: nothing here reads
tokens, n-grams or any structure in `content` at all.

**Configuration is `dimension`, and nothing else.** No model name, no API
endpoint, no batching knob — there is no model to name, and pretending
otherwise (a `model: "text-embedding-3-small"` field that is silently
ignored) would be exactly the kind of plausible-but-false configuration
surface the project's catch-specific-exceptions rule already refuses at the
error-handling layer. `dimension` is real: it is the length of the vector
this stage actually produces.
"""

import hashlib
from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict, model_validator

from weft_kernel.context import Context
from weft_kernel.payload import Node, NothingToProduce, Outcome, Produced, Vector

#: Matches `weft-store`'s pgvector column, which is declared without a fixed
#: dimension — see `docs/06-phase-0-build.md` step 8 and `weft_store.pgvector_store`.
#: Any positive dimension works; this is only the default a `with:` block may omit.
_DEFAULT_DIMENSION = 64

#: The width of the slice of each SHA-256 digest this module turns into one component.
_UINT64_RANGE = 2**64


class HashEmbedderConfig(BaseModel):
    """`HashEmbedder`'s `with:` config — one real field. See the module docstring for why."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    dimension: int = _DEFAULT_DIMENSION

    @model_validator(mode="after")
    def _dimension_is_positive(self) -> "HashEmbedderConfig":
        if self.dimension < 1:
            raise ValueError(
                f"dimension must be at least 1 — a Vector cannot be empty (got {self.dimension})"
            )
        return self


class HashEmbedder:
    """Attaches a deterministic, content-hashed `Vector` to every node it is handed.

    **Not a quality component** — see the module docstring. Satisfies
    `weft_embed.contract.Embedder` structurally: this class never imports it,
    the same path every third-party embedder pack is expected to take.
    """

    def __init__(self, config: HashEmbedderConfig | None = None) -> None:
        self._config = config if config is not None else HashEmbedderConfig()

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        del ctx  # no service or locale this stage needs
        if not payload:
            return NothingToProduce(reason="no nodes to embed")
        embedded = [
            node.with_embedding(_hash_vector(node.content, self._config.dimension))
            for node in payload
        ]
        return Produced(value=embedded)


def _hash_vector(content: str, dimension: int) -> Vector:
    """`dimension` components, each a deterministic function of `content` and its own index."""
    encoded = content.encode("utf-8")
    components = tuple(_component(encoded, index) for index in range(dimension))
    return Vector(values=components)


def _component(encoded: bytes, index: int) -> float:
    """One component: a SHA-256 digest of `encoded` and `index`, mapped onto `[-1.0, 1.0)`."""
    digest = hashlib.sha256(encoded + index.to_bytes(4, byteorder="big")).digest()
    raw = int.from_bytes(digest[:8], byteorder="big")
    return (raw / _UINT64_RANGE) * 2.0 - 1.0
