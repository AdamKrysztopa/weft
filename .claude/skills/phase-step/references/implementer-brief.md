# Dispatching the implementer

Read this when you are about to hand green-phase work to `weft-implementer`. It carries the tier
rule, the brief template, and what to check when the work comes back.

The agent's standing prohibitions live in `.claude/agents/weft-implementer.md` and travel with every
dispatch — do not restate them in the brief. What the brief carries is everything the agent cannot
know: which task, which test, which files, and which choices are already made.

---

## 1. Choose the tier

One agent definition, two models. `model` on the dispatch overrides the definition's `sonnet`.

| Tier | When | Why |
|---|---|---|
| **`haiku`** | The test fully specifies the artefact. Every field, type, name and signature is either in the test or in the brief, and a careful reader could produce the file with no other input — payload models, enum files, fixtures, a registration entry, a fully-specified helper. | Nothing is left to judgment, so nothing is bought by paying for judgment. |
| **`sonnet`** (default) | Everything else — anything where the implementation shape is still open, touches the seam, spans more than one module, or needs the surrounding code read to get right. | This is the working tier. When you are unsure which side the task falls on, it is this one. |

**Escalation goes up, never sideways.** A dispatch that comes back blocked or fails your review is
re-dispatched **one tier up** with the blocker answered in the brief — never re-sent at the same
tier with a firmer tone. Above `sonnet` is you: a task that fails review twice is a task whose test
or whose brief is wrong, and rewriting either is not the implementer's to do.

---

## 2. The brief

Fill every heading. A brief that omits one is the most common cause of a blocked return, because the
agent has none of the reasoning that produced this task and will correctly refuse to invent it.

```markdown
## Task
<ledger id> — <the ledger's property sentence, copied verbatim>
Ledger line: docs/build-ledger.md:<lineno>

## The failing test
<paths>
Run it with: uv run pytest <node ids> -x
It currently fails with: <paste the actual failure output>
It fails because: <the implementation does not exist / returns the wrong shape / …>

## What the implementation has to do
<the behaviour, in prose. Not a design — the property the test is checking, said in words,
so the agent can tell an honest implementation from one shaped to the assertion.>

## Files
Write: <paths — be specific>
Do not write: everything else, and in particular <the test paths above>

## Already decided
<every choice you made while writing the test that the code must match: the module path, the
class and method names, the exact exception type and message shape, the enum members, whether a
field is optional. Anything left out here is a choice the agent must not make, so it will stop.>

## Contract to implement against
<the Protocol or base class, with its file path. Say which methods and their signatures.>

## Not in scope
<the neighbouring thing that looks like it belongs and does not — the next ledger task, the
refactor the code is asking for, the second call site.>
```

**On the failing test.** If the brief mandates a *signature* change, grep for every caller of the
old signature — tests included — and either update them in *Red* or name them here. A brief's list
of affected sites is the author's memory unless a search produced it, which is `L5.14` landing one
step later than where that lesson is applied. Task 6.18 mandated `store_name` → `store_names` in two
modules, named only the one test file its author happened to be editing, and the implementer — which
may not touch a test — correctly returned green against a suite with eight new failures it had been
instructed to cause.

**On "Already decided".** This is the section that decides whether the dispatch succeeds. Every name
the test asserts on is already a decision you made; write it down. A brief that says "implement the
store adapter" and a test that asserts `WeftStoreError("no such collection: …")` will produce a
blocked return, correctly, because the agent cannot tell your message shape from a plausible one.

---

## 3. Review what comes back

The report is a claim, not evidence. Read the diff.

```bash
git status --short
git diff -- tests/ testing/ docs/          # must be empty
git diff -- pyproject.toml                 # must be empty unless the brief asked for it
git diff | grep -nE '# *(noqa|type: ?ignore)|pytest\.mark\.(skip|xfail)|ruff: *noqa'
```

Then read the implementation itself against three questions:

1. **Is it honest, or shaped to the assertion?** A method that returns the literal value the test
   compares against passes and implements nothing. This is what the tier system cannot catch and
   you can.
2. **Did it decide something?** Anything in the diff that is a design choice and is not in your
   brief's *Already decided* is a decision made by a model that had not read the documents. Either
   adopt it deliberately or send it back.
3. **Did it report something it noticed?** The last section of the agent's report is the channel by
   which you find out what only it saw. A neighbouring assertion it flagged as wrong is worth more
   than the diff.

Then the whole gate, in the foreground, run by you — `uv run poe ci-checks`. The implementer ran the
test node ids it was given, which is not the same evidence (`docs/lessons.md` L5.12).

---

## 4. Parallel dispatch

**Disjoint write sets are not enough, and this paragraph said they were.** Two implementers at
once need **two worktrees**: the same checkout serialises them whether or not their files overlap,
because the thing they share is not the files, it is the *test suite*, the one `.venv` and the one
container. Two agents running `pytest` against the same tree truncate each other's tables and get a
result about neither — three unrelated red tests, naming nothing (`docs/lessons.md` `L9.61`,
`L6.22`). `isolation: "worktree"` gives an agent its own checkout; it does **not** give it its own
container, so anything touching the database is serial whatever the isolation.

In practice parallelism is rare inside one ledger task — the tasks are ordered so each is one
property — and the merge costs more than the sequence saved. Default to one.

**And the dispatcher counts as a writer.** While an agent runs, the brief and its tests are that
agent's ground truth and are frozen at dispatch: a defect found in them mid-flight is interrupted
and re-dispatched, or waited out — never silently repaired underneath (`L9.57`, broken five times in
one session by the author who had just written the rule down).


## Constraints can be jointly unsatisfiable, and the author is who cannot see it

`docs/lessons.md` `L8.36`. Task 7.2's brief told the implementer, of one branch, *"do not invent a
`StopReason` member for it; use `BUDGET_EXHAUSTED` only for the budget"* — two clauses with no
value between them that is true, each reasonable alone. It also said *"if you find you need a third
member to be honest, stop and report"*, which is the tell: **an escape hatch in a brief is a signal
the author noticed a fork and did not settle it**, not a safety net that makes leaving it open fine.

The implementer took the strongest available action — it reused the wrong member, wrote the
contradiction into the module docstring *and* its report, and shipped green. No test reached that
branch, so the report was the only reason anyone looked.

**Before dispatching, take each branch the brief constrains and name the value it should produce.**
A branch with no nameable value is a decision still owed, not a constraint. *Already decided* is
read once per constrained branch, never once per file.


## Before you send: six checks a brief fails silently

Phase 10 filed **six** entries that are one sentence — *the brief was wrong in a way the dispatcher
could have checked before sending it*. That density is the finding: none of these is caught by the
agent, by the gate, or by the tests, because each is a defect in the specification rather than in
the work. Run these against the brief, not against the code.

1. **Every name the brief tells the agent to reach for: does the gate permit reaching it?**
   `L10.39`. A brief said *"you may import `_cosine`, `_format_cluster`... import it rather than
   copying it"*, and pyright's strict `reportPrivateUsage` refuses cross-module access to any
   leading-underscore name, by import and by attribute alike. The agent could not both obey and
   pass, so it blocked — correctly, and after doing the whole task. *Usefulness and reachability
   are decided by different files, and the brief's author is reading only the first.* One grep for
   the name across `packages/*/src`, or one look at the lint configuration, answers it.

2. **Is *Already decided* derived from the contract, or from your own test?** `L10.37`, and it is
   `L5.6`'s rule — a comparison whose two sides come from one source cannot disagree. A brief
   spelled a field `node` where the model calls it `value`; the Red test had the identical error
   because the brief was written *from* the test. Read the field off the model, the method off the
   Protocol, the enum member off the enum — not off the file you just wrote.

3. **Does the brief grow a published surface, and does the family forbid it?** `L10.35`. A brief
   added a method to `NodeStore`; `SourceDeletable`'s docstring, twelve classes down the same file,
   forbids exactly that. What caught it was the **version arithmetic** — growing a base is a major
   where four comparable additions were minors — so price the change before writing the brief: a
   change that suddenly costs a major is evidence about its shape, not merely a bill.

4. **Have you counted the search that proves an absence, or sampled it?** `L10.34`. A brief asserted
   **in bold** that all 23 pre-existing type errors were the task's own missing import, checked with
   an inverted `grep` piped through `head -3` — which cannot prove a negative. Two were an invented
   field in the dispatcher's own fixture. Group and count by file; never `head` a search whose
   conclusion is "there are no others".

5. **Does the change land in a function already near a ceiling?** `L10.32`. A brief added two
   branches to a method one below ruff's `max-complexity`, and said nothing — silently delegating
   the choice between extracting a method and writing `# noqa: C901`, only one of which is visible
   in a diff. If the brief adds branching, say which side of the ceiling it lands on.

6. **Is every clause of *done when* something the agent can actually satisfy?** `L10.29`, reported
   by the same agent in all four of its returns. `git diff -- tests/ docs/ is empty` is the
   **dispatcher's** Verify step about the agent's diff, and is unsatisfiable as the agent's own
   condition because the Red test is uncommitted by design, every time. It spent its one reporting
   channel explaining a criterion that could never be met. Keep the dispatcher's checks in *Verify*
   and out of the brief.
