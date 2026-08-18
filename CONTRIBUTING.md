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

**Claims about the reference need evidence.** Weft's plan asserts a lot about `a prior project`, and every
assertion carries a `path:line`. This is not pedantry: the review that started this project got
several of its facts wrong, and the corrections are logged in
[`docs/reference/study/10-doc-corrections.md`](docs/reference/study/10-doc-corrections.md). Measure, then
assert.

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
  This is the single most load-bearing lesson from the reference, where every concern the machinery
  applied automatically held and every concern an author had to remember decayed.
- **No `dict[str, Any]` returns**, no `Literal[...]` where an `Enum` belongs, no bare
  `except Exception`, no silent fallback.

---

## Working on it

```bash
git clone <this repo> && cd weft
uv sync
uv run poe ci-checks
```

Optionally, for reading the reference and lifting from it:

```bash
git clone <a prior project> ../a prior project   # the `reference` symlink expects a sibling checkout
```

The symlink is untracked and **no build, test or packaging step may read through it**. If a check
starts depending on the reference being present, that check is wrong.

### Gates

```bash
uv run poe ci-no-tests      # format, lint, types, architecture
uv run poe ci-checks        # the canonical full gate — run this before you push
uv run poe kernel-isolated  # install weft-kernel alone in a clean env and import it
```

**If you add an architecture check, add it to `ci-checks` in the same commit.** Fitness function 0
asserts that membership and will fail otherwise. It exists because the reference shipped a 316-line
boundary checker that was not in its canonical task and therefore never ran, on a tree with eleven
violations.

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

## Learning from the reference, without copying it

**No source text from any other codebase enters this repository.** Not a file, not a function, not a
docstring, not a comment, not a prompt string, not a word list. There is no attribution procedure
here because there is nothing to attribute: see [`NOTICE`](NOTICE).

What the reference is for is *understanding*. Read it, work out why something is the way it is, then
close it and write ours. [`docs/04-reference-inventory.md`](docs/04-reference-inventory.md) is a record of
what was worth understanding — an ordering that was learned from broken output, a taxonomy that
turned out to be the only usable retry axis, a guard that records a paid-for bug. Carry the
*knowledge* across in your own words and implement it against Weft's contracts, which are not the
reference's contracts anyway.

The practical test, and it is not a formality: **if you could not have written this line without the
reference's file open, it is a copy.** Reviewers check for this.

---

## Reporting security issues

Do not open a public issue. See [`SECURITY.md`](SECURITY.md), which also explains — honestly — what
Weft's plugin model does and does not protect you from.

---

## Conduct

[`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md) applies to every space this project uses.
