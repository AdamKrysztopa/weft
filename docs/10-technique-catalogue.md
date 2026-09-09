# 10 — Technique catalogue and plugin naming

**Reference.** This file owns **the provenance of every technique Weft ships**: where the idea comes
from in the literature, whether its common name was earned by a paper or coined by tooling, and the
canonical plugin name that follows.

> **The rule that keeps this file honest.** A plugin name is a **published surface**. Third parties
> write it in configuration files, and Weft's own failure path prints it back to them (`02` §2 —
> *"every unresolvable plugin name carries its reason"*). So a name is a claim, and a name borrowed
> from a paper is a claim about what the code does. This document exists to make sure every one of
> those claims is either true or knowingly withdrawn **before** the name is published.
>
> The corollary, and it is the reason the *Unconfirmed* column is not decoration: **a catalogue that
> gives every row a confident citation is a catalogue nobody should trust.** Four of the rows below
> have no paper behind their common name at all. Saying so is the finding.

**What this file does not own.** It states no contract — `02` §1 owns the `Strategy` and `Retriever`
protocols and every signature. It states no phase, requirement or exit criterion — `01` owns those. It
holds no task state — `build-ledger.md` owns that, and §3 below points at its lines rather than
duplicating them.

**Weft copies no source text from anywhere.** Everything below traces *ideas*
to their published origin, which is the opposite operation: a technique from a paper belongs to the
literature, not to any codebase, and naming it after the literature is what lets a third party know
whether their pack duplicates one of ours.

---

## How to read a row

| Column | Means |
|---|---|
| **Weft name** | The recommended registry name. Bare, lowercase, kebab-case — see §2 |
| **What it does** | One line. If it needs two, the row is a composition and belongs in a pipeline, not a plugin |
| **Origin** | The paper that **introduced** the technique, cited in full. Where a different work **named** or **popularised** it, both are given, because they are different facts |
| **Name provenance** | Whether the *common name* comes from literature, from tooling, or from nowhere. **This column decides whether a rename is a correction or a preference** |

**Name provenance values.**

- **Literature** — a paper introduced the technique *and* named it. The name carries authority; keep it.
- **Taxonomy** — a survey or textbook coined the label to organise work that had no agreed name. The
  technique is real; the label has no more authority than its usefulness.
- **Framework-coined** — the label comes from LangChain / LlamaIndex / LangGraph documentation or a
  blog post, not from a paper. **A rename here is a correction, not a preference.**
- **Ad hoc** — the label exists with no paper or framework behind it, coined for one implementation
  and nowhere else. It carries no authority whatsoever.
- **False** — the name claims a paper or library that does not contain the thing. Renaming is mandatory.

---

## 1. The catalogue

### 1.1 Query-path techniques

Every row here is Phase 2 work. `01` → Phase 2 owns the phase; this table owns what each name means.

| Weft name | What it does | Origin | Name provenance |
|---|---|---|---|
| **`no-retrieval`** | Answers from the model's parametric memory; retrieves nothing and returns an empty source list by design. This is the only path that skips citation binding and the post-generation guardrails — that must be a *stated* property of the plugin, not an accidental consequence of which helper it calls | The *setting* was named by Adam Roberts, Colin Raffel, Noam Shazeer, *How Much Knowledge Can You Pack Into the Parameters of a Language Model?*, EMNLP 2020, arXiv:2002.08910 — "closed-book QA". The *name* is Adaptive-RAG's label for this branch, written **"No Retrieval"** (§A.2, and the Types column of its results tables): Soyeong Jeong, Jinheon Baek, Sukmin Cho, Sung Ju Hwang, Jong C. Park, *Adaptive-RAG*, NAACL 2024, arXiv:2403.14403. **The technique itself needs no citation — it is the null case** | Ad hoc (`direct`). Not found in LlamaIndex, LangChain or Haystack documentation as a routing mode or component name — see §5 |
| **`retrieve-then-generate`** | Retrieves once for the user's question and answers from that context, with citations. Caveat: an implementation that wraps this loop in query rewriting, hybrid retrieval, reranking and bounded regeneration is no longer a single-pass baseline in cost — floor of several LLM calls, ceiling unbounded without an explicit cap — and must not be named as though it were "simple" | Danqi Chen, Adam Fisch, Jason Weston, Antoine Bordes, *Reading Wikipedia to Answer Open-Domain Questions*, ACL 2017, pp. 1870-1879, arXiv:1704.00051 — the retriever→reader split this actually implements. The three letters and the trained formulation are Patrick Lewis et al., *Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks*, NeurIPS 2020, arXiv:2005.11401 | Taxonomy — "naive RAG" is a **retronym** from Yunfan Gao et al., *Retrieval-Augmented Generation for Large Language Models: A Survey*, arXiv:2312.10997, an **unrefereed preprint marked "Ongoing Work"**. No paper used the term before Dec 2023 |
| **`contextual-query-rewrite`** | Rewrites a follow-up question into a standalone retrieval query using the conversation history. Caveat: if this runs unconditionally inside every other strategy rather than as its own nameable, disableable stage, it becomes a technique with no name at all — the same defect as a technique with the wrong name | No single origin traced; conversational query rewriting has its own literature which **this catalogue has not searched** — see §5 | **Unconfirmed** |
| **`hyde`** | Generates a hypothetical answer document and retrieves against *that* instead of the question. HyDE's own formulation averages the embeddings of several generated documents together with the original query's embedding, and is a claim about *dense* retrieval only — feeding the hallucinated passage to lexical search or using it as a reranker query is outside what the technique was validated for. A single hypothetical document with no fallback means a bad generation directly becomes the query | Luyu Gao, Xueguang Ma, Jimmy Lin, Jamie Callan, *Precise Zero-Shot Dense Retrieval without Relevance Labels*, ACL 2023, pp. 1762-1777, arXiv:2212.10496 | **Literature** — the authors coin "HyDE" in their own abstract. Keep the acronym; it is what a practitioner will search for |
| **`repack`** *(method: `sides` \| `forward` \| `reverse`)* | Reorders the ranked node list before it enters the prompt, to exploit position effects in long contexts. Caveat: a "sides" packing that puts the second-best-ranked item at the very end of the list rather than immediately following the best is a common inversion bug — check the emitted ordering against the definition, not just the docstring. If only one method ships, it should be `reverse`, which Wang et al.'s own results (Table 11, Avg column) select as best, at 0.483 — not `sides` | The effect: Nelson F. Liu, Kevin Lin, John Hewitt, Ashwin Paranjape, Michele Bevilacqua, Fabio Petroni, Percy Liang, *Lost in the Middle: How Language Models Use Long Contexts*, TACL vol. 12, pp. 157-173, 2024, arXiv:2307.03172. The operation and its three method names: Xiaohua Wang et al. (14 authors), *Searching for Best Practices in Retrieval-Augmented Generation*, EMNLP 2024, arXiv:2407.01219 §3.6 | **Literature** for `repack` and the three method values. LlamaIndex's `LongContextReorder` is the framework label and names the *problem*, not the operation — do not adopt it |
| **`postqfrap`** *(cluster_size, similarity_threshold, max_levels)* | Replaces the retrieved passages with **one** query-focused summary built over them: cluster the hits, summarise each cluster against the question, recurse, then summarise the top layer — so a prompt-sized context is produced by *compressing* a wider retrieval rather than by dropping passages whole. Caveat: the summarising calls are model calls made while somebody waits — twenty passages at `cluster_size: 4` is six before the answer — and they run on the `index` role, **not** `generate`, because concurrent calls on a displayed role interleave in a streamed answer (ledger `10.15`; the general defect is carried repair `R10.1`). A second caveat the paper does not have: clustering above level 1 goes by order rather than similarity, because summaries carry no vectors and requiring an `Embedder` on the query path would make the stage unusable where none is configured | Charbel Chucri, Rami Azouz, Joachim Ott, *Recursive Abstractive Processing for Retrieval in Dynamic Datasets*, 2024, arXiv:2410.01736 §5, Algorithm 3. The **strongest measured result in the four papers this plugin family draws on** (§6.5, Figs. 6–9) — against post-retrieval baselines only, never head-to-head with a persisted tree, which is worth stating | **Literature** — the paper's own name for the technique, per §2.1 rule 3. Taken rather than reserved at ledger `10.15`; §4 records the release |
| **`step-back`** | Abstracts the question into a more general one, retrieves for both, and answers grounded in both contexts. Caveat: keeping the literal and abstract contexts as genuinely separate prompt slots matters — a streaming code path that collapses that separation into one generic cited-context call quietly turns this into plain dual-query retrieval with fusion, a materially weaker technique wearing the same name | Huaixiu Steven Zheng, Swaroop Mishra, Xinyun Chen, Heng-Tze Cheng, Ed H. Chi, Quoc V. Le, Denny Zhou, *Take a Step Back: Evoking Reasoning via Abstraction in Large Language Models*, ICLR 2024 (poster; OpenReview forum `3bq3jsvcQ1`), arXiv:2310.06117 | **Literature** — the paper names the technique in its own title. LangChain's *Query Transformations* post (24 Oct 2023) popularised the RAG framing, but that framing is the paper's own |
| **`multi-query`** | Fans one question into several reformulations and retrieves each independently. Caveats: dropping the original query from the fan-out set loses whatever it alone would retrieve; a generation prompt that asks only for *paraphrases* forbids the two things the expansion literature actually credits — new vocabulary and aspect coverage; and near-duplicate reformulations weaken the downstream fusion, whose benefit comes from rankings that disagree | The idea: Nicholas J. Belkin, Paul Kantor, Edward A. Fox, Joseph A. Shaw, *Combining the evidence of multiple query representations for information retrieval*, Information Processing & Management 31(3), pp. 431-448, 1995. The problem it solves: George W. Furnas, Thomas K. Landauer, Louis M. Gomez, Susan T. Dumais, *The vocabulary problem in human-system communication*, CACM 30(11), pp. 964-971, 1987. LLM-generated expansion: Rolf Jagerman, Honglei Zhuang, Zhen Qin, Xuanhui Wang, Michael Bendersky, *Query Expansion by Prompting Large Language Models*, arXiv:2305.03653, 2023 | **Framework-coined**, but descriptive and aligned with the IR literature's "multiple query representations" — keep it. LangChain's `MultiQueryRetriever` put the exact string into circulation |
| **`reciprocal-rank-fusion`** | Merges several ranked lists into one by summing `1/(k+rank)`. Caveat: this formula is easy to reimplement inconsistently across call sites — one canonical implementation should serve every fusion site, not a copy per code path that can silently grow its own extra weighting behaviour | Gordon V. Cormack, Charles L. A. Clarke, Stefan Büttcher, *Reciprocal rank fusion outperforms condorcet and individual rank learning methods*, SIGIR 2009, pp. 758-759, DOI 10.1145/1571941.1572114. Precursor: Edward A. Fox, Joseph A. Shaw, *Combination of Multiple Searches*, TREC-2, NIST SP 500-215, 1994, p. 243 | **Literature** |
| **`iterative-retrieval`** | Retrieves, asks a critic whether the evidence suffices, generates a new query from what is missing, and answers only once the loop ends. Caveats: forcing a minimum number of loop iterations regardless of what the critic reports contradicts every paper in this technique family, and treating a failed critique call as automatic sufficiency silently downgrades the strategy to single-shot retrieval without saying so | Peng Qi, Xiaowen Lin, Leo Mehr, Zijian Wang, Christopher D. Manning, *Answering Complex Open-domain Questions Through Iterative Query Generation*, EMNLP-IJCNLP 2019, arXiv:1910.07000 | **Taxonomy** — the label is a bucket in Gao et al.'s survey (arXiv:2312.10997 §V-A), not a technique name. It cannot miscite a paper, and it will never tell a user whether generation is interleaved |
| **`corrective`** *(name conditional — see below)* | Grades each retrieved document against the query, discards the failures, and takes a corrective action when the set is judged bad. In the paper's own formulation, the corrective action reaches *outside* the corpus (e.g. web search) and refinement works on fine-grained knowledge strips, not whole documents — a version that only rewrites the query and re-asks the same index has not actually added a corrective action, whatever it is named. A grader that silently falls back to word-overlap scoring when the judging call fails is a silent fallback masquerading as a grade | Shi-Qi Yan, Jia-Chen Gu, Yun Zhu, Zhen-Hua Ling, *Corrective Retrieval Augmented Generation*, arXiv:2401.15884, 2024. **arXiv preprint only** — the authors' own BibTeX still reads `journal={arXiv preprint}` and the record carries no journal-ref. Do not cite it as a conference paper | **Framework-coined as practised.** LangGraph's tutorial reduced the paper to "grade each doc, rewrite the query, add web search" and says so; every downstream implementation inherits that reduction |
| **`contradiction-check`** | Asks whether the retrieved sources agree, and answers with agreement and conflict separated and cited. Caveat: a disagreement detector that reports agreement when the underlying critique call fails is claiming consensus it cannot see — that failure mode should surface as "unknown", not as a positive result | The phenomenon: Rongwu Xu, Zehan Qi, Zhijiang Guo, Cunxiang Wang, Hongru Wang, Yue Zhang, Wei Xu, *Knowledge Conflicts for LLMs: A Survey*, EMNLP 2024, pp. 8541-8565, arXiv:2403.08319 — "inter-context conflict". Closest published analogue: Vignesh Gokul, Srikanth Tenneti, Alwarappan Nakkiran, *Contradiction Detection in RAG Systems*, arXiv:2504.00180, 2025 (parallel framing, not a source) | **Ad hoc** (`rag_consensus`). Not a paper, not a framework — searched LlamaIndex's fusion modes (RECIPROCAL_RANK, RELATIVE_SCORE, DIST_BASED_SCORE, SIMPLE) and LangChain's retrieval docs; nothing named "consensus" |
| **`boolean-retrieval`** | Parses the query into Boolean operands, retrieves each independently, and combines the result sets by set algebra. Caveats for implementers: an `AND` that silently returns the union when the intersection is empty is the logical opposite of what was asked, and indistinguishable to the caller from a correct result — it must fail loudly or return empty instead. A flat operator representation that cannot express a compound query correctly collapses everything to `OR`. And advertising `XOR` as a supported operator without implementing it anywhere is worse than not advertising it | Christopher D. Manning, Prabhakar Raghavan, Hinrich Schütze, *Introduction to Information Retrieval*, Ch. 1 "Boolean retrieval", Cambridge University Press, 2008. Modern evaluation: Chaitanya Malaviya, Peter Shaw, Ming-Wei Chang, Kenton Lee, Kristina Toutanova, *QUEST*, ACL 2023, arXiv:2305.11694; Zongmeng Zhang et al., *BoolQuestions: Does Dense Retrieval Understand Boolean Logic in Language?*, Findings of EMNLP 2024, pp. 2767-2779, arXiv:2411.12235 | **Literature (textbook).** Marked *named* rather than *introduced*: operational Boolean systems predate any single citable paper, and this catalogue deliberately asserts no origin paper for it |
| **`refine-on-uncertainty`** | Retrieves, drafts, and retrieves once more if the draft signals uncertainty. Caveat: detecting uncertainty by matching the draft against a fixed list of hedge phrases is a weak proxy for the technique — the literature's own mechanisms use token probabilities (FLARE) or trained reflection tokens (Self-RAG); a phrase-matching check fires on hedging language rather than genuine unsupportedness, and breaks silently in another language or under a different system prompt | Zhengbao Jiang, Frank F. Xu, Luyu Gao, Zhiqing Sun, Qian Liu, Jane Dwivedi-Yu, Yiming Yang, Jamie Callan, Graham Neubig, *Active Retrieval Augmented Generation*, EMNLP 2023, pp. 7969-7992, arXiv:2305.06983 — the nearest published ancestor | **Framework-coined** (`rag_adaptive`; the "adaptive" / "router" vocabulary comes from LangGraph and LlamaIndex docs, not from the papers whose names it borrows) |
| **`query-scorer`** + **`routing-policy`** *(two plugins)* | An LLM scores the query on named dimensions; a pure function maps those scores to a strategy. Caveats: capturing several typed scoring dimensions and attaching every one to the observability span is worth keeping regardless of how routing is implemented. A routing function built from many unfit if/elif branches risks becoming unable to reach one of its own named strategies at all — verify every strategy the router can name is actually reachable from it. And catching a broad exception list (including bare exceptions) to silently substitute a different routing algorithm is a silent fallback, not error handling | Soyeong Jeong et al., *Adaptive-RAG*, NAACL 2024, arXiv:2403.14403 — the route-by-query-complexity formulation. Related: Alex Mallen, Akari Asai, Victor Zhong, Rajarshi Das, Daniel Khashabi, Hannaneh Hajishirzi, *When Not to Trust Language Models*, ACL 2023, arXiv:2212.10511; Yile Wang, Peng Li, Maosong Sun, Yang Liu, *Self-Knowledge Guided Retrieval Augmentation*, Findings of EMNLP 2023, arXiv:2310.05002 | **Framework-coined** for "router"/"selector". `adaptive-rag` as a *name* is Jeong et al.'s and must be reserved for an implementation that trains a classifier |

**Two conditional names, stated as conditions rather than preferences.**

- **`corrective`** is only honest if the plugin gains a *distinct knowledge action* — a second
  `Retriever` resolved by contract, not the same index re-queried. Absent that, the name is
  `graded-retrieval` and the word `corrective` stays free for a plugin that earns it. This is a
  design decision with a naming consequence.
- **`repack`** may only be registered with a `sides` method once `sides` does what Wang et al. define.
  Shipping the name over a defective ordering would launder the defect through a citation.

### 1.2 Index-path techniques

**Phase 2 work** — `raptor` is ledger task **2.32**, `hypothetical-questions` is **2.31**, and
`cross-encoder-rerank` was named by **2.7**'s reranking row. Listed here because they are techniques
with origins, not because this file owns the phase.

> *(Corrected 2026-08-17, when task **2.7** closed.* **`cross-encoder-rerank` did not ship, and is
> not owed by any open task.** *2.7 shipped `llm-rerank` — a `Reranker` that asks the model an
> operator has already configured, under a role they already map, and therefore adds no dependency.
> A cross-encoder needs a model download, which `09` §4.4's own argument keeps out of the gate, and
> this section already files the technique on the **index path** rather than in 2.7's reranking
> position. The language-aware mapping in the row below —* `sdadas/polish-reranker-roberta-v3` *for
> Polish,* `cross-encoder/ms-marco-MiniLM-L-6-v2` *otherwise — stays here as **seed data for the pack
> that eventually ships it**, plugin-declared as* `by_locale` *configuration and never a table in
> core. Saying so is better than leaving a closed task named beside an unbuilt row, which is the
> shape the correction above this one was written about.)*

> *(Corrected 2026-08-17, scope decision `S2`. This section read **"Phase 1 work"** until then, and
> Phase 1's own ledger never contained a single one of these rows — so from Phase 1's exit until `S2`
> the sentence assigned work to a phase that had ended, which is exactly the property task **1.17**
> made false. The correction is recorded rather than made silently because the gap is the interesting
> part: `tests/docs/test_phase_document_routing.py` did not catch it and was never going to. That
> file declines the general sweep on purpose — its own docstring says so — because a heuristic cannot
> tell a document that **routes** a reader to a dead phase from a docstring that **records** why
> something was built. Both are citations of a closed phase and only one is a defect. So 1.17's
> property is broader than 1.17's test, and this is what fell through the difference.)*

> *(Corrected 2026-08-18, when task **2.31** closed.* **`hypothetical-questions` shipped, under
> exactly the citation this row already names** — `weft_index.hypothetical_questions`, registered
> under `weft_index.contract.Expander`, doc2query (arXiv:1904.08375) rather than HyDE. §3.4 below
> used to propose phantom tasks **1.11** and **1.12** for `raptor` and this row, written before
> scope decision `S2` created **2.31**–**2.33** instead; that proposal was never updated when `S2`
> landed, which is the same "routes to a dead phase" gap task **1.17** and the note above already
> found once in this section. Removed rather than left to mislead the next reader — `raptor` (task
> **2.32**) is still open and still needs a real task line, but not this stale one.)*

> *(Corrected 2026-08-18, when task **2.32** closed.* **`raptor` shipped, under the citation this
> row already names** — `weft_index.raptor`, registered under `weft_index.contract.Expander`
> beside `hypothetical-questions`, Sarthi, Abdullah, Tuli, Khanna, Goldie & Manning (ICLR 2024,
> arXiv:2401.18059) — but not the whole paper, and `weft_index.raptor`'s own module docstring
> states the divergence rather than leaving it to be assumed. Clustering is a fresh, small
> cosine-similarity algorithm — not the UMAP+GMM approach LangChain's own RAPTOR cookbook uses, which
> `CLAUDE.md`'s own rule keeps out of this tree as another codebase's source text. One level of clustering-and-summarisation ships per
> `Expander.run` call; `max_levels` is deliberately not a field on this plugin. **Chaining
> `embed`, `raptor`, `embed`, `raptor`, ... in an operator's own pipeline document does not
> yet build a correct deeper tree** — the second `raptor` stage would receive the whole
> cumulative node set (original leaves plus level-1 summaries) with no filter excluding
> already-summarised nodes, so it could re-merge a leaf with its own summary rather than
> build a genuine next level. *(Re-scoped 2026-09-07 at task 10.4, which moved the stage after
> `embed`: the shipped rung is now `embed` → `raptor`, so the warning above is about the **second**
> `raptor` in such a chain and never the first. The first is what `index-with-raptor` ships, and it
> is correct — a summary comes back already vectorised, by the plugin that wrote it. **And the
> chain the sentence above names is itself one an operator should not write, corrected at 10.6:**
> since 10.4 `raptor` embeds its own summaries, so a second `embed` between two `raptor` stages
> re-bills every leaf and every level-1 summary — the doubled cost 10.4 removed, reintroduced.
> A deeper rung is `embed`, `raptor`, `raptor`.)* That filtering is future work, corrected here (2026-08-18, a
> repair of task 2.32) after review found the claim above stated as fact what neither the
> code nor a test actually supported. `mode: collapsed` is what this ships structurally —
> a summary is just another node
> with its own vector in the same store, found by the existing vector-search retriever exactly
> the way task 2.31's own question nodes are; `mode: traversal` — an explicit top-down descent
> through the tree at query time — is not implemented, and would be a distinct `Retriever`
> position over `Lineage.parents` read as a tree, filed as future work rather than claimed here.
> What this task closes is a known defect from the prior approach: RAPTOR summaries built without
> genealogy tracking carried `relationships={}` and no deletion path could ever reach them; `weft_index.raptor`
> builds every summary through `Node.combine`, which refuses an empty `members` sequence and
> derives `Lineage.sources` as the union of the clustered members' own sources, so cascade
> delete reaches a summary by construction. *Corrected 2026-09-06 (`L9.38`):* this sentence went on
> to say that was "proven against a real corpus, real embeddings and a real store in
> `tests/integration/test_raptor_pipeline.py`, not merely asserted of the type". That file asserts
> the precondition — `summary.lineage.sources` equals the union of its members' (`:305-306`) — and
> never deletes anything (`grep -c delete` over it → `0`), so the end-to-end proof was owed by Phase
> 10 task 10.1. **It exists as of 2026-09-07 and cascade delete is proven in
> `tests/integration/test_raptor_cascade_delete.py` (`delete_source`)**, over a cluster deliberately
> built across two documents: deleting one takes the summary with it and leaves the other document's
> own leaf standing, which is the cross-document case the claim is actually about and the one a
> precondition about `sources` cannot decide on its own. A store deleting on `sources = ARRAY[id]`
> rather than on containment would satisfy that precondition and fail this, silently. The claim is
> written in the form fitness function **26** requires — the cited file and the literal string it
> must contain — so the next time it stops being true, something says so.)*

> *(Corrected 2026-09-06, `L9.30`.* **The row below carried** *(mode: `collapsed` \| `traversal`)*
> **in its name column and "recursively … by descending it" in its description from task 2.32 until
> today, while this block withdrew both** — a correction that did not edit the claim it corrected, so
> the row a reader scanning the table sees kept claiming what the prose four lines above denied. The
> row now says what ships. The mode annotation is gone because `RaptorConfig` has no `mode` field
> (`packages/weft-rag/src/weft_index/raptor.py:132-171`, seven fields) and an index-side plugin
> cannot own a query-time behaviour (`raptor.py:93-102`); the only readers of `lineage.parents` on
> the query path walk child→parent (`weft_retrieve/collapse.py:142-146`,
> `weft_generate/representation.py:68-72`). `build-ledger.md` → Phase 10 is where recursion becomes
> true (10.7) and where a traversal retriever, if ever built, gets its own name and its own row.)*

| Weft name | What it does | Origin | Name provenance |
|---|---|---|---|
| **`raptor`** | Clusters chunks by embedding similarity and writes one LLM summary per cluster as a retrievable node beside the leaves, its `Lineage.sources` the union of its members' — **one level per stage, built by greedy cosine grouping rather than the paper's soft GMM, each divergence stated in the module docstring** (`packages/weft-rag/src/weft_index/raptor.py:35-103`). Retrieval is over the whole tree, flat, through the existing vector-search retriever — what the paper calls *collapsed*. **One tree over the configured store's collection, not one per document** — Chucri et al.'s scope (§4.1) and a deliberate divergence from Sarthi et al., whose p.9 builds one tree per story; `raptor` **the `Expander`** reads no store, so the collection is expected to be indexed in one run and a later batch founds a second tree rather than joining the first (stated in the module docstring and in `index-with-raptor.yaml`, named by the owner 2026-09-07). **That property is narrowed to this contract rather than withdrawn, and the distinction is task 10.14's**: G15 (2026-09-08) settled that a corpus-reading pass is a `Revisable`, a different contract, so `adrap` joins a later batch into this tree while every `Expander` — first-party or not — still reads no store. **Not shipped:** the paper's recursion to deeper levels (Phase 10 task 10.7) and its top-down *traversal*, which, if ever built, is its own `Retriever` under its own name and never a `mode:` of this plugin — the paper measured it worse than collapsed on 20 QASPER stories (p.5) and dropped it. Caveats for any implementation: every clustering knob that matters (`cluster_size`, `min_cluster_size`, `similarity_threshold`, `max_cluster_chars`) is a field and none is hard-coded — hard-coding them defeats configurability. A degrade-rather-than-crash behaviour around a failed summary (continuing with fewer summaries instead of failing the run) is a genuinely useful robustness property that neither the paper nor common reference implementations provide, and is kept deliberately. Under the default `hash` embedder the shipped rung builds zero summaries and its pipeline document says so | Parth Sarthi, Salman Abdullah, Aditi Tuli, Shubh Khanna, Anna Goldie, Christopher D. Manning, *RAPTOR: Recursive Abstractive Processing for Tree-Organized Retrieval*, ICLR 2024, arXiv:2401.18059 | **Literature** — a proper noun with one paper and no competing meaning. Keep the acronym |
| **`adrap`** *(similarity_threshold, cluster_size, max_cluster_chars)* | Joins a newly indexed document into a tree `raptor` already built, instead of founding a second one beside it: assign each new leaf to the nearest existing cluster by a centroid **recomputed from that cluster's stored members**, re-summarise the clusters that grew, and `supersede` each affected summary and every ancestor above it — so no query returns both the old and the new summary of one cluster. A `Revisable` (not an `Expander`), which is what lets it read the corpus through `ctx.require(NodeStore)` while `raptor` and every third-party `Expander` still read no store (G15, 2026-09-08). **Its value is operational, not qualitative, and the row says so because the paper does**: §6.5 measures adRAP *below* a full rebuild on two of three datasets, so re-running `index-with-raptor` over the whole corpus is the higher-quality answer and this rung buys back the ~61 s of ingest per ten PDFs that ledger 10.22 measured. Two stated divergences: **nothing is persisted that is not a `Node`** — Chucri §4.2 stores fitted UMAP and GMM instances with the tree, Weft's clusterer fits no model, so a centroid is recomputed rather than stored — and `auto` here reads the threshold the tree recorded (`RaptorFacts.resolved_*`, task 10.9) rather than deriving one from this run's payload, which would describe the arriving document instead of the corpus it joins. Follows §6.4's greedy variant, which the paper measures as the worse of its two, because the better one needs the fitted state Weft does not have | Charbel Chucri, Rami Azouz, Joachim Ott, *Recursive Abstractive Processing for Retrieval in Dynamic Datasets*, 2024, arXiv:2410.01736, §4, §4.2, §6.4, §6.5 | **Literature** — the paper's own name for the technique, per §2.1 rule 3. Taken rather than reserved at ledger `10.14`; §4 records the release |
| **`hypothetical-questions`** | At index time, generates the questions a chunk would answer and indexes them as retrievable nodes. Caveat: this is easily miscited as HyDE (arXiv:2212.10496) purely on name-association — HyDE is a query-time technique that generates hypothetical *answers*; this is the mechanical opposite, done at index time. A plausible-looking reference attached to the wrong paper is exactly the failure this catalogue exists to catch | Rodrigo Nogueira, Wei Yang, Jimmy Lin, Kyunghyun Cho, *Document Expansion by Query Prediction* (doc2query), arXiv:1904.08375, 2019 | **Framework-coined** ("Reverse HyDE" circulates in framework docs and blog posts). **No paper uses the term** — see §5 |
| **`cross-encoder-rerank`** | Rescores first-stage candidates with a full-attention query-passage model and keeps the top *n*. Caveats: constructing this inline at each call site with divergent defaults, rather than behind one registered and swappable component, defeats composability. Building a cache for the model but never routing calls through it is dead infrastructure worth checking for. And silently returning the unranked candidates when the model fails to load is a silent fallback indistinguishable to the caller from a real reranking — it must fail loudly instead | Rodrigo Nogueira, Kyunghyun Cho, *Passage Re-ranking with BERT*, arXiv:1901.04085, 2019 (never formally published; the canonical citation). The architecture term: Samuel Humeau, Kurt Shuster, Marie-Anne Lachaux, Jason Weston, *Poly-encoders*, ICLR 2020, arXiv:1905.01969. Polish models: Sławomir Dadas, Małgorzata Grębowiec, *Assessing generalization capability of text ranking models in Polish*, presented at **ICAISC 2024**; Springer LNCS proceedings volume dated **2025**, pp. 37-49, DOI 10.1007/978-3-031-84353-2_4, arXiv:2402.14318. **Both years are stated deliberately** — conference 2024, proceedings 2025 — so a bibliography tool does not flag the mismatch as an error | **Literature** |
| **`cooccurrence-graph`** *(max_name_words, min_mentions)* | Attaches to each chunk the capitalised name candidates it mentions and an undirected edge between every pair of them, with **no model call and no credential** — the one advanced rung a laptop can climb, and the stage that makes `index-with-cooccurrence` produce a graph on a machine that has nothing but Postgres. Rows are not written here: the stage attaches ext data and `weft_kg.store.GraphStore.add` derives the entity and relation rows when the node is stored, which is what lets it sit in a pipeline with no graph store configured. **Honest about being crude**, on the class and in this row: a Title-Case run is the candidate rule, so it over-generates on a sentence-initial capitalised word (a stopword list is the only filter) and under-generates on a lower-cased acronym or a name split across a chunk boundary. **No citation, and that is the answer rather than a gap** — see §5. Deliberately **not** `ner` or `named-entities`: this is a regular expression over capitalisation, and taking a name a practitioner would search for is §2.1 rule 4's overclaim with teeth. Qualified per rule 6 against `11.7`'s model-backed sibling. Ledger 11.6 |

### 1.3 Judge techniques

Phase 4 work. The naming problem here is the worst in the catalogue, because the borrowed name points
at a **library that was never actually imported**.

Grepping for `import ragas` returns 0 hits, and RAGAS is absent from `pyproject.toml` — it is not a
dependency. The catalogue's addition is that **the prefix is not merely unnecessary, it is
false in one case**, and that "RAGAS" names two different things which must never be cited as one:

- **The paper** — Shahul Es, Jithin James, Luis Espinosa-Anke, Steven Schockaert, *RAGAS: Automated
  Evaluation of Retrieval Augmented Generation*, EACL 2024 System Demonstrations, arXiv:2309.15217 —
  defines exactly **three** reference-free metrics: Faithfulness, Answer Relevance, Context Relevance.
- **The library** — has since added Context Recall and Factual Correctness and deprecated Context
  Relevance in its original form.

| Weft name | Existing name | Origin |
|---|---|---|
| **`answer-relevance`** | `answer_relevance` | Es et al., arXiv:2309.15217 |
| **`context-relevance`** | `document_relevance` (class `RagasContextRelevance`) | Es et al., arXiv:2309.15217 — one of three (of six) judge metrics in this family that compute the score in code from extracted counts rather than reading it directly off the model; registered under a name that contradicts its own class |
| **`faithfulness`** | `faithfulness` | Es et al., arXiv:2309.15217 — the paper's algorithm decomposes the answer into claims, verifies each, and divides in code; doing this in one call and reading the ratio directly off the model's own arithmetic is a common shortcut that discards the very numerator and denominator the decomposition was meant to produce |
| **`context-recall`** | `ragas_context_recall` | The RAGAS **library**, not the paper — the same self-scored-arithmetic shortcut as `faithfulness` above |
| **`answer-correctness`** | `ragas_answer_correctness` | The RAGAS **library**, not the paper |
| **`answer-completeness`** | `ragas_answer_completeness` | **Nothing.** RAGAS has no completeness metric in the paper or in any version of the library — an invented metric wearing a borrowed name; a reader who goes looking in the RAGAS docs to learn what the number means will find nothing (**Name provenance: False**) |

The lineage the evaluation pack should cite instead, and be explicit that it reimplements rather than
wraps: Lianmin Zheng et al., *Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena*, NeurIPS 2023
Datasets & Benchmarks, arXiv:2306.05685 — which named the method **and catalogued its failure modes
(position, verbosity and self-enhancement bias), none of which single-call judges mitigate**; and Yang
Liu, Dan Iter, Yichong Xu, Shuohang Wang, Ruochen Xu, Chenguang Zhu, *G-Eval*, EMNLP 2023,
arXiv:2303.16634, whose form-filling pattern these prompts structurally resemble.

### 1.4 The rows where a rename is a correction

Consolidated, because these are the decisions with no discretion in them.

| Name | Why the rename is not a preference |
|---|---|
| `ragas_answer_completeness` | **False provenance.** Names a metric that does not exist in the RAGAS paper or library |
| `reverse_hyde` | **Wrong citation** — cites HyDE for a doc2query-shaped technique, and the label has no paper of its own |
| `document_relevance` | Registers a **context**-relevance metric under a **document** name; the class and the registry disagree |
| `rag_consensus` | Names sampling-and-voting; implements contradiction detection. Keeping it burns `self-consistency` — the name Wang et al. (ICLR 2023, arXiv:2203.11171) fixed for the real technique — for a plugin that is not it |
| `rag_adaptive` | Two mechanisms share the word, **with no wiring between them**: the router cannot select the strategy. And `adaptive-rag` is a paper's name for a trained classifier |
| `rag_simple` | Names a single-pass baseline over a pipeline with ≥3 LLM calls and unbounded regeneration. An operator reads this name when deciding what to run in a loop |
| `sides` (repack method) | The name is Wang et al.'s; the ordering is not theirs. Porting the name without the algorithm launders a defect through a citation |

### 1.5 Supporting plugins

`.phase2-design.md` §12 (in-place note 4) obliges this table: task **2.26**'s own audit checks, in
both directions, that a registered plugin name appears somewhere in this document and that a Weft
name this document states is either a registered plugin or a shipped pipeline. §1.1 and §2.2 name
the fourteen techniques the catalogue traces to an origin; every plugin below is a name the phase
also registers that traces to no paper of its own — a fuser, a reranker, a routing policy, a
sufficiency signal, the one shared generator, a provider, an extractor pair, a store, or a prompt
template one of the fourteen resolves by name. None of it is a naming defect; the catalogue owns
naming, not just citation, so a name with nothing to cite still needs a row.

| Weft name | Contract | What it is |
|---|---|---|
| `vector-top-k` | `Retriever` | A single vector search, `top_k` — the retriever `retrieve-then-generate` resolves. Not itself a cited technique (§2.1 rule 5: a composition is a pipeline, never a plugin); the name states the pipeline's own cost, per §12 decision 12 |
| `multi-arm` | `Retriever` | Searches several **arms** of one index in a single stage — the same `VectorSearch`, narrowed per arm by a `Filter` and labelled per arm so a `Fuser` can weight them apart (`multi-arm:leaves`, `multi-arm:raptor`). No citation of its own: it is the arity a pipeline cannot express, not a technique. **A documented exception to §2.1 rule 5** — a composition is normally a pipeline, but two retrievers cannot sit in sequence because they do not compose by type, so the fan-out has to live inside one plugin. Not `hybrid` — **built at ledger 8.6, three rows below** — which additionally needs `TextSearch`; naming it that would have been the overclaim rule 4 forbids. *(Pointer corrected 2026-09-05: this row said "§1.1's unbuilt row" from task 2.33 until 8.6, and §1.1 never held a `hybrid` row. The name was reserved in prose, in two places, and catalogued in neither — which is how a name ends up printed at users in a refusal while nothing can be installed under it.)* |
| `hybrid` | `Retriever` | Searches the **vector** and **text** arms of one store per query and returns both rankings, labelled `hybrid:vector` and `hybrid:text` so a `Fuser` can weight them apart. The second documented exception to §2.1 rule 5, on `multi-arm`'s own footing — two retrievers cannot sit in sequence because they do not compose by type, so the arity lives inside one plugin. **No citation, and that is the answer rather than a gap**: "hybrid retrieval" is a practitioner and framework term for a store satisfying both search protocols — `02` §1's own words, *"hybrid is not a third method — it is a store satisfying both search protocols"* — and the technique it composes is `reciprocal-rank-fusion`, which carries the citation. See §5. **Deliberately does no score fusion**: an alpha over a cosine similarity and a lexical relevance score compares two scales with no common unit — exactly the kind of tuning constant that creeps in when a fusion step is reimplemented per call site instead of shared, per §1.1's `reciprocal-rank-fusion` row. Declares `needs_store = (VectorSearch, TextSearch)` whatever `channels` says, so a run against `qdrant` (no `TextSearch`, ledger 2.6) is refused at assembly rather than at a later `with:` edit |
| `multi-retriever` | `Retriever` | Fans out over other **retrievers**, each resolved by name through `StageLookup` and relabelled `multi-retriever:<arm>` so a `Fuser` can weight the arms apart. **The third documented exception to §2.1 rule 5**, on `multi-arm`'s and `hybrid`'s own footing — two retrievers cannot sit in sequence because they do not compose by type, so the arity lives inside one plugin. What separates it from those two is *what* it fans out over: `multi-arm` takes slices of one index and `hybrid` the two arms of one store, and neither reaches a second retrieval **strategy** or a second **base**. This is the plugin `product-direction.md:16-17`'s "several bases at once" had none of. **Named for what it fans out over, per §2.1 rule 6** — not `fan-out`, which `multi-arm` and `hybrid` also do and which a first implementation may not seize from its siblings; not `federated`, which claims distributed sources with their own policies and would be the overclaim rule 4 forbids; and not `multi-source`, because a *source* is already a document in this tree (`weft_kernel.payload.SourceId`). **No citation, and that is the answer rather than a gap**: the arity is what a pipeline cannot express, not a technique, and the technique it composes is `reciprocal-rank-fusion`, which carries the citation. See §5. **Declares no `needs_store`**, on `iterative-retrieval`'s stated precedent — an arm is resolved at run time, so there is no store capability this class could state ahead of it, and a sub-plugin's own declaration is invisible to the run assembler either way (fitness function 16's own docstring says the same of reachability). An arm returning `NothingToProduce` contributes no lists and the fan-out carries on; one returning `Failed` fails the whole retrieval, because a partial fan-out is a plausible answer against incomplete evidence. Ledger 11.2 |
| `single-list` | `Fuser` | The identity fuser — one ranked list, unchanged. What `no-retrieval` and `retrieve-then-generate` resolve when there is nothing to combine |
| `boolean-combine` | `Fuser` | Combines each Boolean operand's own result set by set algebra — `boolean-retrieval`'s own combiner, never `reciprocal-rank-fusion`'s statistical merge |
| `llm-rerank` | `Reranker` | Asks the model an operator has already configured to rerank — `prompt`, `role`, `top_n`. Ships in place of `cross-encoder-rerank` (§1.2), which needs a model download `09` §4.4 keeps out of the gate |
| `collapse-to-parent` | `Reranker` | Groups a `Ranking`'s hits by parent and keeps one per parent — a `hypothetical-questions` (§1.2) or `raptor` (§1.2) derived node collapses into the one node it stands in for. `policy` (`max`/`sum`/`mean`) states which score survives; ledger **2.33**, `.phase2-findings.md` §11's own closing paragraph. No citation of its own — the artefact it removes is measured, not sourced |
| `threshold-ladder` | `RoutingPolicy` | Closed, operator-authored bands over `query-scorer`'s dimensions |
| `nearest-description` | `RoutingPolicy` | Open: matches a query against every installed pipeline's own `route.summary`, zero-edit on install |
| `always` | `RoutingPolicy` | The constant policy — one named pipeline, no scoring |
| `llm-sufficiency` | `Sufficiency` | Asks the model whether the evidence suffices — this build's own mechanism; §1.1's `refine-on-uncertainty` row states neither `Sufficiency` implementation traces to a paper |
| `hedge-phrases` | `Sufficiency` | A locale-keyed hedge-phrase table, authored fresh for Weft as the documented weak baseline, replacing the substring-matching mechanism described in §1.4 rather than porting it |
| `cited-answer` | `Generator` | The one generator every pipeline above resolves. `when_no_evidence` switches stance (refuse, or answer from memory) rather than a second plugin existing |
| `openai-vision` | `Describer` | `weft-openai`'s image describer, calling the vendor's chat endpoint with a page crop. **No citation, and that is the answer rather than a gap**: describing an image is a capability of a model, not a technique from a paper, and the plugin names the *role* — §2.1 rule 6, the same reasoning that keeps `pdf-layout` from being called `docling`. The model is a `with:` value, so a local or hosted VLM is this plugin with a different `base_url`. The contract it satisfies (`weft_vision.Describer`) names the medium and not the model, which is what lets the same contract cover audio transcription later without a rename. Ledger 9.9 |
| `openai-embeddings` | `Embedder` | `weft-openai`'s account-backed embedder, calling the vendor's embeddings endpoint (`text-embedding-3-small`) |
| `openai` | `LLMProvider` | `weft-openai`'s chat provider (`gpt-5.6-luna`). **Two names, one account, since ledger 8.15**: these were both `openai` until a name answering to two contracts turned out to be selectable by no pipeline document at all — `use:` names a plugin and never a contract, so there was nothing to say which was meant. Fitness function 18 refuses the shape now |
| `scripted` | `LLMProvider` | A fixed-response provider for tests and CI — no network, no account |
| `pdf-text` | `Extractor` | `weft-pdf`'s plain-text extractor — `.pdf`, `MediaType.TEXT` |
| `pdf-layout` | `Extractor` | `weft-pdf`'s layout-aware extractor — same declared extension and media type |
| `pdf-layout-model` | `Extractor` | `weft-docling`'s **learned** layout rung, over docling's page-level object-detection model — the one backend here that reads a page image rather than a text layer, which is what makes a scanned PDF readable at all. Named for what it is rather than for the library behind it, per §2.1 rule 6 — the same reasoning `openai-vision`'s row cites in the other direction (*"the same reasoning that keeps `pdf-layout` from being called `docling`"*). Its own distribution for a measured reason: 897 MB of `torch`, `torchvision` and `transformers` against `weft-pdf`'s few megabytes, so nobody pays for a model their corpus does not need. Ledger 9.13 |
| `qdrant` | `NodeStore` | `weft-qdrant`'s store — derives `VectorSearch` and `MetadataFilter`, deliberately not `TextSearch` (ledger 2.6) |
| `pgvector-graph` | `NodeStore` | `weft_kg`'s store — nodes, sources, entities and relations in one Postgres schema of its own (`kg_*`), sitting **beside** the vector store rather than replacing it: `index-with-graph` names both, and each gets the identical batch (`02` §4). Also `SourceDeletable` and `Reconcilable`, structurally, so `weft delete` and `weft reconcile` reach it because a document names it and for no other reason. **Qualified, per §2.1 rule 6**, and the sibling is already named rather than hypothetical: `01` → *The least-architecture check* defers the traversal contract's promotion into the store family behind `weft-neo4j` implementing it, so an unqualified `graph` would be the first implementation seizing a namespace two are meant to share. Not `graph-store`, which restates the contract the registry already knows as a type (§2.3). Ledger 11.5 |
| `pgvector-traversal` | `GraphTraversal` | `weft_kg`'s bounded, undirected walk — entities by name, the nodes that mention them, and the neighbourhood within *n* hops. **A second name for one capability because two rules pull against each other**: fitness function 18 forbids one name under two contracts, and `[services] graph` resolves through `registry.entry(GraphTraversal, <name>)`, so the role is selectable only where something is registered under the role's own contract. **A second *class*, too** — `weft_cli.fanout.participants_for` deduplicates participants by class and applies its `NodeStore` filter only to the `NodeStore` contract, so one class under both would join every project's fan-out through whichever contract sorted first (`docs/lessons.md` `L11.23`). No citation: a bounded walk over a graph is not a technique from a paper, and the name states what it does over what backs it, per §2.1 rule 6. Ledger 11.5 |
| `passage-relevance` | `Prompt` | `graded-retrieval`'s own template — the question, and the numbered candidates |
| `standalone-question` | `Prompt` | `contextual-query-rewrite`'s template — the follow-up as asked, and the history it depends on |
| `hyde-document` | `Prompt` | `hyde`'s template — the question, and how many hypothetical documents to write |
| `step-back-question` | `Prompt` | `step-back`'s template — the question exactly as the user asked it |
| `next-action` | `Prompt` | The agent loop's own template — the goal, the tools on offer as a numbered catalogue, and what has happened so far. Named for the question it asks the model rather than for a technique, per §2.1 rule 4: choosing a next step from a tool list is what every agent loop does, and claiming a paper for it would be the false provenance rule 4 forbids; `weft_agent`'s own module docstring carries what it is faithful to. **Catalogued 2026-09-09 and registered since Phase 7** — it was invisible to this check for two phases because `test_technique_naming`'s audited set named distributions, and `weft-agent` was never one of them. **G19** folded that pack into `weft-rag` and the omission surfaced on the first run, which is the audited set having been the wrong subject rather than an incomplete one |
| `multi-query-variants` | `Prompt` | `multi-query`'s template — the seed question, and how many alternatives to generate |
| `relevance-grade` | `Prompt` | `corrective`'s template — the question, and one batch of numbered candidates to grade |
| `boolean-parse` | `Prompt` | `boolean-retrieval`'s template — the query to tokenise, and which operator keywords it recognises |
| `sufficiency-check` | `Prompt` | `llm-sufficiency`'s template — the question, and the evidence gathered so far |
| `route-query` | `Prompt` | `query-scorer`'s template — the question, and the dimensions to score it on |
| `answer-with-citations` | `Prompt` | `cited-answer`'s template — the question, and the numbered evidence |
| `contradiction-critic` | `Prompt` | `contradiction-check`'s critic half — the question, and the numbered evidence to judge for agreement |
| `contradiction-answer` | `Prompt` | `contradiction-check`'s answer half — the question, the numbered evidence, and the critic's verdict |

`graded-retrieval` (a `Reranker`, §1.4's conditional name for `corrective` when the plugin gains no
distinct knowledge action) and `routing-policy` (§1.1's row label for the family `threshold-ladder`,
`nearest-description` and `always` implement) are named in §1.1/§2.2 already and are not repeated
here.

---

**Eighteen rows added 2026-09-06, at Phase 8's close review, and the reason is that nothing was
looking.** `tests/docs/test_technique_naming.py`'s `_AUDITED_DISTRIBUTIONS` named four packages —
`weft-retrieve`, `weft-generate`, `weft-llm`, `weft-prompts` — that stopped being distributions at
**G10's re-settlement**, when `weft-rag` began *containing* the fourteen packs rather than pinning
them. `discover(allow=...)` ignores a name it does not know without complaining, so property 5's
reverse direction narrowed from ~100 registered names to **5** and went on passing. Every plugin
below was registered, listed by `weft plugins list`, placeable in a document — and named nowhere in
this catalogue, which is the exact condition §1.5's own opening paragraph says a row exists to
prevent. The check now asserts that every audited distribution actually resolved.

| Weft name | Contract | What it is |
|---|---|---|
| `text` | `Extractor` | Reads a directory of plain-text and Markdown files into one node per file. The default `weft index` resolves, and the reason a clean checkout can index with no PDF backend installed |
| `fixed-size` | `Chunker` | Splits a node's content into fixed-length character windows with a configurable overlap, recording each chunk's offset into its parent. No citation: it is the floor every chunking comparison is measured against, not a claim |
| `hash` | `Embedder` | Turns content into a deterministic vector and understands nothing about it. **Not a quality component and the catalogue says so here as well as in the manuals**: two documents on unrelated topics are as "similar" to it as two ways of saying the same thing. It exists so a clean checkout indexes, searches and passes its whole suite with no account and no model download |
| `unicode-normalize` | `Cleaner` | NFC normalisation, so text that is byte-different and reader-identical compares equal downstream |
| `whitespace` | `Cleaner` | Collapses runs of whitespace and strips the margins a layout-aware extractor leaves behind |
| `hyphenation` | `Cleaner` | Rejoins a word a line break split across two lines — a PDF artefact that otherwise reaches the index as two tokens neither of which is the word |
| `artifact-remove` | `Cleaner` | Removes the repeating page furniture an extractor cannot tell from body text — headers, footers, page numbers — identified by recurrence across pages rather than by a pattern list |
| `table-linearize` | `Cleaner` | Rewrites an extracted table into one row-per-line reading order, so a retriever scoring on text does not score a table as a column of fragments |
| `table-rows` | `Chunker` | Splits a table node into one child per row, each carrying the header into its own text and its own one-row `TableGrid`, with the parent table left in place beside them. Named for what it produces rather than for a method, per §2.1 rule 4 — there is no named technique here to claim, only the measurement §4 records under `describe-table`: row-level chunking with the header propagated moves BM25 Recall@1 **0.366 → 0.754** and hybrid MRR **0.3576 → 0.5945** (arXiv:2605.00318), which is the largest absolute gain in that survey and the bar anything calling itself a table technique has to clear. It is a `Chunker` declaring `Applies(media_type=TABLE)`, which is the atomic rule's own mechanism rather than an exception to it: `fixed-size` declares `TEXT` and routes tables past untouched. Ledger 9.14 |
| `polish-dictionary-spacing` | `Cleaner` | Repairs missing inter-word spacing in Polish text against a dictionary. **The one shipped plugin whose subject is a specific language**, and it is a `Cleaner` rather than anything wider precisely so the content-language axis stays a fact on the node |
| `keybert` | `Enhancer` | Attaches keyword terms to a node. Named for the method it applies rather than for the outcome it claims, per §2.1 rule 4 |
| `describe-figure` | `Enhancer` | Reads a figure's pixels back through the blob store, asks the configured `Describer` what they contain, and puts the answer beside the caption the document already supplied. Named for what it does to the node rather than for the model that answers it — §2.1 rule 4, and the same reason the `Describer` contract names the medium and no vendor. It traces to no paper of its own: describing an image so text retrieval can reach it is the obvious move once a caption is the thing being matched, and `11` §2.4 settles it as a pipeline position rather than a technique |
| `generate-questions` | `Prompt` | The prompt `hypothetical-questions` (§1.2) resolves by name to produce the questions a chunk answers |
| `summarize-cluster` | `Prompt` | The prompt `raptor` (§1.2) resolves by name to summarise one cluster of children into a parent node |
| `summarize-for-query` | `Prompt` | The prompt `postqfrap` (§1.1) resolves by name to summarise one cluster of retrieved passages **against the question**, keeping only what bears on it. `summarize-cluster`'s query-time twin: the same shape with one field added, and that field is the whole difference between this technique and `raptor` run at query time |
| `faithfulness-judge` | `Prompt` | The prompt the `faithfulness` metric resolves — is every claim in the answer supported by the retrieved context |
| `answer-relevance-judge` | `Prompt` | The prompt the `answer-relevance` metric resolves — does the answer address the question asked |
| `answer-correctness-judge` | `Prompt` | The prompt the `answer-correctness` metric resolves — does the answer agree with the reference |
| `answer-completeness-judge` | `Prompt` | The prompt the `answer-completeness` metric resolves — does the answer cover what the reference covers |
| `context-relevance-judge` | `Prompt` | The prompt the `context-relevance` metric resolves — is the retrieved context about the question |
| `context-recall-judge` | `Prompt` | The prompt the `context-recall` metric resolves — does the retrieved context contain what the reference needed |

**What this table deliberately does not owe rows for, and where those live instead.** A `Command`
is `03`'s subject and is already generated into `manual/user-manual.md`'s command table; a
`Renderer` is output plumbing making no technique claim; a `GenerationMetric` or `RetrievalMetric`
is `09` §4's, which specifies what a baseline is judged against and names every one it uses. That
is a boundary rather than a backlog, and it is stated in
`tests/docs/test_technique_naming.py`'s `_CONTRACTS_OUTSIDE_THE_CATALOGUE` so the check enforces
the same line this paragraph draws — 41 of the 63 names that read as missing are these.

## 2. The naming rule, argued

### 2.1 The rule

1. **Bare, lowercase, kebab-case. No capability prefix.** `hyde`, not `rag_hyde`; `step-back`, not
   `StepBackStrategy`. This matches the names `02` §3 already publishes (`use: docling`,
   `use: bge-m3`) and the entry-point style Phase 0 already ships.
2. **Name the mechanism, never a position on a difficulty axis.** `simple` / `complex` / `adaptive`
   are relative to a codebase the reader has not seen, and the axis rots: the first plugin that lands
   between `simple` and `complex` has nowhere to go.
3. **Use the literature's own name when the literature has one** — including acronyms. `hyde`,
   `raptor` and `step-back` are what a practitioner will search for, and rewriting them "more clearly"
   would make them less findable, not more.
4. **Never take a name that promises more than the code does.** This is the rule with teeth. It is why
   `refine-on-uncertainty` is not `self-rag`, why `corrective` is conditional, and why `sides` may not
   ship over a defective ordering.
5. **A composition is a pipeline, never a plugin.** `rag_complex` is HyDE plus repacking on the
   baseline skeleton. Registering the composition would put a name on something requirement 3 says is
   derivable data.
6. **Qualify a name that will have siblings.** `cross-encoder-rerank`, not `rerank` — Weft will want
   `llm-rerank` and `colbert-rerank`, and an unqualified name lets the first implementation seize the
   namespace.

### 2.2 Applied to all ten

| Existing name | Weft | Kind of change |
|---|---|---|
| `direct` | `no-retrieval` | Rename |
| `rag_simple` | `retrieve-then-generate` | Rename |
| `rag_complex` | **not a plugin** — `hyde` + `repack`, composed | Split; the composition becomes a named pipeline (`hyde-repack`) if a preset is wanted |
| `rag_adaptive` | `refine-on-uncertainty` | Rename, and the router half separates into `query-scorer` + `routing-policy` |
| `rag_multi_query` | `multi-query` + `reciprocal-rank-fusion` | Split — the fuser is reusable over hybrid retrieval, and a fusion step that is not its own plugin tends to get re-implemented per call site instead of shared |
| `rag_iterative` | `iterative-retrieval` | Prefix drop |
| `rag_corrective` | `corrective` \| `graded-retrieval` | Prefix drop, name conditional on the implementation |
| `rag_consensus` | `contradiction-check` | Rename — the current name describes a technique the code does not implement |
| `rag_boolean` | `boolean-retrieval` | Rename |
| `rag_stepback` | `step-back` | Prefix drop, hyphen restored to match the literature |

### 2.3 Why the prefix has to go, on the evidence itself

The argument is usually "in a RAG engine, `rag_` carries zero bits". True, and weak — four characters
is not an argument. The stronger one sits in a real registry examined for this catalogue: of ten
technique names reviewed, only one dropped the prefix, and it was the one plugin that does not
retrieve at all.

**`direct` is the only one of the ten without the prefix**, because it is the only one that is not
RAG. So the prefix *was* carrying semantics — it silently marked "this retrieves" — and the moment a
plugin came along that did not retrieve, the convention broke rather than expressed it. A marker that
one member has to opt out of is not a namespace, it is an undeclared boolean field smuggled into a
string.

Weft cannot even have that field. Its registry is contract-scoped: a `Strategy` is registered as a
`Strategy`, so the contract already says what kind of thing the name refers to, and the prefix is
restating in a string what the registry knows as a type. That is the same failure mode `README.md`
opens with — one fact in two places, one of which cannot be checked.

The same registry is inconsistent about it anyway: `rag_complex` but `reverse_hyde`;
`ragas_context_recall` but `faithfulness`. There is no convention to preserve.

### 2.4 The cost of changing later, stated plainly

A plugin name is not an implementation detail. Once published:

- it appears in third-party `weft.yaml` files that Weft does not control;
- it appears in Weft's own error path — `02` §2 requires every unresolvable name to be printed back
  with its reason, so the name is part of the user-facing failure surface;
- it appears in the registry's "valid options" list, which requirement 5 makes the *entire content* of
  an unknown-name failure. A list rendered as `no-retrieval, hyde, step-back, corrective, …` is
  self-explanatory; the same list rendered as `direct, rag_simple, rag_complex, …` invites the reader
  to ask "complex how?" and answers nothing;
- and renaming it later is a compatibility event, which lands on **G9** (contract versioning and
  deprecation, Open). Every name published before G9 closes is a name G9 will have to write a policy
  for.

Which is the timing argument: **these names are cheap to get right now and expensive to change after
Phase 2 ships.** Nothing here is a matter of taste that can be revisited in Phase 5.

---

## 3. What this changes about the plan

### 3.1 The gap

`build-ledger.md` → Phase 2 has **one** task about technique: `2.4`, *"a retrieval strategy is a
plugin, with domain types on both sides."* That task is right and should not change — it is the
**contract**. But nothing in the ledger required a single technique to exist on the other side of it,
and `2.8` (the router discovers strategies from the registry) can be demonstrated green with two
strategies in the tree.

That is precisely the state requirement 6 exists to catch — `01` → *What "modern and elastic" has to
mean concretely*: **"a mechanism can be perfect and empty"**, and *"a microkernel that ships nothing is
a plugin API with no product."* A ledger that tracks the seam and not the technique will produce
exactly that, one reasonable commit at a time, and every commit will be defensible.

The second clause of requirement 6 is also at stake and was not covered by 2.4 either: *every piece is
parameterisable and composable by someone who did not write it*. Four of the techniques above were
found welded in place — HyDE has no configuration and cannot run outside `rag_complex`, repack
is hard-coded to one method, the reranker is a constructor call in two files, RAPTOR's two shape knobs
are literals. Lifting them into plugins without lifting their parameters would satisfy 2.4 and fail
requirement 6.

### 3.2 The task lines

In `build-ledger.md`'s exact format, for Phase 2. **`2.4` is unchanged** — it is the contract, and
these hang off it.

**Ids are 2.13 and up because ids are never reused** (`build-ledger.md` → *How to read a task line*),
not because the work comes last. **The work order is: `2.4` → this block → `2.8`.** A router cannot be
shown to discover what it was never told about until there is a registry of things it was never told
about. Phase 0's `0.12`–`0.14` already set the precedent that id order and work order are separate;
the ledger states the order explicitly rather than implying it from numbering.

**The lines are `2.13`–`2.26` in `build-ledger.md` → Phase 2**, one per technique, in the order §1.1
gives them. The ledger owns their state and their exact wording; this file owns what each one is
*about*, which is the §1.1 row each of them names as its owner. They are not reproduced here: a second
copy of a live task line is the drift `README.md` opens by describing.

### 3.3 Which are ⚠, and why

**⚠ on 2.15, 2.16, 2.17, 2.18 and 2.19 — all five for the same reason, and it is G2.**

These are the five techniques that are *stages in a composed query path* rather than whole strategies:
a transform before retrieval, a fan-out, a fusion, a reorder after it. Whether a query path is
expressible as pipeline data — and in what form, YAML or Python or both — is exactly what G2 settles,
and the ledger already carries ⚠ on `2.7` for that reason. If G2 lands somewhere that makes a query
path a method body rather than data, all five of these tasks change shape: they become parameters of a
strategy instead of stages a user can compose. The property each states would still be desirable; the
sentence would no longer be true as written.

**No ⚠ on the rest.** 2.13, 2.14 and 2.20–2.26 are whole strategies behind the `Strategy` contract,
which `02` §1 owns and which no open gate touches. They are real tasks with real content today.

**Two of them are what `01` → Phase 2's *Gate* line is about**, and it is worth naming them rather
than marking them. `01` says: *"Re-open G5 only if a strategy cannot express what it needs to pass
along."* **2.20** (a retrieval loop carrying accumulated evidence across rounds) and **2.24** (a
confidence signal produced during generation and read by the strategy) are the two most likely to hit
that wall. If either does, the instruction is to **stop and reopen G5**, not to widen the payload
inside a commit. They are not ⚠, because G5 is settled — but they are where it would come unsettled.

### 3.4 A cross-phase note, raised rather than decided

**Phase 4.** `4.2` says the metric suite ships *"with its four recorded defects fixed at the door"*.
This catalogue finds a fifth defect and a naming correction, raised here rather than resolved:

- **A fifth defect** — **three** of six judges read the score off the model's own arithmetic while
  the numerator and denominator sit extracted and unused. **Two** get it right and both follow the
  same better pattern: dividing extracted counts, or extracting a full confusion-matrix term set from
  the judge and deriving an F1 in code. The remaining judge also computes in code but is **not** an
  instance of the pattern: it never asks the model for a number at all — it scores by embedding
  similarity.
- **The `ragas_` prefix is false, not merely unnecessary.** RAGAS is not a dependency here. It should
  also be recorded that `ragas_answer_completeness` is not a RAGAS metric under any version of the
  library — so the prefix is a provenance claim, and it is untrue.

Both are flagged here, in the form `build-ledger.md` → *Raised, not resolved* uses, rather than
settled inside a document that does not own them.

---

## 4. Reserved names

Part of what this document owns, and the cheapest thing in it. These names must stay free because the
literature has already fixed them for techniques Weft does not implement:

`self-rag` (Akari Asai, Zeqiu Wu, Yizhong Wang, Avirup Sil, Hannaneh Hajishirzi, *Self-RAG*, ICLR
2024 oral, arXiv:2310.11511) · `flare` / `active-retrieval` (Jiang et al., EMNLP 2023,
arXiv:2305.06983) · `ircot` (Harsh Trivedi, Niranjan Balasubramanian, Tushar Khot, Ashish Sabharwal,
*Interleaving Retrieval with Chain-of-Thought Reasoning*, ACL 2023, arXiv:2212.10509) · `iter-retgen`
(Zhihong Shao et al., Findings of EMNLP 2023, arXiv:2305.15294) · `self-ask` / `multi-hop` (Ofir
Press, Muru Zhang, Sewon Min, Ludwig Schmidt, Noah A. Smith, Mike Lewis, *Measuring and Narrowing the
Compositionality Gap*, Findings of EMNLP 2023, arXiv:2210.03350) · `self-consistency` (Xuezhi Wang et
al., ICLR 2023, arXiv:2203.11171) · `adaptive-rag` (Jeong et al., NAACL 2024, arXiv:2403.14403) ·
`query2doc` · `ragas-*` (free for a pack that genuinely wraps the library).

**Added 2026-09-06, from Phase 10's four papers** (`build-ledger.md` → Phase 10; each read at source):
`t-retriever` (Chunyu Wei, Huaiyu Qin, Siyuan He, Yunhai Wang, Yueguo Chen, *T-Retriever: Tree-based
Hierarchical Retrieval Augmented Generation for Textual Graphs*, 2026, arXiv:2601.04945 — cited as
arXiv; the PDF carries an AAAI template block and no acceptance statement. **Must not be taken by
anything that omits the GNN soft prompt of its eq. 14–16**, which every Weft plugin would: that path
prepends a vector to an LLM's input embedding layer, and `LLM.complete` takes a rendered string) ·
`structural-entropy` / `s2-entropy` (the same paper's criterion, eq. 5 — the criterion, not the
system) · `g-retriever` (He et al. 2024), `grag` (Hu et al. 2024) and `archrag` (Wang et al. 2025 —
the structure-first hierarchical baseline), all three as cited in T-Retriever's baselines, p.5, and
none read at its own source · `hipporag` (Jimenez Gutierrez et al. 2024, as cited in T-Retriever's
related work, p.2; PPR-based; not read at source). **`adrap` was reserved here and is now taken** — ledger `10.14`, 2026-09-08, and its row is in
§1.1. The reservation described it as "the incremental tree, which the paper's own §6.5 measures
below a full rebuild on two of three datasets", and **that caveat survived into the plugin rather
than being dropped on the way**: it is in the module docstring, in `index-with-adrap.yaml`, and in
the §1.1 row, because §2.1 rule 4 makes a name a claim and the honest claim here is "cheaper to
keep current", never "better". What unblocked it was grilling session **G15**, which found the
reservation's implicit assumption wrong: the blocker was thought to be persisted per-cluster state
(Chucri §4.2 stores fitted UMAP and GMM instances with the tree) and Weft's clusterer fits no
model, so a cluster's whole state is a centroid recomputable from members already stored — **no
row that is not a `Node`**. **`postqfrap` was reserved here and is now taken** — ledger `10.15`, 2026-09-08, and its
row is in §1.1. The reservation said *"if the technique ever ships in Weft it is a pipeline
document, not a plugin, so the name stays free"*, and grilling session **G15** found that wrong on
both halves: a query-time summariser is not an `Expander` and never needed one, because `Ranking`
already carries `origin: Query` and `ContextPacker` is `Stage[Ranking, Passages]` — so the position
exists, and something still has to *summarise*, which is a plugin.

`colvbert` is **neither reserved nor to be taken, for a third reason**: its paper (Takato Yasuno,
*RAPTOR-AI for Disaster OODA Loop*, 2026, arXiv:2602.00030, §3.2) coins it as "Contextualized Late
Interaction over Visual-BERT" and asserts ColBERT-style token-level matching, while its own eq. 1–3
produce one dense fused vector per chunk and eq. 4 clusters that single vector — no MaxSim, no
token-level scoring anywhere in the PDF — and Table 1 then uses the same name for an ablation
baseline "without hierarchical structure". One name for two things, and the mechanism it names
demonstrated for neither: not a technique the literature has fixed, so nothing to reserve, and an
overclaim under §2.1 rule 4 to take. `late-interaction` and `maxsim` are already reserved by `11`
(`11:238-239`).

**Added 2026-09-06, from Phase 9's design (`11`)** — the multimodal set this section owed and did
not hold. The first six are the literature's, on this section's own rubric; the last three are
**Weft's own names, held against nothing built**, which is a different reason and is stated as one:

`colpali` · `colqwen` · `late-interaction` · `maxsim` (all four fixed by the late-interaction
literature; `11` §3 D5 has why none is built) · `visual-citation` · `grounded-answer` — the last two
under §2.1 rule 4 rather than under provenance: ViDoRe V3 (arXiv:2601.08620) measures visual
grounding F1 at **0.602 human, 0.089 Qwen3-VL, 0.065 Gemini 3 Pro**, so a plugin called
`grounded-answer` today would claim a capability the field delivers at roughly one-seventh of human.

`describe-query-image` · `describe-table` — Weft's own, reserved so that the
first implementation cannot seize a name that will have siblings (§2.1 rule 6).

**`pdf-layout-model` was reserved here and is now shipped** — ledger `9.13`, 2026-09-06, and its row
is in §1.5 beside the two `weft-pdf` rungs. The reservation did the job it exists to do: the name
was fixed before the code, so the first implementation could not call itself `docling` and leave a
second learned rung with nowhere to go. `pdf-layout` was already the pdfplumber rung's name, which
is why the learned one is not simply that.

**`describe-table` is reserved and deliberately not built, and the number is why.** A table already
gets two *deterministic* renderings of its grid — index form and prompt form, ledger `9.6` — and its
rows become children with the header propagated (`9.14`). Those are where the measured gain is:
row-level chunking moves BM25 Recall@1 **0.366 → 0.754** and hybrid MRR **0.3576 → 0.5945**
(arXiv:2605.00318). An LLM pass over table chunks was evaluated against the same corpus family and
measured **+2.2 to +2.8pp Recall@5** (arXiv:2604.01733) — an order of magnitude less, for one model
call per chunk at index time, which is the dominant ingest cost of any table pipeline. `11` §6 rank
14 is the refusal; `01` → *The least-architecture check* carries the reopen trigger. The asymmetry
with a figure is not an oversight: a figure has no structure to render, so a describer is the only
thing standing between it and a caption or nothing. **Whoever builds this has to beat 0.754, not
0.366.**

`decomposition` is reserved too, for the opposite reason: it is spoken for by the *reasoning*
decomposition line (least-to-most — Denny Zhou et al., ICLR 2023, arXiv:2205.10625; decomposed
prompting — Tushar Khot et al., ICLR 2023, arXiv:2210.02406), and using it for Boolean operand
splitting would promise sequential dependent sub-answers that `boolean-retrieval` structurally cannot
produce.

---

## 5. What is not confirmed

Stated as a section rather than as footnotes, because the value of a catalogue is proportional to how
visible its gaps are.

**Names with no traceable origin.**

- **`cooccurrence-graph`** — built at ledger **11.6** with **no origin paper**, and the search was made rather than skipped. Building a co-occurrence graph from capitalised runs is ordinary, unattributed practice: there is a large literature on co-occurrence networks and on graph construction for retrieval, and **no work introduced or named this particular mechanism**, which is a crude candidate rule chosen because it needs no model. So the name states the mechanism (§2.1 rule 2) and claims nothing about provenance. Recorded here rather than left blank, because a row with an empty Origin column reads as a citation somebody forgot to fill in.

- **`hybrid`** — built at ledger **8.6** with **no origin paper cited, deliberately**. The
  dense-plus-lexical combination has a real literature (and its *fusion* step is
  `reciprocal-rank-fusion`, cited in full in §1.1), but this catalogue has **not** searched that
  literature at source and will not assert an origin it has not read — `CLAUDE.md`'s measure-before-
  asserting rule applied to a citation rather than to a count. The name is treated as
  **taxonomy/framework-coined**, and it is one Weft had already fixed the meaning of internally
  before the plugin existed: `02` §1 and `weft_retrieve.payload.Channel`'s own docstring both define
  hybrid as *"a store satisfying both search protocols"*, and `weft_retrieve.vector_top_k` has
  printed the name at operators in a refusal since task 2.14. **What is unconfirmed** is whether any
  paper introduced the term, and whether the practice of fusing the two arms by rank rather than by
  a weighted score blend is attributable. Anyone who searches it should record the answer here.
- **`direct`** — searched LlamaIndex, LangChain and Haystack documentation for a no-retrieval routing
  mode, query-engine setting or component by that name. Found none. Treated as ad hoc;
  **unconfirmed as framework-coined**.
- **`rag_consensus`** — searched LlamaIndex's fusion modes and LangChain's retrieval docs; nothing
  named "consensus". Treated as ad hoc.
- **"Reverse HyDE"** — searched alongside "hypothetical questions", "arXiv" and "doc2query"; only
  framework docs, blog posts and survey taxonomies. **No paper confirmed to use the term.** Treated as
  framework-coined with low confidence, *not* as a paper that was not found.
- **"Naive RAG"** — no paper used the term before Gao et al.'s survey (Dec 2023). Whether LangChain or
  LlamaIndex used it informally earlier is **unconfirmed in the negative**: docs and blog posts of that
  era are poorly archived and search is dominated by post-survey secondary sources.
- **"Iterative retrieval"** as a framework label — searched; LlamaIndex's nearest component is the
  Multi-Step Query Engine and LangChain's is the MultiQuery Retriever, neither named this.
  **Framework-coinage unconfirmed**; the survey-taxonomy origin is confirmed.

**Facts about confirmed papers that were not pinned down.**

- **HyDE's sample count.** Secondary sources say 5 in some places and 8 in others; the arXiv and ACL
  PDFs would not render to text and the abstract does not state it. The *shape* is solidly confirmed
  (sample several, embed each, average **with the original query's embedding**). **Do not put a number
  in a docstring without opening §3 of the paper.**
- **Self-RAG's "top-1%" designation.** OpenReview's `venue` field reads *"ICLR 2024 oral"*, so the
  oral designation is confirmed at source and §4 states it. The widely repeated **top-1%** figure was
  **not** confirmed and is asserted nowhere in this document.
- **The Polish reranker checkpoint.** `sdadas/polish-reranker-roberta-v3` **post-dates**
  arXiv:2402.14318. Cite that paper for the approach, never as the source of v3's reported numbers.
- **The LangChain RAPTOR cookbook.** Removed upstream from `langchain-ai/langchain` (404 on master and
  on the v0.1.0 tag). The lineage is confirmed from a preserved third-party copy plus ~133 GitHub
  files carrying the identical function set — strong evidence, **not the primary artefact**. If the
  licensing ledger needs the primary artefact it must come from a git-history walk of that repository.

**Deliberately not asserted.**

- **No origin paper for Boolean retrieval.** Operational Boolean systems predate any citable paper.
  Manning et al. Ch. 1 is the canonical *statement*. Treat any citation claiming an origin paper with
  suspicion.
- **Not searched, and therefore not cited:** Rocchio (1971) relevance feedback; Montague & Aslam's
  Condorcet Fuse (the baseline in RRF's own title); Query2Box (BetaE's conjunctive-query predecessor);
  Speculative RAG (arXiv:2407.08223, seen in results, unverified); the learned-router line surfaced by
  search (RAGRouter, SkewRoute); and one result that appeared as "NSFL: A Post-Training Neuro-Symbolic
  Fuzzy Logic Framework". All are plausibly relevant. **None has been verified at source and none
  should enter `docs/` until it has been**, per `CLAUDE.md`'s evidence rule.
- **Conversational query rewriting** has a literature this catalogue did not trace. The
  `contextual-query-rewrite` row names the technique and admits the gap rather than attaching a
  plausible citation to it.

**Everything else in §1 was verified against arXiv, the ACL Anthology, Crossref, OpenReview and NIST's
TREC proceedings index** — titles, author lists, years, venues, page numbers and arXiv ids read off
the primary records. **No arXiv id in this document was inferred from a pattern.**
