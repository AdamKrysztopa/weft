"""The result every contract method returns.

Settled in G5. Never a bare value: `Produced` / `NothingToProduce` / `Failed`.
This is what lets the kernel own a fallback combinator over any contract
without inspecting payload content — it matches on the outcome's type and
never looks inside it — and it is the fix for the reference's worst extraction
trap: a `fail_silently` path that returned an empty result indistinguishable
downstream from a successfully-parsed empty document. A backend that
legitimately produced nothing now has `NothingToProduce` to say so, distinct
from `Failed`. See `docs/02-extension-model.md` section 1.
"""

from pydantic import BaseModel, ConfigDict


class Produced[T](BaseModel):
    """The stage ran and produced a value."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    value: T


class NothingToProduce(BaseModel):
    """The stage ran, found nothing to produce, and that is a legitimate result."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    reason: str


class Failed(BaseModel):
    """The stage did not complete."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    reason: str


type Outcome[T] = Produced[T] | NothingToProduce | Failed
