"""Unit tests for `weft_openai`'s `register()`.

Mirrors `packages/weft-openai/src/weft_openai/__init__.py`. Covers the happy
path (`register` adds `OpenAIEmbedder` as `"openai-embeddings"` under the `Embedder`
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

import re

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
    entry = registry.entry(Embedder, "openai-embeddings")
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


def test_the_disclosure_names_no_endpoint_the_pack_cannot_reach() -> None:
    """Carried repair `R17.17`.

    The disclosure is what an operator reads to decide whether a pack may run, so an endpoint it
    names is a claim about where their data goes. This one named `OPENAI_BASE_URL`, on the stated
    reasoning that "the OpenAI SDK reads `OPENAI_BASE_URL` for itself when `base_url` is unset".

    It is never unset. `weft_openai.embedder.build_client` is the single construction point for
    all three of this pack's plugins — `llm.py` and `vision.py` both import it — and it passes
    `base_url=settings.base_url if settings.base_url is not None else VENDOR_BASE_URL`. So the SDK
    is never handed `None` and never consults the variable, and an operator who had set
    `OPENAI_BASE_URL` and read this disclosure would believe their traffic went to their own proxy
    while it went to the vendor. `manual/operations-guide.md` had already documented the truth.

    The positive half is asserted with it: the disclosure must still name the setting that *does*
    decide, because `02` §2's rule is that the disclosure names the knob rather than a bare host.
    """
    # Arrange
    from weft_openai import DISCLOSURE

    network = " ".join(DISCLOSURE.network)

    # Assert — stated as the class, not as the one instance. The first version of this test
    # named `OPENAI_BASE_URL` alone and passed against a note that still said the credential
    # comes from "[packs.openai] api_key or OPENAI_API_KEY", which is false by the identical
    # mechanism: `build_client` passes `api_key=` explicitly too, and two shipped pipeline
    # documents plus `manual/troubleshooting.md:2112 "deliberately does *not* read"` say the pack
    # does not read `OPENAI_API_KEY` on its own. A check narrower than the defect it was
    # written for is `L17.4`'s shape, and it reproduced here inside the repair for it.
    spelled = f"{network} {DISCLOSURE.note}"
    for variable in re.findall(r"\bOPENAI_[A-Z_]+\b", spelled):
        assert f"${{env:{variable}}}" in spelled, (
            f"the disclosure names {variable} as something this pack reads. It does not: "
            f"`build_client` passes every one of these explicitly, so the SDK never falls back "
            f"to the environment. A variable may appear only in the `${{env:...}}` spelling, "
            f"which is the settings loader interpolating it — a different mechanism."
        )
    assert "base_url" in network
