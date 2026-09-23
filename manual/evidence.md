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
  - `context-construction-then-generate`: token recall +0.030 to +0.035, for about twice the
    prompt tokens.
  - `adjacent-chunks-then-generate`: +0.032 on one English set.
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
- **Multi-hop and corpus-wide questions: no evidence either way.** RAPTOR and the graph rungs exist
  for questions that need several documents, or a view of the whole corpus. Every question set
  Weft has measured on asks single-document questions. Nothing on this page tells you whether
  `index-with-raptor` or `graph-then-generate` helps on the questions they were built for (see §2).
- **Most shipped settings are unmeasured defaults**, not tuned values: chunk size 512 with overlap
  50, `top_k` 20, `top_n` 8, the packer's `reverse` order, the router, and RRF's k 60 and 0.8 text
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
- *never*: never measured.

| rung | status | evidence |
|---|---|---|
| `retrieve-then-generate` | helps (best first stage) | `eval/experiments/orb-retrieval-baseline/table.md` |
| `hybrid-then-generate`, `lexical-retrieve` | harms | same table: hybrid mrr@5 −0.021, lexical recall@5 0.244 against 0.986 |
| `hybrid-normalized-scores` | wrong questions (measured with the `hash` embedder) | `eval/lexical-fusion/measurement.json` |
| `anchor-promote-retrieve`, `anchor-promote-then-generate` | harms on TechQA, no gain on ESCI | `eval/pool-promotion/` (§4, Phase 40) |
| `intent-and-anchors-then-generate` | no gain | Phase 39 (ledger only, records not committed) |
| `dedupe-then-generate` | no gain | `eval/experiments/context-construction-en-fetch-ir/table.md` |
| `mmr-then-generate` | helps on one set of three | `eval/experiments/context-construction-en-operator-ir/table.md` |
| `adjacent-chunks-then-generate`, `context-construction-then-generate` | helps, below the pre-set margin | `eval/experiments/context-construction-en-*-widen/table.md` |
| `hyde-then-retrieve`, `index-with-questions` | no gain (the data had no headroom) | `eval/experiments/orb-hyde-questions/table.md` |
| `index-with-raptor`, `raptor-and-leaves-rrf` | wrong questions | `eval/raptor-baseline/` |
| `index-with-deep-raptor` | wrong questions, and harms on them | `eval/raptor-baseline/after-16a/remeasurement.json` |
| `graph-then-generate`, `graph-and-vector-rrf`, `index-with-facts`, `index-with-facts-openai`, `index-with-cooccurrence` | wrong questions (12 one-sentence documents, questions generated from the graph under test) | Phase 11 exit (ledger only) |
| `cross-encoder-retrieve`, `cross-encoder-rerank-then-generate` | no gain on ESCI, harms on TechQA | `eval/pool-promotion/esci-ce-verdict.json`, `techqa-ce-verdict.json` |
| `replay-llm-rerank` | helps on ESCI at ~$1.83/830 questions, underpowered, one repetition | ledger `41.4` |
| `graph-2hop-then-generate`, `graph-then-rerank`, `rerank-then-generate`, `iterative-retrieve`, `corrective-retrieve`, `grade-then-generate`, `multi-query-then-retrieve`, `step-back-then-retrieve`, `rewrite-then-retrieve`, `boolean-then-retrieve`, `broad-and-refined-rrf`, `contradiction-aware`, `draft-then-refine`, `summarise-then-generate`, `no-retrieval`, `route`, `route-by-score`, `route-fixed`, `enrich-with-questions`, `enrich-with-raptor`, `enrich-with-facts-and-graph`, `questions-then-generate`, `index-with-adrap`, `index-with-graph`, `index-with-keywords` | never | none |
| `index-text` | helps (the leaves arm RAPTOR is measured against) | `eval/raptor-baseline/after-16a/remeasurement.json` |
| `index-pdf-text` | no dense cost against clean markdown; lexical recall@5 −0.037 | `eval/parser-tax/table.md` |
| `index-pdf`, `index-pdf-described`, `index-pdf-learned`, `index-pdf-rows`, `index-pdf-undescribed`, `index-messy-text`, `index-polish`, `index-openai*`, `index-qdrant` | never, as a comparison | none |
| `preview-plain`, `preview-markdown`, `baseline` | no retrieval claim to test | — |

---

## 4. The measurements, newest first

### Phase 43: asking while indexing (2026-09-22)

- **Question.** How soon after `weft index` starts can you ask about what it is reading, and does
  asking slow down while it runs?
- **Data.** 100 arXiv PDFs from Open RAGBench (243 MB), through `index-openai-large-pdf`
  (`text-embedding-3-large`), default batch 25. Five runs on pgvector and one on Qdrant, each from
  the built wheel into a fresh database, with `weft ask` running every 5 s in a second shell.
  About $2 in total.
- **Result.** The first document is queryable at **30.0 s** (median; 29.8–31.0), and a correct,
  cited answer about it arrives at **34.2 s**. All 100 are queryable at **127.2 s** (126.4–127.8).
  Before this phase the same run returned nothing until **226.8 s**. `weft ask` p95 is 3.87 s
  during indexing against 3.65 s after, a ratio of 0.93–1.11 across runs. A question about a
  document not yet reached is told so rather than answered from the rest. Qdrant (one run): 25.4 s,
  27.2 s and 107.8 s. Source: `eval/fast-ingest/table.md`, from `exit-a-summary.jsonl`.
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
- **Result.** Neighbour-widening and the full composition raised token recall by +0.035
  [+0.013, +0.061] and +0.030 [+0.004, +0.058], below the 0.08 set beforehand and for about twice
  the prompt tokens (`eval/experiments/context-construction-en-*-widen/table.md`). Deduplication
  changed nothing: the corpus has no repeated passages. MMR lifted mrr@5 by +0.041
  [+0.013, +0.075] on the operator set only, and left the fetch and Polish sets unchanged
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
