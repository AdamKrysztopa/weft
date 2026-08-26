"""Unit tests for `weft_cli.deletion`.

Mirrors `packages/weft-cli/src/weft_cli/deletion.py`. Task **5.1a**: "deleting a source
reaches everything derived from it: `SourceDeletable` is published in the store family,
`weft delete` fans out across every registered participant, and a participant that fails is
named rather than swallowed."

Three properties are what these tests are for, and only the second one is obvious. That the
fan-out finds a pack registered under a contract this module has never heard of — the graph
store `02` §4 describes, standing in here for a pack that does not exist yet, registered under
its *own* contract with nothing declared. That a failing participant does not stop the ones
after it. And that the configured `[services] store` is the only `NodeStore` asked, because a
project with two store packs installed has exactly one it actually writes to, and deleting from
the other means connecting to a database the operator does not use.

The participants below are hand-written fakes rather than the real `PgVectorStore`, because
what is under test is the *fan-out*, not Postgres — and "a participant that raises" is the one
shape a real container cannot be asked to provide on demand.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import Protocol, runtime_checkable

import pytest

from weft_cli.deletion import delete_everywhere, participants
from weft_kernel.context import Context
from weft_kernel.payload import Node, NodeId, Outcome, Produced, SourceId
from weft_kernel.registry import Registry
from weft_store import Cursor, NodeStore, Page, Removed, SourceDeletable, SourceRecord


@runtime_checkable
class _GraphStore(Protocol):
    """A contract `weft_cli.deletion` has never heard of — the graph pack's own, in miniature.

    Registering a participant under this rather than under `NodeStore` is the whole point:
    the fan-out must find it by capability, not by knowing which contracts hold deletable
    things.
    """

    async def delete_source(self, source_id: SourceId) -> Removed: ...


class _RecordingStore:
    """A `NodeStore` that records what it was asked to delete and answers with a count."""

    def __init__(self, config: object = None) -> None:
        del config
        self.deleted: list[str] = []

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        del ctx
        return Produced(value=payload)

    async def add(self, nodes: Sequence[Node]) -> None:
        del nodes

    async def flush(self) -> None: ...

    async def get(self, ids: Sequence[NodeId]) -> Sequence[Node]:
        del ids
        return ()

    async def delete_source(self, source_id: SourceId) -> Removed:
        self.deleted.append(str(source_id))
        return Removed(source_id=source_id, node_count=7)

    async def scan(self, cursor: Cursor | None = None) -> Page[Node]:
        del cursor
        return Page(items=())

    async def count(self) -> int:
        return 0

    async def put_source(self, record: SourceRecord) -> None:
        del record

    async def get_source(self, source_id: SourceId) -> SourceRecord | None:
        del source_id
        return None

    async def list_sources(self) -> Sequence[SourceRecord]:
        return ()


class _SecondStore(_RecordingStore):
    """A second registered `NodeStore` — the one `[services] store` did *not* select."""


class _DerivedHolder:
    """A pack holding data derived from nodes. Not a store; one method, and that is the point."""

    def __init__(self, config: object = None) -> None:
        del config

    async def delete_source(self, source_id: SourceId) -> Removed:
        return Removed(source_id=source_id, node_count=3)


class _BrokenHolder:
    """A participant that raises — the case the fan-out exists to survive."""

    def __init__(self, config: object = None) -> None:
        del config

    async def delete_source(self, source_id: SourceId) -> Removed:
        del source_id
        raise RuntimeError("connection refused")


def _registry_with_everything() -> Registry:
    registry = Registry()
    registry.add(NodeStore, "pgvector", _RecordingStore, distribution="weft-store")
    registry.add(NodeStore, "qdrant", _SecondStore, distribution="weft-qdrant")
    registry.add(_GraphStore, "graph", _DerivedHolder, distribution="weft-graph")
    return registry


def test_the_fan_out_finds_a_pack_registered_under_a_contract_it_never_heard_of() -> None:
    # Arrange
    registry = _registry_with_everything()

    # Act
    found = participants(registry=registry, store_names=frozenset({"pgvector"}))

    # Assert
    assert [(target.name, target.distribution) for target in found] == [
        ("pgvector", "weft-store"),
        ("graph", "weft-graph"),
    ]


def test_a_second_node_store_this_project_uses_is_asked_as_well() -> None:
    """G13's repair, task **6.18**. `store_names` is a set rather than a name because a
    project runs data through more than one `NodeStore` — `02` §1 → *Extended by G13*, whose
    worked case is the graph store the `kg` pipeline writes to. Both are asked; the one
    nothing names is still absent, which is the half of task 5.1a's narrowing that was right.
    """
    # Arrange
    registry = _registry_with_everything()

    # Act
    found = participants(registry=registry, store_names=frozenset({"pgvector", "qdrant"}))

    # Assert
    assert [target.name for target in found] == ["pgvector", "qdrant", "graph"]


def test_only_the_node_stores_in_use_participate() -> None:
    # Arrange
    registry = _registry_with_everything()

    # Act
    found = participants(registry=registry, store_names=frozenset({"qdrant"}))

    # Assert
    assert [target.name for target in found] == ["qdrant", "graph"]


async def test_every_participant_is_asked_and_the_failing_one_is_named() -> None:
    # Arrange
    registry = Registry()
    registry.add(NodeStore, "pgvector", _RecordingStore, distribution="weft-store")
    registry.add(_GraphStore, "broken", _BrokenHolder, distribution="weft-broken")
    registry.add(_GraphStore, "graph", _DerivedHolder, distribution="weft-graph")
    targets = participants(registry=registry, store_names=frozenset({"pgvector"}))

    # Act
    outcomes = await delete_everywhere(SourceId("doc-1"), targets=targets)

    # Assert
    assert [(o.plugin, o.node_count, o.error) for o in outcomes] == [
        ("pgvector", 7, None),
        ("broken", None, "RuntimeError: connection refused"),
        ("graph", 3, None),
    ]


async def test_a_source_nothing_holds_is_not_an_error() -> None:
    # Arrange
    registry = Registry()

    # Act
    outcomes = await delete_everywhere(
        SourceId("doc-1"),
        targets=participants(registry=registry, store_names=frozenset({"pgvector"})),
    )

    # Assert
    assert outcomes == ()


async def test_cancellation_propagates_rather_than_becoming_a_named_failure() -> None:
    # Arrange
    class _Cancelling:
        def __init__(self, config: object = None) -> None:
            del config

        async def delete_source(self, source_id: SourceId) -> Removed:
            del source_id
            raise asyncio.CancelledError

    registry = Registry()
    registry.add(_GraphStore, "cancels", _Cancelling, distribution="weft-graph")

    # Act / Assert
    with pytest.raises(asyncio.CancelledError):
        await delete_everywhere(
            SourceId("doc-1"),
            targets=participants(registry=registry, store_names=frozenset({"pgvector"})),
        )


def test_a_node_store_satisfies_source_deletable_without_declaring_anything() -> None:
    # Arrange
    store = _RecordingStore()

    # Act
    derived = isinstance(store, SourceDeletable)

    # Assert
    assert derived is True
