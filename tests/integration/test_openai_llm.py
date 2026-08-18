"""The live half of `weft-openai`'s `LLMProvider`: a real completion, from a real account.

`docs/build-ledger.md` task 2.30 — "the generation pack names no vendor, because a provider
adapter is its own pack and the offline default is a deterministic scripted provider." Every
other test in this tree proves the second half by never needing an account; this file is the
first half, mirrored on `tests/integration/test_openai_embedder.py`'s own shape — skipped,
with a reason, when no credential is present, so `poe ci-checks` runs end to end on a clean
checkout and re-measures the live claim whenever a key is exported.

**What is asserted is behaviour, not a threshold.** `09` §4.4 forbids inventing a quality
number; the property worth checking against the real API is that `gpt-4o-mini` answers a
question this pack asked it to answer, under the model this pack asked for, and that the
same account refuses cleanly — mapped to `weft_llm.errors.LLMAuthenticationError`, not a bare
vendor exception — when the key is wrong.

**One test here is a repair for a reviewer finding against task 2.30, not a new claim about
the API.** `tests/unit/weft_openai/test_llm.py`'s own blocking-guard test injects a `client`,
so `_connected()` returns before ever reaching `asyncio.to_thread(build_client, settings)` —
the line the guard exists to police. Only a provider built with *no* injected client reaches
it, and that needs a real credential and a real `AsyncOpenAI`, the same reason
`tests/unit/weft_qdrant/test_store.py`'s task 2.6 repair needs a real Qdrant container rather
than a stub — so this test lives here, not in the unit suite.
"""

import os

import pytest
from pydantic import SecretStr

from weft_kernel.context import Context
from weft_kernel.payload import Produced
from weft_kernel.seam import wrap
from weft_llm.errors import LLMAuthenticationError
from weft_llm.payload import Conversation, Message, MessageRole
from weft_openai import Settings
from weft_openai.llm import DEFAULT_MODEL, NAME, OpenAILLMProvider

_API_KEY_VAR = "OPENAI_API_KEY"


def _ctx() -> Context:
    return Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")


def _credential() -> SecretStr:
    key = os.environ.get(_API_KEY_VAR)
    if not key:
        pytest.skip(f"{_API_KEY_VAR} is unset: the live OpenAI completion checks cannot run")
    return SecretStr(key)


async def test_the_default_model_answers_a_question_it_was_asked() -> None:
    # Arrange
    provider = OpenAILLMProvider(Settings(api_key=_credential()))
    conv = Conversation(
        messages=(
            Message(
                role=MessageRole.USER,
                content='Reply with exactly one word: the word "acknowledged".',
            ),
        )
    )

    # Act
    outcome = await provider.complete(conv, model=DEFAULT_MODEL, ctx=_ctx())

    # Assert
    assert isinstance(outcome, Produced)
    assert "acknowledged" in outcome.value.text.lower()
    assert outcome.value.model == DEFAULT_MODEL
    await provider.close()


async def test_streaming_answers_the_same_question_in_pieces() -> None:
    # Arrange
    provider = OpenAILLMProvider(Settings(api_key=_credential()))
    conv = Conversation(
        messages=(Message(role=MessageRole.USER, content="Count from one to three."),)
    )

    # Act
    pieces = [piece async for piece in provider.stream(conv, model=DEFAULT_MODEL, ctx=_ctx())]

    # Assert — streamed as more than one fragment, and it reassembles into prose.
    assert len(pieces) > 1
    assert "".join(pieces).strip()
    await provider.close()


async def test_a_bad_credential_is_mapped_to_an_authentication_error() -> None:
    # Arrange — a well-formed but wrong key, so the request reaches the vendor and is refused
    # there rather than failing this pack's own local validation.
    _credential()  # skip if there is no real account to contrast against
    provider = OpenAILLMProvider(Settings(api_key=SecretStr("sk-not-a-real-key")))
    conv = Conversation(messages=(Message(role=MessageRole.USER, content="hello"),))

    # Act / Assert
    with pytest.raises(LLMAuthenticationError) as raised:
        await provider.complete(conv, model=DEFAULT_MODEL, ctx=_ctx())
    assert raised.value.provider == "openai"
    await provider.close()


async def test_driving_a_freshly_built_client_through_the_seam_makes_no_blocking_call() -> None:
    """Repair for a reviewer finding against task 2.30: the unit suite's blocking-guard test
    never reaches `asyncio.to_thread(build_client, settings)`, because its injected `client`
    short-circuits `_connected()` before that line runs. This one gives `OpenAILLMProvider` no
    client at all, so `.complete()` — driven through the same `weft_kernel.seam.wrap` a
    registered plugin is actually called through — builds a real `AsyncOpenAI` off the loop
    for the first time. A regression that dropped the `asyncio.to_thread` offload would raise
    `weft_kernel.blocking.BlockingCallError` before the request ever reached the network.
    """
    # Arrange
    provider = OpenAILLMProvider(Settings(api_key=_credential()))  # no injected client
    wrapped = wrap(
        provider.complete, distribution="weft-openai", contract="LLMProvider", plugin=NAME
    )
    conv = Conversation(
        messages=(Message(role=MessageRole.USER, content='Reply with one word: "ok".'),)
    )

    # Act
    outcome = await wrapped(conv, model=DEFAULT_MODEL, ctx=_ctx())

    # Assert
    assert isinstance(outcome, Produced)
    await provider.close()
