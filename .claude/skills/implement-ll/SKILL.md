---
name: implement-ll
description: Drain the lessons queue — take every open entry in docs/lessons.md, group them, route each to the artefact that would actually have caught it (a hook, a fitness function, a skill, CLAUDE.md), apply them in one commit, and leave the queue empty. Use at a phase close or a gate close, or whenever asked to implement the lessons learned, spend the ledger, apply what we learned, or clear lessons.md. The queue is drained completely or the entries are declined with a reason; nothing is carried to a second phase close.
---

# Drain the lessons queue

`docs/lessons.md` accumulates during a phase. This skill spends it. **The queue is empty when you are
done** — every entry has become an edit or a recorded decline. Nothing is carried forward, because an
entry that survives two phase closes is one nobody intends to implement, and a queue with permanent
residents stops being read.

## First, ask whether you have been here before

```bash
python3 scripts/lessons_graph.py
```

**Run this before reading the queue, not after routing it.** It walks
`docs/lessons-archive.md` and reports three things a flat reading cannot see:

- **Oscillation** — a `reverses` edge onto an entry that itself reverses something. Per the archive's
  own rule this is a **stop**: what you are holding is an unsettled decision wearing a lesson's
  clothes, and it goes to a grilling session with the whole chain as its evidence. Do not apply
  either side again. The chain is the argument, which is why reversed entries are kept rather than
  deleted.
- **Recurrence** — a rule that was applied and re-learned anyway. It did not bite, so it is in the
  wrong artefact. The repair is a `moves` edge, almost always `CLAUDE.md` → a hook. **Do not write a
  second rule saying the same thing louder** — that is how a `CLAUDE.md` grows until nobody reads it.
- **Dangling references** — an edge naming an id the archive does not hold.

Then read the archive's entries for this phase's subject matter. Half of what a queue proposes has
been proposed before, and the archive is the only place that says so.

## Before you route anything

**Read the whole queue first, then group.** Entries are written one at a time, in the moment, by
someone who could not see the next four. Several usually collapse into one rule, and the grouped
version routes differently from any of its members — most often *upward*, from four skill sentences
to one hook.

Then, per group, ask the question the routing turns on:

> **At what moment could this have been caught, and what was running at that moment?**

Not *what would be nice to write down.* The artefact that gets the rule is the one that was already
executing when the mistake was made.

## Routing, in order of preference

The order is by **cost of being forgotten**, and it is not negotiable — it is the same ordering
`CLAUDE.md` states for cross-cutting concerns, which the reference measured: every concern its machinery
applied automatically held, and every concern an author had to remember decayed.

1. **A hook** (`.claude/hooks/`, registered in `.claude/settings.json`). Use when the moment is
   mechanically detectable — a file being written, a command being run, a session starting. Strongest
   available: it cannot be forgotten, costs nothing to remember, and both files are checked in so it
   travels with the repository. **Reach here first and only fall through when you genuinely cannot
   detect the moment.**
2. **A fitness function** (`tests/architecture/`). Use when it is a property of the *whole tree*
   rather than of one edit. Per FF0, add it to the `ci-checks` composite **in the same commit** — the
   reference shipped a boundary checker that was not in its canonical task and therefore never ran, and
   FF0 exists because of it. Prefer a ratchet with a named waiver constant pinned empty, so a waiver
   is a visible act in a diff.
3. **A skill** (`.claude/skills/`). Use when it is judgement applied at a known moment — a step in
   `phase-step`, a lens in `weft-qualities`. **Amend an existing skill rather than writing a new one**
   unless the moment genuinely has no owner; a fifth skill nobody invokes is worse than a sixth
   sentence in one that is.
4. **`CLAUDE.md`.** Use when it governs everything and belongs in the first thing anyone reads. This
   is the **most expensive destination, not the default** — every line there competes for attention
   with every other line, and a `CLAUDE.md` that grows every phase is one that stops being read.
5. **A reference document** (`01`–`05`, `build-ledger.md`). Use when the entry is really a design fact
   or a build task wearing a lesson's clothes. `docs/README.md` holds state and pointers only, never
   definitions — so nothing lands there but a link.
6. **Decline.** A real outcome and it must stay available. Decline when the entry is an anecdote with
   no general shape, when the rule would fire constantly on correct work, or when the cost of the
   check exceeds the cost of the mistake. **Record the reason** — that is the whole value, and it is
   what stops the same proposal arriving next phase.

## The two traps

**A rule written in the wrong place looks applied and is not.** If a group's honest moment is "while
someone was typing an edit" and it lands as a sentence in `CLAUDE.md`, the entry is closed and the
defect will recur. When in doubt between a hook and a sentence, take the hook.

**Do not implement a *finding* as a rule.** Some entries carry a defect in the tree as well as a
lesson about the work — L5.5's unchecked `weft.toml` container is one. The defect becomes a
**build-ledger task**; only the generalisation becomes a rule. Fixing the instance and calling the
lesson applied leaves the class open.

## Finishing

1. **Apply every group**, and run `uv run poe ci-checks` — green, in the foreground. A new fitness
   function is in the composite in the same commit or FF0 fails.
2. **If a hook was added or changed, trigger it** and read what it prints. A hook is code, and
   `CLAUDE.md`'s rule holds: a green gate is not a working binary.
3. **Move every entry out of `lessons.md`'s *Queue* into `lessons-archive.md`**, under a new dated
   `##` section for this drain. One line each — id, the rule in one sentence (or `declined` and the
   reason), where it landed, the commit, and **any edge to an earlier entry**. `lessons.md` ends the
   drain empty.

   **The edges are the part that is easy to skip and expensive to skip.** An entry that refines,
   supersedes, moves, recurs, reverses or is caused-by an earlier one must say so, using the archive's
   closed vocabulary — that is the only thing standing between this loop and an on/off cycle, and the
   next drain's oscillation check can only see what this drain wrote down. The one-sentence rule is
   written to be read cold by someone who was not there, because it is what the `SessionStart` hook
   injects and therefore the entire memory of the loop.
4. **One commit**, naming the lesson ids and saying what each became. The diff says what changed; the
   message says which mistake bought it.
5. **Answer the loop's own check**, in the phase's build-ledger entry:

   > *Which of this phase's defects would a rule already in **Applied** have caught?*

   *"One, and it was in the queue"* means the loop collected and did not spend — drain earlier.
   *"One, and it was Applied"* means the rule is in the wrong place, and it is almost always a
   `CLAUDE.md` sentence that should have been a hook. Re-route it in this same drain rather than
   logging a new entry about it.
