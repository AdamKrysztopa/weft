---
name: paper-to-plugin
description: Turn a research paper into a Weft plugin — correctly named, honestly scoped, and written fresh. Use whenever a paper, arXiv link, PDF or technique name is dropped into this repository with any expectation of code, and whenever someone asks to implement, port, add or "do" a named technique (RAPTOR, HyDE, ColBERT, GraphRAG, a reranker, a chunker, a metric). Also use before registering ANY plugin whose name comes from the literature, before adding a row to docs/10-technique-catalogue.md, and when deciding whether something is one plugin, a pipeline, or a name that must not be taken. If a paper is in the conversation and code is the destination, this skill owns the path.
---

# Paper to plugin

A paper describes a technique. A plugin claims to implement one. This skill is about keeping those
two things honest to each other, because in Weft **a plugin name is a published surface**: third
parties write it into configuration, and the failure path prints it back at them
(`docs/02-extension-model.md` §2 — *every unresolvable plugin name carries its reason*).

So `hyde` is not a label. It is a claim that this code does what Gao et al. described. Someone will
read the name, believe the claim, and configure a system on it.

`docs/10-technique-catalogue.md` owns provenance and states the rule that keeps it honest. This
skill is how a new paper gets through that door.

## The thing that goes wrong

Not bad code — **an overclaiming name attached to good code**. It is invisible in review, because the
implementation is fine and the name reads as documentation. It surfaces years later when someone
configures `self-rag` expecting reflection tokens and gets a confidence threshold.

The catalogue records this happening: `rag_consensus` named a technique the code did not
implement, and `10` §2.2 renames it to `contradicted-check` for exactly that reason. Weft's own
`hyde` diverges from its paper — it fuses where the paper averages — and that divergence is written
on the class docstring rather than left for someone to find by diffing the module against the PDF.

**The test to apply at every step: if a practitioner searched for this technique's name and landed on
this plugin, would they be misled?**

## Procedure

### 1. Read the paper. Actually read it.

Not the abstract, not a summary, not your memory of it. `CLAUDE.md`'s standing rule is *measure
before asserting*, and it is nowhere more load-bearing than here — you are about to make a public
claim about what a paper says.

What you need out of it, and each of these is a separate fact:

- **The mechanism.** What does the technique actually do, stated as steps.
- **The constants.** Every number the authors chose, and whether they justified it. RRF's `k=60` is
  in the paper; HyDE's sample count is not confirmed at source, and `10` §5 says so out loud.
- **What the paper claims and what it measured.** These differ more often than not.
- **What it depends on** — a model class, a corpus property, a language. A technique validated only
  on English is a technique with a scope, and `weft-eval`'s hardcoded `lang="en"` is the live
  example of what happens when that scope goes unrecorded.

Write down what you could not determine. An unconfirmed fact stated confidently is worse than a gap,
and `10` §5 exists as a section rather than as footnotes precisely because *the value of a catalogue
is proportional to how visible its gaps are*.

### 2. Establish the name before you write any code

This ordering is not bureaucracy. Naming after implementing means naming what you built, and what you
built is exactly what you will be tempted to describe generously.

Four questions, in order:

1. **Is this name reserved?** `10` §4 holds names the literature has fixed for techniques Weft does
   not implement — `self-rag`, `flare`, `ircot`, `iter-retgen`, `self-ask`, `self-consistency`,
   `adaptive-rag`, `query2doc`, `decomposition`. Taking one is not a style choice; it forecloses the
   real technique ever shipping under its own name. If the paper *is* one of these, you are removing
   a row from §4, and that is part of the task.
2. **Does the literature already name it?** Use that name, acronyms included — `hyde`, `raptor`,
   `step-back`. A "clearer" rewrite makes it less findable, which is backwards.
3. **Who named it?** The paper that *introduced* a technique and the work that *named* or
   *popularised* it are different facts and the catalogue has a column for each. This decides
   whether a future rename is a correction or a preference.
4. **Will it have siblings?** `cross-encoder-rerank`, never `rerank` — an unqualified name lets the
   first implementation seize a namespace that belongs to a family.

Then apply the rule with teeth (`10` §2.1 rule 4): **never take a name that promises more than the
code does.**

### 3. Decide what it actually is — and it may not be a plugin

Three outcomes, and picking wrong is the most expensive error available here:

- **A plugin**, if it is one mechanism filling one position.
- **A pipeline**, if it is a composition of things that already exist. `10` §2.1 rule 5:
  *a composition is a pipeline, never a plugin*. `rag_complex` named HyDE plus repacking;
  registering it would have put a name on data that requirement 3 says is derivable. **Weft ships
  four pipeline documents in the whole tree, so this outcome is almost certainly under-used, not
  over-used** — if the paper is a recipe over known parts, a document is the honest answer and it is
  also the cheaper one.
- **A field on something that exists.** `weft_retrieve.repack` and `collapse-to-parent`'s
  `CollapsePolicy` are one mechanism with a config field rather than three plugins. If the paper's
  contribution is a parameter choice, ship the parameter.

Then place it: which contract does it register against, and which pack publishes that contract? The
kernel names no capability, so if the technique needs a contract that does not exist, a **pack** owns
the new one — and a new first-party contract is a decision with a gate behind it, not a task. Stop
and say so rather than defaulting it.

### 4. Write it fresh

**No source text from any implementation** — not the authors' reference code, not a framework's
version, not another Weft plugin's body. The rule is absolute and `NOTICE` states it as a property of
the repository. The test from `CLAUDE.md`: *if you could not have written this line without the other
file open, it is a copy.*

This is easier here than it sounds, because **a technique from a paper belongs to the literature, not
to any codebase** (`10`'s own framing). You are implementing a described mechanism against Weft's
contracts, which have different types and a different shape from anything the authors wrote.

The parts that carry the most risk are the text-shaped ones — prompts especially. A prompt in a paper
is prose you must re-author for Weft's prompt layer, not a string to transcribe. `04`:144-145 is
explicit that prompts, word lists, locale catalogues and regexes must be authored rather than carried,
because *for those the text is the asset*.

While writing, hold Weft's shape: every contract method is `async def`; return frozen Pydantic models,
never `dict[str, Any]`; `Enum` for string constants, never `Literal`; catch specific exceptions,
because a silent fallback is worse than a failure. Every constant the paper chose becomes a config
field with the paper's value as its default — `10`'s whole complaint about a fixed ladder is
that tuned numbers were unreachable.

### 5. Write the divergence at the name

Almost every honest implementation diverges from its paper somewhere. Weft's convention is that the
divergence lives **in the plugin's own docstring, next to the name that makes the claim** — not in a
commit message, not in the catalogue alone.

`Hyde`'s docstring is the worked example: the paper averages several hypothetical documents'
embeddings with the query's own into one dense vector; Weft's plugin does not average — each
hypothetical becomes its own query, retrieved separately and combined downstream by a `Fuser`. That
sentence is on the class, so a reader who arrives at the name arrives at the divergence.

`tests/docs/test_technique_naming.py` enforces this: **a docstring a future edit strips is a silent
regression**, and that test exists because a hand-read audit cannot re-run itself next phase.

Classify the fidelity honestly, using the catalogue's own vocabulary: **Faithful** · **Simplified** ·
**Diverges** · **Different technique** · **Defective**. If it lands on *Different technique*, the name
is wrong — go back to step 2.

### 6. Record the provenance

- **A row in `docs/10-technique-catalogue.md`** §1.1–§1.5, with all five columns filled: Weft name,
  what it does in one line, Origin cited in full, Name provenance, and fidelity. *If the "what it
  does" needs two lines, it is a composition and belongs in a pipeline* — that is the catalogue's own
  diagnostic, and it will catch a step-3 mistake here.
- **A full citation in the `build-ledger.md` entry** — authors, title, venue, year, arXiv or DOI. The
  existing entries are the format: RRF cites *Cormack, Clarke & Büttcher, SIGIR 2009, pp. 758-759,
  DOI 10.1145/1571941.1572114*; HyDE cites *Gao, Ma, Lin, Callan, arXiv:2212.10496 (2022), ACL 2023*.
- **If nothing supports the common name**, say so in `10` §5 rather than inventing provenance. Four
  rows already have no paper behind their name, and recording that is the finding.
- **If the paper's name was reserved**, remove it from §4 in the same commit.

### 7. Run the check that enforces all of this

```bash
uv run pytest tests/docs/test_technique_naming.py -q   # the naming rule, five properties
uv run poe ci-checks                                    # the canonical gate
```

Then run the binary. `CLAUDE.md`'s strongest warning applies with full force to a plugin that has
only ever been tested: all four of Phase 3's repairs were found by running `weft` and none by its
1,513 tests. Configure the new plugin into a pipeline document, run it from a directory that is not
this repository, and read what it prints — including a failure path.

## When the paper is a family, not a technique

Papers like RAPTOR or GraphRAG describe a *system*: an index-side construction, a retrieval-side
traversal, and often an evaluation protocol. Implementing "the paper" as one plugin is the mistake
this repository is shaped to prevent — it produces the same god-object and fixed
ladder `10` complains about.

Split by **position**, and let each piece register where it belongs. RAPTOR is already split this way
in Weft: `RaptorSummarizer` is an `Expander` on the index path in `weft-index`, and what it produces
is retrieved through the ordinary query path with `collapse-to-parent` handling the several-ways-
indexed problem. The paper is one thing; the plugins are several, and each is separately
configurable, which is requirement 6.

A useful question when splitting: *which of these pieces would somebody want to use without the
others?* Each yes is a plugin.

## Failure modes worth naming

- **Naming what you built rather than what the paper described.** Prevented by doing step 2 first.
- **Carrying a constant without its justification.** A number with no comment is a number the next
  person will "clean up". The paper's value goes in the default; the paper's reasoning goes beside it.
- **Implementing the ablation instead of the method.** Papers often describe several variants; the
  headline result is usually one of them. Say which one you built.
- **A prompt transcribed rather than authored.** The most likely place this repository's originality
  rule gets broken, because a prompt looks like configuration rather than like source text.
- **Silence about scope.** A technique validated on English, on one corpus size, or against one model
  family has a scope. Unstated, it becomes a silent wrong answer — which is the failure class
  `CLAUDE.md` singles out: *it does not crash, it produces a plausible answer against the wrong data.*
- **Growing the kernel.** If a technique seems to need kernel lines, the technique is not the problem
  — the seam is. Fitness function 3 caps `weft-kernel` at 3,500 lines with a review trigger at 2,800,
  and it is at ~3,079. Say what the extension point would have to be instead.

## What this skill does not do

It does not decide whether a technique is worth building — that is a scoping conversation and,
for a new contract, a gate. It does not settle where a new capability family lives. And it does not
write the ledger task: `phase-step` owns that, and a task states the property that must hold rather
than the repair that will make it hold (`lessons.md` L7.1).
