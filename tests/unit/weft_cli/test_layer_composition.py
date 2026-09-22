"""Ledger task **43.7** — a layer is composed with its base, never run on its own.

A layer document lists only the stages that enrich stored nodes: `enrich-with-questions` is
`[questions]`. Owner's decision, 2026-09-22: no contract lets a plugin drop the nodes it is handed
(`Expander` promises every node back, unchanged), and a layer carrying its own `embed` stage would
embed its questions with an embedder the target was not built with. So `compose_layer` takes the
layer's stages and the base document's own `Embedder` and `NodeStore` stages, and `layer_created`
keeps only the nodes the layer made, which are all that reach that tail.
"""

from collections.abc import Iterator
from pathlib import Path

import pytest

from weft_cli.layers import (
    LayerDuplicatesBaseStageError,
    NotALayerError,
    compose_layer,
    layer_created,
)
from weft_embed import Embedder
from weft_engine import registry_bootstrap
from weft_engine.registry_bootstrap import Dependencies
from weft_index import Expander
from weft_kernel.payload import MediaType, Node, SourceId
from weft_store import NodeStore


@pytest.fixture
def deps(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Dependencies]:
    config = tmp_path / "weft.toml"
    # Resolution builds nothing, so the store needs a DSN and never a reachable one.
    config.write_text('[packs.store]\ndsn = "postgresql://nobody@localhost:1/none"\n')
    monkeypatch.chdir(tmp_path)
    yield registry_bootstrap.build_dependencies(config_path=config)


def test_enrich_with_questions_is_one_expander_and_borrows_the_base_s_embed_and_store(
    deps: Dependencies,
) -> None:
    # Act
    composed = compose_layer(
        "enrich-with-questions", base="index-text", registry=deps.registry, reports=deps.reports
    )

    # Assert
    assert [(spec.id, spec.contract) for spec in composed.layer_specs] == [("questions", Expander)]
    assert [spec.name for spec in composed.layer_specs] == ["hypothetical-questions"]
    assert [(spec.id, spec.contract, spec.name) for spec in composed.tail_specs] == [
        ("embed", Embedder, "hash"),
        ("store", NodeStore, "pgvector"),
    ]
    assert (composed.layer, composed.base) == ("enrich-with-questions", "index-text")


def test_the_tail_is_whichever_embedder_the_base_names(deps: Dependencies) -> None:
    # Act
    composed = compose_layer(
        "enrich-with-questions", base="index-openai", registry=deps.registry, reports=deps.reports
    )

    # Assert
    assert [spec.name for spec in composed.tail_specs if spec.contract is Embedder] == [
        "openai-embeddings"
    ]


def test_a_document_that_reads_files_is_refused_as_a_layer_naming_its_base(
    deps: Dependencies,
) -> None:
    # Act
    with pytest.raises(NotALayerError) as refused:
        compose_layer(
            "index-with-questions",
            base="index-text",
            registry=deps.registry,
            reports=deps.reports,
        )

    # Assert
    message = str(refused.value)
    assert "'index-with-questions'" in message
    assert "'extract'" in message
    assert "'index-text'" in message
    assert "enrich-with-questions" in refused.value.valid_options


def test_a_layer_naming_its_own_embedder_is_refused_naming_the_base_stages(
    deps: Dependencies, tmp_path: Path
) -> None:
    # Arrange — a project document, found through the same catalogue `weft index` reads.
    (tmp_path / "pipelines").mkdir()
    (tmp_path / "pipelines" / "questions-and-embed.yaml").write_text(
        "name: questions-and-embed\n"
        "stages:\n"
        "  - {id: questions, use: hypothetical-questions}\n"
        "  - {id: embed, use: hash}\n",
        encoding="utf-8",
    )

    # Act
    with pytest.raises(LayerDuplicatesBaseStageError) as refused:
        compose_layer(
            "questions-and-embed",
            base="index-text",
            registry=deps.registry,
            reports=deps.reports,
        )

    # Assert
    message = str(refused.value)
    assert "'questions-and-embed'" in message
    assert "'embed'" in message
    assert "'index-text'" in message


def _node(content: str) -> Node:
    return Node.synthetic(
        content=content,
        media_type=MediaType.TEXT,
        reason="layer composition",
        sources=frozenset({SourceId("doc")}),
    )


def test_only_the_nodes_a_layer_made_reach_the_tail() -> None:
    # Arrange
    leaves = (_node("leaf one"), _node("leaf two"))
    derived = leaves[0].derive(content="what is leaf one?", media_type=MediaType.TEXT, ordinal=0)

    # Act
    created = layer_created(leaves, (leaves[1], derived, leaves[0]))

    # Assert
    assert created == (derived,)


def test_a_layer_that_made_nothing_hands_nothing_on() -> None:
    # Arrange
    leaves = (_node("leaf one"),)

    # Act / Assert
    assert layer_created(leaves, leaves) == ()
