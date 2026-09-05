"""Unit tests for `weft_embed.contract`.

Mirrors `packages/weft-rag/src/weft_embed/contract.py`. Covers a full
resolve-then-run of `Embedder` through `weft_kernel.runner` with a plugin
that satisfies the contract structurally (no inheritance), capability
derived by `isinstance` rather than declared, and the version constant
fitness function 6 binds to this distribution's own version.
"""

from collections.abc import AsyncIterator, Sequence

from weft_embed.contract import EMBEDDER_CONTRACT_VERSION, Embedder
from weft_embed.hash_embedder import HashEmbedder
from weft_kernel.context import Context
from weft_kernel.payload import MediaType, Node, Outcome, Produced
from weft_kernel.registry import Registry
from weft_kernel.runner import Runner, StageSpec


def _ctx() -> Context:
    return Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")


def _node(content: str) -> Node:
    return Node.synthetic(content=content, media_type=MediaType.TEXT, reason="test fixture")


async def test_embedder_composes_through_the_runner_end_to_end() -> None:
    # Arrange
    registry = Registry()
    registry.add(Embedder, "hash", HashEmbedder, distribution="weft-embed")
    engine = Runner(registry)
    specs = (StageSpec(id="embed", contract=Embedder, name="hash"),)
    node = _node("hello")

    async def batches() -> AsyncIterator[list[Node]]:
        yield [node]

    # Act
    pipeline = engine.resolve(specs, tenant_id="tenant-a")
    summary = await engine.run(pipeline, batches(), _ctx())

    # Assert
    assert summary.produced == 1


def test_embedder_capability_is_derived_by_isinstance_not_declared() -> None:
    # Arrange
    class _MissingRun:
        """Declares `version` but not `run` — never satisfies the contract."""

        version = EMBEDDER_CONTRACT_VERSION

    class _OnlyRun:
        """`run` and nothing else."""

        async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
            return Produced(value=[])

    # Act / Assert
    assert isinstance(HashEmbedder(config=None), Embedder)
    assert not isinstance(_MissingRun(), Embedder)
    assert isinstance(_OnlyRun(), Embedder)


def test_embedder_version_is_declared_on_the_contract_itself() -> None:
    # Act / Assert
    assert Embedder.version == EMBEDDER_CONTRACT_VERSION
