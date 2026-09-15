"""Unit tests for `scripts/bench_qdrant.py` — Phase 29 task **29.11**.

Qdrant with the same vectors and the same four selectivities, with no payload index and with one
created before ingest (`fix-plans/07` 29.11). The condition itself comes from the store's own
public translator, `weft_qdrant.store.to_qdrant_filter`, so this file does not compare that
function with itself. It pins what the harness contributes: that the payload it writes puts each
bucket where the store's dotted key looks, and which fields a payload index is built over.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TypeGuard

import bench_filtered
import bench_qdrant
import pytest

from weft_store.contract import FilterOp


def _is_mapping(value: object) -> TypeGuard[Mapping[str, object]]:
    return isinstance(value, Mapping)


def _resolve(payload: Mapping[str, object], dotted: str) -> object:
    value: object = payload
    for part in dotted.split("."):
        assert _is_mapping(value), f"{dotted} stops at a non-mapping before '{part}'"
        value = value[part]
    return value


@pytest.mark.parametrize("selectivity", list(bench_filtered.Selectivity))
def test_the_filter_key_resolves_to_the_bucket_the_payload_carries(
    selectivity: bench_filtered.Selectivity,
) -> None:
    # Arrange
    payload = bench_qdrant.point_payload("node-7", content="row seven")
    wanted = bench_qdrant.bucket_filter(selectivity)

    # Act
    resolved = _resolve(payload, wanted.field or "")

    # Assert
    assert wanted.op is FilterOp.EQ
    assert wanted.value is True
    assert resolved is bench_filtered.in_bucket("node-7", selectivity)


def test_a_payload_index_is_built_over_every_bucket_field_and_nothing_else() -> None:
    assert bench_qdrant.payload_index_fields() == tuple(
        bench_qdrant.bucket_filter(selectivity).field for selectivity in bench_filtered.Selectivity
    )


def test_the_two_arms_are_named_for_what_differs_between_them() -> None:
    assert [arm.value for arm in bench_qdrant.PayloadIndexing] == [
        "no payload index",
        "payload index before ingest",
    ]
