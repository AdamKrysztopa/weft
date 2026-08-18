# 02 — The extension model

This is the load-bearing document. If the ideas here are right the project succeeds; the rest is
execution.

Three concepts, deliberately separate, because conflating them is what broke the predecessor:

| Concept | What it is | Unit of |
|---|---|---|
| **Contract** | A published Protocol a plugin satisfies. `Extractor`, `Chunker`, `Retriever`, `Store` | **Extension** |
| **Pack** | An installable Python distribution that registers one or more plugins | **Distribution** |
| **Pipeline** | Data describing an ordered set of stages and their configuration | **Composition** |

One pack may register a dozen plugins across five contracts, and a pipeline may reference plugins
from ten packs. Keeping these three axes independent is what lets the graph add-on be a single
install while still participating in indexing, retrieval and the CLI.

---

## 1. Contracts

A contract is narrow by construction. The predecessor's `BaseExtractor` is the model to copy: one
method, domain types on both sides. Its interface was never the problem — only its dispatch.

> **Confirmed and extended by the reference study (2026-08-10).** `indexing/parsing/extractors/base.py`
> is 51 lines, one `@abstractmethod extract(file, mode) -> ExtractionResult` (`:18-38`) plus one
> concrete helper, with 14 subclasses; the `ExtractionResult` envelope is a Pydantic model with five
> `mode='before'` type-guards. Two additions worth having, both from the same repository:
>
> - **The counter-example is next door, and it makes the rule teachable.** `PDFParserStrategy`
>   (`retrieval/parsers.py:22`) is also one abstract method and is also called a strategy — but it
>   returns a LlamaIndex `Document` straight out of the port, which the reference's own `src/CLAUDE.md`
>   forbids. It has exactly one implementation, no library caller, and a dead 127-line file behind
>   it. Same shape, opposite verdict: the difference is entirely the type at the boundary.
> - **The other half of the good design is the chain executor.** `MultiBackendReader._try_extractors`
>   (`indexing/parsing/multi_reader.py:164-222`) takes a `list[BaseExtractor]` and knows nothing
>   about its contents — the reference already had the fallback-chain executor that §3's `fallback: [...]`
>   syntax needs. Its semantics decision is *"non-empty `texts` means success"*, which is the right
>   call for scanned-vs-digital PDFs (pdfplumber succeeds on a scanned page and returns nothing, so
>   the chain must fall through to OCR), and errors accumulate and are reported together rather than
>   last-one-wins. **Two traps come with it.** Its `fail_silently=True` path returns an empty
>   `ExtractionResult` with `metadata={'error': …}` that is *indistinguishable downstream from a
>   successfully-parsed empty document* — kill that channel and return an explicit outcome type. And
>   a backend that legitimately extracts zero text cannot say so, so **G2/G5 must answer: can a
>   backend report definitive success-with-no-content and stop the chain?** See
>   `reference/study/09-open-questions.md`. (`reference/study/10-doc-corrections.md` C4; `reference/study/08-salvage.md`
>   §T1.15, §T2.3.)

Phase 0 publishes exactly three contracts. Everything else stays internal until a second
implementation forces it, because a published contract you regret is expensive and an unpublished
one is free.

Rules that apply to every contract:

- **Domain types at the boundary.** No vendor SDK types, no framework objects. The predecessor
  leaked LlamaIndex `BaseNode` into a port and its own ADR flagged it as debt.
- **Widening a signature to `Any` is not a fix.** A parameter typed `Any` so a vendor object
  satisfies it structurally is the same coupling with the type information deleted.
- **Narrow over convenient.** When a caller needs only half an interface, that is two contracts.
  Vision and text models were correctly split in the reference and that judgement holds.
- **Versioned.** Every contract carries a version, enforced by fitness function 6.
- **A capability declares its own metadata.** An extractor states which extensions and MIME types
  it handles. This is not decoration — it is the fix for the accept-then-fail bug, because there is
  then no second list to fall out of step with **and no way to declare a format whose implementation
  is not there** (fitness function 5).
- **A contract's registration API carries a typed configuration model, or the extension point is
  decorative.** See the note on `with:` in §3.

> **Corrected from the reference study (2026-08-10) — the boundary leak is far larger than one type in
> one port.** **14 port signatures carry a LlamaIndex type**, across 4 of 17 port modules:
> `core/ports/enhancer.py:36` (`BaseNode` in *and* out), `retrieval.py:32,52,126` (`NodeWithScore`),
> `storage.py:34,68,82` (`BaseNode`), `table.py:81,799,816` (`NodeWithScore`). **`core/ports/table.py:19`
> is a module-level, unguarded, runtime `llama_index` import into the innermost ring.** A further 6
> signatures carry inner- or outer-ring concrete types and 12 carry `dict[str, Any]`/`Any`. **Only
> 11 of 55 contracts are clean.**
>
> The `Any`-widening rule above comes from the most honest artefact in the reference,
> `core/ports/llm.py:42`, which explains that `LLMProtocol`'s parameters are `Any` *"to remain
> compatible with the LlamaIndex concrete types without importing them here"* — i.e. the boundary
> was widened until it could not see the vendor type. That is not domain typing; it is the same leak
> with the evidence removed.
>
> The whole debt is ticketed as **RAG-314**, 23 `TODO(RAG-314)` lines — a backlog item not to
> inherit. (`reference/study/10-doc-corrections.md` C3; `reference/study/05-boundaries.md` §1.4, §3.)

> **Corrected in G5 (2026-08-10) — RAG-314 is not the node specification.** This note previously
> read *"treat RAG-314 as the specification of 'define a domain node type' … those 23 sites enumerate
> exactly which fields a domain model has to carry."* All 23 were read. Six are `dict[str, Any]`
> config fields in `core/ports/metadata.py`, five more in `storage.py`, six are `Any` parameters in
> `llm.py`, three in `evaluation.py`, one each in `observation.py` and `core/engine/types.py` — and
> **exactly one** concerns a node value object (`core/ports/retrieval.py:14`, *"Replace with a domain
> value-object once defined"*). RAG-314 is a *typed-it-as-`Any`-everywhere* ticket, and it specifies
> nothing about a node's fields.
>
> **The empirical specification is what the reference actually put in `node.metadata`** — one untyped
> dict, 40+ distinct keys, tabulated in `04` → *The node metadata surface*. That table is what G5
> designed the payload model against, and it is better evidence than the ticket ever was: it shows
> which data is universal (identity, lineage, content), which is one pack's private business (the
> seven `raptor_*` keys), and which had no business being on a node at all (`tenant_id`).

### Who publishes a contract

**Settled in G1.** The kernel publishes the contract *mechanism* — registration, versioning, the
`Outcome` type, the domain node type — and **no capability contract of its own**. `Extractor`,
`Chunker` and `Store`, the three Phase 0 publishes, ship from the first-party packs that own them;
so do `Retriever`, `LLM` and everything after. A pack depends on the pack that publishes the
contract it implements, exactly as it would on any third-party protocol.

The risk accepted is rival contracts — nothing structurally stops a second pack publishing its own
`Retriever`. The mitigation is ordering, not enforcement: the first-party contract ships first and
every built-in satisfies it. The reasoning for taking that risk is in `01` → *The kernel boundary*.

### What a plugin receives

Two seams, deliberately, because configuration and ambient identity have different lifetimes.
Conflating them is what fissioned the reference's one passport into three overlapping bags — 10 fields
on `EngineContext`, 11 on `StrategyContext`, 14 on `EngineMetadata`, with `tenant_id` on the object
plugins never got.

```python
class Stage[In, Out](Protocol):
    lifetime: ClassVar[Lifetime] = Lifetime.RUN
    requires: ClassVar[tuple[type[ExtModel], ...]] = ()
    provides: ClassVar[tuple[type[ExtModel], ...]] = ()

    def __init__(self, config: MyConfig) -> None: ...
    async def run(self, payload: In, ctx: Context) -> Outcome[Out]: ...
```

- **Configuration arrives at construction.** The kernel validates the stage's `with:` block against
  the Pydantic model the plugin declares, *before* instantiation, and fails naming the stage and the
  field. A contract whose registration API carries no typed configuration model is decorative.
- **The passport arrives at the call, and there is exactly one.** `Context` carries `tenant_id`, run
  and trace ids, cancellation, locale, and `require()`. **The admission rule for new fields:** a
  field is admitted only if it is needed by *every* plugin regardless of contract **and** is
  meaningless to resolve as a service. Tuning knobs fail the second test, which is precisely how
  `EngineMetadata` acquired seven of them.
- **Services are resolved by contract.** `ctx.require(LLM)` returns a typed handle or raises naming
  the pack that provides it. This is what makes `llm: Any` — the reference's *"typed `Any` for
  flexibility in tests"* at `core/engine/context.py:51` — structurally impossible: the handle is
  typed by the contract you asked for. It is a late-binding point, and the distinction from the
  reference's service locator is real: that one resolved **literal module paths** at import time,
  untyped and unregistered, reaching outward past its own boundary; this resolves exactly what
  discovery registered, keyed by a published contract.
- **Every contract returns an `Outcome`**, never a bare value: `Produced` / `NothingToProduce` /
  `Failed`. This is what lets the kernel own a fallback combinator without knowing what any stage
  does — it matches on the outcome and never inspects payload content. It also kills the reference's
  worst extraction trap by construction: `_try_extractors`' `fail_silently` path returned an empty
  `ExtractionResult` *indistinguishable downstream from a successfully-parsed empty document*, and a
  backend that legitimately extracted nothing had no way to say so. It now does, and it stops the
  chain. **This constrains G5** — the payload envelope is still G5's to design, but its result type
  is settled.
- **A plugin declares its own lifetime.** `Lifetime.RUN` by default: a fresh instance per pipeline
  run, no thread-safety obligation on the author. `Lifetime.PROCESS` is opt-in and accepts the
  obligation — the instance must be reusable and safe under concurrent `run()`. The kernel's cache
  is keyed `(tenant_id, contract, name, config_hash)`; the tenant is in the key or multi-tenancy is
  broken on day one. The reference's equivalent is the one piece of real tenancy machinery it has
  (`RegistryFactory._llm_cache`, keyed `f'{tenant_id}:{config.model}'`, one of only four locks in
  52,021 lines) — and what not to copy is that it is cleared only by a manual `clear_cache()`.
- **Errors have a root and an origin.** Packs raise subclasses of `WeftError`, which carries a
  `transient` marker so a pack can say what is worth retrying. Anything escaping a plugin seam is
  wrapped with pack, contract, plugin and stage, `__cause__` preserved so no traceback is hidden.
  The kernel raises its own: unknown plugin name *listing the valid options*, unresolved contract,
  invalid configuration, contract version mismatch. There is **no kernel retry engine** — resilience
  stays at the model seam per `01`.
- **The author supplies no observability.** Span name and `span_kind` are derived at the registration
  seam from contract and plugin name. The reference's hand-written spans decayed to 38 of 54 names
  off-convention and 5 with no kind, because both were an author's job; here there is nothing to
  forget and nothing to get wrong.
- **Messages are looked up, never formatted in place.** `ctx.t('graph.node_dropped', n=3)` resolves
  against the merged catalogue, namespaced by pack.
- **Every contract method is `async def`** (G6). There is no sync protocol and no declared colour: a
  CPU-bound stage is still `async def` and offloads its own blocking work. Fitness function 7 fails
  the build on any blocking *call* made while a stage runs — file IO, sockets, `time.sleep`, a
  synchronous driver — which is the realistic mistake; a stage that hogs the loop with pure
  computation is visible in its span rather than caught by a gate. No plugin ever writes
  `asyncio.run`: the library contains exactly one, in `weft-cli`.
- **Cancellation is native, and must not be swallowed.** `ctx` carries cancellation, and under an
  async core that is task cancellation. A stage must let `CancelledError` propagate; the way it gets
  swallowed by accident is `except Exception` around an `await`, which is already forbidden by the
  catch-specific-exceptions rule and is worth stating twice. Cleanup belongs in `finally` or a
  context manager, not in a handler that returns `Failed`.
- **Streaming is a service, not a second contract.** A generator resolves `ctx.require(TokenSink)`
  and emits tokens as it produces them, then returns a decided `Outcome[Answer]`; the CLI provides a
  printing sink and a batch run provides a no-op. One generator contract, and `Outcome` keeps the
  meaning §1 gives it — it is decided when the stage returns, not when a stream is drained. The shape
  being refused is the reference's: **10 `@register_strategy` and 10 `@register_streaming_strategy`
  sites, kept symmetric by hand with no test asserting it.** A sink fails the passport's admission
  rule — only generators need it — which is exactly why it is a service and not a field.

### The payload model

**Settled in G5.** What flows between stages, and what a pack may attach to it.

```python
class Node(frozen):
    id: NodeId  # digest — see Identity below
    lineage: Lineage  # parents: tuple[NodeId, ...] (never empty)
    # sources: frozenset[SourceId] — derived, never authored
    content: str
    media_type: MediaType
    embedding: Vector | None
    ext: ExtMap  # namespaced, typed by declaration
```

**The core is narrow by an admission rule**, the same shape as the passport's: a field is admitted
only if **every store and every retrieval strategy must understand it to function**. That admits the
six above and excludes everything else. The reference's counter-example is the specification here — one
untyped `metadata` dict that reached **40+ distinct keys**, enumerated in `04` → *The node metadata
surface*. Page numbers, parser names, captions, entities and the seven `raptor_*` keys are all
namespaced extension data under this rule; `tenant_id`, which the reference also kept there, is on the
passport.

**Extension data is declared, not stuffed.** A pack declares a model that owns a namespace, and the
kernel validates on write:

```python
class GraphData(ExtModel):
    __namespace__ = 'weft-graph'          # the distribution name — collision-free by construction
    entities: list[Entity]
    relations: list[Relation]

node = node.with_ext(GraphData(entities=…, relations=…))    # validated on write
data = node.ext_as(GraphData)                               # typed, or None if absent
```

Namespace strings never appear in plugin code, so `metadata['entites']` — silently `None` forever —
has no equivalent. RAPTOR's seven loose keys become one `RaptorTree` model no other pack can read
or corrupt by accident.

**Transience is a property of the declaration.** `__transient__ = True` on an ext model means the
kernel strips that namespace before any `Store` sees the node. The reference needed a pipeline stage for
this — stage 4.5, guarding against *"multi-MB base64 blobs serialised into PGVector JSONB"* when the
vision enhancer is absent or fails. A stage is a legal target for `remove:` in a derived pipeline; a
declaration is not, and it holds whether or not the producing stage ever ran.

**Stages declare what they read and write.** `requires` and `provides` name ext models, and the
resolver checks the chain at load: a stage requiring `ChunkData` that no upstream stage produces
fails with the stage, the namespace and the providing pack named — the same standard §3 already sets
for a missing plugin. **Reading an undeclared namespace raises**, always, so the declarations stay
load-bearing rather than decaying into documentation the way the reference's span-kind convention did.
At run time `ext_as` returning `None` is legitimate — the upstream stage may have produced nothing
for this node — and the stage answers with `NothingToProduce` or `Failed`.

**Nodes are frozen, and lineage cannot be omitted.** There are three ways to make one:

```python
child = parent.derive(content=chunk_text)  # lineage carried
summary = Node.combine(members, content=text)  # parents explicit, never empty
probe = Node.synthetic(reason="…")  # explicit, greppable, doctor-reportable
```

`Lineage.sources` is **computed by the kernel** as the union of the parents' sources, so a level-3
RAPTOR summary automatically carries the source ids of every document beneath it. This is the fix
for the reference's worst data bug: summary nodes built with `relationships={}` carried no `ref_doc_id`,
and `_handle_deleted_files` deletes only by `doc_id`, so **one class of node was unreachable by every
deletion path — delete a document and its summaries describe it forever**. The justification given
was *"global summary: no single source document"*, which conflates *no single source* with *no
parents*: RAPTOR had just clustered the twelve nodes it was summarising. Under `combine` that
information cannot be discarded, and under derived `sources` it cannot be forgotten.

**Deleting a source cascades.** Every node whose derived `sources` contain the deleted document is
deleted with it, and the store reports the removed set so a rebuild knows what to re-derive. This is
deliberately the aggressive reading: a node kept but hidden from retrieval looks like deletion to a
user and is not deletion at all to a regulator. The honest cost is that the RAPTOR root summary
descends from every document, so removing any one document removes the top of the tree. The
mechanism — transactionality, and what `delete` returns — belongs to **G4**.

**Identity is a content-addressed digest** over media type, content, sorted parent ids, and an
ordinal within the parent. Re-indexing unchanged content therefore produces the same ids, which is
what makes re-index idempotent and gives dedup and cache reuse for free. The ordinal is there
because identical content is not hypothetical — the reference's RAPTOR row recovery uses **exact float
equality**, so *"two identical chunks cross-assign cluster ids silently"*. The digest excludes the
embedding (derived from content, and it would bind ids to a model) and the stage configuration (so
two pipelines producing byte-identical output produce one node, which is what lets evaluation
compare them).

**Composition is typed and checked at load.** `Stage[In, Out]` means the ingest path is
`Stage[Seq[Node], Seq[Node]]` throughout while the query path is not: `Retriever` is
`Stage[Query, Seq[Scored[Node]]]`, `Generator` is `Stage[Seq[Scored[Node]], Answer]`. The resolver
checks that consecutive stages compose and fails naming both types. **The score lives on
`Scored[Node]`, not on `Node`** — it is a property of one retrieval, not of the node, and it would
fail the admission rule above. A stage takes and returns a *sequence*; the kernel runner owns
batching, so memory is bounded by batch size rather than corpus size while each stage invocation
stays eager and `Outcome` stays decidable at return.

### The store contract family

**Settled in G4**, published by `weft-store`. Backends differ genuinely — hybrid search, filtering,
full text, graph traversal — and the reference proved what happens when a contract pretends otherwise:
**17 dispatch sites over backend identity and zero registry lookups**, capability determined by
`hasattr(adapter, 'hybrid_search')`, an error string hard-coding `PGVECTOR_HYBRID_SEARCH=true`, and
`isinstance(adapter, LocalFileSystemAdapter)` guards that made three safety checks report
`all_passed=False` for every remote store.

```python
class NodeStore(Protocol):                         # the base; every store implements all of it
    async def add(self, nodes: Seq[Node]) -> None          # may buffer
    async def flush(self) -> None                          # idempotent; the runner calls it
    async def get(self, ids: Seq[NodeId]) -> Seq[Node]
    async def delete_source(self, sid: SourceId) -> Removed
    async def scan(self, cursor: Cursor | None) -> Page[Node]
    async def count(self) -> int
    async def put_source(self, rec: SourceRecord) -> None
    async def get_source(self, sid: SourceId) -> SourceRecord | None
    async def list_sources(self) -> Seq[SourceRecord]

class VectorSearch(Protocol):
    async def search_vector(self, vec: Vector, top_k: int, filter: Filter | None) -> Seq[Scored[Node]]

class TextSearch(Protocol):
    async def search_text(self, text: str, top_k: int, filter: Filter | None) -> Seq[Scored[Node]]

class MetadataFilter(Protocol): ...                # marker: supports the whole operator set
```

**Capability is derived, never declared.** At registration the kernel computes which protocols a
store class satisfies, and that set *is* its capability. Nobody writes a flag, so nobody writes a
false one — which matters because a declared flag is `hasattr` with better manners, and the reference's
signature bug is a capability declared unconditionally whose implementation is inserted
conditionally (`.doc`/`.ppt`). **Fitness function 5 holds here by construction**, provided the second
half is respected: a pack with optional dependencies **probes at `register()` and registers the class
that actually works**, so declaration and verification are one act. `weft plugins doctor` prints what
registered, what didn't, and why.

**Retrievers declare what they need.** `needs_store = (VectorSearch, MetadataFilter)`, checked at
resolution against the configured store; failure names the store, the missing capability and the
backends that provide it. There is no adaptation and no degradation: a pipeline that wanted hybrid
search does not quietly become vector-only, because *"quality silently dropped"* is the failure rule
5 exists to forbid. Hybrid is not a third method — it is a store satisfying both search protocols,
with fusion staying where it belongs, in the retriever.

**Stores never embed.** `VectorSearch` takes a vector, `TextSearch` takes text; a store is therefore
not coupled to a model and can be used with two, or with none. The reference's `query(query: str,
top_k, strategy_name)` did the opposite — it embedded internally *and* carried a retrieval concept
in the storage port.

**Filters are data.** A serialisable Pydantic AST — `eq ne in lt lte gt gte exists contains and or
not` — with field paths as strings **validated at pipeline load** against the registered ext models,
so `weft-graph.knd` fails at resolution naming `GraphData`'s real fields rather than matching
nothing at query time. One representation serves YAML and Python, which is also what makes a
resolved pipeline diffable. `contains` is not optional: cascade delete is a filter over
`lineage.sources`.

**Durability is a guarantee, not a call.** There is no `persist()` and no `load(force_rebuild)` —
the reference's, which had no transactional semantics across 9 call sites and imposed disk-index
lifecycle on backends with no such concept. `add()` may buffer; **the kernel runner calls `flush`**
at the end of a run and on cancellation, so no plugin can forget it: a completed run is durable, a
cancelled one durable to its last finished batch.

**Deletion is idempotent and resumable rather than atomic**, because atomicity would disqualify
every backend without transactions and `05` requires two backends satisfying this without stubs.
`delete_source` writes a tombstone — a status on the `SourceRecord` — deletes by filter on
`lineage.sources`, then clears it. A crash leaves the tombstone, so the next call or `weft doctor`
finishes the job, and nothing is ever half-deleted invisibly. It returns counts and affected
sources with a cursor for ids rather than materialising a cascade that can span a corpus.

**`SourceRecord` closes the last reach-through.** `id`, `uri`, `content_hash`, `indexed_at`,
`pipeline`, `status` — one structure serving change detection (re-index skips an unchanged file
instead of re-paying for every enhancer's LLM calls), cascade resumption, and `doctor`'s inventory.
`pipeline` is what lets `weft index` say *"already indexed, by a different pipeline"* rather than
silently skipping or silently duplicating.

Taken together the four names retrieval used to reach through for are gone: `_vector_indices` sits
behind `VectorSearch`, `_strategy_for_nodes` names a concept a store no longer has, `indices_dir`
has nothing to hold because **retrievers never build an index** — text search is a store capability,
so the BM25 pickle cache has no successor — and `update_file_metadata` is `SourceRecord`.

## 2. Packs and discovery

A pack declares one entry point. That is the entire integration surface:

```toml
# in the graph add-on's own pyproject.toml — nothing in weft changes
[project.entry-points."weft.packs"]
graph = "weft_graph:register"
```

`register` receives the registry and adds whatever the pack provides. One call site, many
registrations, any mix of contracts.

**Built-ins ship as first-party packs through the same entry point.** They live in the same
repository for release convenience and get no shortcut. This is fitness function 2, and it is the
difference between a plugin API that works and one that is theoretically supported.

**Discovery is eager.** When a command needs the registry, every permitted pack is imported and its
`register()` is called. Enumeration on its own — `importlib.metadata` reading `.dist-info` — imports
nothing and is always safe; execution begins at `register()`. And because `register()` is where a
pack contributes, it is also the only thing that knows what a pack contributes: nothing can answer
*"who provides `docling`?"* without running it.

> **Corrected in G3 (2026-08-15).** This paragraph read: *"Discovery is lazy: entry points are
> enumerated at startup, but a pack's module is imported only when one of its plugins is actually
> requested. A pack that registers a heavy dependency costs nothing until used."* **That cannot be
> true as written.** Pipelines select plugins by bare name (§3 — `use: docling`), and entry-point
> metadata says nothing about what a pack will register, so resolving a bare name means importing
> packs until one claims it. Lazy import and bare names are mutually exclusive. Bare names win,
> because pipelines-as-data is what Phase 1 exists to prove, and namespacing every reference to a
> distribution (`use: weft-docling/docling`) would couple the data format to packaging and make every
> derived pipeline worse.
>
> The two designs that would have preserved laziness both die on **G4**: per-plugin entry points,
> where the metadata *is* the registration, and a cached resolution index. Neither can express
> **conditional registration** — a pack probing its optional dependencies and registering only what
> works. The true registration set depends on the *environment*, not on the installed distributions,
> so any answer computed without executing `register()` is a second source of truth that can disagree
> with the first. That is the reference's *17 of 23 evaluators* bug in a new costume.

Eager discovery is paid for at the registration seam rather than by asking authors to be careful:

- **`register()` is import-light.** It registers factories, not instances — `registry.add(Retriever,
  'graph', partial(GraphRetriever, settings))` — and a pack imports its heavy dependencies inside the
  factory, not at module top. That is an author obligation, and author obligations decay, so it is
  **measured**: the registration wrapper times each `register()` and records what it added to
  `sys.modules`, and `weft plugins doctor` prints both. Not enforcement — a fact instead of a hope.
- **Discovery runs when a command needs the registry, never at process start.** `weft --version`,
  `weft init` and `weft config get` complete with zero pack code executed. `weft --help` *does* need
  it, because `03` generates help from the registry so the command list cannot drift from what is
  installed. That cost is accepted rather than bought off with a second, static entry-point group for
  commands, which would buy a fast `--help` by reintroducing precisely the declared-versus-actual
  drift this model exists to prevent.

Two things this buys immediately that the predecessor could not do at all:

- `uv add weft-graph` adds a capability. `uv remove weft-graph` removes it. Core is untouched both
  times.
- A private, unpublishable, customer-specific pack works exactly like a public one.

**Settled in G3** — entry points execute third-party code at discovery. The posture, the allow-list
and what a refused pack does are specified in *The trust model* at the end of this section.

> **Extended by the reference study (2026-08-10) — three things this section should say explicitly.**
>
> **1. The reference did have late binding; it bound in the wrong direction.** There is no discovery
> mechanism of any kind — 0 hits for `pkgutil`, `walk_packages`, `entry_points` or
> `importlib.metadata` across 259 files — but there are **15 `importlib.import_module` sites, all
> against hardcoded literals, and 11 of them import `'adapters.…'`**: the library dynamically
> reaching *outward* into its own deployment layer by name. `core/llm/adapter.py:16-20` is the
> shape — a module `__getattr__` that resolves `LiteLLMAdapter` by importing
> `adapters.llm.litellm_adapter`. That is **a service locator, not dependency injection**, and it is
> the anti-pattern the entry-point model replaces.
>
> **2. Built-ins registering through private import lists is not hypothetical — the lists are
> already wrong.** The reference has three mutually inconsistent bootstrap mechanisms (eager sibling
> imports at `core/engine/strategies/__init__.py:7-53`; a lazy literal tuple
> `_BUILTIN_ENHANCER_MODULES` at `indexing/enhancers/registry.py:26-31`; a comment-annotated import
> pair at `evaluation/__init__.py:20-22`), with two consequences measured in a cold process:
> `import a_prior_project.evaluation` registers **17 of 23** evaluators, because two `llm_judge/__init__.py`
> files are docstring-only — asking for `faithfulness` returns no error and no score; and
> `import a_prior_project.indexing.enhancers.registry` yields **3** enhancers while
> `get_available_enhancers()` yields **4**. Two sources of truth for "what exists" that disagree
> until a specific function is called. This is why fitness function 2 must be a runtime check.
>
> **3. A pack needs somewhere to put its settings, and the reference has nowhere.** `IndexingStrategy`
> (`core/config/models.py:208-216`) has exactly **3 fields** — `type: str` (unvalidated),
> `parser_config`, `enhancers: list[str]`. Enhancers get names only. A graph add-on contributing an
> enhancer, a retriever and a store has no place for its configuration at all. **A per-pack config
> namespace is a distinct requirement from per-stage config** (§3's `with:`), and §4 needs both.
>
> **This requirement has no gate that owns it, which is itself the defect to fix first.** Item 4
> below routes to G2 and G4; this one routed nowhere, so nothing in the execution script would have
> forced a decision before the pack contract is published. It belongs to **G1**, because G1 draws the
> kernel/pack line and Phase 0 publishes the contracts a pack is written against — a pack contract
> shipped without a settled place for pack settings is a contract that breaks on its first real
> add-on, which is Phase 5's entire test. Added to G1's agenda in `05` §G1 rather than left as prose
> here.
>
> **4. Collision policy is undefined here, and it was undefined there.** Six registration decorators,
> four different collision behaviours: `register_strategy` warns then overwrites
> (`core/engine/strategies/registry.py:47-48`); `register_evaluator` warns then overwrites
> (`evaluation/base.py:111-112`); `register_streaming_strategy` (`:83-85`), `register_enhancer`
> (`indexing/enhancers/registry.py:51`), `register_retrieval_strategy` (`retrieval/registry.py:164`)
> and `register_indexing_strategy` (`:184`) **overwrite silently with no check at all**. Two packs
> both registering `keybert` has no defined outcome in the reference and none here yet. **Open question
> for G2 and G4** — see `reference/study/09-open-questions.md` C-12, *"what arbitrates when two plugins
> claim the same thing?"*
>
> (`reference/study/10-doc-corrections.md` E2, E3, E5, E9.)

### Pack settings, and what `register` receives

**Settled in G1** — this is the answer to item 3 above. Per-stage `with:` config and per-pack
settings are different lifetimes: `with:` is *this stage in this pipeline*, pack settings are *this
installation of this pack* — credentials, an endpoint, a cache directory, a default model — shared
across every plugin it registers. The reference had nowhere at all for the second kind, so a pack
contributing an enhancer, a retriever and a store would repeat its connection details three times
and hope they stayed in sync.

```yaml
# weft.yaml
packs:
  weft-graph:                       # keyed by distribution name, never the entry-point alias
    endpoint: bolt://localhost:7687
    api_key: ${env:GRAPH_KEY}
```

```python
# weft_graph/__init__.py
class Settings(BaseModel):
    endpoint: str
    api_key: SecretStr


def register(registry: Registry, settings: Settings) -> None:
    registry.add(Retriever, "graph", partial(GraphRetriever, settings))
    registry.add_messages(ns="graph", resources=files("weft_graph") / "locales")
```

- **Keyed by distribution name.** `weft-graph`, not `graph`. Entry-point aliases can collide between
  two packs; distribution names cannot, so the `packs:` namespace has no arbitration problem to
  solve. (Plugin-*name* collisions remain open — G2.)
- **Typed, validated at discovery.** The pack declares a Pydantic model; the kernel validates before
  `register` is called and fails naming the pack and the field. Never `dict[str, Any]`.
- **Handed to `register`, not injected into plugins.** The pack wires its own settings into its own
  factories, which is why the `Stage` protocol in §1 stays at `__init__(config)` with no second
  injection path and no extra passport field.
- **Secrets are `SecretStr`, with `${env:VAR}` interpolation performed by the config loader**, so no
  component reads the environment itself.
- **A `packs:` key naming a pack that is not installed is an error**, per rule 5 — loud, naming the
  distribution to install. A config block that is silently ignored is how a machine ends up running
  without the pack nobody noticed was missing. The remedy is `weft plugins doctor`, not a warning.

**Catalogues are contributed the same way.** A pack hands the kernel its own locale resources at
registration, addressed through its own distribution (`importlib.resources`), namespaced by pack.
No component ever computes a path to another package's files — which is what made the reference's
`PromptLoader` resolve locales as `Path(__file__).parent.parent / 'locales'` and made shipping
prompts or translations from a pack impossible. The bug is not fixed here; it is unreachable.

### The trust model

**Settled in G3, 2026-08-15.**

**The threat, named precisely, because the convenient framing answers the wrong question.** *Malicious
pack* is the framing that suggests itself and it does not survive contact: if you deliberately
install a hostile distribution, entry points changed nothing — its code was already in your
environment and already ran at the first `import`. Under that framing there is no gap and no decision
to make.

The framing that survives is narrower and true. **Entry points convert *installed* into *executed
with the application's privileges and configuration*.** The gap is not malicious versus benign, it is
**installed-and-intended versus installed-and-ambient**: a pack you never chose, arriving as a
transitive dependency of something you did choose, whose `register()` runs inside your process, at
your credentials, against your data — with nothing in `uv add some-rag-toolkit` telling you it
happened. That is the only risk entry points create, and it generalises past malice to the case that
will actually occur, which is a pack somebody forgot was installed, quietly contributing to
production. Under eager discovery this is not an edge case: **every installed pack executes on every
command that touches the registry.**

**What cannot be built, recorded so that it is not re-proposed.** A two-tier model — discovery open,
but filesystem, network and shell capabilities granted explicitly — is not implementable here. A pack
runs in your interpreter, and CPython has no in-process boundary that constrains `open`, `socket` or
`subprocess`; `sys.audit` hooks are advisory and removable by the code they audit. Enforcement needs
a process or container boundary, which costs a serialisation format for every payload that crosses
it, eliminates the shared `Context`, and contradicts G6's single event loop. A grant weft cannot
enforce is only *a declaration a pack makes about itself*, and a control that looks like enforcement
but is not is worse than an acknowledged gap, because people build policy on it. **Weft therefore
states the posture instead of simulating a control: a pack runs with your full privileges, and
installing is trusting.**

**The posture: open by default, exact pin available.**

```toml
# weft.toml — optional. Absent means open.
[packs]
allow = ["weft-extract", "weft-chunk", "weft-store", "weft-graph"]
```

- **Exhaustive when present.** Everything unlisted is refused. A list that only adds is not a
  control.
- **Distribution names, never versions.** Version pinning belongs to `uv.lock`; duplicating it here
  would create the second list that drifts from the first — the failure the control file in
  `README.md` exists to prevent.
- **Absent by default**, and the reason opt-in security is acceptable *here* specifically: the harm
  under this threat model is unchosen code executing, not credentials exfiltrated. A posture that
  demanded a manual step on every install would be disabled wholesale with `allow = ["*"]`, which is
  open with extra ceremony and a false sense of safety.

Two things run **always**, opted in or not, and they carry most of the practical weight:

- **The executed pack set is recorded on every run.** Not as a security feature: **Phase 4 requires it
  anyway.** `weft eval compare` across two pipelines is meaningless if the installed pack set differed
  between them, and `weft trace` claims to replay what a run actually did. The record therefore has an
  owner and a user outside security, which is what keeps it correct — and the trust model gets its
  answer to *"what was in this process?"* for free.
- **`weft plugins doctor` flags packs that are not direct dependencies.** Deriving trust from the
  dependency graph was considered as the *mechanism* and rejected: installed metadata does not record
  which distributions a human named, `uv` knows and `pip` does not, and `uvx weft` has no project
  manifest at all — so the fallback would be "open", and a control that evaporates when a file is
  absent is one nobody can reason about. Demoted to reporting, its unreliability is harmless:
  *"cannot determine, no manifest"* is a fine thing for a report to say and an unacceptable thing for
  a gate to say. It makes ambient arrival visible on every doctor run.

**One status vocabulary, shared with G4's conditional registration.** A refused pack and a pack that
lost half its registrations to a missing optional dependency are the same question asked twice —
*why is this not contributing?* — and they get one answer surface, not two:

| Status | Meaning |
|---|---|
| `active` | Imported, `register()` ran, *n* contributions |
| `refused` | Unlisted under an active pin. **Never imported** — refusal precedes execution, or it is not refusal |
| `failed` | `register()` raised |
| `partial` | Registered, but conditional registration skipped something — *what*, and *why* (G4) |
| `allowed, not installed` | Named in `allow`, absent from the environment |
| `ambient` *(flag on `active`)* | Running, and not a direct dependency |

The behaviours that vocabulary implies:

- **An `allow` entry for a pack that is not installed is reported, not fatal.** This is a deliberate
  asymmetry with the rule above that a `packs:` key naming an uninstalled pack *is* an error, and the
  distinction is exact: **`packs:` expresses a requirement, `allow` expresses a permission.** Running
  without something you configured is the "machine quietly missing the pack nobody noticed" failure;
  permitting something absent costs nothing, and making it fatal would break sharing one config across
  environments.
- **`failed` skips the pack and continues**, with one line to stderr naming the distribution and
  pointing at doctor, on every command, suppressed only by `--quiet`. A broken pack silently absent is
  the reference's accept-then-fail shape exactly.
- **Every unresolvable plugin name carries its reason**, taken from doctor's own data — *"`docling` is
  provided by `weft-docling`, which is refused"* — never a bare `unknown plugin 'docling'`. This is
  the anti-reference property in one sentence: asking the reference for `faithfulness` returned **no error and
  no score**.
- **Exit codes distinguish policy from data.** A pipeline naming a plugin from a `refused` pack exits
  **3**, refused, and names the config key that would permit it. A name provided by no pack at all
  stays **4**; a name lost to `failed` or `partial` stays **4** with its reason attached, because
  neither is a policy decision. A CI job can act on that difference; collapsed into one code, it
  cannot.

**Disclosure, which grants and denies nothing.** A pack may publish what it touches. The kernel reads
a module-level `DISCLOSURE` immediately after import and before calling `register()`:

```python
DISCLOSURE = Disclosure(
    network=("bolt://localhost:7687",),
    filesystem=("~/.cache/weft-graph",),
    subprocess=(),
    note="Reads and writes the configured Neo4j database.",
)
```

- **Concrete strings, not booleans.** `network: true` is noise; a hostname is information.
- **Optional.** Doctor prints `not disclosed` when it is absent. The asymmetry with the mandatory
  command permission class below is principled rather than convenient: **a permission class is
  enforced**, the kernel acts on it, so demanding it is fair; **disclosure is not**, so requiring it
  would produce only text, and required unverifiable text reliably degrades into copy-pasted
  boilerplate. `not disclosed` is honest, informative, and applies the same social pressure without
  manufacturing false data.
- **It is a disclosure to the operator, never a claim weft checks.** Weft refuses nothing on the basis
  of it. Stated in this form deliberately: a field that reads as *"this pack does not use the
  network"* is unverified, unenforced, and fails silently in the unsafe direction; a field that reads
  as *"this pack talks to `bolt://…`"* is documentation with a fixed location and a machine-readable
  shape, which nobody can mistake for a sandbox.
- **A near-miss worth naming, because a builder will find it and think it is clever.** G6's fitness
  function 7(b) already installs a blocking-call detector that intercepts `open`, `socket` and
  `subprocess` at the stage seam. It must **not** be reused as a capability observer. It sees only
  *blocking* calls on the loop thread, so an async HTTP client or anything behind `to_thread` is
  invisible to it — it would report "no network access" for a pack that spent the whole stage
  exfiltrating over `aiohttp`. Sound for colour, unsound for security, and a detector reused across
  that line is how false assurance gets built.

**What this model does not solve, stated so nobody assumes otherwise.** Signature verification,
sandboxing, per-pack privilege separation, and any defence against a pack that is hostile once
running. All four are out of reach without a process boundary. If weft ever wants them it wants an
out-of-process pack host, and that is a new decision with its own gate — not an extension of this
one.

## 3. Pipelines as data

A pipeline is an ordered list of stages. Each stage names a contract, selects a plugin by name, and
carries that plugin's configuration. Because it is data, it can be diffed, versioned, generated,
compared in evaluation, and — the point — derived.

```yaml
# base.yaml
name: base
stages:
  - id: extract
    use: docling
    fallback: [pdfplumber, ocr]
  - id: clean
    use: standard
  - id: chunk
    use: sentence
    with: {size: 512, overlap: 50}
  - id: embed
    use: bge-m3
  - id: store
    use: pgvector
```

> **Corrected from the reference study (2026-08-10) — this example asserts a stage order the reference did
> not use, and it is load-bearing.** The reference **chunks first and cleans second**, and it has two
> stages this example omits. `IndexingPipeline.process` (`indexing/pipeline.py:82-150`), by the
> code's own numbering: **0** separate `Document`s from `BaseNode`s (`:111`) — tables and figures are
> atomic and bypass the parser; **1** chunk (`:121`); **2** clean (`:124`); **3** attach `chunk_index`
> metadata (`:127`); **4** enhance (`:130`); **4.5** scrub transient metadata (`:135-136`); **5**
> store (`:142`). There is **no separate embed stage** — embedding happens inside storage.
>
> The example above is left as written because it may well be what Weft *wants*; but it is now a
> **decision for G2**, not an inherited fact, and G2 must state which order Weft adopts and why.
> Whichever way it goes, stage 0 and stage 4.5 belong in the model: stage 0 exists so atomic nodes
> are never re-chunked, and 4.5 exists because *"if the enhancer is absent or fails, this guard
> prevents multi-MB base64 blobs from being serialised into PGVector JSONB"*
> (`indexing/pipeline.py:429-438`). If Weft has no embed stage either, `bge-m3` above belongs inside
> the store's configuration rather than beside it.
> (`reference/study/10-doc-corrections.md` A12; `reference/study/08-salvage.md` §T1.1.)

> **Extended by the reference study (2026-08-10) — an ordered list is not enough. Three findings, all
> for G2.**
>
> **Ordering constraints exist, and in the reference they are prose only.** The `CorrectionPipeline`
> docstring (`indexing/cleaning/pipeline.py:30-51`) is the highest-value scar in the study:
> *"HyphenationFixer — MUST run before whitespace normalization while newlines still exist (e.g.
> kompu-\\nter -> komputer); TableLinearizer — Detect columns based on whitespace gaps, MUST run
> before whitespace normalization collapses gaps; WhitespaceNormalizer — this is destructive and must
> run last. **IMPORTANT: Changing this order will break functionality.**"* The four derivation
> operators below let a third party insert a stage between `HyphenationFixer` and
> `WhitespaceNormalizer` and **silently corrupt text**. Pipeline-as-data therefore needs an
> **ordering-constraint concept**, not just an ordered list — a fifth position for G2 to attack.
>
> **A stage list the executor does not read is worse than no stage list.** `CleaningConfig.processors:
> list[str] = ['unicode','whitespace','artifacts','table']` (`core/config/models.py:51-54`) is the
> one field in the reference shaped like this YAML — and it is **never read**. `CorrectionPipeline.__init__`
> (`pipeline.py:53-110`) reads six individual `*_enabled` booleans instead.
>
> **Language-conditional stages are a real requirement this YAML cannot express.** Two of those six
> booleans are additionally gated on `config.language == 'pl'` (`pipeline.py:81`, `:97`) — a
> hardcoded language check inside a supposedly generic pipeline. Weft's model needs an answer for it.
>
> (`reference/study/10-doc-corrections.md` E7, E8; `reference/study/08-salvage.md` §T2.10.)

### Derivation — driving use case A

> *"I need to add KeyBERT to the `specific` pipeline — that pipeline is created from an existing
> one but with KeyBERT added."*

```yaml
# specific.yaml
name: specific
extends: base

insert:
  - after: chunk
    stage: {id: keywords, use: keybert, with: {top_n: 8}}
```

That is the whole change. The parent is referenced, never copied, so improvements to `base` reach
`specific` automatically.

> **Extended by the reference study (2026-08-10) — the `with:` block is the most-repeated mistake in the
> reference, and it must not be an afterthought.** The identical failure occurs independently in two
> subsystems that never talked to each other. `evaluation/config.py:22` has a `params` field
> **literally commented out**, so `EvaluatedPipeline` constructs every metric with zero arguments
> (`wrapper.py:42,47`) — no metric in the reference can be parameterised at all. And
> `evaluation/datasets/settings_loader.py:233` carries `# TODO: Enhance registry to support
> enhancer-specific configuration`, because `create_enhancer(name, llm, language, **kwargs)` cannot
> carry per-enhancer typed configuration. `{top_n: 8}` above and the multi-registration pack in §4
> both depend on this being solved, which is why §1 now states it as a contract rule.
> (`reference/study/10-doc-corrections.md` E4.)

Four operators, and the set stays closed until something real needs a fifth:

| Operator | Effect |
|---|---|
| `insert` | Add a stage, positioned `after:` or `before:` an existing stage id |
| `replace` | Swap the plugin at a stage id, keeping its position |
| `remove` | Drop a stage by id |
| `set` | Override configuration of an existing stage without changing the plugin |

Resolution produces a frozen, fully-explicit pipeline: every stage, plugin, version and
configuration value named, with no inheritance left to interpret. That resolved form is what runs,
what gets logged, and what evaluation compares — so two runs can always be diffed exactly, which is
the thing the predecessor's A/B story was missing.

> **Corrected from the reference study (2026-08-10):** "missing" understates it. The predecessor had **no
> comparison capability at all**, not a weak one — `evaluation/helpers.py` is entirely dead (all four
> public functions, zero references in `src/` and `tests/`), `grep 'ab_test|sweep|grid_search|compare_strateg'`
> returns 0, and **nothing in 6,632 lines of `evaluation/` persists a result anywhere**. Diffing the
> resolved form therefore only works if resolved runs are *stored*; `01` Phase 4's exit criterion
> now says so. (`reference/study/10-doc-corrections.md` C5; `reference/study/09-open-questions.md` C-10.)

If KeyBERT is not installed, resolution fails at load with the valid options named. Not at first
document. Never a silent fallback.

**Resolution checks three things, not one** (G5). The plugin exists; the stage's `requires` are
produced by some upstream stage; and consecutive stages **compose by type** — `Stage[In, Out]`, so a
pipeline that reranks before it retrieves fails at load naming both types rather than on the first
query. Everything a resolved pipeline can be wrong about is therefore wrong *before* it runs, which
is the whole reason resolution produces a frozen, fully-explicit form.

**Open decisions:** the exact overlay semantics, conflict rules for multi-level inheritance, and
whether pipelines are authored in YAML, Python, or both, are grilling session **G2**. The stage
payload's type model is **G5** — it is the hardest question in the design and defaulting it would
be a mistake.

## 4. Add-ons — driving use case B

> *"I need to add graph — a simple and independent add-on, easily plugged into the system."*

The graph pack, complete:

| It registers | Against contract | Effect |
|---|---|---|
| Entity and relation extractor | `Enhancer` | Usable as a stage in any pipeline |
| Graph store | `Store` | Sits beside the vector store |
| Graph-walk retriever | `Retriever` | Selectable by any retrieval strategy |
| `weft graph build`, `weft graph show` | `Command` | Appear in `--help` and REPL completion |
| A pipeline fragment | — | Ships a ready-made derived pipeline users can extend further |

Install:

```bash
uv add weft-graph
weft pipeline derive kg --from base --insert-after chunk graph.entities
weft index ./docs --pipeline kg
```

Nothing in core changed. Nothing in core knows what a graph is. If the pack is uninstalled, the
`kg` pipeline fails to resolve with a message naming the missing plugin and the pack that provides
it — which is the correct behaviour, and is what "loudly" means in rule 5.

**The independence test.** Phase 5 exists to check this honestly: the graph pack is built by
someone who has not worked on the core. If they need a core change, the extension model has a hole,
and finding it that way is much cheaper than finding it after publishing contracts.

## 5. Why this survives where the predecessor did not

| Predecessor failure | What prevents it here |
|---|---|
| Chunker factory in `evaluation/datasets/settings_loader.py:55-99`, on the production path via function-local imports at `retrieval/storage.py:145,407` | Plugins are discovered, never constructed by a hand-written factory |
| `FileType` enum plus five more structures across three files plus a separate extension list | Capability metadata is declared on the plugin. There is no second list |
| `RetrievalStrategyType` closed enum as the **key type** of `RETRIEVAL_BUILDERS` (`retrieval/registry.py:147`, `retrieval/types.py:24-26`) — hard-closed at the type level, which is worse than a string key and which no grep can see | Fitness function 4 **clause (b)**: `set(valid_names) == set(registry.keys())` asserted at every selection surface, as a runtime property |
| `StrategyName` (10 members, `core/engine/types.py:56-72`) declared in a different module from `STRATEGY_REGISTRY` (`core/engine/strategies/registry.py:35`), kept in sync by hand, with no test asserting it | Fitness function 4 clause (a). And the rule behind it: valid names *are* the registry's keys |
| `FileType` in front of `EXTRACTOR_MAP` with three formats bypassing the map entirely through an `if` chain (`indexing/parsing/factory.py:333-338`) | Same runtime property — an `if` chain over literals is a registry with the registration removed |
| Unknown strategy silently becomes `rag_simple` — **four sites**, not one: `core/config/models.py:271-283` (`except ValueError: return StrategyName.RAG_SIMPLE`), `models.py:336-342` (`_get_default_strategy()`), `core/engine/router.py:541` (`.get('strategy', 'rag_simple')`), `router.py:567-573` (total parse failure) | Rule 5, and resolution failing at load rather than at use |
| **A registered third-party strategy that can never run.** In the reference a plugin registered through `@register_strategy` *is* registered, *is* listed by `get_all_strategy_metadata()`, *is* described to the LLM in the routing prompt (`router.py:381-383`) — and hits three walls: the enum coercion above, `RoutingResponse.validate_strategy` (`core/engine/types.py:476-495`) hard-rejecting non-enum values, and `AdaptiveRouter._select_strategy_from_scores` (`router.py:287-350`), a hard-coded 10-branch `if/elif` assigning literal `StrategyName.*` members with no plugin branch | Fitness function 4 clause (b), which is the only one of the checks that catches wall three. This row is the sharpest statement of this document's thesis: **registration is not reachability** |
| Nothing **discoverable** from outside the package. One axis (enhancers) is otherwise fully open — `@register_enhancer('keybert')` works end to end today via `indexing/enhancers/registry.py:51`, `get_enhancer_class` (`:59`) and `create_enhancer` (`:75-106`) — and lacks only the import trigger | Entry points, tested by the Phase 0 exit criterion. The reference's enhancer axis is the proof that decorator + lazy bootstrap + loud lookup suffices *once discovery exists*, so discovery is the only genuinely new mechanism |
| Built-ins using internal paths the public API lacked — literally, at `retrieval/registry.py:649-668`, where the three indexing builders are re-wrapped and re-assigned *after* registration to add span wrapping, so a plugin using the public decorator silently gets less observability | Fitness function 2, as a **runtime** check |

Every row is a real defect found in shipped code, paired with a mechanism rather than an intention.
That pairing is the difference between this document and the predecessor's own architecture docs,
which described the same goals and were not wrong so much as unenforced.

> **Corrected from the reference study (2026-08-10).** Four rows were sharpened rather than replaced,
> and one row is new. The corrections: the `rag_simple` coercion is **four sites** (the prior review
> located one); the `FileType` cluster is six structures across three files, not "four maps"; the
> `RetrievalStrategyType` row was attributed to fitness function 4 as originally worded, which could
> not have caught it, because there is no shadowing to grep for; and "nothing extensible from outside
> the package" is true of *discovery* but not of the enhancer axis, which matters because driving use
> case A runs through exactly that axis. The new row — a strategy that registers and can never
> execute — is the study's sharpest single finding about the reference's seam.
> (`reference/study/10-doc-corrections.md` A10, B7, B10, C7; `reference/study/02-discovery-and-config.md` §2.3.)
