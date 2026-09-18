"""`weft_eval.pool` — ledger **40.2**: a frozen retrieval pool, written once and read back.

A pool two phases share has to be written down rather than re-derived: under HNSW a search's
depth depends on settings a later run may not share. What is checked here is the file itself —
that it reads back as written, that a schema this release cannot read is refused, and that the
two hashes a replay compares a question file against are over the fact and not its spelling.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from weft_eval.pool import (
    POOL_MANIFEST_SCHEMA_VERSION,
    PoolChunk,
    PoolManifest,
    PoolManifestSchemaError,
    PoolQuestion,
    PoolQuestionEntry,
    load_pool_manifest,
    relevant_set_sha256,
    text_sha256,
    write_pool_manifest,
)
from weft_kernel.errors import WeftError


def _manifest() -> PoolManifest:
    return PoolManifest(
        schema_version=POOL_MANIFEST_SCHEMA_VERSION,
        experiment="esci-pool",
        experiment_digest="e" * 64,
        arm="dense",
        corpus_digest="c" * 64,
        question_set_digest="q" * 64,
        query_pipeline="dense-pool-retrieve",
        query_pipeline_identity="i" * 64,
        model_versions={"embed": "text-embedding-3-large"},
        store="pgvector",
        store_rows=2,
        document_ids=("/corpus/doc-a", "/corpus/doc-b"),
        questions=(
            PoolQuestion(
                id="q-1",
                text_sha256=text_sha256("what is weft?"),
                relevant_sha256=relevant_set_sha256(["doc-a"]),
                rule_fires=False,
                chunks=(
                    PoolChunk(
                        node_id="n-1", document_id="doc-a", content_sha256="a" * 64, score=0.9
                    ),
                    PoolChunk(
                        node_id="n-2", document_id="doc-b", content_sha256="b" * 64, score=0.4
                    ),
                ),
            ),
        ),
    )


def test_a_manifest_reads_back_as_written_with_the_digest_of_its_bytes(tmp_path: Path) -> None:
    # Arrange
    path = tmp_path / "run.pool.json"
    manifest = _manifest()

    # Act
    write_pool_manifest(manifest, path)
    loaded = load_pool_manifest(path)

    # Assert
    assert loaded.manifest == manifest
    assert loaded.sha256 == hashlib.sha256(path.read_bytes()).hexdigest()
    assert [chunk.node_id for chunk in loaded.manifest.questions[0].chunks] == ["n-1", "n-2"]


def test_a_manifest_written_by_a_newer_schema_is_refused_naming_both_versions(
    tmp_path: Path,
) -> None:
    # Arrange
    path = tmp_path / "run.pool.json"
    write_pool_manifest(_manifest(), path)
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            f'"schema_version": {POOL_MANIFEST_SCHEMA_VERSION}', '"schema_version": 99'
        ),
        encoding="utf-8",
    )

    # Act
    with pytest.raises(PoolManifestSchemaError) as caught:
        load_pool_manifest(path)

    # Assert
    assert isinstance(caught.value, WeftError)
    assert "99" in str(caught.value)
    assert str(POOL_MANIFEST_SCHEMA_VERSION) in str(caught.value)


def test_a_relevant_set_hashes_the_same_whatever_order_it_is_written_in() -> None:
    assert relevant_set_sha256(["doc-b", "doc-a"]) == relevant_set_sha256(["doc-a", "doc-b"])
    assert relevant_set_sha256(["doc-a"]) != relevant_set_sha256(["doc-a", "doc-b"])


def test_a_question_texts_hash_is_the_sha256_of_its_utf8_bytes() -> None:
    assert text_sha256("zażółć") == hashlib.sha256("zażółć".encode()).hexdigest()


def test_the_entry_a_replayed_ranking_carries_names_its_own_namespace_and_question() -> None:
    # Act
    entry = PoolQuestionEntry(corpus_digest="c" * 64, question_id="q-1", text_sha256="t" * 64)

    # Assert
    assert PoolQuestionEntry.__namespace__ == "weft-eval-pool"
    assert entry.question_id == "q-1"
