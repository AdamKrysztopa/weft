# Reproducing the published baseline

This file ships inside `weft-reproduction-v*.tar.gz`, attached to every release. It assumes you
hold that archive and nothing else — no clone of this repository.

`docs/09-release.md` §5.2: *"Fails if reproducing the published number requires cloning."* This
page is what that clause costs, and it is honest about the part that still does.

## What is in the archive

| | |
|---|---|
| `baselines/` | the published runs, one JSON each: the resolved pipeline stage by stage, the corpus identity, the active distribution set, and per-metric aggregates over repeated passes |
| `questions/` | the question sets the metrics are scored against, one file per tier |
| `corpus-manifest.toml` | every corpus document named, with the sha256 that identifies it and the pinned revision that returns it |
| `fetch_corpus.py`, `wikitext.py` | turn that manifest into bytes. Standard library only — nothing to install |

**The corpus bytes are deliberately not here.** Some documents are published under publisher
copyright, so redistributing them is not this project's to do. What is distributable is the
manifest: names, digests and version pins, which is what makes the fetch reproducible
byte-for-byte rather than merely repeatable.

## Materialise the corpus

```bash
python fetch_corpus.py --manifest corpus-manifest.toml fetch
python fetch_corpus.py --manifest corpus-manifest.toml verify
```

Documents land beside the manifest, at the paths it declares. Run against the `v2.6.0` archive
this retrieves **19 of 25** and reports six as `missing`; all six are `operator`-tier — published
under copyright, named and checksummed so a local copy can be *verified* and never fetched — and
the summary says so. That is the expected outcome, not a partial failure: the baselines below
score the `fetch` tier alone.

`verify` re-checks what is on disk against the digests. A document whose pin returns different
bytes than it did when the manifest was written is reported as `corrupt` rather than accepted,
which is the whole reason the pins are revisions rather than titles.

## Read the baseline before running anything

Every fact you need to match is in the JSON, and reading it beats trusting this page:

- `record.resolved_pipeline.stages` — every stage, its plugin **and** its config. The `v2.6.0`
  baselines run `text` → `fixed-size` (512/50) → `hash` → `qdrant`. The `hash` embedder needs no
  account, so reproducing these costs no credentials; `qdrant` means you need one running.
- `repeats`, `retrieval_depth`, `questions` — the shape of the pass.
- `metrics[]` — each metric's `values` across those repeats, with `mean`, `low` and `high`. **The
  interval is part of the published number.** A run landing inside it has reproduced the baseline;
  one landing outside has found something.

## Run it

```bash
uv pip install 'weft-rag[qdrant]'
export WEFT_DATABASE_URL="postgresql://weft:weft@localhost:5433/weft"
weft eval run <pipeline> <corpus directory> --questions questions/fetch.toml
```

`weft eval run --help` names every flag; `weft pipeline list` names every pipeline the install
offers.

## What you cannot do from this archive yet, and what it costs

**Two of the artefacts the published baselines were produced by are not here**, and saying so is
cheaper than letting you find out:

- the **runner** that produced them — it composes the pipeline the records call `baseline`,
  repeats the pass and writes the JSON, and it lives in this project's `eval/` directory;
- a **comparison command that takes a baseline file**. `weft eval compare` takes two *run ids*
  from your own `runs/` directory and diffs them; it has no argument for a published baseline.

So the comparison this archive supports today is by eye: run the pipeline whose stages the record
names, then check your metric against that metric's `low`/`high`. That is a real reproduction of
the *number* and not yet a reproduction of the *procedure*, and the difference is tracked as a
carried repair rather than papered over here.
