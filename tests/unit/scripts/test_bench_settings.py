"""Unit tests for `scripts/bench_settings.py` — Phase 31 task **31.6**.

Filtered recall@10 against an exact-scan control, reached *through the settings surface*: a written
`weft.toml` and a `vector-top-k` document's own `Filter`, with no hand-written SQL and no direct
client call. All 65 of Phase 29's arms issued their own SQL, so nothing in this tree has ever
proven that a `[packs.store]` key parses, validates, binds through `functools.partial` and then
actually reaches the database — which is the one thing this harness exists to catch.

What a run cannot show being wrong is pinned here: the arm matrix the ninth owner decision settled,
that every backend carries its own exact-scan control at every selectivity its approximate arms
use, the `weft.toml` each arm writes, and the filter document that carries the ladder.

**`bench_record.arms_from_settings` is tested here rather than in `test_bench_record.py`**, against
this module's own run model. Importing `bench_settings` into that file would make every test in it
fail at collection while this module does not exist, and it is green today — a masking shape this
phase has already paid for once (`L23.9`).

The ladder is `lineage.sources`, and nothing in it is invented for this file: the shipped ingest
path attaches no `ext` at all (`weft_chunk/__init__.py:10 "This pack contributes no"`),
so `Phase 29`'s bucket column is unavailable and the only graded core field is the one below.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import bench_filtered
import bench_record
import bench_settings
import pytest

from weft_store.contract import FilterOp, VectorIndexKind, VectorPrecision

_MACHINE = bench_record.bench_latency.describe_machine(
    chip="Apple M4 Pro", memory_bytes=25_769_803_776, cpus=12, os_version="26.6.2"
)
_TAKEN = datetime(2026, 9, 16, 12, 0, tzinfo=UTC)

_LADDER = (
    None,
    bench_filtered.Selectivity.ONE_PERCENT,
    bench_filtered.Selectivity.TENTH_OF_A_PERCENT,
)


def _sources() -> tuple[str, ...]:
    return (
        "/corpus/open_ragbench/pdfs/2410.17420v2.pdf",
        "/corpus/open_ragbench/pdfs/2406.05923v2.pdf",
    )


# ---------------------------------------------------------------------------------------------
# The matrix
# ---------------------------------------------------------------------------------------------


def test_the_matrix_is_the_seventeen_arms_the_ninth_decision_settled() -> None:
    assert len(bench_settings.arms()) == 17


def test_each_backend_carries_its_own_exact_scan_control_at_every_selectivity_it_measures() -> None:
    # Arrange — the property the ninth decision added: recall is only meaningful against a control
    # taken on the same backend, in the same run, at the same selectivity.
    arms = bench_settings.arms()

    for backend in bench_settings.Backend:
        approximate = {
            arm.selectivity for arm in arms if arm.backend is backend and not arm.is_control
        }
        controls = {arm.selectivity for arm in arms if arm.backend is backend and arm.is_control}

        # Assert
        assert approximate, f"{backend} has no approximate arm to measure"
        assert approximate <= controls, f"{backend} measures a selectivity it cannot control for"


def test_a_control_arm_is_exactly_an_exact_index_on_either_backend() -> None:
    for arm in bench_settings.arms():
        assert arm.is_control is (arm.index is VectorIndexKind.EXACT)


def test_the_iterative_scan_knob_is_set_on_pgvector_arms_and_absent_on_qdrant_arms() -> None:
    # `hnsw.iterative_scan` is a pgvector session GUC; the value means nothing to Qdrant, and
    # carrying one there would be a setting this harness claims to measure and never sends.
    for arm in bench_settings.arms():
        if arm.backend is bench_settings.Backend.QDRANT:
            assert arm.iterative_scan is None
        elif arm.index is VectorIndexKind.HNSW:
            assert arm.iterative_scan is not None


def test_both_iterative_scan_modes_are_measured_at_every_rung_of_the_ladder() -> None:
    # Arrange — this pair is the whole point: identical recall across the two is the signature of
    # the GUC never reaching the server.
    measured = {
        (arm.iterative_scan, arm.selectivity)
        for arm in bench_settings.arms()
        if arm.backend is bench_settings.Backend.PGVECTOR and arm.index is VectorIndexKind.HNSW
    }

    # Assert
    for selectivity in _LADDER:
        assert (bench_filtered.IterativeScan.OFF, selectivity) in measured
        assert (bench_filtered.IterativeScan.RELAXED_ORDER, selectivity) in measured


def test_the_reductions_the_eighth_decision_made_are_still_in_force() -> None:
    # Arrange
    arms = bench_settings.arms()

    # Assert — `strict_order` tracks `relaxed_order` within 0.05 everywhere; 50% and 10% separate
    # nothing; `diskann` shipped as a refusal, so its settings path is an error, not a number.
    assert all(arm.iterative_scan is not bench_filtered.IterativeScan.STRICT_ORDER for arm in arms)
    assert all(arm.selectivity in _LADDER for arm in arms)
    assert all(arm.index is not VectorIndexKind.DISKANN for arm in arms)


def test_no_arm_asks_pgvector_for_a_precision_it_refuses_by_name() -> None:
    # pgvector indexes `vector`, `halfvec` and `bit` and has no `int8` — asking for one is an
    # error path, which task 31.12 already proves, not a recall number.
    for arm in bench_settings.arms():
        if arm.backend is bench_settings.Backend.PGVECTOR:
            assert arm.precision is not VectorPrecision.INT8


def test_the_compressed_arms_are_measured_only_where_a_control_exists_at_the_same_rung() -> None:
    # Arrange
    compressed = [
        arm
        for arm in bench_settings.arms()
        if arm.precision in (VectorPrecision.FLOAT16, VectorPrecision.BINARY)
    ]

    # Assert
    assert compressed, "the compressed arms are what prove precision reaches the column"
    for arm in compressed:
        assert arm.selectivity is bench_filtered.Selectivity.ONE_PERCENT


def test_every_arm_is_distinct_so_no_configuration_is_measured_twice() -> None:
    arms = bench_settings.arms()
    assert len(set(arms)) == len(arms)


# ---------------------------------------------------------------------------------------------
# The settings surface — what the harness actually writes
# ---------------------------------------------------------------------------------------------


def test_a_pgvector_arm_writes_its_three_keys_under_the_store_pack() -> None:
    # Arrange
    arm = bench_settings.Arm(
        backend=bench_settings.Backend.PGVECTOR,
        index=VectorIndexKind.HNSW,
        precision=VectorPrecision.FLOAT32,
        iterative_scan=bench_filtered.IterativeScan.OFF,
        selectivity=bench_filtered.Selectivity.ONE_PERCENT,
    )

    # Act
    written = bench_settings.weft_toml_for(arm)

    # Assert — the pack table is `[packs.store]`, which is the *pack* name, never the distribution.
    assert "[packs.store]" in written
    assert 'index = "hnsw"' in written
    assert 'precision = "float32"' in written
    assert 'iterative_scan = "off"' in written
    assert 'store = "pgvector"' in written


def test_a_qdrant_arm_writes_its_own_pack_table_and_the_width_its_collection_fixes() -> None:
    # Arrange
    arm = bench_settings.Arm(
        backend=bench_settings.Backend.QDRANT,
        index=VectorIndexKind.EXACT,
        precision=VectorPrecision.FLOAT32,
        iterative_scan=None,
        selectivity=None,
    )

    # Act
    written = bench_settings.weft_toml_for(arm)

    # Assert — a Qdrant collection fixes its width at creation, so the file has to name it.
    assert "[packs.qdrant]" in written
    assert 'index = "exact"' in written
    assert f"vector_size = {bench_settings.WIDTH}" in written
    assert 'store = "qdrant"' in written
    assert "iterative_scan" not in written


def test_the_file_never_writes_a_dsn_literal_so_the_environment_still_fills_it() -> None:
    # `merged_pack_settings` is file-wins key by key, with the environment filling what the file
    # omits — so a block naming the index but no `dsn` still picks the database up from
    # `WEFT_DATABASE_URL`, which is how every other harness reaches the store.
    for arm in bench_settings.arms():
        written = bench_settings.weft_toml_for(arm)
        assert "postgresql://" not in written


def test_every_arm_pins_the_query_embedder_to_the_one_width_the_service_can_produce() -> None:
    # `ServiceSelection.embed` is a bare `str` and the query path builds it `factory(None)`, so
    # the service is configless and `hash` answers at its own default. Every arm is at that width
    # or the ladder compares vectors from two different spaces.
    assert bench_settings.WIDTH == 64
    for arm in bench_settings.arms():
        assert 'embed = "hash"' in bench_settings.weft_toml_for(arm)


# ---------------------------------------------------------------------------------------------
# The filter document — the ladder itself
# ---------------------------------------------------------------------------------------------


def test_the_filter_document_carries_the_ladder_as_an_in_over_lineage_sources() -> None:
    # Act
    document = bench_settings.filter_document(
        bench_filtered.Selectivity.ONE_PERCENT, sources=_sources()
    )

    # Assert — `lineage.sources` is a TEXT_SET, and `in` is one of the three operators it admits.
    assert f"op: {FilterOp.IN.value}" in document
    assert "field: lineage.sources" in document
    for source in _sources():
        assert source in document


def test_an_unfiltered_document_carries_no_filter_at_all_rather_than_an_empty_one() -> None:
    # Act
    document = bench_settings.filter_document(None, sources=_sources())

    # Assert — an empty filter is a predicate that matches everything by accident rather than by
    # statement, and the two are indistinguishable in a result.
    assert "filter:" not in document


def test_the_document_ends_in_a_packer_so_retrieve_only_can_run_it() -> None:
    # `--retrieve-only --pipeline` requires the document to end in `Passages`, and only a
    # `ContextPacker` produces one — a document ending at the retriever is refused by name.
    document = bench_settings.filter_document(
        bench_filtered.Selectivity.ONE_PERCENT, sources=_sources()
    )

    assert "use: vector-top-k" in document
    assert "use: single-list" in document
    assert "use: repack" in document


def test_the_packer_keeps_at_least_the_ten_hits_recall_is_measured_over() -> None:
    # A `top_n` below `top_k` would truncate the ranking before it is scored, and recall@10 would
    # measure the packer rather than the index.
    document = bench_settings.filter_document(
        bench_filtered.Selectivity.ONE_PERCENT, sources=_sources()
    )

    assert f"top_k: {bench_settings.TOP_K}" in document
    assert f"top_n: {bench_settings.TOP_K}" in document


def test_a_document_asking_for_sources_it_was_given_none_of_is_refused() -> None:
    # An `in` over an empty list matches nothing, and a recall of 0 against an empty filter reads
    # as a broken index rather than as a harness that was handed nothing.
    with pytest.raises(ValueError, match="sources"):
        bench_settings.filter_document(bench_filtered.Selectivity.ONE_PERCENT, sources=())


# ---------------------------------------------------------------------------------------------
# The record — the seventh `arms_from_*` adapter
# ---------------------------------------------------------------------------------------------


def _result(
    arm: bench_settings.Arm, *, rows: int = 180_400, recall: float = 0.98
) -> bench_settings.SettingsArmResult:
    return bench_settings.SettingsArmResult(
        arm=arm,
        queries=50,
        matching_rows=1_804,
        returned_min=10,
        recall_at_10=recall,
        p50_ms=12.0,
        p95_ms=31.0,
        rows_before=rows,
        rows_after=rows,
    )


def _run(*results: bench_settings.SettingsArmResult) -> bench_settings.SettingsRun:
    return bench_settings.SettingsRun(
        machine=_MACHINE,
        database="weft_bench_settings_64_20260916120000",
        corpus="open_ragbench",
        documents=1_000,
        rows=180_400,
        width=bench_settings.WIDTH,
        pgvector_version="0.8.6",
        server_version="16.15",
        qdrant_version="1.12.4",
        results=results,
        taken_at=_TAKEN,
    )


def test_an_arm_becomes_a_record_naming_this_task_and_its_own_configuration() -> None:
    # Arrange
    arm = bench_settings.arms()[0]

    # Act
    (record,) = bench_record.arms_from_settings(_run(_result(arm)))

    # Assert
    assert record.task == "31.6"
    assert arm.backend.value in record.name
    assert arm.index.value in record.name
    assert "recall@10" in {measure.label for measure in record.measures}


def test_the_sample_size_travels_with_every_figure_it_qualifies() -> None:
    # Recall@10 over 50 queries carries a standard error near 0.02-0.05 — ample to separate 0.003
    # from 0.98, useless at the third decimal. A figure without its sample size invites the
    # second reading.
    (record,) = bench_record.arms_from_settings(_run(_result(bench_settings.arms()[0])))

    assert "queries" in {measure.label for measure in record.measures}


def test_an_arm_whose_table_moved_under_it_is_refused_rather_than_recorded() -> None:
    # Arrange — `L8.30`: a measurement asserts its own row count immediately before *and* after.
    moved = _result(bench_settings.arms()[0]).model_copy(update={"rows_after": 180_399})

    # Act / Assert
    with pytest.raises(bench_record.bench_latency.RowCountMismatchError):
        bench_record.arms_from_settings(_run(moved))


def test_every_arm_of_a_full_run_reaches_the_record() -> None:
    # Arrange
    run = _run(*(_result(arm) for arm in bench_settings.arms()))

    # Act
    records = bench_record.arms_from_settings(run)

    # Assert
    assert len(records) == len(bench_settings.arms())


def _manifest(tmp_path: Path, *, documents: tuple[str, ...], excluded: tuple[str, ...]) -> Path:
    """A corpus manifest in the shape `corpus/open-ragbench-pdfs.toml` actually has: the
    `[[document]]` entries are already the filtered set, and `[[excluded]]` records why the
    missing ones are missing.
    """
    lines = ['query = "fixture"', ""]
    for identifier in documents:
        lines += ["[[document]]", f'id = "{identifier}"', 'source = "s"', 'sha256 = "d"', ""]
    for identifier in excluded:
        lines += ["[[excluded]]", f'id = "{identifier}"', 'reason = "R29.2"', ""]
    path = tmp_path / "manifest.toml"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def test_a_manifest_makes_the_corpus_its_documents_and_not_the_directory(tmp_path: Path) -> None:
    # Arrange — the directory holds a paper the manifest excluded, which is the real situation:
    # `R29.2` aborts the whole `weft index` run on it, so meeting it at all ends the measurement.
    corpus = tmp_path / "pdfs"
    corpus.mkdir()
    for identifier in ("good-1", "good-2", "surrogate"):
        (corpus / f"{identifier}.pdf").write_bytes(b"%PDF-1.4\n")
    manifest = _manifest(tmp_path, documents=("good-1", "good-2"), excluded=("surrogate",))

    # Act
    sources = bench_settings.corpus_sources(corpus, manifest=manifest)

    # Assert
    assert {path.name for path in sources} == {"good-1.pdf", "good-2.pdf"}


def test_a_manifest_document_missing_from_the_corpus_is_refused_not_dropped(tmp_path: Path) -> None:
    # A silently shorter corpus is a measurement over a set nobody chose.
    corpus = tmp_path / "pdfs"
    corpus.mkdir()
    (corpus / "present.pdf").write_bytes(b"%PDF-1.4\n")
    manifest = _manifest(tmp_path, documents=("present", "absent"), excluded=())

    with pytest.raises(bench_settings.bench_latency.MeasurementRefusedError, match="absent"):
        bench_settings.corpus_sources(corpus, manifest=manifest)


def test_without_a_manifest_every_file_under_the_corpus_is_taken(tmp_path: Path) -> None:
    # The default the smaller corpora rely on, kept working.
    corpus = tmp_path / "docs"
    corpus.mkdir()
    for name in ("a.txt", "b.md"):
        (corpus / name).write_text("x", encoding="utf-8")

    assert len(bench_settings.corpus_sources(corpus)) == 2


def test_a_settings_run_round_trips_through_its_json_file(tmp_path: Path) -> None:
    # Arrange
    run = _run(_result(bench_settings.arms()[0]))
    path = tmp_path / "run-31.6.json"

    # Act
    path.write_text(run.model_dump_json(indent=2), encoding="utf-8")

    # Assert
    assert bench_settings.SettingsRun.model_validate_json(path.read_text(encoding="utf-8")) == run
