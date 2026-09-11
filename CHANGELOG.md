# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html) **per distribution** — `weft`
ships as several packages (`docs/README.md` → *Where things are*), not one, and each carries its own
version, tracked in its own `pyproject.toml`. This file does not repeat those numbers — a second,
hand-copied list of them is exactly the two-lists bug `docs/README.md` opens with, aimed at version
digits instead of prose — it records what changed, and why, for someone using the software.

**Architecture decisions are not changelog entries.** They live in the decision log in
[`docs/README.md`](docs/README.md), which records what was decided, when, and where the reasoning is
written down.

**First release: 2026-09-11, tag `v2.4.0`.** `weft-rag` and `weft-kernel` are the two names this
project publishes (**G19**, 2026-09-09 — a new capability never adds a third; `docs/README.md`'s
decision log owns the reasoning). Measured 2026-09-08, before that gate closed: all eight names G10
had published under returned 404 on PyPI — this is the first index publication either successor name
has ever had. Four retired, pre-consolidation names (`weft-command`, `weft-embed`, `weft-generate`,
`weft-llm`) reached PyPI at `0.1.0` on 2026-09-05 before a rate limit stopped the rest; their code
ships inside `weft-rag` now, and all four are **yanked** as of this release (see *Removed*, below).

> **This file went stale again, and the way it did is worth more than the apology.** `docs/lessons.md`
> L5.8 was written because this changelog was nineteen lines, touched once, and unmoved while five
> phases shipped around it. Task 5.2f brought it current and added a check
> (`tests/docs/test_changelog_deprecation_coverage.py`) — and then it sat untouched through **five
> more** phases, 6 through 10. The check is not broken and it did not fail: its subject is
> *deprecations*, of which this tree has zero, so it passes by asking nothing about the rest of the
> file. A check whose real subject is legitimately empty cannot notice the artefact rotting around
> it, which is `L5.19`'s own shape landing on the artefact `L5.8` was written to protect. Brought
> current here in the commit that prepares the first release.

## [Unreleased]

## [2.4.0] - 2026-09-11

### Added

- **The distribution is `weft-rag`; the command is `weft`.** `weft` itself is another project's
  name on PyPI (101 releases, unrelated), so this project cannot publish under it — `weft-rag` is
  what `pip install` names, and the console script the wheel places on your `PATH` is still `weft`
  (**G18**, 2026-09-09; `docs/README.md`'s decision log owns the lookup that found the collision).
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
