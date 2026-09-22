"""`--target` reaches a store through one binder, and a store that cannot hold targets is refused
by name — ledger task **34.3**.

Every store is built per invocation from `registry.entry(NodeStore, name).factory(None)`, so the
binder is applied to what that returns; `target` never rides `Context`, which is a kernel type.
"""

from __future__ import annotations

import pytest

from weft_engine.targets import StoreHoldsNoTargetsError, bind_store
from weft_kernel.errors import WeftError
from weft_kernel.payload import MediaType, Node
from weft_store.contract import InvalidTargetNameError
from weft_store.memory import MemoryStore


class _NoTargets:
    """Anything that is not a `TargetHolding` store; the binder must not look further."""


async def test_no_target_returns_the_store_it_was_handed() -> None:
    # Arrange
    store = MemoryStore()

    # Act
    bound = await bind_store(store, None, store_name="memory")

    # Assert
    assert bound is store


async def test_a_target_binds_the_store_to_it() -> None:
    # Arrange
    store = MemoryStore()

    # Act
    bound = await bind_store(store, "w128", store_name="memory")
    await bound.add([Node.synthetic(content="x", media_type=MediaType.TEXT, reason="targets test")])

    # Assert
    assert await store.count() == 0
    assert await bound.count() == 1


async def test_a_store_that_holds_no_targets_is_refused_naming_it_and_the_capability() -> None:
    # Act / Assert
    with pytest.raises(StoreHoldsNoTargetsError) as caught:
        await bind_store(_NoTargets(), "w128", store_name="example-store")
    assert isinstance(caught.value, WeftError)
    message = str(caught.value)
    assert "example-store" in message
    assert "TargetHolding" in message
    assert "w128" in message


async def test_a_malformed_target_is_refused_before_the_store_is_asked() -> None:
    # Act / Assert
    with pytest.raises(InvalidTargetNameError):
        await bind_store(MemoryStore(), "W-128", store_name="memory")
