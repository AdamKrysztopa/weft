"""The QASPER converter — task 44.41.

QASPER asks questions of whole research papers, each answered by annotators as extractive spans,
free-form text, yes or no, or not at all. The converter makes one document per paper and one
question per answerable question, reading the first annotator's answer, and splits by paper so a
paper's questions never straddle train and held-out.

Every title, sentence and answer below is invented for Weft; only the field names are QASPER's.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest
from open_ragbench_questions import split_of
from qasper_questions import AnswerKind, convert, parse_paper, questions_toml

from weft_cli.eval_scoring import resolve_labels
from weft_eval.question_set import read_question_set

_SEED = "44.41"


def _answer(
    *,
    spans: Sequence[str] = (),
    free: str = "",
    yes_no: bool | None = None,
    unanswerable: bool = False,
) -> dict[str, object]:
    return {
        "annotation_id": "a",
        "worker_id": "w",
        "answer": {
            "unanswerable": unanswerable,
            "extractive_spans": list(spans),
            "free_form_answer": free,
            "yes_no": yes_no,
            "evidence": [],
            "highlighted_evidence": [],
        },
    }


def _qa(question_id: str, text: str, *answers: Mapping[str, object]) -> dict[str, object]:
    return {"question_id": question_id, "question": text, "answers": list(answers)}


def _paper(title: str, qas: Sequence[Mapping[str, object]]) -> dict[str, object]:
    return {
        "title": title,
        "abstract": f"{title} studies how looms keep tension.",
        "full_text": [
            {"section_name": "Introduction", "paragraphs": [f"{title} opens with a loom."]},
            {
                "section_name": "Method",
                "paragraphs": ["We count warp threads.", "Then weft passes."],
            },
        ],
        "figures_and_tables": [],
        "qas": list(qas),
    }


def test_each_paper_is_one_document_holding_its_title_abstract_and_sections() -> None:
    # Arrange
    paper = parse_paper(
        "1901.00001",
        _paper("Warp Tension", [_qa("q1", "What is counted?", _answer(spans=["warp threads"]))]),
    )

    # Act
    converted = convert([paper], seed=_SEED, dev_fraction=0.5)

    # Assert
    assert set(converted.documents) == {"qp-1901.00001.txt"}
    content = converted.documents["qp-1901.00001.txt"]
    for part in (
        "Warp Tension",
        "studies how looms keep tension",
        "Method",
        "We count warp threads.",
    ):
        assert part in content


def test_each_answer_kind_becomes_its_reference_answer() -> None:
    # Arrange
    paper = parse_paper(
        "1901.00002",
        _paper(
            "Shuttle Speed",
            [
                _qa("q-span", "What passes?", _answer(spans=["weft", "the shuttle"])),
                _qa("q-free", "Why count?", _answer(free="to keep tension even")),
                _qa("q-bool", "Is a loom used?", _answer(yes_no=True)),
            ],
        ),
    )

    # Act
    converted = convert([paper], seed=_SEED, dev_fraction=0.5)

    # Assert
    by_id = {question.id: question for question in converted.questions}
    assert by_id["qp-q-span"].reference_answer == "weft; the shuttle"
    assert by_id["qp-q-span"].axes["answer-type"] == AnswerKind.EXTRACTIVE.value
    assert by_id["qp-q-free"].reference_answer == "to keep tension even"
    assert by_id["qp-q-free"].axes["answer-type"] == AnswerKind.ABSTRACTIVE.value
    assert by_id["qp-q-bool"].reference_answer == "Yes"
    assert by_id["qp-q-bool"].axes["answer-type"] == AnswerKind.BOOLEAN.value
    assert all(
        question.relevant_documents == ("qp-1901.00002.txt",) for question in converted.questions
    )


def test_a_question_whose_first_annotator_found_no_answer_is_dropped_and_counted() -> None:
    # Arrange — the second annotator's answer does not rescue it: the first decides.
    paper = parse_paper(
        "1901.00003",
        _paper(
            "Heddle Wear",
            [
                _qa("q-none", "Who invented it?", _answer(unanswerable=True), _answer(free="Ada")),
                _qa("q-ok", "What wears?", _answer(spans=["the heddle"])),
            ],
        ),
    )

    # Act
    converted = convert([paper], seed=_SEED, dev_fraction=0.5)

    # Assert
    assert converted.dropped_unanswerable == 1
    assert [question.id for question in converted.questions] == ["qp-q-ok"]


def test_a_paper_s_questions_share_its_split() -> None:
    # Arrange
    paper = parse_paper(
        "1901.00004",
        _paper(
            "Reed Spacing",
            [_qa(f"q{index}", f"Question {index}?", _answer(free="x")) for index in range(4)],
        ),
    )

    # Act
    converted = convert([paper], seed=_SEED, dev_fraction=0.5)

    # Assert
    expected = split_of("qp-1901.00004.txt", seed=_SEED, dev_fraction=0.5)
    assert {question.axes["split"] for question in converted.questions} == {expected}


def test_max_papers_samples_by_the_seed_whatever_the_input_order() -> None:
    # Arrange
    papers = [
        parse_paper(
            f"1901.1{index:04d}",
            _paper(f"Paper {index}", [_qa(f"q{index}", "Q?", _answer(free="a"))]),
        )
        for index in range(6)
    ]

    # Act
    first = convert(papers, seed="one", dev_fraction=0.5, max_papers=2)
    again = convert(list(reversed(papers)), seed="one", dev_fraction=0.5, max_papers=2)

    # Assert
    assert len(first.documents) == 2
    assert set(first.documents) == set(again.documents)


def test_a_paper_missing_a_field_is_refused_naming_it() -> None:
    # Arrange
    raw = _paper("Broken", [])
    del raw["full_text"]

    # Act / Assert
    with pytest.raises(ValueError, match="full_text"):
        parse_paper("1901.00009", raw)


def test_the_written_question_file_reads_back_as_the_same_questions(tmp_path: Path) -> None:
    # Arrange
    paper = parse_paper(
        "1901.00005",
        _paper(
            "Batten Force",
            [
                _qa("q-a", "What presses?", _answer(spans=["the batten"])),
                _qa("q-b", "Is it firm?", _answer(yes_no=False)),
            ],
        ),
    )
    converted = convert([paper], seed=_SEED, dev_fraction=0.5)
    path = tmp_path / "qasper.toml"

    # Act
    path.write_text(questions_toml(converted.questions), encoding="utf-8")
    read = read_question_set(path).questions

    # Assert
    assert [question.id for question in read] == [question.id for question in converted.questions]
    assert [question.reference_answer for question in read] == ["the batten", "No"]
    assert [dict(question.axes) for question in read] == [
        dict(question.axes) for question in converted.questions
    ]


def test_every_label_names_the_file_the_converter_writes() -> None:
    # Arrange — scoring resolves a label as a path suffix of a corpus file, extension included.
    paper = parse_paper(
        "1901.00006",
        _paper("Selvage Edge", [_qa("q-s", "What edge?", _answer(spans=["the selvage"]))]),
    )
    converted = convert([paper], seed=_SEED, dev_fraction=0.5)
    written = [f"/staged/corpus/{name}" for name in converted.documents]
    labels = {label for question in converted.questions for label in question.relevant_documents}

    # Act
    resolved = resolve_labels(labels, corpus_document_ids=written)

    # Assert
    assert set(resolved) == labels
    assert all(name.endswith(".txt") for name in converted.documents)
