"""`weft eval experiment` — ledger task **44.55a**: arms that read a layer.

An arm naming `layers = [...]` has them built after the base index, once per (ingest pipeline,
corpus, layers), and every later arm naming the same set reuses them. Every arm shares one store
and `vector-top-k` filters no derived node out, so an arm is scored only when the store holds
exactly the layers it names, each built on every source — a layer left from another arm or an
earlier invocation, or one half built, would be read without the record saying so. The record
names the layers its arm read.

The layer build is `weft index --layers`'s, tested in `test_layers*.py`; here `run_index_for` is
doubled by what it leaves in the store — one source record per document, carrying one
`LayerRecord` per layer built — which is the part this command reads back.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pytest

from weft_chunk import Chunker
from weft_cli import eval_commands as eval_commands_module
from weft_cli import ingest as ingest_module
from weft_cli import layers as layers_module
from weft_cli import route_ask as route_ask_module
from weft_cli.eval_commands import LayersNotAsNamedError
from weft_cli.eval_experiment import (
    EvalExperimentArgs,
    EvalExperimentCommand,
    EvalExperimentCommandResult,
    EvalPlanArgs,
    EvalPlanCommand,
    EvalPlanCommandResult,
)
from weft_cli.eval_scoring import ScoredRun
from weft_cli.ingest import IndexResult, corpus_documents
from weft_cli.layers import UnknownLayerError
from weft_cli.render import render_outcome
from weft_embed import Embedder
from weft_engine.registry_bootstrap import Dependencies
from weft_engine.services import ServiceSelection
from weft_eval import Settings, register
from weft_eval.experiment import EXPERIMENT_SCHEMA_VERSION
from weft_eval.question_set import Question, question_set_digest
from weft_eval.run_record import NoQueryRung, PerQuestionScores, QuestionKey, load_run_record
from weft_extract import Extractor
from weft_extract.text import SourceRef
from weft_index import Expander
from weft_kernel.context import Context
from weft_kernel.discovery import PackRegistrar
from weft_kernel.payload import NothingToProduce, Outcome, Produced
from weft_kernel.pipeline import Pipeline, StageDeclaration
from weft_kernel.registry import Registry
from weft_kernel.runner import RunSummary
from weft_store import LayerRecord, LayerStatus, NodeStore, SourceRecord, SourceStatus
from weft_store.contract import target_name
from weft_store.memory import MemoryStore

_WHEN = datetime(2026, 9, 29, 12, 0, tzinfo=UTC)
_LAYER = "enrich-x"


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


def _catalogue() -> dict[str, Pipeline]:
    return {
        "index": Pipeline(
            name="index",
            stages=(
                StageDeclaration(id="extract", use="text"),
                StageDeclaration(id="chunk", use="fixed-size"),
                StageDeclaration(id="embed", use="hash"),
                StageDeclaration(id="store", use="pgvector"),
            ),
        ),
        _LAYER: Pipeline(name=_LAYER, stages=(StageDeclaration(id="expand", use="echo"),)),
    }


def _stub_catalogue(catalogue: dict[str, Pipeline]) -> Callable[..., dict[str, Pipeline]]:
    def _full_catalogue(
        *, directory: Path = Path("pipelines"), reports: Sequence[object] = ()
    ) -> dict[str, Pipeline]:
        del directory, reports
        return catalogue

    return _full_catalogue


def _ctx(store: MemoryStore) -> Context:
    def _store_factory(config: object) -> MemoryStore:
        del config
        return store

    registry = Registry()
    registrar = PackRegistrar(registry, distribution="weft-eval")
    register(registrar, Settings())
    registrar.commit()
    registry.add(Extractor, "text", _PassThroughStage, distribution="weft-extract")
    registry.add(Chunker, "fixed-size", _PassThroughStage, distribution="weft-chunk")
    registry.add(Embedder, "hash", _PassThroughStage, distribution="weft-embed")
    registry.add(Expander, "echo", _PassThroughStage, distribution="weft-index")
    registry.add(NodeStore, "pgvector", _store_factory, distribution="weft-store")
    ctx = Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")
    ctx.services.add(
        Dependencies,
        Dependencies(registry=registry, reports=(), services=ServiceSelection(store="pgvector")),
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
relevant_documents = ["two.txt"]
"""


def _arm(name: str, extra: str = "") -> str:
    return f'\n[[arm]]\nname = "{name}"\npipeline = "index"\n{extra}'


def _layered(name: str) -> str:
    return _arm(name, f'layers = ["{_LAYER}"]\n')


def _experiment(root: Path, arms: str, *, repeats: int = 2) -> Path:
    """An experiment over a two-document corpus, so a layer can be built on one of two."""
    project = root / "project"
    (project / "corpus").mkdir(parents=True, exist_ok=True)
    (project / "corpus" / "one.txt").write_text("hello weft", encoding="utf-8")
    (project / "corpus" / "two.txt").write_text("hello warp", encoding="utf-8")
    (project / "questions.toml").write_text(_QUESTIONS, encoding="utf-8")
    path = project / "experiment.toml"
    path.write_text(
        f"[experiment]\nschema = {EXPERIMENT_SCHEMA_VERSION}\n"
        f'name = "layered"\nquestions = "questions.toml"\ncorpus = "corpus"\n'
        f'repeats = {repeats}\ntop_k = 5\nmetrics = ["precision@5"]\n'
        "minimum_detectable_effect = 0.05\n" + arms,
        encoding="utf-8",
    )
    return path


def _record(ref: SourceRef, layers: tuple[LayerRecord, ...]) -> SourceRecord:
    return SourceRecord(
        id=ref.source_id,
        uri=ref.uri,
        content_hash=ref.content_hash,
        indexed_at=_WHEN,
        pipeline="index",
        status=SourceStatus.ACTIVE,
        layers=layers,
    )


def _layer(name: str, status: LayerStatus) -> LayerRecord:
    return LayerRecord(name=name, pipeline_identity="x", status=status, attempts=1, at=_WHEN)


async def _record_layers(
    store: MemoryStore, ref: SourceRef, names: Sequence[str], status: LayerStatus
) -> None:
    existing = await store.get_source(ref.source_id)
    kept = existing.layers if existing is not None else ()
    kept_names = {layer.name for layer in kept}
    built = tuple(_layer(name, status) for name in names if name not in kept_names)
    await store.put_source(_record(ref, kept + built))


def _layering_index(
    calls: list[dict[str, Any]], store: MemoryStore, *, failing: frozenset[str] = frozenset()
) -> Callable[..., Any]:
    """`run_index_for`'s effect on the store: each layer named is recorded on every source.

    A source whose file name is in `failing` records the layer `FAILED` rather than `ACTIVE`, as
    a layer batch that raised does. Layers already recorded on a source are kept, as an
    unchanged source's are under `reprocess=False`.
    """

    async def _index(deps: Dependencies, directory: Path, **kwargs: Any) -> IndexResult:
        calls.append(kwargs)
        resolved, _specs, refs = corpus_documents(
            directory, pipeline=str(kwargs["pipeline"]), registry=deps.registry, reports=()
        )
        target = kwargs.get("target")
        written = store if target is None else await store.bind_target(target_name(target))
        for ref in refs:
            status = LayerStatus.FAILED if ref.path.name in failing else LayerStatus.ACTIVE
            await _record_layers(written, ref, kwargs.get("layers", ()), status)
        return IndexResult(
            summary=RunSummary(),
            stored_count=len(refs),
            resolved_pipeline=resolved,
            document_ids=tuple(str(ref.source_id) for ref in refs),
            content_hashes=tuple(ref.content_hash for ref in refs),
        )

    return _index


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
    for module in (ingest_module, route_ask_module, layers_module):
        monkeypatch.setattr(module, "full_catalogue", _stub_catalogue(_catalogue()))


async def test_a_layer_is_built_once_after_the_base_and_each_record_names_what_its_arm_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    store = MemoryStore()
    path = _experiment(tmp_path, _arm("dense") + _layered("raptor") + _layered("raptor-again"))
    indexed: list[dict[str, Any]] = []
    scored: list[dict[str, object]] = []
    monkeypatch.setattr(eval_commands_module, "run_index_for", _layering_index(indexed, store))
    monkeypatch.setattr(eval_commands_module, "score_pipeline", _scoring_stub(scored))

    # Act
    outcome = await EvalExperimentCommand().run(EvalExperimentArgs(path=str(path)), _ctx(store))

    # Assert
    assert isinstance(outcome, Produced)
    assert [tuple(call.get("layers", ())) for call in indexed] == [(), (_LAYER,)]
    assert all(call["reprocess"] is False for call in indexed)
    targets = {call["target"] for call in indexed} | {call["target"] for call in scored}
    assert len(targets) == 1
    assert None not in targets
    result = cast("EvalExperimentCommandResult", outcome.value)
    read: dict[str, set[tuple[str, ...]]] = {}
    for run in result.runs:
        record = load_run_record(path.with_suffix("") / "runs" / f"{run.run_id}.json")
        assert record.experiment is not None
        read.setdefault(run.arm, set()).add(record.experiment.layers)
    assert read == {"dense": {()}, "raptor": {(_LAYER,)}, "raptor-again": {(_LAYER,)}}


async def test_an_unknown_layer_is_refused_before_anything_is_indexed_or_scored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A misnamed layer on the last arm must not cost every arm before it."""
    # Arrange
    store = MemoryStore()
    path = _experiment(tmp_path, _arm("dense") + _arm("raptor", 'layers = ["enrich-missing"]\n'))
    indexed: list[dict[str, Any]] = []
    scored: list[dict[str, object]] = []
    monkeypatch.setattr(eval_commands_module, "run_index_for", _layering_index(indexed, store))
    monkeypatch.setattr(eval_commands_module, "score_pipeline", _scoring_stub(scored))

    # Act
    with pytest.raises(UnknownLayerError) as caught:
        await EvalExperimentCommand().run(EvalExperimentArgs(path=str(path)), _ctx(store))

    # Assert
    assert _LAYER in caught.value.valid_options
    assert indexed == []
    assert scored == []


async def test_a_layer_already_in_the_store_that_an_arm_does_not_name_is_refused_unscored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A completed invocation leaves its layer behind; a fresh one would read it silently."""
    # Arrange — an earlier experiment built the layer into this pipeline's target.
    store = MemoryStore()
    earlier = _experiment(tmp_path, _arm("dense") + _layered("raptor"))
    monkeypatch.setattr(eval_commands_module, "run_index_for", _layering_index([], store))
    monkeypatch.setattr(eval_commands_module, "score_pipeline", _scoring_stub([]))
    await EvalExperimentCommand().run(EvalExperimentArgs(path=str(earlier)), _ctx(store))
    path = earlier.with_name("unlayered.toml")
    path.write_text(
        earlier.read_text(encoding="utf-8").split("\n[[arm]]")[0] + _arm("dense") + _arm("other"),
        encoding="utf-8",
    )
    scored: list[dict[str, object]] = []
    monkeypatch.setattr(eval_commands_module, "score_pipeline", _scoring_stub(scored))

    # Act
    with pytest.raises(LayersNotAsNamedError) as caught:
        await EvalExperimentCommand().run(EvalExperimentArgs(path=str(path)), _ctx(store))

    # Assert
    assert caught.value.arm == "dense"
    assert caught.value.unnamed == (_LAYER,)
    assert "does not name" in str(caught.value)
    assert scored == []


async def test_a_named_layer_built_on_only_part_of_the_corpus_is_refused_unscored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    store = MemoryStore()
    path = _experiment(tmp_path, _arm("dense") + _layered("raptor"), repeats=2)
    scored: list[dict[str, object]] = []
    indexed: list[dict[str, Any]] = []
    monkeypatch.setattr(
        eval_commands_module,
        "run_index_for",
        _layering_index(indexed, store, failing=frozenset({"two.txt"})),
    )
    monkeypatch.setattr(eval_commands_module, "score_pipeline", _scoring_stub(scored))

    # Act
    with pytest.raises(LayersNotAsNamedError) as caught:
        await EvalExperimentCommand().run(EvalExperimentArgs(path=str(path)), _ctx(store))

    # Assert
    assert caught.value.arm == "raptor"
    assert caught.value.unbuilt == (_LAYER,)
    assert "built on 1 of 2 source(s)" in str(caught.value)
    assert f"--layers {_LAYER} --layers-only --retry-failed" in str(caught.value)
    assert f"--target {indexed[-1]['target']} " in str(caught.value), (
        "the remedy must reach the arm's target"
    )
    assert len(scored) == 2, "only the dense arm's two repetitions were scored"


async def test_the_plan_states_the_layers_each_arm_reads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    store = MemoryStore()
    path = _experiment(tmp_path, _arm("dense") + _layered("raptor"))
    indexed: list[dict[str, Any]] = []
    monkeypatch.setattr(eval_commands_module, "run_index_for", _layering_index(indexed, store))

    # Act
    outcome = await EvalPlanCommand().run(EvalPlanArgs(path=str(path)), _ctx(store))

    # Assert
    assert isinstance(outcome, Produced)
    plan = cast("EvalPlanCommandResult", outcome.value)
    assert [(arm.arm, arm.layers) for arm in plan.arms] == [("dense", ()), ("raptor", (_LAYER,))]
    lines = (render_outcome(outcome).stdout or "").splitlines()
    raptor_line = next(line for line in lines if line.strip().startswith("raptor:"))
    dense_line = next(line for line in lines if line.strip().startswith("dense:"))
    assert f"layers {_LAYER}" in raptor_line
    assert "layers" not in dense_line
    assert indexed == [], "a plan indexes nothing"
