"""`weft_eval.question_set` — ledger repair **R22.4a**: the V2 question set, read from the wheel.

The archive ships the question files; before this repair only a checkout could read them.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from weft_eval.question_set import QuestionSetError, load_questions, reproducible_questions
from weft_kernel.errors import WeftError

_QUESTIONS_DIR = Path(__file__).resolve().parents[3] / "eval" / "questions"

_ANSWERABLE = """[[question]]
id = "{id}"
text = "What is it?"
language = "en"
kind = "definitional"
difficulty = "easy"
relevant_documents = ["{document}"]
reference_answer = "That."
notes = "written for this test"
"""

_QUOTE = """
  [[question.quote]]
  document = "{document}"
  page = 0
  text = "That."
"""

_UNANSWERABLE = """[[question]]
id = "{id}"
text = "What is not here?"
language = "en"
kind = "unanswerable"
difficulty = "hard"
reference_answer = "The corpus does not say."
notes = "written for this test"
"""


def test_the_tracked_set_loads_every_question_its_files_declare() -> None:
    # Arrange
    declared = [
        entry["id"]
        for path in sorted(_QUESTIONS_DIR.glob("*.toml"))
        for entry in tomllib.loads(path.read_text(encoding="utf-8")).get("question", [])
    ]

    # Act
    loaded = load_questions(_QUESTIONS_DIR)

    # Assert
    assert len(declared) >= 2
    assert [question.id for question in loaded] == declared


def test_a_question_breaking_its_own_invariant_is_refused_naming_its_file(tmp_path: Path) -> None:
    # Arrange
    (tmp_path / "round-2.toml").write_text(
        _ANSWERABLE.format(id="q-1", document="doc-a"), encoding="utf-8"
    )

    # Act
    with pytest.raises(QuestionSetError) as caught:
        load_questions(tmp_path)

    # Assert
    assert isinstance(caught.value, WeftError)
    assert "round-2.toml" in str(caught.value)
    assert "carries no supporting quote" in str(caught.value)


def test_a_file_that_is_not_toml_is_refused_naming_it(tmp_path: Path) -> None:
    # Arrange
    (tmp_path / "broken.toml").write_text("[[question]\n", encoding="utf-8")

    # Act
    with pytest.raises(QuestionSetError) as caught:
        load_questions(tmp_path)

    # Assert
    assert "broken.toml" in str(caught.value)


def test_a_question_resting_on_an_operator_document_is_not_reproducible(tmp_path: Path) -> None:
    # Arrange
    (tmp_path / "set.toml").write_text(
        _ANSWERABLE.format(id="q-open", document="doc-a")
        + _QUOTE.format(document="doc-a")
        + _ANSWERABLE.format(id="q-closed", document="doc-b")
        + _QUOTE.format(document="doc-b")
        + _UNANSWERABLE.format(id="q-none"),
        encoding="utf-8",
    )
    questions = load_questions(tmp_path)

    # Act
    kept = reproducible_questions(
        questions,
        tiers={"doc-a": "fetch", "doc-b": "operator"},
        reproducible=frozenset({"gate", "fetch"}),
    )

    # Assert
    assert len(questions) == 3
    assert [question.id for question in kept] == ["q-open", "q-none"]
