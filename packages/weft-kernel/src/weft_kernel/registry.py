"""`Registry` — where a pack's `register()` adds what it provides.

Specified across `docs/02-extension-model.md` section 2 ("Packs and
discovery") and the duplicate-name trap in `docs/06-phase-0-build.md` (*the
three places this phase can accidentally settle G2*, item 3): G2 owns
arbitration between two packs registering the same name and has not decided,
so Phase 0 takes the reversible choice — **refuse the second registration
outright, naming both distributions**, and implement no last-wins,
first-wins or qualification. Four of the reference's six registration decorators
overwrote silently with no check at all, and every one of those is a bug
someone eventually has to find; refusing can be relaxed later without anyone
having silently lost a registration first, which is why it is the fixed
choice rather than an improvement on it.

Lookup is the other side of the same design: an unresolvable name is loud —
naming what was wanted, that nothing registered it, and what the valid
options are — never a bare failure with no further information
(`docs/02-extension-model.md` section 2, *the trust model*).

**This is the base mechanism only.** The kernel names no capability:
`contract` here is any type a pack publishes, and `Registry` never imports or
knows what any particular contract is for. Discovery (step 5) decides how
a pack's own distribution name reaches `add`'s `distribution` argument; the
entry-point trust model, conditional registration and pack settings are all
later steps.

**`destroys` mandatoriness, added at task 1.2.** `docs/02-extension-model.md`
§3 → *Ordering constraints*: "`destroys` is mandatory wherever a contract
publishes a property vocabulary, an explicit empty tuple included;
registration is refused otherwise, naming the missing declaration." Detected
generically off `contract` — `getattr(contract, "publishes_property_vocabulary",
False)` — never off a hardcoded list of contract names, because the module
docstring above already states the rule this obeys: "the kernel never
imports or knows what any particular contract is for." A contract opts in
the same way a real contract publishes `version` (`weft_extract.contract`,
`weft_chunk.contract`): a `ClassVar` declared under `if TYPE_CHECKING:` and
assigned for real after the class body, so it never joins
`__protocol_attrs__` and costs a structurally-conforming plugin nothing. The
asymmetry with `intact`, which stays a convention no seam enforces, is
`02` §3's own: "forgetting `intact` harms only your own stage and you find
out, while forgetting `destroys` silently corrupts a stranger's, and the
pack that caused it never sees a failure" — a defect this refusal exists to
make impossible rather than merely documented against.

**Read through `unwrap_factory`, never off `factory` directly.** A plugin
that binds pack settings ahead of time — `functools.partial(PluginClass,
settings)`, the only shape available to one, and the one `weft_store`
actually registers — has no attributes of its own: `hasattr` on a `partial`
never reaches `.func`. Skipping the unwrap would make this refusal loud for
the wrong reason (a plugin that *did* declare `destroys`, refused anyway,
pointed at a remedy already satisfied) and, in `weft_kernel.resolution`,
silent for the worse one — `getattr(factory, "requires", ())` on an
unwrapped `partial` just returns the default, invisibly. `unwrap_factory`
is the one place that peeling happens; every reader of a class-level plugin
declaration goes through it.

**Added at step 6 (the linear runner).** `entry()` returns the full
`RegistryEntry` — factory *and* distribution — where `lookup()` returns only
the factory. The runner needs the distribution to attribute the spans and
errors `weft_kernel.seam.wrap` produces to the pack that registered a
resolved stage; nothing before step 6 needed it, which is why `lookup` alone
was the whole surface until now.

**`contracts()` and `distributions_for()` added at task 0.12.** Until then,
`Registry` had no enumeration API a caller outside the kernel could walk —
`weft_cli.plugins_report`'s own module docstring named the gap explicitly,
as a real limitation rather than an oversight this module papered over.
`docs/08-manuals.md` §3 clause (b) is the first caller that actually needs
one: the generated contract reference has to know what got registered
without a second, hand-kept list of contract names, or it reproduces the
two-lists bug it exists to prevent. Both methods stay contract-agnostic —
`Registry` still never imports or knows what any particular contract is
for — and both are read-only projections of `_entries`, adding no new
state.

**Task 1.12 — G2 relaxed the refusal rather than tightening a silence.**
`docs/06-phase-0-build.md`'s own trap 3 already named the direction: "If G2
later chooses last-wins, first-wins or explicit qualification, it relaxes a
refusal rather than tightening a silence." G2 closed on qualification, but
qualification by the *operator*, not the pack — `docs/02-extension-model.md`
§3 → *When resolution fails*: "G3 settled that pipelines keep bare names, so
the data cannot break the tie and the operator does." `plugin_pins` is that
operator's `[plugins]` table from `weft.toml`, already parsed into a
`{"Contract:name": "distribution"}` mapping by whoever reads the file —
`weft-cli`'s `registry_bootstrap`, never this module, which is why `Registry`
takes a plain `Mapping[str, str]` rather than a path.

A pin changes what a collision *does*, never whether one is checked for:
`add`/`add_many` still refuse an unpinned collision exactly as before, now
printing the `[plugins]` line that would resolve it — the fixed refusal is
still the default, not replaced. A pinned collision instead resolves without
raising: the named distribution's registration stands (or takes over, if it
was the second to arrive), and the other is recorded in `displaced()` —
`docs/03-cli.md`'s own words, "installed, active, and one of its plugins is
unreachable" — never silently dropped the way the reference's four overwriting
decorators dropped one every time. This is also why a pinned collision no
longer fails `add_many`'s whole batch the way an unpinned one still does: the
pack that lost is not broken, so nothing about the rest of what it registered
should be either.

**A pin is a claim about a real fight, not a standing wildcard.** A pin
naming a distribution that is neither side of the collision it targets is
refused immediately, by `UnresolvedPluginPinError` — resolving it anyway
would silently start honouring a pin for a pack that never even contended,
which is exactly the kind of quiet drift a pin exists to prevent, not enable.
A pin that never sees a collision at all — because the name was never
claimed twice, or ever — is checked separately, by `unconsulted_pins()`;
`weft_kernel.discovery.discover` raises `InertPluginPinError` once discovery
finishes if any pin it was given never got the chance to arbitrate anything
and the caller has not opted out with `strict_pins=False` (a diagnostic
caller only — see `InertPluginPinError`'s own docstring), the same way an
unclaimed `packs:` settings key already raises there. Both directions share
one reasoning: `docs/02` says it as "an inert pin is a lie about what is
running."
"""

import functools
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass

from weft_kernel.errors import WeftError


class DuplicateRegistrationError(WeftError):
    """Two distributions registered the same name under the same contract, and no pin resolves it.

    Fixed for Phase 0 by `docs/06-phase-0-build.md`: refusal, not silent
    arbitration. Task 1.12 relaxes this exactly the way that trap said it
    would — a `[plugins]` pin in `weft.toml` lets the operator name the
    winner (see `Registry.__init__` and the module docstring); this class is
    raised only when no such pin exists for the colliding name, and its
    message prints the pin that would resolve it.
    """


class UnresolvedPluginPinError(WeftError):
    """A `[plugins]` pin exists for this collision, but names neither side of it.

    `docs/02-extension-model.md` §3: a pin naming a distribution that did not
    claim the name must fail loudly rather than being ignored — resolving it
    anyway would silently honour a pin for a pack that never contended, and
    an inert pin is exactly the lie about what is running this refusal
    exists to catch. Distinct from `DuplicateRegistrationError`: that one
    fires when *no* pin exists for the key at all; this one fires when a pin
    exists but points somewhere neither contender is.
    """


class MissingDestroysDeclarationError(WeftError):
    """A plugin registered for a contract that publishes a property vocabulary states no `destroys`.

    `docs/02-extension-model.md` §3 → *Ordering constraints*: `destroys` is
    mandatory wherever a contract publishes a property vocabulary — an
    explicit empty tuple counts as stating it, silence does not. Refused
    here, at registration, rather than left to surface later as a stranger's
    ordering-sensitive stage silently corrupted by this one at resolution
    time, with neither pack ever seeing a failure that names the cause.
    """


class UnknownPluginError(WeftError):
    """`Registry.lookup` was asked for a name no distribution registered.

    The message states the contract and name that were wanted, that no
    distribution registered it, and the full set of names that *are*
    registered for that contract, so a typo reads as a typo rather than a
    mystery — the anti-reference property: asking the reference for `faithfulness`
    returned no error and no score at all.
    """


@dataclass(frozen=True, slots=True)
class RegistryEntry:
    """One `(contract, name)` slot: what it resolves to, and which distribution put it there.

    Public — unlike `lookup`, which hands back only the factory, the linear
    runner (`06` step 6) needs the distribution too, to attribute the spans
    and errors `weft_kernel.seam.wrap` produces to the pack that registered
    the stage. `entry()` returns this; `lookup()` is `entry(...).factory` for
    callers that only need the callable.
    """

    factory: Callable[..., object]
    distribution: str


@dataclass(frozen=True, slots=True)
class DisplacedRegistration:
    """A registration a `[plugins]` pin resolved *away from* — recorded, never dropped.

    `docs/03-cli.md`: "the pack lost a `(contract, name)` collision to an
    operator's pin, so it is installed, active, and one of its plugins is
    unreachable." `distribution` is the pack that lost; `winner` is the one
    the pin named instead; `pin` is the exact `"Contract:name"` key from
    `weft.toml`'s `[plugins]` table, so `weft plugins doctor` can print the
    line an operator would need to change to reverse the decision.
    """

    contract: type[object]
    name: str
    distribution: str
    winner: str
    pin: str


@dataclass(frozen=True, slots=True)
class _CollisionResolution:
    """What a pinned collision resolves to — computed without mutating the registry.

    `entry` is `None` when the already-registered side wins (nothing to
    write); otherwise it is the replacement to write. Kept side-effect-free
    so `add_many` can resolve every entry in a batch *before* committing any
    of it — the same all-or-nothing discipline the unpinned path already has.
    """

    entry: RegistryEntry | None
    displaced: DisplacedRegistration


class Registry:
    """Where every pack's `register()` adds what it provides, keyed by contract and name.

    Two names collide only if they share both the contract *and* the string
    name: two packs each publishing the name `"fast"`, but under two
    different contract types, are unrelated registrations, because the
    kernel treats the contract as part of the key, never as a shared
    namespace plugins must avoid colliding in by convention.
    """

    def __init__(self, *, plugin_pins: Mapping[str, str] | None = None) -> None:
        """`plugin_pins` is the parsed `[plugins]` table — see the module docstring.

        Keyed `"Contract:name"` to the distribution that should win a
        collision on that name — `docs/02-extension-model.md` §3's exact
        shape. Copied into a plain `dict` so a caller mutating the mapping it
        passed in afterwards cannot change this registry's policy out from
        under it. Absent (`None`, the default) behaves exactly as Phase 0
        did: every collision is refused, unconditionally.
        """
        self._entries: dict[tuple[type[object], str], RegistryEntry] = {}
        self._plugin_pins: dict[str, str] = dict(plugin_pins or {})
        self._displaced: list[DisplacedRegistration] = []
        self._consulted_pins: set[str] = set()

    def add(
        self,
        contract: type[object],
        name: str,
        factory: Callable[..., object],
        *,
        distribution: str,
    ) -> None:
        """Register `factory` as `name` for `contract`, attributed to `distribution`.

        `distribution` is supplied by the registration seam (step 3), never
        by a pack author: attribution is a cross-cutting concern, and
        CLAUDE.md places those at the seam rather than in a rule authors
        must remember. A pack's own `register()` calls the seam-bound
        surface with `(contract, name, factory)`; this lower-level `add` is
        what the seam calls once it has filled `distribution` in itself.

        If `(contract, name)` is already taken, a `[plugins]` pin for this
        exact key resolves it — see the module docstring, *"Task 1.12."* With
        no pin, this still refuses outright, naming both the distribution
        that registered first and the one attempting to register now, and
        printing the pin that would resolve it — the fixed, reversible
        choice `docs/06-phase-0-build.md` took for G2's open arbitration
        question, still the default now that G2 has closed.

        Also refuses `factory` outright — before either check, since this is
        a property of the registration attempt itself rather than of what
        else is already here — if `contract` publishes a property vocabulary
        and `factory` never mentions `destroys` at all; see the module
        docstring, *"`destroys` mandatoriness, added at task 1.2."*
        """
        _require_destroys_if_governed(contract, name, factory, distribution=distribution)
        key = (contract, name)
        existing = self._entries.get(key)
        if existing is None:
            self._entries[key] = RegistryEntry(factory=factory, distribution=distribution)
            return
        resolution = self._resolve_collision(
            contract, name, existing=existing, factory=factory, distribution=distribution
        )
        self._commit_resolution(key, resolution)

    def add_many(
        self,
        entries: Iterable[tuple[type[object], str, Callable[..., object]]],
        *,
        distribution: str,
    ) -> None:
        """Register every `(contract, name, factory)` in `entries`, all at once or not at all.

        The commit half of a pack's transactional registration
        (`weft_kernel.discovery.PackRegistrar`): a pack's own `register()`
        buffers every `add` call instead of writing immediately, precisely so
        that a pack raising partway through never leaves some of its
        registrations standing while its `PackReport` claims zero — the
        defect this method exists to make structurally impossible. Every key
        in `entries` is checked against both the registry and the rest of
        the batch *before* anything is written — an unpinned collision
        against an existing registration, or `entries` registering the same
        `(contract, name)` twice within this one call, both still raise
        `DuplicateRegistrationError` and leave the registry exactly as it
        was. A *pinned* collision against an existing registration resolves
        instead of raising (task 1.12): the rest of the batch still commits,
        because the pack that lost one name is installed and active, not
        broken — `docs/03-cli.md`'s own words. Only once every entry is
        either free or pin-resolved does any write happen, so a failed call
        is still always a no-op. The mandatory-`destroys` check `add`
        performs (see its own docstring) runs here too, for the same reason
        and on the same all-or-nothing terms.
        """
        batch = list(entries)
        pending_new: dict[tuple[type[object], str], RegistryEntry] = {}
        pending_resolutions: list[tuple[tuple[type[object], str], _CollisionResolution]] = []
        for contract, name, factory in batch:
            _require_destroys_if_governed(contract, name, factory, distribution=distribution)
            key = (contract, name)
            existing = self._entries.get(key)
            if existing is not None:
                resolution = self._resolve_collision(
                    contract, name, existing=existing, factory=factory, distribution=distribution
                )
                pending_resolutions.append((key, resolution))
                continue
            if key in pending_new:
                raise DuplicateRegistrationError(
                    f"'{name}' is registered twice for {contract.__name__} within "
                    f"distribution '{distribution}'s own register() call; a pack cannot "
                    f"register the same name for the same contract more than once."
                )
            pending_new[key] = RegistryEntry(factory=factory, distribution=distribution)

        for key, entry in pending_new.items():
            self._entries[key] = entry
        for key, resolution in pending_resolutions:
            self._commit_resolution(key, resolution)

    def displaced(self) -> tuple[DisplacedRegistration, ...]:
        """Every registration a `[plugins]` pin resolved away from, in the order it happened.

        `weft_cli.plugins_report.render_doctor`'s source for the "displaced"
        report `docs/03-cli.md` describes — never dropped, per the module
        docstring's *Task 1.12* note.
        """
        return tuple(self._displaced)

    def unconsulted_pins(self) -> frozenset[str]:
        """Every `[plugins]` pin this registry was given that never resolved an actual collision.

        `weft_kernel.discovery.discover` raises `InertPluginPinError` off
        this once discovery finishes, the same way it already raises for an
        unclaimed `packs:` settings key — see the module docstring's *Task
        1.12* note. A pin naming a `(contract, name)` nothing ever claimed
        twice stays in this set forever; one that actually arbitrated a
        collision (`add`/`add_many` calling `_resolve_collision`) leaves it.
        """
        return frozenset(self._plugin_pins) - self._consulted_pins

    def _resolve_collision(
        self,
        contract: type[object],
        name: str,
        *,
        existing: RegistryEntry,
        factory: Callable[..., object],
        distribution: str,
    ) -> _CollisionResolution:
        """What a pin says to do about this collision, or the refusal if none applies.

        Pure — reads `self._plugin_pins` but writes nothing, so `add_many`
        can call this for every colliding entry in a batch before committing
        any of them. Raises `DuplicateRegistrationError` (no pin for this
        key) or `UnresolvedPluginPinError` (a pin exists but names neither
        `existing.distribution` nor `distribution`) directly; a caller never
        has to distinguish those from an ordinary return.
        """
        pin_key = _pin_key(contract, name)
        pin = self._plugin_pins.get(pin_key)
        if pin is None:
            raise DuplicateRegistrationError(
                f"'{name}' is already registered for {contract.__name__} by "
                f"distribution '{existing.distribution}'; distribution '{distribution}' "
                f"cannot register it too. Weft refuses to arbitrate between them — pin the "
                f"winner in weft.toml:\n\n[plugins]\n"
                f'"{pin_key}" = "{existing.distribution}"  # or "{distribution}"\n\n'
                f"to keep the other distribution's claim instead. See the duplicate-name "
                f"trap in docs/06-phase-0-build.md and docs/02-extension-model.md §3, "
                f"'When resolution fails'."
            )
        if pin not in (existing.distribution, distribution):
            raise UnresolvedPluginPinError(
                f"[plugins] pins '{pin_key}' to '{pin}', but '{pin}' registered neither "
                f"claim on '{name}' for {contract.__name__} — '{existing.distribution}' and "
                f"'{distribution}' are the two distributions actually contending for it. "
                f"Point the pin at one of them, or remove it if it was meant for a "
                f"different collision."
            )
        if pin == existing.distribution:
            return _CollisionResolution(
                entry=None,
                displaced=DisplacedRegistration(
                    contract=contract,
                    name=name,
                    distribution=distribution,
                    winner=existing.distribution,
                    pin=pin_key,
                ),
            )
        return _CollisionResolution(
            entry=RegistryEntry(factory=factory, distribution=distribution),
            displaced=DisplacedRegistration(
                contract=contract,
                name=name,
                distribution=existing.distribution,
                winner=distribution,
                pin=pin_key,
            ),
        )

    def _commit_resolution(
        self, key: tuple[type[object], str], resolution: _CollisionResolution
    ) -> None:
        """Write what `_resolve_collision` decided: the replacement (if any), and the record."""
        if resolution.entry is not None:
            self._entries[key] = resolution.entry
        self._displaced.append(resolution.displaced)
        self._consulted_pins.add(resolution.displaced.pin)

    def contracts(self) -> frozenset[type[object]]:
        """Every contract type with at least one registered name.

        Two names under one contract still count once — the key this counts
        over is `_entries`' contract half, not the full `(contract, name)`
        pair. See the module docstring for why this exists and who the
        first caller is.
        """
        return frozenset(contract for contract, _ in self._entries)

    def distributions_for(self, contract: type[object]) -> frozenset[str]:
        """Every distribution that registered at least one name under `contract`.

        A contract is not one pack's alone — two distributions may each
        register a different name under the same contract, exactly the
        shape `docs/02-extension-model.md` describes for a second store
        backend — so this returns every contributor, never a single owner.
        Empty, never an error, for a contract nothing registered.
        """
        return frozenset(
            entry.distribution
            for (registered, _), entry in self._entries.items()
            if registered is contract
        )

    def lookup(self, contract: type[object], name: str) -> Callable[..., object]:
        """The factory registered as `name` for `contract`.

        `self.entry(contract, name).factory` — see `entry` for the same
        lookup with the providing distribution attached, and for the error
        both raise.
        """
        return self.entry(contract, name).factory

    def entry(self, contract: type[object], name: str) -> RegistryEntry:
        """The full registration for `(contract, name)`: its factory and providing distribution.

        Raises `UnknownPluginError`, naming the contract and name that were
        wanted, stating that nothing registered it, and listing every name
        that *is* registered for that contract.
        """
        found = self._entries.get((contract, name))
        if found is not None:
            return found

        options = sorted(
            registered_name
            for registered_contract, registered_name in self._entries
            if registered_contract == contract
        )
        available = ", ".join(f"'{option}'" for option in options) if options else "none"
        raise UnknownPluginError(
            f"no '{name}' is registered for {contract.__name__}. It is "
            f"unavailable because no distribution has registered that name for this "
            f"contract. Names registered for {contract.__name__}: {available}."
        )


def _pin_key(contract: type[object], name: str) -> str:
    """The exact `"Contract:name"` string a `[plugins]` pin uses for this collision.

    `docs/02-extension-model.md` §3's own shape — `"Enhancer:keybert" =
    "weft-kw"`. `contract.__name__` rather than a fully-qualified path,
    matching every other message in this module that already names a
    contract this way (`DuplicateRegistrationError`, `UnknownPluginError`):
    the operator writing `weft.toml` sees the same short name doctor and
    every refusal already print.
    """
    return f"{contract.__name__}:{name}"


def unwrap_factory(factory: Callable[..., object]) -> object:
    """The plugin class (or callable) a factory constructs, `functools.partial` peeled away.

    A plugin needing pack settings has only one shape available to it —
    `functools.partial(PluginClass, settings)`, exactly what
    `weft_store.pgvector_store.register` does — and `functools.partial` does
    not proxy attribute access to `.func`: `hasattr(functools.partial(C), "x")`
    is `False` even when `C.x` is set, for any `x`. Every read site in the
    kernel that inspects a *class* attribute a plugin declared — `destroys`
    here, and `requires`/`provides`/`intact`/`destroys` in
    `weft_kernel.resolution.resolve` — must therefore unwrap the same way
    before reading, or a pack binding its own settings this way has its
    declarations silently invisible to one reader while
    `weft_kernel.runner.Runner`, which reads a *constructed instance* instead
    of the factory, sees them correctly. Walking `.func` repeatedly handles a
    `partial` of a `partial`, which `functools.partial` itself collapses on
    construction but nothing guarantees a caller building one by hand did.
    """
    target: object = factory
    while isinstance(target, functools.partial):
        target = target.func
    return target


def _require_destroys_if_governed(
    contract: type[object], name: str, factory: Callable[..., object], *, distribution: str
) -> None:
    """Refuse `factory` if `contract` publishes a property vocabulary and it never says `destroys`.

    `getattr(contract, "publishes_property_vocabulary", False)` is the whole
    detection — see the module docstring, *"`destroys` mandatoriness, added
    at task 1.2."* An ungoverned contract (the overwhelming majority; nothing
    about `requires`/`provides` or ordinary registration ever required this)
    is untouched: this function returns immediately, and every existing
    caller of `add`/`add_many` that registers a bare stand-in with no
    `destroys` at all keeps working exactly as before.

    `hasattr(unwrap_factory(factory), "destroys")` reads the *class*, not an
    instance — `factory` is ordinarily the plugin class itself
    (`registrar.add(Chunker, "fixed-size", FixedSizeChunker)`), sometimes a
    `functools.partial` binding pack settings ahead of it (see
    `unwrap_factory`), and no config exists yet to build an instance from at
    registration time either way. A class that never mentions `destroys` —
    not even inherited — answers `False`; one that assigns `destroys = ()`
    explicitly answers `True`, which is exactly the asymmetry `02` §3
    requires: the empty tuple must be *written*, not merely true by silence.
    """
    if not getattr(contract, "publishes_property_vocabulary", False):
        return
    if hasattr(unwrap_factory(factory), "destroys"):
        return
    raise MissingDestroysDeclarationError(
        f"'{name}' registers for {contract.__name__} (distribution '{distribution}') without "
        f"declaring `destroys`. {contract.__name__} publishes a property vocabulary "
        f"(docs/02-extension-model.md §3 → Ordering constraints), so every implementation "
        f"states what it destroys — an explicit empty tuple if it destroys nothing. Add "
        f"`destroys: tuple[type[Property], ...] = (...)` to the plugin class."
    )
