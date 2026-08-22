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

**Built in Phase 5 task 5.2c.** `__schema_version__` is a second mandatory
declaration, checked in the same `__pydantic_init_subclass__` seam as
`__namespace__` and for the identical reason — G9's ruling (`docs/README.md`
decision log, `docs/02-extension-model.md` §1): a contract version cannot
stand in for it because it is not available at the read site, so an
`ExtModel` carries its own version, and a missing one fails loudly at class
definition rather than silently at first read. `SCHEMA_VERSION_KEY` is
written into every dumped namespace by `_dump` below — *in the data*, never
as a `ClassVar` a serialiser would drop, which is the exact defect `Filter.
version` demonstrates. `upgrade` is the classmethod a reader calls when a
stored version disagrees with the current one; its default refuses, naming
the namespace, the stored version and the current one, because silence here
is the reference's contaminated fallback in another costume.
"""

from collections.abc import Mapping
from types import MappingProxyType
from typing import Annotated, ClassVar, Final

from pydantic import AfterValidator, BaseModel, ConfigDict, PlainSerializer, SerializeAsAny

from weft_kernel.errors import WeftError

#: The key `_dump` writes a namespace's `__schema_version__` under, inside the plain dict
#: `ExtModel.model_dump()` otherwise produces — chosen dunder-shaped so it reads as
#: metadata about the namespace rather than one of the subclass's own fields, the same
#: visual distinction `__namespace__` itself makes at the Python level.
SCHEMA_VERSION_KEY: Final[str] = "__schema_version__"


class SchemaVersionRefusedError(WeftError):
    """A stored namespace's schema version disagrees with the class reading it, and
    `upgrade` was not overridden to reconcile the difference.

    `docs/02-extension-model.md` §1: "A reader upgrades or refuses... Silence is
    refusal." `stored_version` is `None` when the data was written before this task —
    every row this store held before 5.2c — rather than assumed to be the current
    version, which would be exactly the silent fallback CLAUDE.md forbids.
    """

    def __init__(self, *, namespace: str, stored_version: str | None, current_version: str) -> None:
        stored = "no version at all (written before schema versioning existed)"
        if stored_version is not None:
            stored = f"version {stored_version!r}"
        message = (
            f"'{namespace}' data was written at {stored}, but the installed class is at "
            f"{current_version!r} and declares no upgrade path from it. Override "
            f"{namespace}'s ExtModel.upgrade(data, from_version) to migrate this shape, "
            f"or reindex the corpus so this namespace is rewritten at the current version."
        )
        super().__init__(message)
        self.namespace = namespace
        self.stored_version = stored_version
        self.current_version = current_version


class ExtModel(BaseModel):
    """Base for a pack's namespaced extension data.

    A subclass must declare a non-empty `__namespace__` and a non-empty
    `__schema_version__` — both enforced at class definition, not at first
    use, so a missing declaration fails at import rather than at the first
    `with_ext` call or the first read off a store.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    __namespace__: ClassVar[str] = ""
    __schema_version__: ClassVar[str] = ""
    __transient__: ClassVar[bool] = False

    @classmethod
    def __pydantic_init_subclass__(cls, **kwargs: object) -> None:
        super().__pydantic_init_subclass__(**kwargs)
        if not cls.__namespace__:
            raise TypeError(
                f"{cls.__name__} must declare a non-empty __namespace__ — the "
                f"distribution name that owns this extension data"
            )
        if not cls.__schema_version__:
            raise TypeError(
                f"{cls.__name__} must declare a non-empty __schema_version__ — the "
                f"version of this namespace's own shape, carried in every dumped "
                f"instance so a reader can tell an old row from a current one even "
                f"when the pack that wrote it is not installed (docs/02-extension-model.md §1)"
            )

    @classmethod
    def upgrade(cls, data: Mapping[str, object], from_version: str | None) -> Mapping[str, object]:
        """Migrate `data`, stored at `from_version`, to this class's current schema.

        Refuses by default — `SchemaVersionRefusedError`, naming the namespace, the
        stored version and the current one. A pack that can actually reconcile an
        older shape overrides this; the base class assumes nothing is compatible,
        because guessing wrong here means silently misreading a user's own data.
        """
        raise SchemaVersionRefusedError(
            namespace=cls.__namespace__,
            stored_version=from_version,
            current_version=cls.__schema_version__,
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

    **Task 5.2c adds `SCHEMA_VERSION_KEY`** to each namespace's dumped dict,
    read off the *class*, not the instance — there is nowhere else in this
    function that the version could come from, since it is a `ClassVar`, not
    a field `model_dump()` itself would ever emit. This is the one place a
    dumped namespace's bytes are assembled, so it is the one place the
    version can travel in them rather than being dropped the way `Filter.
    version` was.
    """
    return {
        namespace: {**model.model_dump(), SCHEMA_VERSION_KEY: type(model).__schema_version__}
        for namespace, model in value.items()
    }


type ExtMap = Annotated[
    Mapping[str, SerializeAsAny[ExtModel]],
    AfterValidator(_freeze),
    PlainSerializer(_dump, return_type=dict),
]
