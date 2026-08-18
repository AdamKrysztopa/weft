"""Unit tests for `weft_prompts.cascade`.

Mirrors `packages/weft-prompts/src/weft_prompts/cascade.py`. Covers all three tiers, the two
corrections `.phase2-design.md` §7 says cannot be re-derived from first principles — tier 2 is
skipped entirely when tier 1 raised `LLMBadRequestError`, and `LLMPermissionDeniedError` is
re-raised rather than stepped down — and the total failure, which returns `Failed` carrying the
truncated raw text rather than leaking an exception.

The `LLMPermissionDeniedError` test is the one that matters most: without it, a bad API key
surfaces as a low structured-output score, which is the worst failure a cascade can produce.
"""

from collections.abc import Mapping
from typing import ClassVar, cast

import pytest
from pydantic import BaseModel

from weft_kernel.context import Context, ServiceRegistry
from weft_kernel.payload import Failed, NothingToProduce, Outcome, Produced
from weft_llm.errors import (
    LLMBadRequestError,
    LLMPermissionDeniedError,
    LLMRateLimitError,
)
from weft_llm.payload import Completion, Rendered
from weft_prompts.cascade import CascadeTier, Structured, execute
from weft_prompts.contract import Prompt
from weft_prompts.typed_prompt import PromptText, TypedPrompt


class _Ask(BaseModel):
    question: str


class _Verdict(BaseModel):
    verdict: str


class _Judge(TypedPrompt):
    name: ClassVar[str] = "judge"
    input_model: ClassVar[type[BaseModel]] = _Ask
    output_model: ClassVar[type[BaseModel] | None] = _Verdict
    texts: ClassVar[Mapping[str, PromptText]] = {"en": PromptText(user="Judge: ${question}")}


class _StubLLM:
    """An `LLM` that answers from a script, and records which members were reached."""

    def __init__(
        self,
        *,
        native: bool = False,
        native_reply: str | BaseException = "",
        plain: list[str | BaseException] | None = None,
    ) -> None:
        self._native = native
        self._native_reply = native_reply
        self._plain = plain if plain is not None else []
        self.plain_calls = 0
        self.native_calls = 0

    async def native_structured_available(self, role: str) -> bool:
        del role
        return self._native

    async def complete_structured(
        self, rendered: Rendered, schema: Mapping[str, object], *, role: str, ctx: Context
    ) -> Outcome[Completion]:
        del rendered, schema, role, ctx
        self.native_calls += 1
        if isinstance(self._native_reply, BaseException):
            raise self._native_reply
        return Produced(value=Completion(text=self._native_reply, model="m"))

    async def complete(self, rendered: Rendered, *, role: str, ctx: Context) -> Outcome[Completion]:
        del rendered, role, ctx
        reply = self._plain[min(self.plain_calls, len(self._plain) - 1)]
        self.plain_calls += 1
        if isinstance(reply, BaseException):
            raise reply
        return Produced(value=Completion(text=reply, model="m"))

    async def close(self) -> None:
        return


def _ctx() -> Context:
    return Context(tenant_id="t", run_id="r", trace_id="x", locale="en", services=ServiceRegistry())


async def _run(llm: _StubLLM) -> Outcome[Structured[_Verdict]]:
    return await execute(
        llm=llm,
        prompt=cast("Prompt", _Judge()),
        values=_Ask(question="is it so?"),
        output=_Verdict,
        role="grade",
        ctx=_ctx(),
    )


async def test_a_native_provider_answers_at_tier_one_in_one_attempt() -> None:
    # Arrange
    llm = _StubLLM(native=True, native_reply='{"verdict": "yes"}')

    # Act
    outcome = await _run(llm)

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value.value == _Verdict(verdict="yes")
    assert (outcome.value.tier, outcome.value.attempts) == (CascadeTier.NATIVE, 1)
    assert llm.plain_calls == 0


async def test_a_plain_provider_starts_at_tier_two_with_the_schema_in_the_prompt() -> None:
    # Arrange
    llm = _StubLLM(native=False, plain=['{"verdict": "no"}'])

    # Act
    outcome = await _run(llm)

    # Assert
    assert isinstance(outcome, Produced)
    assert (outcome.value.tier, outcome.value.attempts) == (CascadeTier.ADAPTED, 1)


async def test_a_fenced_reply_is_rescued_at_tier_three() -> None:
    # Arrange — tier 2 answers with prose around the JSON, which `model_validate_json` refuses.
    llm = _StubLLM(
        native=False,
        plain=['Sure:\n```json\n{"verdict": "maybe"}\n```', '```json\n{"verdict": "maybe"}\n```'],
    )

    # Act
    outcome = await _run(llm)

    # Assert
    assert isinstance(outcome, Produced)
    assert (outcome.value.tier, outcome.value.attempts) == (CascadeTier.RESCUED, 2)


async def test_tier_two_is_skipped_entirely_when_tier_one_rejected_the_request() -> None:
    # Arrange — `04`:147-153 records this short-circuit as one that "cannot be re-derived from
    # first principles": a vendor that refused the schema-shaped request will refuse the
    # schema-instructed one too, so tier 2 is a wasted call, not a chance.
    llm = _StubLLM(
        native=True,
        native_reply=LLMBadRequestError("schema unsupported", provider="p", model="m"),
        plain=['```json\n{"verdict": "yes"}\n```'],
    )

    # Act
    outcome = await _run(llm)

    # Assert — one native call, one plain call, and that plain call was tier 3.
    assert isinstance(outcome, Produced)
    assert outcome.value.tier is CascadeTier.RESCUED
    assert (llm.native_calls, llm.plain_calls) == (1, 1)


async def test_a_permission_denied_at_tier_one_is_re_raised_rather_than_stepped_down() -> None:
    # Arrange
    llm = _StubLLM(
        native=True,
        native_reply=LLMPermissionDeniedError("no access to this model", provider="p", model="m"),
        plain=['{"verdict": "yes"}'],
    )

    # Act / Assert — a bad credential must never surface as a low structured-output score.
    with pytest.raises(LLMPermissionDeniedError):
        await _run(llm)
    assert llm.plain_calls == 0


async def test_a_permission_denied_at_tier_two_is_re_raised_too() -> None:
    # Arrange
    llm = _StubLLM(
        native=False,
        plain=[LLMPermissionDeniedError("no access", provider="p", model="m")],
    )

    # Act / Assert
    with pytest.raises(LLMPermissionDeniedError):
        await _run(llm)


async def test_a_transient_failure_is_not_a_step_down_and_leaves_the_cascade() -> None:
    # Arrange — retry is the provider wrapper's job. Stepping down on a rate limit would burn
    # the two remaining tiers on an error that had nothing to do with the shape of the answer.
    llm = _StubLLM(native=False, plain=[LLMRateLimitError("slow down", provider="p", model="m")])

    # Act / Assert
    with pytest.raises(LLMRateLimitError):
        await _run(llm)


async def test_three_unusable_answers_fail_with_the_raw_text_truncated() -> None:
    # Arrange
    refusal = "I am not able to answer in that format because " + ("x" * 400)
    llm = _StubLLM(native=False, plain=[refusal, refusal])

    # Act
    outcome = await _run(llm)

    # Assert — the only diagnostic that survives a total parse failure, kept at 200 chars.
    assert isinstance(outcome, Failed)
    assert "I am not able to answer" in outcome.reason
    assert len(outcome.reason) < len(refusal)


async def test_a_provider_that_answered_with_nothing_is_relayed_not_reinterpreted() -> None:
    # Arrange
    class _Silent(_StubLLM):
        async def complete(
            self, rendered: Rendered, *, role: str, ctx: Context
        ) -> Outcome[Completion]:
            del rendered, role, ctx
            self.plain_calls += 1
            return NothingToProduce(reason="the model said nothing")

    # Act
    outcome = await _run(_Silent(native=False))

    # Assert — `NothingToProduce` is not a parse failure, and pretending otherwise would send
    # two more calls at a model that has already declined to speak.
    assert isinstance(outcome, NothingToProduce)
