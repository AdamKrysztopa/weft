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

### L11.1 — a count cited to a script that was not re-run after the commit that fed it

**What happened.** Phase 10's drain filed `R10.2` saying `L5.15` "stands at **five** recurrences …
counted by `scripts/lessons_graph.py` after Phase 10's drain". The script counts `recurs` edges in
`docs/lessons-archive.md`, and it reports **four**. Two separate reasons, both invisible from the
sentence: the count was formed while routing the queue, *before* the same commit wrote the edges the
script reads — so "after Phase 10's drain" named a moment that had not happened when the number was
taken; and the fifth instance was Phase 10's own `index-with-adrap.yaml` shipping without its
`add_pipeline_resource` registration, **a defect caught in the tree, which carries no archive edge at
all**. Found by running the script as `implement-ll`'s own first step, one turn later, against the
entry the *Next action* row sends the next reader to first. The same drain had just routed `L10.18`
— *prefer a pointer to a count* — into `weft-qualities`.

**Generalises to.** When a document cites a script for a number, run the script *after* the edit is
written and paste what it says; and before citing its total, ask what population it walks — a counter
that reads one artefact is a floor for any class recorded somewhere else, so "N by the script" and
"N in the project" are different claims and the document must say which.

**Candidate home.** `weft-qualities` → *a claim with nothing left to check it* already holds the
counts half (`L10.18`, `L6.1`); this adds the ordering (*the number was taken before the act it
describes*) and the population question (*what can the counter not see?*). Possibly instead
`scripts/lessons_graph.py` itself, printing the population it walked and what it structurally cannot
count, so the floor is stated by the instrument rather than remembered by its reader. `recurs L6.1`,
`recurs L10.18`.

## When the queue is empty

That is the healthy state, and it means the last drain finished. What was learned lives in
`lessons-archive.md`, session by session, with the edges between entries — which is where the
question *have we been here before?* is answered, and where an on/off cycle becomes visible.
