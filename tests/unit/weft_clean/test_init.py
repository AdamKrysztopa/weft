"""Unit tests for `weft_clean`'s `register()`.

Mirrors `packages/weft-clean/src/weft_clean/__init__.py`. Covers the happy
path (`register` adds all six plugins under `Cleaner`, task 2.35 having
added `UnicodeNormalizer` and `ArtifactRemover` to the four task 1.7
shipped), and that an unknown settings field is refused — `weft-clean`
takes no settings, so `extra` fields are the only shape its `Settings`
model can get wrong.
"""

import pytest
from pydantic import ValidationError

from weft_clean import (
    ArtifactRemover,
    HyphenationRepair,
    PolishFusedWordFixer,
    Settings,
    TableLinearizer,
    UnicodeNormalizer,
    WhitespaceNormalizer,
    register,
)
from weft_clean.contract import Cleaner
from weft_kernel.discovery import PackRegistrar
from weft_kernel.registry import Registry

_REGISTERED_NAMES = (
    "unicode-normalize",
    "artifact-remove",
    "hyphenation",
    "table-linearize",
    "polish-dictionary-spacing",
    "whitespace",
)


def test_register_adds_all_six_plugins_under_cleaner() -> None:
    # Arrange
    registry = Registry()
    registrar = PackRegistrar(registry, distribution="weft-clean")

    # Act
    register(registrar, Settings())
    registrar.commit()

    # Assert
    assert registry.entry(Cleaner, "unicode-normalize").factory is UnicodeNormalizer
    assert registry.entry(Cleaner, "artifact-remove").factory is ArtifactRemover
    assert registry.entry(Cleaner, "hyphenation").factory is HyphenationRepair
    assert registry.entry(Cleaner, "table-linearize").factory is TableLinearizer
    assert registry.entry(Cleaner, "polish-dictionary-spacing").factory is PolishFusedWordFixer
    assert registry.entry(Cleaner, "whitespace").factory is WhitespaceNormalizer
    for name in _REGISTERED_NAMES:
        assert registry.entry(Cleaner, name).distribution == "weft-clean"


def test_settings_refuses_an_unknown_field() -> None:
    # Act / Assert
    with pytest.raises(ValidationError):
        Settings.model_validate({"bogus": "x"})
