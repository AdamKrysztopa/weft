# Reproducing the published baseline

This file ships inside `weft-reproduction-v*.tar.gz`, attached to every release. It assumes you
hold that archive and an installed `weft-rag`, and nothing else — no clone of this repository.

`docs/09-release.md` §5.2: *"Fails if reproducing the published number requires cloning."* This
page is the procedure that clause asks for. Every command and every transcript below was run as
written on 2026-09-14, and §3 and §4 again on 2026-09-21, from a directory outside the repository,
against wheels built from the tree.

**Which release.** The procedure needs `weft eval baseline` and a `weft eval compare` that reads a
baseline report, both added after `v2.6.0`. It also needs the fetcher, and `v2.6.0`'s archive
predates it: that asset was uploaded before the release job learned to copy `fetch_corpus.py`,
`wikitext.py` and this page. Use the archive and the `weft-rag` of one release, the first after
`v2.6.0` or later.

## What is in the archive

| | |
|---|---|
| `baselines/` | the published runs, one JSON each: the resolved pipeline stage by stage, the corpus identity, the active distribution set, and per-metric intervals over repeated passes |
| `questions/` | the question sets the metrics are scored against |
| `corpus-manifest.toml` | every corpus document named, with the sha256 that identifies it and the pinned revision that returns it |
| `fetch_corpus.py`, `wikitext.py` | turn that manifest into bytes. Standard library only, Python 3.11 or later |

**The corpus bytes are deliberately not here.** Some documents are published under publisher
copyright, so redistributing them is not this project's to do. The manifest is distributable, and
its names, digests and revision pins are what make the fetch reproducible byte-for-byte.

## 1. Materialise the corpus

```bash
python3 fetch_corpus.py --manifest corpus-manifest.toml fetch
python3 fetch_corpus.py --manifest corpus-manifest.toml verify
```

```text
corpus mrmr-v1: 25 documents — 19 verified, 0 fetched, 0 corrupt, 6 missing (6 of them operator-tier and therefore permitted)
```

The six `missing` documents are all `operator`-tier: named and checksummed so a local copy can be
verified, never fetched. The published baselines score the `fetch` tier alone, so this is the
expected outcome. A document whose pin now returns different bytes is reported `corrupt`, never
accepted.

## 2. Install, and give the store an empty collection

```bash
uv venv && uv pip install 'weft-rag[qdrant]'
docker run -d -p 6333:6333 qdrant/qdrant:v1.12.4
```

and a `weft.toml` in the directory you run from:

```toml
[packs.qdrant]
url = "http://localhost:6333"
collection = "weft_reproduction"
vector_size = 64
```

**The collection has to hold nothing else.** A passage from any document this run did not stage
changes every rank while still looking like ordinary retrieval, so `weft eval baseline` refuses the
run and names the passage. `vector_size = 64` is the `hash` embedder's width. The published
pipeline embeds with `hash`, so reproducing it needs no vendor account.

## 3. Take the baseline

```bash
weft eval baseline corpus-manifest.toml questions --out mine.json
```

```text
{"path":"mine.json","report":{"recorded_at":"2026-09-21T12:13:28+00:00","corpus_name":"mrmr-v1","tiers":["fetch"],"extractor":"text", …
```

It prints the report it wrote. With no other flags this is the published measurement: the `fetch`
tier, three repetitions, `--top-k 10`, depths 5 and 10, and the shipped `baseline` pipeline
(`text` → `fixed-size` → `hash` → `qdrant`). It indexes once, then retrieves and scores every
question three times, all in one process.

## 4. Judge it against the published baseline

> **Judge against `baselines/8854c33f71ea-2026-09-21.json`.** The earlier
> `8854c33f71ea-2026-08-25.json` recorded the hash embedder's stage with no configuration, and a
> `weft-rag` newer than 2.7.0 writes its default `dimension: 64` into the record, so that file
> refuses the comparison: `stage 'embed' config differs ({} vs {'dimension': 64})`. The vectors
> and every metric are unchanged; only the record is. The refusal is the reproduction check
> working, and the re-take is its answer.

```bash
weft eval compare baselines/8854c33f71ea-2026-09-21.json mine.json
```

```text
'mine.json' reproduces 'baselines/8854c33f71ea-2026-09-21.json': 12 of 12 metric(s) inside the intervals 'baselines/8854c33f71ea-2026-09-21.json' recorded
  document-mrr@10: 0.26875 inside [0.26875, 0.26875]
  document-mrr@5: 0.25 inside [0.25, 0.25]
  document-ndcg@10: 0.3275977762880931 inside [0.3275977762880931, 0.3275977762880931]
  document-ndcg@5: 0.2819344072873667 inside [0.2819344072873667, 0.2819344072873667]
  document-recall@10: 0.5416666666666666 inside [0.5416666666666666, 0.5416666666666666]
  document-recall@5: 0.4166666666666667 inside [0.4166666666666667, 0.4166666666666667]
  quote-mrr@10: 0.0 inside [0.0, 0.0]
  quote-mrr@5: 0.0 inside [0.0, 0.0]
  quote-ndcg@10: 0.0 inside [0.0, 0.0]
  quote-ndcg@5: 0.0 inside [0.0, 0.0]
  quote-recall@10: 0.0 inside [0.0, 0.0]
  quote-recall@5: 0.0 inside [0.0, 0.0]
```

**Every metric inside the interval the published run's own repetitions spanned** is a reproduction.
No tolerance is chosen anywhere: the interval is what three passes produced, and this pipeline is
deterministic, so every interval has zero width. An *installation differs* line, when a later
release prints one, is not a failure: it reports a plugin shipping from another distribution or
at a newer declared contract version. Anything that changed retrieval would have moved a metric.

A metric outside its interval, or one your run did not measure, exits `1` and names each:

```text
$ weft eval compare baselines/8854c33f71ea-2026-09-21.json shifted.json
'shifted.json' does not reproduce 'baselines/8854c33f71ea-2026-09-21.json': document-recall@10: 0.5 is outside [0.5416666666666666, 0.5416666666666666]
```

A run over a different corpus, stage configuration, model version, retrieval depth or question set
is refused with exit `1`, naming every difference, rather than compared.
