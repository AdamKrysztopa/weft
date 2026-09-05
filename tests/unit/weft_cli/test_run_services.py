"""Unit tests for `weft_cli.run_services`.

Mirrors `packages/weft-rag/src/weft_cli/run_services.py`. Task **2.5**: a stage
declaring what it needs from the store is checked against the store the run was
configured with, *before* the run starts. Covers the happy path (a retriever needing
vector and text search, against a store advertising both, and a stage that declares
nothing beside it), the error case that gives the check its point (the same retriever
against a store advertising only vector search — refused by name, naming what the store
does advertise and which registered store provides the rest), and the malformed
declaration a plugin author can write by accident.

The retrievers below are declared against the real `weft_retrieve.contract.Retriever` and
the real `weft_store` capability Protocols, because the property under test is exactly
that this check reads a *published* contract's declaration and derives a *published*
capability by `isinstance`. Fakes stand in for the stores themselves — the point being
demonstrated is capability, not Postgres, and a store fake with no `search_text` is the
one shape a container cannot provide.
"""

from __future__ import annotations

from collections.abc import Sequence
from functools import partial

import pytest
from pydantic import SecretStr

from weft_cli.llm_roles import LLMSection
from weft_cli.run_services import (
    MalformedNeedsStoreError,
    StoreCapabilityMissingError,
    build_services,
    check_store_capabilities,
)
from weft_cli.services import ServiceSelection
from weft_embed import Embedder
from weft_kernel.context import Context
from weft_kernel.payload import Node, Outcome, Produced, Vector
from weft_kernel.pipeline import Pipeline, StageDeclaration
from weft_kernel.registry import Registry, UnknownPluginError
from weft_kernel.runner import StageSpec
from weft_llm.client import NullSink
from weft_llm.contract import LLM, LLMProvider, TokenSink
from weft_llm.scripted import ScriptedProvider
from weft_prompts.contract import Prompts
from weft_retrieve import Candidates, QuerySet, Retriever
from weft_retrieve.contract import RouteCatalogue, StageLookup
from weft_store import Filter, NodeStore, Scored, TextSearch, VectorSearch
from weft_store.pgvector_store import PgVectorSettings, PgVectorStore


class _HybridRetriever:
    """Needs both search capabilities — the `hybrid` shape, without the retrieval."""

    needs_store: tuple[type, ...] = (VectorSearch, TextSearch)

    def __init__(self, config: object = None) -> None:
        del config

    async def run(self, payload: QuerySet, ctx: Context) -> Outcome[Candidates]:
        del ctx
        return Produced(value=Candidates(origin=payload.origin))


class _DenseRetriever:
    """Declares nothing: a plugin with no `needs_store` is not a plugin that needs nothing
    checked *badly*, it is one this check must pass over in silence.
    """

    def __init__(self, config: object = None) -> None:
        del config

    async def run(self, payload: QuerySet, ctx: Context) -> Outcome[Candidates]:
        del ctx
        return Produced(value=Candidates(origin=payload.origin))


class _MisdeclaringRetriever:
    """`needs_store` written as the *name* of a capability rather than the capability."""

    needs_store = "VectorSearch"

    def __init__(self, config: object = None) -> None:
        del config

    async def run(self, payload: QuerySet, ctx: Context) -> Outcome[Candidates]:
        del ctx
        return Produced(value=Candidates(origin=payload.origin))


class _VectorOnlyStore:
    """Advertises `VectorSearch` and nothing else — every store this tree had before 2.5."""

    async def search_vector(
        self, vector: Vector, top_k: int, filter: Filter | None = None
    ) -> Sequence[Scored[Node]]:
        return ()


class _HybridStore(_VectorOnlyStore):
    """Advertises both search capabilities, the way `PgVectorStore` now does."""

    async def search_text(
        self, text: str, top_k: int, filter: Filter | None = None
    ) -> Sequence[Scored[Node]]:
        return ()


def _registry() -> Registry:
    """A registry holding the two retrievers and the real pgvector registration.

    `PgVectorStore` is registered exactly the way its own pack registers it —
    `functools.partial` binding pack settings — because the remedy this check prints has
    to see through that wrapper to the class, and a bare class here would let the test
    pass with the unwrapping removed.
    """
    registry = Registry()
    registry.add(Retriever, "hybrid", _HybridRetriever, distribution="weft-test-pack")
    registry.add(Retriever, "vector-top-k", _DenseRetriever, distribution="weft-test-pack")
    registry.add(Retriever, "misdeclared", _MisdeclaringRetriever, distribution="weft-test-pack")
    settings = PgVectorSettings(dsn=SecretStr("postgresql://weft:weft@localhost:5433/weft"))
    registry.add(NodeStore, "pgvector", partial(PgVectorStore, settings), distribution="weft-store")
    return registry


def test_a_run_whose_stages_need_what_the_store_advertises_is_allowed() -> None:
    # Arrange
    specs = (
        StageSpec(id="retrieve", contract=Retriever, name="hybrid"),
        StageSpec(id="second", contract=Retriever, name="vector-top-k"),
    )

    # Act
    check_store_capabilities(
        specs,
        registry=_registry(),
        store=_HybridStore(),
        store_contract=NodeStore,
        store_name="fake-hybrid",
    )

    # Assert — no exception is the whole result: this check speaks only to refuse, and a
    # stage declaring no `needs_store` contributes nothing to refuse with.


def test_a_stage_needing_text_search_is_refused_against_a_store_without_it() -> None:
    # Arrange
    specs = (StageSpec(id="retrieve", contract=Retriever, name="hybrid"),)

    # Act
    with pytest.raises(StoreCapabilityMissingError) as caught:
        check_store_capabilities(
            specs,
            registry=_registry(),
            store=_VectorOnlyStore(),
            store_contract=NodeStore,
            store_name="fake-vector-only",
            pipeline="hybrid-search",
        )

    # Assert — what was wanted, what the store actually offers, and where to get the rest.
    message = str(caught.value)
    assert "TextSearch" in message
    assert "fake-vector-only" in message
    assert "VectorSearch" in message
    assert "pgvector" in message
    assert caught.value.stages == ("retrieve",)
    assert caught.value.pipeline == "hybrid-search"
    assert "weft-store" in caught.value.distributions


def test_a_fallback_needing_text_search_is_refused_against_a_store_without_it() -> None:
    """Repair for a reviewer finding: a fallback is a candidate that will actually run.

    `weft_kernel.runner.Runner._chain` already checks every fallback for existence *and*
    substitutability, precisely because `weft_kernel.fallback.try_in_order` runs it when the
    primary refuses. `needs_store` was the one declaration in that set left unchecked, so a
    chain whose *fallback* wanted text search passed assembly against a vector-only store and
    raised `AttributeError` mid-batch — after the run had already done work, from a bare
    non-`WeftError`, which is exactly what checking before any stage runs exists to prevent.
    """
    # Arrange — the primary needs nothing; the fallback needs both capabilities.
    specs = (
        StageSpec(id="retrieve", contract=Retriever, name="vector-top-k", fallback=("hybrid",)),
    )

    # Act
    with pytest.raises(StoreCapabilityMissingError) as caught:
        check_store_capabilities(
            specs,
            registry=_registry(),
            store=_VectorOnlyStore(),
            store_contract=NodeStore,
            store_name="fake-vector-only",
        )

    # Assert — the refusal names the candidate in the chain that cannot be served.
    message = str(caught.value)
    assert "hybrid" in message
    assert "fallback 1 of 1" in message
    assert "TextSearch" in message


def test_an_unregistered_fallback_name_is_left_to_the_runners_own_refusal() -> None:
    """A name no distribution registered has no declaration to read, and is not this check's.

    `Runner._chain` refuses it by name with `UnknownFallbackError`, naming its position in the
    chain and every name registered for the contract — so the pipeline is refused either way and
    nothing runs unchecked. Answering it a second time here, worse, would be the noise.
    """
    # Arrange
    specs = (
        StageSpec(
            id="retrieve", contract=Retriever, name="vector-top-k", fallback=("nobody-ships-this",)
        ),
    )

    # Act
    check_store_capabilities(
        specs,
        registry=_registry(),
        store=_VectorOnlyStore(),
        store_contract=NodeStore,
        store_name="fake-vector-only",
    )

    # Assert — no exception: existence is the runner's refusal, capability is this one's.


def test_a_needs_store_that_is_not_a_tuple_of_capabilities_is_refused_by_name() -> None:
    # Arrange
    specs = (StageSpec(id="retrieve", contract=Retriever, name="misdeclared"),)

    # Act / Assert — a declaration nobody can check is not quietly skipped: skipping it
    # would run the pipeline the declaration existed to stop.
    with pytest.raises(MalformedNeedsStoreError) as caught:
        check_store_capabilities(
            specs,
            registry=_registry(),
            store=_HybridStore(),
            store_contract=NodeStore,
            store_name="fake-hybrid",
        )
    assert "misdeclared" in str(caught.value)


# --- build_services (task 2.8) ---------------------------------------------------------


class _FakeStore:
    """A `NodeStore` stand-in — `build_services` never calls a method on it, only resolves
    the registered factory and hands the instance to the `ServiceRegistry`."""


class _FakeEmbedder:
    """An `Embedder` stand-in, on the identical footing as `_FakeStore` above."""


def _scripted_factory(config: object) -> ScriptedProvider:
    del config
    return ScriptedProvider()


def _fake_store_factory(config: object) -> _FakeStore:
    del config
    return _FakeStore()


def _fake_embedder_factory(config: object) -> _FakeEmbedder:
    del config
    return _FakeEmbedder()


def _services_registry() -> Registry:
    registry = Registry()
    registry.add(LLMProvider, "scripted", _scripted_factory, distribution="weft-llm")
    registry.add(NodeStore, "fake", _fake_store_factory, distribution="weft-store")
    registry.add(Embedder, "fake", _fake_embedder_factory, distribution="weft-embed")
    return registry


def _routable_catalogue() -> dict[str, Pipeline]:
    return {
        "retrieve-then-generate": Pipeline(
            name="retrieve-then-generate",
            vars={"route.summary": "one search, one answer"},
            stages=(StageDeclaration(id="s", use="vector-top-k"),),
        )
    }


async def test_build_services_populates_every_service_a_query_path_stage_may_require() -> None:
    # Arrange
    registry = _services_registry()

    # Act
    services = await build_services(
        registry=registry,
        catalogue=_routable_catalogue(),
        llm=LLMSection(),
        services=ServiceSelection(embed="fake", store="fake"),
        sink=NullSink(),
    )

    # Assert
    assert isinstance(services.resolve(TokenSink), NullSink)
    assert isinstance(services.resolve(NodeStore), _FakeStore)
    assert isinstance(services.resolve(Embedder), _FakeEmbedder)
    assert services.resolve(RouteCatalogue).names() == frozenset({"retrieve-then-generate"})
    assert services.resolve(StageLookup).names(NodeStore) == frozenset({"fake"})
    # LLM and Prompts are services this run may never call; presence, not behaviour, is
    # what a stage that never asks a model depends on — `services.resolve` not raising is
    # the whole assertion.
    services.resolve(LLM)
    services.resolve(Prompts)


async def test_build_services_registers_exactly_the_sink_the_caller_chose() -> None:
    # Arrange — task 3.6's own repair: `build_services` used to hardcode `NullSink()`
    # regardless of what a caller wanted; `docs/03-cli.md` -> *Output* (G6) makes the CLI
    # responsible for choosing, so this proves the *caller's* instance is what a stage
    # resolves, not merely that a `NullSink` still shows up by coincidence.
    registry = _services_registry()

    class _MarkedSink:
        async def emit(self, chunk: object) -> None:
            del chunk

        async def close(self, *, reason: str | None = None) -> None:
            del reason

    chosen = _MarkedSink()

    # Act
    services = await build_services(
        registry=registry,
        catalogue={},
        llm=LLMSection(),
        services=ServiceSelection(embed="fake", store="fake"),
        sink=chosen,
    )

    # Assert
    assert services.resolve(TokenSink) is chosen


async def test_build_services_route_catalogue_reflects_exactly_the_catalogue_handed_in() -> None:
    # Arrange — an empty catalogue is a legitimate run (no pipeline advertises route.summary
    # yet), and `RouteCatalogue.candidates()` must say so rather than inventing one.
    registry = _services_registry()

    # Act
    services = await build_services(
        registry=registry,
        catalogue={},
        llm=LLMSection(),
        services=ServiceSelection(embed="fake", store="fake"),
        sink=NullSink(),
    )

    # Assert
    assert services.resolve(RouteCatalogue).candidates() == ()


async def test_build_services_raises_for_a_service_selection_naming_an_unregistered_plugin() -> (
    None
):
    # Arrange — `[services] store` naming a plugin nothing registered is exactly the
    # scenario `weft_cli.registry_bootstrap.require_plugin` exists to diagnose before this
    # point is ever reached; `build_services` itself raises the registry's own loud refusal.
    registry = _services_registry()

    # Act / Assert
    with pytest.raises(UnknownPluginError, match="ghost"):
        await build_services(
            registry=registry,
            catalogue=_routable_catalogue(),
            llm=LLMSection(),
            services=ServiceSelection(embed="fake", store="ghost"),
            sink=NullSink(),
        )
