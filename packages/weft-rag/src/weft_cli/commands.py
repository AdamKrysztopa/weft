"""The built-in commands, registered under `Command` exactly as a third party would.

Task **3.2**: "`weft --help` cannot drift from what is installed, because core has no command
list to edit." `weft_cli.cli.COMMANDS` used to be that list — a hand-written
`dict[str, CliCommand]`, five entries, each a small hard-coded dispatch table needing an edit
to grow. This module is what replaces it: every built-in command is a plugin registered against
`weft_command.contract.Command`, discovered through the same `weft.packs` entry point a
stranger's pack uses, so the argument-grammar and `--help` text `weft_cli.cli` builds by walking
`Registry.names_for(Command)` (see that module) cannot disagree with what is actually installed
— there is no second list to keep in sync because there is no first one any more.

**Why `weft-cli` owns the entry point, rather than a new distribution.** CLAUDE.md: "Built-ins
get no shortcut. A first-party pack registers through the same public entry point a third party
uses, and receives nothing extra" — applied here to the CLI's own surface, as the task line asks.
The candidate that was not taken is a new, dedicated distribution (`weft-command` publishing the
contract already declines to register anything of its own, on `weft-prompts`' precedent — see
`weft_command.contract`'s module docstring). Splitting registration into an eleventh package
would buy nothing: every one of these five commands calls straight into `weft_cli.ingest`,
`weft_cli.ask`, `weft_cli.route_ask` and `weft_cli.plugins_report` — modules that already live
here, that a hypothetical sibling distribution would have to depend on `weft-cli` to reach,
which is exactly the inverted dependency 3.1's own module docstring refuses for a *contract*
publisher and would be no better for a pure re-exporter. `weft-cli` already depends on every
first-party distribution these five commands need (`weft-extract`, `weft-chunk`, `weft-embed`,
`weft-store`, `weft-retrieve`, `weft-generate`, `weft-llm`, `weft-prompts`) and its own handlers
already live here — the task's own suggested candidate, taken because nothing else was cheaper
or more honest about where the logic already sits.

**A built-in command needs the registry, the discovery reports and `[services]`/`[llm]` — and a
`Command.run(self, args, ctx)` receives neither directly.** `weft_kernel.context.Context.services`
is `docs/02-extension-model.md`'s own answer to exactly this shape of question: "ambient services
every stage may need regardless of what pipeline it runs in", resolved by *type alone*, with no
name to disambiguate — precisely true of "this run's `Dependencies`", of which there is exactly
one. `weft_cli.cli` adds it once, immediately after `build_dependencies()` returns and before any
command runs — `ctx.services.add(Dependencies, deps)` — and every command below reads it back
with `ctx.require(Dependencies)`. This is not a new mechanism: it is `ServiceRegistry`, already
generic over any type, used for a fact 3.2 needs and no earlier task did. A third party's own
command is free to ignore it (and most will, since depending on `weft_engine.registry_bootstrap.
Dependencies` means depending on `weft-cli` itself) or to read `ctx.require(weft_kernel.registry.
Registry)` directly if all it needs is plugin resolution — nothing here reserves `Dependencies`
to built-ins; it is simply the shape *these* five commands, all of them already written against
it before this task, already share.

**What changed in each command's own logic, and what did not.** Every `run()` body below is the
same sequence `weft_cli.cli`'s retired `handle_index`/`handle_ask`/`handle_route`/
`handle_plugins_list`/`handle_plugins_doctor` ran — `require_active`/`require_plugin` before
calling into the library, then `run_index`/`run_ask`/`run_routed_ask` unchanged, then the same
shape of result. Two things moved, both mechanical: a refusal `(ExitCode, str)` tuple used to be
printed and returned directly; now it is raised as `CommandRefusalError`, carrying the exit code
as data rather than as a control-flow return value, because `run()` cannot print and a `Command`
that swallowed its own exit code into `Outcome` would need `weft_command.CommandResult` to name a
weft-cli-specific enum it has no business knowing about (G1's own reasoning, one layer up: the
*contract* names no adapter). `weft_cli.render.render_outcome` is the one place that turns either
a `CommandResult` or a `CommandRefusalError` back into text and an exit code — see that module.
`IndexCommand`'s "some files failed" case is *not* modelled as a refusal or as `Outcome.Failed`:
the run genuinely produced a `RunSummary`, failures included, exactly as `run_index` already
returns it on success — only the exit code, a rendering-adjacent decision, moves to
`weft_cli.render`, which is what "the CLI renders it" (`03`'s governing rule) means applied to a
process's own exit status.

**Task 3.11 retires `route` as a separate registered name.** `AskCommand` below absorbs
`RouteCommand`'s own body — the question a user asks now reaches the pipeline the router names with
no second command to know about, `docs/03-cli.md`'s own already-published *Command surface* table
read literally ("query, streaming the answer with citations" — no `route` entry ever existed in that
table). `--pipeline` is what a caller naming a specific pipeline uses instead of the router's own
choice; `--retrieve-only` is Phase 0's own contract, kept reachable rather than deleted, because
`manual/quickstart.md`'s own zero-configuration walkthrough and `weft eval baseline`'s V3
baseline (`docs/09-release.md` §4.3, `weft_cli.eval_baseline`, repair R22.4c) both depend on a
deterministic, credential-free, network-free measurement that routing cannot honestly offer once
generation is a real model call resolved from `[llm.roles]` — see `docs/internal/build-ledger.md`'s
3.11 entry for the full argument.

**Task 4.0 gives `IndexCommand` the identical `--pipeline` surface `AskArgs` already has.**
`weft_cli.ingest.run_index`'s own module docstring carries the argument (Q3, settled:
`[services]` and a document's `with:` stay two surfaces); this module's own share of it is
`ConflictingIndexModeError` — `--extract`/`--pipeline` refuse together on
`ConflictingAskModeError`'s exact footing — and skipping `INDEX_PACKS`/`[services]`'s
own `require_plugin` gate when a document names the run, since neither promise is one a
named document has made.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from typing import ClassVar, Final, cast

from pydantic import BaseModel, ConfigDict, Field

from weft_cli.ask import AskHit, hits_for, run_ask
from weft_cli.config_commands import register_config_commands
from weft_cli.coverage import (
    LayerCoverage,
    SourceCoverage,
    coverage_of,
    layer_coverage_of,
    ready_layers,
)
from weft_cli.deletion import ParticipantOutcome, delete_everywhere
from weft_cli.deletion import participants as deletion_participants
from weft_cli.eval_baseline import register_eval_baseline_command
from weft_cli.eval_commands import DEFAULT_RUNS_DIR, register_eval_commands
from weft_cli.eval_experiment import register_eval_experiment_command
from weft_cli.eval_table import register_eval_table_command
from weft_cli.exit_codes import ExitCode
from weft_cli.explain import (
    ScoreExplanation,
    arm_explanations,
    explanations_for,
    incomparable_note,
    record_lines,
)
from weft_cli.fanout import Participant
from weft_cli.ingest import DEFAULT_BATCH_SIZE, INDEX_PACKS, SourceChange, run_index_for
from weft_cli.installed_versions import active_distribution_versions, installed_versions
from weft_cli.layers import (
    LayerFailure,
    LayerJoin,
    LayerReclaim,
    LayerRelease,
    LayerStoreFallback,
    UnknownLayerError,
    corpus_scoped_layer_names,
    demote_layer_records,
    installed_layers,
)
from weft_cli.output import AskFormat
from weft_cli.pack_new import PackNewCommand
from weft_cli.participation import (
    DEFAULT_INDEX_RUNS_DIR,
    check_participants_agree,
    load_run_records,
    produced_value,
    stores_in_use,
)
from weft_cli.pipeline_catalogue import (
    DEFAULT_PIPELINES_DIR,
    declared_slot_ids,
    full_catalogue,
    load_pipeline_catalogue,
)
from weft_cli.pipeline_commands import register_pipeline_commands
from weft_cli.preview import run_render
from weft_cli.progress import ProgressReporter
from weft_cli.reconcile import (
    ReconcileEstimateOutcome,
    ReconcileOutcome,
    estimate_everywhere,
    reconcile_everywhere,
)
from weft_cli.reconcile import participants as reconcile_participants
from weft_cli.route_ask import (
    named_pipeline,
    pipelines_producing,
    resolve_named_pipeline,
    routable_rung_roles,
    run_named_ask,
    run_named_retrieve,
    run_routed_ask,
)
from weft_cli.skew import SkewReport, detect_skew
from weft_cli.target_commands import (
    TargetDropCommandResult,
    TargetPromoteCommandResult,
    TargetRollbackCommandResult,
    register_target_commands,
)
from weft_cli.tracing_status import describe_tracing
from weft_cli.writer_claim import claim_all_writers
from weft_command.contract import Command, CommandResult
from weft_command.permission import CommandRefusalError as CommandRefusalError
from weft_command.permission import PermissionClass
from weft_embed import Embedder
from weft_engine.registry_bootstrap import (
    DEFAULT_CONFIG_PATH,
    Dependencies,
    PluginRefusal,
    require_active,
    require_plugin,
)
from weft_engine.services import embed_config_for
from weft_engine.targets import StoreHoldsNoTargetsError, bind_store, require_existing_target
from weft_eval.run_record import (
    CorpusDigestBasis,
    build_run_record,
    corpus_identity,
    write_run_record,
)
from weft_extract import Extractor
from weft_extract.payload import Rendition
from weft_generate.contract import Generator
from weft_generate.payload import Answer
from weft_kernel.context import Context
from weft_kernel.discovery import PackRegistrar, PackReport
from weft_kernel.errors import UnresolvedNameError, WeftError
from weft_kernel.payload import Failed, Outcome, Produced, SourceId
from weft_kernel.pipeline import Pipeline
from weft_kernel.registry import DisplacedRegistration, unwrap_factory
from weft_kernel.resolution import Contribution, ResolvedPipeline
from weft_kernel.runner import RunSummary
from weft_kernel.seam import StageRecord, aclose, recording, wrap
from weft_retrieve.contract import ContextPacker, Retriever
from weft_retrieve.engine import missing_roles, route_requirements
from weft_store import NodeStore, ReconcileMode, SourceRecord, SourceStatus
from weft_store.contract import (
    EmbeddingIdentity,
    GenerationId,
    LayerStatus,
    TargetCatalogue,
    TargetHolding,
    target_name,
)

_INDEX_HELP = (
    "run an ingest pipeline over a directory. Which formats are accepted is derived from "
    "the extractors actually installed, never from a fixed list. --pipeline names a "
    "document instead of the built-in four stages, reaching a plugin's own 'with:' "
    "configuration (ledger task 4.0). A successful run always ends with an automatic "
    "'repair' reconciliation pass; --reconcile full opts this run into backfill too "
    "(ledger task 5.1c)."
)

_ASK_HELP = (
    "ask a question. Routes through the installed router by default — a QueryScorer and a "
    "RoutingPolicy discovered from the registry, never a fixed list here — and prints the "
    "generated, cited answer. --pipeline names one directly, skipping the router; "
    "--retrieve-only stops at the passages and makes no model call — on its own it runs the "
    "hardwired vector search (Phase 0's own contract, kept for scripts), and with --pipeline "
    "it runs that pipeline instead, which is how a retrieval-only document such as "
    "lexical-retrieve is reached with nothing configured."
)

_DELETE_HELP = (
    "remove a source and everything derived from it, everywhere — the configured node "
    "store and every installed pack that holds derived data, each one named in the result "
    "whether it succeeded or failed"
)

_RECONCILE_HELP = (
    "converge derived state against what the corpus actually holds — every installed pack "
    "that can reconcile is asked, and one that fails is named. --mode full also backfills "
    "state that was never built, and prints what that will cost first; --dry-run names the "
    "participants (and, for full, the cost) and stops. --mode omitted uses weft.toml's own "
    "[reconcile] mode, or 'full' if that says nothing"
)

_PLUGINS_LIST_HELP = "one line per discovered pack"

_PLUGINS_DOCTOR_HELP = "full status, reason and disclosure per discovered pack"

_SOURCES_LIST_HELP = (
    "list every source recorded by every node store a project indexes into, failures "
    "included; --status keeps only sources at that status"
)

_TARGET_LIST_HELP = (
    "one line per target a store holds: its name, whether it is live or the previous live "
    "target, its embedding identity if one is recorded, and its source count (ledger task 34.6)"
)


class TargetAlreadyExistsError(WeftError):
    """`weft init` refused to overwrite a `weft.toml` that already exists.

    **Repair, 2026-08-20** (`docs/internal/build-ledger.md`'s dated paragraph for tasks 3.3/3.6/3.7
    has the argument in full, against `docs/03-cli.md` → *Permissions*'s own table): `weft init` is
    `write`-class now, not `overwrite` — table row `write`'s own worked example is "index into a new
    collection, write a derived pipeline", which is exactly what a first-run `weft
    init` scaffolding a project's own `weft.toml` is. `write` is `allow` by default, so it never
    reaches `weft_cli.confirm.gate` at all, which is the fix for the reported bug: a first
    `weft init` in CI, where nothing is a TTY, no longer refuses.

    What `overwrite` bought instead — refusing to silently discard whatever the existing file
    held — is not given up; it moves from a TTY prompt to an unconditional, loud refusal:
    this command creates, it does not replace, so a target that already exists is not asked
    about, it is refused outright, naming the path. Not a permission refusal (`weft_cli.
    confirm.gate` never runs for a `write`-class command), so this is not `CommandRefusalError`
    and does not carry `ExitCode.POLICY_REFUSED`: `weft_cli.exit_codes.exit_code_for`'s own
    default for "every other `WeftError`" — `OPERATION_FAILED` (`1`) — is the right code,
    argued explicitly rather than defaulted past: the answer here is certain, not a policy
    this tool declined to decide without a human, which is what `3` means.
    """

    def __init__(self, message: str, *, path: str) -> None:
        super().__init__(message)
        self.path = path


class UnresolvedPluginNameError(CommandRefusalError, UnresolvedNameError):
    """Refusal for a plugin name that genuinely fails to resolve.

    `CommandRefusalError`'s own family member for a genuine name-resolution failure —
    finding 2 of the 2026-08-20 Phase 3 review, repairing tasks 3.2/3.3/3.7 (`docs/build-ledger.
    md`'s dated paragraph carries the argument in full).

    Before this repair, `IndexCommand`/`AskCommand` caught `weft_engine.registry_bootstrap.
    require_plugin`'s answer and always raised the plain `CommandRefusalError` above, whatever
    the underlying cause — including the branch where `weft_kernel.registry.UnknownPluginError`
    had already computed `valid_options`, every name actually registered for the contract that
    was asked. That field reached `require_plugin`'s own `_unresolved` only as `plain=str(exc)`,
    a string folded into the message, and was discarded there. History matters here: before
    Phase 3, this path was a plain return value with no typed field to lose at all — it was
    Phase 3's own `Command`/`Outcome` unification (task 3.2) that turned the refusal into an
    exception and dropped the guarantee in the same motion.

    This subclass exists so only the branch that genuinely has real registered names to offer —
    `PluginRefusal.valid_options is not None`, see that class's own docstring — is required to
    supply them; `CommandRefusalError` itself keeps covering the *policy* refusals (a pack
    refused by `[packs] allow`, a no-TTY `overwrite`/`destroy` refusal) that `docs/build-ledger.
    md` 3.3's own paragraph already argued out of FF12's family, correctly, and that argument is
    not reversed here — only narrowed to the branch it was never actually about. `exit_code`
    stays `ExitCode.RESOLUTION_FAILED` (`4`) in every raise site today, `docs/03-cli.md` →
    *Output*'s own "a name no pack provides" — never `POLICY_REFUSED` (`3`), which
    `PluginRefusal.valid_options is None` (the refused branch) always pairs with instead.
    """

    def __init__(
        self, message: str, *, exit_code: ExitCode, valid_options: tuple[str, ...]
    ) -> None:
        super().__init__(message, exit_code=exit_code)
        self.valid_options = valid_options


class ConflictingIndexModeError(WeftError):
    """Refusal for `weft index` given both `--extract` and `--pipeline`.

    `weft index` was given both `--extract` and `--pipeline` — two different, mutually
    exclusive claims about what should run: narrow the default four-stage path's own
    auto-discovery to one named extractor, or run a whole document whose own `extract`
    stage already names its plugin (task **4.0**). Neither wins silently over the other,
    the identical reasoning `ConflictingAskModeError` below already gives `weft ask`'s own
    `--retrieve-only`/`--pipeline` pair — refused, loudly, before either resolves a plugin.

    Not a name-resolution failure — there is no alternative *name* to offer, only a choice
    between two flags that are individually valid — so this does not join `NAME_RESOLUTION_
    FAMILY`, on `ConflictingAskModeError`'s own footing.
    """


class NoLayersToRunError(WeftError):
    """`weft index --layers-only` was given, but no layer is named anywhere — ledger task **43.8**.

    `--layers-only` says "run the layers and nothing else", and with none named that is a run that
    does nothing at all, refused before `run_index_for` opens anything.

    Not a name-resolution failure — there is no name to offer, only a flag with nothing to
    act on — so this does not join `NAME_RESOLUTION_FAMILY`, `ConflictingIndexModeError`'s
    own footing.
    """


class ConflictingAskModeError(WeftError):
    """Refusal for `weft ask --retrieve-only` naming a pipeline that ends in a `Generator`.

    `weft ask --retrieve-only --pipeline <name>` was given a pipeline that ends in a
    `Generator` — repair **R21.5** narrowed this from every `--retrieve-only`/`--pipeline`
    pairing to exactly this one: `--retrieve-only` no longer refuses a named pipeline on
    sight, because a pipeline can end in a retrieval stage just as easily as a generating
    one, and running one through to its own last stage — no router, no model — is
    `--retrieve-only`'s whole contract asked of a pipeline the caller chose by name rather
    than the hardwired vector search. What still contradicts `--retrieve-only` is a
    pipeline whose own last stage *would* call a model — retrieve the nearest passages
    with no model call at all, or run this particular pipeline through to a generated
    answer, and the two cannot both be true of one run. Refused, loudly, before either
    resolves a single plugin — CLAUDE.md: "a silent fallback is worse than a failure."

    Not a name-resolution failure — an unknown pipeline name is refused separately, by
    `weft_cli.route_ask.named_pipeline`'s own `UnknownPipelineNameError` — so this does not
    join `NAME_RESOLUTION_FAMILY`; `weft_cli.exit_codes.exit_code_for`'s own default,
    `OPERATION_FAILED` (`1`), is the code, on the identical footing task 3.7's own
    `TargetAlreadyExistsError`/`PipelineAlreadyExistsError` argue for a certain answer that
    is not a policy question.
    """


class LayerDemotionFailedError(WeftError):
    """Stops a delete before a stale corpus layer could keep answering over the removed source.

    `weft delete` could not mark a corpus layer the source covered `STALE`, so the delete was
    refused before anything was removed — tasks **43.21** and **R43.33**. Deleting anyway would
    serve the unmarked tree whole with a hole in it.
    """


class PendingLayerError(WeftError):
    """Refusal for a `--pipeline` rung whose required layer is not built everywhere.

    `--pipeline` named a rung whose `route.requires` layer is not built on every indexed
    source — ledger task **43.9**. A rung reached through the router is simply not offered
    (`weft_retrieve.engine.route_catalogue`'s own `ready_layers` filter); naming one directly
    bypasses that filter, so it is refused here instead, unless `--allow-pending` says the
    caller wants the part that is built.

    A plain `WeftError`, on `ConflictingAskModeError`'s own footing: the failure mode is a
    layer not yet ready, never a name nothing registered, so this does not join
    `NAME_RESOLUTION_FAMILY` — `weft_cli.exit_codes.exit_code_for`'s own default,
    `OPERATION_FAILED` (`1`), is the code.
    """


def _raise_for_plugin_refusal(refusal: PluginRefusal | None) -> None:
    """Turn `require_plugin`'s answer into the right raise — `None` does nothing.

    The one place `IndexCommand`/`AskCommand` decide between `UnresolvedPluginNameError` and
    plain `CommandRefusalError`, so the two commands cannot drift from each other on which
    branch gets the typed field — the identical "one code path, not two per author" reasoning
    `weft_kernel.seam.wrap`'s own registration seam already applies one layer down.
    """
    if refusal is None:
        return
    if refusal.valid_options is not None:
        raise UnresolvedPluginNameError(
            refusal.message, exit_code=refusal.exit_code, valid_options=refusal.valid_options
        )
    raise CommandRefusalError(refusal.message, exit_code=refusal.exit_code)


def _stores_in_use(deps: Dependencies) -> frozenset[str]:
    """Every `NodeStore` name that `weft delete` and `weft reconcile` must reach.

    Every `NodeStore` name `weft delete`/`weft reconcile` must reach — task **6.18**, G13's
    first repair (`docs/02-extension-model.md` §1 → *Extended by G13*), narrowed by carried
    repair **R11.2**: the configured `[services] store`, plus every `NodeStore` reachable from a
    project's *own* pipeline documents — including through their `extends:` chains — or named by
    a persisted run record, from either `weft eval run` or `weft index`. One helper for all
    three call sites — `DeleteCommand._targets`, `ReconcileCommand._targets` and
    `IndexCommand._auto_reconcile` — so the prompt, the run and the automatic post-index pass
    cannot disagree about who participates.
    """
    return stores_in_use(
        configured=deps.services.store,
        registry=deps.registry,
        project=load_pipeline_catalogue(DEFAULT_PIPELINES_DIR),
        catalogue=full_catalogue(reports=deps.reports),
        records=load_run_records(DEFAULT_RUNS_DIR) + load_run_records(DEFAULT_INDEX_RUNS_DIR),
    )


async def _require_target_exists(deps: Dependencies, target: str | None) -> None:
    """Refuse a read command whose target does not exist in `[services] store`.

    `weft_engine.targets.require_existing_target`, against `[services] store` — every read
    command's own existence check, ledger task **34.6**. `None` — every read naming no explicit
    target — instead checks that this project's own `TargetHolding` participants agree on which
    target is live (`weft_cli.target_commands.check_participants_agree`, ledger task **34.11**):
    a `--pipeline` run's own store stage may need no `[services] store` at all (the module
    docstring's *"Q3, settled"*), and that function's own docstring carries the identical
    "resolving an unreachable name is not this check's job" footing this one always has.
    """
    if target is None:
        await check_participants_agree(deps)
        return
    await require_existing_target(
        deps.registry.entry(NodeStore, deps.services.store).factory(None),
        target,
        store_name=deps.services.store,
    )


async def _read_sources_by_store(
    deps: Dependencies, target: str | None
) -> Outcome[tuple[tuple[str, tuple[SourceRecord, ...]], ...]]:
    """Read `list_sources()` once per store in use, bound to `target`.

    One `list_sources()` read per store `_stores_in_use` names, bound to `target` — the
    fan-out `SourcesListCommand.run` and `AskCommand`'s own coverage line share, ledger task
    **43.4**, through the identical `wrap(..., stage="sources:list")`/`aclose` seam, so the two
    cannot disagree about which stores answer or how a failed read is reported. A store without
    `list_sources` is skipped, not refused — the empty tuple this returns for "no store could
    answer" is the same shape as "every store answered with nothing", and it is left to each
    caller to tell those apart, exactly as `SourcesListCommand.run` always has.
    """
    by_store: list[tuple[str, tuple[SourceRecord, ...]]] = []
    for name in sorted(_stores_in_use(deps)):
        entry = deps.registry.entry(NodeStore, name)
        store = await bind_store(entry.factory(None), target, store_name=name)
        if not hasattr(store, "list_sources"):
            continue

        async def _list(store: NodeStore = store) -> Outcome[tuple[SourceRecord, ...]]:
            return Produced(value=tuple(await store.list_sources()))

        wrapped = wrap(
            _list,
            distribution=entry.distribution,
            contract=NodeStore.__qualname__,
            plugin=name,
            stage="sources:list",
        )
        try:
            listed = await wrapped()
        finally:
            await aclose(
                store,
                distribution=entry.distribution,
                contract=NodeStore.__qualname__,
                plugin=name,
            )
        if not isinstance(listed, Produced):
            return listed
        by_store.append((name, listed.value))
    return Produced(value=tuple(by_store))


@dataclass(frozen=True, slots=True)
class _AskCoverage:
    """What `_coverage_for` answers: coverage, layers, and the records behind them.

    `_coverage_for`'s own answer — ledger tasks **43.4**/**43.9** share the one
    `list_sources()` read this carries: `coverage`, every layer's own `LayerCoverage` (built
    or not — `AskCommandResult.layers`'s own docstring), and the records both were computed
    from, so a caller checking `PendingLayerError` reads `bases` off them rather than a second
    read.
    """

    coverage: SourceCoverage | None
    layers: tuple[LayerCoverage, ...]
    records: tuple[SourceRecord, ...] = ()


async def _coverage_for(deps: Dependencies, target: str | None) -> Outcome[_AskCoverage]:
    """Let `weft ask` say how much of the corpus, and which layers, its answer could see.

    `AskCommandResult.coverage`/`.layers` for one ask — ledger task **43.4**, widened at
    **43.9**. `coverage` is `None` only when no store `_stores_in_use` names could answer
    `list_sources` at all, so a build with none does (every existing test's own registry,
    `weft eval baseline`'s deterministic store included) renders exactly as it did before this
    task; a store that answered with nothing outstanding still sets `coverage`,
    `SourceCoverage.complete` and all, which is what lets `weft_cli.render._render_ask` tell
    "nothing to say" from "nothing was asked".
    """
    read = await _read_sources_by_store(deps, target)
    if not isinstance(read, Produced):
        return read
    if not read.value:
        return Produced(value=_AskCoverage(coverage=None, layers=()))
    records = tuple(record for _, records in read.value for record in records)
    return Produced(
        value=_AskCoverage(
            coverage=coverage_of(records), layers=layer_coverage_of(records), records=records
        )
    )


def _layer_progress(layer: str, ask_coverage: _AskCoverage) -> tuple[int, int]:
    """Count how many sources have `layer` built, out of how many it could cover.

    `(built, of)` for `layer` off `ask_coverage.layers` — `0` built and every `ACTIVE`
    source for `of` when no record carries the layer at all (the "Already decided" text
    ledger task **43.9**'s brief states for `PendingLayerError`'s own message).
    """
    matched = next((c for c in ask_coverage.layers if c.name == layer), None)
    if matched is not None:
        return matched.built, matched.of
    return 0, ask_coverage.coverage.indexed if ask_coverage.coverage is not None else 0


def _raise_unknown_route_layer(doc: str, layer: str, *, deps: Dependencies) -> None:
    """Raise `UnknownLayerError` for a document's `route.requires` naming `layer`.

    `UnknownLayerError` for `doc`'s own `route.requires`, naming `layer` — carried repair
    **R43.13**. `installed_layers` is only computed here, once a refusal is certain, for
    `valid_options` — the cheap membership check both call sites run first does not need it.
    """
    options = installed_layers(
        registry=deps.registry, reports=deps.reports, contributions=deps.contributions
    )
    raise UnknownLayerError(
        f"'{doc}' names '{layer}' in route.requires, which is not an installed layer. "
        f"Installed layers: {', '.join(options) or '(none)'}.",
        valid_options=options,
        pipeline=doc,
    )


def _raise_for_uninstalled_route_layers(
    catalogue: Mapping[str, Pipeline], *, deps: Dependencies
) -> None:
    """Refuse an ask when a catalogue document requires a layer nothing installs.

    Refuse the whole ask, before either the router or a named pipeline ever runs, when any
    catalogue document's own `route.requires` names something the catalogue does not hold at
    all — carried repair **R43.13**, found by the exit review: a misspelt layer left the rung
    never offered and `PendingLayerError`'s own remedy then failed with `UnknownLayerError`,
    and a routed ask over such a document was never checked at all. `layer not in catalogue`
    is a set lookup — cheap enough to run over every document on every ask.
    """
    for doc, layer in sorted(route_requirements(catalogue).items()):
        if layer not in catalogue:
            _raise_unknown_route_layer(doc, layer, deps=deps)


def _raise_if_pending(
    pipeline_name: str,
    *,
    catalogue: Mapping[str, Pipeline],
    ask_coverage: _AskCoverage,
    deps: Dependencies,
) -> None:
    """Keep a directly named rung from silently answering over a half-built layer.

    Refuse `pipeline_name` when its own `route.requires` layer is not built on every
    indexed source — ledger task **43.9**. Does nothing for a rung naming no layer, or one
    whose layer is already built everywhere.
    """
    layer = route_requirements(catalogue).get(pipeline_name)
    if layer is None or layer in ready_layers(ask_coverage.layers):
        return
    if layer not in installed_layers(
        registry=deps.registry, reports=deps.reports, contributions=deps.contributions
    ):
        # R43.13: the catalogue holds `layer` (`_raise_for_uninstalled_route_layers` already
        # refused the alternative), but it is not a real layer — refused the same way, so this
        # error's own remedy below is never reached over a document that cannot build one.
        _raise_unknown_route_layer(pipeline_name, layer, deps=deps)
    built, of = _layer_progress(layer, ask_coverage)
    bases = ", ".join(
        f"'{name}'"
        for name in sorted(
            {
                record.pipeline
                for record in ask_coverage.records
                if record.status is SourceStatus.ACTIVE
            }
        )
    )
    raise PendingLayerError(
        f"'{pipeline_name}' answers from the '{layer}' layer, which is built on {built:,} of "
        f"{of:,} sources indexed with {bases}. Build it with `weft index <dir> --layers "
        f"{layer} --layers-only`, or ask again with --allow-pending to answer from the part "
        f"that is built."
    )


def _excluded_rung_explanations(
    catalogue: Mapping[str, Pipeline],
    *,
    ask_coverage: _AskCoverage,
    ready: frozenset[str],
    deps: Dependencies,
) -> tuple[str, ...]:
    """`--explain`'s own line per catalogue document the router left out — ledger task **43.9**.

    Routed path only: a rung named directly is refused or accepted before this point, never silently
    excluded. A document with no `route.summary` is never a candidate whatever its layer, so it is
    not listed as left out (R43.21). Carried repair **R43.30** adds a line per role `[llm.roles]`
    does not map, read through `weft_retrieve.engine.missing_roles` — the reason the router's own
    catalogue left the rung out.
    """
    lines: list[str] = []
    for name, layer in sorted(route_requirements(catalogue).items()):
        if layer in ready or "route.summary" not in catalogue[name].vars:
            continue
        built, of = _layer_progress(layer, ask_coverage)
        lines.append(
            f"not offered: '{name}' needs the '{layer}' layer, built on {built:,} of {of:,} sources"
        )
    rung_roles = routable_rung_roles(
        catalogue, registry=deps.registry, reports=deps.reports, contributions=deps.contributions
    )
    for name, roles in missing_roles(rung_roles, frozenset(deps.llm.roles.roles)).items():
        lines.extend(f"not offered: '{name}' needs role '{role}'" for role in roles)
    return tuple(lines)


def _register_corpus(ctx: Context, deps: Dependencies) -> None:
    """Give reconcile participants the primary corpus they check orphans and backfill against.

    Put the configured `NodeStore` on the `Context` a reconcile pass carries — task
    **6.19**, G13's second repair (`docs/02-extension-model.md` §1 → *Extended by G13*): "the
    CLI registers the configured store into the `Context` a reconcile pass carries, and a
    participant reaches it with `ctx.require(NodeStore)`." No contract change: `Context.require`
    is G1's own one resolution seam, and `NodeStore` already answers "what should exist" with
    `list_sources`/`scan`/`count`.

    A `[services] store` that resolves to nothing registered adds nothing here — no raise, no
    placeholder. `weft_engine.registry_bootstrap.require_plugin` is what turns an unresolvable
    `[services] store` into a diagnosable refusal; a participant that then reaches for a corpus
    with none registered gets `UnresolvedServiceError`, naming what it wanted and what is
    available, which is the loud failure, correctly located — a second translation here would
    give one mistake two messages (`docs/internal/lessons.md` L5.9).

    Called from exactly two places, both inside `run`, never inside `describe_impact` (a
    confirmation prompt must not open a connection to the corpus before consent), and both
    before the estimate/reconcile fan-out itself runs. Not idempotent, and does not catch
    `DuplicateServiceError`: one `Context` is built per `run_command` invocation
    (`weft_cli.cli._context`), so one call each is exactly one registration.
    """
    if deps.services.store not in deps.registry.names_for(NodeStore):
        return
    entry = deps.registry.entry(NodeStore, deps.services.store)
    ctx.services.add(NodeStore, entry.factory(None))


class NoArgs(BaseModel):
    """The args model for a command that takes none — `plugins list` and `plugins doctor`."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class IndexArgs(BaseModel):
    """Command-line arguments for `weft index`.

    `weft index <path> [--extract NAME | --pipeline NAME] [--reconcile repair|full]` — see
    `weft_cli.argparse_gen` for how a field with no default becomes a positional and one with
    a default becomes a flag.

    `extract` and `pipeline` are mutually exclusive — `IndexCommand.run` refuses both
    together, loudly, before either resolves a plugin, the identical shape `AskArgs`'
    `pipeline`/`retrieve_only` pair already has.

    **`reconcile`, task 5.1c.** `docs/02-extension-model.md` §3 → *Slots*, "Tested by G7":
    "a `Reconcilable` pack creating derived data during an automatic pass *would* breach
    it, so the automatic pass never does; backfill is reached only by a person's per-run
    flag." That is why this field's default is the hardcoded `ReconcileMode.REPAIR` — never
    read from `weft.toml`'s own `[reconcile]` block (see `weft_engine.reconcile_policy`'s own
    module docstring for why that block governs `weft reconcile`'s bare default and nothing
    about this one) — so a project cannot, by editing one file once, turn every future `weft
    index` into a `full` run with nobody typing `--reconcile full` for that particular
    invocation. Naming `full` here is exactly what opts *this* run into the expensive pass.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    path: str = Field(description="directory to index")
    extract: str | None = Field(
        default=None,
        description=(
            "the extractor plugin to use, when more than one claims what is in the "
            "directory. Omit it and the single claimant is used; a refusal lists the "
            "candidates. Mutually exclusive with --pipeline."
        ),
    )
    pipeline: str | None = Field(
        default=None,
        description=(
            "name a pipeline document instead of the built-in four stages (a project-local "
            "document or an installed pack's own contribution — the same set `weft pipeline "
            "show` resolves against). Every stage's plugin and its own 'with:' "
            "configuration come from the document; [services] embed/store are not read for "
            "this run. Mutually exclusive with --extract (ledger task 4.0)."
        ),
    )
    reconcile: ReconcileMode = Field(
        default=ReconcileMode.REPAIR,
        description=(
            "mode for the automatic reconciliation pass this command runs after a "
            "successful index — 'repair' (the default, and the only mode reached with no "
            "flag) drops derived state whose source is gone; 'full' also backfills state "
            "that was never built, and prints what that will cost before it spends it. "
            "Never influenced by weft.toml — see 'weft reconcile --mode' for the command "
            "whose own default that file may change."
        ),
    )
    reprocess: bool = Field(
        default=False,
        description=(
            "do the work again for documents that did not move — the escape hatch for a "
            "change the pipeline identity cannot see, such as a hosted model that changed "
            "behind a stable name."
        ),
    )
    batch_size: int | None = Field(
        default=None,
        gt=0,
        description=(
            "index this many documents at a time (default 25, ledger task 43.2): each batch "
            "is queryable the moment it lands and peak memory is bounded by the batch. Given "
            "explicitly, it is refused before anything runs for a pipeline containing a stage "
            "whose output depends on which other nodes shared its batch; without it, such a "
            "pipeline indexes the whole corpus in one batch and says so."
        ),
    )
    retry_failed: bool = Field(
        default=False,
        description=(
            "retry a source a previous run recorded failed, instead of skipping it — paid "
            "stages sit on the ingest path, so a failure is not retried unasked (ledger task "
            "36.2). A source whose bytes or pipeline moved since it failed is indexed either "
            "way, with or without this flag."
        ),
    )
    target: str | None = Field(
        default=None,
        description=(
            "write into this target instead of the live one — a candidate beside it, "
            "created on its first write (ledger task 34.6). Omit for the live target."
        ),
    )
    layers: str | None = Field(
        default=None,
        description=(
            "comma-separated layer document(s) to run after the base, or 'none' to run "
            "none this invocation (ledger task 43.8). Omit to use [index] layers in "
            "weft.toml; a layer named that is not installed is refused, naming every "
            "installed layer."
        ),
    )
    layers_only: bool = Field(
        default=False,
        description=(
            "run only the layers named by --layers or [index] layers, over the sources "
            "already indexed — no extraction, no base pipeline run. Refused when no "
            "layer is named anywhere."
        ),
    )


class AskArgs(BaseModel):
    """`weft ask <question> [--pipeline NAME] [--retrieve-only] [--top-k N] [--format text|json]`.

    Task **3.11**: `ask` routes by default — see `AskCommand`'s own docstring for the surface
    decision and `docs/internal/build-ledger.md`'s 3.11 entry for the argument in full. `pipeline`
    and `retrieve_only` may be given together: `AskCommand.run` then retrieves through the named
    pipeline's own stages, refused only when it ends in a `Generator` (repair **R21.5**).
    `top_k`/`format` only take effect with `--retrieve-only` — a routed or named-pipeline answer
    has no `top_k` of its own to report (each pipeline decides that internally) and is always
    rendered the same way `_render_ask` already renders a routed answer.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    question: str = Field(description="the question to ask")
    pipeline: str | None = Field(
        default=None,
        description=(
            "name a pipeline directly, bypassing the router (a project-local document or an "
            "installed pack's own contribution — the same set `weft pipeline show` resolves "
            "against). With --retrieve-only, retrieves through this pipeline's own stages; "
            "refused when it ends in a Generator."
        ),
    )
    explain: bool = Field(
        default=False,
        description=(
            "print what each score means and what produced it, and say so when the scores in "
            "one ranking came from more than one retriever and are therefore on different "
            "scales. Rank order is what a reader is meant to trust; this is how to check why."
        ),
    )
    retrieve_only: bool = Field(
        default=False,
        description=(
            "retrieve and print the nearest passages, with no pipeline run at all — no "
            "router, no generation, no model call. Phase 0's own contract, kept for scripts."
        ),
    )
    top_k: int = Field(
        default=5, description="how many passages to retrieve — --retrieve-only only"
    )
    format: AskFormat = Field(
        default=AskFormat.TEXT,
        description=(
            "how to render --retrieve-only's passages: 'text' ranks them for a reader, "
            "'json' emits one line carrying each passage's node id, sources and raw "
            "similarity score. Has no effect without --retrieve-only."
        ),
    )
    target: str | None = Field(
        default=None,
        description=(
            "which target to read instead of the live one (ledger task 34.6). Refused for a "
            "target that does not exist, naming every target that does. Omit for the live one."
        ),
    )
    allow_pending: bool = Field(
        default=False,
        description=(
            "answer from a rung whose layer is not yet built on every source, stating how far "
            "it has got"
        ),
    )


class IndexCommandResult(CommandResult):
    """What `weft index` produced, as a `CommandResult` a renderer can format.

    What `weft index` produced — the same two facts `weft_cli.ingest.IndexResult` always
    carried, now a `CommandResult` a renderer can format without importing that dataclass.

    **`reconcile`, task 5.1c.** The automatic post-index pass's own result, reusing
    `ReconcileCommandResult` rather than a second, parallel shape — `weft_cli.render.
    _render_reconcile` is then one renderer for both `weft reconcile`'s own result and
    `weft index`'s automatic pass, so the two cannot disagree about what a participant's
    line looks like. `None` only when `run_index` itself raised before the pass could run —
    never for "the pass found no participants", which `ReconcileCommandResult.participants
    == ()` already says honestly.
    """

    summary: RunSummary
    stored_count: int | None
    reconcile: ReconcileCommandResult | None = None
    #: What re-indexing changed, per source — ledger task **9.17**. Carried here so the renderer
    #: can report it without reaching back into `weft_cli.ingest`; empty when the store could not
    #: answer `list_sources`, which is an absent comparison and not a claim that nothing moved.
    source_changes: Mapping[str, SourceChange] = Field(default_factory=dict)
    #: Carried repair `R17.6` — the embedder this run used, but only when `weft.toml` did not
    #: name one: the renderer cannot know where a value came from, so that fact travels here
    #: rather than being re-derived from the file a second time. `None` means the operator chose
    #: it, in a file, and a warning about a choice already made is one people learn to ignore.
    defaulted_embedder: str | None = None
    #: Ledger task **17.4** — copied from `weft_cli.ingest.IndexResult`, so the renderer can
    #: print what this run counts without importing that dataclass.
    documents_discovered: int = 0
    documents_indexed: int = 0
    #: Ledger **36.3**: documents this run recorded failed.
    documents_failed: int = 0
    #: Ledger task **31.14** — the payload index field paths the store ensured for this run, so
    #: an operator learns from the binary what `31.1` guarantees: every filter Weft itself issues
    #: against Qdrant is served by an index that exists *before the first point is written*. Empty
    #: is a **stated absence, not a claim of zero**: a store that declares no such attribute — as
    #: pgvector does, ensuring none — has said nothing rather than said none, and the renderer
    #: prints nothing at all in that case. Read off the built store the way `31.8` reads its index
    #: kind, so no `NodeStore` Protocol member and no `STORE_CONTRACT_VERSION` move is needed.
    payload_indexes: tuple[str, ...] = ()
    #: Repair **R38.13** — how many stored chunks carry `weft_index.payload.
    #: ExpansionDegraded`, copied from `weft_cli.ingest.IndexResult`. `None` when this run
    #: cannot answer — see that field's own docstring for exactly when it can.
    degraded_expansions: int | None = None
    #: `--target`, ledger task **34.6**, widened by **34.10** — copied from `weft_cli.ingest.
    #: IndexResult.target`, so the renderer can say where this run wrote without importing that
    #: dataclass. Never `None` for a store that satisfies `TargetHolding`, whether or not
    #: `--target` was given.
    target: str | None = None
    #: The target that was live when this run started. Paired with `target` so the renderer can
    #: say "(live)" or "(candidate; live is '...')".
    target_live: str | None = None
    #: Ledger task **34.10** — `True` when this run wrote the live target and another promote
    #: made a different one live before this run finished.
    target_stopped_being_live: bool = False
    #: The target that is live now, once this run finished — `None` unless
    #: `target_stopped_being_live` is.
    target_now_live: str | None = None
    #: Carried repair **R43.9** — copied from `weft_cli.ingest.IndexResult`: until then a
    #: changed or failed layer was reported to nobody.
    layers_changed: tuple[str, ...] = ()
    layers_failed: tuple[LayerFailure, ...] = ()
    #: Ledger task **43.23** — copied from `weft_cli.ingest.IndexResult.layers_joined`, so the
    #: renderer can say how many added leaves each corpus layer joined.
    layers_joined: tuple[LayerJoin, ...] = ()
    #: Repair **R43.38** — copied from `weft_cli.ingest.IndexResult`, so the renderer can name a
    #: store a corpus layer fell back on.
    stores_without_withdraw: tuple[LayerStoreFallback, ...] = ()
    stores_without_carry: tuple[LayerStoreFallback, ...] = ()
    #: Repair **R43.43** — copied from `weft_cli.ingest.IndexResult.layers_reclaimed`, so the
    #: renderer can say how many nodes each corpus layer's builds reclaimed.
    layers_reclaimed: tuple[LayerReclaim, ...] = ()
    #: Carried repair **R43.28** — copied from `weft_cli.ingest.IndexResult.layers_released`,
    #: so the renderer can name a layer `--reprocess` released and did not rebuild.
    layers_released: tuple[LayerRelease, ...] = ()
    #: Ledger task **43.15** — copied from `weft_cli.ingest.IndexResult.layers_stale`, so the
    #: renderer can name a corpus-scoped layer that has fallen behind without importing that
    #: dataclass.
    layers_stale: tuple[str, ...] = ()
    #: `layers_stale`'s own `(built, of)` pair per name — `weft_cli.ingest.IndexResult.
    #: layers_stale_progress`, copied for the identical reason.
    layers_stale_progress: Mapping[str, tuple[int, int]] = Field(default_factory=dict)
    #: Ledger task **43.21** — copied from `weft_cli.ingest.IndexResult.layers_stale_deleted`,
    #: the identical reason `layers_stale` is.
    layers_stale_deleted: tuple[str, ...] = ()


class AskCommandResult(CommandResult):
    """What `weft ask` produced: a generated `Answer` or ranked passages.

    What `weft ask` produced — a routed, generated `Answer` by default, or, with
    `--retrieve-only`, the ranked passages Phase 0's own contract always returned.

    Exactly one of `answer` / `hits` is populated for a given run — `answer is not None`
    marks the generated shape, `weft_cli.render._render_ask`'s own dispatch (never both at
    once, and never a third field to keep in step with which mode ran; see `AskCommand.run`,
    the one place that decides). `pipeline_name` is set whenever `answer` is: the router's own
    choice, or the name `--pipeline` gave directly — either way, the pipeline that actually
    answered.
    """

    question: str
    pipeline_name: str | None = None
    answer: Answer | None = None
    top_k: int
    format: AskFormat
    hits: tuple[AskHit, ...] = ()
    #: Ledger task **21.1**, populated only under `--explain`. One line per *distinct* producer,
    #: each in that producer's own words — `weft_cli.explain` holds no sentences of its own.
    explanations: tuple[str, ...] = ()
    #: The sentence saying these numbers are not comparable, when they came from more than one
    #: retriever. `None` when they came from one, which is the ordinary case.
    score_note: str | None = None
    #: Ledger task **33.5** — every `wrap`-ed call this run made, populated only under `--explain`.
    stages: tuple[StageRecord, ...] = ()
    #: Ledger task **33.10** — the recorded branch's own wall time, only under `--explain`.
    stages_seconds: float | None = None
    #: Ledger task **40.3** — one line per `Passages.ext` entry, each in its own producer's
    #: words, populated only under `--explain`.
    records: tuple[str, ...] = ()
    #: Ledger task **43.4** — one `list_sources()` read across every store in use, bound to
    #: this ask's own target. `None` only when no store answered at all (none carries
    #: `list_sources`), never when the answer is that nothing is outstanding — `weft_cli.
    #: render._render_ask` reads `SourceCoverage.complete` for that distinction.
    coverage: SourceCoverage | None = None
    #: Ledger task **43.9** — every layer the same `list_sources()` read found, built or not,
    #: filled on every ask path (`_coverage_for`'s own `_AskCoverage.layers`). `weft_cli.render`
    #: narrows this to the pending ones before stating anything under the answer or in the
    #: JSON envelope; a corpus with nothing pending renders exactly as it did before this task.
    layers: tuple[LayerCoverage, ...] = ()


_RENDER_HELP: Final[str] = (
    "extract a directory and print it as one readable document: `weft render ./docs "
    "preview-markdown`. Answers 'what does Weft actually see in this file?' — the question "
    "you have before you trust an index built from it. The second argument names a pipeline "
    "whose last stage is a Renderer; 'preview-plain' and 'preview-markdown' ship. The "
    "rendered text goes to stdout alone, so it can be redirected to a file; what rendering "
    "cost goes to stderr."
)


class RenderArgs(BaseModel):
    """`weft render <path> --pipeline NAME` — task **8.9**.

    **Both fields are positional, and `pipeline` is deliberately one of them.**
    `weft_cli.argparse_gen`'s rule is that a field with no default becomes a positional and one
    with a default becomes a flag — so giving `pipeline` a default would make it `--pipeline`,
    and the default is what this command must not have. Its whole output is whatever the
    document's terminus renders; choosing `preview-plain` on the operator's behalf would be
    this command deciding what "readable" means, which is the one thing `weft_cli.preview`'s own
    module docstring says it does not do. Required-and-positional is the honest shape:
    `weft render ./docs preview-markdown`.

    *Found by running the binary. The first draft said "required flag" in this docstring and
    wrote `--pipeline` into the help text, and the generated surface is a positional either
    way — `weft render ./corpus --pipeline preview-markdown` exited 2 with "unrecognized
    arguments". Every test passed throughout: they construct `RenderArgs` directly and never
    meet argparse.*
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    path: str = Field(description="directory whose files to extract and render")
    pipeline: str = Field(
        description=(
            "pipeline to render through — its last stage must be a Renderer. 'preview-plain' "
            "and 'preview-markdown' ship; `weft pipeline list` shows the rest."
        ),
    )


class RenderCommandResult(CommandResult):
    """The rendered document, and an honest account of what rendering cost.

    `rendition` is `None` for exactly one case: a directory holding nothing any installed
    extractor claims. That is a fact about the filesystem rather than a failure — the same
    distinction `weft index` draws for an empty directory — and it is kept as `None` rather than
    flattened into an empty `Rendition`, which would be indistinguishable from a corpus that
    genuinely rendered to nothing.
    """

    rendition: Rendition | None
    pipeline: str


class RenderCommand:
    """`weft render` — task **8.9**, and a driver for a contract that had none.

    `weft_extract.contract.Renderer` has been published since task 2.27 with two plugins
    registered under it, and until this command **nothing in the tree ever took a `Rendition`
    out of a pipeline**. That is why fitness function 16 carried `plain` and `markdown` in its
    waiver: a document ending in one would resolve, run, and throw its only product away. Task
    2.27's own exit demonstration — "an operator's PDF becomes readable" — was not reachable
    from the CLI at all.

    `permission_class` is `READ`: it opens files and writes to stdout, touching no store and
    creating nothing. `docs/03-cli.md` → *Permissions* is what that class means.
    """

    args_model: ClassVar[type[BaseModel]] = RenderArgs
    result_model: ClassVar[type[CommandResult]] = RenderCommandResult
    permission_class: ClassVar[PermissionClass] = PermissionClass.READ
    help: ClassVar[str] = _RENDER_HELP

    def __init__(self, config: object = None) -> None:
        del config  # this pack takes no `with:`-style configuration

    async def run(self, args: BaseModel, ctx: Context) -> Outcome[CommandResult]:
        """Extract and render one path through the named pipeline.

        Args:
            args: The parsed `RenderArgs`.
            ctx: The command's context, carrying `Dependencies`.

        Returns:
            `Produced` with the `RenderCommandResult`.
        """
        render_args = cast(RenderArgs, args)
        deps = ctx.require(Dependencies)
        rendition = await run_render(
            Path(render_args.path),
            pipeline=render_args.pipeline,
            registry=deps.registry,
            ctx=ctx,
            reports=deps.reports,
            contributions=deps.contributions,
        )
        return Produced(
            value=RenderCommandResult(rendition=rendition, pipeline=render_args.pipeline)
        )


class PluginsListCommandResult(CommandResult):
    """`weft plugins list`'s whole answer — one `PackReport` per discovered distribution."""

    reports: tuple[PackReport, ...]


class PluginsDoctorCommandResult(CommandResult):
    """The fuller answer of `weft plugins doctor`, including tracing status.

    `weft plugins doctor`'s fuller answer — reports, displacements, unconsulted pins, and
    whether the process's `TracerProvider` is real. `tracing` — task **5.1d** — is
    `weft_cli.tracing_status.describe_tracing()`'s own words, read *after* discovery has run
    so it reflects whatever actually happened, `weft-otel` installed or not.

    `skew` — task **5.2e** — is every `weft_cli.skew.SkewReport` `weft_cli.skew.
    detect_skew()` found: a distribution whose installed version does not satisfy another
    installed distribution's own declared specifier, `docs/09-release.md` §2.3 answer 1.
    Deprecation needs no field of its own here — `PackReport.deprecations` already travels
    on `reports`, read by `weft_cli.plugins_report` as a flag beside a pack's status.

    `unreachable_contributions` — task **5.3a** (`S8`) — is every `weft_kernel.resolution.
    Contribution` in `Dependencies.contributions` whose `slot` no pipeline in the catalogue
    declares at all, computed against `weft_cli.pipeline_catalogue.declared_slot_ids` — `02`
    §3 → *Slots*: "`weft plugins doctor` flags a pack whose contributions land in no pipeline
    at all."

    `versions` — task **6.4**, `docs/09-release.md` §1 — is the installed version of each
    distribution reported here, read by `weft_cli.installed_versions.installed_versions`. §1's
    own words: `doctor` "gains one column, not a new command: the version of each active
    distribution... `doctor` has to be able to *say* what is installed before any policy can act
    on it." A distribution with no recorded metadata is **absent from the mapping**, which
    `weft_cli.plugins_report` renders as "(version not recorded)" rather than as a blank.
    """

    reports: tuple[PackReport, ...]
    displaced: tuple[DisplacedRegistration, ...]
    unconsulted_pins: tuple[str, ...]
    tracing: str
    skew: tuple[SkewReport, ...]
    unreachable_contributions: tuple[Contribution, ...]
    versions: dict[str, str] = {}
    #: The embedder this project would resolve when nobody has chosen one — task **28.8**.
    #: `None` when `[services] embed` names one, on `R17.6`'s rule that a choice made is not a
    #: choice to warn about.
    defaulted_embedder: str | None = None


def _defaulted_embedder(deps: Dependencies, resolved: ResolvedPipeline | None) -> str | None:
    """The embedder a `weft index` run used without anyone choosing it, or `None` — `R17.6`.

    A `--pipeline` document names its own embed stage, so the default ran only if that stage names
    it too. Reading `[services] embed` alone told a run that embedded through OpenAI it had used
    `hash` (carried repair `R22.12`).
    """
    if deps.embed_was_selected:
        return None
    if resolved is None:
        return deps.services.embed
    ran = {stage.use for stage in resolved.stages if stage.contract == "Embedder"}
    return deps.services.embed if deps.services.embed in ran else None


def _index_layers(index_args: IndexArgs, deps: Dependencies) -> tuple[str, ...]:
    """The layers one `weft index` run builds, refusing `--layers-only` with none named.

    Raises:
        NoLayersToRunError: `--layers-only` was given and no layer is named anywhere.
    """
    # Ledger task **43.8** — `--layers` overrides `[index] layers` for this one run;
    # `--layers none` runs none whatever the project names. `deps.index_policy.layers`
    # is read only when the flag is absent at all, never merged with it. Resolved before
    # the default path's own plugin checks below, so `--layers-only` with nothing named
    # anywhere is refused by name rather than by whatever `[services] embed` happens to
    # resolve to.
    layers = (
        ()
        if index_args.layers == "none"
        else tuple(name.strip() for name in index_args.layers.split(",") if name.strip())
        if index_args.layers is not None
        else deps.index_policy.layers
    )
    if index_args.layers_only and not layers:
        raise NoLayersToRunError(
            "--layers-only was given, but no layer is named: pass --layers a,b or set "
            "[index] layers in weft.toml."
        )
    return layers


def _require_default_index_plugins(index_args: IndexArgs, deps: Dependencies) -> None:
    """Refuse the default four-stage path when a pack or plugin it promises is missing.

    Raises:
        CommandRefusalError: `INDEX_PACKS` are not all active, or the extractor, embedder or
            store the run would use does not resolve.
    """
    active_refusal = require_active(deps.reports, packs=INDEX_PACKS)
    if active_refusal is not None:
        # `require_active` never resolves `weft_kernel.registry.UnknownPluginError` —
        # it checks a fixed distribution list, not a plugin name — so it has no
        # `valid_options` to lose in the first place; see `weft_engine.registry_bootstrap.
        # require_active`'s own docstring for why it structurally cannot be the gate
        # `require_plugin` below is.
        code, message = active_refusal
        raise CommandRefusalError(message, exit_code=code)

    plugin_refusal: PluginRefusal | None = None
    if index_args.extract is not None:
        plugin_refusal = require_plugin(
            deps.reports,
            registry=deps.registry,
            contract=Extractor,
            name=index_args.extract,
            setting="--extract",
        )
    if plugin_refusal is None:
        plugin_refusal = require_plugin(
            deps.reports,
            registry=deps.registry,
            contract=Embedder,
            name=deps.services.embed,
            setting="[services] embed",
        )
    if plugin_refusal is None:
        plugin_refusal = require_plugin(
            deps.reports,
            registry=deps.registry,
            contract=NodeStore,
            name=deps.services.store,
            setting="[services] store",
        )
    _raise_for_plugin_refusal(plugin_refusal)


def _write_index_run_record(
    deps: Dependencies,
    path: str,
    resolved_pipeline: ResolvedPipeline,
    content_hashes: tuple[str, ...],
) -> None:
    """Persist the run record of one `--pipeline` index under `DEFAULT_INDEX_RUNS_DIR`."""
    record = build_run_record(
        recorded_at=datetime.now(UTC).isoformat(),
        resolved_pipeline=resolved_pipeline,
        corpus=corpus_identity(path, content_hashes),
        corpus_digest_basis=CorpusDigestBasis.DOCUMENT_BYTES,
        reports=deps.reports,
        distribution_versions=active_distribution_versions(deps.reports),
    )
    write_run_record(record, DEFAULT_INDEX_RUNS_DIR / f"{uuid.uuid4()}.json")


class IndexCommand:
    """`weft index` — see the module docstring for what moved and what did not.

    **Task 4.0.** `--pipeline` resolves a document through `weft_cli.ingest.run_index`'s own
    new `pipeline` parameter, exactly the way `AskCommand._run_generating` already resolves
    `--pipeline` for a query. `INDEX_PACKS`/`[services] embed`/`[services] store` are
    the default four-stage path's own promises — a named document may need none of those
    three distributions and reads no `[services]` value at all (the module docstring's *"Q3,
    settled"*), so this command checks neither when `--pipeline` is given; `run_index` raises
    its own `weft_kernel.runner.PipelineResolutionError` family member for whatever the
    document itself gets wrong, the same family `_raise_for_plugin_refusal` maps the default
    path's own refusals into.
    """

    args_model: ClassVar[type[BaseModel]] = IndexArgs
    result_model: ClassVar[type[CommandResult]] = IndexCommandResult
    permission_class: ClassVar[PermissionClass] = PermissionClass.WRITE
    help: ClassVar[str] = _INDEX_HELP

    def __init__(self, config: object = None) -> None:
        del config  # this pack takes no `with:`-style configuration

    async def run(self, args: BaseModel, ctx: Context) -> Outcome[CommandResult]:
        """Index one directory, then run the automatic reconcile pass.

        Args:
            args: The parsed `IndexArgs`.
            ctx: The command's context, carrying `Dependencies`.

        Returns:
            `Produced` with the `IndexCommandResult`.

        Raises:
            ConflictingIndexModeError: Both `--extract` and `--pipeline` were given.
            NoLayersToRunError: `--layers-only` was given with no layer named.
            CommandRefusalError: The default path's packs or plugins do not resolve.
        """
        index_args = cast(IndexArgs, args)  # `args_model` is the isinstance contract
        deps = ctx.require(Dependencies)
        if index_args.target is None:
            # Ledger **34.11** — an untargeted index writes wherever the primary store's own
            # live pointer says, so this refuses before writing anything if this project's own
            # participants already disagree about what that is (`_require_target_exists`'s own
            # footing for every read command).
            await check_participants_agree(deps)

        if index_args.pipeline is not None and index_args.extract is not None:
            raise ConflictingIndexModeError(
                "--extract and --pipeline cannot both be given: --extract narrows the "
                "default four-stage path's own auto-discovery to one named extractor; "
                "--pipeline names a whole document whose own 'extract' stage already names "
                "its plugin. Choose one."
            )

        layers = _index_layers(index_args, deps)

        if index_args.pipeline is None and not index_args.layers_only:
            # `--layers-only` skips this block on the identical footing `--pipeline` already
            # does, just below: `INDEX_PACKS`/`[services] embed`/`[services] store` are
            # promises the *base* run makes, and `layers_only=True` means the base does not
            # run at all (no extract, no base pipeline) — see `weft_cli.ingest.run_index`'s
            # own docstring. Checking them here would refuse a layers-only run over an
            # already-indexed corpus for a plugin that invocation never touches.
            _require_default_index_plugins(index_args, deps)

        on_batch = (
            deps.token_sink.batch_progress
            if isinstance(deps.token_sink, ProgressReporter)
            else None
        )
        result = await run_index_for(
            deps,
            Path(index_args.path),
            ctx=ctx,
            pipeline=index_args.pipeline,
            extractor=index_args.extract,
            reprocess=index_args.reprocess,
            batch_size=index_args.batch_size,
            default_batch_size=DEFAULT_BATCH_SIZE,
            on_batch=on_batch,
            retry_failed=index_args.retry_failed,
            target=index_args.target,
            layers=layers,
            layers_only=index_args.layers_only,
        )
        if result.resolved_pipeline is not None:
            # Carried repair R11.2's second half: `stores_in_use`'s run-record source only ever
            # sees a store a `--pipeline` run named if this run wrote one down. `model_versions`
            # is deliberately left at its default — the derivation lives in
            # `weft_cli.eval_commands.model_versions_of`, and reaches only
            # `_incomparable_reasons`, which an index record never does; copying it here
            # to fill a field nothing reads would be a second implementation of it. The default
            # four-stage path resolves no document, so it writes nothing: `RunRecord.
            # resolved_pipeline` is mandatory, and the only store that path writes to is
            # `[services] store`, which `stores_in_use` already counts unconditionally.
            _write_index_run_record(
                deps, index_args.path, result.resolved_pipeline, result.content_hashes
            )
        reconcile_result = await self._auto_reconcile(
            index_args.reconcile,
            deps=deps,
            ctx=ctx,
            target=index_args.target,
            spare=frozenset(result.generations_withdrawn),
        )
        defaulted_embedder = _defaulted_embedder(deps, result.resolved_pipeline)
        return Produced(
            value=IndexCommandResult(
                summary=result.summary,
                stored_count=result.stored_count,
                reconcile=reconcile_result,
                source_changes=result.source_changes,
                defaulted_embedder=defaulted_embedder,
                documents_discovered=len(result.document_ids),
                documents_indexed=result.documents_indexed,
                documents_failed=result.documents_failed,
                payload_indexes=result.payload_indexes,
                degraded_expansions=result.degraded_expansions,
                target=result.target,
                target_live=result.target_live,
                target_stopped_being_live=result.target_stopped_being_live,
                target_now_live=result.target_now_live,
                layers_changed=result.layers_changed,
                layers_failed=result.layers_failed,
                layers_joined=result.layers_joined,
                stores_without_withdraw=result.stores_without_withdraw,
                stores_without_carry=result.stores_without_carry,
                layers_reclaimed=result.layers_reclaimed,
                layers_released=result.layers_released,
                layers_stale=result.layers_stale,
                layers_stale_progress=result.layers_stale_progress,
                layers_stale_deleted=result.layers_stale_deleted,
            )
        )

    async def _auto_reconcile(
        self,
        mode: ReconcileMode,
        *,
        deps: Dependencies,
        ctx: Context,
        target: str | None,
        spare: frozenset[GenerationId],
    ) -> ReconcileCommandResult:
        """Run the automatic reconcile pass that follows a successful index.

        The automatic post-index pass, task **5.1c** — `docs/02-extension-model.md` §3 →
        *Slots*, "Tested by G7": run unconditionally after a successful index, in whichever
        mode `--reconcile` named (hardcoded `repair` unless a person opted this run into
        `full`), against `[services] store` and every other registered `Reconcilable` — the
        identical participants `weft reconcile` itself would ask, found the same way
        (`weft_cli.reconcile.participants`), so the automatic pass and a person's own later
        `weft reconcile` can never disagree about who converges.

        **Run for `--pipeline` too, deliberately, not only the default four-stage path.**
        `run_index`'s own "Q3, settled" promise is that `[services] embed`/`store` are not
        read *to build that run's own stages* when a document names them instead; it says
        nothing about a *separate*, subsequent convergence step, which is a project-wide
        concern rather than a fact about one pipeline's own stage list. Skipping it for
        `--pipeline` would silently drop `--reconcile full` on that path with no refusal and
        no explanation — exactly the surprise this task exists to prevent — so this runs the
        same way regardless of which path indexed. A `[services] store` that resolves to
        nothing registered simply contributes no `NodeStore` participant (`weft_cli.fanout`'s
        own filtering, not a refusal), so a `--pipeline` project with no store configured at
        all still indexes cleanly; other `Reconcilable` packs are still asked.

        `spare` is the generations this run withdrew, which the pass leaves for the layer's next
        build or an explicit `weft reconcile` (repair **R43.47**).
        """
        targets = reconcile_participants(registry=deps.registry, store_names=_stores_in_use(deps))
        _register_corpus(ctx, deps)
        async with claim_all_writers(targets, store_target=target, command="weft index"):
            estimates = (
                await estimate_everywhere(mode, targets=targets, ctx=ctx, target=target)
                if mode is ReconcileMode.FULL
                else ()
            )
            outcomes = await reconcile_everywhere(
                mode, targets=targets, ctx=ctx, target=target, spare=spare
            )
        return ReconcileCommandResult(
            mode=mode, dry_run=False, participants=outcomes, estimates=estimates
        )


class AskCommand:
    """Route a `weft ask` question to a pipeline and answer it.

    `weft ask` — task **3.11**: routes by default, so the question a user asks reaches
    the pipeline the router names without them knowing a second command exists.

    **The surface decision, argued against `docs/03-cli.md`.** Before this task, `ask` was
    Phase 0's own retrieve-only command and `route` (task 2.8) was an additive, separate
    entry point that actually reached the router — two commands, and a caller had to know
    which one to type. `docs/03-cli.md` → *Command surface* already published the answer
    without anyone updating it for `route`'s existence: `weft ask <question>` is documented
    as *"query, streaming the answer with citations"* — routed generation — and the table
    never lists `route` at all. This class makes that already-published surface real: `ask`
    absorbs `RouteCommand`'s own body verbatim (the only change is where it lives), and
    `route` is retired as a registered name rather than kept as a second spelling of the
    same thing (`docs/internal/build-ledger.md`'s 3.11 entry has the fuller argument).

    **Naming a pipeline directly** (the capability the ledger's own note asked this task to
    make sure stayed reachable) is new, not a re-spelling of what `route` did: `route` never
    took a pipeline name either — it only ever ran the router. `--pipeline <name>` bypasses
    the router and runs `weft_cli.route_ask.run_named_ask` instead, against the same
    catalogue `weft pipeline show` resolves names against.

    **`--retrieve-only` keeps Phase 0's own contract reachable**, deliberately not deleted:
    `manual/quickstart.md`'s zero-configuration walkthrough and `weft eval baseline`'s V3
    baseline (`docs/09-release.md` §4.3, `weft_cli.eval_baseline`) both need a deterministic,
    credential-free, network-free measurement — a `weft.toml` with no `[llm.roles]` table maps
    nothing (`weft_llm.roles.LLMRoles`'s own "no silent default" clause), so routed generation
    refuses loudly rather than running with nothing configured, exactly the gap `--retrieve-
    only` closes for a caller who wants no model call at all.
    """

    args_model: ClassVar[type[BaseModel]] = AskArgs
    result_model: ClassVar[type[CommandResult]] = AskCommandResult
    permission_class: ClassVar[PermissionClass] = PermissionClass.READ
    help: ClassVar[str] = _ASK_HELP

    def __init__(self, config: object = None) -> None:
        del config

    async def run(self, args: BaseModel, ctx: Context) -> Outcome[CommandResult]:
        """Answer one question, recording each stage's timing under `--explain`.

        Args:
            args: The parsed `AskArgs`.
            ctx: The command's context, carrying `Dependencies`.

        Returns:
            The chosen branch's outcome, carrying stage records under `--explain`.
        """
        ask_args = cast(AskArgs, args)
        deps = ctx.require(Dependencies)

        if ask_args.retrieve_only and ask_args.pipeline is not None:
            branch = self._run_retrieve_only_named(ask_args, deps=deps, ctx=ctx)
        elif ask_args.retrieve_only:
            branch = self._run_retrieve_only(ask_args, deps=deps, ctx=ctx)
        else:
            branch = self._run_generating(ask_args, deps=deps, ctx=ctx)

        if not ask_args.explain:
            return await branch

        started_at = time.monotonic()
        with recording() as scope:
            outcome = await branch
            elapsed = time.monotonic() - started_at
        if isinstance(outcome, Produced) and isinstance(outcome.value, AskCommandResult):
            return Produced(
                value=outcome.value.model_copy(
                    update={"stages": scope.records, "stages_seconds": elapsed}
                )
            )
        return outcome

    async def _run_retrieve_only_named(
        self, ask_args: AskArgs, *, deps: Dependencies, ctx: Context
    ) -> Outcome[CommandResult]:
        """Run a named pipeline to its last stage for `--retrieve-only`, with no model call.

        `--retrieve-only --pipeline <name>` — repair **R21.5**: run the named pipeline
        through to its own last stage, with no router and no model call, unless that stage
        is a `Generator`, which is the one shape `--retrieve-only` still refuses.

        Resolution is `weft_cli.route_ask.named_pipeline`'s — an unknown name is refused by
        that lookup alone, before this method decides anything, so the two commands cannot
        disagree about what "not found" means for a bare pipeline name (`_raise_for_plugin_
        refusal`'s own "one code path, not two" footing, one caller further).
        """
        await _require_target_exists(deps, ask_args.target)
        pipeline_name = cast(str, ask_args.pipeline)
        catalogue = full_catalogue(reports=deps.reports)
        named_pipeline(pipeline_name, catalogue=catalogue)
        if self._generates(pipeline_name, deps=deps):
            alternatives = pipelines_producing(
                ContextPacker, catalogue=catalogue, registry=deps.registry
            )
            raise ConflictingAskModeError(
                f"--retrieve-only and --pipeline '{pipeline_name}' cannot both be given: "
                f"'{pipeline_name}' ends in a Generator and would call a model. Run it "
                f"without --retrieve-only, or choose a pipeline that already ends in a "
                f"retrieval stage and calls no model: "
                f"{', '.join(repr(name) for name in alternatives) or '(none installed)'}."
            )
        coverage_outcome = await _coverage_for(deps, ask_args.target)
        if not isinstance(coverage_outcome, Produced):
            return coverage_outcome
        _raise_for_uninstalled_route_layers(catalogue, deps=deps)
        if not ask_args.allow_pending:
            _raise_if_pending(
                pipeline_name,
                catalogue=catalogue,
                ask_coverage=coverage_outcome.value,
                deps=deps,
            )
        passages = await run_named_retrieve(
            ask_args.question,
            pipeline_name=pipeline_name,
            registry=deps.registry,
            reports=deps.reports,
            ctx=ctx,
            llm=deps.llm,
            services=deps.services,
            sink=deps.token_sink,
            contributions=deps.contributions,
            roles=deps.roles,
            target=ask_args.target,
        )
        return Produced(
            value=AskCommandResult(
                question=ask_args.question,
                top_k=ask_args.top_k,
                format=ask_args.format,
                pipeline_name=pipeline_name,
                answer=None,
                hits=hits_for([p.scored for p in sorted(passages.passages, key=lambda p: p.rank)]),
                records=record_lines(passages.ext) if ask_args.explain else (),
                coverage=coverage_outcome.value.coverage,
                layers=coverage_outcome.value.layers,
            )
        )

    @staticmethod
    def _generates(pipeline_name: str, *, deps: Dependencies) -> bool:
        """Whether the named pipeline's **resolved** last stage is a `Generator`.

        Resolved, not as written. `pipelines_producing` reads `Pipeline.stages`, and a document
        spelled `extends:` plus `replace:` carries none of its own — so every derived generating
        rung was invisible to it, and `--retrieve-only --pipeline rewrite-then-retrieve` reached
        the runner. With `[llm.roles]` configured that is a query rewrite **and** a generated
        answer, two model calls, under the one flag whose whole promise is that it makes none.
        Found at Phase 28's close by asking this check's own walk how many documents it reaches.

        `resolve_named_pipeline` is pure — no I/O, nothing run — so this stays a decision taken
        before any plugin is constructed, which is what `ConflictingAskModeError` promises.
        """
        resolved = resolve_named_pipeline(
            pipeline_name,
            registry=deps.registry,
            reports=deps.reports,
            contributions=deps.contributions,
        )
        if not resolved.stages:
            return False
        last = resolved.stages[-1].use
        return last in deps.registry.names_for(Generator)

    async def _run_retrieve_only(
        self, ask_args: AskArgs, *, deps: Dependencies, ctx: Context
    ) -> Outcome[CommandResult]:
        """Answer `--retrieve-only` by embedding the question and searching directly.

        Phase 0's own contract, unchanged: embed the question, search directly, print
        ranked passages — no router, no generation, no model call.
        """
        refusal = require_plugin(
            deps.reports,
            registry=deps.registry,
            contract=Embedder,
            name=deps.services.embed,
            setting="[services] embed",
        )
        if refusal is None:
            refusal = require_plugin(
                deps.reports,
                registry=deps.registry,
                contract=NodeStore,
                name=deps.services.store,
                setting="[services] store",
            )
        _raise_for_plugin_refusal(refusal)
        await _require_target_exists(deps, ask_args.target)

        results = await run_ask(
            ask_args.question,
            registry=deps.registry,
            ctx=ctx,
            top_k=ask_args.top_k,
            embedder=deps.services.embed,
            store=deps.services.store,
            target=ask_args.target,
            embedder_config=embed_config_for(deps.registry, deps.services),
        )
        explanations: tuple[str, ...] = ()
        if ask_args.explain:
            # The class, not an instance: `vector_score_semantics` is a `ClassVar`, `run_ask`
            # closes the instance it built before returning, and building a second store to read
            # a constant off it would open a connection to answer a documentation question.
            store_class = unwrap_factory(
                deps.registry.entry(NodeStore, deps.services.store).factory
            )
            explanations = (
                ScoreExplanation.of(
                    store_class,
                    produced_by=deps.services.store,
                    attribute="vector_score_semantics",
                ).rendered(),
            )
        coverage_outcome = await _coverage_for(deps, ask_args.target)
        if not isinstance(coverage_outcome, Produced):
            return coverage_outcome
        return Produced(
            value=AskCommandResult(
                question=ask_args.question,
                top_k=ask_args.top_k,
                format=ask_args.format,
                hits=hits_for(results),
                explanations=explanations,
                # One store arm produced every number here, so there is nothing incomparable to
                # report — `incomparable_note` would return `None` for a one-element sequence and
                # calling it would be asking a question whose answer is structural.
                score_note=None,
                coverage=coverage_outcome.value.coverage,
                layers=coverage_outcome.value.layers,
            )
        )

    async def _run_generating(
        self, ask_args: AskArgs, *, deps: Dependencies, ctx: Context
    ) -> Outcome[CommandResult]:
        """Serve `weft ask`'s default answer: generated text with citations, not raw passages.

        The default: route through the installed router, or run `--pipeline`'s own
        named pipeline directly — either way, a generated, cited `Answer`.

        `[services]` is checked first, as the retrieve-only path checks it: `build_services`
        resolves both roles unconditionally, and without this a failed pack surfaced as a bare
        `UnknownPluginError` with no reason attached (carried repair `R18.2`).
        """
        refusal = require_plugin(
            deps.reports,
            registry=deps.registry,
            contract=Embedder,
            name=deps.services.embed,
            setting="[services] embed",
        )
        if refusal is None:
            refusal = require_plugin(
                deps.reports,
                registry=deps.registry,
                contract=NodeStore,
                name=deps.services.store,
                setting="[services] store",
            )
        _raise_for_plugin_refusal(refusal)
        await _require_target_exists(deps, ask_args.target)
        # Ledger task **43.9** — read before routing or running, so a rung whose layer is
        # not ready everywhere can be refused (or the router told to leave it out) before
        # anything runs, on one `list_sources()` read.
        coverage_outcome = await _coverage_for(deps, ask_args.target)
        if not isinstance(coverage_outcome, Produced):
            return coverage_outcome
        ask_coverage = coverage_outcome.value
        ready = ready_layers(ask_coverage.layers)
        catalogue = full_catalogue(reports=deps.reports)
        # R43.13: a misspelt route.requires is a fault in the document, never a layer that is
        # merely not built yet — checked over the whole catalogue before either branch below,
        # so a routed ask over such a document is refused rather than routed around it.
        _raise_for_uninstalled_route_layers(catalogue, deps=deps)
        if ask_args.pipeline is not None:
            pipeline_name = ask_args.pipeline
            if not ask_args.allow_pending:
                _raise_if_pending(
                    pipeline_name, catalogue=catalogue, ask_coverage=ask_coverage, deps=deps
                )
            answer = await run_named_ask(
                ask_args.question,
                pipeline_name=pipeline_name,
                registry=deps.registry,
                reports=deps.reports,
                ctx=ctx,
                llm=deps.llm,
                services=deps.services,
                sink=deps.token_sink,
                contributions=deps.contributions,
                # Ledger task **9.0** — every declared role `[services]` selected reaches
                # this query-path run, exactly as `deps.llm` above already does.
                roles=deps.roles,
                target=ask_args.target,
            )
        else:
            pipeline_name, answer = await run_routed_ask(
                ask_args.question,
                registry=deps.registry,
                reports=deps.reports,
                ctx=ctx,
                llm=deps.llm,
                services=deps.services,
                sink=deps.token_sink,
                contributions=deps.contributions,
                roles=deps.roles,
                target=ask_args.target,
                ready_layers=ready,
            )
        explanations: tuple[str, ...] = ()
        note: str | None = None
        if ask_args.explain:
            # `Passage.retrieved_by` is the one place that records which retriever produced a
            # passage, and a fan-out — `multi-retriever`, `hybrid` — puts several in one list.
            produced_by = tuple(passage.retrieved_by for passage in answer.used)
            # Keyed by **plugin** name, not by label: a fan-out writes `<plugin>:<arm>` and
            # `hybrid:vector` is not a registered name, so filtering on the whole label built an
            # empty mapping and every arm reported an absence. `explanations_for` falls back to
            # the part before the colon, and this is the half that has to put it there.
            registered = deps.registry.names_for(Retriever)
            wanted = {label.partition(":")[0] for label in produced_by} | set(produced_by)
            producers = {
                name: unwrap_factory(deps.registry.entry(Retriever, name).factory)
                for name in wanted
                if name in registered
            }
            # Built the way a query run builds it (`weft_engine.run_services`): a store
            # instance, not its class, because `text_score_semantics` since ledger **21.7** is
            # a fact about `text_mode`, which only a configured instance carries. Bound to
            # `ask_args.target`, ledger task **34.6**, so an explanation reads the target this
            # run actually answered from.
            store = await bind_store(
                deps.registry.entry(NodeStore, deps.services.store).factory(None),
                ask_args.target,
                store_name=deps.services.store,
            )
            explanations = tuple(
                explanation.rendered()
                for explanation in explanations_for(produced_by, producers=producers)
            ) + tuple(
                explanation.rendered()
                for explanation in arm_explanations(produced_by, producers=producers, store=store)
            )
            if ask_args.pipeline is None:
                # Ledger task **43.9** — routed path only: a rung reached by name was
                # already refused or accepted above, so there is nothing left to exclude.
                explanations += _excluded_rung_explanations(
                    catalogue, ask_coverage=ask_coverage, ready=ready, deps=deps
                )
            note = incomparable_note(produced_by)
        return Produced(
            value=AskCommandResult(
                question=ask_args.question,
                top_k=ask_args.top_k,
                format=ask_args.format,
                pipeline_name=pipeline_name,
                answer=answer,
                explanations=explanations,
                score_note=note,
                coverage=ask_coverage.coverage,
                layers=ask_coverage.layers,
            )
        )


class PluginsListCommand:
    """`weft plugins list` — see the module docstring."""

    args_model: ClassVar[type[BaseModel]] = NoArgs
    result_model: ClassVar[type[CommandResult]] = PluginsListCommandResult
    permission_class: ClassVar[PermissionClass] = PermissionClass.READ
    help: ClassVar[str] = _PLUGINS_LIST_HELP

    def __init__(self, config: object = None) -> None:
        del config

    async def run(self, args: BaseModel, ctx: Context) -> Outcome[CommandResult]:
        """Report every discovered distribution.

        Args:
            args: The parsed `NoArgs`.
            ctx: The command's context, carrying `Dependencies`.

        Returns:
            `Produced` with the `PluginsListCommandResult`.
        """
        del args
        deps = ctx.require(Dependencies)
        return Produced(value=PluginsListCommandResult(reports=deps.reports))


class PluginsDoctorCommand:
    """`weft plugins doctor` — see the module docstring."""

    args_model: ClassVar[type[BaseModel]] = NoArgs
    result_model: ClassVar[type[CommandResult]] = PluginsDoctorCommandResult
    permission_class: ClassVar[PermissionClass] = PermissionClass.READ
    help: ClassVar[str] = _PLUGINS_DOCTOR_HELP

    def __init__(self, config: object = None) -> None:
        del config

    async def run(self, args: BaseModel, ctx: Context) -> Outcome[CommandResult]:
        """Diagnose discovery: displacements, pins, tracing, skew and reachability.

        Args:
            args: The parsed `NoArgs`.
            ctx: The command's context, carrying `Dependencies`.

        Returns:
            `Produced` with the `PluginsDoctorCommandResult`.
        """
        del args
        deps = ctx.require(Dependencies)
        catalogue = full_catalogue(reports=deps.reports)
        declared = declared_slot_ids(catalogue)
        unreachable = tuple(
            contribution for contribution in deps.contributions if contribution.slot not in declared
        )
        return Produced(
            value=PluginsDoctorCommandResult(
                reports=deps.reports,
                displaced=deps.registry.displaced(),
                unconsulted_pins=tuple(sorted(deps.registry.unconsulted_pins())),
                tracing=describe_tracing(),
                skew=detect_skew(),
                unreachable_contributions=unreachable,
                versions=installed_versions(report.distribution for report in deps.reports),
                defaulted_embedder=None if deps.embed_was_selected else deps.services.embed,
            )
        )


class SourcesListArgs(BaseModel):
    """`weft sources list [--status <status>]` — task **36.4**.

    `status` filters to one `SourceStatus`, e.g. `failed`; omitted, every recorded status
    is listed.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: SourceStatus | None = Field(
        default=None,
        description=(
            "keep only sources at this status (e.g. 'failed'). Omit to list every status."
        ),
    )
    target: str | None = Field(
        default=None,
        description=(
            "list sources from this target instead of the live one (ledger task 34.6). "
            "Refused for a target that does not exist, naming every target that does. Omit "
            "for the live one."
        ),
    )


class ListedSource(BaseModel):
    """One recorded source, and which store's own records it came from.

    `store` names the `NodeStore` plugin `SourcesListCommand.run` read the record off —
    task **R36.4**: a project that indexes into more than one store (a pipeline naming a
    second `NodeStore` stage, e.g. a graph store) can no longer be listed from `[services]
    store` alone, so an entry has to say which store it is answering for.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    store: str
    record: SourceRecord


class SourcesListCommandResult(CommandResult):
    """Lets an operator find a failed or stale source across every store in use.

    `weft sources list`'s whole answer — every recorded `SourceRecord` every store in use
    reported, filter applied, sorted by `(record.uri, store)`.
    """

    sources: tuple[ListedSource, ...]
    #: The `--status` filter the list was taken under, so an empty answer can say which.
    status: SourceStatus | None = None


class SourcesListCommand:
    """List every recorded source across the stores a project indexes into.

    `weft sources list` — task **36.4**, widened at **R36.4**: an operator finds a failed
    source without reading a database. Reads `list_sources()` off every `NodeStore` a project
    indexes into — the same set `weft delete`/`weft reconcile` fan out across, from
    `_stores_in_use` — filters by `SourcesListArgs.status` when given, and reports every
    `SourceRecord` alongside the store it came from; a failed one carries its own
    `SourceFailure`, which `weft_cli.render` prints.
    """

    args_model: ClassVar[type[BaseModel]] = SourcesListArgs
    result_model: ClassVar[type[CommandResult]] = SourcesListCommandResult
    permission_class: ClassVar[PermissionClass] = PermissionClass.READ
    help: ClassVar[str] = _SOURCES_LIST_HELP

    def __init__(self, config: object = None) -> None:
        del config

    async def run(self, args: BaseModel, ctx: Context) -> Outcome[CommandResult]:
        """List every recorded source across the stores in use, filtered by status.

        Args:
            args: The parsed `SourcesListArgs`.
            ctx: The command's context, carrying `Dependencies`.

        Returns:
            `Produced` with the `SourcesListCommandResult`, or the first store read
            that did not produce.

        Raises:
            UnresolvedPluginNameError: `[services] store` does not resolve.
        """
        typed = cast(SourcesListArgs, args)
        deps = ctx.require(Dependencies)
        _raise_for_plugin_refusal(
            require_plugin(
                deps.reports,
                registry=deps.registry,
                contract=NodeStore,
                name=deps.services.store,
                setting="[services] store",
            )
        )
        await _require_target_exists(deps, typed.target)
        read = await _read_sources_by_store(deps, typed.target)
        if not isinstance(read, Produced):
            return read
        entries: list[ListedSource] = [
            ListedSource(store=name, record=record)
            for name, records in read.value
            for record in records
            if typed.status is None or record.status == typed.status
        ]
        sources = tuple(sorted(entries, key=lambda entry: (entry.record.uri, entry.store)))
        return Produced(value=SourcesListCommandResult(sources=sources, status=typed.status))


class ListedTarget(BaseModel):
    """One target in one store's own catalogue — `weft target list`'s own row, ledger task **34.6**.

    `live`/`previous` mark this target against `weft_store.contract.TargetCatalogue.
    live`/`.previous`; `embedding` is `None` when nothing has claimed this target yet
    (`weft_engine.targets.claim_embedding_for_write` never ran against it), which `weft_cli.render`
    reports as *"embedding not recorded"* rather than as an empty identity.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    store: str
    name: str
    live: bool
    previous: bool
    embedding: EmbeddingIdentity | None
    sources: int
    #: Ledger task **43.10** — every layer built on every source of this target
    #: (`weft_cli.coverage.ready_layers`), sorted. Empty for a target with none, or none
    #: complete on every one of its sources.
    layers_complete: tuple[str, ...] = ()


class TargetListCommandResult(CommandResult):
    """Lets an operator see every index target before promoting or dropping one.

    `weft target list`'s whole answer — every target every `TargetHolding` store in use
    holds, sorted by `(store, name)`.
    """

    targets: tuple[ListedTarget, ...]


async def _listed_targets(
    store: str,
    catalogue_of: Callable[[], Awaitable[Outcome[TargetCatalogue]]],
    sources_of: Callable[[str], Awaitable[Outcome[tuple[SourceRecord, ...]]]],
) -> list[ListedTarget]:
    """Every target one `TargetHolding` store holds, with its source count and complete layers.

    Args:
        store: The store's registered name.
        catalogue_of: The wrapped read of the store's target catalogue.
        sources_of: The wrapped read of one named target's source records.

    Returns:
        One `ListedTarget` per catalogued target, in catalogue order.
    """
    catalogue_outcome = await catalogue_of()
    catalogue = produced_value(catalogue_outcome, stage="target:catalogue")
    listed: list[ListedTarget] = []
    for record in catalogue.targets:
        sources_outcome = await sources_of(record.name)
        source_records = produced_value(sources_outcome, stage="target:sources")
        listed.append(
            ListedTarget(
                store=store,
                name=record.name,
                live=record.name == catalogue.live,
                previous=record.name == catalogue.previous,
                embedding=record.embedding,
                sources=len(source_records),
                # Ledger task **43.10** — the layers built on every source of
                # this target, from the same `list_sources()` read.
                layers_complete=tuple(sorted(ready_layers(layer_coverage_of(source_records)))),
            )
        )
    return listed


class TargetListCommand:
    """`weft target list` — ledger task **34.6**.

    Reads `[services] store`'s own catalogue, and every other `NodeStore` `_stores_in_use` names
    that also satisfies `TargetHolding` — the graph pack's store since task 34.11; a store in use
    that does not is left out rather than refused, since it holds no targets to list. `[services]
    store` itself is refused by name — `StoreHoldsNoTargetsError` — when it does not satisfy
    `TargetHolding`: there is nothing this command could list, and silence would read as "no
    targets" rather than "this store has no notion of one".

    Each target's source count is read by binding a fresh handle to it and calling
    `list_sources()` — the identical walk `weft_cli.fanout.built` would perform, done directly
    here since a target list is read-only and every handle is closed the moment its count is
    taken.

    `permission_class` is `READ`: it opens connections and reads catalogues, writing nothing.
    """

    args_model: ClassVar[type[BaseModel]] = NoArgs
    result_model: ClassVar[type[CommandResult]] = TargetListCommandResult
    permission_class: ClassVar[PermissionClass] = PermissionClass.READ
    help: ClassVar[str] = _TARGET_LIST_HELP

    def __init__(self, config: object = None) -> None:
        del config

    async def run(self, args: BaseModel, ctx: Context) -> Outcome[CommandResult]:
        """List every target held by each `TargetHolding` store in use.

        Args:
            args: The parsed `NoArgs`.
            ctx: The command's context, carrying `Dependencies`.

        Returns:
            `Produced` with the `TargetListCommandResult`.
        """
        del args
        deps = ctx.require(Dependencies)
        store_names = sorted({deps.services.store} | _stores_in_use(deps))
        listed: list[ListedTarget] = []
        for name in store_names:
            entry = deps.registry.entry(NodeStore, name)
            instance = entry.factory(None)
            if not isinstance(instance, TargetHolding):
                if name == deps.services.store:
                    raise StoreHoldsNoTargetsError(store_name=name, target=None)
                continue

            async def _catalogue(
                instance: TargetHolding = instance,
            ) -> Outcome[TargetCatalogue]:
                return Produced(value=await instance.target_catalogue())

            async def _sources_for(
                record_name: str, instance: TargetHolding = instance
            ) -> Outcome[tuple[SourceRecord, ...]]:
                # `bind_target`'s own `Self` is `TargetHolding`-typed here, this
                # closure's own narrowing; the built instance is a `NodeStore` by
                # construction (`entry` is `NodeStore`'s own registration), which is
                # the fact this `cast` states rather than invents.
                handle = cast(NodeStore, await instance.bind_target(target_name(record_name)))
                return Produced(value=tuple(await handle.list_sources()))

            wrapped_catalogue = wrap(
                _catalogue,
                distribution=entry.distribution,
                contract=NodeStore.__qualname__,
                plugin=name,
                stage="target:catalogue",
            )
            wrapped_sources = wrap(
                _sources_for,
                distribution=entry.distribution,
                contract=NodeStore.__qualname__,
                plugin=name,
                stage="target:sources",
            )
            try:
                listed.extend(await _listed_targets(name, wrapped_catalogue, wrapped_sources))
            finally:
                await aclose(
                    instance,
                    distribution=entry.distribution,
                    contract=NodeStore.__qualname__,
                    plugin=name,
                )
        listed.sort(key=lambda target: (target.store, target.name))
        return Produced(value=TargetListCommandResult(targets=tuple(listed)))


_INIT_HELP = (
    "scaffold weft.toml in the current directory — every key commented out, offline by default"
)

_INIT_TEMPLATE = """\
# Weft project configuration. See weft.toml.example in the repository, or
# docs/03-cli.md -> Project context, for the full reference — every key below
# has a built-in default, so a clean checkout with nothing uncommented still
# runs entirely offline, against the deterministic hash embedder and pgvector.
# Explicit flags beat this file; this file beats the built-in defaults below.
# `weft config get --origin` prints, per key, which of the three answered it.

[services]
# embed = "hash"
# 'hash' carries no semantic meaning — it digests the text, so a
# ranking built from it says the pipeline ran and nothing about
# relevance. Set [services] embed in weft.toml to change it:
# 'openai-embeddings' for the vendor, or
# 'openai-compatible-embeddings' pointed at an OpenAI-compatible
# server you run, which needs no account.
# store = "pgvector"

[permissions]
# overwrite = "ask"
# destroy = "ask"

[reconcile]
# mode = "full"

# [packs.store]
# dsn = "${env:WEFT_DATABASE_URL}"
"""


class InitCommandResult(CommandResult):
    """`weft init`'s whole answer — the path it wrote."""

    path: str


class InitCommand:
    """`weft init` — scaffold `weft.toml`, task **3.7**.

    `docs/02-extension-model.md` §2's "`weft init`... complete[s] with zero pack code
    executed" is corrected in the same commit that ships this class — see `weft_cli.
    pipeline_commands`'s own module docstring for why that claim stopped being true the
    moment task 3.2 made every subcommand's own grammar depend on the whole registry.
    `weft init` still touches nothing about *what is installed*: it writes a fixed
    template with every key commented out, so its own `run()` reads no `PackReport` and
    resolves no plugin name — the discovery `weft_cli.cli.main` already paid to build the
    parser this command was found on is simply unused by this command's own body, the
    identical relationship every other command here already has to the registry entries
    it does not happen to need.

    **`write`-class, repaired 2026-08-20 from `overwrite`** — see `TargetAlreadyExistsError`'s
    own docstring, and `weft_cli.pipeline_commands`'s module docstring for the argument shared
    with `PipelineDeriveCommand`, for why: scaffolding into a project with no `weft.toml` yet
    is a *create*, `docs/03-cli.md`'s own `write`-row example, not a *replace*. A `weft.toml`
    already present is refused outright, loudly, naming the path — never silently replaced,
    never asked about — rather than losing whatever it held with no upsert-safety.
    `weft.toml.example`'s own copy-by-hand path — what `manual/quickstart.md` actually walks —
    is untouched; this command is a convenience with a refusal around it, not a replacement
    for that flow.
    """

    args_model: ClassVar[type[BaseModel]] = NoArgs
    result_model: ClassVar[type[CommandResult]] = InitCommandResult
    permission_class: ClassVar[PermissionClass] = PermissionClass.WRITE
    help: ClassVar[str] = _INIT_HELP

    def __init__(self, config: object = None) -> None:
        del config

    async def run(self, args: BaseModel, ctx: Context) -> Outcome[CommandResult]:
        """Write a new project's `weft.toml`.

        Args:
            args: The parsed `NoArgs`.
            ctx: The command's context, carrying `Dependencies`.

        Returns:
            `Produced` with the `InitCommandResult` naming the written file.

        Raises:
            TargetAlreadyExistsError: `weft.toml` already exists.
        """
        del args, ctx
        if DEFAULT_CONFIG_PATH.exists():
            raise TargetAlreadyExistsError(
                f"'{DEFAULT_CONFIG_PATH}' already exists. 'weft init' creates a new "
                f"project's configuration; it does not replace one. Edit the existing file "
                f"directly, or remove it first if you mean to start over.",
                path=str(DEFAULT_CONFIG_PATH),
            )
        DEFAULT_CONFIG_PATH.write_text(_INIT_TEMPLATE, encoding="utf-8")
        return Produced(value=InitCommandResult(path=str(DEFAULT_CONFIG_PATH)))


class DeleteArgs(BaseModel):
    """`weft delete <source-id>` — one required positional, the source to remove."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_id: str
    target: str | None = Field(
        default=None,
        description=(
            "delete from this target instead of the live one (ledger task 34.6). Refused for "
            "a target that does not exist, naming every target that does. Omit for the live one."
        ),
    )


class DeleteCommandResult(CommandResult):
    """Which source was deleted, and what every participant did about it.

    The per-participant list is the result rather than a bare total, because the property
    task **5.1a** exists to make true is that a participant that failed is *named*. A single
    "deleted 41 nodes" line cannot carry that, and a total computed across a fan-out where
    one arm raised is a number that means nothing.
    """

    source_id: str
    participants: tuple[ParticipantOutcome, ...]
    #: Carried repair **R43.17** — whether any store recorded `source_id` before the fan-out,
    #: so an id nothing held reads differently from a delete that removed something.
    held: bool = True
    #: Ledger task **43.21** — every corpus-scoped layer this delete demoted from `ACTIVE` to
    #: `LayerStatus.STALE` on the sources it still covers, sorted by name. `()` when the
    #: deleted source carried no corpus-scoped layer `ACTIVE`, or nothing was deleted at all.
    layers_staled: tuple[str, ...] = ()

    @property
    def failed(self) -> tuple[ParticipantOutcome, ...]:
        """Every participant whose delete failed."""
        return tuple(outcome for outcome in self.participants if outcome.failed)


async def _resolve_deletion_id(
    deps: Dependencies, target: str | None, given: str
) -> tuple[str, bool]:
    """`(source_id, held)` for what `weft delete` was handed — carried repair **R43.17**.

    `weft sources list` prints each record's `uri`, so a uri a record carries resolves to that
    record's `id`. An unreadable store answers `(given, True)`: this read only words the answer,
    and must never stand between an operator and a delete.
    """
    read = await _read_sources_by_store(deps, target)
    if not isinstance(read, Produced):
        return given, True
    records = [record for _, records in read.value for record in records]
    if any(str(record.id) == given for record in records):
        return given, True
    by_uri = next((str(record.id) for record in records if record.uri == given), None)
    return (by_uri, True) if by_uri is not None else (given, False)


async def _corpus_layers_held_active(
    deps: Dependencies, target: str | None, source_id: str
) -> Outcome[frozenset[str]]:
    """Every corpus-scoped layer a source's record carries as `ACTIVE`.

    Every corpus-scoped layer `source_id`'s own record carries `ACTIVE`, read across every
    store `_stores_in_use` names — ledger task **43.21**. Read **before** the fan-out deletes
    that record: a corpus-scoped tree this source never joined has no hole to leave behind, so
    only a layer this source itself held is a candidate to demote everywhere else.
    """
    names = frozenset(
        corpus_scoped_layer_names(
            registry=deps.registry, reports=deps.reports, contributions=deps.contributions
        )
    )
    if not names:
        return Produced(value=frozenset())
    read = await _read_sources_by_store(deps, target)
    if not isinstance(read, Produced):
        return cast("Outcome[frozenset[str]]", read)
    held: set[str] = set()
    for _, records in read.value:
        record = next((candidate for candidate in records if str(candidate.id) == source_id), None)
        if record is None:
            continue
        held.update(
            layer.name
            for layer in record.layers
            if layer.name in names and layer.status is LayerStatus.ACTIVE
        )
    return Produced(value=frozenset(held))


async def _demote_layer_records(
    list_sources: Callable[[], Awaitable[Sequence[SourceRecord]]],
    put_source: Callable[[SourceRecord], Awaitable[None]],
    names: frozenset[str],
    excluded: frozenset[SourceId],
) -> Outcome[tuple[str, ...]]:
    """`weft_cli.layers.demote_layer_records` as the `Outcome` the store seam's `wrap` takes."""
    return Produced(value=await demote_layer_records(list_sources, put_source, names, excluded))


async def _demote_stale_corpus_layers(
    deps: Dependencies, target: str | None, names: frozenset[str], excluded: SourceId
) -> tuple[str, ...]:
    """Demote corpus layers `names` to `STALE` on every source but `excluded`.

    Demote `names` from `ACTIVE` to `LayerStatus.STALE` on every source but `excluded`, on
    every store `_stores_in_use` names — ledger task **43.21**, called *before* the fan-out
    (**R43.33**) so a tree is marked before it is holed and a failed mark deletes nothing;
    `excluded` is the source about to be deleted. Existing record
    APIs only (`list_sources`/`put_source`), the same ones `_read_sources_by_store` reads with,
    never a new store method. Returns every name actually demoted somewhere, sorted — a name
    that reaches no `ACTIVE` record on any remaining source is not reported as staled.
    """
    if not names:
        return ()
    demoted: set[str] = set()
    failures: list[str] = []
    for name in sorted(_stores_in_use(deps)):
        entry = deps.registry.entry(NodeStore, name)
        store = await bind_store(entry.factory(None), target, store_name=name)
        raw_list_sources = getattr(store, "list_sources", None)
        raw_put_source = getattr(store, "put_source", None)
        if (
            raw_list_sources is None
            or raw_put_source is None
            or not callable(raw_list_sources)
            or not callable(raw_put_source)
        ):
            await aclose(
                store, distribution=entry.distribution, contract=NodeStore.__qualname__, plugin=name
            )
            continue
        _demote = partial(
            _demote_layer_records,
            cast("Callable[[], Awaitable[Sequence[SourceRecord]]]", raw_list_sources),
            cast("Callable[[SourceRecord], Awaitable[None]]", raw_put_source),
            names,
            frozenset({excluded}),
        )
        wrapped = wrap(
            _demote,
            distribution=entry.distribution,
            contract=NodeStore.__qualname__,
            plugin=name,
            stage="layers:demote",
        )
        try:
            outcome = await wrapped()
        except WeftError as exc:
            failures.append(f"'{name}': {exc}")
            continue
        finally:
            await aclose(
                store, distribution=entry.distribution, contract=NodeStore.__qualname__, plugin=name
            )
        if isinstance(outcome, Produced):
            demoted.update(outcome.value)
        elif isinstance(outcome, Failed):
            failures.append(f"'{name}': {outcome.reason}")
    if failures:
        listed = ", ".join(sorted(names))
        raise LayerDemotionFailedError(
            f"'{excluded}' was not deleted: marking corpus layer(s) {listed} stale failed on "
            f"{'; '.join(failures)}. Nothing was removed; weft delete {excluded} again "
            "retries it."
        )
    return tuple(sorted(demoted))


class DeleteCommand:
    """`weft delete <source-id>` — G7's fast path, task **5.1a**.

    `docs/02-extension-model.md` §1 → *Extended by G7*: "`SourceDeletable` is the fast path.
    Deletion fans out synchronously, in-command, across *every* registered plugin that
    satisfies it — not just the node store." The fan-out itself is `weft_cli.deletion`; this
    class is the thin command around it, exactly as `IndexCommand` is around `run_index`.

    **`destroy`-class, and that is what makes the prompt appear.** `weft_cli.confirm.gate`
    already refuses a `destroy` command with no TTY, naming `--yes` — so nothing here writes
    a confirmation, and `docs/03-cli.md` → *Permissions*'s "the prompt states what will be
    destroyed and how much of it" is answered by `describe_impact` below, the contract method
    that section recorded as unbuilt and left to "whichever later task first ships a real
    `overwrite`/`destroy` command and needs one". This is that command.

    **A source nothing holds is a success, not a refusal.** Every participant answers
    `node_count=0`, the result says nothing held it (R43.17), and the exit code is `0`:
    deletion is idempotent, so re-running a delete that already finished has to be the
    ordinary case rather than an error, and a fan-out resumed after a partial failure depends
    on it.
    """

    args_model: ClassVar[type[BaseModel]] = DeleteArgs
    result_model: ClassVar[type[CommandResult]] = DeleteCommandResult
    permission_class: ClassVar[PermissionClass] = PermissionClass.DESTROY
    help: ClassVar[str] = _DELETE_HELP

    def __init__(self, config: object = None) -> None:
        del config

    def describe_impact(self, args: BaseModel, ctx: Context) -> str:
        """What the confirmation prompt says before anything is deleted.

        `docs/03-cli.md` → *Permissions*: "The prompt states **what will be destroyed and how
        much of it**". *How much* is honestly unavailable without asking every backend — which
        would connect to all of them before consent — so what this states instead is the
        source and every participant that will be asked, by name and distribution. That is the
        fact an operator most needs and could not otherwise get: a pack they forgot they
        installed is about to delete data.

        **It resolves the store first, and that ordering was found by running the binary
        rather than by a test.** `weft delete doc-1` in a project with no `dsn` configured
        printed a `destroy`-class TTY refusal whose impact sentence read *"nothing installed
        holds data for a source to delete"* — plausible, and false: `weft-store` was installed
        and had refused to *register* because its settings did not validate, which `--yes`
        then reported perfectly from `run()` one layer down. Two refusals for one situation,
        the wrong one first. So the same check `run()` makes is made here, ahead of any
        sentence about participants, and `weft_cli.confirm.impact_of` deliberately does not
        catch it: a command that cannot say what it will destroy has not earned a
        confirmation, and the operator gets the diagnosis they can act on instead of a prompt
        about a deletion that could never have happened.
        """
        typed = cast(DeleteArgs, args)
        targets = self._targets(ctx.require(Dependencies))
        if not targets:
            return f"'{typed.source_id}' — no registered plugin holds data derived from it."
        listed = ", ".join(target.label for target in targets)
        return f"'{typed.source_id}' will be removed from {len(targets)} participant(s): {listed}."

    async def run(self, args: BaseModel, ctx: Context) -> Outcome[CommandResult]:
        """Delete one source from every participant, demoting corpus layers it leaves holed.

        Args:
            args: The parsed `DeleteArgs`.
            ctx: The command's context, carrying `Dependencies`.

        Returns:
            `Produced` with the `DeleteCommandResult`, or the first read that did not
            produce.
        """
        typed = cast(DeleteArgs, args)
        deps = ctx.require(Dependencies)
        targets = self._targets(deps)
        await _require_target_exists(deps, typed.target)
        source_id, held = await _resolve_deletion_id(deps, typed.target, typed.source_id)
        # Ledger **43.21** — read while the deleted source's own record still exists: a
        # corpus-scoped layer it never held `ACTIVE` leaves no remaining source's tree with a
        # hole, so it is never a candidate for demotion.
        staled_names = await _corpus_layers_held_active(deps, typed.target, source_id)
        if not isinstance(staled_names, Produced):
            return cast("Outcome[CommandResult]", staled_names)
        async with claim_all_writers(targets, store_target=typed.target, command="weft delete"):
            layers_staled = await _demote_stale_corpus_layers(
                deps, typed.target, staled_names.value, SourceId(source_id)
            )
            outcomes = await delete_everywhere(
                SourceId(source_id), targets=targets, target=typed.target
            )
        return Produced(
            value=DeleteCommandResult(
                source_id=source_id, participants=outcomes, held=held, layers_staled=layers_staled
            )
        )

    def _targets(self, deps: Dependencies) -> tuple[Participant, ...]:
        """Who the fan-out will ask — refusing first if `[services] store` names nothing.

        One helper for both `describe_impact` and `run`, rather than the same lines twice: the
        prompt and the run must not be able to disagree about who participates, and the
        refusal an unresolvable store earns is the same refusal on both paths.
        """
        _raise_for_plugin_refusal(
            require_plugin(
                deps.reports,
                registry=deps.registry,
                contract=NodeStore,
                name=deps.services.store,
                setting="[services] store",
            )
        )
        return deletion_participants(registry=deps.registry, store_names=_stores_in_use(deps))


class ReconcileArgs(BaseModel):
    """`weft reconcile [--mode repair|full] [--dry-run]`.

    **`mode`, narrowed at task 5.1c.** `None` means "no flag given" — `ReconcileCommand` then
    falls back to `weft.toml`'s own `[reconcile] mode` (`weft_engine.reconcile_policy`, default
    `full`), so someone typing bare `weft reconcile` still reaches `full` unless they, or their
    project, said otherwise. The flag always wins over that default when given, per
    `docs/03-cli.md`'s own words. The automatic pass at the end of an index run does not come
    through here at all — it is `weft_cli.commands.IndexArgs.reconcile`'s own field, hardcoded
    to `repair`, never influenced by `[reconcile]`.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    mode: ReconcileMode | None = Field(
        default=None,
        description=(
            "repair drops derived state whose source is gone; full also backfills state "
            "that was never built, and prints what that will cost before it spends it. "
            "Omit to use weft.toml's [reconcile] mode, or 'full' if that says nothing."
        ),
    )
    dry_run: bool = False
    target: str | None = Field(
        default=None,
        description=(
            "reconcile this target instead of the live one (ledger task 34.6). Refused for a "
            "target that does not exist, naming every target that does. Omit for the live one."
        ),
    )


class ReconcileCommandResult(CommandResult):
    """Which mode ran, and what every participant did about it.

    **`estimates`, task 5.1c.** Populated only when `mode` resolved to `full` — `repair` never
    backfills, so it has no cost to state before spending (`docs/03-cli.md` → *Command
    surface*: "full states its cost before it spends it"). Computed, and therefore already
    known, before `participants`/`reconcile_everywhere` ever ran: this is what "before it
    spends it" means for a command with no streaming output of its own — the number is asked
    for and carried first, in the data, rather than a raw `print()` inside `run()`, which
    `docs/03-cli.md`'s own governing rule ("a Command returns a typed result, never writes to
    a stream") forbids.
    """

    mode: ReconcileMode
    dry_run: bool
    participants: tuple[ReconcileOutcome, ...]
    #: Populated on `--dry-run`, where nothing was asked and the labels are the whole answer.
    would_ask: tuple[str, ...] = ()
    estimates: tuple[ReconcileEstimateOutcome, ...] = ()

    @property
    def failed(self) -> tuple[ReconcileOutcome, ...]:
        """Every participant whose reconcile failed."""
        return tuple(outcome for outcome in self.participants if outcome.failed)

    @property
    def unconverged(self) -> tuple[ReconcileOutcome, ...]:
        """Participants that ran and did not finish — an interrupted pass, owed another."""
        return tuple(
            outcome for outcome in self.participants if not outcome.failed and not outcome.converged
        )


class ReconcileCommand:
    """`weft reconcile` — G7's safety net, task **5.1b**, and the cost `full` states, 5.1c's.

    `docs/03-cli.md` → *Command surface*: "`weft reconcile` converges what deletion missed."
    The fan-out is `weft_cli.reconcile`; this class is the thin command around it, on
    `DeleteCommand`'s own footing, and it shares that command's `describe_impact` discipline —
    resolve `[services] store` before saying anything about participants, so an operator whose
    store failed to register reads that fact rather than a sentence about an empty fan-out
    (`docs/internal/lessons.md` L5.9).

    **`destroy`-class, which is the stricter of the two `03` names, and unchanged by 5.1c.**
    That section says "class `network` for `full`, `destroy` for `repair` — one command
    declaring the higher of the two it may reach", and `permission_class` holds one value:
    `destroy` is the one the table actually gates, so declaring `network` would be a command
    that removes state and asks nobody. Every invocation — `full` included — still goes
    through `weft_cli.confirm.gate`'s own `--yes`/no-TTY machinery exactly as before; what 5.1c
    adds is the cost block `full` prints in its own *result*, informational rather than a
    second confirmation on top of the flag — `03`'s own argument against "a confirmation on
    top of an explicit flag" is about not inventing a second gate, not about the existing one.

    **`_effective_mode`, task 5.1c.** `ReconcileArgs.mode` is `None` exactly when no `--mode`
    was given; the fallback to `deps.reconcile_policy.mode` happens here, once, so
    `describe_impact` and `run` cannot resolve it two different ways.
    """

    args_model: ClassVar[type[BaseModel]] = ReconcileArgs
    result_model: ClassVar[type[CommandResult]] = ReconcileCommandResult
    permission_class: ClassVar[PermissionClass] = PermissionClass.DESTROY
    help: ClassVar[str] = _RECONCILE_HELP

    def __init__(self, config: object = None) -> None:
        del config

    def describe_impact(self, args: BaseModel, ctx: Context) -> str:
        """What the confirmation prompt says before anything is reconciled.

        Args:
            args: The parsed `ReconcileArgs`.
            ctx: The command's context, carrying `Dependencies`.

        Returns:
            The mode and every participant that will be asked, by label.
        """
        typed = cast(ReconcileArgs, args)
        deps = ctx.require(Dependencies)
        mode = self._effective_mode(typed, deps)
        targets = self._targets(deps)
        if not targets:
            return "nothing installed can reconcile; there is nothing to converge."
        listed = ", ".join(target.label for target in targets)
        return f"mode '{mode.value}' will run against {len(targets)} participant(s): {listed}."

    async def run(self, args: BaseModel, ctx: Context) -> Outcome[CommandResult]:
        """Reconcile every participant, or list who would be asked under `--dry-run`.

        Args:
            args: The parsed `ReconcileArgs`.
            ctx: The command's context, carrying `Dependencies`.

        Returns:
            `Produced` with the `ReconcileCommandResult`.
        """
        typed = cast(ReconcileArgs, args)
        deps = ctx.require(Dependencies)
        mode = self._effective_mode(typed, deps)
        targets = self._targets(deps)
        await _require_target_exists(deps, typed.target)
        _register_corpus(ctx, deps)
        if typed.dry_run:
            estimates = (
                await estimate_everywhere(mode, targets=targets, ctx=ctx, target=typed.target)
                if mode is ReconcileMode.FULL
                else ()
            )
            return Produced(
                value=ReconcileCommandResult(
                    mode=mode,
                    dry_run=True,
                    participants=(),
                    would_ask=tuple(target.label for target in targets),
                    estimates=estimates,
                )
            )
        async with claim_all_writers(targets, store_target=typed.target, command="weft reconcile"):
            estimates = (
                await estimate_everywhere(mode, targets=targets, ctx=ctx, target=typed.target)
                if mode is ReconcileMode.FULL
                else ()
            )
            outcomes = await reconcile_everywhere(
                mode, targets=targets, ctx=ctx, target=typed.target
            )
        return Produced(
            value=ReconcileCommandResult(
                mode=mode, dry_run=False, participants=outcomes, estimates=estimates
            )
        )

    def _effective_mode(self, typed: ReconcileArgs, deps: Dependencies) -> ReconcileMode:
        """`--mode`, or `weft.toml`'s own `[reconcile] mode` when the flag was not given."""
        return typed.mode if typed.mode is not None else deps.reconcile_policy.mode

    def _targets(self, deps: Dependencies) -> tuple[Participant, ...]:
        """Who the pass will ask — refusing first if `[services] store` names nothing.

        One helper for both `describe_impact` and `run`, so the prompt and the run cannot disagree.
        """
        _raise_for_plugin_refusal(
            require_plugin(
                deps.reports,
                registry=deps.registry,
                contract=NodeStore,
                name=deps.services.store,
                setting="[services] store",
            )
        )
        return reconcile_participants(registry=deps.registry, store_names=_stores_in_use(deps))


class Settings(BaseModel):
    """`weft-cli` takes no pack settings of its own — an empty model is still the required shape."""

    model_config = ConfigDict(frozen=True, extra="forbid")


def register(registrar: PackRegistrar, settings: Settings) -> None:
    """Register every built-in command through the public command seam.

    Register every built-in command — the whole of what `weft_cli.cli.COMMANDS` used
    to declare by hand, now through the identical seam `weft-kg` or any other pack would
    use. Task **3.7** adds `init` here directly, and delegates `pipeline ...`/`config ...`
    to their own modules' `register_pipeline_commands`/`register_config_commands` — one
    entry point still (`weft-cli`'s own `[project.entry-points."weft.packs"]` line is
    unchanged), composed from more than one function rather than one function growing
    without bound. Task **3.11** removes `route`: `AskCommand` now does what it did, so a
    second registered name for the same behaviour would be exactly the "two commands, know
    which one" surface this task closes. Task **4.6** adds `register_eval_commands` beside them
    — `eval run`/`eval compare`/`trace`, `weft_cli.eval_commands`'s own three — on the identical
    "compose from more than one function" footing, not a fourth entry point. Repair **R22.4c**
    adds `register_eval_baseline_command` right after it, for `eval baseline` —
    `weft_cli.eval_baseline`'s own single command — the identical footing one module over. Task
    **38.0** adds `register_eval_experiment_command` right after that, for `eval experiment` —
    `weft_cli.eval_experiment`'s own single command, which runs every arm of an experiment
    document through `weft_cli.eval_commands.index_and_score`, the identical path `eval run`
    itself now calls. **38.1** adds `register_eval_table_command` right after that, for
    `eval table` — `weft_cli.eval_table`'s own single command, which reads what `eval
    experiment` wrote and prints `weft_eval.evidence`'s table, on the identical `READ` footing
    `eval compare`/`trace` already hold.

    **Task 6.20 (G13) adds `weft_cli.render.register_renderers(registrar)`** — the same
    "compose from more than one function" footing again, this time on the renderer axis
    rather than the command one: every built-in `CommandResult` gets a renderer through
    `registrar.add_renderer`, the identical seam a stranger's pack uses, so a built-in keeps
    no privileged path. Imported locally, inside this function body, rather than at module
    scope: `weft_cli.render` imports this module (`weft_cli.commands`) at its own module
    scope to reach every built-in `CommandResult`, so a module-level import back here would
    be a cycle — the identical local-import convention `weft_cli.exit_codes.exit_code_for`'s
    own docstring documents, applied to the same problem one seam over.
    """
    del settings
    from weft_cli.render import register_renderers

    registrar.add(Command, "index", IndexCommand)
    registrar.add(Command, "ask", AskCommand)
    registrar.add(Command, "plugins list", PluginsListCommand)
    registrar.add(Command, "plugins doctor", PluginsDoctorCommand)
    registrar.add(Command, "sources list", SourcesListCommand)
    registrar.add(Command, "target list", TargetListCommand)
    register_target_commands(registrar)
    registrar.add(Command, "init", InitCommand)
    registrar.add(Command, "pack new", PackNewCommand)
    registrar.add(Command, "delete", DeleteCommand)
    registrar.add(Command, "reconcile", ReconcileCommand)
    registrar.add(Command, "render", RenderCommand)
    register_pipeline_commands(registrar)
    register_config_commands(registrar)
    register_eval_commands(registrar)
    register_eval_baseline_command(registrar)
    register_eval_experiment_command(registrar)
    register_eval_table_command(registrar)
    register_renderers(registrar)


__all__ = [
    "AskArgs",
    "RenderArgs",
    "RenderCommand",
    "RenderCommandResult",
    "AskCommand",
    "AskCommandResult",
    "CommandRefusalError",
    "ConflictingAskModeError",
    "ConflictingIndexModeError",
    "DeleteArgs",
    "DeleteCommand",
    "DeleteCommandResult",
    "ReconcileArgs",
    "ReconcileCommand",
    "ReconcileCommandResult",
    "IndexArgs",
    "IndexCommand",
    "IndexCommandResult",
    "InitCommand",
    "InitCommandResult",
    "ListedSource",
    "ListedTarget",
    "NoArgs",
    "PluginsDoctorCommand",
    "PluginsDoctorCommandResult",
    "PluginsListCommand",
    "PluginsListCommandResult",
    "SourcesListArgs",
    "SourcesListCommand",
    "SourcesListCommandResult",
    "Settings",
    "TargetAlreadyExistsError",
    "TargetDropCommandResult",
    "TargetListCommand",
    "TargetListCommandResult",
    "TargetPromoteCommandResult",
    "TargetRollbackCommandResult",
    "UnresolvedPluginNameError",
    "register",
]
