"""`weft pipeline list|show|derive|validate|diff` — task **3.7**'s five pipeline commands.

`docs/03-cli.md` → *Command surface*. Registered exactly like every other `Command` —
`weft_cli.commands`'s own module docstring's "built-ins get no shortcut" applies here
unchanged: nothing below reaches the registry, the parser or `weft --help` through a second
path, only through `weft_cli.commands.register`'s single entry point, which this module's
own `register_pipeline_commands` is called from.

**Every command here needs the registry — `full_catalogue`/`weft_kernel.resolution.resolve`
cannot answer without one — so all five go through the ordinary discovery-requiring path
every other command does since task 3.2 unified the parser.** `docs/02-extension-model.md`
§2's own line — "`weft --version`, `weft init` and `weft config get` complete with zero
pack code executed" — predates that unification: it described a world with a hand-written
`COMMANDS` table, where a command's own `needs_registry` flag decided whether discovery ran
for it. Task 3.2 deleted that table; `weft_cli.cli.build_parser` now walks the *whole*
registry to build even one subcommand's grammar (`_add_command_level` groups every
registered `Command` name by shared prefix before it can hand back a single leaf), so
building a parser that recognises `weft init` or `weft config get` as valid subcommands at
all already requires the same `build_dependencies()` — and therefore the same `discover()`
— every other command pays. `weft --version` remains the **one** categorically pack-code-free
command (`tests/architecture/test_ff8_trust_model.py::test_version_command_executes_no_pack_code`,
unweakened, still subprocess-asserted) because it alone never reaches `build_parser` at all
— `weft_cli.cli.wants_version`'s own mini-parser answers it before discovery is even
considered. `docs/02-extension-model.md` §2 is corrected in the same commit that ships this
module, rather than left to say something the architecture stopped making true two tasks
ago. The alternative — a third, hand-coded pre-scan for `init`/`config get`, on
`wants_version`'s own precedent, bypassing the registry-driven parser entirely — was
rejected: it is exactly the "second dispatch path" this task's own brief refuses, and it
would also have to duplicate `init`/`config get`'s own argument grammar by hand, the "no
hand-written table" rule applied to itself.

**`weft pipeline show`/`validate`/`diff`/`derive` all resolve against `weft_kernel.
resolution.resolve` with `contributions=()`, its own default — never a caller-assembled
`Contribution` tuple.** Nothing in this tree builds one yet: a grep of `packages/` finds no
`PackRegistrar.add_contribution`-shaped method and no call site that ever constructs
`weft_kernel.resolution.Contribution` outside that module's own tests — slot-contribution
discovery (`02` §3 → *Slots*: "a pack may... contribute into a slot a pipeline opted into")
has no wiring from an installed pack's `register()` call to a resolved pipeline anywhere in
this repository, first-party or not. That is a real, named gap for whichever task first
ships a pack that contributes into a slot (`weft-graph`, per `02` §4's own worked example,
is the natural first caller) — not this one's to build. What this task *does* build is the
**print path**: `weft_kernel.resolution.ResolvedPipeline.unapplied_operators`/
`unplaced_contributions` are carried straight onto `PipelineShowCommandResult` and rendered
(`weft_cli.render`), honestly empty today because nothing supplies a contribution to have
one to report, exactly as `weft_kernel.resolution`'s own module docstring already states for
itself: "`unapplied_operators` stays empty even now... task 1.11 gives them something to
hold." `docs/03-cli.md` calls printing them "the only way they are visible" — this module is
what makes that true the day a pack finally does supply one, with no CLI-side change needed.

**`weft pipeline derive` writes the smallest legal derived pipeline, and nothing more.**
`02` §3 → *Derivation*: "The parent is referenced, never copied... `extends: base`... That
is the whole change." A document with `extends: <parent>` and no operators is already a
complete, valid `Pipeline` — `weft_kernel.pipeline.Pipeline._extends_and_stages_are_mutually_
exclusive_with_operators` refuses `stages:`/`slots:` alongside `extends`, never an *empty*
operator set — so this command scaffolds exactly that skeleton (`name:`, `extends:`) and
stops, the same "produce, don't half-author" boundary `weft init` draws for `weft.toml`: an
author who wants an `insert`/`replace`/`remove`/`set` block edits the file `derive` just
wrote, by hand, in a text editor, because generating one from CLI flags would mean this
module inventing an argument grammar for four different operator shapes
(`weft_kernel.pipeline.InsertOperator`/`StageDeclaration`/`SetOperator`) that
`weft_cli.argparse_gen`'s own documented floor — `str`, `int`, `StrEnum`, `bool`, and `|
None` wrapping any of those — has no honest way to express. `weft pipeline validate <name>`
is the natural next command to run once the file is hand-edited, and this command's own
render output says so.

**`derive` was briefly `overwrite`-class, and is `write`-class again — repaired 2026-08-20,
from a review of task 3.7's landed `f201e70`.** The argument this task originally shipped —
`derive` writing `pipelines/<name>.yaml` with no upsert-safety draws the same line `weft
init` draws, so both are `overwrite` — proved too wide once someone actually ran `weft init`
in a genuinely empty project: `docs/03-cli.md` → *Permissions*'s own table puts "write a
derived pipeline" under `write` (allow), not `overwrite` (ask), and a *first* `weft pipeline
derive` — the only case the "no upsert-safety" argument was ever really about, since nothing
existed yet to lose — refused outright in CI, where nothing is a TTY, on a table `03` had
already settled the other way. `PipelineAlreadyExistsError`'s own docstring carries the
corrected argument in full: `write` for the create, and an unconditional, loud, named refusal
— never a prompt, never a silent replace — for the one case the old classification actually
existed to catch, a target that already exists. `weft init` and `weft config set` get the
identical treatment; see `weft_cli.commands`'s and `weft_cli.config_commands`'s own module
docstrings. **A consequence stated rather than discovered later**: with all three reclassified
and no example pack anywhere in this tree declaring `overwrite`/`destroy` either, task 3.3's
no-TTY/`--yes` machinery is now exercised only by hand-registered test doubles
(`tests/unit/weft_cli/test_cli.py::_WipeCommand`, `tests/unit/weft_cli/test_confirm.py`'s own
direct unit tests) — acceptable, and recorded here rather than left to be noticed by accident,
the same discipline `docs/build-ledger.md`'s O1–O3 items were carried under.
"""

from __future__ import annotations

from typing import ClassVar, cast

import yaml
from pydantic import BaseModel, ConfigDict, Field

from weft_cli.compile import contracts_for
from weft_cli.pipeline_catalogue import (
    DEFAULT_PIPELINES_DIR,
    UnknownPipelineNameError,
    full_catalogue,
)
from weft_cli.pipeline_diff import PipelineDiff, diff_resolved
from weft_cli.registry_bootstrap import Dependencies
from weft_command.contract import Command, CommandResult
from weft_command.permission import PermissionClass
from weft_kernel.context import Context
from weft_kernel.discovery import PackRegistrar
from weft_kernel.errors import WeftError
from weft_kernel.payload import Outcome, Produced
from weft_kernel.pipeline import Pipeline
from weft_kernel.resolution import ResolvedPipeline, resolve

_LIST_HELP = (
    "every pipeline this project can resolve — project-local documents and every "
    "installed pack's own contribution"
)

_SHOW_HELP = (
    "the resolved form of one pipeline: every stage's provenance, every var's final "
    "value, and anything that went unplaced or unapplied"
)

_DERIVE_HELP = "scaffold a new pipeline document with 'extends:' set to an existing one"

_VALIDATE_HELP = (
    "resolve a pipeline and report whether it does, in the resolution-failure family's own words"
)

_DIFF_HELP = "the exact, structural difference between two resolved pipelines"


class NoArgs(BaseModel):
    """The args model for `pipeline list`, which takes none."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class PipelineNameArgs(BaseModel):
    """`weft pipeline show <name>` / `weft pipeline validate <name>`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(
        description=(
            "the pipeline to resolve — a project-local document's own name:, or an "
            "installed pack's contribution"
        )
    )


class PipelineDeriveArgs(BaseModel):
    """`weft pipeline derive <parent> <name>`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    parent: str = Field(description="the pipeline to extend")
    name: str = Field(description="the new pipeline's own name")


class PipelineDiffArgs(BaseModel):
    """`weft pipeline diff <a> <b>`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    a: str = Field(description="the first pipeline")
    b: str = Field(description="the second pipeline")


class PipelineListCommandResult(CommandResult):
    """`weft pipeline list`'s whole answer — every name `full_catalogue` holds, sorted."""

    names: tuple[str, ...]


class PipelineShowCommandResult(CommandResult):
    """`weft pipeline show`'s whole answer — the resolved form itself.

    `resolved` carries the `weft_kernel.resolution.ResolvedPipeline` unwrapped, not a
    re-derived summary of it: `02` §3 states exactly what a resolved pipeline makes
    explicit — "every stage, plugin, version and configuration value named" plus
    provenance, `applies_to`, `unapplied_operators` and `unplaced_contributions` — and this
    result carries all of it because the model already does, with no second, narrower shape
    for a renderer to fall out of step with the first.
    """

    resolved: ResolvedPipeline


class PipelineDeriveCommandResult(CommandResult):
    """`weft pipeline derive`'s whole answer — what was written, and where."""

    parent: str
    name: str
    path: str


class PipelineValidateCommandResult(CommandResult):
    """`weft pipeline validate`'s whole answer on success — resolution failure never reaches
    this far; see the module docstring on why a failure is left to propagate.
    """

    name: str
    stage_count: int


class PipelineDiffCommandResult(CommandResult):
    """`weft pipeline diff`'s whole answer — `weft_cli.pipeline_diff.PipelineDiff` itself."""

    diff: PipelineDiff


class PipelineAlreadyExistsError(WeftError):
    """`weft pipeline derive` refused to overwrite a pipeline document that already exists.

    **Repair, 2026-08-20** — `weft_cli.commands.TargetAlreadyExistsError`'s own docstring
    carries the shared argument against `docs/03-cli.md` → *Permissions*'s table in full;
    this is `derive`'s own instance of it, not a re-export, because `weft_cli.commands`
    already imports `register_pipeline_commands` from this module — the reverse import would
    be circular. `derive` is `write`-class now: scaffolding `pipelines/<name>.yaml` for a
    name nothing has used yet is a *create*, and a name already on disk is refused outright,
    loudly, naming the path — never silently replaced, never asked about. Not a permission
    refusal, so not `CommandRefusalError`/`ExitCode.POLICY_REFUSED`: `exit_code_for`'s own
    default, `OPERATION_FAILED` (`1`), is the deliberate choice — the answer is certain, not
    a policy question this tool declined to decide without a human.
    """

    def __init__(self, message: str, *, path: str) -> None:
        super().__init__(message)
        self.path = path


def _resolved_or_refuse(
    name: str, *, deps: Dependencies, catalogue: dict[str, Pipeline]
) -> ResolvedPipeline:
    """`name` resolved against `catalogue` — `UnknownPipelineNameError` if `name` is absent.

    Shared by `show`/`validate`/`diff`, each of which already has its own `catalogue` (one
    `full_catalogue()` call per command invocation, never per name — `diff a b` builds it
    once and resolves both names against it, so `a` and `b` are compared against the
    identical catalogue rather than two that could theoretically disagree).
    """
    pipeline = catalogue.get(name)
    if pipeline is None:
        options = tuple(sorted(catalogue))
        raise UnknownPipelineNameError(
            f"'{name}' is not a pipeline this project knows — checked the project's own "
            f"'{DEFAULT_PIPELINES_DIR}' directory and every installed pack's own "
            f"contribution. Known pipelines: {', '.join(options) or '(none)'}.",
            valid_options=options,
            pipeline=name,
            remedy=f"use one of: {', '.join(options) or '(none — no pipeline is known yet)'}.",
        )
    contracts = contracts_for(pipeline, registry=deps.registry, parents=catalogue)
    return resolve(pipeline, registry=deps.registry, contracts=contracts, parents=catalogue)


class PipelineListCommand:
    """`weft pipeline list` — see the module docstring."""

    args_model: ClassVar[type[BaseModel]] = NoArgs
    result_model: ClassVar[type[CommandResult]] = PipelineListCommandResult
    permission_class: ClassVar[PermissionClass] = PermissionClass.READ
    help: ClassVar[str] = _LIST_HELP

    def __init__(self, config: object = None) -> None:
        del config

    async def run(self, args: BaseModel, ctx: Context) -> Outcome[CommandResult]:
        del args
        deps = ctx.require(Dependencies)
        catalogue = full_catalogue(reports=deps.reports)
        return Produced(value=PipelineListCommandResult(names=tuple(sorted(catalogue))))


class PipelineShowCommand:
    """`weft pipeline show <name>` — see the module docstring."""

    args_model: ClassVar[type[BaseModel]] = PipelineNameArgs
    result_model: ClassVar[type[CommandResult]] = PipelineShowCommandResult
    permission_class: ClassVar[PermissionClass] = PermissionClass.READ
    help: ClassVar[str] = _SHOW_HELP

    def __init__(self, config: object = None) -> None:
        del config

    async def run(self, args: BaseModel, ctx: Context) -> Outcome[CommandResult]:
        show_args = cast(PipelineNameArgs, args)
        deps = ctx.require(Dependencies)
        catalogue = full_catalogue(reports=deps.reports)
        resolved = _resolved_or_refuse(show_args.name, deps=deps, catalogue=catalogue)
        return Produced(value=PipelineShowCommandResult(resolved=resolved))


class PipelineValidateCommand:
    """`weft pipeline validate <name>` — see the module docstring.

    A resolution failure is never caught here: `weft_kernel.resolution.resolve` (or
    `full_catalogue`, for a document that will not even parse) already raises the
    resolution-failure family's own named subclass with its own message —
    `docs/02-extension-model.md` §3 → *When resolution fails*: "each failure is its own
    `WeftError` subclass... [with] the pipeline, the stage ids, the distributions in
    conflict, and the remedy." Re-catching it here to re-raise as something else would be a
    second, narrower vocabulary standing in front of the real one; letting it propagate is
    what `weft_cli.cli.run_command`'s own `except WeftError` already exists for, and
    `weft_cli.exit_codes.exit_code_for` maps the whole family to exit **4** with no
    per-command mapping to keep in step.
    """

    args_model: ClassVar[type[BaseModel]] = PipelineNameArgs
    result_model: ClassVar[type[CommandResult]] = PipelineValidateCommandResult
    permission_class: ClassVar[PermissionClass] = PermissionClass.READ
    help: ClassVar[str] = _VALIDATE_HELP

    def __init__(self, config: object = None) -> None:
        del config

    async def run(self, args: BaseModel, ctx: Context) -> Outcome[CommandResult]:
        validate_args = cast(PipelineNameArgs, args)
        deps = ctx.require(Dependencies)
        catalogue = full_catalogue(reports=deps.reports)
        resolved = _resolved_or_refuse(validate_args.name, deps=deps, catalogue=catalogue)
        return Produced(
            value=PipelineValidateCommandResult(
                name=resolved.name, stage_count=len(resolved.stages)
            )
        )


class PipelineDiffCommand:
    """`weft pipeline diff <a> <b>` — see the module docstring and `weft_cli.pipeline_diff`."""

    args_model: ClassVar[type[BaseModel]] = PipelineDiffArgs
    result_model: ClassVar[type[CommandResult]] = PipelineDiffCommandResult
    permission_class: ClassVar[PermissionClass] = PermissionClass.READ
    help: ClassVar[str] = _DIFF_HELP

    def __init__(self, config: object = None) -> None:
        del config

    async def run(self, args: BaseModel, ctx: Context) -> Outcome[CommandResult]:
        diff_args = cast(PipelineDiffArgs, args)
        deps = ctx.require(Dependencies)
        catalogue = full_catalogue(reports=deps.reports)
        resolved_a = _resolved_or_refuse(diff_args.a, deps=deps, catalogue=catalogue)
        resolved_b = _resolved_or_refuse(diff_args.b, deps=deps, catalogue=catalogue)
        return Produced(value=PipelineDiffCommandResult(diff=diff_resolved(resolved_a, resolved_b)))


class PipelineDeriveCommand:
    """`weft pipeline derive <parent> <name>` — see the module docstring.

    **`write`-class, repaired 2026-08-20 from `overwrite`** — see `PipelineAlreadyExistsError`'s
    own docstring for the argument in full. Scaffolding `pipelines/<name>.yaml` for a name
    nothing has used yet is `docs/03-cli.md`'s own `write`-row example, "write a derived
    pipeline", not a replace; a name already on disk is refused outright, loudly, naming the
    path — never silently replaced, never asked about.
    """

    args_model: ClassVar[type[BaseModel]] = PipelineDeriveArgs
    result_model: ClassVar[type[CommandResult]] = PipelineDeriveCommandResult
    permission_class: ClassVar[PermissionClass] = PermissionClass.WRITE
    help: ClassVar[str] = _DERIVE_HELP

    def __init__(self, config: object = None) -> None:
        del config

    async def run(self, args: BaseModel, ctx: Context) -> Outcome[CommandResult]:
        derive_args = cast(PipelineDeriveArgs, args)
        deps = ctx.require(Dependencies)
        catalogue = full_catalogue(reports=deps.reports)
        if derive_args.parent not in catalogue:
            options = tuple(sorted(catalogue))
            raise UnknownPipelineNameError(
                f"'{derive_args.parent}' is not a pipeline this project knows. Known "
                f"pipelines: {', '.join(options) or '(none)'}.",
                valid_options=options,
                pipeline=derive_args.parent,
                remedy=(
                    f"use one of: {', '.join(options) or '(none — no pipeline is known yet)'}."
                ),
            )

        DEFAULT_PIPELINES_DIR.mkdir(parents=True, exist_ok=True)
        path = DEFAULT_PIPELINES_DIR / f"{derive_args.name}.yaml"
        if path.exists():
            raise PipelineAlreadyExistsError(
                f"'{path}' already exists. 'weft pipeline derive' creates a new pipeline "
                f"document; it does not replace one. Choose a different name, or remove "
                f"the existing file first if you mean to start over.",
                path=str(path),
            )
        document = {"name": derive_args.name, "extends": derive_args.parent}
        path.write_text(yaml.safe_dump(document, sort_keys=False))

        return Produced(
            value=PipelineDeriveCommandResult(
                parent=derive_args.parent, name=derive_args.name, path=str(path)
            )
        )


def register_pipeline_commands(registrar: PackRegistrar) -> None:
    """Register all five `pipeline` commands — called from `weft_cli.commands.register`,
    never from a second entry point (see the module docstring).
    """
    registrar.add(Command, "pipeline list", PipelineListCommand)
    registrar.add(Command, "pipeline show", PipelineShowCommand)
    registrar.add(Command, "pipeline derive", PipelineDeriveCommand)
    registrar.add(Command, "pipeline validate", PipelineValidateCommand)
    registrar.add(Command, "pipeline diff", PipelineDiffCommand)


__all__ = [
    "NoArgs",
    "PipelineAlreadyExistsError",
    "PipelineDeriveArgs",
    "PipelineDeriveCommand",
    "PipelineDeriveCommandResult",
    "PipelineDiffArgs",
    "PipelineDiffCommand",
    "PipelineDiffCommandResult",
    "PipelineListCommand",
    "PipelineListCommandResult",
    "PipelineNameArgs",
    "PipelineShowCommand",
    "PipelineShowCommandResult",
    "PipelineValidateCommand",
    "PipelineValidateCommandResult",
    "register_pipeline_commands",
]
