"""`weft eval experiment` — ledger task **20.11**: arms indexed by different embedders coexist.

A target holds one embedder's vectors (`weft_engine.targets.claim_embedding_for_write`), so two
arms that embed differently cannot share one. Each distinct (index pipeline, corpus) indexes into
its own target, named from that pair and never from an arm, and every arm is scored against the
target its pipeline was indexed into. Layers grow inside their pipeline's target, as `44.55a` built
them. A captured pool names the target it was captured in, and a replay reads that target.

Indexing here is real — `TextExtractor`, `FixedSizeChunker`, `HashEmbedder` into one shared
`MemoryStore` — because the property is the store's own refusal; scoring is stubbed where
`test_eval_experiment.py` stubs it, and each stub records the target it was asked to read.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, cast

import pytest

from weft_chunk import Chunker
from weft_chunk.fixed_size import FixedSizeChunker
from weft_cli import eval_commands as eval_commands_module
from weft_cli import ingest as ingest_module
from weft_cli import route_ask as route_ask_module
from weft_cli.eval_experiment import (
    EvalExperimentArgs,
    EvalExperimentCommand,
    EvalExperimentCommandResult,
)
from weft_cli.eval_scoring import ScoredRun
from weft_cli.ingest import IndexResult, run_index_for
from weft_embed import Embedder
from weft_embed.hash_embedder import HashEmbedder, HashEmbedderConfig
from weft_engine.registry_bootstrap import Dependencies
from weft_engine.services import ServiceSelection
from weft_engine.targets import StoreHoldsNoTargetsError
from weft_eval import Settings, register
from weft_eval.experiment import EXPERIMENT_SCHEMA_VERSION
from weft_eval.pool import PoolChunk, load_pool_manifest
from weft_eval.question_set import Question, question_set_digest
from weft_eval.run_record import NoQueryRung, PerQuestionScores, QuestionKey, load_run_record
from weft_extract import Extractor
from weft_extract.text import TextExtractor
from weft_kernel.context import Context
from weft_kernel.discovery import PackRegistrar
from weft_kernel.payload import NothingToProduce, Outcome, Produced
from weft_kernel.pipeline import Pipeline, StageDeclaration
from weft_kernel.registry import Registry
from weft_kernel.resolution import ResolvedPipeline
from weft_retrieve import ContextPacker
from weft_store import NodeStore
from weft_store.contract import DEFAULT_TARGET, EmbeddingIdentity, target_name
from weft_store.memory import MemoryStore

_WIDE = 64
_NARROW = 32


class _PassThroughStage:
    def __init__(self, config: object) -> None:
        del config

    async def run(self, payload: Sequence[object], ctx: Context) -> Outcome[Sequence[object]]:
        del ctx
        if not payload:
            return NothingToProduce(reason="nothing to pass through")
        return Produced(value=payload)


class _UntargetedStore:
    """A store that keeps nodes and satisfies no `TargetHolding`."""

    def __init__(self, config: object) -> None:
        del config

    async def run(self, payload: Sequence[object], ctx: Context) -> Outcome[Sequence[object]]:
        del ctx
        return Produced(value=payload)

    async def add(self, nodes: Sequence[object]) -> None:
        del nodes

    async def flush(self) -> None:
        return

    async def count(self) -> int:
        return 0


def _index(name: str, dimension: int) -> Pipeline:
    return Pipeline(
        name=name,
        stages=(
            StageDeclaration(id="extract", use="text"),
            StageDeclaration(id="chunk", use="fixed-size"),
            StageDeclaration(id="embed", use="hash", config={"dimension": dimension}),
            StageDeclaration(id="store", use="memory"),
        ),
    )


def _catalogue() -> dict[str, Pipeline]:
    return {
        "index-wide": _index("index-wide", _WIDE),
        "index-narrow": _index("index-narrow", _NARROW),
        "some-rung": Pipeline(
            name="some-rung", stages=(StageDeclaration(id="pack", use="repack"),)
        ),
    }


def _stub_catalogue(catalogue: dict[str, Pipeline]) -> Callable[..., dict[str, Pipeline]]:
    def _full_catalogue(
        *, directory: Path = Path("pipelines"), reports: Sequence[object] = ()
    ) -> dict[str, Pipeline]:
        del directory, reports
        return catalogue

    return _full_catalogue


def _ctx(store: object) -> Context:
    def _store_factory(config: object) -> object:
        del config
        return store

    registry = Registry()
    registrar = PackRegistrar(registry, distribution="weft-eval")
    register(registrar, Settings())
    registrar.commit()
    registry.add(Extractor, "text", TextExtractor, distribution="weft-extract")
    registry.add(Chunker, "fixed-size", FixedSizeChunker, distribution="weft-chunk")
    registry.add(Embedder, "hash", HashEmbedder, distribution="weft-embed")
    registry.add(NodeStore, "memory", _store_factory, distribution="weft-store")
    registry.add(ContextPacker, "repack", _PassThroughStage, distribution="weft-retrieve")
    ctx = Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")
    ctx.services.add(
        Dependencies,
        Dependencies(registry=registry, reports=(), services=ServiceSelection(store="memory")),
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


def _arm(name: str, pipeline: str, extra: str = "") -> str:
    return f'\n[[arm]]\nname = "{name}"\npipeline = "{pipeline}"\nrepeats = 1\n{extra}'


def _experiment(root: Path, arms: str, *, document: str = "experiment.toml") -> Path:
    project = root / "project"
    (project / "corpus").mkdir(parents=True, exist_ok=True)
    (project / "corpus" / "one.txt").write_text("weft is the thread across", encoding="utf-8")
    (project / "corpus" / "two.txt").write_text("a warp runs lengthwise", encoding="utf-8")
    (project / "questions.toml").write_text(_QUESTIONS, encoding="utf-8")
    path = project / document
    path.write_text(
        f"[experiment]\nschema = {EXPERIMENT_SCHEMA_VERSION}\n"
        f'name = "{path.stem}"\nquestions = "questions.toml"\ncorpus = "corpus"\n'
        'repeats = 2\ntop_k = 5\nmetrics = ["precision@5"]\n'
        "minimum_detectable_effect = 0.05\n" + arms,
        encoding="utf-8",
    )
    return path


def _scored(questions: tuple[Question, ...], **extra: Any) -> ScoredRun:
    return ScoredRun(
        metrics={},
        query_rung=NoQueryRung(reason="stub"),
        question_scores={
            "precision@5": PerQuestionScores(
                keyed_by=QuestionKey.QUESTION_ID,
                scores={question.id: Produced(value=1.0) for question in questions},
            )
        },
        question_set=question_set_digest(questions),
        **extra,
    )


def _scoring_stub(calls: list[dict[str, Any]]) -> Callable[..., Any]:
    async def _fake(**kwargs: Any) -> ScoredRun:
        calls.append(kwargs)
        return _scored(cast("tuple[Question, ...]", kwargs["questions"]))

    return _fake


def _counting_index(calls: list[dict[str, Any]]) -> Callable[..., Any]:
    async def _index(deps: Dependencies, directory: Path, **kwargs: Any) -> IndexResult:
        calls.append(kwargs)
        return await run_index_for(deps, directory, **kwargs)

    return _index


async def _run(path: Path, store: object) -> EvalExperimentCommandResult:
    outcome = await EvalExperimentCommand().run(EvalExperimentArgs(path=str(path)), _ctx(store))
    assert isinstance(outcome, Produced)
    return cast("EvalExperimentCommandResult", outcome.value)


def _records(result: EvalExperimentCommandResult, document: Path) -> dict[str, Any]:
    runs = document.with_suffix("") / "runs"
    return {run.arm: load_run_record(runs / f"{run.run_id}.json") for run in result.runs}


async def _target_names(store: MemoryStore) -> set[str]:
    return {record.name for record in (await store.target_catalogue()).targets}


@pytest.fixture(autouse=True)
def in_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    run_dir = tmp_path / "cwd"
    run_dir.mkdir()
    monkeypatch.chdir(run_dir)
    monkeypatch.setattr(ingest_module, "full_catalogue", _stub_catalogue(_catalogue()))
    monkeypatch.setattr(route_ask_module, "full_catalogue", _stub_catalogue(_catalogue()))


async def test_two_arms_embedding_at_two_widths_run_in_one_invocation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Each arm is indexed into, and scored against, a target holding only its own embedder."""
    # Arrange
    store = MemoryStore()
    path = _experiment(tmp_path, _arm("wide", "index-wide") + _arm("narrow", "index-narrow"))
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(eval_commands_module, "score_pipeline", _scoring_stub(calls))

    # Act
    result = await _run(path, store)

    # Assert
    records = _records(result, path)
    widths = {"wide": _WIDE, "narrow": _NARROW}
    for arm, record in records.items():
        assert record.target_embedding is not None, arm
        assert record.target_embedding.width == widths[arm], arm
    assert records["wide"].target != records["narrow"].target
    assert {call["target"] for call in calls} == {
        records["wide"].target,
        records["narrow"].target,
    }
    catalogue = {
        record.name: record.embedding for record in (await store.target_catalogue()).targets
    }
    for record in records.values():
        assert catalogue[record.target] == record.target_embedding


async def test_each_record_names_the_embedder_its_questions_were_embedded_by(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ledger task 20.12: the record persists what scoring says embedded the questions."""
    # Arrange
    store = MemoryStore()
    path = _experiment(tmp_path, _arm("wide", "index-wide") + _arm("narrow", "index-narrow"))
    embedded_by = {
        width: EmbeddingIdentity(
            plugin="hash", distribution="weft-embed", model="hash", width=width
        )
        for width in (_WIDE, _NARROW)
    }

    async def _fake(**kwargs: Any) -> ScoredRun:
        stage = next(
            stage
            for stage in cast("ResolvedPipeline", kwargs["resolved_pipeline"]).stages
            if stage.id == "embed"
        )
        width = cast("HashEmbedderConfig", stage.config).dimension
        questions = cast("tuple[Question, ...]", kwargs["questions"])
        return _scored(questions, query_embedding=embedded_by[width])

    monkeypatch.setattr(eval_commands_module, "score_pipeline", _fake)

    # Act
    result = await _run(path, store)

    # Assert
    records = _records(result, path)
    assert records["wide"].query_embedding == embedded_by[_WIDE]
    assert records["narrow"].query_embedding == embedded_by[_NARROW]


async def test_two_arms_naming_one_pipeline_and_corpus_index_once_into_one_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    store = MemoryStore()
    path = _experiment(
        tmp_path,
        _arm("dense", "index-wide") + _arm("again", "index-wide") + _arm("narrow", "index-narrow"),
    )
    indexed: list[dict[str, Any]] = []
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(eval_commands_module, "run_index_for", _counting_index(indexed))
    monkeypatch.setattr(eval_commands_module, "score_pipeline", _scoring_stub(calls))

    # Act
    result = await _run(path, store)

    # Assert
    records = _records(result, path)
    assert records["dense"].target == records["again"].target
    assert sorted(str(call["pipeline"]) for call in indexed) == ["index-narrow", "index-wide"]
    assert len({call["target"] for call in indexed}) == 2
    assert len(await _target_names(store) - {DEFAULT_TARGET}) == 2


async def test_the_target_is_derived_from_the_pipeline_and_corpus_never_from_an_arm(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two documents naming their arms differently reach the same targets, and no arm's name.

    An arm name is the operator's, and an operator who could name targets could name two arms
    into one and get the refusal back.
    """
    # Arrange — arm names that are themselves valid target names, so using one would not raise.
    store = MemoryStore()
    monkeypatch.setattr(eval_commands_module, "score_pipeline", _scoring_stub([]))
    first = _experiment(tmp_path, _arm("alpha", "index-wide") + _arm("beta", "index-narrow"))
    second = _experiment(
        tmp_path,
        _arm("gamma", "index-wide") + _arm("delta", "index-narrow"),
        document="renamed.toml",
    )

    # Act
    by_first = _records(await _run(first, store), first)
    by_second = _records(await _run(second, store), second)

    # Assert
    assert by_first["alpha"].target == by_second["gamma"].target
    assert by_first["beta"].target == by_second["delta"].target
    for record in (*by_first.values(), *by_second.values()):
        assert record.target is not None
        assert target_name(record.target) == record.target
        assert record.target not in {"alpha", "beta", "gamma", "delta", DEFAULT_TARGET}


async def test_every_arm_is_scored_refusing_foreign_documents_in_its_own_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    store = MemoryStore()
    path = _experiment(tmp_path, _arm("wide", "index-wide") + _arm("narrow", "index-narrow"))
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(eval_commands_module, "score_pipeline", _scoring_stub(calls))

    # Act
    result = await _run(path, store)

    # Assert
    records = _records(result, path)
    by_target = {call["target"]: call for call in calls}
    for record in records.values():
        call = by_target[record.target]
        assert call["refuse_foreign_documents"] is True
        assert {Path(document).name for document in call["corpus_document_ids"]} == {
            "one.txt",
            "two.txt",
        }


class _InterruptedError(Exception):
    """The run killed part-way, once `survive` arms have been scored."""


async def test_a_resumed_invocation_scores_into_the_targets_the_first_one_made(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange — the first run indexes both arms and is killed scoring the second.
    store = MemoryStore()
    path = _experiment(tmp_path, _arm("wide", "index-wide") + _arm("narrow", "index-narrow"))
    first_calls: list[dict[str, Any]] = []
    scoring = _scoring_stub(first_calls)

    async def _interrupted(**kwargs: Any) -> ScoredRun:
        if first_calls:
            raise _InterruptedError
        return await scoring(**kwargs)

    monkeypatch.setattr(eval_commands_module, "score_pipeline", _interrupted)
    with pytest.raises(_InterruptedError):
        await _run(path, store)
    made = await _target_names(store)

    # Act
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(eval_commands_module, "score_pipeline", _scoring_stub(calls))
    result = await _run(path, store)

    # Assert
    assert [run.arm for run in result.runs] == ["wide", "narrow"]
    assert len(calls) == 1
    assert await _target_names(store) == made
    narrow = _records(result, path)["narrow"]
    assert narrow.target in made
    assert narrow.target_embedding is not None
    assert narrow.target_embedding.width == _NARROW


async def test_an_experiment_against_a_store_holding_no_targets_is_refused_writing_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    path = _experiment(tmp_path, _arm("wide", "index-wide") + _arm("narrow", "index-narrow"))
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(eval_commands_module, "score_pipeline", _scoring_stub(calls))

    # Act
    with pytest.raises(StoreHoldsNoTargetsError) as caught:
        await EvalExperimentCommand().run(
            EvalExperimentArgs(path=str(path)), _ctx(_UntargetedStore(None))
        )

    # Assert
    assert "TargetHolding" in str(caught.value)
    assert calls == []
    assert list((path.with_suffix("") / "runs").glob("*.json")) == []


# --- A pool names the target it was captured in, and a replay reads that target.

_ANCHORED_QUESTIONS = """[question_set]
schema = 2
absent = ["kind", "difficulty", "quote", "reference_answer", "notes"]
absent_reason = "an experiment fixture"
axes = []

[[question]]
id = "q-plain"
text = "what is weft?"
language = "en"
relevant_documents = ["one.txt"]
"""


def _capturing_stub(calls: list[dict[str, Any]]) -> Callable[..., Any]:
    async def _fake(**kwargs: Any) -> ScoredRun:
        calls.append(kwargs)
        questions = cast("tuple[Question, ...]", kwargs["questions"])
        capturing = bool(kwargs.get("capture_pool"))
        pools = {
            question.id: (
                PoolChunk(
                    node_id=f"{question.id}-n1",
                    document_id="one.txt",
                    content_sha256="a" * 64,
                    score=0.9,
                ),
            )
            for question in questions
        }
        return _scored(
            questions,
            question_pools=pools if capturing else None,
            store_rows=3 if capturing else None,
        )

    return _fake


def _replay(root: Path, manifest: Path) -> Path:
    replay = root / "project" / "replay.toml"
    replay.write_text(
        f"[experiment]\nschema = {EXPERIMENT_SCHEMA_VERSION}\n"
        'name = "replay"\nquestions = "questions.toml"\ncorpus = "corpus"\n'
        'repeats = 2\ntop_k = 5\nmetrics = ["precision@5"]\nminimum_detectable_effect = 0.05\n'
        + _arm("identity", "index-wide", f'query_pipeline = "some-rung"\npool = "{manifest}"\n')
        + _arm("again", "index-wide", f'query_pipeline = "some-rung"\npool = "{manifest}"\n'),
        encoding="utf-8",
    )
    return replay


async def test_a_captured_pool_names_its_target_and_every_replay_arm_reads_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    store = MemoryStore()
    path = _experiment(
        tmp_path,
        _arm("dense", "index-wide", 'query_pipeline = "some-rung"\ncapture_pool = true\n')
        + _arm("narrow", "index-narrow", 'query_pipeline = "some-rung"\n'),
    )
    (path.parent / "questions.toml").write_text(_ANCHORED_QUESTIONS, encoding="utf-8")
    monkeypatch.setattr(eval_commands_module, "score_pipeline", _capturing_stub([]))
    captured = _records(await _run(path, store), path)
    (manifest,) = (path.with_suffix("") / "runs" / "pools").glob("*.json")
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(eval_commands_module, "score_pipeline", _capturing_stub(calls))

    # Act
    replay = _replay(tmp_path, manifest.resolve())
    replayed = _records(await _run(replay, store), replay)

    # Assert
    loaded = load_pool_manifest(manifest).manifest
    assert loaded.target == captured["dense"].target
    assert {call["target"] for call in calls} == {captured["dense"].target}
    assert {record.target for record in replayed.values()} == {captured["dense"].target}


async def test_a_pool_captured_before_targets_were_recorded_replays_against_the_live_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange — the committed pools predate the field; their manifests carry no `target`.
    store = MemoryStore()
    path = _experiment(
        tmp_path,
        _arm("dense", "index-wide", 'query_pipeline = "some-rung"\ncapture_pool = true\n')
        + _arm("other", "index-wide", 'query_pipeline = "some-rung"\n'),
    )
    (path.parent / "questions.toml").write_text(_ANCHORED_QUESTIONS, encoding="utf-8")
    monkeypatch.setattr(eval_commands_module, "score_pipeline", _capturing_stub([]))
    await _run(path, store)
    (manifest,) = (path.with_suffix("") / "runs" / "pools").glob("*.json")
    older = manifest.with_name("older.json")
    body = json.loads(manifest.read_text(encoding="utf-8"))
    body.pop("target", None)
    older.write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(eval_commands_module, "score_pipeline", _capturing_stub(calls))

    # Act
    await _run(_replay(tmp_path, older.resolve()), store)

    # Assert
    assert load_pool_manifest(older).manifest.target is None
    assert {call["target"] for call in calls} == {None}
