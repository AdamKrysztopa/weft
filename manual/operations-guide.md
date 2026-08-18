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
# **Bringing the container up is not enough to make the store usable.** `weft-store`
# requires a `dsn` in its pack settings, and there are two ways to supply it. With no
# `weft.toml` at all, an exported `WEFT_DATABASE_URL` is offered as `dsn` and the store
# comes up `active` — the no-file path `manual/quickstart.md` walks. A `weft.toml`
# carrying `[packs.weft-store] dsn` — see `weft.toml.example` — wins over the
# environment, key by key. `weft plugins doctor` reports `weft-store: failed`, naming
# the missing field, only when NEITHER supplies a `dsn` — the loud failure working: the
# pack refuses rather than defaulting to some database it guessed.
#
# Port 5433, not 5432: `.env.example` explains why — a bare default port on a
# developer's machine belongs to whichever Postgres happened to claim it
# first, and this project's store is namespaced everywhere else too.
services:
  postgres:
    image: pgvector/pgvector:pg16
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

volumes:
  weft-postgres-data:
  weft-qdrant-data:
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

`weft-store` takes its connection string from its own pack settings, `[packs.weft-store] dsn`, and
there are two ways to supply it. **With no `weft.toml` at all** — the path `manual/quickstart.md`
walks — an exported `WEFT_DATABASE_URL` is offered as `dsn` on its own, and that is enough to bring
`weft-store` up. A project that wants an explicit, committed connection string instead copies
`weft.toml.example`:

```toml
[packs.weft-store]
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

**A `weft.toml` value wins over the environment, key by key.** `weft-store`'s settings are built by
merging what `weft.toml` says over what `WEFT_DATABASE_URL` offers, and the file's own keys are
never overwritten by the environment — only keys the file leaves unsaid are filled from it. This
is deliberate: a stale `WEFT_DATABASE_URL` left over in a shell must never quietly redirect a
project whose `weft.toml` already names a different database. A store pointed at the wrong
database does not crash — it answers plausibly, against the wrong data, which is the failure this
project exists to remove. Concretely: with `WEFT_DATABASE_URL` pointed at a real, reachable
database and `weft.toml` naming a different, unreachable one, `weft plugins doctor` reports
`weft-store: active` — the file's value is the one in play — and `weft ask` fails to connect,
exactly as it should for the database `weft.toml` actually named.

`weft.toml` is also where a project pins which packs may run at all:

```toml
[packs]
allow = ["weft-extract", "weft-chunk", "weft-embed", "weft-store"]
```

Absent, the posture is open — every installed pack runs. Present, it is exhaustive: anything not
listed is refused, and refusal happens *before* the pack is ever imported, not after. This is a
statement of policy, not a sandbox — see *What this does not protect you from*, below.

**A pin has to permit the pack behind every plugin name the rest of the file selects.** Setting
`[services] embed = "openai"` and leaving `weft-openai` off this list is a contradiction, and
`weft index` says so before it runs anything:

```text
[services] embed names 'openai', and no registered Embedder has that name. These distributions
are refused by [packs] allow in weft.toml and were never imported, so what they would have
registered is unknown: weft-openai. Add the one that provides 'openai' to [packs] allow.
```

Exit `3`, not `4`: the name is a policy problem, and the key that fixes it is named. A refused
pack is never imported, so nothing can prove it is the one that would have claimed the name —
which is why the message says the packs are refused rather than claiming one of them provides it.

## Choosing an embedder

Weft ships two, registered under one contract, and `[services]` chooses between them:

```toml
[services]
embed = "openai"

[packs.weft-openai]
api_key = "${env:OPENAI_API_KEY}"
```

That block is the whole operation. No package is edited, nothing is reinstalled, and an embedder
some third party's pack registers is selectable by name the moment it is installed.

**`hash` is the default, and it is not a quality component.** `weft-embed`'s `hash` embedder turns
content into a deterministic vector and understands nothing about it: two documents on unrelated
topics are as "similar" to it as two ways of saying the same thing. It is what lets a clean checkout
index, search and pass its whole test suite with no account and no model download, and it is the
wrong thing to judge a retrieval result against. `weft-openai`'s `openai` embedder calls
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

**Where the credential comes from.** `weft-openai` reads its key from `[packs.weft-openai] api_key`
and from nowhere else. It deliberately does *not* fall back to the `OPENAI_API_KEY` the vendor's own
SDK would read on its own — an exported variable that silently made a project work on one machine is
the same failure mode `weft.toml` beating `WEFT_DATABASE_URL` avoids for the database. `${env:...}`
is how the secret still stays out of the file. With no key configured at all the pack still
registers and `weft plugins doctor` still reports it `active`, deliberately: nothing is missing
until something asks it to embed, and then the failure names this exact line.

**Which model, and how wide — not yet selectable from a file.** `[services] embed` chooses the
*plugin*; the model name, the `dimensions` a `-3` model will shorten a vector to, and the batch
size are the embedder stage's own `with:` configuration, and no route from a pipeline document to
`weft index`'s stages exists — `weft index` still names its four stages in Python rather than
resolving a document (`weft_cli/services.py`'s own docstring). Ledger tasks 2.4 and 2.8, both now
closed, built that document-to-`StageSpec` bridge (`weft_cli.compile`) and wired it into a new
query-path command, `weft route`; neither one touched `weft index`. No task in this ledger
currently owns closing that gap for the ingest path. Until one does, `weft index` and `weft ask`
run `weft-openai` with its defaults — `text-embedding-3-small`, the model's native 1536
components, 128 texts per request — and `weft-embed`'s `hash` with its own, the same way. This is
stated rather than left to be discovered: the knobs are real, they are on `OpenAIEmbedderConfig`,
and a library caller constructing the plugin directly can already set them. It is the
configuration file that cannot reach them yet.

## Choosing a store

Weft ships two backends, registered under one contract by two distributions, and `[services]`
chooses between them exactly as it chooses an embedder:

```toml
[services]
store = "qdrant"

[packs.weft-qdrant]
url = "http://localhost:6333"
collection = "weft_nodes"
vector_size = 64
```

The `[services] store` line is what *selects* the backend; the `[packs.weft-qdrant]` block
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

**Capabilities differ between backends, and a run that needs a missing one is refused before it
starts.** `pgvector` provides vector search, lexical text search and metadata filtering; `qdrant`
provides vector search and metadata filtering, and deliberately not text search — its text matching
is a filter predicate rather than a scored ranking, and a store that returned an invented score
would be worse than one that says no. A pipeline whose retriever needs `TextSearch` fails with
`StoreCapabilityMissingError` at run assembly, naming the capability, what your store does
advertise, and which registered stores provide the rest. `manual/contract-reference.md` lists which
distribution satisfies which capability, derived from the code rather than typed by hand.

## Choosing which model answers

Weft ships two `LLMProvider` plugins under one contract, and `[llm.roles]` — not `[services]` —
chooses between them per *role*, because a pipeline stage never names a provider or a model, only
a role a technique plugin's own configuration reads:

```toml
[llm.roles]
generate = { provider = "openai", model = "gpt-4o-mini" }
grade    = { provider = "openai", model = "gpt-4o-mini" }
rerank   = { provider = "openai", model = "gpt-4o-mini" }
route    = { provider = "scripted" }

[packs.weft-openai]
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
generated answer against. `weft-openai`'s `openai` calls `gpt-4o-mini` by default and produces
answers that mean something; it needs the credential above, and every call is a metered API call.

**A role nothing maps fails loudly, the first time something asks it to answer** — there is no
default provider a role silently falls back to. `weft ask` itself still only retrieves — Phase 0's
own documented contract, unchanged — but `weft route <question>` (task 2.8) does resolve a role:
it runs the installed router, then whichever pipeline it selects, so the `route` and `generate`
roles above are exactly what that command reaches for. An unmapped role there fails loudly by
name, the same as it would for any other pipeline stage.

**A model string may name its provider, and a mismatch is refused rather than guessed.**
`model = "openai/gpt-4o-mini"` under a role whose `provider` is `openai` is the same thing as
`model = "gpt-4o-mini"`; under a role whose provider is `scripted` it is a contradiction, and
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

## Tuning the text arm

The pgvector store's lexical search has three decisions in it, and none of them is knowable from
inside the pack. They are `[packs.weft-store]` settings, so running the same store against two
corpora with two different answers is a file edit:

```toml
[packs.weft-store]
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
expect. One status per installed distribution:

| Status | Meaning | What to do |
|---|---|---|
| `active` | Imported, `register()` ran, contributing | Nothing — this is the working state. See the next section for the one thing `active` does *not* mean |
| `refused` | Listed out of an active `[packs] allow` pin. Never imported | Add the distribution to `allow` in `weft.toml`, if you meant to permit it |
| `failed` | Imported, but `register()` raised — most often, its settings failed validation | Read the reason doctor prints; it names the pack and the field. Fix the setting or the `weft.toml` entry it comes from |
| `partial` | Registered, but a conditional dependency it wanted was not available, so part of what it offers did not | Install the missing optional dependency, or accept the reduced set — doctor's reason names what was skipped and why |
| `allowed, not installed` | Named in `[packs] allow`, but nothing installed provides it | `uv add` the distribution, or remove it from `allow` if it was named in error |

`doctor` also flags a pack `active, ambient` when it is running but is not a direct dependency of
the project — arriving as something a chosen pack pulled in transitively, rather than something
anyone `uv add`ed on purpose. That flag depends on `weft` being told which distributions a project
actually named as direct dependencies; Phase 0's CLI does not yet supply that, so every pack
reports without the `ambient` flag regardless of how it arrived. Read the `status` column, not the
`ambient` flag, until that lands.

Every block also prints a pack's `disclosure` — what it says it touches, in its own words. A pack
that discloses nothing prints `not disclosed`. This is information the pack chose to publish about
itself, never a fact `weft` checked; see *What this does not protect you from*.

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
$ weft ask "hello"
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

## Measuring a baseline, and judging a later run against it

Weft's numbers are measured by a hand-run harness under `eval/`, and the runs it writes are
committed under `eval/baselines/`. Nothing about this is a `weft` command: the harness drives
`weft` as a subprocess, exactly as you would.

```bash
# the corpus first — the harness refuses to measure a set it cannot verify byte for byte
uv run python scripts/fetch_corpus.py fetch

OPENAI_API_KEY=… uv run python eval/run_baseline.py --tiers fetch --repeats 3
```

It stages the corpus, writes the `weft.toml` it measures through, indexes, asks every question
the tiers allow, repeats the whole pass, and writes one JSON file.

**Why `--repeats` has no default below 2.** A baseline records, per metric, the **interval its own
repetitions spanned**, and that interval is the only tolerance a later run is judged by. Nobody
picks a number:

```bash
uv run python eval/check_baseline.py eval/baselines/<baseline>.json <later-run>.json
```

Every metric inside its interval, and the run reproduced the baseline; anything outside, and the
command names the metric and both bounds and exits `1`. A run over a different corpus, pipeline or
model is refused outright with exit `2` rather than compared — the comparison would produce an
ordinary-looking number that means nothing.

**Two baselines, and only one of them may be published.** `--tiers fetch` measures over the
documents anybody can obtain from a pinned, checksummed source; that run is marked
`"reproducible": true` and is the number to report. `--tiers fetch,operator` includes papers held
under publisher copyright, which nobody else can fetch at any price — that run is written with
`"reproducible": false`, its file name says `unreproducible`, and the label belongs with the
number every time it is quoted.

**What is measured, and what is not.** `weft ask` retrieves; it does not yet generate. So the
baseline is a retrieval measurement — recall, nDCG and MRR at two depths, at two granularities: a
`quote-…` metric counts a passage that contains the ground-truth span, a `document-…` metric counts
one drawn from the right paper. The unanswerable questions carry no retrieval judgement at all;
they are **excluded and counted**, with the reason recorded in the file, never scored as zero.

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
