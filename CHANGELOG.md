# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html) **per distribution** — `weft`
ships as two packages (`docs/internal/README.md` → *Where things are*), not one, and each carries its own
version, tracked in its own `pyproject.toml`. This file does not repeat those numbers — a second,
hand-copied list of them is exactly the two-lists bug `docs/internal/README.md` opens with, aimed at version
digits instead of prose — it records what changed, and why, for someone using the software.

**Architecture decisions are not changelog entries.** They live in a decision log that is
developer-local — `docs/internal/README.md`, which `.gitignore` keeps out of this repository — and
what a release actually did to the software is what this file records. Where a decision changed
something you can see from outside, the entry below says so in its own words.

**First release: 2026-09-11, tag `v2.4.0`.** `weft-rag` and `weft-kernel` are the two names this
project publishes (**G19**, 2026-09-09 — a new capability never adds a third; `docs/internal/README.md`'s
decision log owns the reasoning). Measured 2026-09-08, before that gate closed: all eight names G10
had published under returned 404 on PyPI — this is the first index publication either successor name
has ever had. Four retired, pre-consolidation names (`weft-command`, `weft-embed`, `weft-generate`,
`weft-llm`) reached PyPI at `0.1.0` on 2026-09-05 before a rate limit stopped the rest; their code
ships inside `weft-rag` now, and all four are **yanked** as of this release (see *Removed*, below).

> **This file went stale again, and the way it did is worth more than the apology.** `docs/internal/lessons.md`
> L5.8 was written because this changelog was nineteen lines, touched once, and unmoved while five
> phases shipped around it. Task 5.2f brought it current and added a check
> (`tests/docs/test_changelog_deprecation_coverage.py`) — and then it sat untouched through **five
> more** phases, 6 through 10. The check is not broken and it did not fail: its subject is
> *deprecations*, of which this tree has zero, so it passes by asking nothing about the rest of the
> file. A check whose real subject is legitimately empty cannot notice the artefact rotting around
> it, which is `L5.19`'s own shape landing on the artefact `L5.8` was written to protect. Brought
> current here in the commit that prepares the first release.

## [Unreleased]

### Deprecated

- **`Language`, the `weft_clean` ext model, is deprecated.** Nothing in Weft writes it: no shipped
  stage attaches a `Language` to a node, so no store holds one, and importing the class is the only
  thing that stops working. `weft plugins doctor` prints the notice. **Removed in `weft-rag`
  3.0.0.**

### Changed

- **`raptor` refuses a corpus it cannot cluster in reasonable time, before starting.**
  `similarity_threshold: auto` compares every pair of leaves. On 3,072-dimension vectors that
  measured 86 s and 339 MB at 1,000 leaves, and it grows with the square of the leaves: about 8.6
  hours at the 19,000 a 100-PDF corpus holds. So `auto` is refused above `max_pairs` (500,000
  pairs), and clustering is refused above `max_leaves` (5,000) whatever the threshold. The message
  names the leaf count, the bound and the remedies: type a `similarity_threshold`, or raise the
  bound in the stage's `with:` block.
- **`weft index` works in batches of 25 by default, and each batch is searchable the moment it
  lands.** A progress line on stderr says how many documents are queryable so far, and `--json`
  carries it as a `batch-progress` line. Only one batch of files is held in memory at a time: on
  1,000 PDFs, memory before the first batch fell from 3.4 GB to 261 MB. `--batch-size` still sets
  the number. A pipeline with a stage that needs the whole corpus in one batch still gets one, and
  the line names that stage.
- **The OpenAI embedder sends up to 4 requests at once** (`max_concurrent_requests` in
  `[packs.openai]`), so embedding 100 PDFs took 35.6 s rather than 117.1 s. Pipeline identity does
  not move.
- **`weft ask` says how much of the corpus it could see.** While some sources are still indexing,
  or have failed, the answer's footer and `--json` envelope count them. A question the indexed
  part cannot answer says *"N sources are not yet indexed"* rather than only *"the corpus does
  not answer this"*.

- **A pipeline's identity hashes each stage contract's major version, not its full version.**
  Before this, every minor release of a contract, such as the store contract's move to `2.9.0`,
  changed the identity of every pipeline, so the first `weft index` after an upgrade re-parsed
  every document, paying again for any model stage. A minor only adds, so it says nothing about
  how a corpus was built. **This moves the identity once more**: the first `weft index` after
  installing this release re-parses each document once, reporting it *"unchanged on disk but
  re-parsed by a different pipeline"*. Later minor releases do not.
- **The published baseline is re-taken: `baselines/8854c33f71ea-2026-09-21.json`.** The earlier
  `2026-08-25` file recorded the `hash` embedder's stage with no configuration, and a `weft-rag`
  newer than 2.7.0 writes its default `dimension: 64`, so `weft eval compare` refused it. Every
  metric is unchanged; `docs/REPRODUCING.md` now judges against the new file.
- **A pipeline's identity is computed from a stage's configuration fields, keys sorted**, not from
  the text pydantic prints for them — so reordering a plugin's config fields, or a pydantic release
  that prints them differently, no longer re-parses a corpus nothing about had changed. **This
  moves the identity once**, for every pipeline document with a stage whose plugin declares a
  configuration model, whether or not the document sets it: the next `weft index --pipeline …`
  over a corpus indexed before this release reports each file *"unchanged on disk but re-parsed
  by a different pipeline"* and re-parses it, once. Bare `weft index` is unaffected.

### Added

- **A plugin declares which config fields name a model role: `Annotated[str, LLMRole()]`.** A
  routed `weft ask` offers only rungs whose roles are mapped, and it found those roles by a fixed
  list of first-party field names. So a third party's `judge_role` went unseen, and its rung
  refused after a paid call. The walk now reads the marker, whatever the field is called, and every
  first-party role field carries it. `weft_llm.LLMRole` is new, and the LLM contract moves to
  `1.1.0`. `examples/weft-example-query` gains `example-llm-judge`, a reranker whose `judge_role`
  is seen this way.
- **A plugin that composes another declares it: `Annotated[str, SubPlugin(config="…")]`.** A
  routed `weft ask` followed a sub-plugin only through a field pair named `X`/`X_config`. So the
  shipped `broad-and-refined-rrf`, whose looping arm needs `grade`, was offered with `grade`
  unmapped and refused after a paid call, and a third party's composer was missed the same way.
  The walk now follows declared references through every nested config model, and every
  first-party composer declares its references. An optional role field now keeps its marker in
  either spelling. `weft_retrieve.SubPlugin` is new, and the retrieve contract moves to `1.1.0`.
  `examples/weft-example-query` gains `example-judge-panel`.
- **Adding documents joins them into a corpus-wide RAPTOR tree instead of rebuilding it.** After
  new sources are indexed, `weft index --layers enrich-with-raptor` hands only their leaves to
  `adrap`. `adrap` rebuilds the summaries they join and carries every other summary forward
  untouched, then publishes the result as one new generation. It prints `layer
  'enrich-with-raptor': joined <n> leaves, <m> unassigned`, and the count is also on
  `IndexResult.layers_joined`. A layer that lost a source is still rebuilt in full, since a join
  cannot remove a member. A layer document names its join stage with `layer.incremental`, and a
  third-party join stage reaches the layer's tree through `weft_index.contract.LayerRevision`.
  **Every existing `enrich-with-raptor` layer is reported changed once after upgrading**, because
  the shipped document gained the join stage. Run `weft index --layers enrich-with-raptor
  --reprocess` once to rebuild it.
- **A store can carry a layer's untouched nodes into its next generation.** `weft_store` publishes
  `GenerationCarrying`: `carry_forward(into, node_ids)` adds a new generation to published nodes
  without rewriting them, so a layer rebuild pays only for what it replaces. pgvector, Qdrant and the
  conformance kit implement it, and the kit's checks prove it for a third-party store. The store
  contract moves to `2.13.0`.
- **An interrupted corpus-wide layer resumes instead of starting over.** Stopping `weft index
  --layers` part-way through a corpus-scoped RAPTOR build keeps every summary finished so far, in
  the generation nobody reads yet. The next run under the same pipeline and models picks that
  generation up and pays only for the clusters still missing. A run whose prompt or models changed
  starts afresh. A third-party layer stage can resume the same way through
  `weft_index.contract.LayerCheckpoints`, and the `Expander` contract moves to `1.1.0`.
- **`enrich-with-facts-and-graph`: the graph as a layer.** `weft index --layers
  enrich-with-facts-and-graph` extracts facts, mentions and co-occurrence from each stored chunk
  after the base is searchable, and the graph store turns them into entities and relations. Over a
  base with no store that can hold them, the layer is refused before anything runs, naming the
  installed stores that can. A layer document states which store it needs with
  `layer.store-consumes`, and a store states what it turns into rows with `consumes`.
- **A store can build a layer as a generation, published whole.** The store contract moves to
  `2.11.0` with one optional capability, `weft_store.contract.GenerationHolding`: open a generation,
  write its nodes through a bound handle, then publish or retract it. Until it is published, its
  nodes are left out of vector search, text search and metadata filters, before the top results
  are taken. A handle keeps the set of generations it saw when it opened, so one question never
  mixes two builds of a tree. The published conformance kit gains six checks for it. pgvector and
  Qdrant hold generations; a store that does not keeps working exactly as before.
- **Layers: enrichment that runs after a corpus is searchable.** `weft index --layers
  enrich-with-questions` indexes the base, then generates questions for every stored chunk, and
  embeds and stores only those questions with the base's own embedder. `--layers-only` runs a layer
  over an already indexed corpus, `--layers none` skips the configured ones, and `[index] layers`
  in `weft.toml` sets them for every run. Each source records the layer as indexing, active or
  failed. A finished layer is skipped, a failed one is retried only under `--retry-failed`, and
  `--reprocess` rebuilds a source's layers with its base. `Weft.index` takes `layers` and
  `layers_only`.
- **A layer can build one tree over the whole corpus, published only when it is complete.**
  `enrich-with-raptor` builds a RAPTOR tree per document; a project derives it with
  `vars: {layer.scope: corpus}` to build one tree over every document instead. That build is
  written as a generation, invisible to every search until it finishes, then replaces the previous
  tree in one step. A document indexed later leaves the tree stale; `weft index` says so, and the
  next run naming the layer rebuilds it. A store that cannot hold generations is refused by name.
- **A second `weft index` into a store another is still writing is refused**, naming the running
  one's command, process and start time. A crashed run releases the store: on pgvector at once,
  on Qdrant when its lease expires. `weft ask` is never refused.
- **A pack outside Weft can ship a layer.** The example ingest pack ships
  `example-first-sentences`, a layer over its own expander, and `weft index --layers` runs it from
  the installed wheel.
- **A query rung can require a layer**, with `route.requires` in its `vars`.
  `questions-then-generate` is the first: it searches the chunks and their generated questions in
  one ranking, then counts each question as the chunk it asks about. The router does not offer
  it until `enrich-with-questions` is built on every indexed source, and `--explain` says why.
  `weft ask --pipeline` naming it is refused with the layer's progress, unless `--allow-pending`
  is given, and then a `layers:` line under the answer says how far the layer has got.
  `weft sources list` shows each source's layers, and `weft target list` shows the layers
  complete on each target.
- **A source record says which layers have been built over it.** The store contract moves to
  `2.10.0`: `SourceRecord` gains `layers`, one `LayerRecord` per layer (its name, the identity of
  the document that built it, `indexing`, `active` or `failed`, its failure, attempts and when),
  empty by default. Every shipped store keeps it, a store written by `2.9.0` reads back with no
  layers, and a layer field or status a newer release wrote is refused by name
  (`UnknownSourceLayerError`). The published conformance kit gains one check for it. No pipeline
  identity moves.
- **A store can hold named targets, one of them live — the start of blue-green index
  migration.** The store contract moves to `2.9.0` with one optional capability,
  `weft_store.contract.TargetHolding`: bind a handle to a target, list the catalogue, promote,
  roll back, drop, and record the embedding identity a target was built with. The in-memory store
  satisfies it and the published conformance kit gains eleven checks for it. A store that does not
  satisfy it keeps working exactly as before; it is refused only when asked for a target.
- **An index remembers which embedder built it, and a question embedded any other way is
  refused.** Each target records the embedder of its first write: plugin, distribution, the model
  it calls and the vector width. `weft ask` and every evaluation that queries a store check the
  query's embedder against that record before comparing any vector
  (`EmbeddingIdentityMismatchError`). This catches the case nothing caught before: a different
  model at the same width. An index written before this release records the embedder of its next
  `weft index`. Embedders state their identity through a new optional Protocol,
  `weft_embed.contract.IdentifiedEmbedder`, and the embedder contract moves to `1.1.0`.
- **`--target <name>` builds and reads a candidate index beside the live one.** `weft index
  --target w128` writes into a new target, created by its first write, and says whether it is
  live. `weft ask`, `weft eval run`, `weft reconcile`, `weft delete` and `weft sources list`
  accept `--target` to read or act on one target, and refuse a target that does not exist,
  naming the targets that do (`UnknownTargetError`). `weft target list` prints each target with
  its live or previous mark, the embedder that built it and its source count. `Weft.index` and
  `Weft.ask` take `target=`. Leaving out `--target` behaves exactly as before.
- **`weft eval compare` compares a live index with a candidate built by another embedder.** A run
  records the target it scored and the embedder that built it. Two runs over two different
  targets, with the same corpus and questions, now compare instead of being refused for differing
  model versions, and the output opens with `comparing targets default → w128; subject: …`,
  naming what changed. Two runs of the same target are refused as before.
- **`weft target promote`, `rollback` and `drop`.** `promote <name> --evidence <live-run>
  <candidate-run>` makes a candidate live in one atomic switch and records who promoted it on which
  runs. It is refused without evidence (unless `--without-evidence`, which is recorded), when the
  evidence is for other targets, corpora or questions, when a candidate document is still being
  indexed or deleted, or when the candidate's embedder was never recorded. `rollback` restores the
  previous target. `drop` removes a target that is neither live nor previous. The graph pack's
  store holds targets the same way, and the query-time graph walk reads whichever is live. Blob
  storage keeps each candidate's figures under `<root>/.targets/<name>/`, so a candidate never
  overwrites the live index's bytes. An existing blob root is read unchanged.
- **A promote moves every store a project uses together.** With the graph pack active, `weft target
  promote`, `rollback` and `drop` act on both the node store and the graph store. `drop` also
  removes the target's figures, and `weft index --target` writes figures into the target's own
  subtree. If a promote stops between two stores, every command refuses, naming each store's live
  target (`TargetPointersDisagreeError`), until the promote is run again, which finishes it.
  Promoting the target that is already live changes nothing. A `weft index` that was writing the
  live target when another process promoted a different one finishes where it started and says so.
- **`[services.embed_config]` configures the embedder that embeds your questions.** An index built
  by a configured embedder, such as `hash` at `dimension: 128` or OpenAI with `dimensions`, can now
  be asked: put the same configuration here. It is checked against the embedder's own settings,
  and a key it does not take is refused by name (`EmbedConfigRefusedError`). A named pipeline's
  own embed stage still wins.
- **A document that failed to index is recorded as failed, and you can find it.** `weft index`
  records every document of a batch that a stage refused or raised on as `failed`, with the
  stage, the error, an attempt count and the time, and removes what it half-wrote. Later runs skip
  it and say so, naming `--retry-failed`, instead of retrying it unasked, because a pipeline with a
  model stage pays for every retry; changing the file or the pipeline retries it with no flag.
  `weft sources list [--status failed]` lists what the store recorded. The store contract moves to
  `2.8.0`: `SourceStatus` gains `FAILED` and `SourceRecord` an optional `failure`, and a status a
  newer `weft-rag` wrote is refused by name (`UnknownSourceStatusError`).
  `weft eval run` and `weft eval experiment` refuse to score a corpus holding a failed document
  (`CorpusHasFailedSourcesError`), since its record would name documents it never saw.
  **A store outside this repository has one new obligation:** keep `SourceRecord.failure` and
  `pipeline_identity` as it is handed them, and accept the `failed` status. Read stored values
  through `weft_store.source_status` and `weft_store.source_failure`, which refuse by name what a
  newer release wrote. `weft_store.conformance`'s source-record checks test all of it; the example
  graph store runs them.
- **`weft index` counts the chunks an expansion stage could not expand.** A chunk whose
  questions, cluster summary or facts could not be generated still degrades rather than failing
  the run, and now carries an `ExpansionDegraded` marker naming the stage and why — for
  `hypothetical-questions`, `raptor` and `llm-facts` alike. After a run whose pipeline has an
  expansion stage, and whose store can filter, `weft index` prints
  `chunks stored without their expansion: N.` — so a questions arm that silently shrank says so.
- **`weft ask --explain` counts each reranker's and packer's passages in and out**, and a
  packer given a token budget records what it kept: `repack: packed 2 of 3 passages in 20 of 20
  tokens`. Before, those stages printed a time and nothing else.
- **A generating rung's run record says which retrieval arms fed each answer**, as a retrieval
  rung's already did. `Answer` carries `contributors`, copied from the passages it was given.

### Fixed

- **A layer no longer enriches fact and mention nodes.** Over an `index-with-facts` base,
  `--layers enrich-with-questions` generated questions for the graph's own fact and mention nodes:
  48 of 54 in a two-document run. An ext model now declares `not_a_leaf`, and a layer skips every
  node carrying one.
- **`index-with-adrap` no longer edits a layer's RAPTOR tree.** It joined new documents into any
  RAPTOR tree in the store, including one a layer built. A layer now marks what it creates, and
  `adrap` joins only the base tree. A tree a layer built before this release is unmarked until the
  layer is rebuilt.
- **Deleting a source marks a corpus-wide layer stale.** A layer built over the whole corpus, such
  as one RAPTOR tree, lost the deleted source's part of the tree and went on being served as whole.
  `weft delete` now marks such a layer `stale` on every remaining source and prints so. `weft
  sources list` and `weft index` show it, the router stops offering its rung, and `weft index
  --layers <name>` rebuilds it. The store contract moves to `2.12.0` for the new `LayerStatus.STALE`.
- **A routed `weft ask` no longer pays for a routing call and then refuses for a missing role.**
  With only some model roles mapped, a routed ask refused for `route`. Once `route` was mapped, it
  made the router's model call and then refused for `grade`. Now the router offers only pipelines
  whose roles are all mapped, and `--explain` says `not offered: '<pipeline>' needs role '<role>'`.
  The router's own role is checked before any model call, and when nothing is left to offer the
  refusal names every missing role at once (`NoRungOfferedError`).
- **Re-indexing a changed document never leaves a corpus-wide layer served with a hole in it.**
  `weft index` released a changed, retried or incomplete source's nodes, the corpus tree's
  summaries over it included, and every other record still read as current. So the layer stayed
  ready, and the next `--layers` run joined into the hole instead of rebuilding. A failed re-parse
  left it that way for good. The corpus layers the source covered are now marked stale before
  anything is released, as `weft delete` does since the previous entry. The stale line reads "a
  source it covered was deleted or re-parsed", and `weft index --layers <name>` rebuilds the tree.
- **A corpus-wide RAPTOR build on pgvector no longer fails once it keeps two summaries.** Resumable
  builds (`LayerCheckpoints`) saved each summary through the one store connection while `raptor`
  wrote several at once, and pgvector refused the interleaved transactions
  (`OutOfOrderTransactionNesting`). The checkpoint service now makes one store call at a time;
  summarising stays concurrent.
- **`weft reconcile` says how many nodes it reclaimed, and `weft index` says when a store made a
  layer build fall back.** Reconcile reclaimed withdrawn layer trees and printed nothing about it.
  Its line now ends `, reclaimed N` when N is not zero. A store that holds generations but cannot
  withdraw one makes a replaced tree vanish at once, under any query still reading it. One that
  cannot carry a generation forward turns a join into a full rebuild. Both used to happen
  silently. `weft index` now prints one line per such store, once per run, naming it and what it
  cannot do.
- **A layer's join stage can no longer write the tree readers are served.** The stage a corpus
  layer's `layer.incremental` names was handed the build's own writer as its `NodeStore`, so a
  join that ignored `LayerRevision` could supersede or delete a published node. It is now handed
  a view that answers every read and refuses every write (`LayerJoinWritesStoreError`). The view
  offers the same optional capabilities as the store behind it.
- **`weft delete` never leaves a corpus-wide layer served whole with a hole in it.** It deleted the
  source first and then marked the layers it covered stale. When the mark failed, the error told
  you to run `weft index --layers <name>`, which rebuilt nothing, because every remaining record
  still read as current. The layers are now marked before anything is deleted. If marking fails,
  the source is not deleted and the error says to run `weft delete <id>` again.
- **Two layers deriving one node are refused whatever the node is.** The collision check compared
  techniques through `Representation`, so a graph layer's fact and mention nodes, or a third
  party's, read as the same technique and the second layer silently overwrote the first's. It now
  compares the layer each stored node is stamped with, and names that layer. An unstamped node is
  judged by its technique, as before.
- **A pgvector read no longer fails with `cached plan must not change result type`.** A handle that
  had run one read five times held a prepared plan, and the first embedded `weft index` into a
  fresh store narrows the `embedding` column's type. Every later read of that shape on the older
  handle failed, and kept failing. A command that reads many times on one store, as
  `weft eval experiment` does, met it when another process wrote the store's first embeddings. The
  store no longer prepares statements server-side, which costs about 0.3 ms per text search.
- **A project can derive `enrich-with-raptor` without its join stage.** A document that extended
  it and removed the `join` stage was refused, because the inherited `layer.incremental: join` named
  a stage that was gone and a var cannot be unset. `layer.incremental: none` now says the layer has
  no join. A var naming a layer's only stage is refused, rather than composing a full build with
  nothing to run.
- **A citation of a summary says what it summarises.** An answer citing a corpus-wide RAPTOR
  summary printed `[1]  — <id>` with an empty label, because a node built from several sources has
  no single location. It now prints `summary of <n> sources (<layer>)`. A cited node with no source
  prints `no source`. `--json` is unchanged: `uri` stays a location, empty when there is none.
- **`weft index --reprocess` says which layers it removed and did not rebuild.** Reprocessing a
  source removes everything built from it, including the output of layers this run did not name in
  `--layers`. That output disappeared without a word. The run now prints `layer '<name>' was
  released with <n> source(s) and not rebuilt — weft index --layers <name> rebuilds it`, and
  `IndexResult.layers_released` carries the same list.
- **`weft index --layers <name> --layers-only --reprocess` rebuilds a layer whose settings
  changed.** It printed "changed since it last ran and was not rebuilt — weft index --layers
  <name> --reprocess rebuilds it" and rebuilt nothing, which made the remedy it named the command
  just run. A corpus-wide layer now rebuilds into a new generation without touching the base. A
  per-source layer's old output can only be removed with its source, so the sources whose layer
  changed are indexed again, base and layer, as `--reprocess` alone does; sources whose layer did
  not change are left alone.
- **On Qdrant, a retracted layer generation's nodes are deleted, not just hidden.** A store
  connection opened before its collection existed remembered that answer. After another
  connection created the collection, the first one retracted a generation's record but left its
  nodes stored, and its reads came back empty. It now asks Qdrant again until the collection
  exists.
- **A query running while a corpus-wide layer is rebuilt keeps the tree it started with.** A query
  that opened before a rebuild was published, and read after the old tree was retracted, could see
  neither tree: in 2 of 4 exit runs on Qdrant it came back with no summaries at all. A replaced
  tree is now withdrawn rather than deleted. New queries see only the new tree, a query already
  running reads the old one to its end, and the old nodes are removed before that layer's next build
  or by `weft reconcile`. `weft_store` publishes `GenerationWithdrawing` (`withdraw_generation`,
  `reclaim_withdrawn`) for third-party stores, with kit checks, and the store contract moves to
  `2.14.0`.
- **A reader sees one tree per layer while a rebuild is published.** A query that opened between a
  corpus layer's publish and the retract after it saw the old and the rebuilt summaries together.
  A store now serves, for each layer, only its newest published generation, on pgvector, Qdrant and
  a store that passes the conformance kit.
- **Deleting a source removes the graph relations only it stated.** A relation stayed reachable
  after the fact that stated it was deleted, while other documents still mentioned its two
  entities. The graph tables move to layout `3.0.0`: a graph indexed before this is refused by
  name, and dropping its `kg_*` tables and re-indexing rebuilds it (`manual/troubleshooting.md` →
  `GraphSchemaVersionRefusedError`).
- **A layer that fails is reported, and `weft index` exits 1.** The run prints each failed layer
  with how many of its sources failed and the first reason; before this it printed nothing and
  exited 0. A layer whose document changed is printed too, and one that failed under an older
  version of its document runs again without `--retry-failed`, so raising a bound RAPTOR refused
  on takes effect.
- **`enrich-with-raptor` builds one tree per document, as documented.** It was handed a whole
  batch of documents at once, one tree over up to 25 of them.
- **A summary `adrap` rebuilds is embedded before it replaces the old one.** It was stored with
  no vector, so after `index-with-adrap` joined a new document to a RAPTOR tree, the rebuilt
  summaries dropped out of vector search.
- **One document that fails no longer fails the documents batched with it.** A failed batch is
  re-run a document at a time, so only the document that fails alone is recorded failed. Before
  this, the default `weft index` over 1,000 PDFs with three unreadable ones indexed none of them.
- **A PDF page `pdf-text` cannot read costs that page, not the whole document.** The page is
  dropped, and every surviving node records which pages were dropped and why.
- **`weft ask` while `weft index` runs no longer breaks or stalls the indexer.**
  - Two processes opening one fresh pgvector database at once no longer race on creating the
    schema.
  - A reader no longer deadlocks the writer on its node productions.
  - Opening a store whose schema is already in place no longer takes a table lock, which had held
    asks behind the indexer for up to 29 s.
- **A Qdrant store nothing writes to creates no collections.**

- **A run's `model_versions` names the embedding model the run actually called.** A model chosen
  only by `[packs.openai] embedding_model` was recorded as the stage's default,
  `text-embedding-3-small`, so two runs that differed only in that setting compared as though
  they did not differ.

- **`weft ask … | head -1` ends quietly.** When the reader of a streamed answer went away, the
  command blamed the model provider and exited 1 with `'generate' failed: ReaderGoneError`. It now
  exits without a message, the way other commands already did when their reader closed.
- **An unmapped role's refusal prints a line that works.** It suggested
  `route = { provider = "scripted" }`, and following it exited 4 because `scripted` cannot give a
  role a structured answer; it also printed a second `[llm.roles]` header into files that already
  had one. It now names an installed provider with a `<model>` placeholder, prints only the entry
  line when the table exists, and says to `pip install "weft-rag[openai]"` when nothing else is
  installed.
- **Qdrant's text search honours a filter the way pgvector's does.** A filtered lexical query
  returned the filter's other nodes at score zero alongside the real matches; it now returns only
  nodes that share a term with the query.
- **`[llm.retry]` is the only retry a model call gets.** The OpenAI SDK retried each failure
  itself, so three attempts could send nine requests; the `openai` and `openai-compatible`
  providers now turn the SDK's retries off for model calls. `max_retries` still applies to the
  account's embeddings and image descriptions.

## [2.7.0] - 2026-09-14

**`weft-kernel` moves `0.2.0` → `0.2.1` with no change to its code.** It is republished only
because the release publishes both distributions and a version on PyPI is not reusable.

### Added

- **`weft eval baseline`** takes the published baseline measurement from an installed wheel —
  staging a corpus manifest's tiers, verifying their bytes, indexing through a named pipeline
  (default: the shipped `baseline` document) and retrieving every scoreable question more than
  once — with no checkout and no `weft` subprocess.
- **`weft eval compare <published report> <later report>`** judges a reproduction: every published
  metric inside its own repetition interval, on what the pipeline states rather than on how it was
  packaged. `docs/REPRODUCING.md` is a transcript of doing exactly that, and the release's
  reproduction archive carries the corpus fetcher it needs.
- **A token sink per call.** `Weft.ask`, `Weft.index` and `Weft.run` take `token_sink=`, so two
  concurrent calls on one session stream into separate sinks; each is closed once when its call
  ends. Omitted, a call streams into the session's sink as before.

### Changed

- **An argument that breaks its command's own constraint is a usage error.** `weft index … --batch-size
  0` prints `argument --batch-size: Input should be greater than 0` and exits `2`, as any other usage
  error does; it used to exit `1` with the validation library's own untranslated message. Under
  `--json` the refusal is the error envelope, `"error": "CommandArgumentsError"`.
- **`weft eval compare` reports which distributions were active, and at which versions, beside a
  comparison instead of refusing it** — `packaging differs, reported not refused: …`. A version bump
  alone had been refusing comparisons of runs on the same corpus and model versions. Corpus, digest
  basis, model versions and question set still refuse. *A script that branched on exit `1` for a
  packaging-only difference now sees `0` and the reported line.*
- **A Qdrant collection missing a vector this store writes is refused on first use, naming the
  remedy**, instead of failing mid-write with Qdrant's own `400 (Bad Request)`. A collection indexed
  by `2.4.0` has no sparse `lexical` vector; point `[packs.qdrant] collection` at a new name and
  re-index, or delete the collection and re-index into the same name.

### Removed

- **`Weft.ask(..., retrieve_only=...)`.** A retrieve-only run produces ranked passages and no
  answer, so behind `ask`'s `-> Answer` it raised on every call. **Migration:**
  `await weft.run("ask", {"question": question, "retrieve_only": True})` returns the passages.

### Fixed

- **`weft index --pipeline index-qdrant` works in a project with no Postgres `dsn`.** A pipeline
  that extends another no longer needs a plugin its own changes replaced.
- **`weft_store.conformance.register_conformance_ext_models()` registers every ext model the kit's
  own checks attach**, so a store author running the kit alone no longer meets failures that only
  a full `weft` installation's discovery had been hiding.
- **The README stopped calling a three-day-old date "today".**

## [2.6.0] - 2026-09-14

**`weft-kernel` moves `0.1.0` → `0.2.0` with this release** — purely additive (`carry_forward` on
the payload package, `aclose` at the seam), nothing removed, which under **G9** is a minor for a
caller and for an implementer alike.

**There is no 2.5.0 on the index and there never will be.** `weft-rag`'s version moved twice
between releases while nothing was cut, so `2.6.0` is the first published release since `2.4.0`
and carries everything below. A version number on PyPI is not reusable and a skipped one is not
recoverable; it is recorded here rather than quietly renumbered.

*(This entry was dated 2026-09-13 and nothing was published under it — the same "prepared but not
cut" state that produced the missing 2.5.0, one release later. Rather than let it become a second
unreachable number, `2.6.0` stayed unclaimed on the index and **grew**: everything Phase 28 added
on 2026-09-13 and 2026-09-14 is in the lists below, and the heading now carries the day it was
actually cut. Phase 28's own exit is what found it — the route it wrote is true of a clone and was
false of every wheel a stranger could install.)*

### Added

- **An embeddable Python API.** `from weft_engine.api import Weft` — `async with Weft.open(config)
  as weft: await weft.run("ask", {"question": ...})`. One verb over the same `Command` registry the
  CLI drives, so **every** installed command is reachable from Python, including one a pack you
  wrote contributed. It is not a second code path: the CLI and the library assemble the same
  services and run the same invocation seam. `manual/user-manual.md` carries the Python half.
- **A store conformance kit you can import.** `weft_store.conformance` — hand it your own
  `NodeStore` and it runs the checks your store's capabilities can actually answer, and **names
  the ones it left out** rather than silently passing a smaller store. 28 checks across four
  capability tiers: `NodeStore`, `VectorSearch`, `TextSearch` and `MetadataFilter`. Previously
  this kit existed and only this repository could run it.
- **`weft pack new`** scaffolds a pack — entry point, settings namespace, a registered plugin and
  a test — so starting one is an artefact you re-run rather than a page you follow.
- **An in-memory store**, so writing and testing a plugin needs no container at all. It satisfies
  `NodeStore`, `VectorSearch` and `MetadataFilter`, and deliberately not `TextSearch`; the
  conformance kit tells you so by name instead of skipping quietly.
- **Real BM25, in both stores.** `pgvector` gains `[packs.store] text_mode`: `fts` (the default,
  Postgres `ts_rank_cd` cover-density ranking) or `bm25`, Okapi BM25 via the `pg_textsearch`
  extension — `docker compose --profile bm25 up -d` brings up an image carrying it. `qdrant` now
  satisfies `TextSearch` at all, ranking by BM25 over a named sparse vector with the IDF computed
  across your collection by Qdrant itself. **`TextSearch` stops being a contract only Postgres can
  meet**, which is the property that made it worth publishing.
- **A second fuser.** `normalized-score-fusion` min-max normalises each arm's own scores and sums
  them, beside the default `reciprocal-rank-fusion`, with the pipeline `hybrid-normalized-scores`
  selecting it. A node an arm never returned contributes **nothing** from that arm — absence, not
  a fabricated zero. **Neither is the default and this release does not move one**: see *What did
  not change*, below.
- **Each arm's own scores survive fusion.** A fused `Ranking` carries `FusionEvidence` — per arm,
  the label, and each node's score and rank as that arm reported them — so a fused result can be
  explained rather than guessed at.
- **Incremental ingestion.** `weft index` skips a document whose content has not changed, and says
  how many it skipped; `--reprocess` forces the work anyway. `--batch-size` bounds memory by
  processing the corpus in chunks, and a pipeline holding a stage whose output depends on which
  other documents were in the call is **refused by name** rather than silently redefined. An index
  killed halfway now leaves a record saying so instead of no trace at all.
- **`weft ask --explain`** prints what a score means in the words of whatever produced it, and
  `[packs.store] text_rank_normalization` makes Postgres's passage-length handling an operator's
  choice rather than a constant.
- **Evaluation you can compare.** A `RunRecord` now names the query pipeline it scored, the
  version of every active distribution, and **one score per question per metric** — so
  `weft eval compare` reports a paired difference over questions with an interval, beside the
  spread between runs, and refuses two runs that are not comparable. Polish is scored as Polish.
- **Provider reach.** `base_url` is documented and a second `[llm.accounts]` entry is
  representable, so local embeddings with a hosted chat model stops being one endpoint pretending
  to be two.

- **A lexical retrieval rung that needs no account, no model and no download.**
  `weft ask "<question>" --pipeline lexical-retrieve --retrieve-only` searches the store's text
  arm — real BM25-class ranking, `ts_rank_cd` in pgvector by default — and prints the passages.
  Until now the only route to that arm was `hybrid-*`, every one of which ends in a generated
  answer and so needs a model configured; the capability shipped in 2.6.0's own work and could not
  be reached. This is what a first hour looks like on a machine with no credentials: a question
  turning on an exact token — a name, an identifier, an error code — answered correctly.
- **`--retrieve-only` accepts `--pipeline`.** The two flags were refused together; they are only
  contradictory when the named pipeline would call a model. Naming one that ends in retrieval now
  runs it and stops at the passages, which is `--retrieve-only`'s own contract asked of a document
  you chose rather than of the hardwired vector search. A pipeline that *would* generate is still
  refused by name, before anything is constructed, and the refusal lists the ones that would work.
- **`embedding_model` on `[packs.openai]` and `[packs.openai-compatible]`.** Which model an account
  serves when no pipeline stage names one — and the only surface the *query* side could ever
  reach, since `weft ask` builds its embedder from `[services] embed` and never from a document.
  Without it a corpus embedded by one model was queried against another, which against a server you
  run is usually a model name that does not exist. A stage's own `with: {model = "..."}` still
  wins.
- **`weft plugins doctor` says what the default embedder is**, when nothing chose one — the same
  sentence `weft index` prints and `weft init` scaffolds, in one place rather than four wordings.

### Changed

- `weft index` counts **documents**, in documents, and says so. It previously printed a number
  whose unit a reader had to infer.
- `--json` writes the command's typed result rather than prose about it.
- `weft_store.contract.Removed` gains `narrowed_count`, optional, defaulting `0`.
  `STORE_CONTRACT_VERSION` moves `2.4.0` → `2.6.0`.
- A pack's resource closing happens at the seam, so no caller reaches for a `getattr` to find out
  whether a plugin has a `close`.
- The public pages hand to each other by name and none of them links into a directory that is not
  in your clone. `README.md` → the quickstart → the user manual → the pack author guide, with
  `docs/08-manuals.md` §1 owning that order and a check failing the build when a hand-off, a shared
  block or a sentence beside an unexecuted block stops being true.

### Deprecated

- **The `keybert` enhancer is renamed to `term-frequency-keywords`.** The old name still works and
  still resolves to the same plugin; selecting it now prints a deprecation notice naming the new
  one. Change `use: keybert` to `use: term-frequency-keywords` in any pipeline document of your
  own — nothing else about the stage moves, and its `top_n` means what it meant. **Removed in
  `weft-rag` 3.0.0.**

  **Why.** It ranks tokens by frequency against a fixed stoplist. KeyBERT ranks n-grams by cosine
  similarity to a transformer embedding of the document, which is a different technique and a
  better one; naming this after it claimed an outcome the code does not produce. The tell is in
  its own output — indexing ordinary prose stored `["microkernel", "every", "capability",
  "plugin", "pipeline"]`, and `"every"` is in that list because the ranking is counting.

  **What it does, stated plainly, because the old name was doing the explaining:** it attaches a
  node's most frequent tokens as namespaced extension data. **Nothing in Weft retrieves through
  it** — the terms are stored beside the node and the text index is built from the node's content,
  which already contains every one of them. It is metadata for a reader or for a consumer you
  write.

### Fixed

- **Two byte-identical documents in one corpus no longer take each other's nodes.** Node ids are
  content digests that exclude the source, so both documents derive one node — that dedup is
  intended — but `add` replaced the node's `sources` with the incoming document's alone, so the
  second ingest took the first's nodes and `weft delete` on the first reported success having
  removed nothing while its content stayed retrievable. The store now records, per node, the set
  of **productions** that wrote it, and a deletion drops the productions naming the departing
  document: the node goes when none survives and is **narrowed** when one does. A `Node.combine`
  summary arrives as one production over several documents and is still deleted with any of them,
  unchanged. `weft delete` reports both numbers — `0 node(s) removed, 1 narrowed`.
  **A corpus indexed before this release keeps the old behaviour until it is re-indexed**: every
  existing node is migrated to one production equal to its recorded `sources`, which is the only
  honest reading of a row whose history was never kept.
- **A mistyped corpus path stops reading as a successful run.** `weft index` told an empty
  directory, a path that does not exist and a path that is a file apart — all three previously
  printed `nothing to produce` and exited `0`.
- **A page number is a fact about a node**, not a character offset into text a cleaner is about to
  rewrite. Measured against 1024 real chunks, **72 of them (7.0%)** carried the wrong page; the
  coordinate system is retired rather than tracked. A stored node written before this release is
  **loudly unreadable** rather than quietly wrong. **Migration:** re-index the corpus with
  `weft index <directory> --reprocess`, which rewrites every node under the new coordinates.
- **The pages a stranger reads first stop overstating what the default does.** The README and the quickstart
  now say that the default embedder is a smoke test whose ranking carries no meaning, `weft index`
  says when the embedder was a default rather than a choice, and `weft plugins doctor` discloses
  what that default is and is not. The operations guide stops telling you `qdrant` has no text
  search, which stopped being true in this release.

### What did not change, and why it is here

**No retrieval default moved.** Both of this release's new retrieval capabilities won their arm of
a crossed measurement over this project's own corpus, and neither became the default. Under
`reciprocal-rank-fusion`, swapping Postgres full-text search for real BM25 moves `precision@5` and
`recall@5` by **exactly nothing** — identical to four decimal places, with zero-width paired
intervals — because rank fusion reads each arm as an ordering and discards what it scored. Under
`normalized-score-fusion` the same swap moves `recall@5` from `0.5117` to `0.8333`. The two factors
interact, and the reason neither default moves is that the dense arm in those runs was Weft's hash
embedder, whose vectors carry no meaning: score fusion's advantage may be its ability to *see* that
one arm is noise rather than any general property of score fusion. Re-run it with a real encoder
configured under `[services] embed` and the answer is yours to act on. `weft eval compare
hybrid-normalized-scores hybrid-then-generate` is the command.

## [2.4.0] - 2026-09-11

### Added

- **The distribution is `weft-rag`; the command is `weft`.** `weft` itself is another project's
  name on PyPI (101 releases, unrelated), so this project cannot publish under it — `weft-rag` is
  what `pip install` names, and the console script the wheel places on your `PATH` is still `weft`
  (**G18**, 2026-09-09; `docs/internal/README.md`'s decision log owns the lookup that found the collision).
- **Phase 0 — the walking skeleton.** The kernel (registry, discovery, the pipeline model, the
  payload types), `weft-cli` (the one driving adapter and the one `asyncio.run` in the tree), and
  the first capability packs — `weft-extract`, `weft-chunk`, `weft-store`, `weft-embed` — plus the
  discovery, extension and trust-model fitness functions (0, 1, 3, 8, 9) that keep them honest.
- **Phase 1 — pipelines as data.** The four-operator derivation set, closed by a named constant
  (fitness function 11a — a fifth operator fails the build until someone changes the constant and
  records why), and every shipped pipeline proven to resolve against the installed registry in
  `ci-checks` (fitness function 11b).
- **Phase 2 — retrieval and generation.** `weft-pdf`, `weft-openai`, `weft-retrieve`,
  `weft-generate`, `weft-qdrant`, `weft-llm`, `weft-index` — the retrieval and generation contract
  families, a router that picks a strategy from the registry with no enum and no closed key space
  (fitness function 4), and the filter AST the store contract family speaks.
- **Phase 3 — the command surface.** `weft-command` and the `Command` contract — CLI verbs are
  plugins too, each declaring its own permission `ClassVar` rather than living in a hard-coded list.
- **Phase 4 — evaluation and observability.** `weft-eval` — retrieval and generation metrics,
  persisted `RunRecord`s, `weft eval run`/`compare`/`metrics`, `weft trace`, and a tool that
  generates its own comparison across two derived pipelines run over one corpus.
- **Phase 5 — the extension model (G7 and G9 settled).** `weft-otel`, setting the
  process `TracerProvider` from a pack with no core edit (5.1d); the store-family
  `SourceDeletable`/`Reconcilable` protocols behind `weft delete` and `weft reconcile`, and the
  `repair`/`full` reconciliation modes a person opts into rather than one that surprises them
  (5.1a–5.1c); fitness function 13, closing a `FilterOp` dispatch gap so an added enum member is
  refused everywhere rather than silently answered as the wrong query (5.2b); mandatory
  `ExtModel.__schema_version__`, so a pack reads back what an older version of itself wrote, or
  refuses by name instead of silently misreading it (5.2c); the structured `--json` error envelope
  carrying a `WeftError` subclass name and `valid_options` as data rather than prose to parse
  (5.2d); `weft plugins doctor` reporting version skew and a deprecated-surface flag, and the
  registration-time deprecation mechanism (`PackRegistrar.deprecate`) behind it (5.2e); this file,
  brought current and checked against that mechanism (5.2f).
- **Phase 6 — release (G10 settled 2026-09-05).** The repository became something a stranger can
  install: a release workflow publishing **eight** distributions from one repository, each with its
  own version, and a published baseline measurement so *"it works"* is a number somebody else can
  reproduce. The eight are `weft-rag` (the default install), `weft-kernel`, `weft-pdf`,
  `weft-openai`, `weft-qdrant`, `weft-otel`, `weft-agent` and `weft-docling`. Fitness function 10
  compares the names the release job actually publishes against the workspace members that do not
  opt out, read from two files that can genuinely disagree, so adding a distribution and forgetting
  to release it fails the build. The release job also carries a **cooling-off gate**: PyPI
  rate-limits project *creation* by attempts rather than successes, so a rerun inside the window
  extends the block instead of clearing it, and the workflow now refuses rather than relying on
  anyone remembering that.
- **Phase 7 — the agent.** `weft-agent` and `weft agent` — a model that plans, calls Weft's
  published commands as tools, and acts on a corpus. It ships as an ordinary first-party pack, not
  as part of the CLI, and fitness function 21 asserts exactly that: it registers through the same
  public entry point a third party uses and receives nothing extra. The planning loop is therefore
  driven by the REPL, a script and an HTTP caller alike.
- **Phase 8 — from engine to product.** The phase about the distance between what the engine can
  express and what a user can reach. It began as a measurement: four pipeline documents in the whole
  tree, naming ten plugins, against forty-eight plugins registered into pipeline positions — so
  *"naive to advanced, quickly"* was true of the engine and false of the product. **Thirty-five
  pipeline documents ship today**, and fitness function 16 fails the build when a distribution
  registers a plugin into a pipeline position that no shipped document names. Also: `weft render`,
  which prints what Weft actually sees in a file before you trust an index built from it; and
  `[services] route` in `weft.toml`, so an operator can author a router rather than only select
  among the ones that ship.
- **Phase 9 — figures and tables as nodes.** `MediaType.IMAGE` and `MediaType.TABLE` have been in
  the payload model since Phase 0 and nothing produced either. Now a table and a figure in a
  born-digital PDF become nodes: `weft-docling` extracts them, a figure's pixels live outside the
  payload behind a blob store (fitness function 24 refuses `bytes` in a `Node`), and a describer is
  a stage a pipeline names or removes. **The expensive architecture was measured before it was
  built, and the measurement said not to build it**: captions reached `recall@1 = 0.900` against
  pixel embedding, so the pixel-embedding tasks were deliberately left unticked rather than
  written.
- **Phase 10 — RAPTOR, extended.** `raptor` has shipped as a registered `Expander` since Phase 2;
  this phase extended it against its source papers rather than adding a new capability —
  configurable clustering and level depth, run facts recorded on the nodes it produces, and the
  `index-with-raptor` document that actually builds a tree. New alongside it: **`adrap`**, which
  joins a newly indexed document into an *existing* tree rather than rebuilding it, shipped as
  `index-with-adrap`; and the `Revisable` and `NodeSupersedable` contracts behind it, so a plugin
  can replace a stored node with a differently-shaped successor through a published protocol.
- **Phase 11 — the graph pack.** `weft_kg` — entities, aliases, facts, mentions and relations
  extracted from a corpus and reachable from `weft ask`. `index-with-facts` builds the graph
  alongside the ordinary vector index; `graph-then-generate` and `graph-and-vector-rrf` answer
  through it, citing across both stores; `weft graph bridges` and `weft graph neighbours` inspect it
  directly; and `weft delete`/`weft reconcile` reach its rows by kind (`node`, `alias`, `entity`,
  `fact`, `mention`, `relation`) alongside the ordinary node store. Entity resolution has two rungs:
  a free, co-occurrence pass with no model and no credential, and an opt-in `full` pass — `index-
  with-facts-openai` — that merges duplicate entities with a real model and states its `model_calls`
  before it spends one. An operator curates the extraction schema a corpus proposes and activates it
  per collection from a project file, so what was approved is a diffable artefact. Ships as an
  ordinary module inside `weft-rag`, needing no extra — its one dependency, `psycopg`, is already
  part of the default install. On one twelve-document corpus, questions that require a graph hop
  scored `1.000` through the graph compared to `0.375`–`0.500` through vector retrieval alone
  (`weft eval compare --kind requires-graph-hop`).

### Changed

- `COMMAND_CONTRACT_VERSION` corrected from a mis-recorded `1.1.0` to `2.0.0` — task 3.2 added a
  name to `required_declarations`, which breaks every `Command` implementer that does not declare
  one, and is therefore major for an implementer even though it is additive for a caller
  (`docs/09-release.md` §2.3's two-audience rule).
- Every first-party distribution's declared dependency on another now carries a real range
  (`>=X,<MAJOR+1`), never a bare name or an exact pin (task 5.2a).
- **Twenty published names became eight (G10, 2026-09-05).** `weft-command`, `weft-extract`,
  `weft-chunk`, `weft-clean`, `weft-embed`, `weft-enhance`, `weft-index`, `weft-store`,
  `weft-retrieve`, `weft-generate`, `weft-llm`, `weft-prompts`, `weft-eval` and `weft-cli` are no
  longer published separately: they ship inside `weft-rag`. **A pack's identity is not its
  distribution** — each is still a pack with its own entry point, its own `[packs.*]` configuration
  namespace and its own `weft plugins doctor` row, so nothing about how you configure or refuse one
  changed. What changed is how many wheels you install to get them.
- **Eight published names became two (G19, 2026-09-09), before any of the eight ever reached an
  index.** `weft-pdf`, `weft-openai`, `weft-qdrant`, `weft-otel`, `weft-docling`, `weft-agent` and
  `weft-kg` are not published distributions and never will be: their code ships inside `weft-rag`,
  behind an extra where they carry an outside library a user may want to decline
  (`weft-rag[pdf]`, `[openai]`, `[qdrant]`, `[otel]`, `[docling]`, or `[all]` for every one of them),
  and unconditionally where they do not (`agent`, `graph` — `graph`'s one dependency, `psycopg`, is
  already part of the default install). `weft-kernel` is the only distribution besides `weft-rag`
  that this project publishes, kept separate solely so it can be installed alone and imported on its
  own. This is the release-day state: install `weft-rag`, not any of the seven names above.
- **`weft --json` now emits only JSON on stdout for a routed answer.** It previously wrote
  well-formed events and then printed the pipeline name and citations as prose, so nothing
  downstream could parse the output — the guard read `weft ask --format json`, a different flag. The
  run now ends with one `answer-envelope` line, discriminated by the same `kind` key the existing
  `stream-event` and `error-envelope` lines carry, holding the pipeline name, the answer text and
  every citation field. **This is additive**: no existing line changed name, shape or meaning.
- **A citation now names the node it came from, and its page when there is one.** The human
  rendering was `[marker] uri` alone, so several passages cut from one document cited identically
  and which node answered was unobservable.

### Deprecated

Nothing yet. The mechanism exists (5.2e) and this file's coverage of it is enforced (5.2f); no
first-party surface has used it.

### Removed

- **`weft-command`, `weft-embed`, `weft-generate` and `weft-llm` are yanked from PyPI as of
  2026-09-11.** These four reached the index at `0.1.0` on 2026-09-05, before G10's own
  eight-distribution set was itself superseded by **G19**'s two. Yanked rather than deleted, so the
  names stay reserved and cannot be picked up by an unrelated project — anyone who installed one of
  them should install `weft-rag` instead; the code they carried ships there now.

### Known gaps

- **A citation's `page` is `None` on every text pipeline.** Every cleaner rebuilds its node in a way
  that drops the extraction-time facts a page number is resolved from. The obvious repairs were
  measured and both fail — carrying the facts through verbatim mis-states the page by up to three
  pages, because the page index and the chunk offsets end up counting different text — so this is
  open as grilling session **G17** rather than guessed at. `page` is honest today: it says the page
  is unknown, not that the passage is on page 1.
