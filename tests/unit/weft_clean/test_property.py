"""Unit tests for `weft_clean.property`.

Mirrors `packages/weft-rag/src/weft_clean/property.py`. Covers the one
thing this module states: `Newlines`, `WhitespaceGaps` and `Verbatim` are
real, namespaced `weft_kernel.payload.Property` markers, not placeholders —
task 1.7, extended by task 2.35, `docs/02-extension-model.md` §3 →
*Ordering constraints*.
"""

from weft_clean.property import Newlines, Verbatim, WhitespaceGaps
from weft_kernel.payload import Property


def test_newlines_is_a_property_namespaced_to_weft_clean() -> None:
    # Act / Assert
    assert issubclass(Newlines, Property)
    assert Newlines.__namespace__ == "weft-clean"


def test_whitespace_gaps_is_a_property_namespaced_to_weft_clean() -> None:
    # Act / Assert
    assert issubclass(WhitespaceGaps, Property)
    assert WhitespaceGaps.__namespace__ == "weft-clean"


def test_verbatim_is_a_property_namespaced_to_weft_clean() -> None:
    # Act / Assert
    assert issubclass(Verbatim, Property)
    assert Verbatim.__namespace__ == "weft-clean"


def test_the_three_properties_are_distinct_types() -> None:
    # Arrange / Act / Assert — `intact`/`destroys` compare by type identity
    # (`weft_kernel.payload.property`'s own module docstring), so three
    # properties sharing a namespace must still never be the same class.
    assert Newlines is not WhitespaceGaps
    assert Newlines is not Verbatim
    assert WhitespaceGaps is not Verbatim
