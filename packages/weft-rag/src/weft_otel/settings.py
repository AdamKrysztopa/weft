"""`weft-otel`'s pack settings — where spans go, and what deciding that costs.

`docs/02-extension-model.md` §2 -> *Pack settings*: "a deployment is one resource everything
this pack registers reaches through" — the same distinction `weft_qdrant.settings` draws for
its Qdrant URL, applied here to a place spans are sent rather than a place nodes are stored.
`weft-otel` registers nothing, so there is no factory to bind this into; `register()` reads
it directly.

**`exporter` is `Enum`, never a bare string** — CLAUDE.md's own rule — and it is exhaustive:
`NONE`, `CONSOLE`, `OTLP`.

**`exporter` defaults to `NONE`, and that default was not the first one written here.** An
earlier draft defaulted to `CONSOLE` — "`uv add weft-otel` and it just works," the reading
`docs/02-extension-model.md` §4's graph-pack narrative invites. It was wrong, and measurably
so rather than merely inconsistent with a preference: `opentelemetry.trace.
set_tracer_provider` succeeds exactly **once** per process, and this repository's own test
suite calls `weft_cli.registry_bootstrap.build_dependencies` — the real discovery path,
open by default — from dozens of existing tests across `tests/unit/weft_cli/test_cli.py`,
`test_repl.py` and `test_registry_bootstrap.py`, none of which has anything to do with
tracing. With `CONSOLE` as the default, whichever of those happened to run first inside one
`pytest tests -q` process silently claimed the provider slot for good, and
`tests/unit/weft_kernel/test_seam_trace_visibility.py` — which needs to be the one that
wins — started losing that race, non-deterministically, depending on collection order. That
is `docs/lessons.md` L5.1's own failure shape one level up: a mechanism that looks like it
closes the gap and does not survive being run. `NONE` closes it correctly: installing
`weft-otel` is necessary but not sufficient, and `[packs.otel] exporter = "console"` (or
`weft config set packs.otel.exporter console`) is the one additional step — no different
in kind from `weft-qdrant`'s own `url` needing to be told where a non-default deployment
lives. `weft plugins doctor`'s `tracing:` line says exactly this when it is not yet done.

**Every other field has a default, `weft_qdrant.settings`'s own load-bearing reason restated
for a different pack**: pack settings are validated *before* `register()` runs, so a required
field with no default would turn a machine with no `[packs.otel]` block into a `FAILED`
pack — for `weft-otel` specifically, `FAILED` and "declined to export, on purpose" are
different facts, and only `exporter: NONE`, not a validation error, tells them apart.
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, SecretStr


class OtelExporter(StrEnum):
    """Where `register()` sends spans. Exhaustive — see fitness function 5(b)'s own rule
    that every dispatch over a published `Enum` is total, applied here even though this
    pack owns no dispatch a fitness function walks: three members, three branches in
    `weft_otel.provider.build_tracer_provider`, nothing left implicit.
    """

    #: The default. `register()` does not call `opentelemetry.trace.set_tracer_provider` at
    #: all — see the module docstring for why this, not `CONSOLE`, is what a fresh install
    #: gets.
    NONE = "none"
    #: `opentelemetry.sdk.trace.export.ConsoleSpanExporter` — stdout, no network, no extra
    #: dependency beyond this pack's own `opentelemetry-sdk` requirement. The one-line opt-in:
    #: `[packs.otel] exporter = "console"`.
    CONSOLE = "console"
    #: `opentelemetry.exporter.otlp.proto.http.trace_exporter.OTLPSpanExporter`, from the
    #: optional `weft-otel[otlp]` extra. Falls back to `CONSOLE`, loudly, when the extra is
    #: not installed or `endpoint` is unset — `weft_otel.provider`'s own docstring.
    OTLP = "otlp"


class OtelSettings(BaseModel):
    """One process's tracing configuration. `docs/02-extension-model.md` §2's shape:
    `register(registrar, settings: OtelSettings)`.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    exporter: OtelExporter = OtelExporter.NONE

    #: The `service.name` resource attribute every span this process emits carries — the one
    #: fact worth setting even for the zero-network `CONSOLE` exporter, since a laptop running
    #: two Weft projects side by side wants their spans distinguishable in whichever backend
    #: eventually reads a persisted export.
    service_name: str = Field(default="weft", min_length=1)

    #: `OTLP` only. Unset means "not configured", which `build_tracer_provider` treats
    #: identically to the optional dependency being absent — both are reasons OTLP cannot
    #: run yet, and the fallback does not need to distinguish which.
    endpoint: str | None = None

    #: `OTLP` only, sent as the literal value of an `Authorization` request header when set —
    #: an operator writes `${env:OTEL_API_KEY}` naming the whole bearer value (`"Bearer
    #: sk-..."`), the identical `${env:VAR}` interpolation `weft_qdrant.settings.api_key`
    #: already documents, never a scheme this pack assumes on the operator's behalf.
    api_key: SecretStr = SecretStr("")
