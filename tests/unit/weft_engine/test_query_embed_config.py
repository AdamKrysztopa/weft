"""`[services.embed_config]` configures the embedder the query side builds — carried repair
**R34.4**, owner's decision 2026-09-22.

Found preparing Phase 34's exit. Every query path builds `[services] embed` with no configuration
(`build_services`, `run_ask`), so a target built by a configured embedder (hash at width 128,
OpenAI with `dimensions: 256`) could never be queried after a promote: the identity check
(`34.4`) refused every question, correctly. The operator states the query embedder's
configuration in `weft.toml`. It is validated against the selected embedder's own config model and
refused by name when a key is unknown, and the identity check proves it matches.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from weft_embed.contract import Embedder, EmbeddingModel, IdentifiedEmbedder
from weft_engine.registry_bootstrap import build_dependencies
from weft_engine.service_roles import RoleTable
from weft_engine.services import (
    EmbedConfigRefusedError,
    embed_config_for,
    service_selection_from_config,
)
from weft_kernel.errors import WeftError


def test_the_table_is_read_into_the_selection() -> None:
    # Act
    selection = service_selection_from_config(
        {"services": {"embed_config": {"dimension": 128}}},
        table=RoleTable(roles={}),
    )

    # Assert
    assert dict(selection.embed_config) == {"dimension": 128}


async def test_the_query_embedder_is_built_with_it(tmp_path: Path) -> None:
    # Arrange
    (tmp_path / "weft.toml").write_text("[services.embed_config]\ndimension = 128\n")
    deps = build_dependencies(config_path=tmp_path / "weft.toml")

    # Act
    config = embed_config_for(deps.registry, deps.services)
    embedder = deps.registry.entry(Embedder, deps.services.embed).factory(config)

    # Assert
    assert isinstance(embedder, IdentifiedEmbedder)
    assert await embedder.embedding_model() == EmbeddingModel(model="hash", width=128)


def test_nothing_configured_leaves_the_embedder_at_its_defaults(tmp_path: Path) -> None:
    # Arrange
    (tmp_path / "weft.toml").write_text("")
    deps = build_dependencies(config_path=tmp_path / "weft.toml")

    # Act / Assert
    assert embed_config_for(deps.registry, deps.services) is None


def test_a_key_the_embedder_does_not_have_is_refused_naming_the_ones_it_does(
    tmp_path: Path,
) -> None:
    # Arrange
    (tmp_path / "weft.toml").write_text("[services.embed_config]\ndimensions = 128\n")
    deps = build_dependencies(config_path=tmp_path / "weft.toml")

    # Act / Assert
    with pytest.raises(EmbedConfigRefusedError) as caught:
        embed_config_for(deps.registry, deps.services)
    message = str(caught.value)
    assert isinstance(caught.value, WeftError)
    assert "'dimensions'" in message
    assert "takes: dimension" in message
    assert "'hash'" in message
