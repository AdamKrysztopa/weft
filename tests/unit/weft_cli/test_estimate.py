"""Unit tests for `weft_cli.estimate` — task **31.8**.

Mirrors `packages/weft-rag/src/weft_cli/estimate.py`. Everything here is a pure function over
numbers a caller already has, which is the whole point of the task: the projection is arithmetic,
and the only part that needs a running system is counting the sample's chunks. Splitting it this
way is what lets the assumptions be asserted rather than described — a number whose provenance is
a field on the result can be checked, and one stated in a sentence cannot.

**The measured index overheads are citations, not constants this task invented.** Phase 29 took
them on 100,142 real `text-embedding-3-large` chunks at width 1536, and they are kept in
`docs/internal/evidence/phase-29/`. Per vector: `hnsw`/`float32` 818,913,280 B (`run-29.7.json`),
`hnsw`/`float16` 409,501,696 B and `hnsw`/`binary` 50,151,424 B (`run-29.8.json`), `diskann`/
`float32` 68,386,816 B (`run-29.9.json`). `29.9`'s own note that "bytes and latency transfer from
hash vectors; recall does not" is what licenses dividing them by the row count and bounds it.
"""

from __future__ import annotations

import pytest

from weft_cli.estimate import (
    BYTES_PER_COMPONENT,
    MEASURED_INDEX_BYTES_PER_VECTOR,
    UNMEASURABLE_FROM_A_SAMPLE,
    Projection,
    project,
    store_index_kind,
    store_precision,
)
from weft_store.contract import VectorIndexKind, VectorPrecision


class _DeclaringStore:
    """A store that declares both facts, the way both shipped stores will."""

    vector_index_kind = VectorIndexKind.HNSW
    vector_precision = VectorPrecision.BINARY


class _SilentStore:
    """A store that declares neither — a third party's, or `MemoryStore`.

    It still satisfies `VectorSearch`; what it has no answer for is which *index* it built,
    because it scans its own dicts. Nothing may refuse it and nothing may guess on its behalf.
    """


def test_every_precision_in_the_vocabulary_has_a_component_size() -> None:
    # Arrange / Act / Assert — a projection that silently skipped a precision would report
    # zero bytes for it, which reads as a small index rather than as a missing case. Asserting
    # the mapping is *complete* against the enum is what makes that impossible, rather than
    # asserting the four members someone remembered to write down.
    assert set(BYTES_PER_COMPONENT) == set(VectorPrecision)


def test_binary_is_an_eighth_of_a_byte_per_component_not_one() -> None:
    # Arrange / Act / Assert — the one entry that is not a whole number of bytes, and the one a
    # reasonable person gets wrong: `binary_quantize` yields one *bit* per component. Reading it
    # as a byte overstates a binary index eightfold, which is precisely the direction that would
    # make an operator provision hardware they do not need.
    assert BYTES_PER_COMPONENT[VectorPrecision.BINARY] == pytest.approx(0.125)
    assert BYTES_PER_COMPONENT[VectorPrecision.FLOAT32] == 4
    assert BYTES_PER_COMPONENT[VectorPrecision.FLOAT16] == 2
    assert BYTES_PER_COMPONENT[VectorPrecision.INT8] == 1


def test_an_exact_store_builds_no_index_so_it_has_no_measured_overhead() -> None:
    # Arrange / Act / Assert — `exact` is a full scan, not a cheap index: there is no structure to
    # pay for. Absent from the mapping rather than present as zero, so a caller must decide what
    # "no index" prints instead of reading a zero that could equally mean "unmeasured".
    assert (VectorIndexKind.EXACT, VectorPrecision.FLOAT32) not in MEASURED_INDEX_BYTES_PER_VECTOR


def test_the_measured_overheads_are_phase_29s_own_numbers_per_vector() -> None:
    # Arrange — Phase 29's recorded index_bytes over its own 100,142 rows.
    rows = 100_142

    # Act / Assert — each entry is the published byte count divided by the rows it was taken
    # over, so the figure the estimator multiplies is derivable from the evidence file rather
    # than transcribed from a summary.
    assert MEASURED_INDEX_BYTES_PER_VECTOR[
        (VectorIndexKind.HNSW, VectorPrecision.FLOAT32)
    ] == pytest.approx(818_913_280 / rows, rel=1e-3)
    assert MEASURED_INDEX_BYTES_PER_VECTOR[
        (VectorIndexKind.HNSW, VectorPrecision.FLOAT16)
    ] == pytest.approx(409_501_696 / rows, rel=1e-3)
    assert MEASURED_INDEX_BYTES_PER_VECTOR[
        (VectorIndexKind.HNSW, VectorPrecision.BINARY)
    ] == pytest.approx(50_151_424 / rows, rel=1e-3)
    assert MEASURED_INDEX_BYTES_PER_VECTOR[
        (VectorIndexKind.DISKANN, VectorPrecision.FLOAT32)
    ] == pytest.approx(68_386_816 / rows, rel=1e-3)


def test_a_store_that_declares_its_index_kind_and_precision_is_read() -> None:
    # Arrange / Act / Assert — declared, never required: the same `getattr` idiom
    # `weft_cli.explain` uses for `score_semantics`, for the reason that module states — a
    # `ClassVar` inside a `@runtime_checkable` Protocol body becomes a *required* `isinstance`
    # member, so a capability check would start refusing stores over a documentation question.
    store = _DeclaringStore()

    assert store_index_kind(store) is VectorIndexKind.HNSW
    assert store_precision(store) is VectorPrecision.BINARY


def test_a_store_that_declares_neither_is_an_absence_and_never_a_guess() -> None:
    # Arrange / Act / Assert — `MemoryStore` satisfies `VectorSearch` by scanning its own dicts,
    # and a third party's store need not have an index kind at all. Inventing `exact` on its
    # behalf would be the silent fallback `01` refuses: a plausible answer against the wrong
    # data, indistinguishable from a real one.
    store = _SilentStore()

    assert store_index_kind(store) is None
    assert store_precision(store) is None


def test_the_vector_count_scales_the_samples_own_chunks_per_document() -> None:
    # Arrange — 40 documents chunked into 1,212, projected to 100,000 documents.
    projection = project(
        pipeline="index-text",
        sample_documents=40,
        sample_chunks=1_212,
        documents=100_000,
        width=64,
        width_assumption=None,
        store="pgvector",
        index_kind=VectorIndexKind.EXACT,
        precision=VectorPrecision.FLOAT32,
    )

    # Assert — 1,212 / 40 = 30.3 chunks per document, and the projection is that rate scaled.
    assert isinstance(projection, Projection)
    assert projection.chunks_per_document == pytest.approx(30.3)
    assert projection.projected_vectors == 3_030_000


def test_raw_vector_bytes_are_the_width_times_the_component_size() -> None:
    # Arrange
    projection = project(
        pipeline="index-text",
        sample_documents=40,
        sample_chunks=1_212,
        documents=100_000,
        width=64,
        width_assumption=None,
        store="pgvector",
        index_kind=VectorIndexKind.EXACT,
        precision=VectorPrecision.FLOAT32,
    )

    # Assert — 3,030,000 vectors x 64 components x 4 bytes.
    assert projection.vector_bytes == 3_030_000 * 64 * 4


def test_a_compressed_store_also_carries_the_full_precision_copy_rescoring_needs() -> None:
    # Arrange — compression does not remove the originals: both backends keep the full-precision
    # vectors to re-score against, which is what 31.3 and 31.10 built. A projection reporting only
    # the compressed size would understate a binary store by roughly thirty-two times.
    projection = project(
        pipeline="index-qdrant",
        sample_documents=40,
        sample_chunks=1_212,
        documents=100_000,
        width=1_536,
        width_assumption=None,
        store="qdrant",
        index_kind=VectorIndexKind.HNSW,
        precision=VectorPrecision.BINARY,
    )

    # Assert
    assert projection.vector_bytes == int(3_030_000 * 1_536 * 0.125)
    assert projection.rescoring_original_bytes == 3_030_000 * 1_536 * 4


def test_an_uncompressed_store_keeps_no_second_copy() -> None:
    # Arrange / Act / Assert — there is nothing to re-score against when nothing was compressed,
    # and reporting the same bytes twice would double a float32 projection.
    projection = project(
        pipeline="index-text",
        sample_documents=40,
        sample_chunks=1_212,
        documents=100_000,
        width=64,
        width_assumption=None,
        store="pgvector",
        index_kind=VectorIndexKind.EXACT,
        precision=VectorPrecision.FLOAT32,
    )

    assert projection.rescoring_original_bytes == 0


def test_a_width_the_configuration_does_not_pin_names_the_field_to_set() -> None:
    # Arrange — the OpenAI embedder leaves the width to the model when `dimensions` is unset, so
    # the number is an assumption rather than a reading. The task's own clause is that every
    # number printed names the assumption it rests on, and a free-text sentence nobody can assert
    # on is how that clause gets quietly dropped — so it is a field.
    projection = project(
        pipeline="index-openai",
        sample_documents=40,
        sample_chunks=1_212,
        documents=100_000,
        width=1_536,
        width_assumption="[packs.openai] dimensions is unset, so the model's native width",
        store="pgvector",
        index_kind=VectorIndexKind.EXACT,
        precision=VectorPrecision.FLOAT32,
    )

    # Assert
    assert projection.width_assumption is not None
    assert "dimensions" in projection.width_assumption


def test_a_store_that_named_no_index_kind_reports_its_overhead_as_unknown() -> None:
    # Arrange / Act / Assert — an unmeasured overhead is `None`, never 0. Zero is a measurement
    # meaning "this costs nothing"; `None` is the honest "nobody took this number", and a reader
    # provisioning storage needs to tell them apart.
    projection = project(
        pipeline="custom",
        sample_documents=40,
        sample_chunks=1_212,
        documents=100_000,
        width=64,
        width_assumption=None,
        store="a-third-partys-store",
        index_kind=None,
        precision=None,
    )

    assert projection.index_bytes is None


def test_a_measured_pairing_multiplies_phase_29s_per_vector_figure() -> None:
    # Arrange
    projection = project(
        pipeline="index-qdrant",
        sample_documents=40,
        sample_chunks=1_212,
        documents=100_000,
        width=1_536,
        width_assumption=None,
        store="qdrant",
        index_kind=VectorIndexKind.HNSW,
        precision=VectorPrecision.BINARY,
    )

    # Assert
    per_vector = MEASURED_INDEX_BYTES_PER_VECTOR[(VectorIndexKind.HNSW, VectorPrecision.BINARY)]
    assert projection.index_bytes == pytest.approx(3_030_000 * per_vector, rel=1e-3)


def test_what_a_sample_cannot_reveal_is_named_rather_than_omitted() -> None:
    # Arrange / Act / Assert — payload, text and write-ahead log are real costs on a real server
    # and none of them is derivable from a sample of forty documents. The plan deferred them to a
    # task that shipped narrowed and measured nothing, so they are named as unknowns here with no
    # expiry attached to a task that will not supply them.
    projection = project(
        pipeline="index-text",
        sample_documents=40,
        sample_chunks=1_212,
        documents=100_000,
        width=64,
        width_assumption=None,
        store="pgvector",
        index_kind=VectorIndexKind.EXACT,
        precision=VectorPrecision.FLOAT32,
    )

    assert set(projection.unknowns) == set(UNMEASURABLE_FROM_A_SAMPLE)
    assert "payload" in projection.unknowns
    assert "text" in projection.unknowns
    assert "WAL" in projection.unknowns


def test_the_projection_reports_that_it_spent_no_model_call() -> None:
    # Arrange / Act / Assert — the task's headline property, and it is a printed number rather
    # than a claim in a docstring: an estimator that quietly embedded the sample would bill the
    # operator for a question about capacity. No shipped stage declares its own cost, so this is
    # how zero is proved rather than asserted.
    projection = project(
        pipeline="index-text",
        sample_documents=40,
        sample_chunks=1_212,
        documents=100_000,
        width=64,
        width_assumption=None,
        store="pgvector",
        index_kind=VectorIndexKind.EXACT,
        precision=VectorPrecision.FLOAT32,
    )

    assert projection.model_calls == 0


def test_a_sample_that_produced_no_chunks_is_refused_rather_than_divided_by() -> None:
    # Arrange / Act / Assert — a directory holding nothing any extractor claims yields zero
    # chunks, and scaling from it is a division by zero dressed as a projection. Refused by name,
    # because an estimate of "0 vectors for 100,000 documents" is a plausible answer against the
    # wrong data.
    with pytest.raises(ValueError, match="sample"):
        project(
            pipeline="index-text",
            sample_documents=0,
            sample_chunks=0,
            documents=100_000,
            width=64,
            width_assumption=None,
            store="pgvector",
            index_kind=VectorIndexKind.EXACT,
            precision=VectorPrecision.FLOAT32,
        )
