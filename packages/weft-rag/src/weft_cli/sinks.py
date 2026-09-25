"""The CLI's own `TokenSink` implementations — `docs/03-cli.md` -> *Output* (G6).

Task **3.6**: "the CLI registers a `TokenSink` implementation, and the generating stage
resolves it through the passport and emits into it." `weft_llm.contract.TokenSink` and
`weft_llm.client.LLMClient.complete` (which already resolves the sink with `ctx.require`
and emits every chunk as it arrives) shipped in Phase 2; `weft_llm.client.NullSink` — the
discard-everything default — shipped with them. What was missing is a sink that puts
tokens somewhere a reader can actually see, and the two others `--json`/`--quiet` need.
Neither belongs in `weft-llm`: a provider's own pack has no reason to know what a
terminal, a JSON consumer or `--quiet` even are — those are CLI concerns, and `weft-llm`
already ships the one sink with nothing to display (`NullSink`), which is what `--quiet`
still uses, unchanged, rather than a second do-nothing class duplicating it here.

**Filtering is shared, not duplicated per sink.** `weft_llm.payload.TokenChunk`'s own
docstring states the rule both sinks below hold: "the CLI's sink display only the roles
in its display set (default `{"generate"}`), so a critic's or a grader's internal call
never pollutes what a reader sees. Filtering at the sink rather than at the emit site is
... a call site that has to remember to stay quiet eventually forgets." `_visible` is the
one place that rule is applied; a role outside `display_roles` is emitted into neither
sink's stream and does not advance `PrintingSink`'s own "has anything printed yet" state.

**The event vocabulary, and why it is three members, not seven.**
`.phase3-design.md` §2.3 reads a comparable `StreamEventType` taxonomy as knowledge worth
keeping — `TOKEN`, `CITATIONS`, `SOURCES`, `STATUS`, `DONE`,
`ERROR`, `GUARDRAIL_WARNING`, one envelope carrying whichever fields the type needs — and
names the real ordering it encodes: `STATUS` interleaves with `TOKEN`, and a terminal
`DONE` or `ERROR` closes the stream. `StreamEvent` below is that shape, rebuilt fresh for
what this sink actually has to emit today: `CHUNK` (every `TokenChunk` this sink sees —
named for the payload it carries rather than `TOKEN`, since Weft already has a
type called `TokenChunk` and a member literally named `TOKEN` reads, to a linter and a
human alike, like the start of "access token" rather than "one piece of a streamed
answer") and `DONE`/`ERROR` (`close`'s own `reason`). `CITATIONS`/`SOURCES` would need
`weft_generate.payload.Answer.citations` threaded into something that today only ever
sees a `TokenChunk`; `STATUS` would need a routing-progress signal nothing in
`weft-retrieve` emits; `GUARDRAIL_WARNING` has no guardrail plugin anywhere in this tree.
Each is a real, named gap for whichever future task builds the thing that would emit it —
not invented ahead of a need, the identical discipline `weft_llm.payload.OnFailure`'s own
docstring states for itself: "not a promise that every enum ships with two members on day
one."

**An error can never be mistaken for a clean end.** `.phase3-design.md` §2.3, correction
(b): logging an exception and yielding a plain `ERROR` *event* a consumer that does not
branch on `type` cannot tell apart from a normal `DONE` is exactly the failure mode this
sink exists to refuse. `TokenSink.close`'s own `reason: str | None`
parameter is the mechanism that makes the two structurally different here rather than
textually similar: `close(reason=None)` is the only call that produces a `DONE` event,
and any other call — `reason` carrying the caught error's own message — produces an
`ERROR` event instead, naming it. `weft_cli.cli.run_command` is what decides which one to
call and with what reason; see that function's own docstring.
"""

from __future__ import annotations

import contextlib
import sys
from collections.abc import Set
from enum import StrEnum
from typing import IO, TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

from weft_llm.payload import TokenChunk

if TYPE_CHECKING:
    # Not imported at runtime: `weft_cli.progress` imports `LineKind` from this module, and a
    # real import back here would be the cycle. Every use below is attribute access, which
    # `from __future__ import annotations` already lets stay a deferred string.
    from weft_cli.progress import BatchProgress

#: `weft_llm.payload.TokenChunk`'s own documented default — a critic's or a grader's own
#: role never reaches a reader unless a caller widens this explicitly.
DEFAULT_DISPLAY_ROLES: frozenset[str] = frozenset({"generate"})


class StreamEventType(StrEnum):
    """Lets a script tell a finished stream from a broken one without parsing prose.

    One line's shape in `--json`'s newline-delimited event stream — see the module
    docstring's own paragraph on why this is three members, not seven.
    """

    CHUNK = "chunk"
    DONE = "done"
    ERROR = "error"


class LineKind(StrEnum):
    """Which **shape** a line on the `--json` stream is — ledger task **6.16**.

    `docs/internal/lessons.md` L5.16: a newline-delimited stream carrying two shapes needs a
    discriminant. `weft --json ask` writes `StreamEvent` lines while a pipeline runs and an
    `ErrorEnvelope` when the run refuses, on the same descriptor, and before this a consumer told
    them apart by sniffing for keys. The ambiguous pair is not hypothetical: a `StreamEvent` whose
    `type` is `ERROR` and an `ErrorEnvelope` are **both** "an error", in different shapes, so
    key-sniffing had to get exactly that case right to be correct at all.

    **`kind` is a second key rather than a widening of `type`.** `StreamEventType` answers *which
    event*; this answers *which line shape*. One key answering both would be the "one word
    answering two questions" `09` §3 refuses for the status vocabulary, one surface over — and it
    would make `type: "error"` mean two unrelated things depending on the other keys present,
    which is the state this task exists to end.

    **Additive, which is what makes it permissible.** `09` §3 promises the machine-readable output
    *additively*: new fields may be added and a consumer ignores what it does not recognise.
    Nothing existing changes name or meaning.
    """

    STREAM_EVENT = "stream-event"
    ERROR_ENVELOPE = "error-envelope"
    #: Carried repair **R9.2**. The third shape on this descriptor: what a routed `weft ask`
    #: produced, once `weft_cli.render._render_ask` stopped printing it as prose under the
    #: global `--json`. It joins the vocabulary rather than arriving beside it, for the reason
    #: this enum exists — a consumer reads `kind`, never which keys happen to be set.
    ANSWER_ENVELOPE = "answer-envelope"
    #: Ledger task **43.2** — one `weft index` batch's own progress. Joins the vocabulary
    #: additively, on the same footing `ANSWER_ENVELOPE` did.
    BATCH_PROGRESS = "batch-progress"


class StreamEvent(BaseModel):
    """One line of `--json`'s event stream.

    One envelope, whichever fields `type` needs — a taxonomy read at `.phase3-design.md` §2.3 and
    rebuilt here for what this sink actually emits.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: Which line shape this is — task **6.16**. Constant per class and dumped on every line, so
    #: a consumer reads one key rather than inferring from which other keys happen to be set.
    kind: LineKind = LineKind.STREAM_EVENT
    type: StreamEventType
    #: Set only on a `CHUNK` event — the role `TokenChunk.role` carried.
    role: str = ""
    #: Set only on a `CHUNK` event — the chunk's own text.
    text: str = ""
    #: Set only on an `ERROR` event — `TokenSink.close`'s own `reason`.
    message: str = ""


def _visible(chunk: TokenChunk, display_roles: Set[str], display_stage: str | None) -> bool:
    """Whether `chunk` reaches a reader at all — see the module docstring's filtering rule.

    **Two independent filters since carried repair `R10.1`.** The role filter is unchanged: a
    critic's or a grader's own role never reaches a reader. The stage filter is the new one, and
    it exists because a role names a *model mapping* — so two stages calling a model on the
    answering role are indistinguishable to a role filter, and the first pipeline to do that
    concurrently printed its intermediate summaries interleaved with the answer.

    `display_stage` is `None` until something tells the sink which stage produces the answer,
    and `None` shows every stage. That is the honest default rather than a lax one: the sink is
    built in `weft_cli.cli.main` before any pipeline is resolved, so at construction it does not
    know, and filtering on a stage nobody named would suppress every chunk in the tree.

    A chunk whose own `stage` is `""` is shown too. Empty means *nothing was in scope to stamp
    it* — a provider called outside a wrapped stage — and reading that as "some other stage"
    would swallow the only output such a caller produces. `TokenChunk.stage` carries the same
    convention at the other end.
    """
    if chunk.role not in display_roles:
        return False
    return display_stage is None or chunk.stage in {"", display_stage}


class ReaderGoneError(BrokenPipeError):
    """A sink's reader closed its end of the pipe while the command was still producing — R38.15.

    Raised by `emit` alone, so `weft_cli.cli` can stop the command quietly on exactly this and
    still report a `BrokenPipeError` from a socket, which is the same class and a real failure.
    """


class PrintingSink:
    """Makes a streamed answer appear on the terminal as live, growing prose.

    Writes a chunk's text to `stream` the instant it arrives — the default sink, the one
    a human reads. Satisfies `weft_llm.contract.TokenSink` structurally, the same path
    every plugin in this tree takes with its own contract.

    `stream` is constructor-injected (default `sys.stdout`) on the identical convention
    `weft_cli.repl.read_line` documents for itself: a test drives this against a captured
    stream, never the real terminal CI never has. Every `write` is followed by an
    unbuffered `flush` — "as they arrive" is a promise about when a reader can see a
    token, and Python's own text-stream buffering would otherwise hold it back until a
    buffer boundary or program exit, silently turning "as they arrive" into "eventually".

    **`close` ends the line, and marks an error distinctly.** Tokens are written with no
    trailing newline between them (that is what makes the terminal show one continuous,
    growing line of prose, the "live typing" a streamed answer is meant to look like);
    `close` writes exactly one newline if any token was actually shown, so whatever a
    caller prints next (citations, the next REPL prompt) starts on its own line. A `reason`
    is not silently absorbed into that same newline: it is a visibly distinct
    `[stream error: ...]` line, so a human reading a scrollback cannot mistake a stream
    that broke for one that simply finished — the same "never mistakable" property
    `StreamEvent`'s `ERROR`/`DONE` split gives a script.

    **`wrote_anything`, made public by task 3.11.** Previously a private bookkeeping flag
    `close` alone read; `weft_cli.cli.run_command` now reads it too, off the real sink
    (never the `_EmissionTrackingSink` wrapper, which is role-blind by design — see that
    class's own docstring), to decide whether `weft_cli.render._render_ask` may skip
    re-printing a routed `Answer.text` that this sink already streamed live. `docs/build-
    ledger.md`'s 3.11 entry has the fix in full, including why `_EmissionTrackingSink`'s own
    `.emitted` is the wrong fact for this: it is set by *any* role's chunk (the router's own
    `role="route"` scoring call included), where this flag is set only for a chunk `_visible`
    already decided a reader would actually see.
    """

    def __init__(
        self,
        *,
        stream: IO[str] | None = None,
        display_roles: Set[str] = DEFAULT_DISPLAY_ROLES,
        progress_stream: IO[str] | None = None,
    ) -> None:
        self._stream: IO[str] = stream if stream is not None else sys.stdout
        self._display_roles = display_roles
        self._display_stage: str | None = None
        self.wrote_anything = False
        self._progress_stream: IO[str] = (
            progress_stream if progress_stream is not None else sys.stderr
        )

    def show_only_stage(self, stage: str) -> None:
        """Show chunks from `stage` alone (plus unstamped ones) — carried repair **R10.1**.

        A *setter* rather than a constructor argument, because the answer's stage is not known
        when the sink is built: `weft_cli.cli.main` chooses the sink from the global flags before
        `build_dependencies` runs, and which stage ends the pipeline is decided later, by
        whichever of the router or `--pipeline` picked one. Whoever resolves the pipeline tells
        the sink; until then it shows everything, exactly as it always did.

        Reached through `getattr` by its one caller rather than added to `weft_llm.contract.
        TokenSink`: adding a method to a published contract breaks every implementation at once
        (`09` §3, G9's *Bring* list), and this is a convenience the CLI's own two sinks offer,
        not a promise every sink must keep. `weft_kernel.runner._flush_of`'s defensive
        duck-typing is the same idiom, for the same reason.
        """
        self._display_stage = stage

    async def emit(self, chunk: TokenChunk) -> None:
        """Write `chunk`'s text and flush it, when this sink shows its role and stage.

        Args:
            chunk: The streamed token chunk.

        Raises:
            ReaderGoneError: The reader closed the stream.
        """
        if not _visible(chunk, self._display_roles, self._display_stage):
            return
        try:
            self._write_now(chunk.text)
        except BrokenPipeError as exc:
            raise ReaderGoneError(*exc.args) from exc
        self.wrote_anything = True

    async def close(self, *, reason: str | None = None) -> None:
        """End the streamed line, and mark a stream that broke with its own line.

        Args:
            reason: Why the stream did not complete, or `None` when it did.
        """
        with contextlib.suppress(BrokenPipeError):
            # The marker ends a line the reader watched grow; after hidden chunks alone there is
            # no such line, and the refusal on stderr is the one account (task 43.36).
            if self.wrote_anything:
                self._stream.write("\n")
                if reason is not None:
                    self._stream.write(f"[stream error: {reason}]\n")
            self._stream.flush()

    def _write_now(self, text: str) -> None:
        self._stream.write(text)
        self._stream.flush()

    async def batch_progress(self, event: BatchProgress) -> None:
        """One line to `progress_stream` per `weft index` batch — ledger task **43.2**.

        Names the stage that kept the corpus whole when `event.whole_corpus_for` is
        non-empty, rather than the batch fraction: a run that never split is not a batch
        count a reader should be tracking, it is a fact about one stage in the pipeline.

        Ends with the batch's own size in MB — ledger task **43.1** — when `event.bytes` is
        known, so one huge document is visible as the cause of a slow batch; unchanged when
        it is `0`, which `43.2`'s own tests pin.

        `event.layer` — ledger task **43.8** — names its own line, distinct from the base's:
        a layer batch counts sources, never documents queryable, and carries no
        `whole_corpus_for`/`bytes` of its own to report.
        """
        if event.layer is not None:
            line = (
                f"layer {event.layer} · batch {event.batch}/{event.batches} · "
                f"{event.queryable}/{event.documents} sources · {event.seconds:.1f} s since start"
            )
            self._progress_stream.write(f"{line}\n")
            self._progress_stream.flush()
            return
        if event.whole_corpus_for:
            names = ", ".join(event.whole_corpus_for)
            head = f"one batch: '{names}' computes over the whole corpus"
        else:
            head = f"batch {event.batch}/{event.batches}"
        line = (
            f"{head} · {event.queryable}/{event.documents} documents queryable · "
            f"{event.seconds:.1f} s since start"
        )
        if event.bytes:
            line += f" · {event.bytes / 1_000_000:.1f} MB"
        self._progress_stream.write(f"{line}\n")
        self._progress_stream.flush()


class JsonSink:
    """One `StreamEvent`, as one line of JSON, per `emit`/`close` call — `--json`'s sink.

    Satisfies `weft_llm.contract.TokenSink` structurally, on the identical footing
    `PrintingSink` does. `stream` is constructor-injected on the same convention, for the
    same reason — a test asserts against a captured stream, never stdout.

    Every event is `model_dump_json()`'d and written with a trailing newline — newline-
    *delimited*, `docs/03-cli.md` -> *Output*'s own spelling, so a reader can parse one
    line at a time without buffering the whole stream first. `ensure_ascii` is pydantic's
    own default here and left alone deliberately, the opposite choice from
    `weft_cli.ask.render_results_json`'s own reasoning for turning it off: that function
    echoes a stored passage's exact characters back to a caller comparing them against the
    corpus, where an escaped rendering would be a different string; a token sink emits
    live model output with no such round-trip promise to keep, so there is nothing here
    that this choice could silently change the meaning of.

    **`wrote_anything`, task 3.11 — `PrintingSink`'s own new flag, mirrored here.** Set only
    for a chunk `_visible` already decided belongs in the event stream, so `--json`, too, can
    tell `weft_cli.render._render_ask` whether a routed `Answer.text` already reached this
    sink as `CHUNK` events before `_render_ask` decides whether to print it again as trailing
    prose.
    """

    def __init__(
        self, *, stream: IO[str] | None = None, display_roles: Set[str] = DEFAULT_DISPLAY_ROLES
    ) -> None:
        self._stream: IO[str] = stream if stream is not None else sys.stdout
        self._display_roles = display_roles
        self._display_stage: str | None = None
        self.wrote_anything = False

    def show_only_stage(self, stage: str) -> None:
        """Show chunks from `stage` alone (plus unstamped ones) — carried repair **R10.1**.

        A *setter* rather than a constructor argument, because the answer's stage is not known
        when the sink is built: `weft_cli.cli.main` chooses the sink from the global flags before
        `build_dependencies` runs, and which stage ends the pipeline is decided later, by
        whichever of the router or `--pipeline` picked one. Whoever resolves the pipeline tells
        the sink; until then it shows everything, exactly as it always did.

        Reached through `getattr` by its one caller rather than added to `weft_llm.contract.
        TokenSink`: adding a method to a published contract breaks every implementation at once
        (`09` §3, G9's *Bring* list), and this is a convenience the CLI's own two sinks offer,
        not a promise every sink must keep. `weft_kernel.runner._flush_of`'s defensive
        duck-typing is the same idiom, for the same reason.
        """
        self._display_stage = stage

    async def emit(self, chunk: TokenChunk) -> None:
        """Write `chunk` as one `chunk` event line, when this sink shows its role and stage.

        Args:
            chunk: The streamed token chunk.

        Raises:
            ReaderGoneError: The reader closed the stream.
        """
        if not _visible(chunk, self._display_roles, self._display_stage):
            return
        self.wrote_anything = True
        try:
            self._write(StreamEvent(type=StreamEventType.CHUNK, role=chunk.role, text=chunk.text))
        except BrokenPipeError as exc:
            raise ReaderGoneError(*exc.args) from exc

    async def close(self, *, reason: str | None = None) -> None:
        """End the stream with one `done` event, or an `error` event carrying `reason`.

        Args:
            reason: Why the stream did not complete, or `None` when it did.
        """
        event = (
            StreamEvent(type=StreamEventType.DONE)
            if reason is None
            else StreamEvent(type=StreamEventType.ERROR, message=reason)
        )
        with contextlib.suppress(BrokenPipeError):
            self._write(event)

    async def batch_progress(self, event: BatchProgress) -> None:
        """One `batch-progress` line per `weft index` batch — ledger task **43.2**.

        `event.model_dump_json()` directly, not wrapped in a `StreamEvent`: `BatchProgress`
        already carries its own `kind` discriminant, so a second envelope around it would
        only duplicate that field under a different name.
        """
        self._stream.write(f"{event.model_dump_json()}\n")
        self._stream.flush()

    def _write(self, event: StreamEvent) -> None:
        # One `write` call per event, not two — a reader watching the stream should see one
        # arrival per event, and a test timing "as they arrive" should not have to skip a
        # second, same-instant write for the trailing newline.
        self._stream.write(f"{event.model_dump_json()}\n")
        self._stream.flush()


__all__ = [
    "DEFAULT_DISPLAY_ROLES",
    "JsonSink",
    "PrintingSink",
    "ReaderGoneError",
    "StreamEvent",
    "StreamEventType",
]
