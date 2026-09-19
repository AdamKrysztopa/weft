"""`scripts/pool_power.py` — ledger **40.6**: power frozen before any reordering arm runs.

Each contrast's paired difference is bounded before any outcome exists, so its sd bound, and the
effect that sd could detect, are quantities no arm can move (`eval/pool-promotion/protocol.toml` →
`[effect]`): a reorderer against dense differs by at most `max(RR@5, oracle gain)` on a question,
and two reorderers of one pool by at most whether any relevant chunk is in it.
"""

from __future__ import annotations

import math

import pytest
from pool_ceilings import QuestionCeiling
from pool_power import power_for, slices_from


def _ceiling(identifier: str, *, rr5: float, oracle: float, in_pool: bool) -> QuestionCeiling:
    return QuestionCeiling(
        question_id=identifier,
        rr5=rr5,
        any_relevant_in_pool=in_pool,
        best_relevant_rank=1 if in_pool else None,
        distinct_documents=10,
        rule_fires=True,
        oracle_gain=oracle,
        promotion_gain=0.0,
    )


def test_each_slices_bound_mde_and_required_n_follow_the_protocols_formulae() -> None:
    # Arrange — four questions; the slice holds the first two.
    ceilings = (
        _ceiling("q-1", rr5=1.0, oracle=0.0, in_pool=True),
        _ceiling("q-2", rr5=0.0, oracle=1.0, in_pool=True),
        _ceiling("q-3", rr5=0.5, oracle=0.5, in_pool=True),
        _ceiling("q-4", rr5=0.0, oracle=0.0, in_pool=False),
    )

    # Act
    power = power_for(ceilings, {"all": {"q-1", "q-2", "q-3", "q-4"}, "some": {"q-1", "q-2"}})

    # Assert
    everything = power["all"]
    assert everything.n == 4
    assert everything.sd_against_dense == pytest.approx(math.sqrt((1 + 1 + 0.25 + 0) / 4))
    assert everything.sd_between_reorderers == pytest.approx(math.sqrt(3 / 4))
    assert everything.mde_against_dense == pytest.approx(2.8 * everything.sd_against_dense / 2)
    assert everything.n_required == math.ceil((2.8 * everything.sd_against_dense / 0.05) ** 2)
    assert everything.underpowered is True
    assert power["some"].n == 2
    assert power["some"].sd_against_dense == pytest.approx(1.0)


def test_a_slice_naming_a_question_the_ceilings_do_not_hold_is_refused() -> None:
    # Arrange
    ceilings = (_ceiling("q-1", rr5=1.0, oracle=0.0, in_pool=True),)

    # Act
    with pytest.raises(ValueError, match="q-9"):
        power_for(ceilings, {"all": {"q-1", "q-9"}})


def test_slices_are_every_axis_value_the_labelled_population_and_the_identifier_exact_yes() -> None:
    # Arrange
    ceilings = (
        _ceiling("q-1", rr5=1.0, oracle=0.0, in_pool=True),
        _ceiling("q-2", rr5=0.0, oracle=1.0, in_pool=True),
        _ceiling("q-3", rr5=0.5, oracle=0.5, in_pool=True),
    )
    axes = {"q-1": {"split": "test"}, "q-2": {"split": "train"}, "q-3": {"split": "test"}}

    # Act
    slices = slices_from(ceilings, axes, labelled={"q-1", "q-2"}, identifier_exact={"q-2"})

    # Assert
    assert slices["all"] == {"q-1", "q-2", "q-3"}
    assert slices["split=test"] == {"q-1", "q-3"}
    assert slices["oracle-labelled"] == {"q-1", "q-2"}
    assert slices["identifier-exact=yes"] == {"q-2"}
    assert slices["rule-fires=true"] == {"q-1", "q-2", "q-3"}
