"""Unit tests for `eval/run_baseline.py` — the bookkeeping a measured number rests on.

Mirrors `eval/run_baseline.py`. The measurement itself is not simulated here: it needs a corpus,
a container and a vendor API, and pretending to it with fakes would test the fakes. What is
covered is everything that decides *what a written run means* — the resolution of a retrieved
passage back to a corpus document, the interval an aggregate records, and the two refusals that
stop an unusable file being written at all. `corpus_identity`'s own digest property is
`weft_eval.run_record`'s to test, not retested here — this file tests what this module does with
the `RunRecord` that function's caller builds.
"""

from pathlib import Path

import pytest
from fetch_corpus import Document, Tier
from metrics import Excluded, ExclusionKind, MetricRecord
from run_baseline import (
    BaselineError,
    BaselineReport,
    aggregate,
    hits_of,
    main,
    parse_tiers,
    selected_documents,
    staged_path,
)

from weft_cli.ask import AskHit, AskResult
from weft_eval.run_record import CorpusIdentity, RunRecord
from weft_kernel.resolution import ResolvedPipeline, ResolvedStage


def _document(identifier: str, *, sha256: str, suffix: str = ".pdf") -> Document:
    return Document(
        id=identifier,
        path=Path(f"corpus/arxiv/{identifier}{suffix}"),
        fmt=suffix.lstrip("."),
        language="en",
        sha256=sha256,
        tier=Tier.FETCH,
        source="https://example.invalid/paper",
    )


def _record() -> RunRecord:
    return RunRecord(
        recorded_at="2026-08-20T12:00:00+00:00",
        resolved_pipeline=ResolvedPipeline(
            name="baseline",
            stages=(
                ResolvedStage(
                    id="embed",
                    contract="Embedder",
                    use="openai",
                    distribution="weft-openai",
                    provenance="baseline",
                ),
            ),
        ),
        corpus=CorpusIdentity(name="pl-wiki-v1", digest="a" * 64),
        model_versions={"embed": "openai:text-embedding-3-small"},
        active_distributions=("weft-cli", "weft-eval"),
    )


def _report(**overrides: object) -> BaselineReport:
    """A written run with one metric, as `BaselineReport` would be built from a real pass."""
    fields: dict[str, object] = {
        "recorded_at": "2026-08-20T12:00:00+00:00",
        "corpus_name": "pl-wiki-v1",
        "tiers": ("fetch",),
        "extractor": "text",
        "documents": ("doc-a",),
        "reproducible": True,
        "record": _record(),
        "questions": ("q001",),
        "repeats": 2,
        "retrieval_depth": 10,
        "wall_clock_seconds": 1.0,
        "metrics": (
            MetricRecord(
                metric="quote-recall@10",
                depth=10,
                values=(0.4, 0.6),
                mean=0.5,
                low=0.4,
                high=0.6,
                n_scored=2,
                n_excluded=0,
            ),
        ),
        "excluded": (),
    }
    return BaselineReport.model_validate(fields | overrides)


def test_selected_documents_refuses_an_extractor_this_harness_does_not_know() -> None:
    # A resolved pipeline names exactly one Extractor stage (task 4.0); a baseline over a format
    # this harness has no suffix mapping for would either silently pick nothing or silently pick
    # everything, and `01` requirement 5 rules both out.
    # Act / Assert
    with pytest.raises(BaselineError, match="text.*pdf-text|pdf-text.*text"):
        selected_documents((Tier.FETCH,), extractor="docling")


def test_a_retrieved_passage_is_resolved_to_the_document_that_was_staged(tmp_path: Path) -> None:
    # The `SourceId` a store returns is the file's resolved path, and this run staged that file
    # itself — so the mapping back to a manifest id is exact rather than a guess about names.
    # Arrange
    workdir = tmp_path
    document = _document("ax-1908.05376v1", sha256="4" * 64)
    known = {str(staged_path(document, workdir)): document.id}
    answer = AskResult(
        question="why?",
        top_k=2,
        hits=(
            AskHit(
                rank=1,
                node_id="node-1",
                score=0.9,
                sources=(str(staged_path(document, workdir)),),
                content="a passage",
            ),
            AskHit(
                rank=2,
                node_id="node-2",
                score=0.1,
                sources=("/somewhere/else/another-index.pdf",),
                content="a passage from an index this run did not write",
            ),
        ),
    )

    # Act
    hits = hits_of(answer, known=known)

    # Assert
    assert hits[0].documents == ("ax-1908.05376v1",)
    assert hits[1].documents == (), (
        "a source this run did not stage was attributed to a corpus document anyway, which "
        "would credit a question with retrieving a paper it never saw"
    )


def test_the_recorded_interval_is_the_one_the_repetitions_spanned() -> None:
    # The whole point of V3: "a later run reproduces the baseline when every metric falls inside
    # that recorded interval". Nobody chooses the bounds — they are min and max of what happened.
    # Arrange
    per_repetition = ({"quote-recall@5": 0.4}, {"quote-recall@5": 0.55}, {"quote-recall@5": 0.5})

    # Act
    (record,) = aggregate(per_repetition, excluded=(), depths=(5,), scored_counts=(90, 90, 90))

    # Assert
    assert (record.low, record.high) == (0.4, 0.55)
    assert record.mean == pytest.approx(0.48333333, abs=1e-6)
    assert record.depth == 5


def test_a_deterministic_pass_records_a_zero_width_interval_rather_than_room_to_move() -> None:
    # `docs/09-release.md` §4.3 names this outcome and calls it correct and strict: "a system
    # that is deterministic records a zero-width interval and admits no drift at all." A
    # harness that widened it "to be safe" would have chosen the tolerance after all.
    # Arrange
    per_repetition = ({"document-mrr@10": 0.75}, {"document-mrr@10": 0.75})

    # Act
    (record,) = aggregate(per_repetition, excluded=(), depths=(10,), scored_counts=(95, 95))

    # Assert
    assert (record.low, record.high) == (0.75, 0.75)
    assert record.outside(0.7500001)


def test_a_single_repetition_is_refused_before_anything_is_measured(tmp_path: Path) -> None:
    # V3's own failure clause, and the reason it is checked in `main` as well as in the model:
    # the refusal has to happen before a corpus is indexed and a vendor is billed, and it has to
    # say why rather than exiting on an argparse error nobody can act on.
    # Arrange
    out = tmp_path / "run.json"

    # Act
    code = main(["--repeats", "1", "--out", str(out)])

    # Assert
    assert code == 2
    assert not out.exists(), "a run that records no interval must leave no file behind"


def test_an_unknown_tier_names_the_ones_the_manifest_declares() -> None:
    # `01` requirement 5 — an unknown name fails loudly, listing the valid options — applied to
    # the one argument that silently changes what "reproducible" means.
    # Act / Assert
    with pytest.raises(BaselineError, match="fetch"):
        parse_tiers("fetch,operatr")


def test_a_run_whose_exclusion_count_no_reason_backs_is_refused() -> None:
    # V4: "aggregates exclude errored metrics and report how many were excluded". The count is
    # on the metric and the reasons are on the run, so this is what stops the two drifting —
    # the reference's aggregators reported means that had failures averaged into them and nothing
    # anywhere could tell.
    # Act / Assert
    with pytest.raises(ValueError, match="n_excluded"):
        _report(
            metrics=(
                MetricRecord(
                    metric="quote-recall@10",
                    depth=10,
                    values=(0.4, 0.6),
                    mean=0.5,
                    low=0.4,
                    high=0.6,
                    n_scored=2,
                    n_excluded=4,
                ),
            )
        )


def test_a_run_that_reports_no_exclusions_and_records_none_is_accepted() -> None:
    # The complement, so the refusal above is not passing for the wrong reason.
    # Act
    report = _report(
        excluded=(
            Excluded(
                question_id="q001",
                repetition=1,
                kind=ExclusionKind.NO_JUDGEMENT,
                detail="unanswerable",
            ),
        ),
        metrics=(
            MetricRecord(
                metric="quote-recall@10",
                depth=10,
                values=(0.4, 0.6),
                mean=0.5,
                low=0.4,
                high=0.6,
                n_scored=2,
                n_excluded=1,
            ),
        ),
    )

    # Assert
    assert report.metric("quote-recall@10") is not None
    assert report.metric("document-recall@10") is None
    assert report.record.corpus.name == "pl-wiki-v1"
