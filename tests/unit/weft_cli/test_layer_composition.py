"""Ledger task **43.7** — a layer is composed with its base, never run on its own.

A layer document lists only the stages that enrich stored nodes: `enrich-with-questions` is
`[questions]`. Owner's decision, 2026-09-22: no contract lets a plugin drop the nodes it is handed
(`Expander` promises every node back, unchanged), and a layer carrying its own `embed` stage would
embed its questions with an embedder the target was not built with. So `compose_layer` takes the
layer's stages and the base document's own `Embedder` and `NodeStore` stages, and `layer_created`
keeps only the nodes the layer made, which are all that reach that tail.
"""

from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Protocol, runtime_checkable

import pytest

from weft_chunk import Chunker
from weft_cli.layers import (
    LayerDuplicatesBaseStageError,
    NotALayerError,
    compose_layer,
    installed_layers,
    layer_created,
)
from weft_embed import Embedder
from weft_engine import registry_bootstrap
from weft_engine.registry_bootstrap import Dependencies
from weft_enhance import Enhancer
from weft_index import Expander, Revisable
from weft_kernel.context import Context
from weft_kernel.payload import MediaType, Node, Outcome, Produced, SourceId
from weft_kernel.runner import Stage
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


@runtime_checkable
class _StrangerEnricher(Stage[Sequence[Node], Sequence[Node]], Protocol):
    """A third party's own nodes-in, nodes-out contract, declared a layer stage by its publisher."""

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]: ...


_StrangerEnricher.layer_stage = True  # pyright: ignore[reportAttributeAccessIssue]


@runtime_checkable
class _StrangerReshaper(Stage[Sequence[Node], Sequence[Node]], Protocol):
    """The same shape with no such declaration — as a `Chunker` has."""

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]: ...


class _Echo:
    def __init__(self, config: object = None) -> None:
        del config

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        del ctx
        return Produced(value=payload)


def _stranger_layer(deps: Dependencies, tmp_path: Path, contract: type[object], use: str) -> str:
    deps.registry.add(contract, use, _Echo, distribution="weft-example-stranger")
    (tmp_path / "pipelines").mkdir(exist_ok=True)
    (tmp_path / "pipelines" / f"{use}-layer.yaml").write_text(
        f"name: {use}-layer\nstages:\n  - {{id: enrich, use: {use}}}\n", encoding="utf-8"
    )
    return f"{use}-layer"


def test_a_stranger_s_own_contract_declared_a_layer_stage_composes_as_a_layer(
    deps: Dependencies, tmp_path: Path
) -> None:
    # Arrange — R43.16: no edit to `weft_cli` lets a third party's contract carry a layer stage.
    layer = _stranger_layer(deps, tmp_path, _StrangerEnricher, "stranger-enrich")

    # Act
    composed = compose_layer(layer, base="index-text", registry=deps.registry, reports=deps.reports)

    # Assert
    assert [spec.contract for spec in composed.layer_specs] == [_StrangerEnricher]
    assert layer in installed_layers(registry=deps.registry, reports=deps.reports)


def test_a_contract_that_does_not_declare_itself_a_layer_stage_is_refused_saying_so(
    deps: Dependencies, tmp_path: Path
) -> None:
    # Arrange
    layer = _stranger_layer(deps, tmp_path, _StrangerReshaper, "stranger-reshape")

    # Act
    with pytest.raises(NotALayerError) as refused:
        compose_layer(layer, base="index-text", registry=deps.registry, reports=deps.reports)

    # Assert
    message = str(refused.value)
    assert "_StrangerReshaper" in message
    assert "layer_stage" in message
    assert layer not in installed_layers(registry=deps.registry, reports=deps.reports)


def test_the_three_first_party_layer_contracts_declare_it_and_no_other_node_contract_does() -> None:
    # Act / Assert
    for declared in (Expander, Enhancer, Revisable):
        assert getattr(declared, "layer_stage", False) is True
    for undeclared in (Chunker, Embedder, NodeStore):
        assert getattr(undeclared, "layer_stage", False) is False
