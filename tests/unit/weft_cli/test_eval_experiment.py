"""`weft eval experiment <path>` — ledger task **38.0**.

One document, one verb: every arm runs every repetition, each writes one `RunRecord` carrying the
experiment's name, digest, invocation, arm and repetition, and an arm whose corpus, question set or
model versions differ from the others is refused before anything is indexed. Scoring goes through
`weft_cli.eval_commands`, the path `weft eval run` scores through, so there is one scoring path
and these tests stub it where `test_eval_commands.py` does; retrieval and scoring themselves are
`test_eval_scoring.py`'s. The doubles are `test_eval_commands.py`'s own, restated rather than
imported, that file's precedent.
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
from weft_cli import route_ask as route_ask_module
from weft_cli.eval_experiment import (
    EvalExperimentArgs,
    EvalExperimentCommand,
    EvalExperimentCommandResult,
    EvalPlanArgs,
    EvalPlanCommand,
    EvalPlanCommandResult,
    IncomparableArmsError,
    UnscorableArmError,
)
from weft_cli.eval_scoring import ScoredRun
from weft_cli.ingest import IndexResult, run_index_for
from weft_cli.pipeline_catalogue import UnknownPipelineNameError
from weft_cli.render import render_outcome
from weft_command.permission import PermissionClass
from weft_embed import Embedder
from weft_engine.registry_bootstrap import Dependencies
from weft_engine.services import ServiceSelection
from weft_eval import Settings, register
from weft_eval.experiment import EXPERIMENT_SCHEMA_VERSION
from weft_eval.offline import UnknownMetricNameError
from weft_eval.question_set import Question, question_set_digest
from weft_eval.run_record import NoQueryRung, PerQuestionScores, QuestionKey, load_run_record
from weft_extract import Extractor
from weft_kernel.context import Context
from weft_kernel.discovery import PackRegistrar
from weft_kernel.payload import Node, NothingToProduce, Outcome, Produced
from weft_kernel.pipeline import Pipeline, StageDeclaration
from weft_kernel.registry import Registry
from weft_retrieve import ContextPacker
from weft_store import NodeStore


class _PassThroughStage:
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


class _FakeEmbedderModelConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    model: str = "text-embedding-3-small"


class _FakeEmbedderWithModel:
    config_model: ClassVar[type[_FakeEmbedderModelConfig]] = _FakeEmbedderModelConfig

    def __init__(self, config: _FakeEmbedderModelConfig) -> None:
        del config

    async def run(self, payload: Sequence[object], ctx: Context) -> Outcome[Sequence[object]]:
        del ctx
        return Produced(value=payload)


def _registry() -> Registry:
    registry = Registry()
    registrar = PackRegistrar(registry, distribution="weft-eval")
    register(registrar, Settings())
    registrar.commit()
    registry.add(Extractor, "text", _PassThroughStage, distribution="weft-extract")
    registry.add(Chunker, "fixed-size", _PassThroughStage, distribution="weft-chunk")
    registry.add(Embedder, "hash", _PassThroughStage, distribution="weft-embed")
    registry.add(Embedder, "fake-openai", _FakeEmbedderWithModel, distribution="test")
    registry.add(NodeStore, "pgvector", _FakeStore, distribution="weft-store")
    registry.add(ContextPacker, "repack", _PassThroughStage, distribution="weft-retrieve")
    return registry


def _document(name: str, *, embed: StageDeclaration | None = None) -> Pipeline:
    return Pipeline(
        name=name,
        stages=(
            StageDeclaration(id="extract", use="text"),
            StageDeclaration(id="chunk", use="fixed-size"),
            embed if embed is not None else StageDeclaration(id="embed", use="hash"),
            StageDeclaration(id="store", use="pgvector"),
        ),
    )


def _catalogue() -> dict[str, Pipeline]:
    return {
        "index": _document("index"),
        "index-other": _document("index-other"),
        "index-small-model": _document(
            "index-small-model", embed=StageDeclaration(id="embed", use="fake-openai")
        ),
        "index-large-model": _document(
            "index-large-model",
            embed=StageDeclaration(
                id="embed", use="fake-openai", config={"model": "text-embedding-3-large"}
            ),
        ),
    }


def _stub_catalogue(catalogue: dict[str, Pipeline]) -> Callable[..., dict[str, Pipeline]]:
    def _full_catalogue(
        *, directory: Path = Path("pipelines"), reports: Sequence[object] = ()
    ) -> dict[str, Pipeline]:
        del directory, reports
        return catalogue

    return _full_catalogue


def _ctx() -> Context:
    ctx = Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")
    ctx.services.add(
        Dependencies,
        Dependencies(registry=_registry(), reports=(), services=ServiceSelection()),
    )
    return ctx


_QUESTIONS = """[question_set]
schema = 2
absent = ["kind", "difficulty", "quote", "reference_answer", "notes"]
absent_reason = "an experiment fixture"
axes = []

[[question]]
id = "q-1"
text = "what is weft?"
language = "en"
relevant_documents = ["one.txt"]

[[question]]
id = "q-2"
text = "what is a warp?"
language = "en"
relevant_documents = ["one.txt"]
"""


def _arm(name: str, pipeline: str, extra: str = "") -> str:
    return f'\n[[arm]]\nname = "{name}"\npipeline = "{pipeline}"\n{extra}'


def _experiment(
    root: Path, arms: str, *, repeats: int = 2, metrics: str = '["precision@5"]', extra: str = ""
) -> Path:
    """An experiment whose corpus, questions and document sit under `root/project`."""
    project = root / "project"
    (project / "corpus").mkdir(parents=True, exist_ok=True)
    (project / "corpus" / "one.txt").write_text("hello weft", encoding="utf-8")
    (project / "questions.toml").write_text(_QUESTIONS, encoding="utf-8")
    path = project / "experiment.toml"
    path.write_text(
        f"[experiment]\nschema = {EXPERIMENT_SCHEMA_VERSION}\n"
        f'name = "fixture"\nquestions = "questions.toml"\ncorpus = "corpus"\n'
        f"repeats = {repeats}\ntop_k = 5\nmetrics = {metrics}\n"
        f"minimum_detectable_effect = 0.05\n{extra}" + arms,
        encoding="utf-8",
    )
    return path


def _scoring_stub(calls: list[dict[str, object]]) -> Callable[..., Any]:
    async def _fake(**kwargs: object) -> ScoredRun:
        calls.append(kwargs)
        questions = cast("tuple[Question, ...]", kwargs["questions"])
        return ScoredRun(
            metrics={},
            query_rung=NoQueryRung(reason="no query rung was named"),
            question_scores={
                "precision@5": PerQuestionScores(
                    keyed_by=QuestionKey.QUESTION_ID,
                    scores={question.id: Produced(value=1.0) for question in questions},
                )
            },
            question_set=question_set_digest(questions),
        )

    return _fake


@pytest.fixture(autouse=True)
def in_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    run_dir = tmp_path / "cwd"
    run_dir.mkdir()
    monkeypatch.chdir(run_dir)
    monkeypatch.setattr(ingest_module, "full_catalogue", _stub_catalogue(_catalogue()))
    monkeypatch.setattr(route_ask_module, "full_catalogue", _stub_catalogue(_query_catalogue()))


async def test_every_arm_runs_every_repetition_and_persists_one_record_each(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    path = _experiment(
        tmp_path,
        _arm("dense", "index") + _arm("rung", "index", 'query_pipeline = "some-rung"\n'),
        repeats=2,
    )
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(eval_commands_module, "score_pipeline", _scoring_stub(calls))

    # Act
    outcome = await EvalExperimentCommand().run(EvalExperimentArgs(path=str(path)), _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    result = cast("EvalExperimentCommandResult", outcome.value)
    assert result.name == "fixture"
    assert len(result.runs) == 4
    assert {(run.arm, run.repetition) for run in result.runs} == {
        ("dense", 1),
        ("dense", 2),
        ("rung", 1),
        ("rung", 2),
    }
    records = [load_run_record(Path("runs") / f"{run.run_id}.json") for run in result.runs]
    experiments = [record.experiment for record in records]
    assert all(experiment is not None for experiment in experiments)
    assert {experiment.digest for experiment in experiments if experiment} == {result.digest}
    assert {experiment.invocation for experiment in experiments if experiment} == {
        result.invocation
    }
    for run, record in zip(result.runs, records, strict=True):
        assert record.experiment is not None
        assert (record.experiment.arm, record.experiment.repetition) == (run.arm, run.repetition)
        assert record.question_scores is not None
    assert sorted(str(call["query_pipeline"]) for call in calls) == [
        "None",
        "None",
        "some-rung",
        "some-rung",
    ]


async def test_scoring_refuses_a_passage_from_outside_the_arms_corpus(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An arm sharing a store with anything else would score passages from documents the
    question set never judged, as misses, silently. The runner asks the scorer to refuse them."""
    # Arrange
    path = _experiment(tmp_path, _arm("a", "index") + _arm("b", "index-other"))
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(eval_commands_module, "score_pipeline", _scoring_stub(calls))

    # Act
    await EvalExperimentCommand().run(EvalExperimentArgs(path=str(path)), _ctx())

    # Assert
    assert calls
    assert all(call["refuse_foreign_documents"] is True for call in calls)


async def test_an_arm_naming_a_different_corpus_is_refused_by_the_digest_before_anything_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    path = _experiment(
        tmp_path,
        _arm("a", "index") + _arm("b", "index") + _arm("planted", "index", 'corpus = "other"\n'),
    )
    other = path.parent / "other"
    other.mkdir()
    (other / "one.txt").write_text("a different weft", encoding="utf-8")
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(eval_commands_module, "score_pipeline", _scoring_stub(calls))

    # Act
    with pytest.raises(IncomparableArmsError) as caught:
        await EvalExperimentCommand().run(EvalExperimentArgs(path=str(path)), _ctx())

    # Assert
    assert caught.value.arm == "planted"
    reasons = " ".join(caught.value.reasons)
    assert "corpus" in reasons
    assert "planted" in str(caught.value)
    assert calls == []
    assert not Path("runs").exists()


async def test_an_arm_scored_on_a_different_question_set_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    path = _experiment(
        tmp_path, _arm("a", "index") + _arm("b", "index", 'questions = "fewer.toml"\n')
    )
    fewer = _QUESTIONS[: _QUESTIONS.index('[[question]]\nid = "q-2"')]
    (path.parent / "fewer.toml").write_text(fewer, encoding="utf-8")
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(eval_commands_module, "score_pipeline", _scoring_stub(calls))

    # Act
    with pytest.raises(IncomparableArmsError) as caught:
        await EvalExperimentCommand().run(EvalExperimentArgs(path=str(path)), _ctx())

    # Assert
    assert caught.value.arm == "b"
    assert "question set" in " ".join(caught.value.reasons)
    assert calls == []


async def test_two_arms_naming_one_model_slot_at_two_versions_are_refused_naming_both(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    path = _experiment(
        tmp_path, _arm("small", "index-small-model") + _arm("large", "index-large-model")
    )
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(eval_commands_module, "score_pipeline", _scoring_stub(calls))

    # Act
    with pytest.raises(IncomparableArmsError) as caught:
        await EvalExperimentCommand().run(EvalExperimentArgs(path=str(path)), _ctx())

    # Assert
    reasons = " ".join(caught.value.reasons)
    assert "text-embedding-3-small" in reasons
    assert "text-embedding-3-large" in reasons
    assert calls == []


async def test_arms_that_use_different_models_in_different_slots_are_not_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A hybrid arm uses an embedder a lexical arm does not have. Model versions are refused only
    where two arms state the same slot at two versions — not where one arm has a slot the other
    lacks, which is most of what an experiment varies."""
    # Arrange
    path = _experiment(tmp_path, _arm("hash", "index") + _arm("modelled", "index-small-model"))
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(eval_commands_module, "score_pipeline", _scoring_stub(calls))

    # Act
    outcome = await EvalExperimentCommand().run(EvalExperimentArgs(path=str(path)), _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    assert len(calls) == 4


async def test_the_experiment_renders_its_digest_and_one_line_per_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    path = _experiment(tmp_path, _arm("a", "index") + _arm("b", "index-other"))
    monkeypatch.setattr(eval_commands_module, "score_pipeline", _scoring_stub([]))
    outcome = await EvalExperimentCommand().run(EvalExperimentArgs(path=str(path)), _ctx())
    assert isinstance(outcome, Produced)
    result = cast("EvalExperimentCommandResult", outcome.value)

    # Act
    rendered = render_outcome(outcome)

    # Assert
    stdout = rendered.stdout or ""
    assert result.digest[:12] in stdout
    for run in result.runs:
        assert f"{run.arm} r{run.repetition}: run {run.run_id}" in stdout


def test_the_command_writes_and_says_so() -> None:
    # Assert
    assert EvalExperimentCommand.permission_class is PermissionClass.WRITE
    assert EvalExperimentCommand.help


# --- Repair R38.0 — an arm that cannot be scored is refused before any arm writes a record.


def _query_catalogue() -> dict[str, Pipeline]:
    catalogue = _catalogue()
    catalogue["some-rung"] = Pipeline(
        name="some-rung", stages=(StageDeclaration(id="pack", use="repack"),)
    )
    catalogue["retrieval-ends-in-a-retriever"] = Pipeline(
        name="retrieval-ends-in-a-retriever",
        stages=(StageDeclaration(id="embed", use="hash"),),
    )
    return catalogue


async def test_an_arm_naming_an_unknown_query_pipeline_is_refused_before_any_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    monkeypatch.setattr(route_ask_module, "full_catalogue", _stub_catalogue(_catalogue()))
    path = _experiment(
        tmp_path, _arm("a", "index") + _arm("b", "index", 'query_pipeline = "no-such-rung"\n')
    )
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(eval_commands_module, "score_pipeline", _scoring_stub(calls))

    # Act
    with pytest.raises(UnknownPipelineNameError):
        await EvalExperimentCommand().run(EvalExperimentArgs(path=str(path)), _ctx())

    # Assert
    assert calls == []
    assert not Path("runs").exists()


async def test_an_arm_whose_query_pipeline_ends_in_neither_a_generator_nor_a_packer_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    monkeypatch.setattr(ingest_module, "full_catalogue", _stub_catalogue(_query_catalogue()))
    monkeypatch.setattr(route_ask_module, "full_catalogue", _stub_catalogue(_query_catalogue()))
    path = _experiment(
        tmp_path,
        _arm("a", "index")
        + _arm("b", "index", 'query_pipeline = "retrieval-ends-in-a-retriever"\n'),
    )
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(eval_commands_module, "score_pipeline", _scoring_stub(calls))

    # Act
    with pytest.raises(UnscorableArmError) as caught:
        await EvalExperimentCommand().run(EvalExperimentArgs(path=str(path)), _ctx())

    # Assert
    assert caught.value.arm == "b"
    assert "retrieval-ends-in-a-retriever" in str(caught.value)
    assert "Embedder" in str(caught.value)
    assert calls == []
    assert not Path("runs").exists()


# --- Repair R38.2 — one index per ingest pipeline and corpus, and no paid run on a name no run
# --- records.


def _counting_index(calls: list[dict[str, Any]]) -> Callable[..., Any]:
    async def _index(deps: Dependencies, directory: Path, **kwargs: Any) -> IndexResult:
        calls.append(kwargs)
        return await run_index_for(deps, directory, **kwargs)

    return _index


async def test_arms_sharing_an_ingest_pipeline_and_corpus_index_it_once_in_bounded_batches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Three arms naming one ingest pipeline over one corpus measure the same index; re-embedding
    it per arm paid for the corpus three times and ignored an index an operator had already
    built. The one index honours unchanged documents and the document's batch size."""
    # Arrange
    path = _experiment(
        tmp_path,
        _arm("a", "index") + _arm("b", "index", 'query_pipeline = "some-rung"\n'),
        extra="index_batch_size = 7\n",
    )
    indexed: list[dict[str, Any]] = []
    monkeypatch.setattr(eval_commands_module, "run_index_for", _counting_index(indexed))
    monkeypatch.setattr(eval_commands_module, "score_pipeline", _scoring_stub([]))

    # Act
    outcome = await EvalExperimentCommand().run(EvalExperimentArgs(path=str(path)), _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    assert len(indexed) == 1
    assert indexed[0]["reprocess"] is False
    assert indexed[0]["batch_size"] == 7


async def test_arms_naming_two_ingest_pipelines_index_each_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    path = _experiment(
        tmp_path, _arm("a", "index") + _arm("b", "index-other") + _arm("c", "index"), repeats=3
    )
    indexed: list[dict[str, Any]] = []
    monkeypatch.setattr(eval_commands_module, "run_index_for", _counting_index(indexed))
    monkeypatch.setattr(eval_commands_module, "score_pipeline", _scoring_stub([]))

    # Act
    await EvalExperimentCommand().run(EvalExperimentArgs(path=str(path)), _ctx())

    # Assert
    assert sorted(str(call["pipeline"]) for call in indexed) == ["index", "index-other"]


async def test_a_metric_no_run_would_record_is_refused_before_anything_is_indexed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`recal@5` and `recall@10` beside `top_k = 5` passed every refusal and let the paid run go
    ahead, to render `unjudgeable` naming nothing. The names a run records are asked of the
    registered metrics at the experiment's own depth, before any index."""
    # Arrange
    path = _experiment(tmp_path, _arm("a", "index") + _arm("b", "index"), metrics='["recal@5"]')
    indexed: list[dict[str, Any]] = []
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(eval_commands_module, "run_index_for", _counting_index(indexed))
    monkeypatch.setattr(eval_commands_module, "score_pipeline", _scoring_stub(calls))

    # Act
    with pytest.raises(UnknownMetricNameError) as caught:
        await EvalExperimentCommand().run(EvalExperimentArgs(path=str(path)), _ctx())

    # Assert
    assert caught.value.name == "recal@5"
    assert "recall@5" in caught.value.valid_options
    assert "recall@10" not in caught.value.valid_options
    assert indexed == []
    assert calls == []


async def test_a_record_names_its_corpus_as_the_document_wrote_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A resolved absolute path names a checkout, and two checkouts of one document would write
    corpus identities `weft eval compare` refuses to pair."""
    # Arrange
    path = _experiment(tmp_path, _arm("a", "index") + _arm("b", "index"))
    monkeypatch.setattr(eval_commands_module, "score_pipeline", _scoring_stub([]))

    # Act
    outcome = await EvalExperimentCommand().run(EvalExperimentArgs(path=str(path)), _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    result = cast("EvalExperimentCommandResult", outcome.value)
    names = {
        load_run_record(Path("runs") / f"{run.run_id}.json").corpus.name for run in result.runs
    }
    assert names == {"corpus"}


# --- Task 38.13 — each arm runs its own number of repetitions.


async def test_an_arm_declaring_one_repetition_is_run_once_while_the_others_repeat(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    path = _experiment(
        tmp_path,
        _arm("dense", "index", "repeats = 1\n")
        + _arm("rung", "index", 'query_pipeline = "some-rung"\n'),
        repeats=2,
    )
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(eval_commands_module, "score_pipeline", _scoring_stub(calls))

    # Act
    outcome = await EvalExperimentCommand().run(EvalExperimentArgs(path=str(path)), _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    result = cast("EvalExperimentCommandResult", outcome.value)
    assert {(run.arm, run.repetition) for run in result.runs} == {
        ("dense", 1),
        ("rung", 1),
        ("rung", 2),
    }


# --- Task 38.16 — an interrupted experiment resumes its invocation instead of starting over.


class _InterruptedError(Exception):
    """The run killed part-way: raised by the scoring stub once it has scored `survive` records."""


def _interrupting_stub(calls: list[dict[str, object]], *, survive: int) -> Callable[..., Any]:
    scoring = _scoring_stub(calls)

    async def _fake(**kwargs: object) -> ScoredRun:
        if len(calls) >= survive:
            raise _InterruptedError
        return await scoring(**kwargs)

    return _fake


async def test_rerunning_an_interrupted_experiment_scores_only_what_it_had_not_written(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`38.6` ran six times and three of the lost runs had already written valid records for
    whole arms, each re-paid from zero. A written record is never re-paid."""
    # Arrange — the first run is killed after writing two of its four records.
    path = _experiment(
        tmp_path,
        _arm("dense", "index") + _arm("rung", "index", 'query_pipeline = "some-rung"\n'),
        repeats=2,
    )
    first_calls: list[dict[str, object]] = []
    monkeypatch.setattr(
        eval_commands_module, "score_pipeline", _interrupting_stub(first_calls, survive=2)
    )
    with pytest.raises(_InterruptedError):
        await EvalExperimentCommand().run(EvalExperimentArgs(path=str(path)), _ctx())
    written = [load_run_record(record) for record in sorted(Path("runs").glob("*.json"))]
    assert len(written) == 2

    # Act — the same document, run again.
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(eval_commands_module, "score_pipeline", _scoring_stub(calls))
    outcome = await EvalExperimentCommand().run(EvalExperimentArgs(path=str(path)), _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    result = cast("EvalExperimentCommandResult", outcome.value)
    assert len(calls) == 2, "the two records the first run wrote were scored again"
    first_invocation = {record.experiment.invocation for record in written if record.experiment}
    assert first_invocation == {result.invocation}
    assert {(run.arm, run.repetition) for run in result.runs} == {
        ("dense", 1),
        ("dense", 2),
        ("rung", 1),
        ("rung", 2),
    }
    assert len(list(Path("runs").glob("*.json"))) == 4


async def test_rerunning_a_completed_experiment_starts_a_new_invocation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A deliberate re-run is still possible: only an incomplete invocation is continued."""
    # Arrange
    path = _experiment(
        tmp_path,
        _arm("dense", "index") + _arm("rung", "index", 'query_pipeline = "some-rung"\n'),
        repeats=2,
    )
    monkeypatch.setattr(eval_commands_module, "score_pipeline", _scoring_stub([]))
    first = await EvalExperimentCommand().run(EvalExperimentArgs(path=str(path)), _ctx())
    assert isinstance(first, Produced)

    # Act
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(eval_commands_module, "score_pipeline", _scoring_stub(calls))
    second = await EvalExperimentCommand().run(EvalExperimentArgs(path=str(path)), _ctx())

    # Assert
    assert isinstance(second, Produced)
    assert len(calls) == 4
    first_result = cast("EvalExperimentCommandResult", first.value)
    second_result = cast("EvalExperimentCommandResult", second.value)
    assert second_result.invocation != first_result.invocation


# --- Task 38.12 — an experiment states its size before anything is indexed or paid for.


async def test_the_plan_states_each_arms_size_and_runs_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`38.6`'s spend was approved twice and its size — 33,856 generation calls, four hours, two
    gigabytes a batch — was never stated. What the document and the corpus can answer exactly is
    answered here, before `--yes` and before any store is touched."""
    # Arrange
    path = _experiment(
        tmp_path,
        _arm("dense", "index", "repeats = 1\n")
        + _arm("rung", "index", 'query_pipeline = "some-rung"\n'),
        repeats=3,
    )
    scored: list[dict[str, object]] = []
    monkeypatch.setattr(eval_commands_module, "score_pipeline", _scoring_stub(scored))

    # Act
    outcome = await EvalPlanCommand().run(EvalPlanArgs(path=str(path)), _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    plan = cast("EvalPlanCommandResult", outcome.value)
    assert plan.name == "fixture"
    assert [(arm.arm, arm.repetitions, arm.questions, arm.executions) for arm in plan.arms] == [
        ("dense", 1, 2, 2),
        ("rung", 3, 2, 6),
    ]
    assert [(corpus.pipeline, corpus.documents) for corpus in plan.corpora] == [("index", 1)]
    assert scored == [], "a plan scores nothing"
    assert not list(Path("runs").glob("*.json")), "a plan writes no record"


def test_the_plan_command_only_reads() -> None:
    assert EvalPlanCommand.permission_class is PermissionClass.READ


async def test_an_answer_metric_a_generating_arm_records_passes_the_pre_flight(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ledger `32.14` scored a generating rung's answer; the pre-flight still asked only the
    retrieval metrics, so every document naming `token_recall` was refused before indexing —
    found by `32.10`'s free smoke run."""
    # Arrange
    path = _experiment(
        tmp_path, _arm("a", "index") + _arm("b", "index"), metrics='["recall@5", "token_recall"]'
    )
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(eval_commands_module, "score_pipeline", _scoring_stub(calls))

    # Act
    outcome = await EvalExperimentCommand().run(EvalExperimentArgs(path=str(path)), _ctx())

    # Assert
    assert isinstance(outcome, Produced)


async def test_a_refused_metric_name_lists_the_answer_metrics_beside_the_retrieval_ones(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange — the plugin name, not the name the metric reports.
    path = _experiment(
        tmp_path, _arm("a", "index") + _arm("b", "index"), metrics='["token-recall"]'
    )
    monkeypatch.setattr(eval_commands_module, "score_pipeline", _scoring_stub([]))

    # Act
    with pytest.raises(UnknownMetricNameError) as caught:
        await EvalExperimentCommand().run(EvalExperimentArgs(path=str(path)), _ctx())

    # Assert
    assert "token_recall" in caught.value.valid_options
    assert "rouge_l" in caught.value.valid_options
    assert "recall@5" in caught.value.valid_options
