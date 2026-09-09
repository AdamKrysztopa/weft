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

**Candidate home.** `phase-step` → *Red*, beside `L6.14`, whose rule this is one step more
specific than: `L6.14` says a hand-written double populates whichever fact the author had in mind;
this says the *shape* is guessed the same way, and unlike the fact, the shape has a checkable
precedent in the tree. It cost a dispatch rather than a phase, which is the split earning its
keep. `recurs L6.14`

### L11.18 — a task whose content needs five later tasks sat third, and nothing could see it

**What happened.** `next_task.py` routed at `11.3` — *"`weft delete` of one source reports the graph
pack's removals by kind — facts, mentions, entities"* — with `weft-graph` not existing until `11.4`
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

**What happened.** Task `11.4` names the distribution `weft-graph`, so `phase-step` → *Orient*'s
rule ran — *"when a decision names something that will be published, check the namespace it will be
published into, in the session that decides it"* — and **`weft-graph` is taken on PyPI**: version
`1.3.0`, seven releases from 2026-01-02 to 2026-03-02, MIT, by another author, and it is a project
*also called Weft* in the *knowledge-graph* space. Its wheel installs a top-level module `weft` and
a console script `weft = weft.cli:main`, which is this project's own binary name. Re-measured the
whole set in the same call: the eight release names are still 404, and `weft-canary` and
`weft-neo4j` are free, so this is one name and not a general loss.

**The rule worked. It fired three days late, and that is the finding.** `S12` chose this name on
2026-09-06 as a **scope decision**, and the check lives in `phase-step`, which is read when a
*task* is built. So between `S12` and now, `01` → Phase 11's Exit, `02:1893`'s literal
`uv add weft-graph`, `09` §1, `S12`'s own row and five ledger task lines have all named a
distribution that cannot be published, and every check in this repository stayed green because
every one of them is a check *about this repository* — `L6.33`'s exact sentence, one instance
later.

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

## When the queue is empty

That is the healthy state, and it means the last drain finished. What was learned lives in
`lessons-archive.md`, session by session, with the edges between entries — which is where the
question *have we been here before?* is answered, and where an on/off cycle becomes visible.
