"""Unit tests for `scripts/bench_latency.py` — Phase 29 task **29.1**.

The harness drives the shipped binary and the store's own statement against a throwaway database
and reports p50/p95 with a machine's name on them. What a run cannot show being wrong is pinned
here: the percentile rule, the count the binary reports, the refusal when a table moved under a
measurement (`L8.30`), the synthetic width-1536 vectors, and the line an operator reads.
"""

from __future__ import annotations

import math

import bench_latency
import pytest


def test_percentiles_use_the_nearest_rank_rule() -> None:
    # Arrange — deliberately unsorted, so a rule that forgets to sort cannot pass.
    samples = [float(n) for n in range(200, 0, -1)]

    # Act / Assert
    assert bench_latency.percentile(samples, 0.50) == 100.0
    assert bench_latency.percentile(samples, 0.95) == 190.0
    assert bench_latency.percentile([7.0], 0.95) == 7.0


def test_a_percentile_of_nothing_is_refused() -> None:
    with pytest.raises(ValueError, match="no samples"):
        bench_latency.percentile([], 0.5)


def test_the_stored_count_is_read_from_what_weft_index_prints() -> None:
    # Arrange — the real line, `weft_cli/render.py:659 "nodes now stored: {stored}."`.
    stdout = "indexed 500 documents.\nnodes now stored: 10000.\n"

    # Act / Assert
    assert bench_latency.parse_nodes_stored(stdout) == 10_000


@pytest.mark.parametrize("stdout", ["indexed 3 documents.\n", "nodes now stored: unknown.\n"])
def test_an_unreported_count_is_refused_rather_than_assumed(stdout: str) -> None:
    with pytest.raises(bench_latency.CountNotReportedError, match="nodes now stored"):
        bench_latency.parse_nodes_stored(stdout)


def test_a_table_that_moved_under_a_measurement_abandons_it_naming_both_counts() -> None:
    # Act / Assert
    bench_latency.assert_rows(label="before", expected=10_000, found=10_000)
    with pytest.raises(
        bench_latency.RowCountMismatchError, match=r"after: expected 10,000 rows, found 1 "
    ):
        bench_latency.assert_rows(label="after", expected=10_000, found=1)


def test_synthetic_vectors_are_deterministic_unit_length_and_exactly_as_wide_as_asked() -> None:
    # Act
    first = bench_latency.synthetic_vector("node-1", 1536)
    again = bench_latency.synthetic_vector("node-1", 1536)
    other = bench_latency.synthetic_vector("node-2", 1536)

    # Assert
    assert len(first) == 1536
    assert first == again
    assert first != other
    assert math.isclose(math.sqrt(sum(v * v for v in first)), 1.0, abs_tol=1e-9)


def test_the_query_sample_is_deterministic_and_independent_of_input_order() -> None:
    # Arrange
    ids = [f"n{i}" for i in range(50)]

    # Act
    sample = bench_latency.query_sample(ids, 10)

    # Assert
    assert len(sample) == 10
    assert len(set(sample)) == 10
    assert sample == bench_latency.query_sample(list(reversed(ids)), 10)
    assert set(sample) <= set(ids)
    with pytest.raises(ValueError, match="51 queries.*50 rows"):
        bench_latency.query_sample(ids, 51)


def test_the_machine_is_named_from_what_the_host_reports() -> None:
    # Act
    machine = bench_latency.describe_machine(
        chip="Apple M4 Pro", memory_bytes=25_769_803_776, cpus=12, os_version="26.6.2"
    )

    # Assert
    assert machine.label == "Apple M4 Pro, 24 GiB, 12 CPUs, macOS 26.6.2"


def test_a_result_line_carries_every_number_with_its_label() -> None:
    # Arrange — seconds in, milliseconds out.
    samples = [0.001 * n for n in range(1, 201)]

    # Act
    result = bench_latency.summarise(
        arm=bench_latency.Arm.STORE_STATEMENT,
        chunks=100_000,
        width=1536,
        samples_seconds=samples,
        rows_before=100_000,
        rows_after=100_000,
    )
    line = bench_latency.format_result(result)

    # Assert
    assert result.p50_ms == pytest.approx(100.0)
    assert result.p95_ms == pytest.approx(190.0)
    assert "chunks: 100,000" in line
    assert "width: 1536" in line
    assert "arm: store statement" in line
    assert "p50: 100.0 ms" in line
    assert "p95: 190.0 ms" in line
    assert "queries: 200" in line
    assert "before: 100,000 rows" in line
    assert "after: 100,000 rows" in line


def test_a_result_whose_rows_moved_is_never_summarised() -> None:
    with pytest.raises(
        bench_latency.RowCountMismatchError, match="after: expected 100,000 rows, found 99,999"
    ):
        bench_latency.summarise(
            arm=bench_latency.Arm.CLI_RETRIEVE_ONLY,
            chunks=100_000,
            width=64,
            samples_seconds=[0.01],
            rows_before=100_000,
            rows_after=99_999,
        )
