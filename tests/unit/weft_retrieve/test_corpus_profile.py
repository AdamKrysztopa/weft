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
        _source("c", status=SourceStatus.FAILED),
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
