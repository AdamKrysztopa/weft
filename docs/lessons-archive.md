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

- **L5.3** *measure before asserting applies to design proposals about this tree, not only to reference
  claims* → `CLAUDE.md` → *Working here* · `a1b2c3d`
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
- **L5.3** *measure before asserting applies to design proposals about this tree, not only to claims about the reference* → declined as a separate rule; the queue's own evidence is that measurement happened every time it was asked for, and `CLAUDE.md` → *Working here* already carries it · `88edcd0`
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
