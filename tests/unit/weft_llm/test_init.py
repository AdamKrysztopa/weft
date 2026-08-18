"""Unit tests for `weft_llm`'s `register()`.

Mirrors `packages/weft-openai/src/weft_openai/test_init.py`'s own shape and the property it
exists to check: every `Settings` field carries a default (here, there are none at all), so
`register()` never raises and `scripted` is always in the registry — the offline default
`.phase2-design.md` §1's derived rule exists to protect, applied to the pack that ships it
rather than to a vendor adapter.
"""

from weft_kernel.discovery import PackRegistrar
from weft_kernel.registry import Registry
from weft_llm import Settings, register
from weft_llm.contract import LLMProvider
from weft_llm.scripted import ScriptedProvider


def test_register_adds_the_scripted_provider_under_the_llmprovider_contract() -> None:
    # Arrange
    registry = Registry()
    registrar = PackRegistrar(registry, distribution="weft-llm")

    # Act
    register(registrar, Settings())
    registrar.commit()

    # Assert
    entry = registry.entry(LLMProvider, "scripted")
    assert entry.distribution == "weft-llm"
    assert isinstance(entry.factory(None), ScriptedProvider)


def test_settings_take_no_fields_so_registration_can_never_fail_on_a_credential() -> None:
    # Act — no argument at all, which is what discovery hands a pack with no settings block.
    settings = Settings()

    # Assert
    assert settings.model_dump() == {}
