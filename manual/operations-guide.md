# Running Weft

Written for someone who runs Weft, not someone who builds it. It answers three questions: how do
I bring the one container up, how do I wire Weft to it, and when `weft plugins doctor` or an exit
code tells me something, what do I do about it. Definitions link to
[`docs/02-extension-model.md`](../docs/02-extension-model.md) §2 and
[`docs/03-cli.md`](../docs/03-cli.md) rather than restating them — this page is the task, not the
argument for why it is shaped this way.

## The one container

Weft's runtime shape gives a container to exactly one thing: the database. This is the repository's
own `compose.yaml`, included here rather than retyped, so this page cannot show a topology that no
longer matches what ships:

```yaml path=compose.yaml
# The one container Weft's runtime shape allows — `docs/01-high-level-plan.md`
# → *Runtime shape*: "the only thing that gets a container is the database."
# G4 retired the zero-container target and made pgvector the floor
# (`docs/06-phase-0-build.md` step 8), so this is where it arrives.
#
# `docker compose up -d` brings it up, and the store creates its own schema on
# first use — there is no separate migration step to run first.
#
# **Bringing the container up is not enough to make the store usable.** `weft-store`
# requires a `dsn` in its pack settings, and there are two ways to supply it. With no
# `weft.toml` at all, an exported `WEFT_DATABASE_URL` is offered as `dsn` and the store
# comes up `active` — the no-file path `manual/quickstart.md` walks. A `weft.toml`
# carrying `[packs.weft-store] dsn` — see `weft.toml.example` — wins over the
# environment, key by key. `weft plugins doctor` reports `weft-store: failed`, naming
# the missing field, only when NEITHER supplies a `dsn` — the loud failure working: the
# pack refuses rather than defaulting to some database it guessed.
#
# Port 5433, not 5432: `.env.example` explains why — a bare default port on a
# developer's machine belongs to whichever Postgres happened to claim it
# first, and this project's store is namespaced everywhere else too.
services:
  postgres:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_USER: weft
      POSTGRES_PASSWORD: weft
      POSTGRES_DB: weft
    ports:
      - "5433:5432"
    volumes:
      - weft-postgres-data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U weft -d weft"]
      interval: 2s
      timeout: 3s
      retries: 20

volumes:
  weft-postgres-data:
```

```bash
docker compose up -d
```

That is the whole operation. There is no migration command to run afterward — the store creates
its own schema the first time anything writes to it — and no second service to start: everything
that is not the database runs inside the `weft` process itself.

## Wiring `weft.toml`

`weft-store` takes its connection string from its own pack settings, `[packs.weft-store] dsn`, and
there are two ways to supply it. **With no `weft.toml` at all** — the path `manual/quickstart.md`
walks — an exported `WEFT_DATABASE_URL` is offered as `dsn` on its own, and that is enough to bring
`weft-store` up. A project that wants an explicit, committed connection string instead copies
`weft.toml.example`:

```toml
[packs.weft-store]
dsn = "${env:WEFT_DATABASE_URL}"
```

`${env:VAR}` is interpolated by the settings loader before a pack ever sees its settings, so a
secret lives in the environment and a project can still commit the file that names which variable
it wants. Referencing a variable that is not set is a hard failure — `weft` refuses to build a
registry at all, naming the variable, rather than handing a pack half a connection string:

```text
'${env:WEFT_DATABASE_URL}' names an environment variable that is not set. Set WEFT_DATABASE_URL,
or remove the reference from the configuration.
```

**A `weft.toml` value wins over the environment, key by key.** `weft-store`'s settings are built by
merging what `weft.toml` says over what `WEFT_DATABASE_URL` offers, and the file's own keys are
never overwritten by the environment — only keys the file leaves unsaid are filled from it. This
is deliberate: a stale `WEFT_DATABASE_URL` left over in a shell must never quietly redirect a
project whose `weft.toml` already names a different database. A store pointed at the wrong
database does not crash — it answers plausibly, against the wrong data, which is the failure this
project exists to remove. Concretely: with `WEFT_DATABASE_URL` pointed at a real, reachable
database and `weft.toml` naming a different, unreachable one, `weft plugins doctor` reports
`weft-store: active` — the file's value is the one in play — and `weft ask` fails to connect,
exactly as it should for the database `weft.toml` actually named.

`weft.toml` is also where a project pins which packs may run at all:

```toml
[packs]
allow = ["weft-extract", "weft-chunk", "weft-embed", "weft-store"]
```

Absent, the posture is open — every installed pack runs. Present, it is exhaustive: anything not
listed is refused, and refusal happens *before* the pack is ever imported, not after. This is a
statement of policy, not a sandbox — see *What this does not protect you from*, below.

## Doctor

`weft plugins doctor` is the first and usually last thing to run when a pack is not doing what you
expect. One status per installed distribution:

| Status | Meaning | What to do |
|---|---|---|
| `active` | Imported, `register()` ran, contributing | Nothing — this is the working state. See the next section for the one thing `active` does *not* mean |
| `refused` | Listed out of an active `[packs] allow` pin. Never imported | Add the distribution to `allow` in `weft.toml`, if you meant to permit it |
| `failed` | Imported, but `register()` raised — most often, its settings failed validation | Read the reason doctor prints; it names the pack and the field. Fix the setting or the `weft.toml` entry it comes from |
| `partial` | Registered, but a conditional dependency it wanted was not available, so part of what it offers did not | Install the missing optional dependency, or accept the reduced set — doctor's reason names what was skipped and why |
| `allowed, not installed` | Named in `[packs] allow`, but nothing installed provides it | `uv add` the distribution, or remove it from `allow` if it was named in error |

`doctor` also flags a pack `active, ambient` when it is running but is not a direct dependency of
the project — arriving as something a chosen pack pulled in transitively, rather than something
anyone `uv add`ed on purpose. That flag depends on `weft` being told which distributions a project
actually named as direct dependencies; Phase 0's CLI does not yet supply that, so every pack
reports without the `ambient` flag regardless of how it arrived. Read the `status` column, not the
`ambient` flag, until that lands.

Every block also prints a pack's `disclosure` — what it says it touches, in its own words. A pack
that discloses nothing prints `not disclosed`. This is information the pack chose to publish about
itself, never a fact `weft` checked; see *What this does not protect you from*.

## The one thing to know about `active`

**`weft-store: active` does not mean the database is reachable.** A `dsn` is validated for shape —
is it a string a driver could parse — never for whether anything answers at the other end. Point
`weft.toml` at a real host with the wrong port and `doctor` still reports `active`; the failure
shows up the moment a command actually tries to connect:

```text
weft ask: OperationalError: connection failed: connection to server at "127.0.0.1", port 59999
failed: could not receive data from server: Connection refused
This is an error weft did not translate — the message above comes from the library that raised it.
Re-run with WEFT_TRACEBACK=1 for the full traceback.
```

That is not a bug to route around — whether `doctor` should probe a store's connectivity is a
design question `docs/02-extension-model.md` §2 owns, not something settled here. The operational
fact stands regardless: `active` is "registered and configured," not "reachable right now," and
the way you find out otherwise is by running a command that actually uses it, or by setting
`WEFT_TRACEBACK=1` to see the driver's own error in full.

## Exit codes

Every command's exit code is meaningful — `weft` never always-exits-`0` — so a script or a CI job
can act on the difference between a policy problem and a resolution problem, per
[`docs/03-cli.md`](../docs/03-cli.md) → *Output*.

| Code | Name | Meaning |
|---|---|---|
| `0` | `SUCCESS` | The command did what it was asked |
| `1` | `OPERATION_FAILED` | The command ran, but the operation itself failed — an unreachable database, a document that failed to extract. An error weft did not translate reaches this code too, printed as one line rather than a traceback |
| `2` | `BAD_USAGE` | The command line itself was wrong — `argparse` catches this before any command runs |
| `3` | `POLICY_REFUSED` | A **policy** refusal — a pipeline named a plugin from a pack `[packs] allow` refuses |
| `4` | `RESOLUTION_FAILED` | A **resolution** failure — a name no installed pack provides, or one lost to a `failed`, `partial` or `allowed, not installed` pack |

**3 and 4 answer different questions, on purpose.** 3 means *the environment refused this on
policy grounds* — fix `weft.toml`, or accept that it is refused. 4 means *nothing here can produce
what was asked for* — fix the pipeline, or install what is missing. A CI job that treats them the
same cannot tell "this needs a config change" from "this needs a different pipeline," which is the
whole reason the split exists. Concretely, with `weft-store` refused by an active `allow` pin:

```text
$ weft ask "hello"
'weft-store' is refused by [packs] allow in weft.toml. Add it there to permit it.
$ echo $?
3
```

and with no `dsn` configured at all, so `weft-store` never registered in the first place:

```text
$ weft index corpus
'weft-store' failed to register: 'weft-store' settings failed validation: 1 validation error for
PgVectorSettings
dsn
  Field required [type=missing, input_value={}, input_type=dict]
$ echo $?
4
```

**A connection failure at runtime is exit `1`, not `3` or `4`.** `weft-store` was `active` — it
registered, its settings validated, the shape checked out — so this is neither a policy refusal
nor a name nothing could resolve. It is an operation that ran and failed, which is exactly what
`1` means.

`WEFT_TRACEBACK=1` re-raises the underlying exception instead of the one-line rendering, for
whoever has to actually fix the failure rather than just see that one happened.

## What this does not protect you from

**A pack runs with your full privileges. Installing one is trusting it.** `[packs] allow` decides
whether a pack's `register()` is ever called; it decides nothing about what that code does once it
runs. There is no process boundary, no sandbox, and no per-pack limit on what a pack can open, call
out to, or read — CPython does not have one to offer, and nothing here simulates one. A pack you
deliberately install and permit can do anything your own account can do.

**Disclosure is a pack's own claim, unverified.** The `network` / `filesystem` / `subprocess`
lines doctor prints under each pack came from that pack's own `DISCLOSURE`, read and printed
as-is. `weft` never checks it against what the pack actually does. `not disclosed` is honest —
nobody claimed anything — not a statement that the pack is safe.

**`[packs] allow` stops an *unlisted* pack from running; it says nothing about a listed one.**
Refusal happens before import, which is real — a refused pack's code genuinely never executes. But
a pack you added to `allow` runs exactly as fully as if there were no allow-list at all.

**Command permission classes (`read`/`write`/`overwrite`/`destroy`/`network`) protect you from the
tool, not from a pack — and Phase 0 declares them without wiring the protection yet.** Every
built-in command names its class today, with no default, so the vocabulary is fixed and every
command is honestly categorised. The prompt they will govern — core stopping and asking before a
destructive-looking operation — arrives with the CLI's destructive-operation guard in Phase 3; Phase
0 ships no `overwrite` or `destroy` command; nothing here interrupts you yet. Once it does, it will
still be the same limit: a dishonest pack that declares `read` and deletes your collection anyway
will not be stopped by anything described on this page.

None of this is a gap waiting to be closed by more careful configuration — it is the actual shape
of the trust model, stated so nobody assumes a protection that was never built. See
[`docs/02-extension-model.md`](../docs/02-extension-model.md) §2, *The trust model*, for the
argument behind each of these, including why a stronger model was considered and rejected.

## Where to go next

- **Never run `weft` before?** [`manual/quickstart.md`](quickstart.md) is the five-minute path from
  nothing to a real, retrieved answer.
- **Writing a pack of your own?** [`manual/pack-author-guide.md`](pack-author-guide.md) walks a
  real one, installed from outside this project's own workspace.
