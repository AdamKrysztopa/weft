"""Cue lexicons and the one locale fallback — task 44.10.

A cue is a phrase family a question's wording can carry — comparing, aggregating, asking about the
whole collection, about time, or across documents — that the query profile reports as a feature.
The phrases are configuration, keyed by locale, authored for Weft. A locale is resolved exactly as
every other locale-keyed table in `weft_retrieve` resolves it: exact, then its primary subtag, then
English; and the profile is told which locale was used, so a fallback is visible.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from weft_retrieve.locale import resolve_locale
from weft_retrieve.profile_cues import DEFAULT_CUES, CueLexicon, CueName


def test_the_five_cues_are_the_named_ones() -> None:
    # Assert
    assert {cue.value for cue in CueName} == {
        "comparison",
        "aggregation",
        "global",
        "temporal",
        "cross-document",
    }


@pytest.mark.parametrize("locale", ["en", "pl"])
def test_each_default_locale_gives_every_cue_phrases(locale: str) -> None:
    # Act
    phrases, resolved = DEFAULT_CUES.for_locale(locale)

    # Assert
    assert resolved == locale
    assert set(phrases) == set(CueName)
    assert all(phrases[cue] for cue in CueName)


@pytest.mark.parametrize(
    ("asked", "resolved"), [("pl-PL", "pl"), ("de", "en"), ("de-AT", "en"), (None, "en")]
)
def test_a_locale_resolves_exact_then_primary_then_english(
    asked: str | None, resolved: str
) -> None:
    # Act
    _, used = DEFAULT_CUES.for_locale(asked)

    # Assert
    assert used == resolved


def test_resolving_against_a_table_with_no_english_and_no_match_finds_nothing() -> None:
    # Act / Assert
    assert resolve_locale("de", ("pl",)) is None
    assert resolve_locale("pl-PL", ("pl",)) == "pl"


def test_a_phrase_that_is_not_lower_case_is_refused() -> None:
    # Act / Assert
    with pytest.raises(ValidationError, match="lower"):
        CueLexicon.model_validate({"phrases": {"en": {"comparison": ("Versus",)}}})


def test_a_phrase_repeated_within_one_cue_is_refused() -> None:
    # Act / Assert
    with pytest.raises(ValidationError, match="versus"):
        CueLexicon.model_validate({"phrases": {"en": {"comparison": ("versus", "versus")}}})


def test_an_unknown_cue_is_refused_naming_the_cues() -> None:
    # Act
    with pytest.raises(ValidationError) as refused:
        CueLexicon.model_validate({"phrases": {"en": {"sarcasm": ("as if",)}}})

    # Assert
    assert "cross-document" in str(refused.value)


def test_a_locale_may_leave_a_cue_out_and_reads_as_no_phrases() -> None:
    # Arrange
    lexicon = CueLexicon.model_validate({"phrases": {"en": {"temporal": ("since",)}}})

    # Act
    phrases, _ = lexicon.for_locale("en")

    # Assert
    assert phrases[CueName.TEMPORAL] == ("since",)
    assert phrases[CueName.COMPARISON] == ()
