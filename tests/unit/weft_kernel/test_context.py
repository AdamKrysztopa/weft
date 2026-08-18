"""Unit tests for `weft_kernel.context`.

Mirrors `packages/weft-kernel/src/weft_kernel/context.py`. Covers `require()`
resolving a registered service and refusing loudly when nothing registered
one, `t()` resolving and formatting a registered message and refusing loudly
when nothing registered one, `cancelled` as a live view onto the running
task's own cancellation state rather than a stored flag (including outside a
running loop, its documented `False` case), the two duplicate-registration
refusals on `ServiceRegistry` and `MessageCatalogue`, and that the passport's
identity cannot be reassigned by a stage that was handed it.
"""

import asyncio
import dataclasses

import pytest

from weft_kernel.context import (
    Context,
    DuplicateMessageError,
    DuplicateServiceError,
    MessageCatalogue,
    MessageFormatError,
    ServiceRegistry,
    UnknownMessageError,
    UnresolvedServiceError,
)


class _LLM:
    """A stand-in contract. `ServiceRegistry` must not know or care what this is."""


class _TokenSink:
    """A second, unrelated contract, used to show resolution is keyed by contract."""


def _context(
    *, services: ServiceRegistry | None = None, messages: MessageCatalogue | None = None
) -> Context:
    return Context(
        tenant_id="tenant-a",
        run_id="run-1",
        trace_id="trace-1",
        locale="en",
        services=services if services is not None else ServiceRegistry(),
        messages=messages if messages is not None else MessageCatalogue(),
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


def test_t_resolves_and_formats_a_registered_message_for_the_context_locale() -> None:
    # Arrange
    messages = MessageCatalogue()
    messages.add(locale="en", key="graph.node_dropped", template="dropped {n} node(s)")
    ctx = _context(messages=messages)

    # Act
    text = ctx.t("graph.node_dropped", n=3)

    # Assert
    assert text == "dropped 3 node(s)"


def test_t_raises_naming_the_wanted_key_the_locale_and_what_is_available() -> None:
    # Arrange
    messages = MessageCatalogue()
    messages.add(locale="en", key="graph.node_dropped", template="dropped {n} node(s)")
    ctx = _context(messages=messages)

    # Act / Assert
    with pytest.raises(UnknownMessageError) as excinfo:
        ctx.t("graph.node_missing")

    message = str(excinfo.value)
    assert "graph.node_missing" in message
    assert "en" in message
    assert "graph.node_dropped" in message


def test_t_raises_a_weft_error_naming_key_locale_template_and_params_on_a_missing_placeholder() -> (
    None
):
    # Arrange
    messages = MessageCatalogue()
    messages.add(locale="en", key="graph.node_dropped", template="dropped {n} node(s)")
    ctx = _context(messages=messages)

    # Act / Assert
    with pytest.raises(MessageFormatError) as excinfo:
        ctx.t("graph.node_dropped")

    message = str(excinfo.value)
    assert "graph.node_dropped" in message
    assert "en" in message
    assert "dropped {n} node(s)" in message


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


def test_message_catalogue_add_refuses_a_second_template_for_an_already_registered_key() -> None:
    # Arrange
    messages = MessageCatalogue()
    messages.add(locale="en", key="graph.node_dropped", template="dropped {n} node(s)")

    # Act / Assert
    with pytest.raises(DuplicateMessageError) as excinfo:
        messages.add(locale="en", key="graph.node_dropped", template="removed {n} node(s)")

    message = str(excinfo.value)
    assert "graph.node_dropped" in message
    assert "en" in message


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
