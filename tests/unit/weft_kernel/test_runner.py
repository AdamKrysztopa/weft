"""Unit tests for `weft_kernel.runner`.

Mirrors `packages/weft-kernel/src/weft_kernel/runner.py`. Covers a full
resolve-then-run over an explicit `StageSpec` list, `requires`/`provides`
threading a *model* — not merely its namespace string — from one stage to the
next, `Lifetime` honoured by the instance cache (`PROCESS` reused across
`resolve()` calls, `RUN` rebuilt every time), the three resolution failures —
an unregistered plugin, a `requires` no earlier stage provides, and two
stages that do not compose by type — none of them a bare `KeyError`, the
runtime properties `06` step 6 names explicitly (one batch in flight,
`flush()` owned by the runner and called once whether a run finishes
normally or `CancelledError` cuts it off mid-batch), `run()` refusing a
`Context` for a tenant the pipeline was not resolved for, `RunSummary` not
retaining a batch's payload past the count, and every stage getting a chance
to flush even when an earlier one raises.

Stand-in contracts (`_TextStage`, `_CountStage`) declare `Stage[In, Out]` as
their own base, exactly as `runner.py`'s module docstring says a real
contract must — the plugin classes under them satisfy the contract
structurally, with no inheritance of their own, to prove that path works
too.

**Task 1.6, `02` §3 → *Applicability*.** `_NodeStage` and `_NaiveSplitter`
below are this file's own worked example of `docs/11-multimodal.md` §2's
claim: "a third-party chunker that has never heard of tables still leaves
an atomic table unsplit, because the seam does it." `_NaiveSplitter.run`
carries no conditional on a node's content at all — it splits whatever it
is handed, unconditionally — so if the atomic node in
`test_run_routes_only_nodes_matching_applies_to_through_a_stage` came out
split, the only place that could have happened is the runner routing it
there, which is exactly what the test's own assertions rule out.
"""

import asyncio
import gc
import time
import weakref
from collections.abc import AsyncIterator, Callable, Sequence
from typing import Protocol

import pytest

from weft_kernel import runner
from weft_kernel.blocking import BlockingCallError
from weft_kernel.context import Context
from weft_kernel.errors import WeftError
from weft_kernel.payload import (
    Applies,
    ExtModel,
    Failed,
    MediaType,
    Node,
    NothingToProduce,
    Outcome,
    Produced,
    Property,
)
from weft_kernel.registry import Registry, UnknownPluginError


class _TextStage(runner.Stage[list[str], list[str]], Protocol):
    async def run(self, payload: list[str], ctx: Context) -> Outcome[list[str]]: ...


class _CountStage(runner.Stage[list[str], int], Protocol):
    async def run(self, payload: list[str], ctx: Context) -> Outcome[int]: ...


class _NodeStage(runner.Stage[Sequence[Node], Sequence[Node]], Protocol):
    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]: ...


class _Uppercased(ExtModel):
    __namespace__ = "weft-test-pack"

    note: str = "uppercased"


class _WordBoundaries(Property):
    """`02` §3's own example: a fact hyphenation repair needs intact, chunking can destroy."""

    __namespace__ = "weft-test-pack"


def _ctx() -> Context:
    return Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")


class _Uppercase:
    lifetime = runner.Lifetime.RUN
    requires: tuple[type[ExtModel], ...] = ()
    provides = (_Uppercased,)

    def __init__(self, config: object) -> None:
        self.config = config

    async def run(self, payload: list[str], ctx: Context) -> Outcome[list[str]]:
        return Produced(value=[item.upper() for item in payload])


class _Count:
    lifetime = runner.Lifetime.RUN
    requires = (_Uppercased,)
    provides: tuple[type[ExtModel], ...] = ()

    def __init__(self, config: object) -> None:
        self.config = config

    async def run(self, payload: list[str], ctx: Context) -> Outcome[int]:
        return Produced(value=len(payload))


async def test_resolve_and_run_thread_every_batch_through_the_whole_stage_list() -> None:
    # Arrange
    registry = Registry()
    registry.add(_TextStage, "upper", _Uppercase, distribution="weft-test-pack")
    registry.add(_CountStage, "count", _Count, distribution="weft-test-pack")
    engine = runner.Runner(registry)
    specs = (
        runner.StageSpec(id="upper", contract=_TextStage, name="upper"),
        runner.StageSpec(id="count", contract=_CountStage, name="count"),
    )

    async def batches() -> AsyncIterator[list[str]]:
        yield ["a", "b"]
        yield ["c"]

    # Act
    pipeline = engine.resolve(specs, tenant_id="tenant-a")
    summary = await engine.run(pipeline, batches(), _ctx())

    # Assert
    assert summary == runner.RunSummary(produced=2)


def test_resolve_reuses_a_process_lifetime_instance_across_separate_resolves() -> None:
    # Arrange
    built: list[object] = []

    class _Cached:
        lifetime = runner.Lifetime.PROCESS
        requires: tuple[type[ExtModel], ...] = ()
        provides: tuple[type[ExtModel], ...] = ()

        def __init__(self, config: object) -> None:
            built.append(config)

        async def run(self, payload: list[str], ctx: Context) -> Outcome[list[str]]:
            return Produced(value=payload)

    registry = Registry()
    registry.add(_TextStage, "cached", _Cached, distribution="weft-test-pack")
    engine = runner.Runner(registry)
    specs = (runner.StageSpec(id="s1", contract=_TextStage, name="cached"),)

    # Act
    first = engine.resolve(specs, tenant_id="tenant-a")
    second = engine.resolve(specs, tenant_id="tenant-a")

    # Assert
    assert first.stages[0].instance is second.stages[0].instance
    assert len(built) == 1


def test_resolve_builds_a_fresh_run_lifetime_instance_every_call() -> None:
    # Arrange
    registry = Registry()
    registry.add(_TextStage, "upper", _Uppercase, distribution="weft-test-pack")
    engine = runner.Runner(registry)
    specs = (runner.StageSpec(id="s1", contract=_TextStage, name="upper"),)

    # Act
    first = engine.resolve(specs, tenant_id="tenant-a")
    second = engine.resolve(specs, tenant_id="tenant-a")

    # Assert
    assert first.stages[0].instance is not second.stages[0].instance


def test_resolve_fails_loudly_for_an_unregistered_plugin_name() -> None:
    # Arrange
    registry = Registry()
    engine = runner.Runner(registry)
    specs = (runner.StageSpec(id="s1", contract=_TextStage, name="missing"),)

    # Act / Assert
    with pytest.raises(UnknownPluginError) as excinfo:
        engine.resolve(specs, tenant_id="tenant-a")

    assert "missing" in str(excinfo.value)


def test_resolve_fails_on_an_unmet_requires_naming_the_stage_namespace_and_pack() -> None:
    # Arrange
    class _Needs:
        lifetime = runner.Lifetime.RUN
        requires = (_Uppercased,)
        provides: tuple[type[ExtModel], ...] = ()

        def __init__(self, config: object) -> None: ...

        async def run(self, payload: list[str], ctx: Context) -> Outcome[list[str]]:
            return Produced(value=payload)

    registry = Registry()
    registry.add(_TextStage, "needs-upper", _Needs, distribution="weft-test-pack")
    engine = runner.Runner(registry)
    specs = (runner.StageSpec(id="s1", contract=_TextStage, name="needs-upper"),)

    # Act / Assert — the specific subclass, not the family base: task 1.13 moved
    # `UnmetRequiresError` here precisely so `Runner.resolve` stops raising the bare
    # `PipelineResolutionError` for this check; a test that only asserts the base would
    # never notice a regression back to that fat-class shape (reviewer finding).
    with pytest.raises(runner.UnmetRequiresError) as excinfo:
        engine.resolve(specs, tenant_id="tenant-a")

    message = str(excinfo.value)
    assert "s1" in message
    assert "_Uppercased" in message
    assert "weft-test-pack" in message
    assert excinfo.value.stages == ("s1",)
    assert excinfo.value.distributions == ("weft-test-pack",)


class _DestroysWordBoundaries:
    """A stand-in for `weft_chunk.fixed_size.FixedSizeChunker` — task 1.2's own example."""

    lifetime = runner.Lifetime.RUN
    requires: tuple[type[ExtModel], ...] = ()
    provides: tuple[type[ExtModel], ...] = ()
    destroys: tuple[type[Property], ...] = (_WordBoundaries,)

    def __init__(self, config: object) -> None: ...

    async def run(self, payload: list[str], ctx: Context) -> Outcome[list[str]]:
        return Produced(value=payload)


class _NeedsWordBoundariesIntact:
    """A stand-in for a hyphenation-repair stage — `02` §3's own worked example."""

    lifetime = runner.Lifetime.RUN
    requires: tuple[type[ExtModel], ...] = ()
    provides: tuple[type[ExtModel], ...] = ()
    intact: tuple[type[Property], ...] = (_WordBoundaries,)
    destroys: tuple[type[Property], ...] = ()

    def __init__(self, config: object) -> None: ...

    async def run(self, payload: list[str], ctx: Context) -> Outcome[list[str]]:
        return Produced(value=payload)


def test_resolve_fails_when_an_earlier_stage_destroyed_a_property_this_stage_needs_intact() -> None:
    # Arrange
    registry = Registry()
    registry.add(_TextStage, "chunk", _DestroysWordBoundaries, distribution="weft-chunk")
    registry.add(_TextStage, "hyphenation", _NeedsWordBoundariesIntact, distribution="acme-clean")
    engine = runner.Runner(registry)
    specs = (
        runner.StageSpec(id="chunk", contract=_TextStage, name="chunk"),
        runner.StageSpec(id="hyphenation", contract=_TextStage, name="hyphenation"),
    )

    # Act / Assert — the specific subclass (reviewer finding; see the identical note on
    # `test_resolve_fails_on_an_unmet_requires_naming_the_stage_namespace_and_pack` above).
    with pytest.raises(runner.IntactViolationError) as excinfo:
        engine.resolve(specs, tenant_id="tenant-a")

    message = str(excinfo.value)
    assert "hyphenation" in message
    assert "chunk" in message
    assert "_WordBoundaries" in message
    assert excinfo.value.stages == ("hyphenation", "chunk")


def test_resolve_succeeds_when_the_stage_needing_intact_runs_before_the_one_that_destroys_it() -> (
    None
):
    # Arrange — reordered: the position `02` §3 says would be legal.
    registry = Registry()
    registry.add(_TextStage, "hyphenation", _NeedsWordBoundariesIntact, distribution="acme-clean")
    registry.add(_TextStage, "chunk", _DestroysWordBoundaries, distribution="weft-chunk")
    engine = runner.Runner(registry)
    specs = (
        runner.StageSpec(id="hyphenation", contract=_TextStage, name="hyphenation"),
        runner.StageSpec(id="chunk", contract=_TextStage, name="chunk"),
    )

    # Act
    pipeline = engine.resolve(specs, tenant_id="tenant-a")

    # Assert
    assert [stage.id for stage in pipeline.stages] == ["hyphenation", "chunk"]


def test_resolve_does_not_require_intact_when_nothing_destroyed_the_property() -> None:
    # Arrange — `destroys` on one stage that no later stage ever needs `intact` is a harmless
    # no-op, not a resolution failure: `02` §3 makes `destroys` mandatory to *declare*, never
    # mandatory to be *needed* by anything else in this particular pipeline.
    registry = Registry()
    registry.add(_TextStage, "chunk", _DestroysWordBoundaries, distribution="weft-chunk")
    engine = runner.Runner(registry)
    specs = (runner.StageSpec(id="chunk", contract=_TextStage, name="chunk"),)

    # Act
    pipeline = engine.resolve(specs, tenant_id="tenant-a")

    # Assert
    assert [stage.id for stage in pipeline.stages] == ["chunk"]


def _never_built(config: object) -> None:
    """A factory the composition check must never call — see the test below."""
    raise AssertionError("composition must fail before any factory is called")


def test_resolve_fails_at_load_when_consecutive_stages_do_not_compose() -> None:
    # Arrange
    registry = Registry()
    registry.add(_CountStage, "count", _never_built, distribution="weft-test-pack")
    registry.add(_TextStage, "upper", _never_built, distribution="weft-test-pack")
    engine = runner.Runner(registry)
    specs = (
        runner.StageSpec(id="count", contract=_CountStage, name="count"),
        runner.StageSpec(id="upper", contract=_TextStage, name="upper"),
    )

    # Act / Assert — the specific subclass (reviewer finding; see the identical note on
    # `test_resolve_fails_on_an_unmet_requires_naming_the_stage_namespace_and_pack` above).
    with pytest.raises(runner.StageCompositionError) as excinfo:
        engine.resolve(specs, tenant_id="tenant-a")

    message = str(excinfo.value)
    assert "count" in message
    assert "upper" in message
    assert excinfo.value.stages == ("count", "upper")


async def test_run_stops_the_chain_for_a_batch_that_produces_nothing() -> None:
    # Arrange
    class _NothingHere:
        lifetime = runner.Lifetime.RUN
        requires: tuple[type[ExtModel], ...] = ()
        provides: tuple[type[ExtModel], ...] = ()

        def __init__(self, config: object) -> None: ...

        async def run(self, payload: list[str], ctx: Context) -> Outcome[list[str]]:
            return NothingToProduce(reason="nothing extracted")

    called_next: list[list[str]] = []

    class _NeverCalled:
        lifetime = runner.Lifetime.RUN
        requires: tuple[type[ExtModel], ...] = ()
        provides: tuple[type[ExtModel], ...] = ()

        def __init__(self, config: object) -> None: ...

        async def run(self, payload: list[str], ctx: Context) -> Outcome[list[str]]:
            called_next.append(payload)
            return Produced(value=payload)

    registry = Registry()
    registry.add(_TextStage, "nothing", _NothingHere, distribution="weft-test-pack")
    registry.add(_TextStage, "never", _NeverCalled, distribution="weft-test-pack")
    engine = runner.Runner(registry)
    specs = (
        runner.StageSpec(id="s1", contract=_TextStage, name="nothing"),
        runner.StageSpec(id="s2", contract=_TextStage, name="never"),
    )

    async def batches() -> AsyncIterator[list[str]]:
        yield ["a"]

    # Act
    pipeline = engine.resolve(specs, tenant_id="tenant-a")
    summary = await engine.run(pipeline, batches(), _ctx())

    # Assert
    assert summary == runner.RunSummary(
        nothing_to_produce=1, nothing_to_produce_reasons=("nothing extracted",)
    )
    assert called_next == []


async def test_run_keeps_exactly_one_batch_in_flight_at_a_time() -> None:
    # Arrange
    events: list[str] = []

    class _Marks:
        lifetime = runner.Lifetime.RUN
        requires: tuple[type[ExtModel], ...] = ()
        provides: tuple[type[ExtModel], ...] = ()

        def __init__(self, config: object) -> None: ...

        async def run(self, payload: list[str], ctx: Context) -> Outcome[list[str]]:
            events.append(f"enter-{payload[0]}")
            await asyncio.sleep(0)
            events.append(f"exit-{payload[0]}")
            return Produced(value=payload)

    registry = Registry()
    registry.add(_TextStage, "marks", _Marks, distribution="weft-test-pack")
    engine = runner.Runner(registry)
    pipeline = engine.resolve(
        (runner.StageSpec(id="s1", contract=_TextStage, name="marks"),), tenant_id="tenant-a"
    )

    async def batches() -> AsyncIterator[list[str]]:
        yield ["1"]
        yield ["2"]

    # Act
    await engine.run(pipeline, batches(), _ctx())

    # Assert
    assert events == ["enter-1", "exit-1", "enter-2", "exit-2"]


async def test_run_flushes_every_stage_exactly_once_after_the_last_batch() -> None:
    # Arrange
    flushed: list[str] = []

    class _Flushable:
        lifetime = runner.Lifetime.RUN
        requires: tuple[type[ExtModel], ...] = ()
        provides: tuple[type[ExtModel], ...] = ()

        def __init__(self, config: object) -> None: ...

        async def run(self, payload: list[str], ctx: Context) -> Outcome[list[str]]:
            return Produced(value=payload)

        async def flush(self) -> None:
            flushed.append("flushed")

    registry = Registry()
    registry.add(_TextStage, "flush-me", _Flushable, distribution="weft-test-pack")
    engine = runner.Runner(registry)
    pipeline = engine.resolve(
        (runner.StageSpec(id="s1", contract=_TextStage, name="flush-me"),), tenant_id="tenant-a"
    )

    async def batches() -> AsyncIterator[list[str]]:
        yield ["a"]
        yield ["b"]

    # Act
    summary = await engine.run(pipeline, batches(), _ctx())

    # Assert
    assert summary == runner.RunSummary(produced=2)
    assert flushed == ["flushed"]


async def test_run_flushes_on_cancellation_and_lets_cancelled_error_propagate() -> None:
    # Arrange
    flushed: list[str] = []

    class _CancelsOnRun:
        lifetime = runner.Lifetime.RUN
        requires: tuple[type[ExtModel], ...] = ()
        provides: tuple[type[ExtModel], ...] = ()

        def __init__(self, config: object) -> None: ...

        async def run(self, payload: list[str], ctx: Context) -> Outcome[list[str]]:
            raise asyncio.CancelledError

        async def flush(self) -> None:
            flushed.append("flushed")

    registry = Registry()
    registry.add(_TextStage, "cancels", _CancelsOnRun, distribution="weft-test-pack")
    engine = runner.Runner(registry)
    pipeline = engine.resolve(
        (runner.StageSpec(id="s1", contract=_TextStage, name="cancels"),), tenant_id="tenant-a"
    )

    async def batches() -> AsyncIterator[list[str]]:
        yield ["a"]

    # Act / Assert
    with pytest.raises(asyncio.CancelledError):
        await engine.run(pipeline, batches(), _ctx())
    assert flushed == ["flushed"]


async def test_run_lets_cancelled_error_propagate_even_when_flush_also_fails() -> None:
    # Arrange — a stage whose `run` raises `CancelledError` and whose `flush` then raises too.
    # `FlushError` must never displace the cancellation that is already in flight.
    flushed: list[str] = []

    class _CancelsAndFailsToFlush:
        lifetime = runner.Lifetime.RUN
        requires: tuple[type[ExtModel], ...] = ()
        provides: tuple[type[ExtModel], ...] = ()

        def __init__(self, config: object) -> None: ...

        async def run(self, payload: list[str], ctx: Context) -> Outcome[list[str]]:
            raise asyncio.CancelledError

        async def flush(self) -> None:
            flushed.append("s1")
            raise ValueError("disk full")

    registry = Registry()
    registry.add(_TextStage, "cancels", _CancelsAndFailsToFlush, distribution="weft-test-pack")
    engine = runner.Runner(registry)
    pipeline = engine.resolve(
        (runner.StageSpec(id="s1", contract=_TextStage, name="cancels"),), tenant_id="tenant-a"
    )

    async def batches() -> AsyncIterator[list[str]]:
        yield ["a"]

    # Act / Assert
    with pytest.raises(asyncio.CancelledError):
        await engine.run(pipeline, batches(), _ctx())
    assert flushed == ["s1"]


async def test_resolve_checks_requires_by_model_type_not_merely_by_namespace_string() -> None:
    # Arrange — a second `ExtModel` that shares `_Uppercased`'s namespace string but is a
    # different type; requires must be checked by model, not by the namespace it collides on.
    class _OtherModelSameNamespace(ExtModel):
        __namespace__ = "weft-test-pack"

        note: str = "not-the-required-model"

    class _ProvidesTheOtherModel:
        lifetime = runner.Lifetime.RUN
        requires: tuple[type[ExtModel], ...] = ()
        provides = (_OtherModelSameNamespace,)

        def __init__(self, config: object) -> None: ...

        async def run(self, payload: list[str], ctx: Context) -> Outcome[list[str]]:
            return Produced(value=payload)

    class _NeedsUppercased:
        lifetime = runner.Lifetime.RUN
        requires = (_Uppercased,)
        provides: tuple[type[ExtModel], ...] = ()

        def __init__(self, config: object) -> None: ...

        async def run(self, payload: list[str], ctx: Context) -> Outcome[list[str]]:
            return Produced(value=payload)

    registry = Registry()
    registry.add(
        _TextStage, "provides-other", _ProvidesTheOtherModel, distribution="weft-test-pack"
    )
    registry.add(_TextStage, "needs-upper", _NeedsUppercased, distribution="weft-test-pack")
    engine = runner.Runner(registry)
    specs = (
        runner.StageSpec(id="s1", contract=_TextStage, name="provides-other"),
        runner.StageSpec(id="s2", contract=_TextStage, name="needs-upper"),
    )

    # Act / Assert — the specific subclass (reviewer finding; see the identical note on
    # `test_resolve_fails_on_an_unmet_requires_naming_the_stage_namespace_and_pack` above).
    with pytest.raises(runner.UnmetRequiresError) as excinfo:
        engine.resolve(specs, tenant_id="tenant-a")

    assert "_Uppercased" in str(excinfo.value)
    assert excinfo.value.stages == ("s2",)
    assert excinfo.value.distributions == ("weft-test-pack",)


async def test_run_refuses_a_context_for_a_tenant_the_pipeline_was_not_resolved_for() -> None:
    # Arrange
    registry = Registry()
    registry.add(_TextStage, "upper", _Uppercase, distribution="weft-test-pack")
    engine = runner.Runner(registry)
    pipeline = engine.resolve(
        (runner.StageSpec(id="s1", contract=_TextStage, name="upper"),), tenant_id="tenant-a"
    )
    other_tenant_ctx = Context(
        tenant_id="tenant-b", run_id="run-1", trace_id="trace-1", locale="en"
    )

    async def batches() -> AsyncIterator[list[str]]:
        yield ["a"]

    # Act / Assert
    with pytest.raises(runner.TenantMismatchError) as excinfo:
        await engine.run(pipeline, batches(), other_tenant_ctx)

    message = str(excinfo.value)
    assert "tenant-a" in message
    assert "tenant-b" in message


async def test_flush_all_flushes_every_stage_even_when_an_earlier_one_raises() -> None:
    # Arrange
    flushed: list[str] = []

    class _FailsToFlush:
        lifetime = runner.Lifetime.RUN
        requires: tuple[type[ExtModel], ...] = ()
        provides: tuple[type[ExtModel], ...] = ()

        def __init__(self, config: object) -> None: ...

        async def run(self, payload: list[str], ctx: Context) -> Outcome[list[str]]:
            return Produced(value=payload)

        async def flush(self) -> None:
            raise ValueError("disk full")

    class _FlushesFine:
        lifetime = runner.Lifetime.RUN
        requires: tuple[type[ExtModel], ...] = ()
        provides: tuple[type[ExtModel], ...] = ()

        def __init__(self, config: object) -> None: ...

        async def run(self, payload: list[str], ctx: Context) -> Outcome[list[str]]:
            return Produced(value=payload)

        async def flush(self) -> None:
            flushed.append("flushed")

    registry = Registry()
    registry.add(_TextStage, "fails", _FailsToFlush, distribution="weft-test-pack")
    registry.add(_TextStage, "fine", _FlushesFine, distribution="weft-test-pack")
    engine = runner.Runner(registry)
    specs = (
        runner.StageSpec(id="s1", contract=_TextStage, name="fails"),
        runner.StageSpec(id="s2", contract=_TextStage, name="fine"),
    )
    pipeline = engine.resolve(specs, tenant_id="tenant-a")

    async def batches() -> AsyncIterator[list[str]]:
        yield ["a"]

    # Act / Assert
    with pytest.raises(runner.FlushError) as excinfo:
        await engine.run(pipeline, batches(), _ctx())

    assert flushed == ["flushed"]
    assert "s1" in str(excinfo.value)
    assert isinstance(excinfo.value.__cause__, WeftError)


async def test_flush_of_treats_a_non_callable_flush_attribute_as_no_flush() -> None:
    # Arrange
    class _BogusFlush:
        lifetime = runner.Lifetime.RUN
        requires: tuple[type[ExtModel], ...] = ()
        provides: tuple[type[ExtModel], ...] = ()
        flush = "not-a-method"

        def __init__(self, config: object) -> None: ...

        async def run(self, payload: list[str], ctx: Context) -> Outcome[list[str]]:
            return Produced(value=payload)

    registry = Registry()
    registry.add(_TextStage, "bogus", _BogusFlush, distribution="weft-test-pack")
    engine = runner.Runner(registry)
    pipeline = engine.resolve(
        (runner.StageSpec(id="s1", contract=_TextStage, name="bogus"),), tenant_id="tenant-a"
    )

    async def batches() -> AsyncIterator[list[str]]:
        yield ["a"]

    # Act — a non-callable `flush` attribute must never reach a bare `await`.
    summary = await engine.run(pipeline, batches(), _ctx())

    # Assert
    assert summary == runner.RunSummary(produced=1)


class _WeighableBatch(list[str]):
    """A `list[str]` that supports `weakref.ref` — a plain `list` cannot."""


async def test_run_does_not_retain_a_produced_payload_past_the_batch_it_belongs_to() -> None:
    # Arrange — memory bounded by batch size, not corpus size (`02` → *Composition is typed
    # and checked at load*): once a batch has been counted, nothing in the returned
    # `RunSummary` may still hold it.
    class _Passthrough:
        lifetime = runner.Lifetime.RUN
        requires: tuple[type[ExtModel], ...] = ()
        provides: tuple[type[ExtModel], ...] = ()

        def __init__(self, config: object) -> None: ...

        async def run(self, payload: list[str], ctx: Context) -> Outcome[list[str]]:
            return Produced(value=payload)

    registry = Registry()
    registry.add(_TextStage, "pass", _Passthrough, distribution="weft-test-pack")
    engine = runner.Runner(registry)
    pipeline = engine.resolve(
        (runner.StageSpec(id="s1", contract=_TextStage, name="pass"),), tenant_id="tenant-a"
    )

    live_batches: list[_WeighableBatch] = [
        _WeighableBatch(["first"]),
        _WeighableBatch(["second"]),
    ]
    weak_refs = [weakref.ref(batch) for batch in live_batches]

    async def batches() -> AsyncIterator[list[str]]:
        while live_batches:
            yield live_batches.pop(0)

    # Act
    summary = await engine.run(pipeline, batches(), _ctx())
    gc.collect()

    # Assert
    assert summary == runner.RunSummary(produced=2)
    assert all(ref() is None for ref in weak_refs)


class _Prose(ExtModel):
    """A fact `_NaiveSplitter` genuinely needs — nothing about tables anywhere in it."""

    __namespace__ = "weft-test-pack"


def _prose_node(text: str) -> Node:
    return Node.synthetic(
        content=text, media_type=MediaType.TEXT, reason="applicability test fixture"
    ).with_ext(_Prose())


def _atomic_node(text: str) -> Node:
    """A node carrying no `_Prose` fact — `docs/11-multimodal.md` §2's atomic table."""
    return Node.synthetic(
        content=text, media_type=MediaType.TABLE, reason="applicability test fixture"
    )


class _NaiveSplitter:
    """Splits every node it is handed in half — no conditional on content anywhere.

    `applies_to` names the one fact this splitter's own logic actually needs
    to do its job (`_Prose`), for reasons that have nothing to do with what
    it thereby excludes — see the module docstring, and `docs/02-extension-
    model.md` §3 → *Applicability*.
    """

    lifetime = runner.Lifetime.RUN
    requires: tuple[type[ExtModel], ...] = ()
    provides: tuple[type[ExtModel], ...] = ()
    applies_to = (Applies(_Prose),)

    def __init__(self, config: object) -> None: ...

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        produced: list[Node] = []
        for node in payload:
            midpoint = len(node.content) // 2
            produced.append(node.derive(content=node.content[:midpoint], ordinal=0))
            produced.append(node.derive(content=node.content[midpoint:], ordinal=1))
        return Produced(value=produced)


class _NaiveSplitterNoFilter:
    """`_NaiveSplitter`'s identical splitting logic, with no `applies_to` declared at all —
    the default this task pins down: it "applies to everything, silently"."""

    lifetime = runner.Lifetime.RUN
    requires: tuple[type[ExtModel], ...] = ()
    provides: tuple[type[ExtModel], ...] = ()

    def __init__(self, config: object) -> None: ...

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        produced: list[Node] = []
        for node in payload:
            midpoint = len(node.content) // 2
            produced.append(node.derive(content=node.content[:midpoint], ordinal=0))
            produced.append(node.derive(content=node.content[midpoint:], ordinal=1))
        return Produced(value=produced)


class _CapturesWhatItReceives:
    """An identity stage that records the payload it was handed, so a test downstream of
    the stage under test can inspect the recombined batch — `Runner.run` itself returns
    only counts, never a batch's payload."""

    lifetime = runner.Lifetime.RUN
    requires: tuple[type[ExtModel], ...] = ()
    provides: tuple[type[ExtModel], ...] = ()

    def __init__(self, captured: list[Sequence[Node]]) -> None:
        self._captured = captured

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        self._captured.append(payload)
        return Produced(value=payload)


def _capture_factory(
    captured: list[Sequence[Node]],
) -> Callable[[object], _CapturesWhatItReceives]:
    """A typed factory binding `captured` ahead of the `config` argument `Runner.resolve`
    calls every factory with — `functools.partial` cannot do this directly, since
    `_CapturesWhatItReceives.__init__` has no `config` parameter for it to also carry."""

    def factory(config: object) -> _CapturesWhatItReceives:
        return _CapturesWhatItReceives(captured)

    return factory


async def test_run_routes_only_nodes_matching_applies_to_through_a_stage() -> None:
    # Arrange — an atomic table sandwiched between two prose nodes, so a correct recombine
    # has to preserve *position*, not merely membership. `docs/11-multimodal.md` §2: "An
    # atomic node passes the chunker unsplit, and the chunker does not have to know that."
    first = _prose_node("ab")
    table = _atomic_node("TABLE")
    second = _prose_node("cd")
    captured: list[Sequence[Node]] = []

    registry = Registry()
    registry.add(_NodeStage, "naive-split", _NaiveSplitter, distribution="weft-test-pack")
    registry.add(
        _NodeStage,
        "capture",
        _capture_factory(captured),
        distribution="weft-test-pack",
    )
    engine = runner.Runner(registry)
    pipeline = engine.resolve(
        (
            runner.StageSpec(id="chunk", contract=_NodeStage, name="naive-split"),
            runner.StageSpec(id="capture", contract=_NodeStage, name="capture"),
        ),
        tenant_id="tenant-a",
    )

    async def batches() -> AsyncIterator[Sequence[Node]]:
        yield [first, table, second]

    # Act
    summary = await engine.run(pipeline, batches(), _ctx())

    # Assert
    assert summary == runner.RunSummary(produced=1)
    assert len(captured) == 1
    result = list(captured[0])
    assert [node.content for node in result] == ["a", "b", "TABLE", "c", "d"]
    assert result[2] is table  # the exact object — the seam never called `run` on it


async def test_run_applies_a_stage_with_no_applies_to_declared_to_the_whole_batch() -> None:
    # Arrange — the contrast case task 1.6 requires: with nothing declared, even a table
    # is split, which is what makes the routed test above a property of `applies_to`
    # rather than of something `_NaiveSplitter.run` itself decided.
    table = _atomic_node("TB")
    captured: list[Sequence[Node]] = []

    registry = Registry()
    registry.add(_NodeStage, "split-all", _NaiveSplitterNoFilter, distribution="weft-test-pack")
    registry.add(
        _NodeStage,
        "capture",
        _capture_factory(captured),
        distribution="weft-test-pack",
    )
    engine = runner.Runner(registry)
    pipeline = engine.resolve(
        (
            runner.StageSpec(id="chunk", contract=_NodeStage, name="split-all"),
            runner.StageSpec(id="capture", contract=_NodeStage, name="capture"),
        ),
        tenant_id="tenant-a",
    )

    async def batches() -> AsyncIterator[Sequence[Node]]:
        yield [table]

    # Act
    await engine.run(pipeline, batches(), _ctx())

    # Assert
    assert [node.content for node in captured[0]] == ["T", "B"]


async def test_run_preserves_order_across_two_separated_non_matching_runs() -> None:
    # Arrange — two atomic nodes, not adjacent, with a prose node between them: the
    # stronger order-preservation proof task 1.6 asks for, over the maximal-contiguous-run
    # segmentation a single sandwiched atomic node alone would not exercise.
    table_one = _atomic_node("X")
    prose = _prose_node("ab")
    table_two = _atomic_node("Y")
    captured: list[Sequence[Node]] = []

    registry = Registry()
    registry.add(_NodeStage, "naive-split", _NaiveSplitter, distribution="weft-test-pack")
    registry.add(
        _NodeStage,
        "capture",
        _capture_factory(captured),
        distribution="weft-test-pack",
    )
    engine = runner.Runner(registry)
    pipeline = engine.resolve(
        (
            runner.StageSpec(id="chunk", contract=_NodeStage, name="naive-split"),
            runner.StageSpec(id="capture", contract=_NodeStage, name="capture"),
        ),
        tenant_id="tenant-a",
    )

    async def batches() -> AsyncIterator[Sequence[Node]]:
        yield [table_one, prose, table_two]

    # Act
    await engine.run(pipeline, batches(), _ctx())

    # Assert
    result = list(captured[0])
    assert [node.content for node in result] == ["X", "a", "b", "Y"]
    assert result[0] is table_one
    assert result[3] is table_two


class _UppercaseChecksApplicability:
    """`_Uppercase`'s identical transform, but with `applies_to` declared over a fact that
    has nothing to do with `list[str]` — a repair test: before it, `_is_routable` checked
    only that the payload was *some* `Sequence`, so a stage declaring `applies_to` over a
    payload whose elements are not `Node` fell into `_segment_by_applicability` instead of
    the unfiltered call the module docstring promises, and every element failed
    `isinstance(item, Node)` — `run` was never invoked at all, silently. `_TextStage`'s
    `list[str]` payload is exactly that shape: a `Sequence` that is not `Sequence[Node]`.
    """

    lifetime = runner.Lifetime.RUN
    requires: tuple[type[ExtModel], ...] = ()
    provides: tuple[type[ExtModel], ...] = ()
    applies_to = (Applies(_Uppercased),)

    def __init__(self, config: object) -> None: ...

    async def run(self, payload: list[str], ctx: Context) -> Outcome[list[str]]:
        return Produced(value=[item.upper() for item in payload])


class _CapturesText:
    """`_CapturesWhatItReceives`'s identical job, over `_TextStage`'s `list[str]` shape."""

    lifetime = runner.Lifetime.RUN
    requires: tuple[type[ExtModel], ...] = ()
    provides: tuple[type[ExtModel], ...] = ()

    def __init__(self, captured: list[list[str]]) -> None:
        self._captured = captured

    async def run(self, payload: list[str], ctx: Context) -> Outcome[list[str]]:
        self._captured.append(list(payload))
        return Produced(value=payload)


def _text_capture_factory(captured: list[list[str]]) -> Callable[[object], _CapturesText]:
    def factory(config: object) -> _CapturesText:
        return _CapturesText(captured)

    return factory


async def test_run_calls_a_stage_with_applies_to_unfiltered_over_a_non_node_payload() -> None:
    # Arrange — `applies_to` over a non-`Node` payload must fall back to the single
    # unfiltered call, exactly as an empty `applies_to` already does; if `run` were never
    # invoked (the pre-repair bug), the captured batch would arrive un-uppercased.
    captured: list[list[str]] = []

    registry = Registry()
    registry.add(_TextStage, "upper", _UppercaseChecksApplicability, distribution="weft-test-pack")
    registry.add(
        _TextStage, "capture", _text_capture_factory(captured), distribution="weft-test-pack"
    )
    engine = runner.Runner(registry)
    pipeline = engine.resolve(
        (
            runner.StageSpec(id="upper", contract=_TextStage, name="upper"),
            runner.StageSpec(id="capture", contract=_TextStage, name="capture"),
        ),
        tenant_id="tenant-a",
    )

    async def batches() -> AsyncIterator[list[str]]:
        yield ["a", "b"]

    # Act
    await engine.run(pipeline, batches(), _ctx())

    # Assert
    assert captured[0] == ["A", "B"]


class _MarksItWasCalled:
    """A `_NodeStage`-shaped stage whose only job is to record every payload it is handed,
    including an empty one — the repair test for `_is_routable` excluding empty batches:
    a non-empty `applies_to` over zero items must let the stage answer for itself, never
    have the runner synthesize a `Produced(value=())` on its behalf without ever calling
    it, the exact silently-empty `Produced` every contract docstring in this tree forbids.
    """

    lifetime = runner.Lifetime.RUN
    requires: tuple[type[ExtModel], ...] = ()
    provides: tuple[type[ExtModel], ...] = ()
    applies_to = (Applies(_Prose),)

    def __init__(self, calls: list[Sequence[Node]]) -> None:
        self._calls = calls

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        self._calls.append(payload)
        if not payload:
            return NothingToProduce(reason="nothing in an empty batch")
        return Produced(value=payload)


def _marks_factory(calls: list[Sequence[Node]]) -> Callable[[object], _MarksItWasCalled]:
    def factory(config: object) -> _MarksItWasCalled:
        return _MarksItWasCalled(calls)

    return factory


async def test_run_calls_a_stage_with_applies_to_even_on_an_empty_batch() -> None:
    # Arrange
    calls: list[Sequence[Node]] = []

    registry = Registry()
    registry.add(_NodeStage, "marks", _marks_factory(calls), distribution="weft-test-pack")
    engine = runner.Runner(registry)
    pipeline = engine.resolve(
        (runner.StageSpec(id="marks", contract=_NodeStage, name="marks"),),
        tenant_id="tenant-a",
    )

    async def batches() -> AsyncIterator[Sequence[Node]]:
        yield []

    # Act
    summary = await engine.run(pipeline, batches(), _ctx())

    # Assert — `run` actually executed, once, with the empty payload, and got the chance
    # to answer `NothingToProduce` for itself.
    assert len(calls) == 1
    assert summary == runner.RunSummary(
        nothing_to_produce=1, nothing_to_produce_reasons=("nothing in an empty batch",)
    )


class _TableFact(ExtModel):
    __namespace__ = "weft-test-pack-table"


class _WideColumns(ExtModel):
    __namespace__ = "weft-test-pack-columns"


def _fact_node(text: str, *, wide_columns: bool) -> Node:
    node = Node.synthetic(
        content=text, media_type=MediaType.TABLE, reason="conjunction test fixture"
    ).with_ext(_TableFact())
    return node.with_ext(_WideColumns()) if wide_columns else node


class _MarksNodesMatchingBothFacts:
    """Appends `!` to whatever it is handed — proof that a stage's `applies_to` tuple is
    a conjunction, never a disjunction. `docs/02-extension-model.md` §3 →
    *Applicability*: a node "not matching *every* `Applies` in the tuple... starts (or
    extends) a non-matching run instead" — the same reading `requires` already gives its
    own tuple of models. Every fixture elsewhere in the tree declares `applies_to` with at
    most one `Applies`, so a regression from `all(...)` to `any(...)` in
    `weft_kernel.runner._segment_by_applicability` would not fail any of them; this one
    names two distinct facts specifically to catch that.
    """

    lifetime = runner.Lifetime.RUN
    requires: tuple[type[ExtModel], ...] = ()
    provides: tuple[type[ExtModel], ...] = ()
    applies_to = (Applies(_TableFact), Applies(_WideColumns))

    def __init__(self, config: object) -> None: ...

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        return Produced(value=[node.derive(content=f"{node.content}!") for node in payload])


async def test_run_treats_a_multi_fact_applies_to_tuple_as_a_conjunction() -> None:
    # Arrange — one node carries both facts the stage names; the other carries only one.
    # AND requires both to route it in; OR would route the second one in too.
    both = _fact_node("both", wide_columns=True)
    table_only = _fact_node("table-only", wide_columns=False)
    captured: list[Sequence[Node]] = []

    registry = Registry()
    registry.add(_NodeStage, "marks", _MarksNodesMatchingBothFacts, distribution="weft-test-pack")
    registry.add(_NodeStage, "capture", _capture_factory(captured), distribution="weft-test-pack")
    engine = runner.Runner(registry)
    pipeline = engine.resolve(
        (
            runner.StageSpec(id="marks", contract=_NodeStage, name="marks"),
            runner.StageSpec(id="capture", contract=_NodeStage, name="capture"),
        ),
        tenant_id="tenant-a",
    )

    async def batches() -> AsyncIterator[Sequence[Node]]:
        yield [both, table_only]

    # Act
    await engine.run(pipeline, batches(), _ctx())

    # Assert — only the node carrying both facts was marked.
    result = list(captured[0])
    assert [node.content for node in result] == ["both!", "table-only"]


# --- task 2.28: a stage's `fallback:` chain, wired to `weft_kernel.fallback` ------------------


class _CannotRead:
    """A backend that refuses every document — the first candidate in the chains below."""

    lifetime = runner.Lifetime.RUN
    requires: tuple[type[ExtModel], ...] = ()
    provides: tuple[type[ExtModel], ...] = ()

    def __init__(self, config: object) -> None: ...

    async def run(self, payload: list[str], ctx: Context) -> Outcome[list[str]]:
        del payload, ctx
        return Failed(reason="could not read it")


def _labelling_factory(built: list[str], label: str) -> Callable[[object], object]:
    """A backend that stamps its own name onto what it produces, and records being built.

    Both halves are what the chain tests need to observe: *which* backend answered
    (the stamp, read off the produced payload by the capture stage that follows) and
    *whether it was ever constructed* (the record, which is how "built lazily, at try
    time" stops being a claim about the implementation).
    """

    class _Backend:
        lifetime = runner.Lifetime.RUN
        requires: tuple[type[ExtModel], ...] = ()
        provides: tuple[type[ExtModel], ...] = ()

        def __init__(self, config: object) -> None:
            built.append(label)

        async def run(self, payload: list[str], ctx: Context) -> Outcome[list[str]]:
            del ctx
            return Produced(value=[f"{item} by {label}" for item in payload])

    return _Backend


async def test_a_stage_whose_plugin_failed_falls_through_to_the_next_backend() -> None:
    # Arrange — task 2.28's shape at the kernel: two backends of one contract, the first
    # refusing, and the chain's order coming from the stage's own data rather than from code.
    built: list[str] = []
    captured: list[list[str]] = []
    registry = Registry()
    registry.add(_TextStage, "primary", _CannotRead, distribution="weft-test-pack")
    registry.add(
        _TextStage, "secondary", _labelling_factory(built, "secondary"), distribution="weft-other"
    )
    registry.add(_TextStage, "capture", _text_capture_factory(captured), distribution="weft-test")
    engine = runner.Runner(registry)
    pipeline = engine.resolve(
        (
            runner.StageSpec(
                id="extract", contract=_TextStage, name="primary", fallback=("secondary",)
            ),
            runner.StageSpec(id="capture", contract=_TextStage, name="capture"),
        ),
        tenant_id="tenant-a",
    )

    async def batches() -> AsyncIterator[list[str]]:
        yield ["paper"]

    # Act
    summary = await engine.run(pipeline, batches(), _ctx())

    # Assert — the run produced, and what it produced says which backend answered.
    assert summary == runner.RunSummary(produced=1)
    assert captured == [["paper by secondary"]]
    assert built == ["secondary"]


async def test_a_fallback_is_never_built_while_the_primary_is_answering() -> None:
    # Arrange — "candidates are built lazily, at try time, so an uninstantiable fallback
    # costs nothing while the primary works." A fallback built at resolution would show up
    # in `built` before a single batch ran.
    built: list[str] = []
    registry = Registry()
    registry.add(_TextStage, "primary", _labelling_factory(built, "primary"), distribution="a")
    registry.add(_TextStage, "secondary", _labelling_factory(built, "secondary"), distribution="b")
    engine = runner.Runner(registry)
    pipeline = engine.resolve(
        (
            runner.StageSpec(
                id="extract", contract=_TextStage, name="primary", fallback=("secondary",)
            ),
        ),
        tenant_id="tenant-a",
    )

    async def batches() -> AsyncIterator[list[str]]:
        yield ["paper"]

    # Act
    summary = await engine.run(pipeline, batches(), _ctx())

    # Assert
    assert summary == runner.RunSummary(produced=1)
    assert built == ["primary"], "the fallback was constructed even though it was never tried"


async def test_a_primary_that_produced_nothing_stops_the_chain_rather_than_trying_the_next() -> (
    None
):
    # Arrange — the whole point of the combinator, at the runner: an empty document is a
    # different outcome from a failed one, and a second backend adds nothing to "I looked,
    # and there is nothing here."
    built: list[str] = []

    class _LooksAndFindsNothing:
        lifetime = runner.Lifetime.RUN
        requires: tuple[type[ExtModel], ...] = ()
        provides: tuple[type[ExtModel], ...] = ()

        def __init__(self, config: object) -> None: ...

        async def run(self, payload: list[str], ctx: Context) -> Outcome[list[str]]:
            del payload, ctx
            return NothingToProduce(reason="4 page(s), and no text on any of them")

    registry = Registry()
    registry.add(_TextStage, "primary", _LooksAndFindsNothing, distribution="a")
    registry.add(_TextStage, "secondary", _labelling_factory(built, "secondary"), distribution="b")
    engine = runner.Runner(registry)
    pipeline = engine.resolve(
        (
            runner.StageSpec(
                id="extract", contract=_TextStage, name="primary", fallback=("secondary",)
            ),
        ),
        tenant_id="tenant-a",
    )

    async def batches() -> AsyncIterator[list[str]]:
        yield ["paper"]

    # Act
    summary = await engine.run(pipeline, batches(), _ctx())

    # Assert
    assert summary.nothing_to_produce == 1
    assert summary.nothing_to_produce_reasons == ("4 page(s), and no text on any of them",)
    assert built == []


def test_resolve_refuses_an_unregistered_fallback_name_naming_the_valid_options() -> None:
    # Arrange — refusing at resolution rather than at try time: refusing when the chain is
    # first *reached* would make the failure depend on encountering a document the primary
    # cannot read, so a pipeline could be green for a year and fail in production.
    registry = Registry()
    registry.add(_TextStage, "primary", _CannotRead, distribution="weft-test-pack")
    registry.add(_TextStage, "secondary", _CannotRead, distribution="weft-other")
    engine = runner.Runner(registry)

    # Act
    with pytest.raises(runner.UnknownFallbackError) as caught:
        engine.resolve(
            (
                runner.StageSpec(
                    id="extract", contract=_TextStage, name="primary", fallback=("secondary", "ocr")
                ),
            ),
            tenant_id="tenant-a",
        )

    # Assert — requirement 5: what was wanted, where, and every option that would have worked.
    message = str(caught.value)
    assert "'ocr'" in message
    assert "fallback 2 of 2" in message
    assert "_TextStage" in message
    assert "'secondary'" in message
    assert caught.value.stages == ("extract",)
    assert "remove" in caught.value.remedy


async def test_a_stage_that_blocks_the_loop_still_fails_the_run_when_it_declares_a_fallback() -> (
    None
):
    # Arrange — fitness function 7(b)'s guard is armed by the seam around every candidate,
    # and `BlockingCallError` is a `WeftError`. A chain that recorded it as a refusal would
    # let one `fallback:` line opt a stage out of the colour rule: the next candidate
    # answers, the run exits 0, and the violation is named nowhere.
    built: list[str] = []

    class _BlocksTheLoop:
        lifetime = runner.Lifetime.RUN
        requires: tuple[type[ExtModel], ...] = ()
        provides: tuple[type[ExtModel], ...] = ()

        def __init__(self, config: object) -> None: ...

        async def run(self, payload: list[str], ctx: Context) -> Outcome[list[str]]:
            del ctx
            time.sleep(0)
            return Produced(value=payload)

    registry = Registry()
    registry.add(_TextStage, "primary", _BlocksTheLoop, distribution="weft-test-pack")
    registry.add(_TextStage, "secondary", _labelling_factory(built, "secondary"), distribution="b")
    engine = runner.Runner(registry)
    pipeline = engine.resolve(
        (
            runner.StageSpec(
                id="extract", contract=_TextStage, name="primary", fallback=("secondary",)
            ),
        ),
        tenant_id="tenant-a",
    )

    async def batches() -> AsyncIterator[list[str]]:
        yield ["paper"]

    # Act / Assert — the same failure the identical stage gets with no fallback declared.
    with pytest.raises(BlockingCallError) as caught:
        await engine.run(pipeline, batches(), _ctx())

    assert "extract:primary" in str(caught.value)
    assert built == [], "the chain moved on from a contract violation instead of failing"


def _declaring_factory(
    *,
    requires: tuple[type[ExtModel], ...] = (),
    provides: tuple[type[ExtModel], ...] = (),
    intact: tuple[type[Property], ...] = (),
    destroys: tuple[type[Property], ...] = (),
) -> Callable[[object], object]:
    """A backend that declares exactly the four class-level facts `_chain` compares."""
    declared_requires, declared_provides = requires, provides
    declared_intact, declared_destroys = intact, destroys

    class _Backend:
        lifetime = runner.Lifetime.RUN
        requires: tuple[type[ExtModel], ...] = declared_requires
        provides: tuple[type[ExtModel], ...] = declared_provides
        intact: tuple[type[Property], ...] = declared_intact
        destroys: tuple[type[Property], ...] = declared_destroys

        def __init__(self, config: object) -> None: ...

        async def run(self, payload: list[str], ctx: Context) -> Outcome[list[str]]:
            del ctx
            return Produced(value=payload)

    return _Backend


@pytest.mark.parametrize(
    ("fallback", "expected"),
    [
        pytest.param(
            _declaring_factory(provides=(_Uppercased,), destroys=(_WordBoundaries,)),
            "destroys",
            id="destroys-more",
        ),
        pytest.param(_declaring_factory(), "provides", id="provides-less"),
        pytest.param(
            _declaring_factory(requires=(_Uppercased,), provides=(_Uppercased,)),
            "requires",
            id="requires-more",
        ),
        pytest.param(
            _declaring_factory(provides=(_Uppercased,), intact=(_WordBoundaries,)),
            "intact",
            id="needs-more-intact",
        ),
    ],
)
def test_resolve_refuses_a_fallback_that_demands_more_or_promises_less_than_the_primary(
    fallback: Callable[[object], object], expected: str
) -> None:
    # Arrange — a fallback's whole claim is substitutability at one position. Every
    # downstream `requires`/`intact` check was answered by the *primary*'s declarations,
    # so a fallback that provides less or destroys more resolves clean and then corrupts
    # the run — and only on the documents the primary could not read, which is where a
    # test would never look. The class-level read this costs is exactly what
    # `weft_kernel.resolution.resolve` already does, with no instance constructed.
    registry = Registry()
    registry.add(
        _TextStage,
        "primary",
        _declaring_factory(provides=(_Uppercased,)),
        distribution="weft-test-pack",
    )
    registry.add(_TextStage, "secondary", fallback, distribution="weft-other")
    engine = runner.Runner(registry)

    # Act
    with pytest.raises(runner.FallbackNotSubstitutableError) as caught:
        engine.resolve(
            (
                runner.StageSpec(
                    id="extract", contract=_TextStage, name="primary", fallback=("secondary",)
                ),
            ),
            tenant_id="tenant-a",
        )

    # Assert — requirement 5: what was wanted, where, and what would have worked.
    message = str(caught.value)
    assert "'secondary'" in message
    assert "fallback 1 of 1" in message
    assert expected in message
    assert caught.value.stages == ("extract",)
    assert caught.value.remedy


def test_resolve_accepts_a_fallback_declaring_exactly_what_the_primary_declares() -> None:
    # Arrange — the check refuses a difference, never a declaration: a fallback that
    # declares the same four facts is substitutable and resolves, with neither candidate
    # constructed beyond the primary resolution already builds.
    registry = Registry()
    registry.add(
        _TextStage,
        "primary",
        _declaring_factory(provides=(_Uppercased,), destroys=(_WordBoundaries,)),
        distribution="weft-test-pack",
    )
    registry.add(
        _TextStage,
        "secondary",
        _declaring_factory(provides=(_Uppercased,), destroys=(_WordBoundaries,)),
        distribution="weft-other",
    )
    engine = runner.Runner(registry)

    # Act
    pipeline = engine.resolve(
        (
            runner.StageSpec(
                id="extract", contract=_TextStage, name="primary", fallback=("secondary",)
            ),
        ),
        tenant_id="tenant-a",
    )

    # Assert
    assert [candidate.name for candidate in pipeline.stages[0].chain] == ["primary", "secondary"]


async def test_a_fallback_the_chain_reached_is_flushed_like_any_other_stage() -> None:
    # Arrange — a fallback is built at try time, so it is invisible to a flush loop that
    # walks only what resolution constructed. A store backend reached as a fallback and
    # never flushed would lose whatever it buffered, silently.
    flushed: list[str] = []

    class _FlushableBackend:
        lifetime = runner.Lifetime.RUN
        requires: tuple[type[ExtModel], ...] = ()
        provides: tuple[type[ExtModel], ...] = ()

        def __init__(self, config: object) -> None: ...

        async def run(self, payload: list[str], ctx: Context) -> Outcome[list[str]]:
            del ctx
            return Produced(value=payload)

        async def flush(self) -> None:
            flushed.append("secondary")

    registry = Registry()
    registry.add(_TextStage, "primary", _CannotRead, distribution="weft-test-pack")
    registry.add(_TextStage, "secondary", _FlushableBackend, distribution="weft-other")
    engine = runner.Runner(registry)
    pipeline = engine.resolve(
        (
            runner.StageSpec(
                id="extract", contract=_TextStage, name="primary", fallback=("secondary",)
            ),
        ),
        tenant_id="tenant-a",
    )

    async def batches() -> AsyncIterator[list[str]]:
        yield ["paper"]

    # Act
    summary = await engine.run(pipeline, batches(), _ctx())

    # Assert
    assert summary == runner.RunSummary(produced=1)
    assert flushed == ["secondary"]


# --- `run_once` — one payload in, that payload's own outcome out (task 2.4) ----------------


async def test_run_once_returns_the_payload_the_last_stage_produced() -> None:
    # Arrange — `run` returns counts by design, which is right for ingest and useless for a
    # query path, where there is exactly one payload and the payload is the point.
    registry = Registry()
    registry.add(_TextStage, "upper", _Uppercase, distribution="weft-test-pack")
    registry.add(_CountStage, "count", _Count, distribution="weft-test-pack")
    engine = runner.Runner(registry)
    pipeline = engine.resolve(
        (
            runner.StageSpec(id="upper", contract=_TextStage, name="upper"),
            runner.StageSpec(id="count", contract=_CountStage, name="count"),
        ),
        tenant_id="tenant-a",
    )

    # Act
    outcome = await engine.run_once(pipeline, ["a", "b"], _ctx())

    # Assert
    assert outcome == Produced(value=2)


async def test_run_once_returns_the_first_outcome_that_is_not_produced() -> None:
    # Arrange
    class _Declines:
        lifetime = runner.Lifetime.RUN
        requires: tuple[type[ExtModel], ...] = ()
        provides = (_Uppercased,)

        def __init__(self, config: object) -> None: ...

        async def run(self, payload: list[str], ctx: Context) -> Outcome[list[str]]:
            del payload, ctx
            return NothingToProduce(reason="declined to act")

    registry = Registry()
    registry.add(_TextStage, "declines", _Declines, distribution="weft-test-pack")
    registry.add(_CountStage, "count", _Count, distribution="weft-test-pack")
    engine = runner.Runner(registry)
    pipeline = engine.resolve(
        (
            runner.StageSpec(id="declines", contract=_TextStage, name="declines"),
            runner.StageSpec(id="count", contract=_CountStage, name="count"),
        ),
        tenant_id="tenant-a",
    )

    # Act
    outcome = await engine.run_once(pipeline, ["a"], _ctx())

    # Assert
    assert outcome == NothingToProduce(reason="declined to act")


async def test_run_once_refuses_a_context_for_a_tenant_the_pipeline_was_not_resolved_for() -> None:
    # Arrange
    registry = Registry()
    registry.add(_TextStage, "upper", _Uppercase, distribution="weft-test-pack")
    engine = runner.Runner(registry)
    pipeline = engine.resolve(
        (runner.StageSpec(id="upper", contract=_TextStage, name="upper"),), tenant_id="tenant-a"
    )
    other = Context(tenant_id="tenant-b", run_id="run-1", trace_id="trace-1", locale="en")

    # Act / Assert
    with pytest.raises(runner.TenantMismatchError) as caught:
        await engine.run_once(pipeline, ["a"], other)
    assert "tenant-a" in str(caught.value)
    assert "tenant-b" in str(caught.value)


async def test_run_once_flushes_every_stage_once_and_again_when_one_raises() -> None:
    # Arrange
    flushed: list[str] = []

    class _Flushable:
        lifetime = runner.Lifetime.RUN
        requires: tuple[type[ExtModel], ...] = ()
        provides = (_Uppercased,)

        def __init__(self, config: object) -> None: ...

        async def run(self, payload: list[str], ctx: Context) -> Outcome[list[str]]:
            del ctx
            return Produced(value=payload)

        async def flush(self) -> None:
            flushed.append("flushable")

    class _Explodes:
        lifetime = runner.Lifetime.RUN
        requires = (_Uppercased,)
        provides: tuple[type[ExtModel], ...] = ()

        def __init__(self, config: object) -> None: ...

        async def run(self, payload: list[str], ctx: Context) -> Outcome[int]:
            del payload, ctx
            raise asyncio.CancelledError

    registry = Registry()
    registry.add(_TextStage, "flushable", _Flushable, distribution="weft-test-pack")
    registry.add(_CountStage, "explodes", _Explodes, distribution="weft-test-pack")
    engine = runner.Runner(registry)
    happy = engine.resolve(
        (runner.StageSpec(id="flushable", contract=_TextStage, name="flushable"),),
        tenant_id="tenant-a",
    )
    unhappy = engine.resolve(
        (
            runner.StageSpec(id="flushable", contract=_TextStage, name="flushable"),
            runner.StageSpec(id="explodes", contract=_CountStage, name="explodes"),
        ),
        tenant_id="tenant-a",
    )

    # Act
    await engine.run_once(happy, ["a"], _ctx())
    with pytest.raises(asyncio.CancelledError):
        await engine.run_once(unhappy, ["a"], _ctx())

    # Assert — once for the clean run, once for the cancelled one, and the cancellation
    # reached the caller untouched
    assert flushed == ["flushable", "flushable"]
