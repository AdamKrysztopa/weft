"""Unit tests for `weft_cli.permission_policy`.

Mirrors `packages/weft-rag/src/weft_cli/permission_policy.py`. Task **3.3**, design question 4:
"[permissions]" is read the same one-file-one-parse way `weft_cli.services.
service_selection_from_config` already reads `[services]`, and this file proves the same three
shapes that module's own test file proves for it — the happy path, the default with no block at
all, and the two refusals (an unknown key, a value that is not `"ask"`/`"allow"`).

**Repair, 2026-08-20** (`docs/build-ledger.md` 3.3's own dated paragraph carries the argument):
`test_an_unknown_permissions_key_carries_the_known_keys_as_a_typed_field` is the new failing-first
test for finding 1 of that review — `permission_policy_from_config`'s unknown-key refusal used to
raise a bare `WeftError` with the valid keys interpolated only into the message string, invisible
to fitness function 12's family walk. `UnknownConfigKeyError`
(`weft_cli.config_surface.py:105-115`) is the same-phase precedent this module now matches.
"""

from __future__ import annotations

import pytest

from weft_cli.permission_policy import (
    PermissionAction,
    PermissionPolicy,
    UnknownPermissionKeyError,
    permission_policy_from_config,
)
from weft_kernel.errors import WeftError


def test_no_document_at_all_defaults_both_classes_to_ask() -> None:
    # Act
    policy = permission_policy_from_config(None)

    # Assert — `docs/03-cli.md` -> Permissions' own table default for both classes.
    assert policy == PermissionPolicy()
    assert policy.overwrite is PermissionAction.ASK
    assert policy.destroy is PermissionAction.ASK


def test_a_document_with_no_permissions_block_defaults_both_classes_to_ask() -> None:
    # Arrange
    document: dict[str, object] = {"services": {"embed": "openai"}}

    # Act
    policy = permission_policy_from_config(document)

    # Assert
    assert policy.overwrite is PermissionAction.ASK
    assert policy.destroy is PermissionAction.ASK


def test_permissions_destroy_allow_overrides_the_built_in_default() -> None:
    # Arrange — the whole operation for an operator who wants `destroy`-class commands to run
    # unattended, e.g. in a CI job that already trusts its own pipeline.
    document: dict[str, object] = {"permissions": {"destroy": "allow"}}

    # Act
    policy = permission_policy_from_config(document)

    # Assert — the key not named keeps its own default.
    assert policy.destroy is PermissionAction.ALLOW
    assert policy.overwrite is PermissionAction.ASK


def test_an_unknown_permissions_key_is_refused_naming_the_keys_that_exist() -> None:
    # Arrange
    document: dict[str, object] = {"permissions": {"delete": "allow"}}

    # Act / Assert — silently ignoring it would let an operator believe they raised the bar
    # (or lowered it) on a class this block never actually reads.
    with pytest.raises(WeftError) as raised:
        permission_policy_from_config(document)
    assert "delete" in str(raised.value)
    assert "overwrite" in str(raised.value)
    assert "destroy" in str(raised.value)


def test_an_unknown_permissions_key_carries_the_known_keys_as_a_typed_field() -> None:
    # Arrange — finding 1 of the 2026-08-20 review: the message already named the keys, but only
    # inside the string, never as a typed field FF12's family walk can see.
    document: dict[str, object] = {"permissions": {"delete": "allow"}}

    # Act / Assert
    with pytest.raises(UnknownPermissionKeyError) as raised:
        permission_policy_from_config(document)
    assert raised.value.valid_options == ("destroy", "overwrite")


def test_a_permissions_value_that_is_not_ask_or_allow_is_refused() -> None:
    # Arrange
    document: dict[str, object] = {"permissions": {"destroy": "sometimes"}}

    # Act / Assert
    with pytest.raises(WeftError) as raised:
        permission_policy_from_config(document)
    assert "destroy" in str(raised.value)


def test_a_permissions_key_that_is_not_a_table_is_refused_the_way_services_is() -> None:
    # Arrange — the same shape `weft_cli.services.service_selection_from_config` refuses for
    # `[services]`: two readers of one file must not disagree about what a malformed block means.
    document: dict[str, object] = {"permissions": ["destroy"]}

    # Act / Assert
    with pytest.raises(WeftError) as raised:
        permission_policy_from_config(document)
    assert "[permissions]" in str(raised.value)
