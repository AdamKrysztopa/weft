"""An OpenAI-compatible account asks for streamed usage only when told to — repair **R33.1**.

Task 33.6 made `OpenAILLMProvider` satisfy `weft_llm.contract.UsageReporting`, so it sends
`stream_options={"include_usage": true}` on every generation. OpenAI's own SDK documents that field
for OpenAI's API. `weft_openai_compatible` registers the same class for any server that speaks the
protocol, and whether a local server accepts the field was not measured — one that rejects unknown
fields would turn every answer into a 400 that worked before 33.6. The owner settled it on
2026-09-15: `[packs.openai-compatible] stream_usage`, default false.

**Driven through `build_dependencies`, as `test_register.py` is** — the value has to travel from a
`[packs.*]` block through discovery into the provider a role will call, and a test handing
`register` a `Settings` it built itself would assert nothing about that journey.
"""

from __future__ import annotations

from pathlib import Path

from weft_engine import registry_bootstrap
from weft_llm.contract import LLMProvider, UsageReporting


def _config(tmp_path: Path, compatible_block: str) -> Path:
    config = tmp_path / "weft.toml"
    config.write_text(
        "[packs.openai]\n"
        'api_key = "sk-hosted-account"\n'
        "\n"
        "[packs.openai-compatible]\n"
        'api_key = "sk-local-account"\n'
        'base_url = "http://127.0.0.1:11434/v1"\n' + compatible_block,
        encoding="utf-8",
    )
    return config


def _provider(config: Path, name: str) -> object:
    deps = registry_bootstrap.build_dependencies(config_path=config)
    return deps.registry.entry(LLMProvider, name).factory(None)


def test_a_compatible_account_does_not_ask_for_usage_by_default(tmp_path: Path) -> None:
    # Act
    provider = _provider(_config(tmp_path, ""), "openai-compatible")

    # Assert
    assert isinstance(provider, LLMProvider)
    assert not isinstance(provider, UsageReporting)


def test_a_compatible_account_asks_for_usage_when_its_settings_opt_in(tmp_path: Path) -> None:
    # Act
    provider = _provider(_config(tmp_path, "stream_usage = true\n"), "openai-compatible")

    # Assert
    assert isinstance(provider, UsageReporting)


def test_the_vendor_account_still_asks_for_usage(tmp_path: Path) -> None:
    """The control: the setting belongs to the compatible account, and the vendor's documented
    field stays on whatever the compatible block says.
    """
    # Act
    provider = _provider(_config(tmp_path, ""), "openai")

    # Assert
    assert isinstance(provider, UsageReporting)
