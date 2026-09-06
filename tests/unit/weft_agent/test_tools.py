"""The agent's tool catalogue is derived, never written — ledger task **7.2a**.

`docs/05-grilling-sessions.md` → G12, settled 2026-09-06: a caller with no TTY cannot reach
`overwrite` or `destroy`, and its autonomous reach is `read`, `write` and `network`. That is a
**ceiling**, and a ceiling enforced by a list somebody maintains is a ceiling that holds until
somebody forgets. This task makes it mechanical.

**The falsifiable claim, and it is the whole point of the task.** A third party ships a
`destroy`-class command tomorrow; it is out of the agent's reach *that day*, with nobody editing
`weft-agent` and nobody adding a name to anything. A deny-list cannot make that claim — it is
exactly the shape that is one forgotten entry away from being wrong, and `docs/lessons.md` `L8.25`
is what a hand-kept scope list does when the tree moves under it. The filter is the mechanism, which
is the same *derived, never declared* discipline G4 already holds capability to.

**Two commands are excluded by name, and each carries its reason in code rather than in a waiver.**

- **`config set`** is `write`-class and writes `weft.toml` — *including `[permissions]`*. An agent
  that can set `destroy = "allow"` has climbed its own ceiling, and no class-based filter can see
  that, because the class is right and the consequence is one level up. This is the single row
  where G12's third position — *the class is the wrong unit for a non-human caller* — turns out to
  be correct, and it is correct about exactly one command out of nineteen.
- **`init`** scaffolds a project. An agent should not scaffold the project it is running inside.

A named exclusion with a stated reason is not a waiver: a waiver says *this rule should apply here
and does not*, and these two say *this rule does not decide this case*. They are pinned, and the
test below asserts each still names a live command, so an exclusion cannot outlive the thing it
excludes.

**The catalogue is a third rendering of one walk.** `weft_cli.cli.build_parser` renders the
registry to a terminal grammar and `weft_cli.command_table` renders it to Markdown; this renders it
to tool schemas. The walk itself moves to `weft_command.catalogue` in this task, because
`weft_agent` must not import the driving adapter and the alternative was a second walk — which is
how a fourth hand-written list gets written. Same argument as task 7.0's: what reads a `Command`'s
own declarations belongs with the contract that publishes them.
"""

from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel

from weft_command.contract import Command, CommandResult
from weft_command.permission import PermissionClass
from weft_kernel.context import Context
from weft_kernel.payload import Outcome, Produced
from weft_kernel.registry import Registry


class _Args(BaseModel):
    target: str


class _Result(CommandResult):
    done: bool


class _Stranger:
    """A command a third party ships. It declares the two mandatory things and nothing else."""

    version: ClassVar[str] = "2.0.0"
    args_model: ClassVar[type[BaseModel]] = _Args
    result_model: ClassVar[type[CommandResult]] = _Result
    required_declarations: ClassVar[tuple[str, ...]] = ("permission_class", "help")
    permission_class: ClassVar[PermissionClass] = PermissionClass.READ
    help: ClassVar[str] = "look at something"

    def __init__(self, config: object = None) -> None:
        del config

    async def run(self, args: BaseModel, ctx: Context) -> Outcome[CommandResult]:
        del args, ctx
        return Produced(value=_Result(done=True))


class _StrangerWipe(_Stranger):
    permission_class: ClassVar[PermissionClass] = PermissionClass.DESTROY
    help: ClassVar[str] = "wipe something"


def _registry_with(**commands: type[_Stranger]) -> Registry:
    registry = Registry()
    for name, factory in commands.items():
        registry.add(Command, name.replace("_", " "), factory, distribution="stranger-pack")
    return registry


def test_a_strangers_destroy_command_is_out_of_reach_the_day_it_ships() -> None:
    """The claim this task exists to make, and it is checked against a pack nobody has seen.

    Nothing in `weft-agent` names this command, and nothing has to: it is absent because of what it
    declared, which is the difference between a ceiling and a list.
    """
    # Arrange
    from weft_agent.tools import tool_catalogue

    registry = _registry_with(look=_Stranger, wipe=_StrangerWipe)

    # Act
    catalogue = tool_catalogue(registry)

    # Assert
    assert "look" in catalogue
    assert "wipe" not in catalogue, (
        "a destroy-class command a third party shipped is reachable by the agent — the filter is "
        "not deriving reach from permission_class (grilling session G12)"
    )


def test_the_reachable_classes_are_exactly_the_ceiling_g12_settled() -> None:
    # Membership, not a count: `03` → *Permissions* states a set, and asserting a number here
    # would make the next class added to the vocabulary fail a test about something else.
    from weft_agent.tools import REACHABLE_CLASSES

    assert (
        frozenset({PermissionClass.READ, PermissionClass.WRITE, PermissionClass.NETWORK})
        == REACHABLE_CLASSES
    )


def test_every_named_exclusion_still_names_a_live_command() -> None:
    """The two-way ratchet. An exclusion that no longer matches anything is one nobody can see has
    stopped applying — the same defect a stale waiver has, and the reason both are checked."""
    from weft_agent.tools import EXCLUDED_BY_NAME
    from weft_cli.contract_reference import discover_for_reference

    registered = set(discover_for_reference().names_for(Command))
    stale = sorted(name for name in EXCLUDED_BY_NAME if name not in registered)

    assert not stale, (
        f"these names are excluded from the agent's tools and no longer name a registered "
        f"command: {stale}. An exclusion outliving what it excludes is invisible until somebody "
        f"registers that name again."
    )


def test_a_tool_describes_itself_from_the_commands_own_declarations() -> None:
    # Derived, not retyped: the description is the command's mandatory `help` and the parameters
    # are its own args model's JSON schema, so a command that changes its arguments changes its
    # tool the same day, with nobody editing the agent.
    from weft_agent.tools import tool_catalogue

    catalogue = tool_catalogue(_registry_with(look=_Stranger))
    tool = catalogue["look"]

    assert tool.description == "look at something"
    assert tool.parameters == _Args.model_json_schema()


def test_the_live_catalogue_holds_the_commands_g12_reaches_and_no_others() -> None:
    """Against the registry the CLI actually builds, so this is a fact about what ships.

    Asserted as three memberships and two absences rather than as a count of fifteen: a count would
    fail the day a command is added, which is not a defect, while these five say what the ceiling
    means. `weft delete` and `weft reconcile` are the tree's only `destroy`-class commands.
    """
    from weft_agent.tools import tool_catalogue
    from weft_cli.contract_reference import discover_for_reference

    catalogue = tool_catalogue(discover_for_reference())

    assert {"ask", "index", "pipeline list"} <= set(catalogue)
    assert "delete" not in catalogue, "a destroy-class command is in the agent's reach"
    assert "reconcile" not in catalogue, "a destroy-class command is in the agent's reach"
    assert "config set" not in catalogue, (
        "the agent can write [permissions] in weft.toml, which is climbing its own ceiling"
    )


def test_the_check_can_actually_fail() -> None:
    # `docs/lessons.md` L5.6 — planted through the same predicate, so a green here cannot mean the
    # filter stopped looking. A read-class stranger is admitted and a destroy-class one is not,
    # from the identical registry shape.
    from weft_agent.tools import tool_catalogue

    admitted = tool_catalogue(_registry_with(thing=_Stranger))
    refused = tool_catalogue(_registry_with(thing=_StrangerWipe))

    assert set(admitted) == {"thing"}
    assert set(refused) == set(), "the filter admits a destroy-class command"
