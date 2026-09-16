"""`weft-qdrant`'s pack settings: one Qdrant deployment, and the two facts it fixes in advance.

The same distinction `weft_store.pgvector_store` draws for its connection string
and `docs/02-extension-model.md` §2 draws for the graph pack's
`endpoint`/`api_key`: a deployment is one resource everything this pack registers
reaches through, not a per-pipeline-stage tuning knob.

**Every field has a default, and that is load-bearing rather than tidy.** Pack
settings are validated *before* `register()` runs, so one required field turns a
machine with no Qdrant configured into a pack that reports `failed` with nothing
contributed — and a plugin that is not in the registry is not in
`manual/contract-reference.md`, not in fitness function 11(b)'s resolution check,
and not in anything else that walks what is installed. Nothing fails; the
capability simply is not there. So the URL defaults to the one `compose.yaml`
publishes and a deployment that is not running is discovered at *use*, by the
driver, naming the address it could not reach.
"""

from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator

from weft_store.contract import VectorIndexKind, VectorPrecision


class QdrantSettings(BaseModel):
    """Where Qdrant is, what to call the collections, and how wide a vector is."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: The default is what `compose.yaml`'s `qdrant` service publishes, so a developer who
    #: brought the conformance profile up needs no `weft.toml` at all.
    url: str = "http://localhost:6333"

    #: Empty means an unauthenticated deployment, which is what a local container is. A
    #: managed one wants `${env:QDRANT_API_KEY}` here, the spelling `weft.toml.example`
    #: shows — the secret stays in the environment and the file names the variable.
    api_key: SecretStr = SecretStr("")

    #: The collection holding nodes. Source records live in a second collection named after
    #: it (see `weft_qdrant.store.QdrantStore`) — Qdrant has no second table inside one
    #: collection, and a `SourceRecord` is not a `Node`.
    collection: str = Field(default="weft_nodes", min_length=1)

    #: **The one place this backend's shape is visibly different from Postgres's, and it is
    #: a setting because it has to be.** A pgvector column is declared without a dimension;
    #: a Qdrant collection fixes its vector width at creation and cannot change it. So the
    #: width the configured embedder produces has to be stated *before* the first node is
    #: written, rather than discovered from it. The default is `weft-embed`'s hash
    #: embedder's, which is what a laptop run uses; `text-embedding-3-small` is 1536, and a
    #: node whose embedding disagrees with this is refused by name rather than truncated.
    vector_size: int = Field(default=64, ge=1)

    #: Whole seconds the driver waits on one request — whole because the driver's own
    #: parameter is an `int`, and accepting a fraction here would mean silently rounding
    #: an operator's number. Unset leaves the driver's default in force, which is not the
    #: same as passing `None` — that would mean no timeout at all.
    timeout_seconds: int | None = Field(default=None, gt=0)

    #: **A disclosed approximation, ledger `21.8`.** `256.0` is Qdrant's own BM25 default,
    #: not the mean length of anybody's corpus — this store has no way to measure the real
    #: one, because collection IDF updates as documents arrive while a document's own
    #: length-normalisation weight is computed once, when its point is written, and never
    #: revisited. Leaving this at the default is a choice, the same as setting it: either
    #: way an operator has seen the number rather than inherited it silently.
    bm25_avg_doc_len: float = Field(default=256.0, gt=0)

    #: Which vector index this store's collection is built under — task **31.2**.
    #:
    #: **`hnsw`, not pgvector's `exact` default.** Qdrant has always built an HNSW index once a
    #: segment passes its own threshold, so `hnsw` records what this backend already does rather
    #: than changing it; `exact` is the opt-in that forces a full scan per search.
    index: VectorIndexKind = VectorIndexKind.HNSW

    #: Which precision the collection's vectors are held at — task **31.2**, the owner's Q2 rule:
    #: float32 stays default until a persisted `weft eval` run puts a compressed arm inside the
    #: baseline interval. Phase 29 measured compression on pgvector only.
    precision: VectorPrecision = VectorPrecision.FLOAT32

    @staticmethod
    def served_precisions() -> tuple[str, ...]:
        """Every precision this backend can hold — the whole closed vocabulary.

        Unlike pgvector, Qdrant serves all four: `float16` is a vector `datatype`, `int8` is
        `ScalarQuantizationConfig`, `binary` is `BinaryQuantizationConfig`, and `float32` is the
        absence of all of it.
        """
        return tuple(precision.value for precision in VectorPrecision)

    @model_validator(mode="after")
    def _reject_unsupported_index(self) -> "QdrantSettings":
        """Refuse an index kind Qdrant does not serve, naming what it does.

        `01` requirement 5 applied to `index`: `diskann` is a real `VectorIndexKind` — pgvector
        does not serve it either without the `vectorscale` extension — but Qdrant builds nothing
        for it and uses HNSW as its only dense vector index.

        The refusal class lives in `weft_store.contract`, shared with the pgvector store — task
        **31.12**. `valid_options` is what *this* backend serves, which is not what the other one
        serves: the shared class fixes the shape of the refusal, never its answer. Still imported
        inside the function rather than at module scope, because this module is imported during
        pack settings validation and `weft_store.contract` pulls in the whole store family.
        """
        from weft_store.contract import UnsupportedIndexKindError

        served = (VectorIndexKind.EXACT, VectorIndexKind.HNSW)
        if self.index not in served:
            valid_options = tuple(kind.value for kind in served)
            raise UnsupportedIndexKindError(
                f"[packs.qdrant] index '{self.index.value}' is not served by Qdrant. It "
                f"serves: {', '.join(valid_options)}.",
                valid_options=valid_options,
                pack="weft-qdrant",
            )
        return self

    @model_validator(mode="after")
    def _reject_unsupported_precision(self) -> "QdrantSettings":
        """Refuse a precision this backend cannot hold, naming what it does.

        Unreachable today — `served_precisions()` is every `VectorPrecision` member, so nothing
        this enum names can trip it. Kept for the shape: a future member added to the shared
        vocabulary without a corresponding Qdrant encoding would otherwise fall through to the
        driver with no refusal at all.
        """
        from weft_store.contract import UnsupportedPrecisionError

        served = self.served_precisions()
        if self.precision.value not in served:
            raise UnsupportedPrecisionError(
                f"[packs.qdrant] precision '{self.precision.value}' is not served by Qdrant. "
                f"It serves: {', '.join(served)}.",
                valid_options=served,
                pack="weft-qdrant",
            )
        return self
