"""`weft ask` will not rank by vectors from an embedder nobody chose — carried repair **R20.6**.

G21 keeps `hash` as the default embedder so `weft index`, the quickstart and the gate run offline,
and it rejected labelling alone as an answer. An outside review then found `weft ask` printed no
warning at all: a project that never set `[services] embed` got a plausible-looking ranking whose
order means nothing, and with `[llm.roles]` mapped, an answer generated from it. So a query that
would embed the question with the defaulted `hash` is refused, naming the three ways on — the
lexical pipeline, a real embedder, or `embed = "hash"` written down as a choice — and a query that
embeds nothing, `lexical-retrieve`, runs as before.

The refusal sits where the query's `Embedder` service is built rather than on a list of pipelines
that embed: no stage declares whether it embeds, and `hybrid` with `channels: [text]` still
declares `VectorSearch`.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import pytest

from weft_cli import commands
from weft_cli.exit_codes import ExitCode, exit_code_for
from weft_embed.contract import Embedder
from weft_embed.hash_embedder import HashEmbedder
from weft_engine.registry_bootstrap import Dependencies
from weft_engine.services import DEFAULT_EMBEDDER, ServiceSelection, UnchosenEmbedderError
from weft_kernel.context import Context, ServiceRegistry
from weft_kernel.discovery import PackReport, PackStatus, PipelineResource
from weft_kernel.payload import MediaType, Node, Produced, Vector
from weft_kernel.registry import Registry
from weft_retrieve import ContextPacker, Fuser, Reranker, Retriever
from weft_retrieve.anchor_promote import AnchorPromote
from weft_retrieve.fusion import SingleList
from weft_retrieve.hybrid import Hybrid
from weft_retrieve.repack import Repack
from weft_retrieve.vector_top_k import VectorTopK
from weft_store.contract import Filter, NodeStore, Scored

LEXICAL = "lexical-retrieve"
VECTOR = "anchor-promote-retrieve"


class _BothArmsStore:
    """Answers either arm, so a refusal is the embedder's and never a missing search."""

    def __init__(self, config: object = None) -> None:
        del config

    async def search_vector(
        self, vector: Vector, top_k: int, filter: Filter | None = None
    ) -> Sequence[Scored[Node]]:
        del vector, top_k, filter
        return (_hit("a loom holds the warp", 0.9),)

    async def search_text(
        self, text: str, top_k: int, filter: Filter | None = None
    ) -> Sequence[Scored[Node]]:
        del text, top_k, filter
        return (_hit("the weft crosses the warp", 7.2),)

    async def count(self) -> int:
        return 2

    async def aclose(self) -> None:
        return None


def _hit(content: str, score: float) -> Scored[Node]:
    node = Node.synthetic(content=content, media_type=MediaType.TEXT, reason="fixture")
    return Scored(value=node, score=score)


def _registry() -> Registry:
    registry = Registry()
    registry.add(NodeStore, "fake-store", _BothArmsStore, distribution="weft-store")
    registry.add(Embedder, DEFAULT_EMBEDDER, HashEmbedder, distribution="weft-embed")
    registry.add(Retriever, "hybrid", Hybrid, distribution="weft-retrieve")
    registry.add(Retriever, "vector-top-k", VectorTopK, distribution="weft-retrieve")
    registry.add(Fuser, "single-list", SingleList, distribution="weft-retrieve")
    registry.add(Reranker, "anchor-promote", AnchorPromote, distribution="weft-retrieve")
    registry.add(ContextPacker, "repack", Repack, distribution="weft-retrieve")
    return registry


def _reports() -> tuple[PackReport, ...]:
    return (
        PackReport(
            pack="retrieve",
            distribution="weft-retrieve",
            status=PackStatus.ACTIVE,
            pipeline_resources=tuple(
                PipelineResource(
                    distribution="weft-retrieve",
                    package="weft_retrieve",
                    resource=f"pipelines/{name}.yaml",
                )
                for name in (LEXICAL, VECTOR)
            ),
        ),
    )


def _deps(*, chosen: bool) -> Dependencies:
    return Dependencies(
        registry=_registry(),
        reports=_reports(),
        services=ServiceSelection(store="fake-store"),
        embed_was_selected=chosen,
    )


def _ctx(deps: Dependencies) -> Context:
    services = ServiceRegistry()
    services.add(Dependencies, deps)
    return Context(tenant_id="t", run_id="r", trace_id="tr", locale="en", services=services)


async def test_retrieve_only_refuses_to_rank_by_an_embedder_nobody_chose() -> None:
    # Arrange
    args = commands.AskArgs(question="what does the weft do", retrieve_only=True)

    # Act
    with pytest.raises(UnchosenEmbedderError) as refusal:
        await commands.AskCommand().run(args, _ctx(_deps(chosen=False)))

    # Assert
    message = str(refusal.value)
    assert f"--pipeline {LEXICAL}" in message
    assert "[services] embed" in message
    assert f'embed = "{DEFAULT_EMBEDDER}"' in message
    assert exit_code_for(refusal.value) == ExitCode.OPERATION_FAILED


async def test_the_lexical_pipeline_answers_with_no_embedder_chosen() -> None:
    # Arrange
    args = commands.AskArgs(question="what does the weft do", retrieve_only=True, pipeline=LEXICAL)

    # Act
    outcome = await commands.AskCommand().run(args, _ctx(_deps(chosen=False)))

    # Assert
    assert isinstance(outcome, Produced)
    result = outcome.value
    assert isinstance(result, commands.AskCommandResult)
    assert [hit.content for hit in result.hits] == ["the weft crosses the warp"]


async def test_a_named_pipeline_that_embeds_the_question_is_refused() -> None:
    # Arrange
    args = commands.AskArgs(question="what does the weft do", retrieve_only=True, pipeline=VECTOR)

    # Act / Assert
    with pytest.raises(UnchosenEmbedderError) as refusal:
        await commands.AskCommand().run(args, _ctx(_deps(chosen=False)))
    assert f"--pipeline {LEXICAL}" in str(refusal.value)


@pytest.mark.parametrize("pipeline", [None, VECTOR])
async def test_hash_written_down_in_weft_toml_is_a_choice_and_ranks(pipeline: str | None) -> None:
    # Arrange
    args = commands.AskArgs(question="what does the weft do", retrieve_only=True, pipeline=pipeline)

    # Act
    outcome = await commands.AskCommand().run(args, _ctx(_deps(chosen=True)))

    # Assert
    assert isinstance(outcome, Produced)
    result = outcome.value
    assert isinstance(result, commands.AskCommandResult)
    assert [hit.content for hit in result.hits] == ["a loom holds the warp"]


@pytest.mark.parametrize(
    ("pipeline", "entry"), [(None, "run_routed_ask"), ("retrieve-then-generate", "run_named_ask")]
)
@pytest.mark.parametrize(("chosen", "expected"), [(False, DEFAULT_EMBEDDER), (True, None)])
async def test_a_generating_ask_hands_the_unchosen_embedder_to_the_run(
    monkeypatch: pytest.MonkeyPatch,
    pipeline: str | None,
    entry: str,
    *,
    chosen: bool,
    expected: str | None,
) -> None:
    # Arrange — the run itself is a double; what is asserted is what reaches it.
    seen: list[dict[str, Any]] = []

    class _StopError(Exception):
        pass

    async def _capture(question: str, **kwargs: Any) -> Any:
        del question
        seen.append(kwargs)
        raise _StopError

    monkeypatch.setattr(commands, entry, _capture)
    args = commands.AskArgs(question="what does the weft do", pipeline=pipeline, allow_pending=True)

    # Act
    with pytest.raises(_StopError):
        await commands.AskCommand().run(args, _ctx(_deps(chosen=chosen)))

    # Assert
    assert [call["unchosen_embedder"] for call in seen] == [expected]
