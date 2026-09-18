"""The OpenAI provider counts tokens for the models its encoder knows — ledger task **32.6**.

Counting uses the encoding the vendor's own tokenizer library maps each model to, and a model it
has no mapping for is answered `None`, which `LLMClient.count_tokens` turns into a refusal
naming the role — never a fallback encoding, because a wrong count would silently overfill or
underfill every budgeted prompt. The Polish sentence below is one where the two recent encodings
disagree (14 tokens against 15), so the test can tell which one was used.

An OpenAI-compatible account never counts, whatever `stream_usage` says: a local server's model
names are not the vendor's, and one aliased to a vendor name would be counted with the wrong
encoding. `R33.1` is the same trap for usage reporting, and the same delegation withholds it.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path

import pytest
import tiktoken
from pydantic import SecretStr

from weft_engine import registry_bootstrap
from weft_llm.contract import LLMProvider, TokenCounting
from weft_openai import Settings
from weft_openai.llm import DEFAULT_MODEL, OpenAILLMProvider

_POLISH = "Zażółć gęślą jaźń — Wisła"


def _provider() -> OpenAILLMProvider:
    return OpenAILLMProvider(Settings(api_key=SecretStr("sk-test")))


def test_the_vendor_provider_offers_counting() -> None:
    # Act / Assert
    assert isinstance(_provider(), TokenCounting)


async def test_the_shipped_default_model_is_counted_with_the_encoding_its_vendor_maps_it_to() -> (
    None
):
    # Arrange
    expected = len(tiktoken.encoding_for_model(DEFAULT_MODEL).encode(_POLISH))
    other = len(tiktoken.get_encoding("cl100k_base").encode(_POLISH))
    assert expected != other, "the fixture must separate the two encodings"

    # Act
    count = await _provider().count_tokens(_POLISH, model=DEFAULT_MODEL)

    # Assert
    assert count == expected


@pytest.mark.parametrize("model", ["llama3.1:8b", "qwen2.5", "nomic-embed-text"])
async def test_a_model_the_encoder_has_no_mapping_for_is_answered_none(model: str) -> None:
    # Act / Assert
    assert await _provider().count_tokens(_POLISH, model=model) is None


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


@pytest.mark.parametrize("compatible_block", ["", "stream_usage = true\n"])
def test_an_openai_compatible_account_never_counts(tmp_path: Path, compatible_block: str) -> None:
    # Arrange
    deps = registry_bootstrap.build_dependencies(config_path=_config(tmp_path, compatible_block))

    # Act
    provider = deps.registry.entry(LLMProvider, "openai-compatible").factory(None)

    # Assert
    assert isinstance(provider, LLMProvider)
    assert not isinstance(provider, TokenCounting)


async def test_counting_runs_off_the_event_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    """`32.10`'s paid run: `tiktoken` reads (and on first use downloads) its encoding file, and
    the seam's blocking-call guard stopped `repack` for `open()` on the event loop thread — no
    unit test could see it, because none ran under the guard."""
    # Arrange
    offloaded: list[str] = []
    real = asyncio.to_thread

    async def _to_thread(
        function: Callable[..., object], /, *args: object, **kwargs: object
    ) -> object:
        offloaded.append(getattr(function, "__name__", repr(function)))
        return await real(function, *args, **kwargs)

    monkeypatch.setattr(asyncio, "to_thread", _to_thread)

    # Act
    count = await _provider().count_tokens(_POLISH, model=DEFAULT_MODEL)

    # Assert
    assert count is not None
    assert offloaded, "the encoding lookup and the count must run through asyncio.to_thread"
