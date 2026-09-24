"""`scripts/open_ragbench_questions.py`, ledger task **38.4**.

`scripts/open_ragbench_questions.py` — ledger task **38.4**: Open RAGBench's questions in the one
question model.

The dataset labels each question with a document and a section of that document, an answer, an
answer form (`type`) and the evidence it rests on (`source`). It labels neither what a question
asks for nor how hard it is, so those two fields are stated absent. The gold section enters as its
opening span (Phase 38 Q3), verified literally against the rendered document the corpus stores;
the dataset's own two labels become axes, and a `split` axis is assigned by source document so no
document's questions sit on both sides of it.
"""

from __future__ import annotations

import hashlib
import json
import tomllib
from pathlib import Path

import open_ragbench
import open_ragbench_questions
import pytest

from weft_eval.question_set import Question, QuestionField, QuestionSetFormat, read_question_set

_LONG_SENTENCE = (
    "We consider hierarchical time series data where the clustering variable is country and "
    "the time variable is year, and where every country reports a different subset of years "
    "across a period of several decades"
)


def _section(section_id: int, text: str) -> dict[str, object]:
    return {"section_id": section_id, "text": text, "tables": {}, "images": {}}


def _document(identifier: str, sections: list[dict[str, object]]) -> dict[str, object]:
    return {"title": f"Paper {identifier}", "id": identifier, "sections": sections}


def _dataset(root: Path) -> Path:
    arxiv = root / "open_ragbench" / "pdf" / "arxiv"
    (arxiv / "corpus").mkdir(parents=True)
    documents = {
        "2401.00001v1": [
            _section(0, "#### Abstract\n\nMissing data are common in survey estimates. We impute."),
            _section(1, f"# 3. Methods.\n\n{_LONG_SENTENCE}. A second sentence follows."),
        ],
        "2401.00002v1": [
            _section(0, "#### Abstract\n\nGrid impedance changes with operating conditions."),
            _section(1, "# 4. Results.\n\n"),
        ],
    }
    for identifier, sections in documents.items():
        (arxiv / "corpus" / f"{identifier}.json").write_text(
            json.dumps(_document(identifier, sections)), encoding="utf-8"
        )
    questions = {
        "q-a": ("What is imputed?", "abstractive", "text", "2401.00001v1", 0),
        "q-b": ("Which variable clusters?", "extractive", "text-table", "2401.00001v1", 1),
        "q-c": ("Why does impedance change?", "abstractive", "text-image", "2401.00002v1", 0),
        "q-d": ("What were the results?", "extractive", "text", "2401.00002v1", 1),
    }
    (arxiv / "queries.json").write_text(
        json.dumps(
            {k: {"query": q, "type": t, "source": s} for k, (q, t, s, _, _) in questions.items()}
        ),
        encoding="utf-8",
    )
    (arxiv / "qrels.json").write_text(
        json.dumps({k: {"doc_id": d, "section_id": n} for k, (_, _, _, d, n) in questions.items()}),
        encoding="utf-8",
    )
    (arxiv / "answers.json").write_text(
        json.dumps(
            {k: f'The answer to "{q}"\nspans two lines.' for k, (q, *_) in questions.items()}
        ),
        encoding="utf-8",
    )
    return arxiv


def test_an_opening_span_is_the_first_sentence_of_the_sections_prose_verbatim() -> None:
    # Arrange
    text = "#### Abstract\n\nMissing data are common in survey estimates. We impute."

    # Act
    span = open_ragbench_questions.opening_span(text)

    # Assert
    assert span == "Missing data are common in survey estimates."
    assert span in text


def test_an_opening_span_is_capped_at_a_word_boundary_when_the_first_sentence_is_long() -> None:
    # Arrange
    text = f"# 3. Methods.\n\n{_LONG_SENTENCE}. A second sentence follows."

    # Act
    span = open_ragbench_questions.opening_span(text)

    # Assert
    assert span is not None
    assert len(span) <= open_ragbench_questions.MAX_SPAN
    assert _LONG_SENTENCE.startswith(span)
    assert not span.endswith(" ")
    assert _LONG_SENTENCE[len(span)] == " "


def test_a_figure_link_and_a_short_line_are_passed_over_for_the_first_line_of_prose() -> None:
    # Arrange
    text = (
        "## B. Figures\n\n![img-15.jpeg](img-15.jpeg)\nJuly 03, 2013\n"
        "Figure 6: Expected estimation error by sample size."
    )

    # Act
    span = open_ragbench_questions.opening_span(text)

    # Assert
    assert span == "Figure 6: Expected estimation error by sample size."


def test_an_opening_span_is_the_shortest_cut_that_occurs_once_in_its_document() -> None:
    """Q3's quote span is as short as it can be while still naming one place in the document.

    Q3's trigger counts quotes no chunk holds whole, so the span is as short as it can be while
    still naming one place in the document; a shorter cut that recurs elsewhere is not a quote of
    this section.
    """
    # Arrange
    text = f"# 3. Methods.\n\n{_LONG_SENTENCE}."
    repeated_head = _LONG_SENTENCE[: _LONG_SENTENCE.rfind(" ", 0, 61)]
    document = f"{repeated_head} appears earlier.\n\n{text}"

    # Act
    unique = open_ragbench_questions.opening_span(text, document)
    alone = open_ragbench_questions.opening_span(text, text)

    # Assert
    assert alone is not None
    assert len(alone) <= 60
    assert unique is not None
    assert len(unique) > len(alone)
    assert document.count(unique) == 1


def test_a_section_with_no_prose_has_no_opening_span() -> None:
    # Act / Assert
    assert open_ragbench_questions.opening_span("# 4. Results.\n\n") is None


def test_every_carried_question_reads_through_the_one_model_with_the_datasets_own_labels(
    tmp_path: Path,
) -> None:
    # Arrange
    dataset = _dataset(tmp_path)
    out = tmp_path / "questions"

    # Act
    build = open_ragbench_questions.build(dataset, out, seed="fixture", dev_fraction=0.5)
    read = [read_question_set(out / f"{split}.toml") for split in ("dev", "test")]

    # Assert
    questions = {
        question.id: question for question_set in read for question in question_set.questions
    }
    assert all(question_set.format is QuestionSetFormat.TOML for question_set in read)
    assert set(questions) == {"q-a", "q-b", "q-c"}
    assert build.uncarried == {
        "q-d": "gold section 1 of 2401.00002v1 has no line of prose 40 characters long"
    }
    b = questions["q-b"]
    assert b.relevant_documents == ("2401.00001v1",)
    assert b.axes == {
        "evidence": "text-table",
        "answer-form": "extractive",
        "split": b.axes["split"],
    }
    assert {QuestionField.KIND, QuestionField.DIFFICULTY} == b.absent
    assert b.absent_reason
    assert b.reference_answer == 'The answer to "Which variable clusters?"\nspans two lines.'
    (quote,) = b.quote
    assert quote.document == "2401.00001v1"
    assert quote.page == 0
    rendered = open_ragbench.render_document(
        (dataset / "corpus" / "2401.00001v1.json").read_bytes()
    ).text
    assert quote.text in rendered


def test_a_documents_questions_all_fall_on_one_side_of_the_split(tmp_path: Path) -> None:
    # Arrange
    dataset = _dataset(tmp_path)
    out = tmp_path / "questions"

    # Act
    open_ragbench_questions.build(dataset, out, seed="fixture", dev_fraction=0.5)
    questions = [
        question
        for split in ("dev", "test")
        for question in read_question_set(out / f"{split}.toml").questions
    ]

    # Assert
    split_of: dict[str, set[str]] = {}
    for question in questions:
        split_of.setdefault(question.relevant_documents[0], set()).add(question.axes["split"])
    assert all(len(splits) == 1 for splits in split_of.values())
    for split in ("dev", "test"):
        assert all(
            question.axes["split"] == split
            for question in read_question_set(out / f"{split}.toml").questions
        )


def test_the_build_is_reproducible_from_its_seed(tmp_path: Path) -> None:
    # Arrange
    dataset = _dataset(tmp_path)

    # Act
    open_ragbench_questions.build(dataset, tmp_path / "one", seed="fixture", dev_fraction=0.5)
    open_ragbench_questions.build(dataset, tmp_path / "two", seed="fixture", dev_fraction=0.5)

    # Assert
    for name in ("dev.toml", "test.toml"):
        assert (tmp_path / "one" / name).read_bytes() == (tmp_path / "two" / name).read_bytes()


def test_the_build_reports_how_many_quotes_straddle_a_chunk_boundary(tmp_path: Path) -> None:
    """The build measures Q3's straddle rate rather than leaving it to be argued.

    Q3's reopen trigger is a straddle rate, so the build measures it rather than leaving it to be
    argued: a quote no 512-character window advancing 462 holds whole cannot be matched at quote
    granularity by the shipped chunker.
    """
    # Arrange
    dataset = _dataset(tmp_path)

    # Act
    build = open_ragbench_questions.build(
        dataset, tmp_path / "questions", seed="fixture", dev_fraction=0.5
    )

    # Assert
    assert build.carried == 3
    assert 0 <= build.straddling <= build.carried


def test_the_build_refuses_a_question_whose_quote_the_quote_check_rejects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The file is verified by `eval/check_questions.py`'s own check before it is written.

    The file is verified by `eval/check_questions.py`'s own check before it is written, not by a
    copy of it — a span that does not survive that check is a bug in this script.
    """
    # Arrange
    dataset = _dataset(tmp_path)

    def _nowhere(text: str, document: str | None = None) -> str:
        del text, document
        return "not in the document at all"

    monkeypatch.setattr(open_ragbench_questions, "opening_span", _nowhere)

    # Act
    with pytest.raises(open_ragbench_questions.UnverifiedQuoteError) as caught:
        open_ragbench_questions.build(
            dataset, tmp_path / "questions", seed="fixture", dev_fraction=0.5
        )

    # Assert
    assert "q-a" in str(caught.value)
    assert not (tmp_path / "questions" / "dev.toml").exists()


def test_the_pin_records_each_files_bytes_and_its_question_set_digest(tmp_path: Path) -> None:
    # Arrange
    dataset = _dataset(tmp_path)
    out = tmp_path / "questions"
    build = open_ragbench_questions.build(dataset, out, seed="fixture", dev_fraction=0.5)

    # Act
    pin = tomllib.loads(open_ragbench_questions.pin_text(build, seed="fixture", dev_fraction=0.5))

    # Assert
    assert pin["build"]["seed"] == "fixture"
    assert pin["build"]["carried"] == 3
    assert pin["build"]["uncarried"] == 1
    for entry in pin["file"]:
        path = out / entry["name"]
        assert entry["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
        assert entry["question_set_digest"] == read_question_set(path).digest
        assert entry["questions"] == len(read_question_set(path).questions)


def _axed(identifier: str, evidence: str, form: str) -> Question:
    return Question.model_validate(
        {
            "id": identifier,
            "text": f"question {identifier}?",
            "language": "en",
            "absent": frozenset(QuestionField),
            "absent_reason": "a subset fixture",
            "axes": {"evidence": evidence, "answer-form": form, "split": "dev"},
        }
    )


def test_a_stratified_subset_keeps_each_strata_share_and_sums_to_its_size() -> None:
    """Q5: the 2x2's 300 questions are stratified on the dataset's own two labels.

    Q5: the 2x2's 300 questions are stratified on the dataset's own two labels, so a subset
    that happened to draw only text questions cannot stand in for the split.
    """
    # Arrange — 60 text/abstractive, 30 text-table/extractive, 10 text-image/abstractive.
    questions = (
        [_axed(f"a-{i}", "text", "abstractive") for i in range(60)]
        + [_axed(f"b-{i}", "text-table", "extractive") for i in range(30)]
        + [_axed(f"c-{i}", "text-image", "abstractive") for i in range(10)]
    )

    # Act
    subset = open_ragbench_questions.stratified_subset(questions, 25, seed="fixture")
    again = open_ragbench_questions.stratified_subset(questions, 25, seed="fixture")

    # Assert
    assert len(subset) == 25
    counts: dict[str, int] = {}
    for question in subset:
        counts[question.axes["evidence"]] = counts.get(question.axes["evidence"], 0) + 1
    # 25 x 0.3 and 25 x 0.1 tie on a remainder of 0.5, broken by stratum key, which puts the
    # last question in text-image.
    assert counts == {"text": 15, "text-table": 7, "text-image": 3}
    assert [q.id for q in subset] == [q.id for q in again]
    order = [q.id for q in questions]
    assert [q.id for q in subset] == sorted((q.id for q in subset), key=order.index)
