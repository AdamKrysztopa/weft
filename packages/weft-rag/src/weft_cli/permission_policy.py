"""`[permissions]` — an operator's override of the two classes `docs/03-cli.md` -> *Permissions*
defaults to `ask`, read from the same `weft.toml` `weft_cli.registry_bootstrap` already parses.

Task **3.3**, design question 4: "Where per-class defaults in `weft.toml` are read, consistent
with `weft_cli.services`' existing config handling, and what happens to a key the CLI does not
know — `03` -> *Project context* requires refusal naming the keys it does know, never silent
acceptance." This module is `weft_cli.services.service_selection_from_config`'s own shape, applied
to a second block: one function reading one already-parsed `dict`, a frozen Pydantic result with a
built-in default for every field, an unknown key refused by name, and a malformed table refused
the identical way `weft_cli.registry_bootstrap.pack_settings_from_config` refuses a `[packs]` that
is a list instead of a table — two readers of one file must not disagree about what a broken block
means.

**Scope, stated rather than silently narrowed.** `docs/03-cli.md`'s own table names five classes;
only `overwrite` and `destroy` default to `ask`, so those are the only two keys this block
accepts. `read`/`write` are unconditionally `allow` — nothing in `weft_cli.confirm` gates them at
all, so a key here that claimed to change one would change nothing, which is exactly the
manufactured-control shape `docs/02-extension-model.md` -> *The trust model* refuses for
disclosure ("a field that reads as... is unverified... and fails silently in the unsafe
direction"). `network`'s own "allow, configurable" is a real, separate knob nothing in this phase
reads yet — no `network`-class command is built before Phase 5's graph pack — so naming it here
would be documentation for a feature nothing exercises, the identical `weft-openai`-shaped
mistake `docs/README.md`'s own correction anecdote (2026-08-10) already names once for this
project. Left to whichever task first ships a `network`-class command.

```toml
[permissions]
destroy = "allow"    # skip confirmation for destroy-class commands, e.g. a CI job that
                      # already trusts its own pipeline
overwrite = "ask"     # unchanged from the built-in default; stated for clarity
```

**There is no way to tighten `overwrite`/`destroy` beyond `ask`, only to loosen them to
`allow`.** `ask` already is the floor `docs/03-cli.md` fixes for both classes; a third value that
made them *stricter* than "always confirm" is not a shape this table's own two-member vocabulary
needs, and `PermissionAction` stays a closed `StrEnum` — never `Literal[...]`, per CLAUDE.md —
so a `weft.toml` naming anything else is refused rather than silently coerced.

**Repair, 2026-08-20** (`docs/build-ledger.md` 3.3's own dated paragraph carries the argument
in full): the unknown-key refusal below used to be a bare `WeftError` computing the valid keys
and interpolating them into the message only — invisible to fitness function 12's family walk,
which looks for a typed `valid_options` field, never message text. `UnknownPermissionKeyError`
now carries it, the identical shape `weft_cli.config_surface.UnknownConfigKeyError` already gives
`[services]`'s sibling refusal. The malformed-value check just below it (`"ask" or "allow"`) is
**not** brought into the family — see that raise site's own comment for why a closed two-member
`StrEnum`'s value validation is a type mismatch, not a name failing to resolve against a set.
"""

from __future__ import annotations

from enum import StrEnum
from typing import cast

from pydantic import BaseModel, ConfigDict

from weft_kernel.errors import UnresolvedNameError, WeftError


class PermissionAction(StrEnum):
    """What `[permissions].<class>` may say. `ASK` is every field's own built-in default —
    `docs/03-cli.md` -> *Permissions*' table for `overwrite` and `destroy`.
    """

    ASK = "ask"
    ALLOW = "allow"


class PermissionPolicy(BaseModel):
    """`[permissions]`, resolved — see the module docstring's *"Scope"* paragraph for why these
    are the only two fields, not one per class in `weft_command.permission.PermissionClass`.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    overwrite: PermissionAction = PermissionAction.ASK
    destroy: PermissionAction = PermissionAction.ASK


class UnknownPermissionKeyError(WeftError, UnresolvedNameError):
    """`[permissions]` names a key this module does not read.

    Repair, 2026-08-20 (finding 1): the identical rule `weft_cli.config_surface.
    UnknownConfigKeyError` already gives `[services]`'s sibling refusal, applied here —
    `docs/03-cli.md` -> *Project context* requires refusal naming the keys the CLI does know,
    never silent acceptance, and fitness function 12 requires that as a typed field a caller
    can read, not only text inside the message a reviewer has to notice.
    """

    def __init__(self, message: str, *, valid_options: tuple[str, ...]) -> None:
        super().__init__(message)
        self.valid_options = valid_options


def permission_policy_from_config(document: dict[str, object] | None) -> PermissionPolicy:
    """`[permissions]` from a parsed `weft.toml`, or every built-in default if it says nothing.

    Refuses an unknown key by naming it and the keys that exist — the identical rule
    `weft_cli.services.service_selection_from_config` applies to `[services]` — and refuses a
    `[permissions]` key that is present but not a table, the same way
    `weft_cli.registry_bootstrap.pack_settings_from_config` refuses a malformed `[packs]`.
    """
    if document is None or "permissions" not in document:
        return PermissionPolicy()
    permissions = document["permissions"]
    if not isinstance(permissions, dict):
        raise WeftError(
            f"weft.toml's [permissions] must be a table, not {type(permissions).__name__} — "
            f"found `permissions = {permissions!r}`. Did you mean "
            f'`[permissions]\\ndestroy = "allow"`?'
        )
    written = cast("dict[str, object]", permissions)
    known = tuple(sorted(PermissionPolicy.model_fields))
    unknown = sorted(key for key in written if key not in PermissionPolicy.model_fields)
    if unknown:
        raise UnknownPermissionKeyError(
            f"unknown [permissions] key(s) in weft.toml: "
            f"{', '.join(repr(key) for key in unknown)}. [permissions] accepts "
            f"{', '.join(known)}. A key nothing reads is refused rather than ignored — a "
            f"permission you did not actually change is one you would have to notice by the "
            f"tool behaving differently than the file says.",
            valid_options=known,
        )
    # `PermissionAction` is a closed, two-member `StrEnum` — `ask`/`allow` are not names
    # resolved against a registry, a catalogue, or any set whose membership could ever depend
    # on what is installed or what a project's own document declares; they are the type's own
    # exhaustive literal values. This is a type mismatch with a friendlier message, the same
    # category FF12's own module docstring uses to exclude a collision or a malformed shape —
    # not brought into `NAME_RESOLUTION_FAMILY`. `PermissionPolicy.model_validate(written)`'s
    # own `pydantic.ValidationError` would report the identical fact were this guard absent.
    valid_values = {member.value for member in PermissionAction}
    for key, value in written.items():
        if value not in valid_values:
            raise WeftError(
                f"weft.toml's [permissions] {key} must be 'ask' or 'allow', not {value!r}."
            )
    return PermissionPolicy.model_validate(written)


__all__ = [
    "PermissionAction",
    "PermissionPolicy",
    "UnknownPermissionKeyError",
    "permission_policy_from_config",
]
