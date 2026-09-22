# Queryable from the first batch — Phase 43, Exit A

Measured 2026-09-22 from the `weft-rag 2.10.0` wheel, installed with `[openai,qdrant,pdf]` into a
virtual environment outside the repository. Host: Apple Silicon, 12 cores, 24 GB, 1-minute load
3.6–4.5 throughout.

**Setup.** 100 arXiv PDFs (243 MB; the first 100 by name of Open RAGBench's corpus), indexed with
`weft index <dir> --pipeline index-openai-large-pdf`. That document is `pdf-text` extraction, the
default chunker, `text-embedding-3-large` and pgvector
(`eval/experiments/pipelines/index-openai-large-pdf.yaml`), run at the default batch of 25 and the
default 4 concurrent embedding requests. The Qdrant run swaps only the store
(`index-openai-large-pdf-qdrant.yaml`).

While indexing, a second shell asks two questions in turn, every 5 s:
`weft ask --pipeline retrieve-then-generate`, answered by `gpt-5.6-luna`.
- `question_first.txt` is answered by a paper in the first batch.
- `question_last.txt` is answered by a paper in the last batch.

Each run used a fresh database, dropped after. The harness is `run_exit_a.sh`, its reader is
`analyse_exit_a.py`, and every run's numbers are one line of `exit-a-summary.jsonl`.

| clock | pgvector, median of 5 (min–max) | Qdrant, 1 run |
|---|---|---|
| first document queryable | **30.0 s** (29.8–31.0) | 25.4 s |
| first correct, cited answer | **34.2 s** (34.0–43.4) | 27.2 s |
| all 100 queryable | **127.2 s** (126.4–127.8) | 107.8 s |
| `weft ask` p95, during indexing | 3.87 s (3.48–4.25) | 4.37 s |
| `weft ask` p95, after indexing | 3.65 s (3.42–4.04) | 3.98 s |

**What it shows:**
- A question about the first batch gets a correct, cited answer about 34 s after `weft index`
  starts, while the other 75 documents are still being embedded.
- A question about a document not yet indexed is answered *"the corpus does not answer this — N
  sources are not yet indexed"*, not with a guess. Once its batch lands, it is answered.
- Asking during indexing costs no latency the measurement can see: p95 during is 0.93–1.11× p95
  after, across all six runs.

The first-answer clock moves in steps of the ask loop (about 8.5 s), which is why one run reads
43.4 s.

**Before Phase 43,** the same 100 PDFs through the same document took 226.8 s. That run used one
batch holding the whole corpus and embedded sequentially, so nothing was queryable until the end
(one run, Phase 43's opening measurement).

**Not measured here:** a cold page cache; any corpus larger than 100 documents for these clocks;
another machine.
