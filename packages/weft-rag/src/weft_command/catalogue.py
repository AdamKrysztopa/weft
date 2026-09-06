"""The one walk of the `Command` registry — every renderer built on top of `Registry.names_for`
reads it from here. Moved out of `weft_cli.command_table` at task **7.2a**.

`weft_cli.cli.build_parser` renders the registry to a terminal grammar,
`weft_cli.command_table` renders it to the Markdown table `manual/user-manual.md` embeds, and
`weft_agent.tools` renders it to the agent's tool catalogue. All three read the identical facts
off the identical registered factory — `help`, `permission_class`, and (for the agent) the
`args_model` — so the walk that reads them belongs beside the contract that publishes them,
`weft_command.contract.Command`, rather than inside any one renderer. `weft_agent` must not
import `weft_cli` — the driving adapter — so a walk that lived only in `weft_cli.command_table`
would force a second, hand-written copy the day the agent needed it; this move is what keeps
there being exactly one.

`weft_cli.command_table` re-exports `PublishedCommand`, `command_entries` and
`CommandNotDescribableError` from here unchanged, so nothing that already imports them from that
module has to change.
"""

from __future__ import annotations

from dataclasses import dataclass

from weft_command.contract import Command
from weft_command.permission import PermissionClass
from weft_kernel.errors import WeftError
from weft_kernel.registry import Registry, unwrap_factory


class CommandNotDescribableError(WeftError):
    """A registered `Command` this generator cannot describe — see the module docstring's
    paragraph on why this exists even though `Command.required_declarations` already makes it
    unreachable in practice.
    """


@dataclass(frozen=True, slots=True)
class PublishedCommand:
    """One registered `Command`, exactly as `weft --help` would already show it.

    `name` is the registered name in full — `"plugins doctor"`, not just `"doctor"` — the same
    string `weft_cli.cli.build_parser` reads off `Registry.names_for(Command)` to build the
    subcommand tree; `weft {name}` is the invocation.
    """

    name: str
    distribution: str
    permission_class: PermissionClass
    help: str


def command_entries(registry: Registry) -> tuple[PublishedCommand, ...]:
    """Every registered `Command`, sorted by name for a stable, diffable render.

    Walks `registry.names_for(Command)` — `weft_cli.cli.build_parser`'s own source of the
    subcommand tree — never a hand-written list of the built-ins, so a plugin's own command is
    walked identically to a first-party one.
    """
    entries: list[PublishedCommand] = []
    for name in sorted(registry.names_for(Command)):
        entry = registry.entry(Command, name)
        factory = unwrap_factory(entry.factory)
        entries.append(
            PublishedCommand(
                name=name,
                distribution=entry.distribution,
                permission_class=_permission_class_of(factory, name),
                help=_help_of(factory, name),
            )
        )
    return tuple(entries)


def _help_of(factory: object, name: str) -> str:
    """`factory.help`, or a loud, specific failure — see `CommandNotDescribableError`."""
    help_text = getattr(factory, "help", None)
    if not isinstance(help_text, str):
        raise CommandNotDescribableError(
            f"'{name}' carries no `help` attribute. Every registered Command must declare "
            "one — weft_command.contract.Command.required_declarations names it mandatory — "
            "and the command-table generator refuses to invent a placeholder for one that "
            "does not exist."
        )
    return help_text


def _permission_class_of(factory: object, name: str) -> PermissionClass:
    """`factory.permission_class`, or a loud, specific failure — see
    `CommandNotDescribableError`."""
    permission_class = getattr(factory, "permission_class", None)
    if not isinstance(permission_class, PermissionClass):
        raise CommandNotDescribableError(
            f"'{name}' carries no `permission_class` attribute. Every registered Command must "
            "declare one — weft_command.contract.Command.required_declarations names it "
            "mandatory — and the command-table generator refuses to invent a placeholder for "
            "one that does not exist."
        )
    return permission_class
