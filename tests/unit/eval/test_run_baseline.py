"""Unit tests for `eval/run_baseline.py` — the bookkeeping a measured number rests on.

Mirrors `eval/run_baseline.py`. The measurement itself is not simulated here: it needs a corpus,
a container and a vendor API, and pretending to it with fakes would test the fakes. What is
covered is everything that decides *what a written run means* — corpus identity, the resolution
of a retrieved passage back to a corpus document, the interval an aggregate records, and the two
refusals that stop an unusable file being written at all.
"""

from pathlib import Path

import pytest
from fetch_corpus import Document, Tier
from metrics import Excluded, ExclusionKind, MetricRecord
from run_baseline import (
    BaselineError,
    BaselineRun,
    CorpusRecord,
    DistributionRecord,
    StageRecord,
    aggregate,
    corpus_id,
    hits_of,
    main,
    parse_tiers,
    staged_path,
)

from weft_cli.ask import AskHit, AskResult


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


def _run(**overrides: object) -> BaselineRun:
    """A written run with one metric, as `BaselineRun` would be built from a real pass."""
    fields: dict[str, object] = {
        "recorded_at": "2026-08-17T12:00:00+00:00",
        "corpus": CorpusRecord(
            name="mrmr-v1", corpus_id="a" * 64, tiers=("fetch",), documents=("doc-a",)
        ),
        "reproducible": True,
        "questions": ("q001",),
        "repeats": 2,
        "retrieval_depth": 10,
        "pipeline": (StageRecord(stage="embed", plugin="openai"),),
        "pipeline_sha256": "b" * 64,
        "models": {"embed": "openai:text-embedding-3-small"},
        "distributions": (DistributionRecord(name="weft-cli", version="0.1.0", status="active"),),
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
    return BaselineRun.model_validate(fields | overrides)


def test_corpus_identity_follows_the_bytes_and_not_the_layout() -> None:
    # V3 fails a claim measured "against a baseline from a different corpus", so corpus identity
    # has to be a fact two machines compute the same way: a digest over each document's id and
    # its own digest, order-independent, and changing the moment any document does.
    # Arrange
    first = _document("doc-a", sha256="1" * 64)
    second = _document("doc-b", sha256="2" * 64)
    moved = _document("doc-b", sha256="3" * 64)

    # Act
    one_way = corpus_id([first, second])
    other_way = corpus_id([second, first])
    after = corpus_id([first, moved])

    # Assert
    assert one_way == other_way
    assert one_way != after


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
        _run(
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
    run = _run(
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
    assert run.metric("quote-recall@10") is not None
    assert run.metric("document-recall@10") is None
