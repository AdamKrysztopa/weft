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
"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar, cast

from pydantic import BaseModel, ConfigDict, Field

from weft_cli.ask import AskHit, hits_for, run_ask
from weft_cli.config_commands import register_config_commands
from weft_cli.exit_codes import ExitCode
from weft_cli.ingest import INDEX_DISTRIBUTIONS, run_index
from weft_cli.output import AskFormat
from weft_cli.pipeline_commands import register_pipeline_commands
from weft_cli.registry_bootstrap import (
    DEFAULT_CONFIG_PATH,
    Dependencies,
    PluginRefusal,
    require_active,
    require_plugin,
)
from weft_cli.route_ask import run_named_ask, run_routed_ask
from weft_command.contract import Command, CommandResult
from weft_command.permission import PermissionClass
from weft_embed import Embedder
from weft_extract import Extractor
from weft_generate.payload import Answer
from weft_kernel.context import Context
from weft_kernel.discovery import PackRegistrar, PackReport
from weft_kernel.errors import UnresolvedNameError, WeftError
from weft_kernel.payload import Outcome, Produced
from weft_kernel.registry import DisplacedRegistration
from weft_kernel.runner import RunSummary
from weft_store import NodeStore

_INDEX_HELP = (
    "run the built-in ingest pipeline over a directory. Which formats are accepted is "
    "derived from the extractors actually installed, never from a fixed list."
)

_ASK_HELP = (
    "ask a question. Routes through the installed router by default — a QueryScorer and a "
    "RoutingPolicy discovered from the registry, never a fixed list here — and prints the "
    "generated, cited answer. --pipeline names one directly, skipping the router; "
    "--retrieve-only runs no pipeline at all and prints the nearest passages instead, with "
    "no generation and no model call (Phase 0's own contract, kept for scripts)."
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


class NoArgs(BaseModel):
    """The args model for a command that takes none — `plugins list` and `plugins doctor`."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class IndexArgs(BaseModel):
    """`weft index <path> [--extract NAME]` — see `weft_cli.argparse_gen` for how a field
    with no default becomes a positional and one with a default becomes a flag.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    path: str = Field(description="directory to index")
    extract: str | None = Field(
        default=None,
        description=(
            "the extractor plugin to use, when more than one claims what is in the "
            "directory. Omit it and the single claimant is used; a refusal lists the "
            "candidates."
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
    """

    summary: RunSummary
    stored_count: int | None


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
    """`weft plugins doctor`'s fuller answer — reports, displacements and unconsulted pins."""

    reports: tuple[PackReport, ...]
    displaced: tuple[DisplacedRegistration, ...]
    unconsulted_pins: tuple[str, ...]


class IndexCommand:
    """`weft index` — see the module docstring for what moved and what did not."""

    args_model: ClassVar[type[BaseModel]] = IndexArgs
    result_model: ClassVar[type[CommandResult]] = IndexCommandResult
    permission_class: ClassVar[PermissionClass] = PermissionClass.WRITE
    help: ClassVar[str] = _INDEX_HELP

    def __init__(self, config: object = None) -> None:
        del config  # this pack takes no `with:`-style configuration

    async def run(self, args: BaseModel, ctx: Context) -> Outcome[CommandResult]:
        index_args = cast(IndexArgs, args)  # `args_model` is the isinstance contract
        deps = ctx.require(Dependencies)
        active_refusal = require_active(deps.reports, distributions=INDEX_DISTRIBUTIONS)
        if active_refusal is not None:
            # `require_active` never resolves `weft_kernel.registry.UnknownPluginError` — it
            # checks a fixed distribution list, not a plugin name — so it has no `valid_options`
            # to lose in the first place; see `weft_cli.registry_bootstrap.require_active`'s own
            # docstring for why it structurally cannot be the gate `require_plugin` below is.
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
        )
        return Produced(
            value=IndexCommandResult(summary=result.summary, stored_count=result.stored_count)
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
        return Produced(
            value=PluginsDoctorCommandResult(
                reports=deps.reports,
                displaced=deps.registry.displaced(),
                unconsulted_pins=tuple(sorted(deps.registry.unconsulted_pins())),
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

# [packs.weft-store]
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
    which one" surface this task closes.
    """
    del settings
    registrar.add(Command, "index", IndexCommand)
    registrar.add(Command, "ask", AskCommand)
    registrar.add(Command, "plugins list", PluginsListCommand)
    registrar.add(Command, "plugins doctor", PluginsDoctorCommand)
    registrar.add(Command, "init", InitCommand)
    register_pipeline_commands(registrar)
    register_config_commands(registrar)


__all__ = [
    "AskArgs",
    "AskCommand",
    "AskCommandResult",
    "CommandRefusalError",
    "ConflictingAskModeError",
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
