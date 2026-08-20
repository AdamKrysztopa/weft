# Contract reference

Generated — `docs/08-manuals.md` §3 clause (b). Every signature, docstring and version
below is read directly off the published `Protocol`; there is no hand-maintained copy for
it to drift from. Regenerate with `uv run python scripts/generate_contract_reference.py`, checked by
`tests/docs/test_generated_docs.py`.

## What you write, and what you get for free

Every method below is declared `async def` and returns an `Outcome[T]` —
`Produced[T] | NothingToProduce | Failed`, defined in `weft_kernel.payload.outcome` and
explained in full in `docs/02-extension-model.md` section 1, which this reference links to
rather than restates. A pack author writes exactly the method bodies below; the call is
never made directly — it always passes through the registration seam
(`weft_kernel.seam.wrap`), which attaches four things automatically, not by convention an
author has to remember:

- **A span**, named from the contract and plugin (or the resolved pipeline position, once a
  runner has one), `SpanKind.INTERNAL`, carrying `weft.pack`, `weft.contract` and
  `weft.plugin` attributes.
- **Error attribution.** A `WeftError` a plugin raises has its `pack`, `contract`, `plugin`
  and `stage` fields filled in wherever the plugin left them unset; anything else escaping
  the call is wrapped fresh with those same four fields and `__cause__` preserved, so no
  traceback is hidden. `CancelledError` is never caught here, so it is never at risk of
  being swallowed.
- **Transient stripping.** Every `Node` a plugin produces (bare, or inside a list or tuple)
  has every `__transient__` extension namespace removed before the result leaves the seam.
- **The categorical blocking-call detector**, scoped to exactly the plugin's own `await` —
  fitness function 7(b) fails the run if that call blocks the loop (file IO, a socket,
  `time.sleep`, a synchronous driver).

**`Lifetime` is declared by the plugin, not attached by the seam.** `lifetime:
ClassVar[Lifetime] = Lifetime.RUN` by default, read defensively
(`getattr(instance, "lifetime", Lifetime.RUN)`) so a plugin satisfying its contract only
structurally still gets the default. `Lifetime.RUN` is a fresh instance per pipeline run —
no thread-safety obligation on the author. `Lifetime.PROCESS` is opt-in and accepts that
obligation, in exchange for the kernel reusing the instance across runs, cached by
`(tenant_id, contract, name, config_hash)`.

## `Chunker`

**Module:** `weft_chunk.contract`  
**Registered by:** `weft-chunk`  
**Version:** `1.0.0`

Splits `Node`s into smaller `Node`s, each one a child under `Node.derive`.

One method, domain types on both sides, exactly `Extractor`'s shape one
stage later in the pipeline. A chunker that finds nothing to split
answers `NothingToProduce`, not an empty `Produced([])` — the same
reference-trap fix `weft_extract.contract.Extractor` documents, applied here
because the same ambiguity is possible at every stage that returns a
sequence.

### Methods

```python
async def run(
    self,
    payload: collections.abc.Sequence[weft_kernel.payload.node.Node],
    ctx: weft_kernel.context.Context,
) -> weft_kernel.payload.outcome.Outcome[
    collections.abc.Sequence[weft_kernel.payload.node.Node]
]: ...
```

## `Cleaner`

**Module:** `weft_clean.contract`  
**Registered by:** `weft-clean`  
**Version:** `1.0.0`

Repairs or normalises a `Node`'s text, one node in, one repaired node out.

A cleaning stage's job is narrower than a chunker's: it never splits or
merges nodes, so every implementation returns exactly as many nodes as it
was handed, each built through `Node.derive` so lineage records the
repair as its own step. A batch with nothing to clean still answers
`NothingToProduce`, never a silently empty `Produced([])` — the same
reference-trap fix `weft_extract.contract.Extractor` and `weft_chunk.contract.
Chunker` already document, applied here because the same ambiguity is
possible at every stage returning a sequence.

### Methods

```python
async def run(
    self,
    payload: collections.abc.Sequence[weft_kernel.payload.node.Node],
    ctx: weft_kernel.context.Context,
) -> weft_kernel.payload.outcome.Outcome[
    collections.abc.Sequence[weft_kernel.payload.node.Node]
]: ...
```

## `Command`

**Module:** `weft_command.contract`  
**Registered by:** `weft-cli`  
**Version:** `1.1.0`

One CLI-invoked action a pack contributes, registered exactly as it registers a retriever.

Not a pipeline position — see the module docstring's *"`Command` is not a pipeline
position"* paragraph. `run` accepts the parsed, already-validated arguments and returns a
decided `Outcome[CommandResult]`, never printed text — see the module docstring's paragraph
on *"The governing property this task builds into the signature."*

### Declared attributes

```python
args_model: typing.ClassVar[type[pydantic.main.BaseModel]]
```

```python
result_model: typing.ClassVar[type[weft_command.contract.CommandResult]]
```

### Methods

```python
async def run(
    self, args: pydantic.main.BaseModel, ctx: weft_kernel.context.Context
) -> weft_kernel.payload.outcome.Outcome[weft_command.contract.CommandResult]: ...
```

## `ContextPacker`

**Module:** `weft_retrieve.contract`  
**Registered by:** `weft-retrieve`  
**Version:** `1.0.0`

Chooses, orders and labels the evidence that will enter a prompt.

A distinct position rather than a knob on the generator, because `10` §1.1's `repack`
row is a measured technique with its own parameters, and because the citation labels
a `Generator` resolves against are assigned here — which is what lets
`weft_generate.payload.Answer` refuse an unfollowable citation at construction.

### Methods

```python
async def run(
    self, payload: weft_retrieve.payload.Ranking, ctx: weft_kernel.context.Context
) -> weft_kernel.payload.outcome.Outcome[weft_retrieve.payload.Passages]: ...
```

## `Embedder`

**Module:** `weft_embed.contract`  
**Registered by:** `weft-embed`, `weft-openai`  
**Version:** `1.0.0`

Attaches an embedding to each `Node` it is handed.

One method, domain types on both sides, exactly `Chunker`'s shape one
stage later in the pipeline. An embedder that finds nothing to embed
(an empty batch) answers `NothingToProduce`, not an empty `Produced([])`
— the same reference-trap fix every other Phase 0 contract documents.

### Methods

```python
async def run(
    self,
    payload: collections.abc.Sequence[weft_kernel.payload.node.Node],
    ctx: weft_kernel.context.Context,
) -> weft_kernel.payload.outcome.Outcome[
    collections.abc.Sequence[weft_kernel.payload.node.Node]
]: ...
```

## `Enhancer`

**Module:** `weft_enhance.contract`  
**Registered by:** `weft-enhance`  
**Version:** `1.0.0`

Attaches a new, namespaced fact to each `Node` it is handed — never rewrites `content`.

One method, domain types on both sides, exactly `Cleaner`'s shape with a different
job: where a `Cleaner` returns a *repaired* node built through `Node.derive`, an
`Enhancer` returns the *same* node with an added `Node.with_ext` fact — identity
(`node.id`) is unaffected, because nothing about the text changed. A batch with
nothing to enhance still answers `NothingToProduce`, never a silently empty
`Produced([])` — the same reference-trap fix every other contract in this tree documents.

### Methods

```python
async def run(
    self,
    payload: collections.abc.Sequence[weft_kernel.payload.node.Node],
    ctx: weft_kernel.context.Context,
) -> weft_kernel.payload.outcome.Outcome[
    collections.abc.Sequence[weft_kernel.payload.node.Node]
]: ...
```

## `Expander`

**Module:** `weft_index.contract`  
**Registered by:** `weft-index`  
**Version:** `1.0.0`

Every node handed in, unchanged, plus zero or more nodes derived from it.

A batch with nothing to expand still answers `NothingToProduce`, never a silently
empty `Produced([])` — the same reference-trap fix every other contract in this tree
documents. A single node this plugin could not generate a representation for is not
that case: the node itself is still in the output, unchanged, and only its own
representations are missing — degrade, never fail the run, the same posture `10` §1.2's
`raptor` row (task 2.32) states for a summary that cannot be produced, because both
techniques are meant to share this one mechanism rather than invent their own failure
policy apiece.

### Methods

```python
async def run(
    self,
    payload: collections.abc.Sequence[weft_kernel.payload.node.Node],
    ctx: weft_kernel.context.Context,
) -> weft_kernel.payload.outcome.Outcome[
    collections.abc.Sequence[weft_kernel.payload.node.Node]
]: ...
```

## `Extractor`

**Module:** `weft_extract.contract`  
**Registered by:** `weft-extract`, `weft-pdf`  
**Version:** `1.0.0`

Turns source documents into the first `Node`s of an ingest pipeline.

One method, domain types on both sides — `docs/02-extension-model.md`
section 1 names the predecessor's `BaseExtractor` as the interface shape
this contract follows, one `@abstractmethod extract(...)`, and the
failure to fix was only ever its dispatch, never its narrowness. The
shape is reused; no line of the reference's own text is. `run` is that method,
async per G6, returning `Outcome` rather than a bare value or an
envelope with an ambiguous empty case: a source that legitimately yields
no text answers `NothingToProduce`, distinct from `Failed`, which is the
fix for the reference's `fail_silently` trap where both looked like the same
empty result downstream.

### Methods

```python
async def run(
    self,
    payload: collections.abc.Sequence[weft_extract.contract.SourceDoc],
    ctx: weft_kernel.context.Context,
) -> weft_kernel.payload.outcome.Outcome[
    collections.abc.Sequence[weft_kernel.payload.node.Node]
]: ...
```

## `Fuser`

**Module:** `weft_retrieve.contract`  
**Registered by:** `weft-retrieve`  
**Version:** `1.0.0`

Collapses k ranked lists into one. The arity-reducing position, by definition.

`Out` being `Ranking` rather than `Candidates` is the load-bearing choice in this
module: **fan-in is expressed in the type, not by a combinator.** It is also what
discharges ledger 2.18 with a single implementation — hybrid retrieval and query
fan-out are the same shape here, because multiplicity is uniform in `Candidates`.

### Methods

```python
async def run(
    self, payload: weft_retrieve.payload.Candidates, ctx: weft_kernel.context.Context
) -> weft_kernel.payload.outcome.Outcome[weft_retrieve.payload.Ranking]: ...
```

## `Generator`

**Module:** `weft_generate.contract`  
**Registered by:** `weft-generate`  
**Version:** `1.0.0`

Turns packed, labelled evidence into an answer that cites it.

Taking `Passages` rather than a `Ranking` is what makes task 2.9 mechanical: the
citation labels are already assigned and final by the time a generator sees them, so
`Answer`'s own validator can refuse a marker that resolves to nothing. A generator
that decides the evidence does not answer the question returns
`Answer(stance=NOT_IN_CORPUS)` — `Produced`, with an honest claim inside it — never
`NothingToProduce`, which would stop the pipeline and leave the caller with no answer
at all where `09` §4's V2 requires one.

### Methods

```python
async def run(
    self, payload: weft_retrieve.payload.Passages, ctx: weft_kernel.context.Context
) -> weft_kernel.payload.outcome.Outcome[weft_generate.payload.Answer]: ...
```

## `LLMProvider`

**Module:** `weft_llm.contract`  
**Registered by:** `weft-llm`, `weft-openai`  
**Version:** `1.0.0`

One vendor's (or one deterministic offline) answer to "continue this conversation".

`complete` returns a decided `Outcome` — `Produced`, never left to a caller draining a
stream to find out whether the call succeeded (`01` → *Colour*, G6). `stream` is always
called by the `LLM` service regardless of whether a caller asked to see tokens as they
arrive (`.phase2-design.md` decision 10: streaming attaches at the client, so a provider
that forgets to implement it faithfully cannot exist as a second, diverging code path).
`close` releases whatever connection the provider opened; a provider that opens none
still implements it, returning immediately, the same shape `Stage` implementations with
nothing to flush already take for `flush`.

### Methods

```python
async def close(self) -> None: ...
```

```python
async def complete(
    self, conv: weft_llm.payload.Conversation, *, model: str, ctx: weft_kernel.context.Context
) -> weft_kernel.payload.outcome.Outcome[weft_llm.payload.Completion]: ...
```

```python
async def stream(
    self, conv: weft_llm.payload.Conversation, *, model: str, ctx: weft_kernel.context.Context
) -> collections.abc.AsyncIterator[str]: ...
```

## `MetadataFilter`

**Module:** `weft_store.contract`  
**Registered by:** `weft-qdrant`, `weft-store`  
**Version:** `1.2.0`

A store that can evaluate a whole `Filter` against what it holds.

The fourth tier, published at task **2.6** — one task later than `02` §1
scheduled it, and for the reason that task exists. Specified there as a bare
marker (`class MetadataFilter(Protocol): ...`), it could not be published as
written: a `@runtime_checkable` Protocol with an empty body has an empty
`__protocol_attrs__`, so `isinstance(42, MetadataFilter)` is `True` and the
capability would be one every store advertises and none implements. It needs
a member that *is* the capability, and `02` names the shape that member must
have — "an entry point taking a `Filter` and nothing else".

`matching` is that entry point. No vector, no text, no `top_k`: the filter
alone decides membership, which is what makes this capability separable from
the two search tiers rather than a footnote on them. `cursor` is not a second
query dimension — it is the same paging vocabulary `NodeStore.scan` already
uses, because a predicate over a corpus can select more of it than one answer
should carry.

**What a store promises by having it.** Every operator in `FilterOp`, over
every path `weft_store.fields` says a `Filter` may name, with the meanings
that module states — and, since a store that can evaluate a filter has no
excuse for ignoring one, `filter` honoured on whichever of `search_vector`
and `search_text` the same store also has. A store that translates only some
of the operator set does not implement this Protocol and must not carry
`matching`: half a filter language silently applied is the failure `01`
requirement 5 exists to forbid, and refusing the whole call is the honest
alternative.

**Order is not promised, pages are.** `matching` and `scan` both walk
whatever key the backend orders by — a content digest in Postgres, a UUID in
Qdrant — and a caller that needs a ranking is asking a search capability, not
this one.

Not a `Stage`: nothing in an ingest pipeline filters, so it carries no `run`
and stays a pure capability Protocol, the same shape as its two siblings.

### Methods

```python
async def matching(
    self, filter: weft_store.contract.Filter, cursor: weft_store.contract.Cursor | None = None
) -> weft_store.contract.Page[weft_kernel.payload.node.Node]: ...
```

## `NativeStructured`

**Module:** `weft_llm.contract`  
**Registered by:** —  
**Version:** `1.0.0`

A provider that will answer *in a schema*, checked by the vendor rather than by us.

**A derived capability sibling, never a declared one** — `.phase2-design.md` §3: "tier 1
is available iff `isinstance(provider, NativeStructured)`. That replaces the reference's
`hasattr(self.llm, "structured_predict")` guard with capability derived at registration,
and it means a provider that lies about structured output cannot exist — it either has
the method or it does not." The same pattern `weft-store` uses for `VectorSearch` and
`TextSearch`, applied to the one branch of the cascade that can skip two tiers of work.

Nothing registers *under* this contract: a provider registers under `LLMProvider` and is
found to satisfy this one, which is what makes the capability underivable from a claim.

### Methods

```python
async def complete_structured(
    self,
    conv: weft_llm.payload.Conversation,
    schema: collections.abc.Mapping[str, object],
    *,
    model: str,
    ctx: weft_kernel.context.Context,
) -> weft_kernel.payload.outcome.Outcome[weft_llm.payload.Completion]: ...
```

## `NodeStore`

**Module:** `weft_store.contract`  
**Registered by:** `weft-qdrant`, `weft-store`  
**Version:** `1.2.0`

The base every store implements all of — see the module docstring for `run`.

`docs/02-extension-model.md` → *The store contract family*, verbatim for
the eight capability methods below `run`; see that section for what each
one is for and why (durability as a guarantee rather than a `persist()`
call, deletion as idempotent-and-resumable rather than atomic, and the
rest).

### Methods

```python
async def add(self, nodes: collections.abc.Sequence[weft_kernel.payload.node.Node]) -> None: ...
```

```python
async def count(self) -> int: ...
```

```python
async def delete_source(
    self, source_id: weft_kernel.payload.ids.SourceId
) -> weft_store.contract.Removed: ...
```

```python
async def flush(self) -> None: ...
```

```python
async def get(
    self, ids: collections.abc.Sequence[weft_kernel.payload.ids.NodeId]
) -> collections.abc.Sequence[weft_kernel.payload.node.Node]: ...
```

```python
async def get_source(
    self, source_id: weft_kernel.payload.ids.SourceId
) -> weft_store.contract.SourceRecord | None: ...
```

```python
async def list_sources(self) -> collections.abc.Sequence[weft_store.contract.SourceRecord]: ...
```

```python
async def put_source(self, record: weft_store.contract.SourceRecord) -> None: ...
```

```python
async def run(
    self,
    payload: collections.abc.Sequence[weft_kernel.payload.node.Node],
    ctx: weft_kernel.context.Context,
) -> weft_kernel.payload.outcome.Outcome[
    collections.abc.Sequence[weft_kernel.payload.node.Node]
]: ...
```

```python
async def scan(
    self, cursor: weft_store.contract.Cursor | None = None
) -> weft_store.contract.Page[weft_kernel.payload.node.Node]: ...
```

## `Prompt`

**Module:** `weft_prompts.contract`  
**Registered by:** `weft-generate`, `weft-index`, `weft-retrieve`  
**Version:** `1.0.0`

One named, versioned, translatable question a model can be asked.

`render` returns a decided `Outcome[Rendered]`, so a prompt that legitimately has nothing
to ask (an evidence-free rerank, say) answers `NothingToProduce` rather than an empty
conversation a provider would then be sent.

### Declared attributes

```python
input_model: typing.ClassVar[type[pydantic.main.BaseModel]]
```

```python
output_model: typing.ClassVar[type[pydantic.main.BaseModel] | None]
```

### Methods

```python
async def render(
    self, values: pydantic.main.BaseModel, ctx: weft_kernel.context.Context
) -> weft_kernel.payload.outcome.Outcome[weft_llm.payload.Rendered]: ...
```

## `QueryScorer`

**Module:** `weft_retrieve.contract`  
**Registered by:** `weft-retrieve`  
**Version:** `1.0.0`

Measures a query along named dimensions. Decides nothing (ledger 2.25).

Two contracts rather than one so a threshold ladder can be replaced by a trained
classifier without touching the measurement, and so the router is two ordinary stages
in an ordinary pipeline rather than an engine — `02` §3, "express the router as a
stage rather than as an engine."

### Methods

```python
async def run(
    self, payload: weft_retrieve.payload.Query, ctx: weft_kernel.context.Context
) -> weft_kernel.payload.outcome.Outcome[weft_retrieve.payload.Scorecard]: ...
```

## `QueryTransform`

**Module:** `weft_retrieve.contract`  
**Registered by:** `weft-retrieve`  
**Version:** `1.0.0`

Rewrites, expands or narrows the set of queries that will be retrieved for.

`Stage[QuerySet, QuerySet]` is what makes a transform omittable by construction
(ledger 2.15): removing it from a document leaves the seams either side composing
unchanged, so no strategy pays for a rewrite it did not ask for. It also makes two
transforms composable in either order, which is how `hyde` then `multi-query` becomes
a document edit rather than a new plugin.

A transform must not rewrite `QuerySet.origin` — see that field's own docstring for
the reference defect the invariant closes.

### Methods

```python
async def run(
    self, payload: weft_retrieve.payload.QuerySet, ctx: weft_kernel.context.Context
) -> weft_kernel.payload.outcome.Outcome[weft_retrieve.payload.QuerySet]: ...
```

## `Renderer`

**Module:** `weft_extract.contract`  
**Registered by:** `weft-extract`  
**Version:** `1.0.0`

Turns nodes into one rendered document in a named format.

`.phase2-design.md` A.2, assigned to ledger 2.27 by A.4's consequences
table: 2.27's exit demonstration is that an operator's PDF becomes
readable, and an operator who cannot get the parse back out in a format
they can read has not been given that.

**Not a `Node` transformation**, which is why `Out` is `Rendition` and not
`Sequence[Node]`: the output leaves the pipeline for a human or another
system. It is an ordinary `Stage` terminus, so the kernel's existing
composition check covers it and **G5 is untouched** — nothing about `Node`
changes and no new payload kind travels inside a pipeline.

**Why this is published here rather than by the kernel, and why it is one
contract rather than a `format:` field.** A `to_markdown()` on `Node` would
put a format in the kernel, which G1 forbids outright. A single renderer
plugin taking `format="markdown"` would be a closed key space with a branch
behind it — finding 9's `if backend == ...` defect with the word changed —
and requirement 4 would break the first time a third party wanted `docx`.
One contract, one registration per format: a `docx` renderer is a
distribution and zero edits to anything here.

`version` is declared the same way `Extractor`'s is, and for the same
reason — see this module's docstring on `__protocol_attrs__`.

### Methods

```python
async def run(
    self,
    payload: collections.abc.Sequence[weft_kernel.payload.node.Node],
    ctx: weft_kernel.context.Context,
) -> weft_kernel.payload.outcome.Outcome[weft_extract.payload.Rendition]: ...
```

## `Reranker`

**Module:** `weft_retrieve.contract`  
**Registered by:** `weft-retrieve`  
**Version:** `1.0.0`

Rescores one list against the question, and returns one list.

Separate from `Fuser` (ledger 2.7: "not a fixed ladder") so that either can be
retuned, replaced or omitted in a document without touching the other. Same in and
out, so a second reranker composes after the first with no new type and no operator.

### Methods

```python
async def run(
    self, payload: weft_retrieve.payload.Ranking, ctx: weft_kernel.context.Context
) -> weft_kernel.payload.outcome.Outcome[weft_retrieve.payload.Ranking]: ...
```

## `Retriever`

**Module:** `weft_retrieve.contract`  
**Registered by:** `weft-retrieve`  
**Version:** `1.0.0`

Turns queries into ranked lists — one per query per channel, never fused.

**A retriever never builds its own index** (ledger 2.5): text and vector search are
things a store *advertises*, reached through `ctx.require(...)` and declared by a
`needs_store: ClassVar[tuple[type, ...]]` class attribute the run assembler checks
before any stage runs. `docs/02-extension-model.md` §1 → *The store contract family*
is the owning text, narrowed in this task to say where the check happens.

Producing `Candidates` rather than one list is the whole fan-out mechanism: k lists
with the `Query` and `Channel` that produced each, so a fuser has something to weight
and so hybrid retrieval and query fan-out arrive at the fuser in the same shape.

### Methods

```python
async def run(
    self, payload: weft_retrieve.payload.QuerySet, ctx: weft_kernel.context.Context
) -> weft_kernel.payload.outcome.Outcome[weft_retrieve.payload.Candidates]: ...
```

## `RoutingPolicy`

**Module:** `weft_retrieve.contract`  
**Registered by:** `weft-retrieve`  
**Version:** `1.0.0`

Turns a scorecard into a named pipeline. The second half of the router.

`reachable` is deliberately not a `Stage` method — it answers "which of these
candidates could this policy ever choose?" for `weft plugins doctor` and for the
registered-but-unroutable check, which is data the caller already holds rather than a
payload flowing down a pipeline. It is nonetheless `async`, like everything else here:
`01` → *Colour*, settled in **G6**, is categorical — "every contract method is
`async def`. There is no sync protocol" — and this is a published contract a third
party implements, not a service. `weft_kernel.seam.wrap` wraps a coroutine, so a sync
method on a registered contract would run outside the seam: no span, no error
attribution, and nothing for FF7(b)'s blocking-call detector to see. A
`nearest-description` policy whose `reachable` reads a file or calls an embedding
endpoint would then block the loop thread with the gate unable to notice, which is the
concern that made G6 categorical in the first place. `.phase2-design.md` §3 calls this
method "deliberately sync"; that file's own status line says `docs/` wins where they
disagree, and this is where they did.

### Methods

```python
async def reachable(
    self, candidates: collections.abc.Sequence[weft_retrieve.payload.RouteCandidate]
) -> frozenset[str]: ...
```

```python
async def run(
    self, payload: weft_retrieve.payload.Scorecard, ctx: weft_kernel.context.Context
) -> weft_kernel.payload.outcome.Outcome[weft_retrieve.payload.Route]: ...
```

## `Sufficiency`

**Module:** `weft_retrieve.contract`  
**Registered by:** `weft-retrieve`  
**Version:** `1.0.0`

Judges whether the evidence in hand answers the question. **Not a pipeline position.**

Declares no `Stage[In, Out]` base, on purpose: it takes three arguments, not one
payload, and it is reached *inside* a looping technique by name through `StageLookup`
rather than placed in a document. Ledger 2.24 wants the uncertainty signal to be a
replaceable named thing rather than a phrase list buried in a generator, and a named
contract with two implementations is what "replaceable" means here.

An implementation that could not look answers `Assessment(observed=False)`. It must
never answer `sufficient=False` to mean "I could not tell" — see `Assessment`.

### Methods

```python
async def assess(
    self,
    question: weft_retrieve.payload.Query,
    evidence: weft_retrieve.payload.Passages,
    draft: str | None,
    ctx: weft_kernel.context.Context,
) -> weft_kernel.payload.outcome.Outcome[weft_retrieve.payload.Assessment]: ...
```

## `TextSearch`

**Module:** `weft_store.contract`  
**Registered by:** `weft-store`  
**Version:** `1.2.0`

A store that can rank `Node`s by lexical match on their own text.

The sibling of `VectorSearch`, and the reason `02` insists the two are
separate Protocols: "stores never embed. `VectorSearch` takes a vector,
`TextSearch` takes text; a store is therefore not coupled to a model."
A store may satisfy both, either or neither, and which it is comes out of
`isinstance` rather than out of anything a store author writes down.

**This is the capability a retriever asks for instead of building.** A
lexical arm implemented inside a retrieval plugin is a second index over
the corpus — one the store's own writes never reach, so it is stale from
the first `add()` and there is nothing in the pipeline to make it fresh
again. A retriever that wants a text channel therefore declares it needs
this capability and is refused, by name, against a store that does not
advertise it (task 2.5; `docs/02-extension-model.md` §1 → *Retrievers
declare what they need*). Nothing here adapts or degrades: a run that
wanted a text channel does not quietly become vector-only.

**An empty ranking is a result, not a failure.** A store whose index holds
nothing matching returns an empty sequence; that is the honest answer to
"what matches these words", and it is a different fact from a store that
could not look, which raises.

Not a `Stage`: nothing in an ingest pipeline calls `search_text`, so it
carries no `run` and stays a pure capability Protocol, checked with
`isinstance` against whatever instance `NodeStore` resolved — the same
shape as `VectorSearch`, for the same reason.

### Methods

```python
async def search_text(
    self, text: str, top_k: int, filter: weft_store.contract.Filter | None = None
) -> collections.abc.Sequence[weft_store.contract.Scored[weft_kernel.payload.node.Node]]: ...
```

## `VectorSearch`

**Module:** `weft_store.contract`  
**Registered by:** `weft-qdrant`, `weft-store`  
**Version:** `1.2.0`

A store that can rank `Node`s by vector similarity. Never embeds — `02`: "stores never
embed. `VectorSearch` takes a vector, `TextSearch` takes text; a store is therefore not
coupled to a model." Not a `Stage`: nothing in an ingest pipeline calls `search_vector`, and
a future `Retriever` (Phase 2) resolves this capability directly against the configured
store rather than through the runner's stage machinery.

### Methods

```python
async def search_vector(
    self,
    vector: weft_kernel.payload.vector.Vector,
    top_k: int,
    filter: weft_store.contract.Filter | None = None,
) -> collections.abc.Sequence[weft_store.contract.Scored[weft_kernel.payload.node.Node]]: ...
```
