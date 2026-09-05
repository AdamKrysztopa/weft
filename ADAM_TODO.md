# What's yours

Everything here needs an account, an authority, or a decision that isn't a task's to default.
Nothing on this list is blocked on more code.

Written 2026-08-26, at Phase 6's close. `docs/README.md` is still the source of truth for project
state — this file is only the subset that has your name on it.

---

## 1. Publish the release — the one thing Phase 6 leaves owed

Everything around it is done and proved. What is missing is the act of claiming names on a public
index, which reaches outside your machine and is irreversible, so it stayed with you.

**Do this first, before anything else on this list:** `weft-rag` is currently unclaimed. `weft` was
too, once. Names go.

### What's ready

- `.github/workflows/release.yml` publishes on a `v*` tag: 19 distributions in parallel, then
  `weft-rag` (it pins exact versions, so it must land after them), then the reproduction artefacts.
- Every artefact builds, and every one carries `LICENSE` and `NOTICE` (task 6.11).
- All twenty names checked against PyPI — nineteen free, and `weft` is why the release set is
  `weft-rag` (task 6.13, `docs/lessons.md` L6.33).
- The whole install-and-reproduce path is proved against a local index (tasks 6.13, 6.30).

### What you need to set up

1. **A PyPI account**, if there isn't one.
2. **Trusted publishing** for each project — the workflow declares `id-token: write` and uses no
   API token. On PyPI: *Your projects → Publishing → Add a new pending publisher*, once per
   distribution, with owner/repo and workflow filename `release.yml`. Twenty of them, and it is
   tedious; an API token in a secret is the alternative if you'd rather, but it means editing the
   workflow.
3. **Decide the tag.** `v0.1.0` matches what the distributions declare. The release set pins
   exactly, so the tag and the pins must agree.

### Then

```bash
git tag v0.1.0 && git push origin v0.1.0
```

and watch the run. Afterwards, two rows of Phase 6's exit criterion close that nothing else can
close — installing **from the package index** rather than a local one, and doing it in a single
`uvx` invocation. `docs/build-ledger.md` → *Phase 6's close* has the table.

**Worth knowing before you tag:** a published version is permanent. PyPI lets you yank a release but
never replace one, so a mistake costs a version number rather than being undoable.

---

## 2. Run G12 — the only open gate, and it blocks all of Phase 7

Phase 7 cannot start. Its four tasks all carry ⚠ and every one is live, which is the opposite of
Phase 6's, where each mark recorded something already settled.

**The question:** `03` → *Permissions* says an `ask`-class operation fails with no TTY and never
proceeds silently. An agent is never a TTY. So either a Phase 7 pack can never `overwrite` or
`destroy`, or something other than a TTY counts as consent. Which?

**Why it can't be defaulted, in one line each:** read strictly, the most useful thing an agent could
do — reindex a collection it just noticed was stale — is permanently out of reach. Read loosely, the
pack passes `--yes` on every call, which is `03`'s own sentence about `--yes` disarming the whole
table, with the human removed.

The session is written and waiting in `docs/05-grilling-sessions.md` → **G12**: the question, three
positions with the attack on each, and what to bring. Run it with the `grilling` skill.

**One prerequisite:** `01` requires the **`agentic-patterns`** skill to run before Phase 7's loop is
written, and G8 deliberately moved that handoff to this gate so it lands with real contracts to
reason about. Do that first — its human-approval material is this session's direct input.

---

## 3. The kernel boundary conversation

`weft-kernel` is **3,079 lines**, past fitness function 3's **2,800-line review trigger**. The
budget is 3,500 and is not close, so nothing fails — but the trigger exists to make this a
conversation before the ceiling is a crisis, and the rule is explicit that **the budget is never
edited in the pull request that grew it**.

It crossed during Phase 5 and Phase 6 added ~90 lines: the deprecation clock (task 6.5, ~66) and the
`PackStatus.PARTIAL` mechanism (task 6.29, ~25). Both were argued in place against `01` → *The
kernel boundary*'s own table, which puts "registration and versioning" and "the `plugins doctor`
computation" in the kernel's column.

**The question to settle:** is that table still the right boundary, or has the kernel taken on
something a pack should own? Either answer is fine; what isn't is drifting past 3,500 and
discovering the conversation is now urgent.

---

## 4. Set the 1.0 review date — G10 required one and there isn't one

G10 settled that 1.0 rests on **evidence**, with a **fixed review date** at which any outstanding
preconditions are *published* — naming what is missing and what it would take. The session's own
argument for keeping a date: *"a checklist whose rows never all tick is a release that never
happens."*

**No date is set anywhere in `docs/`.** The mechanism G10 built to stop 1.0 drifting is itself
drifting.

Six preconditions, in `docs/09-release.md` §2.2. Four are demonstrable today:

| Precondition | Where it stands |
|---|---|
| The store contract is not over-fitted to one backend | ✅ pgvector and Qdrant, neither stubbed |
| The kernel names no capability and stayed in budget | ✅ FF1 and FF3 green (see item 3) |
| Quality is a number someone else can reproduce | ✅ task 6.30 |
| A break is survivable by a pack author | ✅ G9's policy implemented |
| Nothing ships that was not meant to ship | ✅ FF10 green |
| The extension model works for someone who is not us | ⏳ needs the graph pack installed **from the index** — item 1 |

So five of six, and the sixth is item 1. Pick a date, write it into `09` §2.2.

---

## 5. Merge the branch

`phase-6-close-findings` has **12 commits** not on `main` — the five close-out tasks (6.31–6.35),
the phase-boundary move, and one lesson.

`main` currently holds Phase 6 as a single squash (`e94fa74`). The repository's convention is one
squashed commit per phase with the true per-task shas in the message
(`docs/build-ledger.md` → *Why the sha column is not optional*). These twelve are Phase 6's close
rather than a phase of their own, so either squash them onto `main` the same way or merge them
normally — your call, and I'd suggest squashing for consistency.

`gates-g10-g13` and `phase-6-detail` both still hold all 70 original commits, so nothing is lost
whichever way you go.

---

## Not yours — here so you don't wonder

These came up during Phase 6 and are already handled or already filed. No action needed.

- **The release set is `weft-rag`, not `weft`.** You chose it; `09` §1, the quickstart, the
  release-set README, the publish workflow and G10's decision-log row all carry the correction.
- **`ruff` is an optional extra of `weft-cli`** (`weft-cli[reference]`), needed only to regenerate
  the contract reference. It was an undeclared runtime dependency until task 6.7.
- **Live-API tests are opt-in.** `poe ci-checks` is deterministic on a machine with an
  `OPENAI_API_KEY` exported; set `WEFT_LIVE_API_TESTS=1` to run them (task 6.28, `CONTRIBUTING.md`).
- **The lessons queue holds one entry** (L7.1), which drains at Phase 7's close. That is the loop
  working, not a backlog.
- **The 2026-08-20 baseline is kept beside the new one** deliberately — it records what the
  workspace measured before G9's contract correction, and deleting it would erase the evidence for
  why the 2026-08-25 one exists.
