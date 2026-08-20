"""`weft config get|set` — the project's own effective configuration, and where it came from.

Task **3.7**. `docs/03-cli.md` → *Project context*: "`weft config get --origin` prints where
each effective value came from, which is the question people actually have." This module is
where that question is answered — `weft_cli.config_commands` is the thin `Command` shell
around it, on the same formatting/data split every other command in this package draws.

**The four keys this module reads are the four keys `weft.toml` already has a reader for.**
`weft_cli.services.ServiceSelection` (`[services] embed`/`store`) and `weft_cli.
permission_policy.PermissionPolicy` (`[permissions] overwrite`/`destroy`) are the only two
project-config blocks any command actually consults today — `[llm]`/`[packs]`/`[plugins]`
are real, but nothing in `docs/03-cli.md` → *Project context* names them as `config get/set`
surface, and inventing a dotted key for a block nothing here was asked to expose would be
documentation for a feature nobody requested. `CONFIG_KEYS` is exactly `services.embed`,
`services.store`, `permissions.overwrite`, `permissions.destroy` — the same "a key the CLI
does not read is refused, naming the keys it does" rule `docs/03-cli.md` already states for
`[services]` itself, applied one level up to the `config` command's own vocabulary.

**Why `--origin` needs the raw, unmerged document — the reference's sentinel bug, avoided rather
than reproduced.** `.phase3-design.md` §2.6, verified at source: `a_prior_project`'s `ConfigMerger`
compares a merged value against a **sentinel** (`cli_overrides.get('embedding_provider',
'local')` then `== 'local'`, `merger.py:42-44`), so an explicit `--embedding-provider local`
is indistinguishable from never having passed the flag at all — it can never override a
config file naming something else, because by the time anything asks "was this set?" the
sentinel comparison has already thrown the answer away. `weft_cli.services.
service_selection_from_config` and `weft_cli.permission_policy.permission_policy_from_config`
both build exactly the merged shape that bug lives in: comparing their *output* — a
`ServiceSelection`/`PermissionPolicy` instance — against `ServiceSelection()`/
`PermissionPolicy()`'s own built-in defaults would reproduce the identical defect one field
at a time, unable to tell "`weft.toml` explicitly names `embed = "hash"`, which happens to
equal the default" from "`weft.toml` says nothing about `embed` at all." So `effective_config`
below never does that comparison — it reads the **raw parsed mapping** (`weft_cli.
registry_bootstrap.document_at`, public since this task for exactly this reader) and asks,
per key, whether that literal key is present in the file, independent of what value it holds.
That is the one fact a merged model can never recover once building it has already happened,
and it is the only fact `--origin` needs.

**`set_config_text` edits text, never a re-serialised document.** `weft.toml.example` and a
real project's own `weft.toml` carry extensive prose comments — `dsn = "${env:...}"`'s own
surrounding paragraph, say — that a parse-mutate-`tomllib.dump`-back round trip would discard
outright (`tomllib` is read-only, and no TOML *writer* is a dependency this distribution
carries; adding one purely to preserve comments on every `config set` call is a real cost for
a feature this task can get more cheaply and more safely another way). This module instead
performs the smallest textual edit that makes the key say what was asked: find the `[section]`
header, find or insert the `key = "value"` line directly under it, and leave every other byte
in the file — including every comment — untouched. `tests/unit/weft_cli/test_config_surface.py`
proves the round trip: write with `set_config_text`, re-read with `tomllib.loads`, get the
value back.
"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Final, cast

from pydantic import BaseModel, ConfigDict

from weft_cli.permission_policy import PermissionAction
from weft_cli.permission_policy import permission_policy_from_config as _permission_policy
from weft_cli.services import service_selection_from_config as _service_selection
from weft_kernel.errors import UnresolvedNameError, WeftError

#: Task 3.7's own closed vocabulary — see the module docstring for why these four and no
#: others. `(section, field)` per dotted key, read by both `effective_config` (to know which
#: model field answers it) and `set_config_text`'s own caller (to know which `[section]` to
#: edit).
_KEY_FIELDS: Final[dict[str, tuple[str, str]]] = {
    "services.embed": ("services", "embed"),
    "services.store": ("services", "store"),
    "permissions.overwrite": ("permissions", "overwrite"),
    "permissions.destroy": ("permissions", "destroy"),
}

#: Every dotted key `weft config get|set` reads or writes, sorted — `UnknownConfigKeyError`'s
#: own `valid_options`, and `weft config get`'s own "print everything" default.
CONFIG_KEYS: Final[tuple[str, ...]] = tuple(sorted(_KEY_FIELDS))


class ConfigOrigin(StrEnum):
    """Where one effective config value came from — `--origin`'s whole vocabulary.

    Two members, not three: `docs/03-cli.md` → *Project context* states the precedence as
    "explicit flags beat the file, the file beats built-in defaults", but `weft config get`
    has no other command's flags to merge against — it inspects the *project's* own
    configuration, `weft.toml` against the built-in defaults, never one particular
    invocation's own overrides (`weft_cli.config_commands`' own module docstring names this
    explicitly, so a reader does not go looking for a third member that was never real here).
    """

    DEFAULT = "default"
    FILE = "file"


class ConfigEntry(BaseModel):
    """One effective config value — `weft config get`'s own unit, with or without `--origin`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    key: str
    value: str
    origin: ConfigOrigin


class UnknownConfigKeyError(WeftError, UnresolvedNameError):
    """`weft config get|set` names a key this module does not read.

    `docs/03-cli.md` → *Project context*: "a key the CLI does not yet read is refused, naming
    the keys it does". Fitness function 12's family — `valid_options` is `CONFIG_KEYS`,
    always, since the vocabulary itself never depends on what any particular `weft.toml` says.
    """

    def __init__(self, message: str, *, valid_options: tuple[str, ...]) -> None:
        super().__init__(message)
        self.valid_options = valid_options


def _refuse_unknown_key(key: str) -> None:
    if key not in _KEY_FIELDS:
        raise UnknownConfigKeyError(
            f"'{key}' is not a key weft config reads or writes. Known keys: "
            f"{', '.join(CONFIG_KEYS)}.",
            valid_options=CONFIG_KEYS,
        )


def section_and_field(key: str) -> tuple[str, str]:
    """`("services", "embed")` for `"services.embed"` — `weft_cli.config_commands.
    ConfigSetCommand`'s own way to know which `[section]`/field `set_config_text` should
    edit, without reaching into this module's private `_KEY_FIELDS` directly.
    """
    _refuse_unknown_key(key)
    return _KEY_FIELDS[key]


def _written_section(document: dict[str, object] | None, section: str) -> dict[str, object]:
    """Every key `[section]` literally sets in `document` — `{}` if the table, or the whole
    document, is absent. Never validated: this exists only to answer "is this key *present*",
    never "is its value legal" — `weft_cli.services`/`weft_cli.permission_policy` already
    validate the values themselves, and `effective_config` below calls both.
    """
    if document is None:
        return {}
    written = document.get(section)
    if not isinstance(written, dict):
        return {}
    return cast("dict[str, object]", written)


def effective_config(document: dict[str, object] | None) -> tuple[ConfigEntry, ...]:
    """Every key `CONFIG_KEYS` names, its effective value, and where that value came from.

    See the module docstring's own paragraph on why `origin` is computed from the **raw**
    `document`, never from comparing `selection`/`policy` against their own built-in
    defaults. Sorted by key, so `weft config get`'s own output is stable across runs.
    """
    selection = _service_selection(document)
    policy = _permission_policy(document)
    services_written = _written_section(document, "services")
    permissions_written = _written_section(document, "permissions")

    values: dict[str, tuple[str, dict[str, object]]] = {
        "services.embed": (selection.embed, services_written),
        "services.store": (selection.store, services_written),
        "permissions.overwrite": (policy.overwrite.value, permissions_written),
        "permissions.destroy": (policy.destroy.value, permissions_written),
    }

    entries: list[ConfigEntry] = []
    for key in CONFIG_KEYS:
        value, written = values[key]
        _, field = _KEY_FIELDS[key]
        origin = ConfigOrigin.FILE if field in written else ConfigOrigin.DEFAULT
        entries.append(ConfigEntry(key=key, value=value, origin=origin))
    return tuple(entries)


def config_entry(document: dict[str, object] | None, key: str) -> ConfigEntry:
    """One key's `effective_config` entry — `UnknownConfigKeyError` if `key` is not one of
    `CONFIG_KEYS`.
    """
    _refuse_unknown_key(key)
    by_key = {entry.key: entry for entry in effective_config(document)}
    return by_key[key]


def validate_set_value(key: str, value: str) -> None:
    """`value` is legal for `key` — `UnknownConfigKeyError` for an unread key, a plain
    `WeftError` for a value `weft.toml`'s own loader would refuse at read time anyway.

    Deliberately does **not** check that `value` resolves to an installed plugin for
    `services.*` — `weft_cli.services.service_selection_from_config` does not either, on
    purpose: a `weft.toml` may legitimately name a plugin from a pack not installed *yet*
    (`docs/03-cli.md`'s own precedent for `use:`/`fallback:` in a pipeline document, applied
    here), and resolution is deferred to whichever command actually needs it — `weft_cli.
    registry_bootstrap.require_plugin` names it loudly, with the pack's own status, the
    moment something does. Checking eagerly here would make `weft config set` stricter than
    `weft.toml` itself, a second, disagreeing rule for the identical field.
    """
    _refuse_unknown_key(key)
    section, field = _KEY_FIELDS[key]
    if section == "permissions":
        # Repair, 2026-08-20 (`docs/build-ledger.md` 3.3's dated paragraph): examined for FF12
        # family membership and excluded, the identical reasoning `weft_cli.permission_policy`'s
        # own raise site for this exact value now states in full. `PermissionAction` is a closed,
        # two-member `StrEnum` fixed by the type itself, not a name resolved against a registry,
        # catalogue or document whose membership could ever differ — a type mismatch with a
        # friendlier message, not an unresolved name. Not brought into `NAME_RESOLUTION_FAMILY`.
        valid = {member.value for member in PermissionAction}
        if value not in valid:
            raise WeftError(
                f"'{key}' must be one of {sorted(valid)}, not {value!r} — "
                f"weft_cli.permission_policy.PermissionPolicy's own vocabulary."
            )
        return
    if not value:
        raise WeftError(f"'{key}' must name a plugin — an empty string is not a valid value.")
    del field


_SECTION_HEADER: Final[re.Pattern[str]] = re.compile(r"^\[(?P<name>[^\[\]]+)\]\s*$")


def _quote(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def set_config_text(text: str, *, section: str, key: str, value: str) -> str:
    """`text` (a `weft.toml`'s raw contents, or `""` for a file that does not exist yet),
    with `key = "value"` set inside `[section]` — every other byte untouched.

    See the module docstring's own paragraph for why this edits text rather than
    re-serialising a parsed document. Three cases, in the order a real `weft.toml` is most
    to least likely to already be in: the key already has a line inside the section (replace
    it in place); the section exists but the key does not (insert directly under the
    header); the section does not exist at all (append a fresh one at the end of the file).
    A commented-out line (`# embed = "..."`) is never mistaken for the key: the match is
    against each line's own stripped text, and a line starting with `#` never starts with
    the bare key name.
    """
    new_line = f"{key} = {_quote(value)}\n"
    lines = text.splitlines(keepends=True)

    section_start: int | None = None
    section_end = len(lines)
    for index, line in enumerate(lines):
        match = _SECTION_HEADER.match(line.strip())
        if match is None:
            continue
        if section_start is None:
            if match.group("name") == section:
                section_start = index
            continue
        section_end = index
        break

    if section_start is None:
        prefix = "" if not text or text.endswith("\n") else "\n"
        separator = "\n" if text.strip() else ""
        return f"{text}{prefix}{separator}[{section}]\n{new_line}"

    key_line = re.compile(rf"^{re.escape(key)}\s*=")
    for index in range(section_start + 1, section_end):
        if key_line.match(lines[index].strip()):
            lines[index] = new_line
            return "".join(lines)

    lines.insert(section_start + 1, new_line)
    return "".join(lines)


__all__ = [
    "CONFIG_KEYS",
    "ConfigEntry",
    "ConfigOrigin",
    "UnknownConfigKeyError",
    "config_entry",
    "effective_config",
    "section_and_field",
    "set_config_text",
    "validate_set_value",
]
