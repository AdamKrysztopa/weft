"""Unit tests for `weft_kernel.payload.media_type`.

Mirrors `packages/weft-kernel/src/weft_kernel/payload/media_type.py`.
"""

from weft_kernel.payload.media_type import MediaType


def test_members_carry_their_string_value() -> None:
    # Arrange / Act / Assert
    assert MediaType.TEXT.value == "text"
    assert MediaType.IMAGE.value == "image"
    assert MediaType.TABLE.value == "table"


def test_a_member_compares_equal_to_its_plain_string() -> None:
    # Arrange
    media_type = MediaType.TEXT

    # Act / Assert
    assert media_type == "text"
