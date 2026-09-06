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
site list.

**Candidate home.** `phase-step` → *Red*, which already carries `L8.12` in the base-class form
("when a brief names a base class, grep for that base class") and does not carry the
add-a-method form. This is that rule re-learned one shape over, which `L6.8` says means moving it
rather than restating it — the two should be one sentence about extending a surface.



### L9.30 — the catalogue row claimed a mode the same page withdrew two paragraphs above it

**What happened.** `docs/10-technique-catalogue.md:148` names the shipped plugin
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

**What happened.** `packages/weft-rag/src/weft_index/pipelines/index-with-raptor.yaml` tells the
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



## When the queue is empty

That is the healthy state, and it means the last drain finished. What was learned lives in
`lessons-archive.md`, session by session, with the edges between entries — which is where the
question *have we been here before?* is answered, and where an on/off cycle becomes visible.




