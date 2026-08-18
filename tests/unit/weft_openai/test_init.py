"""Unit tests for `weft_openai`'s `register()`.

Mirrors `packages/weft-openai/src/weft_openai/__init__.py`. Covers the happy
path (`register` adds `OpenAIEmbedder` as `"openai"` under the `Embedder`
contract `weft-embed` publishes), the property the whole pack depends on —
**every settings field carries a default**, so `register()` runs and
contributes its plugin on a machine with no credential at all — and the
error case of an unknown settings field.

The default matters more than it looks. A required `api_key` would make
`register()` raise, the pack would report `failed` with nothing contributed,
and `openai` would disappear from the registry, from
`manual/contract-reference.md` and from fitness function 11(b)'s resolution
check **with no test failing anywhere**. A missing credential has to fail at
use — `tests/unit/weft_openai/test_embedder.py` is where that is checked.
"""

import pytest
from pydantic import ValidationError

from weft_embed.contract import Embedder
from weft_kernel.discovery import PackRegistrar
from weft_kernel.registry import Registry
from weft_llm.contract import LLMProvider
from weft_openai import Settings, register
from weft_openai.embedder import OpenAIEmbedder
from weft_openai.llm import OpenAILLMProvider


def test_register_adds_the_openai_embedder_under_the_embedder_contract() -> None:
    # Arrange
    registry = Registry()
    registrar = PackRegistrar(registry, distribution="weft-openai")

    # Act
    register(registrar, Settings())
    registrar.commit()

    # Assert
    entry = registry.entry(Embedder, "openai")
    assert entry.distribution == "weft-openai"
    assert isinstance(entry.factory(None), OpenAIEmbedder)


def test_register_adds_the_openai_llm_provider_under_the_llmprovider_contract() -> None:
    # Arrange — task 2.30: the same account registers a second capability.
    registry = Registry()
    registrar = PackRegistrar(registry, distribution="weft-openai")

    # Act
    register(registrar, Settings())
    registrar.commit()

    # Assert
    entry = registry.entry(LLMProvider, "openai")
    assert entry.distribution == "weft-openai"
    assert isinstance(entry.factory(None), OpenAILLMProvider)


def test_settings_are_constructible_with_no_credential_so_registration_cannot_fail() -> None:
    # Act — no argument at all, which is what discovery hands a pack with no settings block.
    settings = Settings()

    # Assert
    assert settings.api_key.get_secret_value() == ""


def test_settings_refuse_an_unknown_field() -> None:
    # Act / Assert
    with pytest.raises(ValidationError):
        Settings.model_validate({"api_ky": "sk-typo"})
