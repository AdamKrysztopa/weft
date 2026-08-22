"""Unit tests for `weft_generate.contract`.

Mirrors `packages/weft-generate/src/weft_generate/contract.py`. Covers a full
resolve-then-run of a `Generator` through `weft_kernel.runner`, capability derived by
`isinstance` rather than declared, and the version constant fitness function 6
binds to this distribution's own version.
"""

import typing
from collections.abc import AsyncIterator

from weft_generate.contract import GENERATE_CONTRACT_VERSION, Generator
from weft_generate.payload import Answer
from weft_kernel.context import Context
from weft_kernel.payload import Outcome, Produced
from weft_kernel.registry import Registry
from weft_kernel.runner import Runner, Stage, StageSpec
from weft_retrieve.payload import Passages, Query


class _StubGenerator:
    """Satisfies `weft_generate.contract.Generator` structurally — never imports it."""

    def __init__(self, config: object = None) -> None: ...

    async def run(self, payload: Passages, ctx: Context) -> Outcome[Answer]:
        return Produced(value=Answer(origin=payload.origin, text="", answered_by="stub"))


async def test_a_generator_composes_through_the_runner_end_to_end() -> None:
    # Arrange
    registry = Registry()
    registry.add(Generator, "stub", _StubGenerator, distribution="weft-generate")
    engine = Runner(registry)
    specs = (StageSpec(id="generate", contract=Generator, name="stub"),)

    async def batches() -> AsyncIterator[Passages]:
        yield Passages(origin=Query(text="why is mRMR preferred?"))

    # Act
    pipeline = engine.resolve(specs, tenant_id="tenant-a")
    summary = await engine.run(
        pipeline,
        batches(),
        Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en"),
    )

    # Assert
    assert summary.produced == 1


def test_generation_capability_is_derived_by_isinstance_not_declared() -> None:
    # Arrange
    class _MissingRun:
        version = GENERATE_CONTRACT_VERSION

    # Act / Assert
    assert isinstance(_StubGenerator(), Generator)
    assert not isinstance(_MissingRun(), Generator)


def _signature(contract: type[object]) -> tuple[object, ...]:
    """The `(In, Out)` pair `contract` declares, read the way the kernel itself reads it."""
    for base in getattr(contract, "__orig_bases__", ()):
        if typing.get_origin(base) is Stage:
            return typing.get_args(base)
    return ()


def test_the_generator_closes_the_query_path_with_domain_types_on_both_sides() -> None:
    # Act / Assert
    assert _signature(Generator) == (Passages, Answer)
    assert Generator.version == GENERATE_CONTRACT_VERSION
