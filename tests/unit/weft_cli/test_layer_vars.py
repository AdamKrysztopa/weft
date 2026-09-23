"""Carried repair **R43.13** — a key under `layer.` a layer does not read is refused.

`layer.scope` is the one var a layer document reads. `layer.scop: corpus` was ignored, so a layer
meant to build one tree over the whole corpus ran per source, and nothing said so.
"""

from collections.abc import Iterator
from pathlib import Path

import pytest

from weft_cli.layers import UnknownLayerVarError, compose_layer
from weft_engine import registry_bootstrap
from weft_engine.registry_bootstrap import Dependencies


@pytest.fixture
def deps(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Dependencies]:
    config = tmp_path / "weft.toml"
    config.write_text('[packs.store]\ndsn = "postgresql://nobody@localhost:1/none"\n')
    (tmp_path / "pipelines").mkdir()
    monkeypatch.chdir(tmp_path)
    yield registry_bootstrap.build_dependencies(config_path=config)


def _layer(project: Path, vars_block: str) -> None:
    (project / "pipelines" / "my-questions.yaml").write_text(
        "name: my-questions\n"
        f"vars:\n{vars_block}"
        "stages:\n  - {id: questions, use: hypothetical-questions}\n",
        encoding="utf-8",
    )


def test_an_unknown_layer_key_is_refused_naming_the_keys_a_layer_reads(
    deps: Dependencies, tmp_path: Path
) -> None:
    # Arrange
    _layer(tmp_path, "  layer.scop: corpus\n")

    # Act
    with pytest.raises(UnknownLayerVarError) as refused:
        compose_layer(
            "my-questions", base="index-text", registry=deps.registry, reports=deps.reports
        )

    # Assert
    message = str(refused.value)
    assert "'my-questions'" in message
    assert "'layer.scop'" in message
    assert refused.value.valid_options == ("layer.scope",)


def test_the_one_layer_key_and_keys_outside_the_namespace_still_compose(
    deps: Dependencies, tmp_path: Path
) -> None:
    # Arrange
    _layer(tmp_path, "  layer.scope: corpus\n  moved: 'yes'\n")

    # Act
    composed = compose_layer(
        "my-questions", base="index-text", registry=deps.registry, reports=deps.reports
    )

    # Assert
    assert composed.scope.value == "corpus"
