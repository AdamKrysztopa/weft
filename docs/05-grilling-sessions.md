# 05 — Open decisions and grilling sessions

This plan settled the architecture and left eleven decisions to grilling sessions, G1 through G11.
**Two more were added by sessions that ran** — G12 by G8 (2026-08-18) and G13 by Phase 5's own failed
exit criterion (2026-08-22) — which is the intended shape: a session that discovers a question it was
not asked files it rather than answering it.
Each is here because **defaulting it would be a mistake** — either it has no obviously right answer, or getting
it wrong is expensive to reverse, or it depends on how you actually intend to work.

Each gets a grilling session: a focused adversarial conversation whose job is to attack the
candidate answers, not to be agreeable about them. Run one with `/grilling`, one topic at a time.

**Do not batch these.** A grilling session works by pushing on one position until it either holds
or breaks. Four topics in one sitting produces four shallow answers, which is worse than none,
because a shallow answer looks settled.

---

## Ordering

Sessions are gated by what they block. G1, G5 and G6 must be resolved before Phase 0 writes a line
of kernel code, because all three change the shape of the kernel itself.

**Status is not recorded here.** Whether a session is open, settled or reopened, and what it
concluded, lives in the decision log in `README.md`. This document owns only the substance of each
question, so that a decision's status has exactly one home.

| Order | Session | Blocks | Reversibility |
|---|---|---|---|
| 1 | **G1** Kernel boundary | Phase 0 | Very low — this is the architecture |
| 2 | **G5** Stage payload typing | Phase 0 | Very low — every contract depends on it |
| 3 | **G6** Sync or async core | Phase 0 | Very low — colours the entire API |
| 4 | **G2** Pipeline derivation semantics | Phase 1 | Low |
| 5 | **G4** Store contract and capabilities | Phase 0 store work | Low |
| 6 | **G3** Plugin trust model | Phase 0 discovery | Medium |
| 7 | **G7** Event bus or explicit extension points | Phase 5 | Medium — settled 2026-08-21 |
| 8 | **G8** Is the REPL agentic | Phase 3 | Medium, but expensive if retrofitted |
| 9 | **G9** Contract versioning policy | First external pack | High — a policy, changeable |
| 10 | **G10** Release and support policy | Phase 6 | Medium — a policy, but published |
| 11 | **G11** Kernel error text | Phase 3 | Low — settled 2026-08-18 |
| 12 | **G12** Permissions when the caller is never a TTY | Phase 7 | Medium — a safety boundary, not a mechanism |
| 13 | **G13** The derived-participant seam | Phase 6 | Medium — two of its three faces move published contracts |

---

## G1 — What belongs in the kernel?

**The question.** Where exactly is the line between kernel and first-party pack?

**Why it cannot be defaulted.** This is the whole architecture. A microkernel's two failure modes
sit on either side of this line: a kernel that grows until plugins are decoration, and a kernel so
thin that every plugin reimplements the same plumbing. The reference failed **both ways at once** —
multimodal config ended up as a field on the central context object, *and* that object was bypassed.

> **Corrected from the reference study (2026-08-10).** The first half is confirmed: `multimodal_config`
> is one of 10 `EngineContext` fields (`core/engine/context.py:67-100`). The second half is new, and
> it reframes this session. Only **6 classes in 259 files** take an `EngineContext`-annotated
> `__init__` parameter (`UnifiedChatEngine`, `QueryRouter`, `DocumentStorage`, `FusionRetriever`,
> `IndexingCommand`, `IndexingPipeline`). What strategy handlers actually receive is a *second*
> context, `StrategyContext` (11 fields, `core/engine/types.py:291-372`), carrying a *third*,
> `EngineMetadata` (14 fields, `:215-288`). `StrategyContext` duplicates `llm` and `prompt_executor`
> and **does not carry `tenant_id`**; `EngineMetadata` mixes identity with 7 tuning knobs copied out
> of `RuntimeGuardrailsConfig`. *"The one passport idea has fissioned into three overlapping bags."*
> So the question is not only "how big is the kernel" but **"does a plugin receive one object or
> three, and which one carries tenancy"** — the reference's answer being that the tenant id lives on the
> object plugins do not get. Note also `llm: Any`, annotated *"typed `Any` for flexibility in tests"*
> (`context.py:51`), which defeats typing at the single most important seam.
> (`reference/study/10-doc-corrections.md` C2; `reference/study/09-open-questions.md` C-6.)

**Positions to attack.** *Minimal*: registry, pipeline model, ports, context, errors. Everything
else is a pack, including prompts and observability. *Pragmatic*: the above plus the prompt layer
and span helpers, on the grounds that every pack needs them and duplicating them is worse.

**Bring.**

- The category A reference list from `04` — as corrected against `reference/study/08-salvage.md` — and for each
  item an argument for which side of the line it sits on.
- **The three-context fission above.** Decide once whether a plugin gets one passport, and what is
  on it.
- **The prompt layer's hard blocker, which decides the session rather than colouring it.**
  `core/prompt/` (9 files, 2,070 lines) is genuinely the extension model done right — 41 typed
  prompts, `override()` for A/B, frozen `PromptMetadata` carrying `version`, locale-key translation
  by construction. **But `PromptLoader` resolves locales as
  `Path(__file__).parent.parent / 'locales'`**, so a pack cannot ship its own prompts or its own
  translations. "Prompts: kernel or pack?" is therefore not a taste question — **whichever side it
  lands on, the locale-resolution mechanism has to change, and that is a Phase 0 design item.**
  (`reference/study/10-doc-corrections.md` E16; `reference/study/08-salvage.md` §T1.8.)

- **Where a pack puts its settings.** `02` §2 establishes that a per-pack config namespace is a
  distinct requirement from per-stage `with:` config, and that driving use case B needs both — but
  no gate owned it until this line. The reference has nowhere at all: `IndexingStrategy`
  (`core/config/models.py:208-216`) has 3 fields and enhancers get names only, so a pack
  contributing an enhancer, a retriever and a store has no place for its configuration. Decide the
  namespace's shape here, because Phase 0 publishes the contracts a pack is written against and a
  pack contract with no settled home for pack settings breaks on the first real add-on — which is
  precisely what Phase 5 exists to test.

**Done when.** Every item in `04` is assigned to kernel or pack, there is a stated numeric kernel
budget for fitness function 3 with a reason attached, there is a decision on how many context
objects a plugin receives and which one carries `tenant_id`, and the per-pack config namespace has
a defined shape (or an explicit, dated deferral naming what unblocks it).

**Where the answers live.** The rule, the kernel/pack table, the packaging and the two consequences
worth watching are `01` → *The kernel boundary*; the budget and its revision rule are `01` →
*Fitness functions* 3; what a plugin receives and who publishes a contract are `02` §1; the pack
settings namespace and catalogue contribution are `02` §2; the per-item assignment is `04` →
*Kernel or pack*. This session's status is in `README.md`, as with every other.

---

## G2 — Pipeline derivation semantics

**The question.** Exactly what do `extends`, `insert`, `replace`, `remove` and `set` mean at the
edges, and are pipelines authored in YAML, in Python, or both?

**Why it cannot be defaulted.** The easy cases are obvious and the hard ones are not: multi-level
inheritance, a parent changing a stage a child overrode, inserting relative to a stage that a
parent removed, two packs contributing fragments that both want to be after `chunk`.

**Positions to attack.** *Flat overlay*, single level of inheritance only, refusing depth to keep
semantics trivial. *Full chain*, arbitrary depth with precedence rules. *Python-first*, where YAML
is a serialisation of a builder API rather than the authoring surface. **A fifth position the study
adds: an ordering-constraint concept, so a pipeline is a constrained order rather than a list** —
see Bring.

**Bring.**

- The KeyBERT case, plus three deliberately nasty cases you invent.
- **The cleaning chain, as the case that breaks a naive operator set.** `indexing/cleaning/pipeline.py:30-51`:
  *"HyphenationFixer — MUST run before whitespace normalization while newlines still exist (e.g.
  kompu-\\nter -> komputer); TableLinearizer — Detect columns based on whitespace gaps, MUST run
  before whitespace normalization collapses gaps; WhitespaceNormalizer — this is destructive and
  must run last. **IMPORTANT: Changing this order will break functionality.**"* `insert` lets a
  third party place a stage between `HyphenationFixer` and `WhitespaceNormalizer` and **silently
  corrupt text**. The constraints exist in the reference as prose only.
- **The ingest order itself.** The reference chunks *then* cleans, and has a stage 0 and a stage 4.5 the
  plan's list omitted (see `02` §3). G2 must state which order Weft adopts and why, because `01` and
  `02` previously asserted the other one.
- **Name collisions.** Two packs both registering `keybert` has no defined outcome in the reference —
  six registration decorators, four different collision behaviours, four of them overwriting
  silently with no check at all. G2 currently covers *position* conflicts ("two fragments that both
  want to be after `chunk`") but not *name* conflicts. See `reference/study/09-open-questions.md` C-12.
  **G1 removed one class of this and sharpened the rest:** pack *settings* are keyed by distribution
  name, which cannot collide, so `packs:` needs no arbitration. Plugin names still can, and they are
  now the only unarbitrated namespace in the system — ext namespaces are distribution-keyed too (G5).
  **G3 closed off the escape route.** Namespacing pipeline references by distribution
  (`use: weft-docling/docling`) was considered as the way to make discovery lazy and rejected — it
  couples the data format to packaging and makes every derived pipeline worse — so **pipelines keep
  bare names**, and G2 cannot resolve collisions by qualifying the reference. Arbitration has to
  happen at registration. G3 does supply one lever that did not exist before: under an active
  allow-list, an operator can refuse a colliding pack outright, which is a remedy but not a rule.
- **What G5 gave this session, and what it pointedly did not.** `requires`/`provides` are checked at
  resolution, so `insert` can no longer place a stage before the thing it reads — ordering by **data
  dependency** is solved, and comes with an error naming the stage, the namespace and the pack. The
  cleaning chain is **not** solved by it: `WhitespaceNormalizer` must run last because it is
  *destructive*, not because anyone reads its output, and no data-dependency graph can see that.
  Inventing a representation for a *semantic* ordering constraint remains this session's hardest
  item, and it is now the only part of the ordering problem still open.
- **A choice G4 forced onto this session: there must be an embed stage, or an embedding step inside
  the store stage.** G4's stores take a **vector**, never text — a store coupled to an embedding
  model cannot be used with two models or none. The reference had **no embed stage at all**; embedding
  happened inside storage, which is why `query()` took a string. So the ingest order G2 settles must
  name where the vector is produced, and the query path must embed before it searches. This is a new
  stage in a list this session was already re-deciding.
- **The one reference field shaped like this YAML is dead.** `CleaningConfig.processors`
  (`core/config/models.py:51-54`) is never read; the executor reads six individual `*_enabled`
  booleans, two of them gated on `config.language == 'pl'`. A stage list the executor does not
  consume is worse than no stage list — and **language-conditional stages are a real requirement the
  current YAML model cannot express.**

(`reference/study/10-doc-corrections.md` E7, E8, E5, A12.)

**Done when.** Every operator has stated conflict behaviour, ordering constraints have a
representation, name collisions have a defined arbitration rule, and a resolution failure has a
defined error shape naming the conflicting sources.

**Settled 2026-08-16.** All four conditions met. The load-bearing move was refusing the fifth
position rather than adopting it: a pipeline stays an **ordered list**, resolution *checks* the order
and never solves it, because a resolver that quietly finds a working arrangement is the same species
as the silent fallback `01` rules out everywhere else — and the refusal names the positions that
would be legal, which is rule 5's shape.

Three answers are worth recording as *arguments* rather than outcomes, because each is what stopped a
worse design:

- **Ordering constraints are the mirror of `requires`/`provides`, not references between plugins.**
  `Before(WhitespaceNormalizer)` fails on inspection: it makes one pack import and name another, and
  it protects against that one class, so a third party's normalizer corrupts text again. Read what
  the reference's own docstring says the dependency *is* — *"while newlines still exist"*, *"whitespace
  gaps"*, *"destructive"* — and nobody depends on a plugin; they depend on a **property of the text a
  later stage annihilates**. Hence `intact` / `destroys`, with `destroys` mandatory because
  forgetting it harms strangers while forgetting `intact` harms only yourself.
- **The language requirement was misdiagnosed as needing conditionals.** The condition is real; what
  is wrong is what it reads. `config.language` is run-wide, so a mixed corpus is uniformly wrong for
  half its documents with no signal. Language is a fact about a **node**, and the answer needs no new
  construct — applicability over that fact, plus vars for the *decision* half (a translation target),
  with the rule that **vars never participate in applicability** so the two can never disagree.
- **A subclass per failure kind, not one class with a `kind` field.** Decided on evidence: task
  0.14's ratchet derives its documented set from `WeftError` subclass *names*
  (`tests/docs/test_troubleshooting_coverage.py:87-119`), so a fat class would present one
  already-documented name and let a dozen new failure modes ship undocumented — the exact hole that
  ratchet was built to close.

The session also answered `11`'s three filed questions. **G2-a** answers itself: G4 forbids a store
to embed, so embed stays a stage and the pixel path stays buildable. **G2-b** is yes, and the
property mechanism is how. **G2-c** dissolves: applicability at the seam means a per-node path needs
no branch construct, so a pipeline remains one straight line.

**Two things it deliberately did not settle.** The exact predicate form for applicability over a
*value* (`Language('pl')`) rather than over an ext model's presence is a Phase 1 ledger item, not a
gate outcome. And the kernel budget: G1 allowed 600–900 lines for discovery, pipeline and derivation
machinery, and this outcome adds property markers, applicability routing, slots and vars on top of
that. It stands at 1,240 of 3,500 — not a breach, but Phase 1 is where the 2,800 review trigger
becomes plausible, and it is better said here than discovered at task 1.9.

**Where the answers live.** The whole outcome is `02` §3 — the model, `intact`/`destroys`,
applicability, slots, derivation and its operator edges, vars, the absence of a canonical ingest
order, the authoring surface, and the failure family. The two checks it turns on are `01` →
*Fitness functions* 11. The name-collision pin is `02` §3, *When resolution fails*, and the operator
policy file it lives in is `02` §2. The doctor surfaces it adds are `03`. Its consequences for
multimodal are `11` → *Gate questions*. This session's status is in `README.md`, as with every other.

---

## G3 — Plugin trust model

**The question.** Entry-point discovery executes third-party code. What is the security posture?

**Why it cannot be defaulted.** This is the security decision of the project, and the convenient
answer — discover and import everything installed — is a supply-chain hole that is hard to close
later without breaking every pack.

**Positions to attack.** *Open*, anything installed is trusted, because installing is already
trusting. *Allow-listed*, packs must be named in `weft.toml` before they load. *Two-tier*, where
discovery is open but capabilities that touch the filesystem, network or shell need explicit grant.

**Bring.**

- The CLI permission classes from `03`, since a coherent answer probably reuses them.
- **The reference's actual security posture, which is *no contract at all* — and one concrete hole that
  predates entry points.** The BM25 node cache is a **pickle** file (`retrieval/utils.py:48`,
  `pickle.load(f)  # noqa: S301`, guarded only by `CACHE_VERSION: int = 1`), so the reference already
  executes arbitrary code from disk with no signature. `pickle.load` appears on 3 read paths, there
  are **zero path-containment checks** anywhere, and `SecretStr` is used **once**. This is the
  concrete case that makes the *two-tier* position argue itself, and Weft must not inherit that
  cache format. (`reference/study/10-doc-corrections.md` E15; `reference/study/04-cross-cutting.md` §11.)

- **What G4 removed from this session's scope, and what it added.** The pickle exhibit is **gone**:
  under G4 text search is a store capability, retrievers never build an index, and the BM25 node
  cache has no successor — so that attack surface does not exist in Weft and the two-tier argument
  has to stand on entry points alone. What G4 added is a reporting requirement that overlaps this
  session's last item: a pack with optional dependencies probes at `register()` and registers only
  what works, so `plugins doctor` must already print *what registered, what didn't, and why*. The
  refused-pack case is the same surface, and it should not be a second mechanism.

**Done when.** There is a stated posture, a defined behaviour for an untrusted pack, and a decision
on whether `weft plugins doctor` shows packs it refused to load — it should.

> **All three met. Two of the three listed positions did not survive, for different reasons.**
> *Two-tier* was struck as **unimplementable**, not merely unattractive: CPython has no in-process
> boundary that constrains `open`, `socket` or `subprocess`, so any grant is a declaration a pack
> makes about itself. It survives only as unenforced **disclosure**, worded so it cannot be mistaken
> for a control. *Allow-listing as the default* was rejected on cost — it breaks the stated property
> that `uv add weft-graph` alone adds a capability, and a posture demanding a manual step per install
> gets disabled wholesale — so it ships as an **exhaustive opt-in pin** instead, with the always-on
> protections carried by the recorded pack set and by doctor's ambient flag.
>
> **The session also corrected `02`.** Its claim that discovery is lazy cannot be true alongside bare
> plugin names in pipelines, and the two designs that would have restored laziness both die on G4's
> conditional registration. Discovery is eager; the correction is recorded in place.

**Where the answers live.** The threat model, the posture and its pin, the status vocabulary, the
refusal behaviours and the disclosure model are `02` §2 → *The trust model*; eager discovery and its
two riders are `02` §2 → *Packs and discovery*; the mandatory permission class on plugin-contributed
commands, doctor's statuses and the exit-code split are `03`; fitness function 8 and its phase
activations are `01` → *Fitness functions*, Phase 0 and Phase 3. Status is in `README.md`.

---

## G4 — The Store contract and capability declaration

**The question.** What is the common store surface, how does a backend declare what it supports,
and what happens when a pipeline needs a capability the configured store lacks?

**Why it cannot be defaulted.** Storage elasticity is a hard requirement, and backends genuinely
differ: hybrid search, metadata filtering, full-text, graph traversal, transactional delete. A
lowest-common-denominator contract makes every backend weak; a union contract makes every backend
implement stubs that fail at runtime.

**Positions to attack.** *Narrow core plus capability flags*, where a pipeline needing hybrid
search fails at resolution against a store that cannot do it. *Capability objects*, where a store
returns a description and the pipeline adapts. *Tiered contracts*, where `Store`, `HybridStore` and
`GraphStore` are separate protocols and a backend implements what it can.

**Bring.**

- Three real backends with genuinely different shapes — pgvector, Qdrant, and a local embedded store
  — plus the zero-container requirement from `01` (now sharpened: the reference's `DocumentStorage.__init__`
  imports the PGVector adapter unconditionally, even for a purely local run).
- **The driver constraint G6 imposed, which narrows the candidates before this session picks any.**
  The core is async-only, so a store adapter is `async def` throughout: pgvector needs `asyncpg` or
  async `psycopg3`, **not `psycopg2`**. And the zero-container store is the awkward case — SQLite and
  a local file store have no async driver at all, so that adapter must offload internally or it
  blocks the loop for every other task. Fitness function 7(b) fails the build the moment it touches
  the filesystem inside the loop, which is the good outcome, but it means *"the local store is the
  simple one"* is false here: it is the one with the bridge inside it.
- **The reference already ran the capability experiment, badly. It declares capability by *undeclared
  attribute*** — the failure mode the *capability flags* position must beat. All of it:
  `hasattr(storage_adapter, 'hybrid_search')` plus `getattr(..., 'hybrid_search', False)`, with an
  error string hard-coding the environment variable `PGVECTOR_HYBRID_SEARCH=true`
  (`retrieval/registry.py:517-528`); `hasattr(context.storage_adapter, 'get_vector_index')` deciding
  adapter-backed vs disk-backed index loading (`:250`); `ensure_pgvector_strategy_compatibility`
  hard-coding the allowed set `{'vector','keyword'}` (`retrieval/utils.py:63-85`);
  `isinstance(adapter, LocalFileSystemAdapter)` guards that make three safety checks return
  `all_passed=False` for any non-local adapter (`retrieval/safety_checks.py:96,147,188`) and
  corruption detection return `('incomplete', ['Adapter is not LocalFileSystemAdapter'])`
  (`retrieval/corruption_detector.py:83,364`); and `_determine_required_strategy_types` returning an
  **empty set** for anything that is not `'postgres'` (`retrieval/retriever.py:414-426`), so a remote
  store silently inherits local tolerance for missing indices. **17 dispatch sites over backend
  identity, zero registry lookups.**
- **The exact list of what the `Store` contract must cover, derived from where the reference's leaks.**
  `retrieval/` owns **92 of the library's 138 `# type: ignore` lines (67%)**, and ~40 of them are one
  structural fact repeated: the storage port does not expose what retrieval needs, so retrieval
  reaches **through** it into private attributes of the concrete adapter. The four names are
  `_vector_indices`, `_strategy_for_nodes`, `indices_dir` and `update_file_metadata` — none of which
  is on `BaseStorageAdapter` (`core/ports/storage.py:26`). See `retrieval/_index_builder.py:107,206,248,262,283`
  and `retrieval/storage.py:1288`. The declared contract is 6 adapter methods; the *actually
  required* contract is those 6 plus **12 undeclared members**.
- The port's own good bones, so they are not thrown out with the leak: `VectorStoreFactory`
  (`core/ports/storage.py:177-239`) is three intent-named methods returning typed models, and
  `ConnectionInfo` is clean. What has to change is documented at `reference/study/08-salvage.md` §T2.4 —
  kill `**kwargs: Any` (12 concrete keyword arguments flow through it), slim `VectorStoreMetadata`
  (21 fields), drop the two methods with zero call sites, and note that **`persist()` has no
  transactional semantics** at 9 call sites.
- `retrieval/storage.py` is **2,347 lines, the largest file in the library**, and the BM25 node cache
  is a pickle. Weft must not inherit that format (see G3).
- **Three requirements G5 handed this session (2026-08-10).** (i) `Store` accepts a `Node` **minus
  its transient namespaces** — the kernel strips them at this seam, so the store never sees them and
  never has to know they existed. (ii) **`delete(source)` cascades and returns the removed set.**
  Every node whose derived `Lineage.sources` contains the deleted document goes with it, which means
  removing one document removes the RAPTOR root summary; the rebuild needs to know what went, so the
  return value is part of the contract, and transactionality across a cascade is this session's
  problem. (iii) **Stores must be able to filter on ext-namespace fields**, or the graph pack cannot
  query the data it wrote — which makes this a capability, not an assumption, and puts it squarely in
  the capability-declaration design rather than beside it.
- **Two things G1 changed about this session's frame.** The `Store` contract is **published by
  `weft-store`, not the kernel** — the kernel owns the contract mechanism and names no capability —
  so whatever capability machinery this session designs lives in that pack and cannot leak inward.
  And there is now a precedent for how a backend declares what it supports: a plugin already
  declares its `lifetime` as a class attribute the kernel reads, which is the *capability
  declaration* pattern the study extracted. Reuse it rather than inventing a second mechanism, and
  note that the failure it must beat is the reference's declaration-by-`hasattr`, 17 dispatch sites over
  backend identity with zero registry lookups.

(`reference/study/10-doc-corrections.md` E13, E14, A9; `reference/study/09-open-questions.md` C-4, C-8.)

**Done when.** The contract is specified, at least two backends are shown to satisfy it without
stub methods, the zero-container path is demonstrated as expressible, and **none of
`_vector_indices`, `_strategy_for_nodes`, `indices_dir` or `update_file_metadata` requires reaching
through the contract.**

> **The third criterion was not met; it was retired.** G4 decided that one container — pgvector — is
> the floor, on the grounds that an embedded store good enough to develop against is *almost* the
> same as the production one, and almost is the expensive kind of different. The over-fitting guard
> it existed to provide moved rather than vanished: the contract is proven on **pgvector and
> Qdrant**, and an ephemeral in-memory store covers tests and demos without pretending to be a
> backend. `01` → *Runtime shape* records the amendment in full.

**Where the answers live.** The contract family, derived capabilities, `needs_store`, the filter
AST, durability, resumable deletion and `SourceRecord` are `02` §1 → *The store contract family*;
the floor and the in-memory store are `01` → *Runtime shape*; what is lifted from the reference's
storage layer and what is left is `04` → *Storage, after G4*. Status is in `README.md`.

---

## G5 — What flows between stages?

**The question.** How strongly typed is the payload passing from one pipeline stage to the next?

**Why it cannot be defaulted.** The hardest question in the design. Too loose — a dict — and stage
composition has no safety at all, and you rediscover the reference's habit of stuffing transient keys
into node metadata and scrubbing them before storage. Too rigid and no third party can add a stage
carrying data the core never anticipated, which breaks requirement 1.

**Positions to attack.** *Typed envelope with an open extension map*, a core schema plus a
namespaced area packs write into. *Generic over a payload type*, pushing composition safety into
the type system at the cost of a steep API. *Fully open documents*, with validation at stage
boundaries rather than in types.

**Bring.**

- The KeyBERT case, which must attach keywords a core schema does not know about, and the graph
  case, which must attach entities and relations.
- **What G1 already fixed, so this session does not reopen it.** Every contract returns an
  `Outcome` — `Produced` / `NothingToProduce` / `Failed` — because the kernel's fallback combinator
  matches on it and must never inspect payload content. That settles the *result* type and answers
  §1's open question: a backend can report definitive success-with-no-content and stop the chain.
  What remains G5's is the **payload** carried inside `Produced`, which is the harder half.

**Done when.** Both cases are expressible, and there is a stated answer for what happens when a
stage receives a payload missing something it needs.

**Where the answers live.** The `Node` model, the admission rule for core fields, `ExtModel` and
declared namespaces, `__transient__`, `requires`/`provides`, the three construction paths, derived
`sources`, cascade on delete, content-addressed identity and `Stage[In, Out]` are all `02` §1 → *The
payload model*; the resolution-time checks are `02` §3; the reference evidence the model was designed
against is `04` → *The node metadata surface*. Status is in `README.md`.

---

## G6 — Sync or async core?

**The question.** Is the kernel async-first, sync-first, or both?

**Why it cannot be defaulted.** It colours every contract signature and cannot be changed later
without touching all of them. The reference was sync with **one** `asyncio.run` bridge inside an
enhancer, which is the outcome nobody chooses deliberately.

> **Corrected from the reference study (2026-08-10):** the plural was wrong and the danger is sharper
> than "nobody chooses this". There is **exactly one** `asyncio.run` call site in 259 files:
> `indexing/enhancers/vision_description.py:74`. The library has **6 real `async def` bodies and 10
> `await`s**, and **no blocking call sits inside an async function** — the colour discipline itself
> held. What did not hold is the *safety* of that one bridge: it is guaranteed **only by a docstring
> plus a caller in `system/`** — *"Safe only in `asyncio.to_thread()` workers — never in FastAPI"* —
> so calling the method directly from a route raises
> `RuntimeError: asyncio.run() cannot be called from a running event loop`. A sibling docstring
> records *"Reset to `None` by the adapter before each `asyncio.run()` call"*: per-call mutable state
> maintained by the caller, again by prose. (`reference/study/10-doc-corrections.md` B6;
> `reference/study/04-cross-cutting.md` §8.)

**Positions to attack.** *Async-first*, with a thin sync facade, on the grounds that embedding and
model calls are IO-bound and concurrency is where the throughput is. *Sync-first*, on the grounds
that a library used from notebooks and scripts should not force an event loop.

**Bring.**

- The CLI's streaming requirement from `03`, and the fact that a service tier is deferred but not
  forbidden.
- **The two docstrings quoted above.** They are the concrete evidence that a colour convention
  enforced only by prose is a latent incident, which is the strongest available argument for this
  session deciding a **type-level marker** rather than a convention.
- **The three kernel surfaces G1 created, all of which this session must colour.** `Stage.run`,
  `Context.require`, and — the two that are not merely signatures — the **fallback combinator**,
  which awaits each plugin in turn, and the **instance cache**, whose lock is a different object in
  an async world. A pack declaring `Lifetime.PROCESS` accepts a concurrency obligation whose meaning
  depends entirely on this answer, so "may a pack be sync-only" is not a side question here.
- **Two more from G5.** The **runner's batching loop** — a stage takes a sequence and the kernel
  feeds batches, so whether batches overlap in flight is a throughput decision this session owns, not
  a later optimisation. And the **resolution-time composition check**, which is pure computation over
  declared types and should stay colourless; if it does not, the colour has reached the config
  loader, which is a warning about the answer rather than a detail of it.

**Done when.** Contract signatures have a stated colour, and there is a decision on whether a pack
may be sync-only.

**Where the answers live.** The colour decision, its four consequences and the runner's concurrency
are `01` → *Colour — the core is async, without exception*; the enforcement is `01` → *Fitness
functions* 7; the async signature, the cancellation obligation and the `TokenSink` are `02` §1 →
*What a plugin receives*; the CLI's side of streaming and the single `asyncio.run` are `03` →
*Output*. Status is in `README.md`.

---

## G7 — Event bus, or explicit extension points only?

**The question.** Can a pack observe things it has no extension point for?

**Why it cannot be defaulted.** `01` defers the event bus, and that deferral is only correct if
explicit extension points genuinely cover the add-on cases. The graph pack is the test: it may want
to observe every indexed node without owning a stage.

**Positions to attack.** *Extension points only*, keeping the system traceable and refusing the
bus until a case cannot be served. *Lifecycle hooks*, a small fixed set of named events with no
general bus. *Full in-process bus*.

**Bring.** The graph pack, and one deliberately awkward capability such as an audit log.

**Done when.** The graph pack is shown to work without a bus, or the bus is justified by a case
that provably cannot be served otherwise.

---

## G8 — Is the REPL agentic?

**The question.** Is the interactive session a command shell, or a model that plans and calls tools?

**Why it cannot be defaulted.** These are different products. If the answer is yes, the design
belongs to a different decision tree — autonomy level, tool contracts, human approval, reasoning
loop — and the `agentic-patterns` skill owns it. Building the shell and retrofitting a loop is the
expensive order.

**Positions to attack.** *Shell*, per `03` Phase 3. *Agentic*, where the model chooses which
pipeline to run and which retrieval strategy to try. *Shell with an agentic mode* as a pack, which
is the interesting third option because it tests whether the CLI extension model is strong enough
to carry it.

**What G3 handed this session.** Every command now declares a permission class at registration, with
no default — so if a model is choosing commands, `overwrite` and `destroy` are exactly the boundary
where autonomy has to stop, and the machinery to find them already exists and cannot be forgotten.
That makes the *agentic* position cheaper to reason about than it was, and it sharpens the question
this session must answer: `03`'s rule is that a non-interactive `ask` **fails** rather than
proceeding. An agent is not a TTY. Whether an approval loop counts as interactive is a decision, and
answering it wrong turns a safety rule into either a blocker or a rubber stamp.

**Done when.** A position is chosen, and if it is anything but "shell", a handoff to
`agentic-patterns` is scheduled before Phase 3.

---

## G9 — Contract versioning and deprecation

**The question.** What does a contract version mean, and what is owed to a pack when one changes?

**Why it cannot be defaulted.** A contract version moving is the only signal a pack author gets, and
nothing states what a move obliges. The first external pack makes this real and it is a promise, so
it is better made deliberately than discovered.

*(Corrected 2026-08-21, at the session. This paragraph read "Fitness function 6 enforces that
versions move, but not what a move obliges." **It does not — there is no `test_ff6_*` in
`tests/architecture/`.** Six unit-test docstrings across the packs describe the constant as one
"fitness function 6 will eventually check", and the eleven contract-version bumps in the tree
happened because people were diligent. The gate was being argued partly on the belief that a check
existed; logged as `lessons.md` L5.4, and the session's ruling turns FF6 into a real check with a
real subject. The argument for the session is unaffected and now rests on a fact.)*

**Positions to attack.** *Semver per contract* with a stated support window. *Single library
version* with all contracts moving together, which is simpler and coarser. *Capability negotiation*,
where a pack declares the range it supports and the kernel refuses incompatible loads.

**Bring.**

**A question G5 created, and the sharper of the two:** an `ExtModel` is a **schema in a database**.
`GraphData` is declared by a pack, validated on write and persisted inside every node the pack
touched — so a pack that adds a required field, renames one, or changes a type breaks data already
stored, and does it to *users' indexes*, not to its own test fixtures. Contract versioning that
covers only call signatures misses this entirely. The reference's V1→V2 schema-migration validator
(`reference/study/08-salvage.md`) is the salvage item, and this is now the first-party case rather than a
hypothetical: `weft-graph` 1.1 must be able to read what `weft-graph` 1.0 wrote, or say precisely
why it cannot.

**Two more from G4.** The store is a *family* of protocols, so adding a method to `VectorSearch`
breaks **every backend at once**, first-party and third-party alike — capability protocols are the
most brittle published surface in the system and the policy has to say what a change to one obliges.
And the **filter AST is a serialised format**: filters live inside stored pipelines, so its shape is
versioned data, not just an API.

**Two small ones from G3, both published surfaces that will look like details until they break.** The
`Disclosure` model and the mandatory permission-class `ClassVar` on `Command` are kernel-published
contracts, so fitness function 6 covers them and this session owes them a policy — adding a required
`Disclosure` field breaks every pack that ships one. And the `[packs] allow` key is **operator
configuration in `weft.toml`**, which is the one format whose compatibility promise is owed to people
who never read a changelog.

**What G7 handed this session, 2026-08-21.** G7 closed by adding **two published Protocols to the
store family** rather than a bus — `SourceDeletable` and `Reconcilable` — which lands squarely on the
brittleness this session already identified: a capability Protocol is the most exposed surface in the
system, because adding a method to one breaks every backend at once. That is now not a hypothetical
about `VectorSearch` but a fresh, first-party instance created *after* the concern was written down.

It also hands this session a **second persisted schema**. `ReconcileReport` is what `reconcile`
returns, and a pack that records what it repaired has stored it — so the `GraphData` problem above
("a schema in a database") now has a sibling that the kernel's own first-party packs will ship. And
`ReconcileMode` is an `Enum` on a published contract: **adding a member is not a breaking change for a
caller but is one for an implementer** that exhaustively matches it, which is a case a call-signature
policy misses in the same way it misses stored data.

Finally, G7 made `weft-cli[otel]` an **optional extra**, so this session inherits a small question it
should answer explicitly rather than by implication: whether an extra is part of a distribution's
compatibility promise, or a convenience outside it.

**A question G1 created and did not answer:** contracts are published by *first-party packs*, not by the kernel, and the repository now ships several distributions (`weft-kernel`,
`weft-cli`, `weft-llm`, `weft-prompts`, `weft-extract`, `weft-store`, `weft-eval`, …). So skew is no
longer only a third-party problem — a user can install `weft-store` 2.0 against `weft-kernel` 1.4,
and the `Extractor` contract a third-party pack compiles against belongs to a distribution that
versions independently of the kernel. Whatever policy this session states has to cover the
first-party case first, because that is the one that will happen by accident.

**Done when.** There is a stated policy, a defined behaviour when a pack requires a contract version
the kernel does not offer, and a decision on whether `weft plugins doctor` reports version skew — it
should.

---

## G10 — The release and support policy

*(`09` recommends a position on two of this session's questions — the unit of release (`09` §1) and
what 1.0 rests on (`09` §2.2). Each recommendation is carried below as the **case to beat**, with the
argument against it stated beside it. That is what makes this a session rather than a ratification: a
gate is not advice, and a gate whose positions arrive pre-judged is not a gate.)*

**The question.** What is the unit of release when one repository ships several independently versioned
distributions, what does 1.0 promise, and what is owed to a user or a pack author when a published
surface changes?

**Why it cannot be defaulted.** G9 decides what a *contract* version means; this decides what an
*installation* means, and the two are different numbers answering different questions. Defaulting it
produces the answer that is easy at the moment of release — bump everything together — which `09` §1
argues is exactly the answer that gives first-party packs a release path a third-party pack cannot have,
against rule 4. That argument is the session's first position, to be tested rather than assumed. This is
the one gate whose subject is a promise to people outside the repository, so it is the one where "we can
change it later" is least true.

**Positions to attack.** Three on the unit of release. `09` §1 recommends the third; the recommendation
is the case to beat and it is stated here with the counter-argument beside it, not with a verdict.

- **Lockstep versioning** — one number for all distributions, simple and coarse. `09` §1 argues against
  it: it is a release path a third-party pack cannot have, which is rule 4 rotting at the packaging
  layer, and it makes the kernel's version meaningless as a compatibility signal. *Attack that:* one
  number a user can hold in their head may be worth more than a precise one they have to look up, and
  the privilege objection is about who *may* release, not about who *does*.
- **Independent semver per distribution, and nothing else** — honest about what actually changes. `09`
  §1 argues it is insufficient on its own, because *"which versions were tested together"* has no
  answer. *Attack that:* the answer could be a documented, tested combination in the release notes
  rather than a distribution, which costs nothing to publish and nothing to keep exact.
- **Independent versions plus a named release set** — a code-free meta-distribution pinning an
  exactly-tested combination. `09` §1 recommends it, on the ground that it is the only one of the three
  under which a third-party pack has the same standing as a first-party one. *Attack that:* it adds a
  distribution whose entire content is a dependency list, someone has to keep that list exact, and the
  name `weft` then means two things — the product and one wheel among several.

And on the promise itself: **1.0 by evidence** — a checklist of demonstrations, which `09` §2
recommends and enumerates — against **1.0 by date**. *Attack the recommendation:* a checklist whose
items are all ticked already is a date with extra steps, and one whose items never all tick is a
release that never happens; a date at least forces the argument about what is good enough to be had out
loud.

**Bring.** `09-release.md` §1 and §2, and G9's settled outcome, which must exist first — G10 states what
an installation promises and cannot do so before G9 has stated what a contract promises. `01` → *The
architecture stack*, Topology row, which is where the skew obligation was recorded and deferred. **A
count, taken on the day of the session, of how many distributions the workspace ships and how many of
them declare a bound on a sibling** — that measurement is the argument's concrete form.

*(Corrected 2026-08-22, at the session. This sentence continued "today every pack declares
`dependencies = ["weft-kernel"]` with no bound, so any pack installs against any kernel". **That was
true when this brief was written and false when the session ran**: G9's enforcement rule landed in
Phase 5, so every distribution under `packages/` now declares `>=X,<MAJOR+1` on each sibling,
`weft-cli` on nine of them. The instruction to take the count *on the day* is what caught it; the
predicted answer is what would have been argued from otherwise. Logged as `lessons.md` L6.1. The case
for a release set survives on the half a bound does not cover — a bound says what is *compatible*, a
pinned set says what was *tested together*.)*
And `02` §2 → *The trust model*, because the release is where its posture is either published to
operators or quietly lost.

**Done when.** There is a stated unit of release, a stated definition of 1.0 and the basis it rests on,
and a release checklist that can be failed. **Not** a home for the deprecation notice: that follows from
the settled rule that cross-cutting concerns attach at the registration seam (`09` §3), and its *clock*
is G9's — so neither is an output of this session, and a session that produces one has answered
something it was not asked.

---

## G11 — Does kernel error text go through the catalogue?

**The question.** `weft_kernel.context.MessageCatalogue` exists and every published pack error can
resolve through it. Does a kernel `WeftError` resolve through the same mechanism, or does the
catalogue serve packs only, leaving kernel error text as literals?

**Why it cannot be defaulted.** Two documents already point in different directions and neither one
noticed. `04` → *Kernel or pack* assigns the reference's 195-key en/pl catalogue split by owner:
*"Intent markers to the router pack, error text to the kernel, CLI strings to `weft-cli`"*
(`04-reference-inventory.md:51`) — which reads as the kernel being one of the catalogue's addressees. But
`MessageCatalogue` shipped in Phase 0 step 4 as a **mechanism with zero messages registered**
(`02` §1 → *What a plugin receives*, the Phase 0 step 4/5 note), and every `WeftError` subclass in
`weft-kernel` today — `UnresolvedServiceError`, `DuplicateRegistrationError`,
`PipelineResolutionError` and its family, and the rest across `context.py`, `discovery.py`,
`registry.py`, `resolution.py` and `runner.py` — carries its message as an f-string literal in
English. Nothing has resolved the disagreement; the mechanism was simply never pointed at the kernel.
It cannot be defaulted because both silences look like decisions from a distance: an empty catalogue
reads as "not needed here," and an English literal reads as "already decided," and neither is true.

**Positions to attack.**

- **Catalogue-only, kernel included.** Every error string, kernel and pack alike, resolves through
  `MessageCatalogue`, on the ground that a mixed surface — translated pack errors beside untranslated
  kernel ones — is a worse reader experience than an English-only one a user could at least predict
  end to end.
- **Pack-only; the kernel stays literal.** Kernel errors are contract violations read by pack authors
  and operators debugging a plugin at development time, not by an end user, so translating them
  serves no one G1's kernel-boundary rule anticipated. The kernel *publishes* the `MessageCatalogue`
  type — the way it publishes `Node` — without being a client of it. *Attack that:* `weft ask`
  surfaces kernel errors (a `PipelineResolutionError`, a `DuplicateRegistrationError`) directly to the
  same end user a pack error reaches, through the same CLI renderer, so the "who reads it" line is not
  as clean as it sounds.
- **Two mechanisms, deliberately.** The catalogue serves packs; the kernel keeps a second, English-only
  surface, but *names* it rather than leaving it implicit — and asks whether 0.14's coverage ratchet
  (every `WeftError` subclass needs a `manual/troubleshooting.md` entry) already **is** that surface,
  making a catalogue entry for kernel errors a duplicate obligation rather than a missing one.

**Bring.**

- `04-reference-inventory.md:51`'s exact assignment, re-read against what "error text to the kernel" was
  actually arguing when it was written — was it arguing kernel errors should translate, or only that
  the reference's *content* which happened to be error strings should be owned by whoever raises it?
- A current count of kernel `WeftError` subclasses and their message sites, taken on the day of the
  session — 31 subclasses across seven files (`blocking.py`, `context.py`, `discovery.py`,
  `registry.py`, `resolution.py`, `runner.py`, plus `WeftError` itself in `errors.py`) at the time
  this gate was opened, every one raised with an English f-string literal.
- `02` §1's Phase 0 step 4/5 note on `MessageCatalogue`'s narrowing: the catalogue owns *merge*, not
  *namespace*, and whether a pack's contribution is even in scope is itself flagged open there,
  pointing at `09-release.md`'s question of whether message-catalogue keys are API at all under G9.
- The 0.14 ratchet itself (`08` §1, §3 clause (d); `tests/docs/test_troubleshooting_coverage.py`),
  since whichever position wins has to say whether it satisfies that obligation, replaces it, or sits
  beside it.
- G1's rule that the kernel names no capability, tested against each position: does routing kernel
  errors through a catalogue make the kernel a *client* of a presentation capability, and is that the
  same thing G1 already ruled out, or a different question the rule never reached?

**Done when.** There is a stated position, and either the catalogue gains its first registered kernel
message or a stated, deliberate reason kernel errors stay English literals — plus a decision on
whether the 0.14 troubleshooting-ratchet entry and a catalogue message key are the same obligation or
two separate ones a kernel error must satisfy.


---

## G12 — What does a permission class mean when the caller is never a TTY?

**Added 2026-08-18 by G8, which settled that Weft's agentic front end is a first-party pack shipped
in Phase 7.** This session is that phase's gate.

**The question.** `03` → *Permissions* says an `ask`-class operation — `overwrite`, `destroy` —
**fails** with no TTY, naming the flag that would permit it, and never proceeds silently. An agent is
never a TTY. So either a Phase 7 pack can never perform those two classes, or something other than a
TTY counts as consent. Which?

**Why it cannot be defaulted.** Both defaults are bad in opposite directions and both look reasonable
from a distance. Reading it strictly, the most useful thing an agent could do — reindex a stale
collection it just noticed was stale — is permanently out of reach, and the rule reads as a
capability ceiling nobody chose. Reading it loosely, the pack passes `--yes` and inherits the exact
failure `03` names one bullet later: *"`destroy` trains people to pass `--yes` reflexively, which
disarms the whole table."* An agent passing `--yes` on every call is that sentence with the human
removed, and the permission classes G3 made mandatory at registration stop meaning anything at the
moment they finally matter.

**Positions to attack.**

- **The ceiling is the answer.** An agentic pack is `read`, `write` and `network` only, by
  construction, and `03`:133 needs no amendment. *Attack that:* a pack that cannot reindex is a
  demo, and Phase 7's exit says it drives a corpus end to end — establish whether end-to-end is
  reachable inside the ceiling before accepting it.
- **An approval channel counts as interactive.** The pack surfaces the pending operation and a human
  answers out of band; `03`:133's "non-interactive means non-guessing" is satisfied because nothing
  was guessed. *Attack that:* the rule's teeth are then entirely in an approval UX, and `03` specifies
  none — say what makes an approval channel meaningfully different from `--yes` rather than a slower
  spelling of it.
- **The class is the wrong unit for a non-human caller.** A human is asked per operation; an agent
  might be granted a bounded budget, a scoped target, or a dry-run-then-confirm protocol instead.
  *Attack that:* this invents a second permission model beside the one G3 settled, and two models is
  how the reference got three overlapping context objects.

**Bring.**

- `03` → *Permissions* in full, including the sentence about `--yes` and the one about the classes
  protecting you from the tool rather than from a pack.
- G3's outcome and the reason command permission classes are mandatory at registration with no
  default (`02` §2 → *The trust model*), since whatever this session decides has to survive the fact
  that a dishonest pack can declare `read` and destroy a collection anyway.
- **The `agentic-patterns` skill**, which `01` requires before this phase's loop is written. Its
  human-approval material is this session's direct input, and G8 moved the handoff here precisely so
  it lands with real contracts to reason about.
- What the Phase 7 pack actually needs to do to satisfy its own exit criterion, taken from the
  criterion rather than imagined — that is what decides whether the ceiling position is viable.
- Whether `03`'s exit-code table (`3` covers policy refusals) already has the right shape for a
  refusal a non-human caller receives, or whether it assumes a reader.

**Done when.** A stated position on whether a non-TTY caller can reach `overwrite` and `destroy`, and
if it can, the mechanism named and specified in `03` → *Permissions* rather than left to the pack.

---

## G13 — The derived-participant seam

**Proposed 2026-08-22 by Phase 5's own exit criterion (task 5.7), which found three faces of one
question.** The graph pack was built with zero edits under `packages/` and then could not do what
`02` §4's own table says it does. This session is the design finding `01` says a core-change request
*is*.

**The question.** What may a participant that is *not* the primary store ask for, and what reaches
it? Three symptoms, one subject:

- **Reach.** `02` §1 settles that deletion fans out *"across **every** registered plugin that
  satisfies `SourceDeletable`"*. Task 5.1a narrowed that at `weft_cli/fanout.py:71`, keeping only the
  `NodeStore` that `[services] store` names, so pgvector and Qdrant are not both connected to. The
  graph store registers under `NodeStore` (`02` §4's table), so the narrowing excludes it and derived
  graph data outlives its source — the reference's RAPTOR scar, first-party (`lessons.md` L5.25, L5.32).
- **Ask.** `Reconcilable.reconcile(ctx, mode)` hands a participant nothing that names the primary
  corpus, so `02` §4's *"`full` backfills entities for nodes indexed by a pipeline that had no graph
  stage"* is unbuildable by a pack (L5.24).
- **Answer.** `weft_cli.render._RENDERERS` is a first-party tuple matched on first-party result
  types, so a pack's `Command` returns a typed result nothing can render for a person (L5.30).

**Why it could not be defaulted.** Each face has a two-line fix that converts an extension point back
into a decision tree — a name in a filter, a branch in a dispatch, a key in a table — which is
requirement 1's exact failure shape. And the obvious general answer, *let a participant declare that
it is derived*, is the declared flag `02` §1 rules out: capability is derived, never declared, so
nobody can write a false one.

**Positions attacked, and what held.**

- **Reach.** *Every registered `NodeStore` participates* was attacked as connecting to a backend the
  operator does not use; *the operator lists extra participants* was attacked as a rule an author
  must remember, which this project has measured as the shape that decays; *derived stores must not
  register under `NodeStore`* was attacked as a convention rather than machinery, and as excluding a
  legitimate second node store. **What held: participation follows use.** The configured
  `[services] store`, plus every `NodeStore` named by a pipeline in the catalogue or by a persisted
  run record. It is derived from what the project actually runs, nothing is declared, and the unused
  backend stays out. *The cost, stated:* `weft delete` must read the catalogue and the run history,
  and a store dropped from every document that also never ran is excluded.
- **Ask.** *A typed corpus view passed to `reconcile`* was attacked on price — a store-contract major
  under G9's implementer rule, changing every implementation in and out of this tree, to hand over
  something the passport already carries. *Withdraw the promise* was attacked as requirement 4 in the
  open: `full` would keep a capability only first-party stores can use. **What held: the primary
  store through `ctx.require(NodeStore)`.** `Context.require` exists (`context.py:208`) and
  `NodeStore` already answers *what should exist* with `scan`, `count` and `list_sources`; the gap was
  only that nothing puts the store in the reconcile `Context`'s services. Zero kernel lines, no
  contract move.
- **Answer.** *Results render themselves* was attacked against `03`'s governing rule — a `Command`
  returns a typed result and the adapter formats it — and on output format, since a `render()` on the
  result cannot vary by `--format` without becoming the dispatch it replaced. *Leave it as structured
  JSON* was attacked as eighteen first-party commands printing for people and nobody else's.
  **What held: a renderer registered at the seam** — `registrar.add_renderer(...)`, `Rendered`
  published from `weft-command`, and the CLI's own renderers moved onto the same call so built-ins
  keep no privileged path.

**Bring.** `02` §1 → *The store contract family* and its G7 extension; `02` §4's table and the two
rows G7 added; `03` → *Output* and *Two modes, one implementation*; `weft_cli/fanout.py`,
`weft_cli/reconcile.py` and `weft_cli/render.py` read rather than remembered; `examples/weft-example-
graph`'s `register()` and `pipelines/kg.yaml`, which name the graph store as a stage and are what
makes *in use* a fact rather than an intention; and `lessons.md` L5.24, L5.25, L5.30 and L5.32.

**Done when.** A stated rule for who a fan-out reaches, a stated answer to what a non-primary
participant may ask for, a stated seam for rendering a pack's result — each specified in the document
that owns it (`02` §1, `02` §4, `03`) and each with a task in the ledger. **Not** a declared flag, and
**not** a per-pack shim: L5.15's rule is that an extension point has a producing and a consuming side
and both must be reachable by a stranger.
