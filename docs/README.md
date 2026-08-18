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
| **Phase** | Phase 1 — Pipelines as data |
| **Blocked by** | **G2** — pipeline derivation semantics, open. Every Phase 1 task is ⚠ until it closes |
| **Next action** | Close **G2** (`05` → G2) |
| **Open decisions** | 5 of 11 — G0, G1, G3, G4, G5 and G6 settled; G2, G7, G8, G9 and G10 open. G0 is logged only; every other row has a session in `05` |
| **Updated** | 2026-08-16 |

`06` names the **three places Phase 0 could accidentally settle G2** — where embedding happens,
what a pipeline is before Phase 1, and what two packs claiming one name does — and fixes the minimal
reversible choice for each. Those choices are not answers, and G2 is still open. The next gate after
the build is **G2**, at the head of Phase 1.

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

- [ ] **G2** Pipeline derivation semantics
- [ ] Phase 1 build
- [ ] **Exit:** the KeyBERT case works from configuration, no copy of the parent

**Phase 2 — Retrieval and generation**

- [ ] **Prerequisite V1–V3** — corpus, question set with ground truth, repeated baseline (`09` §4)
- [ ] Phase 2 build *(no gate)*
- [ ] **Exit:** the router discovers strategies from the registry, not an enum

**Phase 3 — The CLI**

- [ ] **G8** Is the REPL agentic *(if not "shell", hand off to `agentic-patterns` first)*
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
| **G2** | Pipeline derivation semantics | Open | — | — |
| **G3** | Plugin trust model | **Settled** | The threat is **installed-and-ambient**, not malicious — entry points turn *installed* into *executed with your privileges*. Discovery is **eager** (lazy import cannot coexist with bare plugin names, and both alternatives die on G4's conditional registration); posture is **open by default with an exhaustive opt-in pin** of distribution names. Two protections run always: the executed pack set is recorded on every run, and doctor flags ambient packs. Refusals share G4's status vocabulary and never import; policy refusal exits 3, resolution failure 4. Two-tier enforcement is **struck as unimplementable** and survives only as unenforced disclosure; command permission classes are mandatory at registration. Fitness function 8. Specified in `02` §2 → *The trust model* | 2026-08-15 |
| **G4** | Store contract and capability declaration | **Settled** | Tiered protocols with capability **derived** at registration, never declared; text search is a store capability so retrievers never build an index; stores take vectors, never embed; filters are a validated serialisable AST; deletion is idempotent and resumable via a source tombstone; the kernel runner owns `flush`. **pgvector is the floor** — the zero-container target is retired, proof moves to pgvector + Qdrant. Specified in `02` §1 → *The store contract family* | 2026-08-10 |
| **G5** | What flows between stages | **Settled** | A frozen `Node` of six core fields admitted by rule, plus typed extension models that declare their namespace and their transience; lineage required and its sources derived, so deletion reaches every descendant; ids are content digests; stages declare what they read and write, and `Stage[In, Out]` composition is checked at resolution. Specified in `02` §1 → *The payload model* | 2026-08-10 |
| **G6** | Sync or async core | **Settled** | **Async only, no exceptions** — no sync protocol, no sync facade, no declared colour, and one `asyncio.run` in the tree at the CLI entry point. A pack may not be sync-only; blocking calls are caught categorically at the stage seam (fitness function 7). Streaming is a `TokenSink` service, not a second contract; the runner keeps one batch in flight. Specified in `01` → *Colour* | 2026-08-10 |
| **G7** | Event bus or explicit extension points | Open | — | — |
| **G8** | Is the REPL agentic | Open | — | — |
| **G9** | Contract versioning and deprecation | Open | — | — |
| **G10** | Release and support policy | Open | — | — |

Statuses: **Open** · **Settled** · **Reopened** — a settled decision found wrong is set back to
Reopened with the date and reason, never quietly edited.

---

## Documents

| File | Owns | Kind |
|---|---|---|
| `README.md` *(this file)* | Status, execution state, decision log, document manifest | **Living** — changes every session |
| `01-high-level-plan.md` | Why rebuild, the architecture stack with costs, **the kernel boundary**, **the async colour**, runtime shape, deferred list, **the phase script**, fitness functions and the kernel budget, risks | Reference |
| `02-extension-model.md` | Contracts, who publishes them, what a plugin receives, the payload model, the store contract family, packs and discovery, **the trust model**, pack settings, pipelines as data, both driving use cases | Reference |
| `03-cli.md` | The CLI as driving adapter, command surface, permissions **including the class every plugin command must declare**, output | Reference |
| `04-reference-inventory.md` | What to lift from `a prior project`, what to rewrite, what to leave, where each item lands — kernel or pack — the reference's node metadata surface, **and its storage layer after G4** | Reference |
| `05-grilling-sessions.md` | The substance of every gate session — G1 through G10 | Reference |
| `06-phase-0-build.md` | The order of work inside Phase 0, what each step makes true, where it must not settle G2, and the scope fence | Reference — retire when Phase 0 exits |
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
