"""Unit tests for `weft_embed`'s `register()`.

Mirrors `packages/weft-rag/src/weft_embed/__init__.py`. Covers the happy
path (`register` adds `HashEmbedder` as `"hash"` under `Embedder`), and that
an unknown settings field is refused the way every pack settings model in
this project refuses one — `weft-embed` takes no settings, so `extra` fields
are the only shape its `Settings` model can get wrong.
"""

import pytest
from pydantic import ValidationError

from weft_embed import Settings, register
from weft_embed.contract import Embedder
from weft_embed.hash_embedder import HashEmbedder
from weft_kernel.discovery import PackRegistrar
from weft_kernel.registry import Registry


def test_register_adds_hash_embedder_under_embedder() -> None:
    # Arrange
    registry = Registry()
    registrar = PackRegistrar(registry, distribution="weft-embed")

    # Act
    register(registrar, Settings())
    registrar.commit()

    # Assert
    entry = registry.entry(Embedder, "hash")
    assert entry.factory is HashEmbedder
    assert entry.distribution == "weft-embed"


def test_settings_refuses_an_unknown_field() -> None:
    # Act / Assert
    with pytest.raises(ValidationError):
        Settings.model_validate({"bogus": "x"})
