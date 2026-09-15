"""`weft eval run` measures each question's latency and each role's tokens — ledger task **33.7**.

A record already carried per-question *scores* (task 16.4) and a run's total query seconds (task
10.22), so a reader could see that a rung was slower without seeing whether every question was
slower or one was a hundred times slower — which is the tail `The Tail at Scale` warns an average
hides. `score_pipeline` now times each question on its own, keyed exactly as `question_scores` is,
and tallies what each model role spent, reading task 33.6's usage entries.

**A role whose provider does not report usage is counted as a call not reporting**, never as zero
tokens: `RoleTokens.calls_not_reporting` is how a reader tells *free* from *unmeasured*.

The doubles are `tests/unit/weft_cli/test_eval_scoring.py`'s (`L11.17`).
"""

import asyncio
from collections.abc import Sequence

from weft_cli.eval_scoring import Question, ScoredRun, role_tokens, score_pipeline
from weft_embed import Embedder
from weft_eval import Settings, register
from weft_eval.run_record import QuestionKey, RoleTokens
from weft_kernel.context import Context
from weft_kernel.discovery import PackRegistrar
from weft_kernel.payload import Lineage, MediaType, Node, Outcome, Produced, SourceId, Vector
from weft_kernel.registry import Registry
from weft_kernel.resolution import ResolvedPipeline, ResolvedStage
from weft_llm.payload import TokenUsage
from weft_llm.usage import UsageEntry
from weft_store import Filter, NodeStore, Scored


class _FakeEmbedder:
    def __init__(self, config: object) -> None:
        del config

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        del ctx
        return Produced(value=[node.with_embedding(Vector(values=(1.0,))) for node in payload])


class _SlowVectorSearchStore:
    def __init__(self, config: object) -> None:
        del config

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        del ctx
        return Produced(value=payload)

    async def search_vector(
        self, vector: Vector, top_k: int, filter: Filter | None = None
    ) -> Sequence[Scored[Node]]:
        del vector, top_k, filter
        await asyncio.sleep(0.01)
        found = Node.synthetic(
            content="a stored passage", media_type=MediaType.TEXT, reason="fixture"
        ).model_copy(
            update={"lineage": Lineage.derived(parents=(), sources=frozenset({SourceId("doc-a")}))}
        )
        return [Scored(value=found, score=0.9)]


def _registry() -> Registry:
    registry = Registry()
    registry.add(Embedder, "hash", _FakeEmbedder, distribution="weft-embed")
    registry.add(NodeStore, "pgvector", _SlowVectorSearchStore, distribution="weft-store")
    registrar = PackRegistrar(registry, distribution="weft-eval")
    register(registrar, Settings())
    registrar.commit()
    return registry


def _resolved_pipeline() -> ResolvedPipeline:
    return ResolvedPipeline(
        name="index",
        stages=(
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
        ),
    )


def _ctx() -> Context:
    return Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")


async def _scored(questions: tuple[Question, ...]) -> ScoredRun:
    return await score_pipeline(
        registry=_registry(),
        resolved_pipeline=_resolved_pipeline(),
        questions=questions,
        top_k=1,
        ctx=_ctx(),
        corpus_document_ids=("doc-a", "doc-b"),
    )


async def test_each_question_is_timed_and_keyed_as_its_scores_are() -> None:
    # Arrange
    questions = (
        Question(id="fetch-001", query="q", relevant_documents=("doc-a",)),
        Question(id="fetch-002", query="q2", relevant_documents=("doc-a",)),
    )

    # Act
    report = await _scored(questions)

    # Assert
    seconds = report.question_seconds
    assert seconds is not None
    assert seconds.keyed_by is QuestionKey.QUESTION_ID
    assert set(seconds.seconds) == set(report.question_scores["precision@1"].scores)
    assert all(value >= 0.009 for value in seconds.seconds.values())


async def test_a_run_that_asked_no_model_records_no_role_rather_than_zero_tokens() -> None:
    # Act
    report = await _scored((Question(query="q", relevant_documents=("doc-a",)),))

    # Assert
    assert report.token_usage == {}


def test_role_tokens_sum_what_was_reported_and_count_what_was_not() -> None:
    # Arrange
    entries = (
        UsageEntry(
            role="generate",
            position="answer",
            provider="openai",
            model="m",
            usage=TokenUsage(prompt_tokens=100, completion_tokens=20),
        ),
        UsageEntry(
            role="generate",
            position="answer",
            provider="openai",
            model="m",
            usage=TokenUsage(prompt_tokens=50, completion_tokens=5),
        ),
        UsageEntry(role="grade", position="grade", provider="scripted", model="", usage=None),
    )

    # Act
    tokens = role_tokens(entries)

    # Assert
    assert tokens == {
        "generate": RoleTokens(
            prompt_tokens=150, completion_tokens=25, calls=2, calls_not_reporting=0
        ),
        "grade": RoleTokens(prompt_tokens=0, completion_tokens=0, calls=1, calls_not_reporting=1),
    }
