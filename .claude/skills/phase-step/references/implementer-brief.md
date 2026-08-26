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

Two implementers at once only when their write sets are disjoint and neither's test can be made
green by the other's file. In practice that is rare inside one ledger task — the tasks are ordered
so each is one property — and two agents editing the same module produce a merge you have to
untangle, which costs more than the sequence saved. Default to one.
