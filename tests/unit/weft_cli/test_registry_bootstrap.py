"""Unit tests for `weft_cli.registry_bootstrap`.

Mirrors `packages/weft-cli/src/weft_cli/registry_bootstrap.py`. Covers
`require_active`'s exit-code split (`docs/02-extension-model.md` → *The trust
model*: refused is policy, 3; genuinely absent or failed is resolution, 4) and
`build_dependencies` reading `[packs] allow` from an on-disk `weft.toml`, or
treating its absence as open — the one file this distribution opens, per
`docs/build-ledger.md` 0.9's note.
"""

import re
from pathlib import Path

import pytest

from weft_cli import registry_bootstrap
from weft_cli.exit_codes import ExitCode
from weft_cli.registry_bootstrap import (
    ConfigFileError,
    allow_list_from_file,
    pack_settings_from_environment,
    require_active,
)
from weft_kernel.discovery import PackReport, PackStatus


def _report(distribution: str, status: PackStatus, *, reason: str | None = None) -> PackReport:
    return PackReport(distribution=distribution, status=status, reason=reason)


def test_require_active_passes_when_every_distribution_is_active() -> None:
    # Arrange
    reports = (_report("weft-store", PackStatus.ACTIVE), _report("weft-embed", PackStatus.ACTIVE))

    # Act
    outcome = require_active(reports, distributions=("weft-store", "weft-embed"))

    # Assert
    assert outcome is None


def test_require_active_reports_partial_as_usable() -> None:
    # Arrange — PARTIAL means *something* registered; whether the specific plugin a command
    # needs is among it is pipeline resolution's own question, not this gate's.
    reports = (_report("weft-store", PackStatus.PARTIAL, reason="optional dependency missing"),)

    # Act
    outcome = require_active(reports, distributions=("weft-store",))

    # Assert
    assert outcome is None


def test_require_active_refused_is_a_policy_exit() -> None:
    # Arrange
    reports = (_report("weft-store", PackStatus.REFUSED, reason="not in [packs] allow"),)

    # Act
    outcome = require_active(reports, distributions=("weft-store",))

    # Assert
    assert outcome is not None
    code, message = outcome
    assert code is ExitCode.POLICY_REFUSED
    assert "weft-store" in message


def test_require_active_missing_distribution_is_a_resolution_exit() -> None:
    # Arrange — no report at all for 'weft-store': never installed, and no allow-list named it.
    reports: tuple[PackReport, ...] = ()

    # Act
    outcome = require_active(reports, distributions=("weft-store",))

    # Assert
    assert outcome is not None
    code, message = outcome
    assert code is ExitCode.RESOLUTION_FAILED
    assert "weft-store" in message


def test_require_active_failed_pack_is_a_resolution_exit() -> None:
    # Arrange
    reports = (_report("weft-store", PackStatus.FAILED, reason="settings failed validation"),)

    # Act
    outcome = require_active(reports, distributions=("weft-store",))

    # Assert
    assert outcome == (
        ExitCode.RESOLUTION_FAILED,
        "'weft-store' failed to register: settings failed validation",
    )


def test_allow_list_from_file_is_none_when_no_config_file_exists(tmp_path: Path) -> None:
    # Arrange
    absent = tmp_path / "weft.toml"

    # Act
    allow = allow_list_from_file(absent)

    # Assert
    assert allow is None


def test_allow_list_from_file_reads_packs_allow_from_an_existing_config_file(
    tmp_path: Path,
) -> None:
    # Arrange
    config = tmp_path / "weft.toml"
    config.write_text('[packs]\nallow = ["weft-store", "weft-embed"]\n')

    # Act
    allow = allow_list_from_file(config)

    # Assert
    assert allow == ("weft-store", "weft-embed")


def test_allow_list_from_file_raises_a_config_file_error_for_malformed_toml(
    tmp_path: Path,
) -> None:
    # Arrange — valid at the filesystem level, invalid as TOML: an unterminated table header.
    config = tmp_path / "weft.toml"
    config.write_text('[packs\nallow = ["weft-store"]\n')

    # Act / Assert
    with pytest.raises(ConfigFileError, match=re.escape(str(config))):
        allow_list_from_file(config)


def test_pack_settings_from_environment_is_empty_when_the_database_url_is_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    monkeypatch.delenv("WEFT_DATABASE_URL", raising=False)

    # Act
    settings = pack_settings_from_environment()

    # Assert — see the module docstring: a bare crash on every registry-needing command,
    # including `plugins doctor`, would be worse than an ordinary, diagnosable FAILED report.
    assert settings == {}


def test_pack_settings_from_environment_references_the_database_url_when_it_is_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    monkeypatch.setenv("WEFT_DATABASE_URL", "postgresql://weft:weft@localhost:5433/weft")

    # Act
    settings = pack_settings_from_environment()

    # Assert — the token, never the value: weft_kernel.discovery.interpolate_env is the only
    # reader of os.environ in this path.
    assert settings == {"weft-store": {"dsn": "${env:WEFT_DATABASE_URL}"}}


def test_pack_settings_from_the_file_beat_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """An explicit project setting is never overridden by an ambient one.

    A developer with a stale `WEFT_DATABASE_URL` exported would otherwise run against a
    different database from the one their `weft.toml` names — and a store pointed at the wrong
    database does not crash, it answers plausibly. `docs/03-cli.md` -> *Project context*.
    """
    # Arrange
    monkeypatch.setenv("WEFT_DATABASE_URL", "postgresql://ambient/wrong")
    document: dict[str, object] = {"packs": {"weft-store": {"dsn": "postgresql://explicit/right"}}}

    # Act
    settings = registry_bootstrap.merged_pack_settings(document)

    # Assert
    assert settings["weft-store"]["dsn"] == "postgresql://explicit/right"


def test_the_environment_fills_a_key_the_file_does_not_set(monkeypatch: pytest.MonkeyPatch) -> None:
    """With no file at all, one `export` is enough — the quickstart's whole path."""
    # Arrange
    monkeypatch.setenv("WEFT_DATABASE_URL", "postgresql://ambient/used")

    # Act
    settings = registry_bootstrap.merged_pack_settings(None)

    # Assert
    assert settings == {"weft-store": {"dsn": "${env:WEFT_DATABASE_URL}"}}


def test_the_allow_list_is_not_read_as_a_settings_block() -> None:
    """`[packs] allow` and `[packs.<dist>]` share one table; only the sub-tables are settings."""
    # Arrange
    document: dict[str, object] = {
        "packs": {"allow": ["weft-store"], "weft-store": {"dsn": "postgresql://x/y"}}
    }

    # Act
    settings = registry_bootstrap.pack_settings_from_config(document)

    # Assert
    assert settings == {"weft-store": {"dsn": "postgresql://x/y"}}
