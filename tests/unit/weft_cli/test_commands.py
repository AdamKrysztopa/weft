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
from typing import cast

import pytest

from weft_cli import commands
from weft_cli.exit_codes import ExitCode
from weft_cli.ingest import IndexResult
from weft_cli.registry_bootstrap import Dependencies
from weft_cli.services import ServiceSelection
from weft_command.contract import Command
from weft_command.permission import PermissionClass
from weft_embed import Embedder
from weft_generate.payload import Answer, AnswerStance
from weft_kernel.context import Context
from weft_kernel.discovery import PackRegistrar, PackReport, PackStatus
from weft_kernel.payload import MediaType, Node, Produced
from weft_kernel.registry import Registry
from weft_kernel.runner import RunSummary
from weft_retrieve.payload import Query
from weft_store import NodeStore, Scored


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
    # (folded into `ask`, `docs/build-ledger.md`'s own 3.11 entry), back to twelve.
    assert registry.names_for(Command) == {
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
