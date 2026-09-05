# 08 — The shipped documentation set

**What this document owns:** a manifest of the documents Weft ships — which need a home of their own,
see *Where these live* below — and the tests that keep each one honest. It does **not** define a
numbered fitness function; see §3, which implements decision **D1**. Four gates are open (**G2, G7,
G8, G9**); every place this document's timing depends on one of them, it says so and assumes nothing
about the outcome.

---

## 0. The gap this closes

`docs/` today is written for the people building Weft. It has no reader who only wants to *use* the
product, and no phase currently produces one line for that reader. That is not an oversight so much
as a predictable consequence of the plan being organised entirely around phases and gates — but this
is a known failure shape when user-facing prose is left to arrive whenever: a library that ships **no
`README` or `.md` file at all** — every claim about how to use it living in a docstring, uninspected —
is a real, observed case, and so is a docstring in exactly that position making a claim the code
cannot back: *"Strategies self-register via decorators so new kinds can be added without modifying
callers,"* against a decorator whose `kind` parameter requires membership in a **closed 3-member
enum**. Nothing checked that sentence against the code it described, so it aged into a false
advertisement of the central thesis it was supposed to be proving — extensibility — read by exactly
the audience most likely to try it and be burned. Weft's own thesis is the same claim; its shipped
documentation needs a mechanism to keep that from happening, not just better intentions.

---

## 1. The shipped documentation set

| Document | Audience | Covers | First written |
|---|---|---|---|
| **Quickstart** | Someone evaluating Weft, five minutes, no context | One executable path from `uv add` to a real answer with citations on their own files. Nothing else — no concepts, no options | Phase 0 step 11 |
| **User manual** | Someone using Weft as a library or CLI day to day | `weft index`, `weft ask`, the pipeline commands, `weft.toml`/`weft.yaml` and the `packs:` namespace, configuration precedence and `--origin`, and the equivalent Python calls for someone driving the kernel without the CLI | Phase 1 (index/ask/config already true from Phase 0, folded in), extended at Phase 3 |
| **Pack author guide** | Someone writing a pack | The walkthrough from an empty directory to a trusted, published pack: publishing one contract implementation, testing it against the conformance kit and the blocking-call detector, and what happens when a pack is refused. Definitions link to `02` §1–§2 | Phase 0 step 11 (single-contract section), extended at Phase 5 (multi-contract pack plus a contributed CLI command) |
| **Contract reference** | Someone implementing a contract | What each published contract requires — method signatures, the `Outcome` shape, the version — and what the registration seam supplies automatically (spans, error attribution, `Lifetime`, transient stripping) so the reader knows what they must write versus what they get for free | Phase 0 for `Extractor`/`Chunker`/`Embedder`/the store family; one section added per phase that publishes a contract (Retriever/LLM at Phase 2, Command at Phase 3, Metric at Phase 4) |
| **Operations guide** | Someone running Weft | The one container (`compose.yaml`, pgvector), configuration file layout and precedence, `weft plugins doctor`'s status vocabulary, exit codes, and what the trust model does and does not protect against | Phase 0, extended at Phase 2 (second backend) and Phase 4 (`weft trace`, persisted runs) |
| **Troubleshooting** | Someone debugging a failure | What each loud failure looks like — exit code, `WeftError` subclass, refusal message — and the first thing to try. Not the reasoning behind the trust model or the store contract; that stays owned by `02` and is linked, not restated | Phase 0, one entry added per phase that introduces a new failure mode |

**No row in this table owns a definition.** Every command, exit code, status name and configuration
key named above is defined in `02` or `03` and is linked from the document that mentions it. What
these six documents own is the *task* — what a reader is trying to do and in what order — never the
fact itself. That is why the column is **Covers**, not **Owns**: an "Owns" column invites exactly the
restatement §3's *Single ownership* rule forbids.

**Only two of the six get a numbered build step, and that is deliberate, not an oversight.** Per
decision **D4**, `06-phase-0-build.md` gains a step 11 covering the quickstart and the single-contract
section of the pack author guide — the two documents whose content is what Phase 0's own exit
criterion makes true, and whose checks (§3, clauses a and c) need CI infrastructure that does not
exist until step 10 does. The other four documents are true earlier or later by the ordinary operation
of the phase that publishes their content, and their checks (§3, clauses b and d) are generic diffs
and set-equality tests that need no bespoke harness — they run the moment their subject exists,
because they live under `tests/docs/` and inherit reachability from `ci-checks` automatically (§3
explains why that is not merely convenient but the actual argument for why these are not fitness
functions). Nothing here asks `01`, `02` or `03` to add a step for them, and nothing here invents a
build-order document for a phase that does not have one yet — see §2.

### Where these live

None of the four settled rules say where shipped documentation goes, because none of `01`–`06` needed
to. `docs/` is claimed as **the plan**: `docs/README.md`'s own Documents table gives `01` through `06`
each a **Reference** kind and an **Owns** line about design — contracts, the CLI surface, the build
order — never about a reader outside the project, and `CLAUDE.md` routes readers
to `docs/README.md` for *"project status, which phase is live, which decisions are settled, and which
document owns what"* — again, project state, not product usage. Filing user-facing manuals into `docs/`
would either dilute that claim or require a second "which half of `docs/` is this" rule nobody has
asked for yet. The six documents above need a location that is obviously not the plan. They go in
a new top-level directory, `manual/`, sibling to `docs/`, `packages/`, `tests/` and
`scripts/`: `manual/quickstart.md`, `manual/user-manual.md`, `manual/pack-author-guide.md`,
`manual/contract-reference.md`, `manual/operations-guide.md`, `manual/troubleshooting.md`.

**The pack author guide's Phase 0 walkthrough is not written here.** Per decision **D3**, this document
specifies the guide — its audience, its scope, its checking mechanism — but does not contain it. The
walkthrough itself is user-facing documentation, not plan, and its corrected text (the `ordinal` bug
fixed) is left in the scratchpad as `draft-pack-author-guide.md`, raw material for whoever writes Phase
0 step 11. The multi-point section the guide gains at Phase 5 is not invented fresh either: it draws on
`02` §4, *Add-ons — driving use case B*, which already owns the graph pack's registration table and the
install sequence — the guide adapts that material into a walkthrough a stranger can follow, it does not
re-derive it.

**The contract reference is the one exception to hand-written prose**: per §3, it is generated by
walking the registered contracts, so its source of truth is a short generator plus each pack's own
docstring, not a hand-maintained file — `manual/contract-reference.md` is the generator's *output*,
checked in so it is readable without running anything, and regenerated in CI. If this is adopted, it is
a one-line addition to `docs/README.md`'s existing *Documents* table — a pointer, not a definition,
exactly as that table's own rule requires.

---

## 2. When each is written, and why not at the end

The argument is the same one `docs/README.md` already makes about itself, one level up: a document
written after the fact describes what got built and can drift from it forever after; a document that
can only be written once its phase's mechanism is real is a design review that happens to leave prose
behind, and it cannot describe something that does not exist yet. Applied here:

- **Quickstart, Phase 0 step 11.** The whole content of a five-minute quickstart is `uv add`, `weft
  index`, `weft ask`, on a directory of the reader's own files, against a real pgvector container.
  That is exactly Phase 0's exit criterion (`01` → *Phases* → Phase 0) plus its infrastructure step
  (`06` step 8, the `compose.yaml`). It cannot be written earlier because the commands do not exist
  yet, and writing it later would mean re-deriving, from memory, commands someone already ran to prove
  the exit criterion. **It is honest about what Phase 0 actually returns**, per `06`'s own scope
  fence: `weft ask` "retrieves and prints the matching passages" — no generation, no LLM pack, and the
  quickstart says so rather than overselling. Two revisions are scheduled, not open-ended: when Phase
  2 wires a real `Generator` the same quickstart starts returning prose with citations instead of a
  passage list, and when Phase 3 ships streaming the same command starts showing tokens as they
  arrive. Each revision is a one-line diff against a command that already runs, and each one changes
  what its check asserts, never how the check works — see §3, clause (a). **From Phase 2 the executed
  blocks run against the offline evaluation subset `09-release.md` §4 (V5) requires — no credentials,
  no network.** That is a dependency on `09`, not a second CI story: `09` §4 owns what the subset is
  and when it exists, and this document only says which check consumes it. It is a dependency with a
  consequence, and the consequence is stated rather than hidden — `09` §4 places V5 among Phase 4's
  deliverables, so the Phase 2 revision is gated on the subset arriving before it. A quickstart whose
  check needs a paid key inside `ci-checks` is a check that gets turned off, which is the outcome
  clause (a) exists to prevent; whether that means V5's offline half lands earlier or the revision
  lands later is `09` §4's call, not this document's.

- **Pack author guide, Phase 0 step 11 (single-contract section), extended Phase 5.** The mechanism a
  pack author needs — an entry point, `register()`, a typed settings model, the registration seam's
  automatic spans and error attribution — is complete at the end of Phase 0 (`06` steps 3, 5, 7) and it
  is the exact thing Phase 0's own exit criterion tests: `06` step 10 keeps a real out-of-tree pack,
  `examples/weft-example-chunker/`, as "an artifact rather than a demo." The guide's walkthrough is
  that artifact, turned into prose, per `draft-pack-author-guide.md` — a code sample that is the file
  it claims to be cannot drift from it (§3, clause c). What Phase 0 cannot teach is a pack that spans
  several contracts plus a CLI command, because the `Command` contract and plugin-contributed `--help`
  entries are Phase 3's, and the independence test that proves the multi-point case — "the graph pack
  is built by someone who has not worked on the core" — is Phase 5's exit criterion by name (`01` →
  Phase 5). The guide therefore gains a second, larger section at Phase 5, adapted from `02` §4's
  registration table and install sequence into the same kind of tested artifact the single-contract
  section already is. This is the single most important document for the project's thesis for exactly
  the reason `01` gives requirement 1 top billing: if a stranger cannot follow this guide and end up
  with a working pack, the microkernel bet did not pay off, whatever the fitness functions say.

  > **Built in Phase 5 task 5.3.** `manual/pack-author-guide.md` §9 is that second section, adapted
  > from `02` §4's graph-pack table and backed by two real, checked-in packs rather than an invented
  > one — `examples/weft-example-ingest/` (seven contracts, including the store-family capabilities
  > G7 added, plus a pack-owned `ExtModel`) and `examples/weft-example-command/` (a contributed
  > `Command`) — because the graph pack itself is task 5.4's, not built yet. It also teaches the
  > three obligations G9 re-derived for a pack author: the `>=X,<MAJOR+1` dependency specifier
  > (task 5.2a), `ExtModel.__schema_version__` and a refusing `upgrade` (task 5.2c), and what
  > `registrar.deprecate` obliges a changelog to say (tasks 5.2e–5.2f) — plus the fourth 5.2g added,
  > that `registrar.add_ext_model` is what makes a namespace survive a store round trip at all, and
  > only for an `ExtModel` reaching `Node.ext`. **Two rows of `02` §4's table could not be shown
  > against real code, and §9 says so rather than inventing a sample no check would cover**: no pack
  > anywhere in this tree — first-party or stranger — can reach `weft_kernel.resolution.Contribution`
  > from `register()` today, a gap `weft_cli.pipeline_commands`'s own module docstring already names
  > and assigns to task 5.4; and every `examples/*/pyproject.toml`, including both packs this section
  > cites, still declares its `weft-*` dependencies as bare names, predating G9 and outside task
  > 5.2a's own scope. Both are recorded in task 5.3's own `docs/build-ledger.md` entry and in
  > `docs/lessons.md` rather than papered over. §8's *Open gates you may hit* table is also corrected
  > in this task, since G2, G7, G8 and G9 — all four gates that table had listed as open — had
  > settled by the time this task started and the table had not been updated to say so.

- **Contract reference, incremental from Phase 0.** `Extractor`, `Chunker`, `Embedder` and the store
  family are the entire content of the reference at the end of Phase 0, because Phase 0 publishes
  exactly those four (`01` → Phase 0). `Retriever` and `LLM` arrive at Phase 2, `Command` at Phase 3 (gated by
  **G8** — the reference cannot describe a command surface that gate might still reshape before it
  exists), `Metric` at Phase 4. There is no "finish this document" milestone; it grows by exactly one
  section per phase that publishes a contract. The generator that produces it needs no bespoke Phase 0
  infrastructure beyond what `weft plugins doctor` already computes — the registry walk — so it needs
  no numbered build step of its own; §3 clause (b) runs the moment the first contract is published, and
  keeps running unattended after that.

- **User manual, Phase 1, extended Phase 3.** `index`, `ask` and the `packs:` settings namespace are
  true from Phase 0, but a manual whose "pipelines" section can only say "an ordered list you wrote
  out in full, no `extends`, no derivation" (`06`'s own description of the Phase 0 linear runner) is
  not yet the document the audience needs — pipelines-as-data, not a fixed list, is the feature that
  makes a manual necessary rather than a two-command cheat sheet. That content becomes true at Phase
  1's exit criterion — a derived pipeline expressed as configuration, no copy of the parent — which is
  gated on **G2**, so the manual's pipeline section cannot be honestly drafted before G2 closes
  regardless of anything this document says; Phase 1 itself already waits on the same gate (`01` →
  Phase 1). The manual's second wave is Phase 3: `weft pipeline derive`, `weft config get|set` and the
  REPL surface belong to the full CLI (`03` in full), not the minimal one Phase 0 ships (`06` step 9
  lists only `index`, `ask`, `plugins list|doctor`, `--version`), so the manual's command reference
  cannot be complete until then either — and its check, §3 clause (b), activates on the same schedule
  as the reference it diffs against.

- **Operations guide, Phase 0, extended Phase 2 and Phase 4.** Every piece named in its row of the
  table above is a Phase 0 deliverable by name: the `compose.yaml` (`06` step 8), the `packs:`
  namespace and `${env:}` interpolation and the doctor status vocabulary (`06` step 5), and the exit
  code split (`06` step 9, `03` → *Output*). It is the one document that could in principle be written
  entirely from Phase 0 output, and its check (§3 clause b — included content, not retyped) needs
  nothing beyond what already exists to diff against, which is why it gets no step of its own either.
  It grows at Phase 2, when a second backend (Qdrant) exists to operate and G4's "trusted by more than
  one implementation" claim becomes something an operator can act on rather than take on faith, and at
  Phase 4, when `weft trace` and persisted runs give an operator something to inspect after the fact.

- **Troubleshooting, Phase 0, one entry per new failure mode.** The kernel's error taxonomy
  (`WeftError`, attribution at the plugin seam) and the trust model's refusal vocabulary
  (`active`/`refused`/`failed`/`partial`/`allowed, not installed`/`ambient`) both exist by the end of
  Phase 0 (`06` steps 2, 3, 5) and are already, by design, loud and specific rather than generic — rule
  5 (unknown names fail loudly, naming the valid options) means most of what this document would say is
  already in the error message. Its job is the second sentence: what to actually *do* about exit 3
  versus exit 4, about a `refused` pack versus a `failed` one. New failure modes arrive with new
  mechanism — a resolution failure once derivation exists (Phase 1, **G2**), a capability mismatch once
  `needs_store` is checked against a real second backend (Phase 2), a permission-class prompt once the
  CLI's destructive-operation guard is live (Phase 3), an eval-comparison failure once runs are
  persisted (Phase 4) — so this document is never "done." What forces each new entry into existence is
  not a build step but §3 clause (d), the coverage ratchet: as soon as a new `WeftError` subclass or
  doctor status lands in code, the ratchet fails, naming it, until an entry exists. That is a stronger
  guarantee than a phase-exit clause would be, because it does not require anyone to remember which
  phase introduces which failure mode.

---

## 3. The rule that keeps them true

`docs/README.md` states its own version of this rule in its opening blockquote: a control file that
paraphrases the plan risks the same two-lists bug at the level of the plan. That bug shows up one
layer further out too, aimed at users instead of builders: a module docstring claiming strategies
"can be added without modifying callers," refuted by the same file's own decorator signature. Nobody
lied; nobody even checked. That is the failure mode this section exists to make structurally
unlikely, not to police by discipline.

**Single ownership among the six.** Exactly the same rule `docs/README.md`'s manifest already applies
to `01` through `06` — restated here because it is easy to assume user docs are exempt, and they are
the more tempting place to restate something for a reader's convenience:

- The user manual explains *how* to derive a pipeline; it links to `02` §3 for *why* the four
  operators are the closed set they are, and to the pack author guide for *how* a plugin declares the
  configuration a `with:` block validates against — it does not re-explain either.
- The pack author guide explains what a pack author writes; it links to the contract reference for
  the exact method signatures of whatever contract they are implementing, rather than listing them
  twice under two different levels of detail that can disagree.
- The operations guide explains what `weft plugins doctor` prints and what to do when a status is not
  `active`; it links to `02` §2 (*The trust model*) for why the posture is open-by-default and why a
  two-tier permission model was rejected, rather than re-arguing it, and it never claims a protection
  the model does not provide — see the next paragraph.
- Troubleshooting explains the symptom and the remedy; it does not re-argue the trust model's posture
  either. Where a symptom is "a pack did something its class did not permit," the remedy points at
  `03`'s own sentence — "these classes protect you from the tool, not from a pack" — instead of
  softening it.

**Generated or tested, where the mechanism allows it — and honest where it does not.**

| Document | Mechanism | What it catches |
|---|---|---|
| **Contract reference** | Generated, not written. A small script walks the registry the same way `weft plugins doctor` does, reads each registered contract's Protocol, docstring and declared version, and renders the reference. There is no second copy of a method signature for a human to keep in sync | A contract whose reference disagrees with its Protocol — the two-lists bug, aimed at a contract instead of a file format |
| **Pack author guide's code samples** | Tested by identity. Each fenced code block that claims to be part of `examples/weft-example-chunker/` (Phase 0 section) or the Phase 5 example pack carries an explicit source-path tag, and a test diffs the tagged block's content against the file it names | The sample drifting from the artifact it is supposed to demonstrate — a guide that once matched the example and quietly stopped |
| **User manual's command reference** | Generated. `03` already commits to help text generated from the registry so `weft --help` "cannot drift from what is installed" (`03` → *Plugin-contributed commands*); the manual's command table is the same generation step, rendered to Markdown instead of a terminal, run in CI against a committed copy | A command added, removed or reworded in the CLI without the manual noticing |
| **Operations guide's `compose.yaml`, exit-code table, doctor vocabulary** | Included, not retyped. The compose snippet is the actual shipped file; the exit-code and status tables are generated from the same enums the CLI and doctor read | The guide showing a container topology or a status name that no longer exists |
| **Quickstart** | Executed. Its fenced shell blocks are extracted and run against a fresh throwaway project in CI, and the run must exit `0` and produce a structure the prose asserts — never a text match on generated prose, so a model swap cannot break the check. From Phase 2 the executed blocks run against the offline evaluation subset `09-release.md` §4 (V5) requires — no credentials, no network | A quickstart that stopped working being discovered by a reader instead of by CI |
| **Troubleshooting's coverage** | Checked, not generated — the remedy is written by a person, but *completeness* is a ratchet, in the same style as the one `01` → *Fitness functions* item 0 already uses: a named waiver constant, pinned empty, so a gap is a visible act in a diff | A new failure mode landing in code with no matching entry — a *17 of 23 evaluators registered*-style gap, aimed at documentation coverage instead of registration |

**What stays honestly hand-written, and does not pretend otherwise.** The *why* in every document —
why the trust model is open by default, why a store never embeds, why deletion cascades — is argued
prose that belongs to `01`/`02` and is linked, never generated; generating an explanation would only
produce confident-sounding filler. The remedy text in troubleshooting ("try X") is a person's
judgement about what usually works, not a fact a script can derive from a stack trace. And the
pack author guide's *narrative* — why to shape a pack this way, what the graph pack's four
registrations are for — is written once and reviewed like any other prose; only its code samples are
mechanically checked. Pretending a rationale can be generated would be the same category of dishonesty
the trust model's disclosure field explicitly refuses (`02` §2: "a field that reads as *this pack does
not use the network* is unverified... and fails silently in the unsafe direction").

### Where each check lives, and how `ci-checks` reaches it — decision D1

**These are ordinary tests, not a numbered fitness function.** `01` → *Fitness functions* is
architecture enforcement — its own preamble reads *"Architecture that is not enforced decays"* — and
item 0 exists because a real boundary checker once sat outside its own canonical gate and therefore
never ran. A documentation
check is not an architecture property; it belongs under `tests/`, checked by `pytest`, exactly like
every other test in the tree, and it gets to skip the ceremony item 0 needs for a reason specific to
that ceremony: `pyproject.toml`'s `[tool.pytest.ini_options]` already sets `testpaths = ["tests"]`, and
`poe test` is `pytest tests -q`, already the last step of `poe ci-checks`. A test placed under
`tests/docs/` is swept up automatically — there is no second reachability proof to write, because
unlike `tests/architecture/` (which needed its own membership check specifically because an
analogous checker once sat in a *different* composite task — call it `quality` — that was never
wired to the one `CLAUDE.md` calls canonical) `tests/docs/` was never at risk of being orphaned in
the first place. That
is not a loophole; it is the actual reason these checks do not need to be fitness-function-shaped —
"ordinary test under `tests/`" already comes with a working reachability guarantee that architecture
checks, historically, did not.

Each check still gets a **ratchet** — a named waiver constant, pinned empty, in the style of `01` item
0's `CHECKS_WAIVED_FROM_GATE` — so that excluding anything from the check is a visible act in a diff,
never a silent omission. And each check has a **floor**: a condition that must be non-trivially true
before the comparison runs, so the check cannot pass by having nothing to compare. That floor is the
fix for a real, observed documentation check that **cannot fail** — it computes a diff, then reports
it through `pytest.warns(...)` called as a bare statement rather than a context manager, so it does
nothing, and *"the 195/195 parity holds today by discipline, not by enforcement."* A check with no
floor is that test with a different subject.

| Clause | Lives at | Ratchet constant | Floor |
|---|---|---|---|
| (a) Quickstart executes | `tests/docs/test_quickstart.py` | `BLOCKS_WAIVED_FROM_EXECUTION: Final[frozenset[str]]`, pinned empty — a fenced block skipped from the CI run (say, one requiring a paid API key added later) must be named here explicitly | At least one fenced shell block is extracted before any is run. A quickstart with nothing to execute cannot pass by having nothing to fail |
| (b) Generated reference and command table match the registry | `tests/docs/test_generated_docs.py` | `CONTRACTS_WAIVED_FROM_REFERENCE: Final[frozenset[str]]`, pinned empty | The set of contracts the generator walked equals the registry's published-contract set — the same runtime set-equality shape fitness functions 2 and 4(b) use — asserted **before** the text diff runs, so a generator that emits nothing cannot match a committed empty file |
| (c) Pack guide code samples are the file they claim | `tests/docs/test_pack_guide_samples.py` | `UNTAGGED_CODE_BLOCKS: Final[frozenset[str]]`, pinned empty — a fenced block that reads as a code sample but carries no source-path tag is a failure unless named here | The count of tagged blocks is non-zero. A guide with zero tagged blocks passes zero comparisons, which is exactly how a retyped, untagged sample drifts unnoticed |
| (d) Troubleshooting coverage | `tests/docs/test_troubleshooting_coverage.py` | `ERRORS_WITHOUT_TROUBLESHOOTING_ENTRY: Final[frozenset[str]]`, pinned empty | The enumerated set of `WeftError` subclasses and doctor statuses is non-zero before checking each has an entry |
| (e) `CHANGELOG.md` names every deprecated surface | `tests/docs/test_changelog_deprecation_coverage.py` | `DEPRECATIONS_WITHOUT_CHANGELOG_ENTRY: Final[frozenset[str]]`, pinned empty | Stated honestly rather than forced: zero first-party surfaces are deprecated today, so asserting the installed set non-empty would be false. The floor is a proof instead — a real `Deprecation`, produced through `PackRegistrar.deprecate` → `commit`, shown to be reported missing against today's real `CHANGELOG.md` and to clear once an entry naming it is added (`test_the_comparison_can_actually_fail`), the same self-test shape `test_ff9_extension_from_outside.py::test_the_grep_can_actually_fail` uses |

All five run inside `poe ci-checks` via the existing `test` step. None of them touches `poe
ci-no-tests` or `tests/architecture/` — they are not architecture checks, and `01` item 0's membership
assertion is unaffected and needs no widening. Clause (e) is task **5.2f** (`docs/build-ledger.md`),
owed by `docs/09-release.md` §3's own block quote and `docs/lessons.md` L5.8.

---

## 4. What keeps each document honest, and what fails when it does not

No document in `docs/` carries an effort estimate — `01` prices the kernel budget once, argues it, and
then enforces the number; nothing in the plan prices *work*. This section replaces effort with the
question that is actually decision-relevant: whether a document's correctness is *generated*, *tested*,
or *hand-written*, and what specifically fails when it drifts.

| Document | Correctness is | What fails when it drifts | Load-bearing? |
|---|---|---|---|
| Quickstart | Tested — executed in CI, §3 clause (a) | The build, not a reader's afternoon: a broken command fails `ci-checks` before it ships | Load-bearing from the first release — nobody evaluates a RAG engine without running it |
| Pack author guide | Tested by identity for its code samples, §3 clause (c); hand-written for its narrative | A retyped sample silently stops matching the artifact it claims to demonstrate — caught by the identity diff, not by a stranger filing an issue | Load-bearing from the first release, and the highest-leverage document in the set — it is the whole thesis; a microkernel nobody can extend without asking is a slower version of the thing being replaced |
| Contract reference | Generated, §3 clause (b) | A contract's reference disagreeing with its own Protocol — the two-lists bug, aimed at a contract instead of a file format | Nice-to-have while the project has no pack authors outside itself; load-bearing the moment one exists, which the project's own thesis says should be soon |
| User manual | Hand-written narrative; its command table generated from Phase 3, §3 clause (b) | Before Phase 3: nothing catches drift but review, same as any hand-written prose. From Phase 3: a command added, removed or reworded in the CLI with nothing in the manual noticing | Load-bearing by Phase 3; the quickstart already covers everything true in the Phase 0–1 window |
| Operations guide | Included, not retyped, for its tables; hand-written for its narrative, §3 | The guide showing a container topology or a status name that no longer exists | Load-bearing from the first release — nobody runs pgvector correctly by guessing |
| Troubleshooting | Checked, not generated: the remedy is a person's judgement, but coverage is a ratchet, §3 clause (d) | A new failure mode landing in code with no matching entry — caught by the ratchet naming it, not by a support conversation | Nice-to-have early; load-bearing once Phase 4–5 complexity (persisted runs, multi-pack failures) makes support cost real |

The corollary of `01`'s own argument about cross-cutting concerns — *a concern the machinery applies
automatically holds; a concern an author has to remember decays* — is a sequencing rule of its own here
too: build the generator or the test *before* the prose it protects, the same order Phase 0 already
puts the registration seam before anything it wraps, so nothing in this set is ever hand-verified even
once.
