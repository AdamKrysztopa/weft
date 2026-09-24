"""Let `weft ask` warn when its answer came from only part of the corpus.

How much of the corpus `weft ask` could see, from one `list_sources()` read — task **43.4**,
widened at **43.9** to answer per-layer coverage from the identical read.

The denominator is what the store has recorded, never the directory: a file no run has reached is
unknown here as it is to `weft sources list`. `indexing` covers a run in flight and one that died
after writing `INDEXING`, which the store cannot tell apart. `DELETING` counts nowhere.
"""

from __future__ import annotations

from collections.abc import Iterable

from pydantic import BaseModel, ConfigDict, Field

from weft_store import LayerStatus, SourceRecord, SourceStatus


class SourceCoverage(BaseModel):
    """`indexed`/`failed`/`indexing` sources, counted from one `list_sources()` read.

    `complete` is `True` only when nothing failed and nothing is still indexing — the one
    condition under which `weft ask` says nothing at all about coverage, so a corpus with no
    outstanding work renders byte-identical to a build before this task.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    indexed: int = Field(ge=0)
    failed: int = Field(ge=0)
    indexing: int = Field(ge=0)

    @property
    def complete(self) -> bool:
        """Whether every recorded source is indexed, with none failed or in flight."""
        return self.failed == 0 and self.indexing == 0


def coverage_of(records: Iterable[SourceRecord]) -> SourceCoverage:
    """Summarise every recorded `SourceRecord` as one `SourceCoverage`.

    One `SourceCoverage` from every recorded `SourceRecord` — `ACTIVE` counts as indexed,
    `FAILED` as failed, `INDEXING` as indexing, `DELETING` counts nowhere (see the module
    docstring for why).
    """
    indexed = failed = indexing = 0
    for record in records:
        if record.status is SourceStatus.ACTIVE:
            indexed += 1
        elif record.status is SourceStatus.FAILED:
            failed += 1
        elif record.status is SourceStatus.INDEXING:
            indexing += 1
    return SourceCoverage(indexed=indexed, failed=failed, indexing=indexing)


class LayerCoverage(BaseModel):
    """How far one derived layer has reached across the corpus — ledger task **43.9**.

    `of` is every `ACTIVE` source, the same denominator `SourceCoverage` counts against; a
    source that has never even attempted `name` carries no `LayerRecord` for it at all and is
    still counted against `of`, since a layer that has not reached a source is exactly the gap
    this model exists to state. `built` counts only a `LayerStatus.ACTIVE` record — `INDEXING`
    and `FAILED` are both "not yet answerable from", on `SourceCoverage`'s own `complete`
    reasoning one layer down.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    built: int = Field(ge=0)
    of: int = Field(ge=0)


def layer_coverage_of(records: Iterable[SourceRecord]) -> tuple[LayerCoverage, ...]:
    """One `LayerCoverage` per layer name appearing on any `ACTIVE` source, sorted by name.

    `of` is the count of `ACTIVE` records — computed once, up front, so a layer named on
    every one of them and a layer named on none both compare against the identical
    denominator. A record whose own status is not `ACTIVE` contributes no layer at all: a
    `FAILED` or `INDEXING` *source* has nothing derived worth counting either way.
    """
    active = tuple(record for record in records if record.status is SourceStatus.ACTIVE)
    of = len(active)
    built: dict[str, int] = {}
    for record in active:
        for layer in record.layers:
            built.setdefault(layer.name, 0)
            if layer.status is LayerStatus.ACTIVE:
                built[layer.name] += 1
    return tuple(LayerCoverage(name=name, built=built[name], of=of) for name in sorted(built))


def ready_layers(layers: Iterable[LayerCoverage]) -> frozenset[str]:
    """Collect every layer name built on every indexed source.

    Every layer name built on every indexed source — `weft_retrieve.engine.route_catalogue`'s
    own `ready_layers` argument, and `weft_cli.commands.PendingLayerError`'s own gate.
    """
    return frozenset(layer.name for layer in layers if layer.of > 0 and layer.built == layer.of)


__all__: list[str] = [
    "LayerCoverage",
    "SourceCoverage",
    "coverage_of",
    "layer_coverage_of",
    "ready_layers",
]
