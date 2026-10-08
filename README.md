# Weft

Weft packages selectable RAG pipelines with reproducible comparisons, executable claims and
inspectable routing decisions. Dense, lexical and hybrid retrieval, reranking, query rewriting,
context construction, RAPTOR trees, a fact graph and whole-corpus reading each ship as a named
pipeline. Weft measures them against plain dense retrieval and commits every result with its run
records, including the null and negative ones. Its evidence router picks a costlier pipeline only
when one of those measured claims supports it.

Underneath, Weft is a microkernel. The kernel knows nothing about PDFs, chunking, embeddings or
graphs: every capability is a plugin discovered through Python entry points, pipelines are data
derivable from other pipelines, and built-in packs are held to the same public contract as anything
a third party writes.

The warp is the fixed frame on a loom; the weft is every thread through it.

## What extra RAG bought on corpus-wide questions

80 synthesis questions ("what themes recur across these papers?") over 16 papers, one run per arm,
answer correctness judged by an LLM, Weft's own implementation of each method. Each row is paired
question by question against dense retrieval (`retrieve-then-generate`):

| Weft pipeline | change in answer correctness vs dense | 95% interval | generation tokens per question (`global-synthesis`) |
|---|---|---|---|
| dense retrieval (baseline) | — | — | 1,673 |
| read the whole corpus (`whole-corpus-wide-then-generate`) | **+0.059** | +0.030 to +0.089 | 262,128 (about 157×) |
| summarise the retrieved passages (`summarise-then-generate`) | −0.018 | −0.049 to +0.010 | 7,879 (477 answering, 7,402 summarising) |
| fact graph fused with vectors (`graph-and-vector-rrf`) | **−0.080** | −0.111 to −0.049 | 1,034 |

Tokens are counted per question at answer time, so building the fact graph is not included.
Reading everything was better, at about 157 times the generation tokens (`global-synthesis`).
Summarising gained nothing, and our graph pipeline did worse. That is a result about these implementations on this corpus, not
about GraphRAG methods in general. RAPTOR ran as a separate experiment with its own dense baseline:
+0.025 [0.000, +0.051], below the +0.05 margin the experiment set before it ran
([table](eval/experiments/global-synthesis-raptor/table.md)). Records, configurations and
limitations: [`eval/experiments/global-synthesis/table.md`](eval/experiments/global-synthesis/table.md)
and [`manual/evidence.md`](manual/evidence.md) §4. Each row is a claim in `eval/claims/` that
`weft eval claims check` recomputes from those records.

**So the default stays conservative.** `route-by-evidence` routes to whole-corpus reading only when
the corpus is the size it was measured at and you have given it a prompt-token budget that holds
the corpus. With no budget, it explains why it fell back:

```text
$ weft route explain "what themes recur across these documents?"
…
route: retrieve-then-generate (fell-through)
  facts: corpus.base_complete=True, corpus.fits_context=True, corpus.leaf_tokens=64
  constraints: max_prompt_tokens=0
  policy: e6dbca5bec067724
  reasons:
    rule 'whole-corpus-when-it-fits' did not hold: corpus.leaf_tokens is 64, the rule needs gte 200000
    no rule was usable, so the fallback 'retrieve-then-generate' answers
```

The quoted output comes from the release wheel, run outside this repository on the two-file corpus
from *Try it*, with the configuration under *A real answer, with citations*.

> **Status.** Indexing, retrieval, generation, evaluation, the graph pack, index layers and
> evidence-driven routing all run end to end from the published wheels. `weft-kernel` and `weft-rag`
> are on PyPI, and
> <!-- weft-release:begin -->this README describes `weft-rag 3.2.0` / `weft-kernel 0.3.1`<!-- weft-release:end -->.
> The four names published 2026-09-05 (`weft-generate`, `weft-embed`, `weft-command`, `weft-llm`)
> are yanked; their code ships inside `weft-rag`. The phase record, the decision log and the lessons
> queue are kept locally by the developer, not in this repository. *Layout* explains what that means
> when a docstring cites one of them by id.

## Try it

Weft indexes a directory of documents and answers questions about them. The path below starts in
an empty directory and needs no account and no model, because the default embedder needs neither.

**Read that last clause carefully: the default is a smoke test, not a search engine.** `hash`
derives each vector from a SHA-256 digest of the chunk's text, so it is deterministic and free
and carries *no meaning at all* — two passages about the same subject are no closer together
than two about different ones. What the commands below prove is that the pipeline runs end
to end on your machine: extract, chunk, embed and store, then a lexical search over the words
themselves, which needs no embedder. `weft ask` will not rank by `hash` vectors unless
`weft.toml` chose `hash`: asked to, it refuses and names the ways on, because an arbitrary ranking
that looks plausible is worse than none. One line in `weft.toml` —
`[services] embed = "openai-embeddings"`, or `"openai-compatible-embeddings"` pointed at a
server you run — switches it for a real one, and then the results mean something. Measured on
TechQA, a local `BAAI/bge-m3` trails OpenAI's `text-embedding-3-large` by 0.085 mrr@5
(`eval/claims/index-openai-large.techqa.mrr-at-5.toml`); `manual/operations-guide.md` has the
other two corpora and the trade-off.

**What you need:** Python 3.12 or newer, [`uv`](https://docs.astral.sh/uv/), and Postgres with
the `pgvector` extension — Docker brings one up below. Nothing else for the offline path. The
cited answer under *A real answer, with citations* also needs an OpenAI API key, and each of its
calls is metered.

```bash id=install
uv init --bare --python 3.12
uv add weft-rag
source .venv/bin/activate
```

`uv init` makes the directory a project for `uv add` to add to; skip it where a `pyproject.toml`
already exists. Activating the environment puts `weft` on your `PATH` for this shell
(`.venv\Scripts\activate` on Windows); without it, prefix each `weft` below with `uv run`.

`weft-rag` is the release set: one exactly-tested combination of the kernel, the CLI and every
first-party pack a working install needs — the extractor, the chunker, the embedder and the
pgvector store. There is nothing else to add. **The distribution is `weft-rag` and the command is
`weft`**: the name `weft` on PyPI belongs to an unrelated project, and the console script is this
distribution's own.

> That resolves against PyPI. To install an unreleased checkout instead — testing a change before
> its own release, say — use `uv pip install -e packages/weft-rag`; everything below is unchanged.

Then the database. This repository's `compose.yaml` runs `pgvector/pgvector:pg16` on port 5433,
with user, password and database all `weft`; its other services sit behind profiles and stay off.
Fetch it into the same directory and start it:

```bash id=database
curl -fsSLO https://raw.githubusercontent.com/AdamKrysztopa/weft/main/compose.yaml
docker compose up -d --wait
```

Tell Weft where it is. For a Postgres of your own, put its URL here instead; the `vector`
extension must be available on it:

```bash id=env
export WEFT_DATABASE_URL="postgresql://weft:weft@localhost:5433/weft"
```

That variable is the whole configuration. No `weft.toml` is needed for this, and leaving it unset
does not crash — `weft plugins doctor` reports the `store` pack as `failed` and names the
missing field. (`store` is the pack; `weft-rag` is the distribution it ships in. The doctor lists
packs, because a pack is what you configure.)

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
thread by thread, until the cloth exists.
EOF
```

Index it, and then ask:

```bash id=index
weft index corpus
```

```bash id=ask
weft ask "what does the weft do" --pipeline lexical-retrieve --retrieve-only
```

`index` reports what it stored — `2 documents: 2 indexed, 0 unchanged. nodes now stored: 2.`
— and `ask` returns the passages whose words match the question, each cited to the file it came
from, ranked by the store's own text search. `--retrieve-only` is what keeps this offline: it
stops at retrieval. Drop it and Weft asks a language model to write an answer over those passages, which needs a provider mapped to a role in
`weft.toml` — `weft ask` refuses by name until one is, rather than quietly answering from nothing.
`manual/user-manual.md` has the two lines that map one.

### A real answer, with citations

The offline path above proves the plumbing. For search by meaning and a generated answer, install
the OpenAI extra, export `OPENAI_API_KEY`, and put this `weft.toml` beside `corpus/`:

```bash
uv add "weft-rag[openai]"
```

```toml
[services]
embed = "openai-embeddings"
route = "route-by-evidence"

[llm.roles]
generate = { provider = "openai", model = "gpt-5.6-luna", context_tokens = 272000 }

[packs.openai]
api_key = "${env:OPENAI_API_KEY}"
```

A target holds one embedder's vectors, and the `hash` run above already filled the live one. Index
into a second target and make it live. Promoting normally asks for two scored runs as evidence;
`--without-evidence` records that you promoted on your own judgement:

```text
$ weft index corpus --target semantic
batch 1/1 · 2/2 documents queryable · 0.3 s since start · 0.0 MB
indexing into target 'semantic' (candidate; live is 'default').
2 documents: 2 indexed, 0 unchanged. nodes now stored: 2.
mode 'repair' — 1 participant(s):
  pgvector (weft-rag): examined 0, removed 0, backfilled 0

$ weft target promote semantic --without-evidence --yes
promoted 'semantic' on pgvector (previous live: 'default')
```

On a fresh database, a plain `weft index corpus` is enough. Then ask a question that shares no
words with the passage that answers it:

```text
$ weft ask "which part of the loom stays still while weaving?"
The warp stays still while weaving. [2]
routed to: retrieve-then-generate
  [2] file:///…/corpus/loom.md — 05616bbb13dffd67d04cb5cab4fa3eafd4e5f231a0ca34a046b26869d6626270
```

The answer cites the file and the content digest of the passage it used. `weft route explain` with
the same question prints the routing receipt shown at the top of this page. `weft ask --explain`
adds the score, every route that was not offered and why, and the time each stage took. These
transcripts were run from the built `weft-rag` wheel, outside this repository, straight after the
offline path above. Model output varies from run to run. Every call is a metered OpenAI API call.

**A pack is how you change any of that.** Swapping the chunker, adding a PDF backend or putting a
graph store beside the vector one is installing a distribution, not editing this one. `weft plugins
doctor` will then name it, at its version, with whatever it discloses about the network and
filesystem it touches — and what installing a pack actually trusts is stated on the release set's
own page rather than left to inference.

## Ask while it indexes

`weft index` writes a folder in batches of 25, and each batch is searchable the moment it lands, so
you can start asking in a second shell straight away. Measured on 2026-09-22 from that day's
release wheel, outside this repository, on 100 arXiv PDFs (243 MB) through `pdf-text` extraction,
`text-embedding-3-large` and pgvector with no enrichment layer. Median of five runs, range in
brackets, on one Apple Silicon laptop (12 cores, 24 GB):

| | seconds after `weft index` starts |
|---|---|
| first batch searchable (25 of 100 documents) | **30.0** (29.8–31.0) |
| first answer citing the source paper, asked about that batch | **34.2** (34.0–43.4) |
| base index complete, all 100 searchable | **127.2** (126.4–127.8); one earlier unbatched run, 226.8, had nothing searchable until the end |

A second shell asked two questions in turn, pausing 5 s after each pair. An answer counted when
its output named the expected paper's file and carried a citation marker; nothing judged whether
the answer was correct. The clocks stop at
the base index: a layer built afterwards (below) was not timed. `weft ask` p95 was 3.87 s during
indexing and 3.65 s after, a per-run ratio of 0.93–1.11. In every run, a question about a paper in
the last batch was answered *"the corpus does not answer this — N sources are not yet indexed"*
while that batch was pending, not with a guess. No run recorded that question answered after its
batch landed. The version measured, the runs, the harness and one Qdrant run are in
[`eval/fast-ingest/table.md`](eval/fast-ingest/table.md).

## Enrich it later, without re-indexing

The slow, clever parts of RAG (hypothetical questions per chunk, RAPTOR summary trees, an
LLM-extracted fact graph) are **layers**: built from the chunks already stored, after the base is
searchable, so they never hold up the first answer.

```bash
weft index corpus --layers enrich-with-questions            # base first, then the layer
weft index corpus --layers enrich-with-raptor --layers-only # a layer over an indexed corpus
```

Four ship: `enrich-with-questions`, `enrich-with-raptor` per document or corpus-wide, and
`enrich-with-facts-and-graph`. A layer never re-extracts or re-embeds the base. An interrupted
build resumes without re-paying the clusters it kept. A deleted or changed document hides a stale
corpus layer from every read until it is rebuilt. A second writer is refused by name. All of it was
soak-tested from the release wheel: every shipped layer alone and all four stacked, delete,
re-parse, interrupt and every reconcile mode, twice on pgvector and twice on Qdrant, with zero
violations (`scripts/soak_layers.py --shape`).

## Or skip retrieval altogether

For a corpus that fits in the model's context, `whole-corpus-then-generate` hands the generator
every chunk instead of retrieving. It refuses by name, never truncating, when the corpus is over its
token bound. Measured on Weft's own 107 English questions over 16 papers (253k tokens),
`gpt-5.6-luna` answering and judging both arms:

| | `retrieve-then-generate` | `whole-corpus-then-generate` |
|---|---|---|
| answer correctness (LLM judge) | 0.672 | **0.743**, paired 95% interval **+0.039 to +0.117** |
| prompt tokens per question (`whole-corpus-en`) | 1,541 | 261,498 (~170×) |
| p50 latency | 3.7 s | 5.5 s |

It is a better answer at a very different price, so the router does not pick it for you: ask it
with `--pipeline`. On the 12 Polish questions of a 15k-token corpus, no difference was detectable.
The records and tables are in [`eval/experiments/whole-corpus-en/`](eval/experiments/whole-corpus-en/table.md).

## What Weft has measured on harder questions

Each experiment below states its decision rule before it runs: a rung has to beat one search
(`retrieve-then-generate`) by a set margin in LLM-judged answer correctness, on the paired 95%
interval. The records and tables are committed, and every number regenerates from them.

| question | what was tried | result against one search |
|---|---|---|
| Corpus-wide ("what themes recur across these papers?"), 80 questions over 16 papers | read everything · RAPTOR tree over the corpus · summarise retrieved passages · graph of extracted facts | reading everything **+0.059** [+0.030, +0.089], worth it at ~157× the tokens (`global-synthesis`) · RAPTOR +0.025 [0.000, +0.051], below the margin · summarise no gain · graph **−0.080**, worse |
| Routing, 107 questions | the shipped model router and score router, against always one search | no gain (−0.000, +0.012); the model router doubles p95 latency. Re-run once its rungs with nothing to read were withheld: +0.022 [−0.001, +0.046], inconclusive at the +0.03 margin, 3× the p50 latency |
| Multi-hop (MuSiQue), 600 questions | iterative retrieval, hybrid, multi-query, broad-and-refined | nothing clears +0.05; iterative +0.018 |
| One long document (QASPER, QuALITY) | adjacent chunks, context construction | nothing clears +0.05; on QuALITY that holds even though the right document is found 99% of the time |

A position-swapped pairwise judge, calibrated at 61% agreement with gold and so read as
preference, prefers the answers from reading everything 98% of the time for comprehensiveness,
and RAPTOR's about 70%. The null results carry the same weight as the wins. Where one search is as
good, it is the cheaper and faster choice. [`manual/evidence.md`](manual/evidence.md) has every
experiment, its data, its cost and what it means for a deployment. The tables:
[corpus-wide](eval/experiments/global-synthesis/table.md) and
[its RAPTOR arm](eval/experiments/global-synthesis-raptor/table.md) ·
[routing](eval/experiments/route-shipped-en/table.md) ·
[multi-hop](eval/experiments/musique-retrieval/table.md) ·
[long documents](eval/experiments/qasper-long-document/table.md).

## Start here

**[`manual/quickstart.md`](manual/quickstart.md) is the next page**: the four commands above with
the database wired up, the failure paths, and what each line of output actually means. After it the
route runs on — day-to-day configuration in [`manual/user-manual.md`](manual/user-manual.md), then
writing a pack of your own in [`manual/pack-author-guide.md`](manual/pack-author-guide.md).
`docs/08-manuals.md` §1 owns that order, and a check holds each page to naming the one after it, so
a hand-off that stops being true fails the build rather than stranding a reader.

**[`manual/evidence.md`](manual/evidence.md) is what Weft has measured and what it recommends
running**: every experiment, its data and result, the evidence status of every shipped rung, and the
questions not yet tested with the test proposed for each.

Why it is shaped the way it is — for anyone reading the code rather than running it:

| | |
|---|---|
| [`docs/01-high-level-plan.md`](docs/01-high-level-plan.md) | The kernel boundary, async colour, the phase script, the fitness functions |
| [`docs/02-extension-model.md`](docs/02-extension-model.md) | Contracts, the payload model, the store family, discovery and the trust model |
| [`docs/03-cli.md`](docs/03-cli.md) | The command line as the single driving adapter |
| [`docs/08-manuals.md`](docs/08-manuals.md) | The shipped documentation set, the public route, and the check that keeps each page honest |

## Layout

One repository, two distributions. That is what lets the kernel be verified by installing it
alone and importing it, rather than by a script that walks the source.

```text
packages/weft-kernel     registry, discovery, pipeline model, payload types
packages/weft-rag        the release set: twenty-six top-level packages, twenty-three packs, one wheel
  src/weft_cli/          the only driving adapter, and the only asyncio.run in the tree
  src/weft_extract/      first-party pack: publishes the Extractor contract
  src/weft_chunk/        first-party pack: publishes the Chunker contract
  src/weft_store/        first-party pack: publishes the Store contract family
  src/weft_kg/           first-party pack: the graph pack (Phase 11), behind no extra
testing/weft-canary      test-only distribution, proves refused packs are never imported
tests/architecture       the fitness functions
```

**Two published names, and only two.** `weft-rag` ships twenty-six top-level packages and
registers twenty-three of them as packs; each keeps its own identity — its `weft.packs` entry-point
name — which is what `weft plugins list` prints and what a `[packs.store]` block in `weft.toml`
configures. `weft-kernel` stays separate because installing it alone and importing it is what
proves it names no capability. A pack whose outside library somebody may decline sits behind an
extra — `pip install weft-rag[pdf]`, `[openai]`, `[qdrant]`, `[otel]`, `[docling]`,
`[cross-encoder]`, or `[all]` for every one at once — and `agent` needs no extra because it imports
nothing outside this wheel.
`weft-openai`, `weft-pdf`, `weft-qdrant`, `weft-otel`, `weft-docling`, `weft-agent` and `weft-kg`
are not distributions and are not published; the code they name ships inside `weft-rag`.

**One directory in the tree above is not in the tree you cloned.** `docs/internal/` holds how the
work is done — the build ledger, the decision log, the lessons queue — and `.gitignore` keeps it
out of version control, so no clone and no wheel has it. Docstrings and documents here still cite
it, in the form `` `docs/internal/lessons.md` `L8.5` ``: **the id is the datum**, a stable name for
the reason a guard exists, and the sentence beside it carries the fact. Nothing you need in order
to use, run or extend Weft is behind one of those ids; where the reasoning itself is load-bearing
it lives in `docs/01` through `docs/13`, which are tracked.

## Development

```bash
uv sync
uv run poe ci-no-tests      # format, lint, types, architecture
uv run poe ci-checks        # the canonical full gate
uv run poe kernel-isolated  # install weft-kernel alone in a clean env and import it
```

Every architecture check must be reachable from `ci-checks`; a test asserts it.

### Driving a phase

The build is sequenced task by task in `docs/internal/build-ledger.md` — developer-local, so a
clone does not have it — and the `phase-step` skill runs one task through **Orient → Red → Green → Verify → Finish**. Its Green phase
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
`docs/internal/lessons.md` to empty, then the Exit criterion in `01` re-checked against
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
