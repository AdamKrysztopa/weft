---
name: implementation-status
description: Answer "where are we" in the Weft repository with one table of the live phase's tasks — id, a five-word description, a size estimate and a status derived from docs/build-ledger.md and docs/README.md. Use this whenever anyone asks for status, progress, the state of play, how far along we are, what is left, what is done, what is blocked, what is next, how much work remains, or names a phase and asks how much of it is built — including a bare "status?", "where are we?", "what's left?" or "how's Phase 10 going?". Use it before writing any prose summary of project progress, because the table is the answer and a paragraph about the plan is not.
---

# The implementation status table

A status answer here is **one markdown table and nothing before it**. No preamble, no "let me
check", no restatement of the phase's purpose. Whoever asked wants to see the shape of the work in
one glance, and any sentence above the table pushes the first row off the top of their screen.

This is the deliberate exception to the standing instruction not to produce status summaries. That
instruction exists to stop *unrequested* progress reports padding an answer about something else.
Here the report **is** what was asked for, so it is given in the densest form there is: a table.

Every row is derived from the repository, now, in this invocation. Not from memory of an earlier
turn, not from a phase document's plan, not from what the last commit message said. `docs/` is a
living plan that changes several times a day, and a status table quoted from memory is confidently
wrong about the one thing it exists to be right about.

## The table

```markdown
| id | description | size | status |
|---|---|---|---|
| 10.0 | baseline before the plugin changes | L | **done** — `dcb3702`, ticked `4e5f4c1` |
| 10.1 | documents agree, proof owed | M | **in progress** |
| 10.2 | truncation recorded | M | not started |
| 10.14 ⚠ | new document joins existing tree | XL | not scheduled |
```

One row per task in the phase, in ledger order — including the ticked ones, because "eleven of
sixteen done" is only visible if the done ones are on screen.

### id

The ledger task identifier exactly as `docs/build-ledger.md` writes it — `10.3`, `9.14`, `10.16` —
carrying any `⚠` or `⛔` the line itself carries. Those glyphs are the ledger's own vocabulary
(`⚠` provisional, an open gate could change the task's shape; `⛔` a block), and dropping them
turns a hypothesis into a commitment.

### description

**At most five words**, saying what the task makes *true*, never what it adds. The ledger's
`makes true` sentence is a full property statement, often forty words; this column is a
compression of it, in your own words, not its first clause copied. `a baseline exists before any
line changes the plugin: a persisted weft eval run, against a real embedder, comparing…` becomes
**baseline before the plugin changes**. If a description reads as "add X", "implement X" or
"write X", it is describing the work rather than the property, and the ledger's own rule for task
lines says the property is the thing.

### size

One of **XS, S, M, L, XL, XXL** — an estimate of the work *remaining*, so a half-built task is
sized by what is left, not by what it always was. Say once, below the table, that these are
estimates; a reader who takes them for measurements will plan against them.

| | roughly |
|---|---|
| **XS** | a one-line edit, or a sentence in a document |
| **S** | one small test plus a small change |
| **M** | a test plus a real implementation in one module |
| **L** | several modules, or a measurement run, or a new fitness function |
| **XL** | a new contract surface, a multi-stage mechanism, or work needing its own design decision |
| **XXL** | something that should probably be more than one task |

An XXL is worth a sentence of its own after the table — it is usually the ledger telling you the
line needs splitting.

### status

Exactly one of:

| value | when |
|---|---|
| `not started` | unticked, reachable, nothing begun |
| `in progress` | work on it has begun **in this session** — a test written, an edit made |
| `blocked — <reason>` | name the gate or decision, e.g. `blocked — G14`, `blocked — 11 D2` |
| `done — <sha>` | ticked, carrying the sha from that line's own `sha` field |
| `not scheduled` | the ledger line says it is conditional or unscheduled |

`not scheduled` is not `not started`, and the distinction is the useful part of the table: nobody
will ever pick that line up in order, and the line itself says what would schedule it. Phase 9
closed with `9.15` and `9.16` deliberately unticked for exactly this reason.

A `done` sha is read out of the ledger, never invented and never a prefix of something you
remember. Optionally add the commit that *ticked* the line — the ledger's working protocol records
a sha one generation behind `HEAD` by design, so the ticking commit is the one a reader can
actually `git show`:

```bash
git blame -L <line>,<line> --date=short -- docs/build-ledger.md   # line numbers come from the script
```

## Where the facts come from

Run this first. It prints every task line of a phase with its tick state, its sha, its marks and
its `makes true` sentence, plus what `docs/README.md` says about the live phase:

```bash
python3 .claude/skills/implementation-status/scripts/phase_tasks.py          # the live phase
python3 .claude/skills/implementation-status/scripts/phase_tasks.py 9        # a named phase
```

**Do not grep the ledger for task lines by hand.** `docs/build-ledger.md` → *How to read a task
line* contains an unticked example inside a fenced code block, put there deliberately so no worked
example could drift. `grep '^- \[ \]'` finds that one first, every time, and the table opens with a
row for the placeholder task `N.M`. The script skips fences and requires a numeric id, which is why
it exists.

Then, for the two things the script does not decide:

```bash
python3 .claude/skills/phase-step/scripts/next_task.py     # which task is current
```

- **`docs/build-ledger.md` is the authority** on which tasks exist, which boxes are ticked and
  which sha each carries. A ticked box is `done`; the sha is that line's own `· sha \`xxxxxxx\` ·`
  field and nothing else.
- **`docs/README.md`'s Status block** says which phase is live and what is blocked. Its **Next
  action** row **outranks ledger order** — it is the project's own statement of where it is, and
  the first unticked box can be a line deliberately left unticked. This is live today: `next_task.py`
  reports `9.15` as the first unticked box while the Next action row names `10.1`. The script prints
  both, so the disagreement is visible rather than silently resolved the wrong way.
- **`in progress`** is a fact about this session, not about the tree: the task `next_task.py` names
  is `in progress` if work on it has begun here, `not started` otherwise. A task nobody has touched
  is not in progress merely because it is next.
- **`blocked`** comes from a `⛔` on the line, or a `⚠` whose gate the phase preamble does not
  record as discharged. Read the sentence before deciding — **a mentioned `⛔` is not a live one**.
  Every `⛔` in Phase 10's task lines today is conditional prose ("a ⛔ this phase does not take",
  "⛔ *if* the ..."), and its preamble discharges all four of its `⚠` marks explicitly. The script
  flags the mention with `⛔?(read the line)` precisely because text cannot tell a live block from a
  discussed one; that call is yours, made against the line and the preamble.

## After the table

**At most two sentences.** A headline number, or what is blocking, or the one thing the reader
would otherwise have to work out from the rows — plus the note that sizes are estimates. Not a
summary of the table: they can see the table.

> Eleven of sixteen tasks remain, and `10.7` and `10.8` cannot start until `10.4` is settled.
> Sizes are estimates of the work left, not measurements.

## Which phase

If the user named a phase, show that phase only. Otherwise show the live phase from
`docs/README.md`'s Status block — which is what the script defaults to. If they ask about the whole
project rather than a phase, still give one phase's table (the live one) and let the second
sentence carry the cross-phase fact, because a table of every task in eleven phases answers nothing.

Nothing in this skill restates what `docs/build-ledger.md` and `docs/README.md` own. It reads them
and shapes what they say into a table; when they disagree with this file, they are right.
