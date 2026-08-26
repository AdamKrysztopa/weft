# What each rule cost

`SKILL.md` states each rule with the one fact that makes it stick. This file holds the rest of the
account, because the rules in that file are not preferences — every one is the residue of something
that went wrong here, and a rule whose evidence has been lost is the prose that decays.

Read a section when you are about to argue past the rule it belongs to.

---

## Running the binary — Phase 3's four repairs

**All four were found by running `weft` through its shipped entry point. None was found by its 1,513
tests.** That is the whole argument for the step, and the four are worth naming because they are not
exotic:

1. `weft init` refused a first run in an empty project — the one situation the command exists for.
2. A refusal printed twice, the second time mislabelled as a stream error.
3. `weft --help` entered the REPL instead of printing help.
4. A refusal spliced a raw Pydantic dump into the middle of an English sentence.

The third falsified **Phase 3's own Exit criterion**, which is written in terms of `weft --help`.
The test written to prove that criterion passed — it had been shaped around the defect. A suite
cannot catch a defect its author shared.

So: `cd` somewhere that is not this repository, run the command a user would run, and read what it
prints. Run the failure path too — the wrong flag, the missing file, the name nothing provides —
because refusals are where composition bugs and text quality both surface. Paste the real output
into the task's ledger entry. Leave nothing behind; a stray `weft.toml` at the repository root is
the tell that a scaffolding command was run in the wrong directory.

---

## A list in a document is not a census — task 5.2b

A settled document naming *"the five known sites"* was written by someone reading one part of the
tree, and it stops where their reading stopped. Task 5.2b was given five sites by a gate's own
ruling and found **nine**: the four in the sibling backend had never been looked at
(`docs/lessons.md` L5.14). Grep for the thing itself before trusting a count.

The same failure has a second face: read what a check *asserts*, not what its name or its docstring
says it is for (`docs/lessons.md` L5.7). And a property about caller shape needs a structural check
— an AST walk — never a textual one; a name-collision check built as a substring search is unsound
(`docs/lessons.md` L5.23, L5.28).

---

## "Every X" and the seductive proviso — task 5.1a

Settled text said deletion *"fans out across **every** registered plugin that satisfies it"*. Task
5.1a narrowed that to exclude all but the configured store, for a sound reason — and thereby
excluded the one participant the mechanism had been built for. Eleven tasks and **1,801 tests** did
not notice, because the tests written alongside the narrowing assert the narrowing
(`docs/lessons.md` L5.32, L5.25).

Two things follow, and both are in `SKILL.md` as rules:

- A narrowing found mid-task is a **gate to reopen**, written up as an open question. A proviso
  invented mid-task is indistinguishable, afterwards, from a decision that was argued.
- The author of a test must not be the author of the implementation it constrains. This is the
  structural reason the implementer is dispatched rather than the whole task being handed over.

---

## Where a fix goes, and what an empty answer means

**Repair user-facing text at the seam that renders it.** Phase 3 fixed a raw-Pydantic-dump splice at
the raise site where it was noticed. It recurred in Phase 5, one raise site over
(`docs/lessons.md` L5.10). A fix scoped to one call site comes back at the next one.

**An empty collection means "I did not find it", never "it is not there"** — do not phrase one as a
diagnosis until every resolution step that could have produced it has run. And where two layers can
both diagnose a situation, the one that runs **first** must make the check the second one makes, or
the operator reads the weaker answer and acts on it (`docs/lessons.md` L5.9).

---

## Checks that cannot fail

Two shapes pass forever:

- A check whose two sides are derived from **one source** cannot disagree with itself
  (`docs/lessons.md` L5.6). Read the two sides from places that can genuinely conflict.
- A check whose real subject is legitimately **empty** today passes vacuously
  (`docs/lessons.md` L5.19). The floor there is a self-test proving the comparison is not vacuous —
  never an assertion that the real set is non-empty, which would be a different and false claim.

Fitness function 16 enforces the convention. Watching your own check go red against a planted
disagreement is still yours, and this skill's own `scripts/next_task.py --self-test` is an example
of the shape: its fixture plants the exact input the parser exists to reject.

---

## Two smaller ones

**Run the gate in the foreground.** Three agents in Phase 3 stalled mid-task after backgrounding
`ci-checks` and waiting on a notification that the work was structured never to produce.

**Run the whole suite, not the part you touched.** Phase 5 shipped a pack whose default claimed a
process-global slot. It passed its own suite, and each test tree run alone, and failed five things
in the combined run (`docs/lessons.md` L5.12). An out-of-workspace pack installed into the
development venv changes what the whole suite sees (`docs/lessons.md` L5.31).
