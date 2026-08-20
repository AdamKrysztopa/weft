"""`weft config get|set` — the `Command` shell around `weft_cli.config_surface`.

Task **3.7**, `docs/03-cli.md` → *Project context*. This module is deliberately thin: every
real decision — which keys exist, how origin is computed, how a value is validated, how the
file is edited — lives in `weft_cli.config_surface`, on the formatting/data split every
command in this package already draws (`weft_cli.commands`'s own module docstring, and
`weft_cli.pipeline_commands` beside it).

**`weft config get [--key <key>] [--origin]`, not `weft config get [<key>]`.** `weft_cli.
argparse_gen`'s own mechanical convention — "a field with no default is a required
positional; a field with a default is an optional flag" (that module's own docstring) — has
no shape for an *optional* positional, only a required one or a flag, and this module does
not widen that mechanism for one command: `key: str | None = None` therefore becomes
`--key`, mechanically, the identical rule every other optional field in this codebase's
generated grammar already follows. `weft config get` (no `--key`) prints every key
`weft_cli.config_surface.CONFIG_KEYS` names; `weft config get --key services.embed` prints
one.

**`weft config set <key> <value>` — both required, both positional**, because neither has a
default and `argparse_gen`'s ordinary rule gives exactly that shape with no special casing
needed. `ConfigSetCommand` is **`write`-class, decided (not defaulted) 2026-08-20** during the
same review that reclassified `weft_cli.commands.InitCommand` and `weft_cli.pipeline_commands.
PipelineDeriveCommand` — `docs/build-ledger.md`'s dated repair paragraph for tasks 3.3/3.6/3.7
has the argument in full. It does not fit `overwrite` (ask) on `docs/03-cli.md` → *Permissions*'s
own terms either: that class exists so a prompt can state "what will be destroyed and how
much of it", and `weft_cli.confirm.gate` genuinely has nothing to add here beyond restating
the invocation the terminal already shows — `set_config_text` "preserves every comment and
every other key untouched", so the entire blast radius is the one key and the one old value
the caller just named on the command line, unlike `overwrite`'s own worked examples
("reindex an existing collection", "replace a pipeline file"), each of which discards
something the invocation itself does not name or bound. Gating a single, self-describing
key edit behind a TTY prompt would buy nothing a reader does not already have, at the cost of
breaking `weft config set <key> <value>` in exactly the non-interactive script it is most
useful in — `weft init`'s own argument, applied here a second time.
"""

from __future__ import annotations

from typing import ClassVar, cast

from pydantic import BaseModel, ConfigDict, Field

from weft_cli.config_surface import (
    CONFIG_KEYS,
    ConfigEntry,
    config_entry,
    effective_config,
    section_and_field,
    set_config_text,
    validate_set_value,
)
from weft_cli.registry_bootstrap import DEFAULT_CONFIG_PATH, document_at
from weft_command.contract import Command, CommandResult
from weft_command.permission import PermissionClass
from weft_kernel.context import Context
from weft_kernel.discovery import PackRegistrar
from weft_kernel.payload import Outcome, Produced

_GET_HELP = (
    "the project's effective configuration — one key with --key, or every key CONFIG_KEYS "
    "names; --origin says whether each value is set in weft.toml or defaulted"
)

_SET_HELP = "set one key in weft.toml, preserving every comment and every other key untouched"


class ConfigGetArgs(BaseModel):
    """`weft config get [--key <key>] [--origin]`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    key: str | None = Field(
        default=None,
        description=f"the key to print — one of {', '.join(CONFIG_KEYS)}; omit for every key",
    )
    origin: bool = Field(
        default=False, description="print whether each value is set in weft.toml or defaulted"
    )


class ConfigSetArgs(BaseModel):
    """`weft config set <key> <value>`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    key: str = Field(description=f"the key to set — one of {', '.join(CONFIG_KEYS)}")
    value: str = Field(description="the new value")


class ConfigGetCommandResult(CommandResult):
    """`weft config get`'s whole answer — one entry per key printed."""

    entries: tuple[ConfigEntry, ...]
    show_origin: bool


class ConfigSetCommandResult(CommandResult):
    """`weft config set`'s whole answer — what was written, and where."""

    key: str
    value: str
    path: str


class ConfigGetCommand:
    """`weft config get` — see the module docstring."""

    args_model: ClassVar[type[BaseModel]] = ConfigGetArgs
    result_model: ClassVar[type[CommandResult]] = ConfigGetCommandResult
    permission_class: ClassVar[PermissionClass] = PermissionClass.READ
    help: ClassVar[str] = _GET_HELP

    def __init__(self, config: object = None) -> None:
        del config

    async def run(self, args: BaseModel, ctx: Context) -> Outcome[CommandResult]:
        get_args = cast(ConfigGetArgs, args)
        del ctx  # this command reads weft.toml directly; it needs no registered plugin
        document = document_at(DEFAULT_CONFIG_PATH)
        entries = (
            (config_entry(document, get_args.key),)
            if get_args.key is not None
            else effective_config(document)
        )
        return Produced(value=ConfigGetCommandResult(entries=entries, show_origin=get_args.origin))


class ConfigSetCommand:
    """`weft config set <key> <value>` — see the module docstring."""

    args_model: ClassVar[type[BaseModel]] = ConfigSetArgs
    result_model: ClassVar[type[CommandResult]] = ConfigSetCommandResult
    permission_class: ClassVar[PermissionClass] = PermissionClass.WRITE
    help: ClassVar[str] = _SET_HELP

    def __init__(self, config: object = None) -> None:
        del config

    async def run(self, args: BaseModel, ctx: Context) -> Outcome[CommandResult]:
        set_args = cast(ConfigSetArgs, args)
        del ctx
        validate_set_value(set_args.key, set_args.value)
        section, field = section_and_field(set_args.key)

        path = DEFAULT_CONFIG_PATH
        current = path.read_text(encoding="utf-8") if path.is_file() else ""
        updated = set_config_text(current, section=section, key=field, value=set_args.value)
        path.write_text(updated, encoding="utf-8")

        return Produced(
            value=ConfigSetCommandResult(key=set_args.key, value=set_args.value, path=str(path))
        )


def register_config_commands(registrar: PackRegistrar) -> None:
    """Register both `config` commands — called from `weft_cli.commands.register`, never
    from a second entry point.
    """
    registrar.add(Command, "config get", ConfigGetCommand)
    registrar.add(Command, "config set", ConfigSetCommand)


__all__ = [
    "ConfigGetArgs",
    "ConfigGetCommand",
    "ConfigGetCommandResult",
    "ConfigSetArgs",
    "ConfigSetCommand",
    "ConfigSetCommandResult",
    "register_config_commands",
]
