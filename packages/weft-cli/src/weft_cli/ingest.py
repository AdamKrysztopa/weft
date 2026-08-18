"""`run_index` — `weft index <path>`, composed from the same four built-ins step 8's test exercises.

`docs/06-phase-0-build.md` step 9: "the product runs end to end." The pipeline
below — extract, chunk, embed, store — is the exact `StageSpec` list
`tests/integration/test_ingest_pipeline.py` already proves works; this module
is that same composition, wired to a real directory and a real, discovered
registry instead of a hand-built test one. **Phase 0 builds no pipeline-as-
data** (`docs/06-phase-0-build.md`'s second G2 trap): the four stage names
below are a constant this module states, not configuration a caller supplies
— Phase 1 is what makes this list something a pipeline file can override.

One batch: every `SourceDoc` `discover_source_docs` finds is handed to
`Runner.run` as the single element of its batch iterator, exactly as the step
8 integration test does — `docs/01-high-level-plan.md` → *Colour*: "the
runner keeps one batch in flight per pipeline run."

**Cleanup, defensively.** `weft_kernel.runner.RunnablePipeline.stages` is
public, and `PgVectorStore.aclose` is not part of any contract `NodeStore`
publishes — a store may or may not have a connection worth closing. This
module treats `aclose` exactly the way `weft_kernel.runner`'s own
`_flush_of` treats `flush`: read defensively off the resolved instance,
called if present and callable, ignored otherwise. Not a second `flush` —
`Runner.run` already called that — only the one thing this store type adds
that no contract requires and no third-party store need provide.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from weft_chunk import Chunker
from weft_embed import Embedder
from weft_extract import Extractor, discover_source_docs
from weft_kernel.context import Context
from weft_kernel.registry import Registry
from weft_kernel.runner import RunnablePipeline, Runner, RunSummary, StageSpec
from weft_store import NodeStore

#: The fixed, explicit pipeline `docs/06-phase-0-build.md` step 9 ships — see the module
#: docstring for why this is a constant and not configuration.
INDEX_SPECS: tuple[StageSpec, ...] = (
    StageSpec(id="extract", contract=Extractor, name="text"),
    StageSpec(id="chunk", contract=Chunker, name="fixed-size"),
    StageSpec(id="embed", contract=Embedder, name="hash"),
    StageSpec(id="store", contract=NodeStore, name="pgvector"),
)

#: The distributions `INDEX_SPECS` names, in the order a caller should check them —
#: `weft_cli.registry_bootstrap.require_active`'s input.
INDEX_DISTRIBUTIONS: tuple[str, ...] = ("weft-extract", "weft-chunk", "weft-embed", "weft-store")


@dataclass(frozen=True, slots=True, kw_only=True)
class IndexResult:
    """`run_index`'s return: the run-level summary, plus the store's own count if it has one.

    `stored_count` is `None` when the resolved `"store"` stage has no
    callable `count` — `NodeStore.count` is part of the published contract
    every store implements, so this is `None` only defensively, the same
    spirit as `aclose` below: a fact this module reads if present, never a
    method it requires beyond what the contract already does.
    """

    summary: RunSummary
    stored_count: int | None


async def run_index(directory: Path, *, registry: Registry, ctx: Context) -> IndexResult:
    """Extract, chunk, embed and store every `.txt`/`.md` file under `directory`.

    An empty directory is not an error: `discover_source_docs` finds nothing,
    the one batch handed to `Runner.run` is an empty tuple, and
    `weft_extract.TextExtractor.run` answers `NothingToProduce` for it — the
    returned `RunSummary` reports that honestly rather than this function
    special-casing "nothing to index" as a distinct outcome.
    """
    docs = discover_source_docs(directory)
    runner = Runner(registry)
    pipeline = runner.resolve(INDEX_SPECS, tenant_id=ctx.tenant_id)

    async def batches() -> AsyncIterator[object]:
        yield docs

    try:
        summary = await runner.run(pipeline, batches(), ctx)
        return IndexResult(summary=summary, stored_count=await _stored_count(pipeline))
    finally:
        for stage in pipeline.stages:
            aclose = _aclose_of(stage.instance)
            if aclose is not None:
                await aclose()


async def _stored_count(pipeline: RunnablePipeline) -> int | None:
    for stage in pipeline.stages:
        if stage.id != "store":
            continue
        count = _count_of(stage.instance)
        if count is not None:
            return await count()
    return None


def _aclose_of(instance: object) -> Callable[[], Awaitable[None]] | None:
    """`instance.aclose`, if it has one and it is callable — the module docstring's *"Cleanup,
    defensively"* note, in code.
    """
    found = getattr(instance, "aclose", None)
    if found is None or not callable(found):
        return None
    return cast(Callable[[], Awaitable[None]], found)


def _count_of(instance: object) -> Callable[[], Awaitable[int]] | None:
    """`instance.count`, if it has one and it is callable — see `IndexResult`'s docstring."""
    found = getattr(instance, "count", None)
    if found is None or not callable(found):
        return None
    return cast(Callable[[], Awaitable[int]], found)
