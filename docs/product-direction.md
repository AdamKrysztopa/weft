# Product direction — a working brief

**This is not a source of truth and it does not hold state.** `README.md` remains both. This file
exists for one reason: the direction below was established in conversation on 2026-09-05, and a
direction that lives only in a conversation is lost when the conversation ends. It is written to be
**dissolved** — once the two reference audits close, every section here moves into the document that owns
it (`01` for phases, `11` for multimodal, a new numbered document for graph, `04`-style inventory for
the second reference, `build-ledger.md` for tasks) and this file is deleted.

Nothing here is settled. Where a decision is named, it is named as **open**.

---

## 1. What Weft is for, in the owner's words

> *"I need weft to be the library to set up quickly rag systems from naive and baseless, to super
> advanced inducing multiple bases (vectors, graph, chunk, RAPTOR) search at the same time."*

and

> *"my goal is for weft to be richer than reference."*

Two things follow, and they are not the same thing:

- **A ladder.** Someone starts at no retrieval at all and climbs to every base searched at once,
  and each rung is a small delta rather than a rewrite. The engine already expresses this; almost
  none of the ladder ships (§3).
- **Richer than the reference.** Not *more ported files* — `04` §C exists precisely so Weft does not
  inherit the reference's mistakes. Richer means more capability **and** that the capability stays
  elastic: a third party adds a base with zero core edits. The studies are monoliths and cannot do
  that, which is the whole reason this project exists.

## 2. What already exists — measured 2026-09-05, not recalled

The engine for "several bases at once" is **largely built**. This was checked in the tree, and it
corrects an earlier assumption in the same conversation that it was not.

| Capability | Where it is |
|---|---|
| No retrieval at all — the naive floor | `no-retrieval` registered as a `Retriever`, `weft_retrieve/__init__.py:332`, with `pipelines/no-retrieval.yaml` |
| Vector search | `vector-top-k` (`:333`), plus `iterative-retrieval` (`:334`) and `corrective` (`:335`) |
| RAPTOR | **already built** — `RaptorSummarizer` registered as an `Expander`, `weft_index/__init__.py:63`, with its `summarize-cluster` `Prompt` at `:64` |
| Query fan-out | `multi-query`, the fourth `QueryTransform` — ledger **2.18** |
| Fusion across bases | `reciprocal-rank-fusion` (`weft_retrieve/fusion.py`) — ledger **2.18** |
| Not double-counting one chunk indexed several ways | `collapse-to-parent` — ledger **2.33**, which already names `raptor` representations as a case it handles |

**The load-bearing fact**, from ledger 2.18: `reciprocal-rank-fusion` accumulates hits by `Node.id`
across `payload.lists` **with no branch** asking whether a list arrived from a second channel on one
query (hybrid) or from one channel on a fan-out-derived query. One implementation serves both, and a
test fuses one of each shape in the same `Candidates` to prove the arithmetic is identical rather
than merely that both compile.

**And the seam for a new base was deliberately left open.** `Channel`
(`weft_retrieve/payload.py:64`) is a *vocabulary, not a field type* — `Query.channels` and
`RankedList.channel` are `str`. Its own docstring gives the reason: `02` names "hybrid search,
filtering, full text, **graph traversal**" as the ways backends genuinely differ, so a closed enum
would force a core edit every time somebody added a base.

## 3. The three gaps

1. **Graph is the one base that is not real.** It exists as `examples/weft-example-graph` (2,249
   lines, one pipeline `kg.yaml`) — an *example* pack written for Phase 5's independence test, not a
   shipped distribution. This is what the second reference supplies.
2. **The ladder does not ship.** Four pipeline documents exist in the entire tree
   (`no-retrieval.yaml`, `retrieve-then-generate.yaml`, `route.yaml`, and the example pack's
   `kg.yaml`). For a library whose promise is *naive to advanced, quickly*, the ladder **is** the
   product, and the engine can currently express far more of it than it ships. This is the largest
   gap between what Weft can do and what somebody can pick up.
3. **Multimodal.** Designed in full in `11-multimodal.md`, **no phase assignment**, seven open owner
   decisions D1–D7 with D1 blocking the rest. `weft-kernel` already ships `MediaType.IMAGE` and
   `MediaType.TABLE` — a closed core vocabulary naming two things nothing in the tree can produce.

## 4. Two references, and they are not governed the same way

| | `a prior project` | `graph-study-main` |
|---|---|---|
| Reached by | the untracked `reference` symlink | `/Users/adamkrysztopa/projects/graph-study-main` |
| Ownership | third party | **the project owner's own, unlicensed** |
| Discipline | read to understand, close the file, write fresh. No source text, ever | **may be copied as-is** — owner's decision, 2026-09-05 |
| Audit | `docs/reference/` (frozen) + `04-reference-inventory.md` | not yet written |

**The consequence that must not be discovered later.** `NOTICE` states as a property of *the
repository* that no source text from any other codebase enters it, and `tests/architecture/test_release_licensing.py`
and ledger task **6.11** exist to keep that true. Copying from `graph-study-main` violates nobody's
licence but it falsifies that sentence. `NOTICE` must be amended to distinguish the third-party
reference from the owner's own prior work, in the same commit as the first copied line — not after.

## 5. What the deliverable is

Stated by the owner, 2026-09-05: **plan the implementation, prove it with several examples, publish
everything.** Read literally, and it should be:

- **Plan** — tasks in `build-ledger.md`, each stating the property that must hold rather than the
  repair that will make it hold (`lessons.md` L7.1).
- **Prove** — *several examples*, not one. Weft's own standard is that a green gate is not a working
  binary; the ladder is proved by someone climbing it, in a directory that is not this repository.
- **Publish** — everything, to the index. Not a checkout.

## 6. What blocks what, as of 2026-09-05 — after both audits

Both audits are complete and land in `audit-a prior project-2026-09-05.md` and
`audit-graph-study-2026-09-05.md`. Read those for evidence; this section carries only the shape.

**The structural finding neither audit was asked for: there is no Phase 8.**
`01-high-level-plan.md` stops at Phase 7, which G12 blocks entirely. Every batch below that is not a
repair to shipped code has no phase to belong to. Extending the phase script is therefore the first
planning act, not a consequence of one.

- **G12** blocks **Phase 7**, and the graph reference supplies it two new positions rather than settling
  it: *autonomy licensed by reversibility of writes* rather than by supervision, and
  *propose-without-persisting then activate-from-a-file* as an approval channel that is not a slower
  spelling of `--yes`. Both are arguments for the session, not substitutes for it.
- **`11` D1** blocks all of multimodal.
- **Graph needs three decisions before any of it is schedulable**, in dependency order: is a graph
  store a member of the G4 family or a second paradigm; where may a corpus-wide revisable pass run
  and may its expensive output be durable (this one touches G2, G4, G5 and S5 at once); and where
  does a pack persist per-corpus operator-curated configuration, given that `with:` is
  per-stage-per-pipeline and `packs:` is per-installation.
- **The second driving adapter does not reopen.** The graph audit looked for an argument to reopen it
  and found the opposite: the source's own two invariants reached through three entry points is the
  best available evidence *for* Weft's rule, produced independently by the same author.
- **What is buildable today, touching no open gate:** every repair both audits found in shipped
  first-party code (§7), and the ladder (§3.2). That is a real body of work and it is where to start.

### The one thing that outranks the graph work

`weft-eval` and a corpus both exist, and neither audit found a reason to wait: **a falsification
instrument** — the ability to show a claimed improvement is not real — discharges an open
release-checklist question and is not blocked by any gate. The graph audit would schedule it first,
ahead of everything graph-shaped, and nothing contradicts that.

### Live defects both audits found in shipped code

Not features, not lifts — things that are wrong now, none needing a gate or a kernel line:

- **Unbounded `asyncio.gather`** at `weft_index/raptor.py:191` and `hypothetical_questions.py:93`.
  A 700-node corpus through `hypothetical-questions` is 700 concurrent LLM calls today.
- **RAPTOR degrades silently** — no input cap, no overflow retry, no degradation record. A run that
  dropped every overflowing cluster returns `Produced` and looks identical to a complete one.
- **`weft ask` bypasses the seam.** `ask.py:106-113` hand-writes `wrap(...)` for the embedder;
  `:133-140` awaits the store unwrapped. The author-must-remember failure the seam abolishes,
  failing twice inside one function, with no coverage check.
- **`bert_score(lang="en")` hardcoded** at `weft_eval/embedding_metrics.py:119` — silently mis-scores
  a Polish corpus, and fails quality requirement 6.
- **`MetricScore.value` unbounded**; `cosine_similarity` does not clamp, so `embedding-similarity`
  can return a negative score that propagates into `answer_correctness`.
- **`weft pipeline derive base ../../x`** writes outside `.weft/pipelines/`.
- **No atomic writes anywhere.** Four sites `write_text` user-visible files, including a whole-file
  read-modify-write of `weft.toml`, which holds the store DSN and the permission policy.
- **`NodeStore.add` lineage collision** — both backends silently agree on the wrong answer, and
  `delete_source` filters on `lineage.sources`, so this is a correctness hole rather than tidiness.
- **Fan-out participants are never closed** — constructed by G13's fan-out, closed by nobody.

### The founding-claim problem, which goes first

Both audits arrive at the same obligation from opposite directions. The copy check found Weft's
originality claim survives as engineering — 0 byte-identical files of 1,572 reference files hashed — but
**not in its absolute wording**: five to eight sites quote reference docstrings verbatim, attributed, and
`NOTICE` says "Weft contains no source text from any other codebase." Separately, §4's decision makes
copying from `graph-study-main` licit and falsifies the same sentence again. And the rule has **no
fitness function** — 33 files in `tests/architecture/` enforce lesser invariants; nothing scans for
reference text, which is `L6.12`'s shape applied to the property the repository is named for.

One amendment covers all three, and it is cheap to get wrong: it must distinguish the third-party
reference (write fresh, always) from the owner's own prior work (copyable) from short attributed
quotation of a cited rationale. There is also a **live rule conflict** to settle in the same act:
`weft_clean/artifact_remover.py:63,67` carries a reference regex under a "facts, not text" exception
while `04:144-145` says regexes specifically must be authored fresh.

## 7. Release state, 2026-09-05

`v0.1.0` tagged at `2525867`. PyPI rate-limited new-project creation (`429 Too many new projects
created`): **4 of 20 published** on the first run — `weft-command`, `weft-embed`, `weft-generate`,
`weft-llm` — with the remaining fifteen, the release set and the reproduction artefacts retried.
`ADAM_TODO.md` items 6 and 7 carry the repository-visibility and token-debt consequences.

Three defects were found by CI's first-ever executions and none by any local run: the lockfile was
gitignored as though it were a cache, a CI job carried `--no-project` copied from a job whose script
needs no dependencies, and a routing change erased the evidence a fitness function reads. The first
is logged as **L7.2** — `ci.yml` was written in Phase 0 and had executed **zero times**, because
there was no git remote until today.
