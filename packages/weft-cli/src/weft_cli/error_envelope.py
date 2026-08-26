"""The structured error envelope crossing the process boundary under `--json` — task 5.2d.

`docs/README.md` decision log, **S6**: G9 ruled CLI error prose unpromised only because a
structured channel is promised in its place — *"the promise is the `WeftError` subclass name as
failure identity plus a structured, additively versioned error envelope carrying the human string
as a `rendered` field."* Before this task nothing built that channel: `weft_cli.render.
render_refusal` returned `str(exc)` on every failure path, `--json` included, so of the 78 raise
sites across `weft-cli` that compute `valid_options` (`docs/01-high-level-plan.md` -> *Fitness
functions* item 12, `weft_kernel.errors.UnresolvedNameError`), **none reached a script except as a
sentence** — the measurement S6 and this task's own `docs/build-ledger.md` line record.

**Why a new module rather than a field on `Rendered`.** `weft_cli.render.Rendered` is `stdout`/
`stderr`/`exit_code` — three primitives, the shape every renderer already returns, human or
machine. This module is what a json-mode renderer builds *before* it becomes one of those three
values; keeping the model here, owned by neither renderer, is what lets this tree's two
`WeftError`-catching sites build the identical envelope instead of each inventing its own JSON
shape: `weft_cli.render.render_refusal` (a `Command` already chosen, refused before or during its
own `run()`) and `weft_cli.cli.main`'s own discovery-failure catch (no `Command` chosen yet —
`weft.toml` did not even parse, say — so `render_refusal`'s `CommandRefusalError` branch could
never apply there).

**Versioned additively, in the data — `docs/09-release.md` §3, and `02` §1's S5 rule pointed at a
wire format instead of a stored one.** `weft_kernel.payload.ext.ExtModel.__schema_version__`
(task 5.2c) settled the shape for a persisted schema: the version travels *in the bytes*, never as
a `ClassVar` a serialiser would drop, because a reader cannot assume the version its own class
expects is the version an already-written row carries. The identical argument applies to a wire
format nobody controls both ends of: `ENVELOPE_VERSION` is a plain field with a default, not a
`ClassVar`, so `model_dump_json()` always emits it, and a future field is additive — `09` §3's own
git `--porcelain=v1` warning is the argument for never freezing this: *"New fields may be added; a
consumer ignores what it does not recognise... could not evolve it, and had to ship v2 as a
parallel format."* A version *bump* is a decision for whoever next reshapes or removes a field;
nothing built here does either.

**What travels, and why each field is here.** `error` — `type(exc).__name__`, the identity `09`
§3 promises, which `manual/troubleshooting.md`'s own coverage ratchet
(`tests/docs/test_troubleshooting_coverage.py`) already enumerates by this exact string, so the
two documents describe the same set without deriving it twice. `rendered` — `str(exc)`, whole and
untruncated; `09` §3: *"The exclusion [of prose from the promise] is what lets the message stay
rich"* — this module is not the place that promise gets broken by templating a human message down
to fit a schema. `exit_code` — the same `weft_cli.exit_codes.ExitCode`
`weft_cli.exit_codes.exit_code_for`/`weft_cli.commands.CommandRefusalError.exit_code` already
computed, so a script reading only stdout can still tell success from failure without also reading
the process's own exit status. `valid_options` — set only when `exc` is a `weft_kernel.errors.
UnresolvedNameError` member, `None` otherwise: a collision or a malformed shape has no alternative
name to offer, and a field that is always present but usually empty would be indistinguishable
from "there really were no alternatives". `pack`/`contract`/`plugin`/`stage` —
`weft_kernel.seam.wrap`'s own attribution (`weft_kernel.errors.WeftError`'s own module docstring:
"Attribution is data this type carries, not logic it performs"), carried through rather than
re-derived, since a script debugging a third-party pack's failure needs exactly what a human
reading `docs/03-cli.md`'s own worked examples already gets. Every one of the four is `None` for
an error raised outside any wrapped call — honestly, not omitted.
"""

from __future__ import annotations

from typing import Final

from pydantic import BaseModel, ConfigDict

from weft_cli.exit_codes import ExitCode
from weft_cli.sinks import LineKind
from weft_kernel.errors import UnresolvedNameError, WeftError

#: `09` §3's "additively versioned" promise, carried in the data (see module docstring) rather
#: than as a `ClassVar` that would never reach `model_dump_json()`.
ENVELOPE_VERSION: Final[str] = "1.0.0"


class ErrorEnvelope(BaseModel):
    """One `WeftError`, whole, for a script — see the module docstring for what each field is
    and why. Constructed only by `build_error_envelope` below; nothing else in this tree
    hand-assembles one, so every emitting site stays identical by construction.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: Which line shape this is — ledger task **6.16**, `weft_cli.sinks.LineKind`. `weft --json`
    #: writes `StreamEvent` lines and this, on one descriptor, and a consumer must not have to
    #: tell them apart by which keys are present: a `StreamEvent` whose `type` is `ERROR` and an
    #: `ErrorEnvelope` are both "an error" in different shapes. Additive under `09` §3, which is
    #: why it may be added at all — `envelope_version` does not move for a new field.
    kind: LineKind = LineKind.ERROR_ENVELOPE
    envelope_version: str = ENVELOPE_VERSION
    error: str
    rendered: str
    exit_code: ExitCode
    valid_options: tuple[str, ...] | None = None
    pack: str | None = None
    contract: str | None = None
    plugin: str | None = None
    stage: str | None = None


def build_error_envelope(exc: WeftError, *, exit_code: ExitCode) -> ErrorEnvelope:
    """The one place a `WeftError` becomes an `ErrorEnvelope` — see the module docstring.

    `exit_code` is a parameter rather than re-derived here because both call sites already
    have to compute it for the process's own exit status (`weft_cli.exit_codes.exit_code_for`,
    or `CommandRefusalError.exit_code`); a second computation here would be the "two sources of
    truth for the exit code" this task's own brief warns against — `weft_cli.render.
    render_refusal` and `weft_cli.exit_codes.exit_code_for` already own that mapping between
    them, and this function is not a third.
    """
    valid_options = exc.valid_options if isinstance(exc, UnresolvedNameError) else None
    return ErrorEnvelope(
        error=type(exc).__name__,
        rendered=str(exc),
        exit_code=exit_code,
        valid_options=valid_options,
        pack=exc.pack,
        contract=exc.contract,
        plugin=exc.plugin,
        stage=exc.stage,
    )


__all__ = ["ENVELOPE_VERSION", "ErrorEnvelope", "build_error_envelope"]
