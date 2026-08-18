"""`wrap` — the registration seam every stage's execution passes through.

Specified in `docs/06-phase-0-build.md` step 3 and `docs/01-high-level-plan.md`
→ *Fitness functions*. Four cross-cutting concerns attach here, applied
without the author asking, because the reference measured what the alternative
costs: every concern its machinery applied automatically held perfectly, and
every concern an author had to remember decayed — spans to 58 hand-written
call sites, 38 of 54 off-convention; observability lost entirely on an
untraced ingest stage. `wrap` is built *before* there is a `Stage` protocol,
a `Context`, or a single published capability contract (those are steps 4, 6
and 7) — deliberately, so nothing downstream ever has the chance to wrap a
call by hand. It is generic over what it wraps: a plain async callable and
three identifying strings (`distribution`, `contract`, `plugin`) are the
whole surface, supplied by whatever calls `wrap` — this module never chooses,
enumerates or hard-codes any of them, so it names no capability of its own
and assumes no pipeline concept.

The four concerns:

1. **Span wrapping**, via `opentelemetry-api`. `docs/02-extension-model.md`
   → *What a plugin receives*: "span name and `span_kind` are derived at the
   registration seam from contract and plugin name" — never written by a
   stage. Every span uses `SpanKind.INTERNAL`: the seam cannot know whether a
   given contract is a store, a client, or neither, so a per-capability kind
   would mean the kernel naming a capability. `SpanKind` beyond "internal
   pipeline step" is a pack's own concern, added inside its stage if it wants
   one.
2. **Error attribution**, naming the pack, contract, plugin and stage — see
   `errors.py`. An exception a pack already raised as `WeftError` is not
   replaced; only the four fields it left as `None` are filled in, because a
   library re-raising with its own attribution knows more than the seam
   does. Anything else escaping is wrapped fresh, `__cause__` preserved, so
   no traceback is hidden. `CancelledError` is a `BaseException`, not an
   `Exception` — it is never caught here, so it is never at risk of being
   swallowed or rewrapped, by construction rather than by an added clause.
3. **`__transient__` stripping** — see `payload/ext.py` and
   `payload/node.py`. A produced `Node`, or a list/tuple of them, has every
   transient namespace stripped before the result leaves this function. This
   is the type-level fact `Node.without_transient` exists to apply, and the
   reference needed a whole pipeline stage (its "4.5") to do it by hand.
4. **The categorical blocking-call detector**, fitness function 7(b) — see
   `blocking.py`. Scoped to exactly the `await` below, so a blocking call
   made anywhere else — a fixture, an import, a factory building an instance
   — is out of scope by construction, not by an exclusion list.

**Where `distribution`, `contract` and `plugin` come from.** `wrap` does not
derive them: they are supplied by whatever calls it, exactly as
`Registry.add` takes `distribution` as a parameter rather than discovering it
(see `registry.py`). Discovery (step 5) is what will thread a pack's own
distribution name through; this module has no opinion on where that string
originates, only that it is attributed once it is known.

**`stage` is an optional parameter, defaulted for the caller that has no
pipeline concept.** `docs/06-phase-0-build.md` step 3 asks for "error
attribution naming the stage and the distribution." A pipeline *position* —
which slot in an ordered list a plugin fills — was not knowable at
registration, before step 6's runner existed to resolve a pipeline; `wrap`
therefore falls back to `f"{contract}:{plugin}"`, the one identifying label
available at registration time, whenever a caller does not supply `stage`
itself. **Step 6's runner is that caller**: it passes the resolved
`StageSpec.id`, so two positions in one pipeline that happen to name the same
plugin now produce distinguishable spans and error attribution — closing the
pipeline-position gap this paragraph used to describe as open.

**`wrap_flush`, below, is the same seam for a plugin's `flush()`.** `flush`
returns nothing an `Outcome` could decide, so it cannot share `wrap`'s
signature — there is nothing for `_strip_transient` to strip — but the other
three concerns still apply: a span, the blocking-call guard, and, for a bare
`WeftError` a pack raises itself, the same four-field attribution `wrap`
gives `run()`.
"""

from collections.abc import Awaitable, Callable
from typing import cast

from opentelemetry import trace
from opentelemetry.trace import SpanKind

from weft_kernel import blocking
from weft_kernel.errors import WeftError
from weft_kernel.payload import Node, Outcome, Produced

_tracer = trace.get_tracer("weft_kernel")

_FlushFn = Callable[[], Awaitable[None]]


def wrap[**P, T](
    run: Callable[P, Awaitable[Outcome[T]]],
    *,
    distribution: str,
    contract: str,
    plugin: str,
    stage: str | None = None,
) -> Callable[P, Awaitable[Outcome[T]]]:
    """Wrap `run` so every call through it carries spans, attribution, stripping and the guard.

    `run` is any async callable returning an `Outcome` — a stage's `run`
    method, bound, is the intended shape, but this function never asserts
    that: it calls what it is given and reacts only to what comes back.
    `stage` names the pipeline position this call fills, when the caller has
    one to give — the runner (`06` step 6) always does. A caller with no
    pipeline concept (registration, step 3) may omit it and falls back to
    `f"{contract}:{plugin}"`, the label available at registration time.
    """
    stage_label = stage if stage is not None else f"{contract}:{plugin}"

    async def _wrapped(*args: P.args, **kwargs: P.kwargs) -> Outcome[T]:
        with _tracer.start_as_current_span(stage_label, kind=SpanKind.INTERNAL) as span:
            span.set_attribute("weft.pack", distribution)
            span.set_attribute("weft.contract", contract)
            span.set_attribute("weft.plugin", plugin)
            with blocking.guard(stage_label):
                try:
                    outcome = await run(*args, **kwargs)
                except WeftError as exc:
                    _attribute(
                        exc,
                        distribution=distribution,
                        contract=contract,
                        plugin=plugin,
                        stage=stage_label,
                    )
                    raise
                except Exception as exc:
                    raise WeftError(
                        f"'{stage_label}' failed: {exc}",
                        pack=distribution,
                        contract=contract,
                        plugin=plugin,
                        stage=stage_label,
                    ) from exc
        return _strip_transient(outcome)

    return _wrapped


def wrap_flush(
    flush: _FlushFn,
    *,
    distribution: str,
    contract: str,
    plugin: str,
    stage: str,
) -> _FlushFn:
    """Wrap a plugin's `flush()` with the same span, guard and attribution `wrap` gives `run()`.

    No `_strip_transient` — `flush` returns nothing an `Outcome` could
    decide, so there is nothing to strip. `stage` is required, not optional,
    because the only caller (`06` step 6's `Runner._flush_all`) always has a
    resolved `StageSpec.id` to give it.
    """

    async def _wrapped() -> None:
        with _tracer.start_as_current_span(f"{stage}:flush", kind=SpanKind.INTERNAL) as span:
            span.set_attribute("weft.pack", distribution)
            span.set_attribute("weft.contract", contract)
            span.set_attribute("weft.plugin", plugin)
            with blocking.guard(f"{stage}:flush"):
                try:
                    await flush()
                except WeftError as exc:
                    _attribute(
                        exc,
                        distribution=distribution,
                        contract=contract,
                        plugin=plugin,
                        stage=stage,
                    )
                    raise
                except Exception as exc:
                    raise WeftError(
                        f"'{stage}' flush failed: {exc}",
                        pack=distribution,
                        contract=contract,
                        plugin=plugin,
                        stage=stage,
                    ) from exc

    return _wrapped


def _attribute(
    exc: WeftError, *, distribution: str, contract: str, plugin: str, stage: str
) -> None:
    """Fill in whichever of `exc`'s four attribution fields a pack's own raise left `None`.

    `errors.py`: a plain `WeftError` a pack raises directly has no reason to
    know its own attribution. A field the pack *did* set — a library
    re-raising with its own `plugin=`, say — is left exactly as it was.
    """
    if exc.pack is None:
        exc.pack = distribution
    if exc.contract is None:
        exc.contract = contract
    if exc.plugin is None:
        exc.plugin = plugin
    if exc.stage is None:
        exc.stage = stage


def _strip_transient[T](outcome: Outcome[T]) -> Outcome[T]:
    """Strip every `__transient__` namespace from a produced `Node`, or a list/tuple of them.

    Anything else a stage produces — a scalar, a future `Answer` — passes
    through untouched: transience is a fact about `Node.ext`, so this looks
    for `Node` and nothing wider. A list or tuple is walked item by item
    rather than gated on every item being a `Node`: a container mixing
    `Node`s with other values must not carry a `Node`'s transients through
    just because it as a whole failed an `all(...)` check — that would be a
    success path and a do-nothing path indistinguishable to the caller, the
    exact silent-fallback shape `payload/outcome.py` exists to avoid. `list`
    is walked alongside `tuple`, not just `tuple`, because a `Produced[list[Node]]`
    — the natural shape for a stage such as a chunker that emits many chunks
    — is exactly as much "a fact about `Node.ext`, in a different container"
    as a tuple is; nothing in Phase 0 restricts a stage's return shape to
    forbid it. The container type is preserved: a `list` in, a `list` out.
    """
    if not isinstance(outcome, Produced):
        return outcome

    value = outcome.value
    if isinstance(value, Node):
        return Produced(value=cast(T, value.without_transient()))
    if isinstance(value, tuple):
        items = cast("tuple[object, ...]", value)
        stripped_tuple = tuple(
            item.without_transient() if isinstance(item, Node) else item for item in items
        )
        return Produced(value=cast(T, stripped_tuple))
    if isinstance(value, list):
        entries = cast("list[object]", value)
        stripped_list = [
            item.without_transient() if isinstance(item, Node) else item for item in entries
        ]
        return Produced(value=cast(T, stripped_list))
    return outcome
