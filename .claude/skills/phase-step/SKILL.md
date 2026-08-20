---
name: phase-step
description: Build one task of the current phase from docs/build-ledger.md — read what the task must make true, write it against the settled contracts, test it, turn on any fitness function it activates, and tick the checklist. Use whenever implementing Weft, starting or continuing a phase task, asking what to build next, or picking up work in this repository, even when the user just names a component like "the registry" or "the payload types".
---

# Build one task

Weft's phases are sequenced task by task in `docs/build-ledger.md`, and each task names **what it
makes true** rather than what it adds. That framing is the point: a task is done when a property
holds, not when files exist. Work one task at a time — they are ordered so that each one has
everything it needs and nothing it does not.

`docs/06-phase-0-build.md` is Phase 0's own build order — **retired** now that Phase 0 has exited
(`docs/README.md` → *Documents*). It is cited below only where a Phase 0 task's own `owner` field in
`build-ledger.md` still points at it, as history, never as where to start.

## Orient

**1. Find the task.** The checklist in `docs/README.md` is the project's position on itself; take the
first unticked box in `build-ledger.md` for the current phase unless told otherwise. Read that task's
line, the task after it — the next one often reveals what the current one has to leave room for — and
the document its `owner` field names (`06` for a Phase 0 task, otherwise the reference document that
task line points at).

**2. Read what constrains it.** Do not reconstruct the design from the code; it is written down.
`01` → *The kernel boundary* decides what may be written at all, `02` §1 has the contracts and the
payload model, `02` §2 has discovery and the trust model. The decision log in `docs/README.md` says
which gates are settled.

**3. Check the gate.** `build-ledger.md`'s phase header carries **⛔** when a gate the phase depends on
is open, and a task line carries **⚠** when an open gate could still change its shape — `build-ledger.md`
→ *How to read a task line*. If either applies, stop and name the open gate rather than defaulting it;
do not take a "minimal reversible choice" as a substitute for reading what the gate actually requires.
*(Historical: Phase 0's own version of this step was three specific traps naming G2 by number — `06`'s
preamble. G2 settled 2026-08-16; that paragraph is cited only for a Phase 0 task now.)*

**4. Check the fence.** If the phase's own reference document states a scope fence — `06` → *What
Phase 0 must not build* is Phase 0's — and the task seems to need something on it, re-read the task: it
usually needs something smaller. Later phases state their own boundaries in `01` → *Phases* and in each
task's `owner` field; there is no single fence document once Phase 0 has exited.

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

A task is not done until all of these are true:

1. `uv run poe ci-checks` is green. Run it in the **foreground**; backgrounding it and waiting for
   a notification is how three agents in Phase 3 stalled mid-task.
2. **Any fitness function the task's own *turns on* field names is wired and green.** Wiring one
   means adding it to the `ci-checks` composite in the same commit; fitness function 0 fails
   otherwise.
3. **You have run the thing, through the shipped entry point, from a directory that is not this
   repository.** A green suite is not the same evidence as a working binary, and in this project
   that is measured rather than asserted: **every one of Phase 3's four repairs was found by
   running `weft` and none by its 1,513 tests.** What they were is the argument for the step —
   `weft init` refusing a first run in an empty project; a refusal printed twice, once mislabelled
   as a stream error; `weft --help` entering the REPL instead of printing help; a refusal splicing
   a raw Pydantic dump into the middle of a sentence. The third of those falsified the phase's own
   **Exit criterion**, which is written in terms of `weft --help`, and it was not caught by the
   test written to prove that criterion — that test had been shaped around the defect instead.

   So: `cd` somewhere empty, run the command a user would run, and read what it prints. Run its
   failure path too — the wrong flag, the missing file, the name nothing provides — because
   refusals are where composition bugs and text quality both surface. Paste the real output into
   the task's ledger entry. Leave no artefacts behind in the repository; a stray `weft.toml` at the
   root is the tell that someone ran a scaffolding command in the wrong directory.
4. The task's box in `build-ledger.md` is ticked with its commit sha, and `docs/README.md`'s Status
   block still reads true.
5. If the work changed something a document owns, that document is edited in the same commit. The
   plan and the code are meant to be true about each other.
6. The commit message says **why**, and names the step. The diff already says what.

Then run the `weft-qualities` skill against what you wrote if the step added a contract, a capability
or a config surface. It is cheaper to catch an elasticity regression now than after something depends
on it.

## When to stop instead of continuing

- **The task needs an open decision.** `docs/README.md` → *Decision log* names which gates are still
  open. Say which one, and what the task would have to assume. Defaulting one quietly is exactly what
  the gates exist to prevent.
- **The kernel crosses 2,800 lines.** That is a review trigger, not a failure — but it is a
  conversation about the boundary, and the budget is never edited in the pull request that grew the
  kernel.
- **A settled decision looks wrong.** That is information, not failure, but it is a stop rather than a
  patch: re-run the session, then re-check the phases downstream, because these decisions cascade.
- **The reference has something for this.** Use `reference-lift` rather than reinventing it, and remember most
  of the inventory is rewrite-from-design rather than copy — which carries no licensing obligations
  and usually produces better code against contracts the reference never had.
