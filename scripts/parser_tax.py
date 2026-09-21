"""What reading the raw PDFs costs against the dataset's own rendering — Phase 38 task **38.8**.

Two measurements make up "the parser tax": whether Weft's own ingest still finds a dev quote once
the document has gone through a PDF extractor instead of Open RAGBench's own markdown rendering,
and whether two run records are even comparable before their numbers are compared at all.

`quote_survival` answers the first. A dev quote is written against a document's *text*, not against
any one chunker's boundaries, so it survives ingest when it sits **whole inside one stored chunk**
of the document it names — the same test `38.4` published for the markdown corpus (1,511 of 1,548).
A quote split across a chunk boundary, or landing in a document that was never stored at all, is
counted and named rather than silently dropped from the average.

`require_parser_pair` answers the second: two `CorpusSide` records — one for the markdown corpus,
one for the raw-PDF corpus — are a comparable pair only when the corpus is the *one* thing that
differs between them. Pairing across a different question set or a different query pipeline would
attribute a different cause's swing to parsing, so it is refused rather than measured.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

import psycopg
from pydantic import BaseModel, ConfigDict

from weft_eval.falsify import PairedDifference, paired_differences
from weft_eval.question_set import Question, read_question_set
from weft_eval.run_record import QueryRung, RunRecord, load_run_record
from weft_kernel.payload import Produced

_METRICS = ("recall@5", "mrr@5", "ndcg@5")


class QuoteSurvival(BaseModel):
    """How many dev quotes survive intact once their document is chunked and stored.

    `lost` and `unstored` name the questions rather than only counting them, because a parser-tax
    report has to say *which* documents lost coverage, not just how many did.
    """

    model_config = ConfigDict(frozen=True)

    total: int
    whole: int
    #: Question ids whose quote's document has stored chunks, but no chunk holds it whole.
    lost: tuple[str, ...]
    #: Question ids whose quote's document was never stored at all.
    unstored: tuple[str, ...]


def _collapsed(text: str) -> str:
    return " ".join(text.split())


def quote_survival(
    questions: Sequence[Question], chunks: Mapping[str, Sequence[str]]
) -> QuoteSurvival:
    """Checks every quote of every question against the stored chunks of the document it names.

    Whitespace runs are collapsed on both sides before comparing, the way the ingest's own
    `whitespace` cleaner normalises a chunk before it is stored — a quote copied from a wrapped
    PDF line is not "lost" over a line break nothing downstream will ever see either.
    """
    total = 0
    whole = 0
    lost: list[str] = []
    unstored: list[str] = []
    for question in questions:
        for quote in question.quote:
            total += 1
            document_chunks = chunks.get(quote.document, ())
            if not document_chunks:
                unstored.append(question.id)
                continue
            needle = _collapsed(quote.text)
            if any(needle in _collapsed(chunk) for chunk in document_chunks):
                whole += 1
            else:
                lost.append(question.id)
    return QuoteSurvival(total=total, whole=whole, lost=tuple(lost), unstored=tuple(unstored))


class CorpusSide(BaseModel):
    """One side of a parser-tax comparison: a run record, reduced to what pairing needs to check."""

    model_config = ConfigDict(frozen=True)

    label: str
    corpus_digest: str
    question_set_digest: str
    query_pipeline: str
    #: The query rung's own `identity` (`QueryRung.identity`) — repair **R38.19**. Two rungs can
    #: share a name and resolve to different pipelines, the identical distinction `weft eval
    #: compare`'s `QueryRung` docstring draws between its `name` and `identity` fields.
    query_identity: str
    #: Repair **R38.19** — `weft eval compare`'s own `_incomparable_reasons` refuses a comparison
    #: over differing `model_versions`; a parser-tax pair is refused on the identical fact.
    model_versions: dict[str, str]


def require_parser_pair(markdown: CorpusSide, pdf: CorpusSide) -> None:
    """Refuses to pair two sides unless the corpus is the only thing that differs between them.

    Any other difference — a different question set, a different query pipeline, a different
    query rung identity, or a different model a role resolved to — would let a second cause ride
    along inside a number reported as "the cost of parsing", so each is refused by name rather
    than absorbed into the comparison. Mirrors what `weft eval compare`'s own
    `_incomparable_reasons` refuses (`packages/weft-rag/src/weft_cli/eval_commands.py`).
    """
    if markdown.question_set_digest != pdf.question_set_digest:
        message = (
            f"{markdown.label!r} and {pdf.label!r} are not a parser pair: they disagree on "
            f"question set ({markdown.question_set_digest} vs {pdf.question_set_digest})."
        )
        raise ValueError(message)
    if markdown.query_pipeline != pdf.query_pipeline:
        message = (
            f"{markdown.label!r} and {pdf.label!r} are not a parser pair: they disagree on "
            f"query pipeline ({markdown.query_pipeline} vs {pdf.query_pipeline})."
        )
        raise ValueError(message)
    if markdown.query_identity != pdf.query_identity:
        message = (
            f"{markdown.label!r} and {pdf.label!r} are not a parser pair: they disagree on "
            f"query pipeline identity ({markdown.query_identity} vs {pdf.query_identity})."
        )
        raise ValueError(message)
    if markdown.model_versions != pdf.model_versions:
        message = (
            f"{markdown.label!r} and {pdf.label!r} are not a parser pair: they disagree on "
            f"model versions ({markdown.model_versions} vs {pdf.model_versions})."
        )
        raise ValueError(message)
    if markdown.corpus_digest == pdf.corpus_digest:
        message = (
            f"{markdown.label!r} and {pdf.label!r} are not a parser pair: they are the same "
            f"corpus ({markdown.corpus_digest})."
        )
        raise ValueError(message)


class PairRow(BaseModel):
    """One arm, repetition and metric, paired question by question: PDF minus markdown."""

    model_config = ConfigDict(frozen=True)

    arm: str
    repetition: int
    metric: str
    markdown: float
    pdf: float
    difference: PairedDifference
    markdown_corpus: str
    pdf_corpus: str


class Measurement(BaseModel):
    """What `measure` writes and `table` reads, so the committed table regenerates from it alone."""

    model_config = ConfigDict(frozen=True)

    markdown_quotes: QuoteSurvival
    pdf_quotes: QuoteSurvival
    pairs: tuple[PairRow, ...]


def _side(record: RunRecord, corpus: str) -> CorpusSide:
    experiment = record.experiment
    rung = record.query_rung
    if experiment is None or record.question_set_digest is None or not isinstance(rung, QueryRung):
        message = "a parser-tax record comes from `weft eval experiment` over a question set"
        raise ValueError(message)
    return CorpusSide(
        label=f"{experiment.arm} r{experiment.repetition} on {corpus}",
        corpus_digest=record.corpus.digest,
        question_set_digest=record.question_set_digest,
        query_pipeline=rung.name,
        query_identity=rung.identity,
        model_versions=dict(record.model_versions),
    )


def _records(runs: Path) -> dict[tuple[str, int], RunRecord]:
    """Every run record under `runs`, keyed by `(arm, repetition)` — repair **R38.19**: a second
    record for one key is refused rather than silently overwriting the first, naming both files.
    """
    found: dict[tuple[str, int], RunRecord] = {}
    sources: dict[tuple[str, int], Path] = {}
    for path in sorted(runs.glob("*.json")):
        record = load_run_record(path)
        if record.experiment is None:
            continue
        key = (record.experiment.arm, record.experiment.repetition)
        if key in found:
            message = (
                f"two records for arm {key[0]!r} repetition {key[1]} under {runs}: "
                f"{sources[key].name} and {path.name}"
            )
            raise ValueError(message)
        found[key] = record
        sources[key] = path
    return found


def _mean(record: RunRecord, metric: str) -> float:
    result = record.metrics.get(metric)
    if not isinstance(result, Produced):
        message = f"{metric} did not aggregate in a parser-tax record"
        raise ValueError(message)
    return result.value.mean


def pairs(markdown_runs: Path, pdf_runs: Path) -> tuple[PairRow, ...]:
    """Each arm and repetition both corpora ran, paired question by question, PDF minus markdown.

    Repair **R38.19**: a repetition either side ran alone used to be silently dropped from
    pairing rather than refused, so a missing arm's cost never reached the table. Both sides are
    required to hold exactly the same set of `(arm, repetition)` keys before anything is paired.
    """
    markdown, pdf = _records(markdown_runs), _records(pdf_runs)
    for key in sorted(set(markdown) ^ set(pdf)):
        side = "markdown" if key in markdown else "pdf"
        missing = "pdf" if key in markdown else "markdown"
        message = (
            f"arm {key[0]!r} repetition {key[1]} ran on {side} but not on {missing}: the two "
            f"corpora must have run exactly the same arms and repetitions to be paired"
        )
        raise ValueError(message)
    rows: list[PairRow] = []
    for key in sorted(markdown):
        left, right = markdown[key], pdf[key]
        require_parser_pair(_side(left, "markdown"), _side(right, "pdf"))
        differences = paired_differences(left, right)
        rows.extend(
            PairRow(
                arm=key[0],
                repetition=key[1],
                metric=metric,
                markdown=_mean(left, metric),
                pdf=_mean(right, metric),
                difference=differences[metric],
                markdown_corpus=left.corpus.digest,
                pdf_corpus=right.corpus.digest,
            )
            for metric in _METRICS
            if metric in differences
        )
    return tuple(rows)


def stored_chunks(dsn: str) -> dict[str, tuple[str, ...]]:
    """Every stored node's text, keyed by the file stem of each source it names."""
    chunks: dict[str, list[str]] = {}
    with psycopg.connect(dsn, autocommit=True) as conn, conn.cursor() as cursor:
        cursor.execute("SELECT source, content FROM weft_nodes, unnest(sources) AS source")
        for source, content in cursor:
            chunks.setdefault(Path(str(source)).stem, []).append(str(content))
    return {document: tuple(texts) for document, texts in chunks.items()}


def table(measured: Measurement) -> str:
    """The committed table, from the measurement alone.

    Repair **R38.19**, `R38.16`'s rule: a table states the population it is over — so it names
    the two corpora it measured, read off the rows' own `markdown_corpus`/`pdf_corpus` rather
    than trusted from outside the measurement. Rows that disagree about which corpora were
    measured are refused rather than reported as one population.
    """
    corpora = {(row.markdown_corpus, row.pdf_corpus) for row in measured.pairs}
    if len(corpora) > 1:
        message = f"pairs disagree about which corpora were measured: {sorted(corpora)}"
        raise ValueError(message)
    lines = [
        "# The parser tax — Open RAGBench dev split, markdown rendering against raw PDFs",
        "",
        "Generated by `scripts/parser_tax.py table`; edit the script, not this file.",
        "",
        "| dev quotes whole in one stored chunk | markdown | pdf |",
        "|---|---|---|",
        f"| of {measured.markdown_quotes.total} | {measured.markdown_quotes.whole} "
        f"| {measured.pdf_quotes.whole} |",
        "",
    ]
    if corpora:
        markdown_corpus, pdf_corpus = next(iter(corpora))
        lines.append(f"markdown corpus: {markdown_corpus}")
        lines.append(f"pdf corpus: {pdf_corpus}")
        lines.append("")
    lines += [
        "| arm | rep | metric | markdown | pdf | pdf − markdown [95% CI] | n | differing |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for row in measured.pairs:
        d = row.difference
        lines.append(
            f"| {row.arm} | {row.repetition} | {row.metric} | {row.markdown:.3f} | {row.pdf:.3f} "
            f"| {d.mean:+.3f} [{d.low:+.3f}, {d.high:+.3f}] | {d.n} | {d.differing} |"
        )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="What reading the raw PDFs costs — ledger 38.8.")
    commands = parser.add_subparsers(dest="action", required=True)
    measure = commands.add_parser("measure", help="records and stored chunks to one JSON")
    measure.add_argument("--questions", type=Path, required=True)
    measure.add_argument("--markdown-runs", type=Path, required=True)
    measure.add_argument("--pdf-runs", type=Path, required=True)
    measure.add_argument("--markdown-dsn", required=True)
    measure.add_argument("--pdf-dsn", required=True)
    measure.add_argument("--out", type=Path, required=True)
    render = commands.add_parser("table", help="the measurement JSON to a markdown table")
    render.add_argument("measurement", type=Path)
    render.add_argument("--out", type=Path, required=True)
    arguments = parser.parse_args(argv)

    if arguments.action == "measure":
        questions = read_question_set(arguments.questions).questions
        measured = Measurement(
            markdown_quotes=quote_survival(questions, stored_chunks(arguments.markdown_dsn)),
            pdf_quotes=quote_survival(questions, stored_chunks(arguments.pdf_dsn)),
            pairs=pairs(arguments.markdown_runs, arguments.pdf_runs),
        )
        arguments.out.write_text(measured.model_dump_json(indent=1) + "\n", encoding="utf-8")
    else:
        measured = Measurement.model_validate_json(arguments.measurement.read_text("utf-8"))
        arguments.out.write_text(table(measured), encoding="utf-8")
    print(f"wrote {arguments.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
