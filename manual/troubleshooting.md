# Troubleshooting

What each loud failure looks like, and the first thing to try. This page does not re-argue why the
trust model is shaped the way it is, why a store never embeds, or why deletion cascades — that
reasoning belongs to [`docs/02-extension-model.md`](../docs/02-extension-model.md) and is linked,
never restated. [`manual/operations-guide.md`](operations-guide.md) already covers `doctor`'s status
vocabulary and the exit-code split in full, with the container and `weft.toml` context around them;
this page exists for the moment you already have an error in front of you and want to know what it
is and what to do about it — one entry per failure mode Weft can raise, matched by name.

**Two audiences, sharing one page.** Most entries below are things a `weft` command can put in front
of you directly. A few are things you only hit while writing or testing a pack of your own, driving
the kernel's Python API rather than the CLI — those say so, so you are not left hunting for a command
line that produces them.

**One habit that helps with one entry here:** `WEFT_TRACEBACK=1 weft ...` re-raises the underlying
exception in full — but only for [the one case below](#an-error-weft-did-not-translate) where `weft`
did not translate the exception at all. Every other exception this page documents is a `WeftError`
subclass, and those are always printed as the one line `str(exc)` produces, `WEFT_TRACEBACK` or not
(the five *Doctor statuses* at the foot are not exceptions at all, and nothing about them changes
either) — see
[`manual/operations-guide.md`](operations-guide.md) → *The one thing to know about `active`* and →
*Exit codes* for where that split is scoped and reproduced. Every reproduction below is the one-line
form a user actually sees.

---

## Errors nothing translated — `weft_cli.cli`

### An error weft did not translate

**Not a `WeftError` subclass** — no `### \`name\`` heading, because this is not one named class but
`main`'s last-resort catch around whatever a pack, a driver, or the standard library raised that no
handler recognised. It is the failure mode a first run is most likely to actually hit, because it is
what an unreachable database looks like through `weft ask`, which resolves its store directly rather
than through a stage. Reproduced from a scratch directory with `weft.toml` naming a dead port:

```text
$ weft ask "hello"
weft ask: OperationalError: connection failed: connection to server at "127.0.0.1", port 9999
failed: could not receive data from server: Connection refused
This is an error weft did not translate — the message above comes from the library that raised it.
Re-run with WEFT_TRACEBACK=1 for the full traceback.
$ echo $?
1
```

This is the one place on this page where the `WEFT_TRACEBACK=1` habit the intro advertises actually
gives you something new — the full traceback instead of one line, because `_report_unexpected`
(`weft_cli.cli`) is the only reader of that variable and it only runs here, never for a `WeftError`.
**What to do:** the type name and message are the library's own — an `OperationalError` almost
always means the database is unreachable (check the container and the `dsn`); for anything else,
re-run with `WEFT_TRACEBACK=1` and read the traceback for which library raised it and from where.

---

## Registration and lookup — `weft_kernel.registry`

### `DuplicateRegistrationError`

**What it looks like.** Two installed packs' `register()` calls both claim the same name under the
same contract — reproduced directly against a `Registry`, the same check every pack's `register()`
goes through:

```text
DuplicateRegistrationError: 'fixed' is already registered for Chunker by distribution 'weft-chunk';
distribution 'acme-chunk' cannot register it too. Weft refuses on duplicate registration rather than
arbitrating between them — rename one, or see the duplicate-name trap in docs/06-phase-0-build.md.
```

You will not see this raised as a bare traceback from `weft`: it is caught inside pack activation and
folded into the *second* pack's `weft plugins doctor` report as `failed`, naming the collision in its
`reason` line — the first-registered pack stays `active`. **What to do:** rename the losing plugin
under a distinct name, or refuse one of the two packs via `[packs] allow` in `weft.toml`. Weft never
arbitrates between them silently, and never will inside Phase 0 — see the duplicate-name trap in
`docs/06-phase-0-build.md`.

### `UnknownPluginError`

**What it looks like**, resolving a plugin name nothing registered:

```text
UnknownPluginError: no 'sliding' is registered for Chunker. It is unavailable because no
distribution has registered that name for this contract. Names registered for Chunker: 'fixed'.
```

`weft index` and `weft ask` both catch this at the top level and exit `4` (`RESOLUTION_FAILED`) with
the message printed as-is — no traceback. It also reaches through the store's own rehydration path
(`weft_store.rehydrate`) with the same message shape, naming an `ExtModel` namespace instead of a
plugin name, if a stored node's `ext` data names a namespace nothing registered:

```text
UnknownPluginError: no 'acme-graph.summary' is registered for ExtModel. It is unavailable because no
distribution has registered that name for this contract. Names registered for ExtModel: 'weft-kernel'.
```

**What to do:** the message already lists every name that *is* registered for that contract — compare
it against what you typed. If the name is right and still missing, `weft plugins doctor` is the next
stop: the pack that should have registered it may be `refused`, `failed`, or simply not installed.

---

## Pack discovery and settings — `weft_kernel.discovery`

### `PackSettingsError`

**What it looks like** — reproduced two ways, both real. The one you will actually run into: a pack's
settings fail Pydantic validation, most often a required field like `weft-store`'s `dsn` left unset
with neither `weft.toml` nor `WEFT_DATABASE_URL` supplying it:

```text
$ weft plugins doctor
...
weft-store: failed (0 contributed)
  reason: 'weft-store' settings failed validation: 1 validation error for PgVectorSettings
dsn
  Field required [type=missing, input_value={}, input_type=dict]
    For further information visit https://errors.pydantic.dev/2.13/v/missing
  disclosure: not disclosed
```

The other shape — a pack author's own bug, not something a `weft` *user* causes — is `register()`
declared with the wrong shape: not exactly `(registrar, settings)`, or `settings` not annotated with a
`pydantic.BaseModel` subclass:

```text
PackSettingsError: 'acme-pack' declares register() with 1 parameter(s); docs/02-extension-model.md
requires exactly (registrar, settings).
```

Like `DuplicateRegistrationError`, this never reaches you as a bare traceback — it is always folded
into that pack's `weft plugins doctor` report as `failed`, with the message above as the `reason`.
**What to do, as a user:** fix the setting the reason names — for `weft-store`'s `dsn`, either export
`WEFT_DATABASE_URL` or add `[packs.weft-store] dsn = "..."` to `weft.toml`; see
[`manual/operations-guide.md`](operations-guide.md) → *Wiring `weft.toml`*. **As a pack author:** fix
`register()`'s own signature — it must match `register(registrar: PackRegistrar, settings:
YourSettingsModel) -> None` exactly.

### `UnknownPackSettingsError`

**What it looks like** — a `weft.toml` names a `[packs.<distribution>]` settings block for a
distribution nothing installed declares, reproduced against a real checkout:

```text
$ cat weft.toml
[packs.acme-graph]
endpoint = "http://localhost:1234"
$ weft plugins doctor
[packs] settings name 'acme-graph', which is not installed. Install the distribution, or remove its
settings block. Distributions that declare a 'weft.packs' entry point: 'weft-canary', 'weft-chunk',
'weft-embed', 'weft-extract', 'weft-store'.
$ echo $?
4
```

(`weft-canary` in that list is this repository's own test-only distribution — a real install of
`weft-cli` will not show it; the distribution list is otherwise exactly what got reproduced.) Unlike
`[packs] allow` naming an absent distribution (see `allowed, not installed` below, which is reported
and not fatal), a `packs:` settings block is a requirement, not a permission — `weft` refuses to build
a registry at all rather than silently ignore a settings block nobody will read. **What to do:** `uv
add` the distribution the block is meant to configure, or delete the block if it was left over from a
pack you no longer use.

### `MalformedDisclosureError`

**What it looks like** — a pack's module-level `DISCLOSURE` is present but is not a
`weft_kernel.discovery.Disclosure` instance:

```text
MalformedDisclosureError: 'acme-bad-disclosure' defines DISCLOSURE but it is not a
weft_kernel.discovery.Disclosure instance (found dict). DISCLOSURE must be built from
Disclosure(network=..., filesystem=..., subprocess=..., note=...).
```

Folded into that pack's `weft plugins doctor` report as `failed`, the reason above verbatim — never a
bare traceback. **What to do, as a user:** this is a bug in the pack, not in your configuration; file
it against the pack, or pin it out of `[packs] allow` until it is fixed. **As a pack author:** build
`DISCLOSURE` from `Disclosure(...)`, never a bare `dict` or any other shape.

### `MissingDistributionMetadataError`

**What it looks like** — an entry point in the `weft.packs` group carries no distribution metadata
(malformed or hand-built `.dist-info`):

```text
MissingDistributionMetadataError: entry point 'mystery' in group 'weft.packs' carries no distribution
metadata; weft cannot attribute it to a pack.
```

Folded into a `weft plugins doctor` report keyed by the entry point's own name, status `failed` — one
malformed package's metadata degrades to a single row, not a hard stop for every other pack. **What
to do:** reinstall the offending package; this almost always means its build metadata is corrupt or
was hand-edited, not that anything about your `weft.toml` is wrong.

### `EnvInterpolationError`

**What it looks like** — a `${env:VAR}` reference in `weft.toml` names a variable that is not set:

```text
'${env:WEFT_DATABASE_URL}' names an environment variable that is not set. Set WEFT_DATABASE_URL, or
remove the reference from the configuration.
```

Unlike the errors above, this one is **not** folded into a per-pack report — it is raised while
building the settings `weft.toml` itself references, before any pack's `register()` runs, and reaches
you as this one line at exit `4`. **What to do:** export the named variable, or remove the `${env:...}`
reference from `weft.toml` if you meant to configure the value directly instead.

---

## Pipeline resolution and running — `weft_kernel.runner`

### `PipelineResolutionError`

**What it looks like** — two checks share this class, both happening *before* any batch runs, never as
a runtime `KeyError`. A stage's `requires` names an `ExtModel` no earlier stage provides:

```text
PipelineResolutionError: stage 'chunk' (Chunker:fixed) requires 'Cleaned' — namespace 'acme-clean',
published by the pack of that name — but no earlier stage in this pipeline provides it.
```

Or two consecutive stages do not compose by type:

```text
PipelineResolutionError: stage 'chunk' (Chunker:fixed) expects <class 'dict'>, but the previous stage
'extract' produces <class 'list'>. Consecutive stages must compose by type.
```

Phase 0's built-in `index` pipeline is fixed and always resolves against a correctly installed
workspace, so an ordinary `weft index`/`weft ask` run does not hit this — it is what you get while
assembling your own `StageSpec` list against `weft_kernel.runner.Runner.resolve` directly, whether
that is a pack's own test suite or a future custom pipeline. **`weft index` and `weft ask` already
catch it at exit `4`**, the same as `UnknownPluginError`, should a custom pipeline reach either
command. **What to do:** the message names the exact stage and what would have made it pass — add the
missing upstream stage, or reorder so types line up.

### `TenantMismatchError`

**What it looks like** — a `ResolvedPipeline` built for one tenant is run with a `Context` for
another:

```text
TenantMismatchError: this pipeline was resolved for tenant 'tenant-a', but run() was given a Context
for tenant 'tenant-b'. An instance cached for one tenant must never run for another.
```

Phase 0's CLI builds exactly one `Context`, with a fixed `tenant_id="default"`, per invocation — this
is unreachable through `weft index`/`weft ask` as shipped. It exists for whoever drives
`weft_kernel.runner.Runner` directly across more than one tenant. **What to do:** resolve a separate
`ResolvedPipeline` per tenant — the instance cache is keyed by tenant precisely so a resolved pipeline
must never be reused across one.

### `FlushError`

**What it looks like** — one or more resolved stages failed to flush, raised once after every stage
was given its chance. Reproduced directly against `Runner`, driving the kernel's Python API rather
than the CLI:

```text
FlushError: 1 of 1 stage(s) failed to flush: 'store'.
```

The count is `len(pipeline.stages)` — a `weft index` run resolves Phase 0's built-in four-stage
pipeline (`extract`, `chunk`, `embed`, `store`), so the equivalent failure there reads `1 of 4
stage(s) failed to flush: 'store'.`, not `1 of 1`.

`__cause__` on the raised exception is the *first* underlying failure encountered
(`weft_kernel.runner`'s own `raise ... from failures[0]`) — but **there is no shipped way to see it
through `weft index` today.** `FlushError` is a `WeftError`; `handle_index` catches it and prints
`str(exc)` only, the same one line above, `WEFT_TRACEBACK` or not — `_report_unexpected`, the one
place that reads `WEFT_TRACEBACK`, only ever runs for [an exception no handler translated](#an-error-weft-did-not-translate),
and `FlushError` is always translated. This surfaces through `weft index` at exit `1`
(`OPERATION_FAILED`) if the store's connection drops between the last write and the end of the run.
**What to do:** the message names which stage failed to flush — for `store`, this is almost always a
dropped database connection; check the container is still up and reachable, and re-run `weft index`.
The run's already-written data is not lost (every stage got its chance to flush, one failing does
not stop the others), only the final flush.

---

## Services and messages — `weft_kernel.context`

Every entry in this section is unreachable through `weft index`, `weft ask` or `weft plugins
list|doctor` as Phase 0 ships them — nothing yet calls `ctx.require()` or `ctx.t()` from a built-in
stage. These are for a pack author's own stage code, or whoever assembles a `Context` directly.

### `UnresolvedServiceError`

**What it looks like** — `ctx.require()` asked for a contract nothing registered on this run:

```text
UnresolvedServiceError: no service is registered for LLM on this run. It is unavailable because
nothing resolved one before this stage ran. Services available on this run: TokenSink.
```

**What to do:** the message lists every service that *is* available — either the caller that built
this run's `Context` forgot to populate the one you need, or your stage is requiring a contract no
one is expected to supply yet.

### `DuplicateServiceError`

**What it looks like** — two instances registered for the same contract on one `ServiceRegistry`:

```text
DuplicateServiceError: a service for LLM is already registered on this run; a second registration
would leave it ambiguous which instance a stage gets back. Refused rather than silently overwritten.
```

**What to do:** whatever assembles the run's `Context` is registering the same contract twice —
remove the duplicate `services.add(...)` call.

### `UnknownMessageError`

**What it looks like** — `ctx.t()` asked for a key no pack's catalogue carries, for the locale asked:

```text
UnknownMessageError: no message 'farewell' is registered for locale 'en'. Messages available for
'en': greeting.
```

**What to do:** the message lists every key that *is* registered for that locale — a typo'd key reads
as a typo, not a mystery. If the key is genuinely missing, register it with
`MessageCatalogue.add(locale=..., key=..., template=...)` before the run starts.

### `DuplicateMessageError`

**What it looks like** — two templates registered for the same `(locale, key)`:

```text
DuplicateMessageError: message 'greeting' is already registered for locale 'en' as 'hi {name}'; a
second template ('hello {name}') would leave it ambiguous which one ctx.t() should return. Refused
rather than silently overwritten.
```

**What to do:** two packs (or two calls in your own setup code) are contributing the same message key
for the same locale — rename one key, or namespace it so the collision cannot happen.

### `MessageFormatError`

**What it looks like** — a template names a placeholder the caller's parameters did not supply:

```text
MessageFormatError: message 'greeting' for locale 'en' (template: 'hi {name}') could not be
formatted: KeyError('name'). Parameters supplied: none.
```

**What to do:** the message states the template and every parameter that *was* supplied — pass the
missing one to `ctx.t(key, **params)`, or fix the template if it names a placeholder that should not
be there.

---

## Blocking calls — `weft_kernel.blocking`

### `BlockingCallError`

**What it looks like** — a stage made a blocking call on the event loop thread while running:

```text
BlockingCallError: stage 'chunk:fixed' made a blocking call (time.sleep()) on the event loop thread.
Offload it — `await asyncio.to_thread(...)` — or use an async client instead. See fitness function
7(b), docs/01-high-level-plan.md.
```

This is a pack-author failure, caught the moment a stage under test makes `open()`, a blocking socket
call, `time.sleep()`, or `Popen.wait()`/`communicate()` while `weft_kernel.blocking.guard()` is armed
— which every registered stage's `run()` runs under, via the registration seam. **What to do:** the
message names the exact call — offload it with `await asyncio.to_thread(...)`, or replace it with an
async client (`httpx.AsyncClient`, an async database driver, `await
asyncio.create_subprocess_exec(...)`). This detector is categorical, not a threshold: there is no
config to loosen it with, and the fitness function it backs (7(b)) is why.

---

## Storage — `weft_store`

### `MalformedExtDataError`

**What it looks like** — a stored node's `ext` namespace value is not a mapping, so it cannot be
re-validated back into its typed model:

```text
MalformedExtDataError: stored ext namespace 'weft-kernel.synthetic-origin' is not a mapping (found
str); cannot rehydrate it.
```

Every namespace `weft-store` ever wrote came from `ExtModel.model_dump()`, which always produces a
mapping — this can only fire against data the store did not write itself. **What to do:** something
outside Weft edited the `weft_nodes.ext` column directly. Re-index the affected source rather than
hand-repairing the JSON; there is no supported path for hand-editing stored `ext` data.

### `UnsupportedFilterError`

**What it looks like** — `search_vector` was given a `Filter` the built-in pgvector store cannot yet
translate to SQL:

```text
UnsupportedFilterError: PgVectorStore.search_vector does not yet translate Filter to SQL — Phase 0
resolves no pipeline against a store's filter capability. Pass filter=None.
```

Unreachable through `weft ask` as shipped — Phase 0's CLI never constructs a `Filter`. This is for
whoever calls `search_vector` directly (a future `Retriever`, or a pack author's own test) with a
non-`None` filter before filter translation exists. **What to do:** pass `filter=None` until a later
phase's store implements filter translation; there is nothing to configure around this today.

---

## `weft ask` — `weft_cli.ask`

### `NotVectorSearchableError`

**What it looks like** — the registered `NodeStore` named `"pgvector"` does not also satisfy
`VectorSearch`:

```text
NotVectorSearchableError: the registered 'pgvector' NodeStore does not satisfy VectorSearch; weft ask
has nothing to search.
```

Unreachable with the built-in store, which always satisfies `VectorSearch` — this fires only if a
pack you installed registers its own `NodeStore` under the name `"pgvector"`, implementing a narrower
store. Capability is derived at registration (G4), never declared, so this is the one thing pipeline
resolution alone cannot catch for `weft ask`'s direct capability resolution. **What to do:** the pack
providing `"pgvector"` needs to also implement `VectorSearch`'s methods, or you need a different
store pack registered under that name.

### `EmbeddingFailedError`

**What it looks like** — the `"hash"` embedder answered `Failed` or `NothingToProduce` for the
question, or produced a node with no embedding attached:

```text
EmbeddingFailedError: could not embed the question: model unavailable
```

The built-in `HashEmbedder` never actually fails for a non-empty question — this exists for a
differently-configured `Embedder` registered under the same name `"hash"`. **What to do:** whatever
the message names as the reason is the embedder's own failure — check its own configuration or
dependency, the same way you would for any pack that failed mid-run.

---

## Project configuration — `weft_cli.registry_bootstrap`

### `ConfigFileError`

**What it looks like** — `weft.toml` exists but cannot be parsed, reproduced against a real,
deliberately broken file:

```text
$ printf '[packs\nallow = [' > weft.toml
$ weft plugins doctor
weft.toml is not valid TOML: Expected ']' at the end of a table declaration (at line 1, column 7)
$ echo $?
4
```

An absent `weft.toml` is not this — absence means open, per `docs/03-cli.md`. This is specifically a
`weft.toml` that exists but is not valid TOML, or cannot be read at all (a permissions problem).
**What to do:** fix the syntax error the message names — `tomllib`'s own error text, unmodified — or
check the file's permissions if the message says it could not be read.

---

## Contract reference generation — `weft_cli.contract_reference`

### `ContractNotDescribableError`

**What it looks like** — `scripts/generate_contract_reference.py` found a registered contract it
cannot describe: no `.version` attribute —

```text
ContractNotDescribableError: acme_pack.contract.Widget carries no `.version` attribute. Every
published contract must declare one — docs/02-extension-model.md §1, 'Versioned' — and the reference
generator refuses to invent a placeholder for one that does not.
```

— or not a `@runtime_checkable` `typing.Protocol` with at least one method:

```text
ContractNotDescribableError: acme_pack.contract.Widget exposes no `__protocol_attrs__` — it is not a
@runtime_checkable typing.Protocol declaring at least one method, so the generator has nothing to
read a method list off. Every contract this reference documents must be one.
```

This only fires while regenerating `manual/contract-reference.md` (`uv run python
scripts/generate_contract_reference.py`), never from `weft index`/`weft ask`. **What to do, as a
contract author:** every published contract needs a `version: ClassVar[str]` and must be a
`@runtime_checkable typing.Protocol` with at least one method — see
[`manual/contract-reference.md`](contract-reference.md) for a contract that already gets this right.

---

## Doctor statuses — `weft plugins doctor`

[`manual/operations-guide.md`](operations-guide.md) → *Doctor* owns the full table and what each
status means; this is the same five names, kept here so a status you are staring at has a page to
search for. Reproduced against a real checkout — one `weft.toml` and one `weft plugins doctor` run
per status below, except `active`, which is what you already saw work in
[`manual/quickstart.md`](quickstart.md).

### `active`

Imported, `register()` ran, and it is contributing. Not a failure — listed here only so the coverage
check behind this page (`docs/08-manuals.md` §3 clause (d)) has all five statuses to account for, the
same way it accounts for every `WeftError` subclass above. Nothing to do; see
[`manual/operations-guide.md`](operations-guide.md) → *The one thing to know about `active`* for the
one thing it does **not** mean (a reachable database).

### `refused`

```text
$ cat weft.toml
[packs]
allow = ["weft-extract", "weft-chunk"]
$ weft plugins doctor
weft-store: refused (0 contributed)
  never imported — 'weft-store' is not listed in [packs] allow. Add it there to permit it.
  disclosure: not disclosed
```

**What to do:** add the distribution to `[packs] allow` in `weft.toml` if you meant to permit it —
that pin is exhaustive, so anything left off is refused, and refusal happens before the pack is ever
imported.

### `failed`

```text
$ weft plugins doctor
weft-store: failed (0 contributed)
  reason: 'weft-store' settings failed validation: 1 validation error for PgVectorSettings
dsn
  Field required [type=missing, input_value={}, input_type=dict]
    For further information visit https://errors.pydantic.dev/2.13/v/missing
  disclosure: not disclosed
```

**What to do:** the `reason` line names the pack and the field — this example is
`PackSettingsError`'s validation shape, above. Fix the setting the reason names.

### `partial`

Registered, but a conditional dependency it wanted was not available, so part of what it offers did
not register. **Not reproducible against Phase 0 as shipped** — the vocabulary exists ahead of the
mechanism that produces it: no first-party pack in Phase 0 conditionally registers based on an
optional dependency yet, so this status has no live example to paste, and pretending otherwise would
be exactly the imagined-not-reproduced failure this page exists to avoid. **What to do, when it
arrives:** `doctor`'s `reason` line will name what was skipped and why — install the missing optional
dependency, or accept the reduced set.

### `allowed, not installed`

```text
$ cat weft.toml
[packs]
allow = ["weft-extract", "weft-chunk", "weft-embed", "weft-store", "acme-graph"]
$ weft plugins doctor
acme-graph: allowed, not installed (0 contributed)
  disclosure: not disclosed
```

**What to do:** `uv add` the distribution, or remove it from `allow` if it was named in error. Unlike
`packs:` settings naming an absent distribution (`UnknownPackSettingsError`, above), this is reported
and not fatal — `allow` only ever narrows what is already there.

---

## Where to go next

- **Never run `weft` before?** [`manual/quickstart.md`](quickstart.md) is the five-minute path from
  nothing to a real, retrieved answer.
- **Bringing the container up, `weft.toml`, exit codes in full** —
  [`manual/operations-guide.md`](operations-guide.md).
- **Writing a pack of your own?** [`manual/pack-author-guide.md`](pack-author-guide.md).
