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

**Under `--json` (task 5.2d), the identical string travels as data instead of as the whole line.**
`weft_cli.render.render_refusal` puts a structured envelope on stdout in place of that one line: the
class name below as `error`, the reproduction's own text as `rendered`, unchanged and unabridged, the
process's exit code as `exit_code`, and — for every entry marked with a `valid_options` field further
down — the alternatives as a JSON array a script reads directly, never a sentence it has to parse.
See [`docs/03-cli.md`](../docs/03-cli.md) → *Output* for the envelope's full shape and its own
version field.

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

### `CommandArgumentsError`

**What it looks like** — an argument parsed, but breaks a bound or a check its command declares: a
count below its minimum, an empty name, a pack name that is not a distribution name. One line per
broken argument, spelled as the command line spells it, exit `2` like any other usage error.
Reproduced from the built wheel:

```text
$ weft index ./corpus --batch-size 0
argument --batch-size: Input should be greater than 0
$ echo $?
2
$ weft pack new "Bad Name"
argument name: 'Bad Name' is not a distribution name. Use lowercase letters, digits and single
hyphens, starting with a letter — 'acme-shouty'. …
$ echo $?
2
```

Under `--json` the same refusal is the error envelope, `"error":"CommandArgumentsError"`,
`"exit_code":2`. Before carried repair `R22.8` this reached you as pydantic's `ValidationError`
under *An error weft did not translate*, exit `1`.
**What to do:** change the named argument; `weft <command> --help` lists every argument the command
takes.

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
weft-chunk 1.0.0: active (1 contributed)
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

### `MissingRequiredDeclarationError`

**What it looks like** — task **3.1**'s generalisation of the check above: a plugin registers
for a contract that names a required class-level declaration (`Command.required_declarations`,
say — `docs/03-cli.md` → *Permissions*) without stating it at all, reproduced directly against a
`Registry`, the same check every pack's `register()` goes through:

```text
MissingRequiredDeclarationError: 'graph-build' registers for Command (distribution
'weft-kg') without declaring `permission_class`. Command.required_declarations names it as
mandatory, with no default silently assumed — see the contract's own docstring for what it
means and what value to give it. Add `permission_class = ...` to the plugin class.
```

The identical mechanism as `MissingDestroysDeclarationError` above — one check,
`weft_kernel.registry._require_declarations_present`, walking whatever names a contract lists
in `required_declarations` (or, for `destroys`, the legacy `publishes_property_vocabulary`
flag) — so this entry and that one share everything except which name was missing and which
contract asked for it. `MissingDestroysDeclarationError` is this class's own subclass, raised
specifically for `destroys`; every other required declaration raises this base class directly.

**What to do, as a pack author:** add the named attribute to the plugin class the message names,
with the value the contract's own documentation asks for — `weft_command.contract.Command`
documents `permission_class` as one of `weft_command.permission.PermissionClass`'s five members,
with no default that is safe to assume (`docs/03-cli.md` → *Permissions*: "No default is safe:
`read` silently under-protects, and `destroy` trains people to pass `--yes` reflexively"). **As a
user:** this is a bug in the pack named in the message, not your configuration; report it, or pin
the pack out of `[packs] allow` until it is fixed.

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
store (weft-store) 2.0.0: failed (0 contributed)
  reason: 'store' settings failed validation: 1 validation error for PgVectorSettings
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
`WEFT_DATABASE_URL` or add `[packs.store] dsn = "..."` to `weft.toml`; see
[`manual/operations-guide.md`](operations-guide.md) → *Wiring `weft.toml`*. **As a pack author:** fix
`register()`'s own signature — it must match `register(registrar: PackRegistrar, settings:
YourSettingsModel) -> None` exactly.

### `UnknownPackSettingsError`

**What it looks like** — a `weft.toml` names a `[packs.<pack>]` settings block for a pack nothing
installed declares, reproduced against a real checkout:

```text
$ cat weft.toml
[packs.acme-graph]
endpoint = "http://localhost:1234"
$ weft plugins doctor
[packs] settings name 'acme-graph', which is not installed. Install the distribution that ships it,
or remove its settings block. Packs that declare a 'weft.packs' entry point: 'canary', 'chunk',
'embed', 'extract', 'store'.
$ echo $?
4
```

(`canary` in that list is this repository's own test-only pack — a real install of
`weft-cli` will not show it; the pack list is otherwise exactly what got reproduced.) The key is the
**pack** name, the first column `weft plugins list` prints, not the distribution: one distribution
can ship several packs and each configures itself. Unlike
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

### `OwnDistributionError`

**What it looks like** — `weft --version` cannot work out which installed distribution put the
`weft` command on your PATH, because either nothing claims it or two things do:

```text
$ weft --version
weft cannot report its version: no installed distribution declares a console script pointing at
'weft_cli.cli'. Install weft-rag (or weft-cli) rather than putting its source directory on
PYTHONPATH.
$ echo $?
1
```

The two-claimant form names both:

```text
weft cannot report its version: 2 installed distributions each provide a console script pointing at
'weft_cli.cli' ('weft-cli', 'weft-rag'). Uninstall all but one.
```

`weft --version` deliberately touches no registry (fitness function 8(b)), so it cannot ask
discovery where it came from — it reads the `console_scripts` entry point pointing at
`weft_cli.cli`, which is exactly the thing that installed the command you typed. Neither state is
guessed past: reporting *a* version when two distributions disagree would be picking one at random.

**What to do:** for the first form, install the distribution rather than running from a source
checkout on `PYTHONPATH` — `uv pip install weft-rag`, or `uv sync` in this repository. For the
second, `uv pip uninstall` whichever of the two you did not mean to have; `weft-rag` bundles
`weft-cli`, so having both installed at once is the usual cause and only one is needed.

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
through `weft index` today.** `FlushError` is a `WeftError`; `weft_cli.commands.IndexCommand.run`
never catches it, so it propagates out to `weft_cli.cli.run_command`'s own `except WeftError`,
which renders `str(exc)` only, the same one line above, `WEFT_TRACEBACK` or not — `_report_unexpected`,
the one place that reads `WEFT_TRACEBACK`, only ever runs for [an exception no handler translated](#an-error-weft-did-not-translate),
and `FlushError` is always translated (`weft_cli.exit_codes.exit_code_for` maps it, like every
`WeftError` outside the resolution family, to `1`). This surfaces through `weft index` at exit `1`
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

### `UnknownFallbackError`

**What it looks like** — task 2.28: a stage's `fallback:` list names a plugin no installed
distribution registered, so the pipeline can be authored but not run:

```text
UnknownFallbackError: stage 'extract' names 'ocr' as fallback 2 of 2, but no distribution
registered that name for Extractor, so this pipeline cannot be run. Names registered for
Extractor: 'pdf-layout', 'pdf-text', 'text'.
```

**A `fallback:` name that is not installed yet is legal in a document and refused only when you
try to run it**, and the split is deliberate. `weft_kernel.resolution.resolve()` carries the name
through unchecked — a pipeline may name `ocr` as its fallback before any pack ships one, and the
document should not have to be re-edited the day one arrives. `Runner.resolve` is a later step,
and it refuses, because *running* a chain whose second candidate does not exist means either
crashing on the first scanned page or skipping it silently. The second is worse: it degrades
quality precisely on the inputs the fallback existed for, and nothing reports it.

`exc.stages` carries `('extract',)`; `exc.remedy` names both ways out. **What to do:** install a
distribution that registers the name — `weft plugins list` shows what each installed pack provides
— or remove it from that stage's `fallback:` list. The message lists every name that *is*
registered for the contract, so a typo (`pdf-lyaout`) reads as a typo.

### `FallbackNotSubstitutableError`

**What it looks like** — a `fallback:` entry declares something the plugin it stands in for does
not, so the pipeline resolves into a chain whose second candidate would break a check the first
one passed:

```text
FallbackNotSubstitutableError: stage 'chunk' names 'sentence' as fallback 1 of 1, but it cannot
stand in for 'fixed-size' at that position: it destroys 'WordBoundaries', which the primary does
not. Every requires, intact and ordering check this pipeline passed was answered by
'fixed-size's declarations, and a chain reaching 'sentence' would run against checks nobody made.
```

**A fallback may demand no more and promise no less than the primary.** Four declarations are
compared, read off the plugin classes with nothing constructed: a fallback may not `require` or
need `intact` what the primary does not (nothing guarantees an earlier stage supplies it), may not
`destroy` what the primary does not (a later stage cleared to run after the primary would silently
receive corrupted input), and may not drop a `provides` the primary makes (a later stage's
`requires` was satisfied by that promise). The reverse directions — providing more, destroying
less — invalidate no check and are not refused.

Why it is refused at resolution rather than left to run: a chain reaches its fallback only on the
documents the primary could **not** read, so the corruption appears in production on the inputs
nobody tested, and appears nowhere else.

`exc.stages` carries the stage id and `exc.distributions` both packs. **What to do:** either
declare on the fallback what the primary declares — if the two really are interchangeable
backends of one contract, they should agree about what they consume, promise and destroy — or
give it a stage of its own, where the ordinary `requires`/`intact` checks apply to it directly.

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

### `PipelineMissingRenderStageError`

**What it looks like** — task 8.9: `weft render` was given a pipeline whose **last** stage is not
registered under the `Renderer` contract, so it produces nodes rather than a document to read.
Reproduced against a real install:

```text
$ weft render ./corpus index-text
pipeline 'index-text' does not end in a stage registered under the Renderer contract, so it
produces nodes rather than a document to read. Its stages: extract, normalize, whitespace,
chunk, embed, store.
$ echo $?
4
```

**Why the *last* stage and not merely "a Renderer somewhere".** A `Renderer` returns a `Rendition`,
which no stage takes as input, so a document with one in the middle cannot compose at all and
`weft_kernel.resolution.resolve` has already refused it long before this check runs. What is left
for this error to catch is the document that composes perfectly and simply ends somewhere else — an
ingest pipeline, as above — whose terminus is a list of nodes this command has no use for.

**What to do:** name a pipeline that renders. `preview-plain` and `preview-markdown` ship, and
`weft pipeline list` shows every document this project knows. If you meant to *index* rather than
read, the command is `weft index`. The message lists the stages the document does have, so an
operator who named the wrong document can see which one they got.

### `SubPluginConfigError`

**What it looks like** — task 8.11: a plugin that resolves a *sibling* by name was given a config
block for it that the sibling's own `config_model` rejects. `iterative-retrieval`'s `leaf_config`,
below; `corrective`'s `primary_config`/`grader_config`/`knowledge_action_config` and
`refine-on-uncertainty`'s `retriever_config`/`signal_config` behave identically. Reproduced against
a real install, from a project-local `pipelines/bad-sub.yaml` that types `top_kk` for `top_k`:

```text
$ weft ask "what is fusion" --pipeline bad-sub
the config block passed for 'vector-top-k' is invalid for VectorTopKConfig: field 'top_kk': Extra
inputs are not permitted. VectorTopKConfig accepts: arm, channels, filter, per_query_top_k, top_k.
$ echo $?
1
```

**Why it is separate from `InvalidStageConfigError` above**, which reports the same *kind* of fact
about a stage's own `with:` block. That one can name a stage id and a pipeline, because a stage has
a position in a document. A sibling resolved through `weft_retrieve.contract.StageLookup` has
neither: it is named by a *field* of the plugin that reaches it, so the message names the plugin
and the model instead. The two are deliberately not merged; a shared message would have to drop
whichever half the other could not supply.

**What to do:** the message names the field that was rejected, why, and every field the model
accepts — fix the value, or check the field name against the accepted list. If you meant to
configure the *outer* plugin rather than its sibling, the block belongs in `with:` directly rather
than inside a `*_config` field.

> *(This error class exists because those seven `*_config` fields had **never worked**. `build`
> handed the raw mapping to the sibling's factory, which received a `dict` where its config object
> belonged and failed later inside its own `run` with `'dict' object has no attribute 'channels'` —
> a message naming neither the field nor the document that set it. Found by running
> `weft ask --pipeline corrective-retrieve`; `docs/internal/lessons.md` L8.5.)*

### `StageNotConfigurableError`

**What it looks like** — a stage writes a non-empty `with:` block for a plugin that declares no
`config_model` at all:

```text
StageNotConfigurableError: stage 'keywords' (Chunker:keybert) in pipeline 'specific' sets a
'with:' block ({'top_n': 8}), but Chunker:keybert publishes no configuration model — it cannot be
parameterised at all. Drop 'with:', or have the plugin declare `config_model`.
```

`02` §3's own extended note names the defect this refuses rather than repeats: a `with:`-
shaped block with nowhere typed to land could be silently dropped in one place and simply
unavailable in another, so a metric or enhancer could never be parameterised as a result. An
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
identical footing `weft_engine.registry_bootstrap` already established for `weft.toml`'s TOML. The first
three fire from `weft_cli.pipeline_catalogue`'s own Python API, and **since ledger task 3.7 the
`weft pipeline` commands open a project-local catalogue directory too**, surfacing them at exit `4`, the same exit `03` reserves for "fix the pipeline". The fourth,
`ContributedPipelineNameCollisionError`, is reachable today, through `weft ask`'s own routed default
(task 2.8, folded into `weft ask` at task 3.11): it is what fires when two installed packs each ship
a pipeline claiming the same `name:`.

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

### `ContributedPipelineNameCollisionError`

**What it looks like** — two installed packs' own `PipelineResource`s (task 2.8:
`PackRegistrar.add_pipeline_resource`, called from each pack's own `register()`) declare the same
`name:`. Unlike `DuplicatePipelineNameError` above, there is no single directory to point at — each
side is `distribution:package/resource`, because the two files live inside two separate installed
packages:

```text
ContributedPipelineNameCollisionError: both pipeline resource 'pipelines/base.yaml' from package
'acme_pack_a' (distribution 'acme-pack-a') and pipeline resource 'pipelines/base.yaml' from package
'acme_pack_b' (distribution 'acme-pack-b') declare name 'base' — a catalogue key must be unique.
Rename one of the two pipeline documents, or uninstall the distribution shipping the one you do not
want routable.
```

**What to do:** rename one pack's pipeline, or uninstall the one you did not mean to have routable —
`weft plugins doctor` names every active distribution, which is where to look for the second pack
this message names.

### `ProjectPipelineNameCollisionError`

**What it looks like** — task 3.7: a project-local document under `pipelines/` and an installed
pack's own contribution declare the same `name:`. Unlike `DuplicatePipelineNameError` and
`ContributedPipelineNameCollisionError` above, the two colliding sources are of different *kinds* —
a file on disk versus a pack's own resource:

```text
$ printf 'name: base\nstages: []\n' > pipelines/base.yaml
$ weft pipeline list
ProjectPipelineNameCollisionError: pipeline 'base' is declared both by a project-local document
under 'pipelines' and by an installed pack's own contribution. Rename one of the two — `weft
plugins doctor` names which pack contributed the other.
```

**What to do:** rename the project-local file's own `name:` field, or find the pack shipping the
same name (`weft plugins doctor`) and either rename its own document upstream or uninstall it.
Neither source wins automatically — a pack installing itself must never silently shadow a
project's own pipeline, or the reverse.

### `UnknownPipelineNameError`

**What it looks like** — task 3.7: `weft pipeline show|derive|validate|diff` names a pipeline
`weft_cli.pipeline_catalogue.full_catalogue` does not hold — neither a project-local document
under `pipelines/` nor any installed pack's own contribution:

```text
$ weft pipeline show ghost
UnknownPipelineNameError: 'ghost' is not a pipeline this project knows — checked the project's own
'pipelines' directory and every installed pack's own contribution. Known pipelines: base, route.
```

**What to do:** the message already names every pipeline that does resolve — pick one of those, or
fix a typo. If the pipeline you expected is missing from the list entirely, `weft pipeline list`
and `weft plugins doctor` both help narrow down whether it was never written, or belongs to a pack
that is not active.

### `UnknownConfigKeyError`

**What it looks like** — task 3.7: `weft config get|set` names a key nothing in this module reads.
`docs/03-cli.md` -> *Project context*: "a key the CLI does not yet read is refused, naming the keys
it does":

```text
$ weft config get --key services.bogus
UnknownConfigKeyError: 'services.bogus' is not a key weft config reads or writes. Known keys:
permissions.destroy, permissions.overwrite, services.embed, services.store.
```

**What to do:** use one of the keys the message names — `weft config get` with no `--key` prints
every one of them and its current value.

### `UnknownPermissionKeyError`

**What it looks like** — repair, 2026-08-20 (finding 1, `docs/internal/build-ledger.md` 3.3's dated
paragraph): `[permissions]` names a key `weft_engine.permission_policy.PermissionPolicy` does not
have — `overwrite`/`destroy` are the only two — reproduced against a real checkout:

```text
$ printf '[permissions]\ndelete = "allow"\n' > weft.toml
$ weft plugins list
unknown [permissions] key(s) in weft.toml: 'delete'. [permissions] accepts destroy, overwrite. A
key nothing reads is refused rather than ignored — a permission you did not actually change is one
you would have to notice by the tool behaving differently than the file says.
$ echo $?
4
```

Before this repair the class was a bare `WeftError` — the message already named the keys, but only
inside the string, invisible to fitness function 12's family walk, which looks for a typed
`valid_options` field. `UnknownConfigKeyError` above is the same-phase precedent this now matches;
`(exc.valid_options == ("destroy", "overwrite"))` for any raise site. **What to do:** use `overwrite`
or `destroy`, the only two keys `[permissions]` reads — `docs/03-cli.md` → *Permissions*.

The sibling "must be 'ask' or 'allow'" refusal, one function below this one and in `weft_cli.
config_surface.validate_set_value`'s `permissions` branch, stays a plain `WeftError` and is **not**
in FF12's family — deliberately: `PermissionAction` is a closed, two-member `StrEnum` fixed by the
type itself, not a name resolved against a set whose membership could ever differ, so there is no
"valid options" to enumerate beyond the type's own two literals already stated in the message.

### `UnknownReconcileKeyError`

**What it looks like** — task 5.1c: `[reconcile]` names a key `weft_engine.reconcile_policy.
ReconcilePolicy` does not have — `mode` is the only one — reproduced against a real checkout:

```text
$ printf '[reconcile]\ndelete = "allow"\n' > weft.toml
$ weft plugins list
unknown [reconcile] key(s) in weft.toml: 'delete'. [reconcile] accepts mode. A key nothing reads
is refused rather than ignored — a default you did not actually change is one you would have to
notice by the tool behaving differently than the file says.
$ echo $?
4
```

The identical shape `UnknownPermissionKeyError` above already gives `[permissions]`'s sibling
refusal, typed from the start rather than repeating that repair a third time: `(exc.valid_options
== ("mode",))` for any raise site. **What to do:** the only key `[reconcile]` reads is `mode`, and
its only legal values are `repair`/`full` — `docs/03-cli.md` → *Project context*, and `weft_cli.
reconcile_policy`'s own module docstring for what this block governs (`weft reconcile`'s own bare
`--mode` default, never `weft index`'s automatic post-index pass, which is hardcoded and reads
nothing here).

The sibling "must be one of ['full', 'repair']" refusal, in `weft_engine.config_surface.
validate_set_value`'s own `reconcile` branch and in `reconcile_policy_from_config` itself, stays a
plain `WeftError` and is **not** in FF12's family — the identical reasoning `UnknownPermissionKeyError`
above states for `PermissionAction`: `ReconcileMode` is a closed, two-member `StrEnum` fixed by the
type itself, so there is no "valid options" to enumerate beyond the type's own two literals already
stated in the message:

```text
$ weft config set reconcile.mode wobble
'reconcile.mode' must be one of ['full', 'repair'], not 'wobble' — weft_store.ReconcileMode's own
vocabulary.
$ echo $?
1
```

### `UnknownIndexKeyError`

**What it looks like** — `[index]` in `weft.toml` names a key it does not read; `layers` is the
only one:

```text
unknown [index] key(s) in weft.toml: 'layer'. [index] accepts layers.
```

`exc.valid_options == ("layers",)`. **What to do:** spell it `layers`, a list of layer documents
that `weft index` runs after the base, such as `layers = ["enrich-with-questions"]`.
### `UnknownServiceKeyError`

**What it looks like** — repair, 2026-08-20 (`docs/01-high-level-plan.md` item 12's own dated
paragraph): `[services]` names a key nothing declares — `embed`, `route`, `store`, `blob` and `describe`
are what a default install accepts — reproduced against a real checkout:

```text
$ printf '[services]\nembedd = "openai"\n' > weft.toml
$ weft plugins list
unknown [services]
key(s) in weft.toml: 'embedd'. [services]
accepts blob, describe, embed, graph, route, store. A key nothing reads is refused rather than
ignored — a service Weft did not select is one you would have to notice by the answers being wrong.
$ echo $?
4
```

Before this repair the class was a bare `WeftError` — the message already named the keys, but only
inside the string, invisible to fitness function 12's family walk, which looks for a typed
`valid_options` field. `UnknownConfigKeyError` above is the same-phase precedent this now matches;
`(exc.valid_options == ("blob", "describe", "embed", "graph", "route", "store"))` for any raise site. `weft plugins list`'s exit `4`
comes from `weft_cli.cli.main`'s own fixed code for any `WeftError` raised while `build_
dependencies` is still assembling the registry — see that function's own comment — not from
`weft_cli.exit_codes.exit_code_for`'s per-exception mapping. **What to do:** use one of the keys
`[services]` actually reads — `docs/03-cli.md` → *Project context*. **The set is no longer fixed**:
task 9.0 made `[services]` keys *declared* by the packs that publish the contracts they select, so
`blob` joined it when `weft_blob` shipped at task 9.4 and a pack you install can add another. That
is why the tuple above is checked against the live one by
`tests/docs/test_manual_valid_options.py` rather than trusted — which is what caught this page the
day `blob` was added.

The malformed-value check just below this one in `weft_engine.services.service_selection_from_
config` (a `[services]` value that is not a non-empty string) stays a plain `WeftError` and is
**not** in FF12's family — it reports a type mismatch, not a name failing to resolve against an
enumerable set; whether the name itself resolves is left to the registry lookup a command
performs later, which is where `weft_kernel.registry.UnknownPluginError` already carries its own
`valid_options`.

### `AmbiguousCapabilityError`

**What it looks like** — ledger task **9.0**: a stage in the pipeline you are running needs a
capability from a run-wide service, and more than one of the roles you selected in `[services]`
provides it, so there is no single instance to hand the stage:

```text
AmbiguousCapabilityError: a stage needs VectorSearch from a run-wide service, and more than
one selected role provides it: [services] embed, [services] store. Resolving it would hand
that stage one of the two arbitrarily and report nothing, so it is refused here. Select a
plugin for exactly one of those roles that provides VectorSearch.
```

Refused at assembly, before any stage runs. Deliberately **not** in fitness function 12's
`UnresolvedNameError` family, on `DuplicateServiceRoleError`'s footing: nothing failed to resolve
against an enumerable set — two things resolved and disagree, which is a collision rather than a
lookup miss, so there is no `valid_options` to offer. **What to do:** the message names both role
keys. Change one of them in `weft.toml` to a plugin that does *not* provide the named capability,
or drop that role if this project does not need it. `weft plugins doctor` lists what every
installed pack registered.

### `SelectedCapabilityMissingError`

**What it looks like** — ledger task **9.0**: a stage needs a capability from a run-wide service,
and nothing you selected in `[services]` provides it. Two shapes, and the difference matters:

```text
SelectedCapabilityMissingError: stage 'retrieve' needs TextSearch from a run-wide service, and
what is selected does not provide it: [services] store = 'qdrant'. Nothing here adapts or
degrades — a run that asked for a capability does not quietly proceed without it.
```

The second shape arises for a role with no built-in default — one a pack you installed declares
and your `weft.toml` never names. It reads *"nothing is selected for"* and then that role's key,
rather than naming a plugin.

The first says the role *is* selected and the plugin you named lacks the capability; the second
says the role is not selected at all. Collapsing them would tell you to swap a plugin you never
chose. This is `StoreCapabilityMissingError`'s refusal asked of the whole selected set rather than
of the one configured store, which is why the remedy names **the role key that could provide it**
rather than a fixed `[services] store`. It exits **4** — this configuration cannot run this
pipeline, decided before anything ran.

**What to do:** the remedy names the `[services]` key to set, and the message names the plugin you
currently have there *by the name you wrote in `weft.toml`*, never by its Python class. `weft
plugins doctor` lists what every installed pack registered, and `weft plugins list` shows which
of them provide the capability you need.

### `MalformedServiceRolesError`

**What it looks like** — ledger task **9.0**: an installed pack defines a module-level
`SERVICE_ROLES` attribute, but it is not a tuple of `weft_kernel.context.ServiceRole`, so
discovery cannot tell which `[services]` keys the pack meant to declare:

```text
MalformedServiceRolesError: 'blob' defines SERVICE_ROLES but it is not a tuple of
weft_kernel.context.ServiceRole (found list). Declare it as `SERVICE_ROLES = (MY_ROLE,)`,
beside the contract the role selects for.
```

The pack is reported `FAILED` rather than treated as declaring nothing, on
`MalformedDisclosureError`'s own footing: a pack that *tried* to declare a role and got the
shape wrong is a different fact from a pack that declares none, and collapsing the two would
leave an operator with a `[services]` key that silently does not exist. **What to do:** this is
a defect in the pack, not in your configuration — `weft plugins doctor` names the distribution,
and its author needs to declare `SERVICE_ROLES` as a tuple beside the contract the role selects
for. Until then the pack contributes nothing.

### `DuplicateServiceRoleError`

**What it looks like** — ledger task **9.0**: two installed, trusted packs each declared a
`ServiceRole` under the same `[services]` key, so `weft_engine.service_roles.
role_table_from_reports` has two claimants for one name and no way to prefer either:

```text
DuplicateServiceRoleError: role 'blobs' was declared by more than one pack for [services]:
'weft-blob' and 'weft-other'. A role key names exactly one contract, so an operator's
[services].blobs must have exactly one pack it could mean.
```

Deliberately **not** in fitness function 12's `UnresolvedNameError` family, unlike
`UnknownServiceKeyError` just above it: nothing here failed to *resolve* against an enumerable
set — two names resolved to the same key and disagree about what it means, which is a
collision, not a lookup miss, so there is no `valid_options` to offer. **What to do:** one of
the two packs named in the message is not the one you meant to install, or the two packs
themselves need to stop naming the same role — `weft plugins doctor` shows what each
installed distribution actually registers.

### `UnknownLLMKeyError`

**What it looks like** — repair, 2026-08-20 (`docs/01-high-level-plan.md` item 12's own dated
paragraph): `[llm]` names a key `weft_engine.llm_roles.llm_section_from_config` does not read —
`loop_guard`/`retry`/`roles` are the only three — reproduced against a real checkout:

```text
$ printf '[llm]\nrules = { attempts = 3 }\n' > weft.toml
$ weft plugins list
unknown [llm] key(s) in weft.toml: 'rules'. [llm] accepts 'loop_guard', 'retry', 'roles'. A key
nothing reads is refused rather than ignored.
$ echo $?
4
```

Before this repair the class was a bare `WeftError` — the message already named the keys, but only
inside the string, invisible to fitness function 12's family walk, which looks for a typed
`valid_options` field. `UnknownConfigKeyError` above is the same-phase precedent this now matches;
`(exc.valid_options == ("loop_guard", "retry", "roles"))` for any raise site. `weft plugins list`'s
exit `4` comes from the identical fixed code `UnknownServiceKeyError` above documents — a `WeftError`
raised while `build_dependencies` is still assembling the registry, not `exit_code_for`'s
per-exception mapping. **What to do:** use one of `loop_guard`, `retry`, `roles` —
`docs/03-cli.md` → *Project context* and this module's own docstring for `[llm]`'s shape.

The three malformed-shape checks below this one (`[llm.roles]`/`[llm.retry]`/`[llm.loop_guard]`
each not being a table) stay plain `WeftError` and are **not** in FF12's family — each reports a
type mismatch, not a name failing to resolve against a set of alternatives.

### `TargetAlreadyExistsError`

**What it looks like** — repair, 2026-08-20 (`docs/internal/build-ledger.md`'s dated paragraph for tasks
3.3/3.6/3.7): `weft init` scaffolds `weft.toml`; it does not replace one. Running it a second time
in a project that already has one refuses outright, naming the path, rather than asking:

```text
$ weft init
$ weft init
weft_cli.commands.TargetAlreadyExistsError: 'weft.toml' already exists. 'weft init' creates a new
project's configuration; it does not replace one. Edit the existing file directly, or remove it
first if you mean to start over.
$ echo $?
1
```

Exit `1`, not `3`: this is not a permission refusal — `weft init` is `write`-class now (see
`CommandRefusalError`'s own entry below for why no command reaches that machinery at all today),
so `weft_cli.confirm.gate` never runs for it. The answer is simply certain: the target this command
would create is already there. **What to do:** edit the existing `weft.toml` directly (`weft config
get|set`, or a text editor), or delete it first if you actually mean to start over.

### `PipelineAlreadyExistsError`

**What it looks like** — the identical shape, for `weft pipeline derive`, task 3.7, repaired the
same day: `pipelines/<name>.yaml` already exists for the name given.

```text
$ weft pipeline derive base specific
$ weft pipeline derive base specific
weft_cli.pipeline_commands.PipelineAlreadyExistsError: 'pipelines/specific.yaml' already exists.
'weft pipeline derive' creates a new pipeline document; it does not replace one. Choose a different
name, or remove the existing file first if you mean to start over.
$ echo $?
1
```

**What to do:** pick a name nothing under `pipelines/` uses yet (`weft pipeline list` shows what
does), or remove the existing file first.

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

### `SchemaVersionRefusedError`

**What it looks like** — a stored `ext` namespace's schema version disagrees with the class reading
it, and that class declares no migration for the difference:

```text
SchemaVersionRefusedError: 'weft-kernel' data was written at no version at all (written before
schema versioning existed), but the installed class is at '1.0.0' and declares no upgrade path from
it. Override weft-kernel's ExtModel.upgrade(data, from_version) to migrate this shape, or reindex
the corpus so this namespace is rewritten at the current version.
```

Every `ExtModel` declares `__schema_version__`, and the version travels inside the dumped
namespace's own bytes — never as a `ClassVar` a serialiser would drop. A reader compares the stored
version against the class's current one; a match rehydrates exactly as before, and anything else —
including a namespace with **no** stored version at all, which is every row written before this
mechanism existed — is handed to `upgrade`, whose default refuses rather than guessing. **What to
do:** two options, and no third. If the pack that owns this namespace can actually reconcile the
older shape, its author overrides `ExtModel.upgrade(data, from_version)` to return the migrated
fields. If it cannot (the common case for data older than the pack itself), re-run `weft index` over
the affected sources — a node's identity is content-addressed, so re-indexing unchanged content
overwrites the same row with a current, versioned dump rather than creating a duplicate. There is no
supported way to make this refusal silent; that would be exactly the indistinguishable success and
failure paths this mechanism exists to avoid.

### `UnaddressableFieldError`

**What it looks like** — a filter names a field that reaches nothing on a `Node`:

```text
UnaddressableFieldError: filter field 'metadata.author' reaches nothing on a Node. The core fields
are: content, id, lineage.parents, lineage.sources, media_type. Anything a pack attached is under
'ext.<namespace>.<field>', where <namespace> is the distribution that owns it — 'ext.weft-pdf.backend',
say.
```

Raised by whichever store was asked, before it queries anything, and identically by both — the parse
lives in `weft-store` and every backend translates from it. **What to do:** the addressable
vocabulary is `Node`'s own shape, so the path is what you would write to reach the value: `id`,
`content`, `media_type`, `lineage.parents`, `lineage.sources`, and `ext.<namespace>.<field>` for
whatever a pack attached. There is no list of blessed field names to consult, and none to add to.

### `FilterOpMismatchError`

**What it looks like** — an operator applied to a field that cannot carry it:

```text
FilterOpMismatchError: filter operator 'eq' cannot apply to field 'lineage.sources', which holds a
set of strings. use 'contains', which asks whether the value is one of the set's members.
```

Three refusals share this class, and each one exists because two backends had to agree rather than
because anybody preferred it that way. **`eq`/`ne` on a set** — a document store matches a payload
array element-wise, so `eq` would mean membership there and whole-list equality in SQL: use
`contains`, or `not` wrapping `contains`. **`contains` on a string** — that reads as substring
matching, which is what `TextSearch` ranks and no filter can. **An ordered comparison on a core
field** — `lt`/`lte`/`gt`/`gte` against text would mean whatever the database's collation means,
which is a fact about a deployment and not about the filter; they apply to numbers under a pack's
namespace. **What to do:** change the operator, or the field it is applied to. A filter that
validates is a filter every backend answers the same way, which is the point of the narrowing.

### `SupersedeNarrowsSourcesError`

**What it looks like** — a replacement node that would drop a source the node it replaces carries:

```text
SupersedeNarrowsSourcesError: cannot supersede node 3f9a2c… with a replacement that drops
source(s) 'source-b'. A superseding node must carry at least the sources of the node it
replaces, or the last node carrying a source disappears while that source's documents remain.
```

You will meet this from a stage that revises a stored tree — an incremental summariser replacing a
summary with a newer one built over more members. `NodeStore.supersede` writes the replacement
first and deletes the superseded node second, so an interrupted call leaves a **duplicate**, which
`weft reindex --repair` finds, rather than a **hole**, which nothing finds. That ordering protects
against a crash; it cannot protect against a caller handing over a replacement that covers less
than the original, which is why this refusal exists as well.

**What to do:** build the replacement so its `Lineage.sources` is the union of every member it was
derived from — `Node.combine` does this for you and is the supported way to build a summary. If you
constructed the node another way, the sources named in the message are the ones missing. A node
that genuinely should no longer carry a source is not a supersede: delete the source with
`weft delete`, which cascades to everything derived from it.

### `UnhandledFilterOpError`

**What it looks like** — an operator a filter translator has not been taught:

```text
UnhandledFilterOpError: weft-qdrant's range translator has no case for 'between'. It knows: gt,
gte, lt, lte.
```

You will only meet this after upgrading `weft-store` (or another pack publishing `FilterOp`) to a
version that added an operator without also upgrading the store pack that translates filters —
`weft-qdrant` or `weft-store`'s own pgvector translator — to a version that knows it. Every
`FilterOp` dispatch in this tree refuses an operator it predates rather than guessing at it, which
is what keeps a new operator from being silently answered as `eq`, `gte` or `not` instead of the
question it was actually asking. **What to do:** update the store pack that raised this to a
version published alongside (or after) the `weft-store` version that added the operator — the
`valid_options` on this error name exactly the operators that translator currently knows, which is
what a version mismatch looks like from the inside. If both are already current, this is a defect
in that translator and is worth reporting rather than working around: the operator is valid and
admitted, and nothing should be able to reach this refusal on a matched pair of versions.

### `VectorWidthMismatchError`

**What it looks like** — a node's embedding is not the width the Qdrant collection was created with:

```text
VectorWidthMismatchError: node 4f1c… carries a 1536-component embedding and collection 'weft_nodes'
was created for 64. A Qdrant collection's width is fixed at creation and cannot be altered, so
either [packs.qdrant] vector_size names the wrong width for the configured embedder, or this
collection was written by a different one — re-index into a new 'collection'.
```

Specific to `weft-qdrant`; the pgvector store has no equivalent, because its vector column is
declared without a dimension. **What to do:** decide which of the two is wrong. If the configured
embedder changed — `hash` is 64 by default and `openai-embeddings`'s `text-embedding-3-small`
is 1536 — set
`[packs.qdrant] vector_size` to match it *and* re-index into a fresh `collection`, because the
existing one holds vectors of the old width and cannot be widened. If the embedder did not change,
the collection belongs to a different corpus and the `collection` name is what to change.

You will only meet this if `[services] store` names `qdrant`; the settings under
`[packs.qdrant]` configure the pack, and that key is what selects it.

### `CollectionSchemaMismatchError`

**What it looks like** — the collection `[packs.qdrant] collection` names already exists, but
lacks a vector this store writes. The usual cause is a collection an earlier release wrote: the
sparse `lexical` vector that serves Qdrant's text search arrived in `2.6.0`, so a collection
indexed by `2.4.0` has only the dense `content` vector:

```text
collection 'weft_nodes' has no vector named 'lexical'. It was written by an earlier release of
this store, or by something else, before this store wrote that vector. Point [packs.qdrant]
collection at a new name, or delete the collection and re-index.
```

Raised on the store's first use, before anything is written or searched. Before carried repair
`R22.7`, the same collection failed mid-index with Qdrant's own `400 (Bad Request) … Not existing
vector name error: lexical`.

**What to do:** Qdrant cannot add a vector to an existing collection, so the choice is yours:
set `[packs.qdrant] collection` to a new name and run `weft index` again, or delete the old
collection (and its `__sources` sibling) and re-index into the same name.

### `QuantizationMismatchError`

**What it looks like** — the collection already carries a quantization configuration, and
`[packs.qdrant] precision` asks for a different one:

```text
QuantizationMismatchError: collection 'weft_nodes' is quantised as 'int8', and [packs.qdrant]
precision asks for 'binary'. Re-quantising in place would silently change what every stored vector
compares as, so this store refuses rather than reconfiguring a collection somebody else's settings
built. Point [packs.qdrant] collection at a new name and re-index, or set precision back to
'int8'.
```

**Why this refuses where a missing configuration does not.** The two cases are deliberately not
treated alike, on the same reasoning grilling session G22 settled for vector width. A collection
with *no* quantization has never had that question answered, so the configured precision is applied
in place — both are online operations in Qdrant and nothing an operator chose is being overwritten.
A collection already quantised *differently* is the other case: somebody's settings decided that,
the stored vectors were encoded under it, and quietly re-encoding them would change what every
comparison means with no error to notice it by. G22 refuses a table holding two widths rather than
migrating it, and this is the same refusal one axis over.

**What to do.** Either point `[packs.qdrant] collection` at a new name and re-index under the
precision you want, or set `precision` back to what the collection already holds — the message
names both. If you are unsure which a collection carries, `GET /collections/<name>` on the Qdrant
server reports its `quantization_config` directly.

### `Bm25NotAvailableError`

**What it looks like** — `[packs.store] text_mode` asks for `bm25` on a database that has no
`pg_textsearch`:

```text
Bm25NotAvailableError: [packs.store] text_mode asks for 'bm25', but this database has no
'pg_textsearch' extension available to install — real BM25 needs timescale/pg_textsearch, which
needs PostgreSQL 17 or 18. Three ways out: run `docker compose --profile bm25 up -d` for a
supported self-hosted PostgreSQL 17/18 carrying timescale/pg_textsearch (port 5434); or set
text_mode back to 'fts' for Postgres's own ts_rank_cd ranking on this database as it is. The
qdrant store is the third route and serves its lexical arm from its own index rather than from a
Postgres extension — check `weft plugins doctor` for whether the installed one advertises
TextSearch before moving a corpus to it.
```

Raised on the store's first use, before any schema is touched. **Why it refuses rather than falling
back:** `fts` and `bm25` are different rankings, not two spellings of one. Postgres's `ts_rank_cd`
has no IDF over your collection and no term saturation, so serving it under a `bm25` label would
give you numbers that are not BM25 and no way to tell — the failure this project refuses on
principle, because it does not crash, it answers plausibly.

**What to do:** the floor container (`pgvector/pgvector:pg16`) cannot serve BM25 and is not meant
to. `docker compose --profile bm25 up -d` starts a second Postgres on **port 5434** carrying both
pgvector and `timescale/pg_textsearch`; point `dsn` at it. It is a separate service rather than an
upgrade to the floor because its image is 3.86 GB against the floor's 640 MB — `compose.yaml`
carries the whole argument. If you do not want that, `text_mode = "fts"` is the honest default and
is what every Weft corpus ran on before this setting existed.

### `DiskannNotAvailableError`

**What it looks like** — `[packs.store] index` asks for `diskann` on a database whose Postgres has
no `vectorscale`:

```text
DiskannNotAvailableError: [packs.store] index asks for 'diskann', but this database has no
'vectorscale' extension available to install — StreamingDiskANN ships in
timescale/timescaledb-ha, not in the pgvector floor image. Two ways out: run `docker compose
--profile bm25 up -d` for a PostgreSQL 17 carrying vectorscale (port 5434) and point dsn at it;
or set index back to 'hnsw', which this database can serve and which Weft measured at recall@10
0.994 against the exact scan.
```

Raised on the store's first embedded write, before any index is built and before the batch is
inserted — an extension that is not *available* cannot be created no matter what runs next, so the
catalogue is asked first.

**Why this is not refused when you write it into `weft.toml`.** `diskann` is a **valid**
`VectorIndexKind` — what varies is whether *this deployment* can serve it. A setting that is correct against one
database and wrong against another cannot honestly be judged by reading a configuration file, so
the answer comes from the database. `Bm25NotAvailableError` above draws the identical line for
`text_mode`, and for the identical reason.

It is therefore a plain error carrying no *valid options*: naming `hnsw` as an alternative you
could have typed would say your setting was wrong, when your deployment was.

**What to do.** Either move to an image that carries the extension — `docker compose --profile
bm25 up -d` starts a PostgreSQL 17 on **port 5434** with both pgvector and vectorscale, and it is
behind a profile because that image is 3.86 GB against the floor's 640 MB — or stay on `hnsw`.

**Before you reach for the bigger image, know what it buys.** Weft measured both on 100,142 real
chunks: diskann reaches recall@10 **0.99** unfiltered at 2.8 ms p95, in a 68 MB index built in
83.6 s. But under a filter it degrades sharply — **0.6885 at 0.1% selectivity** — while HNSW with
`iterative_scan = "relaxed_order"` holds **0.89** there. If your searches carry filters, the floor
image's `hnsw` is the better answer as well as the cheaper one.

### `UnknownTextSearchConfigError`

**What it looks like** — `[packs.store] text_search_config` names something this database has
no text search configuration for:

```text
UnknownTextSearchConfigError: [packs.store] text_search_config names 'klingon', which this
database has no text search configuration for. Installed here: arabic, armenian, basque, catalan,
danish, dutch, english, finnish, french, german, greek, hindi, hungarian, indonesian, irish,
italian, lithuanian, nepali, norwegian, portuguese, romanian, russian, serbian, simple, spanish,
swedish, tamil, turkish, yiddish.
```

Raised on the store's first use, before any schema is touched, and the list is read out of your
database rather than out of Weft — a configuration you installed yourself appears in it. **What to
do:** correct the name in `weft.toml`. The pack default is `simple`, which folds case and splits on
word boundaries and stems nothing; that is deliberate for a mixed-language corpus and wrong for an
English-only one, where `english` is what makes a question about "retrieval" reach a passage that
says "retrieved".

### `TextSearchConfigMismatchError`

**What it looks like** — the database's text index was generated under one configuration and
`weft.toml` now asks for another:

```text
TextSearchConfigMismatchError: weft_nodes.content_tsv in this database is generated by 'simple', and
[packs.store] text_search_config asks for 'english'. A generated column cannot be altered in
place, so the stored lexemes would stay 'simple's while every query asked 'english's — near-zero
matches, and no error to notice it by. Either set text_search_config back to 'simple', or drop the
column (ALTER TABLE weft_nodes DROP COLUMN content_tsv) and let this store recreate it: it is
generated from content, so nothing needs re-indexing.
```

`content_tsv` is a **generated** column: Postgres recomputes it from `content` on every write, which
is what makes the text index impossible to leave stale — and also what makes its configuration part
of the schema rather than of a query. `ADD COLUMN IF NOT EXISTS` cannot change an existing column's
generation expression, so without this check the setting would appear to apply and would not.
**What to do:** either of the two fixes in the message. Dropping the column is safe and cheap in the
sense that matters — nothing needs re-indexing, because the column is derived from `content`, which
is already stored — but the rebuild is a full table rewrite, so on a large corpus do it when you can
afford one.

### `VectorWidthMismatchError`

**What it looks like** — a node's embedding is a different width from the one this table already
committed to:

```text
VectorWidthMismatchError: node 3a3a9776…72a56c carries a 3-component embedding, and
weft_nodes.embedding committed to 1536 components at its first write. A pgvector column's width is
fixed once it is typed and cannot be widened in place, so either this node was embedded by a
different embedder than the rest of this corpus, or [services] embed now names a different one —
re-index this corpus under a single embedder.
```

**Why the store refuses rather than letting Postgres do it.** This store learns its column's width
from the first embedded node it is ever handed, types the column to `vector(n)`, and refuses any
other width from then on. Postgres would refuse the write too, but with a message naming neither the
node nor the remedy — and the remedy is a decision, not a retry.

**What to do:** decide which embedder this corpus is, and re-index under it. *Changing the embedder
means reindexing* is the standing rule, and this is the failure that enforces it. There is no
setting to relax: the width is learned from your own data, never configured, so nothing here can be
"set to the right number" instead.

---

### `MixedVectorWidthError`

**What it looks like** — the table already holds more than one width, so there is no single width to
commit to:

```text
MixedVectorWidthError: weft_nodes.embedding already holds nodes of 64, 1536 components each, and its
column is still untyped. Typing it to any one of these widths would silently strand every row
carrying the others, so this store refuses to guess — decide which width this corpus actually is and
re-index the rest under it.
```

**How a table gets into this state.** Not through this store: `add()` refuses a mismatching node
before it is written, so one width can never accumulate a second that way. It means the table was
written by an older release, which declared the column with no dimension at all, under two different
embedders.

**What to do:** decide which width this corpus is. Then either re-index the whole corpus under that
embedder into a fresh database, or delete the rows carrying the other width and let this store type
the column on the next write. Typing the column yourself is the one thing to avoid — every row of
the other width stays in the table, unsearchable and unreported.

---

---

## Blob storage — `weft_blob`

Where a figure's pixels live. `[packs.blob] root` names a directory; a `BlobRef` in a node's `ext`
points into it, and `weft delete` reaps a source's blobs through the same fan-out that reaches the
node store. The bytes never enter the payload — `docs/02-extension-model.md` §1 → *The payload
model* is why, and it is what keeps a JSONB column from growing a megabyte per figure.

### `BlobKeyRefusedError`

**What it looks like** — a key or a blob uri that would resolve outside the configured root:

```text
'../escaped.png' is refused: a blob key or prefix must be a relative path with no '..' segment,
so it cannot resolve outside the configured root
```

or, on the reading side:

```text
'file:///etc/passwd' resolves outside /srv/weft/blobs, the root [packs.blob] root names. A blob
uri is read back from a stored record, so this store resolves only inside its own root and
refuses anything else rather than reading it.
```

Two boundaries, one rule. First-party keys are derived by `weft_blob.keys.blob_key`, which cannot
produce a traversal — but `put`, `delete_prefix` and `open` all take a bare string, and a key
composed by a third-party extractor or a uri read back from a stored `BlobRef` are both inputs this
pack did not write. A stored record is **data**, not an instruction, which is the identical
argument `weft_kernel.payload.applicability._FactRef` makes one layer up about resolving a
persisted class reference by importing it.

An empty key or prefix is refused for its own reason: it names the root itself, so
`delete_prefix("")` would reap every tenant in it, and an empty string arriving at a
`destroy`-class operation is far more likely to be a variable nobody set than a caller who means
*everything*.

**What to do:** compose keys through `weft_blob.keys.blob_key` rather than by hand. If the refusal
names a uri rather than a key, the `BlobRef` in that node was written against a different root —
check `[packs.blob] root` against the one the corpus was indexed with.

### `BlobNotFoundError`

**What it looks like** — `open` was asked for a uri nothing ever wrote, or whose file has since
been removed from outside Weft:

```text
no blob was ever written at 'file:///srv/weft/blobs/tenant-a/9f2c.../0.png'
```

Never an empty `bytes`. An empty answer here would be indistinguishable from a real empty blob, so
a describer or an embedder handed it would produce a plausible result against nothing at all —
the exact silent-fallback shape `CLAUDE.md` refuses.

**What to do:** the common cause is a root that was emptied, moved, or is a different directory
from the one that was indexed. `weft reconcile` does **not** reach blobs today, so a corpus whose
blob root was lost needs re-indexing rather than repair.

### `BlobLayoutVersionError`

**What it looks like** — the root was written by a different on-disk layout than this version of
the pack reads:

```text
/srv/weft/blobs was written by blob layout version '2'; this store is layout version '1' and
refuses to read or write a root a different layout produced. Point [packs.blob] root at a root
this version wrote, or migrate this root's contents to the current layout before reusing it.
```

**This is the seventh persistence surface, and the rule behind it is `S11`** (`docs/internal/README.md`'s
decision log). `ExtModel.__schema_version__` versions the `BlobRef` a node carries and says nothing
about the layout that reference resolves *through*; every persistence root a pack owns outside the
node store carries its own version, in the root, checked at open and refused on mismatch. Guessing
here means reading somebody's bytes from a layout that did not write them.

A root with no marker and no blobs is a *fresh* root and is adopted rather than refused — otherwise
first use would be impossible.

**What to do:** what the message says. There is no automatic migration, deliberately: a migration
nobody wrote is a migration nobody tested, and the alternative to refusing is silently
misinterpreting a corpus.

---

## `weft index` — `weft_cli.ingest`

Which formats `weft index` accepts is **derived from the extractors actually installed**, never from
a fixed list: `weft_extract.accept.claimed_extensions` reads the `extensions` every registered
`Extractor` declares, and their union is the accept set. Installing an extractor pack therefore makes
its formats reachable with no edit to anything. Three of the errors below are what that derivation
says when it cannot finish — each is a `PipelineResolutionError`, so `weft index` exits `4`.

**`--pipeline`, ledger task 4.0**: `weft index <path> --pipeline <name>` resolves a whole pipeline
document instead of the built-in four stages, reaching a plugin's own `with:` configuration —
`OpenAIEmbedderConfig.model`, say — that `[services] embed`/`[services] store` can never carry,
since those two name a plugin and nothing else. See `manual/operations-guide.md` → *Choosing an
embedder* for the worked example, and `weft_cli.ingest`'s own module docstring for why `[services]`
and a document's `with:` stay two surfaces rather than merging into one grammar.

### `ConflictingIndexModeError`

**What it looks like** — task 4.0: `weft index` was given both `--extract` and `--pipeline` in the
same invocation, two mutually exclusive claims about what should run — raised by
`weft_cli.commands.IndexCommand.run`, before either flag resolves a single plugin:

```text
$ weft index corpus --extract pdf-text --pipeline kg
weft_cli.commands.ConflictingIndexModeError: --extract and --pipeline cannot both be given:
--extract narrows the default four-stage path's own auto-discovery to one named extractor;
--pipeline names a whole document whose own 'extract' stage already names its plugin. Choose one.
$ echo $?
1
```

Exit `1`, not `4`: neither flag is invalid on its own, and there is no alternative *name* to offer
(this is not a `NAME_RESOLUTION_FAMILY` member, the identical reasoning `ConflictingAskModeError`
below states for its own pair), so `weft_cli.exit_codes.exit_code_for`'s default is the right
answer. **What to do:** drop one of the two flags — `--extract <name>` to narrow the default
path's own discovery, or `--pipeline <name>` to run a specific document. With neither, `weft index`
auto-discovers as before.

### `SourceChangedDuringIndexError`

**What it looks like** — ledger task 43.1: a file was edited, replaced or deleted while
`weft index` was running. The run takes each file's hash at the start and loads that file's bytes
when its batch begins, so a file that moves in between no longer matches what the run recorded:

```text
$ weft index corpus
batch 1/4 · 25/100 documents queryable · 13.1 s since start
'file:///corpus/report.pdf' changed since this run's inventory: its bytes no longer match the hash
taken at the start of this run. Indexing was refused rather than recording it under a stale
identity — the next run over this directory will see it as changed.
$ echo $?
1
```

**Why this is refused rather than indexed.** The hash is the document's identity: the next run
compares it to decide what is unchanged. Indexing the new bytes under the old hash would leave a
record claiming a document Weft never read, and every later run would report it unchanged. The
batches that finished before the refusal keep their documents, which are already `ACTIVE`.

**What to do:** run `weft index` again once the directory is settled. The changed file is seen as
changed and indexed; everything else is unchanged and costs nothing. If a directory is written to
continuously, index a snapshot of it rather than the live directory.

### `BatchScopedStageError`

**What it looks like** — ledger task 17.3: `weft index --batch-size` was given a pipeline holding a
stage whose output depends on **which other nodes shared its batch**. Raised by
`weft_cli.ingest.run_index` before anything is written or deleted, reproduced against the shipped
wheel:

```text
$ weft index corpus --pipeline index-with-raptor --batch-size 50
--batch-size cannot be used with this pipeline: raptor computes its output over whichever nodes
share its batch, so splitting the corpus would silently build a different tree per batch instead
of one tree per run. Drop --batch-size, or use the 'index-with-adrap' rung instead, which joins a
later batch into a tree an earlier run already built.
$ echo $?
1
```

**Why this is refused rather than allowed.** `raptor` reads no store — grilling session **G15**
settled that reading one is a different contract, `Revisable`, whose registration is `adrap` — so
it clusters over the payload it was handed and nothing else. `docs/01-high-level-plan.md` records
the measurement: it clusters **batch-wide, not corpus-wide**. Without `--batch-size` that is one
batch per `weft index`, so a run builds one tree. With it, the corpus arrives in pieces and each
piece founds a **separate tree** — and nothing would tell you: the command exits `0`, retrieval
still returns passages, and the corpus is quietly worse. That is the failure mode this project
refuses above a crash.

Exit `1`, not `4`: `--batch-size` is valid, the pipeline is valid, and there is no alternative
*name* to offer — only a combination that does not compose. So it is not a `NAME_RESOLUTION_FAMILY`
member, on `ConflictingIndexModeError`'s own footing above.

**What to do**, in order of what you probably want:

- **Drop `--batch-size`.** One `weft index` over the whole corpus builds one tree, which is what
  `index-with-raptor` is for, and Chucri §6.5 measures a full rebuild as the *better* answer.
- **Use `index-with-adrap`** if the corpus is too large to index in one run, or if documents keep
  arriving. That rung joins a later batch into a tree an earlier run already built, rather than
  founding a second one beside it. Its value is operational, never qualitative — the paper's own
  §6.5 puts it below a full rebuild on two of three datasets.
- **Keep `--batch-size` and change the pipeline** if what you need is bounded memory and you were
  not relying on the clustering — `index-text` and every rung without an `Expander` chunk freely.

**If this fired on a pipeline you wrote**, the stage that caused it declared
`depends_on_batch_membership = True`. That is a plugin author's statement that their output is a
function of what shared the call; the refusal names every such plugin in the pipeline, so the one
to look at is in the message.

### `PackTargetExistsError`

**What it looks like** — ledger task 26.7: `weft pack new` was pointed at a directory that already
exists. Raised before any file is written, reproduced against the shipped command:

```text
$ weft pack new acme-shouty
'/home/you/src/acme-shouty' already exists, and scaffolding into it would leave a half-written
pack over whatever is there with nothing saying which files moved. Choose another name, or
another --into directory, or remove that path yourself.
$ echo $?
1
```

**Why it refuses rather than merging.** `weft pack new` is a `write`-class command: it *creates*.
`weft init`'s own repair from `overwrite` to `write` is the precedent, and the reasoning is the
same — a template written over a directory somebody already has leaves a half-pack that is neither
theirs nor the template's, the result says nothing about which files were replaced, and there is no
undo. Nothing is written at all when this fires, so the directory is exactly as you left it.

**What to do:** pick another name, pass `--into` a different directory, or remove the path
yourself. The command will not do it for you, deliberately: a scaffolder that deletes is a
scaffolder somebody eventually runs in the wrong place.

### `NotAStoreError`

**What it looks like** — ledger task 26.5: the published store conformance kit was handed an object
that does not satisfy `NodeStore`. Raised by `weft_store.conformance.checks_for` and
`unsupported_checks` before any check runs, reproduced against the shipped module:

```text
>>> from weft_store.conformance import checks_for
>>> checks_for(object())
NotAStoreError: object does not satisfy NodeStore — it is missing add, count, delete_source,
flush, get, get_source, list_sources, put_source, run, scan. Every check in this kit needs the
base contract, so this is not a store with fewer capabilities; it is not a store.
`weft_store.contract.NodeStore` names the members it must have.
```

**Why this is a refusal and not an empty result**, which is the distinction the whole selector
rests on. A store without `NodeSupersedable` is a **smaller** store: `checks_for` offers it fewer
checks and `unsupported_checks` names the ones it left out with the capability each needs, so a
pack author always knows which half of the contract a green run proved. A store without `NodeStore`
is not smaller — it is not a store, and answering it with an empty list would be
`docs/01-high-level-plan.md`'s *an empty answer is not a fact about the world*: it would read as
*you passed everything I have* rather than *you handed me the wrong object*.

**What to do:** the message lists exactly the members that are missing. `NodeStore` is a Protocol,
so there is nothing to inherit and nothing to register — implement those methods with the
signatures `weft_store.contract.NodeStore` declares, and the object satisfies it. Capability is
derived from the methods present, never declared, so no flag is needed for the optional ones
either: add `supersede` and the supersede checks are offered on the next call.

### `AmbiguousExtractorError`

**What it looks like** — two extractors claim a format found in the directory, which is the normal
state, not a mistake: `weft-pdf` registers `pdf-text` (`pypdf`) and `pdf-layout` (`pdfplumber`)
separately *because they read differently*.

```text
$ weft index corpus/mrmr
2 extractors could read this directory (pdf-layout, pdf-text, claiming .pdf), and this command will
not choose between them — they are registered separately because they read differently.
```

`exc.stages == ('extract',)`, `exc.distributions` names every distribution providing a candidate, and
`exc.remedy` repeats the fix. **What to do:** name one — `weft index corpus/mrmr --extract pdf-text`.
Composing several backends into a chain that tries each in turn is built in the kernel (ledger task
**2.28**), and a pipeline document's `fallback:` list *does* reach `weft index`'s stages — name the
document with `--pipeline` and `weft pipeline show` prints the chain on the stage that carries it.
What it will not do is rescue *this* failure: the directory-readability check above reads the
formats the **primary** plugin claims, so a chain whose fallback claims the format never gets far
enough to be tried (`docs/internal/lessons.md` `L8.19`; no task owns that repair). For this command, without
a document, choosing is the operator's, and it will not do it silently.

### `UnclaimedFormatError`

**What it looks like** — the directory holds files, and no installed extractor claims any of their
formats:

```text
$ weft index ./slides
nothing under './slides' can be read: found .key, .pptx, and the installed extractors claim .md,
.pdf, .txt.
```

An empty directory is *not* this error — it reports "nothing to produce" and exits `0`, because
nothing to index is a fact. This fires only when there was something to index and nothing installed
could read it, which is the difference between "nothing here" and "nothing here I can read". **What
to do:** install a pack claiming one of the formats the message names, then re-run; `weft plugins
doctor` will show whether a pack you expected registered at all.

### `CorpusPathNotFoundError`

**What it looks like** — the path you named is not on disk:

```text
$ weft index ./corpuss
there is no './corpuss' to index. Nothing was read and nothing was stored — check the path, then
run 'weft index <directory>' again.
```

**Until 2026-09-12 this was silent**, and that is why the entry is worth reading rather than
skipping: a mistyped corpus path produced `produced 0, nothing to produce 1, failed 0` at exit `0`
— byte-identical to an empty directory's answer — so a typo read as a successful run that happened
to find nothing, and a script checking the exit code saw a clean build. Carried repair `R27.1`.

**What to do:** check the spelling and the working directory. `weft index` takes a path relative to
where you ran it, so `weft index corpus` from the wrong directory is this error and not a
configuration problem. Nothing was written, so nothing needs undoing.

### `CorpusPathNotADirectoryError`

**What it looks like** — the path is there, and it is a file:

```text
$ weft index ./corpus/paper.pdf
'./corpus/paper.pdf' is a file, and 'weft index' reads a directory. Index the directory holding it
— 'weft index corpus' — and every file under it whose format an installed extractor claims is read.
```

**What to do:** name the directory, as the message says. Indexing one file at a time is not
supported — `weft index` derives which formats to read from what is present under a directory, so
there is nowhere for a single file to enter. If you want to index one paper and not its neighbours,
put it in a directory of its own.

### `PipelineMissingExtractStageError`

**What it looks like** — task 4.0: `--pipeline` named a document with no stage registered under
the `Extractor` contract, so there is nothing for `weft index` to derive "which files to read" from
— the same fact `AmbiguousExtractorError`/`UnclaimedFormatError` derive from `--extract` or from
every claim the registry holds, for a document that made no claim at all:

```text
$ weft index corpus --pipeline no-extract
weft_cli.ingest.PipelineMissingExtractStageError: pipeline 'no-extract' has no stage registered
under the Extractor contract, so 'weft index' has nothing to derive which files to read from.
Stages: chunk, embed, store.
```

`exc.valid_options` is every stage id the document does resolve, `exc.pipeline` names the document.
**What to do:** add a stage to the document whose `use:` names a registered `Extractor` plugin —
`weft pipeline show <name>` prints what the document currently resolves to.

### `NotALayerError`

**What it looks like** — a document offered as a layer reads files instead of the nodes already
stored:

```text
'index-with-questions' reads files — its stage 'extract' is an Extractor — so it cannot run as a
layer over the nodes 'index-text' stored. Installed layers: enrich-with-questions.
```

**Why** — a layer enriches what a base document already indexed, such as adding generated
questions to stored chunks. A document that starts by reading files is a base document, and
running it as a layer would re-parse the whole corpus.

A document whose stage is some other contract is refused the same way, naming the contract: only
a contract whose publisher declares `layer_stage` promises to hand back every node it was given.

```text
'my-reshaper' cannot run as a layer: its stage 'reshape' is a Chunker, which does not declare
layer_stage — a layer's stages take stored nodes and return every one of them. Installed layers:
enrich-with-questions.
```

**What to do:** name one of the installed layers the message lists, or run the document as the
base with `weft index --pipeline <name>`. If you publish the contract yourself and its stages do
return every node they are handed, declare it: `MyContract.layer_stage = True`.

### `LayerDuplicatesBaseStageError`

**What it looks like** — a layer document names its own embedder or store:

```text
'questions-and-embed' names 'embed' (Embedder:hash), which a layer takes from its base:
'index-text' embeds with 'embed' and stores with 'store'. Remove it from the layer.
```

**Why** — a layer's new nodes are embedded and stored by the base document's own stages, so they
are searchable in the same index the base built. A layer carrying its own embedder would embed
them differently, and asking would refuse the mismatch.

**What to do:** delete the embedder and store stages from the layer document.

### `UnknownLayerError`

**What it looks like** — `--layers` or `[index] layers` names a document nothing provides:

```text
'enrich-with-nothing' is not an installed layer. Installed layers: enrich-with-questions.
```

`weft ask` gives the same refusal when a rung's `route.requires` names a layer nothing installs,
before it would answer or report the rung as pending:

```text
'needs-questions' names 'enrich-with-questons' in route.requires, which is not an installed
layer. Installed layers: enrich-with-questions.
```

**What to do:** name one of the listed layers — in `route.requires` when `weft ask` refused. A
layer is a pipeline document from an installed pack or from your project's `pipelines/`
directory; `weft pipeline list` shows them all.

### `LayerNeedsMetadataFilterError`

**What it looks like** — layers were asked for against a store that cannot select stored nodes by
their metadata:

```text
layers need a store that can select stored nodes by metadata (MetadataFilter), and the 'my-store'
store cannot, so 'enrich-with-questions' has no way to read the leaves it enriches. Run without
layers, or index into a store that implements MetadataFilter.
```

**Why** — a layer reads the chunks a base run already stored, by source, and skips what another
layer derived. That selection is a metadata filter, and this store has none. Nothing was indexed:
the refusal comes before the base runs.

**What to do:** run with `--layers none`, or index into `pgvector` or `qdrant`, which both
filter.

### `LayerNodeCollisionError`

**What it looks like** — a second layer derived a node another layer already stored:

```text
layer 'enrich-with-same' derived node 3f9a…, which the 'enrich-with-questions' layer already
wrote: two layers producing one node would erase each other's marker. Run one of them, or change
what one derives.
```

**Why** — a derived node's id is a digest of its content and its parent. Two layers that derive the
same text from the same chunk produce the same node, and storing the second would overwrite the
first's record of where it came from. That layer's batch is recorded failed and the run stops. The layer named is the one the stored
node is stamped with; a node written before layers were stamped is named by its technique instead.

**What to do:** run only one of the two layers over this corpus, or change the second so it
derives something different.

### `LayerDemotionFailedError`

**What it looks like** — `weft delete` could not mark a corpus-wide layer stale, so it deleted
nothing:

```text
'docs/b.txt' was not deleted: marking corpus layer(s) raptor-corpus stale failed on 'pgvector':
<the store's own error>. Nothing was removed; weft delete docs/b.txt again retries it.
```

**Why** — a layer built over the whole corpus, such as one RAPTOR tree, loses whatever the deleted
source contributed. Weft marks it stale before deleting anything, so it is never served as whole
with a hole in it. Here the mark could not be written, so the delete stopped first.

**What to do:** run the `weft delete` the message names again, once the store is healthy. It
marks the layer stale and deletes the source, and `weft index --layers <name>` then rebuilds the
tree over the sources that remain.

### `LayerIncrementalStageError`

**What it looks like:**

```text
'my-raptor' sets layer.incremental to 'jion', which is not one of its stages. Its stages: raptor,
join.
```

**Why:** a corpus-wide layer can name the stage that joins newly added sources into its existing
tree, rather than rebuilding it: `layer.incremental: join` in the document's `vars`, beside a
stage `- {id: join, use: adrap}`. The value is a stage **id** from the same document, and this one
names none.

**What to do:** set `layer.incremental` to one of the stage ids the message lists, or to `none`,
and the layer then rebuilds in full whenever sources are added. A document that extends a layer and
removes its join stage sets `layer.incremental: none`, since an inherited var cannot be unset. The
var may not name a layer's only stage: that would leave a full build with nothing to run.

### `LayerJoinWritesStoreError`

**What it looks like:**

```text
layer 'enrich-with-raptor': its join stage called supersede, and a join does not write to the
store — it may only return the nodes it creates, and report what they replace through
LayerRevision.replaced.
```

**Why:** the stage `layer.incremental` names joins new sources into a published tree. The store it
reaches through `ctx.require(NodeStore)` answers every read and refuses every write, because
writing there could change or remove a node readers are still being served. The join's build is
recorded failed, and the published tree is left as it was.

**What to do:** if you wrote the stage, return each rebuilt node as one it created, and call
`LayerRevision.replaced(old)` for the published node it stands in for. The build writes and
publishes the new generation itself (`manual/pack-author-guide.md` §9.6). If the stage came from a
pack, report it to the pack's author, and set `layer.incremental: none` so the layer rebuilds in
full in the meantime.

### `LayerNeedsConsumingStoreError`

**What it looks like** — a layer that needs a particular store, over a base that does not name it:

```text
'enrich-with-facts-and-graph' needs a store that turns 'weft-kg-fact' into rows of its own
(consumes), and 'index-text' has none — it stores with 'pgvector'. Installed stores that can:
pgvector-graph.
```

**Why** — the layer's output means something only once a store turns it into rows of its own.
`enrich-with-facts-and-graph` produces facts and mentions, and a graph store builds entities and
relations from them. Without such a store the facts would land in the vector store alone, and
there would be no graph. The stores listed at the end are the installed ones that can.

**What to do:** index with a base that names one of the listed stores, e.g. `index-with-graph`,
then run the layer over it.

### `LayerNeedsGenerationHoldingError`

**What it looks like** — a corpus-scoped layer over a base with a store stage that cannot hold
generations:

```text
'my-raptor' is corpus-scoped (layer.scope: corpus): what it builds over the whole corpus is
published as one generation, and store stage 'side-store' (my-side-store) cannot hold
generations (GenerationHolding). Run it per source (drop layer.scope: corpus), or remove or replace
that stage, or index into a store that can: pgvector, pgvector-graph, qdrant.
```

**Why** — a tree over every document is misleading while half built, so it is written invisibly
and made searchable all at once. Every store the base writes to receives the tree, so every one of
them has to keep nodes hidden until then. The stores listed at the end are the installed ones that
can.

**What to do:** remove `layer.scope: corpus` to build one tree per document, or index with a base
whose every store stage is one of the listed stores.

### `LayerScopeError`

**What it looks like** — a layer document's `layer.scope` is neither `source` nor `corpus`:

```text
'my-raptor' sets layer.scope to 'global'; a layer runs per 'source' or over the whole 'corpus'.
```

**What to do:** set `layer.scope: corpus` for one build over every document, or remove it to run
per document.

### `UnknownLayerVarError`

**What it looks like** — a layer document sets a `layer.` key no layer reads:

```text
'my-raptor' (or a document it extends) sets 'layer.scop', which no layer reads. A layer reads:
layer.scope, layer.store-consumes, layer.incremental.
```

**Why** — a misspelt key would be ignored, so a layer meant to build one tree over the whole
corpus would quietly run per document.

**What to do:** correct the key to one the message lists, or remove it.

### `NoLayersToRunError`

**What it looks like** — `weft index --layers-only` with no layer named anywhere:

```text
--layers-only was given, but no layer is named: pass --layers a,b or set [index] layers in
weft.toml.
```

**What to do:** name the layers with `--layers`, or list them under `[index] layers` in
`weft.toml`.

---

## `weft ask` — `weft_cli.ask`

### `PendingLayerError`

**What it looks like** — `weft ask --pipeline` names a rung that answers from a layer not yet
built over every document:

```text
'questions-then-generate' answers from the 'enrich-with-questions' layer, which is built on 412 of
1,000 sources indexed with 'index-pdf-text'. Build it with `weft index <dir> --layers
enrich-with-questions --layers-only`, or ask again with --allow-pending to answer from the part
that is built.
```

**Why** — an answer from a half-built layer is drawn from part of the corpus while looking like
it came from all of it. The router leaves such a rung out on its own; naming it is refused so the
choice is yours.

**What to do:** finish the layer with the command the message gives, or pass `--allow-pending`.
The answer then says under it how far the layer has got.

### `UnknownRouteVarError`

**What it looks like** — a pipeline document sets a `route.` key the router does not read:

```text
'my-rung' sets 'route.require', which the router does not read. A routable document reads:
route.cost, route.requires, route.summary.
```

**Why** — a misspelt key would be ignored: `route.require` would leave a rung offered over a
layer that is still being built, and `route.sumary` would leave it never offered at all.

**What to do:** correct the key to one the message lists, or remove it.

### `UnknownSubPluginConfigFieldError`

**What it looks like** — a routed `weft ask`, or `weft ask --explain`, refuses before any model
call:

```text
'judge-rung': PanelConfig.panelist is declared SubPlugin(config='setings'), but PanelConfig has
no field 'setings'. PanelConfig's fields: panelist, settings.
```

**Why:** `SubPlugin(config=…)` names the field that holds the composed plugin's `with:` block.
Without it, a routed ask cannot work out which model roles the rung needs, so it refuses rather
than offer a rung that might fail after the router has paid for a call. The declaration is the
pack's, so this is a defect in the pack, whatever your document sets.

**What to do:** if you wrote the pack, set `config=` to one of the fields the message lists. If
the pack is someone else's, report it to its author. Until it is fixed, ask with
`--pipeline <name>`, which skips the router.

### `ConflictingAskModeError`

**What it looks like** — `weft ask --retrieve-only` was given a `--pipeline` whose last stage
is a `Generator`, so the run would have to call a model to finish. Raised by
`weft_cli.commands.AskCommand.run`, before either flag resolves a single plugin:

```text
$ weft ask "what changed?" --retrieve-only --pipeline retrieve-then-generate
weft_cli.commands.ConflictingAskModeError: --retrieve-only and --pipeline
'retrieve-then-generate' cannot both be given: 'retrieve-then-generate' ends in a Generator and
would call a model. Run it without --retrieve-only, or choose a pipeline that already ends in a
retrieval stage and calls no model: 'lexical-retrieve'.
$ echo $?
1
```

*(**Narrowed 2026-09-13 by `R21.5`**, and the dated note is the remedy rather than history: until
then these two flags refused together **always**, which put a store's lexical arm out of reach of
anyone without a model configured. `--retrieve-only --pipeline lexical-retrieve` is now the
offline, account-free way to search the text arm, and the message above is what you get only when
the pipeline you named would have called a model.)*

Exit `1`, not `3` or `4`: neither flag is invalid on its own, and there is no alternative *name*
to offer (this is not a `NAME_RESOLUTION_FAMILY` member — see `weft_cli.commands`'s own
docstring for why), so `weft_cli.exit_codes.exit_code_for`'s default is the right answer, on the
same footing `TargetAlreadyExistsError`/`PipelineAlreadyExistsError` below argue for a certain
outcome that is not a policy question. **What to do:** either drop `--retrieve-only` and let the
named pipeline generate, or name a pipeline that stops at retrieval — the refusal lists the ones
installed. With neither flag, `weft ask` routes through the installed router by default.

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

**What it looks like** — the embedder `[services] embed` selected answered `Failed` or
`NothingToProduce` for the question, or produced a node with no embedding attached:

```text
EmbeddingFailedError: the 'hash' embedder could not embed the question: model unavailable
```

The built-in `HashEmbedder` never actually fails for a non-empty question — this exists for any
other embedder, or a differently-configured one. The message names the plugin, because the fix is
that pack's own configuration. **What to do:** whatever the message names as the reason is the
embedder's own failure — check its configuration or dependency, the same way you would for any pack
that failed mid-run.


### `ReferenceFormatterUnavailableError`

**What it looks like** — you asked `weft` to generate the contract reference and `ruff` is not
installed in the environment you asked from:

```text
ReferenceFormatterUnavailableError: the contract reference is formatted with `ruff` and it could
not be run (Command '[...]' returned non-zero exit status 1.). `ruff` is an optional dependency of
weft-cli because nothing on the index-and-ask path needs it: install `weft-cli[reference]` to
generate the reference.
```

Nothing about indexing or asking reaches this. The contract reference is a *generated document* —
it lists every contract your installed packs publish, which is the thing worth regenerating once
you have third-party packs installed — and it is piped through the same `ruff format` the gate
runs so the generated file is byte-identical to a checked-in one.

**What to do:** `uv add 'weft-rag[reference]'`, or `pip install 'weft-rag[reference]'`. It is a
refusal rather than a fallback on purpose: a hand-rolled line-wrapper would produce a file that
differs from what `ruff` produces, and the whole value of generating the reference is that there is
exactly one formatter deciding what it looks like.


### `PipelineProducedTheWrongShapeError`

**What it looks like** — you ran `weft ask --pipeline <name>` against a pipeline that does not end
in a generating stage:

```text
pipeline 'my-retrieval' finished and produced PassageSet, but `weft ask` needs Answer. A
pipeline's last stage decides the shape of its result: a query pipeline that ends in a retriever
produces passages, and only one ending in a Generator produces an Answer. Add a generating stage,
or run this pipeline with `--retrieve-only`, which asks for the shape it actually produces.
```

Nothing is wrong with the pipeline. It ran to completion and produced exactly what its last stage
produces — the mismatch is between that and what `weft ask` was asked to hand back.

**What to do:** the message names both halves. Either append a stage registered under `Generator`,
so the pipeline produces an answer, or ask for what it does produce with `--retrieve-only`.
`weft pipeline show <name>` prints the resolved stage list if you are not sure what it ends in.

**Why this is an error and not an assertion.** It used to be three bare `assert isinstance(...)`
calls carrying the comment *"every shipped routable pipeline ends in a Generator"* — true of the
pipelines this project ships and checked against documents anyone may write, so a three-line
pipeline of your own made it fail with no message at all. `python -O` also strips `assert`
entirely, which would have let the wrong object flow onward rather than stopping.

---

## Compiling a pipeline document — `weft_cli.compile`

Turning a pipeline document into something runnable needs one thing the document itself never says:
which *contract* each stage fills. A document names a plugin (`use: vector-top-k`) and nothing else,
because the kernel names no capability, so the only thing that can answer is the registry — which
contract currently has a plugin registered under that name. Both errors below are that question
coming back without exactly one answer, and neither is guessed through.

### `UnknownStagePluginError`

**What it looks like** — a stage's `use:` names a plugin no installed distribution registered under
any contract:

```text
stage 'retrieve' names plugin 'vector-top-kk', which no installed distribution registered under any
contract. Installed plugin names: fixed-size, hash, pdf-layout, pdf-text, pgvector, term-frequency-keywords, text.
```

Usually a typo, sometimes a pack that is named in the document but not installed. It is *not* raised
for a `fallback:` name — those are deliberately carried through unchecked, so a document may name a
plugin nobody has shipped yet; making such a document runnable is refused later, by
[`UnknownFallbackError`](#unknownfallbackerror). **What to do:** correct the `use:` field to one of
the names listed — `weft plugins list` shows what is registered and which pack contributed it.

**When a pack could explain the miss, this message says so and says what to install** — carried
repair `R11.3`. `weft plugins doctor` already knows why a pack contributed nothing; until that
repair, a document naming that pack's plugin printed the bare list above and none of it. Now the
same `PackReport` reaches this message:

```text
stage 'store' names plugin 'qdrant', which no installed distribution registered under any
contract. These packs contributed nothing, or only part of what they publish, and one of them
may be the one that provides it: blob (failed); docling (failed); eval (partial);
openai (failed); otel (failed); pdf (failed); qdrant (failed). Installed plugin names:
accuracy, adjudicate-entities, ...

Diagnostic detail:
blob:
    'blob' settings failed validation: 1 validation error for Settings
    root
      Field required [type=missing, input_value={}, input_type=dict]
docling:
    No module named 'docling'
    pip install weft-rag[docling]
...
qdrant:
    No module named 'qdrant_client'
    pip install weft-rag[qdrant]
```

**Every pack that could explain the miss is listed, not just the one you named** — nothing here
knows which of them would have registered `qdrant`, and guessing would be the silent-fallback this
project refuses everywhere else. Each row is keyed on the **pack**, which since G19 is the only
thing that tells them apart: all fourteen first-party packs ship in `weft-rag`, so a message keyed
on the distribution printed the same string seven times. `weft plugins doctor` is the fuller view
of the same facts.

The install line is read from the distribution's own `Provides-Extra`, so it is offered only where
an extra genuinely exists — `weft-rag` ships every first-party pack's code and makes the outside
library declinable (**G19**), which is why the remedy is an extra rather than a second package to
install. A pack with no extra — one whose settings are simply wrong — gets its reason and no
install line, because there is no `pip install` that would fix it.

### `AmbiguousStageContractError`

**What it looks like** — two contracts each have a plugin registered under the one name the document
uses:

```text
stage 'retrieve' names plugin 'hybrid', which is registered under more than one contract: Fuser,
Retriever. A pipeline document names a plugin, never a contract, so there is nothing here that says
which was meant.
```

Not a defect in either pack: two distributions may pick the same short word without knowing about
each other. What is refused is choosing between them, because a silently chosen contract resolves,
runs, and produces a pipeline whose middle does something nobody asked for. `exc.distributions`
names both distributions, which is what tells you who to talk to. **What to do:** one of them must
rename its plugin — a plugin name answers to exactly one contract. Until then, `weft plugins list`
shows both registrations side by side.

### `RefusedStagePluginError`

**What it looks like** — a stage's `use:` names a plugin that no installed distribution registered,
and `[packs] allow` is refusing a distribution that may be the one which would have:

```text
stage 'retrieve' names plugin 'example-fixed', which no installed distribution registered under
any contract. These distributions are refused by [packs] allow in weft.toml and were never
imported, so what they would have registered is unknown: weft-example-query. Add the one that
provides 'example-fixed' to [packs] allow. Installed plugin names: accuracy, ...
```

**Exit `3`, not `4`, and that is the whole point of the class** —
[`docs/02-extension-model.md`](../docs/02-extension-model.md) → *The trust model*: a pipeline naming
a plugin from a `refused` pack "exits 3, refused, and names the config key that would permit it",
while a name no pack provides at all stays `4`. The split is what lets a CI job tell *"fix the
environment"* from *"fix the pipeline"*, and until carried repair `R11.3` the document path answered
`4` to both. `[services]` had always answered correctly, which is exactly why this went unnoticed.

Note what the message does **not** say: that the refused distribution is the one providing the name.
A refused pack is never imported — that is what refusing means — so nothing here can know what it
would have registered, and it says so rather than asserting it. **What to do:** add the distribution
to `[packs] allow` in `weft.toml` if you trust it, or correct the `use:` field. `[packs] allow` is a
list of *distributions*, not packs, which is why the message names one and the entry above names the
other.

---

## Assembling a run — `weft_engine.run_services`

A pipeline resolving is not the same as a pipeline being able to run. A stage may need something
from the *store* — vector search, text search — that the store you configured does not do, and the
kernel cannot check that: it names no capability and does not know what a store is. So the check
happens where both are known for the first time, when the run is assembled, and always **before any
stage runs**. Nothing here adapts and nothing degrades: a run that asked for a text channel is
refused rather than quietly served without one, because a run that answers with half the evidence
looks exactly like a run that answered.

Both errors below exit `4` — fix the pipeline or the configuration, not the corpus.

### `StoreCapabilityMissingError`

**What it looks like** — a stage needs a store capability the configured store does not advertise:

```text
stage 'retrieve' names 'hybrid', which needs TextSearch from the store, and the configured store
'qdrant' does not provide it. 'qdrant' advertises: VectorSearch. Registered stores that do provide
TextSearch: 'pgvector' (weft-store). Nothing here adapts or degrades — a run that asked for a
capability does not quietly proceed without it.
```

Which capabilities a store has is *derived* — Weft asks the store object itself, rather than reading
a flag a store author wrote — so this message describes what your store can actually do, never what
it claims. `exc.stages` names the stage, `exc.distributions` the distributions providing what is
missing, and `exc.remedy` repeats the fix. **What to do:** choose a plugin for that stage that does
not need the capability — the message names the stage — or, if you wrote the store, implement the
capability's methods; there is nothing to declare, because implementing them *is* the declaration.
If the stage names the capability from its `fallback:` list rather than its `use:`, dropping that
name from the list is the third fix: a fallback is a plugin that will really run, so it is checked
here on the same terms as the primary.

**The fourth fix is the key the message names.** `[services] store` selects which registered
`NodeStore` a run uses, so the list of registered stores providing what is missing is directly
actionable: name one of them there and re-index. It is one line and no package edit —

```toml
[services]
store = "pgvector"
```

— and re-indexing is not optional, because the corpus does not move with the key: a store you have
never written to answers every question with nothing and reports no error while doing it.

**A reranker needing `MetadataFilter` fires here too** — `adjacent-chunks` (`weft_retrieve.
adjacent_chunks`) declares `needs_store: ClassVar[tuple[type, ...]] = (MetadataFilter,)`, so a
stage naming it against a store that cannot evaluate a metadata filter refuses at run assembly,
before the stage itself ever runs — message from the source, not reproduced against a real store,
because both shipped stores (`pgvector`, `memory`) satisfy `MetadataFilter` and this needs a
third-party one that does not:

```text
stage 'widen' names 'adjacent-chunks', which needs MetadataFilter from the store, and the
configured store 'acme-store' does not provide it. 'acme-store' advertises: VectorSearch.
Registered stores that do provide MetadataFilter: 'pgvector' (weft-store). Nothing here adapts or
degrades — a run that asked for a capability does not quietly proceed without it.
```

`AdjacentChunks.run` carries its own `isinstance(store, MetadataFilter)` check as well, with its own
message ("'adjacent-chunks' needs a store that can evaluate a metadata filter to find a hit's
siblings by ordinal, and `<StoreClass>` does not provide it. Configure a store that satisfies
MetadataFilter.") — but under `weft ask` and `weft index` you will never see it: `needs_store`
means `check_store_capabilities` above catches the identical gap first, one layer out, before the
stage runs at all. That in-stage check only fires for the other audience this page names in its
intro — a caller driving `AdjacentChunks.run` directly against a hand-built `Context`, bypassing
run assembly entirely. **What to do:** the same fourth fix as above — name a store providing
`MetadataFilter` in `[services] store` and re-index.

### `MalformedNeedsStoreError`

**What it looks like** — a plugin's `needs_store` is not a tuple of capability Protocols:

```text
plugin 'misdeclared' declares needs_store='VectorSearch', which is not a tuple of capability
Protocols. Declare the Protocols themselves — `needs_store: ClassVar[tuple[type, ...]] =
(VectorSearch,)` — importing them from the pack that publishes them.
```

A plugin-authoring mistake, not an operator one, and it fires even when the store would have
satisfied the requirement: a declaration nobody can check is refused rather than skipped, because
skipping it would run the very pipeline the declaration existed to stop. The same error covers a
capability Protocol written without `@runtime_checkable`, which `isinstance` refuses to answer for.
**What to do:** report it to the pack the message names — `weft plugins list` shows which
distribution contributed the plugin.

### `MalformedNeedsServicesError`

**What it looks like** — the sibling above, one attribute over. A plugin's `needs_services` is not
a tuple of capability Protocols:

```text
plugin 'graph-walk' declares needs_services='GraphTraversal', which is not a tuple of capability
Protocols. Declare the Protocols themselves — `needs_services: ClassVar[tuple[type, ...]] =
(GraphTraversal,)` — importing them from the pack that publishes them.
```

**The two declarations, and which one a plugin wants.** `needs_store` says what the **configured
store** must be, and is checked against the one instance `[services] store` names.
`needs_services` (ledger task `11.10`) says what the **run** must offer through a `[services]`
role — a capability no store provides and no `[services] store` could supply, like `weft_kg`'s
`GraphTraversal`. Declaring the second kind under the first is the mistake worth knowing about,
because it does not look like one: the run is refused on every invocation, and the remedy names
`[services] store`, which the operator can change all day without helping.

Like its sibling this is a plugin-authoring mistake rather than an operator one, and it fires even
when a selected role would have satisfied the requirement — a declaration nobody can check is
refused rather than skipped. **What to do:** report it to the pack the message names;
`weft plugins list` shows which distribution contributed the plugin.

---

## Routing a query — `weft_cli.route_ask`

`weft ask <question>` (task 2.8; folded into `weft ask` as the default at task 3.11 — `weft ask
--pipeline <name>` skips this and runs a named pipeline directly instead) resolves `route.yaml` —
whichever installed pack contributes it — runs it to get a `Route`, resolves whichever pipeline it
names, and runs that too. Every error below exits `4`: each is "fix the pipeline, the installation
or the router's own selection," never a question's fault.

### `NoRouterPipelineError`

**What it looks like** — no installed pack contributed a pipeline named `route`:

```text
NoRouterPipelineError: no installed pack contributed a pipeline named 'route'. Run `weft plugins
doctor` to see whether 'weft-retrieve' is active.
```

`weft-retrieve` is the pack that ships `route.yaml` and calls `PackRegistrar.add_pipeline_resource`
for it in its own `register()`. **What to do:** `weft plugins doctor` — if `weft-retrieve` is not
`active`, its own row names why (refused by `[packs] allow`, not installed, or `FAILED` with a
reason); install it, permit it, or fix whatever its report names.

### `UnroutedPipelineNameError`

**What it looks like** — a `RoutingPolicy` selected a pipeline name outside its own
`RouteCatalogue`:

```text
UnroutedPipelineNameError: the router selected 'acme-strategy', which the pipeline catalogue does
not hold. Catalogue: ['no-retrieval', 'retrieve-then-generate', 'route'].
```

Every shipped `RoutingPolicy` (`threshold-ladder`, `nearest-description`, `always`) selects only from
`RouteCatalogue.candidates()` — the same catalogue this message prints — so this cannot happen against
one of them; it means a third-party `RoutingPolicy` returned a name it was never handed. **What to
do:** report it to the pack that ships the `RoutingPolicy` your `route.yaml`'s `decide:` stage names —
`exc.pipeline` is the name it invented.

### `PipelineDidNotProduceError`

**What it looks like** — either resolution (the router itself, or whichever pipeline it selected) ran
to completion but answered `NothingToProduce` or `Failed` rather than `Produced`:

```text
PipelineDidNotProduceError: pipeline 'retrieve-then-generate' did not produce: the 'openai' provider
raised LLMAuthenticationError: invalid API key
```

This is the real reason a stage gave, translated rather than swallowed — the same discipline every
other `Outcome`-to-exception translation in this tree follows: nothing here invents a second message
for a fact a stage already stated plainly. **What to do:** read the reason the message quotes; it
almost always names the actual failing stage and pack. Three reasons worth knowing by name:

**A hit with no recorded chunk position** — `adjacent-chunks` reads each hit's
`weft_chunk.payload.ChunkPosition` to find its ordinal among siblings, and a node indexed before
positions were recorded carries none. Reproduced from a corpus indexed by a release before ledger
**32.1**:

```text
$ weft ask --pipeline context-construction-then-generate "…"
pipeline 'context-construction-then-generate' did not produce: 'adjacent-chunks' needs a recorded
chunk position for node 2b9931e2…, and it carries none. The corpus was indexed before chunk
positions were recorded — run `weft index --reprocess` over it.
$ echo $?
4
```

**What to do:** re-index with `--reprocess`, which rewrites every node's recorded extension facts
(`ChunkPosition` included) under the same node ids, so citations and passage labels stay valid:

```text
$ weft index ./corpus --pipeline index-text --reprocess
9 documents: 9 indexed, 0 unchanged. nodes now stored: 107.
```

— after which the same `weft ask` prints a cited answer, exit `0`.

**A token budget smaller than the best passage** — `repack`'s own reason, when `budget_tokens`
cannot fit even the single best passage. Reproduced with a document setting `budget_tokens: 10`:

```text
pipeline 'tiny-budget' did not produce: 'repack': the best passage alone counts 158 tokens against
a budget of 10 tokens — raise budget_tokens or lower chunk size.
$ echo $?
4
```

Refused rather than packing nothing: an empty context reads downstream exactly like "not in this
corpus" — a wrong answer indistinguishable from a corpus that genuinely has no relevant passage.
**What to do:** raise `budget_tokens`, or lower the chunker's chunk size so a single passage fits
within the budget you have.

**A hit that arrives without a stored vector** — `mmr` scores relevance and novelty from each
hit's own stored embedding and refuses by name rather than treating a missing one as maximally
dissimilar or irrelevant. Not reproduced against a real store; message from the source
(`weft_retrieve.mmr`):

```text
'mmr' scores relevance and novelty from stored vectors, and 1 hit(s) arrived with no stored
embedding: sha256:1b4f….
```

This reaches `mmr` from a retriever or an earlier reranker that never attached a vector to that
hit — `weft_store.pgvector_store.PgVectorStore.search_vector` only ever returns nodes whose
`embedding` column is not null, so a hit that came in through `search_text` alone, or through a
corpus indexed with no embedder configured, is the usual source. **What to do:** put `mmr` after a
stage whose search returns stored vectors — `vector-top-k`, or the vector side of a fused hybrid
ranking — rather than after a text-only retrieval path.

---

## Embedding with a model — `weft_openai`

`weft-openai` registers `openai-embeddings` under the same `Embedder` contract `weft-embed`'s
deterministic
`hash` plugin registers under, and `[services] embed` in `weft.toml` chooses between them — see
[`manual/operations-guide.md`](operations-guide.md) → *Choosing an embedder*. Every error below
comes from the moment something asked it to embed, never from start-up: the pack registers cleanly
with no credential at all, deliberately, so `weft plugins doctor` reports it `active` and a run that
does not use it never needs an account.

### `MissingApiKeyError`

**What it looks like** — `[services] embed = "openai-embeddings"` with no credential configured, reproduced
against a real checkout:

```text
$ cat weft.toml
[services]
embed = "openai-embeddings"
$ weft index docs
no OpenAI credential is configured, so the 'openai' embedder has nothing to authenticate with. Add
`[packs.openai] api_key = "${env:OPENAI_API_KEY}"` to weft.toml — the settings loader
interpolates `${env:...}`, so the key stays in the environment and out of the file.
$ echo $?
1
```

Exit `1`, not `4`: the pipeline resolved, the run failed. **What to do:** exactly what the message
says — add the settings block. `weft-openai` deliberately does *not* read `OPENAI_API_KEY` on its
own the way the vendor SDK would, so that a project that runs on one machine runs on every machine,
and so that this message can name a file that was actually consulted.

### `EmbeddingRequestFailedError`

**What it looks like** — the API refused the call, or could not be reached. Reproduced with a
credential that is not a real key:

```text
$ weft index docs
the embeddings API refused a batch of 1 for model 'text-embedding-3-small': Error code: 401 -
{'error': {'message': 'Incorrect API key provided: sk-not-a*****-key. ...', 'type':
'invalid_request_error', 'code': 'invalid_api_key', 'param': None}, 'status': 401}
```

The vendor's own message is relayed unedited, with the model this pack asked for in front of it —
the SDK redacts the key itself, as above. **What to do:** read the relayed status. `401` is the
credential, `429` is a rate or quota limit, `400` is the request itself — for a batch that reached
`weft index`, most often one chunk longer than the model's input limit — and a connection error is
the network. Rate limits, timeouts, connection failures and `5xx` are marked `transient`, so a
caller that retries knows which ones are worth retrying; the rest will refuse identically forever.

The model and `dimensions` are *not* things to check here, because nothing in `weft.toml` can set
them: `weft index` and `weft ask` run this pack's defaults until a pipeline document reaches them
(see [`manual/operations-guide.md`](operations-guide.md) → *Choosing an embedder*). A `400` naming
a model that does not exist means a library caller built `OpenAIEmbedderConfig` by hand, or the
`base_url` in `[packs.openai]` points at a server that does not serve that model.

### `UnembeddableNodeError`

**What it looks like** — a node reached the embedder with no text in it:

```text
node 'sha256:1b4f…' has no text to embed, and the embeddings API refuses an empty input. Drop empty
chunks before this stage, or check the chunker that produced it.
```

The API rejects an empty string with `'$.input' is invalid`, which names neither the node nor the
document it came from, so this pack refuses first and names the node. Note that `hash` embeds an
empty string quite happily — this is a real behavioural difference between two plugins of one
contract, not a bug in either. **What to do:** find the node the id names (it is the content digest,
so an empty or whitespace-only chunk) and fix whatever produced it.

---

## Generation, offline and online — `weft_llm`

Not yet reachable through `weft ask` — `[llm.roles]` (below) names which provider and model
answer a call, but nothing yet resolves a role at run time; that arrives with the `LLM` service,
one task later. Every class here is reachable today by driving an `LLMProvider` plugin directly —
`weft-llm`'s own `scripted` (which never raises any of these; it makes no call to fail) or
`weft-openai`'s `openai`, whose `_map_error` table turns each of OpenAI's own exception classes
into exactly one of the fourteen below. A pack author writing a second provider, or a technique
plugin's own retry logic, catches these — see `weft_llm.errors`'s own module docstring for the
two places this taxonomy is decided on rather than merely documented.

### `LLMError`

Never raised directly — the root of the taxonomy. Catch this to catch every generation failure
this pack or any `LLMProvider` it registers can raise, the way `WeftError` catches everything
Weft itself raises, narrowed to one family.

### `LLMTransientError`

Never raised directly — the branch every class below marked "worth retrying" inherits.
`transient` is `True` on every instance without a leaf class having to set it, and this is the one
class the retry wrapper's `isinstance` check actually looks for.

### `LLMRateLimitError`

**What it looks like** — the account is over its request or token budget for the vendor's window:

```text
LLMRateLimitError: Error code: 429 - {'error': {'message': 'Rate limit reached for gpt-4o-mini...',
'type': 'requests', 'code': 'rate_limit_exceeded'}}
```

**What to do:** wait for the window to reset, or reduce concurrency — `transient=True`, so a
caller's own retry logic (not the kernel's; it runs none) is the right place to handle this
automatically rather than surfacing it to an operator.

### `LLMTimeoutError`

**What it looks like** — the request was sent and no answer arrived before the client's deadline:

```text
LLMTimeoutError: Request timed out.
```

**What to do:** retry — `transient=True` — or raise `[packs.openai] timeout_seconds` if this
model's answers are routinely slower than the SDK's own default allows.

### `LLMConnectionError`

**What it looks like** — the request never reached the vendor at all:

```text
LLMConnectionError: Connection error.
```

**What to do:** check DNS and outbound network access from wherever `weft` is running; `base_url`
in `[packs.openai]` if this project talks to a proxy or a compatible server rather than the
vendor's own endpoint.

### `LLMServiceUnavailableError`

**What it looks like** — the vendor accepted the connection and answered with its own `5xx`:

```text
LLMServiceUnavailableError: Error code: 503 - {'error': {'message': 'The server had an error...',
'type': 'server_error'}}
```

**What to do:** retry — `transient=True` — the vendor's own infrastructure, not this request, is
the failure.

### `LLMPermanentError`

Never raised directly — the branch every class below inherits, `transient=False` without a leaf
class having to set it. Retrying the identical call will refuse identically forever.

### `LLMAuthenticationError`

**What it looks like** — no credential configured, reproduced against a real checkout with no
`[packs.openai]` block at all:

```text
no OpenAI credential is configured, so the 'openai' provider has nothing to authenticate with. Add
`[packs.openai] api_key = "${env:OPENAI_API_KEY}"` to weft.toml — the settings loader
interpolates `${env:...}`, so the key stays in the environment and out of the file.
```

Also raised for a credential the vendor itself rejects — reproduced against the real API with a
key of the right shape and the wrong value:

```text
LLMAuthenticationError: Error code: 401 - {'error': {'message': 'Incorrect API key provided:
sk-not-a*****-key. ...', 'type': 'invalid_request_error', 'code': 'invalid_api_key'}}
```

**What to do:** the first is `[packs.openai] api_key` missing entirely; the second is the
same key, wrong. Either way, fix the credential this pack reads — never the `OPENAI_API_KEY` the
vendor SDK would read on its own, which this pack deliberately ignores.

### `LLMPermissionDeniedError`

**What it looks like** — the credential is real but is not allowed the model or action requested:

```text
LLMPermissionDeniedError: Error code: 403 - {'error': {'message': 'Your account does not have
access to model gpt-4o-mini', 'type': 'invalid_request_error'}}
```

**What to do:** a different credential for the model this project asked for, or a different
`model` in the `[llm.roles]` entry that names it. Caught separately from `LLMAuthenticationError`
because the structured-output cascade (one task later) re-raises this one specifically rather than
stepping down a tier — a bad key surfacing as a low structured-output score is the failure that
repair exists to prevent.

### `LLMBadRequestError`

**What it looks like** — the vendor rejected the shape of the request itself:

```text
LLMBadRequestError: Error code: 400 - {'error': {'message': "'model' is a required property",
'type': 'invalid_request_error'}}
```

This is also `_map_error`'s catch-all for any `openai.APIError` this table has no more specific
row for — a `409` or `422` this pack has not seen before lands here rather than escaping unmapped.
**What to do:** read the relayed vendor message; it names the malformed field.

### `LLMNotFoundError`

**What it looks like** — the model or deployment named in the request does not exist for this
account:

```text
LLMNotFoundError: Error code: 404 - {'error': {'message': 'The model `gpt-4o-mnii` does not
exist...', 'type': 'invalid_request_error'}}
```

**What to do:** check the model string in `[llm.roles]` — usually a typo, occasionally a model
retired since the role was configured.

### `LLMContentFilterError`

**What it looks like** — the vendor's own moderation refused the request before it was answered:

```text
LLMContentFilterError: Error code: 400 - {'error': {'message': "Invalid prompt: your prompt was
flagged...", 'type': 'invalid_request_error', 'code': 'content_policy_violation'}}
```

**What to do:** this is a fact about the content sent, not about this project's configuration —
change what is being asked, or accept that this question cannot be answered through this vendor.

### `LLMContextLengthError`

**What it looks like** — the conversation, tokenised, is longer than the model accepts:

```text
LLMContextLengthError: Error code: 400 - {'error': {'message': "This model's maximum context
length is 128000 tokens...", 'type': 'invalid_request_error', 'code': 'context_length_exceeded'}}
```

**What to do:** fewer or shorter passages reaching the prompt — a `ContextPacker`'s `top_n`, most
often — or a model with a wider context window.

### `LLMCompletionError`

**What it looks like** — the vendor answered successfully and the answer could not be used:

```text
LLMCompletionError: could not parse a JSON object from the completion after 3 attempts. Raw text
(200 chars): "I'm not able to provide that in the requested format because..."
```

Never raised by a provider itself — a provider has no opinion on what its caller intended to do
with the text it returned. Raised by the structured-output cascade, one task later, once its last
tier exhausts every way it knows to parse a completion into the type it was asked for.
`transient=False`: resending the identical request will not make a differently-shaped answer more
likely. **What to do:** read the raw text the message truncates to 200 characters — it is usually
the model explaining, in prose, why it declined the shape asked for.

---

## Which model answers a role — `weft_engine.llm_roles`

### `NoRungOfferedError`

**What it looks like:**

```text
the router has no rung to offer: every routable pipeline needs a model role [llm.roles] does not
map — 'grade-then-generate' needs 'grade'; 'iterative-retrieve' needs 'grade'. Roles mapped in
weft.toml: generate, index, route. Map 'grade' under [llm.roles], or ask with --pipeline <name>.
```

**Why:** a routed `weft ask` offers only the pipelines whose model roles are all mapped under
`[llm.roles]`, so it never pays for a routing call and then fails on a role nobody configured.
Here every pipeline it could offer needs a role that is not mapped.

**What to do:** map the roles the message names under `[llm.roles]` in `weft.toml`, or name a
pipeline yourself with `weft ask --pipeline <name>`. `weft ask --explain` lists every pipeline left
out and the role it lacks.

### `UnmappedLLMRoleError`

**What it looks like** — a call was made under a role `[llm.roles]` never named:

```text
UnmappedLLMRoleError: no [llm.roles] entry maps role 'grade'. Roles mapped in weft.toml: generate,
route. Add this line under [llm.roles] in weft.toml:
grade = { provider = "openai", model = "<model>" }
```

**What to do:** add the line the message prints under `[llm.roles]` in `weft.toml`, with a real
model name — see [`manual/operations-guide.md`](operations-guide.md) → *Choosing which model
answers*. The suggested provider is one that is installed; it is never `scripted`, which cannot
give a role that needs a structured answer one. When no other provider is installed, the message
says to `pip install "weft-rag[openai]"` instead. It lists every role that *is* mapped, so a typo
in a technique plugin's own `role:` configuration reads as a typo rather than a mystery.

---

## The LLM client — `weft_llm.client`, `weft_llm.models`

Everything in this section is raised *before or around* a provider call, by the `LLM` service
rather than by a vendor adapter. None of them is transient: retrying an identical call produces an
identical refusal, which is why they are all `LLMPermanentError` subclasses.

### `LLMProviderFaultError`

**What it looks like** — a provider adapter let something out that is not an `LLMError`:

```text
LLMProviderFaultError: provider 'acme' (role 'generate') raised KeyError: 'choices'. That is not an
LLMError, so nothing downstream could have caught it by class — it is a defect in the provider
adapter, not a failure mode of the model.
```

**What to do:** this is a bug in the provider pack, not in your configuration — the adapter's job is
to turn every vendor failure into exactly one `weft_llm.errors.LLMError` leaf. Report it to whoever
ships that pack, naming the provider from the message. If it is a first-party pack, the missing row
belongs in its vendor→domain mapping table. Working around it by catching `Exception` at the call
site is what this class exists to make unnecessary.

### `NativeStructuredUnsupportedError`

**What it looks like** — `complete_structured` was called for a role whose provider does not offer
native structured output:

```text
NativeStructuredUnsupportedError: provider 'scripted' (role 'grade') does not offer native
structured output. Ask `native_structured_available('grade')` first, or call the structured-output
cascade, which steps down for you.
```

**What to do:** call `weft_prompts.cascade.execute(...)` instead of the client directly — it asks
first and steps down through two more tiers when the answer is no. Only code that deliberately
requires tier 1 should see this, and the remedy for *that* code is to point the role at a provider
that offers it.

### `LLMGenerationLoopError`

**What it looks like** — `weft_llm.loop_guard` recognised the answer settling into a repeating
span mid-stream, and generation was stopped rather than left to keep filling the terminal:

```text
LLMGenerationLoopError: provider 'scripted' (role 'generate') was generating a repeating span and
was stopped after 214 characters rather than left to keep filling the terminal. This is a
loop-breaker for a model that got stuck, not a judgment about the content — retrying the identical
prompt against the same model is likely to loop again; try a different prompt, role, or model.
```

This is a known failure mode of small or local models under greedy decoding, not a judgment about
whether the generated text is true — it is never raised because an answer looked wrong, only
because it stopped saying anything new. Every token shown before the guard fired is exactly what a
reader already saw; nothing already displayed is retracted, and `weft_cli.cli.run_command` closes
the run's `TokenSink` with this error's own message as `reason`, so a scrollback shows a distinct
`[stream error: ...]` line rather than an answer that merely looks like it finished. **What to do:**
try a different prompt or a different model for the role the message names — replaying the
identical request against the same model tends to reproduce the same loop. If this fires on
legitimately repetitive content that is not a markdown table (the guard already excludes those),
the thresholds are `[llm.loop_guard]` in `weft.toml` — raising `similarity_threshold` (closer to
`1.0`) or lowering `diversity_threshold` (closer to `0.0`) makes the guard fire on fewer, more
extreme cases, per [`manual/operations-guide.md`](operations-guide.md).

### `TokenCountUnavailableError`

**What it looks like** — `repack`'s token budget (or any other caller of
`LLMClient.count_tokens`) asked for a count and the role's provider could not produce one, either
because it does not offer counting at all or because it does and does not know the model:

```text
TokenCountUnavailableError: provider 'scripted' (role 'generate') cannot count tokens for model
'any-model'. Map role 'generate' to a provider that counts (the `openai` pack does, for models its
encoder knows), or remove the budget that needs this count.
```

**What to do:** one of the two things the message says. Point the role at a provider that offers
`weft_llm.contract.TokenCounting` — `openai`, for a model its `tiktoken` encoding knows — or drop
the feature that needs a token budget for this role. Never estimated by character count: a wrong
count would silently over- or under-fill a budgeted prompt, so this is refused rather than guessed.
An `openai-compatible` account never counts, whatever `[packs.openai-compatible] stream_usage`
says — its model names are not the vendor's, and the vendor's encoder would count an aliased model
wrongly.

### `CorpusOverTokenBoundError`

**What it looks like** — `whole-corpus` hands the generator every leaf of the corpus, and it counted
more tokens than its bound before it finished reading:

```text
CorpusOverTokenBoundError: 'whole-corpus': the corpus's leaves count at least 100,412 tokens against
a bound of 100,000 tokens — raise max_tokens if the model's context holds the corpus, or ask a
pipeline that retrieves, such as retrieve-then-generate
```

**What to do:** one of the two things the message says. The count is *at least*, because reading
stops at the first leaf past the bound. Raise `max_tokens` in a project document deriving
`whole-corpus-then-generate` only if the generating model's context window holds the corpus and
you accept paying for every token on every question; otherwise ask a retrieving pipeline. The
corpus is never cut to fit: a cut corpus answers from whichever part happened to be read first.

### `ModelProviderMismatchError`

**What it looks like** — a `[llm.roles]` entry's model string carries a provider prefix naming a
different provider from the entry's own:

```text
ModelProviderMismatchError: model string 'openai/gpt-4o-mini' names provider 'openai', but the
[llm.roles] entry using it resolves to provider 'scripted'. Refused rather than guessed: drop the
prefix, or point the role at 'openai'.
```

**What to do:** exactly what the message says — one of the two. A prefix is only read as a provider
when it names a provider some role in this `weft.toml` maps, so a model id that merely contains a
slash (`meta-llama/Llama-3-8B`) never trips this.

### `UnknownModelError`

**What it looks like** — a provider publishes a model catalogue and the model a role names is not
in it:

```text
UnknownModelError: provider 'acme' does not offer model 'tiny' (from 'tiny'). Models it advertises:
small-v2, large-v2.
```

**What to do:** write one of the models the message lists into the role's `model =` line. This
refusal arrives before any network call, so a typo costs a second rather than an HTTP 404 halfway
through a run. A provider that publishes no catalogue is asked for whatever you wrote.

### `AmbiguousModelError`

**What it looks like** — a short model name matches two entries in a provider's catalogue:

```text
AmbiguousModelError: model 'small-v2' (from 'small-v2') matches 2 entries in provider 'acme''s
catalogue: eu/small-v2, us/small-v2. Write one of them in full — choosing between them by ordering
is a decision this code must not make.
```

**What to do:** write the qualified name. Picking one by sort order would be a data-residency (or
tier, or region) decision made by an accident of ordering, which is exactly the silent coercion
`docs/02-extension-model.md` §5 records four times over.

---

## Prompts — `weft_prompts`

The first three are raised where a prompt class is **defined**, not where it renders, so a
mis-declared prompt cannot reach a run at all. If you see one, it arrives at import time, naming the
prompt and the locale.

### `TemplateVariableError`

**What it looks like** — a template names a placeholder its input model cannot supply:

```text
TemplateVariableError: judge:pl: the template names placeholder(s) 'pytanie' that Ask does not
supply. Fields it does supply: evidence, question.
```

**What to do:** rename the placeholder to one of the fields the message lists, or add the field to
the prompt's `input_model`. The same class covers a template that is not a valid `${name}` template
at all — a literal `$` must be written `$$`.

### `UnusedTemplateFieldError`

**What it looks like** — an input model declares a field one locale's template never renders:

```text
UnusedTemplateFieldError: judge:pl: Ask declares field(s) 'evidence' that this template never
renders. A field nothing renders is configuration the model is never told about — remove it, or use
it. In a translation this is usually a dropped ${placeholder}.
```

**What to do:** almost always, restore the `${placeholder}` a translation dropped. This is checked
per locale precisely because that failure is otherwise invisible: the code is unchanged, the prompt
still renders, and answers get worse in one language only.

### `MissingFallbackLocaleError`

**What it looks like** — a prompt declares translations but not the `en` one every lookup falls
back to:

```text
MissingFallbackLocaleError: prompt 'judge' declares locales pl but not 'en', which every lookup
falls back to. Add the 'en' text: without it a run under an untranslated locale has nothing to
degrade to.
```

**What to do:** add the `en` entry to the prompt's `texts`. Locale selection is exact locale →
primary subtag → `en`, and the last step needs somewhere to land.

### `PromptInputMismatchError`

**What it looks like** — `render` was handed a model that is not the prompt's declared
`input_model`:

```text
PromptInputMismatchError: prompt 'judge' renders Ask, and was handed a Verdict. The caller and the
prompt disagree about what this question needs.
```

**What to do:** build the model the message names. This is a bug in the calling technique rather
than in configuration — a prompt's input model *is* its interface.

---

## Aggregating metric observations — `weft_eval.aggregate`

Both errors below are raised while folding many per-sample `Outcome[MetricScore]` observations of
one metric into one `MetricAggregate` (task 4.3, `docs/09-release.md` §4 V4). Neither is a name
*resolution* failure — there is no alternative name to offer, only a fact that a caller handed this
code two things that disagree — so neither joins `NAME_RESOLUTION_FAMILY`.

### `MismatchedMetricNameError`

**What it looks like** — two observations passed to one `aggregate()` call report different
`metric_name`s:

```text
MismatchedMetricNameError: cannot aggregate: one observation reports metric_name='precision@7',
but an earlier observation in the same aggregate reported 'precision@3' — every `Produced`
observation folded into one aggregate must report the identical name the metric itself computed;
mixing two configurations (e.g. two different `k`) into one aggregate is a caller error, not
something to average over.
```

**What to do:** group observations by which configuration actually produced them before calling
`aggregate()`. Seeing this means two runs of the same registered plugin at two different `with:`
values (two different `k`, say) were folded into one call — split them into two calls, one per
configuration, the same way `weft-eval`'s own two-thresholds demonstration (task 4.1) keeps two
`AtThresholdConfig` instances' results apart.

### `ReportedNameMismatchError`

**What it looks like** — a report's key for a metric's aggregate does not match the name that
metric actually computed:

```text
ReportedNameMismatchError: report key 'precision_at_k' does not match the name this metric
computed, 'precision@7' — a report's key must be the name the metric itself reports for what it
measured, never a caller-chosen label maintained by hand.
```

**What to do:** use the metric's own computed name — `MetricAggregate.reported_name`, read off
`MetricScore.metric_name` — as the report key, rather than a hand-typed literal. This guards
against a documented failure mode: two dataset-track runners hardcoded the report
key `'precision_at_k'`/`'recall_at_k'` while the real `k` was a caller-supplied
`similarity_top_k`, so the key silently stopped describing what was actually measured the moment
`k` was anything but the value baked into the literal. Seeing this error means `weft_eval.
aggregate.aggregate_report` caught that exact drift before it reached a run record or a CLI table.

---

## Asking what a run did — `weft_cli.eval_commands`

### `EmptyCorpusError`

**What it looks like** — `weft eval run` pointed at a directory none of the named pipeline's
own extractor claims anything in, reproduced against a real checkout with an empty directory:

```text
$ mkdir empty && weft eval run empty index
'empty' produced nothing to index under pipeline 'index' — there is nothing for a run record to
carry a corpus identity over. Point --path at a directory pipeline 'index' can actually read.
$ echo $?
1
```

Unlike `weft index` over the same directory, which is a silent, successful no-op
(`weft_cli.ingest`'s own module docstring: "An empty directory is not an error"), `weft eval run`
refuses: a persisted run record with zero documents has a content-derived digest
(`weft_eval.run_record.corpus_identity`) indistinguishable from any other empty corpus's digest,
so it would not be a fact worth diffing a later run against — a record that looks complete and
measures nothing. **What to do:** point `--path` at a directory the named pipeline's own
`extract` stage can actually read, or run `weft index` first to confirm which formats it claims.

### `NoBaselineRunsError`

**What it looks like** — `weft eval compare --baseline` naming a pipeline no persisted run under
`runs/` ever ran, reproduced from outside the repository against an installed `weft-rag`:

```text
$ weft eval compare 6f04fe6b-...-76990a5a778f 57998ac5-...-f8fe088200305 --baseline hybrid-then-generate
'hybrid-then-generate' names no persisted baseline repetition under 'runs' (excluding the two runs
being compared). Pipelines actually run: index-text, rung-small-chunks.
$ echo $?
4
```

`--baseline` names a **pipeline**, never a run id: its repetitions are every persisted run whose
own resolved pipeline carries that name, with the two runs being compared excluded — a rung is not
one of its own baseline's repetitions. So the two ways to see this are naming a pipeline you have
not run yet, and naming the pipeline of one of the two runs you are comparing when it has no
*other* run on disk. Exit `4`, not `1`: this is fitness function 12's family, "fix what you typed",
the same footing an unknown run id already has. **What to do:** the message lists every pipeline
that has actually been run. Run the baseline pipeline at least twice — `weft eval run <corpus>
<baseline-pipeline> --questions <file>` — before asking for a verdict against it.

### `UnknownQuestionKindError`

**What it looks like** — `weft eval compare --kind` naming a question kind neither run recorded,
reproduced from outside the repository against an installed `weft-rag`:

```text
$ weft eval compare 50c889b0-...-77068cc3637f 6f96e716-...-f7715d321e --kind requires-graph-hop
'requires-graph-hop' is not a question kind either run recorded. Kinds recorded: definitional,
methodological.
$ echo $?
4
```

`--kind` restricts a comparison to one class of question, reading each run's own per-kind slice
instead of its whole-run mean — so a rung that is better at one class and worse at another reports
two numbers rather than one in which they cancel. A kind reaches a run from the `kind` field of the
questions file that run was scored against; a question with no `kind` contributes to the mean and
to no slice, because an unclassified question is not a class.

Exit `4`, not `1`: this is fitness function 12's family, "fix what you typed", the same footing an
unknown run id and an unknown baseline pipeline already have. It is deliberately a **refusal**
rather than a comparison of two absent slices — a verdict computed from two numbers nobody measured
is one a reader cannot tell from a real one.

**What to do:** the message lists every kind either run actually recorded. Either name one of
those, or re-run with a question file whose questions carry the `kind` you want to compare — `kind =
"methodological"`, or an axis named `kind` in a set that states `kind` absent — and compare the new
runs. Dropping `--kind` compares the whole run, which is what this command did before the flag
existed. `--kind X` is the case `--slice kind=X` of `UnknownSliceError`'s flag.

### `UnknownSliceError`

**What it looks like** — `weft eval compare --slice` naming an `axis=value` pair neither run
recorded:

```text
$ weft eval compare <run-a> <run-b> --slice evidence=video
'evidence=video' is not a slice either run recorded. Slices recorded: evidence=text, evidence=text-table, split=dev.
$ echo $?
4
```

A question file declares axes (`[question_set] axes = ["evidence", ...]`) and each question a value
for each; a run records a mean per value beside its whole-run mean, and `--slice` reads that number
on both sides instead. A value no scored question carried has no slice, so it is refused rather than
compared as two absent numbers. **What to do:** name one of the listed pairs, written `axis=value`.

### `TooFewRepetitionsError`

**What it looks like** — a baseline that exists but was run only once, reproduced the same way:

```text
$ weft eval run ./corpus index-messy-text --questions questions.json
run 9a1c... persisted (./corpus -> pipeline 'index-messy-text'). ...
$ weft eval compare 6f04fe6b-...-76990a5a778f 57998ac5-...-f8fe088200305 --baseline index-messy-text
a baseline needs at least 2 repetitions to measure its own variability; 1 given — V3's own failure
clause: 'the baseline was run once, in which case it records no interval and no later run can be
judged against it.'
$ echo $?
1
```

This is `09-release.md` §4.3's derivation refusing to proceed without its own input. The whole
point of the instrument is that **no tolerance is chosen by anybody** — the only number a
difference is judged against is the width of the interval the baseline's own repetitions spanned,
so a baseline that was never repeated has measured nothing and can license no verdict. A tool that
answered anyway would be inventing the threshold `09` §4.4 forbids. Exit `1`, deliberately not
`4`: the name resolved and nothing is misspelled — the runs on disk simply cannot answer the
question, which is "something failed", the footing `EmptyCorpusError` and `IncomparableRunsError`
already have. **What to do:** run the baseline pipeline again, at least once more, and re-compare.
A deterministic pipeline will record a zero-width interval, which is correct and strict — it means
any difference at all is outside what the baseline produced by repeating itself.

### `IncomparableRunsError`

**What it looks like** — `weft eval compare` given two run ids whose persisted corpora differ,
reproduced against two real runs over two different directories:

```text
$ weft eval run corpus-a index
run 3f9c...-1 persisted (corpus-a -> pipeline 'index'). produced 1, nothing to produce 0, failed
0. nodes now stored: 1. corpus: 'corpus-a' (a1b2c3d4e5f6…).
$ weft eval run corpus-b index
run 3f9c...-2 persisted (corpus-b -> pipeline 'index'). produced 1, nothing to produce 0, failed
0. nodes now stored: 1. corpus: 'corpus-b' (f6e5d4c3b2a1…).
$ weft eval compare 3f9c...-1 3f9c...-2
'3f9c...-1' and '3f9c...-2' are not comparable as a change of pipeline alone: corpus differs
('corpus-a' a1b2c3d4e5f6… vs 'corpus-b' f6e5d4c3b2a1…). A comparison is only meaningful when the
corpus, model versions and question set agree and only the pipeline differs — otherwise a metric
delta cannot be attributed to the pipeline change ('09-release.md' §4, V3's own failure clause).
Which distributions were active, and at which versions, is reported beside a comparison and never
refused on.
$ echo $?
1
```

This is `09-release.md` §4's V3 failure clause, enforced at the CLI seam rather than left for a
reader to misattribute a number later: "a shipped technique's improvement is reported against...
a baseline from a different corpus, pipeline or model version." Which distributions were active,
and at which versions, is not on that list: since carried repair `R22.11` a difference there is
printed beside the comparison as `packaging differs, reported not refused: …`, because a version
bump alone had been refusing comparisons. **What to do:** the message names every fact that
differed. Compare two runs over the identical corpus, model versions and question set —
`weft eval run` twice against the *same* `--path`, once per pipeline, is 4.9's own exit
demonstration and the shape this error exists to hold every other caller to as well.

**One reason this error gives has a different remedy, because no corpus changed.** *"corpus
digests are not over the same thing (document-bytes vs not recorded)"* means one of the two
records was written before 2026-09-12, when the digest was over each document's resolved
filesystem path rather than its bytes. Nothing about the corpus differs and nothing is
misconfigured; the two digests simply answer different questions and cannot be compared even
over identical files. **What to do:** re-take the older arm on this version. There is no
migration — the bytes an old record digested were never written down. `manual/operations-guide.md`
→ *What the corpus digest is over, and why a record says so* has the reproduction.

### `UnpairableRecordsError`

**What it looks like** — `weft eval compare` given two replay records of the same corpus and
question set whose pool manifests differ, reproduced from the built wheels on 2026-09-21 with a
Phase 40 record and a copy of it naming another manifest:

```text
$ weft eval compare aaaaaaaa-0000-0000-0000-000000000001 aaaaaaaa-0000-0000-0000-000000000002
these two records do not pair question by question: pool manifest differs (8593b58c918a… vs ffffffffffff…) — task 40.2: two arms compare only on the same pool manifest and question-set digests
$ echo $?
1
```

A paired difference subtracts one record's score on a question from the other's. Two records that
replayed different pools, or were scored on different question sets, can share every question id
and still be answering different questions, so the difference would be about nothing. Records that
carry no pool manifest, or whose question-set digests were computed two different ways, are not
refused; there is nothing to disagree. `weft eval experiment` makes the same check before any arm
runs and reports it as `IncomparableArmsError`. **What to do:** pair records that replayed the same
manifest over the same question file. The message prints the first twelve characters of each
digest; the full values are in each record, `runs/<run>.json`, as `experiment.pool_manifest` and
`question_set_digest`.

### `PoolManifestError`

**What it looks like** — reading a frozen retrieval pool (`runs/pools/<run_id>.json`, written by an
experiment arm with `capture_pool = true`) fails on the file itself:

```text
'runs/pools/torn.json': not valid JSON: Expecting value: line 2 column 1 (char 37)
```

**Why it can happen at all.** A pool is written once, by the run that captured it, and read back
instead of searching again. A file cut short by an interrupted copy, or edited by hand, is no
longer the pool that run captured. **What to do:** copy the manifest again from the machine that
captured it, or capture the pool again with the capturing arm. Do not repair it by hand: its sha256
is recorded with every run that reads it.

### `PoolManifestSchemaError`

**What it looks like:**

```text
'runs/pools/new.json': schema_version 99 is not the 1 this weft-rag reads.
```

**Why it can happen at all.** The manifest was written by a `weft-rag` release whose pool format
this one does not know. It is refused before its fields are read, so a newer field is never
silently dropped. **What to do:** read it with the release that wrote it, or upgrade `weft-rag`.

### `PoolIntegrityError`

**What it looks like** — an arm naming `pool = "..."` replays a captured pool, and something the
manifest, the question file or the store agree on has moved since capture:

```text
question 'q-1' names chunk 'n2abc123', whose content no longer hashes to what the pool captured.
```

Other shapes the same error takes, each naming what moved: a question in the question file but
not in the manifest, or the reverse; a question whose text or `relevant_documents` has changed
under an id the manifest already used; a chunk the store no longer holds at all; and a store row
count that no longer matches the manifest's own, checked once before the first question replays
and once again after the last one —

```text
the store now holds 71 row(s), but the pool was captured against a store holding 70 row(s) —
something changed the store while this replay ran.
```

**Why it can happen at all.** A replay never embeds, never searches and never reads the corpus —
its whole claim to being a fast, deterministic comparison is that it reruns the *rerank* half of a
rung against exactly the chunks a capture run once retrieved. That claim is only honest while the
question file, the manifest and the store all still agree with each other; a question file edited
after capture, a manifest copied beside the wrong store, or another process writing to the same
store while a replay runs all break the agreement silently unless this refuses by name the moment
it is noticed.

**What to do:** if the question file changed on purpose, capture the pool again against it. If the
manifest is right and the store is wrong, replay against the store the pool names in `store`/
`corpus_digest` (`runs/pools/<run_id>.json`) rather than whatever `[services] store` happens to
point at now. Never edit the manifest by hand to make a mismatch go away — its own sha256 is what
every replay's record pins its trust to.

### `CollidingScoreNameError`

**What it looks like** — a run scoring a generating pipeline (`weft eval run --query-pipeline` or
`weft eval experiment`) refuses because a retrieval metric and an answer metric report one name:

```text
a retrieval metric and a generation metric both report 'overlap' in this run. A scored run keys
both its aggregates and its per-question scores by the name a metric computes, so one would
silently replace the other. Have one pack's metric report a name of its own.
```

**Why it can happen at all.** Since ledger `32.14` a generating pipeline is scored twice in one run
— its passages by the retrieval metrics and its answer by the answer metrics — and both land in one
record keyed by reported name. Weft's own metrics report distinct names; a clash means an installed
pack reports a name another metric already uses, across the two kinds. `CollidingMetricNameError`
below is the same refusal within one kind.

**What to do:** uninstall the pack you did not mean to score with, or ask its author to report a
name of its own.

### `CollidingMetricNameError`

**What it looks like** — two installed metrics compute the same reported name, so `weft eval run
--questions` refuses rather than scoring:

```text
two registered metrics both report 'precision@5' — 'precision-at-k' and 'acme-precision'. A run
record keys both its aggregates and its per-question scores by the name a metric computes, so one
of the two would silently replace the other. Uninstall one, or have its pack report a name of its
own.
```

**Registered name and reported name are different things.** A metric registers under a plugin name
(`precision-at-k`) and *reports* the name it computed (`precision@5`, which carries its `k`). A run
record is keyed by the second, because that is what a reader compares across two runs — so two
plugins that report one name would occupy one entry, and the one scored second would replace the
first without a word.

**What to do:** the message names both registered plugins. Uninstall the pack you did not mean to
score with, or ask its author to report a name of its own — a metric that reports a name another
pack already publishes is claiming that pack's identity, which is `docs/10-technique-catalogue.md`
§2.1's rule about names one level down.

### `UnresolvableLabelError`

**What it looks like** — a `--questions` file whose `relevant_documents` label names no document
in the corpus being scored. Reproduced against a real two-document corpus and a real run:

```text
$ weft eval run corpus index-text --questions questions.json --yes ; echo $?
relevant_documents label 'ax-1304.7717v2' names no document in the scored corpus. Valid options: /tmp/t165/corpus/arxiv/1304.7717v2.pdf.txt, /tmp/t165/corpus/other.txt
4
```

**A label is a corpus-relative path, and it matches a document when its path components are a
suffix of that document's.** So `arxiv/1304.7717v2.pdf.txt` names that file wherever the corpus is
staged, a bare `other.txt` names it when only one document has that name, and a whole resolved
path is its own suffix and keeps working. What does *not* resolve is an identifier from somewhere
else — a manifest id like `ax-1304.7717v2`, a title, a DOI — because nothing in the corpus is
named that.

**Why this refuses rather than scoring zero.** A label that matches nothing would count every hit
as irrelevant and report `0.000` at every cutoff, and a `0.000` meaning *the ground truth is
wrong* is indistinguishable in a report from a `0.000` meaning *retrieval failed*. This project
has made that mistake and recorded it: an early RAPTOR measurement read `0.000` everywhere and was
not reported as a finding.

**What to do:** rewrite the label as the document's path relative to the corpus directory. The
message lists every document the run actually scored, so the label you want is in it.

### `AmbiguousLabelError`

**What it looks like** — a label that names more than one document, because two directories hold a
file of the same name:

```text
$ weft eval run corpus index-text --questions questions.json --yes ; echo $?
relevant_documents label 'other.txt' names 2 documents in the scored corpus: /tmp/t165/corpus/b/other.txt, /tmp/t165/corpus/other.txt
4
```

**Refused rather than resolved by picking.** Whichever of the two the resolution happened to
choose would score, and the other would count as a miss for a question that named it — a wrong
number rather than a missing one. `weft index`'s own `AmbiguousExtractorError` takes the identical
posture one surface over.

**What to do:** lengthen the label until it names one document — `b/other.txt` rather than
`other.txt`. The message names both candidates, so the distinguishing prefix is visible in it.

### `UnknownRunIdError`

**What it looks like** — `weft eval compare`/`weft trace` given a run id nothing persisted,
reproduced against a real, empty `runs/` directory:

```text
$ weft trace does-not-exist
'does-not-exist' is not a persisted run — checked 'runs'. Persisted runs: (none).
$ echo $?
4
```

Fitness function 12's family: `valid_options` is every run id actually found under `runs/` —
every `*.json` file's own stem — the identical "list what does exist" rule
`weft_cli.pipeline_catalogue.UnknownPipelineNameError` already gives a pipeline name. **What to
do:** the message names every run id that does exist; run `weft eval run` first if none does.

---

## Scoring retrieval for a persisted run — `weft_cli.eval_scoring`

Task **4.9**, `.phase4-design.md` §7. `weft eval run <path> <pipeline> --questions <file>`
retrieves for every query a `--questions` file names, through the resolved pipeline's own
`Embedder`/`NodeStore` stages, and folds the gate-safe `RetrievalMetric` subset's scores into the
persisted `RunRecord`. The error below is refused before any partial, misleading `metrics`
mapping is ever persisted; a `--questions` file that cannot be read is `QuestionSetError`.

### `PipelineNotRetrievableError`

**What it looks like** — `--questions` given a pipeline document with no `Embedder`/`NodeStore`
stage to retrieve against:

```text
$ weft eval run corpus extract-only --questions questions.json
pipeline 'extract-only' has no stage registered under the NodeStore contract, so --questions has
nothing to retrieve against.
$ echo $?
1
```

Refused outright rather than silently persisting an empty `metrics` mapping indistinguishable
from "no `--questions` given at all" — a run record that looks like it scored nothing by choice
when it actually could not score anything is exactly the silent-fallback shape CLAUDE.md refuses.
**What to do:** name a pipeline that resolves an `Embedder` and a `NodeStore` stage, or drop
`--questions` if this pipeline genuinely never retrieves.

---

## Asking whether a metric can run here — `weft_eval.offline`

Task **4.7**, `docs/09-release.md` §4 V5. `weft eval metrics [--name <name>]` (`weft_cli.eval_commands.
EvalMetricsCommand`) answers "what runs in the gate" by reading whether each registered
`GenerationMetric`/`RetrievalMetric` declared `runs_in_gate = True` at registration — see
`weft_eval.contract`'s own module docstring for Q6, the mechanism. Both errors below can also
reach a caller who never typed `weft eval metrics` at all, once a future task's `weft eval run`
selects metrics by name — see each error's own class docstring.

### `UnknownMetricNameError`

**What it looks like** — a metric name neither `GenerationMetric` nor `RetrievalMetric`
registered, reproduced against a real, unmodified checkout:

```text
$ weft eval metrics --name does-not-exist
'does-not-exist' is not a registered metric. Registered metrics: 'accuracy', 'answer-completeness',
'answer-correctness', 'answer-relevance', 'bertscore', 'context-recall', 'context-relevance',
'embedding-similarity', 'exact-match', 'f1-score', 'faithfulness', 'key-terms-precision',
'mean-average-precision', 'mrr-at-k', 'ndcg', 'overlap-at-threshold', 'precision-at-k',
'recall-at-k',
'rouge-1', 'rouge-2', 'rouge-l', 'token-overlap', 'token-recall'.
$ echo $?
4
```

Fitness function 12's family: `valid_options` is every metric name actually registered, across
both contracts — never only one, which is why this is a distinct type from
`weft_kernel.registry.UnknownPluginError` rather than a reuse of it (`weft_eval.offline`'s own
module docstring). **What to do:** the message names every metric that does exist; check for a
typo, or that the pack registering the metric you expected is actually installed and active
(`weft plugins doctor`).

### `MetricNeedsCredentialsError`

**What it looks like** — a real, registered metric that declared `runs_in_gate = False`,
reproduced against a real, unmodified checkout with no `[llm.roles]` configured anywhere:

```text
$ weft eval metrics --name faithfulness
'faithfulness' cannot run in the deterministic, gate-safe subset: needs a real judge model behind
'[llm.roles]' — the deterministic 'scripted' provider resolves the service but cannot produce a
usable structured judgement, so this metric is excluded from the gate's offline subset regardless
of whether an operator configures a role for it. Configure '[llm.roles]' to map this metric's role
(default 'grade') to a real provider such as 'openai' to run it outside the gate.
$ echo $?
1
```

Not a name-resolution failure — the name was valid, and there is no alternative name to offer, so
this maps to `OPERATION_FAILED` (exit `1`), the identical footing `EmptyCorpusError`/
`IncomparableRunsError` already have, never exit `4`. `bertscore` answers the identical way for a
different reason: "needs the optional 'bert_score' package and a downloaded BERT checkpoint on
first use — install weft-eval's 'bertscore' extra to run this metric outside the gate." **What to
do:** the message already names what would permit it — configure a real provider for an LLM
judge, or install the named extra for `bertscore`. This is by design, not a bug: the whole point
of `runs_in_gate` is that these metrics never quietly score something meaningless in `poe
ci-checks` — they refuse loudly instead.

---

## Scoring a published baseline — `weft_eval.baseline`, `weft_eval.question_set`, `weft_eval.corpus_manifest`

Repair **R22.4a**, `docs/09-release.md` §4.3 V2–V4. What a published baseline measures, the
question set it is scored against and the corpus manifest it names are read by these three
modules, from the installed wheel, so a reproduction needs no checkout. Each refusal below was
produced by calling the module with the input described.

### `QuestionSetError`

**What it looks like** — a question file under the directory handed to `load_questions` that is
not valid TOML:

```text
QuestionSetError: round-2.toml: Expected ']]' at the end of an array declaration (at line 1, column 11)
```

`weft eval run --questions` raises the same class for its input, a JSON list included — *`questions.json
is not valid JSON: …`*, or one naming an `'id'` for some questions and not others. A question that
breaks its own invariant names its file and index the same way —
*`round-2.toml, question 0: … definitional but carries no supporting quote`*. **What to do:** fix the
named file. The question set is ground truth, so nothing is skipped: one bad question refuses the
whole set rather than scoring a smaller one under the same name.

### `QuestionSetSchemaError`

**What it looks like** — a question file whose `[question_set]` table names a schema newer than
this `weft-rag` reads, reproduced with a one-table file:

```text
QuestionSetSchemaError: round-3.toml: schema 3 is newer than the 2 this weft-rag reads — upgrade weft-rag to read it
```

A question file is a persisted format with its own version marker: no `[question_set]` table is
schema 1, `schema = 2` lets a file state which fields it cannot supply (`absent`, with an
`absent_reason`) and which partition axes its questions carry. A newer schema is refused rather
than read on a guess. **What to do:** upgrade `weft-rag` to a release that reads that schema, or
use the release that wrote the file.

### `ExperimentDocumentError`

**What it looks like** — `weft eval experiment` given a document that cannot be run as written,
here one asking for a single repetition:

```text
$ weft eval experiment one.toml --yes ; echo $?
one.toml: repeats: Input should be greater than or equal to 2
1
```

An experiment document states its arms, question set, corpus, repetitions, metrics and minimum
detectable effect before any run, and each is checked when it is read: fewer than two arms or two
repetitions, a zero or missing effect, no metric, two arms under one name, an unknown key and a
missing `schema` are all refused naming the file and the field. **What to do:** fix the named field.
Two repetitions is the least that gives a between-run spread to judge a difference against.

### `ExperimentSchemaError`

**What it looks like** — an experiment document whose `[experiment] schema` is not one this release
reads:

```text
$ weft eval experiment newer.toml --yes ; echo $?
newer.toml names schema 2, and this weft-rag reads schema 1 — upgrade weft-rag to read a document written for a different schema.
1
```

**What to do:** upgrade `weft-rag` to a release that reads that schema, or run the document with the
release that wrote it.

### `IncomparableArmsError`

**What it looks like** — an experiment whose arms would not measure the same thing, refused before
anything is indexed:

```text
$ weft eval experiment planted.toml --yes ; echo $?
arm 'planted' is not comparable to 'dense': corpus differs ('dense' d3b18b20c967… vs 'planted' 4d10128f9175…).
1
```

Every arm is compared with the first on three things: the digest of the documents its pipeline reads
from its corpus, the digest of its question set, and any model slot both arms name at two
different versions. An arm using a model slot the other lacks is not a difference — that is most
of what an experiment varies. **What to do:** point the arm at the same corpus and questions, or
run it as its own experiment; a difference in the corpus is a different measurement, not a
comparison.

### `IncompleteExperimentError`

**What it looks like** — `weft eval table` asked for an experiment whose records under `runs/` do
not hold every arm and repetition of one invocation:

```text
$ weft eval table experiment.toml ; echo $?
invocation 'inv-1' of experiment 'fixture' (5abd131efc38…) is missing arm 'better' repetition 2.
1
```

With no record of the document at all it says *"no records of experiment 'fixture' (5abd131efc38…)
were found."* A table is computed from one complete invocation or not at all, because a cell from a
partial run would read as a result. The digest is the document's bytes: records written before the
document was edited belong to a different experiment and are not counted. **What to do:** run the
experiment to completion with `weft eval experiment`, or point `--runs` at the directory holding its
records.

### `AmbiguousInvocationError`

**What it looks like** — two complete invocations of the same document under `runs/`:

```text
$ weft eval table experiment.toml ; echo $?
more than one complete invocation of experiment 'fixture' (5abd131efc38…) exists: 'inv-1', 'inv-2' — name one with --invocation.
1
```

**What to do:** pass `--invocation` with the one the table should describe.

### `UnscorableArmError`

**What it looks like** — an experiment arm whose query pipeline ends in a stage an arm cannot be
scored over, refused before any arm is indexed or any record written:

```text
$ weft eval experiment bad.toml --yes ; echo $?
arm 'embed-only' names query pipeline 'index-text', which ends in a NodeStore stage — an arm is scored over what a ContextPacker packed or a Generator answered from, so its last stage must be one of those.
1
```

An arm's query pipeline is resolved in the experiment's pre-flight, beside the corpus and question
set checks, so an unrunnable arm cannot leave the arms before it with records nobody can table. A
pipeline ending in a `ContextPacker` — `lexical-retrieve` — is scored over the passages it packed
and calls no model; one ending in a `Generator` over the passages its answer used. **What to do:**
name a query pipeline that ends in one of those two, or drop `query_pipeline` to score the ingest
pipeline's own vector search.

### `ForeignDocumentRetrievedError`

**What it looks like** — an experiment arm retrieving a passage from a document the store holds
and the arm's corpus does not:

```text
$ weft index foreign
$ weft eval experiment experiment.toml --yes ; echo $?
a retrieved passage names document '/tmp/exp/foreign/saffron.txt', which the store holds but the scored corpus does not (2 document(s)).
1
```

Scored, that passage would count as a miss against questions that never judged it, and the arm
would read as worse than it is. `weft eval run` still scores such a store; the experiment runner
refuses it. **What to do:** give the experiment a store holding only its corpus — a fresh database
in `[packs.store] dsn`, or a new `[packs.qdrant] collection`.

### `CorpusManifestError`

**What it looks like** — a manifest entry declaring a tier that does not exist:

```text
CorpusManifestError: document 'doc-a' in …/manifest.toml declares tier 'borrowed', which is not a tier. Valid tiers are: gate, fetch, operator.
```

The same class refuses an absent manifest, an entry missing `id`, `path`, `format`, `language`,
`sha256` or `tier`, and a `path` resolving outside the manifest's own directory, each naming the
entry. **What to do:** correct the entry the message names. `scripts/fetch_corpus.py` reads the same
file and refuses the same mistakes.

### `BaselineScoringError`

**What it looks like** — a mean asked of no values:

```text
BaselineScoringError: the mean of no values is not a number; the caller must exclude instead
```

The base of the scoring refusals. **What to do:** a caller that reaches this passed a question with
no judgement, or a repetition that scored nothing, to arithmetic that has no answer for it — exclude
it with a reason (`Unscoreable`, `Excluded`) rather than averaging a zero.

### `DepthTooShallowError`

**What it looks like** — a metric asked for at a `k` deeper than the retrieval that fed it:

```text
DepthTooShallowError: metrics were asked for at depth(s) [10] over a retrieval of 5. A metric's name must state the k it computed
```

V4's rule, *"the `k` in a metric's name equals the `k` it computed"*. **What to do:** retrieve at
least as deep as the deepest metric you report, or drop that depth.

### `IncomparableBaselinesError`

**What it looks like** — a later run whose chunk stage was configured differently from the
published baseline's, judged against it:

```text
IncomparableBaselinesError: these two baselines measure different things, so neither reproduces the other: stage 'chunk' config differs ({'size': 512, 'overlap': 50} vs {'size': 256, 'overlap': 50})
```

`09` §4.3 V3 refuses a baseline *"from a different corpus, pipeline or model version"*. Refused
here: any difference a pipeline document states (a stage's `contract`, `use`, `config`,
`fallback`, `provenance`, or the stage list itself) and any difference in the corpus, model
versions, retrieval depth or question set. Every difference is named, not the first. **Not
refused:** a stage's `distribution`, `contract_version` or `applies_to`. Those describe the
installation, so they are reported beside the verdict, and any effect they have on retrieval shows
up in the metric intervals. **What to do:** run the pipeline the published baseline names, over its
corpus and question set, at its retrieval depth.

---

## Taking a baseline — `weft_cli.eval_baseline`

Repair **R22.4c**. `weft eval baseline <manifest> <questions>` verifies, stages, indexes and scores
in one process. Each refusal below was produced by the installed binary, from a directory outside
this repository, over the tracked corpus manifest and question set.

### `BaselineRunError`

**What it looks like** — a tier the manifest does not declare:

```text
$ weft eval baseline corpus/manifest.toml eval/questions --tiers fetch,borrowed
'borrowed' is not a corpus tier. The manifest declares ['gate', 'fetch', 'operator'].
$ echo $?
1
```

The same class refuses a `--depths` piece that is not an integer, a selected document that is
missing or does not match its manifest digest (each named with its status), a pipeline that reads
none of the staged documents, and a run with no question it can score. All of these except the
last two are refused before anything is staged. **What to do:** the message names the input. For
missing documents, run `fetch_corpus.py fetch` first; the operator tier is placed by hand.

### `BaselineOutputExistsError`

**What it looks like** — a report path that is already taken:

```text
$ weft eval baseline corpus/manifest.toml eval/questions --out baselines/8854c33f71ea-2026-09-14.json
'baselines/8854c33f71ea-2026-09-14.json' already exists. 'weft eval baseline' refuses to overwrite a published run — remove it first, or point --out somewhere else.
```

An explicit `--out` is checked before anything runs. The default name,
`baselines/<corpus digest>-<date>.json`, is only known once the corpus is, so a second run on the
same day in the same directory is refused at the end. **What to do:** pass `--out`.

### `BaselineStoreNotIsolatedError`

**What it looks like** — a store that already held a document this run did not stage (here one
indexed first with `weft index foreign --pipeline baseline` into the same collection):

```text
$ weft eval baseline corpus/manifest.toml eval/questions --out polluted.json
a retrieved passage traces to '…/foreign/doc-z.md', which this run did not stage — the 'qdrant' store holds at least one document outside this run's own corpus, which changes every question's ranks. Point it at a collection holding nothing but this run's corpus (for Qdrant, '[packs.qdrant] collection').
```

No report is written. A passage from another corpus changes the ranks, and so every number, while
reading as ordinary retrieval, which is why this refuses rather than dropping the passage. **What
to do:** set `[packs.qdrant] collection` in `weft.toml` to a collection nothing else writes to.

### `BaselineNotReproducedError`

**What it looks like** — `weft eval compare` given a published baseline and a later report whose
`document-recall@10` falls outside the interval the published run's repetitions spanned (repair
**R22.4d**, produced by the installed binary):

```text
$ weft eval compare archive/baselines/8854c33f71ea-2026-09-21.json shifted.json
'shifted.json' does not reproduce 'archive/baselines/8854c33f71ea-2026-09-21.json': document-recall@10: 0.5 is outside [0.5416666666666666, 0.5416666666666666]
$ echo $?
1
```

Every metric that did not reproduce is named, with the later value and the published interval; a
metric the later run did not measure at all is named as not measured. No tolerance is chosen
anywhere: the interval is what the published repetitions produced. **What to do:** if the later
run used the same corpus, pipeline, model versions and depth (otherwise `IncomparableBaselinesError`
would have refused first), the difference is real. Look at what changed in the installation before
treating the published number as wrong.

### `NotABaselineReportError`

**What it looks like** — `weft eval compare` given a file that is not a baseline report:

```text
$ weft eval compare archive/baselines/8854c33f71ea-2026-09-21.json notes.json
'notes.json' is not a baseline report: 13 validation errors for BaselineReport
```

An argument that names a file on disk is read as a baseline report, whatever it is called; one that
names no file is read as a run id. **What to do:** pass the report `weft eval baseline` wrote, or a
file from the release archive's `baselines/`.

---

## Project configuration — `weft_engine.registry_bootstrap`

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

### `CommandRefusalError`

**What it looks like** — `weft ask`/`weft index` refusing before calling into the library at all,
because `[services] embed`/`[services] store` or `--extract` names a plugin from a distribution
`[packs] allow` refuses, reproduced against a real checkout with `weft-store` and `weft-openai`
left off the allow-list. **`--retrieve-only`, since task 3.11**: the default, routed `weft ask`
resolves `[services] store` inside `weft_engine.run_services.build_services`, which calls
`Registry.entry` directly rather than through `require_plugin` (that module's own docstring:
"this function does not repeat that translation") — a real, narrower gap this repair found and
named but did not fix, being a different call site than the one it was scoped to. `--retrieve-
only` is Phase 0's own contract, `weft_cli.ask.run_ask`, which still calls `require_plugin` for
both `Embedder` and `NodeStore` exactly as it always has:

```text
$ weft ask "what changed?" --retrieve-only
[services] store names 'pgvector', and no registered NodeStore has that name. These distributions
are refused by [packs] allow in weft.toml and were never imported, so what they would have
registered is unknown: weft-openai, weft-qdrant, weft-store. Add the one that provides 'pgvector'
to [packs] allow. Registered NodeStore names: none.
$ echo $?
3
```

**Repair, 2026-08-20 (open item O4, `.phase3-design.md` §4).** This message used to end `. no
'pgvector' is registered for NodeStore. It is unavailable because no distribution has registered
that name for this contract. Names registered for NodeStore: none.` — `weft_kernel.registry.
UnknownPluginError`'s own text, spliced on with a bare space, restating in different words the
same fact `wanted` already stated. `weft_engine.registry_bootstrap._unresolved` now composes its own
"Registered NodeStore names: ..." sentence from `exc.valid_options` instead of quoting `exc`'s
text — every sentence in a composed refusal is written by the module raising it, never a
concatenation of two independently-capitalised messages.

Task **3.2** introduced this class as the typed carrier for a refusal every built-in `Command`
computes before running — `weft_engine.registry_bootstrap.require_active`/`require_plugin`'s own
`(exit code, message)` answer, raised rather than printed-and-returned directly because a
`Command.run` cannot print (`docs/03-cli.md` → *Two modes, one implementation*). The message and
exit code are unchanged from before that task: `3` when a distribution that would have provided
the name is refused by `[packs] allow`, `4` when the name is simply unregistered or the pack that
would provide it only partly loaded. **What to do:** the message names the setting to fix —
`[packs] allow`, `[services] embed`/`[services] store`, or `--extract` — and, for exit `3`,
which distribution to add to the allow-list.

**Task 3.3** gives this class a second raise site: an `overwrite`/`destroy`-class command with no
TTY to confirm in, or one an interactive caller declined — `weft_cli.confirm.gate`, called from
`weft_cli.cli.run_command` immediately before any registered `Command` runs. **No first-party
command is `overwrite`/`destroy`-class, and — as of the 2026-08-20 repair recorded in
`docs/internal/build-ledger.md`'s dated paragraph for tasks 3.3/3.6/3.7 — none is expected to become one
under this task surface**: `init`, `pipeline derive` and `config set` were briefly `overwrite`,
found to refuse a first, non-interactive `weft init` in exactly the environment (CI) it most needs
to work in, and were reclassified `write` with an unconditional refusal-to-clobber in their place
(`TargetAlreadyExistsError`/`PipelineAlreadyExistsError`, above) rather than a prompt. `weft index`
was never a candidate either — it upserts by content-addressed id. So this path is reproduced
directly against `weft_cli.confirm`, the same way the `MissingRequiredDeclarationError` entry above
is reproduced against a bare `Registry` rather than a full `weft` run — a hand-registered
`destroy`-class command, no TTY:

```text
>>> confirm.gate(command, "graph destroy", args, yes=False, policy=PermissionPolicy())
weft_cli.commands.CommandRefusalError: 'graph destroy' is a destroy-class command, called with
{'collection': 'reports'}. It refuses to run with no terminal to confirm in, and never proceeds
silently. Pass --yes to permit it for this invocation.
```

with exit code `3`. Declining an interactive prompt (a TTY attached, answered anything but `y`/
`yes`) raises the same class with `'<command>' was not confirmed; nothing was done.`, also `3`.
**What to do:** pass `--yes` after the command name (`weft <command> ... --yes`) to permit it for
one invocation, or set `[permissions] destroy = "allow"` / `[permissions] overwrite = "allow"` in
`weft.toml` to stop asking for that class entirely — `docs/03-cli.md` → *Permissions* and
*Project context*. These classes protect you from the tool running unattended, not from a
dishonest pack (`02` §2 → *The trust model*): a pack that lies about its own `permission_class`
is not caught here.

### `UnresolvedPluginNameError`

**What it looks like** — repair, 2026-08-20 (finding 2, `docs/internal/build-ledger.md`'s dated paragraph
for tasks 3.2/3.3/3.7): `CommandRefusalError`'s own family member for a genuine name-resolution
failure — `[services] embed`/`[services] store` or `--extract` names a plugin no *active* pack
provides, reproduced against a real checkout with `[services] embed` naming a plugin nothing
provides and every pack otherwise active. `--retrieve-only` again — see the `CommandRefusalError`
entry above for why the default, routed `weft ask` does not reach this path today:

```text
$ printf '[services]\nembed = "no-such-embedder"\n' > weft.toml
$ weft ask "what changed?" --retrieve-only
[services] embed names 'no-such-embedder', and no registered Embedder has that name. These
distributions contributed nothing, or only part of what they publish, and one of them may be
the one that provides it: weft-rag (partial). Registered Embedder names: 'hash',
'openai-embeddings'.
$ echo $?
4
```

**The middle clause is about the environment, not about the name you typed.** `weft-rag` reads
`partial` here because `bertscore` needs an optional package this checkout does not have — task
6.29's designed behaviour, reported at discovery rather than one moment too late — so the message
honestly cannot rule that distribution out as the source of the missing name. Install the
`bertscore` extra and the clause disappears; `weft plugins doctor` is what says which distribution
is partial and why. It is named here because a reader meeting it for the first time will read it as
part of the failure and it is not.

Before this repair, `weft_engine.registry_bootstrap.require_plugin` caught the kernel's own
`weft_kernel.registry.UnknownPluginError` — which already carries `valid_options`, every name
actually registered for the contract asked — and threw the field away into `plain=str(exc)`
before `IndexCommand`/`AskCommand` ever raised anything: both always raised the plain
`CommandRefusalError` above, message-only, whatever the underlying cause. Confirmed
programmatically, not only by the message text already naming the names: catching this
exception directly off a real `AskCommand.run()` call with the `weft.toml` above gives
`exc.valid_options == ("hash", "openai-compatible-embeddings", "openai-embeddings")`, a typed field a caller can read, never
only text inside the message. History: before Phase 3 this path was a plain return value with no
typed field to lose at all — task 3.2's own `Command`/`Outcome` unification is what turned it into an
exception and dropped the guarantee in the same motion.

**A second repair, 2026-08-20 (open item O4, `.phase3-design.md` §4).** The message itself used
to end `. no 'no-such-embedder' is registered for Embedder. It is unavailable because no
distribution has registered that name for this contract. Names registered for Embedder:
'hash', 'openai-compatible-embeddings', 'openai-embeddings'.` — `weft_kernel.registry.UnknownPluginError`'s own text, spliced onto
this module's
sentence with a bare space: a sentence beginning lowercase right after a full stop, and "nothing
is registered under that name" stated twice in different words. `require_plugin`'s `_unresolved`
now composes its own sentence from `exc.valid_options` (the same tuple this section's own
`valid_options` field already carries) instead of quoting `exc`'s text — see
`weft_engine.registry_bootstrap._unresolved`'s own docstring for the argument in full, and the
`CommandRefusalError` entry above for the same fix's effect on a `silent`-branch message, where a
raw multi-line Pydantic dump used to be spliced mid-sentence too.

`isinstance(exc, CommandRefusalError)` still holds — this **is** a `CommandRefusalError`
subclass, so `weft_cli.render.render_refusal` needs no change and `.exit_code` still reads off
it directly — but it additionally carries `valid_options`, keyword-only with no default, so a
raise site that forgets to collect the registered names cannot construct it at all. **Only** the
branch that genuinely has real names to offer raises this subclass: a pack refused by `[packs]
allow` (exit `3`, `POLICY_REFUSED`) still raises the plain `CommandRefusalError` above with no
`valid_options` — a refused pack is never imported, so nothing here can honestly claim to know
what it would have registered, and inventing a list would be worse than omitting one.
**What to do:** the message already names every registered alternative — pick one, or fix a
typo in `[services] embed`/`[services] store`/`--extract`; `weft plugins doctor` shows what is
actually installed if none of the names look right.

### `UnsupportedArgumentTypeError`

**What it looks like** — a pack's own `Command.args_model` declares a field type
`weft_cli.argparse_gen` has no generic mapping for, reproduced directly against the function that
raises it:

```text
UnsupportedArgumentTypeError: field 'paths' has annotation tuple[str, ...], which is not a class —
no generated argument grammar knows how to parse that from the command line. Supported: str, int,
a StrEnum, or any of those wrapped in `| None`.
```

This surfaces the moment `weft` builds its argument grammar — which happens for every command
except `--version` (`docs/02-extension-model.md` §2) — so an installed pack with a malformed
`args_model` breaks `weft --help` and every other command too, not only its own. It is always a
**pack author's** bug, never a user's: exits `4`, the same "fix the pipeline" family a malformed
`weft.toml` exits with, since neither is something a user's own command line caused. **What to
do, as a user:** report it to the pack's author, or remove the pack from `[packs] allow` until
it is fixed. **As a pack author:** narrow the field's annotation to `str`, `int`, a `StrEnum`, or
one of those wrapped in `| None` — the three shapes the generated grammar understands.

---

## Who a fan-out reaches — `weft_cli.participation`

Task **6.18**, `docs/02-extension-model.md` §1 → *Extended by G13*. `weft delete` and `weft
reconcile` fan out across the configured `[services] store` **plus** every `NodeStore` named by
a pipeline in the project's catalogue or by a persisted run record, so a graph store the `kg`
pipeline writes to loses what the corpus lost. Reading the run history is what makes a store
that no document names any more still reachable — and it is why a run record that will not parse
is a refusal rather than a shrug.

### `UnreadableRunRecordError`

**What it looks like** — a file under `runs/` that is not a well-formed run record, reproduced
against a real project with `runs/broken.json` holding `{not json at all`:

```text
$ weft delete doc-1 --yes
run record at runs/broken.json could not be read: 1 validation error for RunRecord
  Invalid JSON: key must be a string at line 1 column 2 [type=json_invalid, input_value='{not json at all', input_type=str]
    For further information visit https://errors.pydantic.dev/2.13/v/json_invalid. A store this project has run data through may be named only here, so a run record that will not parse is refused rather than silently skipped.
$ echo $?
1
```

Exit `1`, "something failed", rather than the `4` a name you can fix earns: nothing about your
command line is wrong. **Why it is not skipped:** the run history is read precisely to find a
store the catalogue no longer names, so the record that will not parse may be the only record
naming it — skipping it would let that store's contents outlive their source with nothing said,
which is the failure the fan-out exists to prevent (`docs/internal/lessons.md` L5.9). **What to do:** the
message names the file. Repair it if you want the run kept, or delete it; a `runs/` directory
that does not exist at all is not an error, and neither is an empty one.

---

## Contract reference generation — `weft_engine.contract_reference`

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

## Command table generation — `weft_cli.command_table`

### `CommandNotDescribableError`

**What it looks like** — `scripts/generate_command_table.py` found a registered `Command` it
cannot describe: no `help` attribute —

```text
CommandNotDescribableError: 'graph build' carries no `help` attribute. Every registered Command
must declare one — weft_command.contract.Command.required_declarations names it mandatory — and
the command-table generator refuses to invent a placeholder for one that does not exist.
```

— or no `permission_class` attribute, the identical message with `permission_class` in place of
`help`. In practice neither can happen from a command that registered at all:
`weft_command.contract.Command.required_declarations` — `("permission_class", "help")` — already
refuses the registration itself, loudly, naming the missing declaration, before this generator
ever sees the plugin's name. This error exists as a second, defensive check anyway, on
`ContractNotDescribableError`'s own footing directly above: a generator that read either
attribute with a bare `getattr` would crash with an unattributed `AttributeError` if that
registration check were ever relaxed, instead of failing loudly and naming which command and
which field.

This only fires while regenerating `manual/user-manual.md`'s command table (`uv run python
scripts/generate_command_table.py`), never from `weft index`/`weft ask`. **What to do, as a
command author:** every registered `Command` needs `permission_class: ClassVar[PermissionClass]`
and `help: ClassVar[str]` — see [`manual/user-manual.md`](user-manual.md) §6 for a command that
already gets this right.

---

## Reranking through a cross-encoder — `weft_cross_encoder`

`cross-encoder-rerank` scores each passage against the question through a
[Text Embeddings Inference](https://github.com/huggingface/text-embeddings-inference) server. It
never returns the passages unranked when it cannot score them: a fault of the server stops the
run, naming the address, and only a passage the server refuses to read fails that one question.

### `CrossEncoderUnreachableError`

**What it looks like** — nothing answered at the configured address:

```text
CrossEncoderUnreachableError: 'cross-encoder-rerank' could not reach http://localhost:8080/info
(ConnectError). Start the TEI server, or point [packs.cross-encoder] url at the one that is running.
```

**What to do:** start the server, or set `[packs.cross-encoder] url` in `weft.toml` to where it
runs. `http://localhost:8080` is the default. A server that is still loading its model refuses
connections until its warm-up ends; wait for its log to print `Ready`.

### `CrossEncoderServerError`

**What it looks like** — the server answered, with an error or with something that is not one
score per passage:

```text
CrossEncoderServerError: 'cross-encoder-rerank': http://localhost:8080/rerank answered 429:
Model is overloaded
```

**What to do:** read the status. `413` means the request carried more passages than the server
accepts, so start it with a larger `--max-client-batch-size` (the reranker already splits a request
at the size `/info` reports). `424` means the served model is not a single-class sequence
classifier. `429` means it is overloaded, so lower the concurrency or raise
`--max-concurrent-requests`. A `5xx` is the server's own failure; its log says why. A response
holding a different number of scores from the passages sent is a server defect, and it is refused
rather than guessed at.

### `CrossEncoderModelMismatchError`

**What it looks like** — the server serves a different model from the one the stage names, or a
model that is not a reranker:

```text
CrossEncoderModelMismatchError: 'cross-encoder-rerank' is configured for 'BAAI/bge-reranker-v2-m3',
but http://localhost:8080 serves 'cross-encoder/ms-marco-MiniLM-L6-v2' (reranker).
```

**What to do:** point `[packs.cross-encoder] url` at a server serving the named model, or name the
served one in the stage's `with: {model: …}`. The check reads `/info` before any passage is scored,
because a score from the wrong model is a number you cannot tell apart from a right one.

### `CrossEncoderModelUnsetError`

**What it looks like** — a pipeline uses `cross-encoder-rerank` with no `model:`:

```text
CrossEncoderModelUnsetError: 'cross-encoder-rerank' needs `model:` in its `with:` block, the
reranker the TEI server serves (for example BAAI/bge-reranker-v2-m3). No model is assumed.
```

**What to do:** add `with: {model: <the served model id>}` to the stage. The shipped rungs
`cross-encoder-retrieve` and `cross-encoder-rerank-then-generate` already name one.

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
store (weft-store) 2.0.0: refused (0 contributed)
  never imported — 'weft-store' is not listed in [packs] allow. Add it there to permit it.
  disclosure: not disclosed
```

**What to do:** add the distribution to `[packs] allow` in `weft.toml` if you meant to permit it —
that pin is exhaustive, so anything left off is refused, and refusal happens before the pack is ever
imported.

### `failed`

```text
$ weft plugins doctor
store (weft-store) 2.0.0: failed (0 contributed)
  reason: 'store' settings failed validation: 1 validation error for PgVectorSettings
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

### `MalformedLLMSectionError`

**What it looks like** — one mistyped key inside `[llm.roles]`, reproduced from a directory with
nothing else in it:

```text
$ printf '[llm.roles]\ngenerate = { provider = "scripted", nonsense = 1 }\n' > weft.toml
$ weft pipeline list
weft.toml's [llm] section is not valid: nonsense: Extra inputs are not permitted. Every key under
[llm.roles], [llm.retry] and [llm.loop_guard] is checked, and one nothing reads is refused rather
than ignored.
$ echo $?
4
```

Exit `4`, not `1`: no command was chosen, because the surface a command is chosen *from* could not
be built. **What to do:** remove the key, or check it against
[`manual/operations-guide.md`](operations-guide.md)'s `[llm]` reference — `provider`, `model` and
`params` are what a role accepts.

**Until 2026-09-06 this printed a Python traceback.** The keys of `[llm]` itself were refused by
name; the keys of the tables *under* it were validated by pydantic, whose `ValidationError` is not
a `WeftError` and so walked straight past `weft_cli.cli.main`'s handler — a handler whose own
comment said it covered a malformed `weft.toml`. Found by running the binary at ledger task 7.4.
`[services]` and `[permissions]` were measured at the same time and already refused correctly.

### `AnswerCarriesNoUsedPassagesError`

**What it looks like** — `weft eval run <path> <pipeline> --query-pipeline <rung>` where the rung
produced something that is not an `Answer`:

```text
the query pipeline's result carries no `used` passages, so there is nothing to score retrieval
against.
```

**What it means.** A query rung is judged on what it actually put in front of the generator —
`Answer.used`, *"exactly the passages that entered the prompt"*. A pipeline whose last stage is not
a `Generator` produces no `Answer`, so there is nothing to score. **What to do:** name a rung that
ends in a generator (`weft pipeline show <name>` prints the resolved stages), or drop
`--query-pipeline` and score the ingest pipeline's own plain retrieval, which is what happens by
default.

**Why this is a refusal rather than a zero.** A rung that scored `0.0` because nothing was measured
is indistinguishable from one that retrieved nothing useful, and `09` §4 exists to keep those two
apart.

## The agent's ceiling — `weft_agent`

`weft-agent` drives Weft through the same command surface a person types at, and it is capped at
what a caller with no terminal may do. Grilling session G12 settled that cap: **nothing other than
a TTY counts as consent**, so an agent — which is never a TTY — may reach `read`, `write` and
`network` commands and may not reach `overwrite` or `destroy` ones. See
[`docs/03-cli.md`](../docs/03-cli.md) → *Permissions* for the rule and the argument.

### `UndecidedActionError`

**What it looks like** — you will not see this. It names a state `NextAction`'s own validator makes
impossible: an action carrying neither a tool call nor a final answer.

**Why it exists at all.** The loop needs one of the two to be set, and the check that proves it is
the model's own validator. The line that reads the call would otherwise be an `assert`, which is
**stripped under `-O`** — so in an optimised build the guarantee would vanish and the next line
would dereference `None`, in exactly the build where nobody is watching. A named refusal survives
`-O`; an assertion does not.

**What to do** if you ever meet it: it is a defect in `weft-agent`, not in your configuration.

### `ConsentRefusedError`

**What it looks like** — not as a crash, and that is deliberate. The agent's own tools catch it and
hand it back to the model as an observation, so it appears inside a run's transcript rather than on
stderr:

```text
'delete' is a destroy-class command. This caller has no terminal to confirm in, and nothing other
than a terminal counts as consent, so it cannot be run from here.
```

**What it means.** Something asked to run an `overwrite`- or `destroy`-class command through a path
that cannot obtain a person's consent. In normal use you will not see it at all: the agent's tool
catalogue is derived from `permission_class` and never offers such a command in the first place, so
meeting this error means the tool was constructed directly — by a pack, a script, or a test.

**Two mechanisms, and they guard different things.** The catalogue decides what the model is
*offered*; consent decides what actually *executes*. They fail independently on purpose, so a bug
in either one alone does not lift the ceiling.

**What to do.** Run the operation yourself. `weft delete <source-id>` and `weft reconcile` prompt on
a terminal, state what will be affected before they touch anything, and take `--yes` when you have
read that and mean it. An agent proposing one of these is telling you what it would do; deciding is
yours, and no flag it can pass changes that.

**What not to do:** do not give an automated caller `--yes`. `docs/03-cli.md` → *Permissions* is
explicit that `destroy` trains people to pass `--yes` reflexively, which disarms the whole table —
and an agent passing it on every call is that sentence with the human removed.

## Where to go next

- **Never run `weft` before?** [`manual/quickstart.md`](quickstart.md) is the five-minute path from
  nothing to a real, retrieved answer.
- **Bringing the container up, `weft.toml`, exit codes in full** —
  [`manual/operations-guide.md`](operations-guide.md).
- **Writing a pack of your own?** [`manual/pack-author-guide.md`](pack-author-guide.md).

### A document is reported "failed earlier, skipped"

**What it looks like:**

```text
$ weft index corpus
2 documents: 0 indexed, 1 unchanged.
1 failed earlier, skipped — weft index --retry-failed includes it
```

**Why** — an earlier run recorded that document as failed, and `weft index` does not retry a
failure unasked: on a pipeline with a model stage, every retry is paid for.

**What to do:** run `weft sources list --status failed` to see which stage failed and why. Fix the
file and run `weft index` again, or run `weft index --retry-failed` if the cause was outside the
file. A refused document is recorded on its own, since the others in its batch are run again
without it. A stage that raised records every document of its batch. `weft delete <source-id>`
abandons it.

### `CorpusHasFailedSourcesError`

**What it looks like** — `weft eval run` or `weft eval experiment` over a corpus where an earlier
`weft index` recorded a document as failed:

```text
1 source(s) under 'corpus' were recorded failed by an earlier index and were skipped, so this run
would score a smaller corpus than its record names (first: file:///…/bad.txt). Run `weft index
--retry-failed` over it first, or remove them with `weft delete`.
```

**Why** — a failed document is skipped rather than retried unasked. An evaluation over the rest
would score a smaller corpus while its record names the whole one, so two runs could compare as
the same corpus when one of them never saw that document.

**What to do:** fix the document and run `weft index --retry-failed`, or remove it with `weft
delete <source-id>`; `weft sources list --status failed` names each one.

### `UnknownSourceFailureError`

**What it looks like** — any command that reads a store's source records, against a store a
**newer** `weft-rag` has written a failure into:

```text
a source record's failure carries field(s) 'retry_after' this weft-rag does not know: a newer
weft-rag wrote it. Install the release that wrote it, or re-index with this one.
```

**Why** — the record of why a document failed has a fixed set of fields. A newer release can add
one, and reading the record while ignoring it would be a guess about what that release meant.

**What to do:** run the command with the release that wrote the store, or re-index the corpus
with this one; a re-index rewrites each failed document's record in a form this release knows.

### `UnknownSourceLayerError`

**What it looks like** — any command that reads a store's source records, against a store a
**newer** `weft-rag` has recorded a layer into:

```text
a source record's layer carries field(s) 'generation' this weft-rag does not know: a newer
weft-rag wrote it. Install the release that wrote it, or re-index with this one.
```

**Why** — each layer built over a document, such as its generated questions, is recorded with a
fixed set of fields and one of three statuses. A newer release can add a field or a status, and
reading the record while ignoring it would be a guess about whether that layer is usable.

**What to do:** run the command with the release that wrote the store, or re-index the corpus
with this one.

### `UnknownSourceStatusError`

**What it looks like** — any command that reads a store's source records, against a store a
**newer** `weft-rag` has written to:

```text
$ weft index corpus
a source record has status 'quarantined', which this weft-rag does not know: a newer weft-rag
wrote it. Install the release that wrote it, or re-index with this one.
$ echo $?
1
```

**Why** — every store keeps one record per indexed document, and its status is a word from a
closed list. A newer release can add a word this one has never seen. Reading it as one of the words
this release does know would be a guess about a document another release was tracking.

**What to do:** run the command with the `weft-rag` release that wrote the store. Or, if you mean to
move this store back to the installed release, re-index its corpus with `--reprocess`: a re-index
rewrites every record in a status this release knows.

### `GraphSchemaVersionRefusedError`

**What it looks like** — two different sentences, because there are two different mistakes behind
them. The first, against a database whose `kg_*` tables were written before ledger task `11.8`:

```text
$ weft index corpus --pipeline index-with-facts
weft_kg found an existing kg_nodes table with no kg_schema row — the layout these tables had
before ledger task 11.8, where kg_entities and kg_relations keyed on entity ids directly rather
than on an alias. Those rows are an operator's own data, and this pack refuses to guess at their
shape rather than silently reading or rewriting them: drop kg_nodes, kg_sources, kg_entities,
kg_entity_nodes and kg_relations (they hold only state this pack can rebuild by re-indexing) and
let it recreate them at '3.0.0', or migrate them to that layout by hand before running weft again.
$ echo $?
1
```

The second, against a database another `weft-rag` wrote at a different layout — `2.0.0` is every graph indexed before `R43.24`, which made each relation row name the node that stated it:

```text
weft_kg's kg_schema row for surface 'tables' is at version '2.0.0', but this installed pack knows
'3.0.0'. Refusing to read kg_* tables written by a different schema version rather than guessing
at their shape: install the version of weft-rag that wrote '2.0.0', or migrate the tables to
'3.0.0' and update the kg_schema row yourself.
```

**What to do.** Either do what the message says, or — if the graph is one you can rebuild — drop
the pack's five tables and re-index. Nothing in `kg_*` is a source of truth: every row in them is
derived from documents you still have, which is why dropping and re-indexing is offered first
rather than as a last resort.

```sql
DROP TABLE IF EXISTS kg_relations, kg_entity_nodes, kg_aliases, kg_entities,
                     kg_sources, kg_nodes, kg_schema CASCADE;
```

Your vector store is untouched by that: `weft_store`'s tables are `weft_nodes` and `weft_sources`,
and the graph pack owns only the `kg_` prefix even when both point at one container.

**Why it refuses instead of migrating.** `S5` — a persisted schema carries its version in the
stored bytes, because at the read site the pack that wrote them may not be the one installed. The
base rule this follows is `weft_kernel.payload.ExtModel.upgrade`'s, one surface over: refuse by
default, and let a pack that can genuinely reconcile an older shape override it. Guessing is the
one option not on the table, because a wrong guess does not crash — it reads a user's own rows
under the wrong column meanings and produces a plausible graph over the wrong entities.

**Why the missing-row case is a separate sentence.** A `kg_nodes` table with no `kg_schema` row is
not an unknown version, it is the layout that predates versioning, and an operator hitting it has
a concrete list of five tables to deal with rather than a version number to hunt for. The check
runs **before** anything is created, because every `CREATE TABLE IF NOT EXISTS` below it would
otherwise adopt those pre-`11.8` rows into the new layout's columns without a word.

### `UnhandledSameEntityVerdictError`

**What it looks like.** You will almost certainly never see this, and that is the point of writing
it down. `weft reconcile --mode full` puts each ambiguous name pair to a model and reads back a
three-member verdict — `yes`, `no`, `unsure`. If a later version of the graph pack adds a fourth
member and forgets to teach the pass what it means, the pass refuses rather than guessing:

```text
$ weft reconcile --mode full
weft_kg's adjudication pass received a SameEntity verdict of 'probably', which its match/case has
not been taught to map to a Verdict. Known members: ['yes', 'no', 'unsure'].
$ echo $?
1
```

**What to do.** Nothing an operator can configure — this is a defect in the installed `weft-rag`,
not in your project, and the remedy is to install a version whose adjudication pass knows every
member of its own enum. In the meantime `weft reconcile --mode repair` converges everything except
the model-driven merges, because the expensive pass is the only thing that reads a verdict at all.

**Why it refuses instead of treating the unknown answer as "different".** The whole argument for a
three-valued vote is that guessing is worse than abstaining: a wrong merge is irreversible and a
wrong refusal leaves a graph quietly split. Falling through to a default `False` would be exactly
the guess the design exists to forbid, made silently, on every pair — and the graph it produced
would look entirely reasonable. This is `weft_store.contract.UnhandledFilterOpError`'s rule one
contract over: `docs/09-release.md` §2.3's *"a version bump does not fix silence, so silence is a
separate defect."* Adding a member to a closed vocabulary is additive everywhere it is *declared*
and wrong at every site that dispatches on it, so every such site raises rather than defaulting.

### `MalformedSchemaFileError`

**What it looks like** — `weft graph activate` was given a file it cannot read as a schema:

```text
$ weft graph activate ./broken.toml
broken.toml does not hold a valid curated graph schema: 1 validation error for GraphSchema
relations
  Input should be a valid tuple [type=tuple_type, input_value='all of them', input_type=str]
$ echo $?
1
```

A curated schema is **hand-edited by design** — that is the point of it being a file a pull
request can show — so a malformed one is the ordinary case rather than the exotic one. The message
names the path, because a project may hold several and the operator needs to know which.

**What to do.** `weft graph propose` prints a valid schema in exactly the shape this reads back,
so the shortest route out is to propose, paste, and re-edit. A schema is a `name` and one or more
`[[relations]]` tables, each with `source_type`, `predicate` and `target_type`:

```toml
name = "papers"

[[relations]]
source_type = "person"
predicate = "wrote"
target_type = "method"
```

**Nothing was written.** `activate` validates before it touches anything — not `weft.toml`, not
the corpus — because a corpus recording that it is under a schema no file can produce is the state
nothing could diagnose. Fix the file and run the same command again.

### `EmptyCorpusError`

**What it looks like** — `weft graph propose` was asked to propose from a corpus that holds no
facts:

**Two causes, two messages, and the second is the one a real corpus meets first.** Reproduced
against a real checkout and a real corpus. An empty graph:

```text
$ weft graph propose
weft_kg has no facts to propose a schema from: nothing in this corpus was extracted at or above
min_count=2. Index a corpus through a rung that names the llm-facts stage — `weft index <path>
--pipeline index-with-facts` is the shipped one — and run this again. A corpus built with
`index-with-cooccurrence` reaches this too: a schema constrains (source_type, predicate,
target_type), and a co-occurrence edge has none of the three.
$ echo $?
1
```

And a corpus that **did** produce facts, none of which recurred:

```text
$ weft graph propose
weft_kg found 11 distinct arrangement(s) in this corpus and none of them was seen at least 2
time(s), so there is nothing to propose at that threshold. Lower it — `weft graph propose
--min-count 1` proposes from everything the corpus wrote — or index more of the corpus so the
arrangements worth keeping recur.
$ echo $?
1
```

**What to do** — whichever the message says, and they are genuinely different problems. The first
needs a corpus; `cooccurrence-graph` (the rung `index-with-cooccurrence` names) writes entities and
edges but **not** typed facts, so a corpus built that way reaches it too. The second needs a lower
threshold: a small corpus states most arrangements once, and `--min-count 2` hides all of them.
**That second message exists because the first one used to serve both cases**, telling an operator
who had just indexed to go and index — found by running the binary at ledger `11.11`, never by a
test.

The alternative — printing an empty schema — is what this refuses to do in either case. An operator
who activated one would have a schema that admits nothing, and every fact the next index run
extracted would be dropped as off-schema, correctly and catastrophically.

### `GraphDsnNotConfiguredError`

**What it looks like** — reproduced against a real checkout, with `WEFT_DATABASE_URL` exported and
no `[packs.graph]` table in `weft.toml`:

```text
$ weft index corpus --pipeline index-with-graph
weft_kg has no database to talk to: [packs.graph] dsn is unset. Add `[packs.graph]
dsn = "${env:WEFT_DATABASE_URL}"` (or a literal DSN) to weft.toml. Exporting WEFT_DATABASE_URL
alone is not enough: this pack is offered no ambient setting, so the one line above is what points
it at the container [packs.store] already uses.
$ echo $?
1
```

**What to do.** Add the two lines the message prints:

```toml
[packs.graph]
dsn = "${env:WEFT_DATABASE_URL}"
```

**Why exporting the variable is not enough, when it is enough for the node store.**
`weft_engine.registry_bootstrap.pack_settings_from_environment` offers `${env:WEFT_DATABASE_URL}` to
the `store` pack and to nothing else. Extending that offer to the graph pack was written and then
reverted at ledger task `11.5`: it would mean `weft-cli` naming a specific capability pack in a
hard-coded literal, which is the anticipation the graph pack exists to prove unnecessary — the
whole point of that phase is a pack built against nothing but the released API, costing zero lines
anywhere else. So the convenience is one line in your own file rather than a name in somebody
else's code.

**Why the pack still reports `active` with nothing configured.** `[packs.graph] dsn` defaults to
empty on purpose. `weft-store`'s is mandatory, so that pack reports `failed` where none is set —
correct, because every project needs a node store. A project that never names the graph store
should not have to read past a failure for a pack it is not using, so this one registers cleanly
and refuses at the first call that genuinely needs a connection. `weft plugins doctor` will show
`graph (weft-rag): active` on a machine where this error is one command away, and both are true.

### `NoRelationsToBridgeError`

**What it looks like** — `weft graph bridges` was asked for two-hop paths in a corpus whose graph
holds no relation at all. Reproduced from outside the repository, against installed wheels and a
database of its own:

```text
$ weft graph bridges
weft_kg has no relations to bridge: this corpus holds no kg_relations row at all. Index a corpus
through a rung that names the llm-facts stage — `weft index <path> --pipeline index-with-facts` is
the shipped one — and run this again. A corpus built with `index-with-cooccurrence` also produces
relations, on a machine with no model configured.
$ echo $?
1
```

**What to do.** Index through a rung that builds a graph. `index-with-facts` asks a model for the
relations each chunk states; `index-with-cooccurrence` needs no model and no credential, and is
the one to reach for on a machine that has nothing but Postgres.

**The other empty answer is not this error, and the difference is the whole point.** A corpus that
*does* hold relations, none of which forms a bridge, is not a failure — it is the finding, and
`bridges` prints it and exits `0`:

```text
$ weft graph bridges
0 bridge(s) found among 1 relation(s)
this corpus's relations are all answerable from a single chunk, so it holds no question on which a
graph must beat a vector baseline. A larger corpus, or a rung that extracts more facts, is what
produces one.
$ echo $?
0
```

That is `weft_kg.schema.propose_schema`'s own split between *nothing was extracted* and *nothing
survived the bar*, one command over: telling an operator who has just indexed to go and index is
advice for a problem they do not have.

### `CeilingDisagreesError`

**What it looks like.** Nothing, on any input — and that is what the entry has to say rather than
show. **No transcript is printed here because none could be produced**: this error fires only when
two independent queries over the same Postgres rows contradict each other, which no corpus, flag
or configuration can arrange from outside. Every attempt to reproduce it through the binary at
ledger `11.13` returned agreement, correctly. What it would print is the message
`weft_kg.bridges._ceiling_disagreement_message` builds, naming the two endpoint entities, at exit
`1`.

**Why an error exists for a thing that cannot be made to happen.** `weft graph bridges` prints a
*vector ceiling* — how many chunks in this corpus hold both endpoints of a question, which is `0`
by the definition of a bridge. Reading that number off the same `NOT EXISTS` clause that selected
the bridge would be a comparison whose two sides come from one source, and it could never disagree
with itself (`docs/internal/lessons.md` `L5.6`). So the ceiling is measured a second time, by
`GraphStore.chunks_by_entity`, a different query with a different filter — and this error is what
happens when the two answers differ. It is the seam that makes the printed number a measurement
rather than a restatement.

**What to do if you ever see it.** Nothing in your corpus caused it; report it. The two queries it
names are `weft_kg.store.GraphStore.two_hop_bridges` and
`weft_kg.store.GraphStore.chunks_by_entity`, and one of them is wrong about a database both can
read. Neither number is printed, deliberately — printing either would be printing a measurement
nothing checked.

### `UnsupportedIndexKindError`

**What it looks like** — `index` names a vector index kind the configured backend does not serve.
**One class serves both backends**, so the message names which block to edit:

```text
UnsupportedIndexKindError: [packs.store] index 'diskann' is not served by pgvector. It serves:
exact, hnsw.

UnsupportedIndexKindError: [packs.qdrant] index 'diskann' is not served by Qdrant. It serves:
exact, hnsw.
```

**Why the kinds differ per backend.** `VectorIndexKind` is one closed vocabulary across the store
family — `exact`, `hnsw`, `diskann` — but no backend serves all of it, and the vocabulary being
shared is what lets the refusal *name* the gap instead of a driver error doing it later and worse.
The refusal class is shared for the same reason the vocabulary is: what each backend serves is its
own fact, carried as `valid_options`, but the *shape* of the refusal is one thing rather than two
that could drift apart.

- **Qdrant** uses HNSW as its only dense vector index, so `diskann` is refused there always.
- **pgvector** serves `diskann` only where the `vectorscale` extension is installed, which the
  default development image does not carry — that case is a **different** message, about the
  extension rather than about the kind.
- `exact` is not a different index but the absence of one: a full scan per search, which is what
  Qdrant already does below its own indexing threshold and what the pgvector store has always done.

**What to do.** Set `index` to one of the kinds the message lists. If you meant to run DiskANN on
Postgres, you need an image carrying `vectorscale`; `compose.yaml`'s `bm25` profile has one, and
the refusal you get without it names the extension rather than this error.

### `UnsupportedPrecisionError`

**What it looks like** — `precision` names a vector precision the configured backend cannot hold:

```text
UnsupportedPrecisionError: [packs.store] precision 'int8' is not served by pgvector. It serves:
float32, float16, binary.
```

**Why this exists when nothing raises it on one backend.** `VectorPrecision` names `float32`,
`float16`, `int8` and `binary`, and the two backends do **not** serve the same subset — they
overlap on `float32` and `binary` only. Qdrant holds all four (`float16` as the vector datatype,
`int8` as scalar quantization, `binary` as binary quantization), so nothing reaches this error
there today. pgvector's HNSW indexes `vector`, `halfvec` and `bit` and has no int8 form at all.

The class is defined for the *shape* of the refusal rather than for a current member, so that a
precision a backend cannot encode is refused by name at settings validation rather than reaching
the driver and failing as something unrecognisable. That asymmetry is stated rather than hidden:
a shared vocabulary does not mean a shared capability, and the honest way to express the
difference is a refusal that names what this backend serves.

**What to do.** Set `precision` to one of the values the message lists, or move the corpus to the
backend that serves the one you want — noting that changing precision against a store that already
holds vectors means re-indexing, since it changes what every stored vector compares as.

### `IterativeScanUnsupportedError`

**What it looks like** — `[packs.store] index` is `hnsw` and `iterative_scan` asks for a mode this
server's pgvector is too old to have:

```text
IterativeScanUnsupportedError: [packs.store] iterative_scan is 'relaxed_order', which pgvector
added in 0.8.0, and this server has vector 0.7.4. A filtered HNSW search without iterative scans
silently returns fewer rows than you asked for — measured at a mean of 0.03 rows out of 10 at 0.1%
selectivity — so this store refuses rather than serving a search whose answer is quietly wrong.
Upgrade pgvector to 0.8.0 or later, or set iterative_scan = "off" and accept that a filtered
search under hnsw may return fewer results than top_k.
```

**Why this refuses instead of falling back.** This is the one setting in this store where the
unsafe value is also the backend's own default. With `hnsw.iterative_scan = off`, pgvector scans a
fixed number of candidates *before* your filter is applied, so a selective filter can leave almost
nothing behind — and the search returns a short list with no error and no warning. Phase 29
measured it on 100,142 real chunks: recall@10 of **0.003** at 0.1% selectivity, and as few as
**0 of 10** rows returned. Quietly answering with the wrong rows is the failure this project
refuses by name, so a store that cannot honour the configured mode says so at connection time
rather than at every later query.

**What to do.** Upgrade the server — pgvector 0.8.0 or later, which the image `compose.yaml` pins
already carries. If you genuinely cannot, set `iterative_scan = "off"` deliberately: the refusal
goes away and so does the guarantee that a filtered search returns `top_k` results.

### `ProviderSettingsUnsupportedError`

**What it looks like** — an `[llm.roles]` entry writes a `settings` sub-table for a provider that
has no configuration of its own:

```text
ProviderSettingsUnsupportedError: role settings ['temperature'] were written for provider
'scripted', which declares no configuration of its own — remove them from this '[llm.roles]'
entry, or name a provider that accepts them.
```

**Why this refuses instead of ignoring them.** An operator who sets a temperature and gets the
model's default back has no way to tell the setting never applied — the run succeeds, the answers
look plausible, and the number they chose is nowhere. Phase 41 paid for the general form of this:
every local measurement in it ran at the server's default sampler because `[llm.roles]` could not
carry one at all, and that was invisible until somebody went looking. A setting that cannot be
honoured is named rather than dropped.

**What to do.** Check which provider the role names. `settings` is validated by *that provider's*
own configuration model, so the keys it accepts are the keys that provider documents — for
`openai` and `openai-compatible` those are `temperature`, `top_p` and `max_tokens`. A provider
like `scripted`, which replays a script and calls no model, has none: delete the sub-table, or
point the role at a provider that does. A key the provider does not recognise is refused by the
provider's own model, naming the field.

## Index targets — `weft_store`, `weft_engine.targets`

A **target** is a named, complete copy of an index. One target is **live**, and everything that
reads without naming a target reads the live one. You build a new index as a candidate target
beside it, compare the two, and then promote the candidate or roll back (`weft target`, and
`--target` on the commands that read or write an index).

### `InvalidTargetNameError`

**What it looks like:**

```text
'W-128' is not a valid target name — a target name is a lowercase letter first, then lowercase
letters, digits and underscores, at most 40 characters total
```

**Why:** a target's name becomes a Postgres schema, a Qdrant collection name and a directory, so it
is limited to the characters all three accept unquoted.

**What to do:** choose a name that fits, such as `w128` or `large_2026`.

### `UnknownTargetError`

**What it looks like:**

```text
'w256' is not a target this store holds — valid targets: default, w128
```

**Why:** you promoted, dropped or read a target that does not exist. A target is created by the
first write into it, so a candidate you have not indexed yet does not exist.

**What to do:** use one of the names the message lists, or index into the new target first.

### `WriterBusyError`

**What it looks like** — a second `weft index` into a store another one is still writing:

```text
another writer holds this store: 'weft index', pid 48213 on laptop.local, started
2026-09-23T14:02:11+00:00. Wait for it to finish, or stop it.
```

**Why** — two runs writing one store at once would interleave their records of which documents
are indexed, and each would report the other's work wrongly. The first run holds the store until
it ends. A run that crashed releases it: on pgvector at once, on Qdrant when its lease expires
(`[packs.qdrant] target_lease_seconds`).

**What to do:** let the first run finish, or stop it. `weft ask` is not a writer and is never
refused.

### `UnknownGenerationError`

**What it looks like:**

```text
'g-7f3a' is not a generation this store holds — generations: g-1c20, g-9e04
```

**Why:** a corpus-scoped layer, such as a RAPTOR tree over every document, is built as a
generation and published whole. The generation you named was never opened in this store, or it
was retracted.

**What to do:** use one of the ids the message lists. `weft index --layers <name>` opens a new
generation for the layer.

### `NotAPublishedGenerationError`

**What it looks like:**

```text
'g-7f3a' is building, not published, so it cannot be withdrawn — published generations: g-9e04
```

**Why:** when a corpus-wide layer is rebuilt, the tree it replaces is *withdrawn*. New queries stop
seeing it, while a query already running keeps reading it to the end. Its nodes are removed later,
before that layer's next build or by `weft reconcile`. Only a published tree can be withdrawn. This
one is still being built, or was withdrawn already.

**What to do:** if you wrote the calling code, withdraw one of the published generations the message
lists. A build that never published is discarded with `retract_generation`. From `weft index`, run
the command again: the rebuild reads the store's generations afresh.

### `NotAPublishedMemberError`

**What it looks like:**

```text
cannot carry 1 node(s) into generation 'g-9e04': no published generation holds n-51c2. Only a
member of a published generation can be carried forward; write a new node through the
generation's bound handle instead.
```

**Why:** a store that carries a layer's untouched nodes into its next generation, so a rebuild
does not rewrite them, carries only what readers can already see. The node named was never
published, it belongs to a retracted generation, or its source has been deleted. Nothing in the
call was carried.

**What to do:** if you wrote the calling code, carry only ids read from the published generation,
and store any other node through the new generation's bound handle. From `weft index --layers`,
run the command again: the rebuild reads the published generation afresh.

### `TargetInUseError`

**What it looks like:**

```text
'w128' cannot be dropped — it is the live target or the previous one, which a rollback needs
```

**Why:** dropping a target deletes everything in it. The live target is serving reads, and the
previous one is what a rollback would restore, so neither is dropped. The same error, ending
*another connection is bound to it* (pgvector) or *another handle is bound to it* (Qdrant), refuses
a target another command is still writing to. On Qdrant that claim is a lease, so a writer that
crashed holds it until `[packs.qdrant] target_lease_seconds` (default 600) has passed.

**What to do:** promote another target first, so the one you want to drop is neither live nor
previous. Or wait for the other command to finish, or, on Qdrant after a crash, for the lease to
expire.

### `NoPreviousTargetError`

**What it looks like:**

```text
nothing to roll back to — 'default' is live and no previous target is recorded
```

**Why:** a rollback restores the target that was live before the last promote, and nothing has
been promoted yet.

**What to do:** nothing needs undoing. To switch targets, promote the one you want.

### `StoreHoldsNoTargetsError`

**What it looks like:**

```text
the store 'example-store' cannot hold targets — it does not satisfy
weft_store.contract.TargetHolding — so --target 'w128' has nowhere to go
```

**Why:** the store you configured does not have the target capability, so it cannot keep a
candidate beside the live index.

**What to do:** leave out `--target` to use the store as it is, or switch to a store that holds
targets. The published conformance kit's target checks show whether a store does.

### `TargetTableMissingError`

**What it looks like:** any read or write against a pgvector target whose schema has lost a table:

```text
target 'w128' is catalogued, but its table weft_nodes is missing from schema weft_target_w128 —
something outside Weft dropped it, or a drop was interrupted. Weft will not recreate it empty or
read another target's table in its place. Drop the target and index it again.
```

**Why:** each pgvector target is a Postgres schema, and the store finds its tables through
`search_path`, with the schema that holds the `vector` extension, usually `public`, after the
target's own schema. If a target table goes missing, Postgres would quietly resolve the name to
the table of the same name in `public`, which belongs to the `default` target. The query would
then answer from the wrong corpus without any error. The store checks each table's schema when it
opens and refuses instead.

**What to do:** drop the target and build it again from its corpus. If the target is live, promote
or roll back to another target first, because a live target is not dropped.

### `TargetCollectionMissingError`

**What it looks like:** any read or write against a Qdrant target whose collection is gone:

```text
target 'w128' is catalogued, but its collection weft_nodes__t_w128 does not exist — something
outside Weft deleted it, or a drop was interrupted. Weft will not recreate it empty. Drop the
target and index it again.
```

**Why:** a Qdrant target is two collections. If one is missing, recreating it empty would make
every query against the target answer "nothing found" instead of reporting a failure.

**What to do:** drop the target and build it again from its corpus. If the target is live, promote
or roll back to another target first.

### `EmbeddingIdentityMismatchError`

**What it looks like:** a question embedded differently from the target it asks:

```text
this query embeds with 'hash' (model hash, width 64), and target 'w128' was built with 'hash'
(model hash, width 128) — vectors from two embedders cannot be compared. Set the embedder to
match the target, or query another target (`weft target rollback` restores the previous one).
```

or an index that would mix two embedders in one target:

```text
this index embeds with 'hash' (model hash, width 128) into target 'default', which was built with
'hash' (model hash, width 64) — a target holds one embedder's vectors. Index into a new target
with --target, or set the embedder back to match.
```

**Why:** each target records the embedder that made its first write: the plugin, its distribution,
the model it calls and the vector width. Two models of the same width produce vectors that can
still be compared numerically but mean nothing to each other, and no store notices that. Weft
refuses before any vector is compared.

**What to do:** configure the embedder that built the target. That means `[services] embed`, the
stage's `with: model:`, or `[packs.openai] embedding_model`, whichever set it. To move to a new
embedder, build a new target with `weft index --target`, compare it with the live one, and promote
it.

### `EmbedderStatesNoIdentityError`

**What it looks like:**

```text
the embedder 'stranger' does not say which model and width it embeds with — it does not satisfy
weft_embed.contract.IdentifiedEmbedder — so target 'w128' cannot record or check what built it
```

**Why:** a target only protects you from mixed embedders if it knows which embedder built it.
Weft refuses an embedder that cannot say when you name a target with `--target`, and when you
query a target whose identity is already recorded.

**What to do:** use an embedder that states its identity (every embedder that ships with Weft
does), or ask the embedder's author to implement `embedding_model()`. It is a one-method Protocol.

### `PromotionEvidenceMissingError`

**What it looks like:**

```text
promoting 'w128' needs evidence: two persisted runs, the first scoring the live target and the
second scoring 'w128', over one corpus and one question set — pass --evidence <live-run>
<candidate-run>, or --without-evidence to promote on your own judgement (recorded on the promotion)
```

**Why:** a promote changes what every question is answered from. Weft asks for the evaluation that
justifies it, and if you skip that, it records that you did.

**What to do:** score both targets with `weft eval run … --target <name>` on the same corpus and
questions, then pass the two run ids, live first. Or promote with `--without-evidence`.

### `PromotionEvidenceMismatchError`

**What it looks like:** the evidence does not show what a promote needs. The message names which
fact disagrees: the first run did not score the live target, the second did not score the
candidate, or the two runs differ in corpus or question set.

**Why:** evidence for a different pair of targets, or for different questions, says nothing about
this switch.

**What to do:** pass the live target's run first and the candidate's second, both scored over the
same corpus and question set. `weft eval compare <live-run> <candidate-run>` shows whether they
compare.

### `CandidateNotReadyError`

**What it looks like:** a promote refused because the candidate still holds a document recorded as
being indexed or deleted. The message names the documents.

**Why:** a candidate with a half-written document would answer from part of its corpus the moment it
became live.

**What to do:** let the index or delete finish, or re-run it (`weft index --target <name>`, or
`weft reconcile --target <name>` for an interrupted delete), then promote.

### `CandidateIdentityUnrecordedError`

**What it looks like:**

```text
'w256' has no recorded embedding identity — nothing ever wrote vectors into it through an
embedder that states one, so a query against it could not be checked. Index it with
`weft index --target w256` before promoting it
```

**Why:** once promoted, every query is checked against the embedder that built the live target. A
target that records none cannot be checked.

**What to do:** index the target with an embedder that states its identity (every shipped embedder
does), then promote.

### `GraphTargetTableMissingError`

**What it looks like:** any command that reads or writes the graph pack's store for a target whose
schema has lost a table:

```text
target 'w128' is catalogued, but its table kg_entities is missing from schema kg_target_w128 —
something outside Weft dropped it, or a drop was interrupted. Weft will not recreate it empty or
read another target's table in its place. Drop the target and index it again.
```

**Why:** the graph pack keeps each target in its own Postgres schema, `kg_target_<name>`, exactly as
the node store does, and it refuses rather than reading `default`'s table of the same name.
`TargetTableMissingError` above explains why.

**What to do:** drop the target and build it again. If it is live, promote or roll back first.

### `TargetPointersDisagreeError`

**What it looks like:** any command that reads or writes a project whose stores hold targets
separately, typically the node store and the graph pack's store:

```text
the stores this project uses disagree about which target is live — pgvector: 'default',
pgvector-graph: 'w128' — a promote or rollback stopped between them. Run `weft target promote w128`
again to finish it, or `weft target rollback` to undo it
```

**Why:** each store switches its live pointer atomically on its own, but there is no transaction
across two stores. If a promote is interrupted between them, the vectors answer from one corpus
and the graph from another. Weft refuses rather than mix them.

**What to do:** run the promote again: a store that already moved is left as it is, and the other
catches up. Or roll back.

### `EmbedConfigRefusedError`

**What it looks like:** a `[services.embed_config]` key the selected embedder does not have:

```text
[services.embed_config] names 'dimensions', which the 'hash' embedder does not take — it takes:
dimension
```

**Why:** `[services.embed_config]` configures the embedder that embeds your questions. It is
checked against that embedder's own settings, and a key it would ignore is refused, because an
ignored key makes the question embed differently from the index you think you are asking.

**What to do:** use one of the keys the message lists. To ask an index built with a configured
embedder, set the same configuration here, for example `dimension = 128` for a hash index built at
width 128. `weft target list` shows how each target was built.
