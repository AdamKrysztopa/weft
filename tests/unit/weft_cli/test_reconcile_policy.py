"""Unit tests for `weft_cli.reconcile_policy`.

Mirrors `packages/weft-cli/src/weft_cli/reconcile_policy.py`. Task **5.1c**: "`weft.toml` sets
a personal default" for `weft reconcile`'s own bare `--mode` — this file proves the same three
shapes `weft_cli.permission_policy`'s own test file proves for `[permissions]`: the happy path,
the default with no block at all, and the two refusals (an unknown key, an illegal value).
"""

from __future__ import annotations

import pytest

from weft_cli.reconcile_policy import (
    ReconcilePolicy,
    UnknownReconcileKeyError,
    reconcile_policy_from_config,
)
from weft_kernel.errors import WeftError
from weft_store import ReconcileMode


def test_no_document_at_all_defaults_to_full() -> None:
    # Act
    policy = reconcile_policy_from_config(None)

    # Assert — unchanged from `weft reconcile`'s own pre-5.1c hardcoded default.
    assert policy == ReconcilePolicy()
    assert policy.mode is ReconcileMode.FULL


def test_a_document_with_no_reconcile_block_defaults_to_full() -> None:
    # Arrange
    document: dict[str, object] = {"services": {"embed": "openai"}}

    # Act
    policy = reconcile_policy_from_config(document)

    # Assert
    assert policy.mode is ReconcileMode.FULL


def test_reconcile_mode_repair_overrides_the_built_in_default() -> None:
    # Arrange — an operator who would rather type `--mode full` explicitly when they mean it.
    document: dict[str, object] = {"reconcile": {"mode": "repair"}}

    # Act
    policy = reconcile_policy_from_config(document)

    # Assert
    assert policy.mode is ReconcileMode.REPAIR


def test_an_unknown_reconcile_key_carries_the_known_keys_as_a_typed_field() -> None:
    # Arrange
    document: dict[str, object] = {"reconcile": {"dry_run": True}}

    # Act / Assert — fitness function 12's family: a typed field, not only message text.
    with pytest.raises(UnknownReconcileKeyError) as raised:
        reconcile_policy_from_config(document)
    assert raised.value.valid_options == ("mode",)
    assert "dry_run" in str(raised.value)


def test_a_reconcile_value_that_is_not_repair_or_full_is_refused() -> None:
    # Arrange
    document: dict[str, object] = {"reconcile": {"mode": "wobble"}}

    # Act / Assert
    with pytest.raises(WeftError, match="full.*repair"):
        reconcile_policy_from_config(document)


def test_a_reconcile_key_that_is_not_a_table_is_refused_the_way_permissions_is() -> None:
    # Arrange — the same shape `weft_cli.permission_policy.permission_policy_from_config`
    # refuses for `[permissions]`: two readers of one file must not disagree.
    document: dict[str, object] = {"reconcile": ["full"]}

    # Act / Assert
    with pytest.raises(WeftError, match=r"\[reconcile\]"):
        reconcile_policy_from_config(document)
