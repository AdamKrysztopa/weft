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

import time
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import replace
from datetime import UTC, datetime
from enum import StrEnum
from typing import Final, cast

from pydantic import BaseModel, ConfigDict

from weft_cli.compile import to_specs
from weft_cli.pipeline_catalogue import full_catalogue
from weft_cli.progress import BatchProgress
from weft_cli.route_ask import resolve_named_pipeline
from weft_embed import Embedder
from weft_enhance import Enhancer
from weft_extract import Extractor
from weft_extract.text import SourceRef
from weft_index import Expander, Revisable
from weft_index.payload import Representation
from weft_kernel.context import Context
from weft_kernel.discovery import PackReport
from weft_kernel.errors import UnresolvedNameError, WeftError
from weft_kernel.payload import Failed, Node, NodeId, Produced, SourceId
from weft_kernel.registry import Registry
from weft_kernel.resolution import Contribution, ResolvedPipeline, pipeline_identity
from weft_kernel.runner import PipelineResolutionError, RunnablePipeline, Runner, StageSpec
from weft_store import NodeStore
from weft_store.contract import (
    Cursor,
    Filter,
    FilterOp,
    LayerRecord,
    LayerStatus,
    Page,
    SourceFailure,
    SourceRecord,
    SourceStatus,
)

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


class LayerNeedsMetadataFilterError(WeftError):
    """A layer was named against a store that cannot select stored nodes by metadata —
    task **43.8**.

    A layer's selection is `layer_leaf_filter`, evaluated through `weft_store.contract.
    MetadataFilter.matching`. A store that does not implement it has no way to read the
    leaves a layer enriches, so this is refused before the base runs at all — no extract,
    no write, nothing to undo.
    """


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
    layer_specs = to_specs(resolved_layer, registry=registry, reports=reports)

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


def layer_leaf_filter(sources: Sequence[SourceId]) -> Filter:
    """The selection a layer's own batch reads its leaves through — ledger task **43.8**.

    `IN lineage.sources` narrows to this batch's own sources, and `NOT(EXISTS
    ext.weft-index.technique)` leaves out every node an `Expander` already derived, so a layer
    never re-enriches another layer's output. The graph pack's fact and mention nodes join this
    filter with the first graph layer (`43.15`): fitness function 28 keeps its name out of here.
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
) -> bool:
    """One layer batch's whole mechanics, lifted out of `run_layers` so that function's own
    complexity stays under the budget every function in this tree already holds to — ledger
    task **43.8**. `True` once every source in `batch_refs` is `ACTIVE` (whether or not there
    was anything to derive); `False` once every one is `FAILED` and the loop above should move
    on to the next batch. `WeftError`/`LayerNodeCollisionError` always propagate instead of
    returning, after this batch is recorded `FAILED` the same way `_fail_layer_batch` always
    records one.
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
        return True

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
        return False

    produced_nodes = cast("Sequence[Node]", outcome.value if isinstance(outcome, Produced) else ())
    created = layer_created(leaves, produced_nodes)
    if created:
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
            tail_outcome = await runner.run_once(tail_runnable, created, indexing_ctx)
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
            return False

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
    return True


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
) -> tuple[str, ...]:
    """Every named layer, in order, after the base run has finished or been skipped under
    `layers_only` — ledger task **43.8**, `weft_cli.ingest.run_index`'s own loop.

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
    """
    if store_stage_id is None:
        return ()
    primary = _stage_instance(runnable, store_stage_id)
    get_source = _get_source_of(primary) if primary is not None else None
    get_nodes = _get_of(primary) if primary is not None else None
    matching = getattr(primary, "matching", None) if primary is not None else None
    if get_source is None or matching is None:
        return ()

    layers_changed: list[str] = []
    layer_loop_started = time.monotonic()
    for composition in compositions:
        identity = pipeline_identity(composition.resolved)
        records = await _current_records(get_source, refs)
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

        batches = _sliced(to_run, effective_batch_size)
        for batch_number, batch_refs in enumerate(batches, start=1):
            attempts_by_source = _next_layer_attempts(existing_by_source, batch_refs)
            succeeded = await _run_one_layer_batch(
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
            if not succeeded:
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

    return tuple(layers_changed)


__all__ = [
    "LAYER_STAGE_CONTRACTS",
    "LayerComposition",
    "LayerDuplicatesBaseStageError",
    "LayerNeedsMetadataFilterError",
    "LayerNodeCollisionError",
    "NotALayerError",
    "UnknownLayerError",
    "compose_layer",
    "compose_layer_over",
    "compose_layers",
    "installed_layers",
    "layer_created",
    "layer_leaf_filter",
    "require_layers_metadata_filter",
    "run_layers",
]
