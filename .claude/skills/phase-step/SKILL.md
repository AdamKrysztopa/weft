---
name: phase-step
description: Build one step of the current phase from docs/06-phase-0-build.md — read what the step must make true, write it against the settled contracts, test it, turn on any fitness function it activates, and tick the checklist. Use whenever implementing Weft, starting or continuing a phase step, asking what to build next, or picking up work in this repository, even when the user just names a component like "the registry" or "the payload types".
---

# Build one step

Weft's phases are sequenced in `docs/06-phase-0-build.md`, and each step names **what it makes true**
rather than what it adds. That framing is the point: a step is done when a property holds, not when
files exist. Work one step at a time — they are ordered so that each one has everything it needs and
nothing it does not.

## Orient

**1. Find the step.** The checklist in `docs/README.md` is the project's position on itself; take the
first unticked item unless told otherwise. Read that step in `06`, and read the step *after* it — the
next step often reveals what the current one has to leave room for.

**2. Read what constrains it.** Do not reconstruct the design from the code; it is written down.
`01` → *The kernel boundary* decides what may be written at all, `02` §1 has the contracts and the
payload model, `02` §2 has discovery and the trust model. The decision log in `docs/README.md` says
which gates are settled.

**3. Check the traps.** `06` opens with three places Phase 0 can accidentally settle **G2**, which is
open: where embedding happens, what a pipeline is before Phase 1, and what two packs claiming one name
does. Each has a fixed minimal choice. Take it, and do not improve on it — the choices are chosen for
reversibility, not for elegance.

**4. Check the fence.** `06` → *What Phase 0 must not build* lists nine things that belong to later
phases. If the step seems to need one, re-read the step: it usually needs something smaller.

## Build

Against the settled contracts, not against instinct:

- **Async.** Every contract method is `async def`. `CancelledError` propagates untouched.
- **Frozen Pydantic returns.** No `dict[str, Any]`, `Enum` over `Literal`, native 3.12 hints.
- **Nothing cross-cutting by hand.** Spans, error attribution, transient stripping and blocking
  detection are applied by the registration seam. If you find yourself writing a span, stop — either
  the seam should do it, or you are in the wrong file.
- **Loud failure.** An unknown name says what was wanted, why it is unavailable, and what the valid
  options are. A silent fallback is worse than a crash because it produces a plausible answer.
- **The kernel names no capability.** If the thing you are writing needs the word `Extractor`,
  `Chunker` or `Store`, it does not belong in `weft-kernel`.

Tests go in the mirroring path: happy path, one edge case, one error case, AAA with one block each,
external services mocked.

## Finish

A step is not done until all of these are true:

1. `uv run poe ci-checks` is green.
2. **Any fitness function the step activates is wired and green.** `06` names them per step — 8(a) at
   step 5, 7(a) and 8(b) at step 9. Wiring one means adding it to the `ci-checks` composite in the
   same commit; fitness function 0 fails otherwise.
3. The checklist item in `docs/README.md` is ticked, and the Status block still reads true.
4. If the work changed something a document owns, that document is edited in the same commit. The
   plan and the code are meant to be true about each other.
5. The commit message says **why**, and names the step. The diff already says what.

Then run the `weft-qualities` skill against what you wrote if the step added a contract, a capability
or a config surface. It is cheaper to catch an elasticity regression now than after something depends
on it.

## When to stop instead of continuing

- **The step needs an open decision.** G2, G7, G8 and G9 are open. Say which one, and what the step
  would have to assume. Defaulting one quietly is exactly what the gates exist to prevent.
- **The kernel crosses 2,800 lines.** That is a review trigger, not a failure — but it is a
  conversation about the boundary, and the budget is never edited in the pull request that grew the
  kernel.
- **A settled decision looks wrong.** That is information, not failure, but it is a stop rather than a
  patch: re-run the session, then re-check the phases downstream, because these decisions cascade.
- **The reference has something for this.** Use `reference-lift` rather than reinventing it, and remember most
  of the inventory is rewrite-from-design rather than copy — which carries no licensing obligations
  and usually produces better code against contracts the reference never had.
