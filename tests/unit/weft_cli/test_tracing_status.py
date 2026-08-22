"""Tests for `weft_cli.tracing_status`.

Mirrors `packages/weft-cli/src/weft_cli/tracing_status.py`. `opentelemetry.trace.
get_tracer_provider` is monkeypatched rather than read for real — the same discipline
`tests/unit/weft_otel/test_register.py` documents: the real one is process-global and
set-once, and this file has no business depending on what order the rest of the suite left
it in.
"""

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider

from weft_cli.tracing_status import describe_tracing


def test_a_real_provider_is_reported_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange
    monkeypatch.setattr(trace, "get_tracer_provider", lambda: TracerProvider())

    # Act
    status = describe_tracing()

    # Assert
    assert status.startswith("configured — spans export through")
    assert "opentelemetry.sdk.trace.TracerProvider" in status


def test_the_no_op_default_is_reported_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange — the true default before anything ever calls `set_tracer_provider`.
    monkeypatch.setattr(trace, "get_tracer_provider", trace.NoOpTracerProvider)

    # Act
    status = describe_tracing()

    # Assert
    assert status.startswith("not configured")
    assert "weft-otel" in status


def test_the_lazy_proxy_default_is_also_reported_not_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange — `opentelemetry.trace.get_tracer_provider`'s own real return before any real
    # provider is set is a `ProxyTracerProvider`, not a bare `NoOpTracerProvider` — both must
    # read as "nothing is really exporting yet."
    monkeypatch.setattr(trace, "get_tracer_provider", trace.ProxyTracerProvider)

    # Act
    status = describe_tracing()

    # Assert
    assert status.startswith("not configured")
