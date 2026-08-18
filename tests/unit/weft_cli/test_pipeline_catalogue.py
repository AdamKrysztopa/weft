"""Unit tests for `weft_cli.pipeline_catalogue`.

Mirrors `packages/weft-cli/src/weft_cli/pipeline_catalogue.py`. Task **1.9**:
`weft-cli` is the only distribution allowed to open a pipeline document — G1 fixes the
kernel's dependencies at `pydantic` and `opentelemetry-api`, so the YAML parser lives
here, on the same footing `weft_cli.registry_bootstrap` already established for
`weft.toml`'s TOML. Covers the happy path (one document parses into the `Pipeline` the
kernel already validates, and a directory of documents becomes a `resolve()`-ready
catalogue keyed by each document's own `name:`), the edge case of two catalogue files
declaring the same name, and the error cases of unreadable YAML and a document that
parses as YAML but fails `Pipeline`'s own validation.
"""

from pathlib import Path

import pytest

from weft_cli.pipeline_catalogue import (
    DuplicatePipelineNameError,
    MalformedPipelineError,
    PipelineDocumentError,
    load_pipeline_catalogue,
    load_pipeline_document,
)
from weft_kernel.pipeline import Pipeline, StageDeclaration


def test_load_pipeline_document_parses_yaml_into_a_validated_pipeline(tmp_path: Path) -> None:
    # Arrange
    path = tmp_path / "base.yaml"
    path.write_text(
        "name: base\n"
        "stages:\n"
        "  - id: chunk\n"
        "    use: fixed-size\n"
        "    with: {size: 200, overlap: 20}\n"
    )

    # Act
    pipeline = load_pipeline_document(path)

    # Assert
    assert pipeline == Pipeline(
        name="base",
        stages=(
            StageDeclaration(id="chunk", use="fixed-size", config={"size": 200, "overlap": 20}),
        ),
    )


def test_load_pipeline_catalogue_keys_every_document_by_its_own_name_field(
    tmp_path: Path,
) -> None:
    # Arrange — the filename is deliberately not the pipeline's name, to prove the key
    # comes from the document's own `name:` field, never the path it was read from.
    (tmp_path / "root.yaml").write_text("name: base\nstages: [{id: chunk, use: fixed-size}]\n")
    (tmp_path / "child.yaml").write_text(
        "name: specific\nextends: base\ninsert: [{after: chunk, stage: {id: kw, use: keybert}}]\n"
    )

    # Act
    catalogue = load_pipeline_catalogue(tmp_path)

    # Assert
    assert set(catalogue) == {"base", "specific"}
    assert catalogue["specific"].extends == "base"


def test_load_pipeline_catalogue_refuses_two_documents_sharing_one_name(tmp_path: Path) -> None:
    # Arrange
    (tmp_path / "a.yaml").write_text("name: base\nstages: [{id: chunk, use: fixed-size}]\n")
    (tmp_path / "b.yaml").write_text("name: base\nstages: [{id: chunk, use: fixed-size}]\n")

    # Act / Assert
    with pytest.raises(DuplicatePipelineNameError, match="base"):
        load_pipeline_catalogue(tmp_path)


def test_load_pipeline_document_raises_for_yaml_that_does_not_parse(tmp_path: Path) -> None:
    # Arrange — an unterminated flow mapping: invalid YAML, not merely an invalid pipeline.
    path = tmp_path / "broken.yaml"
    path.write_text("name: base\nstages: [{id: chunk, use: fixed-size\n")

    # Act / Assert
    with pytest.raises(PipelineDocumentError, match="broken.yaml"):
        load_pipeline_document(path)


def test_load_pipeline_document_raises_for_valid_yaml_that_fails_pipeline_validation(
    tmp_path: Path,
) -> None:
    # Arrange — valid YAML, but `extends` and a non-empty `stages:` together have no
    # meaning to `Pipeline` itself (`weft_kernel.pipeline`'s own mutual-exclusivity rule).
    path = tmp_path / "confused.yaml"
    path.write_text("name: confused\nextends: base\nstages: [{id: chunk, use: fixed-size}]\n")

    # Act / Assert
    with pytest.raises(MalformedPipelineError, match="confused.yaml"):
        load_pipeline_document(path)
