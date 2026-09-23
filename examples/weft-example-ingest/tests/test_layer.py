"""Ledger task **43.19** — a pack written outside the tree ships a layer, and `weft index --layers`
runs it exactly as it runs `enrich-with-questions`.

A layer is only a pipeline document whose stages take stored nodes and return nodes (`43.7`), so a
stranger needs nothing Weft does not already publish: an `Expander`, one YAML file, and one
`add_pipeline_resource` call. This pack's `example-first-sentence` expander is the stage.
"""

from importlib import resources

import yaml
from weft_example_ingest import Settings, register
from weft_example_ingest.expander import NAME as EXPANDER_NAME

from weft_kernel.discovery import PackRegistrar
from weft_kernel.pipeline import Pipeline
from weft_kernel.registry import Registry

_LAYER = "pipelines/example-first-sentences.yaml"


def test_the_pack_ships_a_layer_document_through_its_own_register() -> None:
    # Arrange
    registrar = PackRegistrar(Registry(), distribution="weft-example-ingest")

    # Act
    register(registrar, Settings())

    # Assert
    shipped = {(r.package, r.resource) for r in registrar.pipeline_resources}
    assert ("weft_example_ingest", _LAYER) in shipped


def test_the_layer_names_only_the_pack_s_own_expander() -> None:
    # Act
    text = resources.files("weft_example_ingest").joinpath(_LAYER).read_text(encoding="utf-8")
    layer = Pipeline.model_validate(yaml.safe_load(text))

    # Assert — no embedder and no store: a layer borrows its base's (`43.7`).
    assert layer.name == "example-first-sentences"
    assert layer.extends is None
    assert [(stage.id, stage.use) for stage in layer.stages] == [("first-sentence", EXPANDER_NAME)]
