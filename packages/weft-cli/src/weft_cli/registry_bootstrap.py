"""Building the registry a command needs, and the one place `weft-cli` opens a file.

`docs/build-ledger.md` 0.9's own note on why discovery took no file format at
step 5: *"the format question moves intact to 0.9, where the CLI is the only
thing that opens a file."* This module is that file-opener, and it reads
exactly one: `weft.toml`'s `[packs] allow` — `docs/02-extension-model.md` →
*The trust model*'s settled posture, parsed with `weft_kernel.discovery.allow_list_from_config`,
which already exists for precisely this caller. Absence is not an error:
"`weft.toml` — optional. Absent means open."

**Task 1.12 adds `[plugins]` to the same one file.** `docs/02-extension-model.md`
§3 → *When resolution fails*: "the pin is read by the operator-policy loader
in weft-cli... never by the kernel." This is that loader's other half —
`plugin_pins_from_config` parses the table the same way `allow_list_from_config`
already parses `[packs] allow`, and `build_dependencies` hands the result to
`Registry(plugin_pins=...)` before `discover()` ever runs, so every pack's
`register()` call sees a registry that already knows how to arbitrate a
collision it is about to cause.

**Task 2.29 adds `[services]`, and it is the same one file again.** Which
`Embedder` a run resolves is an operator's choice rather than a constant in
`weft_cli.ingest` — the argument is `weft_cli.services`', not this module's —
and it is parsed from the *same* `_document_at` call as everything above, so
the allow-list, the pack settings, the pins and the service selection cannot
come from two different reads of one file.

**Where pack settings come from, and the narrowing that decides it.**
`docs/02-extension-model.md` §2's `packs:` settings block (keyed by
distribution, validated against a pack's own Pydantic model) is real, but
*which file it lives in was an open inconsistency* — §2 writes it into
`weft.yaml`, while `docs/03-cli.md` → *Project context* describes `weft.toml`
as the one project-defaults file and has `weft init` scaffold it.

**Phase 0 narrows it to `weft.toml`, and this module is where that is true.**
Not by preference: this module already had to open `weft.toml` for
`[packs] allow`, and a second file read for the settings beside it would mean
two project files in a phase whose whole job is wiring. `02` §2's `weft.yaml`
is the outlier against `03`, `weft.toml.example` and `weft init` — the same
shape as step 10's *"names the distribution"*, corrected the same way rather
than honoured because it was written first. Reversible: the loader is
`pack_settings_from_config`, and pointing it at a different file changes one
function.

**The file wins over the environment, key by key** — see
`merged_pack_settings`. `WEFT_DATABASE_URL` is offered as `weft-store`'s `dsn`
only when `weft.toml` does not say, so a stale shell export cannot silently
send a project at a database its own configuration does not name. The value is
still read exclusively by `discover()`'s `interpolate_env`; this module never
reads it, exactly as `docs/02-extension-model.md` requires.

**`pack_settings_from_environment` checks the variable's *presence*, never its value.**
`interpolate_env` raises `EnvInterpolationError` outright, uncaught, when a
referenced variable is unset — correct for a config file that names a
variable a caller explicitly asked to resolve, but wrong here: `weft-store`'s
settings are this module's own default, assembled whether or not a database
has been configured yet, and a bare crash on every registry-needing command
— including `plugins doctor`, the one command meant to diagnose exactly this
— would be worse than the loud, per-pack `FAILED` report Pydantic validation
already produces for a `dsn` genuinely missing. So `${env:WEFT_DATABASE_URL}`
is offered only when the variable exists; otherwise `weft-store` is handed no
settings at all, which — like any pack given `{}` it cannot validate against
— resolves to `PackStatus.FAILED` with a plain "field required" reason,
diagnosable through `doctor` rather than a stack trace before `doctor` can
even run.

**The exit-code split is computed here, before a pipeline is ever resolved.**
`docs/02-extension-model.md` → *The trust model*: "A pipeline naming a plugin
from a `refused` pack exits 3... A name provided by no pack at all stays 4...
with its reason attached." Phase 0's built-in pipeline names a fixed, known
set of distributions (`weft-extract`, `weft-chunk`, `weft-embed`,
`weft-store`), so `require_active` checks each one's `PackReport` directly
rather than parsing an `UnknownPluginError` message after the fact.

**That fixed set stopped being the whole answer at task 2.29, and
`require_plugin` is the other half** — a repair for a reviewer finding. Once
`[services] embed` lets an operator's file name the plugin, the distribution
behind that name may be `weft-openai` or a stranger's pack, and no tuple
written in this repository can contain it. `require_active` still covers the
distributions this repository's own commands name; `require_plugin` covers
the name itself, whoever provides it, and it is the one that keeps the two
sentences above true for a third-party pack.

**Task 2.30 adds `[llm.roles]`, from the same one-file read again.** Which
provider and model answer a call made under a role is an operator's choice
in `weft.toml`, exactly as `[services]` is — see `weft_cli.llm_roles`'s own
module docstring for why it is its own top-level table rather than a third
`[services]` field. **Task 2.10 adds `[llm.retry]` beside it**, for the same
reason and out of the same parse: it built the retry wrapper the block
configures, and a knob parsed by one reader and dropped before the run that
needs it is a knob that silently does nothing.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

from weft_cli.exit_codes import ExitCode
from weft_cli.llm_roles import LLMRoles, LLMSection, llm_section_from_config
from weft_cli.services import ServiceSelection, service_selection_from_config
from weft_kernel.discovery import (
    PackReport,
    PackStatus,
    allow_list_from_config,
    discover,
    plugin_pins_from_config,
)
from weft_kernel.errors import WeftError
from weft_kernel.registry import Registry, UnknownPluginError

#: `docs/build-ledger.md` 0.9's own note — see the module docstring.
DEFAULT_CONFIG_PATH = Path("weft.toml")

#: `.env.example`'s own name for the one connection string Phase 0 needs.
_DATABASE_URL_VAR = "WEFT_DATABASE_URL"

#: The statuses that mean a distribution is installed and permitted, and still did not put
#: everything it publishes in the registry. `require_plugin` names these when a plugin name
#: does not resolve, because one of them is the likeliest reason it did not.
_CONTRIBUTED_INCOMPLETELY = (
    PackStatus.FAILED,
    PackStatus.PARTIAL,
    PackStatus.ALLOWED_NOT_INSTALLED,
)


class ConfigFileError(WeftError):
    """`config_path` exists but is not readable as `weft.toml` — malformed TOML, or unreadable.

    `docs/03-cli.md` -> *Project context*: "`weft.toml` — optional. Absent means open." A file
    that is genuinely *absent* is not this — `allow_list_from_file` already answers `None` for
    that, before either `open()` or `tomllib.load()` ever runs. This is the other case: a
    `weft.toml` that exists but a syntax error or a permissions problem stops from being parsed.
    Raising it as a `WeftError` — naming the file and what went wrong — is what lets
    `weft_cli.cli.dispatch`'s `except WeftError` map it to exit 4, a diagnosable message, rather
    than the raw `tomllib.TOMLDecodeError` or `OSError` surfacing as an unexplained traceback out
    of `plugins doctor`, the one command meant to diagnose exactly this.
    """


@dataclass(frozen=True, slots=True, kw_only=True)
class Dependencies:
    """What a registry-needing command's handler receives.

    The built registry, its reports, and what `[services]` selected — read
    from the same single parse of `weft.toml` as the allow-list and the pack
    settings, so no two readers of one file can disagree about what it says.

    `llm` defaults to an empty section — no role mapped and the default retry
    policy — rather than carrying no default at all, for the same reason every
    field two tasks over on `ServiceSelection` carries one: a caller building
    `Dependencies` directly, in a test or a library use `weft ask` does not yet
    take, should not have to construct one by hand for a run that never asks a
    model anything. `llm_roles` stays available as a property, because task
    2.30's shape (a bare role table) is what every existing caller reads.
    """

    registry: Registry
    reports: tuple[PackReport, ...]
    services: ServiceSelection
    llm: LLMSection = field(default_factory=LLMSection)

    @property
    def llm_roles(self) -> LLMRoles:
        """`[llm.roles]` alone — the narrow view every caller before task 2.10 held."""
        return self.llm.roles


def build_dependencies(
    config_path: Path = DEFAULT_CONFIG_PATH, *, strict_pins: bool = True
) -> Dependencies:
    """Discover every installed pack, honouring `[packs] allow` from `config_path` if present.

    Only ever called by a command whose `weft_cli.permissions.CliCommand.needs_registry`
    is `True` — see `weft_cli.cli` — which is what keeps `weft --version` from
    running a single line of pack code (fitness function 8(b)).

    `strict_pins` is threaded straight through to `discover()` — see its own
    docstring's *repair for a reviewer finding* note. `weft_cli.cli.dispatch`
    passes `False` only for `plugins list`/`plugins doctor`; every other
    caller keeps the default, so an inert `[plugins]` pin still refuses
    `index`/`ask` exactly as it always has.
    """
    _ensure_chunk_offset_rehydrates()
    document = _document_at(config_path)
    allow = None if document is None else allow_list_from_config(document)
    settings = merged_pack_settings(document)
    pins = {} if document is None else plugin_pins_from_config(document)
    services = service_selection_from_config(document)
    llm = llm_section_from_config(document)
    registry = Registry(plugin_pins=pins)
    reports = discover(registry, allow=allow, pack_settings=settings, strict_pins=strict_pins)
    return Dependencies(registry=registry, reports=reports, services=services, llm=llm)


def _ensure_chunk_offset_rehydrates() -> None:
    """Make `weft_chunk.payload.ChunkOffset` reconstructable by `weft_store.rehydrate`.

    Every chunk `weft-chunk` derives now carries `ChunkOffset` (ledger 2.9, the
    page-attribution gap `weft_chunk.fixed_size`'s own module docstring names), and
    `weft_store.rehydrate` refuses to read a stored node back unless the namespace that
    reached storage was registered first. Neither pack makes this call itself —
    `weft_chunk.__init__`'s own module docstring says why: fitness function 9(a) proves a
    stranger can extend `weft-chunk` from a wheel carrying only `weft-kernel` and
    `weft-chunk`, and a hard `weft-store` dependency there would break that. `weft-cli`
    depends on both, so this is where the two ends of a real pipeline meet.

    **Imported lazily, inside this function, never at module scope.** A top-level import
    of `weft_chunk`/`weft_store` here would put both in `sys.modules` for *every*
    command `build_dependencies` is not even called for — `weft --version` included,
    which is exactly what fitness function 8(b) refuses (`test_ff8_trust_model.py`
    caught this once already, as a module-level version of this same call).

    **Checked first, not caught blindly — a repair for a reviewer finding.** This function
    runs once per command but many times over within this module's own test suite, each
    against the one, process-wide registry `register_ext_model` writes to — unlike the
    plugin `Registry` `build_dependencies` builds fresh every call. The first cut wrapped
    the call in `contextlib.suppress(DuplicateRegistrationError)` unconditionally, which
    made "this function's own idempotent second call" and "a genuine second class claiming
    the `weft-chunk` namespace" indistinguishable — exactly the failure mode CLAUDE.md
    names by description: a silent fallback whose success and failure paths cannot be told
    apart. So this looks the namespace up first: if `ChunkOffset` itself is already the
    registrant, there is nothing to do — it is this function's own earlier call in this
    process. Otherwise it calls `register_ext_model`, unguarded, and lets
    `DuplicateRegistrationError` propagate — naming both classes — exactly as
    `weft_store.rehydrate`'s own docstring says every namespace collision must.
    """
    from weft_chunk.payload import ChunkOffset
    from weft_kernel.payload import ExtModel
    from weft_kernel.registry import UnknownPluginError
    from weft_store import register_ext_model
    from weft_store.rehydrate import ext_models

    try:
        registrant = ext_models.entry(ExtModel, ChunkOffset.__namespace__).factory
    except UnknownPluginError:
        register_ext_model(ChunkOffset)
        return
    if registrant is not ChunkOffset:
        register_ext_model(ChunkOffset)


def merged_pack_settings(document: dict[str, object] | None) -> dict[str, dict[str, object]]:
    """Pack settings from `weft.toml`, with the environment filling only what it does not set.

    **The file wins, key by key.** `weft.toml` is a project stating what it wants;
    `WEFT_DATABASE_URL` is whatever the shell happened to export. An ambient value that
    overrode an explicit one would mean a developer with a stale variable silently running
    against a different database from the one their project names — a store answering
    plausibly against the wrong data, which is the failure this project exists to remove.

    The environment is a *convenience for the case with no file at all*, which is the path
    `manual/quickstart.md` walks: one `export` and a stranger is running, without first
    learning what a pack settings block is. It is not a second configuration system, and it
    contributes exactly one key.
    """
    from_file = pack_settings_from_config(document)
    merged: dict[str, dict[str, object]] = {
        distribution: dict(values) for distribution, values in from_file.items()
    }
    for distribution, values in pack_settings_from_environment().items():
        target = merged.setdefault(distribution, {})
        for key, value in values.items():
            target.setdefault(key, value)
    return merged


def pack_settings_from_config(document: dict[str, object] | None) -> dict[str, dict[str, object]]:
    """Every `[packs.<distribution>]` table in a parsed `weft.toml`.

    `[packs]` carries both the allow-list and the per-distribution settings blocks, so the
    sub-tables are exactly its dict-valued entries — `allow` is a list and is skipped by that
    same rule rather than by being named here, which means a future scalar key under `[packs]`
    does not have to be added to a second list to be ignored correctly.

    **A `packs` key that is present but not a table is refused, the same way
    `weft_kernel.discovery.allow_list_from_config` refuses it** — `docs/02-extension-model.md`
    §2 → *The trust model*. This module reads `[packs]` a second time, independently of that
    function, so it carried the identical `isinstance(packs, dict)` bug: `packs =
    ["weft-store"]` used to fail the check and return `{}`, silently indistinguishable from a
    `weft.toml` with no `[packs]` table at all. Two distributions reading one file must not
    disagree about what a malformed shape means, so this raises the same way, naming the same
    shapes. `None` only for a key genuinely absent from `document`.
    """
    if document is None:
        return {}
    if "packs" not in document:
        return {}
    packs = document["packs"]
    if not isinstance(packs, dict):
        raise WeftError(
            f"weft.toml's [packs] must be a table, not {type(packs).__name__} — found "
            f"`packs = {packs!r}`. Did you mean `[packs]\\nallow = [...]`? See "
            f"docs/02-extension-model.md section 2, The trust model."
        )
    return {
        str(key): dict(cast("dict[str, object]", value))
        for key, value in cast("dict[str, object]", packs).items()
        if isinstance(value, dict)
    }


def pack_settings_from_environment() -> dict[str, dict[str, object]]:
    """`weft-store`'s settings, referencing `${env:WEFT_DATABASE_URL}` only if it is set.

    See the module docstring, *"`pack_settings_from_environment` checks the variable's
    presence, never its value."* — this reads only whether the name exists in
    `os.environ`, never the connection string itself.
    """
    if _DATABASE_URL_VAR not in os.environ:
        return {}
    return {"weft-store": {"dsn": f"${{env:{_DATABASE_URL_VAR}}}"}}


def require_active(
    reports: tuple[PackReport, ...], *, distributions: tuple[str, ...]
) -> tuple[ExitCode, str] | None:
    """`None` if every one of `distributions` is usable; otherwise the exit code and why.

    `PARTIAL` is let through: it means *something* registered, and whether it
    is the specific plugin a command needs is exactly what pipeline
    resolution's own `weft_kernel.registry.UnknownPluginError` checks next —
    this function only rules out the cases it can decide on its own:
    genuinely absent, refused by policy, or `register()` raising outright.
    """
    by_distribution = {report.distribution: report for report in reports}
    for distribution in distributions:
        report = by_distribution.get(distribution)
        if report is None or report.status is PackStatus.ALLOWED_NOT_INSTALLED:
            return (
                ExitCode.RESOLUTION_FAILED,
                f"'{distribution}' is not installed. Install it, or run "
                f"`weft plugins doctor` to see every pack's status.",
            )
        if report.status is PackStatus.REFUSED:
            return (
                ExitCode.POLICY_REFUSED,
                f"'{distribution}' is refused by [packs] allow in {DEFAULT_CONFIG_PATH}. "
                f"Add it there to permit it.",
            )
        if report.status is PackStatus.FAILED:
            return (
                ExitCode.RESOLUTION_FAILED,
                f"'{distribution}' failed to register: {report.reason}",
            )
    return None


def require_plugin(
    reports: tuple[PackReport, ...],
    *,
    registry: Registry,
    contract: type[object],
    name: str,
    setting: str,
) -> tuple[ExitCode, str] | None:
    """`None` if `name` resolves for `contract`; otherwise the exit code and why it does not.

    **The gate `require_active` structurally cannot be.** That one takes a
    fixed tuple of distribution names, which was sound while every plugin name
    a command resolved was written in this repository. It stopped being sound
    the moment `[services] embed` let an operator's file name the plugin
    (ledger task 2.29): the distribution behind that name can be `weft-openai`,
    or a pack neither of us wrote, and neither can ever appear in a tuple
    compiled in here. With the providing pack `refused` or `failed`,
    `require_active` returned `None`, the run proceeded, and the operator was
    told by `weft_kernel.registry.UnknownPluginError` that *no distribution
    has registered that name* — which is false, and which
    `docs/02-extension-model.md` → *The trust model* settles twice over:
    "every unresolvable plugin name carries its reason... never a bare
    `unknown plugin 'docling'`", and a name from a `refused` pack "exits 3,
    refused, and names the config key that would permit it."

    So this takes the contract and the name instead of a distribution list,
    and reads `reports` only once resolution has already failed:

    - **Refused packs present → exit 3.** A refused pack is *never imported*,
      which is the whole point of refusing it, so nothing here can prove it is
      the one that would have claimed `name` — and the message says exactly
      that rather than asserting it. The code is still policy's: the operator's
      next move is `[packs] allow`, and a CI job acting on 3 is acting on the
      right thing.
    - **Failed, partial or allowed-but-absent packs → exit 4, with their
      reasons attached** — `02` again: "a name lost to `failed` or `partial`
      stays 4 with its reason attached, because neither is a policy decision."
    - **Nothing amiss → exit 4** and the registry's own message, whose claim
      that nothing registered the name is, in that case, true.

    `setting` names where `name` came from — `[services] embed`, `--extract` —
    because "'openai' is not registered" sends an operator looking for a pack
    when the thing to edit is a line in their own file. `contract` is a bare
    `type[object]` for the same reason the kernel's own registry takes one:
    this module names no capability, and the same gate has to serve the roles
    `[services]` grows later.
    """
    try:
        registry.entry(contract, name)
    except UnknownPluginError as exc:
        return _unresolved(reports, contract=contract, name=name, setting=setting, plain=str(exc))
    return None


def _unresolved(
    reports: tuple[PackReport, ...],
    *,
    contract: type[object],
    name: str,
    setting: str,
    plain: str,
) -> tuple[ExitCode, str]:
    """`require_plugin`'s answer once the name is known not to resolve — see its docstring."""
    refused = tuple(report for report in reports if report.status is PackStatus.REFUSED)
    silent = tuple(report for report in reports if report.status in _CONTRIBUTED_INCOMPLETELY)
    wanted = f"{setting} names '{name}', and no registered {contract.__name__} has that name."
    if refused:
        listed = ", ".join(sorted(report.distribution for report in refused))
        return (
            ExitCode.POLICY_REFUSED,
            f"{wanted} These distributions are refused by [packs] allow in "
            f"{DEFAULT_CONFIG_PATH} and were never imported, so what they would have "
            f"registered is unknown: {listed}. Add the one that provides '{name}' to "
            f"[packs] allow. {plain}",
        )
    if silent:
        listed = "; ".join(
            f"{report.distribution} ({report.status.value}"
            + (f": {report.reason}" if report.reason else "")
            + ")"
            for report in sorted(silent, key=lambda report: report.distribution)
        )
        return (
            ExitCode.RESOLUTION_FAILED,
            f"{wanted} These distributions contributed nothing, or only part of what they "
            f"publish, and one of them may be the one that provides it: {listed}. {plain}",
        )
    return (ExitCode.RESOLUTION_FAILED, f"{wanted} {plain}")


def allow_list_from_file(config_path: Path) -> tuple[str, ...] | None:
    """`None` if `config_path` is absent; its `[packs] allow`, parsed, if it exists.

    Raises `ConfigFileError` — a `WeftError` — if `config_path` exists but `tomllib` cannot
    parse it or the file cannot be read at all, naming the file and the underlying reason.
    See `ConfigFileError`'s own docstring for why this module re-raises rather than letting
    `tomllib.TOMLDecodeError` or `OSError` escape uncaught.
    """
    document = _document_at(config_path)
    return None if document is None else allow_list_from_config(document)


def _document_at(config_path: Path) -> dict[str, object] | None:
    """`config_path` parsed, or `None` if it is absent. One read, so the allow-list and the
    pack settings blocks cannot come from two different parses of the same file.
    """
    if not config_path.is_file():
        return None
    try:
        with config_path.open("rb") as handle:
            return tomllib.load(handle)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigFileError(f"{config_path} is not valid TOML: {exc}") from exc
    except OSError as exc:
        raise ConfigFileError(f"{config_path} could not be read: {exc}") from exc
