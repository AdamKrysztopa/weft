"""Unit tests for `weft_cli.config_commands`.

Mirrors `packages/weft-rag/src/weft_cli/config_commands.py`. Runs against a real `weft.toml`
under `tmp_path` (`monkeypatch.chdir`), never a stubbed `weft_cli.config_surface` — the
property under test is the `Command` wiring around that module's real functions, on
`test_registry_bootstrap.py`'s own convention for `weft.toml`-reading code. Covers the happy
path for `get` (every key, one key, `--origin`) and `set` (writing a fresh key and replacing
an existing one, round-tripped through a real `ConfigGetCommand` afterward), and the error
case of an unknown key.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from weft_cli.config_commands import (
    ConfigGetArgs,
    ConfigGetCommand,
    ConfigGetCommandResult,
    ConfigSetArgs,
    ConfigSetCommand,
    ConfigSetCommandResult,
)
from weft_cli.config_surface import ConfigOrigin, UnknownConfigKeyError
from weft_cli.registry_bootstrap import Dependencies
from weft_cli.services import ServiceSelection
from weft_kernel.context import Context
from weft_kernel.payload import Produced
from weft_kernel.registry import Registry


def _ctx(deps: Dependencies) -> Context:
    ctx = Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")
    ctx.services.add(Dependencies, deps)
    return ctx


@pytest.fixture(autouse=True)
def in_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


def _deps() -> Dependencies:
    return Dependencies(registry=Registry(), reports=(), services=ServiceSelection())


async def test_config_get_with_no_key_reports_every_default(tmp_path: Path) -> None:
    # Arrange — no weft.toml at all
    del tmp_path

    # Act
    outcome = await ConfigGetCommand().run(ConfigGetArgs(), _ctx(_deps()))

    # Assert
    assert isinstance(outcome, Produced)
    result = outcome.value
    assert isinstance(result, ConfigGetCommandResult)
    assert {entry.key for entry in result.entries} == {
        "services.embed",
        "services.store",
        "permissions.overwrite",
        "permissions.destroy",
        "reconcile.mode",
    }
    assert all(entry.origin is ConfigOrigin.DEFAULT for entry in result.entries)
    assert result.show_origin is False


async def test_config_get_with_a_key_reports_only_that_one(tmp_path: Path) -> None:
    # Arrange
    (tmp_path / "weft.toml").write_text('[services]\nembed = "openai"\n')

    # Act
    outcome = await ConfigGetCommand().run(
        ConfigGetArgs(key="services.embed", origin=True), _ctx(_deps())
    )

    # Assert
    assert isinstance(outcome, Produced)
    result = outcome.value
    assert isinstance(result, ConfigGetCommandResult)
    assert result.show_origin is True
    assert len(result.entries) == 1
    assert result.entries[0].value == "openai"
    assert result.entries[0].origin is ConfigOrigin.FILE


async def test_config_get_refuses_an_unknown_key(tmp_path: Path) -> None:
    del tmp_path

    with pytest.raises(UnknownConfigKeyError):
        await ConfigGetCommand().run(ConfigGetArgs(key="services.bogus"), _ctx(_deps()))


async def test_config_set_writes_a_fresh_key_into_a_new_weft_toml(tmp_path: Path) -> None:
    # Act
    outcome = await ConfigSetCommand().run(
        ConfigSetArgs(key="services.embed", value="openai"), _ctx(_deps())
    )

    # Assert
    assert isinstance(outcome, Produced)
    result = outcome.value
    assert isinstance(result, ConfigSetCommandResult)
    assert result.key == "services.embed"
    assert result.value == "openai"
    assert (tmp_path / "weft.toml").is_file()

    # Round trip through a real ConfigGetCommand
    get_outcome = await ConfigGetCommand().run(
        ConfigGetArgs(key="services.embed", origin=True), _ctx(_deps())
    )
    assert isinstance(get_outcome, Produced)
    get_result = get_outcome.value
    assert isinstance(get_result, ConfigGetCommandResult)
    entry = get_result.entries[0]
    assert entry.value == "openai"
    assert entry.origin is ConfigOrigin.FILE


async def test_config_set_replaces_an_existing_value_and_preserves_the_rest(
    tmp_path: Path,
) -> None:
    # Arrange
    (tmp_path / "weft.toml").write_text(
        '# a project comment\n[services]\nembed = "hash"\nstore = "qdrant"\n'
    )

    # Act
    await ConfigSetCommand().run(ConfigSetArgs(key="services.embed", value="openai"), _ctx(_deps()))

    # Assert
    written = (tmp_path / "weft.toml").read_text()
    assert "# a project comment" in written
    assert 'store = "qdrant"' in written
    assert 'embed = "openai"' in written


async def test_config_set_refuses_an_unknown_key(tmp_path: Path) -> None:
    del tmp_path

    with pytest.raises(UnknownConfigKeyError):
        await ConfigSetCommand().run(ConfigSetArgs(key="services.bogus", value="x"), _ctx(_deps()))
