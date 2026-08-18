"""Unit tests for `weft_cli.permissions`.

Mirrors `packages/weft-cli/src/weft_cli/permissions.py`. Covers the one
property the module exists to hold: a `CliCommand` with a permission class
declared registers, and `permission` carries no default a call site could
omit and still succeed — no runtime guard to bypass, per `docs/03-cli.md` →
*Permissions*.
"""

import argparse
import dataclasses

from weft_cli.exit_codes import ExitCode
from weft_cli.permissions import CliCommand, PermissionClass
from weft_cli.registry_bootstrap import Dependencies


async def _noop_handler(
    args: argparse.Namespace, deps: Dependencies
) -> ExitCode:  # pragma: no cover - never called
    del args, deps
    return ExitCode.SUCCESS


def test_a_command_with_a_permission_class_registers() -> None:
    # Arrange / Act
    command = CliCommand(
        name="ask",
        help="retrieve and print matching passages",
        permission=PermissionClass.READ,
        needs_registry=True,
        handler=_noop_handler,
    )

    # Assert
    assert command.permission is PermissionClass.READ


def test_permission_carries_no_default_a_call_site_could_omit() -> None:
    # Arrange / Act — proving "no default" as the language-level fact the module docstring
    # claims, rather than attempting the omitted-argument call itself: that call is a static
    # type error under pyright strict (correctly so — the same error a hand-built COMMANDS
    # entry missing `permission` would get), so this is what actually exercises the guarantee.
    permission_field = next(
        field for field in dataclasses.fields(CliCommand) if field.name == "permission"
    )

    # Assert
    assert permission_field.default is dataclasses.MISSING
    assert permission_field.default_factory is dataclasses.MISSING


def test_permission_class_is_the_closed_vocabulary_docs_03_names() -> None:
    # Arrange / Act
    names = {member.value for member in PermissionClass}

    # Assert
    assert names == {"read", "write", "overwrite", "destroy", "network"}
