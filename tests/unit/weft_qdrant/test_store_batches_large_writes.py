"""`QdrantStore.add` bounds the size of the requests it issues — carried repair **R31.10**.

**Why this is a unit test with a recording double, when every other test of this store runs
against the real container.** The property is *how many requests are issued and how large each
one is*, which a live server cannot report and which is true regardless of whether a server is
reachable. `tests/unit/weft_qdrant/test_store.py` owns the behaviour that needs a real Qdrant;
this owns the one fact that does not.

**What it is for.** `weft_cli/ingest.py` hands the store the whole corpus as a single batch —
"every `SourceDoc` `discover_source_docs` finds is handed to `Runner.run` as the single element of
its batch iterator" — so `add` is routinely called with every node in the corpus at once. On
2026-09-16 that was 169,223 nodes, and `31.6`'s measurement died twice inside this method: once
with the client's default timeout and again with `timeout_seconds` raised to 900. Both times the
error reaching the operator was `'store' failed: ` with no message, which is `R31.9`.

Both calls are bounded, not just the write. `retrieve` runs **first**, carrying one id per node,
and an unbounded read is as unsendable as an unbounded write — the failure was reached before the
upsert on either attempt, so a repair that chunked only the upsert would have fixed nothing.
"""

from collections.abc import Sequence
from typing import Any

import pytest

from weft_kernel.payload import MediaType, Node, Vector
from weft_qdrant import QdrantSettings, QdrantStore

_WIDTH = 2
#: Comfortably more than any sane batch size, so "more than one request" is a real claim rather
#: than an accident of where the boundary happens to fall.
_NODES = 2_500


class _RecordingClient:
    """Counts the ids and points each call carries, and answers nothing else.

    Deliberately not a `Mock`: what this asserts is arithmetic over call sizes, and a double that
    returns real, empty results keeps `add`'s own merge logic running rather than stubbing out the
    method under test.
    """

    def __init__(self) -> None:
        self.retrieved: list[int] = []
        self.upserted: list[int] = []
        self.points_seen: list[str] = []

    async def retrieve(self, _collection: str, **kwargs: Any) -> Sequence[object]:
        self.retrieved.append(len(kwargs["ids"]))
        return []

    async def upsert(self, _collection: str, **kwargs: Any) -> None:
        points = kwargs["points"]
        self.upserted.append(len(points))
        self.points_seen.extend(str(point.id) for point in points)


def _nodes(count: int) -> list[Node]:
    return [
        Node.synthetic(
            content=f"passage {index}", media_type=MediaType.TEXT, reason="test fixture"
        ).with_embedding(Vector(values=(float(index), 1.0)))
        for index in range(count)
    ]


@pytest.fixture
def recording(monkeypatch: pytest.MonkeyPatch) -> tuple[QdrantStore, _RecordingClient]:
    settings = QdrantSettings(url="http://localhost:6333", collection="unused", vector_size=_WIDTH)
    store = QdrantStore(settings)
    client = _RecordingClient()

    async def _connection(self: QdrantStore) -> _RecordingClient:
        del self
        return client

    monkeypatch.setattr(QdrantStore, "_connection", _connection)
    return store, client


async def test_a_corpus_sized_add_is_split_across_several_upserts(
    recording: tuple[QdrantStore, _RecordingClient],
) -> None:
    # Arrange — one `add` carrying far more nodes than one request should hold, which is what
    # `weft index` does on every run: the whole corpus arrives as a single batch.
    store, client = recording

    # Act
    await store.add(_nodes(_NODES))

    # Assert
    assert len(client.upserted) > 1, (
        f"every one of {_NODES} points went out in a single upsert; a corpus-sized write has to "
        "be split or it is unsendable (R31.10)"
    )
    assert max(client.upserted) < _NODES


async def test_the_read_that_precedes_the_write_is_split_too(
    recording: tuple[QdrantStore, _RecordingClient],
) -> None:
    # `retrieve` runs before `upsert` and carries one id per node, so it is reached first and is
    # the call the 2026-09-16 run actually died in.
    store, client = recording

    await store.add(_nodes(_NODES))

    assert len(client.retrieved) > 1, (
        f"all {_NODES} ids were retrieved in one request; the read is as unbounded as the write "
        "and is issued first (R31.10)"
    )
    assert max(client.retrieved) < _NODES


async def test_splitting_writes_every_point_exactly_once(
    recording: tuple[QdrantStore, _RecordingClient],
) -> None:
    # The failure mode a naive chunking introduces: a dropped or duplicated slice. Batching that
    # loses a point is worse than not batching, because the run still reports success.
    store, client = recording

    await store.add(_nodes(_NODES))

    assert sum(client.upserted) == _NODES
    assert len(set(client.points_seen)) == _NODES
