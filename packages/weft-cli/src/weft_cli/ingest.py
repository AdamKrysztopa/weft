"""`run_index` — `weft index <path>`, composed from the same four built-ins step 8's test exercises.

`docs/06-phase-0-build.md` step 9: "the product runs end to end." The pipeline
below — extract, chunk, embed, store — is the exact `StageSpec` list
`tests/integration/test_ingest_pipeline.py` already proves works; this module
is that same composition, wired to a real directory and a real, discovered
registry instead of a hand-built test one. **Phase 0 builds no pipeline-as-
data** (`docs/06-phase-0-build.md`'s second G2 trap): the chunk name below is
a constant this module states, not configuration a caller supplies.

**Three of the four stages are chosen at run time, each for its own reason.**
Extraction, below, because a pack that claims a format has to be reachable
without editing this file. Embedding, from `[services] embed`, because which
embedder ran decides what a stored vector *means*. Storage, from
`[services] store`, because which store a run uses decides *where the corpus
is* — and because task 2.6 shipped a second registered `NodeStore` that a
constant here made unreachable, which is `.phase2-findings.md` finding 9's
test failed at the last inch. See `weft_cli.services`, which holds both
arguments in full rather than repeating them here.

**The extract stage was the first exception, and it is a repair.** It used to be
pinned to `"text"`, and discovery filtered on `weft-extract`'s own
`EXTENSIONS`. Both were correct while one extractor pack existed and became
silently wrong the moment `weft-pdf` shipped: `weft index corpus/mrmr` walked
nine PDFs, matched none of them, handed an empty batch to a text extractor and
exited 0 reporting success — a run whose failure looked exactly like a run
with nothing to do. Under the lens's own test, a stranger shipping
`weft-extract-epub` had to edit two files that were not theirs to become
reachable, and zero is the only passing answer (`01` requirement 1).

So the accept set is derived: `weft_extract.accept.claimed_extensions` reads
the `extensions` every registered `Extractor` declares, and the extractor for
this run is the one those claims name. **Where the claims name more than one,
this module refuses instead of choosing** — task 2.28 is what composes two
backends for one media type into a chain, and an ordering invented here would
be that task decided by accident. `--extract` is how an operator names one
until then, and the refusal says so.

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

from collections.abc import AsyncIterator, Awaitable, Callable, Collection, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from weft_chunk import Chunker
from weft_cli.services import DEFAULT_EMBEDDER, DEFAULT_STORE
from weft_embed import Embedder
from weft_extract import (
    Extractor,
    claimed_extensions,
    discover_source_docs,
    present_suffixes,
)
from weft_kernel.context import Context
from weft_kernel.errors import UnresolvedNameError
from weft_kernel.registry import Registry
from weft_kernel.runner import (
    PipelineResolutionError,
    RunnablePipeline,
    Runner,
    RunSummary,
    StageSpec,
)
from weft_store import NodeStore

#: Chunking: fixed, explicit, and stated once. See the module docstring for why extraction
#: is chosen at run time, and `weft_cli.services` for why embedding and storage are.
_CHUNK_SPEC = StageSpec(id="chunk", contract=Chunker, name="fixed-size")

#: The distributions `index_specs` names *itself*, in the order a caller should check them —
#: `weft_cli.registry_bootstrap.require_active`'s input. `weft-store` is deliberately not
#: among them any more: the store is named by `[services] store`, so the distribution that
#: provides it is whichever one registered that name, and a hard-coded tuple can never
#: contain a stranger's pack. `weft_cli.cli` covers it with `require_plugin`, exactly as it
#: already covers `--extract` and `[services] embed`.
INDEX_DISTRIBUTIONS: tuple[str, ...] = ("weft-extract", "weft-chunk", "weft-embed")


class AmbiguousExtractorError(PipelineResolutionError, UnresolvedNameError):
    """More than one registered `Extractor` claims what is in this directory.

    Not a defect and not a rare edge: `weft-pdf` registers `pdf-text` and
    `pdf-layout` for `.pdf` deliberately, because they fail differently. This
    module will not pick between them — the message names every candidate and
    the option that selects one, which is `01` requirement 5's rule applied to
    a choice rather than to a typo.

    Fitness function 12's family: `valid_options` is every candidate extractor
    name — the choice this module refuses to make on the caller's behalf.
    """

    def __init__(
        self,
        message: str,
        *,
        valid_options: tuple[str, ...],
        stages: tuple[str, ...] = (),
        distributions: tuple[str, ...] = (),
        remedy: str = "",
    ) -> None:
        PipelineResolutionError.__init__(
            self, message, stages=stages, distributions=distributions, remedy=remedy
        )
        self.valid_options = valid_options


class UnclaimedFormatError(PipelineResolutionError, UnresolvedNameError):
    """A directory holds files, and no installed `Extractor` claims any of their formats.

    The alternative is the silent, successful no-op this module's own repair
    is about: reporting "produced 0" for a directory of `.docx` tells an
    operator nothing, while naming the suffixes found and the suffixes
    installed tells them exactly which pack to install.

    Fitness function 12's family: `valid_options` is every format some
    installed extractor does claim — empty when nothing claims anything at
    all, which is a fact, not an omission.
    """

    def __init__(
        self,
        message: str,
        *,
        valid_options: tuple[str, ...],
        stages: tuple[str, ...] = (),
        remedy: str = "",
    ) -> None:
        PipelineResolutionError.__init__(self, message, stages=stages, remedy=remedy)
        self.valid_options = valid_options


def index_specs(
    extractor: str, *, embedder: str = DEFAULT_EMBEDDER, store: str = DEFAULT_STORE
) -> tuple[StageSpec, ...]:
    """The four-stage ingest pipeline, with three of the four names given by the caller.

    `embedder` comes from `[services] embed` and `store` from `[services] store`
    — `weft_cli.services`, which holds the whole argument for why those two are
    configuration rather than constants, and why their defaults are the offline
    deterministic embedder and the backend `01` makes the floor.
    """
    return (
        StageSpec(id="extract", contract=Extractor, name=extractor),
        _CHUNK_SPEC,
        StageSpec(id="embed", contract=Embedder, name=embedder),
        StageSpec(id="store", contract=NodeStore, name=store),
    )


@dataclass(frozen=True, slots=True, kw_only=True)
class IndexResult:
    """`run_index`'s return: the run-level summary, plus the store's own count if it has one.

    `stored_count` is `None` when the resolved `"store"` stage has no
    callable `count` — `NodeStore.count` is part of the published contract
    every store implements, so this is `None` only defensively, the same
    spirit as `aclose` below: a fact this module reads if present, never a
    method it requires beyond what the contract already does. It is also
    `None` when nothing was found to index, because no store was ever built.
    """

    summary: RunSummary
    stored_count: int | None


async def run_index(
    directory: Path,
    *,
    registry: Registry,
    ctx: Context,
    extractor: str | None = None,
    embedder: str = DEFAULT_EMBEDDER,
    store: str = DEFAULT_STORE,
) -> IndexResult:
    """Extract, chunk, embed and store every file under `directory` an extractor claims.

    `extractor`, when given, is both the plugin that runs and the narrowing of
    what is discovered: naming `pdf-text` over a directory of Markdown and PDFs
    indexes the PDFs, rather than handing a text extractor bytes it will refuse.

    `embedder` is `[services] embed`'s answer, defaulting to the deterministic
    one. An unregistered name is `Runner.resolve`'s own `UnknownPluginError`,
    naming what was wanted and every embedder installed — never a quiet
    substitution, because an index built with a different embedder from the
    one an operator named does not fail, it answers plausibly.

    `store` is `[services] store`'s answer, and it reaches the pipeline the same
    way for the same reason: writing a corpus into a store the operator did not
    name is a run that succeeds and leaves the index somewhere else.

    An empty directory is not an error and does not resolve a pipeline at all:
    there is nothing whose format needs an extractor, so there is nothing to
    choose, and opening a database connection to report "nothing to index"
    would be work done to say nothing happened.
    """
    claims = claimed_extensions(registry)
    accepted = _accepted_extensions(claims, registry=registry, extractor=extractor)
    present = present_suffixes(directory)
    readable = present & accepted
    docs = discover_source_docs(directory, extensions=readable)
    if not docs:
        return IndexResult(
            summary=_nothing_found(directory, present=present, accepted=accepted),
            stored_count=None,
        )

    name = (
        extractor
        if extractor is not None
        else _sole_claimant(readable, claims=claims, registry=registry)
    )
    runner = Runner(registry)
    pipeline = runner.resolve(
        index_specs(name, embedder=embedder, store=store), tenant_id=ctx.tenant_id
    )

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


def _accepted_extensions(
    claims: Mapping[str, tuple[str, ...]], *, registry: Registry, extractor: str | None
) -> frozenset[str]:
    """What to discover: one named extractor's claims, or the union of everyone's.

    A named extractor is validated through `Registry.entry`, whose
    `UnknownPluginError` already names what was wanted and lists every
    registered alternative — there is no second, worse version of that message
    written here.
    """
    if extractor is None:
        if not claims:
            registered = ", ".join(sorted(registry.names_for(Extractor))) or "none"
            remedy = (
                "Install an extractor pack, or check `weft plugins doctor` for one that "
                "registered but failed."
            )
            raise UnclaimedFormatError(
                "no installed extractor claims any file format, so nothing under this "
                f"directory can be read. Extractors registered: {registered}. {remedy}",
                valid_options=(),
                stages=("extract",),
                remedy=remedy,
            )
        return frozenset(claims)

    registry.entry(Extractor, extractor)  # raises UnknownPluginError, listing the options
    return frozenset(suffix for suffix, claimants in claims.items() if extractor in claimants)


def _sole_claimant(
    readable: Collection[str], *, claims: Mapping[str, tuple[str, ...]], registry: Registry
) -> str:
    """The one extractor claiming every suffix actually present, or a refusal naming them all.

    Scoped to `readable` rather than to every claim in the registry: a
    directory of Markdown must not become ambiguous because a PDF pack happens
    to be installed. Ambiguity here means the files in *this* directory are
    genuinely claimed by more than one plugin.
    """
    candidates = sorted({name for suffix in readable for name in claims[suffix]})
    if len(candidates) == 1:
        return candidates[0]
    # The remedy is in the message as well as on the field: `weft_cli.cli` prints
    # `str(exc)` and nothing else, so a remedy that lived only on the attribute would be
    # invisible to the one person who needs it. Every sibling in this family does the same.
    remedy = (
        "Name one with `--extract <name>`. The kernel walks a stage's `fallback:` chain "
        "(ledger task 2.28), but no route from a pipeline document to this command's stages "
        "exists, so `weft index` cannot compose several. Ledger tasks 2.4 and 2.8 built that "
        "bridge for a different command (`weft route`); no task currently owns it for `weft "
        "index`."
    )
    raise AmbiguousExtractorError(
        f"{len(candidates)} extractors could read this directory "
        f"({', '.join(candidates)}, claiming {', '.join(sorted(readable))}), and this "
        "command will not choose between them — they are registered separately because "
        f"they read differently. {remedy}",
        valid_options=tuple(candidates),
        stages=("extract",),
        distributions=tuple(
            sorted({registry.entry(Extractor, name).distribution for name in candidates})
        ),
        remedy=remedy,
    )


def _nothing_found(
    directory: Path, *, present: Collection[str], accepted: Collection[str]
) -> RunSummary:
    """`NothingToProduce` for an empty walk — or a refusal, if the files were simply unreadable.

    The distinction is the whole point: a directory with no files in it has
    nothing to index and that is a fact, while a directory full of `.docx` has
    something to index and no installed pack that can.
    """
    unclaimed = frozenset(present) - frozenset(accepted)
    if unclaimed:
        options = tuple(sorted(accepted))
        remedy = "Install a pack that claims one of the formats found."
        raise UnclaimedFormatError(
            f"nothing under '{directory}' can be read: found {', '.join(sorted(unclaimed))}, "
            f"and the installed extractors claim {', '.join(options)}. {remedy}",
            valid_options=options,
            stages=("extract",),
            remedy=remedy,
        )
    return RunSummary(
        nothing_to_produce=1,
        nothing_to_produce_reasons=(f"no files under '{directory}' to index",),
    )


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
