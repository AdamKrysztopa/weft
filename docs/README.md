# Weft — control

**This is the single source of truth. Open this file first; it routes everything else.**

Weft is a RAG engine being rebuilt from scratch: a small kernel that knows nothing about PDFs,
chunking, embeddings or graphs, where every capability is a plugin discovered through Python entry
points, pipelines are data derivable from other pipelines, and built-ins are held to the same
public contract as anything a third party writes. `a prior project` is a parts reference, not a baseline.

> **The rule that keeps this file true.** It holds **state and pointers only — never definitions.**
> Identifiers live here (phase names, gate IDs, statuses, dates). Content lives in exactly one
> reference document and is linked, never restated. This is not tidiness: `a prior project` kept its
> supported file formats in two places, they could drift, and the same file format was accepted at
> upload and had no extractor at extraction time. A control file that paraphrases the plan
> reproduces that bug at the level of the plan itself.
>
> *(Corrected 2026-08-10: the anecdote originally said the two lists "drifted". They have not — they
> are identical today, 17 entries each. The accept-then-fail consequence is real, by a different
> mechanism: `.doc`/`.ppt` are declared unconditionally while their extractors are inserted
> conditionally on optional dependencies. The argument for single-sourcing is unaffected and now
> rests on a fact. See `reference/study/10-doc-corrections.md` A1, A2.)*

---

## Status

| | |
|---|---|
| **Phase** | Phase 5 — The independence test |
| **Blocked by** | **Nothing, and Phase 5's build is complete** — every task 5.1a–5.7 closed, plus two the phase added to itself (`S7`, `S8`). **Its exit criterion was run and not met**: the graph pack was built with zero edits under `packages/`, and its author filed three core-change requests, two of which stop the pack doing what `02` §4's table says it does. `01` calls that *"a Phase 5 failure and a design finding, not a feature request"*, which is what the phase exists to produce — see `build-ledger.md` → 5.7 for the full assessment. **G13 is proposed and Open** and carries all three findings |
| **Next action** | **Run G13** — the derived-participant seam (`README.md` → *Decision log*). It is the only thing standing between the graph pack and `02` §4's own table, and it should settle before Phase 6 publishes the contracts it would change. Phase 6 is separately blocked by **G10**. Do **not** treat Phase 5's exit as met: `02` §4's *"`weft delete` fans out to it in-command"* is false against the code as it stands, and `09` §5.2's release checklist consumes that promise |
| **Open decisions** | 3 of 14 — G0, G1, G2, G3, G4, G5, G6, G7, G8, G9 and G11 settled; G10, G12 and **G13** open. G0 is logged only; every other row has a session in `05` |
| **Updated** | 2026-08-22 |

G2's close resolved the **three places Phase 0 could accidentally settle it**, each of which `06`
had fixed to a minimal reversible choice: embedding **stays a stage** (G4 forbids a store to embed,
so it was never G2's to choose); a pipeline **stays an ordered list**, now with derivation, slots and
declared constraints on top of it; and two packs claiming one name **stays a refusal**, relaxed only
by an operator's pin in `weft.toml`. All three moved in the direction `06` required — relaxing a
refusal rather than tightening a silence. It also cleared `11`'s three filed questions and one of
`11`'s deferred-gate blockers. Both of Phase 5's gates closed on 2026-08-21 — **G7** without a bus, **G9** without a new declaration
mechanism and without a kernel line. The next gate is **G10**, at Phase 6, and `09` §2.3's five
dependencies are now answered rather than open.

---

## Execution path

Gates and phases interleaved in the order they must happen. Tick as you go; this checklist is the
project's position.

**Phase 0 — Walking skeleton**

- [x] **G1** Kernel boundary
- [x] **G5** Stage payload typing
- [x] **G6** Sync or async core
- [x] **G4** Store contract and capabilities *(before store work)*
- [x] **G3** Plugin trust model *(before discovery ships)*
- [x] Phase 0 build — eleven steps in `06-phase-0-build.md`, tracked task by task in `build-ledger.md`
- [x] **Exit:** a plugin in a separate installed package works with zero edits to core

**Phase 1 — Pipelines as data**

- [x] **G2** Pipeline derivation semantics
- [x] Phase 1 build — eighteen tasks in `build-ledger.md` → Phase 1
- [x] **Exit:** the KeyBERT case works from configuration, no copy of the parent *(and FF11 green)*

**Phase 2 — Retrieval and generation**

- [x] **Prerequisite V1–V3** — corpus, question set with ground truth, repeated baseline (`09` §4)
- [x] Phase 2 build *(no gate)*
- [x] **Exit:** the router discovers strategies from the registry, not an enum *(and FF12 green)*
- [x] **G11** Kernel error text — catalogue or literal *(settled 2026-08-18: literal, and the catalogue is retired; turns on FF12)*

**Phase 3 — The CLI**

- [x] **G8** Is the REPL agentic *(settled 2026-08-18: no, and never — the agent is a pack, and it is Phase 7)*
- [x] Phase 3 build
- [x] **Exit:** a plugin's command appears in `--help` without core knowing it exists *(task 3.8, proven against the real binary in a throwaway venv)*

**Phase 4 — Evaluation and observability**

- [x] Phase 4 build *(no gate)* — eleven tasks, 4.0–4.10, closed 2026-08-20
- [x] **Exit:** the tool generates its own comparison across two derived pipelines *(task 4.9,
  closed 2026-08-20 — see `docs/build-ledger.md`'s 4.9 entry for the transcript, the two real
  defects found and fixed proving it, and the deliberate failing run; made permanent and
  repeatable the same day by `tests/integration/test_phase4_exit_evaluation_comparison.py`,
  reusing `test_cli_end_to_end.py`'s own skip construct)*

**Phase 5 — The independence test**

- [x] **G7** Event bus or explicit extension points *(settled 2026-08-21: explicit points only, no bus — and the hole it found is closed by two store-family Protocols)*
- [x] **G9** Contract versioning and deprecation *(settled 2026-08-21: per-contract semver bound to distribution versions, two-audience classification, stored schemas a second axis in the data, enforcement is the dependency specifier, prose unpromised but a structured channel promised in its place; turns on FF6)*
- [x] Phase 5 build — sixteen tasks, 5.1a–5.7, closed 2026-08-22, including two the phase added to itself (`S7`, `S8`)
- [ ] **Exit:** the graph pack is built by someone who never touches core *(run 2026-08-22 and **not met** — the pack needed no core edit to be **written**, and needs three to **work as `02` §4 specifies**. Task 5.7 carries the assessment; **G13** carries the question)*

**Phase 6 — Release**

- [ ] **G10** Release and support policy *(after G9)*
- [x] Prerequisite V4–V6 complete — metric semantics, providers and cost, a persisted baseline run *(V4 task 4.3, V5 task 4.7, V6 task 4.8 — closed 2026-08-20; the checklist item this feeds, "the baseline run is published with the release" in `09` §5.2, stays unticked, since publication is Phase 6's)*
- [ ] Phase 6 build *(turns on FF10)*
- [ ] **Exit:** a stranger installs the release from the index and reproduces the published baseline

**Phase 7 — The agent** *(added 2026-08-18 by G8, logged as `S3`)*

- [ ] **G12** Permissions when the caller is never a TTY *(this is where the `agentic-patterns` handoff lands)*
- [ ] Phase 7 build
- [ ] **Exit:** the agentic pack installs from the index and drives a corpus end to end through the published command surface, with no edit to core

Each phase's gates, required reading, reference lifts and exit criterion are specified in
`01-high-level-plan.md` → **Phases**. That section is the execution script; this is its state.

---

## Decision log

The authoritative status of every decision. The *content* of each session — the question, the
positions to attack, what to bring, what done looks like — lives in `05-grilling-sessions.md`.

| ID | Decision | Status | Outcome | Settled |
|---|---|---|---|---|
| **G0** | Project name | **Settled** | **Weft.** The warp is the fixed frame on a loom, the weft is every thread through it. Polish *wątek* also means thread and narrative topic | 2026-08-10 |
| **G1** | Kernel boundary — what is kernel vs first-party pack | **Settled** | The kernel expresses, loads and runs contracts it knows nothing about and performs no RAG work — no capability contract, no capability name, two dependencies, a stated budget; a plugin gets one passport carrying `tenant_id` and `require()`, config at construction; packs get a `packs:` settings namespace. Specified in `01` → *The kernel boundary* | 2026-08-10 |
| **G2** | Pipeline derivation semantics | **Settled** | A pipeline is an **ordered list** and resolution *checks* the order rather than solving it, refusing with the positions that would be legal. Ordering constraints are the mirror of `requires`/`provides` — a plugin declares what it needs `intact` and what it `destroys`, published as namespaced properties, `destroys` mandatory at registration — so no plugin ever names another. Stage 0 becomes **applicability** routed at the seam, which also means a per-node path needs no branch. `extends` takes one parent at any depth; all four operators are strict; they apply in written order. Packs contribute only into **declared slots**, ordered by declaration then by distribution name, with unplaced contributions recorded, not silent. Name collisions are refused at registration and resolved by an operator pin. Language is a fact on the node; `vars` carry the decision half and never touch applicability. **Weft adopts no canonical ingest order.** One Pydantic model, YAML as its serialisation, covering ingest and query alike; a subclass per resolution failure. Fitness function 11. Specified in `02` §3 | 2026-08-16 |
| **G3** | Plugin trust model | **Settled** | The threat is **installed-and-ambient**, not malicious — entry points turn *installed* into *executed with your privileges*. Discovery is **eager** (lazy import cannot coexist with bare plugin names, and both alternatives die on G4's conditional registration); posture is **open by default with an exhaustive opt-in pin** of distribution names. Two protections run always: the executed pack set is recorded on every run, and doctor flags ambient packs. Refusals share G4's status vocabulary and never import; policy refusal exits 3, resolution failure 4. Two-tier enforcement is **struck as unimplementable** and survives only as unenforced disclosure; command permission classes are mandatory at registration. Fitness function 8. Specified in `02` §2 → *The trust model* | 2026-08-15 |
| **G4** | Store contract and capability declaration | **Settled** | Tiered protocols with capability **derived** at registration, never declared; text search is a store capability so retrievers never build an index; stores take vectors, never embed; filters are a validated serialisable AST; deletion is idempotent and resumable via a source tombstone; the kernel runner owns `flush`. **pgvector is the floor** — the zero-container target is retired, proof moves to pgvector + Qdrant. Specified in `02` §1 → *The store contract family* | 2026-08-10 |
| **G5** | What flows between stages | **Settled** | A frozen `Node` of six core fields admitted by rule, plus typed extension models that declare their namespace and their transience; lineage required and its sources derived, so deletion reaches every descendant; ids are content digests; stages declare what they read and write, and `Stage[In, Out]` composition is checked at resolution. Specified in `02` §1 → *The payload model* | 2026-08-10 |
| **G6** | Sync or async core | **Settled** | **Async only, no exceptions** — no sync protocol, no sync facade, no declared colour, and one `asyncio.run` in the tree at the CLI entry point. A pack may not be sync-only; blocking calls are caught categorically at the stage seam (fitness function 7). Streaming is a `TokenSink` service, not a second contract; the runner keeps one batch in flight. Specified in `01` → *Colour* | 2026-08-10 |
| **G7** | Event bus or explicit extension points | **Settled** | **Explicit extension points only — there is no bus, and none was needed.** A pack participates by *registering*, never by being installed, so ambient observation is refused on G3's own argument: a pack reading every node a pipeline touches is the consent problem `02` §3's slot rule already forbids, and the audit log — this session's deliberately awkward case — is awkward precisely because it wants to be un-opt-out-able. Shape-level observation is the OTel span stream `seam.py` already emits on every call, which **was a fiction**: nothing in the tree configured a `TracerProvider`, so those spans reached the no-op default. It is made real by **`weft-otel`, an exporter pack** whose `register()` sets the provider — `01`'s own rule that *everything that exports a span is a pack*, applied rather than worked around, and the better close for this session: the audit log is not merely refused but **served, by a pack, through the published extension model with no core change**, which is Phase 5's exit criterion demonstrated on this session's hardest case. Core changes not at all — the kernel keeps `opentelemetry-api`, the CLI gains nothing. The cross-corpus pass needs no bus either — the runner's `flush()` already runs once per resolved stage, at end of run and on cancellation. The one real hole was **derived data outliving its source**: `delete_source` sat on `NodeStore` and was called by nothing, which is the reference's RAPTOR scar reappearing first-party. It is closed by two narrow `@runtime_checkable` store-family Protocols, per G4's *separate Protocols, not optional methods*: `SourceDeletable` (synchronous in-command fan-out across every registered participant) and `Reconcilable` (idempotent convergence, which reaches what a bus provably cannot — a pack installed after the corpus, a drain killed mid-flight, a second machine on one database). `ReconcileMode` is `repair` by default and is all the automatic post-index pass ever uses; `full` adds backfill and is reached only by a person's per-run flag, stating its cost before spending it, which is why G3's ambient rule stands unamended. **Kernel cost: zero lines.** Specified in `02` §1 and §4, and `03` | 2026-08-21 |
| **G8** | Is the REPL agentic | **Settled** | **No, and it never becomes one — but Weft does.** A planning loop is logic, and `03`'s governing rule keeps logic out of the adapter, so an agentic REPL is the wrong shape whatever the end state. Weft's finished form *is* agentic: the agent ships as a **first-party pack**, driven by the REPL, a script or an HTTP caller alike, scheduled as **Phase 7, after release** so it is built against published, versioned contracts. Phase 3 is unblocked, stays a shell, and owes it one property it needed anyway — a `Command` returns a typed result a renderer formats, never printed text. The `agentic-patterns` handoff moves to **G12**. Specified in `03` → *Is the REPL an agent?* and `01` → Phase 7 | 2026-08-18 |
| **G9** | Contract versioning and deprecation | **Settled** | **Per-contract semver, bound to the distribution version that is its enforceable shadow** — a contract major forces a distribution major, a minor forces at least a minor, and a distribution publishing several takes the maximum. Semver is classified for **two audiences** and the bump is the maximum, because the surface is Protocols others implement: adding a method, an `Enum` member, or a name to `required_declarations` is minor for a caller and **major for an implementer**. That makes `COMMAND_CONTRACT_VERSION` 1.1.0 a **mis-recorded major**, corrected to 2.0.0. **A stored schema is a second axis, carried in the data** — the contract version is not available at the read site, since the pack that wrote a row may not be installed, so `ExtModel.__schema_version__` is mandatory and a reader **upgrades or refuses**, refusing by default. **Enforcement adds no new declaration**: a version requirement *is* the dependency specifier, so `0.0.0` ends, bare names end, ranges are `>=X,<MAJOR+1` and never exact pins; skew is **reported by `doctor`, never refused by the kernel**, which gains zero lines. **Prose is not promised** — no project with a written policy promises it, and all of them name the channel they promise instead — so the promise is the `WeftError` subclass name as failure identity plus a structured, **additively** versioned error envelope carrying the human string as a `rendered` field; today `render_refusal` emits `str(exc)` on every failure path including `--json`, so requirement 5 is kept in-process and promised to nobody, and closing that is task 5.2d. The entry-point group name is **versioned, not immutable**. Inside 0.x a contract may move without a deprecation period but never silently; after 1.0 the clock is **one major of the publishing distribution**, and the changelog entry that carries it becomes **checkable**, because `CHANGELOG.md` has been written to once and is stale by five phases. **Fitness function 6, which did not exist, is built.** Specified in `09` §2–§3 and `02` §1 | 2026-08-21 |
| **G10** | Release and support policy | Open | — | — |
| **G12** | Permissions when the caller is never a TTY | Open | — | — |
| **G13** | The derived-participant seam — what a participant that is not the primary store may ask for, and be reached by | **Open** | Proposed 2026-08-22 by Phase 5's own exit criterion (task **5.7**), which found three faces of one question. **Reach**: `02` §1 settles that deletion fans out across *every* plugin satisfying `SourceDeletable`; task 5.1a excluded every `NodeStore` but the configured one to avoid acting on an unused backend, which excludes the graph store `02` §4 registers under `NodeStore` (`lessons.md` L5.25, L5.32). **Ask**: `Reconcilable.reconcile(ctx, mode)` hands a participant nothing naming the primary corpus, so `02` §4's promised `full` backfill is unbuildable by a pack (L5.24). **Answer**: a pack's `Command` cannot render its result for a person, because `weft_cli.render._RENDERERS` is a first-party table matched on result type (L5.30). All three ask what a *secondary, derived* participant is, without reintroducing the declared flag `02` §1 rules out — *"capability is derived, never declared"* | — |
| **G11** | Kernel error text — catalogue or literal | **Settled** | **Literal, and the catalogue is retired.** Weft's *interface* is English-only as a product decision; the **content**-language axis is where it invests. `MessageCatalogue`, `Context.messages` and `ctx.t()` are removed from the kernel with their three error classes, 33 → 30 — after three phases they had zero registered messages and zero call sites, and the 51 pack error classes that were their intended clientele had all chosen literals too. `Context.locale` stays, sharpened to the run's configured *content* language. A kernel error's explanation surface is `manual/troubleshooting.md`'s coverage ratchet — one obligation, not two — and its *quality* is new **fitness function 12**. Specified in `02` §1 | 2026-08-18 |
| **S1** | Phase 2 scope — reading the corpus, and measuring against it | **Settled** | Phase 2 also ships **PDF extraction**, a **semantic embedder** and a **model-provider adapter**, each as a pack, plus the `_try_extractors` combinator `01` had already assigned here. Forced by V1: the corpus is nine PDF papers, so the prerequisite this phase is judged against is unbuildable without them. Requirement **6** is the one touched; Phase 2's exit is unchanged and no fitness function moves. Tasks and exit demonstrations in `build-ledger.md` → Phase 2, 2.27–2.30 | 2026-08-17 |
| **S2** | Phase 2 scope — indexing a chunk several ways | **Settled** | The index-path techniques `10` §1.2 had filed as *Phase 1 work* are **Phase 2's**, as tasks **2.31** (`hypothetical-questions`) and **2.32** (`raptor`), plus **2.33** (`collapse-to-parent`), which exists because a chunk indexed four ways would otherwise take four of a ranking's top five slots and make every fan-out measurement in 2.16–2.18 look better than it is. Phase 1 exited without ever holding these rows, so until now no phase owned them. Requirements **6** and **3** are the ones touched; Phase 2's exit is unchanged and no fitness function moves. `10` §1.2 corrected in the same commit | 2026-08-17 |
| **S3** | Phase 7 — the agent | **Settled** | Weft's finished form is **agentic**, and the agent is a **first-party pack** rather than the REPL, because `03`'s governing rule keeps logic out of the driving adapter. Added as **Phase 7, after release**, so it is built against published, versioned contracts — which also makes it a harder instance of Phase 5's own proof: a pack built against nothing but the released API. Gated by **G12**. Forced by G8, whose two candidate answers were both wrong in the same way — "shell forever" declines the question and "agentic REPL" puts a planning loop where no other adapter could reach it. Requirements **1** and **4** are the ones touched; no earlier phase's exit moves and no fitness function is activated. `01` → Phase 7; procedure `09` §6.1 and §6.4 | 2026-08-18 |
| **S4** | Phase 4 scope — who wires `weft index` to a pipeline document | **Settled** | **Task 4.0, first in Phase 4, before 4.4.** Ledger task 2.29 recorded that `weft index` names its four stages in Python and that a plugin's `with:` configuration is therefore unreachable from `weft.toml` — and that **no task owned closing it**. Phase 4 is where it stops being optional: task **4.4** persists a run carrying *its resolved pipeline*, and the index path has no resolved pipeline to persist. The bridge already exists — `weft_cli.compile`, built by 2.4 and used only by the query path — so this is a wiring task, not a design one. Requirements **1** and **3** are the ones touched; Phase 4's exit is unchanged and no fitness function moves. Exit demonstration on the task line in `build-ledger.md` → Phase 4, 4.0 | 2026-08-20 |
| **S5** | Phase 5 scope — persisted schemas get a version axis | **Settled** | Six surfaces in the tree are data at rest — the `ext` map, the store's table, the filter AST, pipeline documents, `RunRecord`, `weft.toml` — and **none carried a version in the stored bytes**; `Filter.version` is a `ClassVar`, which pydantic never serialises, so a filter inside a stored pipeline has always carried none at all. Forced by G9: a contract version cannot cover this because it is not available at the read site. Adds tasks **5.2c** (kernel: `__schema_version__`, `upgrade`-or-refuse) with mechanism owned per surface. Requirement **6** is the one touched; Phase 5's exit is unchanged. 5.2c **must precede 5.4** — the graph pack ships the first third-party `ExtModel` | 2026-08-21 |
| **S8** | Phase 5 scope — a pack can offer a slot contribution | **Settled** | Measured while closing 5.3, by following the pack author guide from outside the repository: **slots are half-built**. `weft_kernel.resolution.Contribution` exists, `resolve()` accepts `contributions=`, and resolution places them, qualifies their ids by distribution and records the unplaced ones — the consuming half, built at task **1.11**. Nothing produces one: `PackRegistrar` has no slot seam, `weft_cli.pipeline_commands` passes `contributions=()` and says so in its own docstring, and `Contribution`'s docstring names a caller that was never written. So `02` §4's *"a named pipeline, and a slot contribution"* row is unreachable by any pack. Adds task **5.3a**, before 5.4, and **not folded into it**: task 5.7 detects whether a pack author needed a core change, and a graph-pack task that built this seam itself would make the change and then report that none was needed. Requirements **1** and **3** are the ones touched; Phase 5's exit is unchanged and no gate reopens | 2026-08-22 |
| **S7** | Phase 5 scope — a pack contributes its ext models | **Settled** | Measured while closing 5.2c: **eleven `ExtModel`s in the tree and one registered namespace**. `weft-store` registers its own `SyntheticOrigin`; `weft-chunk`'s `ChunkOffset` is hand-registered by `weft_cli.registry_bootstrap`; the other nine are unreachable on the read path, so a node carrying `PdfPages`, `Language`, `Keywords`, `Representation` or any retrieval trace cannot be rehydrated. `02` §1 recorded the gap at Phase 0 and deferred the design question — *what a pack contributes at registration beyond plugins* — as not Phase 0's to settle. **Phase 5's exit is what forces it**: a pack author whose ext model survives only when `weft-cli` is edited has needed a core change, which is what task 5.7 is written to detect. Adds task **5.2g**, before 5.3 and 5.4. Requirements **1** and **4** are the ones touched; Phase 5's exit is unchanged and no gate reopens | 2026-08-22 |
| **S6** | Phase 5 scope — the structured error channel | **Settled** | G9 ruled error prose unpromised, which is only honest paired with the channel that *is* promised — and Weft has no such channel on the failure path: `weft_cli.render.render_refusal` returns `str(exc)` and an exit code under `--json` exactly as without it, and of 78 `valid_options` sites in `weft-cli` **none is in a renderer**. So requirement 5's *"naming the valid options"* reaches a user only as prose, and declaring prose unpromised would delete the guarantee rather than relocate it. Adds task **5.2d**. Requirements **5** and **1** are the ones touched; Phase 5's exit is unchanged and no fitness function moves | 2026-08-21 |

Statuses: **Open** · **Settled** · **Reopened** — a settled decision found wrong is set back to
Reopened with the date and reason, never quietly edited.

**`G` is a gate, `S` is a scope decision.** They share the log because it is the authoritative status
of every decision, and they differ in one way that matters: a gate has a session in `05` that must be
run before it can be settled, and a scope decision has the `09` §6.4 procedure instead — which is why
`S1` carries no session and why the *Open decisions* count above stays a count of gates.

---

## Documents

| File | Owns | Kind |
|---|---|---|
| `README.md` *(this file)* | Status, execution state, decision log, document manifest | **Living** — changes every session |
| `01-high-level-plan.md` | Why rebuild, the architecture stack with costs, **the kernel boundary**, **the async colour**, runtime shape, deferred list, **the phase script**, fitness functions and the kernel budget, risks | Reference |
| `02-extension-model.md` | Contracts, who publishes them, what a plugin receives, the payload model, the store contract family, packs and discovery, **the trust model**, pack settings, pipelines as data, both driving use cases | Reference |
| `03-cli.md` | The CLI as driving adapter, command surface, permissions **including the class every plugin command must declare**, output | Reference |
| `04-reference-inventory.md` | What to lift from `a prior project`, what to rewrite, what to leave, where each item lands — kernel or pack — the reference's node metadata surface, **and its storage layer after G4** | Reference |
| `05-grilling-sessions.md` | The substance of every gate session — G1 through G11 | Reference |
| `reference-corrections.md` | Errors found in the **frozen** `reference/` audit, measured at source: what the audit claims, what is actually there, how it was verified | **Living** — appended to whenever the audit is found wrong. Opened 2026-08-20, after Phase 3's one reference lift found `08-salvage.md` §T1.12 naming a method that does not exist. `docs/reference/` stays frozen and unwritable; this is where a correction goes instead of scattering into whichever live document cited the claim |
| `06-phase-0-build.md` | The order of work inside Phase 0, what each step made true, where it had to avoid settling G2, and the scope fence | Historical — **retired 2026-08-16**, when Phase 0 exited (`7dae68b`). Its own retirement condition already fired; nothing routes to it as a live guide any more, and `build-ledger.md` is the phase-agnostic source for how to work a task. Packages' and tests' docstrings still cite specific steps of it as the historical reasoning behind code shaped that way — that is a citation, not a routing, and stays |
| `07-extension-cost.md` | The per-kind file cost of adding a capability, and fitness function 9 | Reference |
| `08-manuals.md` | The documents Weft ships to its users, which phase writes each, and the tests that keep them honest | Reference |
| `09-release.md` | Distribution and publishing, the user-facing version policy, the support and deprecation surface, the validation prerequisite, the production-readiness checklist, and the protocol for adjusting this plan | Reference |
| `10-technique-catalogue.md` | Every shipped technique's origin in the literature, whether its common name is earned or borrowed, the plugin name that follows, and whether the reference's implementation is faithful to what it is named after | Reference |
| `11-multimodal.md` | What the reference knows about PDFs, tables, figures and vision, what Weft ships as packs, and the decisions and gate questions multimodal raises | Reference |
| `build-ledger.md` | Task-level state for every phase: what is next, what each task makes true, and the commit that closed it | **Living** — changes every task |
| `lessons.md` | **How the work goes wrong** — a queue of defects in the process, drained at each phase close into a hook, a fitness function, a skill or `CLAUDE.md`. Written by the `lessons` skill, drained by `implement-ll`, injected into every session by `.claude/hooks/lessons_context.py` | **Living** — empty is the healthy state |
| `lessons-archive.md` | **What was learned, session by session, and how the entries relate** — drained entries with a closed edge vocabulary (`refines`, `supersedes`, `moves`, `recurs`, `reverses`, `caused-by`). It exists for the one failure a queue cannot see: a rule added, reversed, then re-learned. `scripts/lessons_graph.py` reports oscillating chains and recurrence, and `implement-ll` runs it before applying anything | **Living** — the only part of the loop that grows |
| `reference/study/` | The exhaustive reference study, moved into this repository 2026-08-15 | Reference — **frozen**, never edited |
| `reference/architecture-review-2026-08-10.md` | The assessment that motivated the rebuild | Historical — **frozen** |

Related. The first two now live **in this repository**, under `docs/reference/`, because they are
**finished audits of a frozen tree** that these documents cite roughly ninety times — evidence a plan
depends on belongs beside the plan, and a document that will never be edited again cannot drift from
a copy. The third stays in `a prior project`, because it documents the reference *for the reference's own readers*
and Weft cites it once, to say it is wrong.

`a prior project` itself remains a sibling checkout, reachable through the untracked `reference` symlink at
this repository's root, and it is needed for one thing only: **lifting code**. That source is live,
so it is never copied here. **Nothing in Weft's build, tests or packaging may read through the
symlink** — if the reference checkout is absent, the build is unaffected and only a reader following a
link notices.

| Where | What it is | Standing |
|---|---|---|
| `reference/study/` | The **exhaustive reference study** of `src/a_prior_project/` — extension axes, discovery and config, algorithms, cross-cutting concerns, boundaries, dead-and-broken, inventory, the three-tier salvage catalogue (`08-salvage.md`), 36 open questions (`09-open-questions.md`) and the edit list applied to this plan (`10-doc-corrections.md`) | **Authoritative on the reference.** Supersedes the review and the deck wherever they disagree |
| `reference/architecture-review-2026-08-10.md` | The 118-line assessment that motivated the rebuild | Historical. It was written without reading storage, without counting the registries, and without running the CI boundary checker against the tree it certifies. Most of the corrections applied below trace back to it |
| `../../a prior project/src/docs/deck/` *(stays in the reference repo)* | The documentation deck describing the reference | Historical, **and it carries two wrong numbers**: `notes-indexing-eval.md:3,74` says *"Indexing: 87 files"* and *"Evaluation: 30 files, 5847 LoC"*. Counted: `indexing/` = **85 files / 15,767 lines**, `evaluation/` = **37 files / 6,632 lines**. The deck's own `spec.json` slide 6 has indexing right, so the two sources disagree with each other. Everything else in that size table checks out (`core` 90 / 16,867, `retrieval` 27 / 9,916, `generation` 5 / 746, total **259 files / 52,021 lines**) |

---

## Corrections applied from the reference study

**Applied 2026-08-10.** Every factual assertion these six documents make about `a prior project` was
checked against the completed reference study. **32 corrections** were applied — 12 *correct before
use*, 13 *correct the detail*, 7 *qualify* — plus 14 claims marked **Unverified** because they
concern `system/`, which the study was instructed not to read. Nothing was deleted: where an
argument rested on a withdrawn premise, the premise was corrected in place and a marked note
records what changed and why. **The plan's architecture — microkernel, entry points, pipelines as
data, no privileged built-ins — is not challenged anywhere.** Every correction makes it
better-founded.

The ones that change what a builder would do:

| What changed | Where |
|---|---|
| **The reference's boundary checker does not fire.** It exits 0 on a tree with 11 runtime `system/` imports, and it is not in the canonical CI task. It is no longer fitness function 1 and has moved to *leave behind*; `tests/unit/architecture/test_allowlist_empty.py` replaces it, and a new **fitness function 0 — the gate must be in the gate** — was added | `01`, `04` |
| **Fitness functions 4 and 5 were rewritten.** FF4's grep-level enum check would have missed both walls that actually made the reference's strategy seam unusable; FF5 encoded a drift bug that never happened instead of the optional-dependency bug that did | `01`, `02` |
| **The reference's ingest order is chunk-then-clean**, with two stages the plan omitted. Which order Weft adopts is now a G2 decision rather than an inherited fact | `01`, `02`, `04`, `05` |
| **Storage is audited.** `get_vector_store_factory` never existed; there are 0 registered backend names and 0 in-library factory implementations, and adding one backend means editing 11 library files. It is the worst axis, not a comparable one | `01`, `05` |
| **`ResolvedLiteLLMTarget` has zero consumers and zero tests** — reclassified from *lift verbatim* to *lift the design* | `04` |
| **The metric suite is not "already correct"** — 6 of 21 never register, 2 test dummies ship registered, metrics cannot be parameterised, unknown names are silently dropped. **RAGAS and ROUGE are not dependencies**: those classes are hand-rolled, so they are original code to lift, not integrations to re-wire | `01`, `04` |
| **Three attractive lifts are contaminated** — a localization parity test that cannot fail, RAPTOR summaries that no deletion path can reach, and a fallback chain whose silent channel is indistinguishable from success | `02`, `04` |
| **`04-reference-inventory.md` is superseded in detail by `reference/study/08-salvage.md`**, the three-tier catalogue in which every Tier 1 entry was opened in the source and confirmed | `04` |

Full detail lives in the marked inline notes, each of which cites its evidence. The authoritative
source is the study itself — start at **`reference/study/00-INDEX.md`** (sections `01`–`11`) — and the
complete edit list, with `path:line` evidence and a ledger of which errors were inherited from
`reference/architecture-review-2026-08-10.md`, is **`reference/study/10-doc-corrections.md`**.

Open questions the study raised and the plan must answer are recorded as questions inside the
grilling sessions, pointing at `reference/study/09-open-questions.md`. They are not answered here.

---

## Protocol

**When a grilling session closes.** Update the decision log row — status, outcome in one line, date
— and tick the checklist item, in the same commit. If the outcome changes a reference document,
edit that document too; the log records *that* it was decided and *what*, never the reasoning,
which belongs in the document the decision changed.

**When a grilling session or a task leaves a lesson.** If a documented check turned out to be
prose, a claim from intuition was falsified by measurement, a recommendation contradicted settled
text, or a defect was found by running the binary rather than by its tests — it goes into
`lessons.md`'s queue, through the `lessons` skill, while the reasoning is still present. The queue is
drained at the phase close by `implement-ll`, which routes each entry to a hook, a fitness function, a
skill or `CLAUDE.md`, and leaves the queue empty.

**When a phase completes.** Tick its build and exit items, and move the Status block to the next
phase and its first open gate.

How a decision is reopened, how a phase or a fitness function is added, and what a scope change
obliges: `09-release.md` §6.

**When a document is added.** Register it in the manifest with one line stating what it *owns*, and
make sure nothing it owns is also stated here or in another document. More documents are expected;
the manifest is what keeps them navigable, and the ownership column is what keeps them from
drifting.

**What never goes in this file.** Design content, rationale, code, or anything already stated in a
reference document. If you find yourself explaining *why* here, it belongs in `01` through `05`,
and the link belongs here.
