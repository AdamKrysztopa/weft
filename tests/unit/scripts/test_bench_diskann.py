"""Unit tests for `scripts/bench_diskann.py` — Phase 29 task **29.9**.

StreamingDiskANN on a typed `vector(n)` column in `timescale/timescaledb-ha:pg17`, filtered two
ways: a JSONB post-filter in the store's own shape, and a `smallint[]` label column the extension
plans as an index condition (`fix-plans/07` Finding 3; position 5, measured and not proposed).
Pinned here: how bucket membership becomes labels, that the label predicate asks for exactly the
selectivity's label, and the two index statements.
"""

from __future__ import annotations

import bench_diskann
import bench_filtered
import pytest


def test_every_selectivity_has_its_own_small_integer_label() -> None:
    # Act
    labels = [bench_diskann.label_of(selectivity) for selectivity in bench_filtered.Selectivity]

    # Assert — small integers, distinct, and never 0, which a reader could take for "unlabelled".
    assert len(set(labels)) == len(labels)
    assert all(0 < label < 2**15 for label in labels)


@pytest.mark.parametrize("node_id", ["node-1", "node-7", "node-42", "node-99999"])
def test_a_rows_labels_are_exactly_the_buckets_it_belongs_to(node_id: str) -> None:
    # Act
    labels = bench_diskann.labels_for(node_id)

    # Assert
    assert set(labels) == {
        bench_diskann.label_of(selectivity)
        for selectivity in bench_filtered.Selectivity
        if bench_filtered.in_bucket(node_id, selectivity)
    }
    assert list(labels) == sorted(labels)


def test_the_two_index_statements_differ_only_by_the_label_column() -> None:
    # Act
    plain = bench_diskann.index_statement(index_name="bench_diskann", with_labels=False).as_string(
        None
    )
    labelled = bench_diskann.index_statement(
        index_name="bench_diskann", with_labels=True
    ).as_string(None)

    # Assert
    assert "USING diskann" in plain
    assert "vector_cosine_ops" in plain
    assert "labels" not in plain
    assert "labels" in labelled


def test_each_selectivity_has_its_own_label_statement_and_its_own_jsonb_statement() -> None:
    # Act
    label_statements = {
        bench_diskann.label_filtered_statement(s).as_string(None)
        for s in bench_filtered.Selectivity
    }
    jsonb_statements = {
        bench_filtered.filtered_statement(s).as_string(None) for s in bench_filtered.Selectivity
    }

    # Assert
    assert len(label_statements) == len(bench_filtered.Selectivity)
    assert label_statements.isdisjoint(jsonb_statements)
