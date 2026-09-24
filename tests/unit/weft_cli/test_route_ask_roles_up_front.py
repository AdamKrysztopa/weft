"""Repair **R43.30**: a routed `weft ask` offers only the rungs whose roles are all mapped.

Found by `43.24`'s exit from the built wheel: with only `index` and `generate` mapped, a routed
ask refused naming `route`; once `route` was mapped it paid for the router's call and then
refused naming `grade`. Settled remedy: only the router's own role is refused up front; a rung
needing an unmapped role — on a stage, or on a sub-plugin named through an `X`/`X_config` pair —
is left out the way a rung on a pending layer is, and `--explain` says which role it needs.
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator, Callable, Mapping
from pathlib import Path
from typing import Annotated, ClassVar

import pytest
import yaml
from pydantic import BaseModel, ConfigDict, Field

from tests.discovery import installed_packs_except_the_canary
from weft_cli import commands
from weft_cli.commands import AskCommandResult
from weft_cli.exit_codes import ExitCode
from weft_cli.pipeline_catalogue import load_contributed
from weft_cli.render import render_refusal
from weft_cli.route_ask import routable_rung_roles, run_named_ask, run_routed_ask
from weft_embed import Embedder
from weft_embed.hash_embedder import HashEmbedder
from weft_engine.llm_roles import LLMSection
from weft_engine.registry_bootstrap import Dependencies
from weft_engine.services import ServiceSelection
from weft_generate import CitedAnswer, Generator
from weft_generate.payload import Answer, AnswerStance
from weft_generate.prompts import ANSWER_WITH_CITATIONS_NAME, AnswerWithCitationsPrompt
from weft_kernel.context import Context, ServiceRegistry
from weft_kernel.discovery import PackReport, PackStatus, PipelineResource, discover
from weft_kernel.errors import WeftError
from weft_kernel.payload import MediaType, Node, Outcome, Produced
from weft_kernel.registry import Registry
from weft_llm import LLMRole
from weft_llm.client import NullSink
from weft_llm.contract import LLM, LLMProvider
from weft_llm.payload import Completion, Conversation, Message, MessageRole, Rendered
from weft_llm.roles import LLMRoles, RoleMapping, UnmappedLLMRoleError
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
    SubPlugin,
)
from weft_retrieve.contract import Reranker, Sufficiency
from weft_retrieve.engine import UnknownSubPluginConfigFieldError
from weft_retrieve.graded import NAME as GRADED_RETRIEVAL
from weft_retrieve.graded import GradedRetrieval
from weft_retrieve.iterative import NAME as ITERATIVE_RETRIEVAL
from weft_retrieve.iterative import IterativeRetrieval
from weft_retrieve.multi_retriever import NAME as MULTI_RETRIEVER
from weft_retrieve.multi_retriever import MultiRetriever
from weft_retrieve.payload import Candidates, Passage, Query, QuerySet, RankedList, Ranking
from weft_retrieve.prompts import (
    RELEVANCE_GRADE_NAME,
    SUFFICIENCY_CHECK_NAME,
    RelevanceGradePrompt,
    SufficiencyCheckPrompt,
)
from weft_retrieve.sufficiency import LLM_SUFFICIENCY_NAME, LlmSufficiency
from weft_store import NodeStore
from weft_store.contract import Scored
from weft_store.memory import MemoryStore

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
_REPLIES = {
    "scores": _SCORES_JSON,
    "grades": '{"grades": [{"index": 0, "grade": "relevant"}]}',
    "answers": "The store refuses the pipeline [1].",
}

_QUESTION = "what happens if a store advertises no capability at all?"
_GRADED_RUNG = "graded-rung"
_LOOPING_RUNG = "looping-rung"
_MEMORY_RUNG = "no-retrieval"

type Calls = list[tuple[str, str]]


class _CountingProvider(ScriptedProvider):
    """`scripted`, recording each call's provider name and prompt into one shared list."""

    def __init__(self, name: str, calls: Calls) -> None:
        super().__init__(ScriptedConfig(reply=_REPLIES[name]))
        self._name = name
        self._calls = calls

    def _record(self, conv: Conversation) -> None:
        self._calls.append((self._name, "\n".join(m.content for m in conv.messages)))

    async def complete(
        self, conv: Conversation, *, model: str, ctx: Context
    ) -> Outcome[Completion]:
        self._record(conv)
        return await super().complete(conv, model=model, ctx=ctx)

    async def stream(self, conv: Conversation, *, model: str, ctx: Context) -> AsyncIterator[str]:
        self._record(conv)
        async for chunk in super().stream(conv, model=model, ctx=ctx):
            yield chunk


class _OneHit:
    """A `Retriever` that finds one passage, so a grading stage has something to grade."""

    def __init__(self, config: object = None) -> None:
        del config

    async def run(self, payload: QuerySet, ctx: Context) -> Outcome[Candidates]:
        del ctx
        node = Node.synthetic(
            content="A store with no capability is refused.",
            media_type=MediaType.TEXT,
            reason="fixture",
        )
        hit = Passage(scored=Scored(value=node, score=0.9), rank=0, retrieved_by="one-hit")
        ranked = RankedList(query=payload.origin, retriever="one-hit", hits=(hit,))
        return Produced(value=Candidates(origin=payload.origin, lists=(ranked,)))


def _counting(name: str, calls: Calls) -> Callable[[object], _CountingProvider]:
    def factory(config: object) -> _CountingProvider:
        del config
        return _CountingProvider(name, calls)

    return factory


def _memory_store(config: object) -> MemoryStore:
    del config
    return MemoryStore()


def _registry(calls: Calls) -> Registry:
    registry = Registry()
    for name in _REPLIES:
        registry.add(LLMProvider, name, _counting(name, calls), distribution="weft-llm")
    registry.add(NodeStore, "memory", _memory_store, distribution="weft-store")
    registry.add(Embedder, "hash", HashEmbedder, distribution="weft-embed")
    registry.add(Retriever, "no-retrieval", NoRetrieval, distribution="weft-retrieve")
    registry.add(Retriever, "one-hit", _OneHit, distribution="weft-retrieve")
    registry.add(Retriever, ITERATIVE_RETRIEVAL, IterativeRetrieval, distribution="weft-retrieve")
    registry.add(Sufficiency, LLM_SUFFICIENCY_NAME, LlmSufficiency, distribution="weft-retrieve")
    registry.add(Fuser, "single-list", SingleList, distribution="weft-retrieve")
    registry.add(Reranker, GRADED_RETRIEVAL, GradedRetrieval, distribution="weft-retrieve")
    registry.add(ContextPacker, "repack", Repack, distribution="weft-retrieve")
    registry.add(Generator, "cited-answer", CitedAnswer, distribution="weft-generate")
    registry.add(QueryScorer, "query-scorer", LlmQueryScorer, distribution="weft-retrieve")
    registry.add(
        RoutingPolicy, "nearest-description", NearestDescription, distribution="weft-retrieve"
    )
    registry.add(Prompt, ROUTE_QUERY_NAME, RouteQueryPrompt, distribution="weft-retrieve")
    registry.add(Prompt, RELEVANCE_GRADE_NAME, RelevanceGradePrompt, distribution="weft-retrieve")
    registry.add(
        Prompt, SUFFICIENCY_CHECK_NAME, SufficiencyCheckPrompt, distribution="weft-retrieve"
    )
    registry.add(
        Prompt, ANSWER_WITH_CITATIONS_NAME, AnswerWithCitationsPrompt, distribution="weft-generate"
    )
    return registry


def _reports(*resources: str) -> tuple[PackReport, ...]:
    return (
        PackReport(
            pack="retrieve",
            distribution="weft-retrieve",
            status=PackStatus.ACTIVE,
            pipeline_resources=tuple(
                PipelineResource(
                    distribution="weft-retrieve",
                    package="weft_retrieve",
                    resource=f"pipelines/{resource}",
                )
                for resource in resources
            ),
        ),
    )


_ROUTER_AND_MEMORY = ("route.yaml", f"{_MEMORY_RUNG}.yaml")


def _write_rungs(root: Path) -> None:
    """Two rungs whose summary is the question itself, so `nearest-description` prefers them."""
    pipelines = root / "pipelines"
    pipelines.mkdir()
    graded = {
        "name": _GRADED_RUNG,
        "vars": {"route.summary": _QUESTION},
        "stages": [
            {"id": "retrieve", "use": "one-hit"},
            {"id": "fuse", "use": "single-list"},
            {"id": "grade", "use": GRADED_RETRIEVAL},
            {"id": "pack", "use": "repack"},
            {"id": "generate", "use": "cited-answer"},
        ],
    }
    looping = {
        "name": _LOOPING_RUNG,
        "vars": {"route.summary": _QUESTION},
        "stages": [
            {
                "id": "retrieve",
                "use": ITERATIVE_RETRIEVAL,
                "with": {"sufficiency": LLM_SUFFICIENCY_NAME, "leaf": "one-hit"},
            },
            {"id": "fuse", "use": "single-list"},
            {"id": "pack", "use": "repack"},
            {"id": "generate", "use": "cited-answer"},
        ],
    }
    for document in (graded, looping):
        (pipelines / f"{document['name']}.yaml").write_text(
            yaml.safe_dump(document, sort_keys=False)
        )


def _ctx() -> Context:
    return Context(
        tenant_id="t", run_id="r", trace_id="tr", locale="en", services=ServiceRegistry()
    )


def _llm(**roles: str) -> LLMSection:
    return LLMSection(
        roles=LLMRoles(
            roles={role: RoleMapping(provider=provider) for role, provider in roles.items()}
        )
    )


def _names(message: str, word: str) -> bool:
    return re.search(rf"\b{re.escape(word)}\b", message) is not None


async def _routed(calls: Calls, llm: LLMSection) -> tuple[str, Answer]:
    return await run_routed_ask(
        _QUESTION,
        registry=_registry(calls),
        reports=_reports(*_ROUTER_AND_MEMORY),
        ctx=_ctx(),
        llm=llm,
        services=ServiceSelection(embed="hash", store="memory"),
        sink=NullSink(),
    )


async def test_an_unmapped_router_role_is_refused_before_any_model_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange — the measured configuration: only `index` and `generate` mapped.
    monkeypatch.chdir(tmp_path)
    _write_rungs(tmp_path)
    calls: Calls = []

    # Act
    with pytest.raises(UnmappedLLMRoleError) as raised:
        await _routed(calls, _llm(index="answers", generate="answers"))

    # Assert
    assert _names(str(raised.value), "route"), str(raised.value)
    assert raised.value.valid_options == ("generate", "index")
    assert calls == []


async def test_a_rung_whose_stage_role_is_unmapped_is_not_offered(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange — `grade` unmapped; the looping rung is removed so only a stage's own role counts.
    monkeypatch.chdir(tmp_path)
    _write_rungs(tmp_path)
    (tmp_path / "pipelines" / f"{_LOOPING_RUNG}.yaml").unlink()
    calls: Calls = []

    # Act
    pipeline_name, answer = await _routed(calls, _llm(route="scores", generate="answers"))

    # Assert
    assert pipeline_name == _MEMORY_RUNG
    assert isinstance(answer, Answer)
    assert [provider for provider, _ in calls] == ["scores", "answers"]
    assert _GRADED_RUNG not in calls[0][1]


async def test_a_rung_whose_sub_plugin_role_is_unmapped_is_not_offered(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange — `llm-sufficiency`, named by `iterative-retrieval`'s `sufficiency` field, needs
    # `grade` by default; the graded rung is removed so only the sub-plugin's role counts.
    monkeypatch.chdir(tmp_path)
    _write_rungs(tmp_path)
    (tmp_path / "pipelines" / f"{_GRADED_RUNG}.yaml").unlink()
    calls: Calls = []

    # Act
    pipeline_name, _answer = await _routed(calls, _llm(route="scores", generate="answers"))

    # Assert
    assert pipeline_name == _MEMORY_RUNG
    assert [provider for provider, _ in calls] == ["scores", "answers"]
    assert _LOOPING_RUNG not in calls[0][1]


async def test_with_no_rung_left_to_offer_the_refusal_names_the_missing_role(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange — the two grade-needing rungs are the only candidates.
    monkeypatch.chdir(tmp_path)
    _write_rungs(tmp_path)
    calls: Calls = []

    # Act
    with pytest.raises(WeftError) as raised:
        await run_routed_ask(
            _QUESTION,
            registry=_registry(calls),
            reports=_reports("route.yaml"),
            ctx=_ctx(),
            llm=_llm(route="scores", generate="answers"),
            services=ServiceSelection(embed="hash", store="memory"),
            sink=NullSink(),
        )

    # Assert
    assert _names(str(raised.value), "grade"), str(raised.value)
    assert calls == []


async def test_a_routed_ask_with_every_role_mapped_offers_and_runs_the_graded_rung(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    monkeypatch.chdir(tmp_path)
    _write_rungs(tmp_path)
    (tmp_path / "pipelines" / f"{_LOOPING_RUNG}.yaml").unlink()
    calls: Calls = []

    # Act
    pipeline_name, answer = await _routed(
        calls, _llm(route="scores", grade="grades", generate="answers")
    )

    # Assert
    assert pipeline_name == _GRADED_RUNG
    assert isinstance(answer, Answer)
    assert [provider for provider, _ in calls] == ["scores", "grades", "answers"]


async def test_a_named_ask_needing_only_generate_is_not_refused_for_router_or_rung_roles(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange — the router and both grade-needing rungs are in the catalogue; none is asked for.
    monkeypatch.chdir(tmp_path)
    _write_rungs(tmp_path)
    calls: Calls = []

    # Act
    answer = await run_named_ask(
        _QUESTION,
        pipeline_name=_MEMORY_RUNG,
        registry=_registry(calls),
        reports=_reports(*_ROUTER_AND_MEMORY),
        ctx=_ctx(),
        llm=_llm(generate="answers"),
        services=ServiceSelection(embed="hash", store="memory"),
        sink=NullSink(),
    )

    # Assert
    assert isinstance(answer, Answer)
    assert [provider for provider, _ in calls] == ["answers"]


class _Routed:
    async def __call__(self, *_args: object, **_kwargs: object) -> tuple[str, Answer]:
        return _MEMORY_RUNG, Answer(
            origin=Query(text=_QUESTION),
            text="the answer",
            stance=AnswerStance.ANSWERED,
            citations=(),
            used=(),
            answered_by="scripted",
        )


async def test_explain_names_each_rung_left_out_and_the_role_it_needs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    monkeypatch.chdir(tmp_path)
    _write_rungs(tmp_path)
    monkeypatch.setattr(commands, "run_routed_ask", _Routed())
    deps = Dependencies(
        registry=_registry([]),
        reports=_reports(*_ROUTER_AND_MEMORY),
        services=ServiceSelection(embed="hash", store="memory"),
        llm=_llm(route="scores", generate="answers"),
    )
    ctx = _ctx()
    ctx.services.add(Dependencies, deps)

    # Act
    outcome = await commands.AskCommand().run(
        commands.AskArgs(question=_QUESTION, explain=True), ctx
    )

    # Assert
    assert isinstance(outcome, Produced)
    result = outcome.value
    assert isinstance(result, AskCommandResult)
    assert f"not offered: '{_GRADED_RUNG}' needs role 'grade'" in result.explanations
    assert f"not offered: '{_LOOPING_RUNG}' needs role 'grade'" in result.explanations
    assert not any(f"'{_MEMORY_RUNG}'" in line for line in result.explanations)


_JUDGE_RUNG = "judge-rung"
_STRANGER_JUDGE = "stranger-judge"


class _StrangerJudgeConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    judge_role: Annotated[str, LLMRole()] = Field(default="judge", min_length=1)


class _StrangerJudge:
    """A third party's `Reranker` calling a model under a role field no first-party plugin names."""

    config_model: ClassVar[type[_StrangerJudgeConfig]] = _StrangerJudgeConfig

    def __init__(self, config: _StrangerJudgeConfig | None = None) -> None:
        self._config = config if config is not None else _StrangerJudgeConfig()

    async def run(self, payload: Ranking, ctx: Context) -> Outcome[Ranking]:
        llm = ctx.require(LLM)
        for hit in payload.hits:
            ask = Message(role=MessageRole.USER, content=hit.node.content)
            rendered = Rendered(conversation=Conversation(messages=(ask,)))
            judged = await llm.complete(rendered, role=self._config.judge_role, ctx=ctx)
            if not isinstance(judged, Produced):
                return judged
        return Produced(value=payload)


def _registry_with_stranger(calls: Calls) -> Registry:
    registry = _registry(calls)
    registry.add(Reranker, _STRANGER_JUDGE, _StrangerJudge, distribution="weft-example-stranger")
    return registry


def _write_judge_rung(root: Path, config: dict[str, object] | None = None) -> None:
    pipelines = root / "pipelines"
    pipelines.mkdir()
    rerank: dict[str, object] = {"id": "rerank", "use": _STRANGER_JUDGE}
    if config is not None:
        rerank["with"] = config
    document = {
        "name": _JUDGE_RUNG,
        "vars": {"route.summary": _QUESTION},
        "stages": [
            {"id": "retrieve", "use": "one-hit"},
            {"id": "fuse", "use": "single-list"},
            rerank,
            {"id": "pack", "use": "repack"},
            {"id": "generate", "use": "cited-answer"},
        ],
    }
    (pipelines / f"{_JUDGE_RUNG}.yaml").write_text(yaml.safe_dump(document, sort_keys=False))


async def test_a_rung_whose_stranger_role_field_is_unmapped_is_not_offered(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R43.35: a stranger's `judge_role`, declared with `LLMRole`, is filtered before any call."""
    # Arrange
    monkeypatch.chdir(tmp_path)
    _write_judge_rung(tmp_path)
    calls: Calls = []

    # Act
    pipeline_name, answer = await run_routed_ask(
        _QUESTION,
        registry=_registry_with_stranger(calls),
        reports=_reports(*_ROUTER_AND_MEMORY),
        ctx=_ctx(),
        llm=_llm(route="scores", generate="answers"),
        services=ServiceSelection(embed="hash", store="memory"),
        sink=NullSink(),
    )

    # Assert
    assert pipeline_name == _MEMORY_RUNG
    assert isinstance(answer, Answer)
    assert [provider for provider, _ in calls] == ["scores", "answers"]
    assert _JUDGE_RUNG not in calls[0][1]


async def test_explain_names_a_stranger_rung_and_the_role_its_config_sets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R43.35: the role checked is the one the rung's `with:` sets, not the field's default."""
    # Arrange
    monkeypatch.chdir(tmp_path)
    _write_judge_rung(tmp_path, {"judge_role": "critic"})
    monkeypatch.setattr(commands, "run_routed_ask", _Routed())
    deps = Dependencies(
        registry=_registry_with_stranger([]),
        reports=_reports(*_ROUTER_AND_MEMORY),
        services=ServiceSelection(embed="hash", store="memory"),
        llm=_llm(route="scores", judge="grades", generate="answers"),
    )
    ctx = _ctx()
    ctx.services.add(Dependencies, deps)

    # Act
    outcome = await commands.AskCommand().run(
        commands.AskArgs(question=_QUESTION, explain=True), ctx
    )

    # Assert
    assert isinstance(outcome, Produced)
    result = outcome.value
    assert isinstance(result, AskCommandResult)
    assert f"not offered: '{_JUDGE_RUNG}' needs role 'critic'" in result.explanations
    assert not any("needs role 'judge'" in line for line in result.explanations)


_FANOUT_RUNG = "fanout-rung"


def _registry_with_multi_retriever(calls: Calls) -> Registry:
    registry = _registry(calls)
    registry.add(Retriever, MULTI_RETRIEVER, MultiRetriever, distribution="weft-retrieve")
    return registry


def _write_fanout_rung(root: Path, sufficiency_config: dict[str, object] | None = None) -> None:
    """The shipped `broad-and-refined-rrf` shape: a plain arm beside a looping one."""
    refined: dict[str, object] = {"sufficiency": LLM_SUFFICIENCY_NAME, "leaf": "one-hit"}
    if sufficiency_config is not None:
        refined["sufficiency_config"] = sufficiency_config
    pipelines = root / "pipelines"
    pipelines.mkdir()
    document = {
        "name": _FANOUT_RUNG,
        "vars": {"route.summary": _QUESTION},
        "stages": [
            {
                "id": "retrieve",
                "use": MULTI_RETRIEVER,
                "with": {
                    "arms": [
                        {"name": "broad", "use": "one-hit"},
                        {"name": "refined", "use": ITERATIVE_RETRIEVAL, "config": refined},
                    ]
                },
            },
            {"id": "fuse", "use": "single-list"},
            {"id": "pack", "use": "repack"},
            {"id": "generate", "use": "cited-answer"},
        ],
    }
    (pipelines / f"{_FANOUT_RUNG}.yaml").write_text(yaml.safe_dump(document, sort_keys=False))


async def test_a_rung_whose_multi_retriever_arm_role_is_unmapped_is_not_offered(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R43.42: an arm's sub-plugin role is filtered before the router's call, not after it."""
    # Arrange
    monkeypatch.chdir(tmp_path)
    _write_fanout_rung(tmp_path)
    calls: Calls = []

    # Act
    pipeline_name, answer = await run_routed_ask(
        _QUESTION,
        registry=_registry_with_multi_retriever(calls),
        reports=_reports(*_ROUTER_AND_MEMORY),
        ctx=_ctx(),
        llm=_llm(route="scores", generate="answers"),
        services=ServiceSelection(embed="hash", store="memory"),
        sink=NullSink(),
    )

    # Assert
    assert pipeline_name == _MEMORY_RUNG
    assert isinstance(answer, Answer)
    assert [provider for provider, _ in calls] == ["scores", "answers"]
    assert _FANOUT_RUNG not in calls[0][1]


async def test_explain_names_a_multi_retriever_rung_and_the_role_its_arm_sets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R43.42: the role checked is the one the arm's own nested config sets, two levels down."""
    # Arrange
    monkeypatch.chdir(tmp_path)
    _write_fanout_rung(tmp_path, {"role": "critic"})
    monkeypatch.setattr(commands, "run_routed_ask", _Routed())
    deps = Dependencies(
        registry=_registry_with_multi_retriever([]),
        reports=_reports(*_ROUTER_AND_MEMORY),
        services=ServiceSelection(embed="hash", store="memory"),
        llm=_llm(route="scores", grade="grades", generate="answers"),
    )
    ctx = _ctx()
    ctx.services.add(Dependencies, deps)

    # Act
    outcome = await commands.AskCommand().run(
        commands.AskArgs(question=_QUESTION, explain=True), ctx
    )

    # Assert
    assert isinstance(outcome, Produced)
    result = outcome.value
    assert isinstance(result, AskCommandResult)
    assert f"not offered: '{_FANOUT_RUNG}' needs role 'critic'" in result.explanations
    assert not any("needs role 'grade'" in line for line in result.explanations)


_SHIPPED_FANOUT_RUNG = "broad-and-refined-rrf"


def test_the_shipped_fanout_rung_needs_the_role_its_looping_arm_calls() -> None:
    """R43.42, measured on the shipped catalogue: `broad-and-refined-rrf`'s `refined` arm runs
    `iterative-retrieval` with `llm-sufficiency`, which calls a model under `grade`."""
    # Arrange
    registry = Registry()
    reports = discover(
        registry,
        allow=installed_packs_except_the_canary(),
        pack_settings={
            "store": {"dsn": "postgresql://tests-route-ask/placeholder"},
            "blob": {"root": "/nonexistent-tests-route-ask-blob-root"},
        },
    )

    # Act
    rung_roles = routable_rung_roles(load_contributed(reports), registry=registry, reports=reports)

    # Assert
    assert rung_roles[_SHIPPED_FANOUT_RUNG] >= {"grade", "generate"}


_MISDECLARED_RUNG = "misdeclared-rung"
_MISDECLARED_PANEL = "stranger-misdeclared-panel"


class _MisdeclaredPanelConfig(BaseModel):
    """R43.45: a stranger's reference whose `SubPlugin.config` names no field of this model."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    panelist: Annotated[str, SubPlugin(config="setings")] = Field(min_length=1)
    settings: Mapping[str, object] | None = None


class _MisdeclaredPanel:
    config_model: ClassVar[type[_MisdeclaredPanelConfig]] = _MisdeclaredPanelConfig

    def __init__(self, config: _MisdeclaredPanelConfig) -> None:
        self._config = config

    async def run(self, payload: Ranking, ctx: Context) -> Outcome[Ranking]:
        del ctx
        return Produced(value=payload)


def _registry_with_misdeclared_panel(calls: Calls) -> Registry:
    registry = _registry_with_stranger(calls)
    registry.add(
        Reranker, _MISDECLARED_PANEL, _MisdeclaredPanel, distribution="weft-example-stranger"
    )
    return registry


def _write_misdeclared_rung(root: Path) -> None:
    pipelines = root / "pipelines"
    pipelines.mkdir()
    document = {
        "name": _MISDECLARED_RUNG,
        "vars": {"route.summary": _QUESTION},
        "stages": [
            {"id": "retrieve", "use": "one-hit"},
            {"id": "fuse", "use": "single-list"},
            {"id": "rerank", "use": _MISDECLARED_PANEL, "with": {"panelist": _STRANGER_JUDGE}},
            {"id": "pack", "use": "repack"},
            {"id": "generate", "use": "cited-answer"},
        ],
    }
    (pipelines / f"{_MISDECLARED_RUNG}.yaml").write_text(yaml.safe_dump(document, sort_keys=False))


def _assert_the_refusal_an_operator_reads(refusal: UnknownSubPluginConfigFieldError) -> None:
    rendered = render_refusal(refusal)
    stderr = rendered.stderr or ""
    assert rendered.exit_code is ExitCode.RESOLUTION_FAILED
    assert f"'{_MISDECLARED_RUNG}'" in stderr, stderr
    assert f"{_MisdeclaredPanelConfig.__name__}.panelist" in stderr, stderr
    assert "'setings'" in stderr, stderr
    assert _names(stderr, "settings"), stderr
    assert refusal.valid_options == ("panelist", "settings")


async def test_a_routed_ask_over_a_misdeclared_sub_plugin_is_refused_before_any_model_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R43.45: the walk cannot compute the rung's roles, so it refuses before the router pays."""
    # Arrange — every role mapped, so nothing but the declaration can stop the ask.
    monkeypatch.chdir(tmp_path)
    _write_misdeclared_rung(tmp_path)
    calls: Calls = []

    # Act
    with pytest.raises(UnknownSubPluginConfigFieldError) as refused:
        await run_routed_ask(
            _QUESTION,
            registry=_registry_with_misdeclared_panel(calls),
            reports=_reports(*_ROUTER_AND_MEMORY),
            ctx=_ctx(),
            llm=_llm(route="scores", judge="grades", generate="answers"),
            services=ServiceSelection(embed="hash", store="memory"),
            sink=NullSink(),
        )

    # Assert
    _assert_the_refusal_an_operator_reads(refused.value)
    assert calls == []


async def test_explain_over_a_misdeclared_sub_plugin_is_refused_naming_the_fields(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    monkeypatch.chdir(tmp_path)
    _write_misdeclared_rung(tmp_path)
    monkeypatch.setattr(commands, "run_routed_ask", _Routed())
    deps = Dependencies(
        registry=_registry_with_misdeclared_panel([]),
        reports=_reports(*_ROUTER_AND_MEMORY),
        services=ServiceSelection(embed="hash", store="memory"),
        llm=_llm(route="scores", judge="grades", generate="answers"),
    )
    ctx = _ctx()
    ctx.services.add(Dependencies, deps)

    # Act
    with pytest.raises(UnknownSubPluginConfigFieldError) as refused:
        await commands.AskCommand().run(commands.AskArgs(question=_QUESTION, explain=True), ctx)

    # Assert
    _assert_the_refusal_an_operator_reads(refused.value)
