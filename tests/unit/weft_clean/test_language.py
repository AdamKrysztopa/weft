"""Unit tests for `weft_clean.language`.

Mirrors `packages/weft-rag/src/weft_clean/language.py`. Covers the one thing this
module states: `Language` is a real, namespaced `weft_kernel.payload.ExtModel`, not a
placeholder — the repair that closes a real gap tasks 1.7/1.8 left open, per the
module's own docstring.
"""

from weft_clean.language import Language
from weft_kernel.payload import ExtModel


def test_language_is_an_ext_model_namespaced_to_weft_clean() -> None:
    # Act / Assert
    assert issubclass(Language, ExtModel)
    assert Language.__namespace__ == "weft-clean"


def test_language_carries_a_code_field() -> None:
    # Act
    fact = Language(code="pl")

    # Assert
    assert fact.code == "pl"
