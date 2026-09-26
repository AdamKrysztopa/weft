"""`weft ask --pipeline whole-corpus-then-generate` — ledger task **43.49**.

The shipped document is `whole-corpus` → `single-list` → `repack` → `cited-answer`. `cited-answer`
reads `Passages`, so a packer has to stand between fusion and generation; it is configured so it
neither cuts nor reorders, and `cited-answer`'s `max_passages: null` (43.48) offers every passage.
The document carries no `route.summary`, so the router never offers it: which questions it should
answer is decided after Phase 43d's measurement, and until then it is reached by name alone.

The registry is the real one discovery builds, so the plugin's registration and the document's
contribution are both what an installed wheel does; only the store and the model are doubles.
"""

from collections.abc import AsyncIterator, Callable
from pathlib import Path

import pytest

from tests.unit.weft_retrieve.leaf_corpus import corpus, stored
from weft_cli.exit_codes import ExitCode
from weft_cli.pipeline_catalogue import full_catalogue
from weft_cli.render import render_refusal
from weft_cli.route_ask import resolve_named_pipeline, run_named_ask
from weft_engine import registry_bootstrap
from weft_engine.llm_roles import LLMSection
from weft_engine.registry_bootstrap import Dependencies
from weft_engine.run_services import StoreCapabilityMissingError
from weft_engine.services import ServiceSelection
from weft_generate.payload import Answer
from weft_kernel.context import Context, ServiceRegistry
from weft_kernel.payload import Outcome
from weft_llm.client import NullSink
from weft_llm.contract import LLMProvider
from weft_llm.payload import Completion, Conversation
from weft_llm.roles import LLMRoles, RoleMapping
from weft_llm.scripted import ScriptedConfig, ScriptedProvider
from weft_retrieve.engine import PipelineRouteCatalogue
from weft_retrieve.repack import RepackMethod
from weft_store.contract import MetadataFilter, NodeStore
from weft_store.memory import MemoryStore

_NAME = "whole-corpus-then-generate"
_QUESTION = "what did the Curies find?"
_READER = "reading"


class _ReadingProvider(ScriptedProvider):
    """`scripted`, recording every prompt it is sent and counting one token per word."""

    def __init__(self, prompts: list[str]) -> None:
        super().__init__(ScriptedConfig(reply="Polonium, then radium [1]."))
        self._prompts = prompts

    def _record(self, conv: Conversation) -> None:
        self._prompts.append("\n".join(message.content for message in conv.messages))

    async def complete(
        self, conv: Conversation, *, model: str, ctx: Context
    ) -> Outcome[Completion]:
        self._record(conv)
        return await super().complete(conv, model=model, ctx=ctx)

    async def stream(self, conv: Conversation, *, model: str, ctx: Context) -> AsyncIterator[str]:
        self._record(conv)
        async for chunk in super().stream(conv, model=model, ctx=ctx):
            yield chunk

    async def count_tokens(self, text: str, *, model: str) -> int | None:
        del model
        return len(text.split())


def _reading(prompts: list[str]) -> Callable[[object], _ReadingProvider]:
    def factory(config: object) -> _ReadingProvider:
        del config
        return _ReadingProvider(prompts)

    return factory


def _serving[T](store: T) -> Callable[[object], T]:
    def factory(config: object) -> T:
        del config
        return store

    return factory


def _deps(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Dependencies:
    monkeypatch.chdir(tmp_path)
    config = tmp_path / "weft.toml"
    config.write_text("", encoding="utf-8")
    return registry_bootstrap.build_dependencies(config_path=config)


def _ctx() -> Context:
    return Context(
        tenant_id="t", run_id="r", trace_id="tr", locale="en", services=ServiceRegistry()
    )


def _llm() -> LLMSection:
    return LLMSection(
        roles=LLMRoles(roles={"generate": RoleMapping(provider=_READER, model="counted")})
    )


def test_the_shipped_document_packs_every_leaf_in_order_and_offers_every_passage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    deps = _deps(tmp_path, monkeypatch)

    # Act
    stages = resolve_named_pipeline(_NAME, registry=deps.registry, reports=deps.reports).stages

    # Assert
    assert [stage.use for stage in stages] == [
        "whole-corpus",
        "single-list",
        "repack",
        "cited-answer",
    ]
    pack, generate = stages[2], stages[3]
    assert getattr(pack.config, "method", None) is RepackMethod.FORWARD
    assert getattr(pack.config, "top_n", "unset") is None
    assert getattr(pack.config, "budget_tokens", "unset") is None
    assert getattr(generate.config, "max_passages", "unset") is None


def test_the_router_never_offers_it_and_still_offers_a_retrieving_rung(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    deps = _deps(tmp_path, monkeypatch)
    catalogue = full_catalogue(reports=deps.reports)

    # Act
    offered = PipelineRouteCatalogue(catalogue).names()

    # Assert
    assert _NAME in catalogue
    assert "route.summary" not in catalogue[_NAME].vars
    assert _NAME not in offered
    assert "retrieve-then-generate" in offered


async def test_a_named_ask_offers_the_generator_every_leaf_in_source_then_ordinal_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange — fifteen leaves, past `cited-answer`'s default of eight.
    deps = _deps(tmp_path, monkeypatch)
    fixture = corpus()
    store = await stored(fixture)
    prompts: list[str] = []
    deps.registry.add(NodeStore, "leaves", _serving(store), distribution="weft-rag")
    deps.registry.add(LLMProvider, _READER, _reading(prompts), distribution="weft-rag")

    # Act
    answer = await run_named_ask(
        _QUESTION,
        pipeline_name=_NAME,
        registry=deps.registry,
        reports=deps.reports,
        ctx=_ctx(),
        llm=_llm(),
        services=ServiceSelection(embed="hash", store="leaves"),
        sink=NullSink(),
    )

    # Assert
    assert isinstance(answer, Answer)
    assert len(prompts) == 1
    prompt = prompts[0]
    positions = [prompt.find(leaf.content) for leaf in fixture.leaves]
    assert len(fixture.leaves) > 8
    assert all(position >= 0 for position in positions), positions
    assert positions == sorted(positions)
    assert not any(node.content in prompt for node in fixture.excluded)


async def test_a_store_that_cannot_filter_is_refused_by_name_before_any_model_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    deps = _deps(tmp_path, monkeypatch)
    prompts: list[str] = []
    deps.registry.add(NodeStore, "memory", _serving(MemoryStore()), distribution="weft-rag")
    deps.registry.add(LLMProvider, _READER, _reading(prompts), distribution="weft-rag")
    assert not isinstance(MemoryStore(), MetadataFilter)

    # Act
    with pytest.raises(StoreCapabilityMissingError) as refused:
        await run_named_ask(
            _QUESTION,
            pipeline_name=_NAME,
            registry=deps.registry,
            reports=deps.reports,
            ctx=_ctx(),
            llm=_llm(),
            services=ServiceSelection(embed="hash", store="memory"),
            sink=NullSink(),
        )

    # Assert
    rendered = render_refusal(refused.value)
    stderr = rendered.stderr or ""
    assert rendered.exit_code is ExitCode.RESOLUTION_FAILED
    assert "'whole-corpus'" in stderr, stderr
    assert "needs MetadataFilter from the store" in stderr, stderr
    assert prompts == []
