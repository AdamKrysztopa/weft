# Weft — control

**This is the single source of truth. Open this file first; it routes everything else.**

Weft is a RAG engine being rebuilt from scratch: a small kernel that knows nothing about PDFs,
chunking, embeddings or graphs, where every capability is a plugin discovered through Python entry
points, pipelines are data derivable from other pipelines, and built-ins are held to the same
public contract as anything a third party writes.

> **The rule that keeps this file true.** It holds **state and pointers only — never definitions.**
> Identifiers live here (phase names, gate IDs, statuses, dates). Content lives in exactly one
> reference document and is linked, never restated. This is not tidiness: keeping one fact in two
> places is a real, observed failure mode — supported file formats kept in two lists that can drift
> apart, so a format accepted at upload had no extractor at extraction time. A control file that
> paraphrases the plan reproduces that bug at the level of the plan itself.
>
> *(Corrected 2026-08-10: the anecdote originally said the two lists "drifted". They have not — they
> are identical today, 17 entries each. The accept-then-fail consequence is real, by a different
> mechanism: two formats are declared unconditionally while their extractors are inserted
> conditionally on optional dependencies. The argument for single-sourcing is unaffected and now
> rests on a fact.)*

---

## Status

| | |
|---|---|
| **Phase** | **Phase 8 — From engine to product**, added 2026-09-05 as scope decision `S9`. It runs **before Phase 7**, which G12 still gates — `01` → Phase 8 says why the number and the order differ, and this row is the mechanism that carries it. Tasks 8.1–8.5 are ticked; 8.6–8.9 are open. Phase 6 closed 2026-08-26 with all 35 tasks ticked, its exit met in substance and unmet in letter — `build-ledger.md` → *Phase 6's close* records which rows and why |
| **Blocked by** | **Nothing. Phase 8 has no gate at all** — the first phase since Phase 2 with no gate line to read, which is why it is schedulable while Phase 7 is not. G12 still gates Phase 7. Phase 6 is closed: all 35 tasks, including the five filed at its own close, plus the eight-task consolidation (`build-ledger.md` → *Consolidation*) that re-settled G10 on 2026-09-05. What it leaves owed is **one publish to a real index**, deliberately the project owner's to run — the workflow exists (6.2), the artefacts build and carry their licences (6.7, 6.11), **six** names are checked rather than twenty, what reproduces the baseline is attached to the release (6.35), and the whole install path is proved against a local index (6.13) and against six freshly built wheels installed into a clean venv outside this repository |
| **Next action** | **Ledger task 8.6** — the hybrid retriever, vector plus full-text fused from one store. `weft_store`'s `search_text` is implemented in pgvector and **has no caller**, and `vector-top-k`'s own error text already advertises `hybrid` to users who cannot install it. **This row outranks ledger order**, which still points at `7.1` because Phase 7 sorts first in the file; `01` → Phase 8 carries the reason. `ROADMAP.md` is retired into Phase 8 and holds nothing. The default install is **`weft-rag`** at `2.1.0`, containing the fourteen packs — six published names, not twenty (G10 re-settled 2026-09-05). `weft` is taken on PyPI at the very version this set first declared (`lessons.md` L6.33). `lessons.md` → *Queue* is where the queue's depth is read, never a count restated here |
| **Open decisions** | 1 of 15 — every row settled except **G12**, which gates Phase 7. `S9` opened and settled Phase 8 on 2026-09-05. G0 is logged only; every other gate row has a session in `05` |
| **Updated** | 2026-09-05 |

G2's close resolved the **three places Phase 0 could accidentally settle it**, each of which `06`
had fixed to a minimal reversible choice: embedding **stays a stage** (G4 forbids a store to embed,
so it was never G2's to choose); a pipeline **stays an ordered list**, now with derivation, slots and
declared constraints on top of it; and two packs claiming one name **stays a refusal**, relaxed only
by an operator's pin in `weft.toml`. All three moved in the direction `06` required — relaxing a
refusal rather than tightening a silence. It also cleared `11`'s three filed questions and one of
`11`'s deferred-gate blockers. Both of Phase 5's gates closed on 2026-08-21 — **G7** without a bus, **G9** without a new declaration
mechanism and without a kernel line — and `09` §2.3's five dependencies are answered rather than open.
**G10 and G13 closed on 2026-08-22**, which leaves **G12** as the only open gate and Phase 7 as the
only phase waiting on one. G10 kept all three of `09`'s recommendations and answered two questions
neither document had asked; G13 closed all three faces of Phase 5's failed exit with **zero kernel
lines** — reach derived from use, the ask served by the passport that already existed, and the one
genuinely missing seam (a renderer a pack can register) built the way every other extension point
already is.

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
- [ ] **Exit:** the graph pack is built by someone who never touches core *(run 2026-08-22 and **not met** — the pack needed no core edit to be **written**, and needs three to **work as `02` §4 specifies**. Task 5.7 carries the assessment; **G13** carried the question and settled it 2026-08-22. Discharged by **task 6.21**, after the repairs 6.18–6.20 — this box is ticked there, not here)*

**Phase 6 — Release**

- [x] **G10** Release and support policy *(settled 2026-08-22: independent semver plus a named release set `weft`; 1.0 by evidence with a date-boxed review; a 1.0 set pins nothing below 1.0; support is the current major plus the previous for one set major or six months)*
- [x] **G13** The derived-participant seam *(settled 2026-08-22: reach follows use, the ask goes through `ctx.require`, a renderer registers at the seam — repairs are tasks 6.18–6.20, and 6.21 re-runs Phase 5's exit)*
- [x] Prerequisite V4–V6 complete — metric semantics, providers and cost, a persisted baseline run *(V4 task 4.3, V5 task 4.7, V6 task 4.8 — closed 2026-08-20; the checklist item this feeds, "the baseline run is published with the release" in `09` §5.2, stays unticked, since publication is Phase 6's)*
- [ ] Phase 6 build *(turns on FF10)*
- [ ] **Exit:** a stranger installs the release from the index and reproduces the published baseline

**Phase 8 — From engine to product** *(added 2026-09-05, logged as `S9`; **runs before Phase 7**, which G12 gates)*

- [x] No gate — every decision this phase needs is settled
- [x] Tasks 8.1–8.5 — the ladder, the ingest documents, `[services] route`, fitness function 16, the naming
- [ ] Tasks 8.6–8.9 — hybrid retrieval, the fan-out cap, the falsification instrument, a driver for `Renderer`
- [ ] **Exit:** from outside this repository, a corpus indexed through a shipped document and answered through three rungs including a hybrid one, FF16 green with an **empty** waiver, no run exceeding its own concurrency cap, and `weft eval` reporting whether a claimed improvement is real — either answer discharges it

**Phase 7 — The agent** *(added 2026-08-18 by G8, logged as `S3`)*

- [ ] **G12** Permissions when the caller is never a TTY *(this is where the `agentic-patterns` handoff lands)*
- [ ] Phase 7 build
- [ ] **Exit:** the agentic pack installs from the index and drives a corpus end to end through the published command surface, with no edit to core

Each phase's gates, required reading and exit criterion are specified in
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
| **G7** | Event bus or explicit extension points | **Settled** | **Explicit extension points only — there is no bus, and none was needed.** A pack participates by *registering*, never by being installed, so ambient observation is refused on G3's own argument: a pack reading every node a pipeline touches is the consent problem `02` §3's slot rule already forbids, and the audit log — this session's deliberately awkward case — is awkward precisely because it wants to be un-opt-out-able. Shape-level observation is the OTel span stream `seam.py` already emits on every call, which **was a fiction**: nothing in the tree configured a `TracerProvider`, so those spans reached the no-op default. It is made real by **`weft-otel`, an exporter pack** whose `register()` sets the provider — `01`'s own rule that *everything that exports a span is a pack*, applied rather than worked around, and the better close for this session: the audit log is not merely refused but **served, by a pack, through the published extension model with no core change**, which is Phase 5's exit criterion demonstrated on this session's hardest case. Core changes not at all — the kernel keeps `opentelemetry-api`, the CLI gains nothing. The cross-corpus pass needs no bus either — the runner's `flush()` already runs once per resolved stage, at end of run and on cancellation. The one real hole was **derived data outliving its source**: `delete_source` sat on `NodeStore` and was called by nothing — the same scar as a derived-summary layer that nothing ever deletes, reappearing first-party. It is closed by two narrow `@runtime_checkable` store-family Protocols, per G4's *separate Protocols, not optional methods*: `SourceDeletable` (synchronous in-command fan-out across every registered participant) and `Reconcilable` (idempotent convergence, which reaches what a bus provably cannot — a pack installed after the corpus, a drain killed mid-flight, a second machine on one database). `ReconcileMode` is `repair` by default and is all the automatic post-index pass ever uses; `full` adds backfill and is reached only by a person's per-run flag, stating its cost before spending it, which is why G3's ambient rule stands unamended. **Kernel cost: zero lines.** Specified in `02` §1 and §4, and `03` | 2026-08-21 |
| **G8** | Is the REPL agentic | **Settled** | **No, and it never becomes one — but Weft does.** A planning loop is logic, and `03`'s governing rule keeps logic out of the adapter, so an agentic REPL is the wrong shape whatever the end state. Weft's finished form *is* agentic: the agent ships as a **first-party pack**, driven by the REPL, a script or an HTTP caller alike, scheduled as **Phase 7, after release** so it is built against published, versioned contracts. Phase 3 is unblocked, stays a shell, and owes it one property it needed anyway — a `Command` returns a typed result a renderer formats, never printed text. The `agentic-patterns` handoff moves to **G12**. Specified in `03` → *Is the REPL an agent?* and `01` → Phase 7 | 2026-08-18 |
| **G9** | Contract versioning and deprecation | **Settled** | **Per-contract semver, bound to the distribution version that is its enforceable shadow** — a contract major forces a distribution major, a minor forces at least a minor, and a distribution publishing several takes the maximum. Semver is classified for **two audiences** and the bump is the maximum, because the surface is Protocols others implement: adding a method, an `Enum` member, or a name to `required_declarations` is minor for a caller and **major for an implementer**. That makes `COMMAND_CONTRACT_VERSION` 1.1.0 a **mis-recorded major**, corrected to 2.0.0. **A stored schema is a second axis, carried in the data** — the contract version is not available at the read site, since the pack that wrote a row may not be installed, so `ExtModel.__schema_version__` is mandatory and a reader **upgrades or refuses**, refusing by default. **Enforcement adds no new declaration**: a version requirement *is* the dependency specifier, so `0.0.0` ends, bare names end, ranges are `>=X,<MAJOR+1` and never exact pins; skew is **reported by `doctor`, never refused by the kernel**, which gains zero lines. **Prose is not promised** — no project with a written policy promises it, and all of them name the channel they promise instead — so the promise is the `WeftError` subclass name as failure identity plus a structured, **additively** versioned error envelope carrying the human string as a `rendered` field; today `render_refusal` emits `str(exc)` on every failure path including `--json`, so requirement 5 is kept in-process and promised to nobody, and closing that is task 5.2d. The entry-point group name is **versioned, not immutable**. Inside 0.x a contract may move without a deprecation period but never silently; after 1.0 the clock is **one major of the publishing distribution**, and the changelog entry that carries it becomes **checkable**, because `CHANGELOG.md` has been written to once and is stale by five phases. **Fitness function 6, which did not exist, is built.** Specified in `09` §2–§3 and `02` §1 | 2026-08-21 |
| **G10** | Release and support policy | **Settled**, and **re-settled 2026-09-05: twenty published names became six.** `weft-rag` now *contains* the fourteen packs rather than pinning them; `weft-kernel` and four add-ons (`weft-openai`, `weft-pdf`, `weft-qdrant`, `weft-otel`) publish beside it. The shape's own argument survives — a third-party pack installs beside `weft-rag` exactly as `weft-qdrant` does, and FF10(a) still compares the release job's matrix against the workspace — but independent semver for the fourteen and per-pack isolated-install proof are given up, and four already-published names go vestigial. What made it affordable was separating a pack's identity (its `weft.packs` entry-point name) from its distribution; without that, bundling collapses twelve `plugins doctor` rows and twelve `[packs.*]` namespaces into one. `09` §1 and `02` §2 carry it *(the set's **name** corrected 2026-08-25 at ledger 6.13: `weft-rag`, not `weft` — that name is taken on PyPI at the very version this set declares, found by installing from a real index. The **shape** G10 settled is untouched, and the command a user types is still `weft`, from `weft-cli`'s console script. `09` §1; `lessons.md` L6.33)* | **Independent semver per distribution, plus a named release set** — a code-free distribution `weft-rag` pinning one exactly-tested combination, which is the only unit under which a third-party pack has a first-party pack's standing, and the only one two sources can be made to disagree about (FF10(a)). **Lockstep is rejected twice over**: it is the privileged path, and it now contradicts G9, which makes a distribution's major a function of the contracts *it* publishes — `weft-store` and `weft-command` are already `2.0.0` against a `0.1.0` kernel. **Independent-and-nothing-else is rejected** because a documented tested combination is the artefact this repository has already measured going stale (`CHANGELOG.md`, `lessons.md` L5.8). **`09` §1's own *Bring* measurement was falsified on the day**: it predicted zero distributions declaring a bound on a sibling; the count is all of them, since G9's rule landed in Phase 5 — bounds say what is *compatible*, and only a pinned set says what was *tested together*. **1.0 rests on evidence, and the date gets a different job**: the checklist gates the release, a fixed review date publishes what is still missing, and it may never ship past a failed row or pass in silence. **A 1.0 release set pins nothing below 1.0** — G9 makes 0.x mean "may move without a deprecation period", so a 1.0 set over 0.x pins promises what its parts reserve the right to break; six distributions read `0.1.0` today and each either makes the promise or installs beside the set. **Support is the current major of every pinned distribution, plus the previous major for one release-set major or six months, whichever is longer, fixes only.** Two clocks now exist and are deliberately different: G9's deprecation clock governs when a surface may be removed, this one governs how long a shipped combination is still fixed. Specified in `09` §1, §2.2, §3 and §5.2 | 2026-08-22 |
| **G12** | Permissions when the caller is never a TTY | Open | — | — |
| **G13** | The derived-participant seam — what a participant that is not the primary store may ask for, and be reached by | **Settled** | **Three faces, one question, and the extension model needed one new seam rather than three.** **Reach: participation follows use.** A fan-out takes the configured `[services] store` **plus** every `NodeStore` named by a pipeline in the catalogue or by a persisted run record; every other contract still contributes every plugin registered under it. Derived from what the project actually runs, so nothing is declared and no author has a rule to remember — the standard *"capability is derived, never declared"* already holds registration to, applied to reach. Task 5.1a's narrowing was right about the unused backend and wrong about the graph store, and its cost is stated: the delete path reads the catalogue and the run history, and a store dropped from every document that also never ran is out. **Ask: through the passport, not a wider signature.** `Context.require` is G1's one resolution seam and `NodeStore` already answers *what should exist* via `list_sources`/`scan`/`count`; the CLI registers the configured store into the reconcile `Context` and a participant calls `ctx.require(NodeStore)`. **`STORE_CONTRACT_VERSION` does not move** — a contract bumped for a fact about the CLI's service registry would be the mis-recorded version G9 spent a session correcting. **Answer: a renderer registers at the seam** — `registrar.add_renderer(ResultType, renderer)`, `Rendered` published from `weft-command`, and the CLI's own renderers moved onto the same call so built-ins keep no private path; the structured dump stays the floor and stops being the ceiling. `COMMAND_CONTRACT_VERSION` moves under G9's two-audience rule. **A declared "I am derived" flag was refused on `02` §1's own argument**, and the one real hole was the half of an extension point nobody had built — L5.15's producing side, again. **Kernel cost: zero lines.** Repairs are ledger tasks **6.18–6.20**; **6.21** re-runs Phase 5's exit. Specified in `02` §1, `02` §4 and `03`; argued in `05` → G13 | 2026-08-22 |
| **G11** | Kernel error text — catalogue or literal | **Settled** | **Literal, and the catalogue is retired.** Weft's *interface* is English-only as a product decision; the **content**-language axis is where it invests. `MessageCatalogue`, `Context.messages` and `ctx.t()` are removed from the kernel with their three error classes, 33 → 30 — after three phases they had zero registered messages and zero call sites, and the 51 pack error classes that were their intended clientele had all chosen literals too. `Context.locale` stays, sharpened to the run's configured *content* language. A kernel error's explanation surface is `manual/troubleshooting.md`'s coverage ratchet — one obligation, not two — and its *quality* is new **fitness function 12**. Specified in `02` §1 | 2026-08-18 |
| **S1** | Phase 2 scope — reading the corpus, and measuring against it | **Settled** | Phase 2 also ships **PDF extraction**, a **semantic embedder** and a **model-provider adapter**, each as a pack, plus the `_try_extractors` combinator `01` had already assigned here. Forced by V1: the corpus is nine PDF papers, so the prerequisite this phase is judged against is unbuildable without them. Requirement **6** is the one touched; Phase 2's exit is unchanged and no fitness function moves. Tasks and exit demonstrations in `build-ledger.md` → Phase 2, 2.27–2.30 | 2026-08-17 |
| **S2** | Phase 2 scope — indexing a chunk several ways | **Settled** | The index-path techniques `10` §1.2 had filed as *Phase 1 work* are **Phase 2's**, as tasks **2.31** (`hypothetical-questions`) and **2.32** (`raptor`), plus **2.33** (`collapse-to-parent`), which exists because a chunk indexed four ways would otherwise take four of a ranking's top five slots and make every fan-out measurement in 2.16–2.18 look better than it is. Phase 1 exited without ever holding these rows, so until now no phase owned them. Requirements **6** and **3** are the ones touched; Phase 2's exit is unchanged and no fitness function moves. `10` §1.2 corrected in the same commit | 2026-08-17 |
| **S3** | Phase 7 — the agent | **Settled** | Weft's finished form is **agentic**, and the agent is a **first-party pack** rather than the REPL, because `03`'s governing rule keeps logic out of the driving adapter. Added as **Phase 7, after release**, so it is built against published, versioned contracts — which also makes it a harder instance of Phase 5's own proof: a pack built against nothing but the released API. Gated by **G12**. Forced by G8, whose two candidate answers were both wrong in the same way — "shell forever" declines the question and "agentic REPL" puts a planning loop where no other adapter could reach it. Requirements **1** and **4** are the ones touched; no earlier phase's exit moves and no fitness function is activated. `01` → Phase 7; procedure `09` §6.1 and §6.4 | 2026-08-18 |
| **S4** | Phase 4 scope — who wires `weft index` to a pipeline document | **Settled** | **Task 4.0, first in Phase 4, before 4.4.** Ledger task 2.29 recorded that `weft index` names its four stages in Python and that a plugin's `with:` configuration is therefore unreachable from `weft.toml` — and that **no task owned closing it**. Phase 4 is where it stops being optional: task **4.4** persists a run carrying *its resolved pipeline*, and the index path has no resolved pipeline to persist. The bridge already exists — `weft_cli.compile`, built by 2.4 and used only by the query path — so this is a wiring task, not a design one. Requirements **1** and **3** are the ones touched; Phase 4's exit is unchanged and no fitness function moves. Exit demonstration on the task line in `build-ledger.md` → Phase 4, 4.0 | 2026-08-20 |
| **S5** | Phase 5 scope — persisted schemas get a version axis | **Settled** | Six surfaces in the tree are data at rest — the `ext` map, the store's table, the filter AST, pipeline documents, `RunRecord`, `weft.toml` — and **none carried a version in the stored bytes**; `Filter.version` is a `ClassVar`, which pydantic never serialises, so a filter inside a stored pipeline has always carried none at all. Forced by G9: a contract version cannot cover this because it is not available at the read site. Adds tasks **5.2c** (kernel: `__schema_version__`, `upgrade`-or-refuse) with mechanism owned per surface. Requirement **6** is the one touched; Phase 5's exit is unchanged. 5.2c **must precede 5.4** — the graph pack ships the first third-party `ExtModel` | 2026-08-21 |
| **S9** | Phase 8 — from engine to product | **Settled** | **The engine expresses far more than it ships, and nothing was measuring the difference.** Counted 2026-09-05: **four** pipeline documents in the whole tree naming **ten** plugins, against **forty-eight** plugins registered into pipeline positions — so *"naive to advanced, quickly"* was true of the engine and false of the product, and thirty-eight capabilities were reachable only by writing YAML against names no shipped document mentioned. `01` stopped at Phase 7 and **G12 blocks Phase 7 entirely**, so every buildable row had no phase to belong to and the lessons queue had no close to drain against — the state `ADAM_TODO.md` item 1 carried. Added as **Phase 8, running before Phase 7** (no gate; `docs/README.md`'s Next action row carries the ordering the ledger cannot). **It absorbs `ROADMAP.md`**, which held no state by design and therefore could not record that its own row 5 shipped as a side effect of row 1; rows 1–5 are tasks 8.1–8.8 and the file is retired to a pointer. **Row 6, the graph pack, is deliberately excluded** — blocked on three decisions, two of which touch G2, G4, G5 and `S5` at once. Turns on **fitness function 16**. Requirements **3**, **4** and **6** are the ones touched; no earlier phase's exit moves and no gate reopens. `01` → Phase 8 owns the content and the exit; `build-ledger.md` → Phase 8 owns the tasks | 2026-09-05 |
| **S8** | Phase 5 scope — a pack can offer a slot contribution | **Settled** | Measured while closing 5.3, by following the pack author guide from outside the repository: **slots are half-built**. `weft_kernel.resolution.Contribution` exists, `resolve()` accepts `contributions=`, and resolution places them, qualifies their ids by distribution and records the unplaced ones — the consuming half, built at task **1.11**. Nothing produces one: `PackRegistrar` has no slot seam, `weft_cli.pipeline_commands` passes `contributions=()` and says so in its own docstring, and `Contribution`'s docstring names a caller that was never written. So `02` §4's *"a named pipeline, and a slot contribution"* row is unreachable by any pack. Adds task **5.3a**, before 5.4, and **not folded into it**: task 5.7 detects whether a pack author needed a core change, and a graph-pack task that built this seam itself would make the change and then report that none was needed. Requirements **1** and **3** are the ones touched; Phase 5's exit is unchanged and no gate reopens | 2026-08-22 |
| **S7** | Phase 5 scope — a pack contributes its ext models | **Settled** | Measured while closing 5.2c: **eleven `ExtModel`s in the tree and one registered namespace**. `weft-store` registers its own `SyntheticOrigin`; `weft-chunk`'s `ChunkOffset` is hand-registered by `weft_cli.registry_bootstrap`; the other nine are unreachable on the read path, so a node carrying `PdfPages`, `Language`, `Keywords`, `Representation` or any retrieval trace cannot be rehydrated. `02` §1 recorded the gap at Phase 0 and deferred the design question — *what a pack contributes at registration beyond plugins* — as not Phase 0's to settle. **Phase 5's exit is what forces it**: a pack author whose ext model survives only when `weft-cli` is edited has needed a core change, which is what task 5.7 is written to detect. Adds task **5.2g**, before 5.3 and 5.4. Requirements **1** and **4** are the ones touched; Phase 5's exit is unchanged and no gate reopens | 2026-08-22 |
| **S9** | The originality claim — three cases, not one absolute sentence | **Settled** | `NOTICE` said *"Weft contains no source text from any other codebase"* and that was **literally false in two directions at once**, with nothing about the project's substance wrong. (1) Five docstrings quote a sentence of a third party's stated *rationale*, attributed with `path:line`, beside Weft's own restatement of the same reasoning — `weft_clean/table_linearizer.py:6-7`, `whitespace.py:6`, `hyphenation.py:7`, `unicode_normalizer.py:5` (which labels its own quotation "verbatim") and `weft_llm/loop_guard.py:50`. Nothing executable was carried; `CLAUDE.md`'s own test is what each fails. (2) The owner decided on 2026-09-05 that **`graph-study-main`, their own unlicensed prior work, may be copied as-is** — licit, and it falsifies the same sentence the moment the first line lands. **The settlement is three cases, stated in `NOTICE`:** a third party's source text, never; the copyright holder's own prior work, permitted and marked at the file that carries it; a sentence or two of a third party's stated rationale, attributed at the point of use and never standing in for our own words. **A live rule conflict is settled in the same act**: an earlier rule forbade *regexes* categorically while `weft_clean/artifact_remover.py:63` shipped one under a "facts, not text" reading. The obligation moves from the artefact's type to whether the string is **recoverable from a written specification** — `^\s*Page\s+\d+\s*$` is, and the specification is now written beside it; a 243-word stop list is not, and stays authored fresh. Requirement **none** is touched and no gate reopens — this is a claim-accuracy repair, which is why it is logged rather than gated. `NOTICE`, `CLAUDE.md`, `CONTRIBUTING.md` and `README.md` carry it | 2026-09-05 |
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
| `05-grilling-sessions.md` | The substance of every gate session — G1 through G11 | Reference |
| `06-phase-0-build.md` | The order of work inside Phase 0, what each step made true, where it had to avoid settling G2, and the scope fence | Historical — **retired 2026-08-16**, when Phase 0 exited (`7dae68b`). Its own retirement condition already fired; nothing routes to it as a live guide any more, and `build-ledger.md` is the phase-agnostic source for how to work a task. Packages' and tests' docstrings still cite specific steps of it as the historical reasoning behind code shaped that way — that is a citation, not a routing, and stays |
| `07-extension-cost.md` | The per-kind file cost of adding a capability, and fitness function 9 | Reference |
| `08-manuals.md` | The documents Weft ships to its users, which phase writes each, and the tests that keep them honest | Reference |
| `09-release.md` | Distribution and publishing, the user-facing version policy, the support and deprecation surface, the validation prerequisite, the production-readiness checklist, and the protocol for adjusting this plan | Reference |
| `10-technique-catalogue.md` | Every shipped technique's origin in the literature, whether its common name is earned or borrowed, the plugin name that follows, and whether the shipped implementation is faithful to what it is named after | Reference |
| `11-multimodal.md` | What Weft ships as packs for PDFs, tables, figures and vision, and the decisions and gate questions multimodal raises | Reference |
| `build-ledger.md` | Task-level state for every phase: what is next, what each task makes true, and the commit that closed it | **Living** — changes every task |
| `lessons.md` | **How the work goes wrong** — a queue of defects in the process, drained at each phase close into a hook, a fitness function, a skill or `CLAUDE.md`. Written by the `lessons` skill, drained by `implement-ll`, injected into every session by `.claude/hooks/lessons_context.py` | **Living** — empty is the healthy state |
| `lessons-archive.md` | **What was learned, session by session, and how the entries relate** — drained entries with a closed edge vocabulary (`refines`, `supersedes`, `moves`, `recurs`, `reverses`, `caused-by`). It exists for the one failure a queue cannot see: a rule added, reversed, then re-learned. `scripts/lessons_graph.py` reports oscillating chains and recurrence, and `implement-ll` runs it before applying anything | **Living** — the only part of the loop that grows |

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
