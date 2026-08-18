"""Unit tests for `weft_kernel.errors`.

Mirrors `packages/weft-kernel/src/weft_kernel/errors.py`.
"""

import pytest

from weft_kernel.errors import WeftError


def test_carries_message_and_defaults_transient_to_false() -> None:
    # Arrange / Act
    error = WeftError("the model call timed out")

    # Assert
    assert str(error) == "the model call timed out"
    assert error.transient is False
    assert (error.pack, error.contract, error.plugin, error.stage) == (None, None, None, None)


def test_attribution_fields_are_settable_at_construction() -> None:
    # Arrange / Act
    error = WeftError(
        "the graph store rejected the write",
        transient=True,
        pack="weft-graph",
        contract="Store",
        plugin="neo4j",
        stage="persist",
    )

    # Assert
    assert error.transient is True
    assert (error.pack, error.contract, error.plugin, error.stage) == (
        "weft-graph",
        "Store",
        "neo4j",
        "persist",
    )


def test_a_pack_specific_subclass_is_catchable_as_weft_error() -> None:
    # Arrange
    class GraphConnectionError(WeftError):
        """A pack's own error, subclassing the kernel root."""

    # Act / Assert
    with pytest.raises(WeftError):
        raise GraphConnectionError("could not reach bolt://localhost:7687")
