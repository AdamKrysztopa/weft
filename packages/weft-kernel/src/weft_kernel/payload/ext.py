"""Namespaced, typed extension data on a `Node`.

Settled in G5. A pack declares a model that owns a namespace; the kernel
validates it on write through ordinary Pydantic construction, and
`Node.with_ext` / `Node.ext_as` are the typed read/write pair — namespace
strings never appear in plugin code. See `docs/02-extension-model.md`
section 1.

`__transient__` marks a namespace the kernel strips before the node is
persisted (`Node.without_transient`). This is deliberately a class-level,
type-checked declaration rather than the reference's `_TRANSIENT_METADATA_KEYS` —
a tuple of key-name strings a stage author had to remember to extend. A
namespace's transience is a fact about its type, checked once, at the
declaration, never re-decided at every call site.
"""

from collections.abc import Mapping
from types import MappingProxyType
from typing import Annotated, ClassVar

from pydantic import AfterValidator, BaseModel, ConfigDict, PlainSerializer, SerializeAsAny


class ExtModel(BaseModel):
    """Base for a pack's namespaced extension data.

    A subclass must declare a non-empty `__namespace__` — enforced at class
    definition, not at first use, so a missing namespace fails at import
    rather than at the first `with_ext` call.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    __namespace__: ClassVar[str] = ""
    __transient__: ClassVar[bool] = False

    @classmethod
    def __pydantic_init_subclass__(cls, **kwargs: object) -> None:
        super().__pydantic_init_subclass__(**kwargs)
        if not cls.__namespace__:
            raise TypeError(
                f"{cls.__name__} must declare a non-empty __namespace__ — the "
                f"distribution name that owns this extension data"
            )


def _freeze(value: Mapping[str, ExtModel]) -> Mapping[str, ExtModel]:
    """Wrap a validated ext mapping in an immutable view.

    `Node`'s `frozen=True` blocks attribute *assignment* only — it does not
    stop `node.ext['x'] = y` from mutating the plain `dict` a bare
    `Mapping[str, ExtModel]` field would validate to. `MappingProxyType`
    closes that door: `node.ext[...] = ...` raises `TypeError`, so
    `Node.with_ext` is the only way to change what a node's `ext` holds.
    """
    return MappingProxyType(dict(value))


def _dump(value: Mapping[str, ExtModel]) -> dict[str, object]:
    """Serialise each namespace's model by its own (sub)class, not `ExtModel`.

    Two problems, both invisible without a test that actually serialises a
    `Node`. First, `MappingProxyType` has no serializer pydantic-core knows,
    so `model_dump_json()` raises on it outright — this function's plain
    `dict` return sidesteps that. Second, declaring the value type as the
    base `ExtModel` makes pydantic serialise every entry *as* `ExtModel`:
    a subclass's own fields (e.g. `entities` on a pack's model) are silently
    dropped, not warned about, because serialisation follows the declared
    type, not the runtime one. Calling each value's own `model_dump` here is
    what stops both today; the `SerializeAsAny` on `ExtMap` below is a second
    line, covering the declared-type path if this serialiser is ever narrowed
    or removed. Only the loss of `model_dump_json` support is loud, so the
    test in `tests/unit/weft_kernel/payload/test_node.py` asserts on the
    subclass's field values, not merely that dumping did not raise.

    Note for step 8 (the store): this is the write side only. A dumped `ext`
    is plain dicts, so `Node.model_validate(node.model_dump())` does *not*
    round-trip — rehydrating a namespace string back to the owning model
    class needs a registry that does not exist yet.
    """
    return {namespace: model.model_dump() for namespace, model in value.items()}


type ExtMap = Annotated[
    Mapping[str, SerializeAsAny[ExtModel]],
    AfterValidator(_freeze),
    PlainSerializer(_dump, return_type=dict),
]
