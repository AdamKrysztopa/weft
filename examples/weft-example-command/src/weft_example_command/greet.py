"""`GreetCommand` — a stranger's `Command`: one CLI-invoked action with no pipeline behind it.

Deliberately not a copy of one of `weft-cli`'s own five built-ins with different words — a
third party has no reason to reimplement `weft index` or `weft ask`, so this one is the
smallest genuinely different action the `Command` contract permits: it takes one argument,
touches no registry, no store and no network, and returns a typed greeting. It exists to prove
the same thing `weft_example_chunker.WordChunker` proves for `Chunker`: any implementation
satisfying `weft_command.contract.Command` structurally is usable, registered through the
identical `weft.packs` entry point `weft-cli`'s own built-ins use — no shortcut, no private
import path, `docs/03-cli.md` → *Plugin-contributed commands*' own worked example
(`weft graph build`) realised for a namespace that happens to be `greet` instead of `graph`.
"""

from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

from weft_command.contract import CommandResult
from weft_command.permission import PermissionClass
from weft_kernel.context import Context
from weft_kernel.payload import Outcome, Produced


class GreetArgs(BaseModel):
    """`weft greet <name>` — one required positional, the shape `weft_cli.argparse_gen`
    (task 3.2) turns into a positional argument because it carries no default.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(description="who to greet")


class GreetResult(CommandResult):
    """What `weft greet` produced — a typed result a renderer formats, never printed text
    (`docs/03-cli.md` → *Two modes, one implementation*), exactly as `weft-cli`'s own
    `IndexCommandResult` and friends are.
    """

    greeting: str


class GreetCommand:
    """Satisfies `weft_command.contract.Command` structurally — this class never imports it,
    the same path `docs/02-extension-model.md` describes for a third-party plugin.

    `permission_class` and `help` are both mandatory declarations
    (`Command.required_declarations`); omitting either refuses registration, loudly, at the
    point this pack's own `register()` runs — proven directly by
    `tests/test_greet.py::test_greet_without_a_declared_permission_class_is_refused`.
    """

    args_model: ClassVar[type[BaseModel]] = GreetArgs
    result_model: ClassVar[type[CommandResult]] = GreetResult
    permission_class: ClassVar[PermissionClass] = PermissionClass.READ
    help: ClassVar[str] = "greet somebody by name"

    def __init__(self, config: object = None) -> None:
        # No `with:`-style configuration this command takes — the registry's factory call
        # always passes something (`None` here, since nothing registers it with a `with:`
        # block), so the parameter exists to accept that, not to be used.
        del config

    async def run(self, args: BaseModel, ctx: Context) -> Outcome[CommandResult]:
        del ctx  # no service or locale this command needs
        assert isinstance(args, GreetArgs)
        return Produced(value=GreetResult(greeting=f"Hello, {args.name}!"))
