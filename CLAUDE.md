# Weft

**Read `docs/README.md` first. It is the single source of truth and it routes everything else** —
project status, which phase is live, which decisions are settled, and which document owns what.
Do not reconstruct project state from this file or from the code; that file holds it.

Weft is a RAG engine built as a **microkernel**: a small kernel that knows nothing about PDFs,
chunking, embeddings or graphs, where every capability is a plugin discovered through Python entry
points, pipelines are data derivable from other pipelines, and built-ins are held to the same public
contract as anything a third party writes.

`a prior project` is a **parts reference, not a baseline** — and what it donates is **knowledge, never text**.
It is a sibling checkout reached through the untracked `reference` symlink, and it is used for one thing:
understanding why something is shaped the way it is, per `docs/04-reference-inventory.md`. Nothing in the
build, tests or packaging may read through that symlink. The finished audit of the reference lives here,
in `docs/reference/`, and is frozen.

---

## Where things are

```text
weft/
├── docs/                  # the plan. README.md routes it; reference/ is the frozen audit
├── packages/              # the shipped distributions
│   ├── weft-kernel/       # registry, discovery, pipeline model, payload types
│   ├── weft-cli/          # the only driving adapter, and the only asyncio.run
│   ├── weft-extract/      # first-party pack: publishes the Extractor contract
│   ├── weft-chunk/        # first-party pack: publishes the Chunker contract
│   ├── weft-store/        # first-party pack: publishes the Store contract family
│   ├── weft-embed/        # first-party pack: publishes the Embedder contract
│   └── weft-otel/         # first-party pack: sets the TracerProvider, publishes no contract
├── testing/weft-canary/   # test-only distribution for fitness function 8
├── tests/architecture/    # the fitness functions
├── tests/integration/     # what needs the one container
├── compose.yaml           # the one container: Postgres + pgvector
└── scripts/
```

`weft-embed` is a fifth distribution the original plan did not anticipate, and the reasoning is
forced rather than aesthetic: G4 forbids a store from embedding, G2 has not placed the embed step,
and a walking skeleton must not depend on a model download or an API key. See `docs/06-phase-0-build.md`
step 8.

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

- **Weft is original work. No source text from any other codebase enters this repository** — not a
  file, a function body, a docstring, a comment, a prompt string, a word list, a regex or a test
  fixture. The reference is read to *understand*, then closed; every line here is written for Weft. The
  test: *if you could not have written this line without the reference's file open, it is a copy.* There
  is no attribution procedure because there is nothing to attribute — see `NOTICE`.
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
  there. The reference measured this precisely: every concern its machinery applied automatically held;
  every concern an author had to remember decayed.
- **Return Pydantic models, never `dict[str, Any]`.** Frozen where the value is a domain object.
- **`Enum` for string constants**, never `Literal[...]`. Native 3.12 type hints (`list[str]`,
  `int | None`).
- **Catch specific exceptions.** A silent fallback is worse than a failure — the reference shipped one
  whose success and failure paths were indistinguishable, and it is in the inventory as a thing not
  to lift.

---

## Quality gates

```bash
uv run poe ci-no-tests     # format, lint, types, architecture
uv run poe ci-checks       # the canonical full gate — everything, plus tests
uv run poe kernel-isolated # install weft-kernel alone in a clean env and import it
```

**`ci-checks` is load-bearing.** Fitness function 0 asserts that every architecture check is
reachable from it, because the reference shipped a boundary checker that was not in its canonical task
and therefore never ran. If you add a check, add it to the composite in the same commit.

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
- **`reference-audit`** — what does the reference have that Weft does not yet? Separates *missed* from *not
  due*, runs the check in reverse to catch anything that arrived from the leave-behind list, and
  checks that nothing was copied. Use before declaring a phase complete.
- **`lessons`** — write a lesson into `docs/lessons.md` the moment it is paid for: a documented check
  that turned out to be prose, a claim from intuition that measurement falsified, a proposal that
  contradicted settled text, a defect found by running the binary rather than by its tests.
- **`implement-ll`** — drain that queue at a phase close: group the entries, route each to the
  artefact that would actually have caught it, apply them in one commit, leave the queue empty.
- **`reference-lift`** — port one catalogued idea correctly: verify at source, work out what the asset
  actually is (an ordering, a distinction, a taxonomy, a measurement, a scar), close the file, and
  write it fresh in the right distribution with the recorded corrections applied.

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
- **Writes are refused to `docs/reference/` and to anything resolving through the `reference` symlink**
  (`PreToolUse`). The first is a frozen snapshot the plan cites ~90 times; editing it destroys the
  evidence rather than correcting it. The second is a *different repository*, not under version
  control, so a write there would leave no trace.

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
- **Claims about the reference need evidence.** Every factual assertion in `docs/` about `a prior project`
  carries a `path:line`, because the assessment that started this project got several of them wrong
  and the corrections are logged. Measure before asserting.
