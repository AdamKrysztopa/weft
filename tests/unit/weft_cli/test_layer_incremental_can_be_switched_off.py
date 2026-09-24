"""Carried repair **R43.32** — a project derives `enrich-with-raptor` without its join stage.

43.23 gave the shipped layer a `join` stage and `layer.incremental: join`. A derived document that
removed the stage was refused, because the inherited var still named it and a var cannot be unset.
`layer.incremental: none` now says the layer has no join, and a var that names the only full-build
stage is refused rather than composing a full build with no stages.
"""

from collections.abc import Iterator
from pathlib import Path

import pytest

from weft_cli.layers import LayerIncrementalStageError, compose_layer
from weft_engine import registry_bootstrap
from weft_engine.registry_bootstrap import Dependencies


@pytest.fixture
def deps(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Dependencies]:
    config = tmp_path / "weft.toml"
    config.write_text('[packs.store]\ndsn = "postgresql://nobody@localhost:1/none"\n')
    (tmp_path / "pipelines").mkdir()
    monkeypatch.chdir(tmp_path)
    yield registry_bootstrap.build_dependencies(config_path=config)


def _derived(project: Path, body: str) -> None:
    (project / "pipelines" / "my-raptor.yaml").write_text(
        f"name: my-raptor\nextends: enrich-with-raptor\n{body}", encoding="utf-8"
    )


def test_a_derived_layer_that_removes_the_join_and_says_none_composes_without_one(
    deps: Dependencies, tmp_path: Path
) -> None:
    # Arrange
    _derived(tmp_path, "vars:\n  layer.incremental: none\nremove: [join]\n")

    # Act
    composed = compose_layer(
        "my-raptor", base="index-text", registry=deps.registry, reports=deps.reports
    )

    # Assert
    assert composed.incremental_specs == ()
    assert [spec.name for spec in composed.layer_specs] == ["raptor"]


def test_none_keeps_every_stage_in_the_full_build(deps: Dependencies, tmp_path: Path) -> None:
    # Arrange
    _derived(tmp_path, "vars:\n  layer.incremental: none\n")

    # Act
    composed = compose_layer(
        "my-raptor", base="index-text", registry=deps.registry, reports=deps.reports
    )

    # Assert
    assert composed.incremental_specs == ()
    assert [spec.name for spec in composed.layer_specs] == ["raptor", "adrap"]


def test_naming_the_only_full_build_stage_as_the_join_is_refused(
    deps: Dependencies, tmp_path: Path
) -> None:
    # Arrange
    _derived(tmp_path, "vars:\n  layer.incremental: raptor\nremove: [join]\n")

    # Act
    with pytest.raises(LayerIncrementalStageError) as refused:
        compose_layer("my-raptor", base="index-text", registry=deps.registry, reports=deps.reports)

    # Assert
    message = str(refused.value)
    assert "'my-raptor'" in message
    assert "none" in message
    assert refused.value.valid_options == ("none",)


def test_removing_the_join_without_saying_none_is_refused_naming_none(
    deps: Dependencies, tmp_path: Path
) -> None:
    # Arrange
    _derived(tmp_path, "remove: [join]\n")

    # Act
    with pytest.raises(LayerIncrementalStageError) as refused:
        compose_layer("my-raptor", base="index-text", registry=deps.registry, reports=deps.reports)

    # Assert
    assert "none" in refused.value.valid_options
    assert "none" in str(refused.value)
