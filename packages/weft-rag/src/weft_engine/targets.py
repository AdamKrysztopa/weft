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

from weft_kernel.errors import WeftError
from weft_store.contract import NodeStore, TargetHolding, target_name


class StoreHoldsNoTargetsError(WeftError):
    """`--target` was given to a store that does not satisfy `TargetHolding` at all.

    Not `UnresolvedNameError`'s family: the target name itself may be perfectly well-formed and
    even one a `TargetHolding` store would recognise — what is missing is the capability, not a
    name among alternatives, so there is nothing enumerable to offer instead.
    """

    def __init__(self, *, store_name: str, target: str) -> None:
        super().__init__(
            f"the store {store_name!r} cannot hold targets — it does not satisfy "
            f"weft_store.contract.TargetHolding — so --target {target!r} has nowhere to go"
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
