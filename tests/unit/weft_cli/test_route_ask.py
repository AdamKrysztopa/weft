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

Task **3.6** adds one more: proof that `sink` genuinely reaches the generating stage
through this module's own `build_services` call, end to end through the real pipeline
machinery above — not a fake standing in for `weft_llm.client.LLMClient`.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest
import yaml

from weft_cli.llm_roles import LLMSection
from weft_cli.pipeline_catalogue import full_catalogue
from weft_cli.registry_bootstrap import build_dependencies
from weft_cli.route_ask import (
    NoRouterPipelineError,
    pipelines_producing,
    run_named_ask,
    run_routed_ask,
)
from weft_cli.services import ServiceSelection
from weft_embed import Embedder
from weft_embed.hash_embedder import HashEmbedder
from weft_generate import CitedAnswer, Generator
from weft_generate.payload import Answer
from weft_generate.prompts import ANSWER_WITH_CITATIONS_NAME, AnswerWithCitationsPrompt
from weft_kernel.context import Context, ServiceRegistry
from weft_kernel.discovery import PackReport, PackStatus, PipelineResource
from weft_kernel.payload import Outcome, Produced
from weft_kernel.pipeline import StageDeclaration
from weft_kernel.registry import Registry
from weft_kernel.resolution import Contribution
from weft_llm.client import NullSink
from weft_llm.contract import LLMProvider
from weft_llm.payload import TokenChunk
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
from weft_retrieve.contract import QueryTransform
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
            pack="retrieve",
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
        sink=NullSink(),
    )

    # Assert
    assert pipeline_name == "no-retrieval"
    assert isinstance(answer, Answer)


class _RecordingSink:
    """A `TokenSink` that keeps everything it saw — no filtering, no printing — so a test
    can inspect exactly what `weft_llm.client.LLMClient.complete` emitted, tagged by role.
    """

    def __init__(self) -> None:
        self.chunks: list[TokenChunk] = []
        self.closed_with: list[str | None] = []

    async def emit(self, chunk: TokenChunk) -> None:
        self.chunks.append(chunk)

    async def close(self, *, reason: str | None = None) -> None:
        self.closed_with.append(reason)


async def test_run_routed_ask_streams_generation_tokens_into_the_caller_s_sink() -> None:
    # Arrange — task 3.6: `run_routed_ask`'s own `sink` parameter has to reach the real
    # generating stage, not merely be accepted and dropped.
    sink = _RecordingSink()

    # Act
    _pipeline_name, answer = await run_routed_ask(
        "what happens if a store advertises no capability at all?",
        registry=_registry(),
        reports=_reports(),
        ctx=_ctx(),
        llm=_llm(),
        services=ServiceSelection(embed="fake-embed", store="fake-store"),
        sink=sink,
    )

    # Assert — the `generate`-role chunks, rejoined in arrival order, are exactly the
    # `Answer.text` this same run produced; `weft_llm.client.LLMClient.complete` accumulates
    # and emits identically (task 2.10's own repair), so this is not a coincidence of the
    # fixture. `run_routed_ask` itself never closes the sink — that is `weft_cli.cli.
    # run_command`'s own job (task 3.6), proven by `closed_with` staying empty here.
    generated = "".join(chunk.text for chunk in sink.chunks if chunk.role == "generate")
    assert generated == answer.text
    assert sink.closed_with == []


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
            sink=NullSink(),
        )


async def test_run_named_ask_resolves_a_derived_pipeline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange — repair, task 4.6: `_run_pipeline` used to pass `resolve()` a one-entry
    # `parents` mapping holding only the named pipeline itself, so a document's own
    # `extends:` had no ancestor to find and every derived pipeline failed
    # `UnknownParentPipelineError` outright — found by running `weft eval run` over a
    # real `weft pipeline derive`d document. This is that defect's own regression test,
    # one layer down: `base.yaml` plus a `derived.yaml` that only says `extends: base`,
    # `weft pipeline derive`'s own minimal shape.
    monkeypatch.chdir(tmp_path)
    pipelines = tmp_path / "pipelines"
    pipelines.mkdir()
    base = {
        "name": "base",
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
    }
    (pipelines / "base.yaml").write_text(yaml.safe_dump(base, sort_keys=False))
    (pipelines / "derived.yaml").write_text(
        yaml.safe_dump({"name": "derived", "extends": "base"}, sort_keys=False)
    )

    # Act
    answer = await run_named_ask(
        "what happens if a store advertises no capability at all?",
        pipeline_name="derived",
        registry=_registry(),
        reports=(),
        ctx=_ctx(),
        llm=_llm(),
        services=ServiceSelection(embed="fake-embed", store="fake-store"),
        sink=NullSink(),
    )

    # Assert
    assert isinstance(answer, Answer)


async def test_run_named_ask_places_a_contribution_in_a_declared_slot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Task **5.3a** (`S8`): `contributions=` reaches `_run_pipeline`'s own `resolve()` call
    for a directly-named pipeline, exactly as it does for `weft_cli.ingest.run_index`'s
    `--pipeline` path — a pack's own `Contribution` lands in a slot the document opted into
    and its stage actually runs, never merely resolves.
    """
    # Arrange — a `QueryTransform` composes cleanly either side of `retrieve`
    # (`Stage[QuerySet, QuerySet]`), so `before: "retrieve"` needs no bespoke contract.
    monkeypatch.chdir(tmp_path)
    pipelines = tmp_path / "pipelines"
    pipelines.mkdir()
    base = {
        "name": "base",
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
        "slots": [{"id": "enrich", "before": "retrieve"}],
    }
    (pipelines / "base.yaml").write_text(yaml.safe_dump(base, sort_keys=False))

    ran: list[str] = []

    class _NoOpTransform:
        def __init__(self, config: object = None) -> None:
            del config

        async def run(self, payload: object, ctx: Context) -> Outcome[object]:
            del ctx
            ran.append("enrich")
            return Produced(value=payload)

    registry = _registry()
    registry.add(QueryTransform, "noop-transform", _NoOpTransform, distribution="weft-graph")
    contribution = Contribution(
        slot="enrich",
        distribution="weft-graph",
        stage=StageDeclaration(id="noop", use="noop-transform"),
    )

    # Act
    answer = await run_named_ask(
        "why does this matter?",
        pipeline_name="base",
        registry=registry,
        reports=(),
        ctx=_ctx(),
        llm=_llm(),
        services=ServiceSelection(embed="fake-embed", store="fake-store"),
        sink=NullSink(),
        contributions=(contribution,),
    )

    # Assert
    assert isinstance(answer, Answer)
    assert ran == ["enrich"]


# ---------------------------------------------------------------------------
# Task 6.32 — the refusal names which pipelines would produce the right shape.
# ---------------------------------------------------------------------------


def test_the_refusal_names_the_pipelines_that_do_produce_an_answer() -> None:
    """Requirement 5's third clause: say what the valid options are.

    **This asserts the list is non-empty against the real registry**, which is the assertion
    that was missing. The first draft asked the registry for `Answer` — a payload type nothing
    is registered under — got `()` back, and printed a refusal with no alternatives at all. An
    empty answer read as "there are none" when it meant "I asked the wrong question"
    (`docs/lessons.md` L5.9), and only running the binary showed it.
    """
    # Arrange — the real catalogue and the real registry, so a lookup asking the wrong
    # question cannot pass by having nothing to find.
    deps = build_dependencies(config_path=Path("weft.toml.does-not-exist"))
    catalogue = full_catalogue(reports=deps.reports)

    # Act
    producing = pipelines_producing(Generator, catalogue=catalogue, registry=deps.registry)

    # Assert
    assert producing, (
        "no shipped pipeline was found ending in a Generator, and `weft-retrieve` ships two. "
        "The lookup is asking the registry the wrong question — which is exactly how this "
        "shipped once, printing a refusal whose 'valid options' half was silently empty."
    )
    assert "retrieve-then-generate" in producing


def test_a_pipeline_that_ends_in_a_retriever_is_not_offered_as_an_alternative() -> None:
    """The other side: a list that offered everything would be worse than no list."""
    # Arrange
    deps = build_dependencies(config_path=Path("weft.toml.does-not-exist"))
    catalogue = full_catalogue(reports=deps.reports)

    # Act
    producing = pipelines_producing(Generator, catalogue=catalogue, registry=deps.registry)

    # Assert
    assert "route" not in producing, (
        "`route` ends in a RoutingPolicy and produces a Route, so offering it to somebody who "
        "needs an Answer would send them straight back to this same refusal"
    )
