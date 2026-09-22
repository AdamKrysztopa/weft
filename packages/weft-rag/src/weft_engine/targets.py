"""`--target` reaches a store through one binder — ledger task **34.3**.

Every store is built per invocation from `registry.entry(NodeStore, name).factory(None)`, so
`bind_store` below is applied to what that factory returns, exactly where `weft_engine.
run_services.check_store_capabilities` already applies `isinstance` checks against a resolved
pipeline: before anything runs, against the store the run was actually configured with.
`target` never rides `weft_kernel.context.Context` — a kernel type naming no capability, and a
target is `weft_store`'s.

**A malformed name is refused before the store is asked anything**, so a typo reads as a typo
rather than as a store that mysteriously cannot hold targets: `target_name` raises first, and
`isinstance` runs only once a real name exists to bind.
"""

from __future__ import annotations

from typing import cast

from weft_embed.contract import IdentifiedEmbedder
from weft_kernel.errors import WeftError
from weft_store.contract import (
    EmbeddingIdentity,
    NodeStore,
    TargetHolding,
    UnknownTargetError,
    target_name,
)


class StoreHoldsNoTargetsError(WeftError):
    """`--target` was given to a store that does not satisfy `TargetHolding` at all.

    Not `UnresolvedNameError`'s family: the target name itself may be perfectly well-formed and
    even one a `TargetHolding` store would recognise — what is missing is the capability, not a
    name among alternatives, so there is nothing enumerable to offer instead.
    """

    def __init__(self, *, store_name: str, target: str | None) -> None:
        consequence = (
            f"so --target {target!r} has nowhere to go"
            if target is not None
            else "so it has no targets to list"
        )
        super().__init__(
            f"the store {store_name!r} cannot hold targets — it does not satisfy "
            f"weft_store.contract.TargetHolding — {consequence}"
        )


async def bind_store(store: object, target: str | None, *, store_name: str) -> NodeStore:
    """`store`, bound to `target` if one was given — else `store` itself, unchanged.

    A malformed `target` is refused by `target_name` before `store` is inspected at all. A
    well-formed one against a store that does not satisfy `TargetHolding` is refused by name,
    naming the store, the target and the capability it lacks.
    """
    if target is None:
        return cast("NodeStore", store)
    name = target_name(target)
    if not isinstance(store, TargetHolding):
        raise StoreHoldsNoTargetsError(store_name=store_name, target=name)
    return cast("NodeStore", await store.bind_target(name))


# -- Embedding identity — ledger task 34.4 ----------------------------------------------------
#
# A target records the identity of the embedder that made its first write, and refuses a query
# whose embedder states a different one, before any vector is compared. G22 already catches a
# width mismatch; nothing catches a different model at the same width, which answers with
# confident nonsense rather than a refusal — `EmbeddingIdentityMismatchError` is that missing
# case. Recorded per target, never per node (owner decision Q5); an embedder that cannot state
# an identity is refused only where a target is explicitly asked for (Q-B) — plain, untargeted
# indexing keeps working with the write left unrecorded.


class EmbedderStatesNoIdentityError(WeftError):
    """`plugin` cannot say what it embeds with, and `target` needed to know — either a write
    that named a target explicitly (`claim_embedding_for_write(..., required=True)`), or a
    query against a target whose identity is already recorded.

    Not `UnresolvedNameError`'s family: nothing about `plugin` or `target` is a name among
    enumerable alternatives — the capability itself is missing, `weft_embed.contract.
    IdentifiedEmbedder`, the same shape `StoreHoldsNoTargetsError` above refuses by name for
    `TargetHolding`.
    """

    def __init__(self, *, plugin: str, target: str) -> None:
        super().__init__(
            f"the embedder {plugin!r} does not say which model and width it embeds with — it "
            f"does not satisfy weft_embed.contract.IdentifiedEmbedder — so target {target!r} "
            f"cannot record or check what built it"
        )
        self.plugin = plugin
        self.target = target


class EmbeddingIdentityMismatchError(WeftError):
    """`other` disagrees with `held`, the identity `target` was actually built with — a write
    that would mix two embedders' vectors into one target, or a query that would compare
    across them. `held` and `other` are the two identities `EmbedderStatesNoIdentityError`
    above only stands in for when one side cannot state one at all.
    """

    def __init__(
        self, message: str, *, held: EmbeddingIdentity, other: EmbeddingIdentity, target: str
    ) -> None:
        super().__init__(message)
        self.held = held
        self.other = other
        self.target = target

    @classmethod
    def for_query(
        cls, *, held: EmbeddingIdentity, other: EmbeddingIdentity, target: str
    ) -> EmbeddingIdentityMismatchError:
        return cls(
            f"this query embeds with {render_embedding_identity(other)}, and target "
            f"{target!r} was built with {render_embedding_identity(held)} — vectors from two "
            f"embedders cannot be compared. Set the embedder to match the target, or query "
            f"another target (`weft target rollback` restores the previous one).",
            held=held,
            other=other,
            target=target,
        )

    @classmethod
    def for_write(
        cls, *, held: EmbeddingIdentity, other: EmbeddingIdentity, target: str
    ) -> EmbeddingIdentityMismatchError:
        return cls(
            f"this index embeds with {render_embedding_identity(other)} into target "
            f"{target!r}, which was built with {render_embedding_identity(held)} — a target "
            f"holds one embedder's vectors. Index into a new target with --target, or set "
            f"the embedder back to match.",
            held=held,
            other=other,
            target=target,
        )


def render_embedding_identity(identity: EmbeddingIdentity) -> str:
    """`'<plugin>' (model <model>, width <width>)` — `width None` reads as `native width`.

    Public since ledger task **34.6**: `weft_cli.commands.TargetListCommand` reuses this
    exact rendering for `weft target list`'s own `embedding` column, so the wording an
    operator meets in a mismatch refusal and the wording they meet listing targets cannot
    drift apart.
    """
    width = "native width" if identity.width is None else f"width {identity.width}"
    return f"{identity.plugin!r} (model {identity.model}, {width})"


async def embedding_identity_of(
    embedder: object, *, plugin: str, distribution: str
) -> EmbeddingIdentity | None:
    """What `embedder` embeds with, or `None` when it cannot say — `IdentifiedEmbedder` is
    structural, so a stranger written before `34.4` simply does not satisfy it.
    """
    if not isinstance(embedder, IdentifiedEmbedder):
        return None
    stated = await embedder.embedding_model()
    return EmbeddingIdentity(
        plugin=plugin, distribution=distribution, model=stated.model, width=stated.width
    )


async def claim_embedding_for_write(
    store: object,
    identity: EmbeddingIdentity | None,
    *,
    plugin: str,
    required: bool,
    target: str | None = None,
) -> None:
    """Record `identity` against the target a write is going into — a no-op against a store
    that does not satisfy `TargetHolding`, since there is nowhere to record into.

    `identity` `None` (the embedder could not state one): refuse with
    `EmbedderStatesNoIdentityError` when `required` (a target was explicitly asked for, Q-B),
    otherwise return — the write proceeds with nothing recorded. `target`, unbound, defaults to
    whatever the message names, since a handle does not say which target it holds.
    """
    if not isinstance(store, TargetHolding):
        return
    named = target if target is not None else (await store.target_catalogue()).live
    if identity is None:
        if required:
            raise EmbedderStatesNoIdentityError(plugin=plugin, target=named)
        return
    held = await store.claim_embedding(identity)
    if held != identity:
        raise EmbeddingIdentityMismatchError.for_write(held=held, other=identity, target=named)


async def require_existing_target(store: object, target: str | None, *, store_name: str) -> None:
    """Refuse a `--target` naming nothing a store's own catalogue holds — ledger task **34.6**.

    `None` (no `--target` given) does nothing: every read command's own default is the live
    target, which always exists. A malformed name is refused by `target_name` before `store`
    is asked anything, on `bind_store`'s own footing; a well-formed one against a store that
    does not satisfy `TargetHolding` is `StoreHoldsNoTargetsError`, naming the capability it
    lacks. Otherwise the store's own `target_catalogue` is the authority: `target` not among
    its names is `UnknownTargetError`, naming every target the catalogue does hold (FF12).
    """
    if target is None:
        return
    name = target_name(target)
    if not isinstance(store, TargetHolding):
        raise StoreHoldsNoTargetsError(store_name=store_name, target=name)
    catalogue = await store.target_catalogue()
    valid = tuple(sorted(record.name for record in catalogue.targets))
    if name not in valid:
        raise UnknownTargetError(name, valid_options=valid)


async def check_embedding_for_query(
    store: object, identity: EmbeddingIdentity | None, *, plugin: str, target: str | None = None
) -> None:
    """Refuse a query whose embedder states a different identity than the target was built
    with — read-only, called before any vector is compared.

    A no-op against a store that does not satisfy `TargetHolding`. A target with no identity
    recorded (nothing has claimed it yet) is left alone: there is nothing to compare against.
    """
    if not isinstance(store, TargetHolding):
        return
    catalogue = await store.target_catalogue()
    named = target if target is not None else catalogue.live
    held = next((record.embedding for record in catalogue.targets if record.name == named), None)
    if held is None:
        return
    if identity is None:
        raise EmbedderStatesNoIdentityError(plugin=plugin, target=named)
    if identity != held:
        raise EmbeddingIdentityMismatchError.for_query(held=held, other=identity, target=named)
