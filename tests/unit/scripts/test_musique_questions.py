"""The MuSiQue-Ans converter — task 44.40.

MuSiQue items are composed from single-hop steps, each answered by one paragraph among twenty. The
converter turns a sample of them into one text document per paragraph and two question sets: the
multi-hop question, whose relevant documents are its supporting paragraphs, and a single-hop
control from its first step, so a retriever's multi-hop loss can be told from a plain miss.

Every title, sentence and answer below is invented for Weft; only the field names are MuSiQue's.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest
from musique_questions import MusiqueItem, convert, parse_item, questions_toml
from open_ragbench_questions import split_of

from weft_cli.eval_scoring import resolve_labels
from weft_eval.question_set import read_question_set

_SEED = "44.40"


def _paragraph(idx: int, title: str, text: str, *, supporting: bool) -> dict[str, object]:
    return {"idx": idx, "title": title, "paragraph_text": text, "is_supporting": supporting}


def _step(question: str, answer: str, support: int | None) -> dict[str, object]:
    return {"id": 0, "question": question, "answer": answer, "paragraph_support_idx": support}


def _raw(
    item_id: str,
    steps: Sequence[Mapping[str, object]],
    paragraphs: Sequence[Mapping[str, object]],
    *,
    answerable: bool = True,
) -> dict[str, object]:
    return {
        "id": item_id,
        "question": f"Which composed fact does {item_id} ask for?",
        "answer": f"answer of {item_id}",
        "answer_aliases": [],
        "answerable": answerable,
        "paragraphs": list(paragraphs),
        "question_decomposition": list(steps),
    }


def _two_hop(item_id: str, *, shared: Mapping[str, object] | None = None) -> MusiqueItem:
    first = shared or _paragraph(
        0, "Veltra Harbour", "Veltra Harbour was dredged by Ossen Carr.", supporting=True
    )
    return parse_item(
        _raw(
            item_id,
            [
                _step("Who dredged Veltra Harbour?", "Ossen Carr", 0),
                _step("Where was #1 born?", "Tamsel", 1),
            ],
            [
                first,
                _paragraph(
                    1, "Ossen Carr", f"Ossen Carr was born in Tamsel ({item_id}).", supporting=True
                ),
                _paragraph(2, "Brannock Mill", "Brannock Mill grinds barley.", supporting=False),
            ],
        )
    )


def _three_hop(item_id: str) -> MusiqueItem:
    return parse_item(
        _raw(
            item_id,
            [
                _step("Which river feeds Lake Oristan?", "the Pell", 0),
                _step("Which town stands at the mouth of #1?", "Quarrow", 1),
                _step("Who founded #2?", "Ida Venn", 2),
            ],
            [
                _paragraph(
                    0,
                    "Lake Oristan",
                    f"Lake Oristan is fed by the Pell ({item_id}).",
                    supporting=True,
                ),
                _paragraph(
                    1,
                    "The Pell",
                    f"The Pell meets the sea at Quarrow ({item_id}).",
                    supporting=True,
                ),
                _paragraph(
                    2, "Quarrow", f"Quarrow was founded by Ida Venn ({item_id}).", supporting=True
                ),
            ],
        )
    )


def _document_id(title: str, text: str) -> str:
    return "mq-" + hashlib.sha256(f"{title}\n{text}".encode()).hexdigest()[:16] + ".txt"


def test_hops_are_counted_from_the_decomposition() -> None:
    # Act
    converted = convert([_three_hop("3hop1__a")], per_hops=5, seed=_SEED, dev_fraction=0.5)

    # Assert
    (question,) = converted.multi_hop
    assert question.axes["hops"] == "3"
    assert question.axes["control"] == "multi-hop"
    assert len(question.relevant_documents) == 3


def test_a_multi_hop_question_is_answered_by_its_supporting_paragraphs_only() -> None:
    # Act
    converted = convert([_two_hop("2hop__a")], per_hops=5, seed=_SEED, dev_fraction=0.5)

    # Assert
    (question,) = converted.multi_hop
    assert set(question.relevant_documents) == {
        _document_id("Veltra Harbour", "Veltra Harbour was dredged by Ossen Carr."),
        _document_id("Ossen Carr", "Ossen Carr was born in Tamsel (2hop__a)."),
    }
    assert question.reference_answer == "answer of 2hop__a"
    assert len(converted.documents) == 3
    assert question.axes["split"] == split_of(
        sorted(question.relevant_documents)[0], seed=_SEED, dev_fraction=0.5
    )


def test_a_shared_paragraph_is_one_document() -> None:
    # Arrange — two items carry the identical first paragraph.
    shared = _paragraph(
        0, "Veltra Harbour", "Veltra Harbour was dredged by Ossen Carr.", supporting=True
    )

    # Act
    converted = convert(
        [_two_hop("2hop__a", shared=shared), _two_hop("2hop__b", shared=shared)],
        per_hops=5,
        seed=_SEED,
        dev_fraction=0.5,
    )

    # Assert
    shared_id = _document_id("Veltra Harbour", "Veltra Harbour was dredged by Ossen Carr.")
    assert shared_id in converted.documents
    assert len(converted.documents) == 4
    assert all(shared_id in question.relevant_documents for question in converted.multi_hop)


def test_unanswerable_items_are_dropped_and_counted() -> None:
    # Arrange
    answerable = _two_hop("2hop__a")
    unanswerable = parse_item(
        {**_raw("2hop__u", [_step("Who dredged it?", "no one", 0)], []), "answerable": False}
    )

    # Act
    converted = convert([answerable, unanswerable], per_hops=5, seed=_SEED, dev_fraction=0.5)

    # Assert
    assert converted.dropped_unanswerable == 1
    assert [question.id for question in converted.multi_hop] == ["mq-2hop__a"]


def test_the_first_step_is_a_single_hop_control_on_its_one_paragraph() -> None:
    # Act
    converted = convert([_two_hop("2hop__a")], per_hops=5, seed=_SEED, dev_fraction=0.5)

    # Assert
    (control,) = converted.single_hop
    assert control.text == "Who dredged Veltra Harbour?"
    assert control.reference_answer == "Ossen Carr"
    assert control.relevant_documents == (
        _document_id("Veltra Harbour", "Veltra Harbour was dredged by Ossen Carr."),
    )
    assert control.axes["control"] == "single-hop"
    assert control.id != converted.multi_hop[0].id


def test_a_back_referencing_first_step_is_not_a_control() -> None:
    # Arrange — a first step that still leans on another step's answer cannot stand alone.
    item = parse_item(
        _raw(
            "2hop__r",
            [_step("Where did #2 train?", "Selk", 0), _step("Who taught at Selk?", "Mora", 1)],
            [
                _paragraph(0, "Selk", "Many trained at Selk.", supporting=True),
                _paragraph(1, "Mora", "Mora taught at Selk.", supporting=True),
            ],
        )
    )

    # Act
    converted = convert([item], per_hops=5, seed=_SEED, dev_fraction=0.5)

    # Assert
    assert converted.single_hop == ()
    assert len(converted.multi_hop) == 1


def test_the_sample_is_a_pure_function_of_the_seed() -> None:
    # Arrange — eight two-hop items, sampled three at a time.
    items = [_two_hop(f"2hop__{index}") for index in range(8)]

    # Act
    first = convert(items, per_hops=3, seed="one", dev_fraction=0.5)
    again = convert(list(reversed(items)), per_hops=3, seed="one", dev_fraction=0.5)
    other = convert(items, per_hops=3, seed="two", dev_fraction=0.5)

    # Assert — the first three by sha256(f"{seed}:{id}"), whatever order the items came in.
    ids = {question.id for question in first.multi_hop}
    assert ids == {"mq-2hop__3", "mq-2hop__6", "mq-2hop__7"}
    assert ids == {question.id for question in again.multi_hop}
    assert {question.id for question in other.multi_hop} == {
        "mq-2hop__4",
        "mq-2hop__6",
        "mq-2hop__7",
    }


def test_the_sample_takes_per_hops_items_for_each_hop_count() -> None:
    # Arrange
    items = [_two_hop(f"2hop__{index}") for index in range(4)] + [
        _three_hop(f"3hop1__{index}") for index in range(4)
    ]

    # Act
    converted = convert(items, per_hops=2, seed=_SEED, dev_fraction=0.5)

    # Assert
    hops = sorted(question.axes["hops"] for question in converted.multi_hop)
    assert hops == ["2", "2", "3", "3"]


def test_an_item_missing_a_field_is_refused_naming_it() -> None:
    # Arrange
    raw = _raw("2hop__x", [_step("q", "a", 0)], [])
    del raw["question_decomposition"]

    # Act / Assert
    with pytest.raises(ValueError, match="question_decomposition"):
        parse_item(raw)


def test_the_written_question_file_reads_back_as_the_same_questions(tmp_path: Path) -> None:
    # Arrange
    converted = convert(
        [_two_hop("2hop__a"), _three_hop("3hop1__b")], per_hops=5, seed=_SEED, dev_fraction=0.5
    )
    questions = converted.multi_hop + converted.single_hop
    path = tmp_path / "musique.toml"

    # Act
    path.write_text(questions_toml(questions), encoding="utf-8")
    read = read_question_set(path).questions

    # Assert
    assert [question.id for question in read] == [question.id for question in questions]
    assert [question.relevant_documents for question in read] == [
        question.relevant_documents for question in questions
    ]
    assert [dict(question.axes) for question in read] == [
        dict(question.axes) for question in questions
    ]
    assert [question.reference_answer for question in read] == [
        question.reference_answer for question in questions
    ]


def test_every_label_names_the_file_the_converter_writes() -> None:
    # Arrange — scoring resolves a label as a path suffix of a corpus file, extension included.
    converted = convert(
        [_two_hop("2hop__a"), _three_hop("3hop1__b")], per_hops=5, seed=_SEED, dev_fraction=0.5
    )
    written = [f"/staged/corpus/{name}" for name in converted.documents]
    labels = {
        label
        for question in converted.multi_hop + converted.single_hop
        for label in question.relevant_documents
    }

    # Act
    resolved = resolve_labels(labels, corpus_document_ids=written)

    # Assert
    assert set(resolved) == labels
    assert all(name.endswith(".txt") for name in converted.documents)
