"""Unit tests for counting tokens for a role's model — ledger task **32.6**, gate **G25**.

`repack`'s budget (`32.7`) counts tokens of the model that will read the context, so the count
is resolved from the role the way `native_structured_available` resolves its answer: through the
role's provider, never through a second statement of the model. A provider offers counting by
satisfying `TokenCounting` — derived by `isinstance`, never declared — and answers `None` for a
model it cannot count. Either absence is refused naming role, provider and model: never a
character estimate, never a default encoding, never pass-through.
"""

from collections.abc import AsyncIterator

import pytest

from weft_kernel.context import Context
from weft_kernel.payload import Outcome, Produced
from weft_kernel.registry import Registry
from weft_llm.client import LLMClient, llm_service
from weft_llm.contract import LLMProvider, TokenCounter, TokenCounting
from weft_llm.errors import TokenCountUnavailableError
from weft_llm.payload import Completion, Conversation
from weft_llm.roles import LLMRoles, RoleMapping
from weft_llm.scripted import ScriptedProvider

_KNOWN_MODEL = "counted-model"


class _CountingProvider:
    """Counts one token per word for `_KNOWN_MODEL`, and knows no other model."""

    def __init__(self, config: object = None) -> None:
        del config

    async def complete(
        self, conv: Conversation, *, model: str, ctx: Context
    ) -> Outcome[Completion]:
        del conv, ctx
        return Produced(value=Completion(text="", model=model, finish_reason="stop"))

    async def stream(self, conv: Conversation, *, model: str, ctx: Context) -> AsyncIterator[str]:
        del conv, model, ctx
        yield ""

    async def close(self) -> None:
        return None

    async def count_tokens(self, text: str, *, model: str) -> int | None:
        return len(text.split()) if model == _KNOWN_MODEL else None


def _client(provider: str, model: str | None = None) -> LLMClient:
    registry = Registry()
    registry.add(LLMProvider, "counting", _CountingProvider, distribution="test")
    registry.add(LLMProvider, "scripted", ScriptedProvider, distribution="weft-llm")
    return llm_service(
        registry=registry,
        roles=LLMRoles(roles={"generate": RoleMapping(provider=provider, model=model)}),
    )


def test_a_provider_with_a_count_method_is_found_to_count_and_one_without_is_not() -> None:
    # Act / Assert
    assert isinstance(_CountingProvider(), TokenCounting)
    assert not isinstance(ScriptedProvider(), TokenCounting)


def test_the_client_offers_counting_by_role_without_changing_the_llm_contract() -> None:
    # Act / Assert
    assert isinstance(_client("counting", _KNOWN_MODEL), TokenCounter)


async def test_a_role_whose_provider_counts_its_model_gets_that_count() -> None:
    # Arrange
    client = _client("counting", _KNOWN_MODEL)

    # Act
    count = await client.count_tokens("generate", "four words right here")

    # Assert
    assert count == 4


async def test_a_role_whose_provider_cannot_count_is_refused_naming_role_provider_and_model() -> (
    None
):
    # Arrange
    client = _client("scripted", "any-model")

    # Act / Assert
    with pytest.raises(TokenCountUnavailableError) as refused:
        await client.count_tokens("generate", "some evidence")
    message = str(refused.value)
    assert "generate" in message
    assert "scripted" in message
    assert "any-model" in message
    assert (refused.value.role, refused.value.provider) == ("generate", "scripted")


async def test_a_model_the_providers_counter_does_not_know_is_refused_not_estimated() -> None:
    # Arrange
    client = _client("counting", "a-local-model")

    # Act / Assert
    with pytest.raises(TokenCountUnavailableError) as refused:
        await client.count_tokens("generate", "some evidence")
    assert "a-local-model" in str(refused.value)
    assert refused.value.model == "a-local-model"
