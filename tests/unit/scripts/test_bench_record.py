"""Unit tests for `scripts/bench_record.py` — Phase 29 task **29.12**.

G22's widened *Bring* is one JSON record per run, naming the machine, the image digests, every
extension version, the row counts before and after each arm, and each arm's numbers. The table the
session reads is generated from that record, never typed. `fix-plans/07` → *The exit* asks for a
table in which every position 1–5 has a row. Pinned here: the positions, how two different run
records become arms (built from the harnesses' own models, not from shapes written for this
file), that a moved row count is refused, and that the table names a position no arm informs.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import bench_filtered
import bench_latency
import bench_record
import pytest

_MACHINE = bench_latency.describe_machine(
    chip="Apple M4 Pro", memory_bytes=25_769_803_776, cpus=12, os_version="26.6.2"
)
_TAKEN = datetime(2026, 9, 15, 17, 0, tzinfo=UTC)


def _latency_run() -> bench_latency.LatencyRun:
    return bench_latency.LatencyRun(
        machine=_MACHINE,
        database="weft_bench_lat_100000_1536_20260915171839",
        pgvector_version="0.8.6",
        server_version="16.15",
        chunks=100_000,
        width=1536,
        synthetic_vectors=True,
        alter_seconds=21.11,
        results=(
            bench_latency.LatencyResult(
                arm=bench_latency.Arm.STORE_STATEMENT,
                chunks=100_000,
                width=1536,
                queries=200,
                p50_ms=149.3,
                p95_ms=168.1,
                rows_before=100_000,
                rows_after=100_000,
            ),
        ),
        taken_at=_TAKEN,
    )


def _filtered_run() -> bench_filtered.FilteredRun:
    return bench_filtered.FilteredRun(
        machine=_MACHINE,
        database="weft_bench_filtered_1536_20260915180000",
        vector_set="abcdef012345-text-embedding-3-large-3072-2026-09-15",
        rows=100_000,
        width=1536,
        pgvector_version="0.8.6",
        server_version="16.15",
        alter_seconds=20.0,
        index_build_seconds=95.5,
        index_bytes=800_000_000,
        ef_search="40",
        max_scan_tuples="20000",
        matching_rows=(
            bench_filtered.SelectivityCount(
                selectivity=bench_filtered.Selectivity.TENTH_OF_A_PERCENT, rows=101
            ),
        ),
        results=(
            bench_filtered.FilteredArmResult(
                selectivity=bench_filtered.Selectivity.TENTH_OF_A_PERCENT,
                iterative_scan=bench_filtered.IterativeScan.OFF,
                queries=200,
                returned_min=0,
                returned_mean=1.4,
                recall_at_10=0.12,
                p50_ms=1.9,
                p95_ms=3.2,
                plan=bench_filtered.PlanShape.INDEX_SCAN,
                rows_before=100_000,
                rows_after=100_000,
            ),
        ),
        taken_at=_TAKEN,
    )


def test_the_five_positions_are_g22s_own_and_in_its_order() -> None:
    assert [position.value for position in bench_record.G22Position] == [
        "1 commit at first write",
        "2 configured width",
        "3 expression indexes per width",
        "4 unindexed, ceiling documented",
        "5 typed column plus label column",
    ]


def test_a_latency_run_becomes_an_arm_carrying_its_rows_numbers_and_positions() -> None:
    # Act
    (arm,) = bench_record.arms_from_latency(_latency_run())

    # Assert
    assert arm.task == "29.1"
    assert arm.rows_before == 100_000
    assert arm.rows_after == 100_000
    assert bench_record.Measure(label="p95", value=168.1, unit="ms") in arm.measures
    assert bench_record.G22Position.UNINDEXED_CEILING in arm.positions


def test_a_filtered_run_becomes_an_arm_that_informs_the_typed_positions() -> None:
    # Act
    (arm,) = bench_record.arms_from_filtered(_filtered_run())

    # Assert
    assert arm.task == "29.7"
    assert bench_record.Measure(label="recall@10", value=0.12, unit="") in arm.measures
    assert bench_record.Measure(label="rows returned, minimum", value=0.0, unit="") in arm.measures
    assert set(arm.positions) == {
        bench_record.G22Position.COMMIT_AT_FIRST_WRITE,
        bench_record.G22Position.CONFIGURED_WIDTH,
    }


def test_an_arm_whose_rows_moved_is_refused_rather_than_recorded() -> None:
    with pytest.raises(
        bench_latency.RowCountMismatchError, match=r"expected 100,000 rows, found 99,999"
    ):
        bench_record.ArmRecord.checked(
            task="29.1",
            name="store statement",
            positions=(bench_record.G22Position.UNINDEXED_CEILING,),
            rows_before=100_000,
            rows_after=99_999,
            measures=(),
        )


def test_the_table_lists_every_arm_under_each_position_and_names_a_position_nothing_informs() -> (
    None
):
    # Arrange — two arms from two tasks, so the rows and their separation are both under test.
    record = bench_record.BenchRecord(
        machine=_MACHINE,
        images=(
            bench_record.ImageDigest(image="pgvector/pgvector:pg16", digest="sha256:" + "a" * 64),
        ),
        extensions=(bench_record.ExtensionVersion(name="vector", version="0.8.6"),),
        arms=(
            *bench_record.arms_from_latency(_latency_run()),
            *bench_record.arms_from_filtered(_filtered_run()),
        ),
        taken_at=_TAKEN,
    )

    # Act
    table = bench_record.session_table(record)

    # Assert
    lines = table.splitlines()
    assert lines[0].startswith("| G22 position | task | arm |")
    assert any(
        line.startswith("| 4 unindexed, ceiling documented | 29.1 |") and "p95 168.1 ms" in line
        for line in lines
    )
    assert any(
        line.startswith("| 1 commit at first write | 29.7 |") and "recall@10 0.12" in line
        for line in lines
    )
    assert any(line.startswith("| 2 configured width | 29.7 |") for line in lines)
    assert "| 5 typed column plus label column | — | no arm informs this position |" in table
    assert bench_record.missing_positions(record) == (
        bench_record.G22Position.EXPRESSION_INDEXES,
        bench_record.G22Position.LABEL_COLUMN,
    )


def test_a_record_round_trips_through_its_json_file(tmp_path: Path) -> None:
    # Arrange
    record = bench_record.BenchRecord(
        machine=_MACHINE,
        images=(),
        extensions=(),
        arms=bench_record.arms_from_latency(_latency_run()),
        taken_at=_TAKEN,
    )
    path = tmp_path / "bench-record.json"

    # Act
    bench_record.write_record(path, record)

    # Assert
    assert bench_record.read_record(path) == record
