"""Carried repair **R44.13e** — a rung is offered only when the service it reads holds something.

A graph rung reads the service selected for the `graph` role, not nodes in the vector store, so
neither `route.requires` (a layer) nor `route.requires-nodes` (a node filter) can state what it
needs. A rung writes `route.requires-role: <role key>`, and the caller adds that role's token to
the ready set only when the selected service reports it holds data
(`weft_cli.route_ask.satisfied_role_requirements`).
"""

from pathlib import Path
from typing import Any

import pytest

from weft_cli.pipeline_catalogue import load_contributed
from weft_engine import registry_bootstrap
from weft_kernel.pipeline import Pipeline
from weft_retrieve.engine import (
    MalformedRouteRequirementError,
    role_requirement_token,
    role_requirements,
    route_catalogue,
)

_GRAPH_RUNGS = {
    "graph-then-generate",
    "graph-2hop-then-generate",
    "graph-and-vector-rrf",
    "graph-then-rerank",
}


def _document(name: str, *, requires_role: Any = None) -> Pipeline:
    variables: dict[str, Any] = {"route.summary": f"{name} answers", "route.cost": "one search"}
    if requires_role is not None:
        variables["route.requires-role"] = requires_role
    return Pipeline.model_validate(
        {"name": name, "vars": variables, "stages": [{"id": "retrieve", "use": "vector-top-k"}]}
    )


_CATALOGUE = {
    "plain": _document("plain"),
    "needs-graph": _document("needs-graph", requires_role="graph"),
}


def test_a_role_requirement_is_offered_only_once_its_token_is_ready() -> None:
    # Act
    withheld = route_catalogue(_CATALOGUE, ready_layers=frozenset()).names()
    offered = route_catalogue(
        _CATALOGUE, ready_layers=frozenset({role_requirement_token("graph")})
    ).names()

    # Assert
    assert withheld == frozenset({"plain"})
    assert offered == frozenset({"plain", "needs-graph"})


def test_a_ready_set_spelling_the_role_but_not_its_token_does_not_offer_the_rung() -> None:
    # Act — a layer named like the role is not the role's token
    offered = route_catalogue(_CATALOGUE, ready_layers=frozenset({"graph"})).names()

    # Assert
    assert offered == frozenset({"plain"})


def test_told_nothing_the_catalogue_still_offers_everything() -> None:
    # Act / Assert
    assert route_catalogue(_CATALOGUE).names() == frozenset(_CATALOGUE)


def test_role_requirements_are_every_distinct_role_key_the_catalogue_names() -> None:
    # Arrange
    catalogue = {**_CATALOGUE, "also-graph": _document("also-graph", requires_role="graph")}

    # Act / Assert
    assert role_requirements(catalogue) == frozenset({"graph"})
    assert role_requirements({"plain": _CATALOGUE["plain"]}) == frozenset()


@pytest.mark.parametrize("value", ["", "  ", True, 3])
def test_a_role_requirement_that_is_not_a_role_key_is_refused_naming_the_document(
    value: object,
) -> None:
    # Arrange
    catalogue = {"bad": _document("bad", requires_role=value)}

    # Act
    with pytest.raises(MalformedRouteRequirementError) as refused:
        route_catalogue(catalogue, ready_layers=frozenset())

    # Assert
    assert refused.value.pipeline == "bad"
    assert "route.requires-role" in str(refused.value)


def test_every_shipped_graph_rung_requires_the_graph_role(tmp_path: Path) -> None:
    # Arrange
    config = tmp_path / "weft.toml"
    config.write_text('[packs.store]\ndsn = "postgresql://nobody@localhost:1/none"\n')
    catalogue = load_contributed(registry_bootstrap.build_dependencies(config_path=config).reports)

    # Act
    requiring = {
        name
        for name, document in catalogue.items()
        if document.vars.get("route.requires-role") == "graph"
    }

    # Assert
    assert requiring == _GRAPH_RUNGS
