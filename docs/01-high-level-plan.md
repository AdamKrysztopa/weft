# 01 — High level plan

## Why rebuild rather than refactor

The decision is settled; this section exists so the reasoning survives into the new repo.

`a prior project` was designed to be elastically extended along at least five axes: parsing methods,
chunking, file types, retrieval engines, **and storage backends — databases and files alike**. An
audit of the shipped code found the seam holds on none of the first four, and the deep study has
since found it holds on the fifth least of all. Adding one parser means editing four to six existing
files. Adding one file format means editing six parallel structures across three files — nine edit
sites for an ordinary format, thirteen for one behind an optional dependency. Retriever builders
have a registry, but it is keyed by a closed enum, so registering one still requires editing core.
There are zero uses of `entry_points` or `pkgutil` across the 259 library files, and no
`[project.entry-points]` group in `pyproject.toml`, so nothing can be extended from outside the
package at all.

> **Corrected from the reference study (2026-08-10).** Two edits to the paragraph above, neither of
> which weakens it.
>
> The file-format claim was *"five parallel maps, two of which are independent sources of truth that
> silently drift."* Counted, it is **six** structures in **three** files: `FileType`
> (`indexing/parsing/factory.py:45-61`, 14 members), `EXTENSION_MAP` (`:65-83`, 17 keys), `MIME_MAP`
> (`:86-103`, 16), `_EXTRACTOR_MAP_BASE` (`:106-118`) → `EXTRACTOR_MAP` (`:124`),
> `FORCE_MARKDOWN_FILE_TYPES` (`:126-136`, 9), and `SUPPORTED_DOCUMENT_EXTENSIONS`
> (`indexing/supported_extensions.py:7-27`). **They do not drift today** — the two format lists have
> an empty symmetric difference, 17 = 17. The defect the sentence needs is different, and worse: a
> declaration that is right with a resolution that is empty. `.doc` and `.ppt` are declared
> *unconditionally* in both lists while their extractors are inserted *conditionally* on optional
> dependencies (`factory.py:119-122`), so a `.ppt` passes every gate and then raises
> `ValueError('No .ppt extractor available …')` at `factory.py:401-405`. This is the accept-then-fail
> bug; drift is not its mechanism. (`reference/study/10-doc-corrections.md` A1, A3.)
>
> The entry-point count was *"1,112 files"*, a repo-wide denominator that includes `system/`. The
> verified figure is **0 across the 259 library files** plus no `[project.entry-points]` block. One
> nuance the study adds and the plan should keep: **one axis is genuinely open already** —
> `@register_enhancer('keybert')` works end to end today, and the only thing missing is the import
> trigger. That is the axis driving use case A runs through, which makes Phase 0's exit criterion
> cheaper and more credible: the reference already proves decorator + lazy bootstrap + loud lookup is
> sufficient *once discovery exists*, so the genuinely new mechanism in Phase 0 is discovery itself.
> (`reference/study/10-doc-corrections.md` B13, C7.)

> **The storage axis is now audited, and the verdict is harsher than the guess this blockquote used
> to record.** The reference does declare a `VectorStoreFactory` port (`core/ports/storage.py:177-239`,
> three well-shaped, intent-named methods returning typed models), so the intent was clearly there.
> But **there is no function named `get_vector_store_factory` anywhere in the repository**, and
> there are **zero `VectorStoreFactory` implementations inside the library** — every named concrete
> lives in `system/`. Selection is constructor injection with two hard-coded escapes:
> `retrieval/storage.py:333` imports the local factory as the `None` default, `:338` imports
> `PGVectorStoreFactory` **unconditionally on every `DocumentStorage` construction**, and `:340-341`
> decides a domain-visible backend string by `isinstance` against a deployment class. The "remote
> implementation" inside the library is `VectorStoreMetadataRegistry.save_collection_metadata`,
> which unconditionally raises `NotImplementedError` with the comment *"This is a placeholder —
> actual implementation depends on vector store capabilities"*
> (`indexing/metadata_registry_vector.py:132-138`).
>
> **So storage is not the same closed-dispatch shape as the other four — it is worse.** No registry,
> no enum, no plugin point, no registered name for any backend: **0 registered names against 10 / 7
> / 14 / 3 on the other axes**, 17 dispatch sites over backend identity and zero registry lookups.
> Adding Qdrant requires editing **11 files inside the library**. It is the leakiest boundary in the
> codebase and the one that most directly threatens the zero-container requirement below, because
> `DocumentStorage.__init__` currently requires the PGVector adapter module to be importable even
> for a purely local run. Note also that the port docstrings advertise *"local filesystem, Qdrant,
> Weaviate"* and *"Elasticsearch"* (`core/ports/storage.py:30,174,181`) and **none of that code
> exists** — a false premise the rebuild must not inherit.
>
> **Corrected from the reference study (2026-08-10):** this blockquote previously labelled the axis
> unaudited and described selection through `get_vector_store_factory(provider=...)`. The audit is
> now done and that function never existed. This stops being "a first-class question for the deep
> study" and becomes a settled finding that raises **G4**'s stakes.
> (`reference/study/10-doc-corrections.md` A9; `reference/study/08-salvage.md` §T2.4.)
>
> **Unverified:** whether a *remote* `VectorStoreFactory` implementation exists at all, and whether
> it is a placeholder, concerns `system/`, which the reference study did not examine. See
> `reference/study/09-open-questions.md` §A.1.

The failure is structural, not sloppy. Every one of those seams started as a small dispatch and
grew. The predecessor also proves the counter-case: where a real string-keyed registry exists —
enhancers, prompts, evaluation metrics — extension is *nearly* clean, and `indexing/enhancers/registry.py`
(120 lines) is the design to reimplement in full — its shape, not its text; `NOTICE` rules out the
latter. But the reference's problem was never a shortage of
registries. It has **9 distinct name→thing registries and 17 registry-shaped containers across 13
files, using 6 different registration idioms with 4 different failure behaviours on an unknown
name** — and only 6 of the 17 expose any registration API. The other 11 are frozen literals,
editable only by patching core.

> **Corrected from the reference study (2026-08-10):** this paragraph read *"the pattern that works is
> already in the codebase, in one small file, applied to one of seven places it belongs"*, inherited
> from `architecture-review:18` (*"three real string-keyed registries"*). Both the count and the
> diagnosis are wrong. The reference's actual failure is that **the key space is declared separately
> from the registry**: `StrategyName` (10 members, `core/engine/types.py:56-72`) is declared in a
> different module from `STRATEGY_REGISTRY` (`core/engine/strategies/registry.py:35`); nothing keeps
> them in sync; and the config validator resolves the discrepancy by discarding the user's input.
> The study's formulation is worth quoting: *"The registry is open; the vocabulary is closed; and
> where they disagree the code prefers to guess."* The design rule this implies is stronger than
> rule 5 below, and it should be read as an addition to it: **the set of valid names must be the
> current keys of the registry, never a parallel declaration.** One further correction — "extension
> is clean" is not true of evaluation metrics: six of the 21 never register at all in the default
> import graph (see `04`). (`reference/study/10-doc-corrections.md` A7, E1, E6.)

A refactor could reach the same end state. It would also have to carry a closed `StrategyName`
enum that shadows the registry, a chunker factory living inside the evaluation package, three
separate reciprocal-rank-fusion implementations of which one is dead, and a `FileType` enum wired
into six structures across three files and an API schema and a frontend union type. The rebuild is
chosen not because the old code is bad but because **the extension model has to be the first
decision, and it cannot be retrofitted underneath 52,000 lines that assume otherwise.**

> **Unverified:** the API schema (`system/sat-db-api`) and the frontend union type
> (`system/sat-db-web`) concern `system/`, which the reference study did not examine. The library-side
> wiring is confirmed and re-counted above. See `reference/study/09-open-questions.md`.

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
> **The second clause is the one with teeth, and the reference is the evidence.** Its metric suite cannot
> be parameterised at all: a metric is selected by name, unknown names are silently dropped, and there
> is no way to run the same metric twice with different thresholds. Ten good retrieval strategies were
> shipped and a third party could not have composed them, because the router assigns literal enum
> members in a hard-coded ten-branch ladder. **An idea that ships as a black box is a feature, not a
> capability**, and the difference is whether the next person can build on it without asking
> permission.

Rule 4 is the one that decides whether this works in two years. If the built-ins get a shortcut,
the public path is exercised only by outsiders, and it rots. Every predecessor seam that failed had
a privileged internal path.

## The architecture stack

| Axis | Pick | Why it fits | Cost to accept |
|---|---|---|---|
| **Structure** | **Microkernel / Plugin**, with the kernel itself organised as hexagonal rings | Third parties extend the product against a published contract — that is the definition of this pattern, and requirement 1 makes it the primary quality attribute rather than a nice-to-have | The contract becomes public API. Versioning, deprecation policy and plugin isolation become real, ongoing work rather than a one-off |
| **Domain overlay** | **None.** A maintained glossary, no DDD ceremony | The domain is real but thin: document, chunk, node, embedding, retrieval, citation. There are no bounded contexts fighting each other and no business rules worth aggregates | The vocabulary drifts unless the glossary is maintained deliberately. Cheap to pay, easy to forget |
| **Topology** | **Modular monolith, several distributions** — one repository shipping a kernel distribution plus first-party packs, and exactly one container: the database | A library with the CLI as its adapter. There is no service tier and none is planned. The only thing that cannot live in the process is durable storage. Splitting the wheel is what makes fitness function 1 a fact rather than a script — see *The kernel boundary* | Several distributions to version and release together, and skew between the kernel and a first-party pack becomes possible. That obligation lands on **G9**. The store obligation is unchanged: keep it behind a contract so the one container is swappable |
| **Data** | **Pipe-and-filter** | Both RAG paths genuinely are staged transforms, and **G2 settled that neither has a canonical order** — see the note below. A pipeline is whatever its author writes, and any particular order is *proved* by each stage's declarations rather than prescribed here. This is also what makes requirement 3 natural — you can only derive a pipeline if stages are addressable data | Stage boundary contracts must be stable and typed. Getting the payload model right is real design work, and it is grilling session G5 |
| **Overlay** | **Stability / resilience** at the model seam only | Remote model calls fail, rate-limit and time out. The predecessor learned this the hard way in RAPTOR summarisation | A retry, timeout and backoff surface that has to be configurable without leaking into every call site. **This is new work, not a lift** — see the note below |

> **Corrected from the reference study (2026-08-10) — the ingest order.** The Data row previously read
> *"extract to clean to chunk to enhance to embed to store."* **The reference chunks first and cleans
> second**, and it has two stages the plan's list omits. `IndexingPipeline.process`
> (`indexing/pipeline.py:82-150`), by the code's own numbering: **stage 0** separates `Document`s
> from `BaseNode`s (`:111`) because tables and figures are atomic and must bypass the parser
> entirely; **1** chunk (`:121`); **2** clean (`:124`); **3** attach `chunk_index` metadata (`:127`);
> **4** enhance (`:130`); **4.5** scrub transient metadata (`:135-136`); **5** store (`:142`). There
> is also **no separate embed stage** — embedding happens inside storage.
>
> This matters here because goals G2 and G5 will both be argued from this list and from the
> `base.yaml` example in `02` §3, and because the cleaning chain's *internal* stage order is the
> single highest-value salvage item in the reference (`indexing/cleaning/pipeline.py:30-51`, whose
> docstring ends *"IMPORTANT: Changing this order will break functionality."*).
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
> multi-MB base64 blobs from being serialised into PGVector JSONB"* (`indexing/pipeline.py:429-438`,
> `_TRANSIENT_METADATA_KEYS = ('_image_data_b64',)` at `:427`).
> (`reference/study/10-doc-corrections.md` A12; `reference/study/08-salvage.md` §T1.1.)

> **Corrected from the reference study (2026-08-10) — the resilience overlay.** The RAPTOR half of the
> Overlay row is confirmed exactly (nine constants at `indexing/parsers/raptor/a_prior_module.py:20-33`).
> The generalisation is not: **the reference has essentially no retry surface to lift.**
> `grep 'retry|retries|attempt|backoff' src/a_prior_project/evaluation/` → **0 occurrences**.
> `PromptExecutor`'s cascade has **no retries** — each tier is attempted once, so its worst case is
> three LLM calls, not three attempts. The only retry constants in 52,021 lines are RAPTOR's, and
> their own `TODO` at `:33` says *"map these constants to parser/database config fields once
> externalized."* Plan the retry/timeout/backoff surface as new work with one worked example
> donated, not as a layer to port. (`reference/study/10-doc-corrections.md` B12.)

**Structure, more precisely.** Microkernel and the ring family are usually alternatives, but here
they compose cleanly and the distinction matters: **microkernel describes how capability is added,
rings describe how the kernel itself is built.** The kernel is small and hexagonal — ports at its
edge, no infrastructure inside. The plugin contracts are simply the subset of those ports that are
published for extension. Rejecting vertical slices for the same reason as in the predecessor
review: the four axes are many-instances-of-one-shape, which is a plugin problem, and slicing would
duplicate the cross-cutting concerns this system actually has.

**What the reference actually validates here, and what it does not.** The paragraph above is a design
choice for Weft and stands. What it may **not** lean on is the prior review's claim that the reference's
hexagon is a proven pattern to copy — the deep study's verdict is *"layered code wearing hexagonal
vocabulary."*

> **Corrected from the reference study (2026-08-10):** the rebuild's premise that *"the kernel is small
> and hexagonal"* was resting on `architecture-review:22,111` (*"the hexagon … the healthiest part
> of the system and should be left alone"*). Measured:
>
> - **31 import statements naming `adapters.*` / `shared.*` across 18 of 259 files** — 20
>   `TYPE_CHECKING`-only, **11 executing at runtime**, of which 2 are module-level and unconditional
>   (`evaluation/datasets/open_rag_fast_track.py:13`, `open_rag_ultimate_track.py:14`) — **plus 11
>   `importlib.import_module('adapters.…')` runtime loads** (`core/llm/adapter.py:19`,
>   `factory.py:29`, `embeddings.py:19`, `callbacks.py:19`, `model_features.py:35`,
>   `_error_mapping.py:27`, and five `indexing/metadata_registry_*` / `sqlite_connection` shims).
> - **`src/a_prior_project/` does not import standalone.** It resolves `adapters.*` only because
>   `pyproject.toml` sets pytest `pythonpath = ["system", ".", "scripts"]` and pyright
>   `extraPaths = [… "system" …]`.
> - **52 of 55 port contracts have zero in-library implementation**; **14 port signatures carry a
>   LlamaIndex type**, 6 carry inner/outer-ring concrete types, 12 carry `dict[str, Any]`/`Any`.
>   **Only 11 of 55 contracts are clean.**
>
> So the reference's **rings are a layering** — real, largely respected at runtime, and worth copying.
> The **hexagon is not**, because its two load-bearing properties (no outward runtime dependency
> from the core; no vendor type in a port signature) are violated 11 and 14 times in the shipped
> tree. The design consequence that matters most for Weft's zero-container requirement:
> **the reference library cannot be exercised end to end without `system/`**, so "kernel + one
> container" has to be *demonstrated* in Phase 0, not assumed.
> (`reference/study/10-doc-corrections.md` A6; `reference/study/05-boundaries.md`.)

## The kernel boundary

**Settled in G1, 2026-08-10.** The rule, in one sentence: **the kernel is what is required to
express, load and run contracts it knows nothing about, plus the domain types those signatures
unavoidably name — and nothing in the kernel performs RAG work.** The falsifiable form, which is
what makes it usable in a review comment: *if you cannot describe the kernel without naming a
capability, it is too big.*

The rule is phrased against **capability, not size**, because size was never the property that
failed in the reference. `EngineContext` grew to 10 fields *and* was bypassed by 253 of 259 files — too
fat and irrelevant at once. A budget alone would have caught neither.

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
bookkeeping — it is what turns fitness function 1 from a script into a fact. The reference's boundary
checker could not fire partly because **`src/a_prior_project/` does not import standalone**: it resolves
`adapters.*` only because `pyproject.toml` sets pytest `pythonpath = ["system", ".", "scripts"]`. A
kernel that is its own wheel is checked by installing it alone and importing it, and Phase 0's exit
criterion — *a plugin in a separate installed package* — stops being a claim about directories.

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
receives is specified in `02` §1; where every reference item lands is `04` → *Kernel or pack*.

## Colour — the core is async, without exception

**Settled in G6, 2026-08-10.** Every contract method is `async def`. There is no sync protocol, no
dual registration, and **no bridge anywhere in the library** — `asyncio.run` appears exactly once in
the whole tree, at `weft-cli`'s entry point.

The positive case is ordinary: embeddings, model calls and store round-trips are IO-bound, and `03`
requires streaming. The negative case is the one that decided the shape. The reference has **exactly
one** `asyncio.run` call site in 259 files (`indexing/enhancers/vision_description.py:74`), and its
safety is guaranteed by a docstring plus a caller in `system/` — *"Safe only in
`asyncio.to_thread()` workers — never in FastAPI"* — so calling that method from a route raises
`RuntimeError: asyncio.run() cannot be called from a running event loop`. A sibling docstring records
*"Reset to `None` by the adapter before each `asyncio.run()` call"*: per-call mutable state
maintained by the caller, again by prose. The colour discipline itself held in the reference — 6 real
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
  `asyncio.run`. A facade would be a bridge, and a bridge is what the reference's incident was made of.
- **Streaming does not fork the contracts.** Tokens go to a `TokenSink` resolved as a service, and
  the generator still returns a decided `Outcome[Answer]` — see `02` §1. The reference's shape is the one
  being refused: **10 `@register_strategy` and 10 `@register_streaming_strategy` sites, symmetry
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

The contrast with the predecessor is the point: it shipped a twenty-four service Compose topology,
and none of those services were the product. They were the cost of having decided, early, that the
product was a deployment rather than a library. Weft keeps that decision unmade.

> **Unverified:** the service count and the characterisation concern `system/docker-compose.yml`,
> which the reference study did not examine. See `reference/study/09-open-questions.md` (U3). What *is*
> confirmed from inside the library points the same way: the library reaches outward into its own
> deployment layer 11 times at runtime, and 52 of 55 port contracts have no in-library
> implementation.

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
| Event bus between components | An add-on genuinely needs to observe events it cannot reach through an explicit extension point. Candidate for G7 — do not build it speculatively |
| Background job broker | The first user needs indexing to survive process restart, or a single index run exceeds a session |
| Any service tier at all — API, worker, gateway | Someone outside the process needs to call this. Until then the library plus one database container is the whole system, and every service added before that point is cost without a user *(the "cost without a user" claim inherits the twenty-four-service figure above and is **unverified** — see `reference/study/09-open-questions.md`, U3/U10)* |
| CQRS | Never, at library level. It was a deployment-shape decision in the predecessor and belongs there if anywhere |
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
- **Lift** — what comes from the reference, per `04`.
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
  *Kernel or pack*. **Not** `scripts/check_hex_boundary.py`, which the study showed does not fire; see
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
> inside that cascade, and the `LLMError` taxonomy. `reference/study/08-salvage.md` §T1.4, §T1.5, §T1.7,
> §T2.8.)*

### Phase 1 — Pipelines as data

The pipeline model, the resolver, and the derivation operators.

- **Gate:** `05` → **G2** derivation semantics — **settled 2026-08-16.**
- **Read:** `02` §3 in full — the operator table and its edge rules, `intact`/`destroys`,
  applicability, slots, vars, and the KeyBERT case.
- **Lift:** `04` category B — **not the reference's stage order, which G2 declined to adopt in either
  direction**, but the two things underneath it: the reason stage 4.5 exists (transient scrubbing,
  which lands at the seam rather than as a stage) and the reason stage 0 exists (atomic nodes must
  never be re-chunked, which lands as applicability). Category A cleaning processors, *with* their
  ordering rationale from `indexing/cleaning/pipeline.py:30-51` — and with the 243-word Polish
  fused-word exception set (`indexing/cleaning/processors/dictionary_spacing.py:31`), which
  `reference/study/08-salvage.md` ranks the second most valuable thing in the reference and which `04` does not
  currently name.
- **Exit:** driving use case A works — a `specific` pipeline derived from `base` with KeyBERT
  inserted after chunking, expressed as configuration, with no change to core and no copy of the
  parent. **Also: fitness function 11 is wired and green**, both clauses.

### Phase 2 — Retrieval and generation

Retrieval strategies, fusion, reranking, the router, citations. The router keeps the predecessor's
design: an LLM scores dimensions, a deterministic ladder decides.

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
  from an enum or an if-chain. **Also: fitness function 9(c) is wired and green** — every contract
  Phase 2 publishes has an out-of-tree example pack implementing it.

### Phase 3 — The CLI

The full driving adapter: REPL, streaming, slash commands, plugin-contributed commands, permissions.

- **Gate:** `05` → **G8** is the REPL agentic. If the answer is anything but "shell", stop and hand
  off to the `agentic-patterns` skill before writing the loop — retrofitting one later is the
  expensive order.
- **Read:** `03` in full.
- **Lift:** nothing. The reference's CLI reached 1,080 lines in one command module (`indexing/indexer.py`,
  exact) and is the shape to avoid. Two specifics worth carrying as rules rather than code: it runs
  `load_dotenv(override=True)` **at module import time** (`:52`), so importing the CLI mutates the
  process environment — **a driving adapter may not mutate process state at import** — and the reference
  ships **three** separate entry points (`rag-index`, `rag-chat`, `rag-query`,
  `pyproject.toml:141-144`), not one.
- **Exit:** a plugin ships a command that appears in `weft --help` and in REPL completion without
  core knowing it exists.

### Phase 4 — Evaluation and observability

Metrics as plugins, spans on every stage, the evaluation harness as a decorator over a pipeline.

- **Gate:** none.
- **Read:** `02` §1 for the `Metric` contract.
- **Lift:** `04` category A — all 21 metric implementations, as the first metric pack, **with the
  four defects listed in `04` fixed at the door**. Note that RAGAS and ROUGE are not dependencies of
  the reference; those classes are hand-rolled, so they are original code to lift rather than
  integrations to re-wire.
- **Exit:** running the same corpus through two derived pipelines produces a comparison the tool
  generates itself, **and both runs are persisted so they can be diffed after the fact**. The
  predecessor could not do this at all. **Also: fitness function 8(c) is wired and green** — every
  persisted run names the distribution set that was active, without which a comparison across two
  runs cannot be trusted to be comparing pipelines rather than environments.

> **Corrected from the reference study (2026-08-10):** the exit criterion said the predecessor's
> comparison helper *"was a display function and the sweep loop was the operator's"*. Correct, and
> understated. `compare_evaluation_results` (`evaluation/helpers.py:172-220`) does return `None` —
> but **the entire module is dead**: all four public functions (`:15`, `:59`, `:118`, `:172`) have
> zero references in `src/a_prior_project/` and zero in `tests/`. `grep 'ab_test|sweep|grid_search|compare_strateg'`
> → 0. And **nothing in 6,632 lines of `evaluation/` writes a result anywhere** — there is no
> persistence, so two runs cannot be diffed after the fact even by hand. There is also no retry, no
> concurrency, and **zero OTEL spans** in `evaluation/`. Hence the added clause: *an evaluation-first
> product that cannot diff two runs after the fact is not evaluation-first*, and a comparison the
> tool generates itself implies stored runs. (`reference/study/10-doc-corrections.md` C5;
> `reference/study/09-open-questions.md` C-10 asks what a persisted run must contain.)

### Phase 5 — The independence test

The graph add-on, per driving use case B, built as an external package.

- **Gate:** `05` → **G7** event bus or explicit extension points, and **G9** contract versioning,
  which the first external pack makes real.
- **Read:** `02` §4 in full.
- **Lift:** nothing. This phase exists to test the extension model, so borrowing shortcuts from the
  reference would defeat it.
- **Exit:** it is written by someone who has not touched the core, and they never need to. If they
  file an issue asking for a core change to make their pack work, that is a Phase 5 failure and a
  design finding, not a feature request.

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
- **Lift:** nothing, and one scar recorded as a rule. The reference was never installable: it cannot be
  installed standalone at all — `core/config/provider_catalog.py:16` reaches a `system/` path through
  `Path(__file__).parents[4]`, which breaks the moment the package is a wheel, and two evaluation
  modules carry unguarded top-level runtime imports of `adapters.*` so
  `import a_prior_project.evaluation.datasets.open_rag_fast_track` hard-fails unless `system/` is on
  `sys.path` (`evaluation/datasets/open_rag_fast_track.py:13`, `open_rag_ultimate_track.py:14`;
  `reference/study/05-boundaries.md` §4, `reference/study/09-open-questions.md` §C-11). **The rule: a
  distribution is proven installable by installing it, never by reading it** — which is fitness
  function 1's primary half applied to every distribution rather than only to the kernel.
- **Exit:** on a machine that has never seen this repository, installing **the release unit G10 names**
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
directory. The reference is the proof that this gap is real and not pedantic — its library resolved its own
imports only because `pyproject.toml` put `system/` on the pytest path (*The kernel boundary* above),
and the same mechanism hid an uninstallable package for the life of the project.

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

---

**If a gate reopens mid-phase.** Discovering that a closed decision was wrong is information, not
failure — but it is a stop, not a patch. Re-run that session, then re-check the phases downstream
of it, because the ordering table in `05` exists precisely because these decisions cascade.

## Fitness functions

Architecture that is not enforced decays. The predecessor proves both halves of that sentence, and
the study measured them: **every concern the machinery did automatically held perfectly; every
concern an author had to remember decayed.** Spans applied at registration held on all ten
strategies; spans written by hand decayed to 58 `traced_operation` sites, 5 with no `span_kind`, 9
hand-rolled bypasses, 38 of 54 names off-convention, and an entire untraced ingest stage.
`get_logger` held — **0 `print()` in 259 files**. The catalog file the reference's own standard requires
does not exist. **The generalisation to adopt: move every cross-cutting concern to the registration
seam.** (`reference/study/10-doc-corrections.md` E11.)

All checks run in CI, before tests.

0. **The gate must be in the gate.** Every architecture check runs inside the composite task the
   docs name as canonical, and a test asserts that membership. This function exists because of the
   reference: `hex-boundary` is **not** in `poe ci-checks` — the composite the root `CLAUDE.md` calls the
   canonical full gate resolves to `quality`, which omits it, and `.pre-commit-config.yaml` omits it
   too. **A fitness function that is not wired into the canonical CI task is not a fitness
   function.** The pattern to reimplement is the reference's genuinely good one:
   `tests/unit/architecture/test_allowlist_empty.py:8`, an 18-line test that pins a named waiver
   constant to empty, fails with a message stating the waiver policy, and is itself unit-tested.
   That is a ratchet rather than a snapshot, which is the property that makes it work.
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
   installed distributions declared. A static check would have passed the reference, whose
   `import a_prior_project.evaluation` registers **17 of 23** evaluators and whose enhancer count is 3 or
   4 depending on which function you call. The reference also contains the single most literal instance
   of the defect this function exists to catch: `retrieval/registry.py:649-668` re-wraps and
   re-assigns the three indexing builders *after* the decorator already registered them, to add span
   wrapping — *"INDEXING_BUILDERS is updated in-place so strategy dispatch also uses spans"* — so a
   plugin registering through the public decorator would silently not get the observability the
   built-ins get. Note this is the same computation `weft plugins doctor` (`03`) has to perform, so
   the fitness function and the CLI command are one piece of code.
3. **Kernel budget — 3,500 lines, review at 2,800.** The kernel fails the build above a stated size.
   A number, argued once, then enforced. The point is not the number; it is that growth becomes a
   conversation. **Settled in G1, 2026-08-10:**

   - **What is counted:** non-blank, non-comment, **non-docstring** Python lines in the `weft-kernel`
     distribution, tests excluded. Docstrings are excluded deliberately, so the budget can never
     become an argument against documenting the kernel.
   - **The number: 3,500, failing the build. 2,800 (80%) is a review trigger** — crossing it does not
     fail anything, it puts kernel growth on the agenda before the ceiling is a crisis.
   - **The reason, because a number without one gets waived:** the reference's `core/` measures 13,969
     non-blank lines across 87 files (`engine/` 7,038 · `ports/` 2,191 · `prompt/` 1,628 · `models/`
     905 · `llm/` 897 · `config/` 736 · `observability/` 299 · top level 247 · `utils/` 28). Under the
     G1 boundary, `engine/`, `prompt/` and `llm/` are packs. What remains kernel-analogous is
     `observability` 299 + `config` 736 + `models` 905 + a thin slice of `ports` (~250 for three
     contract *mechanisms* against the reference's 55 contracts, 52 of which have no in-library
     implementation) + context and the registry factory (~300) ≈ **2,500** — plus the discovery,
     pipeline and derivation machinery the reference has **none** of, 600–900. The honest estimate is
     **≈ 3,300**, so 3,500 leaves enough headroom to be legitimate and not enough to be ignored.
   - **The revision rule, which is the part that actually does the work:** the constant may be
     changed **only by a dated entry in the decision log**, never in the same pull request that grew
     the kernel. This is the ratchet property that makes the reference's `test_allowlist_empty.py` its
     best fitness function — the waiver is a deliberate, visible act rather than a silent edit.
   - **Known limitation, recorded rather than solved:** lines are a proxy for published surface, and
     a kernel can sit at 3,400 lines while its API doubles. The surface governor today is `01`'s cap
     of three published contracts in Phase 0 and the G1 rule that the kernel names no capability. If
     that proves insufficient, the second number to add is a public-symbol cap.
4. **No closed enumeration of registry keys — anywhere a name is decided.** Two clauses. (a) No enum
   shadows a registry. (b) **No literal enumeration of registry keys may appear in a dispatch, a
   validator or a routing decision**, expressed as a runtime property —
   `set(valid_names) == set(registry.keys())` asserted for every selection surface — rather than as
   a grep.
5. **Every declared capability resolves.** Every capability a plugin declares must resolve to a live
   implementation at discovery time, or the plugin must declare it unavailable and say why.
6. **Contracts are versioned.** Every published contract carries a version, and a check fails on a
   changed contract whose version did not move.
7. **Colour integrity.** Two clauses, from G6, and **no tuning constants in either.**
   (a) **One bridge.** `asyncio.run` appears exactly once in the tree, at `weft-cli`'s entry point,
   asserted by path — so a second one fails the build rather than being noticed in review. This
   exists because the reference's single bridge was safe only by docstring.
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
   clause whose two sides came from one computation would be the reference's `test_keys_parity` defect,
   which cannot fail at all (`reference/study/08-salvage.md:777-782`). **How it fails:** publish a
   contract and ship no example for it — which is the everyday case this clause exists to catch. It
   carries a **ratchet** in the style of item 0: a named constant
   `CONTRACTS_WITHOUT_AN_EXAMPLE_PACK`, pinned empty, so an exemption is a visible entry in a diff
   rather than a silent edit, changeable only by a dated decision-log entry. *Active from Phase 2*,
   the first phase that publishes a contract Phase 0 did not, and its activation is an exit
   criterion of that phase.

   **Why it exists.** Requirement 1 is the thesis of the project and it is the only one of the six
   that has never been enforced by anything. The reference is why that matters: adding one storage
   backend meant editing **11 files inside the library** plus at least 3 in `system/`
   (`reference/study/01-extension-axes.md:3260-3263`), against **"None at all — 0 registered names"**
   and 17 dispatch sites of which 0 are registry lookups (`:25`). Nothing in the reference's CI measured
   that, and nothing could have — its own boundary checker was not in its canonical gate and exited
   0 on a tree with 11 violations (fitness function 0). Weft's gap today is narrower and the same
   shape: the requirement is applied by a human running the `weft-qualities` lens, and a lens is not
   a ratchet.

   **What it deliberately does not catch, and why there is no fourth clause.**

   - **Reachability.** A plugin can register from outside, cost zero core edits, and still never
     execute — the reference's sharpest finding, where a third-party strategy registers, is listed, is
     described to the LLM in the routing prompt, and hits three walls
     (`reference/study/02-discovery-and-config.md:226-234`). That is **fitness function 4(b)**'s job.
     Function 9 asserts that extension happens from outside; 4(b) asserts the extension can *run*.
     Reading 9 as covering both is how the reference's seam would pass a green build.
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
    the reference's `test_keys_parity` shape (`reference/study/08-salvage.md:777-782`). Here a hand-maintained
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
    text that rots silently while every unit test passes, which is exactly how the reference arrived at a
    strategy that registers, is listed, is described to the LLM, and can never run
    (`reference/study/02-discovery-and-config.md:226-234`). **How it fails:** rename a plugin and leave
    `base.yaml` naming the old one — caught in the gate rather than on a user's first index run.

> **Corrected from the reference study (2026-08-10) — fitness function 1, and the preamble.** This
> section previously opened *"the predecessor's AST boundary checker is the single best thing in
> it"* and specified FF1 as *"lifted almost verbatim from the reference."* It is not the best thing in
> the reference and it must not be lifted verbatim, because **it does not fire.**
> `scripts/check_hex_boundary.py` (316 lines, 5 rules) prints *"Hex boundary check passed."* and
> exits 0 on the current tree — a tree that carries **11 runtime imports of `system/`-owned
> namespaces**. Why it cannot fire:
>
> 1. `INFRA_SDK_PREFIXES` = `litellm` / `psycopg2` / `sqlalchemy` / `redis`, which match **0 imports
>    in the entire library**. The rule is dead code.
> 2. `llama_index` is **not** on the list, and there are **150** `llama_index` imports, 37 inside
>    `core/`.
> 3. All `TYPE_CHECKING` blocks are skipped entirely (`check_hex_boundary.py:80-90`).
> 4. The deployment-namespace rule fires only on `importlib.import_module` **and** only under
>    `src/a_prior_project/core/` (`:119-121`), so a plain `from adapters.storage… import` anywhere in
>    `indexing/`, `retrieval/`, `generation/` or `evaluation/` matches no rule at all.
> 5. **It is not in the canonical CI composite** — hence fitness function 0 above.
>
> A four-name denylist ages into a no-op the moment the dependency set changes, and this one already
> has. Hence FF1 as reworded: derive the invariant, do not enumerate the villains. There is a second
> lesson in it that Weft should take seriously — the reference's gate **shaped the workaround rather
> than removing the coupling**: `test_core_llm_modules_do_not_use_top_level_adapters_imports` is
> precisely why eleven modules reach `system/` through `importlib.import_module('adapters.…')` under
> a module `__getattr__` instead of a plain import. A lazy dynamic import of a literal module path is
> the exact evasion, and FF1 must police it.
> (`reference/study/10-doc-corrections.md` A5, A11; `reference/study/08-salvage.md` §T1.17, §T3.14;
> `reference/study/05-boundaries.md` §4.)
>
> **Unverified:** which composite the CI workflow actually invokes requires `.github/workflows/`,
> outside the study's readable scope. The `poe`/pre-commit configuration is confirmed. See
> `reference/study/09-open-questions.md` §A.4.

> **Corrected from the reference study (2026-08-10) — fitness functions 4 and 5.**
>
> **FF4** was *"a grep-level check that no enum shadows a registry."* The mechanism is right and the
> check is not sufficient: it catches `StrategyName` vs `STRATEGY_REGISTRY` and misses the two walls
> that actually made the reference's strategy seam unusable. (i) `RetrievalStrategyType` (3 members,
> `retrieval/types.py:24-26`) is the **key type** of `RETRIEVAL_BUILDERS` (`retrieval/registry.py:147`)
> — there is no shadowing to grep for; the lock is structural, and a plugin cannot construct a
> fourth member at all. (ii) `AdaptiveRouter._select_strategy_from_scores` (`core/engine/router.py:287-350`)
> is a hard-coded 10-branch `if/elif` assigning literal `StrategyName.*` members with no plugin
> branch — an enum check sees nothing. (iii) `RoutingResponse.validate_strategy`
> (`core/engine/types.py:476-495`) hard-rejects any value not in the enum. **A third-party strategy
> in the reference registers successfully, is listed by `get_all_strategy_metadata()`, is described to
> the LLM in the routing prompt (`router.py:381-383`) — and can never be executed.** That is the
> defect FF4 has to prevent, and only clause (b) prevents it. A runtime check is also the only thing
> that would have caught the reference's evaluator gap (6 of 23 unregistered).
>
> **FF5** was *"no capability's metadata may appear in two maps — the file-format drift bug,
> encoded."* It encodes a bug **that never occurred**: the two format lists are identical (17 = 17,
> empty symmetric difference). The bug that *did* occur is a capability declared unconditionally
> whose implementation is inserted conditionally on an optional dependency (`factory.py:119-122`) —
> the declaration is right and the *resolution* is empty. A source-text comparison would pass a tree
> where `.ppt` is declared and unresolvable. Checking the **resolved** map covers both the drift bug
> and the optional-dependency bug in one check, and it is exactly what `weft plugins doctor`
> (`03`) already has to print. (`reference/study/10-doc-corrections.md` B10, B11, A1, A10.)

## Risks worth stating now

- **Over-generalising the kernel.** A microkernel's failure mode is a core so abstract nothing can
  be done without three indirections. Mitigation: the kernel budget, and the rule that no
  abstraction enters the kernel before two real plugins need it.
- **Contract churn.** Publishing contracts early means changing them hurts. Mitigation: Phase 0
  publishes exactly three, and the rest stay internal until a second implementation exists.
- **Plugin trust.** Entry points execute third-party code on discovery. This is a real security
  decision, deliberately unresolved here — grilling session G3.
- **Losing the reference's hard-won detail.** The cleaning order, the retry constants, the Polish
  reranker selection, the multilingual citation extraction: none are obvious, all were learned. All
  four are confirmed by the study to the line. The list is also **incomplete**, and deliberately not
  extended here — an enumeration in a risk paragraph goes stale. Mitigation:
  `04-reference-inventory.md` names the lifts, and **`reference/study/08-salvage.md` is the authoritative
  three-tier inventory** with each item's source, its dependencies, what has to change to lift it,
  and its traps. Its "if you only lift ten things" table is the shortest useful version.
- **Losing the reference's good habits.** Less obvious than losing its code, and just as expensive. The
  study confirms: **0 `print()`** in 259 files; **0 `FIXME`/`XXX`/`HACK`/`WORKAROUND`** markers; **no
  bare `# type: ignore`** — all 138 name their rule; the env-var discipline holding with 4 annotated
  exceptions; per-file `T201` ignores scoped exactly to `src/a_prior_project/output/*`. These are worth
  carrying as explicitly as the algorithms.
