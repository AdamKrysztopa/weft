"""`[reconcile]` — an operator's own default for `weft reconcile`'s bare `--mode`, task **5.1c**.

`docs/03-cli.md` -> *Command surface*: "`weft reconcile` typed by a person defaults to `full`,
because someone typing that word means it... `weft.toml` sets a personal default and the flag
always wins." This module is `weft_cli.permission_policy`'s own shape, applied to a third block:
one function reading one already-parsed `dict`, a frozen Pydantic result with a built-in default,
an unknown key refused by name, and a malformed table refused the identical way `weft_cli.
registry_bootstrap.pack_settings_from_config` refuses a `[packs]` that is a list instead of a
table — three readers of one file must not disagree about what a broken block means.

**What this does *not* touch, stated rather than left to be inferred.** `weft index`'s own
automatic post-index pass is `docs/02-extension-model.md` §3 → *Slots*' own rule made concrete:
"a `Reconcilable` pack creating derived data during an automatic pass would breach it, so the
automatic pass never does" — that mode is hardcoded to `repair` in `weft_cli.commands.IndexArgs`
and reads nothing from this block, on purpose, so a `weft.toml` written once cannot quietly turn
every future `weft index` into a `full` run with nobody typing a flag that invocation. This block
governs one thing only: what `weft reconcile`, typed by hand with no `--mode`, resolves to — a
person already deliberately invoking the command, for whom "which default" is a preference, never
a consent question. `full` is still reached only by a person's per-run flag either way — this
just lets that person say which flag they mean by default, the same way `[permissions] destroy =
"allow"` lets a person change what an *unflagged* invocation of a different command does, without
changing who is doing the invoking.

**Scope: one field**, unlike `PermissionPolicy`'s two, because `weft reconcile` has exactly one
default worth overriding — `--dry-run`'s own default (`False`) is not a consent question
`weft.toml` should get to move, since a project that always dry-runs by default would silently
turn every `weft reconcile` into a no-op, which is the opposite failure this rule exists to
prevent for `full`.
"""

from __future__ import annotations

from typing import cast

from pydantic import BaseModel, ConfigDict

from weft_kernel.errors import UnresolvedNameError, WeftError
from weft_store import ReconcileMode


class ReconcilePolicy(BaseModel):
    """`[reconcile]`, resolved. `mode` defaults to `full` — unchanged from `weft reconcile`'s
    own pre-5.1c hardcoded default, so a project with no `[reconcile]` block behaves exactly
    as it always has.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    mode: ReconcileMode = ReconcileMode.FULL


class UnknownReconcileKeyError(WeftError, UnresolvedNameError):
    """`[reconcile]` names a key this module does not read.

    The identical rule `weft_cli.permission_policy.UnknownPermissionKeyError` and
    `weft_cli.config_surface.UnknownConfigKeyError` already give their own sibling blocks —
    `docs/03-cli.md` -> *Project context* requires refusal naming the keys the CLI does know,
    never silent acceptance, and fitness function 12 requires that as a typed field a caller
    can read, not only text inside the message.
    """

    def __init__(self, message: str, *, valid_options: tuple[str, ...]) -> None:
        super().__init__(message)
        self.valid_options = valid_options


def reconcile_policy_from_config(document: dict[str, object] | None) -> ReconcilePolicy:
    """`[reconcile]` from a parsed `weft.toml`, or the built-in default if it says nothing.

    Refuses an unknown key by naming it and the keys that exist, and refuses a `[reconcile]`
    key that is present but not a table — the identical two refusals `weft_cli.
    permission_policy.permission_policy_from_config` gives `[permissions]`.
    """
    if document is None or "reconcile" not in document:
        return ReconcilePolicy()
    reconcile = document["reconcile"]
    if not isinstance(reconcile, dict):
        raise WeftError(
            f"weft.toml's [reconcile] must be a table, not {type(reconcile).__name__} — "
            f'found `reconcile = {reconcile!r}`. Did you mean `[reconcile]\\nmode = "repair"`?'
        )
    written = cast("dict[str, object]", reconcile)
    known = tuple(sorted(ReconcilePolicy.model_fields))
    unknown = sorted(key for key in written if key not in ReconcilePolicy.model_fields)
    if unknown:
        raise UnknownReconcileKeyError(
            f"unknown [reconcile] key(s) in weft.toml: "
            f"{', '.join(repr(key) for key in unknown)}. [reconcile] accepts "
            f"{', '.join(known)}. A key nothing reads is refused rather than ignored — a "
            f"default you did not actually change is one you would have to notice by the "
            f"tool behaving differently than the file says.",
            valid_options=known,
        )
    # `ReconcileMode` is a closed, two-member `StrEnum` — `repair`/`full` are not names
    # resolved against a registry, a catalogue, or any set whose membership could ever
    # depend on what is installed; they are the type's own exhaustive literal values. The
    # identical exclusion `weft_cli.permission_policy`'s own raise site states in full for
    # `PermissionAction` — a type mismatch with a friendlier message, not a name failing to
    # resolve, so this is not brought into `NAME_RESOLUTION_FAMILY` either.
    valid_values = {member.value for member in ReconcileMode}
    for key, value in written.items():
        if value not in valid_values:
            raise WeftError(
                f"weft.toml's [reconcile] {key} must be one of {sorted(valid_values)}, "
                f"not {value!r}."
            )
    return ReconcilePolicy.model_validate(written)


__all__ = [
    "ReconcilePolicy",
    "UnknownReconcileKeyError",
    "reconcile_policy_from_config",
]
