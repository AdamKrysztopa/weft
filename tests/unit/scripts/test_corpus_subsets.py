"""Nested corpus subsets for E1, the whole-corpus size sweep — task 44.51 (fix-plans/24 Task 13).

E1 asks at what corpus size reading the whole corpus stops beating one search. It runs the same
arm pair on nested subsets of `validation-en`, so a subset must contain every smaller one, and a
question may run on a subset only when every document it cites is in it — a question whose answer
lies outside the subset would measure the subset, not the method.
"""

from __future__ import annotations

from collections.abc import Sequence

from corpus_subsets import nested_subsets, questions_within

from weft_eval.question_set import Question, QuestionField

_DOCUMENTS = tuple(f"papers/p{n:02d}.pdf" for n in range(16))


def _question(identifier: str, documents: Sequence[str]) -> Question:
    return Question.model_validate(
        {
            "id": identifier,
            "text": "Which loom keeps its warp taut?",
            "language": "en",
            "relevant_documents": tuple(documents),
            "absent": frozenset(QuestionField),
            "absent_reason": "a subset fixture",
        }
    )


def test_subsets_nest() -> None:
    # Act
    subsets = nested_subsets(_DOCUMENTS, fractions=(0.25, 0.5, 1.0), seed="44.51")

    # Assert — 25 ⊂ 50 ⊂ 100 by document, sized by fraction, the full set last.
    quarter, half, whole = subsets[0.25], subsets[0.5], subsets[1.0]
    assert (len(quarter), len(half), len(whole)) == (4, 8, 16)
    assert set(quarter) <= set(half) <= set(whole) == set(_DOCUMENTS)


def test_the_subsets_follow_the_seed_not_the_input_order() -> None:
    # Act
    forward = nested_subsets(_DOCUMENTS, fractions=(0.25,), seed="44.51")
    backward = nested_subsets(tuple(reversed(_DOCUMENTS)), fractions=(0.25,), seed="44.51")
    other = nested_subsets(_DOCUMENTS, fractions=(0.25,), seed="another")

    # Assert
    assert set(forward[0.25]) == set(backward[0.25])
    assert set(forward[0.25]) != set(other[0.25])


def test_a_question_with_a_document_outside_the_subset_is_left_out() -> None:
    # Arrange
    inside = ("papers/p00.pdf", "papers/p01.pdf")
    questions = (
        _question("both-in", ("papers/p00.pdf", "papers/p01.pdf")),
        _question("one-out", ("papers/p00.pdf", "papers/p09.pdf")),
        _question("suffix", ("p01.pdf",)),
    )

    # Act
    kept = questions_within(questions, inside)

    # Assert — a label resolves as a path suffix of a corpus file, as scoring resolves it.
    assert [question.id for question in kept] == ["both-in", "suffix"]
