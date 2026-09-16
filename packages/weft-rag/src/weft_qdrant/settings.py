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

from collections.abc import Mapping
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator

from weft_store.contract import VectorIndexKind, VectorPrecision


class PayloadIndexType(StrEnum):
    """The payload index kinds an operator may declare — task **31.1**.

    A Weft-side vocabulary rather than the client's `models.PayloadSchemaType` re-exported, so a
    pack's settings do not carry a driver type across the seam. Each maps onto exactly one member
    of that enum: `KEYWORD`, `INTEGER`, `FLOAT`.
    """

    KEYWORD = "keyword"
    INTEGER = "integer"
    FLOAT = "float"


#: The one filter this store issues itself, unconditionally — `delete_source` on every delete,
#: `reconcile` on every pass. Every other key is the operator's to declare. Public — not just a
#: default in shape, but a guarantee `weft_qdrant.store` folds in again at index-creation time,
#: so the key is indexed even against a `QdrantSettings` built by `model_copy`, which does not
#: re-run `_merge_and_validate_payload_indexes`.
DEFAULT_PAYLOAD_INDEXES: Mapping[str, PayloadIndexType] = {
    "lineage.sources": PayloadIndexType.KEYWORD
}


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

    #: How many extra candidates the quantized index is asked for per requested result, before
    #: the winners are rescored against the full-precision vectors — task **31.3**. `None` leaves
    #: Qdrant's own default (`1.0`) in force, and that is deliberate rather than an omission:
    #: Phase 29 measured no oversampling arm on this backend at all, so no number here would be
    #: earned by anything more than a guess. `float`, because Qdrant's own documented example
    #: uses `2.4`; `ge=1.0` because oversampling multiplies `top_k`, so a value below 1 would ask
    #: the quantized index for fewer candidates than the caller wants results back.
    rescore_oversampling: float | None = Field(default=None, ge=1.0)

    #: The optimizer's own `indexing_threshold`, in points — task **31.5**. `None` leaves Qdrant's
    #: default (20,000) in force, and that is not the same as passing `0`: Qdrant's own
    #: documentation defines `0` as *disabling* indexing entirely, so a caller who wants an index
    #: on a small collection reaches for it and gets the opposite. A small positive value — the
    #: conformance kit's approximate-regime fixture uses `1` — is what forces the optimizer to
    #: build an HNSW segment well below the point count it would otherwise wait for, which is the
    #: only way a test collection of a few hundred points ever leaves the exact-search regime.
    indexing_threshold: int | None = Field(default=None, ge=1)

    #: Every key filtered against Qdrant needs a payload index created **before** the first
    #: point is written — task **31.1**: filterable-HNSW edges are generated only for data
    #: indexed after the payload index exists, so an index created later still answers filters
    #: but the graph it needed was already built without it. `lineage.sources` is in the default
    #: because this store filters on it itself, unconditionally, on every `delete_source` and
    #: `reconcile` call; an operator's own map is merged with that default, never replacing it.
    #: `content` is deliberately absent — it is addressable and admits `eq`, but a keyword index
    #: over whole chunk text is paid for on every write and no filter Weft ships asks for it.
    payload_indexes: Mapping[str, PayloadIndexType] = Field(
        default_factory=lambda: dict(DEFAULT_PAYLOAD_INDEXES)
    )

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

    @model_validator(mode="after")
    def _merge_and_validate_payload_indexes(self) -> "QdrantSettings":
        """Merge the operator's map with the store's own filter's index, and refuse a bad key.

        The default is folded in rather than overwritten, so a declared map can never drop the
        index `delete_source` and `reconcile` depend on. Every resulting key is checked through
        `parse_field_path` — the same function the filter translator uses — so an operator cannot
        declare an index for a path no `Filter` could ever address; imported inside the function
        for the reason the two validators above already give.
        """
        from weft_store.fields import parse_field_path

        merged: dict[str, PayloadIndexType] = {
            **DEFAULT_PAYLOAD_INDEXES,
            **self.payload_indexes,
        }
        for field in merged:
            parse_field_path(field)
        object.__setattr__(self, "payload_indexes", merged)
        return self
