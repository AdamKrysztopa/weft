"""The QuALITY converter — task 44.41b, for E3b.

QuALITY asks four-option multiple-choice questions of long articles; each article row carries
one writer's questions, and an article appears once per writer group. The converter makes one
document per article (the rows of one article must agree on its text), and one question per
question, whose text carries its four options and whose reference answer is the gold option.
It splits by article so an article's questions never straddle train and held-out.

Every title, sentence and option below is invented for Weft; only the field names are QuALITY's.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest
from quality_questions import convert, parse_rows, questions_toml

from weft_cli.eval_scoring import resolve_labels
from weft_eval.question_set import read_question_set

_SEED = "44.41b"


def _question(
    unique_id: str, text: str, options: Sequence[str], gold: int, *, hard: int = 0
) -> dict[str, object]:
    return {
        "question_unique_id": unique_id,
        "question": text,
        "options": list(options),
        "gold_label": gold,
        "writer_label": gold,
        "difficult": hard,
        "validation": [],
        "speed_validation": [],
    }


def _row(
    article_id: str, set_id: str, questions: Sequence[dict[str, object]], *, article: str = ""
) -> dict[str, object]:
    return {
        "article_id": article_id,
        "set_unique_id": set_id,
        "batch_num": "1",
        "writer_id": "w",
        "source": "Gutenberg",
        "title": f"The Loom of {article_id}",
        "year": 1960,
        "author": "A. Weaver",
        "topic": "",
        "url": "",
        "license": "public domain, for Weft's tests",
        "article": article or f"The loom {article_id} kept its warp taut through the long winter.",
        "questions": list(questions),
    }


_OPTIONS = ("a shuttle", "a heddle", "a reed", "a batten")


def test_rows_of_one_article_become_one_document() -> None:
    # Arrange — two writer groups asked about the same article.
    rows = [
        _row("20001", "20001_1", [_question("20001_1_q1", "What passes the weft?", _OPTIONS, 1)]),
        _row("20001", "20001_2", [_question("20001_2_q1", "What lifts the warp?", _OPTIONS, 2)]),
    ]

    # Act
    converted = convert(parse_rows(rows), seed=_SEED, dev_fraction=0.5)

    # Assert
    assert set(converted.documents) == {"ql-20001.txt"}
    assert "kept its warp taut" in converted.documents["ql-20001.txt"]
    assert "The Loom of 20001" in converted.documents["ql-20001.txt"]
    assert len(converted.questions) == 2


def test_a_question_carries_its_options_and_its_gold_option_is_the_reference() -> None:
    # Arrange
    rows = [
        _row(
            "20002",
            "20002_1",
            [_question("20002_1_q1", "What beats the weft?", _OPTIONS, 4, hard=1)],
        )
    ]

    # Act
    [question] = convert(parse_rows(rows), seed=_SEED, dev_fraction=0.5).questions

    # Assert
    assert question.id == "ql-20002_1_q1"
    assert question.text.startswith("What beats the weft?")
    for option in _OPTIONS:
        assert option in question.text
    assert question.reference_answer == "a batten"
    assert question.relevant_documents == ("ql-20002.txt",)
    assert question.axes["difficulty"] == "hard"


def test_an_article_s_questions_share_its_split() -> None:
    # Arrange
    rows = [
        _row(
            "20003",
            "20003_1",
            [_question(f"20003_1_q{n}", "Which tool?", _OPTIONS, 1) for n in range(4)],
        ),
        _row(
            "20003",
            "20003_2",
            [_question(f"20003_2_q{n}", "Which part?", _OPTIONS, 3) for n in range(4)],
        ),
    ]

    # Act
    converted = convert(parse_rows(rows), seed=_SEED, dev_fraction=0.5)

    # Assert
    assert len({question.axes["split"] for question in converted.questions}) == 1


def test_two_rows_that_disagree_on_an_article_s_text_are_refused_naming_it() -> None:
    # Arrange
    rows = [
        _row("20004", "20004_1", [_question("20004_1_q1", "Q?", _OPTIONS, 1)], article="One text."),
        _row(
            "20004",
            "20004_2",
            [_question("20004_2_q1", "Q?", _OPTIONS, 1)],
            article="Another text.",
        ),
    ]

    # Act / Assert
    with pytest.raises(ValueError, match="20004"):
        convert(parse_rows(rows), seed=_SEED, dev_fraction=0.5)


def test_a_gold_label_outside_the_options_is_refused_naming_the_question() -> None:
    # Act / Assert
    with pytest.raises(ValueError, match="20005_1_q1"):
        parse_rows([_row("20005", "20005_1", [_question("20005_1_q1", "Q?", _OPTIONS, 5)])])


def test_the_written_question_file_reads_back_as_the_same_questions(tmp_path: Path) -> None:
    # Arrange
    rows = [
        _row(
            "20006",
            "20006_1",
            [
                _question("20006_1_q1", "What passes?", _OPTIONS, 1),
                _question("20006_1_q2", "What beats?", _OPTIONS, 4, hard=1),
            ],
        )
    ]
    converted = convert(parse_rows(rows), seed=_SEED, dev_fraction=0.5)
    path = tmp_path / "quality.toml"

    # Act
    path.write_text(questions_toml(converted.questions), encoding="utf-8")
    read = read_question_set(path).questions

    # Assert
    assert [question.id for question in read] == [question.id for question in converted.questions]
    assert [question.reference_answer for question in read] == ["a shuttle", "a batten"]
    assert [dict(question.axes) for question in read] == [
        dict(question.axes) for question in converted.questions
    ]


def test_every_label_names_the_file_the_converter_writes() -> None:
    # Arrange — scoring resolves a label as a path suffix of a corpus file, extension included.
    rows = [_row("20007", "20007_1", [_question("20007_1_q1", "What edge?", _OPTIONS, 2)])]
    converted = convert(parse_rows(rows), seed=_SEED, dev_fraction=0.5)
    written = [f"/staged/corpus/{name}" for name in converted.documents]
    labels = {label for question in converted.questions for label in question.relevant_documents}

    # Act
    resolved = resolve_labels(labels, corpus_document_ids=written)

    # Assert
    assert set(resolved) == labels
