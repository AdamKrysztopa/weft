"""Unit tests for `weft_index.contract` — ledger task **10.23**.

Mirrors `packages/weft-rag/src/weft_index/contract.py`. Covers the `Revisable` contract that
grilling session **G15**'s *Read* face settled: what a stage may see beyond the payload it was
handed.
"""

from collections.abc import Sequence

from weft_index.contract import (
    EXPANDER_CONTRACT_VERSION,
    REVISABLE_CONTRACT_VERSION,
    Expander,
    Revisable,
)
from weft_kernel.context import Context
from weft_kernel.payload import Node, Outcome, Produced


class _Revising:
    """A stranger's `Revisable`, implementing `run` and declaring nothing."""

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        return Produced(value=payload)


def test_revisable_is_satisfied_by_implementing_run_and_nothing_else() -> None:
    """Capability is derived, never declared — G4, and the reason `version` sits outside the body.

    A `Revisable` announces nothing about itself. If satisfying this contract ever required an
    attribute, a pack could write a false one, which is the whole thing `02` §1 refuses.
    """
    # Arrange & Act & Assert
    attrs = getattr(Revisable, "__protocol_attrs__", frozenset[str]())
    assert attrs == {"run"}, (
        "satisfying `Revisable` must need `run` and nothing else — anything more is a declaration "
        f"a pack could get wrong: {attrs}"
    )
    assert isinstance(_Revising(), Revisable)


def test_revisable_and_expander_are_structurally_identical_and_that_is_recorded() -> None:
    """**The distinction is the registration, not `isinstance`, and pinning that is the point.**

    Both contracts are `Stage[Sequence[Node], Sequence[Node]]` with `run` alone, so a class
    satisfying one satisfies the other and no runtime check can separate them. What separates them
    is which contract a pack *registers* under, which is what `weft pipeline show` prints and what
    a reader of a resolved document sees: `Expander:raptor` reads no store, `Revisable:adrap` does.

    This test exists so that nobody later "fixes" the ambiguity by adding a marker attribute to one
    of them. That would make capability *declared* rather than derived — `02` §1's refusal, and
    `Revisable.__protocol_attrs__` above is the assertion it would break.
    """
    # Arrange & Act & Assert
    expander_attrs = getattr(Expander, "__protocol_attrs__", frozenset[str]())
    revisable_attrs = getattr(Revisable, "__protocol_attrs__", frozenset[str]())
    assert expander_attrs == revisable_attrs
    assert expander_attrs, "both sets are empty, so this comparison proves nothing"
    assert isinstance(_Revising(), Expander), (
        "structural identity is the honest state of these two contracts; if this ever fails, one "
        "of them has grown a declared marker and G4's derived-capability rule has been broken"
    )


def test_revisable_carries_its_own_version_separate_from_the_expander_s() -> None:
    """Two contracts, two version constants — they move for different reasons.

    `Expander` is the shape every derived-node technique in this pack already satisfies;
    `Revisable` is new at task 10.23 and starts at `1.0.0`. Sharing a constant would mean a change
    to either forcing a bump readers would have to attribute by hand, which is the two-lists bug
    fitness function 6 exists to keep out of version numbers.
    """
    # Arrange & Act & Assert
    assert REVISABLE_CONTRACT_VERSION == "1.0.0"
    assert Revisable.version == REVISABLE_CONTRACT_VERSION
    assert Expander.version == EXPANDER_CONTRACT_VERSION
