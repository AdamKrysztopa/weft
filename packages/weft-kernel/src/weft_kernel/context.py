"""`Context` — the one passport every stage's `run()` receives, and its two seams.

Specified in `docs/06-phase-0-build.md` step 4 and `docs/02-extension-model.md`
section 1 ("What a plugin receives"): `tenant_id`, run and trace ids,
cancellation, locale, `require()` and `t()`. **The admission rule for a new
field, quoted directly:** a field is admitted only if it is needed by *every*
plugin regardless of contract **and** is meaningless to resolve as a service.
Tuning knobs fail the second test — that is precisely how the reference's
`EngineContext` grew to ten fields including multimodal config, a capability
leaking into the kernel, and was still bypassed: only 6 classes in 259 files
take an `EngineContext`-annotated `__init__` parameter, because strategy
handlers reached for a second, overlapping bag instead
(`docs/04-reference-inventory.md`, the C2 correction). This module is deliberately
narrow: five identity fields with no default, two resolution methods, and
nothing else.

**Two collaborators, not two copies of the same idea.** `require()` resolves
against a `ServiceRegistry`; `t()` resolves against a `MessageCatalogue`. Both
are separate from `weft_kernel.registry.Registry` (step 2), which maps
`(contract, name) -> factory` for *plugins a pipeline names in configuration*.
The service registry maps `contract -> an already-resolved instance` for
*ambient services every stage may need regardless of what pipeline it runs
in* — `docs/02-extension-model.md`'s example is `ctx.require(LLM)` returning a
typed handle with no name to disambiguate, and `ctx.require(TokenSink)` for
the one streaming service (`docs/03-cli.md` → *Output*). Nothing in Phase 0
populates either collaborator yet — no service exists to require, no pack has
registered a message — so both start empty and are handed to `Context`
already built, exactly as `Registry.add` takes `distribution` as a parameter
rather than discovering it. Whatever assembles a run (the runner, step 6, or
the CLI, step 9) builds and populates them; this module only gives `Context`
somewhere to resolve against.

**Cancellation is not a field, on purpose.** `docs/02-extension-model.md`:
"cancellation is native, and under an async core that is task cancellation."
Storing a second, Weft-owned cancellation flag would be exactly the shadow
machinery G6 refuses — it could drift from the real `asyncio.Task` state, and
nothing would keep the two in sync. `Context.cancelled` is a computed view
onto the task actually running the stage: `asyncio.current_task().cancelling()
> 0` (Python 3.11+, native to `asyncio`, no new primitive). It exists so a
compute-heavy stage with no `await` in its inner loop — invisible to the
blocking-call detector by design, `blocking.py`'s closing note — has a
cooperative checkpoint; it is not how cancellation is *requested*. Requesting
it is `task.cancel()`, called by whoever holds the task, which is never this
module's job.

**Identity fields carry no default.** `tenant_id`, `run_id`, `trace_id` and
`locale` are supplied by the caller. A default locale, in particular, is a
policy choice — which language a tenant with no stated preference gets — and
the kernel names no capability and states no policy; the driver constructing
a `Context` states it instead.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

from weft_kernel.errors import WeftError

if TYPE_CHECKING:
    from collections.abc import Mapping


class UnresolvedServiceError(WeftError):
    """`ctx.require()` was asked for a contract nothing registered for this run.

    The message states the contract that was wanted and every contract that
    *is* available, so a stage author who forgot to wire a service reads the
    error as a wiring bug rather than a mystery — the same standard
    `registry.py`'s `UnknownPluginError` sets for plugin lookup.
    """


class DuplicateServiceError(WeftError):
    """Two instances were registered for the same contract on one `ServiceRegistry`.

    A service registry is populated once per run by whatever assembles it; a
    second instance for a contract already resolved is not an update, it is
    two callers disagreeing about which instance a stage should get. Refused
    rather than silently overwritten — `registry.py` takes the same stance for
    plugin names, for the same reason: a silent overwrite is a bug someone
    eventually has to find.
    """


class UnknownMessageError(WeftError):
    """`ctx.t()` was asked for a key no pack's catalogue carries, for the given locale.

    States the key and locale that were wanted and every key registered for
    that locale, so a typo'd message key reads as a typo rather than a blank
    string silently reaching a user — the anti-reference property `registry.py`
    already documents for plugin names, applied to message keys instead.
    """


class DuplicateMessageError(WeftError):
    """Two templates were registered for the same `(locale, key)` on one `MessageCatalogue`.

    A catalogue is populated once per run by whatever assembles it; a second
    template for a `(locale, key)` pair already registered is not an update,
    it is two contributors disagreeing about what `ctx.t()` should return.
    Refused rather than silently overwritten — `registry.py`'s
    `DuplicateRegistrationError` takes the same stance for plugin names, and
    `ServiceRegistry.add`'s `DuplicateServiceError` takes it for services, for
    the same reason: a silent overwrite is a bug someone eventually has to
    find, and the duplicate-name trap `docs/06-phase-0-build.md` fixes for G2
    is refuse, naming both, not last-wins.
    """


class MessageFormatError(WeftError):
    """`ctx.t()`'s template could not be formatted with the parameters supplied.

    Raised when a template names a placeholder (`{n}`, `{}`) the caller did
    not pass — `str.format` would otherwise raise a bare `KeyError` or
    `IndexError` naming only the missing placeholder, with no key, locale or
    template to say where the mismatch is. States all four.
    """


class ServiceRegistry:
    """Per-run map of `contract -> the one resolved instance a stage gets back.`

    Distinct from `weft_kernel.registry.Registry`: that one holds *factories*,
    keyed by `(contract, name)`, for plugins a pipeline names in
    configuration. This one holds *already-built instances*, keyed by
    contract alone, for services `docs/02-extension-model.md` says are
    "meaningless to resolve" any other way — there is no name to disambiguate
    because a run has exactly one answer for "the LLM" or "the token sink".
    """

    def __init__(self) -> None:
        self._instances: dict[type[object], object] = {}

    def add[T](self, contract: type[T], instance: T) -> None:
        """Register `instance` as this run's answer for `contract`.

        Refuses a second instance for a contract already registered — see
        `DuplicateServiceError`.
        """
        if contract in self._instances:
            raise DuplicateServiceError(
                f"a service for {contract.__name__} is already registered on this run; "
                f"a second registration would leave it ambiguous which instance a stage "
                f"gets back. Refused rather than silently overwritten."
            )
        self._instances[contract] = instance

    def resolve[T](self, contract: type[T]) -> T:
        """This run's instance for `contract`.

        Raises `UnresolvedServiceError`, naming `contract` and every contract
        that *is* available, if nothing registered one.
        """
        if contract in self._instances:
            # `add` only ever stores an instance under its own `contract` key,
            # so this cast states exactly the invariant `resolve` relies on.
            return cast(T, self._instances[contract])

        available = ", ".join(sorted(c.__name__ for c in self._instances)) or "none"
        raise UnresolvedServiceError(
            f"no service is registered for {contract.__name__} on this run. It is "
            f"unavailable because nothing resolved one before this stage ran. "
            f"Services available on this run: {available}."
        )


class MessageCatalogue:
    """Per-locale map of a dotted message key to a format template, merged across packs.

    `docs/02-extension-model.md` section 1 says messages resolve "against the
    merged catalogue, namespaced by pack" — collision-free by construction,
    the same guarantee `ExtModel.__namespace__` gives payload fields. This
    class stays a flat `{locale: {key: template}}` map because *how* a pack's
    namespace reaches a key — `add_messages(ns=..., resources=...)` on the
    surface a pack's `register()` receives — **is not built in any Phase 0
    step.** This docstring originally said step 5 would build it; step 5 built
    `weft_kernel.discovery.PackRegistrar`, which exposes `add` and nothing
    else, and `docs/02-extension-model.md` section 1 has been corrected to
    match. What this class owns today is the merge itself: a `(locale, key)`
    pair is refused if it is
    already registered, so two contributors can never silently decide the
    same key differently — see `DuplicateMessageError`.
    """

    def __init__(self) -> None:
        self._templates: dict[str, dict[str, str]] = {}

    def add(self, *, locale: str, key: str, template: str) -> None:
        """Contribute one message: `key`, in `locale`, formatted from `template`.

        Refuses a second template for a `(locale, key)` pair already
        registered — see `DuplicateMessageError`.
        """
        by_locale = self._templates.setdefault(locale, {})
        existing = by_locale.get(key)
        if existing is not None:
            raise DuplicateMessageError(
                f"message '{key}' is already registered for locale '{locale}' as "
                f"'{existing}'; a second template ('{template}') would leave it "
                f"ambiguous which one ctx.t() should return. Refused rather than "
                f"silently overwritten."
            )
        by_locale[key] = template

    def resolve(self, *, locale: str, key: str, params: Mapping[str, object]) -> str:
        """`key`'s template for `locale`, formatted with `params`.

        Raises `UnknownMessageError`, naming `key`, `locale`, and every key
        registered for that locale, if nothing registered one. Raises
        `MessageFormatError`, naming `key`, `locale`, the template and the
        parameters supplied, if `template` names a placeholder `params` does
        not carry.
        """
        by_locale = self._templates.get(locale, {})
        template = by_locale.get(key)
        if template is None:
            available = ", ".join(sorted(by_locale)) or "none"
            raise UnknownMessageError(
                f"no message '{key}' is registered for locale '{locale}'. Messages "
                f"available for '{locale}': {available}."
            )
        try:
            return template.format(**params)
        except (KeyError, IndexError) as exc:
            supplied = ", ".join(sorted(params)) or "none"
            raise MessageFormatError(
                f"message '{key}' for locale '{locale}' (template: {template!r}) could "
                f"not be formatted: {exc!r}. Parameters supplied: {supplied}."
            ) from exc


@dataclass(frozen=True, slots=True, kw_only=True)
class Context:
    """The one passport a stage's `run()` receives. There is exactly one per run.

    `tenant_id`, `run_id`, `trace_id` and `locale` are ambient identity, fixed
    for the lifetime of one run — `frozen=True` makes that a type-level fact
    rather than a convention a stage could break by assigning `ctx.tenant_id`,
    consistent with CLAUDE.md's "frozen where the value is a domain object"
    and with `registry.RegistryEntry`'s precedent in this same layer. Freezing
    `Context` does not freeze `services` or `messages`: those two collaborators
    are populated by whatever assembles the run, not carried as identity.
    `require()` and `t()` are the two resolution seams — see the module
    docstring for why nothing else lives here.
    """

    tenant_id: str
    run_id: str
    trace_id: str
    locale: str
    services: ServiceRegistry = field(default_factory=ServiceRegistry)
    messages: MessageCatalogue = field(default_factory=MessageCatalogue)

    @property
    def cancelled(self) -> bool:
        """Whether the task running this stage has a pending cancellation request.

        A computed view onto `asyncio`'s own task state — see the module
        docstring for why `Context` stores no cancellation flag of its own.
        `False` outside a running task (for example, while unit-testing a
        stage's pure logic with no event loop, or from inside an
        `asyncio.to_thread` worker — the compute-heavy-stage offload path this
        property exists to serve, which itself runs off the event loop), never
        an error: the absence of a task is not a request to cancel.
        `asyncio.current_task()` raises `RuntimeError` rather than returning
        `None` when there is no running loop to ask, so that specific,
        documented case is the one exception this property catches.
        """
        try:
            task = asyncio.current_task()
        except RuntimeError:
            return False
        return task is not None and task.cancelling() > 0

    def require[T](self, contract: type[T]) -> T:
        """This run's instance for `contract`, resolved by type — never by name.

        Raises `UnresolvedServiceError`, naming what was wanted and what is
        available, if nothing registered one — see `ServiceRegistry.resolve`.
        """
        return self.services.resolve(contract)

    def t(self, key: str, **params: object) -> str:
        """The message registered as `key` for this context's locale, formatted with `params`.

        Never formats in place elsewhere: `docs/02-extension-model.md` — "messages
        are looked up, never formatted in place." Raises `UnknownMessageError`
        naming `key`, the locale, and every key available for it, if nothing
        registered one — see `MessageCatalogue.resolve`.
        """
        return self.messages.resolve(locale=self.locale, key=key, params=params)
