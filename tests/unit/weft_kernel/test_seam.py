"""Unit tests for `weft_kernel.seam`.

Mirrors `packages/weft-kernel/src/weft_kernel/seam.py`. Covers the concerns
`wrap` applies without the author asking: a span carrying the derived name
and attributes, `__transient__` stripped from a produced `Node`, every NUL
byte a produced `Node`'s `content` or ext `str` fields carry replaced with a
space and counted on that same span, an unrelated exception attributed and
re-raised with `__cause__` preserved, and `CancelledError` propagating
unwrapped rather than being caught and rewritten.

Span assertions use a hand-rolled tracer double, not the OpenTelemetry SDK:
`weft-kernel` ships only `opentelemetry-api` (fitness function 1), whose
default tracer is a no-op, so a real span never has content to assert on.
Substituting a recording double at the same seam `wrap` calls through tests
exactly what this module is responsible for — that it calls the tracer
correctly — without pulling in the SDK to test a promise the SDK, not this
module, keeps.

**Task 5.2e** adds `warn_deprecated` on its own: one `DeprecationWarning` per buffered
`Deprecation`, in order, and an empty buffer warning of nothing — the coverage
`weft_kernel.discovery`'s own test file exercises through `discover()` end to end.
"""

import asyncio
import time
import warnings
from collections.abc import Generator
from contextlib import contextmanager

import pytest
from pydantic import Field, ValidationError

from weft_kernel import seam
from weft_kernel.blocking import BlockingCallError
from weft_kernel.errors import WeftError
from weft_kernel.payload import ExtModel, MediaType, Node, Outcome, Produced, SourceId


class _Secret(ExtModel):
    __namespace__ = "weft-test-secret"
    __schema_version__ = "1.0.0"
    __transient__ = True

    blob: str


class _Kept(ExtModel):
    __namespace__ = "weft-test-kept"
    __schema_version__ = "1.0.0"

    label: str


class _TextField(ExtModel):
    __namespace__ = "weft-test-textfield"
    __schema_version__ = "1.0.0"

    body: str


class _NoWhitespace(ExtModel):
    __namespace__ = "weft-test-nowhitespace"
    __schema_version__ = "1.0.0"

    word: str = Field(pattern=r"^\S+$")


class _RecordingSpan:
    def __init__(self) -> None:
        self.attributes: dict[str, object] = {}

    def set_attribute(self, key: str, value: object) -> None:
        self.attributes[key] = value


class _RecordingTracer:
    def __init__(self) -> None:
        self.spans: list[tuple[str, _RecordingSpan]] = []

    @contextmanager
    def start_as_current_span(self, name: str, **kwargs: object) -> Generator[_RecordingSpan]:
        span = _RecordingSpan()
        self.spans.append((name, span))
        yield span


@pytest.fixture
def tracer(monkeypatch: pytest.MonkeyPatch) -> _RecordingTracer:
    fake = _RecordingTracer()
    monkeypatch.setattr(seam, "_tracer", fake)
    return fake


async def test_wrap_runs_the_call_and_records_a_span(tracer: _RecordingTracer) -> None:
    # Arrange
    async def run(payload: str) -> Outcome[str]:
        return Produced(value=payload.upper())

    wrapped = seam.wrap(run, distribution="weft-chunk", contract="Chunker", plugin="fixed-size")

    # Act
    outcome = await wrapped("hello")

    # Assert
    assert outcome == Produced(value="HELLO")
    [(name, span)] = tracer.spans
    assert name == "Chunker:fixed-size"
    assert span.attributes == {
        "weft.pack": "weft-chunk",
        "weft.contract": "Chunker",
        "weft.plugin": "fixed-size",
        "weft.nul_bytes_removed": 0,
    }


async def test_wrap_strips_transient_ext_from_a_produced_node(tracer: _RecordingTracer) -> None:
    # Arrange
    node = Node.synthetic(
        content="full document text",
        media_type=MediaType.TEXT,
        reason="root of doc-1",
        sources=frozenset({SourceId("doc-1")}),
    )
    node = node.with_ext(_Secret(blob="do-not-persist")).with_ext(_Kept(label="keep-me"))

    async def run() -> Outcome[Node]:
        return Produced(value=node)

    wrapped = seam.wrap(run, distribution="weft-graph", contract="Extractor", plugin="demo")

    # Act
    outcome = await wrapped()

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value.ext_as(_Secret) is None
    assert outcome.value.ext_as(_Kept) == _Kept(label="keep-me")


async def test_wrap_strips_transient_ext_from_a_produced_list_of_nodes(
    tracer: _RecordingTracer,
) -> None:
    # Arrange
    node = Node.synthetic(
        content="chunk one",
        media_type=MediaType.TEXT,
        reason="chunk of doc-1",
        sources=frozenset({SourceId("doc-1")}),
    )
    node = node.with_ext(_Secret(blob="do-not-persist")).with_ext(_Kept(label="keep-me"))

    async def run() -> Outcome[list[Node]]:
        return Produced(value=[node])

    wrapped = seam.wrap(run, distribution="weft-chunk", contract="Chunker", plugin="fixed-size")

    # Act
    outcome = await wrapped()

    # Assert
    assert isinstance(outcome, Produced)
    [stripped] = outcome.value
    assert isinstance(outcome.value, list)
    assert stripped.ext_as(_Secret) is None
    assert stripped.ext_as(_Kept) == _Kept(label="keep-me")


async def test_wrap_sanitizes_nul_bytes_in_produced_node_content(
    tracer: _RecordingTracer,
) -> None:
    # Arrange
    node = Node.synthetic(
        content="page one\x00\x00page two",
        media_type=MediaType.TEXT,
        reason="extracted from doc-1",
        sources=frozenset({SourceId("doc-1")}),
    )

    async def run() -> Outcome[Node]:
        return Produced(value=node)

    wrapped = seam.wrap(run, distribution="weft-pdf", contract="Extractor", plugin="pdf-text")

    # Act
    outcome = await wrapped()

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value.content == "page one  page two"
    assert "\x00" not in outcome.value.content
    [(_name, span)] = tracer.spans
    assert span.attributes["weft.nul_bytes_removed"] == 2


async def test_wrap_sanitizes_nul_bytes_in_an_ext_models_str_field(
    tracer: _RecordingTracer,
) -> None:
    # Arrange — a NUL byte in a non-transient ext model's `str` field, not in `content`.
    node = Node.synthetic(
        content="clean content",
        media_type=MediaType.TEXT,
        reason="extracted from doc-1",
        sources=frozenset({SourceId("doc-1")}),
    ).with_ext(_TextField(body="dirty\x00body"))

    async def run() -> Outcome[Node]:
        return Produced(value=node)

    wrapped = seam.wrap(run, distribution="weft-pdf", contract="Extractor", plugin="pdf-text")

    # Act
    outcome = await wrapped()

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value.content == "clean content"
    assert outcome.value.ext_as(_TextField) == _TextField(body="dirty body")
    [(_name, span)] = tracer.spans
    assert span.attributes["weft.nul_bytes_removed"] == 1


async def test_wrap_raises_when_nul_sanitisation_breaks_an_ext_models_own_constraint(
    tracer: _RecordingTracer,
) -> None:
    # Arrange — a NUL satisfies `_NoWhitespace`'s pattern; the space the sanitiser
    # turns it into does not, so the rebuild must fail loudly rather than smuggle it through.
    node = Node.synthetic(
        content="clean content",
        media_type=MediaType.TEXT,
        reason="extracted from doc-1",
        sources=frozenset({SourceId("doc-1")}),
    ).with_ext(_NoWhitespace(word="dirty\x00word"))

    async def run() -> Outcome[Node]:
        return Produced(value=node)

    wrapped = seam.wrap(run, distribution="weft-pdf", contract="Extractor", plugin="pdf-text")

    # Act / Assert
    with pytest.raises(WeftError) as excinfo:
        await wrapped()

    error = excinfo.value
    assert "_NoWhitespace" in str(error)
    assert isinstance(error.__cause__, ValidationError)


async def test_wrap_returns_the_same_node_object_when_nothing_needs_cleaning(
    tracer: _RecordingTracer,
) -> None:
    # Arrange — no NUL anywhere, and no transient ext, so nothing this seam does should rebuild.
    node = Node.synthetic(
        content="already clean",
        media_type=MediaType.TEXT,
        reason="extracted from doc-1",
        sources=frozenset({SourceId("doc-1")}),
    ).with_ext(_Kept(label="keep-me"))

    async def run() -> Outcome[Node]:
        return Produced(value=node)

    wrapped = seam.wrap(run, distribution="weft-pdf", contract="Extractor", plugin="pdf-text")

    # Act
    outcome = await wrapped()

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value is node
    [(_name, span)] = tracer.spans
    assert span.attributes["weft.nul_bytes_removed"] == 0


async def test_wrap_sanitizes_nul_bytes_in_a_produced_list_of_nodes(
    tracer: _RecordingTracer,
) -> None:
    # Arrange — one dirty node and one clean node in the same batch.
    dirty = Node.synthetic(
        content="dirty\x00page",
        media_type=MediaType.TEXT,
        reason="chunk one of doc-1",
        sources=frozenset({SourceId("doc-1")}),
    )
    clean = Node.synthetic(
        content="clean page",
        media_type=MediaType.TEXT,
        reason="chunk two of doc-1",
        sources=frozenset({SourceId("doc-1")}),
    )

    async def run() -> Outcome[list[Node]]:
        return Produced(value=[dirty, clean])

    wrapped = seam.wrap(run, distribution="weft-pdf", contract="Extractor", plugin="pdf-text")

    # Act
    outcome = await wrapped()

    # Assert
    assert isinstance(outcome, Produced)
    assert isinstance(outcome.value, list)
    [cleaned_dirty, cleaned_clean] = outcome.value
    assert cleaned_dirty.content == "dirty page"
    assert cleaned_clean is clean
    [(_name, span)] = tracer.spans
    assert span.attributes["weft.nul_bytes_removed"] == 1


async def test_wrap_leaves_a_non_node_payload_untouched(tracer: _RecordingTracer) -> None:
    # Arrange — a scalar payload carrying a NUL byte of its own, not wrapped in a `Node`.
    async def run() -> Outcome[str]:
        return Produced(value="not a node\x00at all")

    wrapped = seam.wrap(run, distribution="weft-llm", contract="LLMProvider", plugin="demo")

    # Act
    outcome = await wrapped()

    # Assert
    assert outcome == Produced(value="not a node\x00at all")
    [(_name, span)] = tracer.spans
    assert span.attributes["weft.nul_bytes_removed"] == 0


async def test_wrap_attributes_an_unrelated_exception_and_keeps_its_cause(
    tracer: _RecordingTracer,
) -> None:
    # Arrange
    failure = ValueError("boom")

    async def run() -> Outcome[str]:
        raise failure

    wrapped = seam.wrap(run, distribution="weft-chunk", contract="Chunker", plugin="fixed-size")

    # Act / Assert
    with pytest.raises(WeftError) as excinfo:
        await wrapped()

    error = excinfo.value
    assert (error.pack, error.contract, error.plugin, error.stage) == (
        "weft-chunk",
        "Chunker",
        "fixed-size",
        "Chunker:fixed-size",
    )
    assert error.__cause__ is failure


async def test_wrap_lets_cancelled_error_propagate_unwrapped(tracer: _RecordingTracer) -> None:
    # Arrange
    async def run() -> Outcome[str]:
        raise asyncio.CancelledError

    wrapped = seam.wrap(run, distribution="weft-chunk", contract="Chunker", plugin="fixed-size")

    # Act / Assert
    with pytest.raises(asyncio.CancelledError):
        await wrapped()


async def test_wrap_fills_only_the_attribution_fields_a_pack_left_none(
    tracer: _RecordingTracer,
) -> None:
    # Arrange
    async def run() -> Outcome[str]:
        raise WeftError("library failure", plugin="its-own-name")

    wrapped = seam.wrap(run, distribution="weft-chunk", contract="Chunker", plugin="fixed-size")

    # Act / Assert
    with pytest.raises(WeftError) as excinfo:
        await wrapped()

    error = excinfo.value
    assert (error.pack, error.contract, error.plugin, error.stage) == (
        "weft-chunk",
        "Chunker",
        "its-own-name",
        "Chunker:fixed-size",
    )


async def test_wrap_integrates_the_blocking_guard(tracer: _RecordingTracer) -> None:
    # Arrange
    async def run() -> Outcome[str]:
        time.sleep(0)
        return Produced(value="unreachable")

    wrapped = seam.wrap(run, distribution="weft-chunk", contract="Chunker", plugin="fixed-size")

    # Act / Assert
    with pytest.raises(BlockingCallError) as excinfo:
        await wrapped()

    assert "Chunker:fixed-size" in str(excinfo.value)


async def test_wrap_skips_the_blocking_guard_when_disabled(tracer: _RecordingTracer) -> None:
    # Arrange — task 3.4's O1: `weft_cli.cli.run_command` passes `guard_blocking_calls=False`
    # for a `Command` invocation, which is CLI orchestration with nothing else sharing its event
    # loop to starve, unlike a `Stage` — see that module's own docstring for the argument in
    # full. The same blocking call `test_wrap_integrates_the_blocking_guard` above proves *does*
    # raise by default must run to completion here.
    async def run() -> Outcome[str]:
        time.sleep(0)
        return Produced(value="ok")

    wrapped = seam.wrap(
        run,
        distribution="weft-cli",
        contract="Command",
        plugin="index",
        guard_blocking_calls=False,
    )

    # Act
    outcome = await wrapped()

    # Assert
    assert outcome == Produced(value="ok")


async def test_wrap_still_attributes_an_exception_when_the_guard_is_disabled(
    tracer: _RecordingTracer,
) -> None:
    # Arrange — the property O1 exists to restore: attribution must not depend on the guard
    # being armed, or on an author remembering to add it by hand (CLAUDE.md: cross-cutting
    # concerns live at the registration seam, never in a rule an author must remember).
    async def run() -> Outcome[str]:
        raise WeftError("refused")

    wrapped = seam.wrap(
        run,
        distribution="weft-cli",
        contract="Command",
        plugin="index",
        guard_blocking_calls=False,
    )

    # Act / Assert
    with pytest.raises(WeftError) as excinfo:
        await wrapped()

    error = excinfo.value
    assert (error.pack, error.contract, error.plugin) == ("weft-cli", "Command", "index")


async def test_wrap_uses_a_caller_supplied_stage_label_over_the_contract_plugin_default(
    tracer: _RecordingTracer,
) -> None:
    # Arrange — two pipeline positions naming the same contract and plugin must be
    # distinguishable, which the `contract:plugin` default alone cannot do (`06` step 6).
    async def run(payload: str) -> Outcome[str]:
        return Produced(value=payload)

    wrapped = seam.wrap(
        run,
        distribution="weft-chunk",
        contract="Chunker",
        plugin="fixed-size",
        stage="clean-then-chunk:2",
    )

    # Act
    await wrapped("a")

    # Assert
    [(name, _span)] = tracer.spans
    assert name == "clean-then-chunk:2"


async def test_wrap_attributes_a_failure_with_the_caller_supplied_stage_label(
    tracer: _RecordingTracer,
) -> None:
    # Arrange
    async def run() -> Outcome[str]:
        raise ValueError("boom")

    wrapped = seam.wrap(
        run,
        distribution="weft-chunk",
        contract="Chunker",
        plugin="fixed-size",
        stage="clean-then-chunk:2",
    )

    # Act / Assert
    with pytest.raises(WeftError) as excinfo:
        await wrapped()

    assert excinfo.value.stage == "clean-then-chunk:2"


async def test_wrap_flush_runs_the_call_and_records_a_span(tracer: _RecordingTracer) -> None:
    # Arrange
    flushed: list[str] = []

    async def flush() -> None:
        flushed.append("flushed")

    wrapped = seam.wrap_flush(
        flush, distribution="weft-store", contract="NodeStore", plugin="pgvector", stage="s1"
    )

    # Act
    await wrapped()

    # Assert
    assert flushed == ["flushed"]
    [(name, span)] = tracer.spans
    assert name == "s1:flush"
    assert span.attributes == {
        "weft.pack": "weft-store",
        "weft.contract": "NodeStore",
        "weft.plugin": "pgvector",
    }


async def test_wrap_flush_attributes_an_unrelated_exception_and_keeps_its_cause(
    tracer: _RecordingTracer,
) -> None:
    # Arrange
    failure = ValueError("disk full")

    async def flush() -> None:
        raise failure

    wrapped = seam.wrap_flush(
        flush, distribution="weft-store", contract="NodeStore", plugin="pgvector", stage="s1"
    )

    # Act / Assert
    with pytest.raises(WeftError) as excinfo:
        await wrapped()

    error = excinfo.value
    assert (error.pack, error.contract, error.plugin, error.stage) == (
        "weft-store",
        "NodeStore",
        "pgvector",
        "s1",
    )
    assert error.__cause__ is failure


# --- warn_deprecated (task 5.2e) --------------------------------------------------------


def test_warn_deprecated_emits_one_deprecation_warning_per_notice() -> None:
    # Arrange
    removal = seam.Removal(
        clock=seam.RemovalClock.NEXT_MAJOR,
        distribution="weft-old",
        installed_version="2.3.1",
        release="weft-old 3.0.0",
    )
    notices = (
        seam.Deprecation(
            distribution="weft-old",
            surface="legacy",
            reason="use 'fast' instead",
            removal=removal,
        ),
        seam.Deprecation(
            distribution="weft-old",
            surface="Retriever:slow",
            reason="removed soon",
            removal=removal,
        ),
    )

    # Act
    with pytest.warns(DeprecationWarning) as caught:
        seam.warn_deprecated(notices)

    # Assert
    messages = [str(warning.message) for warning in caught]
    assert messages == [
        "'weft-old' marks 'legacy' deprecated: use 'fast' instead — removed in weft-old 3.0.0",
        "'weft-old' marks 'Retriever:slow' deprecated: removed soon — removed in weft-old 3.0.0",
    ]


def test_warn_deprecated_with_no_notices_warns_of_nothing() -> None:
    # Arrange / Act / Assert — the edge case: an empty buffer is a silent no-op, not an
    # empty warning nobody asked for.
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        seam.warn_deprecated(())


# --- the removal clock (task 6.5) ---------------------------------------------------------
#
# `docs/09-release.md` §3, and G9's own answer 3: "**Releases, not months, and the unit is one
# major of the publishing distribution.** A calendar window needs a cadence promise this project
# does not make... A deprecated surface keeps working, warning at registration, until its
# publisher's next major." So the clock is **derived** from the publishing distribution's own
# installed version and never declared by the author — `CLAUDE.md`'s measured rule, every concern
# an author had to remember decayed. A `removed_in` a pack author types is a number that goes
# stale on the pack's next release with nothing to notice.


def test_the_clock_is_the_publishing_distributions_next_major() -> None:
    """G9's unit, for a distribution that has reached 1.0 and therefore makes the promise."""
    # Arrange / Act
    removal = seam.removal_for("weft-example", version_of=lambda _: "2.3.1")

    # Assert
    assert removal.clock is seam.RemovalClock.NEXT_MAJOR
    assert removal.release == "weft-example 3.0.0"
    assert removal.installed_version == "2.3.1"
    assert removal.describe() == "removed in weft-example 3.0.0"


def test_a_0x_publisher_promises_no_deprecation_period_and_says_so() -> None:
    """G9: "Inside 0.x a contract may move without a deprecation period but never silently."

    The honest answer for a 0.x distribution is not "removed in 1.0.0" — that would promise a
    window 0.x explicitly reserves the right not to give. It is that there is no window, said
    out loud, which is what makes the clock observable rather than invented.
    """
    # Arrange / Act
    removal = seam.removal_for("weft-kernel", version_of=lambda _: "0.1.0")

    # Assert
    assert removal.clock is seam.RemovalClock.UNPROMISED_BEFORE_1_0
    assert removal.release is None
    assert removal.installed_version == "0.1.0"
    assert "0.x" in removal.describe()


def test_an_unreadable_version_is_reported_rather_than_guessed() -> None:
    """`docs/lessons.md` L5.9 — the absence is the answer, and it reaches the reader."""

    # Arrange
    def missing(_: str) -> str:
        raise LookupError("no metadata")

    # Act
    absent = seam.removal_for("weft-ghost", version_of=missing)
    unparseable = seam.removal_for("weft-odd", version_of=lambda _: "not-a-version")

    # Assert
    assert absent.clock is seam.RemovalClock.VERSION_UNREADABLE
    assert absent.installed_version is None
    assert unparseable.clock is seam.RemovalClock.VERSION_UNREADABLE
    assert unparseable.installed_version == "not-a-version"
    assert "unknown" in absent.describe()


def test_a_prerelease_major_still_reads_as_its_major() -> None:
    """`2.0.0rc1` is major 2 — the edge a naive `int(version.split(".")[0])` gets wrong."""
    # Arrange / Act
    removal = seam.removal_for("weft-example", version_of=lambda _: "2.0.0rc1")

    # Assert
    assert removal.clock is seam.RemovalClock.NEXT_MAJOR
    assert removal.release == "weft-example 3.0.0"
