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

## `BlobStore`

**Module:** `weft_blob.contract`  
**Registered by:** `weft-rag`  
**Version:** `1.0.0`

Store bytes under a caller-composed key, read them back by uri, and reap a prefix.

Puts bytes under a caller-composed key, opens them back by the returned uri, and reaps a
prefix on delete. Three methods, and every one of them the whole surface a plugin owes.

**`put` takes a plain `str` key, not a `weft_blob.keys.BlobUri` or a `SourceId`-shaped
argument** — the module publishing this contract has no opinion on how a key is derived;
`weft_blob.keys` is one caller's answer, not part of the capability. A caller composing its
own key is exactly the case `weft_blob.filesystem_store`'s own boundary check exists for.

**`media_type` on `put` and nowhere else.** `open` returns the bytes a caller already knows
the shape of — the `BlobRef.media_type` field carries that fact durably — so the contract
does not ask a store to remember or return it a second time.

### Methods

```python
async def delete_prefix(self, prefix: str) -> int: ...
```

Delete every blob whose key lies under `prefix`.

Args:
    prefix: The key prefix to reap.

Returns:
    How many blobs were deleted.

```python
async def open(self, uri: weft_blob.contract.BlobUri) -> bytes: ...
```

Read back the bytes a `put` stored.

Args:
    uri: A uri this store returned from `put`.

Returns:
    The stored bytes.

```python
async def put(self, key: str, data: bytes, media_type: str) -> weft_blob.contract.BlobUri: ...
```

Store `data` under `key`.

Args:
    key: The caller-composed key the bytes are stored under.
    data: The bytes to store.
    media_type: What the bytes are; recorded by the caller's `BlobRef`, not returned.

Returns:
    The uri `open` reads the bytes back by.

## `Chunker`

**Module:** `weft_chunk.contract`  
**Registered by:** `weft-rag`  
**Version:** `1.0.0`

Splits `Node`s into smaller `Node`s, each one a child under `Node.derive`.

One method, domain types on both sides, exactly `Extractor`'s shape one
stage later in the pipeline. A chunker that finds nothing to split
answers `NothingToProduce`, not an empty `Produced([])` — the same fix
`weft_extract.contract.Extractor` documents for collapsing a legitimately
empty result into the same ambiguous case as a failure, applied here
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

Split each node in `payload` into child chunks.

Args:
    payload: The nodes to split.
    ctx: The run's context.

Returns:
    `Produced` carrying the chunks, or `NothingToProduce` when there were none.

## `Cleaner`

**Module:** `weft_clean.contract`  
**Registered by:** `weft-rag`  
**Version:** `1.0.0`

Repairs or normalises a `Node`'s text, one node in, one repaired node out.

A cleaning stage's job is narrower than a chunker's: it never splits or
merges nodes, so every implementation returns exactly as many nodes as it
was handed, each built through `Node.derive` so lineage records the
repair as its own step. A batch with nothing to clean still answers
`NothingToProduce`, never a silently empty `Produced([])` — the same fix
`weft_extract.contract.Extractor` and `weft_chunk.contract.Chunker`
already document for collapsing a legitimately empty result into the
same ambiguous case as a failure, applied here because the same
ambiguity is possible at every stage returning a sequence.

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

Clean each node in `payload`, returning the cleaned nodes.

Args:
    payload: The nodes to clean.
    ctx: The run's context.

Returns:
    `Produced` carrying the cleaned nodes, or `NothingToProduce` when there were none.

## `Command`

**Module:** `weft_command.contract`  
**Registered by:** `weft-rag`  
**Version:** `2.1.0`

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

Execute the command.

Args:
    args: An instance of this command's `args_model`.
    ctx: The run's context.

Returns:
    The command's `Outcome`, carrying a `result_model` instance when it produced one.

## `ContextPacker`

**Module:** `weft_retrieve.contract`  
**Registered by:** `weft-rag`  
**Version:** `1.1.0`

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

Choose and order the passages a generator is shown.

Args:
    payload: The final ranking.
    ctx: The run's context.

Returns:
    The packed passages.

## `Describer`

**Module:** `weft_vision.contract`  
**Registered by:** `weft-rag`  
**Version:** `1.0.0`

Says what an image (or, later, some other medium) contains, in words.

`data` is the bytes themselves and `media_type` is the IANA type that says how to read them —
a plain `str` for the reason `weft_extract.payload.Rendition.media_type` gives: the IANA set is
open by construction, and a closed enum here would need a member added in a distribution a
third party does not own.

`instruction` is what the caller wants said. It is an argument rather than plugin
configuration because two stages consume this contract for different purposes — an index-time
describer wants a retrieval-shaped description, a query-side one wants the user's own question
answered about the image — and a prompt fixed at registration could serve only one of them.

### Methods

```python
async def describe(
    self, data: bytes, media_type: str, instruction: str
) -> weft_kernel.payload.outcome.Outcome[str]: ...
```

Say in words what `data` contains, as `instruction` asks.

Args:
    data: The bytes to describe.
    media_type: The IANA type saying how to read `data`.
    instruction: What the caller wants said.

Returns:
    `Produced` carrying the description, or `NothingToProduce`/`Failed`.

## `Embedder`

**Module:** `weft_embed.contract`  
**Registered by:** `weft-rag`  
**Version:** `1.1.0`

Attaches an embedding to each `Node` it is handed.

One method, domain types on both sides, exactly `Chunker`'s shape one
stage later in the pipeline. An embedder that finds nothing to embed
(an empty batch) answers `NothingToProduce`, not an empty `Produced([])`
— the same fix every other Phase 0 contract documents for collapsing a
legitimately empty result into the same ambiguous case as a failure.

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

Attach an embedding to each node in `payload`.

Args:
    payload: The nodes to embed.
    ctx: The run's context.

Returns:
    `Produced` carrying the embedded nodes, or `NothingToProduce` when there were none.

## `Enhancer`

**Module:** `weft_enhance.contract`  
**Registered by:** `weft-rag`  
**Version:** `1.0.0`

Attaches a new, namespaced fact to each `Node` it is handed — never rewrites `content`.

One method, domain types on both sides, exactly `Cleaner`'s shape with a different
job: where a `Cleaner` returns a *repaired* node built through `Node.derive`, an
`Enhancer` returns the *same* node with an added `Node.with_ext` fact — identity
(`node.id`) is unaffected, because nothing about the text changed. A batch with
nothing to enhance still answers `NothingToProduce`, never a silently empty
`Produced([])` — the same fix every other contract in this tree documents for
collapsing a legitimately empty result into the same ambiguous case as a failure.

`layer_stage = True` (R43.16): this contract's publisher promises that a stage under it
takes nodes already stored and returns every node it was handed, each under its own id,
plus whatever it derived from them — it neither embeds nor stores.

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

Attach facts to each node in `payload`, keeping every node's identity.

Args:
    payload: The nodes to enhance.
    ctx: The run's context.

Returns:
    `Produced` carrying every node it was handed plus anything derived from them, or
    `NothingToProduce` when there was nothing to enhance.

## `Expander`

**Module:** `weft_index.contract`  
**Registered by:** `weft-rag`  
**Version:** `1.1.0`

Every node handed in, unchanged, plus zero or more nodes derived from it.

A batch with nothing to expand still answers `NothingToProduce`, never a silently
empty `Produced([])` — the same ambiguous-empty-case fix every other contract in this
tree documents. A single node this plugin could not generate a representation for is not
that case: the node itself is still in the output, under its own id, and only its own
representations are missing — degrade, never fail the run, the same posture `10` §1.2's
`raptor` row (task 2.32) states for a summary that cannot be produced, because both
techniques are meant to share this one mechanism rather than invent their own failure
policy apiece. Since repair **R38.13**, and repair **R38.18** for every shipped
`Expander` rather than `hypothetical-questions` alone, that node also carries
`weft_index.payload.ExpansionDegraded`, naming which expander could not expand it and
why.

`layer_stage = True` (R43.16): this contract's publisher promises that a stage under it
takes nodes already stored and returns every node it was handed, each under its own id,
plus whatever it derived from them. It stores nothing except through a `LayerCheckpoints`
it was handed (task 43.20), into a generation no reader sees until it is published. It
may embed what it derives — `raptor` does, through `ctx.require(Embedder)`.

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

Return every node handed in, plus whatever this stage derived from them.

Args:
    payload: The nodes to expand or revise.
    ctx: The run's context, through which services such as an `Embedder` are reached.

Returns:
    The handed nodes and the derived ones, or `NothingToProduce`/`Failed`.

## `Extractor`

**Module:** `weft_extract.contract`  
**Registered by:** `weft-rag`  
**Version:** `1.0.0`

Turns source documents into the first `Node`s of an ingest pipeline.

One method, domain types on both sides — `docs/02-extension-model.md`
section 1 names a `BaseExtractor`-shaped interface as the shape this
contract follows, one `@abstractmethod extract(...)`, and the
failure to fix was only ever its dispatch, never its narrowness. The
shape is reused; nothing else about it is. `run` is that method,
async per G6, returning `Outcome` rather than a bare value or an
envelope with an ambiguous empty case: a source that legitimately yields
no text answers `NothingToProduce`, distinct from `Failed`, which avoids
a `fail_silently`-shaped trap where both would look like the same
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

Turn source documents into root nodes.

Args:
    payload: The source documents to extract.
    ctx: The run's context.

Returns:
    `Produced` carrying the nodes, `NothingToProduce` when the sources held no text, or
    `Failed`.

## `Fuser`

**Module:** `weft_retrieve.contract`  
**Registered by:** `weft-rag`  
**Version:** `1.1.0`

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

Merge the retrieved lists into one ranking.

Args:
    payload: The ranked lists to merge.
    ctx: The run's context.

Returns:
    The one merged ranking.

## `GenerationCarrying`

**Module:** `weft_store.contract`  
**Registered by:** `weft-rag`  
**Version:** `2.14.0`

A store that carries a published generation's untouched members into a new one.

A store that carries a published generation's untouched members into a new one — ledger
task **43.22**.

`carry_forward` adds `into` to each node's generation membership and changes nothing else
about it: no rewrite, no re-embedding. Publishing `into` and retracting the generation it
replaces then keeps every carried node and drops every node `into` left out. Repeated ids
count once; the return is the number of distinct nodes carried. An unknown `into` raises
`UnknownGenerationError`; an id no published generation holds raises
`NotAPublishedMemberError` naming every such id, and nothing in that call is carried. A
separate Protocol rather than a method on `GenerationHolding`, `NodeSupersedable`'s
precedent: `09`'s table makes a method added to a Protocol a major for its implementers.

### Methods

```python
async def carry_forward(
    self,
    into: weft_store.contract.GenerationId,
    node_ids: collections.abc.Sequence[weft_kernel.payload.ids.NodeId],
) -> int: ...
```

Make published members of an earlier generation members of `into` too.

Args:
    into: The generation the nodes join.
    node_ids: The nodes to carry; repeated ids count once.

Returns:
    The number of distinct nodes carried.

Raises:
    UnknownGenerationError: The store holds no generation `into`.
    NotAPublishedMemberError: An id is held by no published generation.

## `GenerationHolding`

**Module:** `weft_store.contract`  
**Registered by:** `weft-rag`  
**Version:** `2.14.0`

A store that builds a corpus-scoped layer as a generation, published whole.

A store that builds a corpus-scoped layer as a generation, published whole — ledger task
**43.14**.

A node written through `bind_generation`'s handle is a member of that generation, and every
search (`search_vector`, `search_text`, `matching`) leaves out members of a generation the
reading handle cannot see, **before** top-k. A handle sees the generations published when it
first touches storage, plus the one it is bound to, and keeps that set for its lifetime, so one
operation never mixes two trees (`TargetHolding`'s Q-C, applied again). Of those published, a
handle sees each layer's newest published generation, by `published_at` (repair **R43.25**),
so a reader opened between a publish and the retract after it sees one tree. A node no
generation wrote is always visible, and a node two generations wrote is visible when either is.
`retract_generation` removes the nodes only that generation made and forgets it.

### Methods

```python
async def bind_generation(self, generation: weft_store.contract.GenerationId) -> typing.Self: ...
```

Open a second handle whose writes join `generation`.

Args:
    generation: The generation the new handle writes into.

Returns:
    The bound handle.

Raises:
    UnknownGenerationError: The store holds no such generation.

```python
async def generations(self) -> tuple[weft_store.contract.GenerationRecord, Ellipsis]: ...
```

Read every generation this store's catalogue holds.

Returns:
    Every generation record, oldest first.

```python
async def open_generation(self, layer: str) -> weft_store.contract.GenerationRecord: ...
```

Open a new, unpublished generation of `layer`.

Args:
    layer: The layer the generation builds.

Returns:
    The generation's record, `building`.

```python
async def publish_generation(
    self, generation: weft_store.contract.GenerationId
) -> weft_store.contract.GenerationRecord: ...
```

Make `generation` visible to handles that open afterwards.

Args:
    generation: The generation to publish.

Returns:
    The generation's record, `published`.

Raises:
    UnknownGenerationError: The store holds no such generation.

```python
async def retract_generation(
    self, generation: weft_store.contract.GenerationId
) -> weft_store.contract.Removed: ...
```

Remove the nodes only `generation` made, and forget it.

Args:
    generation: The generation to retract.

Returns:
    How many nodes were deleted.

Raises:
    UnknownGenerationError: The store holds no such generation.

## `GenerationMetric`

**Module:** `weft_eval.contract`  
**Registered by:** `weft-rag`  
**Version:** `1.0.0`

Scores one `GenerationSample` — a prediction against a reference (and, sometimes, context).

`evaluate` is `async def` unconditionally (G6) and returns `Outcome[MetricScore]`: a score
(`Produced`), a legitimate absence of anything to score (`NothingToProduce`), or a failure
(`Failed`) — see `weft_eval.contract`'s module docstring for the full reasoning.

### Methods

```python
async def evaluate(
    self, payload: weft_eval.contract.GenerationSample, ctx: weft_kernel.context.Context
) -> weft_kernel.payload.outcome.Outcome[weft_eval.contract.MetricScore]: ...
```

Score one generation sample.

Args:
    payload: The question, the prediction and the reference to score.
    ctx: The run's context, through which a metric reaches any service it needs.

Returns:
    The score, or the outcome naming why none could be produced.

## `GenerationWithdrawing`

**Module:** `weft_store.contract`  
**Registered by:** `weft-rag`  
**Version:** `2.14.0`

A store that withdraws a superseded generation now and reclaims its nodes later.

A store that withdraws a superseded generation now and reclaims its nodes later — repair
**R43.29**.

`withdraw_generation` marks a published generation `WITHDRAWN` and touches no node and no
membership, so it leaves the manifest of every handle that opens afterwards while a handle
that opened before keeps reading the tree it opened on. An unknown id raises
`UnknownGenerationError`; a `building` or `withdrawn` one raises `NotAPublishedGenerationError`.
`reclaim_withdrawn(layer)` does what `retract_generation` does for every withdrawn generation of
`layer`, and nothing to any other layer. A separate Protocol, `GenerationCarrying`'s precedent.

### Methods

```python
async def reclaim_withdrawn(self, layer: str) -> weft_store.contract.Removed: ...
```

Retract every withdrawn generation of `layer`.

Args:
    layer: The layer whose withdrawn generations are reclaimed.

Returns:
    How many nodes were deleted.

```python
async def withdraw_generation(
    self, generation: weft_store.contract.GenerationId
) -> weft_store.contract.GenerationRecord: ...
```

Mark a published `generation` withdrawn, touching no node.

Args:
    generation: The generation to withdraw.

Returns:
    The generation's record, `withdrawn`.

Raises:
    UnknownGenerationError: The store holds no such generation.
    NotAPublishedGenerationError: The generation is not published.

## `Generator`

**Module:** `weft_generate.contract`  
**Registered by:** `weft-rag`  
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

Answer `payload.origin` from the labelled passages, citing them by label.

Args:
    payload: The packed, labelled evidence and the question it was retrieved for.
    ctx: The run's context, which supplies the `LLM` and the other services.

Returns:
    The answer — `Answer(stance=NOT_IN_CORPUS)` where the evidence does not answer
    the question, never `NothingToProduce`.

## `GraphTraversal`

**Module:** `weft_kg.contract`  
**Registered by:** `weft-rag`  
**Version:** `2.0.0`

A bounded walk over resolved entities and the nodes and neighbours around them.

Not a `Stage` — see the module docstring. Reached through `ctx.require`, never run as a
pipeline rung, so it carries no `run` and no `Stage[In, Out]` base.

Three members, every one `async def` and every one at batch granularity: a caller asking about
several names, several entity ids, or several hops gets one answer for all of them, never one
round trip per element. Ranking entities by a vector is `EntityVectorSearch`'s, below — a
capability a graph backend may or may not also have, never a member this one requires.

### Methods

```python
async def entities_by_name(
    self, names: collections.abc.Sequence[str]
) -> tuple[weft_kg.contract.Entity, Ellipsis]: ...
```

Resolve surface forms to the distinct canonical entities they currently name.

Args:
    names: The surface forms to look up.

Returns:
    Each distinct entity any of `names` resolves to; a name that resolves to nothing
    contributes nothing.

```python
async def neighbourhood(
    self, entity_ids: collections.abc.Sequence[weft_kg.contract.EntityId], *, hops: int
) -> collections.abc.Mapping[
    weft_kg.contract.EntityId, tuple[weft_kg.contract.Entity, Ellipsis]
]: ...
```

Every entity reachable from each seed within `hops` relation edges.

Args:
    entity_ids: The seeds to walk from.
    hops: The most relation edges a walk may cross.

Returns:
    Each seed mapped to the entities within reach of it, the seed itself excluded.

```python
async def nodes_for_entities(
    self, entity_ids: collections.abc.Sequence[weft_kg.contract.EntityId]
) -> collections.abc.Mapping[
    weft_kg.contract.EntityId, tuple[weft_kernel.payload.ids.NodeId, Ellipsis]
]: ...
```

Map each held entity to the nodes that mention it.

Args:
    entity_ids: The entities to look up.

Returns:
    One key per requested id this backend holds — an id it does not hold is absent,
    never a key mapping to `()`.

## `IdentifiedEmbedder`

**Module:** `weft_embed.contract`  
**Registered by:** `weft-rag`  
**Version:** `1.1.0`

An embedder that can state what it embeds with.

An embedder that can state what it embeds with — one member, `NodeSupersedable`'s
shape (`weft_store.contract`), for the same reason: growing `Embedder` itself would be a
major for every third-party implementer, for a capability most already have and a
stranger with no declared model does not.

### Methods

```python
async def embedding_model(self) -> weft_embed.contract.EmbeddingModel: ...
```

Report the model and width this embedder's requests actually use.

Returns:
    The model name and, when the embedder fixes it, the vector width.

## `LLMProvider`

**Module:** `weft_llm.contract`  
**Registered by:** `weft-rag`  
**Version:** `1.1.0`

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

Release whatever connection the provider opened; return at once if it opened none.

```python
async def complete(
    self, conv: weft_llm.payload.Conversation, *, model: str, ctx: weft_kernel.context.Context
) -> weft_kernel.payload.outcome.Outcome[weft_llm.payload.Completion]: ...
```

Continue `conv` in one call, decided when it returns.

Args:
    conv: The conversation to continue.
    model: The model to answer under; one provider instance serves many.
    ctx: The run's context.

Returns:
    The answer, or `NothingToProduce` where the model produced none.

Raises:
    LLMError: The provider's failure, as one leaf of `weft_llm.errors`.

```python
async def stream(
    self, conv: weft_llm.payload.Conversation, *, model: str, ctx: weft_kernel.context.Context
) -> collections.abc.AsyncIterator[str]: ...
```

Continue `conv`, yielding the answer's text as it arrives.

Args:
    conv: The conversation to continue.
    model: The model to answer under; one provider instance serves many.
    ctx: The run's context.

Yields:
    Each fragment of the answer's text, in order.

Raises:
    LLMError: The provider's failure, as one leaf of `weft_llm.errors`.

## `MetadataFilter`

**Module:** `weft_store.contract`  
**Registered by:** `weft-rag`  
**Version:** `2.14.0`

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

Walk every stored node `filter` selects, one page at a time.

Args:
    filter: The predicate that alone decides membership.
    cursor: Where the previous page ended, or `None` for the first page.

Returns:
    One page of matching nodes and the cursor for the next, if any.

## `NativeStructured`

**Module:** `weft_llm.contract`  
**Registered by:** —  
**Version:** `1.1.0`

A provider that will answer *in a schema*, checked by the vendor rather than by us.

**A derived capability sibling, never a declared one** — `.phase2-design.md` §3: "tier 1
is available iff `isinstance(provider, NativeStructured)`. That replaces a
`hasattr(self.llm, "structured_predict")` guess with capability derived at registration,
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

Continue `conv` with an answer the vendor itself constrains to `schema`.

Args:
    conv: The conversation to continue.
    schema: The JSON schema the answer must satisfy.
    model: The model to answer under.
    ctx: The run's context.

Returns:
    The answer, whose text is a document in `schema`.

Raises:
    LLMError: The provider's failure, as one leaf of `weft_llm.errors`.

## `NodeStore`

**Module:** `weft_store.contract`  
**Registered by:** `weft-rag`  
**Version:** `2.14.0`

The base every store implements all of — see the module docstring for `run`.

`docs/02-extension-model.md` → *The store contract family*, verbatim for
the eight capability methods below `run`; see that section for what each
one is for and why (durability as a guarantee rather than a `persist()`
call, deletion as idempotent-and-resumable rather than atomic, and the
rest).

**`supersede` is deliberately *not* here — see `NodeSupersedable`, ledger task
10.24.** It was written onto this Protocol first, and that broke this family's own
stated rule: `SourceDeletable`'s docstring calls a separate Protocol *"exactly the
optional-method design this family exists to refuse"*, and `MetadataFilter` was
corrected into the same shape at task 2.6. Growing this base would also have made
every third-party store owe a method to keep satisfying it — a **major** by `09`'s
table — to gain a capability most of them will never offer.

### Methods

```python
async def add(self, nodes: collections.abc.Sequence[weft_kernel.payload.node.Node]) -> None: ...
```

Accept `nodes` for storage; a store may buffer them until `flush`.

Args:
    nodes: The nodes to write.

```python
async def count(self) -> int: ...
```

Count the nodes stored.

Returns:
    How many nodes this store holds.

```python
async def delete_source(
    self, source_id: weft_kernel.payload.ids.SourceId
) -> weft_store.contract.Removed: ...
```

Delete what `source_id` produced, idempotently and resumably.

Args:
    source_id: The source whose nodes and record are removed.

Returns:
    How many nodes were deleted and how many were narrowed.

```python
async def flush(self) -> None: ...
```

Write out anything `add` buffered; idempotent, and called by the runner.

```python
async def get(
    self, ids: collections.abc.Sequence[weft_kernel.payload.ids.NodeId]
) -> collections.abc.Sequence[weft_kernel.payload.node.Node]: ...
```

Read the nodes stored under `ids`.

Args:
    ids: The node ids to read.

Returns:
    The nodes that exist; an id the store does not hold is absent from the answer.

```python
async def get_source(
    self, source_id: weft_kernel.payload.ids.SourceId
) -> weft_store.contract.SourceRecord | None: ...
```

Read one source's record.

Args:
    source_id: The source to read.

Returns:
    The record, or `None` when none is stored.

```python
async def list_sources(self) -> collections.abc.Sequence[weft_store.contract.SourceRecord]: ...
```

Read every source record this store holds.

Returns:
    Every source record.

```python
async def put_source(self, record: weft_store.contract.SourceRecord) -> None: ...
```

Write or replace one source's record.

Args:
    record: The record to store under its own id.

```python
async def run(
    self,
    payload: collections.abc.Sequence[weft_kernel.payload.node.Node],
    ctx: weft_kernel.context.Context,
) -> weft_kernel.payload.outcome.Outcome[
    collections.abc.Sequence[weft_kernel.payload.node.Node]
]: ...
```

Store the nodes arriving at this pipeline position and pass them on.

Args:
    payload: The nodes to store.
    ctx: The run's context.

Returns:
    The same nodes, unchanged, once stored.

```python
async def scan(
    self, cursor: weft_store.contract.Cursor | None = None
) -> weft_store.contract.Page[weft_kernel.payload.node.Node]: ...
```

Walk every stored node, one page at a time.

Args:
    cursor: Where the previous page ended, or `None` for the first page.

Returns:
    One page of nodes and the cursor for the next, if any.

## `NodeSupersedable`

**Module:** `weft_store.contract`  
**Registered by:** `weft-rag`  
**Version:** `2.14.0`

A store that can replace one node with another — ledger task **10.24**, G15's *Remove*.

**One member, and that member *is* the capability**, which is this family's own rule:
`SourceDeletable` states it (*"A separate Protocol rather than a reuse of `NodeStore`,
deliberately... exactly the optional-method design this family exists to refuse"*) and
`MetadataFilter` was corrected into it at task 2.6. This began as a method on `NodeStore`
and was moved here before it shipped — growing the base would have obliged every
third-party store to implement supersession to keep satisfying it, a **major** under
`09`'s table, for a capability most stores will never offer. Both shipped backends satisfy
this structurally and declare nothing, so `adrap` asks the store it was handed and refuses
by name when the answer is no.

**Why it exists.** `delete_source` is keyed on a *source*, and a summary's relationship to
a source is many-to-many — `Lineage.sources` is the union of its members' — so *"this node
is out of date"* had no expression at all and an incremental tree could not replace what it
superseded.

**Write `new` first, delete `old` second, and that ordering is the contract.** An
interruption then leaves a **duplicate**, which `reconcile` can find, and never a **hole**,
which nothing can and which `04` category A records as staying retrievable forever
describing content that is gone. No atomicity is promised: Qdrant has no cross-operation
transaction, and a guarantee only one backend could keep is worse than the honest one —
`weft_qdrant.delete_source` already works exactly this way and calls itself *"`02`'s
idempotent, resumable deletion"*.

**Idempotent**, so the retry that ordering makes safe is also possible: `old` already
absent is not an error. **Refuses first**, changing nothing, when `new.lineage.sources`
does not cover every source `old` carries — see `SupersedeNarrowsSourcesError`.
Superseding a node with itself is a no-op that must not delete it.

### Methods

```python
async def supersede(
    self, old: weft_kernel.payload.ids.NodeId, new: weft_kernel.payload.node.Node
) -> None: ...
```

Replace node `old` with `new`, writing `new` first.

Args:
    old: The node being replaced; already absent is not an error.
    new: The replacement, which must cover every source `old` carries.

Raises:
    SupersedeNarrowsSourcesError: `new` covers fewer sources than `old`.

## `Prompt`

**Module:** `weft_prompts.contract`  
**Registered by:** `weft-rag`  
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

Render this prompt's conversation for `values`.

Args:
    values: An instance of `input_model`.
    ctx: The run's context, whose locale selects the text.

Returns:
    `Produced` carrying the rendered conversation, or `NothingToProduce` when there is
    nothing to ask.

## `QueryScorer`

**Module:** `weft_retrieve.contract`  
**Registered by:** `weft-rag`  
**Version:** `1.1.0`

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

Score a query along the dimensions a router decides on.

Args:
    payload: The query to score.
    ctx: The run's context.

Returns:
    The query's scorecard.

## `QueryTransform`

**Module:** `weft_retrieve.contract`  
**Registered by:** `weft-rag`  
**Version:** `1.1.0`

Rewrites, expands or narrows the set of queries that will be retrieved for.

`Stage[QuerySet, QuerySet]` is what makes a transform omittable by construction
(ledger 2.15): removing it from a document leaves the seams either side composing
unchanged, so no strategy pays for a rewrite it did not ask for. It also makes two
transforms composable in either order, which is how `hyde` then `multi-query` becomes
a document edit rather than a new plugin.

A transform must not rewrite `QuerySet.origin` — see that field's own docstring for
the defect the invariant closes.

### Methods

```python
async def run(
    self, payload: weft_retrieve.payload.QuerySet, ctx: weft_kernel.context.Context
) -> weft_kernel.payload.outcome.Outcome[weft_retrieve.payload.QuerySet]: ...
```

Rewrite, expand or decompose the queries to search with.

Args:
    payload: The queries so far.
    ctx: The run's context.

Returns:
    The queries to search with.

## `Reconcilable`

**Module:** `weft_store.contract`  
**Registered by:** `weft-rag`  
**Version:** `2.14.0`

Anything whose state can be made to agree with what the corpus actually holds — G7.

The sixth capability in this family, and `docs/02-extension-model.md` §1 → *Extended by
G7* calls it "the safety net, and it is why there is no bus": a bus reaches only
subscribers live when the event fired, so it cannot repair a pack installed *after* the
corpus was built, a drain killed mid-flight, or a second machine sharing one database.
Convergence can, and it needs nothing new to ask its question — `list_sources`, `scan`
and `count` already answer *what should exist*.

**What an implementor promises.** Idempotent, so a second pass over a converged store is
a legitimate no-op. `O(corpus)` and cursored, so it is bounded by what is stored rather
than by what changed. Interruptible, with `CancelledError` propagating untouched — and,
the clause that gives that meaning, **resumable**: whatever a cancelled pass did not
finish must still be discoverable on the next pass, from durable state, never from a
cursor that died with the process.

**`estimate`, task 5.1c, added rather than left optional.** `docs/02-extension-model.md`
§3 → *Slots*: "backfill is reached only by a person's per-run flag" — and `03`'s own text
adds that the person is told the cost first, in real numbers, not asked to trust a flag
blindly. A pack that can converge can say what converging would cost, and CLAUDE.md's own
"cross-cutting concerns live at the registration seam, never in a rule authors must
remember" is exactly why this is a second required member rather than an optional
duck-typed method the way `describe_impact` is for `weft_command.contract.Command`:
`describe_impact`'s own absence is silently fine because nothing there is mandatory for
every command, while a `Reconcilable` that could not say its own cost would make `03`'s
promise one whose truth depends on which packs happened to remember. **This is why
`STORE_CONTRACT_VERSION` moves `1.4.0` → `2.0.0`** rather than to `1.5.0` — see that
constant's own comment for G9's two-audience rule.

### Methods

```python
async def estimate(
    self, ctx: weft_kernel.context.Context, mode: weft_store.contract.ReconcileMode
) -> weft_store.contract.ReconcileEstimate: ...
```

Say what converging would cost, before anything is spent.

Args:
    ctx: The run's context.
    mode: The mode being asked about.

Returns:
    The outstanding work and the model calls converging would make.

```python
async def reconcile(
    self, ctx: weft_kernel.context.Context, mode: weft_store.contract.ReconcileMode
) -> weft_store.contract.ReconcileReport: ...
```

Converge stored state with what the corpus holds.

Args:
    ctx: The run's context.
    mode: Whether the pass only repairs or also backfills.

Returns:
    What the pass did, and how much it left for the next pass.

## `Renderer`

**Module:** `weft_extract.contract`  
**Registered by:** `weft-rag`  
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

Render nodes into one document of this renderer's media type.

Args:
    payload: The nodes to render.
    ctx: The run's context.

Returns:
    `Produced` carrying the `Rendition`, or `NothingToProduce` when there was nothing to
    render.

## `Reranker`

**Module:** `weft_retrieve.contract`  
**Registered by:** `weft-rag`  
**Version:** `1.1.0`

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

Reorder, filter or rescore a ranking.

Args:
    payload: The ranking to rerank.
    ctx: The run's context.

Returns:
    The reranked ranking.

## `RetrievalMetric`

**Module:** `weft_eval.contract`  
**Registered by:** `weft-rag`  
**Version:** `1.0.0`

Scores one `RetrievalSample` — a ranked result against a relevance judgement.

Identical shape to `GenerationMetric` in every respect but the payload type it accepts — see
the module docstring for why the input, and only the input, needed two contracts rather than
one wide `Sample`.

### Methods

```python
async def evaluate(
    self, payload: weft_eval.contract.RetrievalSample, ctx: weft_kernel.context.Context
) -> weft_kernel.payload.outcome.Outcome[weft_eval.contract.MetricScore]: ...
```

Score one retrieval sample.

Args:
    payload: The ranked result and the relevance judgement to score it against.
    ctx: The run's context, through which a metric reaches any service it needs.

Returns:
    The score, or the outcome naming why none could be produced.

## `Retriever`

**Module:** `weft_retrieve.contract`  
**Registered by:** `weft-rag`  
**Version:** `1.1.0`

Turns queries into ranked lists — one per query per channel, never fused.

**A retriever never builds its own index** (ledger 2.5): text and vector search are
things a store *advertises*, reached through `ctx.require(...)` and declared by a
`needs_store: ClassVar[tuple[type, ...]]` class attribute the run assembler checks
before any stage runs. `docs/02-extension-model.md` §1 → *The store contract family*
is the owning text, narrowed in this task to say where the check happens.

**`needs_services`, ledger task 11.10, sits beside `needs_store` for the capability no
store provides.** `needs_store` says what the **configured `[services] store`** must be;
`needs_services` says what the **run** must offer instead — a capability supplied by a
`[services]` role and reached through `ctx.require(...)`, for a retriever whose need is
not a store's business at all (a graph traversal, say). Declared the identical shape,
`needs_services: ClassVar[tuple[type, ...]]`, and read off the factory by the same run
assembler before any stage runs — `weft_engine.run_services.demanded_capabilities` builds the
map, `check_selected_capabilities` checks it. Neither attribute is a member of this
Protocol: `isinstance(plugin, Retriever)` is unaffected by either one, and no plugin that
already satisfies this Protocol's `run` method is asked for anything new because one of
its siblings declared a need it does not share.

Producing `Candidates` rather than one list is the whole fan-out mechanism: k lists
with the `Query` and `Channel` that produced each, so a fuser has something to weight
and so hybrid retrieval and query fan-out arrive at the fuser in the same shape.

### Methods

```python
async def run(
    self, payload: weft_retrieve.payload.QuerySet, ctx: weft_kernel.context.Context
) -> weft_kernel.payload.outcome.Outcome[weft_retrieve.payload.Candidates]: ...
```

Search with every query, one ranked list per arm.

Args:
    payload: The queries to search with.
    ctx: The run's context.

Returns:
    The ranked lists retrieved.

## `Revisable`

**Module:** `weft_index.contract`  
**Registered by:** `weft-rag`  
**Version:** `1.0.0`

A stage that revises what is **already stored**.

Not only the payload it was handed — grilling session **G15**'s *Read* face, ledger task
**10.23**.

Every other stage in an ingest document is a pure function of its payload. An incremental
tree is not: `adrap` must read the summaries a previous run wrote in order to join a new
document to them instead of founding a second tree beside it. Ledger `10.5` settled that
`raptor` performs **no store read** of the corpus, and that property is exactly why decision
`D2` went unreached for two phases — so the capability needed somewhere to live that did not
quietly make it true of every `Expander`. (`raptor`'s `LayerCheckpoints.recall`, task 43.20,
reads back only its own interrupted build's summaries, never the corpus.)

**The corpus is reached through `ctx.require(NodeStore)`, and there is no new type for it.**
G13 settled that move for `reconcile`: the primary store, from the context, zero kernel
lines, no contract change. `NodeStore` already answers *what exists* — `scan`, `count`,
`matching`, `get` — so a "corpus view" would be a second way to ask the same questions.

**Why a separate contract rather than letting an `Expander` do it.** Registering the
capability is what makes it *visible*: `weft pipeline show` prints `Expander:raptor` beside
`Revisable:adrap`, so a reader of a resolved document can see which stages read the corpus.
Allowing any `Expander` to call `ctx.require(NodeStore)` would turn `10.5`'s property from a
fact about a **kind** of stage into a per-plugin habit, with nothing to key a check on and
nothing to tell a reader — requirement 1's failure shape, an extension point decaying into
a convention.

**Structurally identical to `Expander`, and that is stated rather than hidden.** Both are
`Stage[Sequence[Node], Sequence[Node]]` with `run` alone, so `isinstance` cannot separate
them and no marker attribute will be added to make it: capability is derived, never
declared (`02` §1), and a declared marker is one a pack could write falsely. What separates
them is the contract a pack registers under.
`tests/unit/weft_index/test_contract.py` pins both halves.

**Ordering is not this contract's problem, which the session initially got wrong.** G15's
*Read* face argued that a `Revisable` placed before a document's own `store` stage would
read a stale corpus and should be refusable at resolution. Re-read against a real document,
that is not so: `adrap` reads what *previous* runs stored, clusters this run's payload into
it, and the `store` stage then writes the result — `embed, adrap, store` is the natural
order and nothing is stale. The refusal that seemed owed is not, and the kernel could not
have expressed it anyway without naming a capability.

**Corrected by G16 (2026-09-08): the conclusion holds and the reason above is incomplete.**
It argues from `adrap`'s *natural* placement, which is a fact about one plugin rather than
about this contract — and a contract's ordering rule may not rest on its only registration.
The durable reason is the second clause: semantic order is not a data dependency, so
`requires`/`provides` cannot express it and the resolver cannot see it. G16 therefore
**permits** a `Revisable` after `store` rather than leaving it undecided, and states what
differs: it then reads a corpus already containing this run's own leaves, so `adrap` finds
them as existing members instead of as arrivals. Nothing breaks — `put` is keyed on a
content digest and `supersede` is idempotent by contract. A second `Revisable` in one
document is permitted too, and runs in its declared order like any other stage.

**How a `Revisable` actually receives the store, which G15 settled and never ran.**
`ctx.require(NodeStore)` resolves on the ingest path **only because** a document declaring
a `Revisable` causes `weft_cli.ingest._store_instance_for_corpus_readers` to hand the store
*stage's own instance* to `build_index_services`. That plumbing is G16's, not G15's: G15
cited G13's `reconcile` precedent, `reconcile` is not a pipeline stage, and this contract,
`NodeSupersedable` and `adrap` all shipped green over a call that could not resolve
(`docs/internal/lessons.md` `L10.40`). An ordinary ingest document still gets no ambient store.

`layer_stage = True` (R43.16): this contract's publisher promises that a stage under it
takes nodes already stored and returns every node it was handed, each under its own id,
plus whatever it derived from them. It may embed what it derives — `adrap` embeds each
summary it rebuilds, through `ctx.require(Embedder)` — and it may write to the store it was
handed: `adrap` supersedes the summaries it rebuilds, unless it was handed a
`LayerRevision` (task 43.23), when it reports each replaced summary there instead and
writes nothing. This is the contract's
own declaration, not a plugin marker: a plugin never sets it, it inherits the promise by
registering under `Revisable`. `reads_corpus = True` (R43.20) is the same kind of
declaration: a stage under this contract is handed the store its document writes to.

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

Return every node handed in, plus whatever this stage derived from them.

Args:
    payload: The nodes to expand or revise.
    ctx: The run's context, through which services such as an `Embedder` are reached.

Returns:
    The handed nodes and the derived ones, or `NothingToProduce`/`Failed`.

## `RoutingPolicy`

**Module:** `weft_retrieve.contract`  
**Registered by:** `weft-rag`  
**Version:** `1.1.0`

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

The names among `candidates` this policy could ever choose.

```python
async def run(
    self, payload: weft_retrieve.payload.Scorecard, ctx: weft_kernel.context.Context
) -> weft_kernel.payload.outcome.Outcome[weft_retrieve.payload.Route]: ...
```

Choose the pipeline a scored query is answered by.

Args:
    payload: The query's scorecard.
    ctx: The run's context.

Returns:
    The chosen route.

## `SingleWriter`

**Module:** `weft_store.contract`  
**Registered by:** `weft-rag`  
**Version:** `2.14.0`

A store that admits one writer at a time — ledger task **43.18**.

`claim_writer` either records the claim or raises `WriterBusyError` naming the claim another
handle holds. The claim ends at `release_writer`, and on a store that can tell, when the
holding process dies. A claim made by a crashed writer never blocks the next one forever.

### Methods

```python
async def claim_writer(self, writer: weft_store.contract.WriterClaim) -> None: ...
```

Claim this store for `writer`, or refuse naming the current holder.

Args:
    writer: Who is claiming the store.

Raises:
    WriterBusyError: Another handle holds the claim.

```python
async def release_writer(self) -> None: ...
```

End this handle's writer claim, if it holds one.

## `SourceDeletable`

**Module:** `weft_store.contract`  
**Registered by:** `weft-rag`  
**Version:** `2.14.0`

Anything holding data that a source's deletion must reach — G7 (2026-08-21).

The fifth capability in this family, and the only one whose implementors
are not expected to be stores. `docs/02-extension-model.md` §1 →
*Extended by G7*: `delete_source` sat on `NodeStore` from G4 and nothing
in the tree called it, while a pack holding entities derived from nodes
would never hear that those nodes were gone. That is exactly the RAPTOR
scar — summaries no deletion path can reach — reappearing first-party.

**A separate Protocol rather than a reuse of `NodeStore`, deliberately.**
A graph store is not a node store: asked to implement `NodeStore` it would
owe `scan`, `count` and the three source methods to answer one question
about deletion, which is exactly the optional-method design this family
exists to refuse. One member, and that member *is* the capability — the
same rule `MetadataFilter` was corrected into at task 2.6.

**`NodeStore` satisfies this by construction and that is the point.**
`delete_source` is already one of `NodeStore`'s own methods, so every store
in this family is a participant with nothing added and nothing declared —
capability derived, never declared, which is what makes a fan-out over
"everything satisfying `SourceDeletable`" find the node store without
naming it.

**What an implementor promises.** Deletion is idempotent and resumable:
deleting a source that is already gone is a legitimate no-op returning
`node_count=0`, never an error, because a fan-out re-run after a partial
failure must be able to finish the job. What it must *not* do is report
success it did not achieve — `weft delete` names a participant that raises,
and a participant that swallows its own failure makes that promise
unkeepable.

### Methods

```python
async def delete_source(
    self, source_id: weft_kernel.payload.ids.SourceId
) -> weft_store.contract.Removed: ...
```

Delete what `source_id` produced, idempotently and resumably.

Args:
    source_id: The source whose derived data is removed.

Returns:
    How many nodes were deleted; zero for a source that is already gone.

## `Sufficiency`

**Module:** `weft_retrieve.contract`  
**Registered by:** `weft-rag`  
**Version:** `1.1.0`

Judges whether the evidence in hand answers the question. **Not a pipeline position**.

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

Judge whether `evidence` suffices to answer `question`.

Args:
    question: The question being answered.
    evidence: The passages gathered so far.
    draft: An answer drafted from `evidence`, when there is one.
    ctx: The run's context.

Returns:
    The `Assessment`; `observed=False` when the judgement could not be made.

## `TargetHolding`

**Module:** `weft_store.contract`  
**Registered by:** `weft-rag`  
**Version:** `2.14.0`

A store that holds named, complete targets, one of them live.

A store that holds named, complete targets, one of them live — ledger task **34.3**,
Phase 34's blue-green index migration.

An unbound handle serves the **live** target, read once when the handle first touches
storage and held for its lifetime (owner decision Q-C, ledger task 34.3) — so one
operation never reads two targets. `bind_target` gives a handle onto one target by name
instead. Embedding identity is recorded per target, through `claim_embedding`, never per
node.

### Methods

```python
async def bind_target(self, target: weft_store.contract.TargetName) -> typing.Self: ...
```

Open a second handle onto this store, bound to `target`.

Args:
    target: The target the new handle reads and writes.

Returns:
    The bound handle.

```python
async def claim_embedding(
    self, identity: weft_store.contract.EmbeddingIdentity
) -> weft_store.contract.EmbeddingIdentity: ...
```

Record `identity` against this handle's target, unless one is recorded.

Args:
    identity: What embedded the vectors about to be written.

Returns:
    The identity the target holds, which is the earlier one if already claimed.

```python
async def drop_target(self, target: weft_store.contract.TargetName) -> None: ...
```

Delete `target` and everything stored in it.

Args:
    target: The target to drop.

Raises:
    UnknownTargetError: The target is not in the catalogue.
    TargetInUseError: The target is live, previous, or bound by another handle.

```python
async def promote(
    self, promotion: weft_store.contract.Promotion
) -> weft_store.contract.TargetCatalogue: ...
```

Make the promoted target live, recording the previous one for rollback.

Args:
    promotion: The target to make live and why.

Returns:
    The catalogue after the promotion.

Raises:
    UnknownTargetError: The target is not in the catalogue.

```python
async def rollback(self) -> weft_store.contract.TargetCatalogue: ...
```

Swap the live target with the previous one.

Returns:
    The catalogue after the rollback.

Raises:
    NoPreviousTargetError: No target was live before this one.

```python
async def target_catalogue(self) -> weft_store.contract.TargetCatalogue: ...
```

Read every target this store holds.

Returns:
    The targets, which one is live, which was live before, and the last promotion.

## `TextSearch`

**Module:** `weft_store.contract`  
**Registered by:** `weft-rag`  
**Version:** `2.14.0`

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

Rank stored nodes by lexical match against `text`.

Args:
    text: The query text.
    top_k: How many nodes to return at most.
    filter: A predicate every returned node must satisfy, if any.

Returns:
    The best `top_k` nodes with their scores, best first; empty when nothing matches.

## `VectorSearch`

**Module:** `weft_store.contract`  
**Registered by:** `weft-rag`  
**Version:** `2.14.0`

A store that can rank `Node`s by vector similarity.

Never embeds — `02`: "stores never embed. `VectorSearch` takes a vector, `TextSearch` takes
text; a store is therefore not coupled to a model." Not a `Stage`: nothing in an ingest pipeline
calls `search_vector`, and a future `Retriever` (Phase 2) resolves this capability directly
against the configured store rather than through the runner's stage machinery.

### Methods

```python
async def search_vector(
    self,
    vector: weft_kernel.payload.vector.Vector,
    top_k: int,
    filter: weft_store.contract.Filter | None = None,
) -> collections.abc.Sequence[weft_store.contract.Scored[weft_kernel.payload.node.Node]]: ...
```

Rank stored nodes by similarity to `vector`.

Args:
    vector: The query vector; the store never embeds.
    top_k: How many nodes to return at most.
    filter: A predicate every returned node must satisfy, if any.

Returns:
    The best `top_k` nodes with their scores, best first.
