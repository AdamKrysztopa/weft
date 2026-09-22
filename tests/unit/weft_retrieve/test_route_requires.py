"""Ledger task **43.9** — the router never offers a rung whose layer is not built everywhere.

A query document that needs a layer says so in `vars` as `route.requires: <layer document>`.
`route_catalogue` is told which layers are built on every source and leaves out every candidate
that requires one that is not. Told nothing, it leaves nothing out: every caller before this task
keeps the catalogue it had.
"""

from pathlib import Path

from weft_cli.pipeline_catalogue import load_contributed
from weft_engine import registry_bootstrap
from weft_kernel.pipeline import Pipeline
from weft_retrieve.engine import route_catalogue, route_requirements


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
