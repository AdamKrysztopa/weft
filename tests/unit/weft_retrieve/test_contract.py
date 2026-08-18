"""Unit tests for `weft_retrieve.contract`.

Mirrors `packages/weft-retrieve/src/weft_retrieve/contract.py`. Covers a full
resolve-then-run of a `Retriever` through `weft_kernel.runner` with a plugin that
satisfies the contract structurally, capability derived by `isinstance` rather than
declared, the version constant fitness function 6 will check, and the one property that
makes the four-contract decomposition worth having: the `(In, Out)` pair the kernel reads
off each contract is a *domain* type on both sides, and consecutive contracts compose.
"""

import inspect
import typing
from collections.abc import AsyncIterator

from weft_kernel.context import Context
from weft_kernel.payload import Outcome, Produced
from weft_kernel.registry import Registry
from weft_kernel.runner import Runner, Stage, StageSpec
from weft_retrieve.contract import (
    RETRIEVE_CONTRACT_VERSION,
    ContextPacker,
    Fuser,
    QueryScorer,
    QueryTransform,
    Reranker,
    Retriever,
    RoutingPolicy,
    Sufficiency,
)
from weft_retrieve.payload import Candidates, Passages, Query, QuerySet, Ranking, Route, Scorecard


class _StubRetriever:
    """Satisfies `weft_retrieve.contract.Retriever` structurally — never imports it."""

    def __init__(self, config: object = None) -> None: ...

    async def run(self, payload: QuerySet, ctx: Context) -> Outcome[Candidates]:
        return Produced(value=Candidates(origin=payload.origin))


def _ctx() -> Context:
    return Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")


async def test_a_retriever_composes_through_the_runner_end_to_end() -> None:
    # Arrange
    registry = Registry()
    registry.add(Retriever, "stub", _StubRetriever, distribution="weft-retrieve")
    engine = Runner(registry)
    specs = (StageSpec(id="retrieve", contract=Retriever, name="stub"),)
    asked = Query(text="why is mRMR preferred?")

    async def batches() -> AsyncIterator[QuerySet]:
        yield QuerySet(origin=asked, queries=(asked,))

    # Act
    pipeline = engine.resolve(specs, tenant_id="tenant-a")
    summary = await engine.run(pipeline, batches(), _ctx())

    # Assert
    assert summary.produced == 1


def test_retrieval_capability_is_derived_by_isinstance_not_declared() -> None:
    # Arrange
    class _MissingRun:
        version = RETRIEVE_CONTRACT_VERSION

    # Act / Assert
    assert isinstance(_StubRetriever(), Retriever)
    assert not isinstance(_MissingRun(), Retriever)


def test_every_published_contract_carries_the_version_constant() -> None:
    # Act / Assert
    for contract in (
        QueryTransform,
        Retriever,
        Fuser,
        Reranker,
        ContextPacker,
        QueryScorer,
        RoutingPolicy,
        Sufficiency,
    ):
        assert contract.version == RETRIEVE_CONTRACT_VERSION


def test_no_published_contract_here_has_a_method_that_is_not_async() -> None:
    """`01` → *Colour*, settled in G6: **every** contract method is `async def`.

    A registered contract is reached through `weft_kernel.seam.wrap`, which wraps a
    coroutine — so a sync method on one runs outside the seam, with no span, no error
    attribution and nothing for FF7(b)'s blocking-call detector to see. Asserted over the
    whole published set rather than against one name, so the next contract added here
    cannot reintroduce it quietly.
    """
    # Arrange
    published = (
        QueryTransform,
        Retriever,
        Fuser,
        Reranker,
        ContextPacker,
        QueryScorer,
        RoutingPolicy,
        Sufficiency,
    )

    # Act — public functions only: `version` is a `ClassVar`, and the `_`-prefixed members
    # are `typing.Protocol`'s own machinery rather than anything this module declares.
    sync_methods = [
        f"{contract.__name__}.{name}"
        for contract in published
        for name, member in inspect.getmembers(contract, inspect.isfunction)
        if not name.startswith("_") and not inspect.iscoroutinefunction(member)
    ]

    # Assert
    assert sync_methods == []


def _signature(contract: type[object]) -> tuple[object, ...]:
    """The `(In, Out)` pair `contract` declares, read the way the kernel itself reads it.

    `weft_kernel.runner._stage_signature` is private, so this walks `__orig_bases__` the
    same way rather than reaching into it — the point being asserted is what the contract
    *declares*, and `tests/unit/weft_cli/test_compile.py` is where the kernel's own
    reading of it is exercised end to end.
    """
    for base in getattr(contract, "__orig_bases__", ()):
        if typing.get_origin(base) is Stage:
            return typing.get_args(base)
    return ()


def test_the_query_paths_type_algebra_is_what_the_kernel_reads_off_the_contracts() -> None:
    # Act
    signatures = {
        contract.__name__: _signature(contract)
        for contract in (QueryTransform, Retriever, Fuser, Reranker, ContextPacker)
    }

    # Assert — fan-out and fan-in are expressed in the types, never by a combinator
    assert signatures["QueryTransform"] == (QuerySet, QuerySet)
    assert signatures["Retriever"] == (QuerySet, Candidates)
    assert signatures["Fuser"] == (Candidates, Ranking)
    assert signatures["Reranker"] == (Ranking, Ranking)
    assert signatures["ContextPacker"] == (Ranking, Passages)


def test_the_router_stages_are_ordinary_stages_over_ordinary_data() -> None:
    # Act / Assert
    assert _signature(QueryScorer) == (Query, Scorecard)
    assert _signature(RoutingPolicy) == (Scorecard, Route)


def test_sufficiency_is_named_and_versioned_but_is_not_a_pipeline_position() -> None:
    # Act / Assert — no `Stage[In, Out]` base at all, deliberately: it is resolved by name
    # through `StageLookup`, never placed in a pipeline document.
    assert _signature(Sufficiency) == ()
    assert Sufficiency.version == RETRIEVE_CONTRACT_VERSION
