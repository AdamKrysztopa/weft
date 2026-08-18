"""Unit tests for `weft_enhance.contract`.

Mirrors `packages/weft-enhance/src/weft_enhance/contract.py`. Covers a full
resolve-then-run of `Enhancer` through `weft_kernel.runner` with a plugin
that satisfies the contract structurally (no inheritance), capability
derived by `isinstance` rather than declared, and the version constant
fitness function 6 will eventually check.
"""

from collections.abc import AsyncIterator, Sequence

from weft_enhance.contract import ENHANCER_CONTRACT_VERSION, Enhancer
from weft_enhance.keybert_stand_in import KeyBertKeywordExtractor
from weft_kernel.context import Context
from weft_kernel.payload import MediaType, Node, Outcome, Produced
from weft_kernel.registry import Registry
from weft_kernel.runner import Runner, StageSpec


def _ctx() -> Context:
    return Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")


def _node(content: str) -> Node:
    return Node.synthetic(content=content, media_type=MediaType.TEXT, reason="test fixture")


async def test_enhancer_composes_through_the_runner_end_to_end() -> None:
    # Arrange
    registry = Registry()
    registry.add(Enhancer, "keybert", KeyBertKeywordExtractor, distribution="weft-enhance")
    engine = Runner(registry)
    specs = (StageSpec(id="keywords", contract=Enhancer, name="keybert"),)
    node = _node("weft weft weft engine")

    async def batches() -> AsyncIterator[list[Node]]:
        yield [node]

    # Act
    pipeline = engine.resolve(specs, tenant_id="tenant-a")
    summary = await engine.run(pipeline, batches(), _ctx())

    # Assert
    assert summary.produced == 1


def test_enhancer_capability_is_derived_by_isinstance_not_declared() -> None:
    # Arrange
    class _MissingRun:
        """Declares `version` but not `run` — never satisfies the contract."""

        version = ENHANCER_CONTRACT_VERSION

    class _OnlyRun:
        """`run` and nothing else."""

        async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
            return Produced(value=[])

    # Act / Assert
    assert isinstance(KeyBertKeywordExtractor(config=None), Enhancer)
    assert not isinstance(_MissingRun(), Enhancer)
    assert isinstance(_OnlyRun(), Enhancer)


def test_enhancer_version_is_declared_on_the_contract_itself() -> None:
    # Act / Assert
    assert Enhancer.version == ENHANCER_CONTRACT_VERSION
