# Weft, day to day

Written for someone using Weft's pipelines, not building the kernel. [`manual/quickstart.md`](
quickstart.md) already walks `weft index`/`weft ask` against the one built-in pipeline Phase 0
hardcodes; this page is about what changes at Phase 1 — a pipeline stops being one fixed list and
becomes a document, one you can derive from another without touching what it derives from.

**Every example below is Python, not the CLI, and that is honest rather than a choice.** There is
no `weft pipeline derive` command yet — that is Phase 3's CLI surface
(`docs/build-ledger.md` 3.7) — so today the only way to open a pipeline document and resolve it is
the same call a future command will make on your behalf: `weft_cli.pipeline_catalogue` to open the
file, `weft_kernel.resolution.resolve` to derive it. Definitions link to
[`docs/02-extension-model.md`](../docs/02-extension-model.md) §3 rather than restating them; this
page is the task, not the argument for why it is shaped this way.

> **Corrected, 2026-08-20 (task 3.9).** "There is no `weft pipeline derive` command yet" stopped
> being true at task 3.7 — every pipeline and config command below now exists. The Python
> examples that follow are unchanged and still teach the shape a real command calls on your
> behalf; they are no longer the *only* way to reach it. §6 below is the complete, generated
> command table.

## 1. A pipeline is a document

A pipeline document has four top-level keys that matter here:

| Key | Holds |
|---|---|
| `name` | The pipeline's own identity — what `extends:` and a catalogue lookup both name it by |
| `extends` | The parent this pipeline changes. Absent on a **root** pipeline, which is the only kind allowed to list its own `stages:` |
| `vars` | Scalar values several stages agree on — see §3 |
| `stages` | An ordered list, root pipelines only. A child expresses what changes with an **operator** instead — see §2 |

Each entry in `stages:` names a plugin, not a contract — the kernel names no capability, so nothing
in the document itself says "this is a chunker." The four fields on a stage:

| Field | Holds |
|---|---|
| `id` | This stage's handle — unique in the document. Every operator, every resolution error and every slot addresses a stage by this and nothing else |
| `use` | A **bare** plugin name (`02` §2: pipelines select plugins by name, never by distribution) |
| `with` | That plugin's own configuration, validated against its `config_model` once the pipeline resolves — an unconfigurable plugin refuses a non-empty block by name, rather than silently dropping it |
| `fallback` | A list of plugin names — see the note below |

**`fallback:` is walked by the runner, as of Phase 2 task 2.28 — and no `weft` command hands it a
document yet.** Read the scope note at the end of this section before you rely on one. Where a chain
does run, the names are tried in order until one answers, and what counts as an answer is the
outcome the plugin returned, never a guess at its value:

| The plugin says | The chain does |
|---|---|
| it produced something | stops, and that is the stage's result |
| **it looked, and there is nothing there** | stops, and *that* is the stage's result |
| it could not do the job — refused, or raised | records why, and tries the next name |

The middle row is the one worth reading twice. "This document is genuinely empty" and "I could not
read this document" are different facts, and a fallback chain that cannot tell them apart either
hands a blank page to every backend in turn and then reports a failure, or reports an unreadable
scan as a successfully-parsed empty file. Both happen; both are silent. So a backend that cannot
distinguish the two for a given input is required to say *"I could not do the job"* — and only a
backend that genuinely looked may stop the chain with an empty result.

The example above is real: `pdf-text` reads a PDF's text layer, `pdf-layout` reconstructs the
page's geometry, and neither is a degraded version of the other. A PDF truncated in transit fails
the first and reads fine through the second; a PDF whose pages carry an image and no text fails
both, which is exactly the document an OCR pack would be for.

**A name in `fallback:` that nothing has installed is fine to write, and refused when a runner is
given it.** Writing `fallback: [ocr]` before any pack ships an `ocr` is legal — the document
resolves, diffs and derives — because a document should not have to be re-edited the day the pack
arrives. `Runner.resolve` refuses that chain at once with `UnknownFallbackError`, naming the stage
and every name that is registered, rather than crashing on the first page the primary cannot read
or, worse, skipping the fallback silently. It refuses a fallback that is not *substitutable* for the
plugin it stands in for the same way, with `FallbackNotSubstitutableError` — see
[`troubleshooting.md`](troubleshooting.md).

**A fallback takes no `with:` block, so a configured second attempt cannot be written at all today.**
It is a bare name, and it runs on its plugin's own defaults. There is nowhere in the grammar to
configure one, and nothing routes a stage's failures into another pipeline — so running a second,
differently-configured pipeline over the documents the first could not read is something you do,
not something Weft does. Widening the grammar is a later task.

**Scope, as of today: what runs, and what does not.** The chain above is walked by
`weft_kernel.fallback.try_in_order` for any caller that hands `Runner.resolve` a `StageSpec`
carrying a `fallback` list. Nothing that opens a *pipeline document* does that yet: `weft index`
pins its own four stages and has no `--fallback` option, and `weft_kernel.resolution.resolve` — the
call every example on this page makes — carries a `fallback:` list through into the resolved form
and executes nothing. The missing link is `weft_cli/compile.py`, which turns a resolved document
into `StageSpec`s (`docs/build-ledger.md` 2.4 and 2.8). So a `fallback:` you write today is stored,
derived and diffed exactly as described above — and until that task lands, no `weft` command tries a
second backend on your behalf, and no `UnknownFallbackError` reaches you through one.

## 2. Deriving one pipeline from another

A pipeline that `extends:` a parent may not list `stages:` of its own — `02` §3: a child expresses
what changes, never a second copy of the whole. Four operators, and only four:

| Operator | Does |
|---|---|
| `insert` | Adds a stage, positioned `after:` or `before:` an existing id |
| `replace` | Swaps the plugin at an existing id, keeping its position |
| `remove` | Drops a stage by id |
| `set` | Overrides an existing stage's `with:` block, without changing its plugin |

**They apply in the order the document writes them, not in this table's order and not in any
fixed order at all.** A YAML mapping cannot repeat a key, so a document choosing `remove:` above
`insert:` on one id is expressing something different from the reverse — the first is a move (the
old stage is gone before the new one lands on its id), the second is a collision (the new one
lands while the old one is still there). Every target is checked against the *running* result, not
against the original parent, and a target that turns out not to exist there — including a `remove`
matching nothing — fails resolution by name rather than silently doing nothing. The full argument
for why written order, rather than a fixed evaluation order, is `02` §3's own; §5 below shows what
one of these failures actually looks like.

### Running it

The example is `02` §3's own worked case: `specific` adds a keyword-extraction stage to `base`
after `chunk`, without copying anything `base` already says.

```python id=derive
import json
import tempfile
from pathlib import Path

from weft_chunk import Chunker, FixedSizeChunker
from weft_cli.pipeline_catalogue import load_pipeline_catalogue
from weft_embed import Embedder, HashEmbedder
from weft_enhance import Enhancer, KeyBertKeywordExtractor
from weft_extract import Extractor, TextExtractor
from weft_kernel.registry import Registry
from weft_kernel.resolution import resolve

# `02` §3's own base.yaml, trimmed to three built-in stages — no clean, no store,
# nothing this walkthrough needs a container for.
BASE_YAML = """\
name: base
vars: {chunk_size: 200}
stages:
  - id: extract
    use: text
    fallback: [pdf-layout]
  - id: chunk
    use: fixed-size
    with: {size: "${var:chunk_size}", overlap: 20}
  - id: embed
    use: hash
"""

# `02` §3's own specific.yaml, verbatim in shape: one `extends:`, one `insert:`.
SPECIFIC_YAML = """\
name: specific
extends: base
insert:
  - after: chunk
    stage: {id: keywords, use: keybert, with: {top_n: 8}}
"""

directory = Path(tempfile.mkdtemp())
(directory / "base.yaml").write_text(BASE_YAML)
(directory / "specific.yaml").write_text(SPECIFIC_YAML)

# `weft_cli.pipeline_catalogue` is the one module that opens a pipeline document —
# the kernel itself parses no file.
catalogue = load_pipeline_catalogue(directory)

# What today's `weft index` builds by hand, from a fixed list — a pipeline document
# names a plugin, never a distribution, so `resolve()` still needs a registry to
# look the name up against.
registry = Registry()
registry.add(Extractor, "text", TextExtractor, distribution="weft-extract")
registry.add(Chunker, "fixed-size", FixedSizeChunker, distribution="weft-chunk")
registry.add(Enhancer, "keybert", KeyBertKeywordExtractor, distribution="weft-enhance")
registry.add(Embedder, "hash", HashEmbedder, distribution="weft-embed")

# Stage id -> contract: `resolve()`'s caller supplies this, never guesses it from
# a bare `use:` name (`02` §3) — the kernel names no capability, so nothing here
# could recognise "Chunker" from the string "fixed-size" on its own.
contracts = {"extract": Extractor, "chunk": Chunker, "keywords": Enhancer, "embed": Embedder}

resolved = resolve(catalogue["specific"], registry=registry, contracts=contracts, parents=catalogue)
print(json.dumps(resolved.model_dump(mode="json"), indent=2))
```

What that prints — the resolved form, exactly as `resolved.model_dump(mode="json")` builds it:

```text id=derive-out
{
  "name": "specific",
  "vars": {
    "chunk_size": 200
  },
  "stages": [
    {
      "id": "extract",
      "contract": "Extractor",
      "contract_version": "1.0.0",
      "use": "text",
      "config": {},
      "fallback": [
        "pdf-layout"
      ],
      "applies_to": [],
      "distribution": "weft-extract",
      "provenance": "base"
    },
    {
      "id": "chunk",
      "contract": "Chunker",
      "contract_version": "1.0.0",
      "use": "fixed-size",
      "config": {
        "size": 200,
        "overlap": 20
      },
      "fallback": [],
      "applies_to": [],
      "distribution": "weft-chunk",
      "provenance": "base"
    },
    {
      "id": "keywords",
      "contract": "Enhancer",
      "contract_version": "1.0.0",
      "use": "keybert",
      "config": {
        "top_n": 8
      },
      "fallback": [],
      "applies_to": [],
      "distribution": "weft-enhance",
      "provenance": "specific"
    },
    {
      "id": "embed",
      "contract": "Embedder",
      "contract_version": "1.0.0",
      "use": "hash",
      "config": {},
      "fallback": [],
      "applies_to": [],
      "distribution": "weft-embed",
      "provenance": "base"
    }
  ],
  "unapplied_operators": [],
  "unplaced_contributions": []
}
```

Four stages, not three plus one appended — `keywords` sits between `chunk` and `embed` exactly
where `insert: {after: chunk}` put it, and `specific.yaml` never mentioned `extract`, `chunk` or
`embed` by name. **`provenance` is where each stage's plugin was last decided**, not where the
stage id first appeared: `extract`, `chunk` and `embed` all read `"base"`, because nothing in
`specific` touched what plugin runs at those ids; `keywords` reads `"specific"`, because that is
the document whose `insert` put a plugin at that id at all. Edit `base.yaml` on disk — its `chunk`
stage's `size`, say — and resolving `specific` again reads the edit with nothing cached in
between: `resolve()` reads a live parent, never a copy (`02` §3).

### The two documents, in full

The script above builds `base.yaml` and `specific.yaml` from Python string constants, so a
reader can run the whole page as one script. Here they are as the plain files they are —
what you would actually write:

```yaml id=pipeline:base
name: base
vars: {chunk_size: 200}
stages:
  - id: extract
    use: text
    fallback: [pdf-layout]
  - id: chunk
    use: fixed-size
    with: {size: "${var:chunk_size}", overlap: 20}
  - id: embed
    use: hash
```

```yaml id=pipeline:specific
name: specific
extends: base
insert:
  - after: chunk
    stage: {id: keywords, use: keybert, with: {top_n: 8}}
```

Quoted here, not merely narrated: `01` → *Fitness functions* item 11(b) reads every
`yaml id=pipeline:...`-tagged block across `manual/` and resolves it against the real,
installed registry in `ci-checks` — the same check that watches every pipeline a pack ships.
A rename of `keybert` or a typo in `after: chunk` fails the gate this page's own prose is
checked against, not a reader's first `weft index`.

## 3. Vars — a decision the whole pipeline shares

A **fact about a node** — the language a passage is written in, say — is not what `vars:` is for;
that is `applies_to`, §4 below. `vars:` is a **decision about the whole pipeline**, substituted
into a `with:` value written as `${var:name}`, and a child that overrides one re-resolves every
inherited stage that references it — no operator needed, because nothing about *which stage runs*
changed, only a value it was configured with.

```python id=vars
import tempfile
from pathlib import Path

from weft_chunk import Chunker, FixedSizeChunker
from weft_cli.pipeline_catalogue import load_pipeline_catalogue
from weft_embed import Embedder, HashEmbedder
from weft_extract import Extractor, TextExtractor
from weft_kernel.registry import Registry
from weft_kernel.resolution import resolve

BASE_YAML = """\
name: base
vars: {chunk_size: 200}
stages:
  - id: extract
    use: text
  - id: chunk
    use: fixed-size
    with: {size: "${var:chunk_size}", overlap: 20}
  - id: embed
    use: hash
"""

# `02` §3's own `base-de.yaml`, in shape: the entire file is `extends:` plus one
# `vars:` override — no operator, no stage of its own.
WIDE_YAML = """\
name: wide
extends: base
vars: {chunk_size: 400}
"""

directory = Path(tempfile.mkdtemp())
(directory / "base.yaml").write_text(BASE_YAML)
(directory / "wide.yaml").write_text(WIDE_YAML)
catalogue = load_pipeline_catalogue(directory)

registry = Registry()
registry.add(Extractor, "text", TextExtractor, distribution="weft-extract")
registry.add(Chunker, "fixed-size", FixedSizeChunker, distribution="weft-chunk")
registry.add(Embedder, "hash", HashEmbedder, distribution="weft-embed")
contracts = {"extract": Extractor, "chunk": Chunker, "embed": Embedder}


def chunk_size(pipeline_name: str) -> int:
    resolved = resolve(
        catalogue[pipeline_name], registry=registry, contracts=contracts, parents=catalogue
    )
    (chunk,) = (stage for stage in resolved.stages if stage.id == "chunk")
    return chunk.config.size


# `wide` writes no `chunk` stage of its own — the override reaches an inherited
# stage's `with:` value with nothing else in the document naming `chunk` at all.
print(f"base's chunk.size: {chunk_size('base')}")
print(f"wide's chunk.size: {chunk_size('wide')}")
```

```text id=vars-out
base's chunk.size: 200
wide's chunk.size: 400
```

`wide.yaml` is two lines beyond `extends:` and never mentions `chunk` — the override reaches it
because `with:` values are substituted against the whole chain's *merged* vars, computed once
resolution has walked every ancestor, not against whichever level happened to write the `with:`
block in the first place.

## 4. Applicability — what a stage operates on

A stage may declare `applies_to` — a tuple of facts a node must carry for that stage to run on it
at all; a node that does not carry them passes through untouched, and the stage never sees it.
`weft_clean.dictionary_spacing.PolishFusedWordFixer` is a real, shipped example: it narrows itself
to nodes whose `Language` fact reads `code="pl"`, so an English node in the same batch is never
handed to a splitter tuned for Polish prefixes. Every stage in the walkthrough above declares none
— `"applies_to": []` in the printed resolved form — which is the default, and it means exactly what
it says: the stage runs on everything it is handed. When a stage does declare one, the resolved
form prints it, because a predicate is data too, not a rule a reader has to trust blindly. The
mechanism that evaluates it — a runner routing whole contiguous runs of matching nodes around a
stage, not one node at a time — is `docs/02-extension-model.md` §3 → *Applicability*, not restated
here.

## 5. When resolution fails

Every way `resolve()` can refuse a document's *shape* — a stale operator target, an undefined var, a
cycle in `extends`, contributions that cannot be ordered, and the rest — is its own `WeftError`
subclass, all under one family (`PipelineResolutionError`), and every one of them names the pipeline,
the stage or operator at fault, and what would have made it pass — never a bare `KeyError` discovered
against the first document that happens to exercise it. A `use:` naming a plugin nothing registered
is refused too, but by a sibling rather than a family member: `weft_kernel.registry.UnknownPluginError`,
raised by `Registry.entry` and reused here rather than wrapped, so a `try/except PipelineResolutionError`
around a `resolve()` call will not catch a typo in `use:` — catch `UnknownPluginError` separately, or
catch `WeftError` if the distinction does not matter to the caller. One example, a typo in an
`insert` operator's target:

```python id=resolution-failure
from weft_chunk import Chunker, FixedSizeChunker
from weft_extract import Extractor, TextExtractor
from weft_kernel.pipeline import Pipeline
from weft_kernel.registry import Registry
from weft_kernel.resolution import StaleOperatorTargetError, resolve

base = Pipeline.model_validate(
    {
        "name": "base",
        "stages": [
            {"id": "extract", "use": "text"},
            {"id": "chunk", "use": "fixed-size"},
        ],
    }
)
# A typo: "chnk" instead of "chunk" — an author's mistake, not a network problem.
typo = Pipeline.model_validate(
    {
        "name": "typo",
        "extends": "base",
        "insert": [{"after": "chnk", "stage": {"id": "keywords", "use": "keybert"}}],
    }
)

registry = Registry()
registry.add(Extractor, "text", TextExtractor, distribution="weft-extract")
registry.add(Chunker, "fixed-size", FixedSizeChunker, distribution="weft-chunk")
contracts = {"extract": Extractor, "chunk": Chunker}

try:
    resolve(typo, registry=registry, contracts=contracts, parents={"base": base})
except StaleOperatorTargetError as exc:
    print(f"{type(exc).__name__}: {exc}")
```

```text id=resolution-failure-out
StaleOperatorTargetError: pipeline 'typo' extends 'base' and its 'insert' operator targets stage id 'chnk', but no stage with that id exists in the parent it resolved against at this point in the chain. The ids that do exist: 'extract', 'chunk'.
```

The message names the id that was wanted, the ids that do exist, and the pipeline and parent
involved — the same shape every other resolution failure follows, whether the mistake is a stale
operator target, an undefined var, a `with:` block that fails its plugin's own configuration model,
or two stages that do not compose by type. [`manual/troubleshooting.md`](troubleshooting.md) has
one entry per failure class, each reproduced and paired with what to do about it — this page shows
one example of the shape, not the catalogue.

## 6. Every command, generated

Every table below is walked from the installed registry, not typed — the same mechanism
`docs/03-cli.md` → *Plugin-contributed commands* already commits `weft --help` to: "Core has no
list of commands to edit. The help text is generated from the registry, which means it cannot
drift from what is installed." This table is that identical walk, rendered to Markdown instead of
a terminal (`docs/08-manuals.md` §3, clause (b)) — a command a pack contributes appears here
because it registered under `weft_command.contract.Command`, exactly as it appears in `weft
--help`, never because someone remembered to add a row.

Regenerate it after a command's `help`, permission class or registration changes, and commit the
result:

```
uv run python scripts/generate_command_table.py
```

`tests/docs/test_generated_docs.py` checks the committed copy against a fresh walk of the
registry on every `ci-checks` run, on `manual/contract-reference.md`'s own footing — a command
added, removed or reworded without this table noticing fails the build before it fails a reader.

<!-- weft-cli:generated:command-table:begin -->
| Command | Permission | Registered by | Summary |
|---|---|---|---|
| `weft ask` | `read` | `weft-cli` | ask a question. Routes through the installed router by default — a QueryScorer and a RoutingPolicy discovered from the registry, never a fixed list here — and prints the generated, cited answer. --pipeline names one directly, skipping the router; --retrieve-only runs no pipeline at all and prints the nearest passages instead, with no generation and no model call (Phase 0's own contract, kept for scripts). |
| `weft config get` | `read` | `weft-cli` | the project's effective configuration — one key with --key, or every key CONFIG_KEYS names; --origin says whether each value is set in weft.toml or defaulted |
| `weft config set` | `write` | `weft-cli` | set one key in weft.toml, preserving every comment and every other key untouched |
| `weft eval compare` | `read` | `weft-cli` | the exact, structural difference between two persisted runs' pipelines, and their per-metric aggregates side by side — refuses if the two ran over a different corpus, model versions or active distribution set, rather than reporting a diff that is not apples to apples |
| `weft eval metrics` | `read` | `weft-cli` | which registered metrics run in the deterministic gate subset — no credentials, no network, no model download — and which do not, or ask about one metric by name |
| `weft eval run` | `write` | `weft-cli` | run a named pipeline over a corpus and persist a run record — resolved pipeline, corpus identity, active distribution set, and (with --questions) per-metric aggregates — so a later 'weft eval compare' can diff it against another. 'pipeline' is required: a run record needs a resolved pipeline to persist. |
| `weft index` | `write` | `weft-cli` | run an ingest pipeline over a directory. Which formats are accepted is derived from the extractors actually installed, never from a fixed list. --pipeline names a document instead of the built-in four stages, reaching a plugin's own 'with:' configuration (ledger task 4.0). |
| `weft init` | `write` | `weft-cli` | scaffold weft.toml in the current directory — every key commented out, offline by default |
| `weft pipeline derive` | `write` | `weft-cli` | scaffold a new pipeline document with 'extends:' set to an existing one |
| `weft pipeline diff` | `read` | `weft-cli` | the exact, structural difference between two resolved pipelines |
| `weft pipeline list` | `read` | `weft-cli` | every pipeline this project can resolve — project-local documents and every installed pack's own contribution |
| `weft pipeline show` | `read` | `weft-cli` | the resolved form of one pipeline: every stage's provenance, every var's final value, and anything that went unplaced or unapplied |
| `weft pipeline validate` | `read` | `weft-cli` | resolve a pipeline and report whether it does, in the resolution-failure family's own words |
| `weft plugins doctor` | `read` | `weft-cli` | full status, reason and disclosure per discovered pack |
| `weft plugins list` | `read` | `weft-cli` | one line per discovered pack |
| `weft trace` | `read` | `weft-cli` | print what one persisted run recorded — its resolved pipeline, corpus, model versions and active distribution set |
<!-- weft-cli:generated:command-table:end -->

## Where to go next

- **Never run `weft` before?** [`manual/quickstart.md`](quickstart.md) is the five-minute path from
  nothing to a real, retrieved answer, against the one pipeline Phase 0 hardcodes.
- **An error in front of you right now?** [`manual/troubleshooting.md`](troubleshooting.md) has
  every failure mode named above, and every one this page does not cover.
- **Writing a pack whose plugin a pipeline could name?** [`manual/pack-author-guide.md`](
  pack-author-guide.md) walks a real one, installed from outside this project's own workspace.
