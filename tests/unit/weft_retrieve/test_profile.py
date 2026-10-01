"""The query profile — task 44.11.

`profile_query` describes a question's shape with no model call: how long it is, which exact spans
it names (the anchors `find_anchors` already finds), and which cue families its wording carries in
its own language. The same text, locale and lexicon always give the same profile, and its features
are the names a routing rule tests and an evidence claim cites.
"""

from __future__ import annotations

from collections import Counter

import pytest

from weft_retrieve.intent_and_anchors import AnchorKind, find_anchors
from weft_retrieve.profile import PROFILER_VERSION, profile_query
from weft_retrieve.profile_cues import CueLexicon, CueName

_LEXICON = CueLexicon.model_validate(
    {
        "phrases": {
            "en": {
                "comparison": ("versus", "compared with"),
                "aggregation": ("how many",),
                "global": ("across the collection",),
                "temporal": ("since",),
                "cross-document": ("both documents",),
            },
            "pl": {"comparison": ("w porównaniu",)},
        }
    }
)


def test_words_are_counted() -> None:
    # Act
    profile = profile_query("What keeps the warp under tension?", locale="en", cues=_LEXICON)

    # Assert
    assert profile.word_count == 6


def test_anchors_are_the_ones_find_anchors_finds_counted_by_kind() -> None:
    # Arrange
    text = 'Does "warp tension" limit loom model LX-450 on the Tamsel line?'

    # Act
    profile = profile_query(text, locale="en", cues=_LEXICON, entities=("Tamsel",))

    # Assert
    expected = Counter(anchor.kind for anchor in find_anchors(text, entities=("Tamsel",)))
    assert profile.anchors[AnchorKind.QUOTED] == expected[AnchorKind.QUOTED] >= 1
    assert profile.anchors[AnchorKind.ENTITY] == expected[AnchorKind.ENTITY] >= 1
    assert profile.anchors[AnchorKind.IDENTIFIER] == expected[AnchorKind.IDENTIFIER]


def test_a_cue_fires_on_whole_words_case_folded() -> None:
    # Act
    fires = profile_query("HOW MANY looms, versus spindles?", locale="en", cues=_LEXICON)
    silent = profile_query("A versusian loom somehow manyfold?", locale="en", cues=_LEXICON)

    # Assert
    assert fires.cues == frozenset({CueName.AGGREGATION, CueName.COMPARISON})
    assert silent.cues == frozenset()


def test_a_question_s_own_language_decides_its_cues() -> None:
    # Act
    polish = profile_query("Jak wypada X w porównaniu z Y?", locale="pl-PL", cues=_LEXICON)

    # Assert
    assert polish.cues == frozenset({CueName.COMPARISON})
    assert polish.locale_used == "pl"
    assert polish.features()["query.locale_fallback"] is False


def test_an_unknown_language_falls_back_to_english_and_says_so() -> None:
    # Act
    profile = profile_query("Wie viele, since when?", locale="de", cues=_LEXICON)

    # Assert
    assert profile.locale_used == "en"
    assert CueName.TEMPORAL in profile.cues
    assert profile.features()["query.locale_fallback"] is True


def test_features_name_every_key_a_rule_can_test() -> None:
    # Act
    features = profile_query("How many looms?", locale="en", cues=_LEXICON).features()

    # Assert
    expected = {
        "query.word_count",
        "query.anchor.identifier",
        "query.anchor.quoted",
        "query.anchor.entity",
        "query.locale_fallback",
    } | {f"query.cue.{cue.value}" for cue in CueName}
    assert set(features) == expected
    assert features["query.word_count"] == 3
    assert features["query.cue.aggregation"] is True
    assert features["query.cue.comparison"] is False


def test_the_same_question_gives_the_same_profile() -> None:
    # Act
    first = profile_query("Since when, versus what?", locale="en", cues=_LEXICON)
    second = profile_query("Since when, versus what?", locale="en", cues=_LEXICON)

    # Assert
    assert first == second
    assert first.profiler_version == PROFILER_VERSION != ""


@pytest.mark.parametrize(
    "text",
    ["", "   ", "​​", "🧵🧵 versus 🧶", "a" * 10_000, "\x00\x7f", "日本語の質問ですか", "««»»\"\"''"],
)
def test_any_text_profiles_without_raising(text: str) -> None:
    # Act
    features = profile_query(text, locale="en", cues=_LEXICON).features()

    # Assert
    assert {f"query.cue.{cue.value}" for cue in CueName} <= set(features)
    assert isinstance(features["query.word_count"], int)


def test_every_feature_a_real_profile_emits_is_declared() -> None:
    # Arrange — R44.15: the vocabulary a rule is checked against is derived from nothing, so
    # it is compared with what the two profilers actually emit, with every optional key present.
    from weft_retrieve.profile import CorpusProfile, LayerState, is_declared_feature

    query = profile_query("Compare X with Y", locale="en")
    corpus = CorpusProfile(
        documents=2,
        leaves=3,
        leaf_tokens=10,
        leaf_tokens_complete=True,
        layers={"enrich-with-questions": LayerState(built=1, of=2, ready=False)},
        fully_enriched=False,
        base_complete=True,
        sources_pending=0,
        sources_failed=0,
        fits_context=True,
        fits_context_by_role={"small": False},
    )

    # Act
    emitted = {*query.features(), *corpus.features()}

    # Assert
    assert {name for name in emitted if not is_declared_feature(name)} == set()
    assert len(emitted) > 10


def test_a_misspelt_feature_is_not_declared() -> None:
    from weft_retrieve.profile import is_declared_feature

    assert not is_declared_feature("corpus.fits_contxt")
    assert not is_declared_feature("query.cue.nonsense")
    assert not is_declared_feature("corpus.layer..ready")


def test_a_per_role_fit_is_declared_by_shape_and_an_empty_role_is_not() -> None:
    from weft_retrieve.profile import is_declared_feature

    assert is_declared_feature("corpus.fits_context.generate")
    assert is_declared_feature("corpus.fits_context.long-context")
    assert not is_declared_feature("corpus.fits_context.")


def test_the_role_a_fit_feature_is_about_is_read_from_its_name() -> None:
    from weft_retrieve.profile import fits_context_role

    assert fits_context_role("corpus.fits_context") == "generate"
    assert fits_context_role("corpus.fits_context.long-context") == "long-context"
    assert fits_context_role("corpus.leaf_tokens") is None
    assert fits_context_role("corpus.fits_context.") is None
