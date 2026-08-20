"""A stranger's `Command` pack — the independence proof, as an artifact.

Fitness function 9's shape, applied to `weft_command.contract.Command` for the first time:
a pack that lives *outside* the `weft` repository's workspace, in its own directory with its
own `pyproject.toml`, installed the same way any third-party pack would be, registering one
plugin through the same `weft.packs` entry point every first-party pack uses — no shortcut, no
private import path. `weft`'s `tests/architecture/test_ff9c_every_contract_has_a_stranger.py`
installs this distribution into a throwaway environment built from wheels, with the `weft`
repository itself nowhere on `sys.path`, and confirms `"example-command"` registers under
`Command` there — clause (c)'s obligation for the contract task 3.2 activated by rewiring
`weft-cli`'s own built-ins onto it (task 3.1 shipped the contract with nothing registered yet,
so clause (c) had no subject; task 3.2's own registrations are what made this pack necessary,
and this is it).
"""

from pydantic import BaseModel, ConfigDict

from weft_command.contract import Command
from weft_example_command.greet import GreetCommand
from weft_kernel.discovery import PackRegistrar


class Settings(BaseModel):
    """This pack takes no settings — an empty model is still the required shape."""

    model_config = ConfigDict(frozen=True, extra="forbid")


def register(registrar: PackRegistrar, settings: Settings) -> None:
    """Register `GreetCommand` as `"greet"` for `Command` — the only plugin here."""
    del settings
    registrar.add(Command, "greet", GreetCommand)


__all__ = ["GreetCommand", "Settings", "register"]
