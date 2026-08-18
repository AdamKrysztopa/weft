"""`PermissionClass` and `CliCommand` — every command declares a class, and there is no default.

`docs/03-cli.md` → *Permissions*: "A plugin-contributed command must declare
its class, and there is no default (G3). The class is a `ClassVar` on the
`Command` contract, read at registration... a command that declares none
fails to register, loudly, while its author is standing right there." The
`Command` *contract* — a pack registering a command exactly as it registers a
retriever — is Phase 3's (`docs/build-ledger.md` task 3.1), gated on **G8**.
`docs/06-phase-0-build.md` step 9 asks for the property one phase early,
scoped to the five commands Phase 0 actually ships: "Permission classes
declared on every command, no default." This module is that property, applied
to `weft-cli`'s own built-in command table rather than to a pack-registration
seam that does not exist yet — there is no registry to register a `Command`
into in Phase 0 (`Command` names a capability the kernel does not own), so
`CliCommand` is `weft_cli`'s own, and `weft_cli.cli.COMMANDS` is where every
built-in command is declared.

**"No default" is a language-level fact, not a runtime check.** `CliCommand`
is `kw_only`, and `permission` carries no default value — omitting it at a
call site is a `TypeError` naming the missing keyword, raised while
`weft_cli.cli` builds `COMMANDS` at import time, which is as loud and as
early as "fails to register" can mean for a table built once, by hand, at
class-definition time. This is the same idiom `weft_kernel.runner.StageSpec`
and `weft_kernel.registry.RegistryEntry` already use for a required field with
no runtime guard to write.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import argparse

    from weft_cli.exit_codes import ExitCode
    from weft_cli.registry_bootstrap import Dependencies


class PermissionClass(StrEnum):
    """The five classes `docs/03-cli.md` → *Permissions* names. `Enum`, never `Literal[...]`.

    Phase 0 ships no `overwrite` or `destroy` command — `index` upserts by
    content-addressed id (`weft_store.pgvector_store`'s `ON CONFLICT DO
    UPDATE`), which is `write`, not `overwrite`: nothing here replaces or
    destroys a collection a caller did not just ask to add to. Both classes
    are declared anyway, because the vocabulary is fixed by `docs/03-cli.md`
    and a pack's future `Command` will need them.
    """

    READ = "read"
    WRITE = "write"
    OVERWRITE = "overwrite"
    DESTROY = "destroy"
    NETWORK = "network"


CommandHandler = Callable[["argparse.Namespace", "Dependencies"], Awaitable["ExitCode"]]


@dataclass(frozen=True, slots=True, kw_only=True)
class CliCommand:
    """One entry in `weft_cli.cli.COMMANDS`. `permission` carries no default — see the module
    docstring.
    """

    name: str
    help: str
    permission: PermissionClass
    needs_registry: bool
    handler: CommandHandler
