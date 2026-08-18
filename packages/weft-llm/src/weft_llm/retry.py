"""Retry, attached once, around a provider — never re-implemented at a call site.

`.phase2-design.md` §7: "**Retry attaches once, at assembly, and no call site re-implements
it.** `weft_llm.retry.with_retry(provider, policy)` returns a structural `LLMProvider` that
delegates; `build_services` applies it before the provider enters the client." That is the
registration-seam rule applied to resilience: a concern every technique author would otherwise
have to remember is applied by the machinery instead, and `docs/01-high-level-plan.md` records
what happens to the ones authors must remember.

**There is still no kernel retry engine, and this is not one.** `docs/02-extension-model.md`
§1 forbids it; resilience lives at the model seam, which is exactly here. Nothing in this
module names a capability the kernel would have to know about — it wraps one object that
answers `complete`/`stream`/`close` and returns another that answers the same three.

**What is retried, stated as a rule rather than a list.** A `weft_llm.errors.LLMError` whose
`transient` flag is set, and nothing else. `transient` is the kernel's own marker
(`weft_kernel.errors.WeftError`), and in this taxonomy exactly one branch sets it:
`LLMTransientError` fixes it to `True` on the branch so no leaf can forget. Catching the
branch class directly would work today and break the moment a provider pack adds a transient
leaf elsewhere; catching `LLMError` and reading the flag is the same set with a reason.

**Never a bare `except Exception`.** A `KeyError` inside a provider is a bug, and retrying a
bug three times turns a stack trace into a timeout. **`CancelledError` is untouched by
construction** — it is a `BaseException`, so no `except Exception` clause here can see it, and
there is no `except BaseException` anywhere in this file.

**A stream is retried only before its first chunk.** Re-running a generator that has already
yielded replays tokens a reader has seen; the honest answer is to let the failure out. Task
2.17's single-code-path argument is unaffected: there is still exactly one `stream`.
"""

import asyncio
from collections.abc import AsyncIterator, Mapping
from typing import cast

from pydantic import BaseModel, ConfigDict, Field

from weft_kernel.context import Context
from weft_kernel.payload import Outcome
from weft_llm.contract import LLMProvider, NativeStructured
from weft_llm.errors import LLMError
from weft_llm.payload import Completion, Conversation


class RetryPolicy(BaseModel):
    """`[llm.retry]` — how many attempts a transient failure gets, and how long between them.

    Every field carries a default, so a `weft.toml` with no `[llm.retry]` block still
    produces a policy: the derived rule `.phase2-design.md` §1 states for pack settings holds
    here for the same reason, that a missing block must not make assembly raise.

    **No jitter, deliberately.** Jitter exists to decorrelate a fleet of clients hammering one
    rate-limited endpoint; Weft runs one process per `weft ask`, so it would buy nothing and
    cost the property that makes this file testable — two runs of the same failure take the
    same time. When a deployment is large enough for the herd to be real, jitter is a field
    added here, once, not a decision spread across call sites.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: Total attempts including the first, so `1` means "do not retry" and `0` is refused —
    #: a policy that never calls the provider is a misconfiguration, not a mode.
    attempts: int = Field(default=3, ge=1)
    #: Delay before the second attempt, doubling for each attempt after it.
    base_delay_ms: int = Field(default=250, ge=0)
    #: The ceiling the doubling stops at, so a high `attempts` cannot produce a wait nobody
    #: intended.
    max_delay_ms: int = Field(default=8_000, ge=0)

    def delay_seconds(self, attempt: int) -> float:
        """Seconds to wait before attempt `attempt` (1-based); `0.0` before the first."""
        if attempt <= 1:
            return 0.0
        uncapped = self.base_delay_ms * (2 ** (attempt - 2))
        return min(uncapped, self.max_delay_ms) / 1000


class RetryingProvider:
    """Delegates to one provider, re-attempting exactly the failures marked transient.

    Satisfies `weft_llm.contract.LLMProvider` structurally, the same path every provider pack
    takes — which is what lets it stand in for the provider it wraps with nothing downstream
    aware that it did.
    """

    def __init__(self, inner: LLMProvider, policy: RetryPolicy) -> None:
        self._inner = inner
        self._policy = policy

    async def complete(
        self, conv: Conversation, *, model: str, ctx: Context
    ) -> Outcome[Completion]:
        last: LLMError | None = None
        for attempt in range(1, self._policy.attempts + 1):
            delay = self._policy.delay_seconds(attempt)
            if delay:
                await asyncio.sleep(delay)
            try:
                return await self._inner.complete(conv, model=model, ctx=ctx)
            except LLMError as error:
                if not error.transient:
                    raise
                last = error
        # Unreachable with `attempts >= 1`, but stated rather than assumed: the loop either
        # returned, re-raised a permanent failure, or recorded a transient one.
        assert last is not None
        raise last

    async def stream(self, conv: Conversation, *, model: str, ctx: Context) -> AsyncIterator[str]:
        last: LLMError | None = None
        for attempt in range(1, self._policy.attempts + 1):
            delay = self._policy.delay_seconds(attempt)
            if delay:
                await asyncio.sleep(delay)
            yielded = False
            try:
                async for chunk in self._inner.stream(conv, model=model, ctx=ctx):
                    yielded = True
                    yield chunk
                return
            except LLMError as error:
                if yielded or not error.transient:
                    raise
                last = error
        assert last is not None
        raise last

    async def close(self) -> None:
        """Closes the wrapped provider. Never retried — a failed close has nothing to redo."""
        await self._inner.close()


class RetryingNativeStructuredProvider(RetryingProvider):
    """`RetryingProvider` for a provider that also satisfies `NativeStructured`.

    A wrapper must advertise **exactly** what it wraps. `NativeStructured` is derived by
    `isinstance`, so a single wrapper class would erase the capability for every provider that
    has it — tier 1 of the cascade would silently never run, which is the class of failure
    `.phase2-design.md` §3 chose derived capability to make impossible. Two classes, selected
    by `with_retry` from what the wrapped object actually is, keep the derivation honest in
    both directions: this one cannot be built around a provider that lacks the method.
    """

    def __init__(self, inner: NativeStructured, policy: RetryPolicy) -> None:
        # `inner` satisfies both Protocols; `with_retry` is the only caller and checks.
        super().__init__(cast("LLMProvider", inner), policy)
        self._native = inner

    async def complete_structured(
        self, conv: Conversation, schema: Mapping[str, object], *, model: str, ctx: Context
    ) -> Outcome[Completion]:
        last: LLMError | None = None
        for attempt in range(1, self._policy.attempts + 1):
            delay = self._policy.delay_seconds(attempt)
            if delay:
                await asyncio.sleep(delay)
            try:
                return await self._native.complete_structured(conv, schema, model=model, ctx=ctx)
            except LLMError as error:
                if not error.transient:
                    raise
                last = error
        assert last is not None
        raise last


def with_retry(provider: LLMProvider, policy: RetryPolicy) -> LLMProvider:
    """`provider`, re-attempting transient failures under `policy`. The one way retry is added.

    The `cast` stands in for the gap every Weft contract shares, not for anything about this
    wrapper: a contract's `version: ClassVar[str]` is declared under `if TYPE_CHECKING:` and
    never on a concrete class, so pyright refuses *every* concrete-to-Protocol assignment in
    the tree on that ground alone — `tests/unit/weft_llm/test_scripted.py` records the same
    thing about `ScriptedProvider`. `isinstance` at runtime is the check that matters, and it
    is one line above.
    """
    if isinstance(provider, NativeStructured):
        return cast("LLMProvider", RetryingNativeStructuredProvider(provider, policy))
    return cast("LLMProvider", RetryingProvider(provider, policy))
