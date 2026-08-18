"""Where a `Node` came from.

Settled in G5. `sources` is computed by the kernel as the union of the
parents' sources — never authored directly, except at a true root, where
there are no parents to derive it from (see `Node.synthetic`). That rule is
what makes cascade delete reach every descendant: `docs/02-extension-model.md`
section 1, "Deleting a source cascades."

`Lineage` can be constructed directly by pack or pipeline code — `Lineage()`
and `Lineage(sources=...)` at a root are both ordinary, validated calls. The
one shape it refuses is `sources` supplied alongside non-empty `parents`: a
`Lineage` holds parent ids, not parent nodes, so it cannot check that
`sources` is *correctly* derived from them, only that it was not authored
out of nothing. `Node.derive` and `Node.combine` compute `sources` as the
union of the actual parent nodes' own sources, then reach `Lineage.derived`
to build the result — that classmethod still goes through the ordinary
validated constructor, so `parents` and `sources` remain type-checked, and
carries the fact that the check already happened through pydantic's
validation context rather than skipping validation (`model_construct`) to
get past it.

The trust signal has to survive one more step than the context argument
alone reaches: `Node.derive` and `Node.combine` embed the `Lineage` they
build into a `Node`, and pydantic re-runs a nested model's
`model_validator`s against that same object — same identity, verified by
`id()` — when the outer `Node` is constructed, but *without* replaying the
context the inner value was originally validated with. So the validator
below also stamps a private, non-field flag onto the object the one time
context says it may, and reads that flag on every later re-run — the
context argument is what makes the *first* validation honest (a caller
cannot get the flag set without going through full field validation), the
flag is what makes it durable.
"""

from pydantic import BaseModel, ConfigDict, PrivateAttr, ValidationInfo, model_validator

from weft_kernel.payload.ids import NodeId, SourceId


class Lineage(BaseModel):
    """A node's ancestry: the nodes it was built from, and the documents it traces to."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    parents: tuple[NodeId, ...] = ()
    sources: frozenset[SourceId] = frozenset()

    _derived: bool = PrivateAttr(default=False)

    @model_validator(mode="after")
    def _sources_are_derived_not_authored(self, info: ValidationInfo) -> "Lineage":
        """Refuse `sources` authored alongside non-empty `parents`.

        The only legal place to author `sources` directly is a root with no
        parents (reached through `Node.synthetic`). Everywhere else,
        `sources` must come from `Lineage.derived`, which the ordinary
        constructor cannot be used for — this is what stops a node claiming
        a source its parents do not, which would make cascade delete either
        miss it or delete it under the wrong document.
        """
        context: dict[str, object] = info.context or {}
        trusted = self._derived or bool(context.get("derived"))
        if self.parents and self.sources and not trusted:
            raise ValueError(
                "Lineage.sources is derived from parents' sources, never authored "
                "directly, except at a root with no parents (Node.synthetic) — got "
                "both non-empty parents and non-empty sources; use Lineage.derived "
                "if sources was genuinely computed from the parents' own sources"
            )
        if trusted and not self._derived:
            object.__setattr__(self, "_derived", True)
        return self

    @classmethod
    def derived(cls, *, parents: tuple[NodeId, ...], sources: frozenset[SourceId]) -> "Lineage":
        """Build a lineage whose `sources` was already correctly computed from `parents`.

        The only callers are `Node.derive` and `Node.combine`, which compute
        `sources` as the union of the actual parent nodes' own sources
        before calling this. Goes through the ordinary validated
        constructor — `parents` and `sources` are still type-checked — and
        passes the trust signal through pydantic's validation context so
        `_sources_are_derived_not_authored` above admits this one call
        without skipping validation to do it; that validator then stamps
        the result so embedding it in a `Node` (which re-runs this
        validator with no context) still passes.
        """
        return cls.model_validate(
            {"parents": parents, "sources": sources}, context={"derived": True}
        )
