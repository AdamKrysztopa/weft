"""`weft_eval.question_set` as the one question model — ledger task **38.10**.

Phase 38's D1 settled that `weft eval run`, `weft eval baseline` and the experiment runner read
one `Question`. This file asserts what that model has to carry for the three sets it will hold:
the 136 hand-written questions, an imported set that states which fields it cannot supply and
why, and a JSON `--questions` file converted rather than read by a second model. The question
file becomes a persistence surface with a version marker of its own.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from weft_eval.contract import QueryModality
from weft_eval.question_set import (
    QUESTION_SET_SCHEMA_VERSION,
    Kind,
    Question,
    QuestionField,
    QuestionSetError,
    QuestionSetFormat,
    QuestionSetSchemaError,
    load_questions,
    question_set_digest,
    read_question_set,
)

_HEADER = """[question_set]
schema = {schema}
absent = {absent}
absent_reason = "{reason}"
axes = {axes}

"""

_BARE_QUESTION = """[[question]]
id = "{id}"
text = "{text}"
language = "en"
relevant_documents = [{documents}]
axes = {axes}

"""

_CURATED = """[[question]]
id = "{id}"
text = "What is it?"
language = "en"
kind = "definitional"
difficulty = "easy"
relevant_documents = ["doc-a"]
reference_answer = "That."
notes = "written for this test"

  [[question.quote]]
  document = "doc-a"
  page = 0
  text = "That."

"""

_IMPORTED_ABSENT = '["kind", "difficulty", "quote", "reference_answer", "notes"]'
_REASON = "imported from a dataset that labels none of these"


def _imported_file(
    directory: Path,
    *,
    questions: str,
    axes: str = '["evidence"]',
    absent: str = _IMPORTED_ABSENT,
    name: str = "imported.toml",
) -> Path:
    path = directory / name
    header = _HEADER.format(
        schema=QUESTION_SET_SCHEMA_VERSION, absent=absent, reason=_REASON, axes=axes
    )
    path.write_text(header + questions, encoding="utf-8")
    return path


def _bare(
    identifier: str, *, documents: str = '"doc-a"', axes: str = '{ evidence = "text" }'
) -> str:
    return _BARE_QUESTION.format(
        id=identifier, text=f"Question {identifier}?", documents=documents, axes=axes
    )


def test_a_set_stating_its_absences_loads_questions_without_those_fields(tmp_path: Path) -> None:
    # Arrange
    _imported_file(tmp_path, questions=_bare("q-1") + _bare("q-2", documents=""))

    # Act
    questions = load_questions(tmp_path)

    # Assert
    by_id = {question.id: question for question in questions}
    assert set(by_id) == {"q-1", "q-2"}
    assert by_id["q-1"].kind is None
    assert by_id["q-1"].difficulty is None
    assert by_id["q-1"].reference_answer is None
    assert by_id["q-1"].quote == ()
    assert QuestionField.KIND in by_id["q-1"].absent
    assert by_id["q-1"].absent_reason == _REASON
    assert by_id["q-1"].answerable
    assert not by_id["q-2"].answerable


def test_a_missing_field_the_file_never_stated_absent_is_refused_naming_file_and_field(
    tmp_path: Path,
) -> None:
    # Arrange
    _imported_file(tmp_path, questions=_bare("q-1"), absent='["difficulty", "quote", "notes"]')

    # Act
    with pytest.raises(QuestionSetError) as caught:
        load_questions(tmp_path)

    # Assert
    message = str(caught.value)
    assert "imported.toml" in message
    assert "q-1" in message
    assert "kind" in message


def test_a_field_stated_absent_that_a_question_supplies_is_refused(tmp_path: Path) -> None:
    # Arrange
    header = _HEADER.format(
        schema=QUESTION_SET_SCHEMA_VERSION, absent='["kind"]', reason=_REASON, axes="[]"
    )
    (tmp_path / "liar.toml").write_text(header + _CURATED.format(id="q-1"), encoding="utf-8")

    # Act
    with pytest.raises(QuestionSetError) as caught:
        load_questions(tmp_path)

    # Assert
    message = str(caught.value)
    assert "liar.toml" in message
    assert "kind" in message


def test_an_absence_stated_without_a_reason_is_refused(tmp_path: Path) -> None:
    # Arrange
    path = tmp_path / "unexplained.toml"
    path.write_text(
        f"[question_set]\nschema = {QUESTION_SET_SCHEMA_VERSION}\n"
        f"absent = {_IMPORTED_ABSENT}\naxes = []\n\n" + _bare("q-1", axes="{}"),
        encoding="utf-8",
    )

    # Act
    with pytest.raises(QuestionSetError) as caught:
        load_questions(tmp_path)

    # Assert
    assert "unexplained.toml" in str(caught.value)
    assert "reason" in str(caught.value)


def test_every_question_carries_exactly_the_axes_its_file_declares(tmp_path: Path) -> None:
    # Arrange
    _imported_file(
        tmp_path,
        axes='["evidence", "answer-form"]',
        questions=_bare("q-1", axes='{ evidence = "text-table", answer-form = "extractive" }'),
    )

    # Act
    (question,) = load_questions(tmp_path)

    # Assert
    assert question.axes["evidence"] == "text-table"
    assert question.axes["answer-form"] == "extractive"
    assert len(question.axes) == 2


@pytest.mark.parametrize(
    ("axes", "fragment"),
    [
        ('{ evidence = "text" }', "answer-form"),
        ('{ evidence = "text", answer-form = "extractive", split = "dev" }', "split"),
    ],
    ids=["a-declared-axis-missing", "an-undeclared-axis-present"],
)
def test_a_question_whose_axes_disagree_with_its_file_is_refused_naming_the_axis(
    tmp_path: Path, axes: str, fragment: str
) -> None:
    # Arrange
    _imported_file(tmp_path, axes='["evidence", "answer-form"]', questions=_bare("q-1", axes=axes))

    # Act
    with pytest.raises(QuestionSetError) as caught:
        load_questions(tmp_path)

    # Assert
    assert "q-1" in str(caught.value)
    assert fragment in str(caught.value)


def test_an_axis_named_kind_is_refused_while_kind_is_a_field_the_question_carries(
    tmp_path: Path,
) -> None:
    # Arrange
    _imported_file(
        tmp_path,
        absent='["difficulty", "quote", "reference_answer", "notes"]',
        axes='["kind"]',
        questions=_bare("q-1", axes='{ kind = "requires-graph-hop" }').replace(
            'language = "en"', 'language = "en"\nkind = "definitional"'
        ),
    )

    # Act
    with pytest.raises(QuestionSetError) as caught:
        load_questions(tmp_path)

    # Assert
    assert "kind" in str(caught.value)
    assert "q-1" in str(caught.value)


def test_an_axis_named_kind_is_read_when_kind_is_stated_absent(tmp_path: Path) -> None:
    # Arrange
    _imported_file(tmp_path, axes='["kind"]', questions=_bare("q-1", axes='{ kind = "hop" }'))

    # Act
    (question,) = load_questions(tmp_path)

    # Assert
    assert question.kind is None
    assert question.axes["kind"] == "hop"


def test_a_question_states_its_query_modality_and_defaults_to_text(tmp_path: Path) -> None:
    # Arrange
    _imported_file(
        tmp_path,
        questions=_bare("q-text")
        + _bare("q-image").replace('language = "en"', 'language = "en"\nmodality = "image"'),
    )

    # Act
    questions = {question.id: question for question in load_questions(tmp_path)}

    # Assert
    assert questions["q-text"].modality is QueryModality.TEXT
    assert questions["q-image"].modality is QueryModality.IMAGE


def test_a_file_without_a_question_set_table_keeps_every_field_required(tmp_path: Path) -> None:
    # Arrange
    (tmp_path / "curated.toml").write_text(_CURATED.format(id="q-1"), encoding="utf-8")
    (tmp_path / "old-and-short.toml").write_text(
        _bare("q-2").replace('axes = { evidence = "text" }\n', ""), encoding="utf-8"
    )

    # Act
    with pytest.raises(QuestionSetError) as caught:
        load_questions(tmp_path)

    # Assert
    assert "old-and-short.toml" in str(caught.value)


def test_a_file_without_a_question_set_table_reads_as_it_always_has(tmp_path: Path) -> None:
    # Arrange
    (tmp_path / "curated.toml").write_text(_CURATED.format(id="q-1"), encoding="utf-8")

    # Act
    (question,) = load_questions(tmp_path)

    # Assert
    assert question.kind is Kind.DEFINITIONAL
    assert question.absent == frozenset()
    assert question.axes == {}


def test_a_question_set_table_naming_no_schema_is_refused(tmp_path: Path) -> None:
    # Arrange
    (tmp_path / "unmarked.toml").write_text(
        f'[question_set]\nabsent = {_IMPORTED_ABSENT}\nabsent_reason = "{_REASON}"\n'
        "axes = []\n\n" + _bare("q-1", axes="{}"),
        encoding="utf-8",
    )

    # Act
    with pytest.raises(QuestionSetError) as caught:
        load_questions(tmp_path)

    # Assert
    assert "unmarked.toml" in str(caught.value)
    assert "schema" in str(caught.value)


def test_a_file_written_by_a_newer_schema_is_refused_naming_both_versions_and_the_remedy(
    tmp_path: Path,
) -> None:
    # Arrange
    newer = QUESTION_SET_SCHEMA_VERSION + 1
    path = tmp_path / "future.toml"
    path.write_text(
        _HEADER.format(schema=newer, absent="[]", reason="", axes="[]") + _CURATED.format(id="q-1"),
        encoding="utf-8",
    )

    # Act
    with pytest.raises(QuestionSetSchemaError) as caught:
        load_questions(tmp_path)

    # Assert
    message = str(caught.value)
    assert isinstance(caught.value, QuestionSetError)
    assert "future.toml" in message
    assert str(newer) in message
    assert str(QUESTION_SET_SCHEMA_VERSION) in message
    assert "upgrade weft-rag" in message


def test_the_digest_names_the_questions_and_not_their_order(tmp_path: Path) -> None:
    # Arrange
    first = _imported_file(tmp_path, questions=_bare("q-1") + _bare("q-2"), name="a.toml")
    swapped = tmp_path / "swapped"
    swapped.mkdir()
    _imported_file(swapped, questions=_bare("q-2") + _bare("q-1"), name="a.toml")
    changed = tmp_path / "changed"
    changed.mkdir()
    _imported_file(changed, questions=_bare("q-1") + _bare("q-2", documents='"doc-b"'))

    # Act
    original = read_question_set(first)
    reordered = read_question_set(swapped)
    edited = read_question_set(changed)

    # Assert
    assert original.digest == reordered.digest
    assert original.digest != edited.digest
    assert original.digest == question_set_digest(original.questions)
    assert len(original.digest) == 64


def test_a_directory_and_its_one_file_read_as_the_same_set(tmp_path: Path) -> None:
    # Arrange
    only = _imported_file(tmp_path, questions=_bare("q-1") + _bare("q-2"))

    # Act
    from_directory = read_question_set(tmp_path)
    from_file = read_question_set(only)

    # Assert
    assert from_directory.format is QuestionSetFormat.TOML
    assert from_file.format is QuestionSetFormat.TOML
    assert [question.id for question in from_directory.questions] == ["q-1", "q-2"]
    assert from_directory.digest == from_file.digest


def test_a_json_questions_file_is_converted_into_the_one_model(tmp_path: Path) -> None:
    # Arrange
    path = tmp_path / "questions.json"
    path.write_text(
        json.dumps(
            [
                {
                    "query": "What is it?",
                    "relevant_documents": ["arxiv/a.pdf"],
                    "kind": "definitional",
                },
                {
                    "query": "How are they linked?",
                    "relevant_documents": ["b.md"],
                    "kind": "requires-graph-hop",
                },
                {
                    "query": "Is it here?",
                    "relevant_documents": [],
                    "modality": "image",
                    "language": "pl",
                },
            ]
        ),
        encoding="utf-8",
    )

    # Act
    converted = read_question_set(path)

    # Assert
    assert converted.format is QuestionSetFormat.JSON
    first, second, third = converted.questions
    assert [first.id, second.id, third.id] == ["0", "1", "2"]
    assert first.text == "What is it?"
    assert first.relevant_documents == ("arxiv/a.pdf",)
    assert first.kind is Kind.DEFINITIONAL
    assert first.quote == ()
    assert {QuestionField.DIFFICULTY, QuestionField.QUOTE} <= first.absent
    assert QuestionField.KIND not in first.absent
    assert first.absent_reason
    assert second.kind is None
    assert QuestionField.KIND in second.absent
    assert second.axes["kind"] == "requires-graph-hop"
    assert third.modality is QueryModality.IMAGE
    assert third.language == "pl"
    assert not third.answerable


def test_a_json_question_naming_its_own_id_keeps_it(tmp_path: Path) -> None:
    # Arrange
    path = tmp_path / "questions.json"
    path.write_text(
        json.dumps([{"id": "keep-me", "query": "What?", "relevant_documents": ["a.md"]}]),
        encoding="utf-8",
    )

    # Act
    (question,) = read_question_set(path).questions

    # Assert
    assert question.id == "keep-me"


@pytest.mark.parametrize(
    ("name", "body", "fragment"),
    [
        ("questions.json", "{not json", "not valid JSON"),
        ("questions.json", '{"query": "a dict, not a list"}', "list"),
        ("questions.json", '[{"query": "a"}, {"id": "x", "query": "b"}]', "'id'"),
        ("questions.csv", "query\nwhat", "questions.csv"),
    ],
    ids=["invalid-json", "not-a-list", "some-ids-only", "unknown-suffix"],
)
def test_a_questions_path_that_cannot_be_read_as_a_set_is_refused_naming_it(
    tmp_path: Path, name: str, body: str, fragment: str
) -> None:
    # Arrange
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")

    # Act
    with pytest.raises(QuestionSetError) as caught:
        read_question_set(path)

    # Assert
    assert fragment in str(caught.value)


def _bridge_question(**stated: object) -> Question:
    return Question.model_validate(
        {
            "id": "bridge-1",
            "text": "How is A related to B?",
            "language": "en",
            "relevant_documents": ("a.md", "b.md"),
            **stated,
        }
    )


def test_a_question_built_in_code_states_its_absences_or_is_refused() -> None:
    # Arrange
    every_absence = frozenset(
        {
            QuestionField.KIND,
            QuestionField.DIFFICULTY,
            QuestionField.QUOTE,
            QuestionField.REFERENCE_ANSWER,
            QuestionField.NOTES,
        }
    )

    # Act
    with pytest.raises(ValueError, match="kind"):
        _bridge_question()
    stated = _bridge_question(
        absent=every_absence,
        absent_reason="generated from a graph path",
        axes={"kind": "requires-graph-hop"},
    )

    # Assert
    assert stated.answerable
    assert stated.axes["kind"] == "requires-graph-hop"
