"""Unit tests for `weft_clean.property`.

Mirrors `packages/weft-clean/src/weft_clean/property.py`. Covers the one
thing this module states: `Newlines` and `WhitespaceGaps` are real,
namespaced `weft_kernel.payload.Property` markers, not placeholders — task
1.7, `docs/02-extension-model.md` §3 → *Ordering constraints*.
"""

from weft_clean.property import Newlines, WhitespaceGaps
from weft_kernel.payload import Property


def test_newlines_is_a_property_namespaced_to_weft_clean() -> None:
    # Act / Assert
    assert issubclass(Newlines, Property)
    assert Newlines.__namespace__ == "weft-clean"


def test_whitespace_gaps_is_a_property_namespaced_to_weft_clean() -> None:
    # Act / Assert
    assert issubclass(WhitespaceGaps, Property)
    assert WhitespaceGaps.__namespace__ == "weft-clean"


def test_the_two_properties_are_distinct_types() -> None:
    # Arrange / Act / Assert — `intact`/`destroys` compare by type identity
    # (`weft_kernel.payload.property`'s own module docstring), so two
    # properties sharing a namespace must still never be the same class.
    assert Newlines is not WhitespaceGaps
