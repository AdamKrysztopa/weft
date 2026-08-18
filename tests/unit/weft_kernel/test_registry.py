"""Unit tests for `weft_kernel.registry`.

Mirrors `packages/weft-kernel/src/weft_kernel/registry.py`. Covers a
successful registration and lookup, the fixed-and-not-arbitrated duplicate
refusal `docs/06-phase-0-build.md` takes for G2's open question, the loud
unknown-name error `docs/02-extension-model.md` specifies, and `add_many`'s
all-or-nothing commit — a collision against an existing entry and a
collision within the batch itself both leave the registry exactly as they
found it.
"""

import pytest

from weft_kernel.registry import DuplicateRegistrationError, Registry, UnknownPluginError


class _Chunker:
    """A stand-in contract. `Registry` must not know or care what this is."""


class _Extractor:
    """A second, unrelated contract, used to show the key includes the contract."""


def test_add_then_lookup_returns_the_registered_factory() -> None:
    # Arrange
    registry = Registry()
    factory = lambda: "a chunker instance"  # noqa: E731 - stand-in, not production code

    # Act
    registry.add(_Chunker, "fixed-size", factory, distribution="weft-chunk")
    resolved = registry.lookup(_Chunker, "fixed-size")

    # Assert
    assert resolved is factory


def test_duplicate_registration_is_refused_naming_both_distributions() -> None:
    # Arrange
    registry = Registry()
    first_factory = lambda: "the first registration"  # noqa: E731 - stand-in, not production code
    registry.add(_Chunker, "semantic", first_factory, distribution="weft-chunk")

    # Act / Assert
    with pytest.raises(DuplicateRegistrationError) as excinfo:
        registry.add(
            _Chunker, "semantic", lambda: "the refused second one", distribution="weft-graph"
        )

    message = str(excinfo.value)
    assert "weft-chunk" in message
    assert "weft-graph" in message
    assert "semantic" in message
    assert registry.lookup(_Chunker, "semantic") is first_factory


def test_entry_returns_the_factory_and_the_distribution_that_registered_it() -> None:
    # Arrange
    registry = Registry()
    factory = lambda: "an entry's factory"  # noqa: E731 - stand-in, not production code
    registry.add(_Chunker, "semantic", factory, distribution="weft-chunk")

    # Act
    found = registry.entry(_Chunker, "semantic")

    # Assert
    assert found.factory is factory
    assert found.distribution == "weft-chunk"


def test_entry_raises_the_same_unknown_plugin_error_as_lookup() -> None:
    # Arrange
    registry = Registry()

    # Act / Assert
    with pytest.raises(UnknownPluginError) as excinfo:
        registry.entry(_Chunker, "missing")

    assert "missing" in str(excinfo.value)
    assert "Chunker" in str(excinfo.value)


def test_unknown_name_lists_the_wanted_name_and_only_its_own_contracts_options() -> None:
    # Arrange
    registry = Registry()
    registry.add(_Chunker, "fixed-size", lambda: None, distribution="weft-chunk")
    registry.add(_Extractor, "pdf", lambda: None, distribution="weft-extract")

    # Act / Assert
    with pytest.raises(UnknownPluginError) as excinfo:
        registry.lookup(_Chunker, "semantic")

    message = str(excinfo.value)
    assert "semantic" in message
    assert "Chunker" in message
    assert "fixed-size" in message
    assert "pdf" not in message


def test_add_many_commits_every_entry_from_one_distribution() -> None:
    # Arrange
    registry = Registry()

    # Act
    registry.add_many(
        [
            (_Chunker, "a", lambda: "a"),
            (_Chunker, "b", lambda: "b"),
        ],
        distribution="weft-chunk",
    )

    # Assert
    assert registry.lookup(_Chunker, "a")() == "a"
    assert registry.lookup(_Chunker, "b")() == "b"


def test_add_many_rejects_a_collision_against_an_existing_entry_and_writes_nothing() -> None:
    # Arrange
    registry = Registry()
    registry.add(_Chunker, "taken", lambda: "first", distribution="weft-chunk")

    # Act / Assert
    with pytest.raises(DuplicateRegistrationError) as excinfo:
        registry.add_many(
            [
                (_Chunker, "new", lambda: "new"),
                (_Chunker, "taken", lambda: "second"),
            ],
            distribution="weft-graph",
        )

    assert "weft-chunk" in str(excinfo.value)
    with pytest.raises(UnknownPluginError):
        registry.lookup(_Chunker, "new")


def test_contracts_is_empty_on_a_fresh_registry() -> None:
    # Arrange
    registry = Registry()

    # Act / Assert
    assert registry.contracts() == frozenset()


def test_contracts_returns_every_distinct_contract_with_at_least_one_registration() -> None:
    # Arrange
    registry = Registry()
    registry.add(_Chunker, "fixed-size", lambda: None, distribution="weft-chunk")
    registry.add(_Chunker, "semantic", lambda: None, distribution="weft-graph")
    registry.add(_Extractor, "pdf", lambda: None, distribution="weft-extract")

    # Act
    contracts = registry.contracts()

    # Assert — two names under `_Chunker` still count once; the key is the contract itself.
    assert contracts == frozenset({_Chunker, _Extractor})


def test_distributions_for_returns_every_distribution_that_registered_the_contract() -> None:
    # Arrange
    registry = Registry()
    registry.add(_Chunker, "fixed-size", lambda: None, distribution="weft-chunk")
    registry.add(_Chunker, "semantic", lambda: None, distribution="weft-graph")

    # Act
    distributions = registry.distributions_for(_Chunker)

    # Assert
    assert distributions == frozenset({"weft-chunk", "weft-graph"})


def test_distributions_for_an_unregistered_contract_is_empty() -> None:
    # Arrange
    registry = Registry()

    # Act / Assert
    assert registry.distributions_for(_Extractor) == frozenset()


def test_add_many_rejects_a_duplicate_name_within_its_own_batch_and_writes_nothing() -> None:
    # Arrange
    registry = Registry()

    # Act / Assert
    with pytest.raises(DuplicateRegistrationError) as excinfo:
        registry.add_many(
            [
                (_Chunker, "twice", lambda: "first"),
                (_Chunker, "twice", lambda: "second"),
            ],
            distribution="weft-chunk",
        )

    assert "twice" in str(excinfo.value)
    with pytest.raises(UnknownPluginError):
        registry.lookup(_Chunker, "twice")
