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


### L12.2 — I wrote "three carried repairs are open" about a section holding nineteen

**What happened.** Closing Phase 11 I rewrote `docs/README.md`'s **Blocked by** row and put in it
*"Three carried repairs are open and none is blocked"*, naming `R11.6`, `R11.3` and `R11.7`. Those
are the three **this session had touched**. `grep -c '^- \[ \] \*\*R' docs/build-ledger.md`
answers **19**, against 7 closed. The sixteen I did not name — `R9.3`–`R9.12`, `R10.1`,
`R10.3`–`R10.6` — have been open since Phase 9's and Phase 10's drains, and `R9.1` is the one
genuinely blocked, on **G17**. It was caught one turn later, when the owner asked for a handoff
prompt and I went to list the remaining work from the tree instead of from the sentence I had
just written.

**The row it replaced was wrong in the same direction and by less.** It said *"Four things
standing: `R9.1`, `R11.3`, `R11.5`, `R11.6`"* — also the ones the then-current session had in
view. So this is not a slip in one edit; it is what this row does, and it has been quietly
narrowing the project's own account of its debt for at least three phases. **The count was never
measured by anyone. Each author listed what they were holding.**

**Generalises to.** `L6.1` already says a present-tense count expires and must be re-taken before
being argued from, and `L10.18` already says *prefer a pointer to a count*. Both were applied, and
neither bit, because both are addressed to a reader **arguing from** a number and this was someone
**writing one** — from working memory, about a section they had not opened, in the one file whose
own opening rule is that it holds *state and pointers only*. The sharper rule: **a cardinality in
`docs/README.md` is written by running the command that produces it, in the same turn, and the
command goes in the cell beside the number.** A count with its own recipe next to it is the only
kind the next author can cheaply re-take — and re-taking it is what they will not do if it looks
authoritative.

**Candidate home.** A check, and this one is cheap and non-vacuous: `next_task.py`'s `live_checks`
already reads `docs/README.md` against `docs/build-ledger.md` and already asserts one cardinality
this way — the lessons-queue depth, which is exactly why *that* number has never been wrong twice.
The same shape for open carried repairs is a few lines: parse `^- \[ \] \*\*R` from the ledger,
find the digit in the Blocked-by row, and fail when they differ. Failing that, `docs/README.md`'s
own **Protocol** section, which tells a closing session which rows to edit and does not say that a
number in one of them is a measurement.

**Edges.** `refines L10.18` — stated in this entry's own prose above, written here in the form `scripts/lessons_graph.py` reads. Carried repair `R9.12` taught the script the open queue; an entry that names a recurrence only in a sentence is still invisible to it.

### L12.3 — a filed repair carried a claim about a versioning policy the tree had already settled

**What happened.** Carried repair `R11.6` (`docs/build-ledger.md:6119-6122`) states the envelope
half of its own remedy as a decision, on the premise that *"`envelope_version` is a persisted
contract a scripted consumer parses, so adding `stance` **moves it**"*. That premise is false
against settled text, in two places written before the repair was filed. `docs/09-release.md` §3's
support table rules CLI machine-readable output **"Promised, additively. New fields may be added; a
consumer ignores what it does not recognise. Never frozen"**; and ledger task `6.16` — the task
that added a field, `kind`, to `ErrorEnvelope` — records *"Additive, which is what makes it
permissible at all… and `envelope_version` does not move for a new field"*, a sentence carried in
code at `packages/weft-rag/src/weft_cli/error_envelope.py:81`. `AnswerEnvelope` is explicitly built
on `ErrorEnvelope`'s reasoning (`answer_envelope.py`'s module docstring), so the precedent is on
its sibling, one module over. Caught by grepping `envelope_version` across the tree before
presenting the options — the repair had been filed, read into `docs/README.md`'s **Next action**
row, and routed by `next_task.py` for a day with the premise unexamined.

**Generalises to.** **A repair that files a decision states which settled text leaves it open,
and the grep that shows it does** — because the reason a question looks open is often that its
answer is in a document the filer had not opened. This is `L5.32`'s neighbour from the other side:
that rule stops a task inventing a narrowing rather than reopening a gate; this one stops a task
*opening* a gate the project already closed. Filing a decision is as much a claim about the settled
documents as taking one is, and it is cheaper to check — one grep for the identifier the claim
turns on, at the moment of filing.

**Candidate home.** `phase-step` → *When to stop instead of continuing*, which currently carries
only the converse ("Settled text says *every X* and you have found an X it should not cover" →
reopen the gate) and has no clause for "you are about to declare something undecided". The Orient
step's *"before recommending where a thing should live, grep the settled documents for a rule about
that location"* is the identical act one subject over and is the sentence to extend. Note for the
drain: `L12.2` and this entry are both a **claim written into a routing document without the
measurement that would have checked it** — one a count, one a policy — and may route together.

**Edges.** `refines L5.32` — stated in this entry's own prose above, written here in the form `scripts/lessons_graph.py` reads. Carried repair `R9.12` taught the script the open queue; an entry that names a recurrence only in a sentence is still invisible to it.

### L12.4 — the transcript was real, the raise site it was blamed on was never opened

**What happened.** Carried repair `R11.3` was filed on a live measurement — *"Measured 2026-09-09
from outside this repository, on one process"* — and pastes the exact message an operator sees. The
symptom is right. The **cause** in the same entry is not: it says a plugin name inside a document
*"reaches `weft_kernel.registry` instead and gets none of it"*, and names
`weft_kernel.registry.UnknownPluginError` in its `owner` field. Reproduced 2026-09-10 from a bare
wheel install, one flag different — `weft --json index corpus --pipeline index-qdrant` — and the
error envelope names it: `{"error":"UnknownStagePluginError","exit_code":4}`, raised at
`packages/weft-rag/src/weft_cli/compile.py` → `_contract_for`, **already inside `weft-cli` and
already holding `registry`**. `_registers()` swallows the kernel's `UnknownPluginError` internally
while probing each contract; none escapes. The wrong cause then produced a wrong remedy pair: one
of the two options the entry told a future session to weigh — *"`require_plugin` extended to every
name a resolved document uses"* — is **structurally impossible on that path**, because
`require_plugin` takes a `contract: type[object]` and the contract is the thing being inferred when
the inference fails. `UnknownStagePluginError`'s own docstring says so in as many words: *"Here
there is no contract yet — that is the thing being inferred."* The entry also says 118 names; it is
123 today, `L6.1`'s shape unprompted.

**Generalises to.** **A pasted transcript is evidence of the symptom and never of the cause.** The
moment a repair, a lesson or a review names a *raise site*, a *class* or a *module* as the origin of
output it has quoted, that name is a second claim needing its own second measurement — and on this
CLI the measurement is one flag: `--json` puts the `WeftError` subclass name in the error envelope,
which is the field `09` §3 promises for exactly this. Reading the message and inferring where it
came from is the step that goes wrong, because two modules in this tree compose deliberately similar
sentences about an unresolvable plugin name and only one of them ran.

**Candidate home.** `phase-step` → *Finish* item 4, which already requires running the binary and
pasting the output, and stops one clause short of asking what the output *identifies*; the sentence
to add is that a claimed origin is re-derived, not read off the prose. `L9.34` ("a `path:line` an
agent reports is a lead, not evidence") is the same rule for a *citation* and did not reach this,
because the origin here was not written as a citation at all — it was written as a diagnosis.
Note for the drain: this and `L12.3` are both **`R11.3`/`R11.6` filed from reading over a real
transcript**, and both were caught by one cheap probe in the session that finally acted on them —
one grep, one `--json`. They may route together, and if they do the rule is about the *filing* step
rather than the acting step.

**Edges.** `refines L9.34` — stated in this entry's own prose above, written here in the form `scripts/lessons_graph.py` reads. Carried repair `R9.12` taught the script the open queue; an entry that names a recurrence only in a sentence is still invisible to it.

### L12.5 — my brief introduced an exception class and named none of the sites keyed on one

**What happened.** R11.3's brief mandated a new `weft_cli.compile.RefusedStagePluginError` and
specified it carefully — not a `PipelineResolutionError` subclass, a local import in
`exit_code_for`, the exit code it maps to. It named **none** of the sites in this tree that are
keyed on exception *identity*, and there were two: `tests/architecture/
test_exit_code_tables_are_live.py`'s hand-maintained `_LOCAL_IMPORT_MEMBERS` tuple, and
`tests/docs/test_troubleshooting_coverage.py`'s ratchet, which requires a
`### \`RefusedStagePluginError\`` section in `manual/troubleshooting.md`. Both live in files the
implementer may not edit, so the dispatch could not have succeeded whole; it correctly returned
having left one red and said so. Both checks fired, and the first one's own assertion message says
*"which is exactly the miss lessons-archive L8.12 records"* — the artefact was right and knew its
own history.

**Generalises to.** `phase-step` → *Red* carries this rule already and it did not fire, because it
is written for one trigger: *"When a brief names a **base class**, grep for that base class"*. This
brief deliberately named **no** base class — the whole point of the new class was that it is not in
the family that maps to exit 4 — so the sentence did not apply and the four sites it exists to find
went unlooked-for. The rule's subject is wrong: what these sites key on is not inheritance but
**identity**. **A brief that introduces a new exception class greps for its own name's shape —
the family frozensets, the exit-code branches, the ratchet tuples, the troubleshooting headings —
and a class that deliberately joins no family owes that grep more, not less**, because none of the
usual inheritance-shaped searches will surface it.

**Candidate home.** `phase-step` → *Red*, the existing `L8.12` paragraph, whose trigger clause is
what needs widening from "names a base class" to "introduces or re-parents an exception class". Note
for the drain: this is `L8.12`'s **fifth** site found by a fifth mechanism, and the mechanisms are
now good — both checks caught it in seconds and named the rule. What is left to fix is only the
brief-writing step, which argues for a sentence rather than a new check.

**Edges.** `recurs L8.12` — stated in this entry's own prose above, written here in the form `scripts/lessons_graph.py` reads. Carried repair `R9.12` taught the script the open queue; an entry that names a recurrence only in a sentence is still invisible to it.

### L12.6 — six tests, six single-row fixtures, and the defect was in the row *labels*

**What happened.** R11.3's whole subject is a message an operator reads. I wrote six tests for it,
every one with exactly **one** `PackReport` in `reports`. All six passed. The first real run of the
shipped binary printed this:

```
These distributions contributed nothing... : weft-rag (failed); weft-rag (failed);
weft-rag (partial); weft-rag (failed); weft-rag (failed); weft-rag (failed); weft-rag (failed).
```

Seven rows an operator cannot tell apart, one of which was the answer. The sentence was keyed on
`PackReport.distribution`, which was correct and unambiguous while every pack shipped in a
distribution of its own — and **G19 made fourteen first-party packs share one name**, so the
discriminating fact became `PackReport.pack`. `PackReport`'s own docstring predicts this exactly:
the two facts *"stopped being the same the moment one distribution shipped fourteen packs, and a
report that carried only the second could no longer tell fourteen rows apart."* A single-row fixture
cannot collide with itself, so no assertion could have looked wrong. Repaired the same session, with
a two-row test that goes red against the old labelling.

**Generalises to.** `phase-step` → *Red* already says to name the dimension a test varies and check
the fixture varies it (`L11.42`, `L11.45`). Both of those are about a *value* dimension; this is the
one below them: **where the thing under test renders a collection, the fixture holds at least two
entries, or the rendering of the collection is untested — separators, ordering, deduplication and
above all whether two entries are distinguishable at all.** One-row fixtures are the default because
they are the cheapest thing to write, and they are exactly the size at which a labelling bug is
invisible.

**Candidate home.** `phase-step` → *Red*, beside the two fixture rules it already carries — this is
the same paragraph's next sentence, not a new section. Note for the drain: it is also the second
consequence of **G19** to arrive as a defect (`R11.3`'s own stale *"install the distribution that
ships it"* remedy was the first, repaired in the same commit), which suggests the useful mechanised
form is not a test rule at all but a sweep: **every site that renders `PackReport.distribution` to
an operator, asked whether it means the distribution or the pack.** That is a grep, it is finite,
and it would have found both. **The sweep was run in the same session rather than filed**: the only
other operator-facing renderer of a `PackReport` is `weft_cli.plugins_report`, which was **already
correct** — `_summary_line` renders `f"{report.pack} ({report.distribution})"` and falls back to the
distribution only where `pack` is `None`. So `weft plugins doctor` printed `qdrant (weft-rag):
failed` accurately in the very run where the refusal one module over printed seven identical
`weft-rag`s. That sharpens the routing: the convention existed, in this repository, one import away,
and the new code did not go looking for it — which is `L11.2`'s rule (*grep for the machinery it may
already have*) applied to a **convention** rather than to a mechanism.

**Edges.** `refines L11.42` — stated in this entry's own prose above, written here in the form `scripts/lessons_graph.py` reads. Carried repair `R9.12` taught the script the open queue; an entry that names a recurrence only in a sentence is still invisible to it.

### L12.7 — I reverted the file I planted in, and the lockfile kept the plant

**What happened.** Proving R11.3's new architecture check could fail meant renaming an extra in
`packages/weft-rag/pyproject.toml` — `otel` to `otel-support` — running the check, watching it go
red, and renaming it back. That is *Finish* item 3 done correctly, three times over. What no step
covered: the `uv run pytest` in the middle re-resolved the workspace and rewrote **`uv.lock`**, and
reverting `pyproject.toml` did not revert it. `uv.lock` sat with `provides-extras = [..., "otel-
support", ...]` naming an extra that no longer existed anywhere.

**A full `uv run poe ci-checks` then passed against it** — 288 architecture, 2,534 unit and docs,
128 integration, `GATE_EXIT=0` — because every check that reads extras reads `pyproject.toml`, and
nothing in this tree asks whether the lockfile still agrees with the manifests it was resolved from.
It was caught by reading `git status --porcelain` before writing the commit message, one line above
`uv.lock`, by eye.

**Generalises to.** **A plant-and-revert reverts the file you edited, never the state that file
drives.** `phase-step` → *Finish* item 3 already carries the neighbouring case — a staged-then-
deleted plant leaves a tracked path with no file behind it — and this is the same class one file
over: a plant inside a *manifest* is a plant inside the lockfile the moment anything resolves. So
the rule is `git status` after the revert, not just a re-read of the planted file. The sharper
statement is `CLAUDE.md`'s own: *"the gate you ran is only the gate if the environment is… the
lockfile is the committed one"* — which this repository states as a thing to check and provides no
way to check.

**Candidate home.** A check, and a cheap one: `uv lock --check` (it exits non-zero when the lockfile
is not up to date with the manifests) as a step in the `ci-checks` composite, beside the ruff-cache
clear that `L9.1` bought. That turns a sentence in `CLAUDE.md` into the mechanism `L9.56` says a
prohibition needs. Note for the drain: this is the **third** entry in this queue where a documented
claim about the environment had no code behind it (`L12.1`'s skip count, `L12.2`'s repair count,
this) — the shape is *a fact `docs/` asserts that nothing re-derives*, and all three may route to
the same place.

### L12.8 — the paragraph explaining the convention was parsed as an instance of it

**What happened.** R11.7's whole subject is that `10` §4 reserves technique names in prose a parser
reads by positional cleverness. The repair adds a second, independent number — the section states
how many names it reserves, and the check refuses a run where the parser reads a different count.
Writing that sentence, I explained the new convention in the same section:

> Every reservation below begins its own line with `` · `name` ``

`_BACKTICK_TOKEN` is `` `([a-z][a-z0-9-]*\*?)` ``, so **`name` was parsed as a twenty-seventh
reservation**. The section genuinely holds 26 readable reservations plus one the parser drops
(`describe-query-image`, found by measurement the same hour), so 26 real + 1 phantom = 27, and the
sentence I had just written said 27. **The count check passed**, on two wrong numbers that happened
to agree, and the live defect it was written to expose stayed invisible. Caught only because four
*other* tests in the same commit were red and the count test's absence from that list did not look
right.

**Generalises to.** **A check that reads a document is data for itself, and the paragraph
explaining the check is the most dangerous line on the page** — it is where the convention's own
syntax is most likely to appear in illustration, written by the person who knows the parser and is
therefore least likely to reread it as input. Two consequences worth separating: *(a)* a documented
convention is illustrated in a form the parser cannot match — here, line-anchoring the pattern is
what made the mid-sentence example safe, which is a reason to prefer an anchored shape beyond the
one R11.7 already had; *(b)* **two numbers agreeing is not two numbers being right**, and a
count check earns nothing unless a deliberate disagreement has been watched — the plant this
repository requires for a fitness function applies to any two-sided assertion, not only to a sweep
that might match nothing.

**Candidate home.** `phase-step` → *Finish* item 3, whose plant rule is written for a *check* and
whose reasoning covers any assertion whose two sides could both be wrong the same way — this is
that rule's second subject. There is also a mechanical half worth the drain's attention: a
`tests/docs/` parser could refuse to read anything from the paragraph that *documents* it, by
requiring the convention's own prose to be fenced or by excluding lines that are not anchored —
which is what the R11.7 design ended up doing for a different reason, and it is why the phantom
disappeared rather than needing a waiver.

### L12.9 — the tool said it edited 160 sites; nothing had asked whether the tree still parsed

**What happened.** `R11.8` retrofits a quoted fragment onto every citation in the tree — a
mechanical edit at **160 sites across 46 files**, written by a script. The script reported
`would annotate: 160 … skipped: 0`, then `already carrying one: 160` on a second pass, and I read
that as done. It was the tool agreeing with itself: both numbers are its own regex counting its own
output. The fragment is delimited with `"`, and a citation inside a Python file very often sits
inside a **string** — an assertion message, an f-string — where a bare `"` closes it. **Twenty-nine
files stopped parsing.** Found by `ruff format`, the first step of the gate, in about a minute:
*"Failed to parse tests/unit/weft_cli/test_service_roles.py:159:99: Expected `)`, found name"*.

**Then the recovery's own check lied in the other direction.** The repair de-annotates and
re-annotates with `'` inside `.py` files, and I verified it by `ast.parse`-ing every tracked Python
file — which reported **28 still broken**, at lines like `def add[T](self, ...)`. That is PEP 695
generic syntax, valid 3.12 and a syntax error in **3.9**, which is what bare `python3` is on this
machine. `CLAUDE.md` states that fact, scoped to `.claude/hooks/`; an ad-hoc verification script is
not a hook and inherits the same interpreter and none of the warning. `uv run python` said zero.

**Generalises to.** Two halves of one rule about bulk edits. **(a) A mechanical edit is verified by
something that did not perform it** — a tool's own count of its own output is the
`L5.6`/`L9.28` shape (both sides from one source) wearing the clothes of a progress report, and the
cheap independent check here was *does the file still parse*, which costs a second and covers every
site at once. Run the cheapest whole-tree validity check immediately after a bulk edit, before the
expensive gate and before reading the tool's summary as a result. **(b) An ad-hoc script that
inspects this tree runs under the same bare `python3` the hooks do**, so it cannot parse the
3.12 idiom the packages are written in — `uv run python` is the interpreter that can, and a
verification script reporting failures at `def name[T]` is reporting its own version, not the tree's.

**Candidate home.** (a) belongs in `phase-step` → *Verify*, beside `L11.35`'s "after a bulk edit,
re-read every assertion it touched" — same trigger, one level coarser: that rule is about *meaning*
after a bulk edit and this one is about *validity*, and validity is the one a machine can answer
for free. (b) belongs in `CLAUDE.md` → *Automation*, whose "Hooks are not project Python" paragraph
already carries the 3.9 fact and scopes it to hooks alone; the sentence to widen is which code that
covers. Note for the drain: this is the third entry in this queue produced by a check that was
right about its own question and wrong about the one being asked (`L12.7`, `L12.8`, this).

**Edges.** `refines L11.35` — stated in this entry's own prose above, written here in the form `scripts/lessons_graph.py` reads. Carried repair `R9.12` taught the script the open queue; an entry that names a recurrence only in a sentence is still invisible to it.

### L12.10 — the plan's next action is a group of repairs and the router can only name one

**What happened.** Closing `R11.3` made the remaining backlog legible as **four groups**, not
fourteen items: documents making a claim no checker can verify (`R11.7`, `R11.8`); a check deriving
its expected set from a proxy (`R9.4`, `R9.6`); the observability seam (`R10.1`, `R10.3`, `R9.8`,
`R9.5`); a fitness function whose population is narrower than its claim (`R9.3`, `R9.7`, `R9.9`,
`R10.6`). Several are one hole seen from three call sites, and `R10.1`'s own entry already says its
group is *one design rather than four repairs*. Writing that into `docs/README.md`'s **Next action**
row as *"Carried repairs `R9.4` and `R9.6` together"* failed `next_task.py --check-live`:
`NEXT_ACTION_REPAIR` is `[Rr]epair\s+[*\`]{0,2}(R\d+\.\d+)`, singular, so the plural sentence
matched nothing and the check fell back to the first unticked task — Phase 9's `9.15` — and reported
the Status block as disagreeing with the ledger. Reworded to *"Carried repair `R9.4`, taken together
with `R9.6`"*, which routes.

**Generalises to.** The reword is correct and the gap is real: **the routing vocabulary can say
"next task" and "next repair" and cannot say "next group", at exactly the point where the project's
own remaining work stopped being a list and became four.** A grammar that only expresses one unit
quietly pushes the author toward writing one unit — which is how a group gets started one item at a
time, and how `R9.4`'s four lessons came to be four lessons about one cause in the first place. The
rule: *when a plan's own vocabulary cannot express the shape the work has taken, widen the
vocabulary rather than reshaping the work to fit it.*

**Candidate home.** `next_task.py` — `NEXT_ACTION_REPAIR` widened to `[Rr]epairs?` and to collect
**every** `R\d+\.\d+` in the row, with `_repair_failures` run over each, so a row naming a group is
routed and each member checked for being open. That is a few lines and it makes the check say more,
not less. Note for the drain: this is small and only bites while the backlog is grouped — but the
next three Next action rows are all groups, so it bites three more times before the queue is next
drained.

### L12.11 — the fixture said "the roles a real installation declares" and named two of five

**What happened.** `weft config get`, with no arguments, on a project with no `weft.toml` at all —
the default flagless invocation of a shipped command — exited **1**:

```
$ weft config get
[services] holds no selection for 'blob'. Selected: (none).
```

`effective_config` lists every key `config_keys_for` names and reads each through
`ServiceSelection.plugin_for`, which *refuses* a role nothing selects. A real installation declares
five roles — `blob`, `describe`, `embed`, `graph`, `store` — and `ServiceSelection` has a field
with a default for only two of them. So the command was broken for every project that had not
selected all five, which is every project, and **2,543 tests were green**. Found in the first
minute of running the binary for a repair about a different half of the same surface.

The reason no test could see it is one line of `tests/unit/weft_cli/test_config_surface.py`:

> `#: The roles a real installation declares.` — `_INSTALLED = RoleTable(roles={"embed": …,
> "store": …})`

Two roles, both of them the ones that default. The failing branch was **unreachable from the
fixture**, and the fixture's own comment asserted it was reality.

**Generalises to.** `L12.6` is the neighbouring rule — a fixture symmetric in the dimension under
test — and it does not quite cover this: the defect here is not that the fixture had one entry, it
is that the fixture **claimed to be representative and was not**. So: **a fixture whose name or
comment says it is "what a real X looks like" is checked against a real X, once, in the commit that
makes the claim.** One `discover()` and a `sorted(table.declared)` would have printed five names
next to a literal holding two. The claim is the trigger — an ordinary fixture invents whatever the
test needs and owes nothing; the moment it says *real*, it has made an assertion about the world
with nothing checking it, which is `docs/README.md`'s own "claims need evidence" one layer down.

**Candidate home.** `phase-step` → *Red*, in the fixture paragraph that already carries `L11.42`,
`L11.45` and (pending) `L12.6` — this is that paragraph's next sentence and shares its trigger.
There is also a mechanical form worth the drain's attention, cheaper than it looks: a `tests/`
check that a fixture named `_INSTALLED`, `_REAL`, `_SHIPPED` or the like agrees with a live
derivation is not writable in general, but *this* one is — `RoleTable` fixtures could be built
from `role_table_from_reports(discover(...))` and narrowed, rather than written out, which is
`L11.17`'s "copy the existing double" applied to a fixture that has a real source available.

**Edges.** `refines L12.6` — stated in this entry's own prose above, written here in the form `scripts/lessons_graph.py` reads. Carried repair `R9.12` taught the script the open queue; an entry that names a recurrence only in a sentence is still invisible to it.

### L12.12 — `pytest.raises(WeftError)` plus a substring accepted the error that said the opposite

**What happened.** Repairing `R9.4` I made `effective_config` omit a declared role nothing selects,
and wrote a test for the other half — that asking for such a key *by name* still explains itself:

```python
with pytest.raises(WeftError) as caught:
    config_entry(None, "services.blob", table=...)
assert "blob" in str(caught.value)
```

It passed. It passed against a build where the shipped binary did this:

```
$ weft config set services.blob filesystem   →  set services.blob = filesystem in weft.toml.   (0)
$ weft config get --key services.blob        →  'services.blob' is not a key weft config
                                                 reads or writes.                              (4)
```

Writable and unreadable, same key, same project. `config_entry` fell through my new omission into
its own `# pragma: no cover` branch and raised `UnknownConfigKeyError` — which **is** a `WeftError`,
and whose message **does** contain `blob`. Both halves of the assertion were satisfied by the
sibling error that says the opposite of the truth: it tells an operator to look for a typo in a key
they are entitled to set. Found by running the binary, in the pair of commands either one of which
alone looks fine.

**Generalises to.** **Assert the exception the code should raise, not the family it belongs to** —
and where a family exists precisely so that several failures share a base, `pytest.raises(<base>)`
asserts almost nothing. The substring made it worse rather than better: a key name appears in every
message *about* that key, so matching on it distinguishes none of them. Two cheap habits close it:
name the leaf class, and match a fragment of the sentence's **claim** (`"holds no selection"`)
rather than of its subject. This is `L9.43`'s rule — asserting a container shape instead of the
fact a field means — arriving at an exception instead of at a tuple, and `L5.6`'s comparison rule
arriving at a type instead of a value.

**Candidate home.** `phase-step` → *Red*, in the paragraph that already says "assert the fact a
field means, never its literal shape" — this is that sentence for `pytest.raises`, and the
mechanical form is worth the drain's attention: a `tests/` check that every `pytest.raises` naming
`WeftError` itself (rather than a subclass) carries a reason, in the shape of the waiver constants
this project already uses. `WeftError` has enough subclasses that catching the base in a test is
almost always a widening nobody intended.

**Edges.** `refines L9.43` — stated in this entry's own prose above, written here in the form `scripts/lessons_graph.py` reads. Carried repair `R9.12` taught the script the open queue; an entry that names a recurrence only in a sentence is still invisible to it.

### L12.13 — the optional method was on the sink, the decorator, and nothing in between

**What happened.** `R10.1` gives a sink an optional `show_only_stage`, reached by `getattr` so it
need not join the published `TokenSink` contract. I wrote it on both sinks, wired the caller, and
wrote **three** unit tests plus a wiring test that captured the call — `phase-step`'s own `L9.79`
remedy. All passed. The repair was **inert on every path the CLI runs**, twice over:

1. Every real run hands the caller `weft_cli.cli._EmissionTrackingSink`, a decorator that forwards
   `emit` and `close` — the contract — and nothing else. `getattr(sink, "show_only_stage", None)`
   found `None` and did nothing, silently. My wiring test passed because it constructed its own
   double, which *had* the method.
2. The stage stamped on each chunk came from a `ContextVar` the seam sets. `wrap` is called for
   services and providers too, nested inside a stage, and `weft_llm.client` wraps its own call as
   `stage=f"llm:{role}"` — so the innermost call won and every chunk was stamped `llm:generate`
   instead of the pipeline position. Narrowing on "was `stage` passed" did not fix it either;
   only an explicit `position` that just one caller supplies did.

Both were found in the first two runs of the shipped binary, by measuring what the sink was told
and what the chunks carried — `told: []`, then `chunk stages: ['llm:generate']`.

**Generalises to.** Two rules, and the first is the sharper one. **A duck-typed optional method is
a contract with no checker, so its test must drive the object the run actually hands over — not one
the test built.** `L11.17` says to copy an existing double rather than write one from prose; this
is the step past it: where a *decorator* stands between the caller and the object, no double is
right, because what the run passes is the decorator. Ask *what type does the caller actually
receive*, and construct that. The second: **a `ContextVar` set by a wrapper that wraps more than
one kind of thing records the innermost, not the meaningful one** — if the value means "which X am
I inside", only the code that knows it is an X may set it, and inferring that from another
parameter's presence is a guess that holds until someone else passes it too.

**Candidate home.** `phase-step` → *Verify*, beside the `L9.87` sentence about a plugin
constructing its own dependency for real: same failure, opposite direction — there a double hid a
dead capability, here a double hid a dead *wire*. The mechanical form worth the drain's attention
is narrower and cheap: a `tests/` check that every `getattr(x, "<name>", None)` reaching for an
optional method has a test naming the decorator types that must forward it — this tree has exactly
one such decorator today (`_EmissionTrackingSink`) and one such reach, so the check would be small
and would have fired.

**Edges.** `refines L9.87` — stated in this entry's own prose above, written here in the form `scripts/lessons_graph.py` reads. Carried repair `R9.12` taught the script the open queue; an entry that names a recurrence only in a sentence is still invisible to it.

## When the queue is empty

That is the healthy state, and it means the last drain finished. What was learned lives in
`lessons-archive.md`, session by session, with the edges between entries — which is where the
question *have we been here before?* is answered, and where an on/off cycle becomes visible.
