"""Unit tests for `weft_kernel.payload.vector`.

Mirrors `packages/weft-kernel/src/weft_kernel/payload/vector.py`.
"""

import pytest
from pydantic import ValidationError

from weft_kernel.payload.vector import Vector


def test_dimension_reports_the_number_of_components() -> None:
    # Arrange
    vector = Vector(values=(0.1, 0.2, 0.3))

    # Act
    result = vector.dimension

    # Assert
    assert result == 3


def test_a_vector_is_frozen() -> None:
    # Arrange
    vector = Vector(values=(1.0,))

    # Act / Assert
    with pytest.raises(ValidationError):
        vector.values = (2.0,)  # type: ignore[misc]


def test_an_empty_vector_raises() -> None:
    # Arrange / Act / Assert
    with pytest.raises(ValidationError, match="at least one dimension"):
        Vector(values=())
