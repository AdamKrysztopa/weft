# Weft

A RAG engine built as a microkernel. The kernel knows nothing about PDFs, chunking, embeddings or
graphs: every capability is a plugin discovered through Python entry points, pipelines are data
derivable from other pipelines, and built-in packs are held to the same public contract as anything
a third party writes.

The warp is the fixed frame on a loom; the weft is every thread through it.

> **Status: built and running.** The walking skeleton (Phase 0) plus eleven further build phases —
> Phases 1 through 11, retrieval, generation, the CLI, evaluation, release, the agent pack, the
> product ladder, multimodal nodes, RAPTOR and the graph pack — are all closed. Indexing, retrieval,
> generation, evaluation and a graph pack all run end to end, proven from outside this repository.
> Of the decision log's thirty-three rows, thirty-one are settled; two gates are still open
> (`G14`, `G17`) and neither blocks anything that ships today. **The one debt every closed phase
> shared — a stranger installing the release from a real package index rather than a checkout — is
> what today's release discharges:** `weft-kernel` and `weft-rag` are published for the first time
> today, 2026-09-11. The four names published 2026-09-05 (`weft-generate`, `weft-embed`,
> `weft-command`, `weft-llm`) are yanked as of the same day; the code they named ships inside
> `weft-rag` now. `docs/README.md` carries the phase-by-phase record and the two open gates.

## Try it

Weft indexes a directory of documents and answers questions about them. Four commands, and the
whole thing runs offline — the default embedder is deterministic and needs no account.

```bash id=install
uv add weft-rag
```

`weft-rag` is the release set: one exactly-tested combination of the kernel, the CLI and every
first-party pack a working install needs — the extractor, the chunker, the embedder and the
pgvector store. There is nothing else to add. **The distribution is `weft-rag` and the command is
`weft`**: the name `weft` on PyPI belongs to an unrelated project, and the console script is this
distribution's own.

> Published for the first time today, 2026-09-11. To install an unreleased checkout instead —
> testing a change before its own release, say — use `uv pip install -e packages/weft-rag`;
> everything below is unchanged.

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
| [`docs/05-grilling-sessions.md`](docs/05-grilling-sessions.md) | Nineteen decision gates, seventeen settled, two open (`G14`, `G17`) |

## Layout

One repository, two distributions. That is what lets the kernel be verified by installing it
alone and importing it, rather than by a script that walks the source.

```text
packages/weft-kernel     registry, discovery, pipeline model, payload types
packages/weft-rag        the release set: twenty-three top-level packages, twenty-one packs, one wheel
  src/weft_cli/          the only driving adapter, and the only asyncio.run in the tree
  src/weft_extract/      first-party pack: publishes the Extractor contract
  src/weft_chunk/        first-party pack: publishes the Chunker contract
  src/weft_store/        first-party pack: publishes the Store contract family
  src/weft_kg/           first-party pack: the graph pack (Phase 11), behind no extra
testing/weft-canary      test-only distribution, proves refused packs are never imported
tests/architecture       the fitness functions
```

**Two published names, and only two.** `weft-rag` ships twenty-three top-level packages and
registers twenty-one of them as packs; each keeps its own identity — its `weft.packs` entry-point
name — which is what `weft plugins list` prints and what a `[packs.store]` block in `weft.toml`
configures. `weft-kernel` stays separate because installing it alone and importing it is what
proves it names no capability. Six of the twenty-one packs carry a dependency somebody may
decline: `pdf`, `openai`, `qdrant`, `otel` and `docling` are each behind an extra —
`pip install weft-rag[pdf]`, `[openai]`, `[qdrant]`, `[otel]`, `[docling]`, or `[all]` for every one
at once — and the sixth, `agent`, needs no extra because it imports nothing outside this wheel.
`weft-openai`, `weft-pdf`, `weft-qdrant`, `weft-otel`, `weft-docling`, `weft-agent` and `weft-kg`
are not distributions and are not published; the code they name ships inside `weft-rag`.

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
`weft-qualities` reading and `implement-ll` draining
[`docs/lessons.md`](docs/lessons.md) to empty, then the Exit criterion in `01` re-checked against
what exists rather than against the ticked boxes. **The queue is drained completely or its entries
are declined with a reason** — nothing is carried to a second phase close. Each of those skills is
still typed directly when you want it on its own.

## Contributing

[`CONTRIBUTING.md`](CONTRIBUTING.md) — including which architecture decisions are settled and
therefore not up for negotiation in a pull request, and which are open and must not be defaulted.
[`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md) applies everywhere this project goes.

Security reports go through [`SECURITY.md`](SECURITY.md), which also states plainly what the plugin
model does and does not protect you from. The short version: **a pack runs with your full privileges,
and installing one is trusting it.**

## Licence

MIT — see [`LICENSE`](LICENSE).

Weft carries no third party's source text — see [`NOTICE`](NOTICE), which states the three cases
precisely. Where a prior system informed a design, what was carried across is understanding: an
approach, an ordering, a measurement, the reason a guard exists. That is restated in this project's
own words and implemented fresh, which is why no third-party licence attaches to anything here.

One body of material is carried across as text, and it is nobody else's to license: `NOTICE` case 2
permits work **this project's own author wrote before this project began**. Where that happens the
lines are marked in place — `weft-prior-work begin: <source work>` opens the span and names where it
came from, `weft-prior-work end` closes it — so you can always tell the two origins apart without
asking anyone. Every source work carried that way is listed here, and
[`tests/architecture/test_release_licensing.py`](tests/architecture/test_release_licensing.py) fails
the build when this list and the markers in the tree disagree:

<!-- weft-prior-work-sources -->

- `graph-study` — a private knowledge-graph project of the same author's, predating Weft. **Three
  things are carried, each inside a marked span in the one file that uses it**, and around every one
  of them the dispatch, the persistence and the reasoning are Weft's own:

  - the **entity-atomicity filter** it developed against real papers — five rules that refuse a name
    for being a clause, an equation, a citation or a pointer to a document's own sections, plus the
    label-token guard that keeps *"table tennis"* out of the fourth rule — in
    [`weft_kg/atomicity.py`](packages/weft-rag/src/weft_kg/atomicity.py). What answers *which* rule
    fired, so every dropped candidate is counted under its own reason rather than summed, is Weft's;
  - the **acronym signals and the union-find** an entity-resolution pass closes its clusters with —
    the initialism rule and its stopword set, the short-form shape test, the Schwartz–Hearst
    definition patterns and the acronym-collision guard — in
    [`weft_kg/resolution.py`](packages/weft-rag/src/weft_kg/resolution.py). The donor computes
    similarity itself over a loaded matrix; Weft scores it in the database and keeps only the part
    SQL cannot do;
  - the **three-valued adjudication band** and the first-non-`None` chain that reads it — a ceiling,
    a floor, and an uncertain interval that abstains rather than guessing — in
    [`weft_kg/adjudication.py`](packages/weft-rag/src/weft_kg/adjudication.py). The donor asks about
    one name against a ranked candidate list and answers with an index into it; Weft asks a single
    question about one pair, and what a merge then does to the tables is its own.

  Nothing else from that project is here — not its prompts, not its store, not its pipeline.
