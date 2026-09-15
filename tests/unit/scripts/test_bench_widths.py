"""Unit tests for `scripts/bench_widths.py` — Phase 29 task **29.10**.

Exact-scan and HNSW recall@10 at widths 256–2000 against the native-width exact ranking, so that
truncation error and index error are two numbers, plus whether truncating and renormalising a
native vector reproduces the API's own `dimensions` output on a sample. Pinned here: the sweep
points, the comparison that decides "reproduces", and its refusals.
"""

from __future__ import annotations

import math

import bench_widths
import pytest


def test_the_widths_are_the_five_sweep_points_and_all_are_hnsw_indexable() -> None:
    assert bench_widths.WIDTHS == (256, 512, 1024, 1536, 2000)
    assert max(bench_widths.WIDTHS) <= 2000


def test_a_truncated_native_vector_that_matches_the_api_output_reproduces_it() -> None:
    # Arrange — the API's shortened vector is the renormalised prefix, by construction here.
    native = (3.0, 4.0, 12.0, 84.0)
    api = (0.6, 0.8)

    # Act
    comparison = bench_widths.compare_truncation(native, api)

    # Assert
    assert comparison.width == 2
    assert math.isclose(comparison.cosine, 1.0, abs_tol=1e-12)
    assert comparison.reproduces


def test_a_shortened_vector_that_is_not_the_native_prefix_does_not_reproduce() -> None:
    # Act
    comparison = bench_widths.compare_truncation((3.0, 4.0, 12.0, 84.0), (0.8, 0.6))

    # Assert
    assert comparison.cosine < bench_widths.MIN_COSINE
    assert not comparison.reproduces


def test_an_api_vector_wider_than_the_native_one_is_refused_with_both_widths() -> None:
    with pytest.raises(ValueError, match="width 3.*2 components"):
        bench_widths.compare_truncation((1.0, 0.0), (1.0, 0.0, 0.0))


def test_the_tolerance_is_stated_as_a_cosine_floor() -> None:
    assert bench_widths.MIN_COSINE == 0.9999
