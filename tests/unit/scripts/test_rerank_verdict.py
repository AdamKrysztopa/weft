"""`scripts/rerank_verdict.py` — ledger **41.3**: the verdict of `protocol.toml` → `[phase_41]`.

Each cross-encoder arm is read against 40.8's dense record by `40.0`'s verdict and against
`anchor-promote`'s descriptively; two repetitions whose verdicts differ read *unstable*; and records
are paired only when they replayed one manifest over one question set — `40.2`'s rule, which
nothing enforced until this script (`L28.4`).
"""

from __future__ import annotations

import pytest
from rerank_verdict import PoolIdentity, require_one_pool, stable


def test_two_repetitions_that_agree_carry_their_verdict() -> None:
    assert stable("positive, below worthwhile", "positive, below worthwhile") == (
        "positive, below worthwhile"
    )


def test_two_repetitions_that_disagree_read_unstable_naming_both() -> None:
    assert stable("worthwhile", "positive, below worthwhile") == (
        "unstable: worthwhile / positive, below worthwhile"
    )


def test_records_from_one_manifest_and_question_set_pair() -> None:
    same = PoolIdentity(pool_manifest="m1", question_set_digest="q1")

    require_one_pool({"dense": same, "cross-encoder-bge r1": same})


@pytest.mark.parametrize(
    "other",
    [
        PoolIdentity(pool_manifest="m2", question_set_digest="q1"),
        PoolIdentity(pool_manifest="m1", question_set_digest="q2"),
        PoolIdentity(pool_manifest=None, question_set_digest="q1"),
    ],
    ids=["another-manifest", "another-question-set", "not-a-replay"],
)
def test_a_record_from_another_pool_is_refused_by_name(other: PoolIdentity) -> None:
    same = PoolIdentity(pool_manifest="m1", question_set_digest="q1")

    with pytest.raises(ValueError, match="cross-encoder-bge r2"):
        require_one_pool({"dense": same, "cross-encoder-bge r2": other})
