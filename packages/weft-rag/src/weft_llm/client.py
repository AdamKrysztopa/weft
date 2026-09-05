"""The `LLM` service — one code path from a role to an answer, with everything attached.

Task **2.10**: the service `weft_llm.contract`'s own docstring promised "one task later",
"alongside the retry and cascade machinery". It is the assembly point for four things a
technique author must never write again: resolving a role to a provider and a model, retry,
the registration seam, and streaming.

**Streaming attaches here, and that discharges task 2.17 structurally.**
`.phase2-design.md` decision 10 and §7: "the `LLM` client **always** calls `provider.stream(...)`,
accumulates, and emits each chunk to `ctx.require(TokenSink)` tagged with the call's `role`.
`complete()` still returns a decided `Outcome[Completion]`, decided at return and not when a
stream is drained (G6)." One code path means "a generator that forgets to stream cannot exist,
and a streaming twin has nowhere to live" — the reference kept ten `@register_strategy` and ten
`@register_streaming_strategy` sites symmetric by hand, with no test asserting it, and
`step-back`'s streaming twin silently became a different technique.

**The cost of always streaming, named rather than discovered.** `LLMProvider.stream` yields
text and nothing else, so a `Completion` built here carries `finish_reason=""` — the vendor's
own word for why generation stopped does not survive. That is acceptable *because the taxonomy
carries the same facts as classes*: a content-filter refusal is an `LLMContentFilterError` and
a truncation is a provider's own concern, so nothing downstream has to string-match a finish
reason to behave correctly. `LLMProvider.complete` remains the contract member a provider
implements and a library caller may call directly; this client does not use it.

**Every provider call goes through `weft_kernel.seam.wrap`.** The client runs a plugin outside
`Runner`, which is exactly the case `weft_cli.ask` already set the precedent for: the span,
the error attribution, the blocking-call guard and the transient strip are the seam's, and
"if you find yourself writing a span by hand, stop."

**Nothing but an `LLMError` escapes.** Anything else a provider lets out is wrapped in
`LLMProviderFaultError` naming the provider — `.phase2-design.md` §7's first enforcement of
"a taxonomy nobody catches is documentation". `CancelledError` is a `BaseException` and is
untouched by every `except Exception` in this file, by construction.

**Task 3.10 adds a fifth thing assembled here: the loop-breaker.** `weft_llm.loop_guard.
detect_generation_loop` needs the whole answer accumulated so far on every call, and `complete`
already builds exactly that (`parts`, joined) before emitting to the sink — the only place in
this tree holding that shape on every token, which is why the guard attaches inside `complete`'s
own accumulation loop rather than living in a `TokenSink` (`reference/study/08-salvage.md` §T1.12,
lifted per `01` → Phase 3 **Lift**). A detected loop raises `LLMGenerationLoopError` — an
`LLMPermanentError`, so it takes the same `except LLMError: raise` path a provider's own errors
do — rather than quietly returning a truncated `Completion`; `weft_cli.cli.run_command` turns
that raise into `TokenSink.close(reason=...)`, so a reader is told the stream was cut short
rather than left to mistake it for one that finished cleanly.
"""

from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import cast

from weft_kernel.context import Context
from weft_kernel.payload import NothingToProduce, Outcome, Produced
from weft_kernel.registry import Registry, unwrap_factory
from weft_kernel.seam import wrap
from weft_llm.contract import LLM, LLMProvider, NativeStructured, TokenSink
from weft_llm.errors import (
    LLMError,
    LLMGenerationLoopError,
    LLMProviderFaultError,
    NativeStructuredUnsupportedError,
)
from weft_llm.loop_guard import LoopGuardConfig, detect_generation_loop
from weft_llm.models import ModelRef, find_runtime_match, model_ref
from weft_llm.payload import Completion, Rendered, TokenChunk
from weft_llm.retry import RetryPolicy, with_retry
from weft_llm.roles import LLMRoles

#: The contract name the seam stamps on every span and every attributed error raised through
#: this client. Written once, here, rather than at each of the three call sites.
_CONTRACT = "LLMProvider"


class NullSink:
    """A `TokenSink` that discards. The default, so no plugin ever needs a `try`.

    `.phase2-design.md` §13 item 7 leaves `PrintingSink` to a Phase 3 sequencing call and
    settles this half: "Phase 2 ships `NullSink` and the client-side emit path." Discarding is
    not a fallback — a run nobody is watching genuinely has nowhere to put tokens, and the
    alternative (no sink at all) would put a `try` in every caller.
    """

    async def emit(self, chunk: TokenChunk) -> None:
        """Discards `chunk`. Deliberately not buffered — nothing would ever read the buffer."""
        del chunk

    async def close(self, *, reason: str | None = None) -> None:
        """Nothing was opened. Present because the contract requires it of every sink."""
        del reason


class _Bound:
    """One role's resolved answer: the provider to call, the model to name, who to blame."""

    def __init__(self, *, provider: LLMProvider, raw: object, ref: ModelRef, distribution: str):
        self.provider = provider
        #: The instance *before* retry wrapped it, kept only so `close` reaches the real one
        #: exactly once when two roles share a provider.
        self.raw = raw
        self.ref = ref
        self.distribution = distribution


class LLMClient:
    """Resolves a role to a provider and a model at call time, and answers through it.

    Satisfies `weft_llm.contract.LLM` structurally — this class never imports it as a base,
    the same path every plugin in this tree takes with its own contract.

    **Providers are built once per provider name, not once per role.** Two roles naming the
    same provider with different models share one instance and one connection pool, which is
    the shape `LLMProvider`'s own docstring argues for: "`model` is a per-call argument, not
    constructor state … the same account, many models".
    """

    def __init__(
        self,
        *,
        registry: Registry,
        roles: LLMRoles,
        retry: RetryPolicy | None = None,
        loop_guard: LoopGuardConfig | None = None,
    ) -> None:
        self._registry = registry
        self._roles = roles
        self._retry = retry if retry is not None else RetryPolicy()
        self._loop_guard = loop_guard if loop_guard is not None else LoopGuardConfig()
        self._bound: dict[str, _Bound] = {}
        #: Every provider name this deployment mapped — what makes a `provider/model` prefix
        #: recognisable as a prefix rather than half of a model id. See `weft_llm.models`.
        self._provider_names = frozenset(mapping.provider for mapping in roles.roles.values())

    async def complete(self, rendered: Rendered, *, role: str, ctx: Context) -> Outcome[Completion]:
        """Continue `rendered`'s conversation under `role`, streaming every chunk to the sink."""
        bound = self._bind(role)
        sink = ctx.require(TokenSink)

        async def run() -> Outcome[Completion]:
            parts: list[str] = []
            try:
                async for chunk in bound.provider.stream(
                    rendered.conversation, model=bound.ref.model, ctx=ctx
                ):
                    parts.append(chunk)
                    await sink.emit(TokenChunk(role=role, text=chunk))
                    # Task 3.10: `parts` already holds the whole answer accumulated so far —
                    # exactly the cumulative-text contract `weft_llm.loop_guard` requires — so
                    # this is where the guard attaches rather than inside a `TokenSink`, which
                    # only ever sees one chunk at a time. The chunk that revealed the loop has
                    # already been emitted above, so a reader still sees it before the stream
                    # stops; nothing after it is generated or shown.
                    accumulated = "".join(parts)
                    if detect_generation_loop(accumulated, config=self._loop_guard):
                        raise self._loop_detected(bound, role, accumulated)
            except LLMError:
                raise
            except Exception as fault:
                raise self._fault(bound, role, fault) from fault
            text = "".join(parts)
            if not text:
                # Never an empty `Produced` — the reference trap every contract in this tree
                # documents. A model that answered with nothing did not answer.
                return NothingToProduce(
                    reason=(
                        f"provider '{bound.ref.provider}' returned no text for role '{role}' "
                        f"on model '{bound.ref.model or '(provider default)'}'"
                    )
                )
            return Produced(value=Completion(text=text, model=bound.ref.model, finish_reason=""))

        return await self._sealed(bound, role, run)()

    async def complete_structured(
        self, rendered: Rendered, schema: Mapping[str, object], *, role: str, ctx: Context
    ) -> Outcome[Completion]:
        """Tier 1 of the cascade: ask the vendor to answer *in* `schema` and check it itself.

        Not streamed. A partial JSON document displayed as it arrives is noise to a reader and
        unparseable to anything else, and the cascade's caller wants a typed value, not tokens.
        """
        bound = self._bind(role)
        native = bound.provider
        if not isinstance(native, NativeStructured):
            raise NativeStructuredUnsupportedError(
                f"provider '{bound.ref.provider}' (role '{role}') does not offer native "
                f"structured output. Ask `native_structured_available('{role}')` first, or "
                f"call the structured-output cascade, which steps down for you.",
                provider=bound.ref.provider,
                model=bound.ref.model,
            )

        async def run() -> Outcome[Completion]:
            try:
                return await native.complete_structured(
                    rendered.conversation, schema, model=bound.ref.model, ctx=ctx
                )
            except LLMError:
                raise
            except Exception as fault:
                raise self._fault(bound, role, fault) from fault

        return await self._sealed(bound, role, run)()

    async def native_structured_available(self, role: str) -> bool:
        """Whether `role`'s provider satisfies `NativeStructured` — derived, never declared."""
        return isinstance(self._bind(role).provider, NativeStructured)

    async def close(self) -> None:
        """Close every provider this client built, once each, in the order they were built."""
        for bound in self._bound.values():
            await bound.provider.close()

    # --- resolution ---------------------------------------------------------------------

    def _bind(self, role: str) -> _Bound:
        """`role` → the provider instance and the model string a call under it uses.

        Every refusal on this path is loud and names its options: an unmapped role names every
        mapped role (`UnmappedLLMRoleError`), an unregistered provider names every registered
        one (the registry's own `UnknownPluginError`), and a model a provider's declared
        catalogue does not offer names the catalogue (`UnknownModelError`).
        """
        mapping = self._roles.resolve(role)
        entry = self._registry.entry(LLMProvider, mapping.provider)
        ref = model_ref(
            provider=mapping.provider, requested=mapping.model, providers=self._provider_names
        )
        catalogue = _declared_catalogue(entry.factory)
        if catalogue and ref.model:
            ref = find_runtime_match(ref, catalogue)
        cached = self._bound.get(mapping.provider)
        if cached is not None:
            return _Bound(
                provider=cached.provider,
                raw=cached.raw,
                ref=ref,
                distribution=cached.distribution,
            )
        raw = entry.factory(None)
        bound = _Bound(
            provider=with_retry(cast("LLMProvider", raw), self._retry),
            raw=raw,
            ref=ref,
            distribution=entry.distribution,
        )
        self._bound[mapping.provider] = bound
        return bound

    def _sealed(
        self, bound: _Bound, role: str, run: Callable[[], Awaitable[Outcome[Completion]]]
    ) -> Callable[[], Awaitable[Outcome[Completion]]]:
        """`run`, through the registration seam, attributed to the provider that will answer."""
        return wrap(
            run,
            distribution=bound.distribution,
            contract=_CONTRACT,
            plugin=bound.ref.provider,
            stage=f"llm:{role}",
        )

    def _fault(self, bound: _Bound, role: str, fault: Exception) -> LLMProviderFaultError:
        return LLMProviderFaultError(
            f"provider '{bound.ref.provider}' (role '{role}') raised "
            f"{type(fault).__name__}: {fault}. That is not an LLMError, so nothing downstream "
            f"could have caught it by class — it is a defect in the provider adapter, not a "
            f"failure mode of the model.",
            provider=bound.ref.provider,
            model=bound.ref.model,
        )

    def _loop_detected(self, bound: _Bound, role: str, accumulated: str) -> LLMGenerationLoopError:
        return LLMGenerationLoopError(
            f"provider '{bound.ref.provider}' (role '{role}') was generating a repeating span "
            f"and was stopped after {len(accumulated)} characters rather than left to keep "
            f"filling the terminal. This is a loop-breaker for a model that got stuck, not a "
            f"judgment about the content — retrying the identical prompt against the same "
            f"model is likely to loop again; try a different prompt, role, or model.",
            provider=bound.ref.provider,
            model=bound.ref.model,
        )


def llm_service(
    *,
    registry: Registry,
    roles: LLMRoles,
    retry: RetryPolicy | None = None,
    loop_guard: LoopGuardConfig | None = None,
) -> LLMClient:
    """Build the run's `LLM`. This pack's own constructor, per `.phase2-design.md` §7.

    "Each pack builds its own service constructor … so a library caller is not forced through
    the CLI." `weft_cli.run_services.build_services` calls this one and adds the result to the
    run's `ServiceRegistry`; an embedding host application calls it directly with a role table
    it built itself.
    """
    return LLMClient(registry=registry, roles=roles, retry=retry, loop_guard=loop_guard)


def _declared_catalogue(factory: Callable[..., object]) -> Sequence[str]:
    """A provider's declared `models`, read the documented way — through `unwrap_factory`.

    `functools.partial` does not proxy attribute access, so a pack binding its settings at
    registration (`partial(Provider, settings)` — `weft-store`'s shape) would otherwise
    advertise nothing and the model check would silently never run.

    A provider declaring nothing gets `()`, which turns the check off rather than refusing
    every model: a name this code cannot check must be passed through, not guessed at.
    """
    declared = getattr(unwrap_factory(factory), "models", ())
    if isinstance(declared, str) or not isinstance(declared, Sequence):
        return ()
    return [str(entry) for entry in cast("Sequence[object]", declared)]


#: Stated so a reader of this module sees that the service Protocol is satisfied structurally,
#: the same way a plugin satisfies its contract, and so a checker verifies it once here rather
#: than at every `ServiceRegistry.add(LLM, ...)` call site.
_: type[LLM] = LLMClient
