# 07 — The extension cost

**What this document owns:** the per-kind file cost of adding a capability, and fitness function 9.
It owns nothing else. Contracts, the payload model, the store family, packs, discovery, pack
settings, the trust model, derivation and the graph add-on are `02`'s; phases, requirements and
fitness functions as a set are `01`'s; the command surface and permissions are `03`'s; the Phase 0
build order is `06`'s; state is `README.md`'s. Where this document needs one of those it links.

**What it deliberately no longer contains.** The pack-author walkthrough that was §3–§4 of the first
draft has moved out, per **D3**: a walkthrough is user-facing documentation, its home is the shipped
manual set specified by `08-manuals.md`, and the multi-point case is already owned by `02` §4
(*Add-ons — driving use case B*). This document links to both rather than restating either.

Requirement 1 in `01` → *What "modern and elastic" has to mean concretely* is *a new capability is
one new package, zero edits to core*, and the `weft-qualities` skill falsifies it with *name every
file outside the new package that has to change*. Today that is a **review lens** — a human asks, a
human answers, nothing records the answer. §1 makes the answer a written argument. §2 makes the part
of it that a test can hold a test.

---

## 1. The extension cost table

### How to read it

**"Inside the new distribution"** counts the files a developer creates. **"Outside it"** counts files
that already exist and must change. The second number is the one that matters, and the number this
project claims is **zero under `packages/` for an out-of-tree pack**. That scoping is load-bearing
and is disclosed in full below — it is not a way of hiding an inconvenient case.

The unit of measure is the **canonical pack, four files**. The mechanism behind each is `02` §2's,
not this document's:

| # | File | What it is for |
|---|---|---|
| 1 | `pyproject.toml` | Name, `requires-python`, dependencies — the kernel **and the pack that publishes the contract** — and one entry point in the `weft.packs` group (`02` §2) |
| 2 | `src/<pkg>/__init__.py` | The pack's `Settings` model and its `register(registry, settings)` (`02` §2 → *Pack settings*) |
| 3 | `src/<pkg>/<impl>.py` | The contract implementation and its `with:` configuration model (`02` §1) |
| 4 | `tests/test_<impl>.py` | The pack's own tests, against the conformance kit and the ephemeral in-memory store |

Contracts are published by packs, not by the kernel (`02` §1 → *Who publishes a contract*), so file 1
depends on `weft-chunk` or `weft-store` the way it would depend on any third-party protocol. That is
the only structural difference from a pack that implements nothing at all.

### The table

| Kind of extension | Inside the new distribution | Outside it, under `packages/` | Why it comes out that way |
|---|---|---|---|
| **New store backend** | **4–5.** The canonical four, plus a `compose.yaml` if its tests need their own container. `register()` probes its optional driver and registers the class that actually works (`02` §1 → *The store contract family*) | **0** | Capability is *derived* at registration from which of the store protocols the class satisfies. There is no flag to write, therefore no flag file to edit, and no `isinstance` ladder anywhere that has to learn the new name |
| **New chunker** | **4** | **0** | The contract is one async method with domain types on both sides. Selection is by registry key from pipeline data |
| **New extractor** | **4** | **0** | The plugin declares its own extensions and MIME types as capability metadata (`02` §1). There is no second list to add a format to, and fitness function 5 makes a declared-but-unresolvable format unrepresentable rather than merely discouraged |
| **New embedder** | **4** | **0**, with an open-gate asterisk | The contract belongs to `weft-embed` (`06` step 8). **G2 has not placed the embed step**, and neither placement changes the file count — only where the operator writes one line. Phase 0's choice is explicitly *not* an answer to G2 (`06` → *The three places this phase can accidentally settle an open decision*, item 1) |
| **New retrieval strategy** | **4** | **0**, from Phase 2 | Requires Phase 2's contract. A strategy declares `needs_store`, checked at resolution against the configured store. The router discovers strategies from the registry, which is Phase 2's exit criterion — **the zero here is guaranteed by fitness function 4(b), not by function 9**; see §2, *What it does not catch* |
| **New metric** | **4** | **0**, from Phase 4 | Requires Phase 4's `Metric` contract. The `with:` block is what makes the same metric runnable twice at two thresholds, which is requirement 6's second clause |
| **New CLI command** | **4** | **0**, from Phase 3 | The `Command` contract carries a mandatory permission-class `ClassVar` with no default (`03` → *Permissions*), read at registration. Help text is generated from the registry, so there is no command list in core to append to |
| **Multi-point pack** (the graph add-on) | **8–9.** The canonical four, plus one module per contract implemented, an `ext.py` declaring the pack's namespaced models, and a pipeline fragment shipped as data | **0** | This is requirement 2. What makes it hold is one entry point, one `register()`, one `Settings` model wired into every factory by the pack itself. `02` §4 owns this case in full, including the registration table and the install sequence; it is not restated here |
| **New stage in an existing pipeline** | **0** — no distribution is created if the plugin already exists | **0 under `packages/`; one derivation, in whatever form G2 settles on** | The parent is referenced, never copied, so the edit is additive and the parent keeps improving. **G2 owns this row's units as well as its edges**: `02` §3 → *Open decisions* assigns it the overlay semantics, multi-level conflict rules, **and whether pipelines are authored in YAML, Python or both** — so "one data file" would be presuming the YAML answer. The operators and the KeyBERT case are `02` §3's. Phase 0 has no derivation operators at all, so today this means writing the list out in full (`06`, item 2) |
| **A new contract entirely** (a capability nobody has published) | **5.** The canonical four plus `contract.py` — the Protocol, its version, and the typed configuration model its registration API carries | **Honestly not zero in the general case.** Zero when the same pack ships the contract *and* the caller that invokes it. Non-zero when an existing stage must do the calling: that stage's pack changes | A contract nobody calls is inert. `ctx.require(NewContract)` has to be written by whoever needs it, and if that is someone else's stage, the extension model has reached its edge. **This is what G7 is for** — *"can a pack observe things it has no extension point for?"* (`05` → G7) — and the honest answer today is: only if an extension point already exists in the right shape |

### What the zero excludes, and why none of it is a cost

A table that reported zero in every column would not be believable, and would be describing a system
where installing a distribution silently changes what your machine does — precisely the threat G3
named. Four classes of file are never zero. Three are the operator's, one is the repository's, and
none of them is code that had to learn the new capability's name.

| File | When | Why it is the interface working rather than a cost |
|---|---|---|
| the pipeline document | always | Something has to *name* the plugin. A capability that installs and activates itself is a capability nobody chose |
| the `packs:` settings block | if the pack takes settings | Keyed by distribution name, validated against the pack's own model before `register` runs (`02` §2 → *Pack settings*) |
| the `[packs] allow` list | only if a pin is active | An allow-list is **exhaustive when present** (`02` §2 → *The trust model*). A list that only adds is not a control, so a new pack means a new line, deliberately |
| **repo-level workspace wiring** | **first-party packs only** | A new distribution under `packages/` is already inside `[tool.uv.workspace] members` (`packages/*`, a glob), but the root `pyproject.toml` also carries an explicit `[tool.uv.sources]` line per first-party distribution, and a new one needs its own — `weft-embed`, arriving at `06` step 8, is the live example. **This is the one place a built-in touches something an out-of-tree pack does not**, and it is worth naming rather than hiding: it touches *packaging*, not code. No dispatch, no import list, no registry learns the name, so requirement 4 is unharmed — fitness function 2 still asserts at runtime that the built-in took no path a third party could not |

**So the claim, stated exactly.** The zero is a claim about **out-of-tree** packs: a pack installed
from outside the workspace adds no file to `packages/` and changes none. That is exactly the property
fitness function 9(a) installs and runs. First-party packs pay one packaging line, and publishing a
*new contract* additionally obliges a new out-of-tree example pack under `examples/` — real files,
outside `packages/`, caused by the extension — because that is what clause 9(c) demands. Both are
disclosed here so the table's zero cannot be read as covering them.

### The measurement this replaces

The reference is the counter-example for every row, and the numbers are the study's. The four columns
below are the study's own columns from its verdict table at
`reference/study/01-extension-axes.md:19-25`, reproduced under the headings it gives them.

| Axis | Registry? | Dispatch sites over a name | Files to edit to add one | Evidence |
|---|---|---|---|---|
| Parsing / extraction | No — 3 unrelated mechanisms | 10 | 1 new + up to 18 existing (~28 edit sites, with the config toggle) | `reference/study/01-extension-axes.md:21` |
| Chunking | No for chunkers; yes for enhancers | 15, in 5 distinct styles | 1 new + 6 (plus 2 byte-identical alias maps) | `:22` |
| File types | No | 12 lockstep sites (10 list-shaped, 2 control-flow) | 1 new + 3 (9 edit sites; 13 for an optional format) | `:23`, and the itemised count at `:1766-1777` |
| Retrieval | Yes — but **three** of them | 21, of which only 3 are registry lookups | 6–8 files, ~12 sites | `:24` |
| Storage | **None at all — 0 registered names** | 17, of which 0 are registry lookups | 11 in the library + 3 or more in `system/` | `:25`, the 17-step table at `:3238-3258`, the count at `:3260-3263` |

Two axes the verdict table does not cover, cited to where they are actually stated:

- **CLI command.** There is no `[project.entry-points]` block of any kind; the only declared surface
  is three fixed Typer apps under `[project.scripts]` — *"Nothing a third party can contribute
  to."* (`reference/study/02-discovery-and-config.md:175-182`.)
- **Metric.** Registration works mechanically, but consumer sites filter with
  `if name in EVALUATOR_REGISTRY`, so *"an unimported plugin metric is silently dropped rather than
  reported"* (`:245-247`) — and the built-ins already prove it: `import a_prior_project.evaluation`
  registers **17 of the 23** decorated classes, measured (`:15-17`).

Three of these rows are worth reading twice.

**The storage row is the shape of the argument.** Seventeen dispatch sites over backend identity
against **zero** registered names is not a big number and a small number; it is a system with no door
at all, where every selection is an `isinstance` discrimination the library performs on adapters it
imports itself.

**The retrieval row is the one where the file count is misleadingly reassuring.** Six to eight files
is not catastrophic, and the result is still unusable: the decorator's `kind` parameter is typed
against a `StrEnum` with exactly three members, which a plugin cannot extend
(`reference/study/02-discovery-and-config.md:236-240`, citing `retrieval/types.py:24-26`), and a strategy
that does register is *"registered, listed by `get_all_strategy_metadata()`, described to the LLM in
the routing prompt … and **can never be executed**"* (`:233-234`).

**The metric row costs almost nothing to add and produces no error and no score when it is wrong.**
The cheapest extension in the reference is also its quietest failure.

Together they are why **a cost table alone is not a sufficient measure of an extension model**, why
fitness function 9 is scoped narrowly in §2, and why fitness functions 2, 4 and 5 are not folded into
it.

---

## 2. Fitness function 9 — extension is proven from outside

*Written in `01`'s format for its **Fitness functions** section, where it is item 9.*

> 9. **Extension is proven from outside.** Every published contract has an implementation that lives
>    outside the workspace, is installed rather than linked, and is nowhere named by core. Three
>    clauses, all categorical, and **no tuning constants in any of them** — no threshold, no file
>    count, no percentage — for the same reason fitness functions 7 and 8 carry none: a number like
>    *"fewer than five files"* is one nobody can defend, and it gets re-baselined until it means
>    nothing. The *cost* of extending is argued in `07-extension-cost.md` §1 and judged per change by
>    the `weft-qualities` lens; this function asserts the tree property that makes that argument
>    checkable, and claims nothing about a diff.
>
>    (a) **The stranger runs.** Each example pack lives outside `packages/`, outside `testing/`, and
>    outside the uv workspace, with its own `pyproject.toml`. The test builds the first-party
>    distributions as wheels, installs them plus the example pack into a throwaway environment, and
>    runs a pipeline that names the example's plugin — with the source tree not on the path, so no
>    path a workspace member has can be the reason it works. **How it fails:** put the example back on
>    the path as a workspace member and the wheel build stops covering it; break the entry point and
>    resolution fails naming the plugin. It is `06` step 10 generalised from one chunker to every
>    published contract. *Active from Phase 0*, where step 10 already builds
>    `examples/weft-example-chunker/`.
>
>    (b) **Core does not know the stranger exists.** No file under `packages/` or `testing/` names any
>    example pack — not as an import, not as an entry point, not as a string literal of its
>    distribution name or of any plugin name it registers. The two sides are computed from different
>    places and never from each other: the names come from the example packs' own metadata and their
>    observed registrations, the text comes from the first-party source tree. **How it fails:** a
>    conftest that special-cases the example, a workspace member listing it, a test asserting on its
>    plugin name. Like `01` item 0's model, the check is **itself unit-tested** against a planted
>    literal, so a clause that stopped being able to fail would fail its own test. Clause (a) proves
>    the pack works; (b) proves it works without having been anticipated, which is the half a demo
>    always quietly fails. *Active from Phase 0.*
>
>    (c) **Every published contract has a stranger.** The set of contracts published by the installed
>    first-party distributions equals the set of contracts implemented by out-of-tree example packs.
>    Both sides are observed at runtime and **neither is derived from the other**: the left from the
>    first-party packs' own registrations, the right from each example pack installed on its own. A
>    clause whose two sides came from one computation would be the reference's `test_keys_parity` defect,
>    which cannot fail at all (`reference/study/08-salvage.md:777-782`). **How it fails:** publish a
>    contract and ship no example for it — which is the everyday case this clause exists to catch. It
>    carries a **ratchet** in the style of item 0: a named constant
>    `CONTRACTS_WITHOUT_AN_EXAMPLE_PACK`, pinned empty, so an exemption is a visible entry in a diff
>    rather than a silent edit, changeable only by a dated decision-log entry. *Active from Phase 2*,
>    the first phase that publishes a contract Phase 0 did not, and its activation is an exit
>    criterion of that phase.
>
>    **Why it exists.** Requirement 1 is the thesis of the project and it is the only one of the six
>    that has never been enforced by anything. The reference is why that matters: adding one storage
>    backend meant editing **11 files inside the library** plus at least 3 in `system/`
>    (`reference/study/01-extension-axes.md:3260-3263`), against **"None at all — 0 registered names"**
>    and 17 dispatch sites of which 0 are registry lookups (`:25`). Nothing in the reference's CI measured
>    that, and nothing could have — its own boundary checker was not in its canonical gate and exited
>    0 on a tree with 11 violations (fitness function 0). Weft's gap today is narrower and the same
>    shape: the requirement is applied by a human running the `weft-qualities` lens, and a lens is not
>    a ratchet.
>
>    **What it deliberately does not catch, and why there is no fourth clause.**
>
>    - **Reachability.** A plugin can register from outside, cost zero core edits, and still never
>      execute — the reference's sharpest finding, where a third-party strategy registers, is listed, is
>      described to the LLM in the routing prompt, and hits three walls
>      (`reference/study/02-discovery-and-config.md:226-234`). That is **fitness function 4(b)**'s job.
>      Function 9 asserts that extension happens from outside; 4(b) asserts the extension can *run*.
>      Reading 9 as covering both is how the reference's seam would pass a green build.
>    - **Cost, per change.** A pack needing 400 lines of boilerplate passes clause (a) exactly as a
>      four-file one does, and a core edit made in the same commit for an unrelated reason is
>      invisible to all three clauses. This is a property of the tree, not of a pull request. The file
>      cost is argued in `07-extension-cost.md` §1 and judged per change by review — a line budget on
>      a pack would be a tuning constant, which is the thing this function refuses.
>    - **Wrong-shaped extension points.** A pack may need a core change to be *useful* rather than to
>      *load*: an extension point that exists but in the wrong shape. That is Phase 5's human test —
>      *if they file an issue asking for a core change, that is a design finding* — and **G7**'s
>      question.

---

## 3. A correction to raise before this document is applied

**Not resolved here, and deliberately not.** This document does not own configuration layout and
must not settle it by demonstrating one answer.

**The discrepancy, verified.** `02` §2 → *Pack settings* shows the `packs:` block in **`weft.yaml`**
(`02-extension-model.md:513`), while `02` §2 → *The trust model* shows `[packs] allow` in
**`weft.toml`** (`:586`). `03` → *Project context* describes `weft.toml` as the file holding the
project's default pipeline, collection, model profile and permission defaults
(`03-cli.md:164-169`), and `03` → *Command surface* has `weft init` scaffold `weft.toml`
(`03-cli.md:54`). Nothing anywhere states whether these are one file or two, or which one an
operator edits for what.

**Why it cannot be left.** Both files are things a pack author is told to write into, and a manual
that shows two config files with no rule for which is which institutionalises the ambiguity in a
third place. It also has a deadline: `06` step 5 builds discovery and the trust model, so it picks an
answer whether or not anyone decides one.

**Who owns the correction.** `02` §2 owns the `packs:` namespace and the allow-list; `03` → *Project
context* owns `weft.toml`'s scope. The correction belongs in those two sections, following
`README.md` → *Protocol* for a reference-document edit — not in this document, and not in the manual.
Until it is made, anything downstream shows **one** file and states the open question in a single
line.

