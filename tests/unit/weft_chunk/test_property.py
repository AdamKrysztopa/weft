"""Unit tests for `weft_chunk.property`.

Mirrors `packages/weft-rag/src/weft_chunk/property.py`. Covers the one
thing this module states: `WordBoundaries` is a real, namespaced
`weft_kernel.payload.Property` marker, not a placeholder — task 1.2,
`docs/02-extension-model.md` §3 → *Ordering constraints*.
"""

from weft_chunk.property import WordBoundaries
from weft_kernel.payload import Property


def test_word_boundaries_is_a_property_namespaced_to_weft_chunk() -> None:
    # Act / Assert
    assert issubclass(WordBoundaries, Property)
    assert WordBoundaries.__namespace__ == "weft-chunk"
