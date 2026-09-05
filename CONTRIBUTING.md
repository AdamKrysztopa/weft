# Contributing to Weft

Weft is pre-alpha: the architecture is settled, the code is not yet written. That makes this a good
moment to contribute and an unusually opinionated one to contribute to, because most of the design
questions you might want to open have already been argued out and recorded.

**Start with [`docs/README.md`](docs/README.md).** It holds the current phase, the decision log, and
which document owns what. Nothing here repeats it.

---

## Before you write code

**Check whether your change touches an open decision.** There are ten architecture gates in
[`docs/05-grilling-sessions.md`](docs/05-grilling-sessions.md); six are closed and four are not. Each
records its question, the positions to attack, what evidence to bring, and what "done" looks like.

- **Touches a closed gate?** The decision stands. If you think it's wrong, say so in an issue with
  the argument and the evidence — a settled decision found wrong is reopened with a date and a
  reason, never quietly edited.
- **Touches an open gate?** Stop and open an issue rather than defaulting it. Defaulting these is
  precisely what the gates exist to prevent, and a PR that silently answers one will be asked to
  back it out.

---

## The rules that are not up for negotiation in a PR

Each of these came out of a gate and is recorded with its argument. Changing one is a decision-log
entry, not a code review.

- **The kernel names no capability.** No `Extractor`, `Chunker`, `Store`, `Retriever` or `LLM` in
  `weft-kernel` — those contracts ship from the packs that own them.
- **The kernel depends on `pydantic` and `opentelemetry-api`, and nothing else.**
- **The kernel has a line budget** — 3,500, review trigger at 2,800. It is changed only by a dated
  decision-log entry, and never in the same pull request that grew the kernel.
- **Async only.** Every contract method is `async def`. There is no sync protocol, no sync facade,
  and exactly one `asyncio.run` in the tree, at `weft-cli`'s entry point. `CancelledError`
  propagates.
- **Built-ins get no shortcut.** A first-party pack registers through the same public entry point a
  third party uses.
- **Cross-cutting concerns go to the registration seam**, never into a rule authors must remember.
  This is the single most load-bearing lesson this project has learned: every concern the machinery
  applied automatically held, and every concern an author had to remember decayed.
- **No `dict[str, Any]` returns**, no `Literal[...]` where an `Enum` belongs, no bare
  `except Exception`, no silent fallback.

---

## Working on it

```bash
git clone <this repo> && cd weft
uv sync
uv run poe ci-checks
```

### Gates

```bash
uv run poe ci-no-tests      # format, lint, types, architecture
uv run poe ci-checks        # the canonical full gate — run this before you push
uv run poe kernel-isolated  # install weft-kernel alone in a clean env and import it
```

**The gate is deterministic, and reaching a live service is opt-in.** Four integration modules can
call the OpenAI API. They skip unless **both** `OPENAI_API_KEY` and `WEFT_LIVE_API_TESTS` are set —
two variables on purpose: having a credential exported for other work is not asking for a network
run, and `poe ci-checks` must mean the same thing on your machine as on a runner with no account.
`09` §4.3's V5 is the requirement ("a deterministic subset that runs in CI with no credentials and
no network"); `tests/architecture/test_the_gate_is_decidable.py` is what holds every such module to
it. To run them:

```bash
WEFT_LIVE_API_TESTS=1 uv run pytest tests/integration -q
```

**If you add an architecture check, add it to `ci-checks` in the same commit.** Fitness function 0
asserts that membership and will fail otherwise. It exists because a real project once shipped a
316-line boundary checker that was not wired into its canonical task and therefore never ran, on a
tree with eleven violations.

Some checks carry a **waiver constant pinned empty**. Adding a name to one is a deliberate, visible
act in a diff; that is the whole point of the pattern, so do not treat it as a quick unblock.

### Tests

- `tests/architecture/` — the fitness functions. Each states which one it implements and why it
  exists.
- Everything else mirrors the package it tests. AAA: arrange, act, assert, one block each.
- Name them `test_<what>_<condition>_<expected>`.
- Cover the happy path, one edge case, one error case. Mock external services; a unit test never hits
  a live model or database.

---

## Pull requests

- One concern per PR. If the diff needs the word "also", it is probably two PRs.
- Say which gate or fitness function your change relates to, if any.
- If you changed something a document owns, edit that document in the same PR — the plan and the code
  are meant to be true about each other.
- Green `ci-checks` before review. It is fast.

Commit messages: a short imperative subject, then a body that says **why**, not what. The diff
already says what.

---

## Learning from prior art, without copying it

**No third party's source text enters this repository.** Not a file, not a function, not a
docstring, not a comment, not a prompt string, not a word list.

Two bounded exceptions, and [`NOTICE`](NOTICE) states all three cases precisely: material written by
this project's own author *before* this project may be carried across, and the file carrying it says
so; and a sentence or two of a third party's stated **rationale** may be quoted, attributed at the
point of use, sitting beside our own restatement of the same reasoning rather than instead of it.
Nothing executable is ever carried that way.

Reading prior art is for *understanding*. Read it, work out why something is the way it is, then
close it and write ours — an ordering learned from broken output, a taxonomy that turned out to be
the only usable retry axis, a guard that records a paid-for bug. Carry the *knowledge* across in
your own words and implement it against Weft's own contracts.

The practical test, and it is not a formality: **if you could not have written this line without
someone else's file open, it is a copy.** Reviewers check for this.

---

## Reporting security issues

Do not open a public issue. See [`SECURITY.md`](SECURITY.md), which also explains — honestly — what
Weft's plugin model does and does not protect you from.

---

## Conduct

[`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md) applies to every space this project uses.
