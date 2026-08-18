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
| **Phase** | Phase 3 — The CLI |
| **Blocked by** | Nothing. This phase's gate, **G8**, is **settled** (2026-08-18): the REPL is a shell and never becomes an agent, because `03`'s governing rule keeps a planning loop out of the driving adapter — Weft's agentic front end is a pack, and it is **Phase 7**. `build-ledger.md` → Phase 3 carries no ⚠ on any task: the three that held one (3.4, 3.5, 3.11) were re-derived when G8 closed rather than merely unmarked, and all three already stated true properties |
| **Next action** | **Task 3.1** — eleven tasks in `build-ledger.md` → Phase 3, none of them gated. **Phase 2 closed 2026-08-18 at 36 of 36 tasks**, its Exit box ticked on the evidence its own criterion names: task **2.8** (the router discovers a strategy from the registry, no enum, no closed key space, `tests/architecture/test_ff4_no_closed_key_space.py`), **FF9(c)** wired and green (task 2.11, all 23 published contracts implemented out of tree, proven against real throwaway environments) and **FF12** wired and green (task 2.36, `tests/architecture/test_ff12_unresolvable_name_carries_options.py`). `uv run poe ci-checks` is green — **1303 passed, 1 skipped, 75 architecture tests**. **One thing this phase inherits, and it is a conversation rather than a blocker**: `weft-kernel` stands at **2,869 lines**, past the **2,800 review trigger** in `tests/architecture/test_ff3_kernel_budget.py` and well under its 3,500 budget. Task 2.36 put it there — 20 error classes across five distributions gained a required `valid_options` field, eight of them kernel-owned — and a post-review repair returned 43 of those lines by collapsing four byte-identical constructors onto one shared base. The budget is never edited in the change that grew the kernel (`phase-step`), so the number stands as measured and the boundary question belongs on this phase's agenda |
| **Open decisions** | 4 of 13 — G0, G1, G2, G3, G4, G5, G6, G8 and G11 settled; G7, G9, G10 and G12 open. G0 is logged only; every other row has a session in `05` |
| **Updated** | 2026-08-18 |

G2's close resolved the **three places Phase 0 could accidentally settle it**, each of which `06`
had fixed to a minimal reversible choice: embedding **stays a stage** (G4 forbids a store to embed,
so it was never G2's to choose); a pipeline **stays an ordered list**, now with derivation, slots and
declared constraints on top of it; and two packs claiming one name **stays a refusal**, relaxed only
by an operator's pin in `weft.toml`. All three moved in the direction `06` required — relaxing a
refusal rather than tightening a silence. It also cleared `11`'s three filed questions and one of
`11`'s deferred-gate blockers. The next gate is **G7**, at Phase 5.

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
- [ ] Phase 3 build
- [ ] **Exit:** a plugin's command appears in `--help` without core knowing it exists

**Phase 4 — Evaluation and observability**

- [ ] Phase 4 build *(no gate)*
- [ ] **Exit:** the tool generates its own comparison across two derived pipelines

**Phase 5 — The independence test**

- [ ] **G7** Event bus or explicit extension points
- [ ] **G9** Contract versioning and deprecation
- [ ] Phase 5 build
- [ ] **Exit:** the graph pack is built by someone who never touches core

**Phase 6 — Release**

- [ ] **G10** Release and support policy *(after G9)*
- [ ] Prerequisite V4–V6 complete — metric semantics, providers and cost, a persisted baseline run
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
| **G7** | Event bus or explicit extension points | Open | — | — |
| **G8** | Is the REPL agentic | **Settled** | **No, and it never becomes one — but Weft does.** A planning loop is logic, and `03`'s governing rule keeps logic out of the adapter, so an agentic REPL is the wrong shape whatever the end state. Weft's finished form *is* agentic: the agent ships as a **first-party pack**, driven by the REPL, a script or an HTTP caller alike, scheduled as **Phase 7, after release** so it is built against published, versioned contracts. Phase 3 is unblocked, stays a shell, and owes it one property it needed anyway — a `Command` returns a typed result a renderer formats, never printed text. The `agentic-patterns` handoff moves to **G12**. Specified in `03` → *Is the REPL an agent?* and `01` → Phase 7 | 2026-08-18 |
| **G9** | Contract versioning and deprecation | Open | — | — |
| **G10** | Release and support policy | Open | — | — |
| **G12** | Permissions when the caller is never a TTY | Open | — | — |
| **G11** | Kernel error text — catalogue or literal | **Settled** | **Literal, and the catalogue is retired.** Weft's *interface* is English-only as a product decision; the **content**-language axis is where it invests. `MessageCatalogue`, `Context.messages` and `ctx.t()` are removed from the kernel with their three error classes, 33 → 30 — after three phases they had zero registered messages and zero call sites, and the 51 pack error classes that were their intended clientele had all chosen literals too. `Context.locale` stays, sharpened to the run's configured *content* language. A kernel error's explanation surface is `manual/troubleshooting.md`'s coverage ratchet — one obligation, not two — and its *quality* is new **fitness function 12**. Specified in `02` §1 | 2026-08-18 |
| **S1** | Phase 2 scope — reading the corpus, and measuring against it | **Settled** | Phase 2 also ships **PDF extraction**, a **semantic embedder** and a **model-provider adapter**, each as a pack, plus the `_try_extractors` combinator `01` had already assigned here. Forced by V1: the corpus is nine PDF papers, so the prerequisite this phase is judged against is unbuildable without them. Requirement **6** is the one touched; Phase 2's exit is unchanged and no fitness function moves. Tasks and exit demonstrations in `build-ledger.md` → Phase 2, 2.27–2.30 | 2026-08-17 |
| **S2** | Phase 2 scope — indexing a chunk several ways | **Settled** | The index-path techniques `10` §1.2 had filed as *Phase 1 work* are **Phase 2's**, as tasks **2.31** (`hypothetical-questions`) and **2.32** (`raptor`), plus **2.33** (`collapse-to-parent`), which exists because a chunk indexed four ways would otherwise take four of a ranking's top five slots and make every fan-out measurement in 2.16–2.18 look better than it is. Phase 1 exited without ever holding these rows, so until now no phase owned them. Requirements **6** and **3** are the ones touched; Phase 2's exit is unchanged and no fitness function moves. `10` §1.2 corrected in the same commit | 2026-08-17 |
| **S3** | Phase 7 — the agent | **Settled** | Weft's finished form is **agentic**, and the agent is a **first-party pack** rather than the REPL, because `03`'s governing rule keeps logic out of the driving adapter. Added as **Phase 7, after release**, so it is built against published, versioned contracts — which also makes it a harder instance of Phase 5's own proof: a pack built against nothing but the released API. Gated by **G12**. Forced by G8, whose two candidate answers were both wrong in the same way — "shell forever" declines the question and "agentic REPL" puts a planning loop where no other adapter could reach it. Requirements **1** and **4** are the ones touched; no earlier phase's exit moves and no fitness function is activated. `01` → Phase 7; procedure `09` §6.1 and §6.4 | 2026-08-18 |

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
| `06-phase-0-build.md` | The order of work inside Phase 0, what each step made true, where it had to avoid settling G2, and the scope fence | Historical — **retired 2026-08-16**, when Phase 0 exited (`7dae68b`). Its own retirement condition already fired; nothing routes to it as a live guide any more, and `build-ledger.md` is the phase-agnostic source for how to work a task. Packages' and tests' docstrings still cite specific steps of it as the historical reasoning behind code shaped that way — that is a citation, not a routing, and stays |
| `07-extension-cost.md` | The per-kind file cost of adding a capability, and fitness function 9 | Reference |
| `08-manuals.md` | The documents Weft ships to its users, which phase writes each, and the tests that keep them honest | Reference |
| `09-release.md` | Distribution and publishing, the user-facing version policy, the support and deprecation surface, the validation prerequisite, the production-readiness checklist, and the protocol for adjusting this plan | Reference |
| `10-technique-catalogue.md` | Every shipped technique's origin in the literature, whether its common name is earned or borrowed, the plugin name that follows, and whether the reference's implementation is faithful to what it is named after | Reference |
| `11-multimodal.md` | What the reference knows about PDFs, tables, figures and vision, what Weft ships as packs, and the decisions and gate questions multimodal raises | Reference |
| `build-ledger.md` | Task-level state for every phase: what is next, what each task makes true, and the commit that closed it | **Living** — changes every task |
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
