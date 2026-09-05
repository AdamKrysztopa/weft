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

### L8.31 — the gate lived where the first caller was, and the second caller gets none

**What happened.** Found by all three of G12's independent reviews, and confirmed directly:
`weft_cli.confirm.gate` is called from exactly one place — inside `weft_cli.cli.run_command` — and
that function takes an `argparse.Namespace` and returns a `Rendered`. The typed result a library
caller needs comes from `Command.run`, and **nothing gates `Command.run`**; the CLI test double's
own docstring states it outright. `confirm.py`'s docstring calls itself *"the invocation seam"* and
says it refuses a pack's `destroy` command *"with no cooperation from its author"* — true for every
caller that goes through `run_command`, and `run_command` was the only caller when it was written.
Phase 7 is the first second caller, and it silently gets no gate at all. `03` also says every
operation the CLI performs is a library call an HTTP route could make identically, and does not say
the gate is not one of them.

**Generalises to.** When a concern is placed at *"the one place that calls X"*, the placement is a
bet that there will never be a second caller — and the bet's expiry date is written down nowhere.
`CLAUDE.md` already says cross-cutting concerns live at the registration seam and never in a rule a
caller must remember; the sharper form is that **"the one caller" is not a seam, it is a coincidence
of the current call graph**, and a docstring calling it a seam is the tell rather than the defence.

**Candidate home.** A fitness function: a `Command` invoked anywhere outside the one gated path
fails. Ledger task 7.0 moves the gate; this is what keeps it moved.

### L8.32 — a gate was one grep from being argued on a false population

**What happened.** G12's brief was written believing there might be no `overwrite`/`destroy`-class
command in the tree at all, and `docs/03-cli.md` said so in two dated blockquotes. Both were true
when written — the 2026-08-20 repair did empty those rows — and neither was re-measured after tasks
5.1a and 5.1b refilled `destroy` the following day with `weft delete` and `weft reconcile`. The same
document records those two commands elsewhere. One registry dump settles it: nineteen commands,
twelve `read`, five `write`, two `destroy`, **zero `overwrite`**.

**Generalises to.** A dated note stating a *count* becomes a false claim the moment a later task
changes the population, and nothing in this tree re-reads it — so a document that reasons from its
own count must re-measure at the point of reasoning, not cite itself. This is `L6.4` in a document
rather than in a marker, and `L6.11` applied to a brief's numbers rather than to its list of sites.

**Candidate home.** A check that a stated count in `docs/` is derivable, or `phase-step` → *Orient*,
which already says to read the population and should say that a document's own count is a
declaration.

### L8.33 — a gate's deciding fact was a query, and its Bring list asked for a judgement

**What happened.** G12's *positions to attack* said of the ceiling: *"establish whether end-to-end is
reachable inside the ceiling before accepting it."* That is not an opinion to form — it is
`weft index`'s permission class, which is `write`, so the answer is yes and one registry dump
produces it. The session's **Bring** list named five documents to read and no measurement to take,
and two of the three reviews spent their first effort finding the same number independently.

**Generalises to.** Where a gate's position turns on a fact about the tree, its brief should name the
**measurement to take**, not only the documents to read — otherwise every participant re-derives it,
and a session can be argued from whichever stale prose it happens to open first.

**Candidate home.** The **Bring** section's own shape in `docs/05-grilling-sessions.md`, which every
future session inherits.

### L8.34 — a table row with no live instance is a rule nobody has tested

**What happened.** `PermissionClass.overwrite` has **zero** registered commands, and `03`'s worked
example for it — *"reindex an existing collection"* — turns out to land as `write`, because node ids
are content digests and the store upserts. So the class whose behaviour G12 spent a session
reasoning about has never been exercised by anything shipped. `confirm.py`'s docstring had already
recorded the identical gap for `destroy` at task 3.3, and 5.1a closed that one by shipping
`weft delete`; the `overwrite` half was never revisited.

**Generalises to.** An enum member with no live instance is a branch whose meaning is whatever its
docstring last claimed — `L6.4` pointed at a rung of a vocabulary rather than at a marker. Either
something declares it, or the vocabulary should say plainly that nothing does and why, so the next
person reasoning about it knows they are reasoning about prose.

**Candidate home.** `03` → *Permissions*, whose table lists the class; or a ratchet over
`PermissionClass` members with no registration, pinned to the ones deliberately unused.


## When the queue is empty

That is the healthy state, and it means the last drain finished. What was learned lives in
`lessons-archive.md`, session by session, with the edges between entries — which is where the
question *have we been here before?* is answered, and where an on/off cycle becomes visible.
