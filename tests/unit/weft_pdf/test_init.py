"""Unit tests for `weft_pdf`'s `register()`.

Mirrors `packages/weft-pdf/src/weft_pdf/__init__.py`. The property under test is
the one the whole pack exists for: **two** names under the **one** `Extractor`
contract `weft-extract` publishes, so choosing a parser is choosing a name and
nothing else. A pack that registered one name and branched inside it would pass
every other test in this directory and fail this one.
"""

import pytest
from pydantic import ValidationError

from weft_extract.contract import Extractor
from weft_kernel.discovery import PackRegistrar
from weft_kernel.registry import Registry
from weft_pdf import PdfLayoutExtractor, PdfTextExtractor, Settings, register


def test_register_adds_both_backends_under_the_one_extractor_contract() -> None:
    # Arrange
    registry = Registry()
    registrar = PackRegistrar(registry, distribution="weft-pdf")

    # Act
    register(registrar, Settings())
    registrar.commit()

    # Assert
    assert registry.entry(Extractor, "pdf-text").factory is PdfTextExtractor
    assert registry.entry(Extractor, "pdf-layout").factory is PdfLayoutExtractor
    assert registry.entry(Extractor, "pdf-text").distribution == "weft-pdf"
    assert registry.entry(Extractor, "pdf-layout").distribution == "weft-pdf"


def test_settings_refuses_an_unknown_field() -> None:
    # Act / Assert
    with pytest.raises(ValidationError):
        Settings.model_validate({"bogus": "x"})
