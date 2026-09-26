"""`weft_eval.question_set` — ledger repair **R22.4a**: the V2 question set, read from the wheel.

The archive ships the question files; before this repair only a checkout could read them.
"""

from __future__ import annotations

import hashlib
import json
import tomllib
from pathlib import Path

import pytest

from weft_eval.question_set import (
    QuestionSetError,
    load_questions,
    read_question_set,
    read_question_sets,
    reproducible_questions,
)
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


# --- Task 43.51 — several named question files are read as one set, their union.


def _question_file(path: Path, ids: list[str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(
            _ANSWERABLE.format(id=identifier, document="doc-a") + _QUOTE.format(document="doc-a")
            for identifier in ids
        ),
        encoding="utf-8",
    )
    return path


def _digest_as_records_have_always_written_it(path: Path) -> str:
    """A record's question-set digest as written before 43.51: canonical and sorted."""
    canonical = sorted(
        json.dumps(question.model_dump(mode="json"), sort_keys=True, ensure_ascii=False)
        for question in read_question_set(path).questions
    )
    return hashlib.sha256("\n".join(canonical).encode("utf-8")).hexdigest()


def test_two_named_files_are_read_as_their_union_in_the_order_named(tmp_path: Path) -> None:
    # Arrange
    operator = _question_file(tmp_path / "operator.toml", ["op-1", "op-2"])
    fetch = _question_file(tmp_path / "fetch.toml", ["fe-1", "fe-2", "fe-3"])

    # Act
    union = read_question_sets([operator, fetch])

    # Assert
    assert len(union.questions) == len(read_question_set(operator).questions) + len(
        read_question_set(fetch).questions
    )
    assert [question.id for question in union.questions] == [
        "op-1",
        "op-2",
        "fe-1",
        "fe-2",
        "fe-3",
    ]


def test_a_question_id_in_two_named_files_is_refused_naming_the_id_and_both_files(
    tmp_path: Path,
) -> None:
    # Arrange
    fetch = _question_file(tmp_path / "fetch.toml", ["fe-1", "shared-7"])
    operator = _question_file(tmp_path / "operator.toml", ["op-1", "shared-7", "op-2"])

    # Act
    with pytest.raises(QuestionSetError) as caught:
        read_question_sets([fetch, operator])

    # Assert
    message = str(caught.value)
    assert "shared-7" in message
    assert "fetch.toml" in message
    assert "operator.toml" in message
    assert "in both" in message


def test_one_named_file_keeps_the_digest_every_existing_record_carries(tmp_path: Path) -> None:
    # Arrange
    fetch = _question_file(tmp_path / "fetch.toml", ["fe-1", "fe-2", "fe-3"])

    # Act
    digest = read_question_sets([fetch]).digest

    # Assert
    assert digest == _digest_as_records_have_always_written_it(fetch)


def test_the_union_digest_is_a_set_of_its_own_and_the_same_set_however_it_is_filed(
    tmp_path: Path,
) -> None:
    """Two files named together digest as the directory holding exactly those two files does.

    `question_set_digest` is canonical and positional nowhere, so a set spread over two files is
    the set one directory holding them reads, and neither file alone is it.
    """
    # Arrange
    together = tmp_path / "together"
    fetch = _question_file(together / "fetch.toml", ["fe-1", "fe-2"])
    operator = _question_file(together / "operator.toml", ["op-1", "op-2", "op-3"])

    # Act
    union = read_question_sets([fetch, operator]).digest

    # Assert
    assert union != _digest_as_records_have_always_written_it(fetch)
    assert union != _digest_as_records_have_always_written_it(operator)
    assert union == read_question_set(together).digest


def test_naming_the_same_files_in_the_other_order_reorders_the_questions_but_not_the_set(
    tmp_path: Path,
) -> None:
    # Arrange
    fetch = _question_file(tmp_path / "fetch.toml", ["fe-1", "fe-2"])
    operator = _question_file(tmp_path / "operator.toml", ["op-1", "op-2", "op-3"])

    # Act
    forward = read_question_sets([fetch, operator])
    backward = read_question_sets([operator, fetch])

    # Assert
    assert [question.id for question in forward.questions] != [
        question.id for question in backward.questions
    ]
    assert forward.digest == backward.digest
