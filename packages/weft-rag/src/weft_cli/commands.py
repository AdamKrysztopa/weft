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
command is free to ignore it (and most will, since depending on `weft_cli.registry_bootstrap.
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
`RouteCommand`'s own body — the question a user asks now reaches the pipeline the router names
with no second command to know about, `docs/03-cli.md`'s own already-published *Command surface*
table read literally ("query, streaming the answer with citations" — no `route` entry ever
existed in that table). `--pipeline` is what a caller naming a specific pipeline uses instead of
the router's own choice; `--retrieve-only` is Phase 0's own contract, kept reachable rather than
deleted, because `manual/quickstart.md`'s own zero-configuration walkthrough and `eval/
run_baseline.py`'s V3 baseline (`docs/09-release.md` §4.3) both depend on a deterministic,
credential-free, network-free measurement that routing cannot honestly offer once generation is
a real model call resolved from `[llm.roles]` — see `docs/build-ledger.md`'s 3.11 entry for the
full argument, including the reference's own absent precedent.

**Task 4.0 gives `IndexCommand` the identical `--pipeline` surface `AskArgs` already has.**
`weft_cli.ingest.run_index`'s own module docstring carries the argument (Q3, settled:
`[services]` and a document's `with:` stay two surfaces); this module's own share of it is
`ConflictingIndexModeError` — `--extract`/`--pipeline` refuse together on
`ConflictingAskModeError`'s exact footing — and skipping `INDEX_PACKS`/`[services]`'s
own `require_plugin` gate when a document names the run, since neither promise is one a
named document has made.
"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar, cast

from pydantic import BaseModel, ConfigDict, Field

from weft_cli.ask import AskHit, hits_for, run_ask
from weft_cli.config_commands import register_config_commands
from weft_cli.deletion import ParticipantOutcome, delete_everywhere
from weft_cli.deletion import participants as deletion_participants
from weft_cli.eval_commands import DEFAULT_RUNS_DIR, register_eval_commands
from weft_cli.exit_codes import ExitCode
from weft_cli.fanout import Participant
from weft_cli.ingest import INDEX_PACKS, run_index
from weft_cli.installed_versions import installed_versions
from weft_cli.output import AskFormat
from weft_cli.participation import load_run_records, stores_in_use
from weft_cli.pipeline_catalogue import declared_slot_ids, full_catalogue
from weft_cli.pipeline_commands import register_pipeline_commands
from weft_cli.reconcile import (
    ReconcileEstimateOutcome,
    ReconcileOutcome,
    estimate_everywhere,
    reconcile_everywhere,
)
from weft_cli.reconcile import participants as reconcile_participants
from weft_cli.registry_bootstrap import (
    DEFAULT_CONFIG_PATH,
    Dependencies,
    PluginRefusal,
    require_active,
    require_plugin,
)
from weft_cli.route_ask import run_named_ask, run_routed_ask
from weft_cli.skew import SkewReport, detect_skew
from weft_cli.tracing_status import describe_tracing
from weft_command.contract import Command, CommandResult
from weft_command.permission import PermissionClass
from weft_embed import Embedder
from weft_extract import Extractor
from weft_generate.payload import Answer
from weft_kernel.context import Context
from weft_kernel.discovery import PackRegistrar, PackReport
from weft_kernel.errors import UnresolvedNameError, WeftError
from weft_kernel.payload import Outcome, Produced, SourceId
from weft_kernel.registry import DisplacedRegistration
from weft_kernel.resolution import Contribution
from weft_kernel.runner import RunSummary
from weft_store import NodeStore, ReconcileMode

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
    "--retrieve-only runs no pipeline at all and prints the nearest passages instead, with "
    "no generation and no model call (Phase 0's own contract, kept for scripts)."
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


class TargetAlreadyExistsError(WeftError):
    """`weft init` refused to overwrite a `weft.toml` that already exists.

    **Repair, 2026-08-20** (`docs/build-ledger.md`'s dated paragraph for tasks 3.3/3.6/3.7 has
    the argument in full, against `docs/03-cli.md` → *Permissions*'s own table): `weft init`
    is `write`-class now, not `overwrite` — table row `write`'s own worked example is "index
    into a new collection, write a derived pipeline", which is exactly what a first-run `weft
    init` scaffolding a project's own `weft.toml` is. `write` is `allow` by default, so it
    never reaches `weft_cli.confirm.gate` at all, which is the fix for the reported bug: a
    first `weft init` in CI, where nothing is a TTY, no longer refuses.

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


class CommandRefusalError(WeftError):
    """A command refused to run before calling into the library — a policy or resolution
    decision made from `PackReport`s and the registry alone, never from anything the run
    itself would have failed on.

    Carries the exact `ExitCode` the retired hand-written handlers used to `return` directly,
    because `Command.run` cannot return an `ExitCode` — only an `Outcome[CommandResult]` — and
    the contract must not learn `weft_cli.exit_codes.ExitCode` any more than it already knows
    `weft_cli` at all. `weft_cli.render.render_outcome` reads `.exit_code` off this exception
    the same way it reads `weft_cli.exit_codes.exit_code_for` for every other `WeftError`.
    """

    def __init__(self, message: str, *, exit_code: ExitCode) -> None:
        super().__init__(message)
        self.exit_code = exit_code


class UnresolvedPluginNameError(CommandRefusalError, UnresolvedNameError):
    """`CommandRefusalError`'s own family member for a genuine name-resolution failure —
    finding 2 of the 2026-08-20 Phase 3 review, repairing tasks 3.2/3.3/3.7 (`docs/build-ledger.
    md`'s dated paragraph carries the argument in full).

    Before this repair, `IndexCommand`/`AskCommand` caught `weft_cli.registry_bootstrap.
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
    """`weft index` was given both `--extract` and `--pipeline` — two different, mutually
    exclusive claims about what should run: narrow the default four-stage path's own
    auto-discovery to one named extractor, or run a whole document whose own `extract`
    stage already names its plugin (task **4.0**). Neither wins silently over the other,
    the identical reasoning `ConflictingAskModeError` below already gives `weft ask`'s own
    `--retrieve-only`/`--pipeline` pair — refused, loudly, before either resolves a plugin.

    Not a name-resolution failure — there is no alternative *name* to offer, only a choice
    between two flags that are individually valid — so this does not join `NAME_RESOLUTION_
    FAMILY`, on `ConflictingAskModeError`'s own footing.
    """


class ConflictingAskModeError(WeftError):
    """`weft ask` was given both `--retrieve-only` and `--pipeline` — two different,
    mutually exclusive claims about what this run should do: retrieve the nearest passages
    with no pipeline running at all, or run one named pipeline through to a generated
    answer. Neither wins silently over the other — CLAUDE.md: "a silent fallback is worse
    than a failure" — so this is refused, loudly, before either resolves a single plugin.

    Not a name-resolution failure — there is no alternative *name* to offer, only a choice
    between two flags that are individually valid — so this does not join `NAME_RESOLUTION_
    FAMILY`; `weft_cli.exit_codes.exit_code_for`'s own default, `OPERATION_FAILED` (`1`), is
    the code, on the identical footing task 3.7's own `TargetAlreadyExistsError`/
    `PipelineAlreadyExistsError` argue for a certain answer that is not a policy question.
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
    """Every `NodeStore` name `weft delete`/`weft reconcile` must reach — task **6.18**, G13's
    first repair (`docs/02-extension-model.md` §1 → *Extended by G13*): the configured
    `[services] store`, plus every `NodeStore` named by a pipeline in the project's catalogue or
    by a persisted run record. One helper for all three call sites — `DeleteCommand._targets`,
    `ReconcileCommand._targets` and `IndexCommand._auto_reconcile` — so the prompt, the run and
    the automatic post-index pass cannot disagree about who participates.
    """
    return stores_in_use(
        configured=deps.services.store,
        registry=deps.registry,
        catalogue=full_catalogue(reports=deps.reports),
        records=load_run_records(DEFAULT_RUNS_DIR),
    )


def _register_corpus(ctx: Context, deps: Dependencies) -> None:
    """Put the configured `NodeStore` on the `Context` a reconcile pass carries — task
    **6.19**, G13's second repair (`docs/02-extension-model.md` §1 → *Extended by G13*): "the
    CLI registers the configured store into the `Context` a reconcile pass carries, and a
    participant reaches it with `ctx.require(NodeStore)`." No contract change: `Context.require`
    is G1's own one resolution seam, and `NodeStore` already answers "what should exist" with
    `list_sources`/`scan`/`count`.

    A `[services] store` that resolves to nothing registered adds nothing here — no raise, no
    placeholder. `weft_cli.registry_bootstrap.require_plugin` is what turns an unresolvable
    `[services] store` into a diagnosable refusal; a participant that then reaches for a corpus
    with none registered gets `UnresolvedServiceError`, naming what it wanted and what is
    available, which is the loud failure, correctly located — a second translation here would
    give one mistake two messages (`docs/lessons.md` L5.9).

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
    """`weft index <path> [--extract NAME | --pipeline NAME] [--reconcile repair|full]` — see
    `weft_cli.argparse_gen` for how a field with no default becomes a positional and one with
    a default becomes a flag.

    `extract` and `pipeline` are mutually exclusive — `IndexCommand.run` refuses both
    together, loudly, before either resolves a plugin, the identical shape `AskArgs`'
    `pipeline`/`retrieve_only` pair already has.

    **`reconcile`, task 5.1c.** `docs/02-extension-model.md` §3 → *Slots*, "Tested by G7":
    "a `Reconcilable` pack creating derived data during an automatic pass *would* breach
    it, so the automatic pass never does; backfill is reached only by a person's per-run
    flag." That is why this field's default is the hardcoded `ReconcileMode.REPAIR` — never
    read from `weft.toml`'s own `[reconcile]` block (see `weft_cli.reconcile_policy`'s own
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


class AskArgs(BaseModel):
    """`weft ask <question> [--pipeline NAME] [--retrieve-only] [--top-k N] [--format text|json]`.

    Task **3.11**: `ask` routes by default — see `AskCommand`'s own docstring for the surface
    decision and `docs/build-ledger.md`'s 3.11 entry for the argument in full. `pipeline` and
    `retrieve_only` are mutually exclusive (`AskCommand.run` refuses both together, loudly,
    before either resolves a plugin); `top_k`/`format` only take effect with `--retrieve-only`
    — a routed or named-pipeline answer has no `top_k` of its own to report (each pipeline
    decides that internally) and is always rendered the same way `_render_ask` already renders
    a routed answer.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    question: str = Field(description="the question to ask")
    pipeline: str | None = Field(
        default=None,
        description=(
            "name a pipeline directly, bypassing the router (a project-local document or an "
            "installed pack's own contribution — the same set `weft pipeline show` resolves "
            "against). Mutually exclusive with --retrieve-only."
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


class IndexCommandResult(CommandResult):
    """What `weft index` produced — the same two facts `weft_cli.ingest.IndexResult` always
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


class AskCommandResult(CommandResult):
    """What `weft ask` produced — a routed, generated `Answer` by default, or, with
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


class PluginsListCommandResult(CommandResult):
    """`weft plugins list`'s whole answer — one `PackReport` per discovered distribution."""

    reports: tuple[PackReport, ...]


class PluginsDoctorCommandResult(CommandResult):
    """`weft plugins doctor`'s fuller answer — reports, displacements, unconsulted pins, and
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
        index_args = cast(IndexArgs, args)  # `args_model` is the isinstance contract
        deps = ctx.require(Dependencies)

        if index_args.pipeline is not None and index_args.extract is not None:
            raise ConflictingIndexModeError(
                "--extract and --pipeline cannot both be given: --extract narrows the "
                "default four-stage path's own auto-discovery to one named extractor; "
                "--pipeline names a whole document whose own 'extract' stage already names "
                "its plugin. Choose one."
            )

        if index_args.pipeline is None:
            active_refusal = require_active(deps.reports, packs=INDEX_PACKS)
            if active_refusal is not None:
                # `require_active` never resolves `weft_kernel.registry.UnknownPluginError` —
                # it checks a fixed distribution list, not a plugin name — so it has no
                # `valid_options` to lose in the first place; see `weft_cli.registry_bootstrap.
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

        result = await run_index(
            Path(index_args.path),
            registry=deps.registry,
            ctx=ctx,
            extractor=index_args.extract,
            embedder=deps.services.embed,
            store=deps.services.store,
            pipeline=index_args.pipeline,
            reports=deps.reports,
            contributions=deps.contributions,
            # Task 8.10: an ingest stage may ask a model — `raptor` summarises a cluster,
            # `hypothetical-questions` writes questions per chunk — so the roles an operator
            # mapped in `[llm.roles]` have to reach the ingest run, exactly as they already
            # reach a query one through `run_routed_ask`. Before this, `run_index` assembled
            # no services at all and both plugins failed at run time.
            llm=deps.llm,
            sink=deps.token_sink,
        )
        reconcile_result = await self._auto_reconcile(index_args.reconcile, deps=deps, ctx=ctx)
        return Produced(
            value=IndexCommandResult(
                summary=result.summary,
                stored_count=result.stored_count,
                reconcile=reconcile_result,
            )
        )

    async def _auto_reconcile(
        self, mode: ReconcileMode, *, deps: Dependencies, ctx: Context
    ) -> ReconcileCommandResult:
        """The automatic post-index pass, task **5.1c** — `docs/02-extension-model.md` §3 →
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
        """
        targets = reconcile_participants(registry=deps.registry, store_names=_stores_in_use(deps))
        _register_corpus(ctx, deps)
        estimates = (
            await estimate_everywhere(mode, targets=targets, ctx=ctx)
            if mode is ReconcileMode.FULL
            else ()
        )
        outcomes = await reconcile_everywhere(mode, targets=targets, ctx=ctx)
        return ReconcileCommandResult(
            mode=mode, dry_run=False, participants=outcomes, estimates=estimates
        )


class AskCommand:
    """`weft ask` — task **3.11**: routes by default, so the question a user asks reaches
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
    same thing (`docs/build-ledger.md`'s 3.11 entry has the fuller argument, including why
    the reference has no precedent to weigh either way — every reference CLI path disables its own
    router explicitly).

    **Naming a pipeline directly** (the capability the ledger's own note asked this task to
    make sure stayed reachable) is new, not a re-spelling of what `route` did: `route` never
    took a pipeline name either — it only ever ran the router. `--pipeline <name>` bypasses
    the router and runs `weft_cli.route_ask.run_named_ask` instead, against the same
    catalogue `weft pipeline show` resolves names against.

    **`--retrieve-only` keeps Phase 0's own contract reachable**, deliberately not deleted:
    `manual/quickstart.md`'s zero-configuration walkthrough and `eval/run_baseline.py`'s V3
    baseline (`docs/09-release.md` §4.3) both need a deterministic, credential-free,
    network-free measurement — a `weft.toml` with no `[llm.roles]` table maps nothing
    (`weft_llm.roles.LLMRoles`'s own "no silent default" clause), so routed generation
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
        ask_args = cast(AskArgs, args)
        deps = ctx.require(Dependencies)

        if ask_args.retrieve_only and ask_args.pipeline is not None:
            raise ConflictingAskModeError(
                "--retrieve-only and --pipeline cannot both be given: --retrieve-only runs "
                "no pipeline at all (embed + vector search only); --pipeline names one to "
                "run through to a generated answer. Choose one."
            )

        if ask_args.retrieve_only:
            return await self._run_retrieve_only(ask_args, deps=deps, ctx=ctx)
        return await self._run_generating(ask_args, deps=deps, ctx=ctx)

    async def _run_retrieve_only(
        self, ask_args: AskArgs, *, deps: Dependencies, ctx: Context
    ) -> Outcome[CommandResult]:
        """Phase 0's own contract, unchanged: embed the question, search directly, print
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

        results = await run_ask(
            ask_args.question,
            registry=deps.registry,
            ctx=ctx,
            top_k=ask_args.top_k,
            embedder=deps.services.embed,
            store=deps.services.store,
        )
        return Produced(
            value=AskCommandResult(
                question=ask_args.question,
                top_k=ask_args.top_k,
                format=ask_args.format,
                hits=hits_for(results),
            )
        )

    async def _run_generating(
        self, ask_args: AskArgs, *, deps: Dependencies, ctx: Context
    ) -> Outcome[CommandResult]:
        """The default: route through the installed router, or run `--pipeline`'s own
        named pipeline directly — either way, a generated, cited `Answer`.
        """
        if ask_args.pipeline is not None:
            pipeline_name = ask_args.pipeline
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
            )
        return Produced(
            value=AskCommandResult(
                question=ask_args.question,
                top_k=ask_args.top_k,
                format=ask_args.format,
                pipeline_name=pipeline_name,
                answer=answer,
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
            )
        )


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


class DeleteCommandResult(CommandResult):
    """Which source was deleted, and what every participant did about it.

    The per-participant list is the result rather than a bare total, because the property
    task **5.1a** exists to make true is that a participant that failed is *named*. A single
    "deleted 41 nodes" line cannot carry that, and a total computed across a fan-out where
    one arm raised is a number that means nothing.
    """

    source_id: str
    participants: tuple[ParticipantOutcome, ...]

    @property
    def failed(self) -> tuple[ParticipantOutcome, ...]:
        return tuple(outcome for outcome in self.participants if outcome.failed)


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
    `node_count=0`, the result says so, and the exit code is `0`: deletion is idempotent, so
    re-running a delete that already finished has to be the ordinary case rather than an
    error, and a fan-out resumed after a partial failure depends on it.
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
        typed = cast(DeleteArgs, args)
        targets = self._targets(ctx.require(Dependencies))
        outcomes = await delete_everywhere(SourceId(typed.source_id), targets=targets)
        return Produced(value=DeleteCommandResult(source_id=typed.source_id, participants=outcomes))

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
    falls back to `weft.toml`'s own `[reconcile] mode` (`weft_cli.reconcile_policy`, default
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
    (`docs/lessons.md` L5.9).

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
        typed = cast(ReconcileArgs, args)
        deps = ctx.require(Dependencies)
        mode = self._effective_mode(typed, deps)
        targets = self._targets(deps)
        if not targets:
            return "nothing installed can reconcile; there is nothing to converge."
        listed = ", ".join(target.label for target in targets)
        return f"mode '{mode.value}' will run against {len(targets)} participant(s): {listed}."

    async def run(self, args: BaseModel, ctx: Context) -> Outcome[CommandResult]:
        typed = cast(ReconcileArgs, args)
        deps = ctx.require(Dependencies)
        mode = self._effective_mode(typed, deps)
        targets = self._targets(deps)
        _register_corpus(ctx, deps)
        estimates = (
            await estimate_everywhere(mode, targets=targets, ctx=ctx)
            if mode is ReconcileMode.FULL
            else ()
        )
        if typed.dry_run:
            return Produced(
                value=ReconcileCommandResult(
                    mode=mode,
                    dry_run=True,
                    participants=(),
                    would_ask=tuple(target.label for target in targets),
                    estimates=estimates,
                )
            )
        outcomes = await reconcile_everywhere(mode, targets=targets, ctx=ctx)
        return Produced(
            value=ReconcileCommandResult(
                mode=mode, dry_run=False, participants=outcomes, estimates=estimates
            )
        )

    def _effective_mode(self, typed: ReconcileArgs, deps: Dependencies) -> ReconcileMode:
        """`--mode`, or `weft.toml`'s own `[reconcile] mode` when the flag was not given."""
        return typed.mode if typed.mode is not None else deps.reconcile_policy.mode

    def _targets(self, deps: Dependencies) -> tuple[Participant, ...]:
        """Who the pass will ask — refusing first if `[services] store` names nothing. One
        helper for both `describe_impact` and `run`, so the prompt and the run cannot disagree.
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
    """Register every built-in command — the whole of what `weft_cli.cli.COMMANDS` used
    to declare by hand, now through the identical seam `weft-graph` or any other pack would
    use. Task **3.7** adds `init` here directly, and delegates `pipeline ...`/`config ...`
    to their own modules' `register_pipeline_commands`/`register_config_commands` — one
    entry point still (`weft-cli`'s own `[project.entry-points."weft.packs"]` line is
    unchanged), composed from more than one function rather than one function growing
    without bound. Task **3.11** removes `route`: `AskCommand` now does what it did, so a
    second registered name for the same behaviour would be exactly the "two commands, know
    which one" surface this task closes. Task **4.6** adds `register_eval_commands` beside them
    — `eval run`/`eval compare`/`trace`, `weft_cli.eval_commands`'s own three — on the identical
    "compose from more than one function" footing, not a fourth entry point.

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
    registrar.add(Command, "init", InitCommand)
    registrar.add(Command, "delete", DeleteCommand)
    registrar.add(Command, "reconcile", ReconcileCommand)
    register_pipeline_commands(registrar)
    register_config_commands(registrar)
    register_eval_commands(registrar)
    register_renderers(registrar)


__all__ = [
    "AskArgs",
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
    "NoArgs",
    "PluginsDoctorCommand",
    "PluginsDoctorCommandResult",
    "PluginsListCommand",
    "PluginsListCommandResult",
    "Settings",
    "TargetAlreadyExistsError",
    "UnresolvedPluginNameError",
    "register",
]
