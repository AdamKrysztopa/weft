"""Generates the command table `manual/user-manual.md` embeds — `docs/08-manuals.md` §1, §3
clause (b), task **3.9**.

`03` → *Plugin-contributed commands* already commits the CLI itself to this: "Core has no list
of commands to edit. The help text is generated from the registry, which means it cannot drift
from what is installed." `weft_cli.cli.build_parser` is that generation step — it walks
`registry.names_for(weft_command.contract.Command)` and reads each entry's `help` off its
registered factory to build `weft --help`'s own text. `08` §3's own words for the manual: "the
manual's command table is the same generation step, rendered to Markdown instead of a terminal."
This module is that second rendering — the same walk, a Markdown table instead of an
`argparse.ArgumentParser` — never a second, hand-typed list a plugin's command could be added to
without anyone noticing.

**Discovery is reused, not reimplemented.** `weft_cli.contract_reference.discover_for_reference`
already builds exactly the registry this needs: open by default (a generated document describes
what is installed, never a project's `[packs] allow` policy), with just enough `weft-store`
settings to let that pack's own `register()` validate without ever dialling a socket — see that
function's own docstring for why. A `Command` never touches a store directly, but discovery
registers every pack in the workspace in one pass, `weft-store` included, so the same placeholder
settings are needed here for the identical reason. Building a second, command-table-only
discovery helper would be two copies of one decision about what "installed" means for a generated
document.

**A registered command's `help` and `permission_class` are read defensively, and a command this
module cannot describe stops generation rather than being described wrongly** — the same
discipline `weft_cli.contract_reference.ContractNotDescribableError` holds for a contract. In
practice this can never fire: `weft_command.contract.Command.required_declarations` —
`("permission_class", "help")` — already refuses a plugin's own registration if either is
missing, before this module ever sees the name. `CommandNotDescribableError` exists anyway,
because reading them here with a bare `getattr(..., name)` would let a future relaxation of that
required-declarations check turn into a generator crash with no attribution, instead of a loud,
specific failure naming which command and which field.

**The table is spliced into `manual/user-manual.md`, never the whole file.** Unlike
`manual/contract-reference.md` — a document with no other job — the user manual is mostly
hand-written narrative (`08` §1: "how to derive a pipeline... the equivalent Python calls"), and
only its command reference is generated. `SECTION_BEGIN`/`SECTION_END` mark the region
`render_command_table`'s output owns; `spliced_manual` replaces exactly that region and leaves
every other byte — the prose above and below it — untouched, so a generator run can never
overwrite a sentence a person wrote.
"""

from __future__ import annotations

from collections.abc import Set as AbstractSet
from dataclasses import dataclass
from typing import Final

from weft_command.contract import Command
from weft_command.permission import PermissionClass
from weft_kernel.errors import WeftError
from weft_kernel.registry import Registry, unwrap_factory

#: The region `render_command_table`'s output owns inside `manual/user-manual.md` — see the
#: module docstring's closing paragraph. HTML comments so they render invisibly wherever the
#: file is viewed as Markdown, the same convention a generated README table uses elsewhere.
SECTION_BEGIN: Final[str] = "<!-- weft-cli:generated:command-table:begin -->"
SECTION_END: Final[str] = "<!-- weft-cli:generated:command-table:end -->"


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
    subcommand tree — never a hand-written list of the five (now thirteen) built-ins, so a
    plugin's own command is walked identically to a first-party one.
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


def missing_command_names(
    *, registered: frozenset[str], walked: AbstractSet[str], waived: frozenset[str]
) -> frozenset[str]:
    """Every command name `registered` (a real `Registry`'s own report) that `walked` lacks.

    `weft_cli.contract_reference.missing_from_walked_set`'s own shape, applied to command names
    (plain strings, keyed by the registration itself) rather than contract classes (keyed by
    `__qualname__`) — kept as a sibling function rather than generalised over both, because a
    contract and a command name are identified differently and a single parameterised version
    would need a callback just to recover what this one gets from `in` alone. A pure function,
    kept separate from `command_entries` so `08` §3's floor has something to call that is not
    the same code path it is checking.
    """
    return frozenset(name for name in registered if name not in waived and name not in walked)


def render_command_table(commands: tuple[PublishedCommand, ...]) -> str:
    """The Markdown table `SECTION_BEGIN`/`SECTION_END` wrap in `manual/user-manual.md`.

    One row per command: the invocation, its permission class, the distribution that
    registered it, and its own `help` text — the identical four facts `weft --help`'s
    generated grammar already carries (`weft_cli.cli._add_command_level` reads `help` off the
    same unwrapped factory this module does), rendered as a table instead of an
    `argparse.ArgumentParser`. A literal `|` in a help string is escaped so it cannot be
    mistaken for a table delimiter — no help text in this workspace carries one today, but a
    plugin author's is unbounded by construction, exactly as `weft_cli.cli._report_unexpected`'s
    own docstring says about exception types.

    Not passed through `ruff format`, unlike `weft_cli.contract_reference.
    render_contract_reference`: that function's own docstring explains the formatter matters
    because its output embeds fenced Python; a Markdown table has no fenced code for `ruff
    format` to rewrap, so running it here would cost a subprocess for a no-op.
    """
    header = "| Command | Permission | Registered by | Summary |\n|---|---|---|---|\n"
    rows = "\n".join(
        f"| `weft {command.name}` | `{command.permission_class.value}` | "
        f"`{command.distribution}` | {command.help.replace('|', '\\|')} |"
        for command in commands
    )
    return f"{header}{rows}\n"


def spliced_manual(markdown: str, table: str) -> str:
    """`markdown` with the region between `SECTION_BEGIN`/`SECTION_END` replaced by `table`.

    Used by both `scripts/generate_command_table.py` (to write) and
    `tests/docs/test_generated_docs.py` (to check without writing) — one splice
    implementation, so the two cannot disagree about where the generated region starts and ends.
    """
    start = markdown.index(SECTION_BEGIN) + len(SECTION_BEGIN) + 1
    end = markdown.index(SECTION_END, start)
    return markdown[:start] + table + markdown[end:]
