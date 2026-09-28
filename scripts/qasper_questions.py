"""The QASPER converter — task **44.41**.

QASPER (Dasigi et al., 2021) asks questions of whole research papers; each question carries one or
more annotators' answers, each an extractive span, free-form text, a yes/no, or a statement that
the paper does not answer it. This converts one QASPER split into `weft_eval.question_set` form: one
text document per paper — title, abstract, every section — and one question per paper question
whose first annotator gave an answer, split by paper so a paper's questions never straddle dev and
test.

QASPER is distributed under CC BY 4.0, which requires attribution: this script reads a local copy of
the archive (`--archive`) and fetches nothing over the network.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import tarfile
from collections.abc import Mapping, Sequence
from enum import StrEnum
from pathlib import Path
from typing import Final, cast

from open_ragbench_questions import split_of
from pydantic import BaseModel, ConfigDict

from weft_eval.question_set import Question

_ABSENT_REASON: Final[str] = (
    "converted from QASPER, which labels neither a question's kind, its difficulty, a supporting "
    "quote nor free-form provenance notes"
)
_ABSENT_FIELDS: Final[tuple[str, ...]] = ("kind", "difficulty", "quote", "notes")
_AXES: Final[tuple[str, ...]] = ("answer-type", "split")


class AnswerKind(StrEnum):
    """What shape a QASPER annotator's answer takes."""

    EXTRACTIVE = "extractive"
    ABSTRACTIVE = "abstractive"
    BOOLEAN = "boolean"
    NONE = "none"


class QasperAnswer(BaseModel):
    """One annotator's answer to one QASPER question."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: AnswerKind
    text: str


class QasperQuestion(BaseModel):
    """One QASPER question, with every annotator's answer in the order QASPER lists them."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    text: str
    answers: tuple[QasperAnswer, ...]


class QasperSection(BaseModel):
    """One section of a QASPER paper's full text."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    paragraphs: tuple[str, ...]


class QasperPaper(BaseModel):
    """One QASPER paper — its title, abstract, sections and the questions asked of it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    title: str
    abstract: str
    sections: tuple[QasperSection, ...]
    questions: tuple[QasperQuestion, ...]


class Converted(BaseModel):
    """The result of converting a batch of QASPER papers: documents, questions, and what was cut."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    documents: Mapping[str, str]
    questions: tuple[Question, ...]
    dropped_unanswerable: int


def _require(raw: Mapping[str, object], key: str) -> object:
    if key not in raw:
        raise ValueError(f"missing required field {key!r}")
    return raw[key]


def _parse_section(raw: Mapping[str, object]) -> QasperSection:
    name = _require(raw, "section_name")
    paragraphs = cast("Sequence[object]", _require(raw, "paragraphs"))
    return QasperSection(name=str(name), paragraphs=tuple(str(item) for item in paragraphs))


def _parse_answer(raw: Mapping[str, object]) -> QasperAnswer:
    answer = cast("Mapping[str, object]", _require(raw, "answer"))
    spans = cast("Sequence[object]", answer.get("extractive_spans") or ())
    free_form = str(answer.get("free_form_answer") or "")
    yes_no = answer.get("yes_no")
    if answer.get("unanswerable"):
        return QasperAnswer(kind=AnswerKind.NONE, text="")
    if spans:
        return QasperAnswer(kind=AnswerKind.EXTRACTIVE, text="; ".join(str(s) for s in spans))
    if free_form:
        return QasperAnswer(kind=AnswerKind.ABSTRACTIVE, text=free_form)
    if yes_no is not None:
        return QasperAnswer(kind=AnswerKind.BOOLEAN, text="Yes" if yes_no else "No")
    return QasperAnswer(kind=AnswerKind.NONE, text="")


def _parse_question(raw: Mapping[str, object]) -> QasperQuestion:
    question_id = _require(raw, "question_id")
    text = _require(raw, "question")
    raw_answers = cast("Sequence[Mapping[str, object]]", _require(raw, "answers"))
    answers = tuple(_parse_answer(entry) for entry in raw_answers)
    return QasperQuestion(id=str(question_id), text=str(text), answers=answers)


def parse_paper(paper_id: str, raw: Mapping[str, object]) -> QasperPaper:
    """Read one QASPER paper's `title`, `abstract`, `full_text` and `qas` out of its raw JSON."""
    title = _require(raw, "title")
    abstract = _require(raw, "abstract")
    raw_sections = cast("Sequence[Mapping[str, object]]", _require(raw, "full_text"))
    raw_qas = cast("Sequence[Mapping[str, object]]", _require(raw, "qas"))
    sections = tuple(_parse_section(entry) for entry in raw_sections)
    questions = tuple(_parse_question(entry) for entry in raw_qas)
    return QasperPaper(
        id=paper_id,
        title=str(title),
        abstract=str(abstract),
        sections=sections,
        questions=questions,
    )


def _render_document(paper: QasperPaper) -> str:
    header = f"{paper.title}\n\n{paper.abstract}\n\n"
    sections = "\n\n".join(
        f"## {section.name}\n\n" + "\n\n".join(section.paragraphs) for section in paper.sections
    )
    return header + sections


def _first_answer(question: QasperQuestion) -> QasperAnswer:
    if not question.answers:
        return QasperAnswer(kind=AnswerKind.NONE, text="")
    return question.answers[0]


def _ordered_papers(
    papers: Sequence[QasperPaper], *, seed: str, max_papers: int | None
) -> list[QasperPaper]:
    ordered = sorted(
        papers, key=lambda paper: hashlib.sha256(f"{seed}:{paper.id}".encode()).hexdigest()
    )
    return ordered if max_papers is None else ordered[:max_papers]


def _convert_paper(
    paper: QasperPaper, *, seed: str, dev_fraction: float
) -> tuple[str, str, list[Question], int]:
    document_id = f"qp-{paper.id}"
    split = split_of(document_id, seed=seed, dev_fraction=dev_fraction)
    questions: list[Question] = []
    dropped = 0
    for question in paper.questions:
        answer = _first_answer(question)
        if answer.kind is AnswerKind.NONE:
            dropped += 1
            continue
        questions.append(
            Question.model_validate(
                {
                    "id": f"qp-{question.id}",
                    "text": question.text,
                    "language": "en",
                    "relevant_documents": (document_id,),
                    "reference_answer": answer.text,
                    "absent": _ABSENT_FIELDS,
                    "absent_reason": _ABSENT_REASON,
                    "axes": {"answer-type": answer.kind.value, "split": split},
                }
            )
        )
    return document_id, _render_document(paper), questions, dropped


def convert(
    papers: Sequence[QasperPaper],
    *,
    seed: str,
    dev_fraction: float,
    max_papers: int | None = None,
) -> Converted:
    """One document and its answerable questions per paper, ordered by `sha256(seed:paper.id)`."""
    documents: dict[str, str] = {}
    questions: list[Question] = []
    dropped_unanswerable = 0
    for paper in _ordered_papers(papers, seed=seed, max_papers=max_papers):
        document_id, content, paper_questions, dropped = _convert_paper(
            paper, seed=seed, dev_fraction=dev_fraction
        )
        documents[document_id] = content
        questions.extend(paper_questions)
        dropped_unanswerable += dropped
    return Converted(
        documents=documents, questions=tuple(questions), dropped_unanswerable=dropped_unanswerable
    )


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


def _find_member(tar: tarfile.TarFile, name: str) -> tarfile.TarInfo:
    for member in tar.getmembers():
        if member.name == name or member.name.endswith(f"/{name}"):
            return member
    raise ValueError(f"{name}: not found in {tar.name}")


def _load_papers(archive: Path, split: str) -> list[QasperPaper]:
    name = f"qasper-{split}-v0.3.json"
    with tarfile.open(archive) as tar:
        member = _find_member(tar, name)
        handle = tar.extractfile(member)
        if handle is None:
            raise ValueError(f"{name}: not a regular file in {archive}")
        raw = cast("dict[str, dict[str, object]]", json.loads(handle.read()))
    return [parse_paper(paper_id, paper_raw) for paper_id, paper_raw in raw.items()]


def _summary(converted: Converted, *, total_characters: int) -> str:
    per_kind: dict[str, int] = {}
    for question in converted.questions:
        kind = question.axes["answer-type"]
        per_kind[kind] = per_kind.get(kind, 0) + 1
    by_kind = ", ".join(f"{kind}={count}" for kind, count in sorted(per_kind.items()))
    return (
        f"{len(converted.documents)} papers, {total_characters} characters, "
        f"questions by answer type: {by_kind}, dropped unanswerable: "
        f"{converted.dropped_unanswerable}"
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Convert one local QASPER split into a document corpus and a question set."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--archive", type=Path, required=True, help="qasper-train-dev-v0.3.tgz")
    parser.add_argument("--split", choices=("dev", "train"), default="dev")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--seed", default="44.41")
    parser.add_argument("--dev-fraction", type=float, default=0.5)
    parser.add_argument("--max-papers", type=int, default=None)
    arguments = parser.parse_args(argv)

    papers = _load_papers(arguments.archive, arguments.split)
    converted = convert(
        papers,
        seed=arguments.seed,
        dev_fraction=arguments.dev_fraction,
        max_papers=arguments.max_papers,
    )

    corpus_dir = arguments.out / "corpus"
    corpus_dir.mkdir(parents=True, exist_ok=True)
    total_characters = 0
    for document_id, content in converted.documents.items():
        (corpus_dir / f"{document_id}.txt").write_text(content, encoding="utf-8")
        total_characters += len(content)
    (arguments.out / "qasper-questions.toml").write_text(
        questions_toml(converted.questions), encoding="utf-8"
    )

    print(_summary(converted, total_characters=total_characters), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
