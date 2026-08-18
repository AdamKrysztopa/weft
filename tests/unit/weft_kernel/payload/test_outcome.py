"""Unit tests for `weft_kernel.payload.outcome`.

Mirrors `packages/weft-kernel/src/weft_kernel/payload/outcome.py`.
"""

import pytest
from pydantic import ValidationError

from weft_kernel.payload.outcome import Failed, NothingToProduce, Outcome, Produced


def _describe(outcome: Outcome[int]) -> str:
    """Exercises `Outcome` the way a kernel fallback combinator would: matched by type."""
    match outcome:
        case Produced(value=value):
            return f"produced {value}"
        case NothingToProduce(reason=reason):
            return f"nothing: {reason}"
        case Failed(reason=reason):
            return f"failed: {reason}"


def test_the_three_shapes_are_distinguishable_without_inspecting_payload_content() -> None:
    # Arrange
    outcomes: list[Outcome[int]] = [
        Produced(value=3),
        NothingToProduce(reason="upstream produced nothing for this node"),
        Failed(reason="the model call timed out"),
    ]

    # Act
    described = [_describe(outcome) for outcome in outcomes]

    # Assert
    assert described == [
        "produced 3",
        "nothing: upstream produced nothing for this node",
        "failed: the model call timed out",
    ]


def test_produced_is_frozen() -> None:
    # Arrange
    outcome = Produced(value=1)

    # Act / Assert
    with pytest.raises(ValidationError):
        outcome.value = 2  # type: ignore[misc]


def test_an_unknown_field_is_rejected_rather_than_silently_accepted() -> None:
    # Arrange / Act / Assert
    with pytest.raises(ValidationError):
        NothingToProduce(reason="ok", extra_field="not part of the contract")  # type: ignore[call-arg]
