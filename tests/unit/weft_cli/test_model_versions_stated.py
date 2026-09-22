"""A run's `model_versions` names the embedding model the run called — carried repair **R34.0**.

Found at ledger `34.0`: `model_versions_of` read the resolved stage's `config.model`, which
resolution fills with `DEFAULT_MODEL` for a stage that set none, while `OpenAIEmbedder` calls
`[packs.openai] embedding_model` in exactly that case (`R22.1`). A run embedded with
`text-embedding-3-large` recorded `-3-small`, and two runs differing only in that setting compared
as though nothing but the pipeline differed — `L10.5`'s shape a second time. The fact to read is
what the embedder states it will call (`34.4`'s `IdentifiedEmbedder`), not what the config printed.
"""

from __future__ import annotations

from pydantic import SecretStr

import weft_openai
from weft_cli.eval_commands import model_versions_of, stated_embedding_models
from weft_kernel.discovery import PackRegistrar
from weft_kernel.registry import Registry
from weft_kernel.resolution import ResolvedPipeline, ResolvedStage
from weft_openai import OpenAIEmbedderConfig, Settings


def _embed_stage() -> ResolvedStage:
    return ResolvedStage(
        id="embed",
        contract="Embedder",
        contract_version="1.1.0",
        use="openai-embeddings",
        config=OpenAIEmbedderConfig(),
        distribution="weft-rag",
        provenance="base",
    )


def _registry(embedding_model: str) -> Registry:
    registry = Registry()
    registrar = PackRegistrar(registry, distribution="weft-rag")
    weft_openai.register(
        registrar, Settings(api_key=SecretStr("sk-test"), embedding_model=embedding_model)
    )
    registrar.commit()
    return registry


async def test_a_settings_only_model_is_the_one_recorded() -> None:
    # Arrange
    resolved = ResolvedPipeline(name="index-openai", stages=(_embed_stage(),))

    # Act
    stated = await stated_embedding_models(resolved, _registry("text-embedding-3-large"))
    versions = model_versions_of(resolved, stated=stated)

    # Assert
    assert versions["embed"] == "openai-embeddings:text-embedding-3-large"


async def test_two_runs_differing_only_in_the_account_model_are_told_apart() -> None:
    # Arrange
    resolved = ResolvedPipeline(name="index-openai", stages=(_embed_stage(),))

    # Act
    large = model_versions_of(
        resolved,
        stated=await stated_embedding_models(resolved, _registry("text-embedding-3-large")),
    )
    small = model_versions_of(
        resolved,
        stated=await stated_embedding_models(resolved, _registry("text-embedding-3-small")),
    )

    # Assert
    assert large != small


def test_without_a_statement_the_config_model_is_still_recorded() -> None:
    # Arrange — a caller that states nothing keeps the pre-R34.0 reading, not an empty one.
    resolved = ResolvedPipeline(name="index-openai", stages=(_embed_stage(),))

    # Act / Assert
    assert model_versions_of(resolved)["embed"] == "openai-embeddings:text-embedding-3-small"
