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
configuration — `weft_engine.services`'s own docstring — so `OpenAIEmbedderConfig
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
test failed at the last inch. See `weft_engine.services`, which holds both
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
publishes — a store may or may not have a connection worth closing.
`weft_kernel.seam.aclose` makes the call defensively; this module names only
the stage each resolved instance is being closed for. Not a second `flush` —
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
import time
from collections import Counter
from collections.abc import (
    AsyncIterator,
    Awaitable,
    Callable,
    Collection,
    Iterable,
    Mapping,
    Sequence,
)
from contextlib import AsyncExitStack
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Final, cast

from pydantic import BaseModel

from weft_chunk import Chunker
from weft_cli.closing import CloseTarget, close_each
from weft_cli.compile import contracts_for, to_specs
from weft_cli.layers import (
    LayerComposition,
    LayerFailure,
    LayerJoin,
    LayerReclaim,
    LayerRelease,
    LayerStoreFallback,
    compose_layers,
    corpus_scoped_layer_names,
    demote_layer_records,
    require_corpus_layers_generation_holding,
    require_layers_metadata_filter,
    run_layers,
    sources_with_moved_layers,
    stale_corpus_layers,
)
from weft_cli.pipeline_catalogue import UnknownPipelineNameError, full_catalogue
from weft_cli.progress import BatchProgress
from weft_cli.writer_claim import claim_writer_for
from weft_embed import Embedder
from weft_engine.llm_roles import LLMSection
from weft_engine.registry_bootstrap import Dependencies
from weft_engine.run_services import build_index_services
from weft_engine.service_roles import RoleTable
from weft_engine.services import DEFAULT_EMBEDDER, DEFAULT_STORE, ServiceSelection
from weft_engine.targets import bind_store, claim_embedding_for_write, embedding_identity_of
from weft_extract import (
    Extractor,
    SourceDoc,
    claimed_extensions,
    present_suffixes,
)
from weft_extract.text import SourceRef, inventory_source_refs, load_source_docs
from weft_index.contract import Expander
from weft_index.payload import ExpansionDegraded
from weft_kernel.context import Context
from weft_kernel.discovery import PackReport
from weft_kernel.errors import UnresolvedNameError, WeftError
from weft_kernel.payload import SourceId
from weft_kernel.registry import Registry
from weft_kernel.resolution import (
    Contribution,
    ResolvedPipeline,
    ResolvedStage,
    pipeline_identity,
    resolve,
)
from weft_kernel.runner import (
    PipelineResolutionError,
    RunnablePipeline,
    Runner,
    RunSummary,
    StageSpec,
)
from weft_kernel.seam import OutcomeKind, StageRecord, recording
from weft_llm.client import NullSink
from weft_llm.contract import TokenSink
from weft_store import NodeStore
from weft_store.contract import (
    Cursor,
    Filter,
    FilterOp,
    GenerationId,
    LayerRecord,
    LayerStatus,
    MetadataFilter,
    SourceFailure,
    SourceRecord,
    SourceStatus,
    TargetHolding,
)

#: What `SourceRecord.pipeline` records for the built-in four-stage path — `06` step 9's
#: hardcoded pipeline, which resolves no `ResolvedPipeline` and so has no name to read.
#: `02` §1 wants this field to let `weft index` say "already indexed, by a different
#: pipeline", and a field meaning "which pipeline" cannot be empty on the path most corpora
#: are indexed by.
BUILT_IN_PIPELINE_NAME: Final[str] = "built-in"

#: Chunking: fixed, explicit, and stated once. See the module docstring for why extraction
#: is chosen at run time, and `weft_engine.services` for why embedding and storage are.
_CHUNK_SPEC = StageSpec(id="chunk", contract=Chunker, name="fixed-size")

#: `run_index`'s own defaults for its new `services`/`roles` parameters (ledger task **9.0**)
#: — module-level singletons, never `ServiceSelection()`/`RoleTable()` written inline in the
#: signature, because ruff's B008 refuses a function call in a default argument's position
#: regardless of the type being frozen. Both are empty and select nothing, which is exactly
#: today's behaviour for a caller — `weft_cli.eval_commands.EvalRunCommand.run`, until it too
#: threads `deps.services`/`deps.roles` through — that names neither.
_NO_SELECTION: Final[ServiceSelection] = ServiceSelection()
_NO_ROLES: Final[RoleTable] = RoleTable()

#: The packs `index_specs` names *itself*, in the order a caller should check them —
#: `weft_engine.registry_bootstrap.require_active`'s input, and entry-point names rather than
#: distribution names since a distribution may ship several. `store` is deliberately not
#: among them any more: the store is named by `[services] store`, so the pack that
#: provides it is whichever one registered that name, and a hard-coded tuple can never
#: contain a stranger's pack. `weft_cli.cli` covers it with `require_plugin`, exactly as it
#: already covers `--extract` and `[services] embed`.
#:
#: Read only for the default, no-`--pipeline` path: a named document may depend on none of
#: these three (a third party's own extractor and embedder pack, say), so `IndexCommand`
#: does not consult this tuple at all once `--pipeline` is given — see that class.
INDEX_PACKS: tuple[str, ...] = ("extract", "chunk", "embed")

#: Ledger task **43.2** — the batch size `weft index` runs with when nobody typed
#: `--batch-size`. `43.0` measured it against a 100-PDF corpus: 25 brings first ACTIVE from
#: 226.7 s to 49.1 s at no total cost. Only `weft_cli.commands.IndexCommand` passes this —
#: `run_index_for`'s other caller, `weft eval run`, keeps whole-corpus runs so its own
#: `ingest_seconds` stays comparable across arms.
DEFAULT_BATCH_SIZE: Final[int] = 25


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


class CorpusPathNotFoundError(WeftError):
    """`weft index` was given a path that is not on disk — carried repair `R27.1`.

    **Measured through the shipped binary at Phase 27's Exit, which is the only thing that
    found it**: an empty directory, a path that does not exist and a path that is a file each
    answered `produced 0, nothing to produce 1, failed 0. nodes now stored: unknown.` at exit
    `0`, byte-identical. So a user who mistyped a corpus path was told indexing had succeeded
    and produced nothing, and a script checking the exit code saw a clean run.

    The cause is one line of `pathlib`: `Path.rglob` yields nothing for a path that is not
    there, and raises nothing. The walk therefore *could not* tell the three cases apart, and
    `run_index`'s docstring — correctly — argues that an empty directory is not an error. A
    claim about one input said nothing about its neighbours, which is `L14.6`.

    **No `valid_options`, deliberately**: fitness function 12's family is for a name drawn from
    an enumerable set, and there is no set of valid filesystem paths to offer. This is
    `weft_kernel.discovery.EnvInterpolationError`'s side of that line, named in FF12's own
    module docstring, so it maps to exit `1` — *something failed* — rather than to exit `4`.
    """


class CorpusPathNotADirectoryError(WeftError):
    """`weft index` was given a path that exists and is not a directory — `R27.1`'s third input.

    Split from `CorpusPathNotFoundError` rather than folded into one path error, because the
    two have different remedies and the remedy is the whole value of the message: a path that
    is not there is a typo, and a path that is a file is a user who meant its directory. A
    single class would make `--json`'s `error.type` say *path problem* where it can say which
    one (`09` §3 promises that field for exactly this, and `L12.4` is what it cost to learn).

    Indexing a single file is not refused here because it is wrong to want — it is refused
    because nothing in this command supports it: `present_suffixes`, `discover_source_docs` and
    `corpus_documents` all take a directory. Naming the parent is the remedy that works today.
    """


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


class BatchScopedStageError(WeftError):
    """Refusal for `--batch-size` over a stage whose output depends on its batch.

    `--batch-size` was given a pipeline containing a stage whose output depends on which
    other nodes shared its batch — ledger task **17.3**.

    `Runner.run` puts each batch through the whole stage list independently, so a stage that
    clusters over whatever it is handed — the plugin names `batch_membership_dependent_stages`
    returns — computes a different tree per batch rather than one tree per run once the corpus
    is chunked, with no error and no failed exit: retrieval would still return passages, and the
    corpus would just be quietly worse. Refused instead, before anything is written or deleted.

    Not a name-resolution failure — there is no alternative *name* to offer, only a flag that
    does not compose with this pipeline — so this does not join `PipelineResolutionError` and
    does not join `NAME_RESOLUTION_FAMILY`, on `ConflictingIndexModeError`'s own footing
    (`weft_cli/commands.py:326 'class ConflictingIndexModeError(WeftError):'`).
    """


def index_specs(
    extractor: str, *, embedder: str = DEFAULT_EMBEDDER, store: str = DEFAULT_STORE
) -> tuple[StageSpec, ...]:
    """The four-stage ingest pipeline, with three of the four names given by the caller.

    `embedder` comes from `[services] embed` and `store` from `[services] store`
    — `weft_engine.services`, which holds the whole argument for why those two are
    configuration rather than constants, and why their defaults are the offline
    deterministic embedder and the backend `01` makes the floor.
    """
    return (
        StageSpec(id="extract", contract=Extractor, name=extractor),
        _CHUNK_SPEC,
        StageSpec(id="embed", contract=Embedder, name=embedder),
        StageSpec(id="store", contract=NodeStore, name=store),
    )


def _identity_of_specs(specs: tuple[StageSpec, ...], *, registry: Registry) -> str:
    """Compute `pipeline_identity` for the default four-stage path.

    `pipeline_identity` for the default four-stage path, which never calls `resolve()` —
    ledger task **9.17** repaired, `L9.64`.

    `index_specs` builds its `StageSpec`s as constants, so this path never has a
    `ResolvedPipeline` to hand `pipeline_identity`, and until this function existed the
    identity it recorded was `""` for every default-path run — indistinguishable from
    itself no matter which extractor, embedder or store actually ran. This rebuilds only
    the shape `pipeline_identity` actually reads off a `ResolvedStage` — `id`, `contract`,
    `contract_version`, `use`, `distribution`, `config` — from the `specs` this path
    already has, and feeds it through that one existing digest function rather than
    adding a second.

    **The `ResolvedPipeline`/`ResolvedStage` built here are throwaway, local to this
    computation, and never become `IndexResult.resolved_pipeline`.** That field means
    "what `weft_kernel.resolution.resolve` produced from a document", and this is a
    reconstruction from constants, not a resolution — one that cannot honestly fill
    `ResolvedPipeline.name`, `unapplied_operators` or `unplaced_contributions` (all three
    describe what happened while resolving a *document*: inheritance, operators,
    slot-filling — none of which this path ever does), or `ResolvedStage.provenance`
    (which pipeline or pack authored the stage — again a document-resolution fact this
    path has no answer for). `pipeline_identity`'s own docstring excludes all four from
    what it hashes, which is exactly why leaving them at their defaults here is safe
    rather than merely convenient.
    """
    stages = tuple(
        ResolvedStage(
            id=spec.id,
            contract=spec.contract.__name__,
            contract_version=getattr(spec.contract, "version", None),
            use=spec.name,
            config=_reconstructed_config(spec.config),
            distribution=registry.entry(spec.contract, spec.name).distribution,
            provenance="",
        )
        for spec in specs
    )
    return pipeline_identity(ResolvedPipeline(name="", stages=stages))


def _reconstructed_config(config: object) -> Mapping[str, object]:
    """Make a default-path stage's config hash the same way a resolved document's does.

    `StageSpec.config` translated into the shape `ResolvedStage.config` holds — see
    `_identity_of_specs`.

    `None`, what every stage `index_specs` builds today carries, becomes the same empty
    mapping `weft_kernel.resolution._validate_stage_config` returns for a plugin that
    declares no `config_model`. A plugin's own config object — a `pydantic.BaseModel` a
    caller assembled by hand — goes through `model_dump()`, the identical translation
    `weft_kernel.resolution._dump_stage_config` performs when a resolved pipeline's own
    config is serialised, so a caller who does hand the default path a real config object
    still gets sorted keys in the identity rather than a model's own `repr()` caught by
    `pipeline_identity`'s `default=str` fallback. Anything already mapping-shaped is
    passed through unchanged.
    """
    if config is None:
        return {}
    if isinstance(config, BaseModel):
        return config.model_dump()
    return cast("Mapping[str, object]", config)


@dataclass(frozen=True, slots=True, kw_only=True)
class IndexResult:
    """`run_index`'s return: the run-level summary, plus the store's own count if it has one.

    `stored_count` is `None` when the resolved store stage has no callable
    `count` — `NodeStore.count` is part of the published contract every store
    implements, so this is `None` only defensively: a fact this module reads
    if present, never a method it requires beyond what the contract already
    does. It is also `None` when nothing was found to index, because no store
    was ever built.

    **`resolved_pipeline`/`document_ids`, task 4.4/4.6.** A run record needs a resolved
    pipeline to persist and the corpus it measured — both facts this function already computes
    for the `pipeline=` path and previously discarded. `resolved_pipeline` is `None` on the
    default four-stage path, honestly: that path builds its `StageSpec`s as constants and never
    calls `weft_kernel.resolution.resolve`, so there is no `ResolvedPipeline` to hand back —
    exactly the gap task 4.0's own module docstring names as the reason it exists at all.
    `document_ids` is every `SourceDoc.source_id` this run actually discovered on disk — `()`
    when nothing was found — what a caller reports an empty corpus by, and no longer what a
    corpus digest is over: that is `content_hashes` below, and task 16.0's own ledger entry
    says why.
    """

    summary: RunSummary
    stored_count: int | None
    resolved_pipeline: ResolvedPipeline | None = None
    document_ids: tuple[str, ...] = ()
    #: Task **16.0** — every discovered document's sha256 over its own bytes, in the same order
    #: as `document_ids`, and the entries a caller hands `weft_eval.run_record.corpus_identity`.
    #: A digest over `document_ids` was a digest over where a machine put its files: it stood
    #: still when a document's contents changed, and moved when one was renamed.
    content_hashes: tuple[str, ...] = ()
    #: What re-indexing changed, per source — ledger task **9.17**. One entry per document this
    #: run discovered; empty only when it discovered none. The renderer reports only the sources
    #: that moved.
    #:
    #: *(This said "empty when the store this run used cannot answer `list_sources`" until task
    #: 17.4 measured it. That store's absent comparison reaches `changes_against_records` as an
    #: empty record mapping, which reports every source `NEW` — so the honest answer is there and
    #: it is not an empty dict. The distinction the old sentence was drawing is real and is kept:
    #: an absent comparison and an unchanged corpus are different facts, and `NEW` versus
    #: `UNCHANGED` is what keeps them apart. Task 17.0 now acts on that difference, so it is load
    #: bearing rather than descriptive — a store that cannot say what it holds gets a full
    #: re-index, never a silent skip.)*
    source_changes: Mapping[str, SourceChange] = field(
        default_factory=lambda: cast("Mapping[str, SourceChange]", {})
    )
    #: The identity this run's pipeline ran under, so a caller can print or persist it.
    pipeline_identity: str = ""
    #: Ledger task **17.4**, narrowed by **36.1**. How many documents this run actually recorded
    #: `ACTIVE` — the sum of every batch that produced, never `len(work)`: a batch `runner.run`
    #: failed or raised out of was handed to it too, but is recorded `FAILED`, not `ACTIVE`, so
    #: counting `work` would claim documents were indexed that were not.
    documents_indexed: int = 0
    #: Ledger **36.3** — documents this run recorded `FAILED`, so the summary line can count
    #: what did not change without counting a failure as unchanged.
    documents_failed: int = 0
    #: Ledger task **31.14** — the payload index field paths the store ensured, read off the
    #: built instance rather than re-derived from settings, so what is reported is what the run
    #: actually wrote. Empty when the store declares no such attribute, which is a stated absence
    #: and not a claim that it ensured none: pgvector ensures none and says nothing, and the
    #: renderer prints nothing for it.
    payload_indexes: tuple[str, ...] = ()
    #: Repair **R38.13** — how many stored chunks carry `weft_index.payload.
    #: ExpansionDegraded`, or `None` when this run cannot answer that. Set only when the
    #: resolved pipeline names an `Expander` stage *and* the built store instance is a
    #: `weft_store.contract.MetadataFilter` — a store that cannot evaluate a filter is not
    #: asked, and the default four-stage path resolves no pipeline document at all, so it is
    #: always `None` there.
    degraded_expansions: int | None = None
    #: `--target`, ledger task **34.6**, widened by **34.10** — the target this run actually
    #: wrote into: the name given to `--target`, or, absent one, the live target this run
    #: opened against (never `None` for a store that satisfies `TargetHolding`; `None` only
    #: when the store has no notion of a target at all). Carried here so `weft_cli.render` can
    #: report where the run wrote without re-deriving it.
    target: str | None = None
    #: The target that was live at the moment this run started, read once before any store
    #: stage is bound — `None` only when the store could not answer. Paired with `target` to
    #: say whether this run built a candidate or wrote the live target itself; equal to
    #: `target` whenever no `--target` was given.
    target_live: str | None = None
    #: Ledger task **34.10** — `True` when this run wrote the live target (no `--target`) and,
    #: by the time it finished, another promote had made a different target live: the run still
    #: finished into `target`, the one it opened against, never split across two.
    target_stopped_being_live: bool = False
    #: `target_stopped_being_live`'s own partner — the target that is live now that this run has
    #: finished, `None` unless `target_stopped_being_live` is, since it is otherwise identical to
    #: `target_live`.
    target_now_live: str | None = None
    #: Ledger task **43.8** — every named layer whose stored identity moved since it last ran,
    #: each name once, in the order named — never re-run unasked, only reported. `()` when no
    #: layer was named, or every named layer's identity still matches what is stored.
    layers_changed: tuple[str, ...] = ()
    #: Carried repair **R43.9** — every named layer this run tried and could not build, with
    #: how many of its sources failed and the first reason. A source skipped because an earlier
    #: run recorded it failed is not counted: this run did not try it.
    layers_failed: tuple[LayerFailure, ...] = ()
    #: Ledger task **43.23** — every corpus-scoped layer this run joined added sources into
    #: through its `layer.incremental` stage, rather than rebuilding it.
    layers_joined: tuple[LayerJoin, ...] = ()
    #: Repair **R43.38** — each store stage a corpus layer fell back on this run, once: see
    #: `weft_cli.layers.LayerStoreFallback`.
    stores_without_withdraw: tuple[LayerStoreFallback, ...] = ()
    stores_without_carry: tuple[LayerStoreFallback, ...] = ()
    #: Repair **R43.43** — each corpus-scoped layer whose builds reclaimed nodes from its
    #: withdrawn generations, and how many; a layer that reclaimed none is absent.
    layers_reclaimed: tuple[LayerReclaim, ...] = ()
    #: Repair **R43.47** — every corpus-layer generation this run's publishes withdrew, which
    #: `IndexCommand`'s closing reconcile pass spares so a reader that opened on one keeps it
    #: until the layer's next build or an explicit `weft reconcile`. Not an operator fact.
    generations_withdrawn: tuple[GenerationId, ...] = ()
    #: Carried repair **R43.28** — every layer a source `--reprocess` released carried that this
    #: run did not name, so released and not rebuilt, by name. `()` without `reprocess`.
    layers_released: tuple[LayerRelease, ...] = ()
    #: Ledger task **43.15** — every corpus-scoped layer document `ACTIVE` on at least one of
    #: this run's `ACTIVE` sources but not on all of them, sorted by name. Computed regardless
    #: of what `layers` this run itself named: a source indexed without naming the layer still
    #: leaves it behind everybody else. `()` when nothing is stale, or no corpus-scoped layer
    #: is installed at all.
    layers_stale: tuple[str, ...] = ()
    #: `(built, of)` for every name in `layers_stale`, so `weft_cli.render` can print how far a
    #: stale layer has got without re-deriving it from the store a second time — the same
    #: reason `payload_indexes`/`degraded_expansions` travel here rather than being recomputed
    #: at render time.
    layers_stale_progress: Mapping[str, tuple[int, int]] = field(
        default_factory=lambda: cast("Mapping[str, tuple[int, int]]", {})
    )
    #: Ledger **43.21**, **R43.41** — layers a deletion or a re-parse staled, this run's among
    #: them: `weft_cli.layers.stale_corpus_layers`.
    layers_stale_deleted: tuple[str, ...] = ()


async def count_degraded_expansions(store: MetadataFilter) -> int:
    """Every stored node carrying `weft_index.payload.ExpansionDegraded`, paged to the end.

    Repair **R38.13**. The store is the authority: the marker lives outside a node's id, so
    only a query over what is actually stored — not over what a run's own `RunSummary`
    counted — answers how many chunks a questions arm actually lost.
    """
    total = 0
    cursor: Cursor | None = None
    filter_ = Filter(op=FilterOp.EXISTS, field=f"ext.{ExpansionDegraded.__namespace__}.expander")
    while True:
        page = await store.matching(filter_, cursor)
        total += len(page.items)
        if page.next_cursor is None:
            return total
        cursor = page.next_cursor


def _validate_batch_size(batch_size: int | None) -> None:
    """`run_index`'s own bound on `batch_size` — no corpus makes a value below `1` sensible.

    `ValueError`, not a `WeftError`: this is a caller handing a library function a value no
    corpus could make sensible, Python's own vocabulary for the case, and unreachable from the
    CLI — `IndexArgs.batch_size`'s own `gt=0` bounds the flag before it ever reaches here.
    """
    if batch_size is not None and batch_size < 1:
        raise ValueError(f"batch_size must be a positive integer, got {batch_size!r}.")


def _refuse_batch_scoped_stages(runnable: RunnablePipeline) -> None:
    """Raise `BatchScopedStageError` when `runnable` holds a batch-scoped stage.

    `BatchScopedStageError`, when `runnable` holds a stage whose output depends on batch
    membership — see that class and `batch_membership_dependent_stages` for the whole argument.
    """
    dependent = batch_membership_dependent_stages(runnable)
    if not dependent:
        return
    names = ", ".join(dependent)
    raise BatchScopedStageError(
        f"--batch-size cannot be used with this pipeline: {names} computes its output over "
        "whichever nodes share its batch, so splitting the corpus would silently build a "
        "different tree per batch instead of one tree per run. Drop --batch-size, or use the "
        "'index-with-adrap' rung instead, which joins a later batch into a tree an earlier run "
        "already built."
    )


def _batch_plan(
    batch_size: int | None, default_batch_size: int | None, runnable: RunnablePipeline
) -> tuple[int | None, tuple[str, ...]]:
    """Decide this run's effective batch size and the plugins that forced one batch.

    The effective batch size for this run, and the plugin names — if any — that kept the
    whole corpus in one batch instead — ledger task **43.2**.

    An explicit `batch_size` keeps its own meaning unchanged: `_refuse_batch_scoped_stages`
    still refuses a batch-scoped pipeline outright rather than falling back to one batch.
    `default_batch_size` treats the identical fact the other way — a reason to keep the
    corpus whole rather than a reason to refuse — because nobody asked for a bound this run
    cannot honour; `whole_corpus_for` is what a progress line then names.
    """
    if batch_size is not None:
        _refuse_batch_scoped_stages(runnable)
        return batch_size, ()
    if default_batch_size is None:
        return None, ()
    dependent = batch_membership_dependent_stages(runnable)
    if dependent:
        return None, dependent
    return default_batch_size, ()


async def _emit_batch_progress(
    on_batch: Callable[[BatchProgress], Awaitable[None]] | None,
    *,
    batch_number: int,
    batches: int,
    queryable: int,
    documents: int,
    start_time: float,
    whole_corpus_for: tuple[str, ...],
    batch_bytes: int = 0,
) -> None:
    """`on_batch`, fed one `BatchProgress` per finished batch — ledger task **43.2**.

    A no-op for an empty `work` (`documents == 0`): task 17.0's fully-unchanged-corpus path
    still runs one batch through `Runner.run` to preserve that behaviour, and a progress line
    reporting 0/0 documents would tell an operator nothing they did not already know from the
    run's own summary.
    """
    if on_batch is None or documents == 0:
        return
    await on_batch(
        BatchProgress(
            batch=batch_number,
            batches=batches,
            queryable=queryable,
            documents=documents,
            seconds=time.monotonic() - start_time,
            whole_corpus_for=whole_corpus_for,
            bytes=batch_bytes,
        )
    )


def _sliced(items: Sequence[SourceRef], size: int | None) -> list[tuple[SourceRef, ...]]:
    """Split `items` into groups of `size`, or one group when `size` is `None`.

    `items`, in groups of `size` (or one whole group when `size` is `None`) — `run_index`'s
    own slicing of `work`, generalised so `_run_base` states it once rather than inline.
    """
    if size is None:
        return [tuple(items)]
    return [tuple(items[start : start + size]) for start in range(0, len(items), size)]


async def _load_and_run_batch(
    runner: Runner,
    runnable: RunnablePipeline,
    batch_refs: Sequence[SourceRef],
    indexing_ctx: Context,
) -> tuple[tuple[SourceDoc, ...], RunSummary]:
    """Read one batch's sources and run them through `runnable` as one payload."""
    batch_docs = load_source_docs(batch_refs)
    return batch_docs, await runner.run(runnable, _one(batch_docs), indexing_ctx)


async def _settle_batch(
    runner: Runner,
    runnable: RunnablePipeline,
    batch_refs: Sequence[SourceRef],
    batch_docs: Sequence[SourceDoc],
    batch_summary: RunSummary,
    indexing_ctx: Context,
    *,
    records: Sequence[StageRecord],
    store_stage_ids: Sequence[str],
    previous: Mapping[SourceId, SourceRecord],
    identity: str,
    pipeline: str | None,
) -> tuple[list[RunSummary], int, int]:
    """Record one finished batch's sources, re-running a failed multi-document batch singly.

    Returns:
        `(summaries, indexed, failed)`: the summaries this batch contributes, and how many of
        its documents were indexed and how many recorded `FAILED`.
    """
    if batch_summary.failed == 0:
        await _record_sources(
            runnable,
            store_stage_ids=store_stage_ids,
            docs=batch_refs,
            pipeline=pipeline,
            identity=identity,
        )
        return [batch_summary], len(batch_refs), 0
    if len(batch_refs) == 1:
        message = "; ".join(batch_summary.failed_reasons) or "the batch failed"
        await _record_batch_failure(
            runnable,
            store_stage_ids=store_stage_ids,
            batch=batch_refs,
            previous=previous,
            identity=identity,
            pipeline=pipeline,
            error_type="Failed",
            stage=_failing_stage(records),
            message=message,
        )
        return [batch_summary], 0, 1
    return await _rerun_batch_singly(
        runner,
        runnable,
        batch_docs,
        indexing_ctx,
        store_stage_ids=store_stage_ids,
        previous=previous,
        identity=identity,
        pipeline=pipeline,
    )


async def _run_base(
    runnable: RunnablePipeline,
    runner: Runner,
    *,
    layers_only: bool,
    refs: Sequence[SourceRef],
    previous: Mapping[SourceId, SourceRecord],
    identity: str,
    retry_failed: bool,
    reprocess: bool,
    pipeline: str | None,
    store_stage_ids: Sequence[str],
    effective_batch_size: int | None,
    whole_corpus_for: tuple[str, ...],
    on_batch: Callable[[BatchProgress], Awaitable[None]] | None,
    indexing_ctx: Context,
    corpus_layers: frozenset[str],
) -> tuple[Mapping[SourceId, SourceChange], tuple[SourceRef, ...], list[RunSummary], int, int]:
    """Run every batch of `work` through `runnable`, or nothing under `layers_only`.

    The base's own run — every batch of `work` through `runnable` — or nothing at all under
    `layers_only`, lifted out of `run_index` so ledger task **43.8**'s own addition does not
    push that function's complexity over the budget every function in this module already
    holds to. Returns `(changes, work, counts, indexed_count, failed_count)`, the five values
    `run_index` needs back from whichever branch ran.

    `layers_only=True` — ledger task **43.8** — skips this entirely: no extract, no
    `_release_reparsed_sources`, no `INDEXING`/catch-up write. The layer loop `run_index` runs
    afterward reads whatever this project already recorded.
    """
    if layers_only:
        return {}, (), [], 0, 0

    changes = changes_against_records(refs, previous, identity=identity, retry_failed=retry_failed)
    demoted = set(
        await _release_reparsed_sources(
            runnable,
            store_stage_ids=store_stage_ids,
            changes=changes,
            corpus_layers=corpus_layers,
        )
    )
    if reprocess:
        # R43.7, the owner's Q6: `--reprocess` rebuilds a source's layers with its base, so an
        # unchanged source that has any gives up the nodes they derived along with its leaves.
        demoted.update(
            await _release_sources(
                runnable,
                store_stage_ids=store_stage_ids,
                sources=_released_by_reprocess(changes, previous),
                corpus_layers=corpus_layers,
            )
        )
    # Ledger task **17.0** — a document whose change is `UNCHANGED` owes this run no work: the
    # store dedupes by content digest, so re-running it would only re-pay extraction, chunking,
    # every enhancer's LLM call and embedding to rewrite rows already right. `reprocess`
    # overrides this for the one change `pipeline_identity` cannot see. Ledger **36.2** —
    # `FAILED` owes this run no work on the identical footing: paid stages sit on the ingest
    # path, so a failure is not retried unasked, and `retry_failed` is the one thing that turns
    # it into `RETRIED` work instead (see `changes_against_records`).
    work = (
        tuple(refs)
        if reprocess
        else tuple(
            ref
            for ref in refs
            if changes.get(ref.source_id) not in (SourceChange.UNCHANGED, SourceChange.FAILED)
        )
    )
    # Ledger task **17.1** — marked before the run so a crash mid-`runner.run` leaves these
    # documents' records saying `INDEXING` rather than the previous run's stale `ACTIVE` or no
    # record at all. Narrowed to `work`, not `refs`: an `UNCHANGED` document's own record is
    # still accurate and this write must not overwrite it with a status the run below never
    # touches it under.
    await _record_sources(
        runnable,
        store_stage_ids=store_stage_ids,
        docs=work,
        pipeline=pipeline,
        identity=identity,
        status=SourceStatus.INDEXING,
    )

    # Ledger task **17.3**, widened by **43.2**. `None` is `work` as one batch, exactly as this
    # function always has — including when `work` is empty, which task **17.0**'s
    # fully-unchanged-corpus behaviour depends on. Otherwise, successive slices of
    # `effective_batch_size` refs (an explicit `batch_size`, or `default_batch_size` when
    # nothing refuses it — see `_batch_plan`), with a shorter final slice when the length is
    # not an exact multiple.
    ref_slices = _sliced(work, effective_batch_size)
    # Ledger task **43.2** — recorded immediately before the loop below, so every batch's
    # `seconds` is measured against the same start rather than against each other.
    batch_loop_started = time.monotonic()

    # Task **38.14**, superseding carried repair R36.0's "a batch that did succeed is re-paid":
    # each batch is its own `runner.run`, flushed and recorded `ACTIVE` the moment it produced,
    # so a failed batch — or a run killed after batch k — leaves batches 1..k done and only the
    # rest `INDEXING`. `38.6`'s question index re-paid every model call twice.
    #
    # Ledger **36.1** — a batch this loop could not finish is recorded `FAILED` rather than left
    # `INDEXING`: a batch `runner.run` returns `Failed` for is read off `RunSummary` below; a
    # batch it raises out of is caught here, recorded, and re-raised unchanged —
    # `CancelledError` above all is never one of the exceptions this catches. **R43.1** narrows
    # this: a batch of more than one document that returns `Failed` is re-run one document at a
    # time before anything is recorded, so a service fault still raises and stops the run, but
    # only a document that fails alone is recorded `FAILED`.
    counts: list[RunSummary] = []
    indexed_count = 0
    failed_count = 0
    for batch_number, batch_refs in enumerate(ref_slices, start=1):
        with recording() as scope:
            try:
                batch_docs, batch_summary = await _load_and_run_batch(
                    runner, runnable, batch_refs, indexing_ctx
                )
            except WeftError as exc:
                await _record_batch_failure(
                    runnable,
                    store_stage_ids=store_stage_ids,
                    batch=batch_refs,
                    previous=previous,
                    identity=identity,
                    pipeline=pipeline,
                    error_type=type(exc).__name__,
                    stage=exc.stage,
                    message=str(exc),
                )
                raise
        settled, indexed_delta, failed_delta = await _settle_batch(
            runner,
            runnable,
            batch_refs,
            batch_docs,
            batch_summary,
            indexing_ctx,
            records=scope.records,
            store_stage_ids=store_stage_ids,
            previous=previous,
            identity=identity,
            pipeline=pipeline,
        )
        counts.extend(settled)
        indexed_count += indexed_delta
        failed_count += failed_delta
        await _emit_batch_progress(
            on_batch,
            batch_number=batch_number,
            batches=len(ref_slices),
            queryable=indexed_count,
            documents=len(work),
            start_time=batch_loop_started,
            whole_corpus_for=whole_corpus_for,
            batch_bytes=sum(ref.size for ref in batch_refs),
        )
    # Ledger **36.2** — a source this run left `FAILED` keeps that record exactly as
    # `_record_batch_failure` wrote it: `attempted` already excludes it (it was never `work`),
    # and it must also be excluded here, or this catch-up write — meant only for the
    # `UNCHANGED` sources `work` skipped — would promote it back to `ACTIVE` for no reason but
    # having been left alone this run. **Ledger 43.8** — this is the one `_record_sources` call
    # an `UNCHANGED` source ever reaches, which is why `changes`/`previous` are passed here and
    # nowhere else: every other call site's `docs` excludes `UNCHANGED` sources by construction.
    attempted = {ref.source_id for ref in work}
    skipped_as_failed = {
        ref.source_id for ref in refs if changes.get(ref.source_id) is SourceChange.FAILED
    }
    await _record_sources(
        runnable,
        store_stage_ids=store_stage_ids,
        docs=tuple(
            ref
            for ref in refs
            if ref.source_id not in attempted and ref.source_id not in skipped_as_failed
        ),
        pipeline=pipeline,
        identity=identity,
        changes=changes,
        previous=previous,
        demoted=frozenset(demoted),
    )
    return changes, work, counts, indexed_count, failed_count


def _released_by_reprocess(
    changes: Mapping[SourceId, SourceChange], previous: Mapping[SourceId, SourceRecord]
) -> dict[SourceId, SourceRecord]:
    """Make `--reprocess` rebuild layers on sources whose own bytes did not change.

    Every `UNCHANGED` source whose previous record carries a layer, with that record — what
    `--reprocess` releases beyond the reparsed sources (R43.7).
    """
    return {
        source: record
        for source, change in changes.items()
        if change is SourceChange.UNCHANGED
        and (record := previous.get(source)) is not None
        and record.layers
    }


def _layers_released(
    compositions: Sequence[LayerComposition],
    *,
    changes: Mapping[SourceId, SourceChange],
    previous: Mapping[SourceId, SourceRecord],
    reprocess: bool,
) -> tuple[LayerRelease, ...]:
    """Count, by layer name, released sources carrying a layer this run did not name.

    Every layer a source `--reprocess` released carried and this run did not name, with how
    many released sources carried it, by name — carried repair **R43.28**.
    """
    if not reprocess:
        return ()
    named = {composition.layer for composition in compositions}
    carried = Counter(
        entry.name
        for record in _released_by_reprocess(changes, previous).values()
        for entry in record.layers
        if entry.name not in named
    )
    return tuple(LayerRelease(layer=name, sources=carried[name]) for name in sorted(carried))


def _base_scope(
    compositions: Sequence[LayerComposition],
    *,
    refs: Sequence[SourceRef],
    previous: Mapping[SourceId, SourceRecord],
    layers_only: bool,
    reprocess: bool,
) -> tuple[Sequence[SourceRef], bool]:
    """`(refs, layers_only)` for `_run_base`.

    Under `--layers-only --reprocess`, the sources whose per-source layer moved run the base as if
    `--layers-only` were absent, and only those: a layer's earlier output can only be released with
    its source (R43.27).
    """
    if not (layers_only and reprocess):
        return refs, layers_only
    moved = sources_with_moved_layers(compositions, refs=refs, records=previous)
    return (moved, False) if moved else (refs, True)


async def _layer_outcomes(
    layer_compositions: Sequence[LayerComposition],
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
    reprocess: bool,
) -> tuple[
    tuple[str, ...],
    tuple[LayerFailure, ...],
    tuple[LayerJoin, ...],
    tuple[LayerStoreFallback, ...],
    tuple[LayerStoreFallback, ...],
    tuple[LayerReclaim, ...],
    tuple[GenerationId, ...],
]:
    """What `run_layers` reports for `layer_compositions`, or seven empty tuples for none."""
    layers_changed: tuple[str, ...] = ()
    layers_failed: tuple[LayerFailure, ...] = ()
    layers_joined: tuple[LayerJoin, ...] = ()
    stores_without_withdraw: tuple[LayerStoreFallback, ...] = ()
    stores_without_carry: tuple[LayerStoreFallback, ...] = ()
    layers_reclaimed: tuple[LayerReclaim, ...] = ()
    generations_withdrawn: tuple[GenerationId, ...] = ()
    if layer_compositions:
        (
            layers_changed,
            layers_failed,
            layers_joined,
            stores_without_withdraw,
            stores_without_carry,
            layers_reclaimed,
            generations_withdrawn,
        ) = await run_layers(
            layer_compositions,
            runner=runner,
            runnable=runnable,
            refs=refs,
            store_stage_id=store_stage_id,
            store_stage_ids=store_stage_ids,
            effective_batch_size=effective_batch_size,
            retry_failed=retry_failed,
            on_batch=on_batch,
            indexing_ctx=indexing_ctx,
            layer_runnables=layer_runnables,
            llm=llm,
            reprocess=reprocess,
        )
    return (
        layers_changed,
        layers_failed,
        layers_joined,
        stores_without_withdraw,
        stores_without_carry,
        layers_reclaimed,
        generations_withdrawn,
    )


def _add_layer_readers_store(
    indexing_ctx: Context,
    specs: tuple[StageSpec, ...],
    layer_compositions: Sequence[LayerComposition],
    runnable: RunnablePipeline,
) -> None:
    """Offer the base's store to layer stages that read the corpus, when any does."""
    layer_specs = tuple(
        spec for c in layer_compositions for spec in (*c.layer_specs, *c.incremental_specs)
    )
    layer_readers_store = _store_instance_for_corpus_readers((*specs, *layer_specs), runnable)
    if layer_readers_store is not None:
        indexing_ctx.services.add(NodeStore, layer_readers_store)


async def _index_claimed(
    runner: Runner,
    runnable: RunnablePipeline,
    specs: tuple[StageSpec, ...],
    refs: Sequence[SourceRef],
    *,
    claim_stack: AsyncExitStack,
    layer_runnables: list[RunnablePipeline],
    registry: Registry,
    reports: Sequence[PackReport],
    contributions: tuple[Contribution, ...],
    resolved_pipeline: ResolvedPipeline | None,
    pipeline: str | None,
    base_name: str,
    layers: tuple[str, ...],
    layers_only: bool,
    reprocess: bool,
    retry_failed: bool,
    store_stage_id: str | None,
    store_stage_ids: tuple[str, ...],
    store_for_readers: NodeStore | None,
    indexing_ctx: Context,
    effective_batch_size: int | None,
    whole_corpus_for: tuple[str, ...],
    on_batch: Callable[[BatchProgress], Awaitable[None]] | None,
    run_llm: LLMSection,
    target: str | None,
    target_live: str | None,
) -> IndexResult:
    """Check the layers, claim the store's writer, then run the base and every layer.

    `run_index`'s own guarded body: `claim_stack` holds the writer claim and `layer_runnables`
    collects every layer pipeline built, both for `run_index` to close whatever happens.
    """
    identity = (
        pipeline_identity(resolved_pipeline)
        if resolved_pipeline is not None
        else _identity_of_specs(specs, registry=registry)
    )
    # Ledger task **43.8** — composed and checked before anything below is written or
    # deleted: `_release_reparsed_sources` is the first write this function makes.
    layer_compositions = compose_layers(
        layers,
        base=base_name,
        specs=specs,
        registry=registry,
        reports=reports,
        contributions=contributions,
    )
    require_layers_metadata_filter(
        layers, runnable=runnable, store_stage_id=store_stage_id, specs=specs
    )
    require_corpus_layers_generation_holding(
        layer_compositions, runnable=runnable, specs=specs, registry=registry
    )
    # R43.20: a layer stage whose contract reads the corpus is handed the base's store too.
    if store_for_readers is None:
        _add_layer_readers_store(indexing_ctx, specs, layer_compositions, runnable)
    # Ledger task **43.18**: one writer per store, claimed before the first write.
    writer = next((st.instance for st in runnable.stages if st.id == store_stage_id), None)
    await claim_stack.enter_async_context(claim_writer_for(writer, command="weft index"))
    # Read *before* the run writes over them: the comparison is against what the last index
    # left, and `_record_sources` below replaces exactly those rows.
    previous = await _recorded_sources(runnable, store_stage_id=store_stage_id)

    # `work` is `_run_base`'s own concern — nothing here reads it back; `refs` is what
    # `IndexResult.document_ids`/`content_hashes` are built from, unconditionally.
    base_refs, base_skipped = _base_scope(
        layer_compositions,
        refs=refs,
        previous=previous,
        layers_only=layers_only,
        reprocess=reprocess,
    )
    corpus_layers = frozenset(
        corpus_scoped_layer_names(registry=registry, reports=reports, contributions=contributions)
    )
    changes, _work, counts, indexed_count, failed_count = await _run_base(
        runnable,
        runner,
        layers_only=base_skipped,
        refs=base_refs,
        previous=previous,
        identity=identity,
        retry_failed=retry_failed,
        reprocess=reprocess,
        pipeline=pipeline,
        store_stage_ids=store_stage_ids,
        effective_batch_size=effective_batch_size,
        whole_corpus_for=whole_corpus_for,
        on_batch=on_batch,
        indexing_ctx=indexing_ctx,
        corpus_layers=corpus_layers,
    )
    summary = _summed(counts)
    layers_released = _layers_released(
        layer_compositions, changes=changes, previous=previous, reprocess=reprocess
    )

    (
        layers_changed,
        layers_failed,
        layers_joined,
        stores_without_withdraw,
        stores_without_carry,
        layers_reclaimed,
        generations_withdrawn,
    ) = await _layer_outcomes(
        layer_compositions,
        runner=runner,
        runnable=runnable,
        refs=refs,
        store_stage_id=store_stage_id,
        store_stage_ids=store_stage_ids,
        effective_batch_size=effective_batch_size,
        retry_failed=retry_failed,
        on_batch=on_batch,
        indexing_ctx=indexing_ctx,
        layer_runnables=layer_runnables,
        llm=run_llm,
        reprocess=reprocess,
    )

    stored_count = await _stored_count(runnable, store_stage_id=store_stage_id)
    written_target, target_stopped_being_live, target_now_live = await _target_written(
        runnable, target=target, target_live=target_live
    )
    layers_stale, layers_stale_progress, layers_stale_deleted = await stale_corpus_layers(
        runnable=runnable,
        store_stage_id=store_stage_id,
        refs=refs,
        registry=registry,
        reports=reports,
        contributions=contributions,
    )
    return IndexResult(
        summary=summary,
        stored_count=stored_count,
        resolved_pipeline=resolved_pipeline,
        document_ids=tuple(str(ref.source_id) for ref in refs),
        content_hashes=content_hashes_of(refs),
        source_changes={str(source): change for source, change in changes.items()},
        pipeline_identity=identity,
        documents_indexed=indexed_count,
        documents_failed=failed_count,
        payload_indexes=_payload_indexes(runnable, store_stage_id=store_stage_id),
        degraded_expansions=await _degraded_expansions(
            runnable, resolved_pipeline=resolved_pipeline, store_stage_id=store_stage_id
        ),
        target=written_target,
        target_live=target_live,
        target_stopped_being_live=target_stopped_being_live,
        target_now_live=target_now_live,
        layers_changed=layers_changed,
        layers_failed=layers_failed,
        layers_joined=layers_joined,
        stores_without_withdraw=stores_without_withdraw,
        stores_without_carry=stores_without_carry,
        layers_reclaimed=layers_reclaimed,
        generations_withdrawn=generations_withdrawn,
        layers_released=layers_released,
        layers_stale=layers_stale,
        layers_stale_progress=layers_stale_progress,
        layers_stale_deleted=layers_stale_deleted,
    )


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
    llm: LLMSection | None = None,
    sink: TokenSink | None = None,
    services: ServiceSelection = _NO_SELECTION,
    roles: RoleTable = _NO_ROLES,
    reprocess: bool = False,
    batch_size: int | None = None,
    default_batch_size: int | None = None,
    on_batch: Callable[[BatchProgress], Awaitable[None]] | None = None,
    retry_failed: bool = False,
    target: str | None = None,
    layers: tuple[str, ...] = (),
    layers_only: bool = False,
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

    `contributions` — task **5.3a** (`S8`) — is `weft_engine.registry_bootstrap.Dependencies.
    contributions`, passed straight through to `_specs_from_document`'s own `resolve()` call
    when `pipeline` is given; a pack's own contributed stage runs in a named `--pipeline`
    document exactly as an authored one does. The default-path four stages below are Python
    constants with no slot to fill, so this parameter does nothing when `pipeline` is `None`.

    `services`/`roles` — ledger task **9.0** — are `weft_engine.registry_bootstrap.Dependencies.
    services`/`.roles`, threaded straight through to `weft_engine.run_services.
    build_index_services` alongside `filled_by_stages` (every contract the resolved `specs`
    already fill, computed here since this is the one place both `specs` and the role table
    are in scope). Both default to an empty table/selection — a caller naming neither gets
    exactly today's four-service ingest registry, unchanged.

    `reprocess` — ledger task **17.0**. A document whose `SourceChange` comes back `UNCHANGED`
    is skipped by default: the bytes and the pipeline identity both match the last recorded
    run, so re-extracting, re-chunking, re-enhancing and re-embedding it would only rewrite
    rows the store already deduplicates by content digest. `True` hands every discovered
    document to the runner anyway, for the one change `pipeline_identity` cannot see — a
    hosted model that moved behind a stable name. The report is unaffected either way: a
    document that did not move still reports `UNCHANGED`, because `source_changes` answers
    *what changed*, not *what ran*.

    `batch_size` — ledger task **17.3**. `None`, the default, is today's behaviour exactly: one
    batch holding the whole corpus, the only shape this function has ever handed `Runner.run`.
    Given a positive integer, the corpus is walked in that many documents at a time instead, so
    peak memory is bounded by the batch rather than by the corpus — `02`:590's own claim, true of
    `Runner.run` since Phase 0 and false of this function until now. A value below `1` raises
    `ValueError` naming `batch_size`, since no corpus makes such a value sensible; unreachable
    from the CLI, where `IndexArgs.batch_size` is bounded at the flag. When the resolved pipeline
    contains a stage whose output depends on which other nodes shared its batch —
    `batch_membership_dependent_stages` — this is refused with `BatchScopedStageError` instead of
    silently computing a different tree per batch; the refusal happens before anything is written
    or deleted.

    `default_batch_size` — ledger task **43.2**. Read only when `batch_size` is `None`: an
    explicit `--batch-size` always wins, unchanged. Given a value, that many documents run per
    batch unless the resolved pipeline holds a stage `batch_membership_dependent_stages` names —
    such a pipeline is not refused under the default the way it is under an explicit
    `batch_size`, since nobody asked for a bound this run cannot honour; it keeps the whole
    corpus in one batch instead, and every `on_batch` event this run emits carries that stage's
    plugin name in `whole_corpus_for`. `weft_cli.commands.IndexCommand` is the only caller that
    passes this — `run_index_for`'s other caller, `weft eval run`, keeps whole-corpus runs.

    `on_batch` — ledger task **43.2**. Awaited once per finished batch (success, R43.1's
    per-document isolation, or a batch recorded `FAILED`), never for a batch a `WeftError`
    raises out of, and never when `work` is empty. `weft_cli.commands.IndexCommand` feeds it a
    sink's own `batch_progress` when that sink satisfies `weft_cli.progress.ProgressReporter`;
    a caller of `run_index` directly gets no progress unless it passes one.

    `retry_failed` — ledger **36.2**. `False`, the default, leaves a source this project already
    recorded `FAILED` skipped exactly like `UNCHANGED` — paid stages sit on the ingest path, so a
    failure is not retried unasked. `True` treats it as work instead (`SourceChange.RETRIED`),
    released before the attempt the same way an `INCOMPLETE` source already is. Neither value
    changes what a source whose bytes or pipeline moved since it failed reports: that is always
    `CONTENT_CHANGED`/`PIPELINE_CHANGED`, and always work.

    `target` — ledger task **34.6**. `None`, the default, writes the live target, exactly
    today's behaviour. Given a name, every `NodeStore` stage this run resolved is bound to it
    through `weft_engine.targets.bind_store` — a candidate beside the live target, created on
    its first write — immediately after resolution and before anything reads or writes through
    it, so every helper below (`_store_instance_for_corpus_readers`, `_record_sources`,
    `_recorded_sources`, `_stored_count`, ...) already sees the bound handle. The embedding
    identity claim then passes `required=True`: an embedder that cannot state its identity is
    refused for a `--target` build (owner decision Q-B), rather than indexing unrecorded.

    `layers` — ledger task **43.8**. Every named layer runs after the base's last batch, in
    order, over the sources this run's own store now records `ACTIVE` — see `_run_layers` for
    the whole loop. Composed before anything is written or deleted: `weft_cli.layers.
    UnknownLayerError` for a name `weft_cli.pipeline_catalogue.full_catalogue` does not hold
    at all, that module's own `NotALayerError`/`LayerDuplicatesBaseStageError` for one that
    resolves but cannot run as a layer, and `LayerNeedsMetadataFilterError` unless the primary
    store's own instance can evaluate a `weft_store.contract.MetadataFilter`.

    `layers_only` — ledger task **43.8**. `True` skips the base entirely — no extract, no
    `_release_reparsed_sources`, no `INDEXING`/catch-up write — and runs the layer loop over
    the sources this project already recorded. Refused by `weft_cli.commands.IndexCommand.run`
    before this function is ever called when no layer is named either way.
    """
    _validate_batch_size(batch_size)
    _require_corpus_directory(directory)
    if pipeline is not None and extractor is not None:
        raise WeftError(
            "run_index was given both 'pipeline' and 'extractor' — a named pipeline "
            "document's own 'extract' stage already names its plugin, so there is nothing "
            "for 'extractor' to narrow. Pass one or the other."
        )

    claims = claimed_extensions(registry)
    #: `"store"`, `index_specs`'s own literal id, matches the default path unchanged; the
    #: pipeline path below derives whichever id its document gave the **first** stage registered
    #: under the `NodeStore` contract — see `_store_stage_id_of`.
    store_stage_id: str | None = "store"
    #: **Every** store the document names, not just the first — carried repair `R11.4`. The two
    #: are deliberately separate: reading back and counting want the primary (one authority for
    #: change detection, one number for the operator), and *writing* the source record wants all
    #: of them, because a store holding a corpus and no record of it is what ledger 6.24 exists
    #: to prevent. See `_store_stage_ids_of`.
    store_stage_ids: tuple[str, ...] = ("store",)
    resolved_pipeline: ResolvedPipeline | None = None
    if pipeline is not None:
        # Carried repair **R10.4**: the same call `weft eval run --reuse-index` makes, so the
        # corpus identity an indexing run records and the one a reusing run records cannot
        # disagree. `accepted` is not recomputed here — `corpus_documents` already applied it.
        resolved_pipeline, specs, pipeline_refs = corpus_documents(
            directory,
            pipeline=pipeline,
            registry=registry,
            reports=reports,
            contributions=contributions,
        )
        store_stage_id = _store_stage_id_of(specs)
        store_stage_ids = _store_stage_ids_of(specs)
        #: The same set `corpus_documents` applied, re-derived from the specs it handed back —
        #: not to select the documents (it already did that) but because `_nothing_found` names
        #: it to an operator whose directory held only formats nothing claims. Deriving it from
        #: `frozenset()` instead made that message claim no extractor accepts anything.
        accepted = _accepted_extensions(
            claims, registry=registry, extractor=_extractor_name_of(specs, pipeline=pipeline)
        )
    else:
        pipeline_refs = None
        accepted = _accepted_extensions(claims, registry=registry, extractor=extractor)
        specs = None  # chosen below, once the sole claimant (or --extract) is known

    present = present_suffixes(directory)
    readable = present & accepted
    if pipeline_refs is not None:
        refs = pipeline_refs
    else:
        refs = inventory_source_refs(directory, extensions=readable)
    if not refs:
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
    target_live = await _target_live_name(runnable)
    runnable = await _bind_store_stages(runnable, target=target)
    # Before anything is written or deleted — `_release_reparsed_sources` and `_record_sources`
    # are both still ahead, in the `try` block below.
    effective_batch_size, whole_corpus_for = _batch_plan(batch_size, default_batch_size, runnable)
    embedder_instance = _embedder_instance_of(specs, runnable)
    await _claim_embedding_for_stores(
        specs, runnable, registry=registry, embedder_instance=embedder_instance, target=target
    )
    # Ledger task **9.0** — every contract a stage in this resolved `specs` already fills is
    # excluded from the ambient role set `build_index_services` would otherwise register; see
    # that function's own docstring for why this is derived from the pipeline rather than a
    # second hardcoded absence beside `NodeStore`'s own.
    filled_by_stages = tuple(spec.contract for spec in specs)
    store_for_readers = _store_instance_for_corpus_readers(specs, runnable)
    run_llm = llm if llm is not None else LLMSection()
    indexing_ctx = replace(
        ctx,
        services=await build_index_services(
            registry=registry,
            llm=run_llm,
            sink=sink if sink is not None else NullSink(),
            embedder=embedder_instance,
            store_for_revisable=store_for_readers,
            roles=roles,
            services=services,
            filled_by_stages=filled_by_stages,
            target=target,
        ),
    )

    # Ledger task **43.8** — the base's own name for a layer refusal's message; the default
    # four-stage path resolves no document at all, so it has no name of its own to give.
    base_name = pipeline if pipeline is not None else BUILT_IN_PIPELINE_NAME
    layer_runnables: list[RunnablePipeline] = []

    in_flight: BaseException | None = None
    claim_stack = AsyncExitStack()
    try:
        return await _index_claimed(
            runner,
            runnable,
            specs,
            refs,
            claim_stack=claim_stack,
            layer_runnables=layer_runnables,
            registry=registry,
            reports=reports,
            contributions=contributions,
            resolved_pipeline=resolved_pipeline,
            pipeline=pipeline,
            base_name=base_name,
            layers=layers,
            layers_only=layers_only,
            reprocess=reprocess,
            retry_failed=retry_failed,
            store_stage_id=store_stage_id,
            store_stage_ids=store_stage_ids,
            store_for_readers=store_for_readers,
            indexing_ctx=indexing_ctx,
            effective_batch_size=effective_batch_size,
            whole_corpus_for=whole_corpus_for,
            on_batch=on_batch,
            run_llm=run_llm,
            target=target,
            target_live=target_live,
        )
    except BaseException as failure:
        in_flight = failure
        raise
    finally:
        await claim_stack.aclose()
        await close_each(
            tuple(
                CloseTarget(
                    instance=stage.instance,
                    distribution=stage.distribution,
                    contract=stage.contract_name,
                    plugin=stage.plugin_name,
                    stage=stage.id,
                )
                for stage in (
                    *runnable.stages,
                    *(
                        stage
                        for layer_runnable in layer_runnables
                        for stage in layer_runnable.stages
                    ),
                )
            ),
            in_flight=in_flight,
        )


async def run_index_for(
    deps: Dependencies,
    directory: Path,
    *,
    ctx: Context,
    pipeline: str | None,
    extractor: str | None = None,
    reprocess: bool = False,
    batch_size: int | None = None,
    default_batch_size: int | None = None,
    on_batch: Callable[[BatchProgress], Awaitable[None]] | None = None,
    retry_failed: bool = False,
    target: str | None = None,
    layers: tuple[str, ...] = (),
    layers_only: bool = False,
) -> IndexResult:
    """The one production caller of `run_index` — `R19.17`.

    Every other ingest concern `run_index` takes by keyword — `contributions`, `llm`, `sink`,
    `services`, `roles` — is read off `deps` here, in one place, rather than passed by hand at
    each call site: `L8.24` fired three times before this existed, each time because one of
    those concerns was forgotten at one caller and not another (most recently, `weft eval run`
    dropped `contributions`, so a pack's contributed stage ran under `weft index` and silently
    did not under it). `tests/unit/weft_cli/test_run_index_has_one_production_caller.py` holds
    this the only production caller of `run_index`; a test may still call `run_index` directly
    with doubles.

    `default_batch_size`/`on_batch` — ledger task **43.2** — are forwarded straight through,
    unread here: whether either is given at all is `weft_cli.commands.IndexCommand.run`'s own
    decision, since it is the caller that knows which sink `deps.token_sink` is.

    `layers`/`layers_only` — ledger task **43.8** — are forwarded straight through as well:
    `weft_cli.commands.IndexCommand.run` is where `--layers` is resolved against
    `deps.index_policy.layers`, since only that caller has the parsed flag to resolve against.
    """
    return await run_index(
        directory,
        registry=deps.registry,
        ctx=ctx,
        extractor=extractor,
        embedder=deps.services.embed,
        store=deps.services.store,
        pipeline=pipeline,
        reports=deps.reports,
        contributions=deps.contributions,
        llm=deps.llm,
        sink=deps.token_sink,
        services=deps.services,
        roles=deps.roles,
        reprocess=reprocess,
        batch_size=batch_size,
        default_batch_size=default_batch_size,
        on_batch=on_batch,
        retry_failed=retry_failed,
        target=target,
        layers=layers,
        layers_only=layers_only,
    )


def corpus_documents(
    directory: Path,
    *,
    pipeline: str,
    registry: Registry,
    reports: Sequence[PackReport],
    contributions: tuple[Contribution, ...] = (),
) -> tuple[ResolvedPipeline, tuple[StageSpec, ...], tuple[SourceRef, ...]]:
    """The resolved pipeline, its specs, and the refs under `directory` it can read.

    **One derivation, and carried repair `R10.4` is why it is public.** `weft eval run --reuse-
    index` scores a query rung against a corpus that is already stored, so it needs the corpus
    *identity* without doing the ingest — and `corpus_identity` digests exactly the sorted source
    ids this returns. A second way of arriving at that set is a second way of disagreeing with
    the run that did index, and two arms that disagree about the corpus compare as incomparable,
    which is the opposite of the repair. So `run_index` below and the evaluator call this one
    function rather than each composing the same four steps.

    Nothing here runs: resolving a document and inventorying a directory listing are the whole
    of it. **Refs, not documents, since ledger task 43.1** — this path is bounded the same way
    the default four-stage path is; `weft eval run --reuse-index` only ever needed `source_id`,
    `uri` and the content hash this already carried, never the bytes.
    """
    _require_corpus_directory(directory)
    resolved, specs = _specs_from_document(
        pipeline, registry=registry, reports=reports, contributions=contributions
    )
    extractor = _extractor_name_of(specs, pipeline=pipeline)
    accepted = _accepted_extensions(
        claimed_extensions(registry), registry=registry, extractor=extractor
    )
    readable = present_suffixes(directory) & accepted
    return resolved, specs, inventory_source_refs(directory, extensions=readable)


def content_hashes_of(sources: Iterable[SourceDoc | SourceRef]) -> tuple[str, ...]:
    """Identify a corpus by its documents' bytes, so two runs can tell if they saw the same one.

    Each source's sha256 content hash, in the order given — the entries a run record's
    corpus digest is over (ledger task **16.0**), widened by **43.1** to a `SourceRef` as
    readily as a `SourceDoc`: both name the same sha256 over the same bytes, and a `SourceRef`
    already carries it without needing the bytes reread.

    Not deduplicated: two byte-identical documents are two documents, which G20 (ledger 27.1)
    settled for the node they produce and is no less true of the corpus they belong to.
    """
    return tuple(_content_hash(source) for source in sources)


def _content_hash(doc: SourceDoc | SourceRef) -> str:
    """Compute one source's content hash.

    One source's content hash, and this module's only definition of it — read by
    `SourceRecord.content_hash`, by `changes_against_records`' comparison, and by the corpus
    digest, three readers that have to agree about what "the same document" means.

    **Read off a `SourceRef` rather than re-derived, since ledger task 43.1.** A `SourceRef`
    already carries the sha256 `inventory_source_refs` stream-hashed it under, and re-hashing
    its bytes here would mean doing so up to four times over the same corpus — once from this
    function's three call sites plus `_next_attempts` — for a value already known. A `SourceDoc`
    (an already-loaded batch, or an eval path still holding real bytes) is hashed directly, on
    identical footing to before this task.
    """
    if isinstance(doc, SourceRef):
        return doc.content_hash
    return hashlib.sha256(doc.content).hexdigest()


def _specs_from_document(
    pipeline_name: str,
    *,
    registry: Registry,
    reports: Sequence[PackReport],
    contributions: tuple[Contribution, ...] = (),
) -> tuple[ResolvedPipeline, tuple[StageSpec, ...]]:
    """Resolve an ingest pipeline by name once, for both the runner and a run record.

    `pipeline_name` resolved into a `ResolvedPipeline` and the `StageSpec` list `Runner.
    resolve` consumes.

    `contributions` — task **5.3a** (`S8`) — reaches both `contracts_for` and `resolve()`
    below, exactly as `weft_cli.pipeline_commands._resolved_or_refuse` and `weft_cli.
    route_ask._run_pipeline` already receive it: one caller (`weft_engine.registry_bootstrap.
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
        document, registry=registry, parents=catalogue, reports=reports, contributions=contributions
    )
    resolved = resolve(
        document,
        registry=registry,
        contracts=contracts,
        parents=catalogue,
        contributions=contributions,
    )
    return resolved, to_specs(resolved, registry=registry, reports=reports)


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


def _embedder_instance_of(
    specs: Sequence[StageSpec], runnable: RunnablePipeline
) -> Embedder | None:
    """The **built instance** of the one stage registered under `Embedder`, or `None` — 8.10.

    Matched by stage `id` rather than by position, so it does not depend on `Runner.resolve`
    preserving the order of `specs`. The third of this module's three "which stage is the X"
    walks, beside `_extractor_name_of` and `_store_stage_id_of`, and the only one that returns
    an object rather than a name: `weft_engine.run_services.build_index_services` takes the
    instance precisely so a run has one embedder rather than two that happen to agree — see
    that function's own docstring for why resolving `[services] embed` a second time here
    would be a silent defect on a `--pipeline` run.

    **`None` rather than a refusal for a document with no embed stage**, deliberately.
    `index_specs` writes one unconditionally, so the default path always has it; a document
    that omits it is unusual and this function is not the place to decide it is wrong —
    refusing here would change what such a document does today, which is outside task 8.10's
    scope. Registering nothing is the honest translation: a stage that then reaches for
    `Embedder` gets `weft_kernel.context.UnresolvedServiceError` naming what the run does
    offer, which is requirement 5's answer at the seam that already gives it, and a document
    whose stages never ask is unaffected.
    """
    by_id = {stage.id: stage.instance for stage in runnable.stages}
    for spec in specs:
        if spec.contract is Embedder and spec.id in by_id:
            return cast(Embedder, by_id[spec.id])
    return None


async def _target_live_name(runnable: RunnablePipeline) -> str | None:
    """Read the store's live target name right now.

    The store's own live target name, right now — ledger task **34.6**, widened by **34.10**
    to run unconditionally: `IndexResult.target` needs the live name whether or not `--target`
    was given, and so does the post-run check for whether it moved.

    Read off the **first** `NodeStore` stage's own instance — a bound handle still answers
    `target_catalogue()` (it is a whole-store fact, not one scoped to the target it is bound to),
    so this reads the same way called before `run_index` binds any stage to `target` (`what was
    live when this run opened`) or after (`what is live now that it finished`). `None` when the
    first store stage does not satisfy `TargetHolding` — `bind_store` is what refuses a malformed
    `--target`, by name; this helper only informs a render line and the 34.10 check — or when
    this pipeline has no `NodeStore` stage at all.
    """
    for stage in runnable.stages:
        if stage.contract_name != NodeStore.__name__:
            continue
        if isinstance(stage.instance, TargetHolding):
            catalogue = await stage.instance.target_catalogue()
            return catalogue.live
        return None
    return None


async def _target_written(
    runnable: RunnablePipeline, *, target: str | None, target_live: str | None
) -> tuple[str | None, bool, str | None]:
    """Report the target this run wrote and how liveness moved.

    `(target this run wrote, target_stopped_being_live, target_now_live)` — ledger task
    **34.10**. Lifted out of `run_index` so this branch stays out of that function's own
    complexity budget, `_bind_store_stages`' own footing.

    The target written is `target` if one was given, else `target_live` — what "finished into
    the target it opened against" means for the common, untargeted case. `target_stopped_being_
    live` is read a second time only then, never for an explicit `--target` build: a crash
    between two participants is ledger **34.11**'s own concern, elsewhere; this is one store's
    own pointer, before and after this run.
    """
    written = target if target is not None else target_live
    if target is not None or target_live is None:
        return written, False, None
    live_now = await _target_live_name(runnable)
    if live_now is None or live_now == target_live:
        return written, False, None
    return written, True, live_now


async def _bind_store_stages(runnable: RunnablePipeline, *, target: str | None) -> RunnablePipeline:
    """`runnable`, with every `NodeStore` stage's instance bound to `target` — ledger task **34.6**.

    `None` returns `runnable` unchanged, never touching a stage's instance: the common, untargeted
    case must build and bind nothing beyond what already ran. Lifted out of `run_index` so the
    branch this adds stays out of that function's own complexity budget.
    """
    if target is None:
        return runnable
    # `list(runnable.stages)`, not `[]` — an empty literal carries no element type for pyright
    # to infer, and `weft_kernel.runner`'s own `_ResolvedStage` is private to that distribution,
    # not a name this one spells; seeding from the tuple already typed gives every element its
    # type for free.
    bound_stages = list(runnable.stages)
    for index, stage in enumerate(bound_stages):
        if stage.contract_name == NodeStore.__name__:
            bound = await bind_store(stage.instance, target, store_name=stage.plugin_name)
            bound_stages[index] = replace(stage, instance=bound)
    return replace(runnable, stages=tuple(bound_stages))


async def _claim_embedding_for_stores(
    specs: Sequence[StageSpec],
    runnable: RunnablePipeline,
    *,
    registry: Registry,
    embedder_instance: Embedder | None,
    target: str | None = None,
) -> None:
    """Let a later query detect it was embedded with a different model than the store holds.

    Record `embedder_instance`'s identity against every store stage this document writes
    through — ledger task **34.4**. A document with no embed stage claims nothing —
    `embedder_instance` is `None` on `index_specs`' own footing, `_embedder_instance_of`'s
    docstring above.

    **`target`, ledger task 34.6.** `None` passes `required=False`, unchanged: an embedder that
    cannot state one keeps indexing unrecorded rather than refusing plain, untargeted ingest
    (Q-B). Given a name, `required=True`: an embedder that cannot state an identity is refused
    for a `--target` build, since there would be nothing to check a later query against.
    """
    if embedder_instance is None:
        return
    embed_spec = next((spec for spec in specs if spec.contract is Embedder), None)
    if embed_spec is None:
        return
    plugin = embed_spec.name
    identity = await embedding_identity_of(
        embedder_instance, plugin=plugin, distribution=registry.entry(Embedder, plugin).distribution
    )
    by_id = {stage.id: stage.instance for stage in runnable.stages}
    for store_id in _store_stage_ids_of(tuple(specs)):
        store_instance = by_id.get(store_id)
        if store_instance is not None:
            await claim_embedding_for_write(
                store_instance,
                identity,
                plugin=plugin,
                required=target is not None,
                target=target,
            )


def _store_instance_for_corpus_readers(
    specs: Sequence[StageSpec], runnable: RunnablePipeline
) -> NodeStore | None:
    """The built store instance, when the document also has a corpus-reading stage.

    The **built instance** of this document's store stage, but only when the document also
    contains a stage whose contract reads the corpus — grilling session **G16**, ledger task
    10.14. `Revisable` is the first-party one; carried repair **R43.20** reads the contract's own
    `reads_corpus` declaration instead of `Revisable`'s identity, so a third party's contract
    qualifies with no edit here.

    `_embedder_instance_of`'s exact shape one contract over, and that is the whole design:
    `build_index_services` registers the embedder the *stage* built rather than resolving
    `[services] embed` a second time, "precisely so a run has one embedder rather than two that
    happen to agree". A store reached this way is the same object the `store` stage writes
    through — one store, not two — which is what answers `build_index_services`' own stated
    reason for excluding an ambient `NodeStore`: *"two paths to the same store with no ordering
    between them."* There are not two paths to two stores; there is one store, and the ordering
    is the `Revisable`'s declared position in the resolved document.

    **Why the `Revisable` condition rather than registering a store unconditionally.** Not
    because of the sentence above — that argument is answered by sharing the instance — but
    because of G15's *Read* face: if every ingest stage could reach the corpus, `10.5`'s
    property would stop being a fact about a **kind** of stage and become a per-plugin habit
    with nothing to key a check on. The contract is what gates it, so a document earns an
    ambient store by declaring a participant that needs one, and an ordinary ingest document
    is unchanged — it still gets exactly the four services `build_index_services` documents.

    **This does not contradict `filled_by_stages`,** which is the mechanism that keeps a
    *role*-selected store from being registered beside a store stage. That mechanism exists to
    stop a **second instance** arriving from configuration; this function supplies the **first
    instance**, the stage's own. The two answer opposite questions and both remain true.

    `None` when either half is absent — no `Revisable`, or no stage under `NodeStore` — on
    `_embedder_instance_of`'s own footing: a stage that then reaches for `NodeStore` gets
    `weft_kernel.context.UnresolvedServiceError` naming what the run does offer, which is
    requirement 5 answered at the seam that already gives it.

    **Found by running the binary, not by a test** (`docs/internal/lessons.md` `L10.40`):
    `Revisable`, `NodeSupersedable` and `adrap` all shipped green over a `ctx.require(NodeStore)`
    call that could not resolve on this path.
    """
    if not any(getattr(spec.contract, "reads_corpus", False) is True for spec in specs):
        return None
    by_id = {stage.id: stage.instance for stage in runnable.stages}
    for spec in specs:
        if spec.contract is NodeStore and spec.id in by_id:
            return cast(NodeStore, by_id[spec.id])
    return None


def _store_stage_id_of(specs: tuple[StageSpec, ...]) -> str | None:
    """Pick the one store whose count and source records a run reports and diffs against.

    The id of the **first** stage in `specs` registered under the `NodeStore` contract, or
    `None` if no stage is.

    Not mandatory the way `_extractor_name_of` is: a document that stores nowhere still
    resolves and runs, it simply has nothing for `_stored_count` to report — the identical
    "`None` only defensively" spirit `IndexResult.stored_count`'s own docstring already
    states for a store with no callable `count`.

    **This said "the one stage" until carried repair `R11.4`, and a document falsified it.**
    `index-with-graph` (ledger 11.5) names two stores, and every rung derived from it names two
    or more; `L6.15`'s rule is that a claim quantifying over documents anyone may write is
    checked against the documents, not against the sentence. What survives the correction is
    that *first* is the right answer for the two callers left here — `_stored_count` reports one
    number to an operator, and summing two stores holding the same nodes would double it, while
    `_recorded_sources` needs one authority for change detection rather than a merge of several.
    Writing the record is the caller that needed all of them: `_store_stage_ids_of`, below.
    """
    for spec in specs:
        if spec.contract is NodeStore:
            return spec.id
    return None


def _store_stage_ids_of(specs: tuple[StageSpec, ...]) -> tuple[str, ...]:
    """Every stage id in `specs` registered under the `NodeStore` contract, in document order.

    Carried repair **R11.4**. `02` §4's *"sits beside the vector store"* is a document naming
    two stores and handing each the identical batch, and from `index-with-graph` onward that is
    a shipped arrangement rather than a hypothetical one. A source record written to only the
    first of them leaves the second holding a corpus it cannot enumerate — `list_sources()`
    answering `()` about nodes it is storing, which is the state ledger 6.24 repaired for the
    one-store case and which a second store silently reopened.

    Empty when no stage stores, which `_record_sources` treats exactly as `None` was treated
    before: nothing to record, and no error, because a document that stores nowhere is a
    document that runs.
    """
    return tuple(spec.id for spec in specs if spec.contract is NodeStore)


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


def _require_corpus_directory(directory: Path) -> None:
    """Refuse a corpus path that is not a directory, saying which of the two ways it is not.

    **Called from both walkers, and that is the point rather than belt-and-braces.** `weft
    index` reaches the walk through `run_index`; `weft eval run --reuse-index` reaches it
    through `corpus_documents` without passing `run_index` at all. A guard at only the first
    would repair one command and leave its neighbour answering a typo with a clean exit — the
    shape `L8.24` records costing Phase 8 twice in one phase, once for `llm=` and once for an
    optional parameter's other call site.

    An empty directory is not an error and does not reach either branch: it is a real
    directory, `run_index`'s own docstring argues why that is a fact rather than a failure, and
    `_nothing_found` is what answers it.
    """
    if not directory.exists():
        raise CorpusPathNotFoundError(
            f"there is no '{directory}' to index. Nothing was read and nothing was stored — "
            f"check the path, then run 'weft index <directory>' again."
        )
    if not directory.is_dir():
        raise CorpusPathNotADirectoryError(
            f"'{directory}' is a file, and 'weft index' reads a directory. Index the directory "
            f"holding it — 'weft index {directory.parent}' — and every file under it whose "
            f"format an installed extractor claims is read."
        )


async def _one(batch: tuple[SourceDoc, ...]) -> AsyncIterator[object]:
    yield batch


async def _rerun_batch_singly(
    runner: Runner,
    runnable: RunnablePipeline,
    batch: Sequence[SourceDoc],
    indexing_ctx: Context,
    *,
    store_stage_ids: Sequence[str],
    previous: Mapping[SourceId, SourceRecord],
    identity: str,
    pipeline: str | None,
) -> tuple[list[RunSummary], int, int]:
    """Re-run a failed multi-document batch one document at a time.

    R43.1 — a batch of more than one document that returned `Failed` is re-run alone, one
    document at a time, so only a document that fails alone is recorded `FAILED`; a service
    fault still raises through `_record_batch_failure` for that one document and stops the run.
    """
    summaries: list[RunSummary] = []
    indexed = 0
    failed = 0
    for doc in batch:
        with recording() as doc_scope:
            try:
                doc_summary = await runner.run(runnable, _one((doc,)), indexing_ctx)
            except WeftError as exc:
                await _record_batch_failure(
                    runnable,
                    store_stage_ids=store_stage_ids,
                    batch=(doc,),
                    previous=previous,
                    identity=identity,
                    pipeline=pipeline,
                    error_type=type(exc).__name__,
                    stage=exc.stage,
                    message=str(exc),
                )
                raise
        summaries.append(doc_summary)
        if doc_summary.failed == 0:
            await _record_sources(
                runnable,
                store_stage_ids=store_stage_ids,
                docs=(doc,),
                pipeline=pipeline,
                identity=identity,
            )
            indexed += 1
        else:
            message = "; ".join(doc_summary.failed_reasons) or "the batch failed"
            await _record_batch_failure(
                runnable,
                store_stage_ids=store_stage_ids,
                batch=(doc,),
                previous=previous,
                identity=identity,
                pipeline=pipeline,
                error_type="Failed",
                stage=_failing_stage(doc_scope.records),
                message=message,
            )
            failed += 1
    return summaries, indexed, failed


def _summed(summaries: Sequence[RunSummary]) -> RunSummary:
    """One `RunSummary` over per-batch runs, counts and reasons in batch order — task 38.14."""
    return RunSummary(
        produced=sum(summary.produced for summary in summaries),
        nothing_to_produce=sum(summary.nothing_to_produce for summary in summaries),
        failed=sum(summary.failed for summary in summaries),
        nothing_to_produce_reasons=tuple(
            reason for summary in summaries for reason in summary.nothing_to_produce_reasons
        ),
        failed_reasons=tuple(reason for summary in summaries for reason in summary.failed_reasons),
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


def _payload_indexes(runnable: RunnablePipeline, *, store_stage_id: str | None) -> tuple[str, ...]:
    """What the store ensured, asked of the **built instance** — ledger task **31.14**.

    `getattr` rather than a `NodeStore` member, which is the shape `31.8` established for reading
    a store's index kind: declared, never required. A store that does not define it reports a
    stated absence and is never refused over a question about reporting, so this needs no Protocol
    member and no `STORE_CONTRACT_VERSION` move.

    Asked of the instance rather than of settings, because the report is a claim about what *this
    run* wrote. `31.1`'s guarantee is that Weft's own filter is served by an index created before
    the first point; reading the settings would restate the intention, and reading the store
    reports the thing that happened.
    """
    if store_stage_id is None:
        return ()
    for stage in runnable.stages:
        if stage.id != store_stage_id:
            continue
        declared: tuple[str, ...] = getattr(stage.instance, "payload_index_fields", ())
        return declared
    return ()


async def _degraded_expansions(
    runnable: RunnablePipeline,
    *,
    resolved_pipeline: ResolvedPipeline | None,
    store_stage_id: str | None,
) -> int | None:
    """Count stored chunks carrying `ExpansionDegraded`, or `None` when unknowable.

    How many stored chunks carry `ExpansionDegraded`, or `None` when this run cannot say —
    repair **R38.13**.

    `None` on the default four-stage path, honestly: `index_specs` resolves no
    `ResolvedPipeline` at all, so there is no document to ask whether an `Expander` stage
    ran. On a `--pipeline` run, `None` unless the document names an `Expander` stage *and*
    the built store for this run is a `weft_store.contract.MetadataFilter` — a store that
    cannot evaluate a filter is not asked, on `count_degraded_expansions`'s own footing.
    """
    if resolved_pipeline is None or store_stage_id is None:
        return None
    if not any(stage.contract == Expander.__name__ for stage in resolved_pipeline.stages):
        return None
    for stage in runnable.stages:
        if stage.id != store_stage_id:
            continue
        if isinstance(stage.instance, MetadataFilter):
            return await count_degraded_expansions(stage.instance)
        return None
    return None


async def _release_reparsed_sources(
    runnable: RunnablePipeline,
    *,
    store_stage_ids: Sequence[str],
    changes: Mapping[SourceId, SourceChange],
    corpus_layers: frozenset[str],
) -> tuple[str, ...]:
    """Keep an old parse's nodes from staying retrievable beside a document's new parse.

    Release what a re-parsed document's previous parse left, before the new one runs —
    ledger task **27.2**, and `L9.37`'s half of Phase 27's one cause.

    A node id is a content digest, so a document whose bytes or whose pipeline moved produces a
    wholly new set of ids: `ON CONFLICT (id)` never fires, and without this the two parses sit
    in the store together, both retrievable, under one `SourceRecord` that records only the
    later. Measured at Phase 11's exit as 23 nodes becoming 42 over four runs (`L11.46`).

    **`CONTENT_CHANGED`, `PIPELINE_CHANGED`, `INCOMPLETE` and `RETRIED`.** `INCOMPLETE` joined at
    repair **R38.14**: an interrupted run leaves its sources `INDEXING` with whatever nodes it
    wrote, and a model-written node gets a new id each run, so `38.6`'s next arm retrieved 22,463
    of them. `RETRIED` joined at ledger **36.2**, on the identical footing: a source `36.1` failed
    partway may have written some of a batch's nodes before the stage that lost it, and a retry is
    a fresh attempt, not a continuation of the old one. `NEW`
    has nothing to release, and
    `UNCHANGED` must not be touched: `02` §1 makes idempotent re-indexing the point of
    content-addressed ids, and releasing there would delete and rewrite an entire corpus to
    arrive back where it started. `FAILED` — skipped, not retried — must not be touched either:
    its nodes were already released the moment `36.1` recorded the failure (see
    `_record_batch_failure`), and releasing an already-empty claim a second time here would be
    silent, harmless, and exactly the kind of redundant call this module elsewhere refuses to
    write.

    **`delete_source` rather than a new contract method**, which is not a shortcut. `27.1` made
    it release *this* document's claim on a node and keep the node when another document still
    produces one — so a re-parsed document that shares a passage with an untouched one narrows
    it rather than taking it away, which is exactly what this needs and what a
    delete-by-source would get wrong.

    **Before the run, and this is the opposite of `supersede`'s ordering on purpose.** `02` §1
    has `supersede` write before it deletes, so an interruption leaves a duplicate `reconcile`
    can find rather than a hole nothing can. The hazards are not comparable: a superseded node's
    `BlobRef` points at bytes gone from everywhere, while a document released and not re-indexed
    is still on disk with no `SourceRecord`, so the next `weft index` over the same directory
    sees it as `NEW` and rebuilds it. Releasing afterwards would need the set of ids this pass
    produced, and `RunSummary` carries counts.

    A store with no callable `delete_source` is skipped rather than fatal, the footing
    `_record_sources` already stands on for `put_source`: refusing the run because one store of
    several keeps no deletion path would make an optional capability mandatory.
    """
    stale = tuple(
        source
        for source, change in changes.items()
        if change
        in (
            SourceChange.CONTENT_CHANGED,
            SourceChange.PIPELINE_CHANGED,
            SourceChange.INCOMPLETE,
            SourceChange.RETRIED,
        )
    )
    return await _release_sources(
        runnable, store_stage_ids=store_stage_ids, sources=stale, corpus_layers=corpus_layers
    )


async def _release_sources(
    runnable: RunnablePipeline,
    *,
    store_stage_ids: Sequence[str],
    sources: Iterable[SourceId],
    corpus_layers: frozenset[str] = frozenset(),
) -> tuple[str, ...]:
    """`delete_source(source)` for every id in `sources`, on every store stage that has one.

    The mechanical half of `_release_reparsed_sources`, factored out so ledger **36.1**'s own
    failure path can release a batch's partial nodes the identical way without going through
    `changes_against_records`'s vocabulary to name a set of ids it already has in hand.

    **R43.41** — `delete_source` removes every summary naming a released source, so first, on
    every store, each of `corpus_layers` a released source held `ACTIVE` is demoted to `STALE`
    on every other source: R43.33's marked-before-holed, as `weft delete` does. Returns the
    names demoted. The failed-batch release passes no `corpus_layers`: its sources were
    already released and rewritten `INDEXING` with no layers.
    """
    sources = tuple(sources)
    if not sources:
        return ()
    wanted = set(store_stage_ids)
    stages = [stage for stage in runnable.stages if stage.id in wanted]
    demoted: set[str] = set()
    if corpus_layers:
        released = frozenset(sources)
        for stage in stages:
            demoted.update(await _demote_released(stage.instance, released, corpus_layers))
    for stage in stages:
        delete_source = _delete_source_of(stage.instance)
        if delete_source is None:
            continue
        for source in sources:
            await delete_source(source)
    return tuple(sorted(demoted))


async def _demote_released(
    instance: object, released: frozenset[SourceId], corpus_layers: frozenset[str]
) -> tuple[str, ...]:
    """One store's half of `_release_sources`'s demotion.

    A store with no callable `list_sources`/`put_source` is skipped, as `_record_sources` skips one
    without `put_source`.
    """
    list_sources = _list_sources_of(instance)
    put_source = _put_source_of(instance)
    if list_sources is None or put_source is None:
        return ()
    held = frozenset(
        layer.name
        for record in await list_sources()
        if record.id in released
        for layer in record.layers
        if layer.name in corpus_layers and layer.status is LayerStatus.ACTIVE
    )
    if not held:
        return ()
    return await demote_layer_records(list_sources, put_source, held, released)


def _delete_source_of(instance: object) -> Callable[[SourceId], Awaitable[object]] | None:
    """The instance's `delete_source` if it has a callable one, else `None`.

    `instance.delete_source`, if it has one and it is callable — the same defensive shape as
    `_put_source_of`, and on the same contract: `delete_source` **is** published on `NodeStore`,
    so this is a guard against a stage that only structurally resembles one, never a licence for
    a store to omit it.
    """
    found = getattr(instance, "delete_source", None)
    if found is None or not callable(found):
        return None
    return cast(Callable[[SourceId], Awaitable[object]], found)


def batch_membership_dependent_stages(runnable: RunnablePipeline) -> tuple[str, ...]:
    """The plugin names in `runnable` whose output depends on which nodes shared their call.

    Ledger task **17.2**, and the fact `17.3`'s refusal is built on. `Runner.run` puts each batch
    through the whole stage list independently, so a stage that **clusters** computes a different
    thing when the batch size changes — and `raptor` is one: it reads no store (G15) and clusters
    over the payload it was handed, which `01`:1012 records as *batch-wide, not corpus-wide*.

    **Declared, not derived, which is this tree's exception rather than its rule.** Whether an
    output depends on batch membership is not computable from a class's shape; only the author of
    the algorithm knows it. So it is read off the constructed instance the way `requires`,
    `provides` and `lifetime` already are — `weft_kernel.runner`'s own *"conventions a plugin may
    set, read defensively"* — and never at registration, because what matters is the instance a
    resolved pipeline actually holds.

    **Silence means no**, unlike `destroys`, where a contract refuses a plugin that states
    nothing. The population here is every stage anybody has ever written, almost all of them
    batch-invariant and none able to declare anything retroactively; a safe default that refused
    them would refuse the whole world to protect one plugin. What `17.3` protects is the shipped
    ladder, where the stage that needs this is known by name.

    The **plugin** name rather than the stage id, because the refusal has to name something an
    operator can look up: an id is whatever the document's author called the position.
    """
    return tuple(
        stage.plugin_name
        for stage in runnable.stages
        if getattr(stage.instance, "depends_on_batch_membership", False)
    )


async def _recorded_sources(
    runnable: RunnablePipeline, *, store_stage_id: str | None
) -> Mapping[SourceId, SourceRecord]:
    """Every `SourceRecord` the run's own store already holds, by id — task **9.17**.

    Found the same way `_record_sources` and `_stored_count` find the store: by the stage id
    already derived from the resolved specs, never by the literal `"store"`. A store with no
    callable `list_sources` answers `{}`, and `changes_against_records` then reports every source
    as `NEW` — which is honest for a store that cannot say otherwise, and is the same defensive
    footing `_stored_count`'s own `None` sits on.
    """
    if store_stage_id is None:
        return {}
    for stage in runnable.stages:
        if stage.id != store_stage_id:
            continue
        list_sources = getattr(stage.instance, "list_sources", None)
        if list_sources is None:
            return {}
        return {record.id: record for record in await list_sources()}
    return {}


class SourceChange(StrEnum):
    """What a re-index found about one source, relative to what a `SourceRecord` already said.

    Ledger task **9.17**. `SourceRecord` has carried `content_hash` since G4 and `pipeline` since
    task 6.24, and `02` §1 states their purpose — *"`pipeline` is what lets `weft index` say
    'already indexed, by a different pipeline'"*. Measured 2026-09-06, **nothing compared either**:
    every use in `packages/` was a write, a read-back or a copy (`docs/internal/lessons.md`
    `L9.37`). This enum is the vocabulary of the comparison that was missing.
    """

    #: No `SourceRecord` exists for this source. The first index of anything, and the state every
    #: corpus indexed before task 9.17 is in for its pipeline identity.
    NEW = "new"
    #: Same bytes, same pipeline identity. The common re-index, and the one worth saying least
    #: about.
    UNCHANGED = "unchanged"
    #: The document itself moved. Reported in preference to `PIPELINE_CHANGED` when both did,
    #: because it is the fact an operator can act on — see `changes_against_records`.
    CONTENT_CHANGED = "content-changed"
    #: The bytes are identical and the pipeline that read them is not: a different parser, or the
    #: same parser and a different model. 9.17's own case, and the one that was invisible.
    PIPELINE_CHANGED = "pipeline-changed"
    #: The record this source's last run left is not `SourceStatus.ACTIVE` — ledger task **17.1**.
    #: `_record_sources` now writes `SourceStatus.INDEXING` before a run and `ACTIVE` after, so a
    #: run killed between the two leaves the record in that state (or, for a source mid-deletion,
    #: `DELETING`). Neither status can say what the store currently holds for this source, so a
    #: match on `content_hash` or `pipeline_identity` against it is not evidence of anything —
    #: this is reported ahead of both comparisons, never instead of one that ran.
    INCOMPLETE = "incomplete"
    #: The record this source's last run left is `SourceStatus.FAILED`, its bytes and pipeline
    #: identity both still match it, and `retry_failed` was not given — ledger **36.2**. Skipped
    #: like `UNCHANGED`, but the record is left exactly as `36.1` wrote it rather than rewritten.
    FAILED = "failed"
    #: The record above, with `retry_failed` given: work, released before the attempt like an
    #: `INCOMPLETE` source — ledger **36.2**.
    RETRIED = "retried"


def changes_against_records(
    docs: Sequence[SourceDoc | SourceRef],
    records: Mapping[SourceId, SourceRecord],
    *,
    identity: str,
    retry_failed: bool = False,
) -> Mapping[SourceId, SourceChange]:
    """What re-indexing `docs` under `identity` changes, per source — task **9.17**.

    Pure and synchronous: the caller fetches the records, this decides what they mean. Keyed on
    the docs this run actually saw, so a source elsewhere in the corpus is not reported — `weft
    index` reports on what it indexed.

    **A record whose `status` is not `SourceStatus.ACTIVE` reports `INCOMPLETE`, checked first —
    ledger task 17.1.** `_record_sources` now writes `SourceStatus.INDEXING` before a run and
    `ACTIVE` after, so a run killed midway leaves the interrupted document's record in that state
    (or `DELETING`, for a source mid-deletion). An interrupted document's bytes and pipeline
    identity very often still match that stale record — that is exactly what makes it dangerous:
    a match against a comparison nobody finished is not evidence the store holds anything
    complete, so this check runs before `content_hash` and before `pipeline_identity` can even be
    asked.

    **`FAILED` is checked before that, ledger 36.2, on the identical footing.** A source `36.1`
    left `FAILED` is not `ACTIVE` either, but it is a *finished* attempt that did not succeed,
    never an interrupted one — so it gets its own report rather than folding into `INCOMPLETE`,
    and its own comparison: bytes or identity moving since the failure is still the operator-
    actionable fact `CONTENT_CHANGED`/`PIPELINE_CHANGED` already are, checked first; only when
    neither moved does whether `retry_failed` was given decide `RETRIED` (work) from `FAILED`
    (skipped, record untouched).

    **An empty `pipeline_identity` on a stored record reports `PIPELINE_CHANGED`, not
    `UNCHANGED`.** Every record written before task 9.17 has one, and it is the *absence of
    evidence* rather than evidence of sameness; `02` §1's own rule is that an empty answer is never
    a fact about the world. Claiming `UNCHANGED` there would claim a comparison nobody made.

    **When both the bytes and the pipeline moved, the bytes are reported.** The document is
    re-parsed either way, so the useful half is the one an operator can act on — telling them the
    pipeline changed would send them looking for a configuration difference that is not the
    interesting fact.

    **What this does not do, stated so nobody infers it.** It reports; it removes nothing. A
    re-parse produces *different* node ids — ids are content digests — so `ON CONFLICT (id)` never
    fires and the old nodes stay beside the new ones, retrievable. That is `L9.37`'s finding and it
    owes a task of its own; 9.17's property is visibility, and quietly widening it here would be a
    deletion on the ingest path that nobody argued for.
    """
    return {
        doc.source_id: _change_of(
            doc, records.get(doc.source_id), identity=identity, retry_failed=retry_failed
        )
        for doc in docs
    }


def _change_of(
    doc: SourceDoc | SourceRef,
    record: SourceRecord | None,
    *,
    identity: str,
    retry_failed: bool,
) -> SourceChange:
    """What re-indexing one source under `identity` changes, against its last `record`."""
    if record is None:
        return SourceChange.NEW
    if record.status is SourceStatus.FAILED:
        if record.content_hash != _content_hash(doc):
            return SourceChange.CONTENT_CHANGED
        if record.pipeline_identity != identity:
            return SourceChange.PIPELINE_CHANGED
        return SourceChange.RETRIED if retry_failed else SourceChange.FAILED
    if record.status is not SourceStatus.ACTIVE:
        return SourceChange.INCOMPLETE
    if record.content_hash != _content_hash(doc):
        return SourceChange.CONTENT_CHANGED
    if record.pipeline_identity != identity:
        return SourceChange.PIPELINE_CHANGED
    return SourceChange.UNCHANGED


async def _record_sources(
    runnable: RunnablePipeline,
    *,
    store_stage_ids: Sequence[str],
    docs: Sequence[SourceDoc | SourceRef],
    pipeline: str | None,
    identity: str = "",
    status: SourceStatus = SourceStatus.ACTIVE,
    failures: Mapping[SourceId, SourceFailure] | None = None,
    changes: Mapping[SourceId, SourceChange] | None = None,
    previous: Mapping[SourceId, SourceRecord] | None = None,
    demoted: frozenset[str] = frozenset(),
) -> None:
    """Record one `SourceRecord` per indexed `SourceDoc` in every store written to.

    One `SourceRecord` per `SourceDoc` this run indexed, in **every** store it was written
    to — ledger task **6.24**'s repair of the defect `02` §1 documents, widened by carried
    repair **R11.4**.

    **`changes`/`previous`, ledger task 43.8.** Both `None` at every call site but
    `run_index`'s own catch-up write, which is the only one whose `docs` ever include a source
    this run left `SourceChange.UNCHANGED` — every other call writes only `work`, which
    excludes `UNCHANGED` by construction. A doc whose `changes` entry is `UNCHANGED` carries
    forward whatever `previous` already recorded for it under `layers`; every other doc — a
    reparse, a fresh source, one this run could not compare — writes `layers=()`, since the
    base re-parsed it and a layer built over the old nodes has nothing left to enrich.

    **`failures`, ledger 36.1.** `None` for every `status` but `SourceStatus.FAILED`, on
    `SourceRecord.failure`'s own rule: an `ACTIVE` write carries `failure=None` regardless of
    what `failures` holds, because a source that just succeeded owes nothing to a mapping built
    for the run's failed batch. A doc in `docs` with no entry in `failures` writes `failure=None`
    too — `_record_batch_failure` builds one entry per doc in the batch it calls this for, so
    the only way to reach this function with a `FAILED` status and a gap is a caller this module
    does not have.

    **`status`, ledger task 17.1 — `delete_source`'s own tombstone shape, applied to the other
    direction.** `run_index` calls this function twice: once for `work` (the documents this run
    is *about* to process) with `status=SourceStatus.INDEXING`, before `runner.run`, and once
    more for the full `docs` list at its default, `SourceStatus.ACTIVE`, after `runner.run`
    returns. A run killed between the two calls therefore leaves the interrupted documents'
    records saying `INDEXING` rather than either lying `ACTIVE` (the previous run's stale record)
    or not existing at all — the two states `changes_against_records` could not tell apart from
    a document nobody had ever touched. Nothing here catches what `runner.run` raises: the
    pre-run write already happened, and that write *is* the mechanism, not a value this function
    reacts to failing.

    6.24's own finding: nothing on the ingest path ever called `put_source`, so
    `list_sources()` answered `()` after a real `weft index` and a `reconcile --mode repair`
    pass built on it deleted a corpus it had no record of just writing.

    **R11.4 is that finding a second time, one store over.** This took a single
    `store_stage_id` and stopped at the first match, which was every document in the tree until
    `index-with-graph` (ledger 11.5) named two stores and handed each the identical batch.
    From that commit the graph store's `put_source` was never called on any ingest run: its
    nodes were written and its ledger was not. Measured through the shipped binary on
    2026-09-09 against a real corpus, with 2,385 tests green — the doubles in the unit suite
    answer a question the running system could not, which is this module's own recurring
    lesson (`docs/internal/lessons.md` L6.14).

    Found the same way `_stored_count` finds the store: by stage ids `_store_stage_ids_of`
    derived from the resolved specs' own `contract`, never by the literal `"store"` id — a
    `--pipeline` document owes this module no naming convention. `content_hash` is over
    `doc.content` itself, because `02` §1's purpose for the field is change detection, which a
    hash of anything else could not serve. `pipeline` is `run_index`'s own parameter — the
    name the caller gave, not a value re-derived from `resolved_pipeline` — falling back to
    `BUILT_IN_PIPELINE_NAME` on the default four-stage path, which resolves no
    `ResolvedPipeline` at all and so has no name of its own to read.

    **One `indexed_at` for the whole run, shared across stores**, so two stores never disagree
    by microseconds about when the same document was indexed — a difference nothing could
    interpret and a comparison could act on.

    A store with no callable `put_source` is skipped rather than fatal, and only that one: it is
    a fact about that backend, and refusing the run because one store of several keeps no ledger
    would make an optional capability mandatory. Otherwise this raises whatever `put_source`
    raises — a source that was indexed and not recorded is the exact state 6.24 exists to end,
    so a failure is not caught and continued past.
    """
    wanted = set(store_stage_ids)
    if not wanted:
        return
    name = pipeline if pipeline is not None else BUILT_IN_PIPELINE_NAME
    indexed_at = datetime.now(UTC)
    for stage in runnable.stages:
        if stage.id not in wanted:
            continue
        put_source = _put_source_of(stage.instance)
        if put_source is None:
            continue
        for doc in docs:
            await put_source(
                SourceRecord(
                    id=doc.source_id,
                    uri=doc.uri,
                    content_hash=_content_hash(doc),
                    indexed_at=indexed_at,
                    pipeline=name,
                    pipeline_identity=identity,
                    status=status,
                    failure=(failures.get(doc.source_id) if failures is not None else None),
                    layers=_carried_layers(
                        doc.source_id, changes=changes, previous=previous, demoted=demoted
                    ),
                )
            )


def _carried_layers(
    source_id: SourceId,
    *,
    changes: Mapping[SourceId, SourceChange] | None,
    previous: Mapping[SourceId, SourceRecord] | None,
    demoted: frozenset[str] = frozenset(),
) -> tuple[LayerRecord, ...]:
    """The `layers` a `_record_sources` write should carry forward — ledger task **43.8**.

    `()` unless this source's own `changes` entry is `SourceChange.UNCHANGED`: the base did
    not re-parse it, so whatever layer this project already built over its nodes is still
    good. Any other change — a reparse, a fresh source, one this run could not compare —
    writes `()`, because the base produced a wholly new set of node ids and a layer recorded
    against the old ones has nothing left to enrich. Under `--reprocess` no source reaches this
    at all: every ref is `work`, and a source with layers was released with them (R43.28).

    `demoted` (**R43.41**) is what this run's releases marked `STALE` after `previous` was read,
    so an `ACTIVE` entry named there is carried `STALE` rather than written back over the mark.
    """
    if changes is None or previous is None or changes.get(source_id) is not SourceChange.UNCHANGED:
        return ()
    record = previous.get(source_id)
    if record is None:
        return ()
    return tuple(
        layer.model_copy(update={"status": LayerStatus.STALE})
        if layer.name in demoted and layer.status is LayerStatus.ACTIVE
        else layer
        for layer in record.layers
    )


async def _record_batch_failure(
    runnable: RunnablePipeline,
    *,
    store_stage_ids: Sequence[str],
    batch: Sequence[SourceDoc | SourceRef],
    previous: Mapping[SourceId, SourceRecord],
    identity: str,
    pipeline: str | None,
    error_type: str,
    stage: str | None,
    message: str,
) -> None:
    """Record every member of a failed batch as `FAILED` and release it.

    Every member of a batch that did not produce, recorded `SourceStatus.FAILED` and released
    — ledger **36.1**.

    Every document in `batch` gets the same `error_type`/`stage`/`message`: they shared the one
    call that did not produce, and a good document caught in a bad batch got no nodes either,
    which is what makes `FAILED` true of it too (see `changes_against_records` and the module
    docstring on batching). Their `SourceFailure.attempts` may still differ — see `_next_attempts`
    — because that count is a per-source history, not a per-batch fact.

    Released the same run it is recorded, never left for the next one: a failed source is not
    retried unasked (`36.2`), so whatever it half-wrote before the stage that lost it must not
    stay retrievable under a record nothing will revisit until `--retry-failed`.
    """
    attempted_at = datetime.now(UTC)
    failures = {
        doc.source_id: SourceFailure(
            error_type=error_type,
            stage=stage,
            message=message,
            attempts=_next_attempts(
                previous.get(doc.source_id), doc, identity=identity, batch_size=len(batch)
            ),
            last_attempt_at=attempted_at,
        )
        for doc in batch
    }
    # Released first: a store's `delete_source` removes the record as well as the nodes.
    await _release_sources(
        runnable,
        store_stage_ids=store_stage_ids,
        sources=tuple(doc.source_id for doc in batch),
    )
    await _record_sources(
        runnable,
        store_stage_ids=store_stage_ids,
        docs=batch,
        pipeline=pipeline,
        identity=identity,
        status=SourceStatus.FAILED,
        failures=failures,
    )


def _next_attempts(
    previous: SourceRecord | None, doc: SourceDoc | SourceRef, *, identity: str, batch_size: int
) -> int:
    """Compute `SourceFailure.attempts` for a document's next failed record.

    `SourceFailure.attempts` for `doc`'s next failed record — ledger **36.1**, owner-settled
    2026-09-21.

    `1` unless the previous record for this source was itself `FAILED` under the identical bytes
    and pipeline identity — anything else (no record, a different hash, a different identity) is
    the first attempt at *this* failure, whatever came before it. When it was, a batch of exactly
    one document advances the count: the failure is unambiguously this document's own, attempt
    after attempt. A batch of several does not: the cause may be any one of its members, so
    marching every document's own count upward because it happened to share a batch with the one
    that actually failed would overstate how many times *it* has failed.
    """
    if (
        previous is not None
        and previous.status is SourceStatus.FAILED
        and previous.failure is not None
        and previous.content_hash == _content_hash(doc)
        and previous.pipeline_identity == identity
    ):
        return previous.failure.attempts + 1 if batch_size == 1 else previous.failure.attempts
    return 1


def _failing_stage(records: Sequence[StageRecord]) -> str | None:
    """Name the stage that stopped a batch, for its sources' failure records.

    The `position` of the last top-level `wrap`-ed call a batch's `recording()` scope saw fail
    — ledger **36.1**.

    `parent is None` picks a stage boundary itself — the identical call `Runner._invoke_stage`
    wraps — never a nested call a stage's own plugin made along the way (an `LLM` it asked, say),
    which records under that stage's own id as `parent` rather than `None`. *Last*, because a
    stage with a non-empty `applies_to` can call `_invoke_stage` more than once per batch — see
    `Runner._run_stage`, `_segment_by_applicability` — and only the final one is the segment that
    actually stopped the batch; every earlier one already produced. `None` when nothing recorded
    `FAILED` at that level, which a raised exception (recorded `RAISED`, never `FAILED`, and
    carrying its own `stage` on the exception instead) leaves this function no reason to be
    asked about.
    """
    failing = [
        record
        for record in records
        if record.parent is None and record.outcome is OutcomeKind.FAILED
    ]
    return failing[-1].position if failing else None


def _count_of(instance: object) -> Callable[[], Awaitable[int]] | None:
    """`instance.count`, if it has one and it is callable — see `IndexResult`'s docstring."""
    found = getattr(instance, "count", None)
    if found is None or not callable(found):
        return None
    return cast(Callable[[], Awaitable[int]], found)


def _list_sources_of(instance: object) -> Callable[[], Awaitable[Sequence[SourceRecord]]] | None:
    """`instance.list_sources`, if it has one and it is callable — `_put_source_of`'s shape."""
    found = getattr(instance, "list_sources", None)
    if found is None or not callable(found):
        return None
    return cast(Callable[[], Awaitable[Sequence[SourceRecord]]], found)


def _put_source_of(instance: object) -> Callable[[SourceRecord], Awaitable[None]] | None:
    """The instance's `put_source` if it has a callable one, else `None`.

    `instance.put_source`, if it has one and it is callable — the same defensive shape as
    `_count_of`. `put_source` **is** on the published `NodeStore` contract, so
    `None` here is not an admission the contract is optional; it is the identical spirit
    `_stored_count`'s own docstring already states for `count`.
    """
    found = getattr(instance, "put_source", None)
    if found is None or not callable(found):
        return None
    return cast(Callable[[SourceRecord], Awaitable[None]], found)
