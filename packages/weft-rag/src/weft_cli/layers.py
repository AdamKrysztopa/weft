"""A layer is composed with its base, never run on its own — ledger task **43.7**.

A base document reads files and stores nodes; a layer enriches nodes a base already stored, so
every stage a layer document may name takes nodes and returns nodes. Which contracts qualify is
not this module's list to keep: a contract's own publisher declares `layer_stage = True` on it —
`Expander`, `Revisable` (`weft_index`) and `Enhancer` (`weft_enhance`) are the three first-party
contracts that do, and a third party's own nodes-in, nodes-out contract may declare it too, with
zero edits here (R43.16). Owner's decision, 2026-09-22: no contract lets a plugin drop the node
it is handed, and a layer names no `Embedder`/`NodeStore` of its own — `compose_layer` takes
those two from the base, in the base's own order, so a layer's new nodes are embedded and stored
exactly as the base's were. No `derived-only` plugin and no new contract were introduced to say
this; a document's own stage list already says it, and `compose_layer` is the one place that
reads it that way.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import StrEnum
from typing import Final, cast

from pydantic import BaseModel, ConfigDict

from weft_cli.compile import to_specs
from weft_cli.pipeline_catalogue import full_catalogue
from weft_cli.progress import BatchProgress
from weft_cli.route_ask import resolve_named_pipeline
from weft_embed import Embedder
from weft_engine.llm_roles import LLMSection
from weft_engine.run_services import class_provides
from weft_extract import Extractor
from weft_extract.text import SourceRef
from weft_index.contract import LayerCheckpoints, LayerRevision
from weft_index.payload import LayerMember, Representation
from weft_kernel.context import Context, ServiceRegistry, UnresolvedServiceError
from weft_kernel.discovery import PackReport
from weft_kernel.errors import UnresolvedNameError, WeftError
from weft_kernel.payload import (
    SCHEMA_VERSION_KEY,
    ExtModel,
    Failed,
    Node,
    NodeId,
    Outcome,
    Produced,
    SourceId,
)
from weft_kernel.registry import Registry, unwrap_factory
from weft_kernel.resolution import Contribution, ResolvedPipeline, pipeline_identity
from weft_kernel.runner import PipelineResolutionError, RunnablePipeline, Runner, StageSpec
from weft_store import NodeStore
from weft_store.contract import (
    Cursor,
    Filter,
    FilterOp,
    GenerationCarrying,
    GenerationHolding,
    GenerationId,
    GenerationRecord,
    GenerationStatus,
    LayerRecord,
    LayerStatus,
    Page,
    SourceFailure,
    SourceRecord,
    SourceStatus,
)
from weft_store.rehydrate import ext_models


def _is_layer_stage(contract: type[object]) -> bool:
    """Whether `contract`'s own publisher declared it a layer stage (R43.16) — read off the
    contract generically, the way `publishes_property_vocabulary` is read in
    `weft_kernel.registry`, never off a closed tuple of first-party names.
    """
    return getattr(contract, "layer_stage", False) is True


_TAIL_CONTRACTS: Final[tuple[type[object], ...]] = (Embedder, NodeStore)

#: `resolved.vars`' own key for a layer's scope — task **43.15**. Dotted, like every other
#: pipeline-level var this tree names, and read straight off `ResolvedPipeline.vars` rather
#: than promoted to a field of its own: a layer document says it the same way it says any
#: other `with:`-adjacent fact about itself.
_SCOPE_VAR: Final[str] = "layer.scope"

#: The ext-model namespace a layer's base must have a consuming store for — task **43.17**.
_STORE_CONSUMES_VAR: Final[str] = "layer.store-consumes"

#: The id of the stage a corpus-scoped layer runs alone, over only the sources its published
#: tree does not cover yet — task **43.23**. A full build never runs it.
_INCREMENTAL_VAR: Final[str] = "layer.incremental"

_KNOWN_LAYER_VARS: Final[tuple[str, ...]] = (_SCOPE_VAR, _STORE_CONSUMES_VAR, _INCREMENTAL_VAR)

#: A layer's build statuses that left no finished tree behind — task **43.20**.
_UNFINISHED: Final[frozenset[LayerStatus]] = frozenset({LayerStatus.FAILED, LayerStatus.INDEXING})

_LAYER_FIELD: Final[str] = f"ext.{LayerMember.__namespace__}.layer"
_CHECKPOINT_FIELD: Final[str] = f"ext.{LayerMember.__namespace__}.checkpoint"


class LayerScope(StrEnum):
    """Where one layer's build runs — ledger task **43.15**. `SOURCE` is the default a layer
    document with no `layer.scope` var gets, and the only scope before this task existed;
    `CORPUS` runs the layer once over every `ACTIVE` source's leaves, as one generation
    (`weft_store.contract.GenerationHolding`) published whole.
    """

    SOURCE = "source"
    CORPUS = "corpus"


class NotALayerError(PipelineResolutionError, UnresolvedNameError):
    """A document offered as a layer names a stage that does not take and return nodes.

    A layer runs over nodes a base document already stored, so every stage it names has to
    take nodes and return nodes — its contract's own publisher has to declare `layer_stage
    = True` on it (R43.16). A document naming an `Extractor` reads files, which is a base
    document's job, not a layer's; any other contract that does not declare itself a layer
    stage is refused the same way, on the same footing.

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


class UnknownLayerError(PipelineResolutionError, UnresolvedNameError):
    """`--layers`/`[index] layers` named a document nothing installed or project-local
    provides — task **43.8**.

    Checked against `installed_layers`' own catalogue, before `compose_layer_over` ever
    resolves the name: a name the catalogue does not hold at all gets this, naming layer
    rather than pipeline; a name the catalogue *does* hold but that fails the layer shape
    checks keeps `NotALayerError`, raised where composition already does that work.
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


class UnknownLayerVarError(PipelineResolutionError, UnresolvedNameError):
    """A layer document (or a document it extends) writes a `layer.` var no layer reads —
    carried repair **R43.13**, found by the exit review: `layer.scop` (a typo for
    `layer.scope`) was silently ignored, so a layer meant to build once over the whole corpus
    ran per source instead, with nothing said.

    Checked in `_layer_scope`, the one function that reads `_SCOPE_VAR` off a
    `ResolvedPipeline` — `LayerComposition`'s own docstring already names it as such.
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


class LayerScopeError(PipelineResolutionError):
    """A layer document's `layer.scope` var names neither `source` nor `corpus` — ledger task
    **43.15**.

    Not a name-resolution failure — there is no catalogue of valid scopes to offer an
    alternative from, only two words a var can take — so this does not join
    `UnresolvedNameError`, on `LayerDuplicatesBaseStageError`'s own footing. Raised at
    composition, before a caller ever learns whether the store it named could run this layer
    at all.
    """


class LayerNeedsMetadataFilterError(WeftError):
    """A layer was named against a store that cannot select stored nodes by metadata —
    task **43.8**.

    A layer's selection is `layer_leaf_filter`, evaluated through `weft_store.contract.
    MetadataFilter.matching`. A store that does not implement it has no way to read the
    leaves a layer enriches, so this is refused before the base runs at all — no extract,
    no write, nothing to undo.
    """


class LayerNeedsGenerationHoldingError(WeftError, UnresolvedNameError):
    """A corpus-scoped layer was named against a store that cannot hold a generation —
    ledger task **43.15**, carried repair **R43.14**.

    A corpus-scoped layer builds one tree over every source at once and publishes it whole
    (`weft_store.contract.GenerationHolding`), so a half-built tree is never visible to a
    search. A store that cannot open a generation has no way to hide what it is still
    writing, so this is refused before the base runs at all — `require_layers_metadata_
    filter`'s own footing, one contract over. Fitness function 12's family: `valid_options`
    is every installed `NodeStore` name whose factory unwraps to a `GenerationHolding`
    class, not two first-party names hardcoded into the message.
    """

    def __init__(self, message: str, *, valid_options: tuple[str, ...]) -> None:
        super().__init__(message)
        self.valid_options = valid_options


class LayerNeedsConsumingStoreError(WeftError, UnresolvedNameError):
    """A layer sets `layer.store-consumes`, and no store its base names declares that ext model
    in its `consumes` — task **43.17**. `valid_options` is every installed `NodeStore` whose
    class does, read off the registry, so this module names no store (FF28).
    """

    def __init__(self, message: str, *, valid_options: tuple[str, ...]) -> None:
        super().__init__(message)
        self.valid_options = valid_options


class LayerIncrementalStageError(WeftError, UnresolvedNameError):
    """A layer's `layer.incremental` names no stage of its own document — task **43.23**.
    `valid_options` is every stage id the document does name.
    """

    def __init__(self, message: str, *, valid_options: tuple[str, ...]) -> None:
        super().__init__(message)
        self.valid_options = valid_options


class LayerNodeCollisionError(WeftError):
    """A second layer derived a node id another layer already stored — task **43.8**.

    A node id is a digest of its content and its parent, so two layers deriving the same
    text from the same leaf collide on one id: storing the second would silently overwrite
    the first's own `weft_index.payload.Representation` marker. Refused rather than
    overwritten — the batch that collided is recorded `FAILED` first, so nothing here is
    silently accepted.
    """


class LayerDuplicatesBaseStageError(PipelineResolutionError):
    """A layer document names its own `Embedder` or `NodeStore`, which its base already owns.

    Not a name-resolution failure — there is no alternative name to offer, only a stage that
    does not belong in a layer document at all, since `compose_layer` already takes the
    base's own `Embedder`/`NodeStore` for the tail. So this does not join
    `UnresolvedNameError`, on `weft_cli.ingest.BatchScopedStageError`'s own footing.
    """


class LayerFailure(BaseModel):
    """A layer this run tried and could not build, on `failed` of the `of` sources it was
    eligible for — carried repair **R43.9**. `reason` is the first failure's own message; the
    rest are on each source's `LayerRecord`, which `weft sources list` prints.
    """

    model_config = ConfigDict(frozen=True)

    layer: str
    failed: int
    of: int
    reason: str


class LayerJoin(BaseModel):
    """A corpus-scoped layer this run joined sources into rather than rebuilt — task **43.23**:
    `joined` of the new leaves were placed in a cluster of the published tree, `unassigned` in
    none.
    """

    model_config = ConfigDict(frozen=True)

    layer: str
    joined: int
    unassigned: int


class LayerComposition(BaseModel):
    """A layer resolved and checked against its base — `compose_layer`'s return.

    `resolved` is the layer's own `ResolvedPipeline`, kept for a caller that wants its name,
    `vars` or provenance; `layer_specs` is what the layer itself contributes and `tail_specs`
    is the base's own `Embedder`/`NodeStore` specs, in the base's order — the two halves
    ledger task **43.8**'s index loop runs in sequence, `layer_specs` first.

    `scope` — ledger task **43.15** — is `resolved.vars`' own `layer.scope`, read once here
    rather than re-read at every call site that needs it: `_layer_scope`, below, is the only
    function that ever reads `_SCOPE_VAR` off a `ResolvedPipeline` directly.

    `incremental_specs` — task **43.23** — is the stage `layer.incremental` names, taken out of
    `layer_specs`: a corpus-scoped layer stale only by addition runs it alone.
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    layer: str
    base: str
    resolved: ResolvedPipeline
    layer_specs: tuple[StageSpec, ...]
    tail_specs: tuple[StageSpec, ...]
    scope: LayerScope = LayerScope.SOURCE
    incremental_specs: tuple[StageSpec, ...] = ()


def _layer_scope(resolved: ResolvedPipeline, *, layer: str) -> LayerScope:
    """`resolved.vars['layer.scope']` as a `LayerScope` — `LayerScope.SOURCE` when the var is
    absent, `LayerScopeError` for any value that is neither `'source'` nor `'corpus'`, and
    `UnknownLayerVarError` — carried repair **R43.13** — for any `layer.` var outside
    `_KNOWN_LAYER_VARS`.
    """
    for key in resolved.vars:
        if key.startswith("layer.") and key not in _KNOWN_LAYER_VARS:
            raise UnknownLayerVarError(
                f"'{layer}' (or a document it extends) sets '{key}', which no layer reads. "
                f"A layer reads: {', '.join(_KNOWN_LAYER_VARS)}.",
                valid_options=_KNOWN_LAYER_VARS,
                pipeline=layer,
            )
    value = resolved.vars.get(_SCOPE_VAR, LayerScope.SOURCE.value)
    try:
        return LayerScope(value)
    except ValueError as exc:
        raise LayerScopeError(
            f"'{layer}' sets layer.scope to {value!r}; a layer runs per 'source' or over "
            "the whole 'corpus'.",
            pipeline=layer,
        ) from exc


def _layer_store_consumes(resolved: ResolvedPipeline) -> str | None:
    """`resolved.vars['layer.store-consumes']`, or `None` when the document sets none."""
    value = resolved.vars.get(_STORE_CONSUMES_VAR)
    return None if value is None else str(value)


def _split_incremental(
    specs: tuple[StageSpec, ...], resolved: ResolvedPipeline, *, layer: str
) -> tuple[tuple[StageSpec, ...], tuple[StageSpec, ...]]:
    """`(layer_specs, incremental_specs)`: `specs` without the stage `layer.incremental` names,
    and that stage. `LayerIncrementalStageError` when the var names none of `specs`' ids.
    """
    value = resolved.vars.get(_INCREMENTAL_VAR)
    if value is None:
        return specs, ()
    stage_id = str(value)
    if not any(spec.id == stage_id for spec in specs):
        ids = tuple(spec.id for spec in specs)
        raise LayerIncrementalStageError(
            f"'{layer}' sets {_INCREMENTAL_VAR} to '{stage_id}', which is not one of its "
            f"stages. Its stages: {', '.join(ids) or '(none)'}.",
            valid_options=ids,
        )
    return (
        tuple(spec for spec in specs if spec.id != stage_id),
        tuple(spec for spec in specs if spec.id == stage_id),
    )


def installed_layers(
    *,
    registry: Registry,
    reports: Sequence[PackReport],
    contributions: tuple[Contribution, ...] = (),
) -> tuple[str, ...]:
    """Every catalogue document that is a layer — sorted names, from the same catalogue
    `weft index --pipeline` resolves against.

    A document is a layer when it resolves at all, names at least one stage, and every one
    of those stages carries a contract whose own publisher declared `layer_stage = True`
    (R43.16), so a third party's own nodes-in, nodes-out contract qualifies with no edit here.
    A document that fails to resolve is skipped, not refused — `full_catalogue` holds every
    document a project or a pack could name, most of which are not layers and some of which
    cannot resolve without context this function was not given (an unmet `requires`, an
    unfilled slot), and neither is this function's business to diagnose. Only `WeftError` is
    caught: a name resolving into a bug should still crash loudly, not disappear from this list.
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
        if specs and all(_is_layer_stage(spec.contract) for spec in specs):
            layers.append(name)
    return tuple(sorted(layers))


def _consuming_store_names(registry: Registry, *, namespace: str) -> tuple[str, ...]:
    """Every registered `NodeStore` whose class lists a model of `namespace` in `consumes`,
    in `_generation_holding_store_names`' shape.
    """
    return tuple(
        sorted(
            name
            for name in registry.names_for(NodeStore)
            if isinstance(candidate := unwrap_factory(registry.lookup(NodeStore, name)), type)
            and any(
                getattr(model, "__namespace__", None) == namespace
                for model in getattr(candidate, "consumes", ())
            )
        )
    )


def compose_layer_over(
    layer: str,
    *,
    base: str,
    tail_specs: tuple[StageSpec, ...],
    registry: Registry,
    reports: Sequence[PackReport],
    contributions: tuple[Contribution, ...] = (),
) -> LayerComposition:
    """`layer` resolved and checked against a base's own tail specs, given directly rather
    than resolved from a name — ledger task **43.8**.

    `compose_layer` below is the named-base case, which resolves `base` itself to derive
    `tail_specs`; this is the general case a caller who already has the base's own resolved
    `Embedder`/`NodeStore` specs in hand (the default four-stage path's `index_specs`
    constants have no document to resolve at all) can call directly, `base` staying a plain
    string for every message below to name.
    """
    resolved_layer = resolve_named_pipeline(
        layer, registry=registry, reports=reports, contributions=contributions
    )
    scope = _layer_scope(resolved_layer, layer=layer)

    store_consumes = _layer_store_consumes(resolved_layer)
    if store_consumes is not None:
        base_stores = tuple(spec.name for spec in tail_specs if spec.contract is NodeStore)
        options = _consuming_store_names(registry, namespace=store_consumes)
        if not set(base_stores) & set(options):
            stores = ", ".join(f"'{name}'" for name in base_stores)
            installed = ", ".join(options)
            raise LayerNeedsConsumingStoreError(
                f"'{layer}' needs a store that turns '{store_consumes}' into rows of its own "
                f"(consumes), and '{base}' has none — it stores with {stores or '(none)'}. "
                f"Installed stores that can: {installed or '(none)'}.",
                valid_options=options,
            )

    layer_specs = to_specs(resolved_layer, registry=registry, reports=reports)

    for spec in layer_specs:
        if _is_layer_stage(spec.contract) or spec.contract in _TAIL_CONTRACTS:
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
                f"{spec.contract.__name__}, which does not declare layer_stage — a layer's "
                f"stages take stored nodes and return every one of them. Installed layers: "
                f"{', '.join(options) or '(none)'}."
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

    layer_specs, incremental_specs = _split_incremental(layer_specs, resolved_layer, layer=layer)
    return LayerComposition(
        layer=layer,
        base=base,
        resolved=resolved_layer,
        layer_specs=layer_specs,
        tail_specs=tail_specs,
        scope=scope,
        incremental_specs=incremental_specs,
    )


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
    Delegates the rest to `compose_layer_over`, which carries both refusals.
    """
    resolved_base = resolve_named_pipeline(
        base, registry=registry, reports=reports, contributions=contributions
    )
    base_specs = to_specs(resolved_base, registry=registry, reports=reports)
    tail_specs = tuple(spec for spec in base_specs if spec.contract in _TAIL_CONTRACTS)
    return compose_layer_over(
        layer,
        base=base,
        tail_specs=tail_specs,
        registry=registry,
        reports=reports,
        contributions=contributions,
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


def layer_enriched(handed: Sequence[Node], returned: Sequence[Node]) -> tuple[Node, ...]:
    """The handed nodes a layer's stages changed in place — every node in `returned` whose id
    is among `handed`'s and which differs from the node handed under it. Carried repair
    **R43.19**: an `Enhancer` keeps each node's id and adds to it, so `layer_created` alone
    handed the tail nothing and the enrichment was discarded.
    """
    handed_by_id = {node.id: node for node in handed}
    return tuple(
        node
        for node in returned
        if (before := handed_by_id.get(node.id)) is not None and node != before
    )


def _stamped(created: Sequence[Node], *, layer: str) -> tuple[Node, ...]:
    """`created`, each carrying `LayerMember(layer=layer)` (R43.23). A leaf passed through or
    enriched in place is the base's own node and is never passed here.
    """
    return tuple(node.with_ext(LayerMember(layer=layer)) for node in created)


def _not_a_leaf_namespaces() -> tuple[str, ...]:
    """Every registered ext model's namespace whose class declares `not_a_leaf = True`, read
    as `_is_layer_stage` reads `layer_stage`, so this module names no pack's model (FF28).
    """
    namespaces: list[str] = []
    for namespace in sorted(ext_models.names_for(ExtModel)):
        registrant = ext_models.lookup(ExtModel, namespace)
        if not (isinstance(registrant, type) and issubclass(registrant, ExtModel)):
            continue
        if getattr(registrant, "not_a_leaf", False) is True:
            namespaces.append(namespace)
    return tuple(namespaces)


def layer_leaf_filter(sources: Sequence[SourceId]) -> Filter:
    """The selection a layer's own batch reads its leaves through — ledger task **43.8**,
    extended **R43.22**.

    `IN lineage.sources` narrows to this batch's own sources; `NOT(EXISTS
    ext.weft-index.technique)` leaves out every node an `Expander` already derived, so a layer
    never re-enriches another layer's output; and every registered ext model declaring
    `not_a_leaf` excludes the nodes carrying it (R43.22). Every stored namespace carries
    `__schema_version__`, which is what the `EXISTS` reads.
    """
    return Filter(
        op=FilterOp.AND,
        clauses=(
            Filter(
                op=FilterOp.IN,
                field="lineage.sources",
                value=tuple(str(source) for source in sources),
            ),
            Filter(
                op=FilterOp.NOT,
                clauses=(
                    Filter(
                        op=FilterOp.EXISTS,
                        field=f"ext.{Representation.__namespace__}.technique",
                    ),
                ),
            ),
            *(
                Filter(
                    op=FilterOp.NOT,
                    clauses=(
                        Filter(
                            op=FilterOp.EXISTS,
                            field=f"ext.{namespace}.{SCHEMA_VERSION_KEY}",
                        ),
                    ),
                )
                for namespace in _not_a_leaf_namespaces()
            ),
        ),
    )


def compose_layers(
    layers: tuple[str, ...],
    *,
    base: str,
    specs: tuple[StageSpec, ...],
    registry: Registry,
    reports: Sequence[PackReport],
    contributions: tuple[Contribution, ...],
) -> tuple[LayerComposition, ...]:
    """Every named layer, checked against the catalogue and composed with `specs`' own tail —
    ledger task **43.8**. `UnknownLayerError` for a name `full_catalogue` does not hold at
    all; `compose_layer_over`'s own `NotALayerError`/`LayerDuplicatesBaseStageError` for one
    that resolves but is not a layer, or duplicates the base's own `Embedder`/`NodeStore`.
    Called by `weft_cli.ingest.run_index` before anything is written or deleted.
    """
    if not layers:
        return ()
    catalogue = full_catalogue(reports=reports)
    tail_specs = tuple(spec for spec in specs if spec.contract in _TAIL_CONTRACTS)
    compositions: list[LayerComposition] = []
    for name in layers:
        if name not in catalogue:
            options = installed_layers(
                registry=registry, reports=reports, contributions=contributions
            )
            raise UnknownLayerError(
                f"'{name}' is not an installed layer. Installed layers: "
                f"{', '.join(options) or '(none)'}.",
                valid_options=options,
                pipeline=name,
            )
        compositions.append(
            compose_layer_over(
                name,
                base=base,
                tail_specs=tail_specs,
                registry=registry,
                reports=reports,
                contributions=contributions,
            )
        )
    return tuple(compositions)


def _stage_instance(runnable: RunnablePipeline, stage_id: str | None) -> object | None:
    """The built instance of `runnable`'s own stage named `stage_id`, or `None`."""
    if stage_id is None:
        return None
    for stage in runnable.stages:
        if stage.id == stage_id:
            return stage.instance
    return None


def require_layers_metadata_filter(
    layers: tuple[str, ...],
    *,
    runnable: RunnablePipeline,
    store_stage_id: str | None,
    specs: tuple[StageSpec, ...],
) -> None:
    """`LayerNeedsMetadataFilterError` unless the primary store's own instance can `matching` —
    ledger task **43.8**. A no-op when no layer is named, and called only once every named
    layer has already composed cleanly, before the base runs.
    """
    if not layers:
        return
    instance = _stage_instance(runnable, store_stage_id)
    if callable(getattr(instance, "matching", None)):
        return
    plugin = next((spec.name for spec in specs if spec.contract is NodeStore), "(none)")
    raise LayerNeedsMetadataFilterError(
        "layers need a store that can select stored nodes by metadata (MetadataFilter), and "
        f"the '{plugin}' store cannot, so '{layers[0]}' has no way to read the leaves it "
        "enriches. Run without layers, or index into a store that implements MetadataFilter."
    )


def _generation_holding_store_names(registry: Registry) -> tuple[str, ...]:
    """Every `NodeStore` name `registry` carries whose factory unwraps to a class that
    structurally satisfies `weft_store.contract.GenerationHolding` — carried repair
    **R43.14**, `LayerNeedsGenerationHoldingError`'s own `valid_options`.

    `weft_kernel.registry.unwrap_factory` peels a `functools.partial` back to the class it
    constructs; `weft_engine.run_services.class_provides` is the shared `issubclass`-that-
    answers-`False`-instead-of-raising helper the store family already carries for exactly
    this — a factory that unwraps to a plain function (`partial(fn, settings)`) is not a
    class, and `class_provides` says so rather than crashing this computation.
    """
    return tuple(
        sorted(
            name
            for name in registry.names_for(NodeStore)
            if isinstance(candidate := unwrap_factory(registry.lookup(NodeStore, name)), type)
            and class_provides(candidate, GenerationHolding)
        )
    )


def require_corpus_layers_generation_holding(
    compositions: Sequence[LayerComposition],
    *,
    runnable: RunnablePipeline,
    specs: tuple[StageSpec, ...],
    registry: Registry,
) -> None:
    """`LayerNeedsGenerationHoldingError` unless every `NodeStore` stage `specs` names is a
    `weft_store.contract.GenerationHolding` — ledger task **43.15**, carried repair
    **R43.11**/**R43.14**, `require_layers_metadata_filter`'s own footing, one contract
    over. A no-op when none of `compositions` is corpus-scoped, and called only once every
    named layer has already composed cleanly, before the base runs.

    Every failing stage is named — never only the first, and never a store that can
    actually hold one — because a base naming two or more stores (`index-with-graph`
    onward) may fail on any subset of them.
    """
    corpus_layer = next(
        (composition for composition in compositions if composition.scope is LayerScope.CORPUS),
        None,
    )
    if corpus_layer is None:
        return
    store_specs = tuple(spec for spec in specs if spec.contract is NodeStore)
    failing = tuple(
        spec
        for spec in store_specs
        if not isinstance(_stage_instance(runnable, spec.id), GenerationHolding)
    )
    if not failing:
        return
    valid_options = _generation_holding_store_names(registry)
    stage_word = "store stage" if len(failing) == 1 else "store stages"
    names = ", ".join(f"'{spec.id}' ({spec.name})" for spec in failing)
    installed = ", ".join(valid_options) if valid_options else "(none installed)"
    raise LayerNeedsGenerationHoldingError(
        f"'{corpus_layer.layer}' builds one tree over the whole corpus, as a generation "
        f"published whole, and {stage_word} {names} cannot hold generations "
        "(GenerationHolding). Run it per source (drop layer.scope: corpus), or remove or "
        f"replace that stage, or index into a store that can: {installed}.",
        valid_options=valid_options,
    )


def _get_source_of(
    instance: object,
) -> Callable[[SourceId], Awaitable[SourceRecord | None]] | None:
    """`instance.get_source`, if it has one and it is callable — the defensive shape
    `weft_cli.ingest._put_source_of` already carries for the sibling method.
    """
    found = getattr(instance, "get_source", None)
    if found is None or not callable(found):
        return None
    return cast(Callable[[SourceId], Awaitable[SourceRecord | None]], found)


def _put_source_of(
    instance: object,
) -> Callable[[SourceRecord], Awaitable[None]] | None:
    """`instance.put_source`, if it has one and it is callable — `_get_source_of`'s own shape."""
    found = getattr(instance, "put_source", None)
    if found is None or not callable(found):
        return None
    return cast(Callable[[SourceRecord], Awaitable[None]], found)


def _get_of(instance: object) -> Callable[[Sequence[NodeId]], Awaitable[Sequence[Node]]] | None:
    """`instance.get`, if it has one and it is callable — `_get_source_of`'s own shape."""
    found = getattr(instance, "get", None)
    if found is None or not callable(found):
        return None
    return cast(Callable[[Sequence[NodeId]], Awaitable[Sequence[Node]]], found)


def _matching_of(
    instance: object,
) -> Callable[[Filter, Cursor | None], Awaitable[Page[Node]]] | None:
    """`instance.matching`, if it has one and it is callable — `_get_source_of`'s own shape.

    `weft_store.contract.MetadataFilter` is not a base any `GenerationHolding` handle is
    typed against, so a bound writer's own `matching` is read this way rather than as a
    static attribute — `_run_corpus_layer`'s own reader for `require_layers_metadata_
    filter`'s promise about the **unbound** store it checked.
    """
    found = getattr(instance, "matching", None)
    if found is None or not callable(found):
        return None
    return cast(Callable[[Filter, Cursor | None], Awaitable[Page[Node]]], found)


class _LayerRunDecision(StrEnum):
    """What a layer batch does about one eligible source — ledger task **43.8**, the
    vocabulary `_layer_decision` returns.
    """

    #: No record for this layer, or one left `INDEXING` by an interrupted run: run it.
    RUN = "run"
    #: A record under the identity this run would build again, `ACTIVE`, or `FAILED` without
    #: `retry_failed`: leave it exactly as it is.
    SKIP = "skip"
    #: A record under a different identity than this run would build: reported, never re-run
    #: unasked.
    CHANGED = "changed"


def _layer_decision(
    existing: LayerRecord | None, *, identity: str, retry_failed: bool
) -> _LayerRunDecision:
    """Ledger task **43.8**'s own per-source table — see `run_layers`' own docstring for the
    four cases this reads off `existing`.
    """
    if existing is None or existing.status is LayerStatus.INDEXING:
        return _LayerRunDecision.RUN
    if existing.pipeline_identity != identity:
        # R43.9: a failed build holds nothing to protect, and its refusal's own remedy — a
        # bound raised in the stage's `with:` — is exactly what moves the identity.
        if existing.status is LayerStatus.FAILED:
            return _LayerRunDecision.RUN
        return _LayerRunDecision.CHANGED
    if existing.status is LayerStatus.ACTIVE:
        return _LayerRunDecision.SKIP
    return _LayerRunDecision.RUN if retry_failed else _LayerRunDecision.SKIP


async def _apply_layer_records(
    runnable: RunnablePipeline,
    *,
    store_stage_id: str,
    store_stage_ids: Sequence[str],
    updates: Mapping[SourceId, LayerRecord],
) -> None:
    """Write `updates` onto each source's own record — ledger task **43.8**, `weft_cli.ingest.
    _record_sources`' own shape for a layer instead of a whole source.

    Each record is read once, from the **primary** store (`store_stage_id`), never from
    whichever store stage is being written to — the identical "the record re-read from the
    primary" rule, so two stores never drift onto two different ideas of what the other
    layers on a source are. Replaces only `new_layer`'s own entry, appending it when the
    source carries no layer of that name yet; every other layer and its order are untouched.
    """
    if not updates:
        return
    primary = _stage_instance(runnable, store_stage_id)
    get_source = _get_source_of(primary) if primary is not None else None
    if get_source is None:
        return
    wanted = set(store_stage_ids)
    put_sources = [
        put_source
        for stage in runnable.stages
        if stage.id in wanted
        for put_source in (_put_source_of(stage.instance),)
        if put_source is not None
    ]
    if not put_sources:
        return
    for source_id, new_layer in updates.items():
        record = await get_source(source_id)
        if record is None:
            continue
        if any(existing.name == new_layer.name for existing in record.layers):
            layers = tuple(
                new_layer if existing.name == new_layer.name else existing
                for existing in record.layers
            )
        else:
            layers = (*record.layers, new_layer)
        updated = record.model_copy(update={"layers": layers})
        for put_source in put_sources:
            await put_source(updated)


async def _fail_layer_batch(
    runnable: RunnablePipeline,
    *,
    store_stage_id: str,
    store_stage_ids: Sequence[str],
    layer: str,
    identity: str,
    batch_refs: Sequence[SourceRef],
    attempts_by_source: Mapping[SourceId, int],
    error_type: str,
    stage: str | None,
    message: str,
) -> None:
    """Every source in `batch_refs` recorded `FAILED` for `layer` — ledger task **43.8**,
    `weft_cli.ingest._record_batch_failure`'s own shape one layer over. Called before a
    `Failed` outcome or a raised `WeftError` is handled the rest of the way — a continue to
    the next batch, or a re-raise the caller performs itself.
    """
    now = datetime.now(UTC)
    await _apply_layer_records(
        runnable,
        store_stage_id=store_stage_id,
        store_stage_ids=store_stage_ids,
        updates={
            ref.source_id: LayerRecord(
                name=layer,
                pipeline_identity=identity,
                status=LayerStatus.FAILED,
                failure=SourceFailure(
                    error_type=error_type,
                    stage=stage,
                    message=message,
                    attempts=attempts_by_source[ref.source_id],
                    last_attempt_at=now,
                ),
                attempts=attempts_by_source[ref.source_id],
                at=now,
            )
            for ref in batch_refs
        },
    )


def _sliced(items: Sequence[SourceRef], size: int | None) -> list[tuple[SourceRef, ...]]:
    """`items`, in groups of `size` (or one whole group when `size` is `None`) — `run_layers`'
    own batching of its `to_run` subset.
    """
    if size is None:
        return [tuple(items)]
    return [tuple(items[start : start + size]) for start in range(0, len(items), size)]


async def _current_records(
    get_source: Callable[[SourceId], Awaitable[SourceRecord | None]], refs: Sequence[SourceRef]
) -> dict[SourceId, SourceRecord]:
    """Every one of `refs`' own `SourceRecord`, read fresh off the primary store — the
    eligibility read `_layer_eligible` runs its table over, always re-read rather than reused
    from `weft_cli.ingest.run_index`'s own `previous`, which was read before the base wrote
    anything.
    """
    records: dict[SourceId, SourceRecord] = {}
    for ref in refs:
        record = await get_source(ref.source_id)
        if record is not None:
            records[ref.source_id] = record
    return records


def _layer_eligible(
    refs: Sequence[SourceRef],
    records: Mapping[SourceId, SourceRecord],
    *,
    layer: str,
    identity: str,
    retry_failed: bool,
) -> tuple[list[SourceRef], list[SourceRef], dict[SourceId, LayerRecord | None], int, bool]:
    """`(eligible, to_run, existing_by_source, queryable_baseline, changed)` for one layer —
    ledger task **43.8**'s own per-source table, applied over every `ACTIVE` source. `changed`
    is `True` the moment any source's own record for `layer` carries a different identity —
    `run_layers` reports the name once, however many sources moved.
    """
    eligible: list[SourceRef] = []
    to_run: list[SourceRef] = []
    existing_by_source: dict[SourceId, LayerRecord | None] = {}
    queryable = 0
    changed = False
    for ref in refs:
        record = records.get(ref.source_id)
        if record is None or record.status is not SourceStatus.ACTIVE:
            continue
        eligible.append(ref)
        existing = next((entry for entry in record.layers if entry.name == layer), None)
        existing_by_source[ref.source_id] = existing
        decision = _layer_decision(existing, identity=identity, retry_failed=retry_failed)
        if decision is _LayerRunDecision.RUN:
            to_run.append(ref)
        elif decision is _LayerRunDecision.CHANGED:
            changed = True
        elif existing is not None and existing.status is LayerStatus.ACTIVE:
            queryable += 1
    return eligible, to_run, existing_by_source, queryable, changed


def _next_layer_attempts(
    existing_by_source: Mapping[SourceId, LayerRecord | None], batch_refs: Sequence[SourceRef]
) -> dict[SourceId, int]:
    """`LayerRecord.attempts` for each of `batch_refs`' next write — `previous + 1`, or `1`
    when this source carries no record for this layer yet.
    """
    return {
        ref.source_id: (
            existing.attempts + 1 if (existing := existing_by_source[ref.source_id]) else 1
        )
        for ref in batch_refs
    }


async def _paged_leaves(
    matching: Callable[[Filter, Cursor | None], Awaitable[Page[Node]]], ids: tuple[SourceId, ...]
) -> list[Node]:
    """Every leaf `layer_leaf_filter(ids)` selects, paged to the end — `weft_cli.ingest.
    count_degraded_expansions`' own paging shape, one filter over.
    """
    leaves: list[Node] = []
    cursor: Cursor | None = None
    while True:
        page = await matching(layer_leaf_filter(ids), cursor)
        leaves.extend(page.items)
        if page.next_cursor is None:
            return leaves
        cursor = page.next_cursor


def _layer_collision(
    created: Sequence[Node],
    existing: Sequence[Node],
    *,
    layer: str,
) -> LayerNodeCollisionError | None:
    """The first node in `created` whose id `existing` already holds under a different
    `weft_index.payload.Representation.technique`, or `None` — ledger task **43.8**.
    """
    existing_by_id = {node.id: node for node in existing}
    for node in created:
        clash = existing_by_id.get(node.id)
        if clash is None:
            continue
        clash_repr = clash.ext_as(Representation)
        new_repr = node.ext_as(Representation)
        clash_technique = clash_repr.technique if clash_repr is not None else "?"
        new_technique = new_repr.technique if new_repr is not None else "?"
        if clash_technique != new_technique:
            return LayerNodeCollisionError(
                f"layer '{layer}' derived node {node.id}, which the '{clash_technique}' layer "
                "already wrote: two layers producing one node would erase each other's "
                "marker. Run one of them, or change what one derives."
            )
    return None


async def _run_one_layer_batch(
    runnable: RunnablePipeline,
    *,
    runner: Runner,
    layer_runnable: RunnablePipeline,
    tail_runnable: RunnablePipeline,
    matching: Callable[[Filter, Cursor | None], Awaitable[Page[Node]]],
    get_nodes: Callable[[Sequence[NodeId]], Awaitable[Sequence[Node]]] | None,
    store_stage_id: str,
    store_stage_ids: Sequence[str],
    composition: LayerComposition,
    identity: str,
    batch_refs: Sequence[SourceRef],
    attempts_by_source: Mapping[SourceId, int],
    indexing_ctx: Context,
) -> str | None:
    """One layer batch's whole mechanics, lifted out of `run_layers` so that function's own
    complexity stays under the budget every function in this tree already holds to — ledger
    task **43.8**. `None` once every source in `batch_refs` is `ACTIVE` (whether or not there
    was anything to derive); the failure's reason once every one is `FAILED` and the loop above
    should move on to the next batch. `WeftError`/`LayerNodeCollisionError` always propagate
    instead of returning, after this batch is recorded `FAILED` the same way
    `_fail_layer_batch` always records one.
    """
    await _apply_layer_records(
        runnable,
        store_stage_id=store_stage_id,
        store_stage_ids=store_stage_ids,
        updates={
            ref.source_id: LayerRecord(
                name=composition.layer,
                pipeline_identity=identity,
                status=LayerStatus.INDEXING,
                attempts=attempts_by_source[ref.source_id],
                at=datetime.now(UTC),
            )
            for ref in batch_refs
        },
    )

    ids = tuple(ref.source_id for ref in batch_refs)
    leaves = await _paged_leaves(matching, ids)
    if not leaves:
        await _apply_layer_records(
            runnable,
            store_stage_id=store_stage_id,
            store_stage_ids=store_stage_ids,
            updates={
                ref.source_id: LayerRecord(
                    name=composition.layer,
                    pipeline_identity=identity,
                    status=LayerStatus.ACTIVE,
                    attempts=attempts_by_source[ref.source_id],
                    at=datetime.now(UTC),
                )
                for ref in batch_refs
            },
        )
        return None

    first_stage_id = composition.layer_specs[0].id
    try:
        outcome = await runner.run_once(layer_runnable, leaves, indexing_ctx)
    except WeftError as exc:
        await _fail_layer_batch(
            runnable,
            store_stage_id=store_stage_id,
            store_stage_ids=store_stage_ids,
            layer=composition.layer,
            identity=identity,
            batch_refs=batch_refs,
            attempts_by_source=attempts_by_source,
            error_type=type(exc).__name__,
            stage=exc.stage,
            message=str(exc),
        )
        raise
    if isinstance(outcome, Failed):
        await _fail_layer_batch(
            runnable,
            store_stage_id=store_stage_id,
            store_stage_ids=store_stage_ids,
            layer=composition.layer,
            identity=identity,
            batch_refs=batch_refs,
            attempts_by_source=attempts_by_source,
            error_type="Failed",
            stage=first_stage_id,
            message=outcome.reason,
        )
        return outcome.reason

    produced_nodes = cast("Sequence[Node]", outcome.value if isinstance(outcome, Produced) else ())
    created = layer_created(leaves, produced_nodes)
    enriched = layer_enriched(leaves, produced_nodes)
    if created or enriched:
        existing_nodes = (
            await get_nodes([node.id for node in created]) if get_nodes is not None else ()
        )
        collision = _layer_collision(created, existing_nodes, layer=composition.layer)
        if collision is not None:
            await _fail_layer_batch(
                runnable,
                store_stage_id=store_stage_id,
                store_stage_ids=store_stage_ids,
                layer=composition.layer,
                identity=identity,
                batch_refs=batch_refs,
                attempts_by_source=attempts_by_source,
                error_type=type(collision).__name__,
                stage=first_stage_id,
                message=str(collision),
            )
            raise collision

        try:
            tail_outcome = await _run_corpus_tail(
                runner,
                tail_runnable,
                (*enriched, *_stamped(created, layer=composition.layer)),
                indexing_ctx,
                embed_stage_ids=frozenset(
                    spec.id for spec in composition.tail_specs if spec.contract is Embedder
                ),
                store_stage_ids=frozenset(
                    spec.id for spec in composition.tail_specs if spec.contract is NodeStore
                ),
            )
        except WeftError as exc:
            await _fail_layer_batch(
                runnable,
                store_stage_id=store_stage_id,
                store_stage_ids=store_stage_ids,
                layer=composition.layer,
                identity=identity,
                batch_refs=batch_refs,
                attempts_by_source=attempts_by_source,
                error_type=type(exc).__name__,
                stage=exc.stage,
                message=str(exc),
            )
            raise
        if isinstance(tail_outcome, Failed):
            await _fail_layer_batch(
                runnable,
                store_stage_id=store_stage_id,
                store_stage_ids=store_stage_ids,
                layer=composition.layer,
                identity=identity,
                batch_refs=batch_refs,
                attempts_by_source=attempts_by_source,
                error_type="Failed",
                stage=first_stage_id,
                message=tail_outcome.reason,
            )
            return tail_outcome.reason

    await _apply_layer_records(
        runnable,
        store_stage_id=store_stage_id,
        store_stage_ids=store_stage_ids,
        updates={
            ref.source_id: LayerRecord(
                name=composition.layer,
                pipeline_identity=identity,
                status=LayerStatus.ACTIVE,
                attempts=attempts_by_source[ref.source_id],
                at=datetime.now(UTC),
            )
            for ref in batch_refs
        },
    )
    return None


async def _emit_layer_progress(
    on_batch: Callable[[BatchProgress], Awaitable[None]] | None,
    *,
    layer: str,
    batch_number: int,
    batches: int,
    queryable: int,
    documents: int,
    start_time: float,
) -> None:
    """`on_batch`, fed one `BatchProgress` per finished layer batch — ledger task **43.8**.

    `weft_cli.ingest._emit_batch_progress`'s own shape, one field over: a layer batch is only
    ever emitted for a batch this loop actually ran (never for a layer with nothing left to
    do), so there is no empty-`documents` case to guard here the way the base's own emitter
    does.
    """
    if on_batch is None:
        return
    await on_batch(
        BatchProgress(
            batch=batch_number,
            batches=batches,
            queryable=queryable,
            documents=documents,
            seconds=time.monotonic() - start_time,
            layer=layer,
        )
    )


def _corpus_layer_status(
    eligible: Sequence[SourceRef],
    records: Mapping[SourceId, SourceRecord],
    *,
    layer: str,
    identity: str,
) -> tuple[bool, bool, dict[SourceId, LayerRecord | None]]:
    """`(build, changed, existing_by_source)` for one corpus-scoped layer over `eligible` —
    ledger task **43.15**'s own all-or-nothing table, one level up from `_layer_decision`'s
    per-source one. A corpus-scoped layer is one generation over every eligible source at
    once, so there is no per-source `RUN`/`SKIP`: either the whole tree is already built
    (every eligible source carries this layer `ACTIVE` under `identity`) and nothing runs, or
    some source carries a *different* identity — reported, left alone, nothing runs either —
    or the whole corpus is built, whether the gap is a stale identity's neighbour, a source
    this layer never reached, or one an earlier build left `FAILED`/`INDEXING`. A build left
    `FAILED` or `INDEXING` under another identity holds nothing to protect, so it is rebuilt
    unasked rather than reported (R43.9, extended to an interrupted build at task 43.20).
    """
    existing_by_source: dict[SourceId, LayerRecord | None] = {}
    all_active = True
    changed = False
    for ref in eligible:
        record = records[ref.source_id]
        existing = next((entry for entry in record.layers if entry.name == layer), None)
        existing_by_source[ref.source_id] = existing
        if existing is None:
            all_active = False
            continue
        if existing.pipeline_identity != identity and existing.status not in _UNFINISHED:
            changed = True
            all_active = False
            continue
        if existing.status is not LayerStatus.ACTIVE:
            all_active = False
    if all_active:
        return False, False, existing_by_source
    return (False, True, existing_by_source) if changed else (True, False, existing_by_source)


async def _run_corpus_tail(
    runner: Runner,
    tail_runnable: RunnablePipeline,
    created: Sequence[Node],
    ctx: Context,
    *,
    embed_stage_ids: frozenset[str],
    store_stage_ids: frozenset[str],
) -> Outcome[object]:
    """A corpus-scoped tail's own two-step run — ledger task **43.15**, carried repair
    **R43.11**. Every `NodeStore` stage in `tail_runnable` is already bound to its *own*
    generation's writer by the caller, one bound instance per store — so a node this build
    creates reaches every store the base names, each inside its own generation, never only
    the primary's.

    `embed_stage_ids`/`store_stage_ids` are the tail's own `Embedder`/`NodeStore` stage ids,
    read by the caller off `LayerComposition.tail_specs`' own contracts — never derived by
    elimination here, so a tail naming stages under neither contract is never silently
    folded into either half.

    Decides only what reaches the `Embedder` stage(s), if any: a node the layer already
    embedded itself — as `raptor` embeds its own summaries — is never handed to it a second
    time, on `index-with-raptor`'s own rule, one contract over. The embedder stage is
    skipped **entirely**, never called with an empty payload, when nothing lacks a vector.
    """
    unembedded = tuple(node for node in created if node.embedding is None)
    if unembedded:
        embed_stages = tuple(stage for stage in tail_runnable.stages if stage.id in embed_stage_ids)
        if embed_stages:
            embed_outcome = await runner.run_once(
                replace(tail_runnable, stages=embed_stages), unembedded, ctx
            )
            if not isinstance(embed_outcome, Produced):
                return embed_outcome
            embedded = cast("Sequence[Node]", embed_outcome.value)
        else:
            embedded = unembedded
        to_store = (*(node for node in created if node.embedding is not None), *embedded)
    else:
        to_store = created
    store_stages = tuple(stage for stage in tail_runnable.stages if stage.id in store_stage_ids)
    if not store_stages:
        return Produced(value=to_store)
    return await runner.run_once(replace(tail_runnable, stages=store_stages), to_store, ctx)


@dataclass
class _CorpusGenerations:
    """One corpus build's generations, one per tail store — carried repair **R43.11**, task
    **43.20**. All keyed by stage id: `holders` is the unbound instance every lifecycle call
    (`publish_generation`/`retract_generation`/`generations`) is issued through; `writers` is
    the bound handle every write goes through, one per store, never shared; `opened` is the
    generation each writer is bound to. `adopted` says those were left `BUILDING` by an
    interrupted build rather than opened by this one; `abandoned` holds what `reopen` let go,
    so a failure retracts it too.
    """

    holders: dict[str, GenerationHolding]
    writers: dict[str, object]
    opened: dict[str, GenerationRecord]
    adopted: bool
    abandoned: list[tuple[str, GenerationId]] = field(
        default_factory=list[tuple[str, GenerationId]]
    )

    async def reopen(self, layer: str) -> None:
        """A fresh generation per store, bound in place of the one the build was writing into."""
        self.abandoned.extend((stage_id, record.id) for stage_id, record in self.opened.items())
        for stage_id, holder in self.holders.items():
            self.opened[stage_id] = await holder.open_generation(layer)
            self.writers[stage_id] = await holder.bind_generation(self.opened[stage_id].id)

    async def retract(self) -> None:
        opened = [(stage_id, record.id) for stage_id, record in self.opened.items()]
        for stage_id, generation in (*self.abandoned, *opened):
            await self.holders[stage_id].retract_generation(generation)


def _newest_building(listed: Sequence[GenerationRecord], *, layer: str) -> GenerationRecord | None:
    building = [
        record
        for record in listed
        if record.layer == layer and record.status is GenerationStatus.BUILDING
    ]
    return max(building, key=lambda record: record.opened_at, default=None)


async def _bind_corpus_generations(
    runnable: RunnablePipeline,
    *,
    layer: str,
    tail_store_specs: Sequence[StageSpec],
    resume: bool,
) -> _CorpusGenerations:
    """Every tail store's generation, bound **on its own instance** — carried repair
    **R43.11**, lifted out of `_run_corpus_layer` for its own complexity budget.

    With `resume` — this layer's records say a build under this identity was interrupted —
    each store's newest `BUILDING` generation of `layer` is adopted, so what that build kept is
    recalled rather than paid for again (task **43.20**). Adoption is all or nothing: a store
    with none to adopt means every store opens afresh. Either way every other `BUILDING`
    generation of `layer` is retracted before the stage runs.
    """
    holders = {
        spec.id: cast(GenerationHolding, _stage_instance(runnable, spec.id))
        for spec in tail_store_specs
    }
    adopted: dict[str, GenerationRecord] = {}
    if resume:
        for stage_id, holder in holders.items():
            newest = _newest_building(await holder.generations(), layer=layer)
            if newest is None:
                adopted = {}
                break
            adopted[stage_id] = newest
    for stage_id, holder in holders.items():
        kept = adopted[stage_id].id if stage_id in adopted else None
        for other in await holder.generations():
            if (
                other.layer == layer
                and other.status is GenerationStatus.BUILDING
                and other.id != kept
            ):
                await holder.retract_generation(other.id)
    opened = dict(adopted)
    for stage_id, holder in holders.items():
        if stage_id not in opened:
            opened[stage_id] = await holder.open_generation(layer)
    writers: dict[str, object] = {
        stage_id: await holders[stage_id].bind_generation(record.id)
        for stage_id, record in opened.items()
    }
    return _CorpusGenerations(
        holders=holders, writers=writers, opened=opened, adopted=bool(adopted)
    )


def _checkpoint_namespace(layer: str, llm: LLMSection) -> str:
    """What every `LayerCheckpoints` key of one build is scoped by: the layer, and a digest of
    the run's `[llm.roles]`, since a stage asks a role and never sees which model answered.
    """
    roles = json.dumps(llm.roles.model_dump(mode="json"), sort_keys=True)
    return f"{layer}/{hashlib.sha256(roles.encode()).hexdigest()[:16]}"


class _GenerationCheckpoints:
    """`weft_index.contract.LayerCheckpoints` over one corpus build's bound generations — task
    **43.20**. `keep` writes through the tail's store stages, each bound to its own store's
    generation, so a kept node reaches every store; `recall` reads the primary's bound handle,
    which sees its own generation before anything is published.
    """

    def __init__(
        self,
        *,
        runner: Runner,
        store_tail: RunnablePipeline,
        matching: Callable[[Filter, Cursor | None], Awaitable[Page[Node]]],
        namespace: str,
        layer: str,
        ctx: Context,
    ) -> None:
        self._runner = runner
        self._store_tail = store_tail
        self._matching = matching
        self._namespace = namespace
        self._layer = layer
        self._ctx = ctx
        self.kept: set[NodeId] = set()

    def _scoped(self, key: str) -> str:
        return f"{self._namespace}/{key}"

    async def recall(self, key: str) -> Node | None:
        page = await self._matching(
            Filter(op=FilterOp.EQ, field=_CHECKPOINT_FIELD, value=self._scoped(key)), None
        )
        return page.items[0] if page.items else None

    async def keep(self, key: str, node: Node) -> None:
        stamped = node.with_ext(LayerMember(layer=self._layer, checkpoint=self._scoped(key)))
        outcome = await self._runner.run_once(self._store_tail, (stamped,), self._ctx)
        if not isinstance(outcome, Produced):
            raise WeftError(
                f"'{self._layer}' could not keep a finished node in its building generation, "
                f"so an interrupted build would pay for it again: {outcome.reason}"
            )
        self.kept.add(node.id)


class _OfferedServices(ServiceRegistry):
    """`base`'s services plus those one layer stage run is offered — task **43.20**. The run's
    own registry is never added to, so a corpus build's checkpoints reach no other stage.
    """

    def __init__(self, base: ServiceRegistry) -> None:
        super().__init__()
        self._base = base

    def resolve[T](self, contract: type[T]) -> T:
        try:
            return super().resolve(contract)
        except UnresolvedServiceError as offered:
            try:
                return self._base.resolve(contract)
            except UnresolvedServiceError as missing:
                options = tuple(sorted({*offered.valid_options, *missing.valid_options}))
                raise UnresolvedServiceError(
                    f"no service is registered for {contract.__name__} on this run. It is "
                    "unavailable because nothing resolved one before this stage ran. "
                    f"Services available on this run: {', '.join(options)}.",
                    valid_options=options,
                ) from missing


def _with_checkpoints(ctx: Context, checkpoints: _GenerationCheckpoints) -> Context:
    services = _OfferedServices(ctx.services)
    services.add(LayerCheckpoints, checkpoints)
    return replace(ctx, services=services)


class _GenerationRevision:
    """`weft_index.contract.LayerRevision` over one join — task **43.23**: what the stage
    replaced, left out of the summaries carried forward, and how many leaves it placed nowhere.
    """

    def __init__(self, layer: str) -> None:
        self.layer = layer
        self.replaced_ids: set[NodeId] = set()
        self.unassigned_count = 0

    async def replaced(self, old: NodeId) -> None:
        self.replaced_ids.add(old)

    async def unassigned(self, count: int) -> None:
        self.unassigned_count += count


def _with_revision(ctx: Context, revision: _GenerationRevision, *, store: object) -> Context:
    """`ctx` offering `revision`, and the join's bound primary as `NodeStore`: the stage reads
    the published tree through the generation it writes into, as `LayerCheckpoints.recall`
    does, never through a handle opened before that tree was published.
    """
    services = _OfferedServices(ctx.services)
    services.add(LayerRevision, revision)
    services.add(NodeStore, cast(NodeStore, store))
    return replace(ctx, services=services)


async def _holds_unpublishable(
    generations: _CorpusGenerations,
    checkpoints: _GenerationCheckpoints,
    matching: Callable[[Filter, Cursor | None], Awaitable[Page[Node]]],
    *,
    layer: str,
    created: Sequence[Node],
) -> bool:
    """Whether the generation the build wrote into holds a kept node the build did not create
    — task **43.20**. An adopted one may: a source added since, or another model, moves the
    clusters its kept summaries answered. Publishing it would publish them.
    """
    created_ids = {node.id for node in created}
    if checkpoints.kept - created_ids:
        return True
    if not generations.adopted:
        return False
    cursor: Cursor | None = None
    while True:
        page = await matching(Filter(op=FilterOp.EQ, field=_LAYER_FIELD, value=layer), cursor)
        for node in page.items:
            member = node.ext_as(LayerMember)
            if member is not None and member.checkpoint is not None and node.id not in created_ids:
                return True
        if page.next_cursor is None:
            return False
        cursor = page.next_cursor


async def _publish_and_supersede_generations(
    holders: Mapping[str, GenerationHolding],
    opened: Mapping[str, GenerationRecord],
    *,
    layer: str,
) -> None:
    """Every generation `opened` published, then every **older** generation of `layer` each
    store still holds retracted — carried repair **R43.11**, lifted out of `_run_corpus_
    layer` for its own complexity budget.

    The exclusion set is every id *this build* opened, across **every** store, not only the
    one a given store's own loop iteration is superseding: pgvector's generations catalogue
    can be shared per target, so excluding only a store's own freshly-opened id could still
    let this loop retract a sibling store's fresh generation out from under it.
    """
    for stage_id, generation in opened.items():
        await holders[stage_id].publish_generation(generation.id)
    opened_ids = frozenset(generation.id for generation in opened.values())
    for stage_id in opened:
        holder = holders[stage_id]
        for other in await holder.generations():
            if (
                other.layer == layer
                and other.id not in opened_ids
                and other.status in (GenerationStatus.PUBLISHED, GenerationStatus.BUILDING)
            ):
                await holder.retract_generation(other.id)


def _corpus_outcome_refusal(
    outcome: Outcome[object], leaves: Sequence[Node], *, layer: str
) -> tuple[str, str] | None:
    """`(error_type, reason)` when a corpus-scoped build must stop at its layer's outcome: the
    layer failed, or — carried repair **R43.19** — it changed stored nodes in place. A
    generation publishes what a build created; a leaf changed in place would change under
    every reader before the publish, so it is refused, never discarded.
    """
    if isinstance(outcome, Failed):
        return "Failed", outcome.reason
    produced = cast("Sequence[Node]", outcome.value if isinstance(outcome, Produced) else ())
    enriched = layer_enriched(leaves, produced)
    if not enriched:
        return None
    return "LayerEnrichesInPlace", (
        f"'{layer}' changed {len(enriched)} stored node(s) in place, and a corpus-scoped build "
        "publishes only the nodes it creates. Run it per source (drop layer.scope: corpus)."
    )


def _bound_tail(
    tail_runnable: RunnablePipeline, writers: Mapping[str, object], *, stage_ids: frozenset[str]
) -> RunnablePipeline:
    """`tail_runnable`'s stages named in `stage_ids`, each store stage bound to its writer."""
    return replace(
        tail_runnable,
        stages=tuple(
            replace(stage, instance=writers[stage.id]) if stage.id in writers else stage
            for stage in tail_runnable.stages
            if stage.id in stage_ids
        ),
    )


async def _write_corpus_created(
    created: Sequence[Node],
    *,
    runner: Runner,
    tail: RunnablePipeline,
    primary_writer: object,
    layer: str,
    embed_stage_ids: frozenset[str],
    store_stage_ids: frozenset[str],
    first_stage_id: str,
    ctx: Context,
    fail: Callable[[str, str | None, str], Awaitable[None]],
) -> str | None:
    """`created`, checked for a collision and written through `tail` — `_run_corpus_layer`'s
    own last step before publishing, lifted out for its complexity budget. `fail` is called
    before a collision or a `WeftError` propagates, and before a `Failed` tail's reason is
    returned.
    """
    writer_get = _get_of(primary_writer)
    existing_nodes = await writer_get([node.id for node in created]) if writer_get else ()
    collision = _layer_collision(created, existing_nodes, layer=layer)
    if collision is not None:
        await fail(type(collision).__name__, first_stage_id, str(collision))
        raise collision
    try:
        tail_outcome = await _run_corpus_tail(
            runner,
            tail,
            _stamped(created, layer=layer),
            ctx,
            embed_stage_ids=embed_stage_ids,
            store_stage_ids=store_stage_ids,
        )
    except WeftError as exc:
        await fail(type(exc).__name__, exc.stage, str(exc))
        raise
    if isinstance(tail_outcome, Failed):
        await fail("Failed", first_stage_id, tail_outcome.reason)
        return tail_outcome.reason
    return None


async def _run_corpus_layer(
    runnable: RunnablePipeline,
    *,
    runner: Runner,
    layer_runnable: RunnablePipeline,
    tail_runnable: RunnablePipeline,
    store_stage_id: str,
    store_stage_ids: Sequence[str],
    composition: LayerComposition,
    identity: str,
    eligible: Sequence[SourceRef],
    attempts_by_source: Mapping[SourceId, int],
    indexing_ctx: Context,
    resume: bool,
    llm: LLMSection,
) -> str | None:
    """One corpus-scoped layer's whole build, as one generation **per store stage**,
    published whole — ledger task **43.15**, carried repair **R43.11**,
    `_run_one_layer_batch`'s own contract one scope over: `None` once the build published
    (whether or not there was anything to derive), the failure's reason once it failed and
    was recorded. `WeftError`/`LayerNodeCollisionError` always propagate after this build is
    recorded `FAILED` on every eligible source and every generation it opened retracted —
    every store's, not only the one that failed, since a half-written tree in any one of
    them is exactly the state generations exist to hide; `CancelledError` above all is never
    caught here, so an interrupted build leaves its generations `BUILDING`, holding what its
    stages kept, for the next build to adopt (task **43.20**, `_bind_corpus_generations`).

    The stages are offered `LayerCheckpoints` over those generations. When the generation
    holds a kept node the build did not create, the created nodes are written into a fresh
    generation instead, and publishing that one retracts the other.

    `store_stage_id` stays the **primary**'s: leaf reading (`matching`), recall and the
    collision check (`_layer_collision`) read the primary's own bound writer only, on
    `_apply_layer_records`'s own footing — every store holds the same nodes, so a second
    check would only re-confirm the first.
    """
    now = datetime.now(UTC)
    await _apply_layer_records(
        runnable,
        store_stage_id=store_stage_id,
        store_stage_ids=store_stage_ids,
        updates={
            ref.source_id: LayerRecord(
                name=composition.layer,
                pipeline_identity=identity,
                status=LayerStatus.INDEXING,
                attempts=attempts_by_source[ref.source_id],
                at=now,
            )
            for ref in eligible
        },
    )

    tail_store_specs = tuple(spec for spec in composition.tail_specs if spec.contract is NodeStore)
    tail_embed_ids = frozenset(
        spec.id for spec in composition.tail_specs if spec.contract is Embedder
    )
    tail_store_ids = frozenset(spec.id for spec in tail_store_specs)

    generations = await _bind_corpus_generations(
        runnable, layer=composition.layer, tail_store_specs=tail_store_specs, resume=resume
    )

    writer_matching = _matching_of(generations.writers[store_stage_id])
    if writer_matching is None:
        # `require_layers_metadata_filter` already checked the *unbound* primary has one, and
        # `bind_generation` returns `Self`, so a store that reaches here honours the contract.
        raise LayerNeedsMetadataFilterError(
            f"'{composition.layer}' bound a generation whose own handle carries no "
            "MetadataFilter, though the store it was bound from did."
        )

    async def _fail(error_type: str, stage: str | None, message: str) -> None:
        await generations.retract()
        await _fail_layer_batch(
            runnable,
            store_stage_id=store_stage_id,
            store_stage_ids=store_stage_ids,
            layer=composition.layer,
            identity=identity,
            batch_refs=eligible,
            attempts_by_source=attempts_by_source,
            error_type=error_type,
            stage=stage,
            message=message,
        )

    ids = tuple(ref.source_id for ref in eligible)
    leaves = await _paged_leaves(writer_matching, ids)

    checkpoints = _GenerationCheckpoints(
        runner=runner,
        store_tail=_bound_tail(tail_runnable, generations.writers, stage_ids=tail_store_ids),
        matching=writer_matching,
        namespace=_checkpoint_namespace(composition.layer, llm),
        layer=composition.layer,
        ctx=indexing_ctx,
    )
    first_stage_id = composition.layer_specs[0].id
    try:
        outcome = await runner.run_once(
            layer_runnable, leaves, _with_checkpoints(indexing_ctx, checkpoints)
        )
    except WeftError as exc:
        await _fail(type(exc).__name__, exc.stage, str(exc))
        raise
    refusal = _corpus_outcome_refusal(outcome, leaves, layer=composition.layer)
    if refusal is not None:
        error_type, reason = refusal
        await _fail(error_type, first_stage_id, reason)
        return reason

    produced_nodes = cast("Sequence[Node]", outcome.value if isinstance(outcome, Produced) else ())
    created = layer_created(leaves, produced_nodes)
    if await _holds_unpublishable(
        generations, checkpoints, writer_matching, layer=composition.layer, created=created
    ):
        await generations.reopen(composition.layer)

    if created:
        reason = await _write_corpus_created(
            created,
            runner=runner,
            tail=_bound_tail(
                tail_runnable,
                generations.writers,
                stage_ids=frozenset(spec.id for spec in composition.tail_specs),
            ),
            primary_writer=generations.writers[store_stage_id],
            layer=composition.layer,
            embed_stage_ids=tail_embed_ids,
            store_stage_ids=tail_store_ids,
            first_stage_id=first_stage_id,
            ctx=indexing_ctx,
            fail=_fail,
        )
        if reason is not None:
            return reason

    try:
        await _publish_and_supersede_generations(
            generations.holders, generations.opened, layer=composition.layer
        )
    except WeftError as exc:
        await _fail(type(exc).__name__, exc.stage, str(exc))
        raise

    await _apply_layer_records(
        runnable,
        store_stage_id=store_stage_id,
        store_stage_ids=store_stage_ids,
        updates={
            ref.source_id: LayerRecord(
                name=composition.layer,
                pipeline_identity=identity,
                status=LayerStatus.ACTIVE,
                attempts=attempts_by_source[ref.source_id],
                at=datetime.now(UTC),
            )
            for ref in eligible
        },
    )
    return None


def _joinable(
    composition: LayerComposition,
    runnable: RunnablePipeline,
    existing_by_source: Mapping[SourceId, LayerRecord | None],
    *,
    identity: str,
) -> bool:
    """Whether a corpus-scoped layer is stale by addition only, so its incremental stage can join
    the uncovered sources into the published tree — task **43.23**. Every record `ACTIVE` under
    `identity` or absent, at least one `ACTIVE`, and every tail store `GenerationCarrying`. A
    `STALE` record means a source was deleted, which a join cannot remove, so deletion wins.
    """
    if not composition.incremental_specs:
        return False
    records = [existing for existing in existing_by_source.values() if existing is not None]
    if not records or len(records) == len(existing_by_source):
        return False
    if any(
        existing.status is not LayerStatus.ACTIVE or existing.pipeline_identity != identity
        for existing in records
    ):
        return False
    return all(
        isinstance(_stage_instance(runnable, spec.id), GenerationCarrying)
        for spec in composition.tail_specs
        if spec.contract is NodeStore
    )


async def _layer_member_ids(
    matching: Callable[[Filter, Cursor | None], Awaitable[Page[Node]]], *, layer: str
) -> list[NodeId]:
    """Every node stamped `LayerMember(layer=layer)` that `matching` sees, paged to the end."""
    ids: list[NodeId] = []
    cursor: Cursor | None = None
    while True:
        page = await matching(Filter(op=FilterOp.EQ, field=_LAYER_FIELD, value=layer), cursor)
        ids.extend(node.id for node in page.items)
        if page.next_cursor is None:
            return ids
        cursor = page.next_cursor


async def _carry_and_publish(
    generations: _CorpusGenerations, carried: Sequence[NodeId], *, layer: str
) -> None:
    """`carried` into every store's new generation, then each published over the old one."""
    for stage_id, holder in generations.holders.items():
        await cast(GenerationCarrying, holder).carry_forward(
            generations.opened[stage_id].id, carried
        )
    await _publish_and_supersede_generations(generations.holders, generations.opened, layer=layer)


async def _run_corpus_join(
    runnable: RunnablePipeline,
    *,
    runner: Runner,
    tail_runnable: RunnablePipeline,
    store_stage_id: str,
    store_stage_ids: Sequence[str],
    composition: LayerComposition,
    identity: str,
    uncovered: Sequence[SourceRef],
    attempts_by_source: Mapping[SourceId, int],
    indexing_ctx: Context,
    layer_runnables: list[RunnablePipeline],
) -> LayerJoin | str:
    """`composition.incremental_specs` over only `uncovered`'s leaves, into a generation that
    carries every published member of the layer the stage did not replace — task **43.23**.
    The `LayerJoin` once published and `uncovered` recorded `ACTIVE`; the failure's reason once
    recorded `FAILED` on `uncovered`, whose tree stays published. A `WeftError` propagates after
    the same. Nothing is recorded `INDEXING`: an interrupted join is joined again, never adopted
    by a full build's resume, whose generation holds only what it checkpointed.
    """
    tail_store_specs = tuple(spec for spec in composition.tail_specs if spec.contract is NodeStore)
    generations = await _bind_corpus_generations(
        runnable, layer=composition.layer, tail_store_specs=tail_store_specs, resume=False
    )
    primary_writer = generations.writers[store_stage_id]
    writer_matching = _matching_of(primary_writer)
    if writer_matching is None:
        raise LayerNeedsMetadataFilterError(
            f"'{composition.layer}' bound a generation whose own handle carries no "
            "MetadataFilter, though the store it was bound from did."
        )

    async def _fail(error_type: str, stage: str | None, message: str) -> None:
        await generations.retract()
        await _fail_layer_batch(
            runnable,
            store_stage_id=store_stage_id,
            store_stage_ids=store_stage_ids,
            layer=composition.layer,
            identity=identity,
            batch_refs=uncovered,
            attempts_by_source=attempts_by_source,
            error_type=error_type,
            stage=stage,
            message=message,
        )

    published = await _layer_member_ids(writer_matching, layer=composition.layer)
    leaves = await _paged_leaves(writer_matching, tuple(ref.source_id for ref in uncovered))
    revision = _GenerationRevision(composition.layer)
    join_runnable = runner.resolve(composition.incremental_specs, tenant_id=runnable.tenant_id)
    layer_runnables.append(join_runnable)
    first_stage_id = composition.incremental_specs[0].id
    try:
        outcome = await runner.run_once(
            join_runnable, leaves, _with_revision(indexing_ctx, revision, store=primary_writer)
        )
    except WeftError as exc:
        await _fail(type(exc).__name__, exc.stage, str(exc))
        raise
    refusal = _corpus_outcome_refusal(outcome, leaves, layer=composition.layer)
    if refusal is not None:
        await _fail(refusal[0], first_stage_id, refusal[1])
        return refusal[1]

    produced_nodes = cast("Sequence[Node]", outcome.value if isinstance(outcome, Produced) else ())
    created = layer_created(leaves, produced_nodes)
    if created:
        reason = await _write_corpus_created(
            created,
            runner=runner,
            tail=_bound_tail(
                tail_runnable,
                generations.writers,
                stage_ids=frozenset(spec.id for spec in composition.tail_specs),
            ),
            primary_writer=primary_writer,
            layer=composition.layer,
            embed_stage_ids=frozenset(
                spec.id for spec in composition.tail_specs if spec.contract is Embedder
            ),
            store_stage_ids=frozenset(spec.id for spec in tail_store_specs),
            first_stage_id=first_stage_id,
            ctx=indexing_ctx,
            fail=_fail,
        )
        if reason is not None:
            return reason

    carried = [node_id for node_id in published if node_id not in revision.replaced_ids]
    try:
        await _carry_and_publish(generations, carried, layer=composition.layer)
    except WeftError as exc:
        await _fail(type(exc).__name__, exc.stage, str(exc))
        raise

    await _apply_layer_records(
        runnable,
        store_stage_id=store_stage_id,
        store_stage_ids=store_stage_ids,
        updates={
            ref.source_id: LayerRecord(
                name=composition.layer,
                pipeline_identity=identity,
                status=LayerStatus.ACTIVE,
                attempts=attempts_by_source[ref.source_id],
                at=datetime.now(UTC),
            )
            for ref in uncovered
        },
    )
    return LayerJoin(
        layer=composition.layer,
        joined=len(leaves) - revision.unassigned_count,
        unassigned=revision.unassigned_count,
    )


async def _run_corpus_scoped_composition(
    composition: LayerComposition,
    *,
    records: Mapping[SourceId, SourceRecord],
    identity: str,
    refs: Sequence[SourceRef],
    runner: Runner,
    runnable: RunnablePipeline,
    store_stage_id: str,
    store_stage_ids: Sequence[str],
    on_batch: Callable[[BatchProgress], Awaitable[None]] | None,
    indexing_ctx: Context,
    layer_runnables: list[RunnablePipeline],
    layer_loop_started: float,
    llm: LLMSection,
) -> tuple[bool, LayerFailure | None, LayerJoin | None]:
    """One corpus-scoped composition's whole turn in `run_layers`' own loop — lifted out so
    that function's per-composition branching stays under the complexity budget every
    function in this tree already holds to. `(changed, failure, joined)`: whether this layer's
    stored identity moved (`run_layers`' own `layers_changed`), the build's failure, if it
    failed, and the join, when the layer was stale by addition only (task **43.23**,
    `_joinable`) and its incremental stage joined the uncovered sources instead of a rebuild.
    """
    eligible = [
        ref
        for ref in refs
        if (record := records.get(ref.source_id)) is not None
        and record.status is SourceStatus.ACTIVE
    ]
    if not eligible:
        return False, None, None
    build, changed, existing_by_source = _corpus_layer_status(
        eligible, records, layer=composition.layer, identity=identity
    )
    if not build:
        return changed, None, None

    tail_ids = {spec.id for spec in composition.tail_specs}
    tail_runnable = replace(
        runnable, stages=tuple(stage for stage in runnable.stages if stage.id in tail_ids)
    )
    joined: LayerJoin | None = None
    if _joinable(composition, runnable, existing_by_source, identity=identity):
        built = [ref for ref in eligible if existing_by_source[ref.source_id] is None]
        outcome = await _run_corpus_join(
            runnable,
            runner=runner,
            tail_runnable=tail_runnable,
            store_stage_id=store_stage_id,
            store_stage_ids=store_stage_ids,
            composition=composition,
            identity=identity,
            uncovered=built,
            attempts_by_source=_next_layer_attempts(existing_by_source, built),
            indexing_ctx=indexing_ctx,
            layer_runnables=layer_runnables,
        )
        reason = outcome if isinstance(outcome, str) else None
        joined = outcome if isinstance(outcome, LayerJoin) else None
    else:
        built = eligible
        reason = await _run_corpus_layer(
            runnable,
            runner=runner,
            layer_runnable=_resolved_layer(runner, composition, runnable, layer_runnables),
            tail_runnable=tail_runnable,
            store_stage_id=store_stage_id,
            store_stage_ids=store_stage_ids,
            composition=composition,
            identity=identity,
            eligible=eligible,
            attempts_by_source=_next_layer_attempts(existing_by_source, eligible),
            indexing_ctx=indexing_ctx,
            resume=_interrupted(existing_by_source, identity=identity),
            llm=llm,
        )
    if reason is not None:
        failure = LayerFailure(
            layer=composition.layer, failed=len(built), of=len(built), reason=reason
        )
        return changed, failure, None
    await _emit_layer_progress(
        on_batch,
        layer=composition.layer,
        batch_number=1,
        batches=1,
        queryable=len(eligible),
        documents=len(eligible),
        start_time=layer_loop_started,
    )
    return changed, None, joined


def _resolved_layer(
    runner: Runner,
    composition: LayerComposition,
    runnable: RunnablePipeline,
    layer_runnables: list[RunnablePipeline],
) -> RunnablePipeline:
    """`composition.layer_specs` resolved, and appended to `layer_runnables` for closing."""
    layer_runnable = runner.resolve(composition.layer_specs, tenant_id=runnable.tenant_id)
    layer_runnables.append(layer_runnable)
    return layer_runnable


def _interrupted(
    existing_by_source: Mapping[SourceId, LayerRecord | None], *, identity: str
) -> bool:
    """Whether a build under `identity` was interrupted — task **43.20**'s resume signal."""
    return any(
        existing is not None
        and existing.status is LayerStatus.INDEXING
        and existing.pipeline_identity == identity
        for existing in existing_by_source.values()
    )


def _note_corpus_turn(
    failure: LayerFailure | None,
    join: LayerJoin | None,
    layers_failed: list[LayerFailure],
    layers_joined: list[LayerJoin],
) -> None:
    if failure is not None:
        layers_failed.append(failure)
    if join is not None:
        layers_joined.append(join)


async def run_layers(
    compositions: Sequence[LayerComposition],
    *,
    runner: Runner,
    runnable: RunnablePipeline,
    refs: Sequence[SourceRef],
    store_stage_id: str | None,
    store_stage_ids: Sequence[str],
    effective_batch_size: int | None,
    retry_failed: bool,
    on_batch: Callable[[BatchProgress], Awaitable[None]] | None,
    indexing_ctx: Context,
    layer_runnables: list[RunnablePipeline],
    llm: LLMSection,
) -> tuple[tuple[str, ...], tuple[LayerFailure, ...], tuple[LayerJoin, ...]]:
    """Every named layer, in order, after the base run has finished or been skipped under
    `layers_only` — ledger task **43.8**, `weft_cli.ingest.run_index`'s own loop. Returns
    `(layers_changed, layers_failed, layers_joined)`; the second is carried repair **R43.9**,
    the third task **43.23**.

    A layer with a stage whose output depends on batch membership — `raptor`, one tree per
    document — runs one source per call (carried repair **R43.10**); every other layer runs in
    the base's own batches, where batching changes the cost and never the output.

    Eligible sources are this run's own `refs` whose record — re-read from the primary store,
    never `run_index`'s own `previous`/`changes`, both computed before the base wrote anything
    — is `SourceStatus.ACTIVE`; `_layer_eligible`/`_layer_decision` are the table deciding, per
    source, whether this layer runs, is skipped, or is reported as `changed` and left alone. A
    batch is drawn only from the sources that decided `run`: a source already `ACTIVE` or
    `FAILED`-unasked under the identity this run would build costs nothing, not even a store
    round trip beyond the eligibility read. `_run_one_layer_batch` carries every batch's own
    mechanics — this function is the loop over layers and their batches alone.

    Every resolved layer instance this call builds is appended to `layer_runnables`, so
    `run_index`'s own `finally` can close it beside the base's stages — resolved once per
    layer, never once per batch, on `Runner.resolve`'s own process-cache footing.

    `llm` is the run's own `[llm]` section: a corpus build scopes its checkpoint keys by its
    roles (task **43.20**).
    """
    if store_stage_id is None:
        return (), (), ()
    primary = _stage_instance(runnable, store_stage_id)
    get_source = _get_source_of(primary) if primary is not None else None
    get_nodes = _get_of(primary) if primary is not None else None
    matching = _matching_of(primary) if primary is not None else None
    if get_source is None or matching is None:
        return (), (), ()

    layers_changed: list[str] = []
    layers_failed: list[LayerFailure] = []
    layers_joined: list[LayerJoin] = []
    layer_loop_started = time.monotonic()
    for composition in compositions:
        identity = pipeline_identity(composition.resolved)
        records = await _current_records(get_source, refs)

        if composition.scope is LayerScope.CORPUS:
            corpus_changed, corpus_failure, corpus_join = await _run_corpus_scoped_composition(
                composition,
                records=records,
                identity=identity,
                refs=refs,
                runner=runner,
                runnable=runnable,
                store_stage_id=store_stage_id,
                store_stage_ids=store_stage_ids,
                on_batch=on_batch,
                indexing_ctx=indexing_ctx,
                layer_runnables=layer_runnables,
                layer_loop_started=layer_loop_started,
                llm=llm,
            )
            if corpus_changed and composition.layer not in layers_changed:
                layers_changed.append(composition.layer)
            _note_corpus_turn(corpus_failure, corpus_join, layers_failed, layers_joined)
            continue

        eligible, to_run, existing_by_source, queryable, changed = _layer_eligible(
            refs, records, layer=composition.layer, identity=identity, retry_failed=retry_failed
        )
        if changed and composition.layer not in layers_changed:
            layers_changed.append(composition.layer)
        if not eligible or not to_run:
            continue
        documents = len(eligible)

        layer_runnable = runner.resolve(composition.layer_specs, tenant_id=runnable.tenant_id)
        layer_runnables.append(layer_runnable)
        tail_ids = {spec.id for spec in composition.tail_specs}
        tail_runnable = replace(
            runnable, stages=tuple(stage for stage in runnable.stages if stage.id in tail_ids)
        )

        per_source = any(
            getattr(stage.instance, "depends_on_batch_membership", False)
            for stage in layer_runnable.stages
        )
        batches = _sliced(to_run, 1 if per_source else effective_batch_size)
        failed = 0
        first_reason: str | None = None
        for batch_number, batch_refs in enumerate(batches, start=1):
            attempts_by_source = _next_layer_attempts(existing_by_source, batch_refs)
            reason = await _run_one_layer_batch(
                runnable,
                runner=runner,
                layer_runnable=layer_runnable,
                tail_runnable=tail_runnable,
                matching=matching,
                get_nodes=get_nodes,
                store_stage_id=store_stage_id,
                store_stage_ids=store_stage_ids,
                composition=composition,
                identity=identity,
                batch_refs=batch_refs,
                attempts_by_source=attempts_by_source,
                indexing_ctx=indexing_ctx,
            )
            if reason is not None:
                failed += len(batch_refs)
                first_reason = first_reason or reason
                continue
            queryable += len(batch_refs)
            await _emit_layer_progress(
                on_batch,
                layer=composition.layer,
                batch_number=batch_number,
                batches=len(batches),
                queryable=queryable,
                documents=documents,
                start_time=layer_loop_started,
            )
        if first_reason is not None:
            layers_failed.append(
                LayerFailure(
                    layer=composition.layer, failed=failed, of=len(to_run), reason=first_reason
                )
            )

    return tuple(layers_changed), tuple(layers_failed), tuple(layers_joined)


def corpus_scoped_layer_names(
    *,
    registry: Registry,
    reports: Sequence[PackReport],
    contributions: tuple[Contribution, ...],
) -> tuple[str, ...]:
    """Every `installed_layers` name whose own `layer.scope` var reads `corpus` — the
    population `stale_corpus_layers` checks for staleness, independent of whatever `--layers`
    a given run actually named. A layer that fails to resolve, here as in `installed_layers`
    itself, is skipped rather than refused: this is a report, not a run.

    Public (ledger **43.21**) — `weft_cli.commands.DeleteCommand` reads the same population,
    to learn which of the sources it just deleted's own `ACTIVE` layers are corpus-scoped and
    so must be demoted everywhere else. A leading-underscore name reached from another module
    is `reportPrivateUsage` under `pyright --strict`.
    """
    names: list[str] = []
    for name in installed_layers(registry=registry, reports=reports, contributions=contributions):
        try:
            resolved = resolve_named_pipeline(
                name, registry=registry, reports=reports, contributions=contributions
            )
            scope = _layer_scope(resolved, layer=name)
        except WeftError:
            continue
        if scope is LayerScope.CORPUS:
            names.append(name)
    return tuple(names)


async def stale_corpus_layers(
    *,
    runnable: RunnablePipeline,
    store_stage_id: str | None,
    refs: Sequence[SourceRef],
    registry: Registry,
    reports: Sequence[PackReport],
    contributions: tuple[Contribution, ...] = (),
) -> tuple[tuple[str, ...], dict[str, tuple[int, int]], tuple[str, ...]]:
    """`(layers_stale, progress, layers_stale_deleted)` — ledger tasks **43.15** and **43.21**.

    `layers_stale` is every corpus-scoped layer document that is `ACTIVE` on at least one of
    `refs`' own `ACTIVE` sources but not on all of them, sorted by name; `progress[name]` is
    `(built, of)`, the pair `weft_cli.render`'s own stale line prints.

    `layers_stale_deleted` (**43.21**) is every corpus-scoped layer carrying `LayerStatus.
    STALE` on any `ACTIVE` source — `weft delete` demoted it there because a source its tree
    covered was removed — reported separately because `weft_cli.render` prints a different
    sentence for it, one that wins over `layers_stale`'s own: a tree missing a source is a
    different problem from one still catching up to new ones, and a name never appears in
    both.

    Read regardless of what this run itself named under `--layers`: a source indexed without
    naming a corpus-scoped layer still leaves that layer behind everybody else, and an
    operator finds out from the very run that caused it, not only from one that names the
    layer to check.
    """
    if store_stage_id is None:
        return (), {}, ()
    primary = _stage_instance(runnable, store_stage_id)
    get_source = _get_source_of(primary) if primary is not None else None
    if get_source is None:
        return (), {}, ()
    records = await _current_records(get_source, refs)
    active = [record for record in records.values() if record.status is SourceStatus.ACTIVE]
    of = len(active)
    if of == 0:
        return (), {}, ()
    stale: list[str] = []
    progress: dict[str, tuple[int, int]] = {}
    deleted: list[str] = []
    for name in corpus_scoped_layer_names(
        registry=registry, reports=reports, contributions=contributions
    ):
        entries = [entry for record in active for entry in record.layers if entry.name == name]
        if any(entry.status is LayerStatus.STALE for entry in entries):
            deleted.append(name)
            continue
        built = sum(1 for entry in entries if entry.status is LayerStatus.ACTIVE)
        if 0 < built < of:
            stale.append(name)
            progress[name] = (built, of)
    return tuple(sorted(stale)), progress, tuple(sorted(deleted))


__all__ = [
    "LayerComposition",
    "LayerDuplicatesBaseStageError",
    "LayerFailure",
    "LayerIncrementalStageError",
    "LayerJoin",
    "LayerNeedsConsumingStoreError",
    "LayerNeedsGenerationHoldingError",
    "LayerNeedsMetadataFilterError",
    "LayerNodeCollisionError",
    "LayerScope",
    "LayerScopeError",
    "NotALayerError",
    "UnknownLayerError",
    "UnknownLayerVarError",
    "compose_layer",
    "compose_layer_over",
    "compose_layers",
    "corpus_scoped_layer_names",
    "installed_layers",
    "layer_created",
    "layer_enriched",
    "layer_leaf_filter",
    "require_corpus_layers_generation_holding",
    "require_layers_metadata_filter",
    "run_layers",
    "stale_corpus_layers",
]
