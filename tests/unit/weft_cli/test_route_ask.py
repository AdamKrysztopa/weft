"""Unit tests for `weft_cli.route_ask`.

Mirrors `packages/weft-cli/src/weft_cli/route_ask.py`. Ledger **2.8**'s own CLI-facing
half: `weft-retrieve`'s own `route.yaml` and `no-retrieval.yaml` are resolved and run
through the *real* `weft_cli.compile`/`weft_kernel.runner.Runner` machinery, against a
hand-assembled registry of real plugin classes — `LlmQueryScorer`, `NearestDescription`,
`NoRetrieval`, `SingleList`, `Repack`, `CitedAnswer` — never test doubles standing in for
the mechanism under test. `scripted` is bound to a fixed reply so the run is deterministic
and needs no credential, the identical offline posture every other gate test in this tree
takes; `NodeStore`/`Embedder` are trivial fakes because nothing in this particular route
(`no-retrieval` needs neither) ever calls either one.

Covers the happy path (route, then execute, end to end, against real registry-resolved
plugins) and the error case of no installed pack contributing `route.yaml` at all.
"""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from weft_cli.llm_roles import LLMSection
from weft_cli.route_ask import NoRouterPipelineError, run_routed_ask
from weft_cli.services import ServiceSelection
from weft_embed import Embedder
from weft_embed.hash_embedder import HashEmbedder
from weft_generate import CitedAnswer, Generator
from weft_generate.payload import Answer
from weft_generate.prompts import ANSWER_WITH_CITATIONS_NAME, AnswerWithCitationsPrompt
from weft_kernel.context import Context, ServiceRegistry
from weft_kernel.discovery import PackReport, PackStatus, PipelineResource
from weft_kernel.registry import Registry
from weft_llm.contract import LLMProvider
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

#: `LlmQueryScorer`'s own JSON contract — `RouteQueryScores` — with every one of the
#: seven default `_SEVEN` dimensions named. `nearest-description` never reads these
#: scores at all, but `query-scorer` still has to answer them to hand a `Scorecard` on.
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


class _FakeStore:
    """A `NodeStore` stand-in — `no-retrieval`, `single-list`, `repack` and `cited-answer`
    call no store method at all, so nothing here needs to answer one."""


def _scripted_factory(config: object) -> ScriptedProvider:
    del config
    return ScriptedProvider(ScriptedConfig(reply=_SCORES_JSON))


def _fake_store_factory(config: object) -> _FakeStore:
    del config
    return _FakeStore()


def _registry() -> Registry:
    registry = Registry()
    registry.add(LLMProvider, "scripted", _scripted_factory, distribution="weft-llm")
    registry.add(NodeStore, "fake-store", _fake_store_factory, distribution="weft-store")
    # `nearest-description` genuinely embeds the query and every candidate's summary —
    # even with one candidate — so this needs a real `Embedder`, not a fake with no
    # `run` at all. `hash` is `weft-embed`'s own offline, deterministic, credential-free
    # built-in — the same default `weft_cli.services.DEFAULT_EMBEDDER` names.
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


def _reports() -> Sequence[PackReport]:
    """`weft-retrieve`'s own real, shipped resources — the exact two files its own
    `register()` contributes in production, read here through the same `importlib.
    resources` path a real install would use."""
    return (
        PackReport(
            distribution="weft-retrieve",
            status=PackStatus.ACTIVE,
            pipeline_resources=(
                PipelineResource(
                    distribution="weft-retrieve",
                    package="weft_retrieve",
                    resource="pipelines/route.yaml",
                ),
                PipelineResource(
                    distribution="weft-retrieve",
                    package="weft_retrieve",
                    resource="pipelines/no-retrieval.yaml",
                ),
            ),
        ),
    )


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


async def test_run_routed_ask_selects_and_executes_the_only_routable_pipeline() -> None:
    # Arrange — `no-retrieval` is the single candidate `route.yaml` can select once
    # loaded from these two real resources, so `nearest-description`'s own embedding
    # argmax has exactly one thing to be nearest to.

    # Act
    pipeline_name, answer = await run_routed_ask(
        "what happens if a store advertises no capability at all?",
        registry=_registry(),
        reports=_reports(),
        ctx=_ctx(),
        llm=_llm(),
        services=ServiceSelection(embed="fake-embed", store="fake-store"),
    )

    # Assert
    assert pipeline_name == "no-retrieval"
    assert isinstance(answer, Answer)


async def test_run_routed_ask_raises_when_no_pack_contributed_a_router() -> None:
    # Arrange — an empty report set: no installed pack ships `route.yaml` at all.

    # Act / Assert
    with pytest.raises(NoRouterPipelineError, match="route"):
        await run_routed_ask(
            "anything",
            registry=_registry(),
            reports=(),
            ctx=_ctx(),
            llm=_llm(),
            services=ServiceSelection(embed="fake-embed", store="fake-store"),
        )
