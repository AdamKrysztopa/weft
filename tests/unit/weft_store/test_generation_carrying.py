"""Ledger task **43.22** — a generation carries the published one's untouched members forward.

A carry adds the new generation's id to a node the published one already holds, and never rewrites
the node, so publishing the new generation and retracting the old one keeps every carried node and
drops every node the new one replaced. `GenerationCarrying` is its own optional Protocol rather than
a method on `GenerationHolding`: `09`'s two-audience table makes a method added to an existing
Protocol a major for its implementers, and `10.24` and `34.3` took the minor this way.

The stranger is `examples/weft-example-ingest`'s store, the only in-process `GenerationHolding` —
`weft_store.memory.MemoryStore` holds no generations.
"""

import importlib
import sys
from collections.abc import Callable
from pathlib import Path
from typing import cast

import pytest

from weft_kernel.errors import WeftError
from weft_kernel.payload import MediaType, Node, NodeId, SourceId, Vector
from weft_store.conformance import (
    GenerationCarryingStore,
    check_a_carried_generation_keeps_what_it_carries_and_drops_what_it_replaces,
    check_carrying_a_node_no_published_generation_holds_is_refused_by_name,
    checks_for,
    unsupported_checks,
)
from weft_store.contract import (
    STORE_CONTRACT_VERSION,
    GenerationCarrying,
    GenerationHolding,
    GenerationId,
    NotAPublishedMemberError,
)
from weft_store.memory import MemoryStore

_OPERATION = "carry_forward"
_PROTOCOL = "GenerationCarrying"
_STORE_TYPE = "GenerationCarryingStore"
_KIT_CHECKS = (
    check_a_carried_generation_keeps_what_it_carries_and_drops_what_it_replaces,
    check_carrying_a_node_no_published_generation_holds_is_refused_by_name,
)


async def _carry(store: GenerationCarryingStore, into: GenerationId, ids: list[NodeId]) -> int:
    return await store.carry_forward(into, ids)


_EXAMPLE_SRC = Path(__file__).resolve().parents[3] / "examples/weft-example-ingest/src"


@pytest.fixture
def stranger(monkeypatch: pytest.MonkeyPatch) -> Callable[[], GenerationCarryingStore]:
    monkeypatch.setattr(sys, "path", [str(_EXAMPLE_SRC), *sys.path])
    module = importlib.import_module("weft_example_ingest.store")
    return lambda: cast("GenerationCarryingStore", module.InMemoryNodeStore())


def _summary(content: str) -> Node:
    return Node.synthetic(
        content=content,
        media_type=MediaType.TEXT,
        reason="43.22",
        sources=frozenset({SourceId("source-a")}),
    ).with_embedding(Vector(values=(0.2, 0.3, 0.5)))


async def _fresh_reader(store: GenerationCarryingStore) -> GenerationCarryingStore:
    """A handle that has not read yet, so it sees what is published now."""
    probe = await store.open_generation("probe")
    return await store.bind_generation(probe.id)


def test_carrying_is_its_own_optional_protocol_so_the_contract_moves_a_minor() -> None:
    # Assert
    assert STORE_CONTRACT_VERSION == "2.13.0"
    assert GenerationCarrying.version == STORE_CONTRACT_VERSION
    assert callable(getattr(GenerationCarrying, _OPERATION, None))
    assert not hasattr(GenerationHolding, _OPERATION)


def test_a_refused_carry_names_the_generation_and_every_node_it_refused() -> None:
    # Act
    refused = NotAPublishedMemberError(GenerationId("g-2"), node_ids=(NodeId("n-1"), NodeId("n-2")))

    # Assert
    assert isinstance(refused, WeftError)
    assert refused.generation == "g-2"
    assert refused.node_ids == ("n-1", "n-2")
    for fact in ("'g-2'", "n-1", "n-2"):
        assert fact in str(refused), fact


def test_the_kit_offers_the_carrying_checks_only_to_a_store_that_carries() -> None:
    # Act
    offered = checks_for(MemoryStore())
    withheld = dict(unsupported_checks(MemoryStore()))

    # Assert
    for check in _KIT_CHECKS:
        assert check.__annotations__.get("store") == _STORE_TYPE
        assert check not in offered
        assert withheld[check] == _PROTOCOL


async def test_a_strangers_store_carries_generations_and_passes_the_published_checks(
    stranger: Callable[[], GenerationCarryingStore],
) -> None:
    """Fitness function 9(c)'s stranger for the new capability, on `43.14`'s footing."""
    # Arrange
    carrying_checks = [
        check
        for check in checks_for(stranger())
        if check.__annotations__.get("store") == _STORE_TYPE
    ]

    # Act — a fresh store per check: the kit owns no lifecycle.
    for check in carrying_checks:
        await check(stranger())

    # Assert
    assert isinstance(stranger(), GenerationCarrying)
    assert sorted(check.__name__ for check in carrying_checks) == sorted(
        check.__name__ for check in _KIT_CHECKS
    )


async def test_a_carried_node_belongs_to_both_generations_and_is_never_rewritten(
    stranger: Callable[[], GenerationCarryingStore],
) -> None:
    # Arrange
    store = stranger()
    node = _summary("a summary the rebuild leaves alone")
    old = await store.open_generation("enrich-with-raptor")
    await (await store.bind_generation(old.id)).add([node])
    await store.publish_generation(old.id)
    new = await store.open_generation("enrich-with-raptor")

    # Act
    carried = await _carry(store, new.id, [node.id, node.id])
    await store.publish_generation(new.id)
    await store.retract_generation(old.id)
    survived = await (await _fresh_reader(store)).get([node.id])
    await store.retract_generation(new.id)
    gone = await (await _fresh_reader(store)).get([node.id])

    # Assert
    assert carried == 1
    assert list(survived) == [node]
    assert list(gone) == []
