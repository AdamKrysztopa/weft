# Running Weft

Written for someone who runs Weft, not someone who builds it. It answers three questions: how do
I bring the one container up, how do I wire Weft to it, and when `weft plugins doctor` or an exit
code tells me something, what do I do about it. Definitions link to
[`docs/02-extension-model.md`](../docs/02-extension-model.md) §2 and
[`docs/03-cli.md`](../docs/03-cli.md) rather than restating them — this page is the task, not the
argument for why it is shaped this way.

## The one container

Weft's runtime shape gives a container to exactly one thing: the database. This is the repository's
own `compose.yaml`, included here rather than retyped, so this page cannot show a topology that no
longer matches what ships:

> **You will see two services below, and Weft still needs one.** `postgres` is the one — bring it
> up and everything works. `qdrant` is a second *backend*, not a second *requirement*: it exists so
> the store contract is proven against a database of a genuinely different shape, which is what G4
> traded the zero-container target for ([`docs/01-high-level-plan.md`](../docs/01-high-level-plan.md)
> → *Runtime shape*). Nothing runs against both at once — the backend is chosen in configuration
> like any other plugin. `docker compose up -d` is unchanged and still starts only Postgres, because `qdrant` sits behind a
> `conformance` profile; `docker compose --profile conformance up -d qdrant` is how you ask for it.

```yaml path=compose.yaml
# The one container Weft's runtime shape allows — `docs/01-high-level-plan.md`
# → *Runtime shape*: "the only thing that gets a container is the database."
# G4 retired the zero-container target and made pgvector the floor
# (`docs/06-phase-0-build.md` step 8), so this is where it arrives.
#
# `docker compose up -d` brings it up, and the store creates its own schema on
# first use — there is no separate migration step to run first.
#
# **Bringing the container up is not enough to make the store usable.** The `store` pack
# requires a `dsn` in its pack settings, and there are two ways to supply it. With no
# `weft.toml` at all, an exported `WEFT_DATABASE_URL` is offered as `dsn` and the store
# comes up `active` — the no-file path `manual/quickstart.md` walks. A `weft.toml`
# carrying `[packs.store] dsn` — see `weft.toml.example` — wins over the
# environment, key by key. `weft plugins doctor` reports `store (weft-rag): failed`, naming
# the missing field, only when NEITHER supplies a `dsn` — the loud failure working: the
# pack refuses rather than defaulting to some database it guessed.
#
# Port 5433, not 5432: `.env.example` explains why — a bare default port on a
# developer's machine belongs to whichever Postgres happened to claim it
# first, and this project's store is namespaced everywhere else too.
services:
  postgres:
    image: pgvector/pgvector:pg16
    # Docker's default /dev/shm is 64 MB. pgvector's parallel HNSW build keeps its shared build
    # state there, and it failed at 100,142 rows of vector(1536) on 2026-09-16 (Phase 29).
    shm_size: 1gb
    environment:
      POSTGRES_USER: weft
      POSTGRES_PASSWORD: weft
      POSTGRES_DB: weft
    ports:
      - "5433:5432"
    volumes:
      - weft-postgres-data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U weft -d weft"]
      interval: 2s
      timeout: 3s
      retries: 20

  # The second backend, and it is not a second requirement. `01` → *Runtime shape*
  # says one container is the floor and it is pgvector; G4 moved the over-fitting
  # guard rather than deleting it, and named the pair it moves to: "the contract is
  # proven on **pgvector and Qdrant**, which have genuinely different shapes, and a
  # store that only Postgres can satisfy fails that test just as loudly."
  #
  # So this service exists to be *proof*, not to be deployed alongside the first one.
  # Nothing in Weft requires both at once: the backend is chosen in configuration like
  # any other plugin, and the store conformance suite is the only thing that asks for
  # this one.
  #
  # Port 6333 is Qdrant's own default and is not remapped, because — unlike Postgres —
  # there is no widespread convention of one already running on a developer's machine.
  # If that stops being true, remap it here and say so in `.env.example`, the same way
  # 5433 is explained there.
  #
  # It sits behind a profile, so `docker compose up -d` still means what this file's
  # opening line says it means: the one container, and it is the database. Starting
  # it takes `--profile conformance` and is therefore a thing you did on purpose.
  qdrant:
    image: qdrant/qdrant:v1.12.4
    profiles: ["conformance"]
    ports:
      - "6333:6333"
    volumes:
      - weft-qdrant-data:/qdrant/storage
    healthcheck:
      # The image carries neither curl nor wget, so the check speaks HTTP itself
      # through bash's /dev/tcp. `CMD` with an explicit `bash` rather than `CMD-SHELL`,
      # because the image's `/bin/sh` is dash and dash has no /dev/tcp — a `CMD-SHELL`
      # form here reports unhealthy forever while the service is in fact serving.
      # `/readyz` rather than `/healthz`: healthz answers as soon as the process is up,
      # readyz waits until the shards are, and a store that answers before it can search
      # is exactly the race an integration test would hit.
      test: ["CMD", "bash", "-c", "exec 3<>/dev/tcp/127.0.0.1/6333 && printf 'GET /readyz HTTP/1.1\\r\\nHost: localhost\\r\\nConnection: close\\r\\n\\r\\n' >&3 && grep -q 'all shards are ready' <&3"]
      interval: 2s
      timeout: 3s
      retries: 20


  # **Real BM25, and it is not the floor.** `TextSearch` has never promised BM25 — the floor
  # store ranks `content_tsv` with `ts_rank_cd`, which has no IDF over the collection and no term
  # saturation. `timescale/pg_textsearch` is the permissive-licensed extension that does
  # (PostgreSQL licence, v1.4.0, 18 August 2026), and it needs PostgreSQL 17 or 18. The floor is
  # `pg16`.
  #
  # **So this is a second service behind a profile, on `qdrant`'s own precedent above, and for
  # the same reason: it exists to be a capability an operator opts into, not one they carry.**
  # `docker compose up -d` still means what this file's opening line says it means. Starting this
  # one takes `--profile bm25` and is therefore a thing you did on purpose.
  #
  # The measured cost of not doing it this way: `timescale/timescaledb-ha:pg17` is **3.86 GB**
  # against the floor image's **640 MB**, and it carries a TimescaleDB Community Edition surface
  # (TSL-licensed) that Weft does not use. Moving the floor to it would put that in front of every
  # developer for a capability most of them have not asked for — against `01` → *Runtime shape*
  # and against this project's own offline-clean-checkout pitch.
  #
  # Verified on 2026-09-13 by running it: this image reports `pg_textsearch 1.4.0` and
  # `vector 0.8.6` — the same pgvector the floor runs — and `CREATE EXTENSION` succeeds for both.
  # The leaner `timescale/timescaledb:latest-pg17` was checked and carries `vector 0.8.1` with
  # **no** `pg_textsearch`; no dedicated `pg_textsearch` image is published. A count and a version
  # about an image, so re-take them rather than cite them.
  #
  # Port 5434: 5432 belongs to whatever Postgres a developer already runs and 5433 is the floor,
  # for the reason `.env.example` gives for both.
  postgres-bm25:
    image: timescale/timescaledb-ha:pg17
    profiles: ["bm25"]
    # The same 64 MB /dev/shm limit, and this image sets maintenance_work_mem to ~980 MB.
    shm_size: 1gb
    environment:
      POSTGRES_USER: weft
      POSTGRES_PASSWORD: weft
      POSTGRES_DB: weft
    ports:
      - "5434:5432"
    volumes:
      - weft-postgres-bm25-data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U weft -d weft"]
      interval: 2s
      timeout: 3s
      retries: 20

volumes:
  weft-postgres-data:
  weft-qdrant-data:
  weft-postgres-bm25-data:
```

```bash
docker compose up -d
```

That is the whole operation, and it starts one container. There is no migration command to run
afterward — the store creates its own schema the first time anything writes to it — and nothing
else to start: everything that is not the database runs inside the `weft` process itself. The
`qdrant` service in the file above is not started by this command and is not part of running Weft;
it is brought up only by the conformance suite, which asks for it by profile.

## Wiring `weft.toml`

The `store` pack takes its connection string from its own pack settings, `[packs.store] dsn` —
the **pack** name, which is what `weft plugins list` prints in its first column, and not the name
of the distribution that ships it. There are two ways to supply it. **With no `weft.toml` at all**
— the path `manual/quickstart.md` walks — an exported `WEFT_DATABASE_URL` is offered as `dsn` on
its own, and that is enough to bring the store up. A project that wants an explicit, committed connection string instead copies
`weft.toml.example`:

```toml
[packs.store]
dsn = "${env:WEFT_DATABASE_URL}"
```

`${env:VAR}` is interpolated by the settings loader before a pack ever sees its settings, so a
secret lives in the environment and a project can still commit the file that names which variable
it wants. Referencing a variable that is not set is a hard failure — `weft` refuses to build a
registry at all, naming the variable, rather than handing a pack half a connection string:

```text
'${env:WEFT_DATABASE_URL}' names an environment variable that is not set. Set WEFT_DATABASE_URL,
or remove the reference from the configuration.
```

**A `weft.toml` value wins over the environment, key by key.** The `store` pack's settings are built by
merging what `weft.toml` says over what `WEFT_DATABASE_URL` offers, and the file's own keys are
never overwritten by the environment — only keys the file leaves unsaid are filled from it. This
is deliberate: a stale `WEFT_DATABASE_URL` left over in a shell must never quietly redirect a
project whose `weft.toml` already names a different database. A store pointed at the wrong
database does not crash — it answers plausibly, against the wrong data, which is the failure this
project exists to remove. Concretely: with `WEFT_DATABASE_URL` pointed at a real, reachable
database and `weft.toml` naming a different, unreachable one, `weft plugins doctor` reports
`store (weft-rag): active` — the file's value is the one in play — and `weft ask` fails to connect,
exactly as it should for the database `weft.toml` actually named.

`weft.toml` is also where a project pins which packs may run at all:

```toml
[packs]
allow = ["weft-rag"]
```

**`allow` names distributions, and `[packs.<pack>]` names packs.** That asymmetry is deliberate:
`allow` is a trust decision, and trust attaches to the thing you installed from an index — so
listing `weft-rag` permits every pack that wheel ships, which is the same posture as before
(what you installed is what you allowed). Add `weft-openai` or `weft-qdrant` to the list to permit
an add-on you installed beside it.

Absent, the posture is open — every installed pack runs. Present, it is exhaustive: anything not
listed is refused, and refusal happens *before* the pack is ever imported, not after. This is a
statement of policy, not a sandbox — see *What this does not protect you from*, below.

**A pin has to permit the pack behind every plugin name the rest of the file selects.** Setting
`[services] embed = "openai-embeddings"` and leaving `weft-openai` off this list is a contradiction, and
`weft index` says so before it runs anything:

```text
[services] embed names 'openai-embeddings', and no registered Embedder has that name. These
distributions are refused by [packs] allow in weft.toml and were never imported, so what they
would have registered is unknown: weft-openai. Add the one that provides 'openai-embeddings' to
[packs] allow.
Registered Embedder names: 'hash'.
```

Exit `3`, not `4`: the name is a policy problem, and the key that fixes it is named. A refused
pack is never imported, so nothing can prove it is the one that would have claimed the name —
which is why the message says the packs are refused rather than claiming one of them provides it.

## Choosing an embedder

Weft ships two, registered under one contract, and `[services]` chooses between them:

```toml
[services]
embed = "openai-embeddings"

[packs.openai]
api_key = "${env:OPENAI_API_KEY}"
```

That block is the whole operation. No package is edited, nothing is reinstalled, and an embedder
some third party's pack registers is selectable by name the moment it is installed.

**`hash` is the default, and it is not a quality component.** `weft-embed`'s `hash` embedder turns
content into a deterministic vector and understands nothing about it: two documents on unrelated
topics are as "similar" to it as two ways of saying the same thing. It is what lets a clean checkout
index, search and pass its whole test suite with no account and no model download, and it is the
wrong thing to judge a retrieval result against. `weft-openai`'s `openai-embeddings` embedder
calls
`text-embedding-3-small` and produces vectors that do carry meaning; it needs a credential, and
every embedding is a metered API call.

**Changing this setting means reindexing.** A stored vector is only comparable to a question
embedded by the same model. Indexing with one embedder and asking with another compares vectors from
two unrelated spaces: when their widths differ the store refuses outright —

```text
weft ask: DataException: different vector dimensions 1536 and 64
```

— and when they happen to match, nothing refuses at all and the ranking is confident nonsense. So
after changing `[services] embed`, index into an empty store, or a store you have cleared.

**Where the credential comes from.** `weft-openai` reads its key from `[packs.openai] api_key`
and from nowhere else. It deliberately does *not* fall back to the `OPENAI_API_KEY` the vendor's own
SDK would read on its own — an exported variable that silently made a project work on one machine is
the same failure mode `weft.toml` beating `WEFT_DATABASE_URL` avoids for the database. `${env:...}`
is how the secret still stays out of the file. With no key configured at all the pack still
registers and `weft plugins doctor` still reports it `active`, deliberately: nothing is missing
until something asks it to embed, and then the failure names this exact line.

**Which model, and how wide — selectable from a file, with `--pipeline`.** `[services] embed`
chooses the *plugin* and carries no configuration; the model name, the `dimensions` a `-3` model
will shorten a vector to, and the batch size are the embedder stage's own `with:` configuration,
and reaching them means naming a document rather than a `[services]` key — ledger task **4.0**
closed the gap this paragraph used to describe (`weft_engine/services.py`'s own docstring recorded it
as open; `weft_cli.ingest`'s now carries the argument in full). `weft ask --pipeline <name>` has
resolved a document since ledger tasks 2.4/2.8; `weft index <path> --pipeline <name>` is the
identical bridge (`weft_cli.compile`), wired into the one command that lacked it:

```yaml
# pipelines/openai-1024.yaml
name: openai-1024
stages:
  - id: extract
    use: text
  - id: chunk
    use: fixed-size
  - id: embed
    use: openai-embeddings
    with: {model: text-embedding-3-large, dimensions: 1024, batch_size: 64}
  - id: store
    use: pgvector
```

```bash
weft index ./corpus --pipeline openai-1024
```

`[services] embed`/`[services] store` are not read for that run — a document's own `use:` on
every stage already names the plugin, so there is no config to merge them with (`weft_cli.ingest`'s
own module docstring, *"Q3, settled"*: the two surfaces stay split rather than growing a second
`{ use = …, with = … }` grammar inside `[services]`). Without `--pipeline`, `weft index` and
`weft ask --retrieve-only` are unchanged: `weft-openai` runs with its defaults —
`text-embedding-3-small`, the model's native 1536 components, 128 texts per request — and
`weft-embed`'s `hash` with its own, exactly as before.

## Choosing a store

Weft ships two backends, registered under one contract by two distributions, and `[services]`
chooses between them exactly as it chooses an embedder:

```toml
[services]
store = "qdrant"

[packs.qdrant]
url = "http://localhost:6333"
collection = "weft_nodes"
vector_size = 64
```

The `[services] store` line is what *selects* the backend; the `[packs.qdrant]` block
configures the pack once it is selected. Setting only the second changes nothing about which store
runs — a distinction worth stating, because the pack settings are the visible half.

**Changing this setting means reindexing, and for a blunter reason than the embedder's.** The corpus
does not move with the key. A store you have never written to holds nothing, so `weft ask` returns
no passages and reports no error at all; there is no width mismatch to refuse and no ranking to look
wrong. Run `weft index` against the store you named before you ask it anything.

**`pgvector` is the default and Qdrant is not a second requirement.** `compose.yaml` starts Postgres
alone; Qdrant sits behind a `--profile conformance` flag, because Weft's runtime shape allows one
container and it is the database. The second backend exists so the store contract is proven against
two engines of genuinely different shapes rather than fitted to one — see the *Capabilities differ
between backends* note below for what that difference costs you.

**How large a corpus the default store serves before a search passes 100 ms.** `pgvector` builds
no vector index. Every search is an exact scan over the stored vectors, so it gets slower as the
corpus grows, and faster or slower with the width of the embedder that filled it. These numbers
come from one machine: an Apple M4 Pro with 24 GiB running macOS 26.6.2, PostgreSQL 16.15 and
pgvector 0.8.6. Each row is the store's own search statement at `top_k` 10, taken over 200
queries in a database that nothing else was writing to:

| chunks | width | p50 | p95 |
|---|---|---|---|
| 10,000 | 64 | 2.8 ms | 3.3 ms |
| 100,000 | 64 | 15.1 ms | 18.4 ms |
| 10,000 | 1536 | 23.4 ms | 26.4 ms |
| 50,000 | 1536 | 82.2 ms | 93.9 ms |
| 60,000 | 1536 | 99.0 ms | 108.8 ms |
| 100,000 | 1536 | 149.3 ms | 168.1 ms |

At width 1536, the width `openai-embeddings` returns by default, **p95 passes 100 ms between
50,000 and 60,000 chunks**. At `hash`'s width of 64 it stays under 20 ms at 100,000. The 1536 rows
were timed on synthetic unit vectors, which an exact scan reads exactly as it reads a model's: its
cost depends on how many vectors there are and how wide they are, not on what they mean. These are
the store's numbers, not `weft ask`'s. Plan against them. End to end, a `weft ask --retrieve-only`
at 10,000 chunks and width 64 takes about **1.5 s** (p50; p95 1.7 s, three runs of 200 queries),
of which the search is under 3 ms. Most of the rest is Python importing the installed packs, and
the `[docling]` extra adds nothing to it until a pipeline uses its extractor.

**Above that, choose the Qdrant backend.** Set `[services] store = "qdrant"` as shown at the top of
this section and index the corpus into it. Qdrant keeps a vector index of its own, where the
default store scans every stored vector on every search. This guide states no Qdrant latency,
because none has been measured on the machine above. The reindexing note above still applies: the
corpus does not move with the key.

**Capabilities differ between backends, and a run that needs a missing one is refused before it
starts.** `pgvector` and `qdrant` both provide vector search, lexical text search and metadata
filtering; the in-memory store provides vector search and metadata filtering and no text search at
all. A pipeline whose retriever needs `TextSearch` fails with `StoreCapabilityMissingError` at run
assembly, naming the capability, what your store does advertise, and which registered stores
provide the rest.

**What differs between the two real backends is now the lexical ranking, not whether there is
one.** `qdrant` offers one: Okapi BM25, with the IDF computed over your collection by Qdrant's own
sparse-vector modifier. `pgvector` offers two, chosen by `[packs.store] text_mode` — `fts`, the
default, which is Postgres `ts_rank_cd` cover-density ranking under your configured
`text_rank_normalization`, and `bm25`, which is Okapi BM25 and needs the `pg_textsearch` extension
the `bm25` compose profile brings up. **None of the three numbers is comparable with either of the
others**, which is why each store *declares* what its text score means — `text_score_semantics`,
beside the `vector_score_semantics` `weft ask --retrieve-only --explain` already prints — rather
than leaving you to assume. Choosing a backend on the strength of its lexical ranking
is a measurement over your own corpus, and `weft eval compare` is what takes it — this project's
own crossed sweep found the swap from `fts` to `bm25` moving `precision@5` and `recall@5` by
exactly nothing under the default fuser, because reciprocal-rank fusion reads each arm as an
ordering and discards what it scored.

## Wiring the graph pack

The graph rungs — `index-with-graph`, `index-with-cooccurrence`, `index-with-facts`,
`index-with-facts-openai` on the ingest side, `graph-then-generate`, `graph-2hop-then-generate`,
`graph-then-rerank` and `graph-and-vector-rrf` on the query side — need **two** things wired, and
they are wired in different places because they are different kinds of fact.

```toml
[packs.graph]
dsn = "${env:WEFT_DATABASE_URL}"

[services]
graph = "pgvector-traversal"
```

**`[packs.graph] dsn` is where the pack's tables live**, and it is the same container
`[packs.store]` already uses — the pack creates its own `kg_*` tables in that database on first
use and sits *beside* the vector store rather than replacing it. **Exporting `WEFT_DATABASE_URL`
is not enough here, and it is enough for the node store.** That offer is made to the `store` pack
and to nothing else, deliberately: extending it would mean the CLI naming one capability pack in a
hard-coded literal, which is precisely what a pack built against nothing but the public API is
supposed to make unnecessary. So the convenience is one line in your own file. Unset, the first
call that genuinely needs a connection refuses at exit `1` and prints the two lines above.

**`[services] graph` is a different question — *which* registered traversal a run may use.** The
query rungs declare that they need a `GraphTraversal` from a run-wide service, and a run that asked
for a capability nothing was selected for is refused **by name at assembly**, before any stage
runs: *"stage 'retrieve' needs GraphTraversal from a run-wide service, and nothing is selected for
[services] graph. Nothing here adapts or degrades."* That is the posture everywhere in this
project — a missing capability is a refusal, never a quiet fallback to a lesser answer.

**The pack reports `active` with nothing configured, and that is correct.** `[packs.graph] dsn`
defaults to empty on purpose, where `weft-store`'s is mandatory: every project needs a node store,
and a project that never names the graph store should not have to read past a failure for a pack
it is not using. So `weft plugins doctor` can show `graph (weft-rag): active` on a machine where
the refusal above is one command away, and both statements are true.

**Order matters between the two sides.** A graph query rung answers from rows an *ingest* graph
rung wrote; pointing `graph-then-generate` at a corpus indexed through plain `index-text` walks an
empty graph and honestly returns nothing. `weft graph show` reports what the corpus actually holds,
and `weft graph bridges` will tell you outright when a corpus is too small to hold a question the
graph could answer and a single passage could not.

## Choosing which router decides

`weft ask` with no `--pipeline` runs a **router** — a pipeline document that scores the question and
selects another pipeline to answer it — and `[services] route` names which document that is:

```toml
[services]
route = "route-by-score"
```

Three routers ship, and they differ in *how closed* the choice is rather than in quality:

| `[services] route` | Policy | What it selects from |
|---|---|---|
| `route` *(default)* | `nearest-description` | Every installed pipeline that states a `route.summary`, matched against the question. **Open** — a rung installed today is selectable today, with no rule edit |
| `route-by-score` | `threshold-ladder` | Only what its own bands name, in order, first match wins. **Closed** — the shipped rules choose between `no-retrieval` and `retrieve-then-generate`, and every other rung is invisible to it until you add a band |
| `route-fixed` | `always` | One named pipeline, whatever the question. The scorecard is still produced and still travels into the trace; it is simply not consulted |

Pick `route-by-score` when you want exactly the behaviours you wrote down and want to know which one
ran and why. Pick `route-fixed` to pin behaviour — a benchmark that must hit one pipeline every
time, or an incident where you want the router out of the loop without losing the dimensions that
would show whether it was at fault. **`route-fixed` is not free**: `RoutingPolicy` takes a
`Scorecard`, so the scorer stage still runs and still costs one model call per question.

Only a pipeline an installed pack **contributed** can be named here — not a document in your own
`pipelines/` directory. A name nothing contributed is refused by listing every router that is
contributed, so a typo names its own alternatives.

> *(Added 2026-09-05 at ledger task 8.3, and it is a repair rather than a feature. Until then the
> router's name was a constant inside `weft-cli`, which made it the one pipeline nothing could
> substitute: a pack cannot contribute a second document under a name another pack already holds,
> and a project that ships its own `route.yaml` is refused outright — taking every `weft pipeline`
> command with it until the file is renamed. So `threshold-ladder` and `always` were registered,
> listed by `weft plugins list` and documented, and placeable by nobody.)*

## Choosing which model answers

Weft ships two `LLMProvider` plugins under one contract, and `[llm.roles]` — not `[services]` —
chooses between them per *role*, because a pipeline stage never names a provider or a model, only
a role a technique plugin's own configuration reads:

```toml
[llm.roles]
generate = { provider = "openai", model = "gpt-5.6-luna" }
grade    = { provider = "openai", model = "gpt-5.6-luna" }
rerank   = { provider = "openai", model = "gpt-5.6-luna" }
route    = { provider = "scripted" }

[packs.openai]
api_key = "${env:OPENAI_API_KEY}"
```

`rerank` is in that list because it is the first role a *shipped* plugin asks under: `llm-rerank`
defaults to it. Which role a technique asks under is that technique's own `role:` field, so a
pipeline that wants its reranking done by a cheaper model than its answers changes one word in a
`with:` block and adds one line here — no second provider, no `model:` string in a stage.

That block is the whole operation, and it is deliberately not a `[services]` field named `llm`: a
single plugin-name key would force every role onto one model, or push a `model:` string into every
technique plugin's own `with:` block. A role is an open string an operator invents in this file —
`generate`, `grade`, `route`, or a name a stranger's technique plugin reads — and nothing in the
registry names one, so a role added by installing a new pack costs zero edits here.

**`scripted` is the offline default, and it is not a quality component.** `weft-llm`'s `scripted`
provider answers deterministically, from the conversation alone, with nothing behind it to call —
the same honesty `weft-embed`'s `hash` states about its own vectors. It is what lets a clean
checkout run `poe ci-checks` with no account and no network, and it is the wrong thing to judge a
generated answer against. `weft-openai`'s `openai` calls `gpt-5.6-luna` by default and produces
answers that mean something; it needs the credential above, and every call is a metered API call.

**A role nothing maps fails loudly, the first time something asks it to answer** — there is no
default provider a role silently falls back to. **`weft ask` routes and generates by default**
(task 3.11) — it runs the installed router, then whichever pipeline it selects, so the `route`
and `generate` roles above are exactly what it reaches for. A clean checkout with no `[llm.roles]`
table maps neither, so `weft ask` refuses loudly rather than guessing at a provider — configure
this section, or run `weft ask --retrieve-only` for Phase 0's own contract, unchanged: nearest
passages, no router, no model call. An unmapped role fails loudly by name, the same as it would
for any other pipeline stage.

**A model string may name its provider, and a mismatch is refused rather than guessed.**
`model = "openai/gpt-5.6-luna"` under a role whose `provider` is `openai` is the same thing as
`model = "gpt-5.6-luna"`; under a role whose provider is `scripted` it is a contradiction, and
Weft says so instead of choosing one half. A slash alone means nothing — `meta-llama/Llama-3-8B`
is one model id, and the prefix is only read as a provider when it names a provider some role in
your own file maps.

**Vendor failures arrive as one of fourteen typed classes, never a raw vendor exception.**
`weft-openai` translates every `openai.APIError` it can raise into a
`weft_llm.errors.LLMError` subclass — `LLMRateLimitError`, `LLMAuthenticationError`,
`LLMContextLengthError`, and so on — so the retry wrapper decides what to do on the class, never
on a vendor's own string. See
[`manual/troubleshooting.md`](troubleshooting.md) → *Generation, offline and online* for the full
set and what each one means.

### How hard to try — `[llm.retry]`

Retry is attached **once**, around the provider, before it reaches anything that asks it a
question. No technique implements its own, and no call site can opt out:

```toml
[llm.retry]
attempts = 3
base_delay_ms = 250
max_delay_ms = 8000
```

Every field defaults, so a `weft.toml` with no `[llm.retry]` block still runs. `attempts` counts
the first call, so `1` means "do not retry"; the delay doubles from `base_delay_ms` and stops at
`max_delay_ms`.

**What gets retried is a fact about the failure's class, not about its message.** Exactly the four
transient classes — `LLMRateLimitError`, `LLMTimeoutError`, `LLMConnectionError`,
`LLMServiceUnavailableError` — are re-attempted. A permanent one is raised on the first attempt,
because a wrong credential, a malformed request or a model that does not exist fails identically
the second time and retrying only converts an error into a wait. Two further properties are worth
knowing: **a stream that has already produced a token is never restarted**, since re-running it
would replay text a reader has seen; and **cancelling a run cancels it immediately** — the retry
loop never swallows a cancellation to finish its attempts.

There is no jitter. One `weft ask` is not a fleet of clients hammering one endpoint, and a
deterministic backoff is one a test can assert on.

### Stopping a model stuck in a loop — `[llm.loop_guard]`

A small or local model asked to keep generating can settle into repeating the same span of text
forever — a known failure mode of greedy decoding, not a claim about whether the text is true.
`LLMClient.complete` watches the accumulated answer as it streams and stops early rather than
filling a reader's terminal, raising `LLMGenerationLoopError`
(see [`manual/troubleshooting.md`](troubleshooting.md) → *The LLM client*). A markdown table is
deliberately excluded: its rows are *supposed* to repeat a shape, and the guard recognises one
before either repetition check runs.

```toml
[llm.loop_guard]
min_period = 50
similarity_threshold = 0.85
diversity_threshold = 0.3
```

Every field defaults to an empirically measured value, so a `weft.toml`
with no `[llm.loop_guard]` block still runs with the guard active. Two thresholds decide whether a
candidate span counts as a loop, and **both** must cross: `similarity_threshold` (how alike two
consecutive windows of the answer must be) and `diversity_threshold` (how internally repetitive
the compared span must be) — a long answer that legitimately reuses a phrase between otherwise
different paragraphs has high similarity but stays diverse, which is what keeps it from being
mistaken for a stuck model. `min_period`/`max_period` bound how short or long a repeating span has
to be before it counts; `min_text_length` is a floor below which nothing is checked at all. If the
guard is firing on content that is not actually a loop, raising `similarity_threshold` or lowering
`diversity_threshold` makes it fire on fewer, more extreme cases; a run that must never be
interrupted mid-stream can set `min_text_length` above the longest answer it expects, which turns
the guard off in practice without removing it from the type.

## Pointing a pack at a different endpoint

Everything above assumes the `openai` pack talks to OpenAI. It does not have to. Any server that
speaks the same API — a gateway, a proxy, a model you are running yourself — is reachable by
setting one key:

```toml
[packs.openai]
api_key = "${env:OPENAI_API_KEY}"
base_url = "http://localhost:11434/v1"
```

That is the whole operation, and it applies to every plugin the pack registers: the embedder, the
provider that answers a role, and the vision describer all share one account, so they all move
together — there is no way, with this pack alone, to point the embedder at one server and leave
the provider on another.

**Which is what the second account is for.** `[packs.openai-compatible]` is a second block holding
the same fields, configured independently, registering the same three capabilities under their own
names — `openai-compatible-embeddings`, `openai-compatible` and `openai-compatible-vision`. It is
named for the protocol rather than for where the server is, because it is true either way:

```toml
[packs.openai]
api_key = "${env:OPENAI_API_KEY}"

[packs.openai-compatible]
api_key = "${env:LOCAL_API_KEY}"
base_url = "http://localhost:11434/v1"

[services]
embed = "openai-compatible-embeddings"

[llm.roles]
generate = { provider = "openai", model = "gpt-5.6-luna" }
```

Embeddings go to the local server, answers go to the vendor, and neither borrows the other's
credential. Each block is disclosed separately in `weft plugins doctor` for the same reason: what
leaves through one account and what leaves through the other may go to different places under
different agreements, so they are two disclosures rather than one.

**What this does not do: it does not read `OPENAI_BASE_URL`.** Weft passes `base_url=` explicitly
on every client it builds — the vendor's own URL when you have set nothing — so the SDK never
reaches for that variable, and exporting it has no effect and produces no error. The reasoning is
in `weft_openai.settings.Settings`: an endpoint a project's own configuration did not name is an
endpoint that configuration cannot be trusted about, and a credential going somewhere the file
does not mention is worth one explicit argument to prevent. If you want the endpoint to come from
the environment, name the variable in the file and let the settings loader interpolate it —
`base_url = "${env:MY_GATEWAY_URL}"` — which keeps the value out of version control and the
*decision* in it.

**Name the model your server actually serves.** A server you run answers to the names it has —
`nomic-embed-text` under Ollama, whatever you loaded under LM Studio or vLLM — and not to the
vendor's catalogue, so pointing `base_url` at it is half the job:

```toml
[packs.openai-compatible]
api_key = "${env:LOCAL_API_KEY}"
base_url = "http://localhost:11434/v1"
embedding_model = "nomic-embed-text"
```

`embedding_model` is the account's answer for *"which model, when nobody says otherwise"*, and
**both sides of a corpus read it**: `weft index` embeds the chunks and `weft ask` embeds the
question, and a stored vector is only comparable to a question embedded by the same model. It is
also the only surface the query side has — `weft ask` builds its embedder from `[services] embed`,
never from a pipeline document, so a stage's `with: {model = "..."}` reaches the ingest run and
nothing else. A stage that does name one still wins for that stage, being one run of one document
rather than what the account serves. (Added 2026-09-13 by `R22.1`: before it, a local server had
to answer to `text-embedding-3-small` or the query side could not reach it at all.)

**A wrong `base_url` fails at the first call, not at startup.** Nothing here reaches the network,
so `weft plugins doctor` reports the pack `active` whether or not the address answers; the error
arrives from the first stage that calls out, naming the model and the endpoint. That entry in
`manual/troubleshooting.md` is the other half of this page.

## Tuning the text arm

The pgvector store's lexical search has three decisions in it, and none of them is knowable from
inside the pack. They are `[packs.store]` settings, so running the same store against two
corpora with two different answers is a file edit:

```toml
[packs.store]
dsn = "${env:WEFT_DATABASE_URL}"
text_search_config = "english"
text_query_mode = "any"
text_rank = "cover-density"
```

**`text_search_config`** is the Postgres text search configuration, and the same value analyses the
stored text *and* the question, so the two cannot disagree about what a word is. The default is
`simple`: fold case, split on word boundaries, stem nothing. That is the honest choice for a corpus
in more than one language — an English stemmer applied to Polish produces matches on stems of
nothing anyone wrote — and it is the wrong one for an English-only corpus, where a question about
"retrieval" never reaches a passage that says "retrieved". `english` fixes that; every
configuration your database installs is available, and a name it does not have is refused with the
list.

**Measured, on English text, before you choose.** Over Open RAGBench's development split — 1,548
questions against 1,000 arXiv papers, 189,523 chunks — lexical search alone found the right paper in
its top five for **24.4%** of questions under `simple` and **68.1%** under `english`, on the same
index with nothing re-embedded, and answered faster (median 0.18 s against 0.45 s). Hybrid search
barely moved (98.3% → 98.5%), because the vector arm already finds nearly everything. So an
English-only corpus that uses the text arm on its own should set `english`; a mixed-language one
should keep `simple`. The `simple` records are `eval/experiments/orb-retrieval-baseline/` in the
repository.

**This one is schema, and changing it later is not free.** The index is a generated column, which
is what makes it impossible to leave stale — Postgres recomputes it from the stored text on every
write — and also what stops the setting from applying to a database that already has one. Weft
refuses rather than pretending; see [`troubleshooting.md`](troubleshooting.md) →
`TextSearchConfigMismatchError` for the two ways forward.

**`text_query_mode`** is `any` (default) or `all`. `any` matches a passage containing any of the
question's words, which is what a natural-language question needs: requiring every word of "why is
mRMR preferred to plain relevance ranking?" matches nothing, and a text arm that answers "no
passages" to everything looks like an empty corpus. `all` is what a keyword-style ask wants back.

**`text_rank`** is `cover-density` (default) or `frequency` — how close the matched words fall to
each other, or how often they occur. Neither score is comparable to a vector search's; that is what
fusion is for.

## Doctor

`weft plugins doctor` is the first and usually last thing to run when a pack is not doing what you
expect. **One status per installed pack**, and a pack is not the same thing as a distribution: one
distribution can ship several. Each row leads with the pack name and names the distribution that
shipped it in parentheses — `store (weft-rag 0.1.0): active (6 contributed)`. The pack name is what
a `[packs.<pack>]` settings block keys on; the distribution is what you install, uninstall, pin in
`[packs] allow`, and read a version off.

| Status | Meaning | What to do |
|---|---|---|
| `active` | Imported, `register()` ran, contributing | Nothing — this is the working state. See the next section for the one thing `active` does *not* mean |
| `refused` | Listed out of an active `[packs] allow` pin. Never imported | Add the distribution to `allow` in `weft.toml`, if you meant to permit it |
| `failed` | Imported, but `register()` raised — most often, its settings failed validation | Read the reason doctor prints; it names the pack and the field. Fix the setting or the `weft.toml` entry it comes from |
| `partial` | Registered, but a conditional dependency it wanted was not available, so part of what it offers did not | Install the missing optional dependency, or accept the reduced set — doctor's reason names what was skipped and why |
| `allowed, not installed` | Named in `[packs] allow`, but nothing installed provides it | `uv add` the distribution, or remove it from `allow` if it was named in error |

This is the one row with no pack name in front of it, and deliberately so: `[packs] allow` names a
*distribution*, nothing installed claims it, so there is no entry point and no pack. It prints the
distribution alone rather than inventing a pack name for something that is not there.

`doctor` also prints a trailing block if two installed distributions both declare a pack under the
same name. Nothing is refused — a stranger's entry-point name is not yours to rename — but one
`[packs.<pack>]` block would configure both, so the block names the pack and both claimants.

`doctor` also flags a pack `active, ambient` when it is running but is not a direct dependency of
the project — arriving as something a chosen pack pulled in transitively, rather than something
anyone `uv add`ed on purpose. That flag depends on `weft` being told which distributions a project
actually named as direct dependencies; Phase 0's CLI does not yet supply that, so every pack
reports without the `ambient` flag regardless of how it arrived. Read the `status` column, not the
`ambient` flag, until that lands.

**Every block names the version that is installed**, beside the distribution's own name:
`chunk (weft-chunk) 1.0.0: active (1 contributed)`. That is what `weft` actually found in the environment,
read from the distribution's own installed metadata — not what a lockfile said, and not what the
release set pins. If a distribution is on disk with no recorded metadata, the block says `(version
not recorded)` rather than leaving the space blank, because a diagnostic command that cannot
measure something should say so. `weft plugins list` stays a one-line summary and prints no
version; it is `doctor` that answers *what exactly is installed here*.

Every block also prints a pack's `disclosure` — what it says it touches, in its own words. A pack
that discloses nothing prints `not disclosed`. This is information the pack chose to publish about
itself, never a fact `weft` checked; see *What this does not protect you from*.

**Two more things `doctor` prints, both added at task 5.2e, neither a new status.** A pack flags
`active, deprecated` when it marked one of its own surfaces deprecated at registration — the block
below names the surface, the reason, and **when the surface goes**: `deprecated: '_Chunker:legacy'
— superseded by 'fast' (removed in weft-chunk 2.0.0)`. That last part is not something the pack
author typed. It is one major of the *publishing* distribution, worked out from the version that
distribution actually has installed, so it cannot go stale the way a hand-written "removed in
2.0.0" would. A distribution still on `0.x` gets the honest answer instead of a number — `'weft-cli'
is 0.x (0.1.0), which promises no deprecation period — this surface may be removed in any release` —
because a pre-1.0 line reserves exactly that right, and printing a release there would promise a
window you do not have. Nothing
stops working: the pack still runs exactly as `active` alone would, and the warning underneath it
is a `DeprecationWarning`, not a refusal. Separately, `doctor` prints a trailing `version skew`
block naming every distribution whose *installed* version does not satisfy some other installed
distribution's *declared* dependency range — the case a plain `uv sync` never reaches, because the
resolver already refused an incompatible install before your environment existed. Skew shows up
from an editable install whose checked-out code has moved past its own recorded version, a forced
`pip install`, or a workspace whose lockfile has drifted:

```text
cli (weft-cli) 0.1.0: active (18 contributed)
  disclosure: not disclosed

version skew — installed does not satisfy a declared specifier:
  'weft-cli' requires 'weft-kernel' >=0.1.0,<1.0.0, but 9.9.9 is installed.
```

Nothing is refused for either condition — a skewed or deprecated pack still loads and still runs.
`docs/09-release.md` §2.3 answer 1 is why: a contract version requirement is the distribution's own
dependency specifier, so the resolver is where an incompatible install actually gets refused; by
the time `weft` is running at all, reporting is the honest thing left to do.

## The one thing to know about `active`

**`weft-store: active` does not mean the database is reachable.** A `dsn` is validated for shape —
is it a string a driver could parse — never for whether anything answers at the other end. Point
`weft.toml` at a real host with the wrong port and `doctor` still reports `active`; the failure
shows up the moment a command actually tries to connect:

```text
weft ask: OperationalError: connection failed: connection to server at "127.0.0.1", port 59999
failed: could not receive data from server: Connection refused
This is an error weft did not translate — the message above comes from the library that raised it.
Re-run with WEFT_TRACEBACK=1 for the full traceback.
```

That is not a bug to route around — whether `doctor` should probe a store's connectivity is a
design question `docs/02-extension-model.md` §2 owns, not something settled here. The operational
fact stands regardless: `active` is "registered and configured," not "reachable right now," and
the way you find out otherwise is by running a command that actually uses it, or by setting
`WEFT_TRACEBACK=1` to see the driver's own error in full.

## Exit codes

Every command's exit code is meaningful — `weft` never always-exits-`0` — so a script or a CI job
can act on the difference between a policy problem and a resolution problem, per
[`docs/03-cli.md`](../docs/03-cli.md) → *Output*.

| Code | Name | Meaning |
|---|---|---|
| `0` | `SUCCESS` | The command did what it was asked |
| `1` | `OPERATION_FAILED` | The command ran, but the operation itself failed — an unreachable database, a document that failed to extract. An error weft did not translate reaches this code too, printed as one line rather than a traceback |
| `2` | `BAD_USAGE` | The command line itself was wrong — `argparse` catches this before any command runs |
| `3` | `POLICY_REFUSED` | A **policy** refusal — a pipeline named a plugin from a pack `[packs] allow` refuses |
| `4` | `RESOLUTION_FAILED` | A **resolution** failure — a name no installed pack provides, or one lost to a `failed`, `partial` or `allowed, not installed` pack |

**3 and 4 answer different questions, on purpose.** 3 means *the environment refused this on
policy grounds* — fix `weft.toml`, or accept that it is refused. 4 means *nothing here can produce
what was asked for* — fix the pipeline, or install what is missing. A CI job that treats them the
same cannot tell "this needs a config change" from "this needs a different pipeline," which is the
whole reason the split exists. Concretely, with `weft-store` refused by an active `allow` pin:

```text
$ weft ask "hello" --retrieve-only
'weft-store' is refused by [packs] allow in weft.toml. Add it there to permit it.
$ echo $?
3
```

and with no `dsn` configured at all, so `weft-store` never registered in the first place:

```text
$ weft index corpus
'weft-store' failed to register: 'weft-store' settings failed validation: 1 validation error for
PgVectorSettings
dsn
  Field required [type=missing, input_value={}, input_type=dict]
$ echo $?
4
```

**A connection failure at runtime is exit `1`, not `3` or `4`.** `weft-store` was `active` — it
registered, its settings validated, the shape checked out — so this is neither a policy refusal
nor a name nothing could resolve. It is an operation that ran and failed, which is exactly what
`1` means.

`WEFT_TRACEBACK=1` re-raises the underlying exception instead of the one-line rendering, for
whoever has to actually fix the failure rather than just see that one happened.

## Persisted runs, and `weft trace`

Task **4.4**, `01` → Phase 4 *Exit*, fitness function 8(c). Every `weft index --pipeline` (task
4.0) and every `weft eval run` persists a **run record** — a plain JSON file, never a row in your
store: `weft eval run` mints a fresh `uuid4`, `weft index --pipeline` mints one the same way, and
each writes `runs/<id>.json` under the current directory, the identical project-local footing
`pipelines/` already has. A `RunRecord` carries these facts, and each one earns its place because a
later comparison needs it, not because more is better:

- **`resolved_pipeline`** — what actually ran, not the document name that asked for it. This is
  why task 4.0 exists: before it, `weft index` built its four stages in Python and had nothing
  resolved to persist.
- **`corpus`** — a name plus a content-derived digest over every document actually indexed, so
  "the same corpus" is something two runs can be checked against rather than an operator's own
  claim.
- **`model_versions`** — which provider and model a role resolved to (`"embed":
  "openai:text-embedding-3-small"`), read off the resolved pipeline's own stage configuration,
  never guessed — a stage whose plugin declares no `model` field contributes nothing, and `weft
  eval run` never reads `[services]` for this (*Choosing an embedder* above, Q3): a named
  pipeline's own `use:`/`with:` already decided what ran.
- **`active_distributions`** — every installed distribution `weft plugins doctor` reports
  `active`. A pipeline change compared across two different pack sets is compared against the
  wrong experiment; fitness function 8(c) is exactly this equality, checked.
- **`metrics`** — task 4.9's own addition: every metric this run actually scored, when `weft eval
  run` was given `--questions`; `{}`, honestly, when it was not.
- **`question_seconds`** (Phase 33, task 33.7): how long each question's retrieval took, keyed the
  same way as that question's scores. The run's total in `durations` cannot show whether one question
  was a hundred times slower than the rest; this can. `None` means the record was written before
  33.7. `weft eval run` prints its p50, p95 and p99 (task 33.8), each one a real observation at
  nearest rank. A percentile whose rank is the last sample prints as
  `not aggregated (N samples)`, because it would be the maximum under another name: with 66
  questions, p99 is withheld and p95 is not. `weft eval compare` prints one latency line per run,
  and says `not recorded` for an older record rather than refusing the comparison. Latency depends
  on the machine, so it is reported beside a comparison and never gated.
- **`question_contributors`** (Phase 39, task 39.2): for each question a query rung retrieved for,
  the labels of the ranked lists its passages were fused from — `hybrid:vector`, `hybrid:text`.
  Under `intent-and-anchors` it is how a record says which branch a question took: a question with
  no anchor names no `hybrid:text`, because its lexical arm was never asked. `None` means the run
  retrieved through the hardwired vector search or a generating rung, or predates 39.2.
- **`token_usage`** (task 33.7): what each model role spent, as prompt and completion tokens over the
  calls that reported them, plus a count of calls whose provider reports nothing, such as the
  scripted one. A role that cannot be metered shows as calls not reporting, never as zero tokens.
  `{}` means no model was asked, and `None` means not recorded. `weft eval run` prints each
  role's tokens (task 33.10) as `generate: 9104 in / 681 out`, and a role whose provider reports
  nothing as `not reported (N calls)`.

**A run record is not `weft ask --explain`.** `weft trace` reads a record `weft eval run` wrote
to disk earlier. `--explain` describes the one `ask` in front of you and persists nothing. Its
`stages:` block gives the milliseconds each call through the registration seam took, so
`ask:search` shows the store's time apart from `ask:embed`'s. Those milliseconds are measured on
your machine, so compare them only against runs on the same machine.

**Read one back with `weft eval compare <a> <b>` or `weft trace <run-id>`** — both name a run by
the id `weft eval run` printed (the file's own stem under `runs/`), and both refuse loudly, naming
every id that does exist, for one that is not there:

```text
$ weft trace does-not-exist
'does-not-exist' is not a persisted run — checked 'runs'. Persisted runs: (none).
```

`weft eval compare` additionally refuses outright — before it ever computes a pipeline diff —
when the two runs are not apples to apples: a different corpus, different `model_versions`, or a
different question set. A different `active_distributions` set or distribution versions is printed
beside the comparison as `packaging differs, reported not refused: …` and never refuses it
(carried repair `R22.11`: a version bump alone had been refusing comparisons). This is
`09-release.md` §4's own V3 failure clause ("a shipped technique's improvement... reported against
a baseline from a different corpus, pipeline or model version") applied at the CLI, and it names which fact differs rather than
printing a pipeline diff that would misattribute a metric delta to the pipeline change alone.

**A baseline report is a second kind of file, in a second directory — not the one above.**
`weft eval baseline`, covered next, writes under `baselines/`, wrapping an identical `RunRecord`
inside its own report (`BaselineReport.record`). `runs/` and `baselines/` are two directories with
two purposes, and neither command looks in the other's for you.

### `weft trace`

`weft trace <run-id>` prints exactly what the persisted record holds — the resolved pipeline's
name, the corpus identity and digest, the model versions, the active distribution set and, since
task 4.9, the metrics block — and nothing this command computes or infers on top of it:

```text
$ weft trace 68280b30-d6a5-4920-9d09-0b402d30395e
run 68280b30-d6a5-4920-9d09-0b402d30395e — recorded 2026-09-12T16:40:21.065657+00:00
pipeline: index-text
corpus: 'corpus' (66d313093adf…)
model versions: (none recorded)
active distributions: weft-rag
metrics: (none recorded — 'weft eval run' was not given --questions)
```

**One active distribution is the normal answer, not a stripped-down install.** This transcript
was taken from an install of both published wheels; **G19** folded every first-party pack into
`weft-rag`, so the twenty-one packs a full install activates all report that one distribution
name and the set records it once (`weft_eval.run_record.active_distribution_set`). A list of
thirteen names here, as this page showed until 2026-09-12, described the pre-G19 tree.

**What it does not do — task 4.6, Q2, a narrowing of what `docs/03-cli.md` first promised, not a
widening.** `weft trace` does not replay a run stage by stage, does not say which stage took how
long or which one failed, and does not read an exported OpenTelemetry span — because nothing in
this tree exports one. The kernel depends on `opentelemetry-api` only (`01` → *The kernel
boundary*: everything that **exports** a span is a pack's job), task 4.5 found the registration
seam already emits every span a future exporter would need, and Phase 4 ships no exporter pack to
consume them. Reading spans back would have meant shipping that pack as a second, unbudgeted
artefact, so `weft trace` reads the cheaper, honest thing that already exists: the five static
facts above. If you need per-stage timing today, `weft eval run`'s own `wall clock: <seconds>s`
is the whole run, measured rather than estimated — not a stage, and not a substitute for a span.

## Measuring a baseline, and judging a later run against it

`weft eval baseline` takes the measurement Weft's published numbers come from. It selects a corpus
manifest's tiers, verifies every selected document against its sha256, stages them under
`--workdir`, indexes them through a named pipeline, retrieves every question it can score more than
once, and writes one report. All of it happens in the `weft` process.

```bash
# the corpus first — the fetcher refuses to keep bytes that do not match their pin
python3 scripts/fetch_corpus.py fetch        # standard library only, Python 3.11 or later

weft eval baseline corpus/manifest.toml eval/questions
```

With no flags that is the published measurement: `--tiers fetch`, `--repeats 3`, `--top-k 10`,
`--depths 5,10`, and the shipped `baseline` pipeline. Run from an install of the two wheels, outside
this repository, against an empty Qdrant collection (2026-09-14), it exited `0` and wrote a
report under the same corpus digest, `8854c33f71ea`, that the published
`eval/baselines/8854c33f71ea-2026-08-25.json` carries. That run was not published; the published
reports are the two files under `eval/baselines/`.

**The pipeline is a shipped document, and the store has to hold nothing else.** `baseline` is
`text` → `fixed-size` → `hash` → `qdrant`: single-vector top-k with no fusion, rerank or
enhancement, which is what `09` §4.3 V3 asks a baseline to be. `hash` needs no vendor account, so
anyone can reproduce the number. `--pipeline` names a different document; its extractor decides
which staged documents are read, and a question resting on a document it does not read is not
scored. The store's collection is `weft.toml`'s `[packs.qdrant] collection`. A retrieved passage from
any document this run did not stage refuses the run (`BaselineStoreNotIsolatedError`), because
other documents change every rank while the result still reads as ordinary retrieval.

**Why `--repeats` has no value below 2.** A baseline records, per metric, the **interval its own
repetitions spanned**, and that interval is the only tolerance a later run is judged by. Nobody
picks a number. `weft eval compare` judges two baseline report files:

```text
$ weft eval compare archive/baselines/8854c33f71ea-2026-08-25.json mine.json
'mine.json' reproduces 'archive/baselines/8854c33f71ea-2026-08-25.json': 12 of 12 metric(s) inside the intervals 'archive/baselines/8854c33f71ea-2026-08-25.json' recorded
installation differs at stage 'extract': distribution weft-extract -> weft-rag
installation differs at stage 'chunk': distribution weft-chunk -> weft-rag
installation differs at stage 'chunk': applies_to [] -> [{"constraints": [], "fact": null, "media_type": ["text"]}]
installation differs at stage 'embed': distribution weft-embed -> weft-rag
installation differs at stage 'store': distribution weft-qdrant -> weft-rag
installation differs at stage 'store': contract_version 2.0.0 -> 2.6.0
  document-mrr@10: 0.26875 inside [0.26875, 0.26875]
  …
```

Every metric inside its interval, and the run reproduced the baseline; anything outside, and it
names the metric and both bounds and exits `1` (`BaselineNotReproducedError`). A run over a
different corpus, stage configuration, model version, retrieval depth or question set is refused
with exit `1`, naming every difference, rather than compared. The
*installation differs* lines are not refusals: they describe what was installed, and any effect it
had on retrieval would show up in the intervals.

**Two baselines, and only one of them may be published.** `--tiers fetch` measures over documents
anybody can obtain from a pinned, checksummed source; that report says `"reproducible": true`.
Adding the `operator` tier includes papers held under publisher copyright, which nobody else can
fetch at any price, and every one of them is a PDF, so the pipeline has to name a PDF extractor.
That report says `"reproducible": false`, its file name says `unreproducible`, and the label goes
with the number every time it is quoted.

**What is measured, and what is not.** A retrieval measurement: recall, nDCG and MRR at each
depth, at two granularities. A `quote-…` metric counts a passage containing the ground-truth span;
a `document-…` metric counts one drawn from the right document. Unanswerable questions carry no
retrieval judgement and are **excluded and counted**, with the reason recorded in the file, never
scored as zero.

## The deterministic subset, and pricing a run

Task **4.7**, `docs/09-release.md` §4 V5. 21 metrics ship in `weft-eval` (task 4.2); six of them
are LLM judges and one (`bertscore`) needs a downloaded model checkpoint. None of the seven can
run in `poe ci-checks` on a clean checkout with no credentials and no network — the gate's default
`hash` embedder and `scripted` LLM provider (see *Choosing an embedder* and *Choosing which model
answers* above) resolve every service a metric asks for, but a judge asked to score against
`scripted`'s canned text cannot produce a usable structured judgement, and `bertscore` needs a
package this pack does not carry as a base dependency at all.

**Ask what runs offline; do not guess.**

```bash
$ weft eval metrics
runs in the gate (no credentials, no network): accuracy, embedding-similarity, exact-match,
f1-score, key-terms-precision, mean-average-precision, mrr-at-k, ndcg, overlap-at-threshold,
precision-at-k, recall-at-k, rouge-1, rouge-2, rouge-l, token-overlap, token-recall
does not run in the gate: answer-completeness, answer-correctness, answer-relevance, bertscore,
context-recall, context-relevance, faithfulness
```

This is read off the registry itself — `weft_eval.offline.gate_subset` — never a paragraph here
that can drift from what a checkout actually installs; a stranger's own metric pack is included
on the identical footing, because `GenerationMetric`/`RetrievalMetric` both refuse to register any
implementation that never declares whether it runs in the gate (`weft_eval.contract`'s own module
docstring, Q6). Ask about one metric by name to get the same refusal a real run would give:

```bash
$ weft eval metrics --name faithfulness
'faithfulness' cannot run in the deterministic, gate-safe subset: needs a real judge model behind
'[llm.roles]' — the deterministic 'scripted' provider resolves the service but cannot produce a
usable structured judgement... Configure '[llm.roles]' to map this metric's role (default
'grade') to a real provider such as 'openai' to run it outside the gate.
```

See `manual/troubleshooting.md` → *Asking whether a metric can run here* for the full text and
exit codes.

**Pricing.** A price needs tokens in and out per call, and a per-model rate. `weft_llm.payload.
Completion.usage` carries the first half — populated by `weft-openai`'s real provider from the
vendor's own response, always `None` for the deterministic `scripted` provider, which made no
real call and has nothing to price. `weft_eval.pricing.price_calls` is the computation: fold many
priced calls into one total, against a rate table. The default table ships as plain data in
`weft_eval.pricing.DEFAULT_RATES` — a `Mapping[str, TokenRate]`, never a closed enum a new model
would need a code change to price — and every `price_calls` call takes `rates=` as a parameter, so
an operator with current numbers substitutes their own without editing a package. **Staleness is
never hidden inside a bare total**: `weft_eval.pricing.RATES_AS_OF` is the date the shipped table
was last checked against a real price sheet, and every computed `RunPrice` carries `rates_as_of`
alongside `total_usd`. A call whose model has no entry in the rate table is never silently priced
at `$0` — it is excluded from the total and counted in `unpriced_calls`/`unpriced_models`, the
identical "excluded, counted rather than merely honoured" shape `weft_eval.aggregate` already
gives a metric's own failures.

`weft eval run`'s own output carries the wall-clock half of a priced run, measured rather than
estimated:

```bash
$ weft eval run corpus index
run 3f9c...-1 persisted (corpus -> pipeline 'index'). produced 12, nothing to produce 0, failed 0.
nodes now stored: 12. corpus: 'corpus' (a1b2c3d4e5f6…). wall clock: 1.84s.
```

Its persisted record's `model_versions` names the models the run actually used: `weft_cli.eval_commands`
derives it from the resolved pipeline's own stages — whichever stage's plugin declares a `model`
field in its own `config_model` (`weft_openai.embedder.OpenAIEmbedderConfig.model`, say)
contributes `"<stage>": "<plugin>:<model>"`, generically, never from `[services]` — a named
pipeline's own `use:`/`with:` already decided what ran (see *Choosing an embedder* above, Q3).

## Scoring retrieval, and comparing what two runs produced

Task **4.9**. Before this, a persisted `RunRecord` carried no metric scores at all — `weft eval
compare` could only report that two runs' resolved pipelines *differ*, never what they
*produced*. `weft eval run --questions <file>` closes that.

`--questions` names a question file — a directory of TOML files, or one — in the form
`eval/questions/` is written in. A set that cannot supply every field says so once, in a
`[question_set]` table, with a reason:

```toml
[question_set]
schema = 2
absent = ["kind", "difficulty", "quote", "reference_answer", "notes"]
absent_reason = "written for a retrieval-only check"
axes = []

[[question]]
id = "intro-1"
text = "what is weft?"
language = "en"
relevant_documents = ["weft-intro.md"]
```

`relevant_documents` names a document, not a chunk: a path relative to the corpus, matched on whole
path components wherever the corpus is staged, because a node id is a content digest nobody can
predict before a run. A set that names documents by manifest id, as `eval/questions/` does, is run
with `--manifest corpus/manifest.toml`, which maps each id to its document's path. A JSON list of
`{"query": ..., "relevant_documents": [...]}` still scores — converted into the same form, with a
notice that the format is deprecated and goes at `weft-rag` 3.0.

```bash
$ weft eval run corpus index --questions questions.toml --top-k 5
run 3f9c...-1 persisted (corpus -> pipeline 'index'). produced 12, ... wall clock: 1.9s.
```

For every question, `weft eval run` retrieves through the resolved pipeline's own
`Embedder`/`NodeStore` stages — never `[services]`, Q3 still holds — and scores the deterministic,
gate-safe `RetrievalMetric` subset over the result (`precision-at-k`, `recall-at-k`,
`mean-average-precision`, `mrr-at-k`, `ndcg`; `weft eval metrics` lists the full set live). The result folds
into the persisted record's `metrics` field, keyed by what each metric actually computed
(`precision@5`, not the registered plugin name — the same "the report is keyed by what a metric
computed" rule task 4.3's aggregation already holds elsewhere). `--questions` is optional:
omitted, `metrics` stays `{}`, honestly — the same gap `model_versions` had before task 4.7.

`weft eval compare` prints the scored metrics from both runs side by side, once the usual
apples-to-apples check passes:

```bash
$ weft eval compare 3f9c...-1 3f9c...-2
'3f9c...-1' vs '3f9c...-2' — same corpus and model versions; pipeline is the only fact that may
differ:
not compared: pack settings ([packs.*]) — a run record does not carry them, so two runs differing
only there read as identical
'index' vs 'specific':
  ~ chunk: fixed-size -> fixed-size
metrics:
  precision@5: 0.520 (n=8, ±0.140) vs 0.680 (n=8, ±0.110)  Δ+0.160
  recall@5: 0.610 (n=8, ±0.090) vs 0.610 (n=8, ±0.090)  Δ+0.000
```

A metric one run scored and the other did not prints `not produced (...)` on the side that never
measured it — never silence, and never a fabricated number standing in for "unmeasured." *Persisted
runs, and `weft trace`* above covers reading a single run's own `metrics:` block back, and what
`weft trace` does not do.

## Comparing two query rungs against one index

Carried repair **R10.4**. Everything above compares two *runs*, and until now every run indexed
first — so comparing two **query** rungs over one corpus meant ingesting it twice and the two arms
were scored against two stores rather than one. On a deterministic ingest rung that is merely
wasted minutes. On a rung that calls a model it is not: `L11.46` measured four runs taking a
corpus from **23 nodes to 42**, and what read as a baseline *interval* was extraction drift, not
retrieval noise. The comparison spanned a store that grew between its arms.

`--reuse-index` scores against what is already stored:

```bash
$ weft eval run corpus index-text --yes
run 68280b30-d6a5-4920-9d09-0b402d30395e persisted (corpus -> pipeline 'index-text'). produced 1, nothing to produce 0, failed 0. nodes now stored: 3. corpus: 'corpus' (66d313093adf…). wall clock: 0.08s.

$ weft eval run corpus index-text --reuse-index --yes
run 4e03560c-fab9-4a14-8f96-4d73acb307ae persisted (corpus -> pipeline 'index-text'). produced 0, nothing to produce 0, failed 0. nodes now stored: unknown. corpus: 'corpus' (66d313093adf…). wall clock: 0.00s.
```

Three things in that second line are the repair. `produced 0` and `wall clock: 0.00s` say the
ingest half did not run — not that it ran quickly. `nodes now stored: unknown` is honesty rather
than a gap: this run stored nothing, so it has no count of its own to report, and printing the
store's current size would be reporting somebody else's number. And the corpus digest is
**identical** — `66d313093adf…` both times — which is the part that makes the two records
*comparable* rather than merely both present.

That digest is identical by construction, not by luck. Both paths discover the corpus through one
function — `weft_cli.ingest.corpus_documents` — and digest one fact about each document it
returns. Reading the ids back out of the store instead would make the record depend on whatever a
previous run happened to write, which is the moving corpus one layer down.

### What the corpus digest is over, and why a record says so

**Each document's own bytes — a sha256 per document, sorted, since 2026-09-12.** So the digest
moves when any document's contents change, and stands still when a document is renamed or the
whole corpus is staged in a different directory. That is what makes it a fact about *the corpus*
rather than about the machine, and it is what a published baseline needs in order to be
reproducible by anyone who has the same files.

**It was over the documents' resolved filesystem paths before that date, which is the opposite
of both halves**, and every run record written before it carries such a digest. Those records are
not comparable by digest to anything written since, so a record now names what its own digest is
over and `weft eval compare` says when the two sides disagree rather than reporting a corpus
difference an operator would go looking for:

```bash
$ weft eval compare 214c9582-60b6-49e6-b668-e1057ae056cc 00000000-0000-0000-0000-00000000old0 ; echo "exit=$?"
'214c9582-60b6-49e6-b668-e1057ae056cc' and '00000000-0000-0000-0000-00000000old0' are not comparable as a change of pipeline alone: corpus digests are not over the same thing (document-bytes vs not recorded) — a record that names no basis was written before ledger task 16.0, when the digest was over each document's resolved path rather than its bytes, so these two digests cannot be compared even over a corpus that never changed. A comparison is only meaningful when the corpus, model versions and question set agree and only the pipeline differs — otherwise a metric delta cannot be attributed to the pipeline change ('09-release.md' §4, V3's own failure clause). Which distributions were active, and at which versions, is reported beside a comparison and never refused on.
exit=1
```

**An older record still loads and still traces.** `weft trace` on one prints everything it holds;
the only field it cannot answer for is what its digest was over, and *not recorded* is the honest
answer to that rather than a retro-label. **What to do** when you hit this: re-take the run you
want to compare against, on this version. There is no migration, because there is nothing in an
old record to migrate from — the bytes it digested were never written down.

A directory the pipeline cannot read refuses, rather than persisting a record with an empty
corpus:

```bash
$ weft eval run empty index-text --reuse-index --yes ; echo "exit=$?"
'empty' holds nothing pipeline 'index-text' can read, so there is no corpus identity for a run record to carry and nothing for a query rung to retrieve. --reuse-index scores against a corpus that is already stored; point --path at the directory that was indexed.
exit=1
```

**`--reuse-index` does not check that the corpus was ever indexed** — nothing reads the store to
confirm it. Point it at a directory whose documents were never ingested and it will score a query
rung against an empty retrieval, honestly and uselessly. The corpus digest is what catches this
after the fact: a run whose numbers are all zero, against a digest no earlier run carries, was
scored against nothing.

## Text search in a language Postgres does not ship

`[packs.store] text_search_config` names the Postgres configuration both the stored column and
the query use, and it defaults to `simple`. The setting's own docstring says `simple` is the
default and not the right answer for an English corpus — `english` is, because with `simple` a
question about "retrieval" never reaches a passage that says "retrieved".

**For Polish there is nothing else to name, and that is a fact about Postgres rather than about
Weft.** Measured against the shipped `pgvector/pgvector:pg16` image on 2026-09-12: it installs 28
text search configurations and `polish` is not one of them. Postgres ships stemmers for the
languages Snowball covers, and Polish is not among them. So on a stock install `simple` is not a
compromise between two options — it is the only one.

See what your own database has:

```bash
$ docker exec weft-postgres-1 psql -U weft -d weft -tAc "select cfgname from pg_ts_config order by 1;"
arabic armenian basque catalan danish dutch english finnish french german greek hindi hungarian
indonesian irish italian lithuanian nepali norwegian portuguese romanian russian serbian simple
spanish swedish tamil turkish yiddish
```

**What to do.** If the list holds the language you need, name it and re-index — the column is
generated, so the configuration is a property of the database and existing rows are rebuilt when
the schema is recreated. If it does not, the honest options are to install a dictionary into
Postgres and build a configuration from it — an `ispell`/Hunspell Polish dictionary plus
`CREATE TEXT SEARCH CONFIGURATION` — and only then name it here, or to leave `simple` and know
what you have: case-folded, whitespace-split matching with no stemming, which finds `Krakowie`
only when the question says `Krakowie`. Naming a configuration the database has not got is
refused before the schema is touched, naming what you asked for and what is installed
(`UnknownTextSearchConfigError`).

**Vector retrieval is unaffected.** This setting governs the *text* arm only; embeddings carry
whatever the embedder understands, and a hybrid rung's vector half works in any language its
model does.

## What this does not protect you from

**A pack runs with your full privileges. Installing one is trusting it.** `[packs] allow` decides
whether a pack's `register()` is ever called; it decides nothing about what that code does once it
runs. There is no process boundary, no sandbox, and no per-pack limit on what a pack can open, call
out to, or read — CPython does not have one to offer, and nothing here simulates one. A pack you
deliberately install and permit can do anything your own account can do.

**Disclosure is a pack's own claim, unverified.** The `network` / `filesystem` / `subprocess`
lines doctor prints under each pack came from that pack's own `DISCLOSURE`, read and printed
as-is. `weft` never checks it against what the pack actually does. `not disclosed` is honest —
nobody claimed anything — not a statement that the pack is safe.

**`[packs] allow` stops an *unlisted* pack from running; it says nothing about a listed one.**
Refusal happens before import, which is real — a refused pack's code genuinely never executes. But
a pack you added to `allow` runs exactly as fully as if there were no allow-list at all.

**Command permission classes (`read`/`write`/`overwrite`/`destroy`/`network`) protect you from the
tool, not from a pack — and Phase 0 declares them without wiring the protection yet.** Every
built-in command names its class today, with no default, so the vocabulary is fixed and every
command is honestly categorised. The prompt they will govern — core stopping and asking before a
destructive-looking operation — arrives with the CLI's destructive-operation guard in Phase 3; Phase
0 ships no `overwrite` or `destroy` command; nothing here interrupts you yet. Once it does, it will
still be the same limit: a dishonest pack that declares `read` and deletes your collection anyway
will not be stopped by anything described on this page.

None of this is a gap waiting to be closed by more careful configuration — it is the actual shape
of the trust model, stated so nobody assumes a protection that was never built. See
[`docs/02-extension-model.md`](../docs/02-extension-model.md) §2, *The trust model*, for the
argument behind each of these, including why a stronger model was considered and rejected.

## Where to go next

- **Never run `weft` before?** [`manual/quickstart.md`](quickstart.md) is the five-minute path from
  nothing to a real, retrieved answer.
- **Writing a pack of your own?** [`manual/pack-author-guide.md`](pack-author-guide.md) walks a
  real one, installed from outside this project's own workspace.
