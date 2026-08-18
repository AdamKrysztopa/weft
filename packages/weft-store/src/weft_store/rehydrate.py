"""The namespace-to-class registry a store needs to read a node's `ext` back off storage.

Specified in `docs/06-phase-0-build.md` step 8: "`Node.model_dump()`
serialises `ext` correctly, but the reverse does not exist: a dumped
namespace is a plain dict, and turning it back into the pack's own `ExtModel`
subclass needs a namespace-to-class registry. Step 1 left that out on
purpose — the registry it would need arrives at steps 2-3 — so the store is
where the rehydration path is designed, **against the registry rather than
against a hand-rolled map**."

That instruction is taken literally: `ext_models` below is an ordinary
`weft_kernel.registry.Registry`, the same mechanism a pack's own `register()`
uses for plugins, reused here for a different key space — `(ExtModel,
namespace) -> the owning class` rather than `(contract, plugin name) ->
factory`. Reusing it rather than a hand-rolled `dict` buys three things for
free: a namespace claimed twice raises `DuplicateRegistrationError` naming
both classes, an unregistered namespace raises `UnknownPluginError` naming
every namespace that *is* known — rule 5's "fails loudly, naming the valid
options" applied to storage rather than to plugin lookup — and there is
exactly one registry implementation in this codebase to read, not two.

**Why `Node.model_validate` alone cannot do this.** `weft_kernel.payload.ext`'s
own module docstring already states the fact this module exists to close:
`ExtMap`'s declared value type is the base `ExtModel`, which carries
`extra="forbid"`, so validating a plain `{"reason": "..."}` dict straight
against it either drops a subclass's own fields or — for a model whose
fields are not a subset of the base's — refuses them outright as unknown.
`rehydrate_ext` is what stands between a JSONB column and `Node.model_validate`,
turning each namespace's plain dict into an instance of the *class that
namespace actually declares* before validation ever sees it.

**Phase 0 seeds this registry with exactly one class**, `weft_kernel.payload.SyntheticOrigin`
— the only `ExtModel` in the tree today, stamped onto every root node by
`Node.synthetic`, which `weft_extract`'s built-in text extractor uses for
every node it produces. A pack that ships its own `ExtModel` and wants nodes
carrying it to survive a round trip through this store calls
`register_ext_model` itself; there is no Phase 0 mechanism for a pack's own
`register()` to contribute one automatically (the same gap
`docs/02-extension-model.md`'s Phase 0 step 5 narrowing note records for
`add_messages`), so this is a second, explicit call a pack author makes, not
a consequence of installing the pack.
"""

from collections.abc import Mapping
from typing import cast

from weft_kernel.errors import WeftError
from weft_kernel.payload import ExtModel, SyntheticOrigin
from weft_kernel.registry import Registry

#: `(ExtModel, namespace) -> the class that owns it` — see the module docstring for why this
#: is a `Registry` rather than a hand-rolled `dict`.
ext_models = Registry()


class MalformedExtDataError(WeftError):
    """A stored `ext` namespace's value is not a mapping, so it cannot be re-validated.

    Every namespace this store ever wrote came from `ExtModel.model_dump()`,
    which always produces a mapping — this can only fire against data this
    store did not write itself, and refusing loudly is the only honest thing
    to do with it.
    """


def register_ext_model(model: type[ExtModel]) -> None:
    """Make `model` reconstructable from its own `__namespace__` by `rehydrate_ext`.

    Raises `weft_kernel.registry.DuplicateRegistrationError`, naming both
    classes, if another model already claimed this namespace — `Registry.add`'s
    own behaviour, unchanged here.
    """
    ext_models.add(ExtModel, model.__namespace__, model, distribution=model.__namespace__)


def rehydrate_ext(raw: Mapping[str, object]) -> dict[str, ExtModel]:
    """Turn a dumped `ext` mapping — `{namespace: plain dict}` — back into typed models.

    Raises `weft_kernel.registry.UnknownPluginError`, naming the namespace and
    every namespace `register_ext_model` *has* registered, if `raw` names one
    this store cannot rehydrate. Raises `MalformedExtDataError` if a
    namespace's value is not itself a mapping.
    """
    rehydrated: dict[str, ExtModel] = {}
    for namespace, value in raw.items():
        if not isinstance(value, Mapping):
            raise MalformedExtDataError(
                f"stored ext namespace '{namespace}' is not a mapping "
                f"(found {type(value).__name__}); cannot rehydrate it."
            )
        model_cls = cast("type[ExtModel]", ext_models.lookup(ExtModel, namespace))
        rehydrated[namespace] = model_cls(**value)
    return rehydrated


register_ext_model(SyntheticOrigin)
