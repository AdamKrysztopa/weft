"""`weft` — the command line. This module holds the library's only `asyncio.run`.

`docs/06-phase-0-build.md` step 9: "`weft index <path>`, `weft ask
<question>`, `weft plugins list|doctor`, `weft --version`. The single
`asyncio.run`, at the entry point." Fitness function 7(a) asserts, by path,
that this is the only call site in the tree — see
`tests/architecture/test_ff7_colour_integrity.py`.

**`COMMANDS` is where every built-in command declares its permission class —
see `weft_cli.permissions` for why there is no default and no separate
registration step to forget it in.** `main` dispatches through it and nothing
else: there is no second, hand-written `if/elif` chain a new command could
land in without a class attached.

**Fitness function 8(b) — no pack code runs for a command that does not need
the registry.** `dispatch` calls `weft_cli.registry_bootstrap.build_dependencies`
— the one function that calls `weft_kernel.discovery.discover` — only when
`CliCommand.needs_registry` is `True`. `version` is the one command Phase 0
ships with it `False`; `docs/01-high-level-plan.md` names `weft --version`
as "precisely the command this clause is about." That property does not
survive an eager import: `weft_cli.ingest` and `weft_cli.ask` each import
`weft_extract`, `weft_chunk`, `weft_embed` and `weft_store` at their own
module scope, to reach the contract classes their `StageSpec`s and direct
resolutions name. Importing either module at `cli.py`'s module scope would
therefore execute thirteen pack modules' bodies for `weft --version` too —
`needs_registry=False` alone cannot stop an import that already ran before
`dispatch` is even called. `handle_index` and `handle_ask` import them
locally instead, so a pack module is only ever imported by the one handler
that actually needs it.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import uuid
from importlib import metadata
from pathlib import Path

from weft_cli.exit_codes import ExitCode
from weft_cli.permissions import CliCommand, PermissionClass
from weft_cli.plugins_report import render_doctor, render_list
from weft_cli.registry_bootstrap import Dependencies, build_dependencies, require_active
from weft_kernel.context import Context
from weft_kernel.errors import WeftError
from weft_kernel.registry import Registry, UnknownPluginError
from weft_kernel.runner import PipelineResolutionError

_DISTRIBUTION = "weft-cli"

#: `weft ask` says, in its own help text, that it does not generate — the fourth,
#: smaller trap `docs/06-phase-0-build.md` names: "Phase 0's `weft ask` retrieves and
#: prints the matching passages, and says so in its help text."
_ASK_HELP = (
    "retrieve and print the passages nearest a question. Generation is Phase 2 — "
    "this command prints matching passages, it composes no answer."
)


def build_parser() -> argparse.ArgumentParser:
    """The argument grammar for every command in `COMMANDS`."""
    parser = argparse.ArgumentParser(prog="weft", description="Weft — a microkernel RAG engine.")
    parser.add_argument("--version", action="store_true", help="print the version and exit")
    subparsers = parser.add_subparsers(dest="command")

    index_parser = subparsers.add_parser(
        "index", help="run the built-in ingest pipeline over a directory of text files"
    )
    index_parser.add_argument("path", help="directory of .txt/.md files to index")

    ask_parser = subparsers.add_parser("ask", help=_ASK_HELP, description=_ASK_HELP)
    ask_parser.add_argument("question")
    ask_parser.add_argument("--top-k", type=int, default=5, dest="top_k")

    plugins_parser = subparsers.add_parser("plugins", help="report on discovered packs")
    plugins_sub = plugins_parser.add_subparsers(dest="plugins_command")
    plugins_sub.add_parser("list", help="one line per discovered pack")
    plugins_sub.add_parser("doctor", help="full status, reason and disclosure per discovered pack")

    return parser


async def handle_version(args: argparse.Namespace, deps: Dependencies) -> ExitCode:
    del args, deps  # neither is used — see the module docstring on fitness function 8(b)
    print(f"weft {metadata.version(_DISTRIBUTION)}")
    return ExitCode.SUCCESS


async def handle_index(args: argparse.Namespace, deps: Dependencies) -> ExitCode:
    # Local import — keeps `weft --version` categorically pack-code-free (fitness function
    # 8(b), see the module docstring): `weft_cli.ingest` imports weft_extract, weft_chunk,
    # weft_embed and weft_store at its own module scope, so importing it up at `cli.py`'s
    # module scope would run all of that for every command, `version` included.
    from weft_cli.ingest import INDEX_DISTRIBUTIONS, run_index

    refusal = require_active(deps.reports, distributions=INDEX_DISTRIBUTIONS)
    if refusal is not None:
        code, message = refusal
        print(message, file=sys.stderr)
        return code

    try:
        result = await run_index(Path(args.path), registry=deps.registry, ctx=_context())
    except (UnknownPluginError, PipelineResolutionError) as exc:
        print(str(exc), file=sys.stderr)
        return ExitCode.RESOLUTION_FAILED
    except WeftError as exc:
        print(str(exc), file=sys.stderr)
        return ExitCode.OPERATION_FAILED

    summary = result.summary
    stored = "unknown" if result.stored_count is None else str(result.stored_count)
    print(
        f"produced {summary.produced}, nothing to produce {summary.nothing_to_produce}, "
        f"failed {summary.failed}. nodes now stored: {stored}."
    )
    for reason in summary.failed_reasons:
        print(f"  failed: {reason}", file=sys.stderr)
    return ExitCode.SUCCESS if summary.failed == 0 else ExitCode.OPERATION_FAILED


async def handle_ask(args: argparse.Namespace, deps: Dependencies) -> ExitCode:
    # Local import — see `handle_index`'s note and the module docstring on fitness function
    # 8(b): `weft_cli.ask` imports weft_embed and weft_store at its own module scope.
    from weft_cli.ask import render_results, run_ask

    refusal = require_active(deps.reports, distributions=("weft-embed", "weft-store"))
    if refusal is not None:
        code, message = refusal
        print(message, file=sys.stderr)
        return code

    try:
        results = await run_ask(
            args.question, registry=deps.registry, ctx=_context(), top_k=args.top_k
        )
    except (UnknownPluginError, PipelineResolutionError) as exc:
        # `run_ask` resolves `Embedder` and `NodeStore` directly against `deps.registry`
        # rather than through `Runner.resolve` — but `require_active` above only rules out a
        # distribution being entirely absent, refused, or failed; it does not know whether the
        # specific plugin name `run_ask` asks for ("hash", "pgvector") is the one a PARTIAL or
        # otherwise-active distribution actually registered. That is exactly what
        # `UnknownPluginError` reports, so it is resolution failure (4) here for the same reason
        # `handle_index` treats it that way — `docs/03-cli.md` -> Output: "4 stays with genuine
        # resolution failure: a name no pack provides, or one lost to a failed or partial
        # registration."
        print(str(exc), file=sys.stderr)
        return ExitCode.RESOLUTION_FAILED
    except WeftError as exc:
        print(str(exc), file=sys.stderr)
        return ExitCode.OPERATION_FAILED

    if not results:
        print("no matching passages found.")
        return ExitCode.SUCCESS
    # Rendering lives in `weft_cli.ask.render_results` — one copy, so the rule in
    # `docs/03-cli.md` -> *Output*, *Score display* has exactly one place to be wrong.
    print(render_results(results))
    return ExitCode.SUCCESS


async def handle_plugins_list(args: argparse.Namespace, deps: Dependencies) -> ExitCode:
    del args
    print(render_list(deps.reports))
    return ExitCode.SUCCESS


async def handle_plugins_doctor(args: argparse.Namespace, deps: Dependencies) -> ExitCode:
    del args
    print(render_doctor(deps.reports))
    return ExitCode.SUCCESS


#: Every command Phase 0 ships, each declaring its permission class — no default,
#: see `weft_cli.permissions.CliCommand`. This is the whole dispatch surface: `main`
#: reads it and nothing else.
COMMANDS: dict[str, CliCommand] = {
    "version": CliCommand(
        name="version",
        help="print the weft-cli version and exit",
        permission=PermissionClass.READ,
        needs_registry=False,
        handler=handle_version,
    ),
    "index": CliCommand(
        name="index",
        help="run the built-in ingest pipeline over a directory of text files",
        permission=PermissionClass.WRITE,
        needs_registry=True,
        handler=handle_index,
    ),
    "ask": CliCommand(
        name="ask",
        help=_ASK_HELP,
        permission=PermissionClass.READ,
        needs_registry=True,
        handler=handle_ask,
    ),
    "plugins list": CliCommand(
        name="plugins list",
        help="one line per discovered pack",
        permission=PermissionClass.READ,
        needs_registry=True,
        handler=handle_plugins_list,
    ),
    "plugins doctor": CliCommand(
        name="plugins doctor",
        help="full status, reason and disclosure per discovered pack",
        permission=PermissionClass.READ,
        needs_registry=True,
        handler=handle_plugins_doctor,
    ),
}


def command_key(args: argparse.Namespace) -> str | None:
    """The `COMMANDS` key `args` selects, or `None` when no command was named at all."""
    if args.version:
        return "version"
    if args.command == "plugins":
        plugins_command = args.plugins_command
        return f"plugins {plugins_command}" if plugins_command is not None else None
    return args.command


async def dispatch(command: CliCommand, args: argparse.Namespace) -> ExitCode:
    """Build a registry only if `command` needs one — see the module docstring, FF8(b)."""
    if not command.needs_registry:
        return await command.handler(args, Dependencies(registry=Registry(), reports=()))

    try:
        deps = build_dependencies()
    except WeftError as exc:
        # Discovery itself failed to build a registry at all, before a single PackReport
        # exists to blame — either weft.toml is not valid TOML at all
        # (weft_cli.registry_bootstrap.ConfigFileError, wrapping tomllib.TOMLDecodeError /
        # OSError) or it parses fine but `[packs] allow` is not a list of distribution names
        # (weft_kernel.discovery.allow_list_from_config's own WeftError). Neither is a policy
        # refusal any specific distribution earned, so both are resolution failure (4).
        print(str(exc), file=sys.stderr)
        return ExitCode.RESOLUTION_FAILED
    return await command.handler(args, deps)


def _context() -> Context:
    """One `Context` per invocation. Phase 0 has no multi-tenancy surface, so `tenant_id`
    is a fixed default rather than a flag — see `docs/01-high-level-plan.md` → *The least-
    architecture check*, "carry a tenant identifier... build no isolation machinery until
    it is real."
    """
    return Context(
        tenant_id="default", run_id=str(uuid.uuid4()), trace_id=str(uuid.uuid4()), locale="en"
    )


def main() -> None:
    """The one entry point. The one `asyncio.run`. Fitness function 7(a)'s subject."""
    parser = build_parser()
    args = parser.parse_args()
    key = command_key(args)
    if key is None:
        parser.error("a command is required (index, ask, plugins list, plugins doctor, --version)")
        return  # unreachable — parser.error() exits the process with code 2

    command = COMMANDS[key]
    try:
        exit_code = asyncio.run(dispatch(command, args))
    except Exception as exc:  # noqa: BLE001 — see `_report_unexpected`; this is the last resort
        _report_unexpected(command.name, exc)
        sys.exit(int(ExitCode.OPERATION_FAILED))
    sys.exit(int(exit_code))


def _report_unexpected(command_name: str, exc: Exception) -> None:
    """Render an exception no handler translated, loudly and without a traceback.

    **Why this exists.** `weft index` and `weft ask` failed differently against the same
    unreachable database: `index` printed one line and exited 1, because every stage runs
    through the registration seam, which attributes the failure. `ask` resolves its store
    directly — there is no stage to attribute — so a `psycopg.OperationalError` travelled all
    the way out of `asyncio.run` and printed twelve lines of traceback at a user whose actual
    mistake was a typo in a port number. `docs/03-cli.md` -> *Output* offers no third
    behaviour for "the library raised something weft has no translation for".

    **Why it catches `Exception` rather than a list.** A driving adapter's job is that the
    process never speaks in stack traces, and the set of exception types a *pack* can raise is
    unbounded by construction — that is what the plugin model means. Enumerating them here
    would be a list that goes stale the first time someone installs a pack this repository has
    never seen. This is the opposite of a silent fallback: nothing is swallowed, the type and
    message are printed, and the exit code is non-zero.

    `BaseException` is deliberately not caught, so `CancelledError` propagates untouched (G6)
    and `KeyboardInterrupt` still ends the process the way a user expects.

    `WEFT_TRACEBACK=1` re-raises instead, because "no traceback" is right for a user and wrong
    for whoever has to fix it.
    """
    if os.environ.get("WEFT_TRACEBACK") == "1":
        raise exc

    print(f"weft {command_name}: {type(exc).__name__}: {exc}", file=sys.stderr)
    print(
        "This is an error weft did not translate — the message above comes from the library "
        "that raised it. Re-run with WEFT_TRACEBACK=1 for the full traceback.",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
