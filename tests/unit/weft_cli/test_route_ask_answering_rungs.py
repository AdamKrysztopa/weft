"""A routed ask offers only rungs that answer — ledger task **44.0**.

A document carrying `route.summary` is a rung, and `weft ask` requires a rung to end in an
`Answer`. Two shipped documents carried a summary and ended in `repack`, so the router could
select one and fail at `_require(..., Answer)` after running it. The refusal happens before the
router is paid for, names the document, and offers the rungs that do answer.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from weft_cli.pipeline_catalogue import full_catalogue
from weft_cli.route_ask import UnansweringRungError, run_routed_ask, unanswering_rungs
from weft_embed import Embedder
from weft_embed.hash_embedder import HashEmbedder
from weft_engine import registry_bootstrap
from weft_engine.llm_roles import LLMSection
from weft_engine.services import ServiceSelection
from weft_generate import CitedAnswer, Generator
from weft_generate.prompts import ANSWER_WITH_CITATIONS_NAME, AnswerWithCitationsPrompt
from weft_kernel.context import Context, ServiceRegistry
from weft_kernel.payload import Outcome
from weft_kernel.registry import Registry
from weft_llm.client import NullSink
from weft_llm.contract import LLMProvider
from weft_llm.payload import Completion, Conversation
from weft_llm.roles import LLMRoles, RoleMapping
from weft_llm.scripted import ScriptedConfig, ScriptedProvider
from weft_prompts.contract import Prompt
from weft_retrieve import (
    ROUTE_QUERY_NAME,
    ContextPacker,
    Fuser,
    LlmQueryScorer,
    NearestDescription,
    NoRetrieval,
    QueryScorer,
    Repack,
    Retriever,
    RouteQueryPrompt,
    RoutingPolicy,
    SingleList,
)
from weft_store import NodeStore

_SCORES_JSON = (
    '{"scores": ['
    '{"name": "complexity", "score": 0.5}, '
    '{"name": "multi_hop", "score": 0.5}, '
    '{"name": "ambiguity", "score": 0.5}, '
    '{"name": "specificity", "score": 0.5}, '
    '{"name": "temporal_sensitivity", "score": 0.5}, '
    '{"name": "parametric_confidence", "score": 0.5}, '
    '{"name": "verifiability_need", "score": 0.5}'
    "]}"
)


class _CountingProvider(ScriptedProvider):
    """`scripted`, counting every model call made through it."""

    def __init__(self, calls: list[str]) -> None:
        super().__init__(ScriptedConfig(reply=_SCORES_JSON))
        self._calls = calls

    async def complete(
        self, conv: Conversation, *, model: str, ctx: Context
    ) -> Outcome[Completion]:
        self._calls.append(model)
        return await super().complete(conv, model=model, ctx=ctx)


class _FakeStore:
    """A `NodeStore` stand-in that no stage here calls."""


def _fake_store_factory(config: object) -> _FakeStore:
    del config
    return _FakeStore()


def _registry(calls: list[str]) -> Registry:
    def _scripted_factory(config: object) -> _CountingProvider:
        del config
        return _CountingProvider(calls)

    registry = Registry()
    registry.add(LLMProvider, "scripted", _scripted_factory, distribution="weft-llm")
    registry.add(NodeStore, "fake-store", _fake_store_factory, distribution="weft-store")
    registry.add(Embedder, "fake-embed", HashEmbedder, distribution="weft-embed")
    registry.add(Retriever, "no-retrieval", NoRetrieval, distribution="weft-retrieve")
    registry.add(Fuser, "single-list", SingleList, distribution="weft-retrieve")
    registry.add(ContextPacker, "repack", Repack, distribution="weft-retrieve")
    registry.add(Generator, "cited-answer", CitedAnswer, distribution="weft-generate")
    registry.add(QueryScorer, "query-scorer", LlmQueryScorer, distribution="weft-retrieve")
    registry.add(
        RoutingPolicy, "nearest-description", NearestDescription, distribution="weft-retrieve"
    )
    registry.add(Prompt, ROUTE_QUERY_NAME, RouteQueryPrompt, distribution="weft-retrieve")
    registry.add(
        Prompt, ANSWER_WITH_CITATIONS_NAME, AnswerWithCitationsPrompt, distribution="weft-generate"
    )
    return registry


def _ctx() -> Context:
    return Context(
        tenant_id="t", run_id="r", trace_id="tr", locale="en", services=ServiceRegistry()
    )


def _llm() -> LLMSection:
    return LLMSection(
        roles=LLMRoles(
            roles={
                "route": RoleMapping(provider="scripted"),
                "generate": RoleMapping(provider="scripted"),
            }
        )
    )


def _write(directory: Path, document: dict[str, object]) -> None:
    (directory / f"{document['name']}.yaml").write_text(
        yaml.safe_dump(document, sort_keys=False), encoding="utf-8"
    )


def _project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A router, one rung that answers, and one that carries a summary and ends in `repack`."""
    monkeypatch.chdir(tmp_path)
    pipelines = tmp_path / "pipelines"
    pipelines.mkdir()
    _write(
        pipelines,
        {
            "name": "my-router",
            "stages": [
                {"id": "score", "use": "query-scorer", "with": {"role": "route"}},
                {"id": "route", "use": "nearest-description"},
            ],
        },
    )
    _write(
        pipelines,
        {
            "name": "my-rung",
            "vars": {"route.summary": "Answers without retrieving anything."},
            "stages": [
                {"id": "retrieve", "use": "no-retrieval"},
                {"id": "fuse", "use": "single-list"},
                {"id": "pack", "use": "repack"},
                {
                    "id": "generate",
                    "use": "cited-answer",
                    "with": {"when_no_evidence": "answer_from_memory"},
                },
            ],
        },
    )
    _write(
        pipelines,
        {
            "name": "answers-nothing",
            "vars": {"route.summary": "Finds passages and never writes an answer."},
            "stages": [
                {"id": "retrieve", "use": "no-retrieval"},
                {"id": "fuse", "use": "single-list"},
                {"id": "pack", "use": "repack"},
            ],
        },
    )


async def test_a_rung_ending_in_no_generator_is_refused_before_the_router_is_paid_for(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    _project(tmp_path, monkeypatch)
    calls: list[str] = []

    # Act
    with pytest.raises(UnansweringRungError) as refused:
        await run_routed_ask(
            "what happens if a store advertises no capability at all?",
            registry=_registry(calls),
            reports=(),
            ctx=_ctx(),
            llm=_llm(),
            services=ServiceSelection(embed="fake-embed", store="fake-store", route="my-router"),
            sink=NullSink(),
        )

    # Assert
    assert "answers-nothing" in str(refused.value)
    assert "my-rung" in refused.value.valid_options
    assert "answers-nothing" not in refused.value.valid_options
    assert calls == []


def test_a_rung_ending_in_a_generator_is_not_named(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    _project(tmp_path, monkeypatch)
    catalogue = full_catalogue(reports=())

    # Act
    named = unanswering_rungs(catalogue, registry=_registry([]), reports=())

    # Assert
    assert named == ("answers-nothing",)


def test_every_shipped_rung_ends_in_a_generator(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange — the registry and catalogue an installed wheel builds, from an empty project.
    monkeypatch.chdir(tmp_path)
    config = tmp_path / "weft.toml"
    config.write_text("", encoding="utf-8")
    deps = registry_bootstrap.build_dependencies(config_path=config)
    catalogue = full_catalogue(reports=deps.reports)

    # Act
    named = unanswering_rungs(
        catalogue,
        registry=deps.registry,
        reports=deps.reports,
        contributions=deps.contributions,
    )

    # Assert — the control: the shipped catalogue does carry rungs, so an empty answer means
    # every one of them answers rather than that none was read.
    assert sum("route.summary" in pipeline.vars for pipeline in catalogue.values()) > 10
    assert named == ()
