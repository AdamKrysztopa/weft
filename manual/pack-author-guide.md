# Writing a pack

Written for someone who has not read the plan. You need Python 3.12+ and `uv`, and nothing else —
no `weft/` directory to touch inside this project, no plugin manifest to append to, no registry
file anywhere in Weft that will learn your pack's name.

This guide is not a hypothetical. It walks the exact pack Weft keeps installed *outside its own
workspace* to prove the claim every capability here rests on — `examples/weft-example-chunker/` —
and every code block below is that pack's real file, checked in CI: if the file changes, this page
is wrong until it changes too. Definitions link to
[`docs/02-extension-model.md`](../docs/02-extension-model.md) §1–§2 rather than restating them.

**§1–§8 are one pack, one contract.** §9 is the other shape — a pack spanning several contracts plus
a contributed command, `docs/02-extension-model.md` §4's graph-add-on case adapted into the same kind
of tested walkthrough, and what G9 (contract versioning and deprecation) now makes a pack author's own
responsibility.

## 1. The directory

```text
weft-example-chunker/              # anywhere. Not inside the weft checkout, not a workspace member
├── pyproject.toml
├── src/
│   └── weft_example_chunker/
│       ├── __init__.py            # Settings + register()
│       └── word_chunker.py        # the contract implementation
└── tests/
    └── test_word_chunker.py
```

Four files that matter, and this one publishes one plugin — a chunker that splits on whitespace
into one child node per word. It is deliberately not a variation on the built-in fixed-size
chunker: a third party has no reason to reimplement that, so this one takes a genuinely different
approach, to make the point that anything satisfying the `Chunker` contract *structurally* is
usable, not only the shape the built-in happens to take.

## 2. `pyproject.toml` — the entire integration surface

```toml path=examples/weft-example-chunker/pyproject.toml
[project]
name = "weft-example-chunker"
version = "0.0.0"
description = "A stranger's chunker — lives outside the weft workspace, proving fitness function 9."
requires-python = ">=3.12"
# Both deps are published packages any third party would `pip install`; this
# distribution never sees the weft workspace's source tree, only the wheels
# those two ship. weft-rag is depended on for the one thing a third-party
# chunker pack needs from it: the `Chunker` Protocol weft_chunk publishes — the
# same relationship docs/07-extension-cost.md section 1 states for any pack that
# implements a contract it does not itself define. **It is `weft-rag` and not
# `weft-chunk` because that is where `weft_chunk` ships since 2026-09-05**: the
# import a pack writes is unchanged, and the name it installs is not.
#
# **Both carry `>=X,<MAJOR+1`, and that is the point of an exemplar** — weft's ledger task 6.26.
# G9 settled that a version requirement *is* the dependency specifier and bare names end; this
# pack, and the five beside it, declared bare names until that task, so the thing a pack author
# copies was teaching that bounds are optional. `tests/architecture/test_example_packs_are_
# exemplars.py` in the weft repository is what keeps them from drifting back.
dependencies = ["weft-kernel>=0.1.0,<1.0.0", "weft-rag>=2.1.0,<3.0.0"]

# The one entry point a pack declares (weft's docs/02-extension-model.md
# section 2). Nothing under weft's own packages/ or testing/ names this
# distribution, this module, or the plugin name below — fitness function
# 9(b), asserted from the weft repository's own tests/architecture/.
[project.entry-points."weft.packs"]
example-chunker = "weft_example_chunker:register"

# This pack's own dev tooling — the fourth canonical file's test runner. Not
# shared with weft's own dev group: a stranger's `uv run pytest` here must
# work from this pyproject alone, with nothing borrowed from the workspace
# it is not a member of.
[dependency-groups]
dev = ["pytest>=8.3", "pytest-asyncio>=0.24"]

[tool.pytest.ini_options]
asyncio_mode = "auto"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

Three things to notice, each a decision rather than a convention:

- **You depend on the distribution that ships `weft_chunk`, not on the kernel alone.** The kernel
  names no capability and publishes no `Chunker`; contracts ship from the packs that own them. You
  depend on the contract's publisher exactly as you would on any third-party protocol —
  `weft-kernel` alone would not even give you something to import against. That distribution is
  `weft-rag` since 2026-09-05, which ships fourteen packs in one wheel; the import you write
  (`from weft_chunk.contract import Chunker`) did not change, and the name you install did.
- **One entry point, in the `weft.packs` group — not one per plugin.** The alias on the left
  (`example-chunker`) labels this line inside the group; the plugin *name* your pack answers to
  (also `example-chunker` here, but the two are independent) is whatever string you pass to
  `registrar.add`.
- **This is the same entry point the first-party packs use.** They ship inside Weft's own
  repository for release convenience and get no shortcut for it — fitness function 2, checked at
  runtime, is what makes that a fact rather than a claim.

## 3. `__init__.py` — settings and `register()`

```python path=examples/weft-example-chunker/src/weft_example_chunker/__init__.py
"""A stranger's chunking pack — the independence proof, as an artifact.

`docs/06-phase-0-build.md` step 10, in the `weft` repository this example is
built to prove a claim about: a pack that lives *outside* that repository's
workspace, in its own directory with its own `pyproject.toml`, installed the
same way any third-party pack would be, registering one plugin through the
same `weft.packs` entry point every first-party pack uses — no shortcut, no
private import path.

`weft`'s `tests/architecture/test_ff9_extension_from_outside.py` installs
this distribution into a throwaway environment built from wheels, with the
`weft` repository itself nowhere on `sys.path`, and runs a pipeline that
names `"example-chunker"` for `weft_chunk.contract.Chunker` — proving the
plugin resolves and runs. Uninstalling this distribution and running the
same pipeline again is the other half: resolution fails, naming the plugin
weft's `weft_kernel.registry.Registry` never saw.
"""

from pydantic import BaseModel, ConfigDict

from weft_chunk.contract import Chunker
from weft_example_chunker.word_chunker import WordChunker
from weft_kernel.discovery import PackRegistrar


class Settings(BaseModel):
    """This pack takes no settings — an empty model is still the required shape."""

    model_config = ConfigDict(frozen=True, extra="forbid")


def register(registrar: PackRegistrar, settings: Settings) -> None:
    """Register `WordChunker` as `"example-chunker"` for `Chunker` — the only plugin here."""
    del settings
    registrar.add(Chunker, "example-chunker", WordChunker)


__all__ = ["Settings", "WordChunker", "register"]
```

- **`register(registrar, settings)` is exactly two parameters, and the kernel checks the shape.**
  It reads your function's signature and requires the second parameter to be annotated with a
  `pydantic.BaseModel` subclass — that model is what your `packs:` settings block validates
  against, *before* `register` ever runs, failing with your pack and field named rather than a
  stack trace inside your own code. A pack with nothing to configure still declares an empty model,
  as above — there is no settings-less shape to special-case.
- **`register` is called once**, when a command first needs the registry — never at process start.
  `weft --version` runs without importing this pack at all.
- **`registrar.add(contract, name, factory)` — never `registry.add`, and never a `distribution`
  argument.** `PackRegistrar` is the view your `register()` actually receives: `Registry.add` minus
  its `distribution` keyword, because attribution is filled in by whoever is calling `discover()`,
  never something a pack author supplies or could get wrong.
- **You register the class, not an instance.** The kernel constructs it itself when a pipeline
  resolves, passing whatever `with:`-style stage configuration that resolution carries — this pack
  takes none, so `WordChunker.__init__` accepts and discards it.
- **Registration is transactional.** Every `registrar.add` call is buffered; nothing reaches the
  shared registry until `register()` returns without raising, at which point the whole batch
  commits at once. A pack that raises partway through contributes exactly zero — its own `doctor`
  report and the registry can never disagree about how much of a half-finished pack is live.
- **Two packs claiming one name is refused, loudly, naming both distributions.** That is the
  reversible Phase 0 choice for G2's still-open arbitration question, not an answer to it.

## 4. `word_chunker.py` — the contract implementation

```python path=examples/weft-example-chunker/src/weft_example_chunker/word_chunker.py
"""`WordChunker` — a stranger's chunker: one child node per whitespace-separated word.

Deliberately not `weft_chunk.fixed_size.FixedSizeChunker` with different
numbers — a third party has no reason to reimplement the built-in, so this
one picks a genuinely different strategy to make the point that any
implementation satisfying `weft_chunk.contract.Chunker` structurally is
usable, not only the shape the built-in happens to take. Every child is
built through `Node.derive`, so lineage is carried automatically — the same
guarantee `docs/02-extension-model.md` gives every chunker, first-party or
not.

`destroys: tuple[type[Property], ...] = ()` is not decoration. `Chunker`
publishes a property vocabulary (`docs/02-extension-model.md` §3 →
*Ordering constraints*), so `weft_kernel.registry` refuses to register any
`Chunker` implementation — a stranger's own no less than a built-in — that
never states `destroys` at all. This one states the truth: splitting
strictly on whitespace never breaks a word the way a fixed-size window can,
so the tuple is empty rather than borrowed from `FixedSizeChunker`.
"""

from collections.abc import Sequence

from weft_kernel.context import Context
from weft_kernel.payload import Node, NothingToProduce, Outcome, Produced, Property


class WordChunker:
    """Splits each node's content on whitespace into one child node per word.

    Satisfies `weft_chunk.contract.Chunker` structurally — this class never
    imports it, the same path `docs/02-extension-model.md` describes for a
    third-party plugin. A node with no words contributes no children; a
    batch that contributes none at all answers `NothingToProduce`, never an
    empty `Produced([])`, the same convention `FixedSizeChunker` follows.
    """

    destroys: tuple[type[Property], ...] = ()

    def __init__(self, config: object = None) -> None:
        # No `with:` configuration this chunker takes — the runner's factory
        # call always passes a `spec.config` (`None` when a `StageSpec`
        # names none), so the parameter exists to accept that, not to be
        # used.
        del config

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        del ctx  # no service or locale this stage needs
        words: list[Node] = []
        for node in payload:
            words.extend(_words(node))
        if not words:
            return NothingToProduce(reason="no node had any word to carry")
        return Produced(value=words)


def _words(node: Node) -> list[Node]:
    """Every whitespace-separated word of `node.content`, each a child of `node`."""
    return [
        node.derive(content=word, ordinal=ordinal)
        for ordinal, word in enumerate(node.content.split())
    ]
```

The rules this obeys, and what enforces each:

| Rule | Enforced by |
|---|---|
| **Every contract method is `async def`.** No sync protocol, no colour to declare | G6. You never write `asyncio.run` — the tree contains exactly one, in `weft_cli` (fitness function 7(a)) |
| **Return an `Outcome`, never a bare value.** `Produced` / `NothingToProduce` / `Failed` | `02` §1. `NothingToProduce(reason=…)` for a legitimately empty result — never an empty `Produced([])`, which is indistinguishable downstream from a real failure hidden behind a fallback |
| **Build children with `Node.derive`, and pass an ordinal** | `02` §1 → *The payload model*. `derive` carries lineage automatically, so cascade delete reaches every child; a node's identity is a digest over its content, media type, sorted parent ids **and this ordinal** |
| **Nothing here writes a span, attributes an error, or checks for a blocking call** | The registration seam (`weft_kernel.seam.wrap`) does all three automatically for every stage a `Runner` actually resolves and runs — see §5. There is nothing to remember and nothing to get wrong by omission |
| **No import of `Chunker` in this file at all** | `02` §1: capability is structural. `WordChunker` satisfies `weft_chunk.contract.Chunker` because it has the one method the Protocol asks for, not because it says so |
| **`destroys` is stated, not omitted — an empty tuple counts** | `02` §3 → *Ordering constraints*. `Chunker` publishes a property vocabulary, so `weft_kernel.registry` refuses to register a `Chunker` implementation that never mentions `destroys` at all, naming the missing declaration. `intact` stays optional — nothing here needs one |

> **The ordinal is not optional, and it is the one line above you must not simplify away.** A
> node's id is a digest over its media type, its content, its sorted parent ids — **and this
> ordinal**. Drop it (or pass the same value for every child) and two nodes with byte-identical
> content under the same parent collapse to the *same id*, silently overwriting one another in
> whatever stores them next. That is not a corner case a chunker can assume away: a repeated
> heading, a boilerplate footer, an empty cell, even the word "the" appearing twice in one
> sentence — `_words` above hands every word its own position in the sentence specifically so
> `enumerate` never lets two siblings collide. Passing distinct ordinals to siblings is the
> caller's job; nothing else in the kernel can infer what "a sibling" means for your stage.

## 5. Proving it runs

**`weft index` and `weft ask` will not run this plugin.** Phase 0 has not built pipelines as
configuration yet — `weft index` composes one fixed list of four stages, and nothing you install
changes which chunker, embedder or store it names. **One stage is the exception, and if you are
writing an *extractor* it is the one that matters:** `weft index` derives what file formats it
accepts, and which extractor runs, from the `extensions` every registered `Extractor` declares
(`weft_extract.accept.claimed_extensions`). Install an extractor pack claiming `.epub` and
`weft index` reads `.epub` with no edit anywhere; if two installed extractors claim the same
suffix it refuses by name rather than choosing, and `--extract <name>` picks one. Proving a third-party plugin works today means
exactly what `tests/architecture/test_ff9_extension_from_outside.py` does, and it is three ordinary
objects: a `weft_kernel.registry.Registry`, one `weft_kernel.runner.StageSpec` naming your plugin
for `Chunker`, and `weft_kernel.runner.Runner.resolve(...)` / `.run(...)` to check and execute it.
Discovery — `weft_kernel.discovery.discover(registry)` — is what populates that registry for real,
by finding this pack's entry point, importing it, and calling `register()`; nothing about the
`Registry` or `Runner` themselves cares whether a plugin arrived through discovery or was added by
hand for a test.

This matters for testing too: calling `WordChunker().run(...)` directly exercises your own logic
and nothing else — no span, no error attribution, no blocking-call check, because none of those
attach to a bare method call. Run the same call through a `Runner` that has resolved a `StageSpec`
naming your plugin, and you get the registration seam for free, exactly as a real pipeline would:
`weft_kernel.seam.wrap` derives the span from your contract and plugin name, attributes any
escaping error to your pack, and raises `BlockingCallError`, naming your stage, if your `run()`
makes a blocking call — file IO, a synchronous socket, `time.sleep` — on the event loop thread
(fitness function 7(b)), categorically rather than past some tolerated duration. A pack with an
expensive, CPU-bound `_split` step offloads it with `asyncio.to_thread`, the same pattern every
first-party pack in this repository uses, so the detector never fires on the one call that is
supposed to block a worker thread instead of the loop.

Phase 1 is what turns "name your plugin in a pipeline" into something `weft index`/`weft ask`
themselves can be pointed at, from a file rather than a Python script you write yourself.

## 6. Testing it

`examples/weft-example-chunker/tests/test_word_chunker.py` is this pack's own suite, and it needs
neither Docker nor the weft repository — `uv run pytest` from inside the pack's own directory is
enough, because its `pyproject.toml` states its own dev dependencies rather than borrowing weft's.
It exercises three things directly:

- **The happy path.** Construct `WordChunker()`, hand `run` a `Node` and a `Context`, and check the
  `Outcome` is `Produced` with one child per word — no mock, because contracts take and return
  domain types.
- **The empty edge case.** Blank content produces `NothingToProduce`, never an empty `Produced([])`.
- **Structural conformance.** `isinstance(WordChunker(), Chunker)` is `True` with no import of
  `Chunker` anywhere in `word_chunker.py` itself — the caller's own check that the contract really
  is satisfied structurally, not merely by convention.

## 7. What happens when the pack is refused

Weft is **open by default**: install this pack with no `[packs] allow` list anywhere, and it is
discovered and runs. An operator who wants an exact pin writes one in `weft.toml`, and it is
**exhaustive when present** — anything installed but unlisted is refused. With such a list present
and `"weft-example-chunker"` left off it:

| What happens | Detail |
|---|---|
| The module is **never imported** | Refusal precedes execution, checked before the entry point is ever loaded — or it is not refusal |
| `weft plugins doctor` reports it `refused` | The same status vocabulary — `active`, `refused`, `failed`, `partial`, `allowed, not installed` — reports every reason a pack is not contributing, in one place |
| Naming the plugin anywhere raises `UnknownPluginError` | A refused pack registered nothing, so `Registry.entry` cannot tell it apart from "never installed" — it names the contract, the plugin name that was wanted, and every name that *is* registered. Telling *why* apart is `doctor`'s job, not resolution's |
| The fix is one line | Add `"weft-example-chunker"` to `[packs] allow` in `weft.toml` |

One honest gap: `docs/03-cli.md`'s exit-3-for-refused / exit-4-for-missing split is real, but today
it only covers the four distributions `weft index`/`weft ask` hardcode — there is no CLI path yet
that resolves a pipeline naming *your* plugin, so nothing translates its `UnknownPluginError` into
one exit code or the other. A script you write yourself, per §5, sees the exception directly.

Two things you may optionally ship, and one you must:

- **`DISCLOSURE`** — an optional module-level `weft_kernel.discovery.Disclosure(network=…,
  filesystem=…, subprocess=…, note=…)`, read right after import and before `register()`. `doctor`
  prints it, or prints "not disclosed" if you skip it. It is information for the operator, never a
  claim Weft checks or enforces — see `02` §2 for why in-process enforcement is not on offer.
- **A permission class**, mandatory with no default, if your pack ships a CLI command — not this
  pack, and not anything Phase 0's CLI supports yet (Phase 3, after gate **G8**).
- **Nothing else.** No manifest, no capability grant, no plugin API version handshake. A pack runs
  with your full privileges the moment it is installed and permitted; installing is trusting,
  stated rather than simulated.

## 8. Open gates you may hit

A pointer to [`docs/05-grilling-sessions.md`](../docs/05-grilling-sessions.md), never a summary of
it — when a gate closes, that document changes and this list does too.

| Gate | Status | What it means for you |
|---|---|---|
| **G2** — pipeline derivation semantics | **Settled** | Pipelines derive (§3 below is the sequel this settling made possible); two packs claiming one plugin name is still a refusal, relaxed only by an operator's pin in `weft.toml` |
| **G7** — event bus or explicit extension points | **Settled** | **No bus.** A pack participates only by registering against a published extension point — `SourceDeletable`/`Reconcilable` (§3 below) are what that ruling added to the store family, not a way to observe every node ambiently |
| **G8** — is the REPL agentic | **Settled** | No, and it never becomes one — irrelevant to writing a pack unless you plan to ship an interactive `Command` |
| **G9** — contract versioning and deprecation | **Settled** | What every dependency specifier you write must look like, what your own `ExtModel` now requires, and what a deprecation warning obliges you to do — §3 below is entirely this ruling's consequences for a pack author |
| **G10** — release and support policy | Open | Whether the surfaces you depend on (§3's `permission_class`, `[packs] allow`, the filter AST) carry a stability promise before Weft's own 1.0 |
| **G12** — permissions when the caller is never a TTY | Open | Only if your command expects an interactive confirmation — what a non-TTY caller (a script, an agent) gets instead |

`docs/README.md`'s own decision log is the current source, never this table restated from memory — it is what told this guide G2/G7/G8/G9 had closed since it was first written.

## 9. A pack spanning several contracts, plus a command

Everything above is one pack, one contract. `docs/02-extension-model.md` §4 specifies the other
shape — a capability spanning several extension points is still **one package** (requirement 2) —
using a graph add-on as the worked example: it registers an `Enhancer`, a store, a `Retriever`, two
`Command`s, a named pipeline and a slot contribution, and (per **G7**) `SourceDeletable` and
`Reconcilable` besides. That pack does not exist yet — task 5.4 builds it — so this section adapts
the same case from what already does exist and is already checked: `examples/weft-example-ingest/`
(seven contracts, a pack-owned `ExtModel` and — since task 5.3a — a slot contribution, from one
entry point) and `examples/weft-example-command/` (a contributed `Command`). Where a real, tested
pack demonstrates a row, this section shows it, tagged the identical way §1–§7 already are. **Where
none does yet, it says so rather than inventing a snippet no check would cover** — §9.8 below is
exactly that, recorded in this phase's own ledger entry (task 5.3, `docs/build-ledger.md`) rather
than papered over. §9.7 used to be the other one; task 5.3a closed that gap, and its own ledger
entry says so.

### 9.1 One entry point, one `register()`, several contracts

```python path=examples/weft-example-ingest/src/weft_example_ingest/__init__.py
"""A stranger's ingest-side pack — the independence proof for the pipeline's first half.

`docs/07-extension-cost.md` §2 clause (c), the task 2.11 backfill: every contract Phase 0
through Phase 2 publishes on the ingest side needs an implementation that lives *outside*
this repository's workspace, installed the same way any third-party pack would be,
registering through the same `weft.packs` entry point every first-party pack uses — no
shortcut, no private import path. `examples/weft-example-chunker` is the precedent this
pack's file shape copies exactly; the difference is scope, not mechanism — one distribution
covering `Extractor`, `Renderer`, `Cleaner`, `Enhancer`, `Embedder`, `Expander` and the whole
`NodeStore` capability family (`NodeStore`, `VectorSearch`, `TextSearch`, `MetadataFilter`),
per `.phase2-design.md` §9's "one multi-contract pack per publishing half" — clause (c) is
set equality over *contracts*, which a multi-point pack satisfies, and a single install
registering across many extension points is exactly requirement 2, the thing Weft exists to
make cheap.

`tests/architecture/test_ff9c_every_contract_has_a_stranger.py` installs this distribution
(built as a real wheel) into a throwaway environment, with the `weft` repository nowhere on
`sys.path`, and asks the resulting registry which contracts it registered under and which
capability Protocols its registered classes satisfy.
"""

from pydantic import BaseModel, ConfigDict

from weft_clean.contract import Cleaner
from weft_embed.contract import Embedder
from weft_enhance.contract import Enhancer
from weft_example_ingest.cleaner import ExampleBlankLineCollapser
from weft_example_ingest.embedder import ExampleChecksumEmbedder
from weft_example_ingest.enhancer import ExampleWordCountEnhancer, WordCount
from weft_example_ingest.expander import NAME as EXPANDER_NAME
from weft_example_ingest.expander import ExampleFirstSentenceExpander
from weft_example_ingest.extractor import ExampleExtractor
from weft_example_ingest.renderer import ExamplePlainRenderer
from weft_example_ingest.store import InMemoryNodeStore
from weft_extract.contract import Extractor, Renderer
from weft_index.contract import Expander
from weft_kernel.discovery import PackRegistrar
from weft_kernel.pipeline import StageDeclaration
from weft_store.contract import NodeStore

#: This pack's own local id for the stage it contributes into a slot — task 5.3a (S8).
#: Unqualified: `Contribution.stage.id` is a pack's local name, qualified by distribution
#: only once actually placed (`weft_kernel.resolution.Contribution`'s own docstring).
_ENRICH_STAGE_ID = "wordcount"

#: The slot name this pack offers into — `02` §3 → *Slots*' own worked example
#: (`weft-graph:entities`) targets a slot named `enrich`; this pack reuses that name
#: rather than inventing a second convention for the identical kind of position.
ENRICH_SLOT = "enrich"


class Settings(BaseModel):
    """This pack takes no settings — an empty model is still the required shape."""

    model_config = ConfigDict(frozen=True, extra="forbid")


def register(registrar: PackRegistrar, settings: Settings) -> None:
    """Register this pack's seven plugins — one per contract it implements — its own
    `WordCount` `ExtModel` (task 5.2g), and a slot contribution (task 5.3a, `S8`): the real
    proof that a stranger's own contributed stage reaches a resolved pipeline with no core
    edit, since this distribution is installed rather than linked (fitness function 9(a)).

    The contribution reuses the same `example-enhancer` plugin already registered under
    `Enhancer` — offering a plugin as both an ordinary stage *and* a slot contribution costs
    nothing extra to declare, and it is the identical class either way: what changes is only
    whether a pipeline document names it directly (`use: example-enhancer`) or opts a slot
    into receiving it (`slots: [{id: enrich, ...}]`).
    """
    del settings
    registrar.add(Extractor, "example-extractor", ExampleExtractor)
    registrar.add(Renderer, "example-renderer", ExamplePlainRenderer)
    registrar.add(Cleaner, "example-cleaner", ExampleBlankLineCollapser)
    registrar.add(Enhancer, "example-enhancer", ExampleWordCountEnhancer)
    registrar.add(Embedder, "example-embedder", ExampleChecksumEmbedder)
    registrar.add(Expander, EXPANDER_NAME, ExampleFirstSentenceExpander)
    registrar.add(NodeStore, "example-store", InMemoryNodeStore)
    registrar.add_ext_model(WordCount)
    registrar.add_contribution(
        ENRICH_SLOT, StageDeclaration(id=_ENRICH_STAGE_ID, use="example-enhancer")
    )


__all__ = ["ENRICH_SLOT", "Settings", "WordCount", "register"]
```

Notice what stayed identical from the single-contract case in §3 above: **one** entry point, **one**
`register(registrar, settings)`, **one** `Settings` model — even though this pack answers to seven
`registrar.add` calls across six different contracts (`Extractor`, `Renderer`, `Cleaner`, `Enhancer`,
`Embedder`, `Expander`) plus `NodeStore`. Nothing about the registration mechanism changes with scope;
only the number of calls inside one function does. Registration is still transactional over all seven
at once — a `register()` that raised after the fifth `add` would commit none of them, exactly as it
would for one.

**An eighth and ninth capability arrive with no ninth `registrar.add` call.** `InMemoryNodeStore`
(`examples/weft-example-ingest/src/weft_example_ingest/store.py:51-166`) also implements
`delete_source` and `reconcile`/`estimate`, so it satisfies `SourceDeletable` and `Reconcilable`
(`docs/02-extension-model.md` §1 → *The store contract family*, G7) **structurally**, the same way
`WordChunker` in §4 above satisfies `Chunker` with no import of it. `weft delete`'s fan-out and
`weft reconcile`'s convergence find this store without you registering anything beyond the one
`NodeStore` line — "capability is derived, never declared" applies exactly as much to a nine-contract
pack as to a one-contract one.

### 9.2 Contributing a command: `permission_class` and `help` are mandatory

```python path=examples/weft-example-command/src/weft_example_command/greet.py
"""`GreetCommand` — a stranger's `Command`: one CLI-invoked action with no pipeline behind it.

Deliberately not a copy of one of `weft-cli`'s own five built-ins with different words — a
third party has no reason to reimplement `weft index` or `weft ask`, so this one is the
smallest genuinely different action the `Command` contract permits: it takes one argument,
touches no registry, no store and no network, and returns a typed greeting. It exists to prove
the same thing `weft_example_chunker.WordChunker` proves for `Chunker`: any implementation
satisfying `weft_command.contract.Command` structurally is usable, registered through the
identical `weft.packs` entry point `weft-cli`'s own built-ins use — no shortcut, no private
import path, `docs/03-cli.md` → *Plugin-contributed commands*' own worked example
(`weft graph build`) realised for a namespace that happens to be `greet` instead of `graph`.
"""

from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

from weft_command.contract import CommandResult
from weft_command.permission import PermissionClass
from weft_kernel.context import Context
from weft_kernel.payload import Outcome, Produced


class GreetArgs(BaseModel):
    """`weft greet <name>` — one required positional, the shape `weft_cli.argparse_gen`
    (task 3.2) turns into a positional argument because it carries no default.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(description="who to greet")


class GreetResult(CommandResult):
    """What `weft greet` produced — a typed result a renderer formats, never printed text
    (`docs/03-cli.md` → *Two modes, one implementation*), exactly as `weft-cli`'s own
    `IndexCommandResult` and friends are.
    """

    greeting: str


class GreetCommand:
    """Satisfies `weft_command.contract.Command` structurally — this class never imports it,
    the same path `docs/02-extension-model.md` describes for a third-party plugin.

    `permission_class` and `help` are both mandatory declarations
    (`Command.required_declarations`); omitting either refuses registration, loudly, at the
    point this pack's own `register()` runs — proven directly by
    `tests/test_greet.py::test_greet_without_a_declared_permission_class_is_refused`.
    """

    args_model: ClassVar[type[BaseModel]] = GreetArgs
    result_model: ClassVar[type[CommandResult]] = GreetResult
    permission_class: ClassVar[PermissionClass] = PermissionClass.READ
    help: ClassVar[str] = "greet somebody by name"

    def __init__(self, config: object = None) -> None:
        # No `with:`-style configuration this command takes — the registry's factory call
        # always passes something (`None` here, since nothing registers it with a `with:`
        # block), so the parameter exists to accept that, not to be used.
        del config

    async def run(self, args: BaseModel, ctx: Context) -> Outcome[CommandResult]:
        del ctx  # no service or locale this command needs
        assert isinstance(args, GreetArgs)
        return Produced(value=GreetResult(greeting=f"Hello, {args.name}!"))
```

`weft_command.contract.Command.required_declarations = ("permission_class", "help")`
(`packages/weft-rag/src/weft_command/contract.py:196`) — the identical mechanism `Chunker`'s
`destroys` already uses in §4 above, applied to a second contract. Omit either and your pack's own
`register()` raises at the point it calls `registrar.add(Command, ...)`, naming your class and the
missing declaration, never a stack trace three layers into `weft-cli`. There is **no default**:
`PermissionClass` has five members (`read`, `write`, `overwrite`, `destroy`, `network`,
`packages/weft-rag/src/weft_command/permission.py:30-44`) and falling back to `read` would
silently under-protect a destructive command, so silence is refused rather than defaulted.

```python path=examples/weft-example-command/src/weft_example_command/__init__.py
"""A stranger's `Command` pack — the independence proof, as an artifact.

Fitness function 9's shape, applied to `weft_command.contract.Command` for the first time:
a pack that lives *outside* the `weft` repository's workspace, in its own directory with its
own `pyproject.toml`, installed the same way any third-party pack would be, registering one
plugin through the same `weft.packs` entry point every first-party pack uses — no shortcut, no
private import path. `weft`'s `tests/architecture/test_ff9c_every_contract_has_a_stranger.py`
installs this distribution into a throwaway environment built from wheels, with the `weft`
repository itself nowhere on `sys.path`, and confirms `"example-command"` registers under
`Command` there — clause (c)'s obligation for the contract task 3.2 activated by rewiring
`weft-cli`'s own built-ins onto it (task 3.1 shipped the contract with nothing registered yet,
so clause (c) had no subject; task 3.2's own registrations are what made this pack necessary,
and this is it).
"""

from pydantic import BaseModel, ConfigDict

from weft_command.contract import Command
from weft_example_command.greet import GreetCommand
from weft_kernel.discovery import PackRegistrar


class Settings(BaseModel):
    """This pack takes no settings — an empty model is still the required shape."""

    model_config = ConfigDict(frozen=True, extra="forbid")


def register(registrar: PackRegistrar, settings: Settings) -> None:
    """Register `GreetCommand` as `"greet"` for `Command` — the only plugin here."""
    del settings
    registrar.add(Command, "greet", GreetCommand)


__all__ = ["GreetCommand", "Settings", "register"]
```

A command pack is otherwise exactly §3's shape: one entry point, one `register()`, one `Settings`
model. Nothing about contributing a `Command` needs a second mechanism.

### 9.3 The dependency specifier: a version requirement, or it is not one

**G9, settled 2026-08-21** (`docs/README.md` decision log): *"a version requirement **is** the
dependency specifier... ranges are `>=X,<MAJOR+1`, never an exact pin — a library that pins exactly
makes any two packs jointly unresolvable"* (`docs/09-release.md` §2.3, answer 5). A bare name —
`dependencies = ["weft-rag"]` — is not a specifier at all: it tells the resolver "any version,
including one whose contract has moved out from under you since you wrote this line," which is
exactly the silent incompatibility a semver policy exists to prevent. Task **5.2a** made this real for
every first-party distribution; the shape to copy is any of them, unchanged since:

```toml path=packages/weft-qdrant/pyproject.toml
[project]
name = "weft-qdrant"
version = "0.1.0"
description = "First-party Qdrant store pack. Registers under the store contract family weft_store publishes."
requires-python = ">=3.12"
license = "MIT"
license-files = ["LICENSE", "NOTICE"]
# `qdrant-client` is Apache-2.0, so it widens nothing an MIT library asks of the people
# who install it. The floor is the version this pack's behaviour was measured against; a
# claim about an older release would be a claim nobody here has checked.
#
# **No ceiling, and that is a repair.** This read `<1.14` so that resolution would not
# outrun `compose.yaml`'s pinned `qdrant/qdrant:v1.12.4` and make the conformance kit emit
# the client's own version warning. That put a *test fixture's* concern into the dependency
# range every downstream install resolves against, and the client's rule is symmetric —
# "major versions should match and minor version difference must not exceed 1" — so a
# client capped at 1.13 is out of its supported window against any server at 1.15 or later.
# An operator pointing this pack at a current deployment could not widen the range without
# editing a file in this repository, which is the one cost this project will not pay. The
# warning itself is something they *can* act on: align the server and the client. The dev
# environment's own alignment with `compose.yaml` lives in the workspace root's
# `[tool.uv] constraint-dependencies`, where a fixture pin belongs.
# `weft-rag` replaces the `weft-store` pin this used to carry: `weft_store` — the module whose
# store contract family this pack registers against — now ships inside that one wheel. The
# import is unchanged; only the name that delivers it is. Note the cost this makes visible:
# an operator who wants Qdrant and not Postgres still gets `psycopg`, because `weft-rag`
# declares it. That is the honest price of one wheel, recorded rather than hidden.
dependencies = ["weft-kernel>=0.1.0,<1.0.0", "weft-rag>=2.1.0,<3.0.0", "qdrant-client>=1.12"]

# The one entry point a pack declares (`docs/02-extension-model.md` section 2).
[project.entry-points."weft.packs"]
qdrant = "weft_qdrant:register"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

Two different shapes appear on that one line, and both are correct for what they name:
`weft-kernel>=0.1.0,<1.0.0` and `weft-rag>=2.1.0,<3.0.0` are G9 ranges — **dependencies on
contract-publishing distributions**, each bound to the major that would break it. `qdrant-client>=1.12`
is an ordinary PyPI floor on a library Weft does not publish a contract for — G9's range rule binds a
*contract's* version to its *publisher's* distribution version; it says nothing about a floor on an
unrelated third-party package, and inventing an upper bound for those would be exactly the "any two
packs jointly unresolvable" trap the rule exists to prevent, aimed at yourself. When you depend on
`weft-rag` (or any contract-publishing distribution) for a Protocol one of its packs owns, write
the range;
when you depend on an ordinary library, write the floor you actually require and nothing more.

**This paragraph used to record an honest gap, and the gap is closed.** Every
`examples/*/pyproject.toml` in this tree once declared its `weft-*` dependencies as bare names —
these packs predate G9 (2026-08-21), and task 5.2a touched only the distributions under
`packages/`, so the thing a pack author copies was teaching that bounds are optional. **Ledger task
6.26 closed it**, and `tests/architecture/test_example_packs_are_exemplars.py` is what keeps it
closed. Every example pack now declares `>=X,<MAJOR+1` on each `weft-*` dependency, so the shape
above is the shape to copy — this note stays only because a reader who saw the old paragraph
deserves to know what happened to it rather than to find it silently gone.

### 9.4 An `ExtModel` needs `__schema_version__`, and an `upgrade` that refuses

```python path=examples/weft-example-ingest/src/weft_example_ingest/enhancer.py
"""`ExampleWordCountEnhancer` — a stranger's `Enhancer`: attaches a word count, never rewrites text.

`weft_enhance.contract.Enhancer`'s own distinction from `Cleaner` at the same input/output
shape: a fact is *added* via `Node.with_ext`, `content` is untouched, and node identity
(`node.id`) does not move.
"""

from collections.abc import Sequence

from weft_kernel.context import Context
from weft_kernel.payload import ExtModel, Node, NothingToProduce, Outcome, Produced


class WordCount(ExtModel):
    """This pack's own namespaced fact: how many whitespace-separated words `content` has."""

    __namespace__ = "weft-example-ingest"
    __schema_version__ = "1.0.0"

    count: int


class ExampleWordCountEnhancer:
    """Attaches a `WordCount` to every node it is handed. Satisfies `weft_enhance.contract.
    Enhancer` structurally — this class never imports it.
    """

    def __init__(self, config: object = None) -> None:
        del config

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        del ctx
        if not payload:
            return NothingToProduce(reason="no node to enhance")
        enhanced = [node.with_ext(WordCount(count=len(node.content.split()))) for node in payload]
        return Produced(value=enhanced)
```

**Both class-level declarations are mandatory**, checked at class *definition*, before your pack ever
runs (`packages/weft-kernel/src/weft_kernel/payload/ext.py:88-101`,
`ExtModel.__pydantic_init_subclass__`): omit `__namespace__` or `__schema_version__` and `TypeError`
raises the moment Python finishes building your class — at import time, not at the first `with_ext`
call or the first read off a store. `__schema_version__` is G9's own addition (task 5.2c) beside the
`__namespace__` declaration §1 above already required, and for a mechanical reason rather than a
stylistic one: **a contract version cannot stand in for a schema version, because the contract version
is not available at the read site** — when a store rehydrates a row your pack wrote, your pack may not
even be installed. So the version travels *in the data itself*: every namespace your `ExtModel`
serialises carries its own `__schema_version__` key alongside its fields
(`weft_kernel.payload.ext._dump`, same file, lines 131-164).

**A reader upgrades or refuses, and the default refuses.** `ExtModel.upgrade(data, from_version)`
(`ext.py:103-116`) raises `SchemaVersionRefusedError`, naming your namespace, the version the row was
stored at and the version your installed class declares, unless you override it. You override
`upgrade` the day you actually change `WordCount`'s shape — add a field, rename one, change a type —
and need to reconcile a row a user's store already holds; until then, the default is correct and
`1.0.0` (what every `ExtModel` in this tree carries today, first-party and stranger alike, since
nothing has shipped a second shape of any of them) needs no override at all.

### 9.5 `add_ext_model` — your `ExtModel` reaches a store only if you offer it

Look again at §9.1's `register()`: the last line is `registrar.add_ext_model(WordCount)`, beside the
seven `registrar.add` calls. **This is not optional if you want a node carrying your namespace to
survive a round trip through a store.** Task 5.2g closed a real gap here — before it, a pack's
`register()` did not contribute its `ExtModel`s automatically at all, and a namespace nobody
registered raised `UnknownPluginError` the moment a store tried to rehydrate it. The kernel itself
stays capability-blind: `registrar.add_ext_model` (`packages/weft-kernel/src/weft_kernel/discovery.py:392-405`)
buffers a bare class reference — no validation, no instantiation — exactly like `add_pipeline_resource`
and `deprecate` below; turning that buffer into something a store can actually use is
`weft_store.rehydrate.register_from_reports`'s job, called once by whatever already calls `discover()`,
with no pack named at that call site (`docs/02-extension-model.md` §1's own "Built in Phase 5 task
5.2g" block has the full mechanism).

**Call it only for an `ExtModel` that attaches to `Node.ext`.** `docs/lessons.md` L5.20 is the
measurement this rule rests on: several first-party `ExtModel`s (`weft_retrieve.boolean.BooleanPlan`,
`weft_generate.contradiction.Agreement`, among others) attach to `QuerySet.ext`, `Candidates.ext` or
`Answer.ext` instead — the query path's own extension points — and *none* of them calls
`add_ext_model`, correctly: only a `Node` is ever handed to a `NodeStore`, so a query-path `ExtModel`
never needs to survive a store round trip, and registering it anyway risks a `DuplicateRegistrationError`
the moment two packs sharing a namespace are both active. If the `ExtModel` you are writing lives on
`Node.ext` (via `Node.with_ext`/`Node.ext_as`, as `WordCount` does above), call `add_ext_model`. If it
lives on a query-path payload's `ext`, do not.

### 9.6 Shipping a named pipeline

`registrar.add_pipeline_resource(package, resource)` buffers a pipeline document the same way
`add_ext_model` buffers a class — attributed to your pack, committed only once `register()` returns
without raising. `weft-retrieve` ships three this way:

```text
registrar.add_pipeline_resource("weft_retrieve", "pipelines/route.yaml")
registrar.add_pipeline_resource("weft_retrieve", "pipelines/no-retrieval.yaml")
registrar.add_pipeline_resource("weft_retrieve", "pipelines/retrieve-then-generate.yaml")
# packages/weft-rag/src/weft_retrieve/__init__.py:369-371
```

`package` and `resource` are read together as an `importlib.resources` path inside your own installed
distribution — ship the YAML file under your package, call `add_pipeline_resource` once per document,
and `weft_cli.pipeline_catalogue.load_contributed` makes it visible to `weft pipeline list`/`show` and
to `--pipeline <name>` the moment your pack is installed, with no core edit.

### 9.7 Contributing into a slot

`docs/02-extension-model.md` §3 → *Slots* specifies the design: a pack "may ship complete named
pipelines, and it may contribute into a slot a pipeline opted into," never rewrite one that did not
ask. **Task 5.3a (`S8`) is what let a pack actually reach it.** Buffer one from `register()` the
identical way you already buffer a pipeline resource or an `ExtModel`:

```text
registrar.add_contribution(ENRICH_SLOT, StageDeclaration(id=_ENRICH_STAGE_ID, use="example-enhancer"))
# examples/weft-example-ingest/src/weft_example_ingest/__init__.py:79-81
```

`add_contribution(slot, stage)` — `discovery.py`'s own `PackRegistrar` — takes the slot name a
pipeline document opted into and a `weft_kernel.pipeline.StageDeclaration` naming your plugin.
`stage.id` is your **local**, unqualified name — never write the `distribution:` prefix yourself;
attribution is filled in for you the identical way `add`'s own `distribution` argument is, and
`resolve()` prefixes it only once the contribution is actually placed (`weft-graph:entities`, `02`
§3's own worked example spelling). Buffered, not written through immediately — a `register()` that
raises after calling this leaves no slot looking filled that was never actually committed, the same
atomicity `add_pipeline_resource`/`add_ext_model`/`deprecate` already give you.

You do not assemble anything yourself, and you do not call `resolve()` yourself. Every installed
pack's own buffered contributions reach every pipeline command through one path you never touch:
`weft_cli.registry_bootstrap.build_dependencies` reads `PackReport.contributions` back off
`discover()`'s own return value, concatenates every report's tuple into `Dependencies.
contributions`, and every `resolve()` call site in `weft_cli` passes that field straight through as
`contributions=`. Your one line above is the entire pack-author-facing surface of this mechanism.

**What you do not control**, because §3's own rule forbids it: whether your contribution actually
lands anywhere. It places only in a pipeline whose author declared a slot by the exact name you
targeted (`slots: [{id: enrich, after: chunk}]` in *their* document) — never in one that did not
ask, and installing your pack cannot make one opt in retroactively. Name a slot no pipeline
declares and your contribution is a recorded no-op: it shows up in `weft pipeline show`'s own
`unplaced_contributions`, and `weft plugins doctor` flags your distribution as contributing to no
pipeline at all, so "installed and doing nothing" stays visible rather than silently swallowed.

`examples/weft-example-ingest` — installed rather than linked, the fitness-function-9(a) pack this
guide's own §5 already runs from an empty directory — offers its own already-registered `Enhancer`
plugin into a slot named `enrich` this exact way; read its `register()` for the real, working line.

### 9.8 A deprecation warning obliges a changelog entry

`registrar.deprecate(surface, reason=...)` (`discovery.py:376-390`) buffers a notice — a plugin name,
a `"Contract:name"` pair, or your pack itself — attributed to your distribution and committed with
everything else `register()` buffers. Once committed, `weft_kernel.seam.warn_deprecated`
(`packages/weft-kernel/src/weft_kernel/seam.py:211-229`) emits one `DeprecationWarning` per notice,
automatically, the moment discovery activates your pack — you state the fact once and never write the
warning by hand, and `weft plugins doctor` surfaces it as a flag beside your pack's ordinary status.

**What it obliges you to do next is written down, not left to memory.** `docs/09-release.md` §3:
*"Removal is a changelog entry with a migration line or it does not happen."* If your pack ships
inside this repository (a first-party pack), `tests/docs/test_changelog_deprecation_coverage.py`
enforces it directly: every surface any installed pack has marked deprecated must appear, backtick-quoted,
in `CHANGELOG.md`'s own `### Deprecated` section, or `ci-checks` fails naming exactly which surface is
missing. **That check reads *this repository's* `CHANGELOG.md`** — if your pack lives outside this
workspace, as every pack this guide otherwise describes does, nothing here can see your own repository
at all, so nothing enforces your own changelog for you. The obligation is the same regardless: a
deprecation without a changelog entry naming it and the release it disappears in is a promise the
warning made and the paper trail did not keep. Hold your own repository to the identical discipline
this one enforces on itself.
