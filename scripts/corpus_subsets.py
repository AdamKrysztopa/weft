"""Nested corpus subsets for E1, the whole-corpus size sweep — task 44.51.

E1 asks at what corpus size reading the whole corpus stops beating one search. It runs the same
arm pair on nested subsets of `validation-en`, so a subset must contain every smaller one, and a
question may run on a subset only when every document it cites is in it — a question whose answer
lies outside the subset would measure the subset, not the method.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Sequence
from pathlib import Path, PurePath

from weft_eval.question_set import Question, read_question_set


def _label_matches(label_parts: tuple[str, ...], document_parts: tuple[str, ...]) -> bool:
    """Whether label_parts is a suffix of document_parts, component-wise."""
    if len(label_parts) > len(document_parts):
        return False
    return document_parts[len(document_parts) - len(label_parts) :] == label_parts


def _document_resolves(label: str, documents: Sequence[str]) -> bool:
    """Whether a label resolves to a document in documents as a path suffix."""
    label_parts = PurePath(label).parts
    for document in documents:
        document_parts = PurePath(document).parts
        if _label_matches(label_parts, document_parts):
            return True
    return False


def nested_subsets(
    documents: Sequence[str], *, fractions: Sequence[float], seed: str
) -> dict[float, tuple[str, ...]]:
    """Order documents by seed and return nested subsets for each fraction.

    Documents are ordered by sha256(f"{seed}:{document}"). Each fraction's subset is the first
    round(fraction * len(documents)) of that order (at least 1), so subsets nest by construction.
    """
    ordered = sorted(
        documents, key=lambda doc: hashlib.sha256(f"{seed}:{doc}".encode()).hexdigest()
    )

    result: dict[float, tuple[str, ...]] = {}
    for fraction in fractions:
        size = max(1, round(fraction * len(documents)))
        result[fraction] = tuple(ordered[:size])

    return result


def questions_within(
    questions: Sequence[Question], documents: Sequence[str]
) -> tuple[Question, ...]:
    """Keep questions whose relevant_documents all resolve within documents."""
    kept: list[Question] = []
    for question in questions:
        if all(_document_resolves(label, documents) for label in question.relevant_documents):
            kept.append(question)
    return tuple(kept)


def _toml_string(value: str) -> str:
    """Quote a value for TOML, through JSON's escaping."""
    return json.dumps(value, ensure_ascii=False).replace("\x7f", "\\u007F")


def _question_toml_lines(question: Question) -> list[str]:
    """Generate TOML lines for a single question."""
    lines: list[str] = ["[[question]]"]
    lines.append(f"id = {_toml_string(question.id)}")
    lines.append(f"text = {_toml_string(question.text)}")
    lines.append(f"language = {_toml_string(question.language)}")
    if question.modality.value != "text":
        lines.append(f"modality = {_toml_string(question.modality.value)}")
    if question.kind is not None:
        lines.append(f"kind = {_toml_string(question.kind.value)}")
    if question.difficulty is not None:
        lines.append(f"difficulty = {_toml_string(question.difficulty.value)}")
    if question.relevant_documents:
        docs = ", ".join(_toml_string(doc) for doc in question.relevant_documents)
        lines.append(f"relevant_documents = [{docs}]")
    if question.reference_answer:
        lines.append(f"reference_answer = {_toml_string(question.reference_answer)}")
    if question.quote:
        q = question.quote[0]
        quote_text = _toml_string(q.text)
        quote_page = q.page
        quote_line = f"{{ text = {quote_text}, page = {quote_page} }}"
        lines.append(f"quote = {quote_line}")
    if question.notes:
        lines.append(f"notes = {_toml_string(question.notes)}")
    if question.axes:
        axes_pairs = ", ".join(
            f"{name} = {_toml_string(question.axes[name])}" for name in sorted(question.axes.keys())
        )
        lines.append(f"axes = {{ {axes_pairs} }}")
    return lines


def _write_questions_toml(questions: Sequence[Question], path: Path) -> None:
    """Write questions to a TOML file, preserving all fields from input questions."""
    lines: list[str] = ["[question_set]", "schema = 2"]

    if questions:
        first_question = questions[0]
        if first_question.absent:
            absent_list = ", ".join(_toml_string(field) for field in first_question.absent)
            lines.append(f"absent = [{absent_list}]")
        if first_question.absent_reason:
            lines.append(f"absent_reason = {_toml_string(first_question.absent_reason)}")
        if first_question.axes:
            axes_list = ", ".join(_toml_string(name) for name in sorted(first_question.axes.keys()))
            lines.append(f"axes = [{axes_list}]")

    lines.append("")
    for question in questions:
        lines.extend(_question_toml_lines(question))
        lines.append("")

    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    """Create nested subsets of a corpus with corresponding question sets."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, required=True, help="Corpus directory")
    parser.add_argument(
        "--questions", type=Path, nargs="+", required=True, help="Question TOML files"
    )
    parser.add_argument(
        "--fractions",
        type=float,
        nargs="+",
        default=[0.25, 0.5, 1.0],
        help="Fractions (default: 0.25 0.5 1.0)",
    )
    parser.add_argument("--seed", default="44.51", help="Random seed (default: 44.51)")
    parser.add_argument("--out", type=Path, required=True, help="Output directory")
    args = parser.parse_args(argv)

    corpus_dir = args.corpus.resolve()
    out_dir = args.out
    out_dir.mkdir(parents=True, exist_ok=True)

    document_files = [
        str(f.relative_to(corpus_dir)) for f in sorted(corpus_dir.rglob("*")) if f.is_file()
    ]

    all_questions_list = [read_question_set(qfile).questions for qfile in args.questions]
    all_questions = ()
    for qs in all_questions_list:
        all_questions = all_questions + qs

    corpus_name = corpus_dir.name
    subsets = nested_subsets(
        document_files, fractions=tuple(sorted(args.fractions)), seed=args.seed
    )

    for fraction in sorted(subsets.keys()):
        subset_docs = subsets[fraction]
        subset_dir_name = f"{corpus_name}-{int(fraction * 100):d}"
        subset_dir = out_dir / subset_dir_name

        subset_dir.mkdir(parents=True, exist_ok=True)
        for doc in subset_docs:
            src = corpus_dir / doc
            dst = subset_dir / doc
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.symlink_to(src.resolve())

        subset_questions = questions_within(all_questions, subset_docs)

        questions_file = out_dir / f"{subset_dir_name}-questions.toml"
        _write_questions_toml(subset_questions, questions_file)

        pct = int(fraction * 100)
        print(
            f"{pct}%: {len(subset_docs)} documents, {len(subset_questions)} questions", flush=True
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
