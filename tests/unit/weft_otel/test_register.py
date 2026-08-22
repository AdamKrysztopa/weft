"""Tests for `weft_otel.register`.

Mirrors `packages/weft-otel/src/weft_otel/__init__.py`. **Every test here monkeypatches
`opentelemetry.trace.set_tracer_provider` rather than calling the real one.** That function
can succeed exactly once per process — a second call anywhere logs a warning and changes
nothing — and this repository's shared `pytest tests -q` session already has a test that
depends on winning that race for real: `tests/unit/weft_kernel/test_seam_trace_visibility.py`
configures the one genuine SDK provider the seam's own spans are proven against. A test here
that called the real function would either contend with that one or (having patched nothing)
silently do nothing on a second run — neither proves what this file wants to prove, which is
register()'s own *logic*: what it decides to build, and when it calls through at all. The one
place this pack's real, unmocked effect on a fresh process is actually demonstrated is
`tests/unit/weft_otel/test_register_subprocess.py`, deliberately isolated in its own process
for exactly this reason.
"""

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider

from weft_kernel.discovery import PackRegistrar
from weft_kernel.registry import Registry
from weft_otel import register
from weft_otel.settings import OtelExporter, OtelSettings


@pytest.fixture(autouse=True)
def never_touch_the_real_provider(monkeypatch: pytest.MonkeyPatch) -> list[TracerProvider]:
    """Every call `register()` makes to `set_tracer_provider`, recorded — never applied."""
    calls: list[TracerProvider] = []
    monkeypatch.setattr(trace, "set_tracer_provider", calls.append)
    return calls


def _registrar() -> PackRegistrar:
    return PackRegistrar(Registry(), distribution="weft-otel")


def test_exporter_console_configures_a_provider_and_contributes_no_plugin(
    never_touch_the_real_provider: list[TracerProvider],
) -> None:
    # Arrange
    registrar = _registrar()

    # Act
    register(registrar, OtelSettings(exporter=OtelExporter.CONSOLE))

    # Assert
    [provider] = never_touch_the_real_provider
    assert isinstance(provider, TracerProvider)
    assert registrar.contributed == 0


def test_the_default_settings_never_touch_the_provider_at_all(
    never_touch_the_real_provider: list[TracerProvider],
) -> None:
    # Arrange — `NONE` is the default (`weft_otel.settings`'s own docstring on why), so a
    # fresh install with no `weft.toml` at all must be exactly this, not merely reachable by
    # naming `NONE` explicitly.
    registrar = _registrar()

    # Act
    register(registrar, OtelSettings())

    # Assert
    assert never_touch_the_real_provider == []
    assert registrar.contributed == 0


def test_otlp_falling_back_to_console_prints_a_loud_reason_and_still_configures_one(
    never_touch_the_real_provider: list[TracerProvider],
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Arrange — `otlp` requested, but `weft-otel[otlp]` is not installed in this workspace
    # (`packages/weft-otel/pyproject.toml`'s own comment), so the real fallback fires.
    registrar = _registrar()
    settings = OtelSettings(exporter=OtelExporter.OTLP, endpoint="http://localhost:4318/v1/traces")

    # Act
    register(registrar, settings)

    # Assert — a real provider was still installed, and the fallback said so on stderr, not
    # silently: `docs/02-extension-model.md` §1's own rule for a probed optional dependency.
    assert len(never_touch_the_real_provider) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "otlp" in captured.err
    assert "console" in captured.err
