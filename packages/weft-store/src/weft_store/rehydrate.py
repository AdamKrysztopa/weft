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

**Seeded unconditionally with exactly one class**, `weft_kernel.payload.SyntheticOrigin`
— a kernel primitive stamped onto every root node by `Node.synthetic` regardless of which
packs are installed, so it is registered here at import time rather than through any
pack's `register()`; see `register_ext_model(SyntheticOrigin)` at the foot of this module.

**Built in Phase 5 task 5.2g.** Every *other* `ExtModel` — a pack's own namespaced
extension data — now reaches this registry through the pack's own `register()`, with no
further call and no `weft-cli` edit: `weft_kernel.discovery.PackRegistrar.add_ext_model`
buffers the class the same way `add_pipeline_resource` buffers a pipeline locator, and
`register_from_reports` below is the generic consumer, reading `PackReport.ext_models`
back off every report `discover()` returns and registering whatever it finds. `weft-cli`
calls it exactly once, right after `discover()`, with no per-pack knowledge in that call
site — the same shape `weft_cli.pipeline_catalogue.load_contributed` already has for
`PackReport.pipeline_resources`. Before this task, only `register_ext_model` existed, a
pack author's own explicit second call; `weft_kernel.discovery.PackRegistrar` had no seam
for this at all (the same gap this module's own docstring, and `docs/02-extension-model.md`
§1's Phase 0 step 5 narrowing note, once recorded for `add_messages` — G11 retired that one
outright, and this is the other half actually closing rather than being retired). Both
paths write to the identical `ext_models` registry, and **they do not behave identically** —
corrected at ledger task 6.34, having said the opposite since task 5.2g. `register_from_reports`
goes through `_register_if_new` and **skips** a namespace the same class already claimed;
`register_ext_model` calls `ext_models.add` directly and **refuses** unconditionally, even for a
re-registration of that same class.

So the choice matters exactly where the old sentence said it did not. **A caller outside full
discovery — a test, or anything building a registry by hand — wants
`register_from_reports`**: `register_ext_model` works when it runs alone and raises
`DuplicateRegistrationError` the moment some earlier caller in the same process has already
registered the class. Two tests hit precisely that in one phase (ledger 6.8 and 6.17), each
passing on its own and failing in the full suite. `docs/lessons.md` **L6.28** is the general form:
an equivalence stated in prose between two code paths is a missing test, and the more precisely it
names the caller it is wrong about, the more expensive it is.

**Built in Phase 5 task 5.2c.** This is also the read side of G9's persisted-
schema axis: every namespace `_dump` writes carries `SCHEMA_VERSION_KEY`
alongside its fields (`weft_kernel.payload.ext`'s own module docstring), and
this is where that key is read back off. A stored version equal to the
class's current `__schema_version__` rehydrates exactly as before this task;
one that differs — including a namespace with no version key at all, which
is every row this store held before this task existed — goes through
`model_cls.upgrade(fields, stored_version)`, whose default refuses with
`SchemaVersionRefusedError`, naming the namespace, the stored version (or
that there was none) and the current one. Nothing here decides *how* to
migrate an older shape; that is the owning pack's `upgrade` override, made
exactly where the class that understands both shapes already lives.
"""

from collections.abc import Iterable, Mapping
from typing import cast

from weft_kernel.discovery import PackReport
from weft_kernel.errors import WeftError
from weft_kernel.payload import SCHEMA_VERSION_KEY, ExtModel, SyntheticOrigin
from weft_kernel.registry import Registry, UnknownPluginError

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


def register_from_reports(reports: Iterable[PackReport]) -> None:
    """Register every `ExtModel` any pack declared through `PackRegistrar.add_ext_model`.

    Task **5.2g** — the generic consumer of `PackReport.ext_models`, the same shape
    `weft_cli.pipeline_catalogue.load_contributed` already has for `PackReport.
    pipeline_resources`: it walks whatever every report carries and knows nothing about
    which pack contributed which class, so a future pack shipping a new `ExtModel` costs
    this function nothing to support. Call once, after `discover()` returns — `weft-cli`'s
    `registry_bootstrap.build_dependencies` is the one caller today.

    **Idempotent for a namespace already claimed by the identical class** — the same
    check `_ensure_chunk_offset_rehydrates` used to make by hand for `weft_chunk.payload.
    ChunkOffset` alone, generalised here for every namespace: this function is safe to
    call more than once in one process (every test in this tree's own suite that calls
    `discover()` more than once does), because a namespace `ext_models` already holds
    against the exact same class is not a collision, only a repeat report of the same
    fact. A *different* class claiming a namespace already held raises
    `weft_kernel.registry.DuplicateRegistrationError`, naming both, exactly as
    `register_ext_model` always has — two packs' `ExtModel`s racing for one namespace is
    a real collision this function must not paper over.
    """
    for report in reports:
        for model in report.ext_models:
            _register_if_new(model)


def _register_if_new(model: type[ExtModel]) -> None:
    """`register_ext_model(model)`, skipped only when `model` itself already claimed
    this namespace — see `register_from_reports`'s own docstring for why.
    """
    try:
        registrant = ext_models.entry(ExtModel, model.__namespace__).factory
    except UnknownPluginError:
        register_ext_model(model)
        return
    if registrant is not model:
        register_ext_model(model)


def rehydrate_ext(raw: Mapping[str, object]) -> dict[str, ExtModel]:
    """Turn a dumped `ext` mapping — `{namespace: plain dict}` — back into typed models.

    Raises `weft_kernel.registry.UnknownPluginError`, naming the namespace and
    every namespace `register_ext_model` *has* registered, if `raw` names one
    this store cannot rehydrate. Raises `MalformedExtDataError` if a
    namespace's value is not itself a mapping. Raises `SchemaVersionRefusedError`
    (task 5.2c, see the module docstring) if the stored `SCHEMA_VERSION_KEY` —
    or its absence — disagrees with the registered class's `__schema_version__`
    and that class's `upgrade` was not overridden to reconcile it.
    """
    rehydrated: dict[str, ExtModel] = {}
    for namespace, value in raw.items():
        if not isinstance(value, Mapping):
            raise MalformedExtDataError(
                f"stored ext namespace '{namespace}' is not a mapping "
                f"(found {type(value).__name__}); cannot rehydrate it."
            )
        model_cls = cast("type[ExtModel]", ext_models.lookup(ExtModel, namespace))
        fields: dict[str, object] = dict(cast("Mapping[str, object]", value))
        stored_version = cast("str | None", fields.pop(SCHEMA_VERSION_KEY, None))
        if stored_version != model_cls.__schema_version__:
            fields = dict(model_cls.upgrade(fields, stored_version))
        rehydrated[namespace] = model_cls(**fields)
    return rehydrated


register_ext_model(SyntheticOrigin)
