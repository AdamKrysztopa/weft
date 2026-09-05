"""First-party command pack. Publishes the `Command` contract and `PermissionClass`.

Task **3.1**: "a pack registers a command exactly as it registers a retriever, and a command
that declares no permission class fails to register while its author is standing there."
`weft_command.contract`'s own module docstring carries the full reasoning for why this
distribution exists at all — in particular why `Command` lives here rather than in
`weft-kernel` (G1: the kernel names no capability) or `weft-cli` (a pack implementing a
contract must not depend on the driving adapter that calls it).

**Registers nothing, and declares no `weft.packs` entry point**, on `weft_prompts`'s
own precedent (see that distribution's module docstring for the identical reasoning): fitness
function 2 requires every distribution declaring that entry point to be active *and
contributing*, and every first-party command belongs to the pack whose behaviour it exposes —
none of which is this one's to own. `weft_cli.commands` carries every built-in command since
task 3.2, registered through `weft-cli`'s own entry point (see that module's docstring for why
`weft-cli` is the owner rather than a twelfth distribution); a third party's first
plugin-contributed `Command` adds the entry-point line to *its own* `pyproject.toml` in the same
commit it registers, exactly as `weft-retrieve` did at task 2.13.

There is therefore no `Settings` model and no `register` function here — a pack declaring no
entry point is never handed either, and declaring them unused would be two more things to keep
true. `weft_generate` and `weft_prompts` take the same shape for the same
reason.

**Task 6.20 (G13) adds `ExitCode` and `Rendered` to this namespace** — `weft_command.render`'s
own module docstring carries the reasoning in full: a renderer a third-party pack registers
through `weft_kernel.discovery.PackRegistrar.add_renderer` has to answer with a `Rendered`
carrying an `ExitCode`, and a pack implementing `Command` must not depend on `weft-cli`, the
driving adapter, for the vocabulary its own renderer speaks.
"""

from weft_command.contract import COMMAND_CONTRACT_VERSION, Command, CommandResult
from weft_command.permission import PermissionClass
from weft_command.render import ExitCode, Rendered

__all__ = [
    "COMMAND_CONTRACT_VERSION",
    "Command",
    "CommandResult",
    "ExitCode",
    "PermissionClass",
    "Rendered",
]
