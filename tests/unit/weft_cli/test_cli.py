"""Unit tests for `weft_cli.cli`.

Mirrors `packages/weft-cli/src/weft_cli/cli.py`. Covers `command_key`'s
mapping from parsed arguments to a `COMMANDS` entry, the argument grammar
`build_parser` builds, `dispatch`'s fitness-function-8(b) property — a
registry is built only for a command that declares `needs_registry=True` —
and the two command handlers' policy-refusal short-circuit, which must never
reach `run_index`/`run_ask` at all. External services (the registry a
command would otherwise build, the ingest and ask pipelines) are stubbed:
this tier proves the dispatch and refusal logic, not the pipelines
themselves — those are `tests/integration/test_cli_end_to_end.py`'s job.
"""

import argparse
import asyncio
import sys
from pathlib import Path

import pytest

from weft_cli import cli
from weft_cli.exit_codes import ExitCode
from weft_cli.output import AskFormat
from weft_cli.permissions import CliCommand, PermissionClass
from weft_cli.registry_bootstrap import Dependencies
from weft_cli.services import ServiceSelection
from weft_embed import Embedder
from weft_kernel.discovery import PackReport, PackStatus
from weft_kernel.registry import Registry


def _null_factory(config: object) -> object:
    """A registerable factory for a plugin no test ever calls — only resolves by name."""
    del config
    return object()


def test_command_key_selects_version_over_any_subcommand() -> None:
    # Arrange
    args = argparse.Namespace(version=True, command="index", plugins_command=None)

    # Act
    key = cli.command_key(args)

    # Assert
    assert key == "version"


def test_command_key_joins_the_plugins_subcommand() -> None:
    # Arrange
    args = argparse.Namespace(version=False, command="plugins", plugins_command="doctor")

    # Act
    key = cli.command_key(args)

    # Assert
    assert key == "plugins doctor"


def test_command_key_is_none_when_plugins_has_no_subcommand() -> None:
    # Arrange
    args = argparse.Namespace(version=False, command="plugins", plugins_command=None)

    # Act
    key = cli.command_key(args)

    # Assert
    assert key is None


def test_only_version_is_declared_as_not_needing_the_registry() -> None:
    # Arrange / Act
    needs_registry = {key: command.needs_registry for key, command in cli.COMMANDS.items()}

    # Assert
    assert needs_registry == {
        "version": False,
        "index": True,
        "ask": True,
        "route": True,
        "plugins list": True,
        "plugins doctor": True,
    }


def test_build_parser_parses_index() -> None:
    # Arrange
    parser = cli.build_parser()

    # Act
    args = parser.parse_args(["index", "./docs-to-index"])

    # Assert
    assert (args.command, args.path) == ("index", "./docs-to-index")


def test_build_parser_parses_ask_with_a_default_top_k() -> None:
    # Arrange
    parser = cli.build_parser()

    # Act
    args = parser.parse_args(["ask", "what changed?"])

    # Assert
    assert (args.command, args.question, args.top_k) == ("ask", "what changed?", 5)
    assert args.format is AskFormat.TEXT, (
        "the default reader of `weft ask` is a person, and structured output is opt-in — a "
        "default of JSON would change what every existing invocation prints"
    )


def test_build_parser_parses_the_ask_output_format_as_the_enum_member() -> None:
    # Arrange — `--format` reaches `handle_ask` as an `AskFormat`, not a string, so the
    # comparison there is against a member rather than a spelling.
    parser = cli.build_parser()

    # Act
    args = parser.parse_args(["ask", "what changed?", "--format", "json"])

    # Assert
    assert args.format is AskFormat.JSON


def test_build_parser_rejects_an_output_format_nothing_renders() -> None:
    # `01` requirement 5: an unknown name fails loudly, naming the valid options. argparse's
    # own `choices` message lists them, which is the whole reason the enum is the choice list
    # rather than a hand-written tuple that could fall behind it.
    # Arrange
    parser = cli.build_parser()

    # Act / Assert
    with pytest.raises(SystemExit):
        parser.parse_args(["ask", "what changed?", "--format", "yaml"])


def test_build_parser_rejects_an_unknown_command() -> None:
    # Arrange
    parser = cli.build_parser()

    # Act / Assert
    with pytest.raises(SystemExit):
        parser.parse_args(["bogus"])


async def test_dispatch_never_builds_a_registry_for_a_command_that_does_not_need_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    def _boom() -> Dependencies:
        raise AssertionError(
            "build_dependencies must not be called — this is fitness function 8(b)"
        )

    monkeypatch.setattr(cli, "build_dependencies", _boom)
    command = cli.COMMANDS["version"]

    # Act
    exit_code = await cli.dispatch(command, argparse.Namespace())

    # Assert
    assert exit_code is ExitCode.SUCCESS


async def test_dispatch_builds_a_registry_for_a_command_that_needs_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    fake_deps = Dependencies(registry=Registry(), reports=(), services=ServiceSelection())
    calls: list[Dependencies] = []

    async def _fake_handler(args: argparse.Namespace, deps: Dependencies) -> ExitCode:
        del args
        calls.append(deps)
        return ExitCode.SUCCESS

    def _fake_build_dependencies(*, strict_pins: bool = True) -> Dependencies:
        del strict_pins
        return fake_deps

    monkeypatch.setattr(cli, "build_dependencies", _fake_build_dependencies)
    command = CliCommand(
        name="ask",
        help="retrieve and print matching passages",
        permission=PermissionClass.READ,
        needs_registry=True,
        handler=_fake_handler,
    )

    # Act
    exit_code = await cli.dispatch(command, argparse.Namespace())

    # Assert
    assert exit_code is ExitCode.SUCCESS
    assert calls == [fake_deps]


async def test_dispatch_passes_strict_pins_false_only_for_the_two_plugins_commands() -> None:
    # Arrange — repair for a reviewer finding: `plugins list`/`plugins doctor` must ask
    # `build_dependencies` not to die on an inert `[plugins]` pin; every other
    # registry-needing command keeps the strict default. Table-driven over one
    # representative of each group rather than every entry in `COMMANDS`, since the
    # property under test is the boolean `dispatch` computes from `command.name`, not
    # anything specific to any one handler.
    seen: dict[str, bool] = {}

    async def _fake_handler(args: argparse.Namespace, deps: Dependencies) -> ExitCode:
        del args, deps
        return ExitCode.SUCCESS

    for name in ("plugins list", "plugins doctor", "ask", "index"):

        def _fake_build_dependencies(*, strict_pins: bool, _name: str = name) -> Dependencies:
            seen[_name] = strict_pins
            return Dependencies(registry=Registry(), reports=(), services=ServiceSelection())

        with pytest.MonkeyPatch.context() as monkeypatch:
            monkeypatch.setattr(cli, "build_dependencies", _fake_build_dependencies)
            command = CliCommand(
                name=name,
                help="test command",
                permission=PermissionClass.READ,
                needs_registry=True,
                handler=_fake_handler,
            )
            await cli.dispatch(command, argparse.Namespace())

    # Assert
    assert seen["plugins list"] is False
    assert seen["plugins doctor"] is False
    assert seen["ask"] is True
    assert seen["index"] is True


async def test_handle_index_refuses_before_running_when_a_required_pack_is_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Arrange — `handle_index` imports `run_index` locally (fitness function 8(b): see
    # `weft_cli.cli`'s module docstring), so the patch target is `weft_cli.ingest.run_index`
    # itself, not a `cli`-module attribute — the local import resolves against the module at
    # call time, which is exactly what lets this patch take effect.
    async def _boom(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("run_index must not run when a required pack is refused")

    monkeypatch.setattr("weft_cli.ingest.run_index", _boom)
    reports = (
        PackReport(distribution="weft-extract", status=PackStatus.REFUSED, reason="not allowed"),
    )
    deps = Dependencies(registry=Registry(), reports=reports, services=ServiceSelection())
    args = argparse.Namespace(path=str(tmp_path))

    # Act
    exit_code = await cli.handle_index(args, deps)

    # Assert
    assert exit_code is ExitCode.POLICY_REFUSED


async def test_handle_ask_reports_resolution_failure_when_a_required_pack_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange — see the sibling `handle_index` test above: `handle_ask` imports `run_ask`
    # locally, so the patch target is `weft_cli.ask.run_ask`, not a `cli`-module attribute.
    async def _boom(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("run_ask must not run when a required pack is missing")

    monkeypatch.setattr("weft_cli.ask.run_ask", _boom)
    deps = Dependencies(
        registry=Registry(), reports=(), services=ServiceSelection()
    )  # nothing discovered at all
    args = argparse.Namespace(question="what changed?", top_k=5)

    # Act
    exit_code = await cli.handle_ask(args, deps)

    # Assert
    assert exit_code is ExitCode.RESOLUTION_FAILED


async def test_handle_ask_reports_resolution_failure_for_an_unregistered_embedder() -> None:
    # Arrange — the report set says the registry-needing gate (`require_active`) would pass:
    # 'weft-embed' is PARTIAL (something registered) and 'weft-store' is ACTIVE. But the
    # registry itself has no 'hash' Embedder registered, so `run_ask`'s own
    # `registry.entry(Embedder, "hash")` raises `UnknownPluginError` — exactly the case
    # `require_active`'s own docstring defers to pipeline resolution. This must come back as
    # resolution failure (4), the same as `handle_index` treats it, not the generic
    # operation-failure catch-all (1) — `docs/03-cli.md` -> Output.
    reports = (
        PackReport(
            distribution="weft-embed", status=PackStatus.PARTIAL, reason="optional dep missing"
        ),
        PackReport(distribution="weft-store", status=PackStatus.ACTIVE),
    )
    deps = Dependencies(
        registry=Registry(), reports=reports, services=ServiceSelection()
    )  # no 'hash' Embedder registered
    args = argparse.Namespace(question="what changed?", top_k=5)

    # Act
    exit_code = await cli.handle_ask(args, deps)

    # Assert
    assert exit_code is ExitCode.RESOLUTION_FAILED


async def test_handle_index_blames_policy_when_the_selected_embedders_pack_is_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # Arrange — the reproduction task 2.29 opened: `[services] embed` names a plugin from a
    # distribution no list in this repository can contain, and `[packs] allow` leaves it off.
    # Every distribution `require_active` knows about is ACTIVE, so that gate passes and the
    # old code went on to tell the operator, falsely, that nothing had registered the name.
    async def _boom(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("run_index must not run when the selected embedder is unreachable")

    monkeypatch.setattr("weft_cli.ingest.run_index", _boom)
    registry = Registry()
    registry.add(Embedder, "hash", _null_factory, distribution="weft-embed")
    reports = (
        *(
            PackReport(distribution=distribution, status=PackStatus.ACTIVE)
            for distribution in ("weft-extract", "weft-chunk", "weft-embed", "weft-store")
        ),
        PackReport(
            distribution="weft-openai", status=PackStatus.REFUSED, reason="not in [packs] allow"
        ),
    )
    deps = Dependencies(
        registry=registry, reports=reports, services=ServiceSelection(embed="openai")
    )
    args = argparse.Namespace(path=str(tmp_path), extract=None)

    # Act
    exit_code = await cli.handle_index(args, deps)

    # Assert
    assert exit_code is ExitCode.POLICY_REFUSED
    printed = capsys.readouterr().err
    assert "weft-openai" in printed
    assert "[packs] allow" in printed


async def test_handle_ask_blames_policy_when_the_selected_embedders_pack_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange — the same hole on the query side. It has to close on both: an index built with
    # one embedder and a question embedded by another are vectors in unrelated spaces.
    async def _boom(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("run_ask must not run when the selected embedder is unreachable")

    monkeypatch.setattr("weft_cli.ask.run_ask", _boom)
    registry = Registry()
    registry.add(Embedder, "hash", _null_factory, distribution="weft-embed")
    reports = (
        PackReport(distribution="weft-embed", status=PackStatus.ACTIVE),
        PackReport(distribution="weft-store", status=PackStatus.ACTIVE),
        PackReport(
            distribution="weft-openai", status=PackStatus.REFUSED, reason="not in [packs] allow"
        ),
    )
    deps = Dependencies(
        registry=registry, reports=reports, services=ServiceSelection(embed="openai")
    )
    args = argparse.Namespace(question="what changed?", top_k=5)

    # Act
    exit_code = await cli.handle_ask(args, deps)

    # Assert
    assert exit_code is ExitCode.POLICY_REFUSED


async def test_handle_index_blames_policy_for_an_extractor_named_from_a_refused_pack(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Arrange — `--extract` has always been able to name a stranger's plugin, so the same gate
    # covers it: the fix is about a name an operator supplies, not about embedders.
    async def _boom(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("run_index must not run when the named extractor is unreachable")

    monkeypatch.setattr("weft_cli.ingest.run_index", _boom)
    reports = (
        *(
            PackReport(distribution=distribution, status=PackStatus.ACTIVE)
            for distribution in ("weft-extract", "weft-chunk", "weft-embed", "weft-store")
        ),
        PackReport(
            distribution="acme-docx", status=PackStatus.REFUSED, reason="not in [packs] allow"
        ),
    )
    registry = Registry()
    registry.add(Embedder, "hash", _null_factory, distribution="weft-embed")
    deps = Dependencies(registry=registry, reports=reports, services=ServiceSelection())
    args = argparse.Namespace(path=str(tmp_path), extract="docx")

    # Act
    exit_code = await cli.handle_index(args, deps)

    # Assert
    assert exit_code is ExitCode.POLICY_REFUSED


async def test_handle_plugins_doctor_prints_a_displaced_registration_from_the_registry(
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Arrange — task 1.12: the registry, not `deps.reports`, is where a displaced
    # registration lives; `handle_plugins_doctor` must read it off `deps.registry`.
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
    exit_code = await cli.handle_plugins_doctor(argparse.Namespace(), deps)
    output = capsys.readouterr().out

    # Assert
    assert exit_code is ExitCode.SUCCESS
    assert "weft-winner" in output
    assert "displaced" in output


def test_main_renders_an_untranslated_exception_without_a_traceback(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A driving adapter never speaks in stack traces.

    `weft index` and `weft ask` failed differently against the same unreachable database:
    `index` printed one line, because every stage runs through the registration seam, and
    `ask` printed twelve lines of `psycopg` traceback, because it resolves its store directly
    and there is no stage to attribute. `docs/03-cli.md` -> *Output* does not offer a third
    behaviour for "the library raised something weft has no translation for".
    """
    # Arrange — a handler that raises what no `except` clause in `dispatch` names.
    monkeypatch.setattr(
        cli, "dispatch", _raising_dispatch(RuntimeError("connection failed: port 59999"))
    )
    monkeypatch.setattr(sys, "argv", ["weft", "--version"])

    # Act
    with pytest.raises(SystemExit) as exit_info:
        cli.main()

    # Assert
    captured = capsys.readouterr()
    assert exit_info.value.code == int(ExitCode.OPERATION_FAILED)
    assert "RuntimeError: connection failed: port 59999" in captured.err
    assert "Traceback" not in captured.err
    assert "WEFT_TRACEBACK=1" in captured.err


def test_main_re_raises_when_weft_traceback_is_set(monkeypatch: pytest.MonkeyPatch) -> None:
    """ "No traceback" is right for a user and wrong for whoever has to fix it."""
    # Arrange
    monkeypatch.setattr(cli, "dispatch", _raising_dispatch(RuntimeError("boom")))
    monkeypatch.setattr(sys, "argv", ["weft", "--version"])
    monkeypatch.setenv("WEFT_TRACEBACK", "1")

    # Act / Assert
    with pytest.raises(RuntimeError, match="boom"):
        cli.main()


def test_main_does_not_swallow_cancellation(monkeypatch: pytest.MonkeyPatch) -> None:
    """G6: `CancelledError` propagates and is never swallowed. It is a `BaseException`, so the
    last-resort `except Exception` must not see it — asserted rather than assumed, because a
    later widening to `BaseException` would look like a harmless tidy-up.
    """
    # Arrange
    monkeypatch.setattr(cli, "dispatch", _raising_dispatch(asyncio.CancelledError()))
    monkeypatch.setattr(sys, "argv", ["weft", "--version"])

    # Act / Assert
    with pytest.raises(asyncio.CancelledError):
        cli.main()


def _raising_dispatch(exc: BaseException) -> object:
    """A stand-in for `cli.dispatch` that raises inside the one `asyncio.run`."""

    async def _dispatch(_command: object, _args: object) -> ExitCode:
        raise exc

    return _dispatch
