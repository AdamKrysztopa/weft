"""`Weft` — the embeddable verb. Ledger task **24.1**.

`02` → *both driving use cases* has named a second driving adapter since Phase 0: an application
opens a `weft.toml`, asks a question and gets an `Answer`, with no subprocess and no parsed
stdout in between. `weft_cli` is the first adapter; this module is the second.

**The one thing this must not become**, named in the phase preamble because it is what a
reasonable commit would do: build a second assembly path beside `weft_cli` — a registry, a
resolved pipeline, a call straight into `run_named_ask`. That path would read well and would be
requirement 4 lost. So `Weft` resolves a `weft_command.contract.Command` **from the registry, by
name**, and runs it through `weft_command.invocation.invoke` — the one seam
`weft_cli.cli.run_command` already goes through, and the one fitness function 20 pins to a single
module. `Weft` never calls `run_ask`, `run_index`, `run_named_ask` or `run_routed_ask`, and never
imports `weft_cli` at all — that property belongs to this module exactly as much as to
`weft_engine.registry_bootstrap`, which established it first.

**`new_context`** is `weft_cli.cli._context`'s body, made public here because both adapters need
one `Context` per invocation and two copies could disagree about what "one per invocation" means.

**`LibraryConsent`** is `weft_cli.cli.TtyConsent`'s sibling and its whole point is the
difference: there is no terminal behind a library call, so there is nothing to prompt. It answers
the same `overwrite`/`destroy` question `weft_cli.confirm.gate` answers, minus the prompt — an
application either says `yes=True` for this call, or the operator's own `[permissions]` table
says `allow`, or the call is refused, loudly, naming the parameter that would have permitted it.
"""

from __future__ import annotations

import dataclasses
import uuid
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, cast

from weft_command.contract import Command, CommandResult
from weft_command.invocation import invoke
from weft_command.permission import CommandRefusalError, PermissionClass
from weft_command.render import ExitCode
from weft_engine.permission_policy import PermissionAction, PermissionPolicy
from weft_engine.registry_bootstrap import DEFAULT_CONFIG_PATH, Dependencies, build_dependencies
from weft_kernel.context import Context
from weft_kernel.errors import WeftError
from weft_kernel.payload import Produced, SourceId
from weft_kernel.seam import aclose

if TYPE_CHECKING:
    from pydantic import BaseModel

    # `TYPE_CHECKING`-only, not the module-scope import `weft_generate.payload`'s own contents
    # would otherwise suggest: importing it for real pulls in `weft_retrieve` (its own
    # `payload` submodule imports `weft_store.contract`, which runs `weft_store/__init__.py` —
    # real pack code, `psycopg`/`pgvector` included) at `weft_engine.api` import time, which is
    # `weft_cli.cli`'s own module scope — exactly the FF8(b) violation this file's docstring
    # promises not to cause. `cast("Answer", ...)` below is the runtime-side half: `cast`'s
    # first argument is never evaluated, so the string form needs no runtime import at all.
    from weft_generate.payload import Answer
    from weft_llm.contract import TokenSink


def new_context() -> Context:
    """One `Context` per invocation, at tenant `"default"`, and it takes no tenant. G23: an
    in-process caller is the operator and the deployment is the boundary
    (`docs/02-extension-model.md` §2), so a tenant a caller could choose here would be a label
    enforcing nothing. Fitness function 32 holds this as the only place a shipped module mints a
    `Context`, and fails naming Phase 22b when a commit makes the tenant choosable.

    Lifted verbatim from `weft_cli.cli._context`, which now calls this rather than carrying its
    own copy — one context builder for both driving adapters, not two that could disagree.
    """
    return Context(
        tenant_id="default", run_id=str(uuid.uuid4()), trace_id=str(uuid.uuid4()), locale="en"
    )


@dataclasses.dataclass(frozen=True)
class LibraryConsent:
    """`weft_command.invocation.Consent` as a library call answers it.

    `weft_cli.cli.TtyConsent`'s sibling, and the difference is the whole point: there is no
    terminal behind a library call, so there is no prompt to fall back to. See
    `weft_cli.confirm.gate` for the decision this mirrors, minus the prompt
    (`packages/weft-rag/src/weft_cli/confirm.py:168 "Not part of the Protocol body"`).
    """

    yes: bool
    policy: PermissionPolicy

    async def decide(self, *, command_name: str, instance: object, args: BaseModel) -> None:
        # Same defensive read, same safest-possible default, as `weft_cli.confirm.gate`'s own
        # — `permission_class` is a `required_declarations` name, not an `isinstance` member.
        permission_class = cast(
            PermissionClass, getattr(instance, "permission_class", PermissionClass.DESTROY)
        )
        if permission_class not in (PermissionClass.OVERWRITE, PermissionClass.DESTROY):
            return

        action = (
            self.policy.destroy
            if permission_class is PermissionClass.DESTROY
            else self.policy.overwrite
        )
        if self.yes or action is PermissionAction.ALLOW:
            return

        # `mode="json"` rather than a bare dump — a raw `Enum` member spliced into a sentence
        # a person reads, which is the reason `gate`'s own comment gives
        # (`packages/weft-rag/src/weft_cli/confirm.py:184 "leaves an `Enum` member as the"`).
        called_with = args.model_dump(mode="json")
        raise CommandRefusalError(
            f"'{command_name}' is a {permission_class.value}-class command, called with "
            f"{called_with}. It refuses to run with no terminal to confirm in, and never "
            f"proceeds silently. Pass yes=True to permit it for this invocation.",
            exit_code=ExitCode.POLICY_REFUSED,
        )


@dataclasses.dataclass(frozen=True, slots=True)
class _Held:
    """One instance `Weft` has been asked to close when its block exits, and the four
    identifying strings `weft_kernel.seam.aclose` needs to attribute a close failure.
    """

    instance: object
    distribution: str
    contract: str
    plugin: str
    stage: str | None


class Weft:
    """The second driving adapter: open a `weft.toml`, ask, get an `Answer` — one `async with`.

    Not frozen and not a dataclass: it holds mutable state, namely what this session has opened
    and is holding open until the block exits.
    """

    def __init__(self, dependencies: Dependencies) -> None:
        self.dependencies = dependencies
        self._held: list[_Held] = []

    @classmethod
    def open(
        cls,
        config_path: Path | str = DEFAULT_CONFIG_PATH,
        *,
        strict_pins: bool = True,
        token_sink: TokenSink | None = None,
    ) -> Weft:
        """Discover every installed pack against `config_path`, honouring `[packs] allow` —
        `build_dependencies` and nothing else. A second assembly here is the phase's own named
        hazard; this calls the identical assembler `weft_cli.cli.main` calls.

        Not `async`: nothing here awaits. `async with Weft.open(path) as w` still works, because
        `__aenter__` runs on the instance this returns.
        """
        deps = build_dependencies(Path(config_path), strict_pins=strict_pins, token_sink=token_sink)
        return cls(deps)

    async def __aenter__(self) -> Weft:
        return self

    async def __aexit__(self, exc_type: object, exc: BaseException | None, tb: object) -> None:
        """Close everything this session holds, reverse of the order it was held in, and never
        suppress the caller's own exception.

        Mirrors `weft_kernel.runner.Runner._flush_all`, whose own docstring states the rule
        this discharges — carried repair `R18.1`: *"raising here would replace it"*
        (`packages/weft-kernel/src/weft_kernel/runner.py:977 "async def _flush_all"`).
        Every held instance gets its chance to close regardless of an earlier one's failure;
        `self.dependencies.token_sink` closes last, because a sink a caller passed in may well
        hold a file even though `weft_llm.client.NullSink` (a run that built no sink of its own)
        has no `aclose` and the seam simply returns for it.

        If `exc` is already propagating, a close failure is attached to it as a note and nothing
        is raised — a `CancelledError` turned into a `WeftError` here would be a cancelled task
        that merely raised. Only when the block exited cleanly does the first close failure, if
        there was one, get raised.

        **Returns `None` rather than `False`**, which is the same answer to the protocol and a
        different one to a type checker: a `-> bool` `__aexit__` tells pyright the block *may*
        suppress, so every variable a caller binds inside an `async with Weft…` becomes
        "possibly unbound" afterwards. That is a false warning this class would have handed to
        every application that uses it.
        """
        failures: list[WeftError] = []
        for held in reversed(self._held):
            try:
                await aclose(
                    held.instance,
                    distribution=held.distribution,
                    contract=held.contract,
                    plugin=held.plugin,
                    stage=held.stage,
                )
            except WeftError as close_failure:
                failures.append(close_failure)

        try:
            await aclose(
                self.dependencies.token_sink,
                distribution="weft-rag",
                contract="TokenSink",
                plugin=type(self.dependencies.token_sink).__name__,
            )
        except WeftError as close_failure:
            failures.append(close_failure)

        if exc is not None:
            for failure in failures:
                exc.add_note(f"close failed during cleanup: {failure}")
            return

        if failures:
            raise failures[0]

    def hold(
        self,
        instance: object,
        *,
        distribution: str,
        contract: str,
        plugin: str,
        stage: str | None = None,
    ) -> None:
        """Register `instance` to be closed through `weft_kernel.seam.aclose` when this
        session's block exits.

        Public: a caller that built a store or an embedder itself, outside `Weft.open`, and
        wants the session to reap it has the identical need the session already has for what it
        opened for itself — and `__aexit__` is the only place that knows when the block ends.
        """
        self._held.append(
            _Held(
                instance=instance,
                distribution=distribution,
                contract=contract,
                plugin=plugin,
                stage=stage,
            )
        )

    async def ask(
        self,
        question: str,
        *,
        pipeline: str | None = None,
        top_k: int = 5,
        token_sink: TokenSink | None = None,
    ) -> Answer:
        """Resolve the `Command` registered as `"ask"` and run it, returning its `Answer`.

        `token_sink` is where this call's tokens stream, as `run` describes. Ranked passages
        with no answer are `run("ask", {"question": ..., "retrieve_only": True})`'s result: a
        retrieve-only run fills `hits` and never `answer`, so it has no place behind `-> Answer`
        (carried repair `R22.6`).

        Raises `WeftError` if the command produced no answer — an application handed `None`
        cannot tell "no answer for this question" from "the command does not answer at all",
        the silent-fallback shape `CLAUDE.md` refuses.
        """
        result = await self._invoke(
            "ask",
            {
                "question": question,
                "pipeline": pipeline,
                "top_k": top_k,
            },
            token_sink=token_sink,
        )
        answer = getattr(result, "answer", None)
        if answer is None:
            raise WeftError(
                f"'ask' produced no answer for question={question!r}, pipeline={pipeline!r}, "
                f"top_k={top_k!r}."
            )
        return cast("Answer", answer)

    async def index(
        self,
        directory: Path | str,
        *,
        yes: bool = False,
        token_sink: TokenSink | None = None,
    ) -> CommandResult:
        """Resolve the `Command` registered as `"index"` and run it against `directory`.

        `token_sink` is where this call's tokens stream, as `run` describes: an ingest rung that
        calls a model emits them too.

        The key is `path` because that is what `weft_cli.commands.IndexArgs` calls the field,
        and `_invoke` projects through the model's own names: a key the model does not declare
        is dropped, so a plausible-looking `directory` here reaches `IndexArgs(**{})` and the
        run dies on a missing required field. Found by running the binary at task 24.2 — the
        unit tests could not see it, because their `Command` doubles declared the names this
        method was passing rather than the names the shipped commands declare (`L12.11`).
        """
        return await self._invoke("index", {"path": str(directory)}, yes=yes, token_sink=token_sink)

    async def delete(self, source: SourceId | str | Path, *, yes: bool = False) -> CommandResult:
        """Resolve the `Command` registered as `"delete"` and run it against `source`.

        `source_id`, for the reason `index` above states about `path`.

        **`Path` is in the union because a source id usually is one.** `weft index` records the
        *resolved* path of every file it read, so the natural thing to hand this method is the
        same `Path` that was handed to `index` — and the first application written against it did
        exactly that and failed type checking (`examples/weft-example-app/app.py`). Accepting
        only `str` would make every caller write `str(...)` at a seam where a path is the honest
        value. Resolving is still the caller's: an unresolved path names a source nothing holds,
        and the run reports `0 node(s) removed` rather than an error, because deleting what is
        not there is not a failure.
        """
        return await self._invoke("delete", {"source_id": str(source)}, yes=yes)

    async def run(
        self,
        command_name: str,
        fields: Mapping[str, object] | None = None,
        *,
        yes: bool = False,
        token_sink: TokenSink | None = None,
    ) -> CommandResult:
        """Run any registered `Command` by name — the general verb the three below are wrappers of.

        **This is public because requirement 4 says so, and it was private for a while.** A real
        installation registers 24 `Command`s — `graph show`, `agent`, `eval run`, `pipeline
        derive` and twenty more — and `weft_cli.cli.run_command` dispatches all of them
        generically, from this same registry, by name. While `ask`/`index`/`delete` were the only
        public entries, a pack's contributed command was reachable from the terminal and not from
        an application: the *built-in* adapter held the general mechanism and the public surface
        held three special cases, which is the privileged path this phase exists to close, running
        the other way. `weft-qualities` found it at the phase close; no test did.

        `fields` are projected through the command's own `args_model`, so the names are the ones
        that command declares — `weft plugins doctor --json` shows them, and the model refuses an
        unknown one. `yes` answers the permission gate for an `overwrite`/`destroy`-class command
        exactly as it does for `delete`: reaching a command by string is not a way around a
        refusal the same command makes by method.

        **`token_sink` belongs to this call** (carried repair `R22.5`). Omitted, the call streams
        into the sink `Weft.open` was given, which every call on the session shares. Given, the
        call streams into it alone and closes it when the call ends, exactly once: `reason=None`
        on success, the failure's message otherwise — the rule `weft_cli.cli.run_command` applies
        to a terminal run's sink. `TokenChunk` carries no run id, so this is the only way two
        concurrent calls on one session can be told apart.
        """
        return await self._invoke(command_name, fields or {}, yes=yes, token_sink=token_sink)

    async def _invoke(
        self,
        command_name: str,
        fields: Mapping[str, object],
        *,
        yes: bool = False,
        token_sink: TokenSink | None = None,
    ) -> CommandResult:
        """Resolve `command_name` from the registry, project `fields` through its own
        `args_model`, and run it through `weft_command.invocation.invoke` — the one seam both
        driving adapters share.

        `entry()` is what raises `weft_kernel.registry.UnknownPluginError`, naming every command
        the registry does hold, when `command_name` is not one of them — requirement 5, and no
        new exception type is invented for it here.
        """
        # Local import — `weft_engine.run_services` pulls `weft_embed`/`weft_store`/
        # `weft_retrieve`/`weft_llm`/`weft_prompts` in transitively, and fitness function 8(b)
        # requires `weft --version` to execute no pack code at all. `weft_cli.cli.run_command`
        # imports this exact function the same way, for the same reason.
        from weft_engine.run_services import command_path_services

        entry = self.dependencies.registry.entry(Command, command_name)
        instance = cast(Command, entry.factory(None))

        all_fields = {**fields, "yes": yes}
        payload = {
            name: all_fields[name]
            for name in instance.args_model.model_fields
            if name in all_fields
        }
        args = instance.args_model(**payload)

        sink = self.dependencies.token_sink if token_sink is None else token_sink
        ctx = dataclasses.replace(
            new_context(),
            services=command_path_services(self.dependencies, sink=sink),
        )

        try:
            outcome = await invoke(
                command_name=command_name,
                instance=instance,
                args=args,
                ctx=ctx,
                consent=LibraryConsent(yes=yes, policy=self.dependencies.permissions),
                distribution=entry.distribution,
            )
            if not isinstance(outcome, Produced):
                raise WeftError(f"'{command_name}' did not produce a result: {outcome.reason}")
        except WeftError as failure:
            if token_sink is not None:
                await _close_after_failure(token_sink, reason=str(failure), failure=failure)
            raise
        except BaseException as failure:
            if token_sink is not None:
                await _close_after_failure(
                    token_sink, reason="command did not complete", failure=failure
                )
            raise
        if token_sink is not None:
            await token_sink.close(reason=None)
        return outcome.value


async def _close_after_failure(sink: TokenSink, *, reason: str, failure: BaseException) -> None:
    """Close a call's own sink while `failure` propagates, attaching a failed close to it as a
    note rather than letting it replace `failure` — carried repair `R18.1`'s rule, which
    `Weft.__aexit__` also follows.
    """
    try:
        await sink.close(reason=reason)
    except Exception as close_failure:
        failure.add_note(f"closing the call's token sink failed: {close_failure}")
