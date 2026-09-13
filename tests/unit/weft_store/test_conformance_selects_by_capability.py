"""A store is asked only the questions its capabilities can answer — ledger task **26.5**.

Task `26.4` published twenty-five checks and ran them, from a bare install, against a store written
outside this repository. Eight passed and seventeen failed — and **six of the failures were
`AttributeError`**: `'DictStore' object has no attribute 'supersede'`, and the same for `reconcile`
and `estimate`. That is the published kit telling a pack author their store is broken when it is
merely *smaller*, in the one dialect this project refuses: a traceback from a missing attribute
rather than a sentence naming what was wanted and what is available.

**Capability is derived, never declared** (`02` → that section's own heading). A store's capability
set *is* the protocols its methods satisfy; nobody writes a flag, so nobody writes a false one. The
kit already has everything it needs to apply that rule — `26.4` typed each check against the
narrowest published protocol it calls — and what was missing is the seam that reads it.

**What this task decides.** `checks_for(store)` returns the checks that store can answer, in a
stable order, and `unsupported_checks(store)` returns the ones it cannot **with the capability each
one needs**. A caller runs the first and reports the second; nothing is skipped silently, because a
kit that quietly ran fewer checks would be a kit whose pass means less the smaller your store is —
and the author would never know which half they had proved.

**A `NodeStore` is not optional and is not a capability.** Every check needs one, so a store that
does not satisfy `NodeStore` is not a smaller store, it is not a store — and that is a refusal
rather than a filter.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import ClassVar

import pytest

from weft_kernel.context import Context
from weft_kernel.payload import Node, NodeId, Outcome, Produced, SourceId
from weft_store import Page, Removed, SourceRecord
from weft_store.contract import STORE_CONTRACT_VERSION, Cursor


class _NodeStoreOnly:
    """A store with the base contract and no optional capability — the pack author's first draft.

    Copied from `tests/unit/weft_store/test_conformance_is_publishable.py`'s double rather than
    written from the protocol's prose (`L11.17`), and extended here with nothing: the *absence* is
    what this file is about.
    """

    version: ClassVar[str] = STORE_CONTRACT_VERSION

    def __init__(self) -> None:
        self.nodes: dict[str, Node] = {}
        self.records: dict[SourceId, SourceRecord] = {}

    async def add(self, nodes: Sequence[Node]) -> None:
        for node in nodes:
            self.nodes[node.id] = node

    async def flush(self) -> None:
        return

    async def count(self) -> int:
        return len(self.nodes)

    async def get(self, ids: Sequence[NodeId]) -> Sequence[Node]:
        return tuple(self.nodes[i] for i in ids if i in self.nodes)

    async def scan(self, cursor: Cursor | None = None) -> Page[Node]:
        del cursor
        return Page[Node](items=tuple(self.nodes.values()), next_cursor=None)

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        del ctx
        await self.add(payload)
        return Produced(value=payload)

    async def put_source(self, record: SourceRecord) -> None:
        self.records[record.id] = record

    async def get_source(self, source_id: SourceId) -> SourceRecord | None:
        return self.records.get(source_id)

    async def list_sources(self) -> Sequence[SourceRecord]:
        return tuple(self.records.values())

    async def delete_source(self, source_id: SourceId) -> Removed:
        kept = {k: v for k, v in self.nodes.items() if source_id not in v.lineage.sources}
        gone = len(self.nodes) - len(kept)
        self.nodes = kept
        self.records.pop(source_id, None)
        return Removed(source_id=source_id, node_count=gone)


class _SupersedableOnly(_NodeStoreOnly):
    """One capability more. Two doubles, because a selector that returned everything for every
    store and one that selects correctly agree whenever only one store is examined (`L12.6`).
    """

    async def supersede(self, node_id: NodeId, replacement: Node) -> None:
        del node_id
        self.nodes[replacement.id] = replacement


class _NotAStore:
    """Satisfies no protocol at all — the refusal case, not the filter case."""


def test_a_base_store_is_offered_the_checks_that_need_nothing_more() -> None:
    """The happy path: a store with only `NodeStore` gets a real, non-empty set of checks."""
    # Arrange
    from weft_store.conformance import checks_for

    # Act
    offered = checks_for(_NodeStoreOnly())

    # Assert — a real population, and every member is callable.
    assert len(offered) >= 10
    assert all(callable(check) for check in offered)


def test_a_capability_a_store_lacks_is_reported_rather_than_silently_dropped() -> None:
    """The half that makes the selection honest.

    A kit that quietly ran fewer checks would mean less the smaller your store is, and the author
    would never learn which half they had proved. So what is skipped is returned, named, with the
    capability that would enable it.
    """
    # Arrange
    from weft_store.conformance import unsupported_checks

    # Act
    skipped = unsupported_checks(_NodeStoreOnly())

    # Assert — the capability is named, not merely the check.
    capabilities = {capability for _check, capability in skipped}
    assert {"NodeSupersedable", "Reconcilable"} <= capabilities, capabilities


def test_gaining_a_capability_moves_checks_from_unsupported_to_offered() -> None:
    """The two doubles differ by exactly one capability, so this is the assertion a selector that
    ignores the store cannot pass — it is the control for both tests above.
    """
    # Arrange
    from weft_store.conformance import checks_for, unsupported_checks

    base, better = _NodeStoreOnly(), _SupersedableOnly()

    # Act
    gained = {c.__name__ for c in checks_for(better)} - {c.__name__ for c in checks_for(base)}
    still_missing = {cap for _c, cap in unsupported_checks(better)}

    # Assert
    assert gained, "adding supersede offered no further checks, so the selector ignores the store"
    assert all("supersede" in name for name in gained), gained
    assert "NodeSupersedable" not in still_missing
    assert "Reconcilable" in still_missing


def test_every_published_check_is_either_offered_or_reported() -> None:
    """No check may fall between the two, which is the defect a two-list design invites.

    Asserted against the module's own published set rather than a number written here, so it stays
    true when the kit grows.
    """
    # Arrange
    import weft_store.conformance as kit
    from weft_store.conformance import checks_for, unsupported_checks

    published = {n for n, v in vars(kit).items() if n.startswith("check_") and callable(v)}
    store = _NodeStoreOnly()

    # Act
    accounted = {c.__name__ for c in checks_for(store)} | {
        c.__name__ for c, _cap in unsupported_checks(store)
    }

    # Assert
    assert published, "the kit published no checks at all, so this comparison is vacuous"
    assert accounted == published, published ^ accounted


def test_something_that_is_not_a_store_is_refused_rather_than_offered_nothing() -> None:
    """The error case, and the distinction the whole task rests on.

    A store lacking `NodeSupersedable` is a *smaller* store and gets fewer checks. A thing lacking
    `NodeStore` is not a store, and answering it with an empty list would be
    `01`'s *an empty answer is not a fact about the world* — it would read as *you passed nothing*
    rather than *you handed me the wrong object*.
    """
    # Arrange
    from weft_store.conformance import NotAStoreError, checks_for

    # Act / Assert
    with pytest.raises(NotAStoreError) as caught:
        checks_for(_NotAStore())
    assert "NodeStore" in str(caught.value)
