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

### L11.2 — a check was designed, sized and nearly declined before anyone grepped for it

**What happened.** Routing `R10.2`, the question was whether `L5.6`/`L5.19` — *a check whose two
sides come from one source cannot fail* — could be made mechanical. A check over the architecture
checks was designed, a detector was written, and it was sized: **31** modules discover a
population, **9** appeared unguarded. Opening three of the nine found all three correctly guarded,
by two spellings the detector could not see (a population floor, `assert found > 50`; and failure
self-tests driving the comparison over synthetic inputs). On that evidence the check was declined.
Then `poe ci-checks` failed — on
`tests/architecture/test_ff0b_checks_are_real.py::test_every_check_here_proves_it_can_fail`, which
**is that check**, has enforced it on every file in that directory since Phase 5's drain, cites
`L5.6` and `L5.19` in its own docstring by name, and had just caught the new fitness function 27
for missing its self-test. Nine minutes of gate answered what one `grep -rn "L5.19"
tests/architecture/` would have. The conclusion survived — the rules recurred in a dispatch brief
and a resolver's diagnosis, which that check cannot reach — but every number offered as evidence
for it was about the wrong thing.

**Generalises to.** Before concluding that a rule cannot be mechanised, search for the machinery it
may already have — by the lesson id, which this repository requires at the point of enforcement
precisely so that search works. And a count taken by a detector you wrote is evidence about the
detector until you open the sites it flagged.

**Candidate home.** `implement-ll` → *Routing*, which requires two numbers for a proposed check and
does not yet require asking whether the check exists. The reverse of `L5.4` (a mechanism believed to
run that did not) and the same family as `weft-qualities` → *before you accept a mechanism as this
change's escape hatch, run it* — this is *before you reject one, look for it*.

### L11.3 — a one-point probe of a step function measures that point

**What happened.** Deciding `R9.1`, the question was whether carrying `PdfPages` through a cleaner
still yields the right page. The first probe compared `page_at` at the **end of the document** on
five papers: drift 0.1–0.3%, page error **0** on all five, and the verbatim carry looked safe. It
is not. `page_at` is a step function over page boundaries, so what matters is whether accumulated
drift crosses a boundary, not how large it is overall — probing every boundary on nine papers gave
a worst error of **3 pages**. The first reading would have shipped a citation that names the wrong
page, silently.

**Generalises to.** When a measurement is about whether a *derived* answer is still right, probe
the derivation at the points where its answer changes, not at the extremes of its input. An extreme
is where the input error is largest and is not where the output error is worst.

**Candidate home.** `weft-qualities` → *can the instrument see the thing being varied?*, which
already holds the metric-sensitivity cases; this is the same lens applied to a probe rather than a
metric. Possibly `phase-step` → *Verify*, since the probe was deciding a repair.

### L11.4 — the same repair filed twice, under two ids, in one section

**What happened.** `R10.2` was filed at Phase 10's drain as *"the three rules this loop keeps
re-learning live somewhere that makes them bite"*. `R9.13`, filed a phase earlier and **86 lines
above it in the same *Carried repairs* section**, already said *"`L5.15`, `L6.4` and `L5.6` are held
by an artefact that makes them bite"* — the same three rules, the same owner, and a sharper property
(`R9.13` says *"or has a recorded decision that it cannot"*, which is the clause `R10.2` needed and
did not have). Found only by grepping the ledger for `R9.1` while closing an unrelated repair.

**Generalises to.** Before filing a carried repair, grep the carried-repairs section for the
identifiers the new entry names. A repair is filed *because* nothing owns it, which is exactly the
condition under which nobody remembers whether it was filed before.

**Candidate home.** `implement-ll` → *Do not implement a finding as a rule*, where filing a repair
is instructed and no lookup is asked for. `L5.14`'s rule reached from a new direction: a list in a
document is where to start looking, and the carried-repairs list is one nobody re-reads.

## When the queue is empty

That is the healthy state, and it means the last drain finished. What was learned lives in
`lessons-archive.md`, session by session, with the edges between entries — which is where the
question *have we been here before?* is answered, and where an on/off cycle becomes visible.
