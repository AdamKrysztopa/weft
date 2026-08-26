# Weft

A RAG engine built as a microkernel. The kernel knows nothing about PDFs, chunking, embeddings or
graphs: every capability is a plugin discovered through Python entry points, pipelines are data
derivable from other pipelines, and built-in packs are held to the same public contract as anything
a third party writes.

The warp is the fixed frame on a loom; the weft is every thread through it.

> **Status: Phase 0, not yet built.** Six of ten architecture decisions are settled and the plan is
> complete. What exists here is the repository skeleton and the fitness functions, wired before there
> was anything to check — deliberately, because the project this one replaces shipped an
> architecture checker that was never in its CI task.

## Try it

Weft indexes a directory of documents and answers questions about them. Four commands, and the
whole thing runs offline — the default embedder is deterministic and needs no account.

```bash id=install
uv add weft-rag
```

`weft-rag` is the release set: one exactly-tested combination of the kernel, the CLI and every
first-party pack a working install needs — the extractor, the chunker, the embedder and the
pgvector store. There is nothing else to add. **The distribution is `weft-rag` and the command is
`weft`**: the name `weft` on PyPI belongs to an unrelated project, and the console script comes
from `weft-cli`, which this set pins.

> Not on an index yet. Until the first release, install from a checkout with
> `uv pip install -e packages/weft-cli`; everything below is unchanged.

You need Postgres with pgvector. `compose.yaml` in this repository brings one up with
`docker compose up -d`, or point Weft at your own:

```bash id=env
export WEFT_DATABASE_URL="postgresql://weft:weft@localhost:5433/weft"
```

That variable is the whole configuration. No `weft.toml` is needed for this, and leaving it unset
does not crash — `weft plugins doctor` reports `weft-store` as `failed` and names the missing
field.

Give it something to read:

```bash id=files
mkdir -p corpus
cat > corpus/weft.md <<'EOF'
Weft is a microkernel RAG engine. A small kernel knows nothing about PDFs,
chunking, embeddings or graphs. Every capability is a plugin discovered
through Python entry points.
EOF
cat > corpus/loom.md <<'EOF'
A loom holds the warp fixed while the weft runs through it, over and under,
one pass at a time. The warp is the structure; the weft is what crosses it.
EOF
```

Index it, and then ask:

```bash id=index
weft index corpus --yes
```

```bash id=ask
weft ask "what does the weft do" --retrieve-only
```

`index` reports what it stored — `produced 1, nothing to produce 0, failed 0. nodes now stored: 2.`
— and `ask --retrieve-only` returns the passages it matched, ranked, each cited to the file it came
from. That flag is what keeps this offline: it stops at retrieval. Drop it and Weft asks a language
model to write an answer over those passages, which needs a provider mapped to a role in
`weft.toml` — `weft ask` refuses by name until one is, rather than quietly answering from nothing.
`manual/user-manual.md` has the two lines that map one.

**A pack is how you change any of that.** Swapping the chunker, adding a PDF backend or putting a
graph store beside the vector one is installing a distribution, not editing this one. `weft plugins
doctor` will then name it, at its version, with whatever it discloses about the network and
filesystem it touches — and what installing a pack actually trusts is stated on the release set's
own page rather than left to inference.

## Start here

**[`docs/README.md`](docs/README.md)** is the single source of truth: current phase, settled
decisions, what to do next, and which document owns what. Everything else is reached from there.

| | |
|---|---|
| [`docs/01-high-level-plan.md`](docs/01-high-level-plan.md) | The kernel boundary, async colour, the phase script, the fitness functions |
| [`docs/02-extension-model.md`](docs/02-extension-model.md) | Contracts, the payload model, the store family, discovery and the trust model |
| [`docs/03-cli.md`](docs/03-cli.md) | The command line as the single driving adapter |
| [`docs/04-reference-inventory.md`](docs/04-reference-inventory.md) | What to lift from the reference, what to rewrite, what to leave |
| [`docs/05-grilling-sessions.md`](docs/05-grilling-sessions.md) | The ten decision gates, six closed |
| [`docs/reference/`](docs/reference/) | The frozen audit of the reference codebase, and the review that started this |

## Layout

One repository, several distributions. That is what lets the kernel be verified by installing it
alone and importing it, rather than by a script that walks the source.

```text
packages/weft-kernel     registry, discovery, pipeline model, payload types
packages/weft-cli        the only driving adapter, and the only asyncio.run in the tree
packages/weft-extract    first-party pack: publishes the Extractor contract
packages/weft-chunk      first-party pack: publishes the Chunker contract
packages/weft-store      first-party pack: publishes the Store contract family
testing/weft-canary      test-only distribution, proves refused packs are never imported
tests/architecture       the fitness functions
```

## Development

```bash
uv sync
uv run poe ci-no-tests      # format, lint, types, architecture
uv run poe ci-checks        # the canonical full gate
uv run poe kernel-isolated  # install weft-kernel alone in a clean env and import it
```

Every architecture check must be reachable from `ci-checks`; a test asserts it.

### Driving a phase

The build is sequenced task by task in [`docs/build-ledger.md`](docs/build-ledger.md), and the
`phase-step` skill runs one task through **Orient → Red → Green → Verify → Finish**. Its Green phase
is dispatched to a `weft-implementer` subagent that cannot edit the test it is asked to satisfy —
so a test written from the settled documents stays a specification rather than becoming a
description of whatever got built. `.claude/skills/phase-step/` owns the detail.

```bash
python3 .claude/skills/phase-step/scripts/next_task.py   # what is next, and is its phase blocked
```

Typed into Claude Code:

```text
/model opus            orchestrator tier — the implementer pins its own, per dispatch
/phase-step            one task, the whole loop
/phase-step Phase 6 end to end: each unticked task in ledger order, one commit each,
            run the binary from outside the repo on each close, stop and name the gate
            if one is open
```

The phase boundary is detected rather than remembered: the script flags the phase's last unticked
task, and `phase-step` → *Close the phase* runs what that boundary owes — the whole-phase
`weft-qualities` reading, `reference-audit`, and `implement-ll` draining
[`docs/lessons.md`](docs/lessons.md) to empty, then the Exit criterion in `01` re-checked against
what exists rather than against the ticked boxes. **The queue is drained completely or its entries
are declined with a reason** — nothing is carried to a second phase close. Each of those skills is
still typed directly when you want it on its own.

## The reference

`a prior project` is a **parts reference, not a baseline** — a production RAG system whose extension points
were audited in detail before any of this was designed. That audit is frozen in `docs/reference/`, and
the source itself is reached through an untracked `reference` symlink to a sibling checkout. **No build,
test or packaging step reads through it.**

## Contributing

[`CONTRIBUTING.md`](CONTRIBUTING.md) — including which architecture decisions are settled and
therefore not up for negotiation in a pull request, and which are open and must not be defaulted.
[`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md) applies everywhere this project goes.

Security reports go through [`SECURITY.md`](SECURITY.md), which also states plainly what the plugin
model does and does not protect you from. The short version: **a pack runs with your full privileges,
and installing one is trusting it.**

## Licence

MIT — see [`LICENSE`](LICENSE).

Weft is original work and contains no source text from any other codebase — see [`NOTICE`](NOTICE).
Where a prior system informed a design, what was carried across is understanding: an approach, an
ordering, a measurement, the reason a guard exists. That is restated in this project's own words and
implemented fresh, which is why no third-party licence attaches to anything here.
