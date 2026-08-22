"""Builds the `TracerProvider` `register()` installs — kept separate so it can be tested
without ever touching `opentelemetry.trace`'s real, process-global, set-once provider slot.

`docs/02-extension-model.md` §1 -> *Capability is derived, never declared* states the rule
this module applies to an exporter instead of a plugin: "a pack probing its optional
dependencies and registering only what works." **Declaration and verification are one act**
here means `build_tracer_provider` does not merely check that `weft-otel[otlp]` is
`pip`-installed; it checks that there is an `endpoint` to send to, because an OTLP exporter
built with no endpoint is not a working exporter, it is a `TypeError` waiting for the first
span. Neither check reaches the network — this function stays as fast and side-effect-free
as `register()` itself must be (`docs/02-extension-model.md` §2: "`register()` is
import-light"), the same reason `weft_store.pgvector_store`'s own connection is lazy, opened
on first use, rather than dialled here to "verify" it. A collector that is configured but
unreachable is the OTLP exporter's own problem at export time — it retries and logs on its
own schedule, which is the whole point of choosing a batching, best-effort exporter over a
call that could fail a person's `weft index` because a trace collector had a bad minute.
"""

from __future__ import annotations

from collections.abc import Callable
from importlib import import_module
from typing import cast

from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor, SpanExporter

from weft_otel.settings import OtelExporter, OtelSettings

#: The optional `weft-otel[otlp]` extra's own module path — named once so `otlp_exporter`
#: and its docstring cannot drift from each other or from `pyproject.toml`'s own extra name.
_OTLP_MODULE = "opentelemetry.exporter.otlp.proto.http.trace_exporter"


def build_tracer_provider(settings: OtelSettings) -> tuple[TracerProvider, OtelExporter]:
    """The provider `register()` should install, and which exporter actually backs it.

    Raises `ValueError` for `settings.exporter is OtelExporter.NONE` — `register()`'s own
    guard checks this first and never calls in, so reaching this function with `NONE` is a
    caller error, not an operator's, and it is refused loudly rather than silently building
    a console exporter labelled `NONE`. The returned `OtelExporter` is `settings.exporter`
    itself only when that is genuinely what got used; it is `CONSOLE` whenever `OTLP` was
    requested but `otlp_exporter` could not build one, so a caller printing what registered
    never claims OTLP ran when the console exporter is what a span will actually reach —
    `docs/02-extension-model.md` §2: "doctor prints what registered, what did not, and why."
    """
    if settings.exporter is OtelExporter.NONE:
        raise ValueError(
            "build_tracer_provider must not be called for OtelExporter.NONE — the caller "
            "(register()) is expected to skip it before reaching here."
        )

    resource = Resource.create({"service.name": settings.service_name})
    provider = TracerProvider(resource=resource)

    actual = settings.exporter
    exporter: SpanExporter
    if settings.exporter is OtelExporter.OTLP:
        chosen = otlp_exporter(settings)
        if chosen is None:
            actual = OtelExporter.CONSOLE
            exporter = ConsoleSpanExporter()
        else:
            exporter = chosen
    else:
        exporter = ConsoleSpanExporter()

    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider, actual


def otlp_exporter(settings: OtelSettings) -> SpanExporter | None:
    """The OTLP exporter, or `None` when it cannot run yet — never raises.

    Two independent reasons return `None`, and both are ordinary, not exceptional: the
    optional `weft-otel[otlp]` extra is not installed (`ImportError`), or `endpoint` was
    never set. Checked in this order so an operator who installed the extra but forgot the
    endpoint gets the identical, unsurprising fallback as one who never installed it at all —
    there is exactly one fallback behaviour, not two.

    Loaded through `importlib.import_module` rather than a top-level `from ... import
    OTLPSpanExporter` — the module docstring's `register()` is import-light, so nothing
    imports this optional extra until a setting actually asks for it, and this is also the
    only shape `pyright --strict` can check without the extra installed: a static `from`
    import of a module this workspace never resolves (the extra ships from no dependency
    group, on purpose — see `pyproject.toml`) would be an unresolvable import at every
    `ci-checks` run, not only at the operator's.
    """
    if settings.endpoint is None:
        return None
    try:
        module = import_module(_OTLP_MODULE)
    except ImportError:
        return None

    api_key = settings.api_key.get_secret_value()
    headers = {"Authorization": api_key} if api_key else None
    exporter_cls: Callable[..., object] = module.OTLPSpanExporter
    return cast("SpanExporter", exporter_cls(endpoint=settings.endpoint, headers=headers))
