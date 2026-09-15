"""Unit tests for `scripts/bench_quantised.py` — Phase 29 task **29.8**.

halfvec and binary-quantised HNSW expression indexes, rescored at full precision from an
oversampled candidate set (`fix-plans/07` 29.8; Q2 settled). What a run cannot show being wrong is
pinned here: the sweep points, the candidate arithmetic, and that every statement is its own. The
integration test beside this one proves the rescoring statement ranks what the store ranks.
"""

from __future__ import annotations

import bench_filtered
import bench_quantised
import pytest


def test_the_oversampling_factors_are_the_four_sweep_points() -> None:
    assert bench_quantised.OVERSAMPLING == (1, 2, 4, 10)


@pytest.mark.parametrize(("factor", "candidates"), [(1, 10), (2, 20), (4, 40), (10, 100)])
def test_the_candidate_set_is_the_factor_times_top_k(factor: int, candidates: int) -> None:
    assert bench_quantised.candidates(factor, top_k=10) == candidates


def test_an_oversampling_factor_below_one_is_refused() -> None:
    with pytest.raises(ValueError, match="oversampling must be at least 1"):
        bench_quantised.candidates(0, top_k=10)


def test_every_quantisation_factor_and_filter_has_its_own_rescoring_statement() -> None:
    # Arrange
    filters: tuple[bench_filtered.Selectivity | None, ...] = (
        None,
        bench_filtered.Selectivity.ONE_PERCENT,
    )

    # Act
    statements = {
        bench_quantised.rescored_statement(
            quantisation, width=1536, selectivity=selectivity
        ).as_string(None)
        for quantisation in bench_quantised.Quantisation
        for selectivity in filters
    }

    # Assert — the factor is a bound parameter, so it multiplies nothing here.
    assert len(statements) == len(bench_quantised.Quantisation) * len(filters)


def test_each_quantisation_builds_an_index_over_its_own_expression() -> None:
    # Act
    halfvec = bench_quantised.index_statement(
        bench_quantised.Quantisation.HALFVEC, width=1536, index_name="bench_q"
    ).as_string(None)
    binary = bench_quantised.index_statement(
        bench_quantised.Quantisation.BINARY, width=1536, index_name="bench_q"
    ).as_string(None)

    # Assert
    assert halfvec != binary
    assert "halfvec(1536)" in halfvec
    assert "binary_quantize" in binary
    assert "bit(1536)" in binary
    assert all("USING hnsw" in statement for statement in (halfvec, binary))


def test_a_width_past_what_the_quantised_type_indexes_is_refused_naming_the_ceiling() -> None:
    with pytest.raises(ValueError, match="halfvec.*4000"):
        bench_quantised.index_statement(
            bench_quantised.Quantisation.HALFVEC, width=4001, index_name="bench_q"
        )
