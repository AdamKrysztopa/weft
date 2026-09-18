"""Unit tests for `weft_retrieve.shingle_resemblance` — ledger task **32.4**.

Broder, "On the resemblance and containment of documents" (Compression and Complexity of
Sequences 1997): the resemblance of A and B is |S(A,w) ∩ S(B,w)| / |S(A,w) ∪ S(B,w)| over their
sets of w-token shingles. A passage whose resemblance to a higher-ranked **kept** passage meets
the threshold is dropped. Computed exactly — no min-hash sketch.

Most cases below use `shingle_size=1`, where a shingle is one token and the resemblance of two
passages is the Jaccard index of their word sets, so each expected verdict is checkable by hand.
Tokens are Unicode words, casefolded: `jaźń` is one token, and a tokenizer that split it at the
non-ASCII letters would make it equal to `ja ń`.
"""

import pytest
from pydantic import ValidationError

from weft_kernel.context import Context
from weft_kernel.payload import MediaType, Node, Produced
from weft_retrieve.contract import Reranker
from weft_retrieve.payload import Passage, Query, Ranking
from weft_retrieve.shingle_resemblance import NAME, ShingleResemblance, ShingleResemblanceConfig
from weft_store.contract import Scored


def _ctx() -> Context:
    return Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")


def _hit(content: str, *, score: float, rank: int) -> Passage:
    node = Node.synthetic(content=content, media_type=MediaType.TEXT, reason="shingle fixture")
    return Passage(scored=Scored(value=node, score=score), rank=rank, retrieved_by="vector-top-k")


def _ranking(*contents: str) -> Ranking:
    hits = tuple(
        _hit(content, score=1.0 - rank / 10, rank=rank) for rank, content in enumerate(contents)
    )
    return Ranking(origin=Query(text="which passages?"), hits=hits, contributors=("vector",))


async def _kept(ranking: Ranking, config: ShingleResemblanceConfig) -> list[str]:
    outcome = await ShingleResemblance(config).run(ranking, _ctx())
    assert isinstance(outcome, Produced)
    return [hit.node.content for hit in outcome.value.hits]


def test_it_is_selectable_by_the_measure_it_computes_and_is_a_reranker() -> None:
    # Act / Assert
    assert NAME == "shingle-resemblance"
    assert isinstance(ShingleResemblance(ShingleResemblanceConfig()), Reranker)


def test_the_defaults_are_the_values_broder_and_his_coauthors_used() -> None:
    # Act
    config = ShingleResemblanceConfig()

    # Assert — "a 50% resemblance" and "The shingle size w is 10" (Broder et al., WWW6 1997).
    assert config.threshold == 0.5
    assert config.shingle_size == 10


@pytest.mark.parametrize(
    ("field", "value"), [("threshold", 0.0), ("threshold", 1.5), ("shingle_size", 0)]
)
def test_a_threshold_outside_zero_to_one_or_an_empty_shingle_is_refused(
    field: str, value: float
) -> None:
    # Act / Assert
    with pytest.raises(ValidationError):
        ShingleResemblanceConfig.model_validate({field: value})


async def test_a_passage_at_the_threshold_is_dropped_and_one_below_it_is_kept() -> None:
    # Arrange — w = 1. A {a b c d}; B {a b c e}: 3/5 = 0.6 ≥ 0.5, dropped.
    # C {a b x y}: against A 2/6 = 0.33, kept.
    ranking = _ranking("a b c d", "a b c e", "a b x y")

    # Act
    kept = await _kept(ranking, ShingleResemblanceConfig(shingle_size=1))

    # Assert
    assert kept == ["a b c d", "a b x y"]


async def test_a_passage_is_compared_only_with_passages_that_were_kept() -> None:
    # Arrange — w = 1. B {a b c e} is dropped against A {a b c d} (0.6). C {b c e f} resembles
    # the dropped B at 3/5 = 0.6 but the kept A only at 2/6 = 0.33, so C stays.
    ranking = _ranking("a b c d", "a b c e", "b c e f")

    # Act
    kept = await _kept(ranking, ShingleResemblanceConfig(shingle_size=1))

    # Assert
    assert kept == ["a b c d", "b c e f"]


async def test_case_and_punctuation_do_not_make_a_copy_look_different() -> None:
    # Arrange
    ranking = _ranking("The quick brown fox.", "the QUICK, brown fox!")

    # Act
    kept = await _kept(ranking, ShingleResemblanceConfig(shingle_size=2))

    # Assert
    assert kept == ["The quick brown fox."]


async def test_a_polish_word_is_one_token_not_split_at_its_diacritics() -> None:
    # Arrange — split at non-ASCII letters, "jaźń" would become {ja, ń} and equal the second.
    ranking = _ranking("jaźń", "ja ń")

    # Act
    kept = await _kept(ranking, ShingleResemblanceConfig(shingle_size=1))

    # Assert
    assert kept == ["jaźń", "ja ń"]


async def test_a_passage_shorter_than_the_shingle_is_its_own_single_shingle() -> None:
    # Arrange — three tokens against w = 10: each passage is one shingle, the whole sequence.
    ranking = _ranking("short passage here", "Short passage here.", "another short one")

    # Act
    kept = await _kept(ranking, ShingleResemblanceConfig())

    # Assert
    assert kept == ["short passage here", "another short one"]


async def test_survivors_keep_their_scores_and_are_renumbered() -> None:
    # Arrange
    ranking = _ranking("a b c d", "a b c d", "x y z w")

    # Act
    outcome = await ShingleResemblance(ShingleResemblanceConfig(shingle_size=1)).run(
        ranking, _ctx()
    )

    # Assert
    assert isinstance(outcome, Produced)
    assert [hit.score for hit in outcome.value.hits] == [1.0, 0.8]
    assert [hit.rank for hit in outcome.value.hits] == [0, 1]
    assert outcome.value.contributors == ("vector",)


async def test_an_empty_ranking_passes_through() -> None:
    # Arrange
    empty = Ranking(origin=Query(text="nothing"), contributors=("vector",))

    # Act
    outcome = await ShingleResemblance(ShingleResemblanceConfig()).run(empty, _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value.hits == ()
    assert outcome.value.contributors == ("vector",)
