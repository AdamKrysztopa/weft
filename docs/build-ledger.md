# Build ledger

**Living — changes every task.** Unnumbered, like `README.md`, because it holds no design.

This file owns **task-level state and nothing else**: which task is next, what each one makes true,
which document owns its content, which fitness function it turns on, and the commit that closed it.

> **The rule that keeps this file true.** Every line is a **pointer**. If a task line explains *how*,
> it has started to duplicate the document that owns the content and it will drift from it — which is
> the failure `README.md` opens by describing, where the reference kept one list in two places. A task
> line may say *what is true when the task is done*; it may not say how to make it true.
>
> The other half of the same rule: **state moves, it is never copied.** The Phase 0 task boxes that
> used to live in `README.md` are here now, and they are not in both.

---

## The working protocol

One task at a time. This is the whole loop.

1. **Take the first unticked box.** If its phase is marked **⛔**, stop and say which gate is open.
   That is the answer, not an obstacle to route around — `01` → *Phases* is explicit that a gate is
   not advice.
2. **Orient with the `phase-step` skill.** Read the owning document named on the task line, the task
   after it, `06`'s three G2 traps and `06`'s scope fence. Do not reconstruct the design from code.
3. **Test first.** Write the test before the implementation, and **watch it fail for the right
   reason** — a test that passes against an empty implementation is testing nothing, and a test that
   fails with `ImportError` when you meant to check behaviour has not been read. Then implement until
   it passes. Shape, per `phase-step`: the mirroring path, happy path, one edge case, one error case,
   AAA with one block each, external services mocked. The `test-patterns` skill on this machine owns
   test-suite discipline; use it when a task's evidence needs more than one test.
4. **`uv run poe ci-checks` is green**, and any fitness function the task's *turns on* field names is
   wired into the composite **in the same commit**. Fitness function 0 fails otherwise, which is the
   point of it.
5. **Tick the box and record the sha**, and edit any document whose content the work changed. The
   plan and the code are meant to be true about each other.
6. **One commit per task.** The subject names the task id and what it makes true; the body says why.
   The diff already says what.

> **Test-first is the project owner's direction rather than the outcome of a grilling session** —
> recorded that way so its provenance is not mistaken for a gate's, in the same form `01` uses for
> requirement 6. It is not up for re-argument in a task, and it is not a gate either: no session
> settled it, so no session has to be reopened to change it.

**When a gate closes.** Every **⚠** task downstream of it is **re-derived from the reference document
the gate changed, never assumed**: un-tick anything the outcome invalidates, rewrite the task lines
that no longer state a true property, and drop the ⚠. This is `README.md` → *Protocol* → *When a
decision reopens* applied forward instead of backward — that rule already requires re-checking every
phase after a changed decision, and a gate closing changes a decision from *undecided* to *decided*,
which is the same cascade. (If `09-release.md` §6 takes ownership of that protocol, follow it there;
the owner moves, the rule does not.)

**When a task turns out to be wrong.** Rewrite the line, do not silently work something else. A task
whose property was mis-stated is information about the plan, and it goes to the document that owns
the content before any code is written to fit.

---

## How to read a task line

```
- [ ] **N.M ⚠** the property that is true once this is done · owner `02` §3 · turns on — · sha —
```

*(A shape, not a real task. A worked example copied from the list below would be a second copy of a
task line, and the first thing to drift when that task is edited.)*

| Field | Means |
|---|---|
| **id** | Stable. It never changes and is never reused, so a commit subject can name it forever |
| **⚠ provisional** | An open gate could change this task's *shape*. The task is real; its content is a hypothesis until the gate closes |
| the sentence | **What is true when the task is done** — a property, not an addition. If it reads as *"add X"*, it is the wrong sentence |
| **owner** | The document and section that owns the content. The task line is a pointer to it and holds no design of its own |
| **turns on** | The fitness function this task activates, wired into `ci-checks` in the same commit. `—` means none |
| **sha** | The single commit that closed it |

**Phase headers carry ⛔ when a gate the phase depends on is open.** A phase can be read at any time;
it cannot be *worked* while it is blocked.

---

## Phase 0 — Walking skeleton

**Gates: all settled.** G1 kernel boundary, G5 stage payload typing, G6 sync-or-async, G4 store
contract (before the store work), G3 plugin trust model (before discovery ships) — statuses in
`README.md` → *Decision log*, substance in `05`.

**Ids 0.1–0.11 mirror `06`'s steps 1–11 exactly**, so a task id and a build step are the same thing.
**0.0 is the scaffold**, which `06` covers in its preamble rather than as a numbered step. Ids
0.12–0.14 have no step in `06` either: they are the three manuals `08-manuals.md` assigns to Phase 0
without one, placed at the tail because nothing depends on them and they need only step 9.

**0.11–0.14 turn on nothing, and that is decision D1 rather than an omission.** The documentation
checks are ordinary tests under `tests/docs/`, swept into `ci-checks` by the existing `test` step —
not numbered fitness functions, which is what the *turns on* field means. Where a task makes one of
`08` §3's checks green, its owner column carries that clause's letter; a test path here would be a
second copy of the table `08` owns and would go stale the first time a file is renamed.

**⚠ on 0.2, 0.6 and 0.8** because those are precisely the three places `06` says Phase 0 can
accidentally settle **G2** — duplicate names, what a pipeline is before Phase 1, and where embedding
happens. Each carries a minimal reversible choice that is *not* an answer.

- [x] **0.0** the repository is several distributions and the gate refuses to be bypassed · owner `06` → *The order* preamble; `01` → *Fitness functions* 0, 1, 3 · turns on FF0, FF1, FF3 · sha `65612e6`
- [x] **0.1** G5 exists in code — a stage payload cannot be malformed rather than being validated · owner `06` step 1; `02` §1 → *The payload model* · turns on — · sha `fb4057d`
- [x] **0.2 ⚠** there is something to register into, and two packs claiming one name is refused with both distributions named · owner `06` step 2; `06` → *The three places…* item 3 · turns on — · sha `24aff26`
- [x] **0.3** every cross-cutting concern attaches without an author asking, so FF7(b) has somewhere to live · owner `06` step 3; `01` → *Fitness functions* 7(b) · turns on — · sha `7b2ea8b`
- [x] **0.4** a stage can be handed something, and nothing resolvable is a field · owner `06` step 4; `02` §1 → *What a plugin receives* · turns on — · sha `67e4702`
- [x] **0.5** an installed pack is discovered, a pinned-out pack is never imported, and FF2 becomes checkable · owner `06` step 5; `02` §2 → *The trust model* · turns on FF8(a) · sha `745f03e`
- [x] **0.6 ⚠** stages compose, and a mis-ordered list fails at resolution naming the stage, the namespace and the pack — not at runtime with a `KeyError` · owner `06` step 6; `06` → *The three places…* item 2 · turns on — · sha `de6718b`
- [x] **0.7** three contracts exist and the kernel names none of them, so FF2 and FF6 have subjects · owner `06` step 7; `02` §1 → *Who publishes a contract* · turns on — *(FF6 gains its first subject here; `01` states no activation phase for it, so this line does not claim one)* · sha `5d661fc`
- [x] **0.8 ⚠** indexing produces stored nodes, against one container, with a real vector from a real stage · owner `06` step 8; `01` → *Runtime shape*; `06` → *The three places…* item 1 · turns on — · sha `578d412`
- [x] **0.9** the product runs end to end, across exactly one bridge, and a registry-free command runs no pack code · owner `06` step 9; `03` → *Command surface* · turns on FF7(a), FF8(b) · sha `c66d844`
- [x] **0.10** the thesis is an artifact rather than a demo — a pack installed from outside the workspace is discovered and used with no edit under `packages/`, and uninstalling it fails resolution by name · owner `06` step 10; `01` → Phase 0 **Exit** · turns on FF9(a), FF9(b) · sha `7bf62d6`
- [x] **0.11** the thesis is not demonstrated once and left to age — a stranger's five-minute path and the pack author's walkthrough are reader-facing documents whose assertions keep getting checked · owner `06` step 11; `08` §1–§3 clauses (a), (c) · turns on — *(clause (a) ships with one named waiver — `install`, in `tests/docs/test_quickstart.py`'s `BLOCKS_WAIVED_FROM_EXECUTION` — because `weft-cli` is not on an index yet; it retires when `09-release.md`'s release policy publishes a version)* · sha `ce03dff`
- [x] **0.12** a contract's published reference cannot disagree with its own Protocol, because there is no second copy of a signature · owner `08` §1, §3 clause (b) · turns on — *(`08` §3 clause (b)'s check rides the existing `test` step rather than a numbered fitness function, per **D1**)* · sha `83a0f9e`
- [x] **0.13** an operator can run the one container, read a `doctor` status and act on an exit code without opening `docs/` · owner `08` §1–§2; `02` §2; `03` → *Output* · turns on — *(`08` §3's included-not-retyped check for this guide rides the existing `test` step rather than a numbered fitness function, per **D1**)* · sha `ce7cefc`
- [x] **0.14** a new failure mode cannot land in code with no entry describing what to do about it · owner `08` §1, §3 clause (d) · turns on — *(`08` §3 clause (d)'s coverage ratchet rides the existing `test` step rather than a numbered fitness function, per **D1**)* · sha `aeded62`

**Exit** (`01` → Phase 0): a plugin in a separate installed package is discovered and used with no
edit to the core package — task 0.10 — plus FF8(a), 8(b), 7(a), 2 and 9(b) wired and green, and
0.11's two checks green. The exit is `01`'s to state; this file only tracks the tasks that make it
true.

**No task line carries *turns on* FF2, and that was the gap the exit check found.** 0.5 says FF2
"becomes checkable" and 0.7 says it "has subjects"; neither is the same as turning it on, so
`tests/architecture/test_ff2_no_privileged_builtins.py` was written at the exit rather than inside a
task. Recorded here rather than back-dated into 0.5 or 0.7: a task line states what was true when
that task closed, and neither of those was false. The exit criterion caught what the ticked boxes
did not, which is why `01` states the exit separately from this list.

**Raised, not resolved.** `02` §2 puts the `packs:` settings block in `weft.yaml` and `[packs] allow`
in `weft.toml`, while `03` → *Project context* describes `weft.toml` as the project's defaults file
and `weft init` scaffolds it. The correction belongs to `02` §2 and `03` → *Project context*, per
`README.md` → *Protocol*; it is flagged here so it is not settled by accident inside a commit.

**Still open after 0.5, deliberately.** 0.5 did not pick a file, because it turned out not to need
one: `weft_kernel.discovery` reads no file at all. `allow_list_from_config` takes an already-parsed
mapping and `discover(pack_settings=…)` takes another, so the format question moves intact to
**0.9**, where the CLI is the only thing that opens a file. That is also the only answer G1 permits —
a YAML parser in the kernel would be a third dependency.

**Half-answered by 0.9, then completed by `ce03dff` — the file location still not in dispute.**
`weft_cli.registry_bootstrap` opens exactly one file, `weft.toml`, with `tomllib`. At 0.9 it read
only `[packs] allow` from it; both documents already agreed on that placement, so nothing was
settled by writing it. `ce03dff` added `pack_settings_from_config`, which reads every
`[packs.<distribution>]` table from the same parse — so the `packs:` *settings* block `02` §2
describes is now backed by a real loader, just keyed under `weft.toml` rather than `02` §2's
`weft.yaml`. The inconsistency between `02` §2 and `03` → *Project context* is about *which file*
carries the block, not whether one is read, and that question therefore survives `ce03dff` intact,
still owned by those two documents, still not to be settled inside a commit.

**Resolved by `ce03dff` and 0.13 (`ce7cefc`).** `weft.toml.example`, `compose.yaml` and `.env.example` used to
assert that `weft-store`'s `dsn` had "deliberately no default and no silent fallback to
`WEFT_DATABASE_URL`" and had to be wired through a project's `weft.toml`, while
`weft_cli.registry_bootstrap.pack_settings_from_environment` did the opposite: whenever
`WEFT_DATABASE_URL` was set, it handed `weft-store` `{"dsn": "${env:WEFT_DATABASE_URL}"}`
unconditionally, and nothing read a `[packs.<distribution>]` block from any file at all — so a
`weft.toml` carrying a different `dsn` under `[packs.weft-store]` was silently ignored rather than
honoured or refused. `ce03dff` made the file win over the environment key by key —
`weft_cli.registry_bootstrap.merged_pack_settings` now reads `[packs.<distribution>]` from
`weft.toml` and lets the environment fill only the keys the file leaves unsaid. `ce7cefc` corrected
`weft.toml.example`, `compose.yaml` and `.env.example` to describe that precedence instead of the
stale "no silent fallback" claim. Verified from a scratch directory outside the repository, after
both: with `WEFT_DATABASE_URL` exported and a `weft.toml` naming a different, unreachable `dsn`
under `[packs.weft-store]`, `weft plugins doctor` reports `weft-store: active` and `weft ask` fails
to connect to the database `weft.toml` named — the file's value is the one in play, exactly as the
three files now say.

---

## Phase 1 — Pipelines as data

**⛔ Blocked by G2** — pipeline derivation semantics, Open. `05` → G2 owns the overlay semantics, the
multi-level conflict rules, the ordering-constraint question, and **whether pipelines are authored in
YAML, Python or both**. Every task below is **⚠**: a Phase 1 task list written before G2 is a
hypothesis, and saying so is the point.

- [ ] **1.1 ⚠** a pipeline is a value that can be diffed, versioned and generated — in whatever form G2 settles on · owner `02` §3 · turns on — · sha —
- [ ] **1.2 ⚠** an inserted stage cannot silently corrupt text, because ordering is a declared constraint rather than a docstring · owner `02` §3 → the ordering-constraint finding · turns on — · sha —
- [ ] **1.3 ⚠** a derived pipeline resolves to a frozen, fully-explicit form with no inheritance left to interpret, and everything it can be wrong about is wrong before it runs · owner `02` §3 → *Derivation* · turns on — · sha —
- [ ] **1.4 ⚠** a derived pipeline changes its parent by operator and never by copy, so improvements to the parent reach it · owner `02` §3 → the operator table · turns on — · sha —
- [ ] **1.5 ⚠** a stage's `with:` block is validated against the plugin's own typed model at resolution, so the same plugin can run twice with different configuration · owner `02` §1 (contract rules), §3 → the `with:` note · turns on — · sha —
- [ ] **1.6 ⚠** the shipped ingest pipeline carries stage 0 and stage 4.5 as stages, in whichever order G2 adopts · owner `01` → *The architecture stack*, Data-row note; `04` category B · turns on — · sha —
- [ ] **1.7 ⚠** the cleaning chain's learned order survives the lift as a machine-checked constraint, not as prose — including the Polish fused-word exception set · owner `04` category B; `01` → Phase 1 **Lift** · turns on — · sha —
- [ ] **1.8 ⚠** a language-conditional stage is expressible in pipeline data instead of hardcoded inside a generic stage · owner `02` §3 → the language-conditional finding · turns on — · sha —
- [ ] **1.9 ⚠** driving use case A works from configuration — `specific` extends `base` with KeyBERT after `chunk`, no change to core, no copy of the parent — as an automated test · owner `01` → Phase 1 **Exit**; `02` §3 · turns on — · sha —
- [ ] **1.10 ⚠** someone using Weft day to day can derive a pipeline from the manual alone · owner `08` §1–§2, *User manual* · turns on — · sha —

**Exit** (`01` → Phase 1): task 1.9.

---

## Phase 2 — Retrieval and generation

**Gate: none.** `01` says reopen **G5** only if a strategy cannot express what it needs to pass along
— if that happens, stop and reopen it rather than widening the payload in a commit. **G2 still shapes
how a query path is expressed as data**, which is why 2.7 and 2.15–2.19 carry **⚠** — `10` §3.3 owns
the reason those five and no others.

> **The technique block (2.13–2.26) is worked between 2.4 and 2.8, and it is `01` → requirement 6's
> only representation in this phase.** 2.4 is the mechanism; without 2.13–2.26 the mechanism is empty
> and 2.8 can go green over two strategies.

**V1–V3 come first, and they are not paperwork.** `09` §4 requires them *before this phase can be
judged*: retrieval and fusion decisions made without them are unmeasured by construction. V3's
baseline is a measurement here; Phase 4 re-runs it as a persisted run (V6). `09` §4 requires both and
does not merge them.

- [ ] **2.1** a bounded, named corpus exists that covers every format an installed extractor claims, including one non-English body · owner `09` §4, V1 · turns on — · sha —
- [ ] **2.2** every question carries ground truth with recorded provenance, and unanswerable questions are among them · owner `09` §4, V2 · turns on — · sha —
- [ ] **2.3** a baseline exists that was run more than once and records, per metric, the interval its own repetitions spanned — so a later run can be judged without anyone choosing a number · owner `09` §4, V3 and the derived-tolerance rule · turns on — · sha —
- [ ] **2.4** a retrieval strategy is a plugin published by a pack, with domain types on both sides · owner `02` §1; `01` → Phase 2 **Read** · turns on — · sha —
- [ ] **2.5** a retriever never builds its own index, because text search is something a store advertises · owner `02` §1 → *The store contract family*; `01` → *Runtime shape* · turns on — · sha —
- [ ] **2.6** the store contract is satisfied by a second backend of a genuinely different shape, so it is no longer a guess · owner `01` → *Runtime shape*; `06` → *What Phase 0 must not build* · turns on — · sha —
- [ ] **2.7 ⚠** fusion and reranking are composable plugins a third party can retune, not a fixed ladder · owner `04` category B; `01` → requirement 6 · turns on — · sha —
- [ ] **2.8** the router picks a strategy it was never told about — discovered from the registry, with no enum, no if-chain and no closed key space anywhere a name is decided · owner `01` → Phase 2 **Exit**; `01` → *Fitness functions* 4 · turns on FF4(a), FF4(b) *(`01` states no activation phase for 4; placed here because this is its first real selection surface — if that is wrong, it is `01`'s to correct)* · sha —
- [ ] **2.9** an answer carries citations a reader can follow back to a passage · owner `04` category B, the citation manager's four responsibilities · turns on — · sha —
- [ ] **2.10** generation is a pack — the prompt layer, the cascade, model strings and the `LLMError` taxonomy ship outside the kernel · owner `04` → *Kernel or pack*; `01` → Phase 0 **Lift** · turns on — · sha —
- [ ] **2.11** every contract this phase publishes has an implementation living outside the workspace · owner `07` §2, clause 9(c); `01` → Phase 2 **Exit** · turns on FF9(c) · sha —
- [ ] **2.12** the contract reference and the operations guide describe what this phase published, without a human retyping a signature or a status name · owner `08` §1–§2 · turns on — · sha —
- [ ] **2.13** the null case is a plugin like any other, and an empty source list is a stated property of it rather than a retrieval failure a consumer has to guess at · owner `10` §1.1; `02` §1 · turns on — · sha —
- [ ] **2.14** the single-pass baseline is a plugin whose name states its cost, so an operator choosing what to run in a loop is not misled by the registry · owner `10` §1.1, §2.1 rule 4 · turns on — · sha —
- [ ] **2.15 ⚠** a query transform is a composable stage a caller can omit, so no strategy pays for a rewrite it did not ask for · owner `10` §1.1; `02` §1; `02` §3 · turns on — · sha —
- [ ] **2.16 ⚠** `hyde` runs in front of any retrieval rather than inside one strategy, and its sample count, query inclusion and failure behaviour are configuration · owner `10` §1.1; `01` → requirement 6, second clause · turns on — · sha —
- [ ] **2.17 ⚠** `step-back` is the same technique whether tokens arrive at once or one at a time · owner `10` §1.1; `01` → *Colour*, the streaming consequence · turns on — · sha —
- [ ] **2.18 ⚠** query fan-out and rank fusion are two plugins, so the fuser serves hybrid retrieval and fan-out from one implementation · owner `10` §1.1; task 2.7 · turns on — · sha —
- [ ] **2.19 ⚠** context ordering is a named, parameterised stage whose method does what the method is named after · owner `10` §1.1, the `repack` row · turns on — · sha —
- [ ] **2.20** an evidence-sufficiency loop is expressible, and its stopping rule is one named, testable thing rather than four scattered breaks · owner `10` §1.1, the `iterative-retrieval` row · turns on — · sha —
- [ ] **2.21** per-document relevance grading is a reusable post-retrieval filter, and a knowledge action that reaches a second retriever is what earns the name `corrective` · owner `10` §1.1, the `corrective` row and its condition; `02` §1 · turns on — · sha —
- [ ] **2.22** a query about whether the sources agree is answerable, and a critic that could not look says so instead of reporting agreement · owner `10` §1.1, the `contradiction-check` row · turns on — · sha —
- [ ] **2.23** a Boolean query is parsed to an operator expression with precedence, and an empty conjunction is a visible outcome rather than a union · owner `10` §1.1, the `boolean-retrieval` row · turns on — · sha —
- [ ] **2.24** a draft's uncertainty is a replaceable, named signal rather than a phrase list, so the trigger cannot break silently under another language or model · owner `10` §1.1, the `refine-on-uncertainty` row · turns on — · sha —
- [ ] **2.25** query scoring and routing policy are two plugins, so a threshold ladder can be replaced by a trained classifier without touching the scorer · owner `10` §1.1, the `query-scorer` row; `04` category B, the `AdaptiveRouter` row · turns on — · sha —
- [ ] **2.26** every strategy this phase ships is named for the technique it implements, and no name claims a paper the code does not implement · owner `10` §1.4, §2 · turns on — · sha —

**Exit** (`01` → Phase 2): task 2.8, plus FF9(c) wired and green (task 2.11).

**Raised, not resolved.** `01` → Phase 0 **Lift** lists the prompt layer, the three-tier cascade,
model strings and the `LLMError` taxonomy as category-A lifts, while `06` → *What Phase 0 must not
build* assigns generation, prompts, the LLM adapter and `weft-llm` to Phase 2. Task 2.10 places them
here. The discrepancy belongs to `01` and `06` and is flagged rather than decided.

---

## Phase 3 — The CLI

**⛔ Blocked by G8** — is the REPL agentic, Open. `01` is explicit: if the answer is anything but
"shell", stop and hand off to the `agentic-patterns` skill before writing the loop. Every task whose
shape the loop decides is **⚠**.

- [ ] **3.1** a pack registers a command exactly as it registers a retriever, and a command that declares no permission class fails to register while its author is standing there · owner `03` → *Plugin-contributed commands*, *Permissions*; `02` §1 · turns on — · sha —
- [ ] **3.2** `weft --help` cannot drift from what is installed, because core has no command list to edit · owner `03` → *Plugin-contributed commands* · turns on — · sha —
- [ ] **3.3** a destructive operation with no TTY fails naming the flag that would permit it, and never proceeds silently · owner `03` → *Permissions* · turns on — · sha —
- [ ] **3.4 ⚠** the interactive session and the one-shot invocation are the same commands with a different renderer, not two implementations · owner `03` → *Two modes, one implementation*; `05` → G8 · turns on — · sha —
- [ ] **3.5 ⚠** session state is explicit and inspectable, so the same command does not behave differently for two people · owner `03` → *In-session commands* · turns on — · sha —
- [ ] **3.6** tokens reach a reader as they arrive, through a resolved service rather than a second set of contracts · owner `01` → *Colour*, the streaming consequence; `02` §1 · turns on — · sha —
- [ ] **3.7** the rest of the command surface exists — `init`, `pipeline list|show|derive|validate|diff`, `config get|set` — and `pipeline diff` is an exact comparison because resolution is fully explicit · owner `03` → *Command surface* · turns on — · sha —
- [ ] **3.8** a plugin's command appears in `--help` and in completion without core knowing it exists, as an automated test · owner `01` → Phase 3 **Exit** · turns on — · sha —
- [ ] **3.9 ⚠** the user manual's command table is generated from the registry rather than maintained, and the contract reference covers `Command` · owner `08` §1–§2, §3 clause (b) · turns on — · sha —

**Exit** (`01` → Phase 3): task 3.8.

---

## Phase 4 — Evaluation and observability

**Gate: none.**

- [ ] **4.1** a metric is a plugin, and the same metric runs twice at two thresholds because its registration carries a typed configuration model · owner `02` §1; `01` → requirement 6, second clause · turns on — · sha —
- [ ] **4.2** the reference's metric suite ships with every recorded defect fixed at the door rather than inherited, and no ratio is a number a model computed · owner `04` → the metric-suite entry; `01` → Phase 4 **Lift** · turns on — · sha —
- [ ] **4.3** a metric's failures are distinguishable from its bad scores, and no reported number stands without the dispersion it was measured with · owner `09` §4, V4 · turns on — · sha —
- [ ] **4.4** a run is persisted carrying its resolved pipeline, corpus identity, model versions and the active distribution set, so two runs can be diffed after the fact · owner `01` → Phase 4 **Exit**; `01` → *Fitness functions* 8(c) · turns on FF8(c) · sha —
- [ ] **4.5** a stage's duration and attribution are visible in a trace without any pack exporting a span by hand · owner `01` → *The kernel boundary* (exporters are packs); `06` step 3 · turns on — · sha —
- [ ] **4.6** `weft eval run|compare` and `weft trace` let an operator ask what a run actually did · owner `03` → *Command surface* · turns on — · sha —
- [ ] **4.7** one full run can be priced in money and wall-clock, its providers and model versions are pinned, and a deterministic subset runs in the gate with no credentials and no network · owner `09` §4, V5 · turns on — · sha —
- [ ] **4.8** the published baseline is a persisted, reproducible run rather than terminal output · owner `09` §4, V6 · turns on — · sha —
- [ ] **4.9** running one corpus through two derived pipelines produces a comparison the tool generates itself · owner `01` → Phase 4 **Exit** · turns on — · sha —
- [ ] **4.10** the contract reference covers `Metric`, and the operations guide covers persisted runs and `weft trace` · owner `08` §1–§2 · turns on — · sha —

**Exit** (`01` → Phase 4): task 4.9, with both runs persisted (4.4), plus FF8(c) wired and green.

---

## Phase 5 — The independence test

**⛔ Blocked by G7 and G9** — event bus or explicit extension points, and contract versioning and
deprecation. Both Open. G9 is the harder blocker: it is also Phase 6's precondition, and `09` §2
records five separate places a release policy would settle it by implication.

**This phase's exit is a person, not a test**, so most of these tasks make *someone else's* work
possible rather than adding a feature.

- [ ] **5.1 ⚠** a pack can participate where it has no extension point — or it provably cannot, and that is written down · owner `05` → G7; `01` → *The least-architecture check* · turns on — · sha —
- [ ] **5.2 ⚠** G9's compatibility policy is implemented rather than only written — every published contract's promise is machine-visible · owner `05` → G9; `01` → *Fitness functions* 6 · turns on — · sha —
- [ ] **5.3 ⚠** a stranger has everything they need before they start: the pack author guide covers a pack spanning several contracts plus a contributed command, adapted from the case `02` §4 already owns · owner `08` §1–§2; `02` §4 · turns on — · sha —
- [ ] **5.4 ⚠** the graph pack registers four things from one install, with one entry point, one `register()` and one settings model · owner `02` §4 → the registration table · turns on — · sha —
- [ ] **5.5 ⚠** the pack ships a derived pipeline as data that users can derive from further · owner `02` §4; `02` §3 · turns on — · sha —
- [ ] **5.6 ⚠** uninstalling the pack fails resolution with a message naming the missing plugin and the pack that provides it · owner `02` §4 · turns on — · sha —
- [ ] **5.7 ⚠** the pack was built by someone who has not touched core, and they never needed to — every request for a core change recorded as a design finding rather than closed as a feature request · owner `01` → Phase 5 **Exit**; `02` §4 → *The independence test* · turns on — · sha —

**Exit** (`01` → Phase 5): task 5.7. A core change requested to make the pack work is a Phase 5
failure and a design finding, which means 5.7 can be *failed* — that is what makes it worth running.

---

## Phase 6 — Release

**⛔ Blocked by G9 and G10** — G10 (the release and support policy) is proposed by `09` and logged
Open when `09` lands, and it cannot be run until G9 has settled, which Phase 5 already requires.
Stating a user-facing release promise before G9 would settle G9 by implication rather than by
argument.

**⚠ marks the four tasks whose shape G9 or G10 decides** — the unit of release itself, the doctor's
behaviour on skew, the deprecation clock's unit, and what a *release* names when the exit criterion
installs one. `09` §1 **recommends** the unit and argues for it; it does not decide it, so 6.1's
property is a hypothesis until G10 closes. The reproduction tolerance is not among the four: `09` §4
derives it from the baseline's own recorded interval rather than from any gate, which is the point of
deriving it. The two fitness-function clauses carry none: `09` argues both hold under every position
G9 and G10 can take, which is the reason they are stated as weakly as they are.

- [ ] **6.1 ⚠** a release is a named, tested set rather than a wheel · owner `09` §1 · turns on — · sha —
- [ ] **6.2** the publish set and the workspace agree, computed from different sources, and the canary is never on an index · owner `09`; `01` → *Fitness functions* 10(a) · turns on FF10(a) · sha —
- [ ] **6.3** no distribution depends on a sibling without a version bound, so a compatibility policy has something to rest on · owner `01` → *Fitness functions* 10(b) · turns on FF10(b) · sha —
- [ ] **6.4 ⚠** every first-party pack is `active` at the version the release names, and `weft plugins doctor` can *say* what is installed — whether it also flags a mismatch, and what a mismatch does, are G9's · owner `09` §1, and `09` §2's table of what Phase 6 needs from G9 · turns on — · sha —
- [ ] **6.5 ⚠** every deprecated surface names the release or date at which it is removed, in the unit G9 chose, and the clock is observable · owner `09` §3 · turns on — · sha —
- [ ] **6.6** every published distribution installs alone into a clean environment and imports — fitness function 1's primary half applied to all of them, not only the kernel · owner `09` §5 → *Install path* · turns on — · sha —
- [ ] **6.7** the sdist builds and its tests pass from the sdist, so nothing load-bearing is present in the checkout and absent from the artefact · owner `09` §5 → *Install path* · turns on — · sha —
- [ ] **6.8** a cancelled run leaves the store durable to its last finished batch, a resumable delete finishes on the next command, and a store written by release *n* is read by release *n+1* — executed once, not asserted · owner `09` §5 → *Operability* · turns on — · sha —
- [ ] **6.9** every shipped technique's claimed improvement is a delta against the published baseline on the same corpus, pipeline and model versions · owner `09` §4, V3; §5 → *Quality* · turns on — · sha —
- [ ] **6.10** the published trust posture is the one `02` §2 actually claims — no package page implying isolation the design refused · owner `09` §5 → *Security, licensing, documentation*; `02` §2 · turns on — · sha —
- [ ] **6.11** every file in the release is accounted for as original work, re-checked with `reference-audit`, with `LICENSE` and `NOTICE` in every built artefact · owner `09` §5; `CLAUDE.md` → the originality rule · turns on — · sha —
- [ ] **6.12** a newcomer installs, indexes and asks from the README alone, without opening `docs/` · owner `09` §5; `08` §1, *Quickstart* · turns on — · sha —
- [ ] **6.13 ⚠** a machine that has never seen this repository installs the release unit G10 names, from the index, and reproduces the published baseline — every metric inside the interval that baseline recorded across its own repetitions · owner `01` → Phase 6 **Exit**; `09` §4 · turns on — · sha —

**Exit** (`01` → Phase 6): task 6.13, plus FF10 wired and green and each of Phases 0–5's exit criteria
re-demonstrated against installed wheels rather than the working tree.

---

## Why the sha column is not optional

A ticked box with no sha is a claim; a ticked box with a sha is a fact someone else can check. The
shape being refused is the reference's only key-parity test, which computes a difference and then reports
it through `pytest.warns(...)` called as a bare statement, so it does nothing and **cannot fail** —
*"the 195/195 parity holds today by discipline, not by enforcement"*
(`reference/study/08-salvage.md:777-782`). A ledger whose ticks cite nothing is that test with a
different subject.

**As of the last edit to this file, the tree was at `aeded62`.** Tasks are ticked by the commit that
closes them, so this line is the only place a date-shaped claim appears — everything else is a sha.
