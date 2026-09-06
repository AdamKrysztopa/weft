"""The command invocation seam — ledger task **7.0** — where consent is a required argument.

`docs/05-grilling-sessions.md` → G12, settled 2026-09-06, and `docs/03-cli.md` → *Permissions* →
*What a permission class means when the caller is never a TTY*. The gate G12 depends on
(`weft_cli.confirm.gate`) was called from exactly one place — inside `weft_cli.cli.run_command`,
which takes an `argparse.Namespace` and returns a `Rendered`. The typed result task 7.3 requires
comes from `Command.run`, and **nothing gated `Command.run`**. So the ceiling G12 settled was
prose on the exact path Phase 7 is told to take: the *control that looks like enforcement and is
not* which `02` §2 refuses.

**The repair is not "call the gate from a second place".** That reproduces the defect one caller
later, and `docs/lessons.md` `L8.31` is the general form: placing a concern at *"the one place
that calls X"* is a bet there will never be a second caller, and the bet's expiry is written down
nowhere. What this module makes true is that **the invocation seam itself takes the consent
decision as a required argument**, so a caller that has not made one cannot construct the call at
all. That is the same shape `CLAUDE.md` already requires of every other cross-cutting concern:
attached at the seam, never left to a rule an author must remember.

**`Consent` is a Protocol rather than a policy object, and that keeps `weft-command` clean.**
This module must not learn `weft.toml`, `PermissionPolicy` or what a TTY is — those belong to the
driving adapter, per `03`'s governing rule. It asks one question and takes whatever answer it is
given: `weft-cli` answers with the TTY prompt it already ships, and an agent answers *"refuse
every ask-class operation"*. Two callers, one seam, and neither can skip it.

`invoke` asks `consent.decide(...)` for every command, regardless of `permission_class` — the
seam does not filter by class itself, because deciding which classes are interesting is the
`Consent` implementation's own job, kept in `03`'s table rather than duplicated here. The command
runs through `weft_kernel.seam.wrap`, exactly as `weft_cli.cli.run_command` already runs it, so
spans, error attribution and transient stripping attach identically on both the CLI path and the
library path — never hand-rolled here.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel

from weft_command.contract import Command, CommandResult
from weft_kernel.context import Context
from weft_kernel.payload import Outcome
from weft_kernel.seam import wrap


@runtime_checkable
class Consent(Protocol):
    """One question, answered by whatever caller drives a command.

    `instance` is typed `object`, not `Command`, for the identical reason `weft_cli.confirm.gate`
    gives in its own docstring: everything an implementation reads off it goes through
    `getattr`, so demanding the full Protocol would force a test double to satisfy a shape
    nothing calls. Returning `None` permits the run; raising refuses it, and `invoke` never runs
    the command once this raises.
    """

    async def decide(self, *, command_name: str, instance: object, args: BaseModel) -> None: ...


async def invoke(
    *,
    command_name: str,
    instance: Command,
    args: BaseModel,
    ctx: Context,
    consent: Consent,
    distribution: str,
) -> Outcome[CommandResult]:
    """Ask `consent` first, then run `instance` through the kernel seam.

    `consent` has no default — a caller that has not decided anything cannot construct this
    call, which is the property `docs/lessons.md` `L8.24` names: a defaulted parameter with one
    caller is a narrowing wearing a default. Consent is asked for every command, whatever its
    `permission_class`; this function never inspects that attribute itself.
    """
    await consent.decide(command_name=command_name, instance=instance, args=args)

    sealed_run = wrap(
        instance.run,
        distribution=distribution,
        contract="Command",
        plugin=command_name,
        stage=f"command:{command_name}",
        guard_blocking_calls=False,
    )
    return await sealed_run(args, ctx)
