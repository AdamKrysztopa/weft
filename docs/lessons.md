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


## When the queue is empty

That is the healthy state, and it means the last drain finished. What was learned lives in
`lessons-archive.md`, session by session, with the edges between entries — which is where the
question *have we been here before?* is answered, and where an on/off cycle becomes visible.
