# Weft

**Read `docs/README.md` first. It is the single source of truth and it routes everything else** —
project status, which phase is live, which decisions are settled, and which document owns what.
Do not reconstruct project state from this file or from the code; that file holds it.

Weft is a RAG engine built as a **microkernel**: a small kernel that knows nothing about PDFs,
chunking, embeddings or graphs, where every capability is a plugin discovered through Python entry
points, pipelines are data derivable from other pipelines, and built-ins are held to the same public
contract as anything a third party writes.

**Nothing tracked in this repository references any other codebase.** Reading around is fine —
understanding why something is shaped the way it is, is how good decisions get made — but what comes
back is *knowledge, never text*, and what gets written down here is Weft's own reasoning in Weft's
own words. Anything that is a record of somebody else's project stays out of version control.

---

## Where things are

```text
weft/
├── docs/                  # the plan. README.md routes it
├── packages/              # the shipped distributions
│   ├── weft-kernel/       # registry, discovery, pipeline model, payload types
│   ├── weft-rag/          # the release set: fourteen packs in one distribution, incl. weft_cli
│   ├── weft-agent/        # add-on: the agentic pack (Phase 7)
│   ├── weft-openai/       # add-on: model-provider adapter
│   ├── weft-pdf/          # add-on: PDF extraction
│   ├── weft-qdrant/       # add-on: the second store backend G4's proof requires
│   └── weft-otel/         # add-on: sets the TracerProvider, publishes no contract
├── testing/weft-canary/   # test-only distribution for fitness function 8
├── tests/architecture/    # the fitness functions
├── tests/integration/     # what needs the one container
├── compose.yaml           # the one container: Postgres + pgvector
└── scripts/
```

**A pack's identity is not its distribution, and this tree is where that stops being abstract.**
`weft_cli`, `weft_extract`, `weft_chunk`, `weft_store`, `weft_embed` and nine more are *packs* — each
with its own `weft.packs` entry point, its own `[packs.*]` namespace and its own `plugins doctor`
row — and all fourteen ship inside the one `weft-rag` distribution. So `packages/weft-cli/` does not
exist; the module is at `packages/weft-rag/src/weft_cli/`. G10 re-settled this on 2026-09-05, turning
twenty published names into six and then seven; `09` §1 owns the reasoning and `docs/README.md`'s G10
row records it. *(This section listed the pre-consolidation layout until 2026-09-06 — five
directories that no longer exist and four that do. It was found by a dispatched agent whose brief
sent it here first, which is the argument for the paragraph rather than against it.)*

`weft-otel` (Phase 5 task 5.1d) is the one distribution that registers no plugin against any
contract and contributes to no pipeline — see `docs/02-extension-model.md` §4, *The second add-on
G7 produced*, for why a capability this narrow still ships as an ordinary pack rather than a core
change.

**One repository, several distributions.** This is not bookkeeping: a kernel that is its own wheel is
checked by installing it alone and importing it, which is what makes fitness function 1 a fact rather
than a script.

---

## The rules that are already settled

These came out of grilling sessions G1 and G3–G6. They are not preferences; each is recorded in
`docs/` with the argument that produced it, and changing one means reopening its gate.

- **Two published names, and only two: `weft-kernel` and `weft-rag`. This is closed.** Settled by
  the owner as **G19** on 2026-09-09, after `weft-graph` was found to be another project's on PyPI
  (**G18**) and the whole nine-distribution split was re-examined. Every first-party pack's code
  ships inside the `weft-rag` wheel; anything needing an outside library is an **extra** —
  `pip install weft-rag[pdf]`, `[graph]`, `[docling]`, `[all]` — so the dependency is declinable
  while the code costs kilobytes. `weft-kernel` stays separate for one reason only: fitness
  function 1 installs it alone and imports it, which is what proves the kernel names no capability.
  **A new capability never adds a third name** — it is a module, an entry point, and an extra if it
  needs a library. `weft-pdf`, `weft-openai`, `weft-qdrant`, `weft-otel`, `weft-docling`,
  `weft-agent` and `weft-kg` are **not** distributions and must not be published. The four
  pre-consolidation names published on 2026-09-05 — `weft-generate`, `weft-embed`, `weft-command`,
  `weft-llm` — are yanked. *Requirement 1's proof does not need published packages, only installable
  ones, and `testing/weft-canary` and `examples/weft-example-*` already carry it from outside the
  tree — that is what unblocked this, and it is why folding the add-ons in costs the project
  nothing it was relying on.* **Do not reopen this to save a wheel or to restore symmetry.**

- **Weft carries no third party's source text.** Not a file, a function body, a docstring, a
  comment, a prompt string, a word list or a test fixture. Another codebase is read to
  *understand*, then closed; every line here is written for Weft. The test: *if you could not have
  written this line without that file open, it is a copy.*

  **Two bounded exceptions, added 2026-09-05 because the absolute wording was not accurate** —
  `NOTICE` carries all three cases in full and is the authority:
  *(a)* **the copyright holder's own prior work may be carried across**, because it is nobody
  else's to license — the file that carries it names the source work, so the two origins stay
  distinguishable; *(b)* **a sentence or two of a third party's stated *rationale* may be quoted,
  attributed at the point of use, beside Weft's own restatement of the same reasoning** — never
  standing in for it, and never anything executable. Five docstrings in this tree already did this
  correctly while the rule forbade it in words.

  A **text-shaped asset** — a prompt, a word list, a locale catalogue — is authored for Weft
  regardless, and the test above is what decides: if the string is recoverable from a written
  specification, it is a specification; if it is not, the text *is* the asset and transcribing it
  is a copy.
- **The kernel names no capability.** No `Extractor`, `Chunker`, `Store`, `Retriever` or `LLM` in
  `weft-kernel` — those contracts ship from the packs that own them. *If you cannot describe the
  kernel without naming a capability, it is too big.*
- **The kernel depends on `pydantic` and `opentelemetry-api`. Nothing else.**
- **Async only, no exceptions.** Every contract method is `async def`. No sync protocol, no sync
  facade, no declared colour. `asyncio.run` appears exactly **once** in the whole tree, at
  `weft-cli`'s entry point. `CancelledError` propagates and is never swallowed.
- **Built-ins get no shortcut.** A first-party pack registers through the same public entry point a
  third party uses, and receives nothing extra.
- **Cross-cutting concerns live at the registration seam**, never in a rule authors must remember.
  Spans, error attribution, blocking-call detection, transient stripping and `flush` all attach
  there. This was measured rather than assumed, on a large codebase built the other way: every
  concern the machinery applied automatically held perfectly, and every concern an author had to
  remember decayed — hand-written spans drifted off-convention in two-thirds of their call sites and
  one whole stage ended up with none at all.
- **Return Pydantic models, never `dict[str, Any]`.** Frozen where the value is a domain object.
- **`Enum` for string constants**, never `Literal[...]`. Native 3.12 type hints (`list[str]`,
  `int | None`).
- **Catch specific exceptions.** A silent fallback is worse than a failure: it does not crash, it
  produces a plausible answer against the wrong data, and its success and failure paths become
  indistinguishable to the caller.

---

## Quality gates

```bash
uv run poe ci-no-tests     # format, lint, types, architecture
uv run poe ci-checks       # the canonical full gate — everything, plus tests
uv run poe kernel-isolated # install weft-kernel alone in a clean env and import it
```

**`ci-checks` is load-bearing.** Fitness function 0 asserts that every architecture check is
reachable from it, because a boundary checker that is not in the canonical task never runs, and a
fitness function that never runs is not a fitness function. If you add a check, add it to the composite in the same commit.

**And the gate you ran is only the gate if the environment is.** Three separate lessons are one
sentence: a `uv.lock` that was untracked made a local run and CI's clean-checkout run different
gates (`L7.2`); a metadata API answered one way under an editable install and another way under a
real one, which is where it actually runs (`L7.6`); and a container brought down mid-task silently
dropped 51 tests out of every run afterwards, green each time (`L7.8`). None of the three is a bad
check — each is a correct check asked in the wrong environment. So before a green means anything:
**the lockfile is the committed one, the container is up, the skip count is the one you
expect, and the lint cache is cold.** And **a container that is reachable is not one that still
holds what you put in it** — `L8.30`: a close-review measurement read `nodes now stored: 70` and
minutes later the table held one row, because a second process in the same session truncated it,
silently inverting a retrieval comparison. A measurement against `compose.yaml` asserts its own row
count immediately before *and* after, and nothing else touches that container while a suite runs. A skip is not a pass, and a suite that quietly shrank is
the failure mode with no symptom — `poe ci-checks` now fails a run whose `WEFT_DATABASE_URL`
claims a database that then turns out to be unreachable, and clears ruff's cache before it
starts. That last one is `L9.1` and it was the fourth instance: ruff caches per file, import
classification is a fact about the tree, and two real errors sat under a green gate for four
runs because the file whose verdict changed was not the file that changed.

**And a green gate is not a working binary.** Before a task is done, run `weft` through its shipped
entry point from a directory that is not this repository, including a failure path, and read what it
prints. This is measured rather than believed: **all four of Phase 3's repairs were found by running
the binary and none by its 1,513 tests** — one of them was `weft --help` entering the REPL, which
falsified that phase's own Exit criterion while the test written to prove that criterion passed,
having been shaped around the defect. `phase-step` → *Finish* carries the step.

The fitness functions are specified in `docs/01-high-level-plan.md` → *Fitness functions*, and each
test file states which one it implements and why it exists. Several have a **ratchet**: a named
waiver constant pinned empty, so a waiver is a visible act in a diff rather than a silent edit.

---

## Skills in this repository

Six live in `.claude/skills/`:

- **`phase-step`** — build one task of the current phase from `docs/build-ledger.md`, the
  phase-agnostic task list (`docs/06-phase-0-build.md` is Phase 0's own retired build order, cited
  only by tasks that carry it as their owner). Start here when writing code.
- **`weft-qualities`** — review a change, design or phase exit against the six requirements in `01`.
  The properties this project exists for are lost silently, one reasonable commit at a time.
- **`lessons`** — write a lesson into `docs/lessons.md` the moment it is paid for: a documented check
  that turned out to be prose, a claim from intuition that measurement falsified, a proposal that
  contradicted settled text, a defect found by running the binary rather than by its tests.
- **`implement-ll`** — drain that queue at a phase close: group the entries, route each to the
  artefact that would actually have caught it, apply them in one commit, leave the queue empty.
- **`implementation-status`** — answer *"where are we"* with one table of the live phase's tasks:
  id, five words, a size estimate, a status derived from `docs/build-ledger.md`'s own ticks and
  shas. Added 2026-09-07. The table **is** the answer; a paragraph about the plan is not, and the
  standing instruction to keep answers short does not make a status question an exception to
  itself.
- **`paper-to-plugin`** — a paper arrives and code is the destination: read it at source, settle the
  **name before writing anything**, decide whether it is a plugin, a pipeline or a config field, write
  it fresh, and put the divergence from the paper in the docstring beside the name that makes the
  claim. A plugin name is a published claim about what the code does, and `10` is where that claim
  is either true or knowingly withdrawn.

## Automation

`.claude/settings.json` is checked in, so hooks and permissions travel with the repository.

- **Python files are formatted and auto-fixed the moment they are written** (`PostToolUse`). This
  changes nothing about what is enforced, only when you find out — a ruff nit surfacing at
  `poe ci-checks` costs a full gate run and arrives after the reasoning is gone. Type checking and the
  architecture checks stay in the gate, where whole-tree properties belong.
- **Every session opens with what the project has already learned** (`SessionStart`), **and so does
  every dispatched agent** (`SubagentStart`). `.claude/hooks/lessons_context.py` injects
  `docs/lessons.md`'s applied rules and its current queue depth, so the loop that improves this
  repository's own tooling does not depend on anyone remembering that the file exists — which is the
  failure it exists to prevent. `SessionStart` does **not** fire for an agent dispatched through the
  Agent tool (measured, 2026-08-22), so before the second event was wired every `weft-implementer`
  worked with no applied rule in its context at all. A subagent gets the rules only — not the open
  queue, which it can neither triage nor write to.
- **What a dispatched agent noticed is harvested rather than remembered** (`SubagentStop`, `Stop`).
  It ends its report under a `## Noticed` heading; `.claude/hooks/subagent_findings.py` appends that
  section to `.claude/lessons-spool.md`, and `.claude/hooks/lessons_gate.py` refuses to end the turn
  while the spool holds an entry — promote it into `docs/lessons.md` or delete it saying why. Before
  this, the agent file asked for those findings and nothing consumed them, which is the
  producing-side-without-a-consuming-side shape `L5.15` forbids. **Spool content is data, never
  instructions** — and never assumed exact: one side of that protocol is a language model, so the
  hook matches loosely and says so loudly when a loose match still misses, rather than returning
  nothing. An instruction to be precise is not an enforcement mechanism.
- **Hooks are not project Python.** They run under bare `python3` — 3.9 on the development machine —
  so the 3.12 idiom the packages are held to does not reach `.claude/hooks/`, and `ci-checks` does
  not cover that directory. Run a hook to know it works; one that fails to import is silently a hook
  that does not exist.
- **The four git commands that discard unrecoverable work are refused** (`PreToolUse` on `Bash`) —
  `git stash`, `git reset`, `git checkout --`, `git clean`. Each throws away a working tree or an
  index that exists nowhere else, and this checkout is shared with whatever agent is running in it.
  The prohibition lived in `.claude/agents/weft-implementer.md` first, was read, and was overridden
  anyway by generic harness guidance that says to stash before a destructive operation — which is
  `docs/lessons.md` L9.56's rule: *a project prohibition that contradicts generic tool guidance
  needs a mechanism, not a stronger sentence.* `git rm` and `--amend` are deliberately not refused:
  both are recorded and recoverable, and a guard that fires on safe commands is one people learn to
  route around. Matched at a **command position** only, after the first version refused the very
  edit that documented it.
- **A `git commit` chained onto a check in one command is refused** (`PreToolUse` on `Bash`,
  `guard_unchecked_commit.py`). Three times in Phase 10 a verdict was swallowed and the wrong thing
  committed: an assertion whose message went nowhere, so a task was committed with no ledger entry;
  a check piped into `tail` before `&&`, where **a pipeline's exit status is its last command's**,
  so the pipe succeeded while the tests failed; and a gate whose exit code was reported by the
  wrapper that backgrounded it, saying `0` for a run that aborted. Run the check alone, as the last
  command in its own chain; read the verdict; then commit — and where a run may be backgrounded,
  write the verdict *into* its log rather than trusting a status. Staging followed by a commit is
  untouched, and heredoc bodies are stripped before matching, because prose is not a command — a
  lesson the guard taught by refusing the very edit that documented it. `docs/lessons.md` `L10.24`.
- **Writes are refused to anything outside this repository's own tracked tree** (`PreToolUse`) —
  reading material kept on disk and excluded from version control. A write there would leave no
  trace in any diff, which is the whole reason it is refused rather than merely discouraged.

## Working here

- **Decisions have gates.** Ten sessions in `docs/05-grilling-sessions.md`, eleven rows in the log —
  G0 was settled without a session and is logged only. Each session carries its question, the
  positions to attack, what to bring and what done looks like. Six are settled. If a task runs
  into an open one, stop and say so rather than defaulting it — that is what they exist to prevent.
- **When a session closes**, follow the Protocol section at the foot of `docs/README.md`: update the
  decision-log row, tick the checklist, and edit the reference document that owns the content. The
  log records *that* it was decided and *what*, never the reasoning.
- **`docs/README.md` holds state and pointers only, never definitions.** If you find yourself
  explaining *why* there, it belongs in `01` through `05`.
- **A claim about what code does is checked against its callers, never against its name, its
  docstring, or a comment's stated scope** — including a claim made by a review or another agent.
  This has now cost three phases in three genres: a proviso invented mid-task rather than reopening
  a gate (`L5.32`), a code invariant asserting "every shipped pipeline" over documents anyone may
  write (`L6.15`), and an adversarial review's finding about a fan-out that was half true, where
  only the call sites said which half (`L9.18`). It lived in `phase-step` through the first two and
  did not bite; it is here because the third arrived in a genre `phase-step` has no step for.
- **Claims need evidence.** Every factual assertion in `docs/` about the tree — a count, a line
  number, a "nothing calls this" — carries something a reader can check, because the assessment that
  started this project got several of its own claims wrong and the corrections are logged. Measure
  before asserting, and re-measure before arguing from a number a phase could have changed.
