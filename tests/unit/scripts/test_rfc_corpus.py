"""Unit tests for `scripts/rfc_corpus.py` — ledger task **39.3**.

The RFC corpus is pinned the way Open RAGBench's is: a manifest of every document's sha256, the
bytes fetched rather than tracked. Its question set carries one obligation Open RAGBench's does not,
settled by the owner as Q2: **every anchor a question names occurs in several documents**, so exact
matching cannot win by construction and the intent half has to decide. That is checked here against
the corpus text, never asserted by whoever wrote the questions.
"""

from __future__ import annotations

import hashlib
import tomllib
from pathlib import Path

from rfc_corpus import (
    RfcQuestion,
    anchor_document_frequency,
    manifest_text,
    question_problems,
    question_set_text,
    rfc_url,
)

from weft_eval.question_set import load_questions


def _documents(tmp_path: Path) -> dict[str, str]:
    texts = {
        "rfc6585": "4. 429 Too Many Requests\n   The 429 status code indicates rate limiting.\n",
        "rfc9110": "15.5.20. 429 is not defined here; see RFC 6585.\n   Retry-After applies.\n",
        "rfc7231": "7.1.3. Retry-After\n   Servers send the Retry-After header field.\n",
    }
    directory = tmp_path / "rfc"
    directory.mkdir()
    for identifier, text in texts.items():
        (directory / f"{identifier}.txt").write_text(text, encoding="utf-8")
    return texts


def test_an_rfc_is_fetched_from_the_rfc_editors_plain_text() -> None:
    # Act / Assert
    assert rfc_url(9110) == "https://www.rfc-editor.org/rfc/rfc9110.txt"


def test_the_manifest_pins_every_document_by_number_with_its_digest(tmp_path: Path) -> None:
    # Arrange
    _documents(tmp_path)

    # Act
    manifest = tomllib.loads(manifest_text(tmp_path / "rfc"))

    # Assert
    documents = manifest["document"]
    assert [entry["id"] for entry in documents] == ["rfc6585", "rfc7231", "rfc9110"]
    first = documents[0]
    body = (tmp_path / "rfc" / "rfc6585.txt").read_bytes()
    assert first["sha256"] == hashlib.sha256(body).hexdigest()
    assert first["path"] == "rfc/rfc6585.txt"
    assert first["source"] == rfc_url(6585)
    assert first["format"] == "txt"
    assert first["tier"] == "fetch"
    assert first["language"] == "en"
    assert manifest["corpus"]["name"] == "rfc"


def test_an_anchor_counts_the_documents_holding_it_as_a_whole_token(tmp_path: Path) -> None:
    # Arrange
    texts = _documents(tmp_path)

    # Act
    status = anchor_document_frequency("429", texts)
    header = anchor_document_frequency("Retry-After", texts)
    partial = anchor_document_frequency("42", texts)

    # Assert
    assert status == 2
    assert header == 2
    assert partial == 0


def test_a_question_whose_anchor_sits_in_one_document_is_refused(tmp_path: Path) -> None:
    # Arrange — Q2: an anchor in exactly one document makes the question a test of `grep`.
    texts = _documents(tmp_path)
    question = RfcQuestion(
        id="q-1",
        text="What does Too Many Requests mean under rate limiting?",
        relevant_document="rfc6585",
        quote="The 429 status code indicates rate limiting.",
        anchors=("Too Many Requests",),
    )

    # Act
    problems = question_problems(question, texts)

    # Assert
    assert any("q-1" in problem and "Too Many Requests" in problem for problem in problems)
    assert any("1 document" in problem for problem in problems)


def test_an_anchor_the_question_does_not_contain_is_refused(tmp_path: Path) -> None:
    # Arrange
    texts = _documents(tmp_path)
    question = RfcQuestion(
        id="q-2",
        text="Which RFC defines the rate-limiting status?",
        relevant_document="rfc6585",
        quote="The 429 status code indicates rate limiting.",
        anchors=("429",),
    )

    # Act
    problems = question_problems(question, texts)

    # Assert
    assert any("q-2" in problem and "'429'" in problem for problem in problems)


def test_a_quote_its_document_does_not_hold_is_refused(tmp_path: Path) -> None:
    # Arrange
    texts = _documents(tmp_path)
    question = RfcQuestion(
        id="q-3",
        text="What does status 429 mean?",
        relevant_document="rfc6585",
        quote="A sentence nobody wrote.",
        anchors=("429",),
    )

    # Act
    problems = question_problems(question, texts)

    # Assert
    assert any("q-3" in problem and "quote" in problem for problem in problems)


def test_a_sound_question_has_no_problem(tmp_path: Path) -> None:
    # Arrange
    texts = _documents(tmp_path)
    anchored = RfcQuestion(
        id="q-4",
        text="What does status code 429 tell a client that is being rate limited?",
        relevant_document="rfc6585",
        quote="The 429 status code indicates rate limiting.",
        anchors=("429",),
    )
    plain = RfcQuestion(
        id="q-5",
        text="How should a server tell a client when to try again?",
        relevant_document="rfc7231",
        quote="Servers send the Retry-After header field.",
        anchors=(),
    )

    # Act
    problems = question_problems(anchored, texts) + question_problems(plain, texts)

    # Assert
    assert problems == []


def _four() -> list[RfcQuestion]:
    return [
        RfcQuestion(
            id=f"q-{kind}{index}",
            text=f"What does 429 mean, case {index}?"
            if kind == "a"
            else f"How to back off {index}?",
            relevant_document="rfc6585",
            quote="The 429 status code indicates rate limiting.",
            anchors=("429",) if kind == "a" else (),
        )
        for kind in ("a", "n")
        for index in (1, 2)
    ]


def test_the_question_set_loads_as_weft_questions_with_the_anchor_axis(tmp_path: Path) -> None:
    # Arrange
    directory = tmp_path / "questions"
    directory.mkdir()

    # Act
    (directory / "rfc.toml").write_text(question_set_text(_four()), encoding="utf-8")
    loaded = load_questions(directory)

    # Assert
    by_id = {question.id: question for question in loaded}
    assert set(by_id) == {"q-a1", "q-a2", "q-n1", "q-n2"}
    assert by_id["q-a1"].axes["anchored"] == "yes"
    assert by_id["q-n1"].axes["anchored"] == "no"
    assert by_id["q-a1"].relevant_documents == ("rfc6585",)
    assert by_id["q-a1"].quote[0].document == "rfc6585"
    assert by_id["q-a1"].quote[0].text == "The 429 status code indicates rate limiting."
    assert by_id["q-a1"].notes is not None and "429" in by_id["q-a1"].notes


def test_the_split_divides_each_slice_in_half_the_same_way_every_time(tmp_path: Path) -> None:
    # Arrange — fusion weights are fitted on `train` and reported on `test` (G24, `20b`'s rule),
    # so each anchor slice is halved rather than the whole set, and the halving is reproducible.
    directory = tmp_path / "questions"
    directory.mkdir()

    # Act
    first = question_set_text(_four())
    second = question_set_text(list(reversed(_four())))
    (directory / "rfc.toml").write_text(first, encoding="utf-8")
    loaded = load_questions(directory)

    # Assert
    splits = {(q.axes["anchored"], q.axes["split"]) for q in loaded}
    assert splits == {("yes", "train"), ("yes", "test"), ("no", "train"), ("no", "test")}
    assert first == second
