"""Open RAGBench's questions as a question set — Phase 38 task **38.4**.

Reads `queries.json`, `qrels.json` and `answers.json` from a copy of `vectara/open_ragbench` whose
bytes `corpus/open-ragbench.toml` pins, and writes `dev.toml` and `test.toml` in
`weft_eval.question_set`'s form, plus `build.json` recording what the build did.

**What each question carries, and what it states absent.** `text` is the dataset's query and
`reference_answer` its answer. `relevant_documents` is the one labelled document, by the id
`corpus/open-ragbench.toml` gives it. The labelled *section* enters as a quote: its opening span,
verified literally against the markdown the corpus stores (Phase 38 Q3 — a section is several
chunks long, so a span is the unit that can resolve at quote granularity). The dataset's own
`source` and `type` are the axes `evidence` and `answer-form`. It labels neither what a question
asks for nor its difficulty, so `kind` and `difficulty` are stated absent rather than guessed.

**The split is by source document.** A document's questions share one side, so nothing learned on
the development side about a paper is scored again on the test side. A document's side is a pure
function of the seed and its id, so the split reproduces from the two recorded values.

**A question the build cannot carry is counted and named, never dropped silently.** `build.json`
lists each with its reason, and the build prints the count.

Run as `uv run python scripts/open_ragbench_questions.py --dataset
corpus/open_ragbench/pdf/arxiv --out corpus/open-ragbench-questions`.

**The quote check is `eval/check_questions.py`'s own**, run over every carried question before a
file is written; a span it rejects is a defect in this script, and the build refuses rather than
writing a set with a quote nothing verified.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "eval"))

from check_questions import unmatched_quotes
from open_ragbench import RAGBENCH_REVISION, render_document

from weft_eval.question_set import QUESTION_SET_SCHEMA_VERSION, Question, read_question_set

#: A span shorter than this is not evidence of a section — a heading fragment matches anywhere.
MIN_SPAN: Final[int] = 40
#: The caps tried in order; the first that yields a span occurring once in its document wins.
#: Measured over the 3,045 questions at revision 63f6b05: a flat 160 leaves 15.9% of quotes across
#: a 512/462 chunk boundary, shortest-unique leaves 1.5%, with 27 spans repeated at every cap.
SPAN_CAPS: Final[tuple[int, ...]] = (60, 80, 100, 120, 140, 160)
MAX_SPAN: Final[int] = SPAN_CAPS[-1]
_CHUNK_SIZE: Final[int] = 512
_CHUNK_STRIDE: Final[int] = 462

AXES: Final[tuple[str, ...]] = ("evidence", "answer-form", "split")
SPLITS: Final[tuple[str, ...]] = ("dev", "test")

_ABSENT_REASON: Final[str] = (
    "Open RAGBench labels neither what a question asks for nor how hard it is, "
    "and a label nobody checked would be sliced as if somebody had"
)


class UnverifiedQuoteError(ValueError):
    """A carried question's quote is not found in the document it names."""


@dataclass
class Build:
    """What one build did.

    How many questions it carried, which it could not and why, how many carried quotes no chunk
    window holds whole, and the digest of each file it wrote.
    """

    carried: int = 0
    uncarried: dict[str, str] = field(default_factory=dict[str, str])
    straddling: int = 0
    files: dict[str, str] = field(default_factory=dict[str, str])
    #: `weft_eval.question_set.question_set_digest` of each file — what a run record carries.
    question_set_digests: dict[str, str] = field(default_factory=dict[str, str])
    counts: dict[str, int] = field(default_factory=dict[str, int])


def opening_span(text: str, document: str | None = None) -> str | None:
    """Return the shortest defensible opening span of a section.

    That is the first sentence of its first line of prose at least `MIN_SPAN` long, cut on a word
    boundary at the first cap in `SPAN_CAPS` whose span occurs exactly once in `document` — or at
    `MAX_SPAN` when none does, or when no document is given. A verbatim substring of `text`;
    `None` where the section has no such line. Headings and figure or table links (`![…](…)`) are
    not prose.
    """
    chosen: str | None = None
    for cap in SPAN_CAPS:
        span = _span_at(text, cap)
        if span is None:
            continue
        chosen = span
        if document is not None and document.count(span) == 1:
            return span
    return chosen


def _span_at(text: str, cap: int) -> str | None:
    for candidate in text.split("\n"):
        stripped = candidate.strip()
        if not stripped or stripped.startswith(("#", "![")):
            continue
        line = candidate.rstrip()
        end = _sentence_end(line)
        span = line[:end] if end is not None else line
        if len(span) > cap:
            cut = span.rfind(" ", 0, cap + 1)
            span = span[:cut] if cut > 0 else span[:cap]
        span = span.rstrip()
        if len(span.strip()) >= MIN_SPAN:
            return span
    return None


def _sentence_end(line: str) -> int | None:
    """The index just past the first full stop that ends a sentence at least `MIN_SPAN` long."""
    position = line.find(".", MIN_SPAN - 1)
    while position != -1:
        if position + 1 == len(line) or line[position + 1] == " ":
            return position + 1
        position = line.find(".", position + 1)
    return None


def split_of(document_id: str, *, seed: str, dev_fraction: float) -> str:
    """`dev` or `test` for every question on `document_id` — a pure function of the seed and id."""
    value = int(hashlib.sha256(f"{seed}:{document_id}".encode()).hexdigest()[:8], 16)
    return "dev" if value / 0xFFFFFFFF < dev_fraction else "test"


def _straddles(offset: int, length: int) -> bool:
    """Whether no chunk window holds `[offset, offset + length)` whole.

    The window starting latest at or before `offset` ends latest, so it is the only one worth
    asking.
    """
    start = (offset // _CHUNK_STRIDE) * _CHUNK_STRIDE
    return offset + length > start + _CHUNK_SIZE


def _toml_string(value: str) -> str:
    """A TOML basic string.

    JSON's escapes are a subset of TOML's, except DEL, which TOML forbids raw.
    """
    return json.dumps(value, ensure_ascii=False).replace("\x7f", "\\u007F")


def _question_toml(question: Question) -> str:
    quote = question.quote[0]
    axes = ", ".join(f"{name} = {_toml_string(question.axes[name])}" for name in AXES)
    return (
        "[[question]]\n"
        f"id = {_toml_string(question.id)}\n"
        f"text = {_toml_string(question.text)}\n"
        f"language = {_toml_string(question.language)}\n"
        f"relevant_documents = [{_toml_string(question.relevant_documents[0])}]\n"
        f"reference_answer = {_toml_string(question.reference_answer or '')}\n"
        f"notes = {_toml_string(question.notes or '')}\n"
        f"axes = {{ {axes} }}\n"
        "\n"
        "  [[question.quote]]\n"
        f"  document = {_toml_string(quote.document)}\n"
        f"  page = {quote.page}\n"
        f"  text = {_toml_string(quote.text)}\n"
    )


def _header(split: str, *, seed: str, dev_fraction: float) -> str:
    return (
        f"# Open RAGBench questions, split '{split}' — Phase 38 task 38.4. Generated by\n"
        f"# `scripts/open_ragbench_questions.py` from revision {RAGBENCH_REVISION}, seed "
        f"{seed!r}, dev fraction {dev_fraction}. Edit the script, not this file.\n\n"
        "[question_set]\n"
        f"schema = {QUESTION_SET_SCHEMA_VERSION}\n"
        'absent = ["kind", "difficulty"]\n'
        f"absent_reason = {_toml_string(_ABSENT_REASON)}\n"
        f"axes = [{', '.join(_toml_string(name) for name in AXES)}]\n"
    )


def stratified_subset(
    questions: Sequence[Question], size: int, *, seed: str
) -> tuple[Question, ...]:
    """Draw `size` questions so each `(evidence, answer-form)` stratum keeps its share.

    The share is of `questions` — Phase 38 Q5. Shares are rounded by largest remainder so the
    strata sum to `size` exactly; within a stratum the questions taken are the first by
    `sha256(seed:id)`, so the subset is a pure function of the seed and the ids. The result keeps
    `questions`' own order.
    """
    strata: dict[tuple[str, str], list[Question]] = {}
    for question in questions:
        strata.setdefault((question.axes["evidence"], question.axes["answer-form"]), []).append(
            question
        )
    total = len(questions)
    exact = {key: size * len(members) / total for key, members in strata.items()}
    taken = {key: int(share) for key, share in exact.items()}
    by_remainder = sorted(exact, key=lambda key: (-(exact[key] - taken[key]), key))
    for key in by_remainder[: size - sum(taken.values())]:
        taken[key] += 1
    chosen: set[str] = set()
    for key, members in strata.items():
        ranked = sorted(
            members, key=lambda q: hashlib.sha256(f"{seed}:{q.id}".encode()).hexdigest()
        )
        chosen.update(question.id for question in ranked[: taken[key]])
    return tuple(question for question in questions if question.id in chosen)


def _carry(
    dataset: Path,
    identifier: str,
    query: dict[str, Any],
    label: dict[str, Any],
    answers: dict[str, Any],
    texts: dict[str, str],
    result: Build,
    *,
    seed: str,
    dev_fraction: float,
) -> tuple[str, Question] | None:
    document_id = str(label["doc_id"])
    section_id = int(label["section_id"])
    source = dataset / "corpus" / f"{document_id}.json"
    if not source.is_file():
        result.uncarried[identifier] = f"labelled document {document_id} is not in the corpus"
        return None
    body = source.read_bytes()
    sections = json.loads(body)["sections"]
    if not 0 <= section_id < len(sections):
        result.uncarried[identifier] = f"gold section {section_id} of {document_id} does not exist"
        return None
    text = texts.setdefault(document_id, render_document(body).text)
    span = opening_span(str(sections[section_id]["text"]), text)
    if span is None:
        result.uncarried[identifier] = (
            f"gold section {section_id} of {document_id} has no line of prose "
            f"{MIN_SPAN} characters long"
        )
        return None
    split = split_of(document_id, seed=seed, dev_fraction=dev_fraction)
    question = Question.model_validate(
        {
            "id": identifier,
            "text": query["query"],
            "language": "en",
            "relevant_documents": (document_id,),
            "reference_answer": answers[identifier],
            "notes": f"Open RAGBench qrels: document {document_id}, section {section_id}",
            "quote": ({"document": document_id, "page": 0, "text": span},),
            "absent": ("kind", "difficulty"),
            "absent_reason": _ABSENT_REASON,
            "axes": {
                "evidence": query["source"],
                "answer-form": query["type"],
                "split": split,
            },
        }
    )
    offset = text.find(span)
    if offset >= 0 and _straddles(offset, len(span)):
        result.straddling += 1
    result.carried += 1
    return split, question


def build(
    dataset: Path,
    out: Path,
    *,
    seed: str,
    dev_fraction: float,
    subset: int | None = None,
) -> Build:
    """Build the question files from the dataset copy at `dataset` into `out`."""
    queries = json.loads((dataset / "queries.json").read_text(encoding="utf-8"))
    qrels = json.loads((dataset / "qrels.json").read_text(encoding="utf-8"))
    answers = json.loads((dataset / "answers.json").read_text(encoding="utf-8"))

    result = Build()
    texts: dict[str, str] = {}
    by_split: dict[str, list[Question]] = {split: [] for split in SPLITS}
    for identifier, query in queries.items():
        carried = _carry(
            dataset,
            identifier,
            query,
            qrels[identifier],
            answers,
            texts,
            result,
            seed=seed,
            dev_fraction=dev_fraction,
        )
        if carried is not None:
            split, question = carried
            by_split[split].append(question)

    unmatched = unmatched_quotes(
        [question for questions in by_split.values() for question in questions], texts
    )
    if unmatched:
        message = (
            f"{len(unmatched)} quote(s) not found in their documents: {'; '.join(unmatched[:5])}"
        )
        raise UnverifiedQuoteError(message)

    out.mkdir(parents=True, exist_ok=True)
    files = dict(by_split)
    if subset is not None:
        files[f"dev-subset-{subset}"] = list(stratified_subset(by_split["dev"], subset, seed=seed))
    for split, questions in files.items():
        path = out / f"{split}.toml"
        body = _header(split, seed=seed, dev_fraction=dev_fraction) + "".join(
            "\n" + _question_toml(question) for question in questions
        )
        path.write_text(body, encoding="utf-8")
        result.files[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
        read = read_question_set(path)
        result.question_set_digests[path.name] = read.digest
        result.counts[path.name] = len(read.questions)
    return result


def pin_text(result: Build, *, seed: str, dev_fraction: float) -> str:
    """Render the tracked record of a build.

    What it was built from and what it wrote, so a copy of the untracked files can be checked
    against it and a run record's question-set digest traced to a split.
    """
    lines = [
        "# The Open RAGBench question files — Phase 38 task 38.4. Generated by",
        "# `scripts/open_ragbench_questions.py --pin`; the files themselves are not tracked.",
        "",
        "[build]",
        f'revision = "{RAGBENCH_REVISION}"',
        f"seed = {_toml_string(seed)}",
        f"dev_fraction = {dev_fraction}",
        f"carried = {result.carried}",
        f"uncarried = {len(result.uncarried)}",
        f"straddling = {result.straddling}",
    ]
    for name in sorted(result.files):
        lines += [
            "",
            "[[file]]",
            f'name = "{name}"',
            f"questions = {result.counts[name]}",
            f'sha256 = "{result.files[name]}"',
            f'question_set_digest = "{result.question_set_digests[name]}"',
        ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    """Build the Open RAGBench question files and report what was carried.

    Args:
        argv: The command-line arguments; `None` reads `sys.argv`.

    Returns:
        The process exit code.
    """
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--seed", default="38.4")
    parser.add_argument("--dev-fraction", type=float, default=0.5)
    parser.add_argument("--pin", type=Path, default=None, help="also write the tracked pin here")
    parser.add_argument(
        "--subset", type=int, default=None, help="also write a stratified dev subset of this size"
    )
    arguments = parser.parse_args(argv)

    result = build(
        arguments.dataset,
        arguments.out,
        seed=arguments.seed,
        dev_fraction=arguments.dev_fraction,
        subset=arguments.subset,
    )
    record = {
        "revision": RAGBENCH_REVISION,
        "seed": arguments.seed,
        "dev_fraction": arguments.dev_fraction,
        "carried": result.carried,
        "straddling": result.straddling,
        "uncarried": result.uncarried,
        "files": result.files,
    }
    if arguments.pin is not None:
        arguments.pin.write_text(
            pin_text(result, seed=arguments.seed, dev_fraction=arguments.dev_fraction),
            encoding="utf-8",
        )
    (arguments.out / "build.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(f"carried {result.carried}, could not carry {len(result.uncarried)}")
    for identifier, reason in sorted(result.uncarried.items()):
        print(f"  {identifier}: {reason}")
    rate = result.straddling / result.carried if result.carried else 0.0
    print(f"quotes straddling a 512/462 chunk boundary: {result.straddling} ({rate:.1%})")
    for name, digest in result.files.items():
        print(f"  {name}: sha256 {digest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
