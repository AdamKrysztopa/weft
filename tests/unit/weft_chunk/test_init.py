"""Unit tests for `weft_chunk`'s `register()`.

Mirrors `packages/weft-rag/src/weft_chunk/__init__.py`. Covers the happy
path (`register` adds `FixedSizeChunker` as `"fixed-size"` under `Chunker`),
and that an unknown settings field is refused — `weft-chunk` takes no
settings, so `extra` fields are the only shape its `Settings` model can get
wrong.
"""

import pytest
from pydantic import ValidationError

from weft_chunk import FixedSizeChunker, Settings, register
from weft_chunk.contract import Chunker
from weft_kernel.discovery import PackRegistrar
from weft_kernel.registry import Registry


def test_register_adds_fixed_size_chunker_under_chunker() -> None:
    # Arrange
    registry = Registry()
    registrar = PackRegistrar(registry, distribution="weft-chunk")

    # Act
    register(registrar, Settings())
    registrar.commit()

    # Assert
    entry = registry.entry(Chunker, "fixed-size")
    assert entry.factory is FixedSizeChunker
    assert entry.distribution == "weft-chunk"


def test_settings_refuses_an_unknown_field() -> None:
    # Act / Assert
    with pytest.raises(ValidationError):
        Settings.model_validate({"bogus": "x"})
