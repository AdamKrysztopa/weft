"""Unit tests for `weft_kernel.payload.property`.

Mirrors `packages/weft-kernel/src/weft_kernel/payload/property.py`. Covers a
declared namespace being readable off the class, the same
class-definition-time refusal `ExtModel` gives a missing namespace
(`tests/unit/weft_kernel/payload/test_ext.py`), and that two `Property`
subclasses are distinct by identity even when nothing else about the check
tells them apart — the property `intact`/`destroys` comparison in
`weft_kernel.runner.Runner.resolve` depends on.
"""

import pytest

from weft_kernel.payload.property import Property


def test_a_declared_namespace_is_readable_as_a_class_attribute() -> None:
    # Arrange
    class WordBoundaries(Property):
        __namespace__ = "weft-chunk"

    # Act
    namespace = WordBoundaries.__namespace__

    # Assert
    assert namespace == "weft-chunk"


def test_two_subclasses_are_distinct_even_with_matching_namespaces() -> None:
    # Arrange — "no plugin ever names another plugin": comparison is by type identity,
    # never by the namespace string, so two unrelated packs minting classes under the same
    # namespace by mistake still do not collide.
    class First(Property):
        __namespace__ = "acme-pack"

    class Second(Property):
        __namespace__ = "acme-pack"

    # Act / Assert
    assert First is not Second
    assert First != Second


def test_declaring_a_subclass_with_no_namespace_raises_at_class_definition() -> None:
    # Arrange
    def _build_invalid_subclass() -> type[Property]:
        class NoNamespace(Property):
            pass

        return NoNamespace

    # Act / Assert
    with pytest.raises(TypeError, match="non-empty __namespace__"):
        _build_invalid_subclass()
