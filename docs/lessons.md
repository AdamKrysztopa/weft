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


## When the queue is empty

That is the healthy state, and it means the last drain finished. What was learned lives in
`lessons-archive.md`, session by session, with the edges between entries — which is where the
question *have we been here before?* is answered, and where an on/off cycle becomes visible.
