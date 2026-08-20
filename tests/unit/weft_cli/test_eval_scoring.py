"""Unit tests for `weft_cli.eval_scoring`.

Mirrors `packages/weft-cli/src/weft_cli/eval_scoring.py`. `load_questions` is exercised against
real files on disk — the happy path (a well-formed JSON list round-trips into `Question`s) and
the error case (malformed JSON refuses naming the path, mirroring `weft_cli.ask`'s own tests'
convention of fake embedder/store stand-ins). `score_pipeline` is exercised against fakes for
`Embedder`/`NodeStore` — `weft_cli.ask`'s own `test_ask.py`'s convention, since the property
under test is that this module retrieves through the *resolved pipeline's own* stages (never
`[services]`) and folds the result into a real `weft_eval.harness.score_retrieval_gate_subset`
report — plus the edge case (a pipeline naming no `Embedder`/`NodeStore` stage refuses outright
rather than silently reporting empty metrics indistinguishable from "no --questions given").
"""

from collections.abc import Sequence
from pathlib import Path

import pytest

from weft_cli.eval_scoring import (
    PipelineNotRetrievableError,
    Question,
    QuestionsFileError,
    load_questions,
    score_pipeline,
)
from weft_embed import Embedder
from weft_eval import Settings, register
from weft_kernel.context import Context
from weft_kernel.discovery import PackRegistrar
from weft_kernel.payload import (
    Lineage,
    MediaType,
    Node,
    Outcome,
    Produced,
    SourceId,
    Vector,
)
from weft_kernel.registry import Registry
from weft_kernel.resolution import ResolvedPipeline, ResolvedStage
from weft_store import Filter, NodeStore, Scored


class _FakeEmbedder:
    def __init__(self, config: object) -> None:
        del config

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        del ctx
        return Produced(value=[node.with_embedding(Vector(values=(1.0,))) for node in payload])


class _FakeVectorSearchStore:
    def __init__(self, config: object) -> None:
        del config

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        del ctx
        return Produced(value=payload)

    async def search_vector(
        self, vector: Vector, top_k: int, filter: Filter | None = None
    ) -> Sequence[Scored[Node]]:
        del vector, top_k, filter
        found = Node.synthetic(
            content="a stored passage", media_type=MediaType.TEXT, reason="fixture"
        ).model_copy(
            update={"lineage": Lineage.derived(parents=(), sources=frozenset({SourceId("doc-a")}))}
        )
        return [Scored(value=found, score=0.9)]


def _registry() -> Registry:
    registry = Registry()
    registry.add(Embedder, "hash", _FakeEmbedder, distribution="weft-embed")
    registry.add(NodeStore, "pgvector", _FakeVectorSearchStore, distribution="weft-store")
    registrar = PackRegistrar(registry, distribution="weft-eval")
    register(registrar, Settings())
    registrar.commit()
    return registry


def _resolved_pipeline(*, with_stages: bool = True) -> ResolvedPipeline:
    stages = (
        (
            ResolvedStage(
                id="embed",
                contract="Embedder",
                use="hash",
                distribution="weft-embed",
                provenance="index",
            ),
            ResolvedStage(
                id="store",
                contract="NodeStore",
                use="pgvector",
                distribution="weft-store",
                provenance="index",
            ),
        )
        if with_stages
        else ()
    )
    return ResolvedPipeline(name="index", stages=stages)


def _ctx() -> Context:
    return Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")


# --- load_questions -------------------------------------------------------------------------


def test_load_questions_round_trips_a_well_formed_file(tmp_path: Path) -> None:
    # Arrange
    path = tmp_path / "questions.json"
    path.write_text(
        '[{"query": "what is weft?", "relevant_documents": ["doc-a", "doc-b"]}]',
        encoding="utf-8",
    )

    # Act
    questions = load_questions(path)

    # Assert
    assert questions == (Question(query="what is weft?", relevant_documents=("doc-a", "doc-b")),)


def test_load_questions_refuses_malformed_json_naming_the_path(tmp_path: Path) -> None:
    # Arrange
    path = tmp_path / "questions.json"
    path.write_text("not json", encoding="utf-8")

    # Act / Assert
    with pytest.raises(QuestionsFileError) as excinfo:
        load_questions(path)
    assert excinfo.value.path == str(path)


def test_load_questions_refuses_a_missing_file(tmp_path: Path) -> None:
    # Arrange
    path = tmp_path / "does-not-exist.json"

    # Act / Assert
    with pytest.raises(QuestionsFileError) as excinfo:
        load_questions(path)
    assert excinfo.value.path == str(path)


# --- score_pipeline --------------------------------------------------------------------------


async def test_score_pipeline_retrieves_and_scores_against_the_resolved_stages() -> None:
    # Arrange — one question whose relevant document is exactly what the fake store returns.
    questions = (Question(query="q", relevant_documents=("doc-a",)),)

    # Act
    report = await score_pipeline(
        registry=_registry(),
        resolved_pipeline=_resolved_pipeline(),
        questions=questions,
        top_k=1,
        ctx=_ctx(),
    )

    # Assert — the one retrieved passage is the one relevant document: precision@1 = 1.0.
    assert "precision@1" in report
    outcome = report["precision@1"]
    assert isinstance(outcome, Produced)
    assert outcome.value.mean == 1.0


async def test_score_pipeline_refuses_a_pipeline_with_no_store_stage() -> None:
    # Arrange
    questions = (Question(query="q", relevant_documents=("doc-a",)),)

    # Act / Assert
    with pytest.raises(PipelineNotRetrievableError) as excinfo:
        await score_pipeline(
            registry=_registry(),
            resolved_pipeline=_resolved_pipeline(with_stages=False),
            questions=questions,
            top_k=1,
            ctx=_ctx(),
        )
    assert excinfo.value.pipeline == "index"
