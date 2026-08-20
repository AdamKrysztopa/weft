"""Unit tests for `weft_cli.eval_commands`.

Mirrors `packages/weft-cli/src/weft_cli/eval_commands.py`. `EvalRunCommand` is exercised the
same way `test_ingest.py`'s own `pipeline=` tests are — a real `Registry` with fake
extract/chunk/embed/store stand-ins, a real document stubbed in for `weft_cli.ingest.
full_catalogue` — because the property under test is that this command actually reaches
`run_index` and persists what it returns, not a re-derivation of `run_index`'s own logic.
`EvalCompareCommand`/`TraceCommand` are exercised against real `RunRecord` files
`weft_eval.run_record.write_run_record` wrote directly, since what they read is a persisted
file, not a pipeline resolution.

Covers, per command: `EvalRunCommand` — the happy path (a persisted record round-trips), the
edge case (an empty corpus refuses rather than persisting a vacuous record), and the error case
(an unknown pipeline name, `weft_cli.pipeline_catalogue.UnknownPipelineNameError`, reused rather
than duplicated). `EvalCompareCommand` — the happy path (a pipeline-only difference diffs
cleanly) and the error case (a corpus mismatch refuses, naming why). `TraceCommand` — the happy
path and the error case (an unknown run id names every id that does exist).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import ClassVar

import pytest
from pydantic import BaseModel, ConfigDict

from weft_chunk import Chunker
from weft_cli import eval_commands as eval_commands_module
from weft_cli import ingest as ingest_module
from weft_cli.eval_commands import (
    EmptyCorpusError,
    EvalCompareArgs,
    EvalCompareCommand,
    EvalCompareCommandResult,
    EvalMetricsArgs,
    EvalMetricsCommand,
    EvalMetricsCommandResult,
    EvalRunArgs,
    EvalRunCommand,
    EvalRunCommandResult,
    IncomparableRunsError,
    TraceArgs,
    TraceCommand,
    TraceCommandResult,
    UnknownRunIdError,
)
from weft_cli.pipeline_catalogue import UnknownPipelineNameError
from weft_cli.registry_bootstrap import Dependencies
from weft_cli.services import ServiceSelection
from weft_embed import Embedder
from weft_eval.aggregate import MetricAggregate
from weft_eval.contract import GenerationMetric
from weft_eval.offline import MetricNeedsCredentialsError, UnknownMetricNameError
from weft_eval.run_record import CorpusIdentity, NotAggregated, build_run_record, write_run_record
from weft_extract import Extractor
from weft_kernel.context import Context
from weft_kernel.discovery import PackReport, PackStatus
from weft_kernel.payload import Node, NothingToProduce, Outcome, Produced
from weft_kernel.pipeline import Pipeline, StageDeclaration
from weft_kernel.registry import Registry
from weft_kernel.resolution import ResolvedPipeline, ResolvedStage
from weft_store import NodeStore


class _PassThroughStage:
    """`test_ingest.py`'s own stand-in, restated here rather than imported across test files —
    `test_ff11_pipeline_integrity.py`'s precedent for why a test tier's own doubles are not
    shared modules.
    """

    extensions: tuple[str, ...] = (".txt",)
    destroys: tuple[type, ...] = ()

    def __init__(self, config: object) -> None:
        del config

    async def run(self, payload: Sequence[object], ctx: Context) -> Outcome[Sequence[object]]:
        del ctx
        if not payload:
            return NothingToProduce(reason="nothing to pass through")
        return Produced(value=payload)


class _FakeStore:
    def __init__(self, config: object) -> None:
        del config
        self.added: list[Node] = []

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        del ctx
        self.added.extend(payload)
        return Produced(value=payload)

    async def add(self, nodes: Sequence[Node]) -> None:
        self.added.extend(nodes)

    async def flush(self) -> None:
        return

    async def count(self) -> int:
        return len(self.added)


def _registry_with_fakes() -> Registry:
    registry = Registry()
    registry.add(Extractor, "text", _PassThroughStage, distribution="weft-extract")
    registry.add(Chunker, "fixed-size", _PassThroughStage, distribution="weft-chunk")
    registry.add(Embedder, "hash", _PassThroughStage, distribution="weft-embed")
    registry.add(NodeStore, "pgvector", _FakeStore, distribution="weft-store")
    return registry


def _document(name: str) -> Pipeline:
    return Pipeline(
        name=name,
        stages=(
            StageDeclaration(id="extract", use="text"),
            StageDeclaration(id="chunk", use="fixed-size"),
            StageDeclaration(id="embed", use="hash"),
            StageDeclaration(id="store", use="pgvector"),
        ),
    )


def _stub_catalogue(catalogue: dict[str, Pipeline]) -> Callable[..., dict[str, Pipeline]]:
    def _full_catalogue(
        *, directory: Path = Path("pipelines"), reports: Sequence[object] = ()
    ) -> dict[str, Pipeline]:
        del directory, reports
        return catalogue

    return _full_catalogue


def _ctx(deps: Dependencies) -> Context:
    ctx = Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")
    ctx.services.add(Dependencies, deps)
    return ctx


def _deps(reports: tuple[PackReport, ...] = ()) -> Dependencies:
    return Dependencies(
        registry=_registry_with_fakes(), reports=reports, services=ServiceSelection()
    )


class _FakeEmbedderModelConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    model: str = "text-embedding-3-small"


class _FakeEmbedderWithModel:
    """A stand-in whose `config_model` carries a `model` field — task 4.7's `model_versions`."""

    config_model: ClassVar[type[_FakeEmbedderModelConfig]] = _FakeEmbedderModelConfig

    def __init__(self, config: _FakeEmbedderModelConfig) -> None:
        del config

    async def run(self, payload: Sequence[object], ctx: Context) -> Outcome[Sequence[object]]:
        del ctx
        return Produced(value=payload)


def _registry_with_a_modelled_embedder() -> Registry:
    registry = _registry_with_fakes()
    registry.add(Embedder, "fake-openai", _FakeEmbedderWithModel, distribution="test")
    return registry


def _document_with_a_modelled_embedder(name: str) -> Pipeline:
    return Pipeline(
        name=name,
        stages=(
            StageDeclaration(id="extract", use="text"),
            StageDeclaration(id="chunk", use="fixed-size"),
            StageDeclaration(id="embed", use="fake-openai"),
            StageDeclaration(id="store", use="pgvector"),
        ),
    )


class _FakeSafeMetric:
    runs_in_gate: ClassVar[bool] = True

    def __init__(self, config: object = None) -> None:
        del config


class _FakeUnsafeMetric:
    runs_in_gate: ClassVar[bool] = False
    gate_unsafe_reason: ClassVar[str] = "needs a real judge model, not a fake"

    def __init__(self, config: object = None) -> None:
        del config


def _deps_with_fake_metrics() -> Dependencies:
    registry = _registry_with_fakes()
    registry.add(GenerationMetric, "safe-metric", _FakeSafeMetric, distribution="test")
    registry.add(GenerationMetric, "unsafe-metric", _FakeUnsafeMetric, distribution="test")
    return Dependencies(registry=registry, reports=(), services=ServiceSelection())


@pytest.fixture(autouse=True)
def in_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


# --- EvalRunCommand -----------------------------------------------------------------------


async def test_eval_run_persists_a_run_record_that_round_trips(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    (tmp_path / "one.txt").write_text("hello weft")
    monkeypatch.setattr(
        ingest_module, "full_catalogue", _stub_catalogue({"index": _document("index")})
    )
    reports = (PackReport(distribution="weft-eval", status=PackStatus.ACTIVE, contributed=1),)
    deps = _deps(reports)

    # Act
    outcome = await EvalRunCommand().run(
        EvalRunArgs(path=str(tmp_path), pipeline="index"), _ctx(deps)
    )

    # Assert
    assert isinstance(outcome, Produced)
    result = outcome.value
    assert isinstance(result, EvalRunCommandResult)
    assert result.summary.produced == 1
    assert result.record.resolved_pipeline.name == "index"
    assert result.record.corpus.name == str(tmp_path)
    assert result.record.active_distributions == ("weft-eval",)
    # Task 4.7 — measured, real, never negative; the fakes here carry no `model` field, so
    # `model_versions` is honestly empty rather than a guess.
    assert result.wall_clock_seconds >= 0.0
    assert result.record.model_versions == {}
    written = tmp_path / "runs" / f"{result.run_id}.json"
    assert written.is_file()
    from weft_eval.run_record import load_run_record

    assert load_run_record(written) == result.record


async def test_eval_run_refuses_an_empty_corpus(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange — a real, genuinely empty directory: nothing on disk for any extractor to claim.
    monkeypatch.setattr(
        ingest_module, "full_catalogue", _stub_catalogue({"index": _document("index")})
    )
    deps = _deps()

    # Act / Assert
    with pytest.raises(EmptyCorpusError) as excinfo:
        await EvalRunCommand().run(EvalRunArgs(path=str(tmp_path), pipeline="index"), _ctx(deps))
    assert excinfo.value.path == str(tmp_path)
    assert excinfo.value.pipeline == "index"
    assert not (tmp_path / "runs").exists()


async def test_eval_run_refuses_an_unknown_pipeline_name(tmp_path: Path) -> None:
    # Arrange — `full_catalogue` is real here (no stub), and simply holds nothing.
    (tmp_path / "one.txt").write_text("hello weft")
    deps = _deps()

    # Act / Assert
    with pytest.raises(UnknownPipelineNameError):
        await EvalRunCommand().run(EvalRunArgs(path=str(tmp_path), pipeline="ghost"), _ctx(deps))


async def test_eval_run_pins_the_model_a_stages_own_config_names(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange — task 4.7: `model_versions` is derived from the resolved pipeline's own stages,
    # never from `[services]` (Q3 still holds for a named pipeline).
    (tmp_path / "one.txt").write_text("hello weft")
    monkeypatch.setattr(
        ingest_module,
        "full_catalogue",
        _stub_catalogue({"index": _document_with_a_modelled_embedder("index")}),
    )
    deps = Dependencies(
        registry=_registry_with_a_modelled_embedder(), reports=(), services=ServiceSelection()
    )

    # Act
    outcome = await EvalRunCommand().run(
        EvalRunArgs(path=str(tmp_path), pipeline="index"), _ctx(deps)
    )

    # Assert
    assert isinstance(outcome, Produced)
    result = outcome.value
    assert isinstance(result, EvalRunCommandResult)
    assert result.record.model_versions == {"embed": "fake-openai:text-embedding-3-small"}


async def test_eval_run_with_questions_folds_the_scored_metrics_into_the_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange — task 4.9: `--questions` is this module's own trigger to call
    # `weft_cli.eval_scoring.score_pipeline`; `score_pipeline`'s own retrieval-and-scoring
    # logic is `test_eval_scoring.py`'s job, so here it is a fake collaborator, exercising only
    # this command's own wiring: load the file, call scoring, fold the result into the record.
    (tmp_path / "one.txt").write_text("hello weft")
    monkeypatch.setattr(
        ingest_module, "full_catalogue", _stub_catalogue({"index": _document("index")})
    )
    questions_path = tmp_path / "questions.json"
    questions_path.write_text('[{"query": "q", "relevant_documents": ["doc-a"]}]')

    async def _fake_score_pipeline(**kwargs: object) -> dict[str, Outcome[MetricAggregate]]:
        del kwargs
        return {
            "precision@5": Produced(
                value=MetricAggregate(
                    reported_name="precision@5",
                    mean=0.8,
                    n=1,
                    stdev=None,
                    excluded=0,
                    nothing_to_produce=0,
                )
            )
        }

    monkeypatch.setattr(eval_commands_module, "score_pipeline", _fake_score_pipeline)
    deps = _deps()

    # Act
    outcome = await EvalRunCommand().run(
        EvalRunArgs(path=str(tmp_path), pipeline="index", questions=str(questions_path)),
        _ctx(deps),
    )

    # Assert
    assert isinstance(outcome, Produced)
    result = outcome.value
    assert isinstance(result, EvalRunCommandResult)
    assert isinstance(result.record.metrics["precision@5"], Produced)
    assert result.record.metrics["precision@5"].value.mean == 0.8


# --- EvalCompareCommand --------------------------------------------------------------------


def _write_record(
    directory: Path,
    run_id: str,
    *,
    pipeline_name: str,
    corpus_name: str,
    stages: tuple[ResolvedStage, ...] = (),
    metrics: dict[str, Outcome[MetricAggregate]] | None = None,
) -> None:
    record = build_run_record(
        recorded_at="2026-08-20T00:00:00+00:00",
        resolved_pipeline=ResolvedPipeline(name=pipeline_name, stages=stages),
        corpus=CorpusIdentity(name=corpus_name, digest="a" * 64),
        metrics=metrics or {},
    )
    write_run_record(record, directory / "runs" / f"{run_id}.json")


async def test_eval_compare_diffs_two_runs_whose_pipeline_alone_differs(tmp_path: Path) -> None:
    # Arrange — a derived pipeline that inserts one stage, `02` §3's own worked example, so the
    # diff is a real structural change rather than two same-shaped pipelines under two names.

    added = ResolvedStage(
        id="keywords",
        contract="Enhancer",
        use="keybert",
        distribution="weft-kw",
        provenance="specific",
    )
    _write_record(tmp_path, "run-a", pipeline_name="base", corpus_name="corpus")
    _write_record(
        tmp_path, "run-b", pipeline_name="specific", corpus_name="corpus", stages=(added,)
    )
    deps = _deps()

    # Act
    outcome = await EvalCompareCommand().run(EvalCompareArgs(a="run-a", b="run-b"), _ctx(deps))

    # Assert
    assert isinstance(outcome, Produced)
    result = outcome.value
    assert isinstance(result, EvalCompareCommandResult)
    assert result.corpus_matches
    assert result.model_versions_match
    assert result.active_distributions_match
    assert not result.pipeline_diff.identical
    assert result.pipeline_diff.a_name == "base"
    assert result.pipeline_diff.b_name == "specific"


async def test_eval_compare_reports_metrics_both_runs_scored_and_names_the_one_run_a_missed(
    tmp_path: Path,
) -> None:
    # Arrange — task 4.9: the comparison the tool generates itself, not only that the
    # pipelines differ. `run-a` never scored `recall@5`; `run-b` did — that must show up as
    # "not measured," never silence and never a fabricated number for `run-a`'s own side.
    scored_a = Produced(
        value=MetricAggregate(
            reported_name="precision@5",
            mean=0.4,
            n=2,
            stdev=0.1,
            excluded=0,
            nothing_to_produce=0,
        )
    )
    scored_b = Produced(
        value=MetricAggregate(
            reported_name="precision@5",
            mean=0.6,
            n=2,
            stdev=0.1,
            excluded=0,
            nothing_to_produce=0,
        )
    )
    recall_b = Produced(
        value=MetricAggregate(
            reported_name="recall@5", mean=0.7, n=2, stdev=0.0, excluded=0, nothing_to_produce=0
        )
    )
    _write_record(
        tmp_path,
        "run-a",
        pipeline_name="base",
        corpus_name="corpus",
        metrics={"precision@5": scored_a},
    )
    _write_record(
        tmp_path,
        "run-b",
        pipeline_name="base",
        corpus_name="corpus",
        metrics={"precision@5": scored_b, "recall@5": recall_b},
    )
    deps = _deps()

    # Act
    outcome = await EvalCompareCommand().run(EvalCompareArgs(a="run-a", b="run-b"), _ctx(deps))

    # Assert
    assert isinstance(outcome, Produced)
    result = outcome.value
    assert isinstance(result, EvalCompareCommandResult)
    assert result.metrics_comparison["precision@5"].a == scored_a
    assert result.metrics_comparison["precision@5"].b == scored_b
    assert isinstance(result.metrics_comparison["recall@5"].a, NotAggregated)
    assert result.metrics_comparison["recall@5"].b == recall_b


async def test_eval_compare_refuses_two_runs_from_a_different_corpus(tmp_path: Path) -> None:
    # Arrange
    _write_record(tmp_path, "run-a", pipeline_name="base", corpus_name="corpus-a")
    _write_record(tmp_path, "run-b", pipeline_name="base", corpus_name="corpus-b")
    deps = _deps()

    # Act / Assert
    with pytest.raises(IncomparableRunsError) as excinfo:
        await EvalCompareCommand().run(EvalCompareArgs(a="run-a", b="run-b"), _ctx(deps))
    assert excinfo.value.run_a == "run-a"
    assert excinfo.value.run_b == "run-b"
    assert any("corpus" in reason for reason in excinfo.value.reasons)


# --- TraceCommand ---------------------------------------------------------------------------


async def test_trace_prints_the_persisted_record(tmp_path: Path) -> None:
    # Arrange
    _write_record(tmp_path, "run-a", pipeline_name="base", corpus_name="corpus")
    deps = _deps()

    # Act
    outcome = await TraceCommand().run(TraceArgs(run_id="run-a"), _ctx(deps))

    # Assert
    assert isinstance(outcome, Produced)
    result = outcome.value
    assert isinstance(result, TraceCommandResult)
    assert result.run_id == "run-a"
    assert result.record.resolved_pipeline.name == "base"
    assert result.record.corpus.name == "corpus"


async def test_trace_refuses_an_unknown_run_id_naming_the_ones_that_exist(tmp_path: Path) -> None:
    # Arrange
    _write_record(tmp_path, "run-a", pipeline_name="base", corpus_name="corpus")
    deps = _deps()

    # Act / Assert
    with pytest.raises(UnknownRunIdError) as excinfo:
        await TraceCommand().run(TraceArgs(run_id="ghost"), _ctx(deps))
    assert excinfo.value.valid_options == ("run-a",)
    assert excinfo.value.run_id == "ghost"


# --- EvalMetricsCommand -----------------------------------------------------------------------


async def test_eval_metrics_lists_the_full_gate_subset() -> None:
    # Arrange
    deps = _deps_with_fake_metrics()

    # Act
    outcome = await EvalMetricsCommand().run(EvalMetricsArgs(), _ctx(deps))

    # Assert
    assert isinstance(outcome, Produced)
    result = outcome.value
    assert isinstance(result, EvalMetricsCommandResult)
    assert result.gate_safe == ("safe-metric",)
    assert result.gate_unsafe == ("unsafe-metric",)


async def test_eval_metrics_by_name_answers_a_gate_safe_metric() -> None:
    # Arrange
    deps = _deps_with_fake_metrics()

    # Act
    outcome = await EvalMetricsCommand().run(EvalMetricsArgs(name="safe-metric"), _ctx(deps))

    # Assert
    assert isinstance(outcome, Produced)
    result = outcome.value
    assert isinstance(result, EvalMetricsCommandResult)
    assert result.gate_safe == ("safe-metric",)
    assert result.gate_unsafe == ()


async def test_eval_metrics_refuses_a_metric_that_needs_credentials_naming_why() -> None:
    # Arrange — the metric exists, it simply cannot run here: never a degraded answer.
    deps = _deps_with_fake_metrics()

    # Act / Assert
    with pytest.raises(MetricNeedsCredentialsError) as excinfo:
        await EvalMetricsCommand().run(EvalMetricsArgs(name="unsafe-metric"), _ctx(deps))
    assert "unsafe-metric" in str(excinfo.value)
    assert "needs a real judge model" in str(excinfo.value)
    assert excinfo.value.metric == "unsafe-metric"


async def test_eval_metrics_refuses_an_unknown_name_listing_what_does_exist() -> None:
    # Arrange
    deps = _deps_with_fake_metrics()

    # Act / Assert
    with pytest.raises(UnknownMetricNameError) as excinfo:
        await EvalMetricsCommand().run(EvalMetricsArgs(name="does-not-exist"), _ctx(deps))
    assert "safe-metric" in excinfo.value.valid_options
    assert "unsafe-metric" in excinfo.value.valid_options
