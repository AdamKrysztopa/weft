"""Unit tests for `scripts/bench_vectors.py` — Phase 29 task **29.6**.

The real-embedder vector set: about 970 pinned arXiv PDFs, 100,000 chunks, embedded once through
`text-embedding-3-large` (`fix-plans/07` Q-A, settled 2026-09-15). Everything here runs with no
network, no database and no credential. The parts that need those — `select`, `fetch`, `sketch`,
`embed`, `load` — are driven through the shipped binary and are checked by running them; what these
tests pin is the part a run cannot show being wrong: the name, the price, the prefix, the pin and
the file that must reload byte-for-byte.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import bench_vectors
import numpy as np
import numpy.typing as npt
import pytest

#: The shape of the PMC Open Access bucket's listing, measured 2026-09-15 on `pmc-oa-opendata`:
#: `ListObjectsV2` with `delimiter=/` answers one `CommonPrefixes` entry per versioned article, and
#: a truncated page carries the token that continues it.
_S3_PAGE = b"""<?xml version="1.0" encoding="UTF-8"?>
<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">
  <Name>pmc-oa-opendata</Name><Prefix></Prefix><KeyCount>2</KeyCount>
  <IsTruncated>true</IsTruncated>
  <NextContinuationToken>token-2</NextContinuationToken>
  <CommonPrefixes><Prefix>PMC11000012.1/</Prefix></CommonPrefixes>
  <CommonPrefixes><Prefix>PMC11000013.2/</Prefix></CommonPrefixes>
</ListBucketResult>
"""

_LAST_S3_PAGE = b"""<?xml version="1.0" encoding="UTF-8"?>
<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">
  <IsTruncated>false</IsTruncated>
  <CommonPrefixes><Prefix>PMC11000020.1/</Prefix></CommonPrefixes>
</ListBucketResult>
"""


def _article(**overrides: object) -> bench_vectors.PmcArticle:
    # Field names and values copied from `pmc-oa-opendata/PMC10000014.1/PMC10000014.1.json`.
    fields: dict[str, object] = {
        "pmcid": "PMC11000012",
        "version": 1,
        "is_pmc_openaccess": True,
        "is_retracted": False,
        "is_historical_ocr": False,
        "license_code": "CC BY",
        "pdf_url": "s3://pmc-oa-opendata/PMC11000012.1/PMC11000012.1.pdf?md5=b5b41ab219fdd0c6",
    }
    fields.update(overrides)
    return bench_vectors.PmcArticle.model_validate(fields)


# --- naming -------------------------------------------------------------------------------------


def test_the_name_is_the_input_digest_the_model_the_width_and_the_date() -> None:
    # Arrange
    pdfs = ("b" * 64, "a" * 64)

    # Act
    digest = bench_vectors.input_digest(pdfs)
    name = bench_vectors.vector_set_name(
        digest, bench_vectors.EmbeddingModel.LARGE, 3072, date(2026, 9, 15)
    )

    # Assert
    assert digest == bench_vectors.input_digest(tuple(reversed(pdfs)))
    assert digest != bench_vectors.input_digest(("a" * 64, "c" * 64))
    assert name == f"{digest[:12]}-text-embedding-3-large-3072-2026-09-15"


# --- the price, printed before the spend --------------------------------------------------------


def test_the_sketch_prices_the_billed_tokens_at_the_models_published_rate(
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Act
    sketch = bench_vectors.sketch_cost(
        pdfs=970, chunks=100_000, tokens=15_600_000, model=bench_vectors.EmbeddingModel.LARGE
    )
    bench_vectors.print_sketch(sketch)

    # Assert
    printed = capsys.readouterr().out
    assert bench_vectors.EmbeddingModel.LARGE.usd_per_million == Decimal("0.13")
    assert bench_vectors.EmbeddingModel.SMALL.usd_per_million == Decimal("0.02")
    assert sketch.usd == Decimal("2.028")
    assert "pdfs: 970" in printed
    assert "chunks: 100,000" in printed
    assert "billed tokens: 15,600,000" in printed
    assert "price: $2.03" in printed
    assert "model: text-embedding-3-large" in printed


def test_an_unknown_model_is_refused_naming_the_ones_that_are_priced() -> None:
    with pytest.raises(bench_vectors.UnknownEmbeddingModelError) as caught:
        bench_vectors.model_named("text-embedding-ada-002")

    message = str(caught.value)
    assert "text-embedding-ada-002" in message
    assert "text-embedding-3-large" in message
    assert "text-embedding-3-small" in message


# --- which PDFs make the set --------------------------------------------------------------------


def test_the_selection_is_the_shortest_manifest_order_prefix_reaching_the_target() -> None:
    # Arrange — manifest order, not size order: the largest document is last.
    counts = (
        ("2401.00001v1", 40),
        ("2401.00002v1", 35),
        ("2401.00003v1", 30),
        ("2401.00004v1", 90),
    )

    # Act
    chosen = bench_vectors.select_prefix(counts, target=100)

    # Assert
    assert chosen == ("2401.00001v1", "2401.00002v1", "2401.00003v1")


def test_a_fetched_set_too_small_for_the_target_is_refused_with_both_numbers() -> None:
    counts = (("2401.00001v1", 40), ("2401.00002v1", 35))

    with pytest.raises(bench_vectors.InsufficientCorpusError, match=r"75 chunks.*100,000"):
        bench_vectors.select_prefix(counts, target=100_000)


# --- the pinned PDFs ----------------------------------------------------------------------------


def test_a_bucket_page_yields_each_versioned_article_and_the_token_that_continues_it() -> None:
    # Act
    page = bench_vectors.parse_s3_listing(_S3_PAGE)
    last = bench_vectors.parse_s3_listing(_LAST_S3_PAGE)

    # Assert
    assert page == bench_vectors.S3Page(
        articles=("PMC11000012.1", "PMC11000013.2"), continuation="token-2"
    )
    assert last == bench_vectors.S3Page(articles=("PMC11000020.1",), continuation=None)


@pytest.mark.parametrize(
    ("overrides", "admitted"),
    [
        ({}, True),
        ({"license_code": "CC0"}, True),
        ({"license_code": "CC BY-NC"}, False),
        ({"is_retracted": True}, False),
        ({"is_pmc_openaccess": False}, False),
        ({"is_historical_ocr": True}, False),
        ({"pdf_url": None}, False),
    ],
)
def test_an_article_is_admitted_only_when_open_licensed_live_and_carrying_a_pdf(
    overrides: dict[str, object], admitted: bool
) -> None:
    assert bench_vectors.admitted(_article(**overrides)) is admitted


def test_an_article_is_pinned_to_the_pdf_under_its_versioned_prefix() -> None:
    # Act
    document = bench_vectors.document_for("PMC11000013.2")

    # Assert — the `.2` is the revision, and the key cannot hold different bytes under it.
    assert document == bench_vectors.BenchDocument(
        id="PMC11000013.2",
        source="https://pmc-oa-opendata.s3.amazonaws.com/PMC11000013.2/PMC11000013.2.pdf",
        sha256="",
    )


def test_the_manifest_round_trips_through_its_file(tmp_path: Path) -> None:
    # Arrange
    manifest = tmp_path / "bench-pdfs.toml"
    documents = (
        bench_vectors.BenchDocument(
            id="2401.00017v2", source="https://arxiv.org/pdf/2401.00017v2", sha256="1" * 64
        ),
        bench_vectors.BenchDocument(
            id="2401.00123v1", source="https://arxiv.org/pdf/2401.00123v1", sha256=""
        ),
    )

    # Act
    bench_vectors.write_manifest(manifest, documents, query="cat:cs.IR")
    loaded = bench_vectors.load_manifest(manifest)

    # Assert
    assert loaded == documents


def test_a_first_fetch_pins_the_digest_and_a_later_one_must_match_it() -> None:
    # Arrange
    unpinned = bench_vectors.BenchDocument(
        id="2401.00017v2", source="https://arxiv.org/pdf/2401.00017v2", sha256=""
    )
    body = b"%PDF-1.5 synthetic"

    # Act
    pinned = bench_vectors.pin_or_verify(unpinned, body)

    # Assert
    assert pinned.sha256 != ""
    assert bench_vectors.pin_or_verify(pinned, body) == pinned
    with pytest.raises(bench_vectors.PinMismatchError) as caught:
        bench_vectors.pin_or_verify(pinned, b"%PDF-1.5 different bytes")
    assert "2401.00017v2" in str(caught.value)
    assert pinned.sha256[:16] in str(caught.value)


# --- the vector set on disk ---------------------------------------------------------------------


def _tables() -> tuple[bench_vectors.TableDump, ...]:
    return (
        bench_vectors.TableDump(
            name="weft_nodes",
            columns=("id", "content", "ext"),
            rows=(("n1", "first chunk", '{"a": 1}'), ("n2", "second chunk", None)),
        ),
        bench_vectors.TableDump(
            name="weft_sources", columns=("source_id", "status"), rows=(("/x.pdf", "active"),)
        ),
    )


def _vectors() -> npt.NDArray[np.float32]:
    # Values exactly representable in float32, so equality is the honest comparison.
    return np.array([[0.5, -0.25, 1.0], [0.125, 0.0, -1.0]], dtype=np.float32)


def test_a_vector_set_reloads_exactly_what_was_written(tmp_path: Path) -> None:
    # Arrange
    vectors = _vectors()

    # Act
    written = bench_vectors.write_vector_set(
        tmp_path,
        input_digest="d" * 64,
        model=bench_vectors.EmbeddingModel.LARGE,
        width=3,
        day=date(2026, 9, 15),
        billed_tokens=321,
        pdfs=1,
        tables=_tables(),
        vectors=vectors,
    )
    reloaded = bench_vectors.read_vector_set(tmp_path / written.meta.name)
    loaded = bench_vectors.open_vectors(tmp_path / written.meta.name, reloaded.meta)

    # Assert — a memory map, because the real set is 100,000 x 3072 and must not become Python
    # floats on every reload (`L22.28`).
    assert reloaded == written
    assert reloaded.meta.rows == 2
    assert reloaded.meta.name == f"{'d' * 12}-text-embedding-3-large-3-2026-09-15"
    assert isinstance(loaded, np.memmap)
    assert loaded.dtype == np.float32
    assert loaded.shape == (2, 3)
    assert np.array_equal(loaded, vectors)


def test_a_tampered_vectors_file_is_refused_by_name(tmp_path: Path) -> None:
    # Arrange
    written = bench_vectors.write_vector_set(
        tmp_path,
        input_digest="d" * 64,
        model=bench_vectors.EmbeddingModel.LARGE,
        width=3,
        day=date(2026, 9, 15),
        billed_tokens=321,
        pdfs=1,
        tables=_tables(),
        vectors=_vectors(),
    )
    vectors_file = tmp_path / written.meta.name / "vectors.f32"
    data = bytearray(vectors_file.read_bytes())
    data[0] ^= 0xFF
    vectors_file.write_bytes(bytes(data))

    # Act / Assert
    with pytest.raises(bench_vectors.VectorSetCorruptError, match=r"vectors\.f32"):
        bench_vectors.read_vector_set(tmp_path / written.meta.name)


def test_vectors_whose_width_disagrees_with_the_set_are_refused_with_both_widths(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match=r"width 3.*2 components"):
        bench_vectors.write_vector_set(
            tmp_path,
            input_digest="d" * 64,
            model=bench_vectors.EmbeddingModel.LARGE,
            width=3,
            day=date(2026, 9, 15),
            billed_tokens=321,
            pdfs=1,
            tables=_tables(),
            vectors=np.array([[0.5, -0.25], [0.125, 0.0]], dtype=np.float32),
        )
