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
- **L5.24** *a capability Protocol specified against "what should exist" is only askable by the thing that already owns those methods* → **G13**, Open · `88edcd0`
- **L5.25** *a fan-out's "only the configured one" exception cannot tell a second primary from a derived participant* → **G13**, Open · `88edcd0` · `caused-by L5.32`
- **L5.26** *a hand-rolled double must carry every public method of the class it doubles* → `tests/architecture/test_ff9_extension_from_outside.py`, a completeness test · `88edcd0`
- **L5.27** *a check that sweeps a directory must be able to answer the question for everything it sweeps* → fixed at task 5.4's repair; no rule owed beyond `L5.6`'s · `88edcd0`
- **L5.28** *a name-collision check built as a substring search is unsound, and a real thing must not take the name a document reserves for a hypothetical* → `phase-step` → *Orient*, with `L5.23`; the AST repair is still owed · `88edcd0`
- **L5.29** *a document's worked transcript is checked against what the code can actually say* → `02` §4 corrected at task 5.6; no rule owed · `88edcd0`
- **L5.30** *a pack that can produce a typed result must be able to render it* → **G13**, Open · `88edcd0`
- **L5.31** *an out-of-workspace pack installed into the development venv changes what the whole suite sees* → **FF9(a)**'s new environment clause · `88edcd0` · `refines L5.12`
- **L5.32** *settled text saying "every X" plus an X it should not cover is a gate to reopen, never a proviso to add* → `phase-step` → *When to stop instead of continuing* · `88edcd0`
