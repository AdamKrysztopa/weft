"""`weft ask --explain` — ledger task **21.1**.

`03` → *Output*, *Score display* decided in Phase 0 that a human sees rank order and never the raw
number, and the reason is still true: `Scored.score` is a similarity, unbounded and routinely
negative with the hash embedder, and a bare `-0.31` reads as broken to somebody with no context
for it. What that decision left is a ladder whose output cannot be inspected by the person climbing
it — `12-roadmap.md` §4 measured `--explain` and `score_semantics` as appearing **zero** times in
this tree, and §5c is why the phase exists.

**The number is shown only with its meaning, and the meaning comes from whatever produced it.**
That is the ⚠ on `21.1`'s ledger line, and it is the shape this file pins: a `score_semantics`
declaration read **defensively off the producer**, the same `getattr(..., default)` idiom
`weft_kernel.runner` uses for `lifetime`/`requires`/`provides` and for the same reason — a
`ClassVar` on a `@runtime_checkable` Protocol becomes a *required* `isinstance` member, and a
third-party retriever that never restates it would fail a capability check that has nothing to do
with capability (`02` → *What a plugin receives*, the Phase 0 step 7 narrowing).

**No central list and no kernel-named enum.** `12` §5c says that if a task finds itself inventing
an enum of score meanings, that is a closed key space the kernel would have to name and the phase
has found a gate rather than a bug. It did not: a producer writes an English sentence beside the
code that computes the number, which is G11's own answer for error text applied to a score.

**Two producers, because there are two.** A `Retriever` has one `run` and declares
`score_semantics`. `PgVectorStore` satisfies *two* published capabilities that produce
incommensurable numbers — `VectorSearch` returns `1 - cosine distance`, `TextSearch` returns
whatever `ts_rank_cd` says under the normalization `21.0` made selectable — so it declares one per
capability rather than one per class. A single `score_semantics` on that class would have to
describe two different numbers, which is the field being wrong rather than the class being awkward.
"""

from __future__ import annotations

from typing import ClassVar

from pydantic import SecretStr

from weft_cli.explain import (
    ScoreExplanation,
    arm_explanations,
    explanations_for,
    incomparable_note,
)
from weft_qdrant.store import QdrantStore
from weft_retrieve.hybrid import Hybrid
from weft_store import PgVectorSettings, PgVectorStore
from weft_store.pgvector_store import TextMode


class _DeclaringRetriever:
    """A retriever that says what its number means, the way a third party's would."""

    score_semantics: ClassVar[str] = "cosine similarity in [-1, 1]; higher is nearer"


class _SilentRetriever:
    """One that declares nothing — which must render as an absence, never as a guess."""


def test_a_producer_that_declares_its_semantics_has_them_read_off_it() -> None:
    # Arrange / Act
    explanation = ScoreExplanation.of(_DeclaringRetriever(), produced_by="acme-retriever")

    # Assert
    assert explanation.produced_by == "acme-retriever"
    assert explanation.semantics == "cosine similarity in [-1, 1]; higher is nearer"


def test_a_producer_that_declares_nothing_says_so_rather_than_guessing() -> None:
    """An absence is a fact.

    Inventing a plausible sentence for a plugin that never wrote one is the silent-fallback shape
    `CLAUDE.md` refuses: a reader cannot tell it from a real claim.
    """
    # Arrange / Act
    explanation = ScoreExplanation.of(_SilentRetriever(), produced_by="acme-quiet")

    # Assert
    assert explanation.semantics is None
    assert "acme-quiet" in explanation.rendered()
    assert "did not say" in explanation.rendered()


def test_a_non_callable_attribute_of_the_right_name_is_not_a_declaration() -> None:
    """A non-callable attribute of the right name is not a declaration.

    The same treatment `weft_kernel.runner._flush_of` gives an attribute that merely shares a
    name — here the failure would be rendering a `dict` into the middle of a sentence a person
    reads, which is the defect `weft_cli.confirm` documents one seam over.
    """

    # Arrange
    class _NotAString:
        score_semantics: ClassVar[dict[str, str]] = {"nope": "not a sentence"}

    # Act
    explanation = ScoreExplanation.of(_NotAString(), produced_by="acme-typo")

    # Assert
    assert explanation.semantics is None


def test_the_pgvector_store_declares_one_meaning_per_capability_not_one_per_class() -> None:
    """`VectorSearch` and `TextSearch` return incommensurable numbers from the same object.

    This is the assertion that would fail if somebody later collapsed them into a single
    `score_semantics`, which is the tempting simplification and the one that makes the field lie.

    **Read off an instance rather than off the class, since task `21.7`.** `text_score_semantics`
    stopped being a `ClassVar` when `text_mode` made the text arm's ranking configurable: a store
    in `bm25` mode runs Okapi BM25 and one in `fts` mode runs `ts_rank_cd`, and the class cannot
    know which. A class-level read here would have to name one of the two rankings for every store
    ever configured, which is the field lying in the other direction.
    """
    # Arrange
    store = PgVectorStore(PgVectorSettings(dsn=SecretStr("postgresql://weft:weft@localhost/weft")))

    # Assert
    assert store.vector_score_semantics != store.text_score_semantics
    assert "cosine" in store.vector_score_semantics
    assert "ts_rank" in store.text_score_semantics


def test_scores_from_one_producer_carry_no_incomparability_note() -> None:
    # Arrange
    produced = ("vector-top-k", "vector-top-k", "vector-top-k")

    # Act / Assert
    assert incomparable_note(produced) is None


def test_scores_from_two_producers_are_never_presented_as_one_comparable_ranking() -> None:
    """The second half of the ledger line, and the half with a live instance.

    A pipeline that fans out — `multi-retriever`, `hybrid` — puts passages from different
    retrievers in one list, and `Passage.retrieved_by` is what records which. Their numbers are on
    different scales; printing them in one column with no note invites exactly the comparison
    `weft_retrieve.fusion` exists because you cannot make.
    """
    # Arrange
    produced = ("vector-top-k", "graph-walk", "vector-top-k")

    # Act
    note = incomparable_note(produced)

    # Assert — it names both producers rather than saying "some of these differ".
    assert note is not None
    assert "graph-walk" in note
    assert "vector-top-k" in note


def test_explanations_are_built_once_per_distinct_producer() -> None:
    """Six hits from one retriever are one explanation, not six identical lines.

    A per-hit repetition is what makes `--explain` unreadable at `top_k: 20`, and the thing a
    reader wants is *what this column means*, which is a property of the producer.
    """
    # Arrange
    producers = {"vector-top-k": _DeclaringRetriever()}

    # Act
    built = explanations_for(("vector-top-k",) * 6, producers=producers)

    # Assert
    assert len(built) == 1
    assert built[0].produced_by == "vector-top-k"


def test_the_caller_names_which_capability_it_invoked() -> None:
    """The caller names which capability it invoked.

    A producer satisfying two capabilities has two meanings, and only the caller knows which
    arm it just used — so the attribute is a parameter rather than a guess from the object.
    """
    # Arrange / Act
    # An instance, not the class: `text_score_semantics` is a fact about the configured store
    # since `21.7`, and `weft_cli.commands` already hands `explanations_for` the resolved plugin
    # rather than its type.
    store = PgVectorStore(PgVectorSettings(dsn=SecretStr("postgresql://weft:weft@localhost/weft")))
    text = ScoreExplanation.of(store, produced_by="pgvector", attribute="text_score_semantics")
    vector = ScoreExplanation.of(store, produced_by="pgvector", attribute="vector_score_semantics")

    # Assert
    assert text.semantics != vector.semantics
    assert "ts_rank" in str(text.semantics)
    assert "cosine" in str(vector.semantics)


def test_a_fan_out_arm_label_resolves_to_the_plugin_behind_it() -> None:
    """Found by running the binary, not by a test — ledger `21.1`.

    A fan-out labels each arm `<plugin>:<arm>`; `weft_retrieve.hybrid`'s own docstring writes
    `weights: {"hybrid:vector": 1.0, "hybrid:text": 0.7}`. Looking up the whole label found
    nothing, so `weft ask --pipeline hybrid-then-generate --explain` reported *"hybrid:vector did
    not say what its score means"* — honest, and useless, because the plugin right there had the
    sentence.

    The label stays whole in what a reader sees: which *arm* produced a number is the thing they
    are asking about. Only the lookup falls back.
    """
    # Arrange
    producers = {"hybrid": _DeclaringRetriever()}

    # Act
    built = explanations_for(("hybrid:vector", "hybrid:text"), producers=producers)

    # Assert — two arms, both resolved, and both still named by their arm.
    assert [explanation.produced_by for explanation in built] == ["hybrid:vector", "hybrid:text"]
    assert all(explanation.semantics is not None for explanation in built)


class _TwoArmRetriever:
    """A fan-out whose arms each call one store capability, the way `hybrid`'s do."""

    score_semantics: ClassVar[str] = "a reciprocal-rank fusion score"
    arm_score_attributes: ClassVar[dict[str, str]] = {
        "vector": "vector_score_semantics",
        "text": "text_score_semantics",
    }


def _bm25_store() -> PgVectorStore:
    return PgVectorStore(
        PgVectorSettings(
            dsn=SecretStr("postgresql://weft:weft@localhost/weft"), text_mode=TextMode.BM25
        )
    )


def test_a_fan_out_arm_says_what_the_store_it_searched_ranked_by() -> None:
    """Carried repair `R21.2`, measured through the shipped wheel.

    `weft ask --pipeline hybrid-then-generate --explain` against a `bm25` store printed the fused
    column's meaning and nothing from the store, so `text_score_semantics` had no production
    reader. The fused line is right about the column; what was missing is each arm's own scale,
    and only the configured store instance knows it — `text_mode` decides the text arm's sentence.
    """
    # Arrange
    store = _bm25_store()

    # Act
    built = arm_explanations(
        ("hybrid:vector", "hybrid:text", "hybrid:vector"),
        producers={"hybrid": _TwoArmRetriever()},
        store=store,
    )

    # Assert
    assert [explanation.produced_by for explanation in built] == [
        "hybrid:vector's own ranking",
        "hybrid:text's own ranking",
    ]
    assert built[0].semantics == store.vector_score_semantics
    assert built[1].semantics == store.text_score_semantics
    assert "BM25" in built[1].rendered()


def test_an_arm_its_retriever_does_not_map_adds_no_arm_line() -> None:
    # Arrange — a retriever with no per-arm declaration, and an arm name `hybrid` does not map.
    producers = {"vector-top-k": _DeclaringRetriever(), "hybrid": _TwoArmRetriever()}

    # Act
    built = arm_explanations(
        ("vector-top-k", "hybrid:renamed"), producers=producers, store=_bm25_store()
    )

    # Assert — the fused line already covers the column; an arm line would be a guess.
    assert built == ()


def test_hybrid_maps_each_channel_to_a_sentence_both_shipped_stores_declare() -> None:
    # Arrange
    attributes = Hybrid.arm_score_attributes

    # Assert
    assert set(attributes) == {"vector", "text"}
    for store_class in (PgVectorStore, QdrantStore):
        for attribute in attributes.values():
            declared = (
                getattr(_bm25_store(), attribute)
                if store_class is PgVectorStore
                else getattr(store_class, attribute)
            )
            assert isinstance(declared, str) and declared, (store_class.__name__, attribute)
