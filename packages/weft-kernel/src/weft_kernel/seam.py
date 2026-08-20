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
5. **The NUL-byte sanitiser** — see `_sanitize_control_bytes` below, riding
   the same `Produced` → `Node` / `tuple` / `list` walk `_strip_transient`
   already performs, immediately after it. `docs/build-ledger.md` → **2.34**
   settles where this lives, against two alternatives, with evidence:

   - **Not in an extractor pack.** Eight sites across `packages/` build a
     `Node` from text that came from outside the process — `weft_extract/
     text.py:80`, `weft_pdf/document.py:205`, `weft_chunk/fixed_size.py:145`,
     `weft_clean/dictionary_spacing.py:117`, `weft_clean/hyphenation.py:70`,
     `weft_clean/whitespace.py:63`, `weft_clean/table_linearizer.py:79`,
     `weft_index/raptor.py:254`. A fix in one extractor covers two of the
     eight — the reference's own twelve-call-site fragility
     (`reference/study/08-salvage.md` §T1.16, *"the trap"*), reproduced here with
     a smaller number but the identical shape: a new construction path that
     forgets the call reaches storage uncleaned.
   - **Not in a store.** `weft_store/pgvector_store.py`'s `weft_nodes.content`
     column is `TEXT NOT NULL` (`:138`) and Postgres refuses a NUL byte in it;
     a second store backend sending the same payload over its own wire
     protocol would not refuse it. Fixing this at a store means the same
     corpus indexes under one backend and fails under another — the exact
     shape this task line refuses ("refused by whichever backend happens to
     notice").
   - **The seam already owns this class of concern.** Spans, error
     attribution and transient stripping all attach here rather than at a
     rule an author must remember (`CLAUDE.md` → *The rules that are already
     settled*), this function already knows what a `Node` is, and `wrap`'s
     own signature already carries `distribution`, `contract` and `plugin` —
     so the reference's diagnostic triple (source, chunk index, extractor name;
     §T1.16, *"the diagnostic is the point, not the strip"*) is structural
     here, read off the span's own attributes, rather than four keyword
     arguments an author has to remember to pass at every call site.

   **NUL becomes a space, never a deletion** — the reference's own choice
   (§T1.16's `_strip_nul`), and this codebase has a live reason the reference
   only had in principle: `weft_chunk.payload.ChunkOffset` records a
   character offset into a parent's content, so deleting a byte would
   silently shift every offset recorded downstream of the node being
   cleaned. A space is one character for one character; every offset already
   recorded against this content stays correct.

   **Scope is `Node.content` and the `str`-typed fields of whatever
   `ExtModel`s `Node.ext` carries** — `weft_store/pgvector_store.py`'s
   `ext` column is `JSONB NOT NULL` (`:141`), and Postgres JSONB refuses a
   NUL byte in a string value exactly as `TEXT` does, so an extension model
   that ever carries verbatim extractor output is `content`'s twin, not a
   narrower case. No current first-party `ExtModel` does — `weft_pdf.
   PdfPages` (`weft_pdf/document.py:94-131`) is the one built directly from
   what a PDF backend reads, and its two fields are `backend: str` (a
   plugin name, never extractor output) and `starts: tuple[int, ...]`
   (offsets, not text) — so today's corpus exercises `content` only. The
   walk still covers `ext` because the JSONB fact above is about the column,
   not about any one model's current fields, and because covering it costs
   one `isinstance` check per field on a namespace that already changed,
   never a maintained list of which namespaces to check (`reference/study/
   08-salvage.md` §T1.20(a)'s recorded lesson about the transient scrub
   applies unchanged: the invariant is "ext is safe to store", not the name
   of whichever field happens to hold it).
6. **Never with a name list.** Every `ExtModel` namespace `Node.ext` carries
   is walked by `type(model).model_fields`, the same field-introspection
   idiom `weft_kernel.pipeline` and `weft_kernel.resolution` already use
   elsewhere in this distribution — never a maintained tuple of which
   fields are known to carry text.

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

**`guard_blocking_calls`, added by `weft-cli` task 3.4 for a caller outside
`Runner`'s own reach.** `docs/build-ledger.md` 3.2 tried running a
`weft_command.contract.Command` invocation through this function unchanged
and reverted: `weft index`'s synchronous filesystem walk tripped concern 4,
which exists because a blocking `Stage` starves an event loop *other stages
share* — a `Command` is CLI orchestration invoked once per invocation or
REPL turn, with nothing else scheduled on that loop to starve, so the guard
was a false positive for it rather than a caught defect. 3.4's own analysis
(recorded in full in its `docs/build-ledger.md` entry) rejected two other
shapes for this fact: a second, hand-written span-and-attribution wrapper in
`weft_cli` (a second implementation of a concern this module already owns,
free to drift from it) and applying the guard unconditionally (the reverted
status quo, which left every `Command` invocation with no attribution at
all — a rule an author had to remember, which CLAUDE.md refuses). A keyword
defaulting to `True` keeps every existing caller's behaviour identical by
construction; only `weft_cli.cli.run_command` passes `False`, and only
concern 4 is affected — spans, attribution and `Produced` post-processing
run exactly as they do when the guard is armed.
"""

import contextlib
from collections.abc import Awaitable, Callable, Sequence
from typing import cast

from opentelemetry import trace
from opentelemetry.trace import SpanKind
from pydantic import ValidationError

from weft_kernel import blocking
from weft_kernel.errors import WeftError
from weft_kernel.payload import ExtModel, Node, Outcome, Produced

#: The span attribute a NUL count is recorded under — see `_sanitize_control_bytes`.
_NUL_BYTES_ATTRIBUTE = "weft.nul_bytes_removed"

_tracer = trace.get_tracer("weft_kernel")

_FlushFn = Callable[[], Awaitable[None]]


def wrap[**P, T](
    run: Callable[P, Awaitable[Outcome[T]]],
    *,
    distribution: str,
    contract: str,
    plugin: str,
    stage: str | None = None,
    guard_blocking_calls: bool = True,
) -> Callable[P, Awaitable[Outcome[T]]]:
    """Wrap `run` so every call through it carries spans, attribution, stripping and the guard.

    `run` is any async callable returning an `Outcome` — a stage's `run`
    method, bound, is the intended shape, but this function never asserts
    that: it calls what it is given and reacts only to what comes back.
    `stage` names the pipeline position this call fills, when the caller has
    one to give — the runner (`06` step 6) always does. A caller with no
    pipeline concept (registration, step 3) may omit it and falls back to
    `f"{contract}:{plugin}"`, the label available at registration time.

    `guard_blocking_calls` defaults to `True` for every existing caller — see
    the module docstring's own paragraph on why and who passes `False`.
    """
    stage_label = stage if stage is not None else f"{contract}:{plugin}"

    async def _wrapped(*args: P.args, **kwargs: P.kwargs) -> Outcome[T]:
        with _tracer.start_as_current_span(stage_label, kind=SpanKind.INTERNAL) as span:
            span.set_attribute("weft.pack", distribution)
            span.set_attribute("weft.contract", contract)
            span.set_attribute("weft.plugin", plugin)
            # A fresh context manager per call, never hoisted above `_wrapped`: a
            # `@contextmanager`-built one (`blocking.guard`) can only be entered once, and
            # `_wrapped` itself is reusable across many invocations.
            guard_cm = (
                blocking.guard(stage_label) if guard_blocking_calls else contextlib.nullcontext()
            )
            with guard_cm:
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
            outcome, nul_count = _sanitize_control_bytes(_strip_transient(outcome))
            span.set_attribute(_NUL_BYTES_ATTRIBUTE, nul_count)
        return outcome

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


def _sanitize_control_bytes[T](outcome: Outcome[T]) -> tuple[Outcome[T], int]:
    """Replace every NUL byte a produced `Node`'s `content` or ext `str` fields carry.

    Returns the (possibly unchanged) outcome and how many bytes were found.

    Same shape as `_strip_transient` immediately above — `Produced` → `Node`
    / `tuple` / `list`, anything else untouched — because it walks the exact
    same values, one step later. See the module docstring, concern 5, for
    why this lives here rather than in an extractor or a store, why the
    replacement is a space rather than a deletion, and why `ext` is in scope
    beside `content`. A container or a `Node` that needed no change is
    returned as the same object the caller passed in — a corpus with no NUL
    bytes, the overwhelming case, costs one `"\\x00" in s` scan per string and
    not one rebuild.
    """
    if not isinstance(outcome, Produced):
        return outcome, 0

    value = outcome.value
    if isinstance(value, Node):
        cleaned, count = _sanitize_node(value)
        return (outcome if count == 0 else Produced(value=cast(T, cleaned))), count
    if isinstance(value, tuple):
        items = cast("tuple[object, ...]", value)
        cleaned_items, count = _sanitize_items(items)
        return (outcome if count == 0 else Produced(value=cast(T, tuple(cleaned_items)))), count
    if isinstance(value, list):
        entries = cast("list[object]", value)
        cleaned_items, count = _sanitize_items(entries)
        return (outcome if count == 0 else Produced(value=cast(T, cleaned_items))), count
    return outcome, 0


def _sanitize_items(items: Sequence[object]) -> tuple[list[object], int]:
    """`_sanitize_node` applied to every `Node` in `items`; anything else passes through."""
    total = 0
    cleaned: list[object] = []
    for item in items:
        if isinstance(item, Node):
            node, count = _sanitize_node(item)
            cleaned.append(node)
            total += count
        else:
            cleaned.append(item)
    return cleaned, total


def _sanitize_node(node: Node) -> tuple[Node, int]:
    """`node` with every NUL in `content` and every ext model's `str` fields turned to a space.

    Rebuilds through `Node._replace` — the same revalidating path
    `without_transient` uses — only when something actually changed, and
    only the fields that did: a node with a clean `content` but a dirty ext
    field does not get its content re-validated for nothing, and the reverse.

    The walk is `node.ext` specifically — the same "`Node` and nothing wider"
    reach `_strip_transient` already states above. `weft_retrieve.payload`'s
    `QuerySet` and `Candidates` carry their own `ext: ExtMap` and are out of
    scope here, unchanged from that pre-existing rule.
    """
    cleaned_content, content_count = _clean_str(node.content)

    ext_updates: dict[str, ExtModel] = {}
    ext_count = 0
    for namespace, model in node.ext.items():
        cleaned_model, model_count = _sanitize_ext_model(model)
        if model_count:
            ext_updates[namespace] = cleaned_model
            ext_count += model_count

    total = content_count + ext_count
    if total == 0:
        return node, 0

    updates: dict[str, object] = {}
    if content_count:
        updates["content"] = cleaned_content
    if ext_updates:
        updates["ext"] = {**node.ext, **ext_updates}
    # `Node._replace` is kernel-internal, not a third-party API — this module is the one
    # other place in the same distribution `node.py` names as the sanctioned revalidating
    # rebuild path, alongside `with_ext`/`without_transient`, which are both defined on
    # `Node` itself and so need no such suppression.
    return node._replace(**updates), total  # pyright: ignore[reportPrivateUsage]


def _sanitize_ext_model(model: ExtModel) -> tuple[ExtModel, int]:
    """`model` with every `str`-typed field's NUL bytes turned to a space, by field introspection.

    `type(model).model_fields` is walked rather than a maintained list of
    which fields carry text — the module docstring's concern 6 — so a pack's
    own `ExtModel` subclass needs no registration here to be covered; it is
    covered the moment it declares a `str` field.

    Scoped to a field whose *runtime value* is a `str` — not `tuple[str, ...]`
    or `list[str]`, checked by `isinstance` rather than by the field's
    annotation. `docs/build-ledger.md` → 2.34 scopes this task to "`Node.content`
    and the `str`-typed fields of the `ExtModel`s in `Node.ext`" literally; no
    shipped `ExtModel` as of this task holds a string collection built from
    verbatim extractor text, so widening to collections has no motivating case
    yet and is left for whichever future field needs it, named at that point
    rather than guessed at here.

    Rebuilt through `model_validate`, never `model_copy(update=...)` — the same
    choice `node.py`'s `Node._replace` makes, and for its own stated reason:
    `model_copy(update=...)` skips validation entirely, so it would let this
    substitution smuggle a NUL-cleaned value past a pack's own `Field` or
    `field_validator` guard. Unlike `_replace`, a validation failure here is
    not the caller's mistake to see raw: nothing upstream asked for this
    rebuild, so `ValidationError` is caught and re-raised naming the model,
    the cause, and carrying pydantic's own field-level detail, rather than
    surfacing as an unexplained validation error out of a sanitiser no caller
    invoked directly.
    """
    updates: dict[str, str] = {}
    total = 0
    for field_name in type(model).model_fields:
        if not isinstance(value := getattr(model, field_name), str):
            continue
        cleaned, count = _clean_str(value)
        if count:
            updates[field_name] = cleaned
            total += count
    if total == 0:
        return model, 0
    try:
        return type(model).model_validate({**model.__dict__, **updates}), total
    except ValidationError as exc:
        raise WeftError(f"NUL sanitisation left {type(model).__name__} invalid: {exc}") from exc


def _clean_str(value: str) -> tuple[str, int]:
    """`value` with every NUL byte replaced by a space, and how many there were.

    The early return is the cost discipline the module docstring promises: a
    clean string — the overwhelming majority — costs one C-level containment
    check and nothing else, never a `.replace` call that would return an
    identical string.
    """
    if "\x00" not in value:
        return value, 0
    return value.replace("\x00", " "), value.count("\x00")
