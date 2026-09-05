# Lessons archive — what was learned, when, and how the entries relate

`lessons.md` is the **queue**: it fills while working and `implement-ll` drains it to empty at each
phase close. This file is where the drained entries land, **session by session**, and it is the only
part of the loop that grows.

It exists for one failure the queue cannot see: **oscillation**. A rule is added, a later session
finds it noisy and removes it, a third session re-learns the original lesson and adds it back. Each
step is defensible alone; the sequence is waste, and in a flat list it is invisible because the queue
that would have shown it was emptied twice in between. A flat list also cannot answer the question
that matters most at a drain — *have we been here before?*

So entries carry **edges**, and the edges are the point.

## The edge vocabulary

Closed set, spelled exactly as below — the same discipline the codebase applies to string constants.
An entry with no edge to anything is the normal case and needs no marker.

| Edge | Means | Why it is separate |
|---|---|---|
| `refines L?.?` | Narrows or widens an existing rule without contradicting it | Healthy. The rule was right and imprecise |
| `supersedes L?.?` | Replaces an earlier rule with a better one, same intent | Healthy. The old rule stops being live |
| `moves L?.?` | Same rule, relocated — usually `CLAUDE.md` → a hook | **The expected repair.** A rule that was applied and did not bite was in the wrong artefact, not wrong |
| `recurs L?.?` | The same class of defect, seen again, after a rule for it was already applied | **A finding, not an entry.** The existing rule did not bite. Do not write a second rule — move the first one |
| `reverses L?.?` | Undoes an earlier rule: it fired on correct work, or its cost exceeded the defect's | Legitimate **once**. Twice in a chain is oscillation |
| `caused-by L?.?` | This defect exists *because* of an earlier rule | The most valuable edge and the rarest. A rule with a `caused-by` child is a rule that bought a problem |

## The oscillation rule

> **A `reverses` edge pointing at an entry that itself carries a `reverses` edge is a stop, not an
> entry.** Do not apply it. The subject is not a lesson — it is an unsettled decision wearing one, and
> it goes to a grilling session with the whole chain as its evidence.

This is `phase-step`'s own rule for a settled decision that looks wrong, applied to the tooling: *that
is information, not failure, but it is a stop rather than a patch.* The chain is what makes the
argument, which is why the archive keeps reversed entries in place rather than deleting them.

`scripts/lessons_graph.py` walks this file and reports oscillating chains, `recurs` counts and
orphaned references. `implement-ll` runs it **before** applying anything.

## Format

One `##` section per drain, newest first, headed by the date and what closed. Inside it, one entry
per line:

```markdown
## 2026-09-14 — Phase 5 close

- **L5.3** *measure before asserting applies to design proposals about this tree, not only to
  claims that already required it* → `CLAUDE.md` → *Working here* · `a1b2c3d`
- **L5.1** *a decision citing an existing mechanism as its escape hatch must run it before closing*
  → `weft-qualities`, new lens · `a1b2c3d` · `refines L5.4`
- **L5.7** *declined* — fires on correct work; the cost of the check exceeds the defect's · `reverses L4.2`
```

Four fields, in order, and only the last is optional: **id**, *the rule in one sentence* (or
`declined` and the reason), **where it landed**, **the commit**, **edges**.

The one-sentence rule is written to be read cold, months later, by someone who was not there — it is
what `.claude/hooks/lessons_context.py` injects into every session, so it is the entire memory of the
loop. If it needs the original entry to make sense, it is not finished.

---

## 2026-08-22 — Phase 6 midpoint

*Thirteen entries, drained at the midpoint rather than the close, which is Phase 5's own finding
applied (`build-ledger.md` → Phase 6 preamble: "Phase 6 should drain at its midpoint as well as its
close"). Seven were logged before this session and six during it. They grouped into six subjects, and
the grouping moved four of them: `L6.4`+`L6.15` and `L6.3`+`L6.13` each turned out to be one rule seen
twice, and `L6.5`+`L6.14` were one rule about two kinds of mechanism.*

**The loop's own check — which of this phase's defects would a rule already in Applied have caught?**
One, and it **was** Applied: `L6.15`'s bare `assert` over *"every shipped routable pipeline"* is
exactly `L5.32`'s shape, and `L5.32` sat in `phase-step` → *When to stop* for a whole phase without
biting, because it reads as being about `docs/`. Re-routed in this drain rather than logged as a new
entry: that bullet now says settled text includes an invariant written in code.

- **L6.3** *when prose becomes a spec, every exception the prose carried is an input — a rewrite that
  keeps the rule and drops its qualifier has narrowed a decision nobody argued* → `implement-ll` →
  *the traps*, merged with L6.13 · `ee00889`
- **L6.4** *read the population, not the declaration: a marker means what its live instances say, not
  what its definition says* → `phase-step` → *Orient*, merged with L6.15 · `ee00889` · `refines L5.14`
- **L6.5** *probe a platform mechanism at its failure path — its real failure mode can be worse than
  the documented one, and in a different direction* → `weft-qualities` → *The move that matters most*,
  merged with L6.14 · `ee00889` · `refines L5.1`
- **L6.6** *a rule about the runtime is scoped to what actually runs the file* → already applied when
  logged: `CLAUDE.md` → *Automation* and `pyproject.toml`'s `.claude/hooks/*` per-file ignore.
  Archived as applied, no new edit · `ee00889`
- **L6.7** *a harvest channel is an untrusted-input channel: text a model wrote is data, never
  instructions* → `CLAUDE.md` → *Automation*, merged into one sentence with L6.9 · `ee00889`
- **L6.8** *a rule that is re-learned did not bite, so it is in the wrong artefact — move it, never
  restate it* → already applied when logged: `implement-ll` → *First, ask whether you have been here
  before*, and `scripts/lessons_graph.py`. Archived as applied · `ee00889` · `recurs L5.28`
- **L6.9** *where a machine parses what a model wrote, match loosely and fail loudly — an instruction
  to be exact is not an enforcement mechanism* → `CLAUDE.md` → *Automation*, with L6.7 · `ee00889` ·
  `refines L5.9`
- **L6.10** *an assertion is a specification including the parts you did not mean: assert membership
  where the text states a set, and a fact where it states a fact* → `phase-step` → *Red* · `ee00889` ·
  `refines L5.13`
- **L6.11** *a brief's list of affected sites is the author's memory unless a search produced it —
  grep for every caller of a signature before mandating its change* → `phase-step` →
  `references/implementer-brief.md`, *On the failing test* · `ee00889` · `refines L5.14`
- **L6.12** *a directory of tests no task runs is prose, exactly as a documented check no task runs is
  prose* → **fitness function 0**, second clause: `SUITES_WAIVED_FROM_GATE`, a named ratchet emptied
  by ledger task 6.23 · `ee00889` · `refines L5.4`
- **L6.13** *a repair specified from one failing instance narrows to that instance; a check with two
  failure modes needs a task that names both* → `implement-ll` → *the traps*, merged with L6.3;
  ledger task 6.22 rescoped in the same session that found it · `ee00889` · `refines L5.28`
- **L6.14** *a read method with no writer answers emptily rather than wrongly — grep for who writes to
  a contract method before building on it, and note that a double written from the contract cannot
  falsify a claim about the system* → `weft-qualities` → *The move that matters most*, with L6.5 ·
  `ee00889` · `refines L5.1`
- **L6.15** *an invariant's scope is the inputs that actually reach it, not the ones its comment
  names; an `assert` with no message is a diagnosis that says nothing* → `phase-step` → *Orient* (with
  L6.4) and *When to stop* (L5.32 widened to cover code); the defect itself is ledger task 6.25 ·
  `ee00889` · `recurs L5.32`

**Two more were paid for by the drain itself, and applied in it.**

- **L6.16** *the oscillation check read only each entry's first line, so it saw 6 of the 18 edges
  written down and answered "no oscillation" from a third of the evidence* →
  `scripts/lessons_graph.py` now accumulates an entry's continuation lines, and
  `tests/docs/test_lessons_archive.py` reads the archive by two routes that can disagree. The same
  run also printed "RECURRENCE — L5.32 re-learned 1x" and then closed with "no recurrence", because
  the summary counted a recurrence only at two or more — a summary that denies the line above it is
  worse than none, since a reader skims the last line. Both fixed together · `ee00889` ·
  `refines L5.6`
- **L6.17** *anchoring a document edit on a string finds the illustrative copy first: this drain's
  own section was written inside the Format section's fenced example, where the parser skips it, and
  thirteen entries went invisible with nothing said* → `tests/docs/test_lessons_archive.py`, which
  fails when any real entry is unreachable to the parser · `ee00889` · `recurs L5.14`

  The Applied rule that did not bite is `phase-step` → *Orient*'s "do not grep for the box by hand:
  `build-ledger.md` → *How to read a task line* contains an unticked task line inside a fenced block,
  and a grep finds that one first." Correct, and scoped to one file — so it did not fire for the
  archive's fenced example. The repair is the check above rather than a second sentence, because a
  rule that is re-learned is in the wrong artefact and the archive's own vocabulary calls that
  `recurs`, not a new entry.

**Four findings became ledger tasks rather than rules**, per *do not implement a finding as a rule*:
**6.22** rescoped (L6.13), **6.23** the gate's suite coverage and the shared-container isolation
behind it (L6.12), **6.24** the missing `SourceRecord` writer (L6.14), **6.25** the bare assertion
(L6.15).

## 2026-08-25 — Phase 6's close

Seventeen entries, five subjects. The phase closed with every task ticked and its **exit met in
substance and unmet in letter**, which is recorded in `build-ledger.md` → *Phase 6's close* rather
than ticked past.

**The loop's own check — which of this phase's defects would a rule already in Applied have caught?**
**Three, and all three were Applied.** `L5.10` (repair at the seam) would have caught task 6.25's
three-sites-not-one; `L5.14` (a list is where to start looking) would have caught 6.11's guide
sample; `L5.19` (a legitimately empty subject needs a self-test proving non-vacuity) would have
caught 6.9's inert sweep — and 6.9 *had* a non-vacuity test, which is why `L6.29` exists. Applied
rules that did not bite go where they are executed rather than being restated: all three moved into
`phase-step`'s *Red* and *Finish* steps here, at the moment they govern.

- **L6.18** *route a rule to the artefact that performs the falsifying act, not to the one that would notice afterwards* → `implement-ll` → *Finishing*, which now corrects whatever states the queue's depth, and prefers a pointer to a count · `fcfe0bc` · `moves L6.1` (it was applied to `weft-qualities`, which reads a change rather than performing the drain)
- **L6.19** *a quoted transcript is executable output or it is a claim nothing checks — so either run it or stop quoting it verbatim* → `phase-step` → *Red*, with `L6.31` · `fcfe0bc` · `recurs L5.29` (declined at Phase 5 as "no rule owed" because its instance was repaired; the decline was the error, and the queue's question is whether the shape recurs)
- **L6.20** *a skill whose central argument depends on a mechanism must say what happens when the mechanism is unavailable, and must make taking its own escape hatch visible* → `phase-step` → *Green*, which now asks the ledger entry to say whether the task was dispatched or done in-session · `fcfe0bc`
- **L6.21** *a check that claims to describe what a command emits must call the renderer the way the command calls it* → `phase-step` → *Finish* item 3 · `fcfe0bc` · `refines L5.6` (the two sides stopped being independent not by derivation but by one being frozen at a version of the other)
- **L6.22** *while a dispatched agent is running, do not edit the tree and do not run the gate — it is not only the working tree that is shared* → `phase-step` → *Green* · `fcfe0bc`
- **L6.23** *a before/after heuristic must name the case where there is no "before"* → `.claude/hooks/guard_quality_gates.py`, signature 3, which now says a file is new instead of reporting its own blind spot as a finding · `fcfe0bc`
- **L6.24** *an import probe measures import-time dependencies; a subprocess call is a dependency declaration you have not written yet* → `phase-step` → *Finish* item 4 · `fcfe0bc` · `refines L5.31`
- **L6.25** *before running a suite in a new environment, ask what each of its directories is a claim about* → `phase-step` → *Red* · `fcfe0bc`
- **L6.26** *an agent that does not own the checkout must not run a command that changes what is in it beyond its own edits* → `.claude/agents/weft-implementer.md`, its standing prohibitions, which now list what it may not **run** · `fcfe0bc` · `caused-by L6.22` (same shared checkout, opposite end)
- **L6.27** *a check inside the canonical gate must be decidable from the repository* → ledger task **6.28**, built and closed the same phase: four integration modules now require an explicit opt-in separate from the credential · `fcfe0bc`
- **L6.28** *an equivalence stated in prose between two code paths is a missing test, and the more precisely it names the caller it is wrong about the more expensive it is* → `weft-qualities` → *The move that matters most*; the defect itself is ledger task **6.34** · `fcfe0bc`
- **L6.29** *a waiver-liveness test must assert the check fires on what it waives, never that the waived text exists* → `phase-step` → *Finish* item 3, and applied the same day to `test_ff0_gate_in_the_gate.py`, which had the identical hole · `fcfe0bc` · `refines L5.19`
- **L6.30** *run the gate before dispatching, not only after — a brief whose done-when names a check promises the check currently reports on the agent's diff* → `phase-step` → *Green* · `fcfe0bc` · `caused-by L6.22`
- **L6.31** *where a check already knows which documents quote which files, a brief that edits a file reads that list rather than remembering* → `phase-step` → *Red* · `fcfe0bc` · `moves L6.11` (that rule was Applied and bit only in the dispatched agent's report, which is where a rule lands when the person it governs is not the person who broke it)
- **L6.32** *re-run the command that failed, not a subset of it* → `phase-step` → *Finish* item 1 · `fcfe0bc`
- **L6.33** *a name a design settles on is a claim on a namespace somebody else owns — check the registry at the moment of choosing, not at the moment of publishing* → `phase-step` → *Orient*; the release set is `weft-rag` and G10's decision-log row carries the correction · `fcfe0bc`
- **L6.34** *"published with the release" is a claim about reachability, and a directory in the repository is not reachable* → ledger task **6.35**, with the three candidate answers and `09` §5.2's sentence to correct · `fcfe0bc`

---

## 2026-08-22 — G10 and G13 close

Two entries, logged after Phase 5's drain and spent at the gate close rather than carried into Phase 6
— which is the correction Phase 5's own drain asked for (*"Phase 6 should drain at its midpoint as well
as its close"*). Both are about the **loop and the gates**, not about the tree: no code changed, no
fitness function was added. One build-ledger task came out of the reading rather than out of the
queue — **6.22**, below.

**The oscillation check ran first and was clean** — 32 entries, 5 edges, no `reverses` chain and no
`recurs`. Every edge in the archive so far is `refines` or `caused-by`, which is the healthy shape: no
rule has yet been undone, and the one `caused-by` (`L5.25` ← `L5.32`) is a rule that bought a problem
and was answered by a gate rather than by another rule. **What the graph cannot see, and a reading of
the rows found: `L5.28` routed its generalisation to a skill and left its mechanical half unowned** —
the name-collision check is still `if name in text` at `test_ff9_extension_from_outside.py:426`, and
the row says *"the AST repair is still owed"* with no task behind it. Filed at this drain as ledger
task **6.22**. That is `implement-ll`'s second trap caught one drain late, and it is the one weakness
in an otherwise clean archive: a `recurs` edge would have surfaced it only *after* the defect came
back.

**The loop's own check — which of these defects would a rule already in Applied have caught?**
**L6.1: `L5.14` would have, and it is Applied.** Per this skill's own instruction that answer means
re-routing rather than logging a second rule — but the re-route here is *not* a `moves`, and the
reason is worth recording. `L5.14`'s home is `phase-step` → *Orient*, and a gate session does not run
`phase-step`; the rule reached this session anyway, because `.claude/hooks/lessons_context.py` injects
**every** applied rule at `SessionStart` regardless of which artefact holds it. So the delivery path
was never the weakness. What was too narrow is the rule's *subject*: `L5.14` speaks about a **list of
sites**, and what went stale was a **count**. `L6.1` widens it, in the skill that actually runs when
someone argues from a cited number. That is a `refines`, and calling it a `moves` would have blamed
the artefact for a wording gap.

- **L6.1** *a count a document states in the present tense expires when a phase could have changed it — re-take it before arguing from it, and correct the document in place* → `weft-qualities` → *The move that matters most* · `6d7411c` · `refines L5.14`
- **L6.2** *group a queue by subject before candidate home: entries that are one hole seen from several call sites route to a gate, never to three artefacts* → `implement-ll` → *Before you route anything* · `6d7411c`

---

## 2026-08-22 — Phase 5 close

Thirty-two entries, drained to empty. Four groups did most of the work: *a named mechanism was
never run* (L5.1, L5.4, L5.8, L5.19 → **fitness function 16**), *a check cannot fail* (L5.6, L5.19,
L5.23, L5.28 → the same function's clause b), *the environment is not what the suite assumes*
(L5.12, L5.31 → a new FF9(a) clause), and *settled text was narrowed or trusted without reading*
(L5.2, L5.7, L5.14, L5.32 → `phase-step`). The single most valuable edit is the smallest: L5.17
became a one-flag change to the hook that caused it.

**The loop's own check — which of this phase's defects would a rule already in Applied have caught?**
*None: this is the first drain, and Applied was empty.* That is the honest answer and it is also the
finding — thirty-two entries is what one phase accumulates when the loop has never spent. Phase 6
should drain at its midpoint as well as its close.

- **L5.1** *a design citing an existing mechanism as its escape hatch must run it before the argument closes — naming it is not evidence it works* → `weft-qualities` → *The move that matters most* · `88edcd0`
- **L5.2** *a recommendation must be checked against the settled text that owns the location before it is written up* → `phase-step` → *Orient* · `88edcd0` · `refines L5.32`
- **L5.3** *measure before asserting applies to design proposals about this tree, not only to claims that already required it* → declined as a separate rule; the queue's own evidence is that measurement happened every time it was asked for, and `CLAUDE.md` → *Working here* already carries it · `88edcd0`
- **L5.4** *every fitness function `01` names has a file in `tests/architecture/`* → **fitness function 16**, clause (a) · `88edcd0`
- **L5.5** *a validator that checks each block must also check the container the blocks sit in* → declined as a rule, kept as the instance: the general form fires on correct work constantly, and the specific gap is `weft.toml`'s, already closed · `88edcd0`
- **L5.6** *a check whose two sides are derived from one source cannot fail; read them from places that can genuinely disagree* → **fitness function 16**, clause (b), and `phase-step` → *Finish* · `88edcd0`
- **L5.7** *read what a check asserts, not what its name or purpose says it is for* → `phase-step` → *Orient* · `88edcd0` · `refines L5.14`
- **L5.8** *an artefact a promise is made in must be written to by the protocol that closes the work* → task 5.2f's `tests/docs` check, plus `weft-qualities` · `88edcd0`
- **L5.9** *an empty result means "I did not find it", never "it is not there" — and where two layers can both diagnose, the first must make the check the second makes* → `phase-step` → *Build* · `88edcd0`
- **L5.10** *repair user-facing text at the seam that renders it for every caller, never at the raise site it was noticed from* → `phase-step` → *Build* · `88edcd0`
- **L5.11** *no new import may put pack code on `weft --version`'s path* → declined: fitness function 8(b) already caught it, in the same task, before the commit. The rule bit; nothing to add · `88edcd0`
- **L5.12** *a new default is checked by the whole suite, not by its own tests or one tree* → `phase-step` → *Finish*, and **FF9(a)**'s new environment clause · `88edcd0`
- **L5.13** *a test asserts the fact a config field means, never its literal shape* → declined as a rule — it fires on ordinary correct tests — and kept as the instance, fixed at task 5.2a · `88edcd0`
- **L5.14** *a list of sites in a document is where to start looking, not a census; grep for the thing itself* → `phase-step` → *Orient* · `88edcd0`
- **L5.15** *an extension point has a producing side and a consuming side, and a per-pack shim is not the general mechanism* → scope decision `S7`, task 5.2g, and `weft-qualities` → requirement 1 · `88edcd0`
- **L5.16** *a newline-delimited stream carrying two shapes needs a discriminant* → ledger task **6.16** · `88edcd0`
- **L5.17** *an auto-fix hook cannot tell "no usage yet" from "no usage ever"* → `.claude/hooks/format_python.py`, `F401` made report-only · `88edcd0`
- **L5.18** *a copied venv's console script still points at the original interpreter* → declined: a fact about `venv`, not about this repository, and it fires nowhere · `88edcd0`
- **L5.19** *where a check's real subject is legitimately empty, the floor is a self-test proving the comparison is not vacuous* → **fitness function 16**, clause (b), and `phase-step` → *Finish* · `88edcd0` · `refines L5.6`
- **L5.20** *an ext-model registry is scoped to what a store actually sees, and two models sharing a namespace collide* → `02` §1, recorded at task 5.2g; no rule owed · `88edcd0`
- **L5.21** *a test that passes only because another file ran first is a defect in the test* → ledger task **6.17** · `88edcd0`
- **L5.22** *a guide's worked examples are checked against the packs they cite* → closed by task 5.3; `08` §3 clause (c) already owns it · `88edcd0`
- **L5.23** *a property about caller shape needs a structural check, never a textual one* → `phase-step` → *Orient*, with `L5.28` · `88edcd0`
- **L5.24** *a capability Protocol specified against "what should exist" is only askable by the thing that already owns those methods* → **G13**, settled 2026-08-22 · `88edcd0`
- **L5.25** *a fan-out's "only the configured one" exception cannot tell a second primary from a derived participant* → **G13**, settled 2026-08-22 · `88edcd0` · `caused-by L5.32`
- **L5.26** *a hand-rolled double must carry every public method of the class it doubles* → `tests/architecture/test_ff9_extension_from_outside.py`, a completeness test · `88edcd0`
- **L5.27** *a check that sweeps a directory must be able to answer the question for everything it sweeps* → fixed at task 5.4's repair; no rule owed beyond `L5.6`'s · `88edcd0`
- **L5.28** *a name-collision check built as a substring search is unsound, and a real thing must not take the name a document reserves for a hypothetical* → `phase-step` → *Orient*, with `L5.23`; the AST repair is still owed · `88edcd0`
- **L5.29** *a document's worked transcript is checked against what the code can actually say* → `02` §4 corrected at task 5.6; no rule owed · `88edcd0`
- **L5.30** *a pack that can produce a typed result must be able to render it* → **G13**, settled 2026-08-22 · `88edcd0`
- **L5.31** *an out-of-workspace pack installed into the development venv changes what the whole suite sees* → **FF9(a)**'s new environment clause · `88edcd0` · `refines L5.12`
- **L5.32** *settled text saying "every X" plus an X it should not cover is a gate to reopen, never a proviso to add* → `phase-step` → *When to stop instead of continuing* · `88edcd0`

---

# Drained 2026-09-05 — Phase 8's close

**Twenty-seven entries, the largest queue this project has held**, and nine of them (`L7.1`–`L7.9`)
had survived a previous phase close, which `implement-ll` forbids. Three agents routed them in
parallel; every claim below was verified against the tree rather than taken from the entry.

**The drain's own finding, and it changed how the rest were read.** The triage question I set —
*"is the defect still there?"* — was the wrong one, and one agent said so instead of answering it.
`lessons` requires an entry be written the moment a defect is caught, which is usually the commit
that fixes it, so in a healthy queue nearly every *instance* is already repaired: of the nine
`L7.x` entries, seven had their defect long gone and their rule still homeless three phases later.
Reading *instance repaired* as *entry finished* would have emptied this queue of everything it was
for. That is written up as `L8.18` and applied to `implement-ll` in this same drain.

**Dispositions.**

| Entry | Disposition |
|---|---|
| `L7.1` | Applied — `implement-ll` → *The two traps*, third trap: a filed remedy is an untested one |
| `L7.2`, `L7.6`, `L7.8` | Applied together — one paragraph in `CLAUDE.md` → *Quality gates*. All three are "the gate I ran is not the gate CI runs", and no artefact stated that. The two checks they also propose are filed as ledger work |
| `L7.3`, `L7.9` | **Discharged** — fully implemented in `.github/workflows/release.yml` (cooling-off job, `--check-url`, `max-parallel: 1`), which cites `L7.9` by id at `:45`. That citation is why this took seconds to confirm, and is now required by `implement-ll` → *Finishing* |
| `L7.4`, `L7.7` | Applied together — a new `weft-qualities` prompt on what identity a surface keys on, and whether it is unique. Both are assumptions true only while cardinality was 1 |
| `L7.5` | Filed as ledger work — a check that a documented "gap" paragraph is retired when its task ticks |
| `L8.1` | Applied — `next_task.py` → `live_checks`. **Verified false-passing on the live tree before the fix**, and the repair re-aimed the comparison rather than tightening it: the subject is the task *Next action* names, not the first unticked one, because that row outranks ledger order and Phase 8 deliberately ran before Phase 7 |
| `L8.2` | Applied — `weft-qualities` lens 5: a waiver's reason being true is necessary and not sufficient |
| `L8.3` | Filed as ledger work — an executed-sample check over `valid_options` tuples quoted in manuals. The instance was hand-patched and `tests/docs/test_manual_config_keys.py` covers the narrower half |
| `L8.4` | **Discharged** — `build_index_services` (task 8.10), which names this lesson in its own docstring |
| `L8.5` | **Discharged** — `_validated_sub_config`/`SubPluginConfigError` (task 8.11). The structural fix supersedes the check the entry asked for |
| `L8.6`, `L8.16` | Applied together — `weft-qualities` lens 1 gains *which* stranger, and what the old constant satisfied by construction. `L8.16` recurred `L8.6` in the same phase, so this is one paragraph, not two |
| `L8.7`, `L8.8`, `L8.9` | **Discharged** — fitness function 17, whose own docstring cites all three |
| `L8.10` | Applied — `phase-step` → *Finish* item 3: a `git ls-files` check is not in its own population until staged |
| `L8.11` | Applied — `phase-step` → *Finish* item 4: construct the condition for a branch that only fires sometimes |
| `L8.12` | Applied — `phase-step` → *Red*: grep the base class before writing *Already decided*. The `exit_codes.py` ratchet it also implies is filed as ledger work |
| `L8.13` | **Discharged** — `tests/architecture/test_pinned_external_facts.py` (task 8.14), both halves |
| `L8.14` | Half applied — the broken command in `index-text.yaml` is repaired. The check that would have caught it (executed samples over shipped `pipelines/*.yaml` comments) is filed as ledger work |
| `L8.15` | Applied — `docs/README.md`'s Status table gains a `Lessons queue` row holding only a number, and `live_checks` asserts it equals the count of `lessons.md`'s own `## Queue`. Parsed structurally, never grepped out of prose |
| `L8.17` | Half applied — `09` §4.3 now says what a zero-width interval actually claims. The rendering change and the deeper sampling repair are filed as ledger work |
| `L8.18` | Applied — `implement-ll` gains the triage question and the cite-the-id convention |

**Filed as ledger work rather than carried:** `docs/build-ledger.md` → *Phase 8's close* holds the
seven follow-ups above. They are tasks with owners, not lessons awaiting a second drain — which is
the distinction `implement-ll` draws between draining a queue and deferring it.

## The entries as they stood

### L8.18 — "is the defect still there?" is the wrong question to ask a lessons queue

**What happened.** Draining this queue, I dispatched three agents to route 25 entries and asked
each of them, first, whether the defect its entries described *still existed* — expecting that a
queue nine entries deep across a phase boundary would be full of stale rows. It is not. Commit
`1b1a600`'s own message says *"Four lessons logged, L7.4 through L7.7"*: those entries were written
in the same commit that repaired the very defects they describe, which is exactly what the
`lessons` skill asks for — *"write it when it is caught"*. So **almost every entry in a healthy
queue will show its instance already fixed, because fixing the instance is what produced the
lesson.** Of the nine `L7.x` entries, seven had their triggering defect long gone and their
generalisation still homeless three phases later; only two were genuinely finished.

Asking "is it still true?" therefore invites exactly the wrong answer. It reads *instance repaired*
as *entry dead*, and archiving on that basis would throw away the whole point of the queue — which
is that `implement-ll`'s own trap already names: *"fixing the instance and calling the lesson
applied leaves the class open."* I wrote that question into all three briefs. Two agents answered
it literally; the third pushed back and said the question was wrong, which is the only reason this
is written down.

**Generalises to.** *A lessons queue is triaged on whether the generalisation has a home, never on
whether the instance survives — the instance is expected to be gone, because the repair is what
paid for the entry.* The corollary for anyone dispatching this work: the question to ask is *"does
the artefact that would have caught this contain the rule yet, and would it have bitten?"*, and
"the defect is fixed" is evidence about the past, not about the queue.

**And a positive pattern worth requiring rather than admiring.** The two genuinely-finished `L7.x`
entries are recognisable because the artefact enforcing them **cites the lesson id at the point of
enforcement** — `.github/workflows/release.yml:45` names `docs/lessons.md L7.9` in a comment
directly above the job that implements it. That is what made "already applied" checkable in
seconds rather than arguable. Every other applied entry in this tree is much harder to confirm.

**Candidate home.** `.claude/skills/implement-ll/SKILL.md`, in two places and they are different
edits. The triage question belongs wherever the skill tells a drainer how to read an entry — it
currently has a trap about implementing a finding as a rule, and this is its mirror image, about
retiring a rule because its finding is gone. The citation convention belongs in *Finishing*: an
entry is applied when the artefact names the lesson id, which turns the next drain's hardest
question into a grep.

### L8.17 — a zero-width interval is a claim about the repetitions, not about the system

**What happened.** Task 8.8's own exit demonstration, run twice from outside the repository a
couple of hours apart against the identical corpus (digest `81018d4c243a` both times), the
identical shipped document (`index-text`), the identical deterministic `hash` embedder and the
identical question file, produced two different baselines: `mean_average_precision` **0.833** in
the first session and **0.667** in the second. The compared rung scored **0.778** in both, so the
move is the baseline's alone. And in *each* session the three or four repetitions agreed exactly —
both runs recorded a **zero-width interval**.

That is the instrument reporting maximum confidence at the exact moment it had least. `09` §4.3
blesses a zero-width interval as *"correct and strict"* for a deterministic system, and the
reasoning is sound — but it silently assumes the repetitions **sample** the system's variability.
Repetitions taken back to back in one session share whatever state differs between sessions, so
they are correlated, and a correlated sample measures the noise it cannot see as zero. Every
difference then reads as `outside-baseline-spread`, which is the over-confident direction.

**The mechanism is not proven and is stated as a hypothesis rather than a finding**, because the
tree does not yet let me distinguish the candidates: the leading one is tie-breaking in the store's
returned order — with three tiny documents and hash vectors, several cosine similarities plausibly
tie, and pgvector's order for tied rows depends on physical layout, which changed between sessions
because the table was truncated and repopulated by other demonstrations in between. `MAP` moving
from 5/6 to 2/3 is one answer sliding from rank 1 to rank 2, which is what a tie-break flip looks
like. **What is certain is the observation, not the cause**, and the observation alone is enough:
two runs the plan calls identical are not.

**Generalises to.** *A dispersion measured from repetitions that share a process, a session or an
ordering measures only what varies inside it — so an interval is a claim about the repetitions that
produced it, and a tolerance derived from one may not be a tolerance for anything else.* The
sharper form for this project: **a zero-width interval should be read as a warning that the
repetitions were correlated, not as evidence of determinism**, because a genuinely deterministic
system and a badly-sampled one produce the identical record.

**Candidate home.** Three, and they are not alternatives. (a) `09` §4.3 states the zero-width case
as *"correct and strict"* and that sentence now needs its assumption written next to it — this is
settled text that is not wrong but is incomplete, and `phase-step` → *When to stop* says a
narrowing invented mid-task is indistinguishable afterwards from one that was argued, so it wants a
deliberate edit rather than a proviso. (b) `weft eval compare --baseline` could **say** when the
interval is zero-width, rather than printing it like any other number — the cheapest honest change,
and it costs one line of rendering. (c) The deeper repair is that a baseline's repetitions should be
required to differ in whatever the store's ordering depends on, which is a real piece of work and
should not be decided from one observation.

### L8.16 — a router document missing a required upstream stage dies with an attribute error

**What happened.** Writing task 8.12's test I authored a minimal router document —
`{"id": "route", "use": "nearest-description"}` — and it failed inside the run with
`'route' failed: 'Query' object has no attribute 'query'`. The cause is a real pairing:
`weft_retrieve.routing.NearestDescription` reads `payload.query.text` off a `Scorecard`, and
`run_routed_ask` hands whatever document `[services] route` names a bare `Query`, so a router
without a `query-scorer` stage ahead of `nearest-description` cannot work. The shipped
`route.yaml` pairs them, and this test file's own docstring already explains why — so the
requirement is *known*, written down in prose, and enforced by nothing.

**What makes it a lesson rather than my typo** is task **8.12** itself. While only an installed
pack could supply the router, the only router in existence was the correct one and the pairing
could not be got wrong. 8.12 lets a project author one — so the first person to write a router
by hand meets an `AttributeError` surfacing through a stage-failure wrapper, naming a Python
attribute rather than the stage that needed a `Scorecard` and the stage that produces one. That
is precisely the failure `01` requirement 5 and CLAUDE.md's loud-failure rule exist to refuse,
and it is `L8.6`'s shape for the third time in this phase: **making something configurable does
not preserve the constraints around it, it exposes them.** I wrote L8.6 in this same phase, cited
it in 8.12's own investigation, and still shipped the test that walks into it.

**Generalises to.** *A stage's input requirement is a contract the assembly step should check, not
a pairing documented in prose and discovered at run time — and the moment a document type becomes
operator-authorable, every constraint its first-party example satisfied by construction becomes a
refusal somebody has to write.*

**Candidate home.** Two halves. The check belongs where a pipeline is resolved — the stage
contracts are already declared (`weft_cli.compile.contracts_for` reads them), so a router whose
first stage cannot accept a `Query` is refusable at assembly with both stage names in the message,
beside the `needs_store` check `hybrid` already gets. The *rule* belongs wherever `L8.6` landed:
one paragraph asking, of any task that turns a constant into a choice, which constraints the old
constant satisfied by construction and which of those now need a refusal written for them.

### L8.15 — the queue's own depth was a number nobody had counted, and I added to it

**What happened.** `docs/README.md`'s Status block said the lessons queue "stands at ten". Writing
task 8.8's own Status update I added my three new entries and wrote **thirteen**, arithmetic on a
number I had not checked. The real depth, counted with `awk` over the `## Queue` section, is
**23** — fourteen `L8.x` and **nine `L7.x`**. So the published count was wrong before I touched it
and wronger after, and the error is mine in exactly the way this repository's own standing rule
names: *"Measure before asserting, and re-measure before arguing from a number a phase could have
changed."* I argued from it without doing either.

The nine `L7.x` entries are the more serious half. `implement-ll`'s own contract is that a queue is
*"drained completely or the entries are declined with a reason; nothing is carried to a second
phase close"* — and nine entries have done exactly that, silently, because the only thing that ever
stated the depth was a hand-written number in a document rather than a count of the file.

**Generalises to.** *A count of something the repository holds does not belong in prose that a
human updates — it belongs to whatever can count it, or it is stated as a pointer instead.* A
written count has two failure modes at once: it goes stale on its own, and it invites the next
person to do arithmetic on it rather than to look. `L6.18` already routed this exact rule into
`implement-ll` → *Finishing* ("corrects whatever states the queue's depth, and prefers a pointer
to a count"), and it did not bite here — which is `L6.8`'s test failing: a rule that is re-learned
is in the wrong artefact. The drain is not the only writer of that number; **`phase-step`'s own
Status edit is**, and it has no such instruction.

**Candidate home.** `.claude/hooks/lessons_context.py` already computes the queue depth for its
`SessionStart` injection, so the count exists in code and the document is a second, hand-maintained
copy of it — the two-sources shape `docs/README.md` itself opens by describing. Either the Status
block stops carrying a number (a pointer to `docs/lessons.md`, per `L6.18`) or `next_task.py`'s
`live_checks` grows an assertion that whatever number the Status block *does* carry equals the
counted one, the same way it already refuses a stale phase name. The nine carried `L7.x` entries
are a separate finding for the drain itself, not for this entry.

### L8.14 — a shipped document told operators to run a command that does not exist, in two ways

**What happened.** `weft_index/pipelines/index-text.yaml`'s own comment tells an operator how to
use a real embedder: *"`weft pipeline derive index-text --set embed.use=openai` is that edit."*
Run from outside the repository against the installed wheel, that command fails twice over.
`weft pipeline derive` takes `parent name` and **no `--set` flag at all** — argparse refuses it as
an unrecognised argument. And the edit it describes is impossible even written correctly: `openai`
is registered under both `Embedder` and `LLMProvider`, and `02` §2's bare-name rule means a
document naming it is refused — *"stage 'embed' names plugin 'openai', which is registered under
more than one contract... there is nothing here that says which was meant."* So the
`weft-openai` embedder cannot be placed by **any** pipeline document, and the one document that
explains how to place it is wrong about the grammar and wrong about the outcome.

Found while building task 8.8's outside-the-repository demonstration — not by any test. The tree
has a check that shipped *manual* samples resolve (`tests/docs/`), and none that a command quoted
inside a **pipeline document's comment** was ever run.

**Generalises to.** *A remedy written in a comment is a promise the gate does not check — an
invocation quoted anywhere that ships is either executed by a test or it is folklore.* And the
sharper half: a plugin registered under two contracts under one bare name is unreachable from
every pipeline document, which makes "registered and listed" a claim the ladder cannot cash —
`01` item 11's own shape, one contract short of being visible.

**Candidate home.** The executed-sample mechanism `tests/docs/` already has, widened from
`manual/*.md` to the comments inside shipped `pipelines/*.yaml` — the same "an invocation that
ships is executed" rule, applied to the files that carry the most operator-facing advice per line.
The ambiguity half is a separate finding and probably a ledger task, not a check: it is about what
`weft-openai` registers, not about who checked it.

### L8.13 — the pinned model was copied rather than imported, and carries no date

**What happened.** `weft_openai.llm.DEFAULT_MODEL` is `"gpt-4o-mini"`, a model two generations
stale. Two things made that invisible and would have made repointing it incomplete. First, the
constant has **copies**: `tests/integration/test_hypothetical_questions_pipeline.py:218` and
`test_raptor_pipeline.py:223` each hardcode `model="gpt-4o-mini"` in a `RoleMapping` fed to the
real provider rather than importing `DEFAULT_MODEL` — so both would have gone on placing live,
billable calls against the old model after the constant moved, and `test_openai_llm.py`, which
imports it correctly, would have been the only one that followed. Second, the constant carries
**no date**, while its own neighbour does: `weft_eval.pricing.RATES_AS_OF` exists precisely
because a rate table goes stale and says when it was last checked. The model pin is the same kind
of fact and admits nothing.

**Generalises to.** *A pinned fact about the outside world needs two things a pinned fact about
this tree does not: exactly one in-tree copy, and a date. Without the first, repointing it is
silently partial; without the second, nothing in the repository can ever tell you it is stale —
only somebody noticing.*

**Candidate home.** Two halves, and they may route apart. The copies are a check —
`tests/architecture/` already proves "no second copy of X" for several things, and a rule that no
test may name a provider model literal that a shipped constant also names is mechanical. The date
is `pricing.py`'s own pattern applied one module over, plus whatever `implement-ll` decides should
fail when a dated fact ages past a stated interval.

### L8.12 — a brief made a class join a marked family and named nothing that is keyed on the family

**What happened.** Task 8.8's implementer brief specified `NoBaselineRunsError(WeftError,
UnresolvedNameError)` verbatim, down to the `__init__` signature. `UnresolvedNameError` is not an
ordinary base class — it is a **marker**, and two other sites are keyed on membership of it. The
brief named neither. `tests/architecture/test_ff12_unresolvable_name_carries_options.py:80`'s
`NAME_RESOLUTION_FAMILY` is a pinned frozenset of every qualname carrying the marker, guarded in
both directions, so the new class failed the build the moment it existed; and
`weft_cli/exit_codes.py:128`'s local-import branch is what turns that family into exit code 4, so
without an entry the new refusal would have exited `1` — "something failed" instead of "fix what
you typed" — with no test anywhere noticing. **A third site turned up only when the full gate
ran**: `tests/docs/test_troubleshooting_coverage.py` requires every `WeftError` subclass in the
tree to have a `manual/troubleshooting.md` entry, so *both* new error classes failed it. Three
sites keyed on one act, none of them reachable from the new code, and none of them in the brief.

**A fourth instance, in a different task and the same shape.** Task 8.14's brief said *"Remove the
`openai:gpt-4o-mini` entry"* from `weft_eval.pricing.DEFAULT_RATES` — correct, and again written
without searching for what keyed on it.
`tests/unit/weft_eval/test_pricing.py::test_a_call_with_no_rate_entry_is_excluded_and_counted_never_priced_at_zero`
uses that key as its *priced* half against a deliberately-absent model as its unpriced half, so
removing the entry made the test assert `priced_calls == 1` against `0`. The implementer left it
red and said so rather than editing a test it may not touch, which is the protocol working — but
the search that would have found it takes one grep and belongs in the brief, not in the return. The implementer found both, could edit neither
(`NAME_RESOLUTION_FAMILY` lives inside a test file), and correctly returned them rather than
guessing. Both were one line. Neither was in *Already decided*, so the dispatch could not have
succeeded whatever the agent did.

**Generalises to.** *Adding an error class is an edit to every site keyed on error classes —
the ratchet pinning the family, the dispatcher switching on it, and the coverage check over all of
them — and none of those is reachable from the new code, so only a grep for the base class finds
them.* Four sites now, across two unrelated tasks, found one at a time by four different
mechanisms — the implementer twice, my own review, and the full gate — when one grep before
writing each brief would have found them all. The rule is not "remember the ratchets"; it is
**every brief that mandates removing or re-typing a named thing carries the grep for that name as
part of writing it**. A marker exists precisely so other code can switch on it; the count of
those switches is a search result, never a memory. This is `L5.14`/`L6.11` one level in: the earlier
form says a brief's list of affected sites must come from a search, and this is the case where the
brief's author does not even realise a list is owed, because the "site" is a frozenset in a test and
a branch in an unrelated module rather than anything the new code imports.

**Candidate home.** `phase-step` → *Red*, beside the existing "before listing what a task touches,
look up who quotes it" paragraph — which already makes exactly this argument for documentation
samples and would cover markers with one clause. The mechanical version is stronger and belongs
with it: **when a brief names a base class, grep for that base class before writing *Already
decided*.** A check that fails the *brief* rather than the diff is also conceivable — a ratchet
whose membership list names its own dependents — but that is `implement-ll`'s call, not this
entry's.

### L8.11 — the rung only failed on the branch that rarely runs, and two defects hid behind one

**What happened.** `corrective-retrieve` shipped in task 8.1, passed fitness functions 11 and 16,
resolved cleanly under `weft pipeline show`, and answered questions. It was broken twice over, and
**neither defect could fire until the corrective branch itself did** — which happens only when
grading leaves fewer hits than `trigger_kept_below`. Against the deterministic test provider that
never happened, so the rung looked fine for its whole life.

The first defect was a config the plugin would refuse: `multi-arm` requires **at least two** arms
and the document supplied one. The second only became visible once the first was fixed: a corrective
action that fires returns *two* ranked lists, and the inherited `single-list` is the identity fuser,
which refuses two by name. **The first defect masked the second**, so the first fix looked like it
had failed rather than progressed.

**Generalises to.** *A conditional branch is untested until something makes the condition true, and
a document whose rare branch is wrong is indistinguishable from a correct one on every ordinary
run.* The concrete form for this project: **any pipeline stage that conditionally produces a
different number of ranked lists changes what its fuser must be**, and the rung has to be exercised
on the branch that produces the larger number. `iterative-retrieval` and `refine-on-uncertainty`
have the same shape and should be checked on their looping branch too.

**Candidate home.** Not a fitness function — resolution cannot know how many lists a retriever will
return at run time, which is precisely why `single-list` refuses at run time instead. It belongs in
`phase-step` → *Finish* item 4, beside "including a failure path": **run the branch that is
conditional, not only the path that is default**, and for a rung that means constructing the
condition rather than hoping a question triggers it.

---

### L8.10 — the check passed because it was not yet part of its own subject

**What happened.** Fitness function 17 walks **tracked** files, enumerated from `git ls-files`. Its
own test fixtures necessarily contain the shapes it refuses — a citation of a file that does not
exist, and a citation naming its own filename. It passed six-for-six and the full gate ran green
(1,955 tests). The gate run happened *before* `git add`, so the file was untracked, so it was not
in `git ls-files`, so **the check excluded itself from its own population**. The moment it was
committed it failed on its own fixtures. Nothing between those two states changed except
membership.

**Generalises to.** *A check whose population is defined by a repository predicate — tracked,
staged, published, installed — does not include itself until it satisfies that predicate, so its
first green is meaningless. Run it once more after committing, or arrange for it to be in its own
subject before you believe it.* The near-miss version is worse than the miss: had the fixtures
happened not to trip it, the check would have shipped with a permanent blind spot at its own file
and nobody would have had a reason to look.

**And a second, sharper form of the same thing:** the fix is not to exclude the check's own file —
that is the carve-out that makes the blind spot permanent and deliberate. It is to build the
fixtures from parts so the literal never appears, leaving the file genuinely inside its own
subject. **A check that cannot survive being pointed at itself is not finished.**

**Candidate home.** `phase-step` → *Finish* item 3 already requires watching a new check fail on a
planted case. This adds a clause with teeth: **run the new check once after `git add`**, because
until then it may not be looking at itself. Cheap, mechanical, and it generalises to every
`git ls-files`-derived check this project has.

---

### L8.9 — the citation named this very file, and described a different one

**What happened.** While removing citations that pointed into another codebase, three were found
that pointed *at a filename this repository also has*. `weft_clean/unicode_normalizer.py` carried
**"Verified at source: `unicode_normalizer.py:12-37`'s `process` calls…"** — inside
`unicode_normalizer.py`. There is no `process` method in this file and never was: the citation was
quoting the other project's file of the same name, and read for three phases as an ordinary
self-reference. `weft_clean/property.py:27` and `weft_retrieve/iterative.py` carried the same shape.
The words *"verified at source"* were attached to a claim that was not true of the source they
appeared to name.

**Why nothing caught it.** Every check that could have run passes: the path exists, the file is
real, the line range is in range, and no word-search for the other project's name matches — the
citation is bare. It survives a "does this path resolve?" check precisely *because* the basename
collides, which makes it the one form of dangling citation that a path-existence check is
structurally blind to.

**Generalises to.** *A citation's basename matching a real local file is not evidence that it refers
to that file — and a **self**-citation is the case to distrust most, because it is the one every
mechanical check waves through.* Where a comment says "verified at source", the thing to verify is
that the source says it, not that the source exists.

**Candidate home.** Refines the fitness function `L8.8` and `L8.7` both route to. "Every `path:line`
citation resolves to a path that exists" would have passed all three of these. The check needs a
second clause with teeth: **a citation naming the file it appears in must be justified**, because a
module citing itself by name and line is either redundant (it is describing code the reader is
already looking at) or wrong (it is describing somebody else's file). Both are worth a failure.
Cheap to implement — the citation and the containing filename are both in hand at the same moment.

---

### L8.8 — the sweep was scoped by a grep, and inherited that grep's blind spot

**What happened.** Asked to remove every reference to another codebase from this repository, the
scope was measured with a grep requiring a two-segment path fragment, when the question was the
bare word that fragment starts with. Reported footprint for shipped source: **13
sites in 9 files**. Actual: **277 sites in 89 files**, a 20× undercount, and the number was then
used to size the whole plan, to write three agent briefs, and to tell the project's owner what the
work involved. A dispatched agent found it, not a check — its `## Noticed` asked whether the file
list was "a deliberate narrow first pass or an undercount".

The same agent found a class **no word-search could ever reach**: `weft_llm/loop_guard.py` carries
~15 line-citations naming a module that **exists nowhere in
this repository**. They were dangling pointers into a tree the reader does not have — the exact
defect the sweep existed to remove — and they contain no matchable word at all.

**Generalises to.** *A search term is a hypothesis about the answer, and a scope measured with one
grep inherits that grep's blind spot for the whole task. Before sizing work from a pattern, run the
widest plausible pattern too and compare the counts — a 20× gap between a word and a path fragment
beginning with that word is visible in one extra command and invisible in none.* And the sharper half: **the durable check is
not a better search, it is the property.** "No occurrence of this word" cannot see a dangling
`file.py:NNN`; "no tracked file cites a path that does not exist in this repository" catches both,
and catches the next form nobody has thought of.

**It happened three times in one session, and the third instance is the one that settles the
argument.** (1) The scope grep required a two-segment path fragment when the question was the bare
word: 13 sites reported, 277 actual. (2) The cleanup was then scoped by three *directory* names,
missing `.claude/`, `.github/`, `eval/`, `scripts/`, the dotfiles and seven `NOTICE` files — a
population only `git ls-files` could have enumerated. (3) Every grep in the whole exercise was
**case-sensitive**, so six bold worked-example headings in a skill file — the same word, capitalised
— were invisible to all of them until an agent working from a different angle reported them. Each miss was found by an agent or by the
project's owner; none was found by the person doing the searching, because a search cannot report
what its own pattern excludes. **Three misses, three different mechanisms — narrowness, scope, case
— and one shape: the searcher grading their own search.**

**Convergent evidence, worth stating because it is unusual.** Three agents working on disjoint
parts of this sweep, unable to see each other's findings, each independently reported the same gap
and each proposed the same remedy: make it a check on the property rather than a better search. A
recommendation reached three times from three different slices of the tree is not a preference.

**Candidate home.** A **fitness function** — every `path:line` citation in a tracked file resolves to
a path that exists in the tree, waiver pinned empty. It attaches to no new seam (it is a sweep over
tracked files, like FF16's), it subsumes the word-search this task actually needed, and it is the
answer to `L8.7` as well. Secondarily `phase-step` → *Orient*, which already says a list in a
document is where to start looking rather than a census (`L5.14`) — this is that rule applied to a
**grep**, which is the form it keeps coming back in.

---

### L8.7 — an arrangement that was safe while the repository was private, and nobody scheduled its end

**What happened.** This project was built while reading a sibling codebase for reference, and the
practice of citing that reading — `path:line`, measure-before-asserting — was written into
`CLAUDE.md` as a rule and followed diligently for eight phases. The result, counted on the day it
was finally questioned: **hundreds of citations across `packages/`, `tests/` and `docs/`, including
13 inside shipped wheels**, pointing at paths that resolve only through one developer's untracked
symlink. A stranger who installs `weft-rag` reads them. Nobody noticed because every individual
citation looked like diligence — it *was* diligence — and the rule that demanded the evidence is the
same rule that spread it. Raised by the project's owner, in anger, and correctly.

It was cheap to detect at any point — one `git ls-files | grep` for the name, at any moment in
eight phases — and nothing ever ran it.

**Generalises to.** *An arrangement that is safe while a project is private becomes a liability the
moment it ships, and its cleanup has to be scheduled when the arrangement is adopted — not when
somebody notices. A convention that produces a growing number of references to anything outside the
repository needs a stated end condition at the moment it is written down, because by the time it is
obviously wrong there are hundreds of them and removing them requires rewriting history.*

**Candidate home.** The same fitness function `L8.8` proposes — the two are one subject and should
be drained together. Beyond the check, `CLAUDE.md`'s own standing rules are where a convention with
a growing footprint should have to state what ends it: a rule that accumulates artefacts is not
finished until it says when it stops.

---

### L8.6 — the repair made a dormant restriction reachable, and I reviewed the repair without re-reading the restriction

**What happened.** Task 8.3 turned the router's name from a constant into `[services] route`, so an
operator can now select a router. `weft_cli.route_ask.run_routed_ask` searches `load_contributed`
— packs only — which is Phase 2's settled behaviour and which 8.3 deliberately did not reopen. The
consequence, measured under `weft-qualities` and not before: a project-local
`pipelines/my-router.yaml` resolves under `weft pipeline show` and runs under
`weft ask --pipeline`, and `[services] route = "my-router"` refuses it. I had read the restriction,
quoted it in three docstrings as *"Phase 2's settled behaviour, not reopened here"*, and never asked
what the *new* key did to it: while nobody could substitute the router at all the restriction was
invisible; the moment a key invites you to name one, half the ways of having one silently do not
count.

**Generalises to.** *Making something configurable does not preserve the restrictions around it —
it exposes them. When a change turns a constant into a choice, re-read every rule that scoped the
constant and ask what it now means to somebody exercising the choice, because a rule that was
unobservable is not the same rule once it can be hit.* Citing a restriction as unchanged is not the
same as checking it is still right.

**Candidate home.** `weft-qualities` lens 1's producing/consuming paragraph, which already asks
*"can a stranger reach both sides?"* and would have caught this if it also asked *which* stranger —
this seam is whole for a pack author and half-built for a project author, and the lens has no prompt
to try both. Possibly also `phase-step` → *Orient*, beside "read the population, not the
declaration": when a change makes a value configurable, the population to re-read is the rules that
assumed it was fixed.

---

### L8.5 — seven documented configuration surfaces, none of which had ever worked

**What happened.** `corrective`, `iterative-retrieval` and `refine-on-uncertainty` each resolve a
sibling plugin by name through `StageLookup` and each publishes `*_config` fields — seven between
them (`primary_config`, `grader_config`, `knowledge_action_config`, `leaf_config`,
`sufficiency_config`, `retriever_config`, `signal_config`), every one typed
`Mapping[str, object] | None` and documented in its own docstring as *the* way a pipeline document
retunes that sibling. `RegistryStageLookup.build` passed the mapping straight to `entry.factory`,
so the sibling was built with a raw `dict` where its config object belonged and died later inside
its own `run`: `'dict' object has no attribute 'channels'`. Requirement 6 — *"every piece of it is
parameterisable"* — was false at all seven, `10` §1.1 describes several of them as if they worked,
and the whole suite was green, because **every test that drove these plugins left the sibling's
config at `None`**. Found by running `weft ask --pipeline corrective-retrieve`, the first caller in
the tree's history to set one. `tests/unit/weft_retrieve/test_engine.py`'s own `_echo_factory` had
been written as `_Echo(config if isinstance(config, _EchoConfig) else None)` since the file was
created — the defect's own workaround, sitting in the test that was supposed to prove the seam.

**Generalises to.** *An optional parameter that every test leaves unset is an untested parameter,
and a test helper that defensively narrows a type the production caller does not narrow is a
recorded sighting of the bug.* The general move: where a field is documented as the way to
configure something, at least one test must actually set it — and an `isinstance` guard in a test
double is a question to ask, not a convenience to write.

**Candidate home.** Grouped with `L8.4` (both are "the gate agrees with itself and not with the
artefact"). Two candidate mechanisms: a check that every `Mapping[str, object]`-typed config field
on a registered plugin is set by at least one test or one shipped document — the ladder makes the
second half cheap now — and a note in `phase-step` → *Red*, beside the existing "assert the fact a
field means", that a defensive `isinstance` in a test double is evidence about production.

---

### L8.4 — two static checks agreed, and the binary said the feature had never run

**What happened.** Phase 8 shipped `index-with-raptor` and `index-with-questions`, the first
documents ever to place `raptor` and `hypothetical-questions` — tasks 2.31 and 2.32, shipped in
Phase 2. Both documents pass fitness function 11(b) (every shipped pipeline resolves) and fitness
function 16 (every registered pipeline position is placed). Running them from `/private/tmp` against
the real container: `no service is registered for Embedder on this run` and the same sentence for
`Prompts`. Both plugins reach an ambient service through `ctx.require`; `weft_cli.run_services.
build_services` builds those for the **query** path and `weft_cli.ingest.run_index` builds none at
all. So two index-path techniques have **never been runnable through the CLI** in the one place they
belong, for two phases, with every gate green — their exit demonstrations were unit tests handing
the context in directly.

**Generalises to.** *A contract's plugins are only proven runnable where a **driver** assembles what
they require — so a new contract's first task must name its driver, and a plugin whose only
execution evidence is a test that constructs its own `Context` has not been shown to run in
production at all.* Resolution proves a name binds; it says nothing about what the run will provide.

**Candidate home.** `phase-step` → *Finish* item 4 already requires running the binary and this
slipped past because the plugin had no shipped document to run it *through* — so the sharper
placement may be a check: every contract with a registered plugin has a driver that builds the
services those plugins `ctx.require`. Possibly a clause of fitness function 5 (*every declared
capability resolves*), which is the nearest existing neighbour and today asks a weaker question.

---

### L8.3 — the manual named two of three keys, and the whole gate was green

**What happened.** Task 8.3 added `route` to `[services]`. `manual/troubleshooting.md:1007-1028`
carried a worked transcript of the unknown-key refusal printing `accepts embed, store`, plus
`(exc.valid_options == ("embed", "store"))` and the sentence *"the only two keys `[services]`
reads"* — all three stale the moment the field landed, and `ci-checks` stayed green through the full
1,929-test run. The block is quoted prose, not a tagged executed sample, so nothing compares it to
anything. `L6.19` already says exactly this and is marked **Applied**; it did not bite, because what
was applied was a rule about writing new transcripts rather than a mechanism that finds the existing
ones a change falsifies.

**Generalises to.** *`L6.8` with a fresh instance — a rule that is re-learned did not bite, so it is
in the wrong artefact.* The specific move: a change to a typed surface an operator configures
(`ServiceSelection`, `LLMRoles`, a `valid_options` tuple) must be answerable by a **lookup** of
which pages quote that surface, the way `tests/docs/test_pack_guide_samples.py` already makes
"which guides quote this file" a lookup rather than a recollection — never by remembering to grep.

**Candidate home.** Extend the pack-guide sample index to `[services]`/`[llm.roles]` key lists, so a
manual page naming a key set is checked against the model the way a quoted file already is. Grouped
with `L8.4` under *the gate agrees with itself and not with the artefact*.

---

### L8.2 — a waiver reason that was true, and still the wrong answer

**What happened.** Writing fitness function 16, two registered `RoutingPolicy` plugins
(`threshold-ladder`, `always`) turned out to be placeable by no document anybody could ship: the
router's name was a constant in `weft_cli.route_ask`, a pack cannot contribute a second document
under a held name, and a project shipping its own `route.yaml` is refused by `full_catalogue` —
which does not merely lose the override, it fails every `weft pipeline` command. That is a true,
checked fact about what can be run, which is precisely the standard the new waiver's own docstring
sets, so the entry was drafted and would have passed review. The repair — `[services] route`,
resolved like `embed` and `store` — is four lines and one call site, and it turned the fact into a
former fact. What stopped the waiver was a `PreToolUse` guard firing on a waiver-shaped collection
gaining an entry, and a standing user preference for the strongest technical option; neither was the
check itself.

**Generalises to.** *A waiver reason must be a fact about the artefact — that is necessary and not
sufficient. The question after establishing it is whether the fact should hold, and a fact that a
short repair would remove is a defect wearing a waiver's clothes.*

**Candidate home.** `weft-qualities`, which reviews for exactly this class and would have asked
requirement 4's question of a registered plugin nothing can place. Possibly also the waiver
convention itself (`08` §3): a waiver entry states its fact **and** what would have to change for
the fact to stop holding, so the reader after next can price the repair instead of re-deriving it.

---

### L8.1 — `--check-live` compared two phase names by substring and reported agreement

**What happened.** `next_task.py`'s live check asserts the Status block's phase and the first
unticked task's phase are the same, via
`task.phase.split("—")[0].strip() not in stated` — a **substring** test over a prose table cell.
Phase 8 is the project's first phase that deliberately runs out of ledger order (no gate; Phase 7 is
blocked by G12), so `docs/README.md`'s Phase cell now reads *"Phase 8 … It runs before **Phase 7**,
which G12 still gates"* while the first unticked box is `7.1`. The two genuinely disagree, the cell
contains the string `Phase 7` because explaining the ordering requires naming it, and the check
printed *"live check ok — its phase agrees with 7.1"*. Its **premise** is also now false: the two
phases can legitimately differ, which is what the Next action row exists to carry.

**Generalises to.** *A containment test between a prose field and an identifier reports agreement
whenever the prose mentions the identifier for any reason — including to say it does **not** apply;
and a check whose premise is "these two must name the same thing" needs re-argued the first time the
project makes them legitimately differ, rather than loosened until it passes.*

**Candidate home.** `.claude/skills/phase-step/scripts/next_task.py` → `live_checks`. The repair is
two things, not one: compare the Status cell's **first** phase identifier for equality rather than
containment, and replace the premise — the real invariant is *the Next action row names a task that
exists in the ledger*, which holds whether or not the phases match, and which nothing checks today.
Sits beside `L6.3` and `L6.4`, both of which are this same script.

---

### L7.9 — the precondition was written down, in this repository, and not checked before acting

**What happened.** `v2.1.0` was tagged and every publish job was refused with
`429 Too many new projects created`. Nothing reached PyPI; `weft-rag` never ran, because its job
needs the five before it.

The precondition was already written, twice, by this repository: `L7.3` — *"the limiter counts
**attempts** over a rolling window rather than successes"* — and the task brief's own
*"no retry against PyPI until its window has been left alone for hours"*. What was reasoned about
before tagging was the **size** of the burst (six serialised creations instead of nineteen
parallel), which is a different variable from the one the limiter actually counts. The window was
still carrying roughly a hundred attempts fired earlier the same day.

**The measurement, since nobody had one.** The saturating run was `08:53Z`; this one was `13:04Z`
and was refused on its *first* request. So the window outlasts **four hours** at that volume —
"hours" was the guess, and it is at least that and possibly much longer.

**Generalises to.** When a rule names a cooling-off period, the check before acting is *how long
since the last attempt*, not *how much smaller this attempt is* — a rate limiter that counts
attempts is unaffected by making the next one smaller.

**Candidate home.** `.github/workflows/release.yml` — **built the same day**, before the drain: a
`cooling-off` job that every publish job needs, refusing when the previous Release run failed less
than twelve hours ago and naming the recovery, with a `workflow_dispatch` `force` override for the
case where PyPI has granted an exception. Built rather than queued because the rule had already
failed twice as prose and the third failure would have been a published version number. What is
still open for the drain is whether the same shape belongs anywhere else — `L7.3` and this entry
drain together.

**Found while building it, and worth as much as the entry above.** The workflow could not be
re-run after a partial failure at all: `v0.1.0` published four of twenty, so a full re-run would
have failed on `File already exists` for exactly the four that *succeeded*. `uv publish
--check-url` makes an upload idempotent and is now on both publish steps. A release job that
cannot be re-run turns every partial failure into hand-work, which is how the seven-attempt retry
loop L7.3 records became the only visible option.

### L7.8 — the gate I ran and the gate CI runs were not the same gate

**What happened.** The consolidation was declared done on a green `poe ci-checks`: 1,867 passed,
**93 skipped**. CI ran the same task and got 1,917 passed, **42 skipped**, and failed on
`tests/docs/test_quickstart.py:156` — a pattern anchored on `^weft-store\b[^:]*: active` against
`weft plugins doctor` output that now reads `store (weft-rag) 2.1.0: active`. Fifty-one tests need
the `compose.yaml` container and skip without it. I had brought the container up mid-task to drive
the shipped binary end to end, then run `docker compose down -v` to tidy up, and every gate run
after that silently covered fifty-one fewer tests than CI's.

The skip count was printed on every one of those runs and read past. It is the only signal that the
two gates differ, and `CLAUDE.md`'s "a green gate is not a working binary" does not cover this
case — the binary *was* run, and correctly; what was not run was a fifth of the suite.

The assertion itself had been broken the same way once before: task 6.4 put the installed version
between the name and the status, and the comment above the line already says *"the fact is
'weft-store is reported active', never the literal line"* — then anchors on `weft-store`, which is
the literal line one field further left.

**Generalises to.** A skip count is a coverage number: when a suite's skips depend on an external
service, the gate is not green until it has been run with that service up, and the count is what
says whether it was.

**Candidate home.** `CLAUDE.md` → *Quality gates* (`ci-checks` is only the canonical gate with the
container running), or a `poe` task that refuses to report success when a container-dependent suite
skipped — the number is already there, nothing reads it.

### L7.7 — a derivation that agrees with the tree until the tree changes shape

**What happened.** Five separate files derived a distribution's import package as
`project.name.replace("-", "_")` — `tests/architecture/test_ff12_unresolvable_name_carries_options.py`,
`test_ff12b_a_repack_keeps_valid_options.py`, `tests/docs/test_troubleshooting_coverage.py`,
`scripts/publish_set.py` and `tests/architecture/test_isolated_installs.py`. It was correct while
every distribution shipped exactly one package named after itself. `weft-rag` ships fourteen and is
named after none of them, so the derivation produced `weft_rag`, a module that does not exist. Three
of the five failed loudly. **`scripts/publish_set.py` did not**: `check_isolated_installs.py` builds
a probe from `member.module`, so it would have installed the bundle alone and imported nothing while
printing success — fitness function 1's generalisation passing by importing zero modules. It was
caught because a *different* test asserted the module was a directory on disk.

Four of the five carried a docstring explaining that the computation was deliberately **restated
rather than imported** across test modules ("one self-contained scenario"). That convention is what
turned one wrong line into a five-file repair, and it is worth knowing that is its price.

**Generalises to.** A structural derivation (`name` → path, `name` → module, one-of-X-per-Y) is an
assumption about the tree's shape, not a fact about a name — read the shape instead, and where the
derivation must be duplicated, duplicate a call rather than a rule.

**Candidate home.** `tests/architecture/conftest.py` now holds `first_party_source_roots()`; the
open question is whether the four restated copies should call it, which means deciding what the
"restate rather than import" convention is actually protecting.

### L7.6 — the plan named a mechanism that does not work where it is needed

**What happened.** The brief for deriving `weft --version`'s own distribution named
`importlib.metadata.packages_distributions()`, and it is the obvious answer. Run in this
repository's own venv it returns `None` for `weft_cli`: it maps import packages to distributions by
reading installed **file records**, and an editable install records only a `.pth`. The first
implementation was written, and the failure surfaced as a test asserting exit 0 and getting 1 — not
as anything the API's documentation would have suggested. The working derivation is the
`console_scripts` entry point pointing at `weft_cli.cli`, which is written for an editable install
and a wheel alike, and is also a better answer: it reports the version of the thing that actually
put `weft` on the reader's PATH.

**Generalises to.** Before building on a packaging or metadata API, run it in the environment the
code will actually run in — a dev checkout is an environment, and editable installs are where
metadata APIs most often answer differently.

**Candidate home.** `CLAUDE.md` → *Quality gates*, beside "a green gate is not a working binary";
this is the same rule one layer down, aimed at an API rather than at a command.

### L7.5 — the guide recorded a gap that had been closed for two weeks

**What happened.** `manual/pack-author-guide.md` §9.3 carried a paragraph headed "Honest gap, not a
pattern to copy", stating that every `examples/*/pyproject.toml` declared its `weft-*` dependencies
as bare names, with a worked example and a note that closing it was "one short follow-up task".
Ledger task **6.26** closed it, added `tests/architecture/test_example_packs_are_exemplars.py` to
keep it closed, and left the paragraph standing — so the guide went on telling pack authors that
the tree's own examples taught the wrong thing, while a fitness function enforced the right one.
Found only because this task happened to be editing the surrounding paragraph.

**Generalises to.** A documented gap needs the task that closes it to name the document — a
prose "honest gap" outlives its own repair by default, and no check in this tree can see one.

**Candidate home.** `phase-step` → *Finish*, or a check that every "gap"/"not yet"/"follow-up"
paragraph in `manual/` names a ledger task and fails when that task is ticked.

### L7.4 — a comparison that collapsed twelve rows into one and still passed a type check

**What happened.** Three separate readers indexed reports by distribution name:
`weft_cli.registry_bootstrap.require_active` (`{report.distribution: report}`),
`tests/architecture/test_ff2_no_privileged_builtins.py`'s contribution counter (a dict comprehension
keyed the same way), and `weft_eval.run_record.active_distribution_set` (a sorted list, not a set).
Every one of them was correct while each distribution shipped one pack, and every one of them
silently kept whichever report came last, or repeated a name twelve times, once one distribution
shipped twelve. FF2 was the only one that failed loudly, and only because it compared 102 written
registrations against the 1 the collapsed dict reported. `require_active` would have answered about
an arbitrary pack — the check that stops `weft index` running without an extractor.

**Generalises to.** A dict keyed on a field that is *currently* unique is an unstated uniqueness
assumption; where the key is an identity that may become shared, index on the identity that is
unique by construction and say which one that is.

**Candidate home.** `weft-qualities` — the identity a surface keys on is a design question, not a
coding one, and this is the second time in one task that the answer was "the entry-point name".

### L7.3 — the retry was the thing keeping the door shut

**What happened.** `v0.1.0` published 4 of 20 distributions; PyPI refused the rest with `429 Too
many new projects created`. It was read as a PyPI limitation and put on a 40-minute retry loop.
Seven attempts later the count was still 4. The limiter counts **attempts** over a rolling
window rather than successes, so every rerun of the fifteen failed jobs re-saturated it — on the
order of a hundred creation requests fired to achieve nothing. Retrying was not neutral; it was
the mechanism preventing recovery.

Underneath it, the actual defect was ours: `.github/workflows/release.yml` published a
nineteen-job matrix in parallel, which asks PyPI to create nineteen new projects within seconds.
Serialising (`max-parallel: 1`) removes the burst and costs wall-clock on a job that runs once
per release.

**Why it was invisible.** The flaw exists **only on a first publish**. Every later release
uploads a version to a project that already exists, which is not rate-limited the same way. So
the code was correct in every scenario except the single one it had never been run in — the same
shape as `L7.2` (a CI workflow that had executed zero times) and as the lockfile nothing had
needed until a clean checkout needed it. Three findings in one day, all of them a path taken for
the first time in production.

**Generalises to.** Two rules, and they are separable. *A retry against a rate limiter is only
safe when the limiter counts outcomes; when it counts attempts, retrying moves recovery further
away* — so before automating a retry, establish which kind of limiter it is, and treat "the
count did not move" as evidence of the attempt-counting kind rather than of bad luck. And: *a
burst is a design decision, not a scheduling detail* — fan-out against a shared external quota
needs a stated concurrency bound at the point the fan-out is written, not after the first refusal.

**Candidate home.** The retry half is the sharper one and has no natural artefact yet: it is not
a fitness function (nothing in the tree can test PyPI) and not `CLAUDE.md`'s gate section. It may
belong wherever this project writes about acting on external services — `ADAM_TODO.md` is where
the release obligations live, and `09-release.md` §5.2 owns the publish path. The burst half is
narrower and already fixed at the site; what would generalise is a rule that any matrix or
`gather` against a third-party service names its bound in the same diff that creates it — which
would also have caught `weft_index.raptor`'s unbounded `asyncio.gather`, found the same day by a
different route. That coincidence is the argument for one rule rather than two.

### L7.2 — the gate had never run anywhere but one laptop, and nobody could have noticed

**What happened.** The first CI run this repository has ever had failed three of its four jobs at
their first step: `error: Unable to find lockfile at uv.lock, but --frozen was provided`.
`.gitignore:17` listed `uv.lock` under `# Tooling`, between `.ruff_cache/` and `.pyright/`, and it
had never been committed in seventy commits. `ci.yml` runs `uv sync --frozen` in `gate` and
`sdists`, and `isolated-installs` needs a populated environment to import pydantic; only
`kernel-isolation` survived, because its script imports nothing outside the standard library.

**Why it was undiscoverable.** There was no git remote until 2026-09-05. `ci.yml` was written in
Phase 0, has been cited and maintained since, and had **executed zero times**. Meanwhile
`poe ci-checks` was green on every run — because a developer's `.venv` and their untracked
`uv.lock` were both already sitting there. The gate passed by a path CI does not have, and the two
paths could not be compared while only one of them was ever taken. `uv lock --check` resolves 145
packages unchanged, so nothing had drifted: the resolution was correct and merely unshared.

This is `01`'s own rule one level out. *A green gate is not a working binary* was learned about a
binary nobody ran; this is a gate nobody ran **elsewhere**. A CI workflow that has never executed is
prose in exactly the sense `L6.12` means it — a directory of tests no task runs — except that it
looks more like a check than prose does, because it is written in YAML and lives where CI would find
it.

**Generalises to.** *A workflow that has never executed is a claim, not a check — and an artefact
whose absence only breaks a path nobody takes is invisible until someone takes it.* Anything the
gate needs must be in the repository, not in the environment of whoever last ran the gate; the test
is whether a clean checkout on a machine that has never seen this project can run it.

**Candidate home.** Two candidates, and they answer different halves. A fitness function could
assert that everything `ci.yml` and `release.yml` reference exists as a tracked file — cheap,
runs locally, would have caught exactly this. `CLAUDE.md` → *Quality gates* is the other: it already
says a green gate is not a working binary and could say that a gate that has run in one environment
is not a gate. The deeper point may belong wherever a phase declares itself complete — Phase 0's
exit was ticked with its CI never having run once, and no check asked.

### L7.1 — a task filed with its remedy already chosen had chosen the wrong one

**What happened.** Phase 6's close filed **6.33** from a diagnosis made in the moment: FF8's canary
assertion was failing under `pytest tests/docs tests/architecture`, a bisect named five `tests/docs`
modules that import the canary through `discover_for_reference()`, and the task was written as
*"stop them"* — with the remedy named, and even a shortlist of candidate seams. Doing it did not
work. Four of the five could be pointed at a restricted helper; the fifth was
`tests/unit/weft_cli/test_contract_reference.py`, which calls the open function five times and
**cannot stop**, because testing that function is what those tests are for.

There was never a set of callers to discipline. Any session that tests open discovery imports the
canary, so an in-process `sys.modules` guard could not survive — and the real repair was to the
*mechanism*: run the probe in a fresh interpreter, which FF8's own docstring had already argued for
in the sibling test beside it. The filed remedy was not merely incomplete; it was impossible, and
the only way to learn that was to attempt it.

**Why the filing was confident and wrong.** The bisect answered *"which files, run before FF8, make
it fail?"* — a real question with a real answer. It did not answer *"can each of them stop?"*, and
nothing in the failing output distinguished the two. A close-out review is exactly where this is
likely: the diagnosis is made with the evidence in hand and the fix is written from the same glance.

**Generalises to.** *A ledger task states the property that must hold, not the repair that will make
it hold* — a filed remedy is a hypothesis formed before anyone tried it, and it arrives carrying the
authority of the ledger. Where a filing does name a candidate fix, it says so as a candidate and
names what would falsify it.

**Candidate home.** `implement-ll` → *The two traps*, which already says a task written from one
instance narrows to that instance (`L6.13`); this is its sibling — a task written with its cure
prescribed narrows to a cure that may not exist. Possibly also `phase-step` → *Orient*, where a task
is read: a remedy in a task line is the previous author's guess, and the property above it is the
part that binds.

---

*Last drained 2026-08-25 at Phase 6's close — seventeen entries, five subjects, in
`lessons-archive.md` under that date, with their edges and the loop's own check answered: three of
this phase's defects would have been caught by rules already **Applied**, so all three moved to the
step that executes them rather than being restated.*

---


---

# Drained 2026-09-05 — Phase 8's close, second pass

One entry, written and applied within the hour, which is the queue working as intended rather than
a queue being skipped.

| Entry | Disposition |
|---|---|
| `L9.1` | Applied — `pyproject.toml` gains a `cold-lint-cache` task (`ruff clean`) as the first step of `ci-checks`, and `CLAUDE.md` → *Quality gates* gains it as the fourth item on the environment-parity list `L7.2`/`L7.6`/`L7.8` produced an hour earlier. `ci-no-tests` deliberately keeps its cache — that is what makes the fast task and the canonical one mean different things |

## The entry as it stood

### L9.1 — the linter cached a verdict that a *different* file had invalidated

**What happened.** `uv run poe ci-checks` reported green four times across this session's last two
tasks. The tree it was reporting on was not clean: `ruff check .` on the identical commit, after
`ruff clean`, finds two `I001` import-order errors. The gate and the code disagreed, and the gate
was wrong.

The mechanism is a cache whose key is narrower than its answer. Ruff caches a verdict **per file**,
keyed on that file's own content and the configuration — but the verdict for
`tests/unit/weft_cli/test_eval_commands.py` depends on whether `weft_eval.falsify` **exists**,
because first-party/third-party import classification is a fact about the *tree*, not about the
file being linted. The import line was written before `falsify.py` did, so it was cached as
third-party and correct. Creating `falsify.py` made it first-party and the cached answer wrong, and
nothing invalidated it, because the file that changed was not the file whose verdict changed.

**How it was caught, and it was luck.** Not by the gate, which never stopped being green. The
squash onto `main` produced a tree byte-identical to the branch (`git diff branch main` empty) and
the gate failed on it — the same code, a different answer. Chasing *that* contradiction is what
surfaced the cache; had I merged with `--no-ff`, or not re-run the gate after merging, this would
have reached `main` green and stayed there.

**Generalises to.** *A cache keyed on one input cannot be trusted for an answer that depends on
several — and a build tool's cache is a second source of truth about the code, so a green from a
warm cache is evidence about the cache.* The repository-specific form: **the canonical gate is only
canonical from a cold cache**, which is the same sentence as `L7.2`/`L7.6`/`L7.8` — the gate I ran
was not the gate a clean checkout runs — landing for a fourth time, in the artefact those three were
routed into **in this same session**. CI does not have this bug, because CI has no warm cache. That
is exactly why nobody would have found it there either.

**Candidate home.** `CLAUDE.md` → *Quality gates*, where the paragraph those three lessons produced
already sits — it currently names the lockfile, the container and the skip count, and this is a
fourth item on the identical list. The stronger form is mechanical and belongs in `pyproject.toml`:
`ci-checks` is the *canonical* gate and is run rarely, so it can afford to clear the cache first;
`ci-no-tests` is the fast one and should keep it. That makes the distinction between the two tasks
mean something it currently does not.
