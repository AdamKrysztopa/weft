"""`run_index` — `weft index <path>`, composed from the same four built-ins step 8's test exercises.

`docs/06-phase-0-build.md` step 9: "the product runs end to end." The pipeline
below — extract, chunk, embed, store — is the exact `StageSpec` list
`tests/integration/test_ingest_pipeline.py` already proves works; this module
is that same composition, wired to a real directory and a real, discovered
registry instead of a hand-built test one. **Phase 0 builds no pipeline-as-
data** (`docs/06-phase-0-build.md`'s second G2 trap): the chunk name below is
a constant this module states, not configuration a caller supplies.

**Task 4.0 — `--pipeline` closes the gap ledger task 2.29 recorded and no task
owned.** `[services] embed`/`[services] store` name a *plugin*, never a
configuration — `weft_cli.services`'s own docstring — so `OpenAIEmbedderConfig
.model`/`dimensions`/`batch_size` and every other plugin's own `with:` block
stayed unreachable from a file for this command, the one gap 2.8 left open
when it wired `weft_cli.compile` into `weft ask` and not here. `run_index`'s
`pipeline` parameter is that wiring: given a name, it resolves a document from
`weft_cli.pipeline_catalogue.full_catalogue` — project-local and pack-
contributed alike, the identical set `weft pipeline show`/`weft ask --pipeline`
already resolve names against — through `weft_cli.compile.contracts_for`/
`to_specs`, exactly as `weft_cli.route_ask.run_named_ask` already does for a
query pipeline. Nothing new is designed here; the bridge already existed.

**Q3, settled: `[services]` and a document's `with:` stay two surfaces, never
merged.** `[services]` continues to be the *whole* answer for the default,
no-`--pipeline` path below — a plugin name and nothing else, exactly as
before — and a stage's own configuration is reached the other way this tree
already has: name a document. Inventing a `{ use = …, with = … }` shape
inside `[services]` was the exact second grammar 2.29's own note warned
against; it is not built. When `--pipeline` is given, the document's own
`use:`/`with:` on every stage decides what runs, and `[services] embed`/
`[services] store` are not read for that run at all — there is no config to
merge them with, since a document names its own plugin per stage already.
This is the identical split `weft ask` already carries between `--retrieve-
only` (Phase 0's `[services]`-only contract) and `--pipeline`/the router (a
document's own `with:`), just applied to the one command that had not
received it yet.

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
until then, and the refusal says so. **`--pipeline` is exempt from this
narrowing on purpose**: a document's own `extract` stage already names one
concrete plugin, the identical decision `--extract` makes by hand, so the
accepted-extension set for that run is derived from that one plugin's own
claims — never from the union across everything installed.

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

**`_store_stage_id_of` finds the store by *contract*, not by the stage id `"store"`.** The
four-stage default path still uses that literal id, but a `--pipeline` document owes this
module no naming convention at all — 2.4's own rule, that a document names a plugin and
the registry is what says which contract answers for it — so which stage's id
`_stored_count` reads back is derived from `StageSpec.contract`, at the same point
`_extractor_name_of` derives the extractor's name, rather than a live `isinstance` check on
a *constructed* instance: several of this module's own test doubles satisfy `Extractor`/
`Embedder` structurally without satisfying every method `NodeStore`'s wider Protocol
declares, so an `isinstance` check against the running instance would silently under-count
a real store too, which `01` requirement 5 rules out as firmly as a missing entry does.
"""

from __future__ import annotations

import hashlib
from collections.abc import AsyncIterator, Awaitable, Callable, Collection, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, cast

from weft_chunk import Chunker
from weft_cli.compile import contracts_for, to_specs
from weft_cli.pipeline_catalogue import UnknownPipelineNameError, full_catalogue
from weft_cli.services import DEFAULT_EMBEDDER, DEFAULT_STORE
from weft_embed import Embedder
from weft_extract import (
    Extractor,
    SourceDoc,
    claimed_extensions,
    discover_source_docs,
    present_suffixes,
)
from weft_kernel.context import Context
from weft_kernel.discovery import PackReport
from weft_kernel.errors import UnresolvedNameError, WeftError
from weft_kernel.registry import Registry
from weft_kernel.resolution import Contribution, ResolvedPipeline, resolve
from weft_kernel.runner import (
    PipelineResolutionError,
    RunnablePipeline,
    Runner,
    RunSummary,
    StageSpec,
)
from weft_store import NodeStore
from weft_store.contract import SourceRecord

#: What `SourceRecord.pipeline` records for the built-in four-stage path — `06` step 9's
#: hardcoded pipeline, which resolves no `ResolvedPipeline` and so has no name to read.
#: `02` §1 wants this field to let `weft index` say "already indexed, by a different
#: pipeline", and a field meaning "which pipeline" cannot be empty on the path most corpora
#: are indexed by.
BUILT_IN_PIPELINE_NAME: Final[str] = "built-in"

#: Chunking: fixed, explicit, and stated once. See the module docstring for why extraction
#: is chosen at run time, and `weft_cli.services` for why embedding and storage are.
_CHUNK_SPEC = StageSpec(id="chunk", contract=Chunker, name="fixed-size")

#: The distributions `index_specs` names *itself*, in the order a caller should check them —
#: `weft_cli.registry_bootstrap.require_active`'s input. `weft-store` is deliberately not
#: among them any more: the store is named by `[services] store`, so the distribution that
#: provides it is whichever one registered that name, and a hard-coded tuple can never
#: contain a stranger's pack. `weft_cli.cli` covers it with `require_plugin`, exactly as it
#: already covers `--extract` and `[services] embed`.
#:
#: Read only for the default, no-`--pipeline` path: a named document may depend on none of
#: these three (a third party's own extractor and embedder pack, say), so `IndexCommand`
#: does not consult this tuple at all once `--pipeline` is given — see that class.
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


class PipelineMissingExtractStageError(PipelineResolutionError, UnresolvedNameError):
    """`--pipeline` named a document with no stage registered under the `Extractor` contract.

    `weft index` has to know what format to look for on disk before anything can run — the
    same fact `_accepted_extensions` derives for the default four-stage path from the
    plugin `--extract` names or from every claim the registry holds. A document naming no
    `Extractor` stage has nothing for this command to derive that from, so this is refused
    rather than treated as "index nothing": an empty directory is a fact about the
    filesystem (see the module docstring's *"An empty directory..."* clause on `run_index`),
    while a document that cannot possibly index anything is a fact about the document.

    Fitness function 12's family: `valid_options` is every stage id the document does
    resolve, so an operator who meant a different id sees the ones that exist.
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

    `stored_count` is `None` when the resolved store stage has no callable
    `count` — `NodeStore.count` is part of the published contract every store
    implements, so this is `None` only defensively, the same spirit as
    `aclose` below: a fact this module reads if present, never a method it
    requires beyond what the contract already does. It is also `None` when
    nothing was found to index, because no store was ever built.

    **`resolved_pipeline`/`document_ids`, task 4.4/4.6.** A run record needs a resolved
    pipeline to persist and the corpus it measured — both facts this function already computes
    for the `pipeline=` path and previously discarded. `resolved_pipeline` is `None` on the
    default four-stage path, honestly: that path builds its `StageSpec`s as constants and never
    calls `weft_kernel.resolution.resolve`, so there is no `ResolvedPipeline` to hand back —
    exactly the gap task 4.0's own module docstring names as the reason it exists at all.
    `document_ids` is every `SourceDoc.source_id` this run actually discovered on disk — `()`
    when nothing was found — the same identity `weft_eval.run_record.corpus_identity` digests,
    so a caller building a run record never re-walks the directory a second time to get it.
    """

    summary: RunSummary
    stored_count: int | None
    resolved_pipeline: ResolvedPipeline | None = None
    document_ids: tuple[str, ...] = ()


async def run_index(
    directory: Path,
    *,
    registry: Registry,
    ctx: Context,
    extractor: str | None = None,
    embedder: str = DEFAULT_EMBEDDER,
    store: str = DEFAULT_STORE,
    pipeline: str | None = None,
    reports: Sequence[PackReport] = (),
    contributions: tuple[Contribution, ...] = (),
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

    `pipeline`, task **4.0**, names a document instead: every stage's plugin and
    its own `with:` configuration come from `weft_cli.pipeline_catalogue.
    full_catalogue` (`reports` is that lookup's own input — every installed
    pack's contribution, alongside a project-local `pipelines/` directory).
    `extractor`/`embedder`/`store` are not read for that run — see the module
    docstring's *"Q3, settled"* — and giving both `pipeline` and `extractor`
    together is refused outright rather than one silently winning. Raises
    `weft_cli.pipeline_catalogue.UnknownPipelineNameError` for a name the
    catalogue does not hold and `PipelineMissingExtractStageError` for a
    document with no stage under the `Extractor` contract; every
    `weft_kernel.runner.PipelineResolutionError` a malformed document or an
    unregistered plugin raises propagates unchanged, the same set
    `weft_cli.route_ask.run_named_ask` already documents for its own resolution.

    An empty directory is not an error and does not resolve a pipeline at all:
    there is nothing whose format needs an extractor, so there is nothing to
    choose, and opening a database connection to report "nothing to index"
    would be work done to say nothing happened.

    `contributions` — task **5.3a** (`S8`) — is `weft_cli.registry_bootstrap.Dependencies.
    contributions`, passed straight through to `_specs_from_document`'s own `resolve()` call
    when `pipeline` is given; a pack's own contributed stage runs in a named `--pipeline`
    document exactly as an authored one does. The default-path four stages below are Python
    constants with no slot to fill, so this parameter does nothing when `pipeline` is `None`.
    """
    if pipeline is not None and extractor is not None:
        raise WeftError(
            "run_index was given both 'pipeline' and 'extractor' — a named pipeline "
            "document's own 'extract' stage already names its plugin, so there is nothing "
            "for 'extractor' to narrow. Pass one or the other."
        )

    claims = claimed_extensions(registry)
    #: `"store"`, `index_specs`'s own literal id, matches the default path unchanged; the
    #: pipeline path below derives whichever id its document gave the one stage registered
    #: under the `NodeStore` contract — see `_store_stage_id_of`.
    store_stage_id: str | None = "store"
    resolved_pipeline: ResolvedPipeline | None = None
    if pipeline is not None:
        resolved_pipeline, specs = _specs_from_document(
            pipeline, registry=registry, reports=reports, contributions=contributions
        )
        name = _extractor_name_of(specs, pipeline=pipeline)
        store_stage_id = _store_stage_id_of(specs)
        accepted = _accepted_extensions(claims, registry=registry, extractor=name)
    else:
        accepted = _accepted_extensions(claims, registry=registry, extractor=extractor)
        specs = None  # chosen below, once the sole claimant (or --extract) is known

    present = present_suffixes(directory)
    readable = present & accepted
    docs = discover_source_docs(directory, extensions=readable)
    if not docs:
        return IndexResult(
            summary=_nothing_found(directory, present=present, accepted=accepted),
            stored_count=None,
            resolved_pipeline=resolved_pipeline,
        )

    if specs is None:
        name = (
            extractor
            if extractor is not None
            else _sole_claimant(readable, claims=claims, registry=registry)
        )
        specs = index_specs(name, embedder=embedder, store=store)

    runner = Runner(registry)
    runnable = runner.resolve(specs, tenant_id=ctx.tenant_id)

    async def batches() -> AsyncIterator[object]:
        yield docs

    try:
        summary = await runner.run(runnable, batches(), ctx)
        await _record_sources(runnable, store_stage_id=store_stage_id, docs=docs, pipeline=pipeline)
        stored_count = await _stored_count(runnable, store_stage_id=store_stage_id)
        return IndexResult(
            summary=summary,
            stored_count=stored_count,
            resolved_pipeline=resolved_pipeline,
            document_ids=tuple(str(doc.source_id) for doc in docs),
        )
    finally:
        for stage in runnable.stages:
            aclose = _aclose_of(stage.instance)
            if aclose is not None:
                await aclose()


def _specs_from_document(
    pipeline_name: str,
    *,
    registry: Registry,
    reports: Sequence[PackReport],
    contributions: tuple[Contribution, ...] = (),
) -> tuple[ResolvedPipeline, tuple[StageSpec, ...]]:
    """`pipeline_name` resolved into a `ResolvedPipeline` and the `StageSpec` list `Runner.
    resolve` consumes.

    `contributions` — task **5.3a** (`S8`) — reaches both `contracts_for` and `resolve()`
    below, exactly as `weft_cli.pipeline_commands._resolved_or_refuse` and `weft_cli.
    route_ask._run_pipeline` already receive it: one caller (`weft_cli.registry_bootstrap.
    build_dependencies`) assembles it once, and every `resolve()` call site passes it through
    unchanged rather than re-deriving its own tuple.

    The exact walk `weft_cli.route_ask.run_named_ask` already performs for a query
    pipeline — `full_catalogue` for the name, `contracts_for`/`to_specs` for the shape —
    reused rather than re-implemented, since 2.4's bridge is generic over *any* document,
    never specific to a query's own payload types. **Task 4.6 widens the return** from the
    `StageSpec` tuple alone to `(ResolvedPipeline, StageSpec tuple)`: `weft eval run` needs the
    resolved value itself to persist a run record, and `resolve()` had already computed it here
    a task ago — this hands it back rather than a second caller re-resolving the same document.

    **Repair, task 4.6: `parents` is the whole catalogue, not a one-entry mapping.** Found by
    running `weft eval run` over a real `pipeline pipeline derive`d document — a derived
    pipeline's own `extends:` names its parent, and `resolve()`'s own `parents` argument is
    where it looks that name up; a mapping holding only the named document itself has no parent
    for `extends:` to find, so every derived pipeline failed `UnknownParentPipelineError`
    outright, unconditionally — 4.0's own tests never caught it because none of them exercised
    `extends:` through this path. `weft_cli.pipeline_commands._resolved_or_refuse` (task 3.7)
    already passes the full `catalogue`, correctly; this function did not, on the identical
    footing `weft_cli.route_ask.run_named_ask`'s own sibling call still does not — see that
    module's own docstring for the parallel repair.
    """
    catalogue = full_catalogue(reports=reports)
    document = catalogue.get(pipeline_name)
    if document is None:
        options = tuple(sorted(catalogue))
        raise UnknownPipelineNameError(
            f"'{pipeline_name}' is not a pipeline this project knows — checked the "
            f"project's own 'pipelines' directory and every installed pack's own "
            f"contribution. Known pipelines: {', '.join(options) or '(none)'}.",
            valid_options=options,
            pipeline=pipeline_name,
            remedy=f"use one of: {', '.join(options) or '(none — no pipeline is known yet)'}.",
        )
    contracts = contracts_for(
        document, registry=registry, parents=catalogue, contributions=contributions
    )
    resolved = resolve(
        document,
        registry=registry,
        contracts=contracts,
        parents=catalogue,
        contributions=contributions,
    )
    return resolved, to_specs(resolved, registry=registry)


def _extractor_name_of(specs: tuple[StageSpec, ...], *, pipeline: str) -> str:
    """The plugin name of the one stage in `specs` registered under the `Extractor` contract.

    Contract-first, exactly as `_store_stage_id_of` is below: a `--pipeline` document owes
    this command no id convention, so "which stage extracts" is answered by asking the
    registry what each stage's plugin *is*, not by a stage id this module would otherwise
    invent a requirement for. Mandatory, unlike `_store_stage_id_of`: `weft index` cannot
    decide what to walk on disk without one, so a document naming none is refused rather
    than left to resolve into a run that reads nothing.
    """
    for spec in specs:
        if spec.contract is Extractor:
            return spec.name
    options = tuple(spec.id for spec in specs)
    raise PipelineMissingExtractStageError(
        f"pipeline '{pipeline}' has no stage registered under the Extractor contract, so "
        f"'weft index' has nothing to derive which files to read from. Stages: "
        f"{', '.join(options) or '(none)'}.",
        valid_options=options,
        pipeline=pipeline,
        remedy=(f"add a stage to '{pipeline}' whose 'use:' names a registered Extractor plugin."),
    )


def _store_stage_id_of(specs: tuple[StageSpec, ...]) -> str | None:
    """The id of the one stage in `specs` registered under the `NodeStore` contract, or
    `None` if no stage is.

    Not mandatory the way `_extractor_name_of` is: a document that stores nowhere still
    resolves and runs, it simply has nothing for `_stored_count` to report — the identical
    "`None` only defensively" spirit `IndexResult.stored_count`'s own docstring already
    states for a store with no callable `count`.
    """
    for spec in specs:
        if spec.contract is NodeStore:
            return spec.id
    return None


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
        "Name one with `--extract <name>`, or name a document with `--pipeline <name>` "
        "whose own 'extract' stage already picks one (ledger task 4.0). The kernel walks a "
        "stage's `fallback:` chain (ledger task 2.28), but this command still will not "
        "compose several claimants on its own."
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


async def _stored_count(runnable: RunnablePipeline, *, store_stage_id: str | None) -> int | None:
    if store_stage_id is None:
        return None
    for stage in runnable.stages:
        if stage.id != store_stage_id:
            continue
        count = _count_of(stage.instance)
        if count is not None:
            return await count()
    return None


async def _record_sources(
    runnable: RunnablePipeline,
    *,
    store_stage_id: str | None,
    docs: Sequence[SourceDoc],
    pipeline: str | None,
) -> None:
    """One `SourceRecord` per `SourceDoc` this run indexed — ledger task **6.24**'s repair of
    the defect `02` §1 documents: nothing on the ingest path ever called `put_source`, so
    `list_sources()` answered `()` after a real `weft index` and a `reconcile --mode repair`
    pass built on it deleted a corpus it had no record of just writing.

    Found the same way `_stored_count` finds the store: by the stage id `_store_stage_id_of`
    already derived from the resolved specs' own `contract`, never by the literal `"store"`
    id — a `--pipeline` document owes this module no naming convention. `content_hash` is over
    `doc.content` itself, because `02` §1's purpose for the field is change detection, which a
    hash of anything else could not serve. `pipeline` is `run_index`'s own parameter — the
    name the caller gave, not a value re-derived from `resolved_pipeline` — falling back to
    `BUILT_IN_PIPELINE_NAME` on the default four-stage path, which resolves no
    `ResolvedPipeline` at all and so has no name of its own to read.

    Raises whatever `put_source` raises: a source that was indexed and not recorded is the
    exact state this task exists to end, so a failure here is not caught and continued past.
    """
    if store_stage_id is None:
        return
    for stage in runnable.stages:
        if stage.id != store_stage_id:
            continue
        put_source = _put_source_of(stage.instance)
        if put_source is None:
            return
        name = pipeline if pipeline is not None else BUILT_IN_PIPELINE_NAME
        indexed_at = datetime.now(UTC)
        for doc in docs:
            await put_source(
                SourceRecord(
                    id=doc.source_id,
                    uri=doc.uri,
                    content_hash=hashlib.sha256(doc.content).hexdigest(),
                    indexed_at=indexed_at,
                    pipeline=name,
                )
            )
        return


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


def _put_source_of(instance: object) -> Callable[[SourceRecord], Awaitable[None]] | None:
    """`instance.put_source`, if it has one and it is callable — the same defensive shape as
    `_count_of`/`_aclose_of`. `put_source` **is** on the published `NodeStore` contract, so
    `None` here is not an admission the contract is optional; it is the identical spirit
    `_stored_count`'s own docstring already states for `count`.
    """
    found = getattr(instance, "put_source", None)
    if found is None or not callable(found):
        return None
    return cast(Callable[[SourceRecord], Awaitable[None]], found)
