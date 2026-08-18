---
name: weft-qualities
description: Review any change, design, contract, or phase exit against Weft's six quality requirements — a capability is one package with zero edits to core, multi-point capabilities stay one package, pipelines derive from pipelines, built-ins get no privileged path, unknown names fail loudly naming the valid options, and shipped technique is parameterisable and composable. Use this whenever adding or reviewing a capability, contract, plugin, pack, pipeline stage, config field, CLI command, registry, enum or dispatch; whenever deciding where code should live or reviewing a diff or PR; and before declaring a phase complete — even when the user says nothing about quality, elasticity or extensibility, because these properties are lost silently and one commit at a time.
---

# Weft's quality requirements

Weft exists because its predecessor was designed to be elastic along five axes and was not elastic
along any of them — not through neglect, but one reasonable-looking commit at a time. Every one of
those commits was defensible on its own. This skill is the check that the current one is too.

**The six requirements are stated in `docs/01-high-level-plan.md` → *What "modern and elastic" has to
mean concretely*. That document owns them; this skill applies them.** If the two disagree, that
document wins and this skill is out of date. Read it if the summaries below are not enough to judge
the case in front of you.

## How to use this

Ask what is being reviewed, then run the lenses that apply — most changes touch two or three, not six:

| Reviewing | Run |
|---|---|
| A new capability, plugin or pack | 1, 2, 6 |
| A contract, or a change to one | 1, 4, 6 |
| A pipeline stage | 3, 6 |
| Config, a registry, an enum, a dispatch | 1, 4, 5 |
| A CLI command | 2, 5 |
| A phase exit | all six |

Each lens below gives the requirement, the **question that falsifies it**, and what it looked like
when the reference got it wrong. Use the falsifying question — a lens you cannot fail is a lens that
passes everything.

---

### 1. A new capability is one new package, zero edits to core

**Falsify it:** *name every file outside the new package that has to change.* If the list is not
empty, the requirement fails, and the length of the list is the size of the failure. "One small edit
to core" is the failure mode, not an exception to it.

Watch for the three shapes this takes: a name added to an enum, a branch added to a dispatch, a key
added to a catalogue. Each is two lines and each converts an extension point back into a decision
tree.

**Reference:** adding one storage backend meant editing **11 library files**, and there were zero
registered backend names.

### 2. A capability spanning several extension points is still one package

**Falsify it:** *if this shipped an enhancer, a retriever, a store and a CLI command, where would its
connection details live?* If the answer is "in each of them" or "there is nowhere", it fails.

The test is really about whether per-pack settings and per-stage config stay distinct: pack settings
are *this installation of this pack*, stage config is *this stage in this pipeline*. Collapsing them
forces a pack to repeat its endpoint three times and hope they stay in sync.

**Reference:** `IndexingStrategy` had exactly three fields and enhancers were named as bare strings, so a
graph add-on had nowhere to put configuration at all.

### 3. A pipeline is derivable from another pipeline

**Falsify it:** *can this stage be added to an existing pipeline by configuration alone, with no copy
of the parent?* And: *if someone inserts a stage in the wrong place, what tells them?*

Data-dependency ordering is solved by `requires`/`provides` checked at resolution. Semantic ordering
is not, and it is why this lens still needs a human: a destructive stage must run last **because it is
destructive**, not because anything reads its output, and no dependency graph can see that.

**Reference:** the cleaning chain's ordering constraints existed as a docstring — *"IMPORTANT: Changing
this order will break functionality"* — and the one config field shaped like a stage list was never
read by the executor.

### 4. Built-ins have no privileged path

**Falsify it:** *what does this built-in use that a third party could not?* Then check it at runtime
rather than by reading — the reference would have passed a static check.

This is the requirement that decides whether the project works in two years. If built-ins get a
shortcut, the public path is exercised only by outsiders, and it rots.

**Reference:** the most literal instance available — `retrieval/registry.py:649-668` re-wraps and
re-assigns the three indexing builders *after* the decorator registered them, to add span wrapping. A
plugin using the public decorator silently got less observability than a built-in.

### 5. An unknown name fails loudly, naming the valid options

**Falsify it:** *what happens on an unknown name, a missing optional dependency, a refused pack?*
Three failures, one standard: say what was wanted, why it is unavailable, and what the valid options
are.

A silent fallback is worse than a crash, because it produces a plausible answer. Weft's `Outcome`
type exists so a degraded path is *visible* rather than indistinguishable from success.

**Reference:** asking for the `faithfulness` metric returned **no error and no score** — 6 of 21
evaluators never registered, and unknown names were silently dropped.

### 6. Real technique, parameterisable and composable by someone who did not write it

**Falsify it, in two parts:** *can a third party run this with different parameters without editing
it?* and *can they compose it with something else without editing it?* Two noes mean this is a
feature, not a capability.

The requirement cuts both ways and that is the point. A kernel that stays small by shipping nothing
fails it; so does technique bought by fattening the core. **Richness is counted in packs, never in
kernel lines** — which is what makes the kernel budget safe to enforce, because it can never be an
argument against having ideas.

Keep the reasoning with the technique. For most of what is worth shipping, the comment is the asset:
why a constant is that value, which way to move it, what breaks if you reorder it.

**Reference:** ten genuinely good retrieval strategies that a third party could not compose, because the
router assigned literal enum members in a hard-coded ten-branch ladder; and a metric suite that could
not be parameterised at all.

---

## The move that matters most

**When a finding could be caught by machinery, say so and propose the check.** This is the project's
central generalisation, and it was measured rather than assumed: in the reference, *every concern the
machinery applied automatically held perfectly, and every concern an author had to remember decayed.*
Spans applied at registration held on all ten strategies; spans written by hand decayed to 38 of 54
names off-convention and an entire untraced stage.

So a review finding is a stopgap, and the durable version of it is a fitness function. When you find
something, ask whether the seam that would catch it already exists — registration, resolution,
discovery, config load — because a check that attaches to an existing seam costs almost nothing.
`docs/01-high-level-plan.md` → *Fitness functions* lists the nine that exist; adding one means adding
it to the `ci-checks` composite in the same commit, which fitness function 0 enforces.

A proposed check is worth more than a fixed line. Say both.

## Report like this

Lead with what fails. If nothing fails, say so plainly and stop — a review that always finds
something is a review nobody believes.

For each finding: **which requirement**, the **falsifying answer** (the actual file list, the actual
error message, the actual thing a third party cannot do), **what to change**, and **whether machinery
could catch it** — naming the seam.

Then one line on requirements that were checked and held, so the reader knows the lens was applied
rather than skipped.

## What this is not

- **Not a style review.** Ruff and Pyright run in `ci-checks` and are better at it.
- **Not an architecture gate.** If the change runs into an *open* decision (G2, G7, G8, G9 in
  `docs/05-grilling-sessions.md`), stop and name the gate. Defaulting an open decision in a code
  review is precisely what the gates exist to prevent.
- **Not a reference audit.** For what is still unlifted, use `reference-audit`.
- **Not a veto.** These requirements have costs, recorded in `docs/01` alongside them. A change that
  fails one may still be right; what is not acceptable is failing one without noticing.
