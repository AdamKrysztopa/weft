# Plan — twenty distributions become six

> **OUTCOME, 2026-09-05: not done, and the reason is measured rather than argued.** The plan below
> was built far enough to answer itself — a real bundled wheel, installed into a clean environment,
> with the binary run against it. It works mechanically and it breaks a published control. **G10
> stands.** What was actually wrong was the release *process*, and that is fixed (`max-parallel: 1`,
> commit `2d91131`). Read §"What the experiment found" at the foot before reopening this.

**Status: proposed and rejected on evidence, 2026-09-05. G10 was reopened and stands.** G10 chose
"independent semver per distribution plus a named release set"; that is what shipped, and its first
contact with a real index found the cost. The decision-log row in `README.md` and `09-release.md` §1
are the documents that own the outcome — this file is the plan for getting there and is deleted when
the ledger tasks it names are ticked.

---

## Why

Measured 2026-09-05, from the twenty `pyproject.toml` files rather than from the design:

> *Corrected after the experiment: this said **eleven** and listed `weft-store` among them. It has
> `psycopg[binary]>=3.2` and `pgvector>=0.3`. The regex that produced the original list stopped at
> the first `]`, and `psycopg[binary]` contains one. The corrected number is **ten**, and the
> correction matters: `weft-store` is a heavy optional backend, not a dependency-free pack.*

**Ten of the twenty declare no external dependency at all** — `weft-chunk`, `weft-command`,
`weft-embed`, `weft-enhance`, `weft-extract`, `weft-generate`, `weft-index`, `weft-llm`,
`weft-prompts`, `weft-retrieve`. Installing without one of these avoids nothing. They are separate
distributions for architectural symmetry, and symmetry is not a user-visible benefit.

Six carry a dependency somebody might genuinely decline: `psycopg`+`pgvector` (`weft-store`),
`openai`, `pypdf`+`pdfplumber`, `qdrant-client`, `opentelemetry-sdk`, and the kernel's own declared
floor of `pydantic` + `opentelemetry-api`.

**The cost was not theoretical.** `v0.1.0` asked PyPI to create nineteen new projects in parallel
and PyPI refused fifteen of them (`429 Too many new projects created`). Twenty names is also twenty
trusted-publisher forms, twenty version numbers to keep coherent, and twenty rows for
`test_release_set.py` to hold in agreement. `lessons.md` L7.3 carries the incident.

## The target

**Six published names.**

| Name | Contents | Why it stays separate |
|---|---|---|
| `weft-kernel` | unchanged | **Fitness function 1.** Installing the kernel alone and importing it is what proves it names no capability. `CLAUDE.md`: *"what makes fitness function 1 a fact rather than a script."* Bundling it would demote that check, which is the one thing this plan refuses to trade |
| `weft-rag` | the fourteen: `command`, `extract`, `chunk`, `clean`, `embed`, `enhance`, `index`, `store`, `retrieve`, `generate`, `llm`, `prompts`, `eval`, `cli` | The default install. `pip install weft-rag`, and the `weft` command works |
| `weft-openai` | unchanged | `openai>=3.1` |
| `weft-pdf` | unchanged | `pypdf`, `pdfplumber` |
| `weft-qdrant` | unchanged | `qdrant-client>=1.12` |
| `weft-otel` | unchanged | `opentelemetry-sdk` |

**The name is `weft-rag`, not `weft`, and that does not change.** `weft` is taken on PyPI at the
very version this set declares (`lessons.md` L6.33). What a user *types* is still `weft`, because
that is `weft-cli`'s console script.

## What does not change, and this is the point

- **The Python packages do not move.** `weft_chunk`, `weft_retrieve` and the rest stay exactly
  where they are, importing exactly what they import. A single wheel may ship many top-level
  packages; what changes is how the code is *wheeled*, not how it is written. No import in the tree
  changes. No test changes because of this.
- **Every pack still registers through the public entry point.** The fourteen entry points move
  into one `pyproject.toml`; the mechanism is untouched, and a third-party pack is discovered by the
  identical path. Requirement 4 holds.
- **The extension model is untouched.** A third-party pack was never a member of our release set. It
  installs beside `weft-rag` exactly as `weft-qdrant` does.
- **The workspace stays as it is.** `packages/*` remain `uv` workspace members so the tree is still
  developed as separate units and the boundary checks still have separate units to check.

## What is genuinely given up

Stated plainly, because the argument is only honest if the cost is on the table:

1. **Independent semver for the fourteen.** They versioned separately (`weft-command` at 2.1.0,
   `weft-store` at 2.0.0, eleven at 1.0.0) and will now share `weft-rag`'s version. G9's deprecation
   machinery was largely built to manage skew *between* these packs; most of that skew stops
   existing. Contract versions (`STORE_CONTRACT_VERSION` and the rest) are a separate axis and are
   **not** affected — a pack outside the bundle still checks them.
2. **Per-pack isolated-install proof.** Task 6.6 generalised fitness function 1 to every published
   distribution. Fourteen of them stop being separately installable, so that check narrows to the
   six. What replaces it for the fourteen is an import-graph assertion, which is weaker and must be
   labelled weaker rather than quietly counted as the same coverage.
3. **Four already-published names become vestigial.** `weft-command`, `weft-embed`, `weft-generate`
   and `weft-llm` published at `v0.1.0` before the rate limit stopped the rest. PyPI cannot delete a
   project. They stay claimed, receive no further versions, and their existence is recorded here so
   that a future reader does not think they were lost.

## The ledger tasks

Each states the property that must hold, not the repair — `lessons.md` L7.1.

- **C1** — `weft-rag` ships the fourteen packs' code and their entry points, and a wheel built from
  it imports every one of them. *(The mechanical core. Everything else follows it.)*
- **C2** — the fourteen `pyproject.toml` files no longer declare a distribution, and the workspace
  still resolves and still runs the gate.
- **C3** — `release.yml`'s matrix publishes six names, and fitness function 10 compares those six
  against the workspace members that do not opt out — the two-sources-that-can-disagree property
  survives the change rather than being satisfied trivially.
- **C4** — `test_release_set.py` holds the new shape: exact pins for the four optional packs and the
  kernel, and no pin for code that now ships inside the set.
- **C5** — the isolated-install check covers the six, and the fourteen are covered by a stated,
  explicitly weaker import-graph assertion.
- **C6** — `09-release.md` §1 and `README.md`'s G10 row carry the re-settled decision; this file is
  deleted.

## Sequencing

C1 first and alone — it is provable in isolation by building the wheel and importing from it in a
clean environment, which is the only evidence that the whole plan is sound. If C1 does not hold,
nothing below it matters. C2 follows. C3–C5 are the checks catching up with the shape and can go in
one commit. C6 last, because a decision record written before the thing works is a claim.

**No publishing until all six are green**, and no retry against PyPI until its window has been left
alone for hours — L7.3.


---

## What the experiment found

C1 was built rather than reasoned about: `weft-rag` was made to ship the fourteen packs'
code and entry points, the wheel was built, installed into a clean virtualenv, and the binary run.
This is the whole value of doing C1 first and alone.

**It works mechanically.** One wheel, fourteen top-level packages, twelve `weft.packs` entry points
and the `weft` console script. `weft plugins list` discovers and registers all twelve. The Python
packages never moved, no import changed, and no test changed — the affordability claim was correct.

**And it destroys `weft plugins doctor`.** Every row reports the same distribution:

```
weft-rag 0.1.0: active (6 contributed)
  disclosure: not disclosed
weft-rag 0.1.0: partial (28 contributed)
  disclosure: not disclosed
```

Two losses, and the second is the one that decides it:

1. **Pack identity collapses.** `weft plugins list` and `doctor` reported *which pack* contributed
   what, because a pack's identity **was** its distribution name. Fourteen rows saying `weft-rag`
   answer nobody's question. `03-cli.md` owns that command surface and describes it otherwise.
2. **Task 6.31's disclosures stop working** — every row reads `disclosure: not disclosed`.
   That task exists because 6.10 published a page telling readers `weft plugins doctor` names what
   each distribution discloses about network, filesystem and subprocess access, and one pack in
   twenty declared one. Disclosures are keyed *per distribution*; collapse the distributions and the
   control has nothing left to distinguish. **This is a security-adjacent published control, built
   three commits before this experiment, silently disabled by repackaging.**

**So the honest cost of consolidation is not packaging — it is that `distribution` is doing two
jobs.** It is both "the thing PyPI installs" and "the pack's identity in every operator-facing
surface". Bundling separates those two meanings and nothing in the tree is ready for that. Making it
ready is a real refactor — a pack id distinct from its distribution, threaded through discovery, the
seam, `doctor`, and the disclosure mechanism — and it lands near G7 and G9 rather than beside them.

**Weighed against what was actually hurting:** twenty PyPI projects cost one bad afternoon, a rate
limit, and twenty pending-publisher forms — a **first-release** cost that does not recur, and it is
already mitigated by `max-parallel: 1`. Trading a live per-pack disclosure control for that is a bad
trade, and it only looks like a good one from the day the rate limiter bit.

**Two corrections this experiment also produced**, both worth keeping:

- The dependency measurement this plan was built on was **wrong**. A regex reading
  `dependencies = [...]` stopped at the first `]`, and `psycopg[binary]>=3.2` contains one — so
  `weft-store` was recorded as having no external dependency when it has two, one of them heavy.
  Ten distributions have no external dependency, not eleven. Measure with a parser, not a regex,
  which is `CLAUDE.md`'s own *measure before asserting* applied to the measuring instrument.
- `weft_cli.cli` hardcoded `_DISTRIBUTION = "weft-cli"` and `weft --version` dies with
  `PackageNotFoundError` if that name is ever not the installed distribution. Latent today, real the
  moment anything repackages. Not fixed here, because the fix belongs with whoever separates pack
  identity from distribution — filed rather than patched around.

**If this is ever reopened**, the first task is not packaging. It is: *does a pack have an identity
separate from the distribution that ships it?* Answer that, and consolidation becomes ordinary work.
Leave it unanswered and consolidation quietly removes controls.
