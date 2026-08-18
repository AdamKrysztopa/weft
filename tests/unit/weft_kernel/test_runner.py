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
"""

import asyncio
import gc
import weakref
from collections.abc import AsyncIterator
from typing import Protocol

import pytest

from weft_kernel import runner
from weft_kernel.context import Context
from weft_kernel.errors import WeftError
from weft_kernel.payload import ExtModel, NothingToProduce, Outcome, Produced
from weft_kernel.registry import Registry, UnknownPluginError


class _TextStage(runner.Stage[list[str], list[str]], Protocol):
    async def run(self, payload: list[str], ctx: Context) -> Outcome[list[str]]: ...


class _CountStage(runner.Stage[list[str], int], Protocol):
    async def run(self, payload: list[str], ctx: Context) -> Outcome[int]: ...


class _Uppercased(ExtModel):
    __namespace__ = "weft-test-pack"

    note: str = "uppercased"


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

    # Act / Assert
    with pytest.raises(runner.PipelineResolutionError) as excinfo:
        engine.resolve(specs, tenant_id="tenant-a")

    message = str(excinfo.value)
    assert "s1" in message
    assert "_Uppercased" in message
    assert "weft-test-pack" in message


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

    # Act / Assert
    with pytest.raises(runner.PipelineResolutionError) as excinfo:
        engine.resolve(specs, tenant_id="tenant-a")

    message = str(excinfo.value)
    assert "count" in message
    assert "upper" in message


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

    # Act / Assert
    with pytest.raises(runner.PipelineResolutionError) as excinfo:
        engine.resolve(specs, tenant_id="tenant-a")

    assert "_Uppercased" in str(excinfo.value)


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
