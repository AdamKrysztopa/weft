"""The agent's tool catalogue — derived from the registry, never hand-written. Task **7.2a**.

`docs/05-grilling-sessions.md` → G12, settled 2026-09-06: a caller with no TTY cannot reach
`overwrite` or `destroy`, and its autonomous reach is `read`, `write` and `network` — see
`REACHABLE_CLASSES`. That is a **ceiling**, and this module makes it mechanical rather than a
list somebody maintains: `tool_catalogue` filters `weft_command.catalogue.command_entries` by
`permission_class` alone, so a third party's `destroy`-class command is out of the agent's reach
the day it ships, with nobody editing this file and nobody adding a name to anything.

Two commands are excluded by name instead, each for a reason the permission class itself cannot
see — see `EXCLUDED_BY_NAME`. A named exclusion with a stated reason is not a waiver: a waiver
says *this rule should apply here and does not*; these say *this rule does not decide this
case*, and `tests/unit/weft_agent/test_tools.py`'s own ratchet asserts each still names a live
command, so an exclusion cannot outlive the thing it excludes.

**This is a third rendering of one walk**, on `weft_cli.command_table`'s own footing —
`weft_cli.cli.build_parser` renders the registry to a terminal grammar and `weft_cli.
command_table` renders it to Markdown; this renders it to tool schemas. The walk itself lives in
`weft_command.catalogue`, never here and never in `weft_cli`, because `weft_agent` must not
import the driving adapter and the alternative to a shared walk is a second, hand-written one —
the same argument task 7.0 made for the invocation seam.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from pydantic import BaseModel, ConfigDict

from weft_command.catalogue import CommandNotDescribableError, command_entries
from weft_command.contract import Command
from weft_command.permission import PermissionClass
from weft_kernel.registry import Registry, unwrap_factory

#: G12's ceiling (`docs/05-grilling-sessions.md` → G12, settled 2026-09-06): nothing but a TTY
#: counts as consent for `overwrite` or `destroy`, and an agent is never a TTY, so those two
#: classes are permanently outside `REACHABLE_CLASSES` rather than reachable through some
#: approval channel this module would have to invent.
REACHABLE_CLASSES: Final[frozenset[PermissionClass]] = frozenset(
    {PermissionClass.READ, PermissionClass.WRITE, PermissionClass.NETWORK}
)

#: The one row a permission class cannot decide by itself, plus the one command the agent
#: should never run on the project it is itself running inside — see the module docstring.
EXCLUDED_BY_NAME: Final[frozenset[str]] = frozenset(
    {
        # `write`-class, and it writes `weft.toml` *including* `[permissions]` — an agent that
        # can call it can set `destroy = "allow"` and climb its own ceiling. The class is right
        # and the consequence is one level up, which no class-based filter can see.
        "config set",
        # Scaffolds a project. The agent should not scaffold the one it is running inside.
        "init",
    }
)


class AgentToolSpec(BaseModel):
    """One command, described the way a model calling it needs — never a `Command` itself and
    never wired into the loop (that is task 7.3).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    description: str
    parameters: Mapping[str, object]


def tool_catalogue(registry: Registry) -> Mapping[str, AgentToolSpec]:
    """Every registered `Command` G12's ceiling reaches, keyed by its registered name in full —
    `"pipeline list"`, with the space, exactly as `registry.names_for(Command)` reports it.

    Built from `weft_command.catalogue.command_entries`, the identical walk `weft_cli.
    command_table` renders to Markdown, filtered to `REACHABLE_CLASSES` and clear of
    `EXCLUDED_BY_NAME` — no deny-list of `destroy`-class names beyond that: the filter is the
    mechanism, not a list of what somebody has seen ship.
    """
    catalogue: dict[str, AgentToolSpec] = {}
    for command in command_entries(registry):
        if command.permission_class not in REACHABLE_CLASSES:
            continue
        if command.name in EXCLUDED_BY_NAME:
            continue
        factory = unwrap_factory(registry.entry(Command, command.name).factory)
        catalogue[command.name] = AgentToolSpec(
            name=command.name,
            description=command.help,
            parameters=_args_schema_of(factory, command.name),
        )
    return catalogue


def _args_schema_of(factory: object, name: str) -> Mapping[str, object]:
    """`factory.args_model.model_json_schema()`, or a loud, specific failure naming which
    command and which field — the same discipline `weft_command.catalogue`'s own defensive
    readers hold for `help` and `permission_class`, and for the identical reason: a bare
    `getattr(..., "args_model")` would turn a future relaxation of `Command.
    required_declarations` into a crash with no attribution instead of a named refusal.
    """
    args_model = getattr(factory, "args_model", None)
    if not (isinstance(args_model, type) and issubclass(args_model, BaseModel)):
        raise CommandNotDescribableError(
            f"'{name}' carries no `args_model` attribute naming a Pydantic model. Every "
            "registered Command must declare one (weft_command.contract.Command) and the "
            "agent's tool catalogue refuses to invent a placeholder schema for one that does "
            "not exist."
        )
    if args_model is BaseModel:
        # `issubclass(BaseModel, BaseModel)` is `True`, so the check above lets the base class
        # itself through — and pydantic then refuses `model_json_schema()` on it with a bare
        # `AttributeError`, which escapes unattributed past the named refusal this function exists
        # to raise. An argument-free command declares a real empty model (`weft_cli.commands`'
        # own `NoArgs`); the bare class is a declaration mistake, and it is named as one.
        raise CommandNotDescribableError(
            f"'{name}' declares `args_model = BaseModel`, the base class itself rather "
            f"than a model of its own. Declare an empty subclass — the CLI's own argument-free "
            f"commands use one — so the command's arguments have a schema a caller can read."
        )
    return args_model.model_json_schema()
