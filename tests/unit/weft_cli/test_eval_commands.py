"""Unit tests for `weft_cli.eval_commands`.

Mirrors `packages/weft-rag/src/weft_cli/eval_commands.py`. `EvalRunCommand` is exercised the
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

Task **8.8** adds `weft eval compare --baseline <pipeline>`, the falsification instrument, and
the tests for it at the foot of this file. What is exercised here is the *seam*, never the
arithmetic — which repetitions the command selects out of `runs/`, that it refuses a baseline
name nothing under `runs/` ran, that it refuses a baseline measured against a different corpus,
and that omitting the flag invents no verdict at all. The rule itself, and every case where
there is nothing to judge, is `tests/unit/weft_eval/test_falsify.py`.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, ClassVar, cast

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
    NoBaselineRunsError,
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
from weft_eval.falsify import BaselineSpread, TooFewRepetitionsError, Verdict
from weft_eval.offline import MetricNeedsCredentialsError, UnknownMetricNameError
from weft_eval.run_record import (
    CorpusIdentity,
    NotAggregated,
    RunRecord,
    build_run_record,
    write_run_record,
)
from weft_extract import Extractor
from weft_kernel.context import Context
from weft_kernel.discovery import PackReport, PackStatus
from weft_kernel.payload import Node, NothingToProduce, Outcome, Produced
from weft_kernel.pipeline import Pipeline, StageDeclaration
from weft_kernel.registry import Registry
from weft_kernel.resolution import ResolvedPipeline, ResolvedStage
from weft_llm.roles import LLMRoles, RoleMapping
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
    reports = (
        PackReport(pack="eval", distribution="weft-eval", status=PackStatus.ACTIVE, contributed=1),
    )
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


async def test_eval_run_persists_both_durations_and_reports_one_of_them_from_the_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Task 10.22 — the timing already existed and did not survive persistence.

    `eval_commands` has wrapped `run_index` in `time.monotonic()` since task 4.7 and shown the
    result to the operator as `wall_clock_seconds`. That number never reached the `RunRecord`, so
    a cost question could be answered about the run in front of you and never about a run recorded
    last week — which is the question G15's *Remove* face actually turns on. The scoring half was
    not measured at all.

    **And the operator-facing field must read from the record rather than call the clock a second
    time.** Two measurements of one quantity is `L7.4`'s shape: they agree until they do not, and
    nothing says which is authoritative. This test pins them to one source by asserting identity,
    not approximate equality.
    """
    # Arrange
    (tmp_path / "one.txt").write_text("hello weft")
    monkeypatch.setattr(
        ingest_module, "full_catalogue", _stub_catalogue({"index": _document("index")})
    )
    deps = _deps(
        (
            PackReport(
                pack="eval", distribution="weft-eval", status=PackStatus.ACTIVE, contributed=1
            ),
        )
    )

    # Act
    outcome = await EvalRunCommand().run(
        EvalRunArgs(path=str(tmp_path), pipeline="index"), _ctx(deps)
    )

    # Assert
    assert isinstance(outcome, Produced)
    result = outcome.value
    assert isinstance(result, EvalRunCommandResult)
    durations = result.record.durations
    assert durations is not None, (
        "the persisted record carries no duration, so the cost of this run is knowable only while "
        "the command's own result is still in hand"
    )
    assert durations.ingest_seconds > 0.0, "ingest was measured but recorded as no time at all"
    assert durations.query_seconds >= 0.0
    assert result.wall_clock_seconds == durations.ingest_seconds, (
        "the operator-facing number and the recorded one must be the same measurement, not two. "
        f"Got {result.wall_clock_seconds!r} against {durations.ingest_seconds!r}"
    )
    # And it survives the file, which is the whole point of putting it on the record.
    from weft_eval.run_record import load_run_record

    reloaded = load_run_record(tmp_path / "runs" / f"{result.run_id}.json")
    assert reloaded.durations == durations


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


def _aggregate(name: str, mean: float) -> Produced[MetricAggregate]:
    """One scored metric for one run — task 8.8's tests care about `mean` and nothing else."""
    return Produced(
        value=MetricAggregate(
            reported_name=name, mean=mean, n=4, stdev=0.0, excluded=0, nothing_to_produce=0
        )
    )


async def test_eval_compare_without_a_baseline_reports_no_verdict_at_all(tmp_path: Path) -> None:
    # Arrange — task 8.8 must not start answering a question nobody asked: with no baseline
    # there is no measured variability, so there is nothing a verdict could be derived from.
    _write_record(
        tmp_path,
        "run-a",
        pipeline_name="vector-top-k",
        corpus_name="corpus",
        metrics={"precision@5": _aggregate("precision@5", 0.40)},
    )
    _write_record(
        tmp_path,
        "run-b",
        pipeline_name="hybrid",
        corpus_name="corpus",
        metrics={"precision@5": _aggregate("precision@5", 0.90)},
    )

    # Act
    outcome = await EvalCompareCommand().run(EvalCompareArgs(a="run-a", b="run-b"), _ctx(_deps()))

    # Assert
    assert isinstance(outcome, Produced)
    result = outcome.value
    assert isinstance(result, EvalCompareCommandResult)
    assert result.falsification is None
    assert result.baseline_runs == ()


async def test_eval_compare_judges_a_difference_against_the_named_baselines_repetitions(
    tmp_path: Path,
) -> None:
    # Arrange — the baseline pipeline ran three times and varied by 0.02 doing nothing; the
    # two rungs then differ by 0.16, which is more than that. Both baseline repetitions and
    # the rungs are ordinary persisted runs under `runs/`, since that is all `weft eval run`
    # ever writes — no second file format the CLI would have to be taught to read.
    for run_id, mean in (("base-1", 0.40), ("base-2", 0.42), ("base-3", 0.41)):
        _write_record(
            tmp_path,
            run_id,
            pipeline_name="vector-top-k",
            corpus_name="corpus",
            metrics={"precision@5": _aggregate("precision@5", mean)},
        )
    _write_record(
        tmp_path,
        "run-a",
        pipeline_name="vector-top-k",
        corpus_name="corpus",
        metrics={"precision@5": _aggregate("precision@5", 0.41)},
    )
    _write_record(
        tmp_path,
        "run-b",
        pipeline_name="hybrid",
        corpus_name="corpus",
        metrics={"precision@5": _aggregate("precision@5", 0.57)},
    )

    # Act
    outcome = await EvalCompareCommand().run(
        EvalCompareArgs(a="run-a", b="run-b", baseline="vector-top-k"), _ctx(_deps())
    )

    # Assert
    assert isinstance(outcome, Produced)
    result = outcome.value
    assert isinstance(result, EvalCompareCommandResult)
    assert result.baseline_pipeline == "vector-top-k"
    # Every persisted run of that pipeline is a repetition, and only those.
    assert set(result.baseline_runs) == {"base-1", "base-2", "base-3"}
    assert result.falsification is not None
    judgement = result.falsification["precision@5"]
    assert judgement.verdict is Verdict.OUTSIDE_BASELINE_SPREAD
    assert isinstance(judgement.spread, BaselineSpread)
    assert (judgement.spread.low, judgement.spread.high) == (0.40, 0.42)


async def test_eval_compare_refuses_a_baseline_pipeline_nothing_under_runs_ran(
    tmp_path: Path,
) -> None:
    # Arrange — `01` requirement 5 applied to a baseline name exactly as `UnknownRunIdError`
    # already applies it to a run id: name what does exist rather than answering emptily.
    _write_record(tmp_path, "run-a", pipeline_name="vector-top-k", corpus_name="corpus")
    _write_record(tmp_path, "run-b", pipeline_name="hybrid", corpus_name="corpus")

    # Act / Assert
    with pytest.raises(NoBaselineRunsError) as caught:
        await EvalCompareCommand().run(
            EvalCompareArgs(a="run-a", b="run-b", baseline="raptor-and-leaves-rrf"), _ctx(_deps())
        )
    assert "raptor-and-leaves-rrf" in str(caught.value)
    assert set(caught.value.valid_options) == {"vector-top-k", "hybrid"}


async def test_eval_compare_refuses_a_baseline_run_once(tmp_path: Path) -> None:
    # Arrange — V3's own failure clause reaching the CLI: one repetition records no interval,
    # so there is nothing to judge against and the command says so instead of judging.
    _write_record(
        tmp_path,
        "base-1",
        pipeline_name="vector-top-k",
        corpus_name="corpus",
        metrics={"precision@5": _aggregate("precision@5", 0.40)},
    )
    _write_record(tmp_path, "run-a", pipeline_name="rerank", corpus_name="corpus")
    _write_record(tmp_path, "run-b", pipeline_name="hybrid", corpus_name="corpus")

    # Act / Assert
    with pytest.raises(TooFewRepetitionsError):
        await EvalCompareCommand().run(
            EvalCompareArgs(a="run-a", b="run-b", baseline="vector-top-k"), _ctx(_deps())
        )


async def test_eval_compare_refuses_a_baseline_measured_against_a_different_corpus(
    tmp_path: Path,
) -> None:
    # Arrange — V3's other failure clause. A baseline's spread is a measurement of *this*
    # system on *this* corpus; one taken elsewhere is not the variability of the thing being
    # judged, and a plausible number computed from it is the more dangerous outcome.
    for run_id in ("base-1", "base-2"):
        _write_record(
            tmp_path,
            run_id,
            pipeline_name="vector-top-k",
            corpus_name="some-other-corpus",
            metrics={"precision@5": _aggregate("precision@5", 0.40)},
        )
    _write_record(tmp_path, "run-a", pipeline_name="rerank", corpus_name="corpus")
    _write_record(tmp_path, "run-b", pipeline_name="hybrid", corpus_name="corpus")

    # Act / Assert
    with pytest.raises(IncomparableRunsError) as caught:
        await EvalCompareCommand().run(
            EvalCompareArgs(a="run-a", b="run-b", baseline="vector-top-k"), _ctx(_deps())
        )
    assert "corpus" in str(caught.value)


def _resolved_pipeline_with_a_model() -> ResolvedPipeline:
    """A resolved pipeline one of whose stages carries a `model` in its own config.

    Built rather than reused so this test's subject is exactly the two halves of the derivation:
    a stage that contributes a model version, and (once `R10.3` lands) a role that does. The
    stage's shape follows `_write_record`'s own `ResolvedStage` above.
    """
    return ResolvedPipeline(
        name="index-openai",
        stages=(
            ResolvedStage(
                id="embed",
                contract="Embedder",
                use="openai-embeddings",
                distribution="weft-rag",
                provenance="index-openai",
                config={"model": "text-embedding-3-small"},
            ),
        ),
    )


def _run_record_with(*, model_versions: dict[str, str]) -> RunRecord:
    """Two records that differ **only** in `model_versions` — same corpus, same pipeline.

    That is the dimension `R10.3` is about, and holding the other two fixed is what makes the
    assertion about this one: `_incomparable_reasons` reads three facts, and a fixture varying
    more than one of them would pass whatever the repair did (`docs/lessons.md` `L12.6`).
    """
    return build_run_record(
        recorded_at="2026-08-20T00:00:00+00:00",
        resolved_pipeline=ResolvedPipeline(name="index-openai", stages=()),
        corpus=CorpusIdentity(name="corpus", digest="a" * 64),
        model_versions=model_versions,
        metrics={},
    )


def test_model_versions_records_what_a_role_resolved_to_not_only_stage_config() -> None:
    """Carried repair **R10.3** (`docs/lessons.md` `L10.5`).

    `_model_versions` reads each resolved stage's own `config` for a `model` field, generically,
    and that is right as far as it goes — `OpenAIEmbedderConfig.model` is pinned by it and
    `hash`/`pgvector` contribute nothing without a table anywhere naming which stages carry a
    model. **What it cannot see is a model named in `[llm.roles]`.** A summarising or judging
    model is chosen there, per *role*, and no stage's config mentions it — so two eval arms
    differing **only** by their summarising model produced byte-identical `model_versions`, and
    `_incomparable_reasons` compared them as if the only difference were the pipeline.

    That is the guard reading one fact and the run using another. `09` §4's V2 pins a comparison
    to *"a baseline from a different corpus, pipeline or model version"*; a role's model **is** a
    model version, and it was the one the guard was blind to.

    **Both sources, and they cannot collide.** A stage entry is keyed by the stage's own id; a
    role entry is keyed `role:<name>`, which no stage id can be — `weft_kernel.pipeline` refuses
    a `:` in a stage id except as a slot qualifier, and a qualifier's left side is a
    distribution. Asserted below rather than argued, because "these keys cannot collide" is the
    kind of claim that is true until somebody widens one of the two namespaces.
    """
    resolved = _resolved_pipeline_with_a_model()
    roles = LLMRoles(
        roles={
            "index": RoleMapping(provider="openai", model="gpt-4o-mini"),
            "generate": RoleMapping(provider="openai", model="gpt-4o"),
        }
    )

    # Act
    versions = _private_member(eval_commands_module, "_model_versions")(resolved, roles=roles)

    # Assert — the stage half is unchanged, and the role half is new.
    assert versions["role:index"] == "openai:gpt-4o-mini"
    assert versions["role:generate"] == "openai:gpt-4o"
    assert any(not key.startswith("role:") for key in versions), (
        "the stage-config half of this derivation disappeared — `OpenAIEmbedderConfig.model` "
        "was pinned by it before this repair and must still be."
    )
    assert not {key for key in versions if key.startswith("role:")} & {
        stage.id for stage in resolved.stages
    }, "a role key collided with a stage id, so one reading is overwriting the other"


def test_two_arms_differing_only_by_a_roles_model_are_refused_as_incomparable() -> None:
    """The property `R10.3` states, at the seam that acts on it.

    Without this the repair is a field nothing reads — `L5.15`'s shape, and the reason
    `_incomparable_reasons` is driven here rather than `_model_versions` alone.
    """
    a = _run_record_with(model_versions={"role:index": "openai:gpt-4o-mini"})
    b = _run_record_with(model_versions={"role:index": "openai:gpt-4o"})

    # Act
    reasons = _private_member(eval_commands_module, "_incomparable_reasons")(a, b)

    # Assert
    assert reasons, (
        "two runs whose summarising model differs compared as identical, which is exactly the "
        "state this repair was filed about."
    )
    assert any("model" in reason for reason in reasons)


def _private_member(module: object, name: str) -> Any:
    """One private module member, by name — the idiom
    `tests/architecture/test_ff13_filter_op_dispatch_is_exhaustive.py` documents.

    Importing a `_`-prefixed name trips pyright's `reportPrivateUsage`; a `getattr` with a
    literal trips ruff's `B009`. Taking the name as a parameter is neither. The subject really is
    the private function: `_model_versions` is where carried repair `R10.3`'s derivation lives,
    and there is no public seam that answers the narrower question this test asks.
    """
    return getattr(module, name)


async def test_reuse_index_scores_against_what_is_already_stored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Carried repair **R10.4** (`docs/lessons.md` `L10.25`, and `L11.46` from the other end).

    `weft eval run` always indexes. Comparing two **query** rungs therefore means running it
    twice against the same corpus, and each run re-ingests — which is harmless for a
    deterministic ingest rung and not at all harmless for one that calls a model. `L11.46`
    measured it: four runs against a model-calling rung took a corpus from **23 nodes to 42**,
    and what read as a baseline *interval* was extraction drift rather than retrieval noise. So
    the comparison spanned a store that grew between its arms, which makes every multi-arm number
    in Phase 10's baselines a measurement of a moving corpus.

    `--reuse-index` is the answer: score the query rung against what is already stored. The
    ingest half does not run at all — asserted by a spy, because *not doing something* is the
    kind of claim that passes by accident.

    **The corpus identity still comes from the same derivation.** `corpus_identity` is a digest
    over the sorted source ids a run discovered on disk, so discovering them without ingesting
    yields the identical digest — which is exactly what makes two arms comparable rather than
    merely both present. Reading it out of the store instead would make the record depend on
    what a *previous* run happened to write.
    """
    (tmp_path / "one.txt").write_text("hello weft")
    (tmp_path / "two.txt").write_text("weft again")
    monkeypatch.setattr(
        ingest_module, "full_catalogue", _stub_catalogue({"index": _document("index")})
    )

    indexed: list[str] = []

    async def _spy(path: Path, **kwargs: object) -> object:
        indexed.append(str(path))
        raise AssertionError("run_index must not be called when --reuse-index is given")

    # Arrange — one ordinary run first, to have something to compare the digest against.
    baseline = await EvalRunCommand().run(
        EvalRunArgs(path=str(tmp_path), pipeline="index"), _ctx(_deps())
    )
    assert isinstance(baseline, Produced)

    # Act — the same directory, scored without ingesting.
    monkeypatch.setattr(eval_commands_module, "run_index", _spy)
    reused = await EvalRunCommand().run(
        EvalRunArgs(path=str(tmp_path), pipeline="index", reuse_index=True), _ctx(_deps())
    )

    # Assert
    assert indexed == [], "the ingest half ran; `--reuse-index` means it must not"
    assert isinstance(reused, Produced)
    assert _corpus_of(reused) == _corpus_of(baseline), (
        "the reused run recorded a different corpus digest from the run that indexed the same "
        "directory, so the two arms would compare as incomparable — the opposite of the repair."
    )


async def test_reuse_index_refuses_a_directory_with_nothing_to_score(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange — an empty directory has no source ids, so there is no corpus identity to record
    # and nothing for a query rung to retrieve. The ordinary path already refuses this with
    # `EmptyCorpusError`; the reuse path must refuse it too rather than writing a run record
    # whose digest is the hash of an empty list — a digest that would silently match every other
    # empty run.
    monkeypatch.setattr(
        ingest_module, "full_catalogue", _stub_catalogue({"index": _document("index")})
    )
    deps = _deps()

    with pytest.raises(EmptyCorpusError):
        await EvalRunCommand().run(
            EvalRunArgs(path=str(tmp_path), pipeline="index", reuse_index=True), _ctx(deps)
        )


def _corpus_of(outcome: object) -> str:
    """The corpus digest a completed  recorded — read back off the persisted
    record rather than off the command's own return value, because the record is what a later
     will actually read."""
    result = cast("Any", outcome).value
    digest: str = result.record.corpus.digest
    return digest
