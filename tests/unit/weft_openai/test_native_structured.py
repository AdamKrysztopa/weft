"""An account asks the endpoint to answer in a schema only when told to — repair **R41.5**.

Tier 1 of the structured-output cascade is available iff `isinstance(provider, NativeStructured)`,
and before this repair no provider in the tree satisfied it, so every typed answer came from tier 2.
The owner settled both open questions on 2026-09-21: the capability is an opt-in per account,
`structured_output`, default false, on `[packs.openai]` and `[packs.openai-compatible]` alike — the
shape R33.1 gave `stream_usage` — because a server that rejects `response_format` raises
`LLMBadRequestError` at tier 1, which `weft_prompts/cascade.py`'s `skip_adapted` turns into a drop
to tier 3; an account that has not opted in is never asked, and asks exactly as it did before.

The wire shape is the SDK's own `ResponseFormatJSONSchema`
(`openai/types/shared_params/response_format_json_schema.py`, read 2026-09-21): `type` is
`"json_schema"`, `json_schema.name` is required and *"must be a-z, A-Z, 0-9, or contain underscores
and dashes, with a maximum length of 64"*, and `strict` is optional — so it is omitted, the
API's own default, by the rule `OpenAILLMConfig` states for every knob.

Driven through `build_dependencies`, as `test_stream_usage.py` is: the setting has to travel from a
`[packs.*]` block into the provider a role will call. The client double is `test_llm.py`'s, widened
by the one argument this repair sends (`L11.17`).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

import httpx2
import pytest
from openai import BadRequestError

from weft_engine import registry_bootstrap
from weft_kernel.context import Context
from weft_kernel.payload import Produced
from weft_llm.contract import LLMProvider, NativeStructured, TokenCounting, UsageReporting
from weft_llm.errors import LLMBadRequestError
from weft_llm.payload import Conversation, Message, MessageRole

_SCHEMA: Mapping[str, object] = {
    "title": "PassageRelevance",
    "type": "object",
    "properties": {"index": {"type": "integer"}, "relevant": {"type": "boolean"}},
    "required": ["index", "relevant"],
}


def _ctx() -> Context:
    return Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")


def _conversation(text: str) -> Conversation:
    return Conversation(messages=(Message(role=MessageRole.USER, content=text),))


@dataclass
class _Message:
    content: str | None


@dataclass
class _Choice:
    message: _Message
    finish_reason: str | None = "stop"


@dataclass
class _Response:
    choices: Sequence[_Choice]
    usage: None = None


@dataclass
class _Call:
    stream: bool
    response_format: Mapping[str, object] | None


@dataclass
class _Completions:
    reply: str = '{"index": 0, "relevant": true}'
    error: Exception | None = None
    calls: list[_Call] = field(default_factory=lambda: [])

    async def create(
        self,
        *,
        model: str,
        messages: Sequence[Mapping[str, str]],
        stream: bool = False,
        response_format: Mapping[str, object] | None = None,
        **_: object,
    ) -> _Response:
        del model, messages
        self.calls.append(_Call(stream=stream, response_format=response_format))
        if self.error is not None:
            raise self.error
        return _Response(choices=[_Choice(message=_Message(content=self.reply))])


@dataclass
class _Chat:
    completions: _Completions = field(default_factory=_Completions)


@dataclass
class _Client:
    chat: _Chat = field(default_factory=_Chat)

    async def close(self) -> None:
        return None


def _config(tmp_path: Path, *, vendor_block: str = "", compatible_block: str = "") -> Path:
    config = tmp_path / "weft.toml"
    config.write_text(
        "[packs.openai]\n"
        'api_key = "sk-hosted-account"\n' + vendor_block + "\n"
        "[packs.openai-compatible]\n"
        'api_key = "sk-local-account"\n'
        'base_url = "http://127.0.0.1:11434/v1"\n' + compatible_block,
        encoding="utf-8",
    )
    return config


def _provider(config: Path, name: str, client: _Client | None = None) -> object:
    deps = registry_bootstrap.build_dependencies(config_path=config)
    factory = deps.registry.entry(LLMProvider, name).factory
    return factory(None) if client is None else factory(None, client=client)


def _bad_request() -> BadRequestError:
    request = httpx2.Request("POST", "http://127.0.0.1:11434/v1/chat/completions")
    body = {"message": "unknown field response_format", "type": "invalid_request_error"}
    response = httpx2.Response(400, request=request, json={"error": body})
    return BadRequestError("unknown field response_format", response=response, body=body)


@pytest.mark.parametrize("name", ["openai", "openai-compatible"])
def test_an_account_that_has_not_opted_in_is_not_asked_in_a_schema(
    tmp_path: Path, name: str
) -> None:
    # Act
    provider = _provider(_config(tmp_path), name)

    # Assert
    assert isinstance(provider, LLMProvider)
    assert not isinstance(provider, NativeStructured)


def test_the_vendor_account_answers_in_a_schema_when_its_settings_opt_in(tmp_path: Path) -> None:
    # Act
    provider = _provider(_config(tmp_path, vendor_block="structured_output = true\n"), "openai")

    # Assert — opting in adds the one capability and withdraws none the account already had.
    assert isinstance(provider, NativeStructured)
    assert isinstance(provider, UsageReporting)
    assert isinstance(provider, TokenCounting)


def test_one_accounts_opt_in_does_not_reach_the_other(tmp_path: Path) -> None:
    # Arrange
    config = _config(tmp_path, compatible_block="structured_output = true\n")

    # Act
    compatible = _provider(config, "openai-compatible")
    vendor = _provider(config, "openai")

    # Assert
    assert isinstance(compatible, NativeStructured)
    assert not isinstance(vendor, NativeStructured)


@pytest.mark.parametrize("stream_usage", [False, True])
def test_a_compatible_accounts_opt_in_withholds_what_it_withheld_before(
    tmp_path: Path, stream_usage: bool
) -> None:
    # Arrange
    block = f"structured_output = true\nstream_usage = {str(stream_usage).lower()}\n"

    # Act
    provider = _provider(_config(tmp_path, compatible_block=block), "openai-compatible")

    # Assert — R33.1's and 32.6's withholdings survive the new capability.
    assert isinstance(provider, NativeStructured)
    assert isinstance(provider, UsageReporting) is stream_usage
    assert not isinstance(provider, TokenCounting)


@pytest.mark.parametrize(
    ("name", "block_key"),
    [("openai", "vendor_block"), ("openai-compatible", "compatible_block")],
)
async def test_an_opted_in_account_sends_the_schema_as_a_json_schema_response_format(
    tmp_path: Path, name: str, block_key: str
) -> None:
    # Arrange
    client = _Client()
    config = _config(tmp_path, **{block_key: "structured_output = true\n"})
    provider = cast("NativeStructured", _provider(config, name, client))

    # Act
    outcome = await provider.complete_structured(
        _conversation("is passage 0 relevant?"), _SCHEMA, model="qwen2.5:7b", ctx=_ctx()
    )

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value.text == '{"index": 0, "relevant": true}'
    [sent] = client.chat.completions.calls
    assert sent.stream is False
    assert sent.response_format is not None
    assert sent.response_format["type"] == "json_schema"
    json_schema = cast("Mapping[str, object]", sent.response_format["json_schema"])
    assert json_schema["schema"] == _SCHEMA
    assert json_schema["name"] == "PassageRelevance"
    assert "strict" not in json_schema


@pytest.mark.parametrize(
    ("schema", "expected_name"),
    [
        (
            {"type": "object", "title": "Structured[PassageRelevance]"},
            "Structured_PassageRelevance_",
        ),
        ({"type": "object", "title": "x" * 80}, "x" * 64),
        ({"type": "object"}, "answer"),
    ],
)
async def test_the_response_format_name_is_one_the_endpoint_accepts(
    tmp_path: Path, schema: Mapping[str, object], expected_name: str
) -> None:
    # Arrange — the name is the schema's title with every character outside `[A-Za-z0-9_-]`
    # replaced by `_` and cut to 64, or `answer` where the schema has no title.
    client = _Client()
    config = _config(tmp_path, compatible_block="structured_output = true\n")
    provider = cast("NativeStructured", _provider(config, "openai-compatible", client))

    # Act
    await provider.complete_structured(_conversation("q"), schema, model="m", ctx=_ctx())

    # Assert
    [sent] = client.chat.completions.calls
    assert sent.response_format is not None
    json_schema = cast("Mapping[str, object]", sent.response_format["json_schema"])
    assert json_schema["name"] == expected_name


async def test_a_server_that_rejects_the_response_format_is_a_bad_request(tmp_path: Path) -> None:
    """The error the cascade's `skip_adapted` keys on — so an operator who opts in against a
    server that refuses the field sees tier 3 in `Structured.tier`, not a crash."""
    # Arrange
    client = _Client(chat=_Chat(completions=_Completions(error=_bad_request())))
    config = _config(tmp_path, compatible_block="structured_output = true\n")
    provider = cast("NativeStructured", _provider(config, "openai-compatible", client))

    # Act / Assert
    with pytest.raises(LLMBadRequestError, match="response_format"):
        await provider.complete_structured(_conversation("q"), _SCHEMA, model="m", ctx=_ctx())


async def test_an_opted_in_accounts_plain_completion_sends_no_response_format(
    tmp_path: Path,
) -> None:
    # Arrange
    client = _Client()
    config = _config(tmp_path, compatible_block="structured_output = true\n")
    provider = cast("LLMProvider", _provider(config, "openai-compatible", client))

    # Act
    await provider.complete(_conversation("q"), model="m", ctx=_ctx())

    # Assert
    [sent] = client.chat.completions.calls
    assert sent.response_format is None
