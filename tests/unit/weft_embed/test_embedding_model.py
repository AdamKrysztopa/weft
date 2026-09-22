"""An embedder states the model and width it embeds with — ledger task **34.4**.

A target records the identity of its first write and refuses a query whose embedder states a
different one. That needs the embedder to say what it is, and `Embedder` carries nothing but
`run`: adding a member there would be a major for every implementer (G9), so the statement is
its own one-member Protocol beside it, `NodeSupersedable`'s shape.
"""

from __future__ import annotations

from pydantic import SecretStr

from weft_embed import HashEmbedder, HashEmbedderConfig
from weft_embed.contract import (
    EMBEDDER_CONTRACT_VERSION,
    Embedder,
    EmbeddingModel,
    IdentifiedEmbedder,
)
from weft_openai import OpenAIEmbedder, OpenAIEmbedderConfig, Settings


def test_the_contract_moved_a_minor_for_the_new_protocol() -> None:
    # Assert
    assert EMBEDDER_CONTRACT_VERSION == "1.1.0"
    assert IdentifiedEmbedder.version == EMBEDDER_CONTRACT_VERSION
    assert Embedder.version == EMBEDDER_CONTRACT_VERSION


async def test_the_hash_embedder_states_its_width() -> None:
    # Arrange
    default = HashEmbedder()
    wide = HashEmbedder(HashEmbedderConfig(dimension=128))

    # Act / Assert
    assert isinstance(default, IdentifiedEmbedder)
    assert await default.embedding_model() == EmbeddingModel(model="hash", width=64)
    assert await wide.embedding_model() == EmbeddingModel(model="hash", width=128)


async def test_the_openai_embedder_states_the_model_it_will_call() -> None:
    """The account-level `embedding_model` wins over the stage default, exactly as the call
    does (`R22.1`) — the identity is what the request sends, not what the config printed."""
    # Arrange
    settings = Settings(api_key=SecretStr("sk-test"), embedding_model="text-embedding-3-large")
    from_settings = OpenAIEmbedder(settings)
    from_stage = OpenAIEmbedder(
        settings, OpenAIEmbedderConfig(model="text-embedding-3-small", dimensions=256)
    )

    # Act / Assert
    assert isinstance(from_settings, IdentifiedEmbedder)
    assert await from_settings.embedding_model() == EmbeddingModel(
        model="text-embedding-3-large", width=None
    )
    assert await from_stage.embedding_model() == EmbeddingModel(
        model="text-embedding-3-small", width=256
    )
