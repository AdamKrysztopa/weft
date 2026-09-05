"""`PermissionClass` — the five-member, closed vocabulary `docs/03-cli.md` → *Permissions* fixes.

Task **3.1** moves this out of `weft_cli.permissions`, where it lived as a stand-in until the
`Command` contract itself existed (`weft_cli.permissions`'s own former docstring: "the `Command`
*contract* ... is Phase 3's ... gated on G8"). G8 settled 2026-08-18 and this distribution is
that contract's home — see `weft_command.contract`'s module docstring for why `Command` lives
here rather than in `weft-kernel` or `weft-cli`. `PermissionClass` moves with it because a
permission class is meaningless without the contract that reads it: `Command.required_declarations`
names `permission_class` as mandatory (`weft_kernel.registry`'s generalised check, task 3.1), and
the vocabulary that field's values are drawn from belongs beside the contract, not beside one
particular renderer of it.

**`weft_cli.permissions` — the re-export this class briefly had — is gone as of task 3.2.** It
existed only to keep `weft_cli.cli.COMMANDS`'s hand-written table importing one name from two
places during the 3.1→3.2 transition; 3.2 deleted `COMMANDS` itself (every built-in command is
now a `weft_command.contract.Command` plugin in `weft_cli.commands`, which imports
`PermissionClass` directly from here, on the same footing any third-party command pack does), so
the stand-in had no remaining caller and staying would have been the exact kind of drift-prone
duplicate name this contract's own placement exists to avoid.

`Enum`, never `Literal[...]`, per CLAUDE.md. The five members are fixed by `docs/03-cli.md`'s own
table — `read`/`write` default to allow, `overwrite`/`destroy` default to ask, `network` defaults
to allow but stays configurable — and defaults are policy a renderer or `weft.toml` enforces,
not a fact this enum carries; see `docs/03-cli.md` → *Permissions* for the table in full.
"""

from enum import StrEnum


class PermissionClass(StrEnum):
    """The five classes `docs/03-cli.md` → *Permissions* names.

    **No default anywhere a `Command` implementation reads this from.** A plugin-contributed
    command must declare exactly one of these — `Command.required_declarations` makes silence a
    registration refusal, never a fallback to `read` — because `read` silently under-protects and
    `destroy` trains an operator to pass `--yes` reflexively, disarming the whole table
    (`docs/03-cli.md` → *Permissions*).
    """

    READ = "read"
    WRITE = "write"
    OVERWRITE = "overwrite"
    DESTROY = "destroy"
    NETWORK = "network"
