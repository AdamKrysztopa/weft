"""The one place `weft_otel.register`'s real, unmocked effect is demonstrated end to end.

`docs/lessons.md` L5.1 — "an escape hatch was cited before it was verified" — is exactly the
mistake this file exists not to repeat: `test_register.py` proves `register()`'s *logic*
against a monkeypatched `set_tracer_provider`, which is the right tool for testing decisions
but proves nothing about whether a real span really reaches a real exporter. This file spawns
a fresh interpreter — `opentelemetry.trace.set_tracer_provider` can only succeed once per
process, so a fresh one is the only way to watch it happen for real without contending with
`tests/unit/weft_kernel/test_seam_trace_visibility.py`'s own claim on the shared pytest
session's single provider slot (see `test_register.py`'s own module docstring for the full
argument). `ConsoleSpanExporter` prints each finished span to stdout, unprompted — this test
reads that output rather than asserting the mechanism worked from intuition.

The script argv below is a literal, inlined directly rather than built from a module-level
constant — ruff's `S603` can prove a literal argv carries nothing an environment variable or
caller input could have changed, which is what lets this file spawn a real interpreter with
no suppression.
"""

import subprocess
import sys


def test_register_makes_a_real_span_reach_a_real_exporter() -> None:
    # Arrange / Act — a fresh interpreter, so the process-global TracerProvider starts
    # unclaimed regardless of what this test session's other files already configured.
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from opentelemetry import trace\n"
            "from weft_kernel.discovery import PackRegistrar\n"
            "from weft_kernel.registry import Registry\n"
            "from weft_otel import register\n"
            "from weft_otel.settings import OtelExporter, OtelSettings\n"
            "registrar = PackRegistrar(Registry(), distribution='weft-otel')\n"
            "settings = OtelSettings(\n"
            "    exporter=OtelExporter.CONSOLE, service_name='weft-otel-subprocess-check'\n"
            ")\n"
            "register(registrar, settings)\n"
            "tracer = trace.get_tracer('weft_otel.subprocess_check')\n"
            "with tracer.start_as_current_span('probe-span'):\n"
            "    pass\n",
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    # Assert — the console exporter printed the span it saw, with no prompting beyond calling
    # `register()` the way `discover()` would.
    assert result.returncode == 0, result.stderr
    assert "probe-span" in result.stdout
    assert "weft-otel-subprocess-check" in result.stdout
