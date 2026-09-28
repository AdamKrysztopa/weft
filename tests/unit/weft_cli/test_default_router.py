"""The default router calls no model and answers through `retrieve-then-generate` — task **44.1**.

`route` pays a `query-scorer` call on every ask for scores `nearest-description` never reads,
and it was never measured (`manual/evidence.md` §3). The default is now the router that picks
the best measured first stage, and it needs no `[llm.roles]` entry to do so.
"""

from pathlib import Path

import pytest

from weft_cli.pipeline_catalogue import full_catalogue
from weft_cli.route_ask import resolve_in_catalogue
from weft_engine import registry_bootstrap
from weft_engine.services import ServiceSelection
from weft_retrieve import AlwaysConfig
from weft_retrieve.engine import roles_needed


def test_the_default_router_needs_no_model_role_and_always_picks_retrieve_then_generate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange — the registry and catalogue an installed wheel builds, from an empty project.
    monkeypatch.chdir(tmp_path)
    config = tmp_path / "weft.toml"
    config.write_text("", encoding="utf-8")
    deps = registry_bootstrap.build_dependencies(config_path=config)
    catalogue = full_catalogue(reports=deps.reports)
    default = ServiceSelection().route

    # Act
    resolved = resolve_in_catalogue(
        catalogue[default],
        registry=deps.registry,
        catalogue=catalogue,
        reports=deps.reports,
        contributions=deps.contributions,
    )

    # Assert
    assert roles_needed(resolved, deps.registry) == frozenset()
    assert resolved.stages[-1].use == "always"
    policy = resolved.stages[-1].config
    assert isinstance(policy, AlwaysConfig)
    assert policy.pipeline == "retrieve-then-generate"


def test_the_measured_but_costly_router_stays_selectable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    monkeypatch.chdir(tmp_path)
    config = tmp_path / "weft.toml"
    config.write_text("", encoding="utf-8")
    deps = registry_bootstrap.build_dependencies(config_path=config)

    # Act
    catalogue = full_catalogue(reports=deps.reports)

    # Assert — `route` still ships, and still needs its model role.
    resolved = resolve_in_catalogue(
        catalogue["route"],
        registry=deps.registry,
        catalogue=catalogue,
        reports=deps.reports,
        contributions=deps.contributions,
    )
    assert "route" in roles_needed(resolved, deps.registry)
