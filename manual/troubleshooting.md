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
same contract, and no `[plugins]` pin resolves it — reproduced directly against a `Registry`, the same
check every pack's `register()` goes through:

```text
DuplicateRegistrationError: 'fixed' is already registered for Chunker by distribution 'weft-chunk';
distribution 'acme-chunk' cannot register it too. Weft refuses to arbitrate between them — pin the
winner in weft.toml:

[plugins]
"Chunker:fixed" = "weft-chunk"  # or "acme-chunk"

to keep the other distribution's claim instead. See the duplicate-name trap in
docs/06-phase-0-build.md and docs/02-extension-model.md §3, 'When resolution fails'.
```

You will not see this raised as a bare traceback from `weft`: it is caught inside pack activation and
folded into the *second* pack's `weft plugins doctor` report as `failed`, naming the collision in its
`reason` line — the first-registered pack stays `active`. **What to do:** paste the `[plugins]` block
the message already prints into `weft.toml`, picking whichever distribution should win, or rename the
losing plugin instead, or refuse one of the two packs via `[packs] allow`. Weft never arbitrates
silently — it either refuses, as here, or resolves against a pin an operator wrote on purpose (see
`UnresolvedPluginPinError` and `InertPluginPinError`, next).

**Once a pin is added**, this collision no longer raises at all: `weft plugins doctor` instead reports
the losing pack as `active` with a `displaced:` line naming what it lost and to whom —

```text
$ weft plugins doctor
...
weft-chunk: active (1 contributed)
  disclosure: not disclosed
  displaced: 'Chunker:fixed' lost to 'acme-chunk' — pinned by [plugins] "Chunker:fixed" = "acme-chunk" in weft.toml
```

— because the pack itself did nothing wrong; it is installed, active, and simply lost one name to the
operator's own choice (`docs/03-cli.md`).

### `UnresolvedPluginPinError`

**What it looks like** — a `[plugins]` pin exists for the colliding name, but names neither of the two
distributions actually contending for it (a typo, or a pin left over from a pack that was renamed):

```text
UnresolvedPluginPinError: [plugins] pins 'Chunker:fixed' to 'acme-old-name', but 'acme-old-name'
registered neither claim on 'fixed' for Chunker — 'weft-chunk' and 'acme-chunk' are the two
distributions actually contending for it. Point the pin at one of them, or remove it if it was meant
for a different collision.
```

Like `DuplicateRegistrationError`, this is caught inside pack activation and folded into the *second*
colliding pack's `weft plugins doctor` report as `failed` — never a bare traceback. **What to do:** the
message names the two distributions genuinely contending — fix the pin to name one of them, or delete
it if it was meant for a different `(contract, name)` pair. `docs/02-extension-model.md` §3: a pin
naming a distribution that never claimed the name is refused rather than silently ignored, because an
inert pin is a lie about what is running.

### `InertPluginPinError`

**What it looks like** — a `[plugins]` pin names a `(contract, name)` that no two distributions ever
actually collided over. **`weft index` and `weft ask` still refuse loudly**, reproduced against a
real checkout:

```text
$ cat weft.toml
[plugins]
"Chunker:no-such-collision" = "weft-chunk"
$ weft index ./docs
[plugins] pins 'Chunker:no-such-collision', but weft never saw two distributions contend for what it
names — nothing to arbitrate. Remove the pin, or check that both distributions it should choose
between are installed and actually registering that name.
$ echo $?
4
```

Unlike `DuplicateRegistrationError` and `UnresolvedPluginPinError`, this is **not** folded into any
one pack's report — it is raised once discovery finishes enumerating every pack, the same way an
unclaimed `packs:` settings key already raises (`UnknownPackSettingsError`, below).

**`weft plugins list` and `weft plugins doctor` are the one exception, and do not raise this at
all** — repaired after review: a command whose whole job is explaining what is installed must not
die before it can, so both build their registry with discovery's `strict_pins=False` and report the
pin instead, as its own block in `doctor`'s output:

```text
$ weft plugins doctor
...
[plugins] pins that never arbitrated anything:
  'Chunker:no-such-collision' — weft never saw two distributions contend for what it names.
```

**What to do:** either the name was never really going to collide — delete the pin — or one of the
two distributions that should be fighting over it is not installed or is not actually registering
that name; `weft plugins list` shows what each installed pack contributed.

### `MissingDestroysDeclarationError`

**What it looks like** — a plugin registers for a contract that publishes a property vocabulary
(`docs/02-extension-model.md` §3 → *Ordering constraints* — `Chunker` is one) without stating
`destroys` at all, reproduced directly against a `Registry`, the same check every pack's `register()`
goes through:

```text
MissingDestroysDeclarationError: 'acme-tokenizer' registers for Chunker (distribution
'acme-chunk') without declaring `destroys`. Chunker publishes a property vocabulary
(docs/02-extension-model.md §3 → Ordering constraints), so every implementation states what it
destroys — an explicit empty tuple if it destroys nothing. Add `destroys: tuple[type[Property],
...] = (...)` to the plugin class.
```

Folded into that pack's `weft plugins doctor` report as `failed`, the same way `DuplicateRegistrationError`
is — never a bare traceback from `weft` itself. **What to do, as a pack author:** add `destroys` to
the plugin class the message names — an explicit empty tuple (`destroys: tuple[type[Property], ...]
= ()`) if your stage genuinely destroys nothing, or the `weft_kernel.payload.Property` marker(s) it
actually does destroy. `intact` stays optional; only `destroys` is refused for being missing, because
forgetting it corrupts a *stranger's* stage silently, while forgetting `intact` only ever costs your
own — see `docs/02-extension-model.md` §3 for the asymmetry. **As a user:** this is a bug in the pack
named in the message, not your configuration; report it, or pin the pack out of `[packs] allow` until
it is fixed.

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

## Pipeline resolution — the shared family base, `weft_kernel.runner`

### `PipelineResolutionError`

**Never raised directly — task 1.13.** It is the family base every specific resolution failure on
this page extends (`docs/02-extension-model.md` §3 → *When resolution fails*: "each failure is its
own `WeftError` subclass under a `PipelineResolutionError` family base"), and it carries the four
fields that section requires on every member — `pipeline`, `stages`, `distributions`, `remedy` —
as real attributes rather than facts you would otherwise have to parse out of the message.
Reproduced directly against the kernel's Python API, constructing the base the way every concrete
subclass below does through it:

```text
>>> from weft_kernel.runner import UnmetRequiresError
>>> exc = UnmetRequiresError(
...     "stage 'chunk' (Chunker:fixed) requires 'Cleaned' but no earlier stage in pipeline "
...     "'base' provides it. Provided so far: (none).",
...     pipeline="base", stages=("chunk",), distributions=("acme-clean",),
...     remedy="add an earlier stage that provides 'Cleaned', or reorder 'base' so one already does.",
... )
>>> exc.pipeline, exc.stages, exc.distributions, exc.remedy
('base', ('chunk',), ('acme-clean',), "add an earlier stage that provides 'Cleaned', or reorder 'base' so one already does.")
```

Whichever concrete subclass actually raises populates all four honestly: `pipeline` is `None`
where a failure genuinely has none to name (`weft_kernel.runner.Runner.resolve` builds no *named*
pipeline at all — see `RunnablePipeline`'s own docstring), `stages` and `distributions` default to
`()` wherever there is nothing real to put there, never a placeholder that reads as data. **What to
do:** never construct or catch this base on purpose — catch the specific subclass the message
names (below), or catch `PipelineResolutionError` only when you merely need to know *that*
resolution failed, and read `.pipeline`/`.stages`/`.distributions`/`.remedy` off whatever you
actually caught instead of parsing the message string.

`UnmetRequiresError`, `StageCompositionError` and `IntactViolationError` are the three checks
`weft_kernel.runner.Runner.resolve` performs against an explicit `StageSpec` list — **the identical
classes** `weft_kernel.resolution.resolve` raises for a pipeline *document*, under *Deriving a
pipeline document* below, not three parallel names that happen to mean the same thing (`is`, not
`==` — one class per kind, `02` §3's own rule). Their reproductions live there, since a document is
the easier way to reach all three; `Runner.resolve` raises the exact same class for the exact same
reason, only with no `pipeline` name to attach. Phase 0's built-in `index` pipeline is fixed and
always resolves against a correctly installed workspace, so an ordinary `weft index`/`weft ask` run
does not hit any of the three — **`weft index` and `weft ask` already catch the whole family at
exit `4`**, the same as `UnknownPluginError`, should a custom pipeline reach either command.

### `TenantMismatchError`

**What it looks like** — a `RunnablePipeline` built for one tenant is run with a `Context` for
another:

```text
TenantMismatchError: this pipeline was resolved for tenant 'tenant-a', but run() was given a Context
for tenant 'tenant-b'. An instance cached for one tenant must never run for another.
```

Phase 0's CLI builds exactly one `Context`, with a fixed `tenant_id="default"`, per invocation — this
is unreachable through `weft index`/`weft ask` as shipped. It exists for whoever drives
`weft_kernel.runner.Runner` directly across more than one tenant. **What to do:** resolve a separate
`RunnablePipeline` per tenant — the instance cache is keyed by tenant precisely so a resolved pipeline
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

## Deriving a pipeline document — `weft_kernel.resolution`

Task 1.3: `weft_kernel.resolution.resolve` turns a `weft_kernel.pipeline.Pipeline` document —
`extends` unfollowed, `vars` unsubstituted, no plugin looked up — into a frozen `ResolvedPipeline`:
every stage's plugin, provenance and final configuration named, with no inheritance left to
interpret. Task 1.4 adds what a non-root pipeline in the `extends` chain is *for*: not another
`stages:` list, but `insert`/`replace`/`remove`/`set` operators, applied against the running result
in the order the document wrote them. Task 1.5 adds one more thing every resolved stage carries:
`config` is the plugin's own `config_model`, validated against the stage's `with:` block — never
the raw mapping the document wrote. Every failure below shares one base, `PipelineResolutionError`
(the same family `weft_kernel.runner` uses — see that class, above, for the four fields — `pipeline`,
`stages`, `distributions`, `remedy` — task 1.13 makes real attributes on every one of the twelve
classes below, not only on the three this page reproduces `.pipeline`/`.stages` for explicitly), and
every one of them happens *before* any stage runs — none of these is reachable through `weft
index`/`weft ask` yet, because nothing in Phase 0's CLI calls `resolve()` here; a future
pipeline-derivation command is what will surface these at exit `4`. Reproduced directly against the
kernel's Python API, which is also how you will meet them if you drive `resolve()` yourself —
writing a pack's own test suite, or exploring `weft pipeline derive` once it
exists.

### `UnknownParentPipelineError`

**What it looks like** — `extends` names a pipeline the `parents` mapping handed to `resolve()`
does not contain:

```text
UnknownParentPipelineError: pipeline 'specific' extends 'base', but the parent lookup this
resolve() call was given has no pipeline named that. Supply it in 'parents', or fix the name if
it was mistyped. Pipelines available in 'parents': 'base-de', 'base-en'.
```

**What to do:** the kernel opens no file — whatever calls `resolve()` is responsible for loading
every ancestor a pipeline might `extends` and passing them all in `parents`. Check that the parent's
own document was loaded and its `name:` matches the child's `extends:` exactly — the names the
message lists as available are the ones a typo is probably one character away from.

### `PipelineCycleError`

**What it looks like** — an `extends` chain loops back on a pipeline already in it, named as the
whole chain rather than only the repeated name:

```text
PipelineCycleError: pipeline 'a' has a cycle in its 'extends' chain: a -> b -> a. A pipeline cannot
extend itself, directly or through any number of intermediate parents.
```

**What to do:** the chain printed is the exact edit to undo — one of the pipelines it names has an
`extends:` line that should point somewhere else, or should not `extends` at all.

### `UnmetRequiresError`

**What it looks like** — a stage's `requires` names an `ExtModel` no earlier stage in the resolved
chain provides:

```text
UnmetRequiresError: stage 'chunk' (Chunker:fixed) requires 'Cleaned' but no earlier stage in
pipeline 'base' provides it. Provided so far: (none).
```

This is the identical class `weft_kernel.runner.Runner.resolve` raises for an explicit `StageSpec`
list (task 1.13 — see `PipelineResolutionError`, above) — run here instead against a pipeline
*document* before any plugin is instantiated. `exc.pipeline`, `exc.stages` and `exc.distributions`
carry `'base'`, `('chunk',)` and `('acme-clean',)` for the reproduction above — real attributes, not
only the message shown. **What to do:** add the missing upstream stage, or reorder so the stage
that provides it runs first — "Provided so far" names everything earlier stages already do provide,
so a stage that is merely in the wrong position (not missing) is visible from the message alone.

### `StageCompositionError`

**What it looks like** — two consecutive stages do not compose by type, checked purely against the
`contracts` mapping `resolve()` was given, before any registry lookup runs:

```text
StageCompositionError: stage 'extract' (Extractor:docling) expects <class 'str'>, but the previous
stage 'chunk' produces <class 'list'>. Consecutive stages must compose by type.
```

Task 1.13: the identical class `weft_kernel.runner.Runner.resolve` raises for this check against an
explicit `StageSpec` list — see `PipelineResolutionError`, above. `exc.pipeline == 'base'` and
`exc.stages == ('chunk', 'extract')` for the reproduction above; `Runner.resolve` populates `stages`
the same way but leaves `pipeline` `None`, since an explicit `StageSpec` list has no name to give it.
**What to do:** reorder the stages so each one's output type matches the next one's input type — the
message names both.

### `IntactViolationError`

**What it looks like** — task 1.2's ordering constraint: a stage needs a `Property` `intact` that an
earlier stage's `destroys` already named:

```text
IntactViolationError: stage 'hyphenation' (Chunker:hyphenation-fix) needs 'WordBoundaries' intact,
but stage 'chunk' earlier in pipeline 'cleaning' already destroys it. The only legal positions for
'hyphenation' are before 'chunk', never after.
```

Task 1.13: the identical class `weft_kernel.runner.Runner.resolve` raises for this check against an
explicit `StageSpec` list — see `PipelineResolutionError`, above. `exc.pipeline == 'cleaning'` and
`exc.stages == ('hyphenation', 'chunk')` for the reproduction above. **What to do:** move the stage
the message names as needing the property `intact` to before the stage it names as destroying it —
the message states both positions explicitly.

### `InvalidStageConfigError`

**What it looks like** — task 1.5: a stage's `with:` block does not validate against the
`config_model` its plugin declares:

```text
InvalidStageConfigError: stage 'keywords' (Chunker:keybert) in pipeline 'specific' has an invalid
'with:' block for KeybertConfig: field 'top_n': Input should be a valid integer, unable to parse
string as an integer. KeybertConfig accepts: top_n.
```

`02` §1: "a contract's registration API carries a typed configuration model, or the extension point
is decorative" — this is that model actually being checked, before the plugin is ever constructed,
never at the first document it happens to run against. **What to do:** the message names the field
pydantic rejected and why, and lists every field the model accepts (`KeybertConfig accepts: ...`) —
fix the `with:` value the field names, or check the field name itself for a typo against the
accepted list.

### `StageNotConfigurableError`

**What it looks like** — a stage writes a non-empty `with:` block for a plugin that declares no
`config_model` at all:

```text
StageNotConfigurableError: stage 'keywords' (Chunker:keybert) in pipeline 'specific' sets a
'with:' block ({'top_n': 8}), but Chunker:keybert publishes no configuration model — it cannot be
parameterised at all. Drop 'with:', or have the plugin declare `config_model`.
```

`02` §3's own extended note names the reference defect this refuses rather than repeats: a `with:`-
shaped block with nowhere typed to land was silently dropped in one reference subsystem and simply
unavailable in another, and no metric or enhancer in it could ever be parameterised as a result. An
absent `config_model` is never read as "accept anything and ignore it" here. **What to do:** either
drop the `with:` block this pipeline wrote for the stage the message names, or — if you own the
plugin — give it a `config_model` so the block has somewhere checked to land.

### `UndefinedVarError`

**What it looks like** — a stage's `with:` block references `${var:NAME}` and no pipeline in the
`extends` chain defines a var by that name:

```text
UndefinedVarError: '${var:target_language}' references var 'target_language' in stage 'extract',
but pipeline 'base' defines no such var — not directly, and none of its ancestors do either. Add it
to a 'vars:' block somewhere in the chain, or fix the reference. Vars defined in this chain:
'target_lang'.
```

A reference must be the **entire** string — `${var:target_lang}`, not `"target is ${var:target_lang}
today"` — the same restriction `${env:VAR}` interpolation already applies to `weft.toml`, per
`docs/02-extension-model.md` §3: partial substitution inside a longer string is a template engine
this project does not have and does not need. **What to do:** add `vars: {target_lang: ...}` to the
pipeline that should own the decision, or fix the var name if it was mistyped — "Vars defined in
this chain" names the whole chain's merged answer, so a one-character typo like `target_language`
for `target_lang` above is readable as a typo directly from the message; the stage the message names
is where that typo lives when a pipeline has more than one `with:` block referencing vars.

### `StaleOperatorTargetError`

Task 1.4: one of the four derivation operators (`insert`, `replace`, `remove`, `set`) names a stage
id that does not exist at the point in the `extends` chain it applies against — including a `remove`
matching nothing, which gets no exemption from this check:

```text
StaleOperatorTargetError: pipeline 'specific' extends 'base' and its 'insert' operator targets stage
id 'clean', but no stage with that id exists in the parent it resolved against at this point in the
chain. The ids that do exist: 'extract', 'chunk'.
```

**What to do:** the message names the ids that actually exist — check the target for a typo, or
whether an ancestor's own `remove`/`replace` already changed what this pipeline is operating against.
Operators apply in **written order** (`02` §3, settled by task 1.4): if this operator's target was
supposed to exist because an earlier operator in the *same* document creates or renames it, check
that the block creating it is written *above* the block that targets it — a document writing `insert`
above `remove` sees the old stage still present (and may instead hit `OperatorIdCollisionError`
below); writing `remove` above `insert` is what expresses a move.

Task 1.11 widens `remove`'s own half two ways, without a new class: `remove: <slot-id>` reaches
this same check if the slot named does not exist either (the message then names both the stage ids
and the slot ids that do exist), and a slot's own `after:`/`before:` position going missing —
because a descendant's `remove` took the stage it was pointed at — raises this too, naming the slot
rather than an operator:

```text
StaleOperatorTargetError: pipeline 'specific' declares slot 'enrich' positioned against stage id
'chunk', but no stage with that id exists in the fully resolved chain — an ancestor's own operator
likely removed or renamed it. The ids that do exist: 'extract'.
```

**What to do, for the slot case:** an ancestor's own `remove` of the stage the slot is positioned
against is almost always the cause — either restore that stage, or move the slot's `after:`/`before:`
to a stage id that survives the whole chain.

### `OperatorIdCollisionError`

Task 1.4: an `insert` operator's new stage id already exists in the parent it resolved against —
inserting it would silently shadow the existing stage rather than adding a new one:

```text
OperatorIdCollisionError: pipeline 'specific' extends 'base' and its 'insert' operator adds stage id
'chunk', but a stage with that id already exists in the parent it resolved against — inserting it
would silently shadow the existing stage. Pick a different id, or use 'replace'/'set' if the intent
is to change the existing stage.
```

**What to do:** pick a stage id that is not already taken, or — if the goal was to change what runs
at that id — use `replace` (swap the plugin) or `set` (override configuration) instead of `insert`.
To reuse an id genuinely intentionally (a move), write `remove` for that id **above** `insert` in the
same document — application order is written order, so the id is free again by the time `insert` runs.

### `SlotOrderConflictError`

Task 1.11, `docs/02-extension-model.md` §3 → *Slots*: two (or more) packs' contributions to one slot
each need a property `intact` that another one destroys, so no order satisfies every declared
constraint — the slot's own version of a cycle, not a single stage checked against an order that
already exists. Reproduced directly against `weft_kernel.resolution.resolve`, which is also how you
will meet it today, since nothing in Phase 0's CLI fills a slot yet:

```text
SlotOrderConflictError: contributions to slot 'enrich' cannot be ordered: 'acme-a:a', 'acme-b:b' each
need a property intact that another destroys, with no legal order between them. Fix the ordering
declarations on the plugins involved.
```

**What to do:** this is a bug in one (or both) of the packs the message names, not something a
pipeline document can work around — their `intact`/`destroys` declarations contradict each other.
File it against the packs, or pin one of them out of `[packs] allow` until the conflict is fixed.

### `DuplicateContributionError`

Task 1.11, repaired after a review of that task's own commit found the gap: two contributions —
whether to the same slot or two different ones — offer the same local stage id from the same
distribution, so both would try to wear the identical qualified id (`distribution:id`) once placed
into the resolved stage list. Reproduced directly against `weft_kernel.resolution.resolve`, the same
way `SlotOrderConflictError` above is:

```text
DuplicateContributionError: pipeline 'base': distribution 'aaa-pack' offers stage id 'e' more than
once — once for slot 'enrich' and again for slot 'enrich' — and both would resolve to the identical
qualified id 'aaa-pack:e'. Give each contribution its own local stage id.
```

Before this check existed, the second contribution built silently replaced the first in
`_order_contributions`'s own bookkeeping — not placed, not refused, and never counted among
`ResolvedPipeline.unplaced_contributions` either, since it never survived long enough to be checked
against a declared slot. **What to do:** this is a bug in the pack the message names, not something a
pipeline document can work around — give the two contributions distinct local stage ids in the
pack's own `register()`. File it against the pack, or pin it out of `[packs] allow` until it is fixed.

---

## Opening a pipeline document — `weft_cli.pipeline_catalogue`

Task 1.9: `weft-cli` is the one distribution allowed to open a pipeline document — G1 keeps
`weft-kernel` at `pydantic` and `opentelemetry-api` only, so the YAML parser lives here, on the
identical footing `weft_cli.registry_bootstrap` already established for `weft.toml`'s TOML. None of
these three is reachable through `weft index`/`weft ask` yet — nothing in Phase 0's CLI opens a
pipeline document; a future `weft pipeline` command (`docs/build-ledger.md` 3.7) is what will surface
these at exit `4`, the same exit `03` reserves for "fix the pipeline". Reproduced directly against
`weft_cli.pipeline_catalogue`'s own Python API, which is also how you will meet them today, writing or
testing a pipeline catalogue of your own.

### `PipelineDocumentError`

**What it looks like** — a file exists but is not valid YAML at all, reproduced against a real,
deliberately broken file (an unterminated flow mapping):

```text
$ printf 'name: base\nstages: [{id: chunk, use: fixed-size\n' > broken.yaml
$ python -c "
from pathlib import Path
from weft_cli.pipeline_catalogue import load_pipeline_document
load_pipeline_document(Path('broken.yaml'))
"
PipelineDocumentError: broken.yaml is not valid YAML: while parsing a flow mapping
  in "<unicode string>", line 2, column 10:
    stages: [{id: chunk, use: fixed-size
             ^
expected ',' or '}', but got '<stream end>'
```

An absent file is not this — `load_pipeline_catalogue` simply finds nothing to glob, and there is no
document to fail parsing. This is specifically a file that exists but is unreadable (a permissions
problem) or not well-formed YAML at all — the same split `ConfigFileError` already draws for
`weft.toml`, one section below. **What to do:** fix the YAML syntax the message names, or check the
file's permissions if the message says it could not be read.

### `MalformedPipelineError`

**What it looks like** — the file parses as YAML, but the mapping it produced fails
`weft_kernel.pipeline.Pipeline`'s own validation — here, a document naming both `extends` and its own
`stages:`, which `02` §3 rules out (a child changes its parent by operator, never by a second stage
list):

```text
$ printf 'name: confused\nextends: base\nstages: [{id: chunk, use: fixed-size}]\n' > confused.yaml
$ python -c "
from pathlib import Path
from weft_cli.pipeline_catalogue import load_pipeline_document
load_pipeline_document(Path('confused.yaml'))
"
MalformedPipelineError: confused.yaml is not a valid pipeline document: 1 validation error for
Pipeline
  Value error, pipeline 'confused' sets 'extends: base' and also lists its own 'stages:'. A pipeline
that extends a parent expresses what changes with an operator (insert, replace, remove, set), never
with its own 'stages:' list — drop 'stages:', or drop 'extends' and author this as a standalone
pipeline. [type=value_error, ...]
```

This is the exact `pydantic.ValidationError` `Pipeline.model_validate` raises, wrapped rather than
improved on — `weft_kernel.pipeline`'s own module docstring is explicit that this error set is
deliberately *not* one of `weft_kernel.resolution`'s `PipelineResolutionError` subclasses, because a
document that will not validate has no resolved parent and no distributions to name. **What to do:**
the wrapped message names the exact rule the document broke — an unknown key, a duplicate stage id, or
(as above) `extends` alongside `stages:` — fix the document accordingly.

### `DuplicatePipelineNameError`

**What it looks like** — two files in one catalogue directory both declare the same `name:`:

```text
$ printf 'name: base\nstages: [{id: chunk, use: fixed-size}]\n' > a.yaml
$ printf 'name: base\nstages: [{id: chunk, use: fixed-size}]\n' > b.yaml
$ python -c "
from pathlib import Path
from weft_cli.pipeline_catalogue import load_pipeline_catalogue
load_pipeline_catalogue(Path('.'))
"
DuplicatePipelineNameError: both a.yaml and b.yaml declare name 'base' — a catalogue key must be
unique. Rename one pipeline, or one of the two files.
```

**What to do:** rename one pipeline's `name:` field, or delete one of the two files — a catalogue is
keyed by the name a document declares, never by the filename it happens to be saved under, so two
files claiming the same name is a genuine ambiguity, not a coincidence for the loader to arbitrate.

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
