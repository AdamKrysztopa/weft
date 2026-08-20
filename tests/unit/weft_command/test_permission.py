"""Unit tests for `weft_command.permission`.

Mirrors `packages/weft-command/src/weft_command/permission.py`. Covers the one property
that matters: `PermissionClass` is exactly the five-member, `Enum`-not-`Literal` vocabulary
`docs/03-cli.md` → *Permissions* fixes, unchanged by task 3.1 moving it out of
`weft_cli.permissions`.
"""

from weft_command.permission import PermissionClass


def test_permission_class_is_the_closed_vocabulary_docs_03_names() -> None:
    # Arrange / Act
    names = {member.value for member in PermissionClass}

    # Assert
    assert names == {"read", "write", "overwrite", "destroy", "network"}


def test_permission_class_members_are_strings_not_a_bare_literal() -> None:
    # Arrange / Act / Assert — CLAUDE.md: "Enum for string constants, never Literal[...]."
    assert PermissionClass.READ == "read"
    assert isinstance(PermissionClass.READ, str)
