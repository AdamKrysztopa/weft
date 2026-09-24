"""What an ingest run into a pipeline would cost in vectors and bytes — ledger task **31.8**.

An operator about to index a large corpus wants to know what it will cost in storage *before*
paying for it. `weft pipeline estimate <pipeline> <sample>` answers that by chunking a small
sample, measuring the chunks-per-document rate the sample produced, and scaling it — then
multiplying by the vector width and the bytes each component takes at the configured precision.

**It spends no model call.** Not "it tries not to" — `weft_cli.pipeline_commands.
PipelineEstimateCommand` runs the sample's ingest stages through `weft_engine.run_services.
build_index_services(..., offer_models=False)`, which registers neither `LLM` nor `Prompts` at
all. A stage that reaches for either gets `weft_kernel.context.UnresolvedServiceError` naming
what the run does offer. `Projection.model_calls` is `0` because the run proves it, not because
this module asserts it.

**Every number names the assumption under it.** Where the width comes from configuration, it is
a reading. Where configuration leaves it to the model — OpenAI's `dimensions` unset — it is an
assumption, and `Projection.width_assumption` is the field that names it rather than a sentence
nobody can assert on. What a sample cannot reveal at all — payload, text, the write-ahead log —
is listed in `Projection.unknowns` rather than silently omitted or reported as zero: zero means
"this costs nothing," `None`/absence means "nobody measured this," and an operator provisioning
storage needs to tell them apart.

**The measured index overheads are citations, not constants this module invented.** Phase 29
took them on 100,142 real `text-embedding-3-large` chunks at width 1536, kept in
`docs/internal/evidence/phase-29/`. `MEASURED_INDEX_BYTES_PER_VECTOR` writes the arithmetic —
the published byte count divided by the row count it was taken over — so the provenance stays
readable in the code rather than living only in a summary. `EXACT` has no entry: it builds no
index, so there is no overhead to have measured, and absent is not the same as zero.

**`store_index_kind`/`store_precision` are declared, never required** — the same `getattr`
idiom `weft_cli.explain` uses for `score_semantics`, and for the reason that module's own
docstring states: a `ClassVar` inside a `@runtime_checkable` Protocol body becomes a *required*
`isinstance` member, so turning this into a capability Protocol would start refusing third-party
stores over a documentation question. A store declaring neither reports its own overhead as
unknown rather than being refused, and rather than this module guessing on its behalf.
"""

from __future__ import annotations

from collections.abc import Mapping

from pydantic import BaseModel, ConfigDict

from weft_store.contract import VectorIndexKind, VectorPrecision

#: One component's storage cost at each precision — task **31.8**'s own vocabulary check:
#: `test_every_precision_in_the_vocabulary_has_a_component_size` asserts this is *complete*
#: against `VectorPrecision`, so a precision silently missing here reports as zero bytes rather
#: than as a caught gap. `BINARY` is **0.125** — one *bit* per component, from
#: `binary_quantize` — not one byte; reading it as a byte overstates a binary index eightfold,
#: which is exactly the direction that makes an operator provision hardware they do not need.
BYTES_PER_COMPONENT: Mapping[VectorPrecision, float] = {
    VectorPrecision.FLOAT32: 4,
    VectorPrecision.FLOAT16: 2,
    VectorPrecision.INT8: 1,
    VectorPrecision.BINARY: 0.125,
}

#: Phase 29's measured index sizes, divided by the 100,142 rows they were taken over on
#: `text-embedding-3-large` at width 1536 — the arithmetic is written out, not the quotient, so
#: the provenance stays in the code. `EXACT` has **no entry at all**: it builds no index, so
#: there is no per-vector overhead to have measured.
MEASURED_INDEX_BYTES_PER_VECTOR: Mapping[tuple[VectorIndexKind, VectorPrecision], float] = {
    # `run-29.7.json`
    (VectorIndexKind.HNSW, VectorPrecision.FLOAT32): 818_913_280 / 100_142,
    # `run-29.8.json`
    (VectorIndexKind.HNSW, VectorPrecision.FLOAT16): 409_501_696 / 100_142,
    (VectorIndexKind.HNSW, VectorPrecision.BINARY): 50_151_424 / 100_142,
    # `run-29.9.json`
    (VectorIndexKind.DISKANN, VectorPrecision.FLOAT32): 68_386_816 / 100_142,
}

#: What a sample of a few dozen documents cannot reveal at all, named rather than omitted or
#: reported as zero. Payload and text are per-row costs on a real server that no chunking pass
#: measures, and the write-ahead log is a property of how the database writes, not of what was
#: written.
UNMEASURABLE_FROM_A_SAMPLE: tuple[str, ...] = ("payload", "text", "WAL")


class Projection(BaseModel):
    """One pipeline's projected vector count and byte cost for a stated corpus size.

    Frozen, `extra="forbid"`: every field a caller might want is here or is not knowable, and a
    later field being read off a stale attribute name would fail loudly rather than reading
    `None` and looking like an honest unknown.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    pipeline: str
    store: str
    width: int
    width_assumption: str | None
    index_kind: VectorIndexKind | None
    precision: VectorPrecision | None
    sample_documents: int
    sample_chunks: int
    projected_documents: int
    chunks_per_document: float
    projected_vectors: int
    vector_bytes: int
    rescoring_original_bytes: int
    index_bytes: int | None
    unknowns: tuple[str, ...]
    model_calls: int


def project(
    *,
    pipeline: str,
    sample_documents: int,
    sample_chunks: int,
    documents: int,
    width: int,
    width_assumption: str | None,
    store: str,
    index_kind: VectorIndexKind | None,
    precision: VectorPrecision | None,
) -> Projection:
    """Scale a sample's own chunking rate to a stated corpus size, and cost the result.

    Raises `ValueError`, naming "sample", for a sample that produced zero documents or zero
    chunks: scaling from it is a division by zero dressed as a projection, and "0 vectors for
    100,000 documents" is a plausible answer against the wrong data — the silent fallback `01`
    refuses.
    """
    if sample_documents <= 0 or sample_chunks <= 0:
        raise ValueError(
            f"the sample produced {sample_chunks} chunk(s) from {sample_documents} document(s); "
            "a projection needs a sample with at least one document and one chunk to derive a "
            "chunks-per-document rate from."
        )

    chunks_per_document = sample_chunks / sample_documents
    projected_vectors = int(chunks_per_document * documents)

    component_bytes = BYTES_PER_COMPONENT[precision] if precision is not None else None
    vector_bytes = (
        int(projected_vectors * width * component_bytes) if component_bytes is not None else 0
    )
    rescoring_original_bytes = (
        projected_vectors * width * 4
        if precision in (VectorPrecision.INT8, VectorPrecision.BINARY)
        else 0
    )

    per_vector_index_bytes = (
        MEASURED_INDEX_BYTES_PER_VECTOR.get((index_kind, precision))
        if index_kind is not None and precision is not None
        else None
    )
    index_bytes = (
        int(per_vector_index_bytes * projected_vectors)
        if per_vector_index_bytes is not None
        else None
    )

    return Projection(
        pipeline=pipeline,
        store=store,
        width=width,
        width_assumption=width_assumption,
        index_kind=index_kind,
        precision=precision,
        sample_documents=sample_documents,
        sample_chunks=sample_chunks,
        projected_documents=documents,
        chunks_per_document=chunks_per_document,
        projected_vectors=projected_vectors,
        vector_bytes=vector_bytes,
        rescoring_original_bytes=rescoring_original_bytes,
        index_bytes=index_bytes,
        unknowns=UNMEASURABLE_FROM_A_SAMPLE,
        model_calls=0,
    )


def store_index_kind(store: object) -> VectorIndexKind | None:
    """`store`'s declared index kind, or `None` — declared, never required.

    See the module docstring's own paragraph on why this is `getattr`, not a capability Protocol.
    """
    declared = getattr(store, "vector_index_kind", None)
    return declared if isinstance(declared, VectorIndexKind) else None


def store_precision(store: object) -> VectorPrecision | None:
    """Let a storage projection size vectors only when the store states their precision.

    `store`'s declared vector precision, or `None` — `store_index_kind`'s own reasoning,
    one attribute over.
    """
    declared = getattr(store, "vector_precision", None)
    return declared if isinstance(declared, VectorPrecision) else None


__all__ = [
    "BYTES_PER_COMPONENT",
    "MEASURED_INDEX_BYTES_PER_VECTOR",
    "UNMEASURABLE_FROM_A_SAMPLE",
    "Projection",
    "project",
    "store_index_kind",
    "store_precision",
]
