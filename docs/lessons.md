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

### L7.3 — the retry was the thing keeping the door shut

**What happened.** `v0.1.0` published 4 of 20 distributions; PyPI refused the rest with `429 Too
many new projects created`. It was read as a PyPI limitation and put on a 40-minute retry loop.
Seven attempts later the count was still 4. The limiter counts **attempts** over a rolling
window rather than successes, so every rerun of the fifteen failed jobs re-saturated it — on the
order of a hundred creation requests fired to achieve nothing. Retrying was not neutral; it was
the mechanism preventing recovery.

Underneath it, the actual defect was ours: `.github/workflows/release.yml` published a
nineteen-job matrix in parallel, which asks PyPI to create nineteen new projects within seconds.
Serialising (`max-parallel: 1`) removes the burst and costs wall-clock on a job that runs once
per release.

**Why it was invisible.** The flaw exists **only on a first publish**. Every later release
uploads a version to a project that already exists, which is not rate-limited the same way. So
the code was correct in every scenario except the single one it had never been run in — the same
shape as `L7.2` (a CI workflow that had executed zero times) and as the lockfile nothing had
needed until a clean checkout needed it. Three findings in one day, all of them a path taken for
the first time in production.

**Generalises to.** Two rules, and they are separable. *A retry against a rate limiter is only
safe when the limiter counts outcomes; when it counts attempts, retrying moves recovery further
away* — so before automating a retry, establish which kind of limiter it is, and treat "the
count did not move" as evidence of the attempt-counting kind rather than of bad luck. And: *a
burst is a design decision, not a scheduling detail* — fan-out against a shared external quota
needs a stated concurrency bound at the point the fan-out is written, not after the first refusal.

**Candidate home.** The retry half is the sharper one and has no natural artefact yet: it is not
a fitness function (nothing in the tree can test PyPI) and not `CLAUDE.md`'s gate section. It may
belong wherever this project writes about acting on external services — `ADAM_TODO.md` is where
the release obligations live, and `09-release.md` §5.2 owns the publish path. The burst half is
narrower and already fixed at the site; what would generalise is a rule that any matrix or
`gather` against a third-party service names its bound in the same diff that creates it — which
would also have caught `weft_index.raptor`'s unbounded `asyncio.gather`, found the same day by a
different route. That coincidence is the argument for one rule rather than two.

### L7.2 — the gate had never run anywhere but one laptop, and nobody could have noticed

**What happened.** The first CI run this repository has ever had failed three of its four jobs at
their first step: `error: Unable to find lockfile at uv.lock, but --frozen was provided`.
`.gitignore:17` listed `uv.lock` under `# Tooling`, between `.ruff_cache/` and `.pyright/`, and it
had never been committed in seventy commits. `ci.yml` runs `uv sync --frozen` in `gate` and
`sdists`, and `isolated-installs` needs a populated environment to import pydantic; only
`kernel-isolation` survived, because its script imports nothing outside the standard library.

**Why it was undiscoverable.** There was no git remote until 2026-09-05. `ci.yml` was written in
Phase 0, has been cited and maintained since, and had **executed zero times**. Meanwhile
`poe ci-checks` was green on every run — because a developer's `.venv` and their untracked
`uv.lock` were both already sitting there. The gate passed by a path CI does not have, and the two
paths could not be compared while only one of them was ever taken. `uv lock --check` resolves 145
packages unchanged, so nothing had drifted: the resolution was correct and merely unshared.

This is `01`'s own rule one level out. *A green gate is not a working binary* was learned about a
binary nobody ran; this is a gate nobody ran **elsewhere**. A CI workflow that has never executed is
prose in exactly the sense `L6.12` means it — a directory of tests no task runs — except that it
looks more like a check than prose does, because it is written in YAML and lives where CI would find
it.

**Generalises to.** *A workflow that has never executed is a claim, not a check — and an artefact
whose absence only breaks a path nobody takes is invisible until someone takes it.* Anything the
gate needs must be in the repository, not in the environment of whoever last ran the gate; the test
is whether a clean checkout on a machine that has never seen this project can run it.

**Candidate home.** Two candidates, and they answer different halves. A fitness function could
assert that everything `ci.yml` and `release.yml` reference exists as a tracked file — cheap,
runs locally, would have caught exactly this. `CLAUDE.md` → *Quality gates* is the other: it already
says a green gate is not a working binary and could say that a gate that has run in one environment
is not a gate. The deeper point may belong wherever a phase declares itself complete — Phase 0's
exit was ticked with its CI never having run once, and no check asked.

### L7.1 — a task filed with its remedy already chosen had chosen the wrong one

**What happened.** Phase 6's close filed **6.33** from a diagnosis made in the moment: FF8's canary
assertion was failing under `pytest tests/docs tests/architecture`, a bisect named five `tests/docs`
modules that import the canary through `discover_for_reference()`, and the task was written as
*"stop them"* — with the remedy named, and even a shortlist of candidate seams. Doing it did not
work. Four of the five could be pointed at a restricted helper; the fifth was
`tests/unit/weft_cli/test_contract_reference.py`, which calls the open function five times and
**cannot stop**, because testing that function is what those tests are for.

There was never a set of callers to discipline. Any session that tests open discovery imports the
canary, so an in-process `sys.modules` guard could not survive — and the real repair was to the
*mechanism*: run the probe in a fresh interpreter, which FF8's own docstring had already argued for
in the sibling test beside it. The filed remedy was not merely incomplete; it was impossible, and
the only way to learn that was to attempt it.

**Why the filing was confident and wrong.** The bisect answered *"which files, run before FF8, make
it fail?"* — a real question with a real answer. It did not answer *"can each of them stop?"*, and
nothing in the failing output distinguished the two. A close-out review is exactly where this is
likely: the diagnosis is made with the evidence in hand and the fix is written from the same glance.

**Generalises to.** *A ledger task states the property that must hold, not the repair that will make
it hold* — a filed remedy is a hypothesis formed before anyone tried it, and it arrives carrying the
authority of the ledger. Where a filing does name a candidate fix, it says so as a candidate and
names what would falsify it.

**Candidate home.** `implement-ll` → *The two traps*, which already says a task written from one
instance narrows to that instance (`L6.13`); this is its sibling — a task written with its cure
prescribed narrows to a cure that may not exist. Possibly also `phase-step` → *Orient*, where a task
is read: a remedy in a task line is the previous author's guess, and the property above it is the
part that binds.

---

*Last drained 2026-08-25 at Phase 6's close — seventeen entries, five subjects, in
`lessons-archive.md` under that date, with their edges and the loop's own check answered: three of
this phase's defects would have been caught by rules already **Applied**, so all three moved to the
step that executes them rather than being restated.*

---
## When the queue is empty

That is the healthy state, and it means the last drain finished. What was learned lives in
`lessons-archive.md`, session by session, with the edges between entries — which is where the
question *have we been here before?* is answered, and where an on/off cycle becomes visible.
