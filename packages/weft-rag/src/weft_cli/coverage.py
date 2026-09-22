"""How much of the corpus `weft ask` could see, from one `list_sources()` read — task **43.4**.

The denominator is what the store has recorded, never the directory: a file no run has reached is
unknown here as it is to `weft sources list`. `indexing` covers a run in flight and one that died
after writing `INDEXING`, which the store cannot tell apart. `DELETING` counts nowhere.
"""

from __future__ import annotations

from collections.abc import Iterable

from pydantic import BaseModel, ConfigDict, Field

from weft_store import SourceRecord, SourceStatus


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
        return self.failed == 0 and self.indexing == 0


def coverage_of(records: Iterable[SourceRecord]) -> SourceCoverage:
    """One `SourceCoverage` from every recorded `SourceRecord` — `ACTIVE` counts as indexed,
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


__all__: list[str] = ["SourceCoverage", "coverage_of"]
