"""Unit tests for `scripts/bench_filtered.py` — Phase 29 task **29.7**.

HNSW on a typed column under a filter, at four selectivities and three iterative-scan modes. What a
run cannot show being wrong is pinned here: recall against the exact ranking, buckets that are
nested and close to their stated fraction, the JSON a row's bucket is written as, the truncation
that makes a 3072-wide vector indexable, and the reading of an `EXPLAIN` plan that stops a
sequential scan passing as an index number.
"""

from __future__ import annotations

import json
import math

import bench_filtered
import pytest

_IDS = tuple(f"node-{n}" for n in range(100_000))


def test_recall_is_the_share_of_the_exact_top_k_the_index_returned() -> None:
    # Arrange
    truth = [f"t{n}" for n in range(10)]
    found = [*truth[:7], "x1", "x2", "x3"]

    # Act / Assert
    assert bench_filtered.recall_at_k(truth, found, k=10) == pytest.approx(0.7)
    assert bench_filtered.recall_at_k(truth, list(reversed(truth)), k=10) == 1.0


def test_recall_over_fewer_true_matches_than_k_is_measured_against_what_exists() -> None:
    # Arrange — a 0.1% filter over a small table can match fewer rows than top_k.
    truth = ["a", "b", "c"]

    # Act / Assert
    assert bench_filtered.recall_at_k(truth, ["c", "a", "b"], k=10) == 1.0
    assert bench_filtered.recall_at_k(truth, ["a"], k=10) == pytest.approx(1 / 3)


def test_recall_with_no_ground_truth_is_undefined_and_refused() -> None:
    with pytest.raises(ValueError, match="no ground truth"):
        bench_filtered.recall_at_k([], ["a"], k=10)


@pytest.mark.parametrize(
    ("selectivity", "fraction"),
    [
        (bench_filtered.Selectivity.HALF, 0.5),
        (bench_filtered.Selectivity.TENTH, 0.1),
        (bench_filtered.Selectivity.ONE_PERCENT, 0.01),
        (bench_filtered.Selectivity.TENTH_OF_A_PERCENT, 0.001),
    ],
)
def test_each_bucket_holds_close_to_its_stated_share_of_rows(
    selectivity: bench_filtered.Selectivity, fraction: float
) -> None:
    # Act
    members = sum(bench_filtered.in_bucket(node_id, selectivity) for node_id in _IDS)

    # Assert — within 15% of the target, which at 0.1% of 100,000 is 100 ± 15 rows.
    assert selectivity.fraction == fraction
    assert math.isclose(members, fraction * len(_IDS), rel_tol=0.15)


def test_buckets_are_nested_so_a_narrower_filter_is_a_subset_of_a_wider_one() -> None:
    # Arrange
    order = (
        bench_filtered.Selectivity.TENTH_OF_A_PERCENT,
        bench_filtered.Selectivity.ONE_PERCENT,
        bench_filtered.Selectivity.TENTH,
        bench_filtered.Selectivity.HALF,
    )

    # Act / Assert
    for narrow, wide in zip(order, order[1:], strict=False):
        narrow_set = {i for i in _IDS if bench_filtered.in_bucket(i, narrow)}
        wide_set = {i for i in _IDS if bench_filtered.in_bucket(i, wide)}
        assert narrow_set < wide_set, f"{narrow.value} is not inside {wide.value}"


def test_a_rows_buckets_are_written_under_the_benchmark_namespace() -> None:
    # Act
    written = json.loads(bench_filtered.bench_ext("node-7"))

    # Assert
    assert set(written) == {bench_filtered.BENCH_NAMESPACE}
    assert written[bench_filtered.BENCH_NAMESPACE] == {
        selectivity.key: bench_filtered.in_bucket("node-7", selectivity)
        for selectivity in bench_filtered.Selectivity
    }


def test_each_selectivity_has_its_own_filtered_statement() -> None:
    statements = {
        bench_filtered.filtered_statement(s).as_string(None) for s in bench_filtered.Selectivity
    }

    assert len(statements) == len(bench_filtered.Selectivity)


def test_truncation_keeps_the_leading_components_and_restores_unit_length() -> None:
    # Arrange
    native = (3.0, 4.0, 12.0, 84.0)

    # Act
    truncated = bench_filtered.truncate_renormalise(native, 2)

    # Assert
    assert truncated == pytest.approx((0.6, 0.8))
    with pytest.raises(ValueError, match="width 5.*4 components"):
        bench_filtered.truncate_renormalise(native, 5)
    with pytest.raises(ValueError, match="zero"):
        bench_filtered.truncate_renormalise((0.0, 0.0, 1.0), 2)


@pytest.mark.parametrize(
    ("plan", "shape"),
    [
        (
            ["Limit  (cost=...)", "  ->  Index Scan using bench_hnsw on weft_nodes  (cost=...)"],
            bench_filtered.PlanShape.INDEX_SCAN,
        ),
        (
            ["Limit", "  ->  Sort", "        ->  Seq Scan on weft_nodes"],
            bench_filtered.PlanShape.SEQ_SCAN,
        ),
        (
            ["Limit", "  ->  Index Scan using weft_nodes_pkey on weft_nodes"],
            bench_filtered.PlanShape.OTHER,
        ),
    ],
)
def test_a_plan_is_an_index_number_only_when_it_scans_the_index_under_test(
    plan: list[str], shape: bench_filtered.PlanShape
) -> None:
    assert bench_filtered.classify_plan(plan, index_name="bench_hnsw") is shape


def test_the_three_iterative_scan_modes_are_pgvectors_own_spellings() -> None:
    assert [mode.value for mode in bench_filtered.IterativeScan] == [
        "off",
        "relaxed_order",
        "strict_order",
    ]
