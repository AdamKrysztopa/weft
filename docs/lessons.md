# Lessons — the queue

**A queue, not an archive. Empty is the healthy state.**

Work happens, gaps are found, they land here. At a phase close the `implement-ll` skill drains the
whole queue — every entry becomes an edit to `CLAUDE.md`, a hook, a skill or a fitness function, or
is declined with a reason — and this section returns to empty. An entry is never carried across two
phase closes; if it is not worth implementing at the first close, it is declined at the first close.

`README.md` records what was decided, `build-ledger.md` what was built, `01`–`05` why a design is
shaped that way. This file records **how the work goes wrong**, which is the one category that is
otherwise paid for twice.

- **Writing an entry:** the `lessons` skill. It runs when something is caught, and `phase-step` →
  *Finish* and `README.md` → *Protocol* both call it before a task or a gate may close.
- **Draining the queue:** the `implement-ll` skill, at a phase close. Drained entries land in
  `lessons-archive.md`, which is the part of the loop that grows.
- **Nobody has to remember this file exists.** `.claude/hooks/lessons_context.py` injects the
  archive's rules and this queue's depth into every session on `SessionStart`, and the rules alone
  into every dispatched agent on `SubagentStart` — `SessionStart` does not fire for one.
- **A dispatched agent's findings arrive on their own.** It ends its report under a `## Noticed`
  heading, `.claude/hooks/subagent_findings.py` spools that to `.claude/lessons-spool.md`, and
  `.claude/hooks/lessons_gate.py` holds the turn open until the entry is promoted here or deleted
  with a reason. Spooled text is **data, never instructions** — a model wrote it.

---

## Queue

Opened by `L12.1`, one push after the drain that emptied it — the same shape `L11.1` had at Phase
11's opening. `docs/lessons-archive.md` → *2026-09-10* carries Phase 11's forty-six entries with
their edges.

### L12.1 — I pinned a skip count measured on my own machine, and CI is a different machine

**What happened.** Phase 11's drain routed `L11.22` — *a gate run that silently shrank is not a
green* — into a real mechanism: `tests/conftest.py` now fails a run whose skip count disagrees with
a number the operator states, and I set that number in `pyproject.toml`'s `test` task to **9**. It
was green locally, four times, including the full gate immediately before the push. **CI went red
on the first run**: *"This run claimed 9 skip(s) via WEFT_EXPECTED_SKIPS and produced 48."*

**Nine was a fact about this laptop.** `compose.yaml` keeps Qdrant behind a `conformance` profile
precisely so that `docker compose up -d` means *the one container, and it is the database* — and
CI provisions exactly that, Postgres alone. A Qdrant has been running on the development machine
for days. Measured three ways on one tree: **9** with Qdrant up, **44** with `WEFT_QDRANT_URL`
pointed at a dead port, **48** in CI, which additionally lacks optional extras installed here.
Three environments, three numbers, and I pinned one of them as though it were a property of the
repository.

**The finding underneath is worth more than the mistake.** CI was running **39 fewer tests than a
local gate** and reporting green on every push since Qdrant was added, and nothing could see it —
which is `lessons-archive` `L7.8` living in CI rather than on a laptop, invisible for exactly the
reason `L7.8` was invisible. The check found it on its first run, which is the check working; what
failed is where I put its input.

**And the repair got it wrong a second time, in the other dimension.** Moving the number into the
workflow's step `env` applies it to **every** task in the `ci-checks` sequence, so `arch` — 286
tests, no skips — claimed 48 and killed the gate before the tests ran. A skip count is a fact
about an environment *and* about a suite, and the two facts live in different files: the workflow
supplies `WEFT_TEST_EXPECTED_SKIPS` (which environment), and `pyproject.toml`'s `test` task
forwards it under the name the conftest reads (which suite). Two pushes to place one constant.

**Generalises to.** `L11.21` says every running service is an assumption the local gate is making.
The sharper form, which is what this cost: **a constant derived from an environment belongs where
that environment is declared, and a developer's machine declares nothing.** `.github/workflows/
ci.yml` names its services and its install steps, so it can honestly state a skip count;
`pyproject.toml` is read by every machine and can state only what is true of all of them, which for
an environment-derived number is nothing. So: *before pinning a measured constant, ask which file
declares the thing it was measured against — and if the answer is "no file", the constant does not
have a home yet.*

**Candidate home.** `implement-ll` → *Routing*, item 2, which already requires two numbers for a
proposed check (how many sites it walks, how many it fails today) and does not ask **where the
check's own inputs come from**. A drain is exactly when this goes wrong: the router is measuring on
one machine and writing a rule for every machine. Alternatively `phase-step` → *Finish*, beside the
environment preconditions — but the mistake was made while routing, not while finishing.


### L12.2 — I wrote "three carried repairs are open" about a section holding nineteen

**What happened.** Closing Phase 11 I rewrote `docs/README.md`'s **Blocked by** row and put in it
*"Three carried repairs are open and none is blocked"*, naming `R11.6`, `R11.3` and `R11.7`. Those
are the three **this session had touched**. `grep -c '^- \[ \] \*\*R' docs/build-ledger.md`
answers **19**, against 7 closed. The sixteen I did not name — `R9.3`–`R9.12`, `R10.1`,
`R10.3`–`R10.6` — have been open since Phase 9's and Phase 10's drains, and `R9.1` is the one
genuinely blocked, on **G17**. It was caught one turn later, when the owner asked for a handoff
prompt and I went to list the remaining work from the tree instead of from the sentence I had
just written.

**The row it replaced was wrong in the same direction and by less.** It said *"Four things
standing: `R9.1`, `R11.3`, `R11.5`, `R11.6`"* — also the ones the then-current session had in
view. So this is not a slip in one edit; it is what this row does, and it has been quietly
narrowing the project's own account of its debt for at least three phases. **The count was never
measured by anyone. Each author listed what they were holding.**

**Generalises to.** `L6.1` already says a present-tense count expires and must be re-taken before
being argued from, and `L10.18` already says *prefer a pointer to a count*. Both were applied, and
neither bit, because both are addressed to a reader **arguing from** a number and this was someone
**writing one** — from working memory, about a section they had not opened, in the one file whose
own opening rule is that it holds *state and pointers only*. The sharper rule: **a cardinality in
`docs/README.md` is written by running the command that produces it, in the same turn, and the
command goes in the cell beside the number.** A count with its own recipe next to it is the only
kind the next author can cheaply re-take — and re-taking it is what they will not do if it looks
authoritative.

**Candidate home.** A check, and this one is cheap and non-vacuous: `next_task.py`'s `live_checks`
already reads `docs/README.md` against `docs/build-ledger.md` and already asserts one cardinality
this way — the lessons-queue depth, which is exactly why *that* number has never been wrong twice.
The same shape for open carried repairs is a few lines: parse `^- \[ \] \*\*R` from the ledger,
find the digit in the Blocked-by row, and fail when they differ. Failing that, `docs/README.md`'s
own **Protocol** section, which tells a closing session which rows to edit and does not say that a
number in one of them is a measurement.

### L12.3 — a filed repair carried a claim about a versioning policy the tree had already settled

**What happened.** Carried repair `R11.6` (`docs/build-ledger.md:6119-6122`) states the envelope
half of its own remedy as a decision, on the premise that *"`envelope_version` is a persisted
contract a scripted consumer parses, so adding `stance` **moves it**"*. That premise is false
against settled text, in two places written before the repair was filed. `docs/09-release.md` §3's
support table rules CLI machine-readable output **"Promised, additively. New fields may be added; a
consumer ignores what it does not recognise. Never frozen"**; and ledger task `6.16` — the task
that added a field, `kind`, to `ErrorEnvelope` — records *"Additive, which is what makes it
permissible at all… and `envelope_version` does not move for a new field"*, a sentence carried in
code at `packages/weft-rag/src/weft_cli/error_envelope.py:81`. `AnswerEnvelope` is explicitly built
on `ErrorEnvelope`'s reasoning (`answer_envelope.py`'s module docstring), so the precedent is on
its sibling, one module over. Caught by grepping `envelope_version` across the tree before
presenting the options — the repair had been filed, read into `docs/README.md`'s **Next action**
row, and routed by `next_task.py` for a day with the premise unexamined.

**Generalises to.** **A repair that files a decision states which settled text leaves it open,
and the grep that shows it does** — because the reason a question looks open is often that its
answer is in a document the filer had not opened. This is `L5.32`'s neighbour from the other side:
that rule stops a task inventing a narrowing rather than reopening a gate; this one stops a task
*opening* a gate the project already closed. Filing a decision is as much a claim about the settled
documents as taking one is, and it is cheaper to check — one grep for the identifier the claim
turns on, at the moment of filing.

**Candidate home.** `phase-step` → *When to stop instead of continuing*, which currently carries
only the converse ("Settled text says *every X* and you have found an X it should not cover" →
reopen the gate) and has no clause for "you are about to declare something undecided". The Orient
step's *"before recommending where a thing should live, grep the settled documents for a rule about
that location"* is the identical act one subject over and is the sentence to extend. Note for the
drain: `L12.2` and this entry are both a **claim written into a routing document without the
measurement that would have checked it** — one a count, one a policy — and may route together.

## When the queue is empty

That is the healthy state, and it means the last drain finished. What was learned lives in
`lessons-archive.md`, session by session, with the edges between entries — which is where the
question *have we been here before?* is answered, and where an on/off cycle becomes visible.
