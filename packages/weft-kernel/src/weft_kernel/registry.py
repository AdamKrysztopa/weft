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
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass

from weft_kernel.errors import WeftError


class DuplicateRegistrationError(WeftError):
    """Two distributions registered the same name under the same contract.

    Fixed for Phase 0 by `docs/06-phase-0-build.md`: refusal, not
    arbitration. If G2 later chooses last-wins, first-wins or explicit
    qualification, that decision relaxes this refusal rather than tightening
    a silence — see the module docstring.
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


class Registry:
    """Where every pack's `register()` adds what it provides, keyed by contract and name.

    Two names collide only if they share both the contract *and* the string
    name: two packs each publishing the name `"fast"`, but under two
    different contract types, are unrelated registrations, because the
    kernel treats the contract as part of the key, never as a shared
    namespace plugins must avoid colliding in by convention.
    """

    def __init__(self) -> None:
        self._entries: dict[tuple[type[object], str], RegistryEntry] = {}

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

        Refuses outright if `(contract, name)` is already taken, naming both
        the distribution that registered first and the one attempting to
        register now — the fixed, reversible choice `docs/06-phase-0-build.md`
        takes for G2's open arbitration question. No last-wins, first-wins or
        qualification is implemented here, or ever silently assumed.
        """
        key = (contract, name)
        existing = self._entries.get(key)
        if existing is not None:
            raise DuplicateRegistrationError(
                f"'{name}' is already registered for {contract.__name__} by "
                f"distribution '{existing.distribution}'; distribution '{distribution}' "
                f"cannot register it too. Weft refuses on duplicate registration rather "
                f"than arbitrating between them — rename one, or see the duplicate-name "
                f"trap in docs/06-phase-0-build.md."
            )
        self._entries[key] = RegistryEntry(factory=factory, distribution=distribution)

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
        the batch *before* anything is written; the first collision found —
        against an existing registration or against `entries` registering
        the same `(contract, name)` twice — raises `DuplicateRegistrationError`
        and leaves the registry exactly as it was. Only once every key is
        confirmed free does any write happen, so a failed call is always a
        no-op.
        """
        batch = list(entries)
        pending: dict[tuple[type[object], str], Callable[..., object]] = {}
        for contract, name, factory in batch:
            key = (contract, name)
            existing = self._entries.get(key)
            if existing is not None:
                raise DuplicateRegistrationError(
                    f"'{name}' is already registered for {contract.__name__} by "
                    f"distribution '{existing.distribution}'; distribution '{distribution}' "
                    f"cannot register it too. Weft refuses on duplicate registration rather "
                    f"than arbitrating between them — rename one, or see the duplicate-name "
                    f"trap in docs/06-phase-0-build.md."
                )
            if key in pending:
                raise DuplicateRegistrationError(
                    f"'{name}' is registered twice for {contract.__name__} within "
                    f"distribution '{distribution}'s own register() call; a pack cannot "
                    f"register the same name for the same contract more than once."
                )
            pending[key] = factory

        for (contract, name), factory in pending.items():
            self._entries[(contract, name)] = RegistryEntry(
                factory=factory, distribution=distribution
            )

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
