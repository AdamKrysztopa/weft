"""The MuSiQue-Ans converter — task **44.40**.

MuSiQue items are composed from single-hop steps, each answered by one paragraph among about
twenty. This script turns a sample of MuSiQue-Ans items into one text document per distinct
paragraph, the multi-hop questions (relevant documents = the supporting paragraphs), and a
single-hop control from each item's first step (relevant document = the one paragraph that step
names), so a multi-hop retrieval loss can be told apart from a plain retrieval miss. Unanswerable
items never enter the converted set; they are counted.

MuSiQue is CC BY 4.0 — attribution is required, and the files this script derives may be
committed with it. This module reads a local MuSiQue-Ans JSONL file already on disk and fetches
nothing itself; pinning a revision and downloading the dataset is the dispatcher's, not this
script's.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Final, cast

from open_ragbench_questions import split_of
from pydantic import BaseModel, ConfigDict

from weft_eval.question_set import QUESTION_SET_SCHEMA_VERSION, Question, QuestionField

#: The fields this converter cannot supply from MuSiQue-Ans: it labels no question kind or
#: difficulty and carries no verified quote.
_ABSENT: Final[tuple[str, ...]] = ("kind", "difficulty", "quote", "notes")
_ABSENT_REASON: Final[str] = (
    "converted from MuSiQue-Ans, which labels neither what a question asks for, how hard it is, "
    "nor a quoted span"
)
AXES: Final[tuple[str, ...]] = ("hops", "split", "control")
#: A step whose question still leans on an earlier step's answer (`#1`, `#2`, ...) cannot stand
#: alone as a single-hop control.
_BACK_REFERENCE: Final[re.Pattern[str]] = re.compile(r"#\d")


class MusiqueParagraph(BaseModel):
    """One paragraph MuSiQue offers as a candidate, supporting or a distractor."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    idx: int
    title: str
    text: str
    supporting: bool


class MusiqueStep(BaseModel):
    """One single-hop step of a MuSiQue item's decomposition."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    question: str
    answer: str
    support_idx: int | None


class MusiqueItem(BaseModel):
    """One MuSiQue-Ans item: its multi-hop question, the candidate paragraphs, and its steps."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    question: str
    answer: str
    answerable: bool
    paragraphs: tuple[MusiqueParagraph, ...]
    decomposition: tuple[MusiqueStep, ...]


class Converted(BaseModel):
    """What a sample of `MusiqueItem`s converts to: documents, both question sets, and a count."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    documents: Mapping[str, str]
    multi_hop: tuple[Question, ...]
    single_hop: tuple[Question, ...]
    dropped_unanswerable: int


def _field(raw: Mapping[str, object], key: str) -> object:
    if key not in raw:
        raise ValueError(f"MuSiQue item is missing required key '{key}'")
    return raw[key]


def _parse_paragraph(raw: Mapping[str, object]) -> MusiqueParagraph:
    return MusiqueParagraph(
        idx=cast(int, _field(raw, "idx")),
        title=cast(str, _field(raw, "title")),
        text=cast(str, _field(raw, "paragraph_text")),
        supporting=cast(bool, _field(raw, "is_supporting")),
    )


def _parse_step(raw: Mapping[str, object]) -> MusiqueStep:
    return MusiqueStep(
        question=cast(str, _field(raw, "question")),
        answer=cast(str, _field(raw, "answer")),
        support_idx=cast("int | None", raw.get("paragraph_support_idx")),
    )


def parse_item(raw: Mapping[str, object]) -> MusiqueItem:
    """Read one MuSiQue-Ans JSONL record into a `MusiqueItem`.

    `answer_aliases` and each step's `id` are ignored. `answerable` defaults to `True` when
    absent, since the MuSiQue-Ans files carry only answerable items. Any other required key that
    is missing raises `ValueError` naming it.
    """
    item_id = cast(str, _field(raw, "id"))
    question = cast(str, _field(raw, "question"))
    answer = cast(str, _field(raw, "answer"))
    paragraphs = tuple(
        _parse_paragraph(cast("Mapping[str, object]", entry))
        for entry in cast("Sequence[object]", _field(raw, "paragraphs"))
    )
    decomposition = tuple(
        _parse_step(cast("Mapping[str, object]", entry))
        for entry in cast("Sequence[object]", _field(raw, "question_decomposition"))
    )
    return MusiqueItem(
        id=item_id,
        question=question,
        answer=answer,
        answerable=cast(bool, raw.get("answerable", True)),
        paragraphs=paragraphs,
        decomposition=decomposition,
    )


def _document_id(title: str, text: str) -> str:
    return "mq-" + hashlib.sha256(f"{title}\n{text}".encode()).hexdigest()[:16]


def _sample_key(seed: str, item_id: str) -> str:
    return hashlib.sha256(f"{seed}:{item_id}".encode()).hexdigest()


def _multi_hop_question(
    item: MusiqueItem, supporting_ids: tuple[str, ...], *, seed: str, dev_fraction: float
) -> Question:
    split = split_of(sorted(supporting_ids)[0], seed=seed, dev_fraction=dev_fraction)
    return Question.model_validate(
        {
            "id": f"mq-{item.id}",
            "text": item.question,
            "language": "en",
            "relevant_documents": supporting_ids,
            "reference_answer": item.answer,
            "absent": frozenset(
                {
                    QuestionField.KIND,
                    QuestionField.DIFFICULTY,
                    QuestionField.QUOTE,
                    QuestionField.NOTES,
                }
            ),
            "absent_reason": _ABSENT_REASON,
            "axes": {
                "hops": str(len(item.decomposition)),
                "split": split,
                "control": "multi-hop",
            },
        }
    )


def _single_hop_question(
    item: MusiqueItem, document_of: Mapping[int, str], *, seed: str, dev_fraction: float
) -> Question | None:
    if not item.decomposition:
        return None
    step = item.decomposition[0]
    if step.support_idx is None or step.support_idx not in document_of:
        return None
    if _BACK_REFERENCE.search(step.question):
        return None
    document_id = document_of[step.support_idx]
    split = split_of(document_id, seed=seed, dev_fraction=dev_fraction)
    return Question.model_validate(
        {
            "id": f"mq-{item.id}-step1",
            "text": step.question,
            "language": "en",
            "relevant_documents": (document_id,),
            "reference_answer": step.answer,
            "absent": frozenset(
                {
                    QuestionField.KIND,
                    QuestionField.DIFFICULTY,
                    QuestionField.QUOTE,
                    QuestionField.NOTES,
                }
            ),
            "absent_reason": _ABSENT_REASON,
            "axes": {"hops": "1", "split": split, "control": "single-hop"},
        }
    )


def _convert_one(
    item: MusiqueItem, documents: dict[str, str], *, seed: str, dev_fraction: float
) -> tuple[Question, Question | None]:
    document_of: dict[int, str] = {}
    for paragraph in item.paragraphs:
        document_id = _document_id(paragraph.title, paragraph.text)
        documents[document_id] = f"{paragraph.title}\n\n{paragraph.text}"
        document_of[paragraph.idx] = document_id
    supporting_ids = tuple(
        document_of[paragraph.idx]
        for paragraph in sorted(item.paragraphs, key=lambda paragraph: paragraph.idx)
        if paragraph.supporting
    )
    multi_hop = _multi_hop_question(item, supporting_ids, seed=seed, dev_fraction=dev_fraction)
    single_hop = _single_hop_question(item, document_of, seed=seed, dev_fraction=dev_fraction)
    return multi_hop, single_hop


def convert(
    items: Sequence[MusiqueItem], *, per_hops: int, seed: str, dev_fraction: float
) -> Converted:
    """Sample `items` per hop count and convert the sample to documents and two question sets.

    Unanswerable items are dropped and counted rather than entering the sample. Within each hop
    count, the sample is the `per_hops` items ranked first by `sha256(f"{seed}:{item.id}")`, so
    the result does not depend on the input order.
    """
    dropped = 0
    by_hops: dict[int, list[MusiqueItem]] = {}
    for item in items:
        if not item.answerable:
            dropped += 1
            continue
        by_hops.setdefault(len(item.decomposition), []).append(item)

    documents: dict[str, str] = {}
    multi_hop: list[Question] = []
    single_hop: list[Question] = []
    for hop_count in sorted(by_hops):
        sampled = sorted(by_hops[hop_count], key=lambda item: _sample_key(seed, item.id))
        for item in sampled[:per_hops]:
            multi, single = _convert_one(item, documents, seed=seed, dev_fraction=dev_fraction)
            multi_hop.append(multi)
            if single is not None:
                single_hop.append(single)
    return Converted(
        documents=documents,
        multi_hop=tuple(multi_hop),
        single_hop=tuple(single_hop),
        dropped_unanswerable=dropped,
    )


def _toml_string(value: str) -> str:
    """Quote a value for the TOML this script writes by hand, through JSON's escaping.

    JSON's escapes are a subset of TOML's, except DEL, which TOML forbids raw.
    """
    return json.dumps(value, ensure_ascii=False).replace("\x7f", "\\u007F")


def _question_toml(question: Question) -> str:
    axes = ", ".join(f"{name} = {_toml_string(question.axes[name])}" for name in AXES)
    relevant = ", ".join(_toml_string(document_id) for document_id in question.relevant_documents)
    return (
        "[[question]]\n"
        f"id = {_toml_string(question.id)}\n"
        f"text = {_toml_string(question.text)}\n"
        f"language = {_toml_string(question.language)}\n"
        f"relevant_documents = [{relevant}]\n"
        f"reference_answer = {_toml_string(question.reference_answer or '')}\n"
        f"axes = {{ {axes} }}\n"
    )


def questions_toml(questions: Sequence[Question]) -> str:
    """Render `questions` as a schema-2 question file `read_question_set` reads back unchanged."""
    header = (
        "[question_set]\n"
        f"schema = {QUESTION_SET_SCHEMA_VERSION}\n"
        f"absent = [{', '.join(_toml_string(name) for name in _ABSENT)}]\n"
        f"absent_reason = {_toml_string(_ABSENT_REASON)}\n"
        f"axes = [{', '.join(_toml_string(name) for name in AXES)}]\n"
    )
    return header + "".join("\n" + _question_toml(question) for question in questions)


def _load_items(path: Path) -> list[MusiqueItem]:
    items: list[MusiqueItem] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped:
            items.append(parse_item(json.loads(stripped)))
    return items


def _write(converted: Converted, out: Path) -> None:
    corpus = out / "corpus"
    corpus.mkdir(parents=True, exist_ok=True)
    total_characters = 0
    for document_id, text in converted.documents.items():
        (corpus / f"{document_id}.txt").write_text(text, encoding="utf-8")
        total_characters += len(text)
    questions = converted.multi_hop + converted.single_hop
    (out / "musique-questions.toml").write_text(questions_toml(questions), encoding="utf-8")
    _print_summary(converted, total_characters)


def _print_summary(converted: Converted, total_characters: int) -> None:
    by_hops: dict[str, int] = {}
    for question in converted.multi_hop:
        hops = question.axes["hops"]
        by_hops[hops] = by_hops.get(hops, 0) + 1
    per_hops_report = ", ".join(f"{hops} hops: {count}" for hops, count in sorted(by_hops.items()))
    print(
        f"documents {len(converted.documents)} ({total_characters} characters), "
        f"multi-hop {len(converted.multi_hop)} ({per_hops_report}), "
        f"single-hop controls {len(converted.single_hop)}, "
        f"dropped unanswerable {converted.dropped_unanswerable}",
        flush=True,
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Convert a local MuSiQue-Ans JSONL file into a document corpus and a question file.

    Args:
        argv: The command-line arguments; `None` reads `sys.argv`.

    Returns:
        The process exit code.
    """
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--input", type=Path, required=True, help="a local MuSiQue-Ans JSONL file")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--per-hops", type=int, default=100)
    parser.add_argument("--seed", default="44.40")
    parser.add_argument("--dev-fraction", type=float, default=0.5)
    arguments = parser.parse_args(argv)

    items = _load_items(arguments.input)
    converted = convert(
        items,
        per_hops=arguments.per_hops,
        seed=arguments.seed,
        dev_fraction=arguments.dev_fraction,
    )
    arguments.out.mkdir(parents=True, exist_ok=True)
    _write(converted, arguments.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
