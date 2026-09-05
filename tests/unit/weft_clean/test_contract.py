"""Unit tests for `weft_clean.contract`.

Mirrors `packages/weft-rag/src/weft_clean/contract.py`. Covers a full
resolve-then-run of `Cleaner` through `weft_kernel.runner`, capability being
derived by `isinstance` rather than declared (the same property
`weft_chunk.contract`'s tests assert for `Chunker`), and task 1.2's own
mandatory-`destroys` check exercised against this real, published contract:
`Cleaner.publishes_property_vocabulary` is `True`, and `weft_kernel.registry`
refuses to register a plugin under it that never mentions `destroys` at all.
"""

from collections.abc import AsyncIterator, Sequence

import pytest

from weft_clean.contract import CLEANER_CONTRACT_VERSION, Cleaner
from weft_kernel.context import Context
from weft_kernel.payload import MediaType, Node, Outcome, Produced
from weft_kernel.registry import MissingDestroysDeclarationError, Registry
from weft_kernel.runner import Lifetime, Runner, StageSpec


def _ctx() -> Context:
    return Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")


def _node(content: str) -> Node:
    return Node.synthetic(content=content, media_type=MediaType.TEXT, reason="test fixture")


class _Uppercases:
    """Satisfies `Cleaner` structurally — a trivial, deterministic text transform."""

    version = CLEANER_CONTRACT_VERSION
    lifetime = Lifetime.RUN
    intact: tuple[type, ...] = ()
    destroys: tuple[type, ...] = ()

    def __init__(self, config: object) -> None:
        self.config = config

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        return Produced(value=[node.derive(content=node.content.upper()) for node in payload])


async def test_cleaner_composes_through_the_runner_end_to_end() -> None:
    # Arrange
    registry = Registry()
    registry.add(Cleaner, "upper", _Uppercases, distribution="weft-test-pack")
    engine = Runner(registry)
    specs = (StageSpec(id="clean", contract=Cleaner, name="upper"),)

    async def batches() -> AsyncIterator[list[Node]]:
        yield [_node("hello world")]

    # Act
    pipeline = engine.resolve(specs, tenant_id="tenant-a")
    summary = await engine.run(pipeline, batches(), _ctx())

    # Assert
    assert summary.produced == 1


def test_cleaner_capability_is_derived_by_isinstance_not_declared() -> None:
    # Arrange
    class _MissingRun:
        """Everything `Cleaner` needs except `run` — never satisfies the contract."""

        version = CLEANER_CONTRACT_VERSION
        lifetime = Lifetime.RUN
        intact: tuple[type, ...] = ()
        destroys: tuple[type, ...] = ()

    class _OnlyRun:
        """`run` and nothing else — no `version`, `lifetime`, `intact` or `destroys`."""

        async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
            return Produced(value=payload)

    # Act / Assert
    assert isinstance(_Uppercases(config=None), Cleaner)
    assert not isinstance(_MissingRun(), Cleaner)
    assert isinstance(_OnlyRun(), Cleaner)


def test_cleaner_publishes_a_property_vocabulary() -> None:
    # Act / Assert — `02` §3 → *Ordering constraints*: readable off the contract itself, the
    # same way `version` is, and for the same reason it must never join `__protocol_attrs__`.
    assert Cleaner.publishes_property_vocabulary is True
    protocol_attrs = getattr(Cleaner, "__protocol_attrs__", frozenset[str]())
    assert "publishes_property_vocabulary" not in protocol_attrs


def test_registering_a_cleaner_with_no_destroys_is_refused() -> None:
    # Arrange — a real contract, not a kernel-level stand-in: `Cleaner` really publishes a
    # property vocabulary, so this is task 1.2's mandatory check proven end to end.
    class _NoDestroysDeclared:
        version = CLEANER_CONTRACT_VERSION
        lifetime = Lifetime.RUN

        def __init__(self, config: object) -> None: ...

        async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
            return Produced(value=payload)

    registry = Registry()

    # Act / Assert
    with pytest.raises(MissingDestroysDeclarationError) as excinfo:
        registry.add(Cleaner, "no-destroys", _NoDestroysDeclared, distribution="acme-clean")

    message = str(excinfo.value)
    assert "no-destroys" in message
    assert "Cleaner" in message
