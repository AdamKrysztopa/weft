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

*Drained 2026-09-07 at Phase 9's close — ninety entries: see `docs/lessons-archive.md` →
**2026-09-07 — Phase 9's close** for where each one landed, and `docs/build-ledger.md` →
**Carried repairs** for the twelve that were defects rather than rules. Refilled the same day by
Phase 10's unblocking, below.*

### L10.1 — a plan asserted what shipped code does, from the question the code was near rather than from its caller

**What happened.** `01:981-983` and `build-ledger.md`'s Phase 10 preamble both stated that the
shipped `raptor` "already clusters corpus-wide and writes durable summaries, which is D2 answered by
code and not by the owner", and 10.5's task line repeated it as *the tension, on the line*. It is
wrong. `RaptorSummarizer.run` clusters `payload`, and `payload` is what **one `weft index`
invocation** was handed — so the scope is **batch-wide**: the same ten documents indexed in one
command and in two commands build different trees. Neither paper has that scope, and it is not D2's
clause answered by anything; it is non-determinism nobody chose. Caught while grilling the owner on
D2, by asking what `run` actually receives — one read of the call site, which the claim had never
had. The consequence was live: 10.0's baseline would not have been reproducible under a different
batching, and 10.3's order-independence repair was specified without it.

**Generalises to.** *A claim about the scope of a computation is a claim about what its caller
passes it, so it is checked at the call site — being adjacent to an open scope question is not
evidence about which side of it the code sits on.* This is `CLAUDE.md`'s callers rule
(`L5.32`, `L6.15`, `L9.18`) in a fourth genre: not a proviso, not an invariant, not a review's
finding, but a **planning document describing shipped behaviour it never ran**.

**Candidate home.** `CLAUDE.md`'s callers paragraph is where the rule already lives and it did not
bite here — which by `implement-ll`'s own verdict means the artefact is wrong, not the wording.
Consider `phase-step` → *Orient* step 3, which is where a task line's factual claims about the tree
are read, and consider whether the graph script's **MOVE IT** verdict already covers this family
(`R9.13` filed three such rules at Phase 9's drain).

### L10.2 — the papers were read once and not kept, so every derived claim outlived the ability to check it

**What happened.** `raptor.py:45-56` argues in bold against the summariser embedding its own output,
and `index-with-raptor.yaml:16-17` places the stage before `embed` on that argument. RAPTOR §3 (p.3)
specifies the opposite as the method's own cycle — *"These summarized texts are then re-embedded,
and the cycle of embedding, clustering, and summarization continues"* — and p.4 states *"we embed
all nodes using SBERT."* The plugin diverges from its paper on a point neither its docstring nor its
row discloses, and the divergence costs every leaf a second embedder call. The ledger's Phase 10
preamble records that all four papers were *"read at source and adversarially peer-reviewed before a
line below was written (31 claims confirmed, 5 refuted, 8 overstated)"* — but the PDFs were not kept
in the tree, so nothing downstream could re-check a claim, and 10.4 was written as an `02` §1
**contract** question when the papers settle it as a stage-order defect. Caught only because the
owner had the PDFs on disk at `tmp/raptor/` and said so.

**Generalises to.** *A document that argues from a source must be re-checkable against that source:
either the source is kept where the tree can reach it, or every claim carries the quotation it
rests on — a citation to a paper nobody in this repository can open is an assertion, not a
citation.* The sharper half: **a divergence from a paper is a claim that must be re-verified when
the code around it changes**, because the docstring recording it is the only thing that knows, and a
docstring cannot notice that it is arguing against its own source.

**Candidate home.** `paper-to-plugin`, which owns the paper-to-code path and already requires the
divergence in the docstring beside the name — it does not require the divergence to be *checkable*
later, nor say where a source lives. Possibly a fitness function over `10`'s catalogue rows, since
10.1 is already repairing three overclaims in that document by hand.

### L10.3 — the metric was at its ceiling before the technique ran, and the default depth is what put it there

**What happened.** Task 10.0's first measurement ran `weft eval run --questions ... --top-k 10`
against the reproducible PDF half of the named corpus. It scored `recall@10 = 1.0`, `precision@10 =
0.1076`, `ndcg@10 = 0.9332` — identically, in all three repetitions. The corpus holds **ten**
documents, ground truth is named per *document* (`weft_cli.eval_scoring`'s own choice), and
`_deduplicated_by_document` keeps one entry per document, so retrieving ten retrieves every document
there is and `recall@10` is 1.0 whatever the pipeline does. The baseline the whole of Phase 10 rests
on would have been taken on an instrument that could not move. Caught by reading the first run's
numbers rather than by any check: nothing in the tree relates a retrieval depth to how many
documents the corpus has. Re-taken at depth 3, where the same arm scores `recall@3 = 0.9596` and has
headroom.

**Generalises to.** *A retrieval measurement states the depth it was taken at **beside the size of
the population it retrieves from**, and a depth at or above that size is refused rather than
reported — at document granularity, `k >= |corpus|` makes recall identically 1 and measures
nothing.* The wider shape: an instrument's ceiling is a property of the instrument and the corpus
together, and neither one alone can be inspected for it.

**Candidate home.** `weft_cli.eval_scoring.score_pipeline`, which knows both `top_k` and — through
the resolved store — how many documents were indexed, so it is the one place that could refuse or
warn. Alternatively `weft eval run`'s own renderer, or `tests/docs/test_raptor_baseline.py`'s
`why_depth_three` field promoted into a rule the harness applies rather than a sentence a human
wrote.

### L10.4 — the falsification instrument judges one run, so which repetition you hand it changes the verdict

**What happened.** 10.0's two arms were each run three times. `weft eval compare <a> <b> --baseline
raptor-baseline` judged `ndcg@3` **outside** the baseline spread (Δ+0.019 against 0.916–0.925) — but
`b` was the best of the raptor arm's three runs, and against that arm's own *mean* the difference is
+0.0106 against a full-arm width of 0.0171, which is **inside**. Same six records, same instrument,
opposite verdicts, decided by which repetition was named on the command line.
`weft_eval.falsify.judge_differences` takes one `RunRecord` per side by construction and computes no
arm mean; `weft_cli.eval_commands._falsify_against_baseline` then removes `a` and `b` from the
repetitions, so an arm that supplies a compared run also loses a third of its own measured
variability. Both behaviours are individually defensible and together they make a verdict depend on
an arbitrary choice.

**Generalises to.** *Where a claim is about two configurations rather than two runs, the instrument
must compare their distributions — a verdict computed from one representative of each side is a
verdict about those two representatives, and naming a different one is allowed to reverse it.*

**Candidate home.** `weft_eval.falsify` — a `judge_arms(a_records, b_records)` beside
`judge_differences`, or `weft eval compare` taking a set per side. Task 10.13 is the first caller
that needs it, and `09` §4.3's V3 is the document that already reasons in repetitions rather than
runs.

### L10.5 — the comparability guard checks "model versions" and cannot see the model that did the work

**What happened.** `weft eval compare` refuses two runs whose `corpus`, `model_versions` or
`active_distributions` differ — V3's own failure clause at the CLI seam
(`weft_cli.eval_commands._incomparable_reasons`). 10.0's raptor arm was summarised by
`gpt-5.4-mini`, named in `[llm.roles]`. `_model_versions` derives its mapping from the **resolved
pipeline's stage configs**, and `RaptorConfig` carries `role`, never `model`, because a stage never
names a provider or a model (`manual/operations-guide.md` → *Choosing which model answers*). So the
records for both arms read `{"embed": "openai-embeddings:text-embedding-3-small"}`, and two raptor
runs summarised by two different models would compare as apples to apples with no objection. Found
while taking 10.0 and recorded by hand in `eval/raptor-baseline/measurement.json` under
`environment`, because nothing in the record could carry it.

**Generalises to.** *A guard named for a class of fact must be derived from every channel that
supplies that class — `[llm.roles]` is a second source of model identity, and a check that reads
only the pipeline is a check whose name overstates it.* The same shape as `L9.42`: the mechanism
existed and the capability did not.

**Candidate home.** `weft_eval.run_record.RunRecord.model_versions`, filled from the `RoleTable`
that was in scope at `EvalRunCommand.run` as well as from the resolved stages — or `_model_versions`
renamed to what it actually derives, so the guard stops claiming the wider fact. `R9.6`'s neighbour:
a model an operator sets in `weft.toml` that no artefact records.

### L10.6 — a diff line printed both sides identically, because what changed is a field the line does not print

**What happened.** `weft eval compare` on the two 10.0 arms printed:

```
'leaves-baseline' vs 'raptor-baseline':
  + summarise (Expander:raptor)
  ~ embed: openai-embeddings -> openai-embeddings
  ~ extract: pdf-text -> pdf-text
```

Two of the three lines say a stage changed and then show the same value twice. Both documents
`replace:` those stages with the identical plugin, so `ResolvedStage.provenance` differs
(`leaves-baseline` vs `raptor-baseline`) while `use` does not, and
`weft_cli.render._pipeline_diff_lines` renders `change.a.use -> change.b.use` alone. The line is
correct about *that* something changed and useless about *what*, and a reader comparing two arms of
a measurement is exactly the reader who has to decide whether the two differ by more than the one
stage. Found by running the binary; no test in the tree renders a provenance-only change.

**Generalises to.** *A renderer for a difference must print the field the difference is in, or say
which field it is in — a line whose two sides are identical is a line that has withheld its own
subject.* Sibling of `L9.45` (`Applies.__repr__` reached by nothing) one step over: this one is
reached, and says nothing.

**Candidate home.** `weft_cli.render._pipeline_diff_lines`, with a test in `tests/unit/weft_cli/`
constructing two resolved stages that differ only in provenance — `weft pipeline diff` is the other
command that renders through the same helper, so the repair is one place and covers both.

### L10.7 — the branch a check's own comment calls "the whole question" had never once run

**What happened.** `.claude/skills/phase-step/scripts/next_task.py`'s `live_checks` compares the
Status block's declared phase against *the task its **Next action** row names*, falling back to
ledger order only when the row names none — its own comment: *"Which task the Status phase is
compared against is the whole question, and getting it wrong is why the old check was written
loosely enough to pass."* `NEXT_ACTION_TASK` matched `task 9.14` and `task **9.14**` and not
``task `9.14` ``. **Every Next action row this project has written spells the identifier in
backticks** — twelve consecutive revisions of `docs/README.md` checked by replaying the regex over
`git show <sha>:docs/README.md`, twelve no-matches. So the branch never ran, the comparison always
fell back to ledger order, and the check stayed green because falling back happened to agree while
the row pointed inside the same phase as the first unticked box. It surfaced the moment those two
diverged: 10.0 ticked, Phase 9's two deliberately-unticked conditional boxes still first in ledger
order, and the check reported the Status block stale when the Status block was right. Repaired in
the same edit, delimiter class widened to ``[*`]``.

**Generalises to.** *A regex over a document this repository writes is a claim about that
document's shape, and it is checked by running it over the document's own history — a
`re.search` that silently returns `None` degrades to a fallback path, so its failure looks
exactly like its success.* The sharper half, which is what makes this a third instance rather
than a first: `next_task.py`'s two known defects (`L6.3`, `L6.4`) were both *an input the script
never read*; this is the same defect one layer in — an input it reads and cannot parse.

**Candidate home.** `next_task.py`'s own `self_test`, which runs against a synthetic ledger and
so had a `## Status` fixture written in whatever shape the author had in mind — the fixture is
the second source that agreed with the regex because the same person wrote both (`L5.6`). The
non-vacuity floor for a pattern with a fallback is an assertion that it *matched*, taken against
the real file rather than the fixture; `live_checks` is where that belongs, since it is already
the half that reads the real documents.

### L10.8 — the ledger's own field parser returns a sha that is not one, on three lines

**What happened.** `.claude/skills/phase-step/scripts/next_task.py`'s `_split_fields` reads a task
line's `· sha \`xxxxxxx\` ·` field by splitting on the separator, and a line whose tail continues
past that field leaks the separator into the value. Measured over the live ledger by calling
`parse()` directly: `10.11` and `11.5` both return `sha` = `'— ·'`, and `9.17` returns
`'shared with \`9.12\`'`. Three of the tree's task lines hand a caller a two-character string
where a sha belongs. `next_task.py` itself never notices, because it prints the field rather than
using it; a *second* caller found it immediately — the `implementation-status` skill's own script,
written the same day, which has to distinguish "done, here is the commit" from "ticked with
nothing behind it". It worked around it by pulling the sha out by shape rather than trusting the
field, which is a second parser for the same thing. Raised by a dispatched agent and re-derived
here before being written down.

**Generalises to.** *A parser with exactly one caller has never had its output checked, only its
side effect — the first field a second caller actually reads is where it stops being right.* The
sharper half, which is what makes this fixable rather than merely noted:
`tests/docs/test_ledger_records_a_sha.py` already extracts the same field with its own regex and
agrees with git about it, so the tree holds **two** readings of one field and the checked one is
not the one the skill uses.

**Candidate home.** `next_task.py`'s `_split_fields`, made to stop at the next `· <field>` rather
than at the end of the tail — with the fix asserted against the three live lines above, since a
fixture would have been written in the shape the parser already handles (`L5.6`). Or, better, the
field extraction moved to one place both `next_task.py` and `test_ledger_records_a_sha.py` read,
which is the shape `tests/architecture/conftest.py`'s `tracked_files()` already took for the same
reason.

### L10.9 — a glyph's meaning was documented for one population and read against another

**What happened.** `next_task.py` documents that a `⛔` in a **phase preamble** is a mention that
must be read rather than a verdict, and refuses to rule on it. Nothing says the same about a `⛔`
on a **task line**, and all four occurrences in Phase 10's task lines today are conditional prose
— *"a kernel change and a ⛔ this phase does not take"*, *"⛔ **if** the expansion route is
taken"* — while `docs/README.md` states the phase is unblocked end to end. A reader or a script
that treats the glyph as a status reports four blocked tasks in a phase with none. Found by an
agent writing a second consumer of the ledger, which had to decide what the glyph meant and found
the answer written down for the wrong half of the population.

**Generalises to.** *Where a marker's meaning has been written down for one population, write it
for every population the marker appears in — a rule recorded against preambles is not a rule
about the glyph.* This is `L6.4` (*read the population, not the declaration*) with the failure on
the other foot: here the declaration exists, is correct, and is scoped to a subset nobody said it
was scoped to.

**Candidate home.** `build-ledger.md` → *How to read a task line*, which already defines `⚠` and
`⛔` for task lines and is the document that would be read by whoever writes the next consumer.
Possibly enforced: a task line carrying a bare `⛔` glyph must either name an open gate the
preamble records, or write the glyph inside a conditional clause — which is a shape a check could
tell apart, and which `next_task.py`'s own preamble handling already had to solve once.

### L10.10 — a correct repair read as a regression, because a test had pinned an order nothing specified

**What happened.** Task 10.3 sorted `_cluster_by_similarity`'s input by `Node.id`, so a cluster's
members — and therefore a summary's `Lineage.parents` — come out in a canonical order rather than
in the order the caller handed them over. One pre-existing test went red:
`tests/unit/weft_index/test_raptor.py`'s `test_a_tight_cluster_is_summarised_and_a_singleton_is_
left_alone` asserted `summary.lineage.parents == (a.id, b.id)`, which was the order those two
nodes were passed in and which **no document has ever stated**. The implementer could not fix it
(it may not touch tests) and correctly returned with it red; the repair was to assert the two
facts that *are* specified — which nodes the summary was built from, and that their order is
canonical — rather than the literal that happened to hold.

**Generalises to.** *An assertion on an order, a count or a container shape is a specification of
that order, and the code will be held to it by whoever changes something nearby — so before
writing one, ask whether a document states it; if none does, assert the fact instead.* Nothing
new: `phase-step` → *Red* already says exactly this, in bold, with a worked example. **It did not
bite**, and by `implement-ll`'s own rule (`L6.8`) that means it is in the wrong artefact — a rule
about what a *new* test may assert cannot reach a literal written eleven phases ago, and the
moment it costs something is the moment somebody changes behaviour the literal silently
constrained.

**Candidate home.** Not another sentence in `phase-step`. The falsifying act is *writing an
equality against a tuple, a count or a dict* in a test, so the artefact that could perform it is a
check over `tests/` — an assertion comparing a `.parents`, `.sources`, `.hits` or similar sequence
against a literal tuple, where the same comparison as a set would do. Its population would need
measuring before adoption (`L9.89`), and it may turn out to be too noisy to be worth having, which
is a finding either way. The cheaper half: `phase-step` → *Verify* could ask, of every
**pre-existing** test a green-phase diff turns red, whether the assertion it broke was a
specification or an accident — which is the question actually asked here, and it is asked nowhere.

### L10.11 — a dispatched agent explained a real, deterministic failure as a build artefact

**What happened.** 10.3's implementer reported: *"The very first `pytest` run right after the edit
(and only that one run) showed a stale-build failure on
`test_a_tight_cluster_is_summarised_and_a_singleton_is_left_alone` — actual `lineage.parents`
order didn't match expected, an artefact of `uv run` reusing a wheel built before the edit
landed... Worth knowing that a single `uv run pytest` result right after an edit under concurrent
build activity in a shared checkout can be a false negative — re-run before trusting a first
red."* It was not a false negative. Sorting the clusterer's input by `Node.id` makes that
fixture's parents come out `(b.id, a.id)`, and the assertion pinned `(a.id, b.id)` — verified by
computing both digests: `passage a` hashes to `f380843a…` and `passage b` to `43f4049d…`, so
sorted order reverses them, deterministically, every run. The agent's later green runs were green
because the assertion had been repaired in the shared checkout in the meantime, not because the
failure went away. Had the explanation been believed, the accident would have stayed in the test
and the entry it earned (`L10.10`) would never have been written.

**Generalises to.** *An agent's account of **why** something failed is a claim to re-derive, not a
result to accept — and an explanation that names an environment state (a stale build, a cache, a
concurrent process) is the one to re-derive first, because it is the explanation that dismisses
the evidence.* `L6.32` is the same sentence about a message: *"a message naming an environment
state is a hypothesis, not a diagnosis."* This is that hypothesis arriving inside a report, where
it reads as a finding rather than as a guess, and where `phase-step`'s *Verify* step reads the
**diff** rather than the reasoning.

**Candidate home.** `phase-step` → *Verify* already says a `path:line` an agent reports is a lead
rather than evidence (`L9.34`), and says nothing about a *causal claim*. The cheapest form is that
every red-then-green an implementer reports must name what changed between the two runs — a diff,
not a condition — since "I re-ran it and it passed" and "somebody else fixed it" are
indistinguishable from inside the agent. Possibly also
`.claude/agents/weft-implementer.md`, which is what travels with the dispatch.

### L10.12 — the dispatch had no isolation and the agent added its own, in the shared checkout

**What happened.** The same 10.3 implementer reported using `git worktree add` against the shared
checkout to establish a pre-edit baseline, and noted that the brief's prohibitions *"don't mention
`worktree add`/`remove`"*. It cleaned up after itself and nothing was lost. But the dispatch was
made without `isolation: "worktree"` — a judgement that the task was small and serial — and the
agent then created the isolation the dispatcher had declined to give it, inside the one checkout
the dispatcher was still working in, and named that as the likely cause of the build state it
misdiagnosed in `L10.11`. Two decisions that each looked local: mine not to isolate, and the
agent's to isolate itself.

**Generalises to.** *An agent that needs a baseline needs a checkout, so either the dispatch gives
it one or the brief says how to get one — leaving it unstated is choosing that the agent decides,
in the tree somebody else is editing.* **G14 is open and is exactly this question** — *is an
isolated checkout the default for a dispatched implementer?* — recorded as blocking nothing. It
blocked nothing and it cost something.

**A third instance, one task later, and this one is the dispatcher's fault.** 10.2's implementer
ended up with **three concurrent `poe ci-no-tests` runs** in the same checkout — one auto-
backgrounded by a tool timeout, one it backgrounded itself, and one it could not account for,
which was mine: I ran `poe ci-checks` while it was still working, which `phase-step` forbids in
those words and which I had already broken twice. The contention produced a **false red** —
`test_ff9c_every_contract_has_a_stranger` timed out, because the `arch` step builds real wheels
and installs them into throwaway venvs per test, so two runs contend for CPU and disk rather than
for the database. A clean single run passed 260/260. This matters beyond the incident: `L6.22`'s
mechanism is *two suites truncating each other's tables*, and an author who has internalised that
one will reason "different databases, no conflict" and be wrong — the second mechanism needs no
shared state at all, only a shared machine, and it fails as a **timeout**, which reads as a real
defect rather than as contention.

**Candidate home.** G14, which now has three concrete instances to weigh and should be answered
rather than left open; `references/implementer-brief.md`, whose *Files* section says what may be
written and says nothing about what may be *created* beside it; and `phase-step` → *Green*, whose
"do not run the gate either" sentence gives `L6.22`'s database reason and should give this one
too, since the reason is what a reader checks their own situation against.

### L10.13 — a published contract's docstring states what its first implementation did, and has been false of its second since the day that second shipped

**What happened.** `weft_index/contract.py:18-20` defines what an `Expander` is: *"every node
handed in continues, unchanged, into the output, and new nodes are added beside it — **each one
`parent.derive(content=...)`**, so its id is its own content digest and its `Lineage` names the
parent it was built from."* `RaptorSummarizer` has never done that. It builds through
`Node.combine(members, ...)`, which takes **several** parents, and it has done so since task 2.32
— the contract was written for `hypothetical-questions` and never revisited when the second
registration arrived. Two neighbours carry the same overstatement:
`weft_index/payload.py:24`, where `Representation` is *"a stand-in for the **one parent** it was
built from"*, and `weft_generate.representation`, which already carries a multi-parent branch
**written for `raptor` before `raptor` existed** — so the author of the reader knew, and the
contract and the marker were never corrected. The docstring is also copied verbatim into
`manual/contract-reference.md:268`, generated and drift-checked, so the wrong sentence is
published to operators and a check guarantees the two copies agree with each other. Found by an
agent surveying what task 10.4 would break, not by anything in the gate.

**Generalises to.** *A contract's docstring describes a population — every plugin registered
against it — so the second registration is when it stops being a description and becomes a claim,
and that is the moment to re-read it.* This is `phase-step`'s "settled text says *every X* and you
have found an X it should not cover" in the one place the rule does not look: not `docs/`, not an
`assert` comment (`L5.32`, `L6.15`, and the code-invariant clause added after them), but a
**Protocol's own docstring**, which is settled text with a machine-checkable population sitting
right beside it in the registry.

**Candidate home.** A fitness function is available and cheap, which is unusual for this family:
the registry knows every `(contract, name)` pair, so *"a contract docstring naming a specific
construction (`parent.derive`, `Node.combine`, `with_ext`) is checked against every plugin
registered under it"* is decidable — and the population is small enough to measure before
adopting (`L9.89`). The narrow half is a repair: 10.4 is already editing this file's neighbourhood
and should correct all three sites, since `manual/contract-reference.md` is regenerated from the
first.

### L10.14 — the citation resolved, named the right file, and pointed at the wrong method

**What happened.** `weft_index/raptor.py:60-61` reads: *"A summary `Node.combine` builds carries
no embedding (`Node.combine`'s own docstring: parents are explicit, content is new, an embedding
is not carried over)"*. `Node.combine`'s docstring (`weft_kernel/payload/node.py:131`) says only
*"A summary built from `members`. Parents are explicit and never empty."* The quoted clause about
the embedding is **`Node.derive`'s**, twenty lines earlier. The fact is true — `combine`
constructs without an embedding — and the attribution is not. Fitness function 17 passes it,
correctly and by design: it matches a citation at **basename** granularity and its own docstring
says outright that it cannot check whether the cited line says what the citing comment claims.

**Generalises to.** *A citation to a `Thing.method`'s docstring is a claim about a span FF17
cannot see, so it carries the quotation or it carries nothing — quoting text and attributing it to
the wrong member of the same file is the one form that reads as more rigorous than a bare
pointer.* Sibling of `L8.9`, where a self-citation resolved *because* the basename collided; this
one resolves because the file is right and the member is not.

**Candidate home.** FF26 just established the shape for exactly this in a document: a claim names
the literal string the cited file must contain, and the check greps for it. The same trick works
one granularity down — a citation of the form ``\`X.y\`'s own docstring: "<quoted words>"`` is
checkable by finding the quoted words inside that symbol's docstring, which `ast` can extract. Its
population wants measuring first: how many docstring citations in `packages/` already quote, and
how many only point.

### L10.15 — the plan cited a paper for the failure that paper is the counter-example to

**What happened.** `build-ledger.md`'s Phase 10 task line 10.9 listed the hyperparameters its
source papers tune without evidence and ended *"Chucri's τ_c = 11 is asserted (§6.4)"*. §6.4, p.8
of that paper says the opposite, verbatim: *"The choice of τc is based on the average cluster size
in the full RAPTOR tree, which is always less than 10 (see appendix, Table 12)."* Table 12 exists
and is per-corpus. **τ_c is the one threshold in all four papers derived from a measured property
of the tree it configures** — which is precisely the shape 10.9 is building (`auto`, recomputed
from the run's own payload), so the line cited the best available precedent for its own design as
an example of the failure it was fixing. A second, smaller instance in the same phase: 10.7 cited
*"Chucri Alg. 1, fewer than 5 layers"* where line 4 reads *"while the top layer contains more than
10 nodes **and** there are fewer than 5 layers"* — half a conjunction, and the omitted half is the
more transferable one, since a depth ceiling alone does not stop a shallow, wide tree. Both found
by a dispatched agent re-reading the papers at source, both re-verified here by grepping the
extracted text before the correction was written.

**Generalises to.** *A claim of the form "paper X asserts Y without evidence" is a claim about
what X does **not** contain, and a negative claim about a source cannot be made from a reading
that was looking for something else — it needs a second pass whose whole purpose is to look for
the evidence and fail to find it.* The planning pass that wrote this line read four papers for
what they *say*; the sentence it produced is about what one of them does not, and that is a
different question asked of the same text.

**Candidate home.** `paper-to-plugin`, which owns the read-at-source path and already requires the
divergence in the docstring, and which is where a step could say: a line asserting that a source
*lacks* evidence names the section it looked in. Note the loop worked here — `L10.2`'s remedy was
to keep the papers on disk so a derived claim stays re-checkable, and this is the first thing that
re-check caught. That is evidence for `L10.2`'s rule and an argument for scheduling its
implementation rather than leaving it queued.

### L10.16 — the test double ran out of script and raised `IndexError` instead of saying so

**What happened.** 10.4 moves `raptor`'s one `Embedder` call from the leaves to the summaries, so
two existing tests about an embedder outage had to be re-pointed: their leaves now arrive embedded,
and the run must get as far as *generating a summary* before there is anything to embed. I rewrote
their payloads and their comments and left `_ctx(...)` without an `llm=`, which defaults to
`_ScriptedLLM([])`. `_ScriptedLLM.complete` indexes its reply list by call number
(`self._replies[len(self.calls) - 1]`), so an empty script does not return an `Outcome` — it raises
`IndexError: list index out of range`. The dispatched implementer, whose brief forbids editing a
test, correctly returned **blocked**, and had to reconstruct from the traceback that the stub had
run dry rather than that the implementation was wrong. The repair is one argument in each test.

**Generalises to.** *A test double that answers from a script must fail, when the script runs out,
with a message naming itself and the call it could not answer — an `IndexError` out of a stub is a
defect report about the wrong module, and the reader who gets it is usually the one least able to
tell.* The cost is asymmetric: the author of the stub always has the context to read the traceback,
and the caller who trips it — a later test, or an agent forbidden from touching either — does not.

**Candidate home.** `_ScriptedLLM` in `tests/unit/weft_index/test_raptor.py`, and its siblings:
`grep -rn "self._replies\[" tests/` finds how many scripted doubles in this tree index a list by
call count, which is the population to measure before deciding whether this is one repair or a
convention. `tests/unit/weft_index/test_raptor.py`'s own `_RefusingLLM` docstring already argues
that *"a test that scripts by index is really asserting a scheduling accident"* — the same file
knows the hazard and the sibling stub still has it.

### L10.17 — the spread was estimated from three runs, and the estimate has more spread than the thing it measures

**What happened.** 10.0 took a baseline: three repetitions of each arm, and a minimum detectable
effect derived from the width their means spanned — `mean_average_precision` **0.012626**. It
reported the shipped one-level `raptor` moving that metric by **+0.017677**, outside the width and
therefore measurable. Re-measuring after 10.2 and again after 10.4 produced two more triples of a
configuration that is **retrieval-identical** to each other — 10.2 attaches `ext`, which is not
embedded and which the plain top-k does not filter on; 10.4 changes where the vectors come from,
not what they are; both trees are the same 112 summaries over the same 1,014 nodes. Their widths:
**0.0025** and **0.0215**. Same configuration, same corpus, same embedder, an **8.6-fold**
difference in the estimate. Pooled over the six, the width is 0.021465 — and **+0.017677 is inside
it**, so the phase's headline improvement is not distinguishable from the arm repeating itself.

**Generalises to.** *An interval taken over n repetitions is a random variable with its own
spread, and at n = 3 that spread can exceed the quantity being estimated — so a tolerance derived
from repetitions carries the number of them, and a claim judged against it is only as strong as
that n.* `09` §4.3's derivation is right that the system's own variability is the honest tolerance;
what it does not say, and what `weft_eval.falsify` cannot know, is that three points measure that
variability badly enough to invert a verdict. `L10.4` is the neighbouring half — a verdict flips
with *which* repetition is compared; this is the width itself moving.

**Candidate home.** `weft_eval.falsify.BaselineSpread` already refuses fewer than two repetitions,
with V3's own failure clause as the reason; the same argument reaches further than two, and the
model carries `means` so `len(means)` is in hand at every use. A `DifferenceJudgement` whose
`spread` rests on three points could say so in its `reason`, the way the zero-width case already
does (`L8.17`, `weft_cli.render._falsification_line`) — that precedent is exact: a number that is
technically an interval and not yet evidence, printed with what is wrong with it. Task **10.13**
is the first caller that must not repeat this, and its ledger line should carry the n.

## When the queue is empty

That is the healthy state, and it means the last drain finished. What was learned lives in
`lessons-archive.md`, session by session, with the edges between entries — which is where the
question *have we been here before?* is answered, and where an on/off cycle becomes visible.











