"""The `LLMProvider` contract — published here, never by the kernel.

Task **2.30**: "the generation pack names no vendor, because a provider adapter is its own
pack and the offline default is a deterministic scripted provider." A vendor's SDK is a
dependency (`weft-openai`'s own module docstring makes the same case for `Embedder`), and a
generation pack that never imports one is only checkable if the contract a vendor registers
under lives somewhere neither the vendor's pack nor the generation pack is required to be —
this module.

**`LLMProvider` is not a pipeline position.** Unlike `Extractor`, `Chunker` or `Embedder`, it
declares no `Stage` base: `.phase2-design.md` §3 groups it with `Prompt` under "named and
registered, but not pipeline positions" — a pipeline names a *role* (`[llm.roles]`), never a
provider, so nothing in a resolved stage list ever names `"openai"` or `"scripted"`
directly. What resolves a role to a provider instance is the `LLM` service `weft-llm` will
publish alongside the retry and cascade machinery, one task later; this module publishes
only the plugin surface a provider registers against.

**`model` is a per-call argument, not constructor state.** A provider instance is built once
(`registry.entry(LLMProvider, name).factory(...)`) and is asked to answer under whatever
model a call names — the same account, many models, exactly the shape an operator's
`[llm.roles]` table needs: `generate` and `grade` can share one `openai` registration while
naming two different models.
"""

from collections.abc import AsyncIterator, Mapping
from typing import TYPE_CHECKING, ClassVar, Protocol, runtime_checkable

from weft_kernel.context import Context
from weft_kernel.payload import Outcome
from weft_llm.payload import Completion, Conversation, Rendered, TokenChunk

#: Fitness function 6's subject for this contract.
LLM_CONTRACT_VERSION = "1.0.0"


@runtime_checkable
class LLMProvider(Protocol):
    """One vendor's (or one deterministic offline) answer to "continue this conversation".

    `complete` returns a decided `Outcome` — `Produced`, never left to a caller draining a
    stream to find out whether the call succeeded (`01` → *Colour*, G6). `stream` is always
    called by the `LLM` service regardless of whether a caller asked to see tokens as they
    arrive (`.phase2-design.md` decision 10: streaming attaches at the client, so a provider
    that forgets to implement it faithfully cannot exist as a second, diverging code path).
    `close` releases whatever connection the provider opened; a provider that opens none
    still implements it, returning immediately, the same shape `Stage` implementations with
    nothing to flush already take for `flush`.
    """

    if TYPE_CHECKING:
        #: Declared only for a type checker, assigned for real after the class body, so it
        #: never joins `__protocol_attrs__` — the pattern every Phase 0/1/2 contract shares.
        version: ClassVar[str]

    async def complete(
        self, conv: Conversation, *, model: str, ctx: Context
    ) -> Outcome[Completion]: ...

    async def stream(self, conv: Conversation, *, model: str, ctx: Context) -> AsyncIterator[str]:
        # Repair for a reviewer finding against task 2.30. An `async def` stub with an
        # `Ellipsis` body types, to a checker, as a coroutine that *returns* an
        # `AsyncIterator[str]` — not as an async generator — so a variable declared
        # `LLMProvider` could not `async for` over `.stream(...)` without first `await`ing
        # it, which neither `ScriptedProvider` nor `OpenAILLMProvider` (both real async
        # generators) satisfies or requires. The unreachable `yield` below is the one thing
        # that tells a checker "this is an async generator", the same way `...` tells it
        # "this is a coroutine" for every method above.
        if False:  # pragma: no cover — never executed, only read by the type checker
            yield ""
        return

    async def close(self) -> None: ...


LLMProvider.version = LLM_CONTRACT_VERSION


@runtime_checkable
class NativeStructured(Protocol):
    """A provider that will answer *in a schema*, checked by the vendor rather than by us.

    **A derived capability sibling, never a declared one** — `.phase2-design.md` §3: "tier 1
    is available iff `isinstance(provider, NativeStructured)`. That replaces the reference's
    `hasattr(self.llm, "structured_predict")` guard with capability derived at registration,
    and it means a provider that lies about structured output cannot exist — it either has
    the method or it does not." The same pattern `weft-store` uses for `VectorSearch` and
    `TextSearch`, applied to the one branch of the cascade that can skip two tiers of work.

    Nothing registers *under* this contract: a provider registers under `LLMProvider` and is
    found to satisfy this one, which is what makes the capability underivable from a claim.
    """

    if TYPE_CHECKING:
        version: ClassVar[str]

    async def complete_structured(
        self, conv: Conversation, schema: Mapping[str, object], *, model: str, ctx: Context
    ) -> Outcome[Completion]: ...


NativeStructured.version = LLM_CONTRACT_VERSION


class LLM(Protocol):
    """The run's one answer to "ask a model" — retry, streaming and role resolution attached.

    **A service, not a plugin.** Reached by `ctx.require(LLM)`, never named in a pipeline.
    `.phase2-design.md` §3 states the mechanical rule that keeps it that way: a service
    "carries no `version` and is never registered under a name", which is what keeps it out of
    the contract reference and out of fitness function 9(c)'s left side. It is therefore a
    plain `Protocol` — not `@runtime_checkable`, and with no `version` assigned after the
    class body — and both omissions are the point rather than an oversight.

    **A stage names a role, never a provider and never a model.** Decision 9: `[llm.roles]` is
    an open key space in the operator's own file, so `generate` and `grade` can run on
    different models without either technique's code knowing which. `weft_llm.roles.LLMRoles`
    is what a role is resolved against, and an unmapped one fails naming every mapped role.

    **`structured` is deliberately absent, and this is a correction to `.phase2-design.md`
    §3.** That section lists a `structured[T]` member here returning `Outcome[Structured[T]]`,
    but `Structured` and the cascade that produces it live in `weft-prompts`, one pack
    *downstream* — §2's one-way chain (`weft-llm ← weft-prompts`) makes naming it here a
    cycle. §7 also says of `weft_prompts.cascade.execute` that "every technique needing a
    typed answer from a model calls this and nothing else", which a second entry point on this
    Protocol would contradict. The two members below are what the cascade needs from a client
    and all it needs: whether tier 1 is available for a role, and how to run it.
    """

    async def complete(
        self, rendered: Rendered, *, role: str, ctx: Context
    ) -> Outcome[Completion]: ...

    async def complete_structured(
        self, rendered: Rendered, schema: Mapping[str, object], *, role: str, ctx: Context
    ) -> Outcome[Completion]: ...

    async def native_structured_available(self, role: str) -> bool: ...

    async def close(self) -> None: ...


class TokenSink(Protocol):
    """Where an answer's tokens go as they arrive. One per run, and never absent.

    A service for the same reasons `LLM` is one, and carrying no `version` for the same
    mechanical reason. `.phase2-design.md` §7 makes its always-present-ness a promise rather
    than a convention — "`NullSink` … **never absent**, so no plugin needs a `try`" — which is
    why `weft_llm.client` resolves it with a bare `ctx.require` and no fallback: a run
    assembled without one is a bug in the assembler, and a silent no-op sink installed here
    would hide it.

    `close` takes a `reason` because a run that ended badly and a run that ended should not
    look identical to whatever is displaying tokens.
    """

    async def emit(self, chunk: TokenChunk) -> None: ...

    async def close(self, *, reason: str | None = None) -> None: ...
