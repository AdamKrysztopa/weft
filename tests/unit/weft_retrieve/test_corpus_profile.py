"""A corpus profile gives routing rules `corpus.*` features, omitting unknowns — task **44.15**.

Built from the `list_sources()` read an ask already makes (never a second scan), from what
`weft index` recorded per source (`SourceStats`, 44.13) and each source's layers. A feature whose
value is not known — sizes no index run recorded, tokens counted by two different tokenizers, a
context size no role declared — is left out, never guessed: a rule that tests a missing feature
does not match.
"""

from __future__ import annotations

from datetime import UTC, datetime

from weft_kernel.context import Context
from weft_kernel.payload import Produced, SourceId
from weft_retrieve.payload import Query
from weft_retrieve.profile import CorpusProfile, corpus_profile
from weft_retrieve.routing import QueryProfileScorer
from weft_store import LayerRecord, LayerStatus, SourceRecord, SourceStats, SourceStatus

_NOW = datetime.now(UTC)


def _layer(name: str, status: LayerStatus) -> LayerRecord:
    return LayerRecord(name=name, pipeline_identity="p", status=status, attempts=1, at=_NOW)


def _source(
    identifier: str,
    *,
    stats: SourceStats | None = None,
    layers: tuple[LayerRecord, ...] = (),
    status: SourceStatus = SourceStatus.ACTIVE,
) -> SourceRecord:
    return SourceRecord(
        id=SourceId(identifier),
        uri=f"file:///{identifier}.txt",
        content_hash=identifier,
        indexed_at=_NOW,
        pipeline="index-text",
        status=status,
        stats=stats,
        layers=layers,
    )


def _stats(leaves: int, tokens: int | None = None, tokenizer: str | None = None) -> SourceStats:
    return SourceStats(leaves=leaves, characters=leaves * 100, tokens=tokens, tokenizer=tokenizer)


def test_sizes_sum_over_active_sources_and_become_features() -> None:
    # Arrange
    records = (
        _source("a", stats=_stats(3, tokens=300, tokenizer="luna")),
        _source("b", stats=_stats(2, tokens=200, tokenizer="luna")),
    )

    # Act
    profile = corpus_profile(records, context_tokens=1000)
    features = profile.features()

    # Assert
    assert features["corpus.documents"] == 2
    assert features["corpus.leaves"] == 5
    assert features["corpus.leaf_tokens"] == 500
    assert features["corpus.fits_context"] is True


def test_a_source_with_no_recorded_size_leaves_the_sizes_out() -> None:
    # Arrange
    records = (_source("a", stats=_stats(3, tokens=300, tokenizer="luna")), _source("b"))

    # Act
    features = corpus_profile(records, context_tokens=1000).features()

    # Assert
    assert features["corpus.documents"] == 2
    assert "corpus.leaves" not in features
    assert "corpus.leaf_tokens" not in features
    assert "corpus.fits_context" not in features


def test_tokens_from_two_tokenizers_are_not_summed() -> None:
    # Arrange
    records = (
        _source("a", stats=_stats(3, tokens=300, tokenizer="luna")),
        _source("b", stats=_stats(2, tokens=200, tokenizer="other-model")),
    )

    # Act
    profile = corpus_profile(records, context_tokens=1000)

    # Assert
    assert profile.leaf_tokens is None
    assert profile.leaf_tokens_complete is False
    assert profile.features()["corpus.leaves"] == 5
    assert "corpus.leaf_tokens" not in profile.features()


def test_a_corpus_larger_than_the_context_does_not_fit_and_an_unknown_context_says_nothing() -> (
    None
):
    # Arrange
    records = (_source("a", stats=_stats(3, tokens=1100, tokenizer="luna")),)

    # Act
    too_big = corpus_profile(records, context_tokens=1000).features()
    unknown = corpus_profile(records, context_tokens=None).features()

    # Assert
    assert too_big["corpus.fits_context"] is False
    assert "corpus.fits_context" not in unknown


def test_a_layer_is_ready_only_when_built_on_every_active_source() -> None:
    # Arrange
    records = (
        _source(
            "a",
            layers=(
                _layer("questions", LayerStatus.ACTIVE),
                _layer("summary", LayerStatus.ACTIVE),
                _layer("raptor", LayerStatus.STALE),
            ),
        ),
        _source(
            "b",
            layers=(
                _layer("questions", LayerStatus.ACTIVE),
                _layer("summary", LayerStatus.INDEXING),
                _layer("raptor", LayerStatus.STALE),
            ),
        ),
    )

    # Act
    features = corpus_profile(records, context_tokens=None).features()

    # Assert
    assert features["corpus.layer.questions.ready"] is True
    assert features["corpus.layer.summary.ready"] is False
    assert features["corpus.layer.raptor.ready"] is False
    assert features["corpus.fully_enriched"] is False


def test_every_layer_ready_is_fully_enriched_and_no_layer_is_not() -> None:
    # Arrange
    enriched = (_source("a", layers=(_layer("questions", LayerStatus.ACTIVE),)),)
    plain = (_source("a"),)

    # Act / Assert
    assert corpus_profile(enriched, context_tokens=None).features()["corpus.fully_enriched"] is True
    assert corpus_profile(plain, context_tokens=None).features()["corpus.fully_enriched"] is False


async def test_the_query_profile_scorer_adds_the_corpus_features_when_the_service_is_present() -> (
    None
):
    # Arrange
    profile = corpus_profile((_source("a", stats=_stats(3)),), context_tokens=None)
    with_corpus = Context(tenant_id="t", run_id="r", trace_id="x", locale="en")
    with_corpus.services.add(CorpusProfile, profile)
    without = Context(tenant_id="t", run_id="r", trace_id="x", locale="en")
    scorer = QueryProfileScorer()

    # Act
    scored = await scorer.run(Query(text="How many looms are there?"), with_corpus)
    bare = await scorer.run(Query(text="How many looms are there?"), without)

    # Assert
    assert isinstance(scored, Produced) and isinstance(bare, Produced)
    assert scored.value.features["corpus.documents"] == 1
    assert "query.word_count" in scored.value.features
    assert not any(key.startswith("corpus.") for key in bare.value.features)


def test_a_corpus_fits_each_role_by_its_own_window_and_the_plain_fit_stays_generates() -> None:
    # Arrange — R44.20b: one corpus of 1,100 tokens, two roles with two different windows.
    records = (_source("a", stats=_stats(3, tokens=1100, tokenizer="luna")),)

    # Act
    features = corpus_profile(
        records,
        context_tokens=2000,
        role_context_tokens={"generate": 2000, "small": 1000},
    ).features()

    # Assert
    assert features["corpus.fits_context"] is True
    assert features["corpus.fits_context.generate"] is True
    assert features["corpus.fits_context.small"] is False


def test_a_role_with_no_declared_window_has_no_fit_feature_and_never_borrows_anothers() -> None:
    # Arrange
    records = (_source("a", stats=_stats(3, tokens=1100, tokenizer="luna")),)

    # Act
    features = corpus_profile(
        records,
        context_tokens=2000,
        role_context_tokens={"generate": 2000, "unsized": None},
    ).features()

    # Assert
    assert "corpus.fits_context.unsized" not in features
    assert "corpus.fits_context.generate" in features


def test_an_unsized_corpus_has_no_per_role_fit_at_all() -> None:
    # Arrange
    records = (_source("a", stats=_stats(3)),)

    # Act
    features = corpus_profile(
        records, context_tokens=2000, role_context_tokens={"generate": 2000}
    ).features()

    # Assert
    assert not [name for name in features if name.startswith("corpus.fits_context")]


def test_the_profile_under_a_role_mapping_reads_every_declared_window() -> None:
    # Arrange
    from weft_llm.roles import RoleMapping

    records = (_source("a", stats=_stats(3, tokens=1100, tokenizer="luna")),)
    roles = {
        "generate": RoleMapping(provider="scripted", context_tokens=2000),
        "small": RoleMapping(provider="scripted", context_tokens=1000),
        "unsized": RoleMapping(provider="scripted"),
    }

    # Act
    from weft_retrieve.profile import corpus_profile_under

    features = corpus_profile_under(records, roles).features()

    # Assert
    assert features["corpus.fits_context"] is True
    assert features["corpus.fits_context.small"] is False
    assert "corpus.fits_context.unsized" not in features


def test_the_profile_under_no_generate_role_has_no_plain_fit() -> None:
    # Arrange
    from weft_llm.roles import RoleMapping
    from weft_retrieve.profile import corpus_profile_under

    records = (_source("a", stats=_stats(3, tokens=1100, tokenizer="luna")),)

    # Act
    features = corpus_profile_under(
        records, {"small": RoleMapping(provider="scripted", context_tokens=1000)}
    ).features()

    # Assert
    assert "corpus.fits_context" not in features
    assert features["corpus.fits_context.small"] is False


_SIZED = _stats(3, tokens=300, tokenizer="luna")
_EXTENTS = (
    "corpus.leaves",
    "corpus.leaf_tokens",
    "corpus.fits_context",
    "corpus.fits_context.generate",
)


def test_a_fully_indexed_corpus_is_base_complete_and_states_its_extent() -> None:
    # Arrange
    records = (_source("a", stats=_SIZED), _source("b", stats=_SIZED))

    # Act
    features = corpus_profile(
        records, context_tokens=1000, role_context_tokens={"generate": 1000}
    ).features()

    # Assert
    assert features["corpus.base_complete"] is True
    assert features["corpus.sources_pending"] == 0
    assert features["corpus.sources_failed"] == 0
    assert all(name in features for name in _EXTENTS)


def test_a_fast_track_corpus_still_indexing_states_no_extent_a_rule_could_mistake_for_whole() -> (
    None
):
    # Arrange — two sources searchable and one in flight: 600 tokens is a subset, not the corpus.
    records = (
        _source("a", stats=_SIZED),
        _source("b", stats=_SIZED),
        _source("c", status=SourceStatus.INDEXING),
    )

    # Act
    profile = corpus_profile(records, context_tokens=1000, role_context_tokens={"generate": 1000})
    features = profile.features()

    # Assert
    assert features["corpus.base_complete"] is False
    assert features["corpus.documents"] == 2
    assert features["corpus.sources_pending"] == 1
    assert not [name for name in _EXTENTS if name in features]


def test_a_failed_source_is_a_corpus_missing_a_document_and_so_not_base_complete() -> None:
    # Arrange
    records = (_source("a", stats=_SIZED), _source("b", status=SourceStatus.FAILED))

    # Act
    features = corpus_profile(records, context_tokens=1000).features()

    # Assert
    assert features["corpus.base_complete"] is False
    assert features["corpus.sources_failed"] == 1
    assert "corpus.leaf_tokens" not in features


def test_no_searchable_source_is_not_a_complete_corpus_of_anything() -> None:
    # Act
    features = corpus_profile((), context_tokens=1000).features()

    # Assert
    assert features["corpus.base_complete"] is False


def test_enrichment_incomplete_on_a_complete_base_is_told_apart_from_the_reverse() -> None:
    # Arrange
    raptor_on_one = (
        _source("a", stats=_SIZED, layers=(_layer("raptor", LayerStatus.ACTIVE),)),
        _source("b", stats=_SIZED),
    )

    # Act
    features = corpus_profile(raptor_on_one, context_tokens=1000).features()

    # Assert
    assert features["corpus.base_complete"] is True
    assert features["corpus.layer.raptor.ready"] is False
    assert features["corpus.fully_enriched"] is False


def test_a_layer_built_on_every_searchable_source_is_not_ready_while_the_base_is_incomplete() -> (
    None
):
    # Arrange — raptor reaches both searchable sources; a third is still being indexed.
    records = (
        _source("a", stats=_SIZED, layers=(_layer("raptor", LayerStatus.ACTIVE),)),
        _source("b", stats=_SIZED, layers=(_layer("raptor", LayerStatus.ACTIVE),)),
        _source("c", status=SourceStatus.INDEXING),
    )

    # Act
    profile = corpus_profile(records, context_tokens=1000)
    features = profile.features()

    # Assert
    assert profile.layers["raptor"].ready is True
    assert features["corpus.layer.raptor.ready"] is False
    assert features["corpus.fully_enriched"] is False


def test_finishing_the_last_source_makes_the_same_corpus_complete_and_its_extent_appears() -> None:
    # Arrange
    layers = (_layer("raptor", LayerStatus.ACTIVE),)
    during = (
        _source("a", stats=_SIZED, layers=layers),
        _source("b", status=SourceStatus.INDEXING),
    )
    after = (_source("a", stats=_SIZED, layers=layers), _source("b", stats=_SIZED, layers=layers))

    # Act
    before_features = corpus_profile(during, context_tokens=1000).features()
    after_features = corpus_profile(after, context_tokens=1000).features()

    # Assert
    assert before_features["corpus.base_complete"] is False
    assert "corpus.leaf_tokens" not in before_features
    assert after_features["corpus.base_complete"] is True
    assert after_features["corpus.leaf_tokens"] == 600
    assert after_features["corpus.layer.raptor.ready"] is True
