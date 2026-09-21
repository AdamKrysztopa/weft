"""`Ranking` and `Passages` answer `len()` — carried repair **R32.3**.

The seam counts a stage's items in and out for `weft ask --explain` by `len()`, and names no
capability to do it; a reranker's `Ranking` and a packer's `Passages` were models, so every
reranker and packer printed a time and no counts. Defining `__len__` also changes a model's
truthiness, so both stay truthy when empty: `if passages:` meant "was a value given", and must
keep meaning it.
"""

from weft_kernel.payload import MediaType, Node
from weft_retrieve.payload import Passage, Passages, Query, Ranking
from weft_store.contract import Scored


def _passage(label: str) -> Passage:
    node = Node.synthetic(content=f"passage {label}", media_type=MediaType.TEXT, reason="fixture")
    return Passage(scored=Scored(value=node, score=0.5), rank=0, retrieved_by="vector", label=label)


def test_a_ranking_counts_its_hits() -> None:
    # Arrange
    ranking = Ranking(origin=Query(text="q"), hits=(_passage(""), _passage(""), _passage("")))

    # Act / Assert
    assert len(ranking) == 3


def test_passages_count_what_was_packed() -> None:
    # Arrange
    packed = Passages(origin=Query(text="q"), passages=(_passage("1"), _passage("2")))

    # Act / Assert
    assert len(packed) == 2


def test_an_empty_ranking_and_empty_passages_are_still_truthy() -> None:
    # Arrange
    ranking = Ranking(origin=Query(text="q"))
    packed = Passages(origin=Query(text="q"))

    # Act / Assert
    assert len(ranking) == 0
    assert len(packed) == 0
    assert bool(ranking)
    assert bool(packed)
