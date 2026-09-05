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
2. **Orient with the `phase-step` skill.** Read the owning document named on the task line and the
   task after it. For a Phase 0 task only, also read `06`'s three G2 traps and `06`'s scope fence —
   `06` is Phase 0's own retired build order (`README.md` → *Documents*), historical for every later
   phase now that G2 has settled. Do not reconstruct the design from code.
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

   **The recorded sha is the pre-amend object, and that is the best this can be.** This step used
   to ask for "the hash of the commit that carries the line", reachable "by committing and then
   amending" — which is not achievable by anything: a commit cannot contain its own hash, and the
   amend that writes the sha in changes the hash again. The rule was corrected on **2026-08-20**,
   after every task in Phase 3 rediscovered the contradiction independently and wrote a paragraph
   explaining it. What 2.4 and 2.29 were "corrected" for was therefore not a mistake either.

   So: commit, then amend the ledger line with the sha the first commit produced, and understand
   that the recorded hash names an object one generation behind `HEAD`. Do not spend time trying
   to close the gap. **Do not run `git merge-base --is-ancestor` against it** — it will fail
   correctly, which is not information. The per-task sha's real audience is a reader tracing the
   work inside a live branch; once the phase is squashed onto `main` every one of them dangles
   anyway, which is why **the phase's squash commit carries the true per-task hashes in its
   message** — that, not the ledger field, is where they survive.

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

**Unblocked — G2 settled 2026-08-16.** Every task below has been **re-derived from `02` §3 as it now
reads**, per *When a gate closes* above, and the ⚠ dropped. Four lines changed shape rather than
wording: **1.6** no longer says "stage 0 and 4.5 as stages" (neither is a stage — one became
applicability, the other was already a seam concern), **1.8** no longer asks for a conditional in
pipeline data (the condition moved onto the node), and **1.1** and **1.2** now name the mechanisms G2
chose instead of deferring to it. Five tasks are new: 1.11–1.15.

The model is deliberately built once for both paths — a query pipeline is a pipeline, typed by its
endpoints — which is why Phase 2's ⚠ on 2.7 and 2.15–2.19 clears without Phase 2 inventing anything.

- [x] **1.1** a pipeline is a frozen Pydantic model the kernel publishes, which YAML deserialises into and Python constructs directly — one validator, one error set, no builder DSL · owner `02` §3 → *One model, two directions* · turns on — · sha `776e78e`
- [x] **1.2** an inserted stage cannot silently corrupt text, because a stage declares the properties it needs `intact` and the ones it `destroys`, and a contract that publishes a property vocabulary gets its implementations' `destroys` refused at registration when omitted · owner `02` §3 → *Ordering constraints* · turns on — · sha `273e49b`
- [x] **1.3** a derived pipeline resolves to a frozen, fully-explicit form with no inheritance left to interpret — carrying each stage's provenance, every var's final value, unplaced contributions and unapplied operators — and everything it can be wrong about is wrong before it runs · owner `02` §3 → *Derivation*, *When resolution fails* · turns on — · sha `2c42cbe`
- [x] **1.4** a derived pipeline changes its parent by operator and never by copy, at any depth through one parent, with a cycle and every stale operator target refused by name · owner `02` §3 → the operator table and its edge rules · turns on — · sha `0cd6e39`
- [x] **1.5** a stage's `with:` block is validated against the plugin's own typed model at resolution, so the same plugin can run twice with different configuration · owner `02` §1 (contract rules), §3 → the `with:` note · turns on — · sha `b9a4598`
- [x] **1.6** an atomic node passes the chunker unsplit **without the chunker knowing what atomic means**, because applicability is declared and routed at the seam · owner `02` §3 → *Applicability*; `11` §2 · turns on — · sha `22b2183`
- [x] **1.7** the cleaning chain's learned order survives the lift as a machine-checked constraint, not as prose — including the Polish fused-word exception set · owner `04` category B; `01` → Phase 1 **Lift** · turns on — · sha `d9f1684`
- [x] **1.8** a language-specific stage applies per **node** rather than per run, so one pass over a mixed corpus is correct for every document, and the decision half — a translation target — is a var · owner `02` §3 → *Language, and what a var is for* · turns on — · sha `da202d1`
- [x] **1.9** driving use case A works from configuration — `specific` extends `base` with KeyBERT after `chunk`, no change to core, no copy of the parent — as an automated test · owner `01` → Phase 1 **Exit**; `02` §3 · turns on — · sha `3f35845`
- [x] **1.10** someone using Weft day to day can derive a pipeline from the manual alone · owner `08` §1–§2, *User manual* · turns on — · sha `97c843c`
- [x] **1.11** an installed pack changes an existing pipeline only where that pipeline declared a slot, two contributions in one slot are ordered by declaration and then by distribution name, and a contribution that lands nowhere is recorded rather than silent · owner `02` §3 → *Slots* · turns on — · sha `a7d0767`
- [x] **1.12** two packs claiming one `(contract, name)` is refused at registration with the pin that resolves it printed, and the displaced registration is recorded and reported by doctor · owner `02` §3 → *When resolution fails*; `02` §2 · turns on — · sha `9635710`
- [x] **1.13** every way resolution can fail is its own `WeftError` subclass carrying the pipeline, the stages, the distributions in conflict and the remedy — so each one enters the 0.14 ratchet and cannot ship undocumented · owner `02` §3 → *When resolution fails*; `08` §3 · turns on — · sha `527be06`
- [x] **1.14** a var overridden by a child re-resolves every inherited stage that references it, and no var can reach applicability · owner `02` §3 → *Language, and what a var is for* · turns on — · sha `e8317f2`
- [x] **1.15** a fifth operator cannot land silently, and a pipeline shipped by any pack or quoted as runnable in a manual cannot rot unnoticed · owner `01` → *Fitness functions* 11 · turns on **FF11(a), FF11(b)** · sha `04c1333`
- [x] **1.16** a `weft.toml` whose `packs` value is not a table is refused by name, saying the file, the key and the shape expected, rather than being treated as absent · owner `02` §2 → *The trust model* · turns on — · sha `3bdcd12`
- [x] **1.17** no document assigns work to a phase that has exited · owner `01` → *Phases*; `04` → *Kernel or pack* · turns on — · sha `1321992`
- [x] **1.18** no file in the tree says Weft copied anything, and no fitness function can pass because its walk found nothing · owner `01` → *Fitness functions*; `NOTICE` · turns on — · sha `6a37822`

**1.16–1.18 are carried-debt tasks, not new scope.** A reference audit run against HEAD `0068595` found
three gaps that predate this ledger line and that nothing in Phase 0 or Phase 1 so far was asked to
close. They sit here, at the tail of Phase 1's list, rather than in a reopened Phase 0, for the same
reason 0.12–0.14 sat at Phase 0's own tail: Phase 0's exit criterion — a plugin in a separate
installed package works with zero edits to core — still holds, and none of the three falsify it: a
malformed `packs` table, a document naming a phase that has exited, and an unstated originality claim
are all things Phase 0 was never asked to check, not things it got wrong. They are **not** part of
Phase 1's exit, which remains task 1.9 plus fitness function 11 — exactly as it was before this note
was added.

**Exit** (`01` → Phase 1): task 1.9, **and 1.15** — fitness function 11 wired and green.

**Settled by 1.4 — the operators' serialisation, raised by 1.1 and left open.** `02` §3 says operators
"apply in written order", and that a `remove` followed by an `insert` is how a move is expressed;
the same section's `specific.yaml` shows them as top-level keyed blocks. Four independent model
fields cannot honour both, because a model's field order is fixed once for every document: whichever
order the fields are declared in is the order every author gets, so one of *remove-then-insert* and
*insert-then-remove* on the same id would become unwritable if application order were assumed from
field position. 1.1 therefore carried **no operator field at all** — `extra="forbid"` refused one by
name rather than half-reading it — leaving the shape to 1.4. It stays **four keyed blocks**, exactly
as `specific.yaml` prints them, never flattened into one tagged sequence; what 1.4 added is that
application order is *read off the document's own key order* (and, identically, a Python call's
keyword-argument order) rather than assumed from the model — `weft_kernel.pipeline.Pipeline.
operator_order`, consumed by `weft_kernel.resolution._apply_operators`. See `02` §3, the paragraph
immediately after the operator table.

**Also raised by 1.1 — a malformed pipeline document has no exit code and no manual entry yet.** The
authored form's error set is pydantic's `ValidationError` (`02` §3 → *One model, two directions*,
which now carries the reasoning), and that is neither a `WeftError` nor a member of the
`PipelineResolutionError` family — so `03`'s exit 4 for *fix the pipeline* does not reach it and
0.14's coverage ratchet, which derives its required set from `WeftError` subclass names, cannot see
it. No path reaches it today: nothing opens a pipeline file until **1.9**. Whichever task first
hands a document to the CLI owns the translation and the `manual/troubleshooting.md` entry — a note
here rather than a fix at 1.1, because the kernel decides no exit codes.

---

## Phase 2 — Retrieval and generation

**Gate: none.** `01` says reopen **G5** only if a strategy cannot express what it needs to pass along
— if that happens, stop and reopen it rather than widening the payload in a commit. **G2 settled how
a query path is expressed as data (2026-08-16): it is a pipeline, in the same model as ingest**, so
the ⚠ on 2.7 and 2.15–2.19 is cleared — those five stay written as they are, and what changes is that
they are no longer hypotheses. `10` §3.3 owns the reason those five and no others carried it.

> **The technique block (2.13–2.26) is worked between 2.4 and 2.8, and it is `01` → requirement 6's
> only representation in this phase.** 2.4 is the mechanism; without 2.13–2.26 the mechanism is empty
> and 2.8 can go green over two strategies.

**V1–V3 come first, and they are not paperwork.** `09` §4 requires them *before this phase can be
judged*: retrieval and fusion decisions made without them are unmeasured by construction. V3's
baseline is a measurement here; Phase 4 re-runs it as a persisted run (V6). `09` §4 requires both and
does not merge them.

- [x] **2.1** a bounded, named corpus exists that covers every format an installed extractor claims, including one non-English body · owner `09` §4, V1 · turns on — · sha `f6b31e2` · **V1 is satisfied by the `fetch` and `gate` tiers alone**, and the six copyrighted papers form an `operator` tier — named and checksummed so a local copy can be verified, never fetched, outside V1's reproducibility clause. **No waiver of V1 is taken and none is logged.** The published baseline is measured on the reproducible tiers, because Phase 6's exit is a stranger reproducing it
- [x] **2.2** every question carries ground truth with recorded provenance, and unanswerable questions are among them · owner `09` §4, V2 · turns on — · sha `4c8a36a` · **A quote is believed only because the gate read it back out of the corpus.** Every supporting span is checked as an exact substring of the document it names, and its page against that document's own page boundaries — these questions were verified by the agents that wrote them, and five spans and five page numbers were still wrong. A run that holds only part of the corpus, which is every machine but the author's, **reports how many quotes it compared and which documents it could not open**, so a partial pass never reads as a whole one. **Which questions a stranger can score is derived from the manifest's tiers**, never written on a question, and the published baseline is measured on that subset alone
- [x] **2.3** a baseline exists that was run more than once and records, per metric, the interval its own repetitions spanned — so a later run can be judged without anyone choosing a number · owner `09` §4, V3 and the derived-tolerance rule · turns on — · sha `2ae66a1` · **Two artefacts, never one** (`.phase2-findings.md` §15): the run over the `fetch` tier is measured on the 95 questions a stranger can score and is the one that may be published, because Phase 6's exit is somebody else reproducing it; the run over `fetch,operator` covers all 136, is written `"reproducible": false` and says `unreproducible` in its own file name. **The flag is derived, never declared** — `Tier.reproducible` now lives on the manifest reader that owns the enum, and `tests/docs/test_corpus_manifest.py` and `test_question_set.py` read it instead of each keeping a copy of the same fact · **the tolerance is the interval three repetitions actually spanned, and every one of them is zero-width**: retrieval through `openai` + `qdrant` was identical across all three passes, which `09` §4.3 calls correct and strict — a later run reproduces this baseline by matching it, and `eval/check_baseline.py` refuses the comparison outright (exit 2) when corpus id, pipeline digest, models or depth differ, rather than producing an ordinary-looking number for a different measurement · **a retrieval baseline, and it says so**: `weft ask` retrieves and does not generate — 2.9 is unbuilt — so the generation-side stance number V3's neighbours will want is **not measured** rather than approximated, and the 17 unanswerable questions are excluded with a reason recorded per exclusion, never scored `0.0` (V4's rule, honoured now because the intervals would otherwise be contaminated) · **two granularities, neither a fallback for the other**: `quote-*` counts a passage containing the ground-truth span, `document-*` one drawn from the right paper. The reference's paper-level fallback was a *silent* substitution when span resolution failed; reporting both under names that state the granularity is what stops that recurring, and `eval/metrics.py` states the `quote-*` floor outright — a span crossing a chunk boundary cannot be contained by any single retrieved passage · **`weft ask --format json` is the only CLI addition**, dated in `03` → *Output*: the harness drives `weft` as a subprocess because FF7(a) permits no second `asyncio.run` under `eval/`, so it has to read what the command printed. `AskFormat` lives in `weft_cli.output` rather than beside the renderer, because `build_parser` runs for `weft --version` too and that command may execute no pack code (FF8(b)) · **found here, not fixed here**: `weft-qdrant` writes a batch in one request, and sixteen papers at once exceeded Qdrant's 32 MiB limit — the HTTP 400 surfaces as `'store' failed:` **with no reason at all**, because the driver's exception stringifies to nothing. The harness indexes one document per invocation; the empty reason belongs to `weft-qdrant`'s owner and is recorded rather than papered over
- [x] **2.4** a retrieval strategy is a plugin published by a pack, with domain types on both sides · owner `02` §1; `01` → Phase 2 **Read** · turns on — · sha `4b9cb12` · **multiplicity lives in the payload type, and the kernel's own composition check was re-verified against it rather than assumed**: `QuerySet` means n queries, `Candidates` means k ranked lists, `Ranking` means one, so every query-path stage is a plain `Stage[In, Out]` in one ordered list and no combinator exists. The four-stage baseline and the seven-stage derived pipeline both compose through the real `weft_kernel.resolution.resolve` *and* the real `Runner.resolve`; rerank-before-fuse, rerank-before-retrieve, generate-before-pack and two retrievers in a row are each refused by both, naming the pair. **G5 is not reopened and nothing was widened**: the `Ranking` narrowing `.phase2-design.md` §15 flags — fusion keeps `Passage.retrieved_by` and throws away which *query* found which hit — is stated in `weft_retrieve.payload`'s own module docstring as the trigger to stop and re-open G5, and no technique built here needed it. **Scoped, deliberately**: `weft-retrieve` and `weft-generate` register nothing and declare **no `weft.packs` entry point**, because fitness function 2 requires every distribution declaring one to be active *and contributing* — the plugins are 2.9 and 2.13–2.26, and `docs/build-ledger.md`'s own note above says this task leaves the mechanism empty. `Citation.source_id` is `SourceId | None`, against the design record, because a `Node.synthetic` root genuinely has no source and inventing one is a citation a reader can follow nowhere · **two further departures from `.phase2-design.md`, on repair 2026-08-17**: (1) `RoutingPolicy.reachable` is `async def`, where the design record calls it "deliberately sync" — `01` → *Colour* is categorical for a **contract** method, the seam wraps a coroutine, and a sync method on a registered contract runs with no span, no error attribution and nothing FF7(b) can see; that file's own status line says `docs/` wins. (2) `Query.channels` and `RankedList.channel` are `str`, not `Channel` — the enum stays as the two names first-party code writes, because `02` §1 opens the store family on graph traversal and `01` requirement 2's worked example is a graph add-on registering a retriever, so a closed member set would leave that pack's ranked lists nothing honest to say about which arm produced them. **Recorded, not fixed**: a plugin name registered under two contracts is refused by `weft_cli.compile` with **no operator-side remedy** — no `contract:` key on a stage, and a `[plugins]` pin is keyed to arbitrate a same-key fight, so one written for a cross-contract clash goes inert. Widening the pin key space or the grammar is G2's and 2.8's; the cost is stated in that module's docstring. **An obligation 2.13–2.26 inherit**: `QuerySet.origin` is a contract term nothing checks — `frozen=True` stops mutation, not substitution, and every stage here builds its output wholesale — so each first-party query-path plugin carries its own `out.origin == in.origin` assertion, which is the only thing standing between `hyde` and the reference's cross-encoder-scores-a-hallucination defect
- [x] **2.5** a retriever never builds its own index, because text search is something a store advertises · owner `02` §1 → *The store contract family*; `01` → *Runtime shape* · turns on — · sha `aab734d` · **the index is the store's, and it cannot go stale**: `TextSearch` is published beside `VectorSearch`, and pgvector satisfies it over a `tsvector` column Postgres *generates* from `content`, so no write path — no upsert, no bulk load — can leave a node searchable by words it no longer contains, which is the one thing a retriever-owned index could not promise. `STORE_CONTRACT_VERSION` moves `1.0.0` → `1.1.0` because fitness function 6's subject grew; **G9 is Open and nothing here decides what a version means**. A stage's `needs_store` is checked at run assembly against the configured store, before any stage runs, and refuses naming the stage, the plugin, the missing capability, what that store *does* advertise and which registered stores provide the rest — with **no adaptation and no degradation**, and no declaration path: the store side of every comparison is `isinstance`, and the checking module names no capability itself · **`MetadataFilter` is deliberately not published, and this is a correction to `02` rather than a deferral**: `02` §1 specifies it as a bare marker, and a `@runtime_checkable` Protocol with an empty body makes `isinstance(42, MetadataFilter)` true, so published as written it would be a capability every store advertises and none implements. It needs a member that *is* the capability, chosen against a store that translates the whole operator set — which is 2.6's · **recorded, not fixed**: nothing calls the check yet, because no command assembles a query run until 2.8/2.10, and `weft ask` resolves no plugin that could carry a declaration · **repaired 2026-08-17, on review**: the check reads every plugin in a stage's chain — `use:` *and* every `fallback:` name — because a fallback is a candidate that really runs, and one needing a capability the store has not got used to reach `AttributeError` mid-batch; the three decisions that *are* pgvector's text technique are now typed `[packs.weft-store]` settings (`text_search_config`, `text_query_mode`, `text_rank`) rather than SQL literals, with the configuration name feeding the generated column and the query from one value and a database generated under a different one refused instead of silently no-opped; the AND→OR rewrite replaced ` & ` rather than `&`, which had been corrupting every lexeme containing one (the default parser's `url`, `url_path` and `host` tokens) into a term no document holds — valid `tsquery`, no error, silently no match; and the troubleshooting remedy naming `[services] store` is gone, because there is no such key: **which store a run uses is still not configurable**, and `tests/docs/test_manual_config_keys.py` now derives that check from `ServiceSelection`
- [x] **2.6** the store contract is satisfied by a second backend of a genuinely different shape, so it is no longer a guess · owner `01` → *Runtime shape*; `06` → *What Phase 0 must not build* · turns on — · sha `54757f8` · **one suite, two engines, no shared code**: `packages/weft-qdrant` registers `qdrant` under `NodeStore` and `tests/integration/test_store_conformance.py` asks the contract's questions of a fixture that cannot say which backend it holds — every core method, every member of `FilterOp`, and both refusals — against the two real containers, skipping per backend with a reason when one is absent. The shapes are genuinely different and that is where it shows: Qdrant keys a point by a UUID (a `NodeId` is a sha256 string it will not accept), fixes a collection's vector width at creation, holds source records in a second vector-less collection, and orders by nothing anybody asked for — so `Page` promising pages and never an order became load-bearing rather than theoretical · **`MetadataFilter` is published with a member, discharging 2.5's obligation**: `matching(filter, cursor)` — no vector, no text, no `top_k`, the filter alone deciding membership — settled against a store that translates the whole operator set, which `weft-qdrant` and (now) `pgvector` both do. `STORE_CONTRACT_VERSION` `1.1.0` → `1.2.0`; **G9 is Open and nothing here decides what a version means** · **the vocabulary is published once, in `weft_store.fields`**, so two translators start from one parse: a path is `Node`'s own shape, and an extension value that is an array is compared element-wise · **three narrowings to the operator set, each forced by two engines having to agree** — ordered comparison takes a number and an `ext.` path (ordering text means whatever a collation means, which is a fact about a deployment); `eq`/`ne` on a set is refused naming `contains` (a document store matches an array element-wise, SQL compares the whole list — one spelling, two meanings, no error); identity against a float is refused naming the range to use. `FILTER_AST_VERSION` `1.0.0` → `1.1.0`, because a filter this AST used to accept no longer validates · **Qdrant deliberately does not satisfy `TextSearch`, and no shim was added to make the two look alike**: its text matching is a filter predicate and `search_text` returns a ranking, so there is no honest score to return — which is what makes 2.5's `needs_store` refusal demonstrable against a real backend, tested · **still open, and named rather than quietly skipped**: `01` → *Runtime shape* also requires an **ephemeral in-memory store** for the conformance kit and for pack authors' unit tests, so writing a plugin needs no Docker. It does not exist, no ledger task claims it, and this task did not build it — the kit runs against the containers and skips with a reason · **repaired 2026-08-17, on review — five findings confirmed, one rejected**: the float refusal ran for *every* comparison operator rather than the four identity ones, so `gte` against `0.8` was refused by a message naming `gte` as the remedy and no filter anywhere could compare against a confidence, a score or a threshold — both translators were already written for a float bound, and every conformance operator case used an integer one, which is why nothing caught it; `QdrantStore._connection` built its `AsyncQdrantClient` on the loop thread, whose constructor makes a synchronous version probe and opens the CA bundle, so every contract method raised `BlockingCallError` the first time it was driven through `weft_kernel.seam.wrap` — the only way a registered plugin is ever called, and a path no test took; `weft_cli.contract_reference.published_contracts` attributed every capability sibling to every distribution registering under the anchor, so `manual/contract-reference.md` shipped `TextSearch: weft-qdrant` — the capability this task deliberately withholds — attribution is now `issubclass` against the registered class, the same question `run_services._providers_of` asks; **`[services] store` exists, and 2.5's line's closing claim that "which store a run uses is still not configurable" no longer holds** — `weft-qdrant` had shipped a `NodeStore` no command could select while `weft.toml.example` and `manual/troubleshooting.md` documented it as reachable, which is `.phase2-findings.md` finding 9 generalised as that finding instructs, so `ServiceSelection` grew the field `.phase2-design.md`'s `[services]` block already names, `weft-store` left `INDEX_DISTRIBUTIONS` for `require_plugin` (a hard-coded tuple can never contain a stranger's pack) and `manual/operations-guide.md` → *Choosing a store* is where an operator meets it; and `qdrant-client`'s `<1.14` ceiling is gone from the distribution — the client's compatibility rule is symmetric, so capping it at 1.13 put every downstream install out of window against a server at 1.15 or later to spare a checked-in fixture a warning, and the fixture's own pin moved to the workspace root's `[tool.uv] constraint-dependencies` · **rejected, with the reason recorded in the kit's own docstring**: that `tests/integration/test_store_conformance.py` should be republished as an importable `weft_store.conformance` suite. `01` → *Runtime shape* names the **in-memory store** as what pack authors' unit tests use, not the kit; the fixture's two branches are container provisioning, not a name space anything is selected from at run time; and what a published suite may depend on (it imports `weft_pdf`, `weft_cli` and `weft_retrieve` today) and what its version would mean while **G9 is Open** are decisions no settled document has taken
- [x] **2.7** fusion and reranking are composable plugins a third party can retune, not a fixed ladder · owner `04` category B; `01` → requirement 6 · turns on — · sha `0110ca1` · **the contracts were already published (2.4); what this task decided is the shape everything downstream fills in**, so it ships one plugin in each position rather than the whole `.phase2-design.md` task-map row, whose other entries belong to open tasks by name: `reciprocal-rank-fusion` is **2.18b**, `repack` is **2.19**, `graded-retrieval` is **2.21a**, and the two shipped pipelines still name `cited-answer` (**2.9**), which nothing registers · **`single-list`** (`weft_retrieve/fusion.py`) is the fuser the design table assigns to no other task: 0 lists → an empty `Ranking`, 1 → unwrapped, ≥2 → `Failed` naming `reciprocal-rank-fusion` and how many arrived, because concatenating, taking the first and interleaving are three different fusion policies and picking one silently is the failure `CLAUDE.md` names outright. **`contributor_label` is published beside it** so 2.18's `weights` mapping and this task's `Ranking.contributors` are keyed on one spelling rather than two written a task apart — the reference's *three divergent copies of one 2009 formula* (`04`:421-426), prevented at the point the second implementation would otherwise invent its own key · **`llm-rerank`** (`weft_retrieve/rerank.py`, config `prompt` / `role` / `top_n`) is the retunable half: without a `Reranker` anybody can configure, "a third party can retune" has nothing behind it. `cross-encoder-rerank` is **not** shipped, for `.phase2-design.md` §10's stated reason (a model download `09` §4.4 keeps out of the gate, and `10` §1.2 files it on the index path) — **`10` §1.2 is corrected in this commit**, because it named 2.7 beside an unbuilt row and this task is now closed · **the ladder is proved by resolving four documents, not by prose**: fuse alone, fuse→rerank, fuse→rerank→rerank (the second retuned in its own `with:` block), and rerank→fuse refused by the kernel's own `_check_composition` naming both types (`tests/unit/weft_retrieve/test_init.py`) · **`ext` crosses the arity reduction and per-query attribution does not** — `Candidates.ext` is copied to the `Ranking` because G5's namespaced extension is the settled answer to "a strategy needs to pass something along" and dropping it at the one seam every query path crosses would make that answer false; `Passage.retrieved_by` survives and which *query* found which hit does not, exactly as 2.4 narrowed it. **Nothing here needed that back**, so G5 stays shut · **first registered `Prompt` in the tree** (`passage-relevance`, en + pl), registered by `weft-retrieve` because a prompt belongs to the plugin that asks the question (2.10's line) — which exposed and repaired a real defect in `weft_cli.contract_reference`: every contract walked until now declared methods only, and `Prompt`'s two *data* members (`input_model`, `output_model`) are annotations with no assignment, so generation died on a bare `AttributeError`. Data members are now documented beside methods, and a contract with nothing to call stops generation loudly instead · **recorded, because the design record is silent on it**: a plugin with a `prompt: str` field reaches the cascade through `StageLookup.build_capability(Prompt, name)` — `Prompts` renders by name but `weft_prompts.cascade.execute` needs the object, and nothing said which bridges them. The alternative was a second copy of the cascade inside a technique pack
- [x] **2.8** the router picks a strategy it was never told about — discovered from the registry, with no enum, no if-chain and no closed key space anywhere a name is decided · owner `01` → Phase 2 **Exit**; `01` → *Fitness functions* 4 · turns on FF4(a), FF4(b) *(`01` states no activation phase for 4; placed here because this is its first real selection surface — if that is wrong, it is `01`'s to correct)* · sha `d2c9ddf` · **deviation, accepted 2026-08-17**: `01` → Phase 2's *Exit* says the router discovers strategies "from the registry"; it discovers them from the pipeline catalogue, which the same eager discovery pass populates — the registry at one remove. Accepted by the project owner rather than corrected in `01`, because the property the exit protects is that no enum and no closed key space decides a name, and that holds: a pack's pipeline becomes routable on install with zero edits here. Recorded so the sentence and the code are known to differ · **the mechanism 2.25 left for this task**: `weft_kernel.discovery.PackRegistrar.add_pipeline_resource` is the contribution seam — buffered and committed exactly like a plugin registration, so a pipeline a raising `register()` claimed to ship never reaches a `PackReport`; `weft_cli.pipeline_catalogue.load_contributed` reads each one through `importlib.resources`, never a filesystem path, so a pack ships this from inside its own installed wheel. `weft_retrieve.engine.RegistryStageLookup`/`PipelineRouteCatalogue` are the real `StageLookup`/`RouteCatalogue` every technique's own test module had, until now, only driven through a hand-built fake · **`route.yaml`** (`score: query-scorer` → `decide: nearest-description`) ships from `weft-retrieve`'s own package, alongside `no-retrieval.yaml` and `retrieve-then-generate.yaml`, moved there from the top-level `packages/weft-retrieve/pipelines/` so a real wheel install can reach them — `tests/architecture/test_ff11_pipeline_integrity.py`'s shipped-pipeline finder and `tests/docs/test_technique_naming.py`'s own pipeline-name resolver are both extended, in the same commit, to read both locations rather than silently losing the coverage the move would otherwise have cost · **`weft_cli.run_services.build_services`** assembles a run's whole `ServiceRegistry` from the constructors each publishing pack already ships (`weft_llm.client.llm_service`, `weft_prompts.registry.prompts_service`, `weft_retrieve.engine.stage_lookup`/`route_catalogue`), never a second copy of any of them · **the CLI wiring is additive, not a rewrite**: a new `weft route <question>` command (`weft_cli.route_ask.run_routed_ask`) resolves and runs `route.yaml` against the installed registry, takes whichever pipeline the router names, resolves and runs that too, and prints the generated answer — verified by hand against the real Postgres/Qdrant containers and a real OpenAI credential, not only by the test suite. `weft ask` keeps Phase 0's own documented, tested, retrieve-only contract untouched, because rewriting it was a bigger, separate risk than this task's own property needed to take on · **`tests/architecture/test_ff4_no_closed_key_space.py`** is the fitness function this line names: (a) walks every `StrEnum` reachable from `packages/` and every module-level `Enum`-keyed `dict`, checked against the real registry for the reference's two actual defects — a shadowing name, and an enum as a registry's key *type*, which no grep could ever have caught; (b) the categorical proof grafted from the winning proposal — a real registry, a real `nearest-description` `RoutingPolicy`, and a pipeline named a freshly generated UUID at test time, selected and then genuinely resolved and executed through `weft_cli.compile` and `weft_kernel.runner.Runner`. Neither clause has a fixed name to enumerate, so neither could pass by construction · **repaired 2026-08-18, on review**: `weft-cli`'s own `pyproject.toml` never declared `weft-generate`, though `weft_cli.route_ask` imports `weft_generate.payload.Answer` at module scope and nothing else weft-cli declares pulls it in transitively (`weft-retrieve` deliberately does not, by the design record's own DAG rule) — invisible inside this repo's shared workspace venv, where every first-party package is already installed regardless of declared deps, so both hand-verified live runs of `weft route` had passed anyway; a real `pip install weft-cli` would raise `ModuleNotFoundError` on the first call. Fixed by declaring it, and `tests/architecture/test_cli_declares_its_imports.py` now checks every first-party import under `weft-cli`'s own source tree against its own manifest, the same AST-walk shape FF1's static half already uses for the kernel, so a future gap of this shape fails in the gate rather than only under a clean install. **Narrowed, not implemented**: `.phase2-design.md` §5 also describes `load_contributed` merging with a project-local catalogue and refusing a name colliding across the two; no CLI command wires a `load_pipeline_catalogue(directory)` result into a route decision yet, so `ContributedPipelineNameCollisionError`'s docstring — which had quoted the wider guarantee as if implemented — now says plainly that only contributed-vs-contributed collisions are checked today. Reviewer findings against this task: two on the missing dependency (confirmed, same defect, fixed once), one on the same defect verified by building and installing weft-cli's wheel standalone (confirmed, same fix), one on the docstring overclaim (confirmed, narrowed rather than implemented — the merge itself has no live caller to serve it yet, and inventing one was judged a larger, separate change than this repair's own scope)
- [x] **2.9** an answer carries citations a reader can follow back to a passage · owner `04` category B, the citation manager's four responsibilities · turns on — · sha `984764d` · **carries a gap 2.27's repair sequenced rather than left to be discovered**: `weft_pdf.PdfPages` records where each page starts, but on the **root** node only — `Node.derive` drops `ext` by design, and the chunker attaches nothing — and a chunk records `ordinal`, never a character offset into its parent. Page attribution therefore needs both halves built here: something that carries a page number (or `PdfPages`) onto a chunk, and a chunk-level offset ext model to look it up with · **both halves built, and kept apart from what they are not**: `weft_chunk.payload.ChunkOffset` is a new, PDF-agnostic ext model recording a chunk's character offset into its parent, attached to every chunk `FixedSizeChunker._windows` derives; `weft_chunk.fixed_size._carry_forward` copies every *other* namespace the parent's `ext` already carries — `PdfPages` included — onto the same chunk, because `Node.derive`'s own docstring says a later stage attaches what it needs, and this is that stage, doing it once rather than per-extractor · **`Citation.page: int | None` is what makes the fix visible to a reader**, resolved by `weft_generate.page.page_for` through two `runtime_checkable` `Protocol`s matching `ChunkOffset` and `PdfPages` structurally — neither is imported — because `weft-generate`'s own dependency table names four packs and neither `weft-pdf` nor `weft-chunk` is one of them, and a citation mechanism that only works for PDFs would be exactly the parser-specific coupling `.phase2-findings.md` finding 10 rules out generally · **`cited-answer` is the `Generator` this task ships**: `Passages` (already labelled by whichever `ContextPacker` ran) in, `Answer` out, one model call through `LLM.complete` — never the structured-output cascade, because the shape of an answer is prose with bracketed markers in it, not a schema — and citations are read back out of the completion by a literal substring search against each offered passage's own label, which needs no language heuristic because Weft controls the label format the reference's four regex extractors existed to guess at · **a repair surfaced by two fitness functions, not by review**: forwarding `ChunkOffset`/`PdfPages` onto a stored chunk means *something* has to call `weft_store.register_ext_model` for them, and neither pack registering its own namespace nor a module-level call in `weft-cli` survived contact with the gate — the first breaks FF9(a) (a stranger's wheel install must not need `weft-store`, and neither does `weft-chunk` today), the second breaks FF8(b) (`weft --version` imports zero pack code). `weft_cli.registry_bootstrap._ensure_chunk_offset_rehydrates` is the fix that satisfies both: called lazily inside `build_dependencies`, never at module scope, and idempotent against `DuplicateRegistrationError` rather than checked first, because this module's own tests call it many times over against one process-wide rehydration registry · **recorded, not fixed**: `PdfPages` itself is not wired the same way — `weft-cli` does not depend on `weft-pdf` at all, by design, so there is no existing import site to add the call to without giving the CLI a dependency its own plugin architecture exists to avoid. A PDF-sourced citation's `page` resolves correctly within one process (proven against the real types in `tests/unit/weft_generate/test_page.py`), but a node carrying `PdfPages` that is stored and then read back by a *separate* `weft ask` process against a PDF corpus will fail to rehydrate until this is closed · **`repack` label assignment is not this task's**, despite `.phase2-design.md` §14's task-map row naming it here: `Passage.label` and `Passages`' own non-empty-and-unique-label validator already existed before this task, `cited-answer` only consumes labels a `ContextPacker` already assigned, and `repack` itself stays 2.19's, unbuilt, per 2.7's own precedent for the identical discrepancy
- [x] **2.10** generation is a pack — the prompt layer, the cascade, model strings and the `LLMError` taxonomy ship outside the kernel · owner `04` → *Kernel or pack*; `01` → Phase 0 **Lift** · turns on — · sha `b04d654` · **two of the four clauses were already true, and they are cited rather than rebuilt**: task 2.30 shipped `packages/weft-llm` with the fourteen-class taxonomy (`weft_llm/errors.py`) and `LLMProvider` (`weft_llm/contract.py`), and this task added `LLMProviderFaultError` and `NativeStructuredUnsupportedError` to that same taxonomy rather than starting a second one. **`packages/weft-prompts` is the new distribution** (the fifteenth), publishing `Prompt`, the `Prompts` service, `TypedPrompt`, the two-direction template validator, the single JSON-rescue extractor and the three-tier cascade — `04`:45-48's assignment followed as recorded, per `.phase2-design.md` decision 19 · **the renderer is `${name}` over `string.Template`, never `str.format`**, so the reference's rule that every JSON-example prompt must escape `{{`/`}}` disappears instead of being documented, and both directions of the template/input-model agreement are checked at **class-definition** time — a translation that drops a `${placeholder}` is refused where it is written, which is the one failure that otherwise changes what a model is told without changing a line of code · **every recorded cascade correction is carried and tested one by one**: tier 1 guarded by `isinstance(provider, NativeStructured)` and not `hasattr`; tier 2 skipped entirely when tier 1 raised `LLMBadRequestError` (`04`:147-153's "cannot be re-derived from first principles" short-circuit, as a named boolean rather than the reference's `(None, True)`); the step-down set narrowed to `ValidationError`/`ValueError`; tier 3's catch set no narrower than the step-down set, so a malformed completion returns `Failed` rather than raising out of `execute()`; the rescue extractor in the **executor's** order; no retries inside the cascade; and `LLMPermissionDeniedError` re-raised at tiers 1 and 2 — without which a bad credential surfaces as a low structured-output score, which is the failure that leaf class exists for · **the `LLM` service always calls `provider.stream`**, which is `.phase2-design.md` §7 read literally and discharges **2.17** structurally; the cost is named rather than left to be found — a streamed `Completion` carries `finish_reason=""`, and `LLMProvider.complete` is now unreached by the shipped client though a provider still implements it and `tests/integration/test_openai_llm.py` still drives it. Driving `scripted` through that one path exposed a real 2.30 divergence: its stream rejoined to the reply **plus a trailing space**, so what the provider said and what a caller received differed by one character. Repaired, and `test_scripted.py`'s assertion tightened from `.strip()` to exact equality · **retry retries a class, not a message**: `with_retry` catches `LLMError` and re-attempts iff `transient`, which is exactly `LLMTransientError` today and stays correct if a provider pack adds a transient leaf elsewhere; never a bare `Exception`, and `CancelledError` is a `BaseException` so no clause in that file can see it. A stream that has already yielded is never restarted. `with_retry` returns a wrapper that advertises exactly what it wraps, because one wrapper class would erase `NativeStructured` and leave tier 1 silently unreachable · **model strings are the rewrite `04`:294 specifies**, catalogue identity (`ModelRef.provider`) against runtime identity (`ModelRef.model`), with the four-step disambiguation written so **a slash is not evidence of a prefix** — `meta-llama/Llama-3-8B` is one model id — and a prefix naming a different provider from the role's own refused rather than guessed · **three departures from `.phase2-design.md`, each forced by §2's own one-way dependency chain and recorded rather than silent**: (1) `Rendered` is published by `weft-llm`, not `weft-prompts` — §2's ownership rule would put it downstream of `LLM.complete`, which is the same conflict §2 settles for `Answer` with "that single placement is what keeps the graph acyclic"; (2) `LLM.structured` from §3 is not built, because it would name `Structured`, which lives in `weft-prompts`, and §7 already says `weft_prompts.cascade.execute` is what a technique calls "and nothing else" — the client exposes `complete_structured` and `native_structured_available` instead, which is all the cascade needs; (3) `RoleMapping`/`LLMRoles`/`UnmappedLLMRoleError` moved from `weft_cli.llm_roles` to `weft_llm.roles`, since the consumer is a `weft-llm` service and a service cannot import the CLI that assembles it — `weft_cli.llm_roles` keeps the parse and re-exports the names · `[llm.retry]` is now accepted, the key that module's own docstring promised to "the task that builds retry", and it reaches a run through `Dependencies.llm` · **`weft-prompts` declares no `weft.packs` entry point and registers nothing**, for `weft-retrieve`'s own recorded reason: fitness function 2 requires a distribution declaring one to be active *and contributing*, and every first-party prompt belongs to the plugin that asks it a question (2.9, 2.7, 2.16, 2.17). The first prompt adds that line in the same commit · **not built here, and not this task's**: `build_services` (2.8), the cited-answer generator (2.9), and `PrintingSink`, which `.phase2-design.md` §13 item 7 leaves as a Phase 3 sequencing call · **the `01`/`06` discrepancy this line's own "Raised, not resolved" paragraph records is untouched** — this task places the work in Phase 2 as the ledger says, and decides nothing about which document was right
- [x] **2.11** every contract this phase publishes has an implementation living outside the workspace · owner `07` §2, clause 9(c); `01` → Phase 2 **Exit** · turns on FF9(c) · sha `4ff7d74` · **the bill, decided 2026-08-17**: clause 9(c) reaches **21 published contracts**, not this phase's fourteen — the seven from Phases 0–1 have never had an out-of-tree implementation either, and nothing budgeted them. The project owner chose to build all 21 rather than waive the backlog, grouped into example distributions by area rather than one per contract · **the bill was already stale by the time this task started, and the check does not hard-code either number**: `Renderer` (task 2.27) and `Expander` (task 2.31) landed between the 2026-08-17 decision and this task, so the real count the day this closed is **23**, not 21 — `tests/architecture/test_ff9c_every_contract_has_a_stranger.py`'s left side is `weft_cli.contract_reference.published_contracts(discover_for_reference())`, read live off this repository's own registrations, never a constant copied from this line, so a twenty-fourth contract published tomorrow is exactly as checkable as the twenty-first was · **three new example packs, one per publishing half, `.phase2-design.md` §9's own grouping**: `examples/weft-example-ingest` (`Extractor`, `Renderer`, `Cleaner`, `Enhancer`, `Embedder`, `Expander`, and the whole `NodeStore` family — `VectorSearch`, `TextSearch`, `MetadataFilter` — over one `Lifetime.PROCESS` in-memory dict, `matching` translated through the same `weft_store.fields.field_for` pgvector and Qdrant already share rather than a fourth reading of the operator set), `examples/weft-example-llm` (`LLMProvider` plus, structurally, `NativeStructured` — one class answering both, an echo-and-reverse completion and a JSON-schema-shaped placeholder for the structured call — and `Prompt`, subclassing the public `weft_prompts.TypedPrompt` base every third-party prompt is meant to use), `examples/weft-example-query` (all nine of `QueryTransform`, `Retriever`, `Fuser`, `Reranker`, `ContextPacker`, `Sufficiency`, `QueryScorer`, `RoutingPolicy` and `Generator` — a fixed-fixture retriever needing no database, a citation-carrying generator whose markers `Answer._citations_resolve` never has cause to refuse, and every plugin's own test carrying the `out.origin == in.origin` obligation task 2.4's line hands to every query-path plugin). `examples/weft-example-chunker` (existing, `Chunker`) is the fourth · **how the check runs, and why it is not the reference's `test_keys_parity` shape**: the first-party wheels are built once, shared across four throwaway venvs — one per example pack, each installed with *every* first-party wheel (never a hand-maintained per-example dependency subset, which would drift from each `pyproject.toml`'s own list the first time one changed) plus that one example's own, so eager discovery (G3) runs every installed pack's `register()` and a probe attributes a registration to the example under test only when `RegistryEntry.distribution` names it. Each probe imports `weft_cli.contract_reference.capability_siblings` from its own installed `weft-cli` wheel rather than reimplementing the sibling walk, so a probe's "this class is a `VectorSearch`" cannot come to disagree with what `manual/contract-reference.md` says. Left and right are computed from genuinely different places — this repository's own registrations, and four independent subprocess probes — and `test_missing_strangers_can_actually_fail` plants a fabricated qualname to prove the comparison itself is not vacuous · **the loophole-closer ratchet, `SERVICE_PROTOCOLS_WITHOUT_AN_EXAMPLE_PACK`**: seven real, exported `Protocol`s with no registration path — `EntryPointLike` and `Stage` (kernel-level infrastructure, never a capability a pipeline chooses among), `LLM`, `TokenSink`, `Prompts`, `RouteCatalogue`, `StageLookup` (services, `ctx.require`d rather than named in a pipeline) — each checked, against a real registry, to genuinely carry zero registrations, so naming something here cannot become a way to dodge a real contract · **`CONTRACTS_WITHOUT_AN_EXAMPLE_PACK` is pinned empty**, `07` §2's exact ratchet name, with its own `test_waiver_list_is_empty` · **`examples` joins `[tool.pyright] include`**, a repository-level tooling gap `.phase2-design.md` §9 named and accepted rather than left implicit — `extraPaths` also gains each example's own `src/` directory, because an out-of-tree pack is deliberately not a workspace member (FF9(a)) and pyright has nothing else to resolve its own package imports against · **a mis-statement in the ledger's own running commentary, corrected in this commit**: 2.31–2.33's own re-check (above) claimed the FF9(c) bill "does not grow" because "these three register against contracts that already exist" — true for 2.32 and 2.33, false for 2.31 itself, whose own line says plainly "`weft-index` publishes `Expander`". Fixed at the source rather than left for a reader to notice the two counts disagree · **run end to end**: `uv run poe ci-checks` is green, 1272 passed + 1 skipped, including this task's own heavy end-to-end test (`test_every_published_contract_has_a_stranger`, real `uv build`/`uv venv`/`uv pip install` against 16 first-party wheels and 4 example wheels, ~30s)
- [x] **2.12** the contract reference and the operations guide describe what this phase published, without a human retyping a signature or a status name · owner `08` §1–§2 · turns on — · sha `bdc4cd5` · **the property was already true, and this task found that rather than building anything**: `uv run python scripts/generate_contract_reference.py` was re-run against the live registry and produced **no diff** against the checked-in `manual/contract-reference.md` — all 23 contracts Phase 2 published are present and correctly attributed, including the families this task's own brief named (`LLMProvider`, `Prompt`, `Sufficiency`, `QueryTransform`, `Fuser`, `Reranker`, `RoutingPolicy`), the store capability siblings (`NodeStore`/`VectorSearch`/`MetadataFilter` under both `weft-store` and `weft-qdrant`, `TextSearch` under `weft-store` alone, matching 2.5's own scoping), `Renderer`, and both `Extractor` backends (`weft-extract`, `weft-pdf`) — repair 2.6's fix to `capability_siblings` (per-distribution attribution rather than every sibling attributed to every registrant) held under the full weight of Phase 2's registrations, not only the case it was written against · **`manual/operations-guide.md` already carried every operator-facing addition this task was told to check for**: `[services] store`/`[services] embed` (*Choosing a store*/*Choosing an embedder*), `[llm.roles]` (*Choosing which model answers*, including the `route` role `weft route <question>` (2.8) reaches for), and the three `[packs.weft-store]` text-search settings (*Tuning the text arm*) — each landed in the commit that published the capability it documents (2.5, 2.6, 2.29), each held to its own checked mechanism (`tests/docs/test_operations_guide.py`'s compose-block, exit-code and doctor-status table checks; `tests/docs/test_generated_docs.py`'s registry-walk floor) rather than trusted by inspection · **`uv run poe ci-checks` is green end to end**: 1275 passed + 1 skipped (the skip is `test_corpus_manifest.py`'s network-gated case, unrelated to this task), including the two fitness functions Phase 2's exit rests on — `tests/architecture/test_ff4_no_closed_key_space.py` (2.8) and `tests/architecture/test_ff9c_every_contract_has_a_stranger.py` (2.11) — both re-run, not merely trusted from the sha they last closed on · **`docs/README.md`'s Status block and Execution path are updated to match, in the commit this line's sha names**: *Prerequisite V1–V3* and *Phase 2 build* are ticked, since all 33 Phase 2 tasks in this ledger are now `[x]`; the *Exit* line is left unticked and the Status block is deliberately left on Phase 2 — the evidence above supports ticking it, but turning that evidence into a ticked Exit box and a moved Status block is the project owner's judgement, not this task's to default. `docs/README.md` → *Next action* carries the same evidence for whoever makes that call
- [x] **2.13** the null case is a plugin like any other, and an empty source list is a stated property of it rather than a retrieval failure a consumer has to guess at · owner `10` §1.1; `02` §1 · turns on — · sha `8223ad3` · **`no-retrieval.yaml` is not shipped here, and that is a recorded decision rather than a default**: the design task map pairs this plugin with `cited-answer(when_no_evidence=answer_from_memory)` in one pipeline, but `cited-answer` is task 2.9's (itself blocked on `weft-llm`/`weft-prompts`' prompt-rendering machinery) and the fuse/pack stages a resolvable pipeline needs — `single-list`, `repack` — are tasks 2.7 and 2.19's. A pipeline document naming plugins nothing registers would fail FF11(b)'s own resolve-every-shipped-pipeline check the moment `weft-retrieve/pipelines/` stopped being empty · **repair, in the same commit rather than deferred**: registering the first `weft-retrieve` plugin surfaced a latent defect in `weft_cli.contract_reference.capability_siblings` — `weft-retrieve`'s five `Stage[In, Out]` positions all declare the identical bare method name `run`, so `issubclass` cannot structurally distinguish `Retriever` from `Fuser` from `ContextPacker`, and the sibling walk built for `weft-store`'s genuinely-overlapping `VectorSearch`/`TextSearch` (which differ by method name) would have printed `weft-retrieve` as "Registered by" for a `Fuser` and a `ContextPacker` nothing registers — task 2.6's own declared-capability-disagrees-with-derived-one failure, arriving through a family it was never built for. Fixed by excluding every `Stage` contract from the sibling walk: a Stage plugin's contract membership is always exactly the one name it registered under (`weft_cli.compile.AmbiguousStageContractError`, exercised by `tests/unit/weft_cli/test_compile.py::test_a_plugin_name_two_contracts_register_is_refused_by_name`), never a second one derived by structural check
- [x] **2.14** the single-pass baseline is a plugin whose name states its cost, so an operator choosing what to run in a loop is not misled by the registry · owner `10` §1.1, §2.1 rule 4 · turns on — · sha `ee996a1` · **read against `10` §2.1 rule 5, not literally**: `retrieve-then-generate` would be `vector-top-k` plus a `Fuser` plus a `ContextPacker` plus a `Generator` — a composition by rule 5's own words ("a composition is a pipeline, never a plugin"), not an atomic technique. This build takes `.phase2-design.md` decision 12's reading, over the literal one §13 item 2 leaves open for the project owner to overrule: `weft_retrieve.vector_top_k.VectorTopK` is the plugin whose name states its cost, and `cost_bound = (0, 0)` is checked by a direct class-attribute assertion against what `run` actually resolves (`NodeStore`, `Embedder`, never an `LLM`-shaped service) — a repair against three reviewer findings replaced this line's earlier claim of a seam-driving call-counting test, whose double was never registered into the run it wrapped and had nothing to count against, since no `LLM` service exists yet for a `(0, 0)` technique to not-call · **`retrieve-then-generate.yaml` is not shipped here, for task 2.13's own recorded reason**: `single-list` (2.7), `repack` (2.19) and `cited-answer` (2.9) are not yet registered, and a pipeline naming plugins nothing registers would fail fitness function 11(b)'s resolve-every-shipped-pipeline check the moment `weft-retrieve/pipelines/` stops being empty. The pipeline lands with whichever of those three tasks closes last · **a store resolved as `NodeStore` that does not satisfy `VectorSearch` fails named (`Failed`) rather than crashing with an `AttributeError` mid-batch** — task 2.5's own repair, applied here because nothing yet calls `weft_cli.run_services.check_store_capabilities` against a query pipeline (that module's own docstring: the assembler that will call it lands with tasks 2.8 and 2.10) · `weft-retrieve` now depends on `weft-embed`: a query's text becomes a `Vector` through the same `Embedder` contract an ingest pipeline embeds through, wrapped in a one-off `Node.synthetic` rather than a second embedding contract for a bare string
- [x] **2.15** a query transform is a composable stage a caller can omit, so no strategy pays for a rewrite it did not ask for · owner `10` §1.1; `02` §1; `02` §3 · turns on — · sha `36769a5` · **the mechanism was task 2.4's** — `QueryTransform` is `Stage[QuerySet, QuerySet]`, so identical `In`/`Out` is what makes inserting or omitting one a document edit that changes nothing about the seam either side — and this task ships `contextual-query-rewrite`, the first plugin standing on it and the position `hyde` (2.16) and `step-back` (2.17) register into next. `tests/unit/weft_retrieve/test_init.py::test_a_query_transform_is_a_composable_stage_a_caller_can_omit` resolves the same `(retrieve,)` stage list with and without the transform inserted ahead of it, through the real `weft_kernel.runner.Runner.resolve`, rather than reasoning about the contract in prose · **omittable by *configuration* too, not only by document**: `skip_without_history` (default `True`) returns `payload` unchanged, unmodified, when `QuerySet.history` is empty — the reference ran its own rewrite on every strategy including the baseline, "un-nameable and un-disableable"; a `_RefusingLLM` stub that raises on any method proves the skip path never resolves `LLM` or `StageLookup` at all, which is what makes `cost_bound = (0, 1)`'s floor of zero a fact rather than a claim · **`out.origin == in.origin` is asserted in every test that produces a `QuerySet`**, per 2.4's own recorded obligation — the reference fed a hallucinated rewrite to a cross-encoder *as the query*, and `contextual-query-rewrite` threads `payload.origin` through unchanged on both the skip path (returns `payload` itself) and the model path (constructs the new `QuerySet` with `origin=payload.origin` explicitly) · **`OnFailure` is published in `weft_llm.payload`, not `weft_retrieve`**, a placement decision this design record left open: seven task rows across `.phase2-design.md` §10 (2.16, 2.20, 2.21a, 2.22, 2.23a, 2.24, plus this one) type an `on_failure`/`on_parse_failure`/… field the same way, spanning both `weft-retrieve` and `weft-generate` — both already depend on `weft-llm`, the fully-upstream pack in `.phase2-design.md` §2's one-way chain, so publishing it there once is what stops six later tasks from each inventing their own `Literal`. **One member today (`FAIL`), deliberately** — every worked example in the design record fails loudly rather than degrading, and inventing an unused second member to make the enum "look right" would be the tuning constant with no measurement behind it this project's rules refuse; a task that needs a second behaviour adds the member in the commit that needs it · **a shared base class for `hyde`, `step-back` and `multi-query` is `.phase2-design.md`'s own stated decision, and it is *not* built here** — factoring one out of a single worked example would be guessing at the other three plugins' shape from one data point before any of them exist, which is the reference's own `FusionRetriever` failure mode (a capability arriving after the mechanism did) applied to abstraction instead of code. Recorded in `weft_retrieve.transforms`'s own module docstring as this build's decision, for task 2.16 or 2.17 to settle once a second concrete case exists to check it against · **new registered `Prompt`, `standalone-question`**, arriving with the plugin that asks it — the same split `passage-relevance` and `llm-rerank` made at task 2.7
- [x] **2.16** `hyde` runs in front of any retrieval rather than inside one strategy, and its sample count, query inclusion and failure behaviour are configuration · owner `10` §1.1; `01` → requirement 6, second clause · turns on — · sha `d43bf9f` · **`Hyde` registers into the `QueryTransform` position task 2.15 built, beside `contextual-query-rewrite`, never a retriever with a rewrite baked in** — `weft_retrieve.transforms.Hyde`, `weft_kernel.discovery.PackRegistrar.add(QueryTransform, "hyde", Hyde)`. Three named knobs, each a `HydeConfig` field with a default: `samples: int = 3` (`.phase2-design.md` §10's own row is explicit no count is asserted in a docstring — `10` §5 records the paper's own number was never confirmed at source), `keep_question: bool = True` (carries the paper's inclusion of the query's own embedding forward, the thing the reference discarded), `on_failure: OnFailure = FAIL` (`weft_llm.payload.OnFailure`, task 2.15's placement, one member today) · **generated through the `LLM` service and the prompt layer task 2.10 built, never a provider directly**: `weft_prompts.cascade.execute` against a new registered `Prompt`, `hyde-document` (`weft_retrieve.prompts.HydeDocumentPrompt`), asking for `${samples}` hypothetical passages in one call — `cost_bound = (1, 1)`, always exactly one cascade call, no skip path, because HyDE is not conditioned on anything in the payload the way a follow-up rewrite is on history · **`out.origin == in.origin` is asserted in every test that produces a `QuerySet`, load-bearing here specifically**: ledger 2.4's own line names `hyde` as the plugin whose loss of this property *is* the reference's cross-encoder-scores-a-hallucination defect, because this is the transform that actually manufactures the hallucinated text a substitution would otherwise leak — `Hyde.run` threads `payload.origin` through unchanged on every derived `Query` it builds · **HyDE is a claim about dense retrieval, made structural**: `HydeConfig.channels` defaults `(Channel.VECTOR,)` and every derived `Query.channels` is stamped with it, so the hallucinated passage never reaches a `TextSearch` arm the way the reference's did — `Query.channels`' own docstring names this as the fix for the reference's HyDE inversion · **what is implemented against Gao, Ma, Lin, Callan, arXiv:2212.10496 (2022), ACL 2023, and what is not, named rather than left for a reader to find**: the paper averages several hypothetical documents' embeddings together with the query's own into one dense vector before search; this plugin does not average — each hypothetical document becomes its own `Query`, retrieved on its own `RankedList` and combined only downstream by a `Fuser` (`reciprocal-rank-fusion`, ledger 2.18), per `hyde-fanout-rrf.yaml`'s own worked example. Fusion in place of averaging is the one respect this plugin does not literally reproduce the paper's arithmetic in, recorded on `Hyde`'s own docstring rather than left to be discovered by diffing this module against the paper · **the shared-base decision `.phase2-design.md` and task 2.15 left open — "for task 2.16 or 2.17 to settle once a second concrete case exists to check the abstraction against" — is checked against `hyde` and still not settled, on purpose**: the design record's own common part ("render a prompt, get one or more derived `Query`s back, combine them with what arrived under `keep_question`") does hold for both `ContextualQueryRewrite` and `Hyde`, but `step-back`'s own row (`.phase2-design.md` §10) needs a third fact neither of them does — *which* derived query is which kind, kept in a separate prompt slot rather than folded into one `keep_question` boolean. Factoring a base now would guess at that fact's shape from two data points neither of which has it, the reference's own `FusionRetriever` failure mode applied to abstraction; left for task 2.17 to settle with three concrete cases instead of two, recorded in `weft_retrieve.transforms`'s own module docstring rather than left silent
- [x] **2.17** `step-back` is the same technique whether tokens arrive at once or one at a time · owner `10` §1.1; `01` → *Colour*, the streaming consequence · turns on — · sha `ebdc3b7`
- [x] **2.18** query fan-out and rank fusion are two plugins, so the fuser serves hybrid retrieval and fan-out from one implementation · owner `10` §1.1; task 2.7 · turns on — · sha `c482633` · **`multi-query`** (`weft_retrieve/transforms.py`, the fourth `QueryTransform`) is the fan-out half — one or more seed queries, selected by `expand_origins` matching `Query.produced_by`, become several via one *batched* cascade call, `_offer_seeds`/`_groups_by_index` mirroring `rerank.py`'s numbered offer-and-parse so `cost_bound` stays `(1, 1)` regardless of how many seeds matched, which is what lets composing two fan-out stages not multiply — `.phase2-design.md`'s own worked example, checked directly by a test that matches two seeds in one call · **`reciprocal-rank-fusion`** (`weft_retrieve/fusion.py`, the second `Fuser` beside `single-list`) is the one implementation this task's own line asks for: Cormack, Clarke & Büttcher, SIGIR 2009, `k=60` default, `weights` keyed on the identical `contributor_label` spelling `single-list` already publishes, optional `top_k`. `run` accumulates every hit by `Node.id` across `payload.lists` with no branch asking whether a list arrived from a second channel on one query (hybrid) or from one channel on a `multi-query`-derived query (fan-out) — both are "another list this document was found in, at this rank, under this label," proved by a test that fuses one of each shape in the same `Candidates` and checks the arithmetic is identical, not merely that both compile · **`Ranking.contributors` is the distinct label set, not one entry per list** — recorded as this task's own decision, because `weft_retrieve.payload`'s own docstring for the field says only "which retriever and which channel fed the fusion," not how many times each may repeat, and sixteen lists from an eight-query two-channel fan-out carrying sixteen mostly-repeated entries would say nothing sixteen `RankedList`s did not already · **the shared-base question `weft_retrieve.transforms`'s own module docstring left for this task to settle "once `multi-query` exists to check the abstraction against"** is closed here, not by folding `multi-query` into `Hyde`/`StepBack`'s three-step common shape but by naming why it doesn't fold: multi-seed batching and an indexed response parse are real machinery neither of the other two transforms ever needs, checked against the fourth case rather than guessed about from three — recorded on `MultiQuery`'s own class docstring rather than left for a diff to discover · `ExpansionKind` (`PARAPHRASE`\|`ASPECT`\|`TERM`, default `ASPECT`) is `10` §1.1's own reference finding turned into a fourth config field: the reference's prompt asked only for paraphrases, "forbidding the two things the expansion literature credits" — this build ships all three, defaulting to the one the reference's prompt could not reach · `require_distinct` drops a variant whose whitespace-collapsed, casefolded text duplicates the seed's own or another kept query's — recorded as this build's own smallest-defensible reading of a knob `.phase2-design.md`'s own row names with no further text, exact-after-normalisation rather than a fuzzy near-duplicate model this plugin resolves no service for · citations: Nicholas J. Belkin, Paul Kantor, Edward A. Fox, Joseph A. Shaw, *Combining the evidence of multiple query representations for information retrieval*, Information Processing & Management 31(3), pp. 431-448, 1995; George W. Furnas, Thomas K. Landauer, Louis M. Gomez, Susan T. Dumais, *The vocabulary problem in human-system communication*, CACM 30(11), pp. 964-971, 1987; Rolf Jagerman, Honglei Zhuang, Zhen Qin, Xuanhui Wang, Michael Bendersky, *Query Expansion by Prompting Large Language Models*, arXiv:2305.03653, 2023 — `multi-query`; Gordon V. Cormack, Charles L. A. Clarke, Stefan Büttcher, *Reciprocal rank fusion outperforms condorcet and individual rank learning methods*, SIGIR 2009, pp. 758-759, DOI 10.1145/1571941.1572114, and Edward A. Fox, Joseph A. Shaw, *Combination of Multiple Searches*, TREC-2, NIST SP 500-215, 1994, p. 243 — `reciprocal-rank-fusion` · every plugin driven through `weft_kernel.seam.wrap` (fitness function 7(b)) and carries its own `out.origin == in.origin` assertion, task 2.4's obligation left to each query-path plugin
- [x] **2.19** context ordering is a named, parameterised stage whose method does what the method is named after · owner `10` §1.1, the `repack` row · turns on — · sha `807a5dd` · **`repack`** (`weft_retrieve/repack.py`) is the sixth contract this pack registers under, `ContextPacker`, `Stage[Ranking, Passages]` — one plugin, one `RepackConfig` field (`method: RepackMethod = REVERSE`, `top_n: int | None = None`), never three plugin names for one mechanism. Dispatch is a `Mapping[RepackMethod, Callable[...]]` keyed on the enum, never an `if`/`elif` chain — a fourth method is one function and one entry, and a typo in a `with:` block is a pydantic `ValidationError` naming the valid set, since `RepackMethod` is a closed `StrEnum` rather than a `str` · **`reverse` is the default, not `forward` and not the reference's hard-coded `sides`** — `10` §1.1's own row: Wang et al.'s Table 11 selects it on the Avg column at 0.483, and Liu et al.'s *Lost in the Middle* is the effect it exploits, putting the single best passage closest to the question. **`sides` ships correctly this time**: even retrieval-order positions kept at the front, odd positions reversed at the back — `hits[0::2]` then `reversed(hits[1::2])` — pinned by a unit test asserting the exact n=7 sequence `[d0, d2, d4, d6, d5, d3, d1]`, refusing forever the reference's best/worst zip-interleave that emitted `[d0, d6, d1, d5, d2, d4, d3]` under the identical citation (`10` §1.1's row, `repacking.py:149-155`) · **labels are assigned here, and this is the type at which they become final** — `weft_retrieve.contract.ContextPacker`'s own docstring names this as its job, and `2.9`'s own line records the gap left for it: every packed passage gets `str(position + 1)` in its *final* packed order, never its retrieval rank, so `[1]` in a generated answer always names whichever passage this stage put first regardless of which method moved it there · **`top_n` truncates the input before any method reorders it** — cutting after reordering would let a method decide *which* hits survive as a side effect of deciding where they sit, a second hidden truncation policy this plugin does not have · **generic over what a hit actually is, on purpose**: `.phase2-findings.md` §11 records that collapsing several derived nodes of one parent chunk to that parent is a separate, named operation on this pack's own to-do list (ledger 2.33), never a `ContextPacker`'s implicit behaviour — this module orders and labels whatever tuple of `Passage`s a `Ranking` carries, with no opinion on how many share a parent, so a collapsing `Reranker` slotted ahead of it in a document changes what arrives and nothing about what this does with it · every test drives `Repack` through `weft_kernel.seam.wrap` (fitness function 7(b)) and asserts `out.origin == in.origin` and `out.ext == in.ext`, task 2.4's obligation left to each query-path plugin · **the two pipelines tasks 2.13 and 2.14 each deferred "to whichever of `single-list` (2.7), `cited-answer` (2.9) or `repack` (2.19) closed last" ship in this commit**, since this is that task: `packages/weft-retrieve/pipelines/retrieve-then-generate.yaml` (`.phase2-design.md` §4's V3 baseline: `vector-top-k` → `single-list` → `repack(reverse, top_n=8)` → `cited-answer`) and `packages/weft-retrieve/pipelines/no-retrieval.yaml` (`no-retrieval` → `single-list` → `repack` → `cited-answer(when_no_evidence=answer_from_memory)`, ledger 2.13's own deferred pairing) — both resolve against the real installed registry (`tests/architecture/test_ff11_pipeline_integrity.py`), which is what makes "reachable from a pipeline document," requirement 6's second clause, a checked fact rather than a claim about a plugin nothing composes · **repair, surfaced by the new registration rather than by review**: `tests/unit/weft_cli/test_contract_reference.py`'s own sibling-exclusion test used `ContextPacker` as its example of a `Stage` contract nothing registers, which stopped being true the moment `repack` landed — reworked onto `QueryScorer` (task 2.25, still open), the identical structural claim with a still-honest example, and `manual/contract-reference.md` regenerated in the same commit
- [x] **2.20** an evidence-sufficiency loop is expressible, and its stopping rule is one named, testable thing rather than four scattered breaks · owner `10` §1.1, the `iterative-retrieval` row · turns on — · sha `3be088b` · **`iterative-retrieval`** (`weft_retrieve/iterative.py`) is a second `Retriever`, and it is the first plugin in this tree that owns its own loop — `weft_retrieve.contract.StageLookup`'s own docstring names the concession this is built on: "a looping technique is one plugin that owns its loop and reaches a sibling through here." `leaf` (another `Retriever`) and `sufficiency` (the `Sufficiency` contract, published at task 2.4) are both resolved by name, never imported, so a document swaps either by editing a `with:` block · **the stopping rule is `stop_reason(state) -> StopReason | None`, one pure function** — not four scattered `break`s inside a `while`. `StopReason` names exactly four facts a round can end on (`SUFFICIENT`, `MAX_ROUNDS`, `NO_NEW_EVIDENCE`, `CRITIC_UNOBSERVED`) in one fixed, documented priority order; `LoopState` is what `stop_reason` decides from, and `tests/unit/weft_retrieve/test_iterative.py`'s `test_stop_reason_*` group drives every branch directly, with a hand-built `LoopState`, never by running the loop · **bounded twice**: `for round_number in range(1, max_rounds + 1)` is what actually stops the loop from spinning forever, independent of whether `stop_reason` itself is correct; `stop_reason` is what makes the stop *honest about why* rather than the loop hiding having stopped early — `test_the_loop_never_exceeds_max_rounds` checks the call count directly · **two reference defects fixed by construction, both named in `10` §1.1's own row**: `min_loops=2` forcing a second round even when the critic said stop is fixed by `min_rounds` defaulting to `1` — nothing forced unless an operator asks for a floor, checked from both sides (`test_the_default_min_rounds_forces_nothing`, `test_min_rounds_forces_a_further_round_even_once_the_critic_is_satisfied`); a failed critique call read as "the context is complete" is fixed by `on_critic_failure: OnFailure = FAIL` propagating the hard failure instead (`test_a_hard_critic_failure_fails_the_whole_retrieval`) · **no second model call for the next round's query** — it is built from `Assessment.missing` directly (`_next_round`), Qi et al.'s trained query generator replaced by reading a fact the critic already computed, which is what keeps `cost_bound`'s floor at one call per round rather than two · **no span written here** — `StopReason` and `rounds_run` are attached to the returned `Candidates.ext` as a namespaced `IterativeRetrievalTrace`, since spans are the registration seam's concern, not a plugin's · `out.origin == in.origin` holds by construction and is asserted; every test drives at least the seam-wrapped path (fitness function 7(b)) · **recorded decisions**: `CRITIC_UNOBSERVED` is checked before the `min_rounds` floor in `stop_reason`'s priority order — forcing further rounds against a critic with nothing to say would only delay an honest stop; `Sufficiency.assess`'s `Passages` argument is built with synthetic per-round labels (`_as_passages`) since this plugin sits two positions before a `ContextPacker` assigns real ones; `StageLookup.build(Retriever, name)` is the first call anywhere in this tree to that method for a `Stage`-typed contract, and pyright cannot solve `build`'s `In`/`Out` from a `type[Protocol subclass]` (confirmed with an isolated repro) — a local `cast` states the fact `Retriever`'s own base list already declares; `llm-sufficiency` (this plugin's own default) is task 2.24's, per `.phase2-design.md`'s task map, not built here — tests drive the loop against a scripted `Sufficiency` stub
- [x] **2.21** per-document relevance grading is a reusable post-retrieval filter, and a knowledge action that reaches a second retriever is what earns the name `corrective` · owner `10` §1.1, the `corrective` row and its condition; `02` §1 · turns on — · sha `6852386` · **two plugins, not one, per the condition's own wording**: `graded-retrieval` (`weft_retrieve/graded.py`, `Reranker`) is the reference's per-document grading behaviour corrected — batched (`batch`, default 5), capped (`max_graded`, default 20, the reference's own uncapped ~30 calls/query), filtered on a named `Grade` (`weft_retrieve.prompts.Grade` — `IRRELEVANT`/`AMBIGUOUS`/`RELEVANT`, ordered in `GRADE_ORDER` rather than by `StrEnum`'s own string comparison) instead of a bare float threshold, and it registers as an ordinary `Reranker` so any pipeline with a `Ranking` can filter through it whether or not anything downstream ever reaches a second retriever · `corrective` (`weft_retrieve/corrective.py`, `Retriever`) is the plugin that earns the other name: `knowledge_action: str` carries **no default**, so a same-index `corrective` cannot be constructed — `CorrectiveConfig`'s own `_the_action_is_not_the_primary` validator also refuses `knowledge_action == primary` directly, the literal case `10` §1.1's row calls "the reference's own 'rewrite the query broader and re-ask the same index'." `primary`, `grader` and `knowledge_action` are each resolved by name through `StageLookup`, the same concession `weft_retrieve.iterative`'s own module docstring names for a looping technique, applied here to a branch that runs at most once rather than to a `for` · **graded through 2.10's `LLM` service and `weft-prompts`, never a provider directly**: a sixth registered `Prompt`, `relevance-grade`, asks the model to grade each offered passage three ways, read back through `weft_prompts.cascade.execute` exactly as `llm-rerank` and every other model-backed plugin in this pack already does · **Shi-Qi Yan, Jia-Chen Gu, Yun Zhu, Zhen-Hua Ling, *Corrective Retrieval Augmented Generation*, arXiv:2401.15884, 2024**, cited on both modules — as the origin of the per-document grading step on `graded-retrieval` (not as a claim that plugin alone is CRAG: it grades and filters, nothing more) and as the paper `corrective` earns its name against, with the divergence stated rather than hidden: the paper's own three-way action (Correct/Incorrect/Ambiguous) and its Incorrect branch's external web search are not implemented — `knowledge_action` generalises "a distinct source of evidence" to any registered `Retriever` a document names, since this build ships no web-search plugin to assume · **every knob is configuration, not a constant**: `prompt`, `role`, `keep_at_or_above`, `max_graded`, `batch`, `on_grader_failure` on `graded-retrieval`; `primary`/`primary_config`, `grader`/`grader_config`, `knowledge_action`/`knowledge_action_config`, `trigger_kept_below` on `corrective` — the `*_config` fields are `.phase2-findings.md` finding 9's own "a knob that exists in the library and not in the config model is a knob a third party cannot reach," applied here from `iterative-retrieval`'s own repaired precedent rather than waiting for a second finding to say it again · `out.origin == in.origin` is asserted in both plugins' own tests, and both are driven through `weft_kernel.seam.wrap`; neither writes a span — `CorrectiveTrace` (`triggered`, `kept`) is attached to the returned `Candidates.ext`, the same no-span-in-a-plugin rule `IterativeRetrievalTrace` already established · **recorded decisions, because the design record is silent on them**: `trigger_kept_below`'s default (`3`) has no analogue in the paper once grading is per-document rather than per-query, so it is this build's own smallest defensible number; an empty `Ranking` short-circuits `graded-retrieval` at zero model calls, below the design table's own declared floor of one — the same emptiness rule `llm-rerank` already established, read as describing the case grading actually runs rather than every possible input; `corrective` flattens a multi-list `Candidates` into one `Ranking` for its grader by concatenation (`contributor_label`-keyed `contributors`, matching `ReciprocalRankFusion.weights`'s own key), not by reusing RRF or `single-list`, since grading needs a flat list rather than a second fusion policy; `Corrective.__init__` refuses a bare `config=None` by name instead of calling a zero-argument `CorrectiveConfig()` pyright would (correctly) reject, which is also what makes `corrective` unusable as a `fallback:` candidate a named fact rather than a raw `ValidationError` about a field the fallback list never mentioned
- [x] **2.22** a query about whether the sources agree is answerable, and a critic that could not look says so instead of reporting agreement · owner `10` §1.1, the `contradiction-check` row · turns on — · sha `da174d3` · **`contradiction-check`** (`weft_generate/contradiction.py`) is the second `Generator` this pack registers: one critic call judges whether the offered passages agree (`ConflictStatus` — `AGREE`/`CONFLICT`/`UNDETERMINED`, `weft_generate.prompts`), then one generation call writes the final answer, separating agreement from conflict, cited by passage label — never sampling and voting, which is the `10` §1.1 condition that makes the reference's own name `rag_consensus` unusable here without burning `self-consistency` (`10` §1.4) · **the load-bearing property is `UNDETERMINED`, distinguishable in the *returned* model from a clean `AGREE`**: the reference's `critique.py:158-166` returned `has_consensus=True` whenever its own critique call failed; `on_critic_failure` (`weft_llm.payload.OnFailure`, one member today, `FAIL`) means a critic whose cascade could not be parsed at any tier reports `Agreement.status = UNDETERMINED` and `Answer.stance = UNDETERMINED` here, never a silently defaulted agreement, and the run still proceeds to answer the question rather than emptying the pipeline of an answer entirely — `09` §4's V2 requirement. `tests/unit/weft_generate/test_contradiction.py::test_a_critic_whose_cascade_cannot_be_parsed_reports_undetermined_not_agreement` drives the cascade through all three tiers to a hard `Failed` and asserts the returned `Agreement.status` is `UNDETERMINED` and not `AGREE`, against the same type the AGREE test above it asserts on · **`cost_bound = (2, 2)`, no skip path** — the critic's own cascade and the final answer call are both always attempted, the same arithmetic `hyde`'s own docstring states for its own single fixed call, since this technique is not conditioned on anything in the payload the way a follow-up rewrite is on history · **two new registered prompts**, `contradiction-critic` and `contradiction-answer`, added to `weft_generate/prompts.py` the same way tasks 2.16/2.17 accumulated onto `weft_retrieve/prompts.py`; the critic's own structured output (`ContradictionCritique`) is read through `weft_prompts.cascade.execute`, the final answer is plain prose read back for `[label]` markers exactly as `cited-answer` already does — never a provider called directly · `out.origin == in.origin` (as `Answer.origin`) is asserted in every test that produces an `Answer`; every test drives at least the seam-wrapped path (fitness function 7(b)) · **recorded decisions**: `max_passages: int = 8` is an added knob beyond the design table's own field list — the same lever `cited-answer`'s config gives its own prompt, so how much evidence both calls see is configuration rather than every offered passage unconditionally; citation extraction (`_offer`, `_citations_for`, `_uris_for`, `_source_id`) is a small, plugin-local duplicate of `cited_answer`'s own functions rather than a shared module, the same per-plugin-numbering split `weft_retrieve.rerank._offer` and `weft_retrieve.graded._offer` already carry — refactoring the already-shipped `cited_answer.py` to share them was out of this task's scope
- [x] **2.23** a Boolean query is parsed to an operator expression with precedence, and an empty conjunction is a visible outcome rather than a union · owner `10` §1.1, the `boolean-retrieval` row · turns on — · sha `859cc25` · **two plugins, per `.phase2-design.md`'s own task map**: `boolean-retrieval` (`weft_retrieve/boolean.py`, a fifth `QueryTransform`) tokenises a query through one cascade call (`boolean-parse`) and parses the result with a plain recursive-descent parser (`parse_tokens`) into a recursive `BoolExpr` — modelled on `weft_store.contract.Filter`'s own shape — never the reference's flat `(operator, list[str])` where any compound query became `MIXED`, handled as `OR`. Standard precedence (`not` tightest, then `and`, then `or`), explicit parentheses overriding it, proven directly against the parser with no model in the loop: `tests/unit/weft_retrieve/test_boolean.py::test_and_binds_tighter_than_or_giving_one_defined_reading` asserts `a AND b OR c` parses to `(a AND b) OR c`, never `a AND (b OR c)`. `boolean-combine` (`weft_retrieve/fusion.py`, a third `Fuser`) evaluates the tree by set algebra over `Node.id` — `and` intersects, `or` unions, `not` subtracts (only inside an `and`, refused elsewhere by name: there is no bounded corpus to complement against). The split is what makes the operator expression *data* between the two plugins: `BooleanPlan` (`provides`/`requires`), inspectable and independently testable, and `tests/unit/weft_retrieve/test_init.py::test_boolean_combine_with_no_boolean_retrieval_upstream_fails_resolution` resolves `boolean-combine` with no `boolean-retrieval` upstream and asserts `UnmetRequiresError` before either plugin ever sees a query — `.phase2-design.md`'s own exit demonstration for this task's `requires`/`provides` line · **the empty-conjunction fix is the *absence* of a special case, not the presence of one**: `_evaluate`'s `and` branch is a plain set intersection, and no line anywhere substitutes `or`'s union when that intersection is empty — the reference's own defect (`10` §1.1: "`AND` returns the union when the intersection is empty … the logical opposite of what was asked") is closed by never writing the rescue rather than by detecting and undoing it. `EmptyConjunction` (`report`/`fail`, **deliberately no `union` member**) governs only whether the caller is *told*, scoped to the case where the whole query's own root is `and` and the result is empty — `tests/unit/weft_retrieve/test_fusion.py::test_an_empty_conjunction_is_reported_never_silently_turned_into_a_union` and `::test_an_empty_conjunction_fails_the_stage_when_configured_to` prove both configured outcomes, and `Ranking.note` (a new field, this task's own addition) is what makes the report legible — `weft_retrieve.payload.RankedList.note`'s own docstring had already named "a boolean parser reporting a conjunction with no satisfying document" as this task's worked example before it existed to check the claim against · **`Query.produced_by` carries leaf identity across the retrieve stage; `ext` carries the tree, and only the tree needed a real fix to work**: `RankedList.query` surviving retrieval is a `Retriever` contract obligation, so stamping each leaf `f"boolean-retrieval#{index}"` was enough on its own, but `QuerySet.ext` — where `BooleanPlan` is attached — was silently dropped by every existing retriever before this task, since neither `VectorTopK.run` nor `NoRetrieval.run` ever forwarded it onto the `Candidates` they produced. `VectorTopK.run` now does; `tests/unit/weft_retrieve/test_vector_top_k.py::test_querysets_ext_is_carried_onto_the_produced_candidates` is the test that would have failed before it did · **recorded decisions, because the design record was silent or a smallest defensible choice was needed**: no `xor` member on `BoolOp` — `10` §1.1 names XOR "advertised in five user-facing places and implemented in none" as the reference's own defect, and an unimplemented member gated only by config would be that same defect reintroduced on spec; a task that needs XOR adds it with real evaluation semantics defined and tested against a fourth case, the same discipline `weft_retrieve.transforms`'s own module docstring already uses for its shared-base question · `not` is a real unary operator in the grammar wherever a primary is legal (so the parser can *represent* any nesting a query actually uses) and a real, named limitation at evaluation (so `boolean-combine` never invents a corpus-wide-complement semantics it has no bounded data to compute) — the split recorded on both modules' own docstrings rather than left for a diff to discover · every plugin carries its own `out.origin == in.origin` assertion and is driven through `weft_kernel.seam.wrap` (FF7(b))
- [x] **2.24** a draft's uncertainty is a replaceable, named signal rather than a phrase list, so the trigger cannot break silently under another language or model · owner `10` §1.1, the `refine-on-uncertainty` row · turns on — · sha `d55680d` · **`weft_retrieve.contract.Sufficiency` (published at task 2.4) gets its first two registered names, both this task's**: `llm-sufficiency` (`weft_retrieve/sufficiency.py`, `weft_retrieve.prompts.SufficiencyCheckPrompt`, a bilingual `en`/`pl` prompt) asks a model, through the same `weft_prompts.cascade.execute` path every other model-backed plugin in this tree already takes, whether the evidence — and, when given, a draft grounded in it — is enough; `hedge-phrases` is the reference's own `str.__contains__` mechanism, kept as the documented weak baseline `.phase2-design.md` §10's own row names it, with its one real defect fixed: `markers: Mapping[str, tuple[str, ...]]` is a locale-keyed *configuration* field an operator's `with:` block reaches, not a literal one call site closes over · **`refine-on-uncertainty` (`weft_generate/refine.py`) is the second `Generator` this task ships alongside them**: drafts through its own single call (`self._config.prompt`, defaulting to `cited-answer`'s own registered `answer-with-citations` rather than a near-duplicate), asks `self._config.signal` (default `llm-sufficiency`) whether the draft is confident, and — if not — retrieves once more through `self._config.retriever` and redrafts, up to `max_rounds` extra times; `signal` and `retriever` are both resolved by name through `StageLookup`, the identical concession `weft_retrieve.iterative`'s own `sufficiency`/`leaf` fields already take for a looping technique, applied here to a refining one — `.phase2-design.md` §4's own line: "`iterative-retrieval`, `corrective` and `refine-on-uncertainty` all need 'do it again, differently, if X'." This module never imports either `Sufficiency` implementation, so `signal: hedge-phrases` in a `with:` block is a document edit, never a code change · **the reference's own defect, closed precisely rather than generally**: `10` §1.1's row states it exactly — "`adaptive.py:83-85` tests the draft against a nine-phrase localised list … with `str.__contains__` … fires on hedging, never on unsupportedness, and breaks silently under another language or system prompt." Nothing about that failure raised, logged or failed a test; the fix is not a better phrase list, it is that the mechanism is a named, registered, swappable contract a document names rather than a constant one generator hard-codes · **the corpus's own Polish tier is the test evidence**: `tests/unit/weft_generate/test_refine.py::test_a_real_hedge_phrases_signal_triggers_a_redraft_on_a_polish_hedge` resolves `signal: hedge-phrases` to the *real* `weft_retrieve.sufficiency.HedgePhrases` class through the same `StageLookup` seam a document would use — never a test double — and a first draft written in Polish ("Nie jestem pewien, czy dostępne źródła jednoznacznie odpowiadają na to pytanie.") correctly triggers a second round exactly the way a fluent English hedge already does, with passage content mirroring `corpus/pl-wiki/las-losowy.md`'s own subject (random forests); delete `hedge-phrases`'s own `"pl"` marker table entry and this test goes red, which the reference's single-language list could never have been checked against — `tests/unit/weft_retrieve/test_sufficiency.py`'s own parametrized `test_hedge_phrases_detects_a_hedge_in_the_askers_own_language` carries the same proof one layer down, directly against the plugin rather than through the generator that consumes it · **`cost_bound = (2, 4)` is fixed, unlike `iterative-retrieval`'s unbounded `(1, -1)`**, because drafting is this plugin's own call rather than a delegated third-party `Generator` of unknown cost — floor: one draft plus one signal call when the first draft is already confident; ceiling, at the default `max_rounds=1`: two full rounds. `refinement_stop` is one named, directly-tested pure function (`RefinementStop`: `CONFIDENT`/`MAX_ROUNDS`/`NO_NEW_EVIDENCE`/`SIGNAL_UNOBSERVED`), mirroring `weft_retrieve.iterative.stop_reason`'s own shape and priority-order reasoning rather than four scattered `break`s — `NO_NEW_EVIDENCE` alone is decided one level up in `run`, once a retrieval the pure function cannot see has actually happened. `on_signal_failure` (`weft_llm.payload.OnFailure`, `FAIL`) relays a hard cascade failure exactly as it answered, the same fix `on_critic_failure` already made for `iterative-retrieval`; a *soft* "could not look" (`Assessment(observed=False)`) is `hedge-phrases`'s own honest answer when handed `draft=None` (`iterative-retrieval`'s own evidence-sufficiency use of this same contract, never this task's), at zero cost, rather than a guess either way · every plugin's own test drives it through `weft_kernel.seam.wrap` (FF7(b)); `Answer.origin`/`Candidates.origin` equal `payload.origin` by construction and are asserted · **recorded decisions, because the design table names five fields and the build needed more**: `signal_config`/`retriever_config` on `refine-on-uncertainty`, `prompt`/`role`/`max_evidence` on `llm-sufficiency`, on `iterative-retrieval`'s own `leaf_config`/`sufficiency_config` precedent for `.phase2-findings.md` finding 9 — a knob that exists in the library and not in the config model is a knob a third party cannot reach; `tests/unit/weft_cli/test_contract_reference.py`'s own `Sufficiency`-stays-unsatisfied assertion is updated to `frozenset({"weft-retrieve"})`, the expected consequence of this task landing rather than a defect; `manual/contract-reference.md` regenerated (`Sufficiency`: `Registered by weft-retrieve`)
- [x] **2.25** query scoring and routing policy are two plugins, so a threshold ladder can be replaced by a trained classifier without touching the scorer · owner `10` §1.1, the `query-scorer` row; `04` category B, the `AdaptiveRouter` row · turns on — · sha `3657691` · **`weft_retrieve/routing.py`** is the new module (`weft_retrieve.contract.QueryScorer` and `weft_retrieve.contract.RoutingPolicy`, both published at task 2.4, get their first registered names here): `query-scorer` (`LlmQueryScorer`, a `QueryScorer`) reads `ctx.require(RouteCatalogue).candidates()`, renders every routable pipeline's own `route.summary`/`route.cost` beside seven fresh-worded dimensions into one cascade call, and returns a `Scorecard` — it never writes a pipeline name in its own source, the reference's genuinely good half kept, its ten-branch `_select_strategy_from_scores` and eleven-type `_ROUTER_STRUCTURED_FALLBACK_EXCEPTIONS` silent-swap both left behind. Three `RoutingPolicy` implementations read the `Scorecard` that produces, with **no import between the scorer and any of them**: `threshold-ladder` (an ordered `Rule` table, ten illustrative seed rules never validated against a real deployment, `cost_bound = (0, 0)`, refuses a rule naming a dimension the handed `Scorecard` does not carry rather than treating it as no-match), `nearest-description` (embeds the query and every candidate's `route.summary` in one batched `Embedder` call and picks the cosine argmax, `cost_bound = (0, 1)`, open to a newcomer pipeline with no rule written at all — the mechanism task 2.8's exit demonstration rests on), and `always` (`AlwaysConfig(pipeline: str)`, ten lines, exists only to prove the first two are genuinely interchangeable). `test_swapping_the_policy_needs_no_edit_to_the_scorer` checks the ledger line directly: one `Scorecard` an `LlmQueryScorer` produced, read by `ThresholdLadder` and by `Always` through a `ServiceRegistry` carrying only a `_RefusingLLM`, proving neither policy resolves the scorer's own `LLM` service · **the seven default dimensions are named fresh for Weft** (`complexity`, `multi_hop`, `ambiguity`, `specificity`, `temporal_sensitivity`, `parametric_confidence`, `verifiability_need`) — no text lifted from the reference's own seven, citing the same three papers `10` §1.1's row does (Jeong et al.'s *Adaptive-RAG*, Mallen et al.'s *When Not to Trust Language Models*, Wang et al.'s *Self-Knowledge Guided Retrieval Augmentation*) — and they are **default configuration**, an operator's `with: {dimensions: [...]}` replaces the list wholesale, requirement 6's second clause applied to the router itself · **new registered `Prompt`, `route-query`**, arriving with `query-scorer`, the same split every model-backed plugin in this pack already makes · **repair this task's own registration forced**: `tests/unit/weft_cli/test_contract_reference.py::test_a_stage_contract_is_never_derived_as_another_stages_sibling` had been re-pointed at `QueryScorer` as its "still open" example by task 2.19's own repair; that stopped being true the moment this task registers it, and every real `Stage` contract in the tree is now registered — the test's own demonstration now uses a locally-defined `_UnregisteredRetriever` stand-in rather than chasing whichever real contract is still open, and `test_capability_siblings_excludes_every_stage_contract` gained a direct `QueryScorer` assertion; `manual/contract-reference.md` regenerated in the same commit · every plugin's own test drives it through `weft_kernel.seam.wrap` (fitness function 7(b)); `Scorecard.query == payload` and `Route.scorecard == payload` are asserted directly, this pack's own obligation for a carrier field applied to the two fields these contracts use instead of `origin` · **not built here, deliberately**: `route.yaml`, `RouteCatalogue`'s real implementation and `weft ask`'s wiring to it are task 2.8's — this task ships two plugins that read a service by type, not the machinery that populates one, per the build lead's own note that 2.8 must discover strategies from the registry with no name written into anything this task built
- [x] **2.26** every strategy this phase ships is named for the technique it implements, and no name claims a paper the code does not implement · owner `10` §1.4, §2 · turns on — · sha `0e0e929` · **the audit found no open gap**: every plugin `weft_retrieve.register` and `weft_generate.register` ship (2.13–2.25) already carries its catalogue row's own divergence, stated at the name, in its own module docstring — several citing "task 2.26's own naming audit" by name ahead of this commit, which is what a working ledger line looks like when the builders downstream of it read it before it closed. `2.31`–`2.33` (`hypothetical-questions`, `raptor`, the passage-collapse stage) are not audited here: they are unbuilt in this tree — `[ ]`, sha `—` — so there is no code yet for a name to drift from, and this task's own scope is 2.13–2.25 plus whatever `2.31`–`2.33` land as, once they do · **made durable, not just read**: `tests/docs/test_technique_naming.py` derives three checks from `10` §4 and §1.4's own markdown rather than retyping them — no registered name may claim a reserved technique, none may reuse a reference name `10` §1.4 renamed for cause, and every technique whose row cites a paper still carries that paper's own arXiv id or DOI somewhere in the pack that registers it — so a future rename or a stripped citation fails a test rather than waiting for the next hand-read audit
- [x] **2.27** the corpus an operator actually has is readable, because `.pdf` is claimed by an extractor that ships as a pack and states the media type it produces · owner `02` §1; `01` → Phase 2 · turns on — · sha `335c452`
- [x] **2.28** two extractor backends for one media type compose as a kernel combinator, and a backend that failed is distinguishable from a document that is genuinely empty · owner `04` → the `_try_extractors` kernel row and its contamination note (T1.15); `02` §1 · turns on — · sha `00fdd71`
- [x] **2.29** a vector carries semantic meaning when a model is configured, and the gate still runs with no credentials and no download because the deterministic embedder stays the offline default · owner `02` §1; `09` §4, V5's offline subset · turns on — · sha `4d7c1a8` · **scoped, on repair 2026-08-17**: `[services] embed` selects the *plugin*, and a plugin's own `with:` configuration — `OpenAIEmbedderConfig.model`, `dimensions`, `batch_size`, and `HashEmbedderConfig.dimension` before it — stays unreachable from `weft.toml`, because the route from a pipeline document to `weft index`'s stages does not exist — `weft index` still names its four stages in Python (`weft_cli/services.py`'s own docstring) rather than resolving a document. **Corrected, repair 2026-08-18**: this line previously named 2.4 and 2.8 as the tasks that would build that route; both are now closed, and neither one wired it — 2.4 built the document-to-`StageSpec` bridge (`weft_cli.compile`) and 2.8 pointed it at a new query-path command, `weft route`, leaving `weft index` untouched. **Corrected 2026-08-20 (decision `S4`): task 4.0 owns closing that gap**, placed first in Phase 4 because 4.4 persists a run carrying its *resolved* pipeline and the index path has none to persist. The concern below — that inventing a `{ use = …, with = … }` form now would be a second configuration shape whichever task built the route would have to undo — is exactly what 4.0 is required to settle rather than add to. Recorded rather than fixed here: the design record's `[services]` block is a name per role, and inventing a `{ use = …, with = … }` form now would be a second configuration shape whichever task eventually builds that route would have to undo. `manual/operations-guide.md` → *Choosing an embedder* states the limit
- [x] **2.30** the generation pack names no vendor, because a provider adapter is its own pack and the offline default is a deterministic scripted provider · owner `02` §1; `04` category A, the `LLMError` taxonomy; `09` §4, V5 · turns on — · sha `c4207bb` · **`packages/weft-llm` is a new distribution** (2.10 had not shipped it) publishing `LLMProvider`, `Conversation`/`Completion` and the fourteen-class `LLMError` taxonomy, and registering `scripted` — the deterministic offline default the gate runs against, same shape as `weft-embed`'s `hash`. `weft-openai` registers `openai` a second time, under this contract, over the same `Settings` account 2.29 built; its `_map_error` table (eleven rows, one test each, most-specific-first — `APITimeoutError` **is** an `APIConnectionError` in the installed SDK) turns every OpenAI exception into exactly one taxonomy leaf, so nothing downstream of `weft-llm` ever imports `openai` to decide what a failure means. Verified reachable: `tests/integration/test_openai_llm.py` calls the real API with the key in this environment and passes. `[llm.roles]` is new config plumbing in `weft_cli.llm_roles`, read from the same one-file parse as `[services]`, with no consumer yet — the `LLM` service that resolves a role at run time is one task later, same boundary `weft_cli.services`'s own docstring already drew. `manual/contract-reference.md` regenerated; `manual/troubleshooting.md` gained two sections (fourteen `LLMError` entries plus `UnmappedLLMRoleError`) because `ERRORS_WITHOUT_TROUBLESHOOTING_ENTRY` stays pinned empty; `weft.toml.example` and `manual/operations-guide.md` → *Choosing which model answers* document the block
- [x] **2.31** a chunk can be found by a question it answers rather than by the words it contains, because a generated question is its own retrievable node · owner `10` §1.2, the `hypothetical-questions` row; `02` §1 → *The payload model* · turns on — · sha `de63dc8` · **`packages/` goes 15 → 16**: `weft-index` publishes `Expander` (`Stage[Sequence[Node], Sequence[Node]]`, every input node unchanged plus zero or more of its own derived children) and `hypothetical-questions` is its first registration — one real completion **per node**, run concurrently via `asyncio.gather`, never one batched call: an index-path stage's batch size is however many chunks a chunker just produced, not a bounded `QuerySet`, so the numbered-offer-and-cascade shape `weft_retrieve.transforms.MultiQuery` takes for its own fan-out does not fit, and this pack needs neither `weft_prompts.cascade` nor `weft_retrieve.contract.StageLookup` — only `weft_prompts.contract.Prompts` and `weft_llm.contract.LLM`, so `weft-index` depends on neither `weft-retrieve` nor `weft-generate`. `Representation(technique=NAME)`, a namespaced `ExtModel`, marks every derived node — the shared marker `10` §1.2's `raptor` row (2.32) is meant to reuse, per `.phase2-findings.md` §11's own instruction that a summariser, a question-generator and a rephraser are three plugins over one mechanism · **the exit demonstration is real, end to end**: `tests/integration/test_hypothetical_questions_pipeline.py` extracts a real paper from `corpus/arxiv/`, chunks it, expands it through a real OpenAI completion per chunk, embeds every node (chunk and question alike) with a real OpenAI embedding, stores everything in real `pgvector`, asks the same account to reword one generated question into an independent paraphrase, embeds *that*, and asserts the nearest neighbour is a question-node whose own wording is nowhere in the corpus (checked by exact substring search, `.phase2-findings.md` finding 12's own discipline) — then runs the real `weft_generate.cited_answer.CitedAnswer` over that hit and asserts the citation names the parent chunk, not the question · **the citation obligation turned out to be deeper than a new field, and the fix is recorded on `cited_answer.py`'s own docstring**: `Answer._citations_resolve` (task 2.9) refuses a `Citation.node_id` that disagrees with the `Passage` it is paired with under its own marker, so patching `Citation` construction alone is structurally impossible — the substitution has to happen to `Passages.passages` itself, before `Answer.used` is set and before the model ever reads `_offer`'s prompt text. `weft_generate.representation.citable_nodes` is that substitution: duck-typed against a bare `technique: str` attribute (a `runtime_checkable` `Protocol`, never an import of `weft-index`), the identical no-new-dependency precedent `weft_generate.page.page_for` already set for a chunk's page number, applied here to a node's own citable identity. Batched exactly like `_uris_for`'s own existing pattern: one `store.get` call for every distinct parent a batch of offered passages actually needs. A node with more than one `Lineage.parents` entry (a future `Node.combine` summary) is left uncollapsed on purpose — `weft_generate.representation`'s own module docstring states why: no single "the" parent to stand in for. **What this does not do**: merge two offered slots that happen to resolve to the same parent into one — that is `10` §1.2's `collapse-to-parent` row, task **2.33**'s own score-policy problem, structurally distinct from this task's 1:1 identity substitution and not preempted by it · **a real, pre-existing gap found and worked around, not fixed**: `weft_cli.registry_bootstrap` registers only `weft_chunk.payload.ChunkOffset` for `weft_store.rehydrate` — `weft_pdf.PdfPages` was never registered either, predating this task — so nothing in production can round-trip a `Representation`-tagged node through a real store yet regardless. The integration test registers all three ext models itself, idempotently, mirroring `_ensure_chunk_offset_rehydrates`'s own check-first pattern; `Representation`'s own registration is *not* added to `weft_cli.registry_bootstrap`, because nothing in production can reach `hypothetical-questions` yet — no pipeline document and no CLI stage list runs it — the identical reason `weft_chunk.__init__` gives for not self-registering `ChunkOffset` either. Recorded rather than silently deferred: once a pipeline document or 2.8's router lets an ingest run include `hypothetical-questions`, `weft_cli.registry_bootstrap` needs the same call this task's own test stands in for · **`docs/10-technique-catalogue.md` §1.2 corrected in the work commit**: a stale "Phase 1" sub-note proposing phantom tasks `1.11`/`1.12` for `raptor`/`hypothetical-questions` — written before scope decision `S2` created `2.31`–`2.33` instead, and never updated when `S2` landed — is removed and the gap recorded, the same "routes to a dead phase" drift task **1.17** exists to catch. `manual/contract-reference.md` regenerated (`Expander`: `Registered by weft-index`) · unit tests for both `weft_index.hypothetical_questions` (happy path: two nodes, distinct derived children each; edge case: one node's generation degrades, its sibling's is unaffected; error case: an unmapped `prompt:` name propagates rather than degrading) and the new `weft_generate.representation` behaviour (a single-parent representation resolves; a multi-parent one does not) are driven through `weft_kernel.seam.wrap` per FF7(b)
- [x] **2.32** a query too broad for any one chunk is answerable, because summaries of clustered chunks are themselves retrievable nodes, and a summary that cannot be produced degrades the tree rather than failing the run · owner `10` §1.2, the `raptor` row; `04` category A, the RAPTOR `relationships={}` correction · turns on — · sha `af78033`
- [x] **2.33** one passage cannot occupy several slots of a ranking merely because it was indexed several ways, because collapsing a ranking to its parents is a named stage with a stated policy · owner `02` §3; `01` → requirement 6 · turns on — · sha `964a112` · **`collapse-to-parent`** (`weft_retrieve/collapse.py`) is a third `Reranker` beside `llm-rerank` and `graded-retrieval` — `Stage[Ranking, Ranking]`, the exact signature `.phase2-design.md` §A.3 names without naming a contract, registered into `Reranker`'s existing slot rather than growing a fifth query-path contract, which is what keeps the phase's own re-check true ("these three register against contracts that already exist"). Groups a `Ranking`'s hits by parent — a single-parent `hypothetical-questions`/`raptor` representation collapses under its one `Lineage.parents` entry; a `Node.combine` summary with several parents groups under its own id, the identical narrowing `weft_generate.representation._parent_of` already states for citation resolution, duplicated rather than imported because the dependency runs the other way (`weft_generate` depends on `weft_retrieve`, never the reverse) · **`CollapsePolicy`** (`max` default, `sum`, `mean`), a closed `StrEnum` dispatched through a mapping — `weft_retrieve.repack`'s own precedent for one mechanism with a field rather than three plugins. `max` is the default because it is the reading that changes a fan-out measurement the least: a chunk found four ways scores no higher than the best of those four finds alone, where `sum` would reward multiplicity of representation as if it were multiplicity of evidence · **which node survives, not only which score**: when the parent itself is already one of the group's own hits it is kept outright, no store call made; when only representations were retrieved, the parent is fetched from the store once per batch (`ctx.require(NodeStore)`, `needs_store = (NodeStore,)`), the identical batched-by-distinct-id pattern `weft_generate.representation.citable_nodes` (task 2.31) and `weft_generate.cited_answer._uris_for` (task 2.9) already use; a parent the store cannot find falls back to the group's own best-scoring representation rather than dropping the group, the same "resolves to *a* node rather than raising" choice `citable_nodes` made for the identical failure one stage later · **composition, stated because `.phase2-findings.md` §11's closing paragraph asks for it explicitly**: it sits after a `Fuser` (2.7, 2.18) and before `repack` (2.19) — `reciprocal-rank-fusion` already merges exact-duplicate `Node.id`s arriving from two channels or two fan-out queries, but has no notion that four *different* node ids are one parent indexed four ways, which is exactly the gap this stage closes; and because collapsing can change the score landscape (`sum`/`mean` combine several scores into one), this stage re-sorts and renumbers `rank` before handing off, so `repack`'s `top_n` truncation and every packing method downstream sees an order consistent with the scores next to it, never the pre-collapse arrangement with gaps where duplicates used to be · unit tests cover the four-representations-collapse-to-one happy path (rescored, ranked ahead of a hit it now outranks), the no-direct-parent edge case (a batched store fetch, `sum` policy), a deleted-parent degrade case, the closed-`CollapsePolicy` error case, and a drive through `weft_kernel.seam.wrap` per FF7(b); `out.origin`/`out.contributors` pass-through is asserted in the happy-path test, task 2.4's own obligation left to each query-path plugin · `docs/10-technique-catalogue.md` §1.5 gained a row (no citation of its own — the artefact this stage removes is measured, not sourced), keeping `tests/docs/test_technique_naming.py`'s reverse-direction check honest
- [x] **2.34** every document `corpus/manifest.toml` names can be indexed into a real store, because a control character an extractor emits is removed and counted where it is produced rather than refused by whichever backend happens to notice · owner `04` category A, the NUL-byte sanitiser; `reference/study/08-salvage.md` §T1.16; `01` → Phase 2, the two-tasks note · turns on — · sha `eeb5945` · **the placement `01`'s two-tasks note left open is settled at the kernel registration seam**, `weft_kernel.seam._sanitize_control_bytes`, riding the same `Produced` → `Node`/`tuple`/`list` walk `_strip_transient` already performs, immediately after it — never `weft-extract`, never a store. **Not `weft-extract`**: eight sites across `packages/` build a `Node` from text that came from outside the process (`weft_extract/text.py:80`, `weft_pdf/document.py:205`, `weft_chunk/fixed_size.py:145`, `weft_clean/dictionary_spacing.py:117`, `weft_clean/hyphenation.py:70`, `weft_clean/whitespace.py:63`, `weft_clean/table_linearizer.py:79`, `weft_index/raptor.py:254`), so an extractor-side fix covers two of eight — the reference's own twelve-call-site fragility (`reference/study/08-salvage.md` §T1.16, "the trap") reproduced with a smaller number. **Not a store**: `weft_store/pgvector_store.py:138` is `content TEXT NOT NULL` and refuses a NUL byte; `weft_qdrant/store.py:218` sends `node.model_dump(mode="json")` over its own wire protocol and does not — a store-level fix makes the same corpus index under one backend and fail under another, exactly what this task line refuses. **The seam already owns this class of concern** (`CLAUDE.md`: cross-cutting concerns live at the registration seam), already knows what a `Node` is, and `wrap`'s own signature already carries `distribution`/`contract`/`plugin`, so the reference's diagnostic triple (source, extractor, count; §T1.16, "the diagnostic is the point, not the strip") becomes a span attribute (`weft.nul_bytes_removed`, set inside the same `with _tracer.start_as_current_span` block `wrap` already opens, before it closes) rather than four keyword arguments an author must remember at every call site · **NUL becomes a space, never a deletion** — the reference's own choice, and this codebase has a live reason the reference only had in principle: `weft_chunk.payload.ChunkOffset` records a character offset into a parent's content, so a deletion would silently shift every offset recorded downstream of the node being cleaned · **scope is `Node.content` and every `str`-typed field an `ExtModel` in `Node.ext` carries**, walked by `type(model).model_fields` rather than a maintained list — `reference/study/08-salvage.md` §T1.20(a)'s recorded lesson about the transient scrub applies unchanged. **Measured, not assumed**: no first-party `ExtModel` shipped as of this task populates a text field — `weft_pdf.PdfPages` (`weft_pdf/document.py:94-131`), the one built directly from what a PDF backend reads, carries only `backend: str` (a plugin name) and `starts: tuple[int, ...]` (offsets) — so today's corpus exercises `content` only; the `ext` walk covers the column-level fact (`weft_store/pgvector_store.py:141`'s `ext JSONB NOT NULL` refuses a NUL byte exactly as `TEXT` does) rather than a currently-populated field, and costs one `isinstance` check per field on a namespace that already changed · **the 65-byte figure was re-measured directly against `PdfTextExtractor.run` on `corpus/arxiv/2508.18901v1.pdf`** (not merely cited from the audit note) and confirmed exact; the same sweep over every corpus PDF found exactly one more affected document, `corpus/arxiv/2510.00907v1.pdf`, 2 NUL bytes — matching the note's "two of the corpus's nineteen PDFs do this" — and zero elsewhere · **the exit demonstration is real and reversible**: `tests/integration/test_nul_byte_sanitisation.py` runs `corpus/arxiv/2508.18901v1.pdf` through the ordinary `pdf-text` → `fixed-size` → `hash` → `pgvector` pipeline, composed by `weft_kernel.runner.Runner` exactly as `tests/integration/test_ingest_pipeline.py` composes the built-in four, against the live container, and asserts every stored node's `content` is free of `\x00`; stashing the seam change and rerunning the same test reproduces `WeftError: 'store' failed: PostgreSQL text fields cannot contain NUL (0x00) bytes` verbatim, checked directly rather than assumed · **kernel budget**: 2,731 → 2,797 non-blank, non-comment, non-docstring lines (budget 3,500, review trigger 2,800 — 3 lines under it), `tests/architecture/test_ff3_kernel_budget.py` green, not edited · unit tests in `tests/unit/weft_kernel/test_seam.py` cover content-only NUL, NUL inside an ext model's `str` field, a clean node returning the same object (no rebuild), NULs across a `list` of nodes, and a non-`Node` payload passing through untouched, all driven through `weft_kernel.seam.wrap` per FF7(b) · `uv run poe ci-checks` green: 64 architecture tests, 1,277 passed + 1 skipped
- [x] **2.35** the cleaning chain is the six processors `04` names rather than four, so the constraint every later processor's regex depends on is expressed in `intact`/`destroys` like the other five · owner `04` category A, the six cleaning processors; `reference/study/08-salvage.md` §T1.1; `01` → Phase 1 **Lift**, corrected 2026-08-18 · turns on — · sha `296be69` · **`weft_clean.unicode_normalizer.UnicodeNormalizer` and `weft_clean.artifact_remover.ArtifactRemover`** are the two new plugins, verified at `reference/study/08-salvage.md` §T1.1 and at source, `unicode_normalizer.py:12-37` and `artifact_remover.py:10-79` — six plugins registered where four were, `weft_clean/__init__.py`'s `register` naming all six under `Cleaner`. **`UnicodeNormalizer` drops the reference's own redundant second normalisation call**: `unicode_normalizer.py:32-35` calls `ftfy.fix_text(text)` then `unicodedata.normalize('NFC', fixed)`, but `ftfy.TextFixerConfig.normalization` already defaults to `"NFC"` — a correction, not a copy, so `weft_clean.unicode_normalizer._normalize` is one call. **`ArtifactRemover` lifts two behaviours only**: the page-number regex and the 0.5 non-alnum separator filter (`artifact_remover.py:22`, `:26`) — its documented header/footer removal is refused: `process()` is 28 lines with no interval analysis, no line-frequency map, no positional logic anywhere in the 79-line file (§T1.1, `artifact_remover.py:16`'s docstring promising what the code does not do), recorded in `weft_clean/artifact_remover.py`'s own module docstring as a scar rather than quietly worked around. **The page pattern stays the English literal `Page`** — §T1.1's own correction item 6 says "change it to a per-language list", but the reference's file never supplies one; inventing a Polish (or any other) translation with no source behind it is exactly the fabricated-coverage failure `weft_clean.dictionary_spacing`'s own module docstring already refused once for its 243-word set, so the limitation is stated plainly instead of papered over — the separator-line filter is unaffected, reading Unicode alphanumeric properties rather than a word. **The ordering constraint the ledger line names is `weft_clean.property.Verbatim`**, a third `Property` beside `Newlines`/`WhitespaceGaps`: "a node's text is still, character for character, what extraction handed over." `UnicodeNormalizer` is the only stage declaring `intact = (Verbatim,)` (and, honestly, `destroys = (Verbatim,)` too — repairing mojibake is itself a character-stream change, and a stage's own `destroys` is checked against earlier stages only, never itself, in `weft_kernel.resolution.resolve`); every other processor's `destroys` tuple now names `Verbatim` alongside whatever it already destroyed — `hyphenation.py`, `table_linearizer.py`, `dictionary_spacing.py`, `whitespace.py` — which forces `UnicodeNormalizer` to position 1 by the identical mechanism `WhitespaceNormalizer`'s "must run last" already uses, pointed the other way, with no new machinery. `ArtifactRemover` additionally declares `intact = (Newlines,)`: both its behaviours are line-oriented by construction (`MULTILINE` anchoring, per-line splitting), the same dependency `HyphenationRepair` already declares. `weft_clean/property.py`'s module docstring is rewritten from "why two properties" to "why three", stating the asymmetry: one stage destroys `Newlines`/`WhitespaceGaps` together; every stage destroys `Verbatim`, because repairing text is what a `Cleaner` is for. **The order is machine-checked, not asserted**: `tests/unit/weft_clean/test_ordering.py` adds `test_hyphenation_before_unicode_normalize_fails_resolution_naming_both_stages` — a pipeline placing `UnicodeNormalizer` after `HyphenationRepair` fails `weft_kernel.resolution.resolve` with `IntactViolationError` naming `unicode`, `hyphenation` and `Verbatim` — beside the two pre-existing whitespace-ordering tests and a rewritten six-stage legal-order test matching the reference's own sequence (`indexing/cleaning/pipeline.py:30-49`). No pipeline document in this repo names the cleaning chain yet, so none needed updating. `ftfy>=6.2` is `weft-clean`'s one new dependency (`packages/weft-clean/pyproject.toml`); `uv.lock` (gitignored) relocked. 51 `weft_clean` unit tests pass; `uv run poe ci-checks` green — 64 architecture tests, 1291 passed / 1 skipped overall.
- [x] **2.36** an error that reports an unresolvable name cannot omit the alternatives, because it carries them as a typed field a check can see rather than prose a reviewer has to notice · owner `01` → *Fitness functions* 12; `05` → G11 · turns on FF12 · sha `53d0b9f` · **the family is identified structurally**, `weft_kernel.errors.UnresolvedNameError` (`packages/weft-kernel/src/weft_kernel/errors.py:52`), a marker with no `__init__` of its own — mixed in as a second base alongside whichever `WeftError` subclass a member already was (`PipelineResolutionError`'s four fields, `LLMError`'s `provider`/`model`, or plain `WeftError`), so membership is one mechanical fact, `issubclass(cls, UnresolvedNameError)`, never a class-name heuristic. Every member's own `__init__` declares `valid_options: tuple[str, ...]` keyword-only with **no default**, so a raise site that forgets to collect the registered names fails to construct the exception at all — the structural fix, not only the check that proves it happened · **the count is 20, not the 18 `01` claimed** — audited by reading every raise site of all 82 error classes (`WeftError` itself, `weft_retrieve.boolean.BooleanSyntaxError`'s bare `Exception`, and 80 `WeftError` subclasses across the first-party tree — matches `01`'s own "82 error classes" exactly) for whether it already computes and interpolates a concrete, enumerable collection of the names that were valid where the one given was not. `01`'s two missed sites: `weft_cli.run_services.StoreCapabilityMissingError` (`packages/weft-cli/src/weft_cli/run_services.py:76`, raise site `:183-202` — `offered`/`named`, the store names that do provide the missing capability) and `weft_prompts.errors.TemplateVariableError` (`packages/weft-prompts/src/weft_prompts/errors.py:13`, one of its two raise sites — `packages/weft-prompts/src/weft_prompts/template.py:61-66` — already named `fields`, the input model's own field names, for the placeholder-not-supplied case; the other raise site, `template.py:52-56`, a template that does not even parse, carries `valid_options=()`, honestly, since there is no name that failed to resolve). **The 20, with class and raise site**: `weft_kernel.registry.UnknownPluginError` (`:168`, raise `:519-524`), `weft_kernel.registry.UnresolvedPluginPinError` (`:135`, raise `:409-415`), `weft_kernel.context.UnresolvedServiceError` (`:77`, raise `:147-152`), `weft_kernel.discovery.UnknownPackSettingsError` (`:226`, raise `:583-588`), `weft_kernel.resolution.UnknownParentPipelineError` (`:320`, raise `:928-939`), `weft_kernel.resolution.UndefinedVarError` (`:398`, raise `:1509-1518`), `weft_kernel.resolution.StaleOperatorTargetError` (`:436`, three raise sites — `:1074-1086`, `:1224-1236`, `:1385-1394`), `weft_kernel.runner.UnknownFallbackError` (`:321`, raise `:674-686`), `weft_cli.compile.UnknownStagePluginError` (`:101`, raise `:203-214`), `weft_cli.compile.AmbiguousStageContractError` (`:66`, raise `:218-232`), `weft_cli.ingest.UnclaimedFormatError` (`:123`, two raise sites — `:263-269`, `:326-332`), `weft_cli.ingest.AmbiguousExtractorError` (`:95`, raise `:299-310`), `weft_cli.route_ask.UnroutedPipelineNameError` (`:65`, raise `:143-153`), `weft_llm.models.UnknownModelError` (`:46`, raise `:145-151`), `weft_llm.models.AmbiguousModelError` (`:64`, raise `:152-159`), `weft_llm.roles.UnmappedLLMRoleError` (`:41`, raise `:76-80`), `weft_store.fields.UnaddressableFieldError` (`:106`, raise `:188-194`), `weft_store.pgvector_store.UnknownTextSearchConfigError` (`:312`, raise `:619-625`) — plus the two named above · **boundary cases examined and excluded, with the reason**: `weft_kernel.discovery.EnvInterpolationError` (no enumerable registry of "valid" environment-variable names to draw from), `weft_kernel.registry.DuplicateRegistrationError` (two names that both already resolved — a collision, not an unresolved lookup), `weft_store.fields.FilterOpMismatchError` and `weft_prompts.errors.UnusedTemplateFieldError`/`MissingFallbackLocaleError` (no alternatives collection computed at today's raise site), `weft_cli.ask.NotVectorSearchableError`/`weft_kernel.resolution.PipelineCycleError`/`weft_llm.models.ModelProviderMismatchError` (a capability mismatch, a whole-chain report, or a two-way disagreement — not a name against a candidate set) · **the check**, `tests/architecture/test_ff12_unresolvable_name_carries_options.py`, is structural throughout: `_carries_valid_options_field` reads `typing.get_type_hints(cls.__init__)` and the parameter's own default via `inspect.signature`, never a formatted message. `NAME_RESOLUTION_FAMILY` is the pinned membership list, guarded against silent omission by `test_the_discovered_family_matches_the_pinned_list` — a live walk of every `UnresolvedNameError` subclass the first-party tree defines today, compared against the pinned list in both directions, so a new family member that mixes the marker in and is not added here fails the build. `FAMILY_MEMBERS_WITHOUT_A_TYPED_FIELD` is `01`'s own waiver, pinned empty, guarded by `test_waiver_list_is_empty`. Both ratchets carry a vacuousness self-test (`test_the_discovery_ratchet_can_actually_fail`, `test_missing_typed_field_check_can_actually_fail`), the `test_ff9c_every_contract_has_a_stranger.py` precedent applied here · **FF0 reachability verified, not assumed**: `pyproject.toml`'s `arch` task is `pytest tests/architecture -q`, already the `ci-checks`/`ci-no-tests` sequence's own member (`test_ff0_gate_in_the_gate.py`'s `ARCHITECTURE_TASKS = {"arch"}`), so a new file under `tests/architecture/` is reachable with no `pyproject.toml` edit — confirmed by running `test_ff0_gate_in_the_gate.py` green, unedited, in the same gate run · **kernel budget**: 2,800 → 2,911 non-blank, non-comment, non-docstring lines (`tests/architecture/test_ff3_kernel_budget.py`'s own `_count_kernel_lines()`; budget 3,500, review trigger 2,800 — 111 over the trigger, 589 under the budget), neither constant edited; eight of the twenty family members are kernel classes, and the increase is `UnresolvedNameError` plus their own `valid_options` plumbing · `01` → *Fitness functions* item 12 corrected in the same commit: 18 → 20, the two missed classes named, the membership mechanism stated · `docs/README.md`'s Status prose corrected in this commit, not moved: the passed-count and architecture-test count, and 2.36 recorded as closed alongside 2.34 and 2.35 — the Exit checkbox and the phase move are left for the project owner · `uv run poe ci-checks` green: 75 architecture tests (was 64), 1,303 passed + 1 skipped (was 1,291 passed + 1 skipped) · **two repairs, 2026-08-18, from a review of `53d0b9f`.** (1) Four `PipelineResolutionError` subclasses that are also `UnresolvedNameError` — `UnknownParentPipelineError`, `UndefinedVarError`, `StaleOperatorTargetError` (`weft_kernel.resolution`) and `UnknownFallbackError` (`weft_kernel.runner`) — each carried an identical 19-line `__init__` forwarding the family base's four fields and setting `valid_options`; the review measured roughly 57 of task 2.36's 111 added lines in that duplication. Collapsed into one shared `weft_kernel.runner.UnresolvedNameInPipelineResolutionError`, listed first among each of the four's bases so Python's MRO finds `__init__` there; deliberately **not** a `WeftError` subclass (it would otherwise need its own `manual/troubleshooting.md` entry for a class nothing ever raises directly, task 0.14's own coverage ratchet) and deliberately **not** mixed into `UnresolvedNameError` itself (it would otherwise be discovered as a 21st family member by FF12's own walk). Public rather than `_`-prefixed: `[tool.pyright] typeCheckingMode = "strict"`'s `reportPrivateUsage` refuses a leading-underscore name imported into another module's source, which rules out the `weft_kernel.pipeline._QUALIFIER` duplicate-rather-than-reach precedent for a class actually meant to be shared; kept out of `weft_kernel/__init__.py`'s export list regardless, since no contract in `02` gives a pack a reason to raise `PipelineResolutionError`'s specific four-field shape. The required-keyword-no-default guarantee was reproved at the interpreter for all four post-collapse — `UnknownParentPipelineError("x")`, `UndefinedVarError("x")`, `StaleOperatorTargetError("x")` and `UnknownFallbackError("x")` each raise `TypeError: ...__init__() missing 1 required keyword-only argument: 'valid_options'` — and FF12's own family walk was reconfirmed to discover exactly the pinned 20, unchanged, both `_all_unresolved_name_subclasses` (`test_ff12_unresolvable_name_carries_options.py`) and `_every_family_member` (`tests/unit/weft_kernel/test_pipeline_resolution_error_family.py`) already being recursive over `__subclasses__()` with no edit needed to either walk. Kernel budget: 2,800 → 2,911 → **2,869** non-blank, non-comment, non-docstring lines (`_count_kernel_lines()`; budget 3,500, review trigger 2,800 — 69 over the trigger, still 631 under the budget), neither constant edited. (2) `01`'s own corrected paragraph (added by `53d0b9f`) derived the 18 `01` originally claimed as "the class name reads `Unknown`/`Unresolved`/`Ambiguous`" — checked directly against `NAME_RESOLUTION_FAMILY` and found false: only **12** of the 20 pinned class names contain one of those three words, six more misses than the two `53d0b9f` already named (`UndefinedVarError`, `StaleOperatorTargetError`, `UnclaimedFormatError`, `UnroutedPipelineNameError`, `UnmappedLLMRoleError`, `UnaddressableFieldError`). `01` → *Fitness functions* item 12 corrected again, same day: the false name-pattern derivation replaced with the true one — the original 18 rested on reading each error's own failure mode by hand, and a name pattern applied instead would have found 12, which is now stated as the argument for the structural `issubclass` check rather than a false account of how the 18 were found · `uv run poe ci-checks` reconfirmed green after both repairs: 75 architecture tests, 1,303 passed + 1 skipped, unchanged

**2.31–2.33 are added scope, recorded as decision `S2`** (`README.md` → *Decision log*), per `09` §6.4.

- **Requirements touched: 6**, in both clauses, and **3**. A representation you cannot retrieve
  separately is a technique the product does not ship; a representation whose generator a third party
  cannot replace is a feature rather than a capability.
- **Why it lands here rather than nowhere.** `10` §1.2 filed `hypothetical-questions` and `raptor` as
  **Phase 1 work**, and Phase 1's own ledger (1.1–1.18) never contained them. Phase 1 has exited, so
  until this decision **no phase owned them** — not a choice anybody made, but a gap between two
  documents that only shows up when both are read at once. `10` §1.2 is corrected in the same commit,
  because a document assigning work to an exited phase is precisely what task **1.17** made false.
- **Why they are not deferred.** The mechanism they need — a derived `Node` carrying its own embedding
  and a `Lineage` naming its parent — already exists in the kernel and needs nothing added. What was
  missing was any plugin using it, and therefore any evidence that multi-representation indexing works
  end to end. `01` → *The least-architecture check* wants a forcing function before deferring, and the
  only honest one here was *"deferred until a phase claims the index path"* — which no phase did.
- **2.33 is not optional, and it is why this is three tasks rather than two.** When one chunk is
  indexed as four nodes, an unmodified ranking can hand that chunk four of its top five slots. Every
  fan-out measurement in 2.16–2.18 would improve and none of the improvement would be real, and the V3
  baseline would absorb the artefact silently — `09` §4.2's failure exactly.
- **Exit demonstrations.** 2.31: a question whose wording appears nowhere in the corpus retrieves the
  chunk that answers it, and the citation resolves to the parent chunk rather than to the generated
  question. 2.32: a query no single chunk answers is answered from a summary node, and a chunk whose
  summary could not be generated stays retrievable — the tree degrades rather than the run failing.
  2.33: with one parent indexed four ways, a ranking that would have held four of its representations
  holds the parent once, and the surviving score follows the stated policy.
- **Re-check** (`09` §6.4 step 4). Phase 2's exit is unchanged — 2.8 plus FF9(c). No fitness function
  is activated or stranded. **Corrected at task 2.11**: this note originally claimed the FF9(c) bill
  "does not grow" because "these three register against contracts that already exist" — true for 2.32
  and 2.33, which register into `Expander` and `Reranker` respectively, but not for 2.31 itself, whose
  own line states plainly "`weft-index` publishes `Expander`" — a contract nobody had published before
  it. The bill did grow by one here; 2.11's own accounting counts it. Phase 4's V6 is unaffected, and no
  earlier phase's exit referenced this work.

**2.27 also published `Renderer` and `Rendition`**, with the `markdown` and `plain` registrations, in
`weft-extract` — the phase design's Amendment A.2 assigns them to this task by name, on the grounds
that 2.27's exit demonstration is that an operator's PDF becomes readable and an operator who cannot
get the parse back out in a format they can read has not been given that. It is disclosed here rather
than smuggled in. Its first build shipped without them and a reviewer caught it; the repair commit
built them.

**2.27's exit demonstration was not met by its first commit, and is now.** `weft index` pinned the
extractor to `"text"` and filtered discovery on `weft-extract`'s own `EXTENSIONS`, so `weft index
corpus/mrmr` discovered zero documents and exited 0 — a PDF could not reach `Node`s through the
ordinary ingest pipeline at all. The accept set is now derived from the registry
(`weft_extract.accept.claimed_extensions`, over `Registry.names_for`), and a format two extractors
claim refuses by name rather than being chosen silently. Verified end to end: `weft index
corpus/mrmr --extract pdf-text` stores 925 nodes and `--extract pdf-layout` stores 1 811, with no
edit to core in either case. **This is the derived accept set `11-multimodal.md` §2.1 predicted would
be needed and filed under its own proposed numbering (1.13) with no live ledger row** — it is owned
by 2.27 because 2.27's exit demonstration is what it makes true, and FF5 is *not* turned on here: the
fitness function is `01`'s to place, and this task's line still reads `turns on —`.

**2.28's boundary distinction was verified empirically before it was built, not assumed.** The
design record flagged one thing to check rather than trust: whether `pypdf` and `pdfplumber` can
actually tell "no text layer but an image present" from "text layer with no glyphs", since the
whole demonstration rests on it. Measured against both libraries, the *text* cannot — each returns
`''` for both cases. The **image evidence** can, and 2.27 had already built the count on both
sides (`weft_pdf.pdf_text._declared_image_count`, `len(page.images)` for `pdf-layout`), so the
distinction is real and no invented one was needed. Two things from the design's §6 are
deliberately **not** built here and are not silently dropped: `weft plugins doctor` reporting
uninstalled `fallback:` names — the command does not exist yet, and it has no shipped or
contributed pipeline documents to walk until 2.8 builds the contribution seam — and a `fallback:`
route through `weft index`, which has no `--fallback` option; the CLI reaches `StageSpec.fallback`
when `weft_cli/compile.py` turns a resolved document into specs. **Corrected, repair 2026-08-18**:
this sentence named 2.4 and 2.8 as the tasks that would deliver that route; both built
`weft_cli/compile.py` and pointed it at a new query-path command (`weft route`, 2.8) instead, so
`weft index` still has no `--fallback` option and no task in this ledger currently owns adding
one — see 2.29's own note, corrected in the same commit.

**2.29 puts the selection in a file, because a capability nobody can select is not one.**
`weft-openai` registers `openai` under the `Embedder` contract `weft-embed` publishes, beside the
deterministic `hash` plugin, and `[services] embed` in `weft.toml` chooses between them — the
`weft-cli` half is not incidental plumbing but the task's own point, since binding constraint 9
(`.phase2-findings.md`) requires that swapping which embedder runs be a configuration edit and
nothing else. Three things are worth recording rather than rediscovering. **Every settings field on
the new pack has a default**, so `register()` cannot raise on a machine with no credential: a
required `api_key` would report the pack `failed`, remove `openai` from the registry, from
`manual/contract-reference.md` and from FF11(b)'s resolution check, and no test anywhere would have
gone red. The refusal happens at use instead, naming `[packs.weft-openai] api_key`. **A failure is
raised, never returned as `Failed`**, which deliberately makes this embedder unusable as a
`fallback:` target — a chain that fell through from a semantic embedder to a deterministic one would
write vectors from two unrelated spaces into one index, and an index like that does not crash, it
answers plausibly. **The semantic claim is measured, and it is measured in a test**: 0.62 cosine
between two ways of saying one thing against 0.07 to an unrelated sentence, with `HashEmbedder`
scoring 0.005 and -0.005 on the same three strings at the same width. That comparison lives in
`tests/integration/test_openai_embedder.py`, which skips with a stated reason when
`OPENAI_API_KEY` is absent — the container's own discipline applied to the other external
dependency, and what keeps `poe ci-checks` green with no account and no network.

**2.27–2.30 are added scope, recorded as decision `S1`** (`README.md` → *Decision log*), per `09` §6.4
— adding and cutting are the same operation and both are decisions, so neither happens silently in a
commit that was about something else.

- **Requirements touched** (`01` → *What "modern and elastic" has to mean concretely*): **6**, in both
  clauses — a format the engine cannot read is technique it does not ship, and a vendor name compiled
  into the generation pack is a black box rather than a capability. **1 and 4** are touched only in the
  sense that every one of the four arrives as a package registering through the public path; none of
  them edits core. **2.28 is the exception and it is not new scope at all** — `01` → Phase 2 **Lift**
  already assigns the fallback-chain combinator to this phase, in the kernel; it is listed here because
  it had no task line, not because it was decided now.
- **Why it lands here.** V1 (`09` §4) requires the corpus to cover every format an installed extractor
  claims, and the corpus is nine PDF papers. Without 2.27 the phase's own prerequisite cannot be built;
  without 2.29 and 2.30 the V3 baseline measures a content hash rather than a retrieval system, which
  is `09` §4.2's failure with the labels changed.
- **Exit demonstrations.** 2.27: a PDF in the named corpus produces `Node`s through the ordinary ingest
  pipeline, with no edit to core. 2.28: with two backends registered and the first one raising, the run
  reports which backend answered — and an empty document is a different outcome from a failed one.
  2.29: the same pipeline resolves against either embedder by configuration alone, and the offline gate
  selects the deterministic one without a credential. 2.30: the generation pack imports no vendor SDK,
  and an unconfigured provider refuses by name naming the valid options.
- **Re-check** (`09` §6.4 step 4). Phase 2's exit is unchanged — task 2.8 plus FF9(c) — because none of
  the four is an exit criterion. No fitness function is activated or de-activated: all four carry
  `turns on —`, and FF9(c) at 2.11 now covers four more published contracts rather than fewer. Phase 4's
  V5 is *narrowed*, not widened: the offline subset it owns is made possible by 2.29 and 2.30 rather
  than by Phase 4 retrofitting one. No earlier phase's exit referenced any of this work.

**2.34, 2.35 and 2.36 were added 2026-08-18**, after 2.1–2.33 were all ticked. 2.34 and 2.35 come
from the Phase 2 exit reference audit `CLAUDE.md` requires before a phase is declared complete, and `01`
→ Phase 2 carries both assignments with their evidence. **2.36 comes from G11**, which settled the
same day and turns on **fitness function 12**; it lands in Phase 2 rather than at the head of Phase 3
for one reason worth stating — Phase 3 is ⛔ behind G8, FF12 has nothing to do with G8, and parking
it there would block a finished decision behind an unrelated open one. `01`'s own requirement that
G11 be settled *"before Phase 3, where user-facing text multiplies"* then reads literally.

**Phase 2's exit gains a clause, and 2.34/2.35 do not touch it.** 2.34 and 2.35 activate no fitness
function and are not exit criteria; whether the Exit box is ticked before or after them is the
project owner's call. **2.36 is different**: `09` §6.3 step 3 requires a new fitness function's
activation to sit in the exit criterion of the phase that activates it, so FF12 joins Phase 2's exit
and the box cannot be ticked until 2.36 is green. *(Corrected 2026-08-18, same day: this paragraph
first said the exit was unchanged, which was a straight §6.3 violation — a phase that opens a fitness
function and exits without switching it on is the exact state FF0 exists to prevent, one level up.)*

This phase is **36 of 36**, closed 2026-08-18. It was recorded at 33 of 36 while the three tasks the
exit reference audit added were open, rather than only in a commit message, because a phase that gains
work after its last box is ticked is exactly the state a ledger exists to hold.

**Exit** (`01` → Phase 2): task 2.8, plus FF9(c) wired and green (task 2.11) and FF12 wired and green (task 2.36).
**Satisfied 2026-08-18**, and each clause carries its own evidence rather than the phase's word for
it: **2.8** is `tests/architecture/test_ff4_no_closed_key_space.py` — the router discovers a strategy
from the registry, no enum and no closed key space; **FF9(c)** is
`tests/architecture/test_ff9c_every_contract_has_a_stranger.py` — all 23 published contracts carry an
out-of-tree implementation, computed live off this repository's own registrations and proven against
four real throwaway environments, with `CONTRACTS_WITHOUT_AN_EXAMPLE_PACK` pinned empty; **FF12** is
`tests/architecture/test_ff12_unresolvable_name_carries_options.py` — 20 error classes across five
distributions carry `valid_options` as a required, no-default keyword-only field, so a raise site that
forgets to collect the registered names cannot construct the exception at all, with
`FAMILY_MEMBERS_WITHOUT_A_TYPED_FIELD` pinned empty and two vacuousness self-tests proving the check
can fail. `uv run poe ci-checks` green: **1303 passed, 1 skipped, 75 architecture tests** (64 before
FF12). **One thing this phase hands forward, unresolved on purpose**: `weft-kernel` finished at
**2,869 lines**, past `test_ff3_kernel_budget.py`'s **2,800 `REVIEW_TRIGGER`** and under its 3,500
`BUDGET`. 2.36 is what put it there and 2.36's own repair returned 43 of those lines; neither constant
was touched, because `phase-step` states the budget is never edited in the change that grew the
kernel. The number is carried into Phase 3's agenda as a boundary conversation, not resolved here by
raising the line it crossed.

**Raised, not resolved.** `01` → Phase 0 **Lift** lists the prompt layer, the three-tier cascade,
model strings and the `LLMError` taxonomy as category-A lifts, while `06` → *What Phase 0 must not
build* assigns generation, prompts, the LLM adapter and `weft-llm` to Phase 2. Task 2.10 places them
here. The discrepancy belongs to `01` and `06` and is flagged rather than decided.

---

## Phase 3 — The CLI

**Gate: none — G8 settled 2026-08-18.** The answer is *shell*, and it is not a deferral: `03`'s
governing rule keeps a planning loop out of the adapter permanently, so no later phase turns this
REPL into an agent. Weft's agentic front end is a **pack**, and it is **Phase 7**. The
`agentic-patterns` handoff moved with it, to **G12**.

**The ⚠ on 3.4, 3.5 and 3.11 is dropped**, per the working protocol above: a gate closing means every
downstream ⚠ task is re-derived from the reference document the gate changed, not merely unmarked.
Re-derived here — all three stated true properties already and none needed rewriting, because each
was written against `03`'s shell as its hypothesis and that hypothesis is what held. **3.4 gains
weight rather than losing it**: `03` → *Two modes, one implementation* now states as a rule what that
task's sentence implies, that a `Command` returns a typed result and never writes to a stream, and
that property is the whole of what this phase owes Phase 7.

- [x] **3.1** a pack registers a command exactly as it registers a retriever, and a command that declares no permission class fails to register while its author is standing there · owner `03` → *Plugin-contributed commands*, *Permissions*; `02` §1 · turns on — · sha `ae4f3eb`
- [x] **3.2** `weft --help` cannot drift from what is installed, because core has no command list to edit · owner `03` → *Plugin-contributed commands* · turns on — · sha `81c335b` · **`weft_cli.cli.COMMANDS`/`build_parser`/`command_key`/`handle_*` are gone.** All five built-ins (`index`, `ask`, `route`, `plugins list`, `plugins doctor`) are now `Command` plugins in a new module, `weft_cli.commands`, registered through `weft-cli`'s own `[project.entry-points."weft.packs"]` line — the same seam a stranger's pack uses. `weft_cli.cli.build_parser(registry)` walks `Registry.names_for(Command)` into an argparse tree (`weft_cli.argparse_gen.add_model_arguments` turns each command's `args_model` fields into positionals/flags, mechanically: no default → positional, a default → `--flag` with underscores turned to hyphens, a `StrEnum` → `choices=`-bounded), recursing on shared name prefixes so a multi-word registered name (`"plugins doctor"`) becomes a nested subparser with no special-cased code for it · **the entry-point owner is `weft-cli` itself, argued rather than defaulted to the task's own suggestion.** The alternative — a twelfth distribution, purely to hold `register()` — was rejected: every one of the five commands calls straight into `weft_cli.ingest`/`ask`/`route_ask`/`plugins_report`, modules that already live here, and a sibling distribution would need `weft-cli` as a dependency to reach them, the identical inverted-dependency shape 3.1's own module docstring refuses for the *contract* (which is why `Command` lives in `weft-command`, not here) — refusing it for the contract and then re-introducing it one layer up for the registrations would be incoherent. `weft-cli` already depends on every first-party distribution these five need, and its own handlers already lived here; splitting registration out would buy nothing · **`Command` grew one required declaration, `help`.** 3.1 shipped `required_declarations = ("permission_class",)`; task 3.2 needed a one-line summary string to generate `--help` from and nothing on the contract carried one, so `weft_command.contract.Command.required_declarations` is now `("permission_class", "help")` — refused at registration, loudly, on the identical mechanism, and `COMMAND_CONTRACT_VERSION` moved to `"1.1.0"` to mark the shape change. `tests/unit/weft_command/test_contract.py` gained the mirror-image refusal test (`help` present, `permission_class` absent — already covered; `permission_class` present, `help` absent — new) · **the 3.1/3.4 split its own docstring predicted was wrong, and this task said so rather than defaulting past it.** 3.1's closing paragraph assigned "rewiring `weft_cli.cli.COMMANDS`'s five built-in commands onto this contract, and building the renderer" to task 3.4. This task's own brief re-scoped that explicitly — build the registry-driven parser/help *and* convert the five built-ins *and* the smallest honest renderer, but not the REPL and not the plural `--json`/REPL renderers — and the stop condition ("if converting the built-ins turns out to require the REPL or the plural renderers, stop") never fired: nothing here needed either. `weft_command.contract.Command`'s own docstring is corrected in the same commit to record why · **`weft_cli.render` — the minimal renderer, one function per direction.** `render_outcome(Outcome[CommandResult]) -> Rendered` (`stdout: str | None`, `stderr: str | None`, `exit_code: ExitCode`) isinstance-dispatches over the five known first-party result types, reproducing each retired handler's exact printed text — proven byte-for-byte in `tests/unit/weft_cli/test_render.py` against the literal strings the old `handle_index`/`handle_ask`/`handle_route`/`handle_plugins_list`/`handle_plugins_doctor` printed (e.g. `"produced 2, nothing to produce 1, failed 0. nodes now stored: 2."`, `"no matching passages found."`, the JSON `--format` line, `"routed to: …"` plus citation lines). A result type this module was not written against — nothing is, today, beyond the five — falls back to `model_dump_json()` rather than silently printing nothing. `render_refusal(WeftError) -> Rendered` reads `.exit_code` off a `CommandRefusalError` directly, or defers to `exit_code_for` for anything else — `03` → *Output* gained a narrowing blockquote recording why one exception carries its own code · **exit codes did not move, only their vehicle.** `IndexCommand`/`AskCommand` still call `require_active`/`require_plugin` before running, unchanged; a refusal is now raised as `CommandRefusalError(message, exit_code=code)` instead of printed-and-returned directly, because `run()` cannot print. `IndexCommand`'s "some files failed" case stays a plain `Produced(IndexCommandResult(summary=..., ...))` — not `Outcome.Failed` — with the exit-code decision (`summary.failed == 0` → 0, else → 1) computed in `weft_cli.render._render_index`, which is what "the CLI renders it" means applied to a process's own exit status rather than to text · **dependency injection through `ctx.services`, not a new contract field.** A built-in `Command.run(self, args, ctx)` needs the plugin registry, discovery reports and `[services]`/`[llm]` — things only `weft_cli.registry_bootstrap.build_dependencies` computes, and unavailable at registration time (registration is what *causes* discovery to run; `Dependencies` does not exist yet when `register()` executes). `weft_kernel.context.ServiceRegistry` was already generic over any type ("ambient services every stage may need, resolved by type alone" — `docs/02-extension-model.md` §1); `weft_cli.cli.run_command` does `ctx.services.add(Dependencies, deps)` once, and every command reads it back with `ctx.require(Dependencies)` — no kernel change, no new field on `Context`, the identical mechanism `ctx.require(LLM)` already uses, applied to a fact 3.2 needed and no earlier task did · **tried, and reverted: running `Command.run` through `weft_kernel.seam.wrap`, `Prompt.render`'s own precedent.** It broke `manual/quickstart.md`'s `weft index` step: `weft_extract.accept.present_suffixes`/`discover_source_docs` are plain synchronous filesystem walks, always called directly by `run_index`, that ran unguarded under every pre-3.2 CLI handler — wrapping `Command.run` in the seam put them under the same blocking-call detector a *stage* answers to, and the detector correctly caught them. `Command` shares `Prompt`'s contract *shape* (not a `Stage`, `run` takes fresh args per call) but not its *content* (`Prompt.render` is pure templating; `weft-cli`'s own built-ins do real I/O as CLI orchestration, not as pipeline stages). Reverted rather than patched around: `run_command` calls `instance.run(args, ctx)` directly, with no span and no error attribution for a `Command` invocation — a real, named gap for whichever task next wants CLI-level observability, not a property this task claims. `docs/03-cli.md` was not changed to claim otherwise · **`weft --version` stays categorically pack-code-free (fitness function 8(b)), proven twice.** `weft_cli.cli.wants_version` is a throwaway `--version`-only `argparse.ArgumentParser` (`parse_known_args`, never the registry-driven one) that `main` checks before anything else. The first attempt at this task leaked anyway: `weft_cli.cli` imported `weft_cli.render` at module scope, which imports `weft_cli.commands`, which imports `weft_cli.ingest`/`ask` — themselves importing `weft_extract`/`weft_chunk`/`weft_embed`/`weft_store` at *their* module scope — so merely `import weft_cli.cli` pulled in all four pack modules regardless of `--version`. Caught by `tests/architecture/test_ff8_trust_model.py::test_version_command_executes_no_pack_code`, unweakened, still exercising the real `cli.main()` in a subprocess. Fixed by moving `weft_cli.render`'s import to `TYPE_CHECKING` at module scope and to two local imports (inside `run_command`, which is never reached for `--version`) — the identical local-import discipline `handle_index`/`handle_ask` already used for the same reason, now needed one layer further out · **checked for the reference's import-time-mutation scar, per the coordinator's addendum.** Neither `weft_cli.cli` nor `weft_cli.commands` reads an environment variable, opens a file, or touches the filesystem at module scope — every read (`weft.toml`, `WEFT_DATABASE_URL`) happens inside a function, called from `main()`. `weft-cli`'s `pyproject.toml` still declares exactly one `[project.scripts]` entry — no second `weft-*` console script, the reference's three-entry-point shape named as the one to avoid · **`weft_cli.permissions` and `CliCommand` are deleted, not left inert.** Nothing in the shipped code path constructed a `CliCommand` any more once `COMMANDS` was gone; `PermissionClass` is imported directly from `weft_command.permission` by its one real caller, `weft_cli.commands`. `tests/unit/weft_cli/test_permissions.py` (which tested the now-dead module) is deleted with it; every stale docstring reference (`weft_command/__init__.py`, `weft_command/permission.py`, `weft_command/contract.py`, `weft_cli/ask.py`, `weft_cli/registry_bootstrap.py`) is corrected in the same commit rather than left to say something false · **FF9(c)'s bill grew by one, and `examples/weft-example-command/` pays it.** `Command` had zero registrations before this task (3.1's own note: "no example pack was built... the obligation activates the moment something registers under it"); `weft-cli`'s five registrations activate it. The new example registers one plugin, `"greet"` (`GreetArgs(name: str)` → `GreetResult(greeting: str)`, `PermissionClass.READ`), proven against a real throwaway environment by the existing, unmodified `test_every_published_contract_has_a_stranger` (`_EXAMPLE_DIRS` reads `examples/`'s own directory listing, so nothing in that test needed to change) — this is also most of what Phase 3's exit (task 3.8) will need. `pyproject.toml`'s `[tool.pyright] extraPaths` gained its `src/` directory, the same repo-level tooling line every other example pays · **the contract reference regenerated, forced by live discovery, not by choice.** `tests/docs/test_generated_docs.py`'s `discover_for_reference()` is real discovery against this checkout; the moment `weft-cli` registered under `Command`, `manual/contract-reference.md` was stale (missing `Command`'s own section) and `KNOWN_WORKSPACE_DISTRIBUTIONS` was stale (missing `weft-cli`, so its five registrations read as environment contamination) — both fixed in this commit, regenerated with `uv run python scripts/generate_contract_reference.py`, zero manual edits to the generated file. **The user manual's command *table* — `docs/08-manuals.md` §3's "Generated" row for it — is not built here.** Task **3.9**'s own ledger line already bundles "the user manual's command table is generated" with "the contract reference covers `Command`"; the contract-reference half was forced by the existing floor tests above and could not be deferred, but the command-table generator itself is new machinery task 3.9 owns, and building it now would be pre-empting a task that has not been reached yet for a property nothing currently checks · **`manual/troubleshooting.md` gained two entries and one correction**, both forced by the existing coverage ratchet (`docs/08-manuals.md` §3 clause (d), task 0.14): `### \`CommandRefusalError\`` and `### \`UnsupportedArgumentTypeError\`` (a pack-author bug — a `Command.args_model` field type `weft_cli.argparse_gen` has no mapping for — exit `4`, since it breaks `weft --help` for every command, not only its own), reproduced against a real checkout and a real function call respectively; the `FlushError` entry's own prose, which named `handle_index` by a name that no longer exists, is corrected to name the real call path · **measured.** `weft-kernel`: **2,886 → 2,886 lines (+0)** — no file under `packages/weft-kernel` changed at all (`git diff --stat packages/weft-kernel` is empty), confirmed independently by `tests/architecture/test_ff3_kernel_budget.py`'s own count, unchanged. `uv run poe ci-checks` is green: **1,338 passed, 1 skipped, 76 architecture tests**. `uv run poe kernel-isolated` is green · **left to later tasks, named rather than silently covered**: the TTY refusal / `--yes` machinery for `overwrite`/`destroy` classes (3.3 — nothing here reads `permission_class` at dispatch time yet, only at registration); the REPL, session state, and the plural renderers `--json`'s newline-delimited sink and the REPL's own (3.4, 3.6 — `weft_cli.render.Rendered` is the shape a JSON renderer will also read, not a JSON renderer itself); token streaming through a resolved `TokenSink` (3.6); `init`/`pipeline …`/`config …` (3.7); an *automated* test proving an installed stranger's command appears in `weft --help` and in completion (3.8 — the mechanism is generic and already proven manually against `weft-example-command`, but no test in this commit drives `weft --help` against a real installed third-party pack); the user manual's generated command table (3.9, per its own ledger line above); CLI-level spans and error attribution for a `Command` invocation (no task currently owns this — named as a gap in `weft_cli.cli.run_command`'s own docstring rather than silently absent). · **Repaired, 2026-08-20, from a review of `4aeba88`.** The gap flagged above — no test drove `weft --help` against a real installed pack — hid a real defect this task itself introduced: `main`'s registry-driven `build_parser` gave `weft --help` a generated grammar to reach, but nothing routed a lone `-h`/`--help` to it — `prescan_command_name`, this task's own pre-scan for `_PIN_DIAGNOSTIC_COMMANDS`, strips every `-`-prefixed token while guessing a command name, so `argv = ["--help"]` read as no command at all and task 3.4's REPL-entry rule took it, `weft --help` printing the interactive banner instead of the generated help. `weft_cli.cli.wants_help(argv)` is the fix — `wants_version`'s own pre-scan shape, repeated, argv-only and discovery-free — read by `main` (task 3.4's own function) to keep `weft --help` out of the REPL once the registry-driven parser already exists; `prescan_command_name` itself is unchanged, since its own job (which command was named, for `strict_pins`) was never wrong. `docs/build-ledger.md`'s 3.4 and 3.8 entries carry the rest of this repair; `tests/unit/weft_cli/test_cli.py` gained `wants_help`'s own unit tests plus a `main`-level test proving the REPL branch is not reached for `--help`/`-h`. `uv run poe ci-checks` reconfirmed green: 79 architecture tests, 1,485 passed + 1 skipped. · **one repair, 2026-08-20, from a review of `dae55e7`.** Finding 2: `CommandRefusalError`'s two raise sites in `IndexCommand`/`AskCommand` caught `weft_cli.registry_bootstrap.require_plugin`'s answer and always raised the plain class above, whatever the underlying cause — including the branch where `weft_kernel.registry.UnknownPluginError` had already computed `valid_options`, every name actually registered for the contract asked (`weft_kernel/registry.py:221-237`). That field reached `require_plugin`'s own `_unresolved` only as `plain=str(exc)`, folded into a message string, and was discarded there — invisible to fitness function 12's family walk, which looks for a typed field, never text. History matters: before Phase 3 this path was a plain `(ExitCode, str)` return value with no typed field to lose at all; this task's own `Command`/`Outcome` unification is what turned the refusal into an exception and dropped the guarantee in the same motion — a real user path, `weft ask`/`weft index` naming an unresolvable `[services] embed`/`[services] store` or `--extract` plugin. Fixed at the source rather than patched at the raise site: `require_plugin` now returns `PluginRefusal | None` (a new frozen dataclass — `exit_code`, `message`, `valid_options: tuple[str, ...] | None`) instead of a bare `(ExitCode, str)` tuple, threading the caught `UnknownPluginError.valid_options` through `_unresolved`'s three branches. A new family member, `weft_cli.commands.UnresolvedPluginNameError(CommandRefusalError, UnresolvedNameError)`, carries it — keyword-only, no default, so a raise site that forgets `valid_options` cannot construct it — and a shared helper, `weft_cli.commands._raise_for_plugin_refusal`, is the one place `IndexCommand`/`AskCommand` decide between it and the plain `CommandRefusalError`, so the two commands cannot drift from each other on which branch gets the typed field. **Decided explicitly, not defaulted: which branch gets `valid_options`.** `_unresolved`'s three branches split cleanly on `docs/03-cli.md` → *Output*'s own policy/resolution line: the `refused` branch (exit `3`, `POLICY_REFUSED`) stays `PluginRefusal.valid_options = None` — a refused pack is never imported, so nothing here can honestly claim to know what it would have registered, and inventing a list would be worse than omitting one, the identical distinction task 3.3's own paragraph already drew for why its no-TTY refusal does not carry `valid_options` either (narrowed there in this repair's own paragraph on that task, not reversed). The `silent` (failed/partial packs) and `nothing amiss` branches — both exit `4`, `RESOLUTION_FAILED`, both genuinely "no pack provides this name" — both carry it; both exit codes are unchanged from before this repair, only the typed field moved. Test-first: `tests/unit/weft_cli/test_registry_bootstrap.py`'s four `require_plugin` tests were converted from tuple-unpack to attribute access and each now asserts `.valid_options` directly — `None` for the refused case, the real registered-name tuple for the other two — watched failing (`TypeError: cannot unpack non-iterable PluginRefusal object`) before the source changed. `tests/unit/weft_cli/test_commands.py` gained `test_ask_command_names_the_registered_embedders_for_an_unresolvable_name` (`UnresolvedPluginNameError`, `.valid_options == ("hash",)`, still `isinstance(..., CommandRefusalError)`) and an assertion on the existing refused-pack test that it is **not** that subclass, locking the boundary in both directions. Demonstrated on the real binary, not only in tests: a project `weft.toml` naming `[services] embed = "no-such-embedder"` with every pack otherwise active — `weft ask "what changed?"` prints `[services] embed names 'no-such-embedder', and no registered Embedder has that name. ... Names registered for Embedder: 'hash', 'openai'.`, exit `4` — and, catching the exception directly off the same real `AskCommand.run()` call: `type(exc).__name__ == 'UnresolvedPluginNameError'`, `isinstance(exc, CommandRefusalError) is True`, `exc.valid_options == ('hash', 'openai')` — the typed field, not only the message, now survives. `manual/troubleshooting.md` gained `### \`UnresolvedPluginNameError\`` (task 0.14's coverage ratchet, a real entry, no waiver), reproduced against this same transcript. `NAME_RESOLUTION_FAMILY` gained `weft_cli.commands.UnresolvedPluginNameError` in the same commit — 22 → 24 pinned members alongside finding 1's own addition (3.3's paragraph), both guarded by the existing discovery ratchet. **No kernel line** (`git diff --stat packages/weft-kernel` empty; 2,891 → 2,891). `uv run poe ci-checks` green after both findings' repairs together, one commit: **79 architecture tests, 1,493 passed, 1 skipped**. `uv run poe kernel-isolated` green. · **one repair, 2026-08-20, from a review of `65b8518`.** Open item O4 (`.phase3-design.md` §4), reproduced on the real binary against a `weft.toml` naming a store no pack provides: `weft ask "what changed?" --retrieve-only` printed `[services] store names 'pgvector', and no registered NodeStore has that name. These distributions contributed nothing, or only part of what they publish, and one of them may be the one that provides it: weft-store (failed: 'weft-store' settings failed validation: 1 validation error for PgVectorSettings\ndsn\n  Field required [type=missing, input_value={}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing). no 'pgvector' is registered for NodeStore. It is unavailable because no distribution has registered that name for this contract. Names registered for NodeStore: 'qdrant'.`, exit `4` — correct (FF12's structural guarantee held throughout; this was message *quality*, which G11 made FF12's own subject) but composed badly: `_unresolved`'s own `wanted` sentence and `weft_kernel.registry.UnknownPluginError`'s own text (`plain=str(exc)`) were joined with a bare space in all three branches, so a sentence began lowercase right after a full stop, a raw multi-line Pydantic validation dump (a `PackReport.reason`) was spliced into the middle of the "contributed nothing" sentence, and "nothing is registered under that name" was stated twice in different words — the kernel's own restatement after `_unresolved`'s identical claim. **Neither message was edited** — `weft_kernel.registry.UnknownPluginError.__init__` is untouched (kernel budget: 2,891 → 2,891, `git diff --stat packages/weft-kernel` empty), and `_unresolved`'s pre-existing `wanted` sentence, the `refused`/`silent` distribution listings and the exit-code split are all unchanged. **The join itself became explicit instead.** `_unresolved` no longer receives or quotes `str(exc)` at all; it keeps only `exc.valid_options` — the identical tuple `PluginRefusal.valid_options` already carries structurally — and states the one fact worth repeating as its own sentence, `_registered_names_sentence` (`"Registered {Contract} names: 'a', 'b'."`), composed rather than quoted. The doubled fact is removed by dropping the kernel's clause entirely in favour of this module's own, rather than trying to make the two say different things — they were never going to, since both name the same registered-name set. A `PackReport.reason` (the Pydantic dump) is genuinely useful and is kept in full, not hidden: `_diagnostic_detail` renders it as an indented block per distribution under a `Diagnostic detail:` header, joined to the summary sentence by a blank line (`_compose`, the one function deciding sentence-vs-block spacing) rather than parenthesised mid-sentence. The `refused` branch dropped its own trailing `{plain}` outright (no `valid_options` to summarise there either — a refused pack is never imported, `PluginRefusal`'s own pre-existing rule, unchanged) and gained the same `_registered_names_sentence`, stating what is *currently* active despite the refusal, which the old text never said at all. **Not a shared framework**: `_unresolved` is `require_plugin`'s only caller of this join, and `require_plugin` is confirmed (by search) to be the only place in `weft-cli` that concatenates a kernel `WeftError`'s own text onto a CLI-built sentence — `weft_cli.cli.run_command`'s `failure_reason = str(exc)` and `weft_cli.render`'s `str(exc)` calls each capture one already-complete message, never join two — so `_compose`/`_registered_names_sentence`/`_diagnostic_detail` stay private to `registry_bootstrap.py` rather than becoming a second, more general facility for one caller. Test-first: `tests/unit/weft_cli/test_registry_bootstrap.py::test_require_plugin_composes_its_own_message_rather_than_splicing_the_kernels`, watched failing on the pre-fix code (`re.search(r"\.\s+[a-z]", ...)` matched `". n"` — the exact lowercase-after-period tell) before the fix, now asserting no such match, the raw dump present but outside the summary sentence, and the kernel's own "is registered for" phrase absent from the composed text; every pre-existing `require_plugin` test (all four) still passes unedited, each already asserting only substrings (`"settings failed validation" in outcome.message`, `"'hash'" in outcome.message`), never the exact concatenated text, so none had locked in the defect. **A second, narrower gap found and named, not fixed here** — out of this repair's own scope, the composition site named in the finding: the default, routed `weft ask` (task 3.11) resolves `[services] store`/`[services] embed` inside `weft_cli.run_services.build_services`, which calls `Registry.entry` directly — that module's own docstring already states "this function does not repeat that translation" — so `require_plugin` is reachable only through `--retrieve-only` (Phase 0's own contract, `weft_cli.ask.run_ask`) or `weft index`, not through a default `weft ask` invocation; the finding's own reproduction command needed the flag to reach this repair's composition site at all, confirmed by running both forms against a real checkout. `manual/troubleshooting.md`'s `CommandRefusalError` and `UnresolvedPluginNameError` entries and `manual/operations-guide.md` → *A pin has to permit the pack behind every plugin name...* all quoted the old, defective concatenation verbatim (the latter two also, independently, `weft ask "what changed?"` with no `--retrieve-only`, silently non-reproducing since task 3.11 landed) — all three corrected in this commit, reproduced fresh against the real binary rather than hand-edited. `uv run poe ci-checks` green after the repair: **79 architecture tests, 1,513 passed, 1 skipped** (one new test). `uv run poe kernel-isolated` green.
- [x] **3.3** a destructive operation with no TTY fails naming the flag that would permit it, and never proceeds silently · owner `03` → *Permissions* · turns on — · sha `13008748869823611c19058c61c683a74f4d87a1` · **the check lives at the invocation seam, not a rule a command author remembers (design question 1).** `weft_cli.confirm.gate(instance, command_name, args, *, yes, policy)`, called from `weft_cli.cli.run_command` immediately before `instance.run(...)`, generalises the pattern `weft_cli.commands.IndexCommand`/`AskCommand` already use for `require_active`/`require_plugin` to *every* registered `Command`. It reads `permission_class` off the constructed instance with `getattr` (the identical defensive convention `_add_command_level` already uses for `help`) — no isinstance check, no cooperation from the plugin's own author required. Proven against a hand-registered, never-imported `destroy`-class command (`tests/unit/weft_cli/test_cli.py::_WipeCommand`, which declares nothing but `permission_class` and flips a `ClassVar` only if `run()` actually executed) rather than against a real first-party command, because none is `overwrite`/`destroy`-class yet — `weft index` upserts by content-addressed id, so nothing built in this repository reaches this path today; the demonstration is real, not hypothetical, but it is a test double by necessity · **no contract addition — the smaller, honest version, argued (design question 2).** `docs/03-cli.md` asks the prompt to state a collection name and a document count. A count means the command already looked, which the seam cannot do generically without either running part of the command early or a `Command.describe_impact`-style method every registered `Command` — built-in and stranger alike, since `required_declarations` has no "mandatory only for `overwrite`/`destroy`" mechanism without a kernel change this task's own budget forbids — would have to implement for a need nothing yet has. Shipped instead: the command's own registered name and its already-validated `args.model_dump()`, e.g. `'graph destroy' is a destroy-class command, called with {'collection': 'reports'}.` — genuinely more than "are you sure?", honestly less than a count. Left to whichever later task first ships a real `overwrite`/`destroy` command; `weft_cli.confirm`'s own module docstring and `.phase3-design.md` §4 carry the reasoning so it does not drift to Phase 4 by silence. `COMMAND_CONTRACT_VERSION` stays `"1.1.0"` — nothing about `Command` changed · **no TTY detected through a monkeypatchable seam, both branches proven in CI (design question 3).** `weft_cli.confirm.is_interactive`/`read_confirmation` each wrap one `sys.stdin.isatty()`/`input()` call in a module-level name for exactly one reason: `tests/unit/weft_cli/test_confirm.py` monkeypatches each directly, proving the no-TTY refusal, the TTY-confirmed path and the TTY-declined path without depending on whether the process running the suite is attached to a real terminal — which CI never is. `read_confirmation` also turns a mid-prompt `EOFError` into an empty string (treated as a decline), so a stdin that runs dry does not crash the process · **`[permissions]` in `weft.toml`, read from the same one-file parse (design question 4).** `weft_cli.permission_policy.PermissionPolicy` — two keys, `overwrite`/`destroy`, each `"ask"` (built-in default) or `"allow"` (an operator's standing override, equivalent to always passing `--yes` for that class) — parsed by `permission_policy_from_config` alongside `[services]`/`[llm]` in `weft_cli.registry_bootstrap.build_dependencies`, carried on `Dependencies.permissions`. An unknown key is refused naming `overwrite`/`destroy` as the keys that exist, the identical rule `service_selection_from_config` already applies to `[services]`. Scope stated rather than silently narrowed: `read`/`write` are unconditionally `allow` and are not keys here (nothing gates them), and `network` is a real, separate knob left out because no `network`-class command exists yet to exercise it — documented in `weft_cli.permission_policy`'s own module docstring rather than added ahead of the task that needs it · **`--yes`, on the leaf subparser only, not the top-level parser too.** `argparse`'s `_SubParsersAction` parses a subcommand's own remaining tokens into a *fresh* sub-namespace and copies every one of its attributes onto the shared namespace, unconditionally — a `--yes` declared on both levels would silently lose a `weft --yes <command> ...` spelling back to the leaf's own `False` default the moment that copy runs (caught by a failing test before it shipped, not read off `argparse`'s docs). One declaration, on `_add_command_level`'s leaf branch, and the convention it leaves — `weft <command> ... --yes`, after the subcommand — matches `apt-get install -y`/`npm install --yes` closer than a global-flag-first spelling would have · **exit code and refusal vehicle are unchanged.** The no-TTY refusal and a declined interactive prompt both raise the existing `weft_cli.commands.CommandRefusalError(message, exit_code=ExitCode.POLICY_REFUSED)` — no second exception type, no change to `weft_cli.render.render_refusal`. Exit `3`, per `docs/02-extension-model.md` §2 → *The trust model*'s policy/resolution split, restated in `docs/03-cli.md` → *Output* · **not FF12's family, and why.** `weft_cli.commands.CommandRefusalError` reports a policy decision about whether to proceed, never a name that failed to resolve against an enumerable set of alternatives — the flag it names is a flag, not a member of a name space `valid_options` could enumerate, the identical distinction `tests/architecture/test_ff12_unresolvable_name_carries_options.py`'s own module docstring draws for `weft_kernel.discovery.EnvInterpolationError` ("cannot enumerate 'valid' environment variable names") and `weft_kernel.registry.DuplicateRegistrationError` ("reports two names that both already resolved, never one that failed to"). `CommandRefusalError` does not gain `valid_options`, and `NAME_RESOLUTION_FAMILY` is unchanged · **the reference has nothing here.** A whole-tree search of `a prior project` for `typer.confirm`/`Confirm.ask`/any "are you sure" text returns zero matches, and its own most destructive command, `indexing/indexer.py`'s `rebuild --force` (`:791`, `:809`), runs immediately with no TTY check and no `--yes` equivalent — `.phase3-design.md` §2.5, verified at source. This module has no scar to avoid inheriting, only `docs/03-cli.md` to build from directly · **`docs/03-cli.md`, `manual/troubleshooting.md` and `weft.toml.example` edited in the same commit** — a narrowing blockquote under *Permissions* recording exactly what the prompt states today and what it does not, a `[permissions]` paragraph under *Project context*, `### \`CommandRefusalError\``'s entry extended with its second raise site (no new `WeftError` subclass, so the coverage ratchet in `tests/docs/test_troubleshooting_coverage.py` needed no new heading — both refusals reuse the existing class), and a documented, commented-out `[permissions]` block beside `[services]` · **measured.** `weft-kernel`: **2,886 → 2,886 lines (+0)** — `git diff --stat packages/weft-kernel` is empty. `uv run poe ci-checks` is green: **1,357 passed, 1 skipped, 76 architecture tests**. `uv run poe kernel-isolated` is green · **left to later tasks, named rather than silently covered**: a `Command.describe_impact`-style contract method for a real collection name and document count, once a real `overwrite`/`destroy` command exists to need it (no task currently owns this); a `[permissions]`/`network` key, once a `network`-class command exists; CLI-level spans and error attribution for a `Command` invocation (3.2's own gap, unchanged, `weft_cli.cli.run_command`'s docstring); the REPL's own confirmation UX and session-scoped `--yes` (3.4, 3.5). · **one repair, 2026-08-20, from a review of `f201e70`.** Running the shipped binary — `cd /tmp/empty && weft init` — found an article-agreement bug in the very message this task's own `gate` builds: `f"'{command_name}' is a {permission_class.value}-class command, called with ..."` reads "'init' is a overwrite-class command" for every `overwrite`-class refusal, unconditionally wrong, because `"a"` was hardcoded rather than agreeing with the class name that follows it. Fixed once at the source, not per call site: `weft_cli.confirm._article(word)` returns `"an"` when `word`'s own first letter is a vowel, `"a"` otherwise, and both f-strings in `gate` (the no-TTY raise and the interactive prompt) call it — `overwrite` now reads "is an overwrite-class command", `destroy` (already correct) is unchanged and covered by an explicit test so a third class cannot regress the rule silently in the other direction. Two new tests, `tests/unit/weft_cli/test_confirm.py::test_no_tty_refusal_uses_the_correct_article_for_overwrite`/`_for_destroy`, assert the exact phrase. **A second, related finding recorded here rather than silently absorbed into 3.7's own entry**: that same reproduction found `weft init` refusing outright in an empty, non-interactive directory — the first thing a new user or a CI job runs — because `init` was `overwrite`-class; task 3.7's own repair paragraph below reclassifies `init`/`pipeline derive`/`config set` to `write` and states the consequence for this task's machinery precisely: **no first-party command is `overwrite`/`destroy`-class**, so `gate`'s `_ASK_CLASSES` branch is now exercised only by `tests/unit/weft_cli/test_cli.py::_WipeCommand` and this task's own direct unit tests of `gate` — the "no task currently owns this" items above (a `describe_impact` count, in particular) stay exactly as unowned as before, since nothing changed about what `gate` itself decides, only the grammar of what it says and which commands ever reach it. `weft-kernel`: **2,891 → 2,891 lines (+0)** — `git diff --stat packages/weft-kernel` empty. `uv run poe ci-checks` reconfirmed green after the repair: **76 architecture tests, 1,476 passed, 1 skipped** (combined count for all three tasks' repairs, recorded once in 3.7's own paragraph rather than three times). · **second repair, 2026-08-20, from a review of `dae55e7`.** Finding 1: `weft_cli.permission_policy.permission_policy_from_config`'s unknown-`[permissions]`-key refusal (`:90-97` at review time) computed the valid keys and interpolated them into the message string only, never into a typed field — invisible to fitness function 12's family walk despite `weft_cli.config_surface.UnknownConfigKeyError` (task 3.7) already handling the near-identical "unknown TOML key" refusal correctly in the same phase. Fixed to match it: `UnknownPermissionKeyError(WeftError, UnresolvedNameError)`, `valid_options` keyword-only with no default, raised in place of the bare `WeftError`, `valid_options=tuple(sorted(PermissionPolicy.model_fields))` — `("destroy", "overwrite")` today. **The second, smaller instance the review also flagged — examined and excluded, with the reason, in 2.36's own style.** `permission_policy.py`'s "must be 'ask' or 'allow'" refusal (one function below the key check) and `weft_cli.config_surface.validate_set_value`'s identical-shape `permissions` branch (`:202-208`) both stay bare `WeftError`, not brought into the family: `PermissionAction` is a closed, two-member `StrEnum` fixed by the type itself, not a name resolved against a registry, a catalogue, or any document whose membership could ever differ — the identical category `test_ff12_unresolvable_name_carries_options.py`'s own module docstring already uses to exclude `weft_kernel.registry.DuplicateRegistrationError` ("two names that both already resolved") and `weft_kernel.discovery.EnvInterpolationError` ("no enumerable registry... to draw from"). A value-validation of a two-member enum is a type mismatch with a friendlier message; `PermissionPolicy.model_validate(written)`'s own `pydantic.ValidationError` would report the identical fact were the guard absent. Both raise sites now carry a comment stating this in place, so the exclusion is not silent. Test-first: `tests/unit/weft_cli/test_permission_policy.py::test_an_unknown_permissions_key_carries_the_known_keys_as_a_typed_field`, watched failing (`NameError: UnknownPermissionKeyError`) before the class existed. `NAME_RESOLUTION_FAMILY` gained `weft_cli.permission_policy.UnknownPermissionKeyError` in the same commit. Demonstrated on the real binary: a project `weft.toml` with `[permissions]\ndelete = "allow"` — `weft plugins list` refuses with the keys named, exit `4` (this fails during `build_dependencies`, before any `Command` is chosen, so `weft_cli.cli.main`'s fixed `RESOLUTION_FAILED` applies regardless of the raised `WeftError`'s own subclass, per that function's own docstring) — and, caught directly, `exc.valid_options == ('destroy', 'overwrite')`. `manual/troubleshooting.md` gained `### \`UnknownPermissionKeyError\`` beside `UnknownConfigKeyError`, stating the excluded boundary case explicitly rather than leaving a reader to wonder why the sibling check was not touched. **Finding 2, spanning this task, 3.2 and 3.7, is recorded in full in 3.2's own paragraph** — `CommandRefusalError`'s no-TTY raise site (this task's own) is unaffected, and this task's earlier claim that the class "does not gain `valid_options`" stays true of that raise site and of the base class itself; a new *sibling* class, `UnresolvedPluginNameError`, now carries the field for the one raise site that is genuinely a name resolution, which narrows this task's own argument rather than reversing it. `uv run poe ci-checks` green after both findings' repairs together, one commit — **79 architecture tests, 1,493 passed, 1 skipped** (see 3.2's paragraph). `uv run poe kernel-isolated` green.
- [x] **3.4** the interactive session and the one-shot invocation are the same commands with a different renderer, not two implementations · owner `03` → *Two modes, one implementation*; `05` → G8 · turns on — · sha `3240064` · **one new module, `weft_cli.repl`, adds a loop and nothing else — no second parser, no second dispatch path.** `weft` with empty `argv` (checked in `main`, after the `--version` pre-scan and after the same `build_dependencies`/`build_parser` discovery every other invocation needs — `weft --help` already pays that cost, so a bare `weft` paying it too is not a new exemption) reaches `weft_cli.repl.run_repl(deps, parser)`, which reads a line (`read_line`, its own monkeypatchable name on `weft_cli.confirm.read_confirmation`'s exact precedent), tokenises it with `shlex.split` and resolves it against the identical registry-driven `argparse.ArgumentParser` `--help` is generated from, then calls `weft_cli.cli.run_command` — the same function `main`'s one-shot path calls, unmodified, receiving no REPL-specific parameter. "Not two implementations" is provable rather than asserted: nothing in `run_command` or `build_parser` changed shape to accommodate a caller that did not exist before this task · **O1 (task 3.2's open item, `.phase3-design.md`) is resolved by parameterising the seam, not by a second attribution wrapper — the coordinator's steer, verified rather than taken on faith.** `weft_kernel.seam.wrap` gained `guard_blocking_calls: bool = True`; every pre-existing caller is unaffected, and `weft_cli.cli.run_command` is the one caller in the whole tree that passes `False`, restoring spans and four-field error attribution to a `Command` invocation (`entry.distribution` read off the registry, the identical field `weft_prompts.registry.PromptRegistry.render` already reads for the same reason) without reintroducing the blocking-call guard's false positive against `weft index`'s own synchronous filesystem walk — the exact failure task 3.2 hit and reverted. The rejected alternative, a CLI-local span/attribution wrapper, would have been a second implementation of a concern `weft_kernel.seam` already owns, free to drift from it — task 3.1's `destroys` → `required_declarations` generalisation is the nearest precedent for refusing that shape, accepted there on the identical evidence this change reproduces: every pre-existing test of the guard's default-`True` behaviour (`tests/unit/weft_kernel/test_seam.py::test_wrap_integrates_the_blocking_guard`) passed unedited. Checked at source, not assumed: `_strip_transient`/`_sanitize_control_bytes` both gate on `isinstance(value, Node | tuple | list)`; a `CommandResult` is none of those, so both concerns pass a `Command`'s result through untouched — a non-question for this contract, stated once here rather than left implicit. Two new kernel tests prove the resolution directly (a blocking `time.sleep(0)` runs to completion with the guard off; a bare `WeftError` still gets `pack`/`contract`/`plugin` filled in with the guard off) and two new `weft_cli` tests prove the wiring (`test_run_command_attributes_an_error_through_the_seam` intercepts `weft_cli.render.render_refusal` to inspect the exception `run_command` actually caught; `test_run_command_does_not_trip_the_blocking_guard` runs a `Command` that opens a real file from `run`). **O2, opened here for task 3.6**: O1's argument holds only while nothing else shares the loop with a `Command`'s run; once 3.6 ships streaming that has to interleave with the REPL's next prompt, `weft_extract.accept`'s walk and `repl.read_line`'s plain `input()` both stop being obviously harmless — recorded in `.phase3-design.md` §4 rather than solved here · **Three slash commands ship; five are named as deferred, not stubbed.** `docs/03-cli.md` → *In-session commands* lists eight. `/help` (reads the same `Registry.names_for(Command)` walk `--help` already does) and `/exit` ship because neither is *about* session state. `/plugins` ships as a slash **alias** for the already-registered `"plugins list"` `Command` — it calls `parser.parse_args(["plugins", "list"])`, the real grammar, and `run_command`, never a hand-rolled `args_model()` guess (an earlier draft did exactly that and pyright caught the type mismatch against `run_command`'s own `argparse.Namespace` parameter — fixed by reusing the parser, which is also the more honest "not two implementations" choice). `/clear`, `/pipeline`, `/trace` are named as task **3.5**'s (session state: conversation history, the active pipeline, the last run's trace — none of which exists yet, so a `/clear` that clears nothing or a `/pipeline` with nothing to switch would be exactly the drifted-surface failure this task exists to refuse elsewhere). `/config` is task **3.7**'s (`weft config get/set` is not registered). `/eval` has no owner: no `weft eval` command exists anywhere in the registry. Typing any of the five prints which task owns it, sourced from one `_DEFERRED_SLASH_COMMANDS` dict rather than five hand-written messages · **Completion — the mechanism, not task 3.8's proof.** `repl_completions(registry, prefix)` is a pure function (`sorted(name for name in registry.names_for(Command) if name.startswith(prefix))`) wired into a real session through `readline.set_completer`, `ImportError`-guarded for platforms without it. Task 3.8's own automated test calls this function directly; nothing here builds that test · **Tested without a terminal, per the task's own brief.** `weft_cli.confirm.read_confirmation`'s monkeypatch convention extended to the REPL: `tests/unit/weft_cli/test_repl.py` drives `run_repl` by monkeypatching `repl.read_line` with a scripted iterator (`EOFError` on exhaustion, matching Ctrl-D), captures stdout/stderr with `capsys`, and asserts on both. Twenty-one tests cover: a bare command dispatching through `run_command`; `/exit` and end-of-input both ending the session with `ExitCode.SUCCESS`; `/help` listing a registered command; `/plugins` both delegating (a real `"plugins list"` registration) and refusing honestly (none registered); each of the five deferred slash commands printing its own reason; an unknown `/bogus` naming itself unknown; a blank line being ignored; a bad-usage line (`argparse`'s own `SystemExit(2)`) being swallowed and the loop continuing, proven by a second scripted line still running afterward; an unparsable `shlex` line (unbalanced quote) being reported and the loop continuing; `KeyboardInterrupt` at an idle prompt re-prompting rather than ending the session; and — the test G6 exists for — a `CancelledError` raised from inside `run_command` while a command is actually running propagating out of `run_repl` **unswallowed**, proven by patching `repl.run_command` itself and asserting `pytest.raises(asyncio.CancelledError)` around the whole call, never a `try`/`except` inside the loop that would have caught it · **Interactive session exit code: always `SUCCESS` on a clean end, independent of the last command's own result.** A session is a shell, not a pipeline of one command — a script wanting a meaningful exit code already has the one-shot form, which G8 already settled is the thing a CI job scripts against. Stated explicitly in `weft_cli.repl`'s own module docstring and in `docs/03-cli.md`, rather than left for a reader to infer from the code · **The reference anti-pattern this task refuses, by name.** `.phase3-design.md` §2.4: `a_prior_project.output.reporter.Reporter` fuses formatting and printing in every method and is threaded as an injected `reporter: Reporter | None = None` collaborator into 24 files of domain code, `if self.reporter:` guards scattered through hundreds of lines — a printing object inside business logic, enforced by a rule an author must remember at every call site rather than by a seam. `weft_command.contract.Command.run` returning `Outcome[CommandResult]` and `weft_cli.render.render_outcome`/`render_refusal` being the only place anything is printed is the structural refusal of exactly that shape, task 3.2's own contribution that this task's REPL renderer inherits unchanged — this task added no new printing site to `weft_cli.repl` beyond `run_repl`'s own `print`/`print(..., file=sys.stderr)` calls, which read a `Rendered` a slash-command handler or `run_command` already computed, never format-and-print fused in one call. Two smaller reference scars named without repetition here (`.phase3-design.md` already carries the line numbers): `Reporter.warning`/`error` skipping the `QUIET` check every other method performs, and `OutputMode.VERBOSE` declared and never read — neither has a Weft analogue to avoid, since `weft_cli.render`/`weft_cli.repl` have no quiet-mode branch yet (task 3.6's). **The structural scar, cited as the task line asks:** `a_prior_project.generation.chat.py` has three Typer commands — `start` (interactive), `query` (one-shot), `unified` (interactive) — each rebuilding config and engine with near-duplicate error handling, and `query` duplicates `_run_chat_loop`'s own setup inline rather than reusing it. This task's whole point is refusing that: one `run_command`, one `build_parser`, called from two entry points that differ only in what surrounds them · **measured.** `weft-kernel`: **2,886 → 2,891 lines (+5)** — `guard_blocking_calls`'s parameter, its docstring paragraph (excluded from the count), and the two-line body change inside `_wrapped`; `git diff --stat packages/weft-kernel` shows only `seam.py` touched. Past the 2,800 review trigger (unchanged fact from 3.2/3.3), well under the 3,500 budget, and inside this task's own ~40-line stop condition by a wide margin. `uv run poe ci-checks` is green: **1,382 passed, 1 skipped, 76 architecture tests**. `uv run poe kernel-isolated` is green · **left to later tasks, named rather than silently covered**: `/clear`/`/pipeline`/`/trace` and real session state (3.5); `/config` (3.7); `/eval` (no owner yet); streaming through a resolved `TokenSink`, and `--json`/`--quiet` (3.6, which also inherits O2 above); the automated stranger-command completion test (3.8, this task's own `repl_completions` is what it will call); the user manual's generated command table (3.9); the degenerate-loop guard (3.10); `weft ask` routing by default (3.11). · **Repaired, 2026-08-20, from a review of `4aeba88`.** This task's own REPL-entry rule — `command_hint is None` — was one fact short: correct for a bare `weft` and for `weft --json`/`weft --quiet` (task 3.6's two flags, neither naming a command either), wrong for `weft --help`/`weft -h`, whose sole token `prescan_command_name` strips on the way to deciding a command name, exactly as it strips every other flag — so a lone help flag entered the session instead of ever reaching `build_parser`'s generated help, falsifying task 3.2's own drift-free claim and `docs/03-cli.md` → *Plugin-contributed commands*'s "They appear in `weft --help`" in the process. `main`'s routing test is now `command_hint is None and not weft_cli.cli.wants_help(argv)` — `wants_help` is new, `wants_version`'s own pre-scan shape; discovery is unaffected, since `build_dependencies`/`build_parser` already ran unconditionally before this check, both before and after. Once routed away from the REPL, `weft --help` falls through to the same `parser.parse_args(argv)` a named command already used — `argparse`'s own `-h`/`--help` action fires before the required-subparsers check, prints the registry-generated help and exits `0`, its own convention for a help request (distinct from `2`, its convention for a genuine usage error). `docs/03-cli.md` → *Two modes, one implementation*'s blockquote, which had stated the broken routing as deliberate ("no arguments at all, or only global flags such as `--json`/`--quiet` — enters the session"), is corrected in this commit to name `-h`/`--help` as the one flag that does not. Full argument in `weft_cli.cli.wants_help`'s and `main`'s own docstrings ("Repaired, 2026-08-20"); reproduced by hand before and after — bare `weft --help`/`weft -h` now print help and exit `0`; bare `weft` with stdin closed still enters the session and exits `0` on end-of-input; `weft --version` unaffected. `uv run poe ci-checks` green: 79 architecture tests, 1,485 passed + 1 skipped; `uv run poe kernel-isolated` green; zero kernel lines added, `BUDGET`/`REVIEW_TRIGGER` untouched.
- [x] **3.5** session state is explicit and inspectable, so the same command does not behave differently for two people · owner `03` → *In-session commands* · turns on — · sha `0e109a5` · **two of `03`'s four are built, two are deferred and argued — `weft_cli.session`, a new module, is the whole data half.** `SessionState` (frozen, `active_pipeline: str | None`, `last_trace: TurnTrace | None`) is replaced wholesale each turn (`with_active_pipeline`, `with_turn_recorded`, `cleared`, each `base.model_copy(update=...)` — the idiom this codebase already uses for `PermissionPolicy`/`ServiceSelection`, applied here to a value that changes turn to turn rather than once per run), never mutated in place; `weft_cli.repl.run_repl` holds exactly one local `state` variable, reassigned. `active_pipeline` is a bare, unvalidated name — `docs/03-cli.md`'s own task brief sanctions holding and printing it with no `pipeline` command surface to validate against (task **3.7**'s own) — set by `/pipeline <name>`, shown by `/pipeline` alone. `last_trace` is one `TurnTrace` (`command_name`, the verbatim `line` typed, `exit_code`), replaced — never appended — on every line that actually reaches `weft_cli.cli.run_command`: a bare command, or `/plugins`' own alias for `"plugins list"`; a slash command that only inspects or changes the session itself does not count as a run. `/trace` prints it or says plainly nothing has run yet; `/clear` (`weft_cli.session.cleared`) resets both to a blank `SessionState` · **the `/config` collision, resolved: the session gets its own command, `/session`, and `docs/03-cli.md` is corrected in the same commit.** `03` named `/config` as the command that prints session state, written before task 3.4 deferred `/config` itself to task 3.7's *project* configuration surface (`weft config get/set`, `weft.toml`) — two different questions sharing one name by accident of when each sentence was written: `weft.toml` is read once at startup, a session's own state changes every turn. Folding both into `/config` now would mean building part of 3.7's command surface early, just to have a project value to distinguish the session's from, or shipping `/config` half-true under a name `03` already promised project configuration to — neither honest. `/session` (not one of `03`'s original eight) prints every value `SessionState` carries and nothing else — `active_pipeline`, the last `TurnTrace`, and an explicit line naming conversation history as untracked, rather than a value silently missing from the printout, which is this task's own bar for "nothing the session applies is implicit" applied to itself. `_DEFERRED_SLASH_COMMANDS` in `weft_cli.repl` shrinks from five entries to two (`config`, now redirecting to `/session`; `eval`, still no owner) · **conversation history and the collection — `03`'s other two — are deferred, argued rather than shipped as decoration.** `weft_cli.commands.AskArgs`/`RouteArgs` take no history field, and neither `weft_llm.contract.LLMProvider` nor `weft_prompts` accepts one from a CLI caller today, so a transcript this module accumulated for display only, with nothing downstream ever reading it back into a run, would be the reference's own failure restated rather than avoided: `.phase3-design.md` §2.5, verified at source — `_run_chat_loop` (`generation/chat.py:353`) passes `chat_history=[]` on every turn, a comment on the same line stating it is stateless, a REPL that presents as a chat session and holds none. Building a history nothing reads back would be the identical defect the other way round: state that *looks* held and consulted and is not. The collection is deferred for a sharper reason — no command in this repository accepts a collection argument at all (`IndexArgs`/`AskArgs` name none; `[services] store` selects which store *plugin* runs, never which named collection inside it), so there is not even a command to hold a session's choice *for* yet. Both arguments are `weft_cli.session`'s own module docstring, not asserted here alone · **no contract change, no kernel line.** Every field this task added lives in a new module, `weft_cli.session`, wired into the existing `weft_cli.repl` loop — `Command`, `weft_command`, and the example pack are untouched, `run_command`'s own signature is untouched, and `git diff --stat packages/weft-kernel` is empty · **tested without a terminal, on the established convention.** `tests/unit/weft_cli/test_session.py` (6 tests: the model's own defaults, the replace-wholesale idiom proven directly against the *original* instance, an overwrite-not-accumulate edge case, `cleared`'s full reset, and an `extra="forbid"` rejection) covers the data half in isolation; `tests/unit/weft_cli/test_repl.py` gained 6 more (pipeline show/set round trip, trace before/after a real run, `/plugins`' own alias updating the trace exactly as a bare command would, `/clear` resetting both, `/session` printing them together) and the existing deferred-slash-command test's parametrization shrank from five names to two (`config`, `eval`) rather than being duplicated · **measured.** `weft-kernel`: **2,891 → 2,891 lines (+0)** — CLI work, as the task line's own owner (`03`) predicts. `uv run poe ci-checks` is green: **1,391 passed, 1 skipped, 76 architecture tests**. `uv run poe kernel-isolated` is green · **`docs/03-cli.md` edited in the same commit**: the *In-session commands* command-list block (`/config` → `/session`, `/trace`'s own description corrected from an aspirational "stages and timings" — never built — to what actually ships, "the last command this session ran"), the prose sentence naming which command prints session state, and a new blockquote recording this task's build and the `/config` resolution in full, beside — not replacing — task 3.4's own · **left to later tasks, named rather than silently covered**: conversation history, once `ask`/`route` (or their prompts) gain something to read it back into (no task currently owns this); the collection, once a command exists to hold one for (no task currently owns this either); `/config` itself (3.7); `/eval` (no owner yet); the top-level `weft trace [<run-id>]` command `03` -> *Command surface* names, a fuller stage-level replay this task's own `/trace` is deliberately lighter than (no task currently owns this).
- [x] **3.6** tokens reach a reader as they arrive, through a resolved service rather than a second set of contracts · owner `01` → *Colour*, the streaming consequence; `02` §1 · turns on — · sha `81c4626` · **the gap was exactly what the task line named: the mechanism, not the seam.** `weft_llm.contract.TokenSink`/`weft_llm.client.LLMClient.complete` shipped in Phase 2 and already emit every chunk into `ctx.require(TokenSink)` as it arrives; `weft_cli.run_services.build_services` hardcoded `NullSink()` regardless of caller intent. This task built the three real sinks and the wiring from a global flag to a resolved instance — no change to `TokenSink`, `LLMProvider` or `LLM`, and no second contract, which is G6's own refusal (*"streaming is a `TokenSink` service, not a second contract"*) held rather than reopened · **`weft_cli.sinks` — a new module, three names.** `PrintingSink` (the new default): `self._stream.write(chunk.text)` then `flush()` on every visible chunk, no trailing newline between chunks (that is what makes a terminal show one growing line), one newline on `close()` if anything was written, and a visually distinct `[stream error: ...]` line when `close(reason=...)` names one — a human reading a scrollback cannot mistake a broken stream for a finished one, either. `JsonSink` (`--json`): one `StreamEvent` (`type`, `role`, `text`, `message` — the reference's one-envelope shape, `.phase3-design.md` §2.3, rebuilt fresh) per `write` call, newline-delimited. `--quiet` reuses `weft_llm.client.NullSink` unchanged — a sink that discards is already what quiet needs, so no second do-nothing class was built. Both real sinks share one filtering rule, `_visible`, applied against `display_roles` (default `frozenset({"generate"})`, `weft_llm.payload.TokenChunk`'s own documented default) rather than duplicated per class · **the event vocabulary is three members, not the reference's seven, and each absent one is named rather than silently dropped.** `core/engine/types.py:85-96`'s `StreamEventType` — `TOKEN`, `CITATIONS`, `SOURCES`, `STATUS`, `DONE`, `ERROR`, `GUARDRAIL_WARNING` — is real knowledge (`.phase3-design.md` §2.3): one envelope, whichever fields the type needs, `STATUS` interleaving with token events, a terminal `DONE`/`ERROR` closing the stream. Weft ships `CHUNK` (renamed from the reference's `TOKEN` — Weft already has a type called `TokenChunk`, and a member literally named `TOKEN` reads, to ruff's own `S105` hardcoded-password heuristic and to a human, like a credential rather than a piece of a streamed answer; fixed by renaming rather than suppressing the check, since CLAUDE.md's "catch specific exceptions" spirit extends to "fix what a check is actually catching" over silencing it), `DONE` and `ERROR`. `CITATIONS`/`SOURCES` would need `weft_generate.payload.Answer.citations` threaded into something that today only ever sees a `TokenChunk`; `STATUS` would need a routing-progress signal nothing in `weft-retrieve` emits; `GUARDRAIL_WARNING` has no guardrail plugin anywhere in this tree — three real gaps for whoever builds the thing that would emit them, the identical discipline `weft_llm.payload.OnFailure`'s own docstring states for itself · **an error can never be mistaken for a clean end — the reference correction (`.phase3-design.md` §2.3(b)) this task exists not to reproduce.** The reference's generator catches an exception, logs it, and yields a plain `ERROR` event a consumer that does not branch on `type` cannot tell from a normal end. `TokenSink.close`'s own `reason: str | None` is the mechanism that keeps the two structurally distinct here: `close(reason=None)` is the only call `JsonSink` turns into a `DONE` event; any other `reason` becomes an `ERROR` event carrying it, never a worded difference a consumer would have to string-match. `weft_cli.cli.run_command` is where that decision is made — the seam-adjacent function that already centralises `WeftError` handling and exit-code translation, not a rule every streaming `Command` author has to remember (CLAUDE.md: cross-cutting concerns live at the seam) — closing `deps.token_sink` exactly once on every one of its three exits: success (`reason=None`), a caught `WeftError` (`reason=str(exc)`), or anything else escaping uncaught, `CancelledError` included (`reason="command did not complete"`, since this function genuinely does not know the cause). The close lives in a `finally`, which does not catch the exception — G6's own rule ("`CancelledError` propagates and is never swallowed") holds by the same construction `weft_kernel.seam.wrap`'s own module docstring already uses for itself: nothing here matches `except CancelledError` or `except BaseException`, so there is no clause for it to be caught by, and `finally` running cleanup on the way out is ordinary asyncio practice, not a second exception replacing the first — proven directly by `test_run_command_closes_the_token_sink_and_still_propagates_cancellation`, which asserts both `pytest.raises(asyncio.CancelledError)` *and* `sink.closed_with == ["command did not complete"]` from the same call · **"as they arrive" is proven as a timing property, per the task's own bar, not a finished-text check a buffering sink would also pass.** `tests/unit/weft_cli/test_sinks.py`'s two timing tests drive the real `weft_llm.client.LLMClient.complete` against a fake `LLMProvider` that `await asyncio.sleep(0.05)`s between three yielded words, through a `stream: io.StringIO` subclass that records `time.monotonic()` on every `write` call, and assert every consecutive gap is at least 60% of the sleep — a sink that buffered every chunk and wrote once in `close()` cannot produce more than one timestamp with no gap between it and nothing. Verified directly, not merely argued: a hand-written buffering `TokenSink` run against the identical fake provider produces exactly one `write` call and an empty gap list — precisely what the timing assertions refuse. `tests/unit/weft_cli/test_route_ask.py::test_run_routed_ask_streams_generation_tokens_into_the_caller_s_sink` extends the same proof one layer out, end to end through the real `route.yaml`/`no-retrieval.yaml`/`CitedAnswer` pipeline machinery already in that file: the `generate`-role chunks a recording sink observed, rejoined in arrival order, equal `Answer.text` exactly, and the sink's own `closed_with` stays empty — proof `run_routed_ask` never closes a sink it was only lent, leaving that to `run_command` alone · **O2 (task 3.4's own follow-on, `.phase3-design.md` §4) — resolved with evidence, not closed by silence.** The question: does a token now arrive while something else blocks the loop, now that the REPL keeps reading a next line on the same loop a stream runs on? Read off `weft_cli.repl.run_repl`'s own code: the loop body is `read_line()` — a plain, synchronous `input()`, never `asyncio.to_thread`-offloaded — then, only once that returns a line, `rendered = await run_command(...)`, a single await that does not return until the whole command, including any token stream inside it, has finished; `read_line()` is not called again until that await completes. Nothing in this tree ever schedules a second coroutine against the same loop while one is running — `docs/01-high-level-plan.md` → *Colour*: "the runner keeps one batch in flight per pipeline run," and fitness function 7(a) keeps `asyncio.run` to exactly one call site in the whole tree. So the answer is **no**, and not by accident of today's fixture set: `weft_extract.accept`'s synchronous filesystem walk and a token stream can never be the same `Command.run` call, and no two `Command.run` calls ever overlap on this loop, REPL or one-shot. Proven rather than merely read: `tests/unit/weft_cli/test_repl.py::test_repl_does_not_read_the_next_line_while_a_stream_is_in_flight` monkeypatches `read_line` to set a flag the instant it is called while a scripted `run_command` (`await asyncio.sleep(0.02)`, standing in for a stream in flight) has itself set a `streaming` flag — the test fails the moment `read_line` is ever invoked during that window. **Named explicitly, not left implicit: what would make this break.** A future task that lets the REPL do anything else while a stream is in flight — `asyncio.create_task`-ing the stream so the loop can poll for `Ctrl-C` or accept a next line concurrently, a "type ahead while the model answers" queue — would reopen this question; nothing built here does either. Neither `weft_extract.accept`'s walk nor `read_line`'s plain `input()` needed to become async, and that conclusion did not cascade beyond `weft-cli` — consistent with the stop condition this task was given, which never fired · **the REPL-entry condition changed, forced by making `--json`/`--quiet` actually reachable from a bare invocation.** `weft_cli.cli.main`'s own pre-scan, `global_output_flags` (`wants_version`'s exact `parse_known_args` pattern, mutually exclusive `--json`/`--quiet`), has to decide the sink *before* `build_dependencies` runs, since the choice is carried on `Dependencies.token_sink` rather than read back out of `argparse.Namespace` afterward — and it has to work for the REPL branch too, which never calls `parser.parse_args(argv)` at all. Under task 3.4's own `not argv` REPL-entry test, `weft --json` (flags, no subcommand) never reached that branch: `argv = ["--json"]` is not empty, so it fell through to the one-shot dispatch parse and failed with `argparse`'s own `add_subparsers(required=True)` usage error. Corrected to `command_hint is None` — `prescan_command_name` already strips every `-`-prefixed token before deciding whether a command was named, so this is the same test 3.4 wrote, saying what it always meant: a bare `weft` and a flags-only `weft --json`/`weft --quiet` are both "no command", and both now enter the session with the sink already selected. No test asserted the old, narrower behaviour (checked before changing it); `docs/03-cli.md` → *Two modes, one implementation* is corrected in the same commit · **`--json`/`--quiet` are declared twice, deliberately, on `--version`'s own precedent.** Once on `global_output_flags`'s throwaway mini-parser (so a bare `weft --json` — argv the real, registry-driven parser never even sees — still selects the right sink), once on `build_parser`'s real top-level parser (so a one-shot `weft --json ask ...`'s dispatch parse recognises the token instead of failing "unrecognized arguments", and so `weft --help` documents it). Declared **before** the subcommand only — the opposite side from `--yes` (`weft <command> ... --yes`) — and for the opposite reason: `--yes` sits on the leaf because `argparse`'s `_SubParsersAction` would silently overwrite a same-named top-level flag with the leaf's own default; `--json`/`--quiet` are genuinely top-level-only, never a per-command choice, so no leaf declares them and the overwrite trap does not apply · **`build_services` gained a required `sink: TokenSink` parameter, no default.** `weft_cli.route_ask.run_routed_ask` gained one too, threaded straight through; `weft_cli.commands.RouteCommand.run` — the only built-in that streams today — reads `deps.token_sink` and passes it down. No default on `build_services`'s own parameter, deliberately: "never absent" is the sink's own promise, not licence for the assembler to guess one on a caller's behalf, the identical reasoning `services.store`/`services.embed` already get no default here. `test_build_services_registers_exactly_the_sink_the_caller_chose` and `test_route_command_passes_the_run_s_own_token_sink` each prove the caller's own instance is what a stage resolves — `is`, not `isinstance` — so a passing test could not be satisfied by a coincidental second `NullSink()` · **measured.** `weft-kernel`: **2,891 → 2,891 lines (+0)** — `git diff --stat packages/weft-kernel` is empty; this task never opened a kernel file. `uv run poe ci-checks` is green: **1,414 passed, 1 skipped, 76 architecture tests** (from 3.5's 1,391 — 23 new tests: 8 in `test_sinks.py`, the rest split across `test_cli.py`, `test_repl.py`, `test_commands.py` and `test_route_ask.py`). `uv run poe kernel-isolated` is green · **`docs/03-cli.md` edited in the same commit**: a new blockquote under *Output* carrying the sink choice, the flag placement, the event vocabulary and the error/clean-end distinction; *Two modes, one implementation*'s own task-3.4 blockquote corrected for the REPL-entry condition change. `docs/README.md`'s Status block carries the same evidence, condensed · **left to later tasks, named rather than silently covered**: the degenerate-loop guard (3.10) composes with `PrintingSink`/`JsonSink` at the point a repeated tail is detected — the natural attachment point is inside `LLMClient.complete`'s own accumulation loop in `weft_llm.client` (it already holds the full accumulated text per chunk, which is what the guard's own cumulative-text contract needs, `.phase3-design.md` §2.2), stopping the `async for` early rather than either sink learning what a loop looks like; `init`/`pipeline …`/`config …` (3.7, unstarted); the stranger-command completion test (3.8); the generated manual command table (3.9); `weft ask` routing by default (3.11) — until then `weft route`'s own live-stream-then-repeat-the-answer-in-full double print (`weft_cli.render._render_route` prints `Answer.text` again after `PrintingSink` already streamed it) is a real, named UX rough edge, not fixed here: `_render_route`'s output is 3.2's own byte-for-byte-tested contract, and resolving the duplication would mean deciding what a renderer is allowed to know about which sink ran, which is `weft ask`'s own unification (3.11) to make, not this task's to pre-empt. · **one repair, 2026-08-20, from a review of `f201e70`.** Running `weft init` in a genuinely empty directory with no TTY (exit `3`, correctly refused, no file written) printed the refusal **twice** — once correctly, via `render_refusal`'s `rendered.stderr`, and once more by this task's own `PrintingSink.close(reason=...)`, wrongly labelled `[stream error: 'init' is a overwrite-class command, ...]`. The root cause was `run_command`'s `finally` block: it closed `deps.token_sink` with `close_reason or "command did not complete"` on *any* non-success exit, with no check for whether the run had actually streamed anything — so `weft_cli.confirm.gate`'s refusal (raised before `instance.run` is ever called) was indistinguishable, to the sink, from a stream genuinely breaking mid-flight. A permission refusal is not a stream error; the command never streamed a token. Re-running the reproduction *by hand*, exactly as this review specifies, is what proved a fix scoped only to `gate`'s own refusal path would have been incomplete: running `weft init` a second time (`weft.toml` now present, refused by task 3.7's new `TargetAlreadyExistsError`, raised from *inside* `InitCommand.run` rather than from `gate`) printed the identical double — the bug is general to "closed with a reason when nothing was ever emitted", not specific to the permission-refusal call site. The fix, `weft_cli.cli._EmissionTrackingSink`: wraps `deps.token_sink` for the duration of one `sealed_run` call, tracks whether `TokenSink.emit` was ever actually invoked, and `finally` now passes a real `reason` only when `.emitted` is `True` — the real sink (never the wrapper) is still closed exactly once, on every exit, unchanged. No `weft_llm.contract.TokenSink` change: the wrapper satisfies the Protocol structurally, the identical footing `PrintingSink`/`JsonSink` already stand on. **Two pre-existing tests asserted the bug's own behaviour and were corrected, not merely accommodated**: `test_run_command_closes_the_token_sink_with_the_weft_error_s_own_reason` (renamed `..._with_none_when_nothing_streamed`) and `test_run_command_closes_the_token_sink_and_still_propagates_cancellation` both drove a command that raises without ever touching the sink and asserted the error's own text/`"command did not complete"` as `reason` — now `None`, per the corrected rule, each with the old assertion recorded in the test's own docstring as what changed and why. Two new positive-case tests, `test_run_command_attributes_a_genuine_mid_stream_failure` and `test_run_command_uses_the_generic_reason_on_mid_stream_cancellation`, drive a command (`_StreamingBoomCommand`/`_StreamingCancellingCommand`) that emits a real chunk before failing, proving the rule still attributes a *genuine* stream failure and is not merely "always `None`". The complete-output regression this review asked for: `test_run_command_does_not_double_print_a_gate_refusal` runs a refused `destroy`-class command against a real `PrintingSink` bound to a captured `io.StringIO`, and asserts the stream captured nothing at all — not merely that the exit code is `3`. **Explicitly out of scope, stated rather than silently half-fixed**: `weft_cli.commands.RouteCommand`'s own double-print of a *successful* streamed answer (`_render_route` re-prints `Answer.text` after `PrintingSink` already streamed it, flagged in this task's own entry above) is untouched — it lives entirely in the `succeeded=True` branch, which this repair's `reason` logic forces to `None` before and after, and remains task **3.11**'s to fix. `weft-kernel`: **2,891 → 2,891 lines (+0)** — `git diff --stat packages/weft-kernel` empty. `uv run poe ci-checks` reconfirmed green after all three tasks' repairs: **76 architecture tests, 1,476 passed, 1 skipped** (`uv run poe kernel-isolated` green too) — the manual reproduction re-run by hand, both with and without an existing `weft.toml`, is recorded in task 3.7's own repair paragraph, where the permission-class change that changes its outcome lives.
- [x] **3.7** the rest of the command surface exists — `init`, `pipeline list|show|derive|validate|diff`, `config get|set` — and `pipeline diff` is an exact comparison because resolution is fully explicit · owner `03` → *Command surface* · turns on — · sha `c951f49` · **eight commands, three new modules, one dispatch path.** `weft_cli.pipeline_commands` (`pipeline list|show|derive|validate|diff`), `weft_cli.config_commands` (`config get|set`) and `InitCommand` in `weft_cli.commands` are registered exactly like every earlier command, through `weft_cli.commands.register`'s one entry point — `register_pipeline_commands`/`register_config_commands` are called from there, never a second `[project.entry-points."weft.packs"]` line and never a hand-coded pre-scan bypassing `weft_cli.cli.build_parser` · **`weft pipeline diff` proves its exactness rather than asserting it — a new module, `weft_cli.pipeline_diff`.** `diff_resolved(a, b)` compares two `weft_kernel.resolution.ResolvedPipeline` values structurally: stages matched by **id**, never position (an inserted stage reads as one addition, not a shift of everything after it), a stage present on both sides compared by `==` — the identical equality that model's own docstring already promises across two separate `resolve()` calls — and never a rendered string anywhere in the comparison. `docs/03-cli.md`'s own words: a text diff would be "a guess about a guess," two renderers' opinions rather than the fact itself. `tests/unit/weft_cli/test_pipeline_diff.py` (5 tests, no YAML, no registry) proves it directly: two separate resolutions of one pipeline diff to `identical=True`; a derived pipeline that inserts one stage (`02` §3's own `specific.yaml` example) diffs to exactly that one addition and nothing else; a same-id stage with a different plugin is reported as **changed**, never as a spurious remove-plus-add pair · **`weft pipeline show` prints what a pre-G2 `show` structurally could not.** `PipelineShowCommandResult.resolved` carries the `ResolvedPipeline` itself, unwrapped — every stage's provenance, distribution, `applies_to`, final `with:` config, and `unapplied_operators`/`unplaced_contributions`, printed even though both are honestly empty in every case this task can produce: nothing in this tree wires an installed pack's slot contribution into a `resolve()` call yet — a grep of `packages/` finds no `PackRegistrar.add_contribution`-shaped method and no live caller of `weft_kernel.resolution.Contribution` outside that module's own tests. That gap is named in `weft_cli.pipeline_commands`'s own module docstring rather than built ahead of need; what this task ships is the print path, so the day a pack finally supplies one, `weft pipeline show` needs no CLI-side change to make it visible · **`weft pipeline derive` scaffolds the smallest legal derived pipeline and stops.** `name:` and `extends:`, nothing else — `Pipeline._extends_and_stages_are_mutually_exclusive_with_operators` accepts an empty operator set, so this is already a complete, valid document. Generating `insert`/`replace`/`remove`/`set` blocks from CLI flags was rejected: `weft_cli.argparse_gen`'s own floor (`str`, `int`, `bool`, `StrEnum`, `| None` wrapping one of those) has no honest way to express four different operator shapes, and an author edits the file by hand from here — `weft pipeline validate <name>` is the natural next command, named in `derive`'s own render output · **a real, project-wide catalogue, closing a gap task 2.8 named and narrowed.** `weft_cli.pipeline_catalogue.full_catalogue` is the first caller anywhere in this tree that merges `load_pipeline_catalogue`'s project-local documents with `load_contributed`'s pack contributions — `ContributedPipelineNameCollisionError`'s own docstring named this as `.phase2-design.md` §5's wider, undelivered guarantee since 2.8. A name both sources declare is refused (`ProjectPipelineNameCollisionError`, new — a pack shipping a whole pipeline under a project's own name is the identical silent-override shape `02` §3 → *Slots* already refuses for a stage-level contribution, one level up), never silently arbitrated by picking a winner. `weft_cli.pipeline_catalogue.UnknownPipelineNameError` — also new, FF12's family, reusing `weft_kernel.runner.UnresolvedNameInPipelineResolutionError`'s shared `__init__` rather than a fifth hand-written copy of it — is what `show`/`validate`/`diff`/`derive` all raise for a name the catalogue does not hold, naming every name it does · **`--origin` answers from the raw parsed document, never from comparing a merged value against its own default — the reference's sentinel bug, avoided rather than reproduced.** `.phase3-design.md` §2.6, verified at source: `a_prior_project`'s `ConfigMerger` compares against a sentinel (`cli_overrides.get('embedding_provider', 'local')` then `== 'local'`, `merger.py:42-44`), so an explicit `--embedding-provider local` is indistinguishable from never having passed the flag, and can never override a config file naming something else. `weft_cli.config_surface.effective_config` reads `weft_cli.registry_bootstrap.document_at` (public since this task, for exactly this second reader) — the **raw** mapping, not `weft_cli.services.service_selection_from_config`/`weft_cli.permission_policy.permission_policy_from_config`'s own already-merged output — and asks, per key, whether it is literally present in the file, independent of its value. `services.embed = "hash"` written explicitly reports `origin: file` even though `"hash"` is also the built-in default (`test_a_value_explicitly_set_to_the_default_is_still_origin_file`); a `weft.toml` that never mentions `embed` reports `origin: default` — the exact distinction a sentinel comparison structurally cannot make · **`CONFIG_KEYS` is four dotted keys, the whole of what `weft.toml` a command actually reads today.** `services.embed`, `services.store`, `permissions.overwrite`, `permissions.destroy` — an unknown key is refused by `UnknownConfigKeyError` (new, FF12's family, a minimal custom `__init__` since `weft_cli.config_surface`'s own failure has no pipeline/stage/distribution to name), naming these four, per `docs/03-cli.md`'s own "a key the CLI does not yet read is refused" rule applied to the `config` command's own vocabulary rather than to `[services]`/`[permissions]` themselves · **`weft config set` edits `weft.toml` as text, never as a re-serialised document.** `tomllib` is read-only and no TOML writer is a dependency `weft-cli` carries; a parse-mutate-write round trip would discard every comment a real `weft.toml` holds (`weft.toml.example`'s own extensive prose, for one). `set_config_text` performs the smallest edit that makes one key say what was asked — replace an existing `key = "..."` line in place, insert one directly under an existing `[section]` header, or append a fresh section at the end of the file — matched against each line's own stripped text, so a commented-out example (`# embed = "openai"`) is never mistaken for the real key. `tests/unit/weft_cli/test_config_surface.py` proves a comment survives a `set` call untouched and the written value round-trips through a real `tomllib.loads` afterward · **`init`, `pipeline derive` and `config set` are `overwrite`-class — the first three first-party commands anywhere in this repository to be one.** Task 3.3's no-TTY refusal and `--yes` machinery has only ever been proven against a hand-registered test double (`tests/unit/weft_cli/test_cli.py::_WipeCommand`) because "none is `overwrite`/`destroy`-class yet" (3.3's own ledger entry). The line drawn: `weft index` upserts a store entry by content-addressed id — safely, no data lost — and stays `write`; these three are plain file writes with no such guarantee, so the previous `weft.toml`, pipeline document or config value is simply gone once one runs. `docs/03-cli.md` → *Permissions* is corrected in the same commit to record this as the machinery's first genuine exercise · **the single-dispatch-path decision, and the doc it corrects.** Every one of the eight commands needs the full registry — `full_catalogue`/`weft_kernel.resolution.resolve` cannot answer without one — and since task 3.2 unified command dispatch behind one registry-driven parser, building a parser that can even *recognise* `weft init` or `weft config get` as valid subcommands already requires the same `build_dependencies()`/`discover()` every other command pays, regardless of whether that command's own body reads anything discovery found. `docs/02-extension-model.md` §2's "`weft init`/`weft config get` complete with zero pack code executed" predates that unification and is corrected in this commit — `weft --version` remains the **one** categorically pack-code-free command, unweakened, still proven by the same subprocess test FF8(b) has carried since Phase 0. The rejected alternative — a third, hand-coded pre-scan for `init`/`config get` on `wants_version`'s own precedent — was refused as exactly the "second dispatch path" this task's own brief forbids, and it would also have had to duplicate two commands' own argument grammars by hand, the "no hand-written table" rule applied to itself · **`weft_cli.argparse_gen` gained `bool` support, for `--origin`.** A `False`-defaulting `bool` field becomes an `action="store_true"` flag; a required `bool` or a `True`-defaulting one is refused loudly rather than guessed at — the identical "honest floor, named refusal over a wrong parse" rule the module already held for every other unsupported shape. `tests/unit/weft_cli/test_argparse_gen.py` gained 3 tests for the three cases · **`_render_result`'s `isinstance` chain became a dispatch table, forced by `ruff`'s own complexity budget** once task 3.7 doubled the count of `CommandResult` subclasses it tells apart (14 branches > the 12-branch ceiling). `_RENDERERS: tuple[tuple[type[CommandResult], Callable[[CommandResult], Rendered]], ...]`, each entry a `lambda` `cast`ing its argument down to the specific type its own `_render_*` function was written against — the identical defensive-cast idiom every `Command.run` in `weft_cli.commands` already uses for its own `args` parameter — rather than widening every existing, already-tested `_render_*` signature to `CommandResult` purely to satisfy one table. A stranger's result still falls through to the identical structured-dump floor as before · **`/config`, wired in the same commit — task 3.5's own deferral, closed.** `weft_cli.repl._dispatch_config` is a `run_command` alias for `config get`, `/plugins`'s own pattern proven a second time: `/config` with no argument is `config get` with no `--key`; `/config <key>` forwards `<key>` as `--key`. Split into its own function, not `_dispatch_slash`'s own body, for the identical `ruff` complexity reason the renderer table exists — the eighth branch that function's own budget refused. `_DEFERRED_SLASH_COMMANDS` shrinks to one entry (`eval`, still no owner) · **measured.** `weft-kernel`: **2,891 → 2,891 lines (+0)** — `git diff --stat packages/weft-kernel` is empty; this task never opened a kernel file. `uv run poe ci-checks` is green: **1,467 passed, 1 skipped, 76 architecture tests** (from 3.6's 1,414 — 53 new tests across `test_pipeline_catalogue.py`, `test_pipeline_diff.py` (new), `test_pipeline_commands.py` (new), `test_config_surface.py` (new), `test_config_commands.py` (new), `test_argparse_gen.py`, `test_commands.py`, `test_render.py`, `test_repl.py`, `test_exit_codes.py`). `uv run poe kernel-isolated` is green · **`docs/02-extension-model.md`, `docs/03-cli.md`, `docs/README.md` and `manual/troubleshooting.md` edited in the same commit** — §2's stale zero-discovery claim corrected; `03` gained three new blockquotes (*Command surface*, *Permissions*, *Project context*) plus a short note under *In-session commands* for `/config`; `README.md`'s Status block carries the same evidence, condensed; `troubleshooting.md` gained three new entries (`ProjectPipelineNameCollisionError`, `UnknownPipelineNameError`, `UnknownConfigKeyError`), satisfying the coverage ratchet properly rather than by waiver · **left to later tasks, named rather than silently covered**: the stranger-command completion test (3.8); the generated manual command table (3.9); the degenerate-loop guard (3.10); `weft ask` routing by default (3.11, and `weft route`'s own double-print rough edge stays exactly as 3.6 left it); a `Command.describe_impact`-style contract method for a real collection name and document count, once a real `overwrite`/`destroy` command needs one — still unowned, though `init`/`derive`/`config set` are now that command in every sense except needing the count; slot-contribution discovery (`PackRegistrar.add_contribution`), the real gap behind `unapplied_operators`/`unplaced_contributions` staying empty — no task currently owns this either. · **one repair, 2026-08-20, from a review of `f201e70`.** Running the shipped binary — `cd /tmp/empty && weft init` — found this task's own `overwrite` classification for `init`/`pipeline derive`/`config set` refusing the *first* run of the first command a new user or a CI job executes, with no TTY to confirm in and no `weft.toml` to lose: exit `3`, correct in isolation, wrong for the operation, because scaffolding into a project with nothing yet is a *create*, and `docs/03-cli.md` → *Permissions*'s own table already puts "write a derived pipeline" under `write` (allow), not `overwrite` (ask) — this task's original "no upsert-safety" argument proved too wide, since the case it was actually protecting against (losing a file that already held something) only exists on a *second* run. **Reclassified**: `InitCommand`/`PipelineDeriveCommand` are `write`-class now; the safety `overwrite` bought is not given up, it moves from a TTY prompt to an unconditional, loud, named refusal when the target already exists — `weft_cli.commands.TargetAlreadyExistsError`/`weft_cli.pipeline_commands.PipelineAlreadyExistsError`, each a plain `WeftError`, never `CommandRefusalError`: this is not a permission refusal (`weft_cli.confirm.gate` never runs for a `write`-class command at all), so it does not carry `ExitCode.POLICY_REFUSED`. Exit code chosen deliberately, per the review's own instruction, not defaulted: `weft_cli.exit_codes.exit_code_for`'s existing default for "every other `WeftError`" — `OPERATION_FAILED` (`1`) — the answer is certain (the target exists), not a policy question this tool declined to decide without a human, which is what `3` means. **`config set` decided independently, argued from the same table rather than accepted on the reviewer's say-so**: `write`, because the class `overwrite` exists for — a prompt stating "what will be destroyed and how much of it" — has nothing meaningful to say about a single, self-named key edit (`set_config_text` preserves every other key and comment untouched); the entire blast radius is the one key and one old value the invocation itself already names, unlike `overwrite`'s own worked examples ("reindex an existing collection", "replace a pipeline file"), each of which discards something the invocation does not bound. **Consequence stated, not discovered later**: no first-party command, and no out-of-tree example pack in this tree (`examples/weft-example-command` declares `read`), is `overwrite`/`destroy`-class any more — task 3.3's no-TTY/`--yes` machinery is exercised only by `tests/unit/weft_cli/test_cli.py::_WipeCommand` and `tests/unit/weft_cli/test_confirm.py`'s own direct unit tests, the same position Phase 0 shipped for other machinery and said so. `docs/03-cli.md` → *Command surface* and *Permissions* corrected in this commit (both blockquotes this task added); `manual/troubleshooting.md` gains `### `TargetAlreadyExistsError`` and `### `PipelineAlreadyExistsError`` (task 0.14's coverage ratchet) and corrects `### `CommandRefusalError``'s own now-stale "none is `overwrite`/`destroy`-class *yet*" sentence to state the permanent position. **Re-proved by hand, exactly as the review specifies** — `weft init` in a genuinely empty directory, no TTY: `wrote weft.toml.`, exit `0` (was: refused, exit `3`, printed twice). `weft init` again, `weft.toml` now present: `'weft.toml' already exists. 'weft init' creates a new project's configuration; it does not replace one. Edit the existing file directly, or remove it first if you mean to start over.`, exit `1`, printed exactly once (task 3.6's own sink-lifecycle repair, above, is what makes this a single line rather than two). `weft-kernel`: **2,891 → 2,891 lines (+0)** — `git diff --stat packages/weft-kernel` empty, `BUDGET`/`REVIEW_TRIGGER` untouched. `uv run poe ci-checks` green after all three tasks' repairs (3.3, 3.6, 3.7 together, one commit): fmt clean, lint clean, `pyright` 0 errors, **76 architecture tests**, **1,476 passed, 1 skipped**. `uv run poe kernel-isolated` green. · **second repair, 2026-08-20, from a review of `dae55e7`.** Finding 2 (recorded in full in 3.2's own paragraph) touches two things this task built: `weft_cli.config_surface.validate_set_value`'s `permissions` branch (`:202-208`) is one of the two boundary cases finding 1 examined and excluded from FF12's family (3.3's own paragraph carries the argument; a comment now states it in place, so the exclusion reads as decided rather than merely unnoticed) — and `weft_kernel.registry.UnknownPluginError`'s `valid_options`, which this task's own `require_plugin`/`_unresolved` docstring already describes as the mechanism behind the refused/silent/nothing-amiss split, now survives into `weft_cli.commands.UnresolvedPluginNameError` for the two branches that are genuinely a name-resolution failure rather than being discarded at `_unresolved`'s own `plain=str(exc)` line. No change to this task's own `UnknownConfigKeyError`/`CONFIG_KEYS` machinery, which was already the shape both findings match themselves against. `uv run poe ci-checks` green after both findings' repairs together, one commit — **79 architecture tests, 1,493 passed, 1 skipped** (see 3.2's paragraph). `uv run poe kernel-isolated` green.
- [x] **3.8** a plugin's command appears in `--help` and in completion without core knowing it exists, as an automated test · owner `01` → Phase 3 **Exit** · turns on — · sha `8358982` · **this is Phase 3's own exit criterion, and it is demonstrated against a real installed stranger, not argued from the code shape.** `tests/architecture/test_phase3_exit_command_surface.py`, a new file, runs `weft-example-command` (task 3.2's stranger) through a throwaway environment built from real wheels — kernel, every first-party pack, and the example — with this repository nowhere on `sys.path`, exactly `test_ff9_extension_from_outside.py`'s own machinery · **claim 1 — appears in `weft --help` — proven by the real, installed console script, not a bare invocation.** `weft <name> --help` (the plugin's own registered name, read off its `pyproject.toml`/`register()`, never hand-typed) is a real subprocess of `weft-cli`'s own `[project.scripts]` entry, and `-h`/`--help` is intercepted by `argparse` itself once the registry-driven parser recognises the subcommand — the leaf `usage: weft <name> ...` line names the plugin. A **bare** `weft --help` was deliberately not used: `weft_cli.cli.main`'s own `prescan_command_name` strips every `-`-prefixed token before deciding whether a command was named, so a lone `--help` is indistinguishable from no arguments at all and enters the interactive session instead of ever reaching `build_parser`'s help text — `docs/03-cli.md` → *Two modes, one implementation* states this as of task 3.6 ("no arguments at all, or only global flags... enters the session"), and confirmed directly by running the shipped binary (`weft --help < /dev/null` prints only the REPL banner). That is documented, deliberate CLI behaviour, not a defect this task exists to route around; `weft <name> --help` is the literal, real-binary, real-`--help`-flag proof the task asks for, and a stronger one than the bare form, which never reaches the registry-driven help text at all · **claim 2 — appears in REPL completion — proven by the real, installed `repl_completions`, called from inside the venv.** A probe script run by the venv's own interpreter imports `weft_cli.registry_bootstrap.build_dependencies` and `weft_cli.repl.repl_completions` — never reimplemented — builds a real registry against a `weft.toml`-less project directory (`build_dependencies()` with no arguments, `weft_cli.cli.main`'s own call for exactly this shape) and asserts the plugin's name is in `repl_completions(registry, "")`'s own output, `weft_cli.repl`'s own module docstring naming this pure function as "what a test — 3.8's, or this file's own — can call directly, without a pty or a keypress" · **claim 3 — without core knowing it exists — proven by reuse, not by a fourth grep implementation.** `files_naming`/`text_files` (`test_ff9_extension_from_outside`'s own helpers) scan every file under `packages/` for the plugin's distribution name, module name and registered plugin name and find none — `weft-example-command` is already one of that file's `_ALL_EXAMPLE_DIRS`, so this property already runs on every commit as part of FF9(b); this file's own copy restates the same evidence from the phase-exit angle on the one function already proven able to fail, rather than a second implementation of the walk · **the self-test — plant the failure, confirm it is caught.** After both surfaces show the plugin, the pack is **uninstalled from the same venv** and both probes are re-run: `weft <name> --help` now fails with `argparse`'s own "invalid choice", and `repl_completions` no longer names it — proving the property depends on the pack being installed, not on one fixed transcript, `test_ff9`'s own clause-(a) uninstall pattern applied to `Command`. `test_the_command_name_scan_can_actually_fail` is the matching plant-a-literal self-test for claim 3, `test_ff9`'s own `test_the_grep_can_actually_fail` pattern applied to this file's own names · **not a new fitness function — the task's own `turns on` field is `—`.** FF9's three clauses are generic over any published contract; this property is specific to `Command` and to two CLI-only surfaces neither clause reaches (a real console script, `repl_completions`), so it earns its own file rather than a fourth FF9 clause. Reachable from `uv run poe ci-checks` exactly as every `tests/architecture` file is — confirmed, not assumed, by reading `test_ff0_gate_in_the_gate.py`: `tool.poe.tasks.arch` runs the whole directory, and `ARCHITECTURE_TASKS = frozenset({"arch"})` is what that test asserts sits inside `ci-checks` · **the venv-building machinery is reused, and reuse forced one small, honest edit to the two files it came from.** `test_ff9_extension_from_outside.py`'s `distribution_name`/`module_and_plugin_names`/`files_naming`/`text_files` and `test_ff9c_every_contract_has_a_stranger.py`'s `run_subprocess`/`build_wheel`/`FIRST_PARTY_DISTRIBUTIONS` were each spelled with a leading underscore until this task — `pyright`'s own `strict` `reportPrivateUsage` check (part of `poe types`, inside `ci-checks`) correctly refuses a third module importing a single-underscore name across files, so reusing them honestly meant renaming all seven to public spellings in both source files, every call site inside each updated in the same commit — a rename, not an extraction: they are genuinely shared infrastructure across three files now, which the old names denied. No fourth, standalone module was created to hold a second copy of a decision two files had already made identically twice · **the example pack needed nothing new.** One command, `"greet"` (`PermissionClass.READ`), already exercises the identical registry-driven mechanism (`_add_command_level`'s leaf branch at depth 0) every namespaced multi-word command also goes through; a second command or a distinct permission class would not have changed which code path any of the three claims exercises, so none was added · **the property held cleanly — no fix to `weft-cli` or the example pack was needed.** The one thing worth naming rather than silently working around is the bare-`--help`-enters-the-REPL behaviour above: real, documented, deliberate, and the reason this task's own claim-1 proof runs `weft <name> --help` against a real registered subcommand instead of the bare form · **measured.** `weft-kernel`: **2,891 → 2,891 lines (+0)** — `git diff --stat packages/weft-kernel` is empty; this task touched no kernel file. `uv run poe ci-checks` is green: **1,479 passed, 1 skipped, 79 architecture tests** (from 3.7's 1,476/76 — the 3 new tests in this file). `uv run poe kernel-isolated` is green · **`docs/03-cli.md` edited in the same commit** — a new blockquote under *Plugin-contributed commands* recording the proof and the bare-`--help` caveat; `docs/README.md`'s Status block carries the same evidence, condensed. **`docs/README.md`'s Phase 3 Exit box is deliberately left unticked** — 3.9, 3.10 and 3.11 remain, and the project owner ticks phase boxes, not a task · **left to later tasks, named rather than silently covered**: the generated manual command table (3.9); the degenerate-loop guard (3.10); `weft ask` routing by default (3.11, and `weft route`'s own double-print rough edge stays exactly as 3.6 left it); CLI-level spans/error attribution and a `Command.describe_impact`-style count, both already unowned before this task and unchanged by it. · **Repaired, 2026-08-20, from a review of `4aeba88`.** This task's own exit demonstration proved claim 1 against `weft <name> --help` — the per-command leaf help — after finding that bare `weft --help` "enters the session" and treating that as documented, deliberate behaviour; it was in fact the defect `weft_cli.cli.wants_help`'s own repair fixes (3.2 and 3.4's ledger entries carry the routing fix, above). `tests/architecture/test_phase3_exit_command_surface.py::test_the_strangers_command_reaches_help_and_completion_without_core_naming_it` now asserts claim 1 against bare `weft --help` first — the exit criterion's own words — checking the plugin's registered name and declared `help` text appear among the top-level help `build_parser` generates, and, in the same uninstall-and-re-probe step this task already built, that removing the pack removes it from that same bare-`--help` output; the leaf `weft <name> --help` form is kept as a second, additional assertion of the same mechanism, not the only one. Watched fail against the pre-repair tree for the right reason before the fix landed: `bare_help_ran.stdout` contained "weft -- interactive session", the REPL banner, not help text — confirmed by temporarily reverting `weft_cli.cli`'s own repair (`git stash` on that one file) and re-running this test in isolation, which failed on exactly that assertion, then restoring the fix and re-running green. Fitness function 8(b) (`tests/architecture/test_ff8_trust_model.py`) is untouched by this repair and reconfirmed green, unedited. `uv run poe ci-checks` green: 79 architecture tests, 1,485 passed + 1 skipped.
- [x] **3.9** the user manual's command table is generated from the registry rather than maintained, and the contract reference covers `Command` · owner `08` §1–§2, §3 clause (b) · turns on — · sha `e49f73f` · **two halves, one already true.** `weft-command` published `Command` (task 3.1) and `weft-cli` registered thirteen names under it (tasks 3.2/3.7), which already made it a *named* registration `weft_cli.contract_reference.published_contracts` walks like any other — `manual/contract-reference.md`'s `## Command` section, and the six tests in `tests/docs/test_generated_docs.py` that already covered it, needed no new code; this task verified that rather than building it twice · **the new half is the command table.** `weft_cli.command_table.command_entries` walks `registry.names_for(weft_command.contract.Command)` — the identical walk `weft_cli.cli.build_parser` already makes to generate `weft --help`'s own grammar (`03` -> *Plugin-contributed commands*: "the help text is generated from the registry, which means it cannot drift from what is installed") — and renders one row per registered command: invocation, permission class, registering distribution, `help` text. `PublishedCommand`'s two attribute reads (`_help_of`/`_permission_class_of`) fail loudly with a new `CommandNotDescribableError` rather than crashing with a bare `AttributeError`, on `ContractNotDescribableError`'s own footing — unreachable in practice since `Command.required_declarations` already refuses a registration missing either, but a defensive check rather than a silent assumption · **spliced, not written whole — `manual/user-manual.md` is mostly hand-written narrative, unlike `manual/contract-reference.md`.** `weft_cli.command_table.SECTION_BEGIN`/`SECTION_END`, two HTML-comment markers, bound the region `spliced_manual` replaces; every other byte of the manual — the pipeline walkthrough, the corrected opening paragraph — is untouched by regeneration. `scripts/generate_command_table.py` writes it; reused, not duplicated, discovery: both this script and the table's own generator call `weft_cli.contract_reference.discover_for_reference`, the identical open, placeholder-DSN registry build the contract reference already uses, argued in `command_table`'s own module docstring rather than assumed · **the floor-before-diff shape, `08` §3's decision D1, on `test_every_registered_contract_is_walked`'s own pattern.** `missing_command_names` is the pure comparison function — every registered name minus what `command_entries` actually walked, minus what is waived — and `test_every_registered_command_is_walked` computes it against the real `Registry.names_for(Command)` directly, never against the generator's own bookkeeping, before `test_generated_command_table_matches_the_checked_in_manual`'s text diff ever runs. `COMMANDS_WAIVED_FROM_TABLE`, `08` §3's ratchet for this clause, pinned empty. A contamination guard, `_command_distributions_beyond_workspace` against the existing `KNOWN_WORKSPACE_DISTRIBUTIONS`, catches a stray installed pack the same way the contract-reference check already does · **proven able to fail, by hand, not merely asserted.** Rewording one committed row's `help` cell by hand and re-running `test_generated_command_table_matches_the_checked_in_manual` fails it, naming the drift and the regeneration command; reverted. Full output in this task's own report · **the manual's one stale claim is corrected, not silently left.** "There is no `weft pipeline derive` command yet" (written before task 3.7 landed) gets a dated blockquote directly beneath it rather than a rewrite in place — the Python walkthrough that follows is unchanged and still true, still the equivalent call a real command now also makes on a reader's behalf · **`CommandNotDescribableError` tripped `08` §3 clause (d)'s troubleshooting ratchet, and got a real entry, never a waiver** — `manual/troubleshooting.md` -> *Command table generation*, on `ContractNotDescribableError`'s own footing directly above it · **G9 not engaged.** Recording `Command.version`'s declared string in the reference is not a claim about what a version *obliges* — that question stays open, untouched by this task · No kernel line (`git diff --stat packages/weft-kernel` empty). `uv run poe ci-checks` is green — **1,491 passed, 1 skipped, 79 architecture tests**. `uv run poe kernel-isolated` is green.
- [x] **3.10** a small model that falls into a loop stops being streamed rather than filling a reader's terminal, and legitimately repetitive content — a markdown table — is not mistaken for one · owner `01` → Phase 3 **Lift**; `reference/study/08-salvage.md` §T1.12 · turns on — · sha `14b409b` · **the asset is a taxonomy of measured tuning, not code — `reference/study/08-salvage.md` §T1.12, verified at source and independently re-verified.** `weft_llm.loop_guard` (new module, `weft-llm`) is a fresh rewrite, never adapted reference text: a `LoopGuardConfig` (frozen, `extra="forbid"`) carrying every constant `[llm.loop_guard]`-parameterisable rather than hardcoded, each with the reasoning that produced its value kept as a comment, not only the number — `min_period=50` (raised from a smaller value the reference also tried, because a shorter period matches ordinary short phrases repeating in normal prose), `max_period=500` (bounds the search cost), `similarity_threshold=0.85` and `diversity_threshold=0.3` (both required together — a candidate window must be similar *and* internally repetitive, which is what keeps ordinary prose that reuses a phrase from tripping the guard), `min_text_length=100` (below this, nothing is checked — the floor that keeps a short answer's per-token cost near zero), `fuzzy_step=10` (candidate periods above the floor are sampled every 10 characters, not walked one at a time), `ngram_size=5` (passed explicitly at the one call site rather than relied on as the diversity helper's own general-purpose default of 3), `table_lookback_chars=500`/`table_lookback_lines=10` (how far back the table detector looks), `table_line_threshold=1` (deliberately aggressive — a table streamed row by row is caught after its first line, before its closing pipe has even arrived), `alphanumeric_ratio_threshold=0.3` (a line under this ratio reads as formatting rather than prose). **The audit is wrong in one place, found at source and independently re-verified by a second agent.** §T1.12 names the alphanumeric-cutoff method `_is_formatting_noise` at `citation.py:183-190` — no method of that name exists; the real one is `_is_special_character_pattern`, `citation.py:149-190` (the line range was already right; only the name was wrong). Corrected in `docs/01-high-level-plan.md` → Phase 3 → *Lift* (dated 2026-08-20) rather than in the frozen `reference/`, and never cited by the wrong name anywhere in Weft. **Ordering is load-bearing and is expressed as a fact a reader sees, not as nesting depth.** `detect_generation_loop` calls `_looks_like_table` and `_has_repeating_tail` as two sibling top-level functions, table check first — three lines, not a repetition check buried inside the table check's negative branch — because a markdown table streamed one row at a time is legitimately repetitive until its last row arrives, and running the repetition passes first would cut it off mid-render. **The cumulative-text contract is stated, not implied.** The guard must be handed the whole answer generated so far on every call, never a delta — the module docstring states this before any other paragraph — and its cost is real: comparing an ever-growing string against itself on every token is `O(n)` per call and `O(n²)` across a stream, which is exactly why `min_period`, `min_text_length` and `fuzzy_step` exist rather than being decoration. A test (`tests/unit/weft_llm/test_loop_guard.py::test_only_the_whole_accumulated_answer_reveals_a_loop_a_single_delta_cannot`) proves it directly: the same text fed as repeated single-phrase deltas never fires, fed cumulatively it does. **Attaches inside `LLMClient.complete`'s own accumulation loop, confirming task 3.6's placement rather than assuming it.** `parts` (the list `complete` already builds, one append per chunk, before this task) is `"".join`ed and checked after every `sink.emit` — the only place in this tree already holding the whole answer on every token, which is exactly the shape the contract needs; a `TokenSink` never sees more than one chunk at a time and could not run this check itself. The chunk that reveals the loop is emitted before the check runs, so a reader still sees it. **The reference ships two variants of the same guard, only one live, and Weft chose neither shape as-is, argued rather than defaulted.** The callback variant splices a visible marker (`'\n[STOPPED: Repetition loop detected]'`) into the model's own output stream; the generator variant — the one the live engine actually calls — breaks silently with only a log warning, indistinguishable from a clean end to any consumer that does not inspect internals. Weft has a third option the reference lacked: `weft_llm.errors.LLMGenerationLoopError` (new `LLMPermanentError` leaf — permanent because a small/local model that loops on a prompt tends to loop identically on retry, so the retry wrapper must not spend attempts replaying it) is raised, takes the same `except LLMError: raise` path a provider's own errors already do, and `weft_cli.cli.run_command` (task 3.6's own seam-adjacent close point) turns the raise into `TokenSink.close(reason=...)` — stopping the stream *and* telling the reader why, distinctly from a clean `DONE`, without splicing text into the model's own output and without the reference's silent-break shape. New `WeftError` subclass, new `manual/troubleshooting.md` entry (`### \`LLMGenerationLoopError\`` under *The LLM client*) forced by the coverage ratchet (task 0.14) — no waiver. `[llm.loop_guard]` threads through `weft_cli.llm_roles.LLMSection`/`llm_section_from_config` on the identical footing `[llm.retry]` already has (a new operator-facing table an operator may omit entirely or override one key of), through `weft_cli.run_services.build_services` to `weft_llm.client.llm_service`; `manual/operations-guide.md` gained a matching *Stopping a model stuck in a loop* subsection beside *How hard to try*. Naming discipline held throughout: never named or documented as hallucination detection, only as a loop-breaker for a model that got stuck. **No source text copied** — verified against the reference's own comment block (`citation.py:255-266`'s worked pair, `:130`'s "lightweight alternative to Levenshtein distance" quote) by writing every docstring, message and algorithm fresh from the *understanding* those passages gave, never by adapting the passages themselves; the module's own algorithm (diversity measured over the whole two-period comparison window, not the reference's own exact internals, which were never read past the audit's own excerpts) was designed and hand-verified against the four worked cases and the true/false pair before any test was written. Tests: `tests/unit/weft_llm/test_loop_guard.py` (9 tests — the four table shapes, the true/false repetition pair, the length floor, the cumulative-text contract, config validation) and four new cases in `tests/unit/weft_llm/test_client.py` (a looping provider stops early and every shown token survives; a streamed table is never interrupted; a caller-supplied `LoopGuardConfig` is honoured) plus 4 new cases in `tests/unit/weft_cli/test_llm_roles.py` for `[llm.loop_guard]` parsing — 16 new tests total. No kernel line (`git diff --stat packages/weft-kernel` empty, confirmed). `uv run poe ci-checks` green: **1,509 passed, 1 skipped, 79 architecture tests** (from 1,493/1/79 before this task). `uv run poe kernel-isolated` green.
- [x] **3.11** `weft ask` routes by default, so the question a user asks reaches the pipeline the router names without them knowing a second command exists · owner `03` → *Command surface*; `01` → Phase 2 **Exit** (the router itself, task 2.8) · turns on — · sha `4af2e28` · **the surface decision, argued from `03` itself rather than defaulted.** Before this task `ask` was Phase 0's own retrieve-only command and `route` (task 2.8) was a second, additive command that actually reached the router — two commands, and a caller had to know which one to type, exactly the gap the task line names. `docs/03-cli.md` → *Command surface* had already published the answer without anyone updating it for `route`'s existence: its table describes `weft ask <question>` as *"query, streaming the answer with citations"* and never lists `route` at all — read literally, that sentence is 3.11's own resolution. Chosen over the ledger's second offered shape (`route` survives as an explicit-override spelling): keeping two names for the identical behaviour is precisely the "two commands, know which one" surface this task exists to close, and `03`'s own table gives no reason to keep a name it never described. `weft_cli.commands.AskCommand` absorbs `RouteCommand`'s body verbatim; `route` is deregistered (`weft_cli.commands.register`), twelve names now, not thirteen · **naming a pipeline directly — a genuinely new capability, not a re-spelling of what `route` did (`route` never took a pipeline name either; it only ever ran the router).** `weft ask <question> --pipeline <name>` bypasses the router and runs `weft_cli.route_ask.run_named_ask` (new) instead, resolved against `weft_cli.pipeline_catalogue.full_catalogue` — project-local documents *and* every installed pack's own contribution, deliberately wider than the router's own `load_contributed`-only search set (Phase 2's settled behaviour, untouched), so a pipeline scaffolded by `weft pipeline derive` and never published as a pack is reachable the moment it validates. An unknown name reuses `weft_cli.pipeline_catalogue.UnknownPipelineNameError` rather than a new class — that class's own docstring already covers "a bare name a person typed at the command line", which is exactly what `--pipeline` is, one caller further than the four `weft pipeline` commands that established it; `NAME_RESOLUTION_FAMILY` therefore stays at 24 members, a deliberate, argued non-addition rather than a silent one. `_prepared_runner`, a small new private helper in `route_ask.py`, is the `build_services`/`Runner`/store setup `run_routed_ask` and `run_named_ask` now share, factored out once a second caller existed rather than duplicated · **`--retrieve-only` keeps Phase 0's own contract reachable, deliberately not deleted.** Reproduced on the real binary before deciding this was necessary, not assumed: a `weft.toml` naming no `[llm.roles]` table maps nothing (`weft_llm.roles.LLMRoles`'s own "no silent default" clause), so the routed default refuses loudly — `no [llm.roles] entry maps role 'route'. Roles mapped in weft.toml: (none mapped).` — exactly where `manual/quickstart.md`'s zero-configuration walkthrough and `eval/run_baseline.py`'s V3 baseline (`09` §4.3, a deterministic, credential-free, network-free measurement) both need `weft ask` to still just retrieve. `--retrieve-only` and `--pipeline` are mutually exclusive — refused by a new `ConflictingAskModeError` (`weft_cli.commands`, exit `1`: not a name-resolution failure, so not `NAME_RESOLUTION_FAMILY`, on `TargetAlreadyExistsError`'s own "a certain answer, not a policy question" footing) before either resolves a plugin. `manual/quickstart.md`'s own `id=ask` block and `eval/run_baseline.py`'s subprocess call both gained `--retrieve-only` in this commit, so neither's own promise (a five-minute, zero-config walkthrough; a deterministic offline baseline) silently broke · **the reference has no precedent, and the absence is itself the finding (`.phase3-design.md` §2.5, verified at source before this task started).** Every reference CLI path that builds an engine config disables its own router explicitly — `RouterConfig(enabled=False, ...)` at `generation/chat.py:99` and `:270` — and `retrieval/query_tools.py` is a third entry point exposing only named-strategy subcommands (`hyde` `:49`, `stepback` `:130`, `compare` `:215`): a user has to already know the strategy name before typing anything, precisely the gap this task closes. `AdaptiveRouter` exists in the reference's core but is opt-in only through a hand-written YAML config, off by default everywhere a human actually types a command · **the double-print fix, and how it relates to the 2026-08-20 repair.** Task 3.6's own report flagged it and named this task as owner: `weft route`'s answer printed twice — once live, through `PrintingSink`/`JsonSink` as the generating stage streamed it, once more in full after the run finished, because `_render_route` unconditionally re-printed `Answer.text`. The mechanism from the *different* double-print repaired 2026-08-20 (a permission refusal, shown once by `render_refusal` and once by the sink's own failure path) supplied the right *shape* — decide from a fact about whether this run's own sink actually showed something — but not the right *fact*: that repair's `_EmissionTrackingSink.emitted` is set by *any* role's chunk reaching `emit`, the router's own `role="route"` scoring call included, so reusing it unchanged would suppress the answer even on a run where nothing visible ever streamed (`--quiet`, or a routing failure before generation ever starts). The fix is a second, role-aware fact the sink itself is uniquely positioned to know, not a second parallel tracking wrapper: `weft_cli.sinks.PrintingSink`/`JsonSink` each grew a public `wrote_anything`, set `True` only for a chunk `_visible` already decided a reader would see (`PrintingSink`'s own `_wrote_anything` already tracked exactly this internally, for its `close()`-newline decision — made public rather than duplicated; `JsonSink` gained the identical attribute fresh). `weft_cli.cli.run_command` reads it off the *real* sink — `getattr(deps.token_sink, "wrote_anything", False)`, never `tracked_sink` — and threads it into `weft_cli.render.render_outcome`'s new `streamed` keyword, read only by `_render_ask`: `NullSink` (`--quiet`) carries no such attribute, so `getattr`'s default answers "nothing streamed" and the full text still prints, holding G6's "`--quiet` suppresses progress but keeps the result." Verified on the real binary in a throwaway project (`--pipeline no-retrieval`, `[llm.roles] generate = { provider = "scripted" }`): the stream showed `[scripted] Question: ...\n\nPassages:\n\n` live, and the final render printed only `routed to: no-retrieval` plus citations — the text did not repeat · **what a caller naming a pipeline explicitly now does**, stated once for the report: `weft ask <question> --pipeline <name>`, checked against `weft plugins doctor`/`weft pipeline list`'s own catalogue, refused with every known name listed if it does not resolve · **measured.** `weft-kernel`: unchanged, `git diff --stat packages/weft-kernel` empty — this task never opened a kernel file. `uv run poe ci-checks`: **79 architecture tests, 1,512 passed, 1 skipped** (from 3.10's 1,509 passed — net +3: several `route`-specific tests folded into `ask`-prefixed ones, three new: the conflicting-mode refusal, `--pipeline` skipping the router, and `_render_ask`'s `streamed` suppression). `uv run poe kernel-isolated` green · **`docs/03-cli.md` edited in the same commit** — a new blockquote under *Command surface* (the ledger's own instruction) carrying the surface decision, `--pipeline`, `--retrieve-only`, the reference's absent precedent and the double-print fix; the task-3.6 blockquote under *Output* corrected to note `RouteCommand`'s retirement. `manual/quickstart.md`, `manual/operations-guide.md`, `manual/troubleshooting.md` (a new `ConflictingAskModeError` entry, and every stale "`weft ask` retrieves; it does not generate" / literal `weft route` mention corrected) and the generated `manual/user-manual.md` command table (`scripts/generate_command_table.py`, re-run) all follow in the same commit. `docs/README.md`'s Status figures carry the same evidence, condensed.

**Exit** (`01` → Phase 3): task 3.8 — **met, and the phase closed 2026-08-20 at 11 of 11 tasks.** `tests/architecture/test_phase3_exit_command_surface.py` proves it against the shipped binary: a throwaway venv installs `examples/weft-example-command`, a subprocess of the installed console script shows its command in bare `weft --help`, the installed `weft_cli.repl.repl_completions` names it, and a scan of `packages/` finds core naming it nowhere — the name read off the pack's own metadata rather than typed into the test, and the check made to fail on purpose by uninstalling the pack and re-probing. The bare-`--help` half is the phase's own second repair (`2513c16`): as first shipped the criterion was demonstrated only against per-command leaf help, because `weft --help` entered the REPL.

**3.1 published `Command` from a new distribution, `weft-command`, and that placement is this
task's own architectural decision — no prior document had settled it.** Not `weft-kernel` (G1:
the kernel names no capability, and "a CLI-invoked action" is one). Not `weft-cli`: `03`'s
governing rule makes `weft-cli` the **driving** adapter, and a pack implementing a contract must
depend on the pack that *publishes* it, never on the adapter that *drives* it — `weft-cli` today
names nine other distributions as dependencies, every one of which a third-party command pack
would otherwise inherit transitively for the sole purpose of reading one Protocol. The precedent
is `weft-prompts`, which took the identical position for `Prompt` at task 2.10: a distribution
that publishes a contract, registers no plugin of its own, and declares no `weft.packs` entry
point (fitness function 2 requires that entry point's owner to be active *and* contributing).
`weft-cli` gains `weft-command` as a tenth dependency, for `PermissionClass` — moved out of
`weft_cli.permissions`, re-exported from there so every existing caller keeps resolving the
identical class object, next to the contract that reads it (`Command.required_declarations`).

**The generalisation task 3.1 required of `weft_kernel.registry` is real, and it is the task's
best evidence of correctness.** `docs/03-cli.md` → *Permissions* asks for the exact shape task
1.2 already built for `destroys` — a required class-level declaration refused at registration,
loudly, naming the plugin and the remedy — but the kernel must not learn the words `Command` or
`permission_class`. `_require_destroys_if_governed` became `_require_declarations_present`,
reading a merged `_required_declarations(contract)`: `contract.required_declarations` (the new,
contract-agnostic mechanism `Command` uses) folded together with the legacy
`publishes_property_vocabulary` flag (folded in as `"destroys"`, so `Chunker`, `Cleaner` and
`Generator` needed no change at all). One loop, one raise. `MissingDestroysDeclarationError`
stays exactly the class task 1.2's own tests catch by name, now as a subclass of a new
`MissingRequiredDeclarationError` that every other required declaration raises directly. Every
pre-existing test of the `destroys` behaviour — `tests/unit/weft_kernel/test_registry.py`,
`tests/unit/weft_chunk/test_contract.py`, `tests/unit/weft_clean/test_contract.py` — passed
unchanged, with no edit; that was the signal the generalisation was the right shape rather than a
second bespoke check wearing a general name.

**`Command`'s own shape**, in `weft_command.contract`: not a pipeline position (`Prompt`'s own
footing — no `Stage` base, so `Runner.resolve` and `capability_siblings`'s `_is_stage_protocol`
filter need no special case for it); `args_model`/`result_model` declared in the Protocol body
and required for `isinstance`, `Prompt.input_model`/`output_model`'s own choice, for the
identical reason; `run(self, args: BaseModel, ctx: Context) -> Outcome[CommandResult]`, args
passed at the call rather than bound at construction, because the same registered instance
answers a fresh `args` on every invocation — one shot from the CLI, or turn after turn in the
REPL — never one `with:`-style configuration a whole pipeline position shares.
`CommandResult` is a frozen Pydantic base every concrete command's own result subclasses,
building `03` → *Two modes, one implementation*'s rule directly into the signature: "a `Command`
returns a typed result and never writes to a stream."

**What this task deliberately left to 3.2 and 3.4, and why.** Namespacing a pack's commands
(`weft graph build`) is a registration-*name* convention — `registrar.add(Command, "graph
build", …)` registers under an arbitrary string exactly as any other contract's name would — and
turning that string into argparse subcommand wiring, generated `--help` text and REPL completion
is 3.2's own ("core has no command list to edit"). `weft_cli.cli.COMMANDS` and `CliCommand` stay
untouched; rewiring the five built-in commands onto `Command`, and building the renderer that
turns a `CommandResult` into text/JSON/REPL output, are 3.4's. Neither omission changes what 3.1
makes true: a pack registers a `Command` today, through the identical seam it would register a
retriever through, and an author who forgets `permission_class` finds out at registration, not
in production.

**No example pack was built for `Command`, and fitness function 9(c) does not ask for one yet.**
Verified by running `tests/architecture/test_ff9c_every_contract_has_a_stranger.py` after this
task's changes (all clauses green): its left side is `registry.contracts()` — contracts with at
least one *registered name* — and nothing registers a `Command` implementation yet, by design
(3.2/3.4's work). `Command` therefore never appears in `published_contracts(discover_for_reference())`,
so clause (c) has nothing to demand a stranger for. `test_every_exported_protocol_without_a_version_is_a_named_service`
also passes untouched: `Command` carries `.version`, so it is correctly classified as a real
contract rather than needing an entry in `SERVICE_PROTOCOLS_WITHOUT_AN_EXAMPLE_PACK`. The
obligation activates the moment something registers under it — most likely 3.2's own rewiring of
`weft_cli.cli.COMMANDS`, which is exactly why building a stranger now, against a contract nothing
implements, would have been premature: `examples/weft-example-command/` has nothing real to
implement yet.

**Measured.** `weft-kernel`: **2,869 → 2,886 lines** (+17, well inside the ~30-line stop
condition — the generalisation is a net-small change, not an addition of new machinery), still
under the 2,800 review trigger's shadow and the 3,500 budget, per `tests/architecture/
test_ff3_kernel_budget.py`. `uv run poe ci-checks` — **75 architecture tests, 1,316 passed, 1
skipped**. `uv run poe kernel-isolated` — green. Two tests needed updating for reasons unrelated
to the `destroys` generalisation and were fixed rather than waived: `tests/docs/
test_troubleshooting_coverage.py`'s hand-counted first-party-distribution floor (16 → 17, for
`weft-command` itself — its own docstring calls this the expected outcome of a new distribution
shipping) and its coverage ratchet, which correctly caught `MissingRequiredDeclarationError` as a
new `WeftError` subclass with no `manual/troubleshooting.md` entry; that entry is added, not
waived.

**Documents edited in this task's commit.** `docs/07-extension-cost.md`'s "New CLI command" row,
to name `weft-command` and task 3.1 rather than describe the contract only hypothetically.
`manual/troubleshooting.md`, a new `### MissingRequiredDeclarationError` entry beside
`MissingDestroysDeclarationError`. `docs/03-cli.md` was checked and needed no edit: it never
names which distribution publishes a contract for any capability, `Command` included, so nothing
it already says became untrue.

**3.10 and 3.11 were added 2026-08-18**, by the Phase 2 exit reference audit. Neither changes this
phase's exit, and neither activates a fitness function. 3.11 briefly carried ⚠ — "the model chooses
which pipeline to run" is G8's *agentic* position stated verbatim — and G8 settled the same day that
the chooser is a routing policy here and a Phase 7 pack there, never this REPL, so it routes by
policy and the ⚠ is gone.

**3.11 is a Phase 2 loose end this phase inherits, and the trail is worth keeping.** 2.25's own note
assigned the `weft ask` wiring to 2.8; 2.8 shipped an *additive* `weft route` instead and said so —
*"`weft ask` keeps Phase 0's own documented, tested, retrieve-only contract untouched, because
rewriting it was a bigger, separate risk than this task's own"* — which is a deferral with a reason
and no forward owner, so it had none until this line. It lands here rather than in Phase 2 because
what is left is a **command-surface** decision (`03`'s content, this phase's subject), not a router
one: the router exists, discovers from the catalogue and is demonstrated by 2.8. Note that `03` does
not yet describe `weft route` at all — whichever way 3.11 resolves, `03` is edited in the same
commit, per `README.md` → *Protocol*.

---

## Phase 4 — Evaluation and observability

**Gate: none.**

- [x] **4.0** `weft index` resolves a pipeline **document** rather than naming its four stages in Python, so a plugin's own `with:` configuration is reachable from a file and the run has a resolved pipeline to persist · owner `S4`; ledger 2.29; `02` §3 · turns on — · sha `1cacae4` · **`weft index <path> --pipeline <name>`, the identical surface `weft ask --pipeline` already has**: `weft_cli.ingest.run_index` grew a `pipeline` parameter that resolves a name against `weft_cli.pipeline_catalogue.full_catalogue` through the exact walk `weft_cli.route_ask.run_named_ask` already performs (`weft_cli.compile.contracts_for`/`to_specs`, then `Runner.resolve`) — no new design, the bridge task 2.4 built is reused rather than re-implemented · **Q3, settled: `[services]` and a document's `with:` stay two surfaces, never merged.** `[services] embed`/`[services] store` keep selecting a plugin with no configuration for the default, no-`--pipeline` path, exactly as before; a stage's own `with:` is reached only by naming a document. Inventing a `{ use = …, with = … }` form inside `[services]` — 2.29's own warning — is not built; when `--pipeline` is given, `[services] embed`/`[services] store` are not read for that run at all, because a document's own `use:` already names every stage's plugin. `manual/operations-guide.md` → *Choosing an embedder* is corrected in this commit — it documented exactly the limit this task removes · **which stage extracts and which stores are derived from `StageSpec.contract`, never from an id convention** — `_extractor_name_of`/`_store_stage_id_of` ask the registry what each stage's plugin *is*, the identical reasoning `weft_cli.compile` already applies one level up; a document naming no `Extractor`-contract stage refuses as `PipelineMissingExtractStageError` (new `NAME_RESOLUTION_FAMILY` member, `manual/troubleshooting.md` entry, coverage ratchet both green) rather than resolving into a run that reads nothing, while a document naming no `NodeStore`-contract stage simply has nothing for `stored_count` to report — the identical "`None` only defensively" reasoning `IndexResult.stored_count` already states for a store with no callable `count`. `--extract`/`--pipeline` together refuse as `ConflictingIndexModeError`, `ConflictingAskModeError`'s exact footing (not a `NAME_RESOLUTION_FAMILY` member — no alternative name to offer, only a choice between two flags), checked at both `weft_cli.commands.IndexCommand.run` and again inside `run_index` itself, so a library caller bypassing the command layer is not left to a silent one-wins-over-the-other · **`INDEX_DISTRIBUTIONS`/`[services]`'s own `require_plugin` gate is skipped when `--pipeline` is given** — a named document may depend on none of the three default-path distributions, so `IndexCommand` does not consult promises the document never made · **measured, from outside the repository, against the real container**: two project directories differing only in `pipelines/index.yaml`'s `chunk` stage `with:` block (`{size: 200, overlap: 20}` vs `{size: 50, overlap: 5}`) — `weft pipeline show index` prints the two resolved pipelines differing in exactly that one line, and `weft index ./corpus --pipeline index` run for real against the compose Postgres/pgvector container produced **4** stored nodes for the first and **16** for the second from the identical source file, with no package in this repository edited between the two runs. Failure paths run the same way: `--extract`/`--pipeline` together → exit `1`, naming both flags; an unknown pipeline name → exit `4`, listing every pipeline the catalogue holds (project-local and pack-contributed together); a document with no `Extractor`-contract stage → exit `4`, naming the stages it does have; a document naming an unregistered plugin → exit `4`, the registry's own full plugin list. `uv run poe ci-checks` green: **1,527 passed, 1 skipped, 85 architecture tests** · **left to later tasks, named rather than silently covered**: 4.4 is what actually *persists* the resolved pipeline this task makes reachable; the default, no-`--pipeline` path's own auto-extractor-discovery and `[services]`-only configuration are unchanged, by design (Q3); `_specs_from_document` passes `parents={document.name: document}` to `contracts_for`/`resolve`, the identical single-entry-catalogue shape `weft_cli.route_ask._run_pipeline` already uses for `weft ask --pipeline` — so an `extends:` chain reaching outside one document is not resolved for either command today, inherited rather than introduced here, and not this task's to fix
- [x] **4.1** a metric is a plugin, and the same metric runs twice at two thresholds because its registration carries a typed configuration model · owner `02` §1; `01` → requirement 6, second clause · turns on — · sha `6863be6` · **Q4 settled** (`.phase4-design.md` §3): `weft-eval` publishes `Metric` in `contract.py` and ships one demonstration plugin in the same distribution, `weft_extract`'s own shape rather than `weft_command`'s — nothing implementing `Metric` needs to avoid depending on its caller. Zero lines under `packages/weft-kernel` — the contract, `Sample`/`MetricScore`, `evaluate` and the whole registration mechanism live in the pack, exactly as G1 requires · **the result shape, and why the reference's accident cannot be represented**: `evaluate` returns `Outcome[MetricScore]` — the kernel's own `Produced[T] | NothingToProduce | Failed`, reused rather than reinvented (`docs/02-extension-model.md` §1: "every contract returns an `Outcome`"). `MetricScore` carries only `metric_name` and `value`, and it appears on `Produced` and nowhere else — there is no `float` field sitting beside an `error` string a caller could forget to check. The reference's own defect (R4 in `.phase4-reference-recon.md`: `BaseEvaluator.__call__` converts an exception to `score=0.0, error=<str>` at `core/ports/evaluation.py:55-63`, but most call sites bypass `__call__` entirely and let the exception propagate uncaught instead, so which of the two happens depends on which convention a caller chose, and only one aggregator in the whole tree ever reads `error` before averaging) is unrepresentable here by construction, not merely avoided by convention. `NothingToProduce` is the third arm, for a sample with nothing to score — an empty reference — distinct from both a real score and a failure, closing the reference's neighbouring defect (missing ground truth silently scored `0.0`, `docs/09-release.md` §4.2) · **dispersion, and the 4.1/4.3 split, stated as Finding 1 asks**: a single `MetricScore` is one number from one sample, and a standard deviation of one observation is not a real quantity, so this task carries none. Task 4.3 owns the aggregate — exclusion counts, dispersion across many observations, and the `k`-in-the-reported-name check run against `metric_name`, never the registered plugin name, per R5 · **the two-thresholds demonstration**: one plugin, `OverlapAtThreshold`, registered once as `"overlap-at-threshold"`; its `config_model`, `AtThresholdConfig(threshold: float)`, is validated independently for two callers — `AtThresholdConfig.model_validate({"threshold": 0.3})` and `{"threshold": 0.9}` — each producing its own constructed instance of the identical registered class, scoring the identical `Sample` differently (`tests/unit/weft_eval/test_at_threshold.py::test_the_same_metric_runs_twice_at_two_thresholds_from_one_registration`). Requirement 6's second clause cashed out: the same metric retuned by a caller who never wrote it, through a typed model the plugin declares — the identical `config_model` convention `weft_extract.render.PlainRenderer` already uses — not a constructor argument only the author knows to pass · **R2/R3 honoured, not fixed**: `evaluate` is `async def` unconditionally (G6) — not a reference repair, an unconditional consequence, since the reference's own port (`core/ports/evaluation.py:40-53`) is fully synchronous and correctly so for its own constraints. `config_model` is the mechanism the reference's own `MetricConfig.params` comment (`evaluation/config.py:22`) marks as missing, not a working mechanism this task replaces · **`Sample` kept narrow, on purpose**: carries only `query`, `prediction: str | None` and `reference` — enough for the one demonstration metric this task ships, not a grab-bag anticipating 4.2's 21. `docs/02-extension-model.md` §1's own rule ("when a caller needs only half an interface, that is two contracts") and the reference's own `RetrievalEvaluator`/`GenerationEvaluator` split are named in `contract.py`'s own docstring as the open question 4.2 settles once real implementations say what shape they need — not decided here by guessing · **fitness function 9(c) satisfied, not deferred**: `examples/weft-example-metric` registers `ExactMatch` under `Metric` from entirely outside the workspace, with its own typed `case_sensitive` config — `docs/07-extension-cost.md`'s own extension-cost table already named this row ("New metric ... 0, from Phase 4 ... the `with:` block is what makes the same metric runnable twice at two thresholds"). `tests/architecture/test_ff9c_every_contract_has_a_stranger.py` green with `Metric` on the left side · `manual/contract-reference.md` regenerated in this commit — `Metric`'s section (Finding 2) — and `KNOWN_WORKSPACE_DISTRIBUTIONS`/`_first_party_top_level_packages`'s pinned 17→18 count corrected alongside it, both drift-catchers this task would otherwise have tripped silently · **measured, from outside the repository**: all 18 first-party distributions (17 → 18, `weft-eval` the addition) built to wheels and installed into a throwaway venv; `weft --help` prints unchanged — no CLI surface for `Metric` ships here, by the scope fence (task 4.6 owns `weft eval`); `weft plugins list` shows `weft-eval: active (1 contributed)`. With no `weft eval` command yet to carry the metric-name failure path through the CLI, it is run one level down, against the installed wheels, from outside the repository: `weft_kernel.registry.Registry.lookup(Metric, "faithfulness")` raises `weft_kernel.registry.UnknownPluginError: no 'faithfulness' is registered for Metric. It is unavailable because no distribution has registered that name for this contract. Names registered for Metric: 'overlap-at-threshold'.` with `valid_options == ('overlap-at-threshold',)`; and the two-thresholds property, against the installed wheel rather than the source tree, prints `lenient (0.3): value=MetricScore(metric_name='overlap_at_threshold@0.3', value=1.0)` and `strict (0.9): value=MetricScore(metric_name='overlap_at_threshold@0.9', value=0.0)` for the identical `Sample`. `uv run poe ci-checks` green: **1,543 passed, 1 skipped, 86 architecture tests**; `uv run poe kernel-isolated` green · **left to 4.2/4.3/4.6, named rather than silently covered**: the 21 reference metrics, every recorded defect fixed at the door, are 4.2's; whether `Sample`/`Metric` stay one contract or split into narrower retrieval/generation contracts is 4.2's to decide once real implementations exist; the aggregate type — exclusion counts, dispersion across many observations, the `k`-in-the-name check run against a run record — is 4.3's; `weft eval run|compare` and the metric-name failure path reaching the CLI itself are 4.6's, unbuilt today by the scope fence, which is why this task's own failure-path demonstration runs one level below the CLI rather than through it.
- [x] **4.2** the reference's metric suite ships with every recorded defect fixed at the door rather than inherited, and no ratio is a number a model computed · owner `04` → the metric-suite entry; `01` → Phase 4 **Lift** · turns on — · sha `fdf44a7` · **21 metrics, three families**: 4 `RetrievalMetric` (`precision-at-k`, `recall-at-k`, `mean-average-precision`, `ndcg`, `weft_eval.ir_metrics`), 11 traditional `GenerationMetric` (`rouge-l`, `rouge-1`, `rouge-2`, `token-overlap`, `token-recall`, `key-terms-precision`, `exact-match`, `f1-score`, `accuracy`, `embedding-similarity`, `bertscore` — `weft_eval.lexical`/`qa_metrics`/`embedding_metrics`) and 6 LLM judges (`faithfulness`, `context-recall`, `context-relevance`, `answer-relevance`, `answer-correctness`, `answer-completeness` — `weft_eval.judges`, asking `weft_eval.prompts`), plus task 4.1's own `overlap-at-threshold` demonstration — 22 metrics and 6 judge prompts, 28 plugins total, `weft plugins list` confirms it against the installed wheel · **the contract split, decided**: `weft_eval.contract` now publishes `RetrievalMetric`/`RetrievalSample` beside `GenerationMetric`/`GenerationSample`, replacing task 4.1's single `Metric`/`Sample`. Argued in `contract.py`'s own module docstring and cashed out by the 21 real implementations: the four IR metrics score a ranked id list against a relevance set and never touch a prediction or reference string; `context-recall`/`context-relevance` need retrieved passage *text* and a query; the other fifteen need `prediction`/`reference` text and never touch a ranked list. A `Sample` wide enough for all of it would be the exact grab-bag `docs/02-extension-model.md` §1 already forbids ("when a caller needs only half an interface, that is two contracts") — mirroring the reference's own `RetrievalEvaluator`/`GenerationEvaluator` split, at the input type only; both still return the identical `Outcome[MetricScore]` V4 shape, so the result-shape half of 4.1's argument needed no change · **defect 1 (six of 21 never register) and defect 4 (an unknown name is silently skipped), fixed by the same structural fact**: `weft_eval.__init__.register()` is the pack's *only* import path, one function, 22 unconditional `registrar.add(...)` calls — there is no second submodule a docstring-only `__init__.py` could leave unimported, because there is no second submodule in the registration path at all. An unknown name still raises the kernel's own `UnknownPluginError` (task 4.1's mechanism, unchanged), naming every registered alternative — proven from outside the repository below, against both `GenerationMetric` and `RetrievalMetric` · **defect 2 (test dummies in production), fixed by omission**: no dummy class ships in `weft_eval`; a test double lives only under `tests/unit/weft_eval/`, and `examples/weft-example-metric`'s own `ExactMatch` (updated for the contract split, `GenerationMetric`/`GenerationSample`) remains the one stranger's metric, never this pack's · **defect 3 (no params), fixed by 4.1's own mechanism, applied 21 times**: every metric declares `config_model`, and it is a real, checkable knob wherever the metric has one — `TopKConfig.k` (IR), `_RougeConfig.use_stemmer`, `JudgeConfig.role` (which `[llm.roles]` answers a judge's questions) and `AnswerCorrectnessConfig.factual_weight` (how much of the correctness score is factual F1 versus semantic similarity) — never a constructor argument only the author knows to pass · **defect 5, the score-arithmetic defect, fixed for all six judges, not the reference's three**: every one of `weft_eval.prompts`'s six output models — `FaithfulnessJudgement`, `ContextRecallJudgement`, `ContextRelevanceJudgement`, `GeneratedQuestions`, `FactualClassification`, `CompletenessJudgement` — carries counts or judgements over discrete items and nowhere for a model to put a ratio; `weft_eval.judges` computes every reported number in Weft's own code. `docs/reference-corrections.md` **C3**'s corrected count (three self-score, three already compute in code) is what this task lifts from: `ContextRelevance` mirrors `ragas_context_relevance.py:117` (a judge-reported relevant-sentence count divided by a code-computed, code-segmented sentence total); `AnswerCorrectness` mirrors `ragas_correctness.py` most closely — the judge returns a full true/false-positive/false-negative confusion-matrix term set and `_f1` derives F1 in code, combined with an embedding-based semantic half by a typed, operator-chosen weight; `AnswerRelevance` mirrors `ragas_answer_relevance.py:150` — the judge is never asked for a number at all, only for candidate questions, and the value is the average cosine similarity between those questions' embeddings and the query's. `Faithfulness`, `ContextRecall` and `AnswerCompleteness` are original to Weft (the reference's three self-scoring judges), built to the identical counts-then-derive shape rather than ported · **the two trailing defects, deliberately flattened into one rule, stated as such**: `.phase4-reference-recon.md` §8 found the reference's two empty-reference defects were shaped differently — `token_recall` returned `1.0` unconditionally, `f1_score` returned `1.0` only when the prediction was *also* empty. Weft does not preserve that difference: `weft_eval.contract`'s own rule is that an empty reference is `NothingToProduce` *unconditionally*, across every metric in the suite, regardless of what the prediction holds — `exact-match` is the one deliberate exception, because an empty prediction against an empty reference is a genuine match, not an absence of anything to compare · **R7, stated precisely**: the reference's `ragas_faithfulness` ran in production through an informal adapter entirely outside its own registry, because the registry path was broken. Weft's `faithfulness` has no broken registry path to route around — it is reachable the same way every other metric is, so there is no adapter to lift and none to build · **dependencies, decided together with 4.7's offline subset**: `rouge-score` (Google Research's own reference implementation) replaces the reference's hand-rolled `O(m·n)` `rouge_l` DP as a real dependency of `weft-eval` — pure Python, no model download, no network call at the `use_stemmer=False` default kept here. `bert-score` is an **optional extra** (`pyproject.toml`'s `[project.optional-dependencies] bertscore`), not a base dependency; `BERT_SCORE_AVAILABLE` derives at import via `importlib.util.find_spec("bert_score")`, the reference's own pattern (`bertscore.py:15`) kept for the *shape*, never a hand-maintained table, and `bertscore` answers `Failed` naming the missing extra when it is absent rather than crashing at import or vanishing from the registry — proven both ways in `tests/unit/weft_eval/test_embedding_metrics.py`. `embedding-similarity`, and the semantic halves of `AnswerRelevance`/`AnswerCorrectness`, need **no new dependency at all**: `weft_eval.embedding_support.embed_texts` resolves `ctx.require(weft_embed.contract.Embedder)` — whatever embedder a run has configured — rather than the reference's `sentence_transformers`, so all three run against `hash` in the gate and against a real provider in production with no code of their own changing. `typings/rouge_score/` and `typings/bert_score/` are real, hand-written type stubs (not a suppression) for two libraries that ship none, letting `pyright` type their return values instead of degrading to `Unknown` · **measured, from outside the repository**: all 18 first-party distributions (unchanged from 4.1 — no new distribution) built to wheels and installed into a throwaway venv; `weft --help` prints unchanged (no CLI surface for either contract ships here, by the scope fence — task 4.6 owns `weft eval`); `weft plugins list` shows `weft-eval: active (28 contributed)`. The failure path, one level below the CLI for the identical scope-fence reason 4.1 gave: `Registry.lookup(GenerationMetric, "faithfulnes")` (a typo) raises `UnknownPluginError` naming all 16 registered `GenerationMetric` names; `Registry.lookup(RetrievalMetric, "precision-at-5")` raises the same, naming all 6 registered `RetrievalMetric` names. `manual/contract-reference.md` regenerated in this commit (24 → 26 contracts: `Metric` replaced by `GenerationMetric` and `RetrievalMetric`). `uv run poe ci-checks` green: **1,589 passed, 1 skipped, 86 architecture tests**; `uv run poe kernel-isolated` green — zero lines under `packages/weft-kernel` · **naming**: the six judges' Weft names were already settled in `docs/10-technique-catalogue.md` §1.3 before this task (`answer-relevance`, `context-relevance`, `faithfulness`, `context-recall`, `answer-correctness`, `answer-completeness` — none carries a `ragas_` prefix; `answer-completeness`'s own row already states why). The 15 IR/traditional names are uncontested textbook metric names with no competing paper claim to adjudicate, so `10` needed no new row for them; `tests/docs/test_technique_naming.py` passes unchanged, and `weft-eval` is **deliberately not added** to that file's own `_AUDITED_DISTRIBUTIONS` — its docstring frames that as "a decision this file should make visibly, in the same commit that adds that distribution's own rows to `10`," and no naming provenance dispute among these 15 forces it now; named here as a stated, visible non-decision rather than a silent gap · **scar, not lifted**: `evaluation/helpers.py`'s four public functions are dead *and* broken — they call an unbound registry class's `.evaluate()` with no `self`, which would raise `TypeError` if ever invoked, and the reference's own type checker was silenced with a committed `# type: ignore[call-arg]` rather than the bug being fixed. Nothing here is lifted from that file · **left to 4.3, 4.6 and 4.7, named rather than silently covered**: the aggregate type — exclusion counts, dispersion across many observations, and the `k`-in-the-**reported**-name check run against a run record rather than only `metric_name` (R5) — is 4.3's; `weft eval run|compare` and every one of these 22 metrics actually reachable through the CLI against a real corpus and a real `LLM`/`Embedder` is 4.6's, unbuilt today by the same scope fence 4.1 named; pricing a full run, pinning providers and model versions, and deciding how a judge declares "needs an LLM" for the offline subset (`.phase4-reference-recon.md` R6: the introspectable signal — does the metric's constructor pull in an `LLM` — exists and is not yet turned into a derived declaration) are 4.7's
- [x] **4.3** a metric's failures are distinguishable from its bad scores, and no reported number stands without the dispersion it was measured with · owner `09` §4, V4 · turns on — · sha `8eb3e22` · **the aggregate half only** (`.phase4-design.md` Finding 1): task 4.1 already carried V4's result shape (`Outcome[MetricScore]`, so a failed metric cannot carry a score); this task is what happens when many of those outcomes, from many samples, fold into one number a human reads. `weft_eval.aggregate` ships `MetricAggregate`, `aggregate()` and `aggregate_report()` — no lines under `packages/weft-kernel` · **exclusion, counted, not merely honoured**: the reference has exactly one aggregator in its whole tree that reads `error` before averaging (`open_rag_evaluator.py:263,271`, `.phase4-reference-recon.md` §5), and even that one reports a *success* count, never an *exclusion* count, leaving a reader to subtract it from a total by hand. `MetricAggregate.excluded` is that count, on the type; `nothing_to_produce` is counted separately, because a legitimate absence and an error are not the same claim — conflating them is the reference's own zero-vs-error accident one level up, at the aggregate rather than the single score · **the dispersion choice, argued**: sample standard deviation, alongside `n`, never an interval — `09` §4's interval language belongs to V3 (a baseline's repeat count spanning a range across repeated *runs*, task 4.8's concern), while V4's dispersion is over *samples within one run*. Stdev uses every observation rather than only two extremes, and pairs with `n` the way a reader needs to judge how much to trust it. At `n == 1`, `stdev` is `None`, never `0.0` — `0.0` would claim a measured, zero spread one observation cannot support, the identical reasoning task 4.1's own ledger entry gives for carrying no dispersion on a single `MetricScore` · **no bare mean, by construction**: `aggregate()`'s only success path returns `Produced[MetricAggregate]`, and `mean`/`n`/`stdev`/`excluded`/`nothing_to_produce` are fields on the one frozen model — there is no function anywhere in the module that hands back a bare `float`, the identical move 4.1 made for `MetricScore`/`error` · **the `k` check runs on the reported name, per R5, not the plugin's own `metric_name` property** — that property was already correct in the reference (`PrecisionAtK`/`RecallAtK`/`NDCG` build `metric_name` from `self.k` correctly, `retrieval/ir_metrics.py:29-30,91-92,230-231`); the defect was one layer up, in `open_rag_fast_track.py:359-364`/`open_rag_ultimate_track.py:514-519` hardcoding the literal report key `'precision_at_k'`/`'recall_at_k'` while the real `k` was a caller-supplied `similarity_top_k` (`open_rag_fast_track.py:299-301`). A check against `PrecisionAtK.metric_name` in isolation would pass on that exact tree. `aggregate()` does not accept a caller-supplied name at all — `MetricAggregate.reported_name` is read off the observations' own `MetricScore.metric_name`, so there is no literal to go stale; `aggregate_report()` goes one step further, refusing via `ReportedNameMismatchError` the moment a report's own key disagrees with what the metric actually computed. `tests/unit/weft_eval/test_aggregate.py::test_aggregate_report_refuses_the_references_hardcoded_report_key_shape` reproduces the reference's exact shape (`{"precision_at_k": [...]}` scoring `metric_name="precision@7"`) and asserts the refusal — the check a property test against `metric_name` alone would never catch, because that property held throughout the reference's own tree · **two new refusals, not name-resolution failures**: `MismatchedMetricNameError` (two `Produced` observations in one `aggregate()` call disagree, e.g. `k=3` mixed with `k=7`) and `ReportedNameMismatchError` (R5's own check). Neither joins `NAME_RESOLUTION_FAMILY` — there is no alternative *name* to offer, only a collision, the exact carve-out `test_ff12_unresolvable_name_carries_options.py`'s own module docstring states for "a class reporting a collision, a malformed shape, or a type mismatch." Both still needed `manual/troubleshooting.md` entries under a new `## Aggregating metric observations — weft_eval.aggregate` section — the coverage ratchet in `tests/docs/test_troubleshooting_coverage.py` is a general `WeftError`-subclass walk, not scoped to the name-resolution family, and it caught the omission on the first `ci-checks` run · **measured, from outside the repository**: all 18 first-party distributions built to wheels and installed into a throwaway venv; `weft --help` and `weft plugins list` unchanged (`weft-eval: active (28 contributed)` — `aggregate.py` registers no plugin, by design, since folding observations into a report is not a capability any pack or third party needs to swap). No `weft eval` command exists yet (4.6's scope fence), so — the identical one-level-below-CLI shape 4.1/4.2 used for their own failure-path demonstrations — against the installed wheel: `aggregate()` on `[precision@7=1.0, precision@7=0.5, Failed]` produced `MetricAggregate(reported_name='precision@7', mean=0.75, n=2, stdev=0.3535533905932738, excluded=1, nothing_to_produce=0)`; a single observation produced `stdev=None`; and `aggregate_report({"precision_at_k": [precision@7 scores]})` raised `ReportedNameMismatchError: report key 'precision_at_k' does not match the name this metric computed, 'precision@7' — a report's key must be the name the metric itself reports for what it measured, never a caller-chosen label maintained by hand`. `uv run poe ci-checks` green: **1,596 passed, 1 skipped, 86 architecture tests**; `uv run poe kernel-isolated` green — zero lines under `packages/weft-kernel` · **left to 4.4/4.6/4.7, named rather than silently covered**: persisting a run that actually calls `aggregate()`/`aggregate_report()` over real per-sample outcomes and writes the result to a run record is 4.4's; rendering an aggregate report to an operator through `weft eval run|compare` is 4.6's, unbuilt today by the same scope fence 4.1/4.2 named; which metrics' dispersion is even reachable offline, and pricing a run that computes it, are 4.7's
- [x] **4.4** a run is persisted carrying its resolved pipeline, corpus identity, model versions and the active distribution set, so two runs can be diffed after the fact · owner `01` → Phase 4 **Exit**; `01` → *Fitness functions* 8(c) · turns on FF8(c) · sha `da3b84c` · **Q1 settled, argued rather than merely followed**: a run record is a **file**, written by `weft-eval` — `weft_eval.run_record.RunRecord`, `build_run_record`, `write_run_record`/`load_run_record` — never the store, because G4 fixes a store's contract at vectors and a run record is not a `Node`; forcing one through `Node` to get it persisted would shape evaluation knowledge to a contract built for retrieval rather than the other way round. **Zero lines under `packages/weft-kernel`** — D1's forcing function does not apply; the whole of this task fit inside the pack D1 already assigned it to · **four fields, and no more, each argued in the module's own docstring**: `resolved_pipeline` is `weft_kernel.resolution.ResolvedPipeline` itself, reused rather than a second, weft-eval-shaped copy of the same information — task 4.0 exists because of this task (before it, `weft index` named its four stages in Python and there was no resolved pipeline to persist); `corpus` is `CorpusIdentity`, a name plus a content-derived sha256 digest built by `corpus_identity()` the identical way `eval/run_baseline.py`'s own `corpus_id()` already does for V3's baseline — order-independent, so layout never moves it and one document changing always does; `model_versions` is taken as given, never derived — `weft-eval` has no way to observe what an `Embedder`/`LLM` role resolved to at run time, only whoever drove the pipeline does; `active_distributions` is `active_distribution_set(reports)` — every `weft_kernel.discovery.PackReport` marked `PackStatus.ACTIVE`, sorted, FF8(c)'s own left-hand side · **how 8(c)'s equality is checked, and proven not vacuous**: `tests/architecture/test_ff8_trust_model.py::test_run_record_active_distributions_equal_what_plugins_doctor_reports` runs real, wide-open `discover()` against the actual installed environment and compares `active_distribution_set`'s output against text parsed out of `weft_cli.plugins_report.render_doctor`'s own rendered block for the identical `PackReport` tuple — the function `weft plugins doctor` itself calls — never against a second copy of the same filter, which would prove nothing. A second test, `test_the_equality_check_is_not_vacuous`, manufactures the exact drift the clause exists to catch: a plausible-looking alternative filter (`contributed > 0` instead of `status is PackStatus.ACTIVE`) that wrongly admits a `PARTIAL` pack and disagrees with what `render_doctor` reports. Proven for real during development, not merely asserted: `active_distribution_set`'s filter was temporarily swapped to `contributed > 0` and both clause-(c) tests failed with a concrete set mismatch (`'weft-chunk' != 'weft-canary'`, `('weft-half', 'weft-real') == ('weft-real',)` failing) before the fix was reverted and both passed again · **FF0**: no new poe task needed — `arch = "pytest tests/architecture -q"` already runs every file under the directory and is already in `ci-checks`'s sequence, so the two new tests in the existing `test_ff8_trust_model.py` are reachable from the gate with no `pyproject.toml` edit · module docstring's clause (c) paragraph added, describing the same equality and its two tests · **measured, from outside the repository**: all 18 first-party distributions built to wheels and installed into a throwaway venv (Python 3.12.12, since a bare `python3 -m venv` on this machine defaults to 3.9 and every package now requires `>=3.12` — noted since it cost a retry); run from a directory that is not this checkout. `weft --help` unchanged; `weft plugins list` shows `weft-eval: active (28 contributed)` alongside 13 other `active` distributions and `weft-store: failed (0 contributed)` (missing `dsn`, pre-existing and unrelated to this task); `weft plugins doctor`'s tail names the same failure. One level below the CLI, the identical scope-fence shape 4.1–4.3 used (no `weft eval` command exists yet — 4.6's scope fence): against the installed wheel, `build_run_record(...)` over the real `discover()` report set produced `active_distributions = ('weft-chunk', 'weft-clean', 'weft-cli', 'weft-embed', 'weft-enhance', 'weft-eval', 'weft-extract', 'weft-generate', 'weft-index', 'weft-llm', 'weft-openai', 'weft-pdf', 'weft-qdrant', 'weft-retrieve')` — 14 of the 15 installed distributions, `weft-store` correctly excluded because it is `failed`, not `active`, matching `plugins list` exactly; `write_run_record`/`load_run_record` round-tripped a 944-byte JSON file byte-for-byte equal to the built record. Two failure paths, both real: `load_run_record(Path("does-not-exist.json"))` raised `FileNotFoundError: [Errno 2] No such file or directory: 'does-not-exist.json'`; a hand-written run-record file missing `corpus` entirely raised `pydantic.ValidationError: 1 validation error for RunRecord\ncorpus\n  Field required`. `weft index ./does-not-exist --pipeline does-not-exist` (unrelated to this task, run to confirm the binary as a whole is unaffected) exited `4`, naming the three pipelines the catalogue holds. No artefact left in the repository — every wheel, venv and written file lived under `/tmp`. `uv run poe ci-checks` green: **1,603 passed, 1 skipped, 88 architecture tests**; `uv run poe kernel-isolated` green · **left to 4.6/4.7/4.8/4.9, named rather than silently covered**: no `weft eval run|compare` or `weft trace` ships here — 4.6 is what calls `build_run_record`/`write_run_record` from a real command and decides Q2 (whether `weft trace` reads this record or exported OTel spans; this record's own shape, one `ResolvedPipeline` plus three flat fields, is written so either answer stays possible); diffing two records — the comparison itself — is 4.6's `weft eval compare` and 4.9's two-pipeline exit demonstration, not attempted here; which model versions a real run supplies, and pricing one, are 4.7's; the published baseline being one of these persisted runs, replacing `eval/run_baseline.py`'s own hand-rolled `BaselineRun`, is 4.8's — `corpus_identity()` is built to the identical recipe that file's `corpus_id()` already uses specifically so 4.8 has one digest convention to adopt, not two to reconcile
- [x] **4.5** a stage's duration and attribution are visible in a trace without any pack exporting a span by hand · owner `01` → *The kernel boundary* (exporters are packs); `06` step 3 · turns on — · sha `322ee08` · **the finding: this was already true, and the kernel needed zero new lines** — `.phase4-design.md`'s own framing ("budgeted, small, and already half-built in `seam.py`") undersold what task 0.3, 2.28, 2.34, 2.36 and 3.2/3.4 had already built there: every stage's `run()` and `flush()` already passes through `weft_kernel.seam.wrap`/`wrap_flush`, which opens a span named for the resolved `StageSpec.id`, sets `weft.pack`/`weft.contract`/`weft.plugin` on it unconditionally, and lets any exception propagate out of `_tracer.start_as_current_span(...)`'s own `with` block. Read at source (`.venv/lib/python3.12/site-packages/opentelemetry/trace/__init__.py`): that propagation path is `opentelemetry.trace.use_span`, called with its own defaults (`record_exception=True, set_status_on_exception=True`) by **both** the no-op API tracer and a real SDK `Tracer.start_as_current_span` — so duration (a span's own start/end timestamps), attribution (the four seam-set attributes, plus the span's own name) and "why" (the exception recorded as a span event, `ERROR` status set with its message as the description) are already produced by `opentelemetry-api` alone, the instant something outside the kernel configures a provider and an exporter. `CancelledError` is a `BaseException`; `use_span`'s own `except Exception` clause does not catch it, so it ends the span without recording it as a failure — CLAUDE.md's rule holding against a *real* exporter, not only the hand-rolled tracer double `test_seam.py` uses (that file's own docstring states why it deliberately avoids the SDK) · **where the recorder lives, and why not a pack**: `tests/unit/weft_kernel/test_seam_trace_visibility.py`, five tests, using a real `opentelemetry.sdk.trace.TracerProvider` + `InMemorySpanExporter` — `opentelemetry-sdk` added to root `pyproject.toml`'s dev-only `dependency-groups`, never to any shipped distribution (`uv sync`: `+ opentelemetry-sdk==1.44.0`). Phase 4 ships no exporter pack: task 4.6's `weft trace` reads the run record task 4.4 persists, not OTel spans (`.phase4-design.md` §3, Q2), so there is no pack home yet for a real, SDK-configured `TracerProvider` — a test fixture standing in for whatever such a pack eventually does is where this demonstration belongs today, named as such in that file's own docstring · **what the five tests prove, each against a real exported `ReadableSpan`, not the double**: a successful stage's span carries a positive duration and the three `weft.*` attributes; a failed stage's span is named for the stage, carries `StatusCode.ERROR` with the failure's message as its description, and records an `exception` event — "which stage and why" with no pack ever naming either; `CancelledError` ends its span with `StatusCode.UNSET` and no recorded event; `wrap_flush` produces its own named span; and — the one property no earlier test exercised — two stages run one after another **land in a single trace**: `weft_cli.cli.run_command` already wraps a whole `Command` invocation through the same `seam.wrap` (`stage=f"command:{command_name}"`, `guard_blocking_calls=False`) before calling into `Runner`, and because `_run_one_batch` walks its stages with a plain sequential `await` — never `asyncio.create_task` — `opentelemetry-api`'s own `contextvars`-based propagation nests every stage span as a child of that command span automatically, with no pack aware a parent exists. Reproduced with two bare `wrap()` calls nested the identical way, confirming this is `opentelemetry-api` doing the work, not something `weft_cli` adds · **measured kernel line delta: 2,891 → 2,891, zero.** `git status` after this task touches `pyproject.toml` (the dev-only SDK dependency) and one new test file under `tests/unit/weft_kernel/`; nothing under `packages/weft-kernel/src` changed, confirmed by `_count_kernel_lines()` before and after. D1's forcing function does not apply — the seam-local work Phase 4 was permitted to do for 4.5 turned out to already exist · **run through the shipped binary, from outside the repository**: all 17 first-party distributions built to wheels and installed into a throwaway venv (the identical technique `test_phase3_exit_command_surface.py` and `test_ff9c` already use), then run from a project directory that is not this checkout. `weft --help` lists every command unchanged. Failure paths: `weft index ./corpus --pipeline does-not-exist` → exit `4`, naming the three pipelines the catalogue holds; `weft index ./corpus --extract text --pipeline index` → exit `1`, naming both flags; `weft index ./corpus` with `[services] store = "pgvector"` but no `dsn` configured → exit `4`, `PgVectorSettings` naming the missing field. A real stage failure, live: `[services] store = "qdrant"` pointed at an unreachable `http://127.0.0.1:1` prints `'store' failed: All connection attempts failed` and exits `1` — exactly the `f"'{stage_label}' failed: {exc}"` shape `wrap` produces, naming the stage and the underlying reason with no code path written for this demonstration. `uv run poe ci-checks` green: **1,532 passed, 1 skipped, 85 architecture tests** · **left to 4.6 and beyond, named rather than silently covered**: no exporter pack ships in this phase, so nothing here wires a real trace out of a live `weft` run — 4.6's `weft trace` reads 4.4's persisted run record instead, by design (Q2), and that choice is unaffected by today's finding that the seam already emits everything a future exporter pack would need for free. Nothing attaches `Context.run_id`/`trace_id` to a span or a `Resource` — the seam's `wrap` never sees a `Context` typed as such (it wraps a bare callable), so correlating one operator-visible trace with one Weft run is a pack's concern once an exporter exists, not attempted here and not needed for 4.6's own answer to Q2.
- [x] **4.6** `weft eval run|compare` and `weft trace` let an operator ask what a run actually did · owner `03` → *Command surface* · turns on — · sha `c8da037` · **three new `Command`s, registered exactly as every built-in already is** — `weft_cli.eval_commands.EvalRunCommand`/`EvalCompareCommand`/`TraceCommand`, wired through `weft_cli.commands.register`'s single entry point (`register_eval_commands`, composed in beside `register_pipeline_commands`/`register_config_commands`, never a fourth entry point) — closing `docs/03-cli.md`:246's own "`/eval` has no owner yet: no `weft eval` command is registered anywhere in this repository" note, corrected in this same commit · **Q2, settled and argued, restating and closing what 4.4/4.5's own ledger entries had already concluded**: `weft trace` reads the **persisted run record** task 4.4 built, never exported OTel spans. `01` → *The kernel boundary* fixes exporting a span as a pack's job; Phase 4 ships no exporter pack (4.5's own finding: the seam already emits everything a future exporter would need, for free, the instant one exists); reading spans would mean shipping an exporter pack as a second, unbudgeted artefact this phase never planned for. **The cost of that answer is a narrowing, made explicit rather than left for a reader to notice**: `docs/03-cli.md`'s published `weft trace [<run-id>]` promised "replay what a run actually did" — language that fits a span-level replay (which stage, how long, why it failed) far better than four static facts. `weft trace` here prints exactly what `weft_eval.run_record.RunRecord` carries — resolved pipeline, corpus identity, model versions, active distribution set — and nothing about per-stage timing or attribution, because nothing in this tree persists that. `docs/03-cli.md` → *Command surface* is corrected in this commit (a new blockquote states the narrowing and the argument in full, and the code block itself drops the promise-language), and `docs/02-extension-model.md`'s identical "`weft trace` claims to replay what a run actually did" is corrected alongside it — the standing rule against a control document that paraphrases a capability it does not have, applied to two documents that both made the same claim · **`weft trace <run-id>` also loses its brackets — a required positional, not an optional one, and that is mechanical, not a design retreat.** `weft_cli.argparse_gen`'s own floor turns a defaulted field into a flag, never an optional positional (`ConfigGetArgs.key` already established this for `weft config get [--key]`); and there is no honest fallback to invent for "no id given" — a bare `weft trace` process has no session and no "last run" of its own the way the REPL's own `/trace` does to fall back to. `weft_cli.pipeline_commands`'s own declined-to-invent-a-grammar precedent (`derive`'s four operator shapes) is the same discipline applied here · **`weft eval run <path> <pipeline>` makes `pipeline` a second required positional, never `weft index`'s optional `--pipeline` flag.** A run record's `resolved_pipeline` field is mandatory (`RunRecord`'s own "four fields, and no more"), and only a *named* pipeline document produces a `ResolvedPipeline` at all — the default four-stage `weft index` path builds its `StageSpec`s as Python constants and never calls `resolve()` (task 4.0's own reason to exist), so there is no resolved form to persist regardless of whether a caller asks for one. Per `argparse_gen`'s own mechanical rule, a value with no honest default is spelled as a second positional, `PipelineDeriveArgs`'s own `<parent> <name>` shape · **`weft eval run` reuses `weft_cli.ingest.run_index` unchanged rather than re-deriving pipeline resolution or extraction** — `IndexResult` grew two fields this task needed and `run_index` already computed and discarded: `resolved_pipeline` (`None` on the default four-stage path, honestly — that path has none) and `document_ids` (every `SourceDoc.source_id` actually discovered, `weft_eval.run_record.corpus_identity`'s own input, so no caller re-walks the directory a second time) · **`model_versions` is `{}` today, named as a gap rather than filled dishonestly.** `--pipeline` never reads `[services]` at all (task 4.0's own Q3), so `deps.services.embed` is not even the plugin a named-pipeline run actually used — stamping it in anyway would be exactly the wrong, misleading value V3's own failure clause warns against ("a baseline from a different corpus, pipeline or **model version**"). Which providers and model versions a real run pins is task **4.7**'s own job (`09` §4, V5), not invented here to make this task's record look more complete than it is · **`weft eval compare` refuses outright, rather than answering, when the two runs are not apples to apples — `09-release.md` §4's V3 failure clause, enforced at the CLI seam before a pipeline diff is ever computed.** `EvalCompareCommand` checks `corpus`/`model_versions`/`active_distributions` for exact equality first and raises `IncomparableRunsError`, naming which facts differ, rather than silently reporting a diff that is true but not the fact a caller is actually asking about (CLAUDE.md: "a silent fallback is worse than a failure") — `weft_eval.run_record`'s own module docstring gives the identical reason for the active-distribution-set clause specifically ("`weft eval compare` across two pipelines is meaningless if the installed pack set differed between them"), checked here at fitness function 8(c)'s first real caller. When all three agree, `weft_cli.pipeline_diff.diff_resolved` — already proven exact by `weft pipeline diff` (task 3.7) — is reused unchanged for the pipeline half, via a `_pipeline_diff_lines` helper `weft_cli.render` now shares between `weft pipeline diff` and `weft eval compare` rather than a second, independently-drifting formatter · **Run ids are filenames.** `runs/`, a project-local, cwd-relative directory on `DEFAULT_PIPELINES_DIR`'s own footing (no new `weft.toml` key); `weft eval run` mints one with `uuid.uuid4()` (the same generator `weft_cli.cli._context()` already uses for `Context.run_id`/`trace_id`) and writes `runs/<id>.json` through `write_run_record` unchanged. `weft eval compare`/`weft trace` refuse an id nothing persisted with `UnknownRunIdError`, naming every id that does exist — `01` requirement 5's rule, fitness function 12's family (`NAME_RESOLUTION_FAMILY` grows by one; `manual/troubleshooting.md` gains its entry) — mapped to exit **4** via a **local import inside `exit_code_for`**, `weft_cli.route_ask.NoRouterPipelineError`'s own established shape, because `weft_cli.eval_commands` pulls in `weft_cli.ingest`'s heavier import chain (`weft-extract`/`weft-chunk`/`weft-embed`/`weft-store`) and `exit_codes.py` is imported at `cli.py`'s own module scope, unconditionally, for `weft --version` too — adding it to the plain `_ALSO_RESOLUTION_FAILED` tuple would have cost `--version` that whole chain, exactly the regression `NoRouterPipelineError`'s own paragraph already refuses one caller up · **`EmptyCorpusError`/`IncomparableRunsError` are certain answers, not policy questions** — `OPERATION_FAILED` (1), `TargetAlreadyExistsError`/`ConflictingAskModeError`'s own footing — `weft eval run` over a directory with nothing for the named pipeline's extractor to read refuses rather than persisting a record with an empty, indistinguishable-from-any-other-empty-corpus digest (an empty `weft index` directory stays a silent, successful no-op — this is a deliberate difference, argued in `eval_commands`'s own module docstring) · **Permission classes, decided rather than defaulted.** `eval run` is `write` — it indexes a corpus and writes a file, `docs/03-cli.md`'s own `write`-row example ("index into a new collection"); never `overwrite`, because a run id is a fresh `uuid4` every call and there is nothing an invocation could ever collide with to ask a TTY about. `eval compare`/`trace` are `read` — both only load files already on disk. **No command in this module is `overwrite`/`destroy`-class**, holding the same property `docs/03-cli.md` → *Permissions* already records for every first-party command since the 2026-08-20 repair · **`/eval` in the REPL: reachable bare, deferred as a slash alias, for a different reason than before.** A bare, non-slash line already reaches all three new commands inside a session (`eval run <path> <pipeline>`, `eval compare <a> <b>`, `trace <run-id>`) through the identical registry-driven grammar every other command uses — nothing in `weft_cli.repl` needed to change for that. The slash alias stays deferred: `/plugins`/`/config` each alias to one command needing at most one bare argument; `/eval` would have to multiplex between two verbs each needing two required positional arguments, genuinely more than either precedent's one-line `parser.parse_args([...])` call — named as small, separable, unbuilt REPL-layer work, `_DEFERRED_SLASH_COMMANDS["eval"]`'s reason text updated accordingly, `docs/03-cli.md` → *In-session commands* corrected in the same commit · **A real composition bug, found running the binary and not by 1,616 green tests, fixed in this commit.** `weft eval run corpus specific` (`specific` a `weft pipeline derive`d child of `index`, same corpus as an earlier `index` run) failed `UnknownParentPipelineError` outright: `weft_cli.ingest._specs_from_document` (task 4.0) and `weft_cli.route_ask._run_pipeline` (task 2.8) both called `contracts_for`/`resolve` with `parents={document.name: document}` — a one-entry mapping holding only the named document, with no ancestor for `extends:` to find — rather than the full catalogue `weft_cli.pipeline_commands._resolved_or_refuse` (task 3.7) already passes correctly. Neither earlier task's own tests ever exercised `extends:` through either path (`test_ingest.py`'s `pipeline=` tests, `test_route_ask.py`'s `run_named_ask`, both used flat, non-derived documents only), so nothing caught it until a real corpus ran through a real derived pipeline — precisely 4.9's own exit shape, and precisely why this task built one to check before declaring itself done. Fixed in both places: `_specs_from_document` and `_run_pipeline` (which grew a `catalogue` parameter, threaded through its three call sites) now pass the full catalogue as `parents`. Regression tests added directly against the defect: `test_ingest.py`'s existing `pipeline=`/`with:` test gained `resolved_pipeline`/`document_ids` assertions; `test_route_ask.py` gained `test_run_named_ask_resolves_a_derived_pipeline`, a project-local `base.yaml`/`derived.yaml` pair proving `weft ask --pipeline <derived-name>` and `weft index --pipeline <derived-name>` — not only `weft eval run` — resolve derived pipelines correctly now, where before this task they silently could not, in the whole tree, ever · **Measured, from outside the repository.** All 18 first-party distributions built to wheels (Python 3.12.12, the identical throwaway-venv technique 4.4/4.5 already used) and installed into a project directory that is not this checkout, against the real `compose.yaml` Postgres+pgvector container. `weft --help` prints help and lists `eval`/`trace` among the other subcommands, still not the REPL. `weft init` → `weft pipeline derive index specific` → `weft eval run corpus-a index` → `weft eval run corpus-a specific` (the derived pipeline, same corpus) → `weft eval compare <run-a> <run-b>` prints `'index' and 'specific' resolve identically.` (both derive from the identical four stages, so the pipeline diff is honestly empty; the environment-match line above it confirms corpus/model-versions/active-distributions all agreed) — the exact shape 4.9's exit demonstration needs, proven reachable here rather than assumed. Failure paths, all real: `weft trace does-not-exist` → exit `4`, naming every run id that does exist (empty, on a fresh `runs/`); `weft eval compare <run> does-not-exist` → exit `4`, identical; `weft eval compare` across two runs from different corpora (`corpus-a` vs `corpus-b`) → exit `1`, naming `corpus differs (...)` and refusing to compute a pipeline diff at all; `weft eval run empty index` (a genuinely empty directory) → exit `1`, `EmptyCorpusError` naming the path and the pipeline, no `runs/` file written; `weft eval run corpus-a ghost-pipeline` → exit `4`, listing every pipeline the catalogue holds; `weft eval run corpus-a` (missing the `pipeline` positional) → exit `2`, argparse's own usage error. `uv run poe ci-checks` green: **1,616 passed, 1 skipped, 88 architecture tests**; `uv run poe kernel-isolated` green. **Kernel line delta: zero** — `git diff --stat packages/weft-kernel` is empty, confirmed both before and after the route_ask/ingest repair. `manual/user-manual.md`'s generated command table regenerated (`uv run python scripts/generate_command_table.py`, 15 commands now, `eval compare`/`eval run`/`trace` among them); `manual/contract-reference.md` regenerated too and came back byte-identical — no new contract published, only new implementations of `Command`, an existing one. No artefact left in the repository — every wheel, venv and written file lived under a scratch directory, deleted after · **left to 4.7/4.8/4.9/4.10, named rather than silently covered**: which providers and model versions a real run pins, and pricing one, are 4.7's (`model_versions` stays `{}` until then); the published baseline becoming one of these persisted runs, replacing `eval/run_baseline.py`'s own hand-rolled `BaselineRun`, is 4.8's; running one corpus through two *actually different* derived pipelines and publishing the comparison as the phase Exit is 4.9's — build to be used, per the task brief, and today's own demonstration (two pipelines that happen to resolve identically) is the mechanism proven, not the exit itself; the operations guide's own coverage of persisted runs and `weft trace` is 4.10's. **One further gap, not owned by any task name yet, flagged rather than silently left**: `01`:725-730 and `09-release.md`'s own Phase 6 Exit language describe a future `weft eval compare` reporting "every metric inside the interval" a baseline recorded — `RunRecord` carries no metric scores at all (4.4's own "four fields, and no more" is a settled constraint this task did not reopen), so today's `eval compare` diffs pipelines and environment only. Whichever task first attaches a computed metric report to a run — Phase 6's own exit, most likely — will need either a fifth `RunRecord` field or a sibling artefact `weft eval compare` also reads; neither is designed here.
- [x] **4.7** one full run can be priced in money and wall-clock, its providers and model versions are pinned, and a deterministic subset runs in the gate with no credentials and no network · owner `09` §4, V5 · turns on — · sha `d258508` · **Q6, settled: `GenerationMetric`/`RetrievalMetric` extend `Command`'s own mechanism (`required_declarations`), never a second one.** Task 3.1 already generalised `destroys`'s mandatory-declaration check into `weft_kernel.registry._required_declarations`/`_require_declarations_present`, reading `contract.required_declarations` off any contract that sets it — `Command.required_declarations = ("permission_class", "help")` is the working precedent. `weft_eval.contract` sets `GenerationMetric.required_declarations = RetrievalMetric.required_declarations = ("runs_in_gate",)`: a metric that never states `runs_in_gate: ClassVar[bool]` fails to *register* — `MissingRequiredDeclarationError`, the identical error a `Command` with no `permission_class` already raises — built-in or a stranger's alike (`examples/weft-example-metric`'s own `ExactMatch` needed the declaration added in this commit, caught by `test_ff9c_every_contract_has_a_stranger.py`, not guessed at). **Zero kernel lines** — the mechanism already existed; only two contracts opted in. An optional, defensively-read `gate_unsafe_reason: ClassVar[str]` — `intact`'s own "convention, not seam" footing — lets a `False` metric say *why* and *what would permit it*; `bertscore` names the missing extra, the six judges name `[llm.roles]`. `weft_eval/offline.py` is the reading half: `gate_subset(registry)` derives the partition off `registry.names_for`/`unwrap_factory`, never a second hand-maintained list, generalising to any stranger's own metric on the identical footing `Registry.names_for`'s own docstring already argues for existing at all · **All 22 metric classes (21 reference + task 4.1's demonstration) declare it**: 15 `True` (4 IR + 11 traditional, `embedding-similarity` included — it scores through whatever `Embedder` a run has configured, `hash` for the gate, proven against the real `HashEmbedder` by `test_embedding_metrics.py` since task 4.2, never a stub) and 7 `False` (the 6 LLM judges plus `bertscore`) — measured directly by `test_offline.py`'s own count assertion against the real, registered suite · **The offline subset is identifiable as a subset: `weft eval metrics [--name <name>]`**, a fourth `EvalCommand`, `read`-class, registered exactly like every other built-in. No name lists everything; a name asks a narrower, different question and **refuses** — never a degraded or empty answer — for a metric that cannot run, via `weft_eval.offline.require_gate_safe`/`MetricNeedsCredentialsError` (`OPERATION_FAILED`, not a name-resolution failure — the name was valid) or `UnknownMetricNameError` (a new `NAME_RESOLUTION_FAMILY` member, `RESOLUTION_FAILED` via the identical local-import shape `UnknownRunIdError` already uses in `exit_codes.py`, so `weft --version` never pays for `weft_eval`'s heavier import chain) · **A real defect found only by running the binary, not by the unit tests, fixed in this commit — exactly CLAUDE.md's own measured claim.** `EvalMetricsArgs.name: str | None = None` has a default, so `weft_cli.argparse_gen`'s own mechanical floor makes it `--name`, not the positional `weft eval metrics <name>` this task's own first draft of `docs/03-cli.md` and the module docstring wrote; every `EvalMetricsCommand` unit test called `EvalMetricsArgs(name=...)` directly and passed regardless, proving nothing about the CLI grammar. Caught only once `weft eval metrics faithfulness` printed argparse's `unrecognized arguments` and exit `2` from a real installed binary — corrected to `--name` everywhere (`03`, the module docstring, `manual/troubleshooting.md`, `manual/operations-guide.md`) before this task could claim done · **Money: `weft_llm.payload.Completion` gained `TokenUsage` (`prompt_tokens`, `completion_tokens`), populated by `weft_openai.llm.OpenAILLMProvider` from the vendor's own response `usage` field (a `ChatCompletionUsage` Protocol added to the pack's own declared-shape response types, never `openai`'s SDK type imported directly — the same "declared as the shape it calls" discipline the rest of that file already holds), and left `None` by `weft_llm.scripted.ScriptedProvider` — honestly: nothing was really called, so there is nothing to price, the identical honesty `HashEmbedder` already states about its own vectors. `weft_eval.pricing.price_calls` folds many `PricedCall`s into one `RunPrice` against a `rates: Mapping[str, TokenRate]` parameter — `DEFAULT_RATES` is the shipped default, never consulted by name inside the function body, so a caller with current numbers substitutes their own without a package edit, the identical "configuration, not a closed key space" argument `weft_eval.at_threshold`'s own module docstring already makes for a metric's tunables. **Staleness surfaces because it travels on the answer**: `RunPrice.rates_as_of` (from `RATES_AS_OF`, or a caller's own dated override) sits beside `total_usd` on every `RunPrice`, never a bare total presented as current. **Excluded, counted, never priced at zero** — a call whose model has no rate entry is dropped from `total_usd` and named in `unpriced_calls`/`unpriced_models`, `weft_eval.aggregate`'s own "excluded, counted rather than merely honoured" shape applied to money instead of a score, argued in `pricing.py`'s own module docstring against the identical reference gap `aggregate.py` already named for scores. **Left honestly incomplete, named rather than faked**: threading `usage` through `weft_prompts.cascade.execute`'s three tiers into a metric's own `evaluate()` call is not done here — no per-sample judge-scoring loop exists anywhere in this tree yet (that is 4.9's), so there is no live call site to thread it to; `Completion.usage` is the contained, real, immediately-useful half (already exercised by `weft ask`'s own generation path once a real provider answers), and wiring it through the cascade is a bounded, obvious follow-on once 4.9 gives it a caller · **Wall-clock and model-version pinning, both live on `weft eval run` today**, the one real, executable "run" in this tree — measured, not estimated. `EvalRunCommandResult.wall_clock_seconds` is `time.monotonic()` around `run_index`'s own real work, printed by `weft_cli.render._render_eval_run`. `RunRecord.model_versions` — `{}` since 4.6, named there as this task's own gap — is now `weft_cli.eval_commands._model_versions(resolved_pipeline)`: every resolved stage whose plugin's own `config` (a `BaseModel` instance or an empty mapping, `weft_kernel.resolution.StageConfig`'s two shapes, both read generically) carries a `model` field contributes `"<stage>": "<plugin>:<model>"` — `hash` and `pgvector` contribute nothing, honestly, because neither declares one; `OpenAIEmbedderConfig.model` would, proven by a fake modelled embedder in `test_eval_commands.py` since this sandbox holds no real OpenAI credential to prove it end-to-end against the vendor · **Measured, from outside the repository, against the real `compose.yaml` Postgres container.** All 18 first-party distributions built to wheels (Python 3.12.12, the throwaway-venv technique 4.4/4.5/4.6 already used) and installed into a project directory that is not this checkout. `weft --help` and `weft eval --help` list `eval metrics` among the others. `weft init` → `weft eval run corpus index` (real `hash`+`pgvector` indexing against `docker compose`'s own Postgres, port 5433) → `run <id> persisted (...) wall clock: 0.03s.`, exit `0`; `weft trace <id>` prints `model versions: (none recorded)`, honest for an all-`hash` pipeline. `weft eval metrics` (no name) prints the full, live partition: 15 gate-safe (`accuracy, embedding-similarity, exact-match, f1-score, key-terms-precision, mean-average-precision, ndcg, overlap-at-threshold, precision-at-k, recall-at-k, rouge-1, rouge-2, rouge-l, token-overlap, token-recall`), 7 not (`answer-completeness, answer-correctness, answer-relevance, bertscore, context-recall, context-relevance, faithfulness`). Failure paths, all real, from the same installed binary: `weft eval metrics --name faithfulness` → exit `1`, prints `'faithfulness' cannot run in the deterministic, gate-safe subset: needs a real judge model behind '[llm.roles]' — the deterministic 'scripted' provider resolves the service but cannot produce a usable structured judgement, so this metric is excluded from the gate's offline subset regardless of whether an operator configures a role for it. Configure '[llm.roles]' to map this metric's role (default 'grade') to a real provider such as 'openai' to run it outside the gate.` — the credential-less refusal this task exists to prove, read exactly as a user would meet it, with no credential and no network anywhere in the process; `weft eval metrics --name bertscore` → exit `1`, names the missing `bert_score` extra; `weft eval metrics --name does-not-exist` → exit `4`, lists all 22 registered names; `weft eval compare` across two differently-named corpora over the identical documents → exit `1`, `IncomparableRunsError` naming the corpus difference, unaffected by this task. `uv run poe ci-checks` green: **1,636 passed, 1 skipped, 88 architecture tests**; `uv run poe kernel-isolated` green. **Kernel line delta: zero** — `git diff --stat packages/weft-kernel` is empty · **left to 4.8/4.9/4.10, named rather than silently covered**: the published baseline becoming one of these persisted runs is 4.8's; threading `Completion.usage` through `weft_prompts.cascade` into a real per-sample judge-scoring loop, and `RunRecord` carrying per-metric aggregates, are 4.9's exit-path work (`.phase4-design.md` §7's gap, unchanged by this task, and nothing here makes it harder — `MetricScore`'s own two-field shape is untouched); a live, credentialed demonstration of `model_versions` pinning a real vendor model end to end, and of a nonzero `RunPrice`, needs an account this sandbox does not carry and is left to whoever runs 4.9 or 4.8 with one; the operations guide's own coverage of persisted runs and `weft trace` beyond this task's own V5 section is 4.10's.
- [x] **4.8** the published baseline is a persisted, reproducible run rather than terminal output · owner `09` §4, V6 · turns on — · sha `3434179` · **the published run record is `eval/run_baseline.py`'s own `BaselineReport.record`, a real `weft_eval.run_record.RunRecord` — the identical type `weft eval run`/`weft eval compare`/`weft trace` read — never a second, hand-shaped copy of the same four facts.** `BaselineRun`/`CorpusRecord`/`DistributionRecord`/`StageRecord` and their own `corpus_id()`/`pipeline_digest()`/`active_distributions()` are deleted; `check_baseline.py`'s `comparable()` compares `record.corpus`/`record.resolved_pipeline`/`record.model_versions` directly (`ResolvedPipeline`'s own docstring: "two resolutions of the same document are comparable by `==`"), never a digest this module computed a second way · **the record is assembled in this harness's own process, not read back from `weft eval run`'s subprocess output — argued, not merely chosen.** `weft eval run` (4.6) is real and could have been shelled out to, but its own `corpus_identity` call hashes `IndexResult.document_ids` — resolved *filesystem paths* under whatever directory a run happened to stage its corpus in — which is a fact about where a machine put the files, not about their bytes; two byte-identical corpora staged under two different working directories (a stranger's checkout, say) would be handed two different digests, breaking exactly the reproducibility V6 exists to prove. `weft_eval.run_record.corpus_identity`'s own docstring says it "does not care" what a document id is, only that the same set always produces the same digest — a caller's choice, not a defect — and this harness already had a content-derived one: `corpus/manifest.toml`'s own sha256, the identical recipe `eval/run_baseline.py`'s old `corpus_id()` used, which is why 4.4's entry built `corpus_identity()` to match it. `build_baseline_record()` resolves the pipeline document and discovers the active distribution set **synchronously, in this process** — `weft_kernel.resolution.resolve`, `weft_cli.compile.contracts_for`, `weft_cli.registry_bootstrap.build_dependencies` are all plain `def`s operating on already-parsed data, never I/O — so this needs no second `asyncio.run` (fitness function 7(a): `eval/` still gets exactly zero), and the record it builds describes what the `weft index --pipeline` subprocess call immediately before it actually ran, over the same `weft.toml` and pipeline document that subprocess reads · **a real, structural finding from running the binary, not guessed at**: `weft-openai` registers its one client under the literal name `"openai"` for *both* `Embedder` and `LLMProvider` (`packages/weft-openai/src/weft_openai/__init__.py`); a pipeline **document**'s bare `use: openai` cannot say which contract it means, and `weft_cli.compile.contracts_for` — which must infer a stage's contract from the registry, since a document names no contract (G1) — refuses with `AmbiguousStageContractError` rather than guess. That module's own docstring already calls this an accepted cost with no operator remedy ("the only remedy is a rename inside a distribution that is not theirs"), so this task does not attempt one — renaming would also break `[services] embed = "openai"`'s own existing convention, a far larger footprint than this task's. `[services] embed = "openai"` is itself unaffected (it supplies `Embedder` as the contract directly and never asks the registry to infer it), so the collision is specific to the *pipeline-document* path task 4.0 built — the one path a persisted `RunRecord` needs. `eval/run_baseline.py`'s `--embedder` default moves from `openai` to `hash`: deterministic, no network, no vendor account, which makes the published baseline reproducible by a stranger with none — a stronger property than the openai-embedded number this harness used to take, not a weaker one, even though it is not semantic · **one extractor per baseline, a scope decision named rather than silently narrowed.** A resolved pipeline names exactly one stage under the `Extractor` contract (task 4.0); `corpus/manifest.toml`'s `fetch` tier mixes PDFs (`arxiv/`) and text/markdown (`pl-wiki/`), which no single resolved pipeline can describe, and building multi-extractor pipeline resolution is not this task's to invent. `EXTRACTOR_SUFFIXES` (`{"text": (".md", ".txt"), "pdf-text": (".pdf",)}`) is the new `--extractor` flag's own suffix table, replacing `DEFAULT_EXTRACTORS`' per-suffix mapping; `selected_documents` refuses an unrecognised extractor by name. **A real bug this narrowing surfaced, found before the published file was written and fixed in this commit**: `reproducible_questions` alone answers "which tier is this document in", not "was this document actually indexed" — with `--extractor text` staging only `pl-wiki`, a first draft of this task still scored 95 of 136 questions, most resting on `arxiv` PDFs this run never indexed, silently penalising the pipeline for documents it was never given. `_run` now additionally keeps only questions whose `relevant_documents` are a subset of `documents` actually staged; `tests/docs/test_baseline_shape.py`'s own cross-check narrowed identically, so a baseline over-scoring or under-scoring its own indexed set is still caught by the gate · **`tests/architecture/test_eval_is_not_a_subsystem.py` is edited in this commit, not retired — the reasoning is in its own module docstring.** Its pre-4.1/4.2 prediction — "every line of `eval/` is meant to be deleted and replaced by Phase 4" — was too strong: 4.1/4.2 replaced the one thing that genuinely risked becoming Phase 4's own extension system in disguise (a registrable, third-party-extensible metric suite, now `weft-eval`'s `GenerationMetric`/`RetrievalMetric`), but never touched `eval/metrics.py`'s own `measure`/`judge` functions or `eval/check_questions.py`'s quote-pinned ground truth — original, Weft-specific, non-extensible scoring glue answering a different question (span-in-passage containment against a `(document, quote)` judgement, deliberately not a `RetrievalSample`'s node-id-based relevance set, because a judgement pinned to a `NodeId` is invalidated by any chunking change) that was never the reference's metric suite to begin with, and 4.1/4.2 never claimed to reimplement it. What *did* come true, this task, is narrower and later than the prediction: the published baseline adopted 4.4's own `RunRecord` rather than reinventing its shape. So the file's four assertions are **unchanged** — still guard no `pyproject.toml`, no `weft.packs` entry point, no reverse import from a distribution — because what they guard (`eval/` never growing the shape of a second extension system) is a **permanent property of a harness that stays**, not a one-time migration; retiring the file was considered and rejected on exactly that basis, stated in the docstring itself · **measured, from outside the repository**: all 18 first-party distributions built to wheels and installed into a throwaway venv (Python 3.12.12). `weft eval run ./corpus baseline` (a toy one-file corpus) persisted a real `RunRecord`, printed `run <id> persisted (...)`; `weft trace <id>` read it back, printing the resolved pipeline, corpus digest and active distribution set. Failure paths, both real: `weft trace does-not-exist` → exit `4`, naming the one run id that does exist; `weft index ./corpus --pipeline openai-embed` (a document naming `openai` for `embed`) → exit `4`, the `AmbiguousStageContractError` above, reproduced through the shipped binary rather than only in this sandbox's dev venv · **the published baseline itself, taken for real**: `uv run python eval/run_baseline.py --repeats 3 --top-k 10 --depths 5,10` against the real `compose.yaml` Qdrant container, over the `pl-wiki` tier (9 documents, `--extractor text`, 29 of 136 questions scoreable — 12 resting only on `pl-wiki` plus 17 unanswerable), wrote `eval/baselines/8854c33f71ea-2026-08-20.json`: three repetitions produced a **zero-width interval on every one of 12 metrics** (`hash`'s own determinism, `09` §4.3's "correct and strict" predicted outcome, not assumed), `reproducible: true`. A fourth, independent run (`--repeats 2 --out /tmp/later-run.json`) reproduced it: `uv run python eval/check_baseline.py eval/baselines/8854c33f71ea-2026-08-20.json /tmp/later-run.json` printed `12 metric(s) inside the interval 3 repetitions of the baseline spanned`, exit `0`. No artefact left outside the repository; every wheel and venv lived under `/tmp`, deleted after; the Qdrant collection the outside-repo demo created was dropped, the one backing the *published*, tracked baseline was kept. `uv run poe ci-checks` green: **1,637 passed, 1 skipped, 88 architecture tests**; `uv run poe kernel-isolated` green. **Zero lines under `packages/weft-kernel`** — `git diff --stat packages/weft-kernel` empty · `manual/operations-guide.md` → *Measuring a baseline* corrected in this commit: the `OPENAI_API_KEY=…` example is gone (the default needs no account), `--extractor`/`AmbiguousStageContractError` are explained, and the "two baselines" paragraph states the `--extractor pdf-text` an unreproducible run over the operator tier now needs, since every operator-tier document is a PDF · **left to 4.9/4.10, named rather than silently covered**: `RunRecord` still carries no metric scores — this task did not reopen that, and neither does `eval/run_baseline.py`'s own `BaselineReport`, which keeps its metrics as a sibling field rather than folding them into `record` — attaching a computed report to a `RunRecord` for `weft eval compare` to read is 4.9's own gap, unchanged and made no harder; running one corpus through two *actually different* derived pipelines and publishing the tool-generated comparison is 4.9's exit; the operations guide's coverage of persisted runs and `weft trace` beyond this task's own baseline section is 4.10's; a `pdf-text` baseline over the `arxiv`/`operator` tiers, and a real `weft-openai`-embedded baseline once the name collision above has an owner, are both left as the identical recipe with one flag different, not attempted here
- [x] **4.9** running one corpus through two derived pipelines produces a comparison the tool generates itself · owner `01` → Phase 4 **Exit** · turns on — · sha `dcad7d3` · **closes `.phase4-design.md` §7: `RunRecord` carried no metric scores, so `weft eval compare` could only report that two runs' pipelines *differ*, never what they *produced*.** `weft_eval.run_record.RunRecord` grows a fifth field, `metrics: Mapping[str, MetricRunResult]` — `MetricRunResult = Produced[MetricAggregate] | NotAggregated`, a two-member closed union distinguished by field name (`value` vs `reason`), never `weft_kernel.payload.Outcome` embedded directly: `Failed`/`NothingToProduce` are structurally identical (`{"reason": str}`), so Pydantic's own union resolution cannot tell them apart on a JSON round-trip — R4's rule ("mutually exclusive by construction, not a nullable field beside one that defaults") applied one level up from where 4.1 first applied it. `NotAggregated` collapses `Failed`/`NothingToProduce` into one persisted "not produced, here is why" shape; the prose in `reason` still distinguishes them, only the type does not · **`weft eval run <path> <pipeline> --questions <file> [--top-k N]`, task 4.9's own CLI surface.** `weft_cli.eval_scoring` (new module) reads a JSON list of `{query, relevant_documents}` judgements — `relevant_documents` names a `SourceDoc.source_id` (a resolved file path for the default extractor), never a node id, because a node id is a content-addressed digest nobody authoring a fixture ahead of a run can predict — retrieves for every question through the *resolved pipeline's own* `Embedder`/`NodeStore` stages (never `[services]`, Q3 still holds for a named pipeline), and scores the gate-safe `RetrievalMetric` subset (`weft_eval.harness.score_retrieval_gate_subset`, new module: derives which names to score from `registry.names_for(RetrievalMetric) ∩ gate_subset(registry).gate_safe`, never a fixed list of four). `--questions` omitted, `metrics` stays `{}` — the identical honesty `model_versions` had before task 4.7 · **`weft eval compare` reports `metrics_comparison`: every metric name either run's own `metrics` carries, paired side by side with a signed delta when both runs scored it, and an honest `NotAggregated` on whichever side did not** — never silence, never a fabricated number. `weft trace` grew a matching `metrics:` block, since it prints exactly what the record carries · **`run_ask` (task 0/2's own retrieval primitive) widened with two optional parameters, `embedder_config`/`store_config`, rather than a second retrieval path built for scoring** — `weft_cli.eval_scoring.score_pipeline` hands back a resolved stage's own configuration instead of `[services]`' unconfigured default, reusing the identical embed-then-search walk every other caller already gets.

  **Two real defects, both found running the binary and by no unit test, both fixed in this commit — exactly CLAUDE.md's own measured claim, twice over.** (1) `run_ask`'s widened parameters were, on this task's first draft, handed `ResolvedStage.config` unmodified: an empty, read-only `MappingProxyType` for a plugin (`HashEmbedder`) that declares no `config_model`, not `None`. `HashEmbedder.__init__` treats anything that is not `None` as a real config object and reads `.dimension` off it, so the first `weft eval run ... --questions` against a real `hash`-embedded pipeline failed outright: `'ask:embed' failed: 'mappingproxy' object has no attribute 'dimension'`. `weft_cli.compile.to_specs` already carries the identical narrowing for the identical reason, one layer up (`config if isinstance(config, BaseModel) else None`, its own docstring argues why); `weft_cli.eval_scoring._factory_config` is that same rule, applied at `run_ask`'s own boundary. (2) `weft_eval.ir_metrics.RecallAtK` counts one hit per retrieved *position* — correct only when `RetrievalSample.retrieved` never repeats an id, which stopped being true the moment ground truth is named by *document* (this task's own choice) over a corpus chunked into several passages per document: several ranks of one document's own chunks legitimately fill the top-`k`, and a real run measured recall **above 1.0**, a number V4's own contract cannot mean anything by. `weft_cli.eval_scoring._deduplicated_by_document` is the fix — retrieve `top_k * 8` raw hits and keep only each document's first, best-ranked occurrence, so no id repeats.

  **The exit demonstration itself: `index` and a genuinely-derived `specific`, not task 4.6's own "resolve identically."** All 18 first-party distributions built to wheels (Python 3.12.12, the throwaway-venv technique 4.4–4.8 already used) and installed into a project directory that is not this checkout, against the real `compose.yaml` Postgres/pgvector container. A two-document corpus (nitrogen, saffron — ~1050 characters each). `index` (`extract:text`, `chunk:fixed-size` at its default 512/50, `embed:hash`, `store:pgvector`), and `weft pipeline derive index specific` scaffolds `specific` (`name`+`extends`, nothing else, task 4.6's own repaired `extends:` path), hand-edited to add one real operator: `set: [{id: chunk, with: {size: 60, overlap: 10}}]` — an ~8x narrower chunk window. `weft eval run corpus index --questions questions.json --top-k 3 --corpus-name demo` → 6 nodes stored; the identical command naming `specific` → 55 nodes stored — a real, structural difference in what indexing produced, not a copy under a second name. `weft eval compare <index-run> <specific-run>`:
  ```text
  '<a>' vs '<b>' — same corpus, model versions and active distributions; pipeline is the only fact that may differ:
  'index' vs 'specific':
    ~ chunk: fixed-size -> fixed-size
  metrics:
    mean_average_precision: 0.750 (n=4, ±0.289) vs 1.000 (n=4, ±0.000)  Δ+0.250
    ndcg@3: 0.815 (n=4, ±0.213) vs 1.000 (n=4, ±0.000)  Δ+0.185
    precision@3: 0.333 (n=4, ±0.000) vs 0.333 (n=4, ±0.000)  Δ+0.000
    recall@3: 1.000 (n=4, ±0.000) vs 1.000 (n=4, ±0.000)  Δ+0.000
  ```
  exit `0` — a real, nonzero delta on two of the four metrics, the comparison the tool generates itself, reporting what the two pipelines *produced*. `weft trace <a>` prints the identical per-metric block. Failure paths, all real: `weft eval compare <a> ghost-run` → exit `4`, naming every run id that does exist; a second corpus, `weft eval compare <a> <c>` → exit `1`, `'demo' ... vs 'other' ...` named as the differing fact, no pipeline diff computed. **The self-check that makes this a proof of the mechanism, not of one fixed transcript:** `weft eval compare <a> <a>` — a run compared against itself — prints `Δ+0.000` on every metric, proving the numbers are genuinely recomputed rather than a fixed or fabricated delta.

  **Made to fail on purpose, and shown failing — not asserted only, run for real.** `specific.yaml` stripped back to `name: specific\nextends: index\n` (no `set:` operator — 4.6's own pre-derivation shape) makes `weft pipeline diff index specific` print `'index' and 'specific' resolve identically`, and the two `weft eval run` calls then produce **identical** node counts (6 and 6). `weft eval compare` on that pair:
  ```text
  metrics:
    mean_average_precision: 0.750 (n=4, ±0.289) vs 0.750 (n=4, ±0.289)  Δ+0.000
    ndcg@3: 0.815 (n=4, ±0.213) vs 0.815 (n=4, ±0.213)  Δ+0.000
    precision@3: 0.333 (n=4, ±0.000) vs 0.333 (n=4, ±0.000)  Δ+0.000
    recall@3: 1.000 (n=4, ±0.000) vs 1.000 (n=4, ±0.000)  Δ+0.000
  ```
  Every delta zero: this is a real, literal `AssertionError` against "at least one metric differs" — `assert any(d != 0.0 for d in deltas)` raises `AssertionError: every metric delta between the two pipelines was exactly zero` over this exact transcript — proving the exit's own core claim is not vacuous: it genuinely depends on the two pipelines actually differing, and fails honestly when they do not.

  **Repaired, 2026-08-20: the permanent, container-skipped `tests/integration` proof this entry once flagged as missing now exists.** `tests/integration/test_phase4_exit_evaluation_comparison.py` reuses the *exact* skip construct `tests/integration/test_cli_end_to_end.py` already carries — copied, not varied: the identical `_database_reachable`/`clean_database` shape (a short-timeout `psycopg.AsyncConnection.connect` probe, `pytest.skip(reason)` on failure) `test_ingest_pipeline.py` and `test_nul_byte_sanitisation.py` already hold too. The quality-gate guard that twice refused a *new* conditional-skip construct raised nothing against reusing an existing one — no third attempt against the guard was needed, because there was no new construct to defend. The file drives the real `Command`/`weft_cli.render.render_outcome` path `weft_cli.cli.main` itself uses — never `weft_eval` internals directly — over one corpus and two pipelines, `index` and a genuinely `extends:`-derived `specific` (one `set:` operator narrowing `chunk`'s window, this task's own shape): `specific.yaml` is asserted to carry no `stages:` of its own and exactly one `set:` entry, and the two runs' `stored_count`s are asserted unequal — the structural proof of a derivation, not a copy. Both runs' `RunRecord`s are re-read from disk through `weft_eval.run_record.load_run_record`, proving persistence rather than trusting the in-process result. `weft eval compare`'s own rendered text — `render_outcome`'s actual output, the same string a real invocation prints — is parsed for a `Δ` line whose value is not `+0.000`/`-0.000`; the test fails if none exists. **Why the delta is guaranteed rather than hoped for**: each question's query is exactly one document's opening sentence, truncated to the shorter of the two documents' openings; `weft_chunk.fixed_size._windows` always cuts a node's first window at `content[0:size]` from offset zero, so under `specific` that first chunk is character-for-character the query — a guaranteed, exact `HashEmbedder` hash match and a rank-one hit — while under `index`'s much wider default window no chunk equals the query at all, so retrieval there falls back to `HashEmbedder`'s own acknowledged non-semantic behaviour (its own docstring: "not a hash-based approximation of semantic similarity... nothing here reads tokens"). Run against the real container: `mean_average_precision: 0.750 (n=2, ±0.354) vs 1.000 (n=2, ±0.000)  Δ+0.250` and `ndcg@3: 0.815 (n=2, ±0.261) vs 1.000 (n=2, ±0.000)  Δ+0.185`, `precision@3`/`recall@3` identical on both sides — the same shape this task's own by-hand transcript produced above, now reproducible on every `ci-checks` run rather than trusted from a pasted log.

  **Made to fail on purpose, run for real, not merely reasoned about — the same discipline this task's own by-hand demonstration used, now repeatable.** Stripping `specific.yaml`'s `set:` operator down to `name: specific\nextends: index\n` (4.6's own pre-derivation shape, nothing else) collapsed the two runs to an equal `stored_count` and produced this real, pasted transcript, `pytest` failing on the same "at least one metric differs" assertion the real test passes:
  ```text
  E       AssertionError: expected at least one metric with a real, nonzero delta between 'index' and 'specific' — got:
  E         'e70d1c00-19c8-4c1e-9e33-3e93505c2f2f' vs '1edbc0e3-6eed-4aec-a1b6-14111efe47df' — same corpus, model versions and active distributions; pipeline is the only fact that may differ:
  E         'index' and 'specific' resolve identically.
  E         metrics:
  E           mean_average_precision: 0.500 (n=2, ±0.000) vs 0.500 (n=2, ±0.000)  Δ+0.000
  E           ndcg@3: 0.631 (n=2, ±0.000) vs 0.631 (n=2, ±0.000)  Δ+0.000
  E           precision@3: 0.333 (n=2, ±0.000) vs 0.333 (n=2, ±0.000)  Δ+0.000
  E           recall@3: 1.000 (n=2, ±0.000) vs 1.000 (n=2, ±0.000)  Δ+0.000
  E       assert []
  ```
  The `set:` operator was restored immediately after (`diff` against the pre-break file confirmed byte-identical), and the real, passing run above was re-verified green before this entry was written.

  **Unit tests, mirroring the source path.** `tests/unit/weft_eval/test_run_record.py` — `NotAggregated` folding (happy path: `Produced` passes through unchanged; edge case: `Failed`/`NothingToProduce` both collapse, carrying their own reason) and an empty-`metrics` default. `tests/unit/weft_eval/test_harness.py` — `score_retrieval_gate_subset` against the real, registered suite: a hand-computed `precision@2` (happy path), an empty-samples run answering `Failed` for every gate-safe metric rather than silence (edge case), gate-unsafe `RetrievalMetric`s (`context-recall`/`context-relevance`) never appearing at all. `tests/unit/weft_cli/test_eval_scoring.py` — `load_questions` round-tripping a well-formed file, refusing malformed JSON and a missing file naming the path (error cases); `score_pipeline` retrieving and scoring through fakes for `Embedder`/`NodeStore` (happy path) and refusing a pipeline with no store stage (edge case). `tests/unit/weft_cli/test_ask.py` — `run_ask` forwards a resolved stage's own config to the factory rather than the `[services]` default. `tests/unit/weft_cli/test_eval_commands.py` — `EvalRunCommand` folding a fake `score_pipeline`'s result into the persisted record (the command's own wiring, isolated from `eval_scoring`'s internals, already covered above); `EvalCompareCommand` pairing two runs' metrics, naming a run that never scored a given metric as `NotAggregated` rather than silence. `tests/unit/weft_cli/test_render.py` — `weft eval compare`'s per-metric delta line, `weft trace`'s `metrics:` block, both the "some metrics scored" and "none scored" cases.

  **Measured.** `uv run poe ci-checks` green: **1,650 passed, 1 skipped, 88 architecture tests**; `uv run poe kernel-isolated` green. **Kernel line delta: zero** — `git diff --stat packages/weft-kernel` is empty. `manual/user-manual.md`'s generated command table regenerated (`weft eval run`/`eval compare` help text updated); `manual/contract-reference.md` regenerated and came back byte-identical — no new contract published, only new implementations against `RetrievalMetric`'s own existing one. `docs/03-cli.md` and `manual/operations-guide.md` corrected in this commit: `--questions`/`--top-k`, the metrics comparison shape, and a worked example. `manual/troubleshooting.md` gains `QuestionsFileError`/`PipelineNotRetrievableError` (`weft_cli.eval_scoring`, new failure modes, neither a name-resolution failure so neither joins `NAME_RESOLUTION_FAMILY`) — `tests/docs/test_troubleshooting_coverage.py` green. No artefact left in the repository — every wheel, venv and written file lived under a scratch directory outside this checkout, deleted after.

  **Measured again, 2026-08-20 repair: the permanent integration test above, added.** `uv run poe ci-checks` green — **1,651 passed, 1 skipped, 88 architecture tests** (one test gained, `tests/architecture`'s own count unchanged since the new file lives under `tests/integration`, already reachable from the composite's own `test` task per `pyproject.toml`'s `testpaths = ["tests"]` — nothing to wire); `uv run poe kernel-isolated` green; **kernel line delta: zero**. The new test **ran**, not skipped — `compose.yaml`'s container was up for this run, confirmed by `pytest -q -rs` naming the one skip in the whole suite as `tests/docs/test_corpus_manifest.py`'s pre-existing, unrelated network gate, not this file.
- [x] **4.10** the contract reference covers `Metric`, and the operations guide covers persisted runs and `weft trace` · owner `08` §1–§2 · turns on — · sha `df8be6e`

**Checked before writing anything: the contract reference was not stale.** The worry named on this task line — task 4.1 published `Metric`'s section before 4.2 split it into `GenerationMetric`/`RetrievalMetric`, before 4.3's aggregation, before 4.7's mandatory `runs_in_gate` declaration — is real in shape but did not hold in fact. Regenerating (`uv run python scripts/generate_contract_reference.py`) produced **byte-identical output** to the committed file: zero diff. The reason is `runs_in_gate` itself, read at source (`weft_eval.contract.GenerationMetric`/`RetrievalMetric`): it is declared `if TYPE_CHECKING:` and assigned after the class body, exactly the pattern `Command.permission_class` already set at task 3.1 — so it is never a member of `__protocol_attrs__`, and the generator (correctly, by the identical logic that already keeps `.version` off the rendered method list) never renders it as a "Declared attribute." The reference was last touched at 4.2 (`fd2afd4`) and 4.7 never needed to touch it, not because 4.7 was forgotten but because what 4.7 added is invisible to this generator by the same design that already makes `permission_class` invisible for `Command`. Verified, not assumed — this is exactly the kind of claim `CLAUDE.md` requires be checked before being written down.

**What was stale: one hand-written example in the operations guide, found by running the binary.** `manual/operations-guide.md`'s `weft eval metrics` transcript listed `embedding-similarity` appended after `token-recall`, out of alphabetical order; a real run (`weft eval metrics` against a fresh project, no credentials) sorts it in after `accuracy`, before `exact-match` — `gate_subset`'s own output is `sorted()`. Corrected to the real fifteen, in the real order.

**What the operations guide gained: a section neither owned before.** `manual/operations-guide.md` → *Persisted runs, and `weft trace`* is new, placed ahead of the baseline-measurement material it now introduces. It states `RunRecord`'s five fields and why each is there (`resolved_pipeline`, `corpus`, `model_versions`, `active_distributions`, `metrics`), that `weft eval run`/`weft index --pipeline` write `runs/<uuid>.json` project-locally while the hand-run harness writes a second, differently-purposed `RunRecord` under `eval/baselines/` — same type, different directory, never conflated — and how to read one back (`weft eval compare`, `weft trace`, both refusing by name for an id that is not there). Its own `### weft trace` subsection states what task 4.6's Q2 settled and `docs/03-cli.md` already carries: `weft trace` prints exactly what the persisted record holds and **does not** replay a run stage by stage, time a stage, or read an exported OTel span — Phase 4 ships no exporter pack, so there is nothing to read. This is the narrowing task 4.6 made, restated here rather than re-argued, so an operator reading only this page is not sold a promise `03-cli.md` itself already retracted. A duplicate, one-line mention of `weft trace` under *Scoring retrieval, and comparing what two runs produced* is trimmed to a cross-reference — the single-ownership rule `08` §3 states for the six manuals, applied to two sections of the same one.

**Measured, from outside the repository, against the real container** (`WEFT_DATABASE_URL=postgresql://weft:weft@localhost:5433/weft`, a scratch directory, the shipped `.venv/bin/weft`): a project-local `pipelines/index.yaml` (four stages, `pgvector`) and a `set:`-derived `specific.yaml` resolved and diffed; `weft eval run corpus index --questions questions.json` persisted a run and printed `wall clock: 0.02s`; `weft trace <id>` printed the resolved pipeline, corpus digest, `model versions: (none recorded)` and a real `metrics:` block (`mean_average_precision`, `ndcg@5`, `precision@5`, `recall@5`); `weft eval compare` on two comparable runs printed matched deltas, and on two runs over different corpora refused outright: `'<a>' and '<b>' are not comparable as a change of pipeline alone: corpus differs (...)`. **Failure paths, real:** `weft trace does-not-exist` → exit `4`, `'does-not-exist' is not a persisted run — checked 'runs'. Persisted runs: (none).`; `weft eval run corpus nope` → exit `4`, naming every pipeline the project actually knows; `weft nope` → exit `2`, argparse's own `invalid choice` naming every real subcommand; `weft --help` from an empty directory printed help and exited `0` — no REPL, the Phase 3 scar named in `CLAUDE.md` stayed shut. `weft eval metrics --name faithfulness` reproduced the exact credential-refusal text task 4.7's own entry already quotes, unchanged. No artefact left behind: the scratch directories were removed after the transcripts above were captured.

`uv run poe ci-checks` green — **1,651 passed, 1 skipped, 88 architecture tests**, unchanged from 4.9's own count, because this task changed no code; `uv run poe kernel-isolated` green. **Zero lines under `packages/weft-kernel`**, and zero lines anywhere under `packages/` — this task edited exactly two files, `manual/operations-guide.md` and this ledger.

**Exit** (`01` → Phase 4): task 4.9 — **met, 2026-08-20**, both runs persisted (4.4) and FF8(c) wired and green (4.4). Two genuinely-derived pipelines over one corpus produce a comparison the tool generates itself, reporting real, nonzero per-metric deltas rather than only a pipeline diff — see 4.9's own entry for the transcript, the two real defects found and fixed proving it, and the deliberate failing run. **The phase closes with this task**: 4.10 was the one thing still open once 4.9 met the exit criterion, and it is now met — see above. The build checklist above ticks in full.

---

## Phase 5 — The independence test

**G9 settled 2026-08-21** — contract versioning and deprecation. This phase is **unblocked**. The
ruling answered all five of `09` §2.3's dependencies and created tasks **5.2a**–**5.2f** below, which
replace the single placeholder 5.2 that stood here while the gate was open. Two of them are scope
additions rather than elaborations of existing work — the persisted-schema axis (5.2c) and the
structured error channel (5.2d) — and are logged as `S5` and `S6` in `README.md`'s decision log under
`09` §6.4.

**G7 settled 2026-08-21**: explicit extension points only, no bus. It did not leave this phase
unchanged. Task **5.1** was the task G7 owned, and it is no longer a question — the session found
one real hole (derived data outliving its source) and closed it with two store-family Protocols,
which makes 5.1 buildable and splits it into **5.1a**–**5.1d** below — the last of those being the second add-on the session produced, `weft-otel`. G7 also *added* to G9's
agenda rather than reducing it — two newly published capability Protocols and a persisted
`ReconcileReport` — and both landed in G9's ruling when it settled on 2026-08-21. **No ⚠ remains on
this phase: it carried one gate, and that gate is closed.**

**This phase's exit is a person, not a test**, so most of these tasks make *someone else's* work
possible rather than adding a feature.

- [x] **5.1a** deleting a source reaches everything derived from it: `SourceDeletable` is published in the store family, `weft delete` fans out across every registered participant, and a participant that fails is named rather than swallowed · owner `02` §1 → *The store contract family*; `03` → *Command surface* · turns on — · sha `8bfbe2a`

  **Run outside the repository, against the real container** — the failure path first, which is
  where the one defect this task shipped was found (`docs/lessons.md` L5.9, and the repair is in
  `DeleteCommand.describe_impact`'s own docstring):

  ```
  $ weft delete doc-1 < /dev/null          # no weft.toml, no dsn
  [services] store names 'pgvector', and no registered NodeStore has that name. These
  distributions contributed nothing, or only part of what they publish, and one of them may be
  the one that provides it: weft-store (failed). Registered NodeStore names: 'qdrant'.
  ...
  'weft-store' settings failed validation: 1 validation error for PgVectorSettings / dsn / Field required
  exit=4

  $ weft delete .../corpus/weaving.txt < /dev/null     # WEFT_DATABASE_URL exported, no TTY
  'delete' is a destroy-class command, called with {'source_id': '.../weaving.txt'}.
  '.../weaving.txt' will be removed from 1 participant(s): pgvector (weft-store). It refuses to
  run with no terminal to confirm in, and never proceeds silently. Pass --yes to permit it for
  this invocation.
  exit=3

  $ weft delete .../corpus/weaving.txt --yes
  '.../weaving.txt' — 1 participant(s):
    pgvector (weft-store): 1 node(s) removed
  exit=0

  $ weft delete .../corpus/weaving.txt --yes           # again: idempotent, still a success
    pgvector (weft-store): 0 node(s) removed
  exit=0
  ```
- [x] **5.1b** derived state converges on what the corpus actually holds, whatever was missed and whoever was not installed at the time: `Reconcilable` is published, `weft reconcile` runs it, and a pass interrupted part-way resumes rather than restarting · owner `02` §1; `03` · turns on — · sha `f38479a`

  **A node store converges tombstones, not orphans**, and that narrowing is recorded in `02` §1
  rather than only here — `repair` as written removes "derived state whose source is gone", which
  applied to a node store would erase every corpus indexed before source records were written.
  Resumption is therefore a fact about durable rows rather than a promise about a cursor, proven
  on both real backends by the conformance kit and by a stranger's own pack.

  **Run outside the repository, against the real container**, with a half-finished deletion
  planted by hand — the state a `delete_source` killed between its two statements leaves:

  ```
  $ weft reconcile --mode wobble
  usage: weft reconcile [-h] [--mode {repair,full}] [--dry-run] [--yes]
  weft reconcile: error: argument --mode: invalid ReconcileMode value: 'wobble'

  $ weft reconcile --dry-run --yes
  mode 'full' would run against 1 participant(s):
    pgvector (weft-store)

  $ weft reconcile < /dev/null
  'reconcile' is a destroy-class command, called with {'mode': 'full', 'dry_run': False}. mode
  'full' will run against 1 participant(s): pgvector (weft-store). It refuses to run with no
  terminal to confirm in, and never proceeds silently. Pass --yes to permit it for this invocation.
  exit=3

  $ weft reconcile --yes
  mode 'full' — 1 participant(s):
    pgvector (weft-store): examined 1, removed 1, backfilled 0
  exit=0

  $ weft reconcile --yes                 # again: idempotent
    pgvector (weft-store): examined 0, removed 0, backfilled 0
  exit=0
  ```

  That third block is the repaired one. It first read `{'mode': <ReconcileMode.FULL: 'full'>,
  ...}` — Phase 3's fourth repair recurring at a different raise site, logged as
  `docs/lessons.md` L5.10 and fixed at the seam that renders every gated command's arguments.
- [x] **5.1c** the expensive mode is never reached ambiently and never surprises anyone: the automatic post-index pass is `repair`, `full` is reached only by a person's per-run flag, and `full` prints what it will cost before it spends it · owner `02` §3 → *Slots*; `03` → *Permissions* · turns on — · sha `da37871`

  `weft_cli.commands.IndexArgs.reconcile` is a hardcoded `ReconcileMode.REPAIR`, read from no
  config — `weft index` runs the automatic pass unconditionally after a successful run, on both
  the default and `--pipeline` paths, since converging `[services] store` is a project-wide
  concern independent of which pipeline a given run used. `ReconcileArgs.mode` moved from a
  hardcoded `full` to `None`, with `weft_cli.reconcile_policy.ReconcilePolicy` (`[reconcile]
  mode` in `weft.toml`, default `full`) supplying the fallback and the flag always winning —
  `weft_cli.config_surface` grew a fifth dotted key, `reconcile.mode`, the identical shape
  `[services]`/`[permissions]` already have. `Reconcilable` gained `estimate(ctx, mode) ->
  ReconcileEstimate` (`weft-store`), asked only when the effective mode is `full` and rendered
  first, ahead of every other line — `STORE_CONTRACT_VERSION` moves `1.4.0` → `2.0.0`, a major
  under G9's two-audience rule, since adding a method to a published Protocol is major for an
  implementer even though it is minor for a caller. All three first-party `Reconcilable`s
  (`PgVectorStore`, `weft_qdrant.store.QdrantStore`, and the out-of-tree stranger
  `examples/weft-example-ingest`) report `model_calls=0` honestly — a node store holds no
  derived state to backfill — proven on both real backends by the conformance kit.

  **A repair found by `ci-checks`, not by the binary — logged as `docs/lessons.md` L5.11.**
  `weft_cli.reconcile_policy` needed `weft_store.ReconcileMode` at its own module scope, and
  importing that module eagerly from `weft_cli.registry_bootstrap` (for `Dependencies.
  reconcile_policy`'s `default_factory`) and from `weft_cli.config_surface` (for `validate_
  set_value`'s new branch) each put `weft_store` in `sys.modules` for `weft --version`, which
  fitness function 8(b) forbids categorically. Both became lazy imports, on the identical
  footing `registry_bootstrap._ensure_chunk_offset_rehydrates` already documents for
  `weft_chunk`/`weft_store`.

  **Run outside the repository, against the real container** — the happy path, the cost block,
  the personal default, and both failure paths:

  ```
  $ weft init
  wrote weft.toml.

  $ weft index corpus
  produced 1, nothing to produce 0, failed 0. nodes now stored: 3.
  mode 'repair' — 1 participant(s):
    pgvector (weft-store): examined 0, removed 0, backfilled 0
  exit=0

  $ weft index corpus --reconcile full --yes
  produced 1, nothing to produce 0, failed 0. nodes now stored: 3.
  mode 'full' — 1 participant(s):
    pgvector (weft-store): no unfinished deletions; nothing to converge
    pgvector (weft-store): examined 0, removed 0, backfilled 0
  exit=0

  $ weft reconcile --dry-run --yes
  mode 'full' would run against 1 participant(s):
    pgvector (weft-store): no unfinished deletions; nothing to converge
  exit=0

  $ weft reconcile < /dev/null
  'reconcile' is a destroy-class command, called with {'mode': None, 'dry_run': False}. mode
  'full' will run against 1 participant(s): pgvector (weft-store). It refuses to run with no
  terminal to confirm in, and never proceeds silently. Pass --yes to permit it for this
  invocation.
  exit=3

  $ weft config set reconcile.mode repair
  set reconcile.mode = repair in weft.toml.
  $ weft reconcile --yes
  mode 'repair' — 1 participant(s):
    pgvector (weft-store): examined 0, removed 0, backfilled 0
  exit=0

  $ printf '[reconcile]\ndelete = "allow"\n' > weft.toml
  $ weft plugins list
  unknown [reconcile] key(s) in weft.toml: 'delete'. [reconcile] accepts mode. A key nothing
  reads is refused rather than ignored — a default you did not actually change is one you
  would have to notice by the tool behaving differently than the file says.
  exit=4

  $ weft config set reconcile.mode wobble
  'reconcile.mode' must be one of ['full', 'repair'], not 'wobble' — weft_store.ReconcileMode's
  own vocabulary.
  exit=1
  ```
- [x] **5.1d** the spans the seam has always emitted reach somewhere a person can read them, through a pack and with no core edit: `weft-otel` sets the `TracerProvider` in `register()`, and `weft plugins doctor` shows it active · owner `02` §4 → *The second add-on G7 produced*; `01` → *The kernel boundary* · turns on — · sha `73bcdf5`

  `packages/weft-otel/` ships as an ordinary first-party pack: one `[project.entry-points.
  "weft.packs"]` line, one `register(registrar, settings)`, zero lines under `packages/
  weft-kernel/`. `register()` never calls `registrar.add(...)` — the kernel boundary this
  task tests is that a capability need not be a stage, a store, a retriever or a command to
  arrive through the published model. `OtelSettings.exporter` (`NONE`/`CONSOLE`/`OTLP`)
  governs whether `register()` calls `opentelemetry.trace.set_tracer_provider`; `OTLP` is
  probed and verified together — the optional `weft-otel[otlp]` extra importable and an
  `endpoint` configured, never a live reachability check — and falls back to `CONSOLE`,
  loudly, on stderr, when either check fails.

  **`exporter` defaults to `NONE`, not `CONSOLE` — a correction made by measurement, logged
  as `docs/lessons.md` L5.12.** The first draft defaulted to `CONSOLE`, read off `02` §4's own
  "ordinary pack, install and it works" framing. `weft-otel`'s own tests passed under it, and
  so did `tests/architecture`/`tests/docs` run alone. Running the *combined* suite
  (`tests/architecture tests/docs tests/unit`) falsified it: `opentelemetry.trace.
  set_tracer_provider` succeeds exactly once per process, and dozens of existing
  `tests/unit/weft_cli` tests (`test_cli.py`, `test_repl.py`, `test_registry_bootstrap.py`)
  call the real, open-by-default discovery path with nothing to do with tracing. With
  `CONSOLE` as the default, whichever of those happened to run first inside one `pytest
  tests -q` process (`tests/unit/weft_cli` sorts before `tests/unit/weft_kernel`) silently
  claimed the provider slot, and `tests/unit/weft_kernel/test_seam_trace_visibility.py` —
  which must win that race to prove `seam.wrap`'s spans reach a real SDK exporter — started
  losing it, deterministically, the moment `weft-otel` was installed. `NONE` makes
  installing the pack necessary but not sufficient; the one-line opt-in is `[packs.weft-otel]
  exporter = "console"`.

  **This narrows the task line above, and `02` §4 now says so rather than leaving it
  implicit.** "`weft-otel` sets the `TracerProvider` in `register()`" reads unconditional;
  it now does that only once a `weft.toml` opts in. The test-suite collision is what forced
  the question, not what settles it — a pack that redirected a process-global singleton the
  moment it was installed, with no operator action, is `02` §3's *slot* rule broken by a
  quieter route (a contribution landing somewhere without anyone opting in) and G3's
  *installed-and-ambient* threat in miniature, so `NONE` is the more defensible default
  independent of the test suite that happened to surface it first.

  **`weft plugins doctor`'s `tracing:` line is pack-agnostic, on purpose.** Nothing on a
  `PackReport` can carry what `register()` decided — `DISCLOSURE` is read before `register()`
  runs, and `weft-otel` contributes zero registrations by design, so `contributed` says
  nothing either. `weft_cli.tracing_status.describe_tracing()` reads `opentelemetry.trace.
  get_tracer_provider()` directly, after discovery has finished, and reports `not configured`
  or `configured`, naming whatever class set it — never importing `weft-otel` by name, so a
  host application embedding `weft` and configuring its own tracing reads the identical line.

  **The trap `01`/`02` name was real, and the fix does not touch what fitness function 2
  polices.** `test_ff2_no_privileged_builtins.py::test_registry_contents_equal_what_
  discovery_declared` carried one assertion, `expected_builtins <= declared`, that read as
  "every first-party pack is active *and contributing*" but was never FF2's substantive
  check — the docstring above it already says so: it is the *floor*, there only to stop the
  real checks (`declared == present`, the per-distribution registration count, factory
  identity — all three untouched by this task) from passing vacuously because `uv sync` was
  never run. That floor happened to work by counting contributions only because, until this
  task, every first-party pack contributed at least one. `weft-otel` is the first that does
  not, by design (`02` §4: "registers no plugin against any contract"), so the floor is
  replaced, for exactly this one pack, with what it was always actually trying to prove —
  `status is ACTIVE`, i.e. installed and running, not `FAILED` — behind a named,
  single-entry waiver constant, `PACKS_THAT_REGISTER_NOTHING_BY_DESIGN`, the identical ratchet
  discipline `test_ff9c_every_contract_has_a_stranger.py`'s own waivers already use. Nothing
  about FF2's actual defect-catching mechanism moved. FF9(c) gains no new obligation either:
  `weft-otel` exports no `Protocol`, so the contract-vs-stranger check it turns on is
  unaffected — verified by reading `test_ff9c`'s own wheel-building and `Protocol`-scanning
  logic against `weft-otel`'s `__all__`, not assumed.

  **Run outside the repository, against the real container** — `weft plugins doctor` before
  and after enabling tracing, a real `weft index` with a span reaching the exporter, and two
  failure paths:

  ```
  $ weft init
  wrote weft.toml.

  $ weft plugins doctor
  ...
  weft-otel: active (0 contributed)
    disclosure: network=[], filesystem=[], subprocess=[], note="Sets the process OpenTelemetry
  TracerProvider from [packs.weft-otel] settings. exporter defaults to 'none' (nothing exported
  until configured); 'console' prints to stdout; 'otlp' reaches the network at whatever endpoint
  is configured. Registers no plugin against any contract."
  ...
  tracing: not configured — spans stay on the no-op default and go nowhere. Install weft-otel
  and set [packs.weft-otel] exporter to 'console' or 'otlp' (its own default is 'none', so
  installing alone is not enough), or configure a TracerProvider yourself.

  $ printf '\n[packs.weft-otel]\nexporter = "console"\n' >> weft.toml
  $ weft index corpus --yes
  {
      "name": "extract",
      "context": {"trace_id": "0x939f3b7c7b64ce1fe362531e6491c7dc", "span_id": "0x72bcd1e5..."},
      "kind": "SpanKind.INTERNAL",
      "attributes": {"weft.pack": "weft-extract", "weft.contract": "Extractor", "weft.plugin": "text", ...}
  }
  { "name": "chunk", ... "attributes": {"weft.pack": "weft-chunk", ...} }
  { "name": "embed", ... "attributes": {"weft.pack": "weft-embed", ...} }
  { "name": "store", ... "attributes": {"weft.pack": "weft-store", "weft.plugin": "pgvector", ...} }
  { "name": "store:flush", ... }
  { "name": "command:index", ..., "attributes": {"weft.pack": "weft-cli", "weft.plugin": "index"} }
  produced 1, nothing to produce 0, failed 0. nodes now stored: 2.
  mode 'repair' — 1 participant(s):
    pgvector (weft-store): examined 0, removed 0, backfilled 0
  exit=0
  # all six spans share one trace_id — one real run, one real trace, reaching a real exporter.

  $ weft plugins doctor
  ...
  tracing: configured — spans export through opentelemetry.sdk.trace.TracerProvider.

  $ printf '[packs.weft-otel]\nexporter = "bogus"\n' > weft.toml
  $ weft plugins doctor
  ...
  weft-otel: failed (0 contributed)
    reason: 'weft-otel' settings failed validation: 1 validation error for OtelSettings
  exporter
  exit=0

  $ printf '[packs.weft-otel]\nexporter = "otlp"\n' > weft.toml
  $ weft plugins doctor
  weft-otel: exporter 'otlp' requested but not usable (install the 'weft-otel[otlp]' extra and
  set [packs.weft-otel] endpoint) — falling back to 'console'. See `weft plugins doctor`.
  ...
  tracing: configured — spans export through opentelemetry.sdk.trace.TracerProvider.
  exit=0
  ```
- [x] **5.2a** a contract version is a fact a resolver can act on, not a constant people remember to move: every distribution leaves `0.0.0`, every intra-repo dependency carries a compatible range `>=X,<MAJOR+1`, and **fitness function 6 exists** — asserting not that the constant moved but that its movement agrees with the version of the distribution publishing it · owner `09` §2.3; `05` → G9 · turns on **FF6** · sha `71c3f31` · **`COMMAND_CONTRACT_VERSION` 1.1.0 → 2.0.0 lands here**, the mis-recorded major task 3.2 created when `help` joined `required_declarations`

  **Version scheme.** Every first-party distribution's real version is the maximum, per G9's
  binding rule, of the contract versions it publishes (`tests/architecture/
  test_ff6_contract_version_binding.py::contract_versions_in`, scanning `packages/*/src/*/contract.py`
  by AST rather than by import): `weft-store` and `weft-command` land on `2.0.0` (each publishes a
  contract already bumped to a major), every other contract-publishing distribution lands on `1.0.0`
  (`STORE_CONTRACT_VERSION` 2.0.0 dominates `weft-store`'s own `FILTER_AST_VERSION` 1.1.0; every other
  distribution's contracts are still at their initial 1.0.0). A distribution that publishes **no**
  contract — `weft-kernel`, `weft-cli`, `weft-otel`, and the three backend-implementer packs
  `weft-pdf`/`weft-openai`/`weft-qdrant` — has nothing to force it above the baseline `09` §2.2
  states for the project as a whole, so each takes `0.1.0`: a real, non-placeholder number, still
  inside the 0.x line, distinct from `0.0.0` only in being a fact rather than a stand-in.
  `testing/weft-canary` is explicitly in scope — its own `pyproject.toml` already says "Never
  published," but `0.0.0` is still a placeholder a resolver could stumble on, and giving it `0.1.0`
  costs nothing since nothing in the tree depends on it by name. `docs/09-release.md` §2.2 gained a
  paragraph reconciling this with "every distribution is 0.x until Phase 6": that sentence was never
  about the literal leading digit, and `weft-store`/`weft-command` reading `2.0.0` today is G9's
  mechanical fact, not an early 1.0 promise — the substantive precondition table in that section is
  untouched.

  **Ranges.** Every intra-repo `dependencies` entry that named another workspace member as a bare
  string now carries `>=X,<MAJOR+1`, `X` being that dependency's own declared version and `MAJOR+1`
  its next major — e.g. `weft-cli` now depends on `weft-store>=2.0.0,<3.0.0` and
  `weft-kernel>=0.1.0,<1.0.0`. `uv sync` re-resolved the whole workspace clean under the new ranges
  (`[tool.uv.sources]`'s `workspace = true` entries satisfy any range whose floor is that member's
  own declared version, by construction), and `poe kernel-isolated` still installs `weft-kernel`
  alone and imports it.

  **Fitness function 6.** `tests/architecture/test_ff6_contract_version_binding.py`. Reads the
  contract-version constant by parsing `contract.py` as text (never `import`, so a pack's own
  import-time side effects never run to answer this) and the distribution version from that
  distribution's own `pyproject.toml` via `tomllib` — two independently-read facts, the direct
  answer to `docs/lessons.md` L5.6's finding that a declaration derived from the thing it verifies
  cannot fail. Asserts the invariant G9's binding rule reduces to: a contract's version can never
  outrun the distribution publishing it. `test_the_check_can_actually_fail` plants a disagreeing pair
  in a throwaway tree and proves the two facts can diverge, in the spirit of
  `test_ff9_extension_from_outside.py::test_the_grep_can_actually_fail`; a companion test proves the
  agreeing case is not flagged, and a third proves `*_SCHEMA_VERSION` constants (the stored-data axis
  `S5` added, not a contract) are deliberately excluded. **What it does not attempt, recorded rather
  than faked:** `01`'s literal sentence — "a check fails on a changed contract whose version did not
  move" — asks for a diff against a stored shape. Nothing in this repository is tagged, released or
  lock-frozen before Phase 6, so a snapshot taken today would be this commit's own tree and would rot
  at the first accepted bump. What is checked instead is the fact that actually matters: the
  agreement invariant holds at every commit, which is what makes the dependency ranges above
  enforceable at all. `docs/01-high-level-plan.md`'s fitness-function-6 line now states this
  narrowing in the same place the sentence lives. The six unit-test docstrings `docs/lessons.md` L5.4
  found saying "fitness function 6 will eventually check" (`tests/unit/weft_{retrieve,enhance,
  extract,embed,generate,eval}/test_contract.py`) now say it binds to the distribution's own version,
  present tense.

  **`COMMAND_CONTRACT_VERSION` 1.1.0 → 2.0.0.** Corrected in code (the G9 commit itself,
  `4fb04d0`, only announced the correction in prose — `docs/README.md`'s decision-log row and
  `docs/09-release.md` §2.3 already read "corrected to 2.0.0," but `weft_command/contract.py` still
  read `"1.1.0"` until this task). `help` joining `required_declarations` (task 3.2) is minor for a
  caller and **major for an implementer** — G9's table, row 3 — so the bump is the maximum of the
  two, corrected here along with the module docstring's own account of why.

  **Every other moved contract, assessed against G9's two-audience table.** `STORE_CONTRACT_VERSION`
  is the only other constant with history (1.0.0→1.1.0→1.2.0→1.3.0→1.4.0→2.0.0, tasks 2.5/2.6/5.1a/
  5.1b/5.1c) and it was **already correctly recorded**, not a second mis-record: each of the first
  four moves adds an entirely new Protocol to the family (`TextSearch`, `MetadataFilter`,
  `SourceDeletable`, `Reconcilable`) — additive, since capability is derived by `isinstance` and no
  existing `NodeStore` implementation is broken by a Protocol it never has to satisfy — correctly
  minor. Only the fifth move (5.1c, adding `estimate` to the already-published `Reconcilable`)
  breaks every existing implementer and is correctly major, as `weft_store/contract.py`'s own
  docstring already argued (written before G9 formally closed, but against the same rule). Every
  other `*_CONTRACT_VERSION`/`*_AST_VERSION` constant in the tree is still at its untouched initial
  `1.0.0` — no history to assess.

  **Run outside the repository:**

  ```
  $ weft --version
  weft 0.1.0

  $ weft plugins doctor
  weft-canary: active (0 contributed)
    disclosure: not disclosed
  weft-chunk: active (1 contributed)
    disclosure: not disclosed
  weft-clean: active (6 contributed)
    disclosure: not disclosed
  weft-cli: active (18 contributed)
    disclosure: not disclosed
  weft-embed: active (1 contributed)
    disclosure: not disclosed
  weft-enhance: active (1 contributed)
    disclosure: not disclosed
  weft-eval: active (28 contributed)
    disclosure: not disclosed
  weft-extract: active (3 contributed)
    disclosure: not disclosed
  weft-generate: active (6 contributed)
    disclosure: not disclosed
  weft-index: active (4 contributed)
    disclosure: not disclosed
  weft-llm: active (1 contributed)
    disclosure: not disclosed
  weft-openai: active (2 contributed)
    disclosure: not disclosed
  weft-otel: active (0 contributed)
    disclosure: network=[], filesystem=[], subprocess=[], note="Sets the process OpenTelemetry
    TracerProvider from [packs.weft-otel] settings. exporter defaults to 'none' (nothing exported
    until configured); 'console' prints to stdout; 'otlp' reaches the network at whatever endpoint
    is configured. Registers no plugin against any contract."
  weft-pdf: active (2 contributed)
    disclosure: not disclosed
  weft-qdrant: active (1 contributed)
    disclosure: not disclosed
  weft-retrieve: active (31 contributed)
    disclosure: not disclosed
  weft-store: active (1 contributed)
    disclosure: not disclosed
  tracing: not configured — spans stay on the no-op default and go nowhere. Install weft-otel and
  set [packs.weft-otel] exporter to 'console' or 'otlp' (its own default is 'none', so installing
  alone is not enough), or configure a TracerProvider yourself.
  exit=0

  $ weft index nonexistent-file.txt
  [services] store names 'pgvector', and no registered NodeStore has that name. These distributions
  contributed nothing, or only part of what they publish, and one of them may be the one that
  provides it: weft-store (failed). Registered NodeStore names: 'qdrant'.

  Diagnostic detail:
  weft-store:
      'weft-store' settings failed validation: 1 validation error for PgVectorSettings
      dsn
        Field required [type=missing, input_value={}, input_type=dict]
          For further information visit https://errors.pydantic.dev/2.13/v/missing
  exit=4

  $ weft ask
  usage: weft ask [-h] [--pipeline PIPELINE] [--retrieve-only] [--top-k TOP_K]
                  [--format {text,json}] [--yes]
                  question
  weft ask: error: the following arguments are required: question
  exit=2

  $ weft --help
  usage: weft [-h] [--version] [--json | --quiet] command ...
  ... (full command list, unchanged in shape)
  exit=0
  ```

  All green: `poe ci-checks` (93 architecture tests, 1727 passed/1 skipped), `poe kernel-isolated`,
  `uv sync`. `docs/lessons.md` L5.13 logged: two pre-existing unit tests
  (`tests/unit/weft_generate/test_init.py`, `tests/unit/weft_retrieve/test_init.py`) asserted a
  dependency list's *literal* shape (a bare-name set) rather than the fact it meant (which
  distributions are depended on), and broke the instant the range task 5.2a requires was appended —
  fixed with a small name-extracting helper in each file.
- [x] **5.2b** an added `Enum` member cannot make a backend answer the wrong query: every dispatch over a published `Enum` is exhaustive by construction, with no fall-through default, and a fitness function keeps it so · owner `05` → G9; `01` → *Fitness functions* · turns on **FF13** · sha `5cd48b3` · **nine sites, not five** — the ledger's own five plus four more this task's audit found in `weft_store.pgvector_store`, undiscovered by `docs/09-release.md` §2.3's own list because it never named the SQL half of task 2.6's translation

  **The five named sites, fixed.** `weft_qdrant.store.to_qdrant_filter`/`_condition`/`_range` and
  `weft_store.contract.Filter._shape_matches_op` now end `match self.op: ... case _: raise
  weft_store.contract.UnhandledFilterOpError(...)` — a `match` whose final arm is mandatory rather
  than an `if`/`elif` chain whose last `else` silently assumed a shape. `weft_store.fields._ADMITTED[
  FieldKind.EXTENSION]` needed a different fix, because its defect was not a fall-through but a
  *widen*: it read `frozenset(FilterOp) - {AND, OR, NOT}`, so it does not fail to notice a 13th
  member, it silently admits it. The nine members are now stated by hand — behaviourally identical
  for every operator that exists today, refusing (via `field_for`'s existing
  `FilterOpMismatchError`) anything a person has not explicitly added tomorrow.

  **The four more.** `weft_store.pgvector_store` publishes its own translator over the identical
  `FilterOp` vocabulary — `_predicate`, `_text_predicate`, `_text_set_predicate`,
  `_extension_predicate` — and every one had the same shape as the Qdrant side: an unhandled
  operator silently answered as `eq`/`ne`/`contains`, or (in `_predicate`) a hypothetical second
  combinator routed through the leaf branch as if it were one, mutually recursing with
  `to_qdrant_filter`'s own sibling defect one layer up. `docs/lessons.md` L5.14 logged why the
  ledger's own "known sites" list missed them: it was written by reading `weft_qdrant.store`, never
  by grepping `FilterOp` across the whole tree for the same dispatch shape.

  **The new error.** `weft_store.contract.UnhandledFilterOpError(WeftError, UnresolvedNameError)` —
  defined once, where `FilterOp` itself is, so `fields.py`, `pgvector_store.py` and
  `weft_qdrant.store` all import the one class rather than each inventing their own. `valid_options`
  names the operators *that site* translates, not the whole enum — the message is "you added a
  member and this translator does not know it yet," not "you spelled an operator wrong." Joins
  `NAME_RESOLUTION_FAMILY` in `tests/architecture/test_ff12_unresolvable_name_carries_options.py`
  (31 members now), and `manual/troubleshooting.md` gains its entry: the realistic trigger is a
  version-skew one, a store pack translating filters against an older `weft-store` than the one
  that published a new operator.

  **Fitness function 13**, `tests/architecture/test_ff13_filter_op_dispatch_is_exhaustive.py`. A new
  numbered function rather than a third clause of FF4 — FF4(b)'s own proof technique manufactures a
  name *nothing was told about* and proves the system still runs it, which is what makes a registry
  key space open; this function manufactures an operator nothing was told about and proves every
  dispatch *refuses* it, which is the mirror-image property for a closed vocabulary serialised into
  stored data rather than resolved against a live plugin set. `01` → *Fitness functions* item 13
  carries the argument in full. The check builds a `FilterOp`-shaped `StrEnum` value none of the
  twelve real members equal (`_unknown_op()`), drives all nine fixed dispatch sites with it through
  `pytest.raises(UnhandledFilterOpError)`, and asserts the manufactured value is admitted by none of
  `weft_store.fields._ADMITTED`'s three `FieldKind` sets. `test_the_check_can_actually_fail`
  reproduces the pre-fix shape of `_range` inline (three named branches, one unconditional
  `return "gte"`) and shows it answers instead of raising for the identical manufactured operator —
  proof the assertions above are not vacuous. Reaching several of these dispatch functions directly
  required bypassing pydantic's own field validation (`Filter.model_construct`, since `op: FilterOp`
  refuses any string that is not a real member before a validator ever runs) and pyright's
  `reportPrivateUsage` (a small `_private(target, name)` helper using `getattr` with a string
  literal, which types as `Any` rather than tripping the check — no suppression comment anywhere in
  the file).

  **Run outside the repository:**

  ```
  $ weft --version
  weft 0.1.0

  $ weft index corpus
  produced 1, nothing to produce 0, failed 0. nodes now stored: 2.
  mode 'repair' — 1 participant(s):
    pgvector (weft-store): examined 0, removed 0, backfilled 0
  exit=0

  $ weft ask --retrieve-only "what is a closed operator vocabulary"
  1. Weft is a microkernel RAG engine. Filters are data: a serialisable Pydantic AST with a closed
  operator vocabulary. Every dispatch over that vocabulary must be exhaustive by construction.

  exit=0
  ```

  Nothing in the CLI takes a `--filter` flag yet — `MetadataFilter.matching` has no pipeline stage
  or command reaching it with operator-carrying input authored by a person, so "a pipeline document
  carrying a filter" has nothing to build against today; recorded here rather than faked. The two
  required failure paths are demonstrated directly against the installed, shipped packages instead,
  from the same outside-the-repository directory:

  ```
  $ python -c "
  from weft_store.fields import field_for
  from weft_store.contract import FilterOp
  field_for(FilterOp.EQ, 'metadata.author')
  "
  UnaddressableFieldError: filter field 'metadata.author' reaches nothing on a Node. The core fields
  are: content, id, lineage.parents, lineage.sources, media_type. Anything a pack attached is under
  'ext.<namespace>.<field>', where <namespace> is the distribution that owns it — 'ext.weft-pdf.backend',
  say.
  valid_options: ('content', 'id', 'lineage.parents', 'lineage.sources', 'media_type')

  $ python -c "
  from weft_store.fields import field_for
  from weft_store.contract import FilterOp
  field_for(FilterOp.EQ, 'lineage.sources')
  "
  FilterOpMismatchError: filter operator 'eq' cannot apply to field 'lineage.sources', which holds a
  set of strings. use 'contains', which asks whether the value is one of the set's members.
  ```

  And this task's own fix, proven against the installed packages rather than only against
  `tests/architecture`: a `FilterOp` member neither translator has been taught (`model_construct`
  standing in for the moment `FilterOp` itself grows one, since pydantic's own field validation
  refuses an unrecognised string outright today — shown failing first, honestly, before the
  bypassed call):

  ```
  UnhandledFilterOpError: weft-qdrant's filter translator has no top-level case for 'between'. It
  translates the combinators 'and', 'or', 'not' and the leaf operators contains, eq, exists, gt,
  gte, in, lt, lte, ne.
  valid_options: ('and', 'or', 'not', 'contains', 'eq', 'exists', 'gt', 'gte', 'in', 'lt', 'lte', 'ne')

  UnhandledFilterOpError: 'between' is a FilterOp this validator has no shape rule for. Every
  operator must have one, named here rather than assumed — the operators it knows are: and,
  contains, eq, exists, gt, gte, in, lt, lte, ne, not, or.
  ```

  All green: `poe ci-checks` (106 architecture tests, 1740 passed/1 skipped), run in the foreground.
  `docs/lessons.md` L5.14 logged: the ledger's own "five known sites" line was written by reading one
  backend's translator and never grepping `FilterOp` across the tree, which is why it missed
  `weft_store.pgvector_store`'s four — the reference's own "doing it by hand at nine sites is why three
  sites do not," one level up.
- [x] **5.2c** a pack can read what an older version of itself wrote, or say precisely why it cannot: `ExtModel.__schema_version__` is mandatory at class definition, written into the dumped namespace, and `upgrade(data, from_version)` **refuses by default** naming the namespace, the stored version and the current one · owner `02` §1 → *The payload model*; `05` → G9 · turns on — · sha `f913380` · **must land before 5.4**, because the graph pack ships the first third-party `ExtModel` and a mandatory declaration added after it would break this phase's own exit demonstration

  **Mandatory at class definition, the same seam `__namespace__` already uses.**
  `ExtModel.__pydantic_init_subclass__` (`weft_kernel/payload/ext.py`) now checks two declarations,
  not one, and `weft_kernel.registry.required_declarations` was deliberately not reused: that
  mechanism fires at plugin *registration*, and an `ExtModel` is never registered — it is a
  `BaseModel` a pack imports and instantiates directly, so class-definition time is the only seam
  that exists for it. A subclass missing either declaration fails the moment the `class` statement
  runs, naming the class and citing `02` §1.

  **The version travels in the bytes.** `SCHEMA_VERSION_KEY = "__schema_version__"` is written into
  every namespace's dumped dict by `ext.py`'s own `_dump` — the one place a namespace's plain-dict
  form is already assembled from `model.model_dump()`, so it is the one place a version read off
  the *class* (never the instance) can be added without being dropped the way `Filter.version`, a
  bare `ClassVar`, always was. Proven by `tests/unit/weft_kernel/payload/test_node.py`'s own
  `test_ext_survives_model_dump_and_json_with_subclass_fields_intact`, extended to assert
  `dumped["ext"]["weft-graph"][SCHEMA_VERSION_KEY]` on a real `Node`, through both `model_dump()`
  and `model_dump_json()`.

  **The read path.** `weft_store.rehydrate.rehydrate_ext` pops `SCHEMA_VERSION_KEY` off the stored
  mapping (`None` if absent) and compares it against the registered class's current
  `__schema_version__`; a match rehydrates exactly as before this task, anything else is handed to
  `model_cls.upgrade(fields, stored_version)`. The default `upgrade` raises
  `SchemaVersionRefusedError`, naming the namespace, the stored version and the current one — not a
  `NAME_RESOLUTION_FAMILY` member, checked and rejected deliberately, because there is no alternative
  *name* to offer, the same reasoning that already excludes `DuplicateRegistrationError`.
  `manual/troubleshooting.md` gains its entry (the coverage ratchet in
  `tests/docs/test_troubleshooting_coverage.py` caught its absence on the first `ci-checks` run).

  **Data written before this task carries no version at all, and that is not treated as
  current.** `stored_version` is `None` when the key is absent, and `None != model_cls.
  __schema_version__` for every real class, so an unversioned row is routed through `upgrade`
  exactly like a genuine mismatch — the refusal names *"no version at all (written before schema
  versioning existed)"* rather than fabricating a version that was never written. The alternative —
  treating an absent key as "must be current" — is exactly the silent fallback CLAUDE.md forbids,
  and this task's own binary run met a real row shaped that way in the running container.

  **Every `ExtModel` in the tree gained the declaration, all starting at `1.0.0`** — nothing had
  shipped a second shape of any of them, so there is no earlier version for `1.0.0` to be a bump
  from: `weft_kernel.payload.node.SyntheticOrigin`, `weft_chunk.payload.ChunkOffset`,
  `weft_clean.language.Language`, `weft_enhance.keywords.Keywords`, `weft_pdf.document.PdfPages`,
  `weft_index.payload.Representation`, `weft_retrieve.corrective.CorrectiveTrace`,
  `weft_retrieve.boolean.BooleanPlan`, `weft_retrieve.iterative.IterativeRetrievalTrace`,
  `weft_generate.refine.RefinementTrace`, `weft_generate.contradiction.Agreement`, and the stranger
  pack's own `weft_example_ingest.enhancer.WordCount`. Roughly forty test-only `ExtModel` fixtures
  across the tree needed the identical one-line addition to keep constructing at all.

  **Kernel budget.** 2,933 lines against the 3,500 ceiling — +42 from this task (`ext.py`'s
  mandatory check, `upgrade`, `SchemaVersionRefusedError`, and `SCHEMA_VERSION_KEY`'s injection into
  `_dump`) — still past the 2,800 review trigger this phase already carried into 5.2a/5.2b (measured
  2,891 there), not newly crossed by this task.

  **Run outside the repository, against the real container — including the row already in it:**

  ```
  $ weft --help
  usage: weft [-h] [--version] [--json | --quiet] command ...
  Weft — a microkernel RAG engine.
  [...]
  $ weft init && weft index .
  wrote weft.toml.
  produced 1, nothing to produce 0, failed 0. nodes now stored: 2.
  mode 'repair' — 1 participant(s):
    pgvector (weft-store): examined 0, removed 0, backfilled 0

  $ weft ask "microkernel" --retrieve-only --top-k 5
  1. Weft is a microkernel RAG engine. Task 5.2c gives every ExtModel a mandatory schema version.

  $ python -c "
  from weft_kernel.payload import ExtModel
  class MissingVersion(ExtModel):
      __namespace__ = 'acme-pack'
  "
  TypeError: MissingVersion must declare a non-empty __schema_version__ — the version of this
  namespace's own shape, carried in every dumped instance so a reader can tell an old row from a
  current one even when the pack that wrote it is not installed (docs/02-extension-model.md §1)
  ```

  The running container already held one row from an earlier task's own fixture (`ext =
  {"weft-kernel": {"reason": "test fixture"}}`, no version key at all — an ordinary
  `Node.synthetic` root with an embedding of `NULL`, invisible to vector search and so never
  surfaced through `weft ask` itself). Read directly off the real table and fed through the real,
  installed `weft_store.pgvector_store._row_to_node`:

  ```
  $ python -c "<fetch the real row, call _row_to_node on it>"
  raw stored ext: {'weft-kernel': {'reason': 'test fixture'}}
  SchemaVersionRefusedError: 'weft-kernel' data was written at no version at all (written before
  schema versioning existed), but the installed class is at '1.0.0' and declares no upgrade path
  from it. Override weft-kernel's ExtModel.upgrade(data, from_version) to migrate this shape, or
  reindex the corpus so this namespace is rewritten at the current version.
  ```

  A deliberate version mismatch, staged the same way — one real, freshly-indexed `weft-chunk` row
  rewritten in place to claim `__schema_version__: "0.9.0"`, read back through the CLI's own
  bootstrap (`weft_cli.registry_bootstrap.build_dependencies`, which is what actually populates
  `ext_models` for `weft-chunk` — see the lesson below) and `weft_store.rehydrate.rehydrate_ext`:

  ```
  raw stored ext (deliberately rewritten to an older version): {'weft-chunk': {'start': 0,
  '__schema_version__': '0.9.0'}}
  SchemaVersionRefusedError: 'weft-chunk' data was written at version '0.9.0', but the installed
  class is at '1.0.0' and declares no upgrade path from it. Override weft-chunk's
  ExtModel.upgrade(data, from_version) to migrate this shape, or reindex the corpus so this
  namespace is rewritten at the current version.
  ```

  Both rows were restored to their correct, current-version shape afterward (`weft index .`
  re-derives content-addressed, so re-indexing overwrites rather than duplicates) — the container
  was left exactly as it was found, working.

  All green: `poe ci-checks` (106 architecture tests; 1746 passed, 1 skipped) and `poe
  kernel-isolated`, both run in the foreground. `docs/lessons.md` L5.15 logged: proving the
  version-mismatch path found that only `weft-retrieve` and `weft-pdf` actually call
  `weft_store.register_ext_model` for their own `ExtModel`s — `weft-chunk`'s gap is papered over by
  a CLI-side shim (`_ensure_chunk_offset_rehydrates`) nothing else has, and `weft-enhance`,
  `weft-clean`, `weft-index` and `weft-generate` have no shim at all, so a node carrying any of
  their own namespaces cannot survive a real store round trip today — a gap `02` §1's own Phase 0
  narrowing note already named and left open, out of scope for this task but worth a task before
  5.3's pack-author guide is written.
- [x] **5.2d** the guarantee requirement 5 makes is one a script can read: `valid_options` crosses the process boundary in a structured error envelope under `--json`, carrying the `WeftError` subclass name as the promised failure identity and the human string as a `rendered` field · owner `03` → *Output*; `09` §3 · turns on — · sha `04a9c19` · **the ledger line said `--format json`; the code does not agree** — `--format json` is `weft ask`'s own per-command result shape (`weft_cli.output.AskFormat`), the only command that has one; `render_refusal` runs for every command's own failure, so the flag this task attaches to is the global `--json` `docs/03-cli.md` already uses to pick the run's `TokenSink`, read here as `isinstance(deps.token_sink, JsonSink)`

  **Two catch sites, one envelope.** `weft_cli.error_envelope.ErrorEnvelope` (new module) carries
  `error` (`type(exc).__name__`), `rendered` (`str(exc)`, whole), `exit_code`, `valid_options`
  (`None` unless `exc` is a `weft_kernel.errors.UnresolvedNameError`), and `pack`/`contract`/
  `plugin`/`stage` — `weft_kernel.seam.wrap`'s own attribution, carried through rather than
  re-derived. `envelope_version` travels in the data as a plain field with a default, not a
  `ClassVar`, on the identical principle 5.2c's `ExtModel.__schema_version__` settled for a
  persisted schema, pointed at a wire format instead — additive only, `09` §3's own `--porcelain
  =v1` warning is why nothing here is ever frozen. `weft_cli.render.render_refusal` grew a
  keyword-only `as_json`: `False` (every existing caller) is byte-identical to before this task;
  `True` builds the envelope and puts it on `stdout` with nothing on `stderr`, the same way
  `weft_cli.sinks.JsonSink` already puts every event on `stdout` rather than splitting a run
  across two streams. `weft_cli.cli.run_command` decides it from `deps.token_sink`'s own type;
  `weft_cli.cli.main`'s own discovery-failure catch (`build_dependencies`/`build_parser` failing
  before a `Command` is even chosen, so `render_refusal`'s `CommandRefusalError` branch could
  never apply there) decides it from `json_flag` directly and calls the envelope builder itself.

  **Measured reach.** `grep -rn "valid_options=" packages/weft-cli/src | wc -l` = 22 raise sites
  constructing a `WeftError` with the field (unchanged by this task — it adds a consumer, not a
  raise site); `NAME_RESOLUTION_FAMILY` is 31 members tree-wide. Every one of the 22 in `weft-cli`
  is now reachable from a renderer: each is raised either during `build_dependencies` (caught by
  `main`'s discovery-failure catch) or during a `Command`'s own `run()` (caught by `run_command`'s
  `except WeftError`), and fitness function 12(b)'s own ratchet already proves the tree contains
  zero catch-and-repack sites that would strip the field before either catch runs — so **22 of
  22**, not a sample. (S6's own "78" counted every textual mention of `valid_options` in
  `weft-cli`, not raise sites — 81 today, three more added by 5.2b/5.2c's own docstrings since;
  loose the way `03`'s own prose is loose, which is this task's own opening line.)

  **Human output is unchanged.** `as_json=False` is the default and every pre-existing caller;
  `tests/unit/weft_cli/test_render.py::test_render_refusal_puts_str_exc_on_stderr_when_json_was_
  not_asked_for` pins the exact pre-task string. No renderer, docstring example or CLI string a
  human reads was reworded.

  **Run outside the repository, against the real container:**

  ```
  $ weft init && weft index docsdir
  wrote weft.toml.
  produced 1, nothing to produce 0, failed 0. nodes now stored: 2.
  mode 'repair' — 1 participant(s):
    pgvector (weft-store): examined 0, removed 0, backfilled 0

  $ weft ask "hello" --pipeline nope
  'nope' is not a pipeline this project knows — checked the project's own 'pipelines' directory
  and every installed pack's own contribution. Known pipelines: no-retrieval,
  retrieve-then-generate, route.
  $ echo $?
  4

  $ weft --json ask "hello" --pipeline nope
  {"type":"done","role":"","text":"","message":""}
  {"envelope_version":"1.0.0","error":"UnknownPipelineNameError","rendered":"'nope' is not a
  pipeline this project knows — checked the project's own 'pipelines' directory and every
  installed pack's own contribution. Known pipelines: no-retrieval, retrieve-then-generate,
  route.","exit_code":4,"valid_options":["no-retrieval","retrieve-then-generate","route"],
  "pack":"weft-cli","contract":"Command","plugin":"ask","stage":"command:ask"}
  $ echo $?
  4

  $ weft --json ask "hello" --pipeline nope 2>/dev/null | jq -c 'select(has("error")) |
      {error, valid_options, exit_code}'
  {"error":"UnknownPipelineNameError","valid_options":["no-retrieval","retrieve-then-generate",
  "route"],"exit_code":4}
  ```

  `jq` never touches the sentence at all — `valid_options` is read as a JSON array, structurally,
  the property this task exists to make true. Two more failure modes, each driven human and
  `--json`, both landing the identical envelope shape (`weft --json ask "hello"` against `[services]
  store = "no-such-store"` → `UnknownPluginError`, `valid_options: ["pgvector","qdrant"]`;
  `weft --json index docsdir` against `[services] embed = "no-such-embedder"` →
  `UnresolvedPluginNameError`, `valid_options: ["hash","openai"]`), plus the discovery-time path
  (`weft --json ask "hello"` against a malformed `weft.toml` → `{"error":"ConfigFileError",
  "rendered":"weft.toml is not valid TOML: ...","exit_code":4,"valid_options":null, ...}`, no
  `DONE` event ahead of it — no `Command` ever ran to close a sink). A bad flag (`weft ask
  --not-a-flag`) is untouched either way: `argparse`'s own exit 2, before any `WeftError` exists.

  All green: `poe ci-checks` (106 architecture tests; 1759 passed, 1 skipped) run in the
  foreground; `scripts/generate_contract_reference.py`/`generate_command_table.py` regenerated
  with no diff — no published `Command`/Protocol surface changed. `docs/lessons.md` L5.16 logged:
  the transcript above shows `--json`'s stdout carrying two JSON shapes on one stream with no
  shared discriminant (a bare `StreamEvent` and this task's own `ErrorEnvelope`), out of scope for
  this task to fix.
- [x] **5.2e** version skew and deprecation are visible where an operator already looks: `weft plugins doctor` reports a distribution whose installed version does not satisfy a declared specifier, and marks a deprecated surface as **a flag on an existing status**, never a new one · owner `09` §3; `02` §2 · turns on — · sha `74178b0`

  **Skew: two sources that can genuinely disagree, never one derived from the other.** `weft_cli.
  skew.detect_skew()` reads, per requiring distribution, its own declared requirement strings
  (`importlib.metadata.requires`, PEP 508, parsed with `packaging.requirements.Requirement`) and
  compares each `weft-...`-named one against that *other* distribution's actually installed
  version (`importlib.metadata.version`) — G9 answer 1's own two halves: "the distribution
  dependency specifier" against what is "detected... by `weft plugins doctor`." Filtered to
  `weft-...` by prefix, never a maintained list of "the weft distributions," so a third-party
  pack's own mis-declared range is caught exactly as a first-party one's would be. Distinct from
  fitness function 6 (`test_ff6_contract_version_binding.py`), which AST-parses `contract.py`
  against `pyproject.toml` at the checked-out tree — a build-time question about what was
  *published*; this module never opens either file and asks only what is *installed*, which is
  why the honest question in the task brief has an honest answer: **in a `uv sync`ed workspace
  nothing is skewed, by construction**, because `uv` already refused an incompatible resolution
  before the environment existed. `weft-cli` lives in `weft-kernel`, not the kernel: G9's own
  words, "the kernel gains zero lines" — `detect_skew` is a new module in `weft-cli` alone.

  **Deprecation: marked at registration, warned by the wrapper, no new status.**
  `weft_kernel.discovery.PackRegistrar.deprecate(surface, reason=...)` buffers a
  `weft_kernel.seam.Deprecation` exactly as `add_pipeline_resource` buffers a `PipelineResource` —
  nothing survives a `register()` that raises. Once a pack's buffer commits, `discovery._activate`
  hands whatever it collected to `weft_kernel.seam.warn_deprecated`, a new function beside `wrap`/
  `wrap_flush` that emits one `DeprecationWarning` per notice — `09` §3's own words, "the warning
  is emitted by the registration wrapper... an author has to remember to print is a deprecation
  notice that will not be printed." `PackReport.deprecations` travels with every report;
  `weft_cli.plugins_report` reads a non-empty tuple as a flag beside `status` — `", deprecated"`,
  the identical shape `", ambient"` already takes — and prints each surface/reason as a detail
  line. `02` §2's status vocabulary gained a documented **row**, not a `PackStatus` member.

  **Kernel: 2,961 lines against the 3,500 ceiling (+28 from 5.2c's 2,933), still past the 2,800
  review trigger this phase has carried since 5.2a/5.2b.** The 28 lines are entirely the
  deprecation half — `Deprecation`, `warn_deprecated`, `PackRegistrar.deprecate`/`.deprecations`,
  and `PackReport.deprecations` — because G9 answer 1 says so in as many words and this task holds
  to it: skew detection added **zero** kernel lines.

  **Nothing becomes a refusal.** A skewed pack still registers and still runs; a deprecated
  surface still registers and still runs. Neither `detect_skew` nor `PackRegistrar.deprecate`
  raises, and `weft plugins doctor` itself still runs with `strict_pins=False` exactly as before —
  proving the report fires is what the transcript below is for, not a new failure mode for
  `doctor` itself to trip on.

  **Proven firing, not merely present — two failure paths, both against a real, force-modified
  environment outside the repository (`docs/lessons.md` L5.1's own defect: a mechanism asserted
  without being run).** A `cp -R .venv` throwaway copy had `weft-kernel`'s own installed
  `.dist-info/METADATA` hand-edited from `Version: 0.1.0` to `Version: 9.9.9` — a stand-in for the
  three cases `09` names (editable, forced, workspace drift) — and a throwaway pack (`weft-demo-
  pack`, `uv pip install --python <copy>/bin/python3 -e ... --no-deps`, never part of this tree)
  registered one plugin and called `registrar.deprecate(...)`. `docs/lessons.md` L5.18 logged a
  trap this cost: a copied venv's console script still shebangs into the *original* interpreter,
  so every invocation must go through `<copy>/bin/python3 <copy>/bin/weft` explicitly, never the
  script alone, or the copy is silently never actually running.

  ```
  $ weft plugins list
  weft-canary: active (0 contributed)
  ...
  weft-demo-pack: active, deprecated (1 contributed)
  ...
  weft-store: failed (0 contributed)

  $ weft plugins doctor
  ...
  weft-demo-pack: active, deprecated (1 contributed)
    disclosure: not disclosed
    deprecated: '_Legacy:old-retriever' — superseded by 'fast-retriever'; removed in
  weft-demo-pack 2.0
  ...
  weft-store: failed (0 contributed)
    reason: 'weft-store' settings failed validation: 1 validation error for PgVectorSettings
  dsn
    Field required [type=missing, input_value={}, input_type=dict]
      For further information visit https://errors.pydantic.dev/2.13/v/missing
    disclosure: not disclosed

  version skew — installed does not satisfy a declared specifier:
    'weft-canary' requires 'weft-kernel' <1.0.0,>=0.1.0, but 9.9.9 is installed.
    'weft-chunk' requires 'weft-kernel' <1.0.0,>=0.1.0, but 9.9.9 is installed.
    ... (19 requiring distributions total, every one of them, all correctly named)
    'weft-store' requires 'weft-kernel' <1.0.0,>=0.1.0, but 9.9.9 is installed.

  tracing: not configured — spans stay on the no-op default and go nowhere. ...

  $ PYTHONWARNINGS=always weft plugins doctor 2>&1 1>/dev/null | grep deprecated
  .../weft_kernel/discovery.py:695: DeprecationWarning: 'weft-demo-pack' marks
  '_Legacy:old-retriever' deprecated: superseded by 'fast-retriever'; removed in weft-demo-pack 2.0
    warn_deprecated(deprecations)
  ```

  The demo pack was uninstalled, the `.dist-info/METADATA` edit and the copied venv were both
  discarded, and a clean-case run against the real, unmodified `.venv` (still outside the
  repository) printed neither block — confirmed by diff against the transcript above, not assumed.
  `weft --version` and `weft --help` were re-checked against the same clean binary: fitness
  function 8(b) — zero pack code for `--version` — still holds, and `weft nope` still exits 2 with
  argparse's own "invalid choice" naming every real subcommand.

  All green: `poe ci-checks` (106 architecture tests; 1774 passed, 1 skipped) run in the
  foreground; `scripts/generate_contract_reference.py`/`generate_command_table.py` regenerated
  with no diff — no published `Command`/Protocol surface changed. `manual/operations-guide.md`
  gained a paragraph beside its existing `ambient` documentation; `manual/troubleshooting.md`'s
  ratchet needed no new entry, since neither half of this task adds a `WeftError` subclass or a
  `PackStatus` member — `tests/docs/test_operations_guide.py`'s own `PackStatus`-exactness check
  is unaffected for the identical reason. `docs/lessons.md` L5.17 and L5.18 logged: an import
  stripped between edits by the repository's own auto-fix hook before its first usage landed, and
  the copied-venv shebang trap above.
- [x] **5.2f** the artefact the deprecation promise is made in is written to rather than hoped for: a `tests/docs` check asserts every surface marked deprecated at registration has a `CHANGELOG.md` entry naming it · owner `09` §3; `08` · turns on — · sha `4dca8cc` · `CHANGELOG.md` has been touched in one commit and is stale by five phases, which is why this is a check and not a sentence

  **Two independent sources, per `docs/lessons.md` L5.6.** `tests/docs/test_changelog_deprecation_
  coverage.py`'s real check asks the **installed tree** — `weft_kernel.discovery.discover(Registry())`
  against the real, installed `weft.packs` group, the identical call `weft plugins doctor` makes,
  folded to every `PackReport.deprecations`'s `surface` — and asks **the document** — `CHANGELOG.md`
  read off disk — whether it names each one as a literal, backtick-quoted mention. Neither is derived
  from the other. `08` §3's own table gains row (e); `docs/09-release.md` §3's block quote gains a
  paragraph recording the check built and naming the protocol question (below) left open.

  **The floor, stated honestly rather than forced — `docs/lessons.md` L5.19 logs the finding.** Zero
  first-party surfaces are deprecated today, so asserting the real, installed set non-empty would be
  false, not a floor. The floor actually carried is `test_the_comparison_can_actually_fail`: a real
  `Deprecation`, produced through `PackRegistrar.deprecate` → `commit` — never a hand-built stand-in
  — proves the comparison reports `'legacy-widget-plugin'` missing against today's real
  `CHANGELOG.md` and clears once an entry naming it is appended, the same shape `test_ff9_extension_
  from_outside.py::test_the_grep_can_actually_fail` and `test_ff6_contract_version_binding.py::test_
  the_check_can_actually_fail` already use. Proven red, then green, directly:

  ```text
  $ uv run pytest tests/docs/test_changelog_deprecation_coverage.py -v
  test_today_the_installed_tree_marks_nothing_deprecated PASSED
  test_the_comparison_can_actually_fail PASSED
  test_a_waived_surface_is_excused PASSED
  test_every_real_deprecation_has_a_changelog_entry PASSED
  4 passed in 0.66s
  ```

  And, forcing the real check itself red by swapping `_real_deprecations` for a stub returning
  `frozenset({"not-really-deprecated-anywhere"})` (a surface no real pack marks and the real
  `CHANGELOG.md` never names):

  ```text
  E       AssertionError: ['not-really-deprecated-anywhere'] marked deprecated at registration with
  no `CHANGELOG.md` entry naming it. Add a bullet naming `not-really-deprecated-anywhere` under
  `### Deprecated`, or name it in DEPRECATIONS_WITHOUT_CHANGELOG_ENTRY if it is deliberately excused.
  1 failed in 0.05s
  ```

  reverted immediately after (`diff` against the pre-break file confirmed byte-identical) — the
  identical proof-then-revert discipline `test_ff8_trust_model.py`'s own record uses.

  **`CHANGELOG.md` stops being five phases stale.** Rewritten from "Nothing released yet. Phase 0...
  is not built" to an `[Unreleased]` entry (nothing is published to an index before Phase 6, `09` §2.2
  — every entry is `[Unreleased]` for that reason, not because nothing shipped) naming what each of
  Phases 0–4 actually shipped and Phase 5's work so far, derived from `docs/build-ledger.md`'s own
  ticked entries and `git log --oneline` rather than invented, plus the `COMMAND_CONTRACT_VERSION`
  correction and the real dependency ranges task 5.2a gave every distribution. No distribution
  version numbers are restated in it — a second, hand-copied list of the digits already living in
  each `pyproject.toml` is the two-lists bug aimed at version numbers instead of prose.

  **The protocol question, judged rather than deferred silently.** `docs/lessons.md` L5.8 named two
  candidate homes — `README.md` → *Protocol* / `phase-step` → *Finish*, or a `tests/docs` check. The
  ledger chose the check, built here. **Judgement:** a check and a protocol line are not mutually
  exclusive, and this check fires only on a *deprecation* — the rest of `CHANGELOG.md` (every
  non-deprecation `Added`/`Changed`/`Fixed` entry) has no mechanism keeping it current at all, which
  is exactly as unmaintained as before this task. Whether `README.md` → *Protocol* should gain a line
  requiring a changelog update on every phase close is left **open, for `implement-ll` to act on or
  decline** at this phase's drain — not edited here, per this task's own instruction not to touch
  `.claude/skills/` in isolation.

  **Measured.** `uv run poe ci-checks` green: **1,778 passed, 1 skipped, 106 architecture tests**
  (four tests gained, all in the new file; `poe test`'s own composite sweeps `tests/docs/`
  automatically — `08` §3 *decision D1*, no second reachability proof needed). `uv run poe
  kernel-isolated` green (`weft-kernel imports standalone`). **Kernel line delta: zero** — nothing
  under `packages/weft-kernel` changed.

  **Run outside the repository**, shipped binary, real installed venv:

  ```text
  $ weft --version
  weft 0.1.0

  $ weft plugins doctor
  weft-canary: active (0 contributed)
  ...
  weft-otel: active (0 contributed)
    disclosure: network=[], filesystem=[], subprocess=[], note="Sets the process OpenTelemetry
    TracerProvider from [packs.weft-otel] settings. ..."
  ...
  weft-store: failed (0 contributed)
    reason: 'weft-store' settings failed validation: 1 validation error for PgVectorSettings
  dsn
    Field required [type=missing, input_value={}, input_type=dict]
  tracing: not configured — spans stay on the no-op default and go nowhere. ...
  exit=0
  ```

  No `deprecated` flag on any block — correct: nothing real is marked deprecated today, exactly what
  `test_today_the_installed_tree_marks_nothing_deprecated` pins. Two failure paths:

  ```text
  $ weft nope
  usage: weft [-h] [--version] [--json | --quiet] command ...
  weft: error: argument command: invalid choice: 'nope' (choose from ask, config, delete, eval,
  index, init, pipeline, plugins, reconcile, trace)
  exit=2

  $ weft ask "hello"
  no 'pgvector' is registered for NodeStore. It is unavailable because no distribution has
  registered that name for this contract. Names registered for NodeStore: 'qdrant'.
  exit=4
  ```

  `weft --help` from the scratch directory printed help and exited `0` — no REPL, the Phase 3 scar
  named in `CLAUDE.md` stayed shut. No artefact left behind: the scratch directory was empty on
  entry and removed after. `docs/lessons.md` L5.19 logged: `08` §3's floor clause, read literally,
  demanded a real-world non-emptiness assertion that would have been false for this check's
  legitimately-empty-today subject; the actual floor is a self-test proving the comparison is not
  vacuous, which is what this task built instead.
- [x] **5.2g** a pack's own `ExtModel` survives a round trip through a store without anyone editing the CLI: a pack contributes its ext models at registration, and a fitness function fails on an `ExtModel` no pack contributes · owner `02` §1 → *The payload model*; `02` §2 · turns on FF14 · sha `edfce8d` · **added 2026-08-22, logged as `S7`**, and it **landed before 5.3 and 5.4**.

  **The seam**: `weft_kernel.discovery.PackRegistrar.add_ext_model(model)` buffers a bare
  `type[ExtModel]` reference exactly like `add_pipeline_resource`/`deprecate` — no
  validation, no instantiation, nothing the kernel could get wrong about a capability it
  does not name. `ExtModel` is a payload primitive the kernel already owns (`Node.ext`'s
  own declared value type), not a capability, so the kernel learns nothing about stores by
  buffering a class reference to one. `PackReport.ext_models` carries the buffer once
  `register()` commits; `weft_store.rehydrate.register_from_reports(reports)` is the
  generic consumer that reads every report's `ext_models` back and registers each class —
  wired into `weft_cli.registry_bootstrap.build_dependencies`, once, right after
  `discover()`, with no pack named at that call site. `weft_chunk`, `weft_clean`,
  `weft_enhance`, `weft_pdf` and `weft_index` all call `add_ext_model` in their own
  `register()` now; `_ensure_chunk_offset_rehydrates` — the shim that proved the gap,
  hand-registering `ChunkOffset` alone from inside `weft-cli` — is **deleted**. The
  stranger pack `examples/weft-example-ingest` calls it too, for its own `WordCount`,
  which is the real proof per fitness function 9(a): that distribution is installed
  rather than linked, and its `ExtModel` reaches `ext_models` with nobody here having
  anticipated it.

  **Correction to this line's own text, found building it — logged as `docs/lessons.md`
  L5.20.** `weft-generate` and `weft-retrieve` do **not** call `add_ext_model`, and that is
  a finding, not an omission. `weft_retrieve.boolean.BooleanPlan`, `weft_retrieve.
  corrective.CorrectiveTrace` and `weft_retrieve.iterative.IterativeRetrievalTrace` all
  share `__namespace__ = "weft-retrieve"`; `weft_generate.contradiction.Agreement` and
  `weft_generate.refine.RefinementTrace` share `"weft-generate"`. All five attach to
  `QuerySet.ext`/`Candidates.ext`/`Answer.ext`, never to `Node.ext`, and only a `Node` is
  ever handed to a `NodeStore` — `rehydrate_ext` is never called with a query-path
  payload's `ext`, so none of the five needs this registry. Registering all five as first
  drafted would have raised `DuplicateRegistrationError` the moment two of the five
  techniques were active in one run, which `weft-generate`'s own default registrations
  (`contradiction-check` and `refine-on-uncertainty`) already are — `ext_models` holds one
  class per namespace, globally, with no pin mechanism reachable from it. `docs/
  02-extension-model.md` §1's own "Built in Phase 5 task 5.2g" block records the argument
  in full.

  **Fitness function 14** (`01` → *Fitness functions*), `tests/architecture/
  test_ff14_ext_model_reaches_rehydration.py`: two independently-computed sets — every
  namespace any `ACTIVE` `PackReport.ext_models` names (*declared*) against every
  namespace `weft_store.rehydrate.ext_models.names_for(ExtModel)` actually holds after
  `register_from_reports` runs (*present*) — asserted equal, against a fresh, monkeypatched
  registry so pytest's own collection order cannot leak into the result. Proven able to
  fail (`test_the_check_can_actually_fail`) by withholding one real, contributing pack's
  own report from `register_from_reports` and showing the comparison catches exactly that
  pack's namespace missing. A new numbered function rather than a clause of fitness
  function 5, whose wording reads as though it already covers this: item 5 already has a
  real, distinct, unclaimed subject (the extractor accept set, `docs/11-multimodal.md`'s
  own task 1.13), and folding a second property in would make one numbered item answer two
  different questions — `01` item 14's own note has the argument in full.

  **Registered-namespace count, measured**: **1 → 6** (`weft-kernel`, `weft-chunk`,
  `weft-clean`, `weft-enhance`, `weft-pdf`, `weft-index`), plus the stranger's own
  `weft-example-ingest` when that distribution is installed (fitness function 9(a)'s
  own throwaway environment, not this workspace's `.venv`). Kernel line count: **2961 →
  2970** (+9 — `PackRegistrar.add_ext_model`/`.ext_models`, `PackReport.ext_models`, the
  `_activate` wiring, and their docstrings), well under the 2800 review trigger already
  crossed at 5.2e and far under the 3500 ceiling.

  **Run outside the repository, against the real container** — the failure this task
  closes, captured before the fix (via a temporary `git stash` back to the pre-5.2g tree,
  same binary, same real container), then the identical sequence after:

  ```
  # before (git stash — the pre-5.2g tree)
  $ weft init
  wrote weft.toml.
  $ weft index corpus --extract pdf-text --yes
  produced 1, nothing to produce 0, failed 0. nodes now stored: 61.
  mode 'repair' — 1 participant(s):
    pgvector (weft-store): examined 0, removed 0, backfilled 0
  exit=0
  $ weft ask "what is the topic of this document" --retrieve-only
  no 'weft-pdf' is registered for ExtModel. It is unavailable because no distribution has
  registered that name for this contract. Names registered for ExtModel: 'weft-chunk',
  'weft-kernel'.
  exit=4

  # after (git stash pop — this task's own tree, same container, same stored rows)
  $ weft ask "what is the topic of this document" --retrieve-only
  1. t canonical correlation ρ1 betweenX andY is the supremum of the correlation coefﬁcients
  over their linear projections, ...
  [... four more ranked passages ...]
  exit=0
  ```

  The write path never failed — `PdfPages` was always written correctly, since a store's
  `add` never rehydrates anything. Only the read path — `weft ask`, a second process,
  exactly the "index, then a separate ask against a PDF corpus" scenario `weft_pdf.
  document.PdfPages`'s own docstring used to warn about — raised, and now does not.

  **Two other failure paths, unrelated to this task's own subject, run the same session**
  to confirm nothing else regressed:

  ```
  $ weft --help
  usage: weft [-h] [--version] [--json | --quiet] command ...
  ... (full command list; no REPL entered)
  exit=0

  $ weft index corpus --extract pdf-txt --yes
  --extract names 'pdf-txt', and no registered Extractor has that name. Registered
  Extractor names: 'pdf-layout', 'pdf-text', 'text'.
  exit=4
  ```

  **Measured**: `uv run poe ci-checks` green — 1,781 passed, 1 skipped, 108 architecture
  tests (one gained, `test_ff14_ext_model_reaches_rehydration.py`, two tests). `uv run poe
  kernel-isolated` green. `docs/lessons.md` L5.20 (the namespace-collision finding above)
  and L5.21 (a pre-existing, unrelated order-dependency in `test_ingest_pipeline.py`'s own
  earlier test, found while adding a sibling test to that file, confirmed pre-existing by
  `git stash` and left as a finding rather than a fix — out of this task's own scope).

  **Owed to task 5.3**: the pack author guide now also owes an author the instruction this
  task's own docstrings carry — declare an `ExtModel` through `registrar.add_ext_model` in
  `register()`, and only for a model that reaches `Node.ext`; a model attached to a
  query-path carrier (`QuerySet`/`Candidates`/`Answer`) does not call it. Not written here —
  5.3's own content is 5.3's to write.
- [x] **5.3** a stranger has everything they need before they start: the pack author guide covers a pack spanning several contracts plus a contributed command, adapted from the case `02` §4 already owns · owner `08` §1–§2; `02` §4 · turns on — · sha `f1d777b` · **re-derived at G9's close**: the guide now also owes a pack author the three things the ruling makes their responsibility — which dependency specifier to write and why a bare name is not one, that an `ExtModel` needs `__schema_version__` and an `upgrade` that refuses, and what a deprecation warning at registration obliges them to put in a changelog — **and now a fourth, from task 5.2g**: an `ExtModel` reaches storage only if `register()` calls `registrar.add_ext_model` on it, and only when it attaches to `Node.ext` rather than to a query-path payload

  `manual/pack-author-guide.md` §9 is the new section, adapted from `02` §4's graph-pack table —
  backed by two real packs rather than an invented one, since the graph pack itself is task 5.4's:
  `examples/weft-example-ingest/` (seven contracts, including `SourceDeletable`/`Reconcilable`
  satisfied structurally, plus a pack-owned `ExtModel`) for the multi-contract half, and
  `examples/weft-example-command/` for the contributed `Command`. Every `python`/`toml` sample is
  `path=`-tagged against one of those two, `packages/weft-store/pyproject.toml`, or
  `packages/weft-kernel/src/weft_kernel/payload/ext.py`'s citation, and `tests/docs/test_pack_guide_
  samples.py` passed against all of them unmodified. The dependency specifier (§9.3) cites G9's
  ruling and `docs/09-release.md` §2.3 answer 5, tagging `packages/weft-store/pyproject.toml` as the
  shape to copy; `__schema_version__`/`upgrade` (§9.4) and `add_ext_model` (§9.5) cite `packages/
  weft-kernel/src/weft_kernel/payload/ext.py:88-116` and `discovery.py:392-405`, plus `docs/lessons.md`
  L5.20's Node.ext-only rule; the deprecation obligation (§9.8) cites `PackRegistrar.deprecate`,
  `seam.warn_deprecated` and `tests/docs/test_changelog_deprecation_coverage.py`, with the honest
  narrowing that the check reads *this repository's* `CHANGELOG.md` and cannot see a stranger's own.
  §8's *Open gates you may hit* table was itself stale — G2, G7, G8 and G9 had all settled since it
  was written — and is corrected in this task rather than left to drift further.

  **Two rows of `02` §4's table could not be shown against real code, and §9 says so (§9.6, §9.7)
  rather than inventing a sample no check would cover — both logged as `docs/lessons.md` L5.22.**
  No pack anywhere in this tree can reach `weft_kernel.resolution.Contribution` from `register()`
  today: `weft_cli.pipeline_commands:32-40`'s own module docstring already names the gap and assigns
  it to whichever task first ships a slot-contributing pack, which this task confirmed by grep rather
  than took on faith, and by running `weft pipeline show route` outside the repository (below) —
  `unplaced contributions: (none)`, honestly, because nothing can supply one yet. And every
  `examples/*/pyproject.toml`, including both packs this section cites, still declares its `weft-*`
  dependencies as bare names: task 5.2a's own scope was `packages/`, never `examples/`, and no later
  task closed the gap. Neither is this task's to fix — 5.3 is the guide, not the examples or the
  kernel — and both are candidates for task 6.3's own version-bound fitness function and for task
  5.4 respectively.

  **Run outside the repository** (`/private/tmp/.../scratchpad/run53`), against the real container,
  with `examples/weft-example-ingest` and `examples/weft-example-command` built as real wheels
  (`uv build --wheel`) and installed into the shipped `.venv` — never `uv pip install <directory>`,
  for the identical reason fitness function 9(a) insists on it — then uninstalled again once the run
  below finished, leaving no trace in the tree or the venv:

  ```
  $ weft --help
  ...
    greet      greet somebody by name
    index      run an ingest pipeline over a directory. ...
  ...
  (no REPL — the Phase 3 scar stayed shut)

  $ weft plugins doctor
  weft-example-command: active (1 contributed)
    disclosure: not disclosed
  weft-example-ingest: active (7 contributed)
    disclosure: not disclosed
  ...
  (every other first-party pack unchanged, `weft-example-ingest` showing exactly the seven
  `registrar.add` calls §9.1 claims — `add_ext_model` buffers separately and is not counted here)

  $ weft greet Ada
  {"greeting":"Hello, Ada!"}

  $ weft greet                              # failure path 1 — missing required arg
  usage: weft greet [-h] [--yes] name
  weft greet: error: the following arguments are required: name
  exit=2

  $ python3 - <<'EOF'                       # failure path 2 — §9.4's claims, live
  from weft_kernel.payload import ExtModel
  class Bad(ExtModel):
      __namespace__ = "throwaway"
  EOF
  TypeError: Bad must declare a non-empty __schema_version__ — ...

  $ python3 - <<'EOF'                       # upgrade() refuses by default, live
  from weft_example_ingest.enhancer import WordCount
  WordCount.upgrade(WordCount(count=3).model_dump(), "0.9.0")
  EOF
  SchemaVersionRefusedError: 'weft-example-ingest' data was written at version '0.9.0', but the
  installed class is at '1.0.0' and declares no upgrade path from it. Override
  weft-example-ingest's ExtModel.upgrade(data, from_version) to migrate this shape, or reindex
  the corpus so this namespace is rewritten at the current version.

  $ weft pipeline show route                # §9.7's claim, confirmed rather than asserted
  ...
  unplaced contributions: (none)
  ```

  Everything the guide claimed a reader could do, this session did by reading only the guide and the
  files it tags — no gap surfaced that the guide did not already name as one (§9.6, §9.7).
- [x] **5.3a** a pack can offer a slot contribution, so `02` §4's table row is reachable: a pack contributes through its own `register()`, whatever assembles the registry collects them, and `resolve()` receives them · owner `02` §3 → *Slots*; `02` §4 · turns on FF15 · sha `2821015` · **added 2026-08-22, logged as `S8`**, and it **landed before 5.4**. Measured while closing 5.3: `Contribution` exists, `resolve()` takes a `contributions=` tuple, and resolution places, qualifies and records unplaced ones — but **nothing can produce one**. `PackRegistrar` offers `add`, `add_pipeline_resource`, `deprecate` and `add_ext_model` and no slot seam; `weft_cli.pipeline_commands` passes `contributions=()` and its own docstring says *"never a caller-assembled"*; `Contribution`'s docstring describes its caller as *"whatever assembled the `Registry` from every installed pack's own registration"*, which does not exist. The consuming half was built at task 1.11 and the producing half never was. **Separate from 5.4 deliberately**: 5.7 exists to detect whether a pack author needed a core change, so a graph-pack task that built this seam itself would make the core change and then report that none was needed

  **The seam, following `add_ext_model` (5.2g)/`deprecate` (5.2e)'s own shape, not a third
  mechanism.** `weft_kernel.discovery.PackRegistrar.add_contribution(slot, stage)` buffers
  a `weft_kernel.resolution.Contribution`, `distribution` filled in by the registrar — never
  stated by the pack, never something it could get wrong — exactly the same atomicity every
  other buffered call already gets: a `register()` that raises after calling this leaves no
  slot looking filled that was never actually committed. `PackReport.contributions` carries
  the buffer once `register()` commits. `weft_cli.registry_bootstrap.build_dependencies` is
  the one assembly point `Contribution`'s own docstring already named as "whatever assembled
  the `Registry`": `contributions_from(reports)` concatenates every report's own tuple into
  `Dependencies.contributions`, computed once, right after `discover()`, with no pack named at
  that call site. **Every `resolve()` call site in `weft-cli` reads it back off that one
  field** — `weft_cli.pipeline_commands._resolved_or_refuse` (`show`/`validate`/`diff`),
  `weft_cli.ingest._specs_from_document` (`weft index --pipeline`), and `weft_cli.
  route_ask._run_pipeline` (both of `run_routed_ask`'s two resolutions and `run_named_ask`'s
  one) — three call sites, four resolutions, one assembly. `weft_cli.compile.contracts_for`
  gained a matching `contributions` parameter: it adds a contract entry only for a
  contribution whose `slot` some pipeline in the ancestor chain actually declares, so an
  unrelated contribution's own broken `use:` can never fail a pipeline it was never meant for.

  **`02` §3's placement properties — which were new work, which were first demonstrations.**
  New: `weft plugins doctor` flagging a pack whose contributions land in no pipeline at all —
  `weft_cli.pipeline_catalogue.declared_slot_ids` and `weft_cli.plugins_report.render_doctor`'s
  own `unreachable_contributions` parameter did not exist before this task, because there was
  no contribution for either to have anything to say about. First-time demonstrations against
  a real, installed pack's own contribution rather than a hand-built test fixture: "a
  contribution with no matching slot is a recorded no-op, never a resolution failure" and
  "installation-dependent targets are recorded, never fatal" were both already true of
  `resolve()` since task 1.11 — this task is the first time either was proven true of
  something a pack actually produced. Ties breaking by distribution name and a contributed
  stage being `set`-able but not `replace`/`remove`-able were untouched (task 1.11's own
  code) and stay covered by that task's own tests; nothing here needed to touch them.

  **`examples/weft-example-ingest`** — installed rather than linked, fitness function 9(a) —
  is the pack that contributes: its `register()` now also calls `registrar.add_contribution
  (ENRICH_SLOT, StageDeclaration(id=_ENRICH_STAGE_ID, use="example-enhancer"))`, reusing the
  same `Enhancer` plugin it already registers under `Enhancer:example-enhancer` — offering a
  plugin as both an ordinary stage and a slot contribution costs nothing extra to declare.
  `tests/architecture/test_ff9_extension_from_outside.py`'s `_NameCapturingRegistrar` gained a
  no-op `add_contribution` so `register()` calling it there does not raise `AttributeError`.

  **Fitness function 15** (`01` → *Fitness functions*), `tests/architecture/
  test_ff15_resolve_call_sites_pass_contributions.py`: every file under `weft-cli`'s own `src`
  that binds `resolve` as a bare name via `from weft_kernel.resolution import resolve` is
  walked for every `ast.Call` whose `func` is that bare name, and each one must carry a
  `contributions=` keyword. **Structural, not textual, and it has to be** — `docs/lessons.md`
  L5.23 logged why: a plain `grep "resolve("` over the same three files also matches
  `Runner.resolve` and `ServiceRegistry.resolve`, two unrelated methods called in the
  identical files, sometimes the identical function. `test_the_check_can_actually_fail`
  parses a file shaped exactly like a fourth call site that forgot the keyword and shows the
  same walk reports it as an offender. A new numbered function rather than a clause of item
  14 (its nearest neighbour): 14 checks a *runtime* fact by driving discovery; this one is a
  *caller-shape* fact, true or false by inspection before anything runs — `01` item 15's own
  note has the argument in full.

  **Kernel: 2982 lines against the 3,500 ceiling (+12 from 5.2g's 2970), still past the
  2,800 review trigger crossed at 5.2c/5.2e/5.2g and well under the ceiling.**

  **Run outside the repository** (a scratch project directory, never this checkout), against
  the real container — `examples/weft-example-ingest` built as a real wheel (`uv build
  --wheel`) and installed into the shipped `.venv` — never `uv pip install <directory>`, the
  identical reasoning fitness function 9(a) insists on — then uninstalled again once the run
  below finished, leaving no trace in the tree, the venv or the scratch directory:

  ```
  $ weft --help
  usage: weft [-h] [--version] [--json | --quiet] command ...
  ...
  (no REPL — the Phase 3 scar stayed shut)

  $ weft pipeline show with-slot        # placed
  pipeline: with-slot
  vars:
    (none)
  stages:
    extract: Extractor:text (distribution: weft-extract, provenance: with-slot)
    chunk: Chunker:fixed-size (distribution: weft-chunk, provenance: with-slot)
      with: {'size': 512, 'overlap': 50}
    weft-example-ingest:wordcount: Enhancer:example-enhancer (distribution: weft-example-ingest, provenance: weft-example-ingest)
    embed: Embedder:hash (distribution: weft-embed, provenance: with-slot)
    store: NodeStore:pgvector (distribution: weft-store, provenance: with-slot)
  unapplied operators: (none)
  unplaced contributions: (none)

  $ weft pipeline show without-slot      # unplaced — a recorded no-op, resolution still succeeds
  pipeline: without-slot
  vars:
    (none)
  stages:
    extract: Extractor:text (distribution: weft-extract, provenance: without-slot)
    chunk: Chunker:fixed-size (distribution: weft-chunk, provenance: without-slot)
      with: {'size': 512, 'overlap': 50}
    embed: Embedder:hash (distribution: weft-embed, provenance: without-slot)
    store: NodeStore:pgvector (distribution: weft-store, provenance: without-slot)
  unapplied operators: (none)
  unplaced contributions: weft-example-ingest:wordcount -> slot 'enrich' (pipeline 'without-slot' declares no such slot)
  exit=0

  $ weft index ./corpus --pipeline with-slot     # the contributed stage actually runs
  produced 1, nothing to produce 0, failed 0. nodes now stored: 2.
  mode 'repair' — 1 participant(s):
    pgvector (weft-store): examined 0, removed 0, backfilled 0
  exit=0

  # with-slot.yaml moved out of pipelines/ — no pipeline in the catalogue declares 'enrich' at all
  $ weft plugins doctor
  weft-example-ingest: active (7 contributed)
    disclosure: not disclosed
    unreachable: slot 'enrich' (stage 'wordcount') lands in no pipeline this catalogue holds

  $ weft pipeline show does-not-exist            # failure path 1
  'does-not-exist' is not a pipeline this project knows — checked the project's own 'pipelines'
  directory and every installed pack's own contribution. Known pipelines: no-retrieval,
  retrieve-then-generate, route, without-slot.
  exit=4

  $ weft pipeline show broken                    # failure path 2 — a document's 'use:' names nothing
  stage 'embed' names plugin 'totally-not-a-real-embedder', which no installed distribution
  registered under any contract. Installed plugin names: ... fixed-size, hash, ... text, ...
  exit=4
  ```

  **Measured**: `uv run poe ci-checks` green — `arch` 111 passed (one file gained,
  `test_ff15_resolve_call_sites_pass_contributions.py`, three tests); `test` 1,799 passed, 1
  skipped. `uv run poe kernel-isolated` green. `docs/lessons.md` L5.23 logged the grep-versus-AST
  finding above; `manual/pack-author-guide.md` §9.7 — previously "the one row this guide cannot
  demonstrate yet" — is rewritten to teach the real mechanism, tagged against
  `examples/weft-example-ingest/src/weft_example_ingest/__init__.py`'s own real line.
- [x] **5.4** the graph pack registers **six** things from one install, with one entry point, one `register()` and one settings model — G7 added `SourceDeletable` and `Reconcilable` to `02` §4's table, and requirement 2 (*a capability spanning several extension points is still one package*) is only tested by the count going up · owner `02` §4 → the registration table · turns on — · sha `9a1029c`

  **Built by a pack author who never touched `packages/` — `examples/weft-example-graph/`**, outside the
  uv workspace and `[tool.uv.sources]` exactly as `docs/07-extension-cost.md` §9's own discipline
  requires for fitness function 9(a). `pyproject.toml` declares four intra-repo ranges (G9's shape)
  plus a bare floor on `psycopg[binary]`, the ordinary third-party library it is.

  **The six, counted honestly rather than by table row.** `docs/02-extension-model.md` §4's own
  table has five rows plus two G7 added; excluding the "—" row (pipeline-as-data, task 5.5's), the
  "Against contract" column names six distinct contracts: `Enhancer` (`graph-entities`), `NodeStore`
  (`graph` — `02`'s own "`Store`"), `Retriever` (`graph-walk`), `Command` (twice: `graph build`,
  `graph show`), `SourceDeletable` and `Reconcilable`. Four come from an explicit
  `registrar.add()` call in `weft_example_graph.register` (`examples/weft-example-graph/src/weft_example_graph/
  __init__.py`); `SourceDeletable`/`Reconcilable` arrive with **no further `.add()` call**, because
  `GraphStore` (the one class registered under `NodeStore`) satisfies both structurally — the
  identical "eighth and ninth capability arrive with no ninth `registrar.add` call" shape
  `examples/weft-example-ingest`'s own `register()` already demonstrates. `registrar.
  add_ext_model(GraphData)` is a seventh registrar call, on a separate axis (a payload primitive
  attaching to `Node.ext`, never a contract) — not one of the six.

  **Measured**: `uv run poe ci-checks` — `fmt`/`lint`/`types` green; `arch` **111 passed, 1
  failed** (`tests/architecture/test_ff9_extension_from_outside.py::
  test_no_first_party_file_names_the_example_pack` — see the design finding below; `docs/
  lessons.md` L5.28); `poe test` (the full `pytest tests -q`, run directly since the sequence
  aborts on the one `arch` failure) **1,799 passed, 1 skipped**, the identical single failure and
  nothing else. This pack's own `uv run pytest examples/weft-example-graph/tests` (33 tests, against the
  real `compose.yaml` Postgres) is green.

  **Design finding — `test_no_first_party_file_names_the_example_pack` false-positives on this
  pack's own, already-documented name.** (No decision-log `S` id assigned here — that log's rows
  are settled by whoever adds the follow-up ledger task, which a pack-author task does not do;
  the finding is recorded fully in `docs/lessons.md` and here instead.) Fitness function 9(b) checks "core must not
  anticipate a stranger it never imported" via a literal substring search for the pack's
  distribution name, module name, and every registered plugin name across every file under
  `packages/`/`testing/`. `weft-example-graph`'s own plugin names (`graph`, `graph build`, `graph show`)
  are ordinary English words already present, as unrelated prose, in dozens of first-party files —
  and the literal string `'weft-graph'` itself already appears verbatim in five first-party
  files (`packages/weft-otel/src/weft_otel/__init__.py` among them), because they quote `docs/
  02-extension-model.md` §4's own worked example by its planned name. Not a defect in this pack —
  renaming away from the name every design document already uses would be optimizing for a check
  instead of for what this task asks it to demonstrate. `docs/lessons.md` L5.28 has the full
  evidence; this is exactly `01` → Phase 5 Exit's *"a design finding, not a feature request"*
  clause, logged rather than routed around.

  **Design finding — the deletion/reconcile fan-out's own `NodeStore` special-case excludes this
  pack from `weft delete`/`weft reconcile`, contradicting `02` §4's own transcript.** (Same note as
  above: no `S` id assigned by this task.) Run for real, against the shipped binary, from a
  directory outside this repository:

  ```
  $ weft index corpus_a
  produced 1, nothing to produce 0, failed 0. nodes now stored: 2.
  mode 'repair' — 1 participant(s):
    pgvector (weft-store): examined 0, removed 0, backfilled 0
  exit=0

  $ weft reconcile --dry-run --yes
  mode 'full' would run against 1 participant(s):
    pgvector (weft-store): no unfinished deletions; nothing to converge
  exit=0
  ```

  `weft-example-graph` never appears, even though `GraphStore` structurally satisfies `Reconcilable` (and
  `SourceDeletable`) — `weft_cli.fanout.participants_for` filters the `NodeStore` contract down to
  the one name `[services] store` configures (`pgvector` here), a rule written to stop two
  interchangeable primary stores (pgvector, Qdrant) from both being acted on, which also — by the
  same filter — excludes a second, *derived* `NodeStore` registration from ever participating.
  `docs/lessons.md` L5.25 has the full evidence and the falsified docstring quotation. `GraphStore.
  reconcile`/`.estimate` (`examples/weft-example-graph/src/weft_example_graph/store.py`) additionally raise
  `GraphBackfillUnavailableError` for `mode=FULL`, for the related but separate reason `docs/
  lessons.md` L5.24 records: `Reconcilable`'s own signature gives a derived participant no way to
  see "what should exist" in the primary corpus at all.

  **The binary, run for real, outside the repository** (`WEFT_DATABASE_URL` pointed at the
  `compose.yaml` container, `[packs.weft-graph] dsn = "${env:WEFT_DATABASE_URL}"` in `weft.toml`):

  ```
  $ weft plugins doctor
  weft-graph: active (5 contributed)
    disclosure: not disclosed
  [... every other installed pack, unchanged ...]

  $ weft graph --help
  usage: weft graph [-h] command ...
  positional arguments:
    command
      build     recompute weft-graph's entities and relations from stored content
      show      show weft-graph's corpus-wide summary, or one entity's neighbours

  $ weft graph show                       # before weft.toml carried a dsn
  weft-graph has no database to talk to: [packs.weft-graph] dsn is unset. Add
  `[packs.weft-graph]\ndsn = "${env:WEFT_DATABASE_URL}"` (or a literal DSN) to weft.toml.
  exit=1

  $ weft graph build                      # overwrite-class, no TTY, no --yes
  'graph build' is an overwrite-class command, called with {}. It refuses to run with no terminal
  to confirm in, and never proceeds silently. Pass --yes to permit it for this invocation.
  exit=3

  $ weft graph show                       # after weft.toml carried the dsn, empty store
  {"nodes_with_graph_data":0,"distinct_entities":0,"distinct_relations":0,"top_entities":[],
  "entity":null,"neighbors":[]}
  exit=0
  ```

  Registration succeeds with **zero** settings supplied too — `GraphSettings.dsn` defaults to an
  empty `SecretStr`, deliberately unlike `PgVectorSettings.dsn` (mandatory): `tests/architecture/
  test_ff9_extension_from_outside.py::module_and_plugin_names` constructs every example pack's
  `Settings()` bare and runs `register()` against a stand-in registrar with no `weft.toml` at all,
  so a mandatory `dsn` would break that check for this pack alone. `register()` never opens a
  connection either way (`GraphStore._connection` is lazy); the DSN is only needed, and only
  checked, the first time a store method actually runs.

  **Read under `packages/` to get this done, and what the guide did not say.** `weft_store.
  rehydrate.rehydrate_ext`/`register_ext_model` (`packages/weft-store/src/weft_store/
  rehydrate.py`) and `weft_cli.fanout.participants_for`/`weft_cli.reconcile._ask` (`packages/
  weft-cli/src/weft_cli/fanout.py`, `reconcile.py`) were read to confirm exactly how `ext`
  round-trips through a store and exactly what `ctx` carries into a `Reconcilable` call —
  `manual/pack-author-guide.md` names `rehydrate_ext` as the mechanism (§9.5) but does not show a
  stranger's own store calling it, and nothing in the guide or `docs/02-extension-model.md`
  documents `participants_for`'s `NodeStore` special-case at all (`02` §1's own "capability is
  derived, never declared" reads as though every capability fans out uniformly, which G7's own
  "no core edit" claim for the graph pack repeats without qualification). Both readings are cited
  in `docs/lessons.md` L5.24/L5.25 as the finding, not silently absorbed.

- [x] **5.5** the pack ships a derived pipeline as data that users can derive from further · owner `02` §4; `02` §3 · turns on — · sha `572b041`

  **`weft_example_graph.register` grows two more calls, no new registrar method needed**:
  `registrar.add_pipeline_resource("weft_example_graph", "pipelines/kg.yaml")` ships the named
  pipeline (extract → chunk → **entities** (`graph-entities`) → embed → store (pgvector) →
  **graph-store** (`graph`), stated whole rather than `extends:`-ing a "base" this repository
  ships nowhere — `docs/02-extension-model.md` §3's own `base.yaml` is illustrative, never a
  document any first-party pack actually publishes); `registrar.add_contribution("enrich",
  StageDeclaration(id="entities", use="graph-entities"))` offers the same, already-registered
  `graph-entities` plugin into any pipeline that opts into an `enrich` slot, reusing
  `examples/weft-example-ingest`'s own slot name for the identical kind of position rather
  than inventing a second convention.

  **The binary, run for real, outside the repository**, over a two-document corpus mentioning
  four entities across two files (`Acme Corp`/`Globex Inc` in one, `Globex Inc`/`Initech`/
  `Umbrella Corp` in the other):

  ```
  $ weft pipeline show kg
  pipeline: kg
  stages:
    extract: Extractor:text (distribution: weft-extract, provenance: kg)
    chunk: Chunker:fixed-size (distribution: weft-chunk, provenance: kg)
    entities: Enhancer:graph-entities (distribution: weft-graph, provenance: kg)
    embed: Embedder:hash (distribution: weft-embed, provenance: kg)
    store: NodeStore:pgvector (distribution: weft-store, provenance: kg)
    graph-store: NodeStore:graph (distribution: weft-graph, provenance: kg)
  unplaced contributions: weft-graph:entities -> slot 'enrich' (pipeline 'kg' declares no such slot)

  $ weft index corpus --pipeline kg
  produced 1, nothing to produce 0, failed 0. nodes now stored: 2.
  mode 'repair' — 1 participant(s):
    pgvector (weft-store): examined 0, removed 0, backfilled 0
  exit=0

  $ weft graph show
  {"nodes_with_graph_data":2,"distinct_entities":4,"distinct_relations":4,
   "top_entities":[{"name":"Globex Inc","count":3},{"name":"Acme Corp","count":2},
                   {"name":"Initech","count":2},{"name":"Umbrella Corp","count":1}]}

  $ weft graph show --entity "Globex Inc"
  {"entity":"Globex Inc","neighbors":[{"name":"Acme Corp","predicate":"co_occurs_with","count":1},
   {"name":"Initech","predicate":"co_occurs_with","count":1},
   {"name":"Umbrella Corp","predicate":"co_occurs_with","count":1}]}
  ```

  **Derivable further, shown rather than merely claimed** — a project-local
  `pipelines/kg-slotted.yaml` declaring an `enrich` slot (task 5.5 does not require the
  pipeline it ships to itself extend anything; §3's own row is about a pack's contribution
  being placeable by *any* pipeline that opts in, first- or third-party):

  ```
  $ weft pipeline show kg-slotted
  pipeline: kg-slotted
  stages:
    extract: Extractor:text (distribution: weft-extract, provenance: kg-slotted)
    chunk: Chunker:fixed-size (distribution: weft-chunk, provenance: kg-slotted)
    weft-graph:entities: Enhancer:graph-entities (distribution: weft-graph, provenance: weft-graph)
    embed: Embedder:hash (distribution: weft-embed, provenance: kg-slotted)
    store: NodeStore:pgvector (distribution: weft-store, provenance: kg-slotted)
  unplaced contributions: (none)
  ```

  The contribution places automatically, qualified `weft-graph:entities`, exactly where `02`
  §3 specifies — no core edit, no pack-author intervention beyond the one `register()` line.

  **The same design finding, now with real data rather than an empty store**: `weft delete
  <doc1>` reports one participant (`pgvector`, 1 node removed); `weft graph show` afterward
  still reports `nodes_with_graph_data: 2` and `Acme Corp` at its pre-delete count — `weft-example-graph`'s
  own entities/relations for the deleted document are left dangling, unreachable, and wrong,
  which is the RAPTOR scar `docs/02-extension-model.md` §1 → *Extended by G7* names as the
  reason `SourceDeletable` exists at all, reproduced live against this pack because of the
  `participants_for` gap `docs/lessons.md` L5.25 records (logged at task 5.4, confirmed here
  with data rather than an empty corpus).

  **Two more design findings, surfaced only once a pipeline resource actually shipped** —
  both recorded in `docs/lessons.md` (L5.26, L5.27) and neither fixed here, since both live in
  `tests/architecture/` files a pack author does not edit:

  - `tests/architecture/test_ff9_extension_from_outside.py::_NameCapturingRegistrar` — the
    `PackRegistrar` stand-in that file's own `module_and_plugin_names` runs a pack's real
    `register()` against — implements `.add()`, `.add_ext_model()` and `.add_contribution()`
    but not `.add_pipeline_resource()` or `.deprecate()`, both real `PackRegistrar` methods.
    `weft_example_graph.register` calling `add_pipeline_resource` (per `docs/02-extension-model.md`
    §9.6's own sanctioned mechanism) raises `AttributeError` inside that test.
  - `tests/architecture/test_ff11_pipeline_integrity.py::_shipped_pipeline_files` walks
    `examples/*` for shipped pipelines by design (its own docstring: "`examples/*` for an
    example pack"), but `_installed_registry`'s `discover(..., allow=_first_party_
    distributions())` structurally refuses any distribution outside `packages/*` — so
    `kg.yaml`, shipped exactly where that docstring says it should be, fails
    `test_every_shipped_or_quoted_pipeline_resolves` with "no installed pack registers"
    for plugins this pack's own `weft pipeline show kg` output above proves resolve
    correctly against a registry that actually has `weft-example-graph` installed.

  **Measured**: `uv run poe ci-checks` — `fmt`/`lint`/`types` green; `arch` **110 passed, 2
  failed** (the two findings above; `arch` was **111/1** at task 5.4, so this task's own
  `add_pipeline_resource` call is what adds the second); `poe test` (full `pytest tests -q`)
  **1,798 passed, 1 skipped, 2 failed** — the identical two and nothing else. **Verified with
  `weft-example-graph` uninstalled from the shared dev `.venv` before each run**: installing the wheel
  for the binary demo above and then re-running the architecture suite without uninstalling
  first produced a *false pass* on the `add_pipeline_resource` finding — `sys.modules['weft_example_graph']`
  gets populated from the stale, already-installed wheel by an earlier-running architecture
  test's own full `discover()` call, so the later in-process `sys.path` import trick returns the
  cached (older) module instead of re-importing current source. Not logged as a `docs/lessons.md`
  entry (it is a fact about this task's own verification hygiene, not something a future pack
  author would hit under normal CI, which never has a stray editable install lying around) —
  recorded here so the two failure counts above are not mistaken for flaky.

  This pack's own `uv run pytest examples/weft-example-graph/tests` (35 tests) is green.

- [x] **5.6** uninstalling the pack fails resolution with a message naming the missing plugin and the pack that provides it · owner `02` §4 · turns on — · sha `caa2d97`

  **No new code — a demonstration**, against the shipped binary, outside the repository.
  Because `weft-example-graph` ships `kg` itself (task 5.5), uninstalling it removes the *pipeline name*
  along with the plugins — `weft pipeline show kg` then fails as "unknown pipeline", not "unknown
  plugin inside a document that still exists". So the demonstration `02` §4 actually describes
  (a document that survives uninstall but names a now-missing plugin) needs a project-local
  pipeline — `pipelines/mykg.yaml` — naming `graph-entities`/`graph` directly, the identical
  shape a user's own `weft pipeline derive` output would have:

  ```
  $ weft pipeline show mykg               # weft-graph installed
  pipeline: mykg
  stages:
    entities: Enhancer:graph-entities (distribution: weft-graph, provenance: mykg)
    graph-store: NodeStore:graph (distribution: weft-graph, provenance: mykg)
    [... other stages unchanged ...]
  exit=0

  $ uv pip uninstall --python .venv/bin/python weft-graph
  Uninstalled 1 package

  $ weft plugins doctor                   # weft-graph: no trace at all, nothing crashes
  weft-canary: active (0 contributed)
  [... every other installed pack, unchanged, weft-graph simply absent ...]

  $ weft pipeline show mykg               # weft-graph uninstalled
  stage 'entities' names plugin 'graph-entities', which no installed distribution registered
  under any contract. Installed plugin names: accuracy, always, ..., text, threshold-ladder,
  token-overlap, token-recall, trace, unicode-normalize, vector-top-k, whitespace.
  exit=4

  $ weft pipeline show kg                 # the pack's OWN shipped pipeline: gone entirely
  'kg' is not a pipeline this project knows — checked the project's own 'pipelines' directory
  and every installed pack's own contribution. Known pipelines: mykg, no-retrieval,
  retrieve-then-generate, route.
  exit=4

  $ weft pipeline list
  mykg
  no-retrieval
  retrieve-then-generate
  route
  ```

  Both refusals are exit 4, loud, and name every valid alternative — rule 5 held for a plugin
  name and for a pipeline name alike.

  **Design finding — `02` §4's own transcript overclaims what the refusal says.** "Fails to
  resolve with a message naming the missing plugin **and the pack that provides it**" is `02`
  §4's own wording; the real message above names the missing plugin and every registered
  alternative, never a distribution, because `weft_kernel.registry.UnknownPluginError.__init__`
  (`packages/weft-kernel/src/weft_kernel/registry.py:235-237`) has no field for one and cannot:
  once uninstalled, nothing in the registry ever knew `weft-example-graph` provided `graph-entities`
  this run — a `RegistryEntry.distribution` exists only for a name that *is* registered.
  `manual/pack-author-guide.md` §7's own table already states the honest version ("names the
  contract, the plugin name that was wanted, and every name that is registered") with no
  providing-pack clause; `02` §4 and the guide disagree, and the code matches the guide, not
  `02` §4. `docs/lessons.md` L5.29 has the full evidence; not fixed here — softening a design
  document's own transcript, or deciding whether resolution owes a last-known-provider record,
  is not a pack author's call.

  **Cleanup**: `weft-example-graph` uninstalled from the shared `.venv` (confirmed absent from `weft
  plugins doctor` above); `weft_example_graph_*` tables dropped from the `compose.yaml` Postgres; the
  scratch run directories hold only `weft.toml` and the project-local `pipelines/*.yaml` this
  demonstration wrote, nothing under this repository changed by running the binary.

- [x] **5.7** the pack was built by someone who has not touched core, and they never needed to — every request for a core change recorded as a design finding rather than closed as a feature request · owner `01` → Phase 5 **Exit**; `02` §4 → *The independence test* · turns on — · sha `49b478c` · **RUN, AND THE EXIT CRITERION IS NOT MET**

  **The first half held completely.** `examples/weft-example-graph` was built with **zero edits under
  `packages/`** — not one line of kernel, CLI or first-party pack code. It registers six extension
  points from one entry point, one `register()` and one settings model; ships `pipelines/kg.yaml` and
  a slot contribution; `weft index --pipeline kg` runs its stages against the real container; its two
  commands appear in `--help`; and uninstalling it refuses resolution by name. Requirement 2 — *a
  capability spanning several extension points is still one package* — is satisfied, and the count
  went up, which is the only way that requirement is tested.

  **The second half did not.** `01` → Phase 5 **Exit**: *"they never need to. If they file an issue
  asking for a core change to make their pack work, that is a Phase 5 failure and a design finding."*
  The author filed three, and two of them stop the pack doing what `02` §4's own table says it does:

  - **`docs/lessons.md` L5.25 — `weft delete` never reaches the graph store, which is the exact scar
    G7 exists to close.** `02` §1 settled that deletion fans out *"across **every** registered plugin
    that satisfies it — not just the node store"*. Task **5.1a** narrowed that, excluding every
    `NodeStore` but the one `[services] store` names, to avoid connecting to pgvector and Qdrant
    both. `02` §4's table registers the graph store under `NodeStore` — *"Sits beside the vector
    store"* — so the narrowing excludes it, and derived graph data outlives its source exactly as the
    reference's RAPTOR summaries did. Reproduced live. **This is a task defaulting an unsettled question
    instead of stopping**, which is the thing `phase-step` names and this phase caught (`L5.32`).
  - **L5.24 — `full` reconcile cannot work for a derived store.** `Reconcilable.reconcile(ctx, mode)`
    hands a participant nothing that names the primary corpus, so *"`full` backfills entities for
    nodes indexed by a pipeline that had no graph stage"* is unbuildable by a pack. The pack raises
    `GraphBackfillUnavailableError` naming the gap rather than pretending.
  - **L5.30 — a pack's command cannot render its result for a person.** `weft example-graph show`
    prints `{"nodes_with_graph_data":11,...}` to a terminal, because `weft_cli.render._RENDERERS` is
    a first-party table matched on result type that no pack can join. `03`'s governing rule — a
    `Command` returns a typed result and the CLI renders it — holds for eighteen first-party commands
    and for nobody else's.

  **Also found, and repaired here rather than deferred:** L5.26/L5.27 (two core test fixtures that
  could not accommodate any example pack shipping a pipeline), L5.28 (a name-collision check
  false-positiving on ordinary English — the pack had also taken `weft-graph`, the name the design
  documents reserve for this pack as a *hypothetical*, and was renamed), L5.29 (`02` §4's own
  uninstall transcript overclaims what the refusal can say), L5.31 (the binary-run step and the gate
  step want opposite venv states and nothing enforces the handover).

  **What this outcome is worth.** Nine of these were invisible to 1,801 tests and to the pack's own
  35. `02` §4 says the independence test exists because *"if they need a core change, the extension
  model has a hole, and finding it that way is much cheaper than finding it after publishing
  contracts"* — which is what happened, one phase before Phase 6 publishes them. **G13 is proposed
  and Open** (`README.md` → *Decision log*): the derived-participant seam, covering L5.24, L5.25 and
  L5.30 together, because all three are the same question — what a participant that is *not* the
  primary store may ask for and be reached by.

  **G13 settled 2026-08-22, and the repairs are Phase 6's, not this phase's.** Reach follows use, a
  participant asks through `ctx.require(NodeStore)`, and a renderer registers at the seam — the full
  outcome is in `README.md` → *Decision log*, the argument in `05` → G13, the mechanisms in `02` §1,
  `02` §4 and `03`. Tasks **6.18**, **6.19** and **6.20** build them; **6.21** re-runs this test and
  is where this criterion is finally met. **This entry stays ticked and the phase's exit stays
  unticked**, which is the honest pair: the task ran and produced exactly what it exists to produce,
  and the criterion it was measuring is still not satisfied. Scheduling the repairs into Phase 6 was
  a decision rather than a drift, and its cost is stated: Phase 6 opens carrying an earlier phase's
  unfinished exit, and the contracts 6.20 moves are published in the same phase that changes them.

**Exit** (`01` → Phase 5): task 5.7. A core change requested to make the pack work is a Phase 5
failure and a design finding, which means 5.7 can be *failed* — that is what makes it worth running.

**G7 closed as *"shown to work without a bus"*, and 5.7 is where the showing happens.** The session
walked the graph pack case by case and found no case a bus served that an extension point could not;
if the pack's author hits one, that is the design finding this phase exists to produce, and `01`'s
deferred *Event bus* row reopens. G7 is settled, not immune.

---

## Phase 6 — Release

**The lessons queue was drained at this phase's opening, not at its close** — two entries logged at
G10 and G13 (`L6.1`, `L6.2`), spent the same day, `lessons-archive.md` → *2026-08-22 — G10 and G13
close*. This is Phase 5's own drain finding applied (*"Phase 6 should drain at its midpoint as well as
its close"*), and the loop's check is answered there: one of the two would have been caught by an
already-applied rule, `L5.14`, whose subject was too narrow rather than whose home was wrong.

**✅ Unblocked 2026-08-22. Both gates are settled** — G9 on 2026-08-21, G10 on 2026-08-22 — and
**G13** settled the same day as G10, which is why this phase gained four tasks it did not have
(6.18–6.21). Nothing here is waiting on a decision any more; `05` → G12 blocks Phase 7 only.

**The ⚠ tasks now have their shape, and it is written down.** They were marked because G9 or G10
decided them; both have. **The unit of release is a named release set** — a code-free distribution
`weft` pinning an exactly-tested combination (`09` §1), so 6.1's property is settled rather than
hypothetical and 6.13 installs *that*. The doctor reports skew and never refuses it (G9); the
deprecation clock is one major of the publishing distribution (G9); the support window is the current
major plus the previous for a release-set major or six months, whichever is longer (`09` §3). Two
release facts arrived with G10 and are new obligations rather than restatements: **a 1.0 release set
may pin nothing below 1.0** (`09` §2.2), and 1.0 rests on evidence with a **date-boxed review that
publishes the gap** rather than shipping past it. The ⚠ marks are kept on the four task lines as a
record of what was once undecided; each line now names the answer. The reproduction tolerance was
never among them — `09` §4 derives it from the baseline's own recorded interval rather than from any
gate, which is the point of deriving it.

- [x] **6.1 ⚠** a release is a named, tested set rather than a wheel · owner `09` §1 · turns on — · sha `1fb66c1`
  **6.1 — the release set exists, and the wheel proves it ships nothing.** `packages/weft/` is a
  `pyproject.toml` and a `README.md`; there is no `src/`. Built for real rather than asserted:

  ```
  $ uv build --wheel packages/weft
  Successfully built weft-0.1.0-py3-none-any.whl
  $ unzip -l weft-0.1.0-py3-none-any.whl
    weft-0.1.0.dist-info/METADATA
    weft-0.1.0.dist-info/RECORD
    weft-0.1.0.dist-info/WHEEL
  $ grep Requires-Dist METADATA        # 15 pins, every one exact
  weft-chunk==1.0.0   weft-clean==1.0.0    weft-cli==0.1.0     weft-command==2.1.0
  weft-embed==1.0.0   weft-enhance==1.0.0  weft-eval==1.0.0    weft-extract==1.0.0
  weft-generate==1.0.0 weft-index==1.0.0   weft-kernel==0.1.0  weft-llm==1.0.0
  weft-prompts==1.0.0 weft-retrieve==1.0.0 weft-store==2.0.0
  ```

  Metadata only — no code in the artefact, which is `09` §1's first binding consequence checked
  against the thing that ships rather than against the checkout. `tests/architecture/
  test_release_set.py` holds the rest: no module, no entry point, exact pins never ranges, and
  **every pin read against that distribution's own `pyproject.toml`** — two sources that can
  genuinely disagree, so a pack bumped without this file following it fails the gate
  (`docs/lessons.md` L5.6). Version `0.1.0`, and it cannot yet be otherwise: `09` §2.2 forbids a
  1.0 set from pinning anything below 1.0, and the kernel is `0.1.0`.

  **What installs beside rather than in**, on `09` §1's own `weft-store-qdrant` precedent:
  `weft-qdrant` (alternative backend), `weft-openai` (credentialed provider), `weft-pdf` (optional
  format), `weft-otel` (observability add-on), and `testing/weft-canary`, which exists to be
  *refused* by discovery and must never reach an index. A first-party pack that is in neither list
  fails `test_the_release_set_names_every_first_party_pack_that_is_not_installed_beside_it` — the
  set is *exactly* tested, so a pack nobody decided about is the drift this refuses.

  **A code-free distribution broke three directory sweeps, and that is `L5.27` recurring.**
  `test_ff12`, `test_ff12b` and `tests/docs/test_troubleshooting_coverage.py` each derive a
  top-level module name from every `packages/*/pyproject.toml` and import it; `weft` has no module,
  so all three raised `ModuleNotFoundError`. Each now skips a distribution with no `src/` directory
  at all — the structural fact, never the name — while a distribution that *has* a `src/` whose
  module will not import still fails, which is the half L5.27 requires a sweep to keep: it must be
  able to answer the question for everything it sweeps, and *"ships nothing"* is an answer where
  *"cannot import it"* is not.

- [x] **6.2** the publish set and the workspace agree, computed from different sources, and the canary is never on an index · owner `09`; `01` → *Fitness functions* 10(a) · turns on FF10(a) · sha `9681e48`
  **6.2 — the two sources, and the release job that gave one of them a subject.** FF10(a) compares
  "the distributions the release job actually passes to the index" against the workspace members
  that do not opt out. Before this task there was **no release job**, so one side of the comparison
  had nothing to read — the clause was runnable in Phase 6 and not before, which is what `01` means
  by *active from Phase 6*. So `.github/workflows/release.yml` is part of this task rather than a
  prerequisite of it.

  **The publish list is hand-written on purpose.** A workflow deriving its own matrix from
  `packages/*` would compare a function to itself and could never fail — the reference's
  `test_keys_parity` shape `01` names in the clause itself
  (`reference/study/08-salvage.md:777-782`). The two sides are `.github/workflows/release.yml` and the
  root `pyproject.toml`'s member globs, and they can genuinely disagree. Both directions were
  planted and watched going red:

  ```
  $ # weft-otel removed from the matrix
  AssertionError: ['weft-otel'] are workspace members with no opt-out marker and the release job
  never passes them to the index. Add them to a `release.yml` job's 'distribution' matrix, or
  declare `[tool.weft] publish = false` in the distribution's own pyproject.toml and say why.

  $ # weft-canary added to the matrix
  AssertionError: ['weft-canary'] would be published and are not workspace members that publish.
  Either the release job names something that does not exist, or the distribution opted out of
  publishing and the workflow was not told (`01` → *Fitness functions* 10(a)).
  ```

  **The opt-out marker is `[tool.weft] publish = false`, in the distribution's own file.** `01`
  requires "an opt-out marker" and deliberately does not spell one. It lives with the distribution
  rather than in a central exclusion list because a central list is a second description of the same
  fact and drifts from it — the failure `docs/README.md`'s own opening rule is written about.
  `testing/weft-canary` carries it, which is `01` 10(a)'s standing test case: a distribution whose
  whole purpose is to be *refused* by discovery must never reach an index.

  **Neither side may answer emptily.** `published_distributions` and `workspace_distributions` raise
  `ShipSetUnreadableError` rather than returning an empty set — an absent workflow, a renamed job, a
  member glob matching nothing. Two empty sets compare equal and check nothing, which is L5.19's
  vacuous pass and L5.9's *"I did not find it" is not "it is not there"* in one place.

  **The reader unions every job's matrix, not one named job's.** The release set is published by a
  second job that `needs` the first, because `weft` pins exact versions (`==`, `09` §1) and is
  uninstallable until everything it pins is on the index. A reader keyed to `jobs.publish` would
  have gone blind to that second job the moment it was added — `docs/lessons.md` L6.4, read the
  population rather than a declaration.

  **The workflow was executed, not only parsed.** A check that reads a YAML file proves the file
  says something, never that the commands in it run — the *green gate is not a working binary* rule
  applied to CI. Both build steps were run for real, including the failure path:

  ```
  $ uv build --package weft --out-dir dist          # the code-free release set
  Successfully built dist/weft-0.1.0.tar.gz
  Successfully built dist/weft-0.1.0-py3-none-any.whl
  $ uv build --package weft-kernel --out-dir dist
  Successfully built dist/weft_kernel-0.1.0-py3-none-any.whl
  $ uv build --package weft-nonexistent --out-dir dist
  error: Package `weft-nonexistent` not found in workspace
  ```

  `uv publish` itself is not run here — it needs an index and a trusted-publishing identity, and
  **6.13** is the task that installs the release set from an index for real.

  **FF16's waiver keeps `10`, and says why.** Clause (a) has a file now, so
  `test_ff16_checks_are_real.py`'s filename check would pass without the waiver. It is kept because
  clause (b) — no distribution depends on a sibling without a version bound — is still prose:
  **task 6.3** builds it into the same file and removes the number. Removing a waiver while half the
  function is unwritten is `L5.4` re-created one clause at a time.
- [x] **6.3** no distribution depends on a sibling without a version bound, so a compatibility policy has something to rest on · owner `01` → *Fitness functions* 10(b) · turns on FF10(b) · sha `5f3852c`
  **6.3 — a check whose subject already agreed, and what that changes about writing it.** G9's
  enforcement rule landed in Phase 5, so every intra-repository requirement in the workspace already
  carries a bound — `09` §1 records G10's own *Bring* prediction of zero being falsified on the day,
  the answer being all of them. The clause was therefore green on the first run, which is the
  condition under which a check is most likely to be worthless: a sweep that reads nothing passes
  identically to one that reads everything and finds agreement. So the floor is `L5.19`'s. The
  reader raises `ShipSetUnreadableError` rather than returning an empty workspace, the test asserts
  the edge population is non-empty **and** that `weft-kernel` is visible in it before judging
  anything, and the disagreement was planted in the real tree and watched going red:

  ```
  $ # weft-pdf's "weft-extract>=1.0.0,<2.0.0" reduced to a bare "weft-extract"
  AssertionError: ['weft-pdf → weft-extract (in dependencies)'] depend on a sibling with no lower
  bound. `01` → *Fitness functions* 10(b): an unbounded requirement permits any pack against any
  kernel, and **any** compatibility policy is unenforceable on top of one.
  ```

  **A bound is a lower bound, and nothing narrower.** `01` names the three shapes — "a floor, a
  compatible range, or an exact pin" — and says the choice between them "is G9's and this clause
  does not choose". So the check asks only that the bottom is pinned: `>=`, `>`, `==`, `===`, `~=`.
  A lone `<1.0.0` is a specifier and not a bound, and is caught. **The clause is deliberately not
  tightened into G9's own rule** (`>=X,<MAJOR+1`, never exact pins): that rule is true of a pack
  depending on a contract publisher and deliberately false of the release set, whose `==` pins are
  what G10 settled it exists for (`09` §1). Two rules, two subjects — collapsing them here would
  fail `weft` for being what it was designed to be, which is the `L5.32` shape read in advance
  rather than after.

  **Both published dependency tables are swept**, `dependencies` and `optional-dependencies`;
  `[dependency-groups]` is not, because a dev group is never installed by anyone depending on the
  distribution and so is not something *a distribution depends on* in `01`'s sense. Neither of the
  two members carrying extras (`weft-eval`, `weft-otel`) names a sibling in one today, so that half
  of the sweep is currently unexercised by the real tree and is exercised by the self-test.

  **FF10 leaves `FITNESS_FUNCTIONS_NOT_YET_DUE` here, not at 6.2.** Both clauses now exist in
  `test_ff10_ship_set_integrity.py`. Holding the waiver across 6.2 — when a file with the right
  *name* already existed — is the point: a fitness function `01` states in two clauses is not built
  while one of them is prose, and per-clause waiver removal is `L5.4` re-created one clause at a
  time.

  **Filed while measuring, not guessed:** six of the seven example packs declare **bare** sibling
  names — 18 requirements across `weft-example-chunker`, `-command`, `-ingest`, `-llm`, `-metric`
  and `-query`. Only `weft-example-graph`, built after G9, carries bounds. They are outside FF10(b)'s
  subject by `01`'s own wording ("a property over the workspace"), and they are the exemplars a pack
  author copies. **Task 6.26.**
- [x] **6.4 ⚠** every first-party pack is `active` at the version the release names, and `weft plugins doctor` can *say* what is installed — whether it also flags a mismatch, and what a mismatch does, are G9's · owner `09` §1, and `09` §2's table of what Phase 6 needs from G9 · turns on — · sha `fdaf689`
  **6.4 — the column, and the property behind it.** `09` §1: `doctor` "gains one column, not a new
  command: the version of each active distribution... `doctor` has to be able to *say* what is
  installed before any policy can act on it." Both halves of the ⚠ are answered by G9, which
  settled before this task ran: skew is **reported and never refused**, and the kernel gains zero
  lines for it. So the reader is `weft_cli.installed_versions` — `importlib.metadata`, in the CLI,
  the same source `weft_cli.skew` already reads and deliberately not the same *question* — and
  `PackReport` gains no field.

  **Three states, kept distinguishable.** `versions=None` is *nobody asked* and reproduces the
  output every existing caller already got; a name present is its version; a name **absent from a
  mapping that was supplied** prints `(version not recorded)`. That third state is the one that
  matters: a `PackReport` exists for a pack that was refused or failed as readily as for one that
  loaded, and a diagnostic command that printed a blank where it could not measure would be hiding
  the diagnosis (`docs/lessons.md` L5.9).

  **Run for real, outside the repository:**

  ```
  $ weft plugins doctor
  weft-chunk 1.0.0: active (1 contributed)
    disclosure: not disclosed
  weft-cli 0.1.0: active (18 contributed)
    disclosure: not disclosed
  [...]
  $ weft plugins list          # unchanged — `09` §1 gives the column to `doctor`
  weft-chunk: active (1 contributed)
  $ weft plugins doctorr
  weft plugins: error: argument command: invalid choice: 'doctorr' (choose from doctor, list)
  ```

  **The other half — "active at the version the release names" — is a check, not a feature**, and
  it reads four sources that can genuinely disagree: the pins from `packages/weft/pyproject.toml`,
  which of them is a *pack* from each distribution's own `weft.packs` entry-point declaration,
  `active` from running discovery, and the installed version from `importlib.metadata`. Nothing is
  derived from anything else (`L5.6`). It is deliberately **not** a skew check: skew asks whether
  an installed version satisfies another distribution's declared specifier; this asks whether the
  combination the release set says was tested together is the one actually here. Planted and
  watched failing:

  ```
  $ # the release set's weft-store pin changed to 9.9.9
  AssertionError: ['weft-store: release set says 9.9.9, 2.0.0 is installed']. The release set
  names the version, and the environment that ran these tests is not the one it names — so
  'tested together' is a claim about something else.
  ```

  The pack filter carries its own self-test, because the whole check leans on it and the real tree
  agrees: `weft-kernel` is pinned and is not a pack, `weft-store` is both, and both facts are
  asserted so a filter that answered `False` for everything cannot pass this vacuously.

  **What the change cost in documents, and what noticed.** Five worked transcripts quoted the old
  status line — `manual/troubleshooting.md` ×4, `manual/operations-guide.md` ×1 — and one test
  assertion did (`tests/docs/test_quickstart.py`, repaired to assert the *fact* rather than the
  literal line, `L5.13`). Only the test failed the gate, because `08` §3 clause (a) executes the
  quickstart; the five transcripts are fenced text nothing runs and were found by grepping.
  **`docs/lessons.md` L6.19** is that finding, and it also records that `L5.29` said the same thing
  one phase earlier and was declined.
- [x] **6.5 ⚠** every deprecated surface names the release or date at which it is removed, in the unit G9 chose, and the clock is observable · owner `09` §3 · turns on — · sha `46a2761`
  **6.5 — the clock is derived, and its third state is the one that matters.** G9 chose the unit
  (`09` §2.3, dependency 3): "**Releases, not months, and the unit is one major of the publishing
  distribution.**" That makes the removal point a pure function of the publishing distribution's
  own installed version, so no pack author states it — `weft_kernel.seam.removal_for`, called from
  `PackRegistrar.deprecate`, carried on every `Deprecation` as a required field, and read by both
  consumers so they cannot drift: the registration wrapper's `DeprecationWarning` and
  `weft plugins doctor`'s flag line. A `removed_in` an author types is stale on that pack's next
  release with nothing to notice, which is `CLAUDE.md`'s measured rule applied to a number.

  **`UNPROMISED_BEFORE_1_0` is the member it would have been easy not to have.** G9 also settled
  that "inside 0.x a contract may move without a deprecation period but never silently", so a 0.x
  publisher's answer is **not** "removed in 1.0.0" — that promises a window 0.x explicitly reserves
  the right not to give. It is that there is no window, said out loud, which is what makes the clock
  *observable* rather than invented. Six distributions read `0.1.0` today (`09` §2.2), so this is
  the common case rather than a corner, and the test asserts `1.0.0` never appears in that render.
  The third member is an unreadable version — absent metadata, or a version whose major will not
  parse — reported rather than guessed (`docs/lessons.md` L5.9), carrying the raw string so
  "no version at all" and "a version I cannot read" stay different problems.

  **`packaging` is not available and never will be**, G1 fixing this distribution's dependencies at
  `pydantic` and `opentelemetry-api`, so the major is the leading run of digits — `2.0.0rc1` reads
  as major 2, where a bare `int(version.split(".")[0])` raises. That edge has its own test.

  **The subject is legitimately empty**, exactly as task 5.2f found: no first-party surface is
  deprecated today. So the derivation is exercised against a distribution that really is installed
  (`weft-store`, 2.x → `weft-store 3.0.0`) rather than only against the fake entry points the other
  discovery tests use — otherwise the only state ever seen would be `VERSION_UNREADABLE` and the
  check would pass while proving nothing about the rule it exists for.

  **Kernel growth, flagged rather than absorbed.** `weft-kernel` went 2,997 → 3,063 lines. It was
  already past fitness function 3's 2,800 review trigger before this task and the 3,500 budget is
  untouched — but the trigger is a conversation, and this is where it is recorded that the
  conversation is owed. The 66 lines are `RemovalClock`, `Removal` and `removal_for`. They are here
  rather than in `weft-cli` because `01` → *The kernel boundary* puts "the contract *mechanism*:
  registration and versioning" and "the `plugins doctor` computation" in the kernel's own column,
  and because both consumers need the same answer; G9's "the kernel gains zero lines" was about
  *refusing a load* on skew, which this neither is nor does.
- [x] **6.6** every published distribution installs alone into a clean environment and imports — fitness function 1's primary half applied to all of them, not only the kernel · owner `09` §5 → *Install path* · turns on — · sha `54af70d`
  **6.6 — twenty distributions, each installed on its own and imported.** `scripts/check_isolated_installs.py`
  generalises `scripts/check_kernel_isolated.py`, which has done exactly this for `weft-kernel`
  alone since Phase 0, and it runs the same way: `poe isolated-installs`, in its own CI job, never
  inside `ci-checks` — the check needs a clean environment this repository's virtualenv cannot
  provide, which is the whole reason `kernel-isolated` is not in the composite either.

  ```
  $ uv run poe isolated-installs
  weft: installed alone, ships no code — nothing to import.
  weft-chunk: installs alone and imports weft_chunk.
  weft-cli: installs alone and imports weft_cli.
  [...]
  weft-store: installs alone and imports weft_store.
  ```

  **Watched failing, with the exact defect it exists for** — an undeclared sibling import planted
  in `weft_chunk/__init__.py`, which the workspace hides because everything is on `sys.path`
  together:

  ```
  ModuleNotFoundError: No module named 'weft_store'
  weft-chunk does not install and import in a clean environment. It needs the workspace, a path
  dependency, or an environment variable to import — see G1, The kernel boundary.
  failed: weft-chunk
  ```

  **A wheelhouse, not an index.** Every member is built into one temporary directory *before* any
  member is installed, and `--find-links` points at it — a sibling requirement has to resolve
  against a wheel that already exists there whatever the sorted order, and none of these
  distributions is on an index yet. That is **6.13**, which does this same install from a real
  index on a machine that has never seen the repository.

  **`packages/weft` is answered, not skipped.** The release set ships no code, so it is installed
  and reported as having nothing to import — reached from the structural fact that it has no
  `src/`, never from its name, which is the half `docs/lessons.md` L5.27 requires of a sweep: it
  must be able to answer the question for everything it sweeps, and a distribution with a `src/`
  whose module will not import still fails.

  **One reader, and fitness function 10(a) now uses it.** `scripts/publish_set.publishing_members`
  owns "which members publish, and what does each ship" — the member globs, the
  `[tool.weft] publish = false` opt-out from task 6.2, and the `src/` test. FF10(a)'s workspace
  side calls it instead of keeping a second copy; the clause's independence is untouched, because
  its *other* side is parsed out of `.github/workflows/release.yml` and this reader never opens it.
  **Built by a dispatched `weft-implementer` (sonnet)** against a test written first and closed
  ahead of the dispatch — the split `phase-step` asks for, and the first task in this phase to
  actually take it (`docs/lessons.md` L6.20).
- [x] **6.7** the sdist builds and its tests pass from the sdist, so nothing load-bearing is present in the checkout and absent from the artefact · owner `09` §5 → *Install path* · turns on — · sha `cdb49c1`
  **6.7 — and the run found three things the workspace was hiding.** `scripts/check_sdists.py`,
  `poe sdists`, its own CI job beside `isolated-installs`. Two phases: a completeness diff per
  distribution, and — under `--run-tests` — every sdist installed together into one clean
  environment with the suite run against the artefacts instead of the editable workspace.

  **Phase one, watched failing with `09` §5.2's own named case** — a data file present in the
  checkout and absent from the artefact, planted by excluding `weft-retrieve`'s pipelines from its
  sdist and restored afterwards:

  ```
  weft-retrieve: a data file, locale catalogue or entry-point declaration is present in the
  checkout and absent from the artefact — missing ['src/weft_retrieve/pipelines/no-retrieval.yaml',
  'src/weft_retrieve/pipelines/retrieve-then-generate.yaml', 'src/weft_retrieve/pipelines/route.yaml']
  failed: weft-retrieve
  ```

  That is not hypothetical: `02` §3 makes a pipeline *data*, so a backend packaging `.py` and
  nothing else would ship a distribution that installs, imports, registers, and cannot resolve one
  of the pipelines it declares — invisible to every check that reads the checkout, including
  task 6.6's.

  **Phase two found a real, undeclared dependency — and it is this task's own failure condition
  one layer up.** `weft_cli.contract_reference` shells out to `sys.executable -m ruff`, and
  `weft-cli` declared `ruff` **nowhere**: it worked only because the workspace root's
  `[dependency-groups] dev` carries it. Installed from its own sdist, four tests failed with
  `CalledProcessError`. Task **6.6** could not have caught this and was green — `import weft_cli`
  never reaches a subprocess call, which is `docs/lessons.md` **L6.24**: an import probe measures
  import-time dependencies and a run-time one is invisible to it. Repaired here, in the shape
  `weft-eval[bertscore]` and `weft-otel[otlp]` already have: `[project.optional-dependencies]
  reference = ["ruff>=0.16.0"]`, plus `ReferenceFormatterUnavailableError` naming the extra
  instead of a subprocess return code, plus its `manual/troubleshooting.md` entry — which
  `08` §3 clause (d)'s ratchet demanded before the gate would go green, exactly as designed.

  **`--run-tests` runs the suites that are claims about the *code*, and that is a correction to
  this task's own brief.** `tests/unit` and `tests/integration`; not `tests/architecture` or
  `tests/docs`, which read `packages/*/pyproject.toml`, walk the repository and assert about the
  workspace. Two of them cannot answer the question in an artefact environment even in principle —
  `test_ff8_trust_model.py` needs `weft-canary` installed and `weft-canary` is deliberately never
  published (task 6.2's opt-out marker). `docs/lessons.md` **L6.25**. Result: **1612 passed** from
  the built sdists.

  **The third finding is filed rather than fixed: task 6.27.** `tests/docs/test_question_set.py`
  fails from freshly-resolved sdists — five quotes stop being literal spans of their documents.
  Measured rather than inferred: `uv.lock` pins `pypdf` at **6.16.1**, a fresh resolve takes
  **6.16.2**, and `weft-pdf` declares `pypdf>=6.16` with no ceiling. A *patch* bump of the
  extraction backend moves the text, and the check's own message anticipates it — "either the
  extraction backend moved and the quotes must be re-taken from its output, or the quote was never
  in that document". Narrowing phase two took this out of the sdist job's view, and nothing else in
  CI resolves freshly, so **no check in this repository would now notice it**. That is why it is a
  task and not a footnote, and why it bears on **6.9**: "the same corpus, pipeline and model
  versions" has to include the backend that produced the text.
- [x] **6.8** a cancelled run leaves the store durable to its last finished batch, a resumable delete finishes on the next command, and a store written by release *n* is read by release *n+1* — executed once, not asserted · owner `09` §5 → *Operability* · turns on — · sha `f5c37e3`
  **6.8 — nothing was built, and that is the finding.** Every mechanism these three promises rest
  on already existed and every one was unit-tested; **none had been run end to end against the real
  store.** That is the same gap `L6.14` was written about one task earlier: `list_sources()` was
  true of the contract, unit-tested against a double, and false of the running system. A promise on
  a release checklist is worth exactly what has been executed of it, which is what `09` §5.2's own
  *"Fails if this has never been run"* says in as many words.

  **The resumable delete, through the shipped binary, from outside the repository.** The crash is
  simulated where it actually happens — after `delete_source` wrote the tombstone and before it
  deleted the nodes, which is unreachable from outside because the real method does both in one
  call:

  ```
  $ weft index . --yes
  produced 1, nothing to produce 0, failed 0. nodes now stored: 1.
  $ psql -c "UPDATE weft_sources SET status='deleting'"   # the crash, mid-delete
  UPDATE 1                                                 # 1 node still present
  $ weft reconcile --mode repair --dry-run
  'reconcile' is a destroy-class command [...] mode 'repair' will run against 1 participant(s):
  pgvector (weft-store). It refuses to run with no terminal to confirm in [...]
  $ weft reconcile --mode repair --yes
  mode 'repair' — 1 participant(s):
    pgvector (weft-store): examined 1, removed 1, backfilled 0
  # 0 nodes, 0 sources
  ```

  **Both plants watched going red**, because all three scenarios passed on the first run and a
  check that has never been seen failing is indistinguishable from one that cannot (`L5.19`):
  removing `upgrade` from the newer class gives `SchemaVersionRefusedError: 'operability-reading'
  data was written at version '1', but the installed class is at '2' and declares no upgrade path
  from it` — the refusal is real, and the upgrade is what makes the read work rather than the read
  being trivially fine; and a repair pass that removes nothing fails `assert report.removed == 1`.
  Each scenario also asserts its **precondition** first — the batch is in the store, the tombstone
  is standing, the payload is at the older version — so none can pass by having nothing to check.

  **What "release *n* → *n+1*" can honestly mean today, stated rather than assumed.** Nothing is on
  an index yet — that is **6.13** — so there is no *n+1* release to install, and a test claiming
  otherwise would be theatre. What exists is the axis G9 settled for exactly this problem: the
  contract version is not available at the read site, because the pack that wrote a row may not be
  installed, so the stored bytes carry `__schema_version__` and a reader **upgrades or refuses**.
  That path is executed here against the real store — bytes written by a class calling itself `1`,
  read back by the class calling itself `2`, value intact. The release-to-release form is owed once
  something has been published twice, and **6.13** is where it becomes possible.

  **Two things this task found on the way.** The interrupted-run scenario failed first with
  `no 'weft-chunk' is registered for ExtModel` — a hand-built `Registry` runs no pack's
  `register()`, so nothing populates the process-global namespace registry. That is exactly the
  latent dependency **6.17** names, met from a second direction, and this module registers what it
  needs rather than inheriting it from whichever file ran first. Doing so then failed in the full
  suite with `DuplicateRegistrationError`, because `register_ext_model` refuses even a
  re-registration of the same class while `register_from_reports` skips it — contradicting
  `rehydrate.py`'s own docstring, which says the two are identical *and names this caller*.
  `docs/lessons.md` **L6.28**.
- [x] **6.9** every shipped technique's claimed improvement is a delta against the published baseline on the same corpus, pipeline and model versions · owner `09` §4, V3; §5 → *Quality* · turns on — · sha `6c0cb18`
  **6.9 — half of this existed and the half nothing checked was the sentence's actual subject.**
  `eval/check_baseline.py` (task 4.8) answers *"did this run reproduce the baseline"*: intervals
  derived from the baseline's own repetitions, `IncomparableRunsError` when the corpus, pipeline or
  model versions differ. `09` §5.2's failure clause is about somewhere else entirely — *"Fails if
  any **claim in the documentation** has no run behind it"* — and a number in a manual is what a
  reader acts on, reachable by anyone with a text editor and no run at all.

  **Two clauses, because a marker alone polices only the claims that opted in.** (a) a claim is a
  fenced ` ```text id=claim:<technique> ` block naming a published run — the tagged-block
  mechanism FF11 already uses for pipelines; (b) **no claim-shaped prose exists outside one**,
  swept over `manual/` and `README.md` with a pinned waiver. Clause (b) is the one that catches
  what actually happens: *"raptor improves recall by 12%"* typed straight into a manual. Planted
  and watched: `user-manual.md: improves recall by 12% over the baseline`.

  **The sweep is over `manual/` and `README.md`, not `docs/`** — `08` §1 defines the shipped
  documentation set and `09` §5's clause sits under *Security, licensing, documentation*. `docs/`
  is where the rule is stated and quoted at length; sweeping it would make every discussion of the
  rule a violation of it.

  **And the check shipped inert once, with its own non-vacuity test passing.** The prose pattern's
  gap was `[^.\n]{0,80}`, which cannot cross a `.`, and the phrasing both real passages use is
  `"improvement... reported against a baseline"` — so clause (b) matched **nothing in the entire
  shipped set** while all five tests were green, the waiver excusing nothing and the
  waiver-liveness test asking whether the text was *present* rather than whether the check *fired
  on it*. Found only by emptying `CLAIM_PROSE_WAIVED` and watching the check stay green, which is
  `phase-step` → *Finish* item 3 doing exactly the job it exists for. Excluding newlines was the
  second miss: the manuals wrap at 100 columns, so a claim and its number routinely sit on
  different lines. The sweep now runs over whitespace-collapsed text and the liveness test asserts
  the sweep *fires*. `docs/lessons.md` **L6.29**, whose closing line names the next thing to check:
  `test_ff0_gate_in_the_gate.py`'s own waiver-liveness test has the same shape and may have the
  same hole.

  **Preceded by 6.27**, which pinned the extraction backend the baseline's quotes were taken from
  — "the same corpus" has to include the text the corpus actually reads as.
- [x] **6.10** the published trust posture is the one `02` §2 actually claims — no package page implying isolation the design refused · owner `09` §5 → *Security, licensing, documentation*; `02` §2 · turns on — · sha `c58ee66`
  **6.10 — the gap was exactly the one `09` §3 predicts.** That section says the posture "must
  appear in the published README of the release, **not only in the plan**", and warns that "a
  design that refused to simulate a control it cannot enforce would be undone by a package page
  that lets a reader assume one exists." The repository's own `README.md` has carried the posture
  since Phase 0. `packages/weft/README.md` — the `readme` the release set *declares*, and therefore
  the page an index renders — carried **none** of it: no privileges, no trusting, no list of what is
  out of reach. Everything a stranger reads before installing said nothing about the one thing
  `02` §2 spent a section refusing to simulate. It says it now, including what Weft gives instead
  (`doctor`'s disclosure column, `[packs] allow`'s refusal-before-import) and that a disclosure is
  what a pack says about itself, checked by nothing.

  **Two clauses, and the second needed the words rather than avoiding them.** (a) the published
  page states both claims — full privileges, installing is trusting — and *names* the absences,
  because "no sandbox" is the half a reader acts on and the half a marketing edit removes first;
  (b) no published surface names an isolation control without denying it, swept over
  `packages/weft/README.md`, `README.md` and every distribution's own one-line `description`, which
  is what a search result shows. A sweep that flagged the word alone would flag every honest
  disclaimer and be switched off in a week; one that ignored it would miss the only sentence that
  matters.

  **Planted and watched:** `packages/weft/README.md: Every pack runs in a secure sandbox, isolated
  from your data.`

  **And the sweep had a false negative, arrived at by accident.** `README.md`'s distribution listing
  is a fenced block containing `kernel-isolated`; collapsed into one enormous "sentence", the word
  "refused" from a different line excused it. Fences are stripped now. The direction of that failure
  is the one this check must never fail in, and it was found by asking what the sweep actually
  matched on the real pages rather than trusting that it passed — the same move that caught
  `docs/lessons.md` **L6.29** one task earlier.
- [x] **6.11** every file in the release is accounted for as original work, re-checked with `reference-audit`, with `LICENSE` and `NOTICE` in every built artefact · owner `09` §5; `CLAUDE.md` → the originality rule · turns on — · sha `255884f`
  **6.11a — the licence was in the repository and in no artefact.** Measured before it was fixed:
  **not one wheel or sdist carried `LICENSE` or `NOTICE`, and no distribution declared a `license`
  at all.** Twenty wheels were one `uv publish` from an index with nothing in them for anyone's
  legal team to read. Two approaches were tried and rejected on evidence rather than taste:
  `[tool.hatch.build.targets.wheel.force-include]` with `"../../LICENSE"` **fails the build**, and
  PEP 639's `license-files` resolves relative to the distribution's own directory, so the root
  files are unreachable from a per-distribution build. So each of the twenty carries its own copy,
  declares `license = "MIT"` and `license-files = ["LICENSE", "NOTICE"]`, and **the copies are held
  byte-identical to the root originals by a check** — which is what makes twenty copies safe rather
  than twenty chances to ship a different promise. `files_that_must_ship` now requires both, so
  task 6.7's comparison against the real archive is what proves they are in the tarball rather than
  merely in the directory. Verified in built artefacts:

  ```
  weft_cli-0.1.0.dist-info/licenses/LICENSE     weft-0.1.0.dist-info/licenses/LICENSE
  weft_cli-0.1.0.dist-info/licenses/NOTICE      weft-0.1.0.dist-info/licenses/NOTICE
  weft_cli-0.1.0/LICENSE  weft_cli-0.1.0/NOTICE     (sdist, both)
  ```

  **6.11b — the originality re-check, measured rather than recalled.** `reference-audit`'s step 5,
  across the whole shipped tree against `reference/src` and `reference/system`:

  - **17,241 substantive source lines in Weft, 23,114 in the reference, 10 identical** — and every one
    of the ten is a bare class declaration in the `LLMError` taxonomy
    (`class LLMRateLimitError(LLMTransientError):` and its nine siblings). That is T1.7, which
    `04` §B assigns as *lift the design, rewrite the code*: a taxonomy's asset **is** its names and
    its transient/permanent axis, both of which `04` documents, so two independent implementations
    of it necessarily agree on the declarations. No body, no docstring and no comment is shared.
  - **0 identical string literals of 40 characters or more**, across 2,650 in Weft and 7,113 in the
    reference. This is the pointed measurement, because prompts, messages and word lists are where
    transcription is easiest and hardest to notice.
  - **The three pre-flagged contamination items have not arrived.** No `RANDOM_SEED = 224`, no
    `### --- Our code below --- ###`, no STX Next header; `weft_index.raptor` imports only the
    standard library and `pydantic` and states in its own docstring that its clustering is a fresh
    small algorithm rather than the reference's UMAP+GMM.
  - **One near-match was chased to the end rather than explained away**, and it is the finding
    worth having. `weft_enhance.keybert_stand_in`'s 73-word stop list is a **strict subset** of the
    reference's 127-word list — no word of its own — which is the shape a transcribe-and-prune
    produces. It is not one: both are drawn from the same canonical population of English function
    words, so a short list sits inside a longer one by construction, and the discriminating
    evidence runs the other way — the reference's list carries `don` and `doing`, the tokenisation
    artefacts of the NLTK list it derives from, and **neither is here**. A prune keeps artefacts;
    it does not remove exactly the ones that would identify the source. The module's comment
    claimed *"any two people asked to write common English stopwords from memory would largely
    agree"*; it now carries the measurement instead, because an unevidenced "written fresh" is
    precisely what this audit exists to test.

  **The forward and reverse gap audit is not this task's** — it is `phase-step` → *Close the phase*
  step 3, run against the whole phase rather than against the release's files. This task is the
  originality half of `reference-audit` and the licence in the artefact.
- [x] **6.12** a newcomer installs, indexes and asks from the README alone, without opening `docs/` · owner `09` §5; `08` §1, *Quickstart* · turns on — · sha `c3427a4`
  **6.12 — measured before it was fixed: they could not.** `README.md`'s *Start here* pointed at
  `docs/README.md` as "the single source of truth", its table listed five design documents, and
  every runnable block on the page was a maintainer's command — `poe ci-checks`, `next_task.py`.
  **No install, no index, no query anywhere.** Somebody arriving at the repository saw a plan
  rather than a product, and the first thing `09` §5.2's checklist promises them was the one thing
  the page did not do. The page now carries the whole path, and it is executed rather than
  believed: `tests/docs/test_readme_is_enough.py` is `08` §3 clause (a)'s harness aimed one page
  over, because the quickstart is reached *from* the README and a newcomer who has to be told where
  to go has already opened something else.

  **Running it found the wall a newcomer would hit**, on the first attempt and not in review:

  ```
  README.md block 'ask' exited 1:
  no [llm.roles] entry maps role 'route'. Roles mapped in weft.toml: (none mapped).
  ```

  `weft ask` refuses by name until a provider is mapped — correct behaviour, and a dead end for
  somebody with no account thirty seconds into their first try. The path uses `--retrieve-only`,
  which is the offline half `manual/quickstart.md` already uses, and the prose says what the flag
  is doing and what dropping it needs. Walked by hand from outside the repository afterwards,
  including that failure path.

  **Two clauses, because "the commands ran" is not the promise.** The second is
  *"without opening `docs/`"*: every executed block is asserted to reference `docs/` nowhere. A
  runnable path that says "see `docs/03-cli.md` for the flag you need" satisfies a harness and
  fails the checklist. **`install` is waived from execution**, one entry, for the reason
  `test_quickstart.py`'s own waiver exists: nothing is on an index until **6.13**, and both empty
  at that task.
- [x] **6.14** the fitness function `01` has named since day one exists: **FF5**, *every declared capability resolves* — a plugin's declared capability resolves to a live implementation at discovery, or the plugin declares it unavailable and says why · owner `01` → *Fitness functions* 5; `11` · turns on **FF5** · sha `0a136c6` · **added 2026-08-22 by Phase 5's lessons drain**, found by FF16 clause (a) on its first run — the same defect as `L5.4` and unnoticed for the same five phases. Waived in `tests/architecture/test_ff16_checks_are_real.py`'s `FITNESS_FUNCTIONS_NOT_YET_DUE` until this closes
  **6.14 — FF5 exists, and this entry says which of its clauses it holds.** Named in `01` on the
  project's first day, built five phases later: `docs/lessons.md` L5.4 exactly, caught by FF16
  clause (a), the check written *from* that lesson finding the lesson's own subject still open.
  FF16's waiver carried a warning worth answering rather than clearing — *"building a fitness
  function hastily at a phase close is how a check that cannot fail gets written."*

  **What a declared capability is here.** G4 made a *store* capability derived, asked of the
  registered class with `issubclass`, so there is nothing there to disagree with itself. The
  declaration FF5 is about is an extractor's **accept set** — a pack says *"I handle `.pdf`"* — and
  that is the reference bug `docs/README.md` opens with, which **happened here, predicted by line
  number before it did**: `11` §2.1 said filtering on one pack's module constant would make `.pdf`
  silently invisible the moment a second extractor pack shipped, `weft-pdf` shipped at 2.27, and
  `weft index corpus/mrmr` walked nine PDFs, matched none and **exited 0 reporting success**.

  **Clause (a), structural over the AST** — no call site passes a pack constant as
  `discover_source_docs`'s `extensions`, following a local name back through its assignments
  because the real call writes `readable = present & accepted`. Watched failing with the
  historical defect reintroduced in the real tree. **Clause (b)** — every extension a live
  extractor declares is in the set ingest accepts, read off the registered classes and off the
  shipped derivation, so a derivation that started dropping a suffix fails while (a) stays green.

  **Clause (c) is NOT held and is pinned rather than pretended.** *"or the plugin must declare it
  unavailable and say why"* needs `PackStatus.PARTIAL` to have a mechanism, and it has never had
  one: `weft_kernel.discovery`'s own docstring deferred it in Phase 0 — *"the mechanism that
  produces it is G4's conditional registration, a later step's job"* — and no later step took it.
  The one real instance is `bertscore`, which registers unconditionally and answers `Failed` at
  *run* time naming the missing extra: saying why, one moment too late.
  `PLUGINS_REPORTING_UNAVAILABILITY_TOO_LATE` holds it, one entry, with a test proving the entry
  names a live registration rather than a string somebody typed. **Task 6.29** empties it.
  `FITNESS_FUNCTIONS_NOT_YET_DUE` is now empty.

  **The first draft of this check broke two other tests, and how that was diagnosed is
  `docs/lessons.md` L6.32.** It called `discover_for_reference()`, which discovers open and
  therefore imports `weft-canary` — whose entire purpose is to prove it was *never* imported — so
  `test_ff8_trust_model.py` failed for every run this file preceded and passed alone.
  `test_ff2_no_privileged_builtins.py` restricts its own `allow` for exactly that reason and says
  so; this one now does too. The lesson is not the import: `uv sync` was run and then **FF8 alone**,
  it passed, and that was written up as venv drift — a green from a narrower scope read as evidence
  about a change. The next full run said otherwise. The entry was rewritten to the real cause
  rather than left standing.
- [x] **6.15** every architecture check proves it can fail: `CHECKS_WITHOUT_A_SELF_TEST` in `tests/architecture/test_ff16_checks_are_real.py` shrinks to empty, one file at a time, each with a planted disagreement watched going red · owner `01` → *Fitness functions* 0; `05` → `lessons.md` L5.6, L5.19 · turns on — · sha `c71538e` · **added 2026-08-22 by Phase 5's lessons drain**. Seven files predate FF16 and carry no self-test; the ratchet is pinned so nothing may be added to it
  **6.15 — the ratchet is empty, and two of the seven were never what the constant said.** Taken
  out of ledger order, in the window a dispatched implementer held task 6.6: writing or changing a
  test is the one thing `phase-step` never delegates, so this is work only the dispatching context
  can do, and doing it while waiting is the whole reason the window existed. (It also produced
  `docs/lessons.md` L6.22 — the tree was shared, and the agent paid for that.)

  **Four files genuinely had none, and each was given one planted through its own real helpers**,
  never against hand-written sets — a self-test asserting `{"arch"} - set() == {"arch"}` proves
  that `frozenset.__sub__` works:

  - `test_ff0_gate_in_the_gate.py` — a gate sequence that forgot `arch`, and a suite the test task
    never reaches, both computed by `table_at`/`str_list_at`/`_covered_roots`.
  - `test_ff1_boundary.py` — a planted file importing `psycopg` and `openai.types`, run through
    the real `_top_level_imports`, in all three AST shapes; plus the stdlib and `weft_kernel`
    exclusions exercised in the same file, and a second self-test for the dependency reader. This
    is the file whose reference ancestor "used a denylist, matched zero imports, and exited 0 on a tree
    with 11 violations" — a check nobody had watched fail, exactly.
  - `test_ff3_kernel_budget.py` — a fixture whose answer is known (four code lines under a
    three-line module docstring, a comment and a blank), so a counter that stopped excluding
    docstrings reads as kernel growth rather than as a broken count.
  - `test_ff7_colour_integrity.py` — all four spellings of the `asyncio.run` bridge caught, and the
    two near-misses (`subprocess.run`, a merely-imported `asyncio`) not caught; plus a walk floor.

  **Two were waived and had a self-test all along**, under names this clause did not recognise:
  `test_ff2_no_privileged_builtins.py`'s `test_a_registration_outside_discovery_is_caught` and
  `test_ff8_trust_model.py`'s `test_the_equality_check_is_not_vacuous`. Both were renamed to the
  convention rather than duplicated, and FF2 gained a second one, because its existing test covers
  the registry equality and says nothing about the *import* comparison — a different comparison
  over a different input that had never been observed catching anything.

  **The seventh was the pattern's fault, not the file's.** `test_ff11_pipeline_integrity.py`
  carries four self-tests named `..._would_be_caught`, each planting a disagreement and watching
  it go red. `_SELF_TEST` recognised two spellings and not that one, so the file was recorded as
  carrying none — false about the tree on the day the constant was written. The regex was widened;
  renaming four accurate test names to satisfy a pattern would be the check dictating the tree.
  This is `docs/lessons.md` **L6.4** in its own home: read the population, not the declaration.

  **And FF8 had stopped describing the shipped command.** Its clause (c) claims to parse "the text
  `weft plugins doctor` itself would print" and called `render_doctor(reports)` with the defaults —
  so from task **6.4** onward it compared against a rendering the binary no longer produces, while
  its own pattern went on matching the shape it had itself produced. Repaired to render the way
  `PluginsDoctorCommand` renders. **`docs/lessons.md` L6.21** is that finding: a
  backward-compatible default keeps a check agreeing with the shape it already had, which is
  indistinguishable from the check working.
- [x] **6.16** a `--json` consumer can tell one event shape from another: the newline-delimited stream carries a discriminant, so a `StreamEvent` and an `ErrorEnvelope` are distinguishable without guessing by key presence · owner `03` → *Output*; `09` §3 · turns on — · sha `476c105` · **added 2026-08-22 by Phase 5's lessons drain** (`lessons.md` L5.16). Additive under `09` §3's *"promised, additively"* rule, which is why it is Phase 6's and not a Phase 5 repair
  **6.16 — the ambiguous pair was the whole problem.** `weft --json ask` writes `StreamEvent`
  lines while a pipeline runs and an `ErrorEnvelope` when the run refuses, on **one descriptor**,
  and a consumer told them apart by which keys were present. That is bad enough as guesswork and
  worse in the one case that matters: a `StreamEvent` whose `type` is `error` and an
  `ErrorEnvelope` are **both** "an error", in different shapes, so key-sniffing had to get exactly
  the ambiguous case right to be correct at all.

  **`kind` is a second key, never a widening of `type`.** `StreamEventType` answers *which event*;
  `LineKind` answers *which line shape*. Collapsing them would make `type: "error"` mean two
  unrelated things depending on what else is set — the "one word answering two questions" `09` §3
  refuses for the status vocabulary, one surface over. **Additive**, which is what makes it
  permissible at all: `09` §3 promises the machine-readable output additively, a consumer ignores
  what it does not recognise, and `envelope_version` does not move for a new field.

  Both shapes on one stream, from the shipped binary:

  ```
  $ weft --json ask "x" --pipeline nope
  {"kind":"stream-event","type":"done","role":"","text":"","message":""}
  {"kind":"error-envelope","envelope_version":"1.0.0","error":"UnknownPipelineNameError",...}
  ```

  **Fitness function 7(a) caught the first draft of the test**, which called `asyncio.run` in a
  helper: exactly one `asyncio.run` in the whole tree, at `weft_cli.cli`'s entry point. The test is
  `async def` and awaits, which is what `asyncio_mode = "auto"` is for.
- [x] **6.17** `tests/integration/test_ingest_pipeline.py` passes on its own: the test-order dependency confirmed at task 5.2g is removed, so the file's result does not depend on another file having run first · owner `01` → *Fitness functions* 0 · turns on — · sha `7bcac16` · **added 2026-08-22 by Phase 5's lessons drain** (`lessons.md` L5.21)
  **6.17 — the cause, not the symptom.** Run alone the file failed with
  `no 'weft-chunk' is registered for ExtModel`. A hand-built `Registry` runs no pack's
  `register()`, so nothing calls `PackRegistrar.add_ext_model` and nothing reaches
  `weft_store.rehydrate`'s **process-global** namespace registry; the file passed only because some
  other test file had run a real `discover()` first. It registers what it needs now and depends on
  nothing having gone before it.

  **Through `register_from_reports`, not `register_ext_model`** — the latter refuses a second call
  even for the same class, so the obvious fix works alone and fails in the full suite. That
  difference contradicts `rehydrate.py`'s own docstring, which says the two are identical *and
  names this exact caller*: `docs/lessons.md` **L6.28**.

  **The family is wider than this one file.** Task 6.8 met the identical dependency from a second
  direction building its interrupted-run scenario, and task 6.14's first draft created a *new* one
  — importing `weft-canary` through open discovery, which made `test_ff8_trust_model.py` fail for
  every run it preceded. A process-global registry that any test may write to is the shared
  mutable state underneath all three.

- [x] **6.18** `weft delete` reaches every store this project actually runs data through: the fan-out takes the configured `[services] store` **plus** every `NodeStore` named by a pipeline in the catalogue or by a persisted run record, and the participant list it prints says who was asked · owner `02` §1 → *Extended by G13*; `05` → G13 · turns on — · sha `6ae68ee` · **added 2026-08-22 by G13**, which settled the question task 5.1a defaulted (`lessons.md` L5.25, L5.32). The reproduction is task 5.7's own: index with `--pipeline kg`, delete the source, and read the graph store — it must be empty. A test that only asserts the participant *list* would pass on the tree as it stands, so the check is the store's contents
  **6.18 — what the fan-out now reaches, run for real outside this repository.** The property is
  a set, not a list: `weft_cli.participation.stores_in_use` computes the configured
  `[services] store` plus every stage name in `full_catalogue` or in a persisted `RunRecord`
  that is registered under `NodeStore`, and `weft_cli.fanout.participants_for` filters
  `NodeStore` down to that set for `weft delete` and `weft reconcile` alike. The dev venv has
  no `weft-example-graph` installed, so `weft-qdrant` and `weft-store` stand in for the two
  registrations; the demonstration is that the second one joins **because a document names it**
  and for no other reason:

  ```
  $ cat weft.toml
  [services]
  store = "qdrant"

  [packs.weft-store]
  dsn = "postgresql://nobody@127.0.0.1:1/none"

  $ ls pipelines/          # nothing names a second store
  $ weft reconcile --dry-run
  'reconcile' is a destroy-class command, called with {'mode': None, 'dry_run': True}. mode
  'full' will run against 1 participant(s): qdrant (weft-qdrant). [...]

  $ cat > pipelines/kg.yaml <<'YAML'
  name: kg
  stages:
    - id: store
      use: qdrant
    - id: second-store
      use: pgvector
  YAML
  $ weft reconcile --dry-run
  'reconcile' is a destroy-class command, called with {'mode': None, 'dry_run': True}. mode
  'full' will run against 2 participant(s): pgvector (weft-store), qdrant (weft-qdrant). [...]

  $ rm pipelines/kg.yaml && cp /tmp/one-run.json runs/r1.json   # run history alone, no document
  $ weft delete doc-1
  'delete' is a destroy-class command, called with {'source_id': 'doc-1'}. 'doc-1' will be
  removed from 2 participant(s): pgvector (weft-store), qdrant (weft-qdrant). [...]
  ```

  Both halves of *participation follows use* are visible there: a store a document names joins,
  a store only the run history names joins, and — asserted in
  `tests/unit/weft_cli/test_commands.py::test_delete_leaves_a_store_nothing_names_alone` — a
  registered store nothing names still does not, which is the half of task 5.1a's narrowing G13
  kept. **The check is the store's contents, per this task's own line**, and that is
  `test_delete_empties_a_graph_store_a_catalogue_pipeline_names`: it failed
  `assert {'doc-1': 4} == {}` before the change, the derived store's data outliving its deleted
  source.

  **Two things this task deliberately did not do.** No ordering: `02` §1 states the rule as a
  set and never says the configured store is asked first, so the fan-out keeps
  `participants_for`'s own name ordering — a first draft of the test asserted an order, the
  implementer invented a `_configured_store_first` policy to satisfy it and said so, and the
  repair was to the test (`docs/lessons.md` L6.10). And no declaration: nothing opts in, which
  is what makes a graph pack a participant with no core edit.

  **A run record that will not parse is refused, not skipped** — `UnreadableRunRecordError`,
  exit `1`, `manual/troubleshooting.md` → *Who a fan-out reaches*. The run history is read
  precisely to find a store the catalogue no longer names, so the unreadable record may be the
  only one naming it; skipping it would let that store outlive its source in silence, which is
  `docs/lessons.md` L5.9 applied to a directory sweep. Found by running the binary — the error
  class was caught first by task 0.14's own troubleshooting ratchet, which failed the gate
  naming it.

- [x] **6.19** a participant that is not the primary store can build `reconcile --mode full`: the CLI registers the configured `NodeStore` into the `Context` a reconcile pass carries, and a pack reaches it with `ctx.require(NodeStore)` · owner `02` §1 → *Extended by G13*; `05` → G13 · turns on — · sha `e98e092` · **added 2026-08-22 by G13** (`lessons.md` L5.24). No contract moves — `Context.require` and `scan`/`count`/`list_sources` already exist, and `STORE_CONTRACT_VERSION` staying put is part of the property. Demonstrated by deleting `GraphBackfillUnavailableError` from `examples/weft-example-graph` and having `full` actually backfill
  **6.19 — the backfill, run for real from an installed wheel.** A throwaway venv with
  `examples/weft-example-graph` installed alongside the first-party distributions, a project
  directory outside this repository, and the one `compose.yaml` container. The corpus is indexed
  by the **default** pipeline, which has no graph stage — the exact case `02` §4's table row is
  about — and the graph store is empty afterwards:

  ```
  $ weft index docs --yes
  produced 1, nothing to produce 0, failed 0. nodes now stored: 2.
  mode 'repair' — 2 participant(s):
    example-graph (weft-example-graph): examined 0, removed 0, backfilled 0
    pgvector (weft-store): examined 0, removed 0, backfilled 0
  $ psql -tAc 'select count(*) from exgraph_nodes'
  0

  $ weft reconcile --mode full --dry-run --yes
  mode 'full' would run against 2 participant(s):
    example-graph (weft-example-graph): 2 node(s) in the corpus have no graph data yet and
      would be backfilled from their own stored content
    pgvector (weft-store): no unfinished deletions; nothing to converge

  $ weft reconcile --mode full --yes
  mode 'full' — 2 participant(s):
    example-graph (weft-example-graph): examined 2, removed 0, backfilled 2
    pgvector (weft-store): examined 0, removed 0, backfilled 0
  $ psql -tAc 'select (select count(*) from exgraph_nodes), (select count(*) from exgraph_entities)'
  2|4
  ```

  The same two commands raised `GraphBackfillUnavailableError` before this task. That class is
  **deleted**, not left unraised: it was a truthful design finding while the access did not exist
  and would have been a lie the moment it did. `weft_cli.commands._register_corpus` is the whole
  CLI-side change — the configured `NodeStore` put on the `Context` inside `ReconcileCommand.run`
  and `IndexCommand._auto_reconcile`, never inside `describe_impact`, since a confirmation prompt
  must not connect to the corpus before consent. **No contract moved**, which is part of the
  property: `Context.require` is G1's one resolution seam and `scan`/`count`/`list_sources`
  already answered *what should exist*, so `STORE_CONTRACT_VERSION` did not need to and did not.

  **The failure path, also run:** a `[services] store` naming nothing registered refuses with
  *"[services] store names 'no-such-store', and no registered NodeStore has that name. Registered
  NodeStore names: 'example-graph', 'pgvector'."* — and a participant reaching for a corpus that
  was never registered gets `UnresolvedServiceError` naming `NodeStore` and what *is* on the run,
  asserted at `tests/unit/weft_cli/test_commands.py::test_a_participant_asking_for_a_corpus_that_
  is_not_there_is_told_so`. An unavailable corpus is not a backfill of zero.

  **Carried to 6.21, deliberately:** `02` §4's `Reconcilable` row promises two things, and only
  one is built. `full` backfills — done here. `repair` *"drops orphans left by anything the fan-out
  missed"* needs the same corpus access but is a separate promise about a different mode, and
  widening `repair`'s behaviour inside this task would have been a decision G13 did not settle.
  6.21 checks that table row by row, and this is the row it will find.

  **Found while doing it, and filed rather than folded in:** nothing in the gate runs
  `examples/*/tests/` — task **6.23**, `docs/lessons.md` L6.12.

- [x] **6.20** a pack's `Command` result renders for a person: `registrar.add_renderer(ResultType, renderer)` is the seam, `Rendered` is published from `weft-command`, and the CLI's own renderers register through the same call so no built-in keeps a private path · owner `03` → *Plugin-contributed commands*; `05` → G13 · turns on — · sha `cffb8c2` · **added 2026-08-22 by G13** (`lessons.md` L5.30, and L5.15's producing/consuming rule). `COMMAND_CONTRACT_VERSION` moves under G9's two-audience rule. The unregistered-result fallback stays the honest structured dump — a floor, not a ceiling. Proven the way requirement 4 has to be, at runtime: `weft example-graph show` prints for a person from an installed wheel, and `weft_cli.render` holds no first-party table the check can find
  **6.20 — a pack's result, printed for a person, from an installed wheel.** The same throwaway
  venv shape 6.19 used: the first-party distributions plus `examples/weft-example-graph`, a
  project outside this repository, the one container.

  ```
  $ weft example-graph show
  1 node(s) carry graph data: 4 distinct entities, 6 distinct relations.
  top entities:
    Acme Corp (1)
    Globex Inc (1)
    Initech (1)
    Umbrella Ltd (1)
  exit=0

  $ weft example-graph show --entity "Nonesuch Ltd"
  1 node(s) carry graph data: 4 distinct entities, 6 distinct relations.
  neighbours of 'Nonesuch Ltd':
    (none)
  ```

  Before this task the same command printed `{"nodes_with_graph_data":...}` at a person while
  eighteen built-in commands printed for one. **`_RENDERERS` is deleted** — `weft_cli.render`
  holds no first-party dispatch table, asserted by a test that walks the module's own namespace
  three levels deep, because the table it forbids was a tuple of *pairs* and a one-level scan
  passed vacuously on the first draft (`docs/lessons.md` L5.19's rule, met by planting the real
  shape). The eighteen built-in renderers reach the dispatch through
  `registrar.add_renderer`, the same call the graph pack makes for `GraphShowResult`: requirement
  4 checked at runtime rather than asserted.

  **`COMMAND_CONTRACT_VERSION` → `2.1.0`, and the reasoning is recorded at the time it was
  taken** rather than left for a later task to reconstruct — the mistake task 5.2a had to correct.
  Under G9's two-audience rule this is additive for a caller *and* for an implementer: nothing on
  `Command` changed, `required_declarations` is untouched, and a pack registering no renderer
  still works, because the honest structured dump stays the floor. `ExitCode` moved to
  `weft-command` with `Rendered`, since a renderer that cannot say the run failed is one no
  built-in could have used — `weft delete` and `weft index` both compute their exit code from
  their own result's fields. `weft_cli.exit_codes` and `weft_cli.render` re-export both under
  `X as X`, so no other module in the tree changed an import.

  **Three checks bit during this task, and all three were doing their job.** Fitness function 6
  forced `packages/weft-command/pyproject.toml` to a matching minor. `test_the_double_carries_
  every_registrar_method` named `_NameCapturingRegistrar`'s missing `add_renderer` — the *fourth*
  recurrence of `L5.26`, and the first caught before a pack crashed on it, exactly as
  `add_pipeline_resource`'s own docstring predicted it would be. And **fitness function 9(b)
  failed the gate on two ordinary docstring sentences** in `weft_cli/render.py` that named the
  example pack; they were generalised rather than waived.

  That last one has a consequence for a task still open: **6.22's wording was corrected here**,
  before anyone implemented it. As filed it said FF9(b) should decide the question structurally
  *"never as a substring of file text"* — and a purely structural check would have missed both of
  the violations found today, since a docstring is neither an import, an entry-point declaration
  nor a registration literal. The check has a false-positive mode and a false-negative mode;
  6.22 now owns both. `docs/lessons.md` L6.13.

- [x] **6.21** the independence test is re-run against `examples/weft-example-graph` and Phase 5's exit criterion is met — no core change requested, and every row of `02` §4's table true against the running binary · owner `01` → Phase 5 **Exit**; `02` §4 · turns on — · sha `bfce486` · **added 2026-08-22 by G13**. Phase 5 closed with its exit **not met** and the finding recorded; this is where it is discharged, after 6.18–6.20 and before 6.13, because Phase 6's own exit re-demonstrates every earlier phase's criterion against installed wheels and cannot re-demonstrate one that was never met

  **6.21 — Phase 5's exit criterion, discharged.** `01` → Phase 5 **Exit**: *"it is written by
  someone who has not touched the core, and they never need to."* Run against
  `examples/weft-example-graph` installed into a throwaway venv beside the first-party
  distributions, from a project directory outside this repository, with the one container.
  **Every row of `02` §4's table, against the running binary:**

  ```
  ROW 1+2  Enhancer stage and graph store, through the pack's own kg pipeline
  $ weft index docs --pipeline kg --yes
  produced 1, nothing to produce 0, failed 0. nodes now stored: 1.
  mode 'repair' — 2 participant(s):
    example-graph (weft-example-graph): examined 1, removed 10, backfilled 0
    pgvector (weft-store): examined 0, removed 0, backfilled 0
  graph nodes|entities: 1|4

  ROW 3    the pack's retriever, swapped into a first-party pipeline by ordinary derivation
  $ cat pipelines/graph-ask.yaml
  name: graph-ask
  extends: retrieve-then-generate
  replace:
    - id: retrieve
      use: example-graph-walk
  $ weft pipeline show graph-ask
    retrieve: Retriever:example-graph-walk (distribution: weft-example-graph, provenance: graph-ask)
    fuse:     Fuser:single-list (distribution: weft-retrieve, provenance: retrieve-then-generate)

  ROW 4    the pack's commands, in --help and rendered for a person
  $ weft --help | grep example-graph
      example-graph  'example-graph' subcommands
  $ weft example-graph show
  1 node(s) carry graph data: 4 distinct entities, 6 distinct relations.

  ROW 5    the shipped pipeline and the slot contribution
  $ weft pipeline list
  kg
  no-retrieval
  retrieve-then-generate
  route

  G7 ROW 1  weft delete fans out to it in-command
  $ weft delete .../docs/a.txt --yes
  '.../docs/a.txt' — 2 participant(s):
    example-graph (weft-example-graph): 1 node(s) removed
    pgvector (weft-store): 1 node(s) removed
  graph nodes after delete: 0

  G7 ROW 2  repair drops orphans; full backfills
  (corpus loses the node, graph keeps it — a participant that raised part-way through)
  $ weft reconcile --mode repair --yes
    example-graph (weft-example-graph): examined 1, removed 11, backfilled 0
  graph nodes after: 0
  ```

  `full`'s half of the last row is 6.19's own evidence entry. **No core change was requested to
  make the pack work**, which is the criterion: everything above runs against the code as
  shipped, and the pack's author touched no file under `packages/`.

  **The remaining half of G7's second row was built here.** 6.19 deliberately left *"repair drops
  orphans"* for this task rather than widening `repair` inside a task G13 had not settled it for;
  `repair` now requires the corpus for the same reason `full` does, and refuses without it —
  doing the half it can and silently skipping orphan detection is `01` rule 5's silent
  degradation, and the operator would read "converged" while still holding orphans.

  **Two defects found by running the binary, neither by any test.** First, the orphan rule was
  written on `NodeStore.list_sources()`, the method `02` §1 names for exactly this — and the
  automatic post-index `repair` pass then **deleted every graph node `kg` had just written**,
  because nothing on the ingest path calls `put_source` and `list_sources()` returns `()` in a
  real run. The pack's own tests had passed, on a double that populated the method the system
  does not. Repaired by deriving the live source set from `scan`'s own nodes and their lineage;
  `02` §1 corrected in place; ledger task **6.24** owns the underlying gap, and **6.8 depends on
  it** — a resumable delete needs a persisted `SourceStatus.DELETING` and nothing persists a
  `SourceRecord` at all. `docs/lessons.md` L6.14. The test was then rewritten to hand the double
  *no* source records, so it reproduces the real condition rather than the convenient one.

  Second, while checking row 3 an ordinary three-line pipeline naming only a retriever printed
  `'command:ask' failed: ` — a trailing space and nothing else, exit 1. `weft_cli.route_ask:275`
  is `assert isinstance(answer, Answer)`, commented *"every shipped routable pipeline ends in a
  Generator"*: an invariant over what this repository ships, checked against documents anyone may
  write, failing with no message and stripped entirely under `-O`. Ledger task **6.25**,
  `docs/lessons.md` L6.15. Not a Phase 5 exit failure — the pack works; this is the CLI
  diagnosing a malformed *user* document badly — but it is `01` rule 5 broken in the open.

- [x] **6.22** fitness function 9(b) decides "does anything under `packages/` name this pack" **structurally** — imports, entry-point declarations and the string literals passed to registration calls, read from the AST — **in addition to**, never instead of, the text scan it already runs; and its self-test plants a real reference rather than a matching word · owner `01` → *Fitness functions* 9; `05` → `lessons.md` L5.23, L5.28 · turns on — · sha `fb4f5ef` · **added 2026-08-22 while answering the archive's own question at the L6.1/L6.2 drain.** `tests/architecture/test_ff9_extension_from_outside.py:426` is still `if name in text`, and L5.28's row says so in as many words — *"the AST repair is still owed"*. The generalisation was routed to `phase-step` → *Orient* at the Phase 5 drain and the mechanical half was never given an owner, which is `implement-ll`'s own second trap: fixing the instance and calling the lesson applied leaves the class open. The defect it already caused is on the record — the check false-positived on ordinary English prose during task 5.4. **Corrected 2026-08-22 during task 6.20, before anyone implemented this line as first written** (`docs/lessons.md` L6.13): the original wording said *"never as a substring of file text"*, and a purely structural check would have missed the violation FF9(b) actually caught that day — two ordinary docstring sentences in `weft_cli/render.py` naming the example pack, which are neither imports nor entry points nor registration literals, and are real violations because a first-party file naming the out-of-tree pack makes the pack part of what it is meant to be independent of. The check has a false-positive mode *and* a false-negative mode; this task owns both
  **6.22 — the AST half `L5.28` recorded as owed, added beside the text scan and not instead of
  it.** `structurally_naming` reads three sources off the AST: an import of the pack's module, a
  string literal passed to a registration call (`add`, `add_renderer`, `add_ext_model`,
  `add_pipeline_resource`, `add_contribution`), and a dotted prefix of either. Planted in the real
  tree and watched: a `registrar.add(Command, "example-graph", ...)` in `weft_cli.commands` is
  named by file and by literal.

  **Both directions of the unsoundness, which is what `L6.13` asks a repair to cover.** The text
  scan **over**-fires on a name discussed rather than used — `02` §4 quotes `weft-graph` as a
  hypothetical throughout, and a real pack taking that name would turn every legitimate quotation
  into a violation, which is why `examples/weft-example-graph` is not called `weft-graph`. It
  **under**-fires on a reference the text never spells the same way. The self-test is built on
  exactly that pair, per this task's own line: a file that *imports and registers* is caught
  structurally, a file that only mentions the name in a docstring is not — **and the substring
  scan still catches the second**, asserted in the same test, so neither check can quietly replace
  the other.

- [x] **6.23** every test suite in the tree is reachable from `ci-checks`: `examples/*/tests/` — six packs' worth, `weft-example-graph`'s twelve included — runs in the gate, and a test whose subject is the one shared container scopes its assertion to what it wrote rather than to the whole table · owner `01` → *Fitness functions* 0; `05` → `lessons.md` L6.12 · turns on — · sha `779d09d` · **added 2026-08-22 during task 6.19**, which needed its pack-side evidence to actually run and found that nothing runs it. `pyproject.toml:142` is `testpaths = ["tests"]`; FF9 installs an example pack and checks the repository does not name it, never that its suite passes. Two of `weft-example-graph`'s tests were red on discovery, on seventeen rows of accumulated residue in `exgraph_nodes`, and went green on `TRUNCATE` — so the wiring and the isolation are one task, because wiring an unisolated suite into the gate only moves the flake
  **6.23 — 116 tests the gate had never run.** `testpaths = ["tests"]` meant seven out-of-tree
  example packs' own suites were invisible to `poe ci-checks`, which is `docs/lessons.md` **L6.12**
  — a directory of tests no task runs is prose, exactly as a documented check no task runs is
  prose, one level up from the check to the suite. All 116 run now, in half a second.

  **A task of its own rather than a widened `testpaths`, for two measured reasons.** An example
  pack is deliberately not a workspace member (FF9(a)), so nothing installs it and its `src/` must
  reach `sys.path` explicitly — the gap `[tool.pyright] extraPaths` already closes for type
  checking. And several packs name a test file the same thing (`test_store.py`,
  `test_retriever.py`, `test_enhancer.py`), which pytest's default import mode refuses outright:
  `--import-mode=importlib` accepts it without renaming 28 files that belong to strangers.

  **FF0 could not have seen the new step, and that is this function's own subject aimed at
  itself.** `_covered_roots` read the `test` task alone — true while the gate had one pytest step,
  and a hole the moment it had two: `examples-tests` really would have covered
  `examples/*/tests`, this function would not have known, and the seven entries would have stayed
  in `SUITES_WAIVED_FROM_GATE` while the suites were already running. It reads **every pytest step
  of the composite** now, both `cmd`-string and table task shapes. `SUITES_WAIVED_FROM_GATE` is
  empty.

  **The container half was already satisfied and was checked rather than assumed.** The task line
  asks that a test whose subject is the one shared container scope its assertion to what it wrote.
  `examples/weft-example-graph`'s suite does reach real Postgres, so 17 rows of foreign residue
  were planted in `exgraph_nodes` (20 total) and all 116 tests still passed — the scoping landed at
  task 6.19, and this is the evidence rather than the memory.

  **Four test docstrings said "Not collected by `weft`'s own `pytest`", and that is now false** —
  corrected in the same commit rather than left to rot, which is `L6.19`'s shape: a change that
  falsifies prose owns the prose.

- [x] **6.24** the ingest path records a `SourceRecord` for every source it indexes, so `NodeStore.list_sources()` answers the question `02` §1 says it answers · owner `02` §1; `05` → `lessons.md` L6.14 · turns on — · sha `2364ac2` · **added 2026-08-22 during task 6.21**, found by running the binary. `grep -rn "put_source" packages/` has exactly one caller and it is inside `weft_qdrant.store` itself, so `weft_sources` is empty after a real `weft index` and `list_sources()` returns `()`. `02` §1's *"`list_sources`/`scan`/`count` already answer what should exist"* is true of the contract and false of the running system, and a design that leaned on it deleted data. **Task 6.8 depends on this**: a resumable delete needs `SourceStatus.DELETING` to be persisted somewhere, and nothing persists a `SourceRecord` at all. Correct `02` §1 in the same commit

  **6.24 — the writer `list_sources()` never had.** `weft_cli.ingest._record_sources`, called
  after `runner.run` returns without raising: one `SourceRecord` per `SourceDoc`, written through
  `put_source` on the instance of the stage `_store_stage_id_of` already identified — the store
  this run actually wrote nodes into, whether it came from `[services] store` or from a named
  pipeline document. `content_hash` is `sha256` over the document's **own bytes**, because `02` §1's
  purpose for the field is change detection and a hash of anything else cannot serve it. A failure
  from `put_source` propagates: a source that was indexed and not recorded is the exact state this
  task exists to end.

  **`BUILT_IN_PIPELINE_NAME = "built-in"`, and it is a real decision rather than a placeholder.**
  The default four-stage path resolves no `ResolvedPipeline` at all (`06` step 9's hardcoded
  pipeline, and `IndexResult`'s own docstring says so), so there is no name to read. `02` §1 wants
  this field to let `weft index` say *"already indexed, by a different pipeline"*, and a field
  meaning *which pipeline* cannot be empty on the path most corpora are indexed by.

  **The check is an integration test against the real store, deliberately.** A double is what hid
  this for a whole phase — `tests/` populated the method the running system did not, so every
  assertion built on it was true about the double and false about Weft (`docs/lessons.md` L6.14).

  **Run through the shipped binary, from outside the repository, against a clean container:**

  ```
  $ weft index . --yes
  produced 1, nothing to produce 0, failed 0. nodes now stored: 2.
  $ psql -c 'select uri, pipeline from weft_sources'
   file:///…/d624/fox.txt   | built-in
   file:///…/d624/notes.md  | built-in
  ```

  Repeated with a corpus already in the store, to check the write is not conditional on an empty
  table: three files indexed across two runs, three sources, three nodes.

  **One observation, and the explanation arrived afterwards.** An earlier run of the same binary
  stored its nodes and left `weft_sources` empty, and did not reproduce under two later attempts.
  The first guess written here was a stale `.venv` copy; **that was wrong**, and the dispatched
  implementer's own report supplied the real cause: it had run `git stash` / `git stash pop` on
  this checkout to test whether a failing test was pre-existing. During that window
  `weft_cli/ingest.py` was the unmodified file — no `_record_sources` — and the binary run that
  landed inside it did exactly what the defect this task repairs does. The same window explains
  the three unrelated tests that went red in a gate run and never again. Both are recorded rather
  than tidied away, because the guess and the correction are the evidence: `docs/lessons.md`
  **L6.26**, a leaf agent running a destructive git operation on a checkout somebody else is
  editing.
- [x] **6.25** a query pipeline that does not end in a `Generator` is refused by name, not by a bare assertion: `weft_cli.route_ask:275`'s `assert isinstance(answer, Answer)` becomes a refusal naming the pipeline, the stage it ended on, and what a query pipeline must end with · owner `03` → *Command surface*; `01` rule 5; `05` → `lessons.md` L6.15 · turns on — · sha `201f760` · **added 2026-08-22 during task 6.21**, found by running the binary. A three-line user-authored pipeline naming only a retriever prints `'command:ask' failed: ` — a trailing space and nothing else, exit 1 — and under `-O` the stripped assertion returns a non-`Answer` silently instead. The comment on that line reads *"every shipped routable pipeline ends in a Generator"*, which is `L5.32`'s shape: an invariant stated over what this repository ships, checked against documents anyone may write
  **6.25 — three sites, not the one the task line named.** `grep "assert isinstance" packages/*/src`
  returns `route_ask.py:181`, `:208` and `:275`; the ledger named the third. Repairing only that
  one is `docs/lessons.md` **L6.13** exactly — *a repair specified from one failing instance
  narrows to that instance* — so all three go through one seam, `_require`, which is also `L5.10`:
  repair at the place that serves every caller, never at the raise site it was noticed from.

  **The comment on two of them was the defect.** `# every shipped routable pipeline ends in a
  Generator` — an "every X" stated over what *this repository ships*, checked against pipeline
  documents **anyone may write**. `L6.15`: an invariant's scope is the inputs that actually reach
  it, not the ones its comment names. **And `python -O` strips `assert` outright**, so on an
  optimised interpreter the wrong object flowed onward with no check at all — a refusal that
  vanishes under a flag.

  **`_require` returns the value narrowed rather than asserting and returning nothing**, because
  `assert isinstance` narrows for a type checker and a plain call does not: a seam returning `None`
  traded three asserts for sixteen `reportUnknownMemberType` errors. Returning the narrowed value
  keeps the static guarantee the asserts carried and makes the runtime one survive `-O`.

  **Reproduced through the binary — the same three-line pipeline that found it:**

  ```
  $ weft ask "fox" --pipeline retrieval-only
  pipeline 'retrieval-only' finished and produced Candidates, but `weft ask` needs Answer. A
  pipeline's last stage decides the shape of its result [...] Add a generating stage, or run this
  pipeline with `--retrieve-only`, which asks for the shape it actually produces.
  exit code: 1
  $ weft --json ask "fox" --pipeline retrieval-only
  {"kind":"error-envelope",...,"error":"PipelineProducedTheWrongShapeError",...}
  ```

  It names the pipeline, what it produced, what was needed and **both** remedies; the JSON envelope
  carries the failure identity and task 6.16's discriminant. `manual/troubleshooting.md` gained its
  entry, which `08` §3 clause (d)'s ratchet demanded before the gate would pass.

- [x] **6.26** the example packs declare the dependency shape G9 settled, so the exemplars a third-party author copies do not teach the unbounded requirement fitness function 10(b) exists to abolish · owner `01` → *Fitness functions* 10(b); `05` → G9; `07` §1 · turns on — · sha `edf753f` · **added 2026-08-25 while building 6.3**, measured rather than guessed: `weft-example-chunker`, `-command`, `-ingest`, `-llm`, `-metric` and `-query` declare 18 bare sibling requirements between them; `weft-example-graph`, written after G9, declares bounds on all five of its. FF10(b) does not reach them — `01` scopes it to the workspace and an example pack is deliberately not a member (FF9(a)) — so this is a separate repair, and the question it has to answer first is whether a never-published pack owes a bound at all or whether what is owed is only that the *documented* example not teach a bare name
  **6.26 — the exemplars were teaching the rule they exist to demonstrate, backwards.** Eighteen
  bare requirements across six of the seven example packs — `"weft-kernel"`, no bound — which is
  exactly what G9 settled against (*"a version requirement **is** the dependency specifier, so
  `0.0.0` ends, bare names end"*) and exactly what FF10(b) abolished inside the workspace. Only
  `weft-example-graph`, written after G9 landed, carried bounds. An example pack is what the next
  pack author copies, so this was teaching that bounds are optional.

  **A separate check, not a widening of FF10(b).** `01` scopes that clause to *"a property over the
  workspace"*, and an example pack is deliberately **not** a workspace member — that is FF9(a),
  the whole point of the arrangement. Widening a settled clause to reach something it was written
  to exclude is the proviso `L5.32` refuses. So the reason is different too: not *"the release must
  be installable"* but *"the exemplar must teach the rule"*.

  **And `L6.31` fired on its own author, one task after being written.** That lesson says a brief
  editing a file should *look up* which guides quote it rather than remember —
  `manual/pack-author-guide.md` quotes `examples/weft-example-chunker/pyproject.toml` byte-for-byte
  and `tests/docs/test_pack_guide_samples.py` holds them identical. The gate caught it, the sample
  was resynced from the live file, and the chunker's own comment now states the rule for the five
  packs whose comments cite it.

- [x] **6.27** the extraction step the published baseline's quotes were taken from is pinned and checked, so a library bump is named rather than arriving as unexplained quote failures · owner `09` §4, V1/V3; `08` §3 · turns on — · sha `e1a046a` · **added and closed 2026-08-25**, found while running 6.7's `--run-tests` phase and reproduced by hand: `uv.lock` pins `pypdf` 6.16.1, a fresh resolve takes 6.16.2, `weft-pdf` declares `pypdf>=6.16` with no ceiling, and under 6.16.2 five quotes stop being literal spans of the documents they name
  **6.27 — the filed framing was wrong, and the file that owns the check said so.** This task was
  written as *"either `weft-pdf` bounds `pypdf` where the text is stable, or the quotes are
  re-taken and the check tolerates what the bound cannot fix"*. Both halves are refused by settled
  text, and reading it is what corrected them. `tests/docs/test_question_set.py`'s own docstring:
  *"It must be able to fail, and it is not made tolerant to avoid that... When a quote stops
  matching, that is the ground truth no longer describing what the pipeline reads — a fact worth a
  red gate, and one that normalised whitespace or a similarity ratio would quietly absorb."* And a
  ceiling in `weft-pdf` contradicts G9, which settled that a pack declares `>=X,<MAJOR+1` and never
  an exact pin, because what version an operator's deployment runs is theirs.

  **What was actually owed is the manifest's own argument, one step further.**
  `corpus/manifest.toml` pins the fetch *and* the render, and says why: *"Pinning only the second
  is how these nine entries were once pinned to bytes made by hand: every digest verified locally
  and not one of them could be reproduced by anybody else."* A quote is a span of **extracted
  text**, which is one step past the document bytes — so pinning only the bytes leaves the text the
  judgements are written against unpinned, and that sentence applies unchanged to the third step.
  `[extraction.pdf-text]` now records `pypdf 6.16.1`: a **record of which extractor produced these
  quotes**, not a ceiling on anybody's install.

  **The check names the event instead of describing its symptoms.** Before, a `pypdf` patch bump
  read as five unexplained quote failures; now it reads as:

  ```
  the extraction backend that produced this question set's quotes is not the one installed:
    pdf-text: quotes were taken with pypdf 6.16.99, 6.16.1 is installed
  ```

  — planted and watched. The remedy it names is the one this module already prescribes for a
  *backend* swap: re-take every affected quote from the new backend's output and move the pin in
  the same commit. A library bump is that same event arriving through a dependency instead of
  through a configuration edit, and the only real difference was that nobody chose it and nothing
  announced it.

  **This had to precede 6.9**, which asserts every shipped technique's improvement is a delta
  against the baseline *"on the same corpus, pipeline and model versions"*. An unpinned extractor
  means the corpus's own text is not the same text, and V1's failure condition — *"a fetch is not
  reproducible byte-for-byte"* — is about bytes that were, by then, one step upstream of the
  problem.

- [x] **6.28** no member of the canonical gate can go red because a third-party service answered differently: every test under `tests/integration` that reaches the network is behind the same explicit key-absent skip its siblings already use, or stops depending on what a live model returns · owner `01` → *Fitness functions* 0; `08` §3; `05` → `lessons.md` L6.27 · turns on — · sha `474576d` · **added 2026-08-25 from task 6.24's implementer report**, and measured rather than guessed: four files reach OpenAI — `test_openai_llm.py`, `test_openai_embedder.py`, `test_raptor_pipeline.py`, `test_hypothetical_questions_pipeline.py` — while four `pytest.skip` sites in that directory already gate on an API key, so the discipline exists and does not cover all four. The failure seen was `vector search must find something in a store that was just populated: assert []`, green on two immediate reruns with no code change. **The damage is not the red run**: it teaches whoever runs `ci-checks` to re-run until green, which is the habit that lets a real regression through, and it makes a dispatched agent's "green" unfalsifiable because a failure it did not cause is indistinguishable from one it did — this one cost three separate diagnostic detours in one session
  **6.28 — all four already gated on the credential, and that was not the property.** Every
  integration module reaching OpenAI skipped when `OPENAI_API_KEY` was unset, so a runner without
  one was deterministic — which is where the discipline had been checked, and where it holds. The
  machine it did **not** hold on is a developer's, with the key exported for other work: there the
  gate calls a live service and its green depends on what that service answered. That is how task
  6.24's implementer got `vector search must find something in a store that was just populated:
  assert []`, green on two immediate reruns with no code change.

  **So the opt-in is a second variable, separate from the credential.** `OPENAI_API_KEY` says *"I
  could reach the network"*; `WEFT_LIVE_API_TESTS` says *"I am asking to"*. Both required.
  `09` §4.3's **V5** is the requirement in as many words — *"a deterministic subset that runs in CI
  with no credentials and no network, so a regression is caught by the gate rather than by a
  quarterly ritual"* — and the damage of the alternative is not the red run: it teaches whoever
  runs `ci-checks` to re-run until green, which is the habit that lets a real regression through,
  and it makes a dispatched agent's green unfalsifiable.

  **Made opt-in, not disabled — checked both ways.** `WEFT_LIVE_API_TESTS=1 uv run pytest
  tests/integration` → **76 passed**, every live test running. `uv run poe ci-checks` → **1919
  passed, 9 skipped**, and 20 seconds faster. The check reads **imports**, not prose, so a module
  whose docstring names OpenAI is not mistaken for one calling it (`L5.23`), and its self-test is
  built on exactly that pair. `CONTRIBUTING.md` says how to run them.

- [x] **6.29** a plugin that cannot run says so at discovery, not at first use: `PackStatus.PARTIAL` gets the mechanism that produces it, so `weft plugins doctor` reports a plugin whose optional dependency is absent instead of a run failing later · owner `01` → *Fitness functions* 5; `02` §2 → *The trust model*; G4 · turns on — · sha `f75c95e` · **added 2026-08-25 at task 6.14**, which built FF5's first two clauses and could not build this one. `weft_kernel.discovery`'s own module docstring has deferred it since Phase 0 — *"`PARTIAL` is part of that vocabulary now because the vocabulary is one piece; the mechanism that produces it is G4's conditional registration, a later step's job"* — and no later step took it, so the status exists in the enum and **no pack has ever reported it**. The one real instance is `weft-eval`'s `bertscore`: it registers unconditionally and answers `Failed` at *run* time naming the missing extra, which is saying why one moment too late — an operator running `doctor` learns nothing and finds out when a run fails. Pinned as `PLUGINS_REPORTING_UNAVAILABILITY_TOO_LATE` in `tests/architecture/test_ff5_declared_capability_resolves.py`, one entry, with a test proving the entry names a live registration rather than a string somebody typed. This task empties it
  **6.29 — `PARTIAL` gets the mechanism it was given a name for in Phase 0.**
  `weft_kernel.discovery`'s own docstring deferred it — *"the mechanism that produces it is G4's
  conditional registration, a later step's job"* — and no later step took it, so the status sat in
  `02` §2's vocabulary for six phases with nothing able to report it.
  `PackRegistrar.unavailable(surface, reason=...)` is that mechanism, buffered exactly like
  `deprecate` and for the identical reason: a pack whose `register()` raises after calling it must
  not leave a report standing about a mark that never committed. A pack that declared any surface
  unavailable is `PARTIAL` — not `ACTIVE`, which claims it is contributing everything it has, and
  not `FAILED`, which claims it contributed nothing.

  **`weft-eval` is the real instance and it now says so at discovery:**

  ```
  weft-eval 1.0.0: partial (28 contributed)
    unavailable: 'bertscore' — needs the optional 'bert_score' package, which is not installed.
                 Install weft-eval's 'bertscore' extra to run this metric.
  ```

  Before this it registered unconditionally and answered `Failed` when the metric was *run* —
  saying why, one moment too late. It stays registered on purpose, so `weft eval` still refuses it
  by name with a reason rather than reporting it as an unknown metric.
  `PLUGINS_REPORTING_UNAVAILABILITY_TOO_LATE` is empty; **FF5 now holds all three of its clauses.**

  **Two checks caught things within a minute of the method landing, and both were right.**
  `docs/lessons.md` **L5.26**'s completeness test — a hand-rolled double must carry every public
  method of the class it doubles — named `_NameCapturingRegistrar` as missing `unavailable`. And
  task 6.4's own check failed: it asserted every pack the release set names is `ACTIVE`, and
  `weft-eval` is now `PARTIAL` on any install without the optional extra, **which is every clean
  install of the set**. Requiring the literal `ACTIVE` would forbid a first-party pack from having
  an optional extra at all, contradicting `weft-eval[bertscore]` and `weft-otel[otlp]`, both
  settled — so the check reads *loaded* (`ACTIVE` or `PARTIAL`), and says in place why the word in
  6.4's line was written when the distinction did not yet exist.

- [x] **6.30** the published baseline is re-taken from a release install, so a stranger's run is comparable to it at all · owner `09` §4, V3/V6; `01` → Phase 6 **Exit** · turns on — · sha `ef28202` · **added 2026-08-25 at task 6.13**, and measured rather than argued. A run driven by the release set installed from an index reproduces `eval/baselines/8854c33f71ea-2026-08-20.json` **exactly — all twelve metrics identical to the last decimal, every one inside the recorded interval** — and `eval/check_baseline.py` still refuses to certify it: `resolved_pipeline.stages[3].contract_version` is `1.2.0` in the baseline and `2.0.0` now (G9's per-contract correction landed after 2026-08-20), and the active distribution sets differ because the baseline was taken **in the development workspace** — it names `weft-canary` and `weft-pdf`, which no release install has, and lacks `weft-store`, which the set pins. The refusal is correct and is V3's own failure clause working: *"a baseline from a different corpus, pipeline or model version"*. **Taking the matching numbers as a pass would be the near-miss comparison `check_baseline`'s own docstring calls the more dangerous outcome**, because nothing about the number would look wrong. The re-take must be driven the way this task drove it — through the shipped command, from a release install — or the next stranger meets the same refusal
  **6.30 — the baseline is now taken the way a stranger would reproduce it.**
  `eval/baselines/8854c33f71ea-2026-08-25.json`: driven through the shipped `weft` command from a
  release install — `weft-rag` plus `weft-qdrant` and `weft-openai` beside it, all from a local
  index into a throwaway venv — 9 documents, 3 repetitions, 78.0s. Its `active_distributions` is
  13 and holds no `weft-canary` and no `weft-pdf`, because a release install has neither; its
  store `contract_version` is `2.0.0`, because that is what the release ships.

  **Then run again and checked, which is the whole point.** A second, independent run through the
  same install: `12 metric(s) inside the interval 3 repetitions of the baseline spanned`. The
  2026-08-20 baseline is kept beside it rather than deleted — it is the record of what the
  workspace measured before G9's contract correction, and deleting it would erase the evidence for
  why this one exists.

- [x] **6.31** every first-party distribution that reaches the network declares a `Disclosure`, so the control the release page advertises is not empty where it matters most · owner `02` §2 → *The trust model*; `09` §5 · turns on — · sha `33534ca` · **added 2026-08-25 by the whole-phase `weft-qualities` reading at Phase 6's close**, and measured: **one of twenty first-party packs declares a `DISCLOSURE`, and it is `weft-otel`, whose exporter defaults to `none`.** `weft-openai` (a credentialed provider) and `weft-qdrant` (a network client) both report `disclosure: not disclosed`. Task 6.10 published a page that tells a reader *"`weft plugins doctor` names ... what each one **discloses** about the network, filesystem and subprocess access it uses"* — true of the mechanism and close to empty in practice, which is requirement 4 read the uncomfortable way: built-ins are exempt from the discipline the page recommends to everyone. **The seam exists**: `DISCLOSURE` is read at import by `weft_kernel.discovery` before `register()` runs, and `tests/architecture/test_the_gate_is_decidable.py` already has the import matcher that says which modules reach a client — a check over the publish set costs almost nothing and attaches where the fact already is
  **6.31 — and the sweep found a third one the review had missed.** `weft-openai` and `weft-qdrant`
  were the two named at the close; deriving the set from imports rather than from that list added
  **`weft-store`**, which opens a `psycopg` socket whether or not the database is on the same
  machine. `docs/lessons.md` L5.14 in miniature: the review's list was where to start looking.

  **Each disclosure names the *setting*, never a guessed host**, because that is what an operator
  can actually check — `[packs.weft-openai] base_url` / `OPENAI_BASE_URL`,
  `[packs.weft-qdrant] url`, `[packs.weft-store] dsn` — and `02` §2's own rule is why they are
  concrete strings rather than booleans: *"a hostname is information, `network: true` is noise."*
  No credential value is printed; `api_key` and `dsn` are `SecretStr` and the disclosure names the
  setting.

  ```
  weft-openai 0.1.0: active (2 contributed)
    disclosure: network=['api.openai.com, or whatever [packs.weft-openai] base_url /
    OPENAI_BASE_URL names'], ... note='Sends prompts and text to be embedded to an
    OpenAI-compatible API [...] Every completion and every embedding leaves this process.'
  ```

  **`weft-store`'s lives in `weft_store/__init__.py`, not in `pgvector_store`** — the kernel reads
  `DISCLOSURE` off the module a pack's *entry point* names, and that is `weft_store:register`.

  **The check derives who owes one and refuses to judge whether it is true.** `02` §2 is explicit
  that a disclosure is "a disclosure to the operator, never a claim weft checks", so verifying one
  would simulate the control the section refuses to simulate. What is checkable is that a pack
  reaching outward has said *something*, and `NETWORK_PACKS_WITHOUT_A_DISCLOSURE` is pinned empty
  with its own `test_the_waiver_is_empty`: a first-party exemption here would be requirement 4's
  failure written down. Planted and watched — `weft-openai`'s `DISCLOSURE` renamed, and the check
  names it by distribution and by the client it imports.

- [x] **6.32** a pipeline refused for producing the wrong shape names which pipelines would produce the right one · owner `01` → requirement 5; `03` → *Output* · turns on — · sha `4872678` · **added 2026-08-25 by the same reading.** `PipelineProducedTheWrongShapeError` (task 6.25) names the pipeline, both shapes and two remedies, and not the valid options. Fitness function 12 does not require it — this is not an unresolvable *name*, and the gate is right to pass — but requirement 5's third clause is *"what the valid options are"*, and `weft_cli.route_ask` holds the catalogue at the raise site, so the answer is one argument away. Small, and filed rather than folded into 6.25's commit because the phase was closed by then
  **6.32 — and the first draft printed an empty list, which is the lesson.** `pipelines_producing`
  walks the catalogue and asks the **registry** which contract each pipeline's last stage is
  registered under, because a document names a plugin and nothing in it says what contract that
  plugin answers for (G1 keeps the kernel from naming a capability). Computed on the failure path
  only.

  The first version asked for **`Answer`** — a *payload* type, which nothing is registered under —
  got `()` back, and printed the refusal with its "valid options" half silently missing. An empty
  answer read as *"there are none"* when it meant *"I asked the wrong question"*
  (`docs/lessons.md` L5.9), and **only running the binary showed it**: every test passed, because
  none of them asserted the list was non-empty. The contract is `Generator`; the test now asserts
  against the real registry that the answer is non-empty and that `route` — which ends in a
  `RoutingPolicy` — is *not* offered, since a list that offered everything would send the reader
  straight back to the same refusal.

  ```
  $ weft ask "fox" --pipeline retrieval-only
  pipeline 'retrieval-only' finished and produced Candidates, but `weft ask` needs Answer. [...]
  Pipelines that already end in Answer: 'no-retrieval', 'retrieve-then-generate'.
  ```

- [x] **6.33** fitness function 8's canary assertion does not depend on which directory `pytest` visits first · owner `01` → *Fitness functions* 8; `05` → `lessons.md` L5.21 · turns on — · sha `ad356e5` · **added 2026-08-25 at Phase 6's close**, found by running `pytest tests/docs tests/architecture` — a combination the gate never runs. `test_ff8_trust_model.py` asserts `weft_canary not in sys.modules`, and **five files under `tests/docs` import it first**: `test_changelog_deprecation_coverage.py`, `test_corpus_manifest.py`, `test_generated_docs.py`, `test_question_set.py` and `test_technique_naming.py`, each through `weft_cli.contract_reference.discover_for_reference()`, which discovers **open** and therefore imports every installed pack. The gate is green **only because `tests/architecture` sorts before `tests/docs`**, and FF8's own guard is what makes this visible rather than silent — its message is *"Something else in this test session imported the canary first; find it and stop it from doing so."* Same family as task 6.17 and as task 6.14's first draft, which made the identical mistake and was caught the same way. **The fix is a seam choice and is deliberately not being made at a phase boundary** (`docs/lessons.md` L5.10 says repair where every caller is served, and the candidates — an `allow` on `discover_for_reference`, a shared test fixture, or excluding a never-published distribution from a reference generator — trade off differently against `02` §2's "refused by an allow-list, never by name")
  **6.33 — the first reading of this was wrong, and finding that out is what fixed it.** The close
  filed it as *"four `tests/docs` modules import the canary through `discover_for_reference()`;
  stop them"*. Pointing those four at a restricted helper did **not** fix it, because
  `tests/unit/weft_cli/test_contract_reference.py` calls the open function five times and
  **cannot stop** — testing that function is what those tests are for. So there is no set of
  callers to discipline: any session that tests open discovery imports the canary, and FF8's
  in-process guard was never going to survive that.

  **The mechanism was the defect, and FF8's own docstring already argued the fix.**
  `test_a_pack_refused_by_the_allow_list_is_never_imported` now runs its probe in a **fresh
  interpreter**, which starts with an empty `sys.modules` whatever ran before it — exactly what the
  canary was built for: *"the same canary works for an in-process discovery test and for a CLI
  invocation."* Its sibling was already a subprocess and was carrying the same in-process guard for
  no reason; that half is gone, and `_assert_canary_installed` keeps the half that is a fact about
  the environment rather than about this pytest session.

  **Verified in all three orderings and against the real defect.** `pytest tests/docs
  tests/architecture` — the combination that failed — 309 passed; the reverse order, 309 passed;
  and alongside the contract-reference tests that cannot avoid open discovery, 17 passed. Then
  planted: `entry_point.load()` before the refusal branch in `weft_kernel.discovery`, which is
  precisely the defect FF8(a) exists for, and it fails naming it — *"an allow-list that excludes
  it must stop discovery before the import happens, not merely before register() is called"*.

  **`tests/discovery.py` stays**, because the four docs modules are better off restricted anyway —
  an allow-list there is what a test session means by *"the packs I mean to load"*, and it is
  derived from what is installed rather than listed, so a pack added tomorrow needs no edit. What
  it is **not** is the fix; `02` §2 settles that a pack is refused by an allow-list and never by
  name, so putting `"weft-canary"` in `weft-cli` would have broken that rule in the one
  distribution that must not.

- [x] **6.34** `weft_store/rehydrate.py` says what its two registration paths actually do · owner `02` §1; `05` → `lessons.md` L6.28 · turns on — · sha `b388a86` · **added 2026-08-25 at Phase 6's lessons drain**, and it is the *finding* half of L6.28 rather than the rule. That module's docstring says `register_ext_model` and `register_from_reports` give "the identical idempotent-or-refuse behaviour either way" and names the caller it is wrong about — "a test, or a caller that builds a registry without running full discovery". Measured: `register_ext_model` calls `ext_models.add` and refuses a second call **even for the same class**, while `register_from_reports` goes through `_register_if_new` and skips it. Two callers hit this in one phase (tasks 6.8 and 6.17), each passing alone and failing in the full suite. One clause to correct, and the honest version is shorter than the wrong one; a test asserting the difference is what would keep it true
  **6.34 — the clause is corrected, and the correction is now load-bearing rather than prose.**
  `rehydrate.py` said the two paths give *"the identical idempotent-or-refuse behaviour either
  way"* and named the caller it was wrong about. They differ: `register_from_reports` goes through
  `_register_if_new` and **skips** a namespace the same class already claimed;
  `register_ext_model` calls `ext_models.add` and **refuses** unconditionally, even for a
  re-registration of that same class. The docstring now says which path a caller outside full
  discovery wants, and why — the wrong one works alone and raises the moment anything earlier in
  the process registered first, which is exactly how tasks 6.8 and 6.17 each met it.

  **Two tests, because the missing test is what let the sentence stand.** One asserts
  `register_from_reports` called twice with the same class raises nothing and leaves the namespace
  resolving to that class; the other asserts `register_ext_model` raises
  `DuplicateRegistrationError` for the same second call. They use a namespace of their own, so
  neither disturbs another test through the process-global registry — which is the same shared
  mutable state underneath tasks 6.8, 6.17 and 6.33.

- [x] **6.35** the published baseline, question set and corpus manifest are reachable by somebody who has the release · owner `09` §5.2; `05` → `lessons.md` L6.34 · turns on — · sha `9b5efbd` · **added 2026-08-25 at Phase 6's lessons drain**, and it is the finding half of L6.34. `09` §5.2 says "the baseline run is published with the release" and V6 requires it to be a persisted run rather than terminal output — it is, in `eval/baselines/`, with `eval/questions/` beside it and `corpus/manifest.toml`. **None of the three is inside any distribution.** Task 6.13 installed the whole product from an index into a clean environment and everything needed to *reproduce* the number was still only in the repository. The shipped CLI can do the work — `weft eval run` and `weft eval compare` are both on the installed binary — so the gap is reachability, not capability. Three candidate answers and the choice is `09` §5.2's: ship them inside a distribution, attach them to a release, or fetch them by a pinned script the release names (`scripts/fetch_corpus.py` already is that answer for the corpus *bytes*, so the question is narrower than it looks). `09` §5.2's own sentence takes the correction either way
  **6.35 — "with the release" had to be made to mean something.** Three answers were available and
  `09` §5.2's own words pick one. *Inside a distribution* would put this corpus's judgements into
  `weft-eval`, which publishes the metric contracts and is installed by people with no interest in
  Weft's corpus. *Fetched by a pinned script* is already the answer for the corpus **bytes**
  (`scripts/fetch_corpus.py`) and cannot be the answer for the **pins**, since the manifest is what
  the fetch reads — circular. *Attached to the release* is the literal reading of "published
  **with**", costs no architectural change, and puts the artefacts where somebody holding a release
  looks.

  A `publish-reproduction-artefacts` job archives `eval/baselines/`, `eval/questions/` and
  `corpus/manifest.toml` and uploads them to the tag's release. `needs: publish-release-set`, so
  they land only once the wheels they describe are on the index — a release carrying a baseline for
  distributions that failed to publish would be worse than one carrying none.

  **The check is the reachability half and says so.** Whether the baseline reproduces is
  `eval/check_baseline.py`'s question and task 6.30's; whether every quote is a literal span is
  `test_question_set.py`'s. This asserts the three artefacts exist *and* that the release job names
  each — two sides, since a job attaching paths that are not there would pass a check that only
  read the workflow. Its self-test states its own limit: it asks whether the path is named, not
  whether the upload is correct, and pretending otherwise would be a check claiming more than it
  does. `09` §5.2's line carries the correction and a new failure clause — *fails if reproducing
  the published number requires cloning*.

- [x] **6.13 ⚠** a machine that has never seen this repository installs the release set — the meta-distribution G10 settled on (`09` §1), named `weft-rag` since this task found `weft` taken on PyPI — from the index, and reproduces the published baseline — every metric inside the interval that baseline recorded across its own repetitions · owner `01` → Phase 6 **Exit**; `09` §4 · turns on — · sha — · turns on — · sha `ef28202`
  **6.13 — closed 2026-08-25, both halves, and it found three things on the way.** The install half:
  a local PEP 503 index, all eighteen distributions published to it, and `uv pip install weft-rag`
  into a throwaway Python 3.12 venv with no path back to this repository — sixteen distributions at
  their declared versions, then `weft --version`, `plugins doctor`, `index` and `ask` all driven
  from it, plus a named failure path, with `weft_cli` resolving from the venv. The baseline half:
  the published baseline **re-taken from that install** at task **6.30**, then an independent run
  checked against it — `12 metric(s) inside the interval 3 repetitions of the baseline spanned`.

  **What it found, none of which any check in this repository could have.** (1) `weft` is taken on
  PyPI at the very version this set declared, so the release set is `weft-rag`
  (`docs/lessons.md` **L6.33**, and G10's row carries the correction). (2) The 2026-08-20 baseline
  was taken in the development workspace and before G9's contract-version correction, so nothing
  installed from a release could ever have been certified against it — the numbers matched to the
  last decimal and `check_baseline` refused anyway, correctly, which is task **6.30**. (3) The
  baseline, question set and corpus manifest ship in no distribution
  (`docs/lessons.md` **L6.34**), so reproducing the number still needs the repository — filed
  against `09` §5.2's own *"published with the release"*.

  **What is still owed, and it is not this task's:** the actual `uv publish` to a real index. The
  workflow exists (`6.2`), the artefacts build and carry their licences (`6.7`, `6.11`), the names
  are checked, and the whole path is proved against a local index. Claiming a name on a public
  index is the project owner's to run, not a task's to do.
  **6.13 — what was proved, and the one thing that stops it.** A local PEP 503 index was stood up
  on `127.0.0.1`, all twenty distributions published to it, and the product installed into a
  throwaway virtualenv on Python 3.12 with no path back to this repository. **That half works, end
  to end:**

  ```
  $ uv pip install --index-url http://127.0.0.1:PORT/simple/ 'weft-cli==0.1.0'   # 33 packages
  $ weft --version
  weft 0.1.0
  $ weft plugins doctor | head -1
  weft-chunk 1.0.0: active (1 contributed)
  $ weft index corpus --yes
  produced 1, nothing to produce 0, failed 0. nodes now stored: 2.
  $ weft ask "what does the weft do" --retrieve-only
  1. A loom holds the warp fixed while the weft runs through it.
  $ weft ask "x" --pipeline nope
  'nope' is not a pipeline this project knows [...] Known pipelines: no-retrieval, ...
  ```

  `weft_cli` resolved from the throwaway venv, not the workspace, and the failure path is named.

  **⛔ `weft` is taken on PyPI, at the version this release set declares.** The install of the
  release set itself came back `+ weft==0.9.97` — *"The durable task substrate for agent systems"*,
  99 releases, and its release list **includes `0.1.0`**. Measured across all twenty names:
  **nineteen are free and the twentieth is the one a newcomer types.** `uv add weft` today gets a
  different project; `uv add 'weft==0.1.0'` can too. G10 settled the set on `weft`, `09` §1 names
  it throughout, `manual/quickstart.md` and `packages/weft/README.md` both print
  `uvx --from weft weft --help`, and nothing ever checked the namespace. `docs/lessons.md`
  **L6.33** — every check this repository has is a check about the repository, and a name is the
  first property that lives somewhere else.

  **This is a decision, not a defect to patch.** Renaming the release set reopens what G10 settled
  and edits `09` §1, the quickstart, the release-set README and the publish workflow. Defaulting a
  name mid-task is exactly what the gates exist to prevent, so **6.13 stays open** and the naming
  goes back to its owner.

  **Re-run 2026-08-25 with the name settled, and the install half is now proved for the release set
  itself.** `weft-rag` is free on PyPI (checked before anything depended on it, which is `L6.33`'s
  own rule), the rename landed, and `uv pip install --index-url <local> weft-rag` pulled the whole
  exactly-pinned set — 16 distributions, every version as declared — into a throwaway Python 3.12
  venv with no path back to this repository:

  ```
  + weft-rag==0.1.0  + weft-cli==0.1.0  + weft-kernel==0.1.0  + weft-store==2.0.0  [...]
  $ weft --version                     → weft 0.1.0
  $ weft index corpus --yes            → produced 1, ... nodes now stored: 2.
  $ weft ask "..." --retrieve-only     → 1. A loom holds the warp fixed...
  $ weft plugins doctor | grep eval    → weft-eval 1.0.0: partial (28 contributed)
                                           unavailable: 'bertscore' — needs the optional ...
  ```

  **And the baseline half was run for real, which is how ledger task 6.30 was found.** The
  published baseline's own harness was driven with the *installed release* on `PATH` — `weft-qdrant`
  and `weft-openai` added beside the set, as `09` §1 says a pack outside it is added — 9 documents,
  107 nodes, 3 repetitions, 82.3s. **All twelve metrics came back identical to the last decimal and
  inside the recorded interval.** `eval/check_baseline.py` refused anyway, correctly: the store
  contract version moved from `1.2.0` to `2.0.0` after the baseline was taken, and the baseline's
  active distribution set is the *development workspace's*. Not ticked on matching numbers —
  that is precisely the near-miss `check_baseline` exists to refuse.

  **A second finding, filed rather than fixed: `docs/lessons.md` L6.34.** `09` §5.2 says "the
  baseline run is published with the release", and `eval/baselines/`, `eval/questions/` and
  `corpus/` are in **no distribution**. The installed product can do the work — `weft eval run` and
  `weft eval compare` are both on the shipped binary — but a stranger who has the release and not
  the repository cannot reproduce the published number. That is why the baseline half of this
  task's own line is not ticked either.

**Exit** (`01` → Phase 6): task 6.13, plus FF10 wired and green and each of Phases 0–5's exit criteria
re-demonstrated against installed wheels rather than the working tree — **which is why 6.21 is in this
phase and not optional**: Phase 5's criterion was never met, so there is nothing to re-demonstrate
until 6.18–6.20 land and 6.21 runs.

---

### Phase 6's close, 2026-08-25

**`weft-qualities` against the phase** — two findings, filed as **6.31** (one first-party pack in
twenty declares a `Disclosure`, and task 6.10's own published page advertises that control) and
**6.32** (the wrong-shape refusal names both shapes and not the valid options). Running the review
turned up a third, **6.33**: FF8's canary assertion is green only because `tests/architecture`
sorts before `tests/docs`.

**`reference-audit`.** Phase 6's **Lift is "nothing, and one scar recorded as a rule"** (`01` → Phase
6), so the forward pass is satisfied by construction, and the scar — *"a distribution is proven
installable by installing it, never by reading it"* — is task **6.6**, built and running in CI. The
originality half was run at **6.11** and is recorded there in full: 10 identical substantive lines
out of 17,241, every one a bare class declaration in the `LLMError` taxonomy that `04` §B assigns
as lift-the-design; **zero** identical string literals of 40 characters or more across 2,650 and
7,113; none of the three pre-flagged `04` §C contamination items present; and one near-match chased
to the end and shown not to be one.

**The Exit criterion, re-read against what exists rather than against the ticked boxes — and it is
not fully met.** `01` → Phase 6 **Exit** asks for four things:

| | asked | what exists |
|---|---|---|
| install | "on a machine that has never seen this repository, installing the release set **from the package index**" | **from a local index**, into a throwaway venv with no path back here (6.13). Nothing is on PyPI, and the one-line `uv publish` is deliberately the project owner's to run |
| one `uvx` invocation | "one `uvx` invocation of that unit indexes the validation corpus, answers its question set" | the install and the drive were separate commands, and the corpus, question set and baseline reached the run **from this repository** — they ship in no distribution (`lessons.md` **L6.34**) |
| reproduce | "`weft eval compare` against the published baseline reports every metric inside the interval" | **met in substance, by `eval/check_baseline.py` rather than by `weft eval compare`**: 12 of 12 inside the interval, against a baseline re-taken from a release install at **6.30** |
| the installed state | "fitness function 10 wired and green... every first-party pack `active`... nothing flagged `ambient`" | FF10 green and `weft-canary` absent from the publish matrix ✓; **nothing ambient** ✓ (measured, 0); **`weft-eval` reports `partial`**, not `active`, since task 6.29 gave `PARTIAL` its mechanism — read as *loaded* and argued in place at 6.29, because requiring the literal would forbid a first-party pack from having an optional extra at all |

**So Phase 6 closes with its exit met in substance and unmet in letter, said plainly rather than
ticked past** — which is the position Phase 5 was found in, and the reason this phase carried
`6.21`. What is owed is **one publish to a real index**, and nothing else.

**Re-checked 2026-08-26, after the five close-out tasks landed.** Two of them moved the table
above. **6.35** attaches `eval/baselines/`, `eval/questions/` and `corpus/manifest.toml` to the
release, so the *"published with the release"* row is no longer false about anything a stranger
holds — the artefacts reach them with the release rather than with a clone. **6.31** closes the
gap the whole-phase review found in the row above it: every distribution that reaches outside the
process now declares what it touches, so `doctor`'s disclosure column means what task 6.10's
published page says it means. The remaining letter-of-the-exit gaps are the two that need an
index: installing **from PyPI** rather than from a local one, and doing it in a single `uvx`
invocation.

### Consolidation — twenty published distributions become six (2026-09-05)

**G10 reopened and re-settled.** `docs/plan-one-distribution.md` held the plan, was rejected on
evidence the same day it was written, and was then corrected: the rejection rested on a fact that
had not been checked (bundling does **not** break task 6.31's disclosures — `_read_disclosure`
reads the entry point's own module, `discovery.py:948`, which is per-pack). What the experiment did
find is that `distribution` was doing two jobs — the thing PyPI installs, and the pack's identity
in every operator-facing surface. C0 below separates them; everything else follows it. The plan
file is deleted with this line, as it said it would be.

- [x] **C0** a pack has an identity separate from the distribution that ships it — the `weft.packs`
  entry-point name, carried on `PackReport.pack`, keying `[packs.<pack>]` settings, the rows
  `weft plugins list|doctor` prints, `require_active`, and the pack named in a settings or
  disclosure failure; `distribution` keeps `[packs] allow`, the version column and version skew ·
  owner `02` §2 → *Pack settings* · sha `f262d25` · **this reverses what G1 settled** and the
  argument G1 gave is what stopped being true: it keyed settings on the distribution because
  "entry-point aliases can collide between two packs; distribution names cannot", and under one
  wheel shipping twelve packs the distribution name is the one that collides · what G1's argument
  was *right* about is covered rather than dismissed — two distributions can both declare a pack
  named `graph`, weft does not refuse it (a stranger's entry-point name is not ours to rename), and
  `weft plugins doctor` names the collision in its own trailing block beside version skew and inert
  pins · `weft-cli`'s entry point renamed `weft-cli` → `cli`, the last first-party pack still named
  after its distribution · kernel cost 3,079 → 3,097 counted lines against a 3,500 budget, no new
  concept and no capability named
- [x] **C0b** `weft --version` derives the distribution that ships it rather than asserting one ·
  owner `03` · sha `121afe9` · filed rather than patched at the first experiment, on the grounds
  that the fix belonged with whoever separated pack identity from distribution · **the obvious
  mechanism is wrong**: `importlib.metadata.packages_distributions()` maps import packages by
  reading installed file records, and an editable install records only a `.pth`, so it answers
  `None` for `weft_cli` in this repository's own venv — measured, not read (`lessons.md` L7.6).
  Derived from the `console_scripts` entry point pointing at `weft_cli.cli` instead, which is what
  actually put `weft` on the reader's PATH. Neither degenerate state is guessed past
- [x] **C1** `weft-rag` ships the fourteen packs' code and their twelve entry points, and a wheel
  built from it imports every one of them · owner `09` §1 · sha `397d5c1` · **the fourteen
  `src/` trees moved under `packages/weft-rag/src/`, and that was forced**: leaving them in place
  and pointing `force-include` at `../weft-chunk/src/...` builds a working wheel and an sdist that
  cannot build a wheel from itself, so task 6.7 could never have held. The move changed no import
  and no test
- [x] **C2** the fourteen `pyproject.toml` files are gone, the workspace resolves, and the gate is
  green · owner `09` §1 · sha `397d5c1` · `weft-rag` is `2.1.0`, which `09` §2.3's binding
  rule forces and `09` §2.2 answers in advance — the binding, not the leading digit
- [x] **C3** `release.yml`'s matrix publishes six names and fitness function 10 still compares two
  sources that can genuinely disagree · owner `01` → FF10 · sha `397d5c1` · `max-parallel: 1`
  kept (`lessons.md` L7.3)
- [x] **C4** the release-set check holds the new shape · owner `09` §1 · sha `397d5c1` ·
  **the plan's own wording for this task was wrong** — it asked for "exact pins for the four
  optional packs and the kernel", and the four add-ons depend on `weft-rag` rather than the
  reverse, so pinning them would invert the graph and force every default install to carry
  `openai` and `qdrant-client`. What replaces the pins is the comparison the pins were a proxy
  for: the hand-written `[tool.hatch.build.targets.wheel] packages` list against the source tree
  beside it, which is now the one place a module can be silently absent from the built wheel
- [x] **C5** the isolated-install check covers the six, and the fourteen are covered by a stated,
  explicitly weaker import assertion · owner `09` §5.2 · sha `397d5c1` · the weakening is
  named in `scripts/check_isolated_installs.py` rather than counted as the same coverage: an
  undeclared dependency between two bundled packs can no longer break an install, because there is
  no longer a declaration between them to omit
- [x] **C6** `09` §1 and `README.md`'s G10 row carry the re-settled decision, and
  `docs/plan-one-distribution.md` is deleted · owner `docs/README.md` → *Protocol* · sha `397d5c1`

**Verified by running the binary, which is where this phase's own repairs came from.** Six wheels
and six sdists built; `weft-rag` installed from its wheel into a clean venv and driven from `/tmp`:
`weft --version`, `plugins list` (twelve distinguishable rows), `plugins doctor` (`weft_store`'s
disclosure intact — the control the first rejection believed bundling destroyed), `pipeline list`,
`weft --help`, and a real `weft index` + `weft ask --retrieve-only` against the `compose.yaml`
container. Four failure paths: a stale `[packs.weft-store]` key refused by name listing all twelve
valid packs (exit 4), an unknown pipeline (exit 4), an unknown command (exit 2), and
`[packs] allow = ["weft-rag"]` refusing `weft-pdf` and `weft-otel` before importing them.

**Nothing published and nothing tagged.** PyPI's limiter counts attempts over a rolling window
(`lessons.md` L7.3); the owner tags.

## Phase 7 — The agent

**Added 2026-08-18 by G8**, logged as scope decision `S3` (`09` §6.1 and §6.4). `01` → Phase 7 owns
the content: the agentic front end is a **first-party pack**, not the REPL, because `03`'s governing
rule keeps logic out of the driving adapter — and it lands after release so it is built against
published, versioned contracts rather than moving ones.

**⛔ Blocked by G12** — what a permission class means when the caller is never a TTY, Open. Until it
closes, `03` → *Permissions* stands unchanged: an `ask`-class operation fails without a TTY, an agent
is never a TTY, so nothing here may `overwrite` or `destroy` on its own. **This is also where the
`agentic-patterns` handoff lands** (`01` → Phase 3's gate line records the move), so no task below is
written in detail yet: writing a loop's task list before that skill has run is the order `01` calls
the expensive one, and the shape of these tasks is what it would decide.

**Every ⚠ below is live, which is the opposite of Phase 6's.** All four tasks carry the mark and
**G12 is open**, so unlike Phase 6 — where each ⚠ was a record of something G9, G10 or G13 had
since settled — these are marks on tasks whose shape a decision could still change. `phase-step` →
*Orient* reads a ⚠ as a question about its gate; here the answer is *not yet*, and a task that
runs into one stops rather than defaulting it. Recorded explicitly because a phase whose preamble
never accounts for its own provisional marks is one where nobody can tell an open question from a
closed one — which is what `next_task.py --check-live` refuses to let happen.

- [ ] **7.1 ⚠** the agent is a pack — it registers against contracts it did not define, and core has no
  knowledge of it · owner `01` → Phase 7; `02` §1 · turns on — · sha —
- [ ] **7.2 ⚠** the loop's autonomy, tool surface, memory and approval points are the ones
  `agentic-patterns` names, chosen rather than inherited · owner `05` → G12; `01` → Phase 7 **Gate** ·
  turns on — · sha —
- [ ] **7.3 ⚠** the agent reaches Weft only through the published command surface — the same typed
  results a human's renderer formats, never a private API and never re-parsed text · owner `03` →
  *Two modes, one implementation*; `01` → Phase 3's gate line · turns on — · sha —
- [ ] **7.4 ⚠** the agentic pack installs from the index alongside the release and drives a corpus end
  to end with no edit to core, and `weft plugins doctor` reports it exactly as it reports any other
  pack · owner `01` → Phase 7 **Exit** · turns on — · sha —

**Exit** (`01` → Phase 7): task 7.4.

**Every task here is ⚠ and that is not hedging.** G12 is open *and* the `agentic-patterns` handoff has
not run, so these four state the properties the phase must end with while leaving their shape to the
gate — which is exactly what the ⚠ marker means in *How to read a task line* above.

## Phase 8 — From engine to product

**Added 2026-09-05, logged as scope decision `S9`.** `01` → Phase 8 owns the content and the exit;
this section owns the tasks. The phase exists because the gap it closes was found by *counting*
rather than by reading: four pipeline documents in the whole tree naming ten plugins, against
forty-eight plugins registered into pipeline positions — the promise "naive to advanced, quickly"
true of the engine and false of the product.

**⚠ No gate, and that is why this phase runs before Phase 7.** G12 blocks Phase 7 and nothing
blocks this. `scripts/next_task.py` reads the ledger top to bottom, so it will keep printing `7.1`
as the first unticked box; **`docs/README.md`'s Next action row is what overrides that**, and it is
pointed here. The number says when this phase was added to the plan, not where it sits in the
queue. Nothing below carries a ⚠: every decision these tasks need is settled.

**This phase absorbed `ROADMAP.md`, which is now retired to a pointer.** That file was a shortlist
ordered by effect ÷ effort and it explicitly held no state, which was correct while its rows had no
phase and wrong the moment one got built — `rerank-then-generate` shipped as a side effect of task
8.1, closing what that list called row 5, and there was nowhere to record it. Rows 1–5 are tasks
8.1–8.8 below. **Row 6, the graph as a shipped pack, is deliberately absent**: it is blocked on
three decisions, the first two of which touch G2, G4, G5 and `S5` at once, and a phase does not
absorb work that is not schedulable.

**Tasks 8.1–8.5 were built in one commit and by one person rather than through the implementer
split.** `phase-step` → *Green* permits that where the change is smaller than its brief, and here
the deliverable *is* the data: nineteen documents whose whole content is judgement — every
`route.summary` is a claim a router will believe, so writing a brief that specified them would have
been writing them. Task **8.3** is the exception in kind and was still done the same way, because
it is a config key and two call sites. Said here because nothing else records it.

- [x] **8.1** every query technique this engine registers is reachable as a rung somebody can run,
  and each rung is a *derivation* on the one below rather than a copy · owner `01` → Phase 8; `02`
  §3 · turns on — · sha `00bf24c` · eleven documents, all `extends: retrieve-then-generate`, one or two
  operator blocks each. **Requirement 3 stops being merely available**: `extends` was exercised by
  tests and by `manual/`'s worked example and by nothing a user could run. Every derived rung
  restates its own `route.summary`/`route.cost`, because `weft_retrieve.engine` merges a parent's
  `vars` and a rung that named none would advertise itself to `nearest-description` in its
  parent's words
- [x] **8.2** a corpus can be indexed through a document rather than through four Python constants ·
  owner `01` → Phase 8 · turns on — · sha `00bf24c` · six ingest documents, the first this project has
  ever shipped. `weft index --pipeline` was a flag pointing at nothing, and every cleaner, the
  chunker, the embedder and the store were registered, listed by `weft plugins list`, and placeable
  by nobody. **Four of the six run end to end; two cannot, and finding that out is what this task
  was for** — see 8.10. This line originally also claimed *"and `raptor-and-leaves-rrf` has a
  floor"*, and that clause was **removed rather than left standing**: the document exists and
  resolves, and running it is blocked by the defect 8.10 names, so the floor is written and not yet
  walkable. A ticked box that claims the second thing would be exactly the ledger this file's own
  closing section refuses
- [x] **8.3** the router is a name an operator selects, not a constant a package holds · owner
  `03` → *Configuration*; `01` requirement 4 · turns on — · sha `00bf24c` · `[services] route`, resolved
  the way `embed` and `store` already are. Found by writing 8.1: `threshold-ladder` and `always`
  were registered, listed and catalogued in `10` §1.5 and **placeable by nobody**, because a pack
  cannot contribute a second document under a name another pack holds and a project shipping its
  own `route.yaml` is refused by `full_catalogue` — which does not merely lose the override, it
  takes every `weft pipeline` command down until the file is renamed. That is `01` item 11's
  quoted reference defect with a live instance in this tree
- [x] **8.4** a capability registered into a pipeline position without a rung fails the gate ·
  owner `01` → *Fitness functions* item 16 · turns on **FF16** · sha `00bf24c` · scope derived from
  which distributions actually contribute a document, positions derived from `Stage in
  __mro__` — neither enumerated here. Waiver pinned at two `Renderer` names, and Phase 8's exit
  requires it **empty**, so the entry is a dated debt rather than a parking space
- [x] **8.5** every rung is named where a reader looks for it — `10` for the technique claims,
  `03` and `manual/` for `[services] route` · owner `10`; `03` · turns on — · sha `00bf24c`
- [ ] **8.12** a router an operator can *name* is a router they can *author* · owner `03` →
  *Project context*; `01` requirement 1 · turns on — · sha — · **Found by `weft-qualities` against
  task 8.3, by running it rather than reading it.** `[services] route` selects among documents an
  installed pack **contributed**: `weft_cli.route_ask.run_routed_ask` searches `load_contributed`,
  not `full_catalogue`, which is Phase 2's settled behaviour and was deliberately not reopened at
  8.3. Measured consequence — a project-local `pipelines/my-router.yaml` is in the catalogue
  (`weft pipeline show my-router` resolves it, `weft ask --pipeline my-router` runs it) and
  `[services] route = "my-router"` refuses it: *"no installed pack contributed a pipeline named
  'my-router'"*. The message is accurate and the asymmetry is still a defect, because **8.3 is what
  made it reachable**: while the router's name was a constant nobody could substitute it at all, so
  the restriction was invisible; now the key invites an operator to name a router and half the ways
  of having one do not work. Requirement 1's producing/consuming test read against a *project*
  author rather than a pack author — the consuming side exists and the producing side is ignored,
  which is `lessons.md` L5.15's shape. **A task and not a patch**: "the router's own search set" is
  settled text in `weft_cli.route_ask`'s own docstring, and narrowing settled text mid-review is
  what `phase-step` → *When to stop* forbids
- [x] **8.6** a question is answered from vector and full-text results **fused**, retrieved from
  the one store, and the fusion asks neither list where it came from · owner `01` → Phase 8;
  `10` §1.5's `hybrid` row · turns on — · sha `—` · `weft_store`'s `search_text` was implemented in
  pgvector and **had no caller in the tree**, while `vector-top-k`'s own config validator had been
  printing *"Use 'hybrid'"* at operators since task 2.14 and `10` §1.5 had been reserving the name
  since 2.33 — a name shown to users in a refusal, documented, and installable by nobody. Two
  halves, each correct, meeting nowhere. **`hybrid` does no score fusion, deliberately**: an alpha
  over a cosine similarity and a lexical relevance score compares two scales with no common unit,
  and `10` §1.1 records the reference growing exactly that in the second of its two RRF copies. It
  returns two labelled `RankedList`s and `reciprocal-rank-fusion` merges them **by rank**, which
  needs no calibration — so the composition is a document (`hybrid-then-generate`), not a second
  fuser. `needs_store = (VectorSearch, TextSearch)` whatever `channels` says, so a run against
  `qdrant` is refused at assembly rather than at a later `with:` edit. **Row filed in `10` §1.5
  with no origin paper and §5 says why**: this catalogue has not read the dense-plus-lexical
  literature at source and will not assert an origin it has not read. The `multi-arm` row's
  pointer to *"§1.1's unbuilt row"* is corrected in the same commit — §1.1 never held one
- [x] **8.7** no run issues more concurrent model calls than its own configured cap · owner
  `01` → Phase 8 · turns on — · sha `54c3d6f` · **This line named two sites and one of them was already
  fixed.** It was written from `ROADMAP.md`'s own row, which said `asyncio.gather` is unbounded at
  `raptor.py:191` and `hypothetical_questions.py:93`. Grepping every fan-out in the tree before
  acting — `asyncio.gather|Semaphore|TaskGroup` across `packages/*/src` — found `raptor` already
  holding `asyncio.Semaphore(max_concurrent_summaries)` at `raptor.py:222`, and `raptor.py:191` is
  now a docstring line. **One** unbounded fan-out remained, in `hypothetical-questions`, which is
  `raptor`'s sibling under the same contract doing the same thing one payload shape over — a rule
  one of two authors remembered, which is the shape `CLAUDE.md` says decays. `max_concurrent_nodes`
  now mirrors `max_concurrent_summaries`, default `8`, held as one semaphore across the whole call
  rather than a chunked `gather` loop that would idle every permit behind one slow completion.
  Checked by a double recording the high-water mark of calls in flight, with a non-vacuity twin
  raising the cap above the batch and asserting the peak rises — a count of completions would be
  identical bounded or not (`lessons.md` L6.1: a claim a document states in the present tense
  expires, and this one had)
- [ ] **8.8** a claimed improvement can be shown **not** to be real · owner `09` §4 · turns on — ·
  sha — · the falsification instrument. `weft-eval` and a validation corpus both exist and no gate
  blocks it, and it discharges an open 1.0 precondition. It outranks everything below it despite a
  lower headline, because it is what makes every claim tasks 8.6 and 8.1 support worth anything
- [ ] **8.9** a `Renderer` has a driver, and fitness function 16's waiver is empty · owner `02`
  §1; `01` → *Fitness functions* item 16 · turns on — · sha — · `plain` and `markdown` are
  registered `Stage` termini producing a `Rendition` that **no shipped command returns to
  anybody**, so a document ending in one runs and discards its only product. Task 2.27's own exit
  demonstration — "an operator's PDF becomes readable" — is not currently reachable from the CLI

- [x] **8.10** an `Expander` runs where it is registered to run · owner `02` §1; `01` → Phase 8 ·
  turns on — · sha `6e3b700` · **Found by running the binary at 8.2, and it is older than this phase.**
  `weft index --pipeline index-with-raptor` fails with *"no service is registered for Embedder on
  this run"*, and `index-with-questions` with the same sentence about `Prompts`. Both plugins are
  registered under `weft_index.contract.Expander` — an **ingest-path** contract — and both reach an
  ambient service through `ctx.require`, which the query path builds in `weft_cli.run_services.
  build_services` and which `weft_cli.ingest.run_index` **never builds at all**. So `raptor` and
  `hypothetical-questions`, tasks 2.31 and 2.32, have never been runnable through the CLI in the
  one place they belong; their exit demonstrations were unit tests handing the context in directly.
  **Not fixed here on purpose**: which ambient services an ingest run should expose is a design
  question — the query path's `build_services` resolves LLM roles, the store and the token sink
  together — and answering it inside a data task would settle it by implication. It is also the
  reason 8.2's own line no longer claims `raptor-and-leaves-rrf` has a floor ·
  **closed by `build_index_services`**, a second, narrower assembler beside `build_services`:
  `LLM`, `TokenSink`, `Prompts` and `Embedder`, and the three that are *absent* are the design
  answer this task owed. `StageLookup`/`RouteCatalogue` are `weft-retrieve`'s and an ingest
  stage able to reach them would be an ingest plugin depending on the query path; `NodeStore`
  is absent because an ingest document already names a store *stage*, so an ambient one would
  give one run two paths to the same store. **And the `Embedder` is the resolved document's own
  embed-stage instance, not `[services] embed`** — on a `--pipeline` run that key is
  deliberately unread, so resolving it here would let `raptor` cluster with one embedder while
  the document wrote vectors with another: a run that succeeds, an index that is built, and
  summaries sitting in a different vector space from the chunks they summarise, with nothing
  reporting it
- [x] **8.11** a `*_config` block reaches the sibling it configures as that sibling's own config
  object · owner `02` §3; `01` requirement 6 · turns on — · sha `6e3b700` · **Found by running
  `weft ask --pipeline corrective-retrieve` while verifying 8.10.** `corrective`,
  `iterative-retrieval` and `refine-on-uncertainty` publish **seven** `*_config` fields between
  them, each typed `Mapping[str, object] | None` and each documented as the way a document
  retunes a sibling resolved by name. `RegistryStageLookup.build` handed that mapping straight
  to the factory, so the sibling was constructed with a raw `dict` where its config object
  belonged and died inside its own `run` — `'dict' object has no attribute 'channels'`. Seven
  parameterisation surfaces, none of which worked, requirement 6 ("every piece of it is
  parameterisable") false at all seven, and no test caught it because every test driving these
  plugins left the sibling's config at `None`. `tests/unit/weft_retrieve/test_engine.py`'s own
  `_echo_factory` had been guarding `isinstance(config, _EchoConfig)` since the file was
  written, which is the shape a workaround leaves behind. Repaired at the seam: `build` and
  `build_capability` validate a `Mapping` into the plugin's own `config_model`, refuse a block
  for a plugin publishing none rather than dropping it, and pass an already-built config object
  through untouched

**Exit** (`01` → Phase 8): tasks 8.4 with an empty waiver, 8.6, 8.7 and 8.8, demonstrated
together from outside this repository against an installed `weft-rag` and one container.

**Verified by running the binary from `/private/tmp`, outside this repository, against the
`compose.yaml` container — which is where four of this phase's five findings came from, and
where tasks 8.10 and 8.11 came from outright.** After those two: `weft index --pipeline
index-with-raptor` and `--pipeline index-with-questions` both run, and the store holds the
proof rather than the summary line — `SELECT ext->'weft-index'->>'technique', count(*) FROM
weft_nodes GROUP BY 1` returns `hypothetical-questions | 9` and `raptor | 1`, so
`raptor-and-leaves-rrf`'s filter finally selects something a shipped path produced.
`iterative-retrieve` and `corrective-retrieve` now run their sub-retrievers to completion and
fail only where `scripted` cannot answer a structured prompt, which is the test provider
behaving as designed. **One thing measured and not repaired**: `index-with-raptor` against the
default `hash` embedder builds **zero** summaries and reports success — `similarity_threshold:
0.75` over deterministic hash vectors is a bar nothing clears. Stated in the document itself
rather than fixed, because clustering meaningless vectors arguably *should* produce nothing;
what is wrong is only that it is silent.

**The first verification pass, before 8.10 and 8.11 existed, found this:**
`weft pipeline list` prints **23** documents where it printed 4. `weft pipeline show` resolves every
one of the nineteen new rungs and prints per-stage provenance, so a derived rung is readable as
either the delta or the resolved whole. `weft index ./corpus --pipeline index-text` stored 5 nodes;
`index-messy-text`, `index-polish` and `index-with-keywords` also ran. `weft ask --pipeline` ran
`retrieve-then-generate`, `no-retrieval`, `rewrite-then-retrieve` and `draft-then-refine` to a
generated answer against the `scripted` provider. **Three failure paths, all loud and all correct**:
an unknown `[services]` key naming all three valid keys and exiting 4; a rung needing a role no
`[llm.roles]` entry maps, naming the role and the line to add; and the structured-output rungs
(`rerank-then-generate`, `grade-then-generate`) refusing because `scripted` returns fixed prose that
is not a `PassageRelevance` — the test provider behaving as designed, not a defect in the rung.

**And one piece of friction the ladder did not cause but did expose.** Every ingest rung names
`pgvector`, so `weft pipeline show index-text` on a checkout with no `[packs.store] dsn` fails with
*"stage 'store' names plugin 'pgvector', which no installed distribution registered"* followed by a
hundred names — while the actual cause is that `weft-store` **failed to register for want of a
DSN**, which `weft plugins doctor` already knows and this message never says. Requirement 5's third
clause is satisfied and its purpose is not: the options are named and the reason is not. Filed here
rather than fixed, because the raise site is in resolution and the fact is in the pack report, and
`phase-step` → *Finish* is explicit that user-facing text is repaired at the seam that renders it

---

## Why the sha column is not optional

A ticked box with no sha is a claim; a ticked box with a sha is a fact someone else can check. The
shape being refused is the reference's only key-parity test, which computes a difference and then reports
it through `pytest.warns(...)` called as a bare statement, so it does nothing and **cannot fail** —
*"the 195/195 parity holds today by discipline, not by enforcement"*
(`reference/study/08-salvage.md:777-782`). A ledger whose ticks cite nothing is that test with a
different subject.

**As of the last edit to this file, the tree was at `6e3b700`.** Tasks are ticked by the commit that
closes them, so this line is the only place a date-shaped claim appears — everything else is a sha.
