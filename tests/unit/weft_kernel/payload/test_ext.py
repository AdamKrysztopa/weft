"""Unit tests for `weft_kernel.payload.ext`.

Mirrors `packages/weft-kernel/src/weft_kernel/payload/ext.py`.
"""

import pytest
from pydantic import ValidationError

from weft_kernel.payload.ext import ExtModel


def test_a_declared_namespace_and_transience_are_readable_as_class_attributes() -> None:
    # Arrange
    class GraphData(ExtModel):
        __namespace__ = "weft-graph"
        __transient__ = True

        entities: tuple[str, ...] = ()

    # Act
    instance = GraphData(entities=("Acme",))

    # Assert
    assert type(instance).__namespace__ == "weft-graph"
    assert type(instance).__transient__ is True


def test_transience_defaults_to_false() -> None:
    # Arrange
    class PlainData(ExtModel):
        __namespace__ = "weft-plain"

    # Act
    result = PlainData.__transient__

    # Assert
    assert result is False


def test_declaring_a_subclass_with_no_namespace_raises_at_class_definition() -> None:
    # Arrange
    def _build_invalid_subclass() -> type[ExtModel]:
        class NoNamespace(ExtModel):
            pass

        return NoNamespace

    # Act / Assert
    with pytest.raises(TypeError, match="non-empty __namespace__"):
        _build_invalid_subclass()


def test_an_ext_model_instance_is_frozen() -> None:
    # Arrange
    class GraphData(ExtModel):
        __namespace__ = "weft-graph"

        entities: tuple[str, ...] = ()

    instance = GraphData(entities=())

    # Act / Assert
    with pytest.raises(ValidationError):
        instance.entities = ("mutated",)  # type: ignore[misc]
