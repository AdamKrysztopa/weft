"""Re-indexing with a different pipeline is visible — ledger task `9.17`.

`SourceRecord` has carried `content_hash` since G4 and `pipeline` since ledger 6.24, and `02` §1
says what they are for: *"`pipeline` is what lets `weft index` say 'already indexed, by a different
pipeline' rather than silently skipping or silently duplicating."* Measured 2026-09-06: **nothing
compares either one.** Every use in `packages/` is a write, a read-back into a model, or a copy —
`docs/lessons.md` `L9.37`, confirmed independently by the survey for this task.

**What the task's own framing gets slightly wrong, corrected here rather than inherited.** `9.17`
says the risk is *"silently keeping whichever parse arrived first"*. It is not — node ids are
content digests (`weft_kernel.payload.node._content_digest`), so a different parse produces
*different* ids and `ON CONFLICT (id)` never fires: the old nodes and the new nodes **coexist**,
both retrievable, and the source row is overwritten so nothing records that the corpus was ever
built another way. Not "the first wins" — "both win, and the evidence is gone". That is worse, and
it is `L9.37`'s finding.

**This task makes it visible; it does not make it clean.** Removing the stale nodes is a deletion
on the ingest path and a larger change than this line asks for — `L9.37` says it "owes a ledger task
before it owes a rule", and that task is not this one. What lands here is the comparison and the
report, so an operator learns at the moment it happens rather than from a retrieval that quietly
mixes two parses.
"""

from datetime import UTC, datetime

from weft_cli.ingest import SourceChange, changes_against_records
from weft_extract.contract import SourceDoc
from weft_kernel.payload import SourceId
from weft_store import SourceRecord

_NOW = datetime(2026, 9, 6, tzinfo=UTC)


def _doc(content: bytes = b"hello") -> SourceDoc:
    return SourceDoc(source_id=SourceId("s-1"), uri="file:///a.txt", content=content)


def _record(*, content_hash: str, identity: str) -> SourceRecord:
    return SourceRecord(
        id=SourceId("s-1"),
        uri="file:///a.txt",
        content_hash=content_hash,
        indexed_at=_NOW,
        pipeline="index-text",
        pipeline_identity=identity,
    )


def _hash_of(content: bytes) -> str:
    import hashlib

    return hashlib.sha256(content).hexdigest()


def test_a_source_nothing_has_indexed_before_is_new() -> None:
    """The first index of anything, and the case every existing corpus is in."""
    # Act / Assert
    assert changes_against_records([_doc()], {}, identity="abc") == {
        SourceId("s-1"): SourceChange.NEW
    }


def test_the_same_bytes_through_the_same_pipeline_is_unchanged() -> None:
    """The common re-index, and the one an operator wants to hear nothing about."""
    # Arrange
    doc = _doc()
    records = {doc.source_id: _record(content_hash=_hash_of(doc.content), identity="abc")}

    # Act / Assert
    assert changes_against_records([doc], records, identity="abc") == {
        doc.source_id: SourceChange.UNCHANGED
    }


def test_different_bytes_through_the_same_pipeline_is_a_changed_document() -> None:
    """The document was edited. Distinct from a reparse, because the *source* moved."""
    # Arrange
    doc = _doc(b"edited")
    records = {doc.source_id: _record(content_hash=_hash_of(b"original"), identity="abc")}

    # Act / Assert
    assert changes_against_records([doc], records, identity="abc") == {
        doc.source_id: SourceChange.CONTENT_CHANGED
    }


def test_the_same_bytes_through_a_different_pipeline_is_a_reparse() -> None:
    """9.17's own case: the file did not move, the parser or the model did.

    This is the one that was invisible — the source row is overwritten and the old nodes stay.
    """
    # Arrange
    doc = _doc()
    records = {doc.source_id: _record(content_hash=_hash_of(doc.content), identity="old")}

    # Act / Assert
    assert changes_against_records([doc], records, identity="new") == {
        doc.source_id: SourceChange.PIPELINE_CHANGED
    }


def test_both_changing_at_once_reports_the_document_rather_than_the_pipeline() -> None:
    """An edited file through a new pipeline is re-parsed either way, so the reason an operator
    needs is the one they can act on: the document moved. Reporting the pipeline here would send
    someone looking for a configuration change that is not the interesting fact.
    """
    # Arrange
    doc = _doc(b"edited")
    records = {doc.source_id: _record(content_hash=_hash_of(b"original"), identity="old")}

    # Act / Assert
    assert changes_against_records([doc], records, identity="new") == {
        doc.source_id: SourceChange.CONTENT_CHANGED
    }


def test_a_record_written_before_this_task_reports_a_reparse_rather_than_unchanged() -> None:
    """The upgrade case, and the honest answer for it.

    Every `SourceRecord` already on disk has an empty `pipeline_identity`, because the field did
    not exist when it was written. That is not evidence the pipeline is unchanged — it is the
    absence of evidence, and `02` §1's own rule is that an empty answer is never a fact about the
    world. Reporting `UNCHANGED` here would claim a comparison nobody made.
    """
    # Arrange
    doc = _doc()
    records = {doc.source_id: _record(content_hash=_hash_of(doc.content), identity="")}

    # Act / Assert
    assert changes_against_records([doc], records, identity="abc") == {
        doc.source_id: SourceChange.PIPELINE_CHANGED
    }


def test_a_record_for_a_source_this_run_did_not_see_is_not_reported() -> None:
    """`weft index` reports on what it indexed. A source elsewhere in the corpus is not its news."""
    # Arrange
    other = SourceRecord(
        id=SourceId("s-2"),
        uri="file:///b.txt",
        content_hash="whatever",
        indexed_at=_NOW,
        pipeline="index-text",
        pipeline_identity="abc",
    )

    # Act
    changes = changes_against_records([_doc()], {other.id: other}, identity="abc")

    # Assert
    assert set(changes) == {SourceId("s-1")}


def test_the_record_a_run_writes_carries_the_identity_it_ran_under() -> None:
    """Otherwise the next run compares against nothing and every re-index reports a reparse."""
    # Act
    record = SourceRecord(
        id=SourceId("s-1"),
        uri="file:///a.txt",
        content_hash="h",
        indexed_at=_NOW,
        pipeline="index-text",
        pipeline_identity="abc",
    )

    # Assert
    assert record.pipeline_identity == "abc"


def test_the_identity_field_defaults_empty_so_every_existing_writer_keeps_working() -> None:
    """Additive for both of G9's audiences — `STORE_CONTRACT_VERSION` moves one minor."""
    # Act
    record = SourceRecord(
        id=SourceId("s-1"),
        uri="file:///a.txt",
        content_hash="h",
        indexed_at=_NOW,
        pipeline="index-text",
    )

    # Assert
    assert record.pipeline_identity == ""
