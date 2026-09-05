"""Answers `weft plugins doctor`'s real question about tracing: *are my spans going anywhere?*

Task **5.1d**. `weft_kernel.seam.wrap` has emitted an OpenTelemetry span for every plugin call
since Phase 0; whether any of them reach an exporter depends on whether something in the
process called `opentelemetry.trace.set_tracer_provider` before the command ran. A `PackReport`
cannot answer this on its own: `weft_kernel.discovery._read_disclosure` reads a pack's
`DISCLOSURE` *before* `register()` runs (`docs/02-extension-model.md` §2), so nothing on a
`PackReport` can carry what `register()` actually decided to do, and `contributed` counts
registrations against a contract — `weft-otel` (`docs/02-extension-model.md` §4) registers
none, by design, so it has no count to report either.

**This check is deliberately pack-agnostic.** It never imports or names `weft-otel` — it reads
`opentelemetry.trace.get_tracer_provider()` after discovery has run and reports the one fact
that answers the operator's question: is the process's `TracerProvider` still the no-op
default, or has *something* — `weft-otel`, or a host application embedding `weft` as a library
and configuring its own tracing — set a real one. This is the same shape `render_doctor`
already uses for `displaced`/`unconsulted_pins` (`weft_cli.plugins_report`'s own module
docstring): a fact assembled from a source beyond any one `PackReport`, printed as its own
block rather than invented as a field on one distribution's report.

**Informational, never enforced** — the identical posture `docs/02-extension-model.md` §2
states for `Disclosure`: this module answers a question, it does not gate a command on the
answer.
"""

from __future__ import annotations

from opentelemetry import trace


def describe_tracing() -> str:
    """One line: whether the process's `TracerProvider` is a real one, and where spans go.

    `trace.NoOpTracerProvider`/`trace.ProxyTracerProvider` are both public
    `opentelemetry-api` classes — the no-op default and the lazy stand-in returned before
    any real provider is set (`opentelemetry.trace.get_tracer_provider`'s own source).
    Anything else is a real, configured provider, whoever set it.
    """
    provider = trace.get_tracer_provider()
    if isinstance(provider, (trace.NoOpTracerProvider, trace.ProxyTracerProvider)):
        return (
            "not configured — spans stay on the no-op default and go nowhere. Install "
            "weft-otel and set [packs.otel] exporter to 'console' or 'otlp' (its own "
            "default is 'none', so installing alone is not enough), or configure a "
            "TracerProvider yourself."
        )
    kind = type(provider)
    return f"configured — spans export through {kind.__module__}.{kind.__qualname__}."
