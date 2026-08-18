"""Unit tests for `weft_clean`'s `register()`.

Mirrors `packages/weft-clean/src/weft_clean/__init__.py`. Covers the happy
path (`register` adds all four plugins under `Cleaner`), and that an unknown
settings field is refused — `weft-clean` takes no settings, so `extra`
fields are the only shape its `Settings` model can get wrong.
"""

import pytest
from pydantic import ValidationError

from weft_clean import (
    HyphenationRepair,
    PolishFusedWordFixer,
    Settings,
    TableLinearizer,
    WhitespaceNormalizer,
    register,
)
from weft_clean.contract import Cleaner
from weft_kernel.discovery import PackRegistrar
from weft_kernel.registry import Registry


def test_register_adds_all_four_plugins_under_cleaner() -> None:
    # Arrange
    registry = Registry()
    registrar = PackRegistrar(registry, distribution="weft-clean")

    # Act
    register(registrar, Settings())
    registrar.commit()

    # Assert
    assert registry.entry(Cleaner, "hyphenation").factory is HyphenationRepair
    assert registry.entry(Cleaner, "table-linearize").factory is TableLinearizer
    assert registry.entry(Cleaner, "polish-dictionary-spacing").factory is PolishFusedWordFixer
    assert registry.entry(Cleaner, "whitespace").factory is WhitespaceNormalizer
    for name in ("hyphenation", "table-linearize", "polish-dictionary-spacing", "whitespace"):
        assert registry.entry(Cleaner, name).distribution == "weft-clean"


def test_settings_refuses_an_unknown_field() -> None:
    # Act / Assert
    with pytest.raises(ValidationError):
        Settings.model_validate({"bogus": "x"})
