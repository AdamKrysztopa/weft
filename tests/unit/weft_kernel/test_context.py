"""Unit tests for `weft_kernel.context`.

Mirrors `packages/weft-kernel/src/weft_kernel/context.py`. Covers `require()`
resolving a registered service and refusing loudly when nothing registered
one, `cancelled` as a live view onto the running task's own cancellation state
rather than a stored flag (including outside a running loop, its documented
`False` case), `ServiceRegistry`'s duplicate-registration refusal, and that
the passport's identity cannot be reassigned by a stage that was handed it.

**The `t()` and `MessageCatalogue` tests were removed by G11 (2026-08-18)**,
with the seam they covered — see that module's own retirement note.
"""

import asyncio
import dataclasses
from typing import Protocol, runtime_checkable

import pytest
from pydantic import ValidationError

from weft_kernel.context import (
    Context,
    DuplicateServiceError,
    ServiceRegistry,
    ServiceRole,
    UnresolvedServiceError,
)


class _LLM:
    """A stand-in contract. `ServiceRegistry` must not know or care what this is."""


class _TokenSink:
    """A second, unrelated contract, used to show resolution is keyed by contract."""


def _context(*, services: ServiceRegistry | None = None) -> Context:
    return Context(
        tenant_id="tenant-a",
        run_id="run-1",
        trace_id="trace-1",
        locale="en",
        services=services if services is not None else ServiceRegistry(),
    )


def test_require_resolves_the_instance_registered_for_its_contract() -> None:
    # Arrange
    services = ServiceRegistry()
    llm = _LLM()
    services.add(_LLM, llm)
    ctx = _context(services=services)

    # Act
    resolved = ctx.require(_LLM)

    # Assert
    assert resolved is llm


def test_require_raises_naming_the_wanted_contract_and_what_is_available() -> None:
    # Arrange
    services = ServiceRegistry()
    services.add(_TokenSink, _TokenSink())
    ctx = _context(services=services)

    # Act / Assert
    with pytest.raises(UnresolvedServiceError) as excinfo:
        ctx.require(_LLM)

    message = str(excinfo.value)
    assert "_LLM" in message
    assert "_TokenSink" in message


def test_service_registry_add_refuses_a_second_instance_for_an_already_registered_contract() -> (
    None
):
    # Arrange
    services = ServiceRegistry()
    services.add(_LLM, _LLM())

    # Act / Assert
    with pytest.raises(DuplicateServiceError) as excinfo:
        services.add(_LLM, _LLM())

    assert "_LLM" in str(excinfo.value)


def test_context_identity_cannot_be_reassigned_by_a_stage_that_was_handed_it() -> None:
    # Arrange
    ctx = _context()

    # Act / Assert
    with pytest.raises(dataclasses.FrozenInstanceError):
        ctx.tenant_id = "tenant-b"  # type: ignore[misc]


def test_cancelled_is_false_with_no_running_event_loop() -> None:
    # Arrange
    ctx = _context()

    # Act
    result = ctx.cancelled

    # Assert
    assert result is False


async def test_cancelled_is_false_with_no_pending_cancellation() -> None:
    # Arrange
    ctx = _context()

    # Act
    result = ctx.cancelled

    # Assert
    assert result is False


async def test_cancelled_reflects_a_pending_cancellation_on_the_running_task() -> None:
    # Arrange
    ctx = _context()
    observed: list[bool] = []

    async def _stage() -> None:
        task = asyncio.current_task()
        assert task is not None
        task.cancel()
        observed.append(ctx.cancelled)
        raise asyncio.CancelledError

    task = asyncio.ensure_future(_stage())

    # Act / Assert
    with pytest.raises(asyncio.CancelledError):
        await task
    assert observed == [True]


# --- service roles (task 9.0) -----------------------------------------------------------


def test_a_service_role_carries_the_key_and_the_contract_it_selects_for() -> None:
    """`ServiceRole` is what a pack declares beside the Protocol it publishes.

    Ledger task **9.0**: `[services].<role>` names one plugin for a role the
    contract-publishing pack declares selectable, and the declaration is "one constant
    beside the Protocol" (`docs/build-ledger.md:5026 'exists b'`, `:5370`). This is the type of that
    constant. The kernel holds a key and a contract and names neither — the same restraint
    `weft_kernel.discovery.RendererOffer` already keeps for a result type it never names.
    """

    # Arrange
    class _BlobStore:
        """A stand-in contract published by some pack the kernel has never heard of."""

    # Act
    role = ServiceRole(key="blobs", contract=_BlobStore)

    # Assert
    assert role.key == "blobs"
    assert role.contract is _BlobStore


def test_a_service_role_is_frozen_so_a_pack_cannot_be_repointed_after_it_declared_one() -> None:
    """A declaration is a fact about the pack that made it, fixed once made.

    `CLAUDE.md`: frozen where the value is a domain object. The failure this forbids is a
    role table that is assembled from every pack's declarations and then mutated by
    whichever pack is imported last.
    """

    # Arrange
    class _BlobStore:
        pass

    role = ServiceRole(key="blobs", contract=_BlobStore)

    # Act / Assert
    with pytest.raises(ValidationError):
        role.key = "something-else"  # type: ignore[misc]


def test_declaring_a_role_leaves_the_contracts_own_isinstance_behaviour_untouched() -> None:
    """The role is a constant beside the Protocol, never a member on it.

    This is the trap `docs/build-ledger.md:5057-5058 'phase and'` names — "**No `service_key`
    ClassVar**
    on any contract" — with the mechanism at
    `packages/weft-rag/src/weft_extract/contract.py:44-56 'inside the'`: `typing.Protocol` computes
    `__protocol_attrs__` once from the class body, so a marker written into the body would
    become a *required* structural member and a third-party implementor that implements the
    real method but never restates the marker would fail a capability check that has nothing
    to do with capability.

    The assertion is the consequence rather than the mechanism: a stranger's class that
    satisfies the Protocol's methods and knows nothing about roles still passes `isinstance`
    after a role has been declared for that contract.
    """

    # Arrange
    @runtime_checkable
    class _BlobStore(Protocol):
        async def put(self, payload: bytes) -> str: ...

    class _StrangersBlobStore:
        """Implements the contract and has never heard of `ServiceRole`."""

        async def put(self, payload: bytes) -> str:
            return "ref"

    # Act
    ServiceRole(key="blobs", contract=_BlobStore)

    # Assert
    assert isinstance(_StrangersBlobStore(), _BlobStore)
    protocol_attrs = getattr(_BlobStore, "__protocol_attrs__", frozenset[str]())
    assert "key" not in protocol_attrs
    assert "contract" not in protocol_attrs
