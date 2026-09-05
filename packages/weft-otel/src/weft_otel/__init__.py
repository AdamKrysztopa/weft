"""First-party observability pack — closes `docs/lessons.md` L5.1, the second add-on G7
produced (`docs/02-extension-model.md` §4).

**The gap this pack closes.** `weft_kernel.seam.wrap` has emitted an OpenTelemetry span for
every plugin call since Phase 0 — distribution, contract, plugin, duration, failure — and
nothing in this tree ever configured a `TracerProvider`, so every one of those spans reached
`opentelemetry-api`'s no-op default and went nowhere. G7 named an audit log as a deliberately
awkward capability to test the extension model against; half of that want (observing runs
that never opted in) stays refused by `docs/02-extension-model.md` §3's own rule, but the
other half — shape-level observation — turned out to already exist and be merely
unreachable. `weft-otel`'s whole job is reachability.

**Registers no plugin against any contract, contributes to no pipeline.** `01` -> *The kernel
boundary*: "everything that exports a span is a pack" — this is that pack, and it needs no
extension point of its own, because setting a process-global `TracerProvider` is not a
capability a pipeline selects among; it is a fact about the process, decided once, before any
pipeline runs. `register()` therefore never calls `registrar.add(...)`; `registrar` is
accepted (`docs/02-extension-model.md` §2's fixed two-parameter shape,
`weft_kernel.discovery._resolve_settings` inspects it) and immediately discarded.

**Why this makes `contributed=0` an honest, permanent fact about this pack rather than a
defect** — see `tests/architecture/test_ff2_no_privileged_builtins.py`'s own note on the
floor assertion this pack forced a correction to, and `docs/build-ledger.md` 5.1d for the
argument in full: fitness function 2's real protection (the registry holds exactly what
discovery declared, one-for-one, with no privileged rewrite) does not depend on every
first-party pack contributing a plugin — only on `weft-otel` never being the exception that
proves a rewrite happened when it did not.

**Exporter choice is a pack setting, probed and verified together at `register()` time** —
see `weft_otel.provider` for the console/OTLP decision and `weft_otel.settings` for the
`Settings` model itself.
"""

from __future__ import annotations

import sys

from opentelemetry import trace

from weft_kernel.discovery import Disclosure, PackRegistrar
from weft_otel.provider import build_tracer_provider
from weft_otel.settings import OtelExporter, OtelSettings

#: The one name a `weft.toml` `[packs]` block or a doctor report ever needs for this pack —
#: the entry-point alias is `otel`, spelled once here so the pack, its own test suite and
#: `pyproject.toml`'s `[project.entry-points."weft.packs"]` line cannot disagree about it.
NAME = "otel"

#: `docs/02-extension-model.md` §2 -> *The trust model*: "concrete strings, not booleans."
#: `network`/`filesystem`/`subprocess` are genuinely empty — an OTLP export is a real network
#: call this pack can make, but only once an operator sets `endpoint`, so there is no fixed
#: address to disclose in advance the way `weft-graph`'s worked example discloses a
#: configured Neo4j URL; `note` says so instead, in prose, since that is exactly what the
#: asymmetry in `02` §2 exists for — a disclosure is informational, never a claim weft checks.
DISCLOSURE = Disclosure(
    network=(),
    filesystem=(),
    subprocess=(),
    note=(
        "Sets the process OpenTelemetry TracerProvider from [packs.otel] settings. "
        "exporter defaults to 'none' (nothing exported until configured); 'console' prints "
        "to stdout; 'otlp' reaches the network at whatever endpoint is configured. "
        "Registers no plugin against any contract."
    ),
)


def register(registrar: PackRegistrar, settings: OtelSettings) -> None:
    """Set the process `TracerProvider` from `settings` — see the module docstring.

    `registrar` is unused by design: this is the one first-party pack with nothing to
    buffer. `settings.exporter is OtelExporter.NONE` is a deliberate no-op, not a partial
    registration — see `weft_otel.settings.OtelExporter.NONE`'s own docstring for the
    operator this exists for.

    `opentelemetry.trace.set_tracer_provider` can only succeed once per process; a second
    call anywhere (this pack's own `register()` running twice, or another library that
    already configured tracing before `weft` did) logs a warning and changes nothing. That is
    `opentelemetry-api`'s own behaviour, not a case this function detects or reports on — a
    real `weft` invocation calls `register()` exactly once, through `discover()`, and the
    only caller with a reason to invoke it more than once is this pack's own test suite,
    which never touches the real global slot to do it (`tests/unit/weft_otel/
    test_register.py`'s own docstring).
    """
    del registrar

    if settings.exporter is OtelExporter.NONE:
        return

    provider, actual = build_tracer_provider(settings)
    if actual is not settings.exporter:
        print(
            f"weft-otel: exporter '{settings.exporter.value}' requested but not usable "
            f"(install the 'weft-otel[otlp]' extra and set [packs.otel] endpoint) — "
            f"falling back to '{actual.value}'. See `weft plugins doctor`.",
            file=sys.stderr,
        )
    trace.set_tracer_provider(provider)


__all__ = [
    "DISCLOSURE",
    "NAME",
    "OtelExporter",
    "OtelSettings",
    "register",
]
