# Writing a pack

Written for someone who has not read the plan. You need Python 3.12+ and `uv`, and nothing else —
no `weft/` directory to touch inside this project, no plugin manifest to append to, no registry
file anywhere in Weft that will learn your pack's name.

This guide is not a hypothetical. It walks the exact pack Weft keeps installed *outside its own
workspace* to prove the claim every capability here rests on — `examples/weft-example-chunker/` —
and every code block below is that pack's real file, checked in CI: if the file changes, this page
is wrong until it changes too. Definitions link to
[`docs/02-extension-model.md`](../docs/02-extension-model.md) §1–§2 rather than restating them.

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
# those two ship. weft-chunk is depended on for the one thing a third-party
# chunker pack needs from it: the `Chunker` Protocol it publishes — the same
# relationship docs/07-extension-cost.md section 1 states for any pack that
# implements a contract it does not itself define.
dependencies = ["weft-kernel", "weft-chunk"]

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

- **You depend on `weft-chunk`, not on the kernel alone.** The kernel names no capability and
  publishes no `Chunker`; contracts ship from the packs that own them. You depend on the contract's
  publisher exactly as you would on any third-party protocol — `weft-kernel` alone would not even
  give you something to import against.
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
| **Every contract method is `async def`.** No sync protocol, no colour to declare | G6. You never write `asyncio.run` — the tree contains exactly one, in `weft-cli` (fitness function 7(a)) |
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

| Gate | What you would hit |
|---|---|
| **G2** — pipeline derivation semantics | Two packs both wanting the name `example-chunker`; inserting a stage into someone else's pipeline; whether pipelines end up authored in YAML, Python or both. Phase 0 raises on duplicate registration and builds no derivation at all — reversible, not an answer |
| **G7** — event bus or explicit extension points | Wanting to observe every indexed node without owning a stage in the pipeline |
| **G8** — is the REPL agentic | Nothing, unless you plan to ship an interactive command |
| **G9** — contract versioning | What a future `weft-chunk` major version owes you, and what you owe your own users once an `ExtModel` you publish gains a required field |
