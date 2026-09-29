"""The QuALITY converter — task **44.41b**, for E3b.

QuALITY (Pang et al., NAACL 2022) asks four-option multiple-choice questions of long articles;
each row is one writer group's questions about one article, and an article appears once per
writer group. This converts one local `.dev` split (the pin: `corpus/quality.toml`) into
`weft_eval.question_set` form: one text document per article — title, then the article text —
and one question per row question, whose text carries its four options and whose reference
answer is the gold option. It splits by article so an article's questions never straddle dev and
test.

Every row's `article` text is checked against every other row sharing its `article_id`: QuALITY
asks the same article of several writer groups, and a converter that trusted one row's copy over
another's would silently prefer whichever writer happened first.

The converted corpus and question set are untracked, per `corpus/quality.toml`'s own reasoning:
run this script to reproduce them.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Final, cast

from open_ragbench_questions import split_of
from pydantic import BaseModel, ConfigDict

from weft_eval.question_set import Question

_ABSENT_REASON: Final[str] = (
    "converted from QuALITY, which labels neither a question's kind, a supporting quote nor "
    "free-form provenance notes; its own difficulty label is carried in the 'difficulty' axis "
    "rather than the schema's difficulty field, since it is the writer's own estimate, not one "
    "checked here"
)
_ABSENT_FIELDS: Final[tuple[str, ...]] = ("kind", "difficulty", "quote", "notes")
_AXES: Final[tuple[str, ...]] = ("difficulty", "source", "split")


class QualityQuestion(BaseModel):
    """One QuALITY question, with its four options and its 1-indexed gold option."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    unique_id: str
    text: str
    options: tuple[str, ...]
    gold: int
    hard: bool


class QualityRow(BaseModel):
    """One QuALITY row — one writer group's questions about one article."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    article_id: str
    title: str
    source: str
    text: str
    questions: tuple[QualityQuestion, ...]


class Converted(BaseModel):
    """The result of converting a batch of QuALITY rows: one document per article, its questions."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    documents: Mapping[str, str]
    questions: tuple[Question, ...]


def _require(raw: Mapping[str, object], key: str) -> object:
    if key not in raw:
        raise ValueError(f"missing required field {key!r}")
    return raw[key]


def _parse_question(raw: Mapping[str, object]) -> QualityQuestion:
    unique_id = str(_require(raw, "question_unique_id"))
    text = str(_require(raw, "question"))
    raw_options = cast("Sequence[object]", _require(raw, "options"))
    options = tuple(str(option) for option in raw_options)
    gold = int(cast("int", _require(raw, "gold_label")))
    if not 1 <= gold <= len(options):
        raise ValueError(f"{unique_id}: gold_label {gold} is outside 1..{len(options)}")
    hard = bool(_require(raw, "difficult"))
    return QualityQuestion(unique_id=unique_id, text=text, options=options, gold=gold, hard=hard)


def _parse_row(raw: Mapping[str, object]) -> QualityRow:
    article_id = str(_require(raw, "article_id"))
    title = str(_require(raw, "title"))
    source = str(_require(raw, "source"))
    text = str(_require(raw, "article"))
    raw_questions = cast("Sequence[Mapping[str, object]]", _require(raw, "questions"))
    questions = tuple(_parse_question(entry) for entry in raw_questions)
    return QualityRow(
        article_id=article_id, title=title, source=source, text=text, questions=questions
    )


def parse_rows(rows: Sequence[Mapping[str, object]]) -> list[QualityRow]:
    """Read every QuALITY row out of its raw JSON, one per (article, writer group)."""
    return [_parse_row(raw) for raw in rows]


def _group_by_article(rows: Sequence[QualityRow]) -> dict[str, list[QualityRow]]:
    groups: dict[str, list[QualityRow]] = {}
    for row in rows:
        groups.setdefault(row.article_id, []).append(row)
    return groups


def _article_text(rows_for_article: Sequence[QualityRow]) -> tuple[str, str]:
    first = rows_for_article[0]
    for row in rows_for_article[1:]:
        if row.text != first.text:
            raise ValueError(f"{first.article_id}: rows disagree on the article's text")
    return first.title, first.text


def _render_document(title: str, text: str) -> str:
    return f"{title}\n\n{text}"


def _options_text(options: Sequence[str]) -> str:
    numbered = " ".join(f"({index + 1}) {option}" for index, option in enumerate(options))
    return f"Options: {numbered}"


def _convert_question(
    question: QualityQuestion, *, document_id: str, seed: str, dev_fraction: float, source: str
) -> Question:
    split = split_of(document_id, seed=seed, dev_fraction=dev_fraction)
    return Question.model_validate(
        {
            "id": f"ql-{question.unique_id}",
            "text": f"{question.text}\n{_options_text(question.options)}",
            "language": "en",
            "relevant_documents": (document_id,),
            "reference_answer": question.options[question.gold - 1],
            "absent": _ABSENT_FIELDS,
            "absent_reason": _ABSENT_REASON,
            "axes": {
                "difficulty": "hard" if question.hard else "easy",
                "source": source,
                "split": split,
            },
        }
    )


def _ordered_article_ids(
    groups: Mapping[str, Sequence[QualityRow]], *, seed: str, max_articles: int | None
) -> list[str]:
    ordered = sorted(
        groups, key=lambda article_id: hashlib.sha256(f"{seed}:{article_id}".encode()).hexdigest()
    )
    return ordered if max_articles is None else ordered[:max_articles]


def convert(
    rows: Sequence[QualityRow],
    *,
    seed: str,
    dev_fraction: float,
    max_articles: int | None = None,
) -> Converted:
    """One document and its questions per article, ordered by `sha256(seed:article_id)`."""
    groups = _group_by_article(rows)
    documents: dict[str, str] = {}
    questions: list[Question] = []
    for article_id in _ordered_article_ids(groups, seed=seed, max_articles=max_articles):
        rows_for_article = groups[article_id]
        title, text = _article_text(rows_for_article)
        document_id = f"ql-{article_id}.txt"
        documents[document_id] = _render_document(title, text)
        for row in rows_for_article:
            for question in row.questions:
                questions.append(
                    _convert_question(
                        question,
                        document_id=document_id,
                        seed=seed,
                        dev_fraction=dev_fraction,
                        source=row.source,
                    )
                )
    return Converted(documents=documents, questions=tuple(questions))


def _toml_string(value: str) -> str:
    """Quote a value for the TOML this script writes by hand, through JSON's escaping."""
    return json.dumps(value, ensure_ascii=False).replace("\x7f", "\\u007F")


def _question_toml(question: Question) -> str:
    axes = ", ".join(f"{name} = {_toml_string(question.axes[name])}" for name in _AXES)
    return (
        "[[question]]\n"
        f"id = {_toml_string(question.id)}\n"
        f"text = {_toml_string(question.text)}\n"
        f"language = {_toml_string(question.language)}\n"
        f"relevant_documents = [{_toml_string(question.relevant_documents[0])}]\n"
        f"reference_answer = {_toml_string(question.reference_answer or '')}\n"
        f"axes = {{ {axes} }}\n"
    )


def questions_toml(questions: Sequence[Question]) -> str:
    """The questions as a `[question_set]` schema-2 TOML file `read_question_set` reads back."""
    absent = ", ".join(_toml_string(field) for field in _ABSENT_FIELDS)
    axes = ", ".join(_toml_string(name) for name in _AXES)
    header = (
        "[question_set]\n"
        "schema = 2\n"
        f"absent = [{absent}]\n"
        f"absent_reason = {_toml_string(_ABSENT_REASON)}\n"
        f"axes = [{axes}]\n"
    )
    return header + "".join("\n" + _question_toml(question) for question in questions)


def _load_rows(source: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    with source.open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if stripped:
                rows.append(json.loads(stripped))
    return rows


def _summary(converted: Converted, *, total_characters: int) -> str:
    per_difficulty: dict[str, int] = {}
    for question in converted.questions:
        difficulty = question.axes["difficulty"]
        per_difficulty[difficulty] = per_difficulty.get(difficulty, 0) + 1
    by_difficulty = ", ".join(f"{name}={count}" for name, count in sorted(per_difficulty.items()))
    return (
        f"{len(converted.documents)} articles, {len(converted.questions)} questions, "
        f"{total_characters} characters, by difficulty: {by_difficulty}"
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Convert one local QuALITY `.dev` split into a document corpus and a question set."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--source", type=Path, required=True, help="QuALITY.v1.0.1.htmlstripped.dev"
    )
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--seed", default="44.41b")
    parser.add_argument("--dev-fraction", type=float, default=0.5)
    parser.add_argument("--max-articles", type=int, default=None)
    arguments = parser.parse_args(argv)

    rows = parse_rows(_load_rows(arguments.source))
    converted = convert(
        rows,
        seed=arguments.seed,
        dev_fraction=arguments.dev_fraction,
        max_articles=arguments.max_articles,
    )

    corpus_dir = arguments.out / "corpus"
    corpus_dir.mkdir(parents=True, exist_ok=True)
    total_characters = 0
    for document_id, content in converted.documents.items():
        (corpus_dir / document_id).write_text(content, encoding="utf-8")
        total_characters += len(content)
    (arguments.out / "quality-questions.toml").write_text(
        questions_toml(converted.questions), encoding="utf-8"
    )

    print(_summary(converted, total_characters=total_characters), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
