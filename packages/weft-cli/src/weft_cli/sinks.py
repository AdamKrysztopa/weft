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

**The event vocabulary, and why it is three members, not the reference's seven.**
`.phase3-design.md` §2.3 reads `core/engine/types.py:85-96`'s `StreamEventType` as a
taxonomy worth having as knowledge — `TOKEN`, `CITATIONS`, `SOURCES`, `STATUS`, `DONE`,
`ERROR`, `GUARDRAIL_WARNING`, one envelope carrying whichever fields the type needs — and
names the real ordering it encodes: `STATUS` interleaves with `TOKEN`, and a terminal
`DONE` or `ERROR` closes the stream. `StreamEvent` below is that shape, rebuilt fresh for
what this sink actually has to emit today: `CHUNK` (every `TokenChunk` this sink sees —
named for the payload it carries rather than the reference's `TOKEN`, since Weft already has a
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

**An error can never be mistaken for a clean end — the reference correction this sink exists
to not reproduce.** `.phase3-design.md` §2.3, correction (b): the reference's engine catches an
exception, logs it, and yields a plain `ERROR` *event* a consumer that does not branch on
`type` cannot tell apart from a normal `DONE`. `TokenSink.close`'s own `reason: str | None`
parameter is the mechanism that makes the two structurally different here rather than
textually similar: `close(reason=None)` is the only call that produces a `DONE` event,
and any other call — `reason` carrying the caught error's own message — produces an
`ERROR` event instead, naming it. `weft_cli.cli.run_command` is what decides which one to
call and with what reason; see that function's own docstring.
"""

from __future__ import annotations

import sys
from collections.abc import Set
from enum import StrEnum
from typing import IO

from pydantic import BaseModel, ConfigDict

from weft_llm.payload import TokenChunk

#: `weft_llm.payload.TokenChunk`'s own documented default — a critic's or a grader's own
#: role never reaches a reader unless a caller widens this explicitly.
DEFAULT_DISPLAY_ROLES: frozenset[str] = frozenset({"generate"})


class StreamEventType(StrEnum):
    """One line's shape in `--json`'s newline-delimited event stream — see the module
    docstring's own paragraph on why this is three members, not the reference's seven.
    """

    CHUNK = "chunk"
    DONE = "done"
    ERROR = "error"


class StreamEvent(BaseModel):
    """One line of `--json`'s event stream. One envelope, whichever fields `type` needs —
    the reference's own shape (`core/engine/types.py:175-200`), read as a taxonomy at
    `.phase3-design.md` §2.3 and rebuilt here for what this sink actually emits.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    type: StreamEventType
    #: Set only on a `CHUNK` event — the role `TokenChunk.role` carried.
    role: str = ""
    #: Set only on a `CHUNK` event — the chunk's own text.
    text: str = ""
    #: Set only on an `ERROR` event — `TokenSink.close`'s own `reason`.
    message: str = ""


def _visible(chunk: TokenChunk, display_roles: Set[str]) -> bool:
    """Whether `chunk` reaches a reader at all — see the module docstring's filtering rule."""
    return chunk.role in display_roles


class PrintingSink:
    """Writes a chunk's text to `stream` the instant it arrives — the default sink, the one
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
        self, *, stream: IO[str] | None = None, display_roles: Set[str] = DEFAULT_DISPLAY_ROLES
    ) -> None:
        self._stream: IO[str] = stream if stream is not None else sys.stdout
        self._display_roles = display_roles
        self.wrote_anything = False

    async def emit(self, chunk: TokenChunk) -> None:
        if not _visible(chunk, self._display_roles):
            return
        self._stream.write(chunk.text)
        self._stream.flush()
        self.wrote_anything = True

    async def close(self, *, reason: str | None = None) -> None:
        if self.wrote_anything:
            self._stream.write("\n")
        if reason is not None:
            self._stream.write(f"[stream error: {reason}]\n")
        self._stream.flush()


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
        self.wrote_anything = False

    async def emit(self, chunk: TokenChunk) -> None:
        if not _visible(chunk, self._display_roles):
            return
        self.wrote_anything = True
        self._write(StreamEvent(type=StreamEventType.CHUNK, role=chunk.role, text=chunk.text))

    async def close(self, *, reason: str | None = None) -> None:
        if reason is None:
            self._write(StreamEvent(type=StreamEventType.DONE))
        else:
            self._write(StreamEvent(type=StreamEventType.ERROR, message=reason))

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
    "StreamEvent",
    "StreamEventType",
]
