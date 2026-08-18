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
from weft_cli.permissions import CliCommand, PermissionClass
from weft_cli.registry_bootstrap import Dependencies
from weft_kernel.discovery import PackReport, PackStatus
from weft_kernel.registry import Registry


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
    fake_deps = Dependencies(registry=Registry(), reports=())
    calls: list[Dependencies] = []

    async def _fake_handler(args: argparse.Namespace, deps: Dependencies) -> ExitCode:
        del args
        calls.append(deps)
        return ExitCode.SUCCESS

    monkeypatch.setattr(cli, "build_dependencies", lambda: fake_deps)
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
    deps = Dependencies(registry=Registry(), reports=reports)
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
    deps = Dependencies(registry=Registry(), reports=())  # nothing discovered at all
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
    deps = Dependencies(registry=Registry(), reports=reports)  # no 'hash' Embedder registered
    args = argparse.Namespace(question="what changed?", top_k=5)

    # Act
    exit_code = await cli.handle_ask(args, deps)

    # Assert
    assert exit_code is ExitCode.RESOLUTION_FAILED


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
