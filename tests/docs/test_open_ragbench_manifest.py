"""`corpus/open-ragbench.toml` — ledger task **38.3**: the corpus Phase 38 measures on is pinned.

V1 accepts a corpus *"fetched by a pinned, checksummed script"*. The dataset's documents and its
question files are not tracked; this manifest is, and it is what makes the corpus bounded and named
without the bytes being here. Whether the pins still describe the bytes is
`scripts/fetch_corpus.py fetch --manifest corpus/open-ragbench.toml`'s job, which refuses a source
that misses its `source_sha256` before rendering it.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Final

import fetch_corpus
from open_ragbench import RAGBENCH_REVISION

_MANIFEST: Final[Path] = Path(__file__).resolve().parents[2] / "corpus" / "open-ragbench.toml"


def test_the_manifest_names_every_processed_document_of_the_pinned_revision() -> None:
    # Act
    name, documents = fetch_corpus.load_manifest(_MANIFEST)

    # Assert
    assert name == "open-ragbench-arxiv"
    assert len(documents) == 1000
    assert len({document.id for document in documents}) == 1000
    assert all(document.tier is fetch_corpus.Tier.FETCH for document in documents)
    assert all(f"/resolve/{RAGBENCH_REVISION}/" in document.source for document in documents)
    assert all(document.source_sha256 and document.sha256 for document in documents)


def test_the_manifest_pins_the_three_files_the_question_set_is_built_from() -> None:
    # Act
    raw = tomllib.loads(_MANIFEST.read_text(encoding="utf-8"))

    # Assert
    names = {entry["name"] for entry in raw["dataset_file"]}
    assert {"queries.json", "qrels.json", "answers.json"} <= names
    assert all(f"/resolve/{RAGBENCH_REVISION}/" in entry["source"] for entry in raw["dataset_file"])
    assert raw["dataset"]["revision"] == RAGBENCH_REVISION


def test_the_question_files_are_pinned_to_the_same_revision_with_their_digests() -> None:
    """`38.4`'s files are untracked; `corpus/open-ragbench-questions.toml` records the build that
    wrote them, so a run record's question-set digest traces to one split of one build."""
    # Act
    pin = tomllib.loads((_MANIFEST.parent / "open-ragbench-questions.toml").read_text("utf-8"))

    # Assert
    assert pin["build"]["revision"] == RAGBENCH_REVISION
    files = {entry["name"]: entry for entry in pin["file"]}
    assert set(files) == {"dev.toml", "test.toml"}
    assert sum(entry["questions"] for entry in files.values()) == pin["build"]["carried"]
    assert all(len(entry["question_set_digest"]) == 64 for entry in files.values())
