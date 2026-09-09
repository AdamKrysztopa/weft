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

### L11.5 — the check written to stop an artefact rotting checks a property the artefact does not have

**What happened.** `CHANGELOG.md` was brought current by task 5.2f *because* `L5.8` recorded that it
had gone stale for five phases, and the same task added
`tests/docs/test_changelog_deprecation_coverage.py` so it would not happen again. It happened again
immediately: last touched at Phase 5's close (`4230057`), untouched through Phases 6, 7, 8, 9 and
10, and found only when a release was being prepared. **The check never failed and is not broken.**
Its subject is *deprecated surfaces*, this tree has zero, and its own waiver docstring says so
honestly — so it passes by asking nothing about whether the file describes the current software. The
artefact rotted underneath a green check written to protect it.

**Generalises to.** When a check is added to stop an artefact going stale, ask what it asserts when
the artefact *is* stale. If the answer is "nothing, because its subject is empty", the check
protects a property the artefact happens to have and not the one it was written for — and its green
is now positive evidence to a later reader that the artefact is fine.

**Candidate home.** `weft-qualities` → *a claim with nothing left to check it*, which holds the
claim-side cases; this is the check-side one. Possibly a `tests/docs` clause instead: a document
that names phases has an entry for every phase the ledger records as closed — a real population
(11 phases), computable, and it would have failed for five phases running. Size it before adopting
it. `recurs L5.8`, `recurs L5.19`.

### L11.6 — the check that reads a preamble for a gate mark never asks whether the preamble is right

**What happened.** `docs/README.md`'s **Next action** row said *"Phase 11's own D2 was settled by
**G15**"* while its **Open decisions** row said *"**2, both Phase 11's** … `11` D2"* and
`docs/build-ledger.md:7532` said *"Two scope decisions are open. **D2** …"*. The decision log's own
G15 row and `docs/05-grilling-sessions.md:1092` both say *"**`D2` is settled by the three
together**"*, quoting D2's exact wording, and G15's *Done when* required *"`D2` moved to Settled in
the decision log"*. So one document was right and two were stale, in the file whose stated rule is
that it holds *"state and pointers only"*. `next_task.py`'s live checks were green through all of
it. Two reasons, both structural: `next_task.py:406-415` asserts only that the phase preamble
**contains the ⚠ glyph** — never that what it says about a gate agrees with the decision log's
status for that gate — and it scopes that assertion to `task.phase`, which was Phase 9, so Phase
11's preamble was not opened at all. Caught by the owner reading three sentences by hand and
telling the session to settle it before 11.7.

**Generalises to.** A check that a document *mentions* a cross-reference is not a check that the
document *agrees* with it; where two files hold the same fact under different ids, assert the
values equal, not that both are non-empty. And a live check scoped to the current task's phase
cannot see the phase the project's own Next-action row is routing to — a check whose subject is
chosen by ledger order inherits ledger order's blind spot.

**Candidate home.** `next_task.py` → `live_checks`: for every ⚠ task in the phase, parse the gate
ids the preamble names and compare each against that gate's Status cell in `docs/README.md`'s
decision log, failing when a preamble calls open what the log calls Settled. The population is
real and computable (17 gate rows, 4 ⚠ lines in Phase 11 alone) and it would have failed on this
tree. Scope it to the routed phase as well as the ledger-order one. `recurs L6.4` — that entry
bought the mention-check this entry finds insufficient; `recurs L5.6` on the two-sides-one-source
half. `caused-by L6.4`

## When the queue is empty

That is the healthy state, and it means the last drain finished. What was learned lives in
`lessons-archive.md`, session by session, with the edges between entries — which is where the
question *have we been here before?* is answered, and where an on/off cycle becomes visible.
