"""Each question's tokens by role, and each judge's prompt digest, reach the scored run — task 44.4.

A run's token total (task 33.7) says what a rung cost on average; a router choosing per question
needs what each question cost. `question_tokens` is what answering a question spent, by role, and
the run total still counts every call. The doubles are `test_eval_latency_and_tokens.py`'s
(`L11.17`), copied here, with an embedder that records usage the way `weft_openai`'s does.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence

from weft_cli.eval_scoring import judge_prompt_digests, score_pipeline
from weft_embed import Embedder
from weft_eval import Settings, register
from weft_eval.prompts import AnswerCorrectnessJudgePrompt
from weft_eval.question_set import Question, QuestionField
from weft_kernel.context import Context
from weft_kernel.discovery import PackRegistrar
from weft_kernel.payload import Lineage, MediaType, Node, Outcome, Produced, SourceId, Vector
from weft_kernel.registry import Registry
from weft_kernel.resolution import ResolvedPipeline, ResolvedStage
from weft_llm.payload import TokenUsage
from weft_llm.usage import UsageEntry, record_usage
from weft_prompts.typed_prompt import prompt_digest
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


def _question(identifier: str, text: str, relevant_documents: tuple[str, ...] = ()) -> Question:
    """The one question model, stating absent every field this fixture does not need."""
    return Question.model_validate(
        {
            "id": identifier,
            "text": text,
            "language": "en",
            "relevant_documents": relevant_documents,
            "absent": frozenset(QuestionField),
            "absent_reason": "a scoring fixture",
        }
    )


def _silent_registry() -> Registry:
    registry = Registry()
    registry.add(Embedder, "hash", _FakeEmbedder, distribution="weft-embed")
    registry.add(NodeStore, "pgvector", _SlowVectorSearchStore, distribution="weft-store")
    registrar = PackRegistrar(registry, distribution="weft-eval")
    register(registrar, Settings())
    registrar.commit()
    return registry


class _MeteredEmbedder:
    """Records one `embed` usage entry per call, one prompt token per character embedded."""

    def __init__(self, config: object) -> None:
        del config

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        del ctx
        record_usage(
            UsageEntry(
                role="embed",
                position="embed",
                provider="metered",
                model="metered-1",
                usage=TokenUsage(
                    prompt_tokens=sum(len(str(node.content)) for node in payload),
                    completion_tokens=0,
                ),
            )
        )
        return Produced(value=[node.with_embedding(Vector(values=(1.0,))) for node in payload])


def _registry() -> Registry:
    registry = Registry()
    registry.add(Embedder, "hash", _MeteredEmbedder, distribution="weft-embed")
    registry.add(NodeStore, "pgvector", _SlowVectorSearchStore, distribution="weft-store")
    registrar = PackRegistrar(registry, distribution="weft-eval")
    register(registrar, Settings())
    registrar.commit()
    return registry


async def test_each_question_carries_what_answering_it_spent_and_the_total_counts_it() -> None:
    # Arrange — two questions whose query embeddings cost differently.
    questions = (
        _question("q-short", "abc", ("doc-a",)),
        _question("q-long", "abcdefghij", ("doc-a",)),
    )

    # Act
    report = await score_pipeline(
        registry=_registry(),
        resolved_pipeline=_resolved_pipeline(),
        questions=questions,
        top_k=1,
        ctx=_ctx(),
        corpus_document_ids=("doc-a", "doc-b"),
    )

    # Assert
    short = report.question_tokens["q-short"]["embed"]
    long = report.question_tokens["q-long"]["embed"]
    assert short.calls >= 1
    assert long.prompt_tokens > short.prompt_tokens
    assert report.token_usage["embed"].prompt_tokens == short.prompt_tokens + long.prompt_tokens
    assert report.token_usage["embed"].calls == short.calls + long.calls


async def test_a_question_that_asked_no_model_has_no_entry() -> None:
    # Act — the latency test's own registry, whose embedder records nothing.
    report = await score_pipeline(
        registry=_silent_registry(),
        resolved_pipeline=_resolved_pipeline(),
        questions=(_question("q-1", "q", ("doc-a",)),),
        top_k=1,
        ctx=_ctx(),
        corpus_document_ids=("doc-a", "doc-b"),
    )

    # Assert
    assert report.question_tokens == {}
    assert report.judge_prompts == {}


def test_a_judge_metric_records_its_prompt_s_digest_under_its_reported_name() -> None:
    # Act — one judge and one metric that calls no model.
    digests = judge_prompt_digests(_registry(), ("answer-correctness", "precision-at-k"))

    # Assert
    assert digests == {"answer_correctness": prompt_digest(AnswerCorrectnessJudgePrompt)}
