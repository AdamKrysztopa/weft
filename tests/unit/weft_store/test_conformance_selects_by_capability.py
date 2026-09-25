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
    """One capability more.

    Two doubles, because a selector that returned everything for every store and one that selects
    correctly agree whenever only one store is examined (`L12.6`).
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
    """Adding one capability offers new checks, so the conformance selector really reads the store.

    The two doubles differ by exactly one capability, so this is the assertion a selector that
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


# --- R21.3: the fourth capability tier gets published checks ----------------------------------
#
# **Measured at Phase 21b's close, by `weft-qualities`' requirement-4 lens run against the phase.**
# The kit published 25 checks: `search_vector` 8, `matching` 18, `supersede` 16, `reconcile` 14,
# `estimate` 16 — and **`search_text` zero**. So a third party writing a store got published
# verification for three of the store contract family's four capability tiers, while Weft's own two
# backends were verified by `tests/`, which ships in no distribution. That is the built-in path
# richer than the public one, which is the shape requirement 4 exists to catch.
#
# **It was defensible until Phase 21b and is not now.** A kit check for a capability with one
# implementation has nothing to hold it to — `02` §1's own *a contract with one implementation is a
# guess* — and task `21.8` made it two. The argument that justified the absence is the argument
# that removes it.


class _TextSearchableOnly(_NodeStoreOnly):
    """A store with the base contract and `search_text`.

    The shape `pgvector` and `qdrant` share and `MemoryStore` does not.
    """

    async def search_text(self, text: str, top_k: int, filter: object = None) -> Sequence[object]:
        del text, top_k, filter
        return ()


def test_a_store_with_a_text_arm_is_offered_the_text_checks() -> None:
    # Arrange
    from weft_store.conformance import checks_for

    # Act
    offered = {check.__name__ for check in checks_for(_TextSearchableOnly())}

    # Assert
    text_checks = {name for name in offered if "search_text" in name}
    assert text_checks, (
        "a store advertising TextSearch is offered no check for it — the fourth capability tier "
        "is published and unverified, which is R21.3"
    )


def test_a_store_without_a_text_arm_is_told_what_it_was_not_asked() -> None:
    """`unsupported_checks` names each skipped text check and the `TextSearch` capability it needs.

    The half that makes the filter honest: nothing is skipped silently, so an author whose
    store has no text arm learns which checks they did not answer and why.
    """
    # Arrange
    from weft_store.conformance import unsupported_checks

    # Act
    reported = {check.__name__: needed for check, needed in unsupported_checks(_NodeStoreOnly())}

    # Assert
    text_checks = {name: needed for name, needed in reported.items() if "search_text" in name}
    assert text_checks, "a store with no text arm is told nothing about the checks it skipped"
    assert set(text_checks.values()) == {"TextSearch"}, (
        f"the capability reported for a text check must be TextSearch: {text_checks}"
    )


def test_gaining_a_text_arm_moves_those_checks_from_unsupported_to_offered() -> None:
    """The property the whole selector exists for, asserted as a *move*.

    The property the whole selector exists for, asserted on the tier this repair adds — and
    asserted as a *move* rather than as two independent counts, so a check that appeared in
    neither list would fail here.
    """
    # Arrange
    from weft_store.conformance import checks_for, unsupported_checks

    def _names(store: object) -> tuple[frozenset[str], frozenset[str]]:
        return (
            frozenset(c.__name__ for c in checks_for(store)),
            frozenset(c.__name__ for c, _ in unsupported_checks(store)),
        )

    # Act
    base_offered, base_missing = _names(_NodeStoreOnly())
    text_offered, text_missing = _names(_TextSearchableOnly())

    # Assert
    gained = text_offered - base_offered
    assert gained, "adding search_text offered no new check"
    assert gained <= base_missing, "a check that was gained was never reported as missing"
    assert gained & text_missing == frozenset(), "a check is offered and reported missing at once"


class _GenerationHoldingOnly(_NodeStoreOnly):
    """Holds generations and searches nothing, as `weft_kg`'s graph store does at ledger 43.39.

    Selection never calls these; each raises so a check that did would fail loudly here.
    """

    async def open_generation(self, layer: str) -> object:
        raise AssertionError(f"selection called open_generation({layer!r})")

    async def bind_generation(self, generation: str) -> object:
        raise AssertionError(f"selection called bind_generation({generation!r})")

    async def publish_generation(self, generation: str) -> object:
        raise AssertionError(f"selection called publish_generation({generation!r})")

    async def retract_generation(self, generation: str) -> object:
        raise AssertionError(f"selection called retract_generation({generation!r})")

    async def generations(self) -> tuple[object, ...]:
        raise AssertionError("selection called generations()")


#: The generation checks that read only through `NodeStore` and the catalogue (ledger 43.39).
_NODE_READ_GENERATION_CHECKS = frozenset(
    {
        "check_retracting_a_generation_removes_its_own_nodes_and_keeps_shared_ones",
        "check_a_generation_record_round_trips_and_an_unknown_one_is_refused_by_name",
        "check_a_handle_opened_before_any_node_was_stored_retracts_a_generations_nodes",
        "check_a_handle_opened_before_any_node_was_stored_reads_what_a_fresh_handle_reads",
    }
)


def test_a_store_that_holds_generations_without_searching_them_is_asked_what_it_can_answer() -> (
    None
):
    """Ledger 43.39: a check is offered only when a store has every capability it calls.

    The generation checks that search were keyed on `open_generation` alone, so a store that
    holds generations and has no search arm was offered them and failed with `AttributeError`.
    """
    # Arrange
    from weft_store.conformance import checks_for, unsupported_checks

    # Act
    offered = {check.__name__ for check in checks_for(_GenerationHoldingOnly())}
    reported = {c.__name__: needed for c, needed in unsupported_checks(_GenerationHoldingOnly())}

    # Assert
    assert offered >= _NODE_READ_GENERATION_CHECKS
    assert "check_an_unpublished_generation_is_invisible_until_it_is_published" not in offered
    assert reported["check_an_unpublished_generation_is_invisible_until_it_is_published"] in {
        "VectorSearch",
        "TextSearch",
        "MetadataFilter",
    }


def test_a_store_with_no_generations_is_offered_no_generation_check() -> None:
    # Arrange
    from weft_store.conformance import checks_for, unsupported_checks

    # Act
    offered = {check.__name__ for check in checks_for(_NodeStoreOnly())}
    reported = {c.__name__: needed for c, needed in unsupported_checks(_NodeStoreOnly())}

    # Assert
    assert offered & _NODE_READ_GENERATION_CHECKS == set()
    assert {reported[name] for name in _NODE_READ_GENERATION_CHECKS} == {"GenerationHolding"}


class _GenerationWithdrawingOnly(_GenerationHoldingOnly):
    """Holds and withdraws generations and searches nothing, as the graph store does at 43.40."""

    async def withdraw_generation(self, generation: str) -> object:
        raise AssertionError(f"selection called withdraw_generation({generation!r})")

    async def reclaim_withdrawn(self, layer: str) -> object:
        raise AssertionError(f"selection called reclaim_withdrawn({layer!r})")


def test_a_store_that_withdraws_without_searching_is_asked_the_refusal_check() -> None:
    """Ledger 43.40: the withdraw refusal reads only the catalogue; its siblings search."""
    # Arrange
    from weft_store.conformance import checks_for, unsupported_checks

    # Act
    offered = {check.__name__ for check in checks_for(_GenerationWithdrawingOnly())}
    reported = {
        c.__name__: needed for c, needed in unsupported_checks(_GenerationWithdrawingOnly())
    }
    base = {c.__name__: needed for c, needed in unsupported_checks(_GenerationHoldingOnly())}

    # Assert
    refusal = "check_withdrawing_an_unknown_or_unpublished_generation_is_refused_by_name"
    assert refusal in offered
    assert base[refusal] == "GenerationWithdrawing"
    assert reported["check_a_layer_rebuilt_twice_reads_as_one_tree_at_every_step"] in {
        "VectorSearch",
        "TextSearch",
        "MetadataFilter",
    }
