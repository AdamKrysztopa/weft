"""What a routed `weft ask` produced, for a script — carried repair **R9.2**.

`weft_cli.error_envelope` is this module's own precedent and its argument applies unchanged one
path over. G9 made CLI *prose* unpromised in exchange for a structured channel, and Phase 5 built
that channel for the failure path only: `render_refusal(exc, as_json=...)` emits an
`ErrorEnvelope`, while a **successful** routed answer went on printing `routed to: <name>` and a
line per citation as prose — under the global `--json` too, after the event stream had already
closed. `docs/03-cli.md` -> *Output* is unambiguous about what that costs: "`--json` switches to
newline-delimited JSON events and disables every decoration... That is the scripting contract:
same events, no parsing of prose."

**Confirmed live at ledger task 10.16, from outside this repository**, which is how it was
found rather than by any of the 2,501 tests: `weft --json ask "..." --pipeline
raptor-and-leaves-rrf` emitted well-formed stream events and then five lines of prose on stdout,
so nothing downstream could parse that output at all.

**What travels, and why exactly this.** The envelope carries what the prose carried and nothing
more — `pipeline_name` (the router's choice or the name `--pipeline` gave), `text`, and
`citations`. Widening it to `Answer.used`, `stance` or the retrieval ranking would be this repair
deciding what a machine reader wants, which is a different question from the one R9.2 states.

**`text` is present whether or not the answer already streamed, and that is a deliberate
divergence from the prose branch.** `weft_cli.render._render_ask` omits an answer a sink already
showed live, so a human does not read the same paragraph twice (task 3.11). That reasoning does
not cross the boundary: a consumer parses one line at a time, and a field whose presence depends
on which sink ran is exactly the state `ErrorEnvelope`'s own docstring refuses for
`valid_options` — "a field that is always present but usually empty would be indistinguishable
from 'there really were no alternatives'". Self-contained either way costs one duplicated string
and removes a conditional a consumer would otherwise have to know about.

**Every field of a `Citation` reaches this rendering, which is R9.2's first half.**
`weft_generate.payload.Citation` carries `marker`, `node_id`, `source_id`, `uri`, `quote` and
`page`; the human line rendered `marker` and `uri` alone, so several nodes cut from one document
cited identically and *which* node answered was unobservable — the exact question task 10.16 was
asked to demonstrate and could not. The models are emitted whole rather than flattened here, so a
field added to `Citation` later reaches a script without this module changing.

**Versioned additively in the data, on `ErrorEnvelope`'s own reasoning** (`docs/09-release.md`
§3): `ENVELOPE_VERSION` is a plain field with a default, never a `ClassVar` a serialiser would
drop, because a consumer cannot assume the version its own reader expects is the version a line
already on the wire carries.
"""

from __future__ import annotations

from typing import Final

from pydantic import BaseModel, ConfigDict

from weft_cli.sinks import LineKind
from weft_generate.payload import Answer, Citation

#: `09` §3's additive promise, carried in the data — see the module docstring.
ANSWER_ENVELOPE_VERSION: Final[str] = "1.0.0"


class AnswerEnvelope(BaseModel):
    """One routed `Answer`, whole, for a script. Built only by `build_answer_envelope` below,
    so every emitting site stays identical by construction — `ErrorEnvelope`'s own rule.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: Which line shape this is — `weft_cli.sinks.LineKind`, ledger task **6.16**. `weft --json`
    #: writes `StreamEvent` lines, this, and `ErrorEnvelope` on one descriptor, and a consumer
    #: must not have to tell them apart by which keys are present.
    kind: LineKind = LineKind.ANSWER_ENVELOPE
    envelope_version: str = ANSWER_ENVELOPE_VERSION
    #: The pipeline that actually answered — the router's own choice, or the name `--pipeline`
    #: gave. `None` only where `AskCommandResult.pipeline_name` is, which `AskCommandResult`'s
    #: own docstring says never happens while `answer` is set.
    pipeline_name: str | None = None
    text: str
    citations: tuple[Citation, ...] = ()


def build_answer_envelope(answer: Answer, *, pipeline_name: str | None) -> AnswerEnvelope:
    """The one place an `Answer` becomes an `AnswerEnvelope`.

    `pipeline_name` is a parameter rather than read off `answer`, because an `Answer` does not
    carry one: it is `weft_cli.commands.AskCommandResult`'s own field, set by whichever of the
    router or `--pipeline` decided, and this module is not a second place that decision is made.
    """
    return AnswerEnvelope(
        pipeline_name=pipeline_name,
        text=answer.text,
        citations=tuple(answer.citations),
    )


__all__: list[str] = ["ANSWER_ENVELOPE_VERSION", "AnswerEnvelope", "build_answer_envelope"]
