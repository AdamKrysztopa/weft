# What Weft has measured, and what it recommends

This page answers three questions for someone deciding what to run:

1. **What should I run today, and on what evidence?**
2. **What has not been tested yet, and how would it be?**
3. **What exactly was measured, on what data, and what came out?**

Every number on this page comes from a committed result file under `eval/`, cited beside it, so a
number here can be checked against the run that produced it. A `tests/docs/` check fails if a
committed result directory is not cited here. A null result is reported as fully as a gain: "we
tried it and it did not help on this data" is what stops the same experiment from being run twice.

**How to read an interval.** Differences are paired over the same questions, with a 95% bootstrap
interval in brackets. From Phase 40 on, a result gets one of five labels, applied first-match:

- *harm*: the interval is entirely below zero.
- *benefit ruled out*: the upper end is below the worthwhile effect, 0.05 mrr@5.
- *worthwhile*: the interval is above zero and the estimate is at least 0.05.
- *positive, below worthwhile*: the interval is above zero, but the estimate is under 0.05.
- *inconclusive*: anything else.

Results on reused public benchmarks are labelled **exploratory**, because earlier phases tuned on
those same questions.

---

## 1. What to run today

- **Use a real embedder.** The default `[services] embed = "hash"` exists so Weft runs offline with no
  account. It carries no meaning, and no retrieval result on this page was measured with it except
  as a floor. Every measurement that found anything used `openai-embeddings`
  (`text-embedding-3-small` or `-3-large`). Selecting one is the single change most likely to
  matter.
- **Keep dense retrieval, `retrieve-then-generate`, as the default.** It is the best measured
  first stage. On Open RAGBench (1,548 questions) dense scored recall@5 0.986 and mrr@5 0.949.
  Hybrid came in *below* it, mrr@5 −0.021 [−0.028, −0.014], and lexical alone reached recall@5
  0.244 (`eval/experiments/orb-retrieval-baseline/table.md`).
- **Do not turn on hybrid search for English prose.** It lost to dense on Open RAGBench. It also
  lost on TechQA (mrr@5 0.511 against 0.611), though that second result is recorded in the build
  ledger only.
- **Opt-in rungs are there to try on your own data, not because they won here.** None of them
  beat the default by the pre-set margin on any data Weft holds. The closest are:
  - `context-construction-then-generate`: token recall +0.038 to +0.050, for about twice the
    prompt tokens.
  - `adjacent-chunks-then-generate`: +0.031 to +0.042 on the two English sets.
  - `mmr-then-generate`: mrr@5 +0.041 [+0.013, +0.075] on the 53 operator questions, and nothing
    on the other two sets.
- **Do not add a cross-encoder reranker on the strength of its reputation.** Measured over dense's
  own top 50, `bge-reranker-v2-m3` gained +0.030 mrr@5 [+0.011, +0.049] on product search — real,
  but under the 0.05 worth having — and **lost 0.104 [−0.132, −0.077] on technical support
  questions**, where it moved the right document down on every slice. A small reranker (MiniLM-L6)
  did the same: +0.014 and −0.107. `anchor-promote`, the cheap string-matching reorderer, also hurt
  TechQA (−0.027) and did not help product search. If you try a reranker, measure it on your own
  questions before trusting it. **Asking a strong LLM to do the reranking did roughly twice as
  well** — `gpt-5.6-luna` gained +0.058 [+0.043, +0.074] on the same ESCI pool — but it is priced
  per question rather than per server, it ran once, and every slice of it is underpowered.
- **For a question about the whole corpus, read all of it when it fits.** On 80 corpus-wide
  questions, `whole-corpus-then-generate` beat one search by +0.059 answer correctness
  [+0.030, +0.089], at about 160× the prompt tokens. A corpus-wide RAPTOR tree gained +0.025
  [0.000, +0.051], under the margin; summarising retrieved passages gained nothing; and the
  graph rung over extracted facts did worse, −0.080 (§4, Phase 44).
- **Keep the fixed router.** The model-driven `route` and `route-by-score` tied always using one
  search on the 107 English questions, and `route` more than doubled p95 latency (§4, Phase 44).
- **Most shipped settings are unmeasured defaults**, not tuned values: chunk size 512 with overlap
  50, `top_k` 20, `top_n` 8, the packer's `reverse` order, and RRF's k 60 and 0.8 text
  weight. Treat them as reasonable starting points.

---

## 2. What has not been tested, and the tests proposed

| gap | rungs it covers | proposed test | data | cost (estimate) | what it would decide |
|---|---|---|---|---|---|
| **Multi-hop questions** | `graph-then-generate`, `graph-2hop-then-generate`, `graph-and-vector-rrf`, `graph-then-rerank`, `iterative-retrieve`, `multi-query-then-retrieve`, and `ircot` when built | recall@5/10 against dense, sliced by hop count | MuSiQue-Ans dev, 300 questions stratified by hops (CC BY 4.0 as recorded; host terms read at source before download) | ≈ $3 planned for `ircot`; `llm-facts` extraction extra, scaled to the corpus | a rung above zero on 2+ hops without losing 1-hop questions is routed to them; no gain withdraws the multi-hop claim from its route summary; harm withdraws the rung |
| **Long documents, RAPTOR's own regime** | `index-with-raptor`, `index-with-deep-raptor`, `index-with-adrap`, `raptor-and-leaves-rrf` | the RAPTOR paper's datasets and metrics, against leaves only | QASPER (named in the catalogue), NarrativeQA, QuALITY; licences read at source before download | summariser plus embeddings, a few dollars per build, times six repetitions | a gain names RAPTOR's regime in its rung; another null states it in the catalogue; deep RAPTOR, already a measured regression, may be withdrawn |
| **Corpus-wide ("global") questions** | `summarise-then-generate`, RAPTOR rungs | LLM-judged comprehensiveness and diversity, pairwise | owner-written global questions over Weft's own corpus; needs a new judge metric first | under $5 for about 100 questions × 4 arms × 2, estimated | route global questions to the winner, or withdraw the global claim |
| **Query transforms and rerankers where dense has room** | `hyde-then-retrieve`, `multi-query-then-retrieve`, `step-back-then-retrieve`, `boolean-then-retrieve`, `corrective-retrieve`, `broad-and-refined-rrf`, `rerank-then-generate`, `hybrid-normalized-scores`, `index-with-keywords`, `index-with-questions` | mrr@5 against dense by replay, Phase 40's protocol | TechQA, 610 questions (dense mrr@5 0.611, so there is headroom) | query-side ≈ $0.12 per arm per repetition; index-side rungs ≈ $49, over the $5 cap | *worthwhile* makes a default candidate only through an untouched-set reading; positive stays opt-in; harm withdraws the rung |
| **Answer-side rungs** | `grade-then-generate`, `contradiction-aware`, `draft-then-refine`, `summarise-then-generate`, `no-retrieval` (control) | token recall, plus refusal on unanswerable questions | Weft's own 107 English and 17 unanswerable questions | ≈ $3 | a gain at the pre-set margin makes a default candidate; a rung beaten by `no-retrieval` is withdrawn |
| **Follow-up questions** | `rewrite-then-retrieve` | recall@5 on the follow-up turn | no conversational set exists yet | not yet priced | keep opt-in or withdraw |
| **Routing** | `route`, `route-by-score`, `route-fixed` | the routed rung's end metric against always using one rung | the union of the sets above, each question labelled with its winning rung | one router call per question | whether `weft ask` keeps the router by default |
| **Extractors and embedders on PDFs** | `index-pdf*`, `index-messy-text`, `index-polish`; `hash` against real embedders | recall@5 sliced by evidence type (text, table, image) | Open RAGBench dev, 1,548 questions (licence read at source) | ≈ $3.87 per 3-large ingest, ≈ $0.60 per 3-small | an extractor that wins the table and image slices without losing text becomes `index-pdf`'s default candidate; the first measured number for `hash` against a real embedder |

**Four of these gaps have since been tested (§4, Phase 44):** multi-hop questions (MuSiQue),
long documents (QASPER, then QuALITY), corpus-wide questions, and routing. The rows are kept as
the tests that were proposed.

**Weft's graph rungs are not GraphRAG.** They walk an entity's neighbourhood. GraphRAG answers
corpus-wide questions by summarising communities, and Weft ships no community summaries
(`docs/10-technique-catalogue.md`, §1.4). So multi-hop is the graph rungs' test, and corpus-wide
questions are RAPTOR's and the summary rung's.

---

## 3. Evidence status of every shipped rung

Taken from the shipped pipeline documents, the same set `weft pipeline list` prints, not from
memory: `tests/docs/test_evidence_page.py` fails when a shipped rung is missing from this table.
The five statuses:

- *helps*: measured, and it beat the baseline.
- *no gain*: measured, with nothing to show over the baseline.
- *harms*: measured, and it did worse.
- *wrong questions*: measured, but only on questions that are not the kind it was built for.
- *never*: never measured, or measured only as a control: a rung with no claim has no comparison to
  state.

The table is generated: `weft eval claims render` prints it from the claim files in `eval/claims/`,
each recomputed from the committed run records it names, and `tests/docs/test_evidence_claims_block.py`
fails when this block differs from that render. A row's evidence is the experiment it was recomputed
from. Edit a claim file, never this block.

**A status hides a verdict, and the verdict is what routing reads.** *helps* covers two readings of
the paired interval against the margin the experiment fixed before it ran: **worthwhile** (the
interval is above zero and the difference reaches the margin) and **positive below margin** (above
zero, but smaller than the margin, so not worth the price). Each row prints both, as
*helps (worthwhile)* or *helps (positive-below-margin)*. An automatic router may cite only a
**worthwhile** claim resting on committed records; a ledger claim cannot be recomputed, so it cannot
be cited either. `weft eval claims check` refuses a claim whose stated verdict the records do not give.

**When evidence stops being evidence.** A claim is *pinned* by `weft eval claims pin <claim>`, which
recomputes it and writes the fingerprint of what it was validated against. `weft eval claims check`
then reads each claim as **valid** (every pinned component matches the running tree),
**definitely stale** (one has changed, and the row names it) or **possibly stale** (not pinned, or
not resolvable here). A rule of a shipped router that cites anything but a *valid* claim fails
fitness function 38.

| Changes the fingerprint (invalidates) | Does not |
|---|---|
| The stages of the rung or the baseline: a plugin, a stage's configuration, a stage added or removed | A comment, a rename, or a `vars` entry no stage reads (`route.summary`) |
| The stages of the index pipeline either arm read | The version of `weft-rag` |
| The judge prompt, when the metric is an LLM judge | Documentation, the manual, any other file in the repository |
| The profiler version, when the regime or a router reads a profile | Your `weft.toml`: its roles, accounts and database |

What it does not cover, stated so it is not assumed: the model a `[llm.roles]` entry names and the
embedding model an account setting selects are properties of a deployment, so a claim measured with
one is not marked stale on a machine using another; the layer pipelines an arm reads are named in a
record but their stages are not, so they are not compared; and a metric that is not a judge is
trusted to be the same code. Pinning says *the records still speak for these pipelines*; read the
diff before committing one.

**Why most rows still read *possibly stale*.** A claim is pinned here only after the stages its own
records ran have been compared with today's. On 2026-10-07, 11 of the 52 claims passed and are
pinned: every arm of §4's corpus-wide comparison, whole-corpus reading on the fetch and operator
questions, the model router, and the three local-embedding claims. Nine are ledger claims, with no records to compare. The other 32
failed the comparison, most because records taken under `weft-rag` 2.7.0 resolved their index
pipeline against `NodeStore` 2.x and the store contract is now 3.x, and a major contract version
moves a pipeline's identity by definition. Those stay unpinned until their experiments run again.

<!-- claims:begin -->
| rung | status | evidence |
|---|---|---|
| `adjacent-chunks-then-generate` | **helps (positive-below-margin)** against `retrieve-then-generate` on `token_recall` (en, validation-en): +0.042 (95% interval +0.026 to +0.060), n 108 — possibly-stale: no evidence fingerprint is pinned: run `weft eval claims pin`; recorded under weft-rag 2.7.0; this is 3.2.0; **helps (positive-below-margin)** against `retrieve-then-generate` on `token_recall` (en, validation-en): +0.031 (95% interval +0.006 to +0.056), n 106 — possibly-stale: no evidence fingerprint is pinned: run `weft eval claims pin`; recorded under weft-rag 2.7.0; this is 3.2.0; **no-gain (benefit-ruled-out)** against `retrieve-then-generate` on `token_recall` (pl, pl-wiki): -0.009 (95% interval -0.041 to +0.029), n 24 — possibly-stale: no evidence fingerprint is pinned: run `weft eval claims pin`; recorded under weft-rag 2.7.0; this is 3.2.0 | `eval/experiments/context-construction-en-fetch-widen`, `eval/experiments/context-construction-en-operator-widen`, `eval/experiments/context-construction-pl-widen` |
| `anchor-promote-retrieve` | **no-gain (benefit-ruled-out)** against `retrieve-then-generate` on `mrr@5` (en, esci): +0.006 (95% interval -0.001 to +0.014), n 830 — possibly-stale: no evidence fingerprint is pinned: run `weft eval claims pin`; recorded under weft-rag 2.7.0; this is 3.2.0; **harms (harm)** against `retrieve-then-generate` on `mrr@5` (en, techqa): -0.027 (95% interval -0.049 to -0.006), n 610 — possibly-stale: no evidence fingerprint is pinned: run `weft eval claims pin`; recorded under weft-rag 2.7.0; this is 3.2.0 | `eval/pool-promotion/runs` |
| `anchor-promote-then-generate` | **no-gain (benefit-ruled-out)** against `retrieve-then-generate` on `mrr@5` (en, esci): +0.006 (95% interval -0.001 to +0.014), n 830 — possibly-stale: no evidence fingerprint is pinned: run `weft eval claims pin`; recorded under weft-rag 2.7.0; this is 3.2.0; **harms (harm)** against `retrieve-then-generate` on `mrr@5` (en, techqa): -0.027 (95% interval -0.049 to -0.006), n 610 — possibly-stale: no evidence fingerprint is pinned: run `weft eval claims pin`; recorded under weft-rag 2.7.0; this is 3.2.0 | `eval/pool-promotion/runs` |
| `context-construction-then-generate` | **helps (positive-below-margin)** against `retrieve-then-generate` on `token_recall` (en, validation-en): +0.038 (95% interval +0.017 to +0.059), n 108 — possibly-stale: no evidence fingerprint is pinned: run `weft eval claims pin`; recorded under weft-rag 2.7.0; this is 3.2.0; **helps (worthwhile)** against `retrieve-then-generate` on `token_recall` (en, validation-en): +0.050 (95% interval +0.027 to +0.076), n 106 — possibly-stale: no evidence fingerprint is pinned: run `weft eval claims pin`; recorded under weft-rag 2.7.0; this is 3.2.0; **no-gain (benefit-ruled-out)** against `retrieve-then-generate` on `token_recall` (pl, pl-wiki): -0.011 (95% interval -0.056 to +0.027), n 24 — possibly-stale: no evidence fingerprint is pinned: run `weft eval claims pin`; recorded under weft-rag 2.7.0; this is 3.2.0 | `eval/experiments/context-construction-en-fetch-widen`, `eval/experiments/context-construction-en-operator-widen`, `eval/experiments/context-construction-pl-widen` |
| `cross-encoder-rerank-then-generate` | **no-gain (benefit-ruled-out)** against `retrieve-then-generate` on `mrr@5` (en, esci): +0.030 (95% interval +0.011 to +0.049), n 830 — possibly-stale: no evidence fingerprint is pinned: run `weft eval claims pin`; recorded under weft-rag 2.7.0; this is 3.2.0; **no-gain (benefit-ruled-out)** against `retrieve-then-generate` on `mrr@5` (en, esci): +0.014 (95% interval -0.006 to +0.034), n 830 — possibly-stale: no evidence fingerprint is pinned: run `weft eval claims pin`; recorded under weft-rag 2.7.0; this is 3.2.0; **harms (harm)** against `retrieve-then-generate` on `mrr@5` (en, techqa): -0.104 (95% interval -0.132 to -0.077), n 610 — possibly-stale: no evidence fingerprint is pinned: run `weft eval claims pin`; recorded under weft-rag 2.7.0; this is 3.2.0; **harms (harm)** against `retrieve-then-generate` on `mrr@5` (en, techqa): -0.107 (95% interval -0.134 to -0.080), n 610 — possibly-stale: no evidence fingerprint is pinned: run `weft eval claims pin`; recorded under weft-rag 2.7.0; this is 3.2.0 | `eval/pool-promotion/runs` |
| `cross-encoder-retrieve` | **no-gain (benefit-ruled-out)** against `retrieve-then-generate` on `mrr@5` (en, esci): +0.030 (95% interval +0.011 to +0.049), n 830 — possibly-stale: no evidence fingerprint is pinned: run `weft eval claims pin`; recorded under weft-rag 2.7.0; this is 3.2.0; **no-gain (benefit-ruled-out)** against `retrieve-then-generate` on `mrr@5` (en, esci): +0.014 (95% interval -0.006 to +0.034), n 830 — possibly-stale: no evidence fingerprint is pinned: run `weft eval claims pin`; recorded under weft-rag 2.7.0; this is 3.2.0; **harms (harm)** against `retrieve-then-generate` on `mrr@5` (en, techqa): -0.104 (95% interval -0.132 to -0.077), n 610 — possibly-stale: no evidence fingerprint is pinned: run `weft eval claims pin`; recorded under weft-rag 2.7.0; this is 3.2.0; **harms (harm)** against `retrieve-then-generate` on `mrr@5` (en, techqa): -0.107 (95% interval -0.134 to -0.080), n 610 — possibly-stale: no evidence fingerprint is pinned: run `weft eval claims pin`; recorded under weft-rag 2.7.0; this is 3.2.0 | `eval/pool-promotion/runs` |
| `dedupe-then-generate` | **no-gain (benefit-ruled-out)** against `retrieve-then-generate` on `recall@5` (en, validation-en): +0.000 (95% interval +0.000 to +0.000), n 108 — possibly-stale: no evidence fingerprint is pinned: run `weft eval claims pin`; recorded under weft-rag 2.7.0; this is 3.2.0; **no-gain (benefit-ruled-out)** against `retrieve-then-generate` on `recall@5` (en, validation-en): +0.000 (95% interval +0.000 to +0.000), n 106 — possibly-stale: no evidence fingerprint is pinned: run `weft eval claims pin`; recorded under weft-rag 2.7.0; this is 3.2.0; **no-gain (benefit-ruled-out)** against `retrieve-then-generate` on `recall@5` (pl, pl-wiki): +0.000 (95% interval +0.000 to +0.000), n 24 — possibly-stale: no evidence fingerprint is pinned: run `weft eval claims pin`; recorded under weft-rag 2.7.0; this is 3.2.0 | `eval/experiments/context-construction-en-fetch-ir`, `eval/experiments/context-construction-en-operator-ir`, `eval/experiments/context-construction-pl-ir` |
| `enrich-with-facts-and-graph` | **harms (harm)** against `retrieve-then-generate` on `answer_correctness` (en, validation-en): -0.080 (95% interval -0.111 to -0.049), n 80 | `eval/experiments/global-synthesis` |
| `enrich-with-raptor` | **helps (positive-below-margin)** against `retrieve-then-generate` on `answer_correctness` (en, validation-en): +0.025 (95% interval +0.000 to +0.051), n 80 | `eval/experiments/global-synthesis-raptor` |
| `graph-and-vector-rrf` | **harms (harm)** against `retrieve-then-generate` on `answer_correctness` (en, validation-en): -0.080 (95% interval -0.111 to -0.049), n 80 | `eval/experiments/global-synthesis` |
| `graph-then-generate` | **wrong-questions** against `retrieve-then-generate` on `recall@5` (en, Phase 11 exit fixture (12 one-sentence documents)): not reproducible from committed records (Phase 11 exit (ledger only)) | Phase 11 exit (ledger only) |
| `hybrid-normalized-scores` | **wrong-questions** against `hybrid-then-generate` on `recall@5` (en, weft-corpus-25-docs): not reproducible from committed records (task 21.9, eval/lexical-fusion/measurement.json (no experiment document; dense arm used the hash embedder)) | task 21.9, eval/lexical-fusion/measurement.json (no experiment document; dense arm used the hash embedder) |
| `hybrid-then-generate` | **harms (harm)** against `retrieve-then-generate` on `mrr@5` (en, open-ragbench): -0.021 (95% interval -0.028 to -0.014), n 4644 — possibly-stale: no evidence fingerprint is pinned: run `weft eval claims pin`; recorded under weft-rag 2.7.0; this is 3.2.0 | `eval/experiments/orb-retrieval-baseline` |
| `hyde-then-retrieve` | **no-gain (benefit-ruled-out)** against `retrieve-then-generate` on `mrr@5` (en, open-ragbench): -0.006 (95% interval -0.015 to +0.002), n 900 — possibly-stale: no evidence fingerprint is pinned: run `weft eval claims pin`; recorded under weft-rag 2.7.0; this is 3.2.0 | `eval/experiments/orb-hyde-questions` |
| `index-openai-large` | **helps (worthwhile)** against `index-openai-compatible` on `mrr@5` (en, esci): +0.109 (95% interval +0.087 to +0.132), n 830; **no-gain (benefit-ruled-out)** against `index-openai-compatible` on `mrr@5` (en, open-ragbench): +0.018 (95% interval +0.007 to +0.029), n 1548; **helps (worthwhile)** against `index-openai-compatible` on `mrr@5` (en, techqa): +0.085 (95% interval +0.059 to +0.112), n 610 | `eval/experiments/local-embed-esci`, `eval/experiments/local-embed-orb`, `eval/experiments/local-embed-techqa` |
| `index-with-cooccurrence` | **wrong-questions** against `retrieve-then-generate` on `recall@5` (en, Phase 11 exit fixture (12 one-sentence documents)): not reproducible from committed records (Phase 11 exit (ledger only)) | Phase 11 exit (ledger only) |
| `index-with-deep-raptor` | **wrong-questions** against `index-text` on `mean_average_precision` (en, weft-fetch-tier-pdfs): not reproducible from committed records (16a re-measurement, eval/raptor-baseline/after-16a/remeasurement.json (MAP -0.023 [-0.047, -0.005]; no experiment document)) | 16a re-measurement, eval/raptor-baseline/after-16a/remeasurement.json (MAP -0.023 [-0.047, -0.005]; no experiment document) |
| `index-with-facts` | **wrong-questions** against `retrieve-then-generate` on `recall@5` (en, Phase 11 exit fixture (12 one-sentence documents)): not reproducible from committed records (Phase 11 exit (ledger only)) | Phase 11 exit (ledger only) |
| `index-with-facts-openai` | **wrong-questions** against `retrieve-then-generate` on `recall@5` (en, Phase 11 exit fixture (12 one-sentence documents)): not reproducible from committed records (Phase 11 exit (ledger only)) | Phase 11 exit (ledger only) |
| `index-with-questions` | **no-gain (benefit-ruled-out)** against `retrieve-then-generate` on `mrr@5` (en, open-ragbench): -0.005 (95% interval -0.016 to +0.006), n 900 — possibly-stale: no evidence fingerprint is pinned: run `weft eval claims pin`; recorded under weft-rag 2.7.0; this is 3.2.0 | `eval/experiments/orb-hyde-questions` |
| `index-with-raptor` | **wrong-questions** against `index-text` on `mean_average_precision` (en, weft-fetch-tier-pdfs): not reproducible from committed records (16a re-measurement, eval/raptor-baseline/after-16a/remeasurement.json (no experiment document)) | 16a re-measurement, eval/raptor-baseline/after-16a/remeasurement.json (no experiment document) |
| `intent-and-anchors-then-generate` | **no-gain (benefit-ruled-out)** against `retrieve-then-generate` on `mrr@5` (en, esci and techqa (held-out splits)): not reproducible from committed records (Phase 39 (ledger only, records not committed)) | Phase 39 (ledger only, records not committed) |
| `lexical-retrieve` | **harms (harm)** against `retrieve-then-generate` on `recall@5` (en, open-ragbench): -0.742 (95% interval -0.764 to -0.720), n 4644 — possibly-stale: no evidence fingerprint is pinned: run `weft eval claims pin`; recorded under weft-rag 2.7.0; this is 3.2.0 | `eval/experiments/orb-retrieval-baseline` |
| `mmr-then-generate` | **no-gain (benefit-ruled-out)** against `retrieve-then-generate` on `recall@5` (en, validation-en): +0.000 (95% interval +0.000 to +0.000), n 108 — possibly-stale: no evidence fingerprint is pinned: run `weft eval claims pin`; recorded under weft-rag 2.7.0; this is 3.2.0; **helps (worthwhile)** against `retrieve-then-generate` on `recall@5` (en, validation-en): +0.082 (95% interval +0.025 to +0.157), n 106 — possibly-stale: no evidence fingerprint is pinned: run `weft eval claims pin`; recorded under weft-rag 2.7.0; this is 3.2.0; **no-gain (benefit-ruled-out)** against `retrieve-then-generate` on `recall@5` (pl, pl-wiki): +0.000 (95% interval +0.000 to +0.000), n 24 — possibly-stale: no evidence fingerprint is pinned: run `weft eval claims pin`; recorded under weft-rag 2.7.0; this is 3.2.0 | `eval/experiments/context-construction-en-fetch-ir`, `eval/experiments/context-construction-en-operator-ir`, `eval/experiments/context-construction-pl-ir` |
| `raptor-and-leaves-rrf` | **helps (positive-below-margin)** against `retrieve-then-generate` on `answer_correctness` (en, validation-en): +0.025 (95% interval +0.000 to +0.051), n 80 | `eval/experiments/global-synthesis-raptor` |
| `replay-llm-rerank` | **helps (worthwhile)** against `replay-identity` on `mrr@5` (en, esci): not reproducible from committed records (ledger `41.4`) | ledger `41.4` |
| `retrieve-then-generate` | **no-gain (benefit-ruled-out)** against `hybrid-then-generate` on `mrr@5` (en, open-ragbench): +0.021 (95% interval +0.014 to +0.028), n 4644 — possibly-stale: no evidence fingerprint is pinned: run `weft eval claims pin`; recorded under weft-rag 2.7.0; this is 3.2.0; **helps (worthwhile)** against `lexical-retrieve` on `recall@5` (en, open-ragbench): +0.742 (95% interval +0.720 to +0.765), n 4644 — possibly-stale: no evidence fingerprint is pinned: run `weft eval claims pin`; recorded under weft-rag 2.7.0; this is 3.2.0 | `eval/experiments/orb-retrieval-baseline` |
| `route` | **no-gain (benefit-ruled-out)** against `route-fixed` on `answer_correctness` (en, validation-en): -0.000 (95% interval -0.026 to +0.024), n 107 | `eval/experiments/route-shipped-en` |
| `route-by-score` | **no-gain (benefit-ruled-out)** against `route-fixed` on `answer_correctness` (en, validation-en): +0.012 (95% interval -0.008 to +0.030), n 107 — possibly-stale: no evidence fingerprint is pinned: run `weft eval claims pin` | `eval/experiments/route-shipped-en` |
| `summarise-then-generate` | **no-gain (benefit-ruled-out)** against `retrieve-then-generate` on `answer_correctness` (en, validation-en): -0.018 (95% interval -0.049 to +0.010), n 80 | `eval/experiments/global-synthesis` |
| `whole-corpus-then-generate` | **no-gain (inconclusive)** against `retrieve-then-generate` on `answer_correctness` (pl, pl-wiki) when corpus.base_complete eq True and corpus.fits_context eq True: +0.004 (95% interval -0.039 to +0.057), n 24 — possibly-stale: no evidence fingerprint is pinned: run `weft eval claims pin` | `eval/experiments/whole-corpus-pl` |
| `whole-corpus-wide-then-generate` | **helps (worthwhile)** against `retrieve-then-generate` on `answer_correctness` (en, validation-en) when corpus.base_complete eq True and corpus.fits_context eq True and corpus.leaf_tokens gte 200000 and corpus.leaf_tokens lte 260000: +0.075 (95% interval +0.039 to +0.117), n 210; **helps (worthwhile)** against `retrieve-then-generate` on `answer_correctness` (en, validation-en) when corpus.base_complete eq True and corpus.fits_context eq True and corpus.leaf_tokens gte 200000 and corpus.leaf_tokens lte 260000: +0.059 (95% interval +0.030 to +0.089), n 80 | `eval/experiments/whole-corpus-en`, `eval/experiments/global-synthesis` |
| `baseline`, `boolean-then-retrieve`, `broad-and-refined-rrf`, `contradiction-aware`, `corrective-retrieve`, `draft-then-refine`, `enrich-with-questions`, `grade-then-generate`, `graph-2hop-then-generate`, `graph-then-rerank`, `index-messy-text`, `index-openai`, `index-openai-compatible`, `index-pdf`, `index-pdf-described`, `index-pdf-learned`, `index-pdf-rows`, `index-pdf-text`, `index-pdf-undescribed`, `index-polish`, `index-qdrant`, `index-text`, `index-with-adrap`, `index-with-graph`, `index-with-keywords`, `iterative-retrieve`, `multi-query-then-retrieve`, `no-retrieval`, `preview-markdown`, `preview-plain`, `questions-then-generate`, `rerank-then-generate`, `rewrite-then-retrieve`, `route-by-evidence`, `route-fixed`, `step-back-then-retrieve` | never | none |
<!-- claims:end -->

---

## 4. The measurements, newest first

### Phase 44: do corpus-wide questions need something other than one search? (2026-09-29)

- **Question.** "What themes recur", "where do these papers disagree": questions whose answer is
  spread across the corpus. Does reading everything, summarising the retrieved passages, a RAPTOR
  tree over the corpus, or a graph of the corpus's facts beat `retrieve-then-generate`?
- **Data.** 80 corpus-wide questions over the 16 `validation-en` papers (253k tokens), written
  and verified for this experiment, each with a reference answer. One repetition per arm,
  `gpt-5.6-luna` answering and judging, `text-embedding-3-large`. RAPTOR ran in a document and
  store of its own, so that no arm read another arm's layer. About $9 of the $10 approved.
- **Result.** Against the pre-registered +0.05 `answer_correctness` margin:
  - `whole-corpus-then-generate`: **+0.059** (95% interval +0.030 to +0.089), `worthwhile`,
    at about 160× the generation prompt tokens (262k against 1.7k).
  - `raptor-and-leaves-rrf` over a corpus-wide tree: +0.025 (0.000 to +0.051),
    `positive-below-margin`.
  - `summarise-then-generate`: −0.018 (−0.049 to +0.010), `benefit-ruled-out`.
  - `graph-and-vector-rrf` over an LLM-extracted facts layer: **−0.080** (−0.111 to −0.049),
    `harm`.

  One search scored 0.496 and 0.485 in the two stores. A position-swapped pairwise judge, read
  as preference because it agrees with the gold-preferred answer only 0.607 of the time,
  prefers whole-corpus answers 0.98 on comprehensiveness, diversity and empowerment, and RAPTOR's
  0.69 to 0.74, while preferring one search's for directness. It prefers one search over the
  graph arm's 0.84 of the time on comprehensiveness. Sources:
  `eval/experiments/global-synthesis/table.md`,
  `eval/experiments/global-synthesis-raptor/table.md`, and each directory's `pairwise/`.
- **What it means for you.** For a question about the whole corpus, when the corpus fits the
  model's context, reading all of it is the one rung that measurably answers better, at a much
  higher price: ask with `--pipeline whole-corpus-then-generate`, raising its `max_tokens` to
  the corpus as the shipped `whole-corpus-wide-then-generate` does.
  A RAPTOR tree reads as more comprehensive to a judge but is not measurably more correct yet.
  Do not use the graph rung for corpus-wide synthesis.

### Phase 44: do the shipped routers beat always using one search? (2026-09-29)

- **Question.** `weft ask` can route each question to a rung. Does the model-driven `route`, or
  `route-by-score`, answer better than `route-fixed`, which always picks
  `retrieve-then-generate`?
- **Data.** The 107 English questions over the 16 `validation-en` papers, one repetition per
  router, `gpt-5.6-luna` answering and judging, `text-embedding-3-large`. About $0.65.
- **Result.** Neither clears the pre-registered +0.03 margin; both are `benefit-ruled-out`.
  `route` −0.000 `answer_correctness` (95% interval −0.026 to +0.024), `route-by-score` +0.012
  (−0.008 to +0.030), with `route-fixed` at 0.670. Both lose a little `token_recall`, and `route`
  more than doubles the p95 latency (21.8 s against 9.1 s). `route` sent 64 of the 107 questions
  to `raptor-and-leaves-rrf` on an index with no RAPTOR tree, so those answers came from its leaf
  search alone. One question it routed to `corrective-retrieve`, which kept three passages, so its
  @5 retrieval metrics are undefined; `answer_correctness` excludes none. Source:
  `eval/experiments/route-shipped-en/table.md`.
- **Re-run after rungs with nothing to read were withheld (2026-10-01).** The router now offers a
  rung only when the index holds what it reads, and `route` was run again against `route-fixed`
  over the same 107 questions, one repetition each, same models, about $0.65 at most. It sent none
  of them to a RAPTOR, graph or questions rung, and `answer_correctness` moved to +0.022 (95%
  interval −0.001 to +0.046, `inconclusive` against the +0.03 margin, `route-fixed` at 0.661).
  `token_recall` +0.012 (−0.006 to +0.029). p50 latency was 9.0 s against 3.0 s, p95 22.8 s against
  8.2 s. One repetition of each is a single sample: it does not show `route` helps, and it does not
  rule it out. Source: `eval/experiments/route-shipped-en-r44-13/table.md`; the document it ran
  from is `as-run.toml` beside it, because its digest depends on where it ran.
- **What it means for you.** Keep `route-fixed`, the default. Choosing among the shipped rungs by
  a model's reading of the question does not answer these questions better and costs a second
  model call and latency.

### Phase 44: at what corpus size does reading everything stop paying off? (2026-09-29)

- **Question.** `whole-corpus-wide-then-generate` sends the model every leaf of the corpus.
  Where, as a corpus grows, does that stop beating one search? The answer is the first routing
  rule's threshold.
- **Data.** Nested subsets of `validation-en` — 4, 8 and 16 papers, chosen by seed — each keeping
  only the questions whose every cited paper is inside: 23, 50 and 107 questions. The 16-paper
  point is `whole-corpus-en` (two repetitions); the two subsets ran one repetition each for $2.22.
- **Result.** No such size within this corpus. Reading everything holds at about 0.75
  `answer_correctness` at every size (0.756, 0.758, 0.743), while one search falls as the corpus
  grows (0.736, 0.722, 0.672). The paired gain grows with it: +0.020 (95% interval −0.032 to
  +0.077) at 4 papers, +0.036 (−0.012 to +0.089) at 8, +0.075 (+0.039 to +0.117) at 16 — the
  first two inconclusive on 23 and 50 questions. Sources:
  `eval/experiments/whole-corpus-size-25/table.md`, `-50/table.md`,
  `eval/experiments/whole-corpus-en/table.md`.
- **What it means for you.** While the whole corpus fits the generate role's `context_tokens`,
  reading it is at least as good as one search here, and better as the corpus grows. What limits
  it is context and cost — about 260,000 prompt tokens, $0.054, per question at 16 papers —
  not answer quality. Declaring `context_tokens` on the generate role is what lets the router
  test `corpus.fits_context`. A rung whose answer is written under another role is tested with
  `corpus.fits_context.<role>`, that role's own `context_tokens`; a role that declares none has
  no such feature, so no rule about it matches.

### Phase 44: does reading more of a long document help, when the document is always found? (2026-09-29)

- **Question.** E3 left open whether reading more around the hits failed on QASPER only because
  search missed the passage. QuALITY asks four-option questions of long stories and articles,
  one document each, in a corpus small enough that search always finds it.
- **Data.** QuALITY v1.0.1 dev, 20 articles sampled by seed, 365 questions, the same three arms,
  one repetition. $1.11. The questions carry no stated licence and stay untracked
  (`corpus/quality.toml`).
- **Result.** Neither arm clears the +0.05 margin; both are `benefit-ruled-out`.
  `adjacent-chunks` +0.013 (95% interval −0.011 to +0.040), `context-construction` +0.022
  (−0.003 to +0.048), over 365 paired questions, with one search at 0.538 and recall@5 at 0.986.
  Source: `eval/experiments/quality-long-document/table.md`.
- **What it means for you.** With the right document found almost every time, handing the model
  more of it still adds under +0.05. Keep `retrieve-then-generate` for questions about one long
  document.

### Phase 44: does reading more of a long document help? (2026-09-29)

- **Question.** When a question is about one long paper, does giving the model more of the paper
  — each hit's neighbouring chunks, or a context assembled around the hits — answer it better
  than the chunks one search returns?
- **Data.** QASPER dev, 910 answerable questions over 281 NLP papers (median about 21,500
  characters). Three arms, one repetition each, `gpt-5.6-luna` answering and judging,
  `text-embedding-3-large` embedding. $3.43 for the three arms, plus about $1.20 on a first
  `context-construction` run the judge lost (repair R44.12).
- **Result.** Neither clears the pre-registered margin of +0.05 `answer_correctness`; both are
  `benefit-ruled-out`. `adjacent-chunks` +0.008 (95% interval −0.002 to +0.018) over 905 paired
  questions, `context-construction` +0.003 (−0.008 to +0.013), each at about two and a half
  times the generation tokens. Every arm scores low here (0.232 for one search): the answers are
  short spans or yes/no, and one search finds a supporting passage for under half the questions
  (recall@5 0.456). Source: `eval/experiments/qasper-long-document/table.md`.
- **What it means for you.** Reading more around the hits does not help on these papers; the
  miss is in finding the right passage. Keep `retrieve-then-generate`. Per-question choice could
  reach +0.060 (`eval/replay/README.md`), again from one repetition.

### Phase 44: does anything answer multi-hop questions better than one search? (2026-09-29)

- **Question.** Questions whose answer chains two to four facts from different passages
  (MuSiQue) are where a single search should fall short. Does searching again, searching more
  ways, or searching more widely answer them better than `retrieve-then-generate`?
- **Data.** MuSiQue-Ans dev, 600 questions: 200 each of two, three and four hops, over the 4,084
  paragraphs they draw on. Five arms, one repetition each, `gpt-5.6-luna` answering and judging,
  `text-embedding-3-large` embedding. $3.51 for the five arms, plus $0.72 spent on the first,
  failed iterative run.
- **Result.** Nothing clears the pre-registered margin of +0.05 `answer_correctness`, so every
  arm is `benefit-ruled-out`. `iterative-retrieve` is the only one ahead: +0.018 (95% interval
  +0.002 to +0.034) over 597 paired questions, at about four times the grading tokens and
  twice the median latency. `hybrid`, `multi-query` and `broad-and-refined` are indistinguishable
  from one search. Retrieval itself holds up (recall@5 0.748 for one search) and falls with hop
  count; the loss is in chaining what was found. Source:
  `eval/experiments/musique-retrieval/table.md`.
- **Correction on the way.** The first run of `iterative-retrieve` failed 263 of its 600
  questions — every question it actually iterated on — because the document inherited a fuser
  that refuses more than one ranked list. Its mean over the 334 survivors (0.649) looked like a
  large win and was not: one search scores 0.656 on those same questions. The document now fuses
  its rounds (repair R44.10), and a judged metric now counts a failed question as excluded
  (repair R44.11), so a survivor mean can no longer pass for a whole-set one.
- **What it means for you.** Keep `retrieve-then-generate` for multi-hop questions. Per-question
  choice among these five could reach +0.097 in principle (`eval/replay/README.md`), but with one
  repetition that ceiling cannot be told apart from judge noise.

### Phase 44: can a question's wording tell which kind of question it is? (2026-09-28)

- **Question.** A routing rule could send a multi-hop or yes/no question somewhere special only
  if something about the question reliably says it is one. Do the query profile's word cues
  (comparison, aggregation, temporal, cross-document, global) say so?
- **Data.** MuSiQue-Ans dev, 300 multi-hop questions and 300 single-hop controls, and QASPER
  dev, 910 answerable questions labelled by answer type. Each set is split by source document.
  No model was called.
- **Result.** No cue is reliable enough to route on. A cue counts only when the 95% lower bound
  of its precision reaches 0.80 on both splits. The closest is the temporal cue as a sign of a
  multi-hop question: 0.909 precision on train and 1.000 held-out, with lower bounds of 0.722
  and 0.796, firing on about one question in ten. The cross-document cue never fires on MuSiQue,
  whose multi-hop questions compose facts without saying so. Source:
  `eval/profile-validity/README.md`, generated by `scripts/profile_validity.py`.
- **What it means for you.** Routing stays corpus-level for now. The cues are recorded on every
  routed ask and every eval record, so a better cue can be measured without re-running
  anything.

### Phase 44: could choosing a rung per question beat the best single rung? (2026-09-28)

- **Question.** Before paying for routing experiments: in the experiments already on record, would
  choosing the best arm for each question beat always using the best arm, by more than judge
  noise alone does?
- **Data.** Every committed experiment with at least two arms and a complete run, replayed with
  `weft eval replay` on its first declared metric. No model was called and nothing was spent.
  Arms that read gold labels at query time are left out, since no router could choose them.
- **Result.** For per-question choice, the oracle is the ceiling and the self-oracle is what the
  best arm's two repetitions reach alone. ESCI's cross-encoder experiments show headroom where the
  self-oracle is zero, because both rankings are deterministic: **+0.063** mrr@5
  (+0.051 to +0.076) with MiniLM and +0.052 (+0.041 to +0.063) with BGE. TechQA's are +0.044 and
  +0.039, with no repeated arm to measure noise. `whole-corpus-en` shows none beyond noise: the
  oracle's +0.036 answer correctness equals the self-oracle's +0.036. Dense, lexical and hybrid
  on Open RAGBench differ by at most +0.001 recall@5. Source: `eval/replay/README.md`, generated
  by `scripts/replay_all.py`.
- **What it means for you.** Nothing changes yet. Per-question routing is worth measuring
  between rerankers, not between retrieval backends, and an oracle is an upper bound a real router
  only approaches.

### Phase 43: asking while indexing (2026-09-22)

- **Question.** How soon after `weft index` starts can you ask about what it is reading, and does
  asking slow down while it runs?
- **Data.** 100 arXiv PDFs from Open RAGBench (243 MB), through `index-openai-large-pdf`
  (`text-embedding-3-large`), default batch 25. Five runs on pgvector and one on Qdrant, each from
  the `weft-rag 2.10.0` wheel on one Apple Silicon laptop (12 cores, 24 GB) into a fresh
  database, with `weft ask` running every 5 s in a second shell. About $2 in total.
- **Result.** The first batch, 25 of the 100, is queryable at **30.0 s** (median; 29.8–31.0),
  and an answer citing the paper that holds it arrives at **34.2 s**: the harness checks the
  paper's file and a citation marker in the output, not whether the answer is correct. The base
  index is complete, all 100 queryable, at **127.2 s** (126.4–127.8). No enrichment layer ran, so
  none was timed. Before this phase the same run returned nothing until **226.8 s**. `weft ask`
  p95 is 3.87 s during indexing against 3.65 s after, a ratio of 0.93–1.11 across runs. A question
  about a document not yet reached is told so rather than answered from the rest; no run recorded
  it answered after its batch landed. Qdrant (one run): 25.4 s, 27.2 s and 107.8 s. Source:
  `eval/fast-ingest/table.md`, from `exit-a-summary.jsonl`.
- **What it means for you.** Point `weft index` at a folder and start asking at once. The answer
  footer says how many documents are not yet indexed, so a missing answer can be told apart from
  a missing document.

### Phase 38: what reading the raw PDFs costs (2026-09-21)

- **Question.** Every Open RAGBench result above was measured on the dataset's own clean markdown.
  A user indexes the PDFs. How much retrieval does Weft lose by parsing them itself with
  `pdf-text`, the *parser tax*?
- **Data.** Open RAGBench dev, 1,548 questions. The same corpus twice: the dataset's markdown
  (1,000 documents) and the raw arXiv PDFs (997; three that `pdf-text` refuses are excluded by
  name, and no dev question rests on them). Both indexed with `text-embedding-3-small`, identical
  chunking; the extractor is the only difference. About $1.12 in embeddings.
- **Result.** Dense retrieval pays **no measurable tax**: recall@5 0.982 on markdown and 0.984 on
  PDFs, a paired difference of +0.003 [−0.005, +0.010]; mrr@5 −0.002 [−0.012, +0.008]. Lexical
  search does pay: recall@5 falls from 0.245 to 0.209, **−0.037 [−0.056, −0.017]**. The text is
  where it goes: 1,200 of 1,548 quotes sit whole in one stored PDF chunk, against 1,511 for the
  markdown. Both repetitions agree. Source: `eval/parser-tax/table.md`, from the records in
  `eval/experiments/orb-parser-tax-*/`.
- **What it means for you.** With a real embedder, `index-pdf-text` retrieves as well as clean text
  on this corpus. Keyword search on PDFs loses about a sixth of its hits; a better extractor is
  where that would come back, and none has been compared yet.

### Phase 41: a cross-encoder reranker over dense's own top 50 (2026-09-20)

- **Question.** Dense leaves room: a perfect reordering of its own top 50 would add 0.147 mrr@5 on
  ESCI and 0.260 on TechQA. Does a cross-encoder, the technique the literature recommends for
  exactly this, collect any of it?
- **Data.** The same frozen pools as Phase 40, replayed: ESCI 830 questions, TechQA 610, exploratory
  on reused benchmarks. Two models served locally by Text Embeddings Inference at $0:
  `BAAI/bge-reranker-v2-m3` (568M parameters, the adoption candidate) and
  `cross-encoder/ms-marco-MiniLM-L6-v2` (22M, exploratory). Each arm ran twice.
- **Result.** On ESCI, bge gained **+0.030 [+0.011, +0.049]**: above zero, but its upper bound falls
  under the 0.05 that counts as worthwhile, so the protocol reads *benefit ruled out*. MiniLM gained
  +0.014 [−0.006, +0.034]. On TechQA both **harmed** retrieval on every slice: bge −0.104
  [−0.132, −0.077], MiniLM −0.107 [−0.134, −0.080]. Both models were deterministic across their two
  repetitions, and no question was excluded. Source:
  `eval/pool-promotion/esci-ce-verdict.json` and `techqa-ce-verdict.json`.
- **Is the harness at fault?** No. A control that puts every relevant chunk first, replayed through
  the identical machinery, scored exactly dense's mrr@5 plus the full oracle ceiling
  (0.985542 against a predicted 0.985542; `eval/pool-promotion/instrument/`). The instrument can
  show the whole gain; these models do not deliver it.
- **An LLM reranker beat both cross-encoders, and cost money to do it.** The same frozen pool put to
  `llm-rerank` with `gpt-5.6-luna` gained **+0.058 mrr@5 [+0.043, +0.074]** on ESCI's 830 questions,
  **0 excluded**, moving 157 of them; `ndcg@10` gained +0.075 [+0.065, +0.086]. That is roughly
  twice bge's +0.030, and the protocol reads it *worthwhile* — with two qualifications that are part
  of the result: every slice is flagged **underpowered** (declared MDE 0.064 against an observed
  0.058, and the interval straddles the 0.05 bar), and the 830 ran **once**, so no stability check
  was possible. Three repetitions at n=100 read 0.918 / 0.921 / 0.931 against a dense control of
  0.883. It cost ~$1.83 for the 830 against the cross-encoders' $0. Source: `m/llm-verdict.json`,
  ledger `41.4`.
- **The local 7B's failure was ours, not the model's** — and this correction is the phase's most
  expensive lesson. `qwen2.5:7b-instruct` first excluded **823 of 830 questions**, which was written
  up here as the model being unable to enumerate a fifty-item list. It was not. `llm-rerank`'s
  prompt asked the model to *"judge every passage exactly once"* and **never said how many passages
  there were**; the model read that as a selection task and returned the handful it judged relevant,
  which the plugin correctly refuses as a partial set. Measured over the same pool: the old wording
  returns a complete judgement set for 3 of 15 questions, the counted wording for 13 of 15. Repaired
  at `R41.6`. **It still is not a usable arm, and now for a different reason.** Re-measured at n=100
  on the fixed build: **84 questions scored, 16 excluded** — 11 unparseable answers and 5 partial
  sets — so the fix moved the failure rather than removing it, and a run with exclusions is read as
  invalid, never as a null. Where it does answer it reranks **worse than not reranking**: mrr@5
  0.845 over its 84 against dense's 0.883 over 100. If you want local reranking, use
  `cross-encoder-rerank`; if you want LLM reranking, the measurement above used a frontier model. Two earlier causes were
  published before this one and were both wrong — the client's loop-breaker (real, fixed at `R41.4`,
  and not this) and the unimplemented native structured-output tier (real, filed as `R41.5`, and not
  this). **If an LLM reranker refuses your pool, read the prompt before blaming the model.**
- **Changed.** `cross-encoder-rerank` ships opt-in, with its measurement in the catalogue. No
  default moved, and the planned adoption reading on untouched data was declined by the rule
  written before the run.

### Phase 40: promoting passages that contain the question's identifiers (2026-09-19)

- **Question.** Among dense's own top 50 chunks, does moving up the ones that literally contain the
  question's identifiers (a model number, an error code) put the right answer higher?
- **Data.** ESCI product search, 830 questions (primary), and IBM TechQA support questions, 610
  (confirmatory). Both are exploratory on reused benchmarks, with one frozen 50-chunk dense pool
  per corpus. Hand-labelled anchors served as the control.
- **Result.** On ESCI, mrr@5 moved +0.006 [−0.001, +0.014], *benefit ruled out*. On TechQA it moved
  −0.027 [−0.049, −0.006], *harm*. On ESCI questions an identifier truly decides it gained +0.026
  [+0.007, +0.048]. Hand-labelled anchors did no better. Source:
  `eval/pool-promotion/esci-verdict.json` and `techqa-verdict.json`, `slices.all`.
- **Changed.** `anchor-promote` ships opt-in, not as a default. A perfect reorder of the same pools
  would gain 0.147 on ESCI and 0.260 on TechQA (`eval/pool-promotion/*-ceilings.json`), which is
  what opened Phase 41.

### Phase 39: searching only a question's identifiers (2026-09-18)

- **Question.** Can a lexical search over just the identifier-shaped words ("anchors") repair the
  weak lexical arm?
- **Data.** 240 RFC questions, then the ESCI and TechQA held-out splits.
- **Result.** It did not beat dense: TechQA −0.008 [−0.021, +0.005] and ESCI +0.001
  [−0.015, +0.018]. These numbers are in the build ledger only. The experiment documents are
  committed (`eval/experiments/rfc-*.toml`, `esci-anchors-*.toml`, `techqa-anchors-*.toml`,
  `*-bm25.toml`), but their run records are not.
- **Changed.** `intent-and-anchors` stays a plugin and is not a default.

### Phase 32: what the model reads, deduplication, MMR and neighbouring chunks (2026-09-18)

- **Question.** Does removing near-duplicates, diversifying (MMR), or widening each hit with its
  neighbours improve what the model reads?
- **Data.** Weft's own English corpus with 54 fetch and 53 operator questions, sized to detect 0.08.
  Separately, 12 Polish questions, too few to detect anything under 0.24.
- **Result.** The full composition raised token recall by +0.038 [+0.017, +0.059] on the fetch
  set and +0.050 [+0.027, +0.076] on the operator set, and neighbour-widening alone by +0.042 and
  +0.031, all below the 0.08 set beforehand and for about twice the prompt tokens (`eval/experiments/context-construction-en-*-widen/table.md`). Deduplication
  changed nothing: the corpus has no repeated passages. MMR lifted mrr@5 by +0.041
  [+0.013, +0.072] on the operator set only, and left the fetch and Polish sets unchanged
  (`eval/experiments/context-construction-*-ir/table.md`). Polish measured nothing
  (`eval/experiments/context-construction-pl-*/table.md`).
- **Changed.** Four opt-in rungs; no default moved.

### Phase 38: dense, lexical and hybrid, then HyDE and hypothetical questions (2026-09-17)

- **Question.** Which first stage retrieves best with a real embedder? Do HyDE (at query time) or
  hypothetical questions (at index time) improve it?
- **Data.** Open RAGBench: 1,000 arXiv papers and 1,548 of the benchmark's own questions. Then a
  300-question subset over 160 papers.
- **Result.** Dense was best (recall@5 0.986). Hybrid came in below it, mrr@5 −0.021
  [−0.028, −0.014], and lexical alone reached recall@5 0.244
  (`eval/experiments/orb-retrieval-baseline/table.md`). On the subset, plain dense already scored
  recall@5 0.997, so there was nothing left to gain. HyDE moved mrr@5 −0.005 [−0.015, +0.003] at
  about 14 times the latency (`eval/experiments/orb-hyde-questions/table.md`). A follow-up with
  English stemming lifted lexical recall to 0.681; that figure is in the ledger only, because
  `orb-retrieval-english.toml`'s records are not committed.
- **Changed.** Dense stays the default. HyDE and hypothetical questions stay opt-in. The lexical
  config stays language-neutral (`simple`) so Polish pipelines work.

### Phase 21: lexical backend and fuser, and rank normalisation (2026-09-13)

- **Question.** Does real BM25 beat Postgres full-text search, does the fuser matter, and which
  rank normalisation is best?
- **Data.** Weft's 25-document corpus and 83 questions. **The dense arm used the `hash` embedder**,
  so it carried no meaning.
- **Result.** BM25 with normalised-score fusion reached recall@5 0.833 against 0.321 for the shipped
  pair (`eval/lexical-fusion/measurement.json`). Rank normalisation changed nothing
  (`eval/text-normalization/measurement.json`).
- **Changed.** No default moved. The record itself refuses to move one until the test is re-run
  with a real embedder.

### Phases 10 and 16a: RAPTOR against leaves only (2026-09-07, re-taken 2026-09-12)

- **Question.** Does a RAPTOR summary tree retrieve better than plain chunks?
- **Data.** 10 PDFs and 66 answerable questions. All but 4 of those questions have a
  single-document answer, so **this is not RAPTOR's intended regime.**
- **Result.** The first reading, +0.018 MAP (`eval/raptor-baseline/measurement.json`), was
  withdrawn: repeating the same configuration spread by 0.021 (`eval/raptor-baseline/remeasurements/`).
  The exit found no gain on any metric (`eval/raptor-baseline/exit/exit-measurement.json`). Re-taken
  with per-question scores, one-level RAPTOR was null and the deep tree lost MAP −0.023
  [−0.047, −0.005] (`eval/raptor-baseline/after-16a/remeasurement.json`).
- **Changed.** RAPTOR stays opt-in. §2's long-document test is what would settle it.

### Phases 4 and 6: the published baseline (2026-08-20, re-taken 2026-08-25)

- **Question.** Is there a baseline a stranger can reproduce from a release, without the
  repository?
- **Data.** 9 Polish Wikipedia documents and 12 Polish questions, with the offline `hash` embedder.
- **Result.** Document recall@5 0.417 and mrr@5 0.25, identical to the last decimal across
  installs (`eval/baselines/`). It measures reproducibility, not retrieval quality.
- **Changed.** `weft eval compare` against the published baseline became a check anyone can run
  (`docs/REPRODUCING.md`).

---

## 5. The question sets

| set | questions | language | author | shape |
|---|---|---|---|---|
| `eval/questions/fetch.toml` | 54 | English | an LLM, checked by a second | 50 single-document, 4 cross-document |
| `eval/questions/operator.toml` | 53 | English | same | 47 single-document, 6 cross-document |
| `eval/questions/polish.toml` | 12 | Polish | same | 9 single-document, 3 cross-document |
| `eval/questions/unanswerable.toml` | 17 | English and Polish | same | no answer in the corpus |
| Open RAGBench dev | 1,548 | English | the benchmark's own | single-document |
| RFC questions | 240 | English | six writers | single-document |
| TechQA | 610 | English | IBM's benchmark | single-document |
| ESCI | 830 | English | Amazon's benchmark | product search; any relevant product answers |

No set is multi-hop by design, and none asks corpus-wide questions. The 13 cross-document
questions are too few to slice, and no measurement has sliced by them.
