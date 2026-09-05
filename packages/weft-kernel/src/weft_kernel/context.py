"""`Context` — the one passport every stage's `run()` receives, and its one seam.

Specified in `docs/06-phase-0-build.md` step 4 and `docs/02-extension-model.md`
section 1 ("What a plugin receives"): `tenant_id`, run and trace ids,
cancellation, locale and `require()`. **The admission rule for a new
field, quoted directly:** a field is admitted only if it is needed by *every*
plugin regardless of contract **and** is meaningless to resolve as a service.
Tuning knobs fail the second test — an unbounded context object that admits
them accumulates fields no plugin is obliged to honour, and callers route
around it by building a second, overlapping bag of ad-hoc state instead of
resolving through the one that already exists, which is a capability leaking
into the kernel by another name. This module is deliberately narrow, and G11
narrowed it further: four identity fields with no default, one collaborator,
one resolution method, and nothing else.

**One collaborator, distinct from the registry.** `require()` resolves against
a `ServiceRegistry`, which is separate from `weft_kernel.registry.Registry`
(step 2): that one maps `(contract, name) -> factory` for *plugins a pipeline
names in configuration*, and this one maps `contract -> an already-resolved
instance` for *ambient services every stage may need regardless of what
pipeline it runs in* — `docs/02-extension-model.md`'s example is
`ctx.require(LLM)` returning a typed handle with no name to disambiguate, and
`ctx.require(TokenSink)` for the one streaming service (`docs/03-cli.md` →
*Output*). It starts empty and is handed to `Context` already built, exactly
as `Registry.add` takes `distribution` as a parameter rather than discovering
it. Whatever assembles a run (the runner, step 6, or the CLI, step 9) builds
and populates it; this module only gives `Context` somewhere to resolve
against.

**There was a second seam, `t()`, and G11 retired it (2026-08-18).** A
`MessageCatalogue` and `Context.messages` lived here from step 4 onward, so a
kernel or pack error could resolve its text per locale. Three phases shipped
with **zero registered messages and zero `ctx.t()` call sites** — the
mechanism's own intended clientele, 51 first-party pack error classes, all
chose English literals too — and G11 settled that Weft's *interface* is
English-only as a product decision, investing instead in the **content**-
language axis it already has. A locale-keyed message store with one locale is
a dict with a constant key, so the catalogue, `Context.messages`, `t()` and
the three error classes they brought (`UnknownMessageError`,
`DuplicateMessageError`, `MessageFormatError`) are gone, taking this kernel
from 33 error classes to 30. `docs/05-grilling-sessions.md` → G11 holds the
session; `docs/02-extension-model.md` §1 owns what replaced it — an English
literal at the raise site, whose explanation surface is
`manual/troubleshooting.md`'s coverage ratchet, and whose *quality* is
fitness function 12 rather than a convention an author has to remember.

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
from typing import cast

from weft_kernel.errors import UnresolvedNameError, WeftError


class UnresolvedServiceError(WeftError, UnresolvedNameError):
    """`ctx.require()` was asked for a contract nothing registered for this run.

    The message states the contract that was wanted and every contract that
    *is* available, so a stage author who forgot to wire a service reads the
    error as a wiring bug rather than a mystery — the same standard
    `registry.py`'s `UnknownPluginError` sets for plugin lookup.

    Fitness function 12's family: `valid_options` is every contract that
    *is* registered on this run.
    """

    def __init__(self, message: str, *, valid_options: tuple[str, ...]) -> None:
        super().__init__(message)
        self.valid_options = valid_options


class DuplicateServiceError(WeftError):
    """Two instances were registered for the same contract on one `ServiceRegistry`.

    A service registry is populated once per run by whatever assembles it; a
    second instance for a contract already resolved is not an update, it is
    two callers disagreeing about which instance a stage should get. Refused
    rather than silently overwritten — `registry.py` takes the same stance for
    plugin names, for the same reason: a silent overwrite is a bug someone
    eventually has to find.
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

        options = tuple(sorted(c.__name__ for c in self._instances))
        available = ", ".join(options) or "none"
        raise UnresolvedServiceError(
            f"no service is registered for {contract.__name__} on this run. It is "
            f"unavailable because nothing resolved one before this stage ran. "
            f"Services available on this run: {available}.",
            valid_options=options,
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class Context:
    """The one passport a stage's `run()` receives. There is exactly one per run.

    `tenant_id`, `run_id`, `trace_id` and `locale` are ambient identity, fixed
    for the lifetime of one run — `frozen=True` makes that a type-level fact
    rather than a convention a stage could break by assigning `ctx.tenant_id`,
    consistent with CLAUDE.md's "frozen where the value is a domain object"
    and with `registry.RegistryEntry`'s precedent in this same layer. Freezing
    `Context` does not freeze `services`: that collaborator is populated by
    whatever assembles the run, not carried as identity.
    `require()` is the one resolution seam — see the module docstring for why
    nothing else lives here, and for what G11 retired.

    **`locale` is the run's configured *content* language, never an interface
    language** (G11, 2026-08-18). Weft's interface is English-only; what this
    field selects is material a model reads or writes, and its only consumer
    today is prompt text selection (`weft_prompts.typed_prompt`, exact locale →
    primary subtag → `en`). It is deliberately distinct from a *query*'s own
    locale: `weft_retrieve.payload.Query.locale` is "a fact about the ask", and
    a question asked in Polish against an English corpus is a different thing
    from a run configured for Polish. Nothing selects this yet — the CLI passes
    `"en"` — and giving an operator a way to choose it is `docs/03-cli.md`'s,
    hence Phase 3's.
    """

    tenant_id: str
    run_id: str
    trace_id: str
    locale: str
    services: ServiceRegistry = field(default_factory=ServiceRegistry)

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
