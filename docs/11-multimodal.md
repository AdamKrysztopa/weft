# 11 — Multimodal

**What is known about PDFs, tables, figures and vision; what Weft ships as packs; the
decisions the owner must take; where each half lands in the phase script; and what is deliberately
not built.**

This document owns the multimodal capability family and nothing else. It does not restate `01`'s
phases, `02`'s contracts, `03`'s command surface, `07`'s cost model, `08`'s manual
assignments, `09`'s validation prerequisite, `10`'s naming rule or `build-ledger.md`'s task state. It
links, and where it has content those documents own, it hands that content over in *Where this goes*
rather than keeping a second copy.

**No phase assignment names multimodal work.** Multimodal *subjects* appear in `docs/` in about
thirty places — `01`:164 (tables and figures are atomic and bypass the parser), `01`:292 (the vision
`asyncio.run`), `02`:39 (scanned versus digital PDFs), `02`:60 (*"Vision and text models were
correctly split and that judgement holds"*), `02`:326, `02`:848, `05`:47, `05`:49,
`05`:369, and more — but not one of them is a phase assignment, and no ledger task names the family.
That is an **omission, not a decision**, and the plan says so in three places without noticing:

- `weft-kernel` already ships `MediaType.IMAGE` and `MediaType.TABLE`
  (`packages/weft-kernel/src/weft_kernel/payload/media_type.py:17-18`) — a closed core vocabulary
  naming two things nothing in the tree can produce.
- G5 built `__transient__` *because of* a real scar: a base64-encoded image blob riding on every node
  through several processing stages until an explicit scrub step removed it (`02` §1 → *The payload
  model*).
- `01` → Phase 1 **Lift** already commits to building two ingest stages that exist only to handle
  tables and figures as atomic elements: one that routes atomic nodes — tables and figures, and
  nothing else — past the chunker, and one that scrubs a transient image-blob key after storage.
  Ledger **1.6** already requires both, for a capability the plan never mentions.

---

## 1. What is known, and what is not

Some of what follows rests on code that was out of bounds by instruction and was never read; rows
resting on that boundary are marked **Unreadable** below, which is a finding about what nobody on
this project has seen, not a gap to fill by guessing.

**What this section owns.** §1 is the *argument* — why the multimodal surface examined here does not
amount to a foundation to build from, evidenced well enough that the conclusion can be checked.

### 1.1 The decisive fact

**Nothing examined here embeds an image.** The embedding interface surveyed has exactly two methods,
`get_text_embedding` and `get_text_embedding_batch`, both taking `str`. No image-embedding method,
image embedder, second index or image vector column exists anywhere in the codebase or its tests.

Both multimodal paths examined are therefore **image → text → embed**. A figure's vector comes from
its caption, else its OCR text, else a synthesised label such as `f'Figure on page {n}'`; a query
image becomes a description appended to the query. A blob URI reaches citations for display and is
never an input to retrieval.

**This decides §2.** No multimodal embedder contract is needed, and none should be published — see
D2.

### 1.2 The measured surface

| Area | Measured this session | Note |
|---|---|---|
| PDF and document parsing | **27 files / 5,083 lines** | |
| — of which the primary layout-parser wrapper | 859 lines | Perhaps 120 lines of that are asset; the rest is wrapper around a fast-moving library |
| — of which ten Office/web/data-format extractors | **1,299 lines** | `docx` 207, `html` 247, `xlsx` 173, `csv` 143, `odt` 125, `ods` 109, `json` 97, `pptx` 74, `txt` 67, `markdown` 57 |
| — of which the GPU-detection module | 183 lines | `torch.cuda.is_available()` around a process-global mutation |
| — of which the `.doc`-format extractor | 216 lines | Printable-strings scavenging of a 1997 binary format |
| Figures, blobs and vision | **1,157 lines** | Spread across the figure pipeline, a figure-asset repository, a blob port, a query-image enricher, a vision-description enhancer, and smaller supporting modules |
| Tables | **2,737 lines** | A table-ingest package (**6 files / 1,412 lines**: a pipeline, validation, node-building, schema-matching, a small init, and schema identity), plus a table port, a table augmenter, and a table-RAG model module |
| — of which port surface with no body | ~1,000 lines | Zero in-library implementers |

**There is no multimodal algorithm anywhere in this surface** — no fusion across modalities, no
cross-modal scoring, no modality-aware reranking. The expensive knowledge is about sixty lines' worth
of scars, three design decisions and one experiment.

### 1.3 What is actually worth carrying

Nine items. Each is a *design, an ordering, a measurement or a scar* — none is code to port.

1. **The atomic rule.** An extracted table or figure must not be re-chunked. It is a genuine ordering
   constraint between two packs' stages and the reason stage 0 exists.
2. **The caption ladder.** A figure's searchable text is caption → OCR text → synthesised label.
   Weft keeps the first two rungs and refuses the third — see §2.4.
3. **The four Docling converter flags and their comment** — `images_scale = 2.0`,
   `generate_page_images`, `generate_picture_images`, `do_picture_classification`, with the recorded
   reason *"Must be set to keep images in memory, otherwise DocumentConverter destroys them."* Miss
   one and figures vanish with no error. Nobody derives that from Docling's own documentation alone.
4. **The OCR heuristic.** Average characters per page under 100 means the PDF is a scan. Its defect
   travels with it: it full-text-extracts with pdfplumber *before every parse* and on any exception
   defaults to OCR enabled, the expensive branch.
5. **The non-AGPL backend decision.** **The asset is the decision, not any particular wording of
   it** — prefer PDF backends that are not AGPL, because an AGPL fast path in an MIT engine is a
   licence problem a rebuild re-litigates and gets wrong. Weft writes its own sentence for this.
6. **Two-level schema matching with two widen caps** — canonical sorted-hash matching, then Jaccard
   similarity, then a deterministic tie-break, with two separate widen caps. The problem — the same
   table extracted from forty PDFs producing forty near-identical schemas — is only visible at corpus
   scale, so a prototype never finds it. **Two** caps rather than one, because a single per-event cap
   lets a schema widen forever two columns at a time.
7. **The continuation problem and its four containment mechanisms.** A multi-page PDF table losing
   its header row is common and silently corrupting: the corpus fills with one-row schemas and nobody
   notices.
8. **Write-verify-rollback, the ghost guard.** Count the materialised rows and, if zero, delete both
   the registry entry and the vector nodes — because a silently failed materialisation leaves vector
   nodes that retrieve fine and return nothing.
9. **The recall spike as a method, not as code.** Before building multimodal retrieval, prove the
   cheap architecture works. Three details make it a template: the verdict bands change the *product*
   rather than the metric (`RED (<30%)` reads *"image-paste ships as search by description"*); it
   loads the **production** caption prompt so experiment and product cannot drift; and its ground
   truth is a model-assigned category, weak and cheap, and the write-up says so. `01`'s V1–V3
   prerequisite is the same instrument pointed at images.

### 1.4 The scars — defects that must travel with the ideas

| Scar |
|---|
| The blob rode on every node through several ingest stages before a late scrub step removed it, and per-strategy copies of node metadata were never scrubbed — so N configured retrieval strategies meant N copies of the base64 string and N vision-LLM calls on the same image. This is money, and it is the strongest available argument that transience must be a type |
| The parsing cache serialised figures excluding the image bytes from its cache key, so a cache **miss** returned figures with bytes and a **hit** returned the same figures with the image data cleared — and the describer then silently did nothing on re-index |
| A plain field assignment **destroyed the caption** the document supplied when a generated description overwrote it |
| A `schema` caption-prompt variant was authored, reviewed, translated into two languages, and is **unreachable** — nothing anywhere sets the prompt-selection key to it. A free-text key is how a reviewed asset becomes dead |
| A documented master switch for the whole multimodal feature has **zero readers**, while its sibling flag for table capability *is* read |
| One port declared a **sync** `ingest` method while its implementation was `async def` and its consumer called it synchronously — `@runtime_checkable` checks method presence, not colour. The cleanest available example for G6 |
| A public concurrency-limit setting was dead — the semaphore it configured was never acquired and the actual work ran as a serial loop — while the setting was still public API and asserted correct by a test |
| A table augmenter's score threshold was compared against a score already computed by reciprocal-rank fusion: summing `1/(k+rank)` across sub-queries with `rrf_k=60` gives a single-query maximum of ≈0.0164 and an N-sub-query maximum of N/61, against a default threshold of 0.7 — every candidate was filtered out and semantic selection was silently replaced by a hardcoded fallback |
| Deterministic visual-intent detection matched substrings without word boundaries, so `graph` fired on `paragraph`; and the mere presence of an attached image alone set visual intent, so *attaching* an image changed routing. Its one sibling, a table-intent detector, was **also** a bare marker test — there was no context-token requirement anywhere |
| Seven bare `except Exception` in one 578-line file, and the method returned an `int`, so a table that failed to index and one that indexed cleanly were indistinguishable to the caller |
| Four of five table→markdown renderers rolled their own conversion, with three different escaping policies; only three of the five shared one helper, which escaped nothing. A cell containing `\|` broke the table for every XLSX, ODS and ODT extraction and for every CSV header row — and that rendered text is what gets embedded |
| The evaluation suite modelled modality as first-class and then measured none of it: filtering functions for modality and source type existed, `source ∈ {text, text-image, text-table, text-table-image}` was stored on every result, and the result-aggregation step never sliced by it — while three call sites hardcoded images out of the corpus entirely |
| **A recall spike's result was unrecoverable** — its report and cache were written to an uncommitted temp directory. The decision the whole feature rested on was lost, and the feature shipped anyway. And **the query caption was not a query**: the index caption and the query caption came from the same prompt and the same image, so it measured prompt stability, not the asymmetry between how a user describes an image and how the index does. Real recall is very likely lower |

Two findings for calibration, because they show extension points can look real without being usable:

- **One dispatch map was live**, not a dead snapshot — read at one clear call site. The finding is
  narrower and still damning: it has **zero readers outside its own module**, so the one structure
  shaped like an extension point is one nobody extends. Mutating it *would* work.
- **One string comparison was the only place a backend name was branched on by value** (an
  `== 'docling'` test giving one named backend behaviour no third party could obtain), though the
  attribute itself was read in about eighty places — so "the only consumer" would have been the wrong
  conclusion.

### 1.5 What is not covered

Said plainly, because it is the owner's judgement and the survey confirms it: **there is not enough
here to build multimodal from.**

- No image embedding of any kind (§1.1), so no evidence about the architecture D2 must choose.
- No page-image retrieval, no late interaction, no vector multiplicity concept at all.
- No hybrid sparse+dense retrieval evidence for table-heavy corpora.
- No modality-sliced measurement — the suite that could have produced one hardcodes images out.
- No usable result from the one experiment that would have decided the architecture.
- No table serialisation choice: the grid is destroyed inside the cleaning pipeline, so nothing
  downstream can choose a representation.

What is available amounts to the shape of the problem, four expensive scars, and a method. Everything
about *what to build* comes from current practice, §3 and §7 — and the two must be kept visibly
apart, because they were verified by different means.

### 1.6 What is unreadable

| Unreadable | Consequence |
|---|---|
| Every concrete blob adapter, the image-serving endpoint, a `supports_vision` capability flag, the sync figure-pipeline adapter, every vision-LLM implementation — all in a deployment layer out of bounds by instruction | *"There is a substantial blob capability"* would rest on code nobody here has read. `supports_vision` is already a **blocking** open question |
| SQL guardrails, the row store, NL→SQL, the schema analyzer — all in the same out-of-bounds deployment layer | **"8 blocked node types, 15-function blocklist" cannot be repeated as fact.** The one in-bounds test exercises **five** statement types and **seven** functions. And a SQL self-correction service exists in that layer — something that rewrites rejected SQL and presumably resubmits it, which is exactly where a guardrail bypass would live |

The in-bounds contract shape *is* legible and is the transferable idea: two functions, not one.
`validate_select` answers *"is this one read-only statement free of dangerous functions"*;
`validate_table_refs(stmt, allowed)` answers *"does it touch only the tables this request may
touch"* — the tenant-isolation guarantee, enforced on a parsed AST.

---

## 2. The design, as packs

**Nothing here enters `weft-kernel`**, and the falsifiable form of G1 applies cleanly: this design can
be described without the kernel learning a single new word. `MediaType.IMAGE` and `MediaType.TABLE`
already exist and are core-field vocabulary under G5's admission rule, not capabilities. There is no
`MultimodalConfig`, no image cap, no model name and no pixel budget anywhere near the passport — a
comparable design put two of ten passport fields there and one of them had zero readers.

### 2.1 The packs

| Pack | Contract | Exists? | What it is |
|---|---|---|---|
| **`weft-extract`** | publishes `Extractor` | **Contract exists, shipped** | Unchanged. A figure is a `Node` with `media_type=IMAGE`; a table is a `Node` with `media_type=TABLE`. **No new contract is needed for either.** What must grow is the *accept set*: `discover_source_docs` filters on one pack's module constant `EXTENSIONS` (`packages/weft-rag/src/weft_extract/text.py:40`, read at `:98`) and `weft-cli` imports that function by name (`packages/weft-rag/src/weft_cli/ingest.py:36,80`). Correct and Phase-0-scoped when this was written; the moment a second extractor pack ships, `.pdf` becomes **silently invisible to ingest**. Fail-closed, so better than a fail-open default — the same missing derivation, and exactly what fitness function 5 exists to hold. **This happened, exactly as predicted, when `weft-pdf` shipped at ledger 2.27, and the derivation was built as part of repairing it** — `weft_extract.accept.claimed_extensions` over `weft_kernel.registry.Registry.names_for`, read by `weft_cli.ingest.run_index`. The line numbers cited above are the ones as of writing and have since moved |
| **`weft-extract-pdf`** | implements `Extractor`; publishes a `TableGrid` and a `BlobRef` ext model, and the **one** table→text serialiser | **New pack, existing contract** | Three plugins against one contract: `pdf-text`, `pdf-layout`, `vlm-parse`. See D3 |
| **`weft-blob`** | publishes **`BlobStore`** | **New pack, new contract — and the contract is a decision, not an implementation detail** | Weft's first non-`Stage` service contract, reached through the passport's `require()` like `TokenSink`. It becomes a **hard prerequisite for the whole design** under D1's recommendation, which is why it gets the same "argue it, do not commit it" treatment `RowStore` gets below. See §4, G1-a |
| **`weft-vision`** | publishes **`Describer`** | **New pack, new contract** | One async method: bytes + media type + instruction → text. Named for the medium, not the model class — the same contract covers audio transcription later. Two stages consume it at opposite ends of the pipeline, which is the argument for one service contract rather than an indexing-only enhancer. `02` §1 already endorses the split from the text LLM port (`:60`), for a contract nobody is scheduled to publish. **Depends on an LLM pack existing** — ledger **2.10** places the prompt layer, the cascade, model strings and the `LLMError` taxonomy in Phase 2; it names **no distributions**, so this document invents none |
| **`weft-embed`** | publishes `Embedder` | **Contract exists, shipped** | A page-image or figure embedder is a **plugin under the shipped contract**, not a new contract. `Embedder` is `Stage[Sequence[Node], Sequence[Node]]` (`packages/weft-rag/src/weft_embed/contract.py:49`) and says nothing about text. Publishing a `MultimodalEmbedder` would be a second way to do what one contract already does — `01` requirement 1 failing on its own terms |
| **`weft-tables`** | publishes `SchemaResolver`; consumes `RowStore` / `StructuredSearch` | **Deferred behind a new gate** | D9. One of its four blockers is still an open gate (G7); the G2 one cleared 2026-08-16 |

**Contracts deliberately not published**, each with its reason: no `MultimodalEmbedder` (above); no
`PageRenderer` (rendering a page to pixels is something a PDF extractor does, not a capability anyone
would swap independently — a contract with one plausible implementation is a guess, `01` →
*Runtime shape*); no `LateInteractionSearch` (D5 — a **G4** question, and the recommendation is not to
open it); no `FigureAssetsRepository` equivalent (§6).

### 2.2 The two new contracts, as a proposal for `02` §1

`02` §1 owns contract definitions. What follows is the **proposal**, not a second definition; the
authoritative text is the edit listed in *Where this goes*.

```python
# weft-blob — a service, not a stage. No pipeline position.
class BlobStore(Protocol):
    async def put(self, key: str, data: bytes, media_type: str) -> BlobUri: ...
    async def open(self, uri: BlobUri) -> bytes: ...
    async def delete_prefix(self, prefix: str) -> int: ...


# weft-vision — a service, not a stage. Two stages consume it, at opposite pipeline ends.
class Describer(Protocol):
    async def describe(self, data: bytes, media_type: str, instruction: str) -> Outcome[str]: ...
```

**Blob keys are derived, never allocated:** `{tenant_id}/{source_id}/{ordinal}.{ext}`. `tenant_id` is
on the passport (`packages/weft-kernel/src/weft_kernel/context.py`), `source_id` is on `SourceDoc`
(`packages/weft-rag/src/weft_extract/contract.py:89`), and `ordinal` is the same one the G5 digest
already requires an extractor to assign distinctly. Cascade delete is then
`delete_prefix(f"{tenant_id}/{source_id}/")` — one call, no ledger, no dedup table. This is forced
rather than chosen: G4's `delete_source` returns `Removed` **counts** and deliberately never a
materialised cascade (`packages/weft-rag/src/weft_store/contract.py:150-158`), so a figure pack
cannot learn URIs after the fact. **Derivable keys are the only design the settled contract admits**,
and they delete the whole `FigureAssetsRepository` component.

A file-upload-and-serve half of a comparable design is dropped entirely: Weft has no HTTP tier.

### 2.3 Plugin names

Per `10` §2.1 — bare, lowercase, kebab-case; name the mechanism; qualify a name that will have
siblings; never take a name that promises more than the code does.

| Name | Rule |
|---|---|
| `pdf-text` | Rule 6 — text-layer extraction will have siblings |
| `pdf-layout` | Rules 2 and 6. Not `docling`: the library is a config value, and the first implementation must not seize the namespace |
| `vlm-parse` | Rule 6, and the strongest case for it here — `dots.ocr` renamed itself `dots.mocr` in 2026 (MIT, 3B, HF `rednote-hilab/dots.mocr`). A name that moved once will move again. The plugin names the role; the model is `with: model:` |
| `describe-figure` | Rules 1 and 2 |
| `describe-query-image` | Rule 6 — same `Describer`, opposite pipeline end |
| `page-image-embed` | Rule 6. Deferred, name claimed now |
| `pool-patch-embeddings` | Deferred. Named so a future implementation cannot be called `colpali` |

**Reserved and not to be taken** (`10` §4 exists for exactly this): `colpali`, `colqwen`,
`late-interaction`, `maxsim`, `visual-citation`, `grounded-answer`. The first four are model or method
names the literature has fixed. The last two are rule 4: ViDoRe V3 (arXiv:2601.08620) measures visual
grounding F1 at **0.602 human, 0.089 Qwen3-VL, 0.065 Gemini 3 Pro**. A plugin named `grounded-answer`
today would claim a capability the field delivers at roughly one-seventh of human. Measure it; do not
name it.

### 2.4 The ingest path, end to end, for a PDF with a table and a chart

`weft index ./annual-report.pdf`, in Weft stages and payload types.

**0 · The source.** `weft-cli` produces one `SourceDoc(source_id, uri, content=bytes)`.
`SourceDoc.content` is `bytes` because the extractor decides how to decode. Nothing has a `Node` yet.

**1 · `extract` — `pdf-layout`, an `Extractor`.** Runs the layout library inside `asyncio.to_thread`
(G6; FF7(b) catches it if the author forgets — D6). The vendor's document tree is translated into
Weft-owned ext models and **never appears in a signature or an ext model's field types**, per `02`
§1's rule against vendor SDK types at the boundary. That translation is a permanent maintained
surface and it is the price of the extractor being swappable at all; all three rungs must land in the
same shape or `chunk` cannot be written once.

Out of one page:

| Node | `media_type` | `content` | `ext` |
|---|---|---|---|
| root | `TEXT` | the document title | `SyntheticOrigin` (kernel-owned) — `Node.synthetic(sources={source_id})` |
| N prose nodes | `TEXT` | section text | `PageSpan` (page, reading-order ordinal) — `derive()` from the root |
| 1 table node | `TABLE` | the **index-form** serialisation | `TableGrid` (rows, headers, spans, caption, page, bbox) + `Atomic` |
| 1 chart node | `IMAGE` | the caption the document supplied → else the OCR text beneath it → else **`NothingToProduce` for that node** | `PageSpan` + `Atomic` + `BlobRef(uri)` |

Three of those are decisions, not descriptions:

- **`TableGrid` is not transient.** A cell grid is kilobytes of JSONB, which is what `ext` is for.
  Only *bytes* are a transience problem. A comparable design destroyed the grid inside its cleaning
  pipeline, which is why nothing downstream could choose a representation; Weft keeps the grid and
  makes serialisation a stage.
- **A figure with neither caption nor OCR text does not enter the index.** Not a template string.
  Synthesised labels such as `f'Figure on page {n}'` or a hardcoded `'Figure from DOCX'` are
  measurable index poisoning — identical strings collide as a block at retrieval time, and no
  metadata-exclusion setting was ever configured to prevent it.
  Under `Outcome` the honest answer is `NothingToProduce`.
- **The pixels are written to the blob store by the extractor, and a non-transient `BlobRef` goes in
  `ext`.** The bytes never enter the payload, so the seam behaviour D1 identifies is not merely
  tolerated — it is unexercised.

**2 · `chunk`.** An atomic node passes the chunker unsplit, and **the chunker does not have to know
that**. G2 settled this as *applicability*: a stage declares what it operates on, the runner routes
everything else past it untouched, so a chunker in a *different distribution* that has never heard of
tables still leaves them whole. This is the cross-pack constraint stage 0 existed to enforce, moved
off the author's memory and onto the seam.

**3 · `clean`.** Text processors in a learned order. **Tables leave this pipeline** — a
`TableLinearizer`-shaped component is text-layout repair for multi-column scans despite its name,
never produces a `Table`, and never touches Table-RAG; it is already filed with the cleaning pack and
stays there.

**4 · `describe` — `describe-figure` *(Phase 2, optional stage)*.** `requires` `BlobRef`, `provides`
`FigureDescription`. Reads the bytes back through `ctx.require(BlobStore).open(uri)`, calls
`ctx.require(Describer)`, and **augments** the node's content — caption *and* description — rather
than replacing it. Because it is a stage, removing it is a `remove:` in a derived pipeline, not a
boolean. That is why there is no `enabled` flag anywhere in this design.

**5 · `embed`.** For `TEXT` and `TABLE` nodes, embeds `content`. For an `IMAGE` node, embeds `content`
— caption plus description. If and only if D2's measurement says otherwise, a second plugin under the
same `Embedder` contract reads the bytes back through `BlobStore` and embeds pixels into the same
space. **One contract, two plugins, a pipeline edit between them.**

**6 · `store`.** `NodeStore.run` → `add` → the runner owns `flush`. One `Vector` per node; pgvector
holds them; `SourceRecord` records `uri`, `content_hash` and `pipeline`.

**Query time.** `Retriever` → `Sequence[Scored[Node]]` → `Generator`. A retrieved `IMAGE` node's
`content` is its caption plus description, and its `BlobRef` is **durable** — so a vision-capable
generator can `BlobStore.open(uri)` and put the pixels in the prompt. That is what D1's recommendation
buys and what neither alternative provides.

**Delete.** `delete_source(sid)` cascades over `lineage.sources` — the table node, the chart node and
every prose node go together, because all derive from the root. The blobs go with `delete_prefix`.
Nothing survives its document.

---

## 3. The decisions the owner must make

Each is a question, **one** recommendation, and what it costs. None is a menu.

### D1 — Where does `__transient__` strip? *(Blocking. Nothing below is buildable first.)*

**Question.** `02` §1 → *The payload model* says a transient namespace is stripped *"before any
`Store` sees the node"* (`docs/02-extension-model.md:323-324`). `weft_kernel.seam` strips it before the
result leaves *any* stage's `wrap` (`packages/weft-kernel/src/weft_kernel/seam.py:36-39`, `:133`,
`:202-234`). Which is the specification?

For Phase 0 the two are indistinguishable. For multimodal they are not: **a `__transient__` ext model
cannot carry image bytes from an extractor stage to a describer stage, because the bytes die at the
extractor's own seam.** The obvious plan — "the bytes ride in a transient namespace, exactly as G5
intended" — does not work as written.

**Recommendation: neither statement changes. Bytes leave the payload entirely.** An extractor writes
pixels to a `BlobStore` and puts a **non-transient** `BlobRef` in `ext`. The seam keeps its current,
stricter behaviour; `02` §1's prose is amended to say what the seam does; and `__transient__` remains
what G5 built it for — a guard against a blob reaching JSONB — rather than becoming a transport
mechanism it was never designed to be.

**Why not the alternatives.** *One merged extract-and-describe stage* is cheapest and costs `01`
requirement 6: the describer stops being swappable or omittable, which is the same failure as
selecting behaviour by comparing a plugin's name to a literal string, only with better manners.
*Narrowing the strip to the store boundary* is a kernel change that weakens a guarantee to buy
in-memory blob carriage — precisely the four-pass cost §1.4 measures. And neither makes pixels
available at query time.

**Cost.** A new contract and a new pack before any figure work — `weft-blob`, three methods, one
local-filesystem plugin, estimated ~150 lines. Plus one unwritten line in `02` §1 (§4, G1-a). This is
most likely a **narrowing** of the kind `02` §1 has already recorded twice for Phase 0 steps 7 and 8,
not a reopen — but that is the owner's judgement, and if the answer is that G5 decided something it
cannot support, its decision-log row goes to **Reopened** with a date and reason, per `README.md` →
*Protocol*. **Nothing else in this document should be built first.**

### D2 — Text-after-description, or true multimodal embedding?

**Question.** Is a figure's vector computed from a caption, or from its pixels?

**Recommendation: ship caption-and-embed, and only that.** No pixel embedder is built until the
measurement in rank 2 of §6 says it is worth it; if it does, the pixel embedder arrives as a **second
plugin under the shipped `Embedder` contract**, and the composition becomes one text node and one
image node per figure fused at query time by `reciprocal-rank-fusion` — a plugin `10` §1.1 already
names — at a **2× index cost**. One architecture, with a stated and measured trigger for its second
step. **Not two vectors per figure by default.**

**The evidence, corrected.** Native multimodal retrieval beats LLM-summary-then-embed by **+13pp
mAP@5 and +11pp nDCG@5** on a financial earnings benchmark (arXiv:2511.16654 — verified; the abstract
also gives 32%/20% relative, and these are the absolute figures). ViDoRe V3 reports **59.8**
(ColEmbed-3B-v2) against **51.0** (Qwen3-8B) nDCG@10 for visual over textual retrievers
(arXiv:2601.08620 — verified). Those say the pixel path wins where it is measured.

**But the top-scoring pipeline on ViDoRe V3 at release was hybrid text *and* visual** —
jina-v4-textual + zerank-2 **together with** ColEmbed-3B-v2 — not text-only, as an earlier draft of
this document claimed. **Its margin is thin exactly where it matters: 54.7% accuracy on hard
queries, against 52.1% for the strongest textual baseline and 54.5% for the strongest visual one**
(arXiv:2601.08620 — verified). A 0.2pp win over visual-alone is not a mandate for a second index. That is the finding that shapes the recommendation: the
best measured system uses both, which is why the second plugin must remain buildable and why the
composition, if it is built, is two nodes fused rather than one node re-embedded. It is also why the
default is the cheap half: caption-and-embed needs no new contract, no GPU and no model download, and
the measurement is what decides whether the expensive half earns its 2×.

**And the measurement comes first.** §1.3 item 9 leaves the template and two defects to fix at the
door: the result was written to an uncommitted temp directory and is unrecoverable, and the query
caption came from the same prompt and the same image as the index caption, so it measured prompt
stability rather than the asymmetry it claimed to measure.

**Cost.** One measurement day against the V1 corpus, before the describer stage is built. The risk it
accepts: a red verdict means Phase 2 grows a model dependency it did not plan for. That is a cheap way
to find out.

### D3 — VLM parsing, or a layout library?

**Question.** Does `weft-extract-pdf` drive a classical layout stack or a document vision-language
model?

**Recommendation: a layout library is the default, a VLM is a config value on the same plugin surface,
and the pack ships a three-rung chain rather than one parser.** `pdf-text` (pypdfium2 or LiteParse —
Apache-2.0, no weights, no network) → `pdf-layout` (Docling: layout + table structure + OCR fallback)
→ `vlm-parse` (a document VLM, reached by config). A born-digital PDF stops at rung one; a scanned
page falls through; a page of dense charts is escalated by explicit configuration. That composition is
data in a pipeline file, so a user who wrote none of it can reorder or remove a rung.

**Docling is the default, and not because it is the most accurate.** It is not the leader: Datalab's
own comparison table puts *Marker — balanced (GPU)* at **76.0%** on olmOCR-bench against Docling's
**50.3%**, and MinerU2.5-Pro's changelog reports OmniDocBench v1.6 at **95.26 / 95.39 / 95.30**
(medium / high / VLM). Both are vendor-run comparisons; treat the ordering as indicative and the gap
as real. Three of the four selection criteria for a small MIT project are not accuracy:

1. **Licence.** Verified at source: Docling's `LICENSE` is the MIT License, *"Copyright (c) 2024
   International Business Machines"*. Weights are CDLA-Permissive-2.0 / Apache-2.0. No revenue
   trigger, no attribution obligation, no field-of-use clause.
2. **Governance.** An LF AI & Data Foundation project with a published technical report
   (arXiv:2408.09869), not one vendor's funnel to a paid API.
3. **Deployability.** `pip install docling` and nothing else — no `poppler-utils`, no `tesseract`, no
   `libreoffice`. That is what disqualifies Unstructured under G4's *probe at `register()` and
   register the class that actually works* rule: `import unstructured` succeeds while `tesseract` is
   absent, so registration would declare a capability whose implementation is not there. **Fitness
   function 5's exact defect, arriving through a door that did not previously exist.**
4. **Shape.** It is the only option shipping a typed document tree with tables as *cell structure* and
   figures as first-class items — which is what an `Extractor -> Sequence[Node]` boundary needs in
   order to translate into a Weft-owned ext model at all.

The accuracy gap closes **without changing packs**: `vlm-parse` points at granite-docling-258M
(Apache-2.0), a vLLM endpoint running PaddleOCR-VL (Apache-2.0), or dots.mocr (MIT, 3B). Model choice
as a config value is requirement 6 working as intended.

**Cost.** What carries over is **design, not code** — items 3, 4 and 5 of §1.3 plus three render
constants (`RENDER_SCALE = 300/72`, `optimize_mode='lcd'`, `draw_annots=True`). **Do not budget "port
the layout extractor"**: 859 lines measured for perhaps 120 lines of value wrapped around a
fast-moving library. Throughput figures for every parser in this document are **unconfirmed** — see
§9.

### D4 — What is refused outright?

**Question.** Which parsers and models must not ship, at any level, including as optional extras?

**Recommendation, in order of how badly it would bite:**

1. **`pymupdf4llm` / PyMuPDF — AGPL-3.0 or a paid Artifex licence. Not a dependency, not an optional
   extra, not an example.** A user running `pip install weft-extract-pdf[fast]` does not read
   Artifex's terms. The one refusal with no nuance.
2. **MinerU as a default.** Verified at source: `LICENSE.md` is Apache 2.0 with additional conditions
   requiring a separate commercial licence above **100M MAU or USD 20M monthly revenue**, and
   requiring anyone providing an online service to *"clearly and prominently indicate, in the relevant
   product or service interface or in publicly available documentation, that MinerU is used"*. **That
   attribution obligation propagates into the UI of every product built on Weft.** Legitimate only as
   an explicitly opted-in separate pack where an operator accepts the terms knowingly.
3. **Chandra 2 as a shipped option.** Verified at source: weights are modified OpenRAIL-M, free below
   **$2M** funding/revenue, and *"cannot be used competitively with our API"*. A document-parsing pack
   inside a RAG engine is arguably competitive with a document-parsing API. Note it as the open-weights
   accuracy ceiling (olmOCR-bench **85.8 ± 0.8**, verified) and leave the plugin surface open.
4. **Marker's weights** — modified AI-Pubs OpenRAIL-M, $5M threshold; the code is Apache-2.0 and the
   thing it downloads is not. A threshold licence is a decision the owner takes consciously and cannot
   delegate to a `pip install`.
5. **Non-commercial embedding weights** — jina-clip-v2 (CC BY-NC-4.0), jina-embeddings-v4 (Qwen
   Research License), NVIDIA `llama-nemoretriever-colembed` (NVIDIA Non-Commercial). A first-party pack
   defaulting to any of these hands every commercial user a problem they did not choose.
6. **A forced-visual fallback tier.** Refused rather than deferred. One design lists *any* ten
   figures — the listing call takes no query argument — builds stubs whose entire content is
   `f'Stored figure from {file_id} (index {n})'` at `score=0.0`, prepends them, and instructs the
   model to cite them. The guarantee is met and the answer is worse than if it had not been; a
   telemetry span recording that the fallback fired is itself the admission. Under `Outcome`, *"this
   collection has figures but none match"* is `NothingToProduce`.
7. **A GPU-detection module.** 183 lines measured, wrapping `torch.cuda.is_available()` around
   `torch.set_default_device()` — a **process-global mutation from a library module, triggered as a
   side effect of the first document parse**. Device policy is a configuration field, never a shared
   service.

**Cost of these refusals:** roughly 20 points of olmOCR-bench against the open-weights ceiling, and one
AGPL fast path. Both are recoverable by an operator who opts in deliberately; neither is recoverable
once shipped as a default.

### D5 — Is visual retrieval in scope at all?

**Question.** Should Weft retrieve by embedding page images rather than extracted text?

**Recommendation: single-vector page-image retrieval is in scope as an optional Phase 2+ plugin,
conditional on D2's measurement. Multi-vector late interaction is out of scope, its names are reserved
now, and the design must not foreclose it.**

Single-vector visual retrieval — the Document Screenshot Embedding paradigm (Ma, Lin, Li, Chen, Lin,
arXiv:2406.11251, EMNLP 2024 — verified) — **fits Weft's contracts exactly as written**: one vector
per node, produced outside the store, written to `Node.embedding`, retrieved by an unchanged
`search_vector`. `MediaType.IMAGE` already exists. pgvector is sufficient. It costs nothing settled.

Multi-vector late interaction does not fit, and §4's G4-a states it properly. The argument is
**storage, not quality**: Nemotron ColEmbed V2's Table 5 (arXiv:2602.03992) compares both families
from the same weights and finds **54.07 vs 60.52** nDCG@10 at 4B and **56.91 vs 62.24** at 8B — about
5–6 points absolute in late interaction's favour. Against that, the same paper's Table 6: 1M pages at
fp16 costs **5,897.5 GB** for the 8B late-interaction model against **3.8 GB** for a 1B single-vector
one — a factor of about 1,550. Even ColPali's much leaner 128-dim vectors are on the order of
hundreds of GB per million pages. **Five points is not worth three orders of magnitude for a project
whose declared floor is pgvector.**

*(An earlier draft clinched this with "Qwen3-VL-Embedding-8B reports ViDoRe v2 69.9 against
ColNomic-7B's 62.7 and llama-nemoretriever-colembed-3b's 63.5". That number is not on the model card —
the card reports 78.3 on MMEB-V2 VisDoc OOD — and the two comparators could not be sourced. The claim
is dropped; the recommendation rests on the two verified tables above and does not need it.)*

**Cost.** A page-render stage and one embedder plugin, if D2's measurement says so. If late
interaction is ever wanted, MUVERA (arXiv:2405.19504) is the escape hatch that keeps the floor in the
game — a Fixed Dimensional Encoding is *one* vector whose inner product approximates MaxSim, computed
outside the store by an ordinary pack, with MaxSim reranking in the retriever where G4 says fusion
belongs. Its dimensional specifics are **unconfirmed** (§9) and must be re-sourced before anyone
designs against them.

### D6 — How does a blocking parser live inside G6?

**Question.** Every mature local parser is synchronous, CPU- or GPU-bound, and runs for seconds to
minutes per document. `asyncio.run` appears once in the tree, at the CLI.

**Recommendation: `asyncio.to_thread` at the plugin boundary, with the cancellation weakening written
down explicitly, and one HTTP-based extractor built early as the reference implementation.**

This is not a G6 conflict — G6 anticipates exactly this and installs a blocking-call detector at the
registration seam (FF7(b)) precisely so the obligation is machine-checked rather than
author-remembered. What *is* a genuine weakening and must be recorded rather than discovered: **none
of these libraries is cancellable mid-document.** `asyncio.to_thread` cannot interrupt the worker;
cancelling the awaiting task leaves the thread running to completion, holding GPU memory and a pool
slot. `CancelledError` reaching the caller untouched is satisfiable — the *resource* is not released
when it does. A cancelled `weft index` over a 500-page PDF therefore honours cancellation at document
granularity at best. Either the extractor runs out of process (killable) or the guarantee is
documented as best-effort at the extraction stage. **Documented, not silent.**

The reference-implementation argument stands separately: an HTTP-based parser is the **only** extractor
in this survey that is natively async and natively cancellable, because `httpx.AsyncClient` genuinely
is both. Building one early proves the `Extractor` contract is async-*shaped* rather than
async-*painted* — even though it must not be the default (D7).

**Cost.** One documented weakening, and a second extractor plugin whose value is architectural rather
than functional.

### D7 — Does a plugin declare that it sends document content off-premises?

**Question.** Hosted parsers send whole documents; hosted embedders send page images; Docling's own
picture-description API options warn that the data goes to a remote provider. G3 settled trust for
**plugin code** and has no notion of data egress, and nothing lets an operator refuse it centrally.

**Recommendation: documented, not enforced — and given a decision-log row so the absence is a recorded
choice rather than an oversight.** G3's settled threat model is *installed-and-ambient, not
malicious*; egress is a different threat model, and bolting an enforcement surface onto G3 would answer
a question G3 did not ask. But for a RAG engine whose likely corpora are internal documents, silence
is worse than a stated limitation.

**Cost.** A decision-log row and a paragraph in the operations manual (`08`). If it is ever enforced,
that is a new gate, not a G3 amendment.

### D8 — What does the evaluation prerequisite have to gain?

**Question.** V1–V3 are already Phase 2 prerequisites (`09` §4.3; ledger 2.1–2.3). What breaks when
the corpus contains images and tables?

**Recommendation: three clauses, and one of them is a corpus obligation no public benchmark can
satisfy.**

1. **A metric result carries the modality of the query that produced it, and the reporter slices by
   it.** Without it a multimodal regression hides inside a text mean. A comparable evaluation suite
   stored `source` on every result, never sliced by it, and hardcoded images out at three call sites
   — so a run against image queries reported what looked like a retrieval failure.
2. **Retrieval and generation are two baselines with two intervals, not one.** V3's reproduction rule
   — every metric inside the recorded interval — becomes unfalsifiable for retrieval if judge noise
   dominates the run. arXiv:2607.10240 measures evaluator choice *alone* moving ST-VQA scores by
   **+7.5 to +10.8 points** (verified; the same paper shows ~zero movement on ChartQA-Machine, so the
   effect is task-dependent and must not be generalised). A deterministic retrieval baseline records a
   near-zero-width interval, which `09` §4.3 already says is correct and strict.
3. **V1's non-English clause cannot be satisfied by any public multimodal corpus.** ViDoRe V3's
   documents are English or French, with queries translated to en/fr/es/de/it/pt and **no Polish**
   (paper §3.4.4 — verified). JinaVDR, MIRACL-VISION and VisR-Bench contain no Polish either. V1's
   *stated reason* for the clause is that Polish retrieval is shipped product under requirement 6.
   French satisfies the letter; **the reason requires a Weft-built Polish slice**, or requirement 6's
   Polish claim is untested for multimodal and the manual must say so.

**Corpus recommendation:** ViDoRe V3's eight public datasets (~26,000 pages, 3,099 queries, graded
qrels, human bounding boxes, human reference answers — all verified) as the published baseline;
ViDoRe V2's `economics_reports_v2` (CC-BY-3.0, 452 pages, 232 queries, 55.1 MB — verified) as V5's
credential-free CI subset; plus a ~50-document Weft slice supplying the three things no public set
can — Polish, non-PDF formats, and unanswerable questions (V2 requires them; ViDoRe V3 has none).
**ViDoRe V3's own annotation licence is unconfirmed** — the dataset repo is gated and the paper says
only "a commercially permissive license". **Pin it before this is written into `09`.**

**Licences, corrected from an earlier draft:**

- **MIRACL-VISION is `cc-by-sa-4.0`, not non-commercial.** The previous "refuse the data"
  recommendation rested on an NC clause that does not exist. **Re-decided: accept it for evaluation.**
  Running a benchmark and publishing numbers is not distributing a derivative of the dataset, so
  ShareAlike does not reach Weft's MIT code; Weft vendors no benchmark data in any case (V1 already
  requires a pinned, checksummed fetch). The only live obligation is that **a redistributed modified
  subset would itself have to be BY-SA** — so do not build one into a shipped artefact.
- **MMLongBench-Doc's data is CC BY-NC 4.0** (code Apache-2.0), **not BY-NC-ND.** The "ND blocks the
  derivative subset V5 requires" half of the argument is void — BY-NC permits derivatives. **The NC
  half stands and is sufficient**: an MIT engine's commercially usable baseline cannot rest on
  non-commercial data. Refuse it as data, borrow the design — its **22.5%** unanswerable share,
  evidence-source labelling and format-dependent scoring are the closest match to V2 in the
  literature.
- **OmniDocBench's data is research-only** (code Apache-2.0). Refuse the data; the metric family
  (TEDS, edit distance) is the part Weft needs.

**Cost.** *Not derived, and therefore not stated as a figure.* An earlier draft asserted $40–180 per
generation-and-judge pass, $200–900 for a five-repeat baseline, $20–80 batched, with no token count,
no per-page cost and no model named. Those numbers are withdrawn. What is known: **retrieval-only
repeats are effectively free once the corpus is indexed**, which is the second argument for splitting
the two baselines; and the embedding side *is* derivable from verified list prices (§7). The
generation-and-judge cost must be derived — pages × tokens per page × the chosen model's price — and
recorded in V5 as `09` already requires, not guessed here.

### D9 — Tables: node/row split, with SQL, or neither?

**Question.** 2,737 lines of table capability were measured in a comparable codebase, of which
~1,000 is a port surface with zero in-library implementers and the security-critical half sits in a
deployment layer nobody on this project may read.

**Recommendation: neither, yet — and the reason is gates, not size.** Defer behind a new gate; when it
opens, ship **the node/row split without SQL**.

Four blockers, **one of them still an open gate** — blocker 2 cleared when G2 settled 2026-08-16:

1. It needs two capability protocols — `RowStore` (the data the node does not carry) and
   `StructuredSearch` (guarded query) — added to a family **G4** closed. Both are additive rather than
   in tension with the derived-capability rule, but **adding a tier to a settled family is a decision,
   not an implementation detail**, and settling it inside a commit is exactly what `README.md` →
   *Protocol* exists to prevent.
2. ~~Its ingest half is a branch inside an ingest pipeline — derivation semantics, **G2, open**.~~
   **Cleared 2026-08-16.** G2 settled that there is no branch: a stage declares what it operates on
   and the runner routes the rest past it, so the table path is stages whose applicability includes
   tables. This blocker no longer holds.
3. Its retrieval half is post-retrieval augmentation — close to the canonical case **G7, open**,
   exists to decide.
4. Its execution half is unreadable (§1.6). A security boundary carried on trust is worse than no
   boundary, and a plan that budgets for it sight-unseen will be wrong about its size.

**On text-to-SQL over PDF-extracted tables: build program-of-thought over one retrieved table's
`TableGrid` instead** (DuckDB MIT, pandas BSD-3) — same questions answered, nothing escapes the node
model, no schema to maintain, no new container. The argument is structural and does not need a
benchmark: a table scraped out of a PDF has no keys, no types and inconsistent headers; no public
benchmark measures that path at all; and the data would sit outside the `Node` model where
`delete_source` cannot reach it, which is a cascade-delete hole in the highest-stakes domain for
tables. *(An earlier draft supported this with Arctic-Text2SQL figures — 71.83% on BIRD, ~21% on
Spider 2.0. The paper exists (arXiv:2505.20315, Arctic-Text2SQL-R1) but neither number could be found
in it, and Spider 2.0 is not among its listed benchmarks. Both are withdrawn; the argument above
stands without them.)* Park the guardrail design with **sqlglot** named (MIT, zero required
dependencies, 30.17.0 — version verified) for when a `Retriever` over a genuine warehouse arrives, and
note that sqlglot is a transpiler, not a validator, so an **allowlist** over the AST is required
rather than a blocklist.

**Placement.** After Phase 5, not before it: Phase 5 is the independence test, and a pack that needs
two new store capabilities and a new gate is the worst possible subject for *"built by someone who
never touches core"*.

---

## 4. Gate questions

**A settled gate is reopened by argument, never by a commit.** Each item is written as the question its
gate would have to reopen for. Where the recommendation is *do not reopen*, that is said.

### G5 — settled

**G5-a.** *"Does `__transient__` mean 'stripped before any `Store` sees the node' (`02` §1's prose) or
'stripped at every stage seam' (`seam.py:202-234`)? A multimodal pipeline needs the difference,
because a describer must read what an extractor produced."*
→ **Recommend: not a reopen.** D1's answer needs no change to the seam and no change to what
`__transient__` guarantees; it needs one sentence in `02` §1 stating what the seam already does — a
**narrowing**, in the form `02` §1 has recorded twice for Phase 0 steps 7 and 8. It becomes a reopen
only if the owner chooses to narrow the strip to the store boundary instead, which weakens a settled
guarantee.

**G5-b.** *"What is the `content` of an image node, given that `content` is a required `str` and feeds
the identity digest?"*
→ **Recommend: not a reopen, but state the answer once**, because every pack author will otherwise
guess differently and three of the four candidate answers break something settled. Base64 in `content`
writes multi-MB strings into the store and `__transient__` does not apply to `content`, so stage 4.5's
scar reappears one field over. A file path or URI binds the id to where the file sits on disk, so
re-indexing from a different directory produces different ids and re-index stops being idempotent. A
caption binds every node id to whichever model captioned it — reintroducing through the front door
exactly the coupling `02` §1 avoided by excluding `embedding` from the digest. **The answer is caption
→ OCR text → `NothingToProduce`**: source-derived, stable, and it never fabricates. A consequence to
record rather than discover: `ordinal` saves the id from colliding across siblings **only if the
extractor assigns distinct ordinals**, which becomes a stated obligation on any image extractor.

**G5-c.** *"Does a resolved pipeline's identity include a parser's model version? A VLM's output for
the same page is not byte-stable across sampling, model version or inference backend, so re-parsing an
unchanged file produces a wholly different node set."*
→ **Recommend: not a reopen.** `SourceRecord.content_hash` rescues the common case and
`SourceRecord.pipeline` is the natural home for the parser's identity — **but only if the resolved
pipeline's identity includes the model version, not just the plugin name.** Without that, `weft index`
cannot honestly say *"already indexed, by a different pipeline"*. Ledger **1.19**.

### G4 — settled

**G4-a.** *"Does the store contract family gain a `LateInteractionSearch` tier —
`search_late_interaction(vecs, top_k, filter)` — given that `Node.embedding` is one `Vector`,
`search_vector` takes one vector, and pgvector (the declared floor) has no multi-vector type and no
MaxSim operator?"*
→ **Recommend: do not open it.** Three reasons in order of weight. (1) `01` → *Runtime shape* requires
a contract to be satisfiable by more than one backend before it is trusted, and names pgvector +
Qdrant as the over-fitting guard; **a tier only Qdrant can satisfy inverts that guard.** (2) The
storage argument in D5, and it is the number that decides this gate: **1M pages at fp16 costs
5,897.5 GB for the 8B late-interaction model against 3.8 GB for a 1B single-vector one**
(arXiv:2602.03992 Table 6 — verified), for the ~5–6 nDCG@10 points Table 5 measures between the two
families from the same weights. (3) The only Postgres-native
implementation is **VectorChord** (current release `pg18-v1.1.1`), dual **AGPLv3 / Elastic License
v2** — and the nuance that decides whether that is even acceptable is that it is a *server-side
Postgres extension reached over SQL*, so `weft-store` links nothing and Weft stays MIT; the obligation
lands on whoever runs the database. That makes it an **operator** decision, documented in plain words,
never an innocuous optional extra.

**Two things to get right, because getting them wrong sends the reopening to the wrong gate.** First,
**G4's "stores never embed" is *not* the obstacle and must not be cited as one** — late-interaction
vectors, pooled vectors and MUVERA encodings are all produced outside the store by an ordinary pack
and handed over already computed. The obstacles are the *signature* (G4) and `Node.embedding` being
singular (G5). Second, no production system indexes MaxSim in one call; every one is two-stage
(pooled prefetch, then exact rerank), which maps cleanly onto Weft's `Retriever` + `VectorSearch`
split. **Any future design assuming a single indexed MaxSim call is wrong.**

**G4-b.** *"Where is 'this store holds vectors of dimension d' checked? pgvector indexes at most 2,000
dimensions for `vector` and 4,000 for `halfvec`, and a multimodal pipeline mixing a text embedder and
an image embedder is the first normal case of two dimensionalities in one pipeline."*
→ **Recommend: an additive check, in the spirit G4 already set — but this is an amendment to a
document a settled gate owns, and whether it is additive is the owner's call, not this document's to
assert.** G4 requires a retriever's missing capability to fail at resolution naming the store, the
capability and the backends that provide it; a 3,072-dim vector discovering at `INSERT` time that the
index refuses it is the same defect class. **Where the check lives matters and must be named:** in the
store pack's `register()` probe and a pack-side resolution validator — **never** in
`weft_kernel.runner.resolve` (`packages/weft-kernel/src/weft_kernel/runner.py:275`), which is the only
"pipeline load" in the tree today and which must not learn the words *embedding dimension*. Ledger
**2.32**. Numbers that will bite: Gemini Embedding 2 defaults to 3072, Qwen3-VL-Embedding-8B to 4096,
jina-embeddings-v4 to 2048 (right at the edge), Cohere Embed 4 to 1536, voyage-multimodal-3.5 to 1024,
SigLIP 2 so400m to 1152. Every oversized model supports Matryoshka truncation, so this is solvable —
but the resolution must be a **declared pack setting checked at load**, not a runtime surprise.

**G4-c.** *"Is `lineage.parents` a validated, filterable field path?"* Table-parent-to-row expansion
(§6 rank 3) needs to fetch a table node's row children. `02` §1 does not say the reverse lookup is
supported. → **Recommend: yes — `lineage.parents` is a validated, filterable field path, and the
filter AST gains one operator over it.** Reverse lineage is already derivable (G5 derives `sources`
from parents), so this exposes a fact the payload model holds rather than adding one; a store that
cannot filter on it falls back to fetching parents by id, which is correct but N+1. Cheap to settle
now, expensive once a second store exists and the tier has to be retrofitted twice. An amendment to
G4's owned document, flagged as such rather than assumed.

### G2 — **settled 2026-08-16.** All three questions answered; none of them cost this design anything.

**G2-a.** *"Does `embed` run as a stage before `store`, or inside the store?"* **A stage** — and it
never became G2's choice to make, because G4 already forbids a store to embed. `06`'s minimal
reversible choice becomes permanent. **The pixel-embedding path stays buildable as designed**, and
the stage reaching a `BlobStore` is an ordinary `ctx.require`.

**G2-b.** *"Can one pack's stage declare a property that another pack's stage in a different
distribution must honour?"* **Yes**, and the mechanism is `intact` / `destroys` — namespaced property
markers published by whichever pack publishes the contract, declared on the plugin class and read at
the seam, with `destroys` mandatory. See `02` §3, *Ordering constraints*.

**G2-c.** *"Is a branch inside an ingest pipeline — a rung selected conditionally, or a table path
taken only for `TABLE` nodes — derivation semantics or something else?"* **Neither: there is no
branch.** A stage declares what it operates on and the runner routes everything else past it
untouched, so "the table path" is simply the stages whose applicability includes tables, and the
pipeline stays one straight line with one resolved order. This is also how the atomic rule is
enforced — a third-party chunker that has never heard of tables still leaves an atomic table unsplit,
because the seam does it rather than the author remembering to. The three-rung extractor chain is a
separate mechanism and unaffected: `fallback:` on a stage, tried in order until one produces.

### G7 — open

*"Is post-retrieval augmentation — pulling a table's rows in after retrieval matched its
schema-preview node — an extension point, an event, or a stage?"* One of the two open gates behind D9.

### G9 — open, and touched by D3

*"When a pack wraps a vendor library whose option surface grows every release, is exposing a new
vendor option a pack version bump, and what does that mean for a published contract's version?"* D3's
recommendation (below, under *Requirement 6*) treats an unsupported vendor option as a pack version
bump. **That is a versioning answer, and G9 owns versioning.** Flagged rather than defaulted, per
`CLAUDE.md`.

### G3 — settled

**G3-a.** *"May a plugin declare that it transmits document content off-premises, and may an operator
refuse it centrally?"*
→ **Recommend: do not reopen; record as documented-not-enforced with a decision-log row.** D7 states
the argument.

### G1 — settled, and holding

Nothing here enters the kernel; every contract is published by the pack that owns it. Two pressures
worth checking explicitly as this is built:

**G1-a — the one genuine gap, and it is why `weft-blob` is a decision rather than a detail.**
`ctx.require(Describer)` and `ctx.require(BlobStore)` resolve capabilities the kernel must not name.
The passport's `require()` is kernel-owned and the contract it resolves is not, which is correct — and
`TokenSink` is the settled precedent from G6. But `02` §1 documents the registration seam against
**stages**, so **whether span wrapping, error attribution, transient stripping and blocking-call
detection apply to a *service* contract is unwritten.** This is the first case where a first-party
pack resolves another first-party pack's capability mid-pipeline, and a new top-level service contract
that the payload model depends on deserves the same *"this is a decision"* sentence `RowStore` gets.
One line in `02` §1, argued before `weft-blob` ships.

**G1-b.** No `multimodal_config` on the passport, ever. All of it — image caps, model names, batch
sizes, pixel budgets — is pack configuration under the `packs:` namespace.

### Fitness function 5 — has no test file today, and this is its first real subject

`tests/architecture/` holds FF0, 1, 3, 7, 8 and 9. FF5 (*"every declared capability resolves"*,
`01` → *Fitness functions*) has none — correct for Phase 0, and triggered by a second extractor pack
rather than by a date.

*"Docling, every VLM path and every local embedder fetch weights from Hugging Face on first use, not
at install. `register()` can prove the import works; it cannot prove the weights are present without
network I/O in a synchronous registration path — and it must not download hundreds of MB at import
time. So is a missing weight a registration failure, a `weft plugins doctor` finding, or a run-time
failure?"*
→ **Recommend: a doctor finding.** A cheap local cache-path check needs no network, so `register()`
still registers the class that actually works for the optional-*dependency* case — which is what FF5
is really about — while a missing *weight*, a data problem rather than a capability problem, is what
`weft plugins doctor` (`03`) exists to report. **A registration that does network I/O is the wrong
answer regardless of the outcome.**

### Runtime shape — a carve-out to write now rather than discover

`01` → *Runtime shape* reads as an absolute: *"the only thing that gets a container is the database."*
Every CPU-only path in this design keeps that promise — `pdf-text`, the default layout pipeline,
caption-and-embed against a hosted embedder. But the practical way to serve a VLM parser is a model
server, which is a second container. **Write the carve-out now: optional model servers are the
operator's infrastructure, not Weft's.** That is not a contradiction of the decision; it is the
sentence that keeps the decision true when the multimodal roadmap lands.

### Requirement 6 — one genuine tension, stated rather than resolved by default

A layout library's PDF pipeline options alone carry OCR engine selection, table-structure mode, cell
matching, image scale, page range, several enrichment toggles and nested option objects. Wrapping it
and exposing three fields is the black box requirement 6 forbids. Mirroring the whole surface into a
Weft Pydantic model is a maintenance obligation ratcheting with every release. The tempting escape — a
passthrough `extra: dict` — stares directly at `02` §1's *"widening to `Any` is not a fix"*.
→ **Recommend: no `extra` dict. Expose the *decisions* in a small typed model** — OCR on/off, table
fidelity versus speed, describe figures or not, classical versus VLM — and treat an unsupported vendor
option as a pack version bump **(a G9 question, flagged above)**. A typed model of four decisions is
composable by someone who did not write it; a dict of forty vendor keys is not, and it is the same
free-text-key failure in a bigger costume — a key authored, reviewed, translated into two languages,
and unreachable because nothing ever set it. **Prompt variant selection is a typed field on the
pack's registration model** (`02` §3's `with:` rule), never a free-text locale key.

**Where the prompts live.** A describer pack's entire behaviour *is* a prompt, which makes it the first
plausible pack that forces the pack-owned-prompt question already flagged as a G1 blocker: a prompt
loader that resolves locales relative to its own package means a pack cannot ship translations.
**Weft's prompts are authored fresh** — a caption prompt examined for its *requirements* (name the
visualisation type; enumerate visible labels, axes and components; state relationships and trends;
state what the figure is for; constrain the output to one paragraph, because bullet output embeds
badly), and those requirements transfer in a sentence. The second variant's existence is the
transferable observation: one caption style does not fit both a bar chart and a circuit diagram.

---

## 5. Phase placement, and the ledger

```
D1 · the transient boundary  ─────────────────► blocks everything below
        │
        ├── blob store, PDF extraction, atomic rule ──► Phase 1
        │        └── figures and tables as nodes ─────► Phase 1  (caption/OCR text; no model call)
        │
        ├── the recall measurement (D2) ──────────────► Phase 2, before the describer
        ├── describer, query-side enricher ───────────► Phase 2  (a model call; needs the LLM pack, ledger 2.10)
        ├── modality-sliced evaluation ───────────────► Phase 2 prerequisite V1–V3; Phase 4 re-runs it as V6
        ├── page-image embedding (D5, conditional) ───► Phase 2+, only if D2's measurement says so
        │
        └── tables ───────────────────────────────────► Phase 7, behind its own gate
```

### Phase 1, in `01`'s four-line format — the two lines that change

> - **Lift:** the ingestion stage order (**chunk before clean**, plus stage 0
>   separating atomic nodes and stage 4.5 scrubbing transient metadata; see the Data-row note above),
>   and specifically the reason stage 4.5 exists. **Both stages exist to handle extracted tables and
>   figures — stage 0 routes them past the chunker, stage 4.5 removes the image blob — so this phase
>   also lands the first non-text extractor, the blob store the bytes go to, and the atomic-node rule
>   that gives stage 0 something to separate. `11-multimodal.md` §2.4 owns the ingest path and §3 D3
>   owns the parser choice. What carries over from prior parsing work is design, not code — the four
>   converter flags with their comment, the <100-characters-per-page OCR heuristic, the cross-page
>   rejoin, the three render constants and the non-AGPL backend decision; `11` §6 states plainly that
>   "port the layout extractor" is not a budget line.** Cleaning processors, *with* their ordering
>   rationale — and with a 243-word Polish fused-word exception set, **reconstructed rather than
>   copied**, ranked as one of the more valuable transferable ideas found.
> - **Exit:** driving use case A works — a `specific` pipeline derived from `base` with KeyBERT
>   inserted after chunking, expressed as configuration, with no change to core and no copy of the
>   parent. **Proposed addition, for `01` to accept or refuse: fitness function 5 is wired and green**
>   — the ingest accept set is the union of what actually registered, so a second extractor pack makes
>   its formats visible with no list to edit. *(Adding a criterion to a settled phase exit is `01`'s
>   decision, not `11`'s. It is proposed here because Phase 1 is where FF5 first has a real subject;
>   if `01` places it elsewhere, ledger 1.13's `turns on` moves with it.)*

### Phase 2 — the two lines that change

> - **Lift:** the router design, the ten strategies, the intent classifier, the
>   citation manager split into its four responsibilities, language-aware reranker selection. **Plus
>   the multimodal query path per `11-multimodal.md` §2 and §3 D2: a one-method `Describer` contract
>   (whose split from the text LLM port `02` §1 already endorses), the index-time describer stage that
>   *augments* rather than replaces the caption (avoiding the defect where a plain assignment
>   overwrote the caption entirely), the query-side enricher whose marker and the router prompt that
>   recognises it are one lift or neither, and — before any of them — the caption-and-embed recall
>   measurement whose template is a spike test for image retrieval recall, and whose two defects
>   (uncommitted temp-directory output, and a query caption drawn from the index caption's own prompt)
>   are fixed at the door.**
> - **Read:** `02` §1 for the `Strategy` and `Retriever` contracts, and `09-release.md` §4 —
>   prerequisite V1–V3 must exist before this phase's work can be judged. **V1's corpus must cover
>   every format an installed extractor claims and carry a Polish body no public multimodal benchmark
>   supplies; V2's results must carry the modality of the query that produced them; and retrieval and
>   generation are two baselines with two intervals, because a judged metric's dispersion would
>   otherwise make V3's reproduction rule unfalsifiable for retrieval (`11-multimodal.md` §3 D8).**

### Phase 7 — Structured elements *(new phase; ⛔ until its gate closes)*

Per D9. Added by `09` §6.1's procedure, not by this document. Placed **after Phase 5**.

### Ledger task lines

Format per `build-ledger.md` → *How to read a task line*. Verified against the live file: existing ids
are `0.0`–`0.14`, `1.1`–`1.10`, `2.1`–`2.26`, `3.1`–`3.9`, `4.1`–`4.10`, `5.1`–`5.7`, `6.1`–`6.13`
(90 tasks). **No collisions.** There is no Phase 7 block today, so `7.1`–`7.5` opens one.

**Phase 1 — Pipelines as data** *(append; `1.11` must come before `1.12`–`1.19`)*
**Every line carries ⚠ because the phase header already rules that every Phase 1 task does** — a
Phase 1 task list written before G2 is a hypothesis.

```
- [ ] **1.11 ⚠** where a `__transient__` namespace is stripped is one rule stated once, so a stage that must read another stage's transient data either can, or provably cannot and the alternative is written down · owner `02` §1 → *The payload model*; `11` §3 D1 · turns on — · sha —
- [ ] **1.12 ⚠** a node an extractor marks unsplittable reaches the store intact, because the chunker in another distribution honours a declared property rather than a convention · owner `02` §1 → *The payload model*; `02` §3 → the ordering-constraint finding · turns on — · sha —
- [ ] **1.13 ⚠** the ingest accept set is the union of the formats plugins that actually resolved declare, computed at resolution, so a format is never accepted with no extractor behind it · owner `02` §1 → *Capability is derived, never declared*; `01` → *Fitness functions* 5 · turns on FF5 *(`01` states no activation phase for 5; placed here because a second extractor pack is its first real subject — if that is wrong, it is `01`'s to correct)* · sha —
- [ ] **1.14 ⚠** a document's pixels outlive the stage that produced them, because bytes go to a blob store and a non-transient reference goes in `ext` — so a describer, an embedder and a generator each read them, and deleting the source reaps them by a key nobody had to record · owner `11` §2.2, §3 D1; `02` §1 → *The store contract family*, `delete_source` returns counts · turns on — · sha —
- [ ] **1.15 ⚠** a PDF is indexable, and its tables and figures arrive as nodes whose media type says what they are, from a pack the CLI has no name for · owner `11` §2.1, §2.4; `01` → Phase 1 **Lift** · turns on — · sha —
- [ ] **1.16 ⚠** a table reaches the index as its cell grid plus a serialisation a stage chose, so index form and prompt form can differ without re-extracting the document · owner `11` §2.4; `01` → requirement 6 · turns on — · sha —
- [ ] **1.17 ⚠** two extractors that both render a table as text use one renderer published by the contract's own pack, so a cell containing a pipe cannot break one of them and not the other · owner `11` §1.4; `01` → requirement 1 · turns on — · sha —
- [ ] **1.18 ⚠** an extractor chain stops at the first rung that produced something, and a rung that correctly produced nothing is distinguishable from a rung that failed · owner `02` §1 → the `Outcome` rule, the contaminated `fail_silently` lift · turns on — · sha —
- [ ] **1.19 ⚠** re-indexing an unchanged file with a different parser is visible as a different pipeline rather than silently keeping whichever parse arrived first · owner `02` §1 → `SourceRecord`; `11` §4, G5-c · turns on — · sha —
```

**Phase 2 — Retrieval and generation** *(append)*
⚠ on `2.29`, `2.32` and `2.33` only. For `2.29` and `2.33` the reason is the one `10` §3.3 gives for
`2.15`–`2.19`: G2 still shapes how a query path is expressed as data. **`2.32` carries its marker
for a different reason — G4-b.** Its line states the resolution as settled, and whether that
amendment to the store contract family is additive is §4's open question and the owner's call; if
G4-b lands differently, `2.32` is re-derived rather than assumed, per this file's own rule.

```
- [ ] **2.27** an image is describable through one contract that names the medium and not the model, and a pack declares whether its model can accept one instead of a deployment layer answering for it · owner `11` §2.1, §2.2; `02` §1 → *Who publishes a contract* · turns on — · sha —
- [ ] **2.28** a described figure keeps the caption its document supplied, and a figure with neither caption nor description is absent from the index rather than present as a template string · owner `11` §2.4; `02` §1 → the `Outcome` rule · turns on — · sha —
- [ ] **2.29 ⚠** an image attached to a question reaches retrieval as text, and the router is not fooled by its own enricher's output — one lift or neither · owner `11` §3 D2; `10` §1.1 (query transforms) · turns on — · sha —
- [ ] **2.30** every metric result carries the modality of the query that produced it and the reporter slices by it, so a multimodal regression cannot hide inside a text mean · owner `09` §4, V2 and V4; `11` §3 D8 · turns on — · sha —
- [ ] **2.31** the cheap architecture is proven before it is built — caption-and-embed recall is measured against the validation corpus, and the verdict names what changes about the product rather than what to tune · owner `09` §4; `11` §1.3, §3 D2 · turns on — · sha —
- [ ] **2.32 ⚠** a pipeline whose embedders disagree about dimensionality fails at load naming the dimensions and the store, rather than at INSERT naming an index — and the check lives in the store pack, never in the kernel's resolver · owner `02` §1 → *The store contract family*; `11` §4, G4-b · turns on — · sha —
- [ ] **2.33 ⚠** a page image is embeddable by a plugin satisfying the same `Embedder` contract a text embedder satisfies, so which one runs is a pipeline edit and not a code change · owner `11` §2.1, §3 D2; `01` → requirement 6 · turns on — · sha —
```

**Phase 7 — Structured elements** *(new phase; `⛔` until its gate closes)*

```
- [ ] **7.1 ⚠** the store family has a home for data a node does not carry, added by argument rather than by a commit · owner `02` §1 → *The store contract family*; `05` → the new gate · turns on — · sha —
- [ ] **7.2 ⚠** the same table extracted from forty documents is one schema, and widening is bounded twice — per event and cumulatively — so a schema cannot drift open two columns at a time · owner `11` §1.3; `02` §1 · turns on — · sha —
- [ ] **7.3 ⚠** a table's rows are searchable without the vector index holding them, and a retrieved table node whose data did not materialise does not exist · owner `11` §1.3; `02` §1 → *The store contract family* · turns on — · sha —
- [ ] **7.4 ⚠** a continuation page whose header row was lost is recovered onto its parent schema rather than creating one, and the deterministic path stands alone when no model is configured · owner `11` §1.3; `01` → requirement 6 · turns on — · sha —
- [ ] **7.5 ⚠** guarded structured query is something a store advertises, so no retriever composes SQL · owner `02` §1 → *The store contract family*; `11` §3 D9 · turns on — · sha —
```

**Not ledger lines.** The reserved names in §2.3 and the licence rows in §7 are **document edits**,
not tasks. `build-ledger.md` holds task state only.

---

## 6. Cost and cuts, ranked

Ranked by value over cost. **`Kind` is there so the load-bearing count is not padded**: an argument, a
measurement and a clause are not capabilities, and calling three non-capabilities load-bearing makes
the ratio look worse than the thinking behind it is. **Ranks 1–10 are load-bearing. Ranks 11 and below
are not, and the cut line is stated once here and honoured in the table.**

| # | Item | Kind | Cost | Verdict |
|---|---|---|---|---|
| **1** | **Settle D1 — where `__transient__` strips** | Decision | Half a day of argument, zero code | **Load-bearing, and first.** Everything else is a hypothesis until it is answered, and it is the one item that can invalidate work already committed |
| **2** | **The caption-and-embed recall measurement (2.31)** | Measurement | One day against the V1 corpus | **Load-bearing, and it must run before the describer is built.** A red verdict changes what gets built rather than what gets tuned. A comparable system shipped multimodal RAG with this exact measurement's result written to an uncommitted temp directory and lost |
| **3** | **Row-level chunking with header propagation, as children of a whole-table parent** | Capability | Small — `derive()` carries lineage, `get(ids)` fetches the parent, the G5 ordinal disambiguates identical rows | **Load-bearing, and on its own benchmark it is the largest absolute gain in the survey:** BM25 Recall@1 **0.366 → 0.754** and hybrid MRR **0.3576 → 0.5945** (arXiv:2605.00318 — verified), corroborated by arXiv:2408.17008 (row-level with the header repeated in every cell). Answer to *one node or many*: **many, plus one.** The missing piece is reverse-lineage lookup — §4, G4-c |
| **4** | **Hybrid sparse+dense with reranking, not dense alone** | Capability | Bringing `TextSearch` forward from design-only, and a BM25 extension in the floor container | **Load-bearing.** On 23,088 real financial QA triples (T2-RAGBench, EACL 2026; benchmarked in arXiv:2604.01733 — verified): dense **0.587** → hybrid **0.695** → hybrid+rerank **0.816** Recall@5, i.e. **+22.9pp absolute over dense and +12.1pp over unreranked hybrid**. *(An earlier draft called this "+39.0pp / +17.4pp, the largest measured number in the survey". Those are the **relative** gains, and the superlative was wrong on both counts — rank 3's number is larger on its own benchmark, and the two are not comparable metrics.)* Postgres' native `ts_rank` will not do: no IDF, no length normalisation. **Same evidence, negatively: HyDE *underperformed* plain dense (0.544 vs 0.587) and multi-query gained almost nothing** — do not spend Phase 2 budget there for table-heavy corpora |
| **5** | **FF5 / the derived accept set (1.13)** | Capability | Small | **Load-bearing** — and **the accept-set half is built**, as part of repairing ledger 2.27, whose exit demonstration it turned out to be. The risk was real and dated and it fired: `discover_source_docs` filtered on one pack's module constant, so shipping `weft-pdf` made `.pdf` silently invisible to ingest. FF5 itself is still unplaced; that placement is `01`'s |
| **6** | **`weft-blob` + PDF extraction with figures and tables as nodes (1.14, 1.15)** | Capability | ~150 lines estimated for the blob pack; the PDF pack is contract-and-test work, not parsing work | **Load-bearing** — the entry point to everything else. Budget it as **one pack**, not as "port a 5,083-line parsing package" |
| **7** | **The atomic-element rule (1.12)** | Capability | Small, and Phase 1 needs it for stage 0 anyway | **Load-bearing.** An ordering constraint across two distributions, which is exactly what ledger 1.2 exists to make declarable |
| **8** | **`Describer` + the index-time describer (2.27, 2.28)** | Capability | Days, *given* an LLM pack. A comparable describer measured 131 lines, most of it an async bridge Weft deletes under G6 | **Load-bearing, full stop.** This is a multimodal plan; a figure with no description is a figure with a caption or nothing. Rank 2 decides whether the caption is a sufficient *vector source* — not whether descriptions exist |
| **9** | **Modality-sliced evaluation, and two baselines (2.30)** | Clause on an existing artefact | One clause each on V2/V4 and V3 | **Load-bearing, cheaply.** Without it *"does multimodal work"* is unanswerable and the baseline cannot tell a text regression from a multimodal one |
| **10** | **Two serialisations, not one (1.16)** | Capability | Trivial once the grid is in `ext` | **Load-bearing, cheaply.** Triplets for the index, markdown or HTML for the prompt. A single linearisation cannot serve both, which is the concrete reason the grid must survive extraction |
| — | — | — | — | **cut line** |
| **11** | **The shared table→text serialiser (1.17)** | Capability | Trivial | **Optional, costs nothing, prevents a real defect class.** Best used as the canonical docstring example of *"if two extractors both need it, it belongs to the contract's pack"* |
| **12** | **Query-side image enrichment (2.29)** | Capability | Small once `Describer` exists | **Optional.** A genuinely elegant simplification — the image never reaches the retriever, which is how image search was shipped on a text-only store elsewhere — but it is a product feature and the CLI is not a paste surface. The two-part protocol travels together or breaks silently |
| **13** | **Page-image embedding (2.33, D5 single-vector)** | Capability | One embedder plugin plus a render stage | **Conditional on rank 2.** Costs nothing settled; buys the difference rank 2 measures |
| **14** | **Contextual retrieval on table chunks** | Capability | One LLM call per chunk at index time — the dominant ingest cost of any table pipeline | **Refuse for now.** The famous headline is a large drop in top-20 failure rate on general text; **independently measured on table data it is +2.2 to +2.8pp Recall@5** (arXiv:2604.01733 — verified), an order of magnitude below ranks 3 and 4. Not where a small project spends its first LLM budget |
| **15** | **Table-RAG without SQL** | Capability | A pack, plus a gate. Measured evidence: 2,737 lines, ~1,000 of it a bodiless port surface | **Defer.** Coherent, self-contained, delivers most of the retrieval benefit — and behind two open gates |
| **16** | **Table-RAG with SQL** | Capability | Two contracts, a store capability tier, and five files nobody may read | **Refuse until `system/` is read.** Roughly doubles the surface. D9 has the argument |

### What to cut outright

- **A figure-assets repository (259 lines).** The single biggest scope saving, and Weft's contracts
  make it not merely unnecessary but inadmissible: `delete_source` returns counts and never a
  materialised cascade, so **derivable blob keys are the only design the settled contract admits**
  and a ledger has nothing to do. On the measured evidence: 8 of 11 methods have zero in-library
  callers; a SHA-256 dedup its own changelog advertised twice never executes, because the lookup
  method behind it has **zero production callers** — a deployment-layer implementation exists, but
  nothing in the library calls it; the cache key is a positional assumption its own docstring states
  and nothing enforces; and it is the **fourth** of four unrelated deletion mechanisms found.
- **A GPU-detection module (183 lines).** D4 item 7.
- **`.doc` (216 lines).** A 1997 format behind an optional dependency whose extractor is
  printable-strings scavenging returning field codes and stylesheet fragments interleaved with prose.
  The honest answer for a user with `.doc` files is to convert them. *Keep one sentence: the encoding
  ladder puts **cp1250 second** — the Polish scar — and that belongs wherever Weft decodes bytes; the
  scan window is bounded head and tail, because Word puts content at both ends.*
- **The ten Office/web/data extractors (1,299 lines) from any lift budget.** Library calls. One or two
  days each if wanted later, and the work is contract plumbing.
- **`resize_for_vision` (35-line module).** Its only content is one invariant — always PNG, so `mime`
  can default — which is a sentence in a docstring. It is also a blocking CPU call, so under G6 it
  goes through the thread offload and FF7(b) catches it if it does not.
- **The `enabled` flag, in every form.** A capability is absent when its stage is not in the pipeline.
  A comparable `multimodal_config.enabled` flag had zero readers, which is what a boolean asserting a
  capability is present is worth.
- **Vendored benchmark data, always.** Fetch by pinned revision with checksums, per V1.

**The one-sentence recommendation.** Settle D1, run the measurement, ship `weft-blob` and
`weft-extract-pdf` with figures and tables as caption-bearing nodes in Phase 1, add the describer in
Phase 2 behind the LLM pack, take ranks 3 and 4 while the retrieval path is being built, and **do not
open the tables project until its gate is argued and someone has read `system/`**.

---

## 7. Dependencies and licences

**Weft is MIT and copies no source text from anything.** A pack's own licence, its runtime
dependency's licence, and any model weights it downloads are three separate questions, and the third
is where every trap here lives. Every row below was read at its source — `LICENSE` file, model card,
or vendor pricing page — except where marked **unconfirmed**.

### Clean — usable in a first-party pack

| Dependency | Licence | Role | Note |
|---|---|---|---|
| **Docling** | **MIT** (code, *"Copyright (c) 2024 International Business Machines"* — verified verbatim); weights CDLA-Permissive-2.0 / Apache-2.0 | `pdf-layout` default | Weights (100s of MB) download on first use. Throughput **unconfirmed** |
| **pypdfium2** | Apache-2.0 / BSD-3 | `pdf-text` floor rung | No weights, no network |
| **LiteParse** | Apache-2.0 | alternative `pdf-text` | A speed floor, not an accuracy contender. Its throughput and olmOCR-bench figures are **unconfirmed** |
| **pdfplumber** | MIT | born-digital tables in the chain | |
| **granite-docling-258M** | **Apache-2.0**, weights included | `vlm-parse` default model | The only unencumbered VLM-parser weight set from a major vendor |
| **PaddleOCR-VL** | Apache-2.0, weights included | `vlm-parse` alternative | Its OmniDocBench table-TEDS figure is **unconfirmed** |
| **dots.mocr** *(renamed from dots.ocr)* | **MIT**, weights included | `vlm-parse` alternative | **3B** (1.7B was dots.ocr's LLM foundation). HF `rednote-hilab/dots.mocr` |
| **SigLIP 2 so400m** | Apache-2.0 | image-embedder *floor* — runs a conformance kit without a GPU or an API key | The card lists the checkpoint at **~1B params** (400M is the vision tower). 1152 dims is the so400m hidden size but is not stated on the card |
| **Qwen3-VL-Embedding (2B / 8B)** | **Apache-2.0**, base also Apache-2.0 | self-hosted multimodal embedder recommendation | **Configure it to emit 1024 or 1536 dims** so pgvector's index ceiling never arises |
| **ColModernVBERT** | **MIT** — architecture, weights *and* training code (verified) | the only licence-clean late-interaction model, if D5 is ever reversed | 250M params. Its card claims only *"matches models nearly 10× larger"*; the "within 0.6 nDCG@5 of ColPali" margin an earlier draft quoted is **unverifiable** and is dropped |
| **pgvector 0.8.6** | PostgreSQL licence | the floor | `vector` index ≤2,000 dims; `halfvec` ≤4,000 |
| **`timescale/pg_textsearch`** | PostgreSQL licence | real BM25 in the floor container (rank 4) | Current **1.4.0-dev**. *(An earlier draft said "v1.0, April 2026" and did not name the org; the version claim is withdrawn and the org is named because a reader will search for it)* |
| **sqlglot 30.17.0** | MIT, no required dependencies | parked, for a future SQL guardrail | Version verified; release date **unconfirmed**. A transpiler, not a validator |
| **DuckDB / pandas** | MIT / BSD-3 | program-of-thought over one retrieved table | In-process |
| **pytrec_eval / ranx** | MIT / MIT | retrieval metrics — **do not hand-roll nDCG** | Both **synchronous** (pytrec_eval is a C extension), so a metric plugin wraps them in `asyncio.to_thread` and FF7(b) must be able to tell that from an accident |
| **MTEB / vidore-benchmark** | Apache-2.0 / MIT | eval harnesses | |
| **Ragas** | Apache-2.0 | multimodal faithfulness | **Each metric call is a VLM call.** Its binary 0/1 multimodal-faithfulness metric sits badly with V4's dispersion rule — a binary metric's interval over repeats is 0 or 1 wide. |
| **ViDoRe V3 datasets** | annotation licence **unconfirmed** — repo gated; paper says only *"a commercially permissive license"* | published baseline corpus | ~26,000 pages, 3,099 queries (verified). **Pin the licence before this is written into `09`** |
| **ViDoRe V2 `economics_reports_v2`** | CC-BY-3.0 | V5's credential-free CI subset | 55.1 MB, 452 pages, 232 queries (verified) |
| **MIRACL-VISION** | **`cc-by-sa-4.0`** (verified — *not* non-commercial) | multilingual sanity check | Usable for evaluation. Do not ship a modified subset unless it is itself BY-SA. Its finding stands: VLM embedders trail text retrievers on multilingual content by roughly **30–40pp absolute** per its card; the "up to 59.7% worse" figure is **unconfirmed** and is likely relative |

### Hosted APIs — a pack is an HTTP client; the obligation lands on the operator

| Service | Cost | Note |
|---|---|---|
| **voyage-multimodal-3.5** | $0.12/M text tokens; $0.60/B pixels; free tier **200M text tokens + 150B pixels per account**; batch −33% *(all verified; the page states no monthly reset, so do not describe it as per-month)* | **The hosted recommendation.** 1024 default dims — under pgvector's limit with no `halfvec` workaround and no truncation to explain |
| **Gemini Embedding 2** | free tier for all modalities; paid **$0.20/M text, $0.45/M image** (verified) | Widest modality coverage, and confirmed as a genuinely multimodal embedding model. **3072 default dims exceeds pgvector's 2,000-dim index ceiling** — truncate or use `halfvec`, as a declared pack setting |
| **Cohere Embed 4** | ~$0.12/M text, ~$0.47/M image tokens — **unconfirmed**, secondary sources only | Credible alternative. 1536 dims, long context. Image tokens at roughly 4× text makes an image-heavy corpus expensive in a way the pack must surface |
| **Hosted parsers** | $1.25–$56 per 1,000 pages by vendor and mode — **indicative, not read off every vendor's page** | Never a default (D7). **But build one early as the reference implementation** — the only natively async, natively cancellable extractor there is (D6) |
| **OpenAI embeddings** | — | **No multimodal embedding endpoint** as of this survey, confirmed against its own docs — three text-only models. Say so in the pack docs so nobody assumes otherwise |

### Incompatible with a pack Weft would ship

| Thing | Licence | Verdict |
|---|---|---|
| **PyMuPDF / pymupdf4llm** | **AGPL-3.0** or paid Artifex | **Refuse absolutely** — not a dependency, not an optional extra, not an example |
| **MinerU** | Apache-2.0 **plus** a 100M MAU / $20M-monthly-revenue commercial trigger **and** an attribution-in-product-interface obligation (verified verbatim) | **Never a default.** Legitimate only as an explicitly opted-in separate pack |
| **Chandra 2** weights | modified OpenRAIL-M; $2M threshold **and** *"cannot be used competitively with our API"* (verified verbatim) | **Refuse as a shipped option.** Field-of-use restriction; not open source |
| **Marker** weights | modified AI-Pubs OpenRAIL-M, $5M threshold; code is Apache-2.0 | Not a first-party dependency. The code/weights split is the trap |
| **Unstructured** | Apache-2.0 code — but needs `libmagic`, `poppler-utils`, `tesseract-ocr`, `libreoffice` as **OS packages** | Not a licence problem; a **G4 probe** problem, and FF5's exact defect |
| **jina-clip-v2** | CC BY-NC-4.0 | **Non-commercial. Not a default.** |
| **jina-embeddings-v4** | Qwen Research License (2048 dims) | Not a default. Use the hosted API and say so |
| **NVIDIA llama-nemoretriever-colembed** | NVIDIA Non-Commercial | Cite for its storage numbers; never ship |
| **ColQwen2.5 / ColPali base weights** | MIT adapters over Qwen Research / Google Gemma Terms | **Verify per checkpoint.** Not uniformly clean |
| **VectorChord** (`pg18-v1.1.1`) | **dual AGPLv3 / Elastic License v2** | The only Postgres-native MaxSim. `weft-store` links nothing — a server-side extension reached over SQL — so the obligation lands on whoever runs the database. **An operator decision, documented in plain words, never an innocuous optional extra** |
| **ParadeDB `pg_search`** | AGPL-3.0 or commercial | Prefer `timescale/pg_textsearch` (PostgreSQL licence) for rank 4 |
| **VectorChord-BM25** | **not confirmed** | Check before depending |
| **MMLongBench-Doc** | data **CC BY-NC 4.0** (code Apache-2.0) | **Refuse the data on NC grounds only.** BY-NC permits derivatives, so the derivative-subset objection is void. Borrow the design: **22.5%** unanswerable, evidence-source labelling, format-dependent scoring |
| **OmniDocBench** data | research-only (code Apache-2.0) | Refuse the data; the metric family (TEDS, edit distance) is the part Weft needs |

**One licence row per shipped model**, per `09`. A pack that defaults to non-commercial weights hands
every commercial user a problem they did not choose.

---

## 8. What is deliberately not planned

**Refused, and re-verified as not having arrived.** `packages/` and `testing/`
contain no `FileType`-shaped enum, no second format list, no `EXTRACTOR_MAP` analogue, and no figure,
image, blob, vision or table code at all. A reader arriving from this document may expect these and
should not:

- A per-format dispatch factory and a separate supported-extensions list — refused. §2.1 states the
  positive rule that replaces them. The accept-then-fail finding it replaces is confirmed by the exact
  mechanism: an extractor for one format is registered only conditionally on an optional dependency
  being present, while the format itself is declared unconditionally in a separate list — so the
  format is accepted and then fails.
- Closed enums used as registries' key types (a strategy-name enum, a retrieval-strategy-type enum, a
  file-type enum) — refused. `MediaType` is not a counter-example: it is a closed *core-field
  vocabulary* with no registry behind it, which its own docstring argues.
- A silent default-strategy fallback — refused, and worth naming again because **this family
  reproduces the same shape four independent times**: a bare `except Exception` counter in the
  describer, the visual-capability listing, a table augmenter's own fallback path, and the figure
  cache-hit path each make total failure indistinguishable from a legitimately empty result. Weft's
  rule against broad exception catching is usually argued from style; this area is the evidence that
  it is a correctness rule.

**Not planned here, with the reason.** *(These rows belong in `01`'s deferred list, which owns
deferrals; they are stated here only long enough to be moved — see *Where this goes*.)*

| Not planned | Why |
|---|---|
| **A multimodal embedder contract** | D2. Nothing examined embeds an image, and `weft-embed`'s `Embedder` already accommodates a pixel embedder as a plugin. A second contract fails `01` requirement 1 |
| **A `PageRenderer` contract** | One plausible implementation is a guess (`01` → *Runtime shape*). Rendering a page is something a PDF extractor does |
| **S3/MinIO blob backends** | Every concrete adapter examined lives in the unread deployment layer, so there is no usable input here. `weft-blob` ships a local filesystem implementation written fresh against Weft's own key scheme |
| **The SQL guardrail, NL→SQL, row materialisation, the schema analyzer** | All in the unread deployment layer. Nobody has read the security-critical half of this capability, and a SQL self-correction service — something that rewrites rejected SQL — is exactly where a guardrail bypass would live. Reading that layer is a separate, explicit decision about the reading restriction, not something to smuggle in through a plan |
| **`supports_vision` semantics** | In the unread deployment layer, and already a blocking open question. Weft must decide how a pack declares image capability rather than inherit an answer |
| **A forced-visual fallback tier** | Refused, not deferred. D4 item 6 |
| **A `MultimodalConfig` equivalent** | G1 forbids it on the passport, and `enabled` should not survive anywhere |
| **`TableLinearizer` in a tables pack** | Not a table capability despite the name. Already assigned to the cleaning pack, and it stays there |
| **The enhancer registry (T2.2)** | Superseded — enhancement is a pipeline stage discovered through entry points; G3's eager discovery replaced a hardcoded built-in tuple. Worth recording once, in `05` → G6 and `02` §1, as the worked example: **the vision describer is the case that broke it.** A generic constructor taking only an LLM handle, a language and open-ended kwargs cannot express a plugin needing a *different* model, so the factory grew a string-comparison special case and the port grew a one-bit flag overridden exactly once. That is `02` §1's *"a registration API without a typed configuration model is decorative"*, demonstrated |

---

## 9. What is not confirmed

Stated as a section rather than as footnotes, following `10` §5's precedent. **No claim in this
document states more than its source.** Each item below could not be reached at a primary source; each
is either already dropped from an argument above or is marked at its point of use. None of them may be
written into `docs/` as fact without being re-sourced first.

**Load-bearing if used, so pin before writing:**

1. **ViDoRe V3's annotation licence.** The dataset repo is gated; the paper says only "a commercially
   permissive license". D8's corpus recommendation depends on it.
2. **A prior recall-spike's actual verdict.** Unrecoverable by construction (written to an
   uncommitted temp directory). Weft's own measurement replaces it; no number from it may be quoted.

**Dropped from the arguments above, and not to be reinstated without a source:**

3. Qwen3-VL-Embedding-8B "ViDoRe v2 69.9", and the comparators "ColNomic-7B 62.7" and
   "llama-nemoretriever-colembed-3b 63.5". The card reports 78.3 on MMEB-V2 VisDoc OOD.
4. "The top ViDoRe V3 pipeline was text-only." It was **hybrid text+visual**.
5. Chart-QA "caption 41.53% vs multimodal 42.53%" — no citation anywhere.
6. "~+6.5% from page image plus OCR text over image alone" — no citation anywhere. *(The
   54.7%/52.1% pair originally listed here was withdrawn in error: it is ViDoRe V3's own sentence,
   arXiv:2601.08620, and now carries that id in D2.)*
7. Arctic-Text2SQL "71.83% on BIRD" and "Spider 2.0 ≈ 21%" — the paper exists (arXiv:2505.20315) but
   neither number is in it and Spider 2.0 is not among its benchmarks.
8. "MinerU2.5-Pro 95.69 on OmniDocBench v1.6" — the changelog gives 95.26 / 95.39 / 95.30.
9. D8's dollar figures for a generation-and-judge pass ($40–180 / $200–900 / $20–80) — no working was
   shown; derive them in V5 instead.
10. MMLongBench-Doc "22.8%" and "20%" unanswerable — the repo says **22.5%**, and an earlier draft gave
    two different numbers for one fact.

**Marked at their point of use, and safe to keep as marked:**

11. Docling throughput (~1.2–1.5 p/s CPU, ~3.1 p/s L40S) — and note Datalab's table reports docling at
    2.1 pg/s on GPU, which conflicts.
12. VLM-pipeline throughput (~2.0–3.8 p/s on consumer GPUs).
13. LiteParse throughput (~1,721 p/s) and its 22.4% olmOCR-bench figure.
14. PaddleOCR-VL table TEDS 0.9195 on OmniDocBench v1.5.
15. ColModernVBERT "within 0.6 nDCG@5 of ColPali".
16. MIRACL-VISION "up to 59.7% worse" (the card shows ~30–40pp absolute).
17. MUVERA specifics — native FDE ~10,240 dims, the ±1 random projection to ≤4,000, FDE-only ≈70% of
    full multi-vector quality.
18. Venue attributions: ViDoRe V3 "ACL 2026" and MUVERA "NeurIPS 2024" — neither appears on the arXiv
    abstract page. Cite by arXiv id only.
19. Cohere Embed 4 pricing (secondary sources only).
20. sqlglot's release date; VectorChord-BM25's licence; "Marker 2" as a version name — Datalab's table
    row is *"Marker — balanced (GPU)"*.

---
