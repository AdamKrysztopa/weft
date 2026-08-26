"""`ExitCode` and `Rendered` — a renderer's own vocabulary, published beside the `Command`
contract that produces the result a renderer formats.

Task **6.20**, G13's third repair (`docs/03-cli.md` → *Plugin-contributed commands*): "a
result type nobody outside the CLI can format is only half a contract." Both classes moved
here from `weft_cli` — `ExitCode` out of `weft_cli.exit_codes`, `Rendered` out of
`weft_cli.render` — because a renderer registered by a third-party pack (`weft_kernel.
discovery.PackRegistrar.add_renderer`) has to build one of these to answer with, and a pack
implementing `Command` must not depend on `weft-cli`, the driving adapter that calls it, for
the vocabulary its own renderer speaks — the identical reasoning `weft_command.contract`'s
own module docstring already gives for why `Command` itself lives here rather than in
`weft-cli`.

**`ExitCode` travels with `Rendered` rather than staying behind, and that is a deliberate
choice, not a convenience.** A renderer that cannot say the run failed is a renderer a
built-in could not have used: `weft delete` and `weft index` both compute their own exit
code from their own result's fields (a partial deletion, or an index run with failures, is
success at the process level and failure at the operation level — see `weft_cli.render`'s
own `_render_delete`/`_render_index`), so a third-party renderer needs the identical
five-value vocabulary to state the same kind of fact about its own result. `weft_command.
permission.PermissionClass` is the standing precedent for a `docs/03-cli.md` concept living
in this pack rather than in `weft-cli`: this pack already publishes a vocabulary that
document defines, because the contract is unusable without it.

**`CommandResult` still names no exit code — what moved is the *renderer's* vocabulary, not
the result's.** `weft_cli.render`'s retired docstring argued exactly this, and the argument
still holds unchanged now that `ExitCode` and `Rendered` live here instead: `CommandResult`
is capability-agnostic, and `IndexCommandResult.summary.failed > 0` still has to become exit
code `1` somewhere — that "somewhere" is still whichever renderer a pack registers through
`PackRegistrar.add_renderer`, computed from the typed fields a command actually returned,
never smuggled into the result itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


class ExitCode(IntEnum):
    """`docs/03-cli.md` → *Output*: "0 success, 1 operation failed, 2 bad usage, 3 refused for
    permissions, 4 pipeline failed to resolve." `2` is never assigned by a renderer — `argparse`
    itself calls `sys.exit(2)` on a usage error, before any command runs, so nothing downstream
    of a `Command`'s own `run` ever needs to produce it.
    """

    SUCCESS = 0
    OPERATION_FAILED = 1
    BAD_USAGE = 2
    POLICY_REFUSED = 3
    RESOLUTION_FAILED = 4


@dataclass(frozen=True, slots=True)
class Rendered:
    """What a renderer answers with — stdout, stderr, and the exit code the process should
    report. `None` on either stream means nothing prints on it.

    Every renderer registered through `weft_kernel.discovery.PackRegistrar.add_renderer`
    returns one of these, whether it is one of `weft_cli`'s own eighteen built-in renderers
    or a third party's — a `Rendered` built by a stranger's pack is indistinguishable from
    one `weft_cli.render` built itself, which is the property task 6.20 exists to make true.
    """

    stdout: str | None
    stderr: str | None
    exit_code: ExitCode
