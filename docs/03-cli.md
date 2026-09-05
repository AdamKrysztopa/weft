# 03 — The CLI

Modelled on Claude Code: an interactive session you live in, that is also a scriptable
non-interactive tool, where installed plugins contribute commands, and where anything destructive
asks first.

## The governing rule

**The CLI is a driving adapter and holds no logic.** Every operation it performs is a library call
that a FastAPI route could make identically. When a behaviour is tempting to put in the CLI —
progress aggregation, retry on a failed document, a summary table — the test is whether an HTTP
caller would want it too. If yes it belongs in the library and the CLI renders it.

> **Unverified:** whether the reference's services could in fact make the same calls concerns
> `system/`, which the reference study did not examine. See `reference/study/09-open-questions.md` (U9). The
> rule stands on its own merits; it is the *lesson-from-the-reference* framing that is unsourced.

This is the rule that keeps requirement 5 true. The predecessor's `indexer.py` reached 1,080 lines
of Typer command that no service could reuse. Two further facts about that file are direct evidence
for the rule:

- **It runs `load_dotenv(override=True)` at module import time** (`indexing/indexer.py:52`), so
  merely importing the CLI mutates the process environment. The scar comment explains why — *"This
  prevents stale shell exports from shadowing .env during local development"* — which is deployment
  policy hardcoded into a library module. The rule Weft should adopt from it: **a driving adapter
  may not mutate process state at import.**
- **The reference ships three separate CLI entry points**, `rag-index`, `rag-chat` and `rag-query`
  (`pyproject.toml:141-144`), not one. Three surfaces means three places for logic to accumulate and
  three help texts to drift.

> **Corrected from the reference study (2026-08-10):** this paragraph previously continued *"…and its
> chunker factory ended up in the evaluation package partly because the CLI was where things
> accumulated."* The 1,080-line figure is exact, but the causal clause cannot be supported:
> `create_parser` lives at `evaluation/datasets/settings_loader.py:55-99` and is pulled onto the
> production path by **function-local imports in `retrieval/storage.py:145` and `:407`**. Nothing
> connects it to the CLI. The two facts above replace it and argue the same rule more strongly.
> (`reference/study/10-doc-corrections.md` C1.)

## Two modes, one implementation

```bash
weft                              # interactive session
weft ask "what changed in Q3?"    # one shot, same code path
```

Both go through the same command objects. The REPL is not a second implementation with its own
parsing; it is the same commands with a different renderer and a persistent context.

**Which forces the shape of what a command returns: a typed result, never printed text.** A command
that prints has already chosen its renderer, so "the same commands with a different renderer" cannot
be true of it — the sentence above is only buildable if rendering happens strictly after the command
returns. State it as the rule it is: **a `Command` returns a typed result and never writes to a
stream**; `weft_cli` renders that result for a human, `--json` renders the same result for a script,
and the REPL renders it again with the session's context around it. G8 (2026-08-18) noted the
consequence rather than adding to it — the same property is what lets a Phase 7 agentic pack call
this surface instead of re-parsing its output. See *Is the REPL an agent?* below.

> **Built in Phase 3 task 3.4 (2026-08-19); the entry condition corrected by task 3.6
> (2026-08-20), `docs/03-cli.md` → *Output*'s own blockquote carries why — and corrected again
> by the repair recorded against 3.2/3.4/3.8 in `docs/build-ledger.md`, dated 2026-08-20.**
> `weft` with no command named — no arguments at all, or only global flags such as
> `--json`/`--quiet` — enters the session above; a lone `-h`/`--help` does not, and this
> paragraph used to say it did, which was the defect the repair fixes (`weft_cli.cli.wants_help`
> is the routing fact that keeps it out, checked ahead of the test below). `weft_cli.repl.run_repl`
> reads a line, resolves it against the identical registry-driven
> `argparse.ArgumentParser` `weft --help` is generated from (`weft_cli.cli.build_parser`), and
> calls `weft_cli.cli.run_command` — the same function a one-shot invocation calls, unmodified —
> so there is nothing here for the REPL to duplicate. `Command.run` now runs through
> `weft_kernel.seam.wrap` again (reverted by task 3.2, `.phase3-design.md` O1): the blocking-call
> guard, the one concern that broke `weft index`'s own filesystem walk, is turned off with a new
> `guard_blocking_calls` keyword rather than the seam being skipped wholesale, so a `Command`
> invocation gets spans and error attribution back without a second, hand-written wrapper beside
> the seam it would drift from. **An interactive session's own process exit code is `SUCCESS`
> whether it ended by `/exit` or end-of-input, independent of the last command's own result** —
> a session is a shell, not a pipeline of one command, and a script that wants a meaningful exit
> code already has the one-shot form for that, per G8.

## Command surface

Verb-first and small. Depth lives in subcommands, not in flags.

```
weft init                      scaffold weft.toml in the current project
weft index <path>              run an ingestion pipeline over a source
weft ask <question>            query, streaming the answer with citations
weft pipeline list|show|derive|validate|diff
weft plugins list|info|doctor
weft eval run <path> <pipeline> [--questions <file>] [--top-k <n>]
                                    run a pipeline over a corpus, persist a run record; with
                                    --questions, also retrieve and score the gate-safe metric
                                    subset, folded into the record
weft eval compare <a> <b>          diff two persisted runs' pipelines and their per-metric
                                    aggregates, refusing if anything but the pipeline differs
weft eval metrics [--name <name>]  which registered metrics run in the deterministic gate
                                    subset — no credentials, no network — or ask about one
weft trace <run-id>            print what one persisted run recorded
weft delete <source-id>        remove a source and everything derived from it, everywhere
weft reconcile [--mode repair|full] [--dry-run]
                               converge derived state against the corpus
weft config get|set
```

Two of these carry weight beyond their size:

- **`weft pipeline diff a b`** renders the difference between two *resolved* pipelines. Because
  resolution produces a fully-explicit form, this is an exact comparison rather than a guess, and
  it is what makes derived pipelines reviewable.
- **`weft plugins doctor`** reports what was discovered, from which distribution, at what contract
  version, and what failed to load and why. When someone's pack is not appearing, this is the
  first and usually last thing they run. It prints **one status per pack** — `active`, `refused`,
  `failed`, `partial`, `allowed, not installed`, with an `ambient` flag — plus each pack's
  disclosure and what its `register()` cost. The vocabulary is defined once in `02` §2, *The trust
  model*; refusals and half-registered packs share it rather than getting a second surface.

  **A row leads with the pack and names its distribution in parentheses** — `store (weft-rag
  0.1.0): active (6 contributed)`. One distribution may ship several packs (`weft-rag` ships
  twelve), so the distribution alone cannot tell twelve rows apart; the pack is the `weft.packs`
  entry-point name and is also what a `[packs.<pack>]` settings block keys on. `allowed, not
  installed` is the one row printed without a pack, because `[packs] allow` named a distribution
  nothing installed claims and there is therefore no entry point to name. `02` §2 → *Pack settings*
  owns the split.

  **`doctor` also names a pack two installed distributions both claim**, in its own trailing block
  beside version skew and inert pins. Nothing is refused — a stranger's entry-point name is not
  ours to rename — but one `[packs.<pack>]` block would configure both, so it is said out loud.

  **The status line also names the distribution's installed version** — task 6.4, `09` §1's "one
  column, not a new command: the version of each active distribution", read from installed
  metadata rather than from any manifest. A distribution with none recorded prints `(version not
  recorded)`, which is a state distinct from a version this command declined to look up. The
  column is `doctor`'s alone; `weft plugins list` stays a one-line summary.

  **G2 adds two reports to it, both about a pack that loaded fine and still does nothing** — the
  failure a status vocabulary alone cannot express. A **displaced** registration: the pack lost a
  `(contract, name)` collision to an operator's pin, so it is installed, active, and one of its
  plugins is unreachable. And a pack whose **contributions land in no pipeline at all**, because no
  available pipeline declares the slot it targets. Both are silent successes otherwise, and both are
  the shape of the reference's registered-but-unreachable strategy.

  **Task 5.1d adds a `tracing:` line, and it is a fact about the process, not about one pack's
  report.** Nothing on a `PackReport` can say whether the OpenTelemetry `TracerProvider` is real —
  `DISCLOSURE` is read before `register()` runs, and `weft-otel` (`02` §4) contributes zero
  registrations by design — so `weft-cli` reads `opentelemetry.trace.get_tracer_provider()` directly,
  after discovery has finished, and prints what it finds: `not configured` (the no-op default; spans
  from every pack call go nowhere) or `configured`, naming whatever set it. It never names `weft-otel`
  by import — a host application embedding `weft` and configuring its own tracing reads the same
  `configured` line.

  > **Built in Phase 5 task 5.2e**, per G9 answer 1 (`docs/09-release.md` §2.3): "Runtime skew...
  > is detected and reported by `weft plugins doctor`, never used to refuse a load." `weft_cli.
  > skew.detect_skew()` compares two independent sources — a distribution's own installed
  > version (`importlib.metadata.version`) against a *different*, already-installed
  > distribution's declared requirement on it (`importlib.metadata.requires`, parsed with
  > `packaging`) — and prints one `version skew` block naming every mismatch it finds, trailing
  > the reports the same way `unconsulted_pins`/`tracing` already do. This lives in `weft-cli`,
  > never the kernel: G9's own words, "the kernel gains zero lines." Task 5.2a's real
  > `>=X,<MAJOR+1` ranges are what make the comparison possible at all — a bare, unconstrained
  > name has nothing for an installed version to disagree with. Deprecation is the same task's
  > second half and needs no line here of its own: `02` §2's status vocabulary already carries it
  > as a flag beside a pack's status, exactly as `ambient` is.

**`weft delete` and `weft reconcile` are G7's (2026-08-21), and they are one idea in two tenses.**
`02` §1 owns the contracts; this section owns what a person types.

- **`weft delete <source-id>`** fans out synchronously across every registered plugin satisfying
  `SourceDeletable` — the node store, and any pack holding data derived from it, such as the graph
  store. Every participant is tried, and one that fails is *named* rather than swallowed: a partial
  deletion the operator does not know about is worse than a refusal. Class `destroy`, so the table
  below already governs it, and the prompt states what will be removed and from how many
  participants.

  > **Built in Phase 5 task 5.1a.** `weft_cli.deletion` is the fan-out, `weft_cli.commands.
  > DeleteCommand` the command around it. Two narrowings this section did not state, both forced
  > by the implementation. **The node store is *selected*, not collected**: `[services] store` has
  > already chosen which store this project writes to, so fanning out across every registered
  > `NodeStore` would connect to a database the operator does not use — every *other* contract
  > contributes every plugin satisfying `SourceDeletable`, which is what makes a graph pack a
  > participant with nothing declared. And the *Permissions* section's own unbuilt
  > `describe_impact` lands here, **optional rather than mandatory** — read off the instance with
  > `getattr`, so no command in this repository or out of it grows a method — which is what lets
  > the prompt name every participant by distribution while the *count* stays honestly
  > unavailable. It also resolves `[services] store` before it says anything about participants,
  > which is a repair rather than a design: see `docs/lessons.md` L5.9.
- **`weft reconcile`** converges what deletion missed. `--mode repair`, the default, drops derived
  state whose source is gone. `--mode full` also **backfills** — building derived state for nodes a
  pipeline indexed without it — and that is the mode nothing ambient may ever choose. `weft
  reconcile` typed by a person defaults to `full`, because someone typing that word means it; the
  automatic pass at the end of `weft index` is always `repair`, and `weft index --reconcile full`
  is how a person opts that run into the expensive one. `weft.toml` sets a personal default and the
  flag always wins.

  > **Built in Phase 5 task 5.1b.** `weft_cli.reconcile` is the fan-out — the same shape and the
  > same failure rule as `weft delete`'s, sharing `weft_cli.fanout` so two walks cannot disagree
  > about who participates. `--dry-run` names the participants and stops. The command declares
  > `destroy`, the stricter of the two classes named above, since `permission_class` holds one
  > value and `network` is the one the table does not gate.
  >
  > **`ReconcileReport.remaining` is what a renderer must not lose.** A pass that was interrupted
  > is a different fact from one that failed, and both are different from one that converged;
  > `weft reconcile` prints all three distinctly and exits non-zero for the first two, because a
  > script reading `0` after an interrupted pass would go on believing the corpus had converged.
  >
  > **Task 5.1c closes the three clauses left above**, and each landed exactly where the note
  > said it would. `weft index` runs `weft_cli.commands.IndexCommand._auto_reconcile` after
  > every successful run, in whichever mode `IndexArgs.reconcile` names — hardcoded to `repair`,
  > never read from `weft.toml`, so an installed pack or a stale config file cannot move an
  > automatic pass into `full` by any route (`docs/02-extension-model.md` §3 → *Slots*, "Tested
  > by G7", is the rule this reads against). `--mode`'s own default moved from a hardcoded `full`
  > to `None` — "no flag given" — so `weft_cli.reconcile_policy.ReconcilePolicy` (`[reconcile]
  > mode` in `weft.toml`, default `full`, unchanged) can supply a personal default for `weft
  > reconcile` typed bare, with the flag always winning when given (`ReconcileCommand.
  > _effective_mode`). And `Reconcilable` gained `estimate(ctx, mode) -> ReconcileEstimate`
  > (`weft-store`, `STORE_CONTRACT_VERSION` `1.4.0` → `2.0.0` — a major, per G9, since an added
  > method is major for an implementer even though it is minor for a caller), asked only when
  > the effective mode is `full` and rendered ahead of every other line — see the worked example
  > below, and `weft_cli.render._render_reconcile`'s own docstring for why "prints before it
  > spends it" is honoured by the order data is computed and rendered rather than by a second,
  > mid-run stdout flush this command's own architecture (a `Command` returns a result; it does
  > not print) does not offer.

**`full` states its cost before it spends it**, because backfill is neither fast nor free:

```
$ weft reconcile
weft-graph: 4,312 nodes have no graph data
            backfill will make ~4,312 model calls
reconciling... 4,312/4,312 ✓  removed 118 orphaned entities
```

It then proceeds, without a prompt. The flag is the consent — and this is deliberate against the
alternative: a confirmation on top of an explicit flag adds no decision, works only on a TTY, and
teaches `--yes` as the scripted spelling, which the table below says disarms the whole thing. What
matters is that the number is *printed before the money is spent*, not that a key is pressed after
it. `--dry-run` prints the same block and stops.

Backfill is `O(corpus)`, cursored and interruptible: `CancelledError` propagates per G6, so a pass
interrupted at 2,000 of 4,312 resumes there rather than starting again. Class `network` for `full`,
`destroy` for `repair` — one command declaring the higher of the two it may reach, per the table
below.

> **Every first-party `Reconcilable` in this tree reports `model_calls=0`, honestly, task
> 5.1c's own worked floor rather than a shortcoming.** `PgVectorStore`, `weft_qdrant.store.
> QdrantStore` and the out-of-tree `examples/weft-example-ingest` all hold only primary node
> data, never derived state a `full` pass would build — see `PgVectorStore.reconcile`'s own
> docstring, which owns the argument for both first-party backends. `pending` still names a
> real number, the tombstone backlog `reconcile` itself converges, so `weft reconcile`'s own
> printed line reads `pgvector (weft-store): 3 source(s) have an unfinished deletion to finish`
> with no second, model-call line — `weft_cli.render._estimate_lines` omits it rather than
> print a vacuous "~0 model calls". The worked example above is `weft-graph`'s, a pack this
> phase does not ship; nothing here can print a nonzero number until one does.

`weft pipeline show` prints the **resolved** form, which after G2 carries more than stages: each
stage's provenance (which pipeline or pack put it there), every var's final value, contributions that
found no slot, and operators that went unapplied because the pack they name is not installed. Those
last two are recorded rather than fatal — see `02` §3, *Slots* — so printing them is the only way
they are visible.

> **`init`, `pipeline list|show|derive|validate|diff` and `config get|set` — built in Phase 3
> task 3.7 (2026-08-20), all eight as registered `Command` plugins through the identical
> single dispatch path every earlier command uses.** `weft_cli.pipeline_commands`/
> `weft_cli.config_commands` are new modules, both called from `weft_cli.commands.register`'s
> one entry point — never a second one.
>
> **`weft pipeline diff` proves its exactness rather than asserting it.**
> `weft_cli.pipeline_diff.diff_resolved` compares two `weft_kernel.resolution.ResolvedPipeline`
> values field by field — stages matched by id, never by position, so an inserted stage reads
> as one addition rather than a shift; a stage present on both sides is compared by `==`, the
> same equality `ResolvedPipeline`'s own docstring already promises across two separate
> `resolve()` calls. No rendered text is ever compared: a text diff would be, in this task's
> own words, "a guess about a guess" — two renderers' opinions about the same fact, not the
> fact itself. `tests/unit/weft_cli/test_pipeline_diff.py` proves it directly: two separate
> resolutions of the identical pipeline diff to `identical=True`, and a pipeline that inserts
> one stage diffs to exactly that one addition and nothing else.
>
> **`weft pipeline show` prints what a pre-G2 `show` structurally could not**, because the
> fields did not exist before task 1.11: `unapplied_operators` and `unplaced_contributions`,
> both printed even when empty (which is every case today — nothing in this tree yet builds a
> slot contribution to populate them; see `weft_cli.pipeline_commands`'s own module docstring
> for that gap, named rather than built ahead of need), alongside every stage's provenance,
> distribution, `applies_to` and final `with:` config, and every var's final merged value.
>
> **`weft pipeline derive` scaffolds the smallest legal derived pipeline** — `name:` and
> `extends:`, nothing else — and stops; an author adds `insert`/`replace`/`remove`/`set` by
> hand, because `weft_cli.argparse_gen`'s own floor (`str`, `int`, `bool`, `StrEnum`, or `|
> None` wrapping one) has no honest way to generate a CLI grammar for four different operator
> shapes. `weft pipeline validate <name>` is the natural next command, and `derive`'s own
> output says so.
>
> **`init`, `pipeline derive` and `config set` were briefly `overwrite`-class, and are
> `write`-class — corrected 2026-08-20, from a review of this task's own landed commit
> (`docs/build-ledger.md`'s dated repair paragraph for tasks 3.3/3.6/3.7 has the argument in
> full).** The table below already places "write a derived pipeline" under `write` (allow),
> and a first `weft init`/`weft pipeline derive` — the case the original "no upsert-safety"
> argument was actually about, since nothing existed yet to lose — refused outright in CI,
> where nothing is a TTY, the first thing a new user or a setup script runs. Scaffolding into
> a project that has nothing yet is a *create*; this table's own `write` row already said so.
> What `overwrite` bought — never silently discarding whatever a target already held — is not
> given up: `init`/`derive` now refuse outright, loudly, naming the path, when the target
> already exists, rather than asking a TTY that CI never has. `config set` reasons from the
> same table differently: it is `write` because the class this table exists for — a prompt
> that states "what will be destroyed and how much of it" — has nothing to say about a single,
> self-named key edit that preserves every other key and comment untouched; see
> `weft_cli.config_commands`'s own module docstring for the argument in full. **A consequence
> of all three moving, stated rather than found by accident**: no first-party command, and no
> out-of-tree example pack in this tree, declares `overwrite`/`destroy` any more, so task 3.3's
> no-TTY/`--yes` machinery is exercised only by hand-registered test doubles
> (`tests/unit/weft_cli/test_cli.py::_WipeCommand`, `tests/unit/weft_cli/test_confirm.py`'s own
> direct unit tests of `gate`) — acceptable, the same position Phase 0 shipped and said so for
> other machinery, but recorded here rather than left to be noticed later.
>
> **`docs/02-extension-model.md` §2's "`weft init`/`weft config get` complete with zero pack
> code executed" is corrected in this same commit.** That claim predates task 3.2's
> registry-driven parser: every subcommand's own grammar, `init`'s and `config get`'s
> included, now needs the whole registry built to be recognised as a valid subcommand at all,
> so discovery already runs before any command's own body executes. `weft --version` remains
> the one categorically pack-code-free command — it alone never reaches the registry-driven
> parser — proven by the same, unweakened subprocess test fitness function 8(b) always has.
>
> **`weft ask <question>` above is task 3.11's own answer, and it is already what this table
> says.** Task 2.8 built the router but shipped it behind a second, additive command, `weft
> route`, leaving Phase 0's own `weft ask` retrieve-only and untouched — a deferral this table
> never caught up with: it kept saying *"query, streaming the answer with citations"* the whole
> time, describing a command that did not yet do that. Task 3.11 makes the table true: `weft ask`
> now routes through the installed router by default and there is no `weft route` — a caller
> never has to know a second command exists. **`weft ask <question> --pipeline <name>`** is what
> a caller who wants a *specific* pipeline uses instead of the router's own choice, resolved
> against the same catalogue `weft pipeline show` resolves names against
> (`weft_cli.pipeline_catalogue.full_catalogue` — project-local documents and every installed
> pack's own contribution, deliberately wider than the router's own `route.yaml`-only search
> set, so a pipeline scaffolded by `weft pipeline derive` and never published as a pack is
> reachable). **`weft ask <question> --retrieve-only`** is Phase 0's own contract, kept
> reachable rather than deleted: `manual/quickstart.md`'s zero-configuration walkthrough and
> `eval/run_baseline.py`'s V3 baseline (`09` §4.3) both need a deterministic, credential-free,
> network-free measurement, which routed generation cannot offer once a real model is involved
> — a `weft.toml` naming no `[llm.roles]` maps nothing (`weft_llm.roles.LLMRoles`'s own "no
> silent default" clause), so the routed default refuses loudly rather than guessing at a
> provider. `--retrieve-only` and `--pipeline` are mutually exclusive, refused together before
> either resolves a plugin. **No reference precedent existed to weigh either way**: every reference CLI
> path that builds an engine config disables its own router explicitly
> (`RouterConfig(enabled=False, ...)`, `generation/chat.py:99` and `:270`), and its
> `retrieval/query_tools.py` exposes only named-strategy subcommands (`hyde`, `stepback`,
> `compare`) — a user has to already know the strategy name, precisely the gap this task closes.
>
> **The double-print `weft route` inherited is fixed in the same commit, reusing the shape of
> an existing repair rather than a second mechanism for the same class of problem.** Task 3.6's
> own report flagged it: a routed answer's text printed twice — once live through
> `PrintingSink`/`JsonSink` as the generating stage streamed it, once more in full after the run
> finished. The 2026-08-20 repair to a *different* double-print (a permission refusal, shown
> once by the renderer and once by the sink's own failure path) had already established the
> right shape — decide from a fact about whether this run's own sink actually showed
> something — but not the right *fact*: that repair's `_EmissionTrackingSink.emitted` is set by
> *any* role's chunk, the router's own `role="route"` scoring call included, so reusing it
> unchanged would suppress the answer even when nothing visible ever streamed. The fix is a
> second, role-aware fact the sink itself is uniquely positioned to know —
> `weft_cli.sinks.PrintingSink`/`JsonSink` grew a public `wrote_anything`, true only for a chunk
> `_visible` already decided a reader would see — read via `getattr(deps.token_sink,
> "wrote_anything", False)` off the *real* sink in `weft_cli.cli.run_command`, so `NullSink`
> (`--quiet`, no such attribute) always answers "nothing streamed" and still gets the full text,
> holding G6's "`--quiet` suppresses progress but keeps the result." Threaded into
> `weft_cli.render.render_outcome`'s new `streamed` keyword, read only by `_render_ask`.

> **`weft eval run|compare` and `weft trace`, task 4.6 (2026-08-20) — and `weft trace
> [<run-id>]` above is narrowed to `weft trace <run-id>`, argued rather than left to drift
> silently from what shipped.** Q2 — *what does `weft trace` read: the persisted run record
> task 4.4 built, or exported OTel spans?* — is settled: **the record.** `01` → *The kernel
> boundary* fixes exporting a span as pack work, Phase 4 ships no exporter pack (task 4.5's
> own finding: the seam already emits everything a future exporter would need, for free, the
> instant one exists), and reading spans would mean shipping one as a second, unbudgeted
> artefact. The cost of that answer is this promise: *"replay what a run actually did"* fits a
> span-level replay — which stage, how long, why it failed — far better than it fits four
> static facts, so it is narrowed rather than kept and quietly under-delivered: `weft trace`
> prints exactly what `weft_eval.run_record.RunRecord` carries (resolved pipeline, corpus,
> model versions, active distributions), nothing about per-stage timing or attribution.
> `<run-id>` loses its brackets for a mechanical reason, not a design one: `weft_cli.
> argparse_gen`'s own floor has no shape for an *optional* positional (a defaulted field
> becomes a flag, never one), and a bare `weft trace` process has no session and no "last
> run" the way the REPL's own `/trace` does to fall back to — see `weft_cli.eval_commands`'s
> own module docstring for the argument in full.
>
> **`weft eval run <path> <pipeline>` makes `pipeline` a second required positional, never
> `weft index`'s optional `--pipeline` flag** — a run record's `resolved_pipeline` field is
> mandatory, and only a *named* document produces one (task 4.0's own reason to exist), so
> there is no default to make it optional from. `weft eval compare <a> <b>` refuses outright,
> naming which facts differ, when the two runs' corpus, model versions or active
> distributions disagree — `09-release.md` §4's V3 failure clause ("a baseline from a
> different corpus, pipeline or model version") enforced at the CLI seam, before a pipeline
> diff is ever computed, rather than left for a reader to misattribute a number later.
>
> **Permission classes**: `eval run` is `write` (it indexes a corpus and writes a run
> record — `docs/03-cli.md`'s own `write`-row example, "index into a new collection");
> `eval compare`/`trace` are `read` (both only load files already on disk). Neither
> `overwrite` nor `destroy` fits any of the three — a run id is a fresh `uuid4` every call,
> so `eval run` has nothing an invocation could ever collide with to ask a TTY about, and
> `eval compare`/`trace` write nothing at all — holding the same "no first-party command is
> `overwrite`/`destroy`-class" property this document's own *Permissions* section already
> records after the 2026-08-20 repair.
>
> **A repair found by running the binary, not by the 1,616 tests this task's own gate ran
> green first.** `weft eval run corpus specific` — `specific` a `weft pipeline derive`d
> child of `index` — failed `UnknownParentPipelineError` outright, unconditionally: `weft_cli.
> ingest._specs_from_document` (task 4.0) and `weft_cli.route_ask._run_pipeline` (task 2.8)
> both called `resolve()`/`contracts_for()` with `parents={document.name: document}` — a
> one-entry mapping holding only the named document itself, with no ancestor for `extends:`
> to find — rather than the full catalogue `weft_cli.pipeline_commands._resolved_or_refuse`
> (task 3.7) already passes correctly. Neither task's own tests ever exercised `extends:`
> through either path, so nothing caught it until a real corpus was run through a real
> derived pipeline — precisely 4.9's own exit shape, and precisely why this task built one to
> check. Fixed in both places, in this commit: `weft ask --pipeline <derived-name>` and
> `weft index --pipeline <derived-name>` (already true before this task, silently broken)
> resolve derived pipelines correctly now too, not only `weft eval run`.

## In-session commands

Slash commands inside the REPL, matching the mental model of the CLI:

```
/help                    /pipeline [name]       show or set the active pipeline
/plugins                 /trace                 show the last command this session ran
/eval                    /session                print the session's own state
/clear                   /exit
```

The session carries state a one-shot invocation does not: the active pipeline, the collection,
conversation history, and the last run's trace. That state is explicit and inspectable — `/session`
prints it — because implicit session state is how a tool starts behaving differently for two people
running the same command.

> **Built in Phase 3 task 3.4 (2026-08-19), three of eight — the rest named as deferred rather
> than shipped as stubs.** `/help` (reads the same registry walk `--help` is generated from) and
> `/exit` ship because neither is *about* session state; `/plugins` ships as a slash **alias**
> for the already-registered `plugins list` `Command` — it builds the identical `args`
> `weft plugins list` would and calls `weft_cli.cli.run_command`, proof that a slash command need
> not be a second implementation of anything. `/clear`, `/pipeline` and `/trace` are each about
> session state this task does not build — conversation history, the active pipeline, the last
> run's trace — and are task **3.5**'s. `/config` needs `weft config get/set`, task **3.7**'s own
> command surface. `/eval` has no owner yet: no `weft eval` command is registered anywhere in this
> repository. Typing any of the five at the prompt names its own reason rather than doing nothing
> or crashing — `weft_cli.repl`'s own module docstring carries the full list.
>
> **Corrected by task 4.6 (2026-08-20): `/eval` has an owner now, and this paragraph's own
> last sentence stopped being true the moment it landed.** `weft eval run|compare` is
> registered; see the blockquote at the end of this section for the resolution in full.

> **Built in Phase 3 task 3.5 (2026-08-19), four more of the original eight, plus a ninth this
> task adds.** `/pipeline [name]`, `/trace` and `/clear` are `weft_cli.session.SessionState` made
> real — a frozen model replaced wholesale each turn (`with_active_pipeline`, `with_turn_recorded`,
> `cleared`), never mutated in place. `/pipeline` with no argument shows the session's
> `active_pipeline`, with one it sets it — held and printed as a bare, unvalidated name, since no
> `weft pipeline` command surface exists yet to resolve it against (task **3.7**'s own). `/trace`
> prints the `TurnTrace` the session's last actual `run_command` call attached — the resolved
> command name, the verbatim line typed, and its exit code — or says plainly that nothing has run
> yet; a slash command that only inspects or changes the session itself (`/help`, `/pipeline`,
> `/clear`, `/session`) does not count as a run. `/clear` resets both back to a blank session.
> **`/config` does not print session state, and this section is corrected to stop saying it
> does.** The sentence above naming `/config` predates task 3.4's own deferral of `/config` to
> task **3.7**'s *project* configuration surface (`weft config get/set`, `weft.toml`) — two
> different questions sharing one name by accident of when each sentence was written: `weft.toml`
> is read once at startup, a session's own state changes every turn. This task gives the session
> its own command instead, **`/session`** — not one of the original eight — printing every value
> `SessionState` carries, nothing more and nothing less: `active_pipeline`, the last `TurnTrace`,
> and an explicit line stating conversation history is not tracked, rather than a field silently
> missing from the printout. **The collection and conversation history — the other two of the
> four named above — are deferred, argued rather than defaulted past**
> (`weft_cli.session`'s own module docstring carries both in full): no command in this repository
> accepts a collection argument for a session to hold a choice of, and no contract reads a prior
> turn back into a later one (`weft_cli.commands.AskArgs`/`RouteArgs` take no history field), so
> building either now would be exactly the shape the reference's own `_run_chat_loop`
> (`generation/chat.py:353`, `.phase3-design.md` §2.5) is a warning against — a `chat_history`
> parameter that always passed `[]`, state that *looks* consulted by generation and is not. This
> task refuses to reproduce that failure in the opposite direction: state a session holds that
> nothing ever reads back is the identical defect the other way round.

> **`/config`, shipped task 3.7 — a `run_command` alias for `weft config get`, `/plugins`'s
> own pattern proven a second time.** `/config` with no argument is `config get` with no
> `--key`; `/config <key>` forwards `<key>` as `--key`. It prints the *project's* effective
> `weft.toml`, never the session's own state — `/session` above still owns that.

> **`/eval`, task 4.6 — registered, and still deferred as a slash alias, for a different
> reason than before.** `weft eval run`/`weft eval compare`/`weft trace` are registered
> `Command`s now (`weft_cli.eval_commands`), and a bare, non-slash line already reaches them
> inside this session — `eval run <path> <pipeline>`, `eval compare <a> <b>` and `trace
> <run-id>` all resolve against the identical registry-driven grammar every other command
> here does, with nothing in `weft_cli.repl` to change. What is still missing is the slash
> **alias**: `/plugins` and `/config` each alias to one command with at most one bare
> argument; `/eval` would have to multiplex between two verbs that each need two required
> positional arguments of their own, which is genuinely more than either precedent's own
> one-line `parser.parse_args([...])` call — named as a small, separable, still-unbuilt piece
> of REPL-layer work rather than invented mid-task. Typing `/eval` at the prompt says exactly
> this, not "not shipped" — `weft_cli.repl._DEFERRED_SLASH_COMMANDS["eval"]` carries the text.

> **`weft eval metrics [--name <name>]`, task 4.7 (2026-08-20) — V5's "the offline subset must be
> identifiable as a subset."** `read`-class, registered exactly like every other built-in: it
> reads `weft_eval.offline.gate_subset` off the registry already built at process start and
> renders which registered `GenerationMetric`/`RetrievalMetric` names run with no credentials,
> no network and no model download, and which do not. Given `<name>`, it asks the narrower
> question instead — `weft_eval.offline.require_gate_safe` — and **refuses**, naming why and
> what would permit it, for a metric that cannot run there, rather than answering with an empty
> or degraded result: `weft eval metrics --name faithfulness` against a project with no `[llm.roles]`
> configured prints `'faithfulness' cannot run in the deterministic, gate-safe subset: needs a
> real judge model behind '[llm.roles]' — the deterministic 'scripted' provider resolves the
> service but cannot produce a usable structured judgement...` and exits `1`
> (`weft_eval.offline.MetricNeedsCredentialsError`, `OPERATION_FAILED` — the metric name was
> valid, so this is "something failed", never FF12's "fix what you typed"). `weft eval run`'s
> own output also grew a line this task added: `wall clock: <seconds>s`, measured around the
> real work `run_index` does, and its persisted record's `model_versions` is no longer always
> `{}` — derived from each resolved stage's own `config`, generically, wherever a stage's plugin
> declares a `model` field.
>
> **`weft eval run --questions <file> [--top-k <n>]`, task 4.9 (2026-08-20) — closes
> `.phase4-design.md` §7's gap: a persisted `RunRecord` carried no metric scores, so `weft eval
> compare` could only report that two runs' pipelines *differ*, never what they *produced*.**
> `--questions` names a JSON file of `{"query": ..., "relevant_documents": [...]}` judgements;
> given one, `weft eval run` retrieves for every question through the resolved pipeline's own
> `Embedder`/`NodeStore` stages (never `[services]` — Q3, task 4.0, still holds for a named
> pipeline) and scores the gate-safe `RetrievalMetric` subset over the result
> (`weft_eval.harness.score_retrieval_gate_subset`), folding it into `RunRecord.metrics`. Omitted,
> `metrics` stays `{}`, the same honesty `model_versions` had before task 4.7. `weft eval compare`
> now also prints `metrics_comparison`: every metric name either run scored, paired side by side
> with a signed delta when both runs scored it, and an honest "not measured for this run" on
> whichever side did not — never silence, and never a fabricated number. `weft trace` grew a
> matching `metrics:` block, since it prints exactly what the record carries.

## Plugin-contributed commands

A pack registers commands against the `Command` contract exactly as it registers a retriever. They
appear in `weft --help`, in REPL completion, and in `weft plugins info`, namespaced under the pack:

```
weft graph build
weft graph show --entity "Acme"
```

Core has no list of commands to edit. The help text is generated from the registry, which means it
cannot drift from what is installed — the same property that makes the plugin model work applied to
the CLI's own surface.

> **REPL completion, built in Phase 3 task 3.4 (2026-08-19).** `weft_cli.repl.repl_completions
> (registry, prefix)` walks the identical `Registry.names_for(Command)` `build_parser` and
> `--help` already read, so a stranger's registered command appears in completion the moment it
> registers — no second list. Wired into a real session through Python's `readline`, best-effort
> (`ImportError`-guarded, since not every platform ships it). This is the *mechanism*; task
> **3.8** is the automated proof that a real installed stranger's command actually shows up here.

> **Proven automatically, task 3.8 (2026-08-20), repaired 2026-08-20 — this is Phase 3's own
> exit criterion.** `tests/architecture/test_phase3_exit_command_surface.py` installs
> `weft-example-command` (task 3.2's stranger) into a throwaway environment built from real
> wheels, with this repository nowhere on `sys.path`, and shows all three claims hold against
> the installed binary rather than against an in-process Python call: **bare `weft --help`** — a
> real subprocess, the exit criterion's own words, no command named — lists the plugin's own
> registered name and declared `help` text among every other command's, generated by
> `weft_cli.cli.build_parser` from the registry (`weft_cli.cli.wants_help` is what keeps a lone
> `-h`/`--help` out of the session two sections up, rather than the session claiming it as this
> document used to say — see that section's own corrected blockquote); the per-command leaf form,
> `weft <name> --help`, is kept as a second, additional assertion of the same mechanism.
> `repl_completions`, called from inside the same venv against the real, installed
> `weft_cli.registry_bootstrap.build_dependencies`, includes it; and no file under `packages/`
> names its distribution, module or plugin name. Uninstalling the pack and re-running every probe
> against the identical venv breaks all of them, so the property is shown to depend on the pack
> being installed, not on the test's own fixed transcript.

> **How a pack's result becomes text — G13, settled 2026-08-22.** The rule at the top of this
> document says a `Command` returns a typed result and a renderer formats it. Phase 5's independence
> test found the second half was first-party only: `weft_cli.render._RENDERERS` is a table matched on
> the CLI's own result types, so `weft example-graph show` printed `{"nodes_with_graph_data":11,...}`
> at a person while eighteen built-in commands printed for one. **A renderer is registered, at the
> same seam a command is** — `registrar.add_renderer(ResultType, renderer)`, with `Rendered` published
> from `weft-command` beside the `Command` contract that produces the result, since a result type
> nobody outside the CLI can format is only half a contract. **The CLI's own renderers move onto that
> call in the same change**, so the dispatch has one path and built-ins take the public one —
> requirement 4 checked at runtime rather than asserted. A result with no registered renderer still
> falls through to the honest structured dump; that stays the floor, and stops being the ceiling.
> `COMMAND_CONTRACT_VERSION` moves under G9's two-audience rule, and `03`'s rule finally holds for
> everyone rather than for the eighteen commands this repository happens to ship. Ledger task
> **6.20**.
>
> **Built at task 6.20 (2026-08-22).** `weft_kernel.discovery.PackRegistrar.add_renderer` buffers a
> `(result type, renderer)` pair exactly as `add_ext_model` buffers a class — **the kernel names
> neither `CommandResult` nor `Rendered`**, it remembers that a pack offered some type and some
> callable and goes no further. `weft_cli.render._RENDERERS` is **deleted**, and
> `weft_cli.render.register_renderers` makes one `add_renderer` call per built-in result type from
> inside `weft-cli`'s own `register()`, so the eighteen built-ins reach the dispatch by the same
> road a stranger's pack does; `register_renderers_from_reports` is the consumer, modelled on
> `weft_store.rehydrate.register_from_reports` — idempotent for a repeat of the same fact, and
> refusing two different renderers for one result type by naming both distributions.
> `COMMAND_CONTRACT_VERSION` went to **`2.1.0`**, not a major: under G9's two-audience rule this is
> additive for a caller *and* additive for an implementer — nothing on `Command` changed,
> `required_declarations` is untouched, and a pack registering no renderer still works because the
> structured dump is the floor. `ExitCode` moved with `Rendered`, because a renderer that cannot say
> the run failed is a renderer a built-in could not have used.

## Permissions

Destructive operations ask before acting. The classes are named, not guessed per command:

| Class | Examples | Default |
|---|---|---|
| `read` | ask, show, list, diff, trace | allow |
| `write` | index into a new collection, write a derived pipeline | allow |
| `overwrite` | reindex an existing collection, replace a pipeline file | **ask** |
| `destroy` | drop a collection, delete blobs, purge a cache | **ask** |
| `network` | call a remote model, download a model | allow, configurable |

Rules that matter more than the table:

- **Non-interactive means non-guessing.** With no TTY, an `ask` operation **fails** with a message
  naming the flag that would permit it. It never proceeds silently. A pipeline that quietly drops a
  production collection because it could not prompt is the failure this prevents.
- `--yes` permits `ask` classes for one invocation. Per-class defaults live in `weft.toml`.
- The prompt states **what will be destroyed and how much of it** — collection name and document
  count — not just "are you sure?".

**A plugin-contributed command must declare its class, and there is no default** (G3). The class is a
`ClassVar` on the `Command` contract, read at registration alongside `lifetime`, `requires` and
`provides`; a command that declares none fails to register, loudly, while its author is standing
right there. No default is safe: `read` silently under-protects, and `destroy` trains people to pass
`--yes` reflexively, which disarms the whole table. `weft graph build` rebuilding a graph belongs in
`overwrite` exactly as a core command would, and the machinery makes that a registration-time fact
rather than something an author remembers.

**These classes protect you from the tool, not from a pack.** A dishonest pack can declare `read` and
delete your collection; nothing here prevents it, and nothing can — see `02` §2, *The trust model*,
for why in-process enforcement is unavailable and what weft does instead. The class exists so that an
*honest* pack participates in the same safety contract as core.

> **Built in Phase 3 task 3.3 (2026-08-19), and narrower than the paragraph above in one
> respect, stated rather than pretended past.** `weft_cli.confirm.gate` is the invocation seam —
> called from `weft_cli.cli.run_command` immediately before any registered `Command` runs, so a
> pack's `overwrite`/`destroy` command is refused with no cooperation from its own author, exactly
> as *"the machinery makes that a registration-time fact"* says of `permission_class` itself. The
> no-TTY refusal and `--yes` land exactly as specified, proven by `tests/unit/weft_cli/
> test_confirm.py` and `test_cli.py` with `is_interactive`/`read_confirmation` monkeypatched so
> both branches are provable in CI, which is never a TTY. `--yes` is spelled `weft <command> ...
> --yes` — declared once, on the leaf subparser a command's own name resolves to, never on the
> top-level parser too: `argparse`'s subparsers copy a fresh sub-namespace over the shared one on
> every dispatch, so a same-named flag declared on both levels would silently lose a
> `weft --yes <command>` spelling back to its subparser default (`weft_cli.cli`'s own module
> docstring has the mechanics). **The prompt does not yet carry a collection name or a document
> count.** Stating a count means the command has already looked, which the generic seam cannot do
> without either partially running the command early or a `Command.describe_impact`-style
> contract method every registered command — none of which declares `overwrite`/`destroy` today —
> would have to implement for a need nothing yet has. What it states instead: the command's own
> registered name and its already-validated, already-typed arguments, e.g. `'graph destroy' is a
> destroy-class command, called with {'collection': 'reports'}.` — genuinely more than "are you
> sure?", honestly less than a document count. Left to whichever later task first ships a real
> `overwrite`/`destroy` command and needs one — `weft_cli.confirm`'s own module docstring records
> the reasoning in full. Per-class defaults in `weft.toml` are `[permissions]`
> (`weft_cli.permission_policy`), and cover only `overwrite`/`destroy` — the two classes anything
> here gates at all — with an unknown key refused, naming `overwrite` and `destroy` as the keys
> that exist, per *Project context* below.

> **Task 3.7 briefly gave this machinery its first genuine `overwrite`-class commands, and the
> 2026-08-20 repair took them back** — `init`, `pipeline derive` and `config set` are
> `write`-class instead (see the *Command surface* section above for the argument in full).
> `test_cli.py`'s own hand-registered double (`_WipeCommand`) remains the only thing proving
> the no-TTY refusal and `--yes` in this tree, exactly as it was before this task, which is
> `docs/build-ledger.md`'s own recorded consequence, not an oversight. The `describe_impact`
> gap above is still real and still unowned regardless of which command class first needs it.

> **Task 5.1c does not move `weft reconcile`'s permission class, and says so rather than
> leaving a reader to wonder why not.** *Command surface* above already argues it: `full`
> proceeding "without a prompt" is about not inventing a *second* confirmation on top of the
> existing `--yes`/no-TTY gate, never about weakening that gate itself — `full`, exactly like
> `repair`, still refuses with no TTY and still honours `[permissions] destroy`. What `full`
> adds is informational, printed as part of the command's own typed result (`ReconcileCommandResult.
> estimates`) rather than a `Command.describe_impact` sentence: `describe_impact` is only ever
> read when the gate is about to ask a question (`weft_cli.confirm.impact_of` is never called
> once `--yes`/`[permissions] destroy = "allow"` already permits the run), and 03's own worked
> example prints the cost block on every `full` invocation, `--yes` included — so the cost
> could not live there without silently vanishing on exactly the scripted path an operator
> running backfill in CI is most likely to take.

## Output

Human output streams: tokens as they generate, stage progress while indexing, citations resolved at
the end. Rendered, coloured, and aware of terminal width.

**How the tokens get here** (G6): the CLI registers a `TokenSink` implementation, and the generating
stage resolves it through the passport and emits into it. There is no streaming variant of any
contract — `--json` swaps the sink for one that writes newline-delimited events, `--quiet` swaps it
for a no-op, and the pipeline is identical in all three cases. The CLI is also where the library's
**only** `asyncio.run` lives, in the entry point; nothing under `weft-kernel` or any pack contains
one, which fitness function 7 asserts by path.

`--json` switches to newline-delimited JSON events and disables every decoration, including
spinners and colour. That is the scripting contract: same events, no parsing of prose. `--quiet`
suppresses progress but keeps the result.

> **Built in Phase 3 task 3.6 (2026-08-20).** `weft_cli.sinks.PrintingSink` is the default
> `TokenSink` — writes a chunk's text to the terminal the instant it arrives, unbuffered, then a
> single newline on `close()`; `weft_cli.sinks.JsonSink` is `--json`'s own, one `StreamEvent` per
> line; `--quiet` reuses `weft_llm.client.NullSink` unchanged, since a sink that discards is
> already what `--quiet` needs. `weft_cli.cli.global_output_flags` recognises both **before** the
> subcommand (`weft --json ask ...`, never `weft ask --json ...`) — the opposite side from `--yes`,
> because these are genuinely top-level flags, never a per-command choice — and `weft_cli.cli.main`
> chooses the sink from them before `build_dependencies` runs, so it is already on
> `Dependencies.token_sink` the moment a `Command` can read it. A flags-only invocation
> (`weft --json`, no subcommand) now enters the interactive session with that sink already
> selected: `main`'s REPL-entry test changed from "argv is empty" to "no command was named",
> which is what it always meant. `weft_cli.commands.RouteCommand` (retired into `AskCommand` at
> task 3.11, below) — the only built-in that streams today — reads `Dependencies.token_sink` and
> threads it through `weft_cli.route_ask.run_routed_ask`
> to `weft_cli.run_services.build_services`, which now takes the sink as a required argument rather
> than hardcoding `NullSink()`. **The event vocabulary is three members** — `CHUNK`, `DONE`,
> `ERROR` — not the seven a taxonomy in the reference's own engine carries; the other four have nothing
> in this tree that would emit them yet, named as gaps rather than built ahead of need. **An error
> can never be mistaken for a clean end**: `TokenSink.close(reason=...)` is the one signal, and
> `JsonSink` turns `reason=None` into a `DONE` event and any other `reason` into a structurally
> different `ERROR` event carrying it — never a worded difference a consumer would have to
> string-match, which is exactly the reference shape this sink refuses to reproduce. `weft_cli.cli.
> run_command` closes the run's sink exactly once, on every exit — success, a caught `WeftError`,
> or an uncaught exception including `CancelledError`, which still propagates untouched (G6); see
> that function's own docstring and task 3.6's ledger entry for the full argument, including why
> nothing about the REPL's own `read_line`/`weft_extract.accept`'s filesystem walk needed to
> become async to ship this (O2, `.phase3-design.md` §4).

> **Built in Phase 3 task 3.10 (2026-08-20), the phase's one reference lift.** `close(reason=...)`
> gained its first real caller on a *non-crash* path: `weft_llm.loop_guard.detect_generation_loop`
> watches the answer accumulate inside `weft_llm.client.LLMClient.complete` and, on a small model
> settling into a repeating span, raises `LLMGenerationLoopError` rather than letting the stream run
> on — a markdown table is checked for and excluded first, so legitimately repetitive rows are never
> mistaken for one. `run_command`'s existing "a caught `WeftError` closes with `reason=str(exc)`"
> branch (above) is what turns the raise into the sink's own `[stream error: ...]` line — no new
> branch needed here, which is itself evidence O1/O2's design already generalised correctly.
> `[llm.loop_guard]` in `weft.toml` parameterises every threshold; see
> `manual/operations-guide.md` → *Stopping a model stuck in a loop*. This is a loop-breaker for a
> model that got stuck, never hallucination detection — `01` → Phase 3 **Lift**'s naming rule.

Exit codes are meaningful, because a CLI that always exits 0 cannot be used in CI: `0` success,
`1` operation failed, `2` bad usage, `3` refused for permissions, `4` pipeline failed to resolve.

`3` covers **policy** refusals of both kinds — an `ask` operation with no TTY, and a pipeline naming a
plugin from a pack an allow-list refused (G3). `4` stays with genuine resolution failure: a name no
pack provides, or one lost to a `failed` or `partial` registration. The split is what lets a CI job
tell *"fix the environment"* from *"fix the pipeline"*.

> **Narrowed in Phase 1 task 1.13 (2026-08-17).** The mapping from a caught exception to one of
> these five codes is one function, `weft_cli.exit_codes.exit_code_for`, not two hand-written
> `except` chains inside `handle_index` and `handle_ask` as it was before this task — `02` §3 →
> *When resolution fails*: "The CLI maps the whole family to exit code 4." `4` is every
> `weft_kernel.runner.PipelineResolutionError` subclass (checked by `isinstance`, so a subclass
> added after this function was written still matches with nothing to update here), plus three
> names that are deliberately *not* in that family and would otherwise fall to `1`:
> `weft_kernel.registry.UnknownPluginError` (a name no pack provides — already stated above) and
> `weft_cli.pipeline_catalogue`'s own `PipelineDocumentError` / `MalformedPipelineError` /
> `DuplicatePipelineNameError` — a pipeline *document* that will not even parse or validate is
> exactly "fix the pipeline", task 1.9's own reasoning for keeping that family out of
> `PipelineResolutionError` in the first place. Every other `WeftError` still maps to `1`. This is
> a narrowing of where the mapping is decided, not of what it decides: `weft index`/`weft ask`
> exit exactly as they did before this task: nothing in Phase 0's CLI opens a pipeline document
> yet, so the three `pipeline_catalogue` names are proven correct without being reachable —
> `tests/unit/weft_cli/test_exit_codes.py` is where that proof lives until a real command reaches
> them.

> **One exception carries its own code, since task 3.2 (2026-08-19), and it is a stated
> exception to "one function."** `weft_cli.commands.CommandRefusalError` is what a built-in
> `Command` raises for the two refusals `weft_cli.registry_bootstrap.require_active`/
> `require_plugin` already computed — `3` for a distribution `[packs] allow` refuses, `4` for a
> name that is simply unregistered — and it carries that `ExitCode` as data rather than going
> through `exit_code_for`. It has to: `Command.run` cannot return an `ExitCode` (only an
> `Outcome[CommandResult]`, per *Two modes, one implementation* above), and the contract must
> not learn a weft-cli-specific enum any more than it already knows `weft_cli` at all — the
> identical reasoning that keeps `weft_kernel` from knowing `Command`. `weft_cli.render.
> render_refusal` reads `.exit_code` off it directly; every other caught `WeftError` still goes
> through `exit_code_for`, unchanged. The messages and codes themselves are unchanged from
> before this task — only the vehicle carrying them from "computed" to "printed" moved from a
> return value to an exception, because `run()` cannot print.

> **Built in Phase 5 task 5.2d (2026-08-22).** G9's ruling (`docs/README.md` decision log; `S6`)
> made CLI error prose unpromised only in exchange for a structured channel that did not yet
> exist: `weft_cli.render.render_refusal` returned `str(exc)` on every failure path, `--json`
> included, so of the 78 `valid_options` sites `weft-cli`'s own raise sites compute
> (`weft_kernel.errors.UnresolvedNameError`, fitness function 12), **none reached a script
> except as a sentence**. `weft_cli.error_envelope.ErrorEnvelope` is that channel: `error` (the
> `WeftError` subclass name — the identity `manual/troubleshooting.md`'s own coverage ratchet
> already enumerates by this exact string), `rendered` (`str(exc)`, whole — prose stays
> unpromised, not unavailable, and unabridged so a remedy stays a person's judgement, `09` §3's
> own argument), `exit_code`, `valid_options` (`None` where the error has none, never omitted),
> and `pack`/`contract`/`plugin`/`stage` — `weft_kernel.seam.wrap`'s own attribution, carried
> through rather than re-derived. `envelope_version` travels in the data, a plain field with a
> default rather than a `ClassVar`, on the identical principle task 5.2c's `ExtModel.
> __schema_version__` settled for a persisted schema (`02` §1's S5 rule, pointed at a wire
> format instead): additive only, never frozen, `09` §3's own git `--porcelain=v1` warning is
> why. **The flag is the global `--json`, not `ask`'s own `--format json`** — `weft_cli.render.
> render_refusal` grew a keyword-only `as_json`, and both of this tree's `WeftError`-catching
> sites decide it from the identical fact `docs/03-cli.md` already uses to pick the run's
> `TokenSink`: `weft_cli.cli.run_command` from `isinstance(deps.token_sink, JsonSink)`, and
> `weft_cli.cli.main`'s own discovery-failure catch (before a `Command` is even chosen, so
> `render_refusal`'s `CommandRefusalError` branch could never apply there) from `json_flag`
> directly. `--format json` stays what it always was — one command's own finished-result shape,
> `weft ask`'s alone — and is untouched by this task. The envelope replaces nothing on the
> human path: `as_json=False`, the default, is byte-identical to before.

**Score display.** A retrieval result carries `Scored.score` — a similarity, never guaranteed to fall
in `[0, 1]` (`02` §1: "the score lives on `Scored[Node]`, not on `Node`"; nothing in that contract
bounds the float). `weft-store`'s own pgvector implementation computes it as `1 - cosine distance`,
which is correctly negative whenever two vectors point more away from each other than towards —
routine with Phase 0's deterministic hash embedder, which carries no semantic meaning to make nearby
questions land in the same half of the vector space. Ranking by it is still exactly right: higher is
closer, first is best. Printing that raw float to a human reader with no bound and no baseline reads
as an error rather than a working feature — `1. (score=-0.0913) …` looks broken even when it is not.
Human-rendered `ask` output therefore prints **rank order only** (`1.`, `2.`, …), never the raw score;
a programmatic caller still gets the exact value through the library return type, `Scored[Node].score`,
completely unrendered — the CLI summarizes for a person, it does not redefine what the store returned.
This is a CLI rendering choice, not a store or contract change: a future `--json` output (not built in
Phase 0) carries the raw score in its event, because a script consuming structured output is exactly
the reader who can use an unbounded float correctly.

> **`weft ask --format json` landed in Phase 2 task 2.3 (2026-08-17).** The paragraph above
> anticipated it; what it did not settle is the spelling, and the two are deliberately different
> things. `--json` above is a **global** flag that swaps the token *sink* for one writing
> newline-delimited events while a pipeline runs — Phase 3's shape, unchanged. `--format` is one
> command choosing what its finished result looks like: `text` ranks the passages for a person,
> `json` emits a single line carrying each passage's node id, its `lineage.sources` and the raw
> score this section withholds from a human. It exists because prerequisite V3 (`09` §4.3) is
> measured **through the shipped command** — fitness function 7(a) permits no second `asyncio.run`,
> so `eval/run_baseline.py` drives `weft` as a subprocess and has to read what it printed. The
> enum lives in `weft_cli.output`, away from `weft_cli.ask`, because `build_parser` runs for
> `weft --version` too and that command may execute no pack code (fitness function 8(b)).

## Project context

`weft.toml` at the project root holds the default pipeline, collection, model profile and
permission defaults, so day-to-day commands take no flags. Explicit flags beat the file, and the
file beats built-in defaults. `weft config get --origin` prints where each effective value came
from, which is the question people actually have.

**`[services]` is where the model profile starts** (Phase 2 task 2.29). It maps a role a command
needs to the name of a registered plugin — `embed = "openai"` today, `store` and an `llm` as the
tasks that build them land — and it is the whole operation for changing which embedder a corpus is
indexed with: no package edited, nothing reinstalled, and a plugin from a pack nobody here wrote is
selectable the moment it is installed. A key the CLI does not yet read is **refused**, naming the
keys it does, rather than accepted and ignored: a service Weft did not actually select is one an
operator would have to notice by the answers being wrong. The defaults are the offline ones, so a
checkout with no `weft.toml` at all needs no credential and no network.

**A name from this block is gated before the command runs, and the gate cannot be a list of
distributions** — `weft_cli.registry_bootstrap.require_plugin`, a repair for a reviewer finding
against 2.29. Once the plugin name comes from an operator's file, the pack behind it may be
`weft-openai` or a stranger's, so the check is on the *name*: unresolvable with some pack
`refused` exits **3** naming `[packs] allow`; unresolvable with a pack `failed` or `partial`
exits **4** with that pack's reason attached; unresolvable with nothing amiss exits **4** listing
every name the contract does have. `02` → *The trust model* requires all three, and a hard-coded
tuple of first-party distribution names could satisfy none of them for a third-party pack.

**`[permissions]` is the *"permission defaults"* named above** (task 3.3). Two keys,
`overwrite` and `destroy` — the only classes *Permissions* defaults to `ask` — each `"ask"`
(the built-in default, so a `weft.toml` naming neither key behaves exactly as one with no
`[permissions]` table at all) or `"allow"` (an operator's override, equivalent to always passing
`--yes` for that class). An unknown key is refused, naming `overwrite` and `destroy` as the keys
that exist — the identical rule `[services]` states two paragraphs up. `weft_cli.permission_policy`
carries the reasoning for why `read`/`write`/`network` are not keys here yet.

> **Extended by the reference study (2026-08-10) — `--origin` is a first-class feature, not a nicety.**
> In the reference, chunk size can be set in **five** places under **two different** precedence rules,
> and no single precedence statement exists anywhere: CLI flag → JSON config file → `strategies.json`
> on disk → `ChunkingConfig` Pydantic default **1024/100** → `create_parser` builder literal
> **512/50** (`evaluation/datasets/settings_loader.py:105-106`) — two default systems, silently
> disagreeing. Worse, **strategy selection inverts the scalar precedence**: config-file strategies >
> on-disk `strategies.json` > `DEFAULT_STRATEGIES`, with the CLI not participating at all
> (`indexing/indexer.py:544-550`), while scalars run CLI > config file > schema default. And
> `ConfigMerger` compares against sentinels in a way that makes an explicit
> `--embedding-provider local` indistinguishable from the default, so it cannot override a config
> file saying `openai` (`merger.py:42-46`). The reference's precedence was genuinely unknowable and it
> caused silent misconfiguration. One idea there is worth keeping: `ConfigMerger.merge_into_base`
> returns `base.model_copy(update=…, deep=True)` (`merger.py:177`) — merge immutably rather than in
> place. Write our own; it is one line and the value is knowing to make it that line. (`reference/study/10-doc-corrections.md` E10.)

> **Built in Phase 3 task 3.7 (2026-08-20) — `weft config get|set` reads and writes exactly
> four dotted keys**, `services.embed`, `services.store`, `permissions.overwrite`,
> `permissions.destroy` — the whole of what a command in this repository consults from
> `weft.toml` today. `weft_cli.config_surface.effective_config` answers `--origin` from the
> **raw parsed document**, never from comparing the merged `ServiceSelection`/
> `PermissionPolicy` against their own built-in defaults: that comparison is the reference's own
> sentinel bug reproduced one field at a time — indistinguishable between "explicitly set to
> the default value" and "not set". Reading the raw mapping and asking, per key, whether it
> is literally present answers the question a merged value structurally cannot:
> `services.embed = "hash"` written explicitly in `weft.toml` reports `origin: file` even
> though `"hash"` is also the built-in default, and a `weft.toml` that never mentions `embed`
> at all reports `origin: default` — the exact distinction a sentinel comparison collapses.
> `weft config set` edits `weft.toml` as **text**, not as a re-serialised document: `tomllib`
> is read-only and no TOML writer is a dependency this distribution carries, and a
> parse-mutate-write round trip would discard every comment a real `weft.toml` holds. The
> smallest edit that makes a key say what was asked — find or insert one `key = "value"` line
> under its `[section]` header, append the section if absent — leaves every other byte,
> comments included, untouched; `tests/unit/weft_cli/test_config_surface.py` proves a
> comment survives a `set` call, and the value round-trips through `tomllib` afterward.

> **Built in Phase 5 task 5.1c — a fifth dotted key, `reconcile.mode`.** `weft_cli.
> reconcile_policy.ReconcilePolicy` is `[services]`/`[permissions]`'s own shape applied to a
> third block: one function reading one already-parsed `dict`, a frozen Pydantic result with a
> built-in default (`full`, unchanged from `weft reconcile`'s own pre-5.1c hardcoded default),
> an unknown key refused by name, a malformed table refused the way `[packs]` already is. It
> governs exactly one thing: what `weft reconcile`, typed by hand with no `--mode`, resolves
> to — never `weft index`'s own automatic post-index pass, which stays hardcoded to `repair`
> and reads nothing here on purpose, so a project cannot, by editing this file once, turn every
> future `weft index` into a `full` run with nobody typing a flag for that particular
> invocation. `weft_cli.reconcile_policy`'s own module docstring carries the argument in full.

## Is the REPL an agent?

**No, and it never becomes one — but Weft does. Settled in G8, 2026-08-18.**

The REPL is a command shell with streaming and session state, closer to `psql` than to Claude Code's
inner loop. Weft's finished form **is** agentic: a model that plans, calls Weft's commands as tools
and acts on the corpus. Those two sentences are not in tension, and the reason is the governing rule
at the top of this document.

**An agent loop cannot live in the REPL, whatever the end state.** *Every operation the CLI performs
is a library call a FastAPI route could make identically* — and a planning loop is not that. It is
logic, it is the largest piece of logic in an agentic product, and putting it behind the prompt would
make the REPL the one adapter that can do something no other caller can. That is the exact shape this
document's first rule exists to refuse, and the reference's 1,080-line `indexer.py` is what it looks like
when the rule is not enforced.

**So the agent is a pack.** It registers against the same contracts a retriever does, it is driven by
the REPL, by a script and by an HTTP caller alike, and it is scheduled: **Phase 7**, after release,
because it is the largest consumer of contract surface Weft will ever have and should be built
against *published, versioned* contracts rather than moving ones. `01` → *Phases* carries it, and
**G12** — what a permission class means when the caller is never a TTY — is its gate.

**What this phase owes it is one property, and this phase needs that property anyway.** A `Command`
returns a **typed result that a renderer formats**, never pre-printed text. That is not a seam added
for a future consumer; it is what *Two modes, one implementation* above already requires, since "the
same commands with a different renderer" is unbuildable if a command prints. Getting it right here
means a Phase 7 loop calls the same surface a human does. Getting it wrong means retrofitting a loop
over text you have to re-parse — the expensive order this gate was opened to avoid, arrived at by
accident rather than by choice.

**Until G12, one rule holds without exception:** *Permissions* below is unchanged, so an `ask`-class
operation still fails without a TTY. An agent is never a TTY. A Phase 7 pack therefore cannot
`overwrite` or `destroy` on its own, and must either accept that ceiling or argue past it in G12 —
with something real to test the argument against, which is precisely what deciding it now would lack.
