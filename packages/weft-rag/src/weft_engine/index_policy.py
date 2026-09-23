"""`[index]` — a project's own standing layers for `weft index`, ledger task **43.8**.

`weft_engine.reconcile_policy`'s own shape, applied to a third block: `weft index` runs no
layer by default, `--layers a,b` narrows or widens one run's own list, and `[index] layers`
is what a project names once so nobody has to type the flag every time. `weft_cli.commands.
IndexArgs.layers` is what actually decides which of the two applies for one invocation — this
module only reads the file.
"""

from __future__ import annotations

import json
from typing import cast

from pydantic import BaseModel, ConfigDict

from weft_kernel.errors import UnresolvedNameError, WeftError


class IndexPolicy(BaseModel):
    """`[index]`, resolved. `layers` defaults to `()` — a project with no `[index]` block
    runs no layer unless a person's own `--layers` names one for that run.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    layers: tuple[str, ...] = ()


class UnknownIndexKeyError(WeftError, UnresolvedNameError):
    """`[index]` names a key this module does not read.

    The identical rule `weft_engine.reconcile_policy.UnknownReconcileKeyError` and its own
    siblings already give their blocks — a key nothing reads is refused rather than ignored.
    """

    def __init__(self, message: str, *, valid_options: tuple[str, ...]) -> None:
        super().__init__(message)
        self.valid_options = valid_options


def index_policy_from_config(document: dict[str, object] | None) -> IndexPolicy:
    """`[index]` from a parsed `weft.toml`, or the built-in default if it says nothing.

    Refuses an unknown key by naming it, and refuses an `[index]` key that is present but not
    a table — `weft_engine.reconcile_policy.reconcile_policy_from_config`'s own two refusals,
    one block over.
    """
    if document is None or "index" not in document:
        return IndexPolicy()
    index = document["index"]
    if not isinstance(index, dict):
        raise WeftError(
            f"weft.toml's [index] must be a table, not {type(index).__name__} — "
            f'found `index = {index!r}`. Did you mean `[index]\\nlayers = ["..."]`?'
        )
    written = cast("dict[str, object]", index)
    unknown = sorted(key for key in written if key not in IndexPolicy.model_fields)
    if unknown:
        raise UnknownIndexKeyError(
            f"unknown [index] key(s) in weft.toml: "
            f"{', '.join(repr(key) for key in sorted(unknown))}. [index] accepts layers.",
            valid_options=tuple(sorted(IndexPolicy.model_fields)),
        )
    # R43.12: the value-type guard `reconcile_policy` has, so pydantic's own error never reaches
    # every command that builds its dependencies.
    layers: object = written.get("layers", [])
    is_list = isinstance(layers, list)
    items: list[object] = list(cast("list[object]", layers)) if is_list else [layers]
    names = [name for name in items if isinstance(name, str)]
    wrong = [name for name in items if not isinstance(name, str)] if is_list else [layers]
    if wrong:
        offending = wrong[0]
        raise WeftError(
            f"weft.toml's [index] layers must be a list of layer names, and {offending!r} is "
            f"a {type(offending).__name__} — found `layers = {layers!r}`. Did you mean "
            f"`layers = {json.dumps(names or ['...'])}`?"
        )
    return IndexPolicy.model_validate(written)


__all__ = ["IndexPolicy", "UnknownIndexKeyError", "index_policy_from_config"]
