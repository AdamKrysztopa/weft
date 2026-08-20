"""Unit tests for `weft_llm.scripted`.

Mirrors `packages/weft-llm/src/weft_llm/scripted.py`. Covers the happy path (a deterministic
answer derived from the conversation), the edge case (a fixed `reply` overrides the derived
one), and drives the plugin through `weft_kernel.seam.wrap` — the group note against every
task from 2.6 forward: a unit test calling `ScriptedProvider.complete` directly never proves
the plugin survives the one path a registered plugin is actually called through.
"""

from typing import cast

from weft_kernel.context import Context
from weft_kernel.payload import Produced
from weft_kernel.seam import wrap
from weft_llm.contract import LLMProvider
from weft_llm.payload import Conversation, Message, MessageRole
from weft_llm.scripted import NAME, ScriptedConfig, ScriptedProvider


def _ctx() -> Context:
    return Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")


def _conversation(*texts: str) -> Conversation:
    return Conversation(messages=tuple(Message(role=MessageRole.USER, content=t) for t in texts))


async def test_complete_derives_a_deterministic_answer_from_the_last_user_turn() -> None:
    # Arrange
    provider = ScriptedProvider()
    conv = _conversation("why does mRMR subtract redundancy?")

    # Act
    first = await provider.complete(conv, model="any-model", ctx=_ctx())
    second = await provider.complete(conv, model="any-model", ctx=_ctx())

    # Assert — same input, same answer, and no vendor name leaked into it.
    assert isinstance(first, Produced)
    assert isinstance(second, Produced)
    assert first.value == second.value
    assert "why does mRMR subtract redundancy?" in first.value.text
    assert first.value.model == "any-model"
    # Task 4.7: nothing was really called, so there is nothing to price — `usage` says so
    # honestly rather than a `0` a caller could mistake for a real, priceable zero-cost call.
    assert first.value.usage is None


async def test_a_configured_reply_overrides_the_derived_one() -> None:
    # Arrange — the edge case: two different questions must not force two different
    # answers when the config says otherwise.
    provider = ScriptedProvider(ScriptedConfig(reply="always this"))

    # Act
    first = await provider.complete(_conversation("question one"), model="m", ctx=_ctx())
    second = await provider.complete(_conversation("question two"), model="m", ctx=_ctx())

    # Assert
    assert isinstance(first, Produced)
    assert isinstance(second, Produced)
    assert first.value.text == "always this"
    assert second.value.text == "always this"


async def test_driving_the_provider_through_the_registration_seam_makes_no_blocking_call() -> None:
    """Fitness function 7(b) against the one path every registered plugin is called through.

    `ScriptedProvider` opens no connection, so nothing here is expected to fail — the value
    of this test is structural: it proves the plugin was actually exercised through
    `weft_kernel.seam.wrap`, not merely through a direct method call a registered instance
    never receives in production.
    """
    # Arrange
    provider = ScriptedProvider()
    wrapped = wrap(provider.complete, distribution="weft-llm", contract="LLMProvider", plugin=NAME)
    conv = _conversation("does this pass through the seam?")

    # Act
    outcome = await wrapped(conv, model="m", ctx=_ctx())

    # Assert
    assert isinstance(outcome, Produced)
    assert isinstance(provider, LLMProvider)


async def _drive_as_the_contract_type(provider: LLMProvider) -> list[str]:
    """`provider.stream(...)` under `async for`, with `provider` typed exactly as
    `weft_llm.contract.LLMProvider` declares it — never as the concrete class. This is what
    makes the test below a check of the *contract's* calling convention rather than of
    whichever concrete `.stream()` pyright happens to see through the variable.
    """
    return [piece async for piece in provider.stream(_conversation("go"), model="m", ctx=_ctx())]


async def test_a_provider_typed_as_the_llmprovider_contract_can_stream_with_no_await() -> None:
    """Repair for a reviewer finding against task 2.30's contract. An `async def` Protocol
    stub with an `Ellipsis` body types `.stream(...)` as a coroutine, not an async generator,
    so a value typed `LLMProvider` could not be driven with a bare `async for` — it would need
    an `await` first, which `ScriptedProvider` (a real async generator) does not want and does
    not need. `cast` stands in only for the unrelated gap every Weft contract shares — none of
    their `version: ClassVar[str]` is ever declared on a concrete plugin, so pyright refuses
    the assignment on that ground alone, in every pack, not on the ground this test exists to
    check; `tests/unit/weft_openai/test_llm.py` carries the matching check for
    `OpenAILLMProvider`, since the defect under test was in the shared Protocol, not in either
    plugin, so both implementations earn the same proof.
    """
    # Arrange
    provider = cast("LLMProvider", ScriptedProvider(ScriptedConfig(reply="a b c")))

    # Act
    pieces = await _drive_as_the_contract_type(provider)

    # Assert — exact, not `.strip()`ed: task 2.10's client always streams, so a stream that
    # does not rejoin to exactly what `complete` returns *is* the divergence decision 10 exists
    # to make impossible.
    assert "".join(pieces) == "a b c"
