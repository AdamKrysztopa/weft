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

### L9.2 — a sibling lower bound was never checked against what is publishable

**What happened.** `packages/weft-openai/pyproject.toml:14`, `packages/weft-pdf/pyproject.toml:19`
and `packages/weft-qdrant/pyproject.toml:28` each declare `weft-rag>=2.1.0,<3.0.0`. `weft-rag` is at
`2.2.0` and **`2.1.0` never reached the index** — all seven release names return 404 on PyPI — so the
bound is a claim about a version that does not exist and never will. Next door,
`packages/weft-agent/pyproject.toml:12,16` carries a written comment about *this exact hazard* and
uses `>=2.2.0`. So the repair was made once, correctly, with its reasoning recorded, and three
siblings carrying the same defect were not touched. Caught by a planning agent querying the index,
not by the gate: FF10 compares the release job's matrix against the workspace, and **nothing
compares a declared bound against what is publishable**.

**Generalises to.** A dependency lower bound is a claim that that version exists on the index and
satisfies its own imports, and it is unfalsifiable until the index has it — so it belongs in the
gate, not in the memory of whoever fixed the first instance: when a bound is repaired in one
manifest, the check that made it necessary is re-run across every sibling that declares one.

**Candidate home.** A fitness function beside FF10 — every sibling bound `>=X` has X either equal to
the version being published or already on the index — plus the pre-flight in `09-release.md`. This is
**`L6.13` recurring** (*a repair specified from one failing instance narrows to that instance*), which
is itself the finding: that rule is archived and it did not bite here.

### L9.3 — advice that named a CI run id went stale silently and would have published a broken set

**What happened.** `ADAM_TODO.md` item 2 advises `gh run rerun 33967852159`. That run belongs to tag
`v2.1.0` (`9a0a972`), whose tree carries `weft-rag 2.1.0`; `main` now carries `2.2.0`, and
`weft-agent` requires `weft-rag>=2.2.0`. **A rerun republishes the tagged tree, not `main`**, so
following the advice would publish a `weft-rag` that cannot satisfy a sibling in the same release
set. Nothing marked the advice stale when the version moved, and nothing could have: the id still
resolves and the command still succeeds.

**Generalises to.** Written advice that names a mutable external coordinate — a CI run id, a tag, a
job number — is valid only while the tree behind that coordinate still matches the repository, so
record the **act and its precondition** rather than the id; otherwise the advice fails silently,
confidently, and against a real index.

**Candidate home.** `ADAM_TODO.md`'s own convention, and `09-release.md` §6's procedure. Related to
**L9.5** — both are pointers to a coordinate that moves without either file being edited.

### L9.4 — three documents state a platform behaviour that the platform's own help page contradicts

**What happened.** `packages/weft-rag/pyproject.toml:46`, and per the same measurement
`.github/workflows/release.yml:31` and `docs/09-release.md:121`, state that PyPI **cannot delete a
project**. PyPI's help page says the opposite, verbatim: deletion is *"permanent and irreversible,
without exception"*, and *"deletion of a project makes it uninstallable, and releases the project
name for use by any other PyPI user."* The claim was written from memory on the day of the publish
incident and never measured. The **position** it supports — keep the four retired names claimed — is
right, and for a stronger reason than the one recorded: deleting them would release
`weft-command`, `weft-embed`, `weft-generate` and `weft-llm` to anyone. The correct word is *must
not*, not *cannot*.

**Generalises to.** A claim about a third party's platform is a factual assertion about the
environment this project runs in, and it carries the same evidence obligation as a claim about the
tree — cite the platform's own documentation, especially where a decision rests on it, because a
plausible-sounding platform fact is exactly the kind that is never re-checked.

**Candidate home.** `CLAUDE.md` → *Claims need evidence*, whose scope today is claims *about the
tree*. The three sites need correcting in the same act.

### L9.5 — a document cited a list by item number, and the list renumbers itself

**What happened.** `docs/product-direction.md:175` cites `ADAM_TODO.md` **items 6 and 7** for the
repository-visibility and token consequences. They are now items 5 and 8, because `ADAM_TODO.md`
renumbers as items close. The pointer drifted **within a day** of being written, with no edit to
either file.

**Generalises to.** Cite a mutable list by a stable identity — a title, an anchor, a quoted phrase —
never by ordinal position: a list whose items close renumbers itself, so the citation decays while
both documents stay untouched and neither diff shows anything.

**Candidate home.** `README.md` → *Protocol*, beside the single-sourcing rule it already carries; or
stable ids in `ADAM_TODO.md`. Group with **L9.3**.

### L9.6 — a ticked ledger property held only for the fixture that demonstrated it

**What happened.** Ledger task **1.6** (applicability routing, `applies_to`) is ticked, and its exit
was demonstrated by `_NaiveSplitter` in `test_runner.py` declaring `applies_to`. Measured across the
shipped tree: **exactly one registered plugin declares it** —
`weft_clean/dictionary_spacing.py:110`, whose own docstring calls it *"a repair, not part of the
original lift"*. No chunker does, so `FixedSizeChunker` applies to every node including a
`MediaType.TABLE` one, and a table is split mid-structure today. Found by a planning agent asking
what would happen to a table node, not by the 1,500-test suite.

**Generalises to.** An exit demonstration that uses a purpose-built fixture proves the *kernel* can
route, never that any shipped plugin participates — so a property asserted of a contract is
demonstrated against the registered population under that contract, not against a fixture written
to satisfy it.

**Candidate home.** A fitness function over the registered population (every plugin under a contract
carries the declared property), and `phase-step` → *Finish*. This is **`L8.4`'s shape one level
down**, and `L6.4` already says *read the population, not the declaration* — both are archived and
neither bit here.

### L9.7 — the citation check matches a basename, so a line-numbered citation rots under a green gate

**What happened.** `tests/architecture/test_ff17_citations_resolve.py:169`
(`test_every_citation_resolves_to_a_path_this_repository_has`) resolves a citation through
`_basename_exists` — it asserts a file *with that name* exists somewhere in the tree. The path is not
matched and **the line number is never checked**. Consequence, measured: three of `11` §3 D1's
citations (`02:323-324`, `seam.py:133`, `:202-234`) now point at unrelated code — `RemovalClock`,
`guard_blocking_calls` — and FF17 is green.

**Generalises to.** A check that verifies the cheap half of a claim licenses the expensive half to
decay: if a citation carries a line number, the check either verifies the line or the citation does
not carry one — a green gate over a weaker assertion than the artefact makes is a documented check
that turned out to be prose.

**Candidate home.** FF17 itself (resolve `path:line` and match an anchor, or forbid line numbers in
prose citations). Note the ratchet already there: `CITATIONS_WAIVED` is pinned empty, so the waiver
discipline is right and the assertion is what is thin.

### L9.8 — the file whose one rule is "state and pointers" holds two contradictory states, and a duplicate id

**What happened.** Found independently by two planning agents, then verified: `docs/README.md`
carries **two different decisions both numbered `S9`** (`:155` Phase 8 — from engine to product;
`:158` The originality claim), so a citation to `S9` is ambiguous. Separately its **Status** block
says all eight phases are closed while its own Execution-path checkboxes leave Phase 6, 7 and 8
exits and G12 unticked. That file's stated governing rule is that it holds *state and pointers only*.

**Generalises to.** A control file's identifiers need a uniqueness check and its two representations
of the same state need to be derived from one another — a document that holds state is subject to
the same single-sourcing rule it imposes on everything else, and it is the one file where drift is
invisible because there is nothing to compare it against.

**Candidate home.** A fitness function over `docs/README.md`: decision ids are unique, and the
Status block agrees with the checklist. Cheap, and it is the file every session reads first.

### L9.9 — settled text contradicts settled text, and a brief inherited the wrong half

**What happened.** `02:1032` states that the `packs:` settings namespace has an installation
lifetime; `03:911` states that `weft.toml` is per project. Both are settled documents. The graph
plan's third open decision — *where does a pack persist per-corpus configuration* — was framed on
the `02` reading, and turned out to be **half-answered by the tree already**, because the
per-project lifetime exists.

**Generalises to.** When two settled documents describe one mechanism, the contradiction is found by
whoever next depends on it and is paid for as a design question that did not need asking — so a
mechanism described in two documents names one owner and the other points at it, which is the rule
`README.md` already applies to itself and not to `01`–`05`.

**Candidate home.** `README.md` → *Protocol*, extended past the control file to the reference
documents; and a repair to whichever of `02:1032` / `03:911` is not the owner.

### L9.10 — a "what to do first" document was falsified within hours and still says it

**What happened.** The graph audit's §5 and `docs/product-direction.md:124-129` both name a general
falsification instrument as the thing to schedule first. It **shipped as ledger task 8.8**
(`ca56ccf`) the same day the audit recommended it. Both documents still carry the recommendation as
though it were open, and a planning agent had to re-derive that it was overtaken.

**Generalises to.** A recommendation about sequencing is a claim with a shelf life, so it carries the
date it was made and the task id that would discharge it — otherwise it reads as current forever and
is re-planned by whoever picks it up next.

**Second instance, same document, found the same day.** Two independent planning agents cited
`product-direction.md` as current — one for a sequencing claim discharged by ledger 8.7
(`raptor.py:222`, the fan-out cap it says "exists in neither"), one for §6's ordering. A file that
says of itself *"this is not a source of truth and it does not hold state"* was read as both, twice,
because nothing in it distinguishes a live claim from a discharged one.

**Candidate home.** `product-direction.md`'s own dissolution (it says it is written to be deleted) —
and until then, a discharge column: every claim names the task id that would close it. A planning
document with no such column decays into a source of truth by being the only place a thing is
written down.

### L9.11 — a design document's external facts rot in weeks and nothing dates them

**What happened.** `11` §7 sorts multimodal dependencies into clean / hosted / incompatible. Re-checked
during planning: `docling` became a meta-package over `docling-slim` extras, `sqlglot` moved, Docling's
copyright line changed, and `dots.mocr`'s HuggingFace org moved. `tests/architecture/test_pinned_external_facts.py`
pins external constants that appear **in code**; nothing covers a licence table written in prose.

**Generalises to.** A licence or packaging fact about a third party is measured at a date, so the
document records the date and what was checked — an undated licence table is indistinguishable from
a current one and is exactly the kind of claim a later reader trusts without re-measuring.

**Candidate home.** Extend `test_pinned_external_facts.py` to prose tables, or require a
*measured YYYY-MM-DD* stamp on any licence/dependency row in `docs/`.

### L9.12 — a seam shipped with a consuming side, a producing side, and nothing that uses either

**What happened.** Scope row `S8` added task **5.3a** so that a pack could offer a slot contribution,
because resolution could place contributions and no pack could produce one. Measured after the
ladder shipped: **no shipped pipeline document declares a `slots:` key**, so there is nowhere for a
contribution to land that a user can actually run. Nothing measured this once the nineteen pipeline
documents existed.

**Generalises to.** Closing the producing half of an extension point does not make it reachable — the
third party needs a *shipped artefact that declares the extension point*, so the completeness check
is "can somebody run it", counted in shipped documents, not "do both sides of the API exist".

**Candidate home.** A fitness function counting shipped documents that declare a slot (ratcheted at
one, not zero), and `weft-qualities`, which reviews for exactly this class.

### L9.13 — a destructive write raced a producer, and the read that would have caught it was skipped

**What happened.** While draining `.claude/lessons-spool.md` I truncated it with `printf > ` after
reading it once. A second dispatched agent completed in the interval and its `## Noticed` section was
written into the file between my read and my write, so the truncation discarded a harvest I had
never seen. It was recoverable only because the same text also arrived in the agent's completion
notification.

**Generalises to.** A file written by a concurrent producer is never cleared by overwriting what an
earlier read showed — clear exactly the entries that were consumed, or re-read immediately before
writing. `CLAUDE.md` already says *before deleting or overwriting, look at the target*; the gap is
that the spool has a live producer and the drain has no read-before-write step.

**Candidate home.** `lessons` → the spool-draining step (consume-by-entry, or re-read before
truncation), and possibly `subagent_findings.py` appending with an entry id the drain can name.

### L9.14 — a settled document describes a resolution mechanism the kernel does not implement

**What happened.** `02` describes reaching a capability through the passport — `ctx.require(...)`
against a contract — and **two independent plans built recommendations on it**. Measured:
`weft_kernel.context.ServiceRegistry.resolve` keys by **exact contract type**
(`packages/weft-kernel/src/weft_kernel/context.py:133-142`), and its own comment states the
invariant — *"`add` only ever stores an instance under its own `contract` key"*. So a service
registered as one type is unreachable as a capability it structurally satisfies, and G13's
*"ask through the passport, not a wider signature"* is narrower in code than in the document that
settled it. Nothing checks that a contract a retriever names in `needs_store` is one any assembler
ever registers.

**And the gap is wider than the registry.** An adversarial review then found a *second* refusal
point on the same path: a retriever's `needs_store` is validated against the one configured primary
store before execution (`weft_cli/run_services.py:127-202`), so a capability-typed retriever is
rejected before `ctx.require` is ever reached. Two independent mechanisms enforce the narrow reading;
the document describes neither.

**Generalises to.** A seam described in a settled document is verified against the code that
implements it before a second design depends on it — and a resolution mechanism in particular is
checked at its *miss* path, because the hit path looks identical whichever way the registry is keyed.
Finding one enforcement point is not finding the mechanism: look for the second before concluding a
repair is complete.

**Candidate home.** A fitness function pairing declared needs with registered services (every
contract named in a `needs_*` declaration is one an assembler registers), plus a repair to whichever
of `02` or the kernel is wrong. This is **`L6.4`'s shape** — *read the population, not the
declaration* — with the population being `services.add` call sites.

### L9.15 — a filed-but-unowned finding with no id is re-derived by everyone who trips over it

**What happened.** Phase 7's close review filed two repairs and gave them no ledger ids;
`docs/README.md`'s Next action carries them as prose. Two planning agents then independently
discovered the same one (the ambient-service seam), independently concluded it was a prerequisite of
their phase, and **both allocated it the same number, `9.2`** — which would have collided the moment
either plan became tasks.

**Generalises to.** A finding recorded without an identifier has no way to be referenced, so it is
rediscovered rather than cited, and each discoverer numbers it themselves — a close review mints the
ledger id at the moment it files the finding, even when nobody is going to build it yet.

**Second instance, same round, different namespace.** Both plans also claimed the **same next
fitness-function number** (`FF22`) in their own task lists. A number allocated in a plan file rather
than at the commit that creates the phase is a collision waiting to happen, for exactly the same
reason: the allocator is not the artefact that holds the sequence.

**Generalises further.** An identifier is minted by the artefact that owns the sequence — ledger ids
by the ledger, fitness-function numbers by `01` — and a document that needs to refer to one before it
exists says *placeholder*, never a number.

**And the mitigation applied on the day was not the rule.** To stop the collision a coordinator
assigned the numbers up front — `FF22/FF23` to one phase, `FF24/FF25` to the other. Three hours later
the owner reordered the roadmap and those allocations swapped phases wholesale. Assigning centrally
beats colliding, and it is still allocation **outside the artefact that holds the sequence**: the
number was stable only as long as the plan was.

**Candidate home.** `phase-step` → *Finish* and the close-review block in `build-ledger.md`: a filed
repair gets an id and a `⛔ unowned` marker, not a sentence. Both planners independently reached this
conclusion, which is itself the evidence — and a document that must refer to a number before the
owning artefact mints it writes *placeholder*, never a number, however carefully allocated.

### L9.16 — a second reader's need falsified a design that two reads of the tree had not

**What happened.** The graph plan's first decision survived its own author reading the tree twice. It
was falsified within minutes of being handed a *sibling plan with a different need*: the graph
retriever cannot reach a second `NodeStore` on the query path, because resolution is exact-typed
(L9.14) — a hole the author found only when asked how their answer served somebody else's case.

**Generalises to.** Where two designs touch one seam, exchanging them is a cheaper falsifier than
either author re-reading the tree — so a design that adds a seam is reviewed by the next consumer's
requirements, not only by its own.

**Candidate home.** `weft-qualities` (requirement 1 already asks whether a capability is one package
with zero core edits; this adds *and does the seam serve the second consumer*), and the dispatch
convention that produced it.

### L9.17 — "converged" was recorded by two parties agreeing on a problem, not on an artefact

**What happened.** Two planning agents were asked to reconcile and both reported collision **C2** as
converged: `Removed` gains per-kind counts, `STORE_CONTRACT_VERSION` 2.0.0 → 2.1.0, minor under G9's
two-audience rule. They agreed on the defect, the shape of the fix and the version arithmetic — and
specified **incompatible public models**: `removed: Mapping[str, int] = {}` against
`counts: tuple[RemovedCount, ...] = ()`. Both wrote "converged". Neither compared the two
declarations, and the review that caught it was a third reader.

**Generalises to.** Agreement on a problem, a mechanism and a version bump is not agreement on an
interface — a reconciliation is recorded by producing the **one artefact** both sides then cite, never
by both parties reporting that they agree. If no single line of the artefact was written, nothing
converged.

**It then recurred in the round convened to fix it.** Told to converge, each plan adopted *the
other's* model: multimodal moved to `removed: Mapping[str, int]`, graph moved to
`counts: tuple[RemovedCount, ...]`. Both reported convergence a second time; there were still two
artefacts, now swapped. Two parties each yielding is indistinguishable from agreement in a report and
distinguishable in a diff. (Settled outside the round on a house rule that neither invoked:
`CLAUDE.md` requires a Pydantic model over `dict[str, Any]`, so `counts` wins.)

**Candidate home.** The dispatch convention for reconciliation rounds (require the shared artefact,
not two reports), and `weft-qualities`, which reviews contract changes and would be the natural place
to ask *whose declaration is this, and is there exactly one*. Note the cheaper fix the second failure
suggests: where a house rule already decides the question, cite it instead of convening a round.

### L9.18 — a review finding about a seam was half-true, and only the call sites said which half

**What happened.** An adversarial review asserted that registering one instance under every
capability it structurally satisfies would collapse G13's multi-participant `SourceDeletable`
fan-out into one arbitrarily preferred service. Checked at the call sites: the fan-out never consults
`ServiceRegistry` at all — `participants_for` (`weft_cli/fanout.py:60-79`) walks the factory
`Registry` via `contracts()`/`names_for`, and `deletion.py:67` calls it with `SourceDeletable`. So the
claim is **false about the registry and true about `ctx.require`**, which does answer with a single
instance. Complying would have added a restriction the code does not need; dismissing it would have
kept a real hole.

**Generalises to.** A finding about a seam is adjudicated against the seam's **callers**, not its
docstring or its own name — an invariant's scope is the inputs that actually reach it, so a
mechanism named in a review is located before its claim is accepted *or* refused.

**Candidate home.** `phase-step` → *Finish*, and the convention for receiving a review. This is
**`L6.15`'s shape** applied to review findings rather than to code.

### L9.19 — every claim of the form "X comes for free" was wrong, and the evidence was already read

**What happened.** A planner's own retrospective: two load-bearing claims were stated as free
consequences and neither was. Provenance-by-lineage would give fact nodes their page numbers for
free — it does not, because `Node.derive` takes one parent and drops `ext`, and `combine` drops it
too (`payload/node.py:108-151`), while `page_for` reads page data only from the same node
(`weft_generate/page.py:42-60`). And an in-memory store would count as G4's second implementation —
`01:349-352` says in so many words that it is not a backend. **Both facts were in documents the
author had already read.**

**Generalises to.** *"Comes for free"* is a claim that some existing mechanism already does the work,
and it is the sentence to re-measure before writing it down — having read the document that contains
the answer is not the same as having asked it the question.

**Candidate home.** `weft-qualities` (a free-consequence claim is a factual claim and owes evidence)
and `CLAUDE.md` → *Claims need evidence*, which today reads as being about counts and line numbers.

### L9.20 — the exit clause is guarded by a test that checks reachability, not reproducibility

**What happened.** Phase 6's exit requires a stranger to reproduce a published number. Measured: the
reproduction path depends on five files — `scripts/fetch_corpus.py`, `scripts/wikitext.py`,
`eval/run_baseline.py`, `eval/check_baseline.py`, `eval/metrics.py` — that ship in **no wheel and no
tarball**; the release tarball attaches baselines, questions and a manifest only
(`release.yml:218-223`). `tests/architecture/test_baseline_is_published.py` asserts the tarball
carries those three data artefacts and **never asks whether anyone could use them**. Separately,
`weft eval compare --baseline` takes a pipeline name whose repetitions live under `runs/`, so the CLI
cannot read the baseline format the release publishes — two formats for one word, recorded in the
ledger as "met in substance" with nothing marking it as a gap.

**Generalises to.** A test that an artefact was *published* is not a test that the claim depending on
it can be *performed* — where an exit clause names an outcome a stranger must reach, the check
performs the stranger's path or the clause is unguarded, however green the suite is.

**Candidate home.** `01`'s Phase 6 exit and its fitness function; `phase-step` → *Finish*, which
already carries "run the binary" and does not carry "run the stranger's path".

### L9.21 — a runbook was verified by reading it, and four of its rows could never have passed

**What happened.** The publish runbook's pre-flight was written carefully and checked by re-reading
it. A second reader found four rows mechanically incapable of passing: a check expecting `3 passed`
against a fitness function with **six** tests; a row prefixing only its first command with
`uv run --project`, so the rest ran outside the environment; a row expecting an all-active `doctor`
report when a clean base install **intentionally** reports `weft-eval` as `partial`; and a shell line
placing `$n` inside a single-quoted Python program, making its condition always true. None was
subtle; none survives execution; all four survived authorship and review-by-reading.

**Generalises to.** A pre-flight row that has never been executed is prose in exactly the sense this
project already refuses — so a runbook's checks are run against the current tree at the moment they
are written, and a row that cannot be run yet is marked as unverified rather than presented as a
check.

**Candidate home.** `CLAUDE.md`'s *a green gate is not a working binary* paragraph, extended to
written procedures; and the convention for any document containing commands the owner will paste.

### L9.22 — the instruction file every session reads described a layout five phases out of date

**What happened.** `CLAUDE.md` → *Where things are* listed seven directories under `packages/`. Five
had not existed since G10's re-settlement consolidated fourteen packs into `weft-rag` — `weft-cli`,
`weft-extract`, `weft-chunk`, `weft-store`, `weft-embed` — and the four that do exist
(`weft-rag`, `weft-agent`, `weft-openai`, `weft-pdf`, `weft-qdrant`) were absent. This file is
injected into **every session and every dispatched agent**, so the wrong map was the first thing each
one read. It was found by an agent whose brief happened to send it to `packages/` to check something
else, five phases after the change.

**And it is invisible to the one check that looks at citations.** FF17 resolves a citation by
**basename**, so every `weft_cli/*.py:N` citation written against the old path still passes — the file
exists, just not where the citation says. The stale tree and the weak check hide each other.

**Generalises to.** A document that describes the shape of the tree is a factual claim about the
tree and decays exactly like a count or a line number — so it is derived from the tree or checked
against it, and the higher its readership the sooner that matters. `docs/` is held to *claims need
evidence*; the file that states the rule was not held to it.

**Candidate home.** A fitness function over `CLAUDE.md`'s tree block (every path listed exists, every
distribution present is listed), which is cheap and would have failed on the day of the
consolidation. Pairs with **`L9.7`**: fixing FF17's basename matching is what stops the stale
citations that this hid.

*Declined at write time:* two miscited line ranges found in a planning document
(`01:939-944` should be `01:802-812`; `05:342-345` should be `05:340-344`). Both are real errors and
both are **instances of `L9.19`'s sibling `L9.7`** — a citation checked by basename cannot catch a
wrong line — which is already in this queue with the repair attached. `L6.8` says a re-learned rule
belongs in one artefact, not two, so these are evidence for `L9.7` rather than entries of their own.
The third spooled note, that `docs/README.md` and `docs/lessons.md` are uncommitted so every
`README.md:line` citation in the plans is a working-tree line, was **acted on rather than logged**:
the doc repairs are committed separately from the ledger text so neither rides in unreviewed.

*Also declined:* a note that `zsh` expands a leading `=` in `echo ======` as a
`=command` lookup. It cost a dispatched agent two failed tool calls, but it is a shell quoting
detail with no shape this project can hold a rule about — logging it would pad the queue, which the
`lessons` skill names as the failure that stops queues being drained.

### L9.23 — a citation pointed at a section title that exists as no heading, five times over

**What happened.** `docs/build-ledger.md` cites *`build-ledger.md` → Phase 7's close* at `:5009`,
`:5011`, `:5035`, `:5282` and `:5283`, as the owner field of task `9.0` among others. There is no
such heading: `grep -n '^#\{2,4\} '` over the file returns close headings for Phase 6 (`:3807`) and
Phase 8 (`:4657`) and none for Phase 7. The text meant is unheaded prose under `## Phase 7 — The
agent` at `:4358-4366`. Found while following the citation to read what `9.0` was actually filed as.
FF17 resolves citations by **basename** (`tests/architecture/test_ff17_citations_resolve.py`), so a
pointer whose file exists and whose *section* does not is green by construction.

**A second instance, sharper, found the same day.** Ledger task `11.4` cites `02:666-670` for the
sentence "a graph store is not a node store". Those lines hold the in-memory-store passage; the
sentence is at `docs/02-extension-model.md:691`. That citation was **written today**, in `b0f04d1`,
and FF17 passed it — because FF17 asks whether a `path:line` *resolves*, never whether the lines
hold what the citation claims. A pointer can be green and wrong on the day it is written.

**Generalises to.** A citation is only as good as the thing it can be checked against — so a
`document → Section` pointer needs the section to be a heading, and a `path:line` pointer needs its
*content* checked, not merely its existence. A check that a line number resolves is a check that the
file is long enough.

**Candidate home.** FF17, whose subject would widen from basenames to `→ Section` anchors; or the
`phase-step` orientation step, which follows these pointers and is where the miss is felt.

### L9.24 — three abandoned worktrees make every tree-wide search silently over-count

**What happened.** `git worktree list` reports three live worktrees under `.claude/worktrees/`
(`phase2-group-e` at `d487653`, `repair-2-30-llm` at `7020480`, `task-2-30` at `c8af558`), all from
Phase 2, each a full checkout of this repository. They are hidden from `git status` by
`.git/info/exclude:11` — a **local, untracked** exclude, so nothing in a diff or a fresh clone
records that they exist. A naive `grep -r` from the repo root therefore returns up to four copies of
every hit. Surfaced by a dispatched agent that scoped its own walks to `packages/ tests/ examples/
testing/ docs/` and said so; nothing in the repository would have told it.

**Generalises to.** A count from a tree-wide search is a claim about the working tree only if the
search's scope was stated — so a search that feeds a brief or a document names the directories it
walked, and stale worktrees are removed at the phase close that abandons them rather than left to
be discovered by whatever trips over them.

**Candidate home.** `phase-step` → *Finish* (leave no worktrees behind, beside "leave no artefacts
behind"); or a `ci-checks` row failing on a worktree whose branch is merged. Phase 13 owns the
removal; this owes the rule that stops the next three.

### L9.25 — two comments asserted another module's state, and were false for a whole phase

**What happened.** `packages/weft-rag/src/weft_retrieve/vector_top_k.py:176` says of
`weft_cli.run_services.check_store_capabilities` that "**nothing does yet**" call it, and
`tests/unit/weft_retrieve/test_vector_top_k.py:189-192` repeats the claim in its Arrange block as
the reason the test exists. `packages/weft-rag/src/weft_cli/route_ask.py:508` has called it since
Phase 2 task 2.8. Both comments are about a **different module's** call graph, so nothing that
changed `route_ask.py` had any reason to touch either, and the test asserting the fallback still
passes — it is the stated *reason* that rotted, not the assertion.

**Generalises to.** A comment claiming what some other module does not yet do has no mechanism to
notice when it starts — so a claim about another file's call sites is written as a check
(`grep`-able, or an assertion) or is not written down.

**Candidate home.** `weft-qualities`, which reads a change and could ask it of the comments in
range; or `phase-step` → *Verify*, beside "read what a check asserts, not what its name says".

### L9.26 — every test supplied the argument by hand, so none could catch the caller supplying the wrong one

**What happened.** `check_store_capabilities` takes `store_name` and builds a refusal reading *"the
configured store '{store_name}'"* whose remedy is *"name a store that provides X in [services]
store"* (`packages/weft-rag/src/weft_cli/run_services.py:186-198`). The one production caller passes
`store_name=type(store).__name__` (`packages/weft-rag/src/weft_cli/route_ask.py:513`), so a live
refusal names `PgVectorStore` where `[services] store` accepts `pgvector` — a remedy an operator
cannot carry out. All six other call sites are tests (`tests/unit/weft_cli/test_run_services.py:134`,
`:152`, `:189`, `:219`, `:237`; `tests/integration/test_store_conformance.py:640`) and every one
passes a plausible plugin-shaped name by hand (`"fake-vector-only"`, `"qdrant"`).

**Generalises to.** A test that supplies a parameter itself is testing the callee and never the
caller — so where a parameter's *value* carries the promise (a name an operator must be able to
type), the check derives it the way production derives it, or runs the production path.

**Candidate home.** Task `9.0` property (iii) repairs the instance; the rule belongs where briefs
are written — `phase-step` → *Verify*, which already carries "read the other call sites before
writing why they abstain" and does not carry "a hand-supplied argument tests nothing about the
caller".


### L9.27 — the check guarding a key set globs the directory that restates it, not the one that defines it

**What happened.** `tests/docs/test_manual_config_keys.py` derives the accepted `[services]` key set
from `ServiceSelection.model_fields` (`:83`) and sweeps for drift across `manual/*.md` plus
`weft.toml.example` (`:47-48`). It never reads `docs/`. But `docs/03-cli.md:925-930` is where the key
set is *defined* — "**`[services]` holds three keys, and the third names a pipeline rather than a
plugin**" — and `docs/02-extension-model.md:1373`, `docs/README.md:114` and some 45 `build-ledger.md`
lines restate it too. Task `9.0` changes that key set from three fixed fields to a declared role set,
and every one of those sentences would have gone stale with the whole gate green. Found by a survey
of the blast radius, not by any check. The same page carries three more statements of the key set in
prose that neither of its two regexes matches (`manual/troubleshooting.md:1066-1067`, `:1074`,
`:1093-1094`) — `_INLINE` (`:41`) requires `[services]` followed immediately by an identifier, and
`:1074` sits inside a ```` ```text ```` block that `_QUOTED_TUPLE` does not reach.

**Generalises to.** A drift check's scope is the set of files that *state* the fact, not the set that
is convenient to glob — so a check guarding a definition covers the document that owns it first, and
a definition restated in prose the check's pattern cannot match is either rewritten into the form the
check reads or is not written down twice.

**Candidate home.** `tests/docs/test_manual_config_keys.py`'s own `_documents()`, widened to the
documents that own the definition; or FF4, which `build-ledger.md:5062` already says must reach the
`[services]` key set through `9.0`.

### L9.28 — a test pinned the expected set as a literal, so the derivation it was guarding could not fail it

**What happened.** `weft config get|set`'s dotted-key vocabulary is a hand-written dict —
`packages/weft-rag/src/weft_cli/config_surface.py:79-85` `_KEY_FIELDS` — listing `services.embed` and
`services.store` and **not** `services.route`, which task 8.3 added to `ServiceSelection`
(`services.py:144`) and wired into `route_ask.py:183`. So two key spaces over one `[services]` block
have disagreed since 8.3. The test that would have caught it,
`tests/unit/weft_cli/test_config_commands.py:60-66`, asserts the five-key set as a **literal**
matching `_KEY_FIELDS`, so both sides of the comparison come from the same hand-written source and
the check cannot fail. The module docstring (`:8-19`) still says "the five keys".

**Generalises to.** Where a production value is hand-written and its test restates the same literal,
the pair is one source checked against itself — so a test over a key space asserts it against the
thing the keys are *for*, and a literal on both sides is the signal that nothing is being looked at.

**Candidate home.** FF4, whose subject is exactly a closed key space over registry-adjacent names;
`weft-qualities`, requirement 4. `9.0` repairs this instance by deriving the `[services]` half of
`_KEY_FIELDS` from the declared role set.



### L9.29 — the brief searched for the precedent it was copying, not for who enumerates the surface it grew

**What happened.** Task `9.0` adds one public method, `add_service_role`, to
`weft_kernel.discovery.PackRegistrar`. Before writing the brief I searched for `add_renderer` —
the precedent whose shape I was copying — and listed its five sites. I did not search for
`PackRegistrar` itself, so the brief omitted
`tests/architecture/test_ff9_extension_from_outside.py:125`, where `_NameCapturingRegistrar` is a
hand-written double whose completeness `test_the_double_carries_every_registrar_method` (`:663`)
asserts against `vars(PackRegistrar)`. The implementer was correctly blocked — the repair is an edit
to a test file, which its standing prohibitions forbid — and a round trip was spent. The check
itself worked: its own docstring records that this had "happened three times and been noticed once",
and this is the first time it fired instead of surfacing as a crash inside an unrelated check.

**And it could not have been delegated even once found.** The designed repair is to add a no-op
stand-in to `_NameCapturingRegistrar`, which lives inside that same test file — so a brief naming
this site would still have handed the implementer work its standing prohibitions forbid. The
implementer said so plainly and stopped, which is the right outcome and still a wasted round trip.

**Generalises to.** Adding a public method to a class is an edit to every site keyed on that class's
*surface*, and none of those sites is reachable from the method you are copying — so the search that
closes the brief is for the class being extended, never for the sibling being imitated. Where such a
site is a test, the dispatcher lands that edit **before** dispatching: a brief whose completion
requires the implementer to edit a test is a dispatch that cannot succeed, however complete its
site list. **And an enumerated fallout list is read as exhaustive**: part 2's brief said "expect
fallout in `test_manual_config_keys.py` and `test_manual_valid_options.py`", having grepped
constructions of `ServiceSelection` but never call sites of `service_selection_from_config` — so a
third file, `tests/unit/weft_cli/test_services.py`, broke in nine places and the implementer had to
invent a default to get past a list it reasonably read as complete. Name the search that produced
the list, or say the list is not exhaustive.

**Candidate home.** `phase-step` → *Red*, which already carries `L8.12` in the base-class form
("when a brief names a base class, grep for that base class") and does not carry the
add-a-method form. This is that rule re-learned one shape over, which `L6.8` says means moving it
rather than restating it — the two should be one sentence about extending a surface.



### L9.30 — the catalogue row claimed a mode the same page withdrew two paragraphs above it

**Repaired 2026-09-06** by Phase 10's planning pass, which rewrote the row; it now carries no
`mode:` annotation and names recursion and traversal as *not shipped*. That edit moved the row and
the correction block down the catalogue, so the line numbers below are as-found, not as-they-are.

**What happened.** `docs/10-technique-catalogue.md:148` named the shipped plugin
**`raptor`** *(mode: `collapsed` | `traversal`)* — the mode annotation sitting inside the row's own
name column. `RaptorConfig` has no `mode` field (`packages/weft-rag/src/weft_index/raptor.py:141-161`
— seven fields, none of them it), and no `Retriever` in `packages/` descends a tree: the only reader
of `lineage.parents` under `weft_retrieve` is `collapse.py:142-146`, which walks child→parent, the
opposite direction. The plugin itself is **honest** — its docstring at `:93-102` says `traversal`
"is not implemented here" and names it as a distinct `Retriever` position — and `10:119-128` carries
a correction block saying the same. So one page states the claim in its row and withdraws it in its
prose, and the row is the half a reader scanning a table actually consumes. Found by a dispatched
agent reading the paper against the code, not by `tests/docs/test_technique_naming.py`, which checks
that a divergence is recorded on the docstring — and it *is*.

**Generalises to.** A correction that does not edit the claim it corrects leaves both in the tree,
and the shorter one wins — so a withdrawal is made **in the row**, and a note added elsewhere is a
second copy of the fact rather than a repair of it. This is `L6.17` (anchoring finds the
illustrative copy first) with the two copies inside a single document.

**Candidate home.** `tests/docs/test_technique_naming.py`, whose five properties cover the docstring
and not the row — a row's parenthetical mode/variant annotations are a claim with no check behind
them. Also `paper-to-plugin` → step 6, which says to fill five columns and does not say that a later
withdrawal edits the column rather than appending a paragraph.

### L9.31 — a pipeline document told operators to do the thing its own plugin documents as broken

**What happened.** `packages/weft-rag/src/weft_retrieve/pipelines/index-with-raptor.yaml` tells the
reader that one summary level "is this document's choice rather than the plugin's limit", and that
"a second level is a second stage naming it again, which is a document edit and not a plugin
change". The plugin says the opposite, in bold, at
`packages/weft-rag/src/weft_index/raptor.py:58-70`: "**Chaining `embed`, `raptor`, `embed`,
`raptor`, ... does not yet build a correct deeper tree, and this module does not claim that it
does**" — because the linear runner hands the second stage the whole cumulative node set, so a leaf
can be re-clustered with the summary already built from it. The document's advice produces a node
mixing raw and already-abstracted content, silently. `10:119-128` agrees with the plugin. Two
artefacts describe one mechanism from opposite sides and only one of them is operator-facing.

**Generalises to.** A pipeline document is operator-facing instruction, not commentary — so a claim
in one about what an operator may safely do is checked against the plugin it names, and a plugin
that documents a limit owes an edit to every document that offers the workaround.

**Candidate home.** A fitness function pairing each shipped pipeline document against the docstrings
of the plugins it names is the durable form, and is plausibly the same check `L9.30` wants. Failing
that, `phase-step` → *Verify*, beside "read the other call sites before writing why they abstain".



### L9.32 — a divergence was justified by a claim about the paper that the paper contradicts

**What happened.** `packages/weft-rag/src/weft_index/raptor.py:35-43` explains why Weft's `raptor`
clusters greedily by cosine similarity rather than the paper's soft GMM, and justifies it like this:
"Sarthi et al.'s own contribution is *recursive abstraction over a similarity-based hierarchy*, not
a specific clustering procedure". A dispatched agent reading the paper at source reports that the
authors present soft clustering as a distinctive design choice in their own right (p.3). So the
divergence note — which is exactly the artefact `paper-to-plugin` step 5 requires, and which is
otherwise well written — rests on an assertion about what the original authors cared about, made
without evidence, that runs the other way. The paper's own ablation is the better argument and the
docstring does not use it: GMM versus a recency tree is reportedly 0.8 points, once, on one dataset,
without variance.

**Generalises to.** A divergence note is a claim about the paper, not only about the code, and
carries the same evidence burden as any other factual claim here — so "the authors did not really
care about the part I changed" is the one justification that must never be written without a
citation, because it is the one that makes a divergence sound like agreement.

**Candidate home.** `paper-to-plugin` → step 5, which tells you to write the divergence and does not
tell you that the *reason* is itself a claim needing a page number. `tests/docs/
test_technique_naming.py` checks a divergence is recorded, never that its stated reason is sourced.

### L9.33 — an expensive intermediate is computed, discarded, and recomputed by the next stage

**What happened.** `weft_index.raptor.RaptorSummarizer` embeds every leaf in order to cluster it
(`_embed`, `packages/weft-rag/src/weft_index/raptor.py:241-263`), then returns
`Produced(value=(*payload, *derived))` at `:239` — where `payload` is the input sequence, unchanged
and un-embedded. The shipped rung `index-with-raptor.yaml` runs `embed` after `raptor`, so every
leaf is embedded **twice per ingest**: once inside the plugin to decide clusters, once by the stage
that actually stores the vector. With the offline `hash` embedder this is invisible; with a paid
embedder it is the entire leaf cost, paid twice. Nothing has ever measured it, because nothing
measures this rung's cost at all.

**Generalises to.** A stage that computes something expensive for its own internal decision and
returns its input unchanged has hidden a cost at a boundary, where no stage-level test can see it —
so a plugin that embeds, calls a model, or does IO for an intermediate says so in its docstring and
names what downstream recomputes, or the cost is discovered on somebody's bill.

**Candidate home.** The `Expander` contract's own documentation, or `weft-eval` gaining a per-rung
cost the comparison already has a place to print. `weft-qualities` could ask it of any plugin that
requires a service it does not return the product of.



### L9.34 — three of four agents cited one paragraph at three different line numbers, on the same day

**What happened.** Four agents were dispatched to read four papers against this tree on 2026-09-06.
Three of them cited `docs/01-high-level-plan.md`'s Phase 10 ordering paragraph — the same paragraph,
in the same file, on the same day — as `:936-939`, `:943-946` and `:945-948`. Only one was right.
Separately, two of the four disagreed about how many members `weft_store.contract.NodeStore`
declares (nine versus ten; it is ten), and one of them listed ten items while writing "nine". None
of these was a reasoning error: every conclusion built on them held. The *pointers* were wrong.

**Three more instances, all the caller's, all within the hour.** *(1)* `L9.31` was written from a
reading agent's report and cites `weft_index/pipelines/index-with-raptor.yaml`; the only copy is
under `weft_retrieve/`. The contradiction the lesson records was verified at source; the *path* was
not — a lesson about a documentation defect, containing one. *(2)* A brief repeated a reviewer's
"both halves are false" about a catalogue row when one half — retrieval over the whole tree — was
true of the code, and the dispatched agent had to correct the brief. *(3)* A brief, and several
reports to the project owner, said a paper blends "a page render" into each leaf vector; the paper
never names the visual unit, and an earlier reviewer had already refuted that phrasing. In every
case the claim was checked once, by somebody else, and then travelled as if it had been checked by
whoever repeated it.

**And a citation can go stale while it is being written.** Two agents ran concurrently over one
tree; one cited `run_services.py` and `cli.py` while the other was editing them, and a third's doc
edit moved the catalogue rows that two open lessons cite. A `path:line` taken during parallel work
is a claim about a file that may not hold still.

**Generalises to.** A `path:line` produced by a dispatched agent is a claim like any other and is
wrong often enough to be assumed wrong — so a citation an agent supplies is re-derived, **at the
moment it is landed**, by whoever lands it in a tracked document; a brief that asks for `path:line`
citations is asking for leads, not evidence; and a claim repeated from another agent's report
inherits none of that agent's verification.

**Candidate home.** `phase-step` → *Verify*, which tells you to read the diff and does not tell you
that an agent's citations are the least reliable part of its report. FF17 cannot help: it checks
that a line resolves, never that it holds what the citation claims (`L9.23`).

### L9.35 — an error message had to be reworded because a documentation scraper mistook it for a key

**What happened.** `tests/docs/test_manual_config_keys.py:41` scrapes `manual/*.md` with
`\[services\][ \t]+([A-Za-z_][A-Za-z0-9_]*)`, treating "`[services]` followed by an identifier" as a
documented key. Task 9.0's new `DuplicateServiceRoleError` originally read *"[services] role 'blobs'
was declared by..."*; quoted into `manual/troubleshooting.md`, as the troubleshooting-coverage
ratchet requires, the word `role` was scraped as an undeclared `[services]` key and failed the test.
The implementer reworded the **error message** — to *"role 'blobs' ... for [services]:"* — to get
past a documentation check. The product's user-facing text was shaped by a regex.

**Generalises to.** A check that scrapes prose for identifiers constrains every sentence that will
ever quote its subject, including sentences in error messages that have to be quoted somewhere else
— so such a scraper matches a *documented-key* form specific enough to exclude ordinary prose, or it
silently becomes a style rule nobody agreed to.

**Candidate home.** `tests/docs/test_manual_config_keys.py`'s two regexes, which could require the
assignment form (`key = value`) it actually cares about. Also worth a line in `CLAUDE.md`'s
automation section: a docs check is a constraint on writing, not only on drift.

### L9.36 — a dispatched agent read a third-party codebase, and nothing in its brief had bounded where it could read

**What happened.** One of four paper-reading agents, briefed to read a PDF at
`tmp/raptor/files/749/`, went to that paper's public GitHub repository on its own initiative and
drew roughly nine of its reported constants from it, marking them `[repo]`. It restated rather than
transcribed, so it did not breach the originality rule — but nothing in the brief had told it not
to, and this repository's central constraint is that another codebase is read to *understand* and
what comes back is "knowledge, never text". The synthesis step noticed and deliberately rebuilt its
own verdict without any repo-derived fact, which is the only reason the distinction survived into
anything a human read.

**Generalises to.** A brief naming a source names what to read, not where to stop — so a brief
dispatched in this repository states the reading boundary explicitly, because "read this paper" and
"read whatever this paper points at" are different instructions and only one of them was given.

**Candidate home.** `.claude/agents/`'s standing prohibitions, which cover writing and not reading;
and `paper-to-plugin` → step 1, which says to read the paper at source and is silent on the
authors' code. `SubagentStart` already injects the applied rules, so this is a rule that would
travel if it existed.



### L9.37 — re-indexing a changed document keeps the old chunks and destroys the evidence it changed

**What happened.** Found while a dispatched agent was reading `weft reconcile` for an unrelated
paper. `SourceRecord.content_hash` is written at
`packages/weft-rag/src/weft_cli/ingest.py:688` and its purpose is stated in this tree's own words at
`:139` — "`02` §1 wants this field to let `weft index` say *already indexed, by a different
pipeline*". **Nothing compares it.** Every use in `packages/` is a write
(`pgvector_store.py:864-876`), a read-back into a model (`:1039`), or a copy
(`weft_qdrant/store.py:272`); there is no equality test anywhere.

The consequence is not a missing feature, it is data corruption. A node's id is
`_content_digest(media_type, content, parent_ids, ordinal)`
(`packages/weft-kernel/src/weft_kernel/payload/node.py:118`, `:148`), so an **edited** chunk hashes
to a **different** id; `add` upserts `ON CONFLICT (id)` (`pgvector_store.py:733`), and a different id
inserts rather than updates. Nothing on the ingest path calls `delete_source` — its only non-store
caller in the tree is `weft_cli/deletion.py:128`, the `weft delete` fan-out. So the old chunks
survive beside the new ones and are retrievable forever. And the source upsert sets
`content_hash = EXCLUDED.content_hash` (`pgvector_store.py:868`), so after the second ingest nothing
records that the document ever differed. Confirmed by exhaustively reading every writer and reader;
**not** confirmed by running, so the reproduction is still owed.

**Generalises to.** A field written, persisted and never read is a feature that does not exist, and
one whose stated purpose is *change detection* is worse than absent — it makes the system look like
it handles change. So a field added for a behaviour lands with the behaviour or with a check that
fails while it is missing, and "the model carries it" is never evidence the behaviour is there
(`L6.14`, whose "read method with no writer" this is the mirror image of).

**Candidate home.** This one owes a **ledger task before it owes a rule** — it is a live
data-correctness defect and the owner should place it. The rule it also owes: a fitness function
that no persisted `SourceRecord`/`Node` field is write-only, which would have caught it the day
`content_hash` landed.



### L9.38 — "proven in <file>, not merely asserted" named a file that proves nothing of the kind

**Repaired 2026-09-06** in the same pass: the catalogue sentence now says the test asserts the
precondition and never deletes. Line numbers below are as-found.

**What happened.** `docs/10-technique-catalogue.md:143-144` stated that `raptor`'s cascade delete —
a summary being reachable by the deletion of a source it was built from — is *"proven against a real
corpus, real embeddings and a real store in `tests/integration/test_raptor_pipeline.py`, not merely
asserted of the type"*. That file contains no deletion at all: `grep -c delete` over it returns
**0**. It asserts `summary.lineage.sources` and the citation path, which is the *precondition* for
cascade delete, and never exercises the cascade. The sentence's own emphasis — "not merely asserted
of the type" — is what makes it worse than a vague claim: it explicitly promises the stronger form
of evidence, and points at a file to prove it. Found by an adversarial reviewer opening the file;
the third overclaim in this one document, after `L9.30` and `L9.31`.

**Generalises to.** A citation of the form *"proven in `<file>`"* is a claim about what that file
does, and it is the one kind of claim a reader is least likely to check because it looks like it has
already been checked — so a sentence naming a test as evidence names the assertion, not the file,
and "not merely asserted" is a phrase that has to be earned by opening the thing you are pointing at.

**Candidate home.** The same check `L9.30` and `L9.31` want: `docs/10-technique-catalogue.md`'s
claims about the tree are unguarded, and three of them are now known false. A fitness function that
resolves each *"proven in `<file>`"* to a named test and fails when the file lacks it would have
caught all three. `phase-step` → *Verify* carries "read what a check asserts, not what its name says
it is for", which is this rule one level up and did not reach a document.



### L9.39 — a test asserted where the code was written, and then forbade the refactor that improved it

**What happened.** `tests/unit/weft_agent/test_command.py`'s ambient-services test existed to prove
that *"`ctx.require(LLM)` answers for anybody"* — its own docstring's words. It asserted that by
parsing `weft_cli/cli.py`'s **AST** for a literal `.add(LLM, ...)` call. Task 9.0 moved that
construction into `weft_cli.run_services.command_path_services`, so the three assemblers stop being
one list written thrice — the exact defect Phase 7's close filed. A green test went red for a change
that strictly improved the thing it guards, and it could not be satisfied without either duplicating
the registration in both files or leaving dead `.add()` calls in `cli.py` to feed the parser. The
dispatched implementer refused both and reported the conflict rather than picking one, which was
right.

Its sibling in the same repair is the mirror image: a test fixture whose plugin class declared no
`__init__` made the production call `registry.entry(...).factory(None)` — the convention every
assembler in the tree uses — fail, and the implementer changed *production* to a bare `factory()`
to suit it. Both real plugins take a config argument
(`packages/weft-rag/src/weft_embed/hash_embedder.py:75`,
`packages/weft-rag/src/weft_store/pgvector_store.py:605`), so the fixture was the unrealistic half.

**Generalises to.** A test that reads source instead of running it asserts *where* code lives, and
location is the thing a good change moves — so a behavioural property is asserted through the seam a
caller actually uses, and a check that greps or parses first-party source is reserved for properties
that really are about the text. And when a test and an implementation disagree, decide which one
models reality before changing either: an unrealistic fixture that the implementation is bent around
is how a suite starts specifying its own fixtures.

**Candidate home.** `phase-step` → *Red*, which carries "an assertion is a specification including
the parts you did not mean" and does not carry the AST/source-reading case; and `weft-qualities`,
which reads a change and could ask whether a failing test is asserting behaviour or location.



### L9.40 — `L8.24` recurred in the same function family, three weeks and one applied rule later

**What happened.** Task 9.0 added a sixth field to `Dependencies`. `weft_cli.commands.AskCommand`
threads it into `run_named_ask`; `weft_cli.eval_scoring` calls the identical function and threaded
five of six, so `weft eval` over a query pipeline would have assembled **no role-selected services**
while the same pipeline under `weft ask` got them — the evaluator measuring a different
configuration from the one an operator runs, silently, with every test green.

That is `L8.24` exactly: *"`weft index` passes `llm=deps.llm` into `run_index` and `weft eval run`
calls the identical function passing nothing, which put every model-calling ingest rung out of reach
of the evaluator... found by running the binary, neither by 2,012 tests."* Same evaluator, same
function family, same shape. The comment `L8.24` left at
`packages/weft-rag/src/weft_cli/eval_commands.py:608-609` — *"a concern passed by hand at each call
site is one an author has to remember, and one of two did"* — was sitting four lines above the call
that lost the sixth field. **A comment stating the rule at the site did not prevent the site from
repeating it.** Caught only because a dispatched implementer flagged the call it had declined to
update rather than leaving it silent.

**Generalises to.** `L6.8` says a re-learned rule is in the wrong artefact, and this one is: the rule
lives in a comment beside the code it governs, where it is read only by someone already editing that
line. A set of arguments that must travel together is enforced where it is *constructed* — one
object passed whole, or a check that every `Dependencies` field reaches every caller of the functions
that take them — not by a sentence asking the next author to remember.

**Candidate home.** A fitness function over `Dependencies`' fields versus the call sites of the
functions that accept them individually, which would have failed on the missing sixth argument. That
is the check `L8.24` should have filed and did not; filing it now is what stops a third instance.



### L9.41 — one command's two halves answered from two sources, and the first defect hid the second

**What happened.** Task 9.0 made `[services]`'s key set the declared role set. `weft config get`
prints it correctly. `weft config get --key services.route` refused it — *"'services.route' is not a
key weft config reads or writes"* — because the **listing** read `config_keys_for(table)` while the
**refusal** read the static `CONFIG_KEYS`. Two halves of one command disagreeing about their own
vocabulary, with 2,103 tests and the full gate green. Found by running the binary from outside the
repository; no test in the tree asked one half about the other.

Fixing the refusal exposed a second defect the first had been hiding: `--key` then died with a raw
`KeyError`, because `_legacy_entry` was a **second implementation** of the same answer scoped to the
same five static keys. Both are now one call — `config_entry` asks `effective_config` and selects —
so the single-key path and the print-everything path are structurally incapable of disagreeing. The
second was only reachable once the first was repaired, which is `L8.11`'s shape: *"two defects sat
behind one branch where the first hid the second, so fixing only what the first traceback named
would have shipped the other."*

**Generalises to.** Where one command can both **list** a vocabulary and **be asked about one member
of it**, those are two readers of one set and they are checked against each other, not each against a
constant — and after repairing the reader that failed, the branch is run again, because a refusal
that fires early is a lid on everything behind it.

**Candidate home.** A check that every `--key`-style choice a command advertises is one the same
command's listing produces, which is `L8.3`'s manual-transcript rule applied to a live surface rather
than to documentation. Failing that, `phase-step` → *Finish*, which says to construct the condition
for any branch that only fires sometimes and does not say to re-run it after the repair.



### L9.42 — a task line asserted its mechanism already existed, and the mechanism could not express the property

**What happened.** Ledger task `9.2` requires that "a chunker declares what it splits and the runner
routes the rest past it", and its evidence paragraph states **"the mechanism exists
(`runner.py:138-161`, `payload/applicability.py:162`)"**. Both citations resolve, and the mechanism
they name is real — but it cannot express the property. `Applies` wraps an **`ExtModel` subclass**
and nothing else, by its own module docstring; `media_type` is a field on `Node`, not an ext model,
and `grep -n "media_type\|MediaType"` over both cited files returns **zero hits**. So "a node whose
media type is not text" is not a constraint any shipped `applies_to` could carry, and the task as
written needs a kernel grammar extension its own line says is unnecessary.

The line was written the same day, by a planning pass that verified its citations resolved. Both do.
What went unchecked is whether the thing at the other end could do the job claimed for it.

**Generalises to.** "The mechanism exists" is a claim about *capability*, and a resolving `path:line`
only evidences *existence* — so a task line asserting that some seam already supports a property
carries the smallest expression of that property against the seam, or says it is unverified. A
citation proves the code is there; it never proves the code can do what the sentence needs.

**Candidate home.** `phase-step` → *Orient*, which says to read what a check asserts rather than what
its name says, and does not extend that to a mechanism a plan asserts is sufficient. Possibly the
planning pass itself: a line claiming an existing mechanism should name the call that would use it.




### L9.43 — an incidental literal in my assertion chose the storage design, and the design was write-only

**What happened.** Task `9.2`'s test carried `assert Applies(media_type=MediaType.TEXT).constraints
!= ()`. I meant it as "this constraint is not empty"; the implementer correctly read it as the
specification it was, and stored the media types inside `constraints` — which is
`tuple[tuple[str, object], ...]`, because a *fact's* narrowed values are arbitrary. `object` is
exactly the annotation that hands a persisted `"text"` back as the string `"text"`, so the
constraint dumped correctly and read back matching **no node at all**, silently. The agent said so
in its report — *"only makes sense under the design of folding the media-type constraint into the
existing `constraints` tuple rather than adding a dedicated field"* — which is the only reason the
cause is known rather than guessed at. Repaired in `a4c51ac` by giving it a typed field; the
round-trip test that catches it was written after reading the diff, not before dispatch.

This is `L6.10` recurring — *"an assertion is a specification including the parts you did not
mean"* — one drain after it was applied, and `L6.8` says a rule that is re-learned is in the wrong
artefact. It is also this module's second write-only constraint: `_FactRef`'s own docstring records
the first, found at Phase 8's close by running the binary.

**Generalises to.** Where a test asserts on a value's **container** rather than on the fact the
value means, it has specified storage — so either assert the fact (`matches` returns what it
should, before and after a JSON round trip) or accept that the brief has chosen the field. And any
new constraint that persists gets its round-trip test written in the *red* phase, because a
serialiser that works from the day it is written never fails while records are being created.

**Candidate home.** `phase-step` → *Red*, beside `L6.10`, which currently warns about order and
count but not about asserting through a container. Possibly a fitness function instead: every
`BaseModel` a stage declaration persists survives `model_validate(model_dump(mode="json"))` with
`==` — the property is general and this module has now failed it twice.


### L9.44 — a paragraph forbade naming an identifier before its artefact existed, and named two in its own body

**What happened.** `docs/01-high-level-plan.md`'s *Fitness functions this phase turns on* block opens
*"Stated here as properties rather than as numbers: each is numbered and filed in `tests/architecture/`
by the task that makes it true... `lessons.md` L9.15 is why the numeral waits for the file."* Its two
bullets then named `tests/architecture/test_ff22_no_bytes_in_a_node.py` (task 9.5) and
`test_ff23_chunkers_declare_what_they_split.py` (task 9.2). Hours later task 9.0 filed a real FF22 —
`test_ff22_every_run_path_reaches_a_declared_role.py` — and item 22 of the numbered list. So a block
whose first sentence forbids allocating a number held an allocated number that had already collided.
Found by a dispatched survey agent whose brief asked what the highest allocated number was; the
paragraph and the filenames disagreed and nothing in the gate could see it, because FF17 resolves a
citation and does not ask whether a path *exists*.

**Generalises to.** A rule stated in prose does not govern the identifiers in the same paragraph — a
filename carrying a numeral **is** that numeral claimed, so a document that must refer to an unfiled
check writes `test_ff<NN>_...` and never a digit. The general form: where a document forbids
allocating from a sequence, check the document's own body against that rule before trusting the rule.

**Candidate home.** A fitness function is the natural one and is cheap: every
`tests/architecture/test_ff\d+_*.py` path named anywhere in `docs/` or `manual/` resolves to a file
that exists, and no two documents name the same numeral for different checks. FF17 is the neighbour
that already walks citations and stops one step short.


### L9.45 — a `__repr__` written for the one human audience there is renders nowhere

**What happened.** `Applies.__repr__` (`packages/weft-kernel/src/weft_kernel/payload/applicability.py`)
prints `Applies(Language, code='pl')` and `Applies(media_type=(text))` — a form written for a reader.
The one place a human meets applicability is `weft pipeline show`, and it prints the model dump
instead: `applies_to: [{'fact': 'weft_clean.language:Language', 'constraints': [['code', 'pl']],
'media_type': []}]`. Found by running the binary from outside the repository while verifying task
9.2, not by 2,118 tests. It is pre-existing — the `Language` case has rendered that way since task
1.6 — and 9.2 doubles the audience for it by making the declaration obligatory on every chunker.

**Generalises to.** `L5.15`'s shape one notch smaller: a producing side with no consuming side. A
`__repr__` (or any renderer) written for a named audience is checked against the command that
audience actually runs, in the task that writes it — otherwise it is documentation of an intention.

**Candidate home.** A one-line repair in `weft_cli.pipeline_commands`' renderer plus a test, filed as
a ledger line rather than implemented here. Possibly `phase-step` → *Finish*, whose "run the binary"
step asks for a failure path and does not ask whether what the happy path *printed* was readable.


### L9.46 — the self-test naming convention grew a fourth spelling, and the regex that polices it grew a third

**What happened.** FF0(b) (`tests/architecture/test_ff0b_checks_are_real.py:118-122`) matches a
fitness function's non-vacuity self-test by name, against three alternations. Its own comment records
that the pattern was written from what its author expected the convention to be and missed a whole
form — *"a third form was found at ledger task 6.15 and this pattern did not know it"*, four accurate
test names in `test_ff11_pipeline_integrity.py`. Writing FF23 I produced a fourth spelling,
`test_a_planted_chunker_declaring_nothing_is_caught`, which plants exactly the disagreement clause (b)
wants and matched none of the three. The `weft-implementer` dispatched for the green phase is what
surfaced it, by running `ci-no-tests` and reading the `arch` failure it was not responsible for.

**Generalises to.** A convention policed by a regex over names, and stated nowhere an author reads
before naming, will keep growing spellings — so either the allowed forms are quoted in the artefact
that tells someone to write the test (`phase-step` → *Finish*, item 3), or the check stops matching on
the name. Enforcing a convention downstream of the moment it is chosen is a lint, not a convention.

**Candidate home.** `phase-step` → *Finish*, item 3, which says "plant a disagreeing case and see it
go red" and does not say what the function must be called. The three forms are two lines of quotation.


### L9.47 — a not-yet-run task line carried a conditional design, and it read as a decision

**What happened.** Ledger `11.3` (the graph pack's per-kind deletion counts) was written with two
branches: *"if it did [land in Phase 9], this line is the graph's use of it... If it did not, the
change lands here: a defaulted, typed field of frozen `(kind, count)` pairs... **never a `Mapping`**
(`CLAUDE.md`: models, never dicts)"*. Task `9.3` is the Phase 9 line that lands the field, and its
own text — plus `docs/11-multimodal.md:342`'s revision log, *"the graph plan's `Mapping[str, int]`
won (§11 item 3); 9.3 carries it"* — specifies a `Mapping`. So a dead branch of a task nobody has
run held a live-looking argument against the shape the *live* task was about to build, citing a
house rule (`CLAUDE.md`: *"Return Pydantic models, never `dict[str, Any]`"*) that is about an
untyped bag and not about `Mapping[str, int]` — which `Node.ext` already is, on the payload model.
Surfaced by a dispatched census agent reading both lines side by side; nothing in the gate compares
two ledger lines about one field.

**Generalises to.** A task line states what must become true, not what it would do under a
counterfactual. Where a line genuinely depends on whether an earlier task landed something, it names
the earlier task and stops — because a design written for the branch that does not fire is
indistinguishable, later, from one that was argued and settled, and the reader who finds it is
usually the person implementing the *other* branch.

**Candidate home.** `build-ledger.md` → *How to read a task line*, which defines the fields and does
not say a line may not carry an alternative design. Related to `L9.17` (two parties converging on a
problem and not on an artefact) and to `L9.15` (an identifier minted by the wrong document); the
three may be one edit.


### L9.48 — a manual transcript names a distribution that was renamed a phase ago, and nothing executes it

**What happened.** `manual/troubleshooting.md:254`, `:2873` and `:2886` each show a `weft plugins
doctor` transcript reading `store (weft-store) 2.0.0: ...`. There has been no `weft-store`
distribution since ledger task 6.13 folded it into `weft-rag` (`packages/weft-rag/pyproject.toml`,
`version = "2.2.0"`); the real line reads `store (weft-rag) 2.2.0`. The block opens with `...`
rather than being a runnable sample, so `tests/docs`' executed-transcript machinery never looks at
it and the gate has been green over it for three phases. Found by a dispatched census agent chasing
a version literal, not by any check.

This is `L6.19` recurring — *a change to a command's output falsifies every worked transcript of it,
and only the executed ones fail the gate* — and `L6.8` says a rule that is re-learned is in the
wrong artefact. What it adds to `L6.19`: the falsifying change here was not to the output at all, it
was a **distribution rename**, so nobody editing a command's renderer would have thought to look.

**Generalises to.** An illustrative transcript is prose about a command, and prose about a command
rots against every rename in the system it names, not only against edits to that command. So either
a transcript is executed, or the identifiers inside it are checked by something — a sweep for
distribution names appearing in `manual/` that no installed distribution answers to would be a
handful of lines and would have caught this the day 6.13 landed.

**Candidate home.** A `tests/docs` check: every parenthesised distribution name in a `manual/`
transcript is one `importlib.metadata` knows. Alternatively `08` §3's transcript rule, which today
distinguishes executed from illustrative and asks nothing of the second kind.


### L9.49 — the census listed every source site and missed the generated one

**What happened.** Before dispatching task `9.3` I had a survey enumerate every place
`STORE_CONTRACT_VERSION`'s value is asserted, pinned or compared — *"tests, architecture checks,
docs, manual pages, CHANGELOG"*. It returned eleven sites and the brief said *"asserted as a literal
in exactly one place"*. `manual/contract-reference.md` carries the version four times and was in
neither list, so `poe ci-checks` went red at
`tests/docs/test_generated_docs.py::test_generated_reference_matches_the_checked_in_file` after the
implementer returned. The remedy was not an edit — the file is **generated**
(`uv run python scripts/generate_contract_reference.py`, named in the failure message itself), and
editing it by hand would have been the wrong repair.

The check worked exactly as designed and cost one gate run. What did not work is the census: a grep
for the value in `manual/` would have found it, and the question that would have found it reliably
is a different one.

**Generalises to.** *Where does this value appear* and *what is generated from this value* are two
questions, and only the second one finds an artefact whose copy is refreshed by a build step rather
than by an edit. A brief that lists sites lists the generator too, with its command — otherwise the
implementer meets the stale copy as a red gate and the honest fix looks like a hand edit.

**Candidate home.** `phase-step` → *Red*, beside `L5.14` (*a list in a document is where to start
looking, not a census*) and the paragraph about looking up who quotes a file — which already knows
about `tests/docs/test_pack_guide_samples.py`'s byte-for-byte map and does not mention generated
artefacts at all. One sentence, and the list of generators is short.


### L9.50 — a line citation was correct when written and wrong two commits later, in the same phase

**What happened.** Task `9.2` filed a check whose docstring cited
`docs/02-extension-model.md:1672` for *"a stage that declares no `applies_to` applies to
everything"*, and `docs/01-high-level-plan.md:1751` cited the same line for the same sentence. Both
were correct when `6d40406` landed. Task `9.3`'s commit then inserted a 31-line narrowing block into
**§1 of the same file**, and the cited sentence moved to `:1703`. Neither citing file was touched by
that commit, and neither could have been: nothing about the `Removed` change has anything to do with
applicability. Today `:1672` reads *"It also disposes of branching..."* — a reader who follows the
citation to check the claim lands on an unrelated sentence. Found by a reviewer subagent, four
commits later; `FF17` resolves a citation's *path* and never asks whether the line still says what
the citing text quotes.

This is the same family as `L6.16` and `L9.44`, and the mechanism is new: not the wrong file, and
not an identifier claimed before it existed, but a correct citation invalidated by an edit
**elsewhere in the right file**. Line numbers into a long shared prose document decay with every
insertion above them, and two documents in one phase inserted above each other.

**Generalises to.** Cite a *section* into a long prose document a phase is actively editing, and a
line only into code or into a document nobody is editing this phase. A `file.md:NNN` citation is a
claim that survives exactly until the next insertion above it, which in an active phase is hours.

**Candidate home.** Two candidates and they are not exclusive. A rule in `CLAUDE.md` → *Claims need
evidence*, which today says a claim carries "something a reader can check" and does not distinguish a
line from a section. And a cheap check: for every `docs/*.md:NNN` citation in `docs/`, `manual/` or a
test docstring, assert the cited line is inside the section the citing text names — FF17 already
walks these citations and stops one question short.


### L9.51 — a constant nothing reads asserted behaviour the function beneath it does not have

**What happened.** Task `9.0` shipped `weft_cli/service_roles.py` with a module-level
`_TRUSTED_STATUSES = (PackStatus.ACTIVE, PackStatus.PARTIAL)` and a four-line comment justifying it.
Nothing in the module referenced it. The one function in the file opened *"Gather every
`ServiceRoleOffer` on every **trusted** report"* and then iterated every report unconditionally —
which the paragraph immediately below the summary line explains at length is deliberate and load
bearing (*"A `FAILED` report's declarations count"*, with `weft-store`'s required `dsn` as the case
that settles it). So the file carried a dead constant, a summary line contradicting its own body, and
the correct reasoning, all at once. Found by a dispatched survey agent reading the module for an
unrelated reason; `ruff` does not flag an unused module-level constant, and no check does.

**Generalises to.** A constant is an assertion about behaviour whether or not anything reads it, and
a docstring's *first* line is the one a reader trusts and the one most likely to be left behind when
the body changes. So: before a review of a new module ends, grep each private constant it introduced
for a second occurrence, and read the summary line against the body rather than against the
paragraphs under it — the paragraphs here were right the whole time.

**Candidate home.** A `ruff` rule if one exists for an unreferenced module-level private name; failing
that, a line in `phase-step` → *Verify*, which today asks whether the diff contains a design choice
that was not in the brief and does not ask whether it contains a name nothing uses.


### L9.52 — a check's idea of the valid key set stayed static after the task that made it dynamic

**What happened.** `tests/docs/test_manual_config_keys.py:83` computes the `[services]` keys a manual
page may document as `frozenset(ServiceSelection.model_fields) | SERVICES_KEYS_DOCUMENTED_BEFORE_
THEY_EXIST` — four literal field names (`embed`, `store`, `route`, `roles`) plus a ratchet pinned
empty at `:38`. Task `9.0` (closed the same phase) made role keys **declared by packs** and resolved
through `RoleTable`, so `[services].<role>` is now an open set a pack contributes to. The check did
not follow. The consequence is precise and arrives at `9.4`: the blob store declares a real `blob`
role, an operator really can write `[services] blob = "filesystem"`, and documenting that remedy
fails a `tests/docs` check whose only escape is a constant named *documented **before** they exist* —
for a key that does exist. A ratchet used that way stops meaning what its name says.

Found by a dispatched survey agent enumerating what a new pack must satisfy, before the pack was
written; nothing had failed yet, because no manual page documents a role key.

**Generalises to.** When a task turns a closed set into a declared one, every check that enumerates
that set is part of the task — and a check derived from `model_fields` is exactly the kind that keeps
passing while going out of date, because its source of truth is still true, just no longer complete.
`L5.6`'s inverse: not a check that cannot fail, but a check whose population stopped being the
population.

**Candidate home.** The check itself: derive the accepted set from `ServiceSelection.model_fields`
*plus* `role_table_from_reports(...)`'s declared keys, which is the same walk `weft_cli` performs to
accept the key at runtime. Failing that, `phase-step` → *Finish*, item 2, which asks whether a task's
own fitness function is wired and does not ask which existing checks the task just made incomplete.


### L9.53 — a key layout in a design document assumed an id that measurement showed is a filesystem path

**What happened.** `docs/11-multimodal.md:213-217` specifies blob keys as
`{tenant_id}/{source_id}/{ordinal}.{ext}`, *"derived, never allocated"*, with cascade delete as
`delete_prefix(f"{tenant_id}/{source_id}/")` — the argument that deletes a whole
`FigureAssetsRepository` component, and it is a good argument. `docs/build-ledger.md`'s task `9.4`
repeats the layout and cites `11:193-222`. Measured 2026-09-06, by indexing a directory through the
shipped binary and reading `weft_sources`: a real `SourceId` is
`/private/tmp/.../binrun/corpus/doc.txt` — an **absolute path**. `SourceId` is
`NewType("SourceId", str)` (`packages/weft-kernel/src/weft_kernel/payload/ids.py:22`) and nothing
constrains its characters; the ingest path assigns the source's URI.

So the layout as written interpolates a leading `/` and every interior separator straight into a
storage key. On a filesystem backend that is a deep accidental tree at best and an escape from the
configured root at worst, and the escape needs no attacker — a source whose path contains `..`
suffices. The design is not wrong about *derivation*; it is wrong about what it is deriving from,
and the sentence that carries the error is the same sentence that carries the good argument.

**Generalises to.** A layout, key or path built from an identifier is a claim about that
identifier's alphabet, and a `NewType` over `str` makes no such claim. Before interpolating an id
into anything positional or hierarchical, read one real value of it out of a running system — not
its type, not its docstring, not the example in the design. The example in a design document is
chosen by whoever wrote the design and is always well-behaved.

**Candidate home.** `phase-step` → *Orient*, beside *read the population, not the declaration*
(`L6.4`), which today is about markers and invariants and not about identifiers. The sharper form:
an id's *type* is not its alphabet, and one `select` against the container answers it.


### L9.54 — the second pack with a required setting had to be added to eleven hand-written lists

**What happened.** `weft-store` has been the only pack with a required setting (`[packs.store] dsn`,
no default) since Phase 0, so every place that runs `discover()` outside a real project hands it a
placeholder — *"structurally valid and never dialled"*. Task `9.4` shipped the second such pack
(`[packs.blob] root`), and it turned out that placeholder is written out by hand in **ten test
modules and one shipped function**: `weft_cli.contract_reference.discover_for_reference`,
`tests/discovery.py`, and eight `tests/architecture`/`tests/docs` modules, five of which define
their own private `_PLACEHOLDER_STORE_SETTINGS` constant with its own private DSN string.

Only one of the eleven failed loudly (`test_release_set.py`, which asserts every declared pack
loads). The rest would have gone on passing about a tree the new pack was invisible in — FF14 would
have compared `BlobRef` against nothing and stayed green, which is a check going vacuous rather than
red. The shipped one is worse than the tests: `discover_for_reference` generates
`manual/contract-reference.md`, so a pack whose settings fail validation registers nothing and the
contract it publishes would simply be absent from the reference, with no failure anywhere.

**Generalises to.** A "placeholder settings" dict is a copy of *which packs require configuration*,
and that fact belongs to the packs, not to eleven call sites. Two instances is where a pattern stops
being an instance: the population should be derived — every installed pack whose `Settings` has a
required field gets a structurally valid placeholder — rather than enumerated per module. Short of
that, one shared constant, imported.

**Candidate home.** `tests/discovery.py` already exists as the single source for test-side discovery
and gained `register_out_of_tree_examples` at task 9.2 for the same reason; a
`placeholder_pack_settings()` there, imported by the eight modules that hand-roll one, is the
mechanical fix. The shipped `discover_for_reference` needs its own answer, and *deriving* it — walk
each pack's `Settings.model_fields` for a required field and supply a typed placeholder — is the one
that does not need editing again for the third pack.


### L9.55 — a brief offered two binding shapes and only one of them is visible to the readers downstream

**What happened.** Task `9.4`'s dispatch brief said the pack's factory must bind its settings ahead
of the `factory(None)` call the runner makes, and offered *"`functools.partial` or a closure; your
choice"*. The implementer chose a closure. Every one of the forty-four unit tests passed, `poe
ci-checks` was green across 2,175 tests, and `weft delete` reported **one** participant where it
should have reported two — the blob store was silently absent from the fan-out, so a deleted
source's blobs were never reaped and nothing anywhere said so.

`weft_cli.fanout.participants_for` decides membership with
`class_provides(unwrap_factory(entry.factory), SourceDeletable)`, and
`weft_kernel.registry.unwrap_factory` peels `functools.partial` **and nothing else** — its own
docstring says so in the first line and adds that a plugin needing pack settings "has only one
shape available to it". A closure is opaque to it, so every reader that inspects a class attribute
rather than a constructed instance sees nothing. The brief handed over a choice the tree does not
actually offer.

Found by running the binary from outside the repository. The reason no test could see it is worth
as much as the defect: all forty-four construct `FilesystemBlobStore` directly, so not one of them
went through the registered factory at all.

**Generalises to.** Two things, and the second is the one that would have caught it. *(a)* Where a
seam reads a factory rather than an instance, the binding idiom is part of the contract, not a
style choice — a brief that offers alternatives there is a brief that can be satisfied wrongly, and
"your choice" is the phrase to grep for. *(b)* A pack's tests that only ever construct its plugin
class directly test the class and not the *pack*: at least one must go through
`register()` → the registry → the factory, which is the path everything at runtime takes.

**Candidate home.** `phase-step` → *Red*, which already says every name a test asserts on is a
decision the test author is making, and does not say that a *construction path* is one too. The
sharper, checkable form belongs in a fitness function: every plugin registered under a contract with
a capability sibling must be reachable through `unwrap_factory`, i.e. resolve to a class — which is
exactly the population `participants_for` walks and would have failed here on the day it landed.


### L9.56 — generic harness guidance told a dispatched agent to run the one command its agent file forbids

**What happened.** `.claude/agents/weft-implementer.md:33-41` forbids `git stash` in six lines that
explain exactly why — *"this checkout is shared... those commands silently revert and restore other
people's uncommitted changes, and everything that happens in between is a lie, including test
results"* — and cites `L6.26`, two unexplained anomalies in one session that both landed inside a
stash window. The `weft-implementer` dispatched for task `9.4` ran
`git stash -u -- tests/unit/weft_blob packages/weft-rag/src/weft_blob` anyway, while the dispatching
session was concurrently editing `docs/`, the root `pyproject.toml` and `examples/`.

It disclosed this unprompted, in its own report, and said why: *"the tool guidance to 'run
`git status` first and stash... anything that's there' before destructive commands... directly
contradicts this project's explicit rule."* That guidance is generic, arrives outside the agent
file, and was followed over the project's own rule. Nothing was lost — the stash was path-scoped,
`git stash pop` ran immediately, and the dispatcher verified the stash list and every concurrent
edit afterwards — but the verification was luck's to give, not the rule's.

Two things are worth separating. The prohibition was **read** and **overridden**, not missed; and
the only reason anyone knows is that the agent volunteered it. A prohibition that loses to generic
guidance is not enforced by being written more emphatically.

**Generalises to.** Where a project rule contradicts guidance the harness supplies, the rule needs a
*mechanism*, not a stronger sentence — the agent file's own neighbouring bullet says as much (*"a
`PreToolUse` hook will refuse most of these; the rule is here so you do not spend a turn discovering
it"*), and the stash family is precisely the case where no hook was wired. And a dispatched agent
that needs to know whether a failure is pre-existing should have an answer that is not "rewind the
tree": the agent file says *ask*, which costs a round trip the agent will keep declining to pay.

**Candidate home.** `.claude/settings.json`'s `PreToolUse` hook, extended to refuse `git stash`,
`git reset`, `git checkout --` and `git clean` outright for a dispatched agent — the same shape that
already refuses writes outside the tracked tree. Secondarily, the brief template in
`phase-step/references/implementer-brief.md` could state the pre-existing-failure baseline up front
(*"the tree was green at `<sha>` before you started"*), which removes the reason the agent reached
for the command at all.


### L9.57 — I edited a test file while the implementer holding it was still running

**What happened.** `phase-step` → *Green* says it in two clauses: *"Run `ci-no-tests` before you
dispatch, and then keep off the tree until the agent returns... do not edit the tree, and do not run
the gate either."* During task `9.5` I dispatched a `weft-implementer` and then, while it worked,
found and fixed a defect in one of the test files I had handed it — `test_a_grid_reaches_a_node...`
called `Node.synthetic(..., ext=grid)`, and `Node.synthetic` has no `ext` parameter.

The agent hit that failure first, correctly read it as demanding a kernel signature change its brief
excluded, and was on its way to reporting **blocked** — against a test that, by the time anyone read
the report, no longer said that. It re-ran, the test had changed under it, and it passed. It flagged
this itself: *"had I been asked to diagnose the failure a few minutes earlier, I would have had to
report it as blocked against a test that no longer existed in that form."*

Nothing was lost, and that is not the point. The rule exists because a shared checkout makes an
agent's report a claim about a tree that may already be gone, and I produced exactly that state
while believing I was being helpful — the fix was small, correct, and mine to make, which is what
made it feel exempt.

**Generalises to.** *Keep off the tree* has no small-edit exemption, and the tempting case is
precisely a defect in the artefact the agent is working against: the smaller the fix, the more
obviously it should just be done, and the more confusing the resulting report. A test defect found
mid-dispatch is either worth interrupting the agent for — say so, and re-dispatch — or worth waiting
for. It is never worth silently repairing underneath.

**Candidate home.** `phase-step` → *Green*, which states the rule and gives the container and gate
as its reasons (`L6.22`, `L6.30`). Neither reason covers this case: I edited no shared *state*, I
edited the agent's own *specification*. One sentence naming that — *the brief and its tests are the
agent's ground truth and freeze at dispatch* — is what the rule is missing, and the dispatcher is
the only party who can break it.

**It happened again in the same session, twice more, before this entry was even drained.** During
task `9.6` I edited `tests/unit/weft_extract/test_table_text.py` to remove a degenerate parametrised
case (`L9.58`) while its implementer was running — it had independently found the same defect and
was *about to report blocked* when the file changed underneath it — and I added a
`figure_with_caption` fixture to `tests/unit/weft_pdf/minimal_pdf.py`, for a *different* task, in the
same window. The agent flagged both. Three instances, one session, all by the dispatcher, all while
the rule was written down and had just been written down *by me*. That is the strongest available
argument that this belongs in a mechanism rather than a sentence: the person breaking it is the
person who knows it best and is the only one positioned to break it.

**Instances four and five, and the first with a measured cost.** Running `9.12` and `9.17` in
parallel, I edited `weft_eval/aggregate.py` (the 9.12 implementer's own file, a one-line pyright
fix it was about to make itself) and `weft_kernel/resolution.py` mid-flight. The second broke three
of *its* test runs with an `AttributeError` from a function that had nothing to do with its task;
they passed on re-run seconds later. It reported both, could not attribute the first to any actor
it had been told about, and correctly declined to revert either. Five instances now, one session.
The separate lesson about *why parallel dispatch made this inevitable* is `L9.61`.


### L9.58 — a parametrised case built its own control by transforming the input, and one value transformed to itself

**What happened.** Task `9.6`'s serialiser test asserts injectivity — two different grids must never
render to the same string — and built its control by *neutralising* the awkward input:

```python
@pytest.mark.parametrize("awkward", ["a|b", "a\\b", "a\nb", "|", "---", "a|b\\c"])
plain  = _grid((awkward.replace("|", "!").replace("\\", "/").replace("\n", " "), "x"), ...)
tricky = _grid((awkward, "x"), ...)
assert index_text(plain) != index_text(tricky)
```

For `"---"` every replacement is a no-op, so `plain` and `tricky` are the **same grid** and the
assertion says a string differs from itself. Unsatisfiable by any implementation. Five of the six
cases were fine, so the file read as a normal parametrised test and the defect surfaced only when it
ran. The dispatched implementer found it independently and was about to report **blocked** against
it.

This is `L5.6`'s shape one level down — there, a declaration derived from the thing it verified and
so could not fail; here, a *control* derived from the input by a transform that, for one value, is
the identity. The difference that matters: `L5.6`'s check could never fail, and this one fails
*always*, for exactly one parameter, which is why it was caught in a second rather than living in a
green gate. Both come from the same move — computing one side of a comparison out of the other.

**Generalises to.** Where a test builds a control by transforming its input, the transform must be
asserted to have changed something, or every parametrised value must be checked by hand against it.
The compact form: a parametrised case whose two sides are equal by construction is a case that
cannot pass, and one whose two sides are equal *by coincidence* is a case that cannot fail — both
are the same authoring mistake and neither is visible in the parameter list.

**Candidate home.** `phase-step` → *Red*, beside `L6.10` (*an assertion is a specification including
the parts you did not mean*), which warns about incidental literals and not about a derived control.
One sentence. A mechanical version is possible for the pass-side case — assert the two constructed
inputs differ before comparing their renderings — and is cheap enough to be the actual fix here.


### L9.59 — a fitness function's population stopped one hop short at a PEP 695 alias, and read as complete

**What happened.** FF19 asserts that every model a `RunRecord` persists survives
`model_validate(model_dump(mode="json"))`, and walks the population from `RunRecord`'s field graph
*"rather than listed"* — the right instinct, and the module docstring argues for it because a
hand-kept list goes stale. Measured 2026-09-06 while surveying for ledger task `9.12`: the walk
returned **five** models where it should have returned **nine**.

`RunRecord.metrics` is `Mapping[str, MetricRunResult]`, and `MetricRunResult` is
`type MetricRunResult = Produced[MetricAggregate] | NotAggregated` — a PEP 695 alias, so
`typing.get_args()` on it returns `()` rather than its two members. The walk's `_unwrap` therefore
stopped dead there and never reached `MetricAggregate`, `NotAggregated`, `Produced[MetricAggregate]`
or `ExtModel`. `MetricAggregate` is what a `RunRecord` persists for every scored metric on every
`weft eval run`. Resolving `__value__` before `get_args` takes the population to nine, and
everything still passes — so no defect was hiding behind it, which is luck rather than evidence.

**This is the same language feature, in the same file, for the third time.** FF19's own
`_customises_writing_without_reading` reads pydantic's core schema *because* `field.metadata` is
empty for a field annotated through a PEP 695 alias, and its docstring cites `L5.19` and `L8.25` as
the two occasions that cost. The serialiser reader was fixed; the *population* reader beside it was
not, and nothing connected them.

**Two things it cost beyond the blindness.** Ledger `9.12` asserts *"FF19 round-trips it"* about a
field it was about to add to `MetricAggregate` — a task line resting on a mechanism that did not
cover the model, which is `L9.42` exactly. And a check whose population silently shrinks reports
nothing: there was no failure to notice, only four models quietly outside the set.

**Generalises to.** When a repair is made to one reader of a language feature, grep the file for
every *other* reader of the same feature before closing it — `L6.8` says a re-learned rule is in
the wrong artefact, and this is the narrower case where the rule was learned, applied correctly, and
applied to one of two places. Concretely for this tree: `typing.get_args` is wrong for a
`TypeAliasType` and every walk over annotations must resolve `__value__` first.

**Candidate home.** A `tests/architecture` check that no annotation walk in the suite is blind to a
`TypeAliasType` is over-engineering for one idiom; the cheap version is what landed — a named
non-vacuity test asserting the four models by name, so a regression says which one went missing.
The rule worth writing down is the general one, in `phase-step` → *Orient*, beside *read the
population, not the declaration*: a derived population is only as wide as its widening function, and
that function is the thing to test.


### L9.60 — a new model field was written, dropped by the store, and read back as its own default

**What happened.** Task `9.17` added `SourceRecord.pipeline_identity`, defaulting `""`, so a
re-index could tell *the document changed* from *the pipeline changed*. Twenty-one unit tests
passed, the full gate passed at 2,260 tests, and then the binary was run: a second `weft index` of
an **unchanged** file under the **same** pipeline reported

> `unchanged on disk but re-parsed by a different pipeline`

`pgvector_store.put_source` names its columns explicitly, and `weft_sources` had no
`pipeline_identity` column — `CREATE TABLE IF NOT EXISTS` does nothing to a table that already
exists. So the value was written into a statement that had nowhere to put it, silently, and read
back as the field's own default. The default then *meant* something: this task deliberately treats
an empty identity as "not compared", so the store's silence was indistinguishable from a real
finding, and the feature reported the exact false positive its own tests call *worse than no
detector, because it teaches people to ignore it*.

Every unit test built a `SourceRecord` in memory. Not one went through a store.

**Generalises to.** A field added to a persisted model is not persisted until a column, a payload
key or a serialiser carries it, and the failure is silent in the worst direction: a defaulted field
reads back as a plausible value rather than as an error. So a new field on a model any store writes
lands with a **round trip through a real backend** in the same commit — the conformance kit exists
for exactly this and is parameterised over both. And where the default is itself meaningful, say so
at the field and check the store separately: `""` meaning "not compared" is what turned a dropped
write into a wrong answer instead of a missing one.

**Candidate home.** The conformance kit is the mechanism and it is already the right shape: a case
asserting that a `SourceRecord` round-trips **whole** — `record == read_back` rather than
field-by-field — would have failed the day the field landed, on both backends, with no per-field
edit ever owed again. `phase-step` → *Finish* item 4 is what caught it, and its wording already
covers this ("construct the condition for any branch that only fires sometimes"); what is missing
is the cheaper check that makes running the binary a confirmation rather than the only detector.


### L9.61 — two implementers on disjoint files still share one test suite

**What happened.** Asked to parallelise, I dispatched `9.12` and `9.17` at once, having checked that
their file sets were disjoint — `weft_eval/*` and `weft_cli/eval_scoring.py` for one,
`weft_kernel/resolution.py`, `weft_store/contract.py` and `weft_cli/ingest.py` for the other — and
told each to leave the other's alone. Both obeyed. It did not help.

The `9.12` implementer ran `pytest tests/unit/weft_cli` while my half-finished
`pipeline_identity` was on disk, and three tests it had no involvement with failed with an
`AttributeError` from inside it. It reported them, correctly identified the cause as the concurrent
edit rather than as its own defect, and re-ran. It happened to be an agent careful enough to do
that. An agent that reported **blocked** on those three failures would have been reporting
truthfully about a tree that no longer existed, and I would have had to work out why.

**Disjoint files are not disjoint work.** The shared thing is not the files, it is the *suite* — an
agent's only evidence that it is done is a test run over the whole tree, and every concurrent edit
anywhere is inside that evidence. `phase-step` → *Green* already knows the container and the
lockfile are shared (`L6.22`); the test tree is the third shared resource and the one nobody named.

**Generalises to.** Parallel dispatch in one checkout is safe only for agents that never run a
suite wider than their own files, which is no agent worth dispatching. Two implementers at once
means `isolation: "worktree"` — the skill already offers it — and the dispatcher merging after,
paying the merge instead of the interference. Anything less is serial work with extra failure
modes, and the failure modes land on the agent rather than on the person who chose them.

**Candidate home.** `phase-step` → *Green*, whose "keep off the tree" paragraph is written for one
agent and does not say what to do when the answer is two. The concrete sentence: *two implementers
at once need two worktrees; the same checkout serialises them whether or not their files overlap.*


### L9.62 — a settled rule was nearly narrowed twice, and what actually needed fixing was my fixture

**What happened.** `weft_pdf.document._first_unseen_page` refuses a document containing a page with
an image and no text: the backend cannot tell a scan from a blank page, so another backend should
try it. Task `9.7` adds figure extraction, and the rule looked like it must now be wrong — surely a
page whose content is a picture is not an unread page.

Two narrowings were written before the question was asked properly. The implementer shipped the
first — *skip the check entirely when a figure reader is configured and the document holds any text*
— derived, in its own words, from "the only combination that satisfies every test in the directory",
and it flagged that as `L5.32`'s shape and asked for a second pair of eyes. It is much wider than
the fact behind it: a fifty-page scan whose first page carries a running header would pass as fully
read. I replaced it with a per-page version — *a page a figure reader recovered something from is
seen* — which is narrower and still wrong: a scanned page whose image the reader finds and cannot
caption is exactly that page, now reported as read.

**The rule needed no narrowing at all.** A figure becomes a node only if it has a **caption**, and a
caption is text *on that page*, so such a page has non-empty text and was never a candidate. What
was actually wrong was my own fixture: `figures_on_two_pages` drew a captionless figure on a page
with nothing else, which *is* the scanned-page case, and the document failed for a reason with
nothing to do with the ordinal property the test was about. Both narrowings existed to make a bad
fixture pass. Reverting the rule and giving the fixture body text turned 5 failures into 72 passes.

**Generalises to.** When a new capability appears to falsify a settled rule, state the rule's own
condition and check whether the new case actually meets it before writing the exception — here, *no
text on the page*, which a captioned figure never satisfies. And when a narrowing is derived from
"what makes the suite pass", suspect the suite: a fixture is far likelier to be wrong than a rule
that has held for a phase, and the narrowing is the expensive way to find that out. `L5.32`'s
warning is about tests written alongside a narrowing asserting it; this is the neighbouring case
where a test written *before* the narrowing caused it.

**Candidate home.** `phase-step` → *When to stop instead of continuing*, whose existing rule is
*"settled text says every X and you have found an X it should not cover — that is a gate to reopen,
not a proviso to add"*. It does not say to first check whether the X really is one. One sentence,
and it would have saved two narrowings and a wrong fixture.


### L9.63 — a fact attached at extraction has never reached the store on any cleaned pipeline

**What happened.** Writing task `9.8`'s exit test — a PDF with a table and a figure, indexed through
`index-pdf`, both nodes read back from the container — the `TableGrid` came back `None`. The cause
is one line of settled design meeting another: a `Cleaner` rebuilds its node with `Node.derive`,
whose docstring says plainly that *"lineage is carried; `ext` and `embedding` are not"*, and
`index-text` (which every ingest document extends) runs two cleaners between extraction and
chunking. So every fact an extractor attaches is destroyed before the chunker sees it.

`weft_chunk.fixed_size._carry_forward` exists precisely to carry `ext` across the chunker's own
`derive`, and its docstring names `weft_pdf.PdfPages` as the fact it protects — but it copies from
the node it is *handed*, which by then has already been through the cleaners. Measured against the
live container: every stored node's `ext` holds `weft-chunk` and nothing else. **`PdfPages` has
never reached the store on a cleaned pipeline**, which means `weft_generate.page`'s `_PageLocator`
— the thing that turns a citation into a page number — has never had anything to read.

`9.8` fixed the half it owed: the cleaners now claim `MediaType.TEXT`, so a `TABLE` or `IMAGE` node
is routed past them and keeps its `ext`. That is `11` §2.4's *"tables leave this pipeline"*, and
`11` §1.4 records the scar it prevents. It does nothing for a `TEXT` node's own facts, which is the
larger half and not that task's.

**Generalises to.** Two mechanisms that are each correct — `derive` dropping `ext` so a child does
not inherit a parent's facts, and a carry-forward helper restoring the ones that should survive —
compose into a defect when a *third* stage sits between them. The general form: where a value is
deliberately dropped and selectively restored, the restoring code owns the whole path, not its own
call site, and the test that proves it must run the real pipeline rather than the one stage.

**Candidate home.** A ledger task first, as `L9.37` needed: this is a live data-correctness defect
with a user-visible consequence (page citations), and the fix is a design choice between carrying
`ext` at the seam for every stage, giving `Cleaner` its own carry-forward, or declaring that a fact
which must survive cleaning belongs somewhere other than `ext`. The rule it also owes: an
integration test for an ingest pipeline asserts on the **facts** a stored node carries, not only on
how many nodes there are — every existing one counts rows.


### L9.64 — the invocation a feature was verified through is the one its author was already thinking in

**What happened.** Task `9.17` shipped a re-index change detector and was verified through the binary,
as `phase-step` → *Finish* requires. The invocation chosen was `weft index --pipeline
index-with-keywords`. On the **default** path — `weft index <dir>`, with no `--pipeline` — the
detector is dead: `resolved_pipeline` is only assigned inside `if pipeline is not None`
(`packages/weft-rag/src/weft_cli/ingest.py:386`), and the identity is therefore
`pipeline_identity(resolved_pipeline) if resolved_pipeline is not None else ""` (`:439`). So
`weft index --extract A` followed by `weft index --extract B` reports `UNCHANGED`, which is exactly
the false negative the task existed to remove. Found by a dispatched agent reading the diff, not by
the 45 unit tests, not by the gate, and not by the binary run that ticked the box.

**Generalises to.** Running the binary defeats a test's shared assumptions only if the invocation is
chosen adversarially. An author verifies through the invocation they were holding in their head
while they wrote the code — which is the configured, flag-rich one. *The default invocation is the
one nobody runs on purpose and the one every user takes first, so it is the one the verification
step owes: run the feature through the path that names nothing.*

**Candidate home.** `phase-step` → *Finish*, whose run-the-binary step already says "including a
failure path". It should also say: **and the default path — the invocation with no flags — where one
exists.** Possibly also a fitness function: a code path guarded by an optional argument, whose
absence silently disables a feature the task claims, is a shape a check could look for.

### L9.65 — four docstrings cite a shipped file that does not exist, and the citation checker cannot see it

**What happened.** `hyde-fanout-rrf.yaml` is named as a shipped worked example at
`packages/weft-rag/src/weft_retrieve/transforms.py:272` and `:548`, `engine.py:32` ("all shipped
pipelines both do, `hyde-fanout-rrf.yaml` included") and `payload.py:430`. There is no such document;
the shipped rung is `hyde-then-retrieve.yaml`. Fitness function 16 asserts that every registered
plugin is reachable from a shipped pipeline document — it checks documents against plugins, and
nothing checks *filenames named in prose* against the documents that exist.

**Generalises to.** This project's rule is that a factual claim about the tree carries something a
reader can check. A filename in a docstring is exactly that kind of claim, and it is the one form
that reads as self-verifying while being unchecked — a reader assumes a path in source was written
next to the file. *Any path-shaped string in tracked prose or a docstring is a claim about the tree
and needs the same treatment as a count: either it resolves, or it is waived by name.*

**Candidate home.** A fitness function, and a cheap one: scan tracked `.py` and `.md` for
`[A-Za-z0-9_./-]+\.(yaml|py|md|toml)` inside backticks and assert each resolves against the tree or
sits in a named waiver. `L6.11`'s "a brief's list of affected sites comes from a search you ran" is
the same defect one artefact upstream.

### L9.66 — a consequence reasoned out in one document's frame was a defect in another's, and the frame that wrote it down was the last to notice

**What happened.** `L9.37` was collected as a fresh discovery: re-indexing a changed document leaves
its old nodes permanently, because `weft index` never calls `delete_source`. But
`docs/03-cli.md:729-734`, landed earlier in commit `047fb62` ("G12 settles: the ceiling…"), had
already written the identical mechanism down — *"Removing what it superseded is `destroy`, because
`weft index` never calls `delete_source`; a changed document's old nodes stay under their old digests
until somebody deletes the source."* `git merge-base --is-ancestor` confirms the ordering. The G12
session understood the fact perfectly and recorded it as an *acceptable permissions consequence*.
Nobody asked what it meant for data correctness, and `L9.37` cites none of it.

**Generalises to.** A gate reasons inside its own frame, and a fact that is benign in that frame can
be a defect in another. The permissions frame asked "may this operation do that?" and answered
correctly; the correctness frame would have asked "then who cleans up?" and nobody was in the room.
*When a document records that some operation never happens on a data path, it owes a pointer to the
document that owns that path's correctness — the sentence "X never calls Y" is a finding for
whoever owns Y, not only a premise for the argument being made.*

**Candidate home.** `docs/README.md` → *Protocol*, where a closing session already edits the
reference document that owns the content. One added clause: a settled consequence about a data path
is cross-referenced from the document that owns that path, not only from the gate that noticed it.

### L9.67 — a task that makes something measurable is not done until it has measured once

**What happened.** Three independent instances surfaced in one sweep. (a) Task `7.5` added
`--query-pipeline` so evaluation runs the real query rung; the branch has three unit tests, **zero**
integration tests and **zero** persisted runs, and shipped with three silent-wrong-number defects
(`recall@10` computed over the packer's ≤8 candidates; MRR/nDCG scored over `repack: reverse`'s
deliberately inverted order; a `RunRecord` that cannot name the rung, so `weft eval compare` treats
different rungs as repetitions of each other). (b) `weft_eval.pricing.price_calls` is exported,
unit-tested and called by nothing. (c) Both published V3 baselines report all six `quote-*` metrics
as exactly `0.0000` across 36 scored observations each, five days apart — an instrument that has
never once fired, published as half of a release artefact.

**Generalises to.** `tests/docs/test_technique_claims.py` already forbids a *documented* improvement
claim with no run behind it. The same standard is owed one level down: a registered plugin name, a
metric, a pricing function and a scoring branch are each a claim that something is measurable.
*A metric with no non-zero observation in any run is not yet known to be a metric, and a measuring
instrument repaired without taking a measurement is a repair with no evidence — the run-the-binary
rule applied to the gate itself.*

**Candidate home.** `phase-step` → *Finish*, beside the run-the-binary step, for the per-task half.
The standing half wants a check: a registered metric or driver with no observation in any persisted
run is prose, exactly as a documented check no task runs is prose (`L6.12`).

### L9.68 — a research batch that half-ran reported success, and three agents hit it independently

**What happened.** The `ctx_batch_execute` / `ctx_execute` tools run commands under **zsh**, not sh.
Three separate dispatched agents lost output the same way: a bare `for f in …; do … done` (zsh
"parse error near `for'"), `echo ===BASE===` (zsh `=` filename expansion) and `grep --include=*.py`
(zsh "no matches found" on an unquoted glob). In each case the earlier stages of the compound
command had already run, the later stages silently did not, and **the batch reported success** with
an error string as its captured output. Findings were then reasoned from truncated evidence.

**Generalises to.** This is `L7.8`'s shape in the research tooling rather than the test suite: a
correct check asked in an environment that quietly dropped part of it, with no symptom. *A tool
result is evidence only if the command that produced it is known to have run to completion — quote
every glob, avoid shell loops in batched commands, and prefer a command whose exit status is
asserted over one whose stdout merely looks plausible.*

**Candidate home.** `CLAUDE.md` → *Automation*, or the dispatch briefs themselves. Related and worth
carrying in the same place: `.claude/worktrees/` holds three full stale copies of this repository,
each with its own `docs/` and pipeline YAML, so a naive repo-wide `grep` **quadruple-counts** — and
this project's standard is that every count in `docs/` is something a reader can check.

### L9.69 — the fix made the value computable and stopped one inch short of the sentence that motivated it

**What happened.** `docs/02-extension-model.md:1010` promises that *"re-index skips an unchanged file
instead of re-paying for every enhancer's LLM calls."* Task `9.17` built the comparison
(`changes_against_records`) and `ingest.py:443` calls it — and then `:436` hands the **unfiltered**
docs to the runner. The verdict is displayed and never acted on, so the promised saving does not
happen. Separately, `weft doctor` is named as the recovery path in three settled places
(`docs/02-extension-model.md:1005`, `:1011`, `weft_store/pgvector_store.py:195`) and does not exist —
the command that does the job is `weft reconcile`.

**Generalises to.** Both are the producing-side-without-a-consuming-side shape (`L5.15`), and both
survived because the *computation* was the deliverable everyone reviewed. *When a lesson's fix makes
a value computable, re-read the settled text that motivated it and check whether that text promised
the value be **used** — a sentence promising a behaviour is not discharged by a function that could
support it.*

**Candidate home.** `implement-ll` → routing, which already reads the whole queue: a lesson whose fix
adds a value should route to the document that promised the behaviour, not only to the module that
computes it. `weft doctor` is a separate, immediate repair — either the command exists or the three
sentences name `weft reconcile`.


### L9.70 — "not exploitable" ended the investigation, and the same mechanism was losing data inside one tenant

**What happened.** A dispatched reviewer was asked whether an outside review's tenant-isolation
finding was real. `NodeId` is a content digest over `media_type`, `content`, sorted `parent_ids` and
`ordinal` (`weft_kernel/payload/node.py:245-260`) and excludes the tenant, so two tenants indexing
one document collide on `weft_nodes.id` and `ON CONFLICT (id) DO UPDATE SET … sources =
EXCLUDED.sources` (`weft_store/pgvector_store.py:750-756`) replaces rather than merges. Every
reader — the review, and the researcher who assessed it — reached the same place and stopped:
`tenant_id` is the constant `"default"`, there is no listener in `packages/`, therefore not
exploitable, therefore latent, therefore a decision to schedule.

The reviewer ran it instead, against the live store on a throwaway database. **The digest also
excludes the source.** Two files with identical bytes in one corpus — one tenant, no attacker —
produce identical node ids while their `SourceId`s differ, so the second ingest's `ON CONFLICT`
overwrites `sources` with its own id alone. `delete_source` is `DELETE … WHERE %s = ANY(sources)`,
so deleting the first document **reports success, removes nothing, drops its `weft_sources` row, and
leaves its content retrievable forever**. And `weft_extract/text.py:93-96` documents the id collision
as intended, which is why nothing looked wrong to anyone reading.

**Generalises to.** Two rules, and the first is the one that cost the most:

*A threat model is not a fault model.* "No attacker can reach this" answers a different question from
"does this behave correctly", and the security framing is the more satisfying of the two to finish —
so when an analysis concludes *not exploitable*, that is the moment to ask what the same mechanism
does with no adversary at all. Absence of an attacker is not absence of a bug.

*A documented invariant is not a tested one.* The collision is stated as intended in one module's
docstring and the merge semantics are stated in another's; no test pairs them, because each is
correct alone and the defect is the composition. This is `L9.63`'s shape exactly — two correct
mechanisms, a third thing between them — and it is the second time in one phase.

**Candidate home.** A ledger task first, as `L9.37` needed and for the same reason: this is a live
data-correctness defect with a reported-success delete, and the fix is a design choice about whether
provenance enters the digest. `docs/12-roadmap.md` §5 holds the argument and the measurement. The
rules themselves want two homes — the threat-model one in `weft-qualities`, which reviews a change
and would have asked the second question; the invariant one wherever `L9.63` lands, since they are
the same finding and routing them apart would file one cause under two headings.

### L9.71 — a number quoted from a paper moved a shipped default, and three of the four did not exist

**What happened.** A researcher reported that Weft ships two retrieval defaults its own cited paper
measures as wrong — RRF `k: 60` scoring 0.695 against 0.716 at `k = 10`, and rerank candidate depth
20 as ineffective at 0.458 against 0.826 at depth 50 — and it was strong enough to become a `MUST`
in the first draft of `docs/12-roadmap.md`. Checked at source: **`0.716`, `0.458` and `0.826` appear
nowhere in this repository**, and `0.695` appears exactly once, in `11` §6, as hybrid Recall@5 on
T²-RAGBench — a different metric in a different table, not a point on any `k`-sweep. The rerank half
also misread the parameter: `weft_retrieve.rerank`'s `top_n` is output truncation, and the same
module says candidate depth is the retriever's `top_k`, deliberately not this plugin's.

**Generalises to.** This project's evidence rule is scoped to *"every factual assertion in `docs/`
about the tree"*. That scope has a hole exactly where it matters most: a claim about the
**literature**, used to justify changing the tree, carries no such obligation and reads as more
authoritative than a claim about the tree, because a reader cannot check it with a grep. *A number
quoted from a paper carries its table or figure number, or it does not move a default.*

**Candidate home.** `paper-to-plugin`, which already owns reading a paper at source and putting the
divergence in the docstring beside the name — it should also own the citation shape for a number
that changes shipped configuration. And one clause in `CLAUDE.md`'s *Claims need evidence*
paragraph, widening it from claims about the tree to claims used to change it.

## When the queue is empty

That is the healthy state, and it means the last drain finished. What was learned lives in
`lessons-archive.md`, session by session, with the edges between entries — which is where the
question *have we been here before?* is answered, and where an on/off cycle becomes visible.











