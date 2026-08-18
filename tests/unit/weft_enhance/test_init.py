"""Unit tests for `weft_enhance`'s `register()`.

Mirrors `packages/weft-enhance/src/weft_enhance/__init__.py`. Covers the happy path
(`register` adds `KeyBertKeywordExtractor` as `"keybert"` under `Enhancer`), and that an
unknown settings field is refused the way every pack settings model in this project
refuses one — `weft-enhance` takes no settings, so `extra` fields are the only shape its
`Settings` model can get wrong.
"""

import pytest
from pydantic import ValidationError

from weft_enhance import Settings, register
from weft_enhance.contract import Enhancer
from weft_enhance.keybert_stand_in import KeyBertKeywordExtractor
from weft_kernel.discovery import PackRegistrar
from weft_kernel.registry import Registry


def test_register_adds_keybert_stand_in_under_enhancer() -> None:
    # Arrange
    registry = Registry()
    registrar = PackRegistrar(registry, distribution="weft-enhance")

    # Act
    register(registrar, Settings())
    registrar.commit()

    # Assert
    entry = registry.entry(Enhancer, "keybert")
    assert entry.factory is KeyBertKeywordExtractor
    assert entry.distribution == "weft-enhance"


def test_settings_refuses_an_unknown_field() -> None:
    # Act / Assert
    with pytest.raises(ValidationError):
        Settings.model_validate({"bogus": "x"})
