"""The three-tier structured-output cascade. Every typed answer from a model comes through here.

`.phase2-design.md` §7: "every technique needing a typed answer from a model calls this and
nothing else." Three tiers, at most three calls, and the tier that succeeded is a **field** on
the result rather than a `logger.debug` — because "which tier answered" is the single most
useful number for deciding whether a model change was an upgrade, and a log line is not a
number anyone aggregates.

All the recorded corrections are carried, and each one is a thing that went wrong once:

- **Tier 1 `native` is guarded by a derived capability**, `llm.native_structured_available(role)`
  over `isinstance(provider, NativeStructured)`, never `hasattr`. A provider that lies about
  structured output cannot exist.
- **Tier 2 `adapted` is skipped entirely when tier 1 raised `LLMBadRequestError`.** `04`:147-153
  records this short-circuit as one that "cannot be re-derived from first principles": a vendor
  that rejected the schema-shaped request rejects the schema-instructed one too. Carried as an
  explicit `skip_adapted` flag, not the reference's `(None, True)` tuple.
- **`LLMPermissionDeniedError` is caught at tiers 1 and 2 and re-raised.** Lifting the cascade
  without this re-introduces the worst failure mode it has: a bad API key surfacing as a `0.0`
  that looks like a bad answer. It is why `weft_llm.errors` gives permission-denied its own leaf
  rather than folding it into `LLMAuthenticationError`.
- **The step-down set is `ValidationError` and `ValueError` only** — narrowed from the reference's
  five. `AttributeError`, `TypeError` and `RuntimeError` in that tuple silence real bugs, and a
  cascade that silences a bug spends two more model calls hiding it.
- **Tier 3's catch set is not narrower than the step-down set**, so a malformed completion
  returns `Failed` instead of raising out of `execute()` the way the reference's did.
- **No retries inside the cascade.** Retry is the provider wrapper's (`weft_llm.retry`), which is
  why a transient failure leaves here rather than costing a tier: three tiers is at most three
  calls, never nine.

**`Failed` carries the raw text, truncated to 200 characters.** It is the only diagnostic that
survives a total parse failure, and it is usually the model explaining in prose why it declined
the shape. The message is phrased by an `LLMCompletionError` — the taxonomy leaf that exists for
"the call succeeded and the answer could not be used" — constructed rather than raised, because
the cascade must not leak an exception past the seam.
"""

import json
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, ValidationError

from weft_kernel.context import Context
from weft_kernel.payload import Failed, Outcome, Produced
from weft_llm.contract import LLM
from weft_llm.errors import LLMBadRequestError, LLMCompletionError, LLMPermissionDeniedError
from weft_llm.payload import Completion, Conversation, Message, MessageRole, Rendered
from weft_prompts.contract import Prompt
from weft_prompts.rescue import rescue_json

#: How much of an unparseable completion survives into the `Failed` reason. The reference's number,
#: kept because it is the length at which a model's prose refusal is still readable in a terminal.
RAW_TEXT_LIMIT = 200

#: Tier 2's schema instruction. Written here rather than as a registered `Prompt` because it is
#: not a question — it is a constraint on the *shape* of an answer to somebody else's question,
#: and a prompt pack translating it into Polish would change nothing a model reads differently.
_SCHEMA_INSTRUCTION = (
    "Answer with a single JSON object and nothing else — no prose, no code fence. "
    "It must validate against this JSON Schema:\n"
)


class CascadeTier(StrEnum):
    """Which of the three routes produced a typed value. A field, never a log line."""

    NATIVE = "native"
    ADAPTED = "adapted"
    RESCUED = "rescued"


class Structured[T: BaseModel](BaseModel):
    """A typed answer, plus how much work it took to get it.

    `tier` and `attempts` are what make a model change measurable: a run whose grader slid from
    `native` to `rescued` is doing three times the work for a worse answer, and nothing else in
    the system would say so.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    value: T
    tier: CascadeTier
    attempts: int


async def execute[T: BaseModel](
    *,
    llm: LLM,
    prompt: Prompt,
    values: BaseModel,
    output: type[T],
    role: str,
    ctx: Context,
) -> Outcome[Structured[T]]:
    """Ask `prompt` under `role` and return `output`, stepping down through the three tiers."""
    rendered_outcome = await prompt.render(values, ctx)
    if not isinstance(rendered_outcome, Produced):
        # A prompt that had nothing to ask, or could not build the ask, is relayed exactly as
        # it answered. Reinterpreting it here would invent a question nobody wrote.
        return rendered_outcome
    rendered = rendered_outcome.value
    attempts = 0

    native_available = await llm.native_structured_available(role)
    skip_adapted = False
    if native_available:
        attempts += 1
        settled, skip_adapted = await _tier_native(
            llm=llm, rendered=rendered, output=output, role=role, ctx=ctx, attempts=attempts
        )
        if settled is not None:
            return settled

    if not skip_adapted:
        attempts += 1
        try:
            adapted = await llm.complete(_with_schema(rendered, output), role=role, ctx=ctx)
        except LLMPermissionDeniedError:
            raise
        if not isinstance(adapted, Produced):
            return adapted
        accepted = _accept(adapted.value.text, output, CascadeTier.ADAPTED, attempts)
        if accepted is not None:
            return accepted

    attempts += 1
    plain = await llm.complete(rendered, role=role, ctx=ctx)
    if not isinstance(plain, Produced):
        return plain
    return _rescue(plain.value, output, attempts=attempts, role=role)


async def _tier_native[T: BaseModel](
    *,
    llm: LLM,
    rendered: Rendered,
    output: type[T],
    role: str,
    ctx: Context,
    attempts: int,
) -> tuple[Outcome[Structured[T]] | None, bool]:
    """Tier 1. Returns `(settled outcome or None, skip tier 2)`.

    The second half of that tuple is `04`:147-153's short-circuit made explicit — the reference
    encoded it as a `(None, True)` return whose meaning lived only in the reader's head, and
    this returns it as a named boolean the caller must do something with.
    """
    try:
        native = await llm.complete_structured(
            rendered, output.model_json_schema(), role=role, ctx=ctx
        )
    except LLMPermissionDeniedError:
        raise
    except LLMBadRequestError:
        return None, True
    if not isinstance(native, Produced):
        return native, False
    return _accept(native.value.text, output, CascadeTier.NATIVE, attempts), False


def _accept[T: BaseModel](
    text: str, output: type[T], tier: CascadeTier, attempts: int
) -> Outcome[Structured[T]] | None:
    """`text` as a finished `Structured`, or `None` meaning "step down to the next tier"."""
    parsed = _validate(text, output)
    if parsed is None:
        return None
    return Produced(value=Structured(value=parsed, tier=tier, attempts=attempts))


def _validate[T: BaseModel](text: str, output: type[T]) -> T | None:
    """`text` as `output`, or `None` to step down. The narrowed catch set, in one place."""
    try:
        return output.model_validate_json(text)
    except (ValidationError, ValueError):
        return None


def _with_schema(rendered: Rendered, output: type[BaseModel]) -> Rendered:
    """`rendered` with the schema instruction appended as a final user turn.

    Appended rather than folded into the prompt's own template: the instruction is the
    cascade's, not the prompt author's, and a prompt whose text changed depending on which tier
    was running would be two prompts wearing one name.
    """

    instruction = _SCHEMA_INSTRUCTION + json.dumps(output.model_json_schema(), indent=2)
    return Rendered(
        conversation=Conversation(
            messages=(
                *rendered.conversation.messages,
                Message(role=MessageRole.USER, content=instruction),
            )
        ),
        prompt=rendered.prompt,
        prompt_version=rendered.prompt_version,
    )


def _rescue[T: BaseModel](
    completion: Completion, output: type[T], *, attempts: int, role: str
) -> Outcome[Structured[T]]:
    """Tier 3: the JSON-rescue extractor, then validation, then a `Failed` that says why."""
    direct = _validate(completion.text, output)
    if direct is not None:
        return Produced(value=Structured(value=direct, tier=CascadeTier.RESCUED, attempts=attempts))
    rescued = rescue_json(completion.text)
    if rescued is not None:
        try:
            return Produced(
                value=Structured(
                    value=output.model_validate(rescued),
                    tier=CascadeTier.RESCUED,
                    attempts=attempts,
                )
            )
        except (ValidationError, ValueError):
            pass
    raw = completion.text[:RAW_TEXT_LIMIT]
    # Constructed for its message, never raised — the cascade must not leak past the seam.
    # `provider=""` because the cascade genuinely does not know which provider answered: it
    # holds an `LLM`, and a role is what identifies the configuration entry. The role is in
    # the message, which is the half that reaches a reader.
    error = LLMCompletionError(
        f"could not parse a {output.__name__} from the completion for role '{role}' after "
        f"{attempts} attempt(s). Raw text ({RAW_TEXT_LIMIT} chars): {raw!r}",
        provider="",
        model=completion.model,
    )
    return Failed(reason=str(error))
