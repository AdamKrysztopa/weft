# 10 — Technique catalogue and plugin naming

**Reference.** This file owns **the provenance of every technique Weft ships**: where the idea comes
from in the literature, whether its common name was earned by a paper or coined by tooling, the
canonical plugin name that follows, and whether the reference's implementation is faithful to the thing it
is named after.

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
duplicating them. It does not decide what to lift from the reference or where it lands — `04` owns that,
and the fidelity column here is evidence for `04`'s decisions, not a second copy of them.

**Weft copies no source text from the reference or from anywhere else.** Everything below traces *ideas*
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
| **Reference** | Whether `a prior project`'s implementation is faithful to what it is named after: **Faithful** · **Simplified** · **Diverges** · **Different technique** · **Defective** |

**Name provenance values.**

- **Literature** — a paper introduced the technique *and* named it. The name carries authority; keep it.
- **Taxonomy** — a survey or textbook coined the label to organise work that had no agreed name. The
  technique is real; the label has no more authority than its usefulness.
- **Framework-coined** — the label comes from LangChain / LlamaIndex / LangGraph documentation or a
  blog post, not from a paper. **A rename here is a correction, not a preference.**
- **Reference-coined** — the label exists only in `a prior project`. It carries no authority whatsoever.
- **False** — the name claims a paper or library that does not contain the thing. Renaming is mandatory.

---

## 1. The catalogue

### 1.1 Query-path techniques

Every row here is Phase 2 work. `01` → Phase 2 owns the phase; this table owns what each name means.

| Weft name | What it does | Origin | Name provenance | Reference |
|---|---|---|---|---|
| **`no-retrieval`** | Answers from the model's parametric memory; retrieves nothing and returns an empty source list by design | The *setting* was named by Adam Roberts, Colin Raffel, Noam Shazeer, *How Much Knowledge Can You Pack Into the Parameters of a Language Model?*, EMNLP 2020, arXiv:2002.08910 — "closed-book QA". The *name* is Adaptive-RAG's label for this branch, written **"No Retrieval"** (§A.2, and the Types column of its results tables): Soyeong Jeong, Jinheon Baek, Sukmin Cho, Sung Ju Hwang, Jong C. Park, *Adaptive-RAG*, NAACL 2024, arXiv:2403.14403. **The technique itself needs no citation — it is the null case** | Reference-coined (`direct`). Not found in LlamaIndex, LangChain or Haystack documentation as a routing mode or component name — see §5 | **Faithful** — the null case implemented as the null case, `strategies/basic.py:56-75`. It is the only path that bypasses citation binding and the post-generation guardrails, which is correct but should be a *stated* property in Weft, not a consequence of which helper it calls |
| **`retrieve-then-generate`** | Retrieves once for the user's question and answers from that context, with citations | Danqi Chen, Adam Fisch, Jason Weston, Antoine Bordes, *Reading Wikipedia to Answer Open-Domain Questions*, ACL 2017, pp. 1870-1879, arXiv:1704.00051 — the retriever→reader split this actually implements. The three letters and the trained formulation are Patrick Lewis et al., *Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks*, NeurIPS 2020, arXiv:2005.11401 | Taxonomy — "naive RAG" is a **retronym** from Yunfan Gao et al., *Retrieval-Augmented Generation for Large Language Models: A Survey*, arXiv:2312.10997, an **unrefereed preprint marked "Ongoing Work"**. No paper used the term before Dec 2023 | **Diverges, and the name lies about cost.** `basic.py:92-120` runs a query-rewrite LLM call, all-modes hybrid retrieval with RRF, cross-encoder reranking, and up to *N* regenerations behind three guardrails. Floor ≈3 LLM calls; ceiling unbounded by inspection. A plugin an operator will run in a loop must not be called `simple` |
| **`contextual-query-rewrite`** | Rewrites a follow-up question into a standalone retrieval query using the conversation history | No single origin traced; conversational query rewriting has its own literature which **this catalogue has not searched** — see §5 | **Unconfirmed** | **Hidden, not absent.** `_query.py:52-66` runs a full LLM call on *every* strategy including the baseline, unconditionally, un-nameable and un-disableable. It is a technique wearing no name at all, which is the same defect as a technique wearing the wrong one |
| **`hyde`** | Generates a hypothetical answer document and retrieves against *that* instead of the question | Luyu Gao, Xueguang Ma, Jimmy Lin, Jamie Callan, *Precise Zero-Shot Dense Retrieval without Relevance Labels*, ACL 2023, pp. 1762-1777, arXiv:2212.10496 | **Literature** — the authors coin "HyDE" in their own abstract. Keep the acronym; it is what a practitioner will search for | **Simplified, and inverted in one respect.** `strategies/hyde.py:74-87` generates **one** document and returns its *text*; the paper averages the embeddings of several **together with the original query's embedding**. `basic.py:165` discards the user query entirely, then feeds the hallucinated passage to BM25 (`retriever.py:814`) and to the cross-encoder as its query (`retriever.py:833`) — HyDE is a claim about *dense* retrieval only. No fallback: garbage in, garbage is the query |
| **`repack`** *(method: `sides` \| `forward` \| `reverse`)* | Reorders the ranked node list before it enters the prompt, to exploit position effects in long contexts | The effect: Nelson F. Liu, Kevin Lin, John Hewitt, Ashwin Paranjape, Michele Bevilacqua, Fabio Petroni, Percy Liang, *Lost in the Middle: How Language Models Use Long Contexts*, TACL vol. 12, pp. 157-173, 2024, arXiv:2307.03172. The operation and its three method names: Xiaohua Wang et al. (14 authors), *Searching for Best Practices in Retrieval-Augmented Generation*, EMNLP 2024, arXiv:2407.01219 §3.6 | **Literature** for `repack` and the three method values. LlamaIndex's `LongContextReorder` is the framework label and names the *problem*, not the operation — do not adopt it | **Defective.** `repacking.py:149-155` emits `[d0, d6, d1, d5, d2, d4, d3]` for n=7 — best at the head, **worst** in slot 1, median at the tail — while its own docstring three lines above (`:120-125`) states the correct definition. That is a best/worst zip-interleave, not a sides packing. The correct implementation was already installed in the reference's venv (`llama_index` `LongContextReorder`). Also hard-coded to `sides` (`basic.py:183`), which is not even Wang et al.'s winner — their Table 11 selects `reverse` on its **Avg** column, at 0.483 |
| **`step-back`** | Abstracts the question into a more general one, retrieves for both, and answers grounded in both contexts | Huaixiu Steven Zheng, Swaroop Mishra, Xinyun Chen, Heng-Tze Cheng, Ed H. Chi, Quoc V. Le, Denny Zhou, *Take a Step Back: Evoking Reasoning via Abstraction in Large Language Models*, ICLR 2024 (poster; OpenReview forum `3bq3jsvcQ1`), arXiv:2310.06117 | **Literature** — the paper names the technique in its own title. LangChain's *Query Transformations* post (24 Oct 2023) popularised the RAG framing, but that framing is the paper's own | **Faithful on the blocking path; a different technique on the streaming path.** `strategies/stepback.py:100-149` keeps the literal and abstract contexts in separate prompt slots, which is *more* faithful than most implementations. But `stepback.py:270` ends the streaming twin in the generic cited-context helper, discarding the split — so under streaming the strategy is dual-query retrieval with fusion and the paper's step 2 is simply absent. One name, two techniques, and the weaker one is the interactive default |
| **`multi-query`** | Fans one question into several reformulations and retrieves each independently | The idea: Nicholas J. Belkin, Paul Kantor, Edward A. Fox, Joseph A. Shaw, *Combining the evidence of multiple query representations for information retrieval*, Information Processing & Management 31(3), pp. 431-448, 1995. The problem it solves: George W. Furnas, Thomas K. Landauer, Louis M. Gomez, Susan T. Dumais, *The vocabulary problem in human-system communication*, CACM 30(11), pp. 964-971, 1987. LLM-generated expansion: Rolf Jagerman, Honglei Zhuang, Zhen Qin, Xuanhui Wang, Michael Bendersky, *Query Expansion by Prompting Large Language Models*, arXiv:2305.03653, 2023 | **Framework-coined**, but descriptive and aligned with the IR literature's "multiple query representations" — keep it. LangChain's `MultiQueryRetriever` put the exact string into circulation | **Simplified.** The original query is dropped (`multiquery.py:72-77`) — the sources retrieve it alongside the variants. The prompt (`en.yaml:580-585`) asks for *paraphrases*, which forbids the two things the expansion literature credits: new terms, and aspect coverage. Near-duplicate queries also weaken the fusion, whose benefit comes from rankings that disagree |
| **`reciprocal-rank-fusion`** | Merges several ranked lists into one by summing `1/(k+rank)` | Gordon V. Cormack, Charles L. A. Clarke, Stefan Büttcher, *Reciprocal rank fusion outperforms condorcet and individual rank learning methods*, SIGIR 2009, pp. 758-759, DOI 10.1145/1571941.1572114. Precursor: Edward A. Fox, Joseph A. Shaw, *Combination of Multiple Searches*, TREC-2, NIST SP 500-215, 1994, p. 243 | **Literature** | **Faithful, and duplicated.** `_retrieval_post.py:113-133` is exactly the 2009 formula with the paper's own `k=60` (`config/models.py:158-162`). It is implemented a **second** time for hybrid modes in `retriever.py`, and only the second copy grew weighted-alpha behaviour. Two copies of one technique is what a missing plugin boundary looks like |
| **`iterative-retrieval`** | Retrieves, asks a critic whether the evidence suffices, generates a new query from what is missing, and answers only once the loop ends | Peng Qi, Xiaowen Lin, Leo Mehr, Zijian Wang, Christopher D. Manning, *Answering Complex Open-domain Questions Through Iterative Query Generation*, EMNLP-IJCNLP 2019, arXiv:1910.07000 — this is the shape the reference implements | **Taxonomy** — the label is a bucket in Gao et al.'s survey (arXiv:2312.10997 §V-A), not a technique name. It cannot miscite a paper, and it will never tell a user whether generation is interleaved | **Simplified, and honestly described.** `iterative.py:70-170` is Qi et al.'s loop with an LLM sufficiency critic in place of a trained query generator. Two things to fix at the door: `min_loops=2` (`types.py:240-244`) forces a second round even when the critic says stop — no paper in the family does that — and `critique.py:76-84` treats *any non-empty context* as "complete" when the critique call fails, silently downgrading the strategy to single-shot |
| **`corrective`** *(name conditional — see below)* | Grades each retrieved document against the query, discards the failures, and takes a corrective action when the set is judged bad | Shi-Qi Yan, Jia-Chen Gu, Yun Zhu, Zhen-Hua Ling, *Corrective Retrieval Augmented Generation*, arXiv:2401.15884, 2024. **arXiv preprint only** — the authors' own BibTeX still reads `journal={arXiv preprint}` and the record carries no journal-ref. Do not cite it as a conference paper | **Framework-coined as practised.** LangGraph's tutorial reduced the paper to "grade each doc, rewrite the query, add web search" and says so; every downstream implementation inherits that reduction | **Diverges on the mechanism that makes it corrective.** The paper's Incorrect action reaches *outside* the corpus (web search) and its refinement works on knowledge strips. The reference grades whole nodes with a prompted LLM (`corrective.py:307-319`, one call per chunk, up to ~30 per query, uncapped), has no three-way action, and its correction is "rewrite the query broader and re-ask the same index" (`corrective.py:62-109`). **Nothing is corrected.** `critique.py:117-127` also fabricates a grade from word overlap when the grader fails |
| **`contradiction-check`** | Asks whether the retrieved sources agree, and answers with agreement and conflict separated and cited | The phenomenon: Rongwu Xu, Zehan Qi, Zhijiang Guo, Cunxiang Wang, Hongru Wang, Yue Zhang, Wei Xu, *Knowledge Conflicts for LLMs: A Survey*, EMNLP 2024, pp. 8541-8565, arXiv:2403.08319 — "inter-context conflict". Closest published analogue: Vignesh Gokul, Srikanth Tenneti, Alwarappan Nakkiran, *Contradiction Detection in RAG Systems*, arXiv:2504.00180, 2025 (**postdates the reference** — parallel framing, not a source) | **Reference-coined** (`rag_consensus`). Not a paper, not a framework — searched LlamaIndex's fusion modes (RECIPROCAL_RANK, RELATIVE_SCORE, DIST_BASED_SCORE, SIMPLE) and LangChain's retrieval docs; nothing named "consensus" | **Different technique from what the name implies.** There is no sampling and no voting anywhere: `consensus.py:61-107` is one retrieval, one critic call, one generation. It detects disagreement **among retrieved sources**, not among sampled answers, and the reference's own metadata says so (`en.yaml:304`). `critique.py:158-166` reports `has_consensus=True` when the critique call fails — a disagreement detector that claims agreement when it cannot look |
| **`boolean-retrieval`** | Parses the query into Boolean operands, retrieves each independently, and combines the result sets by set algebra | Christopher D. Manning, Prabhakar Raghavan, Hinrich Schütze, *Introduction to Information Retrieval*, Ch. 1 "Boolean retrieval", Cambridge University Press, 2008. Modern evaluation: Chaitanya Malaviya, Peter Shaw, Ming-Wei Chang, Kenton Lee, Kristina Toutanova, *QUEST*, ACL 2023, arXiv:2305.11694; Zongmeng Zhang et al., *BoolQuestions: Does Dense Retrieval Understand Boolean Logic in Language?*, Findings of EMNLP 2024, pp. 2767-2779, arXiv:2411.12235 | **Literature (textbook).** Marked *named* rather than *introduced*: operational Boolean systems predate any single citable paper, and this catalogue deliberately asserts no origin paper for it | **Simplified, and one silent inversion.** The reference cites Manning Ch. 1 correctly (`boolean_decompose.py:19-21`). But the decomposition is a flat `(operator, list[str])` (`types.py:75-82`), so any compound query parses to `MIXED` and `MIXED` is handled as `OR` (`_retrieval_post.py:86-87`); **`AND` returns the union when the intersection is empty** (`_retrieval_post.py:78`), which is the logical opposite of what was asked and is indistinguishable to the caller; and XOR is advertised in five user-facing places and implemented in none |
| **`refine-on-uncertainty`** | Retrieves, drafts, and retrieves once more if the draft signals uncertainty | Zhengbao Jiang, Frank F. Xu, Luyu Gao, Zhiqing Sun, Qian Liu, Jane Dwivedi-Yu, Yiming Yang, Jamie Callan, Graham Neubig, *Active Retrieval Augmented Generation*, EMNLP 2023, pp. 7969-7992, arXiv:2305.06983 — the nearest published ancestor, and the reference does not cite it | **Framework-coined** (`rag_adaptive`; the "adaptive" / "router" vocabulary comes from LangGraph and LlamaIndex docs, not from the papers whose names it borrows) | **Diverges — the reflection mechanism is substring matching.** `adaptive.py:83-85` tests the draft against a nine-phrase localised list (`en.yaml:944-953`) with `str.__contains__`. FLARE uses token probabilities; Self-RAG uses trained reflection tokens. This fires on *hedging*, never on *unsupportedness*, and breaks silently under another language or system prompt. Capped at one extra round despite metadata calling it "iterative" |
| **`query-scorer`** + **`routing-policy`** *(two plugins)* | An LLM scores the query on named dimensions; a pure function maps those scores to a strategy | Soyeong Jeong et al., *Adaptive-RAG*, NAACL 2024, arXiv:2403.14403 — the route-by-query-complexity formulation. Related: Alex Mallen, Akari Asai, Victor Zhong, Rajarshi Das, Daniel Khashabi, Hannaneh Hajishirzi, *When Not to Trust Language Models*, ACL 2023, arXiv:2212.10511; Yile Wang, Peng Li, Maosong Sun, Yang Liu, *Self-Knowledge Guided Retrieval Augmentation*, Findings of EMNLP 2023, arXiv:2310.05002 | **Framework-coined** for "router"/"selector". `adaptive-rag` as a *name* is Jeong et al.'s and must be reserved for an implementation that trains a classifier | **Adaptive-RAG's shape, none of its method.** `RoutingScores` (`types.py:506-551`) carries exactly seven typed dimensions and every one is attached to the span (`router.py:129-142`) — genuinely good, genuinely rare, and the thing worth keeping. But `_select_strategy_from_scores` (`router.py:287-350`) is ten `if/elif` branches over constants nobody fit to anything, and it **cannot select `rag_adaptive` at all** — the strategy named "adaptive" is unreachable from the router named "adaptive". `_ROUTER_STRUCTURED_FALLBACK_EXCEPTIONS` (`router.py:44-56`) catches eleven types including bare `ValueError` and silently swaps in a different routing algorithm |

**Two conditional names, stated as conditions rather than preferences.**

- **`corrective`** is only honest if the plugin gains a *distinct knowledge action* — a second
  `Retriever` resolved by contract, not the same index re-queried. If Weft ships the reference's behaviour
  unchanged, the name is `graded-retrieval` and the word `corrective` stays free for a plugin that
  earns it. This is a design decision with a naming consequence, and `04` owns the decision.
- **`repack`** may only be registered with a `sides` method once `sides` does what Wang et al. define.
  Porting the name over the reference's ordering would launder a defect through a citation.

### 1.2 Index-path techniques

Phase 1 work. Listed here because they are techniques with origins, not because this file owns the
phase.

| Weft name | What it does | Origin | Name provenance | Reference |
|---|---|---|---|---|
| **`raptor`** *(mode: `collapsed` \| `traversal`)* | Recursively embeds, clusters and summarises chunks into a hierarchy, then retrieves over the whole tree or by descending it | Parth Sarthi, Salman Abdullah, Aditi Tuli, Shubh Khanna, Anna Goldie, Christopher D. Manning, *RAPTOR: Recursive Abstractive Processing for Tree-Organized Retrieval*, ICLR 2024, arXiv:2401.18059 | **Literature** — a proper noun with one paper and no competing meaning. Keep the acronym | **Structurally faithful, partly not the reference's code, and unparameterised where it matters.** Both retrieval modes are implemented (`strategies/raptor.py:22-40`, real top-down traversal at `:130-211`) — better than most ports. But the UMAP+GMM clustering (`a_prior_module.py:20-201`) is **the LangChain RAPTOR cookbook**, carried under an STX Next SPDX header; `RANDOM_SEED = 224` and the divider `### --- Our code below --- ###` survive verbatim while the cookbook's attribution header above them was dropped. The two knobs that decide the tree's whole shape — UMAP dim and the GMM probability threshold — are hard-coded at `a_prior_module.py:244-246`. **The genuinely reference-invented asset is the degrade-don't-crash contract** (`a_prior_module.py:354-466`), which is in neither the paper nor the cookbook |
| **`hypothetical-questions`** | At index time, generates the questions a chunk would answer and indexes them as retrievable nodes | Rodrigo Nogueira, Wei Yang, Jimmy Lin, Kyunghyun Cho, *Document Expansion by Query Prediction* (doc2query), arXiv:1904.08375, 2019 | **Framework-coined** ("Reverse HyDE" circulates in framework docs and blog posts). **No paper uses the term** — see §5 | **Correct technique, wrong citation.** `enhancers/reverse_hyde.py:25` cites `arXiv:2212.10496` — that is HyDE, a *query-time* technique that generates hypothetical *answers*. This does the opposite at index time. A plausible-looking reference attached to the wrong paper is exactly the failure this catalogue exists to catch |
| **`cross-encoder-rerank`** | Rescores first-stage candidates with a full-attention query-passage model and keeps the top *n* | Rodrigo Nogueira, Kyunghyun Cho, *Passage Re-ranking with BERT*, arXiv:1901.04085, 2019 (never formally published; the canonical citation). The architecture term: Samuel Humeau, Kurt Shuster, Marie-Anne Lachaux, Jason Weston, *Poly-encoders*, ICLR 2020, arXiv:1905.01969. Polish models: Sławomir Dadas, Małgorzata Grębowiec, *Assessing generalization capability of text ranking models in Polish*, presented at **ICAISC 2024**; Springer LNCS proceedings volume dated **2025**, pp. 37-49, DOI 10.1007/978-3-031-84353-2_4, arXiv:2402.14318. **Both years are stated deliberately** — conference 2024, proceedings 2025 — so a bibliography tool does not flag the mismatch as an error | **Literature** | **Right technique, no technique object.** `SentenceTransformerRerank` is constructed inline in two places (`retriever.py:731-734`, `fusion.py:139`) with divergent defaults; it is not registered, not swappable, not composable. `_get_or_create_reranker` (`retriever.py:48-67`) is a carefully written thread-safe model cache with **zero callers**. And `retriever.py:1042-1044` returns unranked `candidates[:top_n]` when the model failed to load — the caller cannot tell reranked from not |

### 1.3 Judge techniques

Phase 4 work. The naming problem here is the worst in the catalogue, because the borrowed name points
at a **library the reference never imported**.

`04` already records that RAGAS is not a dependency (`grep 'import ragas'` → 0; absent from
`pyproject.toml`). The catalogue's addition is that **the prefix is not merely unnecessary, it is
false in one case**, and that "RAGAS" names two different things which must never be cited as one:

- **The paper** — Shahul Es, Jithin James, Luis Espinosa-Anke, Steven Schockaert, *RAGAS: Automated
  Evaluation of Retrieval Augmented Generation*, EACL 2024 System Demonstrations, arXiv:2309.15217 —
  defines exactly **three** reference-free metrics: Faithfulness, Answer Relevance, Context Relevance.
- **The library** — has since added Context Recall and Factual Correctness and deprecated Context
  Relevance in its original form.

| Weft name | Reference name | Origin | Reference |
|---|---|---|---|
| **`answer-relevance`** | `answer_relevance` | Es et al., arXiv:2309.15217 | **Faithful** to the paper's algorithm, embedding step included |
| **`context-relevance`** | `document_relevance` (class `RagasContextRelevance`) | Es et al., arXiv:2309.15217 | **Faithful**, and the only one of six that computes its score in code (`ragas_context_relevance.py:117`). Registered under a name that contradicts its own class |
| **`faithfulness`** | `faithfulness` | Es et al., arXiv:2309.15217 | **Defective.** The paper decomposes then verifies then divides; the reference does it in one call and **reads the ratio off the model** (`ragas_faithfulness.py:105`) while the numerator and denominator sit unused two lines below |
| **`context-recall`** | `ragas_context_recall` | The RAGAS **library**, not the paper | Same self-scored arithmetic (`context_recall.py:107`) |
| **`answer-correctness`** | `ragas_answer_correctness` | The RAGAS **library**, not the paper | Reasonable reproduction of the library's weighted F1 + semantic score |
| **`answer-completeness`** | `ragas_answer_completeness` | **Nothing.** RAGAS has no completeness metric in the paper or in any version of the library | **Name provenance: False.** An invented metric wearing a borrowed name — a reader will go to the RAGAS docs to learn what the number means and find nothing |

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
| `reverse_hyde` | **Wrong citation in code** (`reverse_hyde.py:25` cites HyDE for a doc2query-shaped technique), and the label has no paper |
| `document_relevance` | Registers a **context**-relevance metric under a **document** name; the class and the registry disagree |
| `rag_consensus` | Names sampling-and-voting; implements contradiction detection. Keeping it burns `self-consistency` — the name Wang et al. (ICLR 2023, arXiv:2203.11171) fixed for the real technique — for a plugin that is not it |
| `rag_adaptive` | Two mechanisms share the word, **with no wiring between them**: the router cannot select the strategy. And `adaptive-rag` is a paper's name for a trained classifier |
| `rag_simple` | Names a single-pass baseline over a pipeline with ≥3 LLM calls and unbounded regeneration. An operator reads this name when deciding what to run in a loop |
| `sides` (repack method) | The name is Wang et al.'s; the ordering is not theirs. Porting the name without the algorithm launders a defect through a citation |

---

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
   ship over the reference's ordering.
5. **A composition is a pipeline, never a plugin.** `rag_complex` is HyDE plus repacking on the
   baseline skeleton. Registering the composition would put a name on something requirement 3 says is
   derivable data.
6. **Qualify a name that will have siblings.** `cross-encoder-rerank`, not `rerank` — Weft will want
   `llm-rerank` and `colbert-rerank`, and an unqualified name lets the first implementation seize the
   namespace.

### 2.2 Applied to all ten

| Reference name | Weft | Kind of change |
|---|---|---|
| `direct` | `no-retrieval` | Rename |
| `rag_simple` | `retrieve-then-generate` | Rename |
| `rag_complex` | **not a plugin** — `hyde` + `repack`, composed | Split; the composition becomes a named pipeline (`hyde-repack`) if a preset is wanted |
| `rag_adaptive` | `refine-on-uncertainty` | Rename, and the router half separates into `query-scorer` + `routing-policy` |
| `rag_multi_query` | `multi-query` + `reciprocal-rank-fusion` | Split — the fuser is reusable over hybrid retrieval, which is why the reference has two copies of it |
| `rag_iterative` | `iterative-retrieval` | Prefix drop |
| `rag_corrective` | `corrective` \| `graded-retrieval` | Prefix drop, name conditional on the implementation |
| `rag_consensus` | `contradiction-check` | Rename — the current name describes a technique the code does not implement |
| `rag_boolean` | `boolean-retrieval` | Rename |
| `rag_stepback` | `step-back` | Prefix drop, hyphen restored to match the literature |

### 2.3 Why the prefix has to go, on the reference's own evidence

The argument is usually "in a RAG engine, `rag_` carries zero bits". True, and weak — four characters
is not an argument. The stronger one is in the reference's registry:

**`direct` is the only one of the ten without the prefix**, because it is the only one that is not
RAG. So the prefix *was* carrying semantics — it silently marked "this retrieves" — and the moment a
plugin came along that did not retrieve, the convention broke rather than expressed it. A marker that
one member has to opt out of is not a namespace, it is an undeclared boolean field smuggled into a
string.

Weft cannot even have that field. Its registry is contract-scoped: a `Strategy` is registered as a
`Strategy`, so the contract already says what kind of thing the name refers to, and the prefix is
restating in a string what the registry knows as a type. That is the same failure mode `README.md`
opens with — one fact in two places, one of which cannot be checked.

The reference is inconsistent about it anyway: `rag_complex` but `reverse_hyde`; `ragas_context_recall`
but `faithfulness`. There is no convention to preserve.

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
parameterisable and composable by someone who did not write it*. Four of the techniques above are
welded in place in the reference — HyDE has no configuration and cannot run outside `rag_complex`, repack
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

### 3.4 Two cross-phase notes, raised rather than decided

**Phase 1.** `raptor` and `hypothetical-questions` are index-path techniques with no ledger line
naming them; `1.6` and `1.7` cover the ingest stage order and the cleaning chain, not these. Proposed:

```
- [ ] **1.11 ⚠** the tree builder's shape is configuration — the reduction dimension and the cluster-membership threshold are parameters rather than literals — and its degrade-don't-crash behaviour survives as a stated contract · owner `10` §1.2, the `raptor` row; `01` → requirement 6, second clause · turns on — · sha —
- [ ] **1.12 ⚠** index-time question generation ships under a name and a citation that match what it does · owner `10` §1.2, the `hypothetical-questions` row · turns on — · sha —
```

Both ⚠ for the reason every Phase 1 task is ⚠: the phase is blocked on G2 and its task list is a
hypothesis until G2 closes.

**Phase 4.** `4.2` says the metric suite ships *"with its four recorded defects fixed at the door"*.
This catalogue finds a fifth and a naming correction, both of which are `04`'s content to state, not
this file's:

- **A fifth defect** — four of six judges read the score off the model's own arithmetic
  (`ragas_faithfulness.py:105`, `context_recall.py:107`, `ragas_completeness.py:96`) while the
  numerator and denominator sit extracted and unused. `ragas_context_relevance.py:117` gets it right
  and is the pattern.
- **The `ragas_` prefix is false, not merely unnecessary.** `04` currently records that RAGAS is not a
  dependency. It should also record that `ragas_answer_completeness` is not a RAGAS metric under any
  version of the library — so the prefix is a provenance claim, and it is untrue.

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

- **`direct`** — searched LlamaIndex, LangChain and Haystack documentation for a no-retrieval routing
  mode, query-engine setting or component by that name. Found none. Treated as reference-coined;
  **unconfirmed as framework-coined**.
- **`rag_consensus`** — searched LlamaIndex's fusion modes and LangChain's retrieval docs; nothing
  named "consensus". Treated as reference-coined.
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
