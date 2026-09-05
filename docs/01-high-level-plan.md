# 01 — High level plan

## Why rebuild rather than refactor

The decision is settled; this section exists so the reasoning survives into the new repo.

A codebase examined before this rebuild began was designed to be elastically extended along at
least five axes: parsing methods, chunking, file types, retrieval engines, **and storage backends —
databases and files alike**. An audit of its shipped code found the seam holds on none of the first
four, and a closer pass found it holds on the fifth least of all. Adding one parser meant editing
four to six existing files. Adding one file format meant editing six parallel structures across
three files — nine edit sites for an ordinary format, thirteen for one behind an optional
dependency. Retriever builders had a registry, but it was keyed by a closed enum, so registering one
still required editing core. There were zero uses of `entry_points` or `pkgutil` across its 259
library files, and no `[project.entry-points]` group in its `pyproject.toml`, so nothing could be
extended from outside the package at all.

> **Corrected 2026-08-10.** Two edits to the paragraph above, neither of which weakens it.
>
> The file-format claim was *"five parallel maps, two of which are independent sources of truth that
> silently drift."* Counted, it was **six** structures in **three** files: a file-type enum (14
> members), an extension map (17 keys), a MIME map (16), an extractor map built from a base map, a
> force-markdown set (9), and a supported-extensions list. **They did not drift** — the two format
> lists had an empty symmetric difference, 17 = 17. The defect the sentence needs is different, and
> worse: a declaration that is right with a resolution that is empty. `.doc` and `.ppt` were declared
> *unconditionally* in both lists while their extractors were inserted *conditionally* on optional
> dependencies, so a `.ppt` passed every gate and then raised
> `ValueError('No .ppt extractor available …')` at the point of use. This is the accept-then-fail
> bug; drift is not its mechanism.
>
> The entry-point count was *"1,112 files"*, a repo-wide denominator that included a deployment
> layer outside the library. The verified figure was **0 across the 259 library files** plus no
> `[project.entry-points]` block. One nuance worth keeping: **one axis was genuinely open already** —
> a `@register_enhancer('keybert')` decorator worked end to end, and the only thing missing was the
> import trigger. That is the axis driving use case A runs through, which makes Phase 0's exit
> criterion cheaper and more credible: decorator + lazy bootstrap + loud lookup was already proven
> sufficient *once discovery exists*, so the genuinely new mechanism in Phase 0 is discovery itself.

> **The storage axis was audited, and the verdict is harsher than an earlier guess had recorded.**
> A `VectorStoreFactory` port existed with three well-shaped, intent-named methods returning typed
> models, so the intent was clearly there. But **there was no function named
> `get_vector_store_factory` anywhere in the repository**, and there were **zero
> `VectorStoreFactory` implementations inside the library** — every named concrete implementation
> lived outside it. Selection was constructor injection with two hard-coded escapes: one call site
> imported a local factory as the `None` default, a second imported a Postgres-backed factory
> **unconditionally on every construction of the storage layer**, and a third decided a
> domain-visible backend string by `isinstance` against a deployment class. The "remote
> implementation" inside the library was a metadata-registry method that unconditionally raised
> `NotImplementedError` with the comment *"This is a placeholder — actual implementation depends on
> vector store capabilities."*
>
> **So storage was not the same closed-dispatch shape as the other four axes — it was worse.** No
> registry, no enum, no plugin point, no registered name for any backend: **0 registered names
> against 10 / 7 / 14 / 3 on the other axes**, 17 dispatch sites over backend identity and zero
> registry lookups. Adding a second vector-store backend meant editing **11 files inside the
> library**. It was the leakiest boundary in the codebase and the one that most directly threatens
> the zero-container requirement below, because the storage layer's construction required the
> Postgres adapter module to be importable even for a purely local run. The port's own docstrings
> also advertised *"local filesystem, Qdrant, Weaviate"* and *"Elasticsearch"* support, and **none of
> that code existed** — a false premise the rebuild must not inherit. This is now a settled finding
> that raises **G4**'s stakes.

The failure is structural, not sloppy. Every one of those seams started as a small dispatch and
grew. The same codebase also proves the counter-case: where a real string-keyed registry existed —
enhancers, prompts, evaluation metrics — extension was *nearly* clean, and a 120-line registry
module built for enhancers is the design to reimplement in full — its shape, not its text; `NOTICE`
rules out the latter. But its problem was never a shortage of registries. It had **9 distinct
name→thing registries and 17 registry-shaped containers across 13 files, using 6 different
registration idioms with 4 different failure behaviours on an unknown name** — and only 6 of the 17
exposed any registration API. The other 11 were frozen literals, editable only by patching core.

> **Corrected 2026-08-10:** this paragraph once read *"the pattern that works is already in the
> codebase, in one small file, applied to one of seven places it belongs"*, drawn from an earlier
> review claiming *"three real string-keyed registries."* Both the count and the diagnosis were
> wrong. The actual failure was that **the key space was declared separately from the registry**: a
> closed 10-member strategy enum was declared in a different module from the registry it was meant
> to key, nothing kept them in sync, and the config validator resolved the discrepancy by discarding
> the user's input. The finding is worth stating plainly: *the registry is open; the vocabulary is
> closed; and where they disagree the code prefers to guess.* The design rule this implies is
> stronger than rule 5 below, and it should be read as an addition to it: **the set of valid names
> must be the current keys of the registry, never a parallel declaration.** One further correction —
> "extension is clean" was not true of evaluation metrics: six of the 21 never registered at all in
> the default import graph (see `04`).

Refactoring in place could reach the same end state. It would also have to carry a closed strategy
enum that shadows the registry, a chunker factory living inside the evaluation package, three
separate reciprocal-rank-fusion implementations of which one is dead, and a file-type enum wired
into six structures across three files and an API schema and a frontend union type. The rebuild is
chosen not because that code is bad but because **the extension model has to be the first
decision, and it cannot be retrofitted underneath 52,000 lines that assume otherwise.**

## What "modern and elastic" has to mean concretely

Vague quality attributes do not constrain design. These do:

1. **A new capability is one new package, zero edits to core.** Not one new file in core. Zero.
2. **A capability that spans several extension points is still one package.** The graph add-on
   registers an enhancer, a retriever, a store and CLI commands from a single install.
3. **A pipeline can be derived from another pipeline** by adding, replacing or removing one stage,
   without copying the parent.
4. **Built-ins have no privileged path.** They register exactly the way a third party does.
5. **An unknown name fails loudly, naming the valid options.** Never a silent fallback.
6. **The product ships real technique, and every piece of it is parameterisable and composable by
   someone who did not write it.** Richness is counted in packs, never in kernel lines.

> **Requirement 6 added 2026-08-15**, at the project owner's direction rather than out of a grilling
> session — recorded that way so its provenance is not mistaken for a gate's.
>
> **Why it needs saying.** Requirements 1–5 describe a mechanism, and a mechanism can be perfect and
> empty. A microkernel that ships nothing is a plugin API with no product, and "keep the kernel small"
> is a comfortable justification for building one. The counterweight fails the other way: shipping
> technique is a comfortable justification for fattening the core. **Requirement 6 resolves the
> tension by making richness and elasticity the same mechanism** — the corrective grading, the
> iterative critique, the step-back and boolean decompositions, RAPTOR's degrade-don't-crash contract,
> the RRF tuning values, the two pieces of Polish retrieval IP all arrive as packs, so adding
> technique costs the kernel nothing and the kernel budget can never be an argument against having
> ideas.
>
> **The second clause is the one with teeth, and there is a concrete precedent for what happens
> without it.** A metric suite in an audited codebase could not be parameterised at all: a metric
> was selected by name, unknown names were silently dropped, and there was no way to run the same
> metric twice with different thresholds. Ten good retrieval strategies were shipped and a third
> party could not have composed them, because the router assigned literal enum members in a
> hard-coded ten-branch ladder. **An idea that ships as a black box is a feature, not a
> capability**, and the difference is whether the next person can build on it without asking
> permission.

Rule 4 is the one that decides whether this works in two years. If the built-ins get a shortcut,
the public path is exercised only by outsiders, and it rots. Every failed seam examined during
design had a privileged internal path.

## The architecture stack

| Axis | Pick | Why it fits | Cost to accept |
|---|---|---|---|
| **Structure** | **Microkernel / Plugin**, with the kernel itself organised as hexagonal rings | Third parties extend the product against a published contract — that is the definition of this pattern, and requirement 1 makes it the primary quality attribute rather than a nice-to-have | The contract becomes public API. Versioning, deprecation policy and plugin isolation become real, ongoing work rather than a one-off |
| **Domain overlay** | **None.** A maintained glossary, no DDD ceremony | The domain is real but thin: document, chunk, node, embedding, retrieval, citation. There are no bounded contexts fighting each other and no business rules worth aggregates | The vocabulary drifts unless the glossary is maintained deliberately. Cheap to pay, easy to forget |
| **Topology** | **Modular monolith, several distributions** — one repository shipping a kernel distribution plus first-party packs, and exactly one container: the database | A library with the CLI as its adapter. There is no service tier and none is planned. The only thing that cannot live in the process is durable storage. Splitting the wheel is what makes fitness function 1 a fact rather than a script — see *The kernel boundary* | Several distributions to version and release together, and skew between the kernel and a first-party pack becomes possible. That obligation lands on **G9**. The store obligation is unchanged: keep it behind a contract so the one container is swappable |
| **Data** | **Pipe-and-filter** | Both RAG paths genuinely are staged transforms, and **G2 settled that neither has a canonical order** — see the note below. A pipeline is whatever its author writes, and any particular order is *proved* by each stage's declarations rather than prescribed here. This is also what makes requirement 3 natural — you can only derive a pipeline if stages are addressable data | Stage boundary contracts must be stable and typed. Getting the payload model right is real design work, and it is grilling session G5 |
| **Overlay** | **Stability / resilience** at the model seam only | Remote model calls fail, rate-limit and time out — a lesson already paid for once, in RAPTOR summarisation work | A retry, timeout and backoff surface that has to be configurable without leaking into every call site. **This is new work, not a lift** — see the note below |

> **Corrected 2026-08-10 — the ingest order.** The Data row previously read *"extract to clean to
> chunk to enhance to embed to store."* **An audited indexing pipeline chunks first and cleans
> second**, and it has two stages the plan's list omits. By that pipeline's own stage numbering:
> **stage 0** separates documents from already-atomic nodes, because tables and figures must bypass
> the parser entirely; **1** chunk; **2** clean; **3** attach `chunk_index` metadata; **4** enhance;
> **4.5** scrub transient metadata; **5** store. There is also **no separate embed stage** —
> embedding happens inside storage.
>
> This matters here because goals G2 and G5 will both be argued from this list and from the
> `base.yaml` example in `02` §3, and because that pipeline's cleaning chain has an *internal* stage
> order that is the single highest-value thing worth carrying forward from it, whose own docstring
> ends *"IMPORTANT: Changing this order will break functionality."*
>
> **Settled in G2, 2026-08-16: Weft adopts neither order, because it adopts no canonical order at
> all.** Cleaning is a stage like any other, present or absent at the author's discretion, and an
> order is *proved* by `requires`/`provides` and `intact`/`destroys` rather than blessed by this
> document — see `02` §3, *No canonical ingest order*. The chunk-versus-clean question dissolves once
> cleaning stops being treated as one stage: hyphenation repair wants to precede chunking, whitespace
> normalization must follow a structure-aware chunker, and both are declarations now. Stage 0 becomes
> **applicability** rather than a stage (a chunker declares it does not operate on atomic nodes and
> the runner routes them past), and stage 4.5 was already a seam concern — transient stripping
> attaches at registration. Stage 4.5's reason stands as written: *"if the enhancer is absent or
> fails, this guard prevents
> multi-MB base64 blobs from being serialised into PGVector JSONB"*, guarding a fixed set of
> transient metadata keys such as an image-data field.

> **Corrected 2026-08-10 — the resilience overlay.** The RAPTOR half of the Overlay row is confirmed
> exactly (nine tuning constants in the RAPTOR summarisation utilities). The generalisation is not:
> **there was essentially no retry surface to lift.** A search for retry/backoff logic across the
> evaluation code returned **0 occurrences**. The prompt-execution cascade had **no retries** — each
> tier was attempted once, so its worst case was three LLM calls, not three attempts. The only retry
> constants in 52,021 lines were RAPTOR's, and their own `TODO` said *"map these constants to
> parser/database config fields once externalized."* Plan the retry/timeout/backoff surface as new
> work with one worked example carried forward, not as a layer to port.

**Structure, more precisely.** Microkernel and the ring family are usually alternatives, but here
they compose cleanly and the distinction matters: **microkernel describes how capability is added,
rings describe how the kernel itself is built.** The kernel is small and hexagonal — ports at its
edge, no infrastructure inside. The plugin contracts are simply the subset of those ports that are
published for extension. Rejecting vertical slices for the same reason an earlier review gave:
the four axes are many-instances-of-one-shape, which is a plugin problem, and slicing would
duplicate the cross-cutting concerns this system actually has.

**What the earlier audit actually validates here, and what it does not.** The paragraph above is a
design choice for Weft and stands. What it may **not** lean on is an earlier review's claim that the
audited codebase's hexagon is a proven pattern to copy — a closer audit's verdict is *"layered code
wearing hexagonal vocabulary."*

> **Corrected 2026-08-10:** the rebuild's premise that *"the kernel is small and hexagonal"* was
> resting on an earlier review's claim that *"the hexagon … the healthiest part of the system and
> should be left alone."* Measured:
>
> - **31 import statements naming adapter/shared modules across 18 of 259 files** — 20
>   `TYPE_CHECKING`-only, **11 executing at runtime**, of which 2 were module-level and unconditional
>   — **plus 11 `importlib.import_module(...)` runtime loads** of the same adapter layer.
> - **The library does not import standalone.** It resolved those adapter imports only because the
>   project's own test and type-checker configuration put an outside deployment directory on the
>   import path.
> - **52 of 55 port contracts had zero in-library implementation**; **14 port signatures carried a
>   third-party framework type**, 6 carried inner/outer-ring concrete types, 12 carried
>   `dict[str, Any]`/`Any`. **Only 11 of 55 contracts were clean.**
>
> So that codebase's **rings were a layering** — real, largely respected at runtime, and worth
> copying. The **hexagon was not**, because its two load-bearing properties (no outward runtime
> dependency from the core; no vendor type in a port signature) were violated 11 and 14 times in the
> shipped tree. The design consequence that matters most for Weft's zero-container requirement:
> **that library could not be exercised end to end without its own deployment layer**, so "kernel +
> one container" has to be *demonstrated* in Phase 0, not assumed.

## The kernel boundary

**Settled in G1, 2026-08-10.** The rule, in one sentence: **the kernel is what is required to
express, load and run contracts it knows nothing about, plus the domain types those signatures
unavoidably name — and nothing in the kernel performs RAG work.** The falsifiable form, which is
what makes it usable in a review comment: *if you cannot describe the kernel without naming a
capability, it is too big.*

The rule is phrased against **capability, not size**, because size was never the property that
failed in the audited codebase. A shared context object there grew to 10 fields *and* was bypassed
by 253 of 259 files — too fat and irrelevant at once. A budget alone would have caught neither.

| The kernel owns | The kernel never owns |
|---|---|
| Registry and lazy entry-point discovery | Any capability contract — `Extractor`, `Chunker`, `Store`, `Retriever`, `LLM` |
| The contract *mechanism*: registration and versioning (fitness function 6) | Prompts, cleaning, chunking, retrieval, routing, citations, metrics |
| The pipeline model, the resolver and the derivation operators | Any pipeline *content* — a shipped `base.yaml` belongs to a pack |
| The domain node and payload types, and the `Outcome` type (`02` §1) | Any vendor SDK |
| The passport: `tenant_id`, run and trace ids, cancellation, locale, `require()` | Tuning knobs — anything resolvable is a service, not a field |
| Configuration loading: pipelines, the `packs:` namespace, `${env:}` interpolation, validation | Message *content* — every pack owns the keys it emits |
| The `WeftError` root and failure attribution at the plugin seam | The `LLMError` taxonomy, which ships with `weft-llm` |
| Span wrapping applied at the registration seam | Exporters, collectors, Phoenix |
| The message-catalogue mechanism | |
| The fallback combinator over any contract | |
| The plugin instance cache, keyed by tenant | |
| The `plugins doctor` computation, which is fitness function 2 | |

**The kernel's dependencies are `pydantic` and `opentelemetry-api`. Nothing else.** The OTel
dependency is the API package, which libraries are meant to depend on and which no-ops without an
SDK; everything that exports a span is a pack.

**Packaging.** One repository, several distributions: `weft-kernel`, `weft-cli`, and first-party
packs (`weft-llm`, `weft-prompts`, `weft-extract`, `weft-store`, `weft-eval`, …). This is not
bookkeeping — it is what turns fitness function 1 from a script into a fact. A boundary checker in
an audited codebase could not fire partly because **the library did not import standalone**: it
resolved its adapter imports only because the project's own test configuration put an outside
directory on the import path. A kernel that is its own wheel is checked by installing it alone and
importing it, and Phase 0's exit criterion — *a plugin in a separate installed package* — stops
being a claim about directories.

**Two consequences that will feel wrong, and are meant to.**

1. **The kernel defines zero capability contracts.** `Extractor`, `Chunker` and `Store` — the three
   Phase 0 publishes — ship from the first-party packs that own them. A newcomer opening
   `weft-kernel` finds no RAG vocabulary at all. The risk this accepts is rival contracts: nothing
   structurally prevents a second pack publishing its own `Retriever`. The mitigation is that the
   first-party contract ships first and every built-in already satisfies it. The alternative was
   worse — if the kernel owns `Store`, then by symmetry it owns `Retriever`, `Chunker` and
   `Extractor`, G4's capability machinery follows them in, and the kernel is a RAG framework again.
2. **The 195-key locale catalogue stops being one file.** Keys belong to whoever emits the message:
   intent markers to the router pack, error text to the kernel, CLI strings to `weft-cli`. The
   Polish translations survive intact — the single asset does not, and losing sight of that is how
   it would quietly decay.

The numeric budget that holds this line is fitness function 3 below. What a plugin actually
receives is specified in `02` §1; where every lifted item lands is `04` → *Kernel or pack*.

## Colour — the core is async, without exception

**Settled in G6, 2026-08-10.** Every contract method is `async def`. There is no sync protocol, no
dual registration, and **no bridge anywhere in the library** — `asyncio.run` appears exactly once in
the whole tree, at `weft-cli`'s entry point.

The positive case is ordinary: embeddings, model calls and store round-trips are IO-bound, and `03`
requires streaming. The negative case is the one that decided the shape. An audited codebase had
**exactly one** `asyncio.run` call site in 259 files, and its safety was guaranteed by a docstring
plus a caller in its own deployment layer — *"Safe only in `asyncio.to_thread()` workers — never in
FastAPI"* — so calling that method from a route would raise
`RuntimeError: asyncio.run() cannot be called from a running event loop`. A sibling docstring
recorded *"Reset to `None` by the adapter before each `asyncio.run()` call"*: per-call mutable state
maintained by the caller, again by prose. The colour discipline itself held there — 6 real
`async def` bodies, 10 `await`s, **no blocking call inside an async function**. What did not hold was
the bridge. So Weft has none to make safe.

Four consequences, each a decision rather than a detail:

- **A pack may not be sync-only.** A CPU-bound stage — KeyBERT, the cleaning processors, RRF fusion —
  is written `async def` and offloads its own blocking work. The kernel offers no dispatch branch and
  no declared colour, so there is one code path and nothing to misdeclare.
- **That makes offloading an author-remembered concern, so it is machine-checked.** While a stage
  runs, a detector installed at the same registration seam that applies spans fails the build on any
  blocking call on the loop thread — file IO, sockets, `time.sleep`, `subprocess`, a synchronous
  driver — naming the stage and the call. It ships in the pack test kit, so a third party sees it
  before publishing rather than after. This is fitness function 7, which is categorical and carries
  no threshold; what it cannot see, and why that is accepted rather than patched with a number, is
  stated there.
- **There is no synchronous facade.** Notebooks use top-level `await`; a script writes one
  `asyncio.run`. A facade would be a bridge, and a bridge is what the fragile-safety incident above
  was made of.
- **Streaming does not fork the contracts.** Tokens go to a `TokenSink` resolved as a service, and
  the generator still returns a decided `Outcome[Answer]` — see `02` §1. This refuses a shape
  observed elsewhere: **10 `@register_strategy` and 10 `@register_streaming_strategy` sites, symmetry
  maintained by hand with no test asserting it.**

**The runner keeps one batch in flight per pipeline run.** Overlapping batches would make every
stage concurrent — including `Lifetime.RUN` stages, whose authors were promised no thread-safety
obligation — so parallelism comes from inside a stage (its own `gather` over a batch) and from
running pipelines concurrently, neither of which changes a published promise. If pipelining is ever
shown to be worth it, it arrives as something a stage declares, not as a silent change to what
every existing pack agreed to.

## Runtime shape — one container, and it is the database

The whole system runs as a library in the caller's process. There is no API service, no worker, no
broker, no object store, no observability stack. **The only thing that gets a container is the
database**, because it is the only component that must outlive the process.

The contrast with an audited comparison point is the point: it shipped a twenty-four service Compose
topology, and none of those services were the product. They were the cost of having decided, early,
that the product was a deployment rather than a library. Weft keeps that decision unmade.

> **Unverified:** the exact service count and characterisation concern that system's deployment
> configuration, which was not examined as closely as the library itself. What *is* confirmed from
> inside the library points the same way: it reached outward into its own deployment layer 11 times
> at runtime, and 52 of 55 port contracts had no in-library implementation.

```
weft-cli  ──▶  weft-kernel  ──▶  Store contract  ──▶  one container
                                 (published by         pgvector | qdrant | …
                                  weft-store)
```

**Storage elasticity is a hard requirement, not a nice-to-have.** The store is therefore one of the
three contract boundaries published in Phase 0 — after G4 a *family* of four protocols rather than a
single one — and it must be satisfiable by more than one backend before it is trusted, because a
contract with one implementation is a guess. Concretely:

- **One container is the floor, and it is pgvector.** *(Amended in G4, 2026-08-10 — this bullet
  previously read "**Zero-container mode is a first-class target.** A local file or embedded store
  must work with no container at all, so `weft index ./docs && weft ask "..."` runs on a laptop with
  nothing installed. If the contract cannot express that, it is over-fitted to Postgres.")* The
  zero-container target was retired deliberately, for a reason worth recording: an embedded store
  good enough to develop against is **almost** the same as the production one, and almost is the
  expensive kind of different — FTS5 ranks unlike `tsvector`, a brute-force scan behaves unlike HNSW,
  and the gap surfaces at deployment. Two backends that are obviously different are safer than two
  that are subtly alike. **The over-fitting guard moves rather than disappears:** the contract is
  proven on **pgvector and Qdrant**, which have genuinely different shapes, and a store that only
  Postgres can satisfy fails that test just as loudly.
- **An ephemeral in-memory store exists, and is not a backend.** A dict with brute-force cosine,
  never persisted, used by the conformance kit and by pack authors' unit tests so writing a plugin
  does not require Docker. It forgets everything on exit, deliberately, so nobody deploys on it and
  there is no migration path to fight.
- **The backend is chosen in configuration**, like any other plugin, and swapping it is a config
  edit plus a re-index. Never a code change.
- **A backend ships as a pack.** `weft-store-qdrant` is an ordinary add-on with no privileged
  status, which means a customer can write a store for their own infrastructure without asking.
- **Capabilities are declared, not assumed.** Backends differ in what they support — hybrid search,
  metadata filtering, full-text, graph traversal. The contract must let a store advertise what it
  can do and let a pipeline fail at resolution when it needs something the configured store lacks.
  Assuming every store does hybrid search is how this contract would rot.

The shape of that capability declaration, and how much of the query surface is common versus
backend-specific, is the substance of grilling session **G4**.

## The least-architecture check — what is deliberately deferred

Each of these is cheap to add later *because* the structure above leaves room, and expensive to
carry now. Each has a named forcing function; nothing is deferred on vibes.

| Deferred | Reopen when |
|---|---|
| Event bus between components | **G7 ruled against it, 2026-08-21, and the trigger it named has been tested rather than left standing.** The graph pack was walked case by case and needed no bus: a cross-corpus pass has the runner's `flush()`, shape-level observation has the OTel spans the seam already emits, and the one genuine hole — derived data outliving its source — is closed by `SourceDeletable` and `Reconcilable` in the store family (`02` §1). The audit log, brought deliberately as the awkward case, splits in two: observing runs that never opted in is **refused** by `02` §3's rule and is not a missing mechanism, while everything it may legitimately see is **served by a pack** — `weft-otel` sets the `TracerProvider` in its `register()`, which is the *everything that exports a span is a pack* rule above doing exactly the job it was written for. The awkward case was answered through the extension model itself, with no core change, which is the strongest form this session's answer could take. **Reopen when** an add-on needs to observe something where an explicit point cannot be *added* — not merely where one does not exist yet, since adding one is what this session did. A Phase 5 pack author hitting that is a design finding and reopens this row |
| Background job broker | The first user needs indexing to survive process restart, or a single index run exceeds a session |
| Any service tier at all — API, worker, gateway | Someone outside the process needs to call this. Until then the library plus one database container is the whole system, and every service added before that point is cost without a user *(the "cost without a user" claim inherits the twenty-four-service figure above and is **unverified**)* |
| CQRS | Never, at library level. It was a deployment-shape decision elsewhere and belongs there if anywhere |
| Multi-tenancy in the core | The second tenant. Carry a tenant identifier through the context from day one, because retrofitting an identifier is painful, but build no isolation machinery until it is real |
| Distributed tracing beyond in-process spans | The first deployment that spans processes. Emit OpenTelemetry spans from day one; do not build a collector story |

## Phases

**This section is the execution script.** Work it top to bottom and it pulls in the other documents
and the grilling sessions at the moments they are needed — you should not have to remember that
`05` exists.

Every phase has four lines:

- **Gate** — grilling sessions that must be closed *before* the phase starts. A gate is not advice.
  Starting a phase with an open gate means building on an undecided foundation, which for Phase 0
  means building the wrong kernel.
- **Read** — the document sections that specify the work.
- **Lift** — what is drawn from prior work, per `04`.
- **Exit** — one criterion that can be demonstrated rather than argued about.

---

### Phase 0 — Walking skeleton

The kernel, the registry, entry-point discovery, and three built-in plugins: one extractor, one
chunker, one store. `weft index` and `weft ask` work end to end on a directory of text files.

- **Gate:** `05` → **G1** kernel boundary, **G5** stage payload typing, **G6** sync or async.
  Then **G4** before the store work and **G3** before discovery ships.
  All three of the first set change the shape of the kernel, so none of this code can be written
  honestly until they are closed.
- **Read:** `01` *The kernel boundary* first — it decides what this phase is allowed to write. Then
  `02` §1 contracts, §2 packs and discovery, and `01` *Runtime shape* for the store.
- **Lift:** `04` category A — model strings, span helpers, and
  `tests/unit/architecture/test_allowlist_empty.py` as the template for fitness functions 0 and 1.
  **Only the span helpers land in the kernel**; model strings ship as a first-party pack, per `04` →
  *Kernel or pack*. **Not** `scripts/check_hex_boundary.py`, which was shown not to fire; see
  *Fitness functions* below and `04` category A.
- **Build order:** `06-phase-0-build.md`, which sequences this phase into ten steps and names the
  three places it could accidentally settle **G2**.
- **Exit:** a plugin living in a *separate installed package* is discovered and used, with no edit
  to the core package — this is fitness function 9(a). This is the thesis of the whole project; if
  it is not true here, the design is wrong and everything after is wasted. **Also: fitness functions
  8(a), 8(b), 7(a), 2 and 9(b) are wired and green** — the canary is refused and never imported, no
  pack code runs for a registry-free command, there is exactly one `asyncio.run`, the registry's
  contents equal what the installed distributions declared, and no file under `packages/` or
  `testing/` names the example pack. **Also: the quickstart and the pack author guide's
  single-contract section are written, and their checks (`08-manuals.md` §3, clauses a and c) are
  green** — a fenced shell block that fails to run, or a code sample that has drifted from
  `examples/weft-example-chunker/`, fails the build the same way an untyped payload would.

> *(Corrected 2026-08-17: this Lift line used to also name the prompt layer, the three-tier cascade
> and the `LLMError` taxonomy. They were never built here. `06-phase-0-build.md`'s scope fence — *What
> Phase 0 must not build* — puts "Generation, prompts, the LLM adapter, `weft-llm`" in Phase 2, the
> build followed `06`, and Phase 0 exited without them, which left this line assigning work to a
> phase that had already closed. They are not dropped from the plan: they now appear in Phase 2's
> Lift line, below, as the prompt registry, the three-tier cascade — the union of `PromptExecutor`'s
> structure and `LLMJudge`'s `LLMBadRequestError` short-circuit — the JSON-rescue extractor nested
> inside that cascade, and the `LLMError` taxonomy.)*

### Phase 1 — Pipelines as data

The pipeline model, the resolver, and the derivation operators.

- **Gate:** `05` → **G2** derivation semantics — **settled 2026-08-16.**
- **Read:** `02` §3 in full — the operator table and its edge rules, `intact`/`destroys`,
  applicability, slots, vars, and the KeyBERT case.
- **Lift:** `04` category B — **not the stage order observed elsewhere, which G2 declined to adopt
  in either direction**, but the two things underneath it: the reason stage 4.5 exists (transient
  scrubbing, which lands at the seam rather than as a stage) and the reason stage 0 exists (atomic
  nodes must never be re-chunked, which lands as applicability). Category A cleaning processors,
  *with* their ordering rationale — and with the 243-word Polish fused-word exception set, ranked the
  second most valuable thing worth carrying forward and which `04` does not currently name.
- **Exit:** driving use case A works — a `specific` pipeline derived from `base` with KeyBERT
  inserted after chunking, expressed as configuration, with no change to core and no copy of the
  parent. **Also: fitness function 11 is wired and green**, both clauses.

> *(Corrected 2026-08-18, from the Phase 2 exit audit; **closed 2026-08-18 by task 2.35**,
> sha `296be69`. "Category A cleaning processors" was **six** in `04` §A; `weft-clean` registered
> **four**. Absent: `UnicodeNormalizer` (appended late in the cleaning chain, whose docstring read
> *"Fix encoding errors first (e.g., Ã³ -> ó) so regexes work correctly"*) and `ArtifactRemover` (its
> page-number regex and 0.5 non-alnum separator filter only; its documented header removal never
> executed, so that half was never lifted). `build-ledger.md` → 1.7 recorded no reason for four. Both
> are now shipped — `weft_clean.unicode_normalizer.UnicodeNormalizer`,
> `weft_clean.artifact_remover.ArtifactRemover` — and `ftfy` is a real `weft-clean` dependency;
> `unicodedata`/`NFKC` still appear nowhere, because `ftfy.fix_text`'s own default is NFC, not NFKC,
> and an earlier, redundant `unicodedata.normalize('NFC', ...)` call was dropped rather than carried
> once that redundancy was verified — a correction task 2.35 made, not an omission it left standing.
> The gap this note named — `UnicodeNormalizer` sitting at position 1 precisely because every later
> processor's regex needs what it produces, with no machine-checked expression of that constraint —
> is closed: `weft_clean.property.Verbatim`, a third `Property`, is declared `intact` by
> `UnicodeNormalizer` alone and `destroys` by every other processor in the pack, which forces
> position 1 through the identical `intact`/`destroys` mechanism `WhitespaceNormalizer`'s "must run
> last" already used, pointed the other way, with no new machinery. `build-ledger.md` → 2.35 has the
> full account, including what was deliberately not lifted (`ArtifactRemover`'s header/footer
> removal, a scar) and why the page-number pattern stays English-only rather than gaining an
> unverified per-language table.)*

### Phase 2 — Retrieval and generation

Retrieval strategies, fusion, reranking, the router, citations. The router keeps the same design
observed elsewhere: an LLM scores dimensions, a deterministic ladder decides.

- **Gate:** none. Re-open **G5** only if a strategy cannot express what it needs to pass along.
- **Read:** `02` §1 for the `Strategy` and `Retriever` contracts, and `09-release.md` §4 —
  prerequisite V1–V3 must exist before this phase's work can be judged.
- **Lift:** `04` category A — the prompt registry, the three-tier cascade (`PromptExecutor`'s
  structure unioned with `LLMJudge`'s `LLMBadRequestError` short-circuit), the JSON-rescue extractor
  nested inside that cascade, and the `LLMError` taxonomy. These four moved here from Phase 0's Lift
  line; see the dated note under Phase 0 for why. Also category B — the router design, the ten
  strategies, the intent classifier, the citation manager split into its four responsibilities,
  language-aware reranker selection — nine items in total. And `04`'s kernel row for
  `_try_extractors`, the fallback-chain combinator (`T1.15`): no phase before this one claimed it,
  and this is the first phase a second backend for one media type exists for it to compose over, so
  it is built here too, in the kernel, alongside the pack work this phase already does.
- **Exit:** strategies are plugins, and the router discovers them from the registry rather than
  from an enum or an if-chain. **Also: fitness functions 9(c) and 12 are wired and green** — every
  contract Phase 2 publishes has an out-of-tree example pack implementing it, and an error reporting
  an unresolvable name carries the alternatives as a typed field. *(FF12 added to this exit
  2026-08-18 by G11, per `09` §6.3 step 3: a fitness function's activation belongs in the exit
  criterion of the phase that activates it, so a phase cannot open one and leave without switching it
  on. Task 2.36.)*

> **Scope added 2026-08-17, logged as `S1`** (`README.md` → *Decision log*; the procedure is `09` §6.4,
> and the four task lines with their exit demonstrations are `build-ledger.md` → Phase 2, 2.27–2.30).
> This phase also ships **PDF extraction**, a **semantic embedder** and a **model-provider adapter**,
> each as a pack. The forcing function was V1: `09` §4 requires the corpus to cover every format an
> installed extractor claims, and the corpus that arrived is nine PDF papers — so the prerequisite this
> phase must satisfy before it can be judged is unbuildable without them, and a baseline measured over
> content hashes would reproduce §4.2's defect with the labels changed. The **exit above is unchanged**:
> none of the four is an exit criterion, and none activates a fitness function.
>
> Two consequences worth stating rather than discovering. **The `_try_extractors` combinator in the
> Lift line above stops being conditional** — the "second backend for one media type" it composes over
> is now a specific pair, so T1.15 lands with something real underneath it. And **nothing is lifted for
> the PDF work**: `04`'s own note records `PDFParserProvider` as one of four documented-but-never-executed
> features found in the audited codebase, Tier 2 as an idea and never Tier 1, so it is written fresh.

> *(Corrected 2026-08-18, from the Phase 2 exit audit. The Lift line above says **nine items**
> and **eight** were built. The ninth, **language-aware reranker selection**, was deliberately not
> built: `weft-retrieve` ships `llm-rerank`, `graded-retrieval` and `collapse-to-parent`, and
> `cross-encoder-rerank` is absent for a reason recorded at the point of the decision
> (`weft_retrieve/rerank.py`'s module docstring and `build-ledger.md` → 2.7 — a model download `09`
> §4.4 keeps out of the gate, and `10` §1.2 files the technique on the index path). It is also
> blocked independently of that: an audited codebase selected its reranker from the collection's
> language (Polish → a Polish-specific reranker model, everything else → a general cross-encoder),
> and **no stage in Weft produces a `Language` fact yet** — `weft-clean` is its interim owner and
> there is no `detect` stage, which is why `PolishFusedWordFixer.applies_to` narrows to no node at
> all today. The item is not dropped: it needs a language fact before it can be built at all, and
> whichever phase ships that ships this with it. This note exists because the same defect had to be
> repaired for Phase 0 — a Lift line left naming work a closed phase never did — and ticking this
> phase's Exit box is what would have frozen it a second time.)*

> **Two tasks added 2026-08-18, from the same audit — `build-ledger.md` → Phase 2, 2.34 and 2.35.**
> Neither is a new lift the plan forgot to schedule; both are items S1 *armed* by putting PDF bytes on
> the ingest path, in a phase whose extraction and store work is where they land.
>
> **2.34 — the NUL-byte sanitiser**, a fragility pattern observed at twelve call sites elsewhere
> (NUL → **space** rather than deletion, counted and logged before stripping). `04`
> lists it among the six highly-ranked Tier 1 items its own tables do not name, and no phase Lift line
> ever claimed it. Measured 2026-08-18, end to end: `corpus/arxiv/2508.18901v1.pdf` — a document
> declared at `corpus/manifest.toml:122-129` — extracts through Weft's own `pdf-text` to a `Produced`
> `Node` whose `content` carries **65 NUL bytes**; `weft-store`'s schema is `content TEXT NOT NULL`
> (`weft_store/pgvector_store.py:138`); psycopg against the live pgvector container answers
> `DataError: PostgreSQL text fields cannot contain NUL (0x00) bytes`. Two of the corpus's nineteen
> PDFs do this, both in the `fetch` tier, which is why the gate is green — the publishable baseline
> rests only on the reproducible tiers.
>
> *(Settled 2026-08-18, in the same task. The sanitiser lives at the kernel registration seam*
> *(`weft_kernel.seam._sanitize_control_bytes`), riding the same `Produced` → `Node` / `tuple` / `list`*
> *walk `_strip_transient` already performs, immediately after it — never `weft-extract`, never a*
> *store. Not `weft-extract`: eight sites across `packages/` build a `Node` from text that came from*
> *outside the process (`weft_extract/text.py:80`, `weft_pdf/document.py:205`, `weft_chunk/*
> *fixed_size.py:145`, `weft_clean/dictionary_spacing.py:117`, `weft_clean/hyphenation.py:70`,*
> *`weft_clean/whitespace.py:63`, `weft_clean/table_linearizer.py:79`, `weft_index/raptor.py:254`) —*
> *a smaller-scale reproduction of the same twelve-call-site fragility observed elsewhere. Not a*
> *store: pgvector's* *`content` column is `TEXT NOT NULL` and refuses a NUL byte; `weft_qdrant/store.py` sends*
> *`model_dump(mode="json")` over its own wire protocol and does not, so fixing this at a store means*
> *the same corpus indexes under one backend and fails under another — exactly what this task line*
> *refuses. The seam already owns this class of concern (`CLAUDE.md`: cross-cutting concerns live at*
> *the registration seam), already knows what a `Node` is, and `wrap`'s own signature already carries*
> *`distribution`/`contract`/`plugin`, so the earlier diagnostic triple (source, extractor, count —*
> *"the diagnostic is the point, not the strip") becomes a span attribute*
> *(`weft.nul_bytes_removed`) rather than four keyword arguments an author must remember at every call*
> *site. NUL becomes a space, never a deletion, following the earlier precedent — and Weft has a live*
> *reason that precedent only had in principle: `weft_chunk.payload.ChunkOffset` records a character*
> *offset into a parent's content, so a deletion would silently shift every offset recorded*
> *downstream. Scope is `Node.content` and every `str`-typed field an `ExtModel` in `Node.ext`*
> *carries, walked by `model_fields` introspection rather than a maintained list — the same lesson*
> *about the transient scrub applies unchanged. Measured directly: no first-party `ExtModel`*
> *shipped as of this task carries verbatim extractor text — `weft_pdf.PdfPages` (`weft_pdf/*
> *document.py:94-131`), the one built straight from what a PDF backend reads, has only `backend: str`*
> *(a plugin name) and `starts: tuple[int, ...]` (offsets) — so today's corpus exercises `content`*
> *only; the `ext` walk covers the column-level fact (pgvector's `ext JSONB NOT NULL` refuses a NUL*
> *byte exactly as `TEXT` does) rather than a currently-populated field, and costs one `isinstance`*
> *check per field on a namespace that already changed. Exit demonstration:*
> *`tests/integration/test_nul_byte_sanitisation.py` runs this exact document through the ordinary*
> *`pdf-text` → `fixed-size` → `hash` → `pgvector` pipeline against the live container and asserts*
> *every stored node's `content` is free of `\x00`; reverting the seam change reproduces the*
> *`DataError` above verbatim, confirmed by running the test against the pre-fix code.)*
>
> **2.35 — the two absent cleaning processors**, re-assigned forward from Phase 1's Lift line; the
> evidence and the reasoning are in that phase's own dated note above.

### Phase 3 — The CLI

The full driving adapter: REPL, streaming, slash commands, plugin-contributed commands, permissions.

- **Gate:** `05` → **G8** is the REPL agentic — **settled 2026-08-18: no, and it never becomes one,
  because a planning loop is logic and `03`'s governing rule keeps logic out of the adapter.** Weft's
  finished form *is* agentic; the agent is a pack, and it is **Phase 7**. This phase owes it one
  property and needs that property regardless — a `Command` returns a typed result a renderer
  formats, never printed text (`03` → *Two modes, one implementation*). The `agentic-patterns` handoff
  moves to **G12**, Phase 7's gate, where there are real contracts to reason about.
- **Read:** `03` in full.
- **Lift:** one item, and it is not the CLI. A CLI examined elsewhere reached 1,080 lines in one
  command module and is the shape to avoid. Two specifics worth carrying as rules rather than code:
  it ran `load_dotenv(override=True)` **at module import time**, so importing the CLI mutated the
  process environment — **a driving adapter may not mutate process state at import** — and it
  shipped **three** separate entry points (`rag-index`, `rag-chat`, `rag-query`), not one. The item
  that *is* lifted is **the streaming-safety tuning evidence** — the degenerate-loop guard for
  streaming generation from small models, plus the markdown-table detector that stops it firing on
  legitimately repetitive content, *"the densest record of measured tuning in the query path"*, four
  worked examples in the source. It arrives here because **this is the phase that ships streaming**;
  see the dated note below.
- **Exit:** a plugin ships a command that appears in `weft --help` and in REPL completion without
  core knowing it exists.

> *(Corrected 2026-08-18, from the Phase 2 exit audit. This Lift line read **"nothing"**, and
> that left the streaming-safety tuning evidence owned by no phase at all. `04` §B assigns
> `PriorCitationManager` **split into its four responsibilities** to Phase 2; two of the four —
> `_detect_repetition` and `generate_with_citations_streaming` — are streaming-only, and Phase 2 has
> no streaming to guard, so `weft-generate` correctly built the other two (the numbered evidence
> block and citation extraction) and stopped. Streaming is this phase, by G6's own consequence: a
> `TokenSink` service, not a second contract (`03` → *Output*), which is task **3.6**. The guard is
> therefore due with 3.6 and is now task **3.10**. Two traps ride with it: the guard's cheap
> heuristics are the asset — positional character equality, chosen as *"a lightweight alternative to
> Levenshtein distance"*, and char-5-gram diversity below 0.3 — and *"hallucination detection" is not
> what it does*; it is a loop-breaker for small local models and must not be named or documented as
> anything else.)*

### Phase 4 — Evaluation and observability

Metrics as plugins, spans on every stage, the evaluation harness as a decorator over a pipeline.

- **Gate:** none.
- **Read:** `02` §1 for the `Metric` contract.
- **Lift:** `04` category A — all 21 metric implementations, as the first metric pack, **with
  every defect listed in `04` fixed at the door**. Note that RAGAS and ROUGE are not dependencies of
  the codebase these were drawn from; those classes are hand-rolled, so they are original code to
  lift rather than integrations to re-wire.
- **Exit:** running the same corpus through two derived pipelines produces a comparison the tool
  generates itself, **and both runs are persisted so they can be diffed after the fact**. An
  audited codebase could not do this at all. **Also: fitness function 8(c) is wired and green** — every
  persisted run names the distribution set that was active, without which a comparison across two
  runs cannot be trusted to be comparing pipelines rather than environments.

> **Corrected 2026-08-10:** the exit criterion said an earlier comparison helper *"was a display
> function and the sweep loop was the operator's"*. Correct, and understated. That helper function
> did return `None` — but **the entire module was dead**: all four public functions had zero
> references anywhere in the library or its tests. A search for ab-test, sweep or grid-search usage
> returned 0 matches. And **nothing in 6,632 lines of evaluation code wrote a result anywhere** —
> there was no persistence, so two runs could not be diffed after the fact even by hand. There was
> also no retry, no concurrency, and **zero OTEL spans** in that evaluation code. Hence the added
> clause: *an evaluation-first product that cannot diff two runs after the fact is not
> evaluation-first*, and a comparison the tool generates itself implies stored runs.

### Phase 5 — The independence test

The graph add-on, per driving use case B, built as an external package.

- **Gate:** `05` → **G7** event bus or explicit extension points, and **G9** contract versioning,
  which the first external pack makes real.
- **Read:** `02` §4 in full.
- **Lift:** nothing. This phase exists to test the extension model, so borrowing shortcuts from
  elsewhere would defeat it.
- **Exit:** it is written by someone who has not touched the core, and they never need to. If they
  file an issue asking for a core change to make their pack work, that is a Phase 5 failure and a
  design finding, not a feature request. Fitness function 13 (task 5.2b) is switched on: every
  dispatch over `FilterOp` raises rather than answers for an operator it predates.

### Phase 6 — Release

The product stops being a repository and becomes something a stranger can install. Several
distributions, one repository, published to an index under a stated version policy, with a support and
deprecation surface a pack author can plan against — and a published baseline measurement, so *"it
works"* is a number someone else can reproduce rather than an opinion held by the people who wrote it.

- **Gate:** `05` → **G10** the release and support policy. G10 cannot be run until **G9** has settled,
  which Phase 5 already requires: a user-facing release promise is built on top of the contract
  compatibility rule, and stating the promise first would settle G9 by implication rather than by
  argument.
- **Read:** `09-release.md` in full — it owns the distribution model, the version policy, the support
  surface, the validation prerequisite and the release checklist. Then this section's *Fitness
  functions* 0–10 and every phase exit above, because the release claim is their conjunction and nothing
  more; and `02` §2 → *The trust model*, because *"installing is trusting"* is a statement made to
  operators and a release is where it is either published or quietly dropped.
- **Lift:** nothing, and one scar recorded as a rule. An audited codebase was never installable: it
  could not be installed standalone at all — one config module reached an outside deployment path
  through `Path(__file__).parents[4]`, which breaks the moment the package is a wheel, and two
  evaluation modules carried unguarded top-level runtime imports of the same adapter layer, so
  importing them hard-failed unless that outside directory was on `sys.path`. **The rule: a
  distribution is proven installable by installing it, never by reading it** — which is fitness
  function 1's primary half applied to every distribution rather than only to the kernel.
- **Exit:** on a machine that has never seen this repository, installing **the release set G10 named** (`09` §1, settled 2026-08-22)
  from the package index reproduces the published baseline — one `uvx` invocation of that unit indexes
  the validation corpus, answers its question set, and `weft eval compare` against the published
  baseline run reports every metric **inside the interval that baseline recorded across its own
  repetitions** (`09` §4, V3 and V4; no tolerance is chosen anywhere, and a baseline that recorded no
  interval fails V3). **Also: fitness function 10 is wired and green**, so the publish set and the
  workspace agree and `weft-canary` is absent from the index; the installed state is that **every
  first-party pack is `active` at the version that release names**, with nothing flagged `ambient` —
  what `doctor` *says* about a pack that is not is G9's, not this criterion's; and each of Phases 0–5's
  exit criteria is re-demonstrated **against installed wheels rather than the working tree**, with
  Phase 5's graph pack installed from the index by name.

**Why the exit is phrased against the index and not the repository.** Every prior exit criterion is
demonstrated in the tree by the tree's own gate. That is the right standard for a design property and
the wrong one for a release, because the failure this phase exists to catch lives exactly in the gap
between them: a package that imports in the workspace and not from a wheel, a data file that is present
in the checkout and not in the sdist, an entry point that resolves because `uv sync` linked the source
directory. An earlier audit is the proof that this gap is real and not pedantic — a library examined
there resolved its own imports only because its `pyproject.toml` put an outside directory on the
pytest path (*The kernel boundary* above), and the same mechanism hid an uninstallable package for
the life of that project.

**Why the baseline is in the exit criterion at all.** Phases 2 and 4 build retrieval, generation and
evaluation. Every design decision inside them — a fusion weight, a rerank order, a chunk size — is a
quality claim, and nothing in Phases 0–5 measures a quality claim. Making the baseline an exit criterion
of Phase 6 rather than a hoped-for follow-up is what stops the release from being the first time anyone
asks. The prerequisite is specified in `09-release.md` §4, and the tolerance the exit criterion is
judged against is derived there rather than chosen here (`09` §4.3, V3 and V4).

**What the exit installs is not decided here.** The criterion says a stranger installs *the release
unit* and reproduces the baseline. Which unit that is — a lockstep version, a single distribution, or a
named set — is **G10**'s, and `09` §1 recommends an answer rather than fixing one. The criterion is written
so that only the noun changes when G10 returns: what it demonstrates is that an installation from an
index, not a checkout, reproduces a published number.

### Phase 7 — The agent

**Added 2026-08-18 by G8, logged as scope decision `S3`** (`09` §6.1 and §6.4). The agentic front
end: a model that plans, calls Weft's commands as tools and acts on the corpus — shipped as a
first-party pack, not as part of the CLI.

**Why it is a pack and not the REPL.** `03`'s governing rule is that every operation the CLI performs
is a library call a FastAPI route could make identically, and a planning loop is not that — it is the
largest piece of logic in an agentic product. Putting it behind the prompt would make the REPL the one
adapter able to do something no other caller can, which is the shape that rule exists to refuse. As a
pack it is driven by the REPL, a script and an HTTP caller alike.

**Why it is after release rather than before.** It is the largest consumer of contract surface Weft
will have, so it should be built against **published, versioned** contracts rather than moving ones —
which puts it after **G9** (Phase 5) and after the release that publishes them. That ordering also
buys the strongest available form of this project's own thesis: Phase 5 proves an outsider can build
a pack against the source tree, and this proves a first-party pack can be built against nothing but
the released API, on the same terms a stranger has.

- **Gate:** `05` → **G12** what a permission class means when the caller is never a TTY. `03` →
  *Permissions* is unchanged until it closes: an `ask`-class operation fails without a TTY, an agent
  is never a TTY, so a pack here cannot `overwrite` or `destroy` on its own. G12 either accepts that
  ceiling or argues past it. **This is where the `agentic-patterns` handoff lands** — G8 moved it here
  from Phase 3 because the questions that skill asks (autonomy level, reasoning loop, tool contracts,
  human approval, memory) are unanswerable against contracts that do not exist yet.
- **Read:** `03` in full, and `02` §1 — the agent consumes contracts rather than defining them.
- **Lift:** nothing. No agent exists elsewhere to draw from.
- **Exit:** the agentic pack is installed from the index alongside the release, drives a corpus
  end to end through the published command surface with no edit to core and no private API, and
  `weft plugins doctor` reports it exactly as it reports any other pack.

### Phase 8 — From engine to product

**Added 2026-09-05, logged as scope decision `S9`.** The engine expresses far more than it ships.
Phases 0–6 built the mechanism and proved it; this phase is about the *distance between what Weft
can express and what a user can reach*, which nothing before it was measuring. It was found by
counting: four pipeline documents in the whole tree, naming ten plugins, against forty-eight
plugins registered into pipeline positions — so the promise "naive to advanced, quickly" was true
of the engine and false of the product, and a user met ten techniques and had to write YAML from
scratch to reach the rest.

**It runs before Phase 7, and the numbering is deliberate rather than an accident.** Phase 7 is
gated by **G12**, which is open; this phase has no gate at all. The number records where it was
added to the plan, not where it sits in the queue — `docs/README.md`'s **Next action** row is the
mechanism that carries an ordering the ledger's own sequence does not express, and it is pointed
here. `scripts/next_task.py` will still print `7.1` as the first unticked box, which is why that
row outranks ledger order and why this paragraph exists rather than a silent renumbering of a
phase somebody may already have cited.

**What it absorbs.** `ROADMAP.md` was a working shortlist ordered by effect ÷ effort, written
because the ordering kept being re-derived between sessions, and it explicitly held no state
because nothing could tick a row on it. That was the right shape for a list with no phase and the
wrong one the moment a row got built: `rerank-then-generate` shipped as a side effect of the
ladder, closing row 5, and there was nowhere to say so. Its rows are now this phase's tasks, its
ordering argument is below, and the file itself is retired to a pointer. **Row 6 — the graph as a
shipped pack — is deliberately not here**: it is blocked on three decisions (whether a graph store
is in the G4 family, where a corpus-wide revisable pass may run, where per-corpus curated
configuration lives), the first two of which touch G2, G4, G5 and `S5` at once. A phase does not
absorb work that is not schedulable.

**The ordering, kept from the list it replaces.** The ladder is what you demonstrate; hybrid
retrieval is the rung that makes the demonstration impressive; the fan-out cap is what stops the
impressive thing saturating a stranger's rate limit on their first real corpus. The falsification
instrument is out of order by wow and in order by consequence: the ability to show that a claimed
improvement is *not* real is what makes every later claim about the rungs worth anything, and both
2026-09-05 audits reached that independently.

- **Gate:** none. Every decision this phase needs is settled — G2 gave it derivation, G4 the store
  family, G10 the distribution it ships from. It is the first phase since Phase 2 with no gate line
  to read, which is itself why it is schedulable while Phase 7 is not.
- **Read:** `02` §3 in full — the operator set, `extends`, slots, and the `route.summary` contract a
  routable document signs; `10` in full, because every rung whose name comes from the literature is
  a published claim `10` either supports or withdraws; and `09` §4, because rows that assert an
  improvement are judged against the baseline that section specifies rather than against an opinion.
- **Lift:** nothing new, and one scar already recorded as a rule. `01` item 11's own worked example —
  a strategy that registers, is listed, is described to an LLM in a routing prompt, and can
  never run — turned out to have a live instance in *this* tree, one contract over: the router's
  name was a constant in `weft-cli`, so `threshold-ladder` and `always` were registered, listed,
  catalogued in `10` §1.5, and placeable by nobody. Fitness function 16 exists because reading for
  that shape is not the same as checking for it.
- **Exit:** on a machine that is not this repository, against an installed `weft-rag` and one
  container: a corpus is indexed through a **shipped ingest document**, and the same question is
  answered through **at least three rungs of the shipped ladder**, one of which fuses vector and
  full-text results retrieved from the same store. **Fitness function 16 is wired and green with its
  waiver empty** — so every plugin the default install registers into a pipeline position is named
  by a document somebody can run, with no position parked behind a reason. No run issues more
  concurrent model calls than its own configured cap, demonstrated by a corpus large enough that an
  uncapped run would exceed it. And `weft eval` reports whether the difference between two of those
  rungs falls outside the interval the published baseline recorded across its own repetitions —
  **either answer discharges this criterion**, because the instrument being able to say "no" is the
  whole of what it is for.

**Why the exit says "either answer".** Every other phase exit is a property that must hold. This one
is deliberately not, and it is the only place in this plan where that is right: a criterion reading
*"and the advanced rung measures better"* would make the phase pass by choosing a favourable
question set, which is the exact failure the instrument is being built to detect. What has to be
demonstrated is that the measurement runs and that its answer is believed — not which answer it
gives.

---

**If a gate reopens mid-phase.** Discovering that a closed decision was wrong is information, not
failure — but it is a stop, not a patch. Re-run that session, then re-check the phases downstream
of it, because the ordering table in `05` exists precisely because these decisions cascade.

## Fitness functions

Architecture that is not enforced decays. An audited codebase proves both halves of that sentence,
and measurement bore it out: **every concern the machinery did automatically held perfectly; every
concern an author had to remember decayed.** Spans applied at registration held on all ten
strategies; spans written by hand decayed to 58 `traced_operation` sites, 5 with no `span_kind`, 9
hand-rolled bypasses, 38 of 54 names off-convention, and an entire untraced ingest stage.
`get_logger` held — **0 `print()` in 259 files**. The catalog file its own standard required did not
exist. **The generalisation to adopt: move every cross-cutting concern to the registration seam.**

All checks run in CI, before tests.

0. **The gate must be in the gate.** Every architecture check runs inside the composite task the
   docs name as canonical, and a test asserts that membership. This function exists because of a
   finding elsewhere: a `hex-boundary` check was **not** wired into its own canonical full gate —
   the composite it should have run inside resolved to a narrower task that omitted it, and its
   pre-commit configuration omitted it too. **A fitness function that is not wired into the
   canonical CI task is not a fitness function.** The pattern to reimplement is a genuinely good one
   observed there: an 18-line test that pins a named waiver constant to empty, fails with a message
   stating the waiver policy, and is itself unit-tested. That is a ratchet rather than a snapshot,
   which is the property that makes it work.
1. **Boundary.** Nothing under the library may import anything the library does not ship. Derived
   from the dependency set, never enumerated as a denylist of prefixes. **Lifted as a technique,
   rewritten as a rule** — see the correction below. **G1 gave this a second, cheaper half:** because
   the kernel is its own distribution, the primary check is to install `weft-kernel` alone in a clean
   environment and import it. It declares `pydantic` and `opentelemetry-api`; if anything else is
   reachable, the import fails and no AST walk was needed. The static rule still runs, for the
   distributions that ship together and can therefore see each other.
2. **No privileged built-ins.** No built-in plugin is imported by the kernel, and no built-in is
   registered by any path a third party could not use. This directly encodes rule 4. **It must be a
   runtime check, not a static one:** after discovery, the registry's contents must equal what the
   installed distributions declared. A static check would have passed a codebase examined elsewhere,
   whose evaluation import registered **17 of 23** evaluators and whose enhancer count was 3 or 4
   depending on which function you called. It also contained the single most literal instance of the
   defect this function exists to catch: a registry module re-wrapped and re-assigned three indexing
   builders *after* a decorator had already registered them, to add span wrapping — *"INDEXING_BUILDERS
   is updated in-place so strategy dispatch also uses spans"* — so a plugin registering through the
   public decorator would silently not get the observability the built-ins got. Note this is the same
   computation `weft plugins doctor` (`03`) has to perform, so the fitness function and the CLI
   command are one piece of code.
3. **Kernel budget — 3,500 lines, review at 2,800.** The kernel fails the build above a stated size.
   A number, argued once, then enforced. The point is not the number; it is that growth becomes a
   conversation. **Settled in G1, 2026-08-10:**

   - **What is counted:** non-blank, non-comment, **non-docstring** Python lines in the `weft-kernel`
     distribution, tests excluded. Docstrings are excluded deliberately, so the budget can never
     become an argument against documenting the kernel.
   - **The number: 3,500, failing the build. 2,800 (80%) is a review trigger** — crossing it does not
     fail anything, it puts kernel growth on the agenda before the ceiling is a crisis.
   - **The reason, because a number without one gets waived:** a codebase examined during design
     measured 13,969 non-blank lines in its core-analogous layer, across 87 files (`engine/`-equivalent
     7,038 · `ports/`-equivalent 2,191 · `prompt/`-equivalent 1,628 · `models/`-equivalent 905 ·
     `llm/`-equivalent 897 · `config/`-equivalent 736 · `observability/`-equivalent 299 · top level
     247 · `utils/`-equivalent 28). Under the G1 boundary, the engine, prompt and LLM layers are
     packs. What remains kernel-analogous is `observability` 299 + `config` 736 + `models` 905 + a
     thin slice of `ports` (~250 for three contract *mechanisms* against 55 contracts observed there,
     52 of which had no in-library implementation) + context and the registry factory (~300) ≈
     **2,500** — plus the discovery, pipeline and derivation machinery that codebase has **none** of,
     600–900. The honest estimate is **≈ 3,300**, so 3,500 leaves enough headroom to be legitimate
     and not enough to be ignored.
   - **The revision rule, which is the part that actually does the work:** the constant may be
     changed **only by a dated entry in the decision log**, never in the same pull request that grew
     the kernel. This is the ratchet property that makes `test_allowlist_empty.py` — a pattern
     observed elsewhere — its best fitness function — the waiver is a deliberate, visible act rather
     than a silent edit.
   - **Known limitation, recorded rather than solved:** lines are a proxy for published surface, and
     a kernel can sit at 3,400 lines while its API doubles. The surface governor today is `01`'s cap
     of three published contracts in Phase 0 and the G1 rule that the kernel names no capability. If
     that proves insufficient, the second number to add is a public-symbol cap.
   - **Review, 2026-08-20 — the trigger fired at task 2.36, and this is the conversation it asked
     for. Both constants stand, unchanged.** Measured at Phase 3's close with the check's own
     counter: **2,891** lines — 609 under the ceiling, 91 over the trigger. The finding worth
     recording is that the estimate above was **right in total and wrong in distribution**. The
     machinery that codebase has **none** of — `resolution.py` 676 + `pipeline.py` 310 + `discovery.py`
     300 = **1,286** — cost roughly double its 600–900 estimate, while the payload model came in at
     **272** against the 905 its analogue suggested, because G5's `Node` admits six fields
     by rule and pushes every other one into a pack's own extension model. The two errors very
     nearly cancel; the registry-and-context estimate (~300) landed at **259**. What matters is
     where the residue sits: in the derivation machinery G1 named as the kernel's reason to exist,
     not in capability knowledge. That last clause is not asserted — fitness functions 1, 2 and 9
     fail the build on capability knowledge in the kernel, and Phase 3's own two additions
     (`required_declarations`, +17; the seam's `guard_blocking_calls`, +5) are capability-blind
     registration-seam work. **No line moves out and neither constant moves**; a split argued from
     a number that is under its own budget would be architecture bought on a hunch.
   - **What Phase 4 may therefore add, decided here rather than task by task.** Spans on every stage
     (ledger 4.5) attach at the **registration seam**, which is kernel by G1's own rule that
     cross-cutting concerns live at the seam and never in a rule an author must remember — budgeted,
     small, and already half-built in `seam.py`. The metric suite (4.1, 4.2) is a **pack**,
     `weft-eval`; `tests/architecture/test_eval_is_not_a_subsystem.py` already fails the build if the
     throwaway harness under `eval/` grows into one instead of being replaced by it. **Run
     persistence (4.4) is not kernel**: what a run record must contain is evaluation knowledge, and a
     kernel that knows what a run is *for* is a kernel that names a capability. **The forcing
     function, stated so this entry is falsifiable:** if Phase 4 finds that run persistence cannot be
     built outside the kernel, that reopens this review rather than editing a constant.
4. **No closed enumeration of registry keys — anywhere a name is decided.** Two clauses. (a) No enum
   shadows a registry. (b) **No literal enumeration of registry keys may appear in a dispatch, a
   validator or a routing decision**, expressed as a runtime property —
   `set(valid_names) == set(registry.keys())` asserted for every selection surface — rather than as
   a grep.
5. **Every declared capability resolves.** Every capability a plugin declares must resolve to a live
   implementation at discovery time, or the plugin must declare it unavailable and say why.
6. **Contracts are versioned.** Every published contract carries a version, and a check fails on a
   changed contract whose version did not move. **Built at task 5.2a, sharpened against what a
   working check can actually assert** (`docs/09-release.md` §2.3; `docs/lessons.md` L5.4, L5.6):
   nothing in this repository is tagged or released before Phase 6, so a diff against a stored
   snapshot would rot at the first accepted bump and catch nothing a reviewer had not already seen.
   What `tests/architecture/test_ff6_contract_version_binding.py` checks instead, from two
   independently-read sources — the constant by parsing `contract.py`, the distribution version
   from its own `pyproject.toml` — is G9's binding rule: a contract's version can never outrun the
   distribution that publishes it. A contract bumped without its distribution keeping pace fails
   immediately; a contract silently left unbumped for a real change is outside what this check can
   see without human judgement about what "changed" means for a Protocol body, and is recorded as a
   known gap rather than asserted shut.
7. **Colour integrity.** Two clauses, from G6, and **no tuning constants in either.**
   (a) **One bridge.** `asyncio.run` appears exactly once in the tree, at `weft-cli`'s entry point,
   asserted by path — so a second one fails the build rather than being noticed in review. This
   exists because a single bridge observed elsewhere was safe only by docstring.
   (b) **No blocking call at the stage seam.** While a stage is executing, the kernel's registration
   wrapper — the same one that applies spans and error attribution — installs a detector for
   blocking calls on the loop thread: file IO, sockets, `time.sleep`, `subprocess`, synchronous
   database drivers. A stage that makes one fails, naming the stage and the call. Because it is
   scoped to stage execution, fixtures, imports and model downloads sit outside it by construction,
   which is where false positives would otherwise come from. It ships in the pack test kit, so a
   third party's stage is checked before publication rather than after.

   **What (b) deliberately does not catch, and why there is no third clause.** A stage that hogs the
   loop with pure computation makes no blocking call, so no categorical check can see it. The
   rejected alternative was a slow-callback duration threshold, and it was rejected on the same
   grounds that make the kernel budget work: a threshold is machine-dependent, so it either floods CI
   on a slow runner or silently disables itself on a fast one — and unlike the kernel budget, its
   correct value changes *legitimately* with every runner, dependency bump and algorithm improvement,
   so it cannot be ratcheted. A number nobody can defend gets re-baselined until it means nothing.
   The signal is not lost: every stage already emits a span carrying its duration, so loop hogging is
   visible in a trace. If it ever needs to be a gate, that belongs in Phase 4, measured on a real
   corpus against persisted runs, not in a unit test against a synthetic batch.
8. **Trust integrity.** Three clauses, from G3, all categorical and carrying no tuning constants.
   Each is stated as a **property**, never as a command list or an API shape, so a later phase can
   satisfy it however it likes. They rely on a **canary**: a test-only distribution that publishes a
   `weft.packs` entry point and writes a marker file *at module import*, before `register()` runs. The
   assertion is always "marker absent", which needs no timing and survives a subprocess boundary.

   (a) **Refusal precedes execution.** With an allow-list active that excludes the canary, discovery
   does not import it. Paired: resolving a pipeline that names the canary's plugin exits **3** and the
   message names the distribution and the config key that would permit it. *Active from Phase 0.*
   (b) **No pack code executes for a command that does not need the registry.** Canary installed and
   *allowed*, marker still absent. Without this clause, "discovery runs when a command needs the
   registry" is a sentence in a document. *Active from Phase 0* — corrected 2026-08-15, having
   originally read *"from Phase 3, when a command surface exists"*. Phase 0 ships `weft --version`,
   which is precisely the command this clause is about; see `06-phase-0-build.md` step 9.
   (c) **The run record names the active distribution set**, equal to what `plugins doctor` reports
   as `active`. *Active from Phase 4*, which is where runs are persisted.

   **Why (b) and (c) are written now rather than when their surfaces exist.** They are the enforcement
   for the two halves of the trust model that run whether or not anyone opts in — eager discovery's
   scope, and the recorded pack set. A clause deferred to "when we get there" is a clause an author
   has to remember, and the preamble to this section is the measurement of what happens to those.
   Writing them early paid immediately: sequencing Phase 0 in `06` showed that (b) was assigned to the
   wrong phase, which a clause written later would simply have been born with.
   Their activation is therefore an **exit criterion of the phase that makes them runnable**, in the
   phase script below, so switching one on is a visible act and leaving it off fails a phase exit
   instead of passing silently.
9. **Extension is proven from outside.** Every published contract has an implementation that lives
   outside the workspace, is installed rather than linked, and is nowhere named by core. Three
   clauses, all categorical, and **no tuning constants in any of them** — no threshold, no file
   count, no percentage — for the same reason fitness functions 7 and 8 carry none: a number like
   *"fewer than five files"* is one nobody can defend, and it gets re-baselined until it means
   nothing. The *cost* of extending is argued in `07-extension-cost.md` §1 and judged per change by
   the `weft-qualities` lens; this function asserts the tree property that makes that argument
   checkable, and claims nothing about a diff.

   (a) **The stranger runs.** Each example pack lives outside `packages/`, outside `testing/`, and
   outside the uv workspace, with its own `pyproject.toml`. The test builds the first-party
   distributions as wheels, installs them plus the example pack into a throwaway environment, and
   runs a pipeline that names the example's plugin — with the source tree not on the path, so no
   path a workspace member has can be the reason it works. **How it fails:** put the example back on
   the path as a workspace member and the wheel build stops covering it; break the entry point and
   resolution fails naming the plugin. It is `06` step 10 generalised from one chunker to every
   published contract. *Active from Phase 0*, where step 10 already builds
   `examples/weft-example-chunker/`.

   (b) **Core does not know the stranger exists.** No file under `packages/` or `testing/` names any
   example pack — not as an import, not as an entry point, not as a string literal of its
   distribution name or of any plugin name it registers. The two sides are computed from different
   places and never from each other: the names come from the example packs' own metadata and their
   observed registrations, the text comes from the first-party source tree. **How it fails:** a
   conftest that special-cases the example, a workspace member listing it, a test asserting on its
   plugin name. Like item 0's model, the check is **itself unit-tested** against a planted
   literal, so a clause that stopped being able to fail would fail its own test. Clause (a) proves
   the pack works; (b) proves it works without having been anticipated, which is the half a demo
   always quietly fails. *Active from Phase 0.*

   (c) **Every published contract has a stranger.** The set of contracts published by the installed
   first-party distributions equals the set of contracts implemented by out-of-tree example packs.
   Both sides are observed at runtime and **neither is derived from the other**: the left from the
   first-party packs' own registrations, the right from each example pack installed on its own. A
   clause whose two sides came from one computation would be the `test_keys_parity` defect observed
   elsewhere, which cannot fail at all. **How it fails:** publish a
   contract and ship no example for it — which is the everyday case this clause exists to catch. It
   carries a **ratchet** in the style of item 0: a named constant
   `CONTRACTS_WITHOUT_AN_EXAMPLE_PACK`, pinned empty, so an exemption is a visible entry in a diff
   rather than a silent edit, changeable only by a dated decision-log entry. *Active from Phase 2*,
   the first phase that publishes a contract Phase 0 did not, and its activation is an exit
   criterion of that phase.

   **Why it exists.** Requirement 1 is the thesis of the project and it is the only one of the six
   that has never been enforced by anything. An earlier audit is why that matters: adding one
   storage backend there meant editing **11 files inside the library** plus at least 3 in its
   deployment layer, against **"None at all — 0 registered names"** and 17 dispatch sites of which
   0 were registry lookups. Nothing in that project's CI measured that, and nothing could have — its
   own boundary checker was not in its canonical gate and exited 0 on a tree with 11 violations
   (fitness function 0). Weft's gap today is narrower and the same shape: the requirement is applied
   by a human running the `weft-qualities` lens, and a lens is not a ratchet.

   **What it deliberately does not catch, and why there is no fourth clause.**

   - **Reachability.** A plugin can register from outside, cost zero core edits, and still never
     execute — the sharpest finding from that audit, where a third-party strategy registers, is
     listed, is described to the LLM in the routing prompt, and hits three walls. That is
     **fitness function 4(b)**'s job. Function 9 asserts that extension happens from outside; 4(b)
     asserts the extension can *run*. Reading 9 as covering both is how that seam would pass a green
     build.
   - **Cost, per change.** A pack needing 400 lines of boilerplate passes clause (a) exactly as a
     four-file one does, and a core edit made in the same commit for an unrelated reason is
     invisible to all three clauses. This is a property of the tree, not of a pull request. The file
     cost is argued in `07-extension-cost.md` §1 and judged per change by review — a line budget on
     a pack would be a tuning constant, which is the thing this function refuses.
   - **Wrong-shaped extension points.** A pack may need a core change to be *useful* rather than to
     *load*: an extension point that exists but in the wrong shape. That is Phase 5's human test —
     *if they file an issue asking for a core change, that is a design finding* — and **G7**'s
     question.
10. **Ship-set integrity.** Two clauses, both categorical and carrying no tuning constants — not a
    threshold, not a file count, not a percentage. **Neither depends on how G9 or G10 settles**: each
    holds under lockstep, under independent semver, and under a named release set. *Active from Phase 6*,
    which is the phase that makes them runnable; per the note under 8, switching them on is an exit
    criterion of that phase rather than an intention.

    (a) **The publish set and the workspace agree.** Two sets are computed from **different sources** and
    compared: on one side, the distributions the release job actually passes to the index; on the other,
    the workspace members (`[tool.uv.workspace] members`) that do not carry an opt-out marker in their
    own `pyproject.toml`. The check fails if either side holds a distribution the other does not. It is
    stated this way so that it can fail *independently of the implementation* — a check that asked the
    derivation function what it derives would compare a function to itself and could never fail, which is
    the same `test_keys_parity` shape observed elsewhere. Here a hand-maintained
    publish list, a new package nobody added to it, or a distribution that opts out and is published
    anyway each break it. `testing/weft-canary` — whose entire purpose is to be *refused* by discovery
    (fitness function 8) — is the standing test case: it must always be on the opt-out side and never in
    the publish job's arguments.

    (b) **No distribution depends on a sibling without a version bound.** Every intra-repository
    dependency declares one, asserted as a property over the workspace rather than as a lint of one file.
    This exists because the tree today declares `dependencies = ["weft-kernel"]` in every pack, which
    permits any pack against any kernel, and **any** compatibility policy is unenforceable on top of an
    unbounded requirement. What a bound *means* — a floor, a compatible range, or an exact pin — is
    **G9**'s and this clause does not choose: a floor is the weakest of the three and is implied by all
    of them, so if G9 settles on lockstep or on negotiation this clause tightens rather than changes.
11. **Pipeline integrity.** Two clauses, from G2, both categorical and carrying no tuning constants.
    *Active from Phase 1*, the phase that makes them runnable; per the note under 8, switching them on
    is an exit criterion of that phase.

    (a) **The operator set stays closed.** `02` §3 states *"the set stays closed until something real
    needs a fifth"*, and a rule with no mechanism is the thing this section exists to prevent. The
    four operator names are pinned in a named constant with a waiver constant pinned empty, in the
    style of item 0, so a fifth operator fails the build until someone changes a constant in a diff
    and records why in the decision log. **How it fails:** add a `move` operator because a case looked
    awkward, and the build says so before review does.

    (b) **Every shipped pipeline resolves.** Every pipeline shipped by a first-party pack, by an
    example pack, or quoted as runnable in the manuals resolves against the installed registry in
    `ci-checks`. This is "registration is not reachability" in its data costume: a pipeline file is
    text that rots silently while every unit test passes, which is exactly the shape observed
    elsewhere in a strategy that registers, is listed, is described to the LLM, and can never run.
    **How it fails:** rename a plugin and leave `base.yaml` naming the old one — caught in the gate
    rather than on a user's first index run.

12. **An unknown name names the alternatives.** Requirement 5 has two clauses and until now only the
    first was enforced: fitness function 4 removes the closed key spaces a name could be silently
    coerced into, but nothing checked the other half — that the refusal *names the valid options*.
    Every error class whose failure mode is an unresolvable name carries those options as a **typed
    field**, not only interpolated into its message, and the check asserts that across the family with
    a waiver constant pinned empty in the style of item 0. **Added by G11 (2026-08-18), and active
    from Phase 2**, the phase that closed the gate; per the note under 8, it is wired into `ci-checks`
    in the same commit that adds it.

    **Why a field rather than a string match.** A test that greps a message for a comma-separated list
    is a test of prose, and it passes the moment someone writes a plausible-looking sentence. A typed
    field is a structural fact the renderer formats, so the options cannot be stale, cannot be omitted
    while the message still reads well, and can be shown differently by a different adapter without
    re-deriving them. **How it fails:** add a `Retriever` lookup that raises `UnknownPluginError`
    without collecting the registered names, and the build says so — rather than a user meeting
    *"unknown retriever: 'graf'"* with no way to discover that `graph` was one character away.

    **There is a concrete precedent for the argument.** In a codebase examined during design, this
    convention appeared *correctly* at nine sites and was missing at three, out of twelve total, and
    the verdict on why is one line: *"doing it by hand at nine sites is why three sites do not."*
    Weft has 82 error classes, of which **20** are in this family. That is already twice the point
    where the earlier approach failed, and G11 was required before Phase 3 precisely because that is
    where the surface multiplies again.

    > **Corrected 2026-08-18, task 2.36.** This paragraph said 18. The task that turns this function on
    > audited all 82 by reading every raise site for whether it already computes and interpolates a
    > concrete, enumerable collection of the names that were valid where the one given was not — the
    > structural line `tests/architecture/test_ff12_unresolvable_name_carries_options.py`'s own module
    > docstring states — and found **20**: `weft_cli.run_services.StoreCapabilityMissingError` (its
    > message already named the store names that *do* provide the missing capability) and
    > `weft_prompts.errors.TemplateVariableError` (one of its two raise sites already named the input
    > model's fields, for the placeholder-not-supplied case) joined the 18 this section originally
    > named. Membership is `weft_kernel.errors.UnresolvedNameError`, a marker mixed into each of the 20
    > alongside whichever `WeftError` subclass it already was, checked structurally
    > (`issubclass`, plus a required, typed `valid_options: tuple[str, ...]` constructor parameter with
    > no default) rather than by class name or by grepping a message.
    >
    > **Corrected again 2026-08-18, same day: the sentence above once derived the original 18 from a
    > name pattern, and that derivation was checked and found false.** It said the 18 were "the class
    > name reads `Unknown`/`Unresolved`/`Ambiguous`" and the two misses were the ones whose names did
    > not. Counted directly against `NAME_RESOLUTION_FAMILY`: of the 20, only **12** class names
    > contain `Unknown`, `Unresolved` or `Ambiguous` — `UndefinedVarError`, `StaleOperatorTargetError`,
    > `UnclaimedFormatError`, `UnroutedPipelineNameError`, `UnmappedLLMRoleError` and
    > `UnaddressableFieldError` are six more misses a name pattern would have produced, on top of the
    > two this section already names. The 18 in this section never came from a name pattern at all —
    > they came from the same thing the audit above did one level earlier: reading each error's own
    > failure mode by hand and judging whether it already reports an enumerable set of alternatives.
    > A name pattern applied in place of that reading finds 12, eight short — which is not a footnote,
    > it is the argument this whole item makes: "doing it by hand... is why sites do not," restated one
    > level up, in this audit's own working. That is why fitness function 12 checks `issubclass(cls,
    > UnresolvedNameError)` — a structural fact set once at the class definition — rather than a name a
    > reviewer could reasonably, and wrongly, expect to be reliable.

    > **Second clause added 2026-08-20, from a Phase 3 fitness-function review (not a build-ledger
    > task; `402a957`'s own two findings are its evidence).** The structural check above proves every
    > *named* family member carries `valid_options` — but membership is opt-in, and `402a957` found two
    > raise sites doing exactly what this item forbids while staying invisible to it: `weft_cli.
    > permission_policy` interpolated computed valid keys into a bare `WeftError`'s message, and
    > `weft_cli.registry_bootstrap.require_plugin` caught `weft_kernel.registry.UnknownPluginError` —
    > which already carries `valid_options` — and discarded it into a string before raising an untyped
    > sibling. Both were repaired by hand; nothing had caught either automatically. `tests/architecture/
    > test_ff12b_a_repack_keeps_valid_options.py` is the second clause this leaves FF12 with: a
    > catch-and-repack check — a function that catches an `UnresolvedNameError` subclass and, in the
    > same handler, raises a `WeftError` that is not one — mechanical, message-blind, and empirically
    > silent on the tree today (zero matches across all 130 first-party modules), which is why its own
    > waiver ships pinned empty rather than pre-populated. **A second candidate was built and measured,
    > then rejected**: flagging any raise of a non-family `WeftError` whose message is built from a
    > `sorted(...)`, a comprehension, or a `.join(...)` call — the shape `weft_cli.permission_policy`'s
    > own pre-repair site had. Run against the real tree, 13 raise sites match that syntactic shape and
    > 11 are not name-resolution failures at all (a closed `StrEnum`'s value check, a contract shape
    > violation, an inert pin, a Pydantic validation report, a type-provision gap, a pipeline cycle, a
    > slot-ordering collision, a fallback's capability mismatch, an API error, an unused-field report,
    > a missing required locale) — distinguishing "these are the valid alternatives for a name" from
    > "this is some other enumerable fact this raise happens to report" is a question about meaning, not
    > shape, and a checker precise enough to need no hand-maintained exclusion list would have to
    > re-derive, structurally, the judgement task 2.36's own audit made by reading every site — the
    > same lesson stated above ("doing it by hand at nine sites is why three sites do not"), applied
    > to the checker itself. **The other 2 of the 13 were real, name-resolution refusals with no typed
    > field, repaired 2026-08-20**: `weft_cli.services.service_selection_from_config`'s unknown-
    > `[services]`-key refusal now raises `UnknownServiceKeyError`, and `weft_cli.llm_roles.
    > llm_section_from_config`'s unknown-`[llm]`-key refusal now raises `UnknownLLMKeyError`, both
    > the identical shape `weft_cli.config_surface.UnknownConfigKeyError` already handles correctly
    > for `config get`/`config set`'s own vocabulary. `NAME_RESOLUTION_FAMILY`: 24 -> 26. No kernel
    > line either repair. Reproduced against a real checkout in `manual/troubleshooting.md`'s own
    > entries for both classes.
13. **Every dispatch over a published `Enum` is exhaustive by construction.** Added by task 5.2b
    (`docs/build-ledger.md`), from `docs/09-release.md` §2.3: *"A version bump does not fix
    silence, so silence is a separate defect. Adding an `Enum` member is textbook-additive and, in
    this tree, makes a backend answer the wrong query without erroring... A published `Enum` must
    therefore be dispatched exhaustively by construction, with no fall-through default —
    requirement 5 applied to a closed vocabulary instead of an open one."* **Active from Phase 5**,
    which is where the task that builds it lands; per the note under item 8, switching it on is an
    exit criterion of that phase.

    **A new numbered function rather than a third clause of item 4.** Item 4 is the nearest
    neighbour — both are about a closed vocabulary and a dispatch over it — but its own proof
    technique is the *inverse* of this one's. FF4(b) manufactures a name **nothing was told
    about** and proves the registry still selects and runs it, which is what makes a registry key
    space *open*; it would fail the instant a hard-coded branch could not produce a fresh UUID. This
    function manufactures an operator **nothing was told about** and proves every dispatch
    **refuses** it, which is what makes a closed vocabulary — `FilterOp`, serialised into stored
    data rather than resolved against a live plugin set — actually stay closed instead of silently
    admitting whatever it gains next. A registry key space and a closed enum are the same shape
    read in opposite directions, and folding the closed case into item 4's own clause (b) would
    make its one runtime property answer two different questions depending on which side of "open"
    or "closed" the vocabulary under test happens to be — which is exactly the ambiguity a numbered
    list of properties exists to prevent.

    **The property**, `tests/architecture/test_ff13_filter_op_dispatch_is_exhaustive.py`:
    manufacture a `FilterOp`-shaped value none of the enum's real members equal, drive every
    dispatch that branches on `FilterOp` identity with it, and assert each one raises
    `weft_store.contract.UnhandledFilterOpError` rather than answering. A permitted set *derived*
    from the enum (`weft_store.fields._ADMITTED[FieldKind.EXTENSION]`, pre-task) is the same defect
    in a different shape — it does not fall through, it silently widens — so its own clause asserts
    the manufactured value is admitted by none of `FieldKind`'s three permitted sets, not only that
    a raise occurs. `test_the_check_can_actually_fail` reproduces the pre-fix shape of
    `weft_qdrant.store._range` inline and shows it answers `"gte"` for the manufactured operator
    instead of raising, in the style item 0's own waiver test and FF6's and FF9's `test_the_check_
    can_actually_fail` already use.

    **Nine sites, not five.** `docs/09-release.md` §2.3 names five: `weft_qdrant.store._condition`,
    `_range` and `to_qdrant_filter`, `weft_store.contract.Filter._shape_matches_op`, and
    `weft_store.fields`'s derived permitted set. Task 5.2b's own audit found four more with the
    identical shape in `weft_store.pgvector_store` — `_predicate`, `_text_predicate`,
    `_text_set_predicate` and `_extension_predicate` — the SQL half of the same task 2.6
    translation the five named sites cover only the Qdrant half of. `docs/lessons.md` L5.14 records
    that a hand-enumerated "known sites" list undercounted by not auditing the sibling backend
    doing the identical job, the same "doing it by hand at nine sites is why three sites do
    not" lesson one level up from item 12's family.

14. **Every declared `ExtModel` reaches the rehydration registry.** Added by task 5.2g. A pack's
    own `weft_kernel.payload.ext.ExtModel` — its namespaced extension data — must be reconstructable
    by whatever store reads it back, or a node carrying that namespace cannot survive a round trip
    at all: `weft_store.rehydrate.rehydrate_ext` raises `UnknownPluginError` for any namespace
    `weft_store.rehydrate.ext_models` was never told about. **Active from Phase 5**, which is where
    the task that builds it lands; per the note under item 8, switching it on is an exit criterion
    of that phase.

    **A new numbered function rather than a clause of item 5, even though item 5's own wording —
    "every declared capability resolves... or the plugin must declare it unavailable and say
    why" — reads as though it already covers this.** It does not, for a reason worth stating
    precisely rather than assumed: item 5 already has a real, distinct, unclaimed subject of its
    own. `docs/11-multimodal.md` names it exactly — the extractor accept set, where a format
    declared by one pack's metadata (an extension, a MIME type) must resolve to an actually
    registered `Extractor` or say why it cannot, the `.ppt` accept-then-fail bug described earlier
    in this document — and assigns it to task **1.13** in that document, unbuilt, with its
    own phase placement still an open question left to this document to answer. Folding a second,
    unrelated property into item 5 now would leave its one numbered clause answering two different
    questions depending on which surface — a capability *offer* resolving to a live implementation,
    or a *type* reaching a registry that can reconstruct it — is under test, which is the identical
    ambiguity item 13's own note refuses for item 4. The two are not the same shape read
    differently, either: item 5's property is about **conditional registration** (a pack probes an
    optional dependency and registers only what actually works, or says why not); this one is
    about a **second registry in a second distribution** (`weft_store.rehydrate.ext_models`) that
    the kernel's own `PackRegistrar` cannot populate itself, because populating it means knowing
    what a store is. Numbering it separately keeps item 5 free to be built later, against its own
    real subject, without this task's test file being read as having already discharged it.

    **The property**, `tests/architecture/test_ff14_ext_model_reaches_rehydration.py`: run real
    discovery (`weft_kernel.discovery.discover`) against the installed first-party packs, feed the
    resulting reports to `weft_store.rehydrate.register_from_reports`, and compare two
    independently-computed sets — every namespace any `ACTIVE` report's own `PackReport.ext_models`
    names (*declared*), against every namespace `weft_store.rehydrate.ext_models.names_for
    (ExtModel)` actually holds afterward (*present*) — the identical two-source shape fitness
    function 2 already uses for "declared" versus "present" in the plugin registry, applied to the
    ext-model registry instead. **How it fails:** a pack ships a new `ExtModel` and its `register()`
    never calls `add_ext_model`, or `register_from_reports` is never wired into whatever calls
    `discover()` — either way `declared` and `present` disagree, and `test_the_check_can_actually_
    fail` proves it by withholding one pack's own contribution from the reports handed to
    `register_from_reports` and showing the comparison catches exactly that pack's namespace
    missing, in the style item 0's own waiver test and FF2's, FF6's and FF9's `test_the_check_
    can_actually_fail` already use.

15. **Every `weft_kernel.resolution.resolve` call site in `weft-cli` passes `contributions=`.**
    Added by task 5.3a (`S8`). `02` §3 → *Slots*: a pack's own `Contribution` only reaches a
    pipeline if the `resolve()` call that produced it was handed one — `weft_cli.registry_
    bootstrap.build_dependencies` assembles `Dependencies.contributions` once, from every
    installed pack's own `PackReport.contributions`, but nothing at the language level stops a
    future `resolve()` call site from being wired to everything else and never that one keyword:
    it would still compile, still resolve, still pass every other test, and silently make a slot
    permanently un-fillable by any pack. **Active from Phase 5**, which is where the task that
    builds it lands; per the note under item 8, switching it on is an exit criterion of that phase.

    **A new numbered function rather than a clause of item 14, its nearest neighbour.** Item 14
    checks a *runtime* fact — two sets computed by actually running discovery and rehydration.
    This one is a *caller-shape* fact, true or false by inspection of the call before anything
    runs at all, which is why an AST walk rather than a driven discovery pass is the right proof
    technique — the identical reasoning item 13's own note gives for why a different *kind* of
    question earns its own number rather than a shared clause.

    **The property**, `tests/architecture/test_ff15_resolve_call_sites_pass_contributions.py`:
    walk every file under `weft_cli`'s own source tree, find the ones that bind `resolve` as a bare
    name via `from weft_kernel.resolution import resolve` — never a textual grep, which would
    also match `Runner.resolve` and `ServiceRegistry.resolve`, two unrelated methods called in
    the same files — and assert every `ast.Call` to that bare name carries a `contributions=`
    keyword. **How it fails:** a fourth call site imports `resolve` and calls it without that
    keyword; `test_the_check_can_actually_fail` proves it by parsing a file shaped exactly like
    that regression and showing the same walk reports it as an offender, in the style item 0's
    own waiver test and FF2's, FF6's, FF9's and FF14's `test_the_check_can_actually_fail`
    already use.
16. **Every pipeline position a shipped ladder registers is reachable from a shipped pipeline.**
    Added by Phase 8. One clause, categorical, carrying no tuning constant: a distribution that
    contributes any pipeline document at all must contribute enough of them that every plugin it
    registers into a *pipeline position* is named by one. Not a percentage and not a count of
    documents — a plugin is either reachable from something a user can run today or it is not.

    **Why this is a fitness function rather than a preference.** A pipeline is data, so the
    distance between *the engine can express this* and *a user can run this* is one YAML file —
    which is exactly the distance nobody notices growing, because nothing fails while it does.
    Measured before the check existed: four shipped documents naming ten plugins against
    forty-eight registered pipeline positions, and every one of 1,900-odd tests green, because
    each half was correct alone. **It is item 11 one question further on.** 11(b) asks whether
    every document that claims to be runnable resolves; this asks whether the documents that ship
    cover what ships beside them. The worked example item 11 quotes — a strategy that
    registers, is listed, is described to an LLM in a routing prompt, and can never run — is not
    caught by 11(b) at all, because nothing about it fails to resolve. It had a live instance in
    this tree when this item was written, and reading for the shape had not found it.

    **The property**, `tests/architecture/test_ff16_ladder_reachability.py`: run real discovery;
    take every distribution whose `PackReport.pipeline_resources` is non-empty — that derivation
    *is* the scope rule, so a pack shipping no document is held to nothing and a pack shipping one
    has taken on the ladder; take every contract with `Stage` in its `__mro__`, never a list this
    file maintains, so a query-path contract published tomorrow is covered with no edit; and
    assert every `(contract, plugin)` those distributions register appears as a `use:` in some
    contributed document. `fallback:` is excluded on 11(b)'s own stated grounds, and a `with:`
    value is out of scope by construction — its meaning belongs to the plugin declaring the field,
    not to the document — which the test's own docstring says out loud rather than leaving as a
    silent boundary. **How it fails:** register a plugin and ship no rung for it;
    `test_the_check_can_actually_fail` drives the identical computation over a planted position
    nothing names.

    **Its waiver is pinned but not at zero, and the exit criterion is what stops that being
    permanent.** Two `Renderer` names are waived because no shipped command consumes a
    `Rendition`, so a document ending in one would run and discard its only product — a fact about
    what can be run, which is the only kind of reason this waiver accepts. Phase 8's exit requires
    the waiver **empty**, so the entry is a dated debt rather than a parking space. A third and
    fourth entry were drafted and then deleted: `threshold-ladder` and `always` were unplaceable
    because the router's name was a constant in `weft-cli`, which was a true fact and still the
    wrong answer, because the fact was a defect. **A waiver reason must be a fact; that is
    necessary and not sufficient, and the question after establishing it is whether the fact
    should hold.**

17. **Every citation resolves.** Added 2026-09-05. Two clauses, categorical: a `path:line`
    citation in a tracked file must name a path that exists in this repository, and must not name
    the file it appears in.

    **This is `lessons.md` L8.7–L8.9 made mechanical, and it is the most expensive lesson this
    project has paid for.** Its own evidence rules — *measure before asserting*, *every factual
    claim carries a `path:line`* — were followed diligently for eight phases while the tree being
    cited was a sibling checkout that existed on one machine. The result was hundreds of pointers
    a reader could not follow, **thirteen of them inside published wheels**. The rule that demanded
    the evidence is the same rule that spread it, and every individual citation looked like
    diligence because it *was* diligence. Removing them took four agents and three failed
    scopings — a pattern too narrow (13 sites reported, 277 actual), a scope written as directory
    names rather than `git ls-files`, and every grep case-sensitive — each found by somebody other
    than the searcher, because **a search cannot report what its own pattern excludes.**

    **The property, `tests/architecture/test_ff17_citations_resolve.py`:** enumerate tracked files
    from `git ls-files`, never a directory list; match `path:line` citations; refuse one whose
    basename exists nowhere the repository owns, and refuse one whose basename is the containing
    file's own. Matching is on **basename**, deliberately generous, because this codebase
    abbreviates its own paths — it refuses a pointer that goes nowhere, not one that is merely
    short. **Clause (b) exists because clause (a) is blind to it:** a comment citing
    `unicode_normalizer.py:12-37` *inside* `unicode_normalizer.py`, describing a method that file
    never had, resolves perfectly — the basename collides. Three of those were found here, one
    carrying the words "verified at source".

    **How it fails:** a citation naming a file nothing here has, watched fire on a planted case in
    a real tracked file rather than only in a fixture. Waiver **pinned empty**, and it reached
    empty by the four real violations being fixed rather than recorded.

    **What it cannot check:** whether the cited *line* says what the citing comment claims. No walk
    can. What it can do is refuse a pointer that goes nowhere and one that goes in a circle, which
    together are every mechanically detectable form the defect took here.


> **Corrected 2026-08-10 — fitness function 1, and the preamble.** This section previously opened
> *"the single best thing in a codebase examined during design is its AST boundary checker"* and
> specified FF1 as *"lifted almost verbatim from it."* It is not the best thing there and it must
> not be lifted verbatim, because **it does not fire.** A `check_hex_boundary.py` script (316 lines,
> 5 rules) printed *"Hex boundary check passed."* and exited 0 on that tree — a tree that carried
> **11 runtime imports of deployment-owned namespaces**. Why it could not fire:
>
> 1. Its infrastructure-SDK denylist matched **0 imports in the entire library**. The rule was dead
>    code.
> 2. A widely-used framework package was **not** on the list, and there were **150** imports of it,
>    37 inside the core layer.
> 3. All `TYPE_CHECKING` blocks were skipped entirely.
> 4. The deployment-namespace rule fired only on `importlib.import_module` **and** only under the
>    core layer, so a plain `from adapters.storage… import` anywhere else in the library matched no
>    rule at all.
> 5. **It was not in the canonical CI composite** — hence fitness function 0 above.
>
> A four-name denylist ages into a no-op the moment the dependency set changes, and this one already
> had. Hence FF1 as reworded: derive the invariant, do not enumerate the villains. There is a second
> lesson in it that Weft should take seriously — that gate **shaped the workaround rather than
> removing the coupling**: a test named for exactly this rule is precisely why eleven modules reached
> the deployment layer through `importlib.import_module('adapters.…')` under a module `__getattr__`
> instead of a plain import. A lazy dynamic import of a literal module path is the exact evasion, and
> FF1 must police it.

> **Corrected 2026-08-10 — fitness functions 4 and 5.**
>
> **FF4** was *"a grep-level check that no enum shadows a registry."* The mechanism is right and the
> check is not sufficient: it catches a closed strategy enum shadowing its registry and misses the
> two walls that actually made an examined strategy seam unusable. (i) A 3-member
> retrieval-strategy-type enum was the **key type** of its own builder registry — there is no
> shadowing to grep for; the lock is structural, and a plugin cannot construct a fourth member at
> all. (ii) A router's score-to-strategy selector was a hard-coded 10-branch `if/elif` assigning
> literal enum members with no plugin branch — an enum check sees nothing. (iii) A
> routing-response validator hard-rejected any value not in the enum. **A third-party strategy in
> that codebase registered successfully, was listed by its metadata function, was described to the
> LLM in the routing prompt — and could never be executed.** That is the defect FF4 has to prevent,
> and only clause (b) prevents it. A runtime check is also the only thing that would have caught
> that codebase's evaluator gap (6 of 23 unregistered).
>
> **FF5** was *"no capability's metadata may appear in two maps — the file-format drift bug,
> encoded."* It encodes a bug **that never occurred**: the two format lists observed there were
> identical (17 = 17, empty symmetric difference). The bug that *did* occur is a capability declared
> unconditionally whose implementation is inserted conditionally on an optional dependency — the
> declaration is right and the *resolution* is empty. A source-text comparison would pass a tree
> where `.ppt` is declared and unresolvable. Checking the **resolved** map covers both the drift bug
> and the optional-dependency bug in one check, and it is exactly what `weft plugins doctor`
> (`03`) already has to print.

## Risks worth stating now

- **Over-generalising the kernel.** A microkernel's failure mode is a core so abstract nothing can
  be done without three indirections. Mitigation: the kernel budget, and the rule that no
  abstraction enters the kernel before two real plugins need it.
- **Contract churn.** Publishing contracts early means changing them hurts. Mitigation: Phase 0
  publishes exactly three, and the rest stay internal until a second implementation exists.
- **Plugin trust.** Entry points execute third-party code on discovery. This is a real security
  decision, deliberately unresolved here — grilling session G3.
- **Losing hard-won detail from what came before.** The cleaning order, the retry constants, the
  Polish reranker selection, the multilingual citation extraction: none are obvious, all were
  learned. All four are confirmed to the line by direct measurement. The list is also
  **incomplete**, and deliberately not extended here — an enumeration in a risk paragraph goes
  stale.
- **Losing good habits already established.** Less obvious than losing the code itself, and just as
  expensive. Direct measurement confirms: **0 `print()`** in 259 files; **0
  `FIXME`/`XXX`/`HACK`/`WORKAROUND`** markers; **no bare `# type: ignore`** — all 138 name their
  rule; the env-var discipline holding with 4 annotated exceptions; per-file `T201` ignores scoped
  exactly to one output module. These are worth carrying as explicitly as the algorithms.
