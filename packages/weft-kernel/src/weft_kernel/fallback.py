"""`try_in_order` — the fallback combinator, over any contract at all.

`04` → the `_try_extractors` row: a fallback-chain executor belongs
in the kernel "as a combinator", because **it composes plugins rather than
doing work**. Nothing here inspects a payload, imports a capability or knows
what a document is; it matches on the `Outcome` type a contract already
defines and calls the next candidate or stops. That is what lets one
implementation serve extraction today and a store, an embedder or a retriever
tomorrow without a line changing.

A separate module rather than a method on `Runner`, for two reasons that are
not style: its cost is visible on its own line in fitness function 3's
per-file numbers, and it is testable with no `Runner`, no `Registry` and no
resolved pipeline — which is what makes the three-outcome table below a
checked fact rather than a claim about the runner.

**A `fail_silently` channel has no equivalent here, and this module is where
that is enforced.** Such a channel returns an empty result indistinguishable
downstream from a successfully-parsed empty document (`payload/outcome.py`) —
the shape a two-state success/failure model is forced into once the real
problem has three states. `Outcome` has the third, and `02` §1 already assigns
the meanings:

- **`Produced` — stop, return it.** Success is contract-defined, never guessed at
  by looking inside the value the way `fail_silently` had to.
- **`NothingToProduce` — stop, return it unchanged.** `02` §1, on a backend that
  legitimately extracted nothing: it can now say so, "**and it stops the chain**".
  *"I looked, and there is nothing here"* is a claim a second backend cannot
  improve on.
- **`Failed` — record it, try the next.** *"I could not see it"* — another backend
  might.
- **raises `WeftError` — record it, try the next.** See below.
- **raises `BlockingCallError` — stop, and let it out.** See below.

**Catching `WeftError` is the one deliberate breadth in this module.** Every
candidate reaches here already wrapped by `weft_kernel.seam.wrap`, which turns
anything a plugin lets escape into a `WeftError` with `__cause__` preserved and
the pack, contract, plugin and stage attributed. So the broad tolerance a
chain over third-party format libraries genuinely needs is declared once, at
the combinator, against the one class the seam guarantees — rather than as a
blind `except Exception` inside every backend, buried where no reviewer of
the combinator would ever see it. `CancelledError`, `KeyboardInterrupt` and
`SystemExit` are `BaseException`, so they are never caught here: cancellation
propagates by construction, not by an added clause.

**`BlockingCallError` is the one exception to that breadth, and it is the
kernel's own, not a backend's.** The seam arms `weft_kernel.blocking.guard`
around every candidate, so fitness function 7(b) raises it from *inside* the
offending call — and it subclasses `WeftError`, so the clause above would file
it as *"this backend could not do its job"* and let the next candidate answer.
That is a `fallback:` line silently opting a stage out of the colour rule: the
run exits with a success, the refusal list is discarded, and with the default
no-op tracer the violation is named nowhere. The distinction the chain is
allowed to walk past is a backend's report about a **document**; a report that
the plugin itself broke the runtime contract is not a refusal to be tried
around, so it propagates untouched. Any future kernel-raised diagnostic of a
contract violation belongs beside it here.

**The author rule that makes the `NothingToProduce` row honest**, stated on
`Attempt` too because a backend author is who has to obey it:

> Return `NothingToProduce` only when you can distinguish "there is nothing
> here" from "I could not see it". If your backend cannot tell those apart for
> this input, return `Failed`.

`weft-pdf` ships both cases as unit tests — a page with a text layer drawing no
glyphs against a page with no text and an embedded image — so the distinction
the chain rests on is checked rather than promised.
"""

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass

from weft_kernel.blocking import BlockingCallError
from weft_kernel.context import Context
from weft_kernel.errors import WeftError
from weft_kernel.payload import Failed, Outcome


@dataclass(frozen=True, slots=True, kw_only=True)
class Attempt[In, Out]:
    """One candidate in a chain: a name, and an already-seam-wrapped call.

    `run` is expected to carry its own span, attribution, blocking guard and
    transient stripping — the caller builds it through `weft_kernel.seam.wrap`
    — which is why **this module writes no span of its own**. A chain of three
    backends produces three spans, each attributed to the backend that
    actually ran, and a fourth wrapping span naming only the chain would say
    less than the three already do.

    `name` is the plugin name, not the stage id: the stage is one position and
    every candidate fills it, so it is the *name* that answers the question a
    reader of the trace or of an exhausted chain's reason is asking — which
    backend answered.
    """

    name: str
    run: Callable[[In, Context], Awaitable[Outcome[Out]]]


async def try_in_order[In, Out](
    payload: In,
    ctx: Context,
    *,
    stage: str,
    attempts: Sequence[Attempt[In, Out]],
) -> Outcome[Out]:
    """Try each of `attempts` in order until one answers something other than a refusal.

    `attempts` is `[primary, *fallbacks]` — the stage's own `use:` plugin is
    simply the first candidate, so there is no special-cased primary path that
    could diverge from the fallback path as either changes. Ordering is the
    caller's data (`StageDeclaration.fallback`, written in a document), never a
    constructor sequence compiled in here.

    Returns the first `Produced` or `NothingToProduce`. When every candidate
    refused, returns a single `Failed` naming **every** one of them and what
    each said, in order — refusals accumulate and are reported together, because
    a chain that reports only its last candidate's reason hides the fact that
    the first one was the interesting failure.

    Raises `BlockingCallError` rather than recording it — see the module
    docstring: a chain is tolerant of what a backend says about a *document*,
    never of a candidate breaking the runtime contract.
    """
    if not attempts:
        raise ValueError(
            f"stage '{stage}' was given an empty chain, so there is nothing to try. A chain "
            f"is [primary, *fallbacks] and its first entry is the stage's own plugin; an "
            f"empty one is a caller's bug, and answering Failed would file it as a backend's."
        )

    refusals: list[str] = []
    for attempt in attempts:
        try:
            outcome = await attempt.run(payload, ctx)
        except BlockingCallError:
            # Before the broad clause, and never recorded: the seam's guard reports that
            # this candidate broke the runtime contract, not that it met a document it
            # could not read. See the module docstring's fifth row.
            raise
        except WeftError as exc:
            refusals.append(f"'{attempt.name}' raised: {exc}")
            continue
        if isinstance(outcome, Failed):
            refusals.append(f"'{attempt.name}' failed: {outcome.reason}")
            continue
        # `Produced` and `NothingToProduce` both stop the chain, and they are returned by
        # the same line on purpose: `Failed` is the only refusal, and a reader looking for
        # what continues a chain finds exactly one answer rather than two rules to compare.
        return outcome

    return Failed(
        reason=(
            f"every candidate for stage '{stage}' refused, in order: {'; '.join(refusals)}. "
            f"No backend produced anything, and none of them reported the document as "
            f"legitimately empty."
        )
    )
