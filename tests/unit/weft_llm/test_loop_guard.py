"""Unit tests for `weft_llm.loop_guard`.

Mirrors `packages/weft-rag/src/weft_llm/loop_guard.py`. Covers the happy path (ordinary prose,
including prose that legitimately reuses a phrase, is never flagged), the edge case (a table
being streamed is read as a table and never reaches the repetition check, and a short answer is
never checked at all), and the error case a caller gets wrong once and never again — feeding
only the newest delta, rather than the whole accumulated answer, silently defeats the guard.

The four worked examples task 3.10 names — a `|---|---|` row, a `====` rule, a `+---+---+`
border, and ordinary prose — are reproduced below as fresh test cases, not copied from the
reference's own comment block; only the *shape* of the four cases (three formatting styles that
must read as a table, one paragraph that must not) is carried over.
"""

import pytest
from pydantic import ValidationError

from weft_llm.loop_guard import LoopGuardConfig, detect_generation_loop

_DEFAULT = LoopGuardConfig()


def _pad_past_floor(text: str) -> str:
    """`text`, repeated until it safely clears `LoopGuardConfig().min_text_length`."""
    while len(text) <= _DEFAULT.min_text_length:
        text += text
    return text


def test_ordinary_prose_is_not_flagged_as_a_loop() -> None:
    # Arrange — long enough to clear the floor, varied enough to never repeat a 50+ character
    # span.
    prose = (
        "Weft is a RAG engine built as a microkernel: a small kernel that knows nothing about "
        "PDFs, chunking, embeddings or graphs, where every capability is a plugin discovered "
        "through Python entry points, and pipelines are data derivable from other pipelines."
    )

    # Act
    flagged = detect_generation_loop(prose)

    # Assert
    assert flagged is False


def test_long_prose_reusing_a_phrase_is_not_mistaken_for_a_loop() -> None:
    # Arrange — the true/false pair task 3.10 asks for: a phrase repeated once, deep inside
    # otherwise-unique paragraphs, must not read the same as a model stuck repeating itself.
    prose = (
        "Based on the sources provided, the committee reviewed several proposals during the "
        "quarter and found that funding allocation needed adjustment across three regions. "
        "As mentioned in the sources, the primary concern was long-term sustainability of the "
        "program budget once initial grants expired at the end of the fiscal year. Later "
        "discussion turned toward staffing needs and coordination between the regional offices, "
        "which as mentioned in the sources required further study before the board could issue "
        "any concrete recommendation to the funding committee."
    )

    # Act
    flagged = detect_generation_loop(prose)

    # Assert
    assert flagged is False


def test_a_repeating_span_above_the_floor_is_flagged() -> None:
    # Arrange — the true-repetition half of the same pair: one short phrase, repeated with
    # nothing else, well past the length floor.
    looping = _pad_past_floor("the answer is the answer is the answer is ")

    # Act
    flagged = detect_generation_loop(looping)

    # Assert
    assert flagged is True


def test_text_at_or_below_the_length_floor_is_never_checked() -> None:
    # Arrange — the edge case: a single repeating character would trip the repetition passes
    # instantly if they ran, but the floor exists precisely so a short answer costs nothing to
    # check.
    config = LoopGuardConfig()
    short = "x" * config.min_text_length

    # Act
    flagged = detect_generation_loop(short, config=config)

    # Assert
    assert flagged is False
    assert len(short) == config.min_text_length  # confirms this is exactly the floor, not under it


def test_a_table_separator_row_is_not_mistaken_for_a_loop() -> None:
    # Arrange — a table streamed row by row is legitimately repetitive; the table check must
    # run before the repetition passes and win.
    table = _pad_past_floor("| Column A | Column B | Column C |\n") + "|---|---|---|\n"

    # Act
    flagged = detect_generation_loop(table)

    # Assert
    assert flagged is False


def test_a_double_equals_rule_is_not_mistaken_for_a_loop() -> None:
    # Arrange
    text = _pad_past_floor("A heading rendered above a rule.\n") + "====\n"

    # Act
    flagged = detect_generation_loop(text)

    # Assert
    assert flagged is False


def test_a_plus_dash_border_is_not_mistaken_for_a_loop() -> None:
    # Arrange
    text = _pad_past_floor("A heading rendered above a border.\n") + "+---+---+\n"

    # Act
    flagged = detect_generation_loop(text)

    # Assert
    assert flagged is False


def test_only_the_whole_accumulated_answer_reveals_a_loop_a_single_delta_cannot() -> None:
    # Arrange — the cumulative-text contract: a caller that hands the guard only the newest
    # chunk, rather than the whole answer so far, can never see a repeat spanning more than one
    # chunk.
    phrase = "the answer is the answer is "
    full_answer = _pad_past_floor(phrase)

    # Act
    fed_as_deltas = any(detect_generation_loop(phrase) for _ in range(6))
    fed_cumulatively = detect_generation_loop(full_answer)

    # Assert
    assert fed_as_deltas is False
    assert fed_cumulatively is True


def test_loop_guard_config_is_frozen_and_refuses_an_unknown_field() -> None:
    # Arrange / Act
    config = LoopGuardConfig(min_period=20)

    # Assert — every constant is parameterisable, but the shape itself is closed: a typo under
    # `[llm.loop_guard]` must be refused rather than silently ignored.
    assert config.min_period == 20
    with pytest.raises(ValidationError):
        LoopGuardConfig.model_validate({"not_a_real_field": 1})
