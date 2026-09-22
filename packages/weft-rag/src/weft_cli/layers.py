"""A layer is composed with its base, never run on its own — ledger task **43.7**.

A base document reads files and stores nodes; a layer enriches nodes a base already stored, so
every stage a layer document may name takes nodes and returns nodes — `Expander`, `Revisable`
(`weft_index`) and `Enhancer` (`weft_enhance`), the three contracts `LAYER_STAGE_CONTRACTS`
names. Owner's decision, 2026-09-22: no contract lets a plugin drop the node it is handed, and a
layer names no `Embedder`/`NodeStore` of its own — `compose_layer` takes those two from the base,
in the base's own order, so a layer's new nodes are embedded and stored exactly as the base's
were. No `derived-only` plugin and no new contract were introduced to say this; a document's own
stage list already says it, and `compose_layer` is the one place that reads it that way.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

from pydantic import BaseModel, ConfigDict

from weft_cli.compile import to_specs
from weft_cli.pipeline_catalogue import full_catalogue
from weft_cli.route_ask import resolve_named_pipeline
from weft_embed import Embedder
from weft_enhance import Enhancer
from weft_extract import Extractor
from weft_index import Expander, Revisable
from weft_kernel.discovery import PackReport
from weft_kernel.errors import UnresolvedNameError, WeftError
from weft_kernel.payload import Node
from weft_kernel.registry import Registry
from weft_kernel.resolution import Contribution, ResolvedPipeline
from weft_kernel.runner import PipelineResolutionError, StageSpec
from weft_store import NodeStore

#: The contracts a layer's own stages may carry — every one that takes nodes and returns nodes.
#: `Embedder`/`NodeStore` are not here: a layer never names either, it borrows the base's.
LAYER_STAGE_CONTRACTS: Final[tuple[type[object], ...]] = (Expander, Enhancer, Revisable)

_TAIL_CONTRACTS: Final[tuple[type[object], ...]] = (Embedder, NodeStore)


class NotALayerError(PipelineResolutionError, UnresolvedNameError):
    """A document offered as a layer names a stage that does not take and return nodes.

    A layer runs over nodes a base document already stored, so every stage it names has to
    take nodes and return nodes — `LAYER_STAGE_CONTRACTS`. A document naming an `Extractor`
    reads files, which is a base document's job, not a layer's; any other disallowed
    contract is refused the same way, on the same footing.

    Fitness function 12's family: `valid_options` is every installed layer, from
    `installed_layers` — the document this caller could have named instead.
    """

    def __init__(
        self,
        message: str,
        *,
        valid_options: tuple[str, ...],
        pipeline: str | None = None,
        remedy: str = "",
    ) -> None:
        PipelineResolutionError.__init__(self, message, pipeline=pipeline, remedy=remedy)
        self.valid_options = valid_options


class LayerDuplicatesBaseStageError(PipelineResolutionError):
    """A layer document names its own `Embedder` or `NodeStore`, which its base already owns.

    Not a name-resolution failure — there is no alternative name to offer, only a stage that
    does not belong in a layer document at all, since `compose_layer` already takes the
    base's own `Embedder`/`NodeStore` for the tail. So this does not join
    `UnresolvedNameError`, on `weft_cli.ingest.BatchScopedStageError`'s own footing.
    """


class LayerComposition(BaseModel):
    """A layer resolved and checked against its base — `compose_layer`'s return.

    `resolved` is the layer's own `ResolvedPipeline`, kept for a caller that wants its name,
    `vars` or provenance; `layer_specs` is what the layer itself contributes and `tail_specs`
    is the base's own `Embedder`/`NodeStore` specs, in the base's order — the two halves
    ledger task **43.8**'s index loop runs in sequence, `layer_specs` first.
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    layer: str
    base: str
    resolved: ResolvedPipeline
    layer_specs: tuple[StageSpec, ...]
    tail_specs: tuple[StageSpec, ...]


def installed_layers(
    *,
    registry: Registry,
    reports: Sequence[PackReport],
    contributions: tuple[Contribution, ...] = (),
) -> tuple[str, ...]:
    """Every catalogue document that is a layer — sorted names, from the same catalogue
    `weft index --pipeline` resolves against.

    A document is a layer when it resolves at all, names at least one stage, and every one
    of those stages carries a contract in `LAYER_STAGE_CONTRACTS`. A document that fails to
    resolve is skipped, not refused — `full_catalogue` holds every document a project or a
    pack could name, most of which are not layers and some of which cannot resolve without
    context this function was not given (an unmet `requires`, an unfilled slot), and neither
    is this function's business to diagnose. Only `WeftError` is caught: a name resolving
    into a bug should still crash loudly, not disappear from this list.
    """
    catalogue = full_catalogue(reports=reports)
    layers: list[str] = []
    for name in catalogue:
        try:
            resolved = resolve_named_pipeline(
                name, registry=registry, reports=reports, contributions=contributions
            )
            specs = to_specs(resolved, registry=registry, reports=reports)
        except WeftError:
            continue
        if specs and all(spec.contract in LAYER_STAGE_CONTRACTS for spec in specs):
            layers.append(name)
    return tuple(sorted(layers))


def compose_layer(
    layer: str,
    *,
    base: str,
    registry: Registry,
    reports: Sequence[PackReport],
    contributions: tuple[Contribution, ...] = (),
) -> LayerComposition:
    """`layer` resolved and checked against `base`, and the base's tail it will run through.

    Both are resolved through the identical catalogue `weft index --pipeline` reads —
    `weft_cli.route_ask.resolve_named_pipeline`, which raises its own
    `UnknownPipelineNameError` unchanged for a name neither a project's `pipelines/`
    directory nor an installed pack contributes.

    Raises `NotALayerError` for the layer's first stage that reads files or otherwise does
    not take and return nodes, and `LayerDuplicatesBaseStageError` for the first stage — once
    no such refusal applies — that names an `Embedder` or `NodeStore` the base already owns.
    """
    resolved_layer = resolve_named_pipeline(
        layer, registry=registry, reports=reports, contributions=contributions
    )
    resolved_base = resolve_named_pipeline(
        base, registry=registry, reports=reports, contributions=contributions
    )
    layer_specs = to_specs(resolved_layer, registry=registry, reports=reports)
    base_specs = to_specs(resolved_base, registry=registry, reports=reports)
    tail_specs = tuple(spec for spec in base_specs if spec.contract in _TAIL_CONTRACTS)

    for spec in layer_specs:
        if spec.contract in LAYER_STAGE_CONTRACTS or spec.contract in _TAIL_CONTRACTS:
            continue
        options = installed_layers(registry=registry, reports=reports, contributions=contributions)
        if spec.contract is Extractor:
            message = (
                f"'{layer}' reads files — its stage '{spec.id}' is an Extractor — so it cannot "
                f"run as a layer over the nodes '{base}' stored. Installed layers: "
                f"{', '.join(options) or '(none)'}."
            )
        else:
            message = (
                f"'{layer}' cannot run as a layer: its stage '{spec.id}' is a "
                f"{spec.contract.__name__}, and a layer's stages take stored nodes and return "
                f"nodes. Installed layers: {', '.join(options) or '(none)'}."
            )
        raise NotALayerError(
            message,
            valid_options=options,
            pipeline=layer,
            remedy="name one of the installed layers, or run the document as the base with "
            "--pipeline.",
        )

    for spec in layer_specs:
        if spec.contract not in _TAIL_CONTRACTS:
            continue
        embeds = ", ".join(f"'{s.id}'" for s in tail_specs if s.contract is Embedder)
        stores = ", ".join(f"'{s.id}'" for s in tail_specs if s.contract is NodeStore)
        raise LayerDuplicatesBaseStageError(
            f"'{layer}' names '{spec.id}' ({spec.contract.__name__}:{spec.name}), which a "
            f"layer takes from its base: '{base}' embeds with {embeds} and stores with "
            f"{stores}. Remove it from the layer.",
            pipeline=layer,
            remedy="delete the embedder and store stages from the layer document.",
        )

    return LayerComposition(
        layer=layer,
        base=base,
        resolved=resolved_layer,
        layer_specs=layer_specs,
        tail_specs=tail_specs,
    )


def layer_created(handed: Sequence[Node], returned: Sequence[Node]) -> tuple[Node, ...]:
    """The nodes a layer's stages made — every node in `returned` whose id is not among
    `handed`'s, in `returned`'s own order.

    `Expander` promises every node it is handed back unchanged alongside whatever it derives,
    so `returned` always holds `handed` plus the new ones; this is the selection ledger task
    **43.8**'s index loop applies between a layer's own stages and the base's `Embedder`/
    `NodeStore` tail, so only the layer's new nodes are embedded and stored.
    """
    handed_ids = {node.id for node in handed}
    return tuple(node for node in returned if node.id not in handed_ids)


__all__ = [
    "LAYER_STAGE_CONTRACTS",
    "LayerComposition",
    "LayerDuplicatesBaseStageError",
    "NotALayerError",
    "compose_layer",
    "installed_layers",
    "layer_created",
]
