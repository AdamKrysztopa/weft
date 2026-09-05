"""Unit tests for `weft_extract`'s `register()`.

Mirrors `packages/weft-rag/src/weft_extract/__init__.py`. Covers the
happy path (`register` adds `TextExtractor` as `"text"` under `Extractor`),
and that an unknown settings field is refused — `weft-extract` takes no
settings, so `extra` fields are the only shape its `Settings` model can get
wrong.
"""

import pytest
from pydantic import ValidationError

from weft_extract import Settings, TextExtractor, register
from weft_extract.contract import Extractor
from weft_kernel.discovery import PackRegistrar
from weft_kernel.registry import Registry


def test_register_adds_text_extractor_under_extractor() -> None:
    # Arrange
    registry = Registry()
    registrar = PackRegistrar(registry, distribution="weft-extract")

    # Act
    register(registrar, Settings())
    registrar.commit()

    # Assert
    entry = registry.entry(Extractor, "text")
    assert entry.factory is TextExtractor
    assert entry.distribution == "weft-extract"


def test_settings_refuses_an_unknown_field() -> None:
    # Act / Assert
    with pytest.raises(ValidationError):
        Settings.model_validate({"bogus": "x"})
