# Weft in five minutes

You have a directory of your own text files and five minutes. This is the one path from nothing
to a real, retrieved answer against them — no concepts, no options, nothing to configure beyond
where your database is.

**What you need:** Python 3.12+, [`uv`](https://docs.astral.sh/uv/), and Docker (for the one
container Weft's store needs — Postgres with the `pgvector` extension).

## 1. Install

```bash id=install
uv add weft-cli
```

`weft-cli` pulls in the kernel and every first-party pack a working install needs — the extractor,
the chunker, the embedder and the pgvector store — so this is the only install command; nothing
else to add.

> `weft-cli` is not on an index yet — Phase 0 has not published a release. Everything after this
> line runs today against a checkout with `weft-cli` already installed; once `09-release.md`'s
> policy ships a version, this line starts working exactly as written and nothing else in this
> page changes.

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
`weft-store: failed`, naming the missing field, rather than a store guessing at a database.

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
produced 1, nothing to produce 0, failed 0. nodes now stored: 2.
```

```bash id=ask
weft ask "what does the weft do"
```

```text
1. A loom holds the warp fixed while the weft runs through it, over and under,
thread by thread, until the cloth exists.

2. Weft is a microkernel RAG engine. A small kernel knows nothing about PDFs,
chunking, embeddings or graphs. Every capability is a plugin discovered
through Python entry points.
```

**`weft ask` retrieves. It does not generate an answer yet** — that is Phase 2's `Generator` and the
LLM pack it ships with, and the command's own `--help` says so. What you see above is real,
ranked retrieval: closest passage first, by vector distance against your indexed content, no LLM
call and no citation to compose because there is no generated sentence to attach one to. Once
generation lands, this same command starts returning prose with citations instead of a passage
list — one line of this page changes, not the shape of it.

## Something not working?

```bash id=doctor
weft plugins doctor
```

One block per discovered pack — status, why, and what it disclosed. If a name you expected is not
`active`, this is the first and usually last thing to run. [`manual/operations-guide.md`](
operations-guide.md) covers what every status means and what to do about it, in full.

## Where to go next

- **Writing a pack of your own?** The [pack author guide](pack-author-guide.md) walks the exact
  plugin this project keeps installed from outside its own workspace, as proof rather than a demo.
- **Running Weft day to day** — bringing the container up, `weft.toml`, `doctor`'s statuses, exit
  codes, and honestly what the trust model does and does not protect you from — is
  [`manual/operations-guide.md`](operations-guide.md).
