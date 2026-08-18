"""Unit tests for `weft_cli.registry_bootstrap`.

Mirrors `packages/weft-cli/src/weft_cli/registry_bootstrap.py`. Covers
`require_active`'s exit-code split (`docs/02-extension-model.md` → *The trust
model*: refused is policy, 3; genuinely absent or failed is resolution, 4) and
`build_dependencies` reading `[packs] allow` from an on-disk `weft.toml`, or
treating its absence as open — the one file this distribution opens, per
`docs/build-ledger.md` 0.9's note.

**Task 1.12** adds `[plugins]` to what this module reads from `weft.toml`:
`build_dependencies` parses it with `weft_kernel.discovery.plugin_pins_from_config`
and constructs the `Registry` with it, so a pin is wired from the file into the
kernel's own arbitration — see `weft_kernel.registry`'s module docstring.
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
    require_plugin,
)
from weft_kernel.discovery import InertPluginPinError, PackReport, PackStatus
from weft_kernel.errors import WeftError
from weft_kernel.registry import Registry


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


class _Contract:
    """A contract nothing in this repository publishes.

    `require_plugin` takes the contract as an argument precisely so it is not
    about embedders — the same gate covers `--extract` and every later
    `[services]` role — so the test states it that way rather than importing a
    real one.
    """


def _plugin(config: object) -> object:
    del config
    return object()


def test_require_plugin_passes_when_the_name_resolves() -> None:
    # Arrange
    registry = Registry()
    registry.add(_Contract, "openai", _plugin, distribution="acme-openai")
    reports = (_report("acme-openai", PackStatus.ACTIVE),)

    # Act
    outcome = require_plugin(
        reports, registry=registry, contract=_Contract, name="openai", setting="[services] embed"
    )

    # Assert
    assert outcome is None


def test_require_plugin_blames_policy_when_a_pack_was_refused_before_it_could_register() -> None:
    # Arrange — the reproduction `weft.toml.example` used to ship adjacently: an operator
    # selects a plugin by name and leaves its distribution off `[packs] allow`. A refused pack
    # is *never imported*, so nothing can prove it is the one that would have provided the
    # name — but the exit code and the remedy are policy's, not resolution's.
    registry = Registry()
    registry.add(_Contract, "hash", _plugin, distribution="weft-embed")
    reports = (
        _report("weft-embed", PackStatus.ACTIVE),
        _report("acme-openai", PackStatus.REFUSED, reason="not in [packs] allow"),
    )

    # Act
    outcome = require_plugin(
        reports, registry=registry, contract=_Contract, name="openai", setting="[services] embed"
    )

    # Assert
    assert outcome is not None
    code, message = outcome
    assert code is ExitCode.POLICY_REFUSED
    assert "[services] embed" in message
    assert "acme-openai" in message
    assert "[packs] allow" in message
    assert "'hash'" in message


def test_require_plugin_attaches_the_reason_when_a_pack_failed_to_register() -> None:
    # Arrange — `failed` and `partial` are resolution, not policy (`docs/02-extension-model.md`
    # → *The trust model*), and the reason is what turns a bare "unknown plugin" into a repair.
    registry = Registry()
    reports = (_report("acme-openai", PackStatus.FAILED, reason="settings failed validation"),)

    # Act
    outcome = require_plugin(
        reports, registry=registry, contract=_Contract, name="openai", setting="[services] embed"
    )

    # Assert
    assert outcome is not None
    code, message = outcome
    assert code is ExitCode.RESOLUTION_FAILED
    assert "settings failed validation" in message


def test_require_plugin_says_plainly_that_nothing_provides_the_name_when_nothing_is_amiss() -> None:
    # Arrange — every pack active, and the name still does not resolve: a typo, or a pack
    # nobody installed. Nothing to blame, so nothing is blamed.
    registry = Registry()
    registry.add(_Contract, "hash", _plugin, distribution="weft-embed")
    reports = (_report("weft-embed", PackStatus.ACTIVE),)

    # Act
    outcome = require_plugin(
        reports, registry=registry, contract=_Contract, name="opneai", setting="[services] embed"
    )

    # Assert
    assert outcome is not None
    code, message = outcome
    assert code is ExitCode.RESOLUTION_FAILED
    assert "'opneai'" in message
    assert "'hash'" in message


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


def test_pack_settings_from_config_refuses_a_packs_value_that_is_not_a_table() -> None:
    """The same typo `weft_kernel.discovery.allow_list_from_config` refuses, refused here too.

    Two distributions read `[packs]` — this module's own `pack_settings_from_config` does not
    go through the kernel's `allow_list_from_config` at all, so fixing one without the other
    would leave them disagreeing about what `packs = [...]` means, exactly the asymmetry
    `docs/02-extension-model.md` §2 → *The trust model* rules out.
    """
    # Arrange
    document: dict[str, object] = {"packs": ["weft-store"]}

    # Act / Assert
    with pytest.raises(WeftError, match=r"\[packs\].*table"):
        registry_bootstrap.pack_settings_from_config(document)


def test_build_dependencies_survives_its_own_repeated_ext_model_registration(
    tmp_path: Path,
) -> None:
    """`build_dependencies` calls `_ensure_chunk_offset_rehydrates` once per command, many
    times over within one test run — against the one, process-wide rehydration registry.

    Repair for a reviewer finding: the first cut suppressed every
    `DuplicateRegistrationError` unconditionally to survive exactly this repeated-call
    case. This proves the check-then-register replacement still survives it too — a second
    call in the same process must not raise merely because `ChunkOffset` is already the
    registrant. Driven through the public `build_dependencies`, never the private helper
    directly, the same way every other caller in this process reaches it.
    """
    # Arrange
    absent = tmp_path / "weft.toml"

    # Act / Assert — twice in a row, against the real process-wide rehydration registry.
    registry_bootstrap.build_dependencies(absent)
    registry_bootstrap.build_dependencies(absent)


def test_build_dependencies_lets_a_genuine_ext_model_namespace_collision_raise(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A second class claiming the `weft-chunk` namespace is refused, not swallowed.

    Repair for a reviewer finding: `_ensure_chunk_offset_rehydrates` used to wrap
    `register_ext_model` in a blanket `contextlib.suppress(DuplicateRegistrationError)`,
    which could not tell "this function's own idempotent re-registration" apart from "a
    genuine second class claiming the namespace" — `weft_store.rehydrate.ext_models`'
    own docstring says every such collision is refused unconditionally, by design. This
    stands in a fresh rehydration registry already claimed by an impostor and proves the
    collision now surfaces through `build_dependencies`, the public entry point every
    real caller reaches this through.
    """
    # Arrange
    import weft_store.rehydrate as rehydrate
    from weft_kernel.payload import ExtModel
    from weft_kernel.registry import DuplicateRegistrationError

    class _Impostor(ExtModel):
        __namespace__ = "weft-chunk"

    fresh = Registry()
    fresh.add(ExtModel, "weft-chunk", _Impostor, distribution="an-impostor-pack")
    monkeypatch.setattr(rehydrate, "ext_models", fresh)
    absent = tmp_path / "weft.toml"

    # Act / Assert
    with pytest.raises(DuplicateRegistrationError, match="weft-chunk"):
        registry_bootstrap.build_dependencies(absent)


def test_build_dependencies_wires_a_plugins_pin_from_weft_toml_into_the_registry(
    tmp_path: Path,
) -> None:
    """The full path from file to kernel: a pin naming no real collision fails loudly.

    No two distributions installed in this environment actually collide over
    `'Chunker:no-such-collision'`, so this proves `build_dependencies` parsed
    `[plugins]` and handed it to `Registry(plugin_pins=...)` rather than the
    pin silently going nowhere — `weft_kernel.discovery.InertPluginPinError`
    only exists to be raised from state a real `Registry` was actually given.
    """
    # Arrange
    config = tmp_path / "weft.toml"
    config.write_text('[plugins]\n"Chunker:no-such-collision" = "weft-chunk"\n')

    # Act / Assert
    with pytest.raises(InertPluginPinError) as excinfo:
        registry_bootstrap.build_dependencies(config)

    assert "Chunker:no-such-collision" in str(excinfo.value)


def test_build_dependencies_with_strict_pins_false_returns_deps_instead_of_raising(
    tmp_path: Path,
) -> None:
    """Repair for a reviewer finding: a diagnostic caller must be able to opt out.

    Identical fixture to the test above — the same inert pin — with
    `strict_pins=False` the only difference, proving `build_dependencies`
    actually threads the flag through to `discover()` rather than the
    keyword being accepted and silently ignored.
    """
    # Arrange
    config = tmp_path / "weft.toml"
    config.write_text('[plugins]\n"Chunker:no-such-collision" = "weft-chunk"\n')

    # Act
    deps = registry_bootstrap.build_dependencies(config, strict_pins=False)

    # Assert
    assert deps.registry.unconsulted_pins() == frozenset({"Chunker:no-such-collision"})


def test_build_dependencies_carries_the_service_selection_from_weft_toml(
    tmp_path: Path,
) -> None:
    """The path from `[services] embed` to the command that resolves an embedder.

    `weft.toml` is parsed once, here, so the selection travels with the
    registry it was read beside rather than each command re-opening the file
    and being free to disagree about what it says.
    """
    # Arrange
    config = tmp_path / "weft.toml"
    config.write_text('[services]\nembed = "openai"\n')

    # Act
    deps = registry_bootstrap.build_dependencies(config)

    # Assert
    assert deps.services.embed == "openai"


def test_build_dependencies_defaults_to_the_offline_embedder_with_no_config_file(
    tmp_path: Path,
) -> None:
    # Arrange — a clean checkout, which is what `poe ci-checks` and the quickstart run in.
    absent = tmp_path / "weft.toml"

    # Act
    deps = registry_bootstrap.build_dependencies(absent)

    # Assert — no credential, no network, no model download.
    assert deps.services.embed == "hash"
