"""Ledger task **43.7** — every shipped document that enriches before storing has a layer twin.

`index-with-questions` inserts `hypothetical-questions` before `store`, so the only way to get
questions was to re-parse the corpus through it. A layer (`enrich-with-questions`) runs the same
enrichment over nodes already stored. A shipped ingest document inserting an `Expander` before
its `NodeStore` owes a layer document whose stages are that same enrichment, or a stated reason
it has none. The population is what the installed packs contribute, never a directory listing
(`L22.2`).
"""

from pathlib import Path
from typing import Final

from weft_cli.pipeline_catalogue import load_contributed
from weft_cli.route_ask import resolve_named_pipeline
from weft_engine import registry_bootstrap
from weft_engine.registry_bootstrap import Dependencies
from weft_kernel.resolution import ResolvedPipeline

#: A shipped enriching document with no layer twin, and why. Emptied as `43.15` ships them.
NO_LAYER_TWIN: Final[dict[str, str]] = {
    "index-with-deep-raptor": "two raptor levels in one document; `enrich-with-raptor` is one "
    "level, and a deeper tree over stored leaves has no task yet",
    "index-with-facts": "the graph layer is `43.17`'s, by the owner's decision at `43.15`",
    "index-with-facts-openai": "the graph layer is `43.17`'s, by the owner's decision at `43.15`",
}


def _deps(tmp_path: Path) -> Dependencies:
    config = tmp_path / "weft.toml"
    config.write_text('[packs.store]\ndsn = "postgresql://nobody@localhost:1/none"\n')
    return registry_bootstrap.build_dependencies(config_path=config)


def _resolved(deps: Dependencies) -> dict[str, ResolvedPipeline]:
    return {
        name: resolve_named_pipeline(name, registry=deps.registry, reports=deps.reports)
        for name in sorted(load_contributed(deps.reports))
    }


def _enrichment(pipeline: ResolvedPipeline) -> tuple[str, ...]:
    """The `Expander`s a document runs before its first `NodeStore`."""
    uses: list[str] = []
    for stage in pipeline.stages:
        if stage.contract == "NodeStore":
            break
        if stage.contract == "Expander":
            uses.append(stage.use)
    return tuple(uses)


def _is_layer(pipeline: ResolvedPipeline) -> bool:
    return bool(pipeline.stages) and all(stage.contract == "Expander" for stage in pipeline.stages)


def test_every_enriching_document_has_a_layer_twin_or_a_reason(tmp_path: Path) -> None:
    # Arrange
    resolved = _resolved(_deps(tmp_path))
    layers = {
        tuple(stage.use for stage in pipeline.stages): name
        for name, pipeline in resolved.items()
        if _is_layer(pipeline)
    }

    # Act
    missing = sorted(
        name
        for name, pipeline in resolved.items()
        if not _is_layer(pipeline)
        and (enrichment := _enrichment(pipeline))
        and enrichment not in layers
        and name not in NO_LAYER_TWIN
    )

    # Assert
    assert missing == [], (
        f"{missing} enrich before storing and have no layer twin. Ship an `enrich-with-*` "
        "document whose stages are that enrichment, or give the reason in NO_LAYER_TWIN."
    )


def test_every_waived_document_still_enriches_and_still_lacks_a_twin(tmp_path: Path) -> None:
    # Arrange
    resolved = _resolved(_deps(tmp_path))
    layers = {
        tuple(stage.use for stage in pipeline.stages)
        for pipeline in resolved.values()
        if _is_layer(pipeline)
    }

    # Act
    stale = sorted(
        name
        for name in NO_LAYER_TWIN
        if name not in resolved
        or not _enrichment(resolved[name])
        or _enrichment(resolved[name]) in layers
    )

    # Assert
    assert stale == [], f"{stale} no longer need a waiver; remove them from NO_LAYER_TWIN."


def test_the_population_is_not_empty(tmp_path: Path) -> None:
    # Act
    resolved = _resolved(_deps(tmp_path))

    # Assert
    assert _enrichment(resolved["index-with-questions"]) == ("hypothetical-questions",)
