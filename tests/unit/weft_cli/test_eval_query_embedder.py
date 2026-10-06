"""`weft eval` — ledger task **20.12**: an arm's questions are embedded by its own index pipeline.

Before this task an arm naming a query pipeline embedded its questions with the invocation's one
`[services] embed`, while an arm naming none used its ingest pipeline's own `Embedder` stage. Two
arms indexed by two embedders could not both be asked, and a record named the ingest pipeline's
model while its questions were embedded by whatever `[services]` said. Every path now takes the
ingest pipeline's `Embedder` stage, plugin and configuration as resolution set it, and the identity
the questions were embedded with is carried on `ScoredRun` for the record to persist.

The per-target identity check (`weft_engine.targets.check_embedding_for_query`) keeps running
against the arm's own target, so it still refuses when the target and the pipeline disagree.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import ClassVar, cast

import pytest
from pydantic import BaseModel, ConfigDict

from weft_cli import eval_scoring as eval_scoring_module
from weft_cli import route_ask as route_ask_module
from weft_cli.eval_scoring import score_pipeline
from weft_embed import Embedder
from weft_embed.contract import EmbeddingModel
from weft_embed.hash_embedder import HashEmbedder, HashEmbedderConfig
from weft_engine.services import ServiceSelection, embed_config_for
from weft_engine.targets import (
    EmbeddingIdentityMismatchError,
    claim_embedding_for_write,
    embedding_identity_of,
)
from weft_eval.harness import SubsetScores
from weft_eval.question_set import Question, QuestionField
from weft_generate import CitedAnswer, Generator
from weft_generate.prompts import ANSWER_WITH_CITATIONS_NAME, AnswerWithCitationsPrompt
from weft_kernel.context import Context
from weft_kernel.payload import Node, Outcome
from weft_kernel.pipeline import Pipeline, StageDeclaration
from weft_kernel.registry import Registry
from weft_kernel.resolution import ResolvedPipeline, resolve
from weft_prompts.contract import Prompt
from weft_retrieve import ContextPacker, Fuser, NoRetrieval, Repack, Retriever, SingleList
from weft_store import NodeStore
from weft_store.contract import EmbeddingIdentity
from weft_store.memory import MemoryStore

#: Not `HashEmbedderConfig`'s default width, so a query embedded with `[services] embed`'s
#: defaults cannot pass for one embedded by the ingest stage.
_INGEST_WIDTH = 32


class _AccountConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    model: str = "configured-default"


class _AccountEmbedder:
    """Calls the account's model unless its own stage names one, as `OpenAIEmbedder` does (R22.1).

    So a stage that names no model and a stage that names this config's default are two
    embedders, and the difference lives only in `model_fields_set`.
    """

    config_model: ClassVar[type[_AccountConfig]] = _AccountConfig

    def __init__(self, config: _AccountConfig | None = None) -> None:
        self._config = config if config is not None else _AccountConfig()
        self._hash = HashEmbedder()

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        return await self._hash.run(payload, ctx)

    async def embedding_model(self) -> EmbeddingModel:
        named = "model" in self._config.model_fields_set
        width = (await self._hash.embedding_model()).width
        return EmbeddingModel(model=self._config.model if named else "account-model", width=width)


def _question(identifier: str, text: str) -> Question:
    return Question.model_validate(
        {
            "id": identifier,
            "text": text,
            "language": "en",
            "relevant_documents": (),
            "absent": frozenset(QuestionField),
            "absent_reason": "a scoring fixture",
        }
    )


def _ctx() -> Context:
    return Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")


def _registry(store: MemoryStore) -> Registry:
    def _store_factory(config: object) -> MemoryStore:
        del config
        return store

    registry = Registry()
    registry.add(Embedder, "hash", HashEmbedder, distribution="weft-embed")
    registry.add(Embedder, "account", _AccountEmbedder, distribution="test-account")
    registry.add(NodeStore, "memory", _store_factory, distribution="weft-store")
    registry.add(Retriever, "no-retrieval", NoRetrieval, distribution="weft-retrieve")
    registry.add(Fuser, "single-list", SingleList, distribution="weft-retrieve")
    registry.add(ContextPacker, "repack", Repack, distribution="weft-retrieve")
    registry.add(Generator, "cited-answer", CitedAnswer, distribution="weft-generate")
    registry.add(
        Prompt, ANSWER_WITH_CITATIONS_NAME, AnswerWithCitationsPrompt, distribution="weft-generate"
    )
    return registry


def _ingest(registry: Registry, embed: StageDeclaration) -> ResolvedPipeline:
    """An ingest pipeline resolved the way `weft eval` resolves one, so its config is as set."""
    pipeline = Pipeline(
        name="index-arm", stages=(embed, StageDeclaration(id="store", use="memory"))
    )
    return resolve(pipeline, registry=registry, contracts={"embed": Embedder, "store": NodeStore})


def _hash_at(width: int) -> StageDeclaration:
    return StageDeclaration(id="embed", use="hash", config={"dimension": width})


def _rungs() -> dict[str, Pipeline]:
    retrieval = (
        StageDeclaration(id="retrieve", use="no-retrieval"),
        StageDeclaration(id="fuse", use="single-list"),
        StageDeclaration(id="pack", use="repack"),
    )
    return {
        "rung-r": Pipeline(name="rung-r", stages=retrieval),
        "rung-a": Pipeline(
            name="rung-a",
            stages=(*retrieval, StageDeclaration(id="generate", use="cited-answer")),
        ),
    }


def _stub_catalogue(catalogue: dict[str, Pipeline]) -> Callable[..., dict[str, Pipeline]]:
    def _full_catalogue(
        *, directory: Path = Path("pipelines"), reports: Sequence[object] = ()
    ) -> dict[str, Pipeline]:
        del directory, reports
        return catalogue

    return _full_catalogue


async def _no_metrics(*_args: object, **_kwargs: object) -> SubsetScores:
    return SubsetScores(metrics={}, per_question={})


async def _hash_identity(width: int) -> EmbeddingIdentity:
    identity = await embedding_identity_of(
        HashEmbedder(HashEmbedderConfig(dimension=width)), plugin="hash", distribution="weft-embed"
    )
    assert identity is not None
    return identity


async def _store_built_with(identity: EmbeddingIdentity) -> MemoryStore:
    store = MemoryStore()
    await claim_embedding_for_write(store, identity, plugin=identity.plugin, required=False)
    return store


@pytest.fixture(autouse=True)
def rungs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(route_ask_module, "full_catalogue", _stub_catalogue(_rungs()))
    monkeypatch.setattr(eval_scoring_module, "score_retrieval_gate_subset", _no_metrics)


async def test_a_retrieval_rung_embeds_its_questions_with_the_ingest_pipelines_embedder() -> None:
    """`[services] embed` is `hash` at its default width; the arm was indexed at another."""
    # Arrange
    ingest_identity = await _hash_identity(_INGEST_WIDTH)
    store = await _store_built_with(ingest_identity)
    registry = _registry(store)

    # Act
    scored = await score_pipeline(
        registry=registry,
        resolved_pipeline=_ingest(registry, _hash_at(_INGEST_WIDTH)),
        questions=(_question("q-1", "why"),),
        top_k=3,
        ctx=_ctx(),
        query_pipeline="rung-r",
        services=ServiceSelection(store="memory"),
        corpus_document_ids=("doc-a",),
    )

    # Assert
    assert scored.query_embedding == ingest_identity


async def test_a_target_built_by_another_embedder_is_still_refused() -> None:
    """The planted control: the identity check still runs, against the arm's own target."""
    # Arrange
    store = await _store_built_with(await _hash_identity(_INGEST_WIDTH * 2))
    registry = _registry(store)

    # Act / Assert
    with pytest.raises(EmbeddingIdentityMismatchError) as caught:
        await score_pipeline(
            registry=registry,
            resolved_pipeline=_ingest(registry, _hash_at(_INGEST_WIDTH)),
            questions=(_question("q-1", "why"),),
            top_k=3,
            ctx=_ctx(),
            query_pipeline="rung-r",
            services=ServiceSelection(store="memory"),
            corpus_document_ids=("doc-a",),
        )
    assert caught.value.other.width == _INGEST_WIDTH


async def test_a_stage_naming_no_model_is_asked_as_a_stage_naming_no_model() -> None:
    """The stage's configuration travels as resolution set it, not with its defaults filled in.

    `_AccountEmbedder` calls the account's model when its stage names none, so a query side
    built from the stage's defaults would embed with `configured-default` against a target
    built with `account-model`.
    """
    # Arrange
    indexed_by = await embedding_identity_of(
        _AccountEmbedder(_AccountConfig()), plugin="account", distribution="test-account"
    )
    assert indexed_by is not None
    store = await _store_built_with(indexed_by)
    registry = _registry(store)

    # Act
    scored = await score_pipeline(
        registry=registry,
        resolved_pipeline=_ingest(registry, StageDeclaration(id="embed", use="account")),
        questions=(_question("q-1", "why"),),
        top_k=3,
        ctx=_ctx(),
        query_pipeline="rung-r",
        services=ServiceSelection(store="memory"),
        corpus_document_ids=("doc-a",),
    )

    # Assert
    assert scored.query_embedding is not None
    assert scored.query_embedding.model == "account-model"


async def test_a_generating_rung_is_handed_the_ingest_pipelines_embedder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    ingest_identity = await _hash_identity(_INGEST_WIDTH)
    registry = _registry(await _store_built_with(ingest_identity))
    handed: list[ServiceSelection] = []

    async def _answer(question: str, **kwargs: object) -> object:
        del question
        handed.append(cast("ServiceSelection", kwargs["services"]))
        raise RuntimeError("the services were captured; nothing past them is under test")

    monkeypatch.setattr(eval_scoring_module, "run_named_ask", _answer)

    # Act
    with pytest.raises(RuntimeError):
        await score_pipeline(
            registry=registry,
            resolved_pipeline=_ingest(registry, _hash_at(_INGEST_WIDTH)),
            questions=(_question("q-1", "why"),),
            top_k=3,
            ctx=_ctx(),
            query_pipeline="rung-a",
            services=ServiceSelection(store="memory"),
            corpus_document_ids=("doc-a",),
        )

    # Assert
    (services,) = handed
    entry = registry.entry(Embedder, services.embed)
    built = entry.factory(embed_config_for(registry, services))
    stated = await embedding_identity_of(
        built, plugin=services.embed, distribution=entry.distribution
    )
    assert stated == ingest_identity


async def test_an_arm_naming_no_query_rung_records_the_embedder_it_asked_with(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    ingest_identity = await _hash_identity(_INGEST_WIDTH)
    registry = _registry(await _store_built_with(ingest_identity))

    async def _no_hits(*_args: object, **_kwargs: object) -> Sequence[object]:
        return ()

    monkeypatch.setattr(eval_scoring_module, "run_ask", _no_hits)

    # Act
    scored = await score_pipeline(
        registry=registry,
        resolved_pipeline=_ingest(registry, _hash_at(_INGEST_WIDTH)),
        questions=(_question("q-1", "why"),),
        top_k=3,
        ctx=_ctx(),
        services=ServiceSelection(store="memory"),
        corpus_document_ids=("doc-a",),
    )

    # Assert
    assert scored.query_embedding == ingest_identity
