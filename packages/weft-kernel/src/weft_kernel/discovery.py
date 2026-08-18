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
said it wrong — so that case is `FAILED`, naming the distribution and what
the attribute must be, rather than silently read as "not disclosed."
Pack settings (`docs/02`'s `packs:` block, keyed by distribution name) are
validated against the pack's own Pydantic model *before* `register()` is
called, because a pack author's `register(registry, settings)` should never
have to guard against malformed input the kernel could have rejected first —
and `${env:VAR}` interpolation happens on that settings data here, so no pack
ever reads `os.environ` itself for a secret. A `packs:` key naming a
distribution nothing installed declares is the strict half of that same
model: `docs/02` states the asymmetry exactly — "`packs:` expresses a
requirement, `allow` expresses a permission" — so once every entry point is
enumerated, any settings key `seen` never claims raises, naming the
distribution to install and every distribution that did declare a
`weft.packs` entry point, rather than being read and quietly discarded.

**Registration is transactional per pack.** `PackRegistrar.add` buffers
every call instead of writing through to the `Registry` immediately; nothing
lands there until `register()` returns without raising, at which point the
whole buffer commits in one atomic step (`Registry.add_many`) or none of it
does. A pack that raises partway through therefore contributes exactly the
`0` its `FAILED` report claims — the report and the registry can never
disagree about how much of a half-finished pack is actually live.

**`PackRegistrar` exists because `distribution` is attribution, and
attribution is never a pack author's to supply** — `registry.py`'s own
docstring names this exact gap: "A pack's own `register()` calls the
seam-bound surface with `(contract, name, factory)`." This is that surface:
`Registry.add` minus its keyword-only `distribution` parameter, bound once
per pack by whatever called `discover()`, so a pack author writes
`registrar.add(Contract, "name", factory)` and never sees attribution at all.
"""

from __future__ import annotations

import inspect
import os
import re
import sys
from collections.abc import Callable, Collection, Iterable, Mapping
from enum import StrEnum
from importlib import metadata
from typing import Protocol, cast, get_type_hints

from pydantic import BaseModel, ConfigDict, ValidationError

from weft_kernel.errors import WeftError
from weft_kernel.registry import Registry

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


class PackReport(BaseModel):
    """One pack's discovery outcome — the row `weft plugins list|doctor` will print.

    `ambient` is only ever meaningful on `ACTIVE`: it means "running, and not
    a direct dependency" (`docs/02-extension-model.md`), which `discover()`
    can only judge when its caller supplies `direct_dependencies` — the
    dependency graph itself lives outside the kernel, in whatever built the
    project manifest. Left `None`-less and `False` by default rather than a
    tri-state, because "cannot determine" is exactly what an absent
    `direct_dependencies` already means to a caller that asked for it.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    distribution: str
    status: PackStatus
    ambient: bool = False
    contributed: int = 0
    reason: str | None = None
    disclosure: Disclosure | None = None


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


class UnknownPackSettingsError(WeftError):
    """A `packs:` settings key names a distribution no installed `weft.packs` entry point claims.

    Raised by `discover()` itself, after every entry point has been
    enumerated — never caught and folded into a `PackReport`, because this is
    not one pack failing; it is the configuration asking for a pack that is
    not there at all. `docs/02-extension-model.md`: "A `packs:` key naming a
    pack that is not installed is an error... loud, naming the distribution
    to install." This is the strict half of the `allow`/`packs:` asymmetry —
    `allow` naming an absent distribution is `ALLOWED_NOT_INSTALLED`,
    reported and not fatal, because `allow` only ever narrows what is already
    there; `packs:` names a requirement, and an unmet requirement raises.
    """


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

    def commit(self) -> None:
        """Write every buffered registration to the `Registry`, all at once or not at all.

        Delegates to `Registry.add_many`, which is what makes this atomic —
        see the module docstring. Called by `_activate` exactly once, after
        a pack's `register()` returns without raising; never called at all
        if `register()` raises, which is what keeps a half-registered pack
        from ever being written.
        """
        self._registry.add_many(self._pending, distribution=self._distribution)


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
    """
    packs = document.get("packs")
    if not isinstance(packs, Mapping):
        return None
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


def discover(
    registry: Registry,
    *,
    allow: Collection[str] | None = None,
    pack_settings: Mapping[str, Mapping[str, object]] | None = None,
    direct_dependencies: Collection[str] | None = None,
    entry_points: Iterable[EntryPointLike] | None = None,
) -> tuple[PackReport, ...]:
    """Discover every installed `weft.packs` pack, importing and registering what is permitted.

    `allow=None` is the open-by-default posture: everything installed is
    imported and registered. `allow` present is an exhaustive pin — anything
    installed but unlisted is `REFUSED` **and its entry point is never
    loaded**, which is fitness function 8(a): refusal precedes execution, not
    a `try` block around it. Every name in `allow` that no installed
    distribution claims comes back as `ALLOWED_NOT_INSTALLED`, reported, not
    fatal — `docs/02-extension-model.md`'s distinction between a permission
    (`allow`) and a requirement (`packs:` settings, which errors on the same
    absence).

    `pack_settings` is interpolated for `${env:VAR}` once, up front, then
    each pack's own slice is validated against the Pydantic model its
    `register(registrar, settings: Settings)` declares — before `register` is
    called. `direct_dependencies`, when supplied, is what lets an `ACTIVE`
    report carry `ambient=True`; the dependency graph itself is not this
    module's to compute.

    Every `pack_settings` key that no enumerated entry point claims raises
    `UnknownPackSettingsError`, naming the distribution to install and every
    distribution that did declare a `weft.packs` entry point — `packs:`
    expresses a requirement, unlike `allow`, so this is fatal where
    `ALLOWED_NOT_INSTALLED` is not.

    `entry_points` defaults to every real, installed `weft.packs` entry
    point; a caller passes its own only to test discovery without installing
    a distribution.
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

    for entry_point in candidates:
        try:
            distribution = _distribution_name(entry_point)
        except MissingDistributionMetadataError as exc:
            # No distribution name means no attribution and nothing to key a settings
            # lookup or an allow-list check on — fold into FAILED, keyed by the entry
            # point's own name, rather than aborting discovery for every other pack.
            reports.append(
                PackReport(distribution=entry_point.name, status=PackStatus.FAILED, reason=str(exc))
            )
            continue
        seen.add(distribution)

        if allow_set is not None and distribution not in allow_set:
            reports.append(
                PackReport(
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
                distribution=distribution,
                registry=registry,
                raw_settings=settings_source.get(distribution, {}),
                direct_dependencies=direct_dependencies,
            )
        )

    if allow_set is not None:
        for missing in sorted(allow_set - seen):
            reports.append(
                PackReport(distribution=missing, status=PackStatus.ALLOWED_NOT_INSTALLED)
            )

    unclaimed = sorted(set(settings_source) - seen)
    if unclaimed:
        named = ", ".join(f"'{distribution}'" for distribution in unclaimed)
        available = ", ".join(f"'{distribution}'" for distribution in sorted(seen)) or "none"
        raise UnknownPackSettingsError(
            f"[packs] settings name {named}, which {'is' if len(unclaimed) == 1 else 'are'} "
            f"not installed. Install the distribution, or remove its settings block. "
            f"Distributions that declare a '{ENTRY_POINT_GROUP}' entry point: {available}."
        )

    return tuple(reports)


def _activate(
    entry_point: EntryPointLike,
    *,
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
    """
    ambient = direct_dependencies is not None and distribution not in direct_dependencies

    try:
        register_fn = entry_point.load()
    except Exception as exc:  # a pack's import can raise anything; that is FAILED, not a crash
        return PackReport(distribution=distribution, status=PackStatus.FAILED, reason=str(exc))

    try:
        disclosure = _read_disclosure(entry_point, distribution=distribution)
    except MalformedDisclosureError as exc:
        return PackReport(distribution=distribution, status=PackStatus.FAILED, reason=str(exc))

    registrar = PackRegistrar(registry, distribution=distribution)
    try:
        settings = _resolve_settings(register_fn, distribution=distribution, raw=raw_settings)
        register_fn(registrar, settings)
        registrar.commit()
    except Exception as exc:  # one broken pack must not stop the rest from loading
        return PackReport(
            distribution=distribution,
            status=PackStatus.FAILED,
            ambient=ambient,
            reason=str(exc),
            disclosure=disclosure,
        )

    return PackReport(
        distribution=distribution,
        status=PackStatus.ACTIVE,
        ambient=ambient,
        contributed=registrar.contributed,
        disclosure=disclosure,
    )


def _read_disclosure(entry_point: EntryPointLike, *, distribution: str) -> Disclosure | None:
    """The pack's module-level `DISCLOSURE`, read after import, before `register()` runs.

    `None` means genuinely absent — no `DISCLOSURE` attribute at all — which
    is the honest "not disclosed" `docs/02-extension-model.md` describes.
    Present but not a `Disclosure` instance is a different fact and is never
    collapsed into that same `None`: it raises `MalformedDisclosureError`,
    naming the distribution and what the attribute must be, so the caller can
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
        f"'{distribution}' defines DISCLOSURE but it is not a "
        f"weft_kernel.discovery.Disclosure instance (found {type(value).__name__}). "
        f"DISCLOSURE must be built from Disclosure(network=..., filesystem=..., "
        f"subprocess=..., note=...)."
    )


def _resolve_settings(
    register_fn: Callable[..., None], *, distribution: str, raw: Mapping[str, object]
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
            f"'{distribution}' declares register() with {len(parameters)} parameter(s); "
            f"docs/02-extension-model.md requires exactly (registrar, settings)."
        )

    hints = get_type_hints(register_fn)
    model = hints.get(parameters[1].name)
    if not (isinstance(model, type) and issubclass(model, BaseModel)):
        raise PackSettingsError(
            f"'{distribution}' does not annotate its settings parameter with a "
            f"pydantic.BaseModel subclass; register(registrar, settings: Settings) is required."
        )

    try:
        return model.model_validate(raw)
    except ValidationError as exc:
        raise PackSettingsError(f"'{distribution}' settings failed validation: {exc}") from exc


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
