"""A source record says how big the source is — task **44.13** (G29).

`corpus.*` routing features need a corpus's size, and an ask-time count is a scan (G29 rejected
it) while `NodeStore.count()` includes layer nodes (`R44.1`). So `weft index` records, per source,
its leaf count, the characters in those leaves and — when a tokenizer was at hand — their tokens.
`stats is None` means not recorded (every record before this task); `tokens is None` means no
tokenizer was available, never zero.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from weft_kernel.payload import SourceId
from weft_store import (
    STORE_CONTRACT_VERSION,
    SourceRecord,
    SourceStats,
    UnknownSourceStatsError,
    source_stats,
)


def _record(**fields: object) -> SourceRecord:
    return SourceRecord.model_validate(
        {
            "id": SourceId("doc"),
            "uri": "file:///doc.txt",
            "content_hash": "h",
            "indexed_at": datetime.now(UTC),
            "pipeline": "index-text",
            **fields,
        }
    )


def test_a_record_written_before_stats_existed_has_none() -> None:
    # Assert
    assert _record().stats is None


def test_stats_without_a_tokenizer_leave_tokens_unknown() -> None:
    # Act
    record = _record(stats=SourceStats(leaves=3, characters=1200, tokens=None, tokenizer=None))

    # Assert
    assert record.stats is not None
    assert (record.stats.leaves, record.stats.characters) == (3, 1200)
    assert record.stats.tokens is None


def test_a_negative_count_is_refused() -> None:
    # Act / Assert
    with pytest.raises(ValidationError):
        SourceStats(leaves=-1, characters=0, tokens=None, tokenizer=None)


def test_stored_stats_decode_and_absent_stats_read_none() -> None:
    # Act
    decoded = source_stats(
        {"leaves": 2, "characters": 40, "tokens": 11, "tokenizer": "gpt-5.6-luna"}
    )

    # Assert
    assert decoded == SourceStats(leaves=2, characters=40, tokens=11, tokenizer="gpt-5.6-luna")
    assert source_stats(None) is None


def test_a_stats_field_a_newer_release_wrote_is_refused_by_name() -> None:
    # Act / Assert
    with pytest.raises(UnknownSourceStatsError, match="'pages'"):
        source_stats({"leaves": 2, "characters": 40, "tokens": None, "tokenizer": None, "pages": 3})


def test_an_optional_field_on_a_returned_model_is_a_minor() -> None:
    # Assert — `09`'s two-audience row "Add an optional field to a returned model".
    assert STORE_CONTRACT_VERSION == "3.1.0"
