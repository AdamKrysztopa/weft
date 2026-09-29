"""Carried repair **R44.13b/c** — a rung is offered only when the store holds what it reads.

E0b's `route` sent 64 of 107 questions to `raptor-and-leaves-rrf` over an index with no RAPTOR
tree: that rung's summary arm reads nodes marked `ext.weft-index.technique == raptor`, and nothing
checked that any existed. A tree can come from a base pipeline, the shipped layer or a project's
own derived layer, so a layer name cannot state the requirement; the rung's own filter can. A
rung writes `route.requires-nodes: <field>=<value>` and the caller adds that string to the ready
set only when the store holds a matching node (`weft_cli.route_ask.satisfied_node_requirements`).
"""

from pathlib import Path

import pytest

from weft_cli.pipeline_catalogue import load_contributed
from weft_engine import registry_bootstrap
from weft_kernel.pipeline import Pipeline
from weft_retrieve.engine import (
    MalformedRouteRequirementError,
    node_requirement_filter,
    node_requirements,
    route_catalogue,
)
from weft_store.contract import FilterOp

_RAPTOR = "ext.weft-index.technique=raptor"


def _document(name: str, *, requires_nodes: str | None = None) -> Pipeline:
    variables = {"route.summary": f"{name} answers", "route.cost": "one search"}
    if requires_nodes is not None:
        variables["route.requires-nodes"] = requires_nodes
    return Pipeline.model_validate(
        {"name": name, "vars": variables, "stages": [{"id": "retrieve", "use": "vector-top-k"}]}
    )


_CATALOGUE = {
    "plain": _document("plain"),
    "needs-tree": _document("needs-tree", requires_nodes=_RAPTOR),
}


def test_a_rung_whose_nodes_the_store_does_not_hold_is_not_offered() -> None:
    # Act
    offered = route_catalogue(_CATALOGUE, ready_layers=frozenset()).names()

    # Assert
    assert offered == frozenset({"plain"})


def test_a_rung_whose_nodes_the_store_holds_is_offered() -> None:
    # Act
    offered = route_catalogue(_CATALOGUE, ready_layers=frozenset({_RAPTOR})).names()

    # Assert
    assert offered == frozenset({"plain", "needs-tree"})


def test_told_nothing_the_catalogue_still_offers_everything() -> None:
    # Act / Assert
    assert route_catalogue(_CATALOGUE).names() == frozenset(_CATALOGUE)


def test_every_distinct_node_requirement_is_read_off_the_catalogue() -> None:
    # Arrange
    catalogue = {**_CATALOGUE, "also-tree": _document("also-tree", requires_nodes=_RAPTOR)}

    # Act / Assert
    assert node_requirements(catalogue) == frozenset({_RAPTOR})


def test_a_requirement_reads_as_an_equality_filter_on_its_field() -> None:
    # Act
    built = node_requirement_filter(_RAPTOR)

    # Assert
    assert built.op is FilterOp.EQ
    assert built.field == "ext.weft-index.technique"
    assert built.value == "raptor"


@pytest.mark.parametrize("written", ["raptor", "=raptor", "ext.weft-index.technique="])
def test_a_requirement_that_is_not_field_equals_value_is_refused_naming_the_document(
    written: str,
) -> None:
    # Arrange
    catalogue = {"bad": _document("bad", requires_nodes=written)}

    # Act
    with pytest.raises(MalformedRouteRequirementError) as caught:
        route_catalogue(catalogue, ready_layers=frozenset())

    # Assert
    assert caught.value.pipeline == "bad"
    assert repr(written) in str(caught.value)


def test_the_shipped_raptor_rung_requires_the_nodes_its_summary_arm_reads(tmp_path: Path) -> None:
    # Arrange
    config = tmp_path / "weft.toml"
    config.write_text('[packs.store]\ndsn = "postgresql://nobody@localhost:1/none"\n')
    deps = registry_bootstrap.build_dependencies(config_path=config)

    # Act
    catalogue = load_contributed(deps.reports)

    # Assert
    assert catalogue["raptor-and-leaves-rrf"].vars["route.requires-nodes"] == _RAPTOR
