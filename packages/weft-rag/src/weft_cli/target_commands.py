"""`weft target promote|rollback|drop` — ledger tasks **34.8** and **34.9**.

Blue-green migration's other half: `weft_cli.commands.TargetListCommand` (task 34.6) only reads
a store's own catalogue; these three write it. Kept in a module of their own rather than growing
`weft_cli.commands` further — the identical "compose from more than one function" convention that
module's own `register` docstring already names for `weft_cli.eval_baseline`/`weft_cli.
eval_experiment` — and registered from there, right after `"target list"`.

**Promote is gated on evidence** (`weft_engine.targets.PromotionEvidenceMissingError`/
`PromotionEvidenceMismatchError`), **a ready candidate** (`CandidateNotReadyError`), and **a
recorded embedding identity** (`CandidateIdentityUnrecordedError`) — all four errors live in
`weft_engine.targets`, beside every other target-shaped refusal that module already owns, and
this module raises them rather than re-deriving the checks. Evidence is loaded and judged the
same way `weft eval compare` judges two runs — `weft_cli.eval_commands.load_or_refuse_run` and
`.incomparable_reasons`, reused rather than copied, so a promotion and a comparison can never
come to disagree about what "comparable" means (owner decision Q-E).

**Promote, rollback and drop act on every `TargetHolding` participant** — ledger task **34.11**,
its fan-out half, widening this module past `[services] store` alone: `weft_cli.participation.
target_participants` (imported from there rather than defined here — that module already sits
below both this one and `weft_cli.eval_commands`, so it is the one place a participant list can
live that both can import from with no cycle) is every `NodeStore` name `stores_in_use` reaches
for this project (the node store, and, once an active pack's own pipelines resolved a second
one, that store too) that also satisfies `weft_store.contract.TargetHolding` — never a plugin
name written here, so this module names no pack beyond what a project's own pipelines already
resolved. Promote's own checks (existence, identity, not-ready, evidence) still read the primary
`[services] store` alone; the fan-out is only the write, once those checks pass, and the target
must exist in every participant or the write refuses by name (`weft_store.contract.
UnknownTargetError`) rather than promoting some of them and not others.

**Drop's blob subtree** — ledger task **34.12** — is reached the identical way: `_blob_instance`
asks the registry which name, if any, is registered under `weft_blob.contract.BlobStore` (empty
when `[packs.blob]` is not configured, never an error), so this module still names no pack. The
target-lifecycle methods `FilesystemBlobStore` adds beyond that published contract —
`bind_target`/`drop_target` — are reached through `weft_blob.contract.BlobTargetHolding`,
published beside `BlobStore` (carried repair **R34.9**) as `weft_store.contract.TargetHolding`
already is beside `NodeStore`: a stranger's `BlobStore` that never grew a target concept is not
asked to drop one.
"""

from __future__ import annotations

import getpass
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import ClassVar, cast

from pydantic import BaseModel, ConfigDict, Field

from weft_blob.contract import BlobStore, BlobTargetHolding
from weft_cli.eval_commands import incomparable_reasons, load_or_refuse_run
from weft_cli.participation import target_participants
from weft_command.contract import Command, CommandResult
from weft_command.permission import PermissionClass
from weft_engine.registry_bootstrap import Dependencies
from weft_engine.targets import (
    CandidateIdentityUnrecordedError,
    CandidateNotReadyError,
    PromotionEvidenceMismatchError,
    PromotionEvidenceMissingError,
    StoreHoldsNoTargetsError,
)
from weft_kernel.context import Context
from weft_kernel.discovery import PackRegistrar
from weft_kernel.payload import Outcome, Produced
from weft_kernel.registry import RegistryEntry
from weft_kernel.seam import aclose, wrap
from weft_store import NodeStore, SourceRecord, SourceStatus
from weft_store.contract import (
    NoPreviousTargetError,
    Promotion,
    TargetCatalogue,
    TargetHolding,
    TargetName,
    UnknownTargetError,
    target_name,
)

_TARGET_PROMOTE_HELP = (
    "make <name> the live target, atomically — refused with no evidence (unless "
    "--without-evidence), for a candidate still indexing or deleting, or one whose embedder "
    "was never recorded (ledger task 34.8)"
)

_TARGET_ROLLBACK_HELP = "restore the previous live target, atomically (ledger task 34.9)"

_TARGET_DROP_HELP = (
    "remove a target that is neither live nor previous-live — never through delete_source "
    "(ledger task 34.9)"
)


class _NoArgs(BaseModel):
    """The args model for `target rollback`, which takes none — `weft_cli.commands.NoArgs`'s own
    shape, defined again here rather than imported: a module-scope import of it back would be
    the identical cycle `weft_cli.commands`' own docstring already names for
    `weft_cli.render` (that module imports `weft_cli.commands`, so `weft_cli.commands`
    importing `weft_cli.target_commands` at module scope, for a result type, and this module
    importing `weft_cli.commands` back for one args model, would be exactly that cycle).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")


class TargetPromoteArgs(BaseModel):
    """`weft target promote <name> [--evidence <live-run> <candidate-run>] [--without-evidence]`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    evidence: list[str] = Field(
        default_factory=list,
        description=(
            "two persisted run ids, the live target's run first and the candidate's second — "
            "loaded and compared the way `weft eval compare` compares two runs"
        ),
    )
    without_evidence: bool = False


class TargetPromoteCommandResult(CommandResult):
    """`weft target promote`'s whole answer — the catalogue after the switch on the primary
    `[services] store`, and every `TargetHolding` participant it switched on.
    """

    catalogue: TargetCatalogue
    store: str
    #: Ledger task **34.11** — every participant `target_participants` named, in the order they
    #: were promoted (`store` first, always). A store already at `catalogue.live` before this
    #: run — a re-run converging a crash — is still named here: its own `promote` was called and
    #: is the store's own idempotent no-op, not a skip this command decided on its behalf.
    stores: tuple[str, ...] = ()


class TargetPromoteCommand:
    """`weft target promote <name>` — ledger task **34.8**.

    Order of checks: `name` exists → its embedding identity is recorded
    (`CandidateIdentityUnrecordedError`) → no source it holds is `SourceStatus.INDEXING` or
    `.DELETING` (`CandidateNotReadyError`) → evidence, unless `--without-evidence`
    (`PromotionEvidenceMissingError`/`PromotionEvidenceMismatchError`). `promote` itself is the
    store's own atomic write; this command only decides whether to call it.

    "Exists" is catalogue membership. Every store catalogues a target on its first write, a
    source record included (the kit's `check_a_target_whose_first_write_is_a_source_record_is_
    catalogued`), so a candidate an interrupted index left with sources and no nodes is
    catalogued, and is refused as unrecorded rather than as unknown.
    """

    args_model: ClassVar[type[BaseModel]] = TargetPromoteArgs
    result_model: ClassVar[type[CommandResult]] = TargetPromoteCommandResult
    permission_class: ClassVar[PermissionClass] = PermissionClass.OVERWRITE
    help: ClassVar[str] = _TARGET_PROMOTE_HELP

    def __init__(self, config: object = None) -> None:
        del config

    async def run(self, args: BaseModel, ctx: Context) -> Outcome[CommandResult]:
        typed = cast(TargetPromoteArgs, args)
        deps = ctx.require(Dependencies)
        store_name = deps.services.store
        entry = deps.registry.entry(NodeStore, store_name)
        instance = entry.factory(None)
        if not isinstance(instance, TargetHolding):
            raise StoreHoldsNoTargetsError(store_name=store_name, target=typed.name)

        name = target_name(typed.name)
        try:
            catalogue = await self._catalogue_of(instance, entry=entry, store_name=store_name)
            sources = await self._sources_of(instance, name, entry=entry, store_name=store_name)
            candidate = next((record for record in catalogue.targets if record.name == name), None)
            if candidate is None:
                valid = tuple(sorted(record.name for record in catalogue.targets))
                raise UnknownTargetError(name, valid_options=valid)
            if candidate.embedding is None:
                raise CandidateIdentityUnrecordedError(target=name)

            not_ready = tuple(
                sorted(
                    str(source.id)
                    for source in sources
                    if source.status in (SourceStatus.INDEXING, SourceStatus.DELETING)
                )
            )
            if not_ready:
                raise CandidateNotReadyError(target=name, sources=not_ready)

            evidence = self._evidence_for(typed, catalogue, name)
            promotion = Promotion(
                target=name,
                at=datetime.now(UTC),
                by=getpass.getuser(),
                evidence=evidence,
                without_evidence=typed.without_evidence,
            )
            # Ledger **34.11** — every other `TargetHolding` participant must hold `name` too,
            # checked before any of them is written, so a promote never writes some and refuses
            # the rest partway through.
            others = tuple(
                participant
                for participant in await target_participants(deps)
                if participant != store_name
            )
            for participant in others:
                await self._require_target_in(participant, name, deps=deps)
            updated = await self._promoted(instance, promotion, entry=entry, store_name=store_name)
            for participant in others:
                await self._promote_participant(participant, promotion, deps=deps)
        finally:
            await aclose(
                instance,
                distribution=entry.distribution,
                contract=NodeStore.__qualname__,
                plugin=store_name,
            )
        return Produced(
            value=TargetPromoteCommandResult(
                catalogue=updated, store=store_name, stores=(store_name, *others)
            )
        )

    async def _require_target_in(
        self, store_name: str, name: TargetName, *, deps: Dependencies
    ) -> None:
        """`name` must exist in `store_name`'s own catalogue too — every other `TargetHolding`
        participant, checked before any of them is written.
        """
        entry = deps.registry.entry(NodeStore, store_name)
        instance = cast(TargetHolding, entry.factory(None))
        try:
            catalogue = await self._catalogue_of(instance, entry=entry, store_name=store_name)
        finally:
            await aclose(
                instance,
                distribution=entry.distribution,
                contract=NodeStore.__qualname__,
                plugin=store_name,
            )
        valid = tuple(sorted(record.name for record in catalogue.targets))
        if name not in valid:
            raise UnknownTargetError(f"{name} (on {store_name!r})", valid_options=valid)

    async def _promote_participant(
        self, store_name: str, promotion: Promotion, *, deps: Dependencies
    ) -> None:
        """`store_name`'s own `promote`, through `_promoted` — a store already at
        `promotion.target` treats this as its own idempotent no-op (`weft_store.conformance.
        check_promoting_the_live_target_again_changes_nothing`), which is what lets a re-run
        after a crash converge the participants that already moved.
        """
        entry = deps.registry.entry(NodeStore, store_name)
        instance = cast(TargetHolding, entry.factory(None))
        try:
            await self._promoted(instance, promotion, entry=entry, store_name=store_name)
        finally:
            await aclose(
                instance,
                distribution=entry.distribution,
                contract=NodeStore.__qualname__,
                plugin=store_name,
            )

    async def _catalogue_of(
        self, instance: TargetHolding, *, entry: RegistryEntry, store_name: str
    ) -> TargetCatalogue:
        """`instance.target_catalogue()`, through `wrap` — `weft_cli.commands.
        TargetListCommand`'s own footing: a local adapter handed to `wrap` *by name*, never
        called directly (fitness function 33(b)).
        """

        async def _catalogue(instance: TargetHolding = instance) -> Outcome[TargetCatalogue]:
            return Produced(value=await instance.target_catalogue())

        return cast(
            Produced[TargetCatalogue],
            await wrap(
                _catalogue,
                distribution=entry.distribution,
                contract=NodeStore.__qualname__,
                plugin=store_name,
                stage="target:catalogue",
            )(),
        ).value

    async def _sources_of(
        self, instance: TargetHolding, name: TargetName, *, entry: RegistryEntry, store_name: str
    ) -> Sequence[SourceRecord]:
        """Every source `name` holds — used both to decide whether a name with no catalogue
        row holds anything at all, and, by `run()`, to find one recorded `SourceStatus.
        INDEXING`/`.DELETING` (`CandidateNotReadyError`'s own evidence). One wrapped call.
        """

        async def _sources(instance: TargetHolding = instance) -> Outcome[Sequence[SourceRecord]]:
            # `bind_target`'s own `Self` is `TargetHolding`-typed; `instance` is `NodeStore`
            # by construction (`entry` above is `NodeStore`'s own registration) —
            # `TargetListCommand`'s identical cast.
            handle = cast(NodeStore, await instance.bind_target(name))
            return Produced(value=await handle.list_sources())

        return cast(
            Produced[Sequence[SourceRecord]],
            await wrap(
                _sources,
                distribution=entry.distribution,
                contract=NodeStore.__qualname__,
                plugin=store_name,
                stage="target:sources",
            )(),
        ).value

    def _evidence_for(
        self, typed: TargetPromoteArgs, catalogue: TargetCatalogue, name: str
    ) -> tuple[str, ...]:
        """`typed.evidence`, validated against `catalogue` and `weft_cli.eval_commands.
        incomparable_reasons` — `()` for `--without-evidence`, never a partial answer: every
        return either is two run ids that passed every check, or the check that failed raised.
        """
        if typed.without_evidence:
            return ()
        if len(typed.evidence) != 2:
            raise PromotionEvidenceMissingError(target=name)
        live_run, candidate_run = typed.evidence
        record_a = load_or_refuse_run(live_run)
        record_b = load_or_refuse_run(candidate_run)
        reasons: list[str] = []
        if record_a.target != catalogue.live:
            reasons.append(
                f"the first run did not score the live target (scored "
                f"{record_a.target!r}, live is {catalogue.live!r})"
            )
        if record_b.target != name:
            reasons.append(
                f"the second run did not score the candidate (scored "
                f"{record_b.target!r}, candidate is {name!r})"
            )
        reasons.extend(incomparable_reasons(record_a, record_b))
        if reasons:
            raise PromotionEvidenceMismatchError(target=name, reasons=tuple(reasons))
        return (live_run, candidate_run)

    async def _promoted(
        self,
        instance: TargetHolding,
        promotion: Promotion,
        *,
        entry: RegistryEntry,
        store_name: str,
    ) -> TargetCatalogue:
        """`instance.promote(promotion)`, through `wrap` — `_catalogue_of`'s own footing."""

        async def _promote(instance: TargetHolding = instance) -> Outcome[TargetCatalogue]:
            return Produced(value=await instance.promote(promotion))

        return cast(
            Produced[TargetCatalogue],
            await wrap(
                _promote,
                distribution=entry.distribution,
                contract=NodeStore.__qualname__,
                plugin=store_name,
                stage="target:promote",
            )(),
        ).value


class TargetRollbackCommandResult(CommandResult):
    """`weft target rollback`'s whole answer — the catalogue after restoring the previous
    live target on the primary `[services] store`, and every `TargetHolding` participant it
    restored it on.
    """

    catalogue: TargetCatalogue
    store: str
    #: Ledger task **34.11** — `store` first, then every other participant `rollback()` actually
    #: changed. A non-primary participant with nothing to roll back to (`NoPreviousTargetError`)
    #: is left alone rather than failing the whole command: it never diverged, so it is already
    #: in the state this rollback is converging toward.
    stores: tuple[str, ...] = ()


class TargetRollbackCommand:
    """`weft target rollback` — ledger task **34.9**, widened by **34.11** to every
    `TargetHolding` participant. `[services] store`'s own `rollback()` is the primary's atomic
    write, and its own `NoPreviousTargetError` propagates exactly as before; every other
    participant is rolled back too, and one with nothing to roll back to is skipped rather than
    failing the command — see `TargetRollbackCommandResult.stores`.
    """

    args_model: ClassVar[type[BaseModel]] = _NoArgs
    result_model: ClassVar[type[CommandResult]] = TargetRollbackCommandResult
    permission_class: ClassVar[PermissionClass] = PermissionClass.OVERWRITE
    help: ClassVar[str] = _TARGET_ROLLBACK_HELP

    def __init__(self, config: object = None) -> None:
        del config

    async def run(self, args: BaseModel, ctx: Context) -> Outcome[CommandResult]:
        del args
        deps = ctx.require(Dependencies)
        store_name = deps.services.store
        entry = deps.registry.entry(NodeStore, store_name)
        instance = entry.factory(None)
        if not isinstance(instance, TargetHolding):
            raise StoreHoldsNoTargetsError(store_name=store_name, target=None)
        try:
            catalogue = await self._rolled_back(instance, entry=entry, store_name=store_name)
        finally:
            await aclose(
                instance,
                distribution=entry.distribution,
                contract=NodeStore.__qualname__,
                plugin=store_name,
            )
        touched = [store_name]
        for participant in await target_participants(deps):
            if participant == store_name:
                continue
            if await self._rollback_participant(participant, deps=deps):
                touched.append(participant)
        return Produced(
            value=TargetRollbackCommandResult(
                catalogue=catalogue, store=store_name, stores=tuple(touched)
            )
        )

    async def _rolled_back(
        self, instance: TargetHolding, *, entry: RegistryEntry, store_name: str
    ) -> TargetCatalogue:
        """`instance.rollback()`, through `wrap` — `TargetPromoteCommand._promoted`'s footing."""

        async def _rollback(instance: TargetHolding = instance) -> Outcome[TargetCatalogue]:
            return Produced(value=await instance.rollback())

        return cast(
            Produced[TargetCatalogue],
            await wrap(
                _rollback,
                distribution=entry.distribution,
                contract=NodeStore.__qualname__,
                plugin=store_name,
                stage="target:rollback",
            )(),
        ).value

    async def _rollback_participant(self, store_name: str, *, deps: Dependencies) -> bool:
        """`store_name`'s own `rollback()` — `True` if it moved, `False` if it had nothing to
        roll back to (`NoPreviousTargetError`, swallowed here: a participant that never diverged
        needs no rollback of its own to converge).
        """
        entry = deps.registry.entry(NodeStore, store_name)
        instance = cast(TargetHolding, entry.factory(None))
        try:
            await self._rolled_back(instance, entry=entry, store_name=store_name)
        except NoPreviousTargetError:
            return False
        finally:
            await aclose(
                instance,
                distribution=entry.distribution,
                contract=NodeStore.__qualname__,
                plugin=store_name,
            )
        return True


class TargetDropArgs(BaseModel):
    """`weft target drop <name>`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str


class TargetDropCommandResult(CommandResult):
    """`weft target drop`'s whole answer — which store, which target, and how many sources it
    held when it was dropped.
    """

    store: str
    target: str
    sources: int
    #: Ledger task **34.11** — `store` first, then every other `TargetHolding` participant it
    #: was also removed from.
    stores: tuple[str, ...] = ()


class TargetDropCommand:
    """`weft target drop <name>` — ledger task **34.9**, widened by **34.11**/**34.12**.

    Never `delete_source`: this removes a whole target's own storage (`TargetHolding.drop_target`),
    not one document's derived state from a target that keeps existing. `[services] store`'s own
    `drop_target` refuses a target that does not exist, or one that is live or previous-live
    (`UnknownTargetError`/`TargetInUseError`), unchanged here; every other `TargetHolding`
    participant is then dropped too, and, once the primary has agreed to drop it,
    `FilesystemBlobStore`'s own blob subtree for `name`, if `[packs.blob]` is configured — no
    subtree is fine.

    **`describe_impact` names the target, not a source count** — `weft_cli.commands.
    DeleteCommand.describe_impact`'s own footing, for the identical reason that docstring
    gives: `describe_impact` is synchronous, so it cannot connect to `[services] store` to count
    anything without either guessing or running part of the command before consent is asked.
    `TargetDropCommandResult.sources` is real, counted inside `run()`, after consent.
    """

    args_model: ClassVar[type[BaseModel]] = TargetDropArgs
    result_model: ClassVar[type[CommandResult]] = TargetDropCommandResult
    permission_class: ClassVar[PermissionClass] = PermissionClass.DESTROY
    help: ClassVar[str] = _TARGET_DROP_HELP

    def __init__(self, config: object = None) -> None:
        del config

    def describe_impact(self, args: BaseModel, ctx: Context) -> str:
        typed = cast(TargetDropArgs, args)
        deps = ctx.require(Dependencies)
        return f"target {typed.name!r} will be dropped from {deps.services.store!r}."

    async def run(self, args: BaseModel, ctx: Context) -> Outcome[CommandResult]:
        typed = cast(TargetDropArgs, args)
        deps = ctx.require(Dependencies)
        store_name = deps.services.store
        entry = deps.registry.entry(NodeStore, store_name)
        instance = entry.factory(None)
        if not isinstance(instance, TargetHolding):
            raise StoreHoldsNoTargetsError(store_name=store_name, target=typed.name)
        name = target_name(typed.name)
        try:

            async def _count(instance: TargetHolding = instance) -> Outcome[int]:
                # `TargetPromoteCommand.run`'s identical cast, `TargetListCommand`'s footing.
                handle = cast(NodeStore, await instance.bind_target(name))
                return Produced(value=len(await handle.list_sources()))

            sources = cast(
                Produced[int],
                await wrap(
                    _count,
                    distribution=entry.distribution,
                    contract=NodeStore.__qualname__,
                    plugin=store_name,
                    stage="target:sources",
                )(),
            ).value

            await self._dropped(instance, name, entry=entry, store_name=store_name)
        finally:
            await aclose(
                instance,
                distribution=entry.distribution,
                contract=NodeStore.__qualname__,
                plugin=store_name,
            )
        touched = [store_name]
        for participant in await target_participants(deps):
            if participant == store_name:
                continue
            await self._drop_participant(participant, name, deps=deps)
            touched.append(participant)
        await self._drop_blob_subtree(name, deps=deps)
        return Produced(
            value=TargetDropCommandResult(
                store=store_name, target=typed.name, sources=sources, stores=tuple(touched)
            )
        )

    async def _dropped(
        self, instance: TargetHolding, name: TargetName, *, entry: RegistryEntry, store_name: str
    ) -> None:
        """`instance.drop_target(name)`, through `wrap` — `TargetPromoteCommand._promoted`'s
        footing.
        """

        async def _drop(instance: TargetHolding = instance) -> Outcome[None]:
            await instance.drop_target(name)
            return Produced(value=None)

        await wrap(
            _drop,
            distribution=entry.distribution,
            contract=NodeStore.__qualname__,
            plugin=store_name,
            stage="target:drop",
        )()

    async def _drop_participant(
        self, store_name: str, name: TargetName, *, deps: Dependencies
    ) -> None:
        """`store_name`'s own `drop_target` — every other `TargetHolding` participant
        `target_participants` names.
        """
        entry = deps.registry.entry(NodeStore, store_name)
        instance = cast(TargetHolding, entry.factory(None))
        try:
            await self._dropped(instance, name, entry=entry, store_name=store_name)
        finally:
            await aclose(
                instance,
                distribution=entry.distribution,
                contract=NodeStore.__qualname__,
                plugin=store_name,
            )

    async def _drop_blob_subtree(self, name: TargetName, *, deps: Dependencies) -> None:
        """`name`'s own blob subtree, if `[packs.blob]` is configured — ledger task **34.12**.

        Read directly off the registry (`deps.registry.names_for(BlobStore)`) rather than
        through `[services] blob` role selection: dropping a target's own blob bytes is this
        project's bookkeeping, not a pipeline capability a run opts into, and an operator who
        configured `[packs.blob] root` but selected no `[services] blob` role still gets its
        bytes reaped. Empty when `[packs.blob]` is not configured, never an error — "no subtree
        is fine". A blob plugin that does not satisfy `BlobTargetHolding` holds no targets and is
        left alone.
        """
        names = sorted(deps.registry.names_for(BlobStore))
        if not names:
            return
        entry = deps.registry.entry(BlobStore, names[0])
        instance = entry.factory(None)
        if not isinstance(instance, BlobTargetHolding):
            return
        try:

            async def _drop(instance: BlobTargetHolding = instance) -> Outcome[None]:
                await instance.drop_target(name)
                return Produced(value=None)

            await wrap(
                _drop,
                distribution=entry.distribution,
                contract=BlobStore.__qualname__,
                plugin=names[0],
                stage="target:blob-drop",
            )()
        finally:
            await aclose(
                instance,
                distribution=entry.distribution,
                contract=BlobStore.__qualname__,
                plugin=names[0],
            )


def register_target_commands(registrar: PackRegistrar) -> None:
    """Register `target promote`/`target rollback`/`target drop` — called from `weft_cli.
    commands.register`, right after `"target list"` is added, never from a second entry point.
    """
    registrar.add(Command, "target promote", TargetPromoteCommand)
    registrar.add(Command, "target rollback", TargetRollbackCommand)
    registrar.add(Command, "target drop", TargetDropCommand)


__all__ = [
    "TargetDropArgs",
    "TargetDropCommand",
    "TargetDropCommandResult",
    "TargetPromoteArgs",
    "TargetPromoteCommand",
    "TargetPromoteCommandResult",
    "TargetRollbackCommand",
    "TargetRollbackCommandResult",
    "register_target_commands",
]
