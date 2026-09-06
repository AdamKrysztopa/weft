# 12 · The roadmap past Phase 11

`01` plans Phases 0–11 and stops there. This document owns everything after, and it exists because
an outside review (2026-09-06) proposed eleven phases, 16–26, that had to be checked against the
tree before any of them could be scheduled. **Nine parallel researchers and two adversarial
reviewers did that check.** What follows is what survived it.

**Read this with `README.md`'s Status block, which says which tranche is live.** This document holds
the argument and the ordering; `README.md` holds the state.

---

## 0 · What the check found, in one paragraph

The proposed roadmap was written against commit `a7b7181` (2026-09-05 21:14) and does not carry an
expiry note. Nine Phase 9 commits landed the following morning and falsified two of its headline
findings outright — **A1** ("evaluation shortcuts to embedder plus store") was fixed by ledger task
`7.5` in `c1d527a`, and **A6** ("PDF extraction is primarily text-layer based") was falsified by
`9.6` and `9.7`. Of its eleven phases, **two duplicate work already in the ledger**, **three re-open
settled gates without the argument**, **four depend on `01`'s deferred rows whose reopen triggers
have not fired**, and **six of its contract sketches re-declare what G4 settled is derived** or
duplicate a shipped type. What is left is real, and most of it is smaller than the phase numbers
suggest. **Phases 12–15 exist nowhere in `docs/`** — they are four words in an owner's stated order,
and the proposed Phase 16 and Phase 26 both declare dependencies on them.

**Nothing below fires a single one of `01`'s deferred-row triggers.** That is the test this document
applies and it is the reason the plan is tranches rather than phases: a phase implies a gate and an
exit, and most of this is work `01` and the ledger already scheduled, waiting on nothing.

---

## 1 · The table

Complication is rated **for the work as this document scopes it**, not as the review proposed it —
several ratings collapse once the duplication is removed. MoSCoW is **order, never exclusion**:
every row gets built. A `WON'T` here means *not in this cycle, and here is what fires it* — a
`WON'T` with no stated trigger is a defect in the verdict, not a decision.

| # | Tranche / work | Complication | MoSCoW | What must be true first |
|---|---|---|---|---|
| **T0** | **Truth and publication** — the status banner, the changelog, the release protocol, and `uv publish` | LOW | **MUST** | Nothing |
| **T1** | **Measurable, in both languages** — `RunRecord.query_pipeline`, the three metric defects, Polish scoring | MEDIUM | **MUST** | T0 published, so a run can name a released version |
| **T2** | **The ladder tells the truth** — the four measured parameter defaults, `--explain`, `score_semantics` | LOW | **MUST** | T1's numbers returned |
| **T3a** | **Embeddable** — `runtime.run(name, args)`, one verb; `08` §33's promised Python documentation | MEDIUM | **SHOULD** | Nothing (runs beside T3b) |
| **T3b** | **Incremental ingest** — chunked batch iterator; make `02` §1010 true; `SourceStatus.INDEXING` | MEDIUM | **SHOULD** | Persists nothing keyed on `NodeId` — see T4 |
| **T4** | **The one-way door** — does the tenant enter the node digest? A `05` session, answered in writing either way | LOW to decide, VERY HIGH to defer | **MUST decide** | T3 persisted nothing on `NodeId` |
| **T5** | **Breadth at the edges** — `format-office`/`format-html` extras on 9.13, `feat-ocr-rapidocr`, `base_url`, a second provider account | LOW | **SHOULD** | Phase 9's `9.13` |
| **T6** | **Everything else** — each gated on a named trigger | HIGH+ | **WON'T yet** | See §5, one trigger per row |

---

## 2 · Tranche 0 — truth and publication

**The cheapest work in this document and the only critical path in it.**

`README.md` (the repository's public front page, not `docs/README.md`) says *"Status: Phase 0, not
yet built"* and *"six of ten architecture decisions are settled"*. Measured: eight phases are closed,
fifteen decision rows are settled, and the repository is **public**, one screen above a non-draft
"Latest" GitHub release describing fourteen shipped packs — with **zero release assets**. All seven
distribution names return 404 on PyPI. `CHANGELOG.md` is frozen at Phase 5 (2026-08-22).

**This is a release-process defect first and a documentation defect second.** `README.md` → *Protocol*
governs closing a gate; **nothing governs cutting a tag**, which is why `v2.1.0` shipped with a stale
changelog, no assets and an install command that 404s. Writing that protocol is part of this tranche.

**Publishing is the critical path and nothing else in this document comes close.** One act discharges
three downstream exits: Phase 6's Exit (*a stranger installs the release from the index*), Phase 7's
fourth exit clause, and every later phase's "from outside this repository" clause, which today is
proved against a checkout rather than an index. The proposed roadmap has it at Phase 26.
`uv publish` is deliberately the project owner's to run.

**A correction to carry:** the review claims `uv add weft-rag` in the README is a false instruction.
It is not — two lines below it the README says *"Not on an index yet."* The false claim is the status
banner. Repairing the wrong line would leave the real defect standing.

---

## 3 · Tranche 1 — measurable, in both languages

**Nothing in this tree is measurable until `RunRecord` can name the query rung.** `weft eval compare
--baseline` selects repetitions by `resolved_pipeline.name`; task `7.5` added `--query-pipeline` as a
second, independent dimension that the record does not carry. So runs of *different* rungs over one
ingest pipeline are indistinguishable repetitions of each other, which inflates the baseline's
measured spread and makes every later improvement fail to clear it. Task 8.8 built the falsification
instrument; this is the field that stops it being wrong about rungs.

Three metric defects ride with it, each a `09` §4.2 catalogue item reproduced in Weft's own code:

- **`recall@10` is computed over at most 8 candidates.** Every shipped rung ends in
  `repack: {top_n: 8}`; the named path does not oversample. V4's clause is that the `k` in a metric's
  name equals the `k` it computed — enforce it with a refusal rather than a comment.
- **Rank metrics are scored over `repack: reverse`'s deliberately inverted order.** `Answer.used` is
  the right *set* — `7.5` settled that — and is not a ranking once the packer has reversed it.
- **`mrr@k` is not a registered metric.** It exists in the repo-level `eval/metrics.py` and not in
  the pack.

**And the axis no single-topic researcher owned: language.** The product brief says Polish and
English; `09` §5.2's V1 requires a non-English corpus body for exactly that reason. Measured:
`weft_eval.embedding_metrics` hardcodes `bert_score(lang="en")`, and `weft_store.pgvector_store`
defaults `text_search_config = "simple"` — unstemmed — while its own docstring says `simple` is *"the
default, not the right answer"* for Polish. So **hybrid retrieval in Polish is unstemmed and
generation scoring in Polish is wrong**, in shipped product. No proposed phase named a language.

---

## 4 · Tranche 2 — the ladder tells the truth

`01`'s requirement 6 is that a shipped technique is real and parameterisable. Weft ships two
retrieval defaults that **its own cited paper measures as wrong**, and the finding came from opening
the PDF Weft cites rather than from any check:

- **RRF `k: 60`** scores 0.695; `k = 10` scores 0.716.
- **Rerank candidate depth 20.** The paper's own words: *"With only 20 candidates, reranking is
  ineffective"* — Recall@5 0.458, against 0.826 at depth 50. **Weft's shipped default sits inside the
  regime where the technique it names does nothing.** A user who climbs `rerank-then-generate` and
  sees no gain concludes the ladder is decorative, which is a product defect and not an evidence task.
- **`hybrid-then-generate.yaml`'s comment asserts a weighted blend is "a tuning constant nobody can
  defend".** §IV-C-a of the same paper defends one: convex combination at α = 0.5 reaches 0.726,
  above RRF's 0.695. A shipped comment contradicted by the shipped citation.
- **Postgres text ranking runs with `normalization = 0`** — no length normalisation, which is one
  integer, unlike the missing IDF, which is not.

Change the defaults the measurement condemns, **or** record in each rung's own comment why a
dominated default stays. Do **not** deprecate dominated pipelines: it breaks FF16, whose waiver is
pinned empty, and the ladder is pedagogical — `hyde-then-retrieve` exists so a user can watch HyDE
lose, which is what the same paper measures it doing.

---

## 5 · Tranche 4 — the decision that gets more expensive every day

**`NodeId` is a content digest that excludes the tenant.** Two tenants indexing the same document
derive the same id; `weft_nodes.id` is the primary key and `ON CONFLICT (id) DO UPDATE` overwrites
`sources`. So tenant B's ingest replaces tenant A's row and erases A's source id, after which A can
no longer delete or reconcile its own document and B's deletion takes A's content with it.

**This is not exploitable today** — `tenant_id` is the constant `"default"` and there is no network
listener anywhere in `packages/`. It is a latent design defect, not a live one, and `01`'s row is
explicit: *"carry a tenant identifier through the context from day one… but build no isolation
machinery until it is real."* Weft did the first half and did it well.

**But the deferral assumed the identifier could be retrofitted, and identity was settled in Phase 0
in a way that decides the retrofit's cost.** Nobody connected the two. Either the primary key becomes
composite — cheap in SQL, but every `get(ids)`, every lineage array and every citation needs a key it
does not have — or the tenant enters the digest, which **changes every node id in every existing
corpus** and invalidates every stored `BlobRef`, `RunRecord` and citation. That is a one-way door and
it is the only item here that gets monotonically more expensive with every corpus indexed.

**So the decision is Tranche 4 and the build is not.** Answer it in a `05` session, in writing, either
way. And write the paragraph that is true today and stated nowhere: **a library has no security
boundary; the deployment is it** — a second tenant is a second `dsn` or collection, enforced by
Postgres roles or a collection-scoped token, and nothing below the configuration enforces anything.

---

## 6 · Tranche 6 — deferred, each with the trigger that fires it

Every row is work this project intends to do. None of it starts on a preference.

| Work | Fires when |
|---|---|
| Source-enumeration seam (`SourceConnector`) | A real second source — a user with an object store, or `weft index <url>`. `02` §1: a contract with one implementation is a guess |
| TEI/HTTP local embedder, `cross-encoder-rerank` | Tranche 2's depth measurement returns the paper's ≥0.826-at-50 |
| BM25 `TextSearch` backend | Chosen: `timescale/pg_textsearch` (PostgreSQL licence). `pg_search` is AGPL and unavailable on stock managed Postgres; VectorChord-bm25 is **now confirmed** dual AGPL/Elastic |
| Durable job broker | `01`: indexing must survive process restart, or one run exceeds a session. And when it does, the job table lives in **the same Postgres as the data** — a separate store is a dual write |
| Service tier, HTTP, MCP server | `01`: someone outside the process needs to call this. The MCP ecosystem ships *clients*, which is `weft-agent`'s business; the protocol also broke on 2026-07-28 |
| Late interaction / multi-vector | G4-a's own recorded trigger: a second backend with a MaxSim operator, or the storage ratio moving an order of magnitude. Neither has fired, and G4-a's recommendation is *do not open it* |
| Production-interaction capture and tuning | Presupposes a production. Its one cheap idea — paired replay against a derived interval — is mostly shipped as `weft eval compare` |
| `weft-sentence-transformers` | The TEI HTTP path proves insufficient. Measured cost: 792 MB / 41 distributions on macOS, ~2.9 GB on Linux against plain PyPI |
| 1.0 graduation | `09` §2.2's six preconditions, three of which are unmet. Note that `llama-index` is at 0.14.24 and among the two most-adopted RAG frameworks: **1.0 is not the adoption gate; publishing is** |

---

## 7 · What no proposed phase covers, and this document claims

1. **Polish as a measured language, end to end.** §3. Structurally invisible to a fan-out whose
   topics are subsystems, because its axis is product scope.
2. **Shipped worked examples.** Twenty-eight pipeline documents and no examples directory. Every
   phase Exit says "from outside this repository" and each is a one-off act by the builder rather
   than an artefact a user re-runs.
3. **The conformance kit.** Promised by `07` §1, `08` §1 and `01` — which already *measured* that it
   does not exist. It is precisely what a third party needs in order to write the second store
   backend that several gates keep deferring for want of one.
4. **Atomic writes to `weft.toml`.** It is a whole-file read-modify-write holding the store DSN and
   the permission policy, and four separate proposals want to write it.
5. **Cost and latency as a column on the ladder.** *Measurable* is one of three adjectives in the
   product brief. `RunRecord` carries `TokenUsage`; nothing reports cost per rung, so a user cannot
   see that one rung costs forty times another — the most decision-relevant number for choosing one.
6. **The upgrade path.** `09`'s *a store written by release n is read by release n+1* is unticked,
   while task `9.17` moved `STORE_CONTRACT_VERSION` and needed an `ALTER TABLE` that a 2,260-test
   gate did not catch (`L9.60`).
7. **Capacity for the lessons drain.** The queue is not free, and eleven proposed phases added none.

---

## 8 · Sequencing hazards the review missed

- **Tranches 3b and 4 share `NodeId`.** A durable delta plan or transformation cache keyed on a node
  id computed *before* the digest decision is computed twice. This is why T3b is constrained to key
  its verdict on `SourceRecord` and to persist nothing on `NodeId`.
- **Three proposed phases all write `RunRecord`.** One schema change wearing three phase numbers.
  `9.17` has just demonstrated what an uncoordinated writer to a persisted record costs.
- **A cache key without a model fingerprint is wrong at the first commit** — incremental ingest and
  provider work share that key and the review separated them.
