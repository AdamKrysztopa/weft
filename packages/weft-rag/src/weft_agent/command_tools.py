"""The agent reaches Weft only through the published command surface — ledger task **7.3**.

`docs/03-cli.md` → *Two modes, one implementation*, and `docs/internal/05-grilling-sessions.md` →
G12. See `tests/unit/weft_agent/test_command_tools.py`'s own module docstring for the three
properties this module makes true; restated here only as pointers to where each lives:

*(a)* `CommandTool.call` reaches a `Command` only through `weft_command.invocation.invoke` — never
`instance.run(...)` directly — so the permission gate task 7.0 moved onto that seam applies to the
agent exactly as it applies to `weft_cli`. `tests/unit/weft_agent/test_command_tools.py::
test_the_tool_runs_a_command_only_through_the_seam` asserts this over the module's own source.

*(b)* The observation returned to the model is built from the typed `Outcome[CommandResult]`
`invoke` returns, never from `weft_command.render.Rendered` — this module imports nothing from
`weft_cli` at all, per `weft_agent`'s own pack-boundary rule (task 7.1).

*(c)* `RefusingConsent` is this pack's answer to `weft_command.invocation.Consent` — G12's
settled ceiling ("nothing but a TTY counts as consent") expressed as code: every
`overwrite`/`destroy`-class command is refused, and the refusal is returned as an observation so
the model can read it and choose otherwise, never raised out of the loop.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Final, cast

from pydantic import BaseModel

from weft_agent.tools import tool_catalogue
from weft_command.catalogue import help_of
from weft_command.contract import Command, CommandResult
from weft_command.invocation import invoke
from weft_command.permission import PermissionClass
from weft_kernel.context import Context
from weft_kernel.errors import WeftError
from weft_kernel.payload import NothingToProduce, Outcome, Produced
from weft_kernel.registry import Registry, unwrap_factory

#: G12's ceiling, read the other way round from `weft_agent.tools.REACHABLE_CLASSES`: these are
#: the two classes nothing but a TTY may answer for, enumerated explicitly (rather than as
#: "everything but read/write/network") so a sixth `PermissionClass` member is permitted by
#: default and a reviewer has to notice it was never added here — the population this module
#: actually decides over, per `docs/internal/lessons.md` `L6.4`.
_REFUSED_CLASSES: Final[frozenset[PermissionClass]] = frozenset(
    {PermissionClass.OVERWRITE, PermissionClass.DESTROY}
)


class ConsentRefusedError(WeftError):
    """A `PermissionClass.OVERWRITE`/`DESTROY` command, refused because nothing here is a TTY.

    Raised by `RefusingConsent.decide` and caught by `CommandTool.call`, never allowed to escape
    the loop — see this module's own docstring, property *(c)*.
    """


class RefusingConsent:
    """`weft_command.invocation.Consent`, answered the way G12 settled it for an agent.

    `permission_class` is read off `instance` with `getattr`, defensively — the identical
    discipline `weft_cli.confirm.gate` uses for the same attribute, and for the same reason:
    `permission_class` is a `Command.required_declarations` name, never a required `isinstance`
    member, so nothing guarantees a stranger's `Command` carries it beyond registration having
    already refused it if it did not.
    """

    async def decide(self, *, command_name: str, instance: object, args: BaseModel) -> None:
        del args
        permission_class = getattr(instance, "permission_class", None)
        if permission_class in _REFUSED_CLASSES:
            refused = cast(PermissionClass, permission_class)
            raise ConsentRefusedError(
                f"'{command_name}' is a {refused.value}-class command. Consent cannot be given "
                "without a TTY, and nothing in this run is one, so it is refused."
            )


def _observation_of(outcome: Outcome[CommandResult]) -> str:
    """The typed `Outcome` a `Command` produced, turned into the string an `AgentTool` returns.

    Never built from `Rendered` — see this module's own docstring, property *(b)*. A `Produced`
    serialises its own value's fields; `NothingToProduce`/`Failed` carry only a `reason`, which is
    exactly what an agent needs to decide what to try next.
    """
    if isinstance(outcome, Produced):
        return json.dumps(outcome.value.model_dump(mode="json"))
    if isinstance(outcome, NothingToProduce):
        return f"nothing to produce: {outcome.reason}"
    # `Failed` by elimination, and **the type checker is what says so** — `pyright` narrows
    # `Outcome` to it here and rejects a further `isinstance` as unnecessary. The first draft of
    # this function asserted the same fact instead; an `assert` is stripped under `-O` and would
    # have left the loop a bare `None` where it expects a string, while proving nothing a build
    # was not already proving. If `weft-kernel` ever grows a fourth `Outcome` member, this line
    # fails the gate rather than silently mis-reading one.
    return f"command failed: {outcome.reason}"


class CommandTool:
    """One registered `Command`, offered to the agent's loop as an `AgentTool`.

    Constructed directly against a `Registry` and a registered name, deliberately independent of
    `weft_agent.tools.tool_catalogue`'s own filtering — `command_tools` below is what wires the
    two together for the ordinary case, but a `CommandTool` built for a `destroy`-class command
    the catalogue would never offer must still refuse it correctly, which is exactly what
    `tests/unit/weft_agent/test_command_tools.py::
    test_a_destroy_class_command_is_refused_even_if_a_tool_exists_for_it` builds to prove the two
    halves — catalogue and consent — fail independently.
    """

    def __init__(self, *, registry: Registry, command_name: str) -> None:
        self._registry = registry
        self._command_name = command_name
        entry = registry.entry(Command, command_name)
        factory = unwrap_factory(entry.factory)
        self.description = help_of(factory, command_name)

    async def call(self, arguments: Mapping[str, object], ctx: Context) -> str:
        """Build this command's `args_model` from `arguments`, then run it through `invoke`.

        Never calls `instance.run(...)` — see this module's own docstring, property *(a)*, and
        `test_the_tool_runs_a_command_only_through_the_seam`, which asserts this over the
        module's source rather than over one call at runtime. `ConsentRefusedError` and any
        other `WeftError` the command itself raises are caught here and returned as the
        observation, per this pack's own reliability decision (`weft_agent.loop`'s own
        docstring): a tool returns a string, and the model reads the refusal on its next turn
        rather than the run ending underneath it. `CancelledError` is not caught and propagates
        untouched.
        """
        entry = self._registry.entry(Command, self._command_name)
        instance = cast(Command, entry.factory(None))
        args_instance = instance.args_model(**dict(arguments))

        try:
            outcome = await invoke(
                command_name=self._command_name,
                instance=instance,
                args=args_instance,
                ctx=ctx,
                consent=RefusingConsent(),
                distribution=entry.distribution,
            )
        except ConsentRefusedError as error:
            return str(error)
        except WeftError as error:
            return str(error)

        return _observation_of(outcome)


def command_tools(registry: Registry) -> Mapping[str, CommandTool]:
    """One `CommandTool` per entry `weft_agent.tools.tool_catalogue` offers, keyed identically.

    The catalogue already applied G12's ceiling (`REACHABLE_CLASSES`) and `EXCLUDED_BY_NAME`; this
    only wraps each surviving name in the tool the loop can actually call. `RefusingConsent` is
    the belt to the catalogue's braces — see this module's own docstring, property *(c)*, and
    `CommandTool`'s own docstring for why the two are tested independently.
    """
    return {
        name: CommandTool(registry=registry, command_name=name) for name in tool_catalogue(registry)
    }


__all__ = ["CommandTool", "ConsentRefusedError", "RefusingConsent", "command_tools"]
