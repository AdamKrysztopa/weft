"""Unit tests for `scripts/dataset_corpora.py` — ledger task **39.7**.

TechQA and ESCI are open datasets (CDLA-Permissive / Apache-2.0) converted into one text file per
document. The conversion must be byte-for-byte reproducible, because `corpus/techqa.toml` and
`corpus/esci.toml` pin every file's sha256 and `fetch_corpus.py verify` holds the materialised
corpus to them. These tests pin the two renderings; the parquet reading around them is a thin loop.
"""

from __future__ import annotations

from dataset_corpora import esci_document, techqa_document, techqa_document_id


def test_a_technote_is_its_title_then_its_body_on_the_next_line() -> None:
    # Act
    rendered = techqa_document("Title:  Fix Pack 6 notes \n\nText:\nApply the fix.\n\nText:\nlater")

    # Assert — split at the first marker only; a second "Text:" belongs to the body.
    assert rendered == "Fix Pack 6 notes\nApply the fix.\n\nText:\nlater"


def test_a_technote_without_the_marker_keeps_its_whole_text_under_an_empty_title() -> None:
    # Act
    rendered = techqa_document("no marker here")

    # Assert
    assert rendered == "\nno marker here"


def test_a_technote_id_drops_the_beir_txt_suffix() -> None:
    # Act / Assert
    assert techqa_document_id("swg21996508.txt") == "swg21996508"


def test_a_product_is_its_non_empty_fields_one_per_line_with_markup_removed() -> None:
    # Arrange
    row = {
        "product_title": "Galaxy S3 Battery ",
        "product_brand": "",
        "product_bullet_point": "2100mAh<br>fits <b>S3</b>",
        "product_description": None,
    }

    # Act
    rendered = esci_document(row)

    # Assert
    assert rendered == "Galaxy S3 Battery\n2100mAh fits  S3\n"
