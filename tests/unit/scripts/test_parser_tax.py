"""`scripts/parser_tax.py` — ledger **38.8**: what reading the raw PDFs costs against the dataset's
own rendering of them.

Two measurements. A dev quote survives Weft's ingest when it sits whole inside one stored chunk of
the document it names — the figure `38.4` published for the markdown corpus (1,510 of 1,548). And
two records pair across corpora only when the corpus is the one thing that differs: the question
set and the query pipeline must match, and the corpora must not.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from parser_tax import (
    CorpusSide,
    Measurement,
    PairRow,
    QuoteSurvival,
    quote_survival,
    require_parser_pair,
    table,
)

from weft_eval.falsify import PairedDifference
from weft_eval.question_set import Question, read_question_set

_QUESTIONS = """
[question_set]
schema = 2
absent = ["kind", "difficulty", "reference_answer", "notes"]
absent_reason = "a fixture"
axes = ["split"]

[[question]]
id = "whole"
text = "q1"
language = "en"
relevant_documents = ["doc-a"]
axes = { split = "dev" }

  [[question.quote]]
  document = "doc-a"
  page = 0
  text = "alpha beta gamma"

[[question]]
id = "straddles"
text = "q2"
language = "en"
relevant_documents = ["doc-a"]
axes = { split = "dev" }

  [[question.quote]]
  document = "doc-a"
  page = 0
  text = "gamma delta epsilon"

[[question]]
id = "unread"
text = "q3"
language = "en"
relevant_documents = ["doc-b"]
axes = { split = "dev" }

  [[question.quote]]
  document = "doc-b"
  page = 0
  text = "anything at all"
"""


def _questions(tmp_path: Path) -> tuple[Question, ...]:
    path = tmp_path / "dev.toml"
    path.write_text(_QUESTIONS, encoding="utf-8")
    return read_question_set(path).questions


def test_a_quote_survives_only_whole_inside_one_chunk_of_its_own_document(tmp_path: Path) -> None:
    # Arrange — `gamma delta epsilon` is split across two chunks; `doc-b` was never stored.
    chunks = {"doc-a": ("alpha beta gamma delta", "delta epsilon zeta")}

    # Act
    survival = quote_survival(_questions(tmp_path), chunks)

    # Assert
    assert (survival.total, survival.whole) == (3, 1)
    assert survival.lost == ("straddles",)
    assert survival.unstored == ("unread",)


def test_whitespace_differences_do_not_lose_a_quote(tmp_path: Path) -> None:
    """The ingest's own `whitespace` cleaner collapses runs, so a quote is compared the same way."""
    # Arrange
    chunks = {"doc-a": ("alpha  beta\ngamma delta epsilon",)}

    # Act
    survival = quote_survival(_questions(tmp_path), chunks)

    # Assert
    assert survival.whole == 2


def _side(corpus: str, *, questions: str = "q1", query: str = "vector-retrieve") -> CorpusSide:
    return CorpusSide(
        label=f"dense on {corpus}",
        corpus_digest=corpus,
        question_set_digest=questions,
        query_pipeline=query,
    )


def test_two_sides_that_differ_only_in_corpus_pair() -> None:
    require_parser_pair(_side("markdown"), _side("pdf"))


@pytest.mark.parametrize(
    ("pdf", "names"),
    [
        (_side("pdf", questions="q2"), "question set"),
        (_side("pdf", query="lexical-wide-retrieve"), "query pipeline"),
        (_side("markdown"), "same corpus"),
    ],
    ids=["another-question-set", "another-query-pipeline", "one-corpus"],
)
def test_any_other_difference_is_refused_by_name(pdf: CorpusSide, names: str) -> None:
    with pytest.raises(ValueError, match=names):
        require_parser_pair(_side("markdown"), pdf)


def _row(arm: str, mean: float) -> PairRow:
    return PairRow(
        arm=arm,
        repetition=1,
        metric="recall@5",
        markdown=0.9,
        pdf=0.9 + mean,
        difference=PairedDifference(
            metric="recall@5", mean=mean, low=mean - 0.01, high=mean + 0.01, n=1548, differing=40
        ),
        markdown_corpus="md-digest",
        pdf_corpus="pdf-digest",
    )


def test_the_table_carries_each_row_with_its_labelled_interval() -> None:
    # Arrange
    measured = Measurement(
        markdown_quotes=QuoteSurvival(total=1548, whole=1510, lost=(), unstored=()),
        pdf_quotes=QuoteSurvival(total=1548, whole=1100, lost=(), unstored=()),
        pairs=(_row("dense", -0.02), _row("lexical", -0.1)),
    )

    # Act
    rendered = table(measured)

    # Assert
    assert "| of 1548 | 1510 | 1100 |" in rendered
    assert (
        "| dense | 1 | recall@5 | 0.900 | 0.880 | -0.020 [-0.030, -0.010] | 1548 | 40 |" in rendered
    )
    assert (
        "| lexical | 1 | recall@5 | 0.900 | 0.800 | -0.100 [-0.110, -0.090] | 1548 | 40 |"
        in rendered
    )
