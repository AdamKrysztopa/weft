"""Entry-point discovery and the trust model — G3 in code.

Specified in `docs/06-phase-0-build.md` step 5 and `docs/02-extension-model.md`
section 2 ("Packs and discovery", *The trust model*). The threat G3 settled on
is **installed-and-ambient, not malicious**: entry points turn *installed*
into *executed with the application's privileges*, and the only defensible
posture is to state that plainly rather than simulate a control CPython
cannot enforce. Two consequences follow directly into this module's shape.

**Discovery is eager, and refusal precedes it.** `discover()` enumerates every
distribution that declares a `weft.packs` entry point and, for each one still
permitted, imports it and calls its `register()` — because bare plugin names
(`docs/02` section 3) mean nothing can answer "who provides this?" without
running `register()` to find out. A pack outside an active `[packs] allow`
pin is never imported at all: the check happens before `entry_point.load()`
is ever called, not after, because "refused" that still executed is not
refusal. This is fitness function 8(a), the property the canary in
`testing/weft-canary/` exists to prove — see `tests/architecture/`.

**One status vocabulary answers "why is this pack not contributing?" for
every reason at once** — refused, failed, partially registered, or simply not
installed — because a refused pack and a pack that lost half its
registrations to a missing optional dependency are the same question asked
twice. `PARTIAL` is part of that vocabulary now because the vocabulary is one
piece; the *mechanism* that produces it is G4's conditional registration, a
later step's job.

**Two more pieces of the trust model attach here because there was nowhere
else for them to attach.** `DISCLOSURE` is a module-level, optional, purely
informational value the kernel reads immediately after import and before
`register()` runs — never a claim weft checks, never a permission it grants.
A `DISCLOSURE` that is present but not a `Disclosure` instance is not the
same fact as no `DISCLOSURE` at all — the pack tried to say something and
said it wrong — so that case is `FAILED`, naming the pack and what
the attribute must be, rather than silently read as "not disclosed."
Pack settings (`docs/02`'s `packs:` block, keyed by **pack** name — the
`weft.packs` entry-point name, so `[packs.store]`, never `[packs.store]`)
are validated against the pack's own Pydantic model *before* `register()` is
called, because a pack author's `register(registry, settings)` should never
have to guard against malformed input the kernel could have rejected first —
and `${env:VAR}` interpolation happens on that settings data here, so no pack
ever reads `os.environ` itself for a secret. A `packs:` key naming a
pack nothing installed declares is the strict half of that same
model: `docs/02` states the asymmetry exactly — "`packs:` expresses a
requirement, `allow` expresses a permission" — so once every entry point is
enumerated, any settings key no entry point claims raises, naming every pack
that did declare a `weft.packs` entry point, rather than being read and
quietly discarded.

**`pack` and `distribution` are two different identities and this module is
where they part.** A pack is what an entry point names; a distribution is what
an index ships. They were the same string while every pack had a wheel of its
own, and stopped being it when one wheel started shipping fourteen. Everything
an operator points at a *pack* keys on the entry-point name — the rows `weft
plugins list|doctor` prints, `[packs.<pack>]` settings, and the pack named in a
settings or disclosure failure. Everything about *provenance* keys on the
distribution — `[packs] allow`, the version column, and version skew. `docs/
02-extension-model.md` §2 owns the split.

**Registration is transactional per pack.** `PackRegistrar.add` buffers
every call instead of writing through to the `Registry` immediately; nothing
lands there until `register()` returns without raising, at which point the
whole buffer commits in one atomic step (`Registry.add_many`) or none of it
does. A pack that raises partway through therefore contributes exactly the
`0` its `FAILED` report claims — the report and the registry can never
disagree about how much of a half-finished pack is actually live.

**`PackRegistrar` exists because attribution is not a pack author's to supply, and
attribution is never a pack author's to supply** — `registry.py`'s own
docstring names this exact gap: "A pack's own `register()` calls the
seam-bound surface with `(contract, name, factory)`." This is that surface:
`Registry.add` minus its keyword-only `distribution` parameter, bound once
per pack by whatever called `discover()`, so a pack author writes
`registrar.add(Contract, "name", factory)` and never sees attribution at all.

**Task 5.2g — `add_ext_model` closes the gap `docs/02-extension-model.md` §1's
Phase 0 step 8 note left open: "a pack's `register()` does not contribute one
automatically."** Buffered exactly like `add_pipeline_resource` and
`deprecate` above, for the identical structural reason — a pack whose
`register()` raises partway through must not leave a namespace claimed that
was never actually committed. `weft_kernel.payload.ext.ExtModel` is a payload
primitive the kernel already owns (`Node.ext`'s own declared value type), not
a capability, so buffering a `type[ExtModel]` here teaches the kernel nothing
about stores: it is inert data until something that *does* know what a store
is reads `PackReport.ext_models` back off every report and registers each
class with the namespace-to-class registry that actually rehydrates one —
`weft_store.rehydrate.register_from_reports`, called once, generically, by
whatever already calls `discover()` (`weft_cli.registry_bootstrap.
build_dependencies`). No pack-specific knowledge sits in that call site: it
walks whatever `PackReport.ext_models` any report carries, so a future pack
shipping a new `ExtModel` needs no edit here and no edit in `weft-cli` at all.

**Task 5.3a (`S8`) — `add_contribution` closes the identical gap for `02` §3 →
*Slots*: a pack could describe a stage contribution as a `weft_kernel.resolution.
Contribution` value, but nothing let a pack's own `register()` hand one to anything.
Buffered exactly like `add_ext_model` just above, for the identical structural
reason — a pack whose `register()` raises partway through must not leave a slot
looking filled that was never actually committed. `Contribution` is a pipeline-model
value the kernel already owns (`weft_kernel.resolution` is this same distribution),
not a capability, so this teaches the kernel nothing new either: it stops at "this
pack offered this contribution," and `PackReport.contributions` is read back off
every report by whatever assembles a `resolve()` call's own `contributions=` tuple —
`weft_cli.registry_bootstrap.build_dependencies`, the same caller `Contribution`'s
own docstring names, now real. No pack-specific knowledge sits there either: it
concatenates whatever `PackReport.contributions` every report carries, so a future
pack contributing into a slot needs no edit here and no edit in `weft-cli` at all.

**Task 6.20 (G13) — `add_renderer` closes the analogous gap for a `Command` result:**
`docs/03-cli.md` → *Plugin-contributed commands*, "a result type nobody outside the CLI
can format is only half a contract." Buffered exactly like `add_ext_model` and
`add_contribution`, on the identical structural reason and the identical restraint: the
kernel names neither `weft_command.contract.CommandResult` nor `weft_command.render.
Rendered` — `RendererOffer` remembers only that this pack offered *some* type and *some*
callable, exactly as `add_ext_model` stops at "this pack declared this class." `PackReport.
renderers` is read back off every report by `weft_cli.render.register_renderers_from_reports`,
called once, generically, by whatever already calls `discover()` — the same shape one
surface over, and the CLI's own built-in renderers register through the identical call so
no built-in keeps a private path.
"""

from __future__ import annotations

import inspect
import os
import re
import sys
from collections.abc import Callable, Collection, Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from importlib import metadata
from typing import Protocol, cast, get_type_hints

from pydantic import BaseModel, ConfigDict, ValidationError

from weft_kernel.errors import UnresolvedNameError, WeftError
from weft_kernel.payload.ext import ExtModel
from weft_kernel.pipeline import StageDeclaration
from weft_kernel.registry import Registry
from weft_kernel.resolution import Contribution
from weft_kernel.seam import Deprecation, Unavailable, removal_for, warn_deprecated

#: The one entry-point group a pack declares. `docs/02-extension-model.md` section 2.
ENTRY_POINT_GROUP = "weft.packs"

_ENV_TOKEN = re.compile(r"^\$\{env:([^}]+)\}$")


class PackStatus(StrEnum):
    """Why a pack is, or is not, contributing to the registry right now.

    One vocabulary for every reason, shared with G4's conditional
    registration (`docs/02-extension-model.md`, *The trust model*): a refused
    pack and one that registered only part of what it offers are the same
    question — *why is this not here?* — answered the same way.
    """

    ACTIVE = "active"
    REFUSED = "refused"
    FAILED = "failed"
    PARTIAL = "partial"
    ALLOWED_NOT_INSTALLED = "allowed, not installed"


class Disclosure(BaseModel):
    """What a pack says it touches. Optional, informational, and enforces nothing.

    `docs/02-extension-model.md`: "a disclosure to the operator, never a claim
    weft checks." Concrete strings, never booleans — a hostname is
    information, `network: true` is noise. Absence (no module-level
    `DISCLOSURE`) is reported by `doctor` as "not disclosed", which is honest;
    an empty `Disclosure()` asserts something the kernel cannot verify either,
    so this model exists to be read, never to gate anything.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    network: tuple[str, ...] = ()
    filesystem: tuple[str, ...] = ()
    subprocess: tuple[str, ...] = ()
    note: str = ""


@dataclass(frozen=True, slots=True)
class PipelineResource:
    """One pipeline document a pack ships from inside its own installed package.

    Task **2.8**. `weft_retrieve.contract.RouteCatalogue`'s own docstring: "populated by
    the same eager discovery pass that builds the registry, from the pipelines packs
    contribute — so a third party's pipeline becomes routable on install with no edit
    anywhere under `packages/`." `package` and `resource` are exactly
    `importlib.resources.files(package).joinpath(resource)`'s two arguments — a locator,
    never an opened file: the kernel still names no capability and opens nothing, the same
    restraint `weft_kernel.pipeline`'s own module docstring states for the `Pipeline`
    model itself ("the kernel publishes the model and opens no file"). Reading `resource`
    and parsing it as a pipeline document is `weft-cli`'s job — the one distribution that
    already owns `weft_cli.pipeline_catalogue`'s YAML parser.
    """

    distribution: str
    package: str
    resource: str


class RendererOffer(BaseModel):
    """One `(result type, renderer)` pair a pack offered, attributed to the pack that offered it.

    Task **6.20**, G13's third repair (`docs/03-cli.md` → *Plugin-contributed commands*): a
    result type nobody outside the CLI can format is only half a `Command` contract, so a
    renderer is registered at the same seam a command is — `PackRegistrar.add_renderer`
    buffers this, exactly as `add_ext_model` buffers a bare class reference. **The kernel
    names neither of the two `weft-command` types involved** — not `weft_command.contract.
    CommandResult`, the type a real `result_type` will always actually be, and not
    `weft_command.render.Rendered`, the type a real `render` will always actually return: it
    remembers only that this pack offered *some* type and *some* callable, and goes no
    further. Turning the buffer into something a renderer dispatch can actually use is
    `weft_cli.render.register_renderers_from_reports`'s job, run once every report is final.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    distribution: str
    result_type: type[object]
    render: Callable[[object], object]


class PackReport(BaseModel):
    """One pack's discovery outcome — the row `weft plugins list|doctor` will print.

    `pack` is the pack's identity — its `weft.packs` **entry-point name** (`chunk =
    "weft_chunk:register"` names the pack `chunk`), which is what every operator-facing
    surface prints and what a `[packs.<pack>]` settings block keys on. `distribution` is a
    different fact: the thing PyPI installs, which is what the `[packs] allow` trust
    boundary, `weft plugins doctor`'s version column and `weft_cli.skew` all key on. They
    were the same string while every pack shipped in a distribution of its own; they stopped
    being the same the moment one distribution shipped fourteen packs, and a report that
    carried only the second could no longer tell fourteen rows apart.

    `pack` is `None` for exactly one row: `ALLOWED_NOT_INSTALLED`, where `[packs] allow`
    named a distribution nothing installed claims. There is no entry point, so there is no
    pack — said out loud rather than filled in with the distribution name, which would
    assert a pack that does not exist.

    `ambient` is only ever meaningful on `ACTIVE`: it means "running, and not
    a direct dependency" (`docs/02-extension-model.md`), which `discover()`
    can only judge when its caller supplies `direct_dependencies` — the
    dependency graph itself lives outside the kernel, in whatever built the
    project manifest. Left `None`-less and `False` by default rather than a
    tri-state, because "cannot determine" is exactly what an absent
    `direct_dependencies` already means to a caller that asked for it.

    `pipeline_resources` is empty for every pack until task 2.8, and empty for any pack
    that never calls `PackRegistrar.add_pipeline_resource` — most packs ship no pipeline
    at all, and requiring an empty declaration from every one of them would be a
    registration tax with no failure behind it, `weft_enhance.contract`'s own declining
    argument for `destroys` applied here to a different field.

    `deprecations` — task 5.2e — is every `weft_kernel.seam.Deprecation` the pack buffered
    through `PackRegistrar.deprecate`, empty for every pack that never calls it. `docs/
    02-extension-model.md` §2's status vocabulary gains no member for this: `weft plugins
    doctor` reads a non-empty tuple as a flag beside `status`, the same way it already
    reads `ambient`, never as a status of its own — `docs/09-release.md` §3, "a flag on
    an existing status... no new status."

    `ext_models` — task 5.2g — is every `weft_kernel.payload.ext.ExtModel` subclass the pack
    buffered through `PackRegistrar.add_ext_model`, empty for any pack that ships no
    namespaced extension data (most packs). This is the *declared* half of fitness function
    14's runtime property; `weft_store.rehydrate.register_from_reports` reads it back off
    every report to compute the *present* half.

    `contributions` — task 5.3a — is every `weft_kernel.resolution.Contribution` the pack
    buffered through `PackRegistrar.add_contribution`, empty for any pack that offers no
    slot contribution (most packs). `weft_cli.registry_bootstrap.build_dependencies` is the
    one place every report's own tuple is concatenated into the `contributions=` argument
    every `weft_kernel.resolution.resolve` call site now passes — `02` §3 → *Slots*: "a pack
    may... contribute into a slot a pipeline opted into."

    `renderers` — task **6.20**, G13 — is every `RendererOffer` the pack buffered through
    `PackRegistrar.add_renderer`, empty for any pack that contributes no `Command` result a
    person needs formatted (most packs). `weft_cli.render.register_renderers_from_reports`
    is the one place every report's own tuple is read back off and made reachable for
    dispatch — the identical shape `ext_models` and `weft_store.rehydrate.
    register_from_reports` already have, one surface over.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    pack: str | None
    distribution: str
    status: PackStatus
    ambient: bool = False
    contributed: int = 0
    reason: str | None = None
    disclosure: Disclosure | None = None
    pipeline_resources: tuple[PipelineResource, ...] = ()
    deprecations: tuple[Deprecation, ...] = ()
    unavailable: tuple[Unavailable, ...] = ()
    ext_models: tuple[type[ExtModel], ...] = ()
    contributions: tuple[Contribution, ...] = ()
    renderers: tuple[RendererOffer, ...] = ()


class PackSettingsError(WeftError):
    """A pack's settings could not be built: wrong `register()` shape, or validation failed.

    Raised before `register()` ever runs — `docs/02-extension-model.md`: "the
    kernel validates before `register` is called and fails naming the pack
    and the field." Inside `discover()` this is caught and folded into a
    `FAILED` report rather than propagated, for the same reason a raising
    `register()` is: one broken pack must not stop every other pack from
    loading. Raised directly (uncaught) when the resolution helpers are
    exercised on their own.
    """


class EnvInterpolationError(WeftError):
    """`${env:VAR}` named an environment variable this process does not have set.

    Never resolves to an empty string instead — a silently-empty secret is a
    credential that looks like it works and is not, which is a worse failure
    than refusing to start.
    """


class InertPluginPinError(WeftError):
    """A `[plugins]` pin never got the chance to arbitrate anything, once discovery finished.

    `docs/02-extension-model.md` §3: "a pin for a pair that has no collision"
    must fail loudly rather than being read as a harmless no-op — "an inert
    pin is a lie about what is running." Raised here, after every entry
    point has been enumerated and every permitted pack activated, off
    `weft_kernel.registry.Registry.unconsulted_pins()` — the same shape as
    `UnknownPackSettingsError` just above: not folded into any one pack's
    report, because this is not one pack's failure, it is the configuration
    naming a fight that never happened. Distinct from
    `weft_kernel.registry.UnresolvedPluginPinError`, which fires *during* a
    real collision when the pin names neither side of it; this one fires
    when no collision for the pinned key ever occurred at all.

    Repair for a reviewer finding: this used to be unconditionally fatal to
    every registry-needing command, `weft plugins doctor` and `weft plugins
    list` included — the two commands whose whole job is explaining what is
    installed, one of which `manual/troubleshooting.md`'s own remedy for this
    exact error names as the next thing to run. `discover`'s `strict_pins`
    parameter is what a diagnostic caller sets `False` to see every
    `PackReport` anyway; `weft_cli.cli.dispatch` does this for `plugins
    list`/`plugins doctor` and no other command, on the same reasoning
    `weft_cli.registry_bootstrap`'s own module docstring already gives for
    `WEFT_DATABASE_URL`: "a bare crash on every registry-needing command —
    including `plugins doctor`, the one command meant to diagnose exactly
    this — would be worse than" a report.
    """


class UnknownPackSettingsError(WeftError, UnresolvedNameError):
    """A `packs:` settings key names a pack no installed `weft.packs` entry point claims.

    Raised by `discover()` itself, after every entry point has been
    enumerated — never caught and folded into a `PackReport`, because this is
    not one pack failing; it is the configuration asking for a pack that is
    not there at all. `docs/02-extension-model.md`: "A `packs:` key naming a
    pack that is not installed is an error... loud, naming the distribution
    to install." Keyed on the **pack** — the entry-point name — since `02` §2's
    settings block is `[packs.store]`, not `[packs.store]`: several packs may
    ship in one distribution, and each configures itself. This is the strict half
    of the `allow`/`packs:` asymmetry — `allow` naming an absent distribution is
    `ALLOWED_NOT_INSTALLED`, reported and not fatal, because `allow` only ever
    narrows what is already there; `packs:` names a requirement, and an unmet
    requirement raises.

    Fitness function 12's family: `valid_options` is every pack that does declare
    a `weft.packs` entry point.
    """

    def __init__(self, message: str, *, valid_options: tuple[str, ...]) -> None:
        super().__init__(message)
        self.valid_options = valid_options


class MalformedDisclosureError(WeftError):
    """A pack's module-level `DISCLOSURE` is present but is not a `Disclosure` instance.

    Distinct from absence: `docs/02-extension-model.md` calls "not
    disclosed" honest reporting of a pack that disclosed nothing, and that
    honesty breaks if a pack that *tried* to disclose something malformed —
    a bare dict, a `Disclosure` from an incompatible version — is reported
    identically. Folded into a `FAILED` report by `_activate`, naming the
    distribution and what `DISCLOSURE` must be, rather than propagated.
    """


class MissingDistributionMetadataError(WeftError):
    """An entry point in the `weft.packs` group carries no distribution metadata.

    Folded into a `FAILED` report keyed by the entry point's own name, the
    same way an import failure or a raising `register()` is — one malformed
    `.dist-info` degrades to a single row, not a hard stop for every other
    installed pack.
    """


class _DistributionLike(Protocol):
    """The one attribute `discover()` needs from `importlib.metadata`'s distribution object."""

    @property
    def name(self) -> str: ...


class EntryPointLike(Protocol):
    """The slice of `importlib.metadata.EntryPoint` `discover()` actually uses.

    A `Protocol` rather than the concrete class so a test can hand `discover()`
    a lightweight double instead of an installed distribution — real
    `EntryPoint` objects already satisfy this structurally, with nothing to
    subclass or register.
    """

    @property
    def name(self) -> str: ...
    @property
    def module(self) -> str: ...
    @property
    def dist(self) -> _DistributionLike | None: ...
    def load(self) -> Callable[..., None]: ...


class PackRegistrar:
    """The registry view a pack's own `register()` receives — see the module docstring.

    `Registry.add` minus its keyword-only `distribution` parameter: a pack
    author calls `registrar.add(contract, name, factory)`, exactly the shape
    `docs/02-extension-model.md` shows, and attribution is filled in from
    whichever distribution `discover()` is currently importing — never
    something the author states, and never something the author could get
    wrong.
    """

    def __init__(self, registry: Registry, *, distribution: str) -> None:
        self._registry = registry
        self._distribution = distribution
        self._pending: list[tuple[type[object], str, Callable[..., object]]] = []
        self._pending_resources: list[PipelineResource] = []
        self._pending_deprecations: list[Deprecation] = []
        self._pending_unavailable: list[Unavailable] = []
        self._pending_ext_models: list[type[ExtModel]] = []
        self._pending_contributions: list[Contribution] = []
        self._pending_renderers: list[RendererOffer] = []

    @property
    def contributed(self) -> int:
        """How many registrations this pack has buffered — and, after `commit`, has landed."""
        return len(self._pending)

    def add(self, contract: type[object], name: str, factory: Callable[..., object]) -> None:
        """Buffer `factory` as `name` for `contract`, attributed to this pack.

        Nothing reaches the shared `Registry` yet — see `commit`. A pack's
        own `register()` never calls `commit` itself; `_activate` does, once
        `register()` has returned without raising.
        """
        self._pending.append((contract, name, factory))

    def add_pipeline_resource(self, package: str, resource: str) -> None:
        """Buffer a `PipelineResource(distribution, package, resource)`, attributed to this pack.

        Task **2.8**. Buffered exactly like `add` — see `commit` — and for the identical
        reason: a pack whose `register()` raises after calling this must not leave a
        catalogue advertising a pipeline it never actually shipped. A pack calls this once
        per pipeline document it ships, typically its own package name and a
        `pipelines/<name>.yaml` resource path — `weft_cli.pipeline_catalogue.
        load_contributed` is what turns the buffered locator into a parsed `Pipeline`.
        """
        self._pending_resources.append(
            PipelineResource(distribution=self._distribution, package=package, resource=resource)
        )

    def deprecate(self, surface: str, *, reason: str) -> None:
        """Mark `surface` — a plugin name, a `"Contract:name"` pair, or the pack itself —
        deprecated, attributed to this pack.

        Task 5.2e. Buffered exactly like `add_pipeline_resource`, for the identical reason:
        a pack whose `register()` raises after calling this must not leave a warning
        standing about a mark that never actually committed. Marking is all this method
        does — the warning itself is `weft_kernel.seam.warn_deprecated`'s job, run by
        `_activate` once `register()` has returned without raising, so a pack author states
        the fact once and never writes the warning by hand; see that function's own
        docstring for why the notice is a `DeprecationWarning`, not a `WeftError`.
        """
        self._pending_deprecations.append(
            Deprecation(
                distribution=self._distribution,
                surface=surface,
                reason=reason,
                removal=removal_for(self._distribution),
            )
        )

    def unavailable(self, surface: str, *, reason: str) -> None:
        """Declare that this pack cannot provide `surface`, and why — ledger task **6.29**.

        `01` → *Fitness functions* 5's second half: a capability that does not resolve to a live
        implementation must be *declared unavailable at discovery time*, with a reason. Calling
        this makes the pack's report `PackStatus.PARTIAL` — `02` §2's own word for "registered,
        but a conditional dependency it wanted was not available, so part of what it offers did
        not" — so `weft plugins doctor` says it before a run does.

        Buffered exactly like `deprecate`, for the identical reason: a pack whose `register()`
        raises after calling this must not leave a report standing about a mark that never
        committed. Registering nothing else and declaring one surface unavailable is a perfectly
        ordinary pack; what it must never be is silent.
        """
        self._pending_unavailable.append(
            Unavailable(distribution=self._distribution, surface=surface, reason=reason)
        )

    def add_ext_model(self, model: type[ExtModel]) -> None:
        """Buffer `model` — a pack's own `ExtModel` subclass — attributed to this pack.

        Task **5.2g**. Buffered exactly like `add_pipeline_resource` and `deprecate`, for
        the identical reason: a pack whose `register()` raises after calling this must not
        leave a namespace looking claimed that never actually committed. `model` is a bare
        class reference, not an instance — nothing here validates, instantiates or reads
        `model.__namespace__`; this method only remembers that this pack offered it.
        Turning the buffer into an entry `weft_store.rehydrate.rehydrate_ext` can actually
        use is `weft_store.rehydrate.register_from_reports`'s job, run once every report is
        final — the kernel names no capability, so it stops at "this pack declared this
        class" and goes no further.
        """
        self._pending_ext_models.append(model)

    def add_contribution(self, slot: str, stage: StageDeclaration) -> None:
        """Offer `stage` into `slot` of whichever pipeline declares it, attributed to this pack.

        Task **5.3a** (`S8`). Buffered exactly like `add_ext_model`, for the identical reason:
        a pack whose `register()` raises after calling this must not leave a slot looking
        filled that was never actually committed. `distribution` — `weft_kernel.resolution.
        Contribution`'s own required field — is filled in from this registrar, on `add`'s own
        footing: attribution is never something a pack author states, or could misattribute to
        a distribution that is not its own. `stage.id` is the contribution's own **local**
        name, unqualified by distribution — `Contribution`'s own docstring, and `02` §3 →
        *Slots*: qualification happens only once a contribution is actually placed. This
        method validates nothing about `slot` itself: a slot no installed pipeline declares is
        `02` §3's own "recorded no-op", not a registration-time refusal — `weft_kernel.
        resolution.resolve` is where that distinction is actually drawn.
        """
        self._pending_contributions.append(
            Contribution(slot=slot, distribution=self._distribution, stage=stage)
        )

    def add_renderer(self, result_type: type[object], renderer: Callable[[object], object]) -> None:
        """Offer `renderer` for `result_type`, attributed to this pack.

        Task **6.20**, G13's third repair. Buffered exactly like `add_ext_model` and
        `add_contribution`, for the identical reason: a pack whose `register()` raises after
        calling this must not leave a result type looking renderable that never actually
        committed. `distribution` is filled in from this registrar, on `add`'s own footing —
        attribution is never something a pack author states. This method validates nothing
        about `result_type` or `renderer`: it does not know either is a `weft_command.
        contract.CommandResult` subclass or a `weft_command.render.Rendered`-returning
        callable — the kernel names neither type, exactly as the module docstring's own
        rule requires. Turning the buffer into a working dispatch is `weft_cli.render.
        register_renderers_from_reports`'s job.
        """
        self._pending_renderers.append(
            RendererOffer(distribution=self._distribution, result_type=result_type, render=renderer)
        )

    def commit(self) -> None:
        """Write every buffered registration to the `Registry`, all at once or not at all.

        Delegates to `Registry.add_many`, which is what makes this atomic —
        see the module docstring. Called by `_activate` exactly once, after
        a pack's `register()` returns without raising; never called at all
        if `register()` raises, which is what keeps a half-registered pack
        from ever being written.
        """
        self._registry.add_many(self._pending, distribution=self._distribution)

    @property
    def pipeline_resources(self) -> tuple[PipelineResource, ...]:
        """Every `PipelineResource` this pack has buffered so far — `_activate`'s own read,
        once `register()` has returned without raising. See `add_pipeline_resource`.
        """
        return tuple(self._pending_resources)

    @property
    def deprecations(self) -> tuple[Deprecation, ...]:
        """Every `Deprecation` this pack has buffered so far — `_activate`'s own read, once
        `register()` has returned without raising. See `deprecate`.
        """
        return tuple(self._pending_deprecations)

    @property
    def unavailable_surfaces(self) -> tuple[Unavailable, ...]:
        """Every `Unavailable` this pack has buffered so far — `_activate`'s own read, once
        `register()` has returned without raising. See `unavailable`.
        """
        return tuple(self._pending_unavailable)

    @property
    def ext_models(self) -> tuple[type[ExtModel], ...]:
        """Every `ExtModel` subclass this pack has buffered so far — `_activate`'s own read,
        once `register()` has returned without raising. See `add_ext_model`.
        """
        return tuple(self._pending_ext_models)

    @property
    def contributions(self) -> tuple[Contribution, ...]:
        """Every `Contribution` this pack has buffered so far — `_activate`'s own read, once
        `register()` has returned without raising. See `add_contribution`.
        """
        return tuple(self._pending_contributions)

    @property
    def renderers(self) -> tuple[RendererOffer, ...]:
        """Every `RendererOffer` this pack has buffered so far — `_activate`'s own read, once
        `register()` has returned without raising. See `add_renderer`.
        """
        return tuple(self._pending_renderers)


def interpolate_env(value: object, *, environ: Mapping[str, str] | None = None) -> object:
    """Recursively resolve every `${env:VAR}` string in `value` against `environ`.

    `docs/02-extension-model.md`: "`${env:VAR}` interpolation [is] performed
    by the config loader, so no component reads the environment itself" —
    this is that interpolation, and the only place in the kernel that reads
    `os.environ` by default. A string that is *exactly* `${env:VAR}` becomes
    the variable's value; a string that merely contains the token as a
    substring is left untouched, because partial substitution inside a
    longer string is a template engine this project does not have and does
    not need for a credential or an endpoint. Walks `dict` and `list`
    recursively so a whole settings block can be interpolated in one call;
    every other type passes through unchanged. Raises `EnvInterpolationError`,
    naming the variable, rather than substituting an empty string, if it is
    unset.
    """
    env = os.environ if environ is None else environ
    return _interpolate(value, env)


def _interpolate(value: object, env: Mapping[str, str]) -> object:
    if isinstance(value, str):
        match = _ENV_TOKEN.match(value)
        if match is None:
            return value
        name = match.group(1)
        if name not in env:
            raise EnvInterpolationError(
                f"'${{env:{name}}}' names an environment variable that is not set. Set "
                f"{name}, or remove the reference from the configuration."
            )
        return env[name]
    if isinstance(value, Mapping):
        items = cast("Mapping[str, object]", value)
        return {key: _interpolate(item, env) for key, item in items.items()}
    if isinstance(value, list):
        entries = cast("list[object]", value)
        return [_interpolate(item, env) for item in entries]
    return value


def allow_list_from_config(document: Mapping[str, object]) -> tuple[str, ...] | None:
    """The exhaustive pin from a parsed `weft.toml`-shaped mapping's `[packs] allow`.

    `None` means absent, which `docs/02-extension-model.md` states plainly:
    "`weft.toml` — optional. Absent means open." Present but empty
    (`allow = []`) is a real, if severe, policy — refuse every pack — and is
    returned as `()`, never coerced to `None`: the two mean different things
    and this function does not collapse them.

    **A `packs` key that is present but not a table is refused, not absorbed
    into absence.** `docs/02` §2's *The trust model*:
    `packs = ["weft-store"]` is the plausible typo for `[packs]\\nallow =
    [...]` — TOML parses it to a `list`, and a bare `isinstance(packs,
    Mapping)` guard used to fail that check the same way a genuinely absent
    `packs` does, silently landing on open-by-default with the operator's
    allow-list never read. `None` only for a key that is not in `document`
    at all; anything present that is not a `Mapping` raises `WeftError`
    naming the shape found and the shape expected, so the typo is loud
    instead of a policy that quietly never applied. `allow = []` inside a
    *valid* `[packs]` table is unaffected — that case reaches the check
    below unchanged, and stays "refuse every pack", not this one.
    """
    if "packs" not in document:
        return None
    packs = document["packs"]
    if not isinstance(packs, Mapping):
        raise WeftError(
            f"weft.toml's [packs] must be a table, not {type(packs).__name__} — found "
            f"`packs = {packs!r}`. Did you mean `[packs]\\nallow = [...]`? See "
            f"docs/02-extension-model.md section 2, The trust model."
        )
    packs_table = cast("Mapping[str, object]", packs)
    allow = packs_table.get("allow")
    if allow is None:
        return None
    if not isinstance(allow, list):
        raise WeftError(
            f"[packs] allow must be a list of distribution names (strings); found "
            f"{type(allow).__name__}."
        )
    entries = cast("list[object]", allow)
    if not all(isinstance(item, str) for item in entries):
        raise WeftError("[packs] allow must be a list of distribution names (strings).")
    return tuple(cast("list[str]", entries))


def plugin_pins_from_config(document: Mapping[str, object]) -> dict[str, str]:
    """The exhaustive `[plugins]` table from a parsed `weft.toml`-shaped mapping.

    `docs/02-extension-model.md` §3's exact shape — `"Enhancer:keybert" =
    "weft-kw"` — a `{"Contract:name": "distribution"}` mapping handed
    straight to `weft_kernel.registry.Registry(plugin_pins=...)`, never
    interpreted here: this function's whole job is the same one
    `allow_list_from_config` already does for `[packs] allow`, turning a
    piece of an already-parsed mapping into the shape the kernel accepts,
    with no file ever opened by this module. Absent `[plugins]` returns
    `{}` — "absent means open" is `[packs] allow`'s reading; here it means
    no pin exists, so every collision still refuses exactly as it always
    has. A key naming no real `(contract, name)` collision is not caught
    here — that is `weft_kernel.discovery.discover`'s `InertPluginPinError`,
    raised only once discovery knows what actually collided.
    """
    plugins = document.get("plugins")
    if not isinstance(plugins, Mapping):
        return {}
    table = cast("Mapping[str, object]", plugins)
    if not all(isinstance(value, str) for value in table.values()):
        raise WeftError('[plugins] must map "Contract:name" strings to distribution-name strings.')
    return {str(key): cast("str", value) for key, value in table.items()}


def discover(
    registry: Registry,
    *,
    allow: Collection[str] | None = None,
    pack_settings: Mapping[str, Mapping[str, object]] | None = None,
    direct_dependencies: Collection[str] | None = None,
    entry_points: Iterable[EntryPointLike] | None = None,
    strict_pins: bool = True,
) -> tuple[PackReport, ...]:
    """Discover every installed `weft.packs` pack, importing and registering what is permitted.

    `allow` is keyed on the **distribution**, not the pack: it is a trust
    boundary, and trust attaches to the thing you installed from an index, not
    to a name chosen inside a wheel you had already accepted.

    `allow=None` is the open-by-default posture: everything installed is
    imported and registered. `allow` present is an exhaustive pin — anything
    installed but unlisted is `REFUSED` **and its entry point is never
    loaded**, which is fitness function 8(a): refusal precedes execution, not
    a `try` block around it. Every name in `allow` that no installed
    distribution claims comes back as `ALLOWED_NOT_INSTALLED`, reported, not
    fatal — `docs/02-extension-model.md`'s distinction between a permission
    (`allow`) and a requirement (`packs:` settings, which errors on the same
    absence).

    `pack_settings` is keyed on the **pack** — the `weft.packs` entry-point name,
    so `[packs.store]` and not `[packs.store]`. It is interpolated for
    `${env:VAR}` once, up front, then
    each pack's own slice is validated against the Pydantic model its
    `register(registrar, settings: Settings)` declares — before `register` is
    called. `direct_dependencies`, when supplied, is what lets an `ACTIVE`
    report carry `ambient=True`; the dependency graph itself is not this
    module's to compute.

    Every `pack_settings` key that no enumerated entry point claims raises
    `UnknownPackSettingsError`, naming the pack and every pack that did declare a
    `weft.packs` entry point — `packs:` expresses a requirement, unlike `allow`,
    so this is fatal where `ALLOWED_NOT_INSTALLED` is not.

    `entry_points` defaults to every real, installed `weft.packs` entry
    point; a caller passes its own only to test discovery without installing
    a distribution.

    `strict_pins=False` — repair for a reviewer finding against the task 1.12
    commit — skips the `InertPluginPinError` check below rather than raising
    it, so a caller whose whole job is *explaining* the environment (`weft
    plugins list`/`doctor`) can still get every `PackReport` back even when a
    `[plugins]` pin never arbitrated anything. Every other caller keeps the
    default `True`: `registry.unconsulted_pins()` is unaffected either way —
    a `plugins doctor` caller passing `strict_pins=False` can still read it
    off the registry it was handed back and report it, rather than losing
    the information the way a raised exception discarding every built
    `PackReport` would.
    """
    candidates: list[EntryPointLike] = (
        list(entry_points)
        if entry_points is not None
        # `importlib.metadata.EntryPoint` satisfies this protocol at runtime — every
        # attribute `EntryPointLike` names is present — but its typeshed stub mixes
        # plain fields and properties in a way pyright's strict structural check
        # cannot verify statically. The cast bridges that one stdlib boundary; it
        # asserts nothing this module does not already rely on being true.
        else cast("list[EntryPointLike]", list(metadata.entry_points(group=ENTRY_POINT_GROUP)))
    )
    allow_set = set(allow) if allow is not None else None
    settings_source = _as_settings_source(interpolate_env(dict(pack_settings or {})))

    reports: list[PackReport] = []
    seen: set[str] = set()
    seen_packs: set[str] = set()

    for entry_point in candidates:
        # The pack's own identity, and never the distribution's: an entry-point name is
        # unique within the group and stays the pack's own even when fourteen packs ship
        # in one wheel. Read before `_distribution_name`, because it is available even
        # when distribution metadata is not.
        pack = entry_point.name
        try:
            distribution = _distribution_name(entry_point)
        except MissingDistributionMetadataError as exc:
            # No distribution name means no attribution for the trust boundary and no
            # version to report — fold into FAILED, keyed by the entry point's own name,
            # rather than aborting discovery for every other pack. The pack identity is
            # intact here; it is the distribution that is missing.
            reports.append(
                PackReport(
                    pack=pack,
                    distribution=entry_point.name,
                    status=PackStatus.FAILED,
                    reason=str(exc),
                )
            )
            continue
        seen.add(distribution)
        seen_packs.add(pack)

        # `allow` stays keyed on the **distribution**, deliberately. It is a trust
        # boundary, and trust is placed in a thing you install from an index and can pin,
        # audit and revoke — not in a name a pack chose for itself inside a wheel you had
        # already accepted. `[packs] allow = ["weft-rag"]` therefore permits every pack
        # that wheel ships, which is the same posture as before: what you installed is
        # what you allowed. `[packs.<pack>]` settings key on `pack` instead, because that
        # is configuration of one pack's behaviour, not a decision about provenance.
        if allow_set is not None and distribution not in allow_set:
            reports.append(
                PackReport(
                    pack=pack,
                    distribution=distribution,
                    status=PackStatus.REFUSED,
                    reason=(
                        f"'{distribution}' is not listed in [packs] allow. Add it there to "
                        f"permit it."
                    ),
                )
            )
            continue

        reports.append(
            _activate(
                entry_point,
                pack=pack,
                distribution=distribution,
                registry=registry,
                raw_settings=settings_source.get(pack, {}),
                direct_dependencies=direct_dependencies,
            )
        )

    if allow_set is not None:
        for missing in sorted(allow_set - seen):
            reports.append(
                PackReport(pack=None, distribution=missing, status=PackStatus.ALLOWED_NOT_INSTALLED)
            )

    unclaimed = sorted(set(settings_source) - seen_packs)
    if unclaimed:
        named = ", ".join(f"'{name}'" for name in unclaimed)
        options = tuple(sorted(seen_packs))
        available = ", ".join(f"'{name}'" for name in options) or "none"
        raise UnknownPackSettingsError(
            f"[packs] settings name {named}, which {'is' if len(unclaimed) == 1 else 'are'} "
            f"not installed. Install the distribution that ships it, or remove its settings "
            f"block. Packs that declare a '{ENTRY_POINT_GROUP}' entry point: {available}.",
            valid_options=options,
        )

    # Every pack that was going to collide with anyone already has, since every candidate
    # above has been activated (or refused, or reported missing) by this point — so a pin
    # `registry` was given that `Registry.unconsulted_pins()` still lists never arbitrated a
    # real collision at all. `docs/02-extension-model.md` §3: "an inert pin is a lie about
    # what is running." Raised here, not folded into any one pack's report — see
    # `InertPluginPinError`'s own docstring for why. Skipped, not silenced, when
    # `strict_pins` is `False`: the state is still sitting on `registry.unconsulted_pins()`
    # for a caller that asked not to have it be fatal to read.
    if strict_pins:
        unconsulted = sorted(registry.unconsulted_pins())
        if unconsulted:
            named = ", ".join(f"'{pin}'" for pin in unconsulted)
            raise InertPluginPinError(
                f"[plugins] pins {named}, but weft never saw two distributions contend for "
                f"what {'it names' if len(unconsulted) == 1 else 'they name'} — nothing to "
                f"arbitrate. Remove the pin, or check that both distributions it should choose "
                f"between are installed and actually registering that name."
            )

    return tuple(reports)


def _activate(
    entry_point: EntryPointLike,
    *,
    pack: str,
    distribution: str,
    registry: Registry,
    raw_settings: Mapping[str, object],
    direct_dependencies: Collection[str] | None,
) -> PackReport:
    """Import one permitted pack, validate its settings, call `register()`, and report.

    Registration is transactional: `registrar.commit()` — which is what
    actually writes to `registry` — runs *inside* the same `try` as
    `register()` itself, so a pack that raises, whether from `register()` or
    from a collision `commit()` discovers, is caught by the same branch and
    reported with `contributed=0` by default, which is true precisely because
    nothing was written. Only a `register()` that returns and then commits
    cleanly reaches `ACTIVE`, where `contributed=registrar.contributed`
    reports what actually landed.

    **Task 5.2e** — a clean commit is also the one point `registrar.deprecations`
    is known to have actually landed, so this is where `weft_kernel.seam.warn_deprecated`
    is called: once, with whatever the pack buffered, never for a pack that raised.

    **Task 5.2g** — `registrar.ext_models` reaches `PackReport.ext_models` on the identical
    terms: only once `register()` has returned and `commit()` has not raised. This function
    does nothing else with it — reading the buffer back off every final report and making
    the classes it names reachable for rehydration is `weft_store.rehydrate.
    register_from_reports`'s job, run by whatever calls `discover()`.

    **Task 5.3a** — `registrar.contributions` reaches `PackReport.contributions` on the
    identical terms, for the identical reason: a pack that raises must never look like it
    offered a slot contribution it never actually committed. This function does nothing else
    with it either — assembling every report's own tuple into one `contributions=` argument
    for `weft_kernel.resolution.resolve` is `weft_cli.registry_bootstrap.build_dependencies`'s
    job, the one caller `weft_kernel.resolution.Contribution`'s own docstring names.

    **Task 6.20** — `registrar.renderers` reaches `PackReport.renderers` on the identical
    terms: only once `register()` has returned and `commit()` has not raised. A `register()`
    that raises after calling `add_renderer` leaves `renderers == ()`, the same atomicity
    every other buffer already has — the CLI must never advertise a way to format a result a
    pack never actually finished offering.
    """
    ambient = direct_dependencies is not None and distribution not in direct_dependencies

    try:
        register_fn = entry_point.load()
    except Exception as exc:  # a pack's import can raise anything; that is FAILED, not a crash
        return PackReport(
            pack=pack, distribution=distribution, status=PackStatus.FAILED, reason=str(exc)
        )

    try:
        disclosure = _read_disclosure(entry_point, pack=pack)
    except MalformedDisclosureError as exc:
        return PackReport(
            pack=pack, distribution=distribution, status=PackStatus.FAILED, reason=str(exc)
        )

    registrar = PackRegistrar(registry, distribution=distribution)
    try:
        settings = _resolve_settings(register_fn, pack=pack, raw=raw_settings)
        register_fn(registrar, settings)
        registrar.commit()
    except Exception as exc:  # one broken pack must not stop the rest from loading
        return PackReport(
            pack=pack,
            distribution=distribution,
            status=PackStatus.FAILED,
            ambient=ambient,
            reason=str(exc),
            disclosure=disclosure,
        )

    deprecations = registrar.deprecations
    warn_deprecated(deprecations)

    unavailable = registrar.unavailable_surfaces

    return PackReport(
        pack=pack,
        distribution=distribution,
        # Task **6.29**: a pack that declared any surface unavailable registered *part* of what it
        # offers, which is exactly what `02` §2 reserves `PARTIAL` for. `ACTIVE` would say it is
        # contributing everything it has, and `FAILED` would say it contributed nothing — both
        # false, and the reason the vocabulary has a third word.
        status=PackStatus.PARTIAL if unavailable else PackStatus.ACTIVE,
        ambient=ambient,
        contributed=registrar.contributed,
        disclosure=disclosure,
        pipeline_resources=registrar.pipeline_resources,
        deprecations=deprecations,
        unavailable=unavailable,
        ext_models=registrar.ext_models,
        contributions=registrar.contributions,
        renderers=registrar.renderers,
    )


def _read_disclosure(entry_point: EntryPointLike, *, pack: str) -> Disclosure | None:
    """The pack's module-level `DISCLOSURE`, read after import, before `register()` runs.

    `None` means genuinely absent — no `DISCLOSURE` attribute at all — which
    is the honest "not disclosed" `docs/02-extension-model.md` describes.
    Present but not a `Disclosure` instance is a different fact and is never
    collapsed into that same `None`: it raises `MalformedDisclosureError`,
    naming the pack and what the attribute must be, so the caller can
    fold it into a `FAILED` report instead of reporting a pack that tried to
    disclose something as one that disclosed nothing.
    """
    module = sys.modules.get(entry_point.module)
    value = getattr(module, "DISCLOSURE", None) if module is not None else None
    if value is None:
        return None
    if isinstance(value, Disclosure):
        return value
    raise MalformedDisclosureError(
        f"'{pack}' defines DISCLOSURE but it is not a "
        f"weft_kernel.discovery.Disclosure instance (found {type(value).__name__}). "
        f"DISCLOSURE must be built from Disclosure(network=..., filesystem=..., "
        f"subprocess=..., note=...)."
    )


def _resolve_settings(
    register_fn: Callable[..., None], *, pack: str, raw: Mapping[str, object]
) -> BaseModel:
    """The validated settings instance `register_fn`'s own model expects.

    Introspects `register_fn`'s second parameter for a `pydantic.BaseModel`
    subclass annotation — `docs/02-extension-model.md`'s own shape,
    `register(registry: Registry, settings: Settings) -> None` — and
    validates `raw` against it before `register_fn` is ever called. A pack
    with nothing to configure still declares an (empty) model; there is no
    settings-less shape to special-case.
    """
    parameters = list(inspect.signature(register_fn).parameters.values())
    if len(parameters) != 2:
        raise PackSettingsError(
            f"'{pack}' declares register() with {len(parameters)} parameter(s); "
            f"docs/02-extension-model.md requires exactly (registrar, settings)."
        )

    hints = get_type_hints(register_fn)
    model = hints.get(parameters[1].name)
    if not (isinstance(model, type) and issubclass(model, BaseModel)):
        raise PackSettingsError(
            f"'{pack}' does not annotate its settings parameter with a "
            f"pydantic.BaseModel subclass; register(registrar, settings: Settings) is required."
        )

    try:
        return model.model_validate(raw)
    except ValidationError as exc:
        raise PackSettingsError(f"'{pack}' settings failed validation: {exc}") from exc


def _distribution_name(entry_point: EntryPointLike) -> str:
    dist = entry_point.dist
    if dist is None:
        raise MissingDistributionMetadataError(
            f"entry point '{entry_point.name}' in group '{ENTRY_POINT_GROUP}' carries no "
            f"distribution metadata; weft cannot attribute it to a pack."
        )
    return dist.name


def _as_settings_source(value: object) -> Mapping[str, Mapping[str, object]]:
    """Narrow `interpolate_env`'s `object` return back to the shape `discover()` needs.

    `interpolate_env` is generic over any parsed config value, so its return
    type is `object`; `discover()` always feeds it a `dict[str, dict[str,
    object]]`, and gets exactly that back, since interpolation preserves
    container shape. This function states that fact once rather than
    scattering `cast` at every call site.
    """
    if not isinstance(value, dict):
        raise WeftError(f"pack settings must be a mapping; found {type(value).__name__}.")
    raw = cast("dict[str, object]", value)
    result: dict[str, Mapping[str, object]] = {}
    for key, item in raw.items():
        if not isinstance(item, Mapping):
            raise WeftError(
                f"pack settings for '{key}' must be a mapping; found {type(item).__name__}."
            )
        result[key] = cast("Mapping[str, object]", item)
    return result
