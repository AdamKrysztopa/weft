"""Ledger task **43.9** — the router never offers a rung whose layer is not built everywhere.

A query document that needs a layer says so in `vars` as `route.requires: <layer document>`.
`route_catalogue` is told which layers are built on every source and leaves out every candidate
that requires one that is not. Told nothing, it leaves nothing out: every caller before this task
keeps the catalogue it had.
"""

from collections.abc import Callable, Mapping
from pathlib import Path

import pytest

from weft_cli.pipeline_catalogue import load_contributed
from weft_engine import registry_bootstrap
from weft_kernel.pipeline import Pipeline
from weft_retrieve.engine import UnknownRouteVarError, route_catalogue, route_requirements


def _document(name: str, *, requires: str | None = None) -> Pipeline:
    variables = {"route.summary": f"{name} answers", "route.cost": "one search"}
    if requires is not None:
        variables["route.requires"] = requires
    return Pipeline.model_validate(
        {"name": name, "vars": variables, "stages": [{"id": "retrieve", "use": "vector-top-k"}]}
    )


_CATALOGUE = {
    "plain": _document("plain"),
    "other": _document("other"),
    "needs-questions": _document("needs-questions", requires="enrich-with-questions"),
}


def test_a_rung_whose_layer_is_not_built_everywhere_is_not_offered() -> None:
    # Act
    offered = route_catalogue(_CATALOGUE, ready_layers=frozenset()).names()

    # Assert
    assert offered == frozenset({"plain", "other"})


def test_a_rung_whose_layer_is_built_everywhere_is_offered() -> None:
    # Act
    offered = route_catalogue(_CATALOGUE, ready_layers=frozenset({"enrich-with-questions"})).names()

    # Assert
    assert offered == frozenset({"plain", "other", "needs-questions"})


def test_told_nothing_about_layers_the_catalogue_offers_everything_as_before() -> None:
    # Act / Assert
    assert route_catalogue(_CATALOGUE).names() == frozenset(_CATALOGUE)


def test_each_rung_s_required_layer_is_read_off_its_document() -> None:
    # Act / Assert
    assert route_requirements(_CATALOGUE) == {"needs-questions": "enrich-with-questions"}


def test_the_shipped_questions_rung_requires_the_shipped_questions_layer(tmp_path: Path) -> None:
    # Arrange
    config = tmp_path / "weft.toml"
    config.write_text('[packs.store]\ndsn = "postgresql://nobody@localhost:1/none"\n')
    deps = registry_bootstrap.build_dependencies(config_path=config)

    # Act
    requirements = route_requirements(load_contributed(deps.reports))

    # Assert
    assert requirements.get("questions-then-generate") == "enrich-with-questions"


def _with_var(name: str, key: str) -> Pipeline:
    return Pipeline.model_validate(
        {
            "name": name,
            "vars": {"route.summary": f"{name} answers", key: "enrich-with-questions"},
            "stages": [{"id": "retrieve", "use": "vector-top-k"}],
        }
    )


@pytest.mark.parametrize("read", [route_requirements, route_catalogue])
def test_an_unknown_route_key_is_refused_naming_the_document_and_the_keys(
    read: Callable[[Mapping[str, Pipeline]], object],
) -> None:
    # Arrange — R43.13: `route.require` was ignored, so the rung was offered over a pending layer.
    catalogue = {**_CATALOGUE, "misspelt": _with_var("misspelt", "route.require")}

    # Act
    with pytest.raises(UnknownRouteVarError) as refused:
        read(catalogue)

    # Assert
    message = str(refused.value)
    assert "'misspelt'" in message
    assert "'route.require'" in message
    assert refused.value.valid_options == ("route.cost", "route.requires", "route.summary")


def test_a_document_whose_only_route_key_is_misspelt_is_refused_too() -> None:
    # Arrange — `route.sumary` drops the document out of the candidates, so it is never offered.
    misspelt = Pipeline.model_validate(
        {
            "name": "misspelt",
            "vars": {"route.sumary": "answers"},
            "stages": [{"id": "retrieve", "use": "vector-top-k"}],
        }
    )

    # Act / Assert
    with pytest.raises(UnknownRouteVarError, match="'route.sumary'"):
        route_catalogue({**_CATALOGUE, "misspelt": misspelt})
