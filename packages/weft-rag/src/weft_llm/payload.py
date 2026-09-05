"""The boundary types `LLMProvider` trades in — a conversation in, a completion out.

Published here rather than reused from anywhere downstream: `weft_retrieve.payload.Turn`
already carries a role and a text, but `weft-llm` sits *upstream* of `weft-retrieve` in the
one-way dependency chain `.phase2-design.md` §2 states — `weft-kernel ← weft-store ←
weft-llm ← weft-prompts ← weft-retrieve ← weft-generate` — so importing that type here would
point a dependency the wrong direction. A conversation with a model and a chat turn in the
query path are two different facts that happen to share a shape; `weft-prompts`, the pack
between them, is what will eventually build one from the other, and until it does the two
stay independent rather than sharing a type neither owns.

`Conversation` and `Completion` are the whole surface `LLMProvider.complete` needs: what was
said, and what came back. Neither carries a `model` field — `model` is an argument to
`complete`/`stream`, not a fact recorded on the exchange, because `.phase2-design.md`
decision 9 is categorical that a role picks a model at the call site and nothing about the
conversation itself should have to agree.
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class MessageRole(StrEnum):
    """Who said one turn of a `Conversation` — the three roles every chat-completion API takes."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class OnFailure(StrEnum):
    """What a model-backed step does when the cascade it called did not answer usably.

    Published here rather than in `weft-retrieve` or `weft-generate`, because both depend on
    `weft-llm` already (the one-way chain in `.phase2-design.md` §2) and both need it: ledger
    2.15's `contextual-query-rewrite` is the first `on_failure` field, and `.phase2-design.md`
    §10's task table types the same field the same way for `hyde` (2.16), `iterative-retrieval`
    (2.20), `graded-retrieval` (2.21a), `contradiction-check` (2.22), `boolean-retrieval`
    (2.23a) and `refine-on-uncertainty` (2.24) — one vocabulary shared by every plugin that
    asks a model something optional, not a fresh `Literal` invented per module.

    **One member today, and that is not a placeholder.** Every task line that names this field
    also names `FAIL` as its default and every worked example in the design record fails loudly
    rather than degrading. `Enum` over `Literal` is this project's rule for a *string constant*,
    not a promise that every enum ships with two members on day one — a task that genuinely
    needs a second behaviour (a transform that degrades to "pass the question through
    unrewritten" rather than stopping the pipeline, say) adds the member here, in the commit
    that needs it, which is a config-shaped change every existing caller of this type is
    unaffected by. Inventing an unused second member now to make the type "look right" would be
    exactly the tuning constant with no measurement behind it this project's rules refuse.
    """

    FAIL = "fail"


class Message(BaseModel):
    """One turn: who said it, and the text of it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    role: MessageRole
    content: str


class Conversation(BaseModel):
    """What `LLMProvider.complete`/`stream` is asked to continue — at least one message."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    messages: tuple[Message, ...] = Field(min_length=1)


class TokenUsage(BaseModel):
    """How many tokens one completion actually cost — task **4.7**, V5's money half.

    A price needs tokens in and out per call, and a per-model rate; this is the "per call"
    half, carried on the `Completion` it describes rather than threaded back out of band. Two
    fields, never a vendor's own richer usage object relayed verbatim — a caller pricing a run
    needs exactly these two numbers, and a wider, vendor-shaped field would be `dict[str, Any]`
    wearing a different hat, the shape CLAUDE.md already refuses.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)


class Completion(BaseModel):
    """What a provider answered: the text, the model that actually produced it, and why it stopped.

    `model` is restated on the answer rather than left implicit — a provider may not honour
    the exact string it was asked for (an alias, a version pin resolved server-side), and a
    caller comparing a `Completion` against `model="gpt-4o-mini"` should compare against
    what ran, not what was requested.

    `usage` is `None` for a provider that made no real call and so has nothing to report —
    `weft_llm.scripted.ScriptedProvider` answers this way honestly, the same way it marks its
    own text `[scripted]` rather than pretending to be a real model — and populated by a real
    vendor provider (`weft_openai.llm.OpenAILLMProvider`) from what the vendor's own response
    reports. `weft_llm.stream` reports no usage either, for the identical reason it reports no
    `finish_reason`: a streamed answer is read a piece at a time, never as one response object
    a token count could be read off.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    text: str
    model: str
    #: The vendor's own word for why generation stopped — `"stop"`, `"length"`,
    #: `"content_filter"` and so on differ by provider, so this is relayed rather than
    #: mapped onto a closed vocabulary nothing here can maintain honestly. `""` when the
    #: answer arrived over `stream`, which reports no reason — see `weft_llm.client`.
    finish_reason: str = ""
    #: See the class docstring's own paragraph on `usage`.
    usage: TokenUsage | None = None


class Rendered(BaseModel):
    """A prompt, rendered into the conversation a provider is asked to continue.

    **Published here rather than in `weft-prompts`, and the placement is forced.** A `Prompt`
    produces it, so `.phase2-design.md` §2's ownership rule would put it one pack downstream —
    but `weft_llm.contract.LLM.complete` takes one, and `weft-llm` may not import
    `weft-prompts` without turning the one-way chain into a cycle. §2 already settles exactly
    this shape of conflict once, for `Answer`: "that single placement is what keeps the graph
    acyclic". The same answer, for the same reason. Task 2.10.

    `prompt` and `prompt_version` are carried so telemetry, a cache key or an A/B comparison
    can say *which* prompt produced an answer without the caller threading it separately;
    both are `""` for a conversation built by hand, which a library caller may legitimately do.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    conversation: Conversation
    prompt: str = ""
    prompt_version: str = ""


class TokenChunk(BaseModel):
    """One piece of an answer as it arrives, tagged with the role that asked for it.

    The `role` tag is what lets one sink serve a whole run: `.phase2-design.md` §7 has the
    CLI's sink display only the roles in its display set (default `{"generate"}`), so a
    critic's or a grader's internal call never pollutes what a reader sees. Filtering at the
    sink rather than at the emit site is the same argument decision 10 makes for streaming
    itself — a call site that has to remember to stay quiet eventually forgets.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    role: str
    text: str
