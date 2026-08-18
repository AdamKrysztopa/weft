"""Unit tests for `weft_chunk.contract`.

Mirrors `packages/weft-chunk/src/weft_chunk/contract.py`. Covers a full
resolve-then-run of `Chunker` through `weft_kernel.runner`, `Outcome`
discipline at this contract's boundary — `NothingToProduce` halting the
chain and a `Failed` reason reaching the returned `RunSummary` — and
capability being derived by `isinstance` rather than declared, the same
property `weft_extract.contract`'s tests assert for `Extractor`.
"""

from collections.abc import AsyncIterator, Sequence

from weft_chunk.contract import CHUNKER_CONTRACT_VERSION, Chunker
from weft_kernel.context import Context
from weft_kernel.payload import Failed, MediaType, Node, NothingToProduce, Outcome, Produced
from weft_kernel.registry import Registry
from weft_kernel.runner import Lifetime, Runner, StageSpec


def _ctx() -> Context:
    return Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")


def _node(content: str) -> Node:
    return Node.synthetic(content=content, media_type=MediaType.TEXT, reason="test fixture")


class _SplitInHalf:
    """Satisfies `Chunker` structurally — one `Node` in, two children out."""

    version = CHUNKER_CONTRACT_VERSION
    lifetime = Lifetime.RUN
    requires: tuple[type, ...] = ()
    provides: tuple[type, ...] = ()

    def __init__(self, config: object) -> None:
        self.config = config

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        midpoint = len(payload[0].content) // 2
        return Produced(
            value=[
                payload[0].derive(content=payload[0].content[:midpoint], ordinal=0),
                payload[0].derive(content=payload[0].content[midpoint:], ordinal=1),
            ]
        )


async def test_chunker_composes_through_the_runner_end_to_end() -> None:
    # Arrange
    registry = Registry()
    registry.add(Chunker, "split-half", _SplitInHalf, distribution="weft-test-pack")
    engine = Runner(registry)
    specs = (StageSpec(id="chunk", contract=Chunker, name="split-half"),)

    async def batches() -> AsyncIterator[list[Node]]:
        yield [_node("hello world")]

    # Act
    pipeline = engine.resolve(specs, tenant_id="tenant-a")
    summary = await engine.run(pipeline, batches(), _ctx())

    # Assert
    assert summary.produced == 1


async def test_chunker_nothing_to_produce_halts_the_chain() -> None:
    # Arrange
    class _EmptyInput:
        version = CHUNKER_CONTRACT_VERSION
        lifetime = Lifetime.RUN
        requires: tuple[type, ...] = ()
        provides: tuple[type, ...] = ()

        def __init__(self, config: object) -> None: ...

        async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
            return NothingToProduce(reason="nothing left to split")

    registry = Registry()
    registry.add(Chunker, "empty", _EmptyInput, distribution="weft-test-pack")
    engine = Runner(registry)
    specs = (StageSpec(id="chunk", contract=Chunker, name="empty"),)

    async def batches() -> AsyncIterator[list[Node]]:
        yield [_node("hello")]

    # Act
    pipeline = engine.resolve(specs, tenant_id="tenant-a")
    summary = await engine.run(pipeline, batches(), _ctx())

    # Assert
    assert summary.nothing_to_produce == 1
    assert summary.nothing_to_produce_reasons == ("nothing left to split",)


async def test_chunker_failed_reason_reaches_the_run_summary() -> None:
    # Arrange
    class _AlwaysFails:
        version = CHUNKER_CONTRACT_VERSION
        lifetime = Lifetime.RUN
        requires: tuple[type, ...] = ()
        provides: tuple[type, ...] = ()

        def __init__(self, config: object) -> None: ...

        async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
            return Failed(reason="content too short to split")

    registry = Registry()
    registry.add(Chunker, "fails", _AlwaysFails, distribution="weft-test-pack")
    engine = Runner(registry)
    specs = (StageSpec(id="chunk", contract=Chunker, name="fails"),)

    async def batches() -> AsyncIterator[list[Node]]:
        yield [_node("hi")]

    # Act
    pipeline = engine.resolve(specs, tenant_id="tenant-a")
    summary = await engine.run(pipeline, batches(), _ctx())

    # Assert
    assert summary.failed == 1
    assert summary.failed_reasons == ("content too short to split",)


def test_chunker_capability_is_derived_by_isinstance_not_declared() -> None:
    # Arrange
    class _MissingRun:
        """Everything `Chunker` needs except `run` — never satisfies the contract."""

        version = CHUNKER_CONTRACT_VERSION
        lifetime = Lifetime.RUN
        requires: tuple[type, ...] = ()
        provides: tuple[type, ...] = ()

    class _OnlyRun:
        """`run` and nothing else — no `version`, `lifetime`, `requires` or `provides`."""

        async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
            return Produced(value=payload)

    # Act / Assert — declaring the metadata neither helps (`_MissingRun`) nor is required
    # (`_OnlyRun`): capability comes from implementing `run`, nothing else.
    assert isinstance(_SplitInHalf(config=None), Chunker)
    assert not isinstance(_MissingRun(), Chunker)
    assert isinstance(_OnlyRun(), Chunker)
