# 12 · The roadmap past Phase 11

`01` plans Phases 0–11 and stops there. This document owns everything after, and it exists because
an outside review (2026-09-06) proposed eleven phases, 16–26, that had to be checked against the
tree before any of them could be scheduled. **Nine parallel researchers and two adversarial
reviewers did that check.** What follows is what survived it.

**Read this with `README.md`'s Status block, which says which phase is live.** This document holds
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
applies and it is the reason several phases split, one dissolves, and one is added: the numbers the review chose
are kept, and what moved is stated per row rather than hidden behind a new unit of work.

---

## 1 · The phases

Eleven phases were proposed, 16–26. All eleven keep their numbers here. What changed after checking
each against the tree is stated per row: **two split**, **one dissolves into work the ledger already
holds**, **one moves to the front**, and **one is added** — Phase 27, because the sharpest defect the
check found belongs to no proposed phase.

Complication is rated for the work as this document scopes it, not as the review proposed it;
several ratings collapse once the duplication is removed. **MoSCoW is order, never exclusion.**
Every phase gets built. A `WON'T` means *not in this cycle*, and it carries the trigger that fires
it — a `WON'T` with no trigger is a defect in the verdict, not a decision.

| Phase | Introduces | Complication | MoSCoW | Depends on |
|---|---|---|---|---|
| **26a** | **Public truth and publication.** Status banner, changelog, release protocol, `uv publish`. **Split out of Phase 26 and moved first** — see §2 | LOW | **MUST** | nothing |
| **16a** | **Evidence truth.** Query-rung identity in `RunRecord`, the three metric defects, Polish scoring. **Phase 16's evidence half** | MEDIUM | **MUST** | 26a |
| **27** | **Node identity.** Does provenance enter the content digest? A live data-loss defect. **New — belongs to no proposed phase** | MEDIUM to repair, VERY HIGH to defer | **MUST** | nothing; its trigger has fired |
| **21a** | **The ladder tells the truth.** `--explain`, `score_semantics`, and whichever shipped defaults Weft's *own* measurements condemn | LOW | **SHOULD** | 16a, and §4's citations recovered |
| **24a** | **Embeddable Python API.** One verb over the `Command` registry, plus `08` §33's promised documentation. **Phase 24 minus its HTTP adapter** | MEDIUM | **SHOULD** | nothing |
| **17** | **Incremental ingestion.** Chunked batch iterator, honour `02` §1010, `SourceStatus.INDEXING` | MEDIUM | **SHOULD** | 27 settled first |
| **19** | **Format breadth.** docx/pptx/html extras and an OCR engine — **folded into ledger task `9.13`; the phase dissolves** (§7) | LOW | **SHOULD** | `9.13` |
| **20a** | **Provider reach.** Document `base_url`, and a second `weft.packs` account so local-embeddings-plus-hosted-chat is representable | LOW | **SHOULD** | nothing |
| **16b** | **Capability manifest and reconciliation.** The derived manifest, maturity, index availability, evidence links. **Phase 16's other half — it is A2's work, not A1's** | LOW-MEDIUM | **SHOULD** | 26a |
| **26b** | **Extension kit.** Publish a conformance kit an author can import, and a pack template | MEDIUM | **SHOULD** | 26a |
| **18** | **Source connectors.** An enumeration seam, then HTTP and object-store connectors | MEDIUM (seam) to VERY HIGH (as proposed) | **WON'T yet** | a real second source |
| **20b** | **Local model packs.** TEI/HTTP embedder, `cross-encoder-rerank`, later `sentence-transformers` | MEDIUM | **WON'T yet** | 21a's depth measurement |
| **21b** | **Retrieval backends.** A BM25 `TextSearch` pack; sparse vectors; late interaction | HIGH | **WON'T yet** | per-row triggers, §6 |
| **22** | **Tenant isolation.** Scope enforcement, ACL, purge. The *machinery*, not the identity decision | VERY HIGH | **WON'T yet** | `01`'s second-tenant trigger |
| **23** | **Durable jobs.** A job store — in the same Postgres as the data, never SQLite beside it | HIGH | **WON'T yet** | `01`'s restart trigger |
| **24b** | **Service tier.** HTTP adapter, and an MCP server over it | HIGH | **WON'T yet** | `01`'s out-of-process trigger, and 22 |
| **25** | **Interaction capture.** Feedback, experiments, promotion — and the **only** privacy, consent and retention scope anywhere in the proposal | VERY HIGH | **WON'T yet** | 22, 23, 24b |
| **26c** | **1.0 graduation.** `09` §2.2's six preconditions | VERY HIGH | **WON'T yet** | three unmet preconditions |

**What the letters mean.** A phase that split keeps its number and gains a letter, so `16a` and `16b`
stay findable from the review that proposed Phase 16. Nothing is renamed away from the vocabulary the
review and the owner already share.

## 2 · Phase 26a — public truth and publication, moved to the front

**The cheapest work in this document and the only critical path in it.**

`README.md` (the repository's public front page, not `docs/README.md`) says *"Status: Phase 0, not
yet built"* and *"six of ten architecture decisions are settled"*. Measured: eight phases are closed,
fifteen decision rows are settled, and the repository is **public**, one screen above a non-draft
"Latest" GitHub release describing fourteen shipped packs — with **zero release assets**. All seven
distribution names return 404 on PyPI. `CHANGELOG.md` is frozen at Phase 5 (2026-08-22).

**This is a release-process defect first and a documentation defect second.** `README.md` → *Protocol*
governs closing a gate; **nothing governs cutting a tag**, which is why `v2.1.0` shipped with a stale
changelog, no assets and an install command that 404s. Writing that protocol is part of this phase.

**Publishing is the critical path and nothing else in this document comes close.** One act discharges
three downstream exits: Phase 6's Exit (*a stranger installs the release from the index*), Phase 7's
fourth exit clause, and every later phase's "from outside this repository" clause, which today is
proved against a checkout rather than an index. The proposed roadmap has it at Phase 26.
`uv publish` is deliberately the project owner's to run.

**A correction to carry:** the review claims `uv add weft-rag` in the README is a false instruction.
It is not — two lines below it the README says *"Not on an index yet."* The false claim is the status
banner. Repairing the wrong line would leave the real defect standing.

---

## 3 · Phase 16a — measurable, in both languages

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

## 4 · Phase 21a — the ladder tells the truth

`01`'s requirement 6 is that a shipped technique is real and parameterisable. A user who climbs
`rerank-then-generate` and sees no gain concludes the ladder is decorative, which is a product defect
and not an evidence task — so if any shipped default sits in a regime where the technique it names
does nothing, that is worth finding.

**The claim that Weft ships two such defaults did not survive checking, and this section records the
failure rather than the finding, because the failure is the more useful of the two.** A researcher
reported that Weft's own cited paper measures RRF `k: 60` (0.695) below `k = 10` (0.716), and rerank
candidate depth 20 as ineffective (0.458) against 0.826 at depth 50. Verified at source:

- **`0.716`, `0.458` and `0.826` appear nowhere in this repository.** `0.695` appears exactly once —
  `11` §6, where it is **hybrid Recall@5 on T²-RAGBench**, part of the chain 0.587 → 0.695 → 0.816.
  It is not a point on an RRF `k`-sweep, and no `k`-sweep is cited anywhere. `weft_retrieve.fusion`
  cites Cormack/Clarke/Büttcher (SIGIR 2009) for the formula and for `k = 60` as **that paper's own
  constant**.
- **"Rerank candidate depth 20" misreads the parameter.** `weft_retrieve.rerank`'s `top_n` is
  *output truncation*, and the same module says candidate depth is the retriever's `top_k`,
  deliberately not this plugin's. `rerank-then-generate.yaml` says `top_n: 20` is chosen to make the
  stage "a reordering of the whole retrieved set rather than a truncation of it" — the opposite of
  what the finding assumed it was.

**So the numbers may be real in some paper, and none of them is traceable from anything Weft cites.**
This project's rule is that a factual claim carries something a reader can check; the rule as written
scopes that to claims *about the tree*, and this was a claim about the *literature*, used to justify
changing the tree. Same standard, and the gap is worth closing: a number quoted from a paper carries
its table or figure, or it does not move a default.

What survives, and is genuinely cheap:

- **Postgres text ranking runs with `normalization = 0`** — `weft_store.pgvector_store` passes no
  normalization argument, so there is no length normalisation. One integer, unlike the missing IDF,
  which is architectural and is `11` §6 rank 4's real subject.
- **`--explain` and a `score_semantics` label do not exist** — both appear in the tree exactly once
  each, inside the untracked review file. They are new work, not an extension of something shipped.

And the thing to do before changing any default: **run the sweep on Weft's own corpus**, which is
what Phase 16a makes possible. Do not deprecate dominated pipelines either way — it breaks FF16,
whose waiver is pinned empty, and the ladder is pedagogical: `hyde-then-retrieve` exists so a user
can watch HyDE lose, which is what `11` §6 measures it doing.

## 5 · Phase 27 — node identity, and the bug hiding behind the tenant question

**`NodeId` is a content digest over `media_type`, `content`, sorted `parent_ids` and `ordinal`
(`weft_kernel/payload/node.py:245-260 "byte-ide"`). It excludes the tenant — and it excludes the source.**

The tenant half is the one an outside review raised, and it is real: two tenants indexing the same
document derive the same id, `weft_nodes.id` is the primary key, and `ON CONFLICT (id) DO UPDATE SET
… sources = EXCLUDED.sources` (`weft_store/pgvector_store.py:750-756 "%(embedd"`) is a wholesale *replace*
rather than a merge. But `tenant_id` is the constant `"default"` and there is no network listener
anywhere in `packages/`, so that half was filed as latent.

**Filing it as latent was wrong, and running it is what showed why.** The same mechanism fires inside
a single tenant, today, with no second tenant and no attacker. Two files with identical bytes in one
corpus produce identical node ids — `weft_extract/text.py:93-96 "is the f"s resolved path — stable across"s resolved path — stable across"` documents that collision as
*intended* — while their `SourceId`s differ, because a source id is the resolved path. So the second
ingest's `ON CONFLICT` overwrites `sources` with its own id alone, and the first document's nodes
silently become the second's. Measured against the live pgvector store, on a throwaway database:

```text
node ids equal: True
count after both ingests: 1
stored sources: frozenset({'/beta.txt'})
delete alpha removed nodes: 0
alpha's content still retrievable: identical bytes
```

`delete_source` is `DELETE FROM weft_nodes WHERE %s = ANY(sources)`, so **deleting the first document
reports success, removes nothing, drops its `weft_sources` row, and leaves its content retrievable
forever.** A reported success that did nothing is worse than a failure, which is the rule
`CLAUDE.md` states for silent fallbacks, arriving through a data path rather than an exception path.

**This and `L9.37` are one defect failing in opposite directions.** There, a re-parse produces
*different* ids so the old nodes linger; here, duplicate content produces the *same* id so one
document's nodes are taken by another. Both are content-addressed identity that excludes provenance.
Two lessons pointing at one cause is the signal that the fix belongs at the cause, and that is why
this is one phase rather than a repair filed under each.

**So the decision is one question with three consequences.** Does provenance — the source, the
tenant, or both — enter the digest? Either the primary key becomes composite, which is cheap in SQL
but needs a key that `get(ids)`, every lineage array and every citation currently do not carry; or
provenance enters the digest, which **changes every node id in every existing corpus** and
invalidates every stored `BlobRef`, `RunRecord` and citation. That is a one-way door, it is the only
phase in this document whose cost grows monotonically with every corpus indexed, and the single-tenant
half means it is a defect to repair rather than a deferral to schedule.

Two things ride with it and are cheap. Write down the fact that is true today and stated nowhere:
**a library has no security boundary; the deployment is it** — a second tenant is a second `dsn` or
collection, enforced by Postgres roles or a collection-scoped token, and nothing below the
configuration enforces anything. And build no isolation machinery: `01`'s row defers that until *the
second tenant*, and that trigger needs an operational reading — a second `tenant_id` value in one
deployment, or an in-process caller that is not the CLI — because "real" is not a condition anything
can check.

## 6 · The deferred phases, each with the trigger that fires it

Every row is work this project intends to do. None of it starts on a preference.

| Work | Fires when |
|---|---|
| Source-enumeration seam (`SourceConnector`) | A real second source — a user with an object store, or `weft index <url>`. `02` §1: a contract with one implementation is a guess |
| TEI/HTTP local embedder, `cross-encoder-rerank` | Phase 21a's depth measurement returns the paper's ≥0.826-at-50 |
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
3. **A conformance kit a third party can import.** Careful here, because the obvious claim is wrong:
   a store conformance kit *does* exist, at `tests/integration/test_store_conformance.py`, and it
   runs against both backends. What does not exist is a **published** one — `01` measured that
   nothing under `packages/` carries a kit, and republishing this one was proposed at a Phase 2 task
   and refused. Four documents promise a kit an author can install; the tree holds one only this
   repository can run. It is precisely what a third party needs in order to write the second backend
   that several gates keep deferring for want of one, so either the promises are made true or they
   are withdrawn.
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

- **Phases 17 and 27 share `NodeId`.** A durable delta plan or transformation cache keyed on a node
  id computed *before* the digest decision is computed twice. This is why Phase 17 is constrained to key
  its verdict on `SourceRecord` and to persist nothing on `NodeId` until Phase 27 has settled.
- **Three proposed phases all write `RunRecord`.** One schema change wearing three phase numbers.
  `9.17` has just demonstrated what an uncoordinated writer to a persisted record costs.
- **A cache key without a model fingerprint is wrong at the first commit** — incremental ingest and
  provider work share that key and the review separated them.
