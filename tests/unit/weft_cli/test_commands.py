"""Unit tests for `weft_cli.commands`.

Mirrors `packages/weft-cli/src/weft_cli/commands.py`. Covers the shape every built-in command
now shares: `ctx.require(Dependencies)` recovering what the retired `handle_*` functions used to
receive as a direct parameter, a policy/resolution refusal raising `CommandRefusalError` with
the same exit code the old handler used to return directly, a successful run producing the same
`Produced[CommandResult]` the retired handler used to print, and `register()` wiring all five
under `Command` with the permission classes `docs/03-cli.md` → *Permissions* assigns. External
services (`run_index`, `run_ask`, `run_routed_ask`, `run_named_ask`) are stubbed by patching
the names `weft_cli.commands` itself imported — this tier proves the `Command` wiring, not the
pipelines themselves, which `tests/unit/weft_cli/test_ingest.py`/`test_ask.py`/
`test_route_ask.py` and `tests/integration/test_cli_end_to_end.py` already cover.

Task **3.11** retires `route` as a separate registered command — `AskCommand` now covers what
`RouteCommand` used to (routing by default, `--pipeline` to name one directly, `--retrieve-only`
for Phase 0's own contract) — so this file's `ask`-prefixed tests below cover what were
previously two commands' worth of coverage.
"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar, Protocol, cast, runtime_checkable
from unittest import mock

import pytest

from weft_cli import commands
from weft_cli.exit_codes import ExitCode
from weft_cli.ingest import IndexResult
from weft_cli.reconcile import participants as reconcile_module_participants
from weft_cli.reconcile import reconcile_everywhere
from weft_cli.reconcile_policy import ReconcilePolicy
from weft_cli.registry_bootstrap import Dependencies
from weft_cli.services import ServiceSelection
from weft_cli.skew import SkewReport
from weft_command.contract import Command
from weft_command.permission import PermissionClass
from weft_embed import Embedder
from weft_generate.payload import Answer, AnswerStance
from weft_kernel.context import Context
from weft_kernel.discovery import PackRegistrar, PackReport, PackStatus
from weft_kernel.payload import MediaType, Node, Produced, SourceId
from weft_kernel.pipeline import StageDeclaration
from weft_kernel.registry import Registry
from weft_kernel.resolution import Contribution
from weft_kernel.runner import RunSummary
from weft_retrieve.payload import Query
from weft_store import (
    NodeStore,
    ReconcileEstimate,
    ReconcileMode,
    ReconcileReport,
    Removed,
    Scored,
)


class _DeletableStore:
    """A `NodeStore` stand-in for the fan-out — `delete_source` is the only method reached,
    and `SourceDeletable` is satisfied by having it, which is the derivation under test.
    """

    def __init__(self, config: object = None) -> None:
        del config

    async def delete_source(self, source_id: object) -> object:
        del source_id
        return None


@runtime_checkable
class _DerivedReconcilable(Protocol):
    """A contract the CLI has never heard of — the graph pack's own, in miniature. A pack
    registered under it joins the `Reconcilable` fan-out by capability alone, which is what
    makes it a *derived* participant rather than a second primary store.
    """

    async def reconcile(self, ctx: Context, mode: ReconcileMode) -> ReconcileReport: ...


class _ReconcilableStore:
    """A `NodeStore` stand-in satisfying `Reconcilable` — `reconcile`/`estimate` are the only
    two methods reached, which is all the fan-out ever calls (`weft_cli.fanout`'s own
    class-level `issubclass` check, never a constructed `NodeStore` used as one).
    """

    pending: int = 2

    def __init__(self, config: object = None) -> None:
        del config

    async def reconcile(self, ctx: object, mode: ReconcileMode) -> ReconcileReport:
        del ctx
        return ReconcileReport(mode=mode, examined=1, removed=1)

    async def estimate(self, ctx: object, mode: ReconcileMode) -> ReconcileEstimate:
        del ctx
        return ReconcileEstimate(
            mode=mode,
            pending=_ReconcilableStore.pending,
            description=f"{_ReconcilableStore.pending} node(s) outstanding",
            model_calls=_ReconcilableStore.pending,
        )


def _null_factory(config: object) -> object:
    del config
    return object()


def _ctx(deps: Dependencies) -> Context:
    ctx = Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")
    ctx.services.add(Dependencies, deps)
    return ctx


def test_register_wires_every_built_in_with_its_permission_class() -> None:
    # Arrange
    registry = Registry()
    registrar = PackRegistrar(registry, distribution="weft-cli")

    # Act
    commands.register(registrar, commands.Settings())
    registrar.commit()

    # Assert — task 3.7 grew this from five names to thirteen; task 3.11 retires `route`
    # (folded into `ask`, `docs/build-ledger.md`'s own 3.11 entry), back to twelve; task 4.6
    # adds `eval run`/`eval compare`/`trace` (`weft_cli.eval_commands`), to fifteen; task 4.7
    # adds `eval metrics`, to sixteen; task 5.1a adds `delete` — G7's fast path, and the
    # first first-party `destroy`-class command — to seventeen, and task 5.1b adds
    # `reconcile`, G7's safety net, to eighteen.
    assert registry.names_for(Command) == {
        "delete",
        "reconcile",
        "index",
        "ask",
        "plugins list",
        "plugins doctor",
        "init",
        "pipeline list",
        "pipeline show",
        "pipeline derive",
        "pipeline validate",
        "pipeline diff",
        "config get",
        "config set",
        "eval run",
        "eval compare",
        "eval metrics",
        "trace",
    }
    expected_permissions = {
        "index": PermissionClass.WRITE,
        "ask": PermissionClass.READ,
        "plugins list": PermissionClass.READ,
        "plugins doctor": PermissionClass.READ,
        # `init`, `pipeline derive` and `config set` — `write`, not `overwrite`, since the
        # 2026-08-20 repair (`docs/build-ledger.md`'s dated paragraph for 3.3/3.6/3.7): each
        # is a *create*, `docs/03-cli.md`'s own `write`-row example, and refuses outright
        # (never asks) when the target already exists — see `test_init_command_refuses_to_
        # overwrite_an_existing_weft_toml`/`test_pipeline_derive_refuses_to_overwrite_an_
        # existing_document` below and `test_pipeline_commands.py`'s own derive coverage.
        "init": PermissionClass.WRITE,
        "pipeline list": PermissionClass.READ,
        "pipeline show": PermissionClass.READ,
        "pipeline derive": PermissionClass.WRITE,
        "pipeline validate": PermissionClass.READ,
        "pipeline diff": PermissionClass.READ,
        "config get": PermissionClass.READ,
        "config set": PermissionClass.WRITE,
        # `eval run` writes a corpus into a store and a run record to disk — `write`, the
        # identical class `index` already carries for the identical reason. `eval compare`/
        # `trace` only read persisted files — `read`, `weft_cli.eval_commands`'s own module
        # docstring has the argument in full, including why neither is `overwrite`/`destroy`.
        "eval run": PermissionClass.WRITE,
        "eval compare": PermissionClass.READ,
        # `eval metrics` only reads the registry already built at process start — `read`,
        # `weft_cli.eval_commands`'s own module docstring.
        "eval metrics": PermissionClass.READ,
        "trace": PermissionClass.READ,
    }
    for name, permission in expected_permissions.items():
        entry = registry.entry(Command, name)
        permission_class = cast(PermissionClass, getattr(entry.factory, "permission_class", None))
        help_text = cast(str, getattr(entry.factory, "help", None))
        assert permission_class is permission
        assert help_text  # every command declares a non-empty one-liner


async def test_init_command_writes_weft_toml_in_the_current_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(commands, "DEFAULT_CONFIG_PATH", tmp_path / "weft.toml")
    deps = Dependencies(registry=Registry(), reports=(), services=ServiceSelection())

    # Act
    outcome = await commands.InitCommand().run(commands.NoArgs(), _ctx(deps))

    # Assert
    assert isinstance(outcome, Produced)
    result = outcome.value
    assert isinstance(result, commands.InitCommandResult)
    written = (tmp_path / "weft.toml").read_text(encoding="utf-8")
    assert "[services]" in written
    assert "[permissions]" in written
    assert result.path == str(tmp_path / "weft.toml")


async def test_init_command_refuses_to_overwrite_an_existing_weft_toml(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange — repair, 2026-08-20: `init` is `write`-class now, so it never reaches
    # `weft_cli.confirm.gate` at all; the safety `overwrite` used to buy moves here instead,
    # an unconditional, loud refusal rather than a TTY prompt.
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / "weft.toml"
    config_path.write_text("# a project's own weft.toml, already here\n", encoding="utf-8")
    monkeypatch.setattr(commands, "DEFAULT_CONFIG_PATH", config_path)
    deps = Dependencies(registry=Registry(), reports=(), services=ServiceSelection())

    # Act / Assert — refused by name, the existing file untouched, never a prompt.
    with pytest.raises(commands.TargetAlreadyExistsError) as raised:
        await commands.InitCommand().run(commands.NoArgs(), _ctx(deps))
    assert str(config_path) in str(raised.value)
    assert config_path.read_text(encoding="utf-8") == "# a project's own weft.toml, already here\n"


async def test_index_command_raises_a_refusal_before_running_when_a_pack_is_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Arrange
    async def _boom(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("run_index must not run when a required pack is refused")

    monkeypatch.setattr(commands, "run_index", _boom)
    reports = (
        PackReport(distribution="weft-extract", status=PackStatus.REFUSED, reason="not allowed"),
    )
    deps = Dependencies(registry=Registry(), reports=reports, services=ServiceSelection())
    args = commands.IndexArgs(path=str(tmp_path))

    # Act / Assert
    with pytest.raises(commands.CommandRefusalError) as excinfo:
        await commands.IndexCommand().run(args, _ctx(deps))
    assert excinfo.value.exit_code is ExitCode.POLICY_REFUSED
    # Repair, 2026-08-20 (finding 2): `require_active`'s own refusal is never a name-resolution
    # failure — it never resolves `UnknownPluginError` at all — so it must never be the new,
    # `valid_options`-carrying family member either.
    assert not isinstance(excinfo.value, commands.UnresolvedPluginNameError)


async def test_index_command_produces_a_result_carrying_the_run_summary(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Arrange
    registry = Registry()
    registry.add(Embedder, "hash", _null_factory, distribution="weft-embed")
    registry.add(NodeStore, "pgvector", _null_factory, distribution="weft-store")
    reports = tuple(
        PackReport(distribution=d, status=PackStatus.ACTIVE)
        for d in ("weft-extract", "weft-chunk", "weft-embed", "weft-store")
    )
    deps = Dependencies(registry=registry, reports=reports, services=ServiceSelection())
    summary = RunSummary(produced=3, nothing_to_produce=0, failed=0)

    async def _fake_run_index(*_args: object, **_kwargs: object) -> IndexResult:
        return IndexResult(summary=summary, stored_count=3)

    monkeypatch.setattr(commands, "run_index", _fake_run_index)
    args = commands.IndexArgs(path=str(tmp_path))

    # Act
    outcome = await commands.IndexCommand().run(args, _ctx(deps))

    # Assert
    assert isinstance(outcome, Produced)
    result = outcome.value
    assert isinstance(result, commands.IndexCommandResult)
    assert result.summary == summary
    assert result.stored_count == 3


async def test_index_command_refuses_extract_and_pipeline_together(tmp_path: Path) -> None:
    # Arrange — task 4.0: a document's own `extract` stage already names its plugin, so
    # `--extract` would have nothing left to narrow; both together is refused before either
    # resolves a plugin, `ConflictingAskModeError`'s exact footing applied to `weft index`.
    deps = Dependencies(registry=Registry(), reports=(), services=ServiceSelection())
    args = commands.IndexArgs(path=str(tmp_path), extract="pdf-text", pipeline="custom")

    # Act / Assert
    with pytest.raises(commands.ConflictingIndexModeError) as excinfo:
        await commands.IndexCommand().run(args, _ctx(deps))
    assert "--extract" in str(excinfo.value)
    assert "--pipeline" in str(excinfo.value)


async def test_index_command_with_pipeline_skips_the_default_path_s_plugin_checks(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Arrange — task 4.0: `INDEX_DISTRIBUTIONS`/`[services] embed`/`[services] store` are the
    # default four-stage path's own promises. A named document may depend on none of them —
    # here every one of the three is refused — and the command must still call `run_index`
    # rather than raising `CommandRefusalError` for a promise the document never made.
    reports = tuple(
        PackReport(distribution=d, status=PackStatus.REFUSED, reason="not allowed")
        for d in ("weft-extract", "weft-chunk", "weft-embed")
    )
    deps = Dependencies(registry=Registry(), reports=reports, services=ServiceSelection())
    summary = RunSummary(produced=1, nothing_to_produce=0, failed=0)
    calls: list[dict[str, object]] = []

    async def _fake_run_index(*_args: object, **kwargs: object) -> IndexResult:
        calls.append(kwargs)
        return IndexResult(summary=summary, stored_count=1)

    monkeypatch.setattr(commands, "run_index", _fake_run_index)
    args = commands.IndexArgs(path=str(tmp_path), pipeline="custom")

    # Act
    outcome = await commands.IndexCommand().run(args, _ctx(deps))

    # Assert
    assert isinstance(outcome, Produced)
    result = outcome.value
    assert isinstance(result, commands.IndexCommandResult)
    assert result.stored_count == 1
    assert calls[0]["pipeline"] == "custom"
    assert calls[0]["reports"] == reports


async def test_ask_command_retrieve_only_raises_a_refusal_for_an_unregistered_embedder() -> None:
    # Arrange
    reports = (
        PackReport(distribution="weft-embed", status=PackStatus.PARTIAL, reason="optional missing"),
        PackReport(distribution="weft-store", status=PackStatus.ACTIVE),
    )
    deps = Dependencies(registry=Registry(), reports=reports, services=ServiceSelection())
    args = commands.AskArgs(question="what changed?", retrieve_only=True)

    # Act / Assert
    with pytest.raises(commands.CommandRefusalError) as excinfo:
        await commands.AskCommand().run(args, _ctx(deps))
    assert excinfo.value.exit_code is ExitCode.RESOLUTION_FAILED


async def test_ask_command_retrieve_only_names_the_embedders_for_an_unresolvable_name() -> None:
    # Arrange — repair, 2026-08-20 (finding 2): `require_plugin` catches `weft_kernel.registry.
    # UnknownPluginError`, which already carries `valid_options`, and it must survive into
    # whatever `AskCommand.run` raises rather than being discarded into a message string only.
    registry = Registry()
    registry.add(Embedder, "hash", _null_factory, distribution="weft-embed")
    reports = (
        PackReport(distribution="weft-embed", status=PackStatus.PARTIAL, reason="optional missing"),
        PackReport(distribution="weft-store", status=PackStatus.ACTIVE),
    )
    deps = Dependencies(
        registry=registry, reports=reports, services=ServiceSelection(embed="opneai")
    )
    args = commands.AskArgs(question="what changed?", retrieve_only=True)

    # Act / Assert
    with pytest.raises(commands.UnresolvedPluginNameError) as excinfo:
        await commands.AskCommand().run(args, _ctx(deps))
    assert excinfo.value.exit_code is ExitCode.RESOLUTION_FAILED
    assert excinfo.value.valid_options == ("hash",)
    assert isinstance(excinfo.value, commands.CommandRefusalError)


async def test_ask_command_retrieve_only_ranks_hits_from_run_ask(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    registry = Registry()
    registry.add(Embedder, "hash", _null_factory, distribution="weft-embed")
    registry.add(NodeStore, "pgvector", _null_factory, distribution="weft-store")
    reports = (
        PackReport(distribution="weft-embed", status=PackStatus.ACTIVE),
        PackReport(distribution="weft-store", status=PackStatus.ACTIVE),
    )
    deps = Dependencies(registry=registry, reports=reports, services=ServiceSelection())

    node = Node.synthetic(content="a passage", media_type=MediaType.TEXT, reason="test")
    scored = Scored[Node](value=node, score=0.5)

    async def _fake_run_ask(*_args: object, **_kwargs: object) -> tuple[Scored[Node], ...]:
        return (scored,)

    monkeypatch.setattr(commands, "run_ask", _fake_run_ask)
    args = commands.AskArgs(question="what changed?", retrieve_only=True)

    # Act
    outcome = await commands.AskCommand().run(args, _ctx(deps))

    # Assert
    assert isinstance(outcome, Produced)
    result = outcome.value
    assert isinstance(result, commands.AskCommandResult)
    assert result.question == "what changed?"
    assert result.answer is None
    assert len(result.hits) == 1
    assert result.hits[0].content == "a passage"
    assert result.hits[0].rank == 1


async def test_ask_command_refuses_retrieve_only_and_pipeline_together() -> None:
    # Arrange — task 3.11: two mutually exclusive claims about what this run should do,
    # refused loudly before either resolves a plugin (CLAUDE.md: "a silent fallback is
    # worse than a failure").
    deps = Dependencies(registry=Registry(), reports=(), services=ServiceSelection())
    args = commands.AskArgs(question="what changed?", retrieve_only=True, pipeline="specific")

    # Act / Assert
    with pytest.raises(commands.ConflictingAskModeError):
        await commands.AskCommand().run(args, _ctx(deps))


async def test_ask_command_routes_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange — task 3.11: `weft ask` reaches the pipeline the router names with no
    # second command to know about; `RouteCommand`'s own former body, folded in here.
    deps = Dependencies(registry=Registry(), reports=(), services=ServiceSelection())
    query = Query(text="what changed?")
    answer = Answer(
        origin=query,
        text="the answer",
        stance=AnswerStance.ANSWERED,
        citations=(),
        used=(),
        answered_by="scripted",
    )

    async def _fake_run_routed_ask(*_args: object, **_kwargs: object) -> tuple[str, Answer]:
        return "specific", answer

    monkeypatch.setattr(commands, "run_routed_ask", _fake_run_routed_ask)
    args = commands.AskArgs(question="what changed?")

    # Act
    outcome = await commands.AskCommand().run(args, _ctx(deps))

    # Assert
    assert isinstance(outcome, Produced)
    result = outcome.value
    assert isinstance(result, commands.AskCommandResult)
    assert result.pipeline_name == "specific"
    assert result.answer is answer
    assert result.hits == ()


async def test_ask_command_with_pipeline_names_one_directly_and_skips_the_router(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange — `--pipeline` is what a caller who wants a specific pipeline uses now that
    # `route` no longer exists as a separate command; it must never reach the router.
    deps = Dependencies(registry=Registry(), reports=(), services=ServiceSelection())
    query = Query(text="what changed?")
    answer = Answer(
        origin=query,
        text="the answer",
        stance=AnswerStance.ANSWERED,
        citations=(),
        used=(),
        answered_by="scripted",
    )
    seen_pipeline_names: list[str] = []

    async def _fake_run_named_ask(*_args: object, **kwargs: object) -> Answer:
        seen_pipeline_names.append(cast(str, kwargs["pipeline_name"]))
        return answer

    async def _boom(*_args: object, **_kwargs: object) -> tuple[str, Answer]:
        raise AssertionError("--pipeline must never fall through to the router")

    monkeypatch.setattr(commands, "run_named_ask", _fake_run_named_ask)
    monkeypatch.setattr(commands, "run_routed_ask", _boom)
    args = commands.AskArgs(question="what changed?", pipeline="retrieve-then-generate")

    # Act
    outcome = await commands.AskCommand().run(args, _ctx(deps))

    # Assert
    assert isinstance(outcome, Produced)
    result = outcome.value
    assert isinstance(result, commands.AskCommandResult)
    assert result.pipeline_name == "retrieve-then-generate"
    assert result.answer is answer
    assert seen_pipeline_names == ["retrieve-then-generate"]


async def test_ask_command_passes_the_run_s_own_token_sink(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange — task 3.6, carried unchanged by task 3.11's fold-in: `AskCommand` must hand
    # `run_routed_ask` the sink `weft_cli.cli.main` chose (carried on `Dependencies.
    # token_sink`), not build or assume one of its own — G6's "the CLI registers a
    # TokenSink implementation".
    class _MarkedSink:
        async def emit(self, chunk: object) -> None:
            del chunk

        async def close(self, *, reason: str | None = None) -> None:
            del reason

    chosen = _MarkedSink()
    deps = Dependencies(
        registry=Registry(), reports=(), services=ServiceSelection(), token_sink=chosen
    )
    query = Query(text="what changed?")
    answer = Answer(
        origin=query,
        text="the answer",
        stance=AnswerStance.ANSWERED,
        citations=(),
        used=(),
        answered_by="scripted",
    )
    seen_sinks: list[object] = []

    async def _fake_run_routed_ask(*_args: object, **kwargs: object) -> tuple[str, Answer]:
        seen_sinks.append(kwargs["sink"])
        return "specific", answer

    monkeypatch.setattr(commands, "run_routed_ask", _fake_run_routed_ask)
    args = commands.AskArgs(question="what changed?")

    # Act
    await commands.AskCommand().run(args, _ctx(deps))

    # Assert
    assert seen_sinks == [chosen]


async def test_plugins_list_command_reports_the_run_s_reports() -> None:
    # Arrange
    reports = (PackReport(distribution="weft-chunk", status=PackStatus.ACTIVE),)
    deps = Dependencies(registry=Registry(), reports=reports, services=ServiceSelection())

    # Act
    outcome = await commands.PluginsListCommand().run(commands.NoArgs(), _ctx(deps))

    # Assert
    assert isinstance(outcome, Produced)
    result = outcome.value
    assert isinstance(result, commands.PluginsListCommandResult)
    assert result.reports == reports


async def test_plugins_doctor_command_reports_displaced_and_unconsulted_pins() -> None:
    # Arrange — task 1.12/repair shapes, read straight off the registry, unchanged.
    class _Chunker:
        """A stand-in contract — only its `__name__` is ever read by rendering."""

    registry = Registry(plugin_pins={"_Chunker:shared": "weft-winner"})
    registry.add(_Chunker, "shared", lambda: "loser", distribution="weft-loser")
    registry.add(_Chunker, "shared", lambda: "winner", distribution="weft-winner")
    reports = (
        PackReport(distribution="weft-loser", status=PackStatus.ACTIVE, contributed=1),
        PackReport(distribution="weft-winner", status=PackStatus.ACTIVE, contributed=1),
    )
    deps = Dependencies(registry=registry, reports=reports, services=ServiceSelection())

    # Act
    outcome = await commands.PluginsDoctorCommand().run(commands.NoArgs(), _ctx(deps))

    # Assert
    assert isinstance(outcome, Produced)
    result = outcome.value
    assert isinstance(result, commands.PluginsDoctorCommandResult)
    assert result.reports == reports
    assert len(result.displaced) == 1
    assert result.displaced[0].distribution == "weft-loser"
    # This test's own venv is `uv sync`ed, so nothing is skewed — see
    # `tests/unit/weft_cli/test_skew.py` for the mechanism proven against doubles instead;
    # task 5.2e's own ledger entry records a real, force-installed skew against the
    # shipped binary, which is the only way to see a genuine disagreement fire.
    assert result.skew == ()


async def test_plugins_doctor_command_reports_the_skew_detect_skew_finds() -> None:
    # Arrange — task 5.2e: proves `PluginsDoctorCommand` actually wires `detect_skew()`
    # in, rather than merely happening to pass through a clean environment's empty result.
    reports = (PackReport(distribution="weft-cli", status=PackStatus.ACTIVE, contributed=1),)
    deps = Dependencies(registry=Registry(), reports=reports, services=ServiceSelection())
    skewed = SkewReport(
        requiring_distribution="weft-cli",
        required_distribution="weft-kernel",
        specifier=">=0.1.0,<1.0.0",
        installed_version="9.9.9",
    )

    with mock.patch("weft_cli.commands.detect_skew", return_value=(skewed,)) as mocked:
        # Act
        outcome = await commands.PluginsDoctorCommand().run(commands.NoArgs(), _ctx(deps))

    # Assert
    mocked.assert_called_once_with()
    assert isinstance(outcome, Produced)
    result = outcome.value
    assert isinstance(result, commands.PluginsDoctorCommandResult)
    assert result.skew == (skewed,)


async def test_plugins_doctor_command_flags_a_contribution_that_lands_nowhere() -> None:
    """Task **5.3a** (`S8`) — `02` §3 → *Slots*: "`weft plugins doctor` flags a pack whose
    contributions land in no pipeline at all." No pipeline in the (empty) catalogue this
    test resolves against declares any slot, so this pack's own offer is unreachable.
    """
    # Arrange
    reports = (PackReport(distribution="weft-graph", status=PackStatus.ACTIVE, contributed=1),)
    contribution = Contribution(
        slot="enrich",
        distribution="weft-graph",
        stage=StageDeclaration(id="entities", use="entity-extractor"),
    )
    deps = Dependencies(
        registry=Registry(),
        reports=reports,
        services=ServiceSelection(),
        contributions=(contribution,),
    )

    # Act
    outcome = await commands.PluginsDoctorCommand().run(commands.NoArgs(), _ctx(deps))

    # Assert
    assert isinstance(outcome, Produced)
    result = outcome.value
    assert isinstance(result, commands.PluginsDoctorCommandResult)
    assert result.unreachable_contributions == (contribution,)


def test_delete_describes_its_impact_by_naming_every_participant() -> None:
    # Arrange
    registry = Registry()
    registry.add(NodeStore, "pgvector", _DeletableStore, distribution="weft-store")
    deps = Dependencies(
        registry=registry,
        reports=(PackReport(distribution="weft-store", status=PackStatus.ACTIVE),),
        services=ServiceSelection(store="pgvector"),
    )

    # Act
    stated = commands.DeleteCommand().describe_impact(
        commands.DeleteArgs(source_id="doc-1"), _ctx(deps)
    )

    # Assert
    assert stated == "'doc-1' will be removed from 1 participant(s): pgvector (weft-store)."


class _GraphNodeStore:
    """A second `NodeStore` — the graph pack's position in `02` §4's table, in miniature.

    It holds its own contents, because task **6.18**'s check is the *store's contents* and
    not the participant list: a fan-out that names the graph store and never reaches it is
    exactly the failure G13 settled, and a list assertion alone would not tell the two apart.
    """

    contents: ClassVar[dict[str, int]] = {}

    def __init__(self, config: object = None) -> None:
        del config

    async def delete_source(self, source_id: object) -> Removed:
        removed = type(self).contents.pop(str(source_id), 0)
        return Removed(source_id=SourceId(str(source_id)), node_count=removed)


class _PrimaryNodeStore:
    """The store `[services] store` names — present so the graph store is the *second* one."""

    def __init__(self, config: object = None) -> None:
        del config

    async def delete_source(self, source_id: object) -> Removed:
        return Removed(source_id=SourceId(str(source_id)), node_count=1)


async def test_delete_empties_a_graph_store_a_catalogue_pipeline_names(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Task **6.18**, G13's first repair, reproduced the way `docs/build-ledger.md` states it:
    a pipeline in the catalogue names a second `NodeStore`, a source is deleted, and that
    store must no longer hold it. Before this task the graph store was outside the fan-out
    entirely — `[services] store` chose one `NodeStore` and the rest were excluded — so its
    contents survived their source with nothing said about it.
    """
    # Arrange
    monkeypatch.chdir(tmp_path)
    (tmp_path / "pipelines").mkdir()
    (tmp_path / "pipelines" / "kg.yaml").write_text(
        "name: kg\nstages:\n  - id: store\n    use: pgvector\n"
        "  - id: graph-store\n    use: example-graph\n",
        encoding="utf-8",
    )
    _GraphNodeStore.contents = {"doc-1": 4}
    registry = Registry()
    registry.add(NodeStore, "pgvector", _PrimaryNodeStore, distribution="weft-store")
    registry.add(NodeStore, "example-graph", _GraphNodeStore, distribution="weft-example-graph")
    deps = Dependencies(
        registry=registry,
        reports=(
            PackReport(distribution="weft-store", status=PackStatus.ACTIVE),
            PackReport(distribution="weft-example-graph", status=PackStatus.ACTIVE),
        ),
        services=ServiceSelection(store="pgvector"),
    )

    # Act
    outcome = await commands.DeleteCommand().run(commands.DeleteArgs(source_id="doc-1"), _ctx(deps))

    # Assert
    assert _GraphNodeStore.contents == {}
    assert isinstance(outcome, Produced)
    result = outcome.value
    assert isinstance(result, commands.DeleteCommandResult)
    assert sorted((o.plugin, o.node_count) for o in result.participants) == [
        ("example-graph", 4),
        ("pgvector", 1),
    ]


def test_delete_leaves_a_store_nothing_names_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The half of task 5.1a's narrowing G13 kept: an installed, registered `NodeStore` that
    no document and no run record names is not asked, because it is the operator's unused
    database and connecting to it is the harm the narrowing existed to prevent.
    """
    # Arrange
    monkeypatch.chdir(tmp_path)
    registry = Registry()
    registry.add(NodeStore, "pgvector", _PrimaryNodeStore, distribution="weft-store")
    registry.add(NodeStore, "qdrant", _GraphNodeStore, distribution="weft-qdrant")
    deps = Dependencies(
        registry=registry,
        reports=(PackReport(distribution="weft-store", status=PackStatus.ACTIVE),),
        services=ServiceSelection(store="pgvector"),
    )

    # Act
    stated = commands.DeleteCommand().describe_impact(
        commands.DeleteArgs(source_id="doc-1"), _ctx(deps)
    )

    # Assert
    assert "qdrant" not in stated


def test_delete_refuses_an_unresolvable_store_before_it_describes_an_impact() -> None:
    """The repair L5.9 records: the prompt used to state "nothing installed holds data" for a
    store that was installed and had failed to register, and the real diagnosis was reachable
    only past `--yes`. `describe_impact` now makes the same check `run` does, first.
    """
    # Arrange
    deps = Dependencies(
        registry=Registry(),
        reports=(PackReport(distribution="weft-store", status=PackStatus.FAILED, reason="no dsn"),),
        services=ServiceSelection(store="pgvector"),
    )

    # Act
    with pytest.raises(commands.CommandRefusalError) as raised:
        commands.DeleteCommand().describe_impact(commands.DeleteArgs(source_id="doc-1"), _ctx(deps))

    # Assert
    assert "[services] store names 'pgvector'" in str(raised.value)


class _CorpusAsking:
    """A `Reconcilable` participant that is *not* the primary store and needs to see it.

    Task **6.19**, G13's second repair. `02` §1 → *Extended by G13*: "the CLI registers the
    configured store into the `Context` a reconcile pass carries, and a participant reaches it
    with `ctx.require(NodeStore)`." This stands in for the graph pack, which needs to know what
    the corpus holds before it can backfill anything derived from it.
    """

    seen: ClassVar[list[str]] = []

    def __init__(self, config: object = None) -> None:
        del config

    async def reconcile(self, ctx: Context, mode: ReconcileMode) -> ReconcileReport:
        corpus = ctx.require(NodeStore)
        type(self).seen.append(type(corpus).__name__)
        return ReconcileReport(mode=mode, examined=1, backfilled=1)

    async def estimate(self, ctx: Context, mode: ReconcileMode) -> ReconcileEstimate:
        corpus = ctx.require(NodeStore)
        type(self).seen.append(type(corpus).__name__)
        return ReconcileEstimate(mode=mode, pending=1, description="one node to backfill")


async def test_reconcile_puts_the_configured_store_on_the_passport_it_carries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The property task **6.19** makes true: a participant that is not the primary store can
    ask what the corpus holds, through `Context.require` — G1's one resolution seam — rather
    than through a wider `reconcile` signature. No contract moves to make this work.
    """
    # Arrange
    monkeypatch.chdir(tmp_path)
    _CorpusAsking.seen = []
    registry = Registry()
    registry.add(NodeStore, "pgvector", _ReconcilableStore, distribution="weft-store")
    registry.add(_DerivedReconcilable, "graph", _CorpusAsking, distribution="weft-example-graph")
    deps = Dependencies(
        registry=registry,
        reports=(PackReport(distribution="weft-store", status=PackStatus.ACTIVE),),
        services=ServiceSelection(store="pgvector"),
    )

    # Act
    outcome = await commands.ReconcileCommand().run(
        commands.ReconcileArgs(mode=ReconcileMode.FULL), _ctx(deps)
    )

    # Assert
    assert _CorpusAsking.seen == ["_ReconcilableStore", "_ReconcilableStore"]
    assert isinstance(outcome, Produced)


async def test_a_participant_asking_for_a_corpus_that_is_not_there_is_told_so(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`weft index --pipeline ...` in a project with no `[services] store` still indexes, and
    its automatic post-index pass deliberately skips the store gate — so a participant that
    needs the corpus there finds nothing registered. It is told, by name, and the fan-out
    records it as that participant's own failure rather than swallowing it: an unavailable
    corpus is not a backfill of zero.
    """
    # Arrange
    monkeypatch.chdir(tmp_path)
    _CorpusAsking.seen = []
    registry = Registry()
    registry.add(_DerivedReconcilable, "graph", _CorpusAsking, distribution="weft-example-graph")
    deps = Dependencies(registry=registry, reports=(), services=ServiceSelection(store="pgvector"))

    # Act
    targets = reconcile_module_participants(registry=registry, store_names=frozenset({"pgvector"}))
    outcomes = await reconcile_everywhere(ReconcileMode.FULL, targets=targets, ctx=_ctx(deps))

    # Assert
    assert outcomes[0].error is not None
    assert "NodeStore" in outcomes[0].error


def _reconcilable_deps(*, reconcile_policy: ReconcilePolicy | None = None) -> Dependencies:
    registry = Registry()
    registry.add(NodeStore, "pgvector", _ReconcilableStore, distribution="weft-store")
    return Dependencies(
        registry=registry,
        reports=(PackReport(distribution="weft-store", status=PackStatus.ACTIVE),),
        services=ServiceSelection(store="pgvector"),
        reconcile_policy=reconcile_policy if reconcile_policy is not None else ReconcilePolicy(),
    )


async def test_reconcile_command_falls_back_to_weft_toml_when_the_flag_is_omitted() -> None:
    # Arrange — task 5.1c: the flag is `None`, so `weft.toml`'s own `[reconcile] mode`
    # decides, exactly as `weft_cli.reconcile_policy`'s own module docstring promises.
    deps = _reconcilable_deps(reconcile_policy=ReconcilePolicy(mode=ReconcileMode.REPAIR))
    args = commands.ReconcileArgs(mode=None, dry_run=False)

    # Act
    outcome = await commands.ReconcileCommand().run(args, _ctx(deps))

    # Assert
    assert isinstance(outcome, Produced)
    result = outcome.value
    assert isinstance(result, commands.ReconcileCommandResult)
    assert (result.mode, result.estimates) == (ReconcileMode.REPAIR, ())


async def test_reconcile_command_flag_wins_over_the_weft_toml_default() -> None:
    # Arrange — `weft.toml` says `repair`; `--mode full` on this one invocation still wins.
    deps = _reconcilable_deps(reconcile_policy=ReconcilePolicy(mode=ReconcileMode.REPAIR))
    args = commands.ReconcileArgs(mode=ReconcileMode.FULL, dry_run=False)

    # Act
    outcome = await commands.ReconcileCommand().run(args, _ctx(deps))

    # Assert
    assert isinstance(outcome, Produced)
    result = outcome.value
    assert isinstance(result, commands.ReconcileCommandResult)
    assert result.mode is ReconcileMode.FULL
    assert result.estimates[0].estimate is not None
    assert result.estimates[0].estimate.model_calls == 2


async def test_reconcile_command_repair_mode_computes_no_estimates() -> None:
    # Arrange — task 5.1c: `full` states its cost; `repair` never backfills, so it has none.
    deps = _reconcilable_deps()
    args = commands.ReconcileArgs(mode=ReconcileMode.REPAIR, dry_run=False)

    # Act
    outcome = await commands.ReconcileCommand().run(args, _ctx(deps))

    # Assert
    assert isinstance(outcome, Produced)
    result = outcome.value
    assert isinstance(result, commands.ReconcileCommandResult)
    assert result.estimates == ()


async def test_reconcile_command_full_dry_run_carries_the_cost_and_asks_nobody() -> None:
    # Arrange — bullet 3: "--dry-run prints the same block and stops."
    deps = _reconcilable_deps()
    args = commands.ReconcileArgs(mode=ReconcileMode.FULL, dry_run=True)

    # Act
    outcome = await commands.ReconcileCommand().run(args, _ctx(deps))

    # Assert
    assert isinstance(outcome, Produced)
    result = outcome.value
    assert isinstance(result, commands.ReconcileCommandResult)
    assert result.participants == ()
    assert result.would_ask == ("pgvector (weft-store)",)
    assert result.estimates[0].estimate is not None
    assert result.estimates[0].estimate.pending == 2


async def test_index_command_runs_an_automatic_repair_pass_after_a_successful_run(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Arrange — task 5.1c: no `--reconcile` flag, so the automatic pass is `repair` — never
    # `full` — regardless of anything `weft.toml` says.
    registry = Registry()
    registry.add(Embedder, "hash", _null_factory, distribution="weft-embed")
    registry.add(NodeStore, "pgvector", _ReconcilableStore, distribution="weft-store")
    reports = tuple(
        PackReport(distribution=d, status=PackStatus.ACTIVE)
        for d in ("weft-extract", "weft-chunk", "weft-embed", "weft-store")
    )
    deps = Dependencies(registry=registry, reports=reports, services=ServiceSelection())
    summary = RunSummary(produced=1, nothing_to_produce=0, failed=0)

    async def _fake_run_index(*_args: object, **_kwargs: object) -> IndexResult:
        return IndexResult(summary=summary, stored_count=1)

    monkeypatch.setattr(commands, "run_index", _fake_run_index)
    args = commands.IndexArgs(path=str(tmp_path))

    # Act
    outcome = await commands.IndexCommand().run(args, _ctx(deps))

    # Assert
    assert isinstance(outcome, Produced)
    result = outcome.value
    assert isinstance(result, commands.IndexCommandResult)
    assert result.reconcile is not None
    assert result.reconcile.mode is ReconcileMode.REPAIR
    assert result.reconcile.estimates == ()
    assert result.reconcile.participants[0].plugin == "pgvector"


async def test_index_command_reconcile_full_flag_opts_this_run_into_backfill(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Arrange — `weft index --reconcile full`, a person's own per-run flag.
    registry = Registry()
    registry.add(Embedder, "hash", _null_factory, distribution="weft-embed")
    registry.add(NodeStore, "pgvector", _ReconcilableStore, distribution="weft-store")
    reports = tuple(
        PackReport(distribution=d, status=PackStatus.ACTIVE)
        for d in ("weft-extract", "weft-chunk", "weft-embed", "weft-store")
    )
    deps = Dependencies(registry=registry, reports=reports, services=ServiceSelection())
    summary = RunSummary(produced=1, nothing_to_produce=0, failed=0)

    async def _fake_run_index(*_args: object, **_kwargs: object) -> IndexResult:
        return IndexResult(summary=summary, stored_count=1)

    monkeypatch.setattr(commands, "run_index", _fake_run_index)
    args = commands.IndexArgs(path=str(tmp_path), reconcile=ReconcileMode.FULL)

    # Act
    outcome = await commands.IndexCommand().run(args, _ctx(deps))

    # Assert
    assert isinstance(outcome, Produced)
    result = outcome.value
    assert isinstance(result, commands.IndexCommandResult)
    assert result.reconcile is not None
    assert result.reconcile.mode is ReconcileMode.FULL
    assert result.reconcile.estimates[0].estimate is not None
    assert result.reconcile.estimates[0].estimate.model_calls == 2
