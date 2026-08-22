"""Tests for `weft_otel.provider`.

Mirrors `packages/weft-otel/src/weft_otel/provider.py`. `build_tracer_provider` is a pure
function over `OtelSettings` — it never calls `opentelemetry.trace.set_tracer_provider`, so
these tests never touch the real, process-global, set-once provider slot `test_register.py`
is careful about; see that file's own module docstring.

`opentelemetry-exporter-otlp-proto-http` (the `weft-otel[otlp]` extra) is not installed in
this workspace — `packages/weft-otel/pyproject.toml`'s own comment on why it is optional — so
the "OTLP requested" tests below exercise the real, un-mocked fallback path: `otlp_exporter`
genuinely cannot import the exporter here, exactly as it could not in an operator's
environment that skipped the extra.
"""

import pytest

from weft_otel.provider import build_tracer_provider, otlp_exporter
from weft_otel.settings import OtelExporter, OtelSettings


def test_console_settings_build_a_console_exporter() -> None:
    # Arrange
    settings = OtelSettings(exporter=OtelExporter.CONSOLE, service_name="weft-provider-test")

    # Act
    provider, actual = build_tracer_provider(settings)

    # Assert
    assert actual is OtelExporter.CONSOLE
    assert provider.resource.attributes["service.name"] == "weft-provider-test"


def test_none_is_refused_loudly_rather_than_silently_built() -> None:
    # Arrange — `register()` is the caller expected to skip `NONE` before ever reaching this
    # function; calling it anyway is a caller error, not an operator's.
    settings = OtelSettings(exporter=OtelExporter.NONE)

    # Act / Assert
    with pytest.raises(ValueError, match="OtelExporter.NONE"):
        build_tracer_provider(settings)


def test_otlp_with_no_endpoint_falls_back_to_console() -> None:
    # Arrange — `OTLP` requested, but `endpoint` is the field `_otlp_exporter` refuses to
    # proceed without, regardless of whether the optional exporter package is installed.
    settings = OtelSettings(exporter=OtelExporter.OTLP)

    # Act
    _, actual = build_tracer_provider(settings)

    # Assert
    assert actual is OtelExporter.CONSOLE


def test_otlp_exporter_helper_returns_none_when_the_extra_is_not_installed() -> None:
    # Arrange — an endpoint alone is not enough: `weft-otel[otlp]` is not part of this
    # workspace's resolved environment, so the import inside `otlp_exporter` genuinely
    # fails, and the `None` this test asserts is the real fallback signal, not a mocked one.
    settings = OtelSettings(exporter=OtelExporter.OTLP, endpoint="http://localhost:4318/v1/traces")

    # Act
    exporter = otlp_exporter(settings)

    # Assert — the failure degrades to `None`, it does not raise.
    assert exporter is None
