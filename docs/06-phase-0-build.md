# Phase 0 — the build plan

**What Phase 0 is, from `01` → *Phases*:** the kernel, the registry, entry-point discovery and three
built-in plugins — one extractor, one chunker, one store — with `weft index` and `weft ask` working
end to end on a directory of text files.

**Its exit criterion is one sentence and it is the thesis of the project:** a plugin living in a
*separate installed package* is discovered and used, with no edit to the core package. Everything
below exists to make that sentence testable, plus fitness function 8(a) green.

This document owns the **order of work** and nothing else. What each piece *is* lives in `01` and
`02`; what is settled lives in the decision log in `README.md`. If this document and one of those
disagree, they are wrong and this one is out of date.

---

## The three places this phase can accidentally settle an open decision

> **G2 settled 2026-08-16, and all three choices below held.** Embedding stays a stage — it was never
> G2's to choose, because G4 forbids a store to embed. A pipeline stays an ordered list, with
> derivation, slots and declared constraints added on top rather than replacing it. Duplicate
> registration stays a refusal, relaxed only by an operator's pin, which is the direction item 3
> required. Nothing below needs undoing; the section is kept because it records *why* each choice was
> made reversible, and that reasoning is what made the gate cheap to close. The outcome lives in
> `02` §3.

Read this before the work list. Phase 0 has to do things that G2 owns and G2 is open, so the rule for
each is the same: **make the minimal choice that is reversible, and record that it is not an answer.**

**1. Where the embedding happens.** G4 settled that stores take a vector and never embed — a store
coupled to an embedding model cannot be used with two models or none. So indexing must produce a
vector before the store stage, and the reference had nowhere for that: it embedded inside storage, which
is why its `query()` took a string. G2 must decide whether that is a stage in the list or a step
inside the store stage. **Phase 0 puts it in the list, as a stage, and this is not an answer to G2.**
It is the shape that requires no new machinery; if G2 chooses otherwise, one stage moves.

**2. What a "pipeline" is before Phase 1 exists.** Phase 1 builds the pipeline model, the resolver and
the derivation operators. Phase 0 still has to run stages in order. **Phase 0 builds a linear runner
over an explicit ordered list and no derivation at all** — no `extends`, `insert`, `replace`, `remove`
or `set`. A pipeline in Phase 0 is a list you wrote out in full. This deliberately leaves G2's
ordering-constraint question untouched, because a plan with no derivation operators cannot silently
place a stage between `HyphenationFixer` and `WhitespaceNormalizer`.

**3. What happens when two packs register the same name.** G2 owns arbitration and has not decided.
**Phase 0 raises on duplicate registration**, naming both distributions. This is the reversible
choice: refusing is strictly recoverable, and every silent-overwrite behaviour in the reference — four of
its six registration decorators — is a bug someone eventually has to find. If G2 later chooses
last-wins, first-wins or explicit qualification, it relaxes a refusal rather than tightening a
silence.

**One more, smaller.** `03` defines `weft ask` as a query that streams an answer with citations.
Generation belongs to Phase 2 and no LLM pack exists in Phase 0. **Phase 0's `weft ask` retrieves and
prints the matching passages, and says so in its help text.** The exit criterion is about the plugin
seam, not about answer quality, and adding an LLM here would drag `weft-llm` and the prompt layer
into a phase whose job is wiring.

---

## The order, and why it is this order

Two principles decide it. **The registration seam comes early**, because every cross-cutting concern
attaches there and the reference measured what happens otherwise: every concern its machinery applied
automatically held perfectly, and every concern an author had to remember decayed. **Discovery comes
before the built-ins**, because built-ins that exist before the public path exists are built-ins that
quietly get a private one — which is exactly the defect fitness function 2 was written to catch.

Each step names what it makes true, not just what it adds.

### 1. The payload types — `weft-kernel`

`NodeId`, `Lineage`, `MediaType`, `Node`, `ExtModel`, `ExtMap`, `Vector`, `Outcome`. Frozen Pydantic
models, the admission rule for the six core fields, `derive` / `combine` / `synthetic`, `with_ext` /
`ext_as`, content-addressed identity, and `sources` derived from lineage rather than stored.

*First because every signature below names these types.* Also because two reference bugs stop being
representable here rather than being fixed later: non-empty parents plus derived `sources` make
RAPTOR's unreachable summaries **unwritable**, and `__transient__` makes the multi-MB base64 blob
into JSONB impossible rather than guarded.

**Makes true:** G5 exists in code. **Runnable:** nothing; unit tests only. **Gate:** none.

### 2. Errors and the registry

`WeftError` as the root, with attribution at the plugin seam. `Registry` with `add(contract, name,
factory)`, lookup by contract and name, and refusal on duplicate (see collision note above).

**Makes true:** something to register into. **Runnable:** nothing.

### 3. The registration seam

The wrapper every registration passes through, applying — without the author asking — span wrapping
via `opentelemetry-api`, error attribution naming the stage and the distribution, `__transient__`
stripping, and the categorical blocking-call detector scoped to stage execution.

*This is the single most load-bearing piece of the kernel and the reason the reference's observability
decayed.* Build it before there is anything to wrap, so that nothing is ever wrapped by hand.

**Makes true:** fitness function 7(b) has somewhere to live. **Runnable:** nothing.

### 4. The passport

`Context`: `tenant_id`, run and trace ids, cancellation, locale, `require()`, and `t()` for messages.
The service registry `require()` resolves against. No tuning knobs — anything resolvable is a service,
not a field.

**Makes true:** a stage can be handed something. **Runnable:** nothing.

### 5. Discovery and the trust model

Entry-point enumeration over `weft.packs`, eager import and `register()` when the registry is needed,
the `[packs] allow` list, the status vocabulary (`active` / `refused` / `failed` / `partial` /
`allowed, not installed`, plus `ambient`), the `DISCLOSURE` read, pack settings validated against the
pack's own Pydantic model before `register` is called, and `${env:}` interpolation in the loader.

**Makes true:** **fitness function 8(a)** goes green against the canary — the first Phase 0 exit
criterion. Fitness function 2 becomes checkable. **Runnable:** `weft plugins list` in spirit, though
the CLI lands at step 9.

### 6. The linear runner

An ordered stage list, `Stage[In, Out]` composition checked at resolution, `requires` / `provides`
checked against what earlier stages provide, `Lifetime` honoured by the instance cache, one batch in
flight, `flush()` owned by the runner rather than by stages, and `CancelledError` propagating
untouched.

**Makes true:** stages compose, and a mis-ordered list fails at resolution with a message naming the
stage, the namespace and the pack — rather than at runtime with a `KeyError`. **Runnable:** a pipeline
in a test.

### 7. The three contracts, published by packs

`Extractor` in `weft-extract`, `Chunker` in `weft-chunk`, `NodeStore` + `VectorSearch` in
`weft-store`. **The kernel defines none of them.** Each carries a version, and capability is *derived*
at registration by what the class satisfies, never declared.

**Makes true:** fitness functions 2 and 6 have subjects. A newcomer opening `weft-kernel` finds no RAG
vocabulary, which is the visible consequence G1 warned would feel wrong.

### 8. The built-ins, and the embedder

A text extractor over a directory of `.txt` and `.md`; a fixed-size chunker with overlap; a pgvector
`NodeStore` with `VectorSearch`. Plus the embedding, per the note above.

**This phase needs a fourth pack the plan did not anticipate: `weft-embed`.** The reasoning is forced
— G4 forbids the store from embedding, G2 has not placed the embed step, and a walking skeleton must
not depend on a model download or an API key. So Phase 0 ships a deterministic local embedder
(hashing to a fixed-dimension vector) whose only job is to be a real vector produced by a real stage.
It is not a quality component and its docstring should say so.

**Reading a node back needs something step 1 deliberately did not build.** `Node.model_dump()`
serialises `ext` correctly, but the reverse does not exist: a dumped namespace is a plain dict, and
turning it back into the pack's own `ExtModel` subclass needs a namespace-to-class registry. Step 1
left that out on purpose — the registry it would need arrives at steps 2–3 — so the store is where
the rehydration path is designed, against the registry rather than against a hand-rolled map.

**Makes true:** indexing produces stored nodes. **Runnable:** an ingest pipeline, in a test.
**Infrastructure:** this is where the one container arrives — a `compose.yaml` with Postgres and
pgvector, because G4 retired the zero-container target and made pgvector the floor.

### 9. The minimal CLI — `weft-cli`

`weft index <path>`, `weft ask <question>`, `weft plugins list|doctor`, `weft --version`. The single
`asyncio.run`, at the entry point. Exit codes `0/1/2/3/4` with the policy-versus-resolution split.
Permission classes declared on every command, no default.

**Makes true:** **fitness function 7(a)** — one bridge, asserted by path — and **8(b)**, no pack code
executing for a command that does not need the registry. *(See the correction note at the foot of this
document: `01` currently activates 8(b) in Phase 3, and Phase 0 is where it becomes possible.)*
**Runnable:** the product, end to end.

### 10. The independence proof

A pack that lives **outside this workspace** — its own directory, its own `pyproject.toml`, installed
with `uv pip install`, not a workspace member — registering one chunker. Install it, run an ingest
pipeline that names it, uninstall it, watch the pipeline fail to resolve with a message that names the
missing distribution.

*This is the exit criterion, and it must be an artifact rather than a demo.* Keep it in the repository
as `examples/weft-example-chunker/` with a test that installs it into a temporary environment. A
criterion that is only ever satisfied by hand is satisfied once. *(The message names the plugin, not
the distribution — see the second correction at the foot of this document.)*

**Makes true:** Phase 0 is over.

### 11. The shipped documentation set and its checks

The two manuals whose content is exactly what Phase 0's exit criterion makes true: the quickstart
(`weft index` / `weft ask`, end to end, on the reader's own files) and the pack author guide's
single-contract section (the independence proof from step 10, turned into prose a stranger can
follow). Both get the CI infrastructure that keeps them from drifting silently, per `08-manuals.md`
§3: a harness that extracts the quickstart's fenced shell blocks and runs them against a throwaway
project, and a test that diffs the guide's tagged code blocks against `examples/weft-example-chunker/`,
the same artifact step 10 already keeps.

*This is the last step for a reason.* Both checks need something to check against — the CLI (step 9)
and the independence proof (step 10) — so writing them earlier would mean documenting commands that
do not exist yet, the exact reference failure `08-manuals.md` §0 opens with.

**Makes true:** Phase 0's thesis is not demonstrated once by a human and then left to age; it is
asserted by a reader-facing document whose assertion keeps getting checked. **Runnable:** `uv run
pytest tests/docs -q`, and the quickstart itself, against a fresh `uv add` in a throwaway directory.

---

## What Phase 0 must not build

A scope fence, because every item here is something a reasonable person would reach for and each one
belongs to a later phase with its own gate or its own exit criterion.

| Not now | Where it belongs |
|---|---|
| `extends` / `insert` / `replace` / `remove` / `set` | Phase 1, after **G2** |
| Ordering constraints beyond data dependency | Phase 1, **G2** — the cleaning chain is its case |
| Retrieval strategies, fusion, reranking, the router | Phase 2 |
| Generation, prompts, the LLM adapter, `weft-llm` | Phase 2 |
| Metrics, the evaluation harness, persisted runs | Phase 4 |
| The REPL, streaming, `TokenSink`, plugin commands in `--help` | Phase 3, after **G8** |
| A second store backend | Phase 2 or later — G4 requires pgvector **and** Qdrant before the contract is trusted, but not in the skeleton |
| An event bus | Phase 5, **G7** |
| Deprecation policy, contract support windows | Phase 5, **G9** |

---

## Done when

All six, not five:

1. `weft index <dir>` ingests a directory of text files into pgvector, and `weft ask <q>` returns the
   matching passages.
2. **Fitness function 8(a)** is green: the canary is refused by an allow-list and never imported.
3. **Fitness function 7(a)** is green: exactly one `asyncio.run`, at the CLI entry point.
4. **Fitness function 2** is green at runtime: the registry's contents equal what the installed
   distributions declared, and no built-in took a path a third party could not.
5. **The independence test passes as an automated test**: a chunker in a separately installed package
   is discovered and used, with no edit to any package under `packages/`.
6. **The quickstart and the pack author guide's single-contract section are written, and their checks
   are green** (`08-manuals.md` §3, clauses a and c): a fenced shell block that fails to run, or a
   code sample that has drifted from `examples/weft-example-chunker/`, fails the build.

The kernel is expected to be well under its 3,500-line budget at this point. If it is not, that is
information about the boundary rather than about the budget, and it goes to the decision log before
anything is written to fit.

---

> **A correction this document produced (2026-08-15).** `01` → *Fitness functions* activates clause
> 8(b) — *no pack code executes for a command that does not need the registry* — in **Phase 3**, on
> the grounds that a command surface exists only then. That is wrong: Phase 0 ships `weft index`,
> `weft ask`, `weft plugins` and `weft --version`, and `--version` is exactly the command the clause
> is about. 8(b) activates at **step 9 of this plan**, in Phase 0. Clause 8(c) — the recorded
> distribution set — stays later, because it depends on persisted runs, which are Phase 4's. `01` and
> the phase exit criteria have been updated accordingly.

> **A correction step 10 produced (2026-08-16).** Step 10 originally ended *"watch the pipeline fail
> to resolve with a message that names the missing distribution."* No message can: once the pack is
> uninstalled, its distribution name is exactly the thing nothing in the process still knows —
> `Registry.entry` is looking up a name that no entry point offered, and naming a distribution there
> would mean keeping a list of packs that once existed, which is the second list this project
> refuses. What the message does name is the **plugin**, the contract it was wanted for, and every
> name that *is* registered for that contract — which is the shape `02` §2 → *The trust model*
> already requires ("A name provided by no pack at all stays 4 … with its reason attached") and the
> form `01`/`07` state for fitness function 9(a) ("break the entry point and resolution fails naming
> the plugin"). Step 10's sentence was the outlier and has been corrected; `build-ledger.md` 0.10
> ("fails resolution by name") was already right.
