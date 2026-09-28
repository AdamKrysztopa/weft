"""A stage's output puts its own facts on the stage's span — carried repair **R44.2**, G28.

G28 settled that a fact a payload carries reaches the trace at the registration seam, never by a
pack setting span attributes by hand: `wrap` reads `telemetry_attributes()` from any produced
value that declares it, and the kernel names no capability to do so. The seam's own attribution
(`weft.pack`, `weft.contract`, `weft.plugin`) is not the payload's to rewrite.

Each test installs its own `TracerProvider` on `seam._tracer`, because
`opentelemetry.trace.set_tracer_provider` succeeds once per process and
`test_seam_trace_visibility.py` already holds it.
"""

from __future__ import annotations

from collections.abc import Mapping

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from weft_kernel import seam
from weft_kernel.payload import Failed, Outcome, Produced


@pytest.fixture
def exporter(monkeypatch: pytest.MonkeyPatch) -> InMemorySpanExporter:
    memory_exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(memory_exporter))
    monkeypatch.setattr(seam, "_tracer", provider.get_tracer("weft-test"))
    return memory_exporter


class _Decision:
    """A pack's own payload: declares what belongs on the span, imports nothing from OTel."""

    def __init__(self, attributes: Mapping[str, str | bool | int | float]) -> None:
        self._attributes = attributes

    def telemetry_attributes(self) -> Mapping[str, str | bool | int | float]:
        return self._attributes


async def test_a_produced_value_s_declared_attributes_are_on_its_stage_s_span(
    exporter: InMemorySpanExporter,
) -> None:
    # Arrange
    async def run(payload: str) -> Outcome[_Decision]:
        del payload
        return Produced(
            value=_Decision({"weft.route.pipeline": "retrieve-then-generate", "weft.hops": 2})
        )

    wrapped = seam.wrap(run, distribution="weft-rag", contract="Policy", plugin="always")

    # Act
    await wrapped("q")

    # Assert
    [span] = exporter.get_finished_spans()
    assert span.attributes is not None
    assert span.attributes["weft.route.pipeline"] == "retrieve-then-generate"
    assert span.attributes["weft.hops"] == 2


async def test_a_value_that_declares_nothing_adds_nothing(
    exporter: InMemorySpanExporter,
) -> None:
    # Arrange
    async def run(payload: str) -> Outcome[str]:
        return Produced(value=payload)

    wrapped = seam.wrap(run, distribution="weft-rag", contract="Policy", plugin="always")

    # Act
    await wrapped("q")

    # Assert
    [span] = exporter.get_finished_spans()
    assert span.attributes is not None
    assert not any(key.startswith("weft.route.") for key in span.attributes)


async def test_a_payload_cannot_rewrite_the_seam_s_own_attribution(
    exporter: InMemorySpanExporter,
) -> None:
    # Arrange
    async def run(payload: str) -> Outcome[_Decision]:
        del payload
        return Produced(
            value=_Decision(
                {
                    "weft.pack": "impostor",
                    "weft.contract": "impostor",
                    "weft.plugin": "impostor",
                    "weft.route.rule": "r1",
                }
            )
        )

    wrapped = seam.wrap(run, distribution="weft-rag", contract="Policy", plugin="always")

    # Act
    await wrapped("q")

    # Assert
    [span] = exporter.get_finished_spans()
    assert span.attributes is not None
    assert span.attributes["weft.pack"] == "weft-rag"
    assert span.attributes["weft.contract"] == "Policy"
    assert span.attributes["weft.plugin"] == "always"
    assert span.attributes["weft.route.rule"] == "r1"


async def test_a_failed_stage_carries_no_payload_attributes(
    exporter: InMemorySpanExporter,
) -> None:
    # Arrange
    async def run(payload: str) -> Outcome[_Decision]:
        del payload
        return Failed(reason="no rule applies")

    wrapped = seam.wrap(run, distribution="weft-rag", contract="Policy", plugin="always")

    # Act
    await wrapped("q")

    # Assert
    [span] = exporter.get_finished_spans()
    assert span.attributes is not None
    assert not any(key.startswith("weft.route.") for key in span.attributes)
