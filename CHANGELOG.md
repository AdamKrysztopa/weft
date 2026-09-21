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
