"""Unit tests for `weft_cli.contract_reference`.

Mirrors `packages/weft-cli/src/weft_cli/contract_reference.py`. Covers the happy path
(walking the real, installed first-party contracts, `NodeStore`'s `VectorSearch`
capability sibling included), the edge case (a rendered method reflects the real
signature and docstring, never a hand-typed approximation), and the error case
(`missing_from_walked_set` actually reports what it is asked to, and respects the
waiver). `tests/docs/test_generated_docs.py` is the check against the checked-in file;
this module is the plumbing that produces it.
"""

from __future__ import annotations

import pytest

from weft_chunk.contract import Chunker
from weft_cli.contract_reference import (
    ContractNotDescribableError,
    PublishedContract,
    discover_for_reference,
    missing_from_walked_set,
    published_contracts,
    render_contract_reference,
)
from weft_store.contract import NodeStore, VectorSearch


def test_published_contracts_includes_vectorsearch_beside_nodestore() -> None:
    # Arrange
    registry = discover_for_reference()

    # Act
    contracts = {
        published.contract: published.distributions for published in published_contracts(registry)
    }

    # Assert — VectorSearch is never registered under its own name (weft_store.contract's
    # own module docstring), so this is only true if the capability-sibling walk ran.
    assert NodeStore in contracts
    assert VectorSearch in contracts
    assert contracts[VectorSearch] == contracts[NodeStore] == frozenset({"weft-store"})


def test_render_contract_reference_reflects_the_real_signature() -> None:
    # Arrange
    registry = discover_for_reference()
    contracts = published_contracts(registry)

    # Act
    rendered = render_contract_reference(contracts)

    # Assert — the edge case: a method's own signature, not a hand-typed approximation.
    # `Chunker.run` takes a `Sequence[Node]` and returns `Outcome[Sequence[Node]]`; if the
    # contract's signature ever changes, these strings change with it because
    # `inspect.signature` read it off the live class, not off a copy in this test. Checked
    # as separate substrings, not one exact line, because `render_contract_reference`
    # pipes its output through `ruff format`, which may wrap a long signature onto
    # several lines — see that function's own docstring for why.
    assert "async def run(" in rendered
    assert "payload: collections.abc.Sequence[weft_kernel.payload.node.Node]" in rendered
    assert "-> weft_kernel.payload.outcome.Outcome[" in rendered
    assert "collections.abc.Sequence[weft_kernel.payload.node.Node]\n]: ..." in rendered
    assert Chunker.__doc__ is not None
    assert Chunker.__doc__.strip().splitlines()[0] in rendered


def test_missing_from_walked_set_reports_an_unwalked_registered_contract() -> None:
    # Arrange
    class _Registered:
        """Stand-in: reported by the registry."""

    # Act
    missing = missing_from_walked_set(
        registered=frozenset({_Registered}), walked=frozenset(), waived=frozenset()
    )

    # Assert
    assert missing == {_Registered}


def test_missing_from_walked_set_respects_a_named_waiver() -> None:
    # Arrange
    class _Registered:
        """Stand-in: reported by the registry, but deliberately waived."""

    # Act
    missing = missing_from_walked_set(
        registered=frozenset({_Registered}),
        walked=frozenset(),
        waived=frozenset({_Registered.__qualname__}),
    )

    # Assert
    assert missing == frozenset()


def test_render_contract_reference_normalises_optional_to_a_native_union() -> None:
    # Arrange
    registry = discover_for_reference()
    contracts = published_contracts(registry)

    # Act
    rendered = render_contract_reference(contracts)

    # Assert — `NodeStore.scan`'s source reads `cursor: Cursor | None = None`, but a
    # `NewType` unioned with `None` evaluates, at class-body time, to
    # `typing.Optional[Cursor]` (see the module's own docstring). The rendered reference
    # reads the way `docs/02-extension-model.md`'s own examples and CLAUDE.md's rule
    # ("native 3.12 type hints") require: `X | None`, and `Optional` never appears.
    assert "cursor: weft_store.contract.Cursor | None = None" in rendered
    assert "Optional" not in rendered


def test_render_contract_reference_raises_for_a_contract_with_no_version() -> None:
    # Arrange
    class _Versionless:
        """Stand-in: satisfies no real contract, carries no `.version`."""

    contracts = (PublishedContract(contract=_Versionless, distributions=frozenset({"weft-test"})),)

    # Act / Assert — a contract the generator cannot describe stops generation rather
    # than being described with an invented `unversioned` placeholder.
    with pytest.raises(ContractNotDescribableError, match="carries no `.version`"):
        render_contract_reference(contracts)


def test_render_contract_reference_raises_for_a_contract_with_no_protocol_attrs() -> None:
    # Arrange
    class _NotAProtocol:
        """Stand-in: has a version, but is not a runtime-checkable Protocol."""

        version = "1.0.0"

    contracts = (PublishedContract(contract=_NotAProtocol, distributions=frozenset({"weft-test"})),)

    # Act / Assert — a contract exposing no `__protocol_attrs__` stops generation rather
    # than being described with an empty `### Methods` section.
    with pytest.raises(ContractNotDescribableError, match="__protocol_attrs__"):
        render_contract_reference(contracts)
