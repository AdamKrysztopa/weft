"""`weft eval experiment` says where it is while it runs — carried repair **R43.58**.

43.53's paid run wrote no line for 25 minutes and was watched through open sockets (`L28.66`).
Progress is counted in work done: questions attempted by the current arm and repetition, and the
start and end of judging them. It reaches the operator the way `weft index`'s batch progress does
— an optional method on the sink, `experiment_progress`, which the text sink prints to its progress
stream, the `--json` sink writes as one `experiment-progress` line, and a sink without it never
receives.
"""

from __future__ import annotations

import io
import json

from weft_cli.cli import _EmissionTrackingSink  # pyright: ignore[reportPrivateUsage]
from weft_cli.progress import (
    ExperimentProgress,
    ExperimentProgressReporter,
    ScoringStage,
)
from weft_cli.sinks import JsonSink, LineKind, PrintingSink
from weft_llm.client import NullSink
from weft_llm.payload import TokenChunk


def _event(done: int = 120, stage: ScoringStage = ScoringStage.ANSWERING) -> ExperimentProgress:
    return ExperimentProgress(
        experiment="musique-retrieval",
        arm="multi-query",
        arm_number=3,
        arms=5,
        repetition=1,
        repetitions=2,
        stage=stage,
        done=done,
        total=600,
        seconds=840.0,
    )


async def test_the_text_sink_prints_where_the_run_is_to_its_progress_stream() -> None:
    # Arrange
    answer, progress = io.StringIO(), io.StringIO()
    sink = PrintingSink(stream=answer, progress_stream=progress)

    # Act
    await sink.experiment_progress(_event())

    # Assert
    line = progress.getvalue()
    assert "arm 3/5 multi-query" in line
    assert "repetition 1/2" in line
    assert "answering 120/600" in line
    assert answer.getvalue() == ""


async def test_the_json_sink_writes_one_experiment_progress_line() -> None:
    # Arrange
    stream = io.StringIO()
    sink = JsonSink(stream=stream)

    # Act
    await sink.experiment_progress(_event(stage=ScoringStage.JUDGING, done=0))

    # Assert
    [line] = [json.loads(raw) for raw in stream.getvalue().splitlines()]
    assert line["kind"] == LineKind.EXPERIMENT_PROGRESS == "experiment-progress"
    assert (line["arm"], line["stage"], line["done"], line["total"]) == (
        "multi-query",
        "judging",
        0,
        600,
    )


async def test_the_command_wrapper_forwards_progress_and_drops_it_for_a_quiet_sink() -> None:
    # Arrange
    stream = io.StringIO()
    shown = _EmissionTrackingSink(JsonSink(stream=stream))
    quiet = _EmissionTrackingSink(NullSink())

    # Act
    await shown.experiment_progress(_event())
    await quiet.experiment_progress(_event())

    # Assert
    assert '"kind":"experiment-progress"' in stream.getvalue()
    assert not shown.emitted


def test_a_sink_that_only_emits_is_not_a_progress_reporter() -> None:
    # Arrange
    class _EmitOnly:
        async def emit(self, chunk: TokenChunk) -> None: ...

        async def close(self, *, reason: str | None = None) -> None: ...

    # Assert
    assert not isinstance(_EmitOnly(), ExperimentProgressReporter)
    assert isinstance(PrintingSink(), ExperimentProgressReporter)
    assert isinstance(JsonSink(), ExperimentProgressReporter)
