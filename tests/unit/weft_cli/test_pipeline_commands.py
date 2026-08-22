"""Unit tests for `weft_cli.pipeline_commands`.

Mirrors `packages/weft-cli/src/weft_cli/pipeline_commands.py`. Builds a real `Registry` with
one stand-in contract/plugin (`_StageContract`, `test_commands.py`'s own `_Chunker`
precedent) and real pipeline documents on disk under a `pipelines/` directory relative to
`tmp_path` (`monkeypatch.chdir`) — never a stubbed `full_catalogue`/`resolve` — because the
property under test is that these five commands wire correctly into `weft_cli.compile.
contracts_for` and `weft_kernel.resolution.resolve`, the same reasoning `test_route_ask.py`
already applies to `weft route`. Covers the happy path for each of the five commands, the
edge case of `derive` scaffolding a minimal `extends:`-only document, and the error case of
an unknown pipeline name naming the valid options.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

import pytest
import yaml

from weft_cli import pipeline_commands
from weft_cli.pipeline_catalogue import UnknownPipelineNameError
from weft_cli.registry_bootstrap import Dependencies
from weft_cli.services import ServiceSelection
from weft_kernel.context import Context
from weft_kernel.payload import Produced
from weft_kernel.pipeline import StageDeclaration
from weft_kernel.registry import Registry
from weft_kernel.resolution import Contribution
from weft_kernel.runner import Stage


class _StageContract(Stage[object, object], Protocol):
    """A stand-in capability contract, `object -> object` so two of them compose trivially
    in the diff test below. `resolve()` reads every optional declaration off a registered
    plugin defensively (`getattr(..., default)`), so a bare `Stage` subclass with nothing
    else declared behaves exactly like a real plugin that declares no `requires`/
    `provides`/`intact`/`destroys`/`config_model`/`applies_to`.
    """


def _factory(config: object = None) -> object:
    del config
    return object()


def _registry() -> Registry:
    registry = Registry()
    registry.add(_StageContract, "fixed-size", _factory, distribution="weft-chunk")
    return registry


def _ctx(deps: Dependencies) -> Context:
    ctx = Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")
    ctx.services.add(Dependencies, deps)
    return ctx


def _write_pipeline(tmp_path: Path, filename: str, document: dict[str, object]) -> None:
    directory = tmp_path / "pipelines"
    directory.mkdir(exist_ok=True)
    (directory / filename).write_text(yaml.safe_dump(document, sort_keys=False))


@pytest.fixture(autouse=True)
def in_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


async def test_pipeline_list_reports_every_catalogue_name(tmp_path: Path) -> None:
    # Arrange
    _write_pipeline(tmp_path, "base.yaml", {"name": "base", "stages": []})
    _write_pipeline(tmp_path, "other.yaml", {"name": "other", "stages": []})
    deps = Dependencies(registry=_registry(), reports=(), services=ServiceSelection())

    # Act
    outcome = await pipeline_commands.PipelineListCommand().run(
        pipeline_commands.NoArgs(), _ctx(deps)
    )

    # Assert
    assert isinstance(outcome, Produced)
    result = outcome.value
    assert isinstance(result, pipeline_commands.PipelineListCommandResult)
    assert result.names == ("base", "other")


async def test_pipeline_show_carries_the_fully_resolved_form(tmp_path: Path) -> None:
    # Arrange
    _write_pipeline(
        tmp_path,
        "base.yaml",
        {"name": "base", "stages": [{"id": "chunk", "use": "fixed-size"}]},
    )
    deps = Dependencies(registry=_registry(), reports=(), services=ServiceSelection())

    # Act
    outcome = await pipeline_commands.PipelineShowCommand().run(
        pipeline_commands.PipelineNameArgs(name="base"), _ctx(deps)
    )

    # Assert
    assert isinstance(outcome, Produced)
    result = outcome.value
    assert isinstance(result, pipeline_commands.PipelineShowCommandResult)
    resolved = result.resolved
    assert resolved.name == "base"
    assert len(resolved.stages) == 1
    stage = resolved.stages[0]
    assert stage.use == "fixed-size"
    assert stage.distribution == "weft-chunk"
    assert stage.provenance == "base"
    assert resolved.unapplied_operators == ()
    assert resolved.unplaced_contributions == ()


async def test_pipeline_show_places_a_contribution_in_a_pipeline_that_declares_its_slot(
    tmp_path: Path,
) -> None:
    """Task **5.3a** (`S8`): `deps.contributions` reaches `resolve()` through this command,
    and lands in the one pipeline that opted into the slot — `02` §3 → *Slots*.
    """
    # Arrange
    _write_pipeline(
        tmp_path,
        "base.yaml",
        {
            "name": "base",
            "stages": [{"id": "chunk", "use": "fixed-size"}],
            "slots": [{"id": "enrich", "after": "chunk"}],
        },
    )
    registry = _registry()
    registry.add(_StageContract, "entity-extractor", _factory, distribution="weft-graph")
    contribution = Contribution(
        slot="enrich",
        distribution="weft-graph",
        stage=StageDeclaration(id="entities", use="entity-extractor"),
    )
    deps = Dependencies(
        registry=registry, reports=(), services=ServiceSelection(), contributions=(contribution,)
    )

    # Act
    outcome = await pipeline_commands.PipelineShowCommand().run(
        pipeline_commands.PipelineNameArgs(name="base"), _ctx(deps)
    )

    # Assert
    assert isinstance(outcome, Produced)
    result = outcome.value
    assert isinstance(result, pipeline_commands.PipelineShowCommandResult)
    resolved = result.resolved
    assert [stage.id for stage in resolved.stages] == ["chunk", "weft-graph:entities"]
    assert resolved.stages[1].provenance == "weft-graph"
    assert resolved.stages[1].distribution == "weft-graph"
    assert resolved.unplaced_contributions == ()


async def test_pipeline_show_records_a_contribution_unplaced_against_a_pipeline_with_no_slot(
    tmp_path: Path,
) -> None:
    """The other half of `02` §3 → *Slots*: "a contribution with no matching slot is a
    recorded no-op" — never a resolution failure, and printed rather than silently dropped.
    """
    # Arrange — the identical pipeline the sibling test above uses, minus the `slots:` block.
    _write_pipeline(
        tmp_path, "base.yaml", {"name": "base", "stages": [{"id": "chunk", "use": "fixed-size"}]}
    )
    registry = _registry()
    registry.add(_StageContract, "entity-extractor", _factory, distribution="weft-graph")
    contribution = Contribution(
        slot="enrich",
        distribution="weft-graph",
        stage=StageDeclaration(id="entities", use="entity-extractor"),
    )
    deps = Dependencies(
        registry=registry, reports=(), services=ServiceSelection(), contributions=(contribution,)
    )

    # Act
    outcome = await pipeline_commands.PipelineShowCommand().run(
        pipeline_commands.PipelineNameArgs(name="base"), _ctx(deps)
    )

    # Assert
    assert isinstance(outcome, Produced)
    result = outcome.value
    assert isinstance(result, pipeline_commands.PipelineShowCommandResult)
    resolved = result.resolved
    assert [stage.id for stage in resolved.stages] == ["chunk"]
    assert len(resolved.unplaced_contributions) == 1
    assert "weft-graph:entities" in resolved.unplaced_contributions[0]
    assert "enrich" in resolved.unplaced_contributions[0]


async def test_pipeline_show_refuses_an_unknown_name_naming_the_valid_options(
    tmp_path: Path,
) -> None:
    # Arrange
    _write_pipeline(tmp_path, "base.yaml", {"name": "base", "stages": []})
    deps = Dependencies(registry=_registry(), reports=(), services=ServiceSelection())

    # Act / Assert
    with pytest.raises(UnknownPipelineNameError) as exc_info:
        await pipeline_commands.PipelineShowCommand().run(
            pipeline_commands.PipelineNameArgs(name="ghost"), _ctx(deps)
        )
    assert exc_info.value.valid_options == ("base",)


async def test_pipeline_validate_reports_the_stage_count_on_success(tmp_path: Path) -> None:
    # Arrange
    _write_pipeline(
        tmp_path,
        "base.yaml",
        {"name": "base", "stages": [{"id": "chunk", "use": "fixed-size"}]},
    )
    deps = Dependencies(registry=_registry(), reports=(), services=ServiceSelection())

    # Act
    outcome = await pipeline_commands.PipelineValidateCommand().run(
        pipeline_commands.PipelineNameArgs(name="base"), _ctx(deps)
    )

    # Assert
    assert isinstance(outcome, Produced)
    result = outcome.value
    assert isinstance(result, pipeline_commands.PipelineValidateCommandResult)
    assert result.name == "base"
    assert result.stage_count == 1


async def test_pipeline_derive_scaffolds_an_extends_only_document(tmp_path: Path) -> None:
    # Arrange
    _write_pipeline(tmp_path, "base.yaml", {"name": "base", "stages": []})
    deps = Dependencies(registry=_registry(), reports=(), services=ServiceSelection())

    # Act
    outcome = await pipeline_commands.PipelineDeriveCommand().run(
        pipeline_commands.PipelineDeriveArgs(parent="base", name="specific"), _ctx(deps)
    )

    # Assert
    assert isinstance(outcome, Produced)
    result = outcome.value
    assert isinstance(result, pipeline_commands.PipelineDeriveCommandResult)
    assert result.parent == "base"
    assert result.name == "specific"
    written = yaml.safe_load((tmp_path / "pipelines" / "specific.yaml").read_text())
    assert written == {"name": "specific", "extends": "base"}


async def test_pipeline_derive_refuses_an_unknown_parent(tmp_path: Path) -> None:
    # Arrange
    deps = Dependencies(registry=_registry(), reports=(), services=ServiceSelection())

    # Act / Assert
    with pytest.raises(UnknownPipelineNameError):
        await pipeline_commands.PipelineDeriveCommand().run(
            pipeline_commands.PipelineDeriveArgs(parent="ghost", name="specific"), _ctx(deps)
        )


async def test_pipeline_derive_refuses_to_overwrite_an_existing_document(tmp_path: Path) -> None:
    # Arrange — repair, 2026-08-20: `derive` is `write`-class now, so it never reaches
    # `weft_cli.confirm.gate`; a name already on disk is refused outright, loudly, naming the
    # path, rather than asked about — see `pipeline_commands.PipelineAlreadyExistsError`.
    _write_pipeline(tmp_path, "base.yaml", {"name": "base", "stages": []})
    _write_pipeline(tmp_path, "specific.yaml", {"name": "specific", "extends": "base"})
    deps = Dependencies(registry=_registry(), reports=(), services=ServiceSelection())
    existing = (tmp_path / "pipelines" / "specific.yaml").read_text()

    # Act / Assert — refused by name, the existing file untouched, never a prompt.
    with pytest.raises(pipeline_commands.PipelineAlreadyExistsError) as raised:
        await pipeline_commands.PipelineDeriveCommand().run(
            pipeline_commands.PipelineDeriveArgs(parent="base", name="specific"), _ctx(deps)
        )
    assert "specific.yaml" in str(raised.value)
    assert (tmp_path / "pipelines" / "specific.yaml").read_text() == existing


async def test_pipeline_diff_reports_the_stage_a_derived_pipeline_adds(tmp_path: Path) -> None:
    # Arrange — `02` §3's own worked example: `specific` inserts one stage after `chunk`.
    _write_pipeline(
        tmp_path,
        "base.yaml",
        {"name": "base", "stages": [{"id": "chunk", "use": "fixed-size"}]},
    )
    _write_pipeline(
        tmp_path,
        "specific.yaml",
        {
            "name": "specific",
            "extends": "base",
            "insert": [{"after": "chunk", "stage": {"id": "keywords", "use": "fixed-size"}}],
        },
    )
    deps = Dependencies(registry=_registry(), reports=(), services=ServiceSelection())

    # Act
    outcome = await pipeline_commands.PipelineDiffCommand().run(
        pipeline_commands.PipelineDiffArgs(a="base", b="specific"), _ctx(deps)
    )

    # Assert
    assert isinstance(outcome, Produced)
    result = outcome.value
    assert isinstance(result, pipeline_commands.PipelineDiffCommandResult)
    diff = result.diff
    assert not diff.identical
    assert [stage.id for stage in diff.added_stages] == ["keywords"]
    assert diff.removed_stages == ()
    assert diff.changed_stages == ()
