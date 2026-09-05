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

### L8.18 — a pre-flight gate refused the run a `fallback:` chain was written to survive

**What happened.** Found by running the binary while repairing prose at ledger task 8.21. A derived
document naming `use: pdf-text` with `fallback: [text]` resolves, and `weft pipeline show fb` prints
`fallback: text` on the stage — so a document's chain **does** reach the resolved `StageSpec`, which
is the opposite of what three documents said. But `weft index ./corpus --pipeline fb` over a
directory of `.md` files refuses before the runner starts: *"nothing under 'corpus' can be read:
found .md, and the installed extractors claim .pdf"*. The accept-set pre-flight reads the **primary**
plugin's claimed formats only; `text` claims `.md` and would have answered. The chain is carried,
the runner would walk it (`weft_kernel.fallback.try_in_order`, task 2.28), and a gate in front of
the runner refuses the run first. Nothing in 2,111 tests looks at this, because no test composes a
document whose fallback claims a format its primary does not.

**Generalises to.** A pre-flight check must be computed over the same set the thing it guards will
actually try — a guard that reads the primary of a chain refuses exactly the inputs the chain was
written for. Where a stage has alternates, every capability derived from that stage is derived from
the union, or the alternates are decoration.

**Candidate home.** A fitness function under `01` → *Fitness functions* item 5 (the derived accept
set, which ledger `1.13` owns and which is exactly this subject), or a repair to whatever computes
`discover_source_docs`'s claimed-format set. Not a `phase-step` rule — this is a defect in shipped
code, not in how the work was done.

### L8.19 — the check certified the field and read as if it had certified the transcript

**What happened.** Ledger task 8.16 built `tests/docs/test_manual_valid_options.py`, which compares a
`valid_options` tuple quoted in `manual/troubleshooting.md` against the live one. It was red on its
first run and caught a real four-day-old staleness. Then it went green — and the **same transcript,
in the same section**, was still wrong: running `weft ask --retrieve-only` from outside the
repository printed a whole clause the manual's copy never carried (*"These distributions contributed
nothing, or only part of what they publish... weft-rag (partial)"*). The check certified one field
of a block and nothing certified the block. A reader of the gate, and of that task's own ledger
entry, would have read "the transcript is checked".

**Generalises to.** Naming what a check covers is not the same as naming what it *leaves* uncovered,
and only the second is load-bearing: a check over one field of a quoted artefact must say, in the
artefact it guards, that the rest of that artefact is unchecked — otherwise its green is read as a
statement about the whole. The sharper form: where the subject is *output*, only executing it
proves anything; a field comparison is a floor.

**Candidate home.** `docs/08-manuals.md` §3, which owns what keeps a manual honest and already
distinguishes a tagged sample from a retyped one — the missing category is an **executed** sample.
Or `phase-step` → *Finish*, beside the existing "run the binary" step, as the reason it is not
discharged by a green check that names the same artefact.


## When the queue is empty

That is the healthy state, and it means the last drain finished. What was learned lives in
`lessons-archive.md`, session by session, with the edges between entries — which is where the
question *have we been here before?* is answered, and where an on/off cycle becomes visible.
