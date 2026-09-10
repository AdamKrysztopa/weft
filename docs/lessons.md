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

### L11.7 — a protocol sentence about a glyph, with thirteen live counter-examples and zero instances of compliance

**What happened.** `docs/build-ledger.md` → *The working protocol* said that when a gate closes,
every ⚠ task downstream is re-derived *"and drop the ⚠"*, and `How to read a task line` defines ⚠
as *"An open gate could change this task's shape"* — so by both sentences a ⚠ on a closed gate is a
notation error. `phase-step` → *Orient* says the opposite in as many words: *"A ⚠ whose gate has
since closed is a record, not a block. The mark is kept on the line as history."* Settling `11` D2
made this a live question about three task lines, and it was nearly resolved by reading the two
documents and picking the one that owns the notation. Counting instead settled it in one command:
**thirteen ticked task lines carry ⚠ against closed gates — `0.2`, `0.6`, `0.8`, `6.1`, `6.4`,
`6.5`, `6.13`, `7.1`–`7.4`, `10.4`, `10.10` — across four phases, and not one task in eleven phases
has ever dropped the mark.** The ledger's sentence had never once been executed.

**Generalises to.** Where two artefacts state a convention differently, the tie is broken by
counting live instances, not by deciding which document owns the notation — a rule with zero
instances of compliance and thirteen of violation is prose, whatever its provenance, and the
practice is the convention. This is `phase-step`'s *read the population, not the declaration*, and
its second instance on this same glyph: `next_task.py` was written against ⚠'s definition and every
live ⚠ meant something the definition did not cover.

**Candidate home.** Applied here as the ledger repair itself, so this entry may be a `declined —
already fixed` at the drain. What is *not* fixed and may deserve a check: nothing computes the
agreement between a glyph's definition, the protocol's rule for it and its live instances, and this
is now the second glyph-semantics defect (`L6.4` was the first, `L11.6` the third in the same
family — a preamble that misstates a gate's status). Three in one family is `L10.24`'s threshold
shape. Size it against the two other entries at the drain rather than alone. `recurs L6.4`,
`caused-by L6.12` — a documented rule that turned out to be prose.

### L11.8 — two licensing checks are green on a layout whose wheels carry no licence at all

**What happened.** Task 11.0 edits the root `NOTICE`, which has **eight byte-identical copies**
under `packages/*/`, so a one-sentence change is a nine-file edit maintained by hand. The obvious
repair — make the copies symlinks to the root, so the nine files become one — was **measured before
adopting it, and it fails, silently**. Built in a throwaway hatchling package on 2026-09-09 with
`LICENSE`/`NOTICE` as symlinks and `license-files` declaring both: the sdist carries them as
symlinks of **size 0**, and the wheel — which `uv build` produces *from* the sdist — carries
**no licence entries at all** (`wheel entries: []`). That is the exact state
`test_release_licensing.py`'s own docstring records the tree being found in: *"not one built
artefact carried either file"*. And both shipped checks pass on it, measured the same day:
`(member.directory / name).is_file()` follows a symlink and returns `True`, and
`read_bytes() != originals[name]` reads through the link and reports no drift. So the two checks
written to keep the licence in the artefact are green on the one configuration that removes it.

**Generalises to.** A check that asks whether a path *resolves* has not asked what the build will
*package*: where the property is "this file's bytes are inside the artefact", `is_file()` and a
content comparison both pass for a link, a hardlink and anything else the filesystem will follow,
so the check must assert the file kind it actually needs. More generally, a deduplication that
removes N-1 copies of a file the build machinery copies must be measured against the build, not
against the checkout — the checkout is where it looks correct.

**Candidate home.** Half of it is applied at 11.0: the licensing check now refuses a carried
licence that is not a regular file, and `poe licence-sync` makes the propagation one command
instead of nine edits, so the drift check stays the enforcement rather than becoming the workflow.
What is not applied: nothing anywhere asserts a property of a **built** artefact except
`scripts/check_sdists.py`, and it was not consulted before this repair was designed — the same
"which artefact is the subject" question `L6.25` raised for `tests/architecture` against installed
distributions. Consider at the drain whether the licensing file's population should be the wheel
rather than the directory. `recurs L5.19` — a check that cannot fail on the case it exists for.

### L11.9 — the brief attributed a cost it had not profiled, and every remedy it listed was wrong

**What happened.** A dispatch brief to speed up `ci-checks` stated as fact that
`test_ff9c_every_contract_has_a_stranger`'s 451 seconds went on *"throwaway virtualenvs built
serially, one per distribution, each installing every first-party wheel"* — read off the test's own
source (`:334-364`, a `uv venv` / `uv pip install` / probe loop) and from `--durations`, which names
the slow test and says nothing about what is slow *inside* it. Measured by the implementer: building
all eight wheels takes **2 s**, `uv venv` **0 s**, installing all eight **1 s**. The 451 s was
`discover()` importing `torch` and `transformers` from **nine physically distinct copies of the same
gigabyte** — macOS's default `uv` link mode copies rather than hardlinks, so the OS page cache was
cold nine times over. Every remedy the brief proposed (shared wheel dir, warm `UV_CACHE_DIR`,
`--offline`, parallelise the loop) targeted the 3 seconds; parallelising nine-wide made it *worse*
and tripped a 180 s subprocess guard. The actual fix was one flag nobody had proposed,
`--link-mode=hardlink`, and a profile of the inner probe would have found it in ninety seconds.

**Generalises to.** `--durations` identifies *which* test is slow and is not evidence about *why*;
a brief that names a cause has made a claim, and a claim about where time goes is measured by
profiling the inner call, never by reading the loop that surrounds it. State the symptom and the
budget in a brief; leave the cause to whoever profiles it, or profile it first.

**Candidate home.** `phase-step` → *Green* / `implementer-brief.md`: a brief may state what was
measured and must not state an unprofiled cause as fact — the *Already decided* section is for
decisions, and a diagnosis is a hypothesis wearing one. This is `L7.1`'s rule (a task names the
property and no remedy) arriving in the dispatch brief rather than in the ledger line.
`recurs L7.1`

### L11.10 — `--dist=loadgroup` silently ignored every group mark, and the win looked like a win

**What happened.** `tests/conftest.py` marks every container-touching test with one
`xdist_group("weft-container")` so `--dist=loadgroup` pins them to a single worker — the whole
reason parallelising the suite is safe. It did nothing. `xdist.remote.WorkerInteractor.
pytest_collection_modifyitems` rewrites each marked item's nodeid to end in `@<group>`, and *that
suffix* is what the scheduler groups on; a conftest hook without `@pytest.hookimpl(tryfirst=True)`
runs **after** xdist's, so the marks were applied to items whose nodeids were already fixed, no
nodeid got a suffix, and the grouping was inert. The first parallel run looked like a three-second
win and was **17 failures — `L8.30` reproduced exactly, by the machinery installed to prevent it**:
`different vector dimensions 3 and 64`, `supersede touched a node it was not given`, `two files were
indexed and list_sources() returned 4`. It was caught only because the implementer read the exit
code and the row counts instead of the wall time.

**Generalises to.** A marker only means something to the component that reads it, and hook ordering
decides whether it is there when that read happens — so a scheduling mark is verified by observing
the *scheduler's* view (grep the output for `@<group>`), never by observing that the mark was
applied. More generally: a parallelisation whose only evidence is a shorter wall time has no
evidence, because the failure mode of a broken one is *also* a shorter wall time.

**Candidate home.** `CLAUDE.md` → the container paragraph that already carries `L8.30`: anything
that changes how tests are scheduled against the one container is proved by row counts and exit
code before wall time is quoted. Possibly a check: assert at collection that every
`_reaches_a_container` item's nodeid carries the group suffix when `--dist=loadgroup` is active —
a real population, computable, and it would have failed here. `recurs L8.30`, `recurs L6.22`

### L11.11 — the detector for "the suite quietly shrank" is covered by no test of its own

**What happened.** `tests/conftest.py` carries `L7.8`'s guard: a run whose `WEFT_DATABASE_URL`
claims a database that turns out unreachable fails rather than passing with 51 fewer tests. While
adding xdist, the implementer wrote into its docstring that xdist round-trips a skip's `longrepr`
through JSON, turning the `(path, lineno, reason)` tuple into a list and silently disabling the
guard — a claim from intuition, defended at length in prose. Measured: false. `execnet` preserves
tuples and the detector fires identically under `-n 2`. The claim was reverted rather than left
standing. **The residue is the real finding**: nobody could tell from the tree whether that guard
still worked under xdist, because *nothing tests the detector itself*. It was argued from first
principles in both directions and settled only by someone running it on purpose.

**Generalises to.** A guard whose whole purpose is to notice a silent shrink is the guard whose own
failure is silent; when the machinery underneath it changes — a runner, a serialisation, a
scheduler — it must be *exercised*, not reasoned about. Any check that exists to detect an absence
needs a test that produces the absence.

**Candidate home.** A test that runs a tiny session with an unreachable `WEFT_DATABASE_URL`, serial
and under `-n 2`, and asserts the banner fires in both. `recurs L7.8`, `recurs L5.19` — a check
that is never seen failing.

### L11.12 — the `# noqa` guard refuses the repository's own settled idiom, and the container set is not a directory

**What happened.** Two findings from one dispatch, kept together because both are *"the tree's own
convention is not where you would look for it"*. **(a)** Five scripts under `scripts/` carry
`# noqa: S603` on literal-argv, no-shell `subprocess.run` calls, with the justification written into
`check_isolated_installs.py`'s docstring — a settled, argued idiom. A new script cannot follow it:
`.claude`'s quality-gate guard refuses any added `# noqa` outright. The implementer restructured
`scripts/impacted_tests.py` to spawn nothing at all, which is arguably better and was **forced by
the tool rather than chosen**. Related and worth knowing: `scripts/` is not in ruff's `S101`
per-file-ignores, so `assert` is a lint error there — the `tests/`-shaped habit does not transfer;
and `S603` does not fire on a fully literal argv at all, so `subprocess.run(["git", "diff"])` never
needed the annotation while `subprocess.run([which("git"), *args])` does. **(b)** The set of tests
that reach the one container is **not** `tests/integration/`: `tests/unit/weft_store/
test_pgvector_store.py`, `tests/unit/weft_qdrant/test_store.py`, `tests/docs/test_quickstart.py` and
`tests/docs/test_readme_is_enough.py` all talk to the real Postgres or Qdrant. A design that
serialised only `tests/integration/` would have broken the gate silently.

**Generalises to.** A guard that forbids a category cannot distinguish the repository's own argued
exception from the abuse it was built to stop, so a blanket refusal quietly outlaws settled practice
— either the guard learns the exception or the convention is retired, but it cannot be both. And a
property of a test (*it needs the container*) is derived from what the test does, never from which
directory it sits in.

**Candidate home.** For (a): decide whether the `# noqa: S603` idiom is retired or whether the guard
gains the exception, and say which in `CLAUDE.md` → *Automation*; it currently reads as though the
idiom is live. For (b): applied already — `tests/conftest.py` derives the container set from each
module's own source rather than from a path — so this half may be `declined — already fixed` at the
drain, with the general rule surviving. `recurs L9.56` — a project prohibition needs a mechanism,
here arriving as a mechanism that outgrew its prohibition.

### L11.13 — a refused command was split, and the half that mattered was dropped

**What happened.** `guard_unchecked_commit.py` correctly refused `python3 - <<PY … PY; git add …
&& git commit --amend; uv run pytest … | tail -3` — a check chained to a commit, `L10.24`'s own
shape. The refusal names the fix: *"split it into two turns"*. I split it and re-ran **only the
git half**, so the heredoc that ticked task `11.0`'s ledger box never executed; the amend then
committed nothing and `70bda15` shipped 11.0's work with its box still unticked. That is precisely
the first of `L10.24`'s three instances — *"an assertion whose message went nowhere, so a task was
committed with no ledger entry"* — reproduced one turn after the guard that exists for it fired
correctly and was read. Caught only because the `git blame` check written minutes later reported
`11.0 -> None` while claiming zero unattributed, a contradiction that had to be chased.

**Generalises to.** A hook refusal rejects the **whole** call, so every side effect in it is
un-run, including the ones that were never the problem — re-issue *all* the parts, not the one the
refusal was about. The tell is that a guard's message describes what was wrong, never what was
lost, and the eye follows the description.

**Candidate home.** `guard_unchecked_commit.py`'s own refusal text: after *"split it into two
turns"*, one line saying that nothing in the refused command ran, including any file edit in it, so
every part must be re-issued. The guard is the only thing that knows what it just discarded, and it
is already speaking at exactly the right moment. `recurs L10.24`

### L11.14 — the routing row named a task that was already done, and the live check confirmed it

**What happened.** `docs/README.md`'s **Next action** row still read *"**Begin Phase 11 — the graph
pack**, at task `11.0`"* and *"its D3 … is still open"* after the commit that ticked `11.0`
(`70bda15`) and after the commit that settled D3 as `S13` (`d88fc32`) — which is the same commit
that edited the **Open decisions** row two cells below to *"**None.**"*. So a session opening on
this tree was routed at a finished task by the one row documented as outranking ledger order, and
`python3 .claude/skills/phase-step/scripts/next_task.py --check-live` printed *"live check ok —
Status block read, its phase agrees with 11.0 (the task its own Next action row names)"* and exited
`0`. The check is not blind here the way `L11.6`'s was: `_phase_agreement_failures`
(`next_task.py:306-316`) **does** parse the identifier out of the row, **does** find that task in
the ledger, and fails when it is in no phase at all — and then compares only the two phase
*numbers* (`:317-325`). Whether the task it just resolved still has an unticked box is a field the
`Task` record already carries and nothing asks for. Caught by reading the ledger by hand after the
script's own output disagreed with the ticked box directly above it.

**Generalises to.** When a check has already resolved a pointer to the object it names, assert the
object is in the state the pointer *claims* for it, not merely that it exists — a router that names
a completed step reads exactly like one that names the right step, and the field that separates
them is the one already in hand. Corollary for this repository's Status block: a row that names a
task id is stale the moment that box is ticked, so the commit that ticks a box owns that row.

**Candidate home.** `next_task.py` → `_phase_agreement_failures`: where `named` is resolved, fail
when `named.done`, saying which task the row points at and which one is actually first unticked.
The population is real and computable and it would have failed on this tree at `d88fc32`. Group it
with `L11.6` — both are the same routing row, both passed a green live check, and the two
assertions land in the same function. `recurs L11.6`


### L11.15 — the nine papers this project measures against have never been through its own ingest ladder

**What happened.** Running the shipped binary from outside the repository at task `11.1`,
`weft index corpus --pipeline index-pdf` over `corpus/mrmr/Ding i Peng - 2005 - MINIMUM REDUNDANCY
FEATURE SELECTION FROM MICROARR.pdf` exited **1** on `'extract' failed: cannot write empty image`,
and so did `index-pdf-undescribed` and `index-pdf-rows`. `corpus/mrmr/` is this project's own
measurement fixture — `05` → G17's *Bring* names it, and its whole four-position argument rests on
numbers taken from it — and `grep -rn mrmr tests/ scripts/` returns **four files, none of which
opens a single one of those PDFs**: three are the string `corpus/mrmr.pdf` used as a stub `uri`,
the fourth is a fitness function. G17's own measurement reached the papers through
`PdfTextExtractor` directly, which is the one path that reads no figures. So the corpus the project
argues from has been read by an extractor and never by a pipeline, and 2,516 green tests say
nothing about whether `weft index` can ingest it.

**Generalises to.** A fixture a document argues from is only evidence for the path that actually
opened it: before quoting a measurement over a corpus, check which entry point produced it, and run
that corpus through the shipped ladder at least once. A directory of real inputs kept in the tree
and never handed to the binary is a fixture for the reading, not for the product.

**Candidate home.** An integration test, or a `poe` task, that indexes `corpus/mrmr/` through
`index-pdf` end to end and asserts every document reaches the store — the population is nine files
and it fails on this tree today. `recurs L9.87` (a capability whose every test injected a double
and shipped dead), and it is the *fifth* consecutive phase where the binary found what the suite
did not.

### L11.16 — a policy stated in one path's docstring was never applied to its sibling

**What happened.** `weft_pdf.document.ExtractedTable`'s docstring settles the policy for a
backend's bad reading: refusing a malformed grid "must skip the one table rather than fail the
document", and `extract_documents` carries an `unreadable` channel for reporting it. The figure
path in the same distribution has neither: `pdf_layout.py:344` is a bare
`rendered.crop(box).save(buffer, format="PNG")`, so one zero-area crop raises out of PIL and takes
the whole run with it — measured, 67 zero-width image boxes on one real paper's 21 pages. Both
paths were built by the same phase (`9.6` tables, `9.7` figures) and only one of them carries the
rule, which is why it read as settled while being true of half the pack.

**Generalises to.** A policy written into one docstring is a policy for that call site until
somebody greps for the siblings it names — so when a task states how a bad input is handled, list
the other paths in that distribution that take bad input and say, in the same commit, whether each
one does it. A rule with one instance and one counter-instance looks exactly like a rule with two
instances from inside either file.

**Candidate home.** Grouped with `L11.15` under carried repair `R11.1`, whose two properties are
this entry's and that one's. If it wants a check rather than a repair: every `Extractor` in the
tree that opens a third-party library has a path where that library's failure on one element is
contained, and `ci-checks` has no way to ask that today. `recurs L6.12` on the prose-check half.

### L11.17 — the double was written from the contract's docstring, and the seam returns something else

**What happened.** Writing `11.2`'s test I gave `_StubLookup.build` a body returning the stub
retriever itself, with a docstring saying "here it hands back the stub itself, which is what the
plugin under test calls". `StageLookup.build`'s own docstring says it returns "a callable already
through `weft_kernel.seam.wrap`", and the real `weft_retrieve.engine.RegistryStageLookup.build`
returns `wrap(instance.run, ...)` — a plain function with no `.run` attribute. Both existing
doubles for that seam, in `test_iterative.py` and `test_corrective.py`, return `self._leaf.run`
and `self._primary.run`. Mine did not, so three of seven tests could only be passed by an
implementation that calls `retriever.run(...)`, which would have needed a second `cast` and would
have failed against the registry everywhere else in the pack calls it. The implementer refused to
edit the test, said exactly that, and came back blocked — which is the split working, at the cost
of one dispatch round trip.

**Generalises to.** A double for a seam is copied from an existing double of *that same seam*,
never written from the contract's prose: the prose says what the value *is for* and the existing
double says what shape actually arrives. Where two test files already stub one seam, a third that
stubs it differently is the one that is wrong. Cheapest check before dispatching: grep for the
other stubs of the same protocol method and diff their return statements against yours.

**Second instance, same session, same author — `11.12`.** `tests/unit/weft_cli/
test_eval_compare_kind.py`'s `_record()` built `RunRecord(run_id=…, pipeline=…, corpus_hash=…)`,
and that model has never had any of those three fields — its real shape, fixed at task `4.4`, is
`recorded_at`/`resolved_pipeline`/`corpus` with `extra="forbid"`. Four of five tests failed at
fixture construction before reaching an assertion, and `tests/unit/weft_cli/test_render.py` has
carried a correct builder for that model since Phase 4. The implementer came back blocked on it,
again correctly, and again the repair was to the test. **Two instances one task apart makes this a
habit rather than a slip**, which is the argument for a mechanical home rather than a sentence.

**Third instance, `11.4`, same author and same session.** That test asserted
`issubclass(GraphTraversal, Stage)` — `Stage` is not `@runtime_checkable`, so that call raises
`TypeError` for *every* class, `Extractor` included, which really is a `Stage`. It constructed
`Vector((0.1, 0.2))` positionally where every one of the tree's call sites writes
`Vector(values=(...))`. And it read `__protocol_attrs__` and `__mro__` directly where
`tests/unit/weft_chunk/test_contract.py:163` has used `getattr(X, "__protocol_attrs__",
frozenset[str]())` since Phase 1, precisely because a type checker cannot see those dunders on a
Protocol. Three idioms, each with a live precedent in the tree, each written from what the API
looked like it should be.

**Three instances in one session, and what did not fail is the other half of the finding**: the
implementer refused to edit the test every time and named the divergence precisely, so the split
caught all three at the cost of a round trip each. The waste is real and bounded; the rule is what
removes it.

**Candidate home.** `phase-step` → *Red*, beside `L6.14`, whose rule this is one step more
specific than: `L6.14` says a hand-written double populates whichever fact the author had in mind;
this says the *shape* is guessed the same way, and unlike the fact, the shape has a checkable
precedent in the tree. Given the second instance, prefer something mechanical to a sentence — the
cheapest is a *Before you send* line requiring `git grep -n '<TypeName>('  tests/` for every model
and protocol a new test constructs, with the first hit read. It cost a dispatch each time rather
than a phase, which is the split earning its keep. `recurs L6.14`

### L11.18 — a task whose content needs five later tasks sat third, and nothing could see it

**What happened.** `next_task.py` routed at `11.3` — *"`weft delete` of one source reports the graph
pack's removals by kind — facts, mentions, entities"* — with `weft-kg` not existing until `11.4`
and `11.5`, facts and mentions not being `Node`s until `11.7`, and entities not being rows until
`11.8`. Measured before concluding it: `Removed.removed` (the field), `weft_cli/deletion.py:120`
(the fan-out carrying it) and `weft_cli/render.py:233` (the per-kind rendering) all landed at task
`9.3`, so **nothing whatever of `11.3` is left that does not require the pack**. The line itself
says so in its own prose — *"this line is the graph's use of it"* — and still sits third. Nothing
in the plan or the tooling could report it: `build-ledger.md` → *How to read a task line* documents
⛔ for a **phase header** against an open **gate**, and there is no mark, field or check for one
task in a phase depending on a later one. `--check-live` was green, and correctly so; the ordering
is not a claim either of its two files makes.

**Generalises to.** A dependency stated only in a task's prose is invisible to the thing that
routes the work, so at a phase's start read every task line for the artefacts it names and check
that each is built by an earlier id — the ledger's number is a stable identifier, never a
derivation of order. Corollary for writing them: a task that names an artefact a later task in the
same phase creates needs a mark, not a sentence.

**Candidate home.** Two candidates and the drain should pick one. Either a `next_task.py` live
check — for the routed phase, flag a task whose sentence names a distribution or module that no
earlier task's sentence introduces (cheap, textual, and would have fired here) — or a ⛔-shaped
mark for an intra-phase dependency, documented in *How to read a task line* beside the phase-header
one it would sit next to. The first is a check and the second is a convention; `L6.12`'s rule is
that the convention alone is prose. `recurs L9.15` on the half about a dependency filed where
nobody can tick it.

### L11.19 — the namespace rule fired at the moment of building, and the name was chosen at the moment of deciding

**What happened.** Task `11.4` named the distribution **`weft-graph`**, so `phase-step` →
*Orient*'s rule ran — *"when a decision names something that will be published, check the namespace
it will be published into, in the session that decides it"* — and **`weft-graph` is taken on
PyPI**: version `1.3.0`, seven releases from 2026-01-02 to 2026-03-02, MIT, by another author, and
it is a project *also called Weft* in the *knowledge-graph* space. Its wheel installs a top-level
module `weft` and a console script `weft = weft.cli:main`, which is this project's own binary name.
Re-measured the whole set in the same call: the eight release names were 404, and `weft-canary` and
`weft-neo4j` free, so this was one name and not a general loss. *(The pack is now named `weft-kg`,
settled at **G18**; this entry keeps the old spelling because it is the record of what was found.)*

**The rule worked. It fired three days late, and that is the finding.** `S12` chose that name on
2026-09-06 as a **scope decision**, and the check lives in `phase-step`, which is read when a
*task* is built. So between `S12` and the lookup, `01` → Phase 11's Exit, `02:2098`'s literal
`uv add weft-graph`, `09` §1, `S12`'s own row and five ledger task lines all named a distribution
that cannot be published, and every check in this repository stayed green because every one of them
is a check *about this repository* — `L6.33`'s exact sentence, one instance later.

**And the owner's own PyPI account then falsified a second claim, 2026-09-09.** `docs/README.md`
said *"all eight release names return 404 on PyPI… the index is proved by nothing"* and called one
publish the standing debt. Four distributions — `weft-generate`, `weft-embed`, `weft-command`,
`weft-llm` — were **already published on 2026-09-05**, the same day `G10` consolidated twenty
distribution names into seven, so the index had been proved four times under names this layout no
longer builds. The 404 measurement was correct and the *sentence* it supported was not: it asked
about the names the plan currently uses, and concluded about the project's history. Nobody in this
repository could have seen it; the account page could.

**Generalises to.** A check attached to the moment of *building* does not run at the moment of
*deciding*, and names are decided in sessions that build nothing. Any protocol that can settle a
name — a `05` grilling session, an `S` scope row — owes the namespace lookup in its own *Done
when*, not by reference to a skill nobody invokes there. And the lookup is not "is the name free":
it is the registry name, the import name, and the console-script name, because a collision on any
of the three reaches a user who installs both.

**Candidate home.** `docs/README.md` → *Protocol* and `05`'s session template: a *Done when* clause
requiring the namespace lookup for every name the decision fixes, with its date and result recorded
on the log row, exactly as this project already requires evidence for a count. Possibly also a
`tests/docs` check that every distribution name in `09`'s release table has a recorded lookup date
— though that one is a check about this repository again, which is the trap `L6.33` named, so the
drain should weigh it. `recurs L6.33`

### L11.20 — the check read imports with a string split, and ruff's own formatter broke it

**What happened.** `test_exit_code_tables_are_live.py`'s second ratchet reads the imports inside
`exit_code_for` to prove no branch member was added without being pinned, and it read them as
`line.split(" import ", 1)[1].split(",")` over the raw source. Adding a fifth member pushed the
`from weft_cli.eval_commands import …` line past 100 characters, `ruff format` wrapped it in
parentheses, and the check reported `exit_code_for imports ['(']` — a red gate on correct,
formatter-produced code, with a message that names a bracket. The one-line assumption was true of
every local import in that function on the day it was written and is not a property of anything.
Repaired by parsing the function body with `ast` and walking `ImportFrom.names`; watched failing
first, on the real omission (`imports ['UnknownQuestionKindError'], which _LOCAL_IMPORT_MEMBERS
does not name`), so the new parser is known to still catch what the old one was for.

**Generalises to.** A check that reads this repository's own source as text is a check against a
formatting the formatter is free to change: parse Python with `ast`, not with `str.split`, and
where a check must read source, ask what `ruff format` would do to the longest form of the thing it
is reading. The tell is a check whose failure message can contain a punctuation mark.

**And it was the fourth site of one family edit, found by a fifth mechanism.** `L8.12`'s shape,
recurring exactly: adding `UnknownQuestionKindError` to the `UnresolvedNameError` family owed edits
at four places, and the dispatch brief's own grep — written because `L8.12` says to write it —
named three (FF12's pinned frozenset, `exit_codes.py`'s dispatch branch, `manual/
troubleshooting.md`'s required heading). The fourth, `_LOCAL_IMPORT_MEMBERS`, was found only by the
red gate above. A brief's grep is better than memory and is still not the population.

**Candidate home.** An `implement-ll` sweep rather than a new mechanism: `git grep -n 'split(" import'`
and its neighbours across `tests/architecture/` and `tests/docs/`, converting each source-reading
check to `ast` where it parses Python. `recurs L11.12` — that entry is a guard refusing this
repository's own settled idiom, and this is the same shape with the formatter rather than the linter
on the other side.

### L11.21 — a service running on my machine hid the defect from every local gate

**What happened.** `G19`'s fold made `weft_qdrant` part of the default wheel, and the rung written
to satisfy fitness function 16 for it — a one-operator `index-qdrant` document — put `qdrant` into
`weft_cli.participation.stores_in_use`, which reads the whole contributed catalogue. Every project
therefore acquired Qdrant as a `weft delete`/repair participant. `uv run poe ci-checks` was **green
on it**, twice, because `compose.yaml`'s Qdrant is up on this machine and has been all session, so
the participant connected and the fan-out succeeded. CI has no Qdrant service, and it failed
immediately: `weft index corpus` exited 1 with *"failed: qdrant (weft-rag) —
ResponseHandlingException: All connection attempts failed"*, taking the README's own quickstart
with it. The owner saw it as a failure email before I saw it at all.

**Generalises to.** A local gate runs against whatever happens to be listening on this machine, and
every running service is an assumption the gate cannot see itself making. So: when a change alters
**which** backends a run touches — not how it touches them — the local green is evidence about one
machine's docker state and nothing else. The cheap discipline is to name the services a change
newly reaches and ask what a machine without them would do; the mechanical one is to run that path
with the container stopped, which `CLAUDE.md` already demands for the *opposite* failure (`L7.8`, a
container that went down and silently dropped 51 tests). This is that lesson's mirror image: there,
an absent service hid tests; here, a **present** one hid a defect.

**Candidate home.** `phase-step` → *Finish*, beside the binary-run step: a change that alters the
set of services a run touches is verified once against a machine that has none of them. A hook
cannot see this and a fitness function cannot either — both run where the services are — so the
honest home is the step that already says "run the thing, from a directory that is not this
repository", extended by "and with the container down, if what you changed is *which* services get
reached". `recurs L7.8`, inverted; `recurs L7.2` on the environment half.

### L11.22 — the shrink guard watches Postgres and Qdrant is the other half of the container

**What happened.** With `weft-qdrant-1` stopped, `uv run poe ci-checks` reported **`GATE_EXIT=0`,
2240 passed, 44 skipped**. The expected skip count is **9**, so thirty-five tests had moved from
passed to skipped and the gate said nothing: `CLAUDE.md` records that `ci-checks` "now fails a run
whose `WEFT_DATABASE_URL` claims a database that then turns out to be unreachable", and that guard
is about Postgres. `compose.yaml` brings up two services. Caught only because the brief for this
session named the expected skip count and I compared, which is a human comparison standing where a
check should be — the exact shape `L7.8` was written about, one service over.

**Generalises to.** A guard against "the suite quietly shrank" has to cover every service the suite
can skip on, not the one that was down the day it was written; and the durable form is a floor on
the skip count rather than a reachability probe per backend, because the count is the thing that
actually goes wrong and it needs no new knowledge when a third service arrives.

**Candidate home.** `pyproject.toml`'s `ci-checks` composite, beside the existing database probe:
assert the skip count is exactly what the suite expects and fail naming the difference, so the
number lives in the gate rather than in a session brief. `tests/conftest.py` already knows which
markers skip on which service (`WEFT_QDRANT_URL` is named there), so the expected count is
derivable rather than pinned by hand. `recurs L7.8`; `recurs L11.11`, which is this file already
recording that the shrink detector is covered by no test of its own.

### L11.23 — the fan-out's store filter keys on one contract, and a class under two escapes it

**What happened.** `weft_cli.fanout.participants_for` narrows `NodeStore` to `store_names` with
`if contract is NodeStore:` and nothing else. It walks contracts in `__qualname__` order and
deduplicates participants **by class**. So a class registered under `GraphTraversal` *and* under
`NodeStore` is reached first as a `GraphTraversal` — `G` sorts before `N` — joins the fan-out
there, and the `NodeStore` registration that would have met the filter is then dropped as a
duplicate. The store filter is never consulted at all, and the pack is a participant in every
project whether or not anything names it. Found while deciding whether `weft_kg` registers one
class under two contracts or two classes under one each, which is a choice nothing in the tree had
had to make before: no first-party class is registered under two contracts today, so the check that
would have caught it has never had a subject.

**Generalises to.** A filter written as *"this contract is special"* is a claim about the
**participant**, enforced against the **contract it happened to be found under**. The two come
apart the moment one plugin answers to more than one contract — and fitness function 18 forbids one
*name* under two contracts while saying nothing about one *class* under two names, which is exactly
the gap. The narrowing G13 argued for is about which backends a project connects to; deciding it
from whichever contract sorted first is deciding it by alphabet.

**Candidate home.** `weft_cli.fanout.participants_for`: apply `store_names` to the participant
rather than to the contract — if the class is registered under `NodeStore` at all, every name it
holds there must be in `store_names` for it to join, whatever contract found it first. A fitness
function is the alternative and is weaker: it would assert that no class is registered under two
contracts, which is a rule this project has no reason to want. `recurs L6.4` — a filter means what
its live population says, and this one has had a population of zero since it was written.

### L11.24 — the plan allocated a fitness-function numeral three phases before the file, and a phase in between took it

**What happened.** `01` → Phase 11's *Fitness function this phase turns on* bullet says *"Fitness
function **21**'s three clauses applied to `weft-kg` … `tests/architecture/
test_ff24_graph_is_an_ordinary_pack.py`"*, and ledger `11.5`'s *turns on* field says `FF24`. But
`tests/architecture/test_ff24_no_bytes_in_a_node.py` has held that numeral since **task 9.5**, and
`01`'s own numbered list at item 24 reads *"Bytes never enter a node"*. Two documents disagree
about what 24 is, and the one that is wrong is the one that wrote the numeral down in **2026-09-06**
for a task nobody would reach until three phases later. FF0(b)'s rule — *"numbered and filed by the
task that makes it true"* — is precisely the rule that would have prevented it, and the Phase 11
bullet quotes that rule directly above the numeral it then hard-codes anyway.

**Generalises to.** A numeral is a claim on a shared namespace, and the moment of *planning* is not
the moment of *claiming* — the namespace keeps being allocated in between. This is `L11.19`'s
namespace rule one register down: there the registry was PyPI and the gap was three days; here it
is this repository's own `tests/architecture/` and the gap is three phases. Both were checkable
with one lookup at the moment of writing, and neither was checked because a plan feels like a place
where nothing is being taken yet.

**Candidate home.** A fitness function's own territory: assert that every numeral `01` → *Phases*
attributes to a named future file agrees with the numeral that file's own directory holds, so a
plan cannot name a numeral a shipped check already has. The cheaper half is a sentence in
`phase-step` → *Orient* — a phase bullet naming an unallocated FF number states a **property** and
the numeral is filled in by the task that files it — but `L9.15` already says that in `01` and it
did not bite, so a prose repair is the weaker answer here. `recurs L9.15`; `recurs L11.19`.

### L11.25 — the session that changed the install wrote down what the install now does, without resolving it

**What happened.** `G19` folded the six add-on distributions into the `weft-rag` wheel behind
extras, and wrote the consequence into `02` §4 the same day: *"the graph pack's code ships inside
the `weft-rag` wheel and only `psycopg` — its outside library — is optional, behind the `graph`
extra."* `weft-rag` has declared `psycopg[binary]>=3.2` and `pgvector>=0.3` among its **core**
`dependencies` since that same session — they are `weft_store`'s pgvector backend, and the file's
own comment argues at length that they must never be an extra, because *"an extra that everything
defaults to needing is a footgun with a flag on it."* So `weft-rag[graph]` would install nothing
that `weft-rag` does not, ledger `11.5`'s clause *"reports `failed` naming its missing library when
the extra is absent"* has no absent case to construct, and `01` → Phase 11's *Read* bullet points
at an install line that cannot mean what it says. Found at the first task obliged to actually build
the extra, three commits later.

**Generalises to.** `phase-step` → *Orient* already says *"when a decision names something that will
be installed, install it and run one real input through it"*, and every instance recorded under it
is about a **third party's** library. This is the same rule turned inward: an extra of one's own is
also an installation, and `weft-rag[graph]` resolving to exactly `weft-rag` is a fact one
`uv pip install` — or one read of the `dependencies` list eleven lines up — would have produced. A
session that changes packaging is the session least able to check its own claims about packaging
from memory, because the memory is of the layout it just replaced.

**Candidate home.** `phase-step` → *Orient*'s installation rule, widened by one clause: an **extra
this repository declares** is checked against this repository's own core dependency list at the
moment it is named, because an extra whose contents are already unconditional is a knob that does
nothing — which `packages/weft-rag/pyproject.toml`'s own comment already refuses for `agent`, in
those words, in the same file. `recurs L6.33`; `recurs L11.19`.

### L11.26 — `plugins doctor` holds the reason and the refusal that needs it never asks

**What happened.** `02` §2 → *The trust model* promises that a pipeline naming a plugin from a pack
that failed is refused *"with its reason attached"*. Measured from outside this repository, in one
project, one process: `weft plugins doctor` prints *"qdrant (weft-rag) 2.3.0: failed (0
contributed) / reason: No module named 'qdrant_client'"*, and `weft index corpus --pipeline
index-qdrant` prints *"stage 'store' names plugin 'qdrant', which no installed distribution
registered under any contract"* followed by all 110 names that **are** registered. The reason is
sitting on a `PackReport` the process already built; the message that needed it lists everything
except it, and the one action an operator could take — install the extra — is the one thing not
said. `weft_cli.registry_bootstrap.require_plugin` does attach it, and only for a name in
`[services]`: the promise was built on that path and reads as if it covered both.

**Generalises to.** A guarantee written once over *"a pipeline naming a plugin"* has as many
implementations as there are paths that resolve a name, and only the path the author had in mind
gets it. This is `phase-step`'s own rule — *a claim about what code does is checked against its
callers* — applied to a claim in a **document** about a class of call sites rather than to one
function: `require_plugin` genuinely does what `02` says, and `02` says it about a population
`require_plugin` does not cover. The document was true of its first instance and never re-read
against its second.

**Candidate home.** Filed as carried repair `R11.3`, which is where the fix goes. The *lesson's*
home is `weft-qualities` → the loud-failure lens: when a document promises a refusal carries a
fact, enumerate the paths that raise that refusal and check each one, because "unresolvable" has
more than one raise site and only one of them was built against the sentence. `recurs L5.15` — the
producing side (`PackReport.reason`) exists and one of its two consuming sides was never wired.

### L11.27 — I told the implementer the gate was red "only on those two files" from a truncated read

**What happened.** The brief for `R11.2`'s green phase said *"`uv run poe ci-no-tests` is currently
RED, and only on those two test files — 26 pyright errors, every one of them `No parameter named
"project"` / `Argument type is unknown` against the API you are about to write."* I had run the
gate, and I had read its output through `tail -25`. The 27th error was a
`reportPrivateUsage` on an import **I** had written, it was above the fold, and it was orthogonal
to everything the brief described. The implementer implemented the brief exactly, could not get
green, and came back blocked — correctly — having spent a dispatch discovering a fact I had told it
was not there. Its `## Noticed` section is what surfaced it.

**Generalises to.** A count is evidence; a count plus the word *"every"* is a claim about the part
of the output you did not read. `tail -n` on a gate run is a sampling decision, and the failure it
hides is by construction the *first* one — which, for a checker that stops at the first subtask,
is often the only one that is not a consequence of the others. `CLAUDE.md`'s standing rule is
*measure before asserting*; the sharper form is that a quantified claim needs the whole population
in view, and a pager is not the whole population.

**Candidate home.** `implementer-brief.md`'s *Before you send* checklist, one line: the red state a
brief describes is quoted from a **complete** gate run, not from its tail — and where the brief
says "only", the count in the brief and the count in the log must be the same number, read from the
log. `recurs L10.24`, whose whole shape is a verdict swallowed by how it was read; `recurs L5.6`
one level out — here the two sides were my summary and the log, and only one was consulted.

### L11.28 — the guard refuses `git checkout --` and waves `git checkout HEAD --` through

**What happened.** `.claude/hooks/guard_history_rewrites.py` refuses the four git commands that
discard unrecoverable work, and its pattern for one of them is
`_AT_COMMAND_POSITION + r"git\s+checkout\s+--"`. I needed to revert one file to `HEAD` after the
owner decided a core edit should not stand, typed `git checkout HEAD -- <path>`, and the guard did
not fire. The command did exactly what the guard's own message describes — *"overwrites files from
the index, silently and unrecoverably"* — and the naming form that carries a commit-ish is if
anything the more destructive of the two, because it reaches past the index to a commit.

**Generalises to.** A guard written against the *spelling* of a command guards that spelling. `git
checkout -- x` and `git checkout HEAD -- x` are one operation with two syntaxes, and the pattern
was derived from whichever one the author had typed the day they wrote it — which is `L6.4`'s
population rule again: a matcher means what its live inputs say, and a matcher tested against one
input is a matcher about that input. The same gap is open for `git restore`, which is the modern
spelling of the whole family and appears in the guard nowhere at all.

**Candidate home.** `.claude/hooks/guard_history_rewrites.py`: match `git checkout` followed by
anything and then `--`, and add `git restore` beside it. Then run the hook against both spellings —
the guard's own history says a pattern here is believed rather than exercised, and this repository
has already paid twice for a hook that was not run (`CLAUDE.md`: "one that fails to import is
silently a hook that does not exist"). `recurs L6.4`.

### L11.29 — the contract bundled a capability its first outside implementer could not have

**What happened.** `11.4` published `GraphTraversal` with four members, `nearest_entities` among
them — entities ranked by cosine distance over a vector. At `11.5` the first out-of-tree
implementation was written: `examples/weft-example-graph`, a graph over ordinary Postgres tables
with **no vector column anywhere in it** and no embedder in the pack. It satisfies three members
completely and the fourth not at all. So a graph backend that walks entities and relations exactly
as the contract describes was, by the contract's own shape, a three-quarters implementer of a
capability it fully had — and fitness function 9(c)'s stranger, which is the only thing keeping
`weft_kg` from being a contract with one implementer, could only be produced by giving a worked
example a vector store it has no reason to own.

**And the tree already had the answer, one level up.** `weft_store.contract` publishes
`VectorSearch` **beside** `NodeStore` rather than folding `search_vector` into the base, for this
exact reason: a store that persists nodes need not be able to rank them, and `weft-qdrant`,
`pgvector` and an in-memory store are all whole `NodeStore`s with different capability sets around
them. The graph family is the same shape and was published without the same split.

**Generalises to.** When a contract is written before any implementation but the author's own, the
member set is a description of *that* implementation. The question that separates a contract from a
description is not "what can my backend do" but **"what is the smallest thing that is still this
capability, and what is merely something a backend might also have?"** — and a family that answers
it wrongly does not fail loudly: it fails as a partial implementer, which reads like a deficiency in
the *backend*. `weft_store`'s split is prior art the graph contract could have been checked against
before it shipped, and one grep for `class VectorSearch` would have found it.

**Candidate home.** `weft-qualities` gains a lens for publishing a contract: *before a Protocol
ships, name one plausible backend that has the capability the Protocol is for and lacks one of its
members — if you can, that member is a sibling, not a member.* `01`'s requirement 4 is what it
serves (a built-in gets no privileged path, and a first implementation must not shape the contract
around itself). `recurs L5.32`, which is the same failure at the level of a proviso rather than a
member set.

### L11.30 — the brief mandated two changes and traced what neither of them falsified

**What happened.** `11.5`'s brief told the implementer to make
`pack_settings_from_environment` offer `${env:WEFT_DATABASE_URL}` to a second pack, and to register
a plugin under `GraphTraversal`. It did exactly that and came back green on its own three files
with three *other* tests red, none of them in its write scope and none named in the brief:
`test_registry_bootstrap.py` asserts that function's return value **exactly**, twice; and
registering under `GraphTraversal` put that contract on fitness function 9c's left side, where it
had no out-of-tree stranger — while the brief's own *Not in scope* section said the stranger was
"a later step of this task and not yours". So the brief's *Done when* and its *Not in scope*
contradicted each other, and the implementer was the one who had to notice.

**And the rule was already written, in the file the brief was copied from.**
`implementer-brief.md`'s *On the failing test* paragraph says: *"If the brief mandates a signature
change, grep for every caller of the old signature — tests included — and either update them in
Red or name them here"*, and it records task 6.18 doing precisely this and getting precisely this
result. I read that paragraph, applied it to nothing, and reproduced the instance it documents.

**Generalises to.** The rule is written about a *signature* change and both of these were **behaviour**
changes — a return value's contents, and a registry gaining a key. That narrowness is what let me
read the paragraph and not see myself in it. The general form is: **a brief mandates a change to a
value some test asserts, and the author owes the grep for that value, not for that name.** For a
registry it is stronger still, because there is no name to grep at all: what changed was a *set*,
and the checks over that set are architecture tests nobody would think to look for from inside one
module. The cheap version is a full gate run before the dispatch rather than after — which the same
brief already promises and which would have shown all three.

**Candidate home.** `implementer-brief.md`'s *Before you send* checklist: widen the signature clause
to *any value a brief changes* — return contents, a registered set, a version constant — and add
the one mechanical step that catches all of them without foresight: run `uv run poe ci-checks` (not
`ci-no-tests`) once before dispatching, and either fix what the change already broke or name every
failure in the brief. `recurs L5.14`, `recurs L11.27` — that entry is this one's other half, both
bought by the same two dispatches: there I described the red state from a truncated read, here I
did not produce it at all.

### L11.31 — the check written to prove a credential was absent printed it

**What happened.** `11.6`'s property is *"a corpus indexed with **no model and no credential**"*, so
while running the binary I went to show the credential was not there:
`echo "OPENAI_API_KEY=${OPENAI_API_KEY:-<unset>}"`. It **was** there — exported in the session's
environment — so the shell substituted the real key and printed it in full into the transcript and
the job log. The run that followed was still a valid demonstration (`index-with-cooccurrence` has no
model-calling stage and cannot reach a provider), but the owner's key had to be rotated because of
a line whose only purpose was to prove a negative.

**Generalises to.** `${VAR:-fallback}` renders the *value* and shows the fallback only in the case
you were not worried about — so as a check for absence it is silent exactly when it is right and
loud exactly when it is wrong, which is the inverse of what any assertion should do. The general
rule: **a check for the absence of a secret must never be able to render the secret.** Ask the
question about the *name*, not the value — `[ -n "${VAR+x}" ]`, or `env | cut -d= -f1 | grep -x`.
This is `L9.28`'s shape moved from data to secrets: an assertion whose two sides come from one
source, where one of those sides is a credential.

And the second half, which is about where it was printed rather than what: a terminal transcript is
**append-only and forwarded**. There is no redaction after the fact, so the cost of this mistake is
paid entirely at the moment the command is typed. `weft_store`'s `dsn` is a `SecretStr` and
`weft_kg`'s refusal deliberately names the setting rather than its value — the code already knows
this rule and the shell around it did not.

**Candidate home.** `phase-step` → *Finish*, item 4, beside "run the thing … including its failure
path": when a task's property is the **absence** of a credential, prove it by the name being unset
or by the run succeeding where a provider is unreachable — never by rendering the variable. The
mechanical form is a `PreToolUse` guard on `Bash` refusing a command that expands a variable whose
name matches `*_API_KEY|*_TOKEN|*_SECRET|*PASSWORD*` into stdout, which is the same
shape as the four destructive-git refusals: a prohibition that needs a mechanism rather than a
stronger sentence (`L9.56`).

### L11.32 — every prompt in this tree fails `Prompt`, and one generic hid it from four packs

**What happened.** `11.7`'s stage is the first in the tree to hand a concrete `TypedPrompt`
subclass to `weft_prompts.cascade.execute` directly, because `weft_cli.run_services.
build_index_services` deliberately publishes no `StageLookup` on the ingest path. pyright refused
it: *"`ExtractFactsPrompt` is incompatible with protocol `Prompt` — `version` is not present."*
I measured rather than assumed it was this class's fault, on a prompt nobody had touched:
`_: Prompt = PassageRelevancePrompt()` fails identically. **No registered prompt in this
repository satisfies its own contract to a type checker**, and none ever has.

**Generalises to.** The two-audience versioning pattern every contract here shares — `version`
declared under `if TYPE_CHECKING:` and assigned to the Protocol object after its class body — is
what keeps `version` out of `__protocol_attrs__` so `isinstance` stays honest about *behaviour*.
The cost, never written down, is that the same declaration makes the Protocol **unsatisfiable by
assignment**: a checker requires a member no implementer carries. Nothing noticed for four packs
and three phases because exactly one function stands between every caller and the check —
`StageLookup.build_capability[T](Prompt, name) -> T` infers `T = Prompt` from the call site and
never looks at the concrete class. So the tree has a contract whose implementers all fail it,
proved satisfiable only by a generic that declines to ask.

The general rule: **a generic that infers its return type from the call site is not a check, and a
population validated only through one is unvalidated.** This is `L6.4`'s population rule in a type
system — a marker means what its live instances say — and `L5.19`'s vacuity rule at the same time:
a check nothing has been seen failing may be a check nothing can fail.

**Candidate home.** Two, and they answer different halves. *(a)* `phase-step` → *Red*: when a task
first uses an existing contract in a new way, assert the concrete class against the contract in
that pack's own `test_contract.py` — `assert_type` or a bare annotated assignment — so the
population is checked where the generic is not standing. *(b)* Whether the pattern itself should
change is a question about **every** contract in the tree, not about this stage, and it belongs to
**G9**, which already owns contract versioning and the two audiences. Filed there rather than
repaired here; `11.7` uses `cast(Prompt, ...)` with the measurement written at the call site, which
is a statement of a true fact (the runtime `isinstance` passes) rather than a suppression.

### L11.33 — 6.24's defect came back, and no code changed to bring it

**What happened.** `_record_sources` records a `SourceRecord` in the store `_store_stage_id_of`
names, whose docstring said *"the one stage registered under the `NodeStore` contract"*. That was
true when 6.24 wrote it. `11.5` then shipped `index-with-graph`, a document naming **two** stores,
and from that commit the second store's `put_source` was never called: `kg_sources` empty after a
real `weft index`, `list_sources()` answering `()` about nineteen nodes it was holding, `reconcile`
with nothing to converge. Found at `11.7` by running the binary from outside the repository, with
2,385 tests green. Repaired as `R11.4`.

**Generalises to.** `L6.15` exactly — *a code invariant asserting "every shipped pipeline" over
documents anyone may write* — and this is its second instance, so the recurrence is the finding
rather than the defect. What is new is the **trigger**: no line of `ingest.py` changed. A YAML file
in a different distribution falsified a sentence in a Python docstring, and nothing in this
repository connects those two facts. That is why the usual defences all missed it: review saw no
diff, the type checker saw no type change, and the unit suite's store doubles answered the question
the running system could not — which is the *same* module's own recorded lesson (`L6.14`), now
twice.

The general rule: **when a document becomes able to name two of something, every "the one" in the
code that reads that document is a claim that just expired.** The moment to look is the commit that
ships the *document*, not the commit that changes the code — because there will not be one.

**Candidate home.** `phase-step` → *Verify*, beside the `path:line` rule: a task shipping a pipeline
document that names two stages of one contract greps for the singular derivations of that contract
(`_store_stage_id_of`, `_extractor_name_of` and their kin) before it ticks. The mechanical form, and
the better one, is a **fitness function**: for each contract a shipped document names more than once,
assert that no first-party derivation of that contract returns a single id — which is checkable
because both sides are in this tree, and which would have fired at `11.5` rather than at `11.7`.

### L11.34 — the architecture suite reads `git ls-files`, so a new file is invisible until it is staged

**What happened.** `11.7`'s implementer reported `test_release_licensing.py::
test_every_enumerated_source_work_is_actually_carried` as failing and correctly diagnosed it as
untracked-file noise: the sweep walks `tracked_files()`, so `weft_kg/atomicity.py` — which carries
the repository's first `weft-prior-work` span — did not exist as far as the check was concerned,
while `README.md` enumerated the source work it was supposed to match. `git add` turned it green
with no edit to anything.

**Generalises to.** `L8.10` twice already: FF17 read `git ls-files` and could not see a file written
in the same task (Phase 8, then again at `11.4`). This is the third instance and the first in a
different check, which is the part that makes it a class rather than a bug — *any* architecture
check whose population is `tracked_files()` reports on the last commit plus whatever was staged,
never on the tree the author is looking at. So a test-first task's gate is red for a reason the diff
does not contain, and the failure names a file rather than the staging.

The rule: **a check that walks `git ls-files` is asking about the index, not about the working tree,
and a task that adds a file must stage it before that check means anything.** It is not a defect in
the checks — `tracked_files()` is what makes them checks about the *repository* rather than about a
scratch directory — it is a precondition nothing states.

**Candidate home.** `phase-step` → *Finish*, item 1, beside the environment preconditions
`CLAUDE.md` already lists for a meaningful gate (committed lockfile, container up, expected skip
count, cold lint cache): **new files staged**. The mechanical form is a line in the gate task itself
— `git add -N` on untracked, non-ignored files before the architecture suite runs, which changes no
content and makes the population the author's tree — or, failing that, `tracked_files()` raising
when the working tree holds an untracked file matching a suffix it sweeps, so the check says
*"stage this"* rather than *"this file is missing"*.

### L11.35 — I rewrote six assertions with find-and-replace, and lint caught the harmless one

**What happened.** `11.8` changed `put_entity`'s return from an entity id to an alias id, so six
tests that had passed that return into `neighbourhood` or `nodes_for_entities` needed the canonical
id looked up instead. I patched them with a scripted find-and-replace. One left a dead assignment,
which `ruff`'s `F841` caught and the implementer reported. Fixing *that* line is what made me read
the assertion under it — `assert found[0].id == await _entity_of(walk, "Chucri")` — where
`_entity_of` calls `entities_by_name`, the function that test exists to check. **A comparison whose
two sides are the same call.** It passed, it would have passed against any implementation, and
nothing in the gate could ever have failed it.

**Generalises to.** `L5.6` and `L9.28` — a comparison whose two sides come from one source cannot
disagree — arriving through a door neither of them names. Both are written as rules about *writing*
a test. This one was not written; it was **transformed**, and the transformation was mechanical and
correct at the level it operated on (every use of the changed value now fetches the right kind of
id). What a find-and-replace cannot see is that substituting a helper into an assertion can make
that assertion tautological, because the property being asserted lives in the relationship between
the two sides and a text edit does not know there is one.

The rule: **a bulk edit across assertions is not a refactor, it is re-authoring every one of them,
and each has to be re-read as an assertion afterwards.** The sharper form, because it names what to
look for: after substituting a helper into a comparison, ask where each side now comes from — if
the answer is the same function, the test is gone whether or not it is green.

And the asymmetry is the part worth keeping: **lint caught the line that was merely dead, and
nothing at all caught the line that had stopped testing.** The two defects were three lines apart
and came from one edit.

**Candidate home.** `phase-step` → *Red*, beside the existing two-sides rule, as the case that rule
does not currently cover: when a task changes a published return type, the tests that consumed it
are rewritten, and a rewritten assertion is a new assertion. The mechanical form worth considering
is narrower than a rule and might actually fire: a check that flags an assertion whose two sides
resolve to the same first-party call — cheap to state, hard to write well, and worth a note rather
than a task until a third instance arrives.

### L11.36 — I used `pgrep` as a subagent's done signal and gated a mid-edit tree

**What happened.** Three implementers ran for `11.9`. For the third I wanted to know when it had
finished so I could run the gate, and rather than wait for the completion notification I watched
the tree: I polled `git diff --stat` until the file stopped changing, then polled `pgrep` for
`pytest` and `pyright` until neither was running, and concluded it was done. It was not. The agent
was between commands. I staged the tree and ran the full gate against a half-written `store.py`,
got four failures, and spent a diagnosis cycle on one of them — a second `full` pass asking the
model a question it had already answered — which the agent had *already fixed* in the edit it made
after my gate started. My own reproduction against the container then showed the behaviour was
correct, which is when the timeline became obvious.

**Generalises to.** The harness states this plainly — *"you will be notified automatically when it
completes"* — and I substituted an inference for a fact that was going to be handed to me. Every
proxy I picked is a real signal of *something*: a quiet file means no write is in flight this
instant, an absent `pytest` means no test is running this instant. Neither is a statement about
whether the agent has more work to do, and a heuristic that answers a narrower question than the
one asked is `L6.4`'s shape — reading a marker's definition rather than its population — in the
domain of process state.

The rule: **a subagent is finished when its completion notification arrives, and at no other
moment.** There is no tree-shaped or process-shaped substitute, because the agent's own plan is not
observable from outside it. If waiting is genuinely wrong, the fix is to send it a message, not to
guess from `pgrep`.

The cost was small and the shape is not: **a gate run against a tree somebody else is still
editing is not a gate**, which is `L6.22`'s rule stated for a different overlap than the one it was
written for — that one is about two suites sharing a container, this one is about one suite and one
author sharing a working tree.

**Candidate home.** `phase-step` → *Green*, beside the existing "keep off the tree until the agent
returns" paragraph, which currently says what not to *do* and does not say how you know it has
returned. One sentence: the notification, and nothing else.

**Second instance, 2026-09-10, one task later, and it is worth more than the first.** At `11.11` I
again did not wait for the notification — this time polling for the source files to stop changing
and for no `pyright` to be running, then starting the full gate. The agent was still in its own
verification run. Two suites against one container is `L6.22` exactly, and it surfaced as
`tests/docs/test_readme_is_enough.py` failing with *"`weft ask` returned no ranked result"* — a
README-path regression that did not exist. It passed alone, and passed again in the next gate.

**What makes the recurrence the finding**: I had written the rule the day before, in this file,
and still substituted a cleverer proxy for it. The proxies get better each time — file hashes, then
process liveness — and every one of them answers a narrower question than *has this agent finished*.
The remedy is not a better proxy. There is a notification; nothing else is evidence. That is now
two costs in two consecutive tasks, both paid in a diagnosis cycle chasing a defect that was never
there, which is the shape `L10.24`'s hook exists for one genre over — a rule at three instances
buys a mechanism rather than a louder sentence, and this is at two.

### L11.37 — I diagnosed against a wheel `uv` was not running

**What happened.** After reverting a defect found by the binary, I rebuilt the wheel, confirmed the
revert with `unzip -p <wheel> weft_cli/commands.py | grep -c`, ran the binary again, and got the
identical `DuplicateServiceError`. I concluded the defect was **not** mine — it had to be somewhere
else in the tree — and said so, twice, before a stack trace showed the running code was
`.cache/uv/archive-v0/JK1-.../weft_cli/commands.py`, at a line number that only existed in the
version I had just deleted. `uv run --with <path.whl>` was serving a previously extracted archive
for a wheel of the same name; `uv cache clean weft-rag` did not evict it either. The wheel I
inspected and the code that ran were two different files, and every check I made was of the first.

**Generalises to.** `L7.6` — a metadata API answered one way under an editable install and another
under a real one — and `L9.1`, ruff's per-file cache holding a verdict about a tree that had
changed. Same shape a third time: **an artefact and the thing that runs it are two facts, and a
build step is not a guarantee that the second one moved.** What makes this instance worth writing
down separately is where it sent me: not to a wrong answer about the code, but to a wrong answer
about *whose* code, which is the most expensive kind — I was one step from re-opening a settled
seam in `weft_cli` to fix a defect that no longer existed.

The rule: **verify the environment by asking the environment, never by asking the artefact you
handed it.** One line of the running module's `__file__` and a `grep` of *that* path would have
ended it immediately. The cheap general form: when a rebuild does not change the behaviour, the
first hypothesis is that the rebuild did not reach the runtime, and it is falsifiable in one
command.

And the structural repair, because "remember to check" is not one: **an installed-artefact run gets
a fresh, explicitly-pathed environment**, not a cache-mediated one. `uv venv` plus
`uv pip install <wheel>` into a directory this session owns costs seconds, has a `site-packages` you
can `grep`, and cannot serve you something else. That is what the measured `11.9` run finally used.

**Candidate home.** `phase-step` → *Finish*, item on running the binary, which says to run it from
a directory that is not this repository and does not say how to be sure the binary is the one you
just built. The concrete form is short enough to be a command rather than a rule.

### L11.38 — my brief named the mechanism, and the mechanism was not sufficient

**What happened.** `11.9`'s brief told the implementer to put `a.entity_id IS DISTINCT FROM
b.entity_id` in the band query and said, in the docstring text it dictated, that this clause is
*"exactly what makes a second `full` pass ask nothing after the first merged the pair."* I derived
that by reading the query. It is false. The cheap resolution pass runs before the expensive one, in
**every** mode, and it re-points every alias to its own cluster's representative — so a pair the
model had merged was split again by the very next pass, landed back in the band, and was paid for a
second time. The implementer found it by writing the test the brief required, watching it fail, and
probing the real container; the repair it made — feeding each alias's current entity-mates back in
as extra similar pairs, so the pass can only ever merge and never split — appears nowhere in the
brief. It reported that clearly, which is the only reason the interaction is written down rather
than discovered later by somebody wondering why a bill kept arriving.

**Generalises to.** `CLAUDE.md`'s own rule: *a claim about what code does is checked against its
callers, never against its name, its docstring, or a comment's stated scope.* The instance it does
not currently name is **a brief**. A brief's *Already decided* section is where the author is most
confident and least checked: it is written from reading, it is handed to something that cannot
argue with it about design, and its sentences become docstrings in the tree verbatim. This one
would have shipped as a comment stating a guarantee the code did not provide. `L11.30` is the
neighbour — a brief that mandated two behaviour changes and traced what neither falsified — but
that one over-specified an outcome; this one **under-specified an interaction** and then asserted
the gap shut.

The rule: **a mechanism named in a brief is a claim about the tree and gets checked like one — by
reading what runs before and after it, not by reading it.** The sharper form, because it names
where to look: when a brief says *"X is what makes Y true"*, find the other things that touch Y. If
any of them runs unconditionally, X is at best half the answer.

And the part worth keeping about the loop: **the split did its job.** A test I wrote from the
documents demanded an outcome; an agent that could not edit that test had to make the outcome real
and could not make it real by narrowing the assertion. That is exactly what `phase-step` says the
split buys, working on the case it was designed for — and it only reached me because the agent said
so in its report rather than quietly fixing it.

**Candidate home.** `phase-step` → *Red*, in the paragraph on writing *Already decided*: a
mechanism the brief names as the reason a test will pass is a claim to verify before sending, not
after. Possibly also `references/implementer-brief.md`'s *Before you send* checklist, which is
where a one-line check would actually fire.

### L11.39 — two paragraphs into `02` invalidated eight citations, and nothing could see it

**What happened.** `11.9` added two blockquotes to `docs/02-extension-model.md`. Starting `11.10`
I went to read its owner reference, `02:818`, and found a G13 note about `SourceDeletable`. Auditing
every line-numbered citation into that one document turned up **seventeen**, of which **eight** had
been shifted by my own insertions and **four more** (all spellings of `02:818`, in `01`, `docs/
README.md` and the ledger, quoted as *"as `02:818` requires of every retriever"*) were wrong
**before** I touched the file — the retriever rule has always been at what is now 981. Every one
resolves now, checked by resolving each citation and printing the line it lands on.

**Generalises to.** `L9.34` said a `path:line` an agent reports is a lead rather than evidence, and
that fitness function 17 *"proves a path resolves, never that the line says what the sentence
claims"*. This is the same gap from the other end: not a citation written wrong, but a correct
citation **made** wrong by an edit somewhere else, in a file the editor never opened. The failure
has no symptom at all — the path still resolves, FF17 stays green, and the number quietly points at
a neighbouring paragraph that reads plausibly enough that nobody checks.

The rule: **a line number into a living document is a dangling pointer with no compiler.** Editing
a `docs/` file above line N invalidates every citation to a line below N, across every other
document, silently — and the edit that does it is usually a two-line addition nobody would think of
as a breaking change.

Two mechanical repairs are available and the cheap one is worth more than it looks. **Cite the
section, not the line** — `02` § *The store contract family* survives any edit above it, and every
citation in this tree that names a heading (`02:97`, `02:567`, `02:2081`) was still correct after
my insertions while every one naming a paragraph was not. **Or check them**: resolving a `NN:line`
citation and asserting the target still contains a distinctive token from the citing sentence is a
real check, and the audit above was fifteen lines of Python — the same fifteen lines, run in
`tests/docs/`, would have failed on my own commit.

**Candidate home.** `tests/docs/`, as a check with the shape `test_pack_guide_samples.py` already
has for quoted code — a citation and the text it claims, compared. Failing that, `CLAUDE.md` →
*Claims need evidence*, which currently says to measure before asserting and does not say that a
measurement expires when somebody edits the file above it. The strong form is a convention change:
new citations name sections, and line numbers are used only where a section would be too coarse.

### L11.40 — every test helper in this repository is exempt from redefinition detection

**What happened.** Writing `11.10`'s tests I added a module-level `def _services_registry()` to
`tests/unit/weft_cli/test_run_services.py`. One already existed 155 lines above it. Python rebinds
at module scope, so the three pre-existing tests that called the first one silently began calling
mine, and failed with `UnknownPluginError: no 'fake' is registered for NodeStore` — a message about
a registry, three files away from the cause. The implementer found it, could not fix it (it may not
edit tests), and reported it, which is the only reason it did not reach a commit.

**The part worth writing down is why lint was silent.** `F811` (redefinition of an unused name) is
selected here and is *not* in `tests/**`'s per-file ignores, so it should have caught this. Measured
against ruff 0.14, `--isolated --select F811`:

| definition | F811 |
|---|---|
| `def helper()` twice | **fires** |
| `def _helper()` twice | silent |
| `def __helper()` twice | silent |

**`F811` exempts any name matching `lint.dummy-variable-rgx`**, whose default matches every
underscore-prefixed name. And every test helper in this tree is underscore-prefixed by
convention — `_ctx`, `_node`, `_registry`, `_reply`, `_deps` — so **the entire population the rule
would protect is exactly the population it exempts.** The check is selected, applies to the right
directory, and can never fire on the code it would help.

**Generalises to.** `L6.4` — read the population, not the declaration — aimed at a linter. "F811 is
selected and applies to `tests/`" was true and was recorded as such (`L10.19`, where the rule was
*declined* on that basis). What nobody asked was which names it actually inspects. A check whose
scope is stated in a config file and whose *effective* scope is decided by a regex somewhere else is
a check whose coverage has to be measured rather than read.

**And there is a measured repair, which is why this is filed rather than merely noted.** One line:

```toml
[tool.ruff.lint]
dummy-variable-rgx = "^_$"
```

It makes F811 fire on `_helper` while still exempting a bare `_`. Cost, measured over the whole
tree with `ruff check --no-cache --statistics --config 'lint.dummy-variable-rgx="^_$"' .` against
the same run without it: **two** new findings, both `B007` (unused loop control variable), and zero
new `F811` or `F841`. Two lines to fix, for a defect class that is currently invisible in every
test module in the repository.

**Candidate home.** `pyproject.toml`'s ruff config, with the measurement above in the comment beside
it — that file already carries argued comments for `per-file-ignores` and for the hooks directory,
and this is the same genre. `L10.19` should be re-read at the same time: it declined a rule on the
strength of F811 being selected, which turns out to have been true and inoperative.

### L11.41 — I wrote two manual transcripts from a brief, and both were wrong

**What happened.** `11.11` added two `manual/troubleshooting.md` entries, each with a `$ weft …`
block showing what the operator sees. I wrote both from my own implementer brief, before the code
existed. Then I ran the binary. **Neither message matched.** `EmptyCorpusError` actually said
`propose_schema found no facts at or above min_count=2` — leaking a Python function name at an
operator — and `MalformedSchemaFileError` said `broken.toml does not hold a valid curated graph
schema`, not the sentence I had invented for it. Both entries were fixed against real output; the
first message was itself repaired, because naming a function is not something an operator can act
on.

**And `tests/docs/test_troubleshooting_coverage.py` was green throughout.** That check asserts a
`### \`ErrorName\`` **section exists** for every `WeftError` subclass in the tree. It has no
opinion about what the section says, so a fabricated transcript passes it exactly as a real one
does — and the ratchet's greenness reads, to whoever runs it, as the manual having been checked.

**Generalises to.** `08` §3's rule is that a manual is **checked, not trusted**, and `L6.19` is the
sharper version: a change to a command's output falsifies every worked transcript of it, and *only
the executed ones fail the gate*. This is the same gap entered from the other end — not a transcript
that rotted, but one that was never true, in a section a coverage check certifies as present. The
common cause is that a transcript is the one part of a document that is a *measurement*, and I
wrote it the way I write prose.

The rule: **a `$` block in a manual is output, and output is copied from a run.** If the code does
not exist yet, the entry is not ready to write — write it after the binary run, in the same pass
that proves the command works at all.

**A mechanical repair exists and is worth more than the rule.** `tests/docs/test_pack_guide_samples.py`
already compares a tagged sample against the file it claims to quote, byte for byte; the same shape
applied here would be a check that each troubleshooting block's *message text* appears in the raise
site it documents. Not the whole block — prose around it is a person's judgement, and `09` §3 keeps
CLI prose unpromised — but the quoted sentence is either in the tree or it is fiction. That would
have failed on both of mine.

**Candidate home.** `tests/docs/`, beside the coverage ratchet it complements: coverage asks
*is there an entry*, this would ask *is the entry's transcript real*. Failing that, `phase-step`
→ *Finish*, which already says to run the binary and read what it prints, and does not say that
what it prints is what the manual must contain.

### L11.42 — a walk is undirected and a fact is not, and one column carried the difference

**What happened.** `weft graph bridges` (task `11.13`) walks `kg_relations`, which stores a
direction. Its SQL doubles every row into both directions — the identical thing
`GraphWalk.neighbourhood` has always done, and right, because *reach* does not care which way a
relation points. This command then **prints the predicate**, and the doubled row had lost which way
the fact was written: a hop the walk traversed backwards printed `Azouz --authored-by--> mRMR`
when the corpus had said *mRMR was authored-by Azouz*. A false claim, one arrowhead wide, standing
beside a citation that was perfectly real — `CLAUDE.md`'s own "plausible answer against the wrong
data", in the output of the command whose whole purpose is to be evidence.

**How it was caught is the finding.** Not by a test — every test in `test_graph_bridges.py` used a
fixture whose relations happened to run the same way as the walk, so none of them could see it. It
was caught by the dispatched implementer **flagging its own decision** in its report: *"`BridgeHop.
source`/`target` are the canonical entity names oriented to the overall path direction… none of the
shipped tests exercise a relation stored in the reverse orientation."* It said so plainly, called
it the only choice consistent with the properties as specified — which was true — and did not know
that the properties as specified were what needed changing. `implementer-brief.md` § *Review what
comes back* asks *did it decide something?*; this is the case where the answer arrived in writing
and was still one read away from being missed.

**Generalises to.** When a representation gains a field the source representation **ordered** — a
predicate, a signature, a from/to, an actor — every place the old code was free to treat the two
directions as interchangeable becomes a place that must now choose, and the choice is invisible in
a fixture that is symmetric. So: *before reusing an undirected traversal to print a directed
statement, find the one input where the two disagree, and make a test out of it.* The reused code
being correct is not the question; what it was correct **about** is.

**Candidate home.** `phase-step` → *Red*, beside the existing rule that a comparison whose two sides
come from one source cannot disagree. This is its twin one level up: a *fixture* whose two sides
cannot disagree — every relation in it stored in the direction the walk happens to take — makes a
whole class of assertion vacuous without any assertion looking wrong. Alternatively `implementer-
brief.md` → *Review what comes back*, whose item 2 could say that a decision the agent **volunteers**
is the highest-value line in its report and is read before the diff, not after it.

### L11.43 — the Exit criterion is a command line, and no part of it is the command

**What happened.** `01` → Phase 11's Exit ends with `weft eval compare graph-then-generate
retrieve-then-generate --baseline retrieve-then-generate`, restricted to `kind =
requires-graph-hop`. Run from outside the repository against installed wheels, **none of that
invocation is how the shipped command works.** `<a>` and `<b>` are **run ids** (`runs/<uuid4>.json`
filename stems), not pipeline names. And `--baseline` is matched against
`RunRecord.resolved_pipeline`, which is the **ingest** pipeline — a run record carries no query
pipeline at all: its seven keys are `active_distributions`, `corpus`, `durations`, `metrics`,
`model_versions`, `recorded_at`, `resolved_pipeline`. So a comparison of two *query rungs* can
never be judged against a *query rung* baseline, because nothing persists which query rung a run
used. `--baseline retrieve-then-generate` refuses at exit **4**, correctly and loudly: *"names no
persisted baseline repetition under 'runs'… Pipelines actually run: index-with-cooccurrence."*

**The exit is met in substance**, and that is what makes this a documentation defect rather than a
gap: naming the ingest pipeline both runs share reports `outside-baseline-spread` on every metric,
`Δ-1.000` against a baseline spread of `0.000-0.000`, with the zero-width caveat `09` §4.3 requires
printed beside it. The instrument works. The sentence that specifies it does not run.

**Generalises to.** An exit criterion, a manual, a docstring or a ledger line that states a
**literal command line** is making a claim about a CLI surface, and this repository checks worked
transcripts (`08` §3, `L6.19`, `L11.41`) while checking exit criteria not at all. `01`'s Exit
clauses are the most load-bearing sentences in the plan and the least checked. The rule:
*a command line written into a document is output-shaped, so it is run before it is written, on the
same footing as a `$` block in `manual/`* — and where it cannot be run at the time the phase is
planned, it names the property rather than the invocation.

**Candidate home.** Two candidates and they are different sizes. The small one: `phase-step` →
*Close the phase* item 4 already says to re-check the exit **against what exists**; it could say
that a clause containing a command line is re-checked *by running it*. The mechanical one: extend
`L11.41`'s proposed transcript checker to `01`'s Exit blocks — a fenced or backticked `weft …`
invocation in `docs/` is either parseable by the shipped argparse tree or it is fiction, and the
argparse tree is already built from the registry by `weft_cli.cli._add_command_level`.

## When the queue is empty

That is the healthy state, and it means the last drain finished. What was learned lives in
`lessons-archive.md`, session by session, with the edges between entries — which is where the
question *have we been here before?* is answered, and where an on/off cycle becomes visible.
