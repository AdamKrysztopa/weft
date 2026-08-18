"""The linear runner — an explicit, ordered `StageSpec` list, resolved once and run batch by batch.

Specified in `docs/06-phase-0-build.md` step 6 and `docs/02-extension-model.md`
section 1 ("What a plugin receives", "Composition is typed and checked at
load"). This is the second of `06`'s three places Phase 0 could accidentally
settle **G2** (pipeline derivation semantics, open): a pipeline here is a
`Sequence[StageSpec]` a caller writes out in full. No `extends`, `insert`,
`replace`, `remove` or `set`, and no derivation of any kind — that machinery
is Phase 1's, after G2 closes. `06`: *"a plan with no derivation operators
cannot silently place a stage between two cleaning stages, which is exactly
why the choice is shaped this way."*

**`Lifetime` and `Stage[In, Out]` are built here**, not in an earlier step,
because nothing before this one needed them: step 3 (the seam) wraps a bare
async callable with no opinion on what it is a method of; step 4 (the
passport) hands `Context` to whatever calls it; discovery (step 5) registers
factories, never instances. The runner is the first thing that has to
*resolve and run a chain of them*, which is what forces the shape a plugin
class must have.

**Three checks happen before a single batch runs — "at resolution", never
discovered later as a runtime `KeyError`** (`06` step 6):

1. **The plugin exists.** `Registry.entry` already raises `UnknownPluginError`
   naming the contract, the name that was wanted, and every name that *is*
   registered — reused here unchanged, not re-implemented.
2. **`requires` is produced by an earlier stage.** Checked model by model
   against the `provides` every earlier stage in the same list declared,
   accumulated as resolution walks the list in order. A miss raises
   `PipelineResolutionError` naming the stage, the missing `ExtModel` and its
   `__namespace__` — which doubles as the pack that owns it, the same
   convention `docs/02-extension-model.md` section 1 uses throughout.
3. **Consecutive stages compose by type.** `Stage[In, Out]` — see below for
   where `In`/`Out` actually come from.

**Where a pipeline's types actually come from — a narrowing worth stating
plainly.** `docs/02-extension-model.md` → *Composition is typed and checked
at load* writes `Stage[In, Out]` once per *contract*, not once per plugin —
see that section for the per-capability examples the kernel itself does not
restate. That reading is what this module implements: a `StageSpec.contract`
is expected to declare `Stage[In, Out]` as one of its own bases, and the
composition check reads `In`/`Out` off the *contract* via `__orig_bases__` —
never off the plugin, which may satisfy a contract structurally with no
declared base at all. This is a deliberate, documented choice, not an
oversight: contracts are few and already generic, one plugin implementing
several contracts would otherwise have to restate the same pair of types
redundantly, and Phase 0 has no contract yet to prove the alternative against
— step 7 is expected to follow this convention, and `docs/02-extension-model.md`
§1 carries the same note.

**`requires`, `provides` and `lifetime` are read off the constructed
instance, defensively, and `Stage` declares none of them.** `run` is the
only member `Stage`'s body carries. `typing.Protocol` computes
`__protocol_attrs__` — the set `isinstance` checks against on a
`@runtime_checkable` Protocol — by walking every base class's `__dict__`,
`Stage` included; a `ClassVar` declared on `Stage` would therefore become a
required `isinstance` member of every contract built on `Stage[In, Out]`
(`Chunker`, `Extractor`, `NodeStore`, …), not merely an inheritable
convenience. `getattr(instance, name, default)` already supplies
`Lifetime.RUN` / `()` / `()` when a plugin never sets them — whether or not
that plugin inherits `Stage` at all — so nothing about correctness depends
on `Stage` declaring these, only on the runner reading them defensively.
See `docs/02-extension-model.md`'s Phase 0 step 7 narrowing note.

**The instance cache honours `Lifetime`.** Keyed `(tenant_id, contract, name,
config_hash)`, per `docs/02-extension-model.md` section 1 — `config_hash` is
a content hash rather than the config object itself, so a config holding an
unhashable field (a plain `dict`, say) does not make caching impossible.
`Lifetime.RUN` — the default — is never written to the cache: a fresh
instance is built every time `resolve()` runs, reused only for the stages of
*that* `ResolvedPipeline`, exactly as "a fresh instance per pipeline run, no
thread-safety obligation on the author" describes. `Lifetime.PROCESS` is
written once and read back by every later `resolve()` call sharing the same
key, on the same `Runner` — which is therefore expected to live for the
process, not be rebuilt per run, or the cache buys nothing.

**`flush()` is the runner's, never a stage's.** `docs/02-extension-model.md`:
"there is no `persist()`... `add()` may buffer; **the kernel runner calls
`flush`** at the end of a run and on cancellation, so no plugin can forget
it." The kernel names no capability, so it cannot know which stages own
persistence — instead every resolved instance that happens to expose an
async, callable `flush()` is flushed, once, whether or not it needs one.
`flush` is documented as idempotent, so calling it on something that has
nothing to flush is a legitimate no-op, never a hazard. Every stage gets its
chance regardless of an earlier one's failure — see `_flush_all` — and each
call carries the same span and attribution `weft_kernel.seam.wrap` gives
`run()`, via `weft_kernel.seam.wrap_flush`.

**`run` returns a `RunSummary`, sized by outcome count, never by payload.**
`docs/02-extension-model.md` → *Composition is typed and checked at load*:
"the kernel runner owns batching, so memory is bounded by batch size rather
than corpus size." Retaining every batch's whole `Outcome` — in particular a
`Produced` batch's produced value — for the life of a run would make that
false for the one component that owns the promise: peak memory would grow
with the corpus, not the batch. `RunSummary` carries only counts of
`Produced` / `NothingToProduce` / `Failed`, plus the reasons the latter two
gave, so a batch's payload is free to be collected the moment it has been
counted.

**One batch in flight**, per `01` → *Colour*: `run` walks its batches with a
plain `async for`, awaiting one batch's whole chain of stages before the next
batch's `__anext__` is even requested. No `asyncio.gather`, no per-batch task
— parallelism, if a stage wants it, is the stage's own concern over the one
batch it was handed.

**`CancelledError` propagates untouched — including when its own cleanup
fails.** `run` catches `BaseException`, not `Exception`, around the batch
loop, so a `CancelledError` raised mid-run still reaches `_flush_all` before
`raise` sends it on. Every stage still gets its chance to flush. The
narrower hazard is what `_flush_all` normally does on a flush failure:
it raises `FlushError`, and raising anything from inside an `except` block
handling `exc` replaces `exc` on the way out — a `CancelledError` would
surface only as `FlushError.__context__`, silently converting a cancelled
task into one that merely raised. So `_flush_all` takes the exception
already in flight and, when one is present, never raises on top of it: a
flush failure is attached to it as a note instead. The result is `01` →
*Colour*'s requirement exactly: never caught, never rewritten, whether or
not cleanup itself succeeds.
"""

from __future__ import annotations

import hashlib
import typing
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, cast

from pydantic import BaseModel, ConfigDict

from weft_kernel.context import Context
from weft_kernel.errors import WeftError
from weft_kernel.payload import ExtModel, NothingToProduce, Outcome, Produced
from weft_kernel.registry import Registry
from weft_kernel.seam import wrap, wrap_flush


class Lifetime(StrEnum):
    """How long one resolved stage instance may be reused. `02` §1 → *What a plugin receives*."""

    RUN = "run"
    PROCESS = "process"


class Stage[In, Out](Protocol):
    """The shape every registered plugin class satisfies. `02` §1 → *What a plugin receives*.

    A contract publishes this specialised — see `docs/02-extension-model.md`
    → *Composition is typed and checked at load* for the per-capability
    examples — which is what the composition check in this module reads back
    via `__orig_bases__`. A plugin implementing that contract does not need
    to name `Stage` itself.

    **`run` is the only member declared here, deliberately.** `Lifetime`,
    `requires` and `provides` are conventions a plugin *may* set — read
    defensively off the constructed instance by `_lifetime_of`,
    `_requires_of` and `_provides_of` below — never declared as `ClassVar`s
    on this Protocol. See the module docstring, *"`requires`, `provides` and
    `lifetime` are read off the constructed instance, defensively, and
    `Stage` declares none of them."*
    """

    async def run(self, payload: In, ctx: Context) -> Outcome[Out]: ...


class PipelineResolutionError(WeftError):
    """A `StageSpec` list failed a resolution check — never discovered later as a `KeyError`.

    Covers the two checks `Registry.entry`'s own `UnknownPluginError` does
    not: an unmet `requires`, and two consecutive stages that do not compose
    by type. Both name the stage that failed, and both name what would have
    made it pass.
    """


class TenantMismatchError(WeftError):
    """`run()` was given a `Context` for a tenant this pipeline was not resolved for.

    `docs/02-extension-model.md`'s cache note is explicit: the instance
    cache is keyed `(tenant_id, contract, name, config_hash)`, and "the
    tenant is in the key or multi-tenancy is broken on day one." A
    `ResolvedPipeline` remembers the tenant `resolve()` built it for; `run()`
    refuses rather than silently executing it against a different tenant's
    `Context`, naming both.
    """


class FlushError(WeftError):
    """One or more resolved stages failed to flush. Raised once, after every stage was tried.

    `Runner._flush_all` gives every stage a chance to flush regardless of an
    earlier one's failure — a completed run must stay durable even when an
    unrelated stage's flush raised, and the store is normally last in the
    list. `__cause__` is the first failure encountered, so its traceback is
    never lost; the message names every stage that failed.
    """


@dataclass(frozen=True, slots=True)
class StageSpec:
    """One named position in an explicit, fully-written-out pipeline.

    `06` step 6's half of G2's minimal, reversible choice: a pipeline is a
    plain `Sequence[StageSpec]`, never a derivation. `id` is what resolution
    errors and `weft_kernel.seam.wrap`'s span both use to say which stage
    failed or ran.
    """

    id: str
    contract: type[object]
    name: str
    config: object = None


@dataclass(frozen=True, slots=True)
class _ResolvedStage:
    """One `StageSpec`, checked and instantiated. Built only by `Runner.resolve`."""

    id: str
    contract_name: str
    plugin_name: str
    distribution: str
    instance: object


@dataclass(frozen=True, slots=True)
class ResolvedPipeline:
    """A `StageSpec` list after every resolution check in `06` step 6 has passed.

    What `Runner.run` executes. Never constructed directly — see
    `Runner.resolve`. `tenant_id` is the tenant `resolve()` built every
    cached instance for; `run()` checks a `Context` against it — see
    `TenantMismatchError`.
    """

    tenant_id: str
    stages: tuple[_ResolvedStage, ...]


class RunSummary(BaseModel):
    """What a run produced, sized by outcome count — never by a batch's payload.

    See the module docstring, *"`run` returns a `RunSummary`..."*. Every
    field is a count or a tuple of short reason strings, never a produced
    value, so this object's size tracks the number of batches a run saw, not
    the volume of data any one of them carried.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    produced: int = 0
    nothing_to_produce: int = 0
    failed: int = 0
    nothing_to_produce_reasons: tuple[str, ...] = ()
    failed_reasons: tuple[str, ...] = ()


_FlushFn = Callable[[], Awaitable[None]]


class Runner:
    """Resolves an explicit `StageSpec` list once, then runs it batch by batch.

    One `Runner` is expected to live for the process — its instance cache is
    where `Lifetime.PROCESS` stages are actually reused across separate
    `resolve()` calls; a `Runner` rebuilt per call defeats that half of the
    contract.
    """

    def __init__(self, registry: Registry) -> None:
        self._registry = registry
        self._process_cache: dict[tuple[str, type[object], str, str], object] = {}

    def resolve(self, specs: Sequence[StageSpec], *, tenant_id: str) -> ResolvedPipeline:
        """Check plugin existence, `requires`/`provides` and `Stage[In, Out]` composition.

        Raises `UnknownPluginError` (via `Registry.entry`) if a plugin name
        was never registered, or `PipelineResolutionError` if a `requires`
        goes unmet or two consecutive stages do not compose. Nothing here
        runs a stage — see `run`.
        """
        if not specs:
            return ResolvedPipeline(tenant_id=tenant_id, stages=())

        _check_composition(specs)

        resolved: list[_ResolvedStage] = []
        provided_models: set[type[ExtModel]] = set()
        for spec in specs:
            entry = self._registry.entry(spec.contract, spec.name)
            key = (tenant_id, spec.contract, spec.name, _config_hash(spec.config))

            instance = self._process_cache.get(key)
            if instance is None:
                instance = entry.factory(spec.config)
                if _lifetime_of(instance) is Lifetime.PROCESS:
                    self._process_cache[key] = instance

            for required in _requires_of(instance):
                if required not in provided_models:
                    raise PipelineResolutionError(
                        f"stage '{spec.id}' ({spec.contract.__name__}:{spec.name}) requires "
                        f"'{required.__name__}' — namespace '{required.__namespace__}', "
                        f"published by the pack of that name — but no earlier stage in this "
                        f"pipeline provides it."
                    )
            provided_models.update(_provides_of(instance))

            resolved.append(
                _ResolvedStage(
                    id=spec.id,
                    contract_name=spec.contract.__name__,
                    plugin_name=spec.name,
                    distribution=entry.distribution,
                    instance=instance,
                )
            )

        return ResolvedPipeline(tenant_id=tenant_id, stages=tuple(resolved))

    async def run(
        self, pipeline: ResolvedPipeline, batches: AsyncIterator[object], ctx: Context
    ) -> RunSummary:
        """Run every batch through the whole stage list, one batch in flight, `flush()` at the end.

        Raises `TenantMismatchError`, naming both tenants, if `ctx.tenant_id`
        does not match the tenant `pipeline` was resolved for — the instance
        cache is keyed by tenant, so running it for a different one would
        silently reach across that boundary. A batch that any stage answers
        with `NothingToProduce` or `Failed` stops there — the remaining
        stages never see it, and that outcome counts toward the returned
        `RunSummary` without its payload (there is none) or reason being
        retained past that count. `flush()` is called on every resolved
        instance that has one, once, whether this loop finishes normally or
        an exception — `CancelledError` above all — cuts it off mid-batch; a
        flush failure in that second case never displaces the exception
        already propagating, which continues on unmodified. See `_flush_all`.
        """
        if ctx.tenant_id != pipeline.tenant_id:
            raise TenantMismatchError(
                f"this pipeline was resolved for tenant '{pipeline.tenant_id}', but run() "
                f"was given a Context for tenant '{ctx.tenant_id}'. An instance cached for "
                f"one tenant must never run for another."
            )

        produced = 0
        nothing_to_produce = 0
        failed = 0
        nothing_to_produce_reasons: list[str] = []
        failed_reasons: list[str] = []
        try:
            async for batch in batches:
                outcome = await self._run_one_batch(pipeline, batch, ctx)
                if isinstance(outcome, Produced):
                    produced += 1
                elif isinstance(outcome, NothingToProduce):
                    nothing_to_produce += 1
                    nothing_to_produce_reasons.append(outcome.reason)
                else:
                    failed += 1
                    failed_reasons.append(outcome.reason)
        except BaseException as exc:
            # An exception already in flight — `CancelledError` above all — must reach the
            # caller untouched. `_flush_all` still runs and every stage still gets its chance,
            # but a flush failure is attached to `exc` rather than raised as `FlushError`,
            # which would otherwise replace `exc` in Python's exception chain. See the module
            # docstring, *"`CancelledError` propagates untouched."*
            await self._flush_all(pipeline, in_flight=exc)
            raise
        else:
            await self._flush_all(pipeline)
        return RunSummary(
            produced=produced,
            nothing_to_produce=nothing_to_produce,
            failed=failed,
            nothing_to_produce_reasons=tuple(nothing_to_produce_reasons),
            failed_reasons=tuple(failed_reasons),
        )

    async def _run_one_batch(
        self, pipeline: ResolvedPipeline, batch: object, ctx: Context
    ) -> Outcome[object]:
        payload = batch
        for stage in pipeline.stages:
            runnable = cast("Stage[object, object]", stage.instance)
            wrapped_run = wrap(
                runnable.run,
                distribution=stage.distribution,
                contract=stage.contract_name,
                plugin=stage.plugin_name,
                stage=stage.id,
            )
            outcome = await wrapped_run(payload, ctx)
            if not isinstance(outcome, Produced):
                return outcome
            payload = outcome.value
        return Produced(value=payload)

    async def _flush_all(
        self, pipeline: ResolvedPipeline, *, in_flight: BaseException | None = None
    ) -> None:
        """Flush every resolved stage once, regardless of an earlier one's failure.

        Each flush runs through `weft_kernel.seam.wrap_flush`, so a failure
        carries the same span and pack/contract/plugin/stage attribution a
        stage's `run()` gets. Every stage is tried — a completed run must
        stay durable even when one stage's flush fails and another (normally
        the store, last in the list) would otherwise never get the chance.

        `in_flight` is the exception already propagating out of `run()`'s
        batch loop, if any. When it is `None` (the ordinary end of a
        successful run), flush failures are collected and raised together,
        once, as a single `FlushError` whose `__cause__` is the first one
        encountered — the caller has nothing else it is already about to
        raise, so `FlushError` is the loudest correct thing to raise. When
        `in_flight` is not `None`, raising here would replace it — Python
        lets an exception raised inside an `except` block's handling
        displace the one being handled — so a flush failure is instead
        attached to `in_flight` as a note and `in_flight` is left to
        propagate exactly as it arrived. This is what keeps a `CancelledError`
        a `CancelledError` even when the cleanup it triggers itself fails; see
        the module docstring, *"`CancelledError` propagates untouched."*
        """
        failures: list[WeftError] = []
        for stage in pipeline.stages:
            flush = _flush_of(stage.instance)
            if flush is None:
                continue
            wrapped_flush = wrap_flush(
                flush,
                distribution=stage.distribution,
                contract=stage.contract_name,
                plugin=stage.plugin_name,
                stage=stage.id,
            )
            try:
                await wrapped_flush()
            except WeftError as exc:
                failures.append(exc)

        if not failures:
            return

        failed_stages = ", ".join(f"'{exc.stage}'" for exc in failures)
        message = (
            f"{len(failures)} of {len(pipeline.stages)} stage(s) failed to flush: {failed_stages}."
        )
        if in_flight is not None:
            in_flight.add_note(f"FlushError: {message}")
            return
        raise FlushError(message) from failures[0]


def _stage_signature(contract: type[object]) -> tuple[object, object]:
    """The `(In, Out)` `contract` declared via `Stage[In, Out]` as one of its own bases."""
    for base in getattr(contract, "__orig_bases__", ()):
        if typing.get_origin(base) is Stage:
            args = typing.get_args(base)
            if len(args) == 2:  # noqa: PLR2004 - Stage is fixed at two type parameters
                return args[0], args[1]
    raise PipelineResolutionError(
        f"'{contract.__name__}' does not declare Stage[In, Out] as a base — every contract "
        f"used in a pipeline states what it consumes and produces, e.g. "
        f"class YourContract(Stage[list[In], list[Out]], Protocol)."
    )


def _check_composition(specs: Sequence[StageSpec]) -> None:
    """Every consecutive pair of `specs` composes: one stage's `Out` is the next stage's `In`."""
    previous: tuple[str, object] | None = None
    for spec in specs:
        payload_type, produced_type = _stage_signature(spec.contract)
        if previous is not None:
            previous_id, previous_produced = previous
            if previous_produced != payload_type:
                raise PipelineResolutionError(
                    f"stage '{spec.id}' ({spec.contract.__name__}:{spec.name}) expects "
                    f"{payload_type!r}, but the previous stage '{previous_id}' produces "
                    f"{previous_produced!r}. Consecutive stages must compose by type."
                )
        previous = (spec.id, produced_type)


def _config_hash(config: object) -> str:
    """A stable digest of `config`, for the instance cache key.

    A content hash rather than `config` itself: the cache key must be
    hashable even when `config` is a Pydantic model carrying an unhashable
    field (a plain `dict`, say), which `frozen=True` alone does not fix.
    """
    payload = config.model_dump_json() if isinstance(config, BaseModel) else repr(config)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _lifetime_of(instance: object) -> Lifetime:
    return cast(Lifetime, getattr(instance, "lifetime", Lifetime.RUN))


def _requires_of(instance: object) -> tuple[type[ExtModel], ...]:
    return cast("tuple[type[ExtModel], ...]", getattr(instance, "requires", ()))


def _provides_of(instance: object) -> tuple[type[ExtModel], ...]:
    return cast("tuple[type[ExtModel], ...]", getattr(instance, "provides", ()))


def _flush_of(instance: object) -> _FlushFn | None:
    """`instance.flush`, if it has one and it is callable — never a bare `TypeError` later.

    An attribute merely named `flush` that is not callable (a plain value, an
    author's typo) is treated the same as no `flush` at all: `flush` is
    documented as an optional method, not a required, checked-elsewhere one.
    """
    found = getattr(instance, "flush", None)
    if found is None or not callable(found):
        return None
    return cast(_FlushFn, found)
