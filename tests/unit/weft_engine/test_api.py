"""Unit tests for `weft_engine.api` — the embeddable verb, ledger task **24.1**.

Mirrors `packages/weft-rag/src/weft_engine/api.py`. `Weft` is the second driving adapter `02`
→ *both driving use cases* has named since Phase 0 and `01` says this engine should have: an
application opens a `weft.toml`, asks a question and gets an `Answer`, with no subprocess and
no parsed stdout in between.

**What these tests are actually holding, and it is not the happy path.** The phase preamble
names the one thing a reasonable commit would get wrong: *"the shortest way to an embeddable
API is a second assembly path beside `weft_cli` — build a registry, resolve a pipeline, call
`run_named_ask`. That path would work, would read well, and would be requirement 4 lost."* So
the assertions below are about **which path ran**, not about what came back. Every one of them
registers a stand-in `Command` under the name the verb is supposed to resolve, and fails if the
verb reached past the registry to whatever the CLI happens to call — which is exactly what a
test asserting only `answer.text == "…"` would not notice.

`weft_command.invocation.invoke` is the seam both adapters go through, and fitness function 20
already pins it to one module. That is why this file asserts the `Command` ran and the consent
was asked, rather than asserting anything structural about imports: the check that no second
invocation path exists is FF20's, and duplicating it here as a grep would assert the current
arrangement rather than the property (`L9.39`).

**The doubles are built from the real thing, not from prose.** `_RecordingCommand` carries
`args_model`, `result_model`, `permission_class`, `help` and `version` because
`weft_command.contract.Command`'s `required_declarations` names two of them and
`__protocol_attrs__` requires two more — a double missing any of them is one the registry
refuses, which would fail these tests for a reason that has nothing to do with the verb
(`L17.17`).
"""

from __future__ import annotations

import asyncio
import inspect
from pathlib import Path
from typing import ClassVar

import pytest
from pydantic import BaseModel, ConfigDict

from weft_cli.commands import IndexArgs
from weft_command.contract import Command, CommandResult
from weft_command.permission import CommandRefusalError, PermissionClass
from weft_engine.api import Weft
from weft_engine.permission_policy import PermissionAction, PermissionPolicy
from weft_engine.registry_bootstrap import Dependencies
from weft_engine.services import ServiceSelection
from weft_generate.payload import Answer, AnswerStance, Citation
from weft_kernel.context import Context
from weft_kernel.errors import WeftError
from weft_kernel.payload import Failed, MediaType, Node, Outcome, Produced, SourceId
from weft_kernel.registry import Registry, UnknownPluginError
from weft_llm.contract import TokenSink
from weft_llm.payload import TokenChunk
from weft_retrieve.payload import Passage, Query
from weft_store import Scored


class _AskArgs(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    question: str
    pipeline: str | None = None
    retrieve_only: bool = False
    top_k: int = 5


class _DeleteArgs(BaseModel):
    """`source_id`, because that is the field `weft_cli.commands.DeleteArgs` declares.

    It said `source` until task 24.2 ran the binary. `_invoke` projects a caller's fields
    through the model's own names, so a double naming the field whatever the method happens to
    pass makes the projection assert nothing — and `Weft.delete` was passing `source`, which
    every shipped `delete` would have dropped (`L12.11`).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_id: str


class _AskResult(CommandResult):
    question: str
    answer: Answer | None = None


def _an_answer(text: str = "the seam closes what it opened") -> Answer:
    """A real `Answer`, with one citation that resolves — which is the part worth stating.

    `Answer._citations_resolve` refuses a citation whose `marker` and `node_id` do not both
    land on **one** passage in `used`, so a fixture carrying a citation and an empty `used`
    cannot be constructed at all. The first version of this helper did exactly that: it was
    written from `tests/unit/weft_cli/test_commands.py`'s own `Answer` fixture, which carries
    `citations=()` — so copying it produced a double that was correct about every field it
    copied and wrong about the one it added (`L11.17` from the other side). The implementer
    found it, could not fix it, and blocked; the passage below is what makes the citation real.

    The citation is not decoration here. Task `24.4`'s Exit prints `Answer.text` **and its
    citations** from outside this repository, so a fixture with no citation would leave the
    verb's only interesting return value unexercised until that run.
    """
    node = Node.synthetic(content="the seam", media_type=MediaType.TEXT, reason="test fixture")
    passage = Passage(
        scored=Scored(value=node, score=0.5),
        rank=0,
        retrieved_by="vector-top-k",
        label="[1]",
    )
    return Answer(
        origin=Query(text="what does the seam close?"),
        text=text,
        stance=AnswerStance.ANSWERED,
        citations=(
            Citation(
                marker="[1]",
                node_id=node.id,
                source_id=SourceId("note.txt"),
                quote="the seam",
            ),
        ),
        used=(passage,),
        answered_by="scripted",
    )


class _RecordingCommand:
    """A `Command` that records the arguments it was given and answers with a fixed `Answer`.

    Registered under the same name the verb must resolve. If `Weft.ask` assembled its own path
    instead of going through the registry, `calls` stays empty and every assertion below fails
    for the right reason.
    """

    calls: ClassVar[list[BaseModel]] = []

    args_model: ClassVar[type[BaseModel]] = _AskArgs
    result_model: ClassVar[type[CommandResult]] = _AskResult
    permission_class: ClassVar[PermissionClass] = PermissionClass.READ
    help: ClassVar[str] = "ask a question"
    version: ClassVar[str] = "1.0.0"

    def __init__(self, config: object = None) -> None:
        del config

    async def run(self, args: BaseModel, ctx: Context) -> Outcome[CommandResult]:
        del ctx
        type(self).calls.append(args)
        assert isinstance(args, _AskArgs)
        return Produced(value=_AskResult(question=args.question, answer=_an_answer()))


class _RefusingCommand(_RecordingCommand):
    """Answers `Failed`.

    A verb that returned `None` here would hand an application a value indistinguishable from a
    legitimate empty answer — the silent-fallback shape `CLAUDE.md` refuses by name.
    """

    calls: ClassVar[list[BaseModel]] = []

    async def run(self, args: BaseModel, ctx: Context) -> Outcome[CommandResult]:
        del ctx
        type(self).calls.append(args)
        return Failed(reason="the corpus holds nothing on that subject")


class _DestructiveCommand(_RecordingCommand):
    """`permission_class = DESTROY` — what an application must authorise explicitly.

    There is no TTY behind a library call, so the prompt `weft_cli.confirm.gate` falls back to
    does not exist here; `03` → *Permissions* leaves exactly two ways to permit such a run, and
    both are the caller's own words rather than an interaction.
    """

    calls: ClassVar[list[BaseModel]] = []
    args_model: ClassVar[type[BaseModel]] = _DeleteArgs
    permission_class: ClassVar[PermissionClass] = PermissionClass.DESTROY

    async def run(self, args: BaseModel, ctx: Context) -> Outcome[CommandResult]:
        del ctx
        type(self).calls.append(args)
        return Produced(value=_AskResult(question="deleted"))


def _deps(
    command: type[_RecordingCommand],
    *,
    name: str = "ask",
    permissions: PermissionPolicy | None = None,
) -> Dependencies:
    registry = Registry()
    registry.add(Command, name, command, distribution="weft-rag")
    if permissions is None:
        return Dependencies(registry=registry, reports=(), services=ServiceSelection())
    return Dependencies(
        registry=registry,
        reports=(),
        services=ServiceSelection(),
        permissions=permissions,
    )


@pytest.fixture(autouse=True)
def clear_recorded_calls() -> None:
    """Class-level `calls` lists are shared across tests; each starts from empty."""
    for cls in (_RecordingCommand, _RefusingCommand, _DestructiveCommand):
        cls.calls.clear()
    _StreamingCommand.emitted.clear()
    _StreamThenFailCommand.emitted.clear()


async def test_ask_runs_the_command_the_registry_holds_and_returns_its_answer() -> None:
    """The phase's whole point: one verb over the `Command` registry, requirement 4 intact."""
    # Arrange
    weft = Weft(_deps(_RecordingCommand))

    # Act
    async with weft as w:
        answer = await w.ask("what does the seam close?")

    # Assert — the registered command ran, and what came back is its `Answer`, not a rendering.
    assert len(_RecordingCommand.calls) == 1
    recorded = _RecordingCommand.calls[0]
    assert isinstance(recorded, _AskArgs)
    assert recorded.question == "what does the seam close?"
    assert isinstance(answer, Answer)
    assert answer.text == "the seam closes what it opened"
    assert answer.citations[0].source_id == SourceId("note.txt")


async def test_ask_passes_the_pipeline_name_it_was_given_to_the_command() -> None:
    """A value whose whole job is to travel from a caller to a call, so the call is captured.

    `L9.79`: where a value's only job is to reach a plugin, one test must read it off the call
    rather than off the result, or the wire is untested along its length.
    """
    # Arrange
    weft = Weft(_deps(_RecordingCommand))

    # Act
    async with weft as w:
        await w.ask("what changed?", pipeline="retrieve-then-generate")

    # Assert
    recorded = _RecordingCommand.calls[0]
    assert isinstance(recorded, _AskArgs)
    assert recorded.pipeline == "retrieve-then-generate"
    assert recorded.retrieve_only is False


def test_ask_offers_no_mode_whose_result_is_not_an_answer() -> None:
    """`R22.6`: `Weft.ask` exposes no `retrieve_only` flag, since it could only ever raise.

    `R22.6`: retrieve-only fills `hits` and never `answer`, so `ask(retrieve_only=True)` raised
    on every call. Ranked passages are `run("ask", {...})`'s to return.
    """
    # Arrange
    offered = inspect.signature(Weft.ask).parameters

    # Act
    names = set(offered)

    # Assert
    assert "retrieve_only" not in names
    assert {"question", "pipeline", "top_k", "token_sink"} <= names


async def test_ask_raises_when_the_command_did_not_produce_rather_than_answering_none() -> None:
    # Arrange
    weft = Weft(_deps(_RefusingCommand))

    # Act / Assert — `WeftError` itself, not a new class: the task line settles that no
    # exception type is invented here, and `09` §3's envelope already names this root.
    with pytest.raises(WeftError) as excinfo:
        async with weft as w:
            await w.ask("what changed?")

    # Assert — the message carries the stage's own reason, not a generic failure.
    assert "the corpus holds nothing on that subject" in str(excinfo.value)


async def test_ask_refuses_a_name_the_registry_does_not_hold_and_says_what_it_does() -> None:
    """Requirement 5 through the library boundary, with no new exception type invented.

    `weft_kernel.registry.UnknownPluginError` is what the CLI already raises and prints; an
    application catches the same class and reads the same `valid_options`.
    """
    # Arrange — a registry holding a command under some *other* name.
    weft = Weft(_deps(_RecordingCommand, name="summarise"))

    # Act / Assert
    with pytest.raises(UnknownPluginError) as excinfo:
        async with weft as w:
            await w.ask("what changed?")

    assert "ask" in str(excinfo.value)
    assert excinfo.value.valid_options == ("summarise",)


async def test_a_destroy_class_command_the_caller_did_not_authorise_is_refused() -> None:
    """No TTY exists behind a library call, so an unauthorised destructive run refuses loudly.

    The alternative — permitting it because nobody was there to say no — is the silent
    escalation `03` → *Permissions* exists to prevent, and the refusal names the parameter that
    would have permitted it rather than naming `--yes`, which an application cannot pass.
    """
    # Arrange
    weft = Weft(_deps(_DestructiveCommand, name="delete"))

    # Act / Assert
    with pytest.raises(CommandRefusalError) as excinfo:
        async with weft as w:
            await w.delete(SourceId("note.txt"))

    assert "yes=True" in str(excinfo.value)
    assert _DestructiveCommand.calls == []


async def test_a_destroy_class_command_the_caller_authorised_runs() -> None:
    # Arrange
    weft = Weft(_deps(_DestructiveCommand, name="delete"))

    # Act
    async with weft as w:
        await w.delete(SourceId("note.txt"), yes=True)

    # Assert
    assert len(_DestructiveCommand.calls) == 1


async def test_a_permissions_table_that_allows_destroy_permits_it_without_the_argument() -> None:
    """`[permissions] destroy = "allow"` is honoured by the library exactly as by the CLI.

    `[permissions] destroy = "allow"` is the operator's standing answer, and the library
    honours the same table the CLI does — one policy, read once, not a second one here.
    """
    # Arrange
    policy = PermissionPolicy(destroy=PermissionAction.ALLOW)
    weft = Weft(_deps(_DestructiveCommand, name="delete", permissions=policy))

    # Act
    async with weft as w:
        await w.delete(SourceId("note.txt"))

    # Assert
    assert len(_DestructiveCommand.calls) == 1


async def test_the_block_exiting_on_an_exception_does_not_replace_it() -> None:
    """Carried repair `R18.1`, discharged where the `async with` exit is first written.

    `Runner._flush_all` already refuses to let a cleanup failure displace the exception already
    propagating, because *"raising here would replace it"* — and a `CancelledError` turned into
    a `WeftError` is a cancelled task that merely raised. `__aexit__` is the first place in this
    tree where a caller's own block and a close can fail together, so it is where the rule lands.
    """

    # Arrange — something the session holds that refuses to be released.
    class _WillNotClose:
        async def aclose(self) -> None:
            raise RuntimeError("the pool would not drain")

    weft = Weft(_deps(_RecordingCommand))
    weft.hold(_WillNotClose(), distribution="acme-store", contract="NodeStore", plugin="acme")

    # Act / Assert — the caller's exception reaches the caller, unchanged.
    with pytest.raises(ZeroDivisionError):
        async with weft:
            raise ZeroDivisionError("the application's own bug")


async def test_what_the_session_holds_is_closed_when_the_block_exits() -> None:
    """The other half of the same exit, and the one `24.4` measures against a real database."""

    # Arrange
    class _Closes:
        def __init__(self) -> None:
            self.closes = 0

        async def aclose(self) -> None:
            self.closes += 1

    held = _Closes()
    weft = Weft(_deps(_RecordingCommand))
    weft.hold(held, distribution="weft-store", contract="NodeStore", plugin="pgvector")

    # Act
    async with weft as w:
        await w.ask("what changed?")

    # Assert — closed once. Closing twice is as wrong as not closing at all.
    assert held.closes == 1


async def test_open_reads_the_config_path_it_is_given(tmp_path: Path) -> None:
    """`Weft.open` is `build_dependencies` and nothing else — the same assembly the CLI runs.

    A second assembly here would be the phase's named hazard, so this asserts the file was read
    rather than asserting anything about what was built from it: a `weft.toml` naming a pack
    setting reaches `Dependencies.reports` through discovery, exactly as it does for `weft ask`.
    """
    # Arrange
    config = tmp_path / "weft.toml"
    config.write_text('[packs.store]\ndsn = "postgresql://nobody@localhost:1/none"\n')

    # Act
    async with Weft.open(config) as w:
        reports = w.dependencies.reports

    # Assert — discovery ran against the real installed set, which is what the CLI gets too.
    assert any(report.pack == "store" for report in reports)


async def test_any_registered_command_is_reachable_by_name_not_only_the_three_with_methods() -> (
    None
):
    """Requirement 4, found by `weft-qualities` at the phase close and not by any test.

    Measured: a real `build_dependencies()` registers **24** `Command`s — `graph show`, `agent`,
    `eval run`, `pipeline derive` and twenty more — and `weft_cli.cli.run_command` dispatches
    every one of them generically, by name, from the same registry. `Weft` shipped `ask`, `index`
    and `delete` and kept the generic call private, so a pack's contributed command was reachable
    from the terminal and not from the library. That is precisely the privileged path this phase
    exists to close, inverted: the *built-in adapter* had the general mechanism and the public
    verb had three special cases.

    `ask`/`index`/`delete` stay, because a named method is a better thing to write than a string
    for the three commands every application uses. They are wrappers over this.
    """
    # Arrange — a command no method on `Weft` is named after, which is every pack's case.
    weft = Weft(_deps(_RecordingCommand, name="graph show"))

    # Act
    async with weft as w:
        result = await w.run("graph show", {"question": "which entities bridge?"})

    # Assert
    assert len(_RecordingCommand.calls) == 1
    recorded = _RecordingCommand.calls[0]
    assert isinstance(recorded, _AskArgs)
    assert recorded.question == "which entities bridge?"
    assert isinstance(result, _AskResult)


async def test_run_asks_consent_for_a_destructive_command_reached_by_name() -> None:
    """The generic path is gated exactly as the three named ones are.

    A command reached by string must not be a way around the permission the same command refuses by
    method.
    """
    # Arrange
    weft = Weft(_deps(_DestructiveCommand, name="graph wipe"))

    # Act / Assert
    with pytest.raises(CommandRefusalError):
        async with weft as w:
            await w.run("graph wipe", {"source_id": "doc-1"})

    assert _DestructiveCommand.calls == []


# --- Repair `R22.5` — a token sink belongs to a call, not only to a session.
#
# G23's measurement (`05` → G23, *"The measurement the gate owed"*): `Weft._invoke` built every
# call's services with the session's own sink, and `TokenChunk` carries no run id, so two
# concurrent `ask`s on one `Weft` interleaved into one sink with nothing to separate them.


class _RecordingSink:
    """A `TokenSink` that keeps every chunk it was given, in order, and every close."""

    def __init__(self) -> None:
        self.chunks: list[TokenChunk] = []
        self.closed_with: list[str | None] = []

    async def emit(self, chunk: TokenChunk) -> None:
        self.chunks.append(chunk)

    async def close(self, *, reason: str | None = None) -> None:
        self.closed_with.append(reason)


class _StreamingCommand(_RecordingCommand):
    """Lets a test prove two concurrent calls on one `Weft` really interleave their streams.

    Streams three chunks through `ctx.require(TokenSink)` and yields between each, so two
    concurrent calls interleave the way two generations on one event loop do. `emitted` records
    the order across both calls, which is what shows the interleaving happened at all.
    """

    emitted: ClassVar[list[str]] = []

    async def run(self, args: BaseModel, ctx: Context) -> Outcome[CommandResult]:
        assert isinstance(args, _AskArgs)
        sink = ctx.require(TokenSink)
        for index in range(3):
            text = f"{args.question}:{index}"
            type(self).emitted.append(text)
            await sink.emit(TokenChunk(role="generate", text=text))
            await asyncio.sleep(0)
        return Produced(value=_AskResult(question=args.question, answer=_an_answer()))


class _StreamThenFailCommand(_RecordingCommand):
    """Streams one chunk, then answers `Failed` — a model stopping mid-answer."""

    emitted: ClassVar[list[str]] = []

    async def run(self, args: BaseModel, ctx: Context) -> Outcome[CommandResult]:
        assert isinstance(args, _AskArgs)
        type(self).emitted.append(args.question)
        await ctx.require(TokenSink).emit(TokenChunk(role="generate", text=f"{args.question}:0"))
        return Failed(reason="the model stopped mid-answer")


def _session(command: type[_RecordingCommand], sink: _RecordingSink, *, name: str = "ask") -> Weft:
    registry = Registry()
    registry.add(Command, name, command, distribution="weft-rag")
    return Weft(
        Dependencies(registry=registry, reports=(), services=ServiceSelection(), token_sink=sink)
    )


async def test_two_concurrent_asks_on_one_session_stream_into_the_sinks_each_was_given() -> None:
    # Arrange
    session_sink, alpha_sink, beta_sink = _RecordingSink(), _RecordingSink(), _RecordingSink()
    weft = _session(_StreamingCommand, session_sink)

    # Act
    async with weft as w:
        await asyncio.gather(
            w.ask("alpha", token_sink=alpha_sink), w.ask("beta", token_sink=beta_sink)
        )

    # Assert
    assert _StreamingCommand.emitted[:2] == ["alpha:0", "beta:0"]
    assert [chunk.text for chunk in alpha_sink.chunks] == ["alpha:0", "alpha:1", "alpha:2"]
    assert [chunk.text for chunk in beta_sink.chunks] == ["beta:0", "beta:1", "beta:2"]
    assert session_sink.chunks == []


async def test_a_call_given_no_sink_streams_into_the_sessions_own() -> None:
    # Arrange
    session_sink = _RecordingSink()
    weft = _session(_StreamingCommand, session_sink)

    # Act
    async with weft as w:
        await w.ask("alpha")
        closed_during_the_session = list(session_sink.closed_with)

    # Assert
    assert [chunk.text for chunk in session_sink.chunks] == ["alpha:0", "alpha:1", "alpha:2"]
    assert closed_during_the_session == []


async def test_a_call_closes_the_sink_it_was_given_once_when_it_ends() -> None:
    # Arrange
    call_sink = _RecordingSink()
    weft = _session(_StreamingCommand, _RecordingSink())

    # Act
    async with weft as w:
        await w.ask("alpha", token_sink=call_sink)
        closed_before_the_block_exits = list(call_sink.closed_with)

    # Assert
    assert closed_before_the_block_exits == [None]
    assert call_sink.closed_with == [None]


async def test_a_call_that_fails_closes_its_sink_saying_why_and_still_raises() -> None:
    # Arrange
    call_sink = _RecordingSink()
    weft = _session(_StreamThenFailCommand, _RecordingSink())

    # Act
    with pytest.raises(WeftError) as caught:
        async with weft as w:
            await w.ask("alpha", token_sink=call_sink)

    # Assert
    assert "the model stopped mid-answer" in str(caught.value)
    assert [chunk.text for chunk in call_sink.chunks] == ["alpha:0"]
    assert len(call_sink.closed_with) == 1
    reason = call_sink.closed_with[0]
    assert reason is not None
    assert "the model stopped mid-answer" in reason


async def test_a_command_reached_by_name_takes_a_sink_for_the_call_too() -> None:
    # Arrange
    session_sink, call_sink = _RecordingSink(), _RecordingSink()
    weft = _session(_StreamingCommand, session_sink, name="graph show")

    # Act
    async with weft as w:
        await w.run("graph show", {"question": "alpha"}, token_sink=call_sink)

    # Assert
    assert [chunk.text for chunk in call_sink.chunks] == ["alpha:0", "alpha:1", "alpha:2"]
    assert call_sink.closed_with == [None]
    assert session_sink.chunks == []


class _IndexCommand(_RecordingCommand):
    """Keeps `Weft.index`'s argument tests honest about what the real `IndexArgs` accepts.

    Declares the shipped `IndexArgs`, so a field `Weft.index` passes that the real model does
    not declare is dropped here exactly as it is in production (`L12.11`).
    """

    calls: ClassVar[list[BaseModel]] = []
    args_model: ClassVar[type[BaseModel]] = IndexArgs
    permission_class: ClassVar[PermissionClass] = PermissionClass.WRITE

    async def run(self, args: BaseModel, ctx: Context) -> Outcome[CommandResult]:
        del ctx
        type(self).calls.append(args)
        return Produced(value=_AskResult(question="indexed"))


async def test_index_can_ask_for_failed_sources_to_be_retried(tmp_path: Path) -> None:
    """`R36.4`: `weft index --retry-failed` had no counterpart on the embedded verb."""
    # Arrange
    weft = Weft(_deps(_IndexCommand, name="index"))

    # Act
    await weft.index(tmp_path, retry_failed=True)

    # Assert
    recorded = _IndexCommand.calls[-1]
    assert isinstance(recorded, IndexArgs)
    assert recorded.retry_failed is True


async def test_index_can_name_its_layers_and_run_only_them(tmp_path: Path) -> None:
    """Ledger **43.8**: `Weft.index` takes `layers` and `layers_only`, as `weft index` does."""
    # Arrange
    weft = Weft(_deps(_IndexCommand, name="index"))

    # Act
    await weft.index(tmp_path, layers=("enrich-with-questions", "enrich-with-facts"))
    named = _IndexCommand.calls[-1]
    await weft.index(tmp_path, layers=(), layers_only=False)
    none = _IndexCommand.calls[-1]
    await weft.index(tmp_path, layers_only=True)
    only = _IndexCommand.calls[-1]

    # Assert
    assert isinstance(named, IndexArgs)
    assert named.layers == "enrich-with-questions,enrich-with-facts"
    assert isinstance(none, IndexArgs)
    assert none.layers == "none"
    assert isinstance(only, IndexArgs)
    assert (only.layers, only.layers_only) == (None, True)
