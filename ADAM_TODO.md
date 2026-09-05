# What's yours

Everything here needs an account, an authority, or a decision that isn't a task's to default.
Nothing on this list is blocked on more code.

Rewritten 2026-09-05, after the consolidation landed and the release was parked. `docs/README.md`
is still the source of truth for project state — this file is only the subset that has your name on
it, and it is ordered by what unblocks the most.

---

## 1. ~~Decide there is a Phase 8~~ — **answered 2026-09-05: yes**

**Closed.** You opened **Phase 8 — From engine to product**, and it owns the whole shortlist rather
than the ladder alone, so `ROADMAP.md` is retired into it and nothing buildable is homeless any
more. `01` → Phase 8 carries the exit criterion; `build-ledger.md` → Phase 8 carries the tasks;
`docs/README.md`'s decision log records it as scope decision `S9`.

Two consequences worth knowing, because neither was in the question as asked:

- **Phase 8 runs before Phase 7**, which G12 still gates. The number says when it was added to the
  plan, not where it sits in the queue. `scripts/next_task.py` will keep printing `7.1` as the first
  unticked box; `docs/README.md`'s **Next action** row is the mechanism that overrides that, and it
  is pointed at task 8.6.
- **The lessons queue now has a phase close to drain against again**, which it did not before.

Nothing here is blocked on you any more. What is left in Phase 8 — hybrid retrieval, the fan-out
cap, the falsification instrument, a driver for `Renderer`, and the expander/services repair — are
tasks, not decisions.

---

## 2. Publish — **parked 2026-09-05, by your call**

Not stale, not forgotten: paused. Here is the exact state so picking it up costs no re-derivation.

`v2.1.0` is tagged, the GitHub Release exists with notes, `main` is green. The workflow ran and
**all five publish jobs were refused**:

```
429 Too many new projects created
```

**Nothing was published.** PyPI holds exactly the four names it held this morning —
`weft-command`, `weft-embed`, `weft-generate`, `weft-llm` — and those are vestigial: they receive
no further versions, and they need no publisher, no token and no attention, ever.

**Do not re-run the workflow to see if it works now.** The limiter counts *attempts* over a rolling
window rather than successes, so a rerun pushes recovery further away — `docs/lessons.md` L7.3 is
the incident and L7.9 is today's repeat of it. Measured today: the saturating burst was `08:53Z`
and a single request at `13:04Z` was still refused, so the window outlasts four hours at that
volume.

**When you want it, in preference order:**

1. **Ask PyPI support for a project-creation exception.** One message, and it is exactly what that
   channel is for — a legitimate multi-distribution project claiming six names. Fastest, and it
   removes the guessing about the window entirely.
2. **Or leave it alone for a day and re-run the existing run** — no new tag, the release object and
   the commit are already correct:
   ```bash
   gh run rerun 33967852159 --failed
   ```

**Six names now, not twenty**, which is the consolidation's most immediate benefit: `weft-rag`,
`weft-kernel`, `weft-openai`, `weft-pdf`, `weft-qdrant`, `weft-otel`. All six are new projects.

**One thing to confirm before it becomes permanent:** `weft-rag` publishes at **`2.1.0`**, not
`0.1.0`. `09` §2.3 forces a distribution's version to the maximum contract version it publishes,
and this wheel publishes `COMMAND_CONTRACT_VERSION = 2.1.0`. §2.2 answers the "but that promises
1.0" objection in advance — the binding, not the leading digit. It is mechanically correct and it
is still a number you can never reuse, so it is worth one deliberate look.

---

## 3. Settle the founding claim — and it goes before the graph work, not after

`NOTICE` says **"Weft contains no source text from any other codebase."** Two separate things have
made that sentence false, and one amendment covers both:

1. **Five to eight sites quote reference docstrings verbatim, attributed** — `weft_clean/
   table_linearizer.py:6-7`, `whitespace.py:6`, `hyphenation.py:7`, `unicode_normalizer.py:5`
   (which labels its own quotation "verbatim"), `weft_llm/loop_guard.py:50`. Nothing executable was
   carried and every fragment is attributed ordering rationale — this is a **claim-accuracy**
   defect, not a plagiarism one.
2. **You decided on 2026-09-05 that `graph-study-main` may be copied as-is**, because it is your own
   unlicensed prior work. Licit, and it falsifies the same sentence the moment the first line lands.

**Why it is yours:** it changes a founding claim, so it wants an explicit decision-log line rather
than a quiet edit. The amendment has to distinguish three cases and is cheap to get wrong: the
third-party reference (write fresh, always) / your own prior work (copyable) / short attributed
quotation of a cited rationale.

**I have drafted it** — see the commit that lands with this file. Read the wording; the substance
is yours to accept or change. There is also a live rule conflict settled in the same act:
`weft_clean/artifact_remover.py:63,67` carries a reference regex under a "facts, not text" exception
while `04:144-145` says regexes specifically must be authored fresh.

---

## 4. Run G12 — still the only open gate, and it still blocks all of Phase 7

Unchanged since 2026-08-26 and repeated here because nothing has moved it.

**The question:** `03` → *Permissions* says an `ask`-class operation fails with no TTY and never
proceeds silently. An agent is never a TTY. So either a Phase 7 pack can never `overwrite` or
`destroy`, or something other than a TTY counts as consent. Which?

Read strictly, the most useful thing an agent could do — reindex a collection it just noticed was
stale — is permanently out of reach. Read loosely, the pack passes `--yes` on every call, which is
`03`'s own sentence about `--yes` disarming the whole table, with the human removed.

**New since it was written:** the graph reference supplies two further positions rather than settling
it — *autonomy licensed by reversibility of writes* rather than by supervision, and
*propose-without-persisting then activate-from-a-file* as an approval channel that is not a slower
spelling of `--yes` (`docs/audit-graph-study-2026-09-05.md`). Both are arguments for the session.

The session is written and waiting in `docs/05-grilling-sessions.md` → **G12**. Run it with the
`grilling` skill. **Prerequisite:** `01` requires the **`agentic-patterns`** skill to run first —
G8 moved that handoff to this gate deliberately, so it lands with real contracts to reason about.

---

## 5. Push the branches that hold the ledger's evidence — and note what changed

`docs/build-ledger.md`'s sha column points into `phase-6-detail` and `gates-g10-g13`, which hold
all 70 original per-task commits. **Only `main` has ever been pushed**, so the ledger's evidence is
one disk failure from gone.

```bash
git push origin phase-6-detail gates-g10-g13
```

**What changed since this was first written:** the repository is **public** now. Pushing these
publishes 70 commits of working history — which is almost certainly fine and arguably the point,
but it is now a different act from what it was when the repo was private, so it is stated rather
than assumed.

---

## 6. Set the 1.0 review date — G10 required one and there still isn't one

G10 settled that 1.0 rests on **evidence**, with a **fixed review date** at which any outstanding
preconditions are *published* — naming what is missing and what it would take. The session's own
argument for keeping a date: *"a checklist whose rows never all tick is a release that never
happens."*

**No date is set anywhere in `docs/`.** The mechanism G10 built to stop 1.0 drifting is itself
drifting. Six preconditions in `docs/09-release.md` §2.2; five are demonstrable today, and the
sixth — *the extension model works for someone who is not us*, with the graph pack installed **from
the index** — is item 2.

Pick a date, write it into `09` §2.2.

---

## 7. The kernel boundary conversation — the number moved

`weft-kernel` is **3,097 lines**, up from 3,079, past fitness function 3's **2,800-line review
trigger**. The budget is 3,500 and is not close, so nothing fails — the trigger exists to make this
a conversation before the ceiling is a crisis, and the rule is explicit that **the budget is never
edited in the pull request that grew it**.

Today's +18 is `PackReport.pack` and its threading through `_activate` — a pack's identity separate
from its distribution. It was argued in place against `01` → *The kernel boundary*'s own table,
which puts "registration and versioning" and "the `plugins doctor` computation" in the kernel's
column.

**A related question worth folding into the same conversation:** `Registry.add` still attributes a
registration to a *distribution*, not a pack. That is why `plugins doctor` groups displaced
registrations per wheel rather than per pack, why fitness function 2's count comparison had to be
aggregated, and why the contract reference says `weft-rag` where it used to say `weft-store`.
Carrying `pack` down to the registry closes all three; it is ~700 call sites and it grows the
kernel. Whether that is worth it is a boundary question, not a coding one.

---

## 8. Repay the token debt — unchanged, and now conditional on item 2

The publish runs on an **account-scoped** PyPI token, which can upload to any of your projects,
including `dependence-forecastability`. That scope exists only because a project-scoped token
cannot be minted for a project that has never been published to.

Once the six names exist that constraint is gone. Then: add a trusted publisher to each of the
**six** projects and delete the token — the resting state the workflow was written for — or replace
it with six project-scoped tokens, which is weaker but bounded. **Either way, delete the
account-scoped token.**

The good news the consolidation brings: six trusted-publisher forms, not twenty.

---

## Done since the last rewrite

- ~~**Decide whether the repository is public.**~~ It is public, so task 6.35's reproduction
  artefacts are reachable by the stranger who installs from the index, and that row of Phase 6's
  exit is no longer blocked by visibility.
- ~~**A PyPI account, a GitHub remote, publishing credentials.**~~ All done 2026-09-05.
- ~~**Merge the branch.**~~ `phase-6-close-findings` is on `main`. What remains of that item is the
  push in item 5.

## Not yours — here so you don't wonder

- **The lessons queue holds nine entries** (L7.1–L7.9), which is the loop working rather than a
  backlog. `implement-ll` drains it at a phase close — which is one more thing item 1 decides,
  since there is currently no phase for it to close against.
- **The release set is `weft-rag`, not `weft`**, and it now *contains* the fourteen packs rather
  than pinning them. `09` §1, G10's decision-log row, the quickstart and the release-set README all
  carry it.
- **`[packs.weft-store]` is now `[packs.store]`.** A pack's identity is its entry-point name; the
  distribution is only what you install. A stale key is refused by name and lists every valid pack,
  so nobody silently runs unconfigured.
- **`ruff` is an optional extra** — `weft-rag[reference]` since the consolidation, needed only to
  regenerate the contract reference.
- **Live-API tests are opt-in.** `poe ci-checks` is deterministic on a machine with an
  `OPENAI_API_KEY` exported; set `WEFT_LIVE_API_TESTS=1` to run them.
- **`ci-checks` is only the canonical gate with the container up.** Fifty-one tests skip without it
  and the skip count is the only signal — `docs/lessons.md` L7.8, learned the hard way today.
