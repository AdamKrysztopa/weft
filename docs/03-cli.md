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

## Command surface

Verb-first and small. Depth lives in subcommands, not in flags.

```
weft init                      scaffold weft.toml in the current project
weft index <path>              run an ingestion pipeline over a source
weft ask <question>            query, streaming the answer with citations
weft pipeline list|show|derive|validate|diff
weft plugins list|info|doctor
weft eval run|compare
weft trace [<run-id>]          replay what a run actually did
weft config get|set
```

Two of these carry weight beyond their size:

- **`weft pipeline diff a b`** renders the difference between two *resolved* pipelines. Because
  resolution produces a fully-explicit form, this is an exact comparison rather than a guess, and
  it is what makes derived pipelines reviewable.
- **`weft plugins doctor`** reports what was discovered, from which distribution, at what contract
  version, and what failed to load and why. When someone's pack is not appearing, this is the
  first and usually last thing they run. It prints one status per distribution — `active`, `refused`,
  `failed`, `partial`, `allowed, not installed`, with an `ambient` flag — plus each pack's
  disclosure and what its `register()` cost. The vocabulary is defined once in `02` §2, *The trust
  model*; refusals and half-registered packs share it rather than getting a second surface.

  **G2 adds two reports to it, both about a pack that loaded fine and still does nothing** — the
  failure a status vocabulary alone cannot express. A **displaced** registration: the pack lost a
  `(contract, name)` collision to an operator's pin, so it is installed, active, and one of its
  plugins is unreachable. And a pack whose **contributions land in no pipeline at all**, because no
  available pipeline declares the slot it targets. Both are silent successes otherwise, and both are
  the shape of the reference's registered-but-unreachable strategy.

`weft pipeline show` prints the **resolved** form, which after G2 carries more than stages: each
stage's provenance (which pipeline or pack put it there), every var's final value, contributions that
found no slot, and operators that went unapplied because the pack they name is not installed. Those
last two are recorded rather than fatal — see `02` §3, *Slots* — so printing them is the only way
they are visible.

## In-session commands

Slash commands inside the REPL, matching the mental model of the CLI:

```
/help                    /pipeline [name]       switch or inspect the active pipeline
/plugins                 /trace                 show the last run's stages and timings
/eval                    /config
/clear                   /exit
```

The session carries state a one-shot invocation does not: the active pipeline, the collection,
conversation history, and the last run's trace. That state is explicit and inspectable — `/config`
prints it — because implicit session state is how a tool starts behaving differently for two people
running the same command.

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
