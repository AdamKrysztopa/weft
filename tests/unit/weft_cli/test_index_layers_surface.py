"""Ledger task **43.8**, the surface — how a project and a run choose the layers `weft index` runs.

Owner's Q3, settled at Phase 43's opening: `[index] layers` in `weft.toml` names a project's
standing layers, and `--layers a,b` overrides it for one run; `--layers none` runs none.
`--layers-only` runs the layers over an indexed corpus without re-running the base. `Weft.index`
takes the same two. A layer batch reports its progress on the same channel a base batch does,
naming the layer.
"""

import io
from pathlib import Path

import pytest

from weft_cli import commands
from weft_cli import ingest as ingest_module
from weft_cli.ingest import IndexResult
from weft_cli.progress import BatchProgress
from weft_cli.sinks import PrintingSink
from weft_embed import Embedder
from weft_engine import registry_bootstrap
from weft_engine.index_policy import IndexPolicy, UnknownIndexKeyError, index_policy_from_config
from weft_engine.registry_bootstrap import Dependencies
from weft_engine.services import ServiceSelection
from weft_kernel.context import Context
from weft_kernel.discovery import PackReport, PackStatus
from weft_kernel.registry import Registry
from weft_kernel.runner import RunSummary
from weft_store import NodeStore


def _ctx(deps: Dependencies) -> Context:
    ctx = Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")
    ctx.services.add(Dependencies, deps)
    return ctx


def _null_factory(config: object) -> object:
    del config
    return object()


def _deps(policy: IndexPolicy) -> Dependencies:
    reports = tuple(
        PackReport(pack=p, distribution=f"weft-{p}", status=PackStatus.ACTIVE)
        for p in ("extract", "chunk", "embed", "store")
    )
    registry = Registry()
    registry.add(Embedder, "hash", _null_factory, distribution="weft-embed")
    registry.add(NodeStore, "pgvector", _null_factory, distribution="weft-store")
    return Dependencies(
        registry=registry, reports=reports, services=ServiceSelection(), index_policy=policy
    )


class _Captured:
    def __init__(self) -> None:
        self.kwargs: dict[str, object] = {}

    async def __call__(self, *_args: object, **kwargs: object) -> IndexResult:
        self.kwargs = kwargs
        return IndexResult(
            summary=RunSummary(produced=0, nothing_to_produce=0, failed=0), stored_count=0
        )


async def _run(
    monkeypatch: pytest.MonkeyPatch, args: commands.IndexArgs, policy: IndexPolicy
) -> dict[str, object]:
    captured = _Captured()
    monkeypatch.setattr(ingest_module, "run_index", captured)
    await commands.IndexCommand().run(args, _ctx(_deps(policy)))
    return captured.kwargs


async def test_the_flag_names_the_layers_for_this_run(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Act
    kwargs = await _run(
        monkeypatch,
        commands.IndexArgs(path=str(tmp_path), layers="enrich-with-questions,enrich-with-facts"),
        IndexPolicy(layers=("enrich-with-raptor",)),
    )

    # Assert
    assert kwargs["layers"] == ("enrich-with-questions", "enrich-with-facts")
    assert kwargs["layers_only"] is False


async def test_the_project_s_layers_apply_when_the_flag_is_absent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Act
    kwargs = await _run(
        monkeypatch,
        commands.IndexArgs(path=str(tmp_path)),
        IndexPolicy(layers=("enrich-with-questions",)),
    )

    # Assert
    assert kwargs["layers"] == ("enrich-with-questions",)


async def test_layers_none_runs_none_whatever_the_project_says(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Act
    kwargs = await _run(
        monkeypatch,
        commands.IndexArgs(path=str(tmp_path), layers="none"),
        IndexPolicy(layers=("enrich-with-questions",)),
    )

    # Assert
    assert kwargs["layers"] == ()


async def test_layers_only_reaches_the_run(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # Act
    kwargs = await _run(
        monkeypatch,
        commands.IndexArgs(path=str(tmp_path), layers_only=True),
        IndexPolicy(layers=("enrich-with-questions",)),
    )

    # Assert
    assert kwargs["layers_only"] is True


async def test_layers_only_with_no_layer_named_anywhere_is_refused_before_running(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Act
    with pytest.raises(commands.NoLayersToRunError) as refused:
        await _run(
            monkeypatch,
            commands.IndexArgs(path=str(tmp_path), layers_only=True),
            IndexPolicy(),
        )

    # Assert
    message = str(refused.value)
    assert "--layers" in message
    assert "[index] layers" in message


def test_the_index_block_names_the_project_s_layers() -> None:
    # Act
    policy = index_policy_from_config({"index": {"layers": ["enrich-with-questions"]}})

    # Assert
    assert policy == IndexPolicy(layers=("enrich-with-questions",))


def test_no_index_block_names_no_layers() -> None:
    # Act / Assert
    assert index_policy_from_config({}) == IndexPolicy()
    assert index_policy_from_config(None).layers == ()


def test_an_unknown_index_key_is_refused_naming_the_keys_it_takes() -> None:
    # Act
    with pytest.raises(UnknownIndexKeyError) as refused:
        index_policy_from_config({"index": {"layer": ["enrich-with-questions"]}})

    # Assert
    assert "'layer'" in str(refused.value)
    assert refused.value.valid_options == ("layers",)


def test_a_project_s_weft_toml_reaches_its_dependencies(tmp_path: Path) -> None:
    # Arrange
    config = tmp_path / "weft.toml"
    config.write_text('[index]\nlayers = ["enrich-with-questions"]\n', encoding="utf-8")

    # Act
    deps = registry_bootstrap.build_dependencies(config_path=config)

    # Assert
    assert deps.index_policy.layers == ("enrich-with-questions",)


async def test_a_layer_batch_prints_its_own_progress_line() -> None:
    # Arrange
    err = io.StringIO()
    sink = PrintingSink(stream=io.StringIO(), progress_stream=err)
    event = BatchProgress(
        batch=1,
        batches=2,
        queryable=4,
        documents=6,
        seconds=3.1,
        layer="enrich-with-questions",
    )

    # Act
    await sink.batch_progress(event)

    # Assert
    assert err.getvalue() == (
        "layer enrich-with-questions · batch 1/2 · 4/6 sources · 3.1 s since start\n"
    )
