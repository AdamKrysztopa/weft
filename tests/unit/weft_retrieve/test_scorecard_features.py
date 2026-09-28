"""A `Scorecard` carries typed features — task 44.12a, gate G27 position 1.

A routing rule tests named features of the question and the corpus. They ride on the `Scorecard`
every policy already receives, as an open key space (FF4: no closed enumeration of names), with
scalar values only. Adding the field is `09`'s "optional field on a returned model" row: a minor
for both audiences, so the family moves 1.1.0 → 1.2.0.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from weft_retrieve import RETRIEVE_CONTRACT_VERSION
from weft_retrieve.payload import Query, Scorecard


def _card(**fields: object) -> Scorecard:
    return Scorecard.model_validate({"query": Query(text="q"), "scores": {}, **fields})


def test_a_scorecard_written_before_features_still_validates() -> None:
    # Act
    card = _card()

    # Assert
    assert card.features == {}


def test_features_hold_counts_flags_and_sizes_outside_the_score_range() -> None:
    # Act
    card = _card(
        features={"query.word_count": 42, "query.cue.comparison": True, "corpus.ratio": 3.5}
    )

    # Assert
    assert card.features["query.word_count"] == 42
    assert card.features["query.cue.comparison"] is True


def test_features_survive_a_json_round_trip() -> None:
    # Arrange
    card = _card(features={"query.word_count": 7, "query.cue.temporal": False})

    # Act
    again = Scorecard.model_validate_json(card.model_dump_json())

    # Assert
    assert again == card


def test_a_feature_that_is_not_a_scalar_is_refused() -> None:
    # Act / Assert
    with pytest.raises(ValidationError):
        _card(features={"query.anchors": ["LX-450"]})


def test_adding_features_is_a_minor_contract_version() -> None:
    # Assert
    assert RETRIEVE_CONTRACT_VERSION == "1.2.0"
