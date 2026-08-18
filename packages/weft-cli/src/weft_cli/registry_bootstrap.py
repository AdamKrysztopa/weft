"""Building the registry a command needs, and the one place `weft-cli` opens a file.

`docs/build-ledger.md` 0.9's own note on why discovery took no file format at
step 5: *"the format question moves intact to 0.9, where the CLI is the only
thing that opens a file."* This module is that file-opener, and it reads
exactly one: `weft.toml`'s `[packs] allow` — `docs/02-extension-model.md` →
*The trust model*'s settled posture, parsed with `weft_kernel.discovery.allow_list_from_config`,
which already exists for precisely this caller. Absence is not an error:
"`weft.toml` — optional. Absent means open."

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
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from weft_cli.exit_codes import ExitCode
from weft_kernel.discovery import PackReport, PackStatus, allow_list_from_config, discover
from weft_kernel.errors import WeftError
from weft_kernel.registry import Registry

#: `docs/build-ledger.md` 0.9's own note — see the module docstring.
DEFAULT_CONFIG_PATH = Path("weft.toml")

#: `.env.example`'s own name for the one connection string Phase 0 needs.
_DATABASE_URL_VAR = "WEFT_DATABASE_URL"


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
    """What a registry-needing command's handler receives: the built registry and its reports."""

    registry: Registry
    reports: tuple[PackReport, ...]


def build_dependencies(config_path: Path = DEFAULT_CONFIG_PATH) -> Dependencies:
    """Discover every installed pack, honouring `[packs] allow` from `config_path` if present.

    Only ever called by a command whose `weft_cli.permissions.CliCommand.needs_registry`
    is `True` — see `weft_cli.cli` — which is what keeps `weft --version` from
    running a single line of pack code (fitness function 8(b)).
    """
    document = _document_at(config_path)
    allow = None if document is None else allow_list_from_config(document)
    settings = merged_pack_settings(document)
    registry = Registry()
    reports = discover(registry, allow=allow, pack_settings=settings)
    return Dependencies(registry=registry, reports=reports)


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
    """
    if document is None:
        return {}
    packs = document.get("packs")
    if not isinstance(packs, dict):
        return {}
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
