"""Tests for `weft_otel.settings`.

Mirrors `packages/weft-otel/src/weft_otel/settings.py`. `OtelSettings` is exercised through
plain construction and `pydantic` validation only — nothing here touches `register()` or the
real `opentelemetry.trace` global, which `test_register.py` and `test_provider.py` own.
"""

import pytest
from pydantic import ValidationError

from weft_otel.settings import OtelExporter, OtelSettings


def test_defaults_export_nothing_until_configured() -> None:
    # Arrange / Act
    settings = OtelSettings()

    # Assert — the module docstring's own argument: installing `weft-otel` alone must not
    # race every other real `discover()` call in this repository's own test suite for the
    # process's one-shot `TracerProvider` slot, so a fresh install is inert until configured.
    assert settings.exporter is OtelExporter.NONE
    assert settings.service_name == "weft"
    assert settings.endpoint is None
    assert settings.api_key.get_secret_value() == ""


def test_exporter_console_is_the_one_line_opt_in() -> None:
    # Arrange / Act
    settings = OtelSettings(exporter=OtelExporter.CONSOLE)

    # Assert
    assert settings.exporter is OtelExporter.CONSOLE


def test_an_unknown_field_is_refused_rather_than_ignored() -> None:
    # Arrange / Act / Assert — `extra="forbid"`, the same guard `weft_qdrant.settings`
    # carries: a typo in `weft.toml` must fail loudly, not be silently dropped.
    with pytest.raises(ValidationError):
        OtelSettings.model_validate({"exporter": "console", "nonsense": True})
