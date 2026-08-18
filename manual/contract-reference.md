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
**Published by:** `weft-chunk`  
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
**Published by:** `weft-clean`  
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

## `Embedder`

**Module:** `weft_embed.contract`  
**Published by:** `weft-embed`  
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
**Published by:** `weft-enhance`  
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

## `Extractor`

**Module:** `weft_extract.contract`  
**Published by:** `weft-extract`  
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

## `NodeStore`

**Module:** `weft_store.contract`  
**Published by:** `weft-store`  
**Version:** `1.0.0`

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

## `VectorSearch`

**Module:** `weft_store.contract`  
**Published by:** `weft-store`  
**Version:** `1.0.0`

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
