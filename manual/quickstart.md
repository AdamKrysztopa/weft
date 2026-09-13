# Weft in five minutes

You have a directory of your own text files and five minutes. This is the one path from nothing
to a working pipeline over them — no concepts, no options, nothing to configure beyond where
your database is.

**It is a smoke test of the pipeline, not a demonstration of search.** The default embedder,
`hash`, builds each vector from a SHA-256 digest of the chunk's text: deterministic, free, no
account, and carrying no meaning, so the order it ranks passages in is arbitrary. That is the
trade this page makes to run offline in five minutes. `manual/operations-guide.md` →
*Choosing an embedder* switches it for a real one in a single `weft.toml` line, and that is when
the results start meaning something.

**What you need:** Python 3.12+, [`uv`](https://docs.astral.sh/uv/), and Docker (for the one
container Weft's store needs — Postgres with the `pgvector` extension).

## 1. Install

```bash id=install
uv add weft-rag
```

`weft-rag` is the default install: twenty-one packs and the CLI in one wheel — the extractor, the
chunker, the embedder and the pgvector store among them — so this is the only install command;
nothing else to add. **The distribution is `weft-rag` and the command is `weft`**: `weft` on PyPI
is an unrelated project, so what you install and what you run are spelled differently.

Anything needing a library you may not want is an **extra** of that same wheel, never a separate
install: `weft-rag[openai]` (a credential and the OpenAI SDK), `[pdf]` (two PDF libraries),
`[qdrant]` (a second store backend), `[otel]` (the OpenTelemetry SDK), `[docling]`, or `[all]`.
None is needed to index a directory and ask a question about it. There are exactly two things this
project publishes — `weft-kernel` and `weft-rag` — and a new capability never adds a third.

*(This section described four separately published add-on distributions until 2026-09-12, and
carried a note saying nothing was on an index yet. **G19** folded the add-ons into extras on
2026-09-09 and the first release went to PyPI on 2026-09-11; this page was not edited with either.
Neither could have been caught by the check that executes this page, because the install block is
the one block it does not run and nothing read the prose beside it — `R17.15`,
`docs/internal/lessons.md` `L17.4`.)*

## 2. Point it at a database

Bring up Postgres with `pgvector` — this project ships a `compose.yaml` at the repository root for
exactly that: run `docker compose up -d` from there — and tell Weft where it is:

> [`manual/operations-guide.md`](operations-guide.md) covers bringing the container up, wiring
> `weft.toml`, `doctor`'s statuses and the exit codes in full; this page stays to the one path.

```bash id=env
export WEFT_DATABASE_URL="postgresql://weft:weft@localhost:5433/weft"
```

That variable alone is enough — no `weft.toml` needed for this.

**Leave it unset** and nothing crashes with a stack trace: `weft plugins doctor` reports
the `store` pack as `failed`, naming the missing field, rather than a store guessing at a database.

**Set it to something unreachable** — a typo'd port is the usual way — and `doctor` still reports
`active`, because a connection string is checked for shape, not for whether anything answers at the
other end. You find out when a command actually connects, and what you get is one line naming the
error, not a stack trace:

```
weft ask: OperationalError: connection failed: ... port 59999 ... Connection refused
```

Once you want to pin which packs may run, or to write the connection string down rather than export
it, `weft.toml` does both — see `weft.toml.example`. **A setting in that file wins over the
environment**, so a stale `WEFT_DATABASE_URL` in your shell cannot quietly send a project at the
wrong database.

## 3. Point it at your files

Weft indexes a directory of `.txt`/`.md` files. Use your own — or make two to try it on:

```bash id=files
mkdir -p corpus
cat > corpus/weft.md <<'EOF'
Weft is a microkernel RAG engine. A small kernel knows nothing about PDFs,
chunking, embeddings or graphs. Every capability is a plugin discovered
through Python entry points.
EOF
cat > corpus/loom.md <<'EOF'
A loom holds the warp fixed while the weft runs through it, over and under,
thread by thread, until the cloth exists.
EOF
```

## 4. Index, then ask

```bash id=index
weft index corpus
```

Weft extracts each file, splits it into chunks, embeds every chunk and stores it in pgvector, then
reports what happened:

```text
2 documents: 2 indexed, 0 unchanged. nodes now stored: 2.
```

Run it again and the second number moves rather than the line staying the same: Weft compares each
file's bytes and the pipeline that read them against what it recorded last time, and does the work
only for what moved.

```text
2 documents: 0 indexed, 2 unchanged. nodes now stored: 2.
```

```bash id=ask
weft ask "what does the weft do" --retrieve-only
```

```text
1. A loom holds the warp fixed while the weft runs through it, over and under,
thread by thread, until the cloth exists.

2. Weft is a microkernel RAG engine. A small kernel knows nothing about PDFs,
chunking, embeddings or graphs. Every capability is a plugin discovered
through Python entry points.
```

**`weft ask` routes to a generated, cited answer by default** — a `QueryScorer` and a
`RoutingPolicy`, both discovered from the registry, pick a pipeline and run it through to prose.
That needs a real model, named in `weft.toml`'s `[llm.roles]` table (`manual/operations-guide.md`
covers wiring one), which this five-minute walkthrough deliberately has not asked you to set up
yet — with nothing configured, routing refuses loudly rather than guessing at a provider.
`--retrieve-only` is what you see above instead: Phase 0's own contract, still exactly this —
nearest passage first by vector distance against your indexed content, no LLM call, and no
citation to compose because there is no generated sentence to attach one to. **Under the default
`hash` embedder that distance is over digests, so the two results above are in the order a hash
happened to produce** — the loom passage is not first because it is a better match, and running
this against your own files will look equally plausible and mean equally little. Configure `[llm.roles]`
and drop `--retrieve-only` to get the routed, cited answer this same command produces by default.

## 5. Make the ranking mean something — first, with no account at all

Everything above is the smoke test. The corpus is indexed and the machinery ran; the *order* is a
hash's. The cheapest way to get an order that means something needs no account, no model and no
download — ask the store for the literal words instead of for a direction in space:

```bash id=lexical
weft ask "microkernel" --pipeline lexical-retrieve --retrieve-only
```

```text
1. Weft is a microkernel RAG engine. A small kernel knows nothing about PDFs,
chunking, embeddings or graphs. Every capability is a plugin discovered
through Python entry points.
```

That is the store's **text arm** — a real lexical ranking, `ts_rank_cd` in pgvector by default —
reached through `lexical-retrieve`, a shipped pipeline that ends at retrieval rather than at a
generated answer, which is why `--retrieve-only` can run it with nothing configured. It is the
honest answer to *"can this thing find anything"* on a machine with no model: a question that turns
on an exact token — a name, an identifier, an error code — is answered correctly, right now, and
the same question through the default `--retrieve-only` above is answered by a hash.

What it cannot do is find a passage that says the same thing in different words. That is what an
embedder is for, and the next section is the cheapest honest one.

## 6. Then, with a real embedder — a server you run

**There is no account in this section and nothing is downloaded by Weft.** Point it at an
OpenAI-compatible embeddings server you are already running — Ollama, LM Studio, vLLM, a gateway —
and the vectors start carrying meaning.

The client that speaks that protocol is an **extra**, because it pulls in a library you may not
want; the plugin's code is already in the wheel you installed:

```bash id=local-install
uv add 'weft-rag[openai]'
```

Without it `weft index` refuses by name — *"`[services] embed` names
'openai-compatible-embeddings', and no registered Embedder has that name"* — and lists what is
registered, which is `hash` alone. That refusal is worth meeting once: it is what every missing
extra looks like.

Then two keys say where the server is and which model it serves:

```bash id=local-config
export WEFT_LIVE_EMBEDDINGS_URL="${WEFT_LIVE_EMBEDDINGS_URL:-http://localhost:11434/v1}"
export WEFT_LIVE_EMBEDDINGS_MODEL="${WEFT_LIVE_EMBEDDINGS_MODEL:-nomic-embed-text}"
cat > weft.toml <<EOF
[services]
embed = "openai-compatible-embeddings"

[packs.openai-compatible]
base_url = "$WEFT_LIVE_EMBEDDINGS_URL"
api_key = "a-local-server-ignores-this"
embedding_model = "$WEFT_LIVE_EMBEDDINGS_MODEL"
EOF
```

The model name matters as much as the address: a server you run answers to the names it has, and
`embedding_model` is read by **both** sides — `weft index` embeds the chunks with it and `weft ask`
embeds the question with it. They have to be the same model, or the store is comparing two
unrelated spaces.

**Changing the embedder means indexing again, into an empty store.** A vector written by one model
means nothing to another, so this is not an upgrade applied in place:

```bash id=local-index
weft delete --all --yes
weft index corpus
```

```bash id=local-ask
weft ask "how does a loom work" --retrieve-only
```

```text
1. A loom holds the warp fixed while the weft runs through it, over and under,
thread by thread, until the cloth exists.
```

Now the first result is first because it is *about* the question — the words "how", "does" and
"work" appear nowhere in it. That is the difference the whole pipeline exists to make, and neither
the hash embedder nor the text arm could have produced it.

**No stderr line this time.** `weft index` warned you about the default embedder while you had not
chosen one; you have now, so it says nothing.

## Something not working?

```bash id=doctor
weft plugins doctor
```

One block per discovered pack — status, why, and what it disclosed. If a name you expected is not
`active`, this is the first and usually last thing to run. [`manual/operations-guide.md`](
operations-guide.md) covers what every status means and what to do about it, in full.

## Where to go next

- **Next on the route: configure it.** [`manual/user-manual.md`](user-manual.md) is where the five
  minutes above stop being a smoke test — `[services]` to swap the `hash` embedder for one that
  means something, `[llm.roles]` to map the model `weft ask` refused to guess at, and `--origin` to
  see which file a setting actually came from.
- **Writing a pack of your own?** The [pack author guide](pack-author-guide.md) walks the exact
  plugin this project keeps installed from outside its own workspace, as proof rather than a demo.
- **Running Weft day to day** — bringing the container up, `weft.toml`, `doctor`'s statuses, exit
  codes, and honestly what the trust model does and does not protect you from — is
  [`manual/operations-guide.md`](operations-guide.md).
